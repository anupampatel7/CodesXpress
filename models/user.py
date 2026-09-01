"""User database model with points balance and referral links."""

from typing import List, Optional
from sqlalchemy import BigInteger, CheckConstraint, Integer, String, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User account tracking Telegram identity, points, and referral status."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("points >= 0", name="chk_user_points_non_negative"),
        Index("ix_users_telegram_id", "telegram_id", unique=True),
        Index("ix_users_referral_code", "referral_code", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Store referrer telegram ID if referred
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    referrals_made: Mapped[List["Referral"]] = relationship(
        "Referral",
        foreign_keys="Referral.referrer_id",
        back_populates="referrer",
        cascade="all, delete-orphan",
    )
    referral_received: Mapped[Optional["Referral"]] = relationship(
        "Referral",
        foreign_keys="Referral.referred_id",
        back_populates="referred_user",
        uselist=False,
    )
    redemptions: Mapped[List["Redemption"]] = relationship(
        "Redemption",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    point_transactions: Mapped[List["PointTransaction"]] = relationship(
        "PointTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tg_id={self.telegram_id}, points={self.points})>"
