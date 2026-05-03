"""Tests for Comments and Replies API endpoints."""

import json
import pytest
from mock_gdrive.models import File, Permission, User, Comment, Reply


@pytest.fixture()
def seed_comment(db_session, seed_user, seed_file):
    """Create a test comment."""
    comment = Comment(
        id="comment_1",
        file_id=seed_file.id,
        author_id=seed_user.id,
        content="This is a test comment",
    )
    db_session.add(comment)
    db_session.commit()
    return comment


@pytest.fixture()
def seed_reply(db_session, seed_user, seed_comment):
    """Create a test reply."""
    reply = Reply(
        id="reply_1",
        comment_id=seed_comment.id,
        author_id=seed_user.id,
        content="This is a test reply",
    )
    db_session.add(reply)
    db_session.commit()
    return reply


class TestCommentsList:
    def test_list_comments(self, client, seed_user, seed_file, seed_comment):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#commentList"
        assert len(data["comments"]) == 1
        assert data["comments"][0]["id"] == "comment_1"
        assert data["comments"][0]["kind"] == "drive#comment"

    def test_list_excludes_deleted(self, client, db_session, seed_user, seed_file, seed_comment):
        seed_comment.deleted = True
        db_session.commit()
        resp = client.get(f"/drive/v3/files/{seed_file.id}/comments")
        assert resp.status_code == 200
        assert len(resp.json()["comments"]) == 0

    def test_list_includes_deleted(self, client, db_session, seed_user, seed_file, seed_comment):
        seed_comment.deleted = True
        db_session.commit()
        resp = client.get(
            f"/drive/v3/files/{seed_file.id}/comments",
            params={"includeDeleted": True},
        )
        assert resp.status_code == 200
        assert len(resp.json()["comments"]) == 1

    def test_list_empty(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/comments")
        assert resp.status_code == 200
        assert resp.json()["comments"] == []


class TestCommentsGet:
    def test_get_comment(self, client, seed_user, seed_file, seed_comment):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/comments/comment_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "comment_1"
        assert data["content"] == "This is a test comment"
        assert data["author"]["emailAddress"] == "test@example.com"

    def test_get_comment_not_found(self, client, seed_user, seed_file):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/comments/nonexistent")
        assert resp.status_code == 404

    def test_get_includes_replies(self, client, seed_user, seed_file, seed_comment, seed_reply):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/comments/comment_1")
        data = resp.json()
        assert len(data["replies"]) == 1
        assert data["replies"][0]["id"] == "reply_1"


class TestCommentsCreate:
    def test_create_comment(self, client, seed_user, seed_file):
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/comments",
            content=json.dumps({"content": "New comment"}),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "New comment"
        assert data["kind"] == "drive#comment"
        assert data["author"]["emailAddress"] == "test@example.com"

    def test_create_comment_with_anchor(self, client, seed_user, seed_file):
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/comments",
            content=json.dumps({"content": "Anchored", "anchor": "line:5"}),
        )
        assert resp.status_code == 200
        assert resp.json()["anchor"] == "line:5"


class TestCommentsUpdate:
    def test_update_comment(self, client, seed_user, seed_file, seed_comment):
        resp = client.patch(
            f"/drive/v3/files/{seed_file.id}/comments/comment_1",
            content=json.dumps({"content": "Updated comment"}),
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "Updated comment"


class TestCommentsDelete:
    def test_delete_comment(self, client, seed_user, seed_file, seed_comment):
        resp = client.delete(f"/drive/v3/files/{seed_file.id}/comments/comment_1")
        assert resp.status_code == 204

        # Verify it's marked deleted, not removed
        resp2 = client.get(
            f"/drive/v3/files/{seed_file.id}/comments/comment_1",
            params={"includeDeleted": True},
        )
        assert resp2.status_code == 200
        assert resp2.json()["deleted"] is True


class TestRepliesList:
    def test_list_replies(self, client, seed_user, seed_file, seed_comment, seed_reply):
        resp = client.get(f"/drive/v3/files/{seed_file.id}/comments/comment_1/replies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["kind"] == "drive#replyList"
        assert len(data["replies"]) == 1


class TestRepliesCreate:
    def test_create_reply(self, client, seed_user, seed_file, seed_comment):
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/comments/comment_1/replies",
            content=json.dumps({"content": "A reply"}),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "A reply"
        assert data["kind"] == "drive#reply"

    def test_create_resolve_reply(self, client, seed_user, seed_file, seed_comment):
        resp = client.post(
            f"/drive/v3/files/{seed_file.id}/comments/comment_1/replies",
            content=json.dumps({"content": "Resolved", "action": "resolve"}),
        )
        assert resp.status_code == 200

        # Verify comment is now resolved
        resp2 = client.get(f"/drive/v3/files/{seed_file.id}/comments/comment_1")
        assert resp2.json()["resolved"] is True


class TestRepliesDelete:
    def test_delete_reply(self, client, seed_user, seed_file, seed_comment, seed_reply):
        resp = client.delete(
            f"/drive/v3/files/{seed_file.id}/comments/comment_1/replies/reply_1"
        )
        assert resp.status_code == 204
