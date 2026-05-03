"""State snapshots, reset, and diff functionality."""

from __future__ import annotations

import json
from pathlib import Path
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from mock_gdoc.models import (
    get_session_factory,
    User,
    Document,
    DocumentRevision,
    Comment,
    Reply,
    Permission,
)

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / ".data" / "snapshots_gdoc"


def _serialize_documents(db: Session, user_id: str) -> list[dict]:
    """Serialize all documents for a user."""
    documents = db.query(Document).filter(Document.user_id == user_id).all()
    result = []
    for d in documents:
        result.append({
            "id": d.id,
            "title": d.title,
            "body": d.body,
            "documentStyle": d.document_style,
            "namedStyles": d.named_styles,
            "lists": d.lists,
            "inlineObjects": d.inline_objects,
            "headers": d.headers,
            "footers": d.footers,
            "footnotes": d.footnotes,
            "namedRanges": d.named_ranges,
            "positionedObjects": d.positioned_objects,
            "revisionId": d.revision_id,
            "suggestionsViewMode": d.suggestions_view_mode,
            "createdTime": d.created_time.isoformat() if d.created_time else None,
            "modifiedTime": d.modified_time.isoformat() if d.modified_time else None,
        })
    return result


def _serialize_comments(db: Session, document_id: str) -> list[dict]:
    """Serialize all comments for a document."""
    comments = db.query(Comment).filter(Comment.document_id == document_id).all()
    result = []
    for c in comments:
        replies = db.query(Reply).filter(Reply.comment_id == c.id).order_by(Reply.created_time).all()
        result.append({
            "id": c.id,
            "documentId": c.document_id,
            "authorId": c.author_id,
            "content": c.content,
            "resolved": c.resolved,
            "quotedText": c.quoted_text,
            "replies": [
                {
                    "id": r.id,
                    "commentId": r.comment_id,
                    "authorId": r.author_id,
                    "content": r.content,
                    "createdTime": r.created_time.isoformat() if r.created_time else None,
                    "modifiedTime": r.modified_time.isoformat() if r.modified_time else None,
                }
                for r in replies
            ],
            "createdTime": c.created_time.isoformat() if c.created_time else None,
            "modifiedTime": c.modified_time.isoformat() if c.modified_time else None,
        })
    return result


def _serialize_user(db: Session, user: User) -> dict:
    """Serialize full user state."""
    documents = _serialize_documents(db, user.id)
    all_comments = []
    for doc in db.query(Document).filter(Document.user_id == user.id).all():
        all_comments.extend(_serialize_comments(db, doc.id))

    revisions = db.query(DocumentRevision).join(Document).filter(Document.user_id == user.id).all()

    # Collect permissions on documents owned by this user AND permissions
    # granted TO this user on other people's documents, so that state
    # dump/restore round-trips correctly for cross-user sharing.
    owned_doc_ids = [d["id"] for d in documents]
    perms_query = db.query(Permission).filter(
        (Permission.document_id.in_(owned_doc_ids)) | (Permission.user_id == user.id)
    ).all()
    seen_perm_ids: set[str] = set()
    all_permissions = []
    for p in perms_query:
        if p.id in seen_perm_ids:
            continue
        seen_perm_ids.add(p.id)
        all_permissions.append({
            "id": p.id,
            "documentId": p.document_id,
            "type": p.type,
            "role": p.role,
            "emailAddress": p.email_address,
            "userId": p.user_id,
            "displayName": p.display_name,
            "createdTime": p.created_time.isoformat() if p.created_time else None,
        })

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "displayName": user.display_name,
        },
        "documents": documents,
        "comments": all_comments,
        "permissions": all_permissions,
        "revisions": [
            {
                "id": r.id,
                "documentId": r.document_id,
                "userId": r.user_id,
                "modifiedTime": r.modified_time.isoformat() if r.modified_time else None,
            }
            for r in revisions
        ],
    }


def get_state_dump() -> dict:
    """Get full state dump for all users."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        users = db.query(User).all()
        return {
            "users": {u.id: _serialize_user(db, u) for u in users},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        db.close()


def take_snapshot(name: str) -> Path:
    """Save current state to a JSON snapshot."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    state = get_state_dump()
    path = SNAPSHOTS_DIR / f"{name}.json"
    path.write_text(json.dumps(state, indent=2))
    return path


def restore_snapshot(name: str) -> bool:
    """Restore DB from a snapshot. Returns True if successful."""
    path = SNAPSHOTS_DIR / f"{name}.json"
    if not path.exists():
        return False

    state = json.loads(path.read_text())
    _restore_from_state(state)
    return True


logger = logging.getLogger(__name__)


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning("Failed to parse datetime %r, falling back to now()", value)
        return datetime.now(timezone.utc)


