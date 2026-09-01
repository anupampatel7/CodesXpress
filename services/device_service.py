"""Device verification, fingerprint binding, and anti-fraud enforcement service."""

import logging
from typing import Optional, Tuple, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from models.base import utc_now
from models.device_binding import DeviceBinding, DeviceBindingStatus
from utils.security import hash_device_fingerprint

logger = logging.getLogger(__name__)


class DeviceService:
    """Service providing privacy-conscious browser/device fingerprint verification and binding."""

    @staticmethod
    async def verify_and_bind_device(
        session: AsyncSession,
        telegram_user_id: int,
        fingerprint_payload: Any,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[DeviceBinding]]:
        """Verify device fingerprint and atomically enforce 1-device = 1-account binding rule.

        Returns:
            Tuple of (success: bool, code_or_message: str, binding: Optional[DeviceBinding])
        """
        if not telegram_user_id or not fingerprint_payload:
            return False, "INVALID_DATA", None

        fp_hash = hash_device_fingerprint(fingerprint_payload)
        now = utc_now()

        # Check existing binding for this fingerprint
        stmt = select(DeviceBinding).where(DeviceBinding.fingerprint_hash == fp_hash)
        res = await session.execute(stmt)
        existing_binding = res.scalar_one_or_none()

        if existing_binding:
            if existing_binding.status == DeviceBindingStatus.BLOCKED:
                logger.warning(f"Verification rejected: Blocked device fingerprint {fp_hash[:8]}... for User {telegram_user_id}")
                return False, "DEVICE_BLOCKED", existing_binding

            if existing_binding.status == DeviceBindingStatus.ACTIVE:
                if existing_binding.telegram_user_id == telegram_user_id:
                    # Same user returning on verified device -> Valid
                    existing_binding.last_seen_at = now
                    if ip_address:
                        existing_binding.ip_address = ip_address
                    await session.flush()
                    return True, "DEVICE_VERIFIED_EXISTING", existing_binding
                else:
                    # Device already claimed by another Telegram ID -> REJECT
                    logger.warning(
                        f"Fraud blocked: Device {fp_hash[:8]}... already bound to User {existing_binding.telegram_user_id}, "
                        f"attempted by different User {telegram_user_id}"
                    )
                    return False, "DEVICE_ALREADY_BOUND", existing_binding

            elif existing_binding.status == DeviceBindingStatus.RELEASED:
                # Device was unlinked by admin -> Rebind to this user
                existing_binding.telegram_user_id = telegram_user_id
                existing_binding.status = DeviceBindingStatus.ACTIVE
                existing_binding.last_seen_at = now
                if user_agent:
                    existing_binding.user_agent = user_agent[:256]
                if ip_address:
                    existing_binding.ip_address = ip_address
                await session.flush()
                logger.info(f"Rebound released device {fp_hash[:8]}... to User {telegram_user_id}")
                return True, "DEVICE_REBOUND", existing_binding

        # Check if this user already has an active binding with a different fingerprint
        user_stmt = select(DeviceBinding).where(
            DeviceBinding.telegram_user_id == telegram_user_id,
            DeviceBinding.status == DeviceBindingStatus.ACTIVE,
        )
        user_res = await session.execute(user_stmt)
        user_existing = user_res.scalar_one_or_none()

        if user_existing:
            # User already verified on another device; update last seen
            user_existing.last_seen_at = now
            await session.flush()
            return True, "USER_ALREADY_VERIFIED", user_existing

        # New device fingerprint + New user -> Create atomic binding
        new_binding = DeviceBinding(
            fingerprint_hash=fp_hash,
            telegram_user_id=telegram_user_id,
            status=DeviceBindingStatus.ACTIVE,
            first_verified_at=now,
            last_seen_at=now,
            risk_score=0,
            user_agent=user_agent[:256] if user_agent else None,
            ip_address=ip_address,
        )
        session.add(new_binding)
        await session.flush()
        logger.info(f"Successfully bound new device {fp_hash[:8]}... to User {telegram_user_id}")
        return True, "DEVICE_BOUND_NEW", new_binding

    @staticmethod
    async def is_device_verified(session: AsyncSession, telegram_user_id: int) -> bool:
        """Check whether a Telegram user has an active device binding."""
        stmt = select(DeviceBinding.id).where(
            DeviceBinding.telegram_user_id == telegram_user_id,
            DeviceBinding.status == DeviceBindingStatus.ACTIVE,
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def get_device_binding_by_user(
        session: AsyncSession,
        telegram_user_id: int,
    ) -> Optional[DeviceBinding]:
        """Fetch active or latest device binding for a user."""
        stmt = (
            select(DeviceBinding)
            .where(DeviceBinding.telegram_user_id == telegram_user_id)
            .order_by(DeviceBinding.created_at.desc())
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_device_binding_by_hash(
        session: AsyncSession,
        fingerprint_hash: str,
    ) -> Optional[DeviceBinding]:
        """Fetch device binding by fingerprint hash."""
        stmt = select(DeviceBinding).where(DeviceBinding.fingerprint_hash == fingerprint_hash)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def release_device_binding(
        session: AsyncSession,
        admin_id: int,
        telegram_user_id: int,
    ) -> Tuple[bool, str]:
        """Admin action: Manually release a user's device binding to resolve legitimate false positives."""
        stmt = select(DeviceBinding).where(
            DeviceBinding.telegram_user_id == telegram_user_id,
            DeviceBinding.status == DeviceBindingStatus.ACTIVE,
        )
        res = await session.execute(stmt)
        binding = res.scalar_one_or_none()

        if not binding:
            return False, "No active device binding found for this user."

        binding.status = DeviceBindingStatus.RELEASED
        binding.last_seen_at = utc_now()
        await session.flush()
        logger.info(f"Admin #{admin_id} released device binding for User #{telegram_user_id}")
        return True, "Device binding successfully released."

    @staticmethod
    async def block_device_binding(
        session: AsyncSession,
        admin_id: int,
        telegram_user_id: int,
    ) -> Tuple[bool, str]:
        """Admin action: Block/blacklist a device binding."""
        stmt = select(DeviceBinding).where(
            DeviceBinding.telegram_user_id == telegram_user_id,
        )
        res = await session.execute(stmt)
        binding = res.scalar_one_or_none()

        if not binding:
            return False, "No device binding found for this user."

        binding.status = DeviceBindingStatus.BLOCKED
        await session.flush()
        logger.info(f"Admin #{admin_id} blocked device binding for User #{telegram_user_id}")
        return True, "Device binding successfully blocked."
