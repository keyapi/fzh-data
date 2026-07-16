"""sellfox_shipping — 赛狐尾程打单系统

Three-interface architecture:
  - FastAPI REST API → Web UI (human operators)
  - FastMCP tools      → AI Agents (Claude, Codex, Cursor)
  - Typer CLI          → Terminal (human + agent)
"""
