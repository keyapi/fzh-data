"""sellfox_shipping — FastAPI web application.

Three interfaces sharing one service layer:
  - /api/*   → REST API (Web UI backend)
  - /mcp     → FastMCP mount (AI Agent tools)
  - /        → Web UI (Jinja2 templates)
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
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
    """Override → EN ZLMB# (V2 with sibling borrowing)."""
    from sellfox_shipping.carriers.lizard.cascade import CascadingDimsLookup
    from sellfox_shipping.carriers.lizard.erpnext_dims_v2 import ErpnextDimsLookupV2
    from sellfox_shipping.carriers.lizard.override_dims import RepositoryDimsLookup
    from sellfox_shipping.env_loader import load_dotenv as _load_env

    _load_env(Path(__file__).resolve().parents[1] / "EN_API" / ".env")
    _load_env()

    repo = _get_package_repository()
    account_key = config["sellfox"]["proxy_account"]
    override = RepositoryDimsLookup(repo, account_key)
    lookups: list = [override]

    erp_key = (
        os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY") or ""
    ).strip()
    erp_secret = (
        os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET") or ""
    ).strip()
    if erp_key and erp_secret:
        erp_url = (
            os.getenv("ERP_URL") or "https://erpnext.vilavi.cn"
        ).strip().rstrip("/")
        lookups.append(
            ErpnextDimsLookupV2(
                base_url=erp_url,
                api_key=erp_key,
                api_secret=erp_secret,
            )
        )
    return CascadingDimsLookup(*lookups)


# ── FastAPI app ──────────────────────────────────────────────────

app = FastAPI(
    title="sellfox-shipping",
    description="赛狐尾程打单系统 — 三界面架构 (REST + MCP + CLI)",
    version="0.1.0",
)

from sellfox_shipping.auth_oidc import (  # noqa: E402
    PUBLIC_PATH_PREFIXES,
    assert_oidc_config_complete,
    build_oidc_router,
    load_oidc_settings,
    require_user,
    resolve_actor,
)

_oidc_settings = load_oidc_settings(config)
assert_oidc_config_complete(_oidc_settings)
app.include_router(build_oidc_router(_oidc_settings))


@app.middleware("http")
async def oidc_gate(request: Request, call_next):
    if not _oidc_settings.enabled:
        return await call_next(request)
    path = request.url.path
    if any(path == p or path.startswith(p + "/") for p in PUBLIC_PATH_PREFIXES):
        return await call_next(request)
    if path.startswith("/static"):
        return await call_next(request)
    try:
        user = require_user(request, _oidc_settings)
    except HTTPException:
        if path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
            )
        return RedirectResponse("/oidc-login")
    request.state.user = user
    return await call_next(request)


