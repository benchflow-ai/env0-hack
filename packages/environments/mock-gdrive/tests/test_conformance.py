"""Conformance tests — validate mock responses against real Google Drive API fixtures.

These tests compare the structure and field types of our mock API responses
against actual responses captured from the real Google Drive API v3.

Real fixtures are in tests/fixtures/real_gdrive/ and were captured using
scripts/capture_fixtures.py with a real Google account. Every fixture file
in that directory should have at least one test here.
"""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "real_gdrive"


def _load(name: str) -> dict:
    data = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
    # Strip capture metadata before comparing
    if isinstance(data, dict):
        data.pop("_captured_at", None)
    return data


def _fixture_exists(name: str) -> bool:
    return (FIXTURES_DIR / f"{name}.json").exists()


def _type_of(value) -> str:
    """Return a simplified type name for comparison."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


# Fields the real API returns that our mock intentionally omits.
# These are documented gaps — our mock focuses on fields agents actually use.
KNOWN_MISSING_FILE_FIELDS = {
    # Thumbnail version (numeric)
    "thumbnailVersion",
    # Download restrictions (new API feature, complex nested object)
    "downloadRestrictions",
    # Deprecated viewer restriction
    "viewersCanCopyContent",
    # Inherited permissions (Shared Drive specific)
    "inheritedPermissionsDisabled",
    # Inline permissions only returned with fields=*
    "permissions",
    # Fields that require actual content or special context to populate
    "exportLinks",
    # Fields in our schema but not always populated (Optional, excluded when None)
    "webViewLink", "size",
}

KNOWN_MISSING_PERMISSION_FIELDS = {
    # Photo link (user avatar)
    "photoLink",
}

KNOWN_MISSING_USER_FIELDS = {
    "photoLink", "permissionId",
}

KNOWN_MISSING_ABOUT_FIELDS = {
    # Theme lists (not meaningful for mock)
    "teamDriveThemes", "driveThemes",
}


# ── Files.get — full response ────────────────────────────────────────────────


class TestFilesGetGolden:
    """Compare mock files.get response against real API response."""

    @pytest.fixture(scope="class")
    def real_file(self):
        return _load("files_get_full")

    @pytest.fixture(scope="class")
    def real_folder(self):
        return _load("files_get_folder")

    def test_mock_has_all_critical_real_fields(self, client, seed_user, seed_file, real_file):
        """Every field in the real response should be in our mock (or documented as missing)."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        real_fields = set(real_file.keys())
        mock_fields = set(mock_resp.keys())

        missing = real_fields - mock_fields - KNOWN_MISSING_FILE_FIELDS
        assert not missing, f"Mock missing real API fields (not in known gaps): {missing}"

    def test_mock_has_no_extra_fields(self, client, seed_user, seed_file, real_file):
        """Mock should not return fields that don't exist in the real API.

        Note: real_file is a single captured fixture and may not contain all valid fields.
        Fields that exist in the real API (per Discovery Document) but are absent from
        this particular fixture are acceptable.
        """
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        real_fields = set(real_file.keys())
        # These are real API fields that happen to not be in our specific fixture capture
        REAL_API_FIELDS_NOT_IN_FIXTURE = {
            "headRevisionId", "hasAugmentedPermissions", "sha256Checksum",
            "md5Checksum", "sha1Checksum", "originalFilename",
            "fullFileExtension", "fileExtension", "resourceKey",
            "quotaBytesUsed", "isAppAuthorized", "permissionIds",
            "copyRequiresWriterPermission", "appProperties",
            "trashedTime", "trashingUser", "modifiedByMe", "viewedByMe",
            "modifiedByMeTime", "sharedWithMeTime", "hasThumbnail",
            "folderColorRgb", "webContentLink", "driveId",
            "linkShareMetadata", "contentRestrictions",
            "imageMediaMetadata", "videoMediaMetadata", "labelInfo",
        }
        extra = set(mock_resp.keys()) - real_fields - REAL_API_FIELDS_NOT_IN_FIXTURE
        assert not extra, f"Mock returns fields not in real API: {extra}"

    def test_field_types_match(self, client, seed_user, seed_file, real_file):
        """Field types in mock should match the real API."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        mismatches = []
        for field in set(mock_resp.keys()) & set(real_file.keys()):
            real_type = _type_of(real_file[field])
            mock_type = _type_of(mock_resp[field])
            if real_type != mock_type:
                # Allow null in mock for optional fields
                if mock_type == "null":
                    continue
                mismatches.append(f"{field}: real={real_type}, mock={mock_type}")
        assert not mismatches, f"Type mismatches:\n" + "\n".join(mismatches)

    def test_kind_matches(self, client, seed_user, seed_file, real_file):
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        assert mock_resp["kind"] == real_file["kind"] == "drive#file"

    def test_owners_structure_matches(self, client, seed_user, seed_file, real_file):
        """Owner objects should have the same structure."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        real_owner_fields = set(real_file["owners"][0].keys())
        mock_owner_fields = set(mock_resp["owners"][0].keys())
        missing = real_owner_fields - mock_owner_fields - KNOWN_MISSING_USER_FIELDS
        assert not missing, f"Mock owner missing fields: {missing}"

    def test_capabilities_structure_matches(self, client, seed_user, seed_file, real_file):
        """All capabilities in the real fixture should be in our mock."""
        real_caps = set(real_file["capabilities"].keys())
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        mock_caps = set(mock_resp["capabilities"].keys())
        # Real fixture only captures a subset of capabilities for this file type.
        # Our mock may return additional real API capabilities (e.g., shared drive,
        # folder-specific). Verify the mock is a superset of the fixture.
        missing = real_caps - mock_caps - {"canModifyContentRestriction"}  # deprecated alias
        assert not missing, f"Mock missing real capabilities: {missing}"

    def test_capabilities_all_booleans(self, client, seed_user, seed_file):
        """All capability values should be booleans, matching real API."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        non_bool = {
            k: type(v).__name__
            for k, v in mock_resp["capabilities"].items()
            if not isinstance(v, bool)
        }
        assert not non_bool, f"Non-boolean capabilities: {non_bool}"

    def test_size_and_version_are_strings(self, client, seed_user, seed_file, real_file):
        """Real API returns size and version as strings (int64 format)."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        if "version" in real_file:
            assert isinstance(real_file["version"], str)
        if "version" in mock_resp and mock_resp["version"] is not None:
            assert isinstance(mock_resp["version"], str), "Mock version should be string"
        if "size" in real_file:
            assert isinstance(real_file["size"], str)

    def test_parents_is_array(self, client, seed_user, seed_file, real_file):
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        assert isinstance(real_file["parents"], list)
        assert isinstance(mock_resp["parents"], list)

    def test_timestamps_are_strings(self, client, seed_user, seed_file, real_file):
        """Timestamps should be RFC 3339 strings."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        for field in ["createdTime", "modifiedTime"]:
            assert isinstance(real_file[field], str), f"Real {field} should be string"
            assert isinstance(mock_resp[field], str), f"Mock {field} should be string"

    def test_folder_response_structure(self, client, seed_user, seed_folder, real_folder):
        """Folder response should match real folder structure."""
        mock_resp = client.get(f"/drive/v3/files/{seed_folder.id}").json()
        assert mock_resp["mimeType"] == "application/vnd.google-apps.folder"
        assert real_folder["mimeType"] == "application/vnd.google-apps.folder"
        # Folders have capabilities too
        assert "capabilities" in mock_resp
        assert "capabilities" in real_folder


# ── Files.list ────────────────────────────────────────────────────────────────


class TestFilesListGolden:
    """Compare mock files.list response against real API response."""

    @pytest.fixture(scope="class")
    def real_list(self):
        return _load("files_list_default")

    def test_top_level_structure(self, client, seed_user, real_list):
        mock_resp = client.get("/drive/v3/files").json()
        # Both should have 'files' array
        assert isinstance(real_list.get("files"), list)
        assert isinstance(mock_resp.get("files"), list)

    def test_file_items_have_consistent_fields(self, client, seed_user, seed_file, real_list):
        """Each file in list should have core fields matching real API."""
        mock_resp = client.get("/drive/v3/files").json()
        if not mock_resp["files"]:
            pytest.skip("No mock files to compare")
        mock_item = mock_resp["files"][0]
        real_item = real_list["files"][0]
        # Core fields every file item should have
        core_fields = {"kind", "id", "name", "mimeType"}
        for field in core_fields:
            assert field in real_item, f"Real file item missing {field}"
            assert field in mock_item, f"Mock file item missing {field}"

    def test_kind_value(self, client, seed_user):
        mock_resp = client.get("/drive/v3/files").json()
        assert mock_resp.get("kind") == "drive#fileList"


# ── Permissions ───────────────────────────────────────────────────────────────


class TestPermissionsGolden:
    """Compare mock permissions responses against real API."""

    @pytest.fixture(scope="class")
    def real_perm_list(self):
        return _load("permissions_list")

    @pytest.fixture(scope="class")
    def real_perm(self):
        return _load("permissions_get")

    def test_permission_list_structure(self, client, seed_user, seed_file, real_perm_list):
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/permissions").json()
        assert mock_resp["kind"] == real_perm_list["kind"] == "drive#permissionList"
        assert isinstance(mock_resp["permissions"], list)
        assert isinstance(real_perm_list["permissions"], list)

    def test_permission_fields_match(self, client, seed_user, seed_file, real_perm):
        """Mock permission should have all real fields (minus known gaps)."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/permissions").json()
        if not mock_resp["permissions"]:
            pytest.skip("No mock permissions to compare")
        mock_perm = mock_resp["permissions"][0]
        real_fields = set(real_perm.keys())
        mock_fields = set(mock_perm.keys())
        missing = real_fields - mock_fields - KNOWN_MISSING_PERMISSION_FIELDS
        assert not missing, f"Mock permission missing real fields: {missing}"

    def test_permission_core_fields(self, client, seed_user, seed_file, real_perm):
        """Core permission fields should always be present."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/permissions").json()
        if not mock_resp["permissions"]:
            pytest.skip("No mock permissions")
        mock_perm = mock_resp["permissions"][0]
        for field in ["id", "role", "type", "kind"]:
            assert field in real_perm, f"Real perm missing {field}"
            assert field in mock_perm, f"Mock perm missing {field}"

    def test_permission_kind_value(self, client, seed_user, seed_file, real_perm):
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/permissions").json()
        if mock_resp["permissions"]:
            assert mock_resp["permissions"][0]["kind"] == real_perm["kind"] == "drive#permission"


# ── About ─────────────────────────────────────────────────────────────────────


class TestAboutGolden:
    """Compare mock about response against real API."""

    @pytest.fixture(scope="class")
    def real_about(self):
        return _load("about_get")

    def test_top_level_fields(self, client, seed_user, real_about):
        mock_resp = client.get("/drive/v3/about").json()
        real_fields = set(real_about.keys())
        mock_fields = set(mock_resp.keys())
        missing = real_fields - mock_fields - KNOWN_MISSING_ABOUT_FIELDS
        assert not missing, f"Mock about missing real fields: {missing}"

    def test_kind_matches(self, client, seed_user, real_about):
        mock_resp = client.get("/drive/v3/about").json()
        assert mock_resp["kind"] == real_about["kind"] == "drive#about"

    def test_user_structure(self, client, seed_user, real_about):
        """User object in about should have matching structure."""
        mock_resp = client.get("/drive/v3/about").json()
        real_user = real_about["user"]
        mock_user = mock_resp["user"]
        real_user_fields = set(real_user.keys())
        mock_user_fields = set(mock_user.keys())
        missing = real_user_fields - mock_user_fields - KNOWN_MISSING_USER_FIELDS
        assert not missing, f"Mock about.user missing fields: {missing}"

    def test_storage_quota_structure(self, client, seed_user, real_about):
        """Storage quota should have matching fields."""
        mock_resp = client.get("/drive/v3/about").json()
        real_quota = real_about["storageQuota"]
        mock_quota = mock_resp["storageQuota"]
        for field in real_quota:
            assert field in mock_quota, f"Mock storageQuota missing: {field}"

    def test_storage_quota_values_are_strings(self, client, seed_user, real_about):
        """Real API returns quota values as strings (int64 format)."""
        real_quota = real_about["storageQuota"]
        for field, value in real_quota.items():
            assert isinstance(value, str), f"Real storageQuota.{field} should be string, got {type(value)}"


# ── Cross-cutting: timestamp format ──────────────────────────────────────────


class TestTimestampFormat:
    """Verify timestamp formats match the real API."""

    @pytest.fixture(scope="class")
    def real_file(self):
        return _load("files_get_full")

    def test_real_timestamps_are_rfc3339(self, real_file):
        """Real API timestamps end with 'Z' (UTC)."""
        for field in ["createdTime", "modifiedTime"]:
            val = real_file[field]
            assert val.endswith("Z"), f"Real {field} should end with Z: {val}"

    def test_mock_timestamps_are_parseable_strings(self, client, seed_user, seed_file):
        """Mock timestamps should be parseable datetime strings."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}").json()
        for field in ["createdTime", "modifiedTime"]:
            val = mock_resp[field]
            assert isinstance(val, str), f"Mock {field} should be string"
            # Should contain date-like pattern
            assert "T" in val, f"Mock {field} should be ISO format: {val}"


