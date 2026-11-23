# -*- coding: utf-8 -*-
"""把「待核」键变成可派工的补证队列。

**这是补证任务，不是补单。** 每行只说「这个键缺哪张证据、该谁去补、现状如何」，
量一律写「未知（不按 0）」，不产生任何补货数量，也不改决策包。

输入：`decision-pack-2026-10-29-h180-actions`（destination=待核）
字段来源：`to_verify` / `missing_evidence` / `destination_reason` / `value_status` /
`demand_evidence_status` / `gap_evidence_status`。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

GROUP_LABELS = {
    "not_qualified_no_stock_basis": "预测键未过资格且无库存基准",
    "not_qualified": "预测键未过资格",
    "stock_only_no_demand": "仅库存、缺需求证据",
    "no_forecast_no_stock": "无预测且无库存",
}
GROUP_EVIDENCE = {
    "not_qualified_no_stock_basis": ["需求资格", "库存基准"],
    "not_qualified": ["需求资格"],
    "stock_only_no_demand": ["需求证据"],
    "no_forecast_no_stock": ["需求证据", "库存基准"],
}
GROUP_ROLES = {
    "not_qualified_no_stock_basis": ("预测/运营", "仓库/主数据"),
    "not_qualified": ("预测/运营", ""),
    "stock_only_no_demand": ("运营", ""),
    "no_forecast_no_stock": ("运营", "仓库/主数据"),
}
# 待核行的供给证据为空，下面两类不适用（但要显式写出来，不能留白）
NOT_APPLICABLE = ["ETA", "用途去重"]


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def build_queue(pack_path: str | Path) -> tuple[pd.DataFrame, dict]:
    pack = pd.read_parquet(pack_path)
    pending = pack[pack["destination"] == "待核"].copy()

    rows = []
    for record in pending.itertuples(index=False):
        group = _text(getattr(record, "missing_evidence", "")) or "unclassified"
        label = GROUP_LABELS.get(group, group)
        evidence = GROUP_EVIDENCE.get(group, ["需求证据"])
        primary, supporting = GROUP_ROLES.get(group, ("待指派", ""))
        uom = _text(getattr(record, "canonical_uom", ""))
        uom_note = "" if uom else "单位缺失"
        rows.append({
            "SKU": getattr(record, "canonical_sku", ""),
            "仓库": getattr(record, "canonical_warehouse", ""),
            "单位": uom,
            "缺证分组": group,
            "缺证分组说明": label,
            "原始原因（destination_reason）": _text(getattr(record, "destination_reason", "")),
            "缺什么证据": "；".join(evidence),
            "不适用证据": "；".join(NOT_APPLICABLE) + "（待核行无供给证据）",
            "单位证据": uom_note or "已按单位分列",
            "证据现状": _text(getattr(record, "value_status", "")) or "not_covered",
            "需求证据状态": _text(getattr(record, "demand_evidence_status", "")) or "not_covered",
            "缺口证据状态": _text(getattr(record, "gap_evidence_status", "")) or "not_covered",
            "影响": "未知（不按 0）",
            "主责角色": primary,
            "协作角色": supporting,
            "待核说明（W1/宽表原文）": _text(getattr(record, "to_verify", "")),
            "状态": "待补证",
            "责任人（待填）": "",
            "补充证据/结论（待填）": "",
            "更新日期（待填）": "",
        })

    frame = pd.DataFrame(rows)
    summary = _summarise(frame, pending)
    return frame, summary


def _summarise(frame: pd.DataFrame, pending: pd.DataFrame) -> dict:
    def counts(column: str) -> dict:
        return {str(k): int(v) for k, v in frame[column].value_counts().items()}

    def role_counts(column: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for value in frame[column]:
            for role in str(value).split("/"):
                role = role.strip()
                if role:
                    out[role] = out.get(role, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    roles = role_counts("主责角色")
    supporting = role_counts("协作角色")

    return dict(
        pending_keys=int(len(frame)),
        by_group=counts("缺证分组"),
        by_group_label={GROUP_LABELS.get(k, k): v for k, v in counts("缺证分组").items()},
        by_role_primary=roles,
        by_role_supporting=supporting,
        by_role={k: roles.get(k, 0) + supporting.get(k, 0)
                 for k in set(roles) | set(supporting)},
        by_warehouse=dict(sorted(counts("仓库").items(), key=lambda kv: -kv[1])),
        by_uom=counts("单位"),
        evidence_types={k: int(v) for k, v in
                        frame["缺什么证据"].str.split("；").explode().value_counts().items()},
        impact="未知（不按 0）",
        note="补证队列，不是补单；所有数量留未知，不参与任何合计",
    )


def write_readme(path: Path, summary: dict, generated_at: str, source: str) -> None:
    lines = [
        "# 待核键补证队列",
        "",
        f"生成时间：{generated_at}",
        f"输入：`{source}`（destination=待核）",
        "",
        "## 这是什么",
        "",
        "**这是补证任务，不是补单。** 每行是一个「宽表判待核」的 SKU×仓×单位键，",
        "说明它缺哪张证据、该谁去补、现在的证据状态如何。**没有产生任何补货数量**，",
        "所有影响量写「未知（不按 0）」，不参与任何合计，也不改决策包。",
        "",
        "## 汇总",
        "",
        "| 缺证分组 | 说明 | 键数 | 主责 |",
        "|---|---|---:|---|",
    ]
    for slug, count in summary["by_group"].items():
        lines.append(f"| {slug} | {GROUP_LABELS.get(slug, slug)} | {count} | "
                     f"{GROUP_ROLES.get(slug, ('待指派', ''))[0]} |")
    lines += [
        "",
        f"合计 **{summary['pending_keys']}** 个键。",
        "",
        "### 按责任角色",
        "",
        "| 角色 | 主责键 | 协作键 |",
        "|---|---:|---:|",
    ]
    for role in summary["by_role"]:
        lines.append(f"| {role} | {summary['by_role_primary'].get(role, 0)} | "
                     f"{summary['by_role_supporting'].get(role, 0)} |")
    lines += ["", "### 按 UOM", "", "| 单位 | 键数 |", "|---|---:|"]
    for uom, count in summary["by_uom"].items():
        lines.append(f"| {uom or '（空）'} | {count} |")
    lines += [
        "",
        "### 按仓库（Top 15）",
        "",
        "| 仓库 | 键数 |",
        "|---|---:|",
    ]
    for warehouse, count in list(summary["by_warehouse"].items())[:15]:
        lines.append(f"| {warehouse} | {count} |")
    lines += [
        "",
        "## 怎么用",
        "",
        "1. 按 `主责角色` 分派：预测/运营补**需求资格/需求证据**，仓库/主数据补**库存基准**；",
        "2. 每行末尾有 `责任人（待填）`、`补充证据/结论（待填）`、`更新日期（待填）` 三栏；",
        "3. 补到证据后回填并把 `状态` 从「待补证」改为「已补证」；",
        "4. 补齐后回到决策包重算，**不要在队列里直接填数量**。",
        "",
        "## 证据类型说明",
        "",
        "- **需求资格**：该键的预测是否过资格（分类/可预测标记）；",
        "- **库存基准**：该仓该物料是否真的没有库存快照（不是 0，是缺观测）；",
        "- **需求证据**：是否有可用的需求观测（新品/停售/未上架都要写明）；",
        "- **ETA / 用途去重**：待核行没有任何供给证据，这两类暂不适用，已在行里显式标注；",
        "- **单位**：本批已按 UOM 分列；`单位` 为空的键需补单位证据。",
        "",
        "## 边界",
        "",
        "- 只读生成，不改 r6 / h180 决策包、不改任何数量、不写生产、不下单；",
        "- 影响量未知，**不得按 0 处理**；",
        "- 未 push。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="待核键补证队列（不改数量）")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    frame, summary = build_queue(args.pack)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_dir / "evidence_queue.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame([{"缺证分组": k, "说明": GROUP_LABELS.get(k, k), "键数": v,
                   "主责角色": GROUP_ROLES.get(k, ("待指派", ""))[0]}
                  for k, v in summary["by_group"].items()]).to_csv(
        out_dir / "summary_by_group.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"角色": k, "主责键": summary["by_role_primary"].get(k, 0),
                   "协作键": summary["by_role_supporting"].get(k, 0)}
                  for k in summary["by_role"]]).to_csv(
        out_dir / "summary_by_role.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"仓库": k, "键数": v} for k, v in summary["by_warehouse"].items()]).to_csv(
        out_dir / "summary_by_warehouse.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"单位": k, "键数": v} for k, v in summary["by_uom"].items()]).to_csv(
        out_dir / "summary_by_uom.csv", index=False, encoding="utf-8-sig")

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    (out_dir / "summary.json").write_text(
        json.dumps(dict(generated_at=generated_at, source=args.pack, **summary),
                   ensure_ascii=False, indent=1), encoding="utf-8")
    write_readme(out_dir / "README.md", summary, generated_at, args.pack)
    print(json.dumps({k: summary[k] for k in ("pending_keys", "by_group", "by_role", "by_uom")},
                     ensure_ascii=False, indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
