"""Map Sellfox commodity_sku → ERPNext ZLMB# weight-template Item name."""

from __future__ import annotations


def commodity_sku_to_zlmb_item_name(commodity_sku: str) -> str | None:
    """KS0002-DL-194-IVORY → ZLMB#KS0002-DL-194 (fabric segment must match).

    Matching key is the first 3 hyphen segments (style-fabric-size). Color and
    further suffixes are dropped. Returns None when fewer than 3 segments.
    """
    sku = (commodity_sku or "").strip()
    if not sku:
        return None
    parts = sku.split("-")
    if len(parts) < 3:
        return None
    key = "-".join(parts[:3])
    return f"ZLMB#{key}"
