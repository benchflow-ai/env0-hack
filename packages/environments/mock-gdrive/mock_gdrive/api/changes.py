"""Changes API endpoints — Drive API v3."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from mock_gdrive.models import File, Change, User
from .deps import get_db, resolve_user
from .schemas import (
    ChangeResource, ChangeList, FileResource, StartPageToken, Channel,
)
from .files import _file_to_resource
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


# --- changes.getStartPageToken ---
@router.get("/drive/v3/changes/startPageToken", tags=["changes"])
def get_start_page_token(
    supportsAllDrives: bool = False,
    driveId: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    # Return the current highest change ID + 1
    latest = db.query(Change).order_by(Change.id.desc()).first()
    token = str(latest.id + 1) if latest else "1"
    return StartPageToken(startPageToken=token).model_dump()


# --- changes.list ---
@router.get("/drive/v3/changes", tags=["changes"])
def list_changes(
    pageToken: str = Query(...),
    pageSize: int = Query(default=100, ge=1, le=1000),
    fields: str | None = None,
    spaces: str = "drive",
    includeItemsFromAllDrives: bool = False,
    supportsAllDrives: bool = False,
    includeRemoved: bool = True,
    includePermissionsForView: str | None = None,
    includeLabels: str | None = None,
    restrictToMyDrive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    try:
        start_id = int(pageToken)
    except ValueError:
        raise HTTPException(400, f"Invalid pageToken: {pageToken}")

    query = db.query(Change).filter(Change.id >= start_id)
    if not includeRemoved:
        query = query.filter(Change.removed == False)
    query = query.order_by(Change.id.asc())

    total = query.count()
    changes = query.limit(pageSize).all()

    change_resources = []
    for c in changes:
        file_resource = None
        if c.file and not c.removed:
            file_resource = _file_to_resource(c.file, current_user, db)

        change_resources.append(ChangeResource(
            changeType=c.change_type,
            time=_ts(c.time),
            fileId=c.file_id,
            file=file_resource,
            removed=c.removed,
        ))

    # Determine next token
    next_token = None
    new_start_token = None
    if changes:
        last_id = changes[-1].id
        if len(changes) >= pageSize:
            next_token = str(last_id + 1)
        else:
            new_start_token = str(last_id + 1)
    else:
        new_start_token = pageToken

    result = ChangeList(
        changes=change_resources,
        nextPageToken=next_token,
        newStartPageToken=new_start_token,
    ).model_dump(exclude_none=True)

    return _apply_fields(result, fields)


# --- changes.watch (stub) ---
@router.post("/drive/v3/changes/watch", tags=["changes"])
def watch_changes(
    pageToken: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    return Channel(
        id=uuid.uuid4().hex,
        resourceId="changes",
        resourceUri="/drive/v3/changes",
        expiration=str(int(datetime.now(timezone.utc).timestamp() * 1000) + 86400000),
    ).model_dump()
