"""Replies API endpoints — Drive API v3."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from mock_gdrive.models import File, Comment, Reply, User
from .deps import get_db, resolve_user
from .schemas import ReplyResource, ReplyList, UserInfo
from .capabilities import user_can_view, get_effective_role
from .fields import parse_fields, filter_response

router = APIRouter()


def _ts(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _reply_to_resource(r: Reply, current_user: User) -> ReplyResource:
    author = UserInfo(
        displayName=r.author.display_name,
        emailAddress=r.author.email,
        me=r.author.id == current_user.id,
        permissionId=r.author.id,
    ) if r.author else None

    return ReplyResource(
        id=r.id,
        author=author,
        content=r.content if not r.deleted else "",
        htmlContent=r.html_content if not r.deleted else None,
        createdTime=_ts(r.created_time),
        modifiedTime=_ts(r.modified_time),
        deleted=r.deleted,
        action=r.action,
    )


def _apply_fields(data: dict, fields: str | None) -> dict:
    if not fields:
        return data
    spec = parse_fields(fields)
    if not spec:
        return data
    return filter_response(data, spec)


def _get_comment_or_404(db: Session, file_id: str, comment_id: str) -> Comment:
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        raise HTTPException(404, f"File not found: {file_id}")
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.file_id == file_id,
    ).first()
    if not comment:
        raise HTTPException(404, f"Comment not found: {comment_id}")
    return comment


# --- replies.list ---
@router.get("/drive/v3/files/{fileId}/comments/{commentId}/replies", tags=["replies"])
def list_replies(
    fileId: str,
    commentId: str,
    pageSize: int = Query(default=20, ge=1, le=100),
    pageToken: str | None = None,
    includeDeleted: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    comment = _get_comment_or_404(db, fileId, commentId)

    file = db.query(File).filter(File.id == fileId).first()
    if not user_can_view(file, current_user, db):
        raise HTTPException(403, "Insufficient permissions.")

    query = db.query(Reply).filter(Reply.comment_id == commentId)
    if not includeDeleted:
        query = query.filter(Reply.deleted == False)
    query = query.order_by(Reply.created_time.asc())

    offset = 0
    if pageToken:
        try:
            offset = int(pageToken)
        except ValueError:
            pass

    total = query.count()
    replies = query.offset(offset).limit(pageSize).all()

    next_token = None
    if offset + pageSize < total:
        next_token = str(offset + pageSize)

    resources = [_reply_to_resource(r, current_user) for r in replies]
    result = ReplyList(
        replies=resources,
        nextPageToken=next_token,
    ).model_dump(exclude_none=True)

    return _apply_fields(result, fields)


# --- replies.get ---
@router.get("/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}", tags=["replies"])
def get_reply(
    fileId: str,
    commentId: str,
    replyId: str,
    includeDeleted: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    comment = _get_comment_or_404(db, fileId, commentId)

    reply = db.query(Reply).filter(
        Reply.id == replyId,
        Reply.comment_id == commentId,
    ).first()
    if not reply:
        raise HTTPException(404, f"Reply not found: {replyId}")
    if reply.deleted and not includeDeleted:
        raise HTTPException(404, f"Reply not found: {replyId}")

    result = _reply_to_resource(reply, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- replies.create ---
@router.post("/drive/v3/files/{fileId}/comments/{commentId}/replies", tags=["replies"])
async def create_reply(
    fileId: str,
    commentId: str,
    request: Request,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    comment = _get_comment_or_404(db, fileId, commentId)

    file = db.query(File).filter(File.id == fileId).first()
    role = get_effective_role(file, current_user, db)
    if role is None:
        raise HTTPException(403, "Insufficient permissions.")

    from mock_gdrive.api.capabilities import _ROLE_RANK
    if _ROLE_RANK.get(role, -1) < _ROLE_RANK["commenter"]:
        raise HTTPException(403, "User does not have comment permission on this file.")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON body")

    now = datetime.now(timezone.utc)
    action = data.get("action")

    reply = Reply(
        id=uuid.uuid4().hex,
        comment_id=commentId,
        author_id=current_user.id,
        content=data.get("content", ""),
        html_content=data.get("htmlContent"),
        created_time=now,
        modified_time=now,
        action=action,
    )
    db.add(reply)

    # Handle resolve/reopen actions
    if action == "resolve":
        comment.resolved = True
    elif action == "reopen":
        comment.resolved = False

    db.commit()
    db.refresh(reply)

    result = _reply_to_resource(reply, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- replies.update ---
@router.patch("/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}", tags=["replies"])
async def update_reply(
    fileId: str,
    commentId: str,
    replyId: str,
    request: Request,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    _get_comment_or_404(db, fileId, commentId)

    reply = db.query(Reply).filter(
        Reply.id == replyId,
        Reply.comment_id == commentId,
    ).first()
    if not reply:
        raise HTTPException(404, f"Reply not found: {replyId}")
    if reply.author_id != current_user.id:
        raise HTTPException(403, "Only the reply author can modify it.")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON body")

    if "content" in data:
        reply.content = data["content"]
    reply.modified_time = datetime.now(timezone.utc)

    db.commit()
    db.refresh(reply)

    result = _reply_to_resource(reply, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- replies.delete ---
@router.delete("/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}", tags=["replies"])
def delete_reply(
    fileId: str,
    commentId: str,
    replyId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    _get_comment_or_404(db, fileId, commentId)

    reply = db.query(Reply).filter(
        Reply.id == replyId,
        Reply.comment_id == commentId,
    ).first()
    if not reply:
        raise HTTPException(404, f"Reply not found: {replyId}")
    if reply.author_id != current_user.id:
        raise HTTPException(403, "Only the reply author can delete it.")

    reply.deleted = True
    reply.content = ""
    db.commit()
    return Response(status_code=204)
