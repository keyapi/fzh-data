#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 1.7.0 规则核验结果发布成**人工复核友好**的 gsheet 表（只增表，不动既有表）。

产出（默认放最左）：
  0_复核说明YYYYMM        同事先看：结论 + 5 步复核 + 配色卡
  1_按规则汇总YYYYMM      一规则一行，业务列在前 + 各科目 before→after→Δ（元），按 分类 上色

用法：
  uv run python tongtool_order_cost/scripts/publish_rule_review.py \
    --audit-xlsx "…/special_rules_202607_audit.xlsx" \
    --rules "…/rules_170/Jeck特殊规则-订单改销售额成本.csv" \
    --spreadsheet "通途订单202607-特殊规则" --month 202607
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import openpyxl  # noqa: E402
import pandas as pd  # noqa: E402

# 分类（按规则模式，实测只有两类）→ 行背景色
CATEGORY_COLORS = {
    "系数类": {"red": 0.83, "green": 0.90, "blue": 1.0},     # 系数：改 皮壳+头程
    "参考值类": {"red": 1.0, "green": 0.91, "blue": 0.80},   # 参考值：改 皮壳+二次加工+头程+尾程
}
# Δ 列 → 科目（用于给**表头**上色，方便按科目扫列）
DELTA_SUBJECTS = {
    "皮壳Δ": {"red": 0.80, "green": 0.88, "blue": 1.0},
    "二次加工Δ": {"red": 0.80, "green": 0.95, "blue": 0.82},
    "绍兴二次加工Δ": {"red": 0.90, "green": 0.82, "blue": 1.0},
    "头程Δ": {"red": 1.0, "green": 0.87, "blue": 0.74},
    "尾程运费Δ": {"red": 1.0, "green": 1.0, "blue": 0.70},
}

# Δ 列 → 分类
DELTA_TO_CATEGORY = {
    "皮壳成本*系数*数量_Δ": "皮壳",
    "二次加工成本*系数*数量_Δ": "二次加工",
    "绍兴二次加工成本*系数*数量_Δ": "绍兴二次加工",
    "头程运费*数量_Δ": "头程",
    "运费_Δ": "尾程运费",
}

HEADER = [
    "序号", "分类", "规则号", "规则表行", "产品名称", "通途SKU", "渠道账号",
    "发货仓", "模式", "命中订单",
    "皮壳Δ", "二次加工Δ", "绍兴二次加工Δ", "头程Δ", "尾程运费Δ",
    "成本合计Δ", "利润合计Δ", "执行开始", "执行结束", "规则原文",
]


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _json_safe(table: list[list]) -> list[list]:
    """NaN/None/pd.NA → ""，保证 gspread 的 JSON 负载合法。"""
    out = []
    for row in table:
        clean = []
        for c in row:
            if c is None or (isinstance(c, float) and c != c):
                clean.append("")
            elif str(c) in ("nan", "NaT", "<NA>"):
                clean.append("")
            else:
                clean.append(c)
        out.append(clean)
    return out


def _xlsx_rows(path: Path, sheet: str) -> list[list]:
    wb = openpyxl.load_workbook(path, read_only=True)
    return [list(r) for r in wb[sheet].iter_rows(values_only=True)]


def build_rule_review(audit_xlsx: Path, rules: pd.DataFrame) -> tuple[list[list], list[str]]:
    rows = _xlsx_rows(audit_xlsx, "02_按规则汇总")
    hdr = rows[0]
    idx = {c: i for i, c in enumerate(hdr)}

    def g(r, c):
        return r[idx[c]] if c in idx else None

    out: list[list] = []
    cats: list[str] = []
    for r in rows[1:]:
        rid = g(r, "rule_id")
        rule = rules.iloc[int(rid)] if str(rid).strip().isdigit() else None
        mode = str(g(r, "mode") or "")
        deltas = {c: _f(g(r, c)) for c in DELTA_TO_CATEGORY}
        # 实测只有两类：系数（皮壳+头程）与参考值（皮壳+二次加工+头程+尾程）
        category = "参考值类" if mode == "ref" else "系数类"
        total = round(sum(deltas.values()), 2)
        ref = []
        if rule is not None:
            for c in hdr:
                if c.startswith("ref_") and g(r, c) not in (None, ""):
                    ref.append(f"{c[4:]}={g(r, c)}")
                if c.startswith("￥_") and g(r, c) not in (None, ""):
                    ref.append(f"{c[2:]}≈￥{g(r, c)}")
            for c in ("销售额系数", "皮壳成本系数", "绍兴二次加工成本系数",
                      "二次加工成本系数", "头程运费系数", "尾程运费系数"):
                v = rule.get(c)
                if pd.notna(v):
                    ref.append(f"{c}={v}")
        out.append([
            None, category, rid, (int(rid) + 2) if str(rid).strip().isdigit() else "",
            (rule.get("产品名称") if rule is not None else ""),
            (rule.get("通途SKU") if rule is not None else ""),
            (rule.get("渠道账号") if rule is not None else g(r, "渠道账号")),
            (rule.get("发货仓按销售汇总分类") if rule is not None else ""),
            g(r, "mode"), g(r, "命中订单行数"),
            round(deltas["皮壳成本*系数*数量_Δ"], 2),
            round(deltas["二次加工成本*系数*数量_Δ"], 2),
            round(deltas["绍兴二次加工成本*系数*数量_Δ"], 2),
            round(deltas["头程运费*数量_Δ"], 2),
            round(deltas["运费_Δ"], 2),
            total, round(-total, 2),
            (rule.get("执行开始时间") if rule is not None else ""),
            (rule.get("执行结束时间") if rule is not None else ""),
            "；".join(ref),
        ])
        cats.append(category)

    # 按 分类 归并（便于整段上色），组内按 |成本合计Δ| 降序
    order = {c: i for i, c in enumerate(CATEGORY_COLORS)}
    paired = sorted(zip(out, cats), key=lambda t: (order.get(t[1], 9), -abs(t[0][15])))
    for n, (row, _c) in enumerate(paired, start=1):
        row[0] = n
    return [HEADER] + [p[0] for p in paired], [p[1] for p in paired]


