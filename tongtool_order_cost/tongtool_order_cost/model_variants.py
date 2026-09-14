# -*- coding: utf-8 -*-
"""多方案并存的费率模型：层级集合、可信度加权与分组评估。

保留多个模型变体以便用实际效果对比（不替换既有发布逻辑）：

- `V0_基线`   现状：排他阶梯 + 硬阈值 30 样本 / 2 个月
- `V1_结构`   独立分层（不排他）+ 补 ZIP 首位档与「国家×重量档」+ 非美国阶梯补全
- `V2_可信度` 在 V1 之上把每个细层向父层按可信度加权 C = Z·X + (1−Z)·M, Z = n/(n+k)
- `V3_近月`   V2 + 按月份线性衰减加权（k 与衰减参数都从训练数据估，不硬编码）
- `V4_排平坦` V2 + 排除已标记的整月平坦费率月份

设计依据见 docs/research/2026-09-14-rate-table-training-methodology.md。
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import pandas as pd

from .history_last_leg_analysis import (
    PUBLISH_LEVELS,
    _row_keys,
    build_monthly_regime,
    build_package_observations,
)

# --------------------------------------------------------------------------- #
# 层级集合
# --------------------------------------------------------------------------- #
L_ZIP3 = ("国家", "通途SKU", "标准仓库", "标准渠道", "美国ZIP3", "观察重量阶梯")
L_ZIP1 = ("国家", "通途SKU", "标准仓库", "标准渠道", "目的地邮编首位", "观察重量阶梯")
L_SKU = ("国家", "通途SKU", "标准仓库", "标准渠道", "观察重量阶梯")
Z_ZIP3 = ("国家", "标准仓库", "标准渠道", "美国ZIP3", "观察重量阶梯")
Z_ZIP1 = ("国家", "标准仓库", "标准渠道", "目的地邮编首位", "观察重量阶梯")
Z_SKU = ("国家", "标准仓库", "标准渠道", "观察重量阶梯")
N_W = ("国家", "观察重量阶梯")
CH = ("国家", "标准仓库", "标准渠道")
WH = ("国家", "标准仓库")
CT = ("国家",)

MODERN_LEVELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("L1_SKU_ZIP3_重量", L_ZIP3),
    ("L1b_SKU_ZIP1_重量", L_ZIP1),
    ("L2_SKU_重量", L_SKU),
    ("L3_ZIP3_重量", Z_ZIP3),
    ("L3b_ZIP1_重量", Z_ZIP1),
    ("L4_ZIP3", ("国家", "标准仓库", "标准渠道", "美国ZIP3")),
    ("L5_重量", Z_SKU),
    ("L5b_国家重量", N_W),
    ("L6_仓库渠道", CH),
    ("L7_仓库", WH),
    ("L8_国家", CT),
)


def ordered_levels(names: Sequence[str], levels=MODERN_LEVELS) -> tuple[tuple[str, tuple[str, ...]], ...]:
    lookup = dict(levels)
    return tuple((name, lookup[name]) for name in names if name in lookup)


# 强分区渠道把分区档提到 SKU 之前；平坦渠道反过来
US_ZONE_FIRST = ("L1_SKU_ZIP3_重量", "L1b_SKU_ZIP1_重量", "L3_ZIP3_重量", "L3b_ZIP1_重量",
                 "L2_SKU_重量", "L4_ZIP3", "L5_重量", "L6_仓库渠道", "L7_仓库", "L8_国家")
US_SKU_FIRST = ("L1_SKU_ZIP3_重量", "L1b_SKU_ZIP1_重量", "L2_SKU_重量", "L3_ZIP3_重量",
                "L3b_ZIP1_重量", "L4_ZIP3", "L5_重量", "L6_仓库渠道", "L7_仓库", "L8_国家")
NON_US_LEVELS = ("L2_SKU_重量", "L5_重量", "L5b_国家重量", "L6_仓库渠道", "L7_仓库", "L8_国家")
STRONGLY_ZONED_CHANNELS = frozenset({"M6180", "US-FEDEX", "星链"})


def level_chain_for(nation: Any, channel: Any, scheme: str) -> tuple[str, ...]:
    if str(nation or "").strip().upper() != "US":
        return NON_US_LEVELS
    if scheme == "sku_first":
        return US_SKU_FIRST
    if scheme == "zone_first":
        return US_ZONE_FIRST
    # adaptive：强分区渠道分区优先，其余 SKU 优先
    return US_ZONE_FIRST if str(channel or "") in STRONGLY_ZONED_CHANNELS else US_SKU_FIRST


# --------------------------------------------------------------------------- #
# 可信度 k 估计（EPV / VHM）
# --------------------------------------------------------------------------- #
def estimate_credibility_k(observations: pd.DataFrame, cols: Sequence[str]) -> float:
    """用组内/组间方差分解估计可信度参数 k = EPV / VHM。

    样本少时 Z = n/(n+k) 自然趋小、估计被拉向父层；样本多时趋近自身经验。
    VHM 估计为负（组间差异不足）时返回一个较大的 k，使估计接近完全池化——
    这正是学界指出的「VHM 可能为负」的稳健处理。
    """
    data = observations[observations["建模状态"] == "可建模"]
    if data.empty:
        return 30.0
    group = data.groupby(list(cols), dropna=False)["观察费用"]
    stats = group.agg(n="size", mean="mean", var=lambda s: float(s.var(ddof=1)) if len(s) > 1 else 0.0)
    stats = stats[stats["n"] > 0]
    total_n = float(stats["n"].sum())
    if total_n <= 0:
        return 30.0
    weights = stats["n"] / total_n
    epv = float((stats["var"].fillna(0.0) * stats["n"]).sum() / total_n)
    weighted_mean = float((stats["mean"] * weights).sum())
    vhm = float((weights * (stats["mean"] - weighted_mean) ** 2).sum()) - epv / max(len(stats), 1)
    if not math.isfinite(vhm) or vhm <= 1e-9 or not math.isfinite(epv) or epv <= 0:
        return 1_000_000.0  # 组间无可辨差异 → 尽量池化
    return epv / vhm


def _credibility_weight(n: float, k: float) -> float:
    n = max(float(n), 0.0)
    return n / (n + k) if (n + k) > 0 else 0.0


# --------------------------------------------------------------------------- #
# 发布层构建
# --------------------------------------------------------------------------- #
def _stats_for(data: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    stats = (
        data.groupby(list(cols), dropna=False)["观察费用"]
        .agg(
            样本数="size",
            覆盖月份数="nunique",
            中位数="median",
            P25=lambda s: float(s.quantile(0.25)),
            P75=lambda s: float(s.quantile(0.75)),
            平均值="mean",
        )
        .reset_index()
    )
    return stats


def build_variant_tiers(
    observations: pd.DataFrame,
    *,
    levels=MODERN_LEVELS,
    min_samples: int = 30,
    min_months: int = 2,
    exclusive: bool = False,
    credibility: bool = False,
    recency: bool = False,
    drop_flat_months: bool = False,
    recency_halflife_months: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """按指定策略发布费率层；返回（层表, 每层 k 值）。

    `exclusive=True` 复刻现状（细层发过就从剩余池移除）；`False` 各层独立。
    `credibility=True` 时把每层向链上的父层按 Z = n/(n+k) 加权。
    `recency=True` 时按月份给样本线性衰减权重，半衰期由回测网格选出。
    """
    data = observations[observations["建模状态"] == "可建模"].copy()
    meta: dict[str, float] = {}
    if data.empty:
        return pd.DataFrame(columns=["匹配层级", "样本数"]), meta

    if drop_flat_months:
        regime = build_monthly_regime(observations)
        flat = regime[regime["费率形态"].str.startswith("平坦")]
        if len(flat):
            keys = set(zip(flat["月份"].astype(str), flat["标准仓库"], flat["标准渠道"]))
            mask = [
                (str(m), w, c) in keys
                for m, w, c in zip(data["月份"].astype(str), data["标准仓库"], data["标准渠道"])
            ]
            data = data[~pd.Series(mask, index=data.index)]

    if recency and recency_halflife_months > 0:
        months = sorted({str(m) for m in data["月份"].astype(str)})
        latest = months[-1] if months else ""
        age = {m: (int(latest[:4]) * 12 + int(latest[4:])) - (int(m[:4]) * 12 + int(m[4:])) for m in months}
        data["_w"] = [
            0.5 ** (age.get(str(m), 0) / recency_halflife_months) for m in data["月份"].astype(str)
        ]

    remaining = data
    published: list[pd.DataFrame] = []
    for index, (level_name, cols) in enumerate(levels):
        pool = remaining[remaining["SKU精确层可用"]] if "通途SKU" in cols else remaining
        if pool.empty:
            continue
        stats = _stats_for(pool, list(cols))
        if recency and recency_halflife_months > 0 and "_w" in pool.columns:
            stats = _weighted_stats_for(pool, list(cols))
        stats = stats[(stats["样本数"] >= min_samples) & (stats["覆盖月份数"] >= min_months)]
        if stats.empty:
            continue
        stats["匹配层级"] = level_name

        if credibility:
            parent_cols = levels[index + 1][1] if index + 1 < len(levels) else ("国家",)
            parent_pool = data if "通途SKU" not in parent_cols else data[data["SKU精确层可用"]]
            parent = _stats_for(parent_pool, list(parent_cols)) if len(parent_pool) else pd.DataFrame()
            k = estimate_credibility_k(data, list(cols))
            meta[level_name] = k
            stats = _blend_with_parent(stats, parent, list(cols), list(parent_cols), k)

        published.append(stats)
        if exclusive:
            keys = _row_keys(stats, list(cols), "\x1f")
            pool_keys = _row_keys(pool, list(cols), "\x1f")
            remaining = remaining[~remaining.index.isin(pool.index[pool_keys.isin(set(keys))])]
        if remaining.empty and exclusive:
            break

    if not published:
        return pd.DataFrame(columns=["匹配层级", "样本数"]), meta
    out = pd.concat(published, ignore_index=True)
    key_cols = list(dict.fromkeys(c for _, cols in levels for c in cols if c in out.columns))
    out["发布键"] = _row_keys(out, key_cols, "|")
    return out, meta


def _weighted_stats_for(data: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    """按 `_w` 加权的稳健统计；中位数用加权后等价样本量近似（重复计数）。"""
    rows = []
    for key, group in data.groupby(list(cols), dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        values, weights = group["观察费用"], group["_w"]
        effective_n = max(int(round(float(weights.sum()))), 1)
        repeated = pd.concat([values] * min(effective_n, 200), ignore_index=True)
        rows.append({
            **dict(zip(cols, key)),
            "样本数": effective_n,
            "覆盖月份数": int(group["月份"].nunique()),
            "中位数": float(repeated.median()),
            "P25": float(repeated.quantile(0.25)),
            "P75": float(repeated.quantile(0.75)),
            "平均值": float((values * weights).sum() / weights.sum()) if weights.sum() else float(values.mean()),
        })
    return pd.DataFrame(rows)


def _parent_lookup(parent: pd.DataFrame, keys: list[str]) -> pd.Series:
    """父层中位数查找表，键为 `keys` 的稳定拼接。"""
    keys = [c for c in keys if c in parent.columns]
    if not keys:
        return pd.Series(dtype="float64")
    frame = parent[keys + ["中位数"]].copy()
    frame["_k"] = _row_keys(frame, keys, "\x1f")
    return frame.groupby("_k")["中位数"].median()


def _blend_with_parent(
    stats: pd.DataFrame,
    parent: pd.DataFrame,
    cols: list[str],
    parent_cols: list[str],
    k: float,
) -> pd.DataFrame:
    """C = Z·自身中位数 + (1−Z)·父层中位数，Z = n/(n+k)。

    父键按「完整 → 去掉分区/重量 → 仅国家」逐级退化，保证父层缺失时仍有稳健兜底；
    完全取不到父值时保留自身中位数（Z 视作 1）。
    """
    out = stats.copy()
    if parent.empty:
        out["可信度Z"] = 1.0
        out["父层中位数"] = out["中位数"]
        return out

    common = [c for c in parent_cols if c in out.columns]
    zone_like = ("美国ZIP3", "目的地邮编首位", "观察重量阶梯")
    attempts = [
        common,
        [c for c in common if c not in zone_like],
        [c for c in common if c in ("国家", "标准仓库", "标准渠道")],
        [c for c in common if c == "国家"],
    ]

    values = pd.Series(float("nan"), index=out.index)
    for attempt in attempts:
        if not attempt:
            continue
        lookup = _parent_lookup(parent, attempt)
        if lookup.empty:
            continue
        mapped = _row_keys(out, attempt, "\x1f").map(lookup)
        values = values.mask(values.isna(), mapped)
    values = values.fillna(float(out["中位数"].median()))

    z = out["样本数"].map(lambda n: _credibility_weight(n, k))
    out["可信度Z"] = z.round(4)
    out["父层中位数"] = values.round(4)
    out["中位数"] = (z * out["中位数"] + (1 - z) * values).round(4)
    return out


def predict_with_variant(
    data: pd.DataFrame,
    tiers: pd.DataFrame,
    *,
    scheme: str = "adaptive",
    levels=MODERN_LEVELS,
) -> pd.Series:
    """按渠道自适应的层级链取首个命中的已发布层。"""
    out = pd.Series(0.0, index=data.index)
    if tiers is None or len(tiers) == 0:
        return out
    lookup_by_level = {
        name: dict(zip(
            _row_keys(tiers[tiers["匹配层级"] == name], list(cols), "\x1f"),
            tiers.loc[tiers["匹配层级"] == name, "中位数"],
        ))
        for name, cols in levels
    }
    level_cols = dict(levels)
    for (nation, channel), index in data.groupby(["国家", "标准渠道"], dropna=False).groups.items():
        chain = level_chain_for(nation, channel, scheme)
        subset = data.loc[index]
        assigned = pd.Series(0.0, index=index)
        for name in chain:
            cols = level_cols.get(name)
            if not cols:
                continue
            lookup = lookup_by_level.get(name) or {}
            if not lookup:
                continue
            keys = _row_keys(subset, list(cols), "\x1f")
            hit = (assigned <= 0) & keys.isin(lookup)
            assigned = assigned.mask(hit, keys.map(lookup))
        out.loc[index] = assigned
    return out


# --------------------------------------------------------------------------- #
# 评估
# --------------------------------------------------------------------------- #
def error_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    usable = (actual > 0) & (predicted > 0)
    if not usable.any():
        return {"覆盖率%": round(float((predicted > 0).mean() * 100), 1)}
    err = predicted[usable] - actual[usable]
    return {
        "覆盖率%": round(float((predicted > 0).mean() * 100), 1),
        "MAE": round(float(err.abs().mean()), 2),
        "MdAE": round(float(err.abs().median()), 2),
        "偏差": round(float(err.mean()), 2),
        "P90": round(float(err.abs().quantile(0.90)), 2),
        "相对误差中位%": round(float((err.abs() / actual[usable].replace(0, pd.NA)).median() * 100), 1),
    }


def evaluate_variant(
    training: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    variant: dict[str, Any],
    legacy: pd.DataFrame | None = None,
    group_cols: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """在给定训练/验证切分上评估一个变体；返回（总体指标, 分组指标）。"""
    from .history_last_leg_analysis import legacy_predict_fee_faithful

    if variant.get("name") == "V0_基线":
        levels = PUBLISH_LEVELS
        tiers, _ = build_variant_tiers(
            training, levels=levels, exclusive=True,
            min_samples=variant.get("min_samples", 30), min_months=variant.get("min_months", 2),
        )
        scheme = "adaptive_full"
    else:
        levels = MODERN_LEVELS
        tiers, _ = build_variant_tiers(
            training,
            levels=levels,
            exclusive=variant.get("exclusive", False),
            credibility=variant.get("credibility", False),
            recency=variant.get("recency", False),
            drop_flat_months=variant.get("drop_flat_months", False),
            recency_halflife_months=variant.get("recency_halflife_months", 0.0),
            min_samples=variant.get("min_samples", 30),
            min_months=variant.get("min_months", 2),
        )
        scheme = variant.get("scheme", "adaptive")

    data = validation.copy()
    if variant.get("name") == "V0_基线":
        data["预测"] = _predict_baseline(data, tiers)
    else:
        data["预测"] = predict_with_variant(data, tiers, scheme=scheme, levels=levels)

    rows = [{"变体": variant["name"], "范围": "总体", **error_metrics(data["观察费用"], data["预测"])}]
    if legacy is not None and len(legacy):
        pred = data.apply(
            lambda r: legacy_predict_fee_faithful(legacy, r["国家"], r["通途SKU"], r["观察重量_kg"])[0],
            axis=1,
        )
        rows.append({"变体": "HLF0001", "范围": "总体", **error_metrics(data["观察费用"], pred)})
        data["HLF0001"] = pred

    grouped = pd.DataFrame()
    if group_cols:
        records = []
        for key, group in data.groupby(list(group_cols), dropna=False):
            key = key if isinstance(key, tuple) else (key,)
            dims = dict(zip(group_cols, key))
            for name in ["HLF0001"] if "HLF0001" in data.columns else []:
                records.append({**dims, "变体": name, **error_metrics(group["观察费用"], group[name])})
            records.append({**dims, "变体": variant["name"], **error_metrics(group["观察费用"], group["预测"])})
        grouped = pd.DataFrame(records)
    return pd.DataFrame(rows), grouped


def _predict_baseline(data: pd.DataFrame, tiers: pd.DataFrame) -> pd.Series:
    out = pd.Series(0.0, index=data.index)
    for name, cols in PUBLISH_LEVELS:
        level = tiers[tiers["匹配层级"] == name]
        if level.empty:
            continue
        lookup = dict(zip(_row_keys(level, list(cols), "\x1f"), level["中位数"]))
        keys = _row_keys(data, list(cols), "\x1f")
        hit = (out <= 0) & keys.isin(lookup)
        out = out.mask(hit, keys.map(lookup))
    return out


VARIANTS: tuple[dict[str, Any], ...] = (
    {"name": "V0_基线", "min_samples": 30, "min_months": 2},
    {"name": "V1_结构_自适应", "exclusive": False, "scheme": "adaptive"},
    {"name": "V1b_结构_分区优先", "exclusive": False, "scheme": "zone_first"},
    {"name": "V1c_结构_SKU优先", "exclusive": False, "scheme": "sku_first"},
    {"name": "V2_可信度_30", "exclusive": False, "scheme": "zone_first", "credibility": True},
    # 低门槛 + 可信度：可信度的价值在于「替代硬阈值」，而不是叠加在 30 样本门槛之上
    {"name": "V3_低门槛5", "exclusive": False, "scheme": "zone_first",
     "min_samples": 5, "min_months": 1},
    {"name": "V3b_低门槛5_可信度", "exclusive": False, "scheme": "zone_first",
     "min_samples": 5, "min_months": 1, "credibility": True},
    {"name": "V4_排平坦_可信度", "exclusive": False, "scheme": "zone_first",
     "credibility": True, "drop_flat_months": True},
)
