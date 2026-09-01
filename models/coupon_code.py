"""CouponCode model for Mode B: Individual unique coupon codes inventory."""

import enum
from typing import Optional
from datetime import datetime
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base, TimestampMixin


class CodeStatus(str, enum.Enum):
    """Lifecycle status of a specific coupon code."""
    AVAILABLE = "AVAILABLE"  # Ready to be assigned
    USED = "USED"            # Assigned to a user upon successful redemption
    RESERVED = "RESERVED"    # Temporarily locked during checkout flow


class CouponCode(Base, TimestampMixin):
    """Individual unique coupon code belonging to a coupon."""

    __tablename__ = "coupon_codes"
    __table_args__ = (
        UniqueConstraint("coupon_id", "code", name="uq_coupon_id_code"),
        Index("ix_coupon_codes_coupon_status", "coupon_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coupon_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("coupons.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[CodeStatus] = mapped_column(
        Enum(CodeStatus),
        default=CodeStatus.AVAILABLE,
        nullable=False,
    )
    
    # User to whom this specific code was assigned
    assigned_to_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    coupon: Mapped["Coupon"] = relationship("Coupon", back_populates="unique_codes")
    assigned_user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<CouponCode(id={self.id}, coupon_id={self.coupon_id}, status={self.status})>"
