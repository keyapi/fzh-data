# -*- coding: utf-8 -*-
"""classified 选型 + q85/q90/q95 的离线测试。

合成数据；不联网、不读生产存储。AutoETS 用确定性 FakeBackend，
SBA/TSB 用本地 statsforecast（未安装时跳过对应断言）。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from self_fulfilled_demand import forecast as F


class FakeBackend:
    """确定性后端：近 3 月均值；不依赖 statsforecast。"""

    name = "fake"
    version = "0.0-test"

    def forecast(self, y: np.ndarray, h: int, season_length: int) -> np.ndarray:
        k = min(3, len(y))
        return np.repeat(float(np.mean(y[-k:])), h)


MONTHS = F.month_range("2024-01", "2026-09")  # 33 个完整月


def _intermittent(n: int) -> np.ndarray:
    y = np.zeros(n, dtype=float)
    idx = [i for i in (1, 4, 7, 9, 14, 18, 22, 25, 29, 32) if i < n]
    vals = [1.0, 2.0, 1.0, 1.0, 3.0, 1.0, 2.0, 1.0, 1.0, 2.0]
    for k, i in enumerate(idx):
        y[i] = vals[k]
    return y


def _lumpy(n: int) -> np.ndarray:
    y = np.zeros(n, dtype=float)
    y[2::6] = 20.0
    y[4::9] = 5.0
    return y


def _smooth(n: int) -> np.ndarray:
    return 10.0 + (np.arange(n) % 5)


# sku → (product_id, values 生成器, map 里的 adopted_model, demand_pattern, 起始月偏移)
CASES: dict[str, tuple[str, object, str | None, str | None, int]] = {
    "STABLE": ("KS-STABLE", lambda n: np.full(n, 10.0), "snaive", "smooth", 0),
    "ETS": ("KS-ETS", _smooth, "ets_ann", "smooth", 0),
    "INTERMITTENT": ("KS-INTER", _intermittent, "sba", "intermittent", 0),
    "LUMPY": ("KS-LUMPY", _lumpy, "tsb", "lumpy", 0),
    "SHORT": ("KS-SHORT", _intermittent, "sba", "intermittent", -5),
    "UNKNOWN": ("KS-UNKNOWN", _intermittent, "prophet", "intermittent", 0),
    "NODEMAND": ("KS-NODEMAND", lambda n: np.zeros(n, dtype=float), "none", "no_demand", 0),
    "TINY": ("KS-TINY", lambda n: np.array([3.0, 4.0]), "sba", "intermittent", -2),
    "NOMAP": ("KS-NOMAP", _smooth, None, None, 0),
}


def _demand_date(m: str) -> str:
    return f"{m}-{F.month_last_day(m) if m == MONTHS[-1] else '01'}"


def _build_inputs(root: Path, with_map: bool = True) -> tuple[Path, Path, Path | None]:
    rows: list[dict] = []
    coverage: list[dict] = []
    map_rows: list[dict] = []
    for sku, (product, gen, model, pattern, offset) in CASES.items():
        months = MONTHS[offset:] if offset else MONTHS
        values = gen(len(months))
        for m, v in zip(months, values):
            rows.append(
                {
                    "tongtool_sku": sku,
                    "demand_date": _demand_date(m),
                    "quantity": float(v),
                    "in_main_series": True,
                    "fulfillment_scope": "self_fulfilled_candidate",
                    "canonical_warehouse": "美东-CENTRADE",
                    "canonical_sku": product,
                    "mapping_status": "mapped",
                }
            )
        coverage.append(
            {
                "tongtool_sku": sku,
                "ready_rows": len(months),
                "blocked_rows": 0,
                "block_reasons": "",
                "canonical_sku": product,
                "mapping_status": "mapped",
                "uom": "个",
                "uom_status": "known_piece",
            }
        )
        if model is not None:
            map_rows.append(
                {
                    "product_id": product,
                    "pool": "美东USNJ",
                    "physical_form": "成品",
                    "canonical_uom": "个",
                    "adopted_model": model,
                    "demand_pattern": pattern,
                    "hist_avg_3y": float(np.mean(values)),
                }
            )

    dispo_path = root / "disposition.parquet"
    pd.DataFrame(rows).to_parquet(dispo_path, index=False)
    cov_path = root / "coverage.parquet"
    pd.DataFrame(coverage).to_parquet(cov_path, index=False)
    map_path = None
    if with_map:
        map_path = root / "model_map.csv"
        pd.DataFrame(map_rows).to_csv(map_path, index=False)
    return dispo_path, cov_path, map_path


def _run(
    tmp_path: Path,
    *,
    with_map: bool = True,
    policy: str = F.MODEL_POLICY_CLASSIFIED,
    backend=None,
    run_id: str = "classified-run",
) -> Path:
    dispo, cov, map_path = _build_inputs(tmp_path, with_map=with_map)
    cfg = F.ForecastConfig(
        decision_date=date(2026, 10, 29),
        max_backtest_origins=4,
        model_policy=policy,
        model_map_path=str(map_path) if map_path else None,
    )
    return F.run(
        disposition_path=dispo,
        coverage_path=cov,
        out_root=tmp_path / "out",
        cfg=cfg,
        run_id=run_id,
        backend=FakeBackend() if backend is None else backend,
    )


@pytest.fixture(scope="module")
def classified_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("classified")
    out = _run(root)
    frames = {
        n: pd.read_parquet(out / f"{n}.parquet")
        for n in (
            "forecast_sku_summary",
            "forecast_sku_monthly",
            "forecast_sku_windows",
            "forecast_sku_warehouse_monthly",
            "forecast_sku_warehouse_windows",
            "forecast_uom_totals",
        )
    }
    man = json.loads((out / "forecast_manifest.json").read_text(encoding="utf-8"))
    return out, {**frames, "_manifest": man}


def _summary(frames: dict) -> pd.DataFrame:
    return frames["forecast_sku_summary"].set_index("tongtool_sku")


def test_map_selection_stable_snaive_and_autoets(classified_run) -> None:
    _, frames = classified_run
    s = _summary(frames)
    # 稳定序列：map 指定 snaive → 实际执行 snaive
    assert s.loc["STABLE", "forecast_method"] == "snaive"
    assert s.loc["STABLE", "selected_model"] == "snaive"
    assert s.loc["STABLE", "selection_source"] == F.SELECTION_MAP
    assert s.loc["STABLE", "forecast_status"] == "ok_classified"
    assert s.loc["STABLE", "model_failure_reason"] == ""
    # D5 旧名 ets_ann 规范成 autoets
    assert s.loc["ETS", "forecast_method"] == "autoets"
    assert s.loc["ETS", "selected_model"] == "autoets"


def test_map_selection_intermittent_sba_lumpy_tsb(classified_run) -> None:
    _, frames = classified_run
    s = _summary(frames)
    assert s.loc["INTERMITTENT", "forecast_method"] == "sba"
    assert s.loc["INTERMITTENT", "selected_model"] == "sba"
    assert s.loc["LUMPY", "forecast_method"] == "tsb"
    assert s.loc["LUMPY", "selected_model"] == "tsb"


def test_unknown_map_model_falls_back_to_pattern(classified_run) -> None:
    _, frames = classified_run
    s = _summary(frames)
    r = s.loc["UNKNOWN"]
    assert r["selected_model"] == "sba"
    assert r["forecast_method"] == "sba"
    assert r["selection_source"] == F.SELECTION_PATTERN
    assert r["forecast_status"] == "ok_classified_pattern"
    assert "不在模型池" in r["selection_reason"]
    assert "prophet" in r["selection_reason"]


def test_short_history_guard_beats_map(classified_run) -> None:
    _, frames = classified_run
    s = _summary(frames)
    r = s.loc["SHORT"]
    assert r["forecast_method"] == "ma3"
    assert r["selected_model"] == "ma3"
    assert r["selection_source"] == F.SELECTION_GUARD
    assert r["forecast_status"] == "ok_short_ma3"
    assert "T20" in r["selection_reason"]
    # 1–2 个月：naive_last 是 T20 标准输出，不是「模型失败」
    t = s.loc["TINY"]
    assert t["forecast_method"] == "naive_last"
    assert t["forecast_status"] == "ok_short_naive"
    assert t["model_failure_reason"] == ""


def test_no_map_uses_autoets_guard_and_no_demand_is_zero(classified_run) -> None:
    _, frames = classified_run
    s = _summary(frames)
    assert s.loc["NOMAP", "forecast_method"] == "autoets"
    assert s.loc["NOMAP", "selection_source"] == F.SELECTION_GUARD
    r = s.loc["NODEMAND"]
    assert r["forecast_method"] == "none"
    assert r["selected_model"] == "none"
    assert r["forecast_status"] == "ok_classified_no_demand"
    assert r["p50_l90"] == 0.0


def test_selection_source_counts_in_manifest(classified_run) -> None:
    _, frames = classified_run
    man = frames["_manifest"]
    assert man["model"]["policy"] == F.MODEL_POLICY_CLASSIFIED
    assert man["model"]["policy_version"] == F.MODEL_POLICY_VERSION
    assert man["model"]["model_map"]["provided"] is True
    assert man["model"]["model_map"]["products"] == 8  # NOMAP 不在 map
    assert man["model"]["quantiles"]["levels"] == [0.85, 0.9, 0.95]
    assert man["model"]["quantiles"]["calibrated"] is False
    counts = man["counts"]
    assert counts["selected_model_counts"]["snaive"] == 1
    assert counts["selection_source_counts"][F.SELECTION_MAP] >= 4
    assert counts["model_failure_skus"] == 0


def test_quantiles_are_monotonic_and_windows_conserved(classified_run) -> None:
    _, frames = classified_run
    s = frames["forecast_sku_summary"]
    monthly = frames["forecast_sku_monthly"]
    windows = frames["forecast_sku_windows"]

    ok = s[s["forecast_eligible"]]
    for d in (60, 90, 120, 180):
        sub = ok.dropna(subset=[f"q85_l{d}", f"q90_l{d}", f"q95_l{d}"])
        assert len(sub) > 0
        assert (sub[f"q85_l{d}"] <= sub[f"q90_l{d}"] + 1e-6).all()
        assert (sub[f"q90_l{d}"] <= sub[f"q95_l{d}"] + 1e-6).all()
        assert (sub[f"p50_l{d}"] <= sub[f"q90_l{d}"] + 1e-6).all()
        assert (sub[f"q85_l{d}"] >= -1e-9).all()

    m = monthly.dropna(subset=["q85", "q90", "q95"])
    assert (m["q85"] <= m["q90"] + 1e-6).all()
    assert (m["q90"] <= m["q95"] + 1e-6).all()
    assert (m["p50"] <= m["q90"] + 1e-6).all()

    w = windows.dropna(subset=["q85", "q90", "q95"])
    assert (w["q85"] <= w["q90"] + 1e-6).all()
    assert (w["q90"] <= w["q95"] + 1e-6).all()

    # 窗口 q90 = 月度 q90 的日历加权和
    m90 = monthly.dropna(subset=["q90"]).set_index(
        ["tongtool_sku", "forecast_month"]
    )["q90"]
    for d in (60, 90):
        weights = {F.index_ym(i): v for i, v in F.window_weights(date(2026, 10, 29), d).items()}
        for rec in windows[
            (windows["lead_days"] == d) & windows["q90"].notna()
        ].itertuples(index=False):
            total = sum(
                wt * float(m90.loc[(rec.tongtool_sku, ym)])
                for ym, wt in weights.items()
                if (rec.tongtool_sku, ym) in m90.index
            )
            assert abs(total - float(rec.q90)) < 0.02


def test_validation_passes_and_quantile_method_marked(classified_run) -> None:
    out, frames = classified_run
    assert frames["_manifest"]["validation"]["status"] == "passed"
    assert "quantile_order" in frames["_manifest"]["validation"]["checks"]
    s = _summary(frames)
    # 4 个回测原点 → own 分位
    assert s.loc["STABLE", "quantile_method"] == "own_rolling_residual_quantile"
    # 短史只有 2 个原点 → 池化系数，并如实标注
    assert s.loc["SHORT", "quantile_method"] == "pooled"


def test_model_failure_falls_back_with_reason(tmp_path: Path, monkeypatch) -> None:
    original = F._named_forecast

    def boom(model: str, y, h, season_length):
        if model == "sba":
            raise RuntimeError("forced failure")
        return original(model, y, h, season_length)

    monkeypatch.setattr(F, "_named_forecast", boom)
    out = _run(tmp_path, run_id="fallback-run")
    s = pd.read_parquet(out / "forecast_sku_summary.parquet").set_index("tongtool_sku")
    r = s.loc["INTERMITTENT"]
    assert r["selected_model"] == "sba"
    assert r["selection_source"] == F.SELECTION_MAP  # 选择来源不丢
    assert r["forecast_method"] == "autoets"  # 实际执行的是回退模型
    assert r["forecast_status"] == "ok_classified_fallback"
    assert "SBA" in r["model_failure_reason"]
    assert "forced failure" in r["model_failure_reason"]


def test_default_policy_is_unchanged(tmp_path: Path) -> None:
    out = _run(tmp_path, with_map=False, policy=F.MODEL_POLICY_AUTOETS)
    s = pd.read_parquet(out / "forecast_sku_summary.parquet").set_index("tongtool_sku")
    assert (s["selection_source"] == F.SELECTION_DEFAULT).all()
    long_hist = s[s["forecast_eligible"] & (s["history_months"] >= 7)]
    assert (long_hist["forecast_method"] == "autoets").all()
    assert s.loc["SHORT", "forecast_status"] == "ok_short_ma3"
    man = json.loads((out / "forecast_manifest.json").read_text(encoding="utf-8"))
    assert man["model"]["policy"] == F.MODEL_POLICY_AUTOETS
    assert man["model"]["policy_version"] is None


# --------------------------------------------------------------------------- #
# model map 装载
# --------------------------------------------------------------------------- #
def test_load_model_map_requires_columns(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    pd.DataFrame([{"product_id": "A", "adopted_model": "sba"}]).to_csv(p, index=False)
    with pytest.raises(ValueError, match="demand_pattern"):
        F.load_model_map(p)


def test_load_model_map_collapses_duplicates(tmp_path: Path) -> None:
    rows = [
        # CG 池没有需求 → none；美东池有真实模型 → 应该选 snaive
        {"product_id": "P1", "pool": "CG", "physical_form": "成品", "canonical_uom": "个",
         "adopted_model": "none", "demand_pattern": "no_demand", "hist_avg_3y": 0},
        {"product_id": "P1", "pool": "美东USNJ", "physical_form": "成品", "canonical_uom": "个",
         "adopted_model": "snaive", "demand_pattern": "lumpy", "hist_avg_3y": 3},
        {"product_id": "P2", "pool": "波兰", "physical_form": "皮壳", "canonical_uom": "个",
         "adopted_model": "ets_ann", "demand_pattern": "smooth", "hist_avg_3y": 1},
    ]
    for suffix in ("csv", "parquet"):
        p = tmp_path / f"map.{suffix}"
        df = pd.DataFrame(rows)
        if suffix == "csv":
            df.to_csv(p, index=False)
        else:
            df.to_parquet(p, index=False)
        m, meta = F.load_model_map(p)
        assert set(m) == {"P1", "P2"}
        assert m["P1"].model == "snaive"
        assert m["P1"].demand_pattern == "lumpy"
        assert m["P1"].ambiguous is True
        assert m["P1"].candidates == 2
        assert m["P2"].model == "autoets"  # ets_ann 规范名
        assert meta["ambiguous_products"] == 1
        assert meta["products"] == 2
        assert meta["model_counts"]["snaive"] == 1


def test_choose_model_pattern_and_guard_directly() -> None:
    cfg = F.ForecastConfig(model_policy=F.MODEL_POLICY_CLASSIFIED)
    # 无 map、无分型 → AutoETS 守卫
    c = F.choose_model(24, cfg, {}, "")
    assert (c.model, c.source) == ("autoets", F.SELECTION_GUARD)
    # 分型回退
    m = {"P": F.ModelMapEntry("P", None, "prophet", "lumpy")}
    c = F.choose_model(24, cfg, m, "P")
    assert (c.model, c.source, c.pattern) == ("tsb", F.SELECTION_PATTERN, "lumpy")
    # 短史守卫压过 map
    m = {"P": F.ModelMapEntry("P", "sba", "sba", "intermittent")}
    c = F.choose_model(4, cfg, m, "P")
    assert (c.model, c.source) == ("ma3", F.SELECTION_GUARD)
    c = F.choose_model(2, cfg, m, "P")
    assert (c.model, c.source) == ("naive", F.SELECTION_GUARD)
