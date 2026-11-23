# -*- coding: utf-8 -*-
"""业务工作簿 v4（v3 返修版，按复审 F1–F4）。

F1：每个窗口（90/150/180）的**动作量与剩余量按该窗口缺口重算**，不沿用 189 天 h180-actions；
   动作选择复用 ``decision_join._replenish_action`` 的同一套「覆盖优先」规则。
F2：SO 摘要与明细按 UOM 分列（个/件/套），禁止跨单位总量；条件供给写「有阶段证据、非可抵扣量」。
F3：边界补 2.779 天需求未知、SO 未进基线、14 天缓冲是条件政策、实际天数 91/154/182、动作源 189 天；
   G 列改名「加缓冲后总量」。
F4：版本页补 R6/R7 证据入口（净额 run 与动作层 manifest 的路径与哈希）。

只重算「动作量 / 剩余需补」这一派生字段；切片数量一律不改。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .business_review_multi import _festival_block, _num, _text, _window_summary
from .decision_join import _replenish_action

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]
WINDOW_LABELS = {30: "30 天参考", 60: "60 天参考", 90: "90 天主窗口", 120: "120 天",
                 150: "150 天春节压力", 180: "180 天情景（仅情景，非采购量）"}
ACTION_EVIDENCE_WINDOW = 180      # 阶段证据来自 h180 决策包（视界 189 天）
DEFAULT_REVIEW_FILE = ("C:/Users/zhang/.agent-ops/fzh-data/reviews/"
                       "business-workbook-v4-review-2026-10-28.md")
DEFAULT_BOARD_ENTRY = ("D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/"
                       "claude/control/PROJECT_BOARD.md")
HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
QTY_FORMAT = "0.000000"
INT_FORMAT = "#,##0"


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, cwd=Path(__file__).resolve().parents[1])
        return out.stdout.strip() or "unknown"
    except Exception:                                   # noqa: BLE001
        return "unknown"


def _stage_rows(actions: pd.DataFrame) -> dict[tuple, dict]:
    """把动作层的阶段证据按 key 建索引（只做证据来源，不用它的 action/action_qty）。"""
    rows = {}
    for record in actions.to_dict("records"):
        key = (record.get("canonical_sku"), record.get("canonical_warehouse"),
               record.get("canonical_uom"))
        rows[key] = record
    return rows


def _actions_for_window(keys: pd.DataFrame, window: int,
                        stage: dict[tuple, dict]) -> pd.DataFrame:
    """按该窗口缺口重算动作（F1）。缺口 = 该窗口 qty_current。"""
    subset = keys[(keys["window_days"] == window)
                  & (pd.to_numeric(keys["qty_current"], errors="coerce") > 0)].copy()
    rows = []
    for record in subset.sort_values("qty_current", ascending=False).to_dict("records"):
        key = (record["canonical_sku"], record["canonical_warehouse"], record["canonical_uom"])
        gap = float(record["qty_current"])
        evidence = stage.get(key) or {}
        action, covered, basis, confidence = _replenish_action(evidence, gap)
        rows.append({
            "SKU": record["canonical_sku"],
            "仓库": record["canonical_warehouse"],
            "单位": record["canonical_uom"],
            "窗口需求": _num(record["forecast_demand"]),
            "窗口未满足": _num(record["cum_unserved"]),
            "建议量（逐键向上取整）": gap,
            "加缓冲后总量": _num(record["qty_higher"]),
            "动作": action,
            "动作量": round(min(covered, gap), 6),
            "剩余需补": round(max(0.0, gap - covered), 6),
            "动作依据": basis,
            "来源SO": _text(evidence.get("action_source_so")),
            "来源WO": _text(evidence.get("action_source_wo")),
            "动作置信度": confidence,
            "动作口径": f"按 {window} 天窗口缺口重算；阶段证据源 "
                        f"{ACTION_EVIDENCE_WINDOW} 天决策包（视界 189 天）",
        })
    return pd.DataFrame(rows), subset


def _window_keys_with_actions(keys: pd.DataFrame, window: int,
                              stage: dict[tuple, dict]) -> pd.DataFrame:
    frame, _ = _actions_for_window(keys, window, stage)
    return frame


def _window_diff_with_actions(keys: pd.DataFrame, base: int, other: int,
                              stage: dict[tuple, dict]) -> pd.DataFrame:
    left = keys[keys["window_days"] == base].set_index(KEY)
    right = keys[keys["window_days"] == other].set_index(KEY)
    joined = left[["forecast_demand", "cum_unserved", "qty_current", "qty_higher"]].join(
        right[["forecast_demand", "cum_unserved", "qty_current", "qty_higher"]],
        how="outer", lsuffix="_base", rsuffix="_other").fillna(0.0).reset_index()
    mask = (joined["qty_current_other"] > 0) | (joined["qty_current_base"] > 0)
    rows = []
    for record in joined[mask].to_dict("records"):
        key = (record["canonical_sku"], record["canonical_warehouse"], record["canonical_uom"])
        gap90 = float(record["qty_current_base"])
        gap150 = float(record["qty_current_other"])
        evidence = stage.get(key) or {}
        action90, covered90, _, _ = _replenish_action(evidence, gap90) if gap90 > 0 else ("", 0.0, "", "")
        action150, covered150, basis150, _ = _replenish_action(evidence, gap150) if gap150 > 0 else ("", 0.0, "", "")
        rows.append({
            "SKU": key[0], "仓库": key[1], "单位": key[2],
            f"{base}天建议量": round(gap90, 6),
            f"{other}天建议量": round(gap150, 6),
            "建议量差（150−90）": round(gap150 - gap90, 6),
            "需求差": round(float(record["forecast_demand_other"])
                        - float(record["forecast_demand_base"]), 6),
            "未满足差": round(float(record["cum_unserved_other"])
                         - float(record["cum_unserved_base"]), 6),
            "90天动作": action90,
            "150天动作": action150,
            "150天动作量": round(min(covered150, gap150), 6) if gap150 > 0 else None,
            "150天剩余需补": round(max(0.0, gap150 - covered150), 6) if gap150 > 0 else None,
            "150天动作依据": basis150,
        })
    frame = pd.DataFrame(rows)
    return frame.sort_values("建议量差（150−90）", ascending=False) if len(frame) else frame


def _so_uom_tables(w1_path: str | Path, audit: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SO 摘要/明细按 UOM 分列（F2）：数量取自 W1 行，仍以审计单数为准。"""
    totals: dict[str, dict[str, float]] = {}
    detail_rows = []
    for line in Path(w1_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line).get("payload") or {}
        so = None
        for row in payload.get("lines") or []:
            qty = float(row.get("qty") or 0)
            delivered = float(row.get("delivered_qty") or 0)
            open_qty = qty - delivered
            if open_qty <= 0:
                continue
            uom = str(row.get("uom") or "")
            so = str(row.get("so"))
            bucket = totals.setdefault(uom, {"qty": 0.0, "orders": set(), "lines": 0})
            bucket["qty"] += open_qty
            bucket["orders"].add(so)
            bucket["lines"] += 1
            detail_rows.append(dict(SO=so, 单位=uom, 客户=str(row.get("customer") or ""),
                                    开放量=round(open_qty, 3)))
    summary = pd.DataFrame([
        {"单位": uom, "开放量": round(values["qty"], 3), "SO数": len(values["orders"]),
         "开放行": values["lines"]}
        for uom, values in sorted(totals.items())])
    summary["说明"] = "按 UOM 分列，禁止跨单位合计；条件供给是「有阶段证据、非可抵扣量」"
    detail = pd.DataFrame(detail_rows).groupby(["SO", "单位", "客户"], as_index=False)["开放量"].sum()
    detail = detail.sort_values("开放量", ascending=False)
    return summary, detail


