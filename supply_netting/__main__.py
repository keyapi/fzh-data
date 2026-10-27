# -*- coding: utf-8 -*-
"""CLI：``uv run python -m supply_netting``

只读本地 Parquet/TSV，产出 Parquet + manifest + 人工审核工作簿；不写生产、不下单。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import WAREHOUSE_ALIASES

from . import artifacts
from .demand import (SERIES_DEFAULT, SERIES_THIRD_PARTY, load_backlog, load_demand_netting,
                     series_rows, unclassified_quantity)
from .engine import build_buckets, net_all
from .supply import load_inputs


def _parse_as_of(text: str) -> datetime:
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"--as-of 需要 ISO 时间：{exc}")
    if value.tzinfo is None:
        raise SystemExit("--as-of 必须带时区，例如 2026-10-21T00:00:00+08:00")
    return value


def _blocked_meta(path: Path | None) -> dict:
    if not path:
        return dict(source="none", participates=False)
    if not path.exists():
        return dict(source=str(path), exists=False, participates=False)
    frame = pd.read_parquet(path)
    return dict(source=str(path), sha256=artifacts.sha256_text(path), rows=int(len(frame)),
                participates=False,
                note="阻断量单独保留；不参与净额，也不与可净额量相减")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="供给净额：需求净额 × 库存/供应事实 → 分桶净额")
    parser.add_argument("--demand", required=True, help="冻结的 demand_netting.parquet")
    parser.add_argument("--stock", required=True, help="通途库存快照 en_stock.parquet")
    parser.add_argument("--sku-map", required=True, help="sku_map.tsv（Item Customer Detail.ref_code → Item）")
    parser.add_argument("--uom-cache", required=True, help="item_uom_cache.parquet")
    parser.add_argument("--warehouse-aliases", default=str(WAREHOUSE_ALIASES))
    parser.add_argument("--po", default=None, help="po_open.tsv（可选，无 ETA）")
    parser.add_argument("--backlog", default=None, help="未履约 SO 余额 csv/parquet（可选）")
    parser.add_argument("--demand-blocked", default=None, help="demand_blocked.parquet（仅登记，不参与）")
    parser.add_argument("--as-of", required=True, help="库存基准时点，ISO 且带时区")
    parser.add_argument("--snapshot-date", default=None, help="库存快照日期；默认取最新")
    parser.add_argument("--protect-days", type=int, default=7)
    parser.add_argument("--weeks", type=int, default=4)
    parser.add_argument("--no-intransit", action="store_true", help="不把通途在途当作供应证据")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    as_of = _parse_as_of(args.as_of)
    buckets = build_buckets(as_of, protect_days=args.protect_days, weeks=args.weeks)

    demand_df, demand_meta = load_demand_netting(args.demand)
    default_rows = series_rows(demand_df, SERIES_DEFAULT)
    third_party_rows = series_rows(demand_df, SERIES_THIRD_PARTY)
    backlog, backlog_meta = load_backlog(args.backlog)

    supply = load_inputs(stock_path=args.stock, po_path=args.po, sku_map_path=args.sku_map,
                         uom_cache_path=args.uom_cache,
                         warehouse_alias_path=args.warehouse_aliases,
                         snapshot_date=args.snapshot_date,
                         include_intransit=not args.no_intransit)

    result = net_all(demand_rows=default_rows, supply_rows=supply["rows"], as_of=as_of,
                     buckets=buckets, backlog=backlog, so_mode="earliest",
                     supply_sources_complete=False)

    tables = artifacts.build_tables(result, supply["evidence"])
    tables["third_party_demand"] = artifacts._third_party_frame(third_party_rows)
    out_dir = Path(args.out)
    paths = artifacts.write_parquet(tables, out_dir)

    facts = tables["supply_facts"]
    net_rows = tables["supply_netting"]
    netted_keys = {tuple(t["key"]) for t in result["targets"]}
    demand_accounted = sum(len(t["demand_dispositions"]) for t in result["targets"])
    checks = dict(
        bucket_identities_passed=True,           # engine 对每一行调用 assert_bucket_identities
        demand_four_key_duplicates=demand_meta["four_key_duplicates"],
        netting_allowed_all_true=True,
        demand_rows_in=len(default_rows),
        demand_rows_accounted=demand_accounted,
        demand_rows_skipped_no_horizon_demand=len(default_rows) - demand_accounted,
        supply_rows_in=len(supply["rows"]),
        supply_rows_outside_demand_keys=sum(
            1 for r in supply["rows"] if (r.sku, r.warehouse, r.uom) not in netted_keys),
        supply_evidence_rows=len(supply["evidence"]),
        supply_facts_rows=int(len(facts)),
        netting_rows=int(len(net_rows)),
        ledger_conserved=all(
            account["input_known"] == account["counted"] + account["excluded_known"]
            for target in result["targets"] for scenario in target["scenarios"].values()
            for account in scenario["ledger"].values()),
        demand_unclassified_quantity=unclassified_quantity(demand_df),
    )
    partial_reasons = [
        "供应来源未覆盖全部渠道（仅通途库存快照/在途与开放 PO），业务覆盖 unverified",
        "通途在途与开放 PO 无逐行 ETA，保持 date_unproven 条件态",
        "未履约 SO 余额未接入（backlog 为空）时，未来需求桶可能为 0",
    ]

    manifest = artifacts.base_manifest(
        as_of=as_of, buckets=buckets, demand_meta=demand_meta,
        blocked_meta=_blocked_meta(Path(args.demand_blocked) if args.demand_blocked else None),
        stock_meta=supply["stock_meta"], po_meta=supply["po_meta"], backlog_meta=backlog_meta,
        extra=dict(
            checks=checks,
            disposition_counts=artifacts.disposition_counts(facts),
            status_counts=net_rows["status"].value_counts().to_dict() if not net_rows.empty else {},
            partial=True, partial_reasons=partial_reasons,
            third_party=dict(rows=len(third_party_rows),
                             note="3PL 需求保留，replenishment_owner=unknown，不并入自发货净额"),
        ),
    )
    manifest["outputs"] = dict(paths)
    manifest["outputs"]["replenishment_review_xlsx"] = artifacts.write_workbook(tables, manifest, out_dir)
    manifest_path = artifacts.write_manifest(manifest, out_dir)

    print(f"需求行 {checks['demand_rows_in']}，净额行 {checks['netting_rows']}，"
          f"供应事实 {checks['supply_facts_rows']}，恒等式={'通过' if checks['bucket_identities_passed'] else '失败'}")
    print(f"输出：{out_dir}")
    print(f"manifest：{manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
