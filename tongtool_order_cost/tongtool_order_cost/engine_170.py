# -*- coding: utf-8 -*-
"""
1.7.0 特殊规则引擎 — 与 Colab notebook Cell 22 对齐。

方式1=系数；方式2=参考值(USD)×汇率 → ￥单件 × 发货数量。
应用过程写入 change_events，供审计穿透。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

COEFF_COLS = [
    "销售额系数",
    "皮壳成本系数",
    "绍兴二次加工成本系数",
    "二次加工成本系数",
    "头程运费系数",
    "海外仓成本系数",
    "尾程运费系数",
]
REF_COLS = [
    "发货数量1皮壳成本*系数参考值",
    "发货数量1绍兴二次加工成本*系数参考值",
    "发货数量1二次加工成本*系数参考值",
    "发货数量1头程运费参考值",
    "发货数量1海外仓成本参考值",
    "发货数量1订单尾程运费",
]
DUP_COLS = [
    "运营人员",
    "发货区域",
    "通途SKU",
    "渠道账号不含国家",
    "渠道账号",
    "发货仓按销售汇总分类",
]
ALLOWED_SHIPPING_AREAS = frozenset({"美国", "欧洲", "日本", "加拿大", "其它"})

COEFF_TO_TARGETS: dict[str, list[str]] = {
    "销售额系数": ["售价*汇率"],
    "皮壳成本系数": [
        "皮壳含包装成本",
        "皮壳不含包装成本",
        "皮壳成本",
        "皮壳成本*数量",
        "皮壳成本*系数",
        "皮壳成本*系数*数量",
    ],
    "绍兴二次加工成本系数": [
        "绍兴二次加工成本",
        "绍兴二次加工成本*数量",
        "绍兴二次加工成本*系数",
        "绍兴二次加工成本*系数*数量",
    ],
    "二次加工成本系数": [
        "二次加工成本",
        "二次加工成本*数量",
        "二次加工成本*系数",
        "二次加工成本*系数*数量",
    ],
    "头程运费系数": ["头程运费金额", "头程运费*数量"],
    "海外仓成本系数": ["海外仓成本", "海外仓成本*数量"],
    "尾程运费系数": ["运费"],
}

REF_TO_TARGETS: dict[str, tuple[list[str], list[str]]] = {
    "发货数量1皮壳成本*系数参考值": (
        ["皮壳含包装成本", "皮壳不含包装成本", "皮壳成本", "皮壳成本*系数"],
        ["皮壳成本*数量", "皮壳成本*系数*数量"],
    ),
    "发货数量1绍兴二次加工成本*系数参考值": (
        ["绍兴二次加工成本", "绍兴二次加工成本*系数"],
        ["绍兴二次加工成本*数量", "绍兴二次加工成本*系数*数量"],
    ),
    "发货数量1二次加工成本*系数参考值": (
        ["二次加工成本", "二次加工成本*系数"],
        ["二次加工成本*数量", "二次加工成本*系数*数量"],
    ),
    "发货数量1头程运费参考值": (["头程运费金额"], ["头程运费*数量"]),
    "发货数量1海外仓成本参考值": (["海外仓成本"], ["海外仓成本*数量"]),
    "发货数量1订单尾程运费": ([], ["运费"]),
}

BACKUP_COL_PAIRS = [
    ("售价*汇率", "备份_售价*汇率"),
    ("皮壳含包装成本", "备份_皮壳含包装成本"),
    ("皮壳不含包装成本", "备份_皮壳不含包装成本"),
    ("皮壳成本", "备份_皮壳成本"),
    ("皮壳成本*数量", "备份_皮壳成本*数量"),
    ("皮壳成本*系数", "备份_皮壳成本*系数"),
    ("皮壳成本*系数*数量", "备份_皮壳成本*系数*数量"),
    ("绍兴二次加工成本", "备份_绍兴二次加工成本"),
    ("绍兴二次加工成本*数量", "备份_绍兴二次加工成本*数量"),
    ("绍兴二次加工成本*系数", "备份_绍兴二次加工成本*系数"),
    ("绍兴二次加工成本*系数*数量", "备份_绍兴二次加工成本*系数*数量"),
    ("二次加工成本", "备份_二次加工成本"),
    ("二次加工成本*数量", "备份_二次加工成本*数量"),
    ("二次加工成本*系数", "备份_二次加工成本*系数"),
    ("二次加工成本*系数*数量", "备份_二次加工成本*系数*数量"),
    ("头程运费金额", "备份_头程运费金额"),
    ("头程运费*数量", "备份_头程运费*数量"),
    ("海外仓成本", "备份_海外仓成本"),
    ("海外仓成本*数量", "备份_海外仓成本*数量"),
    ("运费", "备份_运费"),
    ("产品成本*系数*数量", "备份_产品成本*系数*数量"),
    ("订单总成本*系数", "备份_订单总成本*系数"),
    ("订单利润*系数", "备份_订单利润*系数"),
]

# 审计汇总优先科目（数量合计列）
ROLLUP_COLS = [
    "售价*汇率",
    "皮壳成本*系数*数量",
    "绍兴二次加工成本*系数*数量",
    "二次加工成本*系数*数量",
    "头程运费*数量",
    "海外仓成本*数量",
    "运费",
    "产品成本*系数*数量",
    "订单总成本*系数",
    "订单利润*系数",
]


def norm_cell(val: Any) -> str:
    v = str(val).strip()
    return "" if v in ("", "nan", "None", "NaT", "<NA>") else v


def rule_cell_str(row: pd.Series, col: str) -> str:
    return norm_cell(row.get(col, ""))


def parse_rule_ym(s: str) -> datetime:
    s = str(s).strip().replace("/", "-")
    # Timestamp / datetime
    if " " in s:
        s = s.split(" ")[0]
    parts = [p for p in s.split("-") if p]
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return datetime(int(parts[0]), int(parts[1]), 1)
    return datetime.strptime(s[:7], "%Y-%m")


def month_active(row: pd.Series, year_month: datetime) -> bool:
    start = rule_cell_str(row, "执行开始时间")
    end = rule_cell_str(row, "执行结束时间")
    if not start and not end:
        return True
    if not start and end:
        return year_month <= parse_rule_ym(end)
    if start and not end:
        return year_month >= parse_rule_ym(start)
    return parse_rule_ym(start) <= year_month <= parse_rule_ym(end)


def has_any_coeff(row: pd.Series) -> bool:
    return any(pd.notna(row.get(c)) for c in COEFF_COLS)


def has_any_ref(row: pd.Series) -> bool:
    return any(pd.notna(row.get(c)) for c in REF_COLS)


def get_rule_mode(row: pd.Series) -> str:
    hc, hr = has_any_coeff(row), has_any_ref(row)
    if hc and hr:
        return "invalid_mixed"
    if hr:
        cur = rule_cell_str(row, "收款币种")
        if not cur:
            return "invalid_no_currency"
        if pd.isna(row.get("汇率")):
            return "invalid_no_fx"
        return "ref"
    if hc:
        return "coeff"
    return "none"


def build_order_filter(df_order: pd.DataFrame, rule: pd.Series) -> pd.Series:
    sku = rule_cell_str(rule, "通途SKU")
    if not sku:
        return pd.Series(False, index=df_order.index)
    f = df_order["通途SKU"].astype(str) == sku
    operator = rule_cell_str(rule, "运营人员")
    area = rule_cell_str(rule, "发货区域")
    acct = rule_cell_str(rule, "渠道账号")
    acct_nc = rule_cell_str(rule, "渠道账号不含国家")
    wh_cat = rule_cell_str(rule, "发货仓按销售汇总分类")
    if operator and "运营人员" in df_order.columns:
        f &= df_order["运营人员"].astype(str) == operator
    if area and "发货区域" in df_order.columns:
        f &= df_order["发货区域"].astype(str) == area
    if acct and "渠道账号" in df_order.columns:
        f &= df_order["渠道账号"].astype(str) == acct
    if acct_nc and "渠道账号不含国家" in df_order.columns:
        f &= df_order["渠道账号不含国家"].astype(str) == acct_nc
    if wh_cat and "发货仓按销售汇总分类" in df_order.columns:
        f &= df_order["发货仓按销售汇总分类"].astype(str) == wh_cat
    return f


def ensure_backup_columns(df: pd.DataFrame) -> list[str]:
    created: list[str] = []
    for src, bak in BACKUP_COL_PAIRS:
        if src in df.columns and bak not in df.columns:
            df[bak] = df[src]
            created.append(bak)
    return created


def fba_mask(df: pd.DataFrame) -> pd.Series:
    m = pd.Series(False, index=df.index)
    if "发货仓按销售汇总分类" in df.columns:
        m = m | df["发货仓按销售汇总分类"].astype(str).str.contains(
            "FBA", case=False, na=False
        )
    if "发货仓库" in df.columns:
        m = m | df["发货仓库"].astype(str).str.contains("FBA", case=False, na=False)
    return m


def attach_fx_to_rules(rules: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    out = rules.drop(columns=["汇率"], errors="ignore").copy()
    out = out.merge(fx[["收款币种", "汇率"]], how="left", on="收款币种")
    out.loc[out["收款币种"] == "RMB", "汇率"] = 1.0
    for col in REF_COLS:
        rmb_col = f"￥{col}"
        out[rmb_col] = pd.to_numeric(out[col], errors="coerce") * pd.to_numeric(
            out["汇率"], errors="coerce"
        ).fillna(1.0)
    return out


def parse_year_month(ym: str | int) -> datetime:
    s = str(ym).strip().replace("-", "")
    if len(s) == 6 and s.isdigit():
        return datetime(int(s[:4]), int(s[4:6]), 1)
    return parse_rule_ym(str(ym))


@dataclass
class ApplyResult:
    orders: pd.DataFrame
    rules_active: pd.DataFrame
    rules_applied: pd.DataFrame
    rules_unmatched: pd.DataFrame
    rules_skipped: pd.DataFrame
    change_events: pd.DataFrame
    affected_mask: pd.Series
    meta: dict[str, Any] = field(default_factory=dict)


def _order_key(df: pd.DataFrame, idx) -> str:
    parts = []
    for c in ("订单号", "通途SKU", "发货仓库", "发货仓按销售汇总分类"):
        if c in df.columns:
            parts.append(str(df.at[idx, c]))
    parts.append(str(idx))
    return "|".join(parts)


def apply_special_rules(
    orders: pd.DataFrame,
    rules: pd.DataFrame,
    year_month: datetime | str,
    fx: pd.DataFrame,
    *,
    dedup_keep: str = "last",
    fx_source: str = "",
    verbose: bool = True,
) -> ApplyResult:
    """对订单应用当月生效特殊规则，返回调整后订单 + 变更事件。"""
    ym = parse_year_month(year_month) if not isinstance(year_month, datetime) else year_month
    df = orders.copy()
    if "渠道账号不含国家" not in df.columns and "渠道账号" in df.columns:
        df["渠道账号不含国家"] = df["渠道账号"].astype(str).str.strip().str[:-2]

    created = ensure_backup_columns(df)
    if verbose and created:
        print(f"已备份 {len(created)} 列")

    rules_fx = attach_fx_to_rules(rules, fx)
    rules_fx["当月生效"] = rules_fx.apply(lambda r: month_active(r, ym), axis=1)
    active = rules_fx[rules_fx["当月生效"]].copy()
    active["rule_mode"] = active.apply(get_rule_mode, axis=1)

    dup_cols = [c for c in DUP_COLS if c in active.columns]
    n_before_dedup = len(active)
    if dup_cols:
        active = active.drop_duplicates(subset=dup_cols, keep=dedup_keep)

    if verbose:
        print(
            f"订单月 {ym.strftime('%Y%m')}: 生效 {n_before_dedup} → "
            f"去重(keep={dedup_keep})后 {len(active)}; FX={fx_source or 'n/a'}"
        )
        if "汇率" in fx.columns and len(fx):
            print("汇率表:")
            print(fx.to_string(index=False))

    fba = fba_mask(df)
    events: list[dict[str, Any]] = []
    all_affected = pd.Series(False, index=df.index)
    prod_affected = pd.Series(False, index=df.index)
    applied_rows: list[pd.Series] = []
    unmatched_rows: list[pd.Series] = []
    skipped_rows: list[pd.Series] = []
    applied_count = 0
    skipped_invalid = 0

    def apply_ref_per_unit(
        mask: pd.Series,
        rmb_per_unit: float,
        unit_cols: list[str],
        total_cols: list[str],
        *,
        rule: pd.Series,
        ref_col: str,
        ref_usd: float,
    ) -> None:
        qty = pd.to_numeric(df.loc[mask, "发货数量"], errors="coerce").fillna(0)
        pu = float(rmb_per_unit)
        tot = pu * qty
        # capture before from current (or backup) then write
        write_cols = [c for c in unit_cols + total_cols if c in df.columns]
        befores: dict[str, pd.Series] = {}
        for c in write_cols:
            bak = f"备份_{c}"
            if bak in df.columns:
                befores[c] = pd.to_numeric(df.loc[mask, bak], errors="coerce")
            else:
                befores[c] = pd.to_numeric(df.loc[mask, c], errors="coerce")
        for uc in unit_cols:
            if uc in df.columns:
                df.loc[mask, uc] = pu
        for tc in total_cols:
            if tc in df.columns:
                df.loc[mask, tc] = tot
        idxs = df.index[mask]
        for col in write_cols:
            after = pd.to_numeric(df.loc[idxs, col], errors="coerce")
            before = befores[col]
            for i in idxs:
                b = before.at[i]
                a = after.at[i]
                try:
                    delta = float(a) - float(b) if pd.notna(a) and pd.notna(b) else float("nan")
                except (TypeError, ValueError):
                    delta = float("nan")
                events.append(
                    {
                        "rule_id": rule.get("excel_row", rule.name),
                        "rule_index": rule.name,
                        "通途SKU": rule_cell_str(rule, "通途SKU"),
                        "渠道账号": rule_cell_str(rule, "渠道账号"),
                        "mode": "ref",
                        "ref_col": ref_col,
                        "coeff_col": "",
                        "ref_usd": ref_usd,
                        "coeff_val": None,
                        "fx": rule.get("汇率"),
                        "rmb_unit": pu,
                        "order_key": _order_key(df, i),
                        "订单号": df.at[i, "订单号"] if "订单号" in df.columns else "",
                        "order_index": i,
                        "发货数量": float(qty.at[i]) if i in qty.index else float("nan"),
                        "column": col,
                        "before": b,
                        "after": a,
                        "delta": delta,
                    }
                )

    for idx, rule in active.iterrows():
        mode = rule["rule_mode"]
        sku = rule_cell_str(rule, "通途SKU")
        if mode.startswith("invalid") or mode == "none":
            skipped_invalid += 1
            skipped_rows.append(rule)
            if verbose:
                print(f"跳过规则[{rule.get('excel_row', idx)}] mode={mode} SKU={sku}")
            continue

        f = build_order_filter(df, rule)
        n = int(f.sum())
        if verbose:
            print(
                f"规则[{rule.get('excel_row', idx)}] mode={mode} SKU={sku} "
                f"账号={rule_cell_str(rule, '渠道账号') or '(不限)'} "
                f"仓={rule_cell_str(rule, '发货仓按销售汇总分类') or '(不限)'} -> {n} 行"
            )
        if n == 0:
            unmatched_rows.append(rule)
            continue

        applied_count += 1
        applied_rows.append(rule)

        if mode == "coeff":
            all_affected = all_affected | f
            for coeff_col, target_cols in COEFF_TO_TARGETS.items():
                v = rule.get(coeff_col, float("nan"))
                if pd.isna(v):
                    continue
                v = float(v)
                write_cols = [c for c in target_cols if c in df.columns]
                befores = {}
                for tc in write_cols:
                    bak = f"备份_{tc}"
                    src = bak if bak in df.columns else tc
                    befores[tc] = pd.to_numeric(df.loc[f, src], errors="coerce")
                for tc in write_cols:
                    bak = f"备份_{tc}"
                    src_vals = (
                        pd.to_numeric(df.loc[f, bak], errors="coerce")
                        if bak in df.columns
                        else pd.to_numeric(df.loc[f, tc], errors="coerce")
                    )
                    df.loc[f, tc] = src_vals * v
                idxs = df.index[f]
                qty = pd.to_numeric(df.loc[f, "发货数量"], errors="coerce").fillna(0)
                for tc in write_cols:
                    after = pd.to_numeric(df.loc[idxs, tc], errors="coerce")
                    before = befores[tc]
                    for i in idxs:
                        b, a = before.at[i], after.at[i]
                        try:
                            delta = (
                                float(a) - float(b)
                                if pd.notna(a) and pd.notna(b)
                                else float("nan")
                            )
                        except (TypeError, ValueError):
                            delta = float("nan")
                        events.append(
                            {
                                "rule_id": rule.get("excel_row", idx),
                                "rule_index": idx,
                                "通途SKU": sku,
                                "渠道账号": rule_cell_str(rule, "渠道账号"),
                                "mode": "coeff",
                                "ref_col": "",
                                "coeff_col": coeff_col,
                                "ref_usd": None,
                                "coeff_val": v,
                                "fx": rule.get("汇率"),
                                "rmb_unit": None,
                                "order_key": _order_key(df, i),
                                "订单号": df.at[i, "订单号"] if "订单号" in df.columns else "",
                                "order_index": i,
                                "发货数量": float(qty.at[i]) if i in qty.index else float("nan"),
                                "column": tc,
                                "before": b,
                                "after": a,
                                "delta": delta,
                            }
                        )
                if coeff_col in (
                    "皮壳成本系数",
                    "绍兴二次加工成本系数",
                    "二次加工成本系数",
                ):
                    prod_affected = prod_affected | f

        elif mode == "ref":
            rule_hit = False
            for ref_col, (unit_cols, total_cols) in REF_TO_TARGETS.items():
                if pd.isna(rule.get(ref_col)):
                    continue
                rmb_pu = rule.get(f"￥{ref_col}")
                if pd.isna(rmb_pu):
                    continue
                ref_usd = float(rule.get(ref_col))
                if ref_col == "发货数量1订单尾程运费":
                    # 正数尾程已含在 Amazon FBA 账期，FBA 行跳过以免重复计入。
                    # 负数 = 账期差异冲减，FBA 也写入 运费。
                    # 0 = 无差异占位，FBA 仍跳过（不覆盖已有尾程）。
                    n_fba = int((f & fba).sum())
                    if ref_usd < 0:
                        f_tail = f
                        if verbose and n_fba > 0:
                            print(
                                f"  FBA {n_fba} 行写入尾程差异 "
                                f"(ref={ref_usd})"
                            )
                    else:
                        f_tail = f & (~fba)
                        if verbose and n_fba > 0:
                            print(
                                f"  FBA {n_fba} 行跳过尾程"
                                f"（参考值 {ref_usd}，账期已含或无差异）"
                            )
                    n_tail = int(f_tail.sum())
                    if n_tail == 0:
                        continue
                    apply_ref_per_unit(
                        f_tail,
                        float(rmb_pu),
                        unit_cols,
                        total_cols,
                        rule=rule,
                        ref_col=ref_col,
                        ref_usd=ref_usd,
                    )
                    all_affected = all_affected | f_tail
                    rule_hit = True
                else:
                    apply_ref_per_unit(
                        f,
                        float(rmb_pu),
                        unit_cols,
                        total_cols,
                        rule=rule,
                        ref_col=ref_col,
                        ref_usd=ref_usd,
                    )
                    all_affected = all_affected | f
                    rule_hit = True
                    if ref_col in (
                        "发货数量1皮壳成本*系数参考值",
                        "发货数量1绍兴二次加工成本*系数参考值",
                        "发货数量1二次加工成本*系数参考值",
                    ):
                        prod_affected = prod_affected | f
            if not rule_hit and verbose:
                print(f"  规则[{rule.get('excel_row', idx)}] 参考值未产生调整")

    # 衍生列重算
    prod_sum_cols = [
        c
        for c in [
            "皮壳成本*系数*数量",
            "绍兴二次加工成本*系数*数量",
            "二次加工成本*系数*数量",
        ]
        if c in df.columns
    ]
    if prod_sum_cols and "产品成本*系数*数量" in df.columns and prod_affected.any():
        df.loc[prod_affected, "产品成本*系数*数量"] = df.loc[
            prod_affected, prod_sum_cols
        ].sum(axis=1)
        if verbose:
            print(f"重算 产品成本*系数*数量: {int(prod_affected.sum())} 行")

    total_sum_cols = [
        c
        for c in ["产品成本*系数*数量", "头程运费*数量", "海外仓成本*数量", "运费"]
        if c in df.columns
    ]
    if total_sum_cols and "订单总成本*系数" in df.columns and all_affected.any():
        df.loc[all_affected, "订单总成本*系数"] = df.loc[
            all_affected, total_sum_cols
        ].sum(axis=1)
        if verbose:
            print(f"重算 订单总成本*系数: {int(all_affected.sum())} 行")

    if (
        all(c in df.columns for c in ["订单利润*系数", "售价*汇率", "订单总成本*系数"])
        and all_affected.any()
    ):
        df.loc[all_affected, "订单利润*系数"] = (
            pd.to_numeric(df.loc[all_affected, "售价*汇率"], errors="coerce")
            - pd.to_numeric(df.loc[all_affected, "订单总成本*系数"], errors="coerce")
        )
        if verbose:
            print(f"重算 订单利润*系数: {int(all_affected.sum())} 行")

    # 衍生列变更事件（相对备份）
    for col in ("产品成本*系数*数量", "订单总成本*系数", "订单利润*系数"):
        bak = f"备份_{col}"
        if col not in df.columns or bak not in df.columns:
            continue
        mask = all_affected if col != "产品成本*系数*数量" else (prod_affected | all_affected)
        idxs = df.index[mask]
        before = pd.to_numeric(df.loc[idxs, bak], errors="coerce")
        after = pd.to_numeric(df.loc[idxs, col], errors="coerce")
        qty = (
            pd.to_numeric(df.loc[idxs, "发货数量"], errors="coerce").fillna(0)
            if "发货数量" in df.columns
            else pd.Series(1.0, index=idxs)
        )
        for i in idxs:
            b, a = before.at[i], after.at[i]
            try:
                delta = float(a) - float(b) if pd.notna(a) and pd.notna(b) else float("nan")
            except (TypeError, ValueError):
                delta = float("nan")
            if pd.isna(delta) or abs(delta) < 1e-12:
                continue
            events.append(
                {
                    "rule_id": "",
                    "rule_index": "",
                    "通途SKU": df.at[i, "通途SKU"] if "通途SKU" in df.columns else "",
                    "渠道账号": df.at[i, "渠道账号"] if "渠道账号" in df.columns else "",
                    "mode": "derived",
                    "ref_col": "",
                    "coeff_col": "",
                    "ref_usd": None,
                    "coeff_val": None,
                    "fx": None,
                    "rmb_unit": None,
                    "order_key": _order_key(df, i),
                    "订单号": df.at[i, "订单号"] if "订单号" in df.columns else "",
                    "order_index": i,
                    "发货数量": float(qty.at[i]) if i in qty.index else float("nan"),
                    "column": col,
                    "before": b,
                    "after": a,
                    "delta": delta,
                }
            )

    events_df = pd.DataFrame(events)
    applied_df = pd.DataFrame(applied_rows) if applied_rows else active.iloc[0:0].copy()
    unmatched_df = (
        pd.DataFrame(unmatched_rows) if unmatched_rows else active.iloc[0:0].copy()
    )
    skipped_df = pd.DataFrame(skipped_rows) if skipped_rows else active.iloc[0:0].copy()

    if verbose:
        print(
            f"应用 {applied_count} 条规则, 跳过无效 {skipped_invalid}, "
            f"未命中 {len(unmatched_df)}, 影响订单行 {int(all_affected.sum())}, "
            f"变更事件 {len(events_df)}"
        )

    meta = {
        "year_month": ym.strftime("%Y%m"),
        "dedup_keep": dedup_keep,
        "fx_source": fx_source,
        "n_active_before_dedup": n_before_dedup,
        "n_active_after_dedup": len(active),
        "n_applied": applied_count,
        "n_unmatched": len(unmatched_df),
        "n_skipped": skipped_invalid,
        "n_affected_rows": int(all_affected.sum()),
        "n_events": len(events_df),
    }
    return ApplyResult(
        orders=df,
        rules_active=active,
        rules_applied=applied_df,
        rules_unmatched=unmatched_df,
        rules_skipped=skipped_df,
        change_events=events_df,
        affected_mask=all_affected,
        meta=meta,
    )
