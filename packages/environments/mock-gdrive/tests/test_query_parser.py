"""Tests for the Drive search query parser."""

import pytest
from mock_gdrive.api.query_parser import parse_query


class TestQueryParser:
    def test_name_eq(self):
        expr = parse_query("name = 'test.txt'", "user1")
        assert expr is not None

    def test_name_contains(self):
        expr = parse_query("name contains 'budget'", "user1")
        assert expr is not None

    def test_mimetype_eq(self):
        expr = parse_query("mimeType = 'application/vnd.google-apps.folder'", "user1")
        assert expr is not None

    def test_in_parents(self):
        expr = parse_query("'folder123' in parents", "user1")
        assert expr is not None

    def test_trashed_eq(self):
        expr = parse_query("trashed = true", "user1")
        assert expr is not None

    def test_starred_eq(self):
        expr = parse_query("starred = false", "user1")
        assert expr is not None

    def test_and_operator(self):
        expr = parse_query("name contains 'x' and trashed = false", "user1")
        assert expr is not None

    def test_or_operator(self):
        expr = parse_query("name contains 'a' or name contains 'b'", "user1")
        assert expr is not None

    def test_not_operator(self):
        expr = parse_query("not trashed = true", "user1")
        assert expr is not None

    def test_parentheses(self):
        expr = parse_query("(name contains 'a' or name contains 'b') and trashed = false", "user1")
        assert expr is not None

    def test_compound_query(self):
        q = "name contains 'budget' and mimeType = 'application/vnd.google-apps.spreadsheet' and 'abc' in parents"
        expr = parse_query(q, "user1")
        assert expr is not None

    def test_fulltext_contains(self):
        expr = parse_query("fullText contains 'api key'", "user1")
        assert expr is not None

    def test_datetime_comparison(self):
        expr = parse_query("modifiedTime > '2026-01-01T00:00:00'", "user1")
        assert expr is not None

    def test_owned_by_me(self):
        expr = parse_query("ownedByMe = true", "user1")
        assert expr is not None

    def test_empty_query(self):
        assert parse_query("", "user1") is None
        assert parse_query("  ", "user1") is None
        assert parse_query(None, "user1") is None

    def test_invalid_query_raises(self):
        with pytest.raises(Exception):
            parse_query("invalid %%% garbage", "user1")

    def test_neq(self):
        expr = parse_query("mimeType != 'application/pdf'", "user1")
        assert expr is not None

    def test_shared_with_me(self):
        expr = parse_query("sharedWithMe = true", "user1")
        assert expr is not None
