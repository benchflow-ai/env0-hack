"""Shared helpers for Slack API route modules."""

from __future__ import annotations

from fastapi.responses import JSONResponse


def _slack_error(error: str) -> JSONResponse:
    return JSONResponse(content={"ok": False, "error": error})