def _boundaries(windows: pd.DataFrame, so_summary: pd.DataFrame) -> pd.DataFrame:
    actual = {int(r.window_days): r.actual_days for r in windows.itertuples(index=False)}
    rows = [
        ("口径总则", "观测销售路径模拟 + 条件供给；不是承诺、不是采购量；"
                 "180 天页为 **scenario_only**，仅作产能/春节排期情景"),
        ("窗口关系", "30/60/90/120/150/180 都是从 as_of 起的累计，**窗口之间不可相加**"),
        ("实际天数", f"90 天={actual.get(90)}、150 天={actual.get(150)}、180 天={actual.get(180)}"
                 "（按真实桶边界，可能比标称多几天）"),
        ("需求盲区", "库存 as_of 2026-10-26 05:17 → 决策日 2026-10-29 之间有 **2.779 天**"
                 "没有新的库存/供给证据，这段需求未知"),
        ("SO 管线", "**工厂 SO 供应**（公司向工厂下的生产/交付单）**未进入净额基线**；"
                 "本表缺口不含其到货承诺"),
        ("终端未履约 backlog", "**终端未履约订单（backlog）与本表分开**：本轮未接 backlog，"
                            "未来需求桶可能偏低；两者不是同一类供给/需求，不能互相冲减"),
        ("14 天缓冲", "「加缓冲后总量」= 建议量 + 14 天参考缓冲，是**条件政策**，"
                  "不是实测提前期，也**不是 β/95% 覆盖承诺**"),
        ("动作来源", f"阶段证据来自 {ACTION_EVIDENCE_WINDOW} 天决策包（视界 189 天）；"
                 "**动作量与剩余量按各页窗口缺口重算**，不沿用 189 天结果"),
        ("待核", "3,469 个待核键动作留空、不按 0、不参与合计"),
        ("SO 数量口径", "SO 开口量按单位分列：" +
         "；".join(f"{r['单位']} {r['开放量']:,.0f}" for _, r in so_summary.iterrows())
         + "（禁止跨单位合计）"),
        ("条件供给", "有阶段证据的供给是**条件量**（无 ETA、未证同批），不是可抵扣量"),
        ("数字来源", "窗口量取 horizon_windows；阶段证据取 h180 动作层；SO 数量取 W1 行；"
                 "全部直取，仅动作量/剩余量为按窗口重算的派生字段"),
    ]
    return pd.DataFrame(rows, columns=["项目", "说明与边界"])


