"""Reminder model."""

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    creator_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)  # who the reminder is for
    text: Mapped[str] = mapped_column(Text, default="")
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    complete_ts: Mapped[str | None] = mapped_column(String, nullable=True)

    workspace: Mapped["Workspace"] = relationship(back_populates="reminders")  # noqa: F821
