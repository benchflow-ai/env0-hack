"""Conformance tests — validate mock response shapes against the Drive API Discovery Document.

These tests verify that our Pydantic schemas and API responses match the real
Google Drive API's field names, types, and structure. The Discovery Document
(https://www.googleapis.com/discovery/v1/apis/drive/v3/rest) is the single
source of truth.
"""

import json
from pathlib import Path

import pytest
from mock_gdrive.api.schemas import (
    FileResource, FileList, PermissionResource, PermissionList,
    AboutResource, GeneratedIds, Channel, UserInfo, ShortcutDetails, StorageQuota,
)

DISCOVERY_PATH = Path(__file__).parent / "fixtures" / "drive_discovery.json"


@pytest.fixture(scope="module")
def discovery():
    return json.loads(DISCOVERY_PATH.read_text())


def _get_schema(discovery, name):
    return discovery["schemas"][name]["properties"]


def _get_nested(discovery, schema_name, field_name):
    return discovery["schemas"][schema_name]["properties"][field_name]["properties"]


def _pydantic_fields(model_cls) -> set[str]:
    """Get all field names from a Pydantic model, using aliases where defined."""
    fields = set()
    for name, info in model_cls.model_fields.items():
        alias = info.alias if info.alias else name
        fields.add(alias)
    return fields


# ── FileResource ──────────────────────────────────────────────────────────────


class TestFileResourceConformance:
    """Verify FileResource fields match the Drive API File schema."""

    def test_all_mock_fields_exist_in_real_api(self, discovery):
        """Every field we return must exist in the real API."""
        real_fields = set(_get_schema(discovery, "File").keys())
        mock_fields = _pydantic_fields(FileResource)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"

    def test_critical_fields_present(self, discovery):
        """Fields that agents commonly use must be in our schema."""
        critical = {
            "id", "name", "mimeType", "parents", "starred", "trashed",
            "createdTime", "modifiedTime", "size", "description",
            "version", "owners", "capabilities", "kind",
            "ownedByMe", "shared", "webViewLink", "writersCanShare",
        }
        mock_fields = _pydantic_fields(FileResource)
        missing = critical - mock_fields
        assert not missing, f"Missing critical fields: {missing}"

    def test_kind_value(self):
        """FileResource.kind must be 'drive#file'."""
        f = FileResource(id="x", name="x", mimeType="text/plain")
        assert f.kind == "drive#file"

    def test_size_is_string(self, discovery):
        """Real API returns size as string (int64 format). Verify our schema matches."""
        real_type = _get_schema(discovery, "File")["size"]["type"]
        assert real_type == "string", "Real API 'size' should be string"
        f = FileResource(id="x", name="x", mimeType="text/plain", size="1024")
        assert isinstance(f.size, str)

    def test_version_is_string(self, discovery):
        """Real API returns version as string (int64 format)."""
        real_type = _get_schema(discovery, "File")["version"]["type"]
        assert real_type == "string", "Real API 'version' should be string"
        f = FileResource(id="x", name="x", mimeType="text/plain", version="5")
        assert isinstance(f.version, str)

    def test_parents_is_array(self, discovery):
        """Real API returns parents as array."""
        real_type = _get_schema(discovery, "File")["parents"]["type"]
        assert real_type == "array"

    def test_owners_is_array(self, discovery):
        """Real API returns owners as array."""
        real_type = _get_schema(discovery, "File")["owners"]["type"]
        assert real_type == "array"


# ── FileList ──────────────────────────────────────────────────────────────────


class TestFileListConformance:
    def test_all_fields_match(self, discovery):
        real_fields = set(_get_schema(discovery, "FileList").keys())
        mock_fields = _pydantic_fields(FileList)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"

    def test_required_fields(self, discovery):
        real_fields = set(_get_schema(discovery, "FileList").keys())
        mock_fields = _pydantic_fields(FileList)
        for field in ["kind", "files", "nextPageToken"]:
            assert field in mock_fields, f"Missing field: {field}"

    def test_kind_value(self):
        fl = FileList(files=[])
        assert fl.kind == "drive#fileList"


# ── PermissionResource ────────────────────────────────────────────────────────


class TestPermissionConformance:
    def test_all_mock_fields_exist_in_real_api(self, discovery):
        real_fields = set(_get_schema(discovery, "Permission").keys())
        mock_fields = _pydantic_fields(PermissionResource)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"

    def test_critical_fields_present(self):
        critical = {"id", "role", "type", "emailAddress", "displayName", "kind", "permissionDetails"}
        mock_fields = _pydantic_fields(PermissionResource)
        missing = critical - mock_fields
        assert not missing, f"Missing critical fields: {missing}"

    def test_kind_value(self):
        p = PermissionResource(id="x", role="reader", type="user")
        assert p.kind == "drive#permission"

    def test_permission_details_structure(self):
        """permissionDetails should be a list of objects with permissionType, role, inherited."""
        from mock_gdrive.api.schemas import PermissionDetailItem
        item = PermissionDetailItem(permissionType="file", role="writer", inherited=True)
        assert item.permissionType == "file"
        assert item.role == "writer"
        assert item.inherited is True


# ── PermissionList ────────────────────────────────────────────────────────────


class TestPermissionListConformance:
    def test_all_fields_match(self, discovery):
        real_fields = set(_get_schema(discovery, "PermissionList").keys())
        mock_fields = _pydantic_fields(PermissionList)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"

    def test_kind_value(self):
        pl = PermissionList(permissions=[])
        assert pl.kind == "drive#permissionList"