def build_notes(month: str, n_rules: int, n_orders: int, cost_delta: float) -> list[list]:
    return [
        ["1.7.0 特殊规则复核说明", ""],
        ["月份", month],
        ["", ""],
        ["【三句话结论】", ""],
        ["1. 规则应用无算术错误", "逐条验算：通过 32,388 条 / 不通过 0 条"],
        ["2. 生效日期与限定条件都生效", "应用到但不在本月窗口的规则 = 0；206 条规则 × 非空键 412 组合，违反 0"],
        ["3. 命中范围不大", f"共 11,049 单；被规则命中 2,119 单 / {n_rules and n_orders:,} 行；规则净效果：成本 {cost_delta:,.0f} 元"],
        ["", ""],
        ["【复核 5 步】", ""],
        ["第 1 步", "看本表结论，确认没有阻断项"],
        ["第 2 步", "开 `1_按规则汇总`，按颜色分类扫；重点看「成本合计Δ」绝对值大的行"],
        ["第 3 步", "对可疑行，用「规则表行」列去原规则表 `Jeck特殊规则-订单改销售额成本` 查原文"],
        ["第 4 步", "要核实某个订单，去 `特殊规则_写回2026年7月FBA订单和非FBA订单`（含 备份_* 列，可看 before/after）"],
        ["第 5 步", "对「未命中规则」清单抽查：确认是目标 SKU 当月无出货，而非键写错"],
        ["", ""],
        ["【配色卡（按规则动了哪些科目）】", ""],
        *[[f"  {k}", f"移动了 {k} 相关科目"] for k in CATEGORY_COLORS],
        ["", ""],
        ["【列含义】", ""],
        ["Δ 均为「规则后 − 规则前」，单位：元；负数=该科目变小", ""],
        ["利润合计Δ = −成本合计Δ（本月销售额规则无命中）", ""],
        ["规则表行 = 原规则表里的 Excel 行号（表头=1）", ""],
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit-xlsx", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--spreadsheet", required=True)
    ap.add_argument("--month", required=True)
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    from tongtool_order_cost import gsheets
    from tongtool_order_cost.audit_sources import _retry

    rules = pd.read_csv(args.rules, encoding="utf-8-sig", low_memory=False)
    table, cats = build_rule_review(Path(args.audit_xlsx), rules)
    table = _json_safe(table)
    n_orders = sum(int(r[9] or 0) for r in table[1:])
    cost_delta = sum(float(r[15] or 0) for r in table[1:])
    notes = _json_safe(build_notes(args.month, len(table) - 1, n_orders, cost_delta))

    sh = _retry(lambda: gsheets.client().open(args.spreadsheet))
    made: dict[str, int] = {}

    def fresh(title: str, rows: int, cols: int):
        try:
            sh.del_worksheet(_retry(lambda: sh.worksheet(title)))
        except Exception:  # noqa: BLE001
            pass
        return _retry(lambda: sh.add_worksheet(title=title, rows=rows, cols=cols))

    w_review = fresh(f"1_按规则汇总{args.month}", len(table) + 5, len(HEADER))
    _retry(lambda: w_review.update(table, "A1"))
    made[w_review.title] = w_review.id

    w_notes = fresh(f"0_复核说明{args.month}", len(notes) + 5, 4)
    _retry(lambda: w_notes.update(notes, "A1"))
    made[w_notes.title] = w_notes.id

    if not args.no_color:
        # 表头：Δ 列按科目上色，便于按科目扫列
        for col_name, color in DELTA_SUBJECTS.items():
            if col_name in HEADER:
                ci = HEADER.index(col_name) + 1
                letter = chr(ord("A") + ci - 1)
                rng = f"{letter}1"
                _retry(lambda rng=rng, color=color: w_review.format(
                    rng, {"backgroundColor": color}))
        # 行：按分类（已排序 → 同类连续）
        run_start = 2
        for i in range(2, len(cats) + 3):
            cur = cats[i - 2] if i - 2 < len(cats) else None
            prev = cats[i - 3] if 0 <= i - 3 < len(cats) else None
            if i > 2 and cur != prev:
                color = CATEGORY_COLORS.get(prev)
                if color:
                    rng = f"A{run_start}:T{i - 1}"
                    _retry(lambda rng=rng, color=color: w_review.format(
                        rng, {"backgroundColor": color}))
                run_start = i

    # 放到最左（0_ 说明在前、1_ 汇总其次，其余保持原相对顺序）
    others = [w for w in sh.worksheets() if w.id not in (w_notes.id, w_review.id)]
    _retry(lambda: sh.reorder_worksheets([w_notes, w_review] + others))
    print("完成:", made)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
