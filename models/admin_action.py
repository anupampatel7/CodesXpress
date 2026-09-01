"""Admin audit action model tracking administrative modifications."""

from sqlalchemy import (
    BigInteger,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base, TimestampMixin


class AdminAction(Base, TimestampMixin):
    """Audit record of actions performed by administrators."""

    __tablename__ = "admin_actions"
    __table_args__ = (
        Index("ix_admin_actions_admin_id", "admin_id"),
        Index("ix_admin_actions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(128), default="")
    details: Mapped[str] = mapped_column(Text, default="")

    def __repr__(self) -> str:
        return f"<AdminAction(id={self.id}, admin_id={self.admin_id}, action='{self.action}', target='{self.target}')>"
