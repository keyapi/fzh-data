"""Entry point — wires FastAPI app + optional FastMCP, starts uvicorn."""

from __future__ import annotations

from sellfox_shipping.app import app, mount_mcp, store

mcp_enabled = False

try:
    from sellfox_shipping.mcp_tools import init_mcp, mcp
except ImportError:
    # FastMCP is optional for P1A Web/REST; Docker may install it separately.
    pass
else:
    init_mcp(store)
    mount_mcp(mcp.asgi_app())
    mcp_enabled = True
