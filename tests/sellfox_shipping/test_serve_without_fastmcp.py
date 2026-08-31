from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient


def test_main_app_loads_without_fastmcp() -> None:
    """Web serve must not require FastMCP for P1A package pages."""
    sys.modules.pop("sellfox_shipping.main", None)
    sys.modules.pop("sellfox_shipping.mcp_tools", None)

    main = importlib.import_module("sellfox_shipping.main")

    assert main.app is not None
    assert main.mcp_enabled is False

    response = TestClient(main.app).get("/packages")
    assert response.status_code == 200
    assert "包裹" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_packages_api_works_via_main_app() -> None:
    sys.modules.pop("sellfox_shipping.main", None)
    main = importlib.import_module("sellfox_shipping.main")

    response = TestClient(main.app).get("/api/packages")
    assert response.status_code == 200
    assert "total" in response.json()
