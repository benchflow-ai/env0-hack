"""Web UI routes — Google Drive-like interface using Jinja2 + Tailwind."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from sqlalchemy import func

from mock_gdrive.models import User, File, Permission
from mock_gdrive.models.comment import Comment
from mock_gdrive.models.revision import Revision
from mock_gdrive.api.deps import get_db
from mock_gdrive.api.capabilities import get_effective_role, compute_capabilities
from mock_gdrive.state.action_log import action_log
from mock_gdrive.state.snapshots import get_diff

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _get_current_user(db: Session, request: Request) -> User | None:
    email = request.cookies.get("mock_gdrive_user", "")
    if email:
        user = db.query(User).filter(User.email == email).first()
        if user:
            return user
    return db.query(User).first()


def _breadcrumb(db: Session, folder_id: str | None) -> list[dict]:
    """Build breadcrumb trail from folder up to root."""
    crumbs = []
    current_id = folder_id
    while current_id:
        folder = db.query(File).filter(File.id == current_id).first()
        if not folder:
            break
        crumbs.append({"id": folder.id, "name": folder.name})
        current_id = folder.parent_id
    crumbs.reverse()
    return crumbs


def _file_icon(mime_type: str) -> dict:
    """Return icon color and label for a mime type."""
    mapping = {
        "application/vnd.google-apps.folder": {"color": "text-gray-500", "bg": "bg-gray-100", "icon": "folder"},
        "application/vnd.google-apps.document": {"color": "text-blue-600", "bg": "bg-blue-50", "icon": "doc"},
        "application/vnd.google-apps.spreadsheet": {"color": "text-green-600", "bg": "bg-green-50", "icon": "sheet"},
        "application/vnd.google-apps.presentation": {"color": "text-yellow-600", "bg": "bg-yellow-50", "icon": "slides"},
        "application/vnd.google-apps.shortcut": {"color": "text-gray-400", "bg": "bg-gray-50", "icon": "shortcut"},
        "application/pdf": {"color": "text-red-600", "bg": "bg-red-50", "icon": "pdf"},
        "image/png": {"color": "text-purple-600", "bg": "bg-purple-50", "icon": "image"},
        "image/jpeg": {"color": "text-purple-600", "bg": "bg-purple-50", "icon": "image"},
        "text/csv": {"color": "text-green-600", "bg": "bg-green-50", "icon": "csv"},
    }
    return mapping.get(mime_type, {"color": "text-gray-500", "bg": "bg-gray-50", "icon": "file"})


_FRIENDLY_TYPES = {
    "application/vnd.google-apps.folder": "Google Drive Folder",
    "application/vnd.google-apps.document": "Google Docs",
    "application/vnd.google-apps.spreadsheet": "Google Sheets",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.form": "Google Forms",
    "application/vnd.google-apps.shortcut": "Shortcut",
    "application/pdf": "PDF",
    "image/png": "PNG image",
    "image/jpeg": "JPEG image",
    "text/csv": "CSV file",
    "text/plain": "Plain text",
    "application/zip": "ZIP archive",
}


def _friendly_type(mime_type: str) -> str:
    return _FRIENDLY_TYPES.get(mime_type, mime_type)


def _format_size(size: int | None) -> str:
    if not size:
        return "-"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _base_context(db: Session, request: Request) -> dict:
    user = _get_current_user(db, request)
    all_users = db.query(User).order_by(User.display_name).all()
    total_files = db.query(File).filter(File.owner_id == user.id).count() if user else 0
    total_shared = 0
    trash_count = 0
    storage_used = 0
    storage_limit = 15_000_000_000
    if user:
        total_shared = db.query(Permission).filter(
            Permission.email_address == user.email,
        ).join(File).filter(File.owner_id != user.id).count()
        trash_count = db.query(File).filter(File.owner_id == user.id, File.trashed == True).count()
        storage_used = db.query(func.coalesce(func.sum(File.size), 0)).filter(File.owner_id == user.id).scalar()
        storage_limit = user.storage_quota_limit or storage_limit
    return {
        "user": user,
        "all_users": all_users,
        "view": "dev",
        "folder_id": None,
        "search_query": "",
        "total_files": total_files,
        "total_shared": total_shared,
        "trash_count": trash_count,
        "storage_used": storage_used,
        "storage_limit": storage_limit,
    }


def _diff_summary() -> dict[str, int]:
    diff = get_diff()
    files = diff.get("files", {})
    permissions = diff.get("permissions", {})
    return {
        "files_added": len(files.get("added", [])),
        "files_updated": len(files.get("updated", [])),
        "files_deleted": len(files.get("deleted", [])),
        "permissions_added": len(permissions.get("added", [])),
        "permissions_updated": len(permissions.get("updated", [])),
        "permissions_deleted": len(permissions.get("deleted", [])),
    }


@router.get("/", response_class=HTMLResponse)
def drive_home(
    request: Request,
    folder: str | None = None,
    q: str = "",
    view: str = "my-drive",
    db: Session = Depends(get_db),
):
    user = _get_current_user(db, request)
    if not user:
        return HTMLResponse("<h1>No users. Run <code>mock-gdrive seed</code></h1>")

    all_users = db.query(User).all()

    query = db.query(File)

    if view == "trash":
        query = query.filter(File.owner_id == user.id, File.trashed == True)
    elif view == "starred":
        query = query.filter(File.owner_id == user.id, File.starred == True, File.trashed == False)
    elif view == "recent":
        # Recent: files owned by or shared with user, sorted by modified_time
        query = query.filter(File.owner_id == user.id, File.trashed == False)
    elif view == "shared":
        # Files shared with me (not owned by me)
        shared_ids = (
            db.query(Permission.file_id)
            .filter(Permission.email_address == user.email)
            .scalar_subquery()
        )
        query = query.filter(
            File.id.in_(shared_ids),
            File.owner_id != user.id,
            File.trashed == False,
        )
    else:
        # My Drive: browse by folder
        query = query.filter(File.owner_id == user.id, File.trashed == False)
        if folder:
            query = query.filter(File.parent_id == folder)
        else:
            query = query.filter(File.parent_id == None)

    # Search
    if q:
        query = query.filter(
            File.name.ilike(f"%{q}%")
            | File.content_text.ilike(f"%{q}%")
        )

    # Sort: folders first, then by name
    files = query.order_by(
        File.mime_type.desc(),  # folders (application/vnd...) sort first
        File.modified_time.desc(),
    ).limit(200).all()

    # Enrich with icon info
    file_list = []
    for f in files:
        icon = _file_icon(f.mime_type)
        perm_count = db.query(Permission).filter(Permission.file_id == f.id).count()
        file_list.append({
            "id": f.id,
            "name": f.name,
            "mime_type": f.mime_type,
            "is_folder": f.is_folder,
            "is_shortcut": f.is_shortcut,
            "owner": f.owner,
            "modified_time": f.modified_time,
            "size": f.size,
            "size_fmt": _format_size(f.size) if not f.is_google_type else "-",
            "starred": f.starred,
            "trashed": f.trashed,
            "icon": icon,
            "perm_count": perm_count,
            "parent_id": f.parent_id,
        })

    breadcrumbs = _breadcrumb(db, folder) if folder else []

    # Stats
    total_files = db.query(File).filter(File.owner_id == user.id).count()
    total_shared = db.query(Permission).filter(
        Permission.email_address == user.email,
    ).join(File).filter(File.owner_id != user.id).count()
    trash_count = db.query(File).filter(File.owner_id == user.id, File.trashed == True).count()
    storage_used = db.query(func.coalesce(func.sum(File.size), 0)).filter(File.owner_id == user.id).scalar()
    storage_limit = user.storage_quota_limit if hasattr(user, 'storage_quota_limit') and user.storage_quota_limit else 15_000_000_000

    return templates.TemplateResponse(request, "drive.html", context={
        "user": user,
        "all_users": all_users,
        "files": file_list,
        "folder_id": folder,
        "breadcrumbs": breadcrumbs,
        "search_query": q,
        "view": view,
        "total_files": total_files,
        "total_shared": total_shared,
        "trash_count": trash_count,
        "storage_used": storage_used,
        "storage_limit": storage_limit,
    })


@router.get("/dev/dashboard", response_class=HTMLResponse)
def dev_dashboard(request: Request, db: Session = Depends(get_db)):
    context = _base_context(db, request)
    mime_rows = (
        db.query(File.mime_type, func.count(File.id))
        .group_by(File.mime_type)
        .order_by(func.count(File.id).desc())
        .limit(8)
        .all()
    )
    context.update({
        "file_count": db.query(File).count(),
        "folder_count": db.query(File).filter(File.mime_type == "application/vnd.google-apps.folder").count(),
        "trashed_count": db.query(File).filter(File.trashed == True).count(),
        "permission_count": db.query(Permission).count(),
        "comment_count": db.query(Comment).filter(Comment.deleted == False).count(),
        "revision_count": db.query(Revision).count(),
        "mime_rows": [(mime_type, count) for mime_type, count in mime_rows],
        "recent_actions": action_log.get_entries()[-12:],
        "diff_summary": _diff_summary(),
    })
    return templates.TemplateResponse(request, "dev_dashboard.html", context)


@router.get("/dev/db-viewer", response_class=HTMLResponse)
def dev_db_viewer(
    request: Request,
    table: str = Query("files", alias="table"),
    page: int = Query(1, alias="page"),
    db: Session = Depends(get_db),
):
    context = _base_context(db, request)
    per_page = 25
    page = max(page, 1)
    offset = (page - 1) * per_page
    rows = []
    columns = []
    total = 0
    tables = ["files", "permissions", "comments", "revisions", "users"]

    if table == "permissions":
        columns = ["id", "file_id", "type", "role", "email_address", "domain", "inherited", "deleted"]
        total = db.query(Permission).count()
        items = db.query(Permission).order_by(Permission.file_id, Permission.id).offset(offset).limit(per_page).all()
        rows = [{
            "id": p.id,
            "file_id": p.file_id,
            "type": p.type,
            "role": p.role,
            "email_address": p.email_address or "",
            "domain": p.domain or "",
            "inherited": p.inherited,
            "deleted": p.deleted,
        } for p in items]
    elif table == "comments":
        columns = ["id", "file_id", "author", "content", "created_time", "deleted"]
        total = db.query(Comment).count()
        items = db.query(Comment).order_by(Comment.created_time.desc()).offset(offset).limit(per_page).all()
        rows = [{
            "id": c.id,
            "file_id": c.file_id,
            "author": c.author.display_name if c.author else "",
            "content": (c.content or "")[:120],
            "created_time": c.created_time.strftime("%Y-%m-%d %H:%M") if c.created_time else "",
            "deleted": c.deleted,
        } for c in items]
    elif table == "revisions":
        columns = ["id", "file_id", "modified_time", "size", "keep_forever", "published"]
        total = db.query(Revision).count()
        items = db.query(Revision).order_by(Revision.modified_time.desc()).offset(offset).limit(per_page).all()
        rows = [{
            "id": r.id,
            "file_id": r.file_id,
            "modified_time": r.modified_time.strftime("%Y-%m-%d %H:%M") if r.modified_time else "",
            "size": r.size,
            "keep_forever": r.keep_forever,
            "published": r.published,
        } for r in items]
    elif table == "users":
        columns = ["id", "email", "display_name", "storage_used", "storage_quota_limit"]
        total = db.query(User).count()
        items = db.query(User).order_by(User.email).offset(offset).limit(per_page).all()
        rows = [{
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "storage_used": u.storage_used,
            "storage_quota_limit": u.storage_quota_limit,
        } for u in items]
    else:
        table = "files"
        columns = ["id", "name", "mime_type", "owner", "parent_id", "modified_time", "trashed", "starred", "size"]
        total = db.query(File).count()
        items = db.query(File).order_by(File.modified_time.desc()).offset(offset).limit(per_page).all()
        rows = [{
            "id": f.id,
            "name": f.name,
            "mime_type": f.mime_type,
            "owner": f.owner.email if f.owner else "",
            "parent_id": f.parent_id or "",
            "modified_time": f.modified_time.strftime("%Y-%m-%d %H:%M") if f.modified_time else "",
            "trashed": f.trashed,
            "starred": f.starred,
            "size": f.size,
        } for f in items]

    context.update({
        "table": table,
        "tables": tables,
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    })
    return templates.TemplateResponse(request, "db_viewer.html", context)


@router.get("/dev/api-explorer", response_class=HTMLResponse)
def dev_api_explorer(request: Request, db: Session = Depends(get_db)):
    context = _base_context(db, request)
    sample_file = db.query(File).order_by(File.modified_time.desc()).first()
    sample_folder = db.query(File).filter(File.mime_type == "application/vnd.google-apps.folder").first()
    sample_permission = db.query(Permission).first()
    context.update({
        "sample_file_id": sample_file.id if sample_file else "file123",
        "sample_folder_id": sample_folder.id if sample_folder else "folder123",
        "sample_permission_id": sample_permission.id if sample_permission else "perm123",
        "endpoints": [
            ("List files", "GET", "/drive/v3/files"),
            ("Get file", "GET", f"/drive/v3/files/{sample_file.id if sample_file else 'file123'}"),
            ("Create folder", "POST", "/drive/v3/files"),
            ("Update metadata", "PATCH", f"/drive/v3/files/{sample_file.id if sample_file else 'file123'}"),
            ("List permissions", "GET", f"/drive/v3/files/{sample_file.id if sample_file else 'file123'}/permissions"),
            ("Create permission", "POST", f"/drive/v3/files/{sample_file.id if sample_file else 'file123'}/permissions"),
            ("List changes", "GET", "/drive/v3/changes"),
            ("About", "GET", "/drive/v3/about?fields=*"),
        ],
    })
    return templates.TemplateResponse(request, "api_explorer.html", context)


@router.get("/file/{file_id}", response_class=HTMLResponse)
def file_detail(
    request: Request,
    file_id: str,
    db: Session = Depends(get_db),
):
    user = _get_current_user(db, request)
    if not user:
        return HTMLResponse("<h1>No users</h1>")

    file = db.query(File).filter(File.id == file_id).first()
    if not file:
        return HTMLResponse("<h1>File not found</h1>", status_code=404)

    all_users = db.query(User).all()
    role = get_effective_role(file, user, db)
    caps = compute_capabilities(file, user, role)
    permissions = db.query(Permission).filter(Permission.file_id == file_id).all()
    icon = _file_icon(file.mime_type)
    breadcrumbs = _breadcrumb(db, file.parent_id)

    # Content preview
    content_preview = None
    if file.content_text:
        content_preview = file.content_text[:2000]

    # Activity data
    comments = db.query(Comment).filter(Comment.file_id == file_id, Comment.deleted == False).order_by(Comment.created_time.desc()).all()
    revisions = db.query(Revision).filter(Revision.file_id == file_id).order_by(Revision.modified_time.desc()).all()

    # Stats for base template sidebar
    total_files = db.query(File).filter(File.owner_id == user.id).count()
    total_shared = db.query(Permission).filter(
        Permission.email_address == user.email,
    ).join(File).filter(File.owner_id != user.id).count()
    trash_count = db.query(File).filter(File.owner_id == user.id, File.trashed == True).count()
    storage_used = db.query(func.coalesce(func.sum(File.size), 0)).filter(File.owner_id == user.id).scalar()
    storage_limit = user.storage_quota_limit if hasattr(user, 'storage_quota_limit') and user.storage_quota_limit else 15_000_000_000

    return templates.TemplateResponse(request, "file_detail.html", context={
        "user": user,
        "all_users": all_users,
        "file": file,
        "role": role,
        "caps": caps,
        "permissions": permissions,
        "icon": icon,
        "breadcrumbs": breadcrumbs,
        "content_preview": content_preview,
        "size_fmt": _format_size(file.size) if not file.is_google_type else "-",
        "friendly_type": _friendly_type(file.mime_type),
        "comments": comments,
        "revisions": revisions,
        "view": "my-drive",
        "folder_id": None,
        "search_query": "",
        "total_files": total_files,
        "total_shared": total_shared,
        "trash_count": trash_count,
        "storage_used": storage_used,
        "storage_limit": storage_limit,
    })


@router.get("/switch-user", response_class=HTMLResponse)
def switch_user(
    request: Request,
    email: str = Query(...),
):
    response = RedirectResponse(request.headers.get("referer", "/"), status_code=303)
    response.set_cookie("mock_gdrive_user", email)
    return response
