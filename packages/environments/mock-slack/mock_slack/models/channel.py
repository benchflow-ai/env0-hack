"""Channel model."""

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. C123ABC
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_im: Mapped[bool] = mapped_column(Boolean, default=False)       # direct message
    is_mpim: Mapped[bool] = mapped_column(Boolean, default=False)     # multi-party DM
    creator_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    topic: Mapped[str] = mapped_column(String, default="")
    purpose: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    workspace: Mapped["Workspace"] = relationship(back_populates="channels")  # noqa: F821
    members: Mapped[list["ChannelMember"]] = relationship(back_populates="channel", cascade="all, delete-orphan")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(back_populates="channel", cascade="all, delete-orphan")  # noqa: F821
    pins: Mapped[list["Pin"]] = relationship(back_populates="channel", cascade="all, delete-orphan")  # noqa: F821
    files: Mapped[list["SlackFile"]] = relationship(back_populates="channel", cascade="all, delete-orphan")  # noqa: F821
