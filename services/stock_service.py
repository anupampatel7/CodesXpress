"""Inventory and stock synchronization service for QUANTITY and UNIQUE_CODES modes."""

import logging
from typing import Tuple, Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_
from models.coupon import Coupon, StockType
from models.coupon_code import CouponCode, CodeStatus
from models.admin_action import AdminAction
from utils.validators import parse_bulk_codes

logger = logging.getLogger(__name__)


class StockService:
    """Service handling stock calculations, manual restock, and bulk code imports."""

    @staticmethod
    async def get_authoritative_stock(session: AsyncSession, coupon: Coupon) -> int:
        """Calculate the true available stock based on the coupon inventory mode."""
        if coupon.stock_type == StockType.UNIQUE_CODES:
            stmt = select(func.count(CouponCode.id)).where(
                CouponCode.coupon_id == coupon.id,
                CouponCode.status == CodeStatus.AVAILABLE,
            )
            count = (await session.execute(stmt)).scalar() or 0
            # Sync coupon.stock column
            if coupon.stock != count:
                coupon.stock = count
                await session.flush()
            return count
        else:
            return max(0, coupon.stock)

    @staticmethod
    async def restock_quantity(
        session: AsyncSession,
        admin_id: int,
        coupon_id: int,
        quantity_to_add: int,
    ) -> Tuple[bool, str, int]:
        """Add numerical stock to a QUANTITY mode coupon.

        Returns:
            Tuple of (success, message, new_stock_count)
        """
        if quantity_to_add <= 0:
            return False, "Restock quantity must be greater than zero.", 0

        stmt = select(Coupon).where(Coupon.id == coupon_id)
        res = await session.execute(stmt)
        coupon = res.scalar_one_or_none()

        if not coupon:
            return False, "Coupon not found.", 0

        if coupon.stock_type != StockType.QUANTITY:
            return False, "This coupon uses unique codes inventory. Use 'Bulk Add Codes' instead.", coupon.stock

        old_stock = coupon.stock
        new_stock = old_stock + quantity_to_add
        coupon.stock = new_stock

        audit = AdminAction(
            admin_id=admin_id,
            action="RESTOCK_COUPON",
            target=f"Coupon #{coupon.id} ({coupon.title})",
            details=f"Old Stock: {old_stock}, Added: {quantity_to_add}, New Stock: {new_stock}",
        )
        session.add(audit)
        await session.flush()

        logger.info(f"Admin #{admin_id} restocked Coupon #{coupon.id} by +{quantity_to_add} (New: {new_stock})")
        return True, f"Stock updated from {old_stock} to {new_stock} (+{quantity_to_add}).", new_stock

    @staticmethod
    async def bulk_import_unique_codes(
        session: AsyncSession,
        admin_id: int,
        coupon_id: int,
        raw_text: str,
    ) -> Tuple[bool, str, Dict[str, int]]:
        """Import unique coupon codes in bulk, deduplicating against database.

        Returns:
            Tuple of (success, message, stats_dict)
        """
        stmt = select(Coupon).where(Coupon.id == coupon_id)
        res = await session.execute(stmt)
        coupon = res.scalar_one_or_none()

        if not coupon:
            return False, "Coupon not found.", {"imported": 0, "duplicates": 0, "invalid": 0}

        if coupon.stock_type != StockType.UNIQUE_CODES:
            coupon.stock_type = StockType.UNIQUE_CODES
            await session.flush()

        parsed_codes, total_raw = parse_bulk_codes(raw_text)
        if not parsed_codes:
            return False, "No valid coupon codes found in input.", {"imported": 0, "duplicates": 0, "invalid": 0}

        # Check existing codes for this coupon in database
        existing_stmt = select(CouponCode.code).where(
            CouponCode.coupon_id == coupon_id,
            CouponCode.code.in_(parsed_codes),
        )
        existing_codes = set((await session.execute(existing_stmt)).scalars().all())

        new_codes_to_insert = []
        duplicate_count = 0

        for code in parsed_codes:
            if code in existing_codes:
                duplicate_count += 1
            else:
                new_codes_to_insert.append(CouponCode(
                    coupon_id=coupon_id,
                    code=code,
                    status=CodeStatus.AVAILABLE,
                ))

        if new_codes_to_insert:
            session.add_all(new_codes_to_insert)
            await session.flush()

        # Recalculate authoritative stock
        new_total_stock = await StockService.get_authoritative_stock(session, coupon)

        stats = {
            "imported": len(new_codes_to_insert),
            "duplicates": duplicate_count,
            "total_available": new_total_stock,
        }

        audit = AdminAction(
            admin_id=admin_id,
            action="BULK_ADD_CODES",
            target=f"Coupon #{coupon.id} ({coupon.title})",
            details=f"Imported: {stats['imported']}, Duplicates: {stats['duplicates']}, Total Available: {new_total_stock}",
        )
        session.add(audit)
        await session.flush()

        msg = (
            f"✅ <b>Codes Import Report:</b>\n\n"
            f"📥 Imported: <b>{stats['imported']}</b>\n"
            f"⚠️ Duplicates Skipped: <b>{stats['duplicates']}</b>\n"
            f"📦 Current Available Stock: <b>{stats['total_available']}</b>"
        )
        return True, msg, stats

    @staticmethod
    async def get_coupon_codes(
        session: AsyncSession,
        coupon_id: int,
        limit: int = 30,
        offset: int = 0,
    ) -> Tuple[List[CouponCode], Dict[str, int]]:
        """Retrieve coupon codes list and status breakdown for a coupon."""
        stmt = (
            select(CouponCode)
            .where(CouponCode.coupon_id == coupon_id)
            .order_by(CouponCode.status.asc(), CouponCode.id.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        codes = list(res.scalars().all())

        # Count breakdown
        counts_stmt = (
            select(CouponCode.status, func.count(CouponCode.id))
            .where(CouponCode.coupon_id == coupon_id)
            .group_by(CouponCode.status)
        )
        counts_res = await session.execute(counts_stmt)
        breakdown = {s.value: 0 for s in CodeStatus}
        for status_val, count in counts_res.all():
            key = status_val.value if hasattr(status_val, "value") else str(status_val)
            breakdown[key] = count

        return codes, breakdown
