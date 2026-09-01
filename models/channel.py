"""Required Telegram Channels configuration model."""

from typing import Optional
from sqlalchemy import (
    Boolean,
    Integer,
    String,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base, TimestampMixin


class Channel(Base, TimestampMixin):
    """Dynamic required Telegram channel configuration."""

    __tablename__ = "channels"
    __table_args__ = (
        Index("ix_channels_channel_id", "channel_id", unique=True),
        Index("ix_channels_is_active_is_required", "is_active", "is_required"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Channel ID (e.g. -1001234567890 or @channelname)
    channel_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    invite_link: Mapped[str] = mapped_column(String(256), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Channel(id={self.id}, title='{self.title}', channel_id='{self.channel_id}', active={self.is_active})>"
