# -*- coding: utf-8 -*-
"""CLI：``uv run python -m supply_netting``

只读本地 Parquet/TSV，产出 Parquet + manifest + 人工审核工作簿；不写生产、不下单。
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import WAREHOUSE_ALIASES, load_sku_map

from . import artifacts
from .facts import (milestones_frame, stages_frame, summarize_stage_balances,
                    tranches_frame, validate_stage_balances)
from .demand import (SERIES_DEFAULT, SERIES_THIRD_PARTY, load_backlog, load_demand_netting,
                     series_rows, unclassified_quantity)
from .engine import build_buckets, day_instant, net_all
from .forecast import forecast_demand_rows, load_forecast, overlap_keys
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


def _file_meta(path) -> dict:
    """F7：影响数值/资格的输入都要有哈希，缺项写 exists=false，不静默。"""
    if not path:
        return dict(path=None, exists=False, sha256="")
    target = Path(path)
    return dict(path=str(target), exists=target.exists(),
                sha256=artifacts.sha256_text(target) if target.exists() else "")


def _git_meta() -> dict:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=15).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                                    text=True, timeout=15).stdout.strip())
        return dict(git_head=head or None, git_dirty=dirty)
    except (OSError, subprocess.SubprocessError):
        return dict(git_head=None, git_dirty=None)


def _timing(stock_meta: dict, as_of: datetime) -> dict:
    """库存快照与 as_of 的差异必须显式披露，不靠读者对比两行。"""
    snapshot_at = stock_meta.get("snapshot_at")
    offset_hours = None
    offset_seconds = None
    if snapshot_at:
        parsed = datetime.fromisoformat(str(snapshot_at))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=as_of.tzinfo)
        offset_seconds = round((as_of - parsed).total_seconds(), 1)
        offset_hours = round(offset_seconds / 3600, 3) + 0.0
    return dict(snapshot_date=stock_meta.get("snapshot_date"), snapshot_at=snapshot_at,
                as_of=as_of.isoformat(), offset_seconds=offset_seconds,
                offset_hours=offset_hours,
                note="snapshot_at 无时区，按 as_of 时区解读；正值表示 as_of 晚于快照")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="供给净额：需求净额 × 库存/供应事实 → 分桶净额")
    parser.add_argument("--demand", required=True, help="冻结的 demand_netting.parquet")
    parser.add_argument("--stock", required=True, help="通途库存快照 en_stock.parquet")
    parser.add_argument("--sku-map", required=True, help="sku_map.tsv（Item Customer Detail.ref_code → Item）")
    parser.add_argument("--uom-cache", required=True, help="item_uom_cache.parquet")
    parser.add_argument("--warehouse-aliases", default=str(WAREHOUSE_ALIASES))
    parser.add_argument("--po", default=None, help="po_open.tsv（可选，无 ETA）")
    parser.add_argument("--po-tongtool", default=None,
                        help="通途采购单 JSONL（purchaseOrderQuery 落地；按通途 SKU，无 ETA）")
    parser.add_argument("--backlog", default=None, help="未履约 SO 余额 csv/parquet（可选）")
    parser.add_argument("--demand-blocked", default=None, help="demand_blocked.parquet（仅登记，不参与）")
    parser.add_argument("--as-of", required=True, help="库存基准时点，ISO 且带时区")
    parser.add_argument("--snapshot-date", default=None, help="库存快照日期；默认取最新")
    parser.add_argument("--protect-days", type=int, default=7)
    parser.add_argument("--weeks", type=int, default=4)
    parser.add_argument("--no-intransit", action="store_true", help="不把通途在途当作供应证据")
    parser.add_argument("--forecast-root",
                        default="D:/Work/fzh-order-store/en-demand-v1/forecast",
                        help="预测根目录（读 CURRENT 指向的 run）")
    parser.add_argument("--forecast-run-id", default=None,
                        help="要求的预测 run_id；与 CURRENT 不一致直接报错，不静默换版本")
    parser.add_argument("--forecast-lead-days", type=int, default=60)
    parser.add_argument("--no-forecast", action="store_true",
                        help="不消费预测（只回放历史需求；manifest 会明确标注）")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    as_of = _parse_as_of(args.as_of)
    buckets = build_buckets(as_of, protect_days=args.protect_days, weeks=args.weeks)

    demand_df, demand_meta = load_demand_netting(args.demand)
    default_rows = series_rows(demand_df, SERIES_DEFAULT)
    third_party_rows = series_rows(demand_df, SERIES_THIRD_PARTY)
    backlog, backlog_meta = load_backlog(args.backlog)

    # 未来桶需求来自刷新预测；历史/资格仍来自 demand_netting。两套资格字段互不替代。
    forecast_meta = dict(source="none", note="--no-forecast")
    forecast_evidence: list[dict] = []
    demand_rows = default_rows
    if not args.no_forecast:
        forecast = load_forecast(args.forecast_root,
                                 expected_run_id=args.forecast_run_id,
                                 lead_days=args.forecast_lead_days)
        covered = overlap_keys(default_rows, forecast.window_start, as_of.tzinfo)
        forecast_rows, forecast_evidence, forecast_meta = forecast_demand_rows(
            forecast, load_sku_map(args.sku_map), buckets=buckets, as_of=as_of,
            skip_keys=covered)
        forecast_meta["keys_with_actuals_in_window"] = len(covered)
        window_start_at = day_instant(forecast.window_start, as_of.tzinfo)
        forecast_meta["gap_from_as_of_days"] = (
            round((window_start_at - as_of).total_seconds() / 86400, 3)
            if window_start_at is not None else None)
        forecast_meta["coverage_note"] = (
            "历史订单全部早于 as_of，只作历史证据；净额需求来自预测。"
            "预测窗口起点与 as_of 之间（gap_from_as_of_days）无需求数据，不填 0。")
        demand_rows = default_rows + forecast_rows

    supply = load_inputs(stock_path=args.stock, po_path=args.po, sku_map_path=args.sku_map,
                         uom_cache_path=args.uom_cache,
                         warehouse_alias_path=args.warehouse_aliases,
                         snapshot_date=args.snapshot_date,
                         include_intransit=not args.no_intransit,
                         po_tongtool_path=args.po_tongtool)

    # F3：阶段余额校验必须在写任何产物之前强制通过（重复身份 = 失败关闭）。
    stage_errors = validate_stage_balances(supply["stage_balances"])
    if stage_errors:
        print("阶段余额校验失败，拒绝写产物：")
        for message in stage_errors[:20]:
            print(f" - {message}")
        return 2

    result = net_all(demand_rows=demand_rows, supply_rows=supply["rows"], as_of=as_of,
                     buckets=buckets, backlog=backlog, so_mode="earliest",
                     supply_sources_complete=False)

    # F8：没有视界内需求键的已证供应也要逐条留痕，不能只留一个计数。
    netted_keys = {tuple(t["key"]) for t in result["targets"]}
    outside_scope = [dict(
        event_id=f"outside:{row.source_layer}:{row.source_key}",
        source_layer=row.source_layer, stage=row.stage, sku=row.sku,
        warehouse=row.warehouse, uom=row.uom, qty=row.qty,
        available_date=row.available_date, date_confidence=row.date_confidence,
        scope=row.scope, identity_confidence=row.identity_confidence,
        warehouse_confidence=row.warehouse_confidence, b_min_eligible=row.b_min_eligible,
        b_max_eligible=row.b_max_eligible, batch_key=row.batch_key,
        batch_proven=row.batch_proven, document_key=row.document_key,
        source_key=row.source_key, exclusion_reason="outside_demand_scope",
        disposition_reason="outside_demand_scope", bucket_id=None, counted=False,
        conditional=False, scenario="any", raw_sku=None, raw_warehouse=None,
    ) for row in supply["rows"]
        if (row.sku, row.warehouse, row.uom) not in netted_keys]
    evidence = supply["evidence"] + forecast_evidence + outside_scope

    stage_rows = stages_frame(supply["stage_balances"])
    schedule_rows = tranches_frame(supply["schedule"])
    milestone_rows = milestones_frame(supply["stage_balances"])
    tables = artifacts.build_tables(result, evidence, stage_rows=stage_rows,
                                    schedule_rows=schedule_rows, milestone_rows=milestone_rows)
    tables["third_party_demand"] = artifacts._third_party_frame(third_party_rows)
    out_dir = Path(args.out)
    paths = artifacts.write_parquet(tables, out_dir)

    facts = tables["supply_facts"]
    net_rows = tables["supply_netting"]
    demand_accounted = sum(len(t["demand_dispositions"]) for t in result["targets"])
    checks = dict(
        bucket_identities_passed=True,           # engine 对每一行调用 assert_bucket_identities
        demand_four_key_duplicates=demand_meta["four_key_duplicates"],
        netting_allowed_all_true=True,
        demand_rows_in=len(demand_rows),
        demand_rows_historical=len(default_rows),
        demand_rows_forecast=len(demand_rows) - len(default_rows),
        forecast_demand_quantity=float(forecast_meta.get("demand_quantity") or 0.0),
        demand_rows_accounted=demand_accounted,
        demand_rows_before_as_of=sum(
            1 for t in result["targets"] for d in t["demand_dispositions"]
            if d["reason"] == "before_as_of"),
        demand_rows_skipped_no_horizon_demand=len(demand_rows) - demand_accounted,
        supply_rows_in=len(supply["rows"]),
        supply_rows_outside_demand_keys=len(outside_scope),
        supply_evidence_rows=len(supply["evidence"]),
        supply_facts_rows=int(len(facts)),
        netting_rows=int(len(net_rows)),
        opening_rows_excluded=sum(t.get("opening_excluded", 0) for t in result["targets"]),
        duplicate_supply_rows=int((facts["disposition_reason"] == "duplicate_supply_row").sum())
        if "disposition_reason" in facts.columns else 0,
        same_batch_excluded_rows=int(
            facts["disposition_reason"].isin(["same_batch_counted_once"]).sum())
        if "disposition_reason" in facts.columns else 0,
        stage_validation_errors=stage_errors,
        ledger_conserved=all(
            account["input_known"] == account["counted"] + account["excluded_known"]
            for target in result["targets"] for scenario in target["scenarios"].values()
            for account in scenario["ledger"].values()),
        demand_unclassified_quantity=unclassified_quantity(demand_df),
    )
    partial_reasons = [
        "供应来源未覆盖全部渠道（通途库存快照/在途 + 开放 PO 或通途采购单），业务覆盖 unverified",
        "通途在途与采购单无逐行 ETA，保持 date_unproven 条件态",
        "未履约 SO 余额未接入（backlog 为空）时，未来桶只剩预测与结转，不含开放 SO",
        "退货仓按业务口径不计可用供给（单列证据），相关键无期初基准时转 unknown，不写 0",
        "占位/物料 SKU 已排除出可用供给（单列证据），其数量不进任何总量口径",
        "预测只覆盖通过预测资格（netting_eligible）的 SKU×仓；未覆盖键仍只有历史需求，"
        "预测资格与需求净额资格是两套字段",
    ]
    net_rows_note = {
        "demand_gap_semantics": "demand 与 gap 为含跨桶结转口径（= 本桶需求 + 上桶未满足）；"
                                "逐桶求和会重复计数，请用 period_demand / carried_unserved，"
                                "视界末累计未满足看最后一个桶的 unserved",
        "columns_added_2026_10_27B": ["period_demand", "carried_unserved"],
    }

    stage_summary = [dict(order_key=row["order_key"], sku=row["sku"], uom=row["uom"],
                          total=row["total"], delta=row["delta"], balanced=row["balanced"],
                          by_stage=row["by_stage"])
                     for row in summarize_stage_balances(supply["stage_balances"])]
    facts_v1 = dict(
        stage_balances=dict(
            rows=len(stage_rows),
            stages=sorted({r["stage"] for r in stage_rows}),
            validation_errors=stage_errors,
            order_balance=stage_summary,
            coverage_gap="仅通途在途可作为真实阶段余额；未排产/在产/完工待发/到仓待上架无本地源",
        ),
        availability_schedule=dict(
            rows=len(schedule_rows),
            counted=sum(1 for r in schedule_rows if not r["exclusion_reason"]),
            conditional=sum(1 for r in schedule_rows if r["scenario"] == "conditional"),
            exclusions={reason: sum(1 for r in schedule_rows if r["exclusion_reason"] == reason)
                        for reason in sorted({r["exclusion_reason"] for r in schedule_rows if r["exclusion_reason"]})},
            date_adapter="sellable_at 优先；缺失则用 actual_at/expected_at；都没有保持 unknown",
        ),
        milestones=dict(rows=len(milestone_rows),
                        note="里程碑字段在结构里，真实来源尚无逐行计划/预计/实际日期"),
    )

    manifest = artifacts.base_manifest(
        as_of=as_of, buckets=buckets, demand_meta=demand_meta,
        blocked_meta=_blocked_meta(Path(args.demand_blocked) if args.demand_blocked else None),
        stock_meta=supply["stock_meta"], po_meta=supply["po_meta"], backlog_meta=backlog_meta,
        extra=dict(
            checks=checks,
            facts_v1=facts_v1,
            forecast=forecast_meta,
            input_files=dict(
                stock=_file_meta(args.stock), po=_file_meta(args.po),
                po_tongtool=_file_meta(args.po_tongtool), sku_map=_file_meta(args.sku_map),
                uom_cache=_file_meta(args.uom_cache),
                warehouse_aliases=_file_meta(args.warehouse_aliases),
                demand=_file_meta(args.demand),
                demand_blocked=_file_meta(args.demand_blocked),
            ),
            code=_git_meta(),
            timing=_timing(supply["stock_meta"], as_of),
            po_tongtool=supply["po_tongtool_meta"],
            net_rows_note=net_rows_note,
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
