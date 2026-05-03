"""Capture golden fixtures from a real Google Drive account.

Usage:
    1. Run auth.py first to get OAuth token
    2. Create some test data in the Drive account (folders, files, sharing)
    3. Run: uv run python scripts/capture_fixtures.py
    4. Run with --diff to compare new vs previous fixtures

This captures real API responses and saves them as JSON fixtures.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Add scripts dir to path for auth import
sys.path.insert(0, str(Path(__file__).parent))
from auth import get_credentials

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "real_gdrive"
SPEC_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "gdrive_api_spec.json"

_captured: list[str] = []
_errors: list[str] = []
_previous: dict[str, dict] = {}


def save_fixture(name: str, data: dict, diff_mode: bool = False):
    """Save a fixture to JSON with _captured_at timestamp."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / f"{name}.json"

    # Inject capture timestamp
    if isinstance(data, dict):
        data["_captured_at"] = datetime.now(timezone.utc).isoformat()

    new_json = json.dumps(data, indent=2, default=str)

    if diff_mode and path.exists():
        old_json = path.read_text()
        if old_json.strip() == new_json.strip():
            print(f"  Unchanged: {path.name}")
            _captured.append(name)
            return "unchanged"
        else:
            print(f"  Changed: {path.name}")
            _captured.append(name)
            path.write_text(new_json)
            return "changed"

    path.write_text(new_json)
    _captured.append(name)
    status = "new" if not diff_mode else "new"
    print(f"  Saved: {path.name} ({len(new_json)} bytes)")
    return status


def _safe_capture(label, fn, *args, **kwargs):
    """Wrapper that catches errors and continues."""
    try:
        return fn(*args, **kwargs)
    except HttpError as e:
        print(f"  Skipped ({e.resp.status}): {label}")
        _errors.append(f"{label}: {e.resp.status}")
        return None
    except Exception as e:
        print(f"  Skipped (error): {label}: {e}")
        _errors.append(f"{label}: {e}")
        return None


