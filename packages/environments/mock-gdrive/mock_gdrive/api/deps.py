"""Shared dependencies for API routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from mock_gdrive.models import get_session_factory, User


def get_db() -> Session:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_user(
    x_mock_drive_user: str | None = Header(None, alias="X-Mock-Drive-User"),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the current user from headers.

    Priority:
    1. X-Mock-Drive-User header (by ID or email)
    2. Authorization: Bearer <user_id_or_email>
    3. Fallback to first user in DB
    """
    identifier = None

    if x_mock_drive_user:
        identifier = x_mock_drive_user
    elif authorization and authorization.startswith("Bearer "):
        identifier = authorization[7:].strip()

    if identifier:
        user = db.query(User).filter(
            (User.id == identifier) | (User.email == identifier)
        ).first()
        if user:
            return user
        raise HTTPException(401, f"User {identifier!r} not found")

    # Fallback: first user
    user = db.query(User).first()
    if not user:
        raise HTTPException(404, "No users in database. Run `mock-gdrive seed` first.")
    return user
