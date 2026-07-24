"""Typer CLI for sellfox-shipping.

Agent-friendly CLI design:
  - --json flag for structured output (default when stdout is piped)
  - TTY detection for auto behavior switching
  - No interactive prompts
  - --dry-run mode
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml

app = typer.Typer(
    name="sellfox-shipping",
    help="赛狐尾程打单系统 CLI",
    no_args_is_help=True,
)

# ── Helpers ───────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

from sellfox_shipping.env_loader import load_dotenv

load_dotenv()


def _load_config() -> dict:
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _output(data, json_mode: bool = False):
    """Output data — JSON for agents, pretty format for humans."""
    if json_mode or not sys.stdout.isatty():
        typer.echo(json.dumps(data, ensure_ascii=False, default=str, indent=2))
    elif isinstance(data, list):
        for item in data:
            typer.echo(json.dumps(item, ensure_ascii=False, default=str))
    else:
        typer.echo(json.dumps(data, ensure_ascii=False, default=str, indent=2))


def _get_store():
    from sellfox_shipping.store import Store
    config = _load_config()
    db_path = BASE_DIR / config.get("store", {}).get("db_path", "data/shipping.db")
    return Store(db_path=str(db_path))


def _get_client():
    import os
    from sellfox_shipping.sellfox_client import SellfoxClient

    app_id = os.getenv("SELLFOX_APP_ID", "").strip()
    app_secret = os.getenv("SELLFOX_APP_SECRET", "").strip()
    if app_id and app_secret:
        from sellfox_shipping.direct_sellfox_client import DirectSellfoxClient
        return DirectSellfoxClient()

    config = _load_config()
    return SellfoxClient(
        proxy_base_url=config["sellfox"]["proxy_base_url"],
        proxy_account=config["sellfox"]["proxy_account"],
        proxy_api_key=os.getenv("SELLFOX_PROXY_API_KEY", ""),
    )


def _get_package_repository():
    from sellfox_shipping.package_repository import PackageRepository

    config = _load_config()
    db_path = BASE_DIR / config.get("store", {}).get("db_path", "data/shipping.db")
    return PackageRepository(db_path)


def _get_package_sync_service():
    from sellfox_shipping.package_service import SyncPackagesService

    return SyncPackagesService(
        gateway=_get_client(),
        repository=_get_package_repository(),
    )


def _get_package_list_service():
    from sellfox_shipping.package_service import ListPackagesService

    return ListPackagesService(_get_package_repository())


# ── Commands ──────────────────────────────────────────────────────

@app.command()
def fetch(
    date_start: str = typer.Option(..., help="Start date (yyyy-MM-dd)"),
    date_end: str = typer.Option(..., help="End date (yyyy-MM-dd)"),
    status: Optional[str] = typer.Option(None, help="Order status filter"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without saving"),
):
    """Pull orders from Sellfox into local store."""
    if dry_run:
        _output({"would_fetch": True, "date_start": date_start, "date_end": date_end, "status": status}, json_output)
        return

    store = _get_store()
    client = _get_client()

    all_orders = []
    page_no = 1
    total = 0
    while True:
        orders, total = client.fetch_orders(
            date_start=date_start, date_end=date_end,
            status=status, page_no=page_no, page_size=50,
        )
        for o in orders:
            store.upsert_order(o)
        all_orders.extend(orders)
        if page_no * 50 >= total:
            break
        page_no += 1

    _output({"fetched": len(all_orders), "total_in_sellfox": total}, json_output)


@app.command("packages-sync")
def packages_sync(
    date_start: str = typer.Option(..., help="Start date (yyyy-MM-dd)"),
    date_end: str = typer.Option(..., help="End date (yyyy-MM-dd)"),
    actor: str = typer.Option(..., help="Operator identity for the audit report"),
    status: Optional[str] = typer.Option(None, help="Sellfox package status"),
    page_size: int = typer.Option(50, min=1, max=200),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Synchronize Sellfox package-processing records into the package store."""
    from sellfox_shipping.package_service import PackageSyncRequest

    config = _load_config()
    request = PackageSyncRequest(
        account_key=config["sellfox"]["proxy_account"],
        date_start=date_start,
        date_end=date_end,
        actor=actor,
        status=status,
        page_size=page_size,
    )
    report = _get_package_sync_service().sync(request)
    payload = report.model_dump(mode="json")
    payload["is_reconciled"] = report.is_reconciled
    payload["remaining_count"] = report.remaining_count
    _output(payload, json_output)
    if report.sync_status != "completed":
        raise typer.Exit(1)


