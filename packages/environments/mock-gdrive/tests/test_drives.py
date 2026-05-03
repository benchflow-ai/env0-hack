"""Tests for Shared Drives API endpoints."""

import json
import pytest


class TestDrivesCreate:
    def test_create_drive(self, client, seed_user):
        resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_1"},
            content=json.dumps({"name": "Engineering Drive"}),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#drive"
        assert data["name"] == "Engineering Drive"
        assert "id" in data
        assert "createdTime" in data
        assert "capabilities" in data
        assert "restrictions" in data

    def test_create_requires_request_id(self, client, seed_user):
        resp = client.post(
            "/drive/v3/drives",
            content=json.dumps({"name": "Test"}),
        )
        assert resp.status_code == 400  # Missing required requestId (Google-style error)

    def test_create_with_theme(self, client, seed_user):
        resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_2"},
            content=json.dumps({"name": "Design Drive", "colorRgb": "#FF6D01"}),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["colorRgb"] == "#FF6D01"


class TestDrivesGet:
    def test_get_drive(self, client, seed_user):
        # Create first
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_get"},
            content=json.dumps({"name": "Get Test Drive"}),
        )
        drive_id = create_resp.json()["id"]

        resp = client.get(f"/drive/v3/drives/{drive_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == drive_id
        assert data["name"] == "Get Test Drive"
        assert data["capabilities"]["canDeleteDrive"] is True

    def test_get_not_found(self, client, seed_user):
        resp = client.get("/drive/v3/drives/nonexistent")
        assert resp.status_code == 404

    def test_get_with_fields(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_fields"},
            content=json.dumps({"name": "Fields Test"}),
        )
        drive_id = create_resp.json()["id"]

        resp = client.get(
            f"/drive/v3/drives/{drive_id}",
            params={"fields": "id,name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"id", "name"}


class TestDrivesList:
    def test_list_empty(self, client, seed_user):
        resp = client.get("/drive/v3/drives")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#driveList"
        assert data["drives"] == []

    def test_list_drives(self, client, seed_user):
        # Create two drives
        for i in range(2):
            client.post(
                "/drive/v3/drives",
                params={"requestId": f"req_list_{i}"},
                content=json.dumps({"name": f"Drive {i}"}),
            )

        resp = client.get("/drive/v3/drives")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["drives"]) == 2

    def test_list_pagination(self, client, seed_user):
        for i in range(3):
            client.post(
                "/drive/v3/drives",
                params={"requestId": f"req_page_{i}"},
                content=json.dumps({"name": f"Page Drive {i}"}),
            )

        resp = client.get("/drive/v3/drives", params={"pageSize": 2})
        data = resp.json()
        assert len(data["drives"]) == 2
        assert "nextPageToken" in data

        # Get next page
        resp2 = client.get(
            "/drive/v3/drives",
            params={"pageSize": 2, "pageToken": data["nextPageToken"]},
        )
        data2 = resp2.json()
        assert len(data2["drives"]) == 1
        assert "nextPageToken" not in data2

    def test_list_query_contains(self, client, seed_user):
        client.post(
            "/drive/v3/drives",
            params={"requestId": "req_q1"},
            content=json.dumps({"name": "Engineering Drive"}),
        )
        client.post(
            "/drive/v3/drives",
            params={"requestId": "req_q2"},
            content=json.dumps({"name": "Marketing Drive"}),
        )

        resp = client.get(
            "/drive/v3/drives",
            params={"q": "name contains 'Engineering'"},
        )
        data = resp.json()
        assert len(data["drives"]) == 1
        assert data["drives"][0]["name"] == "Engineering Drive"

    def test_list_hidden_excluded(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_hide"},
            content=json.dumps({"name": "Hidden Drive"}),
        )
        drive_id = create_resp.json()["id"]
        client.post(f"/drive/v3/drives/{drive_id}/hide")

        resp = client.get("/drive/v3/drives")
        data = resp.json()
        assert all(d["name"] != "Hidden Drive" for d in data["drives"])

    def test_list_hidden_with_admin_access(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_admin"},
            content=json.dumps({"name": "Admin Hidden Drive"}),
        )
        drive_id = create_resp.json()["id"]
        client.post(f"/drive/v3/drives/{drive_id}/hide")

        resp = client.get(
            "/drive/v3/drives",
            params={"useDomainAdminAccess": True},
        )
        data = resp.json()
        names = [d["name"] for d in data["drives"]]
        assert "Admin Hidden Drive" in names


class TestDrivesUpdate:
    def test_update_name(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_upd"},
            content=json.dumps({"name": "Old Name"}),
        )
        drive_id = create_resp.json()["id"]

        resp = client.patch(
            f"/drive/v3/drives/{drive_id}",
            content=json.dumps({"name": "New Name"}),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_restrictions(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_restr"},
            content=json.dumps({"name": "Restricted Drive"}),
        )
        drive_id = create_resp.json()["id"]

        resp = client.patch(
            f"/drive/v3/drives/{drive_id}",
            content=json.dumps({
                "restrictions": {
                    "domainUsersOnly": True,
                    "driveMembersOnly": True,
                }
            }),
        )
        assert resp.status_code == 200
        r = resp.json()["restrictions"]
        assert r["domainUsersOnly"] is True
        assert r["driveMembersOnly"] is True
        assert r["copyRequiresWriterPermission"] is False  # unchanged

    def test_update_not_found(self, client, seed_user):
        resp = client.patch(
            "/drive/v3/drives/nonexistent",
            content=json.dumps({"name": "x"}),
        )
        assert resp.status_code == 404


class TestDrivesDelete:
    def test_delete_drive(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_del"},
            content=json.dumps({"name": "Delete Me"}),
        )
        drive_id = create_resp.json()["id"]

        resp = client.delete(f"/drive/v3/drives/{drive_id}")
        assert resp.status_code == 204

        # Verify deleted
        resp2 = client.get(f"/drive/v3/drives/{drive_id}")
        assert resp2.status_code == 404

    def test_delete_not_found(self, client, seed_user):
        resp = client.delete("/drive/v3/drives/nonexistent")
        assert resp.status_code == 404


class TestDrivesHideUnhide:
    def test_hide_drive(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_h"},
            content=json.dumps({"name": "Hide Me"}),
        )
        drive_id = create_resp.json()["id"]

        resp = client.post(f"/drive/v3/drives/{drive_id}/hide")
        assert resp.status_code == 200
        assert resp.json()["hidden"] is True

    def test_unhide_drive(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_uh"},
            content=json.dumps({"name": "Unhide Me"}),
        )
        drive_id = create_resp.json()["id"]

        client.post(f"/drive/v3/drives/{drive_id}/hide")
        resp = client.post(f"/drive/v3/drives/{drive_id}/unhide")
        assert resp.status_code == 200
        assert resp.json()["hidden"] is False

    def test_hide_not_found(self, client, seed_user):
        resp = client.post("/drive/v3/drives/nonexistent/hide")
        assert resp.status_code == 404

    def test_unhide_not_found(self, client, seed_user):
        resp = client.post("/drive/v3/drives/nonexistent/unhide")
        assert resp.status_code == 404


class TestDriveResourceShape:
    """Verify the Drive resource matches the real API shape."""

    def test_capabilities_keys(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_shape"},
            content=json.dumps({"name": "Shape Test"}),
        )
        caps = create_resp.json()["capabilities"]
        expected_keys = {
            "canAddChildren",
            "canChangeCopyRequiresWriterPermissionRestriction",
            "canChangeDomainUsersOnlyRestriction",
            "canChangeDownloadRestriction",
            "canChangeDriveBackground",
            "canChangeDriveMembersOnlyRestriction",
            "canChangeSharingFoldersRequiresOrganizerPermissionRestriction",
            "canComment",
            "canCopy",
            "canDeleteChildren",
            "canDeleteDrive",
            "canDownload",
            "canEdit",
            "canListChildren",
            "canManageMembers",
            "canReadRevisions",
            "canRename",
            "canRenameDrive",
            "canResetDriveRestrictions",
            "canShare",
            "canTrashChildren",
        }
        assert set(caps.keys()) == expected_keys

    def test_restrictions_keys(self, client, seed_user):
        create_resp = client.post(
            "/drive/v3/drives",
            params={"requestId": "req_restr_shape"},
            content=json.dumps({"name": "Restrictions Shape"}),
        )
        r = create_resp.json()["restrictions"]
        expected_keys = {
            "adminManagedRestrictions",
            "copyRequiresWriterPermission",
            "domainUsersOnly",
            "driveMembersOnly",
            "sharingFoldersRequiresOrganizerPermission",
        }
        assert set(r.keys()) == expected_keys
