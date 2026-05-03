"""Reaction model."""

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Reaction(Base):
    __tablename__ = "reactions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("slack_messages.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("slack_users.id"), nullable=False)
    emoji_name: Mapped[str] = mapped_column(String, nullable=False)

    message: Mapped["Message"] = relationship(back_populates="reactions")  # noqa: F821
    user: Mapped["SlackUser"] = relationship(back_populates="reactions")  # noqa: F821
