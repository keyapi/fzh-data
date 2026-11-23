# -*- coding: utf-8 -*-
"""未履约 SO 逐单审计：把 W1 阶段余额与 SO 行对齐，出「能不能作为条件供给」的事实。

输入
- ``w1_supply_facts_v2/supply_facts_raw.jsonl``：97 张开放 SO 的 W1 返回（阶段余额 / 里程碑 / 关联）
- ``pack-2026-10-26-r5/so_backlog_rows.csv``：SO 行（客户、工厂仓、开放量、交付日、分公司）

输出（本地 CSV）每单一行：阶段余额、WO 状态与实产、DN/运单、逾期天数、预计到仓与依据、
异常标记与处置建议。**只读事实，不改净额、不下单。**

预计到仓口径（任务指定）：``锚点 + 90 天业务口径``；若路径 [锚点, 锚点+90] 穿越春节
（2027-02-06）再加 60 天。锚点为阶段/里程碑可观测日期，缺失时退回 SO 交付日或审计日；
只有 ``not_planned`` / ``unknown`` 证据的单标 ``unknown``，不给日期。
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

AUDIT_DATE = date(2026, 10, 27)
SPRING_FESTIVAL_2027 = date(2027, 2, 6)
ORDER_TO_BRANCH_DAYS = 90
FESTIVAL_BUFFER_DAYS = 60

STAGES = ("in_production", "produced_pending_dn", "shipped_in_transit", "not_planned",
          "unknown", "over_produced", "arrived_not_sellable", "delivered_sellable")
STAGE_LABELS = {
    "in_production": "在产",
    "produced_pending_dn": "完工待发运",
    "shipped_in_transit": "在途",
    "not_planned": "未排产",
    "unknown": "阶段未归类",
    "over_produced": "超产",
}


def _num(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if pd.isna(number) else number


def _d(text) -> date | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    try:
        return pd.Timestamp(str(text)).date()
    except (TypeError, ValueError):
        return None


def crosses_spring_festival(start: date, days: int = ORDER_TO_BRANCH_DAYS) -> bool:
    """[start, start+days] 是否穿越春节（2027-02-06）前后各 15 天窗口。"""
    end = start + timedelta(days=days)
    window_start = SPRING_FESTIVAL_2027 - timedelta(days=15)
    window_end = SPRING_FESTIVAL_2027 + timedelta(days=45)
    return start <= window_end and end >= window_start


def estimate_arrival(start: date | None, days: int = ORDER_TO_BRANCH_DAYS) -> tuple[date | None, int, bool]:
    """返回 (预计到仓日, 春节缓冲天数, 是否穿越春节)。"""
    if start is None:
        return None, 0, False
    festival = crosses_spring_festival(start, days)
    buffer_days = FESTIVAL_BUFFER_DAYS if festival else 0
    return start + timedelta(days=days + buffer_days), buffer_days, festival


def load_so_lines(path: str | Path) -> pd.DataFrame:
    """读取全部 SO 行（**不**过滤单列行），保证 97 单全覆盖。"""
    return pd.read_csv(path, encoding="utf-8-sig")


def load_w1(path: str | Path) -> dict[str, dict]:
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        out[str(record.get("so"))] = record.get("payload") or {}
    return out


def audit_so(so: str, lines: pd.DataFrame, payload: dict) -> dict:
    stages = payload.get("stage_balances") or []
    milestones = payload.get("milestones") or []
    manifest = payload.get("manifest") or {}
    coverage = manifest.get("coverage") or {}

    open_qty = float(pd.to_numeric(lines["quantity"], errors="coerce").sum())
    counted_qty = float(pd.to_numeric(
        lines.loc[lines["excluded_reason"].isna(), "quantity"], errors="coerce").sum())
    excluded_reasons = "；".join(sorted({str(r) for r in lines["excluded_reason"].dropna()}))
    delivery_dates = sorted({_d(v) for v in lines["scheduled_delivery"] if _d(v)})
    first_delivery = delivery_dates[0] if delivery_dates else None
    overdue_days = max(0, (AUDIT_DATE - first_delivery).days) if first_delivery else None

    w1_lines = payload.get("lines") or []
    w1_total = sum(_num(l.get("qty")) for l in w1_lines)
    w1_delivered = sum(_num(l.get("delivered_qty")) for l in w1_lines)
    in_house = [s for s in stages if str(s.get("scope") or "in_house") == "in_house"]
    fba = [s for s in stages if str(s.get("scope")) == "external_fba"]
    totals = {stage: sum(_num(s.get("qty")) for s in in_house if s.get("stage") == stage)
              for stage in STAGES}
    fba_total = sum(_num(s.get("qty")) for s in fba)

    wo_records = sorted({str(s.get("source_record")) for s in in_house
                         if str(s.get("source_record") or "").startswith("WO")})
    dn_records = sorted({str(s.get("source_record")) for s in in_house
                         if str(s.get("source_record") or "").startswith("DN")})

    start_ms = [m for m in milestones if m.get("node") == "production_start"]
    end_ms = [m for m in milestones if m.get("node") == "production_end"]
    dispatch_ms = [m for m in milestones if m.get("node") == "dispatch"]
    wo_started = sum(1 for m in start_ms if m.get("actual_at"))
    wo_finished = sum(1 for m in end_ms if m.get("actual_at"))
    produced_actual = sum(_num(m.get("qty")) for m in end_ms if m.get("actual_at"))

    # 锚点：阶段里最新的可观日期 → 里程碑 latest/actual → SO 交付日
    dates = []
    for item in stages:
        for key in ("available_date", "latest_expected_at", "actual_at"):
            value = _d(item.get(key))
            if value:
                dates.append(value)
    for item in milestones:
        for key in ("actual_at", "latest_expected_at", "committed_due_at"):
            value = _d(item.get(key))
            if value:
                dates.append(value)
    anchor = max(dates) if dates else first_delivery

    has_only_unplanned = bool(stages) and all(
        s.get("stage") in ("not_planned", "unknown") for s in in_house) and not any(
        totals[s] > 0 for s in ("in_production", "produced_pending_dn", "shipped_in_transit"))
    # 锚点不早于审计日：阶段证据可能停在很久以前（DN 已发但长期在途），
    # 直接拿旧日期 +90 天会算出一个过去的“预计到仓”。
    anchor_lag_days = (AUDIT_DATE - anchor).days if anchor else None
    effective_anchor = max(anchor, AUDIT_DATE) if anchor else None
    if not stages or has_only_unplanned:
        arrival, buffer_days, festival = None, 0, False
        confidence = "unknown"
    else:
        arrival, buffer_days, festival = estimate_arrival(effective_anchor)
        confidence = "estimated" if arrival else "unknown"

    stage_sum = sum(totals[s] for s in STAGES)
    stage_sum_no_over = stage_sum - totals["over_produced"]
    excess_cumulative = sum(_num(s.get("cumulative_excess_qty")) for s in in_house)
    # 守恒以 W1 的 SO 总量（开放 + 已发）为准，超产是订单外的额外实物，单独剔出比较
    conserved = abs(stage_sum_no_over - w1_total) <= max(0.01, w1_total * 1e-6)
    anomalies = []
    if totals["produced_pending_dn"] > 0:
        anomalies.append("已完工未发运")
    if totals["not_planned"] > 0:
        anomalies.append("有未排产")
    if excess_cumulative > 0 or totals["over_produced"] > 0:
        anomalies.append("超产")
    if stages and not conserved:
        anomalies.append(
            f"阶段与SO总量不守恒(阶段{stage_sum_no_over:g}≠SO总量{w1_total:g})")
    if fba and in_house:
        anomalies.append("FBA/自营混")
    elif fba and not in_house:
        anomalies.append("仅FBA")
    if not stages:
        anomalies.append("无W1阶段证据")
    if overdue_days:
        anomalies.append(f"逾期{overdue_days}天")
    if anchor_lag_days is not None and anchor_lag_days > 7 and not has_only_unplanned:
        anomalies.append(f"阶段证据陈旧{anchor_lag_days}天")

    if totals["produced_pending_dn"] > 0 or totals["shipped_in_transit"] > 0:
        verdict = "可作条件供给"
    elif totals["in_production"] > 0 or totals["not_planned"] > 0:
        verdict = "需催（在产/未排产）"
    else:
        verdict = "无法判断（无阶段证据）"

    return dict(
        SO=so,
        客户=str(lines["customer"].iloc[0]),
        分公司仓=str(lines["branch_warehouse"].iloc[0]),
        工厂仓="；".join(sorted({str(v) for v in lines["factory_warehouse"]})),
        开放量=round(open_qty, 4),
        计入管线量=round(counted_qty, 4),
        单列原因=excluded_reasons,
        W1开放量=round(w1_total - w1_delivered, 4),
        W1已发量=round(w1_delivered, 4),
        行数=int(len(lines)),
        交付日=first_delivery.isoformat() if first_delivery else "",
        逾期天数=overdue_days,
        在产=round(totals["in_production"], 4),
        完工待发运=round(totals["produced_pending_dn"], 4),
        在途=round(totals["shipped_in_transit"], 4),
        未排产=round(totals["not_planned"], 4),
        unknown=round(totals["unknown"], 4),
        超产=round(totals["over_produced"], 4),
        累计超产=round(excess_cumulative, 4),
        已到未可售=round(totals["arrived_not_sellable"], 4),
        已交付=round(totals["delivered_sellable"], 4),
        FBA量=round(fba_total, 4),
        WO数=len(wo_records),
        WO已开工=wo_started,
        WO已完工=wo_finished,
        实产量=round(produced_actual, 4),
        DN数=len(dn_records),
        运单数=int(coverage.get("shipments") or 0),
        阶段合计=round(stage_sum, 4),
        阶段合计_不含超产=round(stage_sum_no_over, 4),
        守恒="是" if conserved else "否",
        锚点日=anchor.isoformat() if anchor else "",
        锚点滞后天数=anchor_lag_days,
        起算日=effective_anchor.isoformat() if effective_anchor else "",
        预计到仓=arrival.isoformat() if arrival else "",
        春节缓冲天数=buffer_days,
        穿越春节="是" if festival else "否",
        日期置信度=confidence,
        异常="；".join(anomalies) or "无",
        处置建议=verdict,
        W1_partial=str(manifest.get("partial")),
        W1_rule_version=str(manifest.get("rule_version")),
    )


def audit_all(so_lines: pd.DataFrame, w1: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for so, group in so_lines.groupby("so"):
        payload = w1.get(str(so)) or {}
        rows.append(audit_so(str(so), group, payload))
    frame = pd.DataFrame(rows)
    return frame.sort_values(["处置建议", "开放量"], ascending=[True, False]).reset_index(drop=True)


def _normalized_anomalies(frame: pd.DataFrame) -> dict:
    """把逐单明细里的数值型异常归并成类别，便于看板阅读。"""
    counts: dict[str, int] = {}
    for row in frame["异常"]:
        for item in str(row).split("；"):
            item = item.strip()
            if not item or item == "无":
                continue
            if item.startswith("阶段与SO总量不守恒"):
                key = "阶段与SO总量不守恒"
            elif item.startswith("逾期"):
                key = "逾期（明细见行）"
            elif item.startswith("阶段证据陈旧"):
                key = "阶段证据陈旧>7天"
            else:
                key = item
            counts[key] = counts.get(key, 0) + 1
    return counts


def summarize(frame: pd.DataFrame) -> dict:
    def total(mask):
        return dict(orders=int(mask.sum()), qty=round(float(frame.loc[mask, "开放量"].sum()), 3))

    conditional = frame["处置建议"] == "可作条件供给"
    push = frame["处置建议"] == "需催（在产/未排产）"
    unknown = frame["处置建议"] == "无法判断（无阶段证据）"
    return dict(
        orders=int(len(frame)),
        open_qty=round(float(frame["开放量"].sum()), 3),
        conditional_supply=total(conditional),
        conditional_stage_qty=dict(
            transit=round(float(frame.loc[conditional, "在途"].sum()), 3),
            produced=round(float(frame.loc[conditional, "完工待发运"].sum()), 3),
        ),
        need_push=total(push),
        cannot_judge=total(unknown),
        overdue_orders=int((pd.to_numeric(frame["逾期天数"], errors="coerce") > 0).sum()),
        anomaly_counts=_normalized_anomalies(frame),
        w1_partial=sorted(set(frame["W1_partial"])),
        w1_rule_version=sorted(set(frame["W1_rule_version"])),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="未履约 SO 逐单审计（只读事实）")
    parser.add_argument("--w1", required=True, help="W1 逐 SO 缓存 JSONL")
    parser.add_argument("--so-lines", required=True, help="so_backlog_rows.csv")
    parser.add_argument("--out", required=True, help="输出 CSV 目录")
    args = parser.parse_args(argv)

    so_lines = load_so_lines(args.so_lines)
    w1 = load_w1(args.w1)
    audit = audit_all(so_lines, w1)
    summary = summarize(audit)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "so_open_audit_2026-10-27.csv"
    audit.to_csv(csv_path, index=False, encoding="utf-8-sig")
    (out_dir / "so_open_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("CSV：", csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
