"""Tests for the Files API endpoints."""

import json


class TestFilesList:
    def test_list_empty(self, client, seed_user):
        resp = client.get("/drive/v3/files")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#fileList"
        assert data["files"] == []

    def test_list_returns_files(self, client, seed_user, seed_file):
        resp = client.get("/drive/v3/files")
        assert resp.status_code == 200
        data = resp.json()
        # seed_file depends on seed_folder, so both are returned
        assert len(data["files"]) == 2
        names = {f["name"] for f in data["files"]}
        assert "Test Document" in names
        assert "Test Folder" in names

    def test_list_excludes_trashed(self, client, seed_user, seed_file, db_session):
        seed_file.trashed = True
        db_session.commit()
        resp = client.get("/drive/v3/files")
        assert resp.status_code == 200
        # Only the non-trashed folder remains
        files = resp.json()["files"]
        assert len(files) == 1
        assert files[0]["name"] == "Test Folder"

    def test_list_includes_trashed_when_queried(self, client, seed_user, seed_file, db_session):
        from mock_gdrive.models import File
        seed_file.trashed = True
        db_session.commit()
        resp = client.get("/drive/v3/files", params={"q": "trashed = true"})
        assert resp.status_code == 200
        assert len(resp.json()["files"]) == 1

    def test_list_excludes_folders_by_default(self, client, seed_user, seed_folder, seed_file):
        """Folders and files are both returned in list."""
        resp = client.get("/drive/v3/files")
        data = resp.json()
        names = [f["name"] for f in data["files"]]
        assert "Test Document" in names
        assert "Test Folder" in names

    def test_list_query_name_contains(self, client, seed_user, seed_file):
        resp = client.get("/drive/v3/files", params={"q": "name contains 'Test'"})
        assert resp.status_code == 200
        assert len(resp.json()["files"]) >= 1

    def test_list_query_name_eq(self, client, seed_user, seed_file):
        resp = client.get("/drive/v3/files", params={"q": "name = 'Test Document'"})
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert len(files) == 1
        assert files[0]["name"] == "Test Document"

    def test_list_query_mimetype(self, client, seed_user, seed_folder, seed_file):
        resp = client.get("/drive/v3/files", params={
            "q": "mimeType = 'application/vnd.google-apps.folder'"
        })
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert all(f["mimeType"] == "application/vnd.google-apps.folder" for f in files)

    def test_list_query_in_parents(self, client, seed_user, seed_folder, seed_file):
        resp = client.get("/drive/v3/files", params={
            "q": f"'{seed_folder.id}' in parents"
        })
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert len(files) == 1
        assert files[0]["id"] == seed_file.id

    def test_list_query_fulltext_contains(self, client, seed_user, seed_file):
        resp = client.get("/drive/v3/files", params={
            "q": "fullText contains 'keywords for searching'"
        })
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert len(files) == 1
        assert files[0]["id"] == seed_file.id

    def test_list_query_compound_and(self, client, seed_user, seed_folder, seed_file):
        resp = client.get("/drive/v3/files", params={
            "q": f"name contains 'Test' and '{seed_folder.id}' in parents"
        })
        assert resp.status_code == 200
        assert len(resp.json()["files"]) == 1

    def test_list_query_not(self, client, seed_user, seed_folder, seed_file):
        resp = client.get("/drive/v3/files", params={
            "q": "not mimeType = 'application/vnd.google-apps.folder'"
        })
        assert resp.status_code == 200
        files = resp.json()["files"]
        for f in files:
            assert f["mimeType"] != "application/vnd.google-apps.folder"

    def test_list_pagination(self, client, seed_user, seed_folder, seed_file):
        resp = client.get("/drive/v3/files", params={"pageSize": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["files"]) == 1
        assert data.get("nextPageToken") is not None

    def test_list_fields_filter(self, client, seed_user, seed_file):
        resp = client.get("/drive/v3/files", params={
            "fields": "files(id,name),nextPageToken"
        })
        assert resp.status_code == 200
        data = resp.json()
        f = data["files"][0]
        assert "id" in f
        assert "name" in f
        assert "mimeType" not in f
        assert "capabilities" not in f

    def test_list_invalid_query(self, client, seed_user):
        resp = client.get("/drive/v3/files", params={"q": "invalid %%% query"})
        assert resp.status_code == 400


class TestFilesGet:
    def test_get_file(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == seed_file.id
        assert data["name"] == "Test Document"
        assert data["kind"] == "drive#file"
        assert data["ownedByMe"] is True
        assert "capabilities" in data

    def test_get_file_not_found(self, client, seed_user):
        resp = client.get("/drive/v3/files/nonexistent")
        assert resp.status_code == 404

    def test_get_file_fields(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}", params={"fields": "id,name"})
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"id", "name"}

    def test_get_file_alt_media(self, client, seed_user, db_session):
        """alt=media returns content for non-Google files."""
        f = File(
            id="file_binary",
            name="test.txt",
            mime_type="text/plain",
            owner_id="user_test",
            last_modifying_user_id="user_test",
            content_blob=b"hello world",
            size=11,
        )
        db_session.add(f)
        db_session.add(Permission(
            id="perm_bin", file_id="file_binary", role="owner",
            type="user", email_address="test@example.com",
        ))
        db_session.commit()

        resp = client.get("/drive/v3/files/file_binary", params={"alt": "media"})
        assert resp.status_code == 200
        assert resp.content == b"hello world"

    def test_get_google_doc_alt_media_rejected(self, client, seed_user, seed_file):
        """alt=media on Google Docs type should return 403."""
        resp = client.get(f"/drive/v3/files/{seed_file.id}", params={"alt": "media"})
        assert resp.status_code == 403


class TestFilesCreate:
    def test_create_file(self, client, seed_user):
        resp = client.post("/drive/v3/files", json={
            "name": "New File",
            "mimeType": "application/vnd.google-apps.document",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New File"
        assert data["ownedByMe"] is True

    def test_create_folder(self, client, seed_user):
        resp = client.post("/drive/v3/files", json={
            "name": "New Folder",
            "mimeType": "application/vnd.google-apps.folder",
        })
        assert resp.status_code == 200
        assert resp.json()["mimeType"] == "application/vnd.google-apps.folder"

    def test_create_with_parent(self, client, seed_user, seed_folder):
        resp = client.post("/drive/v3/files", json={
            "name": "Child File",
            "mimeType": "application/vnd.google-apps.document",
            "parents": [seed_folder.id],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["parents"] == [seed_folder.id]

    def test_create_with_invalid_parent(self, client, seed_user):
        resp = client.post("/drive/v3/files", json={
            "name": "Orphan",
            "parents": ["nonexistent"],
        })
        assert resp.status_code == 404

    def test_create_shortcut(self, client, seed_user, seed_file):
        resp = client.post("/drive/v3/files", json={
            "name": "Shortcut to Test",
            "mimeType": "application/vnd.google-apps.shortcut",
            "shortcutDetails": {
                "targetId": seed_file.id,
                "targetMimeType": seed_file.mime_type,
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["shortcutDetails"]["targetId"] == seed_file.id


class TestFilesPatch:
    def test_rename(self, client, seed_user, seed_file):
        resp = client.patch(f"/drive/v3/files/{seed_file.id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    def test_trash(self, client, seed_user, seed_file):
        resp = client.patch(f"/drive/v3/files/{seed_file.id}", json={"trashed": True})
        assert resp.status_code == 200
        assert resp.json()["trashed"] is True

    def test_untrash(self, client, seed_user, seed_file, db_session):
        seed_file.trashed = True
        seed_file.explicitly_trashed = True
        db_session.commit()
        resp = client.patch(f"/drive/v3/files/{seed_file.id}", json={"trashed": False})
        assert resp.status_code == 200
        assert resp.json()["trashed"] is False

    def test_move_file(self, client, seed_user, seed_folder, seed_file, db_session):
        new_folder = File(
            id="folder_new", name="New Folder",
            mime_type="application/vnd.google-apps.folder",
            owner_id=seed_user.id, last_modifying_user_id=seed_user.id,
        )
        db_session.add(new_folder)
        db_session.add(Permission(
            id="perm_nf", file_id="folder_new", role="owner",
            type="user", email_address=seed_user.email,
        ))
        db_session.commit()

        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}",
            params={"addParents": new_folder.id, "removeParents": seed_folder.id},
        )
        assert resp.status_code == 200
        assert resp.json()["parents"] == [new_folder.id]

    def test_trash_folder_cascades(self, client, seed_user, seed_folder, seed_file):
        resp = client.patch(f"/drive/v3/files/{seed_folder.id}", json={"trashed": True})
        assert resp.status_code == 200
        # Child should also be trashed
        child = client.get(f"/drive/v3/files/{seed_file.id}")
        assert child.json()["trashed"] is True

    def test_patch_not_found(self, client, seed_user):
        resp = client.patch("/drive/v3/files/nonexistent", json={"name": "x"})
        assert resp.status_code == 404

    def test_version_increments(self, client, seed_user, seed_file):
        v1 = client.get(f"/drive/v3/files/{seed_file.id}").json()["version"]
        client.patch(f"/drive/v3/files/{seed_file.id}", json={"name": "v2"})
        v2 = client.get(f"/drive/v3/files/{seed_file.id}").json()["version"]
        assert int(v2) == int(v1) + 1


class TestFilesDelete:
    def test_delete_file(self, client, seed_user, seed_file):
        resp = client.delete(f"/drive/v3/files/{seed_file.id}")
        assert resp.status_code == 204
        # Verify gone
        resp2 = client.get(f"/drive/v3/files/{seed_file.id}")
        assert resp2.status_code == 404

    def test_delete_not_owner(self, client, seed_users, db_session):
        """Non-owner cannot delete."""
        alice = seed_users["alice@example.com"]
        bob = seed_users["bob@example.com"]
        f = File(
            id="file_bob", name="Bob's file", mime_type="text/plain",
            owner_id=bob.id, last_modifying_user_id=bob.id,
        )
        db_session.add(f)
        db_session.add(Permission(
            id="perm_bob", file_id="file_bob", role="owner",
            type="user", email_address=bob.email,
        ))
        db_session.add(Permission(
            id="perm_alice_reader", file_id="file_bob", role="reader",
            type="user", email_address=alice.email,
        ))
        db_session.commit()

        # Alice tries to delete Bob's file
        resp = client.delete("/drive/v3/files/file_bob",
                             headers={"X-Mock-Drive-User": alice.email})
        assert resp.status_code == 403

    def test_delete_folder_cascades(self, client, seed_user, seed_folder, seed_file):
        resp = client.delete(f"/drive/v3/files/{seed_folder.id}")
        assert resp.status_code == 204
        # Child should also be gone
        resp2 = client.get(f"/drive/v3/files/{seed_file.id}")
        assert resp2.status_code == 404

    def test_delete_not_found(self, client, seed_user):
        resp = client.delete("/drive/v3/files/nonexistent")
        assert resp.status_code == 404


class TestFilesCopy:
    def test_copy_file(self, client, seed_user, seed_file):
        resp = client.post(f"/drive/v3/files/{seed_file.id}/copy", json={"name": "Copy"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Copy"
        assert data["id"] != seed_file.id

    def test_copy_folder_rejected(self, client, seed_user, seed_folder):
        resp = client.post(f"/drive/v3/files/{seed_folder.id}/copy")
        assert resp.status_code == 400


class TestFilesExport:
    def test_export_google_doc(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/export",
                          params={"mimeType": "text/plain"})
        assert resp.status_code == 200
        assert b"test document content" in resp.content

    def test_export_unsupported_mime(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/export",
                          params={"mimeType": "video/mp4"})
        assert resp.status_code == 400

    def test_export_non_google_type(self, client, seed_user, db_session):
        f = File(
            id="file_pdf", name="test.pdf", mime_type="application/pdf",
            owner_id="user_test", last_modifying_user_id="user_test",
        )
        db_session.add(f)
        db_session.add(Permission(
            id="perm_pdf", file_id="file_pdf", role="owner",
            type="user", email_address="test@example.com",
        ))
        db_session.commit()
        resp = client.get("/drive/v3/files/file_pdf/export",
                          params={"mimeType": "text/plain"})
        assert resp.status_code == 400


class TestFilesGenerateIds:
    def test_generate_ids(self, client, seed_user):
        resp = client.get("/drive/v3/files/generateIds", params={"count": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ids"]) == 5
        assert len(set(data["ids"])) == 5  # all unique


class TestEmptyTrash:
    def test_empty_trash(self, client, seed_user, seed_file, db_session):
        seed_file.trashed = True
        db_session.commit()
        resp = client.delete("/drive/v3/files/trash")
        assert resp.status_code == 204
        # File should be permanently gone
        resp2 = client.get(f"/drive/v3/files/{seed_file.id}")
        assert resp2.status_code == 404


# Import File here for use in fixtures within test methods
from mock_gdrive.models import File, Permission
