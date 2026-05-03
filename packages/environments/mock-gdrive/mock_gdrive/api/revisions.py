"""Revisions API endpoints — Drive API v3."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from mock_gdrive.models import File, Revision, User
from .deps import get_db, resolve_user
from .schemas import RevisionResource, RevisionList, UserInfo
from .capabilities import user_can_view
from .fields import parse_fields, filter_response

router = APIRouter()


def _ts(dt) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _revision_to_resource(r: Revision, current_user: User) -> RevisionResource:
    last_mod = None
    if r.last_modifying_user:
        last_mod = UserInfo(
            displayName=r.last_modifying_user.display_name,
            emailAddress=r.last_modifying_user.email,
            me=r.last_modifying_user.id == current_user.id,
            permissionId=r.last_modifying_user.id,
        )

    return RevisionResource(
        id=r.id,
        mimeType=r.mime_type,
        modifiedTime=_ts(r.modified_time),
        lastModifyingUser=last_mod,
        size=str(r.size) if r.size else None,
        md5Checksum=r.md5_checksum,
        originalFilename=r.original_filename,
        keepForever=r.keep_forever,
        published=r.published,
        publishAuto=r.publish_auto,
        publishedOutsideDomain=r.published_outside_domain,
        publishedLink=r.published_link,
    )


def _apply_fields(data: dict, fields: str | None) -> dict:
    if not fields:
        return data
    spec = parse_fields(fields)
    if not spec:
        return data
    return filter_response(data, spec)


# --- revisions.list ---
@router.get("/drive/v3/files/{fileId}/revisions", tags=["revisions"])
def list_revisions(
    fileId: str,
    pageSize: int = Query(default=200, ge=1, le=1000),
    pageToken: str | None = None,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")
    if not user_can_view(file, current_user, db):
        raise HTTPException(403, "Insufficient permissions.")

    query = db.query(Revision).filter(Revision.file_id == fileId).order_by(Revision.modified_time.asc())

    offset = 0
    if pageToken:
        try:
            offset = int(pageToken)
        except ValueError:
            pass

    total = query.count()
    revisions = query.offset(offset).limit(pageSize).all()

    next_token = None
    if offset + pageSize < total:
        next_token = str(offset + pageSize)

    resources = [_revision_to_resource(r, current_user) for r in revisions]
    result = RevisionList(
        revisions=resources,
        nextPageToken=next_token,
    ).model_dump(exclude_none=True)

    return _apply_fields(result, fields)


# --- revisions.get ---
@router.get("/drive/v3/files/{fileId}/revisions/{revisionId}", tags=["revisions"])
def get_revision(
    fileId: str,
    revisionId: str,
    acknowledgeAbuse: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")
    if not user_can_view(file, current_user, db):
        raise HTTPException(403, "Insufficient permissions.")

    revision = db.query(Revision).filter(
        Revision.id == revisionId,
        Revision.file_id == fileId,
    ).first()
    if not revision:
        raise HTTPException(404, f"Revision not found: {revisionId}")

    result = _revision_to_resource(revision, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- revisions.update ---
@router.patch("/drive/v3/files/{fileId}/revisions/{revisionId}", tags=["revisions"])
async def update_revision(
    fileId: str,
    revisionId: str,
    request: Request,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")
    if file.owner_id != current_user.id:
        raise HTTPException(403, "Only file owner can modify revisions.")

    revision = db.query(Revision).filter(
        Revision.id == revisionId,
        Revision.file_id == fileId,
    ).first()
    if not revision:
        raise HTTPException(404, f"Revision not found: {revisionId}")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON body")

    if "keepForever" in data:
        revision.keep_forever = data["keepForever"]
    if "published" in data:
        revision.published = data["published"]
    if "publishAuto" in data:
        revision.publish_auto = data["publishAuto"]
    if "publishedOutsideDomain" in data:
        revision.published_outside_domain = data["publishedOutsideDomain"]

    db.commit()
    db.refresh(revision)

    result = _revision_to_resource(revision, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- revisions.delete ---
@router.delete("/drive/v3/files/{fileId}/revisions/{revisionId}", tags=["revisions"])
def delete_revision(
    fileId: str,
    revisionId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")
    if file.owner_id != current_user.id:
        raise HTTPException(403, "Only file owner can delete revisions.")

    revision = db.query(Revision).filter(
        Revision.id == revisionId,
        Revision.file_id == fileId,
    ).first()
    if not revision:
        raise HTTPException(404, f"Revision not found: {revisionId}")

    db.delete(revision)
    db.commit()
    return Response(status_code=204)