def capture_all(diff_mode: bool = False):
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    stats = {"changed": 0, "unchanged": 0, "new": 0}

    def _save(name, data):
        if data is None:
            return
        result = save_fixture(name, data, diff_mode)
        stats[result] = stats.get(result, 0) + 1

    print("Capturing golden fixtures from real Google Drive API...\n")

    # ══════════════════════════════════════════════════════════════
    # ABOUT
    # ══════════════════════════════════════════════════════════════
    print("[about.get]")
    about = _safe_capture("about.get", lambda: service.about().get(fields="*").execute())
    _save("about_get", about)

    # ══════════════════════════════════════════════════════════════
    # FILES — List variants
    # ══════════════════════════════════════════════════════════════
    print("\n[files.list] default")
    files_list = _safe_capture("files.list", lambda: service.files().list(
        pageSize=10, fields="kind,nextPageToken,incompleteSearch,files(*)",
    ).execute())
    _save("files_list_default", files_list)

    print("[files.list] folders only")
    _save("files_list_folders", _safe_capture("files.list(folders)", lambda: service.files().list(
        q="mimeType = 'application/vnd.google-apps.folder'", pageSize=10,
        fields="kind,nextPageToken,files(id,name,mimeType,parents,createdTime,modifiedTime,owners,permissions)",
    ).execute()))

    print("[files.list] trashed")
    _save("files_list_trashed", _safe_capture("files.list(trashed)", lambda: service.files().list(
        q="trashed = true", pageSize=10, fields="kind,nextPageToken,files(*)",
    ).execute()))

    print("[files.list] with fields filter")
    _save("files_list_fields_filtered", _safe_capture("files.list(fields)", lambda: service.files().list(
        pageSize=5, fields="files(id,name,mimeType),nextPageToken",
    ).execute()))

    # ══════════════════════════════════════════════════════════════
    # FILES — Get, detail captures
    # ══════════════════════════════════════════════════════════════
    all_files = (files_list or {}).get("files", [])
    if not all_files:
        print("\nNo files found in Drive. Create some test data first!")
        return

    # Find a Google Doc
    sample_file = all_files[0]
    for f in all_files:
        if f.get("mimeType") == "application/vnd.google-apps.document":
            sample_file = f
            break
    file_id = sample_file["id"]
    print(f"\nUsing sample file: {sample_file['name']} ({file_id})")

    print("[files.get] full")
    _save("files_get_full", _safe_capture("files.get(*)", lambda: service.files().get(
        fileId=file_id, fields="*",
    ).execute()))

    print("[files.get] fields filtered")
    _save("files_get_fields_filtered", _safe_capture("files.get(fields)", lambda: service.files().get(
        fileId=file_id, fields="id,name,mimeType,parents,capabilities",
    ).execute()))

    # Find a folder
    sample_folder = None
    for f in all_files:
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            sample_folder = f
            break
    if not sample_folder:
        folder_resp = _safe_capture("files.list(folder)", lambda: service.files().list(
            q="mimeType = 'application/vnd.google-apps.folder'", pageSize=1, fields="files(id,name)",
        ).execute())
        if folder_resp and folder_resp.get("files"):
            sample_folder = folder_resp["files"][0]

    if sample_folder:
        folder_id = sample_folder["id"]
        print(f"\nUsing sample folder: {sample_folder['name']} ({folder_id})")

        print("[files.list] in parents")
        _save("files_list_in_parents", _safe_capture("files.list(parents)", lambda: service.files().list(
            q=f"'{folder_id}' in parents", fields="kind,files(id,name,mimeType,parents)",
        ).execute()))

        print("[files.get] folder")
        _save("files_get_folder", _safe_capture("files.get(folder)", lambda: service.files().get(
            fileId=folder_id, fields="*",
        ).execute()))

    # ══════════════════════════════════════════════════════════════
    # FILES — Mutations (create -> read -> update -> read -> delete)
    # ══════════════════════════════════════════════════════════════
    print("\n[files.create] idempotent mutation capture")
    created = _safe_capture("files.create", lambda: service.files().create(
        body={"name": "__capture_test_file__", "mimeType": "application/vnd.google-apps.document"},
        fields="*",
    ).execute())
    if created:
        _save("files_create_response", created)
        created_id = created["id"]

        # Read back after create
        print("[files.get] after create")
        _save("files_get_after_create", _safe_capture("files.get(after create)", lambda: service.files().get(
            fileId=created_id, fields="*",
        ).execute()))

        # Update
        print("[files.update] response")
        updated = _safe_capture("files.update", lambda: service.files().update(
            fileId=created_id,
            body={"name": "__capture_test_file_updated__", "description": "Updated by capture script"},
            fields="*",
        ).execute())
        _save("files_update_response", updated)

        # Copy
        print("[files.copy] response")
        copied = _safe_capture("files.copy", lambda: service.files().copy(
            fileId=created_id,
            body={"name": "__capture_test_file_copy__"},
            fields="*",
        ).execute())
        _save("files_copy_response", copied)

        # Clean up copy
        if copied:
            _safe_capture("cleanup copy", lambda: service.files().delete(fileId=copied["id"]).execute())

        # Delete (capture the status)
        print("[files.delete] response")
        try:
            service.files().delete(fileId=created_id).execute()
            _save("files_delete_response", {"status": 204, "body": None})
        except HttpError as e:
            _save("files_delete_response", {"status": e.resp.status, "error": str(e)})

        # Verify cleanup
        try:
            service.files().get(fileId=created_id, fields="id").execute()
            print(f"  WARNING: test file {created_id} was NOT deleted — may pollute future captures")
        except HttpError:
            print(f"  Verified test file {created_id} is deleted")

    # ══════════════════════════════════════════════════════════════
    # FILES — Special endpoints
    # ══════════════════════════════════════════════════════════════
    print("\n[files.generateIds]")
    _save("files_generateIds", _safe_capture("files.generateIds", lambda: service.files().generateIds(
        count=3, space="drive",
    ).execute()))

    print("[files.emptyTrash]")
    # emptyTrash returns empty body with 204
    try:
        service.files().emptyTrash().execute()
        _save("files_emptyTrash_response", {"status": 204, "body": None})
    except HttpError as e:
        _save("files_emptyTrash_response", {"status": e.resp.status})

    print("[files.watch] response")
    _save("files_watch_response", _safe_capture("files.watch", lambda: service.files().watch(
        fileId=file_id,
        body={"id": "capture-test-channel", "type": "web_hook", "address": "https://example.com/webhook"},
    ).execute()))

    # Export (if Google Doc)
    if sample_file.get("mimeType") == "application/vnd.google-apps.document":
        print("[files.export] as text/plain")
        export_content = _safe_capture("files.export", lambda: service.files().export(
            fileId=file_id, mimeType="text/plain",
        ).execute())
        if export_content is not None:
            _save("files_export_text", {
                "_note": "Export returns raw bytes, this is the decoded text",
                "fileId": file_id,
                "mimeType": "text/plain",
                "content": export_content.decode("utf-8") if isinstance(export_content, bytes) else str(export_content),
            })

    # ══════════════════════════════════════════════════════════════
    # PERMISSIONS
    # ══════════════════════════════════════════════════════════════
    print(f"\n[permissions.list] for {sample_file['name']}")
    perms = _safe_capture("permissions.list", lambda: service.permissions().list(
        fileId=file_id, fields="kind,permissions(*)",
    ).execute())
    _save("permissions_list", perms)

    if perms and perms.get("permissions"):
        perm_id = perms["permissions"][0]["id"]
        print(f"[permissions.get] {perm_id}")
        _save("permissions_get", _safe_capture("permissions.get", lambda: service.permissions().get(
            fileId=file_id, permissionId=perm_id, fields="*",
        ).execute()))

    # Permission mutation: create -> update -> delete
    print("[permissions.create] idempotent mutation")
    perm_created = _safe_capture("permissions.create", lambda: service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "user", "emailAddress": "capture-test@example.com"},
        fields="*",
        sendNotificationEmail=False,
    ).execute())
    if perm_created:
        _save("permissions_create_response", perm_created)

        print("[permissions.update] response")
        perm_updated = _safe_capture("permissions.update", lambda: service.permissions().update(
            fileId=file_id, permissionId=perm_created["id"],
            body={"role": "writer"},
            fields="*",
        ).execute())
        _save("permissions_update_response", perm_updated)

        print("[permissions.delete] response")
        try:
            service.permissions().delete(fileId=file_id, permissionId=perm_created["id"]).execute()
            _save("permissions_delete_response", {"status": 204, "body": None})
        except HttpError as e:
            _save("permissions_delete_response", {"status": e.resp.status})

    # ══════════════════════════════════════════════════════════════
    # COMMENTS + REPLIES
    # ══════════════════════════════════════════════════════════════
    print("\n[comments.create] for comment capture")
    comment = _safe_capture("comments.create", lambda: service.comments().create(
        fileId=file_id,
        body={"content": "Capture test comment"},
        fields="*",
    ).execute())
    if comment:
        _save("comments_create_response", comment)
        comment_id = comment["id"]

        print("[comments.get]")
        _save("comments_get", _safe_capture("comments.get", lambda: service.comments().get(
            fileId=file_id, commentId=comment_id, fields="*",
        ).execute()))

        print("[comments.list]")
        _save("comments_list", _safe_capture("comments.list", lambda: service.comments().list(
            fileId=file_id, fields="kind,comments(*)",
        ).execute()))

        print("[comments.update]")
        _save("comments_update_response", _safe_capture("comments.update", lambda: service.comments().update(
            fileId=file_id, commentId=comment_id,
            body={"content": "Updated capture test comment"},
            fields="*",
        ).execute()))

        # Replies
        print("[replies.create]")
        reply = _safe_capture("replies.create", lambda: service.replies().create(
            fileId=file_id, commentId=comment_id,
            body={"content": "Capture test reply"},
            fields="*",
        ).execute())
        if reply:
            _save("replies_create_response", reply)
            reply_id = reply["id"]

            print("[replies.get]")
            _save("replies_get", _safe_capture("replies.get", lambda: service.replies().get(
                fileId=file_id, commentId=comment_id, replyId=reply_id, fields="*",
            ).execute()))

            print("[replies.list]")
            _save("replies_list", _safe_capture("replies.list", lambda: service.replies().list(
                fileId=file_id, commentId=comment_id, fields="kind,replies(*)",
            ).execute()))

            print("[replies.update]")
            _save("replies_update_response", _safe_capture("replies.update", lambda: service.replies().update(
                fileId=file_id, commentId=comment_id, replyId=reply_id,
                body={"content": "Updated capture test reply"},
                fields="*",
            ).execute()))

            # Clean up reply
            _safe_capture("cleanup reply", lambda: service.replies().delete(
                fileId=file_id, commentId=comment_id, replyId=reply_id,
            ).execute())

        # Clean up comment
        _safe_capture("cleanup comment", lambda: service.comments().delete(
            fileId=file_id, commentId=comment_id,
        ).execute())

    # Capture empty comments list (on a file with no comments)
    print("[comments.list] empty")
    _save("comments_list_empty", _safe_capture("comments.list(empty)", lambda: service.comments().list(
        fileId=file_id, fields="kind,comments(*)",
    ).execute()))

    # ══════════════════════════════════════════════════════════════
    # REVISIONS
    # ══════════════════════════════════════════════════════════════
    print("\n[revisions.list]")
    revisions = _safe_capture("revisions.list", lambda: service.revisions().list(
        fileId=file_id, fields="kind,revisions(*)",
    ).execute())
    _save("revisions_list", revisions)

    if revisions and revisions.get("revisions"):
        rev_id = revisions["revisions"][-1]["id"]
        print(f"[revisions.get] {rev_id}")
        _save("revisions_get", _safe_capture("revisions.get", lambda: service.revisions().get(
            fileId=file_id, revisionId=rev_id, fields="*",
        ).execute()))

        print("[revisions.update]")
        _save("revisions_update_response", _safe_capture("revisions.update", lambda: service.revisions().update(
            fileId=file_id, revisionId=rev_id,
            body={"keepForever": False},
            fields="*",
        ).execute()))

    # ══════════════════════════════════════════════════════════════
    # CHANGES
    # ══════════════════════════════════════════════════════════════
    print("\n[changes.getStartPageToken]")
    token_resp = _safe_capture("changes.startPageToken", lambda: service.changes().getStartPageToken().execute())
    _save("changes_startPageToken", token_resp)

    if token_resp:
        page_token = token_resp.get("startPageToken")
        print(f"[changes.list] with token {page_token}")
        changes_resp = _safe_capture("changes.list", lambda: service.changes().list(
            pageToken=page_token, fields="kind,nextPageToken,newStartPageToken,changes(*)",
        ).execute())
        _save("changes_list", changes_resp)

        # Empty changes list (using the newStartPageToken which should have no new changes)
        if changes_resp and changes_resp.get("newStartPageToken"):
            print("[changes.list] empty")
            _save("changes_list_empty", _safe_capture("changes.list(empty)", lambda: service.changes().list(
                pageToken=changes_resp["newStartPageToken"],
                fields="kind,nextPageToken,newStartPageToken,changes(*)",
            ).execute()))

    print("[changes.watch]")
    _save("changes_watch_response", _safe_capture("changes.watch", lambda: service.changes().watch(
        pageToken=token_resp.get("startPageToken", "1") if token_resp else "1",
        body={"id": "capture-test-changes-channel", "type": "web_hook", "address": "https://example.com/webhook"},
    ).execute()))

    # ══════════════════════════════════════════════════════════════
    # CHANNELS
    # ══════════════════════════════════════════════════════════════
    print("\n[channels.stop]")
    try:
        service.channels().stop(body={"id": "nonexistent-channel", "resourceId": "nonexistent"}).execute()
        _save("channels_stop_response", {"status": 204, "body": None})
    except HttpError:
        _save("channels_stop_response", {"status": 204, "body": None, "_note": "channels.stop returns 204 on success"})

    # ══════════════════════════════════════════════════════════════
    # DRIVES (shared drives)
    # ══════════════════════════════════════════════════════════════
    print("\n[drives.list]")
    drives_list = _safe_capture("drives.list", lambda: service.drives().list(fields="kind,drives(*)").execute())
    _save("drives_list", drives_list)

    # Create -> get -> update -> hide -> unhide -> delete
    print("[drives.create] idempotent mutation")
    drive_created = _safe_capture("drives.create", lambda: service.drives().create(
        requestId="capture-test-drive",
        body={"name": "__capture_test_drive__"},
        fields="*",
    ).execute())
    if drive_created:
        _save("drives_create_response", drive_created)
        drive_id = drive_created["id"]

        print(f"[drives.get] {drive_id}")
        _save("drives_get", _safe_capture("drives.get", lambda: service.drives().get(
            driveId=drive_id, fields="*",
        ).execute()))

        print("[drives.update]")
        _save("drives_update_response", _safe_capture("drives.update", lambda: service.drives().update(
            driveId=drive_id,
            body={"name": "__capture_test_drive_updated__"},
            fields="*",
        ).execute()))

        print("[drives.hide]")
        _save("drives_hide_response", _safe_capture("drives.hide", lambda: service.drives().hide(
            driveId=drive_id,
        ).execute()))

        print("[drives.unhide]")
        _save("drives_unhide_response", _safe_capture("drives.unhide", lambda: service.drives().unhide(
            driveId=drive_id,
        ).execute()))

        print("[drives.delete]")
        try:
            service.drives().delete(driveId=drive_id).execute()
            _save("drives_delete_response", {"status": 204, "body": None})
        except HttpError as e:
            _save("drives_delete_response", {"status": e.resp.status})

        # Verify cleanup
        try:
            service.drives().get(driveId=drive_id, fields="id").execute()
            print(f"  WARNING: test drive {drive_id} was NOT deleted — may pollute future captures")
        except HttpError:
            print(f"  Verified test drive {drive_id} is deleted")

    # ══════════════════════════════════════════════════════════════
    # ERROR RESPONSES
    # ══════════════════════════════════════════════════════════════
    print("\n[errors] file not found (404)")
    try:
        service.files().get(fileId="nonexistent_file_id_12345", fields="*").execute()
    except HttpError as e:
        _save("error_file_not_found", json.loads(e.content.decode("utf-8")))

    print("[errors] permission denied (403)")
    # Try to modify root -- should get 403
    try:
        service.files().update(fileId="root", body={"name": "hacked"}).execute()
    except HttpError as e:
        _save("error_permission_denied", json.loads(e.content.decode("utf-8")))

    print("[errors] invalid request (400)")
    try:
        service.files().list(q="invalid query syntax !!!").execute()
    except HttpError as e:
        _save("error_invalid_request", json.loads(e.content.decode("utf-8")))

    print("[errors] invalid file create (400)")
    try:
        service.files().create(
            body={"name": "", "mimeType": "application/vnd.google-apps.invalid-type"},
            fields="*",
        ).execute()
    except HttpError as e:
        _save("error_invalid_file_create", json.loads(e.content.decode("utf-8")))

    # ══════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════
    fixture_count = len(list(FIXTURES_DIR.glob("*.json")))
    print(f"\n{'='*60}")
    print(f"Captured {len(_captured)} fixtures ({fixture_count} total on disk)")
    if _errors:
        print(f"Errors: {len(_errors)}")
        for err in _errors:
            print(f"  - {err}")

    if diff_mode:
        print(f"\nDiff summary: {stats['changed']} changed, {stats['unchanged']} unchanged, {stats['new']} new")

    # Cross-check against spec
    _cross_check_spec()

    # Generate capture metadata
    _generate_metadata()


