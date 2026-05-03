"""Files API routes — files.* methods."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from mock_slack.models import Channel, SlackFile, SlackUser
from .deps import get_db, resolve_workspace_id
from .schemas import (
    FileSchema,
    FilesListResponse,
    FileInfoResponse,
    FileUploadResponse,
    FileUploadRequest,
    FileDeleteRequest,
)

router = APIRouter()


def _file_to_schema(f: SlackFile) -> FileSchema:
    created_ts = int(f.created_at.timestamp()) if f.created_at else 0
    channels = [f.channel_id] if f.channel_id else []
    return FileSchema(
        id=f.id,
        created=created_ts,
        timestamp=created_ts,
        name=f.name,
        title=f.title,
        mimetype=f.mimetype,
        filetype=f.filetype,
        pretty_type=f.filetype.title() if f.filetype else "",
        user=f.user_id,
        user_team="",
        editable=False,
        size=f.size,
        mode="hosted",
        is_external=False,
        external_type="",
        is_public=f.is_public,
        public_url_shared=False,
        display_as_bot=False,
        username="",
        url_private=f"https://files.slack.com/files-pri/mock/{f.id}/{f.name}",
        url_private_download=f"https://files.slack.com/files-pri/mock/{f.id}/download/{f.name}",
        media_display_type="unknown",
        permalink=f"https://mock.slack.com/files/mock/{f.id}/{f.name}",
        permalink_public=f"https://slack-files.com/mock-{f.id}",
        comments_count=0,
        is_starred=False,
        shares={},
        channels=channels,
        groups=[],
        ims=[],
        has_more_shares=False,
        has_rich_preview=False,
        file_access="visible",
        content=f.content if f.content else None,
    )


def _slack_error(error: str) -> JSONResponse:
    return JSONResponse(content={"ok": False, "error": error})


@router.get("/files.list")
def files_list(
    channel: str | None = Query(None),
    user: str | None = Query(None),
    count: int = Query(100, ge=1, le=1000),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    query = db.query(SlackFile).filter(SlackFile.workspace_id == workspace_id)
    if channel:
        query = query.filter(SlackFile.channel_id == channel)
    if user:
        query = query.filter(SlackFile.user_id == user)

    total = query.count()
    offset = (page - 1) * count
    files = query.order_by(SlackFile.created_at.desc()).offset(offset).limit(count).all()
    pages = max(1, (total + count - 1) // count)

    return FilesListResponse(
        ok=True,
        files=[_file_to_schema(f) for f in files],
        paging={"count": count, "total": total, "page": page, "pages": pages},
    )


@router.get("/files.info")
def files_info(
    file: str = Query(...),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    f = db.query(SlackFile).filter(
        SlackFile.id == file, SlackFile.workspace_id == workspace_id
    ).first()
    if not f:
        return _slack_error("file_not_found")
    return FileInfoResponse(
        ok=True,
        file=_file_to_schema(f),
        comments=[],
        response_metadata={"next_cursor": ""},
    )


@router.post("/files.upload")
def files_upload(
    body: FileUploadRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    # Resolve uploading user
    user = db.query(SlackUser).filter(
        SlackUser.workspace_id == workspace_id, SlackUser.is_bot == False
    ).first()
    if not user:
        return _slack_error("user_not_found")

    # Resolve channel
    channel_id = None
    if body.channels:
        # Take first channel in comma-separated list
        first_channel = body.channels.split(",")[0].strip()
        ch = db.query(Channel).filter(
            Channel.id == first_channel, Channel.workspace_id == workspace_id
        ).first()
        if ch:
            channel_id = ch.id

    file_id = "F" + uuid.uuid4().hex[:8].upper()
    content = body.content
    size = len(content.encode("utf-8")) if content else 0

    # Determine mimetype from filetype
    mimetype_map = {
        "text": "text/plain",
        "python": "text/x-python",
        "javascript": "application/javascript",
        "json": "application/json",
        "html": "text/html",
        "css": "text/css",
        "markdown": "text/markdown",
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "gif": "image/gif",
    }
    filetype = body.filetype or "text"
    mimetype = mimetype_map.get(filetype, "text/plain")

    f = SlackFile(
        id=file_id,
        workspace_id=workspace_id,
        user_id=user.id,
        name=body.filename,
        title=body.title or body.filename,
        mimetype=mimetype,
        filetype=filetype,
        size=size,
        is_public=False,
        channel_id=channel_id,
        created_at=datetime.utcnow(),
        content=content,
    )
    db.add(f)
    db.commit()
    db.refresh(f)

    return FileUploadResponse(ok=True, file=_file_to_schema(f))


@router.post("/files.delete")
def files_delete(
    body: FileDeleteRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(resolve_workspace_id),
):
    f = db.query(SlackFile).filter(
        SlackFile.id == body.file, SlackFile.workspace_id == workspace_id
    ).first()
    if not f:
        return _slack_error("file_not_found")
    db.delete(f)
    db.commit()
    return {"ok": True, "warning": "missing_charset", "response_metadata": {"warnings": ["missing_charset"]}}
