"""Tests for capabilities computation."""

from mock_gdrive.models import User, File, Permission
from mock_gdrive.api.capabilities import compute_capabilities, get_effective_role, user_can_view


class TestEffectiveRole:
    def test_owner_role(self, db_session, seed_user, seed_file):
        role = get_effective_role(seed_file, seed_user, db_session)
        assert role == "owner"

    def test_no_access(self, db_session, seed_users, seed_file):
        bob = seed_users["bob@example.com"]
        role = get_effective_role(seed_file, bob, db_session)
        assert role is None

    def test_direct_permission(self, db_session, seed_users, seed_file):
        bob = seed_users["bob@example.com"]
        db_session.add(Permission(
            id="perm_bob_w", file_id=seed_file.id, role="writer",
            type="user", email_address=bob.email,
        ))
        db_session.commit()
        role = get_effective_role(seed_file, bob, db_session)
        assert role == "writer"

    def test_inherited_from_parent(self, db_session, seed_users, seed_folder, seed_file):
        bob = seed_users["bob@example.com"]
        # Share the parent folder with Bob
        db_session.add(Permission(
            id="perm_bob_folder", file_id=seed_folder.id, role="reader",
            type="user", email_address=bob.email,
        ))
        db_session.commit()
        role = get_effective_role(seed_file, bob, db_session)
        assert role == "reader"

    def test_anyone_permission(self, db_session, seed_users, seed_file):
        bob = seed_users["bob@example.com"]
        db_session.add(Permission(
            id="perm_anyone", file_id=seed_file.id, role="reader",
            type="anyone",
        ))
        db_session.commit()
        role = get_effective_role(seed_file, bob, db_session)
        assert role == "reader"

    def test_highest_role_wins(self, db_session, seed_users, seed_folder, seed_file):
        bob = seed_users["bob@example.com"]
        # Reader on parent, writer on file directly
        db_session.add(Permission(
            id="perm_bob_r", file_id=seed_folder.id, role="reader",
            type="user", email_address=bob.email,
        ))
        db_session.add(Permission(
            id="perm_bob_w2", file_id=seed_file.id, role="writer",
            type="user", email_address=bob.email,
        ))
        db_session.commit()
        role = get_effective_role(seed_file, bob, db_session)
        assert role == "writer"


class TestComputeCapabilities:
    def test_owner_capabilities(self, db_session, seed_user, seed_file):
        caps = compute_capabilities(seed_file, seed_user, "owner")
        assert caps["canEdit"] is True
        assert caps["canDelete"] is True
        assert caps["canShare"] is True
        assert caps["canTrash"] is True

    def test_reader_capabilities(self, db_session, seed_users, seed_file):
        bob = seed_users["bob@example.com"]
        caps = compute_capabilities(seed_file, bob, "reader")
        assert caps["canEdit"] is False
        assert caps["canDelete"] is False
        assert caps["canCopy"] is True
        assert caps["canDownload"] is True

    def test_writer_capabilities(self, db_session, seed_users, seed_file):
        bob = seed_users["bob@example.com"]
        caps = compute_capabilities(seed_file, bob, "writer")
        assert caps["canEdit"] is True
        assert caps["canDelete"] is False
        assert caps["canShare"] is True  # writersCanShare defaults to True

    def test_no_role_capabilities(self, db_session, seed_users, seed_file):
        bob = seed_users["bob@example.com"]
        caps = compute_capabilities(seed_file, bob, None)
        assert caps["canEdit"] is False
        assert caps["canCopy"] is False


class TestUserCanView:
    def test_owner_can_view(self, db_session, seed_user, seed_file):
        assert user_can_view(seed_file, seed_user, db_session) is True

    def test_stranger_cannot_view(self, db_session, seed_users, seed_file):
        bob = seed_users["bob@example.com"]
        assert user_can_view(seed_file, bob, db_session) is False
