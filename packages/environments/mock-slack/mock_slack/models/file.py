"""SlackFile model."""

from datetime import datetime

from sqlalchemy import String, Boolean, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SlackFile(Base):
    __tablename__ = "slack_files"

    id: Mapped[str] = mapped_column(String, primary_key=True)   # e.g. F123ABC
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("slack_users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
    mimetype: Mapped[str] = mapped_column(String, default="text/plain")
    filetype: Mapped[str] = mapped_column(String, default="text")
    size: Mapped[int] = mapped_column(Integer, default=0)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_id: Mapped[str | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content: Mapped[str] = mapped_column(Text, default="")

    workspace: Mapped["Workspace"] = relationship(back_populates="files")  # noqa: F821
    user: Mapped["SlackUser"] = relationship(back_populates="files")  # noqa: F821
    channel: Mapped["Channel"] = relationship(back_populates="files")  # noqa: F821