@app.command("packages-list")
def packages_list(
    status: Optional[str] = typer.Option(None, help="Filter by package_status"),
    channel: Optional[str] = typer.Option(None, help="Filter by channel_name"),
    limit: int = typer.Option(50, min=1, max=500, help="Max results"),
    offset: int = typer.Option(0, min=0, help="Offset for pagination"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List local package summaries from the package store."""
    from sellfox_shipping.package_service import PackageListRequest

    config = _load_config()
    result = _get_package_list_service().list(
        PackageListRequest(
            account_key=config["sellfox"]["proxy_account"],
            package_status=status,
            channel_name=channel,
            limit=limit,
            offset=offset,
        )
    )
    _output(result.model_dump(mode="json"), json_output)


def _get_lizard_dims_lookup():
    """Local override → EN ZLMB# (V2 with sibling borrowing)."""
    import os
    from pathlib import Path

    from sellfox_shipping.carriers.lizard.cascade import CascadingDimsLookup
    from sellfox_shipping.carriers.lizard.erpnext_dims_v2 import ErpnextDimsLookupV2
    from sellfox_shipping.carriers.lizard.override_dims import RepositoryDimsLookup
    from sellfox_shipping.env_loader import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "EN_API" / ".env")
    load_dotenv()

    config = _load_config()
    account_key = config["sellfox"]["proxy_account"]
    override = RepositoryDimsLookup(_get_package_repository(), account_key)
    lookups: list = [override]

    erp_key = (
        os.getenv("PROD_ERP_API_KEY")
        or os.getenv("ERP_API_KEY")
        or ""
    ).strip()
    erp_secret = (
        os.getenv("PROD_ERP_API_SECRET")
        or os.getenv("ERP_API_SECRET")
        or ""
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


@app.command("lizard-export")
def lizard_export(
    output: Path = typer.Option(..., "--output", "-o", help="Output xlsx path"),
    actor: str = typer.Option("cli", help="Actor for audit"),
    limit: int = typer.Option(500, min=1, max=5000),
    shipper_code: str = typer.Option("S0143", help="Lizard shipper / sub-account code"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Export approved 蜴国际 packages to lizard upload Excel (P1B)."""
    from sellfox_shipping.lizard_batch import (
        ExportLizardUploadService,
        LizardExportRequest,
    )

    config = _load_config()
    repo = _get_package_repository()
    result = ExportLizardUploadService(repo, _get_lizard_dims_lookup()).export(
        LizardExportRequest(
            account_key=config["sellfox"]["proxy_account"],
            actor=actor,
            output_path=output,
            limit=limit,
            shipper_code=shipper_code,
        )
    )
    _output(result.model_dump(mode="json"), json_output)
    if result.exported == 0:
        raise typer.Exit(1)


@app.command("lizard-import-tracking")
def lizard_import_tracking(
    input_path: Path = typer.Option(..., "--input", "-i", help="Lizard return xlsx"),
    actor: str = typer.Option("cli", help="Actor for audit"),
    batch_id: Optional[int] = typer.Option(
        None, "--batch-id", help="Optional ShippingBatch id to update"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Parse lizard tracking-return Excel and reconcile by package_sn (P1B)."""
    from sellfox_shipping.lizard_batch import (
        ImportLizardTrackingService,
        LizardImportRequest,
    )

    config = _load_config()
    result = ImportLizardTrackingService(_get_package_repository()).import_file(
        LizardImportRequest(
            account_key=config["sellfox"]["proxy_account"],
            actor=actor,
            input_path=input_path,
            batch_id=batch_id,
        )
    )
    _output(result.model_dump(mode="json"), json_output)
    if result.unmatched:
        raise typer.Exit(2)


@app.command("packages-prepare-submit")
def packages_prepare_submit(
    package_sn: str = typer.Option(..., "--package-sn", help="Sellfox packageSn"),
    actor: str = typer.Option("cli", help="Actor for audit"),
    carrier_name: str = typer.Option("", help="Override carrier name"),
    shipping_service: str = typer.Option("", help="Optional ship service"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create SubmissionIntent rows for an approved package (no HTTP)."""
    from sellfox_shipping.submission_service import SubmissionService

    config = _load_config()
    result = SubmissionService(_get_package_repository()).prepare_intents_for_package(
        account_key=config["sellfox"]["proxy_account"],
        package_sn=package_sn,
        actor=actor,
        carrier_name=carrier_name or "",
        shipping_service=shipping_service or "",
    )
    _output(result.__dict__, json_output)


@app.command("packages-submit-intent")
def packages_submit_intent(
    intent_id: int = typer.Option(..., "--intent-id", help="SubmissionIntent id"),
    actor: str = typer.Option("cli", help="Actor for audit"),
    dry_run: bool = typer.Option(True, help="Preview only; no HTTP (default)"),
    i_understand_side_effects: bool = typer.Option(
        False,
        "--i-understand-side-effects",
        help="Allow real submitToPlatform (requires --no-dry-run)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Submit one intent (default dry-run; real call needs explicit side-effect flag)."""
    from sellfox_shipping.submission_rate_limit import SqliteSubmitRateLimiter
    from sellfox_shipping.submission_service import SubmissionService

    config = _load_config()
    repo = _get_package_repository()
    client = _get_client() if (not dry_run and i_understand_side_effects) else None
    interval = float(
        config.get("sellfox", {}).get("submit_min_interval_seconds", 2.0)
    )
    db_path = BASE_DIR / config.get("store", {}).get("db_path", "data/shipping.db")
    result = SubmissionService(
        repo,
        client,
        rate_limiter=SqliteSubmitRateLimiter(db_path, interval),
    ).submit_intent(
        intent_id=intent_id,
        actor=actor,
        dry_run=dry_run,
        allow_side_effects=i_understand_side_effects and not dry_run,
    )
    _output(result.__dict__, json_output)


@app.command("packages-verify-intent")
def packages_verify_intent(
    intent_id: int = typer.Option(..., "--intent-id", help="SubmissionIntent id"),
    actor: str = typer.Option("cli", help="Actor for audit"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Promote SUCCESS → VERIFIED via packageDetail readback (no submit)."""
    from sellfox_shipping.submission_service import SubmissionService

    repo = _get_package_repository()
    result = SubmissionService(repo, _get_client()).verify_intent_from_readback(
        intent_id=intent_id,
        actor=actor,
    )
    _output(result.__dict__, json_output)


@app.command()
def orders(
    status: Optional[str] = typer.Option(None, help="Filter by package_status"),
    limit: int = typer.Option(20, help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List orders in local store."""
    store = _get_store()
    orders = store.list_orders(status=status, limit=limit)
    total = store.count_orders(status=status)
    _output({
        "total": total,
        "count": len(orders),
        "orders": [
            {
                "amazon_order_id": o.amazon_order_id,
                "package_sn": o.package_sn,
                "shop_name": o.shop_name,
                "package_status": o.package_status.value,
                "item_count": len(o.items),
            }
            for o in orders
        ],
    }, json_output)


@app.command()
def status(
    amazon_order_id: str = typer.Argument(..., help="Amazon order ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check the shipping status of an order."""
    store = _get_store()
    order = store.get_order(amazon_order_id)
    if not order:
        _output({"error": f"Order {amazon_order_id} not found"}, json_output)
        raise typer.Exit(1)

    labels = store.get_labels_for_order(order.id)
    _output({
        "amazon_order_id": order.amazon_order_id,
        "package_status": order.package_status.value,
        "labels": [
            {"carrier": l.carrier, "tracking": l.tracking_number, "status": l.status, "cost": l.cost}
            for l in labels
        ],
    }, json_output)


@app.command()
def carriers(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List configured carriers."""
    config = _load_config()
    data = {
        name: {"enabled": cfg.get("enabled", False), "label": cfg.get("label", name)}
        for name, cfg in config.get("carriers", {}).items()
    }
    _output(data, json_output)


@app.command()
def rules(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List shipping rules."""
    config = _load_config()
    _output(config.get("rules", []), json_output)


@app.command("packages-rate-history")
def packages_rate_history(
    package_sn: str = typer.Option(..., "--package-sn", help="Sellfox packageSn"),
    limit: int = typer.Option(10, min=1, max=50, help="Max history rows (default 10)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Query VITE rate quote history for a package (AI-operable JSON output)."""
    config = _load_config()
    repo = _get_package_repository()
    package_db_id = repo.get_package_db_id(
        config["sellfox"]["proxy_account"], package_sn
    )
    if package_db_id is None:
        _output({"error": f"Package {package_sn} not found"}, json_output)
        raise typer.Exit(1)

    rates = repo.list_package_rates(package_db_id, limit=limit)
    _output(
        [
            {
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
                "carrier": r.carrier,
                "service": r.service,
                "total_amount": r.total_amount,
                "currency": r.currency,
                "billing_weight_lb": r.billing_weight,
                "zone": r.zone,
                "channel": r.channel,
                "max_side_in": r.max_side_in,
                "weight_lb": r.weight_lb,
                "is_fedex": r.is_fedex,
                "raw_data": r.raw_data,
            }
            for r in rates
        ],
        json_output,
    )


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8401, help="Bind port"),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Auto-reload on code change (local dev only; production keep off)",
    ),
):
    """Start the web server (FastAPI; FastMCP mounted when installed)."""
    import uvicorn

    typer.echo(f"Starting sellfox-shipping on {host}:{port}")
    typer.echo(f"  Web UI:     http://{host}:{port}/packages")
    typer.echo(f"  Export:     http://{host}:{port}/lizard/export")
    typer.echo(f"  Import:     http://{host}:{port}/lizard/import")
    typer.echo(f"  Artifacts:  http://{host}:{port}/lizard/artifacts")
    typer.echo(f"  Batches:    http://{host}:{port}/lizard/batches")
    typer.echo(f"  REST:       http://{host}:{port}/api/")
    if reload:
        typer.echo("  Reload:     ON (code changes auto-restart)")
    try:
        import fastmcp  # noqa: F401
    except ImportError:
        typer.echo("  MCP:        disabled (fastmcp not installed)")
    else:
        typer.echo(f"  MCP:        http://{host}:{port}/mcp")
    # log_level=info: startup line is the only reliable ready signal (Lesson 59)
    uvicorn.run(
        "sellfox_shipping.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    app()
