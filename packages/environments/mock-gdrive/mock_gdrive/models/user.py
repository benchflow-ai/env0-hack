"""User model."""

from sqlalchemy import String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, default="")
    storage_quota_limit: Mapped[int] = mapped_column(BigInteger, default=15_000_000_000)  # 15GB
    storage_used: Mapped[int] = mapped_column(BigInteger, default=0)

    files: Mapped[list["File"]] = relationship(  # noqa: F821
        back_populates="owner", foreign_keys="File.owner_id",
    )
