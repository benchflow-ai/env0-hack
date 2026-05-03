"""Tests for the Permissions API endpoints."""

from mock_gdrive.models import File, Permission, User


class TestPermissionsList:
    def test_list_permissions(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#permissionList"
        assert len(data["permissions"]) == 1
        assert data["permissions"][0]["role"] == "owner"

    def test_list_permissions_file_not_found(self, client, seed_user):
        resp = client.get("/drive/v3/files/nonexistent/permissions")
        assert resp.status_code == 404


class TestPermissionsCreate:
    def test_share_with_user(self, client, seed_user, seed_file, seed_users):
        bob = seed_users["bob@example.com"]
        resp = client.post(f"/drive/v3/files/{seed_file.id}/permissions", json={
            "role": "reader",
            "type": "user",
            "emailAddress": bob.email,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "reader"
        assert data["emailAddress"] == bob.email

    def test_share_with_anyone(self, client, seed_user, seed_file):
        resp = client.post(f"/drive/v3/files/{seed_file.id}/permissions", json={
            "role": "reader",
            "type": "anyone",
        })
        assert resp.status_code == 200
        assert resp.json()["type"] == "anyone"

    def test_share_invalid_role(self, client, seed_user, seed_file):
        resp = client.post(f"/drive/v3/files/{seed_file.id}/permissions", json={
            "role": "superadmin",
            "type": "user",
        })
        assert resp.status_code == 400

    def test_transfer_ownership_requires_flag(self, client, seed_user, seed_file, seed_users):
        bob = seed_users["bob@example.com"]
        resp = client.post(f"/drive/v3/files/{seed_file.id}/permissions", json={
            "role": "owner",
            "type": "user",
            "emailAddress": bob.email,
        })
        assert resp.status_code == 400  # transferOwnership not set

    def test_transfer_ownership(self, client, seed_user, seed_file, seed_users):
        bob = seed_users["bob@example.com"]
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/permissions",
            params={"transferOwnership": True},
            json={
                "role": "owner",
                "type": "user",
                "emailAddress": bob.email,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "owner"

    def test_missing_role_type(self, client, seed_user, seed_file):
        resp = client.post(f"/drive/v3/files/{seed_file.id}/permissions", json={
            "emailAddress": "someone@example.com",
        })
        assert resp.status_code == 400


class TestPermissionsUpdate:
    def test_update_role(self, client, seed_user, seed_file, seed_users, db_session):
        bob = seed_users["bob@example.com"]
        perm = Permission(
            id="perm_bob_reader", file_id=seed_file.id, role="reader",
            type="user", email_address=bob.email,
        )
        db_session.add(perm)
        db_session.commit()

        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}/permissions/{perm.id}",
            json={"role": "writer"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "writer"

    def test_update_not_found(self, client, seed_user, seed_file):
        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}/permissions/nonexistent",
            json={"role": "writer"},
        )
        assert resp.status_code == 404


class TestPermissionsDelete:
    def test_delete_permission(self, client, seed_user, seed_file, seed_users, db_session):
        bob = seed_users["bob@example.com"]
        perm = Permission(
            id="perm_bob_del", file_id=seed_file.id, role="reader",
            type="user", email_address=bob.email,
        )
        db_session.add(perm)
        db_session.commit()

        resp = client.delete(f"/drive/v3/files/{seed_file.id}/permissions/{perm.id}")
        assert resp.status_code == 204

    def test_cannot_delete_owner_permission(self, client, seed_user, seed_file):
        # Get the owner permission
        perms = client.get(f"/drive/v3/files/{seed_file.id}/permissions").json()
        owner_perm = [p for p in perms["permissions"] if p["role"] == "owner"][0]

        resp = client.delete(f"/drive/v3/files/{seed_file.id}/permissions/{owner_perm['id']}")
        assert resp.status_code == 400

    def test_delete_not_found(self, client, seed_user, seed_file):
        resp = client.delete(f"/drive/v3/files/{seed_file.id}/permissions/nonexistent")
        assert resp.status_code == 404


class TestPermissionsVisibility:
    def test_shared_file_visible_to_recipient(self, client, seed_users, db_session):
        """A file shared with Bob should be visible to Bob in files.list."""
        alice = seed_users["alice@example.com"]
        bob = seed_users["bob@example.com"]

        f = File(
            id="file_shared", name="Shared Doc", mime_type="text/plain",
            owner_id=alice.id, last_modifying_user_id=alice.id,
        )
        db_session.add(f)
        db_session.add(Permission(
            id="perm_a_own", file_id="file_shared", role="owner",
            type="user", email_address=alice.email,
        ))
        db_session.add(Permission(
            id="perm_b_read", file_id="file_shared", role="reader",
            type="user", email_address=bob.email,
        ))
        db_session.commit()

        # Bob can see the file
        resp = client.get("/drive/v3/files",
                          headers={"X-Mock-Drive-User": bob.email})
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert any(f["id"] == "file_shared" for f in files)

    def test_unshared_file_not_visible(self, client, seed_users, db_session):
        """A file not shared with Bob should NOT be visible to Bob."""
        alice = seed_users["alice@example.com"]
        bob = seed_users["bob@example.com"]

        f = File(
            id="file_private", name="Private Doc", mime_type="text/plain",
            owner_id=alice.id, last_modifying_user_id=alice.id,
        )
        db_session.add(f)
        db_session.add(Permission(
            id="perm_a_own2", file_id="file_private", role="owner",
            type="user", email_address=alice.email,
        ))
        db_session.commit()

        resp = client.get("/drive/v3/files",
                          headers={"X-Mock-Drive-User": bob.email})
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert not any(f["id"] == "file_private" for f in files)
