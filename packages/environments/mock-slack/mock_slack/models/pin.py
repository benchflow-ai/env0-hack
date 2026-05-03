"""Pin model."""

from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Pin(Base):
    __tablename__ = "pins"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), nullable=False)
    message_id: Mapped[str] = mapped_column(ForeignKey("slack_messages.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("slack_users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    channel: Mapped["Channel"] = relationship(back_populates="pins")  # noqa: F821
    user: Mapped["SlackUser"] = relationship(back_populates="pins")  # noqa: F821
