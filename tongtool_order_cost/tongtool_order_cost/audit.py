# -*- coding: utf-8 -*-
"""变更事件 → 多 Sheet 审计工作簿。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .engine_170 import ROLLUP_COLS, ApplyResult, REF_COLS

ARCHITECTURE_NOTE = """本工具证明的是「特殊规则是否按 1.7.0 代码逻辑执行」，不裁决参考成本是否合理。

## 两种规则方式
1. 系数(coeff)：目标列 = 备份列 × 系数
2. 参考值(ref)：￥单件 = 参考值(外币) × 汇率；数量列 = ￥单件 × 发货数量
   整行不可混用两种方式。

## 六月 AMZBAINAUS 常见误解
- 同事给的参考成本（如皮壳 $8、二次加工 $0）与旧架构（皮壳 ¥30+、二次加工 $40）不是同一套拆分。
- ref 会覆盖写入多列（含 皮壳成本 / 皮壳成本*系数 及对应*数量）。
- 二次加工参考为 0 → 对应列会被写成 0（不是「保持旧值」）。
- 单看皮壳科目，特殊规则后可能比旧皮壳更高；总成本是否下降要看各科合计（见 01_科目瀑布）。
- 尾程参考值对 FBA 订单不生效（发货仓/仓分类名含 FBA 则跳过改运费）。