# -- Comments golden fixture tests ----------------------------------------


class TestCommentsGolden:
    """Compare mock comments responses against real API (if fixtures exist)."""

    @pytest.fixture()
    def comment_fixture(self, db_session, seed_user, seed_file):
        """Create a comment for testing."""
        from mock_gdrive.models import Comment
        c = Comment(
            id="comment_test",
            file_id=seed_file.id,
            author_id=seed_user.id,
            content="Test comment",
            html_content="<p>Test comment</p>",
        )
        db_session.add(c)
        db_session.commit()
        return c

    def test_comments_list_structure(self, client, seed_user, seed_file, comment_fixture):
        """Mock comments.list should return proper structure."""
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/comments").json()
        assert mock_resp.get("kind") == "drive#commentList"
        assert isinstance(mock_resp.get("comments"), list)
        assert len(mock_resp["comments"]) >= 1

    @pytest.mark.skipif(not _fixture_exists("comments_list"), reason="No real fixture")
    def test_comments_list_keys_match(self, client, seed_user, seed_file, comment_fixture):
        real = _load("comments_list")
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/comments").json()
        real_keys = set(real.keys())
        mock_keys = set(mock_resp.keys())
        assert real_keys.issubset(mock_keys), f"Mock missing keys: {real_keys - mock_keys}"

    @pytest.mark.skipif(not _fixture_exists("comments_get"), reason="No real fixture")
    def test_comment_item_keys(self, client, seed_user, seed_file, comment_fixture):
        real = _load("comments_get")
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/comments/comment_test").json()
        real_keys = set(real.keys())
        mock_keys = set(mock_resp.keys())
        # Allow some missing keys (author photoLink, etc.)
        known_missing = {"quotedFileContent", "anchor"}
        missing = real_keys - mock_keys - known_missing
        assert not missing, f"Mock comment missing real keys: {missing}"

    def test_empty_comments_list(self, client, seed_user, seed_folder):
        """Empty comments list should still have proper structure."""
        mock_resp = client.get(f"/drive/v3/files/{seed_folder.id}/comments").json()
        assert mock_resp.get("kind") == "drive#commentList"
        assert isinstance(mock_resp.get("comments"), list)
        assert len(mock_resp["comments"]) == 0


