# -*- coding: utf-8 -*-
"""通途月度订单历史尾程费用只读分析。"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

REQUIRED_COLUMNS = {
    "发货日期",
    "通途SKU",
    "发货数量",
    "渠道",
    "渠道账号",
    "发货仓库",
    "包裹号",
    "邮寄方式",
    "通途重量",
    "包裹总运费",
    "订单号",
    "国家/地区",
    "邮编",
}
PLATFORM_PAID_CHANNELS = frozenset({"WAYFAIR", "WF", "OVERSTOCK", "OSTK", "OS", "POTTERYBARN", "PB"})
PLATFORM_PAID_ACCOUNTS = frozenset({"TTTOODDLYUS", "TTCOZYDOZYUS"})
# 起运邮编由用户 2026-09-11 核实：USNJ=07936（新泽西），USTX=77099（休斯顿）。
# 计算 UPS/FedEx zone 还需承运商分区表；本模块只用 ZIP3 作分区代理。
ORIGIN_ZIP5 = {"USNJ": "07936", "USTX": "77099"}
ORIGIN_ZIP3 = {"USNJ": "079", "USTX": "770"}


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalized(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def normalize_warehouse(value: Any) -> str:
    text = _normalized(value)
    if "CENTRADE" in text:
        return "USNJ"
    if "DANEEY" in text or "USTX" in text or "美中" in _text(value):
        return "USTX"
    if "POLAND" in text or "波兰" in _text(value):
        return "PL"
    return _text(value)


def normalize_postal(value: Any, country: Any) -> tuple[str, str, bool]:
    raw = _text(value).upper()
    if _normalized(country) in {"US", "USA", "UNITEDSTATES"}:
        match = re.match(r"^\s*(\d{5})(?:-\d{4})?\s*$", raw)
        if not match:
            return raw, "", False
        zip5 = match.group(1)
        return zip5, zip5[:3], True
    return raw, "", bool(raw)


def normalize_mail_method(value: Any) -> tuple[str, str, str]:
    raw = _text(value)
    provider, _, service = raw.partition(">>")
    probe = f"{provider} {service}".upper()
    if "FEDEX" in probe:
        carrier = "FEDEX"
    elif "UPS" in probe:
        carrier = "UPS"
    elif "USPS" in probe or "POSTPONY" in probe:
        carrier = "USPS"
    elif "GLS" in probe:
        carrier = "GLS"
    elif "DHL" in probe:
        carrier = "DHL"
    else:
        carrier = _normalized(provider) or "UNKNOWN"
    normalized_service = re.sub(r"[^A-Z0-9]+", "_", service.upper()).strip("_") or "UNKNOWN"
    return provider.strip(), carrier, normalized_service


CHANNEL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("M6180", "蜴国际"), "M6180"),
    (("VITE",), "VITE"),
    (("OVERSTOCK", "OSTK"), "OSTK"),
    (("WAYFAIR", "WFCG"), "WFCG"),
    (("星链",), "星链"),
    (("TIKTOK",), "TIKTOK"),
    (("GLS",), "GLS-PL"),
    (("DHL",), "DHL24"),
    (("POSTPONY", "USPSFIRSTCLASS"), "POSTPONY"),
    (("CENTRADE", "NOTPRIME"), "CENTRADE-NOTPRIME"),
    (("云仓",), "云仓直发"),
    (("USFEDEX",), "US-FEDEX"),
)


def _probe(value: Any) -> str:
    """保留中文字符的归一化，避免 星链/云仓 等中文渠道名被清空。"""
    return re.sub(r"[^0-9A-Z一-鿿]", "", _text(value).upper())


def normalize_channel(provider: Any, service: Any) -> str:
    """把 `邮寄方式` 折成价格本级的承运渠道。

    同为 FedEx，`VITE-Fedex` / `US-FedEx` / `M6180蜴国际` 是三套不同价目
    （USNJ 中位 122.40 / 150.00 / 89.70）。若按 carrier=FEDEX 合并，就会重演
    「全国均价」式的平均化错误，因此渠道必须单独成维。
    """
    probe = _probe(f"{_text(provider)}{_text(service)}")
    for keywords, code in CHANNEL_RULES:
        if any(_probe(k) in probe for k in keywords):
            return code
    return _normalized(provider) or "UNKNOWN"


def observed_weight_tier(weight_kg: Any) -> str:
    if pd.isna(weight_kg) or float(weight_kg) <= 0:
        return ""
    upper = math.ceil(float(weight_kg))
    lower = max(0, upper - 1)
    return f"({lower},{upper}]kg"


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype("string").str.replace(",", "", regex=False), errors="coerce")


def _validate_columns(df: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"订单表缺少列: {', '.join(sorted(missing))}")


def prepare_order_rows(orders: pd.DataFrame, month: str) -> pd.DataFrame:
    _validate_columns(orders)
    df = orders.copy()
    df["月份"] = month
    for col in ("发货数量", "商品重量", "通途重量", "物流商重量", "包裹总运费", "通途运费", "物流商运费"):
        if col in df.columns:
            df[col] = _numeric(df[col])

    df["国家"] = df["国家/地区"].map(_normalized)
    df["标准仓库"] = df["发货仓库"].map(normalize_warehouse)
    postal = df.apply(lambda row: normalize_postal(row["邮编"], row["国家/地区"]), axis=1)
    df[["邮编标准值", "美国ZIP3", "邮编有效"]] = pd.DataFrame(postal.tolist(), index=df.index)
    mail = df["邮寄方式"].map(normalize_mail_method)
    df[["物流商原值", "标准物流商", "标准服务"]] = pd.DataFrame(mail.tolist(), index=df.index)
    df["标准渠道"] = [
        normalize_channel(provider, service)
        for provider, service in zip(df["物流商原值"], df["标准服务"])
    ]
    df["观察重量_kg"] = df["通途重量"] / 1000
    df["观察重量阶梯"] = df["观察重量_kg"].map(observed_weight_tier)
    df["包裹键"] = df["月份"].astype(str) + "|" + df["包裹号"].map(_text)
    df["起点邮编"] = df["标准仓库"].map(ORIGIN_ZIP5)

    channel = df["渠道"].map(_normalized)
    account = df["渠道账号"].map(_normalized)
    warehouse_raw = df["发货仓库"].map(_text)
    warehouse = warehouse_raw.map(_normalized)
    df["排除原因"] = ""
    df.loc[channel.isin(PLATFORM_PAID_CHANNELS), "排除原因"] = "平台承担尾程:渠道"
    df.loc[(df["排除原因"] == "") & account.isin(PLATFORM_PAID_ACCOUNTS), "排除原因"] = "平台承担尾程:账号"
    df.loc[(df["排除原因"] == "") & warehouse.str.contains("FBA", na=False), "排除原因"] = "FBA仓"
    df.loc[(df["排除原因"] == "") & warehouse_raw.str.contains("多渠道仓库", case=False, na=False), "排除原因"] = "多渠道仓库"
    return df


def build_package_observations(rows: pd.DataFrame) -> pd.DataFrame:
    package_meta = (
        rows.groupby("包裹键", dropna=False)
        .agg(
            月份=("月份", "first"),
            包裹号=("包裹号", "first"),
            发货日期=("发货日期", "first"),
            订单号=("订单号", "first"),
            国家=("国家", "first"),
            发货仓库=("发货仓库", "first"),
            标准仓库=("标准仓库", "first"),
            起点邮编=("起点邮编", "first"),
            邮编原值=("邮编", "first"),
            邮编标准值=("邮编标准值", "first"),
            美国ZIP3=("美国ZIP3", "first"),
            邮编有效=("邮编有效", "first"),
            邮寄方式=("邮寄方式", "first"),
            标准物流商=("标准物流商", "first"),
            标准渠道=("标准渠道", "first"),
            标准服务=("标准服务", "first"),
            观察重量_kg=("观察重量_kg", "first"),
            观察重量阶梯=("观察重量阶梯", "first"),
            包裹总运费=("包裹总运费", "max"),
            通途运费=("通途运费", "sum"),
            物流商运费=("物流商运费", "sum"),
            排除原因=("排除原因", lambda s: next((v for v in s if v), "")),
            商品行数=("通途SKU", "size"),
            SKU数=("通途SKU", "nunique"),
            通途SKU=("通途SKU", lambda s: "|".join(sorted({_text(v) for v in s if _text(v)}))),
            发货数量=("发货数量", "sum"),
            包裹费用最小值=("包裹总运费", "min"),
            包裹费用最大值=("包裹总运费", "max"),
        )
        .reset_index()
    )
    # 费用列优先级：`物流商运费` 是**实际回传的承运商扣款**（月初先是 EN 预估占位，
    # 之后被李娜上传的真实费用替换），是唯一可信的建模目标。
    # `包裹总运费` 口径不稳定：实测同一包裹有时等于物流商运费、有时等于通途运费，
    # 波兰线上更是长期停留在通途侧报价（52.88），因此只能作为兜底。
    # `通途运费` 是通途自己的阶梯预估，最后兜底。
    observed_fee = pd.Series(0.0, index=package_meta.index)
    fee_source = pd.Series("", index=package_meta.index)
    for column in ("物流商运费", "包裹总运费", "通途运费"):
        use = (fee_source == "") & (package_meta[column] > 0)
        observed_fee = observed_fee.mask(use, package_meta[column])
        fee_source = fee_source.mask(use, column)
    package_meta["观察费用"] = observed_fee
    package_meta["费用来源"] = fee_source
    package_meta["建模状态"] = "可建模"
    package_meta["跳过原因"] = ""
    excluded = package_meta["排除原因"] != ""
    package_meta.loc[excluded, "建模状态"] = "跳过"
    package_meta.loc[excluded, "跳过原因"] = package_meta.loc[excluded, "排除原因"]
    conditions = [
        ((package_meta["包裹费用最大值"] - package_meta["包裹费用最小值"]) > 0.05, "同包裹费用不一致"),
        (package_meta["观察费用"] <= 0, "无正数费用"),
        (package_meta["观察重量_kg"].isna(), "重量非数值"),
        (package_meta["观察重量_kg"] <= 0, "重量非正数"),
        ((package_meta["国家"] == "US") & ~package_meta["邮编有效"], "美国邮编无效"),
    ]
    for mask, reason in conditions:
        target = (package_meta["建模状态"] == "可建模") & mask
        package_meta.loc[target, "建模状态"] = "跳过"
        package_meta.loc[target, "跳过原因"] = reason
    package_meta["SKU精确层可用"] = (package_meta["建模状态"] == "可建模") & (package_meta["SKU数"] == 1)
    return package_meta


def add_outlier_flags(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    out["统计异常"] = False
    out["异常原因"] = ""
    eligible = out["建模状态"] == "可建模"
    group_cols = ["国家", "标准仓库", "美国ZIP3", "标准物流商", "观察重量阶梯"]
    for _, index in out[eligible].groupby(group_cols, dropna=False).groups.items():
        values = out.loc[index, "观察费用"]
        if len(values) < 4:
            continue
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = q3 - q1
        median = values.median()
        mad = (values - median).abs().median()
        iqr_mask = (values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr) if iqr > 0 else pd.Series(False, index=index)
        mad_mask = ((values - median).abs() / (1.4826 * mad) > 3.5) if mad > 0 else pd.Series(False, index=index)
        flagged = iqr_mask | mad_mask
        out.loc[flagged[flagged].index, "统计异常"] = True
        out.loc[flagged[flagged].index, "异常原因"] = "组内IQR/MAD异常"
    return out


def _trimmed_mean(values: pd.Series, proportion: float = 0.1) -> float:
    ordered = values.dropna().sort_values()
    trim_n = int(len(ordered) * proportion)
    if trim_n and len(ordered) > 2 * trim_n:
        ordered = ordered.iloc[trim_n : len(ordered) - trim_n]
    return float(ordered.mean()) if len(ordered) else float("nan")


def build_group_statistics(observations: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    data = observations[observations["建模状态"] == "可建模"].copy()
    if "通途SKU" in group_cols:
        data = data[data["SKU精确层可用"]]
    if data.empty:
        return pd.DataFrame(columns=group_cols)

    # 异常只标记不删除：去异常统计在全为异常时回退到全体样本。
    data["_去异常费用"] = data["观察费用"].where(~data["统计异常"])
    data["_统计基准费用"] = data["_去异常费用"].fillna(data["观察费用"])

    grouped = data.groupby(group_cols, dropna=False)
    stats = grouped.agg(
        样本数=("观察费用", "size"),
        去异常样本数=("_去异常费用", lambda s: int(s.notna().sum())),
        异常数=("统计异常", "sum"),
        覆盖月份数=("月份", "nunique"),
        P25=("观察费用", lambda s: float(s.quantile(0.25))),
        中位数=("观察费用", "median"),
        P75=("观察费用", lambda s: float(s.quantile(0.75))),
        P90=("观察费用", lambda s: float(s.quantile(0.90))),
        最小值=("观察费用", "min"),
        最大值=("观察费用", "max"),
        平均值=("观察费用", "mean"),
        去异常中位数=("_统计基准费用", "median"),
    )
    stats["截尾均值"] = grouped["_统计基准费用"].apply(_trimmed_mean)
    stats["置信等级"] = [
        "高" if n >= 30 and m >= 3 else ("中" if n >= 10 and m >= 2 else "低")
        for n, m in zip(stats["样本数"], stats["覆盖月份数"])
    ]
    return stats.reset_index()


@dataclass
class HistoryLastLegAnalysis:
    rows: pd.DataFrame
    observations: pd.DataFrame
    reconciliation: pd.DataFrame
    fee_sources: pd.DataFrame
    monthly_regime: pd.DataFrame
    monthly: pd.DataFrame
    channel_stats: pd.DataFrame
    zone_gradient: pd.DataFrame
    tier_stats: pd.DataFrame
    sku_stats: pd.DataFrame
    publishable: pd.DataFrame
    publish_coverage: pd.DataFrame
    outliers: pd.DataFrame
    skipped: pd.DataFrame


def analyze_history_last_leg(monthly_orders: Iterable[tuple[str, pd.DataFrame]]) -> HistoryLastLegAnalysis:
    row_frames = [prepare_order_rows(frame, month) for month, frame in monthly_orders]
    rows = pd.concat(row_frames, ignore_index=True) if row_frames else pd.DataFrame()
    observations = add_outlier_flags(build_package_observations(rows))

    reconciliation = (
        observations.groupby("月份", dropna=False)
        .agg(
            输入包裹数=("包裹键", "size"),
            可建模包裹数=("建模状态", lambda s: int((s == "可建模").sum())),
            跳过包裹数=("建模状态", lambda s: int((s == "跳过").sum())),
            SKU精确层包裹数=("SKU精确层可用", "sum"),
            多SKU包裹数=("SKU数", lambda s: int((s > 1).sum())),
            异常包裹数=("统计异常", "sum"),
        )
        .reset_index()
    )
    reconciliation["对账差异"] = reconciliation["输入包裹数"] - reconciliation["可建模包裹数"] - reconciliation["跳过包裹数"]
    eligible = observations[observations["建模状态"] == "可建模"]
    fee_sources = (
        eligible.groupby(["月份", "费用来源"], dropna=False)
        .agg(包裹数=("包裹键", "size"), 中位数=("观察费用", "median"))
        .reset_index()
    )
    monthly = build_group_statistics(observations, ["月份", "国家", "标准仓库"])
    channel_stats = build_group_statistics(observations, ["国家", "标准仓库", "标准渠道"])
    tier_stats = build_group_statistics(observations, ["国家", "标准仓库", "标准渠道", "美国ZIP3", "观察重量阶梯"])
    sku_stats = build_group_statistics(
        observations, ["国家", "通途SKU", "标准仓库", "标准渠道", "美国ZIP3", "观察重量阶梯"]
    )
    outliers = eligible[eligible["统计异常"]].copy()
    skipped = observations[observations["建模状态"] == "跳过"].copy()
    publishable = build_publishable_tiers(observations)
    return HistoryLastLegAnalysis(
        rows,
        observations,
        reconciliation,
        fee_sources,
        build_monthly_regime(observations),
        monthly,
        channel_stats,
        build_zone_gradient(observations),
        tier_stats,
        sku_stats,
        publishable,
        summarize_publish_coverage(observations, publishable),
        outliers,
        skipped,
    )


def build_zone_gradient(observations: pd.DataFrame, min_samples_per_band: int = 30) -> pd.DataFrame:
    """按 国家×仓库×渠道 汇总目的地分区的费率梯度，判断分区是否可分。

    用目的地邮编首位（10 个地理带）作分区代理；足够样本的带之间中位数差距
    就是该渠道的分区幅度。USNJ(VITE) 近区→远区约 +13%，USTX 平坦，直接回答
    「该仓该渠道值不值得建分区层」。
    """
    data = observations[observations["建模状态"] == "可建模"].copy()
    data = data[data["美国ZIP3"].astype(str).str.len() == 3]
    if data.empty:
        return pd.DataFrame(columns=["国家", "标准仓库", "标准渠道", "目的地邮编首位"])
    data = data.assign(目的地邮编首位=data["美国ZIP3"].astype(str).str[0])
    bands = (
        data.groupby(["国家", "标准仓库", "标准渠道", "目的地邮编首位"], dropna=False)["观察费用"]
        .agg(样本数="size", 中位数="median")
        .reset_index()
    )
    usable = bands[bands["样本数"] >= min_samples_per_band]
    summary = (
        usable.groupby(["国家", "标准仓库", "标准渠道"], dropna=False)["中位数"]
        .agg(可用分区带数="size", 最便宜带中位="min", 最贵带中位="max")
        .reset_index()
    )
    summary["分区幅度%"] = (
        (summary["最贵带中位"] - summary["最便宜带中位"]) / summary["最便宜带中位"] * 100
    ).round(1)
    summary["分区结论"] = [
        "分区显著" if amp >= 10 and n >= 3 else ("分区弱" if amp >= 5 else "近乎不分区")
        for amp, n in zip(summary["分区幅度%"], summary["可用分区带数"])
    ]
    return bands.merge(summary, on=["国家", "标准仓库", "标准渠道"], how="left").sort_values(
        ["国家", "标准仓库", "标准渠道", "目的地邮编首位"]
    )


PUBLISH_LEVELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("L1_SKU_分区_重量", ("国家", "通途SKU", "标准仓库", "标准渠道", "美国ZIP3", "观察重量阶梯")),
    ("L2_SKU_重量", ("国家", "通途SKU", "标准仓库", "标准渠道", "观察重量阶梯")),
    ("L3_分区_重量", ("国家", "标准仓库", "标准渠道", "美国ZIP3", "观察重量阶梯")),
    ("L4_分区", ("国家", "标准仓库", "标准渠道", "美国ZIP3")),
    ("L5_重量", ("国家", "标准仓库", "标准渠道", "观察重量阶梯")),
    ("L6_仓库渠道", ("国家", "标准仓库", "标准渠道")),
    ("L7_仓库", ("国家", "标准仓库")),
    ("L8_国家", ("国家",)),
)
PUBLISH_LEVELS_ZONE_FIRST: tuple[tuple[str, tuple[str, ...]], ...] = (
    PUBLISH_LEVELS[0],
    PUBLISH_LEVELS[2],
    PUBLISH_LEVELS[1],
    *PUBLISH_LEVELS[3:],
)
STRONGLY_ZONED_CHANNELS = frozenset({"M6180", "US-FEDEX", "星链"})


def _row_keys(frame: pd.DataFrame, cols: list[str], separator: str) -> pd.Series:
    """稳定拼接分层键；缺失值统一成空串，避免 dtype/NaN 参与比较。"""
    return (
        frame[cols]
        .astype("string")
        .fillna("")
        .apply(lambda row: separator.join(row), axis=1)
    )


def summarize_publish_coverage(observations: pd.DataFrame, tiers: pd.DataFrame) -> pd.DataFrame:
    """把每个可建模包裹归到最细的已发布层，核对覆盖率。

    分层发布不能静默丢包裹：未能归入任何已发布层（样本/月份不足）的必须计数列出。
    """
    data = observations[observations["建模状态"] == "可建模"]
    if data.empty:
        return pd.DataFrame(columns=["匹配层级", "层数", "覆盖包裹数"])
    assigned = pd.Series("", index=data.index)
    if len(tiers):
        for level_name, cols in PUBLISH_LEVELS:
            level = tiers[tiers["匹配层级"] == level_name]
            if level.empty:
                continue
            keys = set(_row_keys(level, list(cols), "\x1f"))
            candidate = _row_keys(data, list(cols), "\x1f")
            hit = (assigned == "") & candidate.isin(keys)
            assigned = assigned.mask(hit, level_name)
    rows = (
        assigned.replace("", "未覆盖")
        .value_counts()
        .rename_axis("匹配层级")
        .reset_index(name="覆盖包裹数")
    )
    if len(tiers):
        counts = tiers.groupby("匹配层级")["样本数"].size().rename("层数")
        rows = rows.merge(counts, on="匹配层级", how="left")
    else:
        rows["层数"] = 0
    rows["层数"] = rows["层数"].fillna(0).astype(int)
    rows["占比%"] = (rows["覆盖包裹数"] / len(data) * 100).round(1)
    return rows.sort_values("覆盖包裹数", ascending=False)[["匹配层级", "层数", "覆盖包裹数", "占比%"]]


def build_publishable_tiers(
    observations: pd.DataFrame,
    *,
    min_samples: int = 30,
    min_months: int = 2,
    levels: tuple[tuple[str, tuple[str, ...]], ...] = PUBLISH_LEVELS,
    exclusive: bool = True,
) -> pd.DataFrame:
    """按由细到粗的层级发布费率行；细层样本不足时自动并入较粗层。

    只对「可建模」包裹生效；SKU 精确层额外要求单 SKU 包裹。阈值不硬编码业务
    猜测，默认 30 样本 / 2 个月，可按回测结果调整。
    """
    data = observations[observations["建模状态"] == "可建模"]
    if data.empty:
        return pd.DataFrame(columns=["匹配层级", "发布键", "样本数", "中位数"])
    remaining = data
    published: list[pd.DataFrame] = []
    for level_name, cols in levels:
        if remaining.empty:
            break
        pool = remaining[remaining["SKU精确层可用"]] if "通途SKU" in cols else remaining
        if pool.empty:
            continue
        stats = build_group_statistics(pool, list(cols))
        stats = stats[(stats["样本数"] >= min_samples) & (stats["覆盖月份数"] >= min_months)]
        if stats.empty:
            continue
        stats["匹配层级"] = level_name
        published.append(stats)
        keys = _row_keys(stats, list(cols), "\x1f")
        pool_keys = _row_keys(pool, list(cols), "\x1f")
        if exclusive:
            remaining = remaining[~remaining.index.isin(pool.index[pool_keys.isin(set(keys))])]
    if not published:
        return pd.DataFrame(columns=["匹配层级", "样本数", "中位数"])
    out = pd.concat(published, ignore_index=True)
    key_cols = list(dict.fromkeys(c for _, cols in levels for c in cols if c in out.columns))
    out["发布键"] = _row_keys(out, key_cols, "|")
    return out[["匹配层级"] + key_cols + [c for c in out.columns if c not in key_cols + ["匹配层级"]]]


def build_monthly_regime(observations: pd.DataFrame) -> pd.DataFrame:
    """按 月份×仓库×渠道 探测「整月平坦费率」。

    2026-03 的 USNJ 各目的地中位数都是 126.0、2026-04/05 的 M6180 恒为
    110.4/109.7 —— 这类月份若混进分区模型会直接污染分区系数，因此单独标出。
    """
    data = observations[observations["建模状态"] == "可建模"]
    if data.empty:
        return pd.DataFrame(columns=["月份", "标准仓库", "标准渠道", "费率形态"])
    stats = (
        data.groupby(["月份", "标准仓库", "标准渠道"], dropna=False)["观察费用"]
        .agg(
            包裹数="size",
            中位数="median",
            P25=lambda s: float(s.quantile(0.25)),
            P75=lambda s: float(s.quantile(0.75)),
        )
        .reset_index()
    )
    stats["四分位距"] = (stats["P75"] - stats["P25"]).round(2)
    stats["费率形态"] = [
        "平坦（疑似整月一价）" if n >= 20 and iqr <= 2 else "正常"
        for n, iqr in zip(stats["包裹数"], stats["四分位距"])
    ]
    return stats.sort_values(["月份", "标准仓库", "标准渠道"])


def load_legacy_items(path: Path | str) -> pd.DataFrame:
    """读取 HLF0001 子表导出（列：sku/nation/w/cost；w 为克）。"""
    frame = pd.read_csv(path)
    frame = frame.rename(
        columns={"tongtool_sku": "sku", "fg_unit_weight": "w", "avg_per_shipping_cost": "cost"}
    )
    for col in ("w", "cost"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["sku", "nation"])


def legacy_predict_fee_faithful(
    legacy: pd.DataFrame,
    nation: Any,
    sku: Any,
    weight_kg: Any,
) -> tuple[float, str]:
    """忠实复刻线上 `_get_hist_predict_fee_for_excel`，含其量纲缺陷。

    优先级1：`SKU + 国家` 精确匹配（线上无 ORDER BY，当前键唯一故取首条）。
    优先级2：**忽略 SKU**，按国家取最近 `fg_unit_weight`——但该列存的是克、
    传入的是千克，因此实际恒定命中该国最小的非零重量记录。
    保留缺陷以便回测量化，修复应在 EN 侧进行。
    """
    if pd.isna(nation) or pd.isna(weight_kg):
        return 0.0, "输入缺失"
    nation = str(nation).strip()
    sku = str(sku).strip() if sku is not None else ""

    if sku:
        hit = legacy[(legacy["sku"] == sku) & (legacy["nation"] == nation) & (legacy["cost"] > 0)]
        if len(hit):
            return float(hit["cost"].iloc[0]), "精确SKU+国家"

    candidates = legacy[(legacy["nation"] == nation) & (legacy["w"] > 0) & (legacy["cost"] > 0)]
    if len(candidates) == 0:
        return 0.0, "无候选"

    best = None
    min_diff = float("inf")
    for weight, cost in zip(candidates["w"], candidates["cost"]):
        diff = abs(float(weight) - float(weight_kg))
        if diff < min_diff or (diff == min_diff and best is not None and float(weight) > best[0]):
            min_diff = diff
            best = (float(weight), float(cost))
    return (best[1], "重量兜底") if best else (0.0, "无候选")


def _error_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    error = predicted - actual
    return {
        "样本数": int(len(actual)),
        "MAE": round(float(error.abs().mean()), 2),
        "MdAE": round(float(error.abs().median()), 2),
        "偏差": round(float(error.mean()), 2),
        "P90绝对误差": round(float(error.abs().quantile(0.90)), 2),
        "中位绝对误差率%": round(float((error.abs() / actual.replace(0, pd.NA)).median() * 100), 1),
    }


def backtest_against_legacy(
    observations: pd.DataFrame,
    legacy: pd.DataFrame,
    publishable: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """用同一批订单比较 HLF0001 与分层模型的误差。

    只在「观测费用>0 且旧模型给出正预测」的包裹上比误差，避免用 0 预测刷低 MAE；
    旧模型覆盖率单独报告，不隐藏。
    """
    data = observations[observations["建模状态"] == "可建模"].copy()
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()

    legacy_pred = data.apply(
        lambda row: legacy_predict_fee_faithful(legacy, row["国家"], row["通途SKU"], row["观察重量_kg"]),
        axis=1,
    )
    data["旧模型预测"] = [p[0] for p in legacy_pred]
    data["旧模型命中方式"] = [p[1] for p in legacy_pred]
    data["新模型预测"] = _predict_with_tiers(data, publishable)

    def summarize(group: pd.DataFrame) -> pd.Series:
        both = group[(group["观察费用"] > 0) & (group["旧模型预测"] > 0)]
        new_ok = group[(group["观察费用"] > 0) & (group["新模型预测"] > 0)]
        old = _error_metrics(both["观察费用"], both["旧模型预测"]) if len(both) else {}
        new = _error_metrics(new_ok["观察费用"], new_ok["新模型预测"]) if len(new_ok) else {}
        return pd.Series(
            {
                "包裹数": len(group),
                "旧模型_有预测": int((group["旧模型预测"] > 0).sum()),
                "旧模型_精确匹配": int((group["旧模型命中方式"] == "精确SKU+国家").sum()),
                "旧模型_MAE": old.get("MAE"),
                "旧模型_MdAE": old.get("MdAE"),
                "旧模型_偏差": old.get("偏差"),
                "旧模型_P90": old.get("P90绝对误差"),
                "新模型_有预测": int((group["新模型预测"] > 0).sum()),
                "新模型_MAE": new.get("MAE"),
                "新模型_MdAE": new.get("MdAE"),
                "新模型_偏差": new.get("偏差"),
                "新模型_P90": new.get("P90绝对误差"),
            }
        )

    by_market = data.groupby("国家", dropna=False).apply(summarize, include_groups=False).reset_index()
    overall = summarize(data).to_frame().T
    return by_market, overall


def compare_holdout_precedence(
    observations: pd.DataFrame,
    legacy: pd.DataFrame,
    *,
    train_end_month: str = "202604",
    validation_start_month: str = "202605",
    min_samples: int = 30,
    min_months: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """在严格时间切分上比较 SKU、分区和渠道自适应三种 fallback 顺序。

    发布层只由 ``月份 <= train_end_month`` 的包裹生成；预测与指标只使用
    ``月份 >= validation_start_month`` 的包裹，避免此前全量拟合后原样回测的泄漏。
    渠道自适应方案仅对历史证据显示强分区的 M6180、US-FEDEX、星链采用
    分区优先，其余渠道采用 SKU 优先。
    """
    eligible = observations[observations["建模状态"] == "可建模"].copy()
    training = eligible[eligible["月份"].astype(str) <= train_end_month]
    validation = eligible[eligible["月份"].astype(str) >= validation_start_month].copy()
    if training.empty or validation.empty:
        return pd.DataFrame(), pd.DataFrame()

    sku_tiers = build_publishable_tiers(
        training,
        min_samples=min_samples,
        min_months=min_months,
        levels=PUBLISH_LEVELS,
        exclusive=False,
    )
    zone_tiers = build_publishable_tiers(
        training,
        min_samples=min_samples,
        min_months=min_months,
        levels=PUBLISH_LEVELS_ZONE_FIRST,
        exclusive=False,
    )
    validation["SKU优先"] = _predict_with_tiers(validation, sku_tiers, levels=PUBLISH_LEVELS)
    validation["分区优先"] = _predict_with_tiers(
        validation, zone_tiers, levels=PUBLISH_LEVELS_ZONE_FIRST
    )
    validation["渠道自适应"] = validation["SKU优先"]
    zoned = validation["标准渠道"].isin(STRONGLY_ZONED_CHANNELS)
    validation.loc[zoned, "渠道自适应"] = validation.loc[zoned, "分区优先"]

    legacy_pred = validation.apply(
        lambda row: legacy_predict_fee_faithful(
            legacy, row["国家"], row["通途SKU"], row["观察重量_kg"]
        ),
        axis=1,
    )
    validation["HLF0001"] = [value for value, _ in legacy_pred]
    validation["HLF0001命中方式"] = [method for _, method in legacy_pred]
    validation["目的地邮编首位"] = validation["美国ZIP3"].astype("string").str[0].fillna("")

    rows = []
    for scheme in ("HLF0001", "SKU优先", "分区优先", "渠道自适应"):
        predicted = validation[scheme]
        usable = (validation["观察费用"] > 0) & (predicted > 0)
        metrics = _error_metrics(validation.loc[usable, "观察费用"], predicted[usable]) if usable.any() else {}
        rows.append(
            {
                "方案": scheme,
                "训练截止月份": train_end_month,
                "验证起始月份": validation_start_month,
                "验证包裹数": len(validation),
                "有预测包裹数": int((predicted > 0).sum()),
                "覆盖率%": round(float((predicted > 0).mean() * 100), 1),
                **metrics,
            }
        )
    return validation, pd.DataFrame(rows)


def summarize_holdout_dimensions(detail: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """按关键业务维度输出 holdout 指标，供发布闸门审阅。"""
    if detail.empty:
        return {}

    def summarize(group_cols: list[str]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        grouped = [((), detail)] if not group_cols else detail.groupby(group_cols, dropna=False)
        for key, group in grouped:
            key = key if isinstance(key, tuple) else (key,)
            dimensions = dict(zip(group_cols, key))
            for scheme in ("HLF0001", "SKU优先", "分区优先", "渠道自适应"):
                predicted = group[scheme]
                usable = (group["观察费用"] > 0) & (predicted > 0)
                metrics = _error_metrics(group.loc[usable, "观察费用"], predicted[usable]) if usable.any() else {}
                rows.append(
                    {
                        **dimensions,
                        "方案": scheme,
                        "验证包裹数": len(group),
                        "有预测包裹数": int((predicted > 0).sum()),
                        "覆盖率%": round(float((predicted > 0).mean() * 100), 1),
                        **metrics,
                    }
                )
        return pd.DataFrame(rows)

    return {
        "00_总体": summarize([]),
        "01_国家仓库": summarize(["国家", "标准仓库"]),
        "02_渠道": summarize(["国家", "标准仓库", "标准渠道"]),
        "03_重量层": summarize(["国家", "标准仓库", "标准渠道", "观察重量阶梯"]),
        "04_目的地带": summarize(["国家", "标准仓库", "标准渠道", "目的地邮编首位"]),
    }


def _predict_with_tiers(
    data: pd.DataFrame,
    publishable: pd.DataFrame,
    *,
    levels: tuple[tuple[str, tuple[str, ...]], ...] = PUBLISH_LEVELS,
) -> pd.Series:
    """按指定的由细到粗层级取中位数，复刻候选线上 fallback 阶梯。"""
    out = pd.Series(0.0, index=data.index)
    if publishable is None or len(publishable) == 0:
        return out
    for level_name, cols in levels:
        level = publishable[publishable["匹配层级"] == level_name]
        if level.empty:
            continue
        lookup = dict(zip(_row_keys(level, list(cols), "\x1f"), level["中位数"]))
        keys = _row_keys(data, list(cols), "\x1f")
        hit = (out <= 0) & keys.isin(lookup)
        out = out.mask(hit, keys.map(lookup))
    return out


def write_history_last_leg_workbook(report: HistoryLastLegAnalysis, out_path: Path | str) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        report.reconciliation.to_excel(writer, sheet_name="00_对账", index=False)
        report.fee_sources.to_excel(writer, sheet_name="01_费用来源", index=False)
        report.monthly_regime.to_excel(writer, sheet_name="02_费率形态探测", index=False)
        report.monthly.to_excel(writer, sheet_name="03_月度趋势", index=False)
        report.channel_stats.to_excel(writer, sheet_name="04_仓库渠道", index=False)
        report.zone_gradient.to_excel(writer, sheet_name="05_分区梯度", index=False)
        report.tier_stats.to_excel(writer, sheet_name="06_ZIP3重量层", index=False)
        report.sku_stats.to_excel(writer, sheet_name="07_SKU候选层", index=False)
        report.publishable.to_excel(writer, sheet_name="08_可发布费率层", index=False)
        report.publish_coverage.to_excel(writer, sheet_name="09_发布覆盖率", index=False)
        report.observations.to_excel(writer, sheet_name="10_包裹观察", index=False)
        report.outliers.to_excel(writer, sheet_name="11_统计异常", index=False)
        report.skipped.to_excel(writer, sheet_name="12_跳过明细", index=False)
    return out_path
