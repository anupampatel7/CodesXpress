"""Referral tracking model with anti-fraud statuses and single-referrer constraint."""

import enum
from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base, TimestampMixin


class ReferralStatus(str, enum.Enum):
    """Status of the referral lifecycle."""
    PENDING = "PENDING"          # User registered via link; pending channel join / verification
    SUCCESSFUL = "SUCCESSFUL"    # All requirements met; +1 point awarded to referrer
    REJECTED = "REJECTED"        # Disqualified due to fraud/abuse or validation failure


class Referral(Base, TimestampMixin):
    """Tracks the 1-to-1 referral relationship between two users."""

    __tablename__ = "referrals"
    __table_args__ = (
        # A referred user can only have ONE referrer in the bot lifetime
        UniqueConstraint("referred_id", name="uq_single_referral_per_user"),
        Index("ix_referrals_referrer_status", "referrer_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    referred_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus),
        default=ReferralStatus.PENDING,
        nullable=False,
    )
    reward_given: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    referrer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referrer_id],
        back_populates="referrals_made",
    )
    referred_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referred_id],
        back_populates="referral_received",
    )

    def __repr__(self) -> str:
        return f"<Referral(id={self.id}, referrer_id={self.referrer_id}, referred_id={self.referred_id}, status={self.status})>"
