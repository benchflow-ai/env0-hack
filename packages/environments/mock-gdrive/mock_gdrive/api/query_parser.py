"""Drive search query parser using lark.

Parses the `q` parameter from files.list into SQLAlchemy filter expressions.
Supports: name, fullText, mimeType, trashed, starred, parents, modifiedTime,
viewedByMeTime, ownedByMe, sharedWithMe, and boolean operators (and/or/not).
"""

from __future__ import annotations

from datetime import datetime

from lark import Lark, Transformer, v_args
from sqlalchemy import and_, or_, not_, func
from sqlalchemy.orm import Session

from mock_gdrive.models.file import File

GRAMMAR = r"""
    ?start: expr

    ?expr: expr "and"i term   -> and_expr
         | term

    ?term: term "or"i atom    -> or_expr
         | atom

    ?atom: "not"i atom        -> not_expr
         | "(" expr ")"
         | comparison

    ?comparison: FIELD "=" value           -> eq
              | FIELD "!=" value          -> neq
              | FIELD "<" value           -> lt
              | FIELD ">" value           -> gt
              | FIELD "<=" value          -> lte
              | FIELD ">=" value          -> gte
              | FIELD "contains"i value   -> contains
              | value "in"i FIELD         -> in_field
              | FIELD "has"i "{" FIELD "=" value "}" -> has_prop

    ?value: SQUOTED
          | BOOLEAN
          | "null"                        -> null_val

    FIELD: /[a-zA-Z_][a-zA-Z0-9_.]*/
    SQUOTED: "'" /[^']*/ "'"
    BOOLEAN: "true" | "false"

    %ignore /\s+/
"""

# Lark's string literal priority ensures "and", "or", "not", "contains", "in", "has"
# are recognized as keywords before the FIELD regex matches them.
_parser = Lark(GRAMMAR, parser="earley", ambiguity="resolve")


def _strip_quotes(s: str) -> str:
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    return s


class _QueryTransformer(Transformer):
    """Transform parse tree into SQLAlchemy filter expressions."""

    def __init__(self, current_user_id: str):
        super().__init__()
        self.current_user_id = current_user_id

    def FIELD(self, token):
        return str(token)

    def SQUOTED(self, token):
        return _strip_quotes(str(token))

    def BOOLEAN(self, token):
        return str(token) == "true"

    def null_val(self, _args):
        return None

    def and_expr(self, args):
        return and_(args[0], args[1])

    def or_expr(self, args):
        return or_(args[0], args[1])

    def not_expr(self, args):
        return not_(args[0])

    def eq(self, args):
        field, value = str(args[0]), args[1]
        return self._field_eq(field, value)

    def neq(self, args):
        field, value = str(args[0]), args[1]
        return not_(self._field_eq(field, value))

    def lt(self, args):
        field, value = str(args[0]), args[1]
        return self._field_cmp(field, value, "<")

    def gt(self, args):
        field, value = str(args[0]), args[1]
        return self._field_cmp(field, value, ">")

    def lte(self, args):
        field, value = str(args[0]), args[1]
        return self._field_cmp(field, value, "<=")

    def gte(self, args):
        field, value = str(args[0]), args[1]
        return self._field_cmp(field, value, ">=")

    def contains(self, args):
        field, value = str(args[0]), args[1]
        return self._field_contains(field, value)

    def in_field(self, args):
        value, field = args[0], str(args[1])
        if field == "parents":
            return File.parent_id == value
        # Unknown field — no-op filter
        return File.id.isnot(None)

    def has_prop(self, args):
        _field, key, value = str(args[0]), str(args[1]), args[2]
        # properties has { key = 'value' } — simplified as JSON lookup
        return File.properties[key].as_string() == value

    def _field_eq(self, field: str, value):
        col = self._resolve_field(field)
        if col is not None:
            if isinstance(value, bool):
                return col == value
            return col == value
        # Virtual fields
        if field == "ownedByMe":
            if value:
                return File.owner_id == self.current_user_id
            return File.owner_id != self.current_user_id
        if field == "sharedWithMe":
            # This requires a join — handled at the query level
            # Return a marker that the caller interprets
            from mock_gdrive.models.permission import Permission
            if value:
                return and_(
                    File.owner_id != self.current_user_id,
                    File.permissions.any(Permission.email_address != None),
                )
            return File.owner_id == self.current_user_id
        return File.id.isnot(None)

    def _field_contains(self, field: str, value: str):
        pattern = f"%{value}%"
        if field == "name":
            return File.name.ilike(pattern)
        if field == "fullText":
            return or_(
                File.name.ilike(pattern),
                File.content_text.ilike(pattern),
                File.description.ilike(pattern),
            )
        return File.id.isnot(None)

    def _field_cmp(self, field: str, value, op: str):
        col = self._resolve_field(field)
        if col is None:
            return File.id.isnot(None)

        # Parse datetime strings for time fields
        if field in ("modifiedTime", "createdTime", "viewedByMeTime"):
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return File.id.isnot(None)

        if op == "<":
            return col < value
        if op == ">":
            return col > value
        if op == "<=":
            return col <= value
        if op == ">=":
            return col >= value
        return File.id.isnot(None)

    def _resolve_field(self, field: str):
        """Map Drive API field names to SQLAlchemy columns."""
        mapping = {
            "name": File.name,
            "mimeType": File.mime_type,
            "trashed": File.trashed,
            "starred": File.starred,
            "modifiedTime": File.modified_time,
            "createdTime": File.created_time,
            "viewedByMeTime": File.viewed_by_me_time,
            "sharedWithMeTime": File.shared_with_me_time,
            "modifiedByMeTime": File.modified_by_me_time,
            "description": File.description,
            "writersCanShare": File.writers_can_share,
        }
        return mapping.get(field)


def parse_query(q: str, current_user_id: str):
    """Parse a Drive search query string into a SQLAlchemy filter expression.

    Returns a SQLAlchemy BooleanClauseList that can be passed to query.filter().
    """
    if not q or not q.strip():
        return None

    tree = _parser.parse(q)
    transformer = _QueryTransformer(current_user_id)
    return transformer.transform(tree)
