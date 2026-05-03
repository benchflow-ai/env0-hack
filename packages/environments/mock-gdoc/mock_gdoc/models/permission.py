"""Permission model for document sharing."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="user")  # user, anyone
    role: Mapped[str] = mapped_column(String, nullable=False, default="reader")  # owner, writer, commenter, reader
    email_address: Mapped[str] = mapped_column(String, nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    document: Mapped["Document"] = relationship(back_populates="permissions")  # noqa: F821
