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
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sellfox_shipping.models import Address, Order, PackageStatus
from sellfox_shipping.package_service import (
    ListPackagesService,
    PackageListRequest,
    PackageReviewRequest,
    ReviewPackageService,
)
from sellfox_shipping.sellfox_client import SellfoxClient
from sellfox_shipping.store import Store

# ── Bootstrap ─────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

from sellfox_shipping.env_loader import load_dotenv

load_dotenv()


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


def _get_package_review_service() -> ReviewPackageService:
    return ReviewPackageService(_get_package_repository())


def _get_lizard_dims_lookup():
    """Cascade: commodity pageList → ERPNext ZLMB (same as CLI)."""
    from sellfox_shipping.carriers.lizard.cascade import CascadingDimsLookup
    from sellfox_shipping.carriers.lizard.commodity_dims import CommodityPageListDimsLookup
    from sellfox_shipping.carriers.lizard.erpnext_dims import ErpnextZlmbDimsLookup
    from sellfox_shipping.env_loader import load_dotenv as _load_env

    _load_env(Path(__file__).resolve().parents[1] / "EN_API" / ".env")
    _load_env()

    primary = CommodityPageListDimsLookup(
        proxy_base_url=config["sellfox"]["proxy_base_url"],
        proxy_account=config["sellfox"]["proxy_account"],
        proxy_api_key=os.getenv("SELLFOX_PROXY_API_KEY", ""),
    )
    erp_key = (
        os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY") or ""
    ).strip()
    erp_secret = (
        os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET") or ""
    ).strip()
    if not erp_key or not erp_secret:
        return primary
    erp_url = (os.getenv("ERP_URL") or "https://erpnext.vilavi.cn").strip().rstrip(
        "/"
    )
    fallback = ErpnextZlmbDimsLookup(
        base_url=erp_url,
        api_key=erp_key,
        api_secret=erp_secret,
    )
    return CascadingDimsLookup(primary, fallback)


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


@app.post("/api/packages/{package_sn}/review")
async def review_package(package_sn: str, body: dict):
    """Set local review status (approved/rejected/pending) with audit."""
    from pydantic import ValidationError

    try:
        record = _get_package_review_service().review(
            PackageReviewRequest(
                account_key=config["sellfox"]["proxy_account"],
                package_sn=package_sn,
                actor=str(body.get("actor") or ""),
                decision=str(body.get("decision") or ""),
                note=str(body.get("note") or ""),
            )
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()) from exc
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
    return templates.TemplateResponse(request, "index.html")


@app.get("/packages", response_class=HTMLResponse)
async def packages_page(
    request: Request,
    status: str | None = Query(None),
    channel: str | None = Query(None),
    review: str | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    """Server-rendered package list for review."""
    account_key = config["sellfox"]["proxy_account"]
    result = _get_package_list_service().list(
        PackageListRequest(
            account_key=account_key,
            package_status=status,
            channel_name=channel,
            local_review_status=review,
            limit=limit,
            offset=offset,
        )
    )
    return templates.TemplateResponse(
        request,
        "packages.html",
        {
            "account_key": account_key,
            "status": status or "",
            "channel": channel or "",
            "review": review or "",
            "total": result.total,
            "items": result.items,
        },
    )


@app.get("/packages/{package_sn}", response_class=HTMLResponse)
async def package_detail_page(request: Request, package_sn: str):
    """Server-rendered package detail for review."""
    record = _get_package_repository().get(
        config["sellfox"]["proxy_account"],
        package_sn,
    )
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        {"package": record, "message": ""},
    )


@app.post("/packages/{package_sn}/review", response_class=HTMLResponse)
async def package_review_form(request: Request, package_sn: str):
    """HTML form post for local review decision."""
    form = await request.form()
    try:
        record = _get_package_review_service().review(
            PackageReviewRequest(
                account_key=config["sellfox"]["proxy_account"],
                package_sn=package_sn,
                actor=str(form.get("actor") or "web-user"),
                decision=str(form.get("decision") or ""),
                note=str(form.get("note") or ""),
            )
        )
        message = f"已更新本地审核状态为 {record.local_review_status}"
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        record = _get_package_repository().get(
            config["sellfox"]["proxy_account"],
            package_sn,
        )
        if record is None:
            raise HTTPException(404, f"Package {package_sn} not found") from exc
        message = f"审核失败: {exc}"
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        {"package": record, "message": message},
    )


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    return templates.TemplateResponse(request, "orders.html")


