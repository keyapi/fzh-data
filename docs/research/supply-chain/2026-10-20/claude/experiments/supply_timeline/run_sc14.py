#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run SC14 validation against the W1 supply rows (read-only).

contract.py / test_contract.py are byte-identical copies from docs/jack-w1-channel
(commit 197901f78026c7e9ff1d4193bca19719b397399c; unchanged through 65f0dff0)
and are kept in sync by tests/test_sc14_sync.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "sc14"))
sys.path.insert(0, str(HERE))

from contract import Finding, rollup, validate_w1, w3_columns  # noqa: E402
import csv  # noqa: E402


def maybe_num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def maybe_bool(v):
    if v in (None, ""):
        return None
    return str(v).lower() in ("1", "true", "yes")


def load_rows(path: Path):
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            r = dict(raw)
            for k in ("qty", "received_qty", "remaining_qty", "doc_qty"):
                r[k] = maybe_num(r.get(k))
            for k in ("event_date", "available_date"):
                r[k] = r.get(k) or None
            for k in ("allocation_known", "received_booked", "received_evidenced", "uom_proven", "counted"):
                r[k] = maybe_bool(r.get(k))
            try:
                r["tracking_numbers"] = json.loads(r.get("tracking_numbers") or "[]")
            except json.JSONDecodeError:
                r["tracking_numbers"] = []
            if r.get("tracking_qty") in ("", None):
                r["tracking_qty"] = None
            else:
                r["tracking_qty"] = maybe_num(r["tracking_qty"])
            if r.get("batch_key") in ("", None):
                r["batch_key"] = None
            rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=str(HERE / "out" / "supply_timeline_rows.csv"))
    ap.add_argument("--out", default=str(HERE / "out"))
    args = ap.parse_args()
    rows = load_rows(Path(args.rows))
    findings = validate_w1(rows)
    by_code = Counter(f.code for f in findings)
    by_sev = Counter(f.severity for f in findings)
    error_rows = sorted({f.row for f in findings if f.severity == "error" and f.row >= 0})
    warning_rows = sorted({f.row for f in findings if f.severity == "warning" and f.row >= 0})
    warning_rows_by_stage = Counter(rows[i].get("stage", "") for i in warning_rows if 0 <= i < len(rows))
    source = json.loads((HERE / "sc14" / "SOURCE.json").read_text(encoding="utf-8"))
    counts = {
        "rows": len(rows),
        "findings": len(findings),
        "errors": by_sev.get("error", 0),
        "warnings": by_sev.get("warning", 0),
        "by_code": dict(by_code),
        "error_rows": len(error_rows),
        "finding_rows": len({f.row for f in findings if f.row >= 0}),
        "warning_rows": len(warning_rows),
        "warning_rows_by_stage": dict(warning_rows_by_stage),
        "contract_source_commit": source.get("source_commit", ""),
        "contract_sha256": source.get("files", {}).get("contract.py", {}).get("sha256_lf", ""),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc14_counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out / "sc14_findings.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "code", "severity", "sku", "stage", "source_key", "message"])
        for f in findings:
            r = rows[f.row] if 0 <= f.row < len(rows) else {}
            w.writerow([f.row, f.code, f.severity, r.get("sku", ""), r.get("stage", ""),
                        r.get("source_key", ""), f.message])
    roll = rollup(rows)
    w3 = w3_columns(roll)
    (out / "w3_preview.json").write_text(json.dumps({
        "opening_by_uom": roll["opening_by_uom"],
        "supply_confirmed": w3["supply_confirmed"],
        "supply_expected": w3["supply_expected"],
        "supply_unknown": w3["supply_unknown"],
        "excluded_external_fba_rows": len(roll["excluded_external_fba"]),
        "null_qty_rows": len(roll["null_qty"]),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SC14_ROWS", len(rows))
    print("SC14_COUNTS", json.dumps({k: counts[k] for k in ("errors", "warnings", "error_rows", "finding_rows", "warning_rows_by_stage", "by_code")}, ensure_ascii=False))
    print("SC14_W3", json.dumps({"opening": w3 and roll["opening_by_uom"],
                                 "confirmed": w3["supply_confirmed"],
                                 "expected": w3["supply_expected"],
                                 "unknown": w3["supply_unknown"]}, ensure_ascii=False))
    return 0 if not error_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
