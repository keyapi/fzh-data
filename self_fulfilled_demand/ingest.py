# -*- coding: utf-8 -*-
"""EN 终端订单只读增量入口。

用法（生产默认只读，不写 EN）::

    uv run python -m self_fulfilled_demand.ingest \
        --out D:/Work/fzh-order-store/en-demand-v1 \
        --sale-since 2026-10-01 \
        --modified-since 2026-10-01 \
        --validate-sept-sample 200

窗口
- A 新增需求：``sale_time in [sale_since, until]``
- B 历史变更：``modified in [modified_since, until]`` 且 ``sale_time < sale_since``
  （取消/改地址/补发等迟到修改；modified 水位 + 回看窗口）
- C 9 月末抽样：``sale_time in [sept_sample_start, sale_since)``，只取前 N 单做交集验证，
  标 ``coverage_status=sample``，不能当完整覆盖。

分页用键集（``>= cursor`` + 去重），子表按 ``name in`` 每批精确取；
遇到失败如实标 partial，不把部分成功写成全量成功。
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from . import READER_VERSION, SCHEMA_VERSION
from .config import (
    DEFAULT_LEGACY_CUTOVER,
    ORDER_HEAD_FIELDS,
    ORDER_ITEM_FIELDS,
    ORDER_PACKAGE_FIELDS,
    SCOPE_UNKNOWN,
)
from .en_reader import EnBudgetExhausted, EnReadError, EnReadOnlyClient
from .normalize import normalize_order
from .store import ParquetStore, now_iso


def _code_fingerprint() -> dict:
    """记录本次运行使用的代码版本，便于区分旧进程数据与新版本验证。"""
    import hashlib
    import subprocess

    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except Exception:  # noqa: BLE001 - 没有 git 也不影响采集
        head, dirty = None, None
    hashes = {}
    for name in ("en_reader.py", "normalize.py", "store.py", "ingest.py", "consumer.py", "config.py"):
        path = Path(__file__).parent / name
        if path.exists():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return {"git_head": head, "worktree_dirty": dirty, "reader_version": READER_VERSION, "module_hashes": hashes}


def _new_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    suffix = "".join(random.choices(string.hexdigits.lower(), k=6))
    return f"{stamp}-{suffix}"


def _en_now() -> str:
    # EN 存的是朴素本地时间；水位也用它，不做时区换算
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _shift_en(value: str, hours: int) -> str:
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S") - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _batched(seq, size):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _head_window(
    reader: EnReadOnlyClient,
    *,
    cursor_field: str,
    start: str,
    until: str,
    extra_filters: list | None,
    page_size: int,
    max_orders: int,
    max_pages: int = 400,
) -> tuple[dict[str, dict], dict]:
    """按键集取一个窗口的订单头，返回 {doc: head} 与统计。"""
    heads: dict[str, dict] = {}
    stats = {"pages": 0, "rows": 0, "unique": 0, "errors": [], "truncated": False}
    try:
        for page in reader.iter_order_heads(
            cursor_field=cursor_field,
            cursor_start=start,
            until=until,
            extra_filters=extra_filters,
            page_size=page_size,
            max_orders=max_orders,
            max_pages=max_pages,
        ):
            stats["pages"] += 1
            stats["rows"] += len(page)
            for head in page:
                heads[head["name"]] = head
            print(
                f"  [{cursor_field}] page {stats['pages']}: +{len(page)} rows "
                f"(unique {len(heads)})",
                flush=True,
            )
    except EnBudgetExhausted as exc:
        stats["truncated"] = True
        stats["errors"].append(f"预算耗尽：{exc}（已取 {exc.fetched} 单）")
        print(f"  [{cursor_field}] 预算耗尽，结果不完整：{exc}", flush=True)
    except EnReadError as exc:
        stats["errors"].append(str(exc))
        print(f"  [{cursor_field}] 读取中断：{exc}", flush=True)
    stats["unique"] = len(heads)
    stats["capped"] = stats["truncated"] or len(heads) >= max_orders
    return heads, stats


def _collect_children(
    reader: EnReadOnlyClient, names: list[str], batch_size: int
) -> tuple[dict[str, list], dict[str, list], list[dict]]:
    items: dict[str, list] = {n: [] for n in names}
    packages: dict[str, list] = {n: [] for n in names}
    failures: list[dict] = []
    for batch in _batched(names, batch_size):
        try:
            item_rows = reader.fetch_children(
                batch, "order_items", ORDER_ITEM_FIELDS, batch_size=batch_size
            )
        except EnReadError as exc:
            failures.append({"stage": "order_items", "docs": batch, "error": str(exc)})
            continue
        try:
            package_rows = reader.fetch_children(
                batch, "packages", ORDER_PACKAGE_FIELDS, batch_size=batch_size
            )
        except EnReadError as exc:
            failures.append({"stage": "packages", "docs": batch, "error": str(exc)})
            continue
        for row in item_rows:
            items.setdefault(row["name"], []).append(row)
        for row in package_rows:
            packages.setdefault(row["name"], []).append(row)
    return items, packages, failures


def _empty_stats() -> dict:
    return {
        "input_orders": 0,
        "new_orders": 0,
        "updated_orders": 0,
        "unchanged_orders": 0,
        "duplicate_lines_collapsed": 0,
        "events_appended": 0,
        "orders_with_conflict": 0,
        "orders_unknown_scope": 0,
        "orders_invalid": 0,
        "orders_fba": 0,
        "lines_written": 0,
        "packages_written": 0,
        "orders_missing_lines": 0,
    }


def _merge_stats(total: dict, part: dict) -> None:
    for key in _empty_stats():
        total[key] = total.get(key, 0) + part.get(key, 0)


def _coverage(store: ParquetStore, run_id: str) -> dict:
    orders = store.load_orders()
    if not len(orders):
        return {}
    fresh = orders[orders["last_run_id"] == run_id]
    out = {"by_scope": {}, "by_warehouse": [], "by_platform": []}
    for scope, grp in fresh.groupby("fulfillment_scope", dropna=False):
        out["by_scope"][str(scope)] = {
            "orders": int(len(grp)),
            "min_sale_date": str(grp["sale_date"].min()),
            "max_sale_date": str(grp["sale_date"].max()),
        }
    wh = (
        fresh.groupby("warehouse_name", dropna=False)
        .agg(orders=("en_doc_name", "count"), min_sale=("sale_date", "min"), max_sale=("sale_date", "max"))
        .reset_index()
        .sort_values("orders", ascending=False)
    )
    out["by_warehouse"] = [
        {
            "warehouse": None if pd.isna(r.warehouse_name) else str(r.warehouse_name),
            "orders": int(r.orders),
            "min_sale_date": str(r.min_sale),
            "max_sale_date": str(r.max_sale),
        }
        for r in wh.itertuples()
    ]
    plat = (
        fresh.groupby("platform_code", dropna=False)
        .agg(orders=("en_doc_name", "count"))
        .reset_index()
        .sort_values("orders", ascending=False)
    )
    out["by_platform"] = [
        {"platform_code": None if pd.isna(r.platform_code) else str(r.platform_code), "orders": int(r.orders)}
        for r in plat.itertuples()
    ]
    return out


def run(args: argparse.Namespace) -> dict:
    run_id = _new_run_id()
    started_at = now_iso()
    until = args.until or _en_now()
    store = ParquetStore(args.out)
    manifest = store.read_manifest()

    prev_watermarks = manifest.get("watermarks", {}) if manifest else {}
    modified_since = args.modified_since
    if not modified_since:
        prev_modified = prev_watermarks.get("modified_max")
        if prev_modified:
            modified_since = _shift_en(prev_modified, args.lookback_hours)
        else:
            modified_since = args.sale_since

    run = {
        "run_id": run_id,
        "started_at": started_at,
        "ingest_scope": None,
        "coverage_status": "complete",
    }
    report = {
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at,
        "finished_at": None,
        "status": "running",
        "mode": "dry-run" if args.dry_run else "write",
        "reader_version": READER_VERSION,
        "code_fingerprint": _code_fingerprint(),
        "windows": {
            "sale_since": args.sale_since,
            "modified_since": modified_since,
            "until": until,
            "sept_sample_start": args.sept_sample_start,
            "sept_sample_size": args.validate_sept_sample,
            "lookback_hours": args.lookback_hours,
        },
        "fetch": {},
        "store": {},
        "coverage": {},
        "failures": [],
        "caveats": [
            "modified 是 EN 记录修改时间，不是源 Tongtool 更新时间；源更新时间见 updated_time。",
            "EN 时间是朴素本地时间，未做时区换算。",
            "9 月末交集仅为抽样验证，coverage_status=sample，不代表完整覆盖。",
            "FBA 订单只记录不进入自发货需求序列。",
            "fulfillment_scope 的仓库判定只认显式证据；未映射仓库对 GS 历史行为 unknown。",
        ],
    }

    try:
        reader = EnReadOnlyClient(
            base_url=args.base_url,
            env_file=args.env_file,
            min_interval=args.min_interval,
        )
    except EnReadError as exc:
        report["status"] = "failed"
        report["failures"].append({"stage": "auth", "error": str(exc)})
        report["finished_at"] = now_iso()
        store.write_run_report(report)
        return report

    # ---- 窗口 A：新增需求 -------------------------------------------------
    print(f"[A] sale_time {args.sale_since} → {until}", flush=True)
    heads_a, fetch_a = _head_window(
        reader,
        cursor_field="sale_time",
        start=args.sale_since,
        until=until,
        extra_filters=None,
        page_size=args.page_size,
        max_orders=args.max_orders,
        max_pages=args.max_pages,
    )

    # ---- 窗口 B：历史变更（modified 水位 + 回看） --------------------------
    print(
        f"[B] modified {modified_since} → {until} 且 sale_time < {args.sale_since}",
        flush=True,
    )
    heads_b, fetch_b = _head_window(
        reader,
        cursor_field="modified",
        start=modified_since,
        until=until,
        extra_filters=[["Tongtool Order", "sale_time", "<", args.sale_since]],
        page_size=args.page_size,
        max_orders=args.max_orders,
        max_pages=args.max_pages,
    )

    heads: dict[str, dict] = {}
    source_of: dict[str, str] = {}
    for doc, head in heads_b.items():
        heads[doc] = head
        source_of[doc] = "modified_window"
    for doc, head in heads_a.items():
        heads[doc] = head
        source_of[doc] = "sale_window"

    # ---- 窗口 C：9 月末抽样交集 ------------------------------------------
    sample_heads: dict[str, dict] = {}
    if args.validate_sept_sample > 0:
        print(
            f"[C] sale_time {args.sept_sample_start} → {args.sale_since} 取样 "
            f"{args.validate_sept_sample}",
            flush=True,
        )
        try:
            rows = reader.get_list(
                "Tongtool Order",
                ORDER_HEAD_FIELDS,
                filters=[
                    ["Tongtool Order", "sale_time", ">=", args.sept_sample_start],
                    ["Tongtool Order", "sale_time", "<", args.sale_since],
                ],
                order_by="sale_time asc",
                limit_page_length=args.validate_sept_sample,
            )
            for head in rows:
                sample_heads[head["name"]] = head
                if head["name"] not in heads:
                    heads[head["name"]] = head
                    source_of[head["name"]] = "validation_sample"
        except EnReadError as exc:
            report["failures"].append({"stage": "sept_sample", "error": str(exc)})

    report["fetch"] = {
        "window_sale": fetch_a,
        "window_modified": fetch_b,
        "sept_sample_orders": len(sample_heads),
        "orders_in_union": len(heads),
        "by_source": dict(Counter(source_of.values())),
        "request_count": reader.request_count,
    }

    if args.dry_run:
        report["status"] = "dry-run"
        report["finished_at"] = now_iso()
        store.write_run_report(report)
        return report

    # ---- 子表 + 标准化 + 分批写入同一个暂存快照 ---------------------------
    try:
        store.begin(run_id)
    except Exception as exc:  # noqa: BLE001 - 快照创建失败必须显式失败
        report["status"] = "failed"
        report["failures"].append({"stage": "store_begin", "error": f"{type(exc).__name__}: {exc}"})
        report["finished_at"] = now_iso()
        store.write_run_report(report)
        return report

    total = _empty_stats()
    failed_docs: list[dict] = []
    names = list(heads)
    for page_no, batch in enumerate(_batched(names, args.page_size), start=1):
        items, packages, failures = _collect_children(reader, batch, args.line_batch)
        if failures:
            failed = {doc for f in failures for doc in f["docs"]}
            failed_docs.extend(failures)
            report["failures"].extend(failures)
            batch = [n for n in batch if n not in failed]
        records = []
        for doc in batch:
            scope_kind = source_of.get(doc, "sale_window")
            run_ctx = {
                **run,
                "ingest_scope": scope_kind,
                "coverage_status": "sample" if scope_kind == "validation_sample" else "complete",
            }
            records.append(normalize_order(heads[doc], items.get(doc, []), packages.get(doc, []), run_ctx))
        if records:
            try:
                part = store.ingest(records, run)
            except Exception as exc:  # noqa: BLE001 - 写盘失败：丢弃整个暂存快照
                failed_path = store.abort(f"page {page_no} write failed: {exc}")
                report["status"] = "failed"
                report["failures"].append(
                    {
                        "stage": "store_write",
                        "page": page_no,
                        "error": f"{type(exc).__name__}: {exc}",
                        "staging": str(failed_path) if failed_path else None,
                    }
                )
                report["finished_at"] = now_iso()
                store.write_run_report(report)
                return report
            _merge_stats(total, part)
        print(
            f"  page {page_no}: collected {len(batch)} orders, "
            f"new={total['new_orders']} updated={total['updated_orders']} "
            f"unchanged={total['unchanged_orders']} lines={total['lines_written']}",
            flush=True,
        )

    # ---- 9 月末交集验证（EN 样本 vs GS） ----------------------------------
    if sample_heads and args.gs_path and Path(args.gs_path).exists():
        try:
            from .consumer import reconcile_overlap

            report["overlap_validation"] = reconcile_overlap(
                store, args.gs_path, args.sept_sample_start, args.sale_since, run_id=run_id
            )
        except Exception as exc:  # noqa: BLE001 - 验证失败不掩盖主流程
            report["failures"].append({"stage": "overlap_validation", "error": f"{type(exc).__name__}: {exc}"})

    # ---- 状态：先定稿再提交，partial 不能冒充 success ----------------------
    errors = fetch_a["errors"] + fetch_b["errors"]
    capped = fetch_a.get("capped") or fetch_b.get("capped")
    if capped:
        report["caveats"].append(
            f"分页/单量预算耗尽或触及 --max-orders={args.max_orders}，结果不完整（见 fetch.capped）。"
        )
    # 关键校验失败不能只写进 failures 还算 success；数据采集与交叉验证分开标注
    critical_stages = {"overlap_validation", "sept_sample"}
    critical_failures = [f for f in report["failures"] if f.get("stage") in critical_stages]
    fetch_ok = not (errors or failed_docs or capped)
    report["data_fetch_status"] = "success" if fetch_ok else "partial"
    if critical_failures:
        report["validation_status"] = "failed"
    elif "overlap_validation" in report:
        report["validation_status"] = "passed"
    else:
        report["validation_status"] = "not_run"
    if not fetch_ok or critical_failures:
        report["status"] = "partial"
    else:
        report["status"] = "success"

    try:
        commit_info = store.commit(status=report["status"], meta={"run_id": run_id})
        report["commit"] = {
            "commit_id": commit_info["commit_id"],
            "status": commit_info["status"],
            "files": list(commit_info["files"]),
        }
    except Exception as exc:  # noqa: BLE001
        failed_path = store.abort(f"commit failed: {exc}")
        report["status"] = "failed"
        report["failures"].append(
            {
                "stage": "store_commit",
                "error": f"{type(exc).__name__}: {exc}",
                "staging": str(failed_path) if failed_path else None,
            }
        )
        report["finished_at"] = now_iso()
        store.write_run_report(report)
        return report

    report["store"] = total
    report["store"]["failed_orders"] = len({d for f in failed_docs for d in f["docs"]})
    report["store"]["totals_after"] = {
        "orders": len(store.load_orders()),
        "lines": len(store.load_lines()),
        "packages": len(store.load_packages()),
        "events": len(store.load_events()),
    }
    report["coverage"] = _coverage(store, run_id)

    # ---- 源覆盖事实（不因测试通过就宣称完整） ------------------------------
    sale_values = [h.get("sale_time") for h in heads_a.values() if h.get("sale_time")]
    modified_values = [h.get("modified") for h in heads.values() if h.get("modified")]
    gs_info = {"path": str(args.gs_path), "exists": Path(args.gs_path).exists()}
    if gs_info["exists"]:
        try:
            gs_dates = pd.read_parquet(args.gs_path, columns=["sale_date", "despatch_date"])
            gs_info.update(
                {
                    "coverage_basis": "despatch_date",
                    "max_sale_date": str(pd.to_datetime(gs_dates["sale_date"], errors="coerce").max())[:10],
                    "max_despatch_date": str(
                        pd.to_datetime(gs_dates["despatch_date"], errors="coerce").max()
                    )[:10],
                    "rows": int(len(gs_dates)),
                }
            )
        except Exception as exc:  # noqa: BLE001
            gs_info["error"] = f"{type(exc).__name__}: {exc}"
    report["source_coverage"] = {
        "gs_legacy": gs_info,
        "en": {
            "as_of": until,
            "sale_min_fetched": min(sale_values) if sale_values else None,
            "sale_max_fetched": max(sale_values) if sale_values else None,
            "modified_max_fetched": max(modified_values) if modified_values else None,
            "sale_window_complete": not fetch_a["errors"] and not fetch_a.get("truncated"),
            "modified_window_complete": not fetch_b["errors"] and not fetch_b.get("truncated"),
            "partial": report["status"] != "success",
        },
    }

    # ---- 水位 -------------------------------------------------------------
    if report["status"] == "success":
        watermarks = {
            "modified_max": until,
            "sale_time_max": until,
            "last_success_run_at": started_at,
        }
    else:
        watermarks = {
            "modified_max": prev_watermarks.get("modified_max"),
            "sale_time_max": max(
                [prev_watermarks.get("sale_time_max") or ""] + [h.get("sale_time") or "" for h in heads_a.values()]
            )
            or None,
            "last_success_run_at": prev_watermarks.get("last_success_run_at"),
        }
    report["watermarks"] = watermarks
    report["finished_at"] = now_iso()

    store.write_manifest(report)
    path = store.write_run_report(report)
    report["report_path"] = str(path)
    return report


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="EN Tongtool Order 只读增量接入（en-demand-v1）")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1")
    ap.add_argument("--sale-since", default=DEFAULT_LEGACY_CUTOVER)
    ap.add_argument("--modified-since", default=None)
    ap.add_argument("--lookback-hours", type=int, default=72)
    ap.add_argument("--until", default=None)
    ap.add_argument("--page-size", type=int, default=500)
    ap.add_argument("--line-batch", type=int, default=50)
    ap.add_argument("--max-orders", type=int, default=30000)
    ap.add_argument("--max-pages", type=int, default=400)
    ap.add_argument("--validate-sept-sample", type=int, default=0)
    ap.add_argument("--sept-sample-start", default="2026-09-20")
    ap.add_argument("--gs-path", default="D:/Work/fzh-order-store/gs_orders.parquet")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--min-interval", type=float, default=0.15)
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["status"] in ("success", "dry-run", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
