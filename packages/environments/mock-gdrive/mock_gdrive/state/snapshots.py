"""State snapshots, reset, and diff functionality."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from mock_gdrive.models import get_session_factory, User, File, Permission

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / ".data" / "snapshots" / "gdrive"


def _serialize_file(f: File) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "mimeType": f.mime_type,
        "parentId": f.parent_id,
        "ownerId": f.owner_id,
        "lastModifyingUserId": f.last_modifying_user_id,
        "createdTime": f.created_time.isoformat() if f.created_time else None,
        "modifiedTime": f.modified_time.isoformat() if f.modified_time else None,
        "viewedByMeTime": f.viewed_by_me_time.isoformat() if f.viewed_by_me_time else None,
        "trashed": f.trashed,
        "starred": f.starred,
        "explicitlyTrashed": f.explicitly_trashed,
        "size": f.size,
        "description": f.description,
        "properties": f.properties,
        "version": f.version,
        "webViewLink": f.web_view_link,
        "writersCanShare": f.writers_can_share,
        "shortcutTargetId": f.shortcut_target_id,
        "shortcutTargetMimeType": f.shortcut_target_mime_type,
        "hasContentText": f.content_text is not None,
        "hasContentBlob": f.content_blob is not None,
    }


def _serialize_permission(p: Permission) -> dict:
    return {
        "id": p.id,
        "fileId": p.file_id,
        "role": p.role,
        "type": p.type,
        "emailAddress": p.email_address,
        "displayName": p.display_name,
        "domain": p.domain,
        "inherited": p.inherited,
        "inheritedFrom": p.inherited_from,
        "expirationTime": p.expiration_time.isoformat() if p.expiration_time else None,
        "pendingOwner": p.pending_owner,
    }


def _serialize_user(db: Session, user: User) -> dict:
    files = db.query(File).filter(File.owner_id == user.id).all()
    # Get all permissions for files this user owns
    file_ids = [f.id for f in files]
    permissions = []
    if file_ids:
        permissions = db.query(Permission).filter(Permission.file_id.in_(file_ids)).all()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "displayName": user.display_name,
            "storageQuotaLimit": user.storage_quota_limit,
            "storageUsed": user.storage_used,
        },
        "files": [_serialize_file(f) for f in files],
        "permissions": [_serialize_permission(p) for p in permissions],
    }


def get_state_dump() -> dict:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        users = db.query(User).all()
        # Dump ALL files and permissions, not just per-owner
        all_files = db.query(File).all()
        all_permissions = db.query(Permission).all()
        return {
            "users": {u.id: {
                "user": {
                    "id": u.id,
                    "email": u.email,
                    "displayName": u.display_name,
                    "storageQuotaLimit": u.storage_quota_limit,
                    "storageUsed": u.storage_used,
                },
            } for u in users},
            "files": [_serialize_file(f) for f in all_files],
            "permissions": [_serialize_permission(p) for p in all_permissions],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        db.close()


def take_snapshot(name: str) -> Path:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    state = get_state_dump()
    path = SNAPSHOTS_DIR / f"{name}.json"
    path.write_text(json.dumps(state, indent=2))
    return path


def restore_snapshot(name: str) -> bool:
    path = SNAPSHOTS_DIR / f"{name}.json"
    if not path.exists():
        return False
    state = json.loads(path.read_text())
    _restore_from_state(state)
    return True


def _restore_from_state(state: dict):
    from mock_gdrive.models import Base, get_engine
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Restore users
        for user_id, user_data in state.get("users", {}).items():
            u = user_data["user"]
            db.add(User(
                id=u["id"],
                email=u["email"],
                display_name=u.get("displayName", ""),
                storage_quota_limit=u.get("storageQuotaLimit", 15_000_000_000),
                storage_used=u.get("storageUsed", 0),
            ))

        db.flush()

        # Restore files (parent_id FK requires ordering — insert folders first, then children)
        # Simple approach: insert all with parent_id=NULL, then update parent_id
        files_data = state.get("files", [])
        for f in files_data:
            created = None
            if f.get("createdTime"):
                try:
                    created = datetime.fromisoformat(f["createdTime"])
                except (ValueError, TypeError):
                    created = datetime.now(timezone.utc)

            modified = None
            if f.get("modifiedTime"):
                try:
                    modified = datetime.fromisoformat(f["modifiedTime"])
                except (ValueError, TypeError):
                    modified = datetime.now(timezone.utc)

            viewed = None
            if f.get("viewedByMeTime"):
                try:
                    viewed = datetime.fromisoformat(f["viewedByMeTime"])
                except (ValueError, TypeError):
                    pass

            db.add(File(
                id=f["id"],
                name=f["name"],
                mime_type=f["mimeType"],
                parent_id=None,  # set after all files exist
                owner_id=f["ownerId"],
                last_modifying_user_id=f.get("lastModifyingUserId"),
                created_time=created or datetime.now(timezone.utc),
                modified_time=modified or datetime.now(timezone.utc),
                viewed_by_me_time=viewed,
                trashed=f.get("trashed", False),
                starred=f.get("starred", False),
                explicitly_trashed=f.get("explicitlyTrashed", False),
                size=f.get("size", 0),
                description=f.get("description"),
                properties=f.get("properties"),
                version=f.get("version", 1),
                web_view_link=f.get("webViewLink"),
                writers_can_share=f.get("writersCanShare", True),
                shortcut_target_id=f.get("shortcutTargetId"),
                shortcut_target_mime_type=f.get("shortcutTargetMimeType"),
                # content_blob and content_text not stored in snapshots for size
            ))

        db.flush()

        # Now set parent_id references
        for f in files_data:
            if f.get("parentId"):
                db.query(File).filter(File.id == f["id"]).update(
                    {"parent_id": f["parentId"]}, synchronize_session=False
                )

        # Restore permissions
        for p in state.get("permissions", []):
            exp_time = None
            if p.get("expirationTime"):
                try:
                    exp_time = datetime.fromisoformat(p["expirationTime"])
                except (ValueError, TypeError):
                    pass

            db.add(Permission(
                id=p["id"],
                file_id=p["fileId"],
                role=p["role"],
                type=p["type"],
                email_address=p.get("emailAddress"),
                display_name=p.get("displayName"),
                domain=p.get("domain"),
                inherited=p.get("inherited", False),
                inherited_from=p.get("inheritedFrom"),
                expiration_time=exp_time,
                pending_owner=p.get("pendingOwner", False),
            ))

        db.commit()
    finally:
        db.close()


def get_diff(initial_state: dict | None = None) -> dict:
    current = get_state_dump()

    if initial_state is None:
        path = SNAPSHOTS_DIR / "initial.json"
        if path.exists():
            initial_state = json.loads(path.read_text())
        else:
            return {"error": "No initial snapshot found"}

    diff = {"files": {"added": [], "updated": [], "deleted": []},
            "permissions": {"added": [], "updated": [], "deleted": []}}

    # Diff files
    curr_files = {f["id"]: f for f in current.get("files", [])}
    init_files = {f["id"]: f for f in initial_state.get("files", [])}

    for fid, fdata in curr_files.items():
        if fid not in init_files:
            diff["files"]["added"].append(fdata)
        elif fdata != init_files[fid]:
            changes = {"id": fid}
            for k, v in fdata.items():
                if init_files[fid].get(k) != v:
                    changes[k] = v
            diff["files"]["updated"].append(changes)

    for fid in init_files:
        if fid not in curr_files:
            diff["files"]["deleted"].append({"id": fid})

    # Diff permissions
    curr_perms = {p["id"]: p for p in current.get("permissions", [])}
    init_perms = {p["id"]: p for p in initial_state.get("permissions", [])}

    for pid, pdata in curr_perms.items():
        if pid not in init_perms:
            diff["permissions"]["added"].append(pdata)
        elif pdata != init_perms[pid]:
            changes = {"id": pid}
            for k, v in pdata.items():
                if init_perms[pid].get(k) != v:
                    changes[k] = v
            diff["permissions"]["updated"].append(changes)

    for pid in init_perms:
        if pid not in curr_perms:
            diff["permissions"]["deleted"].append({"id": pid})

    return diff
