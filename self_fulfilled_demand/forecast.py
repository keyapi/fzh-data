# -*- coding: utf-8 -*-
"""自发货需求预测：原始销售 SKU（通途 SKU）× 完整月。

本模块**只做预测**，不重做订单管道、不做供应净额、不下单。

口径（2026-10-27，2026-10-29 补货决策包）
- 输入用已经验收的 ``en-demand-v1/canonical/demand_line_disposition.parquet``
  （GS 发货口径 2022-12 起 + EN 10 月增量），只取 ``in_main_series``。
- 单位 = **原始销售 SKU 的订单行件数**；不因历史 BOM / 发货形态未证而停止预测。
  预测资格（历史长度）与供应净额资格（canonical SKU / UOM / 仓库证据）**分开记录**。
- **不足月**：数据首/末月若不是整月（当前为 2022-12 与 2026-10），一律不进入拟合、
  不参与同比/趋势；单独作为分月观测输出，并显式标注。
- 未知不当 0：不可预测写 null + 原因；断货/无销量与「没算」区分。

模型（复用既有方案，不自造）
- 默认 **AutoETS**（statsforecast 2.1.1），规则来自 T5 / 工程裁定 A；
  T20 guard：``len<3 → naive 末值``、``3<=len<7 → MA3``、``len>=7 → AutoETS``；
  AutoETS 抛错（如 tiny datasets）→ **MA3 回退**，逐 SKU 写原因。
- 可选 ``model_policy="classified"``（默认关闭）：按 ``--model-map`` 的
  ``adopted_model`` 为每个 SKU 选模型（AutoETS / SeasonalNaive / Naive / MA3 /
  SBA / TSB / Croston 对照）；map 缺失或模型名不认识 → 按 ``demand_pattern``
  回退（smooth→AutoETS、intermittent→SBA、lumpy/obsolescent→TSB、
  new/short→MA3、no_demand→不拟合）；仍失败 → 现有 AutoETS 守卫。
  每 SKU 记录 ``selected_model`` / ``selection_source`` / ``model_failure_reason``。
- 回测：滚动原点、一步预测，报告所选方法的 WAPE / 偏差 / 原点数；
  同时并列 MA3 / naive / seasonal_naive 的 WAPE 作对照。
  选型**不**按回测结果切换（DECISIONS D19：没有干净留出块，现有证据不支持
  「选择流程 / AutoETS 更好」）；回测只用于透明度和区间尺度。
- 区间：滚动原点**有符号残差**的经验下/上分位（own >= 3 个原点），
  否则用池化相对误差系数（截顶 3×）；**不是已标定分位**，不承诺覆盖率。
- 分位：p10/p50/p90 之外新增 **q85/q90/q95**（窗口 + 月表），由同一批滚动
  有符号需求残差的上分位估计；样本不足用池化系数并标 ``quantile_method=pooled``。
  构造上保证 q85<=q90<=q95、p50<=q90，并由 ``validate_frames`` 断言。
- 仓库分配：SKU 级预测按该 SKU 最近 3 个完整月（2026-07..09）各 canonical 仓
  销量占比分配；无近 3 月销量时分配写 null（未知），不写 0。

产物（本地，不进 git）
- ``D:/Work/fzh-order-store/en-demand-v1/forecast/<run_id>/``
- ``forecast_sku_monthly.parquet`` / ``forecast_sku_windows.parquet``
- ``forecast_sku_warehouse_monthly.parquet`` / ``forecast_sku_warehouse_windows.parquet``
- ``forecast_sku_summary.parquet`` / ``forecast_sku_summary.csv``
- ``forecast_manifest.json`` / ``forecast_report.md``
- ``CURRENT`` 指针（上一次成功产物目录名）
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import math
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np
import pandas as pd

from . import censoring
from .store import now_iso

SCHEMA_VERSION = "en-demand-forecast-v1"
MODEL_RULE_VERSION = "autoets_m3_naive@t5+t20-2026-10-27"
# classified 选型只影响 ``model_policy="classified"``；默认 autoets 的行为与旧版逐字一致
MODEL_POLICY_VERSION = "classified-map+pattern@d5v6.8-2026-11-24"

DEFAULT_DISPOSITION = (
    "D:/Work/fzh-order-store/en-demand-v1/canonical/demand_line_disposition.parquet"
)
DEFAULT_COVERAGE = "D:/Work/fzh-order-store/en-demand-v1/canonical/sku_coverage.parquet"
DEFAULT_OUT_ROOT = "D:/Work/fzh-order-store/en-demand-v1/forecast"
DEFAULT_STOCK_OBS = (
    "D:/Work/fzh-order-store/en-demand-v1/stockout-censoring-2026-10-28/"
    "input_stock_status_daily.parquet"
)
DEFAULT_UOM_CACHE = (
    "D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet"
)

DECISION_DATE = date(2026, 10, 29)
LEADS = (60, 90, 120, 180)

MIN_MA3_LEN = 3
MIN_AUTOETS_LEN = 7
SEASON_LONG_FROM = 24  # >= 24 个完整月才用 season_length=12（与 T5 一致）

STATUS_OK = {
    "ok_autoets",
    "ok_fallback_ma3",
    "ok_short_ma3",
    "ok_short_naive",
    # classified 选型（新增，向后兼容：旧状态一个都不删）
    "ok_classified",
    "ok_classified_pattern",
    "ok_classified_no_demand",
    "ok_classified_fallback",
}
STATUS_NOT_FORECASTABLE = "not_forecastable"
STATUS_NO_HISTORY = "not_forecastable_no_complete_month"

INTERVAL_LEVEL = 0.80
INTERVAL_MAX_COEF = 3.0

RECENT_SHARE_MONTHS = 3

# --------------------------------------------------------------------------- #
# 分型选型（classified policy）
# --------------------------------------------------------------------------- #
MODEL_POLICY_AUTOETS = "autoets"
MODEL_POLICY_CLASSIFIED = "classified"
MODEL_POLICIES = (MODEL_POLICY_AUTOETS, MODEL_POLICY_CLASSIFIED)

# 模型池（规范化名）；croston 只作对照
MODEL_POOL = ("autoets", "snaive", "naive", "ma3", "sba", "tsb", "croston")
MODEL_LABELS = {
    "autoets": "AutoETS",
    "snaive": "SeasonalNaive",
    "naive": "Naive",
    "ma3": "MA3",
    "sba": "SBA（CrostonSBA）",
    "tsb": "TSB",
    "croston": "Croston（对照）",
    "none": "不拟合（no_demand）",
}
MODEL_ALIASES = {
    "autoets": "autoets",
    "ets": "autoets",
    "ets_ann": "autoets",  # D5/D3b 的 adopted_model 旧名
    "ets_aaa": "autoets",
    "snaive": "snaive",
    "seasonal_naive": "snaive",
    "seasonalnaive": "snaive",
    "naive": "naive",
    "naive_last": "naive",
    "last": "naive",
    "ma3": "ma3",
    "ma_3": "ma3",
    "window_average3": "ma3",
    "sba": "sba",
    "croston_sba": "sba",
    "crostonsba": "sba",
    "tsb": "tsb",
    "croston": "croston",
    "croston_classic": "croston",
    "crostonclassic": "croston",
    "none": "none",
}

# demand_pattern → 模型；"new"/"short" 走短史规则（MA3，不足 3 个月由 guard 兜底）
PATTERN_FALLBACK = {
    "smooth": "autoets",
    "intermittent": "sba",
    "lumpy": "tsb",
    "obsolescent": "tsb",
    "new": "ma3",
    "short": "ma3",
    "no_demand": "none",
}

MODEL_MAP_REQUIRED = ("product_id", "adopted_model", "demand_pattern")
MODEL_MAP_PREFERRED = ("pool", "physical_form", "canonical_uom")

QUANTILE_LEVELS = (0.85, 0.90, 0.95)
QUANTILE_OWN_MIN_ORIGINS = 3

SELECTION_MAP = "map"
SELECTION_PATTERN = "pattern"
SELECTION_GUARD = "guard"
SELECTION_FALLBACK = "fallback"
SELECTION_DEFAULT = "default"


# --------------------------------------------------------------------------- #
# 月份 / 窗口工具
# --------------------------------------------------------------------------- #
def ym_index(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def index_ym(i: int) -> str:
    y, m = divmod(i, 12)
    return f"{y:04d}-{m + 1:02d}"


def add_month(ym: str, k: int = 1) -> str:
    return index_ym(ym_index(ym) + k)


def month_last_day(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    nxt = date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def month_range(first: str, last: str) -> list[str]:
    return [index_ym(i) for i in range(ym_index(first), ym_index(last) + 1)]


def window_weights(start: date, days: int) -> dict[int, float]:
    """日历窗口落在每个自然月的比例（与 experiments/business_phase/build_iteration_v2.py
    的 ``window_weights`` 同一公式，T5 沿用）。"""
    end = start + timedelta(days=days)
    out: dict[int, float] = {}
    cur = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    while cur <= last:
        ms = date(cur // 12, cur % 12 + 1, 1)
        nm = date((cur + 1) // 12, (cur + 1) % 12 + 1, 1)
        s, e = max(start, ms), min(end, nm)
        if e > s:
            out[cur] = (e - s).days / (nm - ms).days
        cur += 1
    return out


def conformal_q(values: Sequence[float], level: float = INTERVAL_LEVEL) -> float:
    """滚动经验分位（共形式）；不承诺有限样本覆盖率（同 SK09/SC05 口径）。"""
    n = len(values)
    if n == 0:
        return 0.0
    lvl = min(1.0, math.ceil((n + 1) * level) / n)
    xs = sorted(float(v) for v in values)
    return xs[min(n - 1, math.ceil(lvl * (n - 1) - 1e-12))]


def _sha256(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _git_dirty() -> bool | None:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ForecastConfig:
    decision_date: date = DECISION_DATE
    leads: tuple[int, ...] = LEADS
    max_backtest_origins: int = 4
    interval_level: float = INTERVAL_LEVEL
    min_ma3_len: int = MIN_MA3_LEN
    min_autoets_len: int = MIN_AUTOETS_LEN
    season_long_from: int = SEASON_LONG_FROM
    recent_share_months: int = RECENT_SHARE_MONTHS
    skip_backtest: bool = False
    # 断货删失（默认关闭；生产保持不变）。flags 来自 stockout-censoring 产物。
    censoring: bool = False
    censoring_mode: str = "conservative"  # conservative | aggressive
    censoring_flags_path: str | None = None
    stock_observations_path: str | None = None
    uom_cache_path: str | None = None
    # 选型策略：autoets（默认，旧行为不变）| classified（按 model map + 分型选模型）
    model_policy: str = MODEL_POLICY_AUTOETS
    model_map_path: str | None = None


# --------------------------------------------------------------------------- #
# 分型选型：model map + demand_pattern 回退
# --------------------------------------------------------------------------- #
def normalize_model_name(value: Any) -> str | None:
    """把 D5/D3b/自定义表里的模型名规范到 ``MODEL_POOL``；未知返回 None。"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    key = str(value).strip().lower().replace(" ", "").replace("-", "_")
    if not key:
        return None
    return MODEL_ALIASES.get(key)


