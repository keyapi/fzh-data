# -*- coding: utf-8 -*-
"""业务审核工作簿（SC09/M1）：把 r2-actions 决策包转成可人工审核的 xlsx。

硬约束：
- **不重算任何数字**，所有数值直接取自 ``decision_pack_2026-10-29_actions.parquet``；
- 不新增报告层级；待核行只做分组披露，**不得按 0 处理**、不参与合计；
- 数值写原始精度，只靠 ``number_format`` 控制显示（4 位小数），
  避免 0.000538 这类正小量显示成 0。

用法::

    uv run python -m supply_netting.business_review \\
        --actions "…/decision-pack-2026-10-29-actions-r2/decision_pack_2026-10-29_actions.parquet" \\
        --out "D:/Work/fzh-order-store/en-demand-v1/supply-netting/business-review-2026-10-29-v2.xlsx"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

GROUP_LABELS = {
    "not_qualified_no_stock_basis": ("预测键未过资格且无库存基准",
                                     "运营/主数据：补预测键资格 + 补库存基准", "运营"),
    "not_qualified": ("预测键未过资格", "运营：补齐预测键资格（分类/可预测标记）", "运营"),
    "stock_only_no_demand": ("仅库存、缺需求证据", "运营/销售：补需求证据，或确认停售/清仓", "运营"),
    "no_forecast_no_stock": ("无预测且无库存", "运营：确认为新品/未上架/停售，给结论或归档", "运营"),
}
HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
QTY_FORMAT = "0.0000"      # 4 位小数：0.000538 不会被显示成 0
INT_FORMAT = "#,##0"
INTERNAL_TOKENS = ("qty_low_counterfactual", "value_status", "key_source", "gap_evidence_status",
                   "demand_evidence_status")

LABEL_GAP = "视界末缺口（逐键向上取整）"
LABEL_HIGHER = "flat95 参考缓冲情景"


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _num(value):
    """原值转 float（不四舍五入）；缺失返回 None，绝不当 0。"""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _sum_or_none(series):
    values = pd.to_numeric(series, errors="coerce")
    return None if values.notna().sum() == 0 else float(values.sum())


def _clean_verify(text: str) -> str:
    segments = [seg.strip() for seg in str(text or "").split("；") if seg.strip()]
    kept = [seg for seg in segments if not any(token in seg for token in INTERNAL_TOKENS)]
    return "；".join(kept)


def _stage_evidence(row) -> str:
    parts = []
    for label, column in (("完工待发运", "so_stage_produced_pending_dn"),
                          ("在产", "so_stage_in_production"),
                          ("缺开工证据", "so_stage_unknown_missing_start"),
                          ("在途", "so_stage_in_transit"),
                          ("未排产", "so_stage_not_planned"),
                          ("阶段待核实", "so_stage_unknown_other")):
        value = _num(row.get(column))
        if value:
            parts.append(f"{label} {value:g}")
    fba = sum(_num(row.get(c)) or 0 for c in ("so_stage_fba_produced_pending_dn",
                                              "so_stage_fba_in_production",
                                              "so_stage_fba_in_transit",
                                              "so_stage_fba_not_planned"))
    if fba:
        parts.append(f"FBA 单列 {fba:g}（不计本仓）")
    return "；".join(parts) if parts else "无 W1 阶段证据"


def _conditional_qualification(row) -> str:
    parts = ["有预计到仓日" if _text(row.get("so_est_branch_date")) else "无逐行 ETA"]
    if str(row.get("timely_coverage_flag") or "") == "timely_coverage_unproven":
        parts.append("时效未证")
    if str(row.get("transit_dedup_status") or "") == "dedup_unproven":
        parts.append("与通途在途/PO 可能重复")
    return "；".join(parts)


def _text(value) -> str:
    """NaN/None → 空串（pandas 读进来的空值常是 float nan）。"""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _source_locator(row) -> str:
    parts = []
    so = _text(row.get("action_source_so"))
    wo = _text(row.get("action_source_wo"))
    if so:
        parts.append(so)
    if wo:
        parts.append("WO: " + wo)
    return " / ".join(parts) if parts else "无 W1 源记录"


def _to_confirm(row) -> str:
    parts = []
    verify = _clean_verify(row.get("to_verify"))
    if verify:
        parts.append(verify)
    if str(row.get("timely_coverage_flag") or "") == "timely_coverage_unproven":
        parts.append("时效未证：无需要日/ETA，动作量只能算可能覆盖")
    residual = _num(row.get("residual_gap"))
    if residual:
        parts.append(f"剩余 {residual:g} 无供给覆盖，需补单或改期")
    if str(row.get("transit_dedup_status") or "") == "dedup_unproven":
        parts.append("在途与通途 PO 可能重复，未证")
    return "；".join(parts)


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, cwd=Path(__file__).resolve().parents[1])
        return out.stdout.strip() or "unknown"
    except Exception:                                          # noqa: BLE001
        return "unknown"


def build_workbook(actions_path: str | Path, out_path: str | Path,
                   manifest_path: str | Path | None = None,
                   acceptance_status: str = "返修后待 Codex 复核") -> dict:
    actions_path, out_path = Path(actions_path), Path(out_path)
    frame = pd.read_parquet(actions_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    suggested = frame[frame["destination"] == "建议补货"].copy()
    no_need = frame[frame["destination"] == "无需补货"].copy()
    pending = frame[frame["destination"] == "待核"].copy()
    not_computable = frame[frame["destination"] == "不可算"].copy()

    summary_rows = []
    for group, subset in pending.groupby("missing_evidence"):
        label, owner, role = GROUP_LABELS.get(group, (group, "待指派", "待定"))
        summary_rows.append({
            "缺证分组": group, "说明": label, "缺什么": label,
            "建议责任角色": owner, "角色": role, "影响键数": int(len(subset)),
            "涉及库存数": _sum_or_none(subset["opening"]),
            "涉及预测需求（待核为空，不按0）": _sum_or_none(subset["horizon_demand"]),
        })
    missing_summary = pd.DataFrame(summary_rows).sort_values("影响键数", ascending=False)

    # 以下全部是源数据直取/直求和，不做任何业务重算
    suggested_gap_total = _sum_or_none(suggested["qty_current"])
    higher_total = _sum_or_none(suggested["qty_higher"])
    action_total = _sum_or_none(suggested["action_qty"])
    residual_total = _sum_or_none(suggested["residual_gap"])
    no_need_demand_total = _sum_or_none(no_need["horizon_demand"])
    no_need_gap_total = _sum_or_none(no_need["qty_current"])
    no_need_opening_total = _sum_or_none(no_need["opening"])
    as_of = str(frame["netting_as_of"].iloc[0])
    horizon_end = str(frame["netting_horizon_end"].iloc[0])
    forecast_window = str(frame["forecast_window"].iloc[0])
    data_cutoff = str(frame["data_cutoff"].iloc[0])
    blind_days = round((pd.Timestamp("2026-10-29T00:00:00+08:00")
                        - pd.Timestamp(as_of)).total_seconds() / 86400, 3)

    explain = pd.DataFrame([
        ("工作簿用途", "10-29 条件补货建议的人工审核工作簿（SC09/M1）；只展示事实与动作，不是采购单，不授权下单。"),
        ("数据基准（库存快照）", f"{data_cutoff}（净额 as_of {as_of}）"),
        ("决策包生成日", "2026-10-29"),
        ("盲区", f"{blind_days} 天（{as_of} → 2026-10-29 00:00）内没有新的库存/供给证据，"
                 "此期间的出入库与到货不在本包内。"),
        ("净额视界", f"{as_of} → {horizon_end}（缺口按视界末 qty_current 计）"),
        ("预测窗口", forecast_window),
        ("供给口径", "期初库存计入可用；在途 / 通途 PO 无逐行 ETA，只作条件量，不计入可用。"),
        ("未履约 SO", "未履约 SO 未接入本净额；工厂 SO 管线在另一份包中单列，"
                     "本表缺口不含未履约 SO 的到货承诺。"),
        ("待核行", f"{len(pending):,} 行：动作与数量留空，**不得按 0 处理**，不参与任何合计；"
                  "按缺证分组在第 4 个 sheet 披露。"),
        (LABEL_GAP + " 合计", f"{suggested_gap_total:g} 件：**视界末缺口逐键向上取整合计（不含服务缓冲）**。"),
        (LABEL_HIGHER, f"{higher_total:g} 件：按 flat95 服务档的缓冲参考，"
                       "**不是 95% 承诺**，也不是采购量。"),
        ("数量口径", "动作缺口 = 视界末 qty_current（缺失退回 gap_today）；7 天保护期 protect_gap 仅作附注；"
                  "表内数值保留源精度，显示 4 位小数。"),
        ("本工作簿", "所有数字取自 decision-pack-2026-10-29-actions-r2，未重算、未合并、未补 0。"),
    ], columns=["项目", "说明与边界"])

    sheet_suggested = pd.DataFrame([{
        "SKU": r.get("canonical_sku"),
        "仓库": r.get("canonical_warehouse"),
        "单位": r.get("canonical_uom"),
        "期初": _num(r.get("opening")),
        "未来需求": _num(r.get("horizon_demand")),
        LABEL_GAP: _num(r.get("qty_current")),
        LABEL_HIGHER: _num(r.get("qty_higher")),
        "条件供应量": _num(r.get("conditional_supply_qty")) or _num(r.get("conditional_supply")),
        "条件供应资格": _conditional_qualification(r),
        "最近日期": _text(r.get("so_est_branch_date")) or _text(r.get("first_gap_bucket_end")),
        "建议动作": r.get("action"),
        "动作数量": _num(r.get("action_qty")),
        "剩余需补": _num(r.get("residual_gap")),
        "动作置信度": r.get("action_confidence"),
        "阶段证据": _stage_evidence(r),
        "源记录定位": _source_locator(r),
        "需确认项": _to_confirm(r),
    } for _, r in suggested.sort_values("qty_current", ascending=False).iterrows()])

    no_need_summary = pd.DataFrame([
        ("行数", int(len(no_need))),
        ("视界末需求合计", no_need_demand_total),
        ("当前缺口合计", no_need_gap_total),
        ("期初合计", no_need_opening_total),
        ("去向原因", "；".join(f"{k} {v}" for k, v in no_need["destination_reason"].value_counts().items())),
        ("说明", "这些键在本视界内期初已覆盖已知需求；不代表未来不需要补。"
                "「视界末需求合计」按 horizon_demand 求和，不是缺口（缺口恒为 0）。"),
    ], columns=["项", "值"])

    no_need_list = pd.DataFrame([{
        "SKU": r.get("canonical_sku"), "仓库": r.get("canonical_warehouse"),
        "单位": r.get("canonical_uom"), "期初": _num(r.get("opening")),
        "视界需求": _num(r.get("horizon_demand")), "当前缺口": _num(r.get("qty_current")),
        "去向原因": r.get("destination_reason"),
    } for _, r in no_need.sort_values("horizon_demand", ascending=False).iterrows()])

    pending_detail = pd.DataFrame([{
        "缺证分组": f"{GROUP_LABELS.get(r.get('missing_evidence'), (r.get('missing_evidence'),))[0]}"
                   f"（{r.get('missing_evidence')}）",
        "SKU": r.get("canonical_sku"), "仓库": r.get("canonical_warehouse"),
        "单位": r.get("canonical_uom"), "期初": _num(r.get("opening")),
        "预测需求": _num(r.get("horizon_demand")),
        "缺什么（原始原因）": r.get("destination_reason"),
        "责任人（待填）": "", "补充证据/结论（待填）": "", "更新日期（待填）": "",
    } for _, r in pending.sort_values(["missing_evidence", "canonical_sku"]).iterrows()])

    not_computable_rows = pd.DataFrame([{
        "SKU": r.get("canonical_sku"), "仓库": r.get("canonical_warehouse"),
        "单位": r.get("canonical_uom"), "去向": r.get("destination"),
        "原因": r.get("destination_reason"), "说明": _clean_verify(r.get("to_verify")),
    } for _, r in not_computable.iterrows()])

    version = pd.DataFrame([
        ("工作簿", out_path.name),
        ("本版改动", "v2 返修：B3 合计改按 horizon_demand；数值保留源精度（4 位显示）；"
                    "495/777 标签改为口径说明；建议页补期初/需求/条件供应/资格/置信度/源记录；"
                    "本页补 commit、测试与验收状态。"),
        ("输入", str(actions_path)),
        ("输入 sha256", _sha256(actions_path)),
        ("生成 commit", _git_commit()),
        ("行数", int(len(frame))),
        ("去向分布", "；".join(f"{k} {v}" for k, v in frame["destination"].value_counts().items())),
        ("动作分布", "；".join(f"{k} {v}" for k, v in
                              frame.loc[frame["action_applicability"] == "evidence", "action"]
                              .value_counts().items())),
        ("测试", "uv run pytest supply_netting/tests -q（含 test_business_review.py）"),
        ("审核记录", "Codex 复审 2026-10-27 reject：B3 合计为 0、E 列精度丢失、495/777 标签含糊、"
                    "建议页缺证据列、版本页缺 commit/验收；本版逐条返修。"),
        ("验收状态", acceptance_status),
        ("下一动作", "交 Codex 复核；通过后替换 business-review-2026-10-29.xlsx 并同步 handoff。"),
        ("生成器", "supply_netting.business_review"),
        ("口径", "不重算、不合并、不补 0；待核不参与合计；数值保留源精度"),
        ("说明", "输出 sha256 见同名 manifest.json（写盘后计算）"),
    ], columns=["项", "值"])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        explain.to_excel(writer, sheet_name="1_说明与边界", index=False)
        sheet_suggested.to_excel(writer, sheet_name="2_建议补货91", index=False)
        no_need_summary.to_excel(writer, sheet_name="3_无需补货452", index=False)
        no_need_list.to_excel(writer, sheet_name="3_无需补货452", index=False,
                              startrow=len(no_need_summary) + 2)
        missing_summary.to_excel(writer, sheet_name="4_待核3469", index=False)
        pending_detail.to_excel(writer, sheet_name="4_待核3469", index=False,
                                startrow=len(missing_summary) + 2)
        not_computable_rows.to_excel(writer, sheet_name="5_不可算2", index=False)
        version.to_excel(writer, sheet_name="6_版本与hash", index=False)

        _style(writer, "1_说明与边界", [28, 116], freeze="A2")
        _style(writer, "2_建议补货91",
               [34, 24, 6, 10, 11, 14, 14, 11, 22, 20, 14, 10, 10, 12, 46, 30, 56],
               freeze="A2", qty_columns=(4, 5, 6, 7, 8, 12, 13), summary_rows=range(2, 92))
        _style(writer, "3_无需补货452", [26, 34, 6, 12, 12, 12, 30], freeze=None,
               detail_header_row=len(no_need_summary) + 3, qty_columns=(2,),
               summary_rows=range(2, len(no_need_summary) + 1),
               detail_qty_columns=(4, 5, 6), detail_start=len(no_need_summary) + 4)
        _style(writer, "4_待核3469", [34, 34, 40, 10, 12, 12, 40, 14, 40, 14], freeze="A2",
               detail_header_row=len(missing_summary) + 3, qty_columns=(7, 8),
               detail_qty_columns=(5, 6), detail_start=len(missing_summary) + 4)
        _style(writer, "5_不可算2", [34, 24, 6, 10, 24, 60], freeze="A2")
        _style(writer, "6_版本与hash", [20, 130], freeze="A2")

    manifest = dict(
        workbook=str(out_path),
        workbook_sha256=_sha256(out_path),
        generated_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(timespec="seconds"),
        git_commit=_git_commit(),
        input=dict(path=str(actions_path), sha256=_sha256(actions_path), rows=int(len(frame))),
        sheets=["1_说明与边界", "2_建议补货91", "3_无需补货452", "4_待核3469", "5_不可算2", "6_版本与hash"],
        counts=dict(suggested=len(suggested), no_need=len(no_need), pending=len(pending),
                    not_computable=len(not_computable),
                    pending_by_group=pending["missing_evidence"].value_counts().to_dict()),
        quantities=dict(
            suggested_gap_total=suggested_gap_total,
            higher_flat95_total=higher_total,
            action_qty_total=action_total,
            residual_total=residual_total,
            no_need_horizon_demand_total=no_need_demand_total,
            no_need_gap_total=no_need_gap_total,
            no_need_opening_total=no_need_opening_total,
        ),
        labels={LABEL_GAP: "qty_current 合计；逐键向上取整；不含服务缓冲",
                LABEL_HIGHER: "flat95 服务档缓冲参考；不是 95% 承诺"},
        blind_window_days=blind_days,
        precision=dict(policy="写原始 float，仅用 number_format 显示", qty_format=QTY_FORMAT),
        acceptance_status=acceptance_status,
        review_history=["Codex 复审 2026-10-27：reject（B3 合计、E 列精度、495/777 标签、R6/R7 缺列）",
                        "本版逐条返修，待复核"],
        rules=["数字全部取自输入，未重算", "待核留空、不按 0、不参与合计",
               "在途/PO 无 ETA 不计可用", "495–777 为情景区间，不是 95% 承诺"],
        note="业务审核用；不是采购单，不授权下单",
    )
    manifest_path = Path(manifest_path) if manifest_path else out_path.with_name(
        out_path.stem + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def _apply_number_format(sheet, columns, rows=None) -> None:
    for column in columns:
        for row in (rows or range(2, sheet.max_row + 1)):
            cell = sheet.cell(row=row, column=column)
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                value = float(cell.value)
                cell.number_format = INT_FORMAT if value.is_integer() and abs(value) >= 1 \
                    else QTY_FORMAT


def _style(writer, sheet_name: str, widths, freeze: str | None, qty_columns=(),
           detail_header_row: int | None = None, summary_rows=None,
           detail_qty_columns=(), detail_start: int | None = None) -> None:
    sheet = writer.sheets[sheet_name]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    if freeze:
        sheet.freeze_panes = freeze
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    if detail_header_row:
        for cell in sheet[detail_header_row]:
            if cell.value is not None:
                cell.font = Font(bold=True)
                cell.fill = HEADER_FILL
                cell.alignment = Alignment(wrap_text=True, vertical="center")
    if qty_columns:
        _apply_number_format(sheet, qty_columns, summary_rows)
    if detail_qty_columns and detail_start:
        _apply_number_format(sheet, detail_qty_columns,
                             range(detail_start, sheet.max_row + 1))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="业务审核工作簿（不重算数字）")
    parser.add_argument("--actions", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--acceptance-status", default="返修后待 Codex 复核")
    args = parser.parse_args(argv)
    manifest = build_workbook(args.actions, args.out, args.manifest,
                              acceptance_status=args.acceptance_status)
    print(json.dumps({k: manifest[k] for k in ("workbook", "counts", "quantities",
                                               "blind_window_days", "workbook_sha256",
                                               "git_commit")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