## Sheet 怎么用
- 00_总览：账号级 before/after/Δ
- 01_科目瀑布：哪科升、哪科降
- 02_按规则汇总：谈判主表
- 03_订单明细 / 04_变更事件：穿透到行与列
- 05_未命中规则：规则生效但订单无匹配
"""


def _sum_col(df: pd.DataFrame, col: str, mask: pd.Series | None = None) -> float:
    if col not in df.columns:
        return float("nan")
    s = pd.to_numeric(df[col], errors="coerce")
    if mask is not None:
        s = s[mask]
    return float(s.fillna(0).sum())


def build_overview(result: ApplyResult) -> pd.DataFrame:
    df = result.orders
    mask = result.affected_mask
    rows = []
    meta = result.meta
    rows.append({"指标": "订单月", "值": meta.get("year_month")})
    rows.append({"指标": "汇率来源", "值": meta.get("fx_source")})
    rows.append({"指标": "去重策略", "值": meta.get("dedup_keep")})
    rows.append({"指标": "生效规则(去重前)", "值": meta.get("n_active_before_dedup")})
    rows.append({"指标": "生效规则(去重后)", "值": meta.get("n_active_after_dedup")})
    rows.append({"指标": "实际应用规则数", "值": meta.get("n_applied")})
    rows.append({"指标": "未命中规则数", "值": meta.get("n_unmatched")})
    rows.append({"指标": "跳过无效规则数", "值": meta.get("n_skipped")})
    rows.append({"指标": "影响订单行数", "值": meta.get("n_affected_rows")})
    rows.append({"指标": "变更事件数", "值": meta.get("n_events")})
    rows.append({"指标": "说明", "值": "本月多为参考值(ref)模式时，请结合 06_架构说明 解读科目升降"})

    for col in ROLLUP_COLS:
        bak = f"备份_{col}"
        if col not in df.columns:
            continue
        before = _sum_col(df, bak if bak in df.columns else col, mask if bak in df.columns else None)
        if bak not in df.columns:
            before = _sum_col(df, col)  # no backup — whole frame before apply not available
            after = _sum_col(df, col)
        else:
            # before = backup sum over ALL rows (account view) or affected?
            # Account-level: use all rows so colleague can match sheet totals.
            before = _sum_col(df, bak)
            after = _sum_col(df, col)
        rows.append(
            {
                "指标": f"{col} before",
                "值": before,
            }
        )
        rows.append({"指标": f"{col} after", "值": after})
        rows.append({"指标": f"{col} Δ", "值": after - before})
    return pd.DataFrame(rows)


def build_waterfall(result: ApplyResult) -> pd.DataFrame:
    df = result.orders
    rows = []
    for col in ROLLUP_COLS:
        bak = f"备份_{col}"
        if col not in df.columns or bak not in df.columns:
            continue
        before = _sum_col(df, bak)
        after = _sum_col(df, col)
        rows.append(
            {
                "科目": col,
                "before": before,
                "after": after,
                "delta": after - before,
                "方向": "升" if after - before > 1e-6 else ("降" if after - before < -1e-6 else "平"),
            }
        )
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("delta")
    return out


def build_by_rule(result: ApplyResult) -> pd.DataFrame:
    ev = result.change_events
    if ev is None or len(ev) == 0:
        return pd.DataFrame()
    # 仅直接写入事件（非 derived），按规则+科目聚合
    direct = ev[ev["mode"].isin(["ref", "coeff"])].copy()
    if len(direct) == 0:
        return pd.DataFrame()

    # 规则元数据
    meta_cols = ["rule_id", "通途SKU", "渠道账号", "mode", "fx"]
    rule_meta = (
        direct.groupby("rule_id", dropna=False)
        .agg(
            {
                "通途SKU": "first",
                "渠道账号": "first",
                "mode": "first",
                "fx": "first",
                "order_index": "nunique",
            }
        )
        .rename(columns={"order_index": "命中订单行数"})
        .reset_index()
    )

    # 参考值摘要
    ref_info = (
        direct[direct["ref_col"].astype(str) != ""]
        .groupby(["rule_id", "ref_col"], dropna=False)
        .agg({"ref_usd": "first", "rmb_unit": "first"})
        .reset_index()
    )
    if len(ref_info):
        ref_pivot = ref_info.pivot_table(
            index="rule_id", columns="ref_col", values="ref_usd", aggfunc="first"
        )
        ref_pivot.columns = [f"ref_{c}" for c in ref_pivot.columns]
        rmb_pivot = ref_info.pivot_table(
            index="rule_id", columns="ref_col", values="rmb_unit", aggfunc="first"
        )
        rmb_pivot.columns = [f"￥_{c}" for c in rmb_pivot.columns]
        rule_meta = rule_meta.merge(ref_pivot, on="rule_id", how="left")
        rule_meta = rule_meta.merge(rmb_pivot, on="rule_id", how="left")

    # 关键 rollup 列 before/after/delta（按订单行去重后取各列）
    # 用订单明细更准：每个 (rule_id, order_index, column) 取一条
    key_cols = [
        c
        for c in [
            "皮壳成本*系数*数量",
            "二次加工成本*系数*数量",
            "绍兴二次加工成本*系数*数量",
            "头程运费*数量",
            "海外仓成本*数量",
            "运费",
            "产品成本*系数*数量",
            "订单总成本*系数",
            "订单利润*系数",
            "售价*汇率",
        ]
        if True
    ]
    sub = direct[direct["column"].isin(key_cols)].copy()
    if len(sub):
        # same order+column may appear once per rule
        g = (
            sub.groupby(["rule_id", "column"], dropna=False)
            .agg(before=("before", "sum"), after=("after", "sum"), delta=("delta", "sum"))
            .reset_index()
        )
        wide_b = g.pivot_table(index="rule_id", columns="column", values="before", aggfunc="sum")
        wide_a = g.pivot_table(index="rule_id", columns="column", values="after", aggfunc="sum")
        wide_d = g.pivot_table(index="rule_id", columns="column", values="delta", aggfunc="sum")
        wide_b.columns = [f"{c}_before" for c in wide_b.columns]
        wide_a.columns = [f"{c}_after" for c in wide_a.columns]
        wide_d.columns = [f"{c}_Δ" for c in wide_d.columns]
        rule_meta = (
            rule_meta.merge(wide_b, on="rule_id", how="left")
            .merge(wide_a, on="rule_id", how="left")
            .merge(wide_d, on="rule_id", how="left")
        )
    return rule_meta


def build_order_detail(result: ApplyResult) -> pd.DataFrame:
    ev = result.change_events
    if ev is None or len(ev) == 0:
        return pd.DataFrame()
    direct = ev[ev["mode"].isin(["ref", "coeff", "derived"])].copy()
    # 宽表：每个 (rule_id, order_index) 一行，关键列 before/after/Δ
    focus = [
        "皮壳成本*系数*数量",
        "二次加工成本*系数*数量",
        "头程运费*数量",
        "运费",
        "订单总成本*系数",
        "订单利润*系数",
    ]
    sub = direct[direct["column"].isin(focus)].copy()
    if len(sub) == 0:
        return direct.head(0)

    base = (
        sub.groupby(["rule_id", "order_index", "订单号", "通途SKU", "渠道账号", "mode"], dropna=False)
        .agg({"发货数量": "first", "fx": "first", "rmb_unit": "first"})
        .reset_index()
    )
    for col in focus:
        piece = sub[sub["column"] == col][
            ["rule_id", "order_index", "before", "after", "delta"]
        ].drop_duplicates(["rule_id", "order_index"])
        piece = piece.rename(
            columns={
                "before": f"{col}_before",
                "after": f"{col}_after",
                "delta": f"{col}_Δ",
            }
        )
        base = base.merge(piece, on=["rule_id", "order_index"], how="left")

    # 仓分类
    df = result.orders
    if "发货仓按销售汇总分类" in df.columns:
        wh = df[["发货仓按销售汇总分类"]].copy()
        wh["order_index"] = df.index
        base = base.merge(wh, on="order_index", how="left")
    return base


def build_unmatched(result: ApplyResult) -> pd.DataFrame:
    u = result.rules_unmatched
    if u is None or len(u) == 0:
        return pd.DataFrame(columns=["excel_row", "通途SKU", "渠道账号", "说明"])
    cols = [
        c
        for c in [
            "excel_row",
            "通途SKU",
            "渠道账号",
            "发货仓按销售汇总分类",
            "发货区域",
            "运营人员",
            "rule_mode",
            "执行开始时间",
        ]
        + REF_COLS
        if c in u.columns
    ]
    out = u[cols].copy()
    out["说明"] = "当月生效且模式有效，但订单中无匹配行（SKU/账号/仓过滤后为 0）"
    return out


def write_audit_workbook(result: ApplyResult, out_path: Path | str) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    overview = build_overview(result)
    waterfall = build_waterfall(result)
    by_rule = build_by_rule(result)
    detail = build_order_detail(result)
    events = result.change_events if result.change_events is not None else pd.DataFrame()
    unmatched = build_unmatched(result)
    arch = pd.DataFrame({"说明": ARCHITECTURE_NOTE.splitlines()})

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="00_总览", index=False)
        waterfall.to_excel(writer, sheet_name="01_科目瀑布", index=False)
        by_rule.to_excel(writer, sheet_name="02_按规则汇总", index=False)
        detail.to_excel(writer, sheet_name="03_订单明细", index=False)
        # 事件可能很大，仍写入（同事需要穿透）
        events.to_excel(writer, sheet_name="04_变更事件", index=False)
        unmatched.to_excel(writer, sheet_name="05_未命中规则", index=False)
        arch.to_excel(writer, sheet_name="06_架构说明", index=False)
    return out_path


def summarize_console(result: ApplyResult) -> None:
    print("\n=== 审计摘要 ===")
    for k, v in result.meta.items():
        print(f"  {k}: {v}")
    wf = build_waterfall(result)
    if len(wf):
        print("\n科目 Δ (升/降):")
        print(wf.to_string(index=False))
