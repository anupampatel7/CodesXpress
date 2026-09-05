"""Coupon browsing, administrative management, and transactional redemption service."""

import logging
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_, delete
from models.coupon import Coupon, CouponCategory, StockType
from models.coupon_code import CouponCode, CodeStatus
from models.redemption import Redemption, RedemptionStatus
from models.user import User
from models.point_transaction import PointTransaction, TransactionType
from models.admin_action import AdminAction
from models.base import utc_now
from services.stock_service import StockService

logger = logging.getLogger(__name__)


class CouponService:
    """Service handling coupon management and atomic redemption workflows."""

    @staticmethod
    async def ensure_global_coupon_order(session: AsyncSession) -> None:
        """Ensure all coupons have a persistent display_order.

        If no coupons have display_order assigned yet (initial global setup),
        randomizes all existing coupons exactly ONCE and assigns sequential orders (1, 2, 3...).
        If some coupons already have display_order, assigns sequential orders (max + 1, max + 2...)
        to any new unassigned coupons deterministically, preserving existing coupons' positions.
        """
        stmt = select(Coupon).order_by(Coupon.id.asc())
        res = await session.execute(stmt)
        all_coupons = list(res.scalars().all())
        if not all_coupons:
            return

        assigned = [c for c in all_coupons if c.display_order and c.display_order > 0]
        unassigned = [c for c in all_coupons if not c.display_order or c.display_order <= 0]

        if not unassigned:
            return

        if not assigned:
            # Case 1: First time global initialization.
            # Randomize existing coupons exactly once globally.
            import random
            shuffled = list(unassigned)
            random.shuffle(shuffled)
            for idx, c in enumerate(shuffled, start=1):
                c.display_order = idx
        else:
            # Case 2: Existing coupons already have permanent positions.
            # Deterministically append unassigned coupons to the end.
            current_max = max(c.display_order for c in assigned)
            unassigned.sort(key=lambda c: (c.created_at or utc_now(), c.id or 0))
            for idx, c in enumerate(unassigned, start=1):
                c.display_order = current_max + idx

        await session.flush()

    @staticmethod
    async def get_available_coupons(
        session: AsyncSession,
        page: int = 1,
        per_page: int = 8,
    ) -> Tuple[List[Coupon], int, int]:
        """Fetch all active, non-expired coupons (including out-of-stock) with pagination in persistent global order."""
        # Ensure any coupons missing display_order are assigned
        check_stmt = select(Coupon.id).where(Coupon.display_order <= 0).limit(1)
        res_check = await session.execute(check_stmt)
        if res_check.scalar_one_or_none() is not None:
            await CouponService.ensure_global_coupon_order(session)

        now = utc_now()
        filters = [
            Coupon.is_active == True,
            or_(Coupon.expiry_date == None, Coupon.expiry_date > now),
        ]

        count_stmt = select(func.count(Coupon.id)).where(and_(*filters))
        total_count = (await session.execute(count_stmt)).scalar() or 0

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        query = (
            select(Coupon)
            .where(and_(*filters))
            .order_by(Coupon.display_order.asc(), Coupon.id.asc())
            .offset(offset)
            .limit(per_page)
        )
        res = await session.execute(query)
        coupons = list(res.scalars().all())

        return coupons, total_count, total_pages

    @staticmethod
    async def get_available_brands(
        session: AsyncSession,
        page: int = 1,
        per_page: int = 8,
    ) -> Tuple[List[str], int, int]:
        """Fetch distinct brands that have at least one active, non-expired, in-stock coupon."""
        now = utc_now()
        stmt = (
            select(Coupon.brand)
            .where(
                Coupon.is_active == True,
                or_(Coupon.expiry_date == None, Coupon.expiry_date > now),
                Coupon.stock > 0,
            )
            .distinct()
            .order_by(Coupon.brand.asc())
        )
        res = await session.execute(stmt)
        all_brands = [b for b in res.scalars().all() if b and b.strip()]

        total_count = len(all_brands)
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        offset = (page - 1) * per_page
        brands_page = all_brands[offset : offset + per_page]

        return brands_page, total_count, total_pages

    @staticmethod
    async def get_coupons_by_brand(
        session: AsyncSession,
        brand: str,
        page: int = 1,
        per_page: int = 6,
    ) -> Tuple[List[Coupon], int, int]:
        """Fetch active, non-expired, in-stock coupons for a specific brand."""
        now = utc_now()
        filters = [
            Coupon.brand == brand,
            Coupon.is_active == True,
            or_(Coupon.expiry_date == None, Coupon.expiry_date > now),
            Coupon.stock > 0,
        ]

        count_stmt = select(func.count(Coupon.id)).where(and_(*filters))
        total_count = (await session.execute(count_stmt)).scalar() or 0

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        query = (
            select(Coupon)
            .where(and_(*filters))
            .order_by(Coupon.points_required.asc(), Coupon.id.desc())
            .offset(offset)
            .limit(per_page)
        )
        res = await session.execute(query)
        coupons = list(res.scalars().all())

        return coupons, total_count, total_pages

    @staticmethod
    async def get_active_coupons(
        session: AsyncSession,
        category: Optional[str] = None,
        page: int = 1,
        per_page: int = 6,
    ) -> Tuple[List[Coupon], int, int]:
        """Fetch active, non-expired coupons with pagination."""
        now = utc_now()
        filters = [
            Coupon.is_active == True,
            or_(Coupon.expiry_date == None, Coupon.expiry_date > now),
        ]

        if category and category != "ALL":
            filters.append(Coupon.category == category)

        # Count total
        count_stmt = select(func.count(Coupon.id)).where(and_(*filters))
        total_count = (await session.execute(count_stmt)).scalar() or 0

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        # Fetch page items
        query = (
            select(Coupon)
            .where(and_(*filters))
            .order_by(Coupon.points_required.asc(), Coupon.id.desc())
            .offset(offset)
            .limit(per_page)
        )
        res = await session.execute(query)
        coupons = list(res.scalars().all())

        return coupons, total_count, total_pages

    @staticmethod
    async def get_all_coupons_admin(
        session: AsyncSession,
        page: int = 1,
        per_page: int = 8,
    ) -> Tuple[List[Coupon], int, int]:
        """Fetch all coupons including inactive/expired for admin panel."""
        count_stmt = select(func.count(Coupon.id))
        total_count = (await session.execute(count_stmt)).scalar() or 0

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        offset = (page - 1) * per_page

        query = (
            select(Coupon)
            .order_by(Coupon.id.desc())
            .offset(offset)
            .limit(per_page)
        )
        res = await session.execute(query)
        coupons = list(res.scalars().all())

        return coupons, total_count, total_pages

    @staticmethod
    async def search_coupons(session: AsyncSession, query_str: str) -> List[Coupon]:
        """Search active coupons by brand, title, or description."""
        search_pattern = f"%{query_str.strip()}%"
        now = utc_now()
        stmt = (
            select(Coupon)
            .where(
                Coupon.is_active == True,
                or_(Coupon.expiry_date == None, Coupon.expiry_date > now),
                or_(
                    Coupon.title.ilike(search_pattern),
                    Coupon.brand.ilike(search_pattern),
                    Coupon.description.ilike(search_pattern),
                ),
            )
            .limit(10)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_coupon_by_id(session: AsyncSession, coupon_id: int) -> Optional[Coupon]:
        """Retrieve coupon by ID."""
        stmt = select(Coupon).where(Coupon.id == coupon_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_user_redemption_count(session: AsyncSession, user_id: int, coupon_id: int) -> int:
        """Count how many times a user has redeemed a specific coupon."""
        stmt = select(func.count(Redemption.id)).where(
            Redemption.user_id == user_id,
            Redemption.coupon_id == coupon_id,
            Redemption.status == RedemptionStatus.SUCCESS,
        )
        return (await session.execute(stmt)).scalar() or 0

    @staticmethod
    async def redeem_coupon(
        session: AsyncSession,
        user_id: int,
        coupon_id: int,
    ) -> Tuple[bool, str, Optional[Redemption]]:
        """Atomically redeem a coupon using user points with strict concurrency safety.

        Guarantees:
        1. User points >= required points.
        2. Points never become negative.
        3. Stock never drops below zero.
        4. Unique code is allocated and marked USED atomically.
        5. Redemption & point transactions recorded in ledger.

        Returns:
            Tuple of (success, message, redemption_record)
        """
        # Fetch user
        user_stmt = select(User).where(User.id == user_id)
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            return False, "User account not found.", None

        if user.is_banned:
            return False, "Account suspended.", None

        # Fetch coupon
        coupon_stmt = select(Coupon).where(Coupon.id == coupon_id)
        coupon_res = await session.execute(coupon_stmt)
        coupon = coupon_res.scalar_one_or_none()
        if not coupon:
            return False, "Coupon not found.", None

        if not coupon.is_active:
            return False, "This coupon is currently unavailable.", None

        if coupon.is_expired:
            return False, "This coupon has expired.", None

        if user.points < coupon.points_required:
            needed = coupon.points_required - user.points
            return False, f"Insufficient points. Need {needed} ⭐.", None

        # Check redemption limit per user
        user_redemptions = await CouponService.get_user_redemption_count(session, user_id, coupon_id)
        if user_redemptions >= coupon.max_redemptions_per_user:
            return False, "Redemption limit reached.", None

        # Initial quick stock pre-check
        if coupon.stock_type == StockType.QUANTITY:
            if coupon.stock <= 0:
                return False, "Currently out of stock.", None

        points_to_deduct = coupon.points_required
        issued_code: str = ""

        try:
            # 1. Reserve Stock / Unique Code atomically
            if coupon.stock_type == StockType.QUANTITY:
                stock_stmt = (
                    update(Coupon)
                    .where(Coupon.id == coupon_id, Coupon.stock >= 1)
                    .values(stock=Coupon.stock - 1)
                )
                stock_res = await session.execute(stock_stmt)
                if stock_res.rowcount == 0:
                    return False, "Sorry! Yeh coupon out of stock ho chuka hai.", None

                issued_code = coupon.code or "COUPON-REWARD-CODE"

            elif coupon.stock_type == StockType.UNIQUE_CODES:
                code_query = (
                    select(CouponCode)
                    .where(
                        CouponCode.coupon_id == coupon_id,
                        CouponCode.status == CodeStatus.AVAILABLE,
                    )
                    .limit(1)
                )
                code_res = await session.execute(code_query)
                available_code = code_res.scalar_one_or_none()

                if not available_code:
                    return False, "Sorry! Unique coupon codes out of stock hain.", None

                code_update_stmt = (
                    update(CouponCode)
                    .where(
                        CouponCode.id == available_code.id,
                        CouponCode.status == CodeStatus.AVAILABLE,
                    )
                    .values(
                        status=CodeStatus.USED,
                        assigned_to_user_id=user_id,
                        assigned_at=utc_now(),
                    )
                )
                code_update_res = await session.execute(code_update_stmt)
                if code_update_res.rowcount == 0:
                    return False, "Concurrent reservation error. Please try again.", None

                issued_code = available_code.code

            # 2. Deduct user points atomically
            points_stmt = (
                update(User)
                .where(User.id == user_id, User.points >= points_to_deduct)
                .values(points=User.points - points_to_deduct)
            )
            points_res = await session.execute(points_stmt)
            if points_res.rowcount == 0:
                # Revert reserved stock/code if points deduction failed
                if coupon.stock_type == StockType.QUANTITY:
                    await session.execute(
                        update(Coupon).where(Coupon.id == coupon_id).values(stock=Coupon.stock + 1)
                    )
                elif coupon.stock_type == StockType.UNIQUE_CODES:
                    await session.execute(
                        update(CouponCode)
                        .where(CouponCode.coupon_id == coupon_id, CouponCode.code == issued_code)
                        .values(status=CodeStatus.AVAILABLE, assigned_to_user_id=None, assigned_at=None)
                    )
                return False, f"Insufficient points! Aapko {points_to_deduct} points ki zaroorat hai.", None

            if coupon.stock_type == StockType.UNIQUE_CODES:
                await StockService.get_authoritative_stock(session, coupon)

            # 3. Create redemption receipt
            redemption = Redemption(
                user_id=user_id,
                coupon_id=coupon_id,
                coupon_code=issued_code,
                points_spent=points_to_deduct,
                status=RedemptionStatus.SUCCESS,
            )
            session.add(redemption)

            # 4. Record points ledger transaction
            point_tx = PointTransaction(
                user_id=user_id,
                amount=-points_to_deduct,
                type=TransactionType.COUPON_REDEMPTION,
                reason=f"Redeemed coupon: {coupon.title}",
                reference_id=str(coupon.id),
            )
            session.add(point_tx)

            await session.flush()
            logger.info(
                f"User #{user.telegram_id} successfully redeemed Coupon #{coupon.id} ('{coupon.title}') for {points_to_deduct} points."
            )

            return True, "Redemption successful!", redemption

        except Exception as e:
            await session.rollback()
            logger.error(f"Atomic redemption failure for user ID {user_id} on coupon ID {coupon_id}: {e}", exc_info=True)
            return False, "Redemption transaction error occurred.", None

    @staticmethod
    async def create_coupon(
        session: AsyncSession,
        admin_id: int,
        title: str,
        brand: str,
        category: CouponCategory = CouponCategory.OTHER,
        value: str = "₹0",
        points_required: int = 1,
        stock_type: StockType = StockType.QUANTITY,
        stock: int = 0,
        code: Optional[str] = None,
        description: str = "",
        terms: str = "",
        expiry_date: Optional[datetime] = None,
        image_url: Optional[str] = None,
        max_redemptions_per_user: int = 1,
        display_order: Optional[int] = None,
    ) -> Coupon:
        """Create a new coupon entity."""
        if display_order is None or display_order <= 0:
            max_order_stmt = select(func.coalesce(func.max(Coupon.display_order), 0))
            max_order = (await session.execute(max_order_stmt)).scalar() or 0
            display_order = max_order + 1

        coupon = Coupon(
            title=title.strip(),
            brand=brand.strip(),
            category=category,
            value=value.strip(),
            points_required=points_required,
            stock_type=stock_type,
            stock=stock,
            code=code.strip() if code else None,
            description=description.strip(),
            terms=terms.strip(),
            expiry_date=expiry_date,
            image_url=image_url.strip() if image_url else None,
            is_active=True,
            max_redemptions_per_user=max_redemptions_per_user,
            display_order=display_order,
        )
        session.add(coupon)
        await session.flush()

        audit = AdminAction(
            admin_id=admin_id,
            action="ADD_COUPON",
            target=f"Coupon #{coupon.id} ({coupon.title})",
            details=f"Brand: {brand}, Value: {value}, Points: {points_required}, Mode: {stock_type.value}",
        )
        session.add(audit)
        await session.flush()
        return coupon

    @staticmethod
    async def toggle_coupon_status(session: AsyncSession, admin_id: int, coupon_id: int) -> Tuple[bool, str]:
        """Toggle active/disabled status of a coupon."""
        coupon = await CouponService.get_coupon_by_id(session, coupon_id)
        if not coupon:
            return False, "Coupon not found."

        coupon.is_active = not coupon.is_active
        status_name = "enabled" if coupon.is_active else "disabled"

        audit = AdminAction(
            admin_id=admin_id,
            action="TOGGLE_COUPON",
            target=f"Coupon #{coupon.id} ({coupon.title})",
            details=f"Set is_active = {coupon.is_active}",
        )
        session.add(audit)
        await session.flush()
        return True, f"Coupon {status_name} successfully."

    @staticmethod
    async def delete_coupon(session: AsyncSession, admin_id: int, coupon_id: int) -> Tuple[bool, str]:
        """Delete coupon and cascade delete codes and redemptions."""
        coupon = await CouponService.get_coupon_by_id(session, coupon_id)
        if not coupon:
            return False, "Coupon not found."

        title = coupon.title
        await session.delete(coupon)

        audit = AdminAction(
            admin_id=admin_id,
            action="DELETE_COUPON",
            target=f"Coupon #{coupon_id} ({title})",
            details="Deleted coupon from database",
        )
        session.add(audit)
        await session.flush()
        return True, "Coupon deleted successfully."

    @staticmethod
    async def update_coupon(
        session: AsyncSession,
        admin_id: int,
        coupon_id: int,
        title: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[CouponCategory] = None,
        value: Optional[str] = None,
        points_required: Optional[int] = None,
        description: Optional[str] = None,
        code: Optional[str] = None,
        terms: Optional[str] = None,
        max_redemptions_per_user: Optional[int] = None,
    ) -> Tuple[bool, str, Optional[Coupon]]:
        """Update editable properties of a coupon."""
        coupon = await CouponService.get_coupon_by_id(session, coupon_id)
        if not coupon:
            return False, "Coupon not found.", None

        changes = []
        if title is not None and title.strip():
            coupon.title = title.strip()
            changes.append(f"Title -> {title}")
        if brand is not None and brand.strip():
            coupon.brand = brand.strip()
            changes.append(f"Brand -> {brand}")
        if category is not None:
            coupon.category = category
            changes.append(f"Category -> {category.value}")
        if value is not None and value.strip():
            coupon.value = value.strip()
            changes.append(f"Value -> {value}")
        if points_required is not None and points_required >= 0:
            coupon.points_required = points_required
            changes.append(f"Points -> {points_required}")
        if description is not None:
            coupon.description = description.strip()
            changes.append("Description updated")
        if code is not None and coupon.stock_type == StockType.QUANTITY:
            coupon.code = code.strip()
            changes.append(f"Code -> {code}")
        if terms is not None:
            coupon.terms = terms.strip()
            changes.append("Terms updated")
        if max_redemptions_per_user is not None and max_redemptions_per_user >= 1:
            coupon.max_redemptions_per_user = max_redemptions_per_user
            changes.append(f"Max Per User -> {max_redemptions_per_user}")

        audit = AdminAction(
            admin_id=admin_id,
            action="EDIT_COUPON",
            target=f"Coupon #{coupon.id} ({coupon.title})",
            details=", ".join(changes) if changes else "No changes",
        )
        session.add(audit)
        await session.flush()
        return True, "Coupon updated successfully.", coupon