@app.get("/lizard/export", response_class=HTMLResponse)
async def lizard_export_page(request: Request):
    """Form to export approved 蜴国际 packages to upload Excel."""
    return templates.TemplateResponse(
        request,
        "lizard_export.html",
        {
            "message": "",
            "error": "",
            "default_actor": "web-user",
            "default_shipper": "S0143",
            "default_limit": 500,
        },
    )


@app.post("/lizard/export")
async def lizard_export_form(
    request: Request,
    actor: str = Form("web-user"),
    limit: int = Form(500),
    shipper_code: str = Form("S0143"),
):
    """Run export service and download xlsx (does not call submitToPlatform)."""
    from datetime import datetime, timezone

    from sellfox_shipping.lizard_batch import (
        ExportLizardUploadService,
        LizardExportRequest,
    )

    out_dir = BASE_DIR / "data" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = out_dir / f"lizard-upload-{stamp}.xlsx"
    try:
        result = ExportLizardUploadService(
            _get_package_repository(),
            _get_lizard_dims_lookup(),
        ).export(
            LizardExportRequest(
                account_key=config["sellfox"]["proxy_account"],
                actor=(actor or "web-user").strip() or "web-user",
                output_path=output_path,
                limit=max(1, min(int(limit), 5000)),
                shipper_code=(shipper_code or "S0143").strip() or "S0143",
            )
        )
    except Exception as exc:  # noqa: BLE001 — surface to operator
        return templates.TemplateResponse(
            request,
            "lizard_export.html",
            {
                "message": "",
                "error": f"导出失败: {exc}",
                "default_actor": actor,
                "default_shipper": shipper_code,
                "default_limit": limit,
            },
            status_code=400,
        )
    if result.exported == 0:
        return templates.TemplateResponse(
            request,
            "lizard_export.html",
            {
                "message": "",
                "error": (
                    f"没有可导出的行（候选 {result.total_candidates}，"
                    f"跳过 {result.skipped}）。请确认本地审核为 approved，"
                    "渠道名含「蜴」，且重尺可查。"
                ),
                "skipped_rows": result.skipped_rows,
                "default_actor": actor,
                "default_shipper": shipper_code,
                "default_limit": limit,
            },
            status_code=400,
        )
    return FileResponse(
        path=str(output_path),
        filename=output_path.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )


@app.get("/lizard/import", response_class=HTMLResponse)
async def lizard_import_page(request: Request):
    """Form to import lizard tracking-return Excel (local DB only)."""
    return templates.TemplateResponse(
        request,
        "lizard_import.html",
        {
            "result": None,
            "error": "",
            "default_actor": "web-user",
        },
    )


@app.post("/lizard/import", response_class=HTMLResponse)
async def lizard_import_form(
    request: Request,
    actor: str = Form("web-user"),
    file: UploadFile = File(...),
):
    """Parse return Excel, persist tracking locally, show reconciliation report."""
    import tempfile

    from sellfox_shipping.lizard_batch import (
        ImportLizardTrackingService,
        LizardImportRequest,
    )

    suffix = Path(file.filename or "return.xlsx").suffix or ".xlsx"
    try:
        raw = await file.read()
        if not raw:
            raise ValueError("上传文件为空")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        try:
            result = ImportLizardTrackingService(
                _get_package_repository()
            ).import_file(
                LizardImportRequest(
                    account_key=config["sellfox"]["proxy_account"],
                    actor=(actor or "web-user").strip() or "web-user",
                    input_path=tmp_path,
                )
            )
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "lizard_import.html",
            {
                "result": None,
                "error": f"导入失败: {exc}",
                "default_actor": actor,
            },
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "lizard_import.html",
        {
            "result": result,
            "error": "",
            "default_actor": actor,
        },
    )


# ── MCP mount — appended in main.py after FastMCP server is created ──

def mount_mcp(mcp_app):
    """Mount FastMCP ASGI app. Called from main.py after MCP tools are defined."""
    app.mount("/mcp", mcp_app)
    return app
