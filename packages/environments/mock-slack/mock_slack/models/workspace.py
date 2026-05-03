"""Workspace model — top-level Slack entity."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False, default="")
    team_id: Mapped[str] = mapped_column(String, nullable=False, default="")

    users: Mapped[list["SlackUser"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")  # noqa: F821
    channels: Mapped[list["Channel"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")  # noqa: F821
    files: Mapped[list["SlackFile"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")  # noqa: F821
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")  # noqa: F821
