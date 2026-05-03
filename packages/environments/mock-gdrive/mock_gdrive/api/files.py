"""Files API endpoints — Drive API v3."""

from __future__ import annotations

import json as _json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, Form
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from mock_gdrive.models import File, Permission, User, Change
from .deps import get_db, resolve_user
from .schemas import (
    FileResource, FileList, GeneratedIds, Channel, UserInfo, ShortcutDetails,
    LinkShareMetadata, PermissionResource, PermissionDetailItem,
)
from .query_parser import parse_query
from .capabilities import get_effective_role, compute_capabilities, user_can_view
from .fields import parse_fields, filter_response

_log = logging.getLogger(__name__)
_GDOC_MIME = "application/vnd.google-apps.document"

router = APIRouter()


# ---------------------------------------------------------------------------
# HACK/TODO: This back-channel is a temporary workaround for the dual-database
# architecture.  Ideally gdoc should read from gdrive.db directly (or they
# should share a single DB), making this sync unnecessary.  Until that
# refactor happens, we push new doc records from gdrive -> gdoc.db whenever a
# Google-Doc file is created or copied via the Drive API.
# ---------------------------------------------------------------------------

def _sync_to_gdoc(
    file_id: str,
    title: str,
    content_text: str | None,
    owner_id: str,
    owner_email: str,
    owner_display_name: str,
    created_time: datetime,
    modified_time: datetime,
) -> None:
    """Insert a Document record into gdoc.db (best-effort, never raises)."""
    gdoc_db = os.environ.get("GDOC_DB_PATH", "/data/gdoc.db")
    if not os.path.exists(gdoc_db):
        return  # gdoc service not in use for this task

    try:
        from mock_gdoc.seed.body_builder import text_to_body
    except ImportError:
        _log.debug("mock-gdoc not installed; skipping gdoc sync")
        return

    try:
        conn = sqlite3.connect(gdoc_db)
        conn.execute("PRAGMA foreign_keys = OFF")

        # Ensure owner exists
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, display_name) VALUES (?, ?, ?)",
            (owner_id, owner_email, owner_display_name),
        )

        body_json = _json.dumps(text_to_body(content_text or ""))
        rev_id = uuid.uuid4().hex[:8]
        ts = modified_time.isoformat()

        conn.execute(
            "INSERT OR IGNORE INTO documents "
            "(id, title, body_json, document_style_json, named_styles_json, "
            " lists_json, inline_objects_json, headers_json, footers_json, "
            " footnotes_json, named_ranges_json, positioned_objects_json, "
            " tabs_json, revision_id, suggestions_view_mode, user_id, "
            " created_time, modified_time) "
            "VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?)",
            (
                file_id, title, body_json, "{}", "{}",
                "{}", "{}", "{}", "{}",
                "{}", "{}", "{}",
                "[]", rev_id, "DEFAULT_FOR_CURRENT_ACCESS", owner_id,
                created_time.isoformat(), ts,
            ),
        )

        conn.execute(
            "INSERT OR IGNORE INTO document_revisions "
            "(id, document_id, user_id, modified_time) VALUES (?, ?, ?, ?)",
            (f"rev_{rev_id}", file_id, owner_id, ts),
        )

        conn.commit()
        conn.close()
    except Exception:
        _log.warning("gdoc back-channel sync failed", exc_info=True)

# Google Docs export MIME type mappings
_EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": {
        "text/plain": "text/plain",
        "text/html": "text/html",
        "application/pdf": "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "application/vnd.google-apps.spreadsheet": {
        "text/csv": "text/csv",
        "text/tab-separated-values": "text/tab-separated-values",
        "application/pdf": "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "application/vnd.google-apps.presentation": {
        "text/plain": "text/plain",
        "application/pdf": "application/pdf",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
}

def _default_icon_link(mime_type: str) -> str:
    """Return a Drive-style icon link for a MIME type."""
    # Real API returns links like https://drive-thirdparty.googleusercontent.com/16/type/...
    base = "https://drive-thirdparty.googleusercontent.com/16/type"
    return f"{base}/{mime_type}"


# Default fields returned by files.list when no fields parameter is specified
# Real Drive API returns only these minimal fields by default
_DEFAULT_LIST_ITEM_FIELDS = {"kind", "id", "name", "mimeType"}

# Default fields returned by files.get when no fields parameter is specified
# Real Drive API returns a full resource by default for .get
_FULL_RESOURCE = True


