"""MCP server for mock-gdoc."""

from __future__ import annotations


def mount_mcp(app):
    """Mount MCP endpoint on the FastAPI app."""
    try:
        from fastapi_mcp import FastApiMCP
        mcp = FastApiMCP(
            app,
            name="mock-gdoc",
            description="Mock Google Docs API — document CRUD, batchUpdate, search",
        )
        mcp.mount()
    except ImportError:
        pass
