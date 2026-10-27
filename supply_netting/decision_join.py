# -*- coding: utf-8 -*-
"""把 r5 动作层接到宽口径决策包（只做 join，不改数量与去向）。

输入
- 宽表：``decision_pack_2026-10-29.parquet``（4,014 行 / 30 列，去向 建议补货·无需补货·不可算·待核）
- 动作层：``pack-2026-10-26-r5/conditional_decision_pack.csv``（545 行，仅覆盖有供给证据的键）

输出新目录（不覆盖原包）：保留原 30 列 + 8 个动作列。

规则（不用动作层反推去向）：
- ``destination=待核`` → 动作列全部留空，``action_applicability=no_supply_evidence``，**不写补单**；
- ``destination=不可算`` → ``action=不可算``；
- ``destination=无需补货`` → ``action=不需补（当前窗口）``；
- ``destination=建议补货`` → 用动作层给的 action；若动作层给的是“不需补”，
  在 ``action_basis`` 末尾标注口径冲突（宽表建议补、动作层按历史缺口算无缺口），数量不改。
- ``destination`` 与所有数量列**原样保留**，本模块只增列。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

JOIN_KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
ACTION_COLUMNS = ["action", "action_confidence", "action_qty", "residual_gap", "action_basis",
                  "action_source_so", "action_source_wo", "action_applicability",
                  "missing_evidence", "action_gap", "action_gap_basis",
                  "protect_gap_action_layer"]
# 动作层参与重算的列：决定动作时用宽表 gap（视界末），不再用 pack 的 protect_gap
PACK_INPUT_COLUMNS = ["action", "action_confidence", "action_basis", "action_source_so",
                      "action_source_wo", "so_stage_produced_pending_dn",
                      "so_stage_in_production", "so_stage_in_transit", "so_stage_not_planned",
                      "so_stage_unknown_missing_start", "so_stage_unknown_other",
                      "conditional_supply_qty", "w1_confidence", "protect_gap"]
ACTION_GAP_BASIS = "horizon_end"
ACTION_SHIP = "催发运"
ACTION_PRODUCE = "催生产"
ACTION_VERIFY_ARRIVAL = "核实到仓 ETA"
ACTION_VERIFY_ETA = "核实 ETA"
ACTION_BUY = "补单"
REPLENISH_ACTIONS = (ACTION_SHIP, ACTION_PRODUCE, ACTION_VERIFY_ARRIVAL, ACTION_VERIFY_ETA,
                     ACTION_BUY)

# 待核的缺证分组：按宽表原有 destination_reason 归组（原列保持不变）
MISSING_EVIDENCE_GROUPS = {
    "预测键未过资格且无库存基准": "not_qualified_no_stock_basis",
    "预测键未过资格": "not_qualified",
    "无预测覆盖（仅有库存，缺需求证据）": "stock_only_no_demand",
    "无预测覆盖且无库存基准": "no_forecast_no_stock",
}

NO_EVIDENCE = "no_supply_evidence"
HAS_EVIDENCE = "evidence"
# 宽表的 destination 取值
DEST_REPLENISH = "建议补货"
DEST_NO_NEED = "无需补货"
DEST_NOT_COMPUTABLE = "不可算"
DEST_PENDING = "待核"
# 本层写出的 action 取值
ACTION_NOT_COMPUTABLE = DEST_NOT_COMPUTABLE
ACTION_NO_NEED = "不需补（当前窗口）"
# 兼容旧引用
ACTION_REPLENISH = DEST_REPLENISH
ACTION_PENDING = DEST_PENDING
CONFLICT_NOTE = "口径冲突：宽表建议补货，动作层按历史缺口判无缺口；动作按动作层原值保留，需人工裁定"


def _gap_of(row) -> float | None:
    """动作缺口口径：视界末 qty_current，缺失时退回 gap_today（与宽表一致）。"""
    for column in ("qty_current", "gap_today"):
        value = row.get(column)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _missing_group(row) -> str:
    """待核缺证分组；「仅库存」里没有库存基准的行单独成「无预测且无库存」。"""
    reason = str(row.get("destination_reason") or "")
    group = MISSING_EVIDENCE_GROUPS.get(reason, "unclassified_no_supply_evidence")
    if group == "stock_only_no_demand":
        opening = row.get("opening")
        lower = row.get("opening_lower_bound")
        if (opening is None or (isinstance(opening, float) and pd.isna(opening))) and \
                (lower is None or (isinstance(lower, float) and pd.isna(lower))):
            return "no_forecast_no_stock"
    return group


def _confidence_of(row) -> str:
    hint = str(row.get("w1_confidence") or "")
    return hint if hint in ("measured", "estimated", "unknown") else "unknown"


def _replenish_action(row, gap: float | None) -> tuple[str, float, str, str]:
    """按视界末 gap 选动作：全覆盖优先，同覆盖按 完工→在产→在途→条件量→补单。"""
    gap_value = 0.0 if gap is None else max(0.0, float(gap))
    produced = float(row.get("so_stage_produced_pending_dn") or 0)
    in_prod = float(row.get("so_stage_in_production") or 0)
    missing_start = float(row.get("so_stage_unknown_missing_start") or 0)
    transit = float(row.get("so_stage_in_transit") or 0)
    unknown_other = float(row.get("so_stage_unknown_other") or 0)
    conditional = max(float(row.get("conditional_supply_qty") or 0),
                      float(row.get("po_qty") or 0), float(row.get("intransit_qty") or 0))
    candidates = [
        (ACTION_SHIP, produced, "完工待发运"),
        (ACTION_PRODUCE, in_prod + missing_start, "在产/工单已覆盖"),
        (ACTION_VERIFY_ARRIVAL, transit, "在途"),
        (ACTION_VERIFY_ETA, conditional, "在途/PO 条件量"),
    ]
    available = [c for c in candidates if c[1] > 0]
    if not available:
        return ACTION_BUY, 0.0, f"按视界末 gap {gap_value:g}：无阶段量/条件量 → 补单", _confidence_of(row)
    full = [c for c in available if c[1] >= gap_value]
    name, qty, label = full[0] if full else available[0]
    covered = min(qty, gap_value)
    basis = (f"按视界末 gap {gap_value:g} 选动作：{label} {qty:g}，覆盖 {covered:g}"
             + ("" if covered >= gap_value else f"，剩余 {gap_value - covered:g} 仍需补单"))
    if unknown_other:
        basis += f"；另有阶段待核实 {unknown_other:g}（unknown，不作供给）"
    return name, covered, basis, _confidence_of(row)


def sha256_of(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tag_baseline(merged: pd.DataFrame, baseline: pd.DataFrame | None) -> pd.DataFrame:
    """标出「上一版就建议补货」与「本版新增建议」的键，便于对照动作变化。"""
    if baseline is None or not len(baseline):
        merged["baseline_group"] = ""
        return merged
    cols = [c for c in JOIN_KEY]
    base = baseline[baseline["destination"] == DEST_REPLENISH]
    base_keys = set(map(tuple, base[cols].values))
    labels = []
    for row in merged.itertuples(index=False):
        key = tuple(getattr(row, c) for c in cols)
        if str(getattr(row, "destination")) != DEST_REPLENISH:
            labels.append("")
        elif key in base_keys:
            labels.append("original")
        else:
            labels.append("new")
    merged["baseline_group"] = labels
    return merged


def _group_stats(merged: pd.DataFrame) -> dict:
    out = {}
    for group in ("original", "new"):
        subset = merged[merged["baseline_group"] == group]
        if not len(subset):
            continue
        out[group] = dict(
            keys=int(len(subset)),
            qty_current=round(float(pd.to_numeric(subset.get("qty_current"), errors="coerce")
                                    .fillna(0).sum()), 3),
            actions={str(k): int(v) for k, v in subset["action"].value_counts().items()},
            action_qty=round(float(pd.to_numeric(subset.get("action_qty"), errors="coerce")
                                   .fillna(0).sum()), 3),
            residual=round(float(pd.to_numeric(subset.get("residual_gap"), errors="coerce")
                                 .fillna(0).sum()), 3),
        )
    return out


def join_actions(wide: pd.DataFrame, pack: pd.DataFrame,
                 baseline: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """返回 (带动作的宽表, join 统计)。原列顺序与数量列不变。"""
    base = wide.copy()
    original_columns = list(base.columns)
    missing = [c for c in JOIN_KEY if c not in pack.columns]
    if missing:
        raise ValueError(f"动作层缺 join 键：{missing}")
    duplicates = int(pack.duplicated(JOIN_KEY).sum())
    if duplicates:
        raise ValueError(f"动作层 join 键重复 {duplicates} 行，拒绝带病 join")

    pack_columns = [c for c in PACK_INPUT_COLUMNS if c in pack.columns]
    merged = base.merge(pack[JOIN_KEY + pack_columns],
                        on=JOIN_KEY, how="left", validate="one_to_one", suffixes=("", "_pack"))
    if len(merged) != len(base):
        raise ValueError(f"join 后行数变化：{len(base)} → {len(merged)}")

    matched = merged["action"].notna() if "action" in merged.columns else pd.Series(False, index=merged.index)
    destination = merged["destination"].astype(str)

    numeric_columns = ("action_qty", "residual_gap", "action_gap", "protect_gap_action_layer")
    for column in ACTION_COLUMNS:
        if column not in merged.columns:
            # 数值列必须是 float，否则写数字会撞 string dtype
            merged[column] = ([float("nan")] * len(merged)) if column in numeric_columns else ""

    applicability, conflicts = [], 0
    for index, row in merged.iterrows():
        dest = str(row["destination"])
        gap = _gap_of(row)
        merged.at[index, "action_gap"] = gap
        merged.at[index, "action_gap_basis"] = ACTION_GAP_BASIS
        merged.at[index, "protect_gap_action_layer"] = row.get("protect_gap_pack")
        if dest == DEST_PENDING:
            applicability.append(NO_EVIDENCE)
            merged.at[index, "missing_evidence"] = _missing_group(row)
            for column in ACTION_COLUMNS[:8]:
                # 数值列清成 NaN，文本列清成空串
                merged.at[index, column] = None if column in numeric_columns else ""
            continue
        applicability.append(HAS_EVIDENCE)
        merged.at[index, "missing_evidence"] = ""
        if dest == DEST_NOT_COMPUTABLE:
            # 不可算：动作留空（不给补单，也不假装有动作），原因留在 basis
            merged.at[index, "action"] = ""
            merged.at[index, "action_qty"] = None
            merged.at[index, "residual_gap"] = None
            merged.at[index, "action_basis"] = (
                f"净额不可算（{row.get('destination_reason') or 'no_snapshot_basis'}），不给出动作")
            continue
        if dest == DEST_NO_NEED:
            merged.at[index, "action"] = ACTION_NO_NEED
            merged.at[index, "action_qty"] = 0.0
            merged.at[index, "residual_gap"] = 0.0
            continue
        # 建议补货：按宽表 gap（视界末）重算动作，保证落在 5 类动作之内
        if dest == DEST_REPLENISH:
            action, covered, basis, confidence = _replenish_action(row, gap)
            if str(row.get("action")) == ACTION_NO_NEED:
                conflicts += 1        # 记录“原动作层判无需补”的行数（用于证明已消除）
                basis += "；原动作层按 7 天保护期判无缺口，本层改按视界末 gap 重算"
            merged.at[index, "action"] = action
            merged.at[index, "action_qty"] = covered
            merged.at[index, "residual_gap"] = max(0.0, (gap or 0.0) - covered)
            merged.at[index, "action_basis"] = basis
            merged.at[index, "action_confidence"] = confidence
    merged["action_applicability"] = applicability
    merged = tag_baseline(merged, baseline)

    stats = dict(
        rows_wide=int(len(base)),
        rows_pack=int(len(pack)),
        matched=int(matched.sum()),
        unmatched=int((~matched).sum()),
        match_rate=round(float(matched.sum()) / len(base), 6) if len(base) else 0.0,
        destination_counts={str(k): int(v) for k, v in destination.value_counts().items()},
        applicability_counts={str(k): int(v) for k, v in
                              pd.Series(applicability).value_counts().items()},
        action_counts={str(k): int(v) for k, v in
                       merged.loc[merged["action_applicability"] == HAS_EVIDENCE, "action"]
                       .value_counts().items()},
        suggested_with_action=int(((destination == DEST_REPLENISH)
                                   & (merged["action"].astype(str) != "")).sum()),
        suggested_total=int((destination == DEST_REPLENISH).sum()),
        # 终态冲突：宽表建议补货但动作不在 5 类之内（必须为 0）
        destination_action_conflicts=int(((destination == DEST_REPLENISH)
                                          & (~merged["action"].astype(str).isin(REPLENISH_ACTIONS))).sum()),
        # 诊断：动作层原判“无需补”的行数（重算前），用于证明口径差已消除
        legacy_action_layer_mismatches=int(conflicts),
        baseline_groups=_group_stats(merged),
        replenish_action_values=sorted({str(a) for a, d in
                                        zip(merged["action"], destination)
                                        if d == DEST_REPLENISH}),
        action_gap_basis=ACTION_GAP_BASIS,
        action_gap_sources="qty_current（缺失时 gap_today），与宽表同口径；protect_gap 仅作附注",
        missing_evidence_counts=dict(
            {slug: 0 for slug in MISSING_EVIDENCE_GROUPS.values()},
            **{str(k): int(v) for k, v in
               merged.loc[merged["action_applicability"] == NO_EVIDENCE,
                          "missing_evidence"].value_counts().items()},
        ),
        unmatched_reasons={
            DEST_PENDING: "宽表判待核：不在 r5 545 个有供给证据的键里（无 W1 阶段、无在途/PO）；"
                            "动作留空，不写补单",
        },
        untouched_columns=original_columns,
        added_columns=ACTION_COLUMNS,
    )
    return merged, stats


def _lineage(previous: str | None) -> dict:
    """记录上一版 actions 目录的 manifest 摘要（用于对照，不参与计算）。"""
    if not previous:
        return {}
    path = Path(previous) / "manifest.json"
    if not path.exists():
        return {"previous": str(previous), "manifest_found": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "previous": str(previous),
        "manifest_found": True,
        "generated_at": data.get("generated_at"),
        "wide_sha256": (data.get("inputs") or {}).get("wide", {}).get("sha256"),
        "pack_sha256": (data.get("inputs") or {}).get("pack", {}).get("sha256"),
        "matched": (data.get("join") or {}).get("matched"),
        "note": "上一版基于 F1 修复前的宽表；本版基于 r2（待核/不可算 demand/gap 为 null）",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="r5 动作层 → 宽口径决策包（只 join，不改数量）")
    parser.add_argument("--wide", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--previous", default=None,
                        help="上一版 actions 目录（仅记录 lineage，不读其数据）")
    parser.add_argument("--baseline-actions", default=None,
                        help="上一版（如 r2）actions parquet，用于标出 original/new 建议键")
    parser.add_argument("--versions-note", default=None,
                        help="自由文本：本版宽表对应的净额版本标签（如 h180 / r6）")
    args = parser.parse_args(argv)

    wide_path, pack_path, out_dir = Path(args.wide), Path(args.pack), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    wide = pd.read_parquet(wide_path)
    pack = pd.read_csv(pack_path, encoding="utf-8-sig")

    baseline = pd.read_parquet(args.baseline_actions) if args.baseline_actions else None
    merged, stats = join_actions(wide, pack, baseline=baseline)

    parquet_path = out_dir / "decision_pack_2026-10-29_actions.parquet"
    csv_path = out_dir / "decision_pack_2026-10-29_actions.csv"
    xlsx_path = out_dir / "decision_pack_2026-10-29_actions.xlsx"
    merged.to_parquet(parquet_path, index=False)
    merged.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name="决策包+动作", index=False)

    manifest = dict(
        schema_version="decision-pack-actions/v1",
        generated_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(timespec="seconds"),
        inputs={
            "wide": dict(path=str(wide_path), sha256=sha256_of(wide_path), rows=int(len(wide))),
            "pack": dict(path=str(pack_path), sha256=sha256_of(pack_path), rows=int(len(pack))),
        },
        outputs={
            "parquet": dict(path=str(parquet_path), sha256=sha256_of(parquet_path)),
            "csv": dict(path=str(csv_path), sha256=sha256_of(csv_path)),
            "xlsx": dict(path=str(xlsx_path), sha256=sha256_of(xlsx_path)),
        },
        join=dict(key=JOIN_KEY, how="left", validate="one_to_one", **stats),
        lineage=_lineage(args.previous),
        versions=dict(
            note=args.versions_note or "宽表为 h180 版（180 天视界）；动作层沿用 r5 键集",
            wide_sha256=sha256_of(wide_path),
            action_layer_sha256=sha256_of(pack_path),
            baseline_actions_sha256=(sha256_of(Path(args.baseline_actions))
                                     if args.baseline_actions else None),
            netting_run_id=sorted({str(v) for v in wide.get("netting_run_id", pd.Series(dtype=str))
                                   .dropna().unique()}) if "netting_run_id" in wide else [],
            horizon_end=sorted({str(v) for v in wide.get("netting_horizon_end", pd.Series(dtype=str))
                                .dropna().unique()}) if "netting_horizon_end" in wide else [],
        ),
        rules={
            "待核": "动作留空，action_applicability=no_supply_evidence，不写补单",
            "不可算": "action=不可算",
            "无需补货": "action=不需补（当前窗口）",
            "建议补货": "沿用动作层 action；若动作层判无缺口，action_basis 标口径冲突",
            "待核展示": "动作/数量留空而非 0；按 missing_evidence 分组披露缺什么，不参与合计",
            "数量与去向": "destination 与所有数量列原样保留，本步骤不重算",
        },
        note=("只做 join；不覆盖原 decision-pack-2026-10-29 目录；行级数据留本地。"
              "待核行的动作与数量一律留空（NaN），**不得按 0 处理**，也不写补单；"
              "missing_evidence 只对 destination_reason 分组，原 reason 列原样保留。"
              "本产物未冻结，终审 reject（F1–F7）后需对 r2 宽表重跑同一 join。"),
    )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: manifest["join"][k] for k in
                      ("rows_wide", "matched", "unmatched", "match_rate",
                       "applicability_counts", "action_counts",
                       "suggested_with_action", "suggested_total",
                       "destination_action_conflicts")}, ensure_ascii=False, indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
