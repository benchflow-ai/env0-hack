"""Comments API endpoints — Drive API v3."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from mock_gdrive.models import File, Comment, User
from .deps import get_db, resolve_user
from .schemas import CommentResource, CommentList, ReplyResource, UserInfo
from .capabilities import get_effective_role, user_can_view
from .fields import parse_fields, filter_response

router = APIRouter()


def _ts(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _comment_to_resource(c: Comment, current_user: User) -> CommentResource:
    author = UserInfo(
        displayName=c.author.display_name,
        emailAddress=c.author.email,
        me=c.author.id == current_user.id,
        permissionId=c.author.id,
    ) if c.author else None

    quoted = None
    if c.quoted_file_content_value:
        quoted = {
            "mimeType": c.quoted_file_content_mime_type or "text/plain",
            "value": c.quoted_file_content_value,
        }

    replies = []
    for r in c.replies:
        r_author = UserInfo(
            displayName=r.author.display_name,
            emailAddress=r.author.email,
            me=r.author.id == current_user.id,
            permissionId=r.author.id,
        ) if r.author else None

        replies.append(ReplyResource(
            id=r.id,
            author=r_author,
            content=r.content if not r.deleted else "",
            htmlContent=r.html_content if not r.deleted else None,
            createdTime=_ts(r.created_time),
            modifiedTime=_ts(r.modified_time),
            deleted=r.deleted,
            action=r.action,
        ))

    return CommentResource(
        id=c.id,
        author=author,
        content=c.content if not c.deleted else "",
        htmlContent=c.html_content if not c.deleted else None,
        createdTime=_ts(c.created_time),
        modifiedTime=_ts(c.modified_time),
        resolved=c.resolved,
        deleted=c.deleted,
        anchor=c.anchor,
        quotedFileContent=quoted,
        replies=replies,
    )


def _get_file_or_404(db: Session, file_id: str) -> File:
    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        raise HTTPException(404, f"File not found: {file_id}")
    return file


def _apply_fields(data: dict, fields: str | None) -> dict:
    if not fields:
        return data
    spec = parse_fields(fields)
    if not spec:
        return data
    return filter_response(data, spec)


# --- comments.list ---
@router.get("/drive/v3/files/{fileId}/comments", tags=["comments"])
def list_comments(
    fileId: str,
    pageSize: int = Query(default=20, ge=1, le=100),
    pageToken: str | None = None,
    startModifiedTime: str | None = None,
    includeDeleted: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)
    if not user_can_view(file, current_user, db):
        raise HTTPException(403, "Insufficient permissions.")

    query = db.query(Comment).filter(Comment.file_id == fileId)
    if not includeDeleted:
        query = query.filter(Comment.deleted == False)

    if startModifiedTime:
        try:
            dt = datetime.fromisoformat(startModifiedTime.replace("Z", "+00:00"))
            query = query.filter(Comment.modified_time >= dt)
        except ValueError:
            pass

    query = query.order_by(Comment.created_time.asc())

    offset = 0
    if pageToken:
        try:
            offset = int(pageToken)
        except ValueError:
            pass

    total = query.count()
    comments = query.offset(offset).limit(pageSize).all()

    next_token = None
    if offset + pageSize < total:
        next_token = str(offset + pageSize)

    resources = [_comment_to_resource(c, current_user) for c in comments]
    result = CommentList(
        comments=resources,
        nextPageToken=next_token,
    ).model_dump(exclude_none=True)

    return _apply_fields(result, fields)


# --- comments.get ---
@router.get("/drive/v3/files/{fileId}/comments/{commentId}", tags=["comments"])
def get_comment(
    fileId: str,
    commentId: str,
    includeDeleted: bool = False,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)
    if not user_can_view(file, current_user, db):
        raise HTTPException(403, "Insufficient permissions.")

    comment = db.query(Comment).filter(
        Comment.id == commentId,
        Comment.file_id == fileId,
    ).first()
    if not comment:
        raise HTTPException(404, f"Comment not found: {commentId}")
    if comment.deleted and not includeDeleted:
        raise HTTPException(404, f"Comment not found: {commentId}")

    result = _comment_to_resource(comment, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- comments.create ---
@router.post("/drive/v3/files/{fileId}/comments", tags=["comments"])
async def create_comment(
    fileId: str,
    request: Request,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)
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

    content = data.get("content", "")
    now = datetime.now(timezone.utc)

    comment = Comment(
        id=uuid.uuid4().hex,
        file_id=fileId,
        author_id=current_user.id,
        content=content,
        html_content=data.get("htmlContent"),
        created_time=now,
        modified_time=now,
        anchor=data.get("anchor"),
    )

    quoted = data.get("quotedFileContent")
    if quoted:
        comment.quoted_file_content_value = quoted.get("value")
        comment.quoted_file_content_mime_type = quoted.get("mimeType", "text/plain")

    db.add(comment)
    db.commit()
    db.refresh(comment)

    result = _comment_to_resource(comment, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- comments.update ---
@router.patch("/drive/v3/files/{fileId}/comments/{commentId}", tags=["comments"])
async def update_comment(
    fileId: str,
    commentId: str,
    request: Request,
    fields: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)
    comment = db.query(Comment).filter(
        Comment.id == commentId,
        Comment.file_id == fileId,
    ).first()
    if not comment:
        raise HTTPException(404, f"Comment not found: {commentId}")

    # Only author can update their comment
    if comment.author_id != current_user.id:
        raise HTTPException(403, "Only the comment author can modify it.")

    import json
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON body")

    if "content" in data:
        comment.content = data["content"]
    if "resolved" in data:
        comment.resolved = data["resolved"]
    comment.modified_time = datetime.now(timezone.utc)

    db.commit()
    db.refresh(comment)

    result = _comment_to_resource(comment, current_user).model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- comments.delete ---
@router.delete("/drive/v3/files/{fileId}/comments/{commentId}", tags=["comments"])
def delete_comment(
    fileId: str,
    commentId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = _get_file_or_404(db, fileId)
    comment = db.query(Comment).filter(
        Comment.id == commentId,
        Comment.file_id == fileId,
    ).first()
    if not comment:
        raise HTTPException(404, f"Comment not found: {commentId}")

    if comment.author_id != current_user.id:
        raise HTTPException(403, "Only the comment author can delete it.")

    # Drive API marks comments as deleted, doesn't remove them
    comment.deleted = True
    comment.content = ""
    db.commit()
    return Response(status_code=204)