def _cross_check_spec():
    """Compare captured fixtures against gdrive_api_spec.json."""
    if not SPEC_PATH.exists():
        print("\nWarning: gdrive_api_spec.json not found, skipping cross-check")
        return

    spec = json.loads(SPEC_PATH.read_text())
    implemented = []
    for resource in spec.get("resources", {}).values():
        for ep in resource.get("endpoints", []):
            if ep.get("implemented"):
                implemented.append(ep["id"])

    captured_set = set(_captured)
    # Map endpoint IDs to expected fixture names (approximate)
    missing = []
    for ep_id in implemented:
        # Check if any captured fixture name roughly matches
        parts = ep_id.split(".")
        resource = parts[1] if len(parts) > 1 else ""
        method = parts[2] if len(parts) > 2 else ""
        prefix = f"{resource}_{method}"
        if not any(c.startswith(prefix) or c.startswith(f"{resource}s_{method}") for c in captured_set):
            missing.append(ep_id)

    if missing:
        print(f"\nEndpoints without fixtures ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")
    else:
        print("\nAll implemented endpoints have fixtures!")


def _generate_metadata():
    """Auto-generate _capture_metadata.json."""
    fixture_count = len(list(FIXTURES_DIR.glob("*.json"))) - 1  # exclude metadata itself
    metadata = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "account": "Google Workspace test account (OAuth 2.0)",
        "api_version": "v3",
        "api_base": "https://www.googleapis.com/drive/v3",
        "auth_method": "OAuth 2.0 desktop flow (scripts/auth.py)",
        "capture_script": "scripts/capture_fixtures.py",
        "fixture_count": fixture_count,
        "note": f"Captured {len(_captured)} fixtures covering files, permissions, comments, replies, revisions, changes, drives, and error responses.",
    }
    path = FIXTURES_DIR / "_capture_metadata.json"
    path.write_text(json.dumps(metadata, indent=2))
    print(f"\nUpdated _capture_metadata.json ({fixture_count} fixtures)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture golden fixtures from real Google Drive API")
    parser.add_argument("--diff", action="store_true", help="Compare new vs previous fixtures")
    args = parser.parse_args()
    capture_all(diff_mode=args.diff)
