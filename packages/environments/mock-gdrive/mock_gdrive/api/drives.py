"""Shared Drives API endpoints — Drive API v3."""

from __future__ import annotations

import json as _json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from mock_gdrive.models import User
from mock_gdrive.models.drive import Drive
from .deps import get_db, resolve_user
from .schemas import DriveResource, DriveList
from .fields import parse_fields, filter_response

router = APIRouter()


def _ts(dt) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _apply_fields(data: dict, fields: str | None) -> dict:
    if not fields:
        return data
    spec = parse_fields(fields)
    if not spec:
        return data
    return filter_response(data, spec)


def _drive_capabilities(is_organizer: bool = True) -> dict:
    """Compute capabilities for a shared drive."""
    return {
        "canAddChildren": is_organizer,
        "canChangeCopyRequiresWriterPermissionRestriction": is_organizer,
        "canChangeDomainUsersOnlyRestriction": is_organizer,
        "canChangeDownloadRestriction": is_organizer,
        "canChangeDriveBackground": is_organizer,
        "canChangeDriveMembersOnlyRestriction": is_organizer,
        "canChangeSharingFoldersRequiresOrganizerPermissionRestriction": is_organizer,
        "canComment": True,
        "canCopy": True,
        "canDeleteChildren": is_organizer,
        "canDeleteDrive": is_organizer,
        "canDownload": True,
        "canEdit": True,
        "canListChildren": True,
        "canManageMembers": is_organizer,
        "canReadRevisions": True,
        "canRename": is_organizer,
        "canRenameDrive": is_organizer,
        "canResetDriveRestrictions": is_organizer,
        "canShare": is_organizer,
        "canTrashChildren": is_organizer,
    }


def _drive_to_resource(d: Drive) -> DriveResource:
    restrictions = {
        "adminManagedRestrictions": d.admin_managed_restrictions,
        "copyRequiresWriterPermission": d.copy_requires_writer_permission,
        "domainUsersOnly": d.domain_users_only,
        "driveMembersOnly": d.drive_members_only,
        "sharingFoldersRequiresOrganizerPermission": d.sharing_folders_requires_organizer_permission,
    }

    return DriveResource(
        id=d.id,
        name=d.name,
        createdTime=_ts(d.created_time),
        hidden=d.hidden,
        colorRgb=d.color_rgb,
        themeId=d.theme_id,
        orgUnitId=d.org_unit_id,
        backgroundImageLink=d.background_image_link,
        backgroundImageFile=d.background_image_file,
        capabilities=_drive_capabilities(is_organizer=True),
        restrictions=restrictions,
    )


async def _parse_body(request: Request) -> dict:
    body_bytes = await request.body()
    if not body_bytes:
        return {}
    try:
        return _json.loads(body_bytes)
    except (ValueError, UnicodeDecodeError):
        return {}


