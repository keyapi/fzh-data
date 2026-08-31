"""FastMCP tools for sellfox-shipping.

AI Agent-friendly tools that wrap the service layer. Outcome-oriented
design: tools represent *what the agent wants to accomplish*, not raw API calls.

All tools share the same Store + SellfoxClient as the REST API.
"""

from __future__ import annotations

from fastmcp import FastMCP

from sellfox_shipping.store import Store

mcp = FastMCP(name="sellfox-shipping")

# ── Shared state ──────────────────────────────────────────────────

_store: Store | None = None


def init_mcp(store: Store):
    global _store
    _store = store


# ── Tools ─────────────────────────────────────────────────────────

@mcp.tool
async def list_orders(
    status: str = "all",
    limit: int = 20,
) -> dict:
    """List orders in the shipping system.

    Args:
        status: Filter by package status. One of: to_audit, to_process,
                apply_track_no, to_print, has_shipped, has_canceled, or "all".
        limit: Maximum number of orders to return (default 20, max 200).
    """
    status_arg = None if status == "all" else status
    orders = _store.list_orders(status=status_arg, limit=min(limit, 200))
    total = _store.count_orders(status=status_arg)
    return {
        "total": total,
        "count": len(orders),
        "orders": [
            {
                "amazon_order_id": o.amazon_order_id,
                "package_sn": o.package_sn,
                "shop_name": o.shop_name,
                "marketplace": o.marketplace,
                "package_status": o.package_status.value,
                "purchase_date": o.purchase_date.isoformat() if o.purchase_date else None,
                "order_total": o.order_total,
                "currency": o.currency,
                "item_count": len(o.items),
            }
            for o in orders
        ],
    }


@mcp.tool
async def get_order(amazon_order_id: str) -> dict:
    """Get full details for a specific order including address and items.

    Args:
        amazon_order_id: The Amazon order ID (e.g., '114-1234567-7890123').
    """
    order = _store.get_order(amazon_order_id)
    if not order:
        return {"error": f"Order {amazon_order_id} not found in local store"}
    labels = _store.get_labels_for_order(order.id)
    return {
        "order": order.model_dump(mode="json"),
        "label_count": len(labels),
        "labels": [
            {
                "carrier": l.carrier,
                "tracking_number": l.tracking_number,
                "status": l.status,
                "cost": l.cost,
                "currency": l.currency,
            }
            for l in labels
        ],
    }


@mcp.tool
async def get_order_shipping_info(amazon_order_id: str) -> dict:
    """Extract shipping-relevant fields from an order: address, items, and
    whether it already has a label.

    Args:
        amazon_order_id: The Amazon order ID.
    """
    order = _store.get_order(amazon_order_id)
    if not order:
        return {"error": f"Order {amazon_order_id} not found"}

    labels = _store.get_labels_for_order(order.id)
    has_label = any(l.status not in ("error",) for l in labels)
    addr = order.shipping_address

    return {
        "amazon_order_id": order.amazon_order_id,
        "package_sn": order.package_sn,
        "package_status": order.package_status.value,
        "has_label": has_label,
        "destination": {
            "name": addr.name,
            "address1": addr.address1,
            "city": addr.city,
            "state": addr.state,
            "postal_code": addr.postal_code,
            "country_code": addr.country_code,
        },
        "items": [
            {"sku": i.seller_sku, "commodity_sku": i.commodity_sku, "qty": i.quantity}
            for i in order.items
        ],
        "warehouse": order.shop_name,
    }


@mcp.tool
async def fetch_orders_from_sellfox(
    date_start: str,
    date_end: str,
    status: str = "all",
) -> dict:
    """Pull orders from Sellfox into the local store for processing.

    Args:
        date_start: Start date in yyyy-MM-dd format.
        date_end: End date in yyyy-MM-dd format.
        status: Order status filter or "all".
    """
    # Import here to avoid circular import — shares the app's client
    from sellfox_shipping.app import sellfox as client

    all_orders = []
    page_no = 1
    total = 0
    status_arg = None if status == "all" else status

    while True:
        orders, total = client.fetch_orders(
            date_start=date_start,
            date_end=date_end,
            status=status_arg,
            page_no=page_no,
            page_size=50,
        )
        for o in orders:
            _store.upsert_order(o)
        all_orders.extend(orders)
        if page_no * 50 >= total:
            break
        page_no += 1

    return {"fetched": len(all_orders), "total_in_sellfox": total}


@mcp.tool
async def get_carrier_info(carrier: str) -> dict:
    """Get information about a shipping carrier: whether it's enabled and
    what label format it uses.

    Args:
        carrier: Carrier name (e.g., 'fedex', 'gls', 'dhl').
    """
    from sellfox_shipping.app import config

    carriers = config.get("carriers", {})
    if carrier not in carriers:
        return {"error": f"Unknown carrier '{carrier}'. Available: {list(carriers)}"}
    cfg = carriers[carrier]
    return {
        "name": carrier,
        "label": cfg.get("label", carrier),
        "enabled": cfg.get("enabled", False),
        "label_format": cfg.get("label_format", "PDF"),
    }


@mcp.tool
async def list_available_carriers() -> dict:
    """List all configured carriers and their enabled status."""
    from sellfox_shipping.app import config

    return {
        name: {
            "enabled": cfg.get("enabled", False),
            "label": cfg.get("label", name),
            "label_format": cfg.get("label_format", "PDF"),
        }
        for name, cfg in config.get("carriers", {}).items()
    }
