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
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
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
    """Override → commodity pageList → ERPNext ZLMB."""
    from sellfox_shipping.carriers.lizard.cascade import CascadingDimsLookup
    from sellfox_shipping.carriers.lizard.commodity_dims import CommodityPageListDimsLookup
    from sellfox_shipping.carriers.lizard.erpnext_dims import ErpnextZlmbDimsLookup
    from sellfox_shipping.carriers.lizard.override_dims import RepositoryDimsLookup
    from sellfox_shipping.env_loader import load_dotenv as _load_env

    _load_env(Path(__file__).resolve().parents[1] / "EN_API" / ".env")
    _load_env()

    repo = _get_package_repository()
    account_key = config["sellfox"]["proxy_account"]
    override = RepositoryDimsLookup(repo, account_key)
    primary = CommodityPageListDimsLookup(
        proxy_base_url=config["sellfox"]["proxy_base_url"],
        proxy_account=account_key,
        proxy_api_key=os.getenv("SELLFOX_PROXY_API_KEY", ""),
    )
    erp_key = (
        os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY") or ""
    ).strip()
    erp_secret = (
        os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET") or ""
    ).strip()
    if not erp_key or not erp_secret:
        return CascadingDimsLookup(override, primary)
    erp_url = (os.getenv("ERP_URL") or "https://erpnext.vilavi.cn").strip().rstrip(
        "/"
    )
    fallback = ErpnextZlmbDimsLookup(
        base_url=erp_url,
        api_key=erp_key,
        api_secret=erp_secret,
    )
    return CascadingDimsLookup(override, primary, fallback)


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
            package_status=status or None,
            channel_name=channel or None,
            local_review_status=review or None,
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
    account_key = config["sellfox"]["proxy_account"]
    record = _get_package_repository().get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=""),
    )


def _package_detail_context(account_key: str, record, *, message: str) -> dict:
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
    return {
        "package": record,
        "message": message,
        "carton_rows": _carton_rows_for_package(account_key, record),
        "submission_intents": intents,
        "package_submission_state": package_submission_state,
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
        resolved = lookup.get(sku)
        rows.append(
            {
                "commodity_sku": sku,
                "override": override,
                "resolved": resolved,
                "source": (
                    "override"
                    if override is not None
                    else ("cascade" if resolved is not None else "missing")
                ),
            }
        )
    return rows


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
    """Save manual carton dims for a commodity_sku on this package."""
    from sellfox_shipping.carriers.lizard.dims import CartonDims

    form = await request.form()
    account_key = config["sellfox"]["proxy_account"]
    repo = _get_package_repository()
    record = repo.get(account_key, package_sn)
    if record is None:
        raise HTTPException(404, f"Package {package_sn} not found")
    sku = str(form.get("commodity_sku") or "").strip()
    actor = _web_actor(request, str(form.get("actor") or "web-user"))
    note = str(form.get("note") or "").strip()
    try:
        dims = CartonDims(
            weight_kg=float(form.get("weight_kg") or 0),
            length_cm=float(form.get("length_cm") or 0),
            width_cm=float(form.get("width_cm") or 0),
            height_cm=float(form.get("height_cm") or 0),
        )
        repo.set_carton_override(
            account_key=account_key,
            commodity_sku=sku,
            dims=dims,
            actor=actor,
            note=note,
        )
        message = f"已保存重尺补录：{sku}"
    except (TypeError, ValueError) as exc:
        message = f"重尺补录失败: {exc}"
    record = repo.get(account_key, package_sn)
    assert record is not None
    return templates.TemplateResponse(
        request,
        "package_detail.html",
        _package_detail_context(account_key, record, message=message),
    )


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

def mount_mcp(mcp_app):
    """Mount FastMCP ASGI app. Called from main.py after MCP tools are defined."""
    app.mount("/mcp", mcp_app)
    return app
