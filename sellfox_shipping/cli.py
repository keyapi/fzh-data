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
    config = _load_config()
    return SellfoxClient(
        proxy_base_url=config["sellfox"]["proxy_base_url"],
        proxy_account=config["sellfox"]["proxy_account"],
        proxy_api_key=os.getenv("SELLFOX_PROXY_API_KEY", ""),
    )


def _get_package_sync_service():
    from sellfox_shipping.package_repository import PackageRepository
    from sellfox_shipping.package_service import SyncPackagesService

    config = _load_config()
    db_path = BASE_DIR / config.get("store", {}).get("db_path", "data/shipping.db")
    return SyncPackagesService(
        gateway=_get_client(),
        repository=PackageRepository(db_path),
    )


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


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8401, help="Bind port"),
):
    """Start the web server (FastAPI + FastMCP)."""
    import uvicorn
    typer.echo(f"Starting sellfox-shipping on {host}:{port}")
    typer.echo(f"  Web UI:  http://{host}:{port}")
    typer.echo(f"  REST:    http://{host}:{port}/api/")
    typer.echo(f"  MCP:     http://{host}:{port}/mcp")
    uvicorn.run("sellfox_shipping.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
