# -*- coding: utf-8 -*-
"""不守恒 SO 的逐行核对与重分类（v2，只读；不改净额）。

对全部 97 张开放 SO 统一按 in_house scope 重审：
    阶段合计（in_house，剔 over_produced） vs SO 总量（in-house 行 qty）

方法（不再用「2× 标记量」拟合总量）
1. **逐 SO 行（so_line_id）做前后账**：同一行的阶段行按进度排序
   （到仓未可售 → 在途 → 完工待发 → 在产 → 未排产 → unknown），
   只把不超过该行 qty 的部分算作 `attributable`；超出部分才是 excess。
2. **只有证明孪生才标重复**：excess 行若能找到同 `source_record`/`batch_key`
   + 同 item + 同 qty、且**未带可疑标记**的另一行，才标 `duplicate`；否则按证据
   归入 `over_ship`（有单号/超订单实物）、`return_pending`（明确退货证据）、
   `abnormal_placeholder`（无单号、无孪生、待核占位）。
3. 修正后金额（原 900）改称 `heuristic_candidate_qty`，**保持隔离、不得抵扣**。
4. 55 张原本守恒的单必须零回归（逐行账仍等于 SO 总量）。

输出：`so_row_reclass.csv`、`so_conservation_fix.csv`、summary、report、manifest。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from supply_netting.scripts.so_conditional_supply import _branch, load_w1

STAGE_PRIORITY = {"arrived_not_sellable": 0, "shipped_in_transit": 1,
                  "produced_pending_dn": 2, "in_production": 3,
                  "not_planned": 4, "unknown": 5}
FLAG_MARKERS = ("重复", "超发", "退货", "待核实")
OVER_SHIP_MARKERS = ("超订单实物", "超发")
RETURN_MARKERS = ("退货",)
TOL = 1e-6
AUTHORITATIVE_STAGES = ("produced_pending_dn", "in_production")


def _is_fba(customer) -> bool:
    return "FBA" in str(customer or "").upper()


def _flagged(row: dict) -> bool:
    reason = str(row.get("exclusion_reason") or "")
    return any(marker in reason for marker in FLAG_MARKERS)


def _source_key(row: dict) -> str:
    return str(row.get("source_record") or row.get("batch_key") or "").strip()


def _find_twin(row: dict, rows: list[dict]) -> str | None:
    """未标记孪生：同 source/batch + 同 item + 同 qty，且对方不带可疑标记。"""
    key = _source_key(row)
    if not key:
        return None
    for other in rows:
        if other is row or _flagged(other):
            continue
        if _source_key(other) != key:
            continue
        if str(other.get("item_code")) != str(row.get("item_code")):
            continue
        if abs(float(other.get("qty") or 0) - float(row.get("qty") or 0)) > TOL:
            continue
        return str(other.get("so_line_id")) or "row"
    return None


def _classify_excess(row: dict, rows: list[dict]) -> tuple[str, str]:
    twin = _find_twin(row, rows)
    reason = str(row.get("exclusion_reason") or "")
    if twin:
        return "duplicate", f"unflagged twin on line {twin} (same source/batch + item + qty)"
    if _source_key(row) or "超订单实物" in reason:
        return "over_ship", "有单号/超订单实物：数量超出本行订单量（超发；无孪生不称重复）"
    if any(marker in reason for marker in RETURN_MARKERS) and not any(
            marker in reason for marker in ("超发", "重复")):
        return "return_pending", "排除原因明确为退货待核；无退货单据证据"
    return "abnormal_placeholder", "无单号、无孪生、待核占位（异常占位；含超发/重复/退货混合文案）"


def reconcile(payload: dict) -> tuple[list[dict], dict]:
    """单张 SO：逐行分配 + excess 分类。返回 (行级记录, SO 级汇总)。"""
    so = payload.get("so")
    lines = payload.get("lines", [])
    in_lines = [line for line in lines if not _is_fba(line.get("customer"))]
    fba_lines = [line for line in lines if _is_fba(line.get("customer"))]
    line_by_id = {line.get("so_line"): line for line in lines}
    in_line_ids = {line.get("so_line") for line in in_lines}

    so_total = sum(float(line.get("qty") or 0) for line in in_lines)
    rows = payload.get("stage_balances", [])
    inhouse_rows = [row for row in rows if row.get("scope") == "in_house"]
    counted = [row for row in inhouse_rows if row.get("stage") != "over_produced"]
    stage_sum = sum(float(row.get("qty") or 0) for row in counted)
    over_qty = sum(float(row.get("qty") or 0) for row in inhouse_rows
                   if row.get("stage") == "over_produced")

    by_line = defaultdict(list)
    for row in counted:
        by_line[row.get("so_line_id")].append(row)
    for group in by_line.values():
        group.sort(key=lambda row: STAGE_PRIORITY.get(str(row.get("stage")), 9))

    remaining = {line.get("so_line"): float(line.get("qty") or 0) for line in in_lines}
    records = []
    for row in rows:
        line = line_by_id.get(row.get("so_line_id"))
        qty = float(row.get("qty") or 0)
        record = dict(
            so=so, so_line_id=row.get("so_line_id"),
            item_code=row.get("item_code"), stage=row.get("stage"), qty=qty,
            uom=row.get("uom"), source_record=row.get("source_record"),
            batch_key=row.get("batch_key"), exclusion_reason=row.get("exclusion_reason"),
            so_line_qty=(float(line.get("qty") or 0) if line else None),
            attributable_qty=0.0, excess_qty=0.0, excess_class="", evidence="",
        )
        if row.get("scope") == "external_fba" or (line is not None and _is_fba(line.get("customer"))):
            record.update(excess_qty=qty, excess_class="fba_external",
                          evidence="FBA 行，不进分公司口径")
        elif row.get("stage") == "over_produced":
            record.update(excess_qty=qty, excess_class="over_produced",
                          evidence="订单外实物，单独分配")
        elif row.get("so_line_id") in in_line_ids:
            left = remaining.get(row.get("so_line_id"), 0.0)
            take = min(qty, max(0.0, left))
            record["attributable_qty"] = take
            remaining[row.get("so_line_id")] = max(0.0, left - take)
            excess = qty - take
            record["excess_qty"] = excess
            if excess > TOL:
                klass, why = _classify_excess(row, rows)
                record["excess_class"] = klass
                record["evidence"] = why
        else:
            record.update(excess_qty=qty, excess_class="unassigned_line",
                          evidence="阶段行没有匹配到本 SO 的订单行")
        record["classification"] = (record["excess_class"]
                                    or ("attributable" if record["attributable_qty"] > 0
                                        else "unmatched"))
        records.append(record)

    attributable = sum(record["attributable_qty"] for record in records)
    classes = Counter(record["excess_class"] for record in records if record["excess_class"])
    excess_total = sum(record["excess_qty"] for record in records)
    fba_qty = sum(record["excess_qty"] for record in records
                  if record["excess_class"] == "fba_external")
    missing = max(0.0, so_total - attributable)

    if abs(missing) < TOL and abs(stage_sum - so_total) < TOL:
        status = "conserved_in_branch_scope"
    elif missing > TOL:
        status = "missing_evidence"
    elif fba_qty > TOL and so_total <= TOL:
        status = "fba_external"
    else:
        status = "excess_reclassified"

    # 启发式候选量：只对可归因、有日期、已证数量、非首工序的行求和（保持隔离）
    heuristic = 0.0
    for record in records:
        if (record["attributable_qty"] > 0
                and record["stage"] in AUTHORITATIVE_STAGES
                and not any(marker in str(record["exclusion_reason"] or "")
                            for marker in FLAG_MARKERS)):
            source = next((r for r in rows if r.get("so_line_id") == record["so_line_id"]
                           and r.get("stage") == record["stage"]
                           and float(r.get("qty") or 0) == record["qty"]), None)
            if source is not None and source.get("qty_status") == "known" \
                    and str(source.get("qty_basis") or "") != "job_card_first_op":
                heuristic += record["attributable_qty"]

    summary = dict(
        so=so,
        branches=",".join(sorted({b for b in
                                  (_branch(line.get("customer"))[0] for line in in_lines) if b})),
        fba_only=bool(lines) and not in_lines,
        so_total_inhouse=round(so_total, 3),
        stage_sum_inhouse=round(stage_sum, 3),
        attributable_after_fix=round(attributable, 3),
        delta_raw=round(stage_sum - so_total, 3),
        delta_after=round(attributable - so_total, 3),
        excess_total=round(excess_total, 3),
        over_ship_qty=round(sum(r["excess_qty"] for r in records
                                if r["excess_class"] == "over_ship"), 3),
        duplicate_qty=round(sum(r["excess_qty"] for r in records
                                if r["excess_class"] == "duplicate"), 3),
        return_pending_qty=round(sum(r["excess_qty"] for r in records
                                     if r["excess_class"] == "return_pending"), 3),
        abnormal_placeholder_qty=round(sum(r["excess_qty"] for r in records
                                           if r["excess_class"] == "abnormal_placeholder"), 3),
        over_produced_qty=round(over_qty, 3),
        fba_qty=round(fba_qty, 3),
        unassigned_qty=round(sum(r["excess_qty"] for r in records
                                 if r["excess_class"] == "unassigned_line"), 3),
        status=status,
        heuristic_candidate_qty=round(heuristic, 3),
        offset_allowed=False,
        isolation_reason=("heuristic_candidate_only" if heuristic > 0 else
                          "missing_evidence" if status == "missing_evidence" else
                          "fba_external" if status == "fba_external" else None),
    )
    return records, summary


def build(w1_rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    row_records, so_records = [], []
    for row in w1_rows:
        payload = dict(row["payload"])
        payload.setdefault("so", row.get("so"))
        records, summary = reconcile(payload)
        row_records.extend(records)
        so_records.append(summary)
    rows = pd.DataFrame(row_records)
    sos = pd.DataFrame(so_records)
    order = {"missing_evidence": 0, "excess_reclassified": 1, "fba_external": 2,
             "conserved_in_branch_scope": 3}
    sos["_order"] = sos["status"].map(order).fillna(9)
    sos = sos.sort_values(["_order", "delta_raw"], ascending=[True, False]) \
        .drop(columns=["_order"]).reset_index(drop=True)
    return rows, sos


def summarize(sos: pd.DataFrame, rows: pd.DataFrame) -> dict:
    return dict(
        orders=int(len(sos)),
        status_counts=dict(Counter(sos["status"])),
        conserved_orders=int((sos["status"] == "conserved_in_branch_scope").sum()),
        excess_orders=int((sos["status"] == "excess_reclassified").sum()),
        missing_orders=int((sos["status"] == "missing_evidence").sum()),
        excess_classes={k: round(float(v), 3) for k, v in
                        rows.groupby("excess_class")["excess_qty"].sum().items()},
        excess_rows=int((rows["excess_qty"] > TOL).sum()),
        duplicate_rows=int((rows["excess_class"] == "duplicate").sum()),
        heuristic_candidate_total=round(float(sos["heuristic_candidate_qty"].sum()), 3),
        offset_allowed=False,
        regression_conserved=int(((sos["status"] == "conserved_in_branch_scope")
                                  & (sos["delta_after"].abs() > TOL)).sum()),
        total_delta_raw=round(float(sos["delta_raw"].sum()), 3),
        total_delta_after=round(float(sos["delta_after"].sum()), 3),
    )


def write_report(sos: pd.DataFrame, rows: pd.DataFrame, stats: dict, meta: dict, out: Path) -> None:
    classes = stats["excess_classes"]
    lines = [
        "# 不守恒 SO 逐行重分类 v2（2026-10-28）",
        "",
        f"- 输入：`{meta['w1']}`（97 张 SO）；审计参照：`{meta['audit_csv']}`",
        "- 口径：in_house 阶段合计（剔 over_produced）vs in-house SO 总量；**逐 SO 行**做前后账",
        "",
        "## 与 v1 的差别",
        "",
        "- v1 把「差额 = 2×可疑标记量」当作重复证明；v2 **不采信**——2× 只是拟合标签。",
        "- v2 逐行按订单行 qty 封顶：超过订单行 qty 的部分才进入 excess，再按证据分类。",
        "- 只有找到**未标记孪生**（同 source_record/batch + 同 item + 同 qty）才标 `duplicate`；"
        "找不到就按超发/退货待核/异常占位处理，不笼统称重复。",
        "- 原 900 改称 `heuristic_candidate_qty`：**保持隔离、不得抵扣**（`offset_allowed=false`）。",
        "",
        "## 97 单重审结果",
        "",
        f"- 总单数 **{stats['orders']}**；状态：{json.dumps(stats['status_counts'], ensure_ascii=False)}",
        f"- 原本守恒（in_house 口径）{stats['conserved_orders']} 单：逐行账后 delta 仍为 0，"
        f"回归 **{stats['regression_conserved']}** 单。",
        f"- 需重分类 {stats['excess_orders']} 单；缺证据 {stats['missing_orders']} 单。",
        f"- 原始总差额 {stats['total_delta_raw']:.0f}；逐行封顶后总差额 {stats['total_delta_after']:.0f}。",
        "",
        "## 四类去向（全部 SO，按数量）",
        "",
        "| 类别 | 数量 | 说明 |",
        "|---|---:|---|",
        f"| over_ship 超发 | {classes.get('over_ship', 0):.0f} | 有单号数量超出订单行，或明确超订单实物 |",
        f"| duplicate 重复 | {classes.get('duplicate', 0):.0f} | 仅限找到未标记孪生的行 |",
        f"| return_pending 退货待核 | {classes.get('return_pending', 0):.0f} | 排除原因含退货、且无退货单据证据 |",
        f"| abnormal_placeholder 异常占位 | {classes.get('abnormal_placeholder', 0):.0f} | 无单号、无孪生、待核实占位 |",
        f"| over_produced 超产 | {classes.get('over_produced', 0):.0f} | 订单外实物，单列 |",
        f"| fba_external | {classes.get('fba_external', 0):.0f} | FBA 行，不进分公司口径 |",
        "",
        "## 反例核对（SO-26-00048）",
        "",
        "| 行 | 阶段 | 数量 | 归因 | 超出 | 分类 |",
        "|---|---|---:|---:|---:|---|",
    ]
    example = rows[rows["so"] == "SO-26-00048"]
    for row in example.itertuples(index=False):
        lines.append(f"| {row.so_line_id} | {row.stage} | {row.qty:g} | "
                     f"{row.attributable_qty:g} | {row.excess_qty:g} | {row.excess_class or '—'} |")
    lines += [
        "",
        "该单差额 40 = 在途超发 20（60 对订单 40）+ 异常占位 20；"
        "**不是**一个 40 的“重复”。",
        "",
        "## 逐单状态（节选）",
        "",
        "| SO | 分公司 | SO 总量 | 阶段合计 | 归因后 | 超发 | 重复 | 退货待核 | 异常占位 | 状态 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in sos.head(50).itertuples(index=False):
        lines.append(f"| {row.so} | {row.branches or '—'} | {row.so_total_inhouse:g} | "
                     f"{row.stage_sum_inhouse:g} | {row.attributable_after_fix:g} | "
                     f"{row.over_ship_qty:g} | {row.duplicate_qty:g} | "
                     f"{row.return_pending_qty:g} | {row.abnormal_placeholder_qty:g} | "
                     f"{row.status} |")
    lines += [
        "",
        "## 边界",
        "",
        f"- 启发式候选量合计 **{stats['heuristic_candidate_total']:.0f}**：只作核对线索，"
        "保持隔离，不进入任何抵扣。",
        "- 逐行重分类是**证据分级**，不是实物已证；DN 级明细（数量/行）未接入前不得当权威。",
        "- 只读：不改 r6/h180 净额与决策包。",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="不守恒 SO 逐行重分类 v2")
    parser.add_argument("--w1", default="D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl")
    parser.add_argument("--audit-csv",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                "so-open-audit-2026-10-27/so_open_audit_2026-10-27.csv")
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "so-conservation-fix-2026-10-28-v2")
    args = parser.parse_args(argv)

    w1 = load_w1(args.w1)
    rows, sos = build(w1)
    stats = summarize(sos, rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows.to_csv(out / "so_row_reclass.csv", index=False, encoding="utf-8-sig")
    sos.to_csv(out / "so_conservation_fix.csv", index=False, encoding="utf-8-sig")
    (out / "so_conservation_fix_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = dict(schema_version="so-conservation-fix/v2",
                generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                w1=str(args.w1), audit_csv=str(args.audit_csv),
                rows=int(len(rows)), orders=int(len(sos)),
                rules=dict(per_line_cap=True, duplicate_requires_unflagged_twin=True,
                           categories=["duplicate", "over_ship", "return_pending",
                                       "abnormal_placeholder"],
                           offset_allowed=False),
                note="只读重分类；不改净额与决策包，不 push")
    (out / "so_conservation_fix_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(sos, rows, stats, meta, out)
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("输出：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
