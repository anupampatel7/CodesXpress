"""Coupon database model supporting categories and dual stock modes."""

import enum
from typing import List, Optional
from datetime import datetime
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    Boolean,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base, TimestampMixin


class StockType(str, enum.Enum):
    """Inventory management mode for the coupon."""
    QUANTITY = "QUANTITY"          # Single reusable code with numerical stock count
    UNIQUE_CODES = "UNIQUE_CODES"  # Pool of distinct one-time coupon codes


class CouponCategory(str, enum.Enum):
    """Categorization for browsing coupons."""
    SHOPPING = "Shopping"
    FOOD = "Food"
    TRAVEL = "Travel"
    PAYMENTS = "Payments"
    RECHARGE = "Recharge"
    GAMING = "Gaming"
    OTHER = "Other"


class Coupon(Base, TimestampMixin):
    """Coupon model defining reward value, cost in points, and stock."""

    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="chk_coupon_stock_non_negative"),
        CheckConstraint("points_required >= 0", name="chk_coupon_points_non_negative"),
        Index("ix_coupons_is_active_category", "is_active", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[CouponCategory] = mapped_column(
        Enum(CouponCategory),
        default=CouponCategory.OTHER,
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g., '₹100', '10% OFF'
    points_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    # Inventory Mode & Stock
    stock_type: Mapped[StockType] = mapped_column(
        Enum(StockType),
        default=StockType.QUANTITY,
        nullable=False,
    )
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Static code for QUANTITY mode (nullable if using UNIQUE_CODES pool)
    code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    terms: Mapped[str] = mapped_column(Text, default="Valid once per user. Subject to brand terms.")
    expiry_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_redemptions_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    unique_codes: Mapped[List["CouponCode"]] = relationship(
        "CouponCode",
        back_populates="coupon",
        cascade="all, delete-orphan",
    )
    redemptions: Mapped[List["Redemption"]] = relationship(
        "Redemption",
        back_populates="coupon",
        cascade="all, delete-orphan",
    )

    @property
    def is_expired(self) -> bool:
        """Check if the coupon has passed its expiry date."""
        if not self.expiry_date:
            return False
        from models.base import utc_now
        return utc_now() > self.expiry_date

    def __repr__(self) -> str:
        return f"<Coupon(id={self.id}, title='{self.title}', stock={self.stock}, points={self.points_required})>"
