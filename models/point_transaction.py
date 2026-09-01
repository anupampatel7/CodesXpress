"""Point transactions ledger model for complete financial & rewards auditability."""

import enum
from typing import Optional
from sqlalchemy import (
    Enum,
    ForeignKey,
    Integer,
    String,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base, TimestampMixin


class TransactionType(str, enum.Enum):
    """Types of points balance mutations."""
    REFERRAL_REWARD = "REFERRAL_REWARD"
    COUPON_REDEMPTION = "COUPON_REDEMPTION"
    ADMIN_ADD = "ADMIN_ADD"
    ADMIN_REMOVE = "ADMIN_REMOVE"
    BONUS = "BONUS"
    ADJUSTMENT = "ADJUSTMENT"


class PointTransaction(Base, TimestampMixin):
    """Immutable ledger entry for every point addition or deduction."""

    __tablename__ = "point_transactions"
    __table_args__ = (
        Index("ix_point_transactions_user_type", "user_id", "type"),
        Index("ix_point_transactions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Signed amount (+1, -6, etc.)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(256), default="")
    # Optional external reference (e.g. referral_id, redemption_id, admin_id)
    reference_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="point_transactions")

    def __repr__(self) -> str:
        return f"<PointTransaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, type={self.type})>"
