"""Web UI routes — document browser and lightweight dev tools."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from mock_gdoc.api.deps import get_db
from mock_gdoc.models import Comment, Document, DocumentRevision, Reply, User
from mock_gdoc.seed.body_builder import body_to_html, extract_plain_text, html_to_body, text_to_body
from mock_gdoc.state.snapshots import get_diff

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _time_ago(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    # Handle naive datetimes from DB by assuming UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = int((now - dt).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"


def _diff_summary() -> dict[str, int]:
    diff = get_diff()
    summary = {
        "documents_added": 0,
        "documents_updated": 0,
        "documents_deleted": 0,
        "comments_added": 0,
        "comments_updated": 0,
        "comments_deleted": 0,
    }
    for user_data in diff.get("updated", {}).values():
        docs = user_data.get("documents", {})
        comments = user_data.get("comments", {})
        summary["documents_added"] += len(docs.get("added", []))
        summary["documents_updated"] += len(docs.get("updated", []))
        summary["documents_deleted"] += len(docs.get("deleted", []))
        summary["comments_added"] += len(comments.get("added", []))
        summary["comments_updated"] += len(comments.get("updated", []))
        summary["comments_deleted"] += len(comments.get("deleted", []))
    return summary


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

@router.get("/", tags=["web"])
def index(request: Request, db: Session = Depends(get_db)):
    """Document list — Google Drive style."""
    documents = (
        db.query(Document)
        .options(joinedload(Document.user))
        .order_by(Document.modified_time.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(
        request, "doc_list.html", {"documents": documents},
    )


@router.get("/doc/{document_id}", tags=["web"])
def view_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Single document — Google Docs editor view."""
    doc = (
        db.query(Document)
        .options(
            joinedload(Document.user),
            joinedload(Document.comments).joinedload(Comment.author),
            joinedload(Document.comments).joinedload(Comment.replies).joinedload(Reply.author),
        )
        .filter(Document.id == document_id)
        .first()
    )
    if not doc:
        return templates.TemplateResponse(
            request, "doc_list.html", {"documents": []},
        )

    plain_text = extract_plain_text(doc.body)
    paragraphs = [p for p in plain_text.split("\n") if p.strip()]
    html_content = body_to_html(doc.body)

    return templates.TemplateResponse(
        request, "doc_editor.html", {
            "doc": doc,
            "owner": doc.user,
            "modified_ago": _time_ago(doc.modified_time),
            "html_content": html_content,
            "paragraphs": paragraphs,
            "comments": sorted(
                doc.comments,
                key=lambda c: c.created_time,
                reverse=True,
            ),
        },
    )


class _SaveRequest(BaseModel):
    content: str
    format: str = "text"  # "text" or "html"


@router.post("/doc/{document_id}/save", tags=["web"])
def save_document(
    document_id: str,
    body: _SaveRequest,
    db: Session = Depends(get_db),
):
    """Save document content from the web editor."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return JSONResponse(status_code=404, content={"error": "not found"})

    if body.format == "html":
        doc.body = html_to_body(body.content)
    else:
        doc.body = text_to_body(body.content)
    doc.modified_time = datetime.now(timezone.utc)

    new_rev = str(uuid.uuid4()).replace("-", "")[:8]
    doc.revision_id = new_rev
    db.add(DocumentRevision(
        id=f"rev_{new_rev}",
        document_id=document_id,
        user_id=doc.user_id,
        modified_time=doc.modified_time,
    ))

    db.commit()
    return {"status": "ok", "modified_time": doc.modified_time.isoformat()}


# ---------------------------------------------------------------------------
# Dev tools
# ---------------------------------------------------------------------------

@router.get("/dev/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Environment overview and recent activity."""
    return templates.TemplateResponse(
        request, "dashboard.html", {
            "doc_count": db.query(Document).count(),
            "comment_count": db.query(Comment).count(),
            "revision_count": db.query(DocumentRevision).count(),
            "user_count": db.query(User).count(),
            "diff_summary": _diff_summary(),
            "recent_docs": (
                db.query(Document)
                .order_by(Document.modified_time.desc())
                .limit(8)
                .all()
            ),
        },
    )


@router.get("/dev/db-viewer")
def db_viewer(
    request: Request,
    table: str = Query("documents", alias="table"),
    page: int = Query(1, alias="page"),
    db: Session = Depends(get_db),
):
    """Browse core database tables."""
    per_page = 25
    offset = (page - 1) * per_page
    all_tables = ["documents", "comments", "revisions", "users"]
    table = table if table in all_tables else "documents"

    columns: list[str]
    rows: list[dict]
    total: int

    if table == "users":
        columns = ["id", "email", "display_name"]
        total = db.query(User).count()
        users = db.query(User).offset(offset).limit(per_page).all()
        rows = [
            {
                "id": u.id,
                "email": u.email,
                "display_name": u.display_name,
            }
            for u in users
        ]
    elif table == "comments":
        columns = ["id", "document_id", "author_id", "resolved", "content"]
        total = db.query(Comment).count()
        comments = (
            db.query(Comment)
            .order_by(Comment.modified_time.desc())
            .offset(offset).limit(per_page).all()
        )
        rows = [
            {
                "id": c.id, "document_id": c.document_id,
                "author_id": c.author_id, "resolved": c.resolved,
                "content": c.content[:120],
            }
            for c in comments
        ]
    elif table == "revisions":
        columns = ["id", "document_id", "user_id", "modified_time"]
        total = db.query(DocumentRevision).count()
        revisions = (
            db.query(DocumentRevision)
            .order_by(DocumentRevision.modified_time.desc())
            .offset(offset).limit(per_page).all()
        )
        rows = [
            {
                "id": r.id, "document_id": r.document_id,
                "user_id": r.user_id,
                "modified_time": (
                    r.modified_time.strftime("%Y-%m-%d %H:%M")
                    if r.modified_time else "—"
                ),
            }
            for r in revisions
        ]
    else:
        columns = ["id", "title", "revision_id", "modified_time", "snippet"]
        total = db.query(Document).count()
        documents = (
            db.query(Document)
            .order_by(Document.modified_time.desc())
            .offset(offset).limit(per_page).all()
        )
        rows = [
            {
                "id": d.id, "title": d.title,
                "revision_id": d.revision_id,
                "modified_time": (
                    d.modified_time.strftime("%Y-%m-%d %H:%M")
                    if d.modified_time else "—"
                ),
                "snippet": extract_plain_text(
                    d.body
                )[:120].replace("\n", " "),
            }
            for d in documents
        ]

    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        request, "db_viewer.html", {
            "table": table,
            "tables": all_tables,
            "columns": columns,
            "rows": rows,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.get("/dev/api-explorer")
def api_explorer(
    request: Request,
    db: Session = Depends(get_db),
):
    """API reference page."""
    sample_doc = (
        db.query(Document)
        .order_by(Document.modified_time.desc())
        .first()
    )
    sample_doc_id = sample_doc.id if sample_doc else "DOC_ID"

    return templates.TemplateResponse(
        request, "api_explorer.html", {
            "sample_doc_id": sample_doc_id,
        },
    )