def _restore_from_state(state: dict):
    """Rebuild DB from a state dict.

    Restores in phases (users -> documents -> comments/replies/permissions/revisions)
    to avoid FK violations when comments reference authors from other users.
    """
    from mock_gdoc.models import Base, get_engine
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        users_data = state.get("users", {})

        # Phase 1: Create all users first
        for user_id, user_data in users_data.items():
            u = user_data["user"]
            db.add(User(id=u["id"], email=u["email"], display_name=u["displayName"]))
        db.flush()

        # Phase 2: Create all documents
        for user_id, user_data in users_data.items():
            for d in user_data.get("documents", []):
                doc = Document(
                    id=d["id"],
                    title=d.get("title", ""),
                    revision_id=d.get("revisionId", "1"),
                    suggestions_view_mode=d.get("suggestionsViewMode", "DEFAULT_FOR_CURRENT_ACCESS"),
                    user_id=user_id,
                    created_time=_parse_dt(d.get("createdTime")) or datetime.now(timezone.utc),
                    modified_time=_parse_dt(d.get("modifiedTime")) or datetime.now(timezone.utc),
                )
                doc.body = d.get("body", {})
                doc.document_style = d.get("documentStyle", {})
                doc.named_styles = d.get("namedStyles", {})
                doc.lists = d.get("lists", {})
                doc.inline_objects = d.get("inlineObjects", {})
                doc.headers = d.get("headers", {})
                doc.footers = d.get("footers", {})
                doc.footnotes = d.get("footnotes", {})
                doc.named_ranges = d.get("namedRanges", {})
                doc.positioned_objects = d.get("positionedObjects", {})
                db.add(doc)
        db.flush()

        # Phase 3: Create comments, replies, permissions, revisions
        seen_comment_ids: set[str] = set()
        seen_perm_ids: set[str] = set()

        for user_id, user_data in users_data.items():
            for c in user_data.get("comments", []):
                if c["id"] in seen_comment_ids:
                    continue
                seen_comment_ids.add(c["id"])
                db.add(Comment(
                    id=c["id"],
                    document_id=c["documentId"],
                    author_id=c["authorId"],
                    content=c.get("content", ""),
                    resolved=c.get("resolved", False),
                    quoted_text=c.get("quotedText"),
                    created_time=_parse_dt(c.get("createdTime")) or datetime.now(timezone.utc),
                    modified_time=_parse_dt(c.get("modifiedTime")) or datetime.now(timezone.utc),
                ))

                for r in c.get("replies", []):
                    db.add(Reply(
                        id=r["id"],
                        comment_id=r["commentId"],
                        author_id=r["authorId"],
                        content=r.get("content", ""),
                        created_time=_parse_dt(r.get("createdTime")) or datetime.now(timezone.utc),
                        modified_time=_parse_dt(r.get("modifiedTime")) or datetime.now(timezone.utc),
                    ))

            for p in user_data.get("permissions", []):
                if p["id"] in seen_perm_ids:
                    continue
                seen_perm_ids.add(p["id"])
                db.add(Permission(
                    id=p["id"],
                    document_id=p["documentId"],
                    type=p.get("type", "user"),
                    role=p.get("role", "reader"),
                    email_address=p.get("emailAddress"),
                    user_id=p.get("userId"),
                    display_name=p.get("displayName"),
                    created_time=_parse_dt(p.get("createdTime")) or datetime.now(timezone.utc),
                ))

            for r in user_data.get("revisions", []):
                db.add(DocumentRevision(
                    id=r["id"],
                    document_id=r["documentId"],
                    user_id=r.get("userId", user_id),
                    modified_time=_parse_dt(r.get("modifiedTime")) or datetime.now(timezone.utc),
                ))

        db.commit()
    finally:
        db.close()


def get_diff(initial_state: dict | None = None) -> dict:
    """Compute diff between initial state (snapshot) and current state."""
    current = get_state_dump()

    if initial_state is None:
        path = SNAPSHOTS_DIR / "initial.json"
        if path.exists():
            initial_state = json.loads(path.read_text())
        else:
            return {"error": "No initial snapshot found"}

    diff = {"added": {}, "updated": {}, "deleted": {}}

    for user_id, current_user in current.get("users", {}).items():
        initial_user = initial_state.get("users", {}).get(user_id)
        if not initial_user:
            diff["added"][user_id] = current_user
            continue

        # Compare documents
        curr_docs = {d["id"]: d for d in current_user.get("documents", [])}
        init_docs = {d["id"]: d for d in initial_user.get("documents", [])}

        user_diff = {"documents": {"added": [], "updated": [], "deleted": []}}

        for did, doc in curr_docs.items():
            if did not in init_docs:
                user_diff["documents"]["added"].append(doc)
            elif doc != init_docs[did]:
                changes = {}
                for k, v in doc.items():
                    if init_docs[did].get(k) != v:
                        changes[k] = v
                user_diff["documents"]["updated"].append({"id": did, **changes})

        for did in init_docs:
            if did not in curr_docs:
                user_diff["documents"]["deleted"].append(init_docs[did])

        # Compare comments
        curr_comments = {c["id"]: c for c in current_user.get("comments", [])}
        init_comments = {c["id"]: c for c in initial_user.get("comments", [])}

        comments_diff = {"added": [], "updated": [], "deleted": []}
        for cid, comment in curr_comments.items():
            if cid not in init_comments:
                comments_diff["added"].append(comment)
            elif comment != init_comments[cid]:
                changes = {}
                for k, v in comment.items():
                    if init_comments[cid].get(k) != v:
                        changes[k] = v
                comments_diff["updated"].append({"id": cid, **changes})
        for cid in init_comments:
            if cid not in curr_comments:
                comments_diff["deleted"].append(init_comments[cid])

        if any(comments_diff.values()):
            user_diff["comments"] = comments_diff

        # Compare permissions
        curr_perms = {p["id"]: p for p in current_user.get("permissions", [])}
        init_perms = {p["id"]: p for p in initial_user.get("permissions", [])}

        perms_diff = {"added": [], "updated": [], "deleted": []}
        for pid, perm in curr_perms.items():
            if pid not in init_perms:
                perms_diff["added"].append(perm)
            elif perm != init_perms[pid]:
                changes = {}
                for k, v in perm.items():
                    if init_perms[pid].get(k) != v:
                        changes[k] = v
                perms_diff["updated"].append({"id": pid, **changes})
        for pid in init_perms:
            if pid not in curr_perms:
                perms_diff["deleted"].append(init_perms[pid])

        if any(perms_diff.values()):
            user_diff["permissions"] = perms_diff

        if any(user_diff["documents"].values()) or "comments" in user_diff or "permissions" in user_diff:
            diff["updated"][user_id] = user_diff

    return diff