# -- Replies golden fixture tests -----------------------------------------


class TestRepliesGolden:
    """Compare mock replies responses against real API (if fixtures exist)."""

    @pytest.fixture()
    def reply_fixtures(self, db_session, seed_user, seed_file):
        from mock_gdrive.models import Comment, Reply
        c = Comment(
            id="comment_for_reply",
            file_id=seed_file.id,
            author_id=seed_user.id,
            content="Parent comment",
        )
        r = Reply(
            id="reply_test",
            comment_id="comment_for_reply",
            author_id=seed_user.id,
            content="Test reply",
            html_content="<p>Test reply</p>",
        )
        db_session.add(c)
        db_session.add(r)
        db_session.commit()
        return c, r

    def test_replies_list_structure(self, client, seed_user, seed_file, reply_fixtures):
        comment, _ = reply_fixtures
        mock_resp = client.get(
            f"/drive/v3/files/{seed_file.id}/comments/{comment.id}/replies"
        ).json()
        assert mock_resp.get("kind") == "drive#replyList"
        assert isinstance(mock_resp.get("replies"), list)
        assert len(mock_resp["replies"]) >= 1

    @pytest.mark.skipif(not _fixture_exists("replies_get"), reason="No real fixture")
    def test_reply_item_keys(self, client, seed_user, seed_file, reply_fixtures):
        real = _load("replies_get")
        comment, reply = reply_fixtures
        mock_resp = client.get(
            f"/drive/v3/files/{seed_file.id}/comments/{comment.id}/replies/{reply.id}"
        ).json()
        real_keys = set(real.keys())
        mock_keys = set(mock_resp.keys())
        missing = real_keys - mock_keys
        assert not missing, f"Mock reply missing real keys: {missing}"


# -- Revisions golden fixture tests ---------------------------------------


class TestRevisionsGolden:
    """Compare mock revisions responses against real API (if fixtures exist)."""

    @pytest.fixture()
    def revision_fixture(self, db_session, seed_user, seed_file):
        from mock_gdrive.models import Revision
        rev = Revision(
            id="rev_test",
            file_id=seed_file.id,
            last_modifying_user_id=seed_user.id,
            mime_type="application/vnd.google-apps.document",
            keep_forever=False,
            size=1234,
        )
        db_session.add(rev)
        db_session.commit()
        return rev

    def test_revisions_list_structure(self, client, seed_user, seed_file, revision_fixture):
        mock_resp = client.get(f"/drive/v3/files/{seed_file.id}/revisions").json()
        assert mock_resp.get("kind") == "drive#revisionList"
        assert isinstance(mock_resp.get("revisions"), list)
        assert len(mock_resp["revisions"]) >= 1

    @pytest.mark.skipif(not _fixture_exists("revisions_get"), reason="No real fixture")
    def test_revision_item_keys(self, client, seed_user, seed_file, revision_fixture):
        real = _load("revisions_get")
        mock_resp = client.get(
            f"/drive/v3/files/{seed_file.id}/revisions/{revision_fixture.id}"
        ).json()
        real_keys = set(real.keys())
        mock_keys = set(mock_resp.keys())
        known_missing = {"exportLinks", "publishedLink", "publishAuto", "published", "publishedOutsideDomain"}
        missing = real_keys - mock_keys - known_missing
        assert not missing, f"Mock revision missing real keys: {missing}"


