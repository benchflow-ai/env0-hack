"""Revision model for Drive API v3."""

from datetime import datetime, timezone

from sqlalchemy import String, BigInteger, Boolean, DateTime, LargeBinary, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Revision(Base):
    __tablename__ = "revisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    last_modifying_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    modified_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    size: Mapped[int] = mapped_column(BigInteger, default=0)
    md5_checksum: Mapped[str | None] = mapped_column(String, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)

    # Content snapshot
    content_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # Publishing
    keep_forever: Mapped[bool] = mapped_column(Boolean, default=False)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    publish_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    published_outside_domain: Mapped[bool] = mapped_column(Boolean, default=False)
    published_link: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    file: Mapped["File"] = relationship(back_populates="revisions")  # noqa: F821
    last_modifying_user: Mapped["User | None"] = relationship()  # noqa: F821
