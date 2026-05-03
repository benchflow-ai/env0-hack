"""ChannelMember many-to-many model."""

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ChannelMember(Base):
    __tablename__ = "channel_members"

    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("slack_users.id"), primary_key=True)

    channel: Mapped["Channel"] = relationship(back_populates="members")  # noqa: F821
    user: Mapped["SlackUser"] = relationship(back_populates="channel_memberships")  # noqa: F821
