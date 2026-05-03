"""Change model for Drive API v3 changes.list."""

from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"), nullable=True)

    change_type: Mapped[str] = mapped_column(String, nullable=False, default="file")
    time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    removed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    file: Mapped["File | None"] = relationship()  # noqa: F821
