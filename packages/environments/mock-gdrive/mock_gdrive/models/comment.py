"""Comment and Reply models for Drive API v3."""

from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    modified_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Anchor (position reference in the document)
    anchor: Mapped[str | None] = mapped_column(String, nullable=True)

    # Quoted content from the file
    quoted_file_content_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    quoted_file_content_mime_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    file: Mapped["File"] = relationship(back_populates="comments")  # noqa: F821
    author: Mapped["User"] = relationship()  # noqa: F821
    replies: Mapped[list["Reply"]] = relationship(
        back_populates="comment", cascade="all, delete-orphan",
        order_by="Reply.created_time",
    )


class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    comment_id: Mapped[str] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    modified_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Action taken by this reply (e.g., "resolve", "reopen")
    action: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    comment: Mapped["Comment"] = relationship(back_populates="replies")
    author: Mapped["User"] = relationship()  # noqa: F821
