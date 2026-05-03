"""Document model."""

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    body_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    document_style_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    named_styles_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    lists_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    inline_objects_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    footers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    footnotes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    named_ranges_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    positioned_objects_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    tabs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    revision_id: Mapped[str] = mapped_column(String, nullable=False, default="1")
    suggestions_view_mode: Mapped[str] = mapped_column(
        String, nullable=False, default="DEFAULT_FOR_CURRENT_ACCESS"
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    modified_time: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="documents")  # noqa: F821
    revisions: Mapped[list["DocumentRevision"]] = relationship(back_populates="document", cascade="all, delete-orphan")  # noqa: F821
    comments: Mapped[list["Comment"]] = relationship(back_populates="document", cascade="all, delete-orphan")  # noqa: F821
    permissions: Mapped[list["Permission"]] = relationship(back_populates="document", cascade="all, delete-orphan")  # noqa: F821

    # --- JSON property accessors ---

    def _json_prop(self, attr: str) -> dict:
        val = getattr(self, attr)
        return json.loads(val) if val else {}

    def _set_json_prop(self, attr: str, value: dict):
        setattr(self, attr, json.dumps(value))

    @property
    def body(self) -> dict:
        return self._json_prop("body_json")

    @body.setter
    def body(self, value: dict):
        self._set_json_prop("body_json", value)

    @property
    def document_style(self) -> dict:
        return self._json_prop("document_style_json")

    @document_style.setter
    def document_style(self, value: dict):
        self._set_json_prop("document_style_json", value)

    @property
    def named_styles(self) -> dict:
        return self._json_prop("named_styles_json")

    @named_styles.setter
    def named_styles(self, value: dict):
        self._set_json_prop("named_styles_json", value)

    @property
    def lists(self) -> dict:
        return self._json_prop("lists_json")

    @lists.setter
    def lists(self, value: dict):
        self._set_json_prop("lists_json", value)

    @property
    def inline_objects(self) -> dict:
        return self._json_prop("inline_objects_json")

    @inline_objects.setter
    def inline_objects(self, value: dict):
        self._set_json_prop("inline_objects_json", value)

    @property
    def headers(self) -> dict:
        return self._json_prop("headers_json")

    @headers.setter
    def headers(self, value: dict):
        self._set_json_prop("headers_json", value)

    @property
    def footers(self) -> dict:
        return self._json_prop("footers_json")

    @footers.setter
    def footers(self, value: dict):
        self._set_json_prop("footers_json", value)

    @property
    def footnotes(self) -> dict:
        return self._json_prop("footnotes_json")

    @footnotes.setter
    def footnotes(self, value: dict):
        self._set_json_prop("footnotes_json", value)

    @property
    def named_ranges(self) -> dict:
        return self._json_prop("named_ranges_json")

    @named_ranges.setter
    def named_ranges(self, value: dict):
        self._set_json_prop("named_ranges_json", value)

    @property
    def positioned_objects(self) -> dict:
        return self._json_prop("positioned_objects_json")

    @positioned_objects.setter
    def positioned_objects(self, value: dict):
        self._set_json_prop("positioned_objects_json", value)

    @property
    def tabs(self) -> list:
        val = self.tabs_json
        return json.loads(val) if val else []

    @tabs.setter
    def tabs(self, value: list):
        self.tabs_json = json.dumps(value)