def _web_actor(request: Request, fallback: str = "") -> str:
    return resolve_actor(request, _oidc_settings, fallback=fallback)


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
    review: str | None = Query(None, description="Filter by local_review_status"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    """List local package summaries from the package-centric store."""
    result = _get_package_list_service().list(
        PackageListRequest(
            account_key=config["sellfox"]["proxy_account"],
            package_status=status or None,
            channel_name=channel or None,
            local_review_status=review or None,
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
async def review_package(request: Request, package_sn: str, body: dict):
    """Set local review status (approved/rejected/pending) with audit."""
    from pydantic import ValidationError

    try:
        record = _get_package_review_service().review(
            PackageReviewRequest(
                account_key=config["sellfox"]["proxy_account"],
                package_sn=package_sn,
                actor=_web_actor(request, str(body.get("actor") or "")),
                decision=str(body.get("decision") or ""),
                note=str(body.get("note") or ""),
            )
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()) from exc
    return record.model_dump(mode="json")


@app.post("/api/packages/{package_sn}/create-label")
async def api_create_label(request: Request, package_sn: str, body: dict):
    """Create a shipping label via carrier API. Returns label record as JSON.

    Body: {"carrier": "vite", "service_level": "GOFO_PARCEL", "channel": "GFUS"}
    """
    from sellfox_shipping.label_service import LabelService, LabelServiceError

    account_key = config["sellfox"]["proxy_account"]
    record = _get_package_repository().get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")

    carrier = str(body.get("carrier") or "").strip()
    if not carrier:
        raise HTTPException(400, "carrier is required")

    try:
        service = LabelService(_get_package_repository())
        result = service.create_label(
            carrier=carrier,
            package=record,
            account_key=account_key,
            actor=_web_actor(request, str(body.get("actor") or "")),
            service_level=str(body.get("service_level") or ""),
            channel=str(body.get("channel") or ""),
        )
    except LabelServiceError as exc:
        raise HTTPException(exc.http_status, str(exc)) from exc
    return result


@app.get("/api/packages/{package_sn}/labels")
async def api_package_labels(package_sn: str):
    """List all shipping labels for a package."""
    from sellfox_shipping.label_service import LabelService

    account_key = config["sellfox"]["proxy_account"]
    record = _get_package_repository().get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    service = LabelService(_get_package_repository())
    return service.get_labels_for_package(account_key, package_sn)


@app.get("/api/labels/{label_id}/download")
async def api_label_download(label_id: int):
    """Download a label's PDF artifact."""
    repo = _get_package_repository()
    label = repo.get_label(label_id)
    if label is None:
        raise HTTPException(404, f"Label {label_id} not found")
    if label.artifact_id is None:
        raise HTTPException(404, f"Label {label_id} has no PDF artifact")
    artifact = repo.get_artifact(label.artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    path = repo.resolve_artifact_path(artifact)
    if not path.is_file():
        raise HTTPException(404, "Artifact blob missing on disk")
    return FileResponse(
        path=str(path),
        filename=artifact.file_name,
        media_type=artifact.mime_type or "application/pdf",
    )


@app.post("/api/labels/{label_id}/cancel")
async def api_cancel_label(request: Request, label_id: int):
    """Cancel a shipping label via carrier API."""
    from sellfox_shipping.label_service import LabelService, LabelServiceError

    try:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    except Exception:
        body = {}
    actor = _web_actor(request, str(body.get("actor") or ""))

    try:
        service = LabelService(_get_package_repository())
        return service.cancel_label(label_id, actor=actor)
    except LabelServiceError as exc:
        raise HTTPException(exc.http_status, str(exc)) from exc


@app.post("/packages/{package_sn}/cancel-label/{label_id}", response_class=HTMLResponse)
async def package_cancel_label_form(request: Request, package_sn: str, label_id: int):
    """HTML form post to cancel a label."""
    from sellfox_shipping.label_service import LabelService, LabelServiceError

    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")

    actor = _web_actor(request, str(form.get("actor") or "web-user"))
    try:
        svc = LabelService(repo)
        result = svc.cancel_label(label_id, actor=actor)
        message = f"面单已取消 — {result.get('message', 'OK')}"
    except LabelServiceError as exc:
        message = f"取消失败: {exc}"

    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
    )


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


@app.get("/api/channels")
async def list_channels():
    """Return distinct channel names for filter dropdown."""
    repo = _get_package_repository()
    channels = repo.list_distinct_channels(config["sellfox"]["proxy_account"])
    return {"channels": channels}


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
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    date_field: str = Query("label"),
    tab: str | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    """Server-rendered package list for review."""
    account_key = config["sellfox"]["proxy_account"]
    result = _get_package_list_service().list(
        PackageListRequest(
            account_key=account_key,
            package_status=status or None,
            channel_name=channel or None,
            local_review_status=review or None,
            date_start=date_start or None,
            date_end=date_end or None,
            date_field=date_field,
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
            "date_start": date_start or "",
            "date_end": date_end or "",
            "date_field": date_field,
            "tab": tab or "",
            "today": date.today().isoformat(),
            "d7": (date.today() - timedelta(days=7)).isoformat(),
            "d30": (date.today() - timedelta(days=30)).isoformat(),
            "total": result.total,
            "items": result.items,
            "limit": limit,
            "offset": offset,
            "total_pages": max(1, (result.total + limit - 1) // limit) if result.total else 1,
            "current_page": (offset // limit) + 1 if limit else 1,
            "pagination": _build_pagination((offset // limit) + 1 if limit else 1,
                                            max(1, (result.total + limit - 1) // limit) if result.total else 1),
        },
    )


@app.get("/packages/{package_sn}", response_class=HTMLResponse)
async def package_detail_page(request: Request, package_sn: str):
    """Server-rendered package detail for review."""
    account_key = config["sellfox"]["proxy_account"]
    record = _get_package_repository().get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=""),
    )


@app.post("/packages/{package_sn}/fetch-rates", response_class=HTMLResponse)
async def package_fetch_rates(request: Request, package_sn: str):
    """Fetch VITE + Lizard rates on demand and redirect back to detail page."""
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")

    carton_rows = _carton_rows_for_package(account_key, record)
    package_dims = _compute_package_dims(record, carton_rows)
    routing_result = _compute_routing(record, carton_rows)

    vite_rate = _get_vite_rate(record, package_dims, routing_result)
    lizard_rate = _get_lizard_rate(record, package_dims)

    # Pick the routing-suggested carrier's rate for display
    if routing_result and routing_result.matched:
        suggested_carrier = (routing_result.carrier or "").strip().lower()
    else:
        suggested_carrier = ""
    display_rate = vite_rate if suggested_carrier == "vite" else (lizard_rate if suggested_carrier == "lizard" else vite_rate)

    if display_rate and "error" not in display_rate:
        message = f"报价已更新 — {display_rate.get('service', '')} ${display_rate.get('total_amount', '—')}"
    elif display_rate and "error" in display_rate:
        message = f"报价失败: {display_rate['error']}"
    else:
        message = "报价完成（查看历史记录）"

    # Re-render with fresh context (live rate + updated history)
    ctx = _package_detail_context(account_key, record, message=message, vite_rate_override=vite_rate, lizard_rate_override=lizard_rate)
    ctx["rate_history"] = _get_rate_history(repo, record, account_key)
    return templates.TemplateResponse(request, "package_detail.html", ctx)


def _build_pagination(current: int, total: int) -> list[dict]:
    """Build pagination items: {'kind':'page'|'gap','label':'1'|'...','page':int,'jump':int}"""
    items: list[dict] = []
    if total <= 7:
        for p in range(1, total + 1):
            items.append({"kind": "page", "label": str(p), "page": p, "current": p == current})
        return items
    items.append({"kind": "page", "label": "1", "page": 1, "current": current == 1})
    if current > 4:
        items.append({"kind": "gap", "label": "...", "jump": max(1, current - 5)})
    start = max(2, current - 1)
    end = min(total - 1, current + 1)
    if current <= 4:
        start = 2; end = max(end, 5)
    if current >= total - 3:
        end = total - 1; start = min(start, total - 4)
    for p in range(start, end + 1):
        items.append({"kind": "page", "label": str(p), "page": p, "current": p == current})
    if current < total - 3:
        items.append({"kind": "gap", "label": "...", "jump": min(total, current + 5)})
    items.append({"kind": "page", "label": str(total), "page": total, "current": current == total})
    return items


def _package_detail_context(account_key: str, record, *, message: str, vite_rate_override: dict | None = None, lizard_rate_override: dict | None = None) -> dict:
    from sellfox_shipping.submission_state import aggregate_package_submission_state

    repo = _get_package_repository()
    intents = repo.list_submission_intents_for_package(
        account_key=account_key,
        package_sn=record.package_sn,
    )
    package_submission_state = (
        aggregate_package_submission_state([i.status for i in intents])
        if intents
        else ""
    )
    carton_rows = _carton_rows_for_package(account_key, record)
    package_dims = _compute_package_dims(record, carton_rows)
    routing_result = _compute_routing(record, carton_rows)
    rate_history = _get_rate_history(repo, record, account_key)

    # Labels + enabled carriers for UI
    labels = _get_labels_for_package(account_key, record.package_sn)
    enabled_carriers = _get_enabled_carriers()
    lizard_services = _get_lizard_services(repo, record, account_key)

    # Use override from fetch-rates, or None for initial load (on-demand pattern)
    # Pick the routing-suggested carrier's rate for display
    if routing_result and routing_result.matched:
        suggested_carrier = (routing_result.carrier or "").strip().lower()
    else:
        suggested_carrier = ""
    if suggested_carrier == "lizard":
        vite_rate = lizard_rate_override
    else:
        vite_rate = vite_rate_override

    # Earliest purchase date from orders
    purchase_date = None
    for order in record.orders:
        if order.purchase_date:
            if purchase_date is None or order.purchase_date < purchase_date:
                purchase_date = order.purchase_date

    return {
        "package": record,
        "message": message,
        "carton_rows": carton_rows,
        "package_dims": package_dims,
        "routing_result": routing_result,
        "vite_rate": vite_rate,
        "lizard_rate": lizard_rate_override,
        "rate_history": rate_history,
        "submission_intents": intents,
        "package_submission_state": package_submission_state,
        "labels": labels,
        "enabled_carriers": enabled_carriers,
        "lizard_services": lizard_services,
        "purchase_date": purchase_date,
    }


def _carton_rows_for_package(account_key: str, record) -> list[dict]:
    repo = _get_package_repository()
    lookup = _get_lizard_dims_lookup()
    seen: set[str] = set()
    rows: list[dict] = []
    for item in record.items:
        sku = (item.commodity_sku or "").strip()
        if not sku or sku in seen:
            continue
        seen.add(sku)
        override = repo.get_carton_override(account_key, sku)
        try:
            resolved = lookup.get(sku)
        except Exception:
            resolved = None
        # Resolve item_name: override first, then EN, else empty
        item_name = (override.item_name if override else "") or ""
        if not item_name:
            item_name = lookup.get_item_name(sku)
            if item_name:
                try:
                    repo.upsert_carton_item_name(
                        account_key=account_key,
                        commodity_sku=sku,
                        item_name=item_name,
                    )
                except Exception:
                    pass
        rows.append(
            {
                "commodity_sku": sku,
                "override": override,
                "resolved": resolved,
                "item_name": item_name,
                "source": (
                    "override"
                    if (override is not None and override.dims.is_complete)
                    else ("cascade" if resolved is not None else "missing")
                ),
            }
        )
    return rows


def _compute_package_dims(record, carton_rows: list[dict]) -> dict | None:
    """Merge per-SKU dims into package-level dims and persist to DB.

    长=max, 宽=max, 高=sum, 重量=sum(weight × qty).
    Results are stored in shipping_package_dims for downstream consumption.
    """
    cr_by_sku = {r["commodity_sku"]: r for r in carton_rows}
    total_weight_kg = 0.0
    lengths: list[float] = []
    widths: list[float] = []
    heights: list[float] = []

    for item in record.items:
        sku = (item.commodity_sku or "").strip()
        if not sku:
            continue
        cr = cr_by_sku.get(sku)
        if cr is None:
            continue
        ov = cr.get("override")
        if ov is not None and ov.dims.is_complete:
            dims = ov.dims
        else:
            dims = cr.get("resolved")
        if dims is None or not dims.is_complete:
            continue
        qty = item.quantity or 1
        total_weight_kg += dims.weight_kg * qty
        lengths.append(dims.length_cm)
        widths.append(dims.width_cm)
        heights.append(dims.height_cm)

    if not lengths:
        return None

    result = {
        "weight_kg": round(total_weight_kg, 2),
        "length_cm": max(lengths),
        "width_cm": max(widths),
        "height_cm": sum(heights),
        "sku_count": len(lengths),
    }

    # Persist to DB for downstream (carrier export, rule engine, etc.)
    repo = _get_package_repository()
    package_db_id = repo.get_package_db_id(
        config["sellfox"]["proxy_account"], record.package_sn
    )
    if package_db_id is not None:
        try:
            repo.upsert_package_dims(
                package_db_id=package_db_id,
                weight_kg=result["weight_kg"],
                length_cm=result["length_cm"],
                width_cm=result["width_cm"],
                height_cm=result["height_cm"],
                sku_count=result["sku_count"],
            )
        except Exception:
            pass  # best-effort persist

    return result


def _compute_routing(record, carton_rows: list[dict]):
    """Run rule engine on package data and return a RoutingResult."""
    from pathlib import Path

    from sellfox_shipping.routing.engine import RuleEngine
    from sellfox_shipping.routing.models import PackageRoutingData

    rules_path = Path(__file__).parent / "routing" / "routing_rules.yaml"
    if not rules_path.exists():
        return None

    # Build dimensional data from carton rows + items
    sides: list[float] = []
    total_weight = 0.0
    total_qty = 0
    cr_by_sku = {r["commodity_sku"]: r for r in carton_rows}
    for item in record.items:
        sku = (item.commodity_sku or "").strip()
        if not sku:
            continue
        cr = cr_by_sku.get(sku)
        if cr is None:
            continue
        dims = cr["override"].dims if cr.get("override") else cr.get("resolved")
        if dims is None or not dims.is_complete:
            continue
        qty = item.quantity or 1
        total_qty += qty
        total_weight += dims.weight_kg * qty
        sides.append(dims.length_cm)
        sides.append(dims.width_cm)
        sides.append(dims.height_cm)

    # Collect all unique sides across SKUs and sort descending for 3-side check
    unique_sides = sorted(set(sides), reverse=True)
    if len(unique_sides) < 3:
        unique_sides += [0] * (3 - len(unique_sides))

    data = PackageRoutingData(
        package_sn=record.package_sn,
        shop_name=record.shop_name or "",
        warehouse_name=record.logistics.warehouse_name or "",
        destination_country=record.address.country_code or record.address.country or "",
        destination_state=record.address.state_or_region or "",
        postal_code=record.address.postal_code or "",
        longest_side_cm=unique_sides[0],
        second_side_cm=unique_sides[1],
        third_side_cm=unique_sides[2],
        weight_kg=round(total_weight, 2) if total_weight > 0 else 0.0,
        total_quantity=total_qty,
        channel_name=record.logistics.channel_name or "",
    )

    try:
        repo = _get_package_repository()
        engine = RuleEngine.from_yaml(str(rules_path))
        result = engine.route(data)
        # Persist to DB for downstream consumption
        package_db_id = repo.get_package_db_id(
            config["sellfox"]["proxy_account"], record.package_sn
        )
        if package_db_id is not None:
            try:
                repo.upsert_package_routing(
                    package_db_id=package_db_id,
                    carrier=result.carrier,
                    label=result.label,
                    reason=result.reason,
                    rule_name=result.rule_name,
                    matched=result.matched,
                )
            except Exception:
                pass
        return result
    except Exception:
        return None


def _build_vite_ship_from(record) -> dict:
    """Build VITE sender address — strict builder, no fictional fallbacks."""
    from sellfox_shipping.carriers.vite.shipment import _build_ship_from

    warehouses_cfg = config.get("warehouses", {})
    return _build_ship_from(record.logistics.warehouse_name or "", warehouses_cfg)


def _build_vite_ship_to(record) -> dict:
    """Build VITE recipient address — strict builder, no fictional fallbacks."""
    from sellfox_shipping.carriers.vite.shipment import _build_ship_to

    return _build_ship_to(record)


VITE_FEDEX_CHANNEL = (os.getenv("VITE_FEDEX_CHANNEL") or "ODFC").strip()


def _read_env_key(key: str) -> str:
    """Read a value directly from the .env file, bypassing os.environ cache."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return (os.getenv(key) or "").strip()
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            val = v.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                val = val[1:-1]
            return val.strip()
    return (os.getenv(key) or "").strip()


def _get_vite_rate(
    record,
    package_dims: dict | None,
    routing_result,
) -> dict | None:
    """Fetch VITE rate quotes — both GOFO and FedEx, always.

    Converts kg/cm to lbs/inches. Queries both GOFO and FedEx endpoints
    so users can compare pricing. All results are persisted to rate history.
    Excluded shops (platform logistics) are still skipped.
    """
    if routing_result is not None and not routing_result.matched:
        return None

    if not package_dims:
        return {"source": "vite", "error": "Missing package dimensions"}

    try:
        from sellfox_shipping.carriers.vite import ViteGofoClient

        weight_lb = round(package_dims["weight_kg"] * 2.20462, 2)
        length_in = round(package_dims["length_cm"] / 2.54, 1)
        width_in = round(package_dims["width_cm"] / 2.54, 1)
        height_in = round(package_dims["height_cm"] / 2.54, 1)
        max_side_in = max(length_in, width_in, height_in)

        try:
            ship_from = _build_vite_ship_from(record)
            ship_to = _build_vite_ship_to(record)
        except ValueError as exc:
            return {"source": "vite", "error": str(exc)}

        dest_country = (
            record.address.country_code or record.address.country or ""
        ).upper()

        packages = [{
            "weight": weight_lb,
            "length": length_in,
            "width": width_in,
            "height": height_in,
        }]

        api_key = _read_env_key("VITE_API_KEY")
        if not api_key:
            return {"source": "vite", "error": "VITE_API_KEY not configured"}
        vite_base = _read_env_key("VITE_API_BASE_URL") or "https://test-api.vitedirect.com"

        results: list[dict] = []
        best_rate: dict | None = None

        with ViteGofoClient(api_key=api_key, base_url=vite_base) as client:
            # ── GOFO ──
            try:
                gofo_body = {
                    "shipDate": date.today().isoformat(),
                    "serviceType": "GOFO_PARCEL",
                    "channel": "GFUS",
                    "from": ship_from,
                    "to": ship_to,
                    "packages": packages,
                }
                gofo_rate = client.rate_gofo(gofo_body)
                gofo_result = _vite_rate_to_dict(
                    gofo_rate, source="vite_gofo", channel="GFUS",
                    max_side_in=max_side_in, weight_lb=weight_lb,
                )
                results.append(gofo_result)
                _persist_rate(record, gofo_result, raw_response=gofo_rate)
                if best_rate is None:
                    best_rate = gofo_result
            except Exception:
                pass

            # ── FedEx Domestic ──
            if dest_country == "US":
                try:
                    fedex_body = {
                        "shipDate": date.today().isoformat(),
                        "serviceType": "FEDEX_GROUND",
                        "channel": VITE_FEDEX_CHANNEL,
                        "from": ship_from,
                        "to": ship_to,
                        "packages": packages,
                    }
                    fedex_rate = client.rate_fedex(fedex_body)
                    fedex_result = _vite_rate_to_dict(
                        fedex_rate, source="vite_fedex", channel=VITE_FEDEX_CHANNEL,
                        max_side_in=max_side_in, weight_lb=weight_lb,
                    )
                    results.append(fedex_result)
                    _persist_rate(record, fedex_result, raw_response=fedex_rate)
                    # Prefer FedEx for display if it's available
                    if best_rate is None or best_rate.get("source") == "vite_gofo":
                        best_rate = fedex_result
                except Exception:
                    pass

        if best_rate is None:
            return {"source": "vite", "error": "No VITE rates available"}
        return best_rate

    except Exception as exc:
        return {"source": "vite", "error": f"VITE rate fetch failed: {exc}"}


def _vite_rate_to_dict(
    rate: dict, *, source: str, channel: str, max_side_in: float, weight_lb: float
) -> dict:
    """Convert a VITE rate API response to internal rate dict."""
    ad = rate.get("amountDetails") or {}
    return {
        "source": source,
        "service": rate.get("serviceDescription") or source,
        "total_amount": rate.get("totalAmount"),
        "currency": rate.get("currency", "USD"),
        "billing_weight": rate.get("billingWeight"),
        "zone": rate.get("zone"),
        "address_type": str(rate.get("address_type_text", "")),
        "channel": channel,
        "max_side_in": max_side_in,
        "weight_lb": weight_lb,
        "is_fedex": source == "vite_fedex",
    }


# Lizard warehouse → ca_zone mapping (based on S0143 shipper registration)
_LIZARD_CA_ZONE: dict[str, int] = {
    "CENTRADE": 1,  # NJ → 美东
    "DANEEY": 0,    # TX → S0143 not in CA zone
    "POLAND": 0,    # 全域
}


def _get_lizard_rate(
    record,
    package_dims: dict | None,
) -> dict | None:
    """Fetch Lizard (蜴国际) ratesv2 quote and persist all products to history.

    Called independently of routing — always tries to fetch for every package
    with dimensions, so history accumulates both VITE and Lizard quotes.
    The live 运费试算 panel still shows only the routing-suggested carrier.
    """
    if package_dims is None:
        return {"source": "lizard", "error": "Missing package dimensions"}

    try:
        from sellfox_shipping.carriers.lizard.api_client import LizardApiClient

        token = _read_env_key("YIGLOBAL_APP_TOKEN") or os.getenv("LIZARD_APP_TOKEN", "")
        key = _read_env_key("YIGLOBAL_APP_KEY") or os.getenv("LIZARD_APP_KEY", "")
        if not token or not key:
            return {
                "source": "lizard",
                "error": "Lizard credentials not configured (YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY)",
            }

        wh_name = (record.logistics.warehouse_name or "").strip()
        ca_zone = _LIZARD_CA_ZONE.get(wh_name, 0)

        addr = record.address
        body = {
            "weight_unit_type": 2,  # KG/CM
            "ca_zone": ca_zone,
            "parcel_declared_value": 10,
            "parcel_quantity": 1,
            "box_list": [{
                "box_actual_weight": package_dims["weight_kg"],
                "box_length": package_dims["length_cm"],
                "box_width": package_dims["width_cm"],
                "box_height": package_dims["height_cm"],
            }],
            "oa_firstname": (addr.name or "Customer")[:35],
            "oa_company": "",
            "oa_country": (addr.country_code or addr.country or "US").upper(),
            "oa_state": (addr.state_or_region or addr.city or "XX")[:2],
            "oa_city": (addr.city or "")[:28],
            "oa_postcode": (addr.postal_code or "")[:10],
            "oa_street_address1": (addr.address_line_1 or "")[:50],
            "oa_street_address2": (addr.address_line_2 or "")[:35],
            "oa_telphone": (addr.phone or addr.mobile or "0000000000")[:15],
            "oa_doorplate": "",
            "oa_phone_ext": "",
            "signature_service": "SSF",
            "reference_no": record.package_sn,
            "shipper_address": {
                "shipper_name": "Dan-zhao",
                "shipper_postal_code": "77099",
                "shipper_address1": "10812 Fallstone Rd",
                "shipper_address2": "Suite 402",
                "shipper_state_province": "TX",
                "shipper_city": "Houston",
                "shipper_country": "US",
                "shipper_telphone": "2816770938",
            },
        }

        base_url = _read_env_key("YIGLOBAL_API_BASE_URL") or os.getenv(
            "LIZARD_API_BASE_URL", "http://47.106.72.196"
        )

        with LizardApiClient(
            app_token=token, app_key=key, base_url=base_url
        ) as client:
            resp = client.ratesv2(body)

        result = resp.get("result") or {}
        if not isinstance(result, dict) or not result:
            return {"source": "lizard", "error": "No rates returned from Lizard API"}

        # Pick the best rate for live display (lowest total_charge)
        best: dict | None = None
        best_total = float("inf")
        for sm_code, item in result.items():
            if not isinstance(item, dict):
                continue
            raw_total = item.get("total_charge")
            if raw_total is None or str(raw_total).strip() == "":
                continue
            total = float(raw_total)
            if total <= 0:
                continue
            rate_record = {
                "source": "lizard",
                "service": str(sm_code),
                "total_amount": total,
                "currency": str(item.get("currency_code", "USD")),
                "billing_weight": float(item.get("charge_weight", 0) or 0),
                "zone": str(item.get("zone", "")),
                "address_type": str(item.get("address_type_text", "")),
                "channel": str(sm_code),
                "max_side_in": round(package_dims["length_cm"] / 2.54, 1),
                "weight_lb": round(package_dims["weight_kg"] * 2.20462, 2),
                "use_fedex": False,
            }
            _persist_rate(record, rate_record, raw_response=item)
            if total < best_total:
                best_total = total
                best = rate_record

        return best

    except Exception:
        return None


def _persist_rate(record, rate_result: dict, raw_response: dict | None = None) -> None:
    """Best-effort persist of a successful rate fetch to the DB."""
    try:
        repo = _get_package_repository()
        package_db_id = repo.get_package_db_id(
            config["sellfox"]["proxy_account"], record.package_sn
        )
        if package_db_id is not None:
            repo.insert_package_rate(
                package_db_id=package_db_id,
                rate=rate_result,
                raw_data=_json_compact(raw_response) if raw_response else None,
            )
    except Exception:
        pass


def _json_compact(obj) -> str | None:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, default=str, indent=2)
    except Exception:
        return None


def _get_rate_history(repo, record, account_key: str) -> list:
    """Return recent rate fetch history for this package."""
    try:
        package_db_id = repo.get_package_db_id(account_key, record.package_sn)
        if package_db_id is None:
            return []
        return repo.list_package_rates(package_db_id, limit=10)
    except Exception:
        return []


def _get_labels_for_package(account_key: str, package_sn: str) -> list[dict]:
    """Return shipping labels for a package (for Web UI)."""
    try:
        repo = _get_package_repository()
        records = repo.list_labels_for_package(
            account_key=account_key, package_sn=package_sn
        )
        result: list[dict] = []
        for r in records:
            result.append({
                "id": r.id,
                "carrier": r.carrier,
                "service_level": r.service_level,
                "tracking_number": r.tracking_number,
                "carrier_order_id": r.carrier_order_id,
                "total_amount": r.total_amount,
                "currency": r.currency,
                "status": r.status,
                "artifact_id": r.artifact_id,
                "label_url": r.label_url,
                "created_by": r.created_by,
                "created_at": r.created_at,
            })
        return result
    except Exception:
        return []


def _get_enabled_carriers() -> list[dict]:
    """Return carriers with enabled=true from config for UI dropdown."""
    carriers = config.get("carriers", {})
    result: list[dict] = []
    for name, cfg in carriers.items():
        if cfg.get("enabled"):
            result.append({
                "name": name,
                "label": cfg.get("label", name.upper()),
            })
    return result


def _get_lizard_services(repo, record, account_key: str) -> list[dict]:
    """Extract available lizard sm_codes from rate history for this package."""
    seen: set[str] = set()
    services: list[dict] = []
    try:
        db_id = repo.get_package_db_id(account_key, record.package_sn)
        if db_id:
            for r in repo.list_package_rates(db_id, limit=20):
                if r.carrier == "lizard" and r.channel and r.channel not in seen:
                    seen.add(r.channel)
                    services.append({"value": r.channel, "label": r.channel})
    except Exception:
        pass
    # Also include all known sm_codes if rate history is sparse
    _known = [
        "FedEx-Ground-J-TX", "FedEx-21-AHS-TX", "FedEx-21-AHS-USEA",
        "FedEx-Eco-21-TX", "FedEx-Economy-10-HOU", "FedEx-Economy-10-USEA",
        "FedEx-Ground-20-OS-TX", "FedEx-Ground-J-USWE",
    ]
    for sm in _known:
        if sm not in seen:
            services.append({"value": sm, "label": sm})
    return services


@app.post("/packages/{package_sn}/review", response_class=HTMLResponse)
async def package_review_form(request: Request, package_sn: str):
    """HTML form post for local review decision."""
    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    try:
        record = _get_package_review_service().review(
            PackageReviewRequest(
                account_key=account_key,
                package_sn=package_sn,
                actor=_web_actor(request, str(form.get("actor") or "web-user")),
                decision=str(form.get("decision") or ""),
                note=str(form.get("note") or ""),
            )
        )
        message = f"已更新本地审核状态为 {record.local_review_status}"
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        record = _get_package_repository().get(account_key, package_sn)
        if record is None:
            raise HTTPException(404, f"Package {package_sn} not found") from exc
        message = f"审核失败: {exc}"
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
    )


@app.post("/packages/{package_sn}/carton-override", response_class=HTMLResponse)
async def package_carton_override_form(request: Request, package_sn: str):
    """Save manual carton dims for one or more commodity_skus on this package."""
    from sellfox_shipping.carriers.lizard.dims import CartonDims

    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")

    # Support both single-row (legacy) and multi-row (table form) submissions.
    # When multiple rows share the same field name, use getlist to collect them.
    skus = form.getlist("commodity_sku")
    if not skus:
        # Legacy single-row fallback (form.get returns one value)
        sku = str(form.get("commodity_sku") or "").strip()
        skus = [sku] if sku else []

    saved: list[str] = []
    errors: list[str] = []
    for i, sku in enumerate(skus):
        sku = (sku or "").strip()
        if not sku:
            continue
        try:
            weight_kg = float(_form_val_at(form, "weight_kg", i) or 0)
            length_cm = float(_form_val_at(form, "length_cm", i) or 0)
            width_cm = float(_form_val_at(form, "width_cm", i) or 0)
            height_cm = float(_form_val_at(form, "height_cm", i) or 0)
            actor = _web_actor(
                request, str(_form_val_at(form, "actor", i) or "web-user")
            )
            note = str(_form_val_at(form, "note", i) or "").strip()
            if weight_kg <= 0 or length_cm <= 0 or width_cm <= 0 or height_cm <= 0:
                errors.append(f"{sku}: 所有字段必须大于 0")
                continue
            dims = CartonDims(
                weight_kg=weight_kg,
                length_cm=length_cm,
                width_cm=width_cm,
                height_cm=height_cm,
            )
            repo.set_carton_override(
                account_key=account_key,
                commodity_sku=sku,
                dims=dims,
                actor=actor,
                note=note,
            )
            saved.append(sku)
        except (TypeError, ValueError) as exc:
            errors.append(f"{sku}: {exc}")

    parts: list[str] = []
    if saved:
        parts.append(f"已保存 {len(saved)} 个 SKU 重尺补录")
    if errors:
        parts.append(f"失败 {len(errors)}: {'; '.join(errors)}")
    message = "；".join(parts) if parts else "无有效重尺数据可保存"

    record = repo.get(account_key, package_sn)
    assert record is not None
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
    )


def _form_val_at(form, field: str, index: int) -> str | None:
    """Get the index-th value of a multi-value form field."""
    vals = form.getlist(field)
    if index < len(vals):
        return str(vals[index])
    # Legacy single-value fallback (only use when index==0)
    if index == 0:
        v = form.get(field)
        return str(v) if v else None
    return None


@app.post("/packages/{package_sn}/prepare-submit", response_class=HTMLResponse)
async def package_prepare_submit_form(request: Request, package_sn: str):
    """Create SubmissionIntent rows (no HTTP)."""
    from sellfox_shipping.submission_service import SubmissionService

    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    actor = _web_actor(request, str(form.get("actor") or "web-user"))
    try:
        result = SubmissionService(repo).prepare_intents_for_package(
            account_key=account_key,
            package_sn=package_sn,
            actor=actor,
            carrier_name=str(form.get("carrier_name") or "").strip(),
            shipping_service=str(form.get("shipping_service") or "").strip(),
        )
        message = (
            f"已准备提交意图 {len(result.intent_ids)} 条；"
            f"包裹聚合状态 {result.package_submission_state}"
        )
    except Exception as exc:  # noqa: BLE001
        message = f"准备提交失败: {exc}"
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
    )


@app.post("/packages/{package_sn}/submit-label-tracking", response_class=HTMLResponse)
async def package_submit_label_tracking_form(request: Request, package_sn: str):
    """Write a valid label's tracking number back to Sellfox (real submitToPlatform).

    Sources the tracking from the package's non-cancelled label record, prepares
    intents with it, and submits them for real. The button click is the user's
    explicit confirmation of this side-effecting call.
    """
    from sellfox_shipping.submission_service import SubmissionService

    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    actor = _web_actor(request, str(form.get("actor") or "web-user"))
    try:
        result = SubmissionService(repo, _get_client()).submit_label_tracking(
            account_key=account_key,
            package_sn=package_sn,
            actor=actor,
        )
        message = (
            f"已回写面单追踪号 {result.tracking_number} → 赛狐；"
            f"意图 {result.intent_ids} 状态 {result.intent_statuses}；"
            f"HTTP {'已调用' if result.http_called else '未调用'}"
        )
    except Exception as exc:  # noqa: BLE001
        message = f"回写赛狐失败: {exc}"
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
    )


@app.post("/packages/{package_sn}/create-label", response_class=HTMLResponse)
async def package_create_label_form(request: Request, package_sn: str):
    """HTML form post to create a shipping label."""
    from sellfox_shipping.label_service import LabelService, LabelServiceError

    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")

    actor = _web_actor(request, str(form.get("actor") or "web-user"))
    carrier = str(form.get("carrier") or "vite").strip()
    service_level = str(form.get("service_level") or "").strip()

    try:
        svc = LabelService(repo)
        result = svc.create_label(
            carrier=carrier,
            package=record,
            account_key=account_key,
            actor=actor,
            service_level=service_level,
        )
        message = (
            f"面单创建成功 — 追踪号: {result.get('tracking_number', '—')} | "
            f"订单号: {result.get('carrier_order_id', '—')}"
        )
    except LabelServiceError as exc:
        message = f"面单创建失败: {exc}"
    except Exception as exc:
        message = f"面单创建失败: {exc}"

    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
    )


@app.post(
    "/packages/{package_sn}/submit-intent/{intent_id}",
    response_class=HTMLResponse,
)
async def package_submit_intent_dry_run(
    request: Request,
    package_sn: str,
    intent_id: int,
):
    """Dry-run one intent from Web (never calls submitToPlatform)."""
    from sellfox_shipping.submission_service import SubmissionService

    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    actor = _web_actor(request, str(form.get("actor") or "web-user"))
    try:
        result = SubmissionService(repo).submit_intent(
            intent_id=intent_id,
            actor=actor,
            dry_run=True,
            allow_side_effects=False,
        )
        message = (
            f"Intent #{intent_id} dry-run OK；状态 {result.intent_status}；"
            f"聚合 {result.package_submission_state}（未调用 HTTP）"
        )
    except Exception as exc:  # noqa: BLE001
        message = f"dry-run 失败: {exc}"
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
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
                actor=_web_actor(request, actor),
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
        batch_hint = (
            f" 批次 #{result.batch_id} 已登记（全跳过）。"
            if result.batch_id
            else ""
        )
        return templates.TemplateResponse(
            request,
            "lizard_export.html",
            {
                "message": "",
                "error": (
                    f"没有可导出的行（候选 {result.total_candidates}，"
                    f"跳过 {result.skipped}）。请确认本地审核为 approved，"
                    f"渠道名含「蜴」，且重尺可查。{batch_hint}"
                ),
                "skipped_rows": result.skipped_rows,
                "default_actor": actor,
                "default_shipper": shipper_code,
                "default_limit": limit,
            },
            status_code=400,
        )
    download_name = output_path.name
    headers: dict[str, str] = {}
    if result.batch_id is not None:
        download_name = (
            f"lizard-upload-batch{result.batch_id}-{stamp}.xlsx"
        )
        headers["X-Shipping-Batch-Id"] = str(result.batch_id)
    return FileResponse(
        path=str(output_path),
        filename=download_name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers=headers or None,
    )


@app.get("/lizard/import", response_class=HTMLResponse)
async def lizard_import_page(
    request: Request,
    batch_id: int | None = Query(None),
):
    """Form to import lizard tracking-return Excel (local DB only)."""
    return templates.TemplateResponse(
        request,
        "lizard_import.html",
        {
            "result": None,
            "error": "",
            "default_actor": "web-user",
            "default_batch_id": batch_id or "",
        },
    )


@app.post("/lizard/import", response_class=HTMLResponse)
async def lizard_import_form(
    request: Request,
    actor: str = Form("web-user"),
    batch_id: str = Form(""),
    file: UploadFile = File(...),
):
    """Parse return Excel, persist tracking locally, show reconciliation report."""
    import tempfile

    from sellfox_shipping.lizard_batch import (
        ImportLizardTrackingService,
        LizardImportRequest,
    )

    suffix = Path(file.filename or "return.xlsx").suffix or ".xlsx"
    parsed_batch_id: int | None = None
    batch_raw = (batch_id or "").strip()
    if batch_raw:
        try:
            parsed_batch_id = int(batch_raw)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "lizard_import.html",
                {
                    "result": None,
                    "error": f"批次 ID 无效: {exc}",
                    "default_actor": actor,
                    "default_batch_id": batch_raw,
                },
                status_code=400,
            )
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
                    actor=_web_actor(request, actor),
                    input_path=tmp_path,
                    batch_id=parsed_batch_id,
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
                "default_batch_id": batch_raw,
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
            "default_batch_id": result.batch_id or batch_raw,
        },
    )


@app.get("/labels", response_class=HTMLResponse)
async def labels_transaction_page(
    request: Request,
    days: int = Query(2, ge=1, le=30, description="Days to look back"),
):
    """Transaction history for financial reconciliation."""
    from datetime import datetime, timedelta, timezone

    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()

    # Query labels from shipping_labels table for last N days
    all_labels: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # Get all packages, then their labels (keeping it simple)
    try:
        from sqlalchemy import text
        with repo.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT l.id, l.carrier, l.service_level, l.tracking_number,
                           l.carrier_order_id, l.total_amount, l.currency,
                           l.status, l.created_by, l.created_at
                    FROM shipping_labels l
                    WHERE l.created_at >= :cutoff
                    ORDER BY l.created_at DESC
                    LIMIT 200
                """),
                {"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S")},
            )
            for row in rows:
                all_labels.append({
                    "id": row[0], "carrier": row[1], "service_level": row[2],
                    "tracking_number": row[3], "carrier_order_id": row[4],
                    "total_amount": row[5], "currency": row[6] or "USD",
                    "status": row[7], "created_by": row[8],
                    "created_at": row[9],
                })
    except Exception:
        pass

    # Summary
    summary: dict[str, dict] = {}
    for lb in all_labels:
        c = lb["carrier"]
        if c not in summary:
            summary[c] = {"count": 0, "total": 0.0, "generated": 0, "cancelled": 0}
        summary[c]["count"] += 1
        if lb["total_amount"]:
            summary[c]["total"] += lb["total_amount"]
        if lb["status"] == "generated":
            summary[c]["generated"] += 1
        elif lb["status"] == "cancelled":
            summary[c]["cancelled"] += 1

    return templates.TemplateResponse(
        request,
        "labels_transaction.html",
        {
            "labels": all_labels,
            "summary": summary,
            "days": days,
            "account_key": account_key,
        },
    )


@app.get("/lizard/batches", response_class=HTMLResponse)
async def lizard_batches_page(
    request: Request,
    limit: int = Query(50, le=200),
):
    """List ShippingBatch rows for current account."""
    account_key = config["sellfox"]["proxy_account"]
    items = _get_package_repository().list_batches(
        account_key=account_key,
        limit=limit,
    )
    return templates.TemplateResponse(
        request,
        "lizard_batches.html",
        {
            "account_key": account_key,
            "items": items,
        },
    )


@app.get("/lizard/batches/{batch_id}", response_class=HTMLResponse)
async def lizard_batch_detail(request: Request, batch_id: int):
    """Show one batch and its package rows."""
    repo = _get_package_repository()
    batch = repo.get_batch(batch_id)
    if batch is None:
        raise HTTPException(404, f"Batch {batch_id} not found")
    packages = repo.list_batch_packages(batch_id)
    return templates.TemplateResponse(
        request,
        "lizard_batch_detail.html",
        {
            "batch": batch,
            "packages": packages,
        },
    )


@app.get("/lizard/artifacts", response_class=HTMLResponse)
async def lizard_artifacts_page(
    request: Request,
    kind: str | None = Query(None),
    limit: int = Query(50, le=200),
):
    """List registered export/import file artifacts (content_hash deduped on disk)."""
    account_key = config["sellfox"]["proxy_account"]
    items = _get_package_repository().list_artifacts(
        account_key=account_key,
        kind=kind or None,
        limit=limit,
    )
    return templates.TemplateResponse(
        request,
        "lizard_artifacts.html",
        {
            "account_key": account_key,
            "kind": kind or "",
            "items": items,
        },
    )


@app.get("/lizard/artifacts/{artifact_id}/download")
async def lizard_artifact_download(artifact_id: int):
    """Download the blob for an artifact (by content_hash storage path)."""
    repo = _get_package_repository()
    record = repo.get_artifact(artifact_id)
    if record is None:
        raise HTTPException(404, f"Artifact {artifact_id} not found")
    path = repo.resolve_artifact_path(record)
    if not path.is_file():
        raise HTTPException(404, "Artifact blob missing on disk")
    return FileResponse(
        path=str(path),
        filename=record.file_name,
        media_type=record.mime_type
        or "application/octet-stream",
    )


# ── MCP mount — appended in main.py after FastMCP server is created ──


@app.get("/packages/{package_sn}/sku-label")
async def package_sku_label_download(package_sn: str, inline: bool = False):
    """Download or preview SKU back-sticker PDF for a package."""
    import os, tempfile
    from pathlib import Path
    from sellfox_shipping.sku_label import SkuNameLookup, generate_sku_label_pdf
    from sellfox_shipping.env_loader import load_dotenv

    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")

    # Collect SKUs
    items_data: list[dict] = []
    skus: set[str] = set()
    for item in record.items:
        sku = (item.commodity_sku or "").strip()
        if sku:
            skus.add(sku)
            items_data.append({"commodity_sku": sku, "qty": item.quantity or 1})

    if not items_data:
        raise HTTPException(400, "No commodity SKUs in this package")

    # Lookup names
    erp_base = os.getenv("ERP_URL", "https://erpnext.vilavi.cn")
    erp_key = ""
    erp_secret = ""
    _env_path = Path(__file__).resolve().parents[1] / "EN_API" / ".env"
    if _env_path.is_file():
        for line in _env_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "PROD_ERP_API_KEY":
                erp_key = v.strip().strip("'\"")
            elif k.strip() == "PROD_ERP_API_SECRET":
                erp_secret = v.strip().strip("'\"")
    erp_key = erp_key or os.getenv("ERP_API_KEY", "")
    erp_secret = erp_secret or os.getenv("ERP_API_SECRET", "")

    lookup = SkuNameLookup(erpnext_base=erp_base, erpnext_api_key=erp_key, erpnext_api_secret=erp_secret)
    lookup.prefetch(list(skus))

    pdf_items: list[dict] = []
    for item in items_data:
        name = lookup.get(item["commodity_sku"])
        pdf_items.append({
            "sku": name["sku"],
            "qty": item["qty"],
            "cn_name": name["cn"],
            "es_name": name["es"],
        })
    lookup.close()

    warehouse = record.logistics.warehouse_name or ""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        generate_sku_label_pdf(
            [{"package_sn": package_sn, "items": pdf_items}],
            tmp.name,
            timestamp=datetime.now().strftime("%Y-%m-%d"),
            warehouse_class=warehouse,
        )
        return FileResponse(
            tmp.name,
            filename=f"sku_label_{package_sn}.pdf",
            media_type="application/pdf",
            content_disposition_type="inline" if inline else "attachment",
        )
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise


@app.post("/api/packages/batch-print")
async def batch_print_packages(request: Request):
    """Merge label/sticker PDFs for selected packages into one preview."""
    import io, tempfile, traceback
    import fitz

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    package_sns: list[str] = body.get("package_sns", [])
    doc_type: str = body.get("document_type", "both")
    if not package_sns:
        raise HTTPException(400, "No package_sns provided")

    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()

    merged = fitz.open()
    skipped: list[str] = []

    # ── Phase 1: collect all documents first ──
    docs: list[dict] = []  # {sn, sticker_bytes, label_bytes}
    for sn in package_sns:
        record = repo.get(account_key, sn)
        if record is None:
            skipped.append(f"{sn}: 包裹不存在")
            continue

        sticker_bytes: bytes | None = None
        label_bytes: bytes | None = None

        # ── Sticker ──
        if doc_type in ("sticker", "both"):
            items_data: list[dict] = []
            skus: set[str] = set()
            for item in record.items:
                sku = (item.commodity_sku or "").strip()
                if sku:
                    skus.add(sku)
                    items_data.append({"commodity_sku": sku, "qty": item.quantity or 1})
            if not items_data:
                skipped.append(f"{sn}: 无商品SKU，无法生成背贴")
            else:
                erp_key = os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY", "")
                erp_secret = os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET", "")
                erp_base = os.getenv("ERP_URL", "https://erpnext.vilavi.cn")
                try:
                    from sellfox_shipping.sku_label import SkuNameLookup, generate_sku_label_pdf
                    lookup = SkuNameLookup(erpnext_base=erp_base, erpnext_api_key=erp_key, erpnext_api_secret=erp_secret)
                    lookup.prefetch(list(skus))
                    pdf_items: list[dict] = []
                    for it in items_data:
                        name = lookup.get(it["commodity_sku"])
                        pdf_items.append({
                            "sku": name["sku"], "qty": it["qty"],
                            "cn_name": name["cn"], "es_name": name["es"],
                        })
                    lookup.close()
                    warehouse = record.logistics.warehouse_name or ""
                    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                    tmp.close()
                    try:
                        generate_sku_label_pdf(
                            [{"package_sn": sn, "items": pdf_items}], tmp.name,
                            timestamp=datetime.now().strftime("%Y-%m-%d"),
                            warehouse_class=warehouse,
                        )
                        sticker_bytes = Path(tmp.name).read_bytes()
                    finally:
                        Path(tmp.name).unlink(missing_ok=True)
                except Exception:
                    traceback.print_exc()
                if not sticker_bytes:
                    skipped.append(f"{sn}: 无法生成背贴")
        if doc_type in ("sticker", "both") and not sticker_bytes:
            continue  # skip this package entirely

        # ── Label ──
        if doc_type in ("label", "both"):
            labels = repo.list_labels_for_package(account_key=account_key, package_sn=sn)
            active = [lbl for lbl in labels if getattr(lbl, "status", None) != "cancelled"]
            if active:
                lbl = active[0]
                if getattr(lbl, "artifact_id", None):
                    artifact = repo.get_artifact(lbl.artifact_id)
                    if artifact:
                        path = repo.resolve_artifact_path(artifact)
                        if path.is_file():
                            label_bytes = path.read_bytes()
            if not label_bytes:
                skipped.append(f"{sn}: 无有效Label面单")
        if doc_type in ("label", "both") and not label_bytes:
            continue  # skip this package entirely

        docs.append({"sn": sn, "sticker": sticker_bytes, "label": label_bytes})

    # ── Hard validation: both mode requires both documents for every package ──
    if skipped:
        raise HTTPException(
            422,
            f"校验失败 — 以下包裹缺少文档，已拒绝打印:\n" + "\n".join(skipped),
        )

    # ── Phase 2: merge in strict order (sticker → label, per package) ──
    for d in docs:
        if doc_type == "both":
            src_s = fitz.open(stream=d["sticker"], filetype="pdf")
            merged.insert_pdf(src_s)
            src_s.close()
            src_l = fitz.open(stream=d["label"], filetype="pdf")
            merged.insert_pdf(src_l)
            src_l.close()
        elif doc_type == "sticker":
            src = fitz.open(stream=d["sticker"], filetype="pdf")
            merged.insert_pdf(src)
            src.close()
        elif doc_type == "label":
            src = fitz.open(stream=d["label"], filetype="pdf")
            merged.insert_pdf(src)
            src.close()

    if len(merged) == 0:
        raise HTTPException(400, f"无有效文档可合并。跳过: {'; '.join(skipped)}")

    buf = io.BytesIO()
    merged.save(buf)
    merged.close()
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=batch_print.pdf"},
    )


@app.post("/api/packages/batch-export")
async def batch_export_packages(request: Request):
    """Export selected package data as CSV (Excel-compatible)."""
    import csv, io

    body = await request.json()
    package_sns: list[str] = body.get("package_sns", [])
    if not package_sns:
        raise HTTPException(400, "No package_sns provided")

    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "包裹号", "赛狐状态", "本地审核", "渠道", "店铺", "追踪号", "站点",
        "建议承运商", "匹配规则", "路由状态",
        "收货人", "电话", "城市/州", "邮编", "国家", "地址",
    ])

    for sn in package_sns:
        record = repo.get(account_key, sn)
        if record is None:
            continue
        addr = record.address
        state_region = (addr.state_or_region or "").strip()
        city_state = addr.city or ""
        if state_region:
            city_state = f"{city_state}/{state_region}" if city_state else state_region

        phone = addr.phone or addr.mobile or ""
        address_line = addr.address_line_1 or ""
        if addr.address_line_2:
            address_line += " " + addr.address_line_2

        # Routing: cached first, compute on-the-fly if missing
        route_label = route_rule = route_status = ""
        db_id = repo.get_package_db_id(account_key, sn)
        if db_id is not None:
            routing = repo.get_package_routing(db_id)
            if routing is not None:
                route_label = routing.label
                route_rule = routing.rule_name
                route_status = "已匹配" if routing.matched else "已排除"
        # Fallback: compute routing on-the-fly
        if not route_label:
            try:
                carton_rows = _carton_rows_for_package(account_key, record)
                computed = _compute_routing(record, carton_rows)
                if computed:
                    route_label = computed.get("label", "")
                    route_rule = computed.get("rule_name", "")
                    route_status = "已匹配" if computed.get("matched") else "已排除"
            except Exception:
                pass

        writer.writerow([
            record.package_sn,
            record.package_status or "",
            record.local_review_status or "",
            record.logistics.channel_name or "",
            record.shop_name or "",
            record.logistics.tracking_number or "",
            record.marketplace or "",
            route_label,
            route_rule,
            route_status,
            addr.name or "",
            phone,
            city_state,
            addr.postal_code or "",
            addr.country or "",
            address_line.strip(),
        ])

    buf.seek(0)
    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=packages_export.csv"},
    )


def mount_mcp(mcp_app):
    """Mount FastMCP ASGI app. Called from main.py after MCP tools are defined."""
    app.mount("/mcp", mcp_app)
    return app