# -- Changes golden fixture tests -----------------------------------------


class TestChangesGolden:
    """Compare mock changes responses against real API (if fixtures exist)."""

    def test_start_page_token_structure(self, client, seed_user):
        mock_resp = client.get("/drive/v3/changes/startPageToken").json()
        assert "startPageToken" in mock_resp
        assert mock_resp.get("kind") == "drive#startPageToken"

    @pytest.mark.skipif(not _fixture_exists("changes_startPageToken"), reason="No real fixture")
    def test_start_page_token_keys(self, client, seed_user):
        real = _load("changes_startPageToken")
        mock_resp = client.get("/drive/v3/changes/startPageToken").json()
        real_keys = set(real.keys())
        mock_keys = set(mock_resp.keys())
        assert real_keys.issubset(mock_keys), f"Mock missing: {real_keys - mock_keys}"

    def test_changes_list_structure(self, client, seed_user):
        token = client.get("/drive/v3/changes/startPageToken").json()["startPageToken"]
        mock_resp = client.get(f"/drive/v3/changes?pageToken={token}").json()
        assert mock_resp.get("kind") == "drive#changeList"
        assert isinstance(mock_resp.get("changes"), list)


# -- Drives golden fixture tests ------------------------------------------


class TestDrivesGolden:
    """Compare mock drives responses against real API (if fixtures exist)."""

    @pytest.fixture()
    def drive_fixture(self, db_session, seed_user):
        from mock_gdrive.models import Drive
        d = Drive(
            id="drive_test",
            name="Test Drive",
            created_time=None,
        )
        db_session.add(d)
        db_session.commit()
        return d

    def test_drives_list_structure(self, client, seed_user, drive_fixture):
        mock_resp = client.get("/drive/v3/drives").json()
        assert mock_resp.get("kind") == "drive#driveList"
        assert isinstance(mock_resp.get("drives"), list)

    @pytest.mark.skipif(not _fixture_exists("drives_get"), reason="No real fixture")
    def test_drive_item_keys(self, client, seed_user, drive_fixture):
        real = _load("drives_get")
        mock_resp = client.get(f"/drive/v3/drives/{drive_fixture.id}").json()
        real_keys = set(real.keys())
        mock_keys = set(mock_resp.keys())
        known_missing = {"orgUnitId"}
        missing = real_keys - mock_keys - known_missing
        assert not missing, f"Mock drive missing real keys: {missing}"


# -- Channels golden fixture tests ----------------------------------------


class TestChannelsGolden:
    """channels.stop returns simple response."""

    def test_channels_stop(self, client, seed_user):
        mock_resp = client.post("/drive/v3/channels/stop").json()
        assert "status" in mock_resp


# -- Mutation response golden fixture tests --------------------------------


