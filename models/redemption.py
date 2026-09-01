"""Redemption record model storing user coupon redemptions."""

import enum
from sqlalchemy import (
    Enum,
    ForeignKey,
    Integer,
    String,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base, TimestampMixin


class RedemptionStatus(str, enum.Enum):
    """Status of redemption."""
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"


class Redemption(Base, TimestampMixin):
    """Stores coupon redemption receipts including points deducted and code issued."""

    __tablename__ = "redemptions"
    __table_args__ = (
        Index("ix_redemptions_user_coupon", "user_id", "coupon_id"),
        Index("ix_redemptions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    coupon_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("coupons.id", ondelete="CASCADE"),
        nullable=False,
    )
    coupon_code: Mapped[str] = mapped_column(String(128), nullable=False)
    points_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RedemptionStatus] = mapped_column(
        Enum(RedemptionStatus),
        default=RedemptionStatus.SUCCESS,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="redemptions")
    coupon: Mapped["Coupon"] = relationship("Coupon", back_populates="redemptions")

    def __repr__(self) -> str:
        return f"<Redemption(id={self.id}, user_id={self.user_id}, coupon_id={self.coupon_id}, code='{self.coupon_code}')>"