def _ts(dt: datetime | None) -> str | None:
    """Format datetime as RFC 3339 with Z suffix, matching real Drive API."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _file_to_resource(file: File, current_user: User, db: Session) -> FileResource:
    """Convert a File ORM model to a full FileResource response."""
    role = get_effective_role(file, current_user, db)
    caps = compute_capabilities(file, current_user, role)

    owners = []
    if file.owner:
        owners = [UserInfo(
            displayName=file.owner.display_name,
            emailAddress=file.owner.email,
            me=file.owner.id == current_user.id,
            permissionId=file.owner.id,
        )]

    last_mod_user = None
    if file.last_modifying_user:
        last_mod_user = UserInfo(
            displayName=file.last_modifying_user.display_name,
            emailAddress=file.last_modifying_user.email,
            me=file.last_modifying_user.id == current_user.id,
            permissionId=file.last_modifying_user.id,
        )

    trashing_user_info = None
    if file.trashing_user:
        trashing_user_info = UserInfo(
            displayName=file.trashing_user.display_name,
            emailAddress=file.trashing_user.email,
            me=file.trashing_user.id == current_user.id,
            permissionId=file.trashing_user.id,
        )

    shortcut = None
    if file.is_shortcut and file.shortcut_target_id:
        shortcut = ShortcutDetails(
            targetId=file.shortcut_target_id,
            targetMimeType=file.shortcut_target_mime_type or "",
        )

    is_shared = len(file.permissions) > 1
    is_owned = file.owner_id == current_user.id

    return FileResource(
        id=file.id,
        name=file.name,
        mimeType=file.mime_type,
        parents=[file.parent_id] if file.parent_id else [],
        starred=file.starred,
        trashed=file.trashed,
        explicitlyTrashed=file.explicitly_trashed,
        createdTime=_ts(file.created_time),
        modifiedTime=_ts(file.modified_time),
        modifiedByMeTime=_ts(file.modified_by_me_time or file.modified_time) if is_owned else None,
        viewedByMeTime=_ts(file.viewed_by_me_time or file.modified_time),
        sharedWithMeTime=_ts(file.shared_with_me_time) if not is_owned and is_shared else None,
        trashedTime=_ts(file.trashed_time) if file.trashed else None,
        size=str(file.size) if not file.is_google_type else None,
        description=file.description,
        properties=file.properties,
        appProperties=file.app_properties,
        version=str(file.version),
        webViewLink=file.web_view_link,
        webContentLink=file.web_content_link,
        iconLink=file.icon_link or _default_icon_link(file.mime_type),
        thumbnailLink=file.thumbnail_link or f"https://lh3.googleusercontent.com/drive-storage/placeholder_{file.id}",
        hasThumbnail=file.has_thumbnail or file.thumbnail_link is not None,
        writersCanShare=file.writers_can_share,
        copyRequiresWriterPermission=file.copy_requires_writer_permission,
        shared=is_shared,
        ownedByMe=is_owned,
        viewedByMe=file.viewed_by_me_time is not None if is_owned else None,
        modifiedByMe=file.modified_by_me_time is not None if is_owned else None,
        owners=owners,
        lastModifyingUser=last_mod_user,
        trashingUser=trashing_user_info,
        shortcutDetails=shortcut,
        capabilities=caps,
        spaces=["drive"],
        folderColorRgb=file.folder_color_rgb,
        originalFilename=file.original_filename,
        fullFileExtension=file.full_file_extension,
        fileExtension=file.file_extension,
        md5Checksum=file.md5_checksum if not file.is_google_type else None,
        sha256Checksum=file.sha256_checksum if not file.is_google_type else None,
        headRevisionId=file.head_revision_id,
        quotaBytesUsed=str(file.size),
        isAppAuthorized=False,
        resourceKey=file.resource_key,
        hasAugmentedPermissions=is_shared,
        permissionIds=[p.id for p in file.permissions] if file.permissions else None,
        linkShareMetadata=LinkShareMetadata(
            securityUpdateEligible=False,
            securityUpdateEnabled=True,
        ),
    )


def _apply_fields(data: dict, fields: str | None) -> dict:
    if not fields:
        return data
    spec = parse_fields(fields)
    if not spec:
        return data
    return filter_response(data, spec)


def _minimize_file_item(item: dict) -> dict:
    """Return only the default fields for a file list item (matching real API)."""
    return {k: v for k, v in item.items() if k in _DEFAULT_LIST_ITEM_FIELDS}


def _record_change(db: Session, file_id: str, removed: bool = False):
    """Record a change entry for evaluation tracking."""
    change = Change(file_id=file_id, removed=removed)
    db.add(change)


# --- files.generateIds (must be before {fileId} routes) ---
@router.get("/drive/v3/files/generateIds", tags=["files"])
def generate_ids(
    count: int = Query(default=10, ge=1, le=1000),
    space: str = "drive",
):
    ids = [uuid.uuid4().hex for _ in range(count)]
    return GeneratedIds(ids=ids, space=space).model_dump()


# --- files.emptyTrash (must be before {fileId} routes) ---
@router.delete("/drive/v3/files/trash", tags=["files"])
def empty_trash(
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    trashed = db.query(File).filter(
        File.owner_id == current_user.id,
        File.trashed == True,
    ).all()
    for f in trashed:
        _record_change(db, f.id, removed=True)
        db.delete(f)
    db.commit()
    return Response(status_code=204)


# --- files.list ---
@router.get("/drive/v3/files", tags=["files"])
def list_files(
    q: str | None = None,
    pageSize: int = Query(default=100, ge=1, le=1000),
    pageToken: str | None = None,
    orderBy: str | None = None,
    fields: str | None = None,
    corpora: str = "user",
    includeItemsFromAllDrives: bool = False,
    supportsAllDrives: bool = False,
    spaces: str = "drive",
    includePermissionsForView: str | None = None,
    includeLabels: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    query = db.query(File)

    # Visibility scoping: user sees files they own or have permission on
    if corpora in ("user", "allDrives"):
        visible_file_ids = (
            db.query(Permission.file_id)
            .filter(Permission.email_address == current_user.email)
            .scalar_subquery()
        )
        query = query.filter(
            (File.owner_id == current_user.id) | File.id.in_(visible_file_ids)
        )

    # Default: exclude trashed unless query explicitly asks for trashed files
    if not q or "trashed" not in q:
        query = query.filter(File.trashed == False)

    # Apply search query
    if q:
        try:
            filter_expr = parse_query(q, current_user.id)
            if filter_expr is not None:
                query = query.filter(filter_expr)
        except Exception:
            raise HTTPException(400, f"Invalid query: {q}")

    # Order
    if orderBy:
        for part in orderBy.split(","):
            part = part.strip()
            desc = False
            if part.endswith(" desc"):
                desc = True
                part = part[:-5].strip()
            col = _ORDER_BY_MAP.get(part)
            if col is not None:
                query = query.order_by(col.desc() if desc else col.asc())
    else:
        query = query.order_by(File.modified_time.desc())

    # Pagination
    offset = 0
    if pageToken:
        try:
            offset = int(pageToken)
        except ValueError:
            pass

    total = query.count()
    files = query.offset(offset).limit(pageSize).all()

    next_token = None
    if offset + pageSize < total:
        next_token = str(offset + pageSize)

    file_resources = [_file_to_resource(f, current_user, db) for f in files]

    # Serialize
    file_dicts = [r.model_dump(exclude_none=True) for r in file_resources]

    # Apply fields parameter
    if fields:
        spec = parse_fields(fields)
        if spec:
            # Check if there's a files() sub-spec
            files_spec = spec.get("files", {})
            other_spec = {k: v for k, v in spec.items() if k != "files"}
            if files_spec:
                file_dicts = [filter_response(f, files_spec) for f in file_dicts]
            result = {"kind": "drive#fileList", "files": file_dicts}
            if next_token:
                result["nextPageToken"] = next_token
            result["incompleteSearch"] = False
            if other_spec:
                result = filter_response(result, {**other_spec, "files": {}})
            return result
    else:
        # No fields specified → return minimal fields per file (matching real API)
        file_dicts = [_minimize_file_item(f) for f in file_dicts]

    result = FileList(
        files=[FileResource(**f) for f in file_dicts],
        nextPageToken=next_token,
    ).model_dump(exclude_none=True)

    return result


# orderBy field mapping
_ORDER_BY_MAP = {
    "name": File.name,
    "name_natural": File.name,  # SQLite doesn't have natural sort; approximate
    "modifiedTime": File.modified_time,
    "modifiedByMeTime": File.modified_by_me_time,
    "createdTime": File.created_time,
    "folder": File.mime_type,
    "quotaBytesUsed": File.size,
    "recency": File.modified_time,  # approximate
    "sharedWithMeTime": File.shared_with_me_time,
    "starred": File.starred,
    "viewedByMeTime": File.viewed_by_me_time,
}


# --- files.get ---
@router.get("/drive/v3/files/{fileId}", tags=["files"])
def get_file(
    fileId: str,
    alt: str | None = None,
    fields: str | None = None,
    acknowledgeAbuse: bool = False,
    supportsAllDrives: bool = False,
    includePermissionsForView: str | None = None,
    includeLabels: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")

    if not user_can_view(file, current_user, db):
        raise HTTPException(403, "The user does not have sufficient permissions for this file.")

    # alt=media: download content
    if alt == "media":
        if file.is_google_type:
            raise HTTPException(403, "Use files.export to download Google Docs editors files.")
        content = file.content_blob or b""
        return Response(
            content=content,
            media_type=file.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{file.name}"'},
        )

    resource = _file_to_resource(file, current_user, db)
    result = resource.model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- files.create ---
@router.post("/drive/v3/files", tags=["files"])
@router.post("/upload/drive/v3/files", tags=["files"])
async def create_file(
    request: Request,
    fields: str | None = None,
    uploadType: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    content_type = request.headers.get("content-type", "")

    metadata = {}
    content_bytes = None

    if "multipart" in content_type:
        form = await request.form()
        # Metadata from form field or JSON part
        if "metadata" in form:
            import json
            metadata = json.loads(await form["metadata"].read())
        # File content
        if "file" in form:
            upload = form["file"]
            content_bytes = await upload.read()
    else:
        body = await request.body()
        if body:
            import json
            try:
                metadata = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                content_bytes = body

    file_id = metadata.get("id") or uuid.uuid4().hex
    name = metadata.get("name", "Untitled")
    mime_type = metadata.get("mimeType", "application/octet-stream")
    parent_id = None
    parents = metadata.get("parents", [])
    if parents:
        parent_id = parents[0]
        # Validate parent exists and is a folder
        parent = db.query(File).filter(File.id == parent_id).first()
        if not parent:
            raise HTTPException(404, f"Parent folder not found: {parent_id}")
        if not parent.is_folder:
            raise HTTPException(400, f"Parent {parent_id} is not a folder")

    now = datetime.now(timezone.utc)

    # Derive file extension from name
    file_ext = None
    full_ext = None
    if "." in name:
        parts = name.rsplit(".", 1)
        file_ext = parts[-1] if len(parts) > 1 else None
        # Full extension: everything after the first dot
        dot_idx = name.index(".")
        full_ext = name[dot_idx + 1:] if dot_idx < len(name) - 1 else None

    new_file = File(
        id=file_id,
        name=name,
        mime_type=mime_type,
        parent_id=parent_id,
        owner_id=current_user.id,
        last_modifying_user_id=current_user.id,
        created_time=now,
        modified_time=now,
        modified_by_me_time=now,
        description=metadata.get("description"),
        properties=metadata.get("properties"),
        app_properties=metadata.get("appProperties"),
        starred=metadata.get("starred", False),
        writers_can_share=metadata.get("writersCanShare", True),
        copy_requires_writer_permission=metadata.get("copyRequiresWriterPermission", False),
        content_blob=content_bytes,
        content_text=metadata.get("contentText"),  # convenience for seeding
        size=len(content_bytes) if content_bytes else 0,
        original_filename=name if content_bytes else None,
        file_extension=file_ext,
        full_file_extension=full_ext,
        folder_color_rgb=metadata.get("folderColorRgb"),
    )

    # Handle shortcuts
    if mime_type == "application/vnd.google-apps.shortcut":
        sd = metadata.get("shortcutDetails", {})
        new_file.shortcut_target_id = sd.get("targetId")
        new_file.shortcut_target_mime_type = sd.get("targetMimeType")

    db.add(new_file)

    # Create owner permission
    owner_perm = Permission(
        id=uuid.uuid4().hex,
        file_id=file_id,
        role="owner",
        type="user",
        email_address=current_user.email,
        display_name=current_user.display_name,
    )
    db.add(owner_perm)

    _record_change(db, file_id)
    db.commit()
    db.refresh(new_file)

    # Back-channel: mirror to gdoc.db so Docs API can serve this document
    if mime_type == _GDOC_MIME:
        _sync_to_gdoc(
            file_id=file_id,
            title=name,
            content_text=new_file.content_text,
            owner_id=current_user.id,
            owner_email=current_user.email,
            owner_display_name=current_user.display_name,
            created_time=now,
            modified_time=now,
        )

    resource = _file_to_resource(new_file, current_user, db)
    result = resource.model_dump(exclude_none=True)
    return JSONResponse(content=_apply_fields(result, fields), status_code=200)


# --- files.patch (update) ---
@router.patch("/drive/v3/files/{fileId}", tags=["files"])
@router.patch("/upload/drive/v3/files/{fileId}", tags=["files"])
async def patch_file(
    fileId: str,
    request: Request,
    addParents: str | None = None,
    removeParents: str | None = None,
    fields: str | None = None,
    supportsAllDrives: bool = False,
    includePermissionsForView: str | None = None,
    includeLabels: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")

    role = get_effective_role(file, current_user, db)
    caps = compute_capabilities(file, current_user, role)
    if not caps.get("canEdit"):
        raise HTTPException(403, "The user does not have sufficient permissions to edit this file.")

    body = await request.body()
    metadata = {}
    if body:
        import json
        try:
            metadata = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    # Update fields
    if "name" in metadata:
        file.name = metadata["name"]
    if "description" in metadata:
        file.description = metadata["description"]
    if "starred" in metadata:
        file.starred = metadata["starred"]
    if "trashed" in metadata:
        new_trashed = metadata["trashed"]
        now = datetime.now(timezone.utc)
        if new_trashed and not file.trashed:
            file.trashed = True
            file.explicitly_trashed = True
            file.trashed_time = now
            file.trashing_user_id = current_user.id
            if file.is_folder:
                _trash_descendants(db, file.id, trash=True)
        elif not new_trashed and file.trashed:
            file.trashed = False
            file.explicitly_trashed = False
            file.trashed_time = None
            file.trashing_user_id = None
            if file.is_folder:
                _trash_descendants(db, file.id, trash=False)
    if "properties" in metadata:
        file.properties = metadata["properties"]
    if "appProperties" in metadata:
        file.app_properties = metadata["appProperties"]
    if "writersCanShare" in metadata:
        file.writers_can_share = metadata["writersCanShare"]
    if "copyRequiresWriterPermission" in metadata:
        file.copy_requires_writer_permission = metadata["copyRequiresWriterPermission"]
    if "mimeType" in metadata:
        file.mime_type = metadata["mimeType"]
    if "contentText" in metadata:
        file.content_text = metadata["contentText"]
    if "folderColorRgb" in metadata:
        file.folder_color_rgb = metadata["folderColorRgb"]

    # Handle parent changes (move)
    if addParents:
        new_parent_id = addParents.split(",")[0].strip()
        parent = db.query(File).filter(File.id == new_parent_id).first()
        if not parent:
            raise HTTPException(404, f"Parent folder not found: {new_parent_id}")
        if not parent.is_folder:
            raise HTTPException(400, f"Parent {new_parent_id} is not a folder")
        file.parent_id = new_parent_id

    if removeParents and not addParents:
        # Removing parent without adding new one → move to root
        file.parent_id = None

    file.modified_time = datetime.now(timezone.utc)
    file.modified_by_me_time = datetime.now(timezone.utc)
    file.last_modifying_user_id = current_user.id
    file.version += 1

    _record_change(db, file.id)
    db.commit()
    db.refresh(file)

    resource = _file_to_resource(file, current_user, db)
    result = resource.model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- files.delete ---
@router.delete("/drive/v3/files/{fileId}", tags=["files"])
def delete_file(
    fileId: str,
    supportsAllDrives: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")

    # Caller must be file owner
    if file.owner_id != current_user.id:
        raise HTTPException(403, "The user does not have sufficient permissions to permanently delete this file.")

    # If folder, recursively delete descendants
    if file.is_folder:
        _delete_descendants(db, file.id)

    _record_change(db, file.id, removed=True)
    db.delete(file)
    db.commit()
    return Response(status_code=204)


# --- files.copy ---
@router.post("/drive/v3/files/{fileId}/copy", tags=["files"])
async def copy_file(
    fileId: str,
    request: Request,
    fields: str | None = None,
    supportsAllDrives: bool = False,
    includePermissionsForView: str | None = None,
    includeLabels: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    source = db.query(File).filter(File.id == fileId).first()
    if not source:
        raise HTTPException(404, f"File not found: {fileId}")
    if not user_can_view(source, current_user, db):
        raise HTTPException(403, "Insufficient permissions.")
    if source.is_folder:
        raise HTTPException(400, "Folders cannot be copied.")

    body = await request.body()
    metadata = {}
    if body:
        import json
        try:
            metadata = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    parent_id = None
    parents = metadata.get("parents", [])
    if parents:
        parent_id = parents[0]
    else:
        parent_id = source.parent_id

    now = datetime.now(timezone.utc)
    new_id = uuid.uuid4().hex
    copy = File(
        id=new_id,
        name=metadata.get("name", f"Copy of {source.name}"),
        mime_type=source.mime_type,
        parent_id=parent_id,
        owner_id=current_user.id,
        last_modifying_user_id=current_user.id,
        created_time=now,
        modified_time=now,
        modified_by_me_time=now,
        content_blob=source.content_blob,
        content_text=source.content_text,
        size=source.size,
        description=metadata.get("description", source.description),
        writers_can_share=source.writers_can_share,
        copy_requires_writer_permission=source.copy_requires_writer_permission,
        original_filename=source.original_filename,
        file_extension=source.file_extension,
        full_file_extension=source.full_file_extension,
    )
    db.add(copy)

    # Owner permission for copy
    db.add(Permission(
        id=uuid.uuid4().hex,
        file_id=new_id,
        role="owner",
        type="user",
        email_address=current_user.email,
        display_name=current_user.display_name,
    ))

    _record_change(db, new_id)
    db.commit()
    db.refresh(copy)

    # Back-channel: mirror to gdoc.db so Docs API can serve the copy
    if source.mime_type == _GDOC_MIME:
        _sync_to_gdoc(
            file_id=new_id,
            title=copy.name,
            content_text=copy.content_text,
            owner_id=current_user.id,
            owner_email=current_user.email,
            owner_display_name=current_user.display_name,
            created_time=now,
            modified_time=now,
        )

    resource = _file_to_resource(copy, current_user, db)
    result = resource.model_dump(exclude_none=True)
    return _apply_fields(result, fields)


# --- files.export ---
@router.get("/drive/v3/files/{fileId}/export", tags=["files"])
def export_file(
    fileId: str,
    mimeType: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(resolve_user),
):
    file = db.query(File).filter(File.id == fileId).first()
    if not file:
        raise HTTPException(404, f"File not found: {fileId}")
    if not user_can_view(file, current_user, db):
        raise HTTPException(403, "Insufficient permissions.")

    allowed = _EXPORT_MIME_MAP.get(file.mime_type)
    if not allowed:
        raise HTTPException(400, f"Export not supported for mimeType: {file.mime_type}")
    if mimeType not in allowed:
        raise HTTPException(400, f"Cannot export {file.mime_type} as {mimeType}")

    # Return content_text as the exported content
    content = file.content_text or ""
    if isinstance(content, str):
        content = content.encode("utf-8")

    return Response(content=content, media_type=mimeType)


# --- files.watch (no-op stub) ---
@router.post("/drive/v3/files/{fileId}/watch", tags=["files"])
def watch_file(fileId: str):
    return Channel(
        id=uuid.uuid4().hex,
        resourceId=fileId,
        resourceUri=f"/drive/v3/files/{fileId}",
        expiration=str(int(datetime.now(timezone.utc).timestamp() * 1000) + 86400000),
    ).model_dump()


# --- Helpers ---
def _trash_descendants(db: Session, folder_id: str, trash: bool):
    """Recursively trash/untrash all descendants of a folder."""
    children = db.query(File).filter(File.parent_id == folder_id).all()
    for child in children:
        child.trashed = trash
        if not trash:
            child.explicitly_trashed = False
            child.trashed_time = None
            child.trashing_user_id = None
        if child.is_folder:
            _trash_descendants(db, child.id, trash)


def _delete_descendants(db: Session, folder_id: str):
    """Recursively delete all descendants of a folder."""
    children = db.query(File).filter(File.parent_id == folder_id).all()
    for child in children:
        if child.is_folder:
            _delete_descendants(db, child.id)
        db.delete(child)
