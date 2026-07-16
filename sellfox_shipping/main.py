"""Entry point — wires FastAPI app + FastMCP together, starts uvicorn."""

from sellfox_shipping.app import app, mount_mcp, store
from sellfox_shipping.mcp_tools import init_mcp, mcp

# Wire MCP tools to shared store
init_mcp(store)

# Mount FastMCP ASGI app under /mcp
mount_mcp(mcp.asgi_app())
