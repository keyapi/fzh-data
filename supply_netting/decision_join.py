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
                  "missing_evidence"]

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


def sha256_of(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def join_actions(wide: pd.DataFrame, pack: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """返回 (带动作的宽表, join 统计)。原列顺序与数量列不变。"""
    base = wide.copy()
    original_columns = list(base.columns)
    missing = [c for c in JOIN_KEY if c not in pack.columns]
    if missing:
        raise ValueError(f"动作层缺 join 键：{missing}")
    duplicates = int(pack.duplicated(JOIN_KEY).sum())
    if duplicates:
        raise ValueError(f"动作层 join 键重复 {duplicates} 行，拒绝带病 join")

    merged = base.merge(pack[JOIN_KEY + [c for c in ACTION_COLUMNS if c in pack.columns]],
                        on=JOIN_KEY, how="left", validate="one_to_one")
    if len(merged) != len(base):
        raise ValueError(f"join 后行数变化：{len(base)} → {len(merged)}")

    matched = merged["action"].notna() if "action" in merged.columns else pd.Series(False, index=merged.index)
    destination = merged["destination"].astype(str)

    for column in ACTION_COLUMNS:
        if column not in merged.columns:
            merged[column] = ""

    applicability, conflicts = [], 0
    for index, row in merged.iterrows():
        dest = str(row["destination"])
        if dest == DEST_PENDING:
            applicability.append(NO_EVIDENCE)
            merged.at[index, "missing_evidence"] = MISSING_EVIDENCE_GROUPS.get(
                str(row.get("destination_reason") or ""), "unclassified_no_supply_evidence")
            for column in ACTION_COLUMNS[:-1]:
                # 数值列清成 NaN，文本列清成空串（直接写 "" 会撞 float dtype）
                merged.at[index, column] = None if column in ("action_qty", "residual_gap") else ""
            continue
        applicability.append(HAS_EVIDENCE)
        merged.at[index, "missing_evidence"] = ""
        if dest == DEST_NOT_COMPUTABLE:
            merged.at[index, "action"] = ACTION_NOT_COMPUTABLE
            merged.at[index, "action_qty"] = None
            merged.at[index, "residual_gap"] = None
            continue
        if dest == DEST_NO_NEED:
            merged.at[index, "action"] = ACTION_NO_NEED
            merged.at[index, "action_qty"] = 0.0
            merged.at[index, "residual_gap"] = 0.0
            continue
        # 建议补货：保留动作层原值；若动作层给“不需补”则标注冲突
        if dest == DEST_REPLENISH and str(row.get("action")) == ACTION_NO_NEED:
            conflicts += 1
            basis = str(row.get("action_basis") or "")
            merged.at[index, "action_basis"] = f"{basis}；{CONFLICT_NOTE}" if basis else CONFLICT_NOTE
    merged["action_applicability"] = applicability

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
        destination_action_conflicts=int(conflicts),
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
    args = parser.parse_args(argv)

    wide_path, pack_path, out_dir = Path(args.wide), Path(args.pack), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    wide = pd.read_parquet(wide_path)
    pack = pd.read_csv(pack_path, encoding="utf-8-sig")

    merged, stats = join_actions(wide, pack)

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
