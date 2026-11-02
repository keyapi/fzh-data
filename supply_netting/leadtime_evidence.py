"""Pure, local helpers for auditable lead-time evidence."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def _date_difference(frame: pd.DataFrame, start_column: str, end_column: str):
    start_raw = frame[start_column]
    end_raw = frame[end_column]
    start = pd.to_datetime(start_raw, errors="coerce")
    end = pd.to_datetime(end_raw, errors="coerce")
    start_missing = start_raw.isna() | start_raw.astype("string").str.strip().eq("")
    end_missing = end_raw.isna() | end_raw.astype("string").str.strip().eq("")
    start_invalid = ~start_missing & start.isna()
    end_invalid = ~end_missing & end.isna()

    days = (end - start).dt.days.astype("Float64")
    status = pd.Series("complete", index=frame.index, dtype="string")
    reason = pd.Series("endpoint_date_difference", index=frame.index, dtype="string")
    invalid = start_invalid | end_invalid
    status.loc[invalid] = "invalid"
    reason.loc[invalid] = np.where(start_invalid[invalid], f"invalid_{start_column}_date", f"invalid_{end_column}_date")
    missing = ~invalid & (start_missing | end_missing)
    status.loc[missing] = "incomplete"
    reason.loc[missing] = np.where(start_missing[missing], f"missing_{start_column}", f"missing_{end_column}")
    reversed_dates = ~invalid & ~missing & (end < start)
    status.loc[reversed_dates] = "invalid"
    reason.loc[reversed_dates] = "end_before_start"
    days.loc[status != "complete"] = pd.NA
    return days, status, reason


def completed_transit_days(
    frame: pd.DataFrame,
    start_column: str = "posting_date",
    end_column: str = "warehouse_in",
) -> pd.DataFrame:
    """Return auditable end-to-end duration and independently dated sub-stages.

    The default stage is DN posting to Tongtool warehouse-in. A caller can
    explicitly select depart to warehouse-in to measure only head-haul.
    """
    missing = [column for column in (start_column, end_column) if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")
    result = frame.copy().reset_index(drop=True)
    result["duration_days"], result["status"], result["reason"] = _date_difference(result, start_column, end_column)
    result["stage"] = f"{start_column}->{end_column}"
    result["start_column"] = start_column
    result["end_column"] = end_column
    result["complete_headhaul"] = result["status"].eq("complete")

    for name, start, end in (
        ("shipping_days", "posting_date", "depart"),
        ("depart_to_warehouse_days", "depart", "warehouse_in"),
    ):
        if start in result.columns and end in result.columns:
            result[name], result[f"{name}_status"], result[f"{name}_reason"] = _date_difference(result, start, end)
        else:
            result[name] = pd.Series(pd.NA, index=result.index, dtype="Float64")
            result[f"{name}_status"] = "unknown"
            result[f"{name}_reason"] = "missing_endpoint_column"
    return result


def _stable_value(series: pd.Series):
    values = series.dropna().unique().tolist()
    if not values:
        return pd.NA
    values = sorted(values, key=lambda value: (type(value).__name__, str(value)))
    return values[0] if len(values) == 1 else tuple(values)


def production_leadtime_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate source details to deterministic DN + SO + role observations.

    ``lead_days_first`` is the earliest observed lead_days in the group and
    ``lead_days_final`` is the latest. ``lead_days`` aliases final delivery for
    legacy consumers. Duplicate item rows are counted in ``n_records`` but do
    not receive extra statistical weight in the summarized observation rows.
    """
    keys = ["dn", "so", "role"]
    missing = [column for column in keys + ["lead_days"] if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")

    work = frame.copy()
    raw_lead_days = work["lead_days"]
    numeric_lead_days = pd.to_numeric(raw_lead_days, errors="coerce")
    work["_lead_days_unknown"] = raw_lead_days.isna()
    work["_lead_days_invalid"] = raw_lead_days.notna() & (numeric_lead_days.isna() | numeric_lead_days.lt(0))
    work["_identity_unknown"] = work["so"].isna() | work["so"].astype("string").str.strip().eq("")
    work["lead_days"] = numeric_lead_days.where(numeric_lead_days.ge(0) & ~work["_identity_unknown"])
    group_keys = keys
    grouped = work.groupby(group_keys, dropna=False, sort=True)
    rows = []
    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        valid = group["lead_days"].dropna()
        record = dict(zip(keys, key))
        record.update(
            lead_days_first=float(valid.min()) if len(valid) else np.nan,
            lead_days_final=float(valid.max()) if len(valid) else np.nan,
            lead_days=float(valid.max()) if len(valid) else np.nan,
            n_records=int(len(group)),
            n_valid_records=int(group["lead_days"].notna().sum()),
            n_unknown_lead_days=int(group["_lead_days_unknown"].sum()),
            n_invalid_lead_days=int(group["_lead_days_invalid"].sum()),
            n_identity_unknown_records=int(group["_identity_unknown"].sum()),
        )
        for column in work.columns:
            if column not in keys + ["lead_days", "_lead_days_unknown", "_lead_days_invalid", "_identity_unknown"]:
                record[column] = _stable_value(group[column])
        rows.append(record)
    columns = keys + [
        "lead_days_first", "lead_days_final", "lead_days", "n_records",
        "n_valid_records", "n_unknown_lead_days", "n_invalid_lead_days", "n_identity_unknown_records",
    ] + [column for column in frame.columns if column not in keys + ["lead_days"]]
    return pd.DataFrame(rows, columns=columns).sort_values(keys, kind="stable", na_position="last").reset_index(drop=True)


def summarize_leadtimes(frame: pd.DataFrame, group_columns: Sequence[str]) -> pd.DataFrame:
    """Summarize final-delivery lead days by explicit dimensions and evidence grain."""
    columns = list(group_columns)
    required = ["lead_days", "dn"]
    missing = [column for column in required + columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")

    work = frame.copy()
    raw_lead = work["lead_days"]
    numeric_lead = pd.to_numeric(raw_lead, errors="coerce")
    work["_invalid_lead"] = raw_lead.notna() & (numeric_lead.isna() | numeric_lead.lt(0))
    work["lead_days"] = numeric_lead.where(numeric_lead.ge(0))
    if columns:
        groups = work.groupby(columns, dropna=False, sort=True)
        iter_groups = groups
    else:
        iter_groups = [((), work)]

    rows = []
    for key, group in iter_groups:
        if columns and not isinstance(key, tuple):
            key = (key,)
        values = group["lead_days"].dropna()
        record = dict(zip(columns, key if columns else ()))
        record.update(
            n_unique_dn=int(group.loc[group["lead_days"].notna(), "dn"].nunique(dropna=True)),
            n_records=int(group["lead_days"].notna().sum()),
            n_unknown=int(group["lead_days"].isna().sum()),
            n_invalid=int(group["_invalid_lead"].sum()) + int(group.get("n_invalid_lead_days", pd.Series(0, index=group.index)).sum()),
            p50=float(values.median()) if len(values) else np.nan,
            p90=float(values.quantile(0.9)) if len(values) else np.nan,
            small_sample=bool(len(values) < 30),
            sample_note="small sample; observed percentile is not a guarantee" if len(values) < 30 else "observed sample; percentile is not a guarantee",
        )
        rows.append(record)
    return pd.DataFrame(rows, columns=columns + [
        "n_unique_dn", "n_records", "n_unknown", "n_invalid", "p50", "p90", "small_sample", "sample_note",
    ])