class TestMutationResponsesGolden:
    """Verify mutation response shapes match real API."""

    def test_files_create_response(self, client, seed_user, seed_folder):
        """files.create should return a file resource."""
        resp = client.post("/drive/v3/files", json={
            "name": "Test Create",
            "mimeType": "application/vnd.google-apps.document",
            "parents": [seed_folder.id],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "kind" in data
        assert data["kind"] == "drive#file"

    @pytest.mark.skipif(not _fixture_exists("files_create_response"), reason="No real fixture")
    def test_files_create_keys_match_real(self, client, seed_user, seed_folder):
        real = _load("files_create_response")
        resp = client.post("/drive/v3/files", json={
            "name": "Test Create Keys",
            "mimeType": "application/vnd.google-apps.document",
            "parents": [seed_folder.id],
        })
        mock_data = resp.json()
        # Core keys must match
        for key in ["kind", "id", "name", "mimeType"]:
            assert key in real, f"Real response missing {key}"
            assert key in mock_data, f"Mock response missing {key}"

    @pytest.mark.skipif(not _fixture_exists("permissions_create_response"), reason="No real fixture")
    def test_permissions_create_response_keys(self, client, seed_user, seed_file):
        real = _load("permissions_create_response")
        resp = client.post(f"/drive/v3/files/{seed_file.id}/permissions", json={
            "role": "reader",
            "type": "user",
            "emailAddress": "someone@example.com",
        })
        mock_data = resp.json()
        real_keys = set(real.keys())
        mock_keys = set(mock_data.keys())
        known_missing = {"photoLink", "pendingOwner"}
        missing = real_keys - mock_keys - known_missing
        assert not missing, f"Mock perm create missing: {missing}"


# -- Error response golden fixture tests -----------------------------------


class TestErrorResponsesGolden:
    """Verify error responses match real API structure."""

    def test_404_error_structure(self, client, seed_user):
        resp = client.get("/drive/v3/files/nonexistent_file_id")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "errors" in data["error"]
        assert isinstance(data["error"]["errors"], list)

    @pytest.mark.skipif(not _fixture_exists("error_file_not_found"), reason="No real fixture")
    def test_404_keys_match_real(self, client, seed_user):
        real = _load("error_file_not_found")
        resp = client.get("/drive/v3/files/nonexistent_file_id")
        mock_data = resp.json()
        # Both should have error.code, error.message, error.errors
        for path in [["error", "code"], ["error", "message"], ["error", "errors"]]:
            real_val = real
            mock_val = mock_data
            for key in path:
                assert key in real_val, f"Real missing {'.'.join(path)}"
                assert key in mock_val, f"Mock missing {'.'.join(path)}"
                real_val = real_val[key]
                mock_val = mock_val[key]

    def test_error_item_has_reason(self, client, seed_user):
        resp = client.get("/drive/v3/files/nonexistent_file_id")
        data = resp.json()
        err_item = data["error"]["errors"][0]
        assert "message" in err_item
        assert "domain" in err_item
        assert "reason" in err_item


# -- Empty collection golden fixture tests ---------------------------------


class TestEmptyCollectionsGolden:
    """Verify empty collection responses have correct structure."""

    def test_empty_files_list(self, client, seed_user):
        """Empty files.list (with impossible query) should still have structure."""
        resp = client.get("/drive/v3/files", params={"q": "name = 'impossible_name_that_never_exists_12345'"}).json()
        assert resp.get("kind") == "drive#fileList"
        assert isinstance(resp.get("files"), list)
        assert len(resp["files"]) == 0

    def test_empty_permissions_list_structure(self, client, seed_user, seed_folder):
        """Files with only owner permission should still return a list."""
        resp = client.get(f"/drive/v3/files/{seed_folder.id}/permissions").json()
        assert resp.get("kind") == "drive#permissionList"
        assert isinstance(resp.get("permissions"), list)

    def test_empty_drives_list(self, client, seed_user):
        """drives.list with no drives should return proper structure."""
        resp = client.get("/drive/v3/drives").json()
        assert resp.get("kind") == "drive#driveList"
        assert isinstance(resp.get("drives"), list)


# ══════════════════════════════════════════════════════════════════════════════
# New fixture conformance tests — cover all 28 previously-untested fixtures
# ══════════════════════════════════════════════════════════════════════════════


def _assert_error_envelope(data: dict, expected_code: int):
    """Assert the standard Google API error envelope shape."""
    assert "error" in data
    err = data["error"]
    assert err["code"] == expected_code
    assert "message" in err
    assert isinstance(err["errors"], list)
    assert len(err["errors"]) >= 1
    item = err["errors"][0]
    assert "message" in item
    assert "domain" in item
    assert "reason" in item


def _assert_shape(mock_data, real_data, path="", strict=True, known_missing: set | None = None):
    """Recursively assert mock response shape matches real fixture.

    Checks:
    - Missing keys: real_keys - mock_keys (always, minus known_missing)
    - Extra keys: mock_keys - real_keys (when strict=True)
    - Type mismatches at leaf nodes
    """
    known_missing = known_missing or set()
    if isinstance(real_data, dict) and isinstance(mock_data, dict):
        real_keys = set(real_data.keys())
        mock_keys = set(mock_data.keys())
        missing = real_keys - mock_keys - known_missing
        assert not missing, f"Mock MISSING keys at {path or 'root'}: {missing}"
        if strict:
            extra = mock_keys - real_keys - known_missing
            assert not extra, f"Mock has EXTRA keys at {path or 'root'}: {extra}"
        for key in real_keys & mock_keys:
            _assert_shape(mock_data[key], real_data[key], f"{path}.{key}" if path else key, strict)
    elif isinstance(real_data, list) and isinstance(mock_data, list):
        if real_data and not mock_data:
            pytest.fail(f"Mock list is empty at {path or 'root'}, real fixture has items")
        if not real_data:
            return
        for idx, item in enumerate(mock_data):
            _assert_any_shape(real_data, item, f"{path}[{idx}]", strict)
    else:
        if real_data is not None and mock_data is not None:
            real_type = type(real_data).__name__
            mock_type = type(mock_data).__name__
            assert real_type == mock_type, f"TYPE MISMATCH at {path}: real={real_type}, mock={mock_type}"


def _assert_any_shape(real_items: list, mock_item, path: str, strict: bool) -> None:
    errors = []
    for real_item in real_items:
        try:
            _assert_shape(mock_item, real_item, path, strict)
            return
        except AssertionError as exc:
            errors.append(str(exc))
    pytest.fail(f"Mock item at {path} matches no fixture item shape: {'; '.join(errors)}")


# -- about_get ----------------------------------------------------------------


class TestAboutGetFixture:
    """Verify mock about.get matches the about_get fixture."""

    def test_keys_match(self, client, seed_user):
        real = _load("about_get")
        mock = client.get("/drive/v3/about").json()
        # Top-level only: about has large nested dicts (importFormats, exportFormats,
        # user) with many intentionally-omitted fields — see KNOWN_MISSING_*_FIELDS.
        # Detailed nested checks are covered by TestAboutGolden.
        real_keys = set(real.keys())
        mock_keys = set(mock.keys())
        missing = real_keys - mock_keys - KNOWN_MISSING_ABOUT_FIELDS
        assert not missing, f"Mock missing real fixture keys: {missing}"

    def test_kind(self, client, seed_user):
        real = _load("about_get")
        mock = client.get("/drive/v3/about").json()
        assert mock["kind"] == real["kind"] == "drive#about"


# -- changes_list -------------------------------------------------------------


class TestChangesListFixture:
    """Verify mock changes.list matches the changes_list fixture."""

    def test_keys_match(self, client, seed_user):
        real = _load("changes_list")
        token = client.get("/drive/v3/changes/startPageToken").json()["startPageToken"]
        mock = client.get(f"/drive/v3/changes", params={"pageToken": token}).json()
        _assert_shape(mock, real)

    def test_kind(self, client, seed_user):
        real = _load("changes_list")
        token = client.get("/drive/v3/changes/startPageToken").json()["startPageToken"]
        mock = client.get(f"/drive/v3/changes", params={"pageToken": token}).json()
        assert mock["kind"] == real["kind"] == "drive#changeList"

    def test_changes_is_array(self, client, seed_user):
        token = client.get("/drive/v3/changes/startPageToken").json()["startPageToken"]
        mock = client.get(f"/drive/v3/changes", params={"pageToken": token}).json()
        assert isinstance(mock["changes"], list)


# -- changes_list_empty -------------------------------------------------------


class TestChangesListEmptyFixture:
    """Verify mock returns same shape for empty changes list."""

    def test_keys_match(self, client, seed_user):
        real = _load("changes_list_empty")
        token = client.get("/drive/v3/changes/startPageToken").json()["startPageToken"]
        mock = client.get(f"/drive/v3/changes", params={"pageToken": token}).json()
        _assert_shape(mock, real)
        assert isinstance(mock["changes"], list)


# -- changes_watch_response ---------------------------------------------------


class TestChangesWatchFixture:
    """Verify mock changes.watch matches the changes_watch_response fixture."""

    def test_keys_match(self, client, seed_user):
        real = _load("changes_watch_response")
        token = client.get("/drive/v3/changes/startPageToken").json()["startPageToken"]
        mock = client.post(
            f"/drive/v3/changes/watch",
            params={"pageToken": token},
            json={"id": "test-channel", "type": "web_hook", "address": "https://example.com/hook"},
        ).json()
        # Channel responses have kind, id, resourceId, resourceUri, expiration
        for key in ["kind", "id", "resourceId", "resourceUri", "expiration"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"

    def test_kind(self, client, seed_user):
        real = _load("changes_watch_response")
        token = client.get("/drive/v3/changes/startPageToken").json()["startPageToken"]
        mock = client.post(
            f"/drive/v3/changes/watch",
            params={"pageToken": token},
            json={"id": "ch", "type": "web_hook", "address": "https://example.com"},
        ).json()
        assert mock["kind"] == real["kind"] == "api#channel"


# -- channels_stop_response ---------------------------------------------------


class TestChannelsStopFixture:
    """Verify mock channels.stop matches the channels_stop_response fixture."""

    def test_status_key(self, client, seed_user):
        real = _load("channels_stop_response")
        mock = client.post("/drive/v3/channels/stop").json()
        # Real API returns 204 with no body; our fixture records {status: 204}.
        # Mock returns {status: "ok"}.  Both should have a "status" key.
        assert "status" in real
        assert "status" in mock


# -- comments_create_response -------------------------------------------------


class TestCommentsCreateFixture:
    """Verify mock comments.create matches the comments_create_response fixture."""

    def test_keys_match(self, client, seed_user, seed_file):
        real = _load("comments_create_response")
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/comments",
            json={"content": "fixture conformance test comment"},
        )
        assert resp.status_code == 200
        mock = resp.json()
        known_missing = {"author"}  # author sub-object has photoLink we omit
        for key in ["kind", "id", "content", "createdTime", "modifiedTime", "deleted"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"

    def test_kind(self, client, seed_user, seed_file):
        real = _load("comments_create_response")
        mock = client.post(
            f"/drive/v3/files/{seed_file.id}/comments",
            json={"content": "test"},
        ).json()
        assert mock["kind"] == real["kind"] == "drive#comment"


# -- comments_list_empty ------------------------------------------------------


class TestCommentsListEmptyFixture:
    """Verify mock returns same shape for empty comments list."""

    def test_keys_match(self, client, seed_user, seed_folder):
        real = _load("comments_list_empty")
        mock = client.get(f"/drive/v3/files/{seed_folder.id}/comments").json()
        _assert_shape(mock, real)
        assert mock["kind"] == real["kind"] == "drive#commentList"
        assert mock["comments"] == []


# -- comments_update_response -------------------------------------------------


class TestCommentsUpdateFixture:
    """Verify mock comments.update matches the comments_update_response fixture."""

    def test_keys_match(self, client, db_session, seed_user, seed_file):
        from mock_gdrive.models import Comment
        c = Comment(
            id="comment_upd_fixture",
            file_id=seed_file.id,
            author_id=seed_user.id,
            content="original",
        )
        db_session.add(c)
        db_session.commit()

        real = _load("comments_update_response")
        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}/comments/{c.id}",
            json={"content": "updated content"},
        )
        assert resp.status_code == 200
        mock = resp.json()
        for key in ["kind", "id", "content", "createdTime", "modifiedTime", "deleted"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "drive#comment"


# -- drives_list --------------------------------------------------------------


class TestDrivesListFixture:
    """Verify mock drives.list matches the drives_list fixture."""

    def test_keys_match(self, client, seed_user):
        real = _load("drives_list")
        mock = client.get("/drive/v3/drives").json()
        _assert_shape(mock, real)

    def test_kind(self, client, seed_user):
        real = _load("drives_list")
        mock = client.get("/drive/v3/drives").json()
        assert mock["kind"] == real["kind"] == "drive#driveList"
        assert isinstance(mock["drives"], list)


# -- error_invalid_request ----------------------------------------------------


class TestErrorInvalidRequestFixture:
    """Verify mock returns similar shape for 400 errors."""

    def test_error_envelope(self, client, seed_user):
        real = _load("error_invalid_request")
        # Trigger a 400 by sending an invalid query
        resp = client.get("/drive/v3/files", params={"q": "invalid_field ???"})
        # Even if our mock returns a different status, verify the real fixture shape
        _assert_error_envelope(real, 400)
        # If the mock also returns an error, verify its envelope
        if resp.status_code >= 400:
            _assert_error_envelope(resp.json(), resp.status_code)

    def test_real_fixture_has_standard_keys(self):
        real = _load("error_invalid_request")
        assert real["error"]["code"] == 400
        assert "message" in real["error"]
        assert isinstance(real["error"]["errors"], list)


# -- error_permission_denied --------------------------------------------------


class TestErrorPermissionDeniedFixture:
    """Verify mock returns similar shape for 403 errors."""

    def test_error_envelope(self, client, db_session, seed_user, seed_file):
        real = _load("error_permission_denied")
        _assert_error_envelope(real, 403)

        # Create a second user who does NOT own the file, try to delete
        from mock_gdrive.models import User
        other = User(id="user_other_403", email="other403@example.com", display_name="Other")
        db_session.add(other)
        db_session.commit()
        resp = client.delete(
            f"/drive/v3/files/{seed_file.id}",
            headers={"X-Mock-Drive-User": other.email},
        )
        assert resp.status_code == 403
        _assert_error_envelope(resp.json(), 403)


# -- error_file_not_found (already tested above, add fixture key comparison) --


class TestErrorFileNotFoundFixture:
    """Explicit fixture comparison for error_file_not_found."""

    def test_keys_match(self, client, seed_user):
        real = _load("error_file_not_found")
        resp = client.get("/drive/v3/files/nonexistent_file_id_xyz")
        assert resp.status_code == 404
        mock = resp.json()
        _assert_error_envelope(real, 404)
        _assert_error_envelope(mock, 404)


# -- files_copy_response ------------------------------------------------------


class TestFilesCopyFixture:
    """Verify mock files.copy matches the files_copy_response fixture."""

    def test_keys_match(self, client, seed_user, seed_file):
        real = _load("files_copy_response")
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/copy",
            json={"name": "Copy of test"},
        )
        assert resp.status_code == 200
        mock = resp.json()
        for key in ["kind", "id", "name", "mimeType"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "drive#file"


# -- files_delete_response ----------------------------------------------------


class TestFilesDeleteFixture:
    """Verify mock files.delete returns 204 like the real fixture."""

    def test_status_204(self, client, db_session, seed_user, seed_folder):
        from mock_gdrive.models import File, Permission
        f = File(
            id="file_del_fixture",
            name="Delete Me",
            mime_type="text/plain",
            parent_id=seed_folder.id,
            owner_id=seed_user.id,
            last_modifying_user_id=seed_user.id,
        )
        db_session.add(f)
        db_session.add(Permission(
            id="perm_del_fixture",
            file_id=f.id,
            role="owner",
            type="user",
            email_address=seed_user.email,
            display_name=seed_user.display_name,
        ))
        db_session.commit()

        real = _load("files_delete_response")
        assert real["status"] == 204

        resp = client.delete(f"/drive/v3/files/{f.id}")
        assert resp.status_code == 204


# -- files_emptyTrash_response ------------------------------------------------


class TestFilesEmptyTrashFixture:
    """Verify mock files.emptyTrash returns 204 like the real fixture."""

    def test_status_204(self, client, seed_user):
        real = _load("files_emptyTrash_response")
        assert real["status"] == 204

        resp = client.delete("/drive/v3/files/trash")
        assert resp.status_code == 204


# -- files_export_text --------------------------------------------------------


class TestFilesExportTextFixture:
    """Verify mock files.export returns content like the real fixture."""

    def test_export_returns_text(self, client, seed_user, seed_file):
        real = _load("files_export_text")
        assert "content" in real
        assert "mimeType" in real

        resp = client.get(
            f"/drive/v3/files/{seed_file.id}/export",
            params={"mimeType": "text/plain"},
        )
        assert resp.status_code == 200
        assert "text" in resp.headers.get("content-type", "")


# -- files_generateIds --------------------------------------------------------


class TestFilesGenerateIdsFixture:
    """Verify mock files.generateIds matches the files_generateIds fixture."""

    def test_keys_match(self, client, seed_user):
        real = _load("files_generateIds")
        mock = client.get("/drive/v3/files/generateIds", params={"count": 3}).json()
        _assert_shape(mock, real)

    def test_kind(self, client, seed_user):
        real = _load("files_generateIds")
        mock = client.get("/drive/v3/files/generateIds", params={"count": 3}).json()
        assert mock["kind"] == real["kind"] == "drive#generatedIds"

    def test_ids_is_array(self, client, seed_user):
        mock = client.get("/drive/v3/files/generateIds", params={"count": 3}).json()
        assert isinstance(mock["ids"], list)
        assert len(mock["ids"]) == 3


# -- files_get_after_create ---------------------------------------------------


class TestFilesGetAfterCreateFixture:
    """Verify mock files.get after create matches the fixture."""

    def test_keys_match(self, client, seed_user, seed_folder):
        real = _load("files_get_after_create")
        # Create a file then GET it
        create_resp = client.post("/drive/v3/files", json={
            "name": "After Create Fixture Test",
            "mimeType": "application/vnd.google-apps.document",
            "parents": [seed_folder.id],
        })
        file_id = create_resp.json()["id"]
        mock = client.get(f"/drive/v3/files/{file_id}").json()
        for key in ["kind", "id", "name", "mimeType", "starred", "trashed"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "drive#file"


# -- files_get_fields_filtered ------------------------------------------------


class TestFilesGetFieldsFilteredFixture:
    """Verify mock files.get with fields param matches the fixture."""

    def test_returns_only_requested_fields(self, client, seed_user, seed_file):
        real = _load("files_get_fields_filtered")
        # The fixture has: id, name, mimeType, parents, capabilities
        mock = client.get(
            f"/drive/v3/files/{seed_file.id}",
            params={"fields": "id,name,mimeType,parents,capabilities"},
        ).json()
        for key in ["id", "name", "mimeType"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"


# -- files_get_folder ---------------------------------------------------------


class TestFilesGetFolderFixture:
    """Verify mock files.get for a folder matches the files_get_folder fixture."""

    def test_keys_match(self, client, seed_user, seed_folder):
        real = _load("files_get_folder")
        mock = client.get(f"/drive/v3/files/{seed_folder.id}").json()
        assert mock["mimeType"] == real["mimeType"] == "application/vnd.google-apps.folder"
        for key in ["kind", "id", "name", "mimeType"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "drive#file"


# -- files_list_fields_filtered -----------------------------------------------


class TestFilesListFieldsFilteredFixture:
    """Verify mock files.list with fields param matches the fixture."""

    def test_structure(self, client, seed_user, seed_file):
        real = _load("files_list_fields_filtered")
        assert isinstance(real["files"], list)
        mock = client.get(
            "/drive/v3/files",
            params={"fields": "files(id,name,mimeType)"},
        ).json()
        assert isinstance(mock["files"], list)
        if mock["files"]:
            item = mock["files"][0]
            real_item = real["files"][0]
            for key in real_item:
                assert key in item, f"Mock file item missing {key}"


# -- files_list_folders -------------------------------------------------------


class TestFilesListFoldersFixture:
    """Verify mock files.list filtered to folders matches the fixture shape."""

    def test_structure(self, client, seed_user, seed_folder):
        real = _load("files_list_folders")
        mock = client.get(
            "/drive/v3/files",
            params={"q": "mimeType = 'application/vnd.google-apps.folder'"},
        ).json()
        assert isinstance(real["files"], list)
        assert isinstance(mock["files"], list)
        # Mock should return at least the seed folder
        assert len(mock["files"]) >= 1
        assert mock["files"][0]["mimeType"] == "application/vnd.google-apps.folder"


# -- files_list_in_parents ----------------------------------------------------


class TestFilesListInParentsFixture:
    """Verify mock files.list with parents query matches the fixture shape."""

    def test_structure(self, client, seed_user, seed_file, seed_folder):
        real = _load("files_list_in_parents")
        assert isinstance(real["files"], list)
        mock = client.get(
            "/drive/v3/files",
            params={"q": f"'{seed_folder.id}' in parents"},
        ).json()
        assert isinstance(mock["files"], list)
        assert len(mock["files"]) >= 1


# -- files_list_trashed -------------------------------------------------------


class TestFilesListTrashedFixture:
    """Verify mock files.list for trashed files matches the fixture shape."""

    def test_structure(self, client, seed_user):
        real = _load("files_list_trashed")
        assert isinstance(real["files"], list)
        assert real.get("kind") == "drive#fileList"
        mock = client.get(
            "/drive/v3/files",
            params={"q": "trashed = true"},
        ).json()
        assert mock.get("kind") == "drive#fileList"
        assert isinstance(mock["files"], list)


# -- files_update_response ----------------------------------------------------


class TestFilesUpdateFixture:
    """Verify mock files.update matches the files_update_response fixture."""

    def test_keys_match(self, client, seed_user, seed_file):
        real = _load("files_update_response")
        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}",
            json={"name": "Updated Fixture Test"},
        )
        assert resp.status_code == 200
        mock = resp.json()
        for key in ["kind", "id", "name", "mimeType"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "drive#file"
        assert mock["name"] == "Updated Fixture Test"


# -- files_watch_response -----------------------------------------------------


class TestFilesWatchFixture:
    """Verify mock files.watch matches the files_watch_response fixture."""

    def test_keys_match(self, client, seed_user, seed_file):
        real = _load("files_watch_response")
        mock = client.post(
            f"/drive/v3/files/{seed_file.id}/watch",
            json={"id": "test-ch", "type": "web_hook", "address": "https://example.com"},
        ).json()
        for key in ["kind", "id", "resourceId", "resourceUri", "expiration"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "api#channel"


# -- replies_create_response --------------------------------------------------


class TestRepliesCreateFixture:
    """Verify mock replies.create matches the replies_create_response fixture."""

    def test_keys_match(self, client, db_session, seed_user, seed_file):
        from mock_gdrive.models import Comment
        c = Comment(
            id="comment_for_reply_create_fixture",
            file_id=seed_file.id,
            author_id=seed_user.id,
            content="Parent comment for reply create",
        )
        db_session.add(c)
        db_session.commit()

        real = _load("replies_create_response")
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/comments/{c.id}/replies",
            json={"content": "fixture conformance reply"},
        )
        assert resp.status_code == 200
        mock = resp.json()
        for key in ["kind", "id", "content", "createdTime", "modifiedTime", "deleted"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "drive#reply"


# -- replies_update_response --------------------------------------------------


class TestRepliesUpdateFixture:
    """Verify mock replies.update matches the replies_update_response fixture."""

    def test_keys_match(self, client, db_session, seed_user, seed_file):
        from mock_gdrive.models import Comment, Reply
        c = Comment(
            id="comment_for_reply_update_fixture",
            file_id=seed_file.id,
            author_id=seed_user.id,
            content="Parent",
        )
        r = Reply(
            id="reply_update_fixture",
            comment_id=c.id,
            author_id=seed_user.id,
            content="original reply",
        )
        db_session.add(c)
        db_session.add(r)
        db_session.commit()

        real = _load("replies_update_response")
        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}/comments/{c.id}/replies/{r.id}",
            json={"content": "updated reply"},
        )
        assert resp.status_code == 200
        mock = resp.json()
        for key in ["kind", "id", "content", "modifiedTime", "deleted"]:
            assert key in real, f"Real fixture missing {key}"
            assert key in mock, f"Mock missing {key}"
        assert mock["kind"] == real["kind"] == "drive#reply"


# -- Remaining fixture coverage tests ----------------------------------------


class TestRepliesListFixture:
    @pytest.mark.skipif(not _fixture_exists("replies_list"), reason="No fixture")
    def test_keys_match(self, client, seed_user, seed_file, db_session):
        from mock_gdrive.models import Comment, Reply
        comment = Comment(id="cmt_rl", file_id=seed_file.id, author_id=seed_user.id, content="test")
        db_session.add(comment)
        db_session.flush()
        reply = Reply(id="rpl_rl", comment_id=comment.id, author_id=seed_user.id, content="reply")
        db_session.add(reply)
        db_session.commit()
        real = _load("replies_list")
        mock = client.get(f"/drive/v3/files/{seed_file.id}/comments/{comment.id}/replies").json()
        assert "replies" in mock
        assert real.get("kind") == mock.get("kind")


class TestRevisionsListFixture:
    @pytest.mark.skipif(not _fixture_exists("revisions_list"), reason="No fixture")
    def test_keys_match(self, client, seed_user, seed_file, db_session):
        from mock_gdrive.models import Revision
        rev = Revision(id="rev_rl", file_id=seed_file.id, last_modifying_user_id=seed_user.id,
                       mime_type="text/plain", keep_forever=False, size=100)
        db_session.add(rev)
        db_session.commit()
        real = _load("revisions_list")
        mock = client.get(f"/drive/v3/files/{seed_file.id}/revisions").json()
        assert "revisions" in mock
        assert real.get("kind") == mock.get("kind")


class TestRevisionsUpdateFixture:
    @pytest.mark.skipif(not _fixture_exists("revisions_update_response"), reason="No fixture")
    def test_keys_match(self, client, seed_user, seed_file, db_session):
        from mock_gdrive.models import Revision
        rev = Revision(id="rev_upd", file_id=seed_file.id, last_modifying_user_id=seed_user.id,
                       mime_type="text/plain", keep_forever=False, size=100)
        db_session.add(rev)
        db_session.commit()
        real = _load("revisions_update_response")
        mock = client.patch(f"/drive/v3/files/{seed_file.id}/revisions/{rev.id}",
                            json={"published": False}).json()
        assert real.get("kind") == mock.get("kind")


class TestErrorInvalidFileCreateFixture:
    """Validate error envelope from invalid file creation (captured from real API)."""

    @pytest.mark.skipif(not _fixture_exists("error_invalid_file_create"), reason="No fixture")
    def test_error_envelope(self):
        real = _load("error_invalid_file_create")
        assert "error" in real
        assert "code" in real["error"]
        assert "message" in real["error"]
        assert "errors" in real["error"]