def build_workbook_v4(*, windows_csv, keys_csv, actions_parquet, so_audit_csv,
                      w1_jsonl, out_path, r6_manifest=None, baseline_actions=None,
                      so_rows_csv=None, review_file=None, board_entry=None,
                      test_command=None, test_result=None,
                      acceptance_status="v5 待复审") -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    windows = pd.read_csv(windows_csv)
    keys = pd.read_csv(keys_csv)
    actions = pd.read_parquet(actions_parquet)
    audit = pd.read_csv(so_audit_csv, encoding="utf-8-sig")
    stage = _stage_rows(actions)

    summary = _window_summary(windows)
    ref3060 = _window_summary(windows[windows["window_days"].isin([30, 60])])
    main90 = _window_keys_with_actions(keys, 90, stage)
    scenario180 = _window_keys_with_actions(keys, 180, stage)
    pressure150 = _window_diff_with_actions(keys, 90, 150, stage)

    so_rows = pd.read_csv(so_rows_csv, encoding="utf-8-sig") if so_rows_csv else None
    so_summary, so_detail = _so_uom_tables(w1_jsonl, audit)
    festival = _festival_block(audit, so_rows)
    boundaries = _boundaries(windows, so_summary)

    pending = actions[actions["destination"] == "待核"]
    no_need = actions[actions["destination"] == "无需补货"]
    not_computable = actions[actions["destination"] == "不可算"]
    h180_actions = actions[actions["destination"] == "建议补货"]["action"].value_counts().to_dict()

    sections = pd.DataFrame([
        ("待核", f"{len(pending):,} 键", "无供给证据；动作与数量留空，不按 0"),
        ("不可算", f"{len(not_computable)} 键", "净额无法计算（no_snapshot_basis），不给动作"),
        ("无需补货（180 天口径）", f"{len(no_need)} 键", "期初已覆盖视界内需求"),
        ("对比：30 天口径的无需补货", "452 键", "来自 r2 包（30 天窗口）；不同窗口不能混用"),
        ("180 天动作分布（189 天口径，仅对照）", " / ".join(f"{k} {v}" for k, v in h180_actions.items()),
         "这是 h180 动作层的原值，**不是本工作簿 180 页的重算结果**"),
    ], columns=["类别", "数量", "说明"])

    version_rows = [
        ("工作簿", out_path.name),
        ("生成 commit", _git_commit()),
        ("生成时间", pd.Timestamp.now(tz="Asia/Shanghai").isoformat(timespec="seconds")),
        ("本版返修", "F1 动作按窗口重算；F2 SO 按 UOM 分列；F3 边界补盲区/SO/缓冲/实际天数/动作源；"
                    "F4 版本页补 R6/R7 证据入口"),
        ("窗口输入", str(windows_csv)),
        ("窗口输入 sha256", _sha256(windows_csv)),
        ("键表输入", str(keys_csv)),
        ("键表 sha256", _sha256(keys_csv)),
        ("动作层", str(actions_parquet)),
        ("动作层 sha256", _sha256(actions_parquet)),
        ("SO 审计", str(so_audit_csv)),
        ("SO 审计 sha256", _sha256(so_audit_csv)),
        ("W1 行级", str(w1_jsonl)),
        ("W1 行级 sha256", _sha256(w1_jsonl)),
    ]
    if r6_manifest:
        version_rows += [("R6 净额证据（manifest）", str(r6_manifest)),
                         ("R6 净额证据 sha256", _sha256(r6_manifest)
                          if Path(r6_manifest).exists() else "missing")]
    if baseline_actions:
        version_rows += [("旧 91 键对照", str(baseline_actions)),
                         ("旧 91 键 sha256", _sha256(baseline_actions)
                          if Path(baseline_actions).exists() else "missing")]
    version_rows += [
        ("R6 政策/模型版本入口",
         "policy-options-2026-10-28 / policy-reconcile-2026-10-28 / "
         "service-inventory-frontier-2026-10-28-v2 / sku-segment-policy-2026-10-28 "
         "（均在 supply-netting 目录下；本工作簿只引用，不含其数字）"),
        ("R6 证据边界",
         "**「核实到仓」≠「已证及时到仓」**：阶段证据只说明货在哪一步，"
         "不证明能在缺口日期前到仓；同批去重仍未证"),
        ("R7 测试命令/结果", f"{test_command or 'uv run pytest supply_netting/tests -q'}"
                          f" → {test_result or '见提交记录'}"),
        ("R7 独立复审文件", review_file or DEFAULT_REVIEW_FILE),
        ("R7 唯一看板入口", board_entry or DEFAULT_BOARD_ENTRY),
        ("验收状态", acceptance_status),
        ("下一动作", "交复审；按窗口分别审，不合并成一张采购单")]
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
        so_detail.head(80).to_excel(writer, sheet_name="7_SO审计摘要", index=False,
                                    startrow=len(so_summary) + 2)
        version.to_excel(writer, sheet_name="8_版本与证据", index=False)

        _style(writer, "1_说明与边界", [22, 120], freeze="A2")
        action_widths = [34, 24, 6, 11, 11, 14, 12, 14, 10, 10, 46, 24, 20, 10, 34]
        _style(writer, "2_90天主表", action_widths, freeze="A2", qty_columns=(4, 5, 6, 7, 9, 10))
        _style(writer, "3_150天春节压力", [22, 120], freeze="A2")
        _style(writer, "3_150天春节压力", [34, 24, 6, 12, 12, 14, 11, 11, 14, 10, 12, 12, 12, 12, 12, 40],
               freeze=None, detail_header_row=len(festival) + 3,
               detail_qty_columns=(4, 5, 6, 7, 8, 12, 13), detail_start=len(festival) + 4)
        _style(writer, "4_180天情景", action_widths, freeze="A2", qty_columns=(4, 5, 6, 7, 9, 10))
        _style(writer, "5_30-60天参考", [12, 20, 12, 30, 14, 14, 10, 10, 16, 14, 14, 30],
               freeze="A2", qty_columns=(3, 5, 6, 9, 10))
        _style(writer, "6_180天其他去向", [26, 30, 70], freeze="A2")
        _style(writer, "7_SO审计摘要", [12, 12, 30, 12], freeze="A2")
        _style(writer, "7_SO审计摘要", [18, 8, 24, 12], freeze=None,
               detail_header_row=len(so_summary) + 3, detail_qty_columns=(4,),
               detail_start=len(so_summary) + 4)
        _style(writer, "8_版本与证据", [26, 130], freeze="A2")

    manifest = dict(
        schema="business-review-workbook/v4",
        workbook=str(out_path),
        workbook_sha256=_sha256(out_path),
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        git_commit=_git_commit(),
        sheets={
            "2_90天主表": f"{len(main90)} 键，动作按 90 天缺口重算",
            "3_150天春节压力": f"{len(pressure150)} 键（与 90 天差值 + 150 天动作重算）",
            "4_180天情景": f"{len(scenario180)} 键，动作按 180 天缺口（实际"
                          f"{int(windows.loc[windows['window_days'] == 180, 'actual_days'].iloc[0])} 天）重算",
            "7_SO审计摘要": "按 UOM 分列：" + "；".join(
                f"{r['单位']} {r['开放量']:,.0f}" for _, r in so_summary.iterrows()),
        },
        counts=dict(main90=len(main90), pressure150=len(pressure150),
                    scenario180=len(scenario180), pending=len(pending),
                    no_need=len(no_need), not_computable=len(not_computable)),
        action_recompute=dict(
            rule="每页用该窗口 qty_current 作为缺口，复用 decision_join._replenish_action",
            evidence_source="h180 动作层（视界 189 天）",
            not_reused="不使用 h180 动作层的 action_qty/residual_gap 数值",
        ),
        inputs=dict(windows_sha256=_sha256(windows_csv), keys_sha256=_sha256(keys_csv),
                    actions_sha256=_sha256(actions_parquet),
                    so_audit_sha256=_sha256(so_audit_csv), w1_sha256=_sha256(w1_jsonl),
                    r6_manifest_sha256=(_sha256(r6_manifest)
                                        if r6_manifest and Path(r6_manifest).exists() else None)),
        evidence_entries=dict(
            r6_policy_models=["policy-options-2026-10-28", "policy-reconcile-2026-10-28",
                              "service-inventory-frontier-2026-10-28-v2",
                              "sku-segment-policy-2026-10-28"],
            r6_boundary="核实到仓 ≠ 已证及时到仓",
            r7_tests=test_result or "见提交记录",
            r7_review=review_file or DEFAULT_REVIEW_FILE,
            r7_board=board_entry or DEFAULT_BOARD_ENTRY,
        ),
        caveats=["窗口累计不可相加", "180 天仅情景", "待核不按 0", "14 天缓冲是条件政策",
                 "2.779 天需求未知", "SO 未进基线", "条件供给非可抵扣量"],
        status="pending",
        acceptance_status=acceptance_status,
    )
    out_path.with_name(out_path.stem + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
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
    parser = argparse.ArgumentParser(description="业务工作簿 v4（窗口动作重算 + SO 按 UOM）")
    parser.add_argument("--windows", required=True)
    parser.add_argument("--keys", required=True)
    parser.add_argument("--actions", required=True)
    parser.add_argument("--so-audit", required=True)
    parser.add_argument("--w1", required=True)
    parser.add_argument("--so-rows", default=None, help="工厂 SO 行级（口径 A 的 ETA 来源）")
    parser.add_argument("--review-file", default=None)
    parser.add_argument("--board-entry", default=None)
    parser.add_argument("--test-result", default=None)
    parser.add_argument("--r6-manifest", default=None)
    parser.add_argument("--baseline-actions", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    manifest = build_workbook_v4(
        windows_csv=args.windows, keys_csv=args.keys, actions_parquet=args.actions,
        so_audit_csv=args.so_audit, w1_jsonl=args.w1, out_path=args.out,
        r6_manifest=args.r6_manifest, baseline_actions=args.baseline_actions,
        so_rows_csv=args.so_rows, review_file=args.review_file,
        board_entry=args.board_entry, test_result=args.test_result)
    print(json.dumps({k: manifest[k] for k in ("workbook", "counts", "sheets",
                                               "workbook_sha256", "git_commit")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
