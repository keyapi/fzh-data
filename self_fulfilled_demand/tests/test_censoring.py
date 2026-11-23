# -*- coding: utf-8 -*-
"""断货删失适配层测试（合成数据）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from self_fulfilled_demand import censoring as C
from self_fulfilled_demand import forecast as F


class FakeBackend:
    name = "fake"
    version = "0.0-test"

    def forecast(self, y: np.ndarray, h: int, season_length: int) -> np.ndarray:
        k = min(3, len(y))
        return np.repeat(float(np.mean(y[-k:])), h)


def _flags_file(tmp_path: Path) -> Path:
    df = pd.DataFrame(
        [
            {"sku": "A", "month": "2026-09", "censored": True, "uom_group": "个"},
            {"sku": "A", "month": "2026-08", "censored": False, "uom_group": "个"},
            {"sku": "B", "month": "2026-09", "censored": True, "uom_group": "套"},
            {"sku": "C", "month": "2026-09", "censored": True, "uom_group": "unknown"},
            {"sku": "D", "month": "2026-09", "censored": True, "uom_group": "uom_conflict"},
        ]
    )
    p = tmp_path / "flags.parquet"
    df.to_parquet(p, index=False)
    return p


def test_load_flags_only_proven_uom(tmp_path: Path) -> None:
    flags, meta = C.load_flags(_flags_file(tmp_path))
    assert set(flags) == {"A", "B"}  # unknown / uom_conflict 不进训练
    assert flags["A"]["2026-09"]["uom_group"] == "个"
    assert meta["skus"] == 2
    assert meta["censored_rows"] == 2


def test_conservative_only_replaces_censored_zero() -> None:
    y = np.array([10.0, 12.0, 0.0, 8.0])
    months = ["2026-06", "2026-07", "2026-08", "2026-09"]
    flags = {"2026-08": {"uom_group": "个"}, "2026-09": {"uom_group": "个"}}
    out, st = C.apply(months, y, flags, "conservative")
    # 2026-08 是删失零 → 前 6 个非删失中位 = median(10,12)=11，P90 截顶后 11
    assert out[2] == 11.0
    # 2026-09 有观测 8 → 保留，不硬补
    assert out[3] == 8.0
    assert st.censored_months == 2
    assert st.censored_zero_months == 1
    assert st.replaced_months == 1


def test_aggressive_changes_all_censored() -> None:
    y = np.array([10.0, 12.0, 1.0, 8.0])
    months = ["2026-06", "2026-07", "2026-08", "2026-09"]
    flags = {"2026-08": {"uom_group": "个"}, "2026-09": {"uom_group": "个"}}
    out, st = C.apply(months, y, flags, "aggressive")
    assert out[2] > 1.0
    assert out[3] >= 8.0
    assert st.replaced_months == 2


def test_tj_bundle_strict_rule() -> None:
    assert C.tj_bundle_allowed("TJ#KS1x1-001", 0) is True
    assert C.tj_bundle_allowed("KS-SET", 1) is False
    assert C.tj_bundle_allowed("PK#1", 1) is False
    assert C.tj_bundle_allowed("TJ#X", 1) is False
    assert C.tj_bundle_allowed("TJ#X", None) is False


def test_no_flags_is_identity() -> None:
    y = np.array([1.0, 2.0])
    out, st = C.apply(["2026-08", "2026-09"], y, {}, "conservative")
    assert np.array_equal(out, y)
    assert st.censored_months == 0


def test_forecast_default_censoring_off() -> None:
    assert F.ForecastConfig().censoring is False


def _make_run_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    months = [f"2024-{m:02d}" for m in range(1, 13)] + [
        f"2025-{m:02d}" for m in range(1, 13)
    ] + [f"2026-{m:02d}" for m in range(1, 10)]
    rows = []
    for i, m in enumerate(months):
        v = 10.0 if m != "2026-07" else 0.0
        rows.append(
            {
                "tongtool_sku": "A",
                "demand_date": f"{m}-30" if m == "2026-09" else f"{m}-01",
                "quantity": v,
                "in_main_series": True,
                "fulfillment_scope": "self_fulfilled_candidate",
                "canonical_warehouse": "美东-CENTRADE",
                "canonical_sku": "CANON-A",
                "mapping_status": "mapped",
            }
        )
    dispo = tmp_path / "d.parquet"
    pd.DataFrame(rows).to_parquet(dispo, index=False)
    cov = tmp_path / "c.parquet"
    pd.DataFrame(
        [
            {
                "tongtool_sku": "A",
                "ready_rows": 33,
                "blocked_rows": 0,
                "block_reasons": "",
                "canonical_sku": "CANON-A",
                "mapping_status": "mapped",
                "uom": "个",
                "uom_status": "known_piece",
            }
        ]
    ).to_parquet(cov, index=False)
    flags = tmp_path / "f.parquet"
    pd.DataFrame(
        [{"sku": "A", "month": "2026-07", "censored": True, "uom_group": "个"}]
    ).to_parquet(flags, index=False)
    stock = tmp_path / "s.parquet"
    pd.DataFrame(
        [
            {"sku": "A", "d": "2026-05-10", "stock_state": "present_positive", "available": 5.0, "source": "pj_checkpoint"},
            {"sku": "A", "d": "2026-07-10", "stock_state": "present_zero", "available": 0.0, "source": "pj_checkpoint"},
        ]
    ).to_parquet(stock, index=False)
    return dispo, cov, flags, stock


def test_forecast_run_censoring_changes_forecast_and_keeps_current(tmp_path: Path) -> None:
    dispo, cov, flags, stock = _make_run_inputs(tmp_path)
    out_root = tmp_path / "out"
    out_root.mkdir()
    (out_root / "CURRENT").write_text("keep", encoding="utf-8")
    cfg_off = F.ForecastConfig(decision_date=date(2026, 10, 29))
    off = F.run(
        dispo, cov, out_root, cfg=cfg_off, run_id="off",
        backend=FakeBackend(), update_current=False,
    )
    cfg_on = F.ForecastConfig(
        decision_date=date(2026, 10, 29), censoring=True,
        censoring_mode="conservative", censoring_flags_path=str(flags),
        stock_observations_path=str(stock),
    )
    on = F.run(
        dispo, cov, out_root, cfg=cfg_on, run_id="on",
        backend=FakeBackend(), update_current=False,
    )
    s_off = pd.read_parquet(off / "forecast_sku_summary.parquet").set_index("tongtool_sku")
    s_on = pd.read_parquet(on / "forecast_sku_summary.parquet").set_index("tongtool_sku")
    assert s_off.loc["A", "censoring_applied"] == False  # noqa: E712
    assert s_on.loc["A", "censoring_applied"] == True  # noqa: E712
    assert s_on.loc["A", "censoring_replaced_months"] == 1
    assert s_on.loc["A", "p50_l90"] > s_off.loc["A", "p50_l90"]
    assert (out_root / "CURRENT").read_text(encoding="utf-8") == "keep"


def test_backtest_actual_uses_raw_not_imputed() -> None:
    """删失补值只改训练；回测真值必须用原始 actual。"""
    raw = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 0.0, 0.0])
    adj = raw.copy()
    adj[8] = 10.0
    adj[9] = 10.0
    res = F.run_backtest(
        adj,
        F.ForecastConfig(max_backtest_origins=4),
        FakeBackend(),
        first_month="2025-12",
        y_actual=raw,
    )
    assert res.n_origins >= 3
    # 最后两个原点的 actual 必须是 0（原始），不是补值后的 10
    assert res.actuals[-2:] == [0.0, 0.0]


def test_censoring_manifest_added_units_by_uom(tmp_path: Path) -> None:
    dispo, cov, flags, stock = _make_run_inputs(tmp_path)
    cfg = F.ForecastConfig(
        decision_date=date(2026, 10, 29), censoring=True,
        censoring_mode="conservative", censoring_flags_path=str(flags),
        stock_observations_path=str(stock),
    )
    out = F.run(
        dispo, cov, tmp_path / "out", cfg=cfg, run_id="on",
        backend=FakeBackend(), update_current=False,
    )
    import json

    man = json.loads((out / "forecast_manifest.json").read_text(encoding="utf-8"))
    cens = man["model"]["censoring"]
    assert "added_units" not in cens  # 不提供跨 UOM 合计
    assert "replaced_months" not in cens
    assert cens["by_uom"]["个"]["added_units"] > 0
    assert cens["l180_coverage"]["complete"] is True
    assert cens["l180_coverage"]["forecast_last_month"] >= "2027-04"
    # v5 接线回归：coverage 未预索引也必须得到 allowed_skus>0 且实际补值
    assert cens["backtest_imputation"]["allowed_skus"] > 0
    assert cens["backtest_imputation"]["points_repeat_across_origins"] is True
    assert cens["backtest_imputation"]["not_independent_sales"] is True
    assert "imputed_points" not in cens["backtest_imputation"]
    assert "imputed_units" not in cens["backtest_imputation"]
    assert cens["backtest_imputation"]["by_uom"]["个"]["skus"] > 0
    s = pd.read_parquet(out / "forecast_sku_summary.parquet")
    assert int(s["backtest_imputed_points"].sum()) > 0


def test_cumulative_rejects_missing_months() -> None:
    from self_fulfilled_demand import stockout_censoring as S

    short = np.repeat(10.0, 6)
    with pytest.raises(ValueError, match="缺预测月"):
        S.cumulative(short, 180, date(2026, 10, 29))
    full = np.repeat(10.0, 7)
    assert S.cumulative(full, 180, date(2026, 10, 29)) > 0


def test_conservative_imputation_ignores_future_values() -> None:
    """补值只用 i 之前的数据；未来月份不能抬高均值/分位。"""
    months = ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    flags = {"2026-08": {"uom_group": "个"}}
    past = np.array([10.0, 10.0, 0.0])
    full = np.array([10.0, 10.0, 0.0, 1000.0, 1000.0])
    a, _ = C.apply(months[:3], past, flags, "conservative")
    b, _ = C.apply(months, full, flags, "conservative")
    assert a[2] == b[2] == 10.0  # 未来 1000 不得影响 2026-08 的补值


def test_apply_as_of_equals_truncated_apply() -> None:
    months = ["2026-06", "2026-07", "2026-08", "2026-09"]
    y = np.array([10.0, 10.0, 0.0, 1000.0])
    flags = {"2026-08": {"uom_group": "个"}, "2026-09": {"uom_group": "个"}}
    a, sa = C.apply_as_of(months, y, flags, 3, "conservative")
    b, sb = C.apply(months[:3], y[:3], {"2026-08": flags["2026-08"]}, "conservative")
    assert np.array_equal(a, b)
    assert sa.censored_months == sb.censored_months == 1


def test_backtest_recomputes_censoring_per_origin(monkeypatch) -> None:
    calls = []
    original = C.apply_as_of

    def spy(months, y, flags, upto, mode="conservative"):
        calls.append(int(upto))
        return original(months, y, flags, upto, mode)

    monkeypatch.setattr(C, "apply_as_of", spy)
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    y = np.repeat(10.0, 12)
    y[8] = 0.0
    flags = {"2025-09": {"uom_group": "个"}}
    F.run_backtest(
        y,
        F.ForecastConfig(max_backtest_origins=3),
        FakeBackend(),
        first_month="2025-01",
        y_actual=y.copy(),
        y_train_raw=y.copy(),
        months=months,
        censoring_flags=flags,
    )
    assert calls, "应逐原点调用 apply_as_of"
    assert max(calls) < len(y)
    # 每个原点只用自己的前缀（i 为训练长度）
    assert all(0 < i <= len(y) for i in calls)


def _stock_rows(rows):
    return pd.DataFrame(rows)


def test_rebuild_flags_as_of_no_lookahead() -> None:
    """早期 origin 不能因为后来出现正库存就把早期零库存月标删失。"""
    stock = _stock_rows(
        [
            {"sku": "A", "d": "2026-04-10", "stock_state": "present_zero", "available": 0.0, "source": "pj_checkpoint"},
            {"sku": "A", "d": "2026-06-10", "stock_state": "present_positive", "available": 5.0, "source": "pj_checkpoint"},
            {"sku": "B", "d": "2026-04-10", "stock_state": "present_positive", "available": 3.0, "source": "pj_checkpoint"},
            {"sku": "B", "d": "2026-06-10", "stock_state": "present_zero", "available": 0.0, "source": "pj_checkpoint"},
        ]
    )
    allowed = {"A", "B"}
    early = C.rebuild_flags_as_of(stock, "2026-04-30", allowed)
    late = C.rebuild_flags_as_of(stock, "2026-06-30", allowed)
    assert early == {}  # 4 月只有零/正之一，不能判 both-states
    assert "2026-04" in late["A"]
    assert "2026-06" in late["B"]


def test_backtest_uses_flags_from_origin_map(monkeypatch) -> None:
    seen = []
    original = C.apply_as_of

    def spy(months, y, flags, upto, mode="conservative"):
        seen.append(set(flags))
        return original(months, y, flags, upto, mode)

    monkeypatch.setattr(C, "apply_as_of", spy)
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    y = np.repeat(10.0, 12)
    y[8] = 0.0
    by_origin = {
        "2025-09": {"2025-09": {"uom_group": "个"}},
        "2025-10": {},
        "2025-11": {},
    }
    F.run_backtest(
        y,
        F.ForecastConfig(max_backtest_origins=3),
        FakeBackend(),
        first_month="2025-01",
        y_actual=y.copy(),
        y_train_raw=y.copy(),
        months=months,
        censoring_flags_by_origin=by_origin,
    )
    assert any("2025-09" in s for s in seen)
