#!/usr/bin/env python3
"""Capture golden fixtures from real Google Docs + Drive APIs.

Prerequisites:
    - Run scripts/auth.py first to get scripts/token.json
    - Ensure at least one Google Doc exists in the test account

Usage:
    python scripts/capture_fixtures.py
    python scripts/capture_fixtures.py --diff   # Show changes vs existing fixtures

Saves fixtures to tests/fixtures/real_gdocs/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PKG_DIR = SCRIPTS_DIR.parent
FIXTURES_DIR = PKG_DIR / "tests" / "fixtures" / "real_gdocs"
TOKEN_PATH = SCRIPTS_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def get_services():
    """Load credentials and build API service clients."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        print(
            "Missing dependencies. Install with:\n"
            "  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client",
            file=sys.stderr,
        )
        sys.exit(1)

    if not TOKEN_PATH.exists():
        print("No token.json found. Run scripts/auth.py first.", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return docs, drive


def save(name: str, data: dict, diff_mode: bool = False):
    """Save a fixture, optionally diffing against existing."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    # Avoid double .json extension if name already ends with .json
    if name.endswith(".json"):
        path = FIXTURES_DIR / name
    else:
        path = FIXTURES_DIR / f"{name}.json"

    data["_captured_at"] = datetime.now(timezone.utc).isoformat()

    if diff_mode and path.exists():
        old = json.loads(path.read_text())
        old.pop("_captured_at", None)
        new = {k: v for k, v in data.items() if k != "_captured_at"}
        if old == new:
            print(f"  {name}: unchanged")
            return False
        else:
            print(f"  {name}: CHANGED")
            # Show key-level diff
            old_keys = set(old.keys())
            new_keys = set(new.keys())
            for k in new_keys - old_keys:
                print(f"    + {k}")
            for k in old_keys - new_keys:
                print(f"    - {k}")
            for k in old_keys & new_keys:
                if old[k] != new[k]:
                    print(f"    ~ {k}")

    path.write_text(json.dumps(data, indent=2))
    print(f"  {name}: saved")
    return True


def capture_drive_files_list(drive, diff_mode: bool):
    """Capture Drive files.list for Google Docs."""
    print("\n--- Drive files.list ---")

    # Non-empty list
    result = drive.files().list(
        q="mimeType='application/vnd.google-apps.document'",
        pageSize=5,
        fields="kind,files(id,name,mimeType,createdTime,modifiedTime,owners,webViewLink),incompleteSearch,nextPageToken",
    ).execute()
    save("drive_files_list.json", result, diff_mode)

    # Empty list (search for something that won't match)
    empty = drive.files().list(
        q="mimeType='application/vnd.google-apps.document' and name = 'zzz_nonexistent_fixture_capture_12345'",
        pageSize=5,
        fields="kind,files(id,name,mimeType),incompleteSearch,nextPageToken",
    ).execute()
    save("drive_files_list_empty.json", empty, diff_mode)


def capture_drive_files_get(drive, file_id: str, diff_mode: bool):
    """Capture Drive files.get for a specific doc."""
    print("\n--- Drive files.get ---")
    result = drive.files().get(
        fileId=file_id,
        fields="kind,id,name,mimeType,createdTime,modifiedTime,owners,webViewLink",
    ).execute()
    save("drive_files_get.json", result, diff_mode)


def capture_documents_get(docs, doc_id: str, diff_mode: bool):
    """Capture documents.get."""
    print("\n--- Documents get ---")
    result = docs.documents().get(documentId=doc_id).execute()
    save("document_get.json", result, diff_mode)


def capture_documents_create_and_delete(docs, drive, diff_mode: bool):
    """Capture documents.create response, then clean up."""
    print("\n--- Documents create ---")
    result = docs.documents().create(
        body={"title": "_fixture_capture_test_doc"}
    ).execute()
    save("document_create.json", result, diff_mode)

    # Clean up: delete via Drive
    doc_id = result["documentId"]
    try:
        drive.files().delete(fileId=doc_id).execute()
        print(f"  Cleaned up test doc {doc_id}")
    except Exception as e:
        print(f"  Warning: could not delete test doc {doc_id}: {e}")

    # Verify cleanup
    try:
        drive.files().get(fileId=doc_id).execute()
        print(f"  WARNING: test doc {doc_id} was NOT deleted — may pollute future captures")
    except Exception:
        print(f"  Verified test doc {doc_id} is deleted")


def capture_documents_batch_update(docs, drive, diff_mode: bool):
    """Capture documents.batchUpdate response."""
    print("\n--- Documents batchUpdate ---")

    # Create a temporary doc for this
    temp = docs.documents().create(
        body={"title": "_fixture_capture_batchUpdate_test"}
    ).execute()
    temp_id = temp["documentId"]

    # Insert text
    result = docs.documents().batchUpdate(
        documentId=temp_id,
        body={
            "requests": [
                {"insertText": {"location": {"index": 1}, "text": "Hello fixture capture!"}}
            ]
        },
    ).execute()
    save("document_batch_update.json", result, diff_mode)

    # replaceAllText
    result2 = docs.documents().batchUpdate(
        documentId=temp_id,
        body={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": "Hello", "matchCase": True},
                        "replaceText": "Goodbye",
                    }
                }
            ]
        },
    ).execute()
    save("document_batch_update_replace.json", result2, diff_mode)

    # Clean up via Drive
    try:
        drive.files().delete(fileId=temp_id).execute()
        print(f"  Cleaned up temp doc {temp_id}")
    except Exception as e:
        print(f"  Warning: could not delete temp doc {temp_id}: {e}")

    # Verify cleanup
    try:
        drive.files().get(fileId=temp_id).execute()
        print(f"  WARNING: temp doc {temp_id} was NOT deleted — may pollute future captures")
    except Exception:
        print(f"  Verified temp doc {temp_id} is deleted")


def capture_error_responses(docs, drive, diff_mode: bool):
    """Capture error responses for 404 and 400 cases."""
    from googleapiclient.errors import HttpError

    print("\n--- Error responses ---")

    # Document not found (404)
    try:
        docs.documents().get(documentId="nonexistent_doc_id_12345").execute()
    except HttpError as e:
        error_body = json.loads(e.content.decode("utf-8"))
        save("document_not_found_error.json", error_body, diff_mode)

    # Drive file not found (404)
    try:
        drive.files().get(fileId="nonexistent_file_id_12345").execute()
    except HttpError as e:
        error_body = json.loads(e.content.decode("utf-8"))
        save("file_not_found_error.json", error_body, diff_mode)

    # Invalid batchUpdate (400) - bad request index
    try:
        docs.documents().batchUpdate(
            documentId="nonexistent_doc_id_12345",
            body={
                "requests": [
                    {"insertText": {"location": {"index": -1}, "text": "bad"}}
                ]
            },
        ).execute()
    except HttpError as e:
        error_body = json.loads(e.content.decode("utf-8"))
        save("batch_update_invalid_error.json", error_body, diff_mode)


def capture_metadata(diff_mode: bool):
    """Write capture metadata."""
    metadata = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "account": "(configure in scripts/auth.py)",
        "api_version": "v1 (Docs), v3 (Drive)",
        "api_base_docs": "https://docs.googleapis.com/v1",
        "api_base_drive": "https://www.googleapis.com/drive/v3",
        "auth_method": "OAuth 2.0 (scripts/auth.py → scripts/token.json)",
        "capture_script": "scripts/capture_fixtures.py",
        "fixture_count": 0,  # Updated below
        "note": "Fixtures captured from real Google Docs + Drive APIs.",
    }

    # Count fixtures
    if FIXTURES_DIR.exists():
        fixtures = [f for f in FIXTURES_DIR.glob("*.json") if f.name != "_capture_metadata.json"]
        metadata["fixture_count"] = len(fixtures)

    path = FIXTURES_DIR / "_capture_metadata.json"
    path.write_text(json.dumps(metadata, indent=2))
    print(f"\nMetadata written: {metadata['fixture_count']} fixtures")


def main():
    parser = argparse.ArgumentParser(description="Capture golden fixtures from real Google APIs")
    parser.add_argument("--diff", action="store_true", help="Show changes vs existing fixtures")
    args = parser.parse_args()

    docs, drive = get_services()

    # Find a doc to use for get/batchUpdate captures
    results = drive.files().list(
        q="mimeType='application/vnd.google-apps.document'",
        pageSize=1,
        fields="files(id,name)",
    ).execute()
    files = results.get("files", [])
    if not files:
        print("No Google Docs found — creating a sample doc...")
        sample_doc = docs.documents().create(
            body={"title": "_fixture_sample_doc"}
        ).execute()
        sample_id = sample_doc["documentId"]
        # Insert some content so it's non-trivial
        docs.documents().batchUpdate(
            documentId=sample_id,
            body={"requests": [
                {"insertText": {"location": {"index": 1}, "text": "Sample document for fixture capture.\nSecond paragraph."}}
            ]},
        ).execute()
        print(f"Created sample doc: {sample_id}")
    else:
        sample_id = files[0]["id"]
        print(f"Using sample doc: {files[0]['name']} ({sample_id})")

    # Capture all endpoints
    capture_drive_files_list(drive, args.diff)
    capture_drive_files_get(drive, sample_id, args.diff)
    capture_documents_get(docs, sample_id, args.diff)
    capture_documents_create_and_delete(docs, drive, args.diff)
    capture_documents_batch_update(docs, drive, args.diff)
    capture_error_responses(docs, drive, args.diff)
    capture_metadata(args.diff)

    print("\nDone! Fixtures saved to tests/fixtures/real_gdocs/")


if __name__ == "__main__":
    main()
