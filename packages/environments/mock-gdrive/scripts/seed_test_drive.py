"""Create test data in a real Google Drive account for golden fixture capture.

Usage:
    uv run python scripts/seed_test_drive.py

Creates: 1 folder, 1 Google Doc, 1 plain text file, shares the doc with a viewer.
"""

import sys
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

sys.path.insert(0, str(Path(__file__).parent))
from auth import get_credentials

SCOPES_NEEDED = ["https://www.googleapis.com/auth/drive"]


def seed():
    creds = get_credentials()

    # Check if we have write scope — if not, we need to re-auth
    if creds.scopes and not any("drive" == s.split("/")[-1] for s in creds.scopes):
        print("Warning: Token may only have read-only scope. If writes fail, re-auth with full drive scope.")

    service = build("drive", "v3", credentials=creds)

    print("Creating test data in Google Drive...\n")

    # 1. Create a folder
    print("[1] Creating folder: Test Project")
    folder_meta = {
        "name": "Test Project",
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = service.files().create(body=folder_meta, fields="id,name").execute()
    folder_id = folder["id"]
    print(f"    Created folder: {folder_id}")

    # 2. Create a Google Doc inside the folder
    print("[2] Creating Google Doc: Meeting Notes")
    doc_meta = {
        "name": "Meeting Notes",
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    doc = service.files().create(body=doc_meta, fields="id,name").execute()
    doc_id = doc["id"]
    print(f"    Created doc: {doc_id}")

    # 3. Create a plain text file
    print("[3] Creating text file: readme.txt")
    txt_meta = {
        "name": "readme.txt",
        "parents": [folder_id],
    }
    txt_content = MediaInMemoryUpload(
        b"This is a test file for golden fixture capture.\nIt contains sample text.",
        mimetype="text/plain",
    )
    txt = service.files().create(
        body=txt_meta, media_body=txt_content, fields="id,name"
    ).execute()
    txt_id = txt["id"]
    print(f"    Created file: {txt_id}")

    # 4. Create a spreadsheet at root
    print("[4] Creating spreadsheet: Budget 2024")
    sheet_meta = {
        "name": "Budget 2024",
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    sheet = service.files().create(body=sheet_meta, fields="id,name").execute()
    sheet_id = sheet["id"]
    print(f"    Created spreadsheet: {sheet_id}")

    # 5. Star the doc
    print("[5] Starring Meeting Notes")
    service.files().update(fileId=doc_id, body={"starred": True}).execute()

    # 6. Share the folder with anyone (viewer link)
    print("[6] Sharing folder with 'anyone' as reader")
    try:
        service.permissions().create(
            fileId=folder_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()
    except Exception as e:
        print(f"    Sharing failed (may need broader scope): {e}")

    print(f"\nDone! Created 4 items. Now run: uv run python scripts/capture_fixtures.py")


if __name__ == "__main__":
    seed()