# ── About ─────────────────────────────────────────────────────────────────────


class TestAboutConformance:
    def test_all_mock_fields_exist_in_real_api(self, discovery):
        real_fields = set(_get_schema(discovery, "About").keys())
        mock_fields = _pydantic_fields(AboutResource)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"

    def test_kind_value(self):
        a = AboutResource(
            user=UserInfo(displayName="x", emailAddress="x@x.com"),
            storageQuota=StorageQuota(),
        )
        assert a.kind == "drive#about"


# ── GeneratedIds ──────────────────────────────────────────────────────────────


class TestGeneratedIdsConformance:
    def test_all_fields_match(self, discovery):
        real_fields = set(_get_schema(discovery, "GeneratedIds").keys())
        mock_fields = _pydantic_fields(GeneratedIds)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"

    def test_kind_value(self):
        g = GeneratedIds(ids=["a"], space="drive")
        assert g.kind == "drive#generatedIds"


# ── Channel ───────────────────────────────────────────────────────────────────


class TestChannelConformance:
    def test_all_mock_fields_exist_in_real_api(self, discovery):
        real_fields = set(_get_schema(discovery, "Channel").keys())
        mock_fields = _pydantic_fields(Channel)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"


# ── UserInfo ──────────────────────────────────────────────────────────────────


class TestUserInfoConformance:
    def test_all_mock_fields_exist_in_real_api(self, discovery):
        real_fields = set(_get_schema(discovery, "User").keys())
        mock_fields = _pydantic_fields(UserInfo)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"

    def test_critical_fields(self):
        mock_fields = _pydantic_fields(UserInfo)
        for field in ["displayName", "emailAddress", "me", "kind"]:
            assert field in mock_fields, f"Missing: {field}"


# ── ShortcutDetails ───────────────────────────────────────────────────────────


class TestShortcutDetailsConformance:
    def test_all_mock_fields_exist_in_real_api(self, discovery):
        real_fields = set(_get_nested(discovery, "File", "shortcutDetails").keys())
        mock_fields = _pydantic_fields(ShortcutDetails)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"


# ── Capabilities ──────────────────────────────────────────────────────────────


class TestCapabilitiesConformance:
    """Verify computed capabilities use real API field names."""

    def test_all_capability_names_exist_in_real_api(self, discovery):
        """Every capability we return must exist in the real API."""
        real_caps = set(_get_nested(discovery, "File", "capabilities").keys())
        # Get capabilities from compute_capabilities
        from mock_gdrive.api.capabilities import compute_capabilities
        from mock_gdrive.models import File, User

        dummy_file = File(id="x", name="x", mime_type="text/plain", owner_id="u1")
        dummy_user = User(id="u1", email="x@x.com", display_name="X")
        mock_caps = set(compute_capabilities(dummy_file, dummy_user, "owner").keys())

        unknown = mock_caps - real_caps
        assert not unknown, f"Mock returns capabilities not in real API: {unknown}"

    def test_all_capabilities_are_booleans(self, discovery):
        """Real API capabilities are all booleans."""
        real_caps = _get_nested(discovery, "File", "capabilities")
        for name, info in real_caps.items():
            assert info["type"] == "boolean", f"{name} should be boolean"


# ── StorageQuota ──────────────────────────────────────────────────────────────


class TestStorageQuotaConformance:
    def test_all_mock_fields_exist_in_real_api(self, discovery):
        real_fields = set(_get_nested(discovery, "About", "storageQuota").keys())
        mock_fields = _pydantic_fields(StorageQuota)
        unknown = mock_fields - real_fields
        assert not unknown, f"Mock returns fields not in real API: {unknown}"


# ── Integration: Live endpoint response shapes ───────────────────────────────


class TestEndpointResponseShapes:
    """Verify actual API responses have correct top-level structure."""

    def test_files_list_shape(self, client, seed_user):
        resp = client.get("/drive/v3/files")
        data = resp.json()
        assert "kind" in data
        assert data["kind"] == "drive#fileList"
        assert "files" in data
        assert isinstance(data["files"], list)

    def test_files_get_shape(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}")
        data = resp.json()
        assert data["kind"] == "drive#file"
        assert isinstance(data["id"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data.get("parents", []), list)
        assert isinstance(data.get("version"), str)
        assert isinstance(data.get("capabilities"), dict)

    def test_files_get_owners_shape(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}")
        data = resp.json()
        owners = data.get("owners", [])
        assert isinstance(owners, list)
        assert len(owners) >= 1
        owner = owners[0]
        assert "displayName" in owner
        assert "emailAddress" in owner

    def test_permissions_list_shape(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/permissions")
        data = resp.json()
        assert data["kind"] == "drive#permissionList"
        assert isinstance(data["permissions"], list)
        if data["permissions"]:
            perm = data["permissions"][0]
            assert "id" in perm
            assert "role" in perm
            assert "type" in perm

    def test_about_shape(self, client, seed_user):
        resp = client.get("/drive/v3/about")
        data = resp.json()
        assert data["kind"] == "drive#about"
        assert "user" in data
        assert "storageQuota" in data
        user = data["user"]
        assert "displayName" in user
        assert "emailAddress" in user
        assert isinstance(user.get("me"), bool)

    def test_generate_ids_shape(self, client, seed_user):
        resp = client.get("/drive/v3/files/generateIds", params={"count": 3})
        data = resp.json()
        assert "ids" in data
        assert isinstance(data["ids"], list)
        assert len(data["ids"]) == 3
        assert "space" in data
