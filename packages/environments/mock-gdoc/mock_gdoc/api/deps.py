"""Shared dependencies for API routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from mock_gdoc.models import get_session_factory, Document, Permission, User


def get_db() -> Session:
    """Yield a DB session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_user_id(
    x_mock_gdoc_user: str | None = Header(None),
    db: Session = Depends(get_db),
) -> str:
    """Resolve the current user.

    Priority: X-Mock-Gdoc-User header -> first user in DB.
    """
    if x_mock_gdoc_user:
        user = db.query(User).filter(
            (User.id == x_mock_gdoc_user) | (User.email == x_mock_gdoc_user)
        ).first()
        if user:
            return user.id

    # Fallback: first user
    user = db.query(User).first()
    if not user:
        raise HTTPException(404, "No users in database. Run `mock-gdoc seed` first.")
    return user.id


# ---------------------------------------------------------------------------
# Shared document access helpers
# ---------------------------------------------------------------------------

VALID_ROLES = {"owner", "writer", "commenter", "reader"}
VALID_ROLES_FOR_COMMENT = {"owner", "writer", "commenter"}


def get_user_permission(db: Session, document_id: str, user_id: str) -> Permission | None:
    """Return the permission record for a user on a document, or None."""
    return db.query(Permission).filter(
        Permission.document_id == document_id,
        Permission.user_id == user_id,
    ).first()


def _get_doc_and_perm(
    db: Session, document_id: str, user_id: str,
) -> tuple[Document, Permission | None]:
    """Load document and user's permission in at most two queries.

    Raises 404 if the document does not exist.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, f"Document '{document_id}' not found")
    perm = None if doc.user_id == user_id else get_user_permission(db, document_id, user_id)
    return doc, perm


def check_document_access(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user has any access (owner or permission).

    Raises 404 if not found or no access.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id or perm:
        return doc
    raise HTTPException(404, f"Document '{document_id}' not found")


def check_document_owner(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user is the owner.

    Raises 403 if the user has access but isn't owner, 404 otherwise.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id:
        return doc
    if perm:
        raise HTTPException(403, "Only the document owner can perform this action")
    raise HTTPException(404, f"Document '{document_id}' not found")


def check_write_access(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user can write (owner or writer role).

    Raises 403 if the user has access but not write permission, 404 otherwise.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id:
        return doc
    if perm and perm.role == "writer":
        return doc
    if perm:
        raise HTTPException(403, "You do not have write access to this document")
    raise HTTPException(404, f"Document '{document_id}' not found")


def check_comment_permission(db: Session, document_id: str, user_id: str) -> Document:
    """Return the document if the user can create/resolve comments.

    Requires owner, writer, or commenter role.
    Raises 403 if access exists but role is insufficient, 404 otherwise.
    """
    doc, perm = _get_doc_and_perm(db, document_id, user_id)
    if doc.user_id == user_id:
        return doc
    if perm and perm.role in VALID_ROLES_FOR_COMMENT:
        return doc
    if perm:
        raise HTTPException(403, "Insufficient permission to comment on this document")
    raise HTTPException(404, f"Document '{document_id}' not found")
