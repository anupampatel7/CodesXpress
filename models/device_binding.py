"""Device binding and browser fingerprint model for anti-fraud referral protection."""

import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Integer,
    String,
    DateTime,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base, TimestampMixin


class DeviceBindingStatus(str, enum.Enum):
    """Lifecycle status of a device binding."""
    ACTIVE = "ACTIVE"          # Bound to telegram user
    RELEASED = "RELEASED"      # Manually unlinked/released by admin
    BLOCKED = "BLOCKED"        # Blacklisted due to verified fraud
    SUSPICIOUS = "SUSPICIOUS"  # Flagged for review


class DeviceBinding(Base, TimestampMixin):
    """Maps a unique device/browser fingerprint hash to a single Telegram account."""

    __tablename__ = "device_bindings"
    __table_args__ = (
        UniqueConstraint("fingerprint_hash", name="uq_device_fingerprint_hash"),
        Index("ix_device_bindings_user_id", "telegram_user_id"),
        Index("ix_device_bindings_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[DeviceBindingStatus] = mapped_column(
        Enum(DeviceBindingStatus),
        default=DeviceBindingStatus.ACTIVE,
        nullable=False,
    )
    first_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<DeviceBinding(id={self.id}, user_id={self.telegram_user_id}, status={self.status})>"
