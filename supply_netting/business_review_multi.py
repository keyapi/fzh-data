# -*- coding: utf-8 -*-
"""多窗口业务审核工作簿 v3（90 主 / 150 春节压力 / 180 仅情景）。

不重算任何数字：窗口量取自 ``horizon_windows.csv`` / ``horizon_windows_keys.csv``，
动作取自 ``decision-pack-2026-10-29-h180-actions``；SO 审计摘要取自
``so-open-audit-2026-10-27``。窗口均为从 as_of 起的累计，**彼此不可相加**。
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

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
QTY_FORMAT = "0.000000"      # 源精度：6 位小数，正小量不显示成 0
INT_FORMAT = "#,##0"
WINDOW_LABELS = {30: "30 天参考", 60: "60 天参考", 90: "90 天主窗口",
                 120: "120 天（未展示明细）", 150: "150 天春节压力", 180: "180 天情景（仅情景，非采购量）"}


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, cwd=Path(__file__).resolve().parents[1])
        return out.stdout.strip() or "unknown"
    except Exception:                                    # noqa: BLE001
        return "unknown"


def _num(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _sum_or_none(series):
    values = pd.to_numeric(series, errors="coerce")
    return None if values.notna().sum() == 0 else float(values.sum())


def load_inputs(windows_csv: Path, keys_csv: Path, actions_parquet: Path,
                so_audit_csv: Path) -> dict:
    return dict(
        windows=pd.read_csv(windows_csv),
        keys=pd.read_csv(keys_csv),
        actions=pd.read_parquet(actions_parquet),
        so_audit=pd.read_csv(so_audit_csv),
    )


def _window_summary(windows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in windows.itertuples(index=False):
        rows.append({
            "窗口(天)": int(row.window_days),
            "说明": WINDOW_LABELS.get(int(row.window_days), ""),
            "实际天数": row.actual_days,
            "覆盖到": row.bucket_end,
            "预测需求": _num(row.forecast_demand),
            "累计未满足": _num(row.cum_unserved),
            "有缺口键数": int(row.gap_keys),
            "建议键数": int(row.suggestion_keys),
            "建议量（逐键向上取整）": _num(row.qty_current),
            "其中参考缓冲": _num(row.qty_higher),
            "用途": row.usage,
            "注意": "累计窗口，窗口之间不可相加",
        })
    return pd.DataFrame(rows)


def _window_keys(keys: pd.DataFrame, window: int, actions: pd.DataFrame | None,
                 extra_columns=False) -> pd.DataFrame:
    subset = keys[(keys["window_days"] == window)
                  & (pd.to_numeric(keys["qty_current"], errors="coerce") > 0)].copy()
    if actions is not None and len(actions):
        action_cols = KEY + ["action", "action_confidence", "action_qty", "residual_gap",
                             "action_source_so", "action_source_wo", "action_gap",
                             "baseline_group"]
        available = [c for c in action_cols if c in actions.columns]
        subset = subset.merge(actions[available], on=KEY, how="left", suffixes=("", "_act"))
        subset["action"] = subset["action"].fillna("")
        subset["action_basis_note"] = ("动作按 180 天缺口选出（h180 动作层），"
                                       "本窗口建议量见「建议量」列")
    rows = []
    for record in subset.sort_values("qty_current", ascending=False).itertuples(index=False):
        row = {
            "SKU": record.canonical_sku,
            "仓库": record.canonical_warehouse,
            "单位": record.canonical_uom,
            "窗口需求": _num(record.forecast_demand),
            "窗口未满足": _num(record.cum_unserved),
            "建议量（逐键向上取整）": _num(record.qty_current),
            "参考缓冲（+14 天）": _num(record.qty_higher),
        }
        if "action" in subset.columns:
            row.update({
                "动作": record.action,
                "动作置信度": getattr(record, "action_confidence", ""),
                "动作量": _num(getattr(record, "action_qty", None)),
                "剩余需补": _num(getattr(record, "residual_gap", None)),
                "来源SO": _text(getattr(record, "action_source_so", "")),
                "来源WO": _text(getattr(record, "action_source_wo", "")),
                "对照分组": _text(getattr(record, "baseline_group", "")),
            })
        rows.append(row)
    return pd.DataFrame(rows)


def _window_diff(keys: pd.DataFrame, base: int, other: int,
                 actions: pd.DataFrame) -> pd.DataFrame:
    """两个窗口的逐键差（差值不是可用量，只说明压力扩大了多少）。"""
    left = keys[keys["window_days"] == base].set_index(KEY)
    right = keys[keys["window_days"] == other].set_index(KEY)
    joined = left[["forecast_demand", "cum_unserved", "qty_current", "qty_higher"]].join(
        right[["forecast_demand", "cum_unserved", "qty_current", "qty_higher"]],
        how="outer", lsuffix="_base", rsuffix="_other")
    joined = joined.fillna(0.0).reset_index()
    joined["需求差"] = joined["forecast_demand_other"] - joined["forecast_demand_base"]
    joined["未满足差"] = joined["cum_unserved_other"] - joined["cum_unserved_base"]
    joined["建议量差"] = joined["qty_current_other"] - joined["qty_current_base"]
    mask = (joined["qty_current_other"] > 0) | (joined["qty_current_base"] > 0)
    joined = joined[mask]
    if len(actions):
        joined = joined.merge(actions[KEY + ["action"]], on=KEY, how="left")
    rows = [{
        "SKU": r.canonical_sku, "仓库": r.canonical_warehouse, "单位": r.canonical_uom,
        f"{base}天建议量": _num(r.qty_current_base),
        f"{other}天建议量": _num(r.qty_current_other),
        "建议量差（150−90）": _num(r.qty_current_other) - _num(r.qty_current_base),
        "需求差": _num(r.forecast_demand_other) - _num(r.forecast_demand_base),
        "未满足差": _num(r.cum_unserved_other) - _num(r.cum_unserved_base),
        "动作": _text(getattr(r, "action", "")),
    } for r in joined.itertuples(index=False)]
    frame = pd.DataFrame(rows)
    return frame.sort_values("建议量差（150−90）", ascending=False) if len(frame) else frame


def _festival_block(so_audit: pd.DataFrame, so_rows: pd.DataFrame | None) -> pd.DataFrame:
    """春节缓冲涉及的 SO：全部穿越 / 计入管线穿越 / 日期可否判定。"""
    rows = [("口径", "生产+发运路径与春节锚点 2027-02-06 ±30 天窗口相交即加 60 天；只作解释与催办，不改净额")]
    if so_rows is not None and len(so_rows):
        applicable = so_rows[so_rows["spring_festival_applicability"] == "applicable"]
        counted = applicable[applicable["excluded_reason"].isna()]
        rows.append(("全部开放行穿越", f"{applicable['so'].nunique()} 单 / "
                                  f"{applicable['quantity'].sum():.0f} 件"))
        rows.append(("计入管线穿越", f"{counted['so'].nunique()} 单 / "
                                f"{counted['quantity'].sum():.0f} 件"))
        per_so = counted.groupby("so")["quantity"].sum().reset_index()
        if len(so_audit):
            joined = per_so.merge(so_audit[["SO", "日期置信度", "预计到仓"]],
                                  left_on="so", right_on="SO", how="left")
            known = joined[joined["日期置信度"] == "estimated"]
            unknown = joined[joined["日期置信度"] != "estimated"]
            rows.append(("其中日期可判（estimated）",
                         f"{len(known)} 单 / {known['quantity'].sum():.0f} 件"))
            rows.append(("其中日期不可判（unknown）",
                         f"{len(unknown)} 单 / {unknown['quantity'].sum():.0f} 件"))
    rows.append(("任务简报口径（待核）",
                 "简报写「有效 6 单 / 1,477 件、2 单 unknown」，现有产物（horizon-windows、"
                 "pack-2026-10-29-h180/so_backlog_summary、so-open-audit）复现不出该拆分；"
                 "本表按上述可复算口径展示，未采用未溯源的数字"))
    return pd.DataFrame(rows, columns=["项", "值"])


def _so_audit_summary(audit: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not len(audit):
        return pd.DataFrame(columns=["项", "值"]), pd.DataFrame()
    verdict = audit["处置建议"].value_counts()
    anomalies = {}
    for text in audit["异常"]:
        for item in str(text).split("；"):
            item = item.strip()
            if not item or item == "无":
                continue
            key = ("阶段与SO总量不守恒" if item.startswith("阶段与SO总量不守恒")
                   else "逾期（明细见行）" if item.startswith("逾期")
                   else "阶段证据陈旧>7天" if item.startswith("阶段证据陈旧")
                   else item)
            anomalies[key] = anomalies.get(key, 0) + 1
    rows = [
        ("审计单数", int(len(audit))),
        ("开放量", _sum_or_none(audit["开放量"])),
        ("可作条件供给", f"{int(verdict.get('可作条件供给', 0))} 单 / "
                   f"{audit.loc[audit['处置建议'] == '可作条件供给', '开放量'].sum():.0f} 件"),
        ("需催（在产/未排产）", f"{int(verdict.get('需催（在产/未排产）', 0))} 单 / "
                        f"{audit.loc[audit['处置建议'] == '需催（在产/未排产）', '开放量'].sum():.0f} 件"),
        ("无法判断", f"{int(verdict.get('无法判断（无阶段证据）', 0))} 单 / "
                 f"{audit.loc[audit['处置建议'] == '无法判断（无阶段证据）', '开放量'].sum():.0f} 件"),
    ]
    for label, count in sorted(anomalies.items(), key=lambda kv: -kv[1]):
        rows.append((f"异常：{label}", count))
    summary = pd.DataFrame(rows, columns=["项", "值"])
    detail = audit[["SO", "客户", "分公司仓", "开放量", "在途", "完工待发运", "在产", "未排产",
                    "unknown", "累计超产", "逾期天数", "预计到仓", "日期置信度",
                    "异常", "处置建议"]].sort_values("开放量", ascending=False)
    return summary, detail


def build_workbook_v3(*, windows_csv, keys_csv, actions_parquet, so_audit_csv,
                      so_rows_csv, out_path, baseline_actions=None,
                      acceptance_status="v3 待复核") -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_inputs(Path(windows_csv), Path(keys_csv), Path(actions_parquet),
                       Path(so_audit_csv))
    windows, keys, actions, audit = data["windows"], data["keys"], data["actions"], data["so_audit"]
    so_rows = pd.read_csv(so_rows_csv, encoding="utf-8-sig") if so_rows_csv else None

    summary = _window_summary(windows)
    main90 = _window_keys(keys, 90, actions, extra_columns=True)
    pressure150 = _window_diff(keys, 90, 150, actions)
    scenario180 = _window_keys(keys, 180, actions)
    ref3060 = _window_summary(windows[windows["window_days"].isin([30, 60])])
    festival = _festival_block(audit, so_rows)
    so_summary, so_detail = _so_audit_summary(audit)

    h180 = actions[actions["destination"] == "建议补货"]
    action_dist = h180["action"].value_counts().to_dict()
    pending = actions[actions["destination"] == "待核"]
    no_need = actions[actions["destination"] == "无需补货"]
    not_computable = actions[actions["destination"] == "不可算"]

    boundaries = pd.DataFrame([
        ("工作簿用途", "10-29 补货建议多窗口审核（v3）；不是采购单，不授权下单"),
        ("窗口关系", "90 天主窗口 / 150 天春节压力 / 180 天仅情景；**都是从 as_of 起的累计，窗口之间不可相加**"),
        ("90 天主窗口", "review_candidate：可作人工审核的补货候选"),
        ("150 天春节压力", "review_candidate：额外覆盖春节停工+恢复；与 90 天的差值只说明压力扩大，不是增量采购"),
        ("180 天情景", "**scenario_only**：只作产能/春节排期情景，**不是采购量**（6 个月，越远越不准）"),
        ("30/60 天", "参考窗口：用于短期催单与观察，不单独构成采购建议"),
        ("库存基准", f"{actions['data_cutoff'].iloc[0] if 'data_cutoff' in actions else ''}"
                 f"（净额 as_of {actions['netting_as_of'].iloc[0] if 'netting_as_of' in actions else ''}）"),
        ("已证到货", "0：在途/通途 PO 无逐行 ETA，只作条件量，不计入可用"),
        ("待核", f"{len(pending):,} 键无供给证据，动作留空、不按 0、不参与合计"),
        ("SO 管线", "97 张开放 SO 逐单审计；42 单阶段与 SO 总量不守恒，接入净额前需逐单核；"
                  "不守恒与逾期详见第 7 个 sheet"),
        ("春节缓冲", "生产+发运路径与 2027-02-06 窗口相交才加 60 天；只作解释与催办，不改净额"),
        ("数字来源", "窗口量取 horizon_windows_2026-10-29；动作取 h180 动作层；SO 摘要取 so-open-audit；"
                  "全部直取，未重算、未相加"),
    ], columns=["项目", "说明与边界"])

    sections = pd.DataFrame([
        ("待核", f"{len(pending):,} 键", "无供给证据；动作与数量留空"),
        ("不可算", f"{len(not_computable)} 键", "净额无法计算（no_snapshot_basis），不给动作"),
        ("无需补货（180 天口径）", f"{len(no_need)} 键", "期初已覆盖视界内需求"),
        ("对比：30 天口径的无需补货", "452 键", "来自 r2 包（30 天窗口）；不同窗口不能混用"),
        ("180 天动作分布", " / ".join(f"{k} {v}" for k, v in action_dist.items()),
         "动作按 180 天缺口选出；不代表采购量"),
        ("180 天缺口/建议量", f"{_num(summary.loc[summary['窗口(天)'] == 180, '建议量（逐键向上取整）'].iloc[0]):g}",
         "逐键向上取整后求和；窗口不可相加"),
    ], columns=["类别", "数量", "说明"])

    version_rows = [
        ("工作簿", out_path.name),
        ("生成 commit", _git_commit()),
        ("生成时间", pd.Timestamp.now(tz="Asia/Shanghai").isoformat(timespec="seconds")),
        ("窗口输入", str(windows_csv)),
        ("窗口输入 sha256", _sha256(windows_csv)),
        ("键表输入", str(keys_csv)),
        ("键表 sha256", _sha256(keys_csv)),
        ("动作层", str(actions_parquet)),
        ("动作层 sha256", _sha256(actions_parquet)),
        ("SO 审计", str(so_audit_csv)),
        ("SO 审计 sha256", _sha256(so_audit_csv)),
    ]
    if baseline_actions:
        version_rows += [("旧 91 键对照", str(baseline_actions)),
                         ("旧 91 键 sha256", _sha256(baseline_actions))]
    version_rows += [
        ("窗口用途", "90 主 / 150 春节压力 / 180 仅情景；30/60 参考；窗口不可相加"),
        ("验收状态", acceptance_status),
        ("下一动作", "交复核；按窗口分别审，不合并成一张采购单"),
    ]
    version = pd.DataFrame(version_rows, columns=["项", "值"])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        boundaries.to_excel(writer, sheet_name="1_说明与边界", index=False)
        main90.to_excel(writer, sheet_name="2_90天主表", index=False)
        festival.to_excel(writer, sheet_name="3_150天春节压力", index=False)
        pressure150.to_excel(writer, sheet_name="3_150天春节压力", index=False,
                             startrow=len(festival) + 2)
        scenario180.to_excel(writer, sheet_name="4_180天情景", index=False)
        ref3060.to_excel(writer, sheet_name="5_30-60天参考", index=False)
        sections.to_excel(writer, sheet_name="6_180天其他去向", index=False)
        so_summary.to_excel(writer, sheet_name="7_SO审计摘要", index=False)
        so_detail.head(60).to_excel(writer, sheet_name="7_SO审计摘要", index=False,
                                    startrow=len(so_summary) + 2)
        version.to_excel(writer, sheet_name="8_版本与证据", index=False)

        _style(writer, "1_说明与边界", [24, 120], freeze="A2")
        _style(writer, "2_90天主表", [34, 24, 6, 12, 12, 16, 14, 12, 12, 12, 10, 28, 22, 10],
               freeze="A2", qty_columns=(4, 5, 6, 7, 9, 10))
        _style(writer, "3_150天春节压力", [24, 120], freeze="A2")
        _style(writer, "3_150天春节压力", [34, 24, 6, 12, 12, 16, 12, 12, 14, 10], freeze=None,
               detail_header_row=len(festival) + 3, detail_qty_columns=(4, 5, 6, 7, 8),
               detail_start=len(festival) + 4)
        _style(writer, "4_180天情景", [34, 24, 6, 12, 12, 16, 14, 12, 12, 12, 10, 28, 22, 10],
               freeze="A2", qty_columns=(4, 5, 6, 7, 9, 10))
        _style(writer, "5_30-60天参考", [12, 20, 12, 30, 14, 14, 10, 10, 16, 14, 14, 30],
               freeze="A2", qty_columns=(3, 5, 6, 9, 10))
        _style(writer, "6_180天其他去向", [26, 24, 70], freeze="A2")
        _style(writer, "7_SO审计摘要", [30, 40], freeze="A2")
        _style(writer, "7_SO审计摘要",
               [16, 12, 20, 10, 8, 10, 8, 8, 10, 10, 8, 14, 12, 40, 20], freeze=None,
               detail_header_row=len(so_summary) + 3, detail_qty_columns=(4, 5, 6, 7, 8, 9, 10),
               detail_start=len(so_summary) + 4)
        _style(writer, "8_版本与证据", [20, 120], freeze="A2")

    manifest = dict(
        workbook=str(out_path),
        workbook_sha256=_sha256(out_path),
        generated_at=pd.Timestamp.now(tz="Asia/Shanghai").isoformat(timespec="seconds"),
        git_commit=_git_commit(),
        sheets={
            "1_说明与边界": "窗口口径、不可相加、待核与不守恒边界",
            "2_90天主表": f"{len(main90)} 键",
            "3_150天春节压力": f"{len(pressure150)} 键（含与 90 天差值）+ 春节 SO 块",
            "4_180天情景": f"{len(scenario180)} 键（scenario_only）",
            "5_30-60天参考": "窗口汇总",
            "6_180天其他去向": "待核/不可算/无需补货与动作分布",
            "7_SO审计摘要": "97 单汇总 + Top60 明细",
            "8_版本与证据": "输入 hash、commit、验收状态",
        },
        counts=dict(
            main90_keys=int(len(main90)),
            pressure150_keys=int(len(pressure150)),
            scenario180_keys=int(len(scenario180)),
            action_distribution=action_dist,
            pending=int(len(pending)), no_need=int(len(no_need)),
            not_computable=int(len(not_computable)),
            so_audit_orders=int(len(audit)),
        ),
        window_summary=summary.to_dict("records"),
        festival=festival.to_dict("records"),
        inputs=dict(windows_sha256=_sha256(windows_csv), keys_sha256=_sha256(keys_csv),
                    actions_sha256=_sha256(actions_parquet), so_audit_sha256=_sha256(so_audit_csv),
                    baseline_sha256=_sha256(baseline_actions) if baseline_actions else None),
        rules=["窗口都是从 as_of 起的累计，不可相加", "180 天只是情景，不是采购量",
               "待核动作留空、不按 0、不参与合计", "数字直取输入，未重算"],
        acceptance_status=acceptance_status,
    )
    manifest_path = out_path.with_name(out_path.stem + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def _apply_format(sheet, columns, rows) -> None:
    for column in columns:
        for row in rows:
            cell = sheet.cell(row=row, column=column)
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                value = float(cell.value)
                cell.number_format = INT_FORMAT if value.is_integer() and abs(value) >= 1 \
                    else QTY_FORMAT


def _style(writer, sheet_name: str, widths, freeze: str | None, qty_columns=(),
           detail_header_row: int | None = None, detail_qty_columns=(), detail_start=None) -> None:
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
        _apply_format(sheet, qty_columns, range(2, sheet.max_row + 1))
    if detail_qty_columns and detail_start:
        _apply_format(sheet, detail_qty_columns, range(detail_start, sheet.max_row + 1))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="多窗口业务审核工作簿 v3")
    parser.add_argument("--windows", required=True)
    parser.add_argument("--keys", required=True)
    parser.add_argument("--actions", required=True)
    parser.add_argument("--so-audit", required=True)
    parser.add_argument("--so-rows", default=None)
    parser.add_argument("--baseline-actions", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    manifest = build_workbook_v3(
        windows_csv=args.windows, keys_csv=args.keys, actions_parquet=args.actions,
        so_audit_csv=args.so_audit, so_rows_csv=args.so_rows, out_path=args.out,
        baseline_actions=args.baseline_actions)
    print(json.dumps({k: manifest[k] for k in ("workbook", "counts", "workbook_sha256")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
