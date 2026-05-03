"""ScheduledMessage model."""

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)           # Sm... style ID
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("slack_users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")
    post_at: Mapped[int] = mapped_column(Integer, nullable=False)        # Unix timestamp
    thread_ts: Mapped[str | None] = mapped_column(String, nullable=True)
    date_created: Mapped[int] = mapped_column(Integer, nullable=False)   # Unix timestamp
    is_delivered: Mapped[bool] = mapped_column(Boolean, default=False)
