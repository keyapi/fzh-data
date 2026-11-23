# -*- coding: utf-8 -*-
"""把一次已完成（或外部进程写入）的根目录 Parquet 收编成正式快照，并做离线一致性审计。

用途
- 旧版采集进程只写根目录文件（没有 ``CURRENT`` 快照指针）；本工具把已有数据
  ``adopt_legacy()`` 成正式快照，不重新拉取 EN。
- 用 EN 侧独立计数（如 ``modified >= 2026-10-01`` = 27,503、``sale_time >= 2026-10-01`` = 6,800）
  校验窗口完整性；计数不符就标 partial，不拿单元测试给旧采集背书。
- 审计：单据唯一、行唯一、订单头 line_count / line_qty_total 与行表一致、scope 取值合法。

用法::

    uv run python -m self_fulfilled_demand.finalize_store \
        --store D:/Work/fzh-order-store/en-demand-v1 \
        --run-report D:/Work/fzh-order-store/en-demand-v1/runs/<run_id>.json \
        --expected-sale-orders 6800 --expected-modified-orders 27503
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import config
from .consumer import reconcile_overlap
from .store import ParquetStore, now_iso

READER_VERSION_PRE_FIX = "pre-2026-10-27-pagination-snapshot-fix"


def audit(store: ParquetStore) -> dict:
    with store.pinned():
        orders = store.load_orders()
        lines = store.load_lines()
        packages = store.load_packages()
    result = {
        "orders": int(len(orders)),
        "lines": int(len(lines)),
        "packages": int(len(packages)),
        "orders_unique": bool(orders["en_doc_name"].is_unique) if len(orders) else True,
        "lines_unique": bool(lines["line_key"].is_unique) if len(lines) else True,
        "scope_values": sorted(orders["fulfillment_scope"].dropna().unique().tolist())
        if len(orders)
        else [],
        "orders_missing_sale_date": int(orders["sale_date"].isna().sum()) if len(orders) else 0,
        "header_line_mismatches": 0,
        "qty_mismatches": 0,
        "examples": [],
    }
    if len(orders):
        actual = lines.groupby("en_doc_name").agg(
            n=("line_key", "count"), qty=("quantity", "sum")
        )
        merged = orders.set_index("en_doc_name")[["line_count", "line_qty_total"]].join(
            actual, how="left"
        )
        merged["n"] = merged["n"].fillna(0)
        merged["qty"] = merged["qty"].fillna(0)
        bad_n = merged[merged["line_count"].fillna(0) != merged["n"]]
        bad_q = merged[merged["line_qty_total"].fillna(0) != merged["qty"]]
        result["header_line_mismatches"] = int(len(bad_n))
        result["qty_mismatches"] = int(len(bad_q))
        if len(bad_n) or len(bad_q):
            result["examples"] = (
                bad_n.head(5).reset_index().to_dict("records")
                + bad_q.head(5).reset_index().to_dict("records")
            )
        invalid_scopes = set(result["scope_values"]) - set(config.ALL_SCOPES)
        result["invalid_scope_values"] = sorted(invalid_scopes)
    else:
        result["invalid_scope_values"] = []
    return result


def window_counts(store: ParquetStore) -> dict:
    orders = store.load_orders()
    if not len(orders):
        return {}
    out = {}
    for scope, grp in orders.groupby("ingest_scope", dropna=False):
        out[str(scope)] = {
            "orders": int(len(grp)),
            "min_sale_date": str(grp["sale_date"].min()),
            "max_sale_date": str(grp["sale_date"].max()),
            "max_modified": str(grp["modified"].max()),
            "coverage_status": sorted(grp["coverage_status"].dropna().unique().tolist()),
        }
    return out


def finalize(
    store: ParquetStore,
    run_report_path: str | Path | None,
    expected_sale_orders: int | None,
    expected_modified_orders: int | None,
) -> dict:
    adopted = store.adopt_legacy()
    audit_result = audit(store)
    counts = window_counts(store)

    sale_orders = counts.get("sale_window", {}).get("orders", 0)
    modified_orders = counts.get("modified_window", {}).get("orders", 0)
    sample_orders = counts.get("validation_sample", {}).get("orders", 0)
    union_ab = sale_orders + modified_orders

    count_checks = {}
    if expected_sale_orders:
        count_checks["sale_window"] = {
            "expected": expected_sale_orders,
            "actual": sale_orders,
            "match": sale_orders == expected_sale_orders,
        }
    if expected_modified_orders:
        count_checks["modified_union"] = {
            "expected": expected_modified_orders,
            "actual": union_ab,
            "match": union_ab == expected_modified_orders,
            "note": "sale_window 与 modified_window 的交集归到 sale_window；若 A⊂B，A+B 应等于 modified 窗口总数",
        }

    gs_path = "D:/Work/fzh-order-store/gs_orders.parquet"
    run_report = {}
    if run_report_path and Path(run_report_path).exists():
        run_report = json.loads(Path(run_report_path).read_text(encoding="utf-8"))

    gs_coverage = {}
    gs_file = Path(gs_path) if gs_path else None
    if gs_file and gs_file.exists():
        try:
            gs_dates = pd.read_parquet(gs_file, columns=["sale_date", "despatch_date"])
            gs_coverage = {
                "path": str(gs_file),
                "rows": int(len(gs_dates)),
                "coverage_basis": "despatch_date",
                "max_sale_date": str(pd.to_datetime(gs_dates["sale_date"], errors="coerce").max())[:10],
                "max_despatch_date": str(
                    pd.to_datetime(gs_dates["despatch_date"], errors="coerce").max()
                )[:10],
            }
        except Exception as exc:  # noqa: BLE001
            gs_coverage = {"path": str(gs_file), "error": f"{type(exc).__name__}: {exc}"}

    counts_ok = all(v["match"] for v in count_checks.values()) if count_checks else False
    audit_ok = (
        audit_result["orders_unique"]
        and audit_result["lines_unique"]
        and audit_result["header_line_mismatches"] == 0
        and audit_result["qty_mismatches"] == 0
        and not audit_result["invalid_scope_values"]
    )

    # 用新版固定快照代码离线重做交叉验证（旧进程混版本时 overlap_validation 失败过）
    run_windows = run_report.get("windows", {})
    validation = {"status": "not_run"}
    gs_path = (
        run_report.get("source_coverage", {}).get("gs_legacy", {}).get("path") or gs_path
    )
    if gs_path and Path(gs_path).exists():
        try:
            validation = reconcile_overlap(
                store,
                gs_path,
                run_windows.get("sept_sample_start", "2026-09-20"),
                run_windows.get("sale_since", config.DEFAULT_LEGACY_CUTOVER),
                run_id=run_report.get("run_id"),
            )
        except Exception as exc:  # noqa: BLE001
            validation = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    validation_ok = validation.get("status") == "ok" and validation.get("matched_lines", 0) > 0

    fetch = run_report.get("fetch", {})
    fetch_ok = (
        not (fetch.get("window_sale", {}).get("errors") or [])
        and not (fetch.get("window_modified", {}).get("errors") or [])
        and not fetch.get("window_sale", {}).get("capped")
        and not fetch.get("window_modified", {}).get("capped")
        and run_report.get("store", {}).get("failed_orders", 0) == 0
    )
    status = "success" if (audit_ok and counts_ok and validation_ok and fetch_ok) else "partial"

    watermarks = dict(run_report.get("watermarks", {}))
    if status != "success":
        # partial 不推进水位：保留原值字段但显式标未推进
        watermarks["modified_max"] = None
        watermarks["watermark_advanced"] = False
    else:
        watermarks["watermark_advanced"] = True

    report = {
        "run_id": run_report.get("run_id") or f"finalize-{now_iso()}",
        "status": status,
        "data_fetch_status": "success" if fetch_ok else "partial",
        "validation_status": (
            "passed"
            if validation_ok
            else ("not_run" if validation.get("status") == "not_run" else "failed")
        ),
        "watermarks": watermarks,
        "source_coverage": {
            "gs_legacy": gs_coverage or run_report.get("source_coverage", {}).get("gs_legacy", {}),
            "original_run": {
                "run_id": run_report.get("run_id"),
                "reported_status": run_report.get("status"),
                "failures": run_report.get("failures", []),
                "reader_version": run_report.get("reader_version"),
                "note": "初次采集报告保留原样；其中 overlap_validation 因旧进程与新 consumer 混版本失败，已由 finalize 用固定快照离线重做。",
            },
            "en": {
                **run_report.get("source_coverage", {}).get("en", {}),
                "reader_version": READER_VERSION_PRE_FIX
                if run_report.get("reader_version") is None
                else run_report["reader_version"],
                "coverage_verified_by_counts": counts_ok,
                "count_checks": count_checks,
            },
            "finalized_at": now_iso(),
            "adopted_legacy_commit": (adopted or {}).get("commit_id"),
            "offline_overlap_validation": validation,
        },
        "store": {"totals_after": {
            "orders": audit_result["orders"],
            "lines": audit_result["lines"],
            "packages": audit_result["packages"],
            "events": len(store.load_events()),
        }},
        "caveats": [
            "本次真实采集由分页/快照修复前的进程启动，不能用修复后的单元测试替其完整性背书。",
            "完整性由 EN 独立计数（sale_window / modified_window）与离线审计（唯一键、头行一致）验证。",
            "9 月末交集是抽样，coverage_status=sample。",
        ],
    }
    if status != "success":
        report["caveats"].append("计数或审计未通过 → partial，不得当作完整更新。")
    store.write_manifest(report)
    out = {
        "status": status,
        "audit": audit_result,
        "window_counts": counts,
        "count_checks": count_checks,
        "data_fetch_status": report["data_fetch_status"],
        "validation_status": report["validation_status"],
        "offline_overlap_validation": validation,
        "adopted_legacy": bool(adopted),
        "manifest": str(store.manifest_path),
    }
    path = store.root / "finalize_report.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    out["report_path"] = str(path)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="收编根目录 Parquet 为快照并做离线审计")
    ap.add_argument("--store", default="D:/Work/fzh-order-store/en-demand-v1")
    ap.add_argument("--run-report", default=None)
    ap.add_argument("--expected-sale-orders", type=int, default=None)
    ap.add_argument("--expected-modified-orders", type=int, default=None)
    args = ap.parse_args(argv)
    store = ParquetStore(args.store)
    result = finalize(
        store, args.run_report, args.expected_sale_orders, args.expected_modified_orders
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
