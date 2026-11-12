# -*- coding: utf-8 -*-
"""服务分档（P2a）：ABC × XYZ → A/B/C/D → 分位政策。

只做纯函数，不读文件、不写文件；CLI 在 `scripts/build_service_policy_20261112.py`。
口径：
- ABC：2026 销量降序累计 80/15/5；跨过 80% 的那一件留在 A（A 实际可略超 80%）。
- XYZ：X=smooth，Y=intermittent，Z=lumpy/erratic/n/a 或 obsolescent/new/short/no_demand。
- A/B/C/D：A(X/Y)=A；A(Z)/B(X/Y)=B；B(Z)/C(X/Y)=C；其余（C(Z)、新品、淘汰、零销量）=D。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ABC_CUTS = (0.80, 0.95)
DEFAULT_PRESET = "balance"

# 三预设：class → 分位。balance 是 P2a 默认；control 压 B；service 抬 B/C。
PRESETS = {
    "balance": {
        "A": dict(service_level_prior=0.95, quantile=0.95,
                  quantile_label="q95", basis="A_balance_q95"),
        "B": dict(service_level_prior=0.90, quantile=0.90,
                  quantile_label="q90", basis="B_balance_q90"),
        "C": dict(service_level_prior=0.85, quantile=0.85,
                  quantile_label="q85", basis="C_balance_q85"),
        "D": dict(service_level_prior=0.85, quantile=0.85,
                  quantile_label="q85", basis="D_balance_fill_rate_proxy"),
    },
    "control": {
        "A": dict(service_level_prior=0.95, quantile=0.95,
                  quantile_label="q95", basis="A_control_q95"),
        "B": dict(service_level_prior=0.85, quantile=0.85,
                  quantile_label="q85", basis="B_control_q85"),
        "C": dict(service_level_prior=0.85, quantile=0.85,
                  quantile_label="q85", basis="C_control_q85"),
        "D": dict(service_level_prior=0.85, quantile=0.85,
                  quantile_label="q85", basis="D_control_fill_rate_proxy"),
    },
    "service": {
        "A": dict(service_level_prior=0.95, quantile=0.95,
                  quantile_label="q95", basis="A_service_q95"),
        "B": dict(service_level_prior=0.95, quantile=0.95,
                  quantile_label="q95", basis="B_service_q95"),
        "C": dict(service_level_prior=0.90, quantile=0.90,
                  quantile_label="q90", basis="C_service_q90"),
        "D": dict(service_level_prior=0.85, quantile=0.85,
                  quantile_label="q85", basis="D_service_fill_rate_proxy"),
    },
}
# 兼容 P2a：balance 即原 CLASS_QUANTILE
CLASS_QUANTILE = PRESETS["balance"]
SERVICE_CLASSES = tuple(CLASS_QUANTILE)
OVERRIDE_COLUMNS = ("sku", "pool", "preset_or_quantile", "reason", "owner", "as_of")


def assign_abc(sales: pd.Series) -> pd.Series:
    """按销量降序累计 80/15/5；返回 A/B/C，索引与输入一致。"""
    s = pd.to_numeric(sales, errors="coerce").fillna(0.0).clip(lower=0.0)
    out = pd.Series("C", index=s.index, dtype=object)
    total = float(s.sum())
    if total <= 0:
        return out
    order = s.sort_values(ascending=False, kind="mergesort").index
    cum = s.loc[order].cumsum() / total
    before = cum.shift(1).fillna(0.0)
    abc = np.where(before < ABC_CUTS[0], "A",
                   np.where(before < ABC_CUTS[1], "B", "C"))
    out.loc[order] = abc
    return out


def assign_xyz(sbc_class, demand_pattern) -> str:
    """X=smooth；Y=intermittent；其余（lumpy/erratic/n/a/新品/淘汰/短史）=Z。"""
    sc = str(sbc_class or "").strip().lower()
    dp = str(demand_pattern or "").strip().lower()
    if dp in ("obsolescent", "new", "short", "no_demand"):
        return "Z"
    if sc == "smooth":
        return "X"
    if sc == "intermittent":
        return "Y"
    return "Z"


def assign_service_class(abc: str, xyz: str, demand_pattern=None, sales_2026=0.0) -> str:
    """ABC×XYZ → A/B/C/D；零销量/新品/淘汰/短史直接 D。"""
    dp = str(demand_pattern or "").strip().lower()
    if float(sales_2026 or 0.0) <= 0 or dp in ("obsolescent", "new", "short", "no_demand"):
        return "D"
    a = str(abc).upper()
    x = str(xyz).upper()
    if a == "A" and x in ("X", "Y"):
        return "A"
    if (a == "A" and x == "Z") or (a == "B" and x in ("X", "Y")):
        return "B"
    if (a == "B" and x == "Z") or (a == "C" and x in ("X", "Y")):
        return "C"
    return "D"


def class_quantile(service_class: str) -> dict:
    """class → 分位政策；未知 class 抛错，不自动补。"""
    key = str(service_class or "").strip().upper()
    if key not in CLASS_QUANTILE:
        raise ValueError(f"未知 service_class：{service_class!r}；不得自动补档")
    return dict(CLASS_QUANTILE[key])


def get_preset(preset: str) -> dict:
    """预设名 → class→分位映射；未知预设抛错。"""
    key = str(preset or DEFAULT_PRESET).strip().lower()
    if key not in PRESETS:
        raise ValueError(f"未知 preset：{preset!r}；可选 {sorted(PRESETS)}")
    return PRESETS[key]


def preset_class_quantile(preset: str, service_class: str) -> dict:
    p = get_preset(preset)
    key = str(service_class or "").strip().upper()
    if key not in p:
        raise ValueError(f"未知 service_class：{service_class!r}；不得自动补档")
    return dict(p[key])


def resolve_override(value) -> dict:
    """覆盖值：preset 名 / q95|q90|q85|fill_rate / 0-1 数值。"""
    raw = str(value or "").strip()
    low = raw.lower()
    if low in PRESETS:
        return dict(kind="preset", preset=low)
    labels = {"q95": 0.95, "q90": 0.90, "q85": 0.85, "fill_rate": 0.85}
    if low in labels:
        return dict(kind="quantile", preset="custom", quantile=labels[low],
                    quantile_label=low, service_level_prior=labels[low],
                    basis=f"override_{low}" + ("_proxy" if low == "fill_rate" else ""))
    try:
        q = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"无法解析 override 值：{value!r}") from None
    if not 0 < q <= 1:
        raise ValueError(f"override 分位必须在 (0,1]：{value!r}")
    return dict(kind="quantile", preset="custom", quantile=q,
                quantile_label=f"q{round(q * 100)}",
                service_level_prior=q, basis=f"override_q{round(q * 100)}")


def apply_overrides(policy: pd.DataFrame, overrides: pd.DataFrame | None = None,
                    preset: str = DEFAULT_PRESET,
                    keys: tuple[str, ...] = ("product_id", "pool", "physical_form",
                                             "canonical_uom")) -> pd.DataFrame:
    """给 policy 加 preset/quantile 与 override 审计列。

    overrides 列：sku,pool,preset_or_quantile,reason,owner,as_of。
    override 按 sku×pool 作用到该 SKU×池下所有形态/UOM；任何未知键、重复键、
    空 reason/owner、非法值 → 抛错，不静默丢弃。
    """
    if "product_id" not in policy.columns and "sku" in policy.columns:
        policy = policy.rename(columns={"sku": "product_id"})
    for c in keys + ("class",):
        if c not in policy.columns:
            raise ValueError(f"policy 缺列：{c}")
    if policy.duplicated(list(keys)).any():
        raise ValueError("policy 完整键重复")
    get_preset(preset)
    out = policy.copy()
    base = [preset_class_quantile(preset, c) for c in out["class"]]
    out["preset"] = preset
    for field in ("service_level_prior", "quantile", "quantile_label", "basis"):
        out[field] = [b[field] for b in base]
    out["override_applied"] = False
    out["override_value"] = ""
    out["override_reason"] = ""
    out["override_owner"] = ""
    out["override_as_of"] = ""
    out["override_status"] = "none"
    if overrides is None or len(overrides) == 0:
        return out

    ov = overrides.copy()
    if "product_id" not in ov.columns and "sku" in ov.columns:
        ov = ov.rename(columns={"sku": "product_id"})
    missing = [c for c in ("product_id", "pool", "preset_or_quantile", "reason",
                           "owner", "as_of") if c not in ov.columns]
    if missing:
        raise ValueError(f"overrides 缺列：{missing}；要求 {OVERRIDE_COLUMNS}")
    if ov.duplicated(["product_id", "pool"]).any():
        raise ValueError("overrides 键重复（同一 sku×pool 只能一行）")
    pos: dict[tuple[str, str], list[int]] = {}
    for i, (p, pool) in enumerate(zip(out["product_id"], out["pool"])):
        pos.setdefault((str(p), str(pool)), []).append(i)
    for r in ov.itertuples(index=False):
        key = (str(r.product_id), str(r.pool))
        if key not in pos:
            raise ValueError(f"override 键不在 policy：{key}")
        if not str(r.reason).strip() or not str(r.owner).strip() or not str(r.as_of).strip():
            raise ValueError(f"override 必须填 reason/owner/as_of：{key}")
        resolved = resolve_override(r.preset_or_quantile)
        for i in pos[key]:
            out.at[i, "override_applied"] = True
            out.at[i, "override_value"] = str(r.preset_or_quantile)
            out.at[i, "override_reason"] = str(r.reason)
            out.at[i, "override_owner"] = str(r.owner)
            out.at[i, "override_as_of"] = str(r.as_of)
            if resolved["kind"] == "preset":
                q = preset_class_quantile(resolved["preset"], out.at[i, "class"])
                out.at[i, "preset"] = resolved["preset"]
                for field in ("service_level_prior", "quantile", "quantile_label", "basis"):
                    out.at[i, field] = q[field]
                out.at[i, "override_status"] = "applied_preset"
            else:
                out.at[i, "preset"] = "custom"
                out.at[i, "service_level_prior"] = resolved["service_level_prior"]
                out.at[i, "quantile"] = resolved["quantile"]
                out.at[i, "quantile_label"] = resolved["quantile_label"]
                out.at[i, "basis"] = resolved["basis"]
                out.at[i, "override_status"] = "applied_quantile"
    return out
