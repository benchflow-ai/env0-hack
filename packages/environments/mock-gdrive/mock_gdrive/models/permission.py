"""Permission model."""

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)

    # Role: owner, organizer, fileOrganizer, writer, commenter, reader
    role: Mapped[str] = mapped_column(String, nullable=False)

    # Type: user, group, domain, anyone
    type: Mapped[str] = mapped_column(String, nullable=False)

    # For type=user or type=group
    email_address: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # For type=domain
    domain: Mapped[str | None] = mapped_column(String, nullable=True)

    # Whether this permission is inherited from a parent folder
    inherited: Mapped[bool] = mapped_column(Boolean, default=False)
    inherited_from: Mapped[str | None] = mapped_column(String, nullable=True)

    # Discovery
    allow_file_discovery: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Expiration
    expiration_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Metadata
    pending_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # View (e.g., "published")
    view: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    file: Mapped["File"] = relationship(back_populates="permissions")  # noqa: F821
