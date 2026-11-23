"""Build raw production and physical-route lead-time evidence by explicit pool."""

from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd

from supply_netting.leadtime_evidence import production_leadtime_rows


_CUSTOMER_POOL = {"CENTRADE": "USNJ", "DANEEY": "USTX", "波兰公司": "PL"}
_REGION_POOL = {"美东": "USNJ", "美中": "USTX", "波兰": "PL"}


def _as_timestamp(value) -> pd.Timestamp:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        raise ValueError(f"invalid as_of date: {value!r}")
    return pd.Timestamp(timestamp).normalize()


def _text(value) -> str:
    if isinstance(value, tuple):
        return ""
    missing = pd.isna(value)
    return "" if bool(missing) else str(value).strip()


def _pool(value, mapping: dict[str, str]) -> str:
    return mapping.get(_text(value), "unknown")


def _main_haul(transport, carrier) -> str:
    transport_text = _text(transport).lower()
    carrier_text = _text(carrier).lower()
    if "matson" in carrier_text or "美森" in transport_text or "美森" in carrier_text:
        return "sea_fast"
    if "空运" in transport_text or re.search(r"\bair\b", carrier_text, flags=re.IGNORECASE):
        return "air"
    if "海运" in transport_text:
        return "sea_regular"
    return "unknown"


def _last_mile(way) -> str:
    value = _text(way)
    if "卡派" in value or "卡车" in value:
        return "truck"
    if "快递" in value:
        return "express"
    return "unknown"


def _group_report(values: dict[tuple, list[float]]) -> dict[tuple, dict]:
    return {
        key: {
            "n": len(days),
            "small_sample": len(days) < 30,
            "sample_note": "small sample; observed days do not guarantee future lead time"
            if len(days) < 30 else "observed sample; does not guarantee future lead time",
        }
        for key, days in sorted(values.items())
    }


