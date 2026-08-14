from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from .labels import HistoricalPairing, audit_historical_pairing


@dataclass(frozen=True)
class AmazonListing:
    shop_id: str
    marketplace_id: str
    msku: str
    asin: str
    parent_asin: str
    title: str
    target_sku: str
    image_url: str
    online_status: str
    fulfillment: str
    parent_sku: str
    fnsku: str = ""
    is_variation: str = ""


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    value = str(value).strip()
    return "" if value.lower() == "nan" else value


def _key(value) -> str:
    return _text(value).casefold()


def _split(value) -> list[str]:
    return [part.strip() for part in re.split(r"[|;,，；]", _text(value)) if part.strip()]


def load_amazon_cache(path: Path) -> list[AmazonListing]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        AmazonListing(
            shop_id=_text(row.get("shopId")),
            marketplace_id=_text(row.get("marketplaceId")),
            msku=_text(row.get("sku")),
            asin=_text(row.get("asin")),
            parent_asin=_text(row.get("parentAsin")),
            title=_text(row.get("title")),
            target_sku=_text(row.get("commoditySku")),
            image_url=_text(row.get("mainImage")),
            online_status=_text(row.get("onlineStatus")),
            fulfillment=_text(row.get("switchFulfillmentTo")),
            parent_sku=_text(row.get("parentSku")),
            fnsku=_text(row.get("fnsku")),
            is_variation=_text(row.get("isVariation")),
        )
        for row in rows
    ]


def _listing_dict(row) -> dict:
    if isinstance(row, AmazonListing):
        return asdict(row)
    return dict(row)


def build_label_audit(
    listings: list, aliases: pd.DataFrame, mapping: pd.DataFrame
) -> list[dict]:
    alias_to_main: dict[str, set[str]] = defaultdict(set)
    for _, row in aliases.iterrows():
        main = _text(row.get("通途SKU"))
        if not main:
            continue
        alias_to_main[_key(main)].add(main)
        for alias in _split(row.get("SKU别名")):
            alias_to_main[_key(alias)].add(main)

    main_to_targets: dict[str, set[str]] = defaultdict(set)
    for _, row in mapping.iterrows():
        main = _text(row.get("通途SKU"))
        if not main:
            continue
        alias_to_main[_key(main)].add(main)
        for target in _split(row.get("赛狐SKU")):
            main_to_targets[_key(main)].add(target)

    result: list[dict] = []
    for original in listings:
        row = _listing_dict(original)
        msku = _text(row.get("msku") or row.get("sku"))
        target = _text(row.get("target_sku") or row.get("commoditySku"))
        mains = sorted(alias_to_main.get(_key(msku), set()))
        targets = sorted(
            {candidate for main in mains for candidate in main_to_targets.get(_key(main), set())}
        )
        target_upper = target.upper()
        target_type = (
            "ordinary"
            if re.match(r"^KS\d{4}(?:-|$)", target_upper)
            and not target_upper.endswith(("-COVER", "-FOAM"))
            else "non_ordinary"
        )
        audit = audit_historical_pairing(
            HistoricalPairing(
                msku=msku,
                target_sku=target,
                alias_targets=tuple(mains),
                en_targets=tuple(targets),
                target_object_type=target_type,
            )
        )
        result.append(
            {
                **row,
                "msku": msku,
                "target_sku": target,
                "tongtu_targets": " | ".join(mains),
                "validated_targets": " | ".join(targets),
                "tier": audit.tier,
                "usable_for_training": audit.usable_for_training,
                "reasons": " | ".join(audit.reasons),
            }
        )
    return result
