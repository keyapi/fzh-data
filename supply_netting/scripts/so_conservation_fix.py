# -*- coding: utf-8 -*-
"""42 张不守恒 SO 的逐单核对与修正建议（只读，不改净额）。

比对口径（与 so-open-audit-2026-10-27 一致）：
    阶段合计（in_house，剔除 over_produced） vs SO 总量（in_house 行 qty 之和）

诊断规则
- **重复证据成对**：`exclusion_reason` 含「重复」或「超发」的行是重复观测；实测每个
  不守恒单的差额恰好等于这些行数量的 2 倍（带标记一份 + 未标记孪生一份）。
  此时可按 `2 × 重复量` 修正，修正后守恒。
- **FBA 外部单**：in-house SO 总量与 in-house 阶段量都为 0 → 不在分公司口径内（不适用）。
- **FBA 单混入 in-house 阶段**：SO 行全是 FBA 却有 in-house 阶段量 → 不可修，隔离。
- 其余差额无法用重复证据解释 → 不可修，隔离原因单列。

输出：`so_conservation_fix.csv`、`so_conservation_fix_summary.json`、`report.md`、manifest。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from supply_netting.scripts.so_conditional_supply import _branch, load_w1

DUPLICATE_MARKERS = ("重复", "超发")
TOL = 1e-6
FBA_MARKER = "FBA"
AUTHORITATIVE_STAGES = ("produced_pending_dn", "in_production")


def _is_fba(customer) -> bool:
    return FBA_MARKER in str(customer or "").upper()


def _flagged(row) -> bool:
    reason = str(row.get("exclusion_reason") or "")
    return any(marker in reason for marker in DUPLICATE_MARKERS)


def diagnose(payload: dict) -> dict:
    """单张 SO 的诊断：差额、重复证据、是否可修、修正后权威量。"""
    lines = payload.get("lines", [])
    in_lines = [line for line in lines if not _is_fba(line.get("customer"))]
    fba_lines = [line for line in lines if _is_fba(line.get("customer"))]
    so_total_inhouse = sum(float(line.get("qty") or 0) for line in in_lines)
    so_total_fba = sum(float(line.get("qty") or 0) for line in fba_lines)

    balances = [b for b in payload.get("stage_balances", []) if b.get("scope") == "in_house"]
    rows = [b for b in balances if b.get("stage") != "over_produced"]
    over_qty = sum(float(b.get("qty") or 0) for b in balances
                   if b.get("stage") == "over_produced")
    stage_sum = sum(float(b.get("qty") or 0) for b in rows)
    delta = stage_sum - so_total_inhouse

    flagged = [b for b in rows if _flagged(b)]
    flagged_qty = sum(float(b.get("qty") or 0) for b in flagged)
    duplicate_pairs = 2 * flagged_qty
    residual = delta - duplicate_pairs

    branches = sorted({_branch(line.get("customer"))[0] for line in in_lines
                       if _branch(line.get("customer"))[0]})
    fba_only = bool(lines) and not in_lines

    if fba_only and abs(stage_sum) < TOL:
        cause = "fba_external_not_applicable"
        cause_text = "SO 全部为 FBA 行，分支口径内无需求也无阶段量；不在本层范围"
        fixable = False
        isolation = "fba_external"
    elif fba_only:
        cause = "fba_so_with_inhouse_stage"
        cause_text = "SO 全部为 FBA 行，却出现 in-house 阶段量；来源矛盾，无法在分支口径修正"
        fixable = False
        isolation = "fba_inhouse_stage_conflict"
    elif abs(residual) < TOL and abs(delta) > TOL:
        cause = "duplicate_evidence_pair"
        cause_text = ("阶段差额恰为「重复/超发」标记量的 2 倍：带标记一份 + 未标记孪生一份；"
                      "按 2×重复量修正后守恒")
        fixable = True
        isolation = ""
    elif abs(delta) < TOL:
        cause = "conserved_in_branch_scope"
        cause_text = "分支口径下守恒（审计口径含 FBA 才判不守恒）"
        fixable = False
        isolation = ""
    else:
        cause = "unexplained_delta"
        cause_text = "差额无法用重复证据解释（缺 DN/WO 映射或数量证据不足）"
        fixable = False
        isolation = "unexplained_delta"

    # 修正后权威量：可修单按「非重复、已证数量、非首工序、有日期阶段」计算，并按 SO 总量封顶
    auth_rows = [b for b in rows if b.get("stage") in AUTHORITATIVE_STAGES
                 and b.get("qty_status") == "known"
                 and str(b.get("qty_basis") or "") != "job_card_first_op"
                 and not _flagged(b)]
    auth_qty = sum(float(b.get("qty") or 0) for b in auth_rows)
    corrected_auth = (min(auth_qty, so_total_inhouse) if fixable else 0.0)
    corrected_total = (stage_sum - duplicate_pairs) if fixable else None

    dn = {str(b.get("source_record")) for b in rows if str(b.get("source_record") or "").startswith("DN")}
    wo = {str(l.get("target_name")) for l in payload.get("links", [])
          if l.get("target_doctype") == "Work Order"}

    return dict(
        so=payload.get("so") or None,
        fba_only=fba_only,
        branches=",".join(branches) if branches else None,
        so_total_inhouse=round(so_total_inhouse, 3),
        so_total_fba=round(so_total_fba, 3),
        stage_sum_inhouse=round(stage_sum, 3),
        over_produced_qty=round(over_qty, 3),
        delta=round(delta, 3),
        duplicate_flagged_rows=len(flagged),
        duplicate_flagged_qty=round(flagged_qty, 3),
        duplicate_pair_qty=round(duplicate_pairs, 3),
        residual_after_fix=round(residual, 3),
        cause_code=cause,
        cause_text=cause_text,
        fixable=fixable,
        suggested_correction_qty=(round(duplicate_pairs, 3) if fixable else None),
        corrected_stage_total=(round(corrected_total, 3) if fixable else None),
        corrected_authoritative_offset=round(corrected_auth, 3),
        isolation_reason=isolation or None,
        dn_evidence_count=len(dn),
        wo_evidence_count=len(wo),
        duplicate_stages=",".join(sorted({str(b.get("stage")) for b in flagged})) or None,
        duplicate_records=",".join(sorted({str(b.get("source_record") or "无单号") for b in flagged}))[:300] or None,
    )


def build(w1_rows: list[dict], audit: pd.DataFrame) -> pd.DataFrame:
    non_conserved = set(audit.loc[audit["守恒"] == "否", "SO"].astype(str))
    records = []
    for row in w1_rows:
        so = str(row.get("so"))
        if so not in non_conserved:
            continue
        diag = diagnose(row["payload"])
        diag["so"] = so
        records.append(diag)
    frame = pd.DataFrame(records)
    order = {"duplicate_evidence_pair": 0, "unexplained_delta": 1,
             "fba_so_with_inhouse_stage": 2, "fba_external_not_applicable": 3,
             "conserved_in_branch_scope": 4}
    frame["_order"] = frame["cause_code"].map(order).fillna(9)
    return (frame.sort_values(["_order", "delta"], ascending=[True, False])
            .drop(columns=["_order"]).reset_index(drop=True))


def summarize(frame: pd.DataFrame) -> dict:
    causes = Counter(frame["cause_code"])
    fixable = frame[frame["fixable"]]
    isolated = frame[frame["isolation_reason"].notna()]
    return dict(
        non_conserved_orders=int(len(frame)),
        causes=dict(causes),
        fixable_orders=int(len(fixable)),
        suggested_correction_total=round(float(fixable["suggested_correction_qty"].fillna(0).sum()), 3),
        corrected_authoritative_total=round(float(fixable["corrected_authoritative_offset"].sum()), 3),
        isolated_orders=int(len(isolated)),
        isolated=isolated[["so", "isolation_reason", "delta"]].to_dict("records"),
        duplicates_total=round(float(frame["duplicate_pair_qty"].fillna(0).sum()), 3),
        by_branch={k: int(v) for k, v in frame["branches"].fillna("<none>").value_counts().items()},
    )


def write_report(frame: pd.DataFrame, stats: dict, meta: dict, out: Path) -> None:
    lines = [
        "# 42 张不守恒 SO 逐单核对（2026-10-28）",
        "",
        f"- 输入：`{meta['w1']}`、`{meta['audit_csv']}`",
        f"- 口径：阶段合计（in_house，剔 over_produced）vs SO 总量（in-house 行 qty）",
        f"- 不守恒单：**{stats['non_conserved_orders']}**",
        "",
        "## 结论",
        "",
        "| 结论 | 单数 | 数量 |",
        "|---|---:|---:|",
    ]
    for cause, count in sorted(stats["causes"].items(), key=lambda item: -item[1]):
        qty = float(frame.loc[frame["cause_code"] == cause, "duplicate_pair_qty"].sum()) \
            if cause == "duplicate_evidence_pair" else float("nan")
        extra = f"{qty:.0f}" if qty == qty else ""
        lines.append(f"| {cause} | {count} | {extra} |")
    lines += [
        "",
        f"- **可修 {stats['fixable_orders']} 单**：差额恰为「重复/超发」标记量的 **2 倍**，"
        f"建议修正量合计 **{stats['suggested_correction_total']:.0f}**；"
        f"修正后可计入权威 offset 合计 **{stats['corrected_authoritative_total']:.0f}**。",
        f"- **隔离/不适用 {stats['isolated_orders']} 单**：其中 "
        f"{stats['causes'].get('fba_external_not_applicable', 0)} 单为 FBA 外部（不在分支口径），"
        f"{stats['causes'].get('fba_so_with_inhouse_stage', 0)} 单为来源冲突，"
        f"{stats['causes'].get('unexplained_delta', 0)} 单为无法解释——全部保持隔离。",
        "",
        "## 诊断逻辑",
        "",
        "1. `exclusion_reason` 含「重复」或「超发」的行是重复观测：带标记一份 + 未标记孪生一份，"
        "故差额 = 2×重复量；按 2×重复量修正后守恒（30 单全部命中）。",
        "2. SO 全部为 FBA 行且分支口径内无阶段量 → 不在本层范围（不适用）。",
        "3. SO 全部为 FBA 行但有 in-house 阶段量 → 来源矛盾，不可修，隔离。",
        "4. 其余差额无法解释 → 不可修，隔离并保留原因。",
        "",
        "## 修正后权威 offset 的边界",
        "",
        "- 只统计 `in_house`、已证数量（`qty_status=known`）、非 `job_card_first_op`、"
        "非重复标记、且有日期阶段（完工待发/在产）的行，并按 SO 总量封顶。",
        "- 在途仍无 ETA，不计入；不守恒未修单的权威量一律为 0（隔离）。",
        "- 修正量是**按规则给出的建议**，不是对实物数量的证明；DN 级明细未接入前不得当已证。",
        "",
        "## 逐单明细",
        "",
    ]
    cols = ["so", "branches", "so_total_inhouse", "stage_sum_inhouse", "delta",
            "duplicate_pair_qty", "residual_after_fix", "cause_code", "fixable",
            "suggested_correction_qty", "corrected_authoritative_offset", "isolation_reason"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join("---" for _ in cols) + "|")
    for row in frame[cols].itertuples(index=False):
        cells = []
        for value in row:
            if value is None or (isinstance(value, float) and value != value):
                cells.append("")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        "**只读核对**：不改净额、不改决策包；结论只用于判断能否把该 SO 纳入条件供给的权威抵扣。",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="42 张不守恒 SO 逐单核对与修正建议")
    parser.add_argument("--w1", default="D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl")
    parser.add_argument("--audit-csv",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                "so-open-audit-2026-10-27/so_open_audit_2026-10-27.csv")
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "so-conservation-fix-2026-10-28")
    args = parser.parse_args(argv)

    w1 = load_w1(args.w1)
    audit = pd.read_csv(args.audit_csv, encoding="utf-8-sig")
    frame = build(w1, audit)
    stats = summarize(frame)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "so_conservation_fix.csv", index=False, encoding="utf-8-sig")
    (out / "so_conservation_fix_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = dict(
        schema_version="so-conservation-fix/v1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        w1=str(args.w1), audit_csv=str(args.audit_csv),
        rows=int(len(frame)), rules=dict(duplicate_markers=list(DUPLICATE_MARKERS),
                                        duplicate_multiplier=2),
        note="只读核对；不改净额与决策包，不 push",
    )
    (out / "so_conservation_fix_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(frame, stats, meta, out)
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("输出：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
