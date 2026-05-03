"""User model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)

    documents: Mapped[list["Document"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821
    comments: Mapped[list["Comment"]] = relationship(back_populates="author", cascade="all, delete-orphan")  # noqa: F821