def build_route_evidence(dn: pd.DataFrame, zmt: pd.DataFrame, as_of) -> tuple[dict, dict, dict]:
    """Return raw production/head-haul day lists and auditable inclusion counts.

    Production observations are one row per DN + SO + role. Production evidence
    uses only the rolling six-month window ending on ``as_of``. Head-haul samples
    use the direct WMS-in to delivery date difference and exact physical regions.
    """
    cutoff = _as_timestamp(as_of)
    recent_start = cutoff - pd.DateOffset(months=6)
    production: dict[tuple[str, str], list[float]] = defaultdict(list)
    head: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    if dn.empty and len(dn.columns) == 0:
        dn = pd.DataFrame(columns=["dn", "posting_date", "customer", "so", "role", "lead_days"])
    missing_dn_columns = [column for column in ("dn", "posting_date", "customer", "so", "role", "lead_days") if column not in dn]
    if missing_dn_columns:
        raise ValueError(f"DN missing required columns: {', '.join(missing_dn_columns)}")
    dn_dates = pd.to_datetime(dn["posting_date"], errors="coerce")
    dn_missing_date = dn["posting_date"].isna() | dn["posting_date"].astype("string").str.strip().eq("")
    dn_invalid_date = ~dn_missing_date & dn_dates.isna()
    dn_after = dn_dates.notna() & (dn_dates.dt.normalize() > cutoff)
    dn_older = dn_dates.notna() & (dn_dates.dt.normalize() < recent_start)
    dn_recent_mask = dn_dates.notna() & ~dn_invalid_date & ~dn_after & ~dn_older
    dn_recent = dn.loc[dn_recent_mask].copy()

    production_rows = production_leadtime_rows(dn_recent)
    recent_lead_days = pd.to_numeric(dn_recent["lead_days"], errors="coerce")
    invalid_negative_lead_days = int(recent_lead_days.lt(0).sum())
    invalid_non_numeric_lead_days = int((dn_recent["lead_days"].notna() & recent_lead_days.isna()).sum())
    unknown_customer_rows = 0
    unknown_role_rows = 0
    included_dn = 0
    for _, row in production_rows.iterrows():
        pool = _pool(row["customer"], _CUSTOMER_POOL)
        role = _text(row["role"])
        role = role if role and not role.startswith("(") else "unknown"
        if pool == "unknown":
            unknown_customer_rows += 1
        if role == "unknown":
            unknown_role_rows += 1
        days = pd.to_numeric(pd.Series([row["lead_days"]]), errors="coerce").iloc[0]
        if pd.isna(days) or days < 0:
            continue
        production[(pool, role)].append(float(days))
        included_dn += 1

    if zmt.empty and len(zmt.columns) == 0:
        zmt = pd.DataFrame(columns=["wms_in_time", "dlvr"])
    missing_zmt_columns = [column for column in ("wms_in_time", "dlvr") if column not in zmt]
    if missing_zmt_columns:
        raise ValueError(f"ZMT missing required columns: {', '.join(missing_zmt_columns)}")
    wms_raw = zmt["wms_in_time"]
    dlvr_raw = zmt["dlvr"]
    wms = pd.to_datetime(wms_raw, errors="coerce")
    dlvr = pd.to_datetime(dlvr_raw, errors="coerce")
    wms_missing = wms_raw.isna() | wms_raw.astype("string").str.strip().eq("")
    dlvr_missing = dlvr_raw.isna() | dlvr_raw.astype("string").str.strip().eq("")
    wms_invalid = ~wms_missing & wms.isna()
    dlvr_invalid = ~dlvr_missing & dlvr.isna()
    future_delivery = dlvr.notna() & (dlvr.dt.normalize() > cutoff)
    invalid_order = wms.notna() & dlvr.notna() & (dlvr < wms)
    incomplete = (wms_missing | dlvr_missing) & ~wms_invalid & ~dlvr_invalid
    invalid = wms_invalid | dlvr_invalid | invalid_order
    valid_mask = ~incomplete & ~invalid & ~future_delivery

    unknown_region_rows = 0
    unknown_main_rows = 0
    unknown_last_rows = 0
    mixed_purpose_counts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: {"mixed_delivery_purpose": 0, "unmarked": 0})
    included_head = 0
    for position in range(len(zmt)):
        if not bool(valid_mask.iloc[position]):
            continue
        row = zmt.iloc[position]
        pool = _pool(row.get("region"), _REGION_POOL)
        main_haul = _main_haul(row.get("transport"), row.get("carrier"))
        last_mile = _last_mile(row.get("way"))
        if pool == "unknown":
            unknown_region_rows += 1
        if main_haul == "unknown":
            unknown_main_rows += 1
        if last_mile == "unknown":
            unknown_last_rows += 1
        route = (pool, main_haul, last_mile)
        days = int((dlvr.iloc[position].normalize() - wms.iloc[position].normalize()).days)
        head[route].append(float(days))
        purpose_text = " ".join(_text(row.get(column)) for column in ("region", "transport", "dest", "remarks", "way", "carrier"))
        purpose = "mixed_delivery_purpose" if re.search(r"FBA", purpose_text, flags=re.IGNORECASE) else "unmarked"
        mixed_purpose_counts[route][purpose] += 1
        included_head += 1

    production = {key: sorted(days) for key, days in sorted(production.items())}
    head = {key: sorted(days) for key, days in sorted(head.items())}
    production_groups = _group_report(production)
    head_groups = _group_report(head)
    report = {
        "as_of": cutoff.date().isoformat(),
        "dn": {
            "input": int(len(dn)),
            "missing_posting_date": int(dn_missing_date.sum()),
            "invalid_posting_date": int(dn_invalid_date.sum()),
            "posting_after_as_of": int(dn_after.sum()),
            "older_than_6_months": int(dn_older.sum()),
            "in_window_source_rows": int(dn_recent_mask.sum()),
            "production_rows": int(len(production_rows)),
            "missing_so_identity": int(production_rows.get("n_identity_unknown_records", pd.Series(dtype=int)).sum()),
            "invalid_negative_lead_days": invalid_negative_lead_days,
            "invalid_non_numeric_lead_days": invalid_non_numeric_lead_days,
            "unknown_customer_pool_rows": unknown_customer_rows,
            "unknown_role_rows": unknown_role_rows,
            "included": included_dn,
            "groups": production_groups,
            "small_sample_groups": sum(bool(group["small_sample"]) for group in production_groups.values()),
        },
        "head": {
            "input": int(len(zmt)),
            "complete_date_pair": int((wms.notna() & dlvr.notna()).sum()),
            "incomplete": int(incomplete.sum()),
            "invalid": int(invalid.sum()),
            "future_delivery": int(future_delivery.sum()),
            "unknown_region": unknown_region_rows,
            "unknown_main_haul": unknown_main_rows,
            "unknown_last_mile": unknown_last_rows,
            "included": included_head,
            "scope": "physical_route_samples",
            "ownership_claim": False,
            "delivery_purpose_counts": dict(mixed_purpose_counts),
            "groups": head_groups,
            "small_sample_groups": sum(bool(group["small_sample"]) for group in head_groups.values()),
            "sample_note": "small route samples are observations, not guarantees",
        },
    }
    return dict(production), dict(head), report
