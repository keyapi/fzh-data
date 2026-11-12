"""Read-only D5 inspection and explicit-period baseline conversion.

No weekly/daily disaggregation, inventory inference, or database activation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook

from .core import DomainError, day, digest, fail, number, text


REQUIRED = {"product_id", "pool", "physical_form", "canonical_uom", "horizon", "horizon_days", "point_forecast"}
POOLS = {"美东USNJ": "USNJ", "美中USTX": "USTX", "波兰": "PL", "USNJ": "USNJ", "USTX": "USTX", "PL": "PL"}


def _horizon(value):
    number(value, "horizon", 1)
    if int(value) != value:
        fail("invalid_horizon", "预测期间天数必须为正整数")
    return int(value)


def inspect_d5(path, horizon=97):
    """Return (normalized rows, reconciliation report). Invalid rows are retained in report."""
    horizon = _horizon(horizon)
    source = Path(path)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {"schema": "operator-demand-import/v1", "source_name": source.name,
              "source_sha256": source_hash, "selected_horizon_days": horizon,
              "input_count": 0, "selected_count": 0, "accepted_count": 0,
              "skipped_count": 0, "rejected_count": 0, "out_of_scope_count": 0,
              "missing_forecast_count": 0, "skipped": [], "rejected": [],
              "out_of_scope": [], "missing_forecast": [],
              "assumptions": ["point_forecast_is_entire_source_horizon", "name_and_tongtool_identity_not_joined", "no_stock_or_history_inferred", "out_of_scope_pools_are_skipped_not_rejected", "missing_point_forecast_is_reported_not_zero_filled"]}
    candidates = []
    with source.open("rb") as handle:
        workbook = load_workbook(handle, read_only=True, data_only=True)
        try:
            if "1_预测" not in workbook.sheetnames:
                fail("missing_sheet", "缺少工作表1_预测")
            iterator = workbook["1_预测"].iter_rows(values_only=True)
            headers = next(iterator, ())
            if len([h for h in headers if h is not None]) != len(set(h for h in headers if h is not None)):
                fail("duplicate_columns", "预测表列名重复")
            if REQUIRED - set(headers):
                fail("missing_columns", "缺少必要列：" + ",".join(sorted(REQUIRED - set(headers))))
            for line, values in enumerate(iterator, start=2):
                report["input_count"] += 1
                raw = dict(zip(headers, values))
                known_pool = raw.get("pool") in POOLS
                try:
                    source_horizon = _horizon(raw.get("horizon"))
                except DomainError:
                    report["selected_count"] += 1
                    item = {"source_row": line, "reason": "invalid_horizon",
                            "product_id": str(raw.get("product_id") or ""), "pool": str(raw.get("pool") or "")}
                    (report["rejected"] if known_pool else report["out_of_scope"]).append(item)
                    continue
                if source_horizon != horizon:
                    report["skipped"].append({"source_row": line, "reason": "different_horizon", "horizon": source_horizon})
                    continue
                report["selected_count"] += 1
                if not known_pool:
                    report["out_of_scope"].append({"source_row": line, "reason": "unknown_pool",
                                                   "product_id": str(raw.get("product_id") or ""),
                                                   "pool": str(raw.get("pool") or "")})
                    continue
                try:
                    if _horizon(raw.get("horizon_days")) != horizon:
                        fail("horizon_mismatch", "horizon与horizon_days不一致")
                    product = text(raw.get("product_id"), "product_id")
                    form = text(raw.get("physical_form"), "physical_form")
                    unit = text(raw.get("canonical_uom"), "canonical_uom")
                    branch = POOLS[raw["pool"]]
                    forecast = raw.get("point_forecast")
                    if forecast is None or (isinstance(forecast, str) and not forecast.strip()):
                        report["missing_forecast"].append({"source_row": line, "reason": "missing_point_forecast",
                                                           "product_id": product, "pool": str(raw.get("pool") or "")})
                        continue
                    quantity = number(forecast, "point_forecast", 0)
                    key = (product, branch, form, unit)
                    candidates.append((key, {"id": digest(key), "product_id": product,
                        "sku": "EN:" + product, "name": product + "（名称未接入）", "branch": branch,
                        "unit": unit, "physical_form": form, "baseline_qty": quantity,
                        "inventory_qty": None, "supply_note": "库存及已有供给未接入；EN前缀不是通途SKU"}, line))
                except DomainError as exc:
                    report["rejected"].append({"source_row": line, "reason": exc.code, "detail": exc.message,
                                               "product_id": str(raw.get("product_id") or ""), "pool": str(raw.get("pool") or "")})
        finally:
            workbook.close()
    counts = Counter(key for key, _, _ in candidates)
    rows = []
    for key, candidate, line in candidates:
        if counts[key] > 1:
            report["rejected"].append({"source_row": line, "reason": "duplicate_physical_target", "product_id": key[0], "branch": key[1]})
        else:
            rows.append(candidate)
    report.update(accepted_count=len(rows), skipped_count=len(report["skipped"]),
                  rejected_count=len(report["rejected"]),
                  out_of_scope_count=len(report["out_of_scope"]),
                  missing_forecast_count=len(report["missing_forecast"]))
    report["reconciled"] = (report["input_count"] == report["selected_count"] + report["skipped_count"]
                            and report["selected_count"] == report["accepted_count"] + report["rejected_count"]
                            + report["out_of_scope_count"] + report["missing_forecast_count"])
    report["status"] = ("rejected" if report["rejected_count"] else
                        "missing" if report["missing_forecast_count"] else
                        "empty" if not rows else "inspected")
    return rows, report


def make_baseline(path, forecast_start, as_of, horizon=97, allow_missing=False):
    """Require explicit dates; reject true invalid rows. Missing point forecasts
    stay in the report and are excluded only with allow_missing=True."""
    start, observed = day(forecast_start), day(as_of)
    horizon = _horizon(horizon)
    rows, report = inspect_d5(path, horizon)
    if report["rejected_count"] or not rows or not report["reconciled"]:
        fail("import_rejected", "输入存在拒收行或没有可用行；请先检查inspect报告")
    if report["missing_forecast_count"] and not allow_missing:
        fail("missing_forecast", "输入存在缺预测行；请补齐或显式使用--allow-missing-forecast")
    end = start + timedelta(days=horizon - 1)
    for row in rows:
        row.update(week=start.isoformat(), period_end=end.isoformat())
    version = "d5-" + digest({"source": report["source_sha256"], "start": start.isoformat(),
                             "as_of": observed.isoformat(), "horizon": horizon})[:24]
    payload = {"version": version, "as_of": observed.isoformat(), "demo": False, "rows": rows}
    report.update(forecast_start=start.isoformat(), forecast_end=end.isoformat(), as_of=observed.isoformat(),
                  baseline_version=version, baseline_sha256=digest(payload),
                  status="converted_with_missing" if report["missing_forecast_count"] else "converted_not_activated")
    return payload, report


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--horizon", type=int, default=97)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--forecast-start")
    parser.add_argument("--as-of")
    parser.add_argument("--allow-missing-forecast", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        _, report = inspect_d5(args.source, args.horizon)
        _write(out / "report.json", report)
        if args.inspect:
            print(json.dumps({k:v for k,v in report.items() if k not in ("rejected", "skipped", "out_of_scope", "missing_forecast")},ensure_ascii=False))
            return 1 if report["rejected_count"] else 0
        if not args.forecast_start or not args.as_of:
            parser.error("转换必须显式提供--forecast-start和--as-of；或使用--inspect只审计")
        payload, report = make_baseline(args.source, args.forecast_start, args.as_of, args.horizon,
                                        allow_missing=args.allow_missing_forecast)
        _write(out / "baseline.json", payload)
        _write(out / "report.json", report)
        print(json.dumps({"status": report["status"], "rows": len(payload["rows"]), "version": payload["version"]}, ensure_ascii=False))
        return 0
    except DomainError as exc:
        _write(out / "last_attempt.json", {"status": "failed", "code": exc.code, "message": exc.message})
        print(exc.message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