# --- drives.create ---
@router.post("/drive/v3/drives", tags=["drives"])
async def create_drive(
    request: Request,
    requestId: str = Query(...),
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    body = await _parse_body(request)
    drive_id = uuid.uuid4().hex[:28]

    d = Drive(
        id=drive_id,
        name=body.get("name", ""),
        color_rgb=body.get("colorRgb"),
        theme_id=body.get("themeId"),
        creator_id=current_user.id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    result = _drive_to_resource(d).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- drives.get ---
@router.get("/drive/v3/drives/{driveId}", tags=["drives"])
def get_drive(
    driveId: str,
    useDomainAdminAccess: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    d = db.query(Drive).filter(Drive.id == driveId).first()
    if not d:
        raise HTTPException(404, f"Shared drive not found: {driveId}")

    result = _drive_to_resource(d).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- drives.list ---
@router.get("/drive/v3/drives", tags=["drives"])
def list_drives(
    pageSize: int = Query(default=10, ge=1, le=100),
    pageToken: str | None = None,
    q: str | None = None,
    useDomainAdminAccess: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    query = db.query(Drive)

    # Simple name-based query support (drives.list q only supports name)
    if q:
        q_stripped = q.strip()
        if "contains" in q_stripped:
            parts = q_stripped.split("contains", 1)
            val = parts[1].strip().strip("'\"")
            query = query.filter(Drive.name.ilike(f"%{val}%"))
        elif "=" in q_stripped:
            parts = q_stripped.split("=", 1)
            val = parts[1].strip().strip("'\"")
            query = query.filter(Drive.name == val)

    # Filter out hidden drives unless admin access
    if not useDomainAdminAccess:
        query = query.filter(Drive.hidden == False)

    query = query.order_by(Drive.created_time.asc())

    # Pagination
    offset = 0
    if pageToken:
        try:
            offset = int(pageToken)
        except ValueError:
            raise HTTPException(400, f"Invalid pageToken: {pageToken}")

    total = query.count()
    drives = query.offset(offset).limit(pageSize).all()

    next_token = None
    if offset + pageSize < total:
        next_token = str(offset + pageSize)

    drive_resources = [_drive_to_resource(d).model_dump(exclude_none=True) for d in drives]

    result = DriveList(
        drives=drive_resources,
        nextPageToken=next_token,
    ).model_dump(exclude_none=True)

    return _apply_fields(result, fields)


# --- drives.update ---
@router.patch("/drive/v3/drives/{driveId}", tags=["drives"])
async def update_drive(
    request: Request,
    driveId: str,
    useDomainAdminAccess: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    d = db.query(Drive).filter(Drive.id == driveId).first()
    if not d:
        raise HTTPException(404, f"Shared drive not found: {driveId}")

    body = await _parse_body(request)

    if "name" in body:
        d.name = body["name"]
    if "colorRgb" in body:
        d.color_rgb = body["colorRgb"]
    if "themeId" in body:
        d.theme_id = body["themeId"]

    if "restrictions" in body:
        r = body["restrictions"]
        if "adminManagedRestrictions" in r:
            d.admin_managed_restrictions = r["adminManagedRestrictions"]
        if "copyRequiresWriterPermission" in r:
            d.copy_requires_writer_permission = r["copyRequiresWriterPermission"]
        if "domainUsersOnly" in r:
            d.domain_users_only = r["domainUsersOnly"]
        if "driveMembersOnly" in r:
            d.drive_members_only = r["driveMembersOnly"]
        if "sharingFoldersRequiresOrganizerPermission" in r:
            d.sharing_folders_requires_organizer_permission = r["sharingFoldersRequiresOrganizerPermission"]

    db.commit()
    db.refresh(d)

    result = _drive_to_resource(d).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- drives.delete ---
@router.delete("/drive/v3/drives/{driveId}", tags=["drives"], status_code=204)
def delete_drive(
    driveId: str,
    allowItemDeletion: bool = False,
    useDomainAdminAccess: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    d = db.query(Drive).filter(Drive.id == driveId).first()
    if not d:
        raise HTTPException(404, f"Shared drive not found: {driveId}")

    db.delete(d)
    db.commit()
    return None


# --- drives.hide ---
@router.post("/drive/v3/drives/{driveId}/hide", tags=["drives"])
def hide_drive(
    driveId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    d = db.query(Drive).filter(Drive.id == driveId).first()
    if not d:
        raise HTTPException(404, f"Shared drive not found: {driveId}")

    d.hidden = True
    db.commit()
    db.refresh(d)

    return _drive_to_resource(d).model_dump(exclude_none=True)


# --- drives.unhide ---
@router.post("/drive/v3/drives/{driveId}/unhide", tags=["drives"])
def unhide_drive(
    driveId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    d = db.query(Drive).filter(Drive.id == driveId).first()
    if not d:
        raise HTTPException(404, f"Shared drive not found: {driveId}")

    d.hidden = False
    db.commit()
    db.refresh(d)

    return _drive_to_resource(d).model_dump(exclude_none=True)
