# -*- coding: utf-8 -*-
"""90/150/180 天累计需求回测（只读、离线）。

问题：现有 45 个完整月（2023-01..2026-09）够不够证明「越远越不准」？

做法
- 在若干 origin（月末）只用**当时可见**的完整月训练，按生产同一套 T5/T20 规则
  （AutoETS 默认，短史 MA3/naive）预测未来 6 个月。
- 累计窗口：从 origin 次日开始，取 90/150/180 个日历日；预测按日历权重
  摊到月，实际按原始行日销量求和。
- 逐 SKU 计算误差，汇总 WAPE / 偏差 / 样本量；区间覆盖只在一个明确的
  SKU 子样本上做（生产同一套一步残差分位，截断到含点预测），并标注不是总体。

不变量
- **不泄漏未来**：训练只到 origin 月末；实际窗口从 origin 次日开始。
- 评估 UOM 分组：主表只算 `个`；`套` 单列；`unknown` 不参与（UOM 未证）。
- 数据不足的 origin×horizon 标明不可用，不补零、不外推。
- 不写生产预测、不写 CURRENT、不下单。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from . import forecast as F
from .store import now_iso

SCHEMA_VERSION = "en-demand-forecast-horizon-backtest-v1"
DEFAULT_DISPOSITION = F.DEFAULT_DISPOSITION
DEFAULT_COVERAGE = F.DEFAULT_COVERAGE
DEFAULT_OUT = "D:/Work/fzh-order-store/en-demand-v1/forecast-backtest-horizon-2026-10-28"

ORIGINS = ("2025-01", "2025-04", "2025-07", "2025-10", "2026-01", "2026-04")
HORIZONS = (90, 150, 180)
FORECAST_H = 6  # 180 天从月末次日起最多跨 6 个自然月


@dataclass(frozen=True)
class Config:
    origins: tuple[str, ...] = ORIGINS
    horizons: tuple[int, ...] = HORIZONS
    forecast_h: int = FORECAST_H
    interval_level: float = 0.80
    interval_sample: int = 400
    max_backtest_origins: int = 4

    def to_json(self) -> dict[str, Any]:
        return {
            "origins": list(self.origins),
            "horizons_days": list(self.horizons),
            "forecast_h_months": self.forecast_h,
            "interval_level_nominal": self.interval_level,
            "interval_sample_skus": self.interval_sample,
            "max_backtest_origins": self.max_backtest_origins,
        }


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _git_dirty() -> bool | None:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10
        )
        return bool(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        return None


def _origin_date(origin: str) -> date:
    return date.fromisoformat(F.month_last_day(origin))


def _window_weights(start: date, days: int) -> dict[int, float]:
    return F.window_weights(start, days)


def feasibility(
    series: dict[str, F.SkuSeries],
    boundary: dict[str, Any],
    cfg: Config,
) -> pd.DataFrame:
    cutoff = date.fromisoformat(boundary["last_date"])
    rows: list[dict[str, Any]] = []
    for origin in cfg.origins:
        od = _origin_date(origin)
        start = od + timedelta(days=1)
        idx_by_sku = {sku: sum(1 for m in s.months if m <= origin) for sku, s in series.items()}
        n_any = sum(1 for n in idx_by_sku.values() if n >= 1)
        n3 = sum(1 for n in idx_by_sku.values() if n >= 3)
        n7 = sum(1 for n in idx_by_sku.values() if n >= 7)
        for d in cfg.horizons:
            end = start + timedelta(days=d - 1)
            available = end <= cutoff
            reason = "" if available else f"窗口末 {end.isoformat()} 晚于数据截止 {cutoff.isoformat()}"
            rows.append(
                {
                    "origin": origin,
                    "origin_date": od.isoformat(),
                    "horizon_days": d,
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                    "available": bool(available),
                    "unavailable_reason": reason,
                    "train_skus_any": n_any,
                    "train_skus_ge3": n3,
                    "train_skus_ge7": n7,
                }
            )
    return pd.DataFrame(rows)


def run(
    disposition_path: str | Path = DEFAULT_DISPOSITION,
    coverage_path: str | Path = DEFAULT_COVERAGE,
    out_dir: str | Path = DEFAULT_OUT,
    cfg: Config | None = None,
    backend: F.Backend | None | object = ...,
) -> Path:
    cfg = cfg or Config()
    if backend is ...:
        backend = F.load_backend()
    disposition_path, coverage_path, out_dir = map(Path, (disposition_path, coverage_path, out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    df, input_meta = F.load_disposition(disposition_path)
    boundary = F.resolve_month_boundary(df)
    series, _, _, series_meta = F.build_series(df, boundary)
    coverage = pd.read_parquet(coverage_path).set_index("tongtool_sku", drop=False)

    # 单位证据（与生产预测同一来源）
    uom: dict[str, tuple[str, str, str, bool]] = {}
    for sku in series:
        c = coverage.loc[sku] if sku in coverage.index else None
        uom[sku] = F._uom_fields(c)

    # 日销量（仅主序列 + 自发货；load_disposition 已完成过滤）
    daily = (
        df.groupby(["tongtool_sku", "demand_date"], as_index=False)["quantity"].sum()
    )

    # 区间覆盖子样本：用**最早 origin 之前**的历史量取 top N「个」组 SKU（确定性），
    # 不使用评估窗口内的任何未来量，避免样本选择泄漏；不是总体。
    first_origin = cfg.origins[0]
    cand: list[tuple[float, str]] = []
    for sku, s in series.items():
        if uom[sku][2] != "个":
            continue
        n0 = sum(1 for m in s.months if m <= first_origin)
        if n0 >= 7:
            cand.append((float(s.y[:n0].sum()), sku))
    cand.sort(key=lambda x: (-x[0], x[1]))
    interval_skus = {sku for _, sku in cand[: cfg.interval_sample]} if cfg.interval_sample > 0 else set()

    feat = feasibility(series, boundary, cfg)
    cutoff = date.fromisoformat(boundary["last_date"])

    cells: list[dict[str, Any]] = []
    for origin in cfg.origins:
        od = _origin_date(origin)
        start = od + timedelta(days=1)
        origin_next_i = F.ym_index(origin) + 1
        idx_by_sku = {
            sku: sum(1 for m in s.months if m <= origin) for sku, s in series.items()
        }
        prev_month = F.index_ym(origin_next_i - 1)

        # 每个 SKU 每个 origin 只拟合一次；区间回测也只跑一次，三个 horizon 复用
        fc: dict[str, tuple[np.ndarray, str, str]] = {}
        iv: dict[str, tuple[float, float] | None] = {}
        for sku, s in series.items():
            n = idx_by_sku[sku]
            if n < 1:
                continue
            ug = uom[sku][2]
            if ug not in ("个", "套"):
                continue
            train = s.y[:n]
            pred, method, reason, _ = F.fit_predict_rule(
                train, cfg.forecast_h, backend, F.ForecastConfig()
            )
            if pred is None:
                continue
            fc[sku] = (np.asarray(pred, dtype=float), method, reason)
            iv[sku] = None
            if sku in interval_skus and n >= 7:
                bt = F.run_backtest(
                    train,
                    F.ForecastConfig(max_backtest_origins=cfg.max_backtest_origins),
                    backend,
                    first_month=s.months[0],
                )
                if bt.n_origins >= 3:
                    iv[sku] = F._demand_residual_quantiles(
                        bt.errors, cfg.interval_level
                    )

        for d in cfg.horizons:
            end = start + timedelta(days=d - 1)
            if end > cutoff:
                continue
            weights = _window_weights(start, d)
            wsum = sum(weights.values())
            mask = (daily["demand_date"] >= start.isoformat()) & (
                daily["demand_date"] <= end.isoformat()
            )
            actual = daily[mask].groupby("tongtool_sku")["quantity"].sum().to_dict()

            for sku, (pred, method, reason) in fc.items():
                ug = uom[sku][2]
                n = idx_by_sku[sku]
                fcum = 0.0
                ok = True
                for mi, w in weights.items():
                    k = mi - origin_next_i
                    if 0 <= k < len(pred):
                        fcum += w * float(pred[k])
                    else:
                        ok = False
                        break
                if not ok:
                    continue
                a = float(actual.get(sku, 0.0))
                rec: dict[str, Any] = {
                    "schema_version": SCHEMA_VERSION,
                    "origin": origin,
                    "origin_date": od.isoformat(),
                    "horizon_days": d,
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                    "tongtool_sku": sku,
                    "uom_group": ug,
                    "train_months": n,
                    "train_last_month": prev_month,
                    "forecast_method": method,
                    "forecast_method_reason": reason,
                    "forecast": round(fcum, 6),
                    "actual": round(a, 6),
                    "error": round(fcum - a, 6),
                    "abs_error": round(abs(fcum - a), 6),
                    "interval_lo": None,
                    "interval_hi": None,
                    "covered": None,
                }
                if iv.get(sku) is not None:
                    lo, hi = iv[sku]
                    ilo = max(0.0, fcum + lo * wsum)
                    ihi = fcum + hi * wsum
                    rec["interval_lo"] = round(ilo, 6)
                    rec["interval_hi"] = round(ihi, 6)
                    rec["covered"] = bool(ilo <= a <= ihi)
                cells.append(rec)

    cell_df = pd.DataFrame(cells)
    if not len(cell_df):
        raise SystemExit("没有任何可评估的 origin×horizon 单元")

    summary_rows: list[dict[str, Any]] = []
    for (origin, d, ug), g in cell_df.groupby(["origin", "horizon_days", "uom_group"]):
        n = len(g)
        sum_a = float(g["actual"].sum())
        sum_f = float(g["forecast"].sum())
        err = g["forecast"] - g["actual"]
        covered = g["covered"].dropna()
        pos = g[g["actual"] > 1e-9]
        sum_a_pos = float(pos["actual"].sum())
        summary_rows.append(
            {
                "origin": origin,
                "horizon_days": int(d),
                "uom_group": ug,
                "n_skus": n,
                "sum_forecast": round(sum_f, 3),
                "sum_actual": round(sum_a, 3),
                "sum_abs_error": round(float(err.abs().sum()), 3),
                "wape": None if sum_a <= 1e-9 else round(float(err.abs().sum()) / sum_a, 6),
                "bias": None if sum_a <= 1e-9 else round(float(err.sum()) / sum_a, 6),
                "n_positive_actual": int(len(pos)),
                "wape_positive_actual": (
                    None
                    if sum_a_pos <= 1e-9
                    else round(float(pos["abs_error"].sum()) / sum_a_pos, 6)
                ),
                "bias_positive_actual": (
                    None
                    if sum_a_pos <= 1e-9
                    else round(float((pos["forecast"] - pos["actual"]).sum()) / sum_a_pos, 6)
                ),
                "mae": round(float(err.abs().mean()), 3),
                "median_abs_error": round(float(err.abs().median()), 3),
                "n_zero_actual": int((g["actual"] <= 1e-9).sum()),
                "interval_n": int(len(covered)),
                "coverage": None if not len(covered) else round(float(covered.mean()), 4),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values(
        ["uom_group", "horizon_days", "origin"]
    )

    pooled_rows: list[dict[str, Any]] = []
    for (d, ug), g in cell_df.groupby(["horizon_days", "uom_group"]):
        sum_a = float(g["actual"].sum())
        err = g["forecast"] - g["actual"]
        covered = g["covered"].dropna()
        pos = g[g["actual"] > 1e-9]
        sum_a_pos = float(pos["actual"].sum())
        pooled_rows.append(
            {
                "horizon_days": int(d),
                "uom_group": ug,
                "n_cells": len(g),
                "sum_forecast": round(float(g["forecast"].sum()), 3),
                "sum_actual": round(sum_a, 3),
                "sum_abs_error": round(float(err.abs().sum()), 3),
                "wape": None if sum_a <= 1e-9 else round(float(err.abs().sum()) / sum_a, 6),
                "bias": None if sum_a <= 1e-9 else round(float(err.sum()) / sum_a, 6),
                "n_positive_actual": int(len(pos)),
                "wape_positive_actual": (
                    None
                    if sum_a_pos <= 1e-9
                    else round(float(pos["abs_error"].sum()) / sum_a_pos, 6)
                ),
                "bias_positive_actual": (
                    None
                    if sum_a_pos <= 1e-9
                    else round(float((pos["forecast"] - pos["actual"]).sum()) / sum_a_pos, 6)
                ),
                "interval_n": int(len(covered)),
                "coverage": None if not len(covered) else round(float(covered.mean()), 4),
            }
        )
    pooled = pd.DataFrame(pooled_rows).sort_values(["uom_group", "horizon_days"])

    # 逐 origin 的 WAPE 走势 + 配对 90 vs 180
    trend_rows: list[dict[str, Any]] = []
    for origin, g in cell_df[cell_df["uom_group"] == "个"].groupby("origin"):
        row = {"origin": origin}
        for d in cfg.horizons:
            sub = g[g["horizon_days"] == d]
            if not len(sub):
                row[f"wape_l{d}"] = None
                continue
            sa = float(sub["actual"].sum())
            row[f"wape_l{d}"] = (
                None
                if sa <= 1e-9
                else round(float((sub["forecast"] - sub["actual"]).abs().sum()) / sa, 6)
            )
            pos = sub[sub["actual"] > 1e-9]
            sap = float(pos["actual"].sum())
            row[f"wape_pos_l{d}"] = (
                None
                if sap <= 1e-9
                else round(float(pos["abs_error"].sum()) / sap, 6)
            )
        trend_rows.append(row)
    trend = pd.DataFrame(trend_rows)

    paired_rows: list[dict[str, Any]] = []
    pcs_cells = cell_df[cell_df["uom_group"] == "个"]
    for origin, g in pcs_cells.groupby("origin"):
        a = g[g["horizon_days"] == 90].set_index("tongtool_sku")
        b = g[g["horizon_days"] == 180].set_index("tongtool_sku")
        common = a.index.intersection(b.index)
        if not len(common):
            continue
        worse = int((b.loc[common, "abs_error"] > a.loc[common, "abs_error"]).sum())
        diff = b.loc[common, "abs_error"] - a.loc[common, "abs_error"]
        paired_rows.append(
            {
                "origin": origin,
                "n_common": len(common),
                "share_180_worse": round(worse / len(common), 4),
                "median_abs_error_diff_180_minus_90": round(float(diff.median()), 3),
                "mean_abs_error_diff": round(float(diff.mean()), 3),
            }
        )
    paired = pd.DataFrame(paired_rows)

    # 数据不足 / 泄漏审计
    leak_rows: list[dict[str, Any]] = []
    for origin in cfg.origins:
        od = _origin_date(origin)
        start = od + timedelta(days=1)
        sub = cell_df[cell_df["origin"] == origin]
        if not len(sub):
            continue
        leak_rows.append(
            {
                "origin": origin,
                "train_last_month": str(sub["train_last_month"].max()),
                "actual_first_date": str(sub["window_start"].min()),
                "actual_last_date": str(sub["window_end"].max()),
                "train_le_origin": bool(str(sub["train_last_month"].max()) <= origin),
                "actual_after_origin": bool(date.fromisoformat(str(sub["window_start"].min())) > od),
            }
        )
    leak = pd.DataFrame(leak_rows)

    # 写产物
    cell_df.to_parquet(out_dir / "horizon_backtest_cells.parquet", index=False)
    summary.to_parquet(out_dir / "horizon_backtest_summary.parquet", index=False)
    summary.to_csv(out_dir / "horizon_backtest_summary.csv", index=False, encoding="utf-8-sig")
    pooled.to_csv(out_dir / "horizon_backtest_pooled.csv", index=False, encoding="utf-8-sig")
    trend.to_csv(out_dir / "horizon_backtest_trend.csv", index=False, encoding="utf-8-sig")
    paired.to_csv(out_dir / "horizon_backtest_paired_90_180.csv", index=False, encoding="utf-8-sig")
    feat.to_csv(out_dir / "origin_horizon_feasibility.csv", index=False, encoding="utf-8-sig")
    leak.to_csv(out_dir / "leakage_audit.csv", index=False, encoding="utf-8-sig")

    outputs = []
    for name in (
        "horizon_backtest_cells.parquet",
        "horizon_backtest_summary.parquet",
        "horizon_backtest_summary.csv",
        "horizon_backtest_pooled.csv",
        "horizon_backtest_trend.csv",
        "horizon_backtest_paired_90_180.csv",
        "origin_horizon_feasibility.csv",
        "leakage_audit.csv",
    ):
        p = out_dir / name
        outputs.append({"file": name, "sha256": _sha(p)})

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "output_dir": str(out_dir),
        "config": cfg.to_json(),
        "data": {
            "disposition_path": str(disposition_path),
            "disposition_sha256": _sha(disposition_path),
            "coverage_path": str(coverage_path),
            "coverage_sha256": _sha(coverage_path),
            "data_cutoff": boundary["last_date"],
            "complete_month_first": boundary["complete_month_first"],
            "complete_month_last": boundary["complete_month_last"],
            "complete_months": len(boundary["complete_months"]),
            "partial_months": boundary["partial_months"],
            "skus": len(series),
        },
        "model_rule": {
            "default": "AutoETS",
            "guards": "len<3→naive, 3-6→MA3, >=7→AutoETS, failure→MA3",
            "forecast_h_months": cfg.forecast_h,
            "note": "与生产 forecast.py 同一规则；不按回测切换",
        },
        "leakage": {
            "status": "passed" if bool(leak["train_le_origin"].all() and leak["actual_after_origin"].all()) else "FAILED",
            "rows": leak.to_dict(orient="records"),
        },
        "uom_policy": {
            "main_group": "个",
            "separate_group": "套",
            "excluded": "unknown（UOM 未证）",
        },
        "code": {
            "git_head": _git_head(),
            "git_dirty": _git_dirty(),
            "module_sha256": _sha(Path(__file__)),
        },
        "versions": {
            "python": platform.python_version(),
            "numpy": F._version_of("numpy"),
            "pandas": F._version_of("pandas"),
            "statsforecast": F._version_of("statsforecast"),
        },
        "counts": {
            "cells": int(len(cell_df)),
            "origins": int(cell_df["origin"].nunique()),
            "skus": int(cell_df["tongtool_sku"].nunique()),
        },
        "outputs": outputs,
        "caveats": [
            "origin 之间窗口重叠，不是独立样本；180 天真正不重叠的窗口只有约 3 个。",
            "区间覆盖只在按历史量取的 top N「个」组 SKU 子样本上计算，不是总体；名义 80% 未校准。",
            "累计误差是月预测按日历权重的和，实际是日销量和；不含断货删失校正。",
            "unknown UOM 不参与；套组单独列出，不跨 UOM 汇总。",
        ],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 报告（产物内）
    lines = [
        "# 90/150/180 天累计回测",
        "",
        f"> 生成：{manifest['generated_at']}　数据截止：{boundary['last_date']}　"
        f"完整月：{boundary['complete_month_first']}..{boundary['complete_month_last']}"
        f"（{len(boundary['complete_months'])} 个月）",
        "",
        "## 可行性",
        "",
        "| origin | 90d | 150d | 180d | 训练 SKU(≥7) |",
        "|---|---|---|---|---:|",
    ]
    for o in cfg.origins:
        sub = feat[feat["origin"] == o]
        mark = {
            int(r.horizon_days): ("✅" if r.available else f"❌ {r.unavailable_reason}")
            for r in sub.itertuples(index=False)
        }
        lines.append(
            f"| {o} | {mark.get(90,'—')} | {mark.get(150,'—')} | {mark.get(180,'—')} | "
            f"{int(sub['train_skus_ge7'].max())} |"
        )
    lines.append("")
    lines.append("## 汇总（个组，主表）")
    lines.append("")
    lines.append("| horizon | cells | Σ预测 | Σ实际 | Σ|e| | WAPE | WAPE(正实际) | 偏差 | 区间 n | 覆盖率 |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in pooled[pooled["uom_group"] == "个"].itertuples(index=False):
        cov = "—" if r.coverage is None or pd.isna(r.coverage) else f"{r.coverage:.1%}"
        wp = "—" if r.wape_positive_actual is None or pd.isna(r.wape_positive_actual) else f"{r.wape_positive_actual:.4f}"
        lines.append(
            f"| L{r.horizon_days} | {r.n_cells:,} | {r.sum_forecast:,.1f} | {r.sum_actual:,.1f} | "
            f"{r.sum_abs_error:,.1f} | {r.wape:.4f} | {wp} | {r.bias:+.4f} | {r.interval_n:,} | {cov} |"
        )
    lines.append("")
    lines.append("## 逐 origin WAPE（个组）")
    lines.append("")
    lines.append("| origin | L90 | L150 | L180 |")
    lines.append("|---|---:|---:|---:|")
    for r in trend.itertuples(index=False):
        def f(v):
            return "—" if v is None or pd.isna(v) else f"{v:.4f}"
        lines.append(f"| {r.origin} | {f(r.wape_l90)} | {f(r.wape_l150)} | {f(r.wape_l180)} |")
    lines.append("")
    lines.append("## 90 vs 180 配对（个组，同 SKU/同 origin）")
    lines.append("")
    lines.append("| origin | 共同 SKU | 180 更差占比 | 中位 |e180|−|e90| | 均值差 |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in paired.itertuples(index=False):
        lines.append(
            f"| {r.origin} | {r.n_common:,} | {r.share_180_worse:.1%} | "
            f"{r.median_abs_error_diff_180_minus_90:+.3f} | {r.mean_abs_error_diff:+.3f} |"
        )
    lines.append("")
    lines.append("## 泄漏审计")
    lines.append("")
    lines.append(f"- 状态：**{manifest['leakage']['status']}**（训练月末 ≤ origin；实际窗口首日 > origin）。")
    lines.append("")
    lines.append("## 读法")
    lines.append("")
    lines.append("- WAPE 是数量加权绝对误差/实际量；不是准确率，没有通用阈值。")
    lines.append("- origin 窗口重叠，不能当独立样本；180 天不重叠窗口约 3 个，结论只能描述，不能做统计证明。")
    lines.append("- 区间覆盖是子样本、名义 80%、未校准；不是总体覆盖率。")
    lines.append("- unknown UOM 不参与；套组单列。")
    report = "\n".join(lines) + "\n"
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    return out_dir


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="90/150/180 天累计需求回测")
    ap.add_argument("--disposition", default=DEFAULT_DISPOSITION)
    ap.add_argument("--coverage", default=DEFAULT_COVERAGE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--origins", default=",".join(ORIGINS))
    ap.add_argument("--interval-sample", type=int, default=400)
    args = ap.parse_args(argv)
    cfg = Config(
        origins=tuple(x.strip() for x in args.origins.split(",") if x.strip()),
        interval_sample=args.interval_sample,
    )
    out = run(args.disposition, args.coverage, args.out, cfg)
    print(f"horizon backtest -> {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
