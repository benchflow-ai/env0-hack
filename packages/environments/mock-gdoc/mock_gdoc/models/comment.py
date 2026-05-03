"""Comment model."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    modified_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    document: Mapped["Document"] = relationship(back_populates="comments")  # noqa: F821
    author: Mapped["User"] = relationship(back_populates="comments")  # noqa: F821
    replies: Mapped[list["Reply"]] = relationship(back_populates="comment", cascade="all, delete-orphan", order_by="Reply.created_time")  # noqa: F821
