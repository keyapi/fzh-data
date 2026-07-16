"""sellfox_shipping — FastAPI web application.

Three interfaces sharing one service layer:
  - /api/*   → REST API (Web UI backend)
  - /mcp     → FastMCP mount (AI Agent tools)
  - /        → Web UI (Jinja2 templates)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sellfox_shipping.models import Address, Order, PackageStatus
from sellfox_shipping.package_service import ListPackagesService, PackageListRequest
from sellfox_shipping.sellfox_client import SellfoxClient
from sellfox_shipping.store import Store

# ── Bootstrap ─────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

def _load_config() -> dict:
    path = BASE_DIR / "config.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

config = _load_config()
store = Store(db_path=BASE_DIR / config.get("store", {}).get("db_path", "data/shipping.db"))

sellfox = SellfoxClient(
    proxy_base_url=config["sellfox"]["proxy_base_url"],
    proxy_account=config["sellfox"]["proxy_account"],
    proxy_api_key=os.getenv("SELLFOX_PROXY_API_KEY", ""),
)


def _get_package_repository():
    from sellfox_shipping.package_repository import PackageRepository

    return PackageRepository(BASE_DIR / config.get("store", {}).get("db_path", "data/shipping.db"))


def _get_package_list_service() -> ListPackagesService:
    return ListPackagesService(_get_package_repository())


# ── FastAPI app ──────────────────────────────────────────────────

app = FastAPI(
    title="sellfox-shipping",
    description="赛狐尾程打单系统 — 三界面架构 (REST + MCP + CLI)",
    version="0.1.0",
)

templates_dir = BASE_DIR / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── REST endpoints ───────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "database": str(store.conn.execute("SELECT 1").fetchone())}


@app.get("/api/packages")
async def list_packages(
    status: str | None = Query(None, description="Filter by package_status"),
    channel: str | None = Query(None, description="Filter by channel_name"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    """List local package summaries from the package-centric store."""
    result = _get_package_list_service().list(
        PackageListRequest(
            account_key=config["sellfox"]["proxy_account"],
            package_status=status,
            channel_name=channel,
            limit=limit,
            offset=offset,
        )
    )
    return result.model_dump(mode="json")


@app.get("/api/packages/{package_sn}")
async def get_package(package_sn: str):
    """Return a single normalized package record from the local store."""
    record = _get_package_repository().get(
        config["sellfox"]["proxy_account"],
        package_sn,
    )
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    return record.model_dump(mode="json")


@app.get("/api/orders")
async def list_orders(
    status: str | None = Query(None),
    carrier: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    orders = store.list_orders(status=status, carrier=carrier, limit=limit, offset=offset)
    total = store.count_orders(status=status)
    return {
        "orders": [o.model_dump(mode="json") for o in orders],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/orders/{amazon_order_id}")
async def get_order(amazon_order_id: str):
    order = store.get_order(amazon_order_id)
    if not order:
        raise HTTPException(404, f"Order {amazon_order_id} not found")
    labels = store.get_labels_for_order(order.id)
    return {
        "order": order.model_dump(mode="json"),
        "labels": [l.model_dump(mode="json") for l in labels],
    }


@app.post("/api/orders/fetch")
async def fetch_orders_from_sellfox(
    date_start: str = Query(description="yyyy-MM-dd"),
    date_end: str = Query(description="yyyy-MM-dd"),
    status: str | None = Query(None),
    page_size: int = Query(20, le=200),
):
    """Pull orders from Sellfox into local store."""
    all_orders = []
    page_no = 1
    total = 0
    while True:
        orders, total = sellfox.fetch_orders(
            date_start=date_start,
            date_end=date_end,
            status=status,
            page_no=page_no,
            page_size=page_size,
        )
        for o in orders:
            store.upsert_order(o)
        all_orders.extend(orders)
        if page_no * page_size >= total:
            break
        page_no += 1
    return {"fetched": len(all_orders), "total_in_sellfox": total}


@app.post("/api/orders/fetch-detail")
async def fetch_order_detail(shop_id: str, amazon_order_id: str):
    """Pull a single full order detail from Sellfox."""
    order = sellfox.get_order_detail(shop_id, amazon_order_id)
    if not order:
        raise HTTPException(404, f"Order {amazon_order_id} not found in Sellfox")
    order_id = store.upsert_order(order)
    return {
        "order_id": order_id,
        "amazon_order_id": order.amazon_order_id,
        "has_address": bool(order.shipping_address.address1),
    }


@app.get("/api/warehouses")
async def list_warehouses():
    return config.get("warehouses", {})


@app.get("/api/carriers")
async def list_carriers():
    return {
        name: {"enabled": cfg.get("enabled", False)}
        for name, cfg in config.get("carriers", {}).items()
    }


@app.get("/api/rules")
async def list_rules():
    return config.get("rules", [])


# ── Web UI ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    return templates.TemplateResponse("orders.html", {"request": request})


# ── MCP mount — appended in main.py after FastMCP server is created ──

def mount_mcp(mcp_app):
    """Mount FastMCP ASGI app. Called from main.py after MCP tools are defined."""
    app.mount("/mcp", mcp_app)
    return app
