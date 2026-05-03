"""Shared Drive model for Drive API v3."""

from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Drive(Base):
    __tablename__ = "drives"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")

    created_time: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    color_rgb: Mapped[str | None] = mapped_column(String, nullable=True)
    theme_id: Mapped[str | None] = mapped_column(String, nullable=True)
    org_unit_id: Mapped[str | None] = mapped_column(String, nullable=True)

    background_image_link: Mapped[str | None] = mapped_column(String, nullable=True)
    background_image_file: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Restrictions (stored as individual columns for queryability)
    admin_managed_restrictions: Mapped[bool] = mapped_column(Boolean, default=False)
    copy_requires_writer_permission: Mapped[bool] = mapped_column(Boolean, default=False)
    domain_users_only: Mapped[bool] = mapped_column(Boolean, default=False)
    drive_members_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sharing_folders_requires_organizer_permission: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    # Creator user ID (not in the real API resource, but useful for access control)
    creator_id: Mapped[str | None] = mapped_column(String, nullable=True)
