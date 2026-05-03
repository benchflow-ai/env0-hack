"""Permissions API endpoints — Drive API v3."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from mock_gdrive.models import File, Permission, User
from .deps import get_db, resolve_user
from .schemas import PermissionResource, PermissionList, PermissionDetailItem
from .capabilities import get_effective_role, compute_capabilities
from .fields import parse_fields, filter_response

router = APIRouter()


def _perm_to_resource(p: Permission, file: File | None = None, db: Session | None = None) -> PermissionResource:
    """Convert Permission ORM to PermissionResource with permissionDetails[]."""
    # Build permissionDetails array (matching real Drive API format)
    details = []

    # Direct permission on this file
    details.append(PermissionDetailItem(
        permissionType="file",
        role=p.role,
        inherited=bool(p.inherited),
        inheritedFrom=p.inherited_from,
    ))

    # If inherited, also check for direct permissions
    if p.inherited and file and db:
        direct = db.query(Permission).filter(
            Permission.file_id == file.id,
            Permission.email_address == p.email_address,
            Permission.inherited == False,
        ).first()
        if direct:
            details.insert(0, PermissionDetailItem(
                permissionType="file",
                role=direct.role,
                inherited=False,
            ))

    return PermissionResource(
        id=p.id,
        type=p.type,
        role=p.role,
        emailAddress=p.email_address,
        displayName=p.display_name,
        domain=p.domain,
        expirationTime=p.expiration_time.isoformat() + "Z" if p.expiration_time else None,
        pendingOwner=p.pending_owner,
        deleted=p.deleted,
        allowFileDiscovery=p.allow_file_discovery,
        view=p.view,
        permissionDetails=details,
    )


def _apply_fields(data: dict, fields: str | None) -> dict:
    if not fields:
        return data
    spec = parse_fields(fields)
    if not spec:
        return data
    return filter_response(data, spec)


def _get_file_or_404(db: Session, file_id: str) -> File:
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        raise HTTPException(404, f"File not found: {file_id}")
    return file


# --- permissions.list ---
@router.get("/drive/v3/files/{fileId}/permissions", tags=["permissions"])
def list_permissions(
    fileId: str,
    pageSize: int = Query(default=100, ge=1, le=100),
    pageToken: str | None = None,
    fields: str | None = None,
    supportsAllDrives: bool = False,
    includePermissionsForView: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)

    role = get_effective_role(file, current_user, db)
    if role is None:
        raise HTTPException(403, "Insufficient permissions.")

    perms = db.query(Permission).filter(Permission.file_id == fileId).all()
    resources = [_perm_to_resource(p, file, db) for p in perms]

    result = PermissionList(permissions=resources).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- permissions.get ---
@router.get("/drive/v3/files/{fileId}/permissions/{permissionId}", tags=["permissions"])
def get_permission(
    fileId: str,
    permissionId: str,
    fields: str | None = None,
    supportsAllDrives: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)

    role = get_effective_role(file, current_user, db)
    if role is None:
        raise HTTPException(403, "Insufficient permissions.")

    perm = db.query(Permission).filter(
        Permission.id == permissionId,
        Permission.file_id == fileId,
    ).first()
    if not perm:
        raise HTTPException(404, f"Permission not found: {permissionId}")

    result = _perm_to_resource(perm, file, db).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- permissions.create ---
@router.post("/drive/v3/files/{fileId}/permissions", tags=["permissions"])
async def create_permission(
    fileId: str,
    request: Request,
    sendNotificationEmail: bool = True,
    transferOwnership: bool = False,
    emailMessage: str | None = None,
    moveToNewOwnersRoot: bool = False,
    fields: str | None = None,
    supportsAllDrives: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)

    role = get_effective_role(file, current_user, db)
    caps = compute_capabilities(file, current_user, role)
    if not caps.get("canShare"):
        raise HTTPException(403, "The user does not have permission to share this file.")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON body")

    perm_role = data.get("role")
    perm_type = data.get("type")
    if not perm_role or not perm_type:
        raise HTTPException(400, "role and type are required")

    valid_roles = {"owner", "organizer", "fileOrganizer", "writer", "commenter", "reader"}
    valid_types = {"user", "group", "domain", "anyone"}
    if perm_role not in valid_roles:
        raise HTTPException(400, f"Invalid role: {perm_role}")
    if perm_type not in valid_types:
        raise HTTPException(400, f"Invalid type: {perm_type}")

    if perm_role == "owner" and not transferOwnership:
        raise HTTPException(400, "transferOwnership must be true to set role=owner")

    new_perm = Permission(
        id=uuid.uuid4().hex,
        file_id=fileId,
        role=perm_role,
        type=perm_type,
        email_address=data.get("emailAddress"),
        display_name=data.get("displayName"),
        domain=data.get("domain"),
        allow_file_discovery=data.get("allowFileDiscovery"),
        view=data.get("view"),
    )
    db.add(new_perm)

    # Transfer ownership: demote current owner to writer
    if perm_role == "owner" and transferOwnership:
        old_owner_perm = db.query(Permission).filter(
            Permission.file_id == fileId,
            Permission.role == "owner",
        ).first()
        if old_owner_perm:
            old_owner_perm.role = "writer"
        file.owner_id = _resolve_user_id_from_email(db, data.get("emailAddress"), current_user)

    db.commit()
    db.refresh(new_perm)

    result = _perm_to_resource(new_perm, file, db).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- permissions.update (PATCH) ---
@router.patch("/drive/v3/files/{fileId}/permissions/{permissionId}", tags=["permissions"])
async def update_permission(
    fileId: str,
    permissionId: str,
    request: Request,
    transferOwnership: bool = False,
    removeExpiration: bool = False,
    fields: str | None = None,
    supportsAllDrives: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)

    role = get_effective_role(file, current_user, db)
    caps = compute_capabilities(file, current_user, role)
    if not caps.get("canShare"):
        raise HTTPException(403, "Insufficient permissions to modify sharing.")

    perm = db.query(Permission).filter(
        Permission.id == permissionId,
        Permission.file_id == fileId,
    ).first()
    if not perm:
        raise HTTPException(404, f"Permission not found: {permissionId}")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON body")

    if "role" in data:
        new_role = data["role"]
        if new_role == "owner" and not transferOwnership:
            raise HTTPException(400, "transferOwnership must be true to set role=owner")
        perm.role = new_role

    if "expirationTime" in data:
        from datetime import datetime
        try:
            perm.expiration_time = datetime.fromisoformat(data["expirationTime"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    if removeExpiration:
        perm.expiration_time = None

    if "view" in data:
        perm.view = data["view"]

    db.commit()
    db.refresh(perm)

    result = _perm_to_resource(perm, file, db).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- permissions.delete ---
@router.delete("/drive/v3/files/{fileId}/permissions/{permissionId}", tags=["permissions"])
def delete_permission(
    fileId: str,
    permissionId: str,
    supportsAllDrives: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)

    role = get_effective_role(file, current_user, db)
    caps = compute_capabilities(file, current_user, role)
    if not caps.get("canShare"):
        raise HTTPException(403, "Insufficient permissions to modify sharing.")

    perm = db.query(Permission).filter(
        Permission.id == permissionId,
        Permission.file_id == fileId,
    ).first()
    if not perm:
        raise HTTPException(404, f"Permission not found: {permissionId}")

    if perm.role == "owner":
        raise HTTPException(400, "Cannot remove the owner permission. Use transferOwnership instead.")

    db.delete(perm)
    db.commit()
    return Response(status_code=204)


def _resolve_user_id_from_email(db: Session, email: str | None, fallback: User) -> str:
    if not email:
        return fallback.id
    user = db.query(User).filter(User.email == email).first()
    return user.id if user else fallback.id
