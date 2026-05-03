"""File model — covers files, folders, and shortcuts."""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Text, LargeBinary, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="Untitled")
    mime_type: Mapped[str] = mapped_column(String, nullable=False, default="application/octet-stream")

    # Single parent (Google deprecated multi-parent in 2020)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    # Ownership
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    last_modifying_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    modified_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    viewed_by_me_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shared_with_me_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    modified_by_me_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trashed_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Trashing user
    trashing_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # State flags
    trashed: Mapped[bool] = mapped_column(Boolean, default=False)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    explicitly_trashed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Content
    content_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0)

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    app_properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    web_view_link: Mapped[str | None] = mapped_column(String, nullable=True)
    web_content_link: Mapped[str | None] = mapped_column(String, nullable=True)
    writers_can_share: Mapped[bool] = mapped_column(Boolean, default=True)
    copy_requires_writer_permission: Mapped[bool] = mapped_column(Boolean, default=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    full_file_extension: Mapped[str | None] = mapped_column(String, nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String, nullable=True)
    folder_color_rgb: Mapped[str | None] = mapped_column(String, nullable=True)
    icon_link: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_link: Mapped[str | None] = mapped_column(String, nullable=True)
    has_thumbnail: Mapped[bool] = mapped_column(Boolean, default=False)
    resource_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # Shortcut fields (only for mimeType = application/vnd.google-apps.shortcut)
    shortcut_target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    shortcut_target_mime_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    owner: Mapped["User"] = relationship(  # noqa: F821
        back_populates="files", foreign_keys=[owner_id],
    )
    last_modifying_user: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[last_modifying_user_id],
    )
    trashing_user: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[trashing_user_id],
    )
    parent: Mapped["File | None"] = relationship(
        remote_side="File.id", foreign_keys=[parent_id],
    )
    children: Mapped[list["File"]] = relationship(
        back_populates="parent", foreign_keys=[parent_id],
    )
    permissions: Mapped[list["Permission"]] = relationship(  # noqa: F821
        back_populates="file", cascade="all, delete-orphan",
    )
    comments: Mapped[list["Comment"]] = relationship(  # noqa: F821
        back_populates="file", cascade="all, delete-orphan",
    )
    revisions: Mapped[list["Revision"]] = relationship(  # noqa: F821
        back_populates="file", cascade="all, delete-orphan",
    )

    @property
    def is_folder(self) -> bool:
        return self.mime_type == "application/vnd.google-apps.folder"

    @property
    def is_shortcut(self) -> bool:
        return self.mime_type == "application/vnd.google-apps.shortcut"

    @property
    def is_google_type(self) -> bool:
        return self.mime_type.startswith("application/vnd.google-apps.")

    @property
    def md5_checksum(self) -> str | None:
        if self.content_blob:
            return hashlib.md5(self.content_blob).hexdigest()
        if self.content_text:
            return hashlib.md5(self.content_text.encode()).hexdigest()
        return None

    @property
    def sha256_checksum(self) -> str | None:
        if self.content_blob:
            return hashlib.sha256(self.content_blob).hexdigest()
        if self.content_text:
            return hashlib.sha256(self.content_text.encode()).hexdigest()
        return None

    @property
    def head_revision_id(self) -> str:
        return f"rev_{self.id}_{self.version}"