def normalize_pattern(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return "new" if key in ("new_product", "newproduct") else key


@dataclass(frozen=True)
class ModelMapEntry:
    """一个 product_id 的选型结果（多 pool/形态时已折叠成一条）。"""

    product_id: str
    model: str | None  # 规范化名；None = 表里的模型名不认识
    raw_model: str
    demand_pattern: str
    pool: str = ""
    physical_form: str = ""
    canonical_uom: str = ""
    candidates: int = 1
    ambiguous: bool = False


def _pick_model_map_row(g: pd.DataFrame) -> ModelMapEntry:
    """同一 product_id 多行时选一条：已知模型 > 非 none > hist_avg_3y 大 > 原顺序。"""
    if "hist_avg_3y" in g.columns:
        hist = pd.to_numeric(g["hist_avg_3y"], errors="coerce")
    else:
        hist = pd.Series([float("nan")] * len(g), index=g.index)
    known = g["_model"].notna() & (g["_model"] != "none")
    order = pd.DataFrame(
        {"_known": known.astype(int), "_hist": hist.values},
        index=g.index,
    ).sort_values(["_known", "_hist"], ascending=[False, False], kind="mergesort")
    row = g.loc[order.index[0]]
    distinct = set(g["_model"].dropna())
    return ModelMapEntry(
        product_id=str(row["product_id"]),
        model=row["_model"] if pd.notna(row["_model"]) else None,
        raw_model="" if pd.isna(row.get("adopted_model")) else str(row.get("adopted_model")),
        demand_pattern=normalize_pattern(row.get("demand_pattern")),
        pool="" if pd.isna(row.get("pool")) else str(row.get("pool")),
        physical_form="" if pd.isna(row.get("physical_form")) else str(row.get("physical_form")),
        canonical_uom="" if pd.isna(row.get("canonical_uom")) else str(row.get("canonical_uom")),
        candidates=int(len(g)),
        ambiguous=len(distinct) > 1,
    )


def load_model_map(path: str | Path) -> tuple[dict[str, ModelMapEntry], dict[str, Any]]:
    """读 model map（parquet/csv），按 product_id 折叠；返回 (map, meta)。

    必需列：``product_id`` / ``adopted_model`` / ``demand_pattern``；
    ``pool`` / ``physical_form`` / ``canonical_uom`` 用于来源记录（缺失不报错）。
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(p)
    elif suffix in (".csv", ".txt"):
        df = pd.read_csv(p)
    else:
        raise ValueError(f"model map 只支持 .parquet / .csv，收到 {p.suffix!r}")
    missing = [c for c in MODEL_MAP_REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"model map 缺必需列: {missing}")

    df = df.copy()
    df["product_id"] = df["product_id"].astype(str).str.strip()
    df = df[~df["product_id"].isin(("", "nan", "None"))].copy()
    df["_model"] = df["adopted_model"].map(normalize_model_name)
    df["demand_pattern"] = df["demand_pattern"].map(normalize_pattern)

    entries: dict[str, ModelMapEntry] = {}
    for pid, g in df.groupby("product_id", sort=False):
        entries[str(pid)] = _pick_model_map_row(g)

    model_counts: dict[str, int] = {}
    unknown = 0
    for e in entries.values():
        if e.model is None:
            unknown += 1
            model_counts[f"unknown:{e.raw_model}"] = model_counts.get(f"unknown:{e.raw_model}", 0) + 1
        else:
            model_counts[e.model] = model_counts.get(e.model, 0) + 1
    meta = {
        "path": str(p),
        "sha256": _sha256(p),
        "rows": int(len(df)),
        "products": len(entries),
        "unknown_model_products": unknown,
        "ambiguous_products": int(sum(1 for e in entries.values() if e.ambiguous)),
        "model_counts": dict(sorted(model_counts.items())),
        "collapse_rule": "per product_id: known model > non-none > hist_avg_3y desc > first row",
    }
    return entries, meta


def _pattern_model(
    pattern: str, n_history: int, cfg: ForecastConfig
) -> tuple[str | None, str]:
    """按 demand_pattern 回退；返回 (模型或 None, 原因)。"""
    p = normalize_pattern(pattern)
    if not p:
        return None, "无 demand_pattern"
    target = PATTERN_FALLBACK.get(p)
    if target is None:
        return None, f"分型 {pattern!r} 无回退规则"
    if target == "ma3" and n_history < cfg.min_ma3_len:
        return "naive", f"分型 {p} → naive（历史 {n_history} 个 < {cfg.min_ma3_len}）"
    return target, f"分型 {p} → {target}"


@dataclass(frozen=True)
class ModelChoice:
    model: str
    source: str
    reason: str
    pattern: str = ""
    product_id: str = ""


def choose_model(
    n_history: int,
    cfg: ForecastConfig,
    model_map: dict[str, ModelMapEntry] | None = None,
    product_id: str = "",
) -> ModelChoice:
    """选模型：map 优先，其次 demand_pattern，最后 T20/AutoETS 守卫。"""
    if cfg.model_policy != MODEL_POLICY_CLASSIFIED:
        return ModelChoice(
            "autoets", SELECTION_DEFAULT, "AutoETS 默认（T5/T20 规则，policy=autoets）"
        )

    entry = (model_map or {}).get(product_id) if product_id else None
    pattern = entry.demand_pattern if entry else ""

    # T20 短史守卫优先于任何 map（少样本无法支撑季节/间歇模型）
    if n_history < cfg.min_ma3_len:
        return ModelChoice(
            "naive",
            SELECTION_GUARD,
            f"完整月历史 {n_history} 个（<{cfg.min_ma3_len}）→ naive 末值（T20 guard）",
            pattern,
            product_id,
        )
    if n_history < cfg.min_autoets_len:
        return ModelChoice(
            "ma3",
            SELECTION_GUARD,
            f"完整月历史 {n_history} 个（{cfg.min_ma3_len}–{cfg.min_autoets_len - 1}）"
            "→ MA3（T20 短史规则）",
            pattern,
            product_id,
        )

    if entry is not None and entry.model is not None:
        why = (
            f"model map 指定 {entry.raw_model}"
            f"（pool={entry.pool or '?'} / {entry.physical_form or '?'}"
            f"{'，多行已折叠' if entry.ambiguous else ''}）"
        )
        return ModelChoice(entry.model, SELECTION_MAP, why, pattern, product_id)

    if entry is not None and entry.model is None:
        model, pat_reason = _pattern_model(pattern, n_history, cfg)
        if model is None:
            return ModelChoice(
                "autoets",
                SELECTION_GUARD,
                f"map 模型 {entry.raw_model!r} 不在模型池，且 {pat_reason} → AutoETS 守卫",
                pattern,
                product_id,
            )
        return ModelChoice(
            model,
            SELECTION_PATTERN,
            f"map 模型 {entry.raw_model!r} 不在模型池 → {pat_reason}",
            pattern,
            product_id,
        )

    model, pat_reason = _pattern_model(pattern, n_history, cfg)
    if model is None:
        return ModelChoice(
            "autoets",
            SELECTION_GUARD,
            f"无 model map（{pat_reason}）→ AutoETS 默认守卫",
            pattern,
            product_id,
        )
    return ModelChoice(model, SELECTION_PATTERN, f"无 model map → {pat_reason}", pattern, product_id)


# --------------------------------------------------------------------------- #
# 模型后端
# --------------------------------------------------------------------------- #
class Backend(Protocol):
    name: str
    version: str

    def forecast(self, y: np.ndarray, h: int, season_length: int) -> np.ndarray: ...


class StatsForecastBackend:
    """AutoETS（statsforecast 2.1.1）；导入失败时由调用方降级并写原因。"""

    name = "statsforecast"

    def __init__(self) -> None:
        from statsforecast import models as sfm

        self._sfm = sfm
        try:
            self.version = md.version("statsforecast")
        except Exception:  # pragma: no cover - 仅环境异常
            self.version = "unknown"

    def forecast(self, y: np.ndarray, h: int, season_length: int) -> np.ndarray:
        model = self._sfm.AutoETS(season_length=season_length)
        model.fit(np.asarray(y, dtype=np.float32))
        return np.asarray(model.predict(h=h)["mean"], dtype=float)


def load_backend() -> Backend | None:
    try:
        return StatsForecastBackend()
    except Exception:
        return None


def _ma3(y: np.ndarray) -> float:
    k = min(3, len(y))
    return float(np.mean(y[-k:])) if k else 0.0


def _snaive(y: np.ndarray, h: int, season_length: int = 12) -> np.ndarray:
    """季节 naive：重复上一个完整周期的末值；不足一个周期时退化为 naive。"""
    sl = int(season_length) if len(y) >= season_length else 1
    seq = np.asarray(y[-sl:], dtype=float)
    reps = int(math.ceil(h / sl))
    return np.tile(seq, reps)[:h]


def _named_forecast(model: str, y: np.ndarray, h: int, season_length: int) -> np.ndarray:
    """模型池里除 AutoETS 之外的模型。

    naive / snaive / ma3 用本地实现（离线、确定性）；sba / tsb / croston 用
    statsforecast 的 CrostonSBA / TSB / CrostonClassic（2.1.1）。
    """
    if model == "naive":
        return np.repeat(float(y[-1]), h)
    if model == "ma3":
        return np.repeat(_ma3(y), h)
    if model == "snaive":
        return _snaive(y, h, season_length)
    from statsforecast import models as sfm
    if model == "sba":
        obj = sfm.CrostonSBA()
    elif model == "tsb":
        # statsforecast 的 TSB 无默认参数；固定 0.1/0.1，与分类层口径一致
        obj = sfm.TSB(alpha_d=0.1, alpha_p=0.1)
    elif model == "croston":
        obj = sfm.CrostonClassic()
    else:  # pragma: no cover - 调用方已限制在模型池内
        raise ValueError(f"未知模型 {model!r}")
    obj.fit(np.asarray(y, dtype=np.float32))
    pred = np.asarray(obj.predict(h=h)["mean"], dtype=float).reshape(-1)
    if len(pred) != h:
        raise ValueError(f"预测长度 {len(pred)} != {h}")
    if not np.isfinite(pred).all():
        raise ValueError("预测含 NaN/inf")
    return pred


def _autoets_predict(
    y: np.ndarray, h: int, backend: Backend | None, cfg: ForecastConfig
) -> tuple[np.ndarray, str, str, bool]:
    """AutoETS 及其既有回退（T20）。返回 (pred, method, reason, clipped)。"""
    n = len(y)
    season_length = 12 if n >= cfg.season_long_from else 1
    if backend is None:
        return (
            np.repeat(_ma3(y), h),
            "ma3",
            "statsforecast 不可用 → MA3 回退（T20 规则）",
            False,
        )
    try:
        pred = backend.forecast(y, h, season_length=season_length)
        pred = np.asarray(pred, dtype=float).reshape(-1)
        if len(pred) != h:
            raise ValueError(f"预测长度 {len(pred)} != {h}")
        reason = (
            f"AutoETS（T5 规则默认，statsforecast {backend.version}，"
            f"season_length={season_length}）"
        )
        clipped = bool((pred < 0).any())
        if clipped:
            pred = np.clip(pred, 0.0, None)
            reason += "；负值已截零"
        return pred, "autoets", reason, clipped
    except Exception as exc:  # noqa: BLE001 - 逐 SKU 记录原因，不中断全表
        msg = f"{type(exc).__name__}: {str(exc)[:80]}"
        return (
            np.repeat(_ma3(y), h),
            "ma3",
            f"AutoETS 不可用（{msg}）→ MA3 回退（T20 规则）",
            False,
        )


def fit_predict_rule(
    y: np.ndarray,
    h: int,
    backend: Backend | None,
    cfg: ForecastConfig,
    model: str = "autoets",
) -> tuple[np.ndarray | None, str, str, bool]:
    """按冻结规则出预测。

    返回 ``(pred, method, reason, negative_clipped)``。``pred`` 为 None 表示不可算。

    ``model`` 只在 ``model_policy="classified"`` 时有意义；默认 ``autoets`` 时
    行为与原实现逐字一致。T20 短史守卫对所有模型都先生效。
    """
    n = len(y)
    if n == 0:
        return None, "none", "没有完整月历史", False
    if n < cfg.min_ma3_len:
        pred = np.repeat(float(y[-1]), h)
        return pred, "naive_last", f"完整月历史 {n} 个（<{cfg.min_ma3_len}）→ naive 末值（T20 guard）", False
    if n < cfg.min_autoets_len:
        pred = np.repeat(_ma3(y), h)
        return pred, "ma3", f"完整月历史 {n} 个（{cfg.min_ma3_len}–{cfg.min_autoets_len - 1}）→ MA3（T20 短史规则）", False

    requested = normalize_model_name(model) or "autoets"
    if requested == "none":
        return np.zeros(h), "none", "no_demand 分型 → 预测 0（不拟合）", False
    if requested == "autoets":
        return _autoets_predict(y, h, backend, cfg)

    season_length = 12 if n >= cfg.season_long_from else 1
    try:
        pred = _named_forecast(requested, y, h, season_length)
        clipped = bool((pred < 0).any())
        if clipped:
            pred = np.clip(pred, 0.0, None)
        reason = (
            f"{MODEL_LABELS.get(requested, requested)}（classified 选型，"
            f"season_length={season_length if requested in ('snaive', 'autoets') else 1}）"
        )
        if clipped:
            reason += "；负值已截零"
        return pred, requested, reason, clipped
    except Exception as exc:  # noqa: BLE001 - 逐 SKU 记录原因，不中断全表
        msg = f"{type(exc).__name__}: {str(exc)[:80]}"
        fb_pred, fb_method, fb_reason, fb_clipped = _autoets_predict(y, h, backend, cfg)
        label = MODEL_LABELS.get(requested, requested)
        return (
            fb_pred,
            fb_method,
            f"{label} 不可用（{msg}）→ {fb_reason}",
            fb_clipped,
        )


# --------------------------------------------------------------------------- #
# 数据装载
# --------------------------------------------------------------------------- #
DISPOSITION_COLUMNS = [
    "tongtool_sku",
    "demand_date",
    "quantity",
    "in_main_series",
    "fulfillment_scope",
    "canonical_warehouse",
    "canonical_sku",
    "mapping_status",
]


def load_disposition(path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """只取自发货主序列（``in_main_series`` + ``self_fulfilled_candidate``）。

    代发/3PL 有效需求保留在 canonical 层，但不进自发货预测；数量单独记账，
    不静默丢弃。FBA 与 unknown scope 本就不在 ``in_main_series``。
    """
    df = pd.read_parquet(path, columns=DISPOSITION_COLUMNS)
    meta: dict[str, Any] = {"input_rows": int(len(df))}
    df = df[df["in_main_series"].fillna(False).astype(bool)].copy()
    meta["main_rows"] = int(len(df))
    meta["main_units"] = float(pd.to_numeric(df["quantity"], errors="coerce").fillna(0).sum())

    is_self = df["fulfillment_scope"] == "self_fulfilled_candidate"
    meta["excluded_scope_rows"] = int((~is_self).sum())
    meta["excluded_scope_units"] = float(
        pd.to_numeric(df.loc[~is_self, "quantity"], errors="coerce").fillna(0).sum()
    )
    df = df[is_self].copy()

    null_sku = df["tongtool_sku"].isna() | (df["tongtool_sku"].astype(str).str.strip() == "")
    meta["null_sku_rows"] = int(null_sku.sum())
    meta["null_sku_units"] = float(
        pd.to_numeric(df.loc[null_sku, "quantity"], errors="coerce").fillna(0).sum()
    )
    df = df[~null_sku & df["demand_date"].notna()].copy()
    meta["used_rows"] = int(len(df))
    meta["used_units"] = float(pd.to_numeric(df["quantity"], errors="coerce").fillna(0).sum())
    df["tongtool_sku"] = df["tongtool_sku"].astype(str)
    df["demand_date"] = df["demand_date"].astype(str).str[:10]
    df["ym"] = df["demand_date"].str[:7]
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0.0)
    return df, meta


def resolve_month_boundary(df: pd.DataFrame) -> dict[str, Any]:
    """识别数据首/末不足月；返回完整月网格。"""
    first_date = str(df["demand_date"].min())
    last_date = str(df["demand_date"].max())
    first_month, last_month = first_date[:7], last_date[:7]
    partial: list[str] = []
    if first_date[8:10] != "01":
        partial.append(first_month)
    if last_date < month_last_day(last_month):
        partial.append(last_month)
    months = month_range(first_month, last_month)
    complete = [m for m in months if m not in partial]
    return {
        "first_date": first_date,
        "last_date": last_date,
        "first_month": first_month,
        "last_month": last_month,
        "partial_months": sorted(set(partial)),
        "complete_months": complete,
        "complete_month_first": complete[0] if complete else None,
        "complete_month_last": complete[-1] if complete else None,
    }


@dataclass
class SkuSeries:
    sku: str
    months: list[str]
    y: np.ndarray
    partial_observed: dict[str, float] = field(default_factory=dict)
    warehouses: list[str] = field(default_factory=list)


def build_series(
    df: pd.DataFrame, boundary: dict[str, Any]
) -> tuple[dict[str, SkuSeries], pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """构造每 SKU 的完整月序列、分月分仓销量、以及不足月观测。

    返回 ``(series, wh_month, partial_monthly, meta)``。
    """
    complete = boundary["complete_months"]
    comp = df[df["ym"].isin(complete)]
    part = df[~df["ym"].isin(complete)]

    monthly = comp.groupby(["tongtool_sku", "ym"], as_index=False)["quantity"].sum()
    wh_month = comp.groupby(
        ["tongtool_sku", "canonical_warehouse", "ym"], as_index=False, dropna=False
    )["quantity"].sum()
    wh_all = df.groupby(
        ["tongtool_sku", "canonical_warehouse"], as_index=False, dropna=False
    )["quantity"].sum()
    partial_monthly = part.groupby(["tongtool_sku", "ym"], as_index=False)["quantity"].sum()

    last_i = ym_index(boundary["complete_month_last"]) if complete else None
    series: dict[str, SkuSeries] = {}
    for sku, g in monthly.groupby("tongtool_sku", sort=True):
        present = dict(zip(g["ym"], g["quantity"].astype(float)))
        first_i = min(ym_index(m) for m in present)
        grid = [index_ym(i) for i in range(first_i, last_i + 1)] if last_i is not None else []
        y = np.array([float(present.get(m, 0.0)) for m in grid], dtype=float)
        series[sku] = SkuSeries(sku=sku, months=grid, y=y)

    # 没有任何完整月记录的 SKU 也保留（不可预测，但仍要出现在表里）
    all_skus = set(df["tongtool_sku"].unique())
    for sku in all_skus:
        if sku not in series:
            series[sku] = SkuSeries(sku=sku, months=[], y=np.array([], dtype=float))

    wh_by_sku: dict[str, list[str]] = {}
    for sku, wh in wh_all[["tongtool_sku", "canonical_warehouse"]].itertuples(index=False):
        wh_by_sku.setdefault(sku, []).append("" if pd.isna(wh) else str(wh))
    for sku, s in series.items():
        s.warehouses = sorted(w for w in wh_by_sku.get(sku, []) if w)

    part_by_sku: dict[str, dict[str, float]] = {}
    for sku, ym, q in partial_monthly.itertuples(index=False):
        part_by_sku.setdefault(sku, {})[ym] = float(q)
    for sku, s in series.items():
        s.partial_observed = part_by_sku.get(sku, {})

    meta = {
        "skus": len(series),
        "complete_monthly_rows": int(len(monthly)),
        "partial_monthly_rows": int(len(partial_monthly)),
        "complete_units": float(comp["quantity"].sum()),
        "partial_units": float(part["quantity"].sum()),
    }
    return series, wh_month, partial_monthly, meta


def product_by_sku_map(df: pd.DataFrame) -> dict[str, str]:
    """tongtool_sku → canonical_sku（= model map 的 product_id）。

    每个 tongtool_sku 只取出现次数最多的 canonical_sku；``unmapped:`` 值保留，
    自然不会命中 model map。
    """
    if "canonical_sku" not in df.columns:
        return {}
    sub = df[
        df["canonical_sku"].notna()
        & (df["canonical_sku"].astype(str).str.strip() != "")
    ]
    if not len(sub):
        return {}
    tmp = (
        sub.groupby(["tongtool_sku", "canonical_sku"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["tongtool_sku", "n"], ascending=[True, False], kind="mergesort")
        .drop_duplicates("tongtool_sku")
    )
    return {
        str(r.tongtool_sku): str(r.canonical_sku)
        for r in tmp.itertuples(index=False)
    }


# --------------------------------------------------------------------------- #
# 回测与预测
# --------------------------------------------------------------------------- #
@dataclass
class BacktestResult:
    n_origins: int = 0
    n_scored: int = 0
    window: str = ""
    wape: float | None = None
    bias: float | None = None
    errors: list[float] = field(default_factory=list)
    actuals: list[float] = field(default_factory=list)
    wape_ma3: float | None = None
    wape_naive: float | None = None
    wape_seasonal_naive: float | None = None
    wape_autoets: float | None = None
    zero_actual: int = 0
    underforecast_origins: int = 0  # actual > pred 的原点数
    overforecast_origins: int = 0  # actual < pred 的原点数
    censored_origins: int = 0  # 回测中实际发生补值的原点数
    imputed_points: int = 0  # 回测中实际补值的月点数
    imputed_units: float = 0.0  # 回测补值增加的训练单位


def _wape(errors: Sequence[float], actuals: Sequence[float]) -> float | None:
    denom = float(sum(actuals))
    if denom <= 1e-9:
        return None
    return float(sum(abs(e) for e in errors)) / denom


def run_backtest(
    y: np.ndarray,
    cfg: ForecastConfig,
    backend: Backend | None,
    first_month: str | None = None,
    y_actual: np.ndarray | None = None,
    y_train_raw: np.ndarray | None = None,
    months: list[str] | None = None,
    censoring_flags: dict[str, dict[str, Any]] | None = None,
    censoring_flags_by_origin: dict[str, dict[str, dict[str, Any]]] | None = None,
    censoring_mode: str = "conservative",
    model: str = "autoets",
) -> BacktestResult:
    """滚动一步回测。

    ``y`` 是训练序列（可含删失补值）；``y_actual`` 是评估真值（必须用原始 actual，
    默认与 y 相同）。补值只改变训练输入，不能改变回测真值。
    """
    n = len(y)
    actual_series = y if y_actual is None else np.asarray(y_actual, dtype=float)
    raw_train_series = y if y_train_raw is None else np.asarray(y_train_raw, dtype=float)
    if len(actual_series) != n or len(raw_train_series) != n:
        raise ValueError("y_actual / y_train_raw 长度必须与 y 一致")
    if (censoring_flags is not None or censoring_flags_by_origin is not None) and months is None:
        raise ValueError("启用删失回测时必须提供 months")
    if n < cfg.min_ma3_len + 1 or cfg.skip_backtest:
        return BacktestResult()
    origins = list(range(max(cfg.min_ma3_len, n - cfg.max_backtest_origins), n))
    res = BacktestResult()
    own_e: list[float] = []
    own_a: list[float] = []
    comp: dict[str, list[tuple[float, float]]] = {
        "ma3": [],
        "naive": [],
        "seasonal_naive": [],
        "autoets": [],
    }
    origin_months: list[str] = []
    base_i = ym_index(first_month) if first_month else None
    for i in origins:
        if i < 1:
            continue
        origin_month = months[i - 1] if months else ""
        if censoring_flags_by_origin is not None:
            # v5：flags 按原点只用当时可见库存重建；记录实际补值
            flags_i = censoring_flags_by_origin.get(origin_month, {})
            train, st = censoring.apply_as_of(
                months or [], raw_train_series, flags_i, i, censoring_mode
            )
            if st.replaced_months:
                res.censored_origins += 1
                res.imputed_points += st.replaced_months
                res.imputed_units += st.added_units
        elif censoring_flags is not None:
            # 每个原点只用当时可见数据重算补值，禁止全期/未来月份
            train, st = censoring.apply_as_of(
                months or [], raw_train_series, censoring_flags, i, censoring_mode
            )
            if st.replaced_months:
                res.censored_origins += 1
                res.imputed_points += st.replaced_months
                res.imputed_units += st.added_units
        else:
            train = y[:i]
        actual = float(actual_series[i])
        pred, method, _, _ = fit_predict_rule(train, 1, backend, cfg, model=model)
        if pred is None:
            continue
        own_e.append(float(pred[0]) - actual)
        own_a.append(actual)
        if actual > float(pred[0]) + 1e-12:
            res.underforecast_origins += 1
        elif actual < float(pred[0]) - 1e-12:
            res.overforecast_origins += 1
        if base_i is not None:
            origin_months.append(index_ym(base_i + i))
        if actual <= 1e-9:
            res.zero_actual += 1
        # 对照模型（同一训练窗，一步预测）
        comp["ma3"].append((_ma3(train) - actual, actual))
        comp["naive"].append((float(train[-1]) - actual, actual))
        if i >= 12:
            comp["seasonal_naive"].append((float(train[-12]) - actual, actual))
        if method == "autoets":
            comp["autoets"].append((float(pred[0]) - actual, actual))

    res.n_origins = len(own_e)
    res.n_scored = len(own_e)
    res.errors = own_e
    res.actuals = own_a
    if origin_months:
        res.window = f"{origin_months[0]}..{origin_months[-1]}"
    res.wape = _wape(own_e, own_a)
    denom = float(sum(own_a))
    res.bias = (float(sum(own_e)) / denom) if denom > 1e-9 else None
    for key, pairs in comp.items():
        if pairs:
            setattr(
                res,
                f"wape_{key}",
                _wape([p[0] for p in pairs], [p[1] for p in pairs]),
            )
    return res


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
@dataclass
class SkuForecast:
    sku: str
    status: str
    method: str
    reason: str
    method_version: str
    history_months: int
    history_start: str | None
    history_end: str | None
    history_nonzero: int
    history_units: float
    backtest: BacktestResult
    p50: np.ndarray | None
    p10: np.ndarray | None
    p90: np.ndarray | None
    negative_clipped: bool
    zero_forecast: bool
    demand_residual_q10: float | None = None
    demand_residual_q90: float | None = None
    # classified 选型溯源
    selected_model: str = ""
    selection_source: str = ""
    selection_reason: str = ""
    selected_pattern: str = ""
    product_id: str = ""
    model_failure_reason: str = ""
    # q85/q90/q95：滚动回测有符号残差的上分位（不是已标定分位）
    q85: np.ndarray | None = None
    q90: np.ndarray | None = None
    q95: np.ndarray | None = None
    demand_residual_q85: float | None = None
    demand_residual_upper_q90: float | None = None
    demand_residual_q95: float | None = None
    quantile_method: str = ""


def _demand_residual_quantiles(
    errors: Sequence[float], level: float
) -> tuple[float, float]:
    """把 ``pred−actual`` 误差转成需求残差 ``actual−pred`` 的下/上分位并截断。

    返回 ``(lo, hi)``，其中 ``lo<=0<=hi``，保证区间包含点预测。
    历史持续低估 → hi>0（上界扩张）；持续高估 → lo<0（下界扩张）。
    """
    demand_residual = [-float(e) for e in errors]  # pred-actual → actual-pred
    tail = (1.0 - level) / 2.0
    lo = min(0.0, conformal_q(demand_residual, tail))
    hi = max(0.0, conformal_q(demand_residual, 1.0 - tail))
    return lo, hi


def _interval_from_errors(
    errors: Sequence[float], p50: np.ndarray, level: float
) -> tuple[np.ndarray, np.ndarray]:
    """按**需求残差**（actual − pred）的经验分位生成区间。

    不是已标定分位，只作尺度参考。
    """
    lo, hi = _demand_residual_quantiles(errors, level)
    return np.clip(p50 + lo, 0.0, None), p50 + hi


def _upper_residual_quantile(errors: Sequence[float], level: float) -> float:
    """需求残差 actual−pred 的单侧上分位，截到 >=0（保证 q>=p50）。"""
    demand_residual = [-float(e) for e in errors]
    return max(0.0, conformal_q(demand_residual, level))


def _forecast_status(
    cfg: ForecastConfig, choice: ModelChoice, method: str, n: int
) -> str:
    """状态枚举；autoets policy 的分支与原实现逐字一致。"""
    if cfg.model_policy != MODEL_POLICY_CLASSIFIED:
        if method == "autoets":
            return "ok_autoets"
        if method == "ma3" and n < cfg.min_autoets_len:
            return "ok_short_ma3"
        if method == "ma3":
            return "ok_fallback_ma3"
        return "ok_short_naive"

    # naive_last 是 T20 对 1–2 个月历史的标准输出，等价于 naive 不算回退
    effective = "naive" if method == "naive_last" else method
    if choice.model != "none" and effective != choice.model:
        return "ok_classified_fallback"
    if choice.model == "none":
        return "ok_classified_no_demand"
    if choice.source == SELECTION_GUARD:
        if n < cfg.min_ma3_len:
            return "ok_short_naive"
        if n < cfg.min_autoets_len:
            return "ok_short_ma3"
        return "ok_autoets"
    if choice.source == SELECTION_MAP:
        return "ok_classified"
    return "ok_classified_pattern"


def forecast_sku(
    s: SkuSeries,
    months: list[str],
    cfg: ForecastConfig,
    backend: Backend | None,
    y_actual: np.ndarray | None = None,
    y_raw: np.ndarray | None = None,
    censoring_flags: dict[str, dict[str, Any]] | None = None,
    censoring_flags_by_origin: dict[str, dict[str, dict[str, Any]]] | None = None,
    censoring_mode: str = "conservative",
    model_map: dict[str, ModelMapEntry] | None = None,
    product_id: str = "",
) -> SkuForecast:
    n = len(s.y)
    if n == 0:
        return SkuForecast(
            sku=s.sku,
            status=STATUS_NO_HISTORY,
            method="none",
            reason="只有不足月观测或无完整月历史 → 不可算（不是 0）",
            method_version=MODEL_RULE_VERSION,
            history_months=0,
            history_start=None,
            history_end=None,
            history_nonzero=0,
            history_units=0.0,
            backtest=BacktestResult(),
            p50=None,
            p10=None,
            p90=None,
            negative_clipped=False,
            zero_forecast=False,
            selected_model="",
            selection_source="",
            selection_reason="无完整月历史 → 不选模型",
            product_id=product_id,
        )

    choice = choose_model(n, cfg, model_map, product_id)
    pred, method, reason, clipped = fit_predict_rule(
        s.y, len(months), backend, cfg, model=choice.model
    )
    assert pred is not None
    status = _forecast_status(cfg, choice, method, n)
    failure_reason = ""
    effective_method = "naive" if method == "naive_last" else method
    if choice.model != "none" and effective_method != choice.model:
        failure_reason = reason

    bt = run_backtest(
        s.y,
        cfg,
        backend,
        first_month=s.months[0],
        y_actual=y_actual,
        y_train_raw=y_raw,
        months=s.months,
        censoring_flags=censoring_flags,
        censoring_flags_by_origin=censoring_flags_by_origin,
        censoring_mode=censoring_mode,
        model=choice.model,
    )

    return SkuForecast(
        sku=s.sku,
        status=status,
        method=method,
        reason=reason,
        method_version=(
            MODEL_RULE_VERSION
            if cfg.model_policy != MODEL_POLICY_CLASSIFIED
            else f"{MODEL_RULE_VERSION}+{MODEL_POLICY_VERSION}"
        ),
        history_months=n,
        history_start=s.months[0],
        history_end=s.months[-1],
        history_nonzero=int(np.count_nonzero(s.y > 0)),
        history_units=float(s.y.sum()),
        backtest=bt,
        p50=np.asarray(pred, dtype=float),
        p10=None,
        p90=None,
        negative_clipped=clipped,
        zero_forecast=bool(np.allclose(pred, 0.0)),
        selected_model=choice.model,
        selection_source=choice.source,
        selection_reason=choice.reason,
        selected_pattern=choice.pattern,
        product_id=choice.product_id,
        model_failure_reason=failure_reason,
    )


def _allocate_interval(
    result: SkuForecast,
    pooled_coef: float | None,
    cfg: ForecastConfig,
    pooled_quantile_coef: dict[float, float | None] | None = None,
) -> None:
    if result.p50 is None:
        return
    if result.backtest.n_origins >= 3:
        lo, hi = _demand_residual_quantiles(
            result.backtest.errors, cfg.interval_level
        )
        result.demand_residual_q10 = lo
        result.demand_residual_q90 = hi
        result.p10 = np.clip(result.p50 + lo, 0.0, None)
        result.p90 = result.p50 + hi
        result.quantile_method = "own_rolling_residual_quantile"
        for level, arr_attr, val_attr in (
            (0.85, "q85", "demand_residual_q85"),
            (0.90, "q90", "demand_residual_upper_q90"),
            (0.95, "q95", "demand_residual_q95"),
        ):
            upper = _upper_residual_quantile(result.backtest.errors, level)
            setattr(result, val_attr, upper)
            setattr(result, arr_attr, result.p50 + upper)
    elif pooled_coef is not None:
        result.p10 = np.clip(result.p50 * (1.0 - pooled_coef), 0.0, None)
        result.p90 = result.p50 * (1.0 + pooled_coef)
        coefs = pooled_quantile_coef or {}
        usable = [c for c in coefs.values() if c is not None]
        result.quantile_method = "pooled" if usable else "insufficient_backtest"
        for level, arr_attr, val_attr in (
            (0.85, "q85", "demand_residual_q85"),
            (0.90, "q90", "demand_residual_upper_q90"),
            (0.95, "q95", "demand_residual_q95"),
        ):
            coef = coefs.get(level)
            if coef is None:
                continue
            # 池化系数是相对误差，不冒充本 SKU 的残差分位 → 残差列保持 None
            setattr(result, arr_attr, result.p50 * (1.0 + coef))
    else:
        result.quantile_method = "insufficient_backtest"
    # 都没有 → 保持 None（没有回测证据，不给假区间）


# --------------------------------------------------------------------------- #
# 产物组装
# --------------------------------------------------------------------------- #
def _uom_fields(c: pd.Series | None) -> tuple[str, str, str, bool]:
    """从 canonical 覆盖表取单位证据。

    返回 ``(canonical_uom, uom_status, uom_group, totals_allowed)``。
    只有 ``known_piece`` 且有具体单位才允许做同组求和；未知/非件类一律
    ``totals_allowed=False``，不得当「件」。
    """
    if c is None:
        return "", "netting_evidence_missing", "unknown", False
    raw_uom = c.get("uom")
    raw_status = c.get("uom_status")
    uom = "" if raw_uom is None or pd.isna(raw_uom) else str(raw_uom).strip()
    status = "" if raw_status is None or pd.isna(raw_status) else str(raw_status).strip()
    if status == "known_piece" and uom:
        return uom, status, uom, True
    if status == "not_piece":
        return uom, status, "not_piece", False
    return uom, status or "unknown", "unknown", False


def build_uom_totals(summary: pd.DataFrame, cfg: ForecastConfig) -> pd.DataFrame:
    """按已证 UOM 分组的总量表；未知单位单列且禁止当件。

    组内可以合计，**组间不得相加**。这里不提供全 SKU 统一合计行。
    """
    rows: list[dict[str, Any]] = []
    if not len(summary):
        return pd.DataFrame(rows)
    for group, g in summary.groupby("uom_group", sort=True):
        ok = g[g["forecast_eligible"]]
        net = ok[ok["netting_eligible"]]
        blocked = ok[~ok["netting_eligible"]]
        allowed = bool(ok["uom_totals_allowed"].all()) if len(ok) else False
        if group == "unknown":
            note = "UOM 未证：只是原始行计数，不得当件/套，也不得跨组相加"
        elif group == "not_piece":
            note = "非件类单位：订单行件数不能直接当该单位，不得与件类合计"
        else:
            note = "组内可合计；组间不得相加"
        for d in cfg.leads:
            total = float(ok[f"p50_l{d}"].sum()) if len(ok) else None
            total_lo = float(ok[f"p10_l{d}"].sum()) if len(ok) else None
            total_hi = float(ok[f"p90_l{d}"].sum()) if len(ok) else None
            net_sum = float(net[f"p50_l{d}"].sum()) if len(net) else None
            blocked_sum = float(blocked[f"p50_l{d}"].sum()) if len(blocked) else None
            share = (
                blocked_sum / total
                if (total is not None and blocked_sum is not None and total > 1e-9)
                else None
            )
            rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "uom_group": group,
                    "lead_days": d,
                    "skus": int(len(g)),
                    "forecastable_skus": int(len(ok)),
                    "p50_sum": None if total is None else round(total, 3),
                    "p10_sum": None if total_lo is None else round(total_lo, 3),
                    "p90_sum": None if total_hi is None else round(total_hi, 3),
                    "netting_eligible_skus": int(len(net)),
                    "netting_blocked_skus": int(len(blocked)),
                    "p50_sum_netting_eligible": None if net_sum is None else round(net_sum, 3),
                    "p50_sum_netting_blocked": None if blocked_sum is None else round(blocked_sum, 3),
                    "netting_blocked_share_within_uom": None if share is None else round(share, 4),
                    "totals_allowed": allowed,
                    "note": note,
                }
            )
    return pd.DataFrame(rows)


def zero_forecast_stats(summary: pd.DataFrame) -> dict[str, int]:
    """零预测与截零的准确交集（分母写清楚，避免把全表截零当子集）。"""
    ok = summary[summary["forecast_eligible"]]
    if not len(ok):
        return {
            "forecastable": 0,
            "zero_p50_l90": 0,
            "negative_clipped_all": int(summary["negative_clipped"].sum()),
            "zero_p50_and_clipped": 0,
            "positive_p50_and_clipped": 0,
            "zero_p50_with_p90_gt_0": 0,
            "zero_p50_clipped_with_p90_gt_0": 0,
            "zero_p50_with_p90_eq_0": 0,
        }
    zero = ok[ok["p50_l90"] <= 0]
    clipped_all = int(summary["negative_clipped"].sum())
    zero_clip = zero[zero["negative_clipped"]]
    pos_clip = ok[(ok["p50_l90"] > 0) & ok["negative_clipped"]]
    return {
        "forecastable": int(len(ok)),
        "zero_p50_l90": int(len(zero)),
        "negative_clipped_all": clipped_all,
        "zero_p50_and_clipped": int(len(zero_clip)),
        "positive_p50_and_clipped": int(len(pos_clip)),
        "zero_p50_with_p90_gt_0": int((zero["p90_l90"] > 0).sum()),
        "zero_p50_clipped_with_p90_gt_0": int((zero_clip["p90_l90"] > 0).sum()),
        "zero_p50_with_p90_eq_0": int((zero["p90_l90"] <= 0).sum()),
    }


def assemble(
    series: dict[str, SkuSeries],
    results: dict[str, SkuForecast],
    wh_month: pd.DataFrame,
    boundary: dict[str, Any],
    cfg: ForecastConfig,
    coverage: pd.DataFrame,
    censoring_stats: dict[str, censoring.CensorStats] | None = None,
) -> dict[str, pd.DataFrame]:
    complete_last = boundary["complete_month_last"]
    forecast_start = add_month(complete_last, 1)
    window_end = cfg.decision_date + timedelta(days=max(cfg.leads))
    horizon_last = f"{window_end.year:04d}-{window_end.month:02d}"
    n_h = ym_index(horizon_last) - ym_index(forecast_start) + 1
    if n_h <= 0:
        raise SystemExit("决策窗口早于预测起点，检查 decision-date / 数据截止")
    months = [index_ym(ym_index(forecast_start) + k) for k in range(n_h)]

    weights = {d: window_weights(cfg.decision_date, d) for d in cfg.leads}
    last_month = boundary["last_month"]
    partial_decision = (
        last_month if boundary["last_date"] < month_last_day(last_month) else None
    )
    partial_days = (
        int(boundary["last_date"][8:10]) if partial_decision is not None else None
    )
    partial_month_days = (
        int(month_last_day(partial_decision)[8:10]) if partial_decision else None
    )

    # 最近 N 个完整月（仓占比）
    char_months = [
        index_ym(i)
        for i in range(
            ym_index(complete_last) - cfg.recent_share_months + 1,
            ym_index(complete_last) + 1,
        )
    ]
    recent = wh_month[wh_month["ym"].isin(char_months)]
    recent_sku_total = recent.groupby("tongtool_sku")["quantity"].sum()

    cov = coverage.set_index("tongtool_sku", drop=False)

    summary_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    wh_month_rows: list[dict[str, Any]] = []
    wh_window_rows: list[dict[str, Any]] = []

    for sku in sorted(series):
        s = series[sku]
        r = results[sku]
        cst = (censoring_stats or {}).get(sku)
        c = cov.loc[sku] if sku in cov.index else None
        if c is None:
            netting_eligible = False
            netting_reason = "netting_evidence_missing"
            canonical_sku = ""
            mapping_status = ""
        else:
            ready = c["ready_rows"]
            blocked = c["blocked_rows"]
            netting_eligible = bool(
                pd.notna(ready) and pd.notna(blocked) and ready > 0 and blocked == 0
            )
            reason_val = c["block_reasons"]
            netting_reason = "" if netting_eligible or pd.isna(reason_val) else str(reason_val)
            csku = c["canonical_sku"]
            canonical_sku = "" if pd.isna(csku) else str(csku)
            mstat = c["mapping_status"]
            mapping_status = "" if pd.isna(mstat) else str(mstat)
        canonical_uom, uom_status, uom_group, uom_totals_allowed = _uom_fields(c)

        # 不足月观测（只对决策相关的不足月）
        part_units = s.partial_observed.get(partial_decision) if partial_decision else None
        part_rate = None
        if part_units is not None and partial_days and partial_month_days:
            part_rate = float(part_units) / partial_days * partial_month_days

        row: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "tongtool_sku": sku,
            "canonical_sku": canonical_sku,
            "mapping_status": mapping_status,
            "forecast_status": r.status,
            "forecast_eligible": r.status in STATUS_OK,
            "forecast_method": r.method,
            "forecast_method_reason": r.reason,
            "model_rule_version": r.method_version,
            "selected_model": r.selected_model,
            "selection_source": r.selection_source,
            "selection_reason": r.selection_reason,
            "selected_demand_pattern": r.selected_pattern,
            "model_map_product_id": r.product_id,
            "model_failure_reason": r.model_failure_reason,
            "quantile_method": r.quantile_method,
            "history_first_month": r.history_start,
            "history_last_month": r.history_end,
            "history_months": r.history_months,
            "history_nonzero_months": r.history_nonzero,
            "history_units_total": round(r.history_units, 3),
            "backtest_window": r.backtest.window,
            "backtest_origins": r.backtest.n_origins,
            "backtest_scored_cells": r.backtest.n_scored,
            "backtest_wape": None if r.backtest.wape is None else round(r.backtest.wape, 4),
            "backtest_bias": None if r.backtest.bias is None else round(r.backtest.bias, 4),
            "backtest_wape_ma3": None if r.backtest.wape_ma3 is None else round(r.backtest.wape_ma3, 4),
            "backtest_wape_naive": None if r.backtest.wape_naive is None else round(r.backtest.wape_naive, 4),
            "backtest_wape_seasonal_naive": None
            if r.backtest.wape_seasonal_naive is None
            else round(r.backtest.wape_seasonal_naive, 4),
            "backtest_wape_autoets": None
            if r.backtest.wape_autoets is None
            else round(r.backtest.wape_autoets, 4),
            "backtest_zero_actual": r.backtest.zero_actual,
            "backtest_censored_origins": r.backtest.censored_origins,
            "backtest_imputed_points": r.backtest.imputed_points,
            "backtest_imputed_units": round(r.backtest.imputed_units, 3),
            "backtest_underforecast_origins": r.backtest.underforecast_origins,
            "backtest_overforecast_origins": r.backtest.overforecast_origins,
            "backtest_residual_q10": (
                None if r.demand_residual_q10 is None else float(r.demand_residual_q10)
            ),
            "backtest_residual_q90": (
                None if r.demand_residual_q90 is None else float(r.demand_residual_q90)
            ),
            "backtest_residual_upper_q85": (
                None if r.demand_residual_q85 is None else float(r.demand_residual_q85)
            ),
            "backtest_residual_upper_q90": (
                None
                if r.demand_residual_upper_q90 is None
                else float(r.demand_residual_upper_q90)
            ),
            "backtest_residual_upper_q95": (
                None if r.demand_residual_q95 is None else float(r.demand_residual_q95)
            ),
            "canonical_uom": canonical_uom,
            "uom_status": uom_status,
            "uom_group": uom_group,
            "uom_totals_allowed": uom_totals_allowed,
            "interval_basis": (
                "own_rolling_residual_quantile"
                if (r.p50 is not None and r.p10 is not None and r.backtest.n_origins >= 3)
                else "pooled_relative_error"
                if (r.p50 is not None and r.p10 is not None)
                else "insufficient_backtest"
                if r.p50 is not None
                else None
            ),
            "interval_level_nominal": cfg.interval_level,
            "zero_forecast": r.zero_forecast,
            "negative_clipped": r.negative_clipped,
            "netting_eligible": netting_eligible,
            "netting_block_reason": netting_reason,
            "netting_evidence_available": c is not None,
            "censoring_applied": cst is not None,
            "censored_months": 0 if cst is None else cst.censored_months,
            "censored_zero_months": 0 if cst is None else cst.censored_zero_months,
            "censoring_replaced_months": 0 if cst is None else cst.replaced_months,
            "censoring_added_units": 0.0 if cst is None else round(cst.added_units, 3),
            "censoring_mode": cfg.censoring_mode if cfg.censoring else "",
            "data_cutoff": boundary["last_date"],
            "complete_month_max": complete_last,
            "partial_month": partial_decision,
            "partial_month_observed_units": None if part_units is None else round(float(part_units), 3),
            "partial_month_days": partial_days,
            "partial_month_month_days": partial_month_days,
            "partial_month_implied_full_rate": None if part_rate is None else round(part_rate, 3),
            "partial_month_note": (
                f"{partial_decision} 是不足月（{partial_days}/{partial_month_days} 天）："
                "不参与拟合/同比/趋势；implied_full_rate 只是线性折算，不是可比月"
                if partial_decision
                else ""
            ),
        }

        # 窗口预测
        window_series = (
            ("p50", r.p50),
            ("p10", r.p10),
            ("p90", r.p90),
            ("q85", r.q85),
            ("q90", r.q90),
            ("q95", r.q95),
        )
        for d in cfg.leads:
            if r.p50 is None:
                for name, _ in window_series:
                    row[f"{name}_l{d}"] = None
                continue
            idxs = list(weights[d])
            vals = []
            for name, arr in window_series:
                if arr is None:
                    vals.append(None)
                    continue
                missing = [
                    index_ym(i)
                    for i in idxs
                    if not (0 <= i - ym_index(forecast_start) < len(arr))
                ]
                if missing:
                    raise ValueError(
                        f"L{d} 窗口缺预测月 {missing}，拒绝静默截断"
                    )
                total = 0.0
                for i in idxs:
                    w = weights[d][i]
                    k = i - ym_index(forecast_start)
                    total += w * float(arr[k])
                vals.append(round(total, 3))
            for (name, _), v in zip(window_series, vals):
                row[f"{name}_l{d}"] = v

        summary_rows.append(row)

        # 月度预测
        for k, m in enumerate(months):
            if r.p50 is None:
                p50 = p10 = p90 = q85 = q90 = q95 = None
            else:
                p50 = round(float(r.p50[k]), 3)
                p10 = None if r.p10 is None else round(float(r.p10[k]), 3)
                p90 = None if r.p90 is None else round(float(r.p90[k]), 3)
                q85 = None if r.q85 is None else round(float(r.q85[k]), 3)
                q90 = None if r.q90 is None else round(float(r.q90[k]), 3)
                q95 = None if r.q95 is None else round(float(r.q95[k]), 3)
            monthly_rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "tongtool_sku": sku,
                    "forecast_month": m,
                    "horizon_index": k + 1,
                    "p50": p50,
                    "p10": p10,
                    "p90": p90,
                    "q85": q85,
                    "q90": q90,
                    "q95": q95,
                    "forecast_method": r.method,
                    "forecast_status": r.status,
                    "selected_model": r.selected_model,
                    "selection_source": r.selection_source,
                    "canonical_uom": canonical_uom,
                    "uom_group": uom_group,
                    "uom_totals_allowed": uom_totals_allowed,
                    "is_history_partial_month": m == partial_decision,
                    "month_note": (
                        f"{m} 的历史观测只有 {partial_days}/{partial_month_days} 天；"
                        "此整月预测不参与同比，也不把部分月当真值"
                        if m == partial_decision
                        else ""
                    ),
                    "data_cutoff": boundary["last_date"],
                }
            )

        # 窗口表（每个 SKU 一行 × lead）
        for d in cfg.leads:
            ws = cfg.decision_date
            we = ws + timedelta(days=d)
            window_rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "tongtool_sku": sku,
                    "lead_days": d,
                    "window_start": ws.isoformat(),
                    "window_end": we.isoformat(),
                    "p50": row.get(f"p50_l{d}"),
                    "p10": row.get(f"p10_l{d}"),
                    "p90": row.get(f"p90_l{d}"),
                    "q85": row.get(f"q85_l{d}"),
                    "q90": row.get(f"q90_l{d}"),
                    "q95": row.get(f"q95_l{d}"),
                    "forecast_method": r.method,
                    "forecast_status": r.status,
                    "selected_model": r.selected_model,
                    "selection_source": r.selection_source,
                    "quantile_method": r.quantile_method,
                    "canonical_uom": canonical_uom,
                    "uom_group": uom_group,
                    "uom_totals_allowed": uom_totals_allowed,
                    "history_months": r.history_months,
                    "backtest_origins": r.backtest.n_origins,
                    "backtest_wape": row["backtest_wape"],
                    "netting_eligible": netting_eligible,
                    "netting_block_reason": netting_reason,
                    "data_cutoff": boundary["last_date"],
                }
            )

        # 仓库分配
        total_recent = float(recent_sku_total.get(sku, 0.0))
        whs = list(dict.fromkeys(s.warehouses))
        share_basis = f"last_{cfg.recent_share_months}_complete_months({char_months[0]}..{char_months[-1]})"
        for wh in whs:
            if total_recent > 1e-9:
                mine = float(
                    recent[
                        (recent["tongtool_sku"] == sku)
                        & (recent["canonical_warehouse"].fillna("") == wh)
                    ]["quantity"].sum()
                )
                share = mine / total_recent
                alloc_status = "allocated_by_recent_share" if share > 0 else "zero_recent_share"
            else:
                share = None
                alloc_status = "no_recent_sales"
            for k, m in enumerate(months):
                if r.p50 is None or share is None:
                    p50 = p10 = p90 = q85 = q90 = q95 = None
                else:
                    p50 = round(float(r.p50[k]) * share, 3)
                    p10 = None if r.p10 is None else round(float(r.p10[k]) * share, 3)
                    p90 = None if r.p90 is None else round(float(r.p90[k]) * share, 3)
                    q85 = None if r.q85 is None else round(float(r.q85[k]) * share, 3)
                    q90 = None if r.q90 is None else round(float(r.q90[k]) * share, 3)
                    q95 = None if r.q95 is None else round(float(r.q95[k]) * share, 3)
                wh_month_rows.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "tongtool_sku": sku,
                        "canonical_warehouse": wh,
                        "forecast_month": m,
                        "p50": p50,
                        "p10": p10,
                        "p90": p90,
                        "q85": q85,
                        "q90": q90,
                        "q95": q95,
                        "allocation_share": None if share is None else round(share, 6),
                        "allocation_basis": share_basis,
                        "allocation_status": alloc_status,
                        "forecast_method": r.method,
                        "forecast_status": r.status,
                        "canonical_uom": canonical_uom,
                        "uom_group": uom_group,
                        "uom_totals_allowed": uom_totals_allowed,
                        "data_cutoff": boundary["last_date"],
                    }
                )
            for d in cfg.leads:
                sp50 = row.get(f"p50_l{d}")
                sp10 = row.get(f"p10_l{d}")
                sp90 = row.get(f"p90_l{d}")
                sq85 = row.get(f"q85_l{d}")
                sq90 = row.get(f"q90_l{d}")
                sq95 = row.get(f"q95_l{d}")
                wh_window_rows.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "tongtool_sku": sku,
                        "canonical_warehouse": wh,
                        "lead_days": d,
                        "window_start": cfg.decision_date.isoformat(),
                        "window_end": (cfg.decision_date + timedelta(days=d)).isoformat(),
                        "p50": None if (sp50 is None or share is None) else round(sp50 * share, 3),
                        "p10": None if (sp10 is None or share is None) else round(sp10 * share, 3),
                        "p90": None if (sp90 is None or share is None) else round(sp90 * share, 3),
                        "q85": None if (sq85 is None or share is None) else round(sq85 * share, 3),
                        "q90": None if (sq90 is None or share is None) else round(sq90 * share, 3),
                        "q95": None if (sq95 is None or share is None) else round(sq95 * share, 3),
                        "allocation_share": None if share is None else round(share, 6),
                        "allocation_status": alloc_status,
                        "forecast_status": r.status,
                        "canonical_uom": canonical_uom,
                        "uom_group": uom_group,
                        "uom_totals_allowed": uom_totals_allowed,
                        "netting_eligible": netting_eligible,
                        "netting_block_reason": netting_reason,
                    }
                )

    summary = pd.DataFrame(summary_rows)
    return {
        "forecast_sku_summary": summary,
        "forecast_sku_monthly": pd.DataFrame(monthly_rows),
        "forecast_sku_windows": pd.DataFrame(window_rows),
        "forecast_sku_warehouse_monthly": pd.DataFrame(wh_month_rows),
        "forecast_sku_warehouse_windows": pd.DataFrame(wh_window_rows),
        "forecast_uom_totals": build_uom_totals(summary, cfg),
        "_meta": pd.DataFrame(
            [
                {
                    "forecast_start_month": forecast_start,
                    "forecast_last_month": months[-1],
                    "horizon_months": n_h,
                    "partial_month": partial_decision,
                    "complete_month_last": complete_last,
                }
            ]
        ),
    }


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
class ValidationError(AssertionError):
    pass


NUMERIC_COLUMNS = {
    "p50",
    "p10",
    "p90",
    "q85",
    "q90",
    "q95",
    "allocation_share",
    "horizon_index",
    "lead_days",
    "history_units_total",
    "partial_month_observed_units",
    "partial_month_implied_full_rate",
    "netting_blocked_share_within_uom",
    "backtest_residual_q10",
    "backtest_residual_q90",
    "backtest_residual_upper_q85",
    "backtest_residual_upper_q90",
    "backtest_residual_upper_q95",
}


def _coerce_numeric(frames: dict[str, pd.DataFrame]) -> None:
    """把可空数值列统一成 float64；None 保留为 NaN，不被读成 0。"""
    for name, df in frames.items():
        if name.startswith("_"):
            continue
        for col in df.columns:
            if col in NUMERIC_COLUMNS or col.startswith(
                ("p50_", "p10_", "p90_", "q85_", "q90_", "q95_")
            ):
                df[col] = pd.to_numeric(df[col], errors="coerce")


def validate_frames(frames: dict[str, pd.DataFrame], cfg: ForecastConfig) -> list[str]:
    checks: list[str] = []
    summary = frames["forecast_sku_summary"]
    monthly = frames["forecast_sku_monthly"]
    windows = frames["forecast_sku_windows"]
    wh_month = frames["forecast_sku_warehouse_monthly"]

    required = {
        "tongtool_sku",
        "forecast_status",
        "forecast_method",
        "forecast_method_reason",
        "history_months",
        "data_cutoff",
        "partial_month",
    }
    missing = required - set(summary.columns)
    if missing:
        raise ValidationError(f"summary 缺列: {sorted(missing)}")
    checks.append("summary_columns")

    bad_status = set(summary["forecast_status"]) - STATUS_OK - {STATUS_NO_HISTORY}
    if bad_status:
        raise ValidationError(f"未知 forecast_status: {bad_status}")
    checks.append("status_enum")

    ok = summary[summary["forecast_eligible"]]
    if ok["p50_l90"].isna().any():
        raise ValidationError("可预测 SKU 的 p50_l90 不应为 null")
    checks.append("ok_has_forecast")

    # 区间顺序
    for d in cfg.leads:
        sub = summary.dropna(subset=[f"p10_l{d}", f"p50_l{d}", f"p90_l{d}"])
        if len(sub):
            if (sub[f"p10_l{d}"] > sub[f"p50_l{d}"] + 1e-6).any():
                raise ValidationError(f"p10_l{d} > p50_l{d}")
            if (sub[f"p50_l{d}"] > sub[f"p90_l{d}"] + 1e-6).any():
                raise ValidationError(f"p50_l{d} > p90_l{d}")
            if (sub[f"p10_l{d}"] < -1e-9).any():
                raise ValidationError(f"p10_l{d} 出现负值")
    checks.append("interval_order")

    # q85<=q90<=q95、p50<=q90：三张 SKU 级表都校验（旧产物无列时跳过）
    def _check_quantile_order(df: pd.DataFrame, cols: tuple[str, ...], label: str) -> None:
        if not all(c in df.columns for c in cols):
            return
        sub = df.dropna(subset=list(cols))
        if not len(sub):
            return
        if (sub[cols[0]] > sub[cols[1]] + 1e-6).any():
            raise ValidationError(f"{label}: {cols[0]} > {cols[1]}")
        if (sub[cols[1]] > sub[cols[2]] + 1e-6).any():
            raise ValidationError(f"{label}: {cols[1]} > {cols[2]}")
        if "p50" in sub.columns and (sub["p50"] > sub[cols[1]] + 1e-6).any():
            raise ValidationError(f"{label}: p50 > {cols[1]}")
        if (sub[cols[0]] < -1e-9).any():
            raise ValidationError(f"{label}: {cols[0]} 出现负值")

    for d in cfg.leads:
        _check_quantile_order(
            summary, (f"q85_l{d}", f"q90_l{d}", f"q95_l{d}"), f"summary L{d}"
        )
    _check_quantile_order(monthly, ("q85", "q90", "q95"), "monthly")
    _check_quantile_order(windows, ("q85", "q90", "q95"), "windows")
    if "quantile_method" in summary.columns:
        allowed_qm = {
            "own_rolling_residual_quantile",
            "pooled",
            "insufficient_backtest",
            "",
        }
        bad_qm = set(summary["quantile_method"].dropna()) - allowed_qm
        if bad_qm:
            raise ValidationError(f"未知 quantile_method: {bad_qm}")
    if "selection_source" in summary.columns:
        allowed_src = {
            SELECTION_MAP,
            SELECTION_PATTERN,
            SELECTION_GUARD,
            SELECTION_FALLBACK,
            SELECTION_DEFAULT,
            "",
        }
        bad_src = set(summary["selection_source"].dropna()) - allowed_src
        if bad_src:
            raise ValidationError(f"未知 selection_source: {bad_src}")
    for d in cfg.leads:
        pcol, qcol = f"p50_l{d}", f"q90_l{d}"
        if pcol in summary.columns and qcol in summary.columns:
            sub = summary.dropna(subset=[pcol, qcol])
            if len(sub) and (sub[pcol] > sub[qcol] + 1e-6).any():
                raise ValidationError(f"summary L{d}: p50 > q90")
    checks.append("quantile_order")

    # 不足月不能出现在历史月里
    if len(summary):
        bad = summary[
            summary["history_last_month"].notna()
            & (summary["history_last_month"] >= summary["partial_month"].fillna("9999-99"))
        ]
        if len(bad):
            raise ValidationError(f"不足月进入历史序列: {len(bad)} 行")
    checks.append("partial_month_excluded")

    # 仓占比：有近月销量的 SKU，每月份额和为 1
    if len(wh_month):
        known = wh_month.dropna(subset=["allocation_share"])
        grouped = known.groupby(["tongtool_sku", "forecast_month"])["allocation_share"].sum()
        bad = grouped[(grouped - 1.0).abs() > 1e-4]
        if len(bad):
            raise ValidationError(f"仓占比不归一: {len(bad)} 组")
        if (known["allocation_share"] < -1e-9).any():
            raise ValidationError("allocation_share 出现负值")
    checks.append("warehouse_share_sums_to_one")

    # 窗口 = 月度加权和（点预测与 q90/q95 同口径）
    if len(windows):
        for value_col in ("p50", "q90", "q95"):
            if value_col not in windows.columns or value_col not in monthly.columns:
                continue
            m = (
                monthly.dropna(subset=[value_col])
                .set_index(["tongtool_sku", "forecast_month"])[value_col]
            )
            for d in cfg.leads:
                w = {index_ym(i): v for i, v in window_weights(cfg.decision_date, d).items()}
                sub = windows[
                    (windows["lead_days"] == d) & windows[value_col].notna()
                ]
                for rec in sub.itertuples(index=False):
                    total = 0.0
                    for ym, wt in w.items():
                        key = (rec.tongtool_sku, ym)
                        if key in m.index:
                            total += wt * float(m.loc[key])
                    got = float(getattr(rec, value_col))
                    if abs(total - got) > max(0.02, abs(total) * 1e-6):
                        raise ValidationError(
                            f"窗口 {value_col} 不等于月度加权和: "
                            f"{rec.tongtool_sku} L{d}: {total} vs {got}"
                        )
    checks.append("windows_equal_weighted_months")

    # 区间方向：全部原点都低估时，需求上界必须高于点预测（高估同理下界）
    if len(ok):
        under = ok[
            (ok["backtest_origins"] >= 3)
            & (ok["backtest_underforecast_origins"] == ok["backtest_origins"])
        ]
        bad = under[under["backtest_residual_q90"] <= 0]
        if len(bad):
            raise ValidationError(f"持续低估但需求上残差分位未为正: {len(bad)} 行")
        over = ok[
            (ok["backtest_origins"] >= 3)
            & (ok["backtest_overforecast_origins"] == ok["backtest_origins"])
        ]
        bad_over = over[over["backtest_residual_q10"] >= 0]
        if len(bad_over):
            raise ValidationError(f"持续高估但需求下残差分位未为负: {len(bad_over)} 行")
    checks.append("interval_direction")

    # UOM 分组总量：只允许组内合计；未知单位禁止当件
    uom_totals = frames.get("forecast_uom_totals")
    if uom_totals is None or not len(uom_totals):
        raise ValidationError("缺 forecast_uom_totals")
    for col in ("uom_group", "lead_days", "p50_sum", "totals_allowed"):
        if col not in uom_totals.columns:
            raise ValidationError(f"forecast_uom_totals 缺列: {col}")
    for row in uom_totals.itertuples(index=False):
        if row.uom_group in ("unknown", "not_piece") and row.totals_allowed:
            raise ValidationError(f"未知/非件类单位被标为可合计: {row.uom_group}")
    for group, g in ok.groupby("uom_group"):
        for d in cfg.leads:
            sel = uom_totals[
                (uom_totals["uom_group"] == group) & (uom_totals["lead_days"] == d)
            ]
            if len(sel) != 1:
                raise ValidationError(f"UOM 总量行不唯一: {group} L{d}")
            expected = float(g[f"p50_l{d}"].sum())
            if abs(float(sel["p50_sum"].iloc[0]) - expected) > 0.01:
                raise ValidationError(
                    f"UOM 总量与 summary 不符: {group} L{d}: "
                    f"{sel['p50_sum'].iloc[0]} vs {expected}"
                )
    checks.append("uom_totals_match_summary")
    return checks


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def render_report(
    frames: dict[str, pd.DataFrame],
    manifest: dict[str, Any],
) -> str:
    s = frames["forecast_sku_summary"]
    meta = manifest["run"]
    total = len(s)
    n_ok = int(s["forecast_eligible"].sum())
    ok_df = s[s["forecast_eligible"]]
    nf = s[~s["forecast_eligible"]]
    by_status = s["forecast_status"].value_counts()
    by_method = s["forecast_method"].value_counts()
    bt = s[s["backtest_origins"] > 0]
    net_ok = int((s["netting_eligible"] & s["forecast_eligible"]).sum())
    net_blocked = int((~s["netting_eligible"] & s["forecast_eligible"]).sum())

    lines: list[str] = []
    lines.append("# 自发货需求预测刷新 — 2026-10-29 补货决策包")
    lines.append("")
    lines.append(f"> 生成：{manifest['generated_at']}　数据截止：**{meta['data_cutoff']}**")
    lines.append(
        f"> 完整月窗口：**{meta['complete_month_first']} .. {meta['complete_month_last']}**；"
        f"不足月：**{', '.join(meta['partial_months']) or '无'}**"
    )
    lines.append("")
    lines.append("## 0. 必读口径")
    lines.append("")
    if meta.get("partial_month"):
        lines.append(
            f"- **{meta['partial_month']} 是不足月**（数据只到 {meta['data_cutoff']}，"
            f"{meta['partial_month_days']}/{meta['partial_month_month_days']} 天）："
            "不进入拟合、不参与同比/趋势；只作为单列观测展示，`partial_month_implied_full_rate` "
            "是线性折算，不是可比月。"
        )
    else:
        lines.append(
            f"- 数据截止 {meta['data_cutoff']} 落在完整月末；本次没有决策相关不足月。"
        )
    part_obs = s.dropna(subset=["partial_month_observed_units"])
    if len(part_obs):
        groups = part_obs.groupby("uom_group")["partial_month_observed_units"].agg(["sum", "size"])
        detail = "；".join(
            f"`{g}` {row['sum']:,.0f}（{int(row['size'])} SKU）" for g, row in groups.iterrows()
        )
        lines.append(
            f"- 该不足月已观测：{detail}。这是**原始行计数、混合单位**，"
            "仅作单列观测，不参与任何完整月比较，也不得相加成统一件数。"
        )
    lines.append(
        "- **数据截止日**：所有数字都基于上述截止日；旧模型报告 / 旧试用包 / 旧预测不得当作本次结果。"
        "新订单增量 ≠ 新预测 —— 本文件才是新预测。"
    )
    lines.append(
        "- **预测资格 ≠ 供应净额资格**：能否预测只看完整月历史长度；"
        "能否与当前库存相减看 canonical 的 SKU/UOM/仓库证据（`netting_eligible`）。"
        "本文件不产生补货量，也不做供应净额。"
    )
    lines.append(
        "- **未知不当 0**：不可预测 → `p50=null` + 原因；无近 3 月销量的仓占比 → `allocation_share=null`。"
    )
    lines.append("")
    lines.append("## 1. 覆盖")
    lines.append("")
    lines.append(f"- SKU 总数：**{total:,}**；可预测：**{n_ok:,}**（{n_ok/total:.1%}）；不可预测：**{len(nf):,}**")
    lines.append(f"- 同时满足预测资格 + 净额资格：**{net_ok:,}**；可预测但净额被阻断：**{net_blocked:,}**")
    lines.append("")
    lines.append("### 方法分布（SKU）")
    lines.append("")
    lines.append("| 方法 | SKU 数 | 说明 |")
    lines.append("|---|---:|---|")
    method_note = {
        "autoets": "AutoETS（T5 规则默认）",
        "ma3": "MA3（短史或 AutoETS 回退）",
        "naive_last": "末值（<3 个完整月）",
        "naive": "Naive 末值（classified 选型）",
        "snaive": "SeasonalNaive（classified 选型）",
        "sba": "SBA / CrostonSBA（intermittent）",
        "tsb": "TSB（lumpy / obsolescent）",
        "croston": "Croston（对照）",
        "none": "不拟合 / 不可算",
    }
    for m, n in by_method.items():
        lines.append(f"| `{m}` | {n:,} | {method_note.get(m, '')} |")
    lines.append("")
    lines.append("### 状态分布")
    lines.append("")
    lines.append("| forecast_status | SKU 数 | 含义 |")
    lines.append("|---|---:|---|")
    status_note = {
        "ok_autoets": "AutoETS 成功",
        "ok_fallback_ma3": "AutoETS 不可用 → MA3",
        "ok_short_ma3": "3–6 个完整月 → MA3",
        "ok_short_naive": "1–2 个完整月 → 末值",
        "ok_classified": "classified：model map 指定模型成功",
        "ok_classified_pattern": "classified：按 demand_pattern 回退成功",
        "ok_classified_no_demand": "classified：no_demand → 预测 0（不拟合）",
        "ok_classified_fallback": "classified：所选模型不可用 → 已回退（见 model_failure_reason）",
        "not_forecastable_no_complete_month": "没有完整月历史",
        "not_forecastable": "其他不可算",
    }
    for st, n in by_status.items():
        lines.append(f"| `{st}` | {n:,} | {status_note.get(st, '')} |")
    lines.append("")

    if manifest.get("model", {}).get("policy") == MODEL_POLICY_CLASSIFIED:
        mm = manifest["model"].get("model_map", {})
        lines.append("### 选型溯源（classified）")
        lines.append("")
        if mm.get("provided"):
            lines.append(
                f"- model map：`{mm.get('path')}`（{mm.get('products', 0):,} 个 product_id / "
                f"{mm.get('rows', 0):,} 行；sha256 `{str(mm.get('sha256', ''))[:12]}…`）。"
            )
            lines.append(
                f"- SKU 命中：**{mm.get('matched_skus', 0):,}**；未命中 **{mm.get('unmatched_skus', 0):,}**；"
                f"未知模型名 product **{mm.get('unknown_model_products', 0):,}**；"
                f"多 pool/形态折叠 **{mm.get('ambiguous_products', 0):,}**。"
            )
            lines.append(f"- 折叠规则：{mm.get('collapse_rule', '')}。")
        else:
            lines.append(f"- 未提供 model map：{mm.get('note', '')}")
        sel = s["selected_model"].replace("", "(none)").value_counts()
        src = s["selection_source"].replace("", "(none)").value_counts()
        lines.append("")
        lines.append("| selected_model | SKU 数 | | selection_source | SKU 数 |")
        lines.append("|---|---:|---|---|---:|")
        sel_rows = list(sel.items())
        src_rows = list(src.items())
        for i in range(max(len(sel_rows), len(src_rows))):
            a = f"`{sel_rows[i][0]}` | {sel_rows[i][1]:,}" if i < len(sel_rows) else " | "
            b = f"`{src_rows[i][0]}` | {src_rows[i][1]:,}" if i < len(src_rows) else " | "
            lines.append(f"| {a} | | {b} |")
        fails = s[
            s["model_failure_reason"].fillna("").astype(str).str.len() > 0
        ]
        lines.append("")
        if len(fails):
            lines.append(
                f"- 所选模型不可用并已回退：**{len(fails):,}** 个 SKU（原因见 `model_failure_reason`）。"
            )
        else:
            lines.append("- 所选模型全部执行成功，无回退。")
        lines.append(
            "- q85/q90/q95 来自滚动回测的**有符号需求残差**上分位；"
            "`quantile_method=pooled` 表示样本不足、用池化系数，不是已校准分位。"
        )
        lines.append("")
    lines.append("## 2. 回测覆盖")
    lines.append("")
    if len(bt):
        lines.append(
            f"- 有回测的 SKU：**{len(bt):,}**；回测原点中位数 **{bt['backtest_origins'].median():.0f}**，"
            f"最大 **{int(bt['backtest_origins'].max())}**；一步预测评分格 **{int(bt['backtest_scored_cells'].sum()):,}**。"
        )
        w = bt["backtest_wape"].dropna()
        if len(w):
            lines.append(
                f"- 所选方法 WAPE（SKU 中位 / 均值）：**{w.median():.4f} / {w.mean():.4f}**；"
                f"有定义 WAPE 的 SKU **{len(w):,}**。"
            )
        lines.append(
            "- 回测是**滚动原点、一步预测**，不是独立留出；WAPE 不是准确率，也没有通用阈值。"
            "选型不按回测切换（DECISIONS D19）。"
        )
    else:
        lines.append("- 本次没有可评分回测（历史太短或 `--skip-backtest`）。")
    lines.append("")
    cens = manifest.get("model", {}).get("censoring", {})
    if cens.get("enabled"):
        app = s[s["censoring_applied"]]
        lines.append("### 2.1 断货删失适配（可选，默认关闭）")
        lines.append("")
        lines.append(
            f"- 模式：`{cens.get('mode')}`；flags：`{cens.get('path')}`"
            f"（sha256 `{str(cens.get('sha256',''))[:12]}…`）。"
        )
        lines.append(
            f"- 受影响 SKU：**{len(app):,}**；删失月 **{int(app['censored_months'].sum()):,}**"
            f"（其中销量=0 的 **{int(app['censored_zero_months'].sum()):,}**）。"
        )
        for grp, stat in sorted(cens.get("by_uom", {}).items()):
            lines.append(
                f"- `{grp}`：SKU {stat['skus']:,}，补值月 {stat['replaced_months']:,}，"
                f"补值增加 **{stat['added_units']:,.1f} {grp}**（不跨 UOM 合计）。"
            )
        bt = cens.get("backtest_imputation")
        if bt:
            lines.append(f"- 回测补值接线：allowed_skus **{bt['allowed_skus']:,}**（按 UOM 分列）。")
            for grp, stat in sorted(bt.get("by_uom", {}).items()):
                lines.append(
                    f"- 回测 `{grp}`：SKU {stat['skus']:,}，补值月点 {stat['imputed_points']:,}，"
                    f"增加训练单位 **{stat['imputed_units']:,.1f} {grp}**。"
                )
            lines.append(
                "- 回测补值月点按 origin 累计；同一训练月可能被多个原点重复计入，"
                "**不是独立新增销量/独立样本**。"
            )
        cov = cens.get("l180_coverage")
        if cov:
            lines.append(
                f"- L180 覆盖：窗口末 {cov['window_end']}，预测到 {cov['forecast_last_month']}"
                f"（{cov['horizon_months']} 个月，complete={cov['complete']}）。"
            )
        lines.append(
            "- 只改训练输入；观测销量是下界，补值是情景假设，**不生成损失销量**。"
        )
        lines.append("")
    lines.append("## 3. 预测窗口（按已证 UOM 分组；组间不得相加）")
    lines.append("")
    ut = frames["forecast_uom_totals"]
    # 每个 UOM 组取 L60/L90/L120 三行
    groups = sorted(ut["uom_group"].unique()) if len(ut) else []
    lines.append(
        "| 单位证据 | 可预测 SKU | L60 P50 | L90 P50 | L120 P50 | **L180 P50（情景）** | L90 净额通过/阻断 SKU | L90 组内阻断占比 | 可合计 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---|---:|---|")
    for g in groups:
        sub = ut[ut["uom_group"] == g]
        by_lead = {int(r.lead_days): r for r in sub.itertuples(index=False)}
        l60, l90, l120, l180 = (
            by_lead.get(60), by_lead.get(90), by_lead.get(120), by_lead.get(180)
        )
        if l90 is None:
            continue
        def _fmt(v):
            return "—" if v is None or pd.isna(v) else f"{float(v):,.3f}"
        share = (
            "—"
            if l90.netting_blocked_share_within_uom is None
            or pd.isna(l90.netting_blocked_share_within_uom)
            else f"{float(l90.netting_blocked_share_within_uom):.1%}"
        )
        lines.append(
            f"| `{g}` | {int(l90.forecastable_skus):,} | {_fmt(l60.p50_sum if l60 else None)} | "
            f"{_fmt(l90.p50_sum)} | {_fmt(l120.p50_sum if l120 else None)} | "
            f"{_fmt(l180.p50_sum if l180 else None)} | "
            f"{int(l90.netting_eligible_skus):,} / {int(l90.netting_blocked_skus):,} | {share} | "
            f"{'是' if bool(l90.totals_allowed) else '**否**'} |"
        )
    lines.append("")
    lines.append(
        "> 只有 `totals_allowed=是` 的组内可以合计；`unknown` 是**原始行计数（UOM 未证）**，"
        "不是「件」，不得参与跨组总量或占比。本报告**不提供**全 SKU 统一总量。"
    )
    lines.append("")
    z = zero_forecast_stats(s)
    lines.append("### 3.1 零预测（分母写清）")
    lines.append("")
    lines.append(
        f"- 可预测 SKU **{z['forecastable']:,}**；L90 P50=0 的 **{z['zero_p50_l90']:,}** 个。"
    )
    lines.append(
        f"- `negative_clipped=true` 全表 **{z['negative_clipped_all']:,}** 个（不全是零预测）；"
        f"其中 L90 P50=0 的只有 **{z['zero_p50_and_clipped']:,}** 个，"
        f"P50>0 的 **{z['positive_p50_and_clipped']:,}** 个。"
    )
    lines.append(
        f"- 在 {z['zero_p50_l90']:,} 个零预测中：P90>0 的 **{z['zero_p50_with_p90_gt_0']:,}** 个，"
        f"P90=0 的 **{z['zero_p50_with_p90_eq_0']:,}** 个；"
        f"其中「零预测且截零」子集 {z['zero_p50_and_clipped']:,} 个里 P90>0 的 "
        f"**{z['zero_p50_clipped_with_p90_gt_0']:,}** 个。"
    )
    lines.append(
        "- 零是模型输出：既不是未知（未知写 null），也不是「确认没有需求」；"
        "不能用当前未标定的区间替代业务判断。"
    )
    under_all = ok_df[
        (ok_df["backtest_origins"] >= 3)
        & (ok_df["backtest_underforecast_origins"] == ok_df["backtest_origins"])
    ]
    over_all = ok_df[
        (ok_df["backtest_origins"] >= 3)
        & (ok_df["backtest_overforecast_origins"] == ok_df["backtest_origins"])
    ]
    lines.append(
        f"- 方向校验：持续低估 **{len(under_all):,}** 个 SKU（全部需求上残差分位 >0），"
        f"持续高估 **{len(over_all):,}** 个（全部下残差分位 <0）；"
        "混合方向按各自分位，不做人工挑选。"
    )
    lines.append("")
    lines.append("### 3.2 L180 情景（只作情景，不承诺覆盖率/精度）")
    lines.append("")
    if 180 in [int(x) for x in ut["lead_days"].unique()]:
        w180 = frames["forecast_sku_windows"]
        w120 = w180[w180["lead_days"] == 120]
        ww180 = frames["forecast_sku_warehouse_windows"]
        ww120 = ww180[ww180["lead_days"] == 120]
        sku180 = w180[w180["lead_days"] == 180]
        wh180 = ww180[ww180["lead_days"] == 180]
        miss = len(set(w120["tongtool_sku"]) - set(sku180["tongtool_sku"]))
        extra = len(set(sku180["tongtool_sku"]) - set(w120["tongtool_sku"]))
        miss_wh = len(
            set(zip(ww120["tongtool_sku"], ww120["canonical_warehouse"]))
            - set(zip(wh180["tongtool_sku"], wh180["canonical_warehouse"]))
        )
        extra_wh = len(
            set(zip(wh180["tongtool_sku"], wh180["canonical_warehouse"]))
            - set(zip(ww120["tongtool_sku"], ww120["canonical_warehouse"]))
        )
        lines.append(
            f"- 窗口：{meta['decision_date']} → {meta['window_end'].get('180', '')}；"
            f"SKU 行 **{len(sku180):,}**、仓行 **{len(wh180):,}**。"
        )
        lines.append(
            f"- 与 L120 键覆盖：SKU 缺 {miss} / 多 {extra}；仓缺 {miss_wh} / 多 {extra_wh}。"
        )
        l180_rows = ut[ut["lead_days"] == 180]
        parts = []
        for row in l180_rows.sort_values("uom_group").itertuples(index=False):
            if row.p50_sum is None or pd.isna(row.p50_sum):
                continue
            parts.append(f"`{row.uom_group}` {float(row.p50_sum):,.3f}")
        if parts:
            lines.append("- L180 P50 组内合计（组间不得相加）：" + "；".join(parts) + "。")
        lines.append("")
        lines.append("| 窗口 | 有区间 SKU（个组） | 中位绝对宽度 P90−P10 | 中位相对宽度 /P50 |")
        lines.append("|---|---:|---:|---:|")
        pcs = ok_df[ok_df["uom_group"] == "个"]
        for d in meta["leads"]:
            cols = [f"p10_l{d}", f"p50_l{d}", f"p90_l{d}"]
            v = pcs.dropna(subset=cols)
            if not len(v):
                continue
            width = v[f"p90_l{d}"] - v[f"p10_l{d}"]
            rel = width[v[f"p50_l{d}"] > 0] / v.loc[v[f"p50_l{d}"] > 0, f"p50_l{d}"]
            label = f"L{d}" + ("（情景）" if d not in (60, 90, 120) else "")
            lines.append(
                f"| {label} | {len(v):,} | {width.median():,.2f} | "
                f"{rel.median():.1%} |"
            )
        lines.append("")
        lines.append(
            "> 180 天只有**一步**滚动的区间尺度，没有多步真值验证；宽度增长**不是**已证精度衰减，"
            "也不能当 80% 覆盖承诺。L180 仅作情景，决策包不得据此生成采购量。"
        )
    lines.append("")
    lines.append("## 4. 不可预测原因")
    lines.append("")
    if len(nf):
        reasons = nf["forecast_method_reason"].value_counts().head(10)
        lines.append("| 原因 | SKU 数 |")
        lines.append("|---|---:|")
        for reason, n in reasons.items():
            lines.append(f"| {reason} | {n:,} |")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 5. Top 20（按 L90 P50）")
    lines.append("")
    lines.append("| 通途 SKU | 单位 | 历史月数 | 方法 | 回测原点 | L90 P50 | P10–P90 | 净额资格 |")
    lines.append("|---|---|---:|---|---:|---:|---|---|")
    top = s[s["forecast_eligible"]].sort_values("p50_l90", ascending=False).head(20)
    for r in top.itertuples(index=False):
        rng = (
            "—"
            if pd.isna(r.p10_l90)
            else f"{r.p10_l90:,.0f}–{r.p90_l90:,.0f}"
        )
        lines.append(
            f"| `{r.tongtool_sku}` | `{r.uom_group}` | {r.history_months} | `{r.forecast_method}` | "
            f"{r.backtest_origins} | {r.p50_l90:,.0f} | {rng} | "
            f"{'是' if r.netting_eligible else '否'} |"
        )
    lines.append("")
    lines.append("## 6. 旧产物日期（不要混用）")
    lines.append("")
    lines.append("| 旧产物 | 日期 | 数据截止 | 状态 |")
    lines.append("|---|---|---|---|")
    for item in manifest.get("supersedes", []):
        lines.append(
            f"| {item['name']} | {item['date']} | {item['data_cutoff']} | {item['status']} |"
        )
    lines.append("")
    lines.append("## 7. 产物与消费")
    lines.append("")
    lines.append(f"- 目录：`{manifest['output_dir']}`（`CURRENT` 指向本次 run）")
    lines.append("- `forecast_sku_summary.parquet`：每 SKU 方法/原因/覆盖/区间/净额资格/不足月标注")
    lines.append("- `forecast_sku_windows.parquet`：SKU × L60/L90/L120")
    lines.append("- `forecast_sku_warehouse_monthly.parquet` / `..._windows.parquet`：SKU × canonical 仓")
    lines.append("- `forecast_sku_monthly.parquet`：SKU × 预测月")
    lines.append("- `forecast_manifest.json`：输入哈希、日期范围、模型参数、版本、生成时间")
    lines.append("")
    lines.append("完整字段说明见 `self_fulfilled_demand/docs/reference/forecast-interface.md`。")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def _version_of(name: str) -> str | None:
    try:
        return md.version(name)
    except Exception:
        return None


def run(
    disposition_path: str | Path = DEFAULT_DISPOSITION,
    coverage_path: str | Path = DEFAULT_COVERAGE,
    out_root: str | Path = DEFAULT_OUT_ROOT,
    cfg: ForecastConfig | None = None,
    run_id: str | None = None,
    backend: Backend | None | object = ...,
    update_current: bool = True,
) -> Path:
    """跑一次完整预测并写产物；返回本次 run 目录。"""
    cfg = cfg or ForecastConfig()
    if cfg.model_policy not in MODEL_POLICIES:
        raise SystemExit(
            f"未知 model_policy {cfg.model_policy!r}；允许 {list(MODEL_POLICIES)}"
        )
    if backend is ...:  # 默认自动加载；显式传 None 表示禁用 AutoETS
        backend = load_backend()

    disposition_path = Path(disposition_path)
    coverage_path = Path(coverage_path)
    out_root = Path(out_root)

    df, input_meta = load_disposition(disposition_path)
    boundary = resolve_month_boundary(df)
    if not boundary["complete_months"]:
        raise SystemExit("没有完整月可用于建模（数据全部落在不足月）")

    # classified 选型：model map（product_id = canonical_sku）+ 分型回退
    model_map: dict[str, ModelMapEntry] = {}
    product_by_sku: dict[str, str] = {}
    model_map_meta: dict[str, Any] = {
        "provided": False,
        "policy": cfg.model_policy,
    }
    if cfg.model_policy == MODEL_POLICY_CLASSIFIED:
        product_by_sku = product_by_sku_map(df)
        if cfg.model_map_path:
            model_map, stats = load_model_map(cfg.model_map_path)
            model_map_meta = {"provided": True, **stats}
        else:
            model_map_meta["note"] = (
                "未提供 --model-map：全部按 demand_pattern 回退；无分型 → AutoETS 守卫"
            )

    series, wh_month, partial_monthly, series_meta = build_series(df, boundary)
    coverage = pd.read_parquet(coverage_path)
    # 原始 actual 留作回测真值；删失补值只改训练序列
    raw_y = {sku: s.y.copy() for sku, s in series.items()} if cfg.censoring else {}

    # 断货删失适配层（默认关闭）：只改训练输入，不生成损失销量
    censoring_stats: dict[str, censoring.CensorStats] = {}
    censoring_meta: dict[str, Any] = {"enabled": False, "mode": cfg.censoring_mode}
    censor_flags_by_sku: dict[str, dict[str, dict[str, Any]]] = {}
    allowed_censoring_skus = 0
    if cfg.censoring:
        flags_path = cfg.censoring_flags_path or censoring.DEFAULT_FLAGS
        flags, flag_meta = censoring.load_flags(flags_path)
        censor_flags_by_sku = flags
        for sku, s in series.items():
            if sku not in flags:
                continue
            s.y, st = censoring.apply(s.months, s.y, flags[sku], cfg.censoring_mode)
            if st.censored_months:
                censoring_stats[sku] = st
        censoring_meta = censoring.as_json(flag_meta, cfg.censoring_mode, True)
        censoring_meta["backtest"] = {
            "actual": "raw_original",
            "imputation": "per_origin_visible_only",
            "note": "每个回测原点只用该 origin 之前的数据重算补值；不用全期/未来月份。",
        }
        censoring_meta["applied_skus"] = len(censoring_stats)
        censoring_meta["replaced_months"] = int(
            sum(s.replaced_months for s in censoring_stats.values())
        )
        censoring_meta["added_units"] = round(
            sum(s.added_units for s in censoring_stats.values()), 3
        )

    complete_last = boundary["complete_month_last"]
    forecast_start = add_month(complete_last, 1)
    window_end = cfg.decision_date + timedelta(days=max(cfg.leads))
    horizon_last = f"{window_end.year:04d}-{window_end.month:02d}"
    n_h = ym_index(horizon_last) - ym_index(forecast_start) + 1
    months = [index_ym(ym_index(forecast_start) + k) for k in range(n_h)]

    # v4：回测 flags 也按原点只用当时可见库存重建
    flags_by_origin_sku: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    if cfg.censoring:
        stock_obs_path = Path(cfg.stock_observations_path or DEFAULT_STOCK_OBS)
        stock_obs = pd.read_parquet(stock_obs_path)
        cov_map = coverage.set_index("tongtool_sku", drop=False)
        uom_cache = pd.read_parquet(
            Path(cfg.uom_cache_path or DEFAULT_UOM_CACHE)
        ).set_index("item_code")
        allowed = set()
        uom_conflicts: list[str] = []
        n_piece = n_tj = 0
        for sku in series:
            c = cov_map.loc[sku] if sku in cov_map.index else None
            _, _, ug, _ = _uom_fields(c)
            if ug == "个":
                allowed.add(sku)
                n_piece += 1
            elif ug == "套":
                item = "" if c is None or pd.isna(c.get("canonical_sku")) else str(c.get("canonical_sku"))
                row = uom_cache.loc[item] if item in uom_cache.index else None
                is_stock = None if row is None else row.get("is_stock_item")
                if censoring.tj_bundle_allowed(item, is_stock):
                    allowed.add(sku)
                    n_tj += 1
                else:
                    uom_conflicts.append(sku)
        if not allowed:
            raise SystemExit(
                "censoring allowed_skus=0：coverage 接线失败，拒绝静默不补值"
            )
        allowed_censoring_skus = len(allowed)
        censoring_meta["uom_eligibility"] = {
            "known_piece_skus": n_piece,
            "tj_set_skus": n_tj,
            "uom_conflict_skus": uom_conflicts,
            "allowed_skus": len(allowed),
            "rule": "个（known_piece）+ 仅 TJ#（stock_uom=套, is_stock_item=0）；非 TJ# 的套为冲突，不进入 allowed",
        }
        origin_months: set[str] = set()
        for s in series.values():
            n = len(s.months)
            if n < cfg.min_ma3_len + 1:
                continue
            idxs = range(max(cfg.min_ma3_len, n - cfg.max_backtest_origins), n)
            origin_months.update(s.months[i - 1] for i in idxs)
        asof_flags = {
            m: censoring.rebuild_flags_as_of(
                stock_obs, month_last_day(m), allowed
            )
            for m in sorted(origin_months)
        }
        for sku, s in series.items():
            n = len(s.months)
            if n < cfg.min_ma3_len + 1:
                continue
            idxs = range(max(cfg.min_ma3_len, n - cfg.max_backtest_origins), n)
            flags_by_origin_sku[sku] = {
                s.months[i - 1]: asof_flags[s.months[i - 1]].get(sku, {})
                for i in idxs
            }
        censoring_meta["stock_observations"] = {
            "path": str(stock_obs_path),
            "sha256": _sha256(stock_obs_path),
        }
        censoring_meta["backtest_flags"] = "rebuilt_as_of_origin_from_raw_inventory"
        censoring_meta["flag_rebuild_origins"] = len(origin_months)

    results: dict[str, SkuForecast] = {}
    for sku in sorted(series):
        results[sku] = forecast_sku(
            series[sku],
            months,
            cfg,
            backend,
            y_actual=raw_y.get(sku) if cfg.censoring else None,
            y_raw=raw_y.get(sku) if cfg.censoring else None,
            censoring_flags=censor_flags_by_sku.get(sku) if cfg.censoring else None,
            censoring_flags_by_origin=(
                flags_by_origin_sku.get(sku) if cfg.censoring else None
            ),
            censoring_mode=cfg.censoring_mode,
            model_map=model_map,
            product_id=product_by_sku.get(sku, ""),
        )

    if cfg.censoring:
        bt_applied = [r for r in results.values() if r.backtest.imputed_points > 0]
        if not bt_applied:
            raise SystemExit(
                "censoring 已启用但回测未发生任何补值：接线失败，拒绝静默"
            )

    # 池化相对误差（只用自己 >=3 个原点的 SKU）
    pooled_rel: list[float] = []
    for r in results.values():
        if r.backtest.n_origins >= 3:
            for e, a in zip(r.backtest.errors, r.backtest.actuals):
                if a > 1e-9:
                    pooled_rel.append(abs(e) / a)
    pooled_coef = (
        min(INTERVAL_MAX_COEF, conformal_q(pooled_rel, cfg.interval_level))
        if len(pooled_rel) >= 3
        else None
    )
    # q85/q90/q95 的池化系数（样本不足时用；标注 quantile_method=pooled）
    pooled_quantile_coef: dict[float, float | None] = {
        lvl: (
            min(INTERVAL_MAX_COEF, conformal_q(pooled_rel, lvl))
            if len(pooled_rel) >= 3
            else None
        )
        for lvl in QUANTILE_LEVELS
    }
    for r in results.values():
        _allocate_interval(r, pooled_coef, cfg, pooled_quantile_coef)

    if cfg.model_policy == MODEL_POLICY_CLASSIFIED:
        matched = sum(1 for sku in series if product_by_sku.get(sku) in model_map)
        model_map_meta["matched_skus"] = matched
        model_map_meta["unmatched_skus"] = len(series) - matched
        model_map_meta["skus_with_product_id"] = sum(
            1 for sku in series if product_by_sku.get(sku)
        )

    frames = assemble(
        series, results, wh_month, boundary, cfg, coverage, censoring_stats
    )
    _coerce_numeric(frames)
    checks = validate_frames(frames, cfg)

    run_id = run_id or datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[dict[str, Any]] = []
    for name in (
        "forecast_sku_summary",
        "forecast_sku_monthly",
        "forecast_sku_windows",
        "forecast_sku_warehouse_monthly",
        "forecast_sku_warehouse_windows",
        "forecast_uom_totals",
    ):
        path = out_dir / f"{name}.parquet"
        frames[name].to_parquet(path, index=False)
        outputs.append(
            {"file": path.name, "rows": int(len(frames[name])), "sha256": _sha256(path)}
        )
    csv_path = out_dir / "forecast_sku_summary.csv"
    frames["forecast_sku_summary"].to_csv(csv_path, index=False, encoding="utf-8-sig")
    outputs.append({"file": csv_path.name, "rows": int(len(frames["forecast_sku_summary"])), "sha256": _sha256(csv_path)})

    meta_row = frames["_meta"].iloc[0].to_dict()
    if cfg.censoring:
        cs = frames["forecast_sku_summary"]
        app = cs[cs["censoring_applied"]]
        by_uom: dict[str, dict[str, Any]] = {}
        for grp, sub in app.groupby("uom_group"):
            by_uom[str(grp)] = {
                "skus": int(len(sub)),
                "censored_months": int(sub["censored_months"].sum()),
                "censored_zero_months": int(sub["censored_zero_months"].sum()),
                "replaced_months": int(sub["censoring_replaced_months"].sum()),
                "added_units": round(float(sub["censoring_added_units"].sum()), 3),
            }
        censoring_meta["by_uom"] = by_uom
        # 回测补值也按 UOM 分列；月点跨原点重复，不是独立新增销量
        bt = cs[cs["backtest_imputed_points"] > 0]
        bt_by_uom: dict[str, dict[str, Any]] = {}
        for grp, sub in bt.groupby("uom_group"):
            bt_by_uom[str(grp)] = {
                "skus": int(len(sub)),
                "imputed_points": int(sub["backtest_imputed_points"].sum()),
                "imputed_units": round(float(sub["backtest_imputed_units"].sum()), 3),
            }
        censoring_meta["backtest_imputation"] = {
            "allowed_skus": int(allowed_censoring_skus),
            "by_uom": bt_by_uom,
            "points_repeat_across_origins": True,
            "not_independent_sales": True,
            "note": "补值月点按回测原点累计；同一训练月可能被多个原点重复计入，不是独立新增销量/样本。",
        }
        # 不提供跨 UOM 的 added_units 合计
        censoring_meta.pop("replaced_months", None)
        censoring_meta.pop("added_units", None)
        if 180 in cfg.leads:
            censoring_meta["l180_coverage"] = {
                "window_end": (cfg.decision_date + timedelta(days=180)).isoformat(),
                "forecast_last_month": months[-1],
                "horizon_months": n_h,
                "complete": bool(months[-1] >= horizon_last),
            }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": now_iso(),
        "output_dir": str(out_dir),
        "run": {
            "decision_date": cfg.decision_date.isoformat(),
            "window_end": {str(d): (cfg.decision_date + timedelta(days=d)).isoformat() for d in cfg.leads},
            "data_cutoff": boundary["last_date"],
            "first_date": boundary["first_date"],
            "complete_month_first": boundary["complete_month_first"],
            "complete_month_last": boundary["complete_month_last"],
            "partial_months": boundary["partial_months"],
            "partial_month": meta_row["partial_month"],
            "partial_month_days": (
                int(boundary["last_date"][8:10])
                if meta_row["partial_month"] is not None
                else None
            ),
            "partial_month_month_days": (
                int(month_last_day(boundary["last_date"][:7])[8:10])
                if meta_row["partial_month"] is not None
                else None
            ),
            "forecast_start_month": meta_row["forecast_start_month"],
            "forecast_last_month": meta_row["forecast_last_month"],
            "horizon_months": int(meta_row["horizon_months"]),
            "leads": list(cfg.leads),
        },
        "model": {
            "rule_version": MODEL_RULE_VERSION,
            "policy": cfg.model_policy,
            "policy_version": (
                MODEL_POLICY_VERSION
                if cfg.model_policy == MODEL_POLICY_CLASSIFIED
                else None
            ),
            "model_pool": list(MODEL_POOL),
            "pattern_fallback": dict(PATTERN_FALLBACK),
            "model_map": model_map_meta,
            "default": "AutoETS (statsforecast)",
            "guards": {
                "naive_if_len_lt": cfg.min_ma3_len,
                "ma3_if_len_lt": cfg.min_autoets_len,
                "season_length_12_if_len_ge": cfg.season_long_from,
                "autoets_failure_fallback": "MA3",
            },
            "backtest": {
                "scheme": "rolling_origin_1step",
                "max_origins": cfg.max_backtest_origins,
                "min_train_len": cfg.min_ma3_len,
                "skipped": cfg.skip_backtest,
            },
            "interval": {
                "nominal_level": cfg.interval_level,
                "own_min_origins": 3,
                "pooled_fallback": "relative_error_quantile_clipped_3x",
                "calibrated": False,
                "note": (
                    "按需求残差 actual−pred 的经验下/上分位（run_backtest 存 pred−actual，"
                    "生成区间时取反）；滚动经验/共形式，不承诺有限样本覆盖率，不是已标定分位"
                ),
            },
            "quantiles": {
                "levels": list(QUANTILE_LEVELS),
                "columns": ["q85", "q90", "q95"],
                "own_min_origins": QUANTILE_OWN_MIN_ORIGINS,
                "own_basis": "one_sided_upper_quantile_of_signed_demand_residual",
                "pooled_fallback": "pooled_relative_error_quantile_clipped_3x",
                "calibrated": False,
                "monotonic_asserted": True,
                "note": (
                    "q85<=q90<=q95 且 p50<=q90 由构造与校验保证；"
                    "样本不足时 quantile_method=pooled，只是尺度参考，不是已校准分位"
                ),
            },
            "uom_policy": {
                "group_field": "uom_group",
                "evidence": "canonical/sku_coverage.parquet 的 uom + uom_status",
                "cross_uom_sum_forbidden": True,
                "unknown_totals_allowed": False,
                "note": (
                    "只允许在已证 UOM 组内合计；unknown 是原始行计数（UOM 未证），"
                    "不得当件/套或与其它组合计；forecast_uom_totals 只给分组总量，不给统一总量"
                ),
            },
            "censoring": censoring_meta,
            "warehouse_allocation": {
                "basis": f"last_{cfg.recent_share_months}_complete_months_share",
                "window": [add_month(complete_last, -cfg.recent_share_months + 1), complete_last],
                "unknown_when_no_recent_sales": True,
            },
            "horizon_policy": {
                "leads": list(cfg.leads),
                "unchanged_core_leads": [d for d in cfg.leads if d in (60, 90, 120)],
                "scenario_only_leads": [d for d in cfg.leads if d not in (60, 90, 120)],
                "forecast_months": [meta_row["forecast_start_month"], meta_row["forecast_last_month"]],
                "note": (
                    "180 天窗口只作情景，不承诺覆盖率或精度；回测只有一步滚动原点，"
                    "没有多步验证。60/90/120 的口径与 r2 保持一致，扩窗不改变它们。"
                ),
            },
            "backend": {
                "name": getattr(backend, "name", None),
                "version": getattr(backend, "version", None),
                "available": backend is not None,
            },
        },
        "versions": {
            "python": platform.python_version(),
            "numpy": _version_of("numpy"),
            "pandas": _version_of("pandas"),
            "pyarrow": _version_of("pyarrow"),
            "statsforecast": _version_of("statsforecast"),
        },
        "code": {
            "git_head": _git_head(),
            "git_dirty": _git_dirty(),
            "module_sha256": _sha256(Path(__file__)),
        },
        "inputs": {
            "disposition": {
                "path": str(disposition_path),
                "sha256": _sha256(disposition_path),
                "rows": input_meta["input_rows"],
                "main_rows": input_meta["main_rows"],
                "used_rows": input_meta["used_rows"],
                "excluded_scope_rows": input_meta["excluded_scope_rows"],
                "excluded_scope_units": round(input_meta["excluded_scope_units"], 3),
                "excluded_scope_note": "main 序列中的 3PL/代发有效需求；不进自发货预测",
                "null_sku_rows": input_meta["null_sku_rows"],
                "null_sku_units": input_meta["null_sku_units"],
                "date_range": [boundary["first_date"], boundary["last_date"]],
            },
            "coverage": {
                "path": str(coverage_path),
                "sha256": _sha256(coverage_path),
                "rows": int(len(coverage)),
                "as_of_note": "canonical 2026-10-27 产物；只用于净额资格，不参与预测",
            },
        },
        "counts": {
            "skus": int(len(frames["forecast_sku_summary"])),
            "forecastable": int(frames["forecast_sku_summary"]["forecast_eligible"].sum()),
            "not_forecastable": int((~frames["forecast_sku_summary"]["forecast_eligible"]).sum()),
            "sku_monthly_rows": int(len(frames["forecast_sku_monthly"])),
            "sku_window_rows": int(len(frames["forecast_sku_windows"])),
            "sku_warehouse_monthly_rows": int(len(frames["forecast_sku_warehouse_monthly"])),
            "sku_warehouse_window_rows": int(len(frames["forecast_sku_warehouse_windows"])),
            "uom_total_rows": int(len(frames["forecast_uom_totals"])),
            "selected_model_counts": {
                str(k): int(v)
                for k, v in frames["forecast_sku_summary"]["selected_model"]
                .replace("", "(none)")
                .value_counts()
                .items()
            },
            "selection_source_counts": {
                str(k): int(v)
                for k, v in frames["forecast_sku_summary"]["selection_source"]
                .replace("", "(none)")
                .value_counts()
                .items()
            },
            "executed_method_counts": {
                str(k): int(v)
                for k, v in frames["forecast_sku_summary"]["forecast_method"]
                .value_counts()
                .items()
            },
            "model_failure_skus": int(
                (
                    frames["forecast_sku_summary"]["model_failure_reason"]
                    .fillna("")
                    .astype(str)
                    .str.len()
                    > 0
                ).sum()
            ),
        },
        "reconciliation": {
            "input_main_rows": input_meta["main_rows"],
            "used_rows": input_meta["used_rows"],
            "excluded_scope_rows": input_meta["excluded_scope_rows"],
            "excluded_null_sku_rows": input_meta["null_sku_rows"],
            "main_units": round(input_meta["main_units"], 3),
            "excluded_scope_units": round(input_meta["excluded_scope_units"], 3),
            "excluded_null_sku_units": round(input_meta["null_sku_units"], 3),
            "used_units": round(input_meta["used_units"], 3),
            "complete_month_units": round(series_meta["complete_units"], 3),
            "partial_month_units": round(series_meta["partial_units"], 3),
            "check_main_equals_parts": bool(
                abs(
                    input_meta["main_units"]
                    - input_meta["excluded_scope_units"]
                    - input_meta["null_sku_units"]
                    - input_meta["used_units"]
                )
                < 0.01
            ),
            "check_used_equals_complete_plus_partial": bool(
                abs(
                    input_meta["used_units"]
                    - series_meta["complete_units"]
                    - series_meta["partial_units"]
                )
                < 0.01
            ),
            "skus": series_meta["skus"],
        },
        "validation": {"status": "passed", "checks": checks},
        "supersedes": [
            {
                "name": "SC09 条件试用包 M1-TRIAL-v1（旧预测率）",
                "date": "2026-10-23",
                "data_cutoff": "as_of 2026-10-22；销量切点 2026-09",
                "status": "旧数据；不得冒充本次预测",
            },
            {
                "name": "T5 replenishment_v2.csv / summary_v3.md（AutoETS 平月率）",
                "date": "2026-10-22",
                "data_cutoff": "销量切点 2026-09；决策日 2026-10-22",
                "status": "旧数据；本次刷新不复用其行级结果",
            },
            {
                "name": "V1 model_race.json（五候选回测）",
                "date": "2026-10-22",
                "data_cutoff": "销量切点 2026-09",
                "status": "方法证据沿用；行级预测作废",
            },
        ],
        "caveats": [
            "预测在原始销售 SKU（通途 SKU）件数上建模；不因历史 BOM/发货形态未证而停止，但也不据此做供应净额。",
            "2026-10 是不足月，绝不参与拟合/同比/趋势；月度表里该月带 is_history_partial_month=true。",
            "预测资格与供应净额资格分离记录；netting_allowed=false 的 SKU 仍可预测，但不得直接与库存相减。",
            "区间是滚动经验/共形式，不是已标定分位，不承诺 80% 覆盖率。",
            "仓库分配是假设（最近 3 个完整月销量占比）；无近月销量时写 null，不写 0。",
            "禁止跨 UOM 合计：只用 forecast_uom_totals 的组内总量；unknown 组是原始行计数，不是件。",
            "数据截止日见 run.data_cutoff；新订单增量不等于新预测。",
        ],
        "outputs": outputs,
    }

    report = render_report(frames, manifest)
    report_path = out_dir / "forecast_report.md"
    report_path.write_text(report, encoding="utf-8")
    outputs.append({"file": report_path.name, "rows": 0, "sha256": _sha256(report_path)})
    manifest["outputs"] = outputs

    manifest_path = out_dir / "forecast_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # CURRENT 指针：最后写，避免半成品被当成成功；独立验证 run 可用 --no-current
    if update_current:
        current_tmp = out_root / "CURRENT.tmp"
        current_tmp.write_text(run_id, encoding="utf-8")
        current_tmp.replace(out_root / "CURRENT")
    return out_dir


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="自发货需求预测（原始销售 SKU × 完整月）")
    parser.add_argument("--disposition", default=DEFAULT_DISPOSITION)
    parser.add_argument("--coverage", default=DEFAULT_COVERAGE)
    parser.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    parser.add_argument("--decision-date", default=DECISION_DATE.isoformat())
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--no-statsforecast", action="store_true", help="强制 MA3/naive（离线/对照）")
    parser.add_argument("--censoring", action="store_true", help="启用断货删失训练适配（默认关闭）")
    parser.add_argument(
        "--censoring-mode", choices=list(censoring.MODES), default="conservative"
    )
    parser.add_argument("--censoring-flags", default=None)
    parser.add_argument("--no-current", action="store_true", help="不更新 CURRENT（独立验证 run）")
    parser.add_argument(
        "--model-policy",
        choices=list(MODEL_POLICIES),
        default=MODEL_POLICY_AUTOETS,
        help="autoets=旧行为（默认）；classified=按 model map + demand_pattern 选模型",
    )
    parser.add_argument(
        "--model-map",
        default=None,
        help="classified 选型的模型映射（parquet/csv，product_id 列 = canonical_sku）",
    )
    parser.add_argument("--validate-only", default=None, help="只校验已存在的 run 目录")
    args = parser.parse_args(argv)

    if args.validate_only:
        d = Path(args.validate_only)
        man = json.loads((d / "forecast_manifest.json").read_text(encoding="utf-8"))
        frames = {
            name: pd.read_parquet(d / f"{name}.parquet")
            for name in (
                "forecast_sku_summary",
                "forecast_sku_monthly",
                "forecast_sku_windows",
                "forecast_sku_warehouse_monthly",
                "forecast_uom_totals",
            )
        }
        cfg = ForecastConfig(
            decision_date=date.fromisoformat(man["run"]["decision_date"]),
            leads=tuple(man["run"]["leads"]),
        )
        checks = validate_frames(frames, cfg)
        print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False))
        return 0

    cfg = ForecastConfig(
        decision_date=date.fromisoformat(args.decision_date),
        skip_backtest=args.skip_backtest,
        censoring=args.censoring,
        censoring_mode=args.censoring_mode,
        censoring_flags_path=args.censoring_flags,
        model_policy=args.model_policy,
        model_map_path=args.model_map,
    )
    backend: Backend | None = None if args.no_statsforecast else load_backend()
    out_dir = run(
        disposition_path=args.disposition,
        coverage_path=args.coverage,
        out_root=args.out_root,
        cfg=cfg,
        run_id=args.run_id,
        backend=backend,
        update_current=not args.no_current,
    )
    print(f"forecast artifacts -> {out_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
