"""Permissions API endpoints — document sharing and collaborator management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mock_gdoc.models import Document, Permission, User
from .deps import get_db, resolve_user_id, check_document_access, check_document_owner, VALID_ROLES
from .schemas import (
    PermissionSchema,
    PermissionCreateRequest,
    PermissionUpdateRequest,
    PermissionListResponse,
)

router = APIRouter()


def _permission_to_schema(perm: Permission) -> PermissionSchema:
    return PermissionSchema(
        id=perm.id,
        documentId=perm.document_id,
        type=perm.type,
        role=perm.role,
        emailAddress=perm.email_address,
        displayName=perm.display_name,
        createdTime=perm.created_time.isoformat() if perm.created_time else None,
    )


@router.get("/documents/{documentId}/permissions", tags=["permissions"])
def list_permissions(
    documentId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """List all permissions on a document."""
    doc = check_document_access(db, documentId, user_id)

    # Always include the owner as a synthetic permission
    owner = db.query(User).filter(User.id == doc.user_id).first()
    owner_perm = PermissionSchema(
        id=f"owner_{doc.user_id}",
        documentId=documentId,
        type="user",
        role="owner",
        emailAddress=owner.email if owner else "",
        displayName=owner.display_name if owner else "",
    )

    permissions = (
        db.query(Permission)
        .filter(Permission.document_id == documentId)
        .order_by(Permission.created_time.asc())
        .all()
    )
    perm_list = [owner_perm] + [_permission_to_schema(p) for p in permissions]
    return PermissionListResponse(
        permissions=perm_list,
        count=len(perm_list),
    )


@router.post("/documents/{documentId}/permissions", tags=["permissions"])
def create_permission(
    documentId: str,
    request: PermissionCreateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Share a document / add a collaborator."""
    doc = check_document_owner(db, documentId, user_id)

    if request.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role '{request.role}'. Must be one of: {', '.join(VALID_ROLES)}")
    if request.role == "owner":
        raise HTTPException(400, "Cannot grant owner role via permissions. Use transfer ownership instead.")

    # Resolve the target user by email
    target_user = None
    if request.type == "user":
        if not request.emailAddress:
            raise HTTPException(400, "emailAddress is required for type 'user'")
        target_user = db.query(User).filter(User.email == request.emailAddress).first()
        if not target_user:
            raise HTTPException(404, f"User with email '{request.emailAddress}' not found")
        if target_user.id == doc.user_id:
            raise HTTPException(400, "Cannot create permission for the document owner")

        # Check if permission already exists
        existing = db.query(Permission).filter(
            Permission.document_id == documentId,
            Permission.user_id == target_user.id,
        ).first()
        if existing:
            raise HTTPException(409, f"Permission already exists for this user. Use PATCH to update role.")

    perm_id = f"perm_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    perm = Permission(
        id=perm_id,
        document_id=documentId,
        type=request.type,
        role=request.role,
        email_address=request.emailAddress,
        user_id=target_user.id if target_user else None,
        display_name=target_user.display_name if target_user else request.emailAddress,
        created_time=now,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return _permission_to_schema(perm)


@router.patch("/documents/{documentId}/permissions/{permissionId}", tags=["permissions"])
def update_permission(
    documentId: str,
    permissionId: str,
    request: PermissionUpdateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Update a permission's role."""
    check_document_owner(db, documentId, user_id)

    perm = db.query(Permission).filter(
        Permission.id == permissionId,
        Permission.document_id == documentId,
    ).first()
    if not perm:
        raise HTTPException(404, f"Permission '{permissionId}' not found")

    if request.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role '{request.role}'. Must be one of: {', '.join(VALID_ROLES)}")
    if request.role == "owner":
        raise HTTPException(400, "Cannot grant owner role via permissions")

    perm.role = request.role
    db.commit()
    db.refresh(perm)
    return _permission_to_schema(perm)


@router.delete("/documents/{documentId}/permissions/{permissionId}", tags=["permissions"])
def delete_permission(
    documentId: str,
    permissionId: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(resolve_user_id),
):
    """Remove a permission / unshare."""
    check_document_owner(db, documentId, user_id)

    perm = db.query(Permission).filter(
        Permission.id == permissionId,
        Permission.document_id == documentId,
    ).first()
    if not perm:
        raise HTTPException(404, f"Permission '{permissionId}' not found")

    db.delete(perm)
    db.commit()
    return {"status": "ok"}
