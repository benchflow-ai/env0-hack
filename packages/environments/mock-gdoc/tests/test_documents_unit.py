"""Unit tests for document endpoint business logic without HTTP transport."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from mock_gdoc.api.documents import (
    batch_update_document,
    get_document,
)
from mock_gdoc.api.schemas import BatchUpdateDocumentRequest
from mock_gdoc.models import (
    Document,
    DocumentRevision,
    User,
    get_session_factory,
)
from mock_gdoc.seed.body_builder import text_to_body


def _insert_foreign_document():
    """Insert a document owned by an existing seeded user other than user_0."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Grab an existing seeded persona user (user_1 is always present)
        foreign_user = db.get(User, "user_1")
        assert foreign_user is not None, "seeded db must contain user_1"

        doc = Document(
            id="foreign_doc",
            title="Private Doc",
            revision_id="rev0",
            user_id=foreign_user.id,
            created_time=datetime.now(timezone.utc),
            modified_time=datetime.now(timezone.utc),
        )
        doc.body = text_to_body("private")
        db.add(doc)
        db.add(DocumentRevision(
            id="rev_rev0",
            document_id=doc.id,
            user_id=foreign_user.id,
            modified_time=datetime.now(timezone.utc),
        ))
        db.commit()
    finally:
        db.close()


def test_get_document_enforces_user_scope(seeded_db):
    _insert_foreign_document()

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            get_document("foreign_doc", db=db, user_id="user_0")
        assert exc_info.value.status_code == 404
    finally:
        db.close()


def test_batch_update_enforces_user_scope(seeded_db):
    _insert_foreign_document()

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            batch_update_document(
                "foreign_doc",
                BatchUpdateDocumentRequest(
                    requests=[{"insertText": {"location": {"index": 1}, "text": "x"}}]
                ),
                db=db,
                user_id="user_0",
            )
        assert exc_info.value.status_code == 404
    finally:
        db.close()


