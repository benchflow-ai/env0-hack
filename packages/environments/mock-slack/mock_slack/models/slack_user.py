"""SlackUser model."""

from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SlackUser(Base):
    __tablename__ = "slack_users"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. U123ABC
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(
        String, nullable=False, default=""
    )  # handle / username
    real_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    email: Mapped[str] = mapped_column(String, nullable=False, default="")
    title: Mapped[str] = mapped_column(String, default="")
    status_text: Mapped[str] = mapped_column(String, default="")
    status_emoji: Mapped[str] = mapped_column(String, default="")
    presence: Mapped[str] = mapped_column(String, default="active")  # online/away/etc.
    avatar_url: Mapped[str] = mapped_column(String, default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    tz: Mapped[str] = mapped_column(String, default="America/Los_Angeles")

    workspace: Mapped["Workspace"] = relationship(back_populates="users")  # noqa: F821
    channel_memberships: Mapped[list["ChannelMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821
    reactions: Mapped[list["Reaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821
    files: Mapped[list["SlackFile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821
    pins: Mapped[list["Pin"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821
