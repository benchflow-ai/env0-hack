"""Response field filtering for the `fields` query parameter.

Drive API uses `fields` to select which fields are returned:
  GET /drive/v3/files?fields=files(id,name,parents),nextPageToken
  GET /drive/v3/files/abc?fields=id,name,permissions(role)

This module parses the fields string and filters serialized response dicts.
"""

from __future__ import annotations


def parse_fields(fields_str: str) -> dict:
    """Parse a fields string into a nested dict of field selections.

    Examples:
        "id,name,mimeType" -> {"id": {}, "name": {}, "mimeType": {}}
        "files(id,name),nextPageToken" -> {"files": {"id": {}, "name": {}}, "nextPageToken": {}}
    """
    if not fields_str or not fields_str.strip():
        return {}

    result = {}
    i = 0
    s = fields_str.strip()

    while i < len(s):
        # Skip whitespace and commas
        while i < len(s) and s[i] in (" ", ","):
            i += 1
        if i >= len(s):
            break

        # Read field name
        start = i
        while i < len(s) and s[i] not in ("(", ",", ")"):
            i += 1
        name = s[start:i].strip()
        if not name:
            break

        if i < len(s) and s[i] == "(":
            # Nested fields: consume until matching ")"
            depth = 1
            i += 1  # skip "("
            inner_start = i
            while i < len(s) and depth > 0:
                if s[i] == "(":
                    depth += 1
                elif s[i] == ")":
                    depth -= 1
                i += 1
            inner = s[inner_start:i - 1]
            result[name] = parse_fields(inner)
        else:
            result[name] = {}

    return result


def filter_response(data: dict | list, field_spec: dict) -> dict | list:
    """Filter a response dict/list to only include fields in field_spec.

    If field_spec is empty, returns data unchanged (no filtering).
    """
    if not field_spec:
        return data

    if isinstance(data, list):
        return [filter_response(item, field_spec) for item in data]

    if not isinstance(data, dict):
        return data

    result = {}
    for key, sub_spec in field_spec.items():
        if key in data:
            val = data[key]
            if sub_spec and isinstance(val, (dict, list)):
                result[key] = filter_response(val, sub_spec)
            else:
                result[key] = val
    return result
