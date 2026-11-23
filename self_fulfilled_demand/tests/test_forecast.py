# -*- coding: utf-8 -*-
"""预测层离线测试（合成数据；不联网、不读生产存储）。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from self_fulfilled_demand import forecast as F


class FakeBackend:
    """确定性后端：用近 3 月均值，避免测试依赖 statsforecast。"""

    name = "fake"
    version = "0.0-test"

    def forecast(self, y: np.ndarray, h: int, season_length: int) -> np.ndarray:
        k = min(3, len(y))
        return np.repeat(float(np.mean(y[-k:])), h)


def _months(first: str, last: str) -> list[str]:
    return F.month_range(first, last)


def _rows_for_sku(
    sku: str,
    months: list[str],
    *,
    base: float = 10.0,
    warehouse: str = "美东-CENTRADE",
) -> list[dict]:
    rows = []
    for i, m in enumerate(months):
        rows.append(
            {
                "tongtool_sku": sku,
                "demand_date": f"{m}-01",
                "quantity": base + (i % 5),
                "in_main_series": True,
                "fulfillment_scope": "self_fulfilled_candidate",
                "canonical_warehouse": warehouse,
                "canonical_sku": f"CANON-{sku}",
                "mapping_status": "mapped",
            }
        )
    return rows


def make_inputs(root: Path) -> tuple[Path, Path]:
    rows: list[dict] = []
    # A：2023-01..2026-09 完整 45 个月；另有 2022-12 与 2026-10 两个不足月
    rows += [
        {
            "tongtool_sku": "A",
            "demand_date": "2022-12-20",
            "quantity": 99,
            "in_main_series": True,
            "fulfillment_scope": "self_fulfilled_candidate",
            "canonical_warehouse": "美东-CENTRADE",
            "canonical_sku": "CANON-A",
            "mapping_status": "mapped",
        }
    ]
    rows += _rows_for_sku("A", _months("2023-01", "2026-09"))
    rows += [
        {
            "tongtool_sku": "A",
            "demand_date": "2026-10-05",
            "quantity": 7,
            "in_main_series": True,
            "fulfillment_scope": "self_fulfilled_candidate",
            "canonical_warehouse": "美东-CENTRADE",
            "canonical_sku": "CANON-A",
            "mapping_status": "mapped",
        }
    ]
    # B：3 个完整月（短史 MA3），两个仓
    rows += _rows_for_sku("B", _months("2026-07", "2026-08"), warehouse="美东-CENTRADE")
    rows += _rows_for_sku("B", ["2026-07", "2026-08", "2026-09"], warehouse="美中-FZH-DANEEY")
    # C：1 个完整月（末值）
    rows += _rows_for_sku("C", ["2026-09"])
    # D：只有不足月 → 不可预测
    rows += [
        {
            "tongtool_sku": "D",
            "demand_date": "2026-10-10",
            "quantity": 4,
            "in_main_series": True,
            "fulfillment_scope": "self_fulfilled_candidate",
            "canonical_warehouse": "波兰-FZHPoland-covers",
            "canonical_sku": "unmapped:D",
            "mapping_status": "unmapped",
        }
    ]
    # E：非主序列（应被过滤）
    rows += [
        {
            "tongtool_sku": "E",
            "demand_date": "2026-08-01",
            "quantity": 1000,
            "in_main_series": False,
            "fulfillment_scope": "self_fulfilled_candidate",
            "canonical_warehouse": "美东-CENTRADE",
            "canonical_sku": "CANON-E",
            "mapping_status": "mapped",
        }
    ]
    dispo = pd.DataFrame(rows)
    dispo_path = root / "disposition.parquet"
    dispo.to_parquet(dispo_path, index=False)

    cov = pd.DataFrame(
        [
            {
                "tongtool_sku": "A",
                "ready_rows": 45,
                "blocked_rows": 0,
                "block_reasons": "",
                "canonical_sku": "CANON-A",
                "mapping_status": "mapped",
                "uom": "个",
                "uom_status": "known_piece",
            },
            {
                "tongtool_sku": "B",
                "ready_rows": 5,
                "blocked_rows": 1,
                "block_reasons": "subwarehouse_identity_unproven",
                "canonical_sku": "CANON-B",
                "mapping_status": "mapped",
                "uom": "个",
                "uom_status": "known_piece",
            },
            {
                "tongtool_sku": "C",
                "ready_rows": 0,
                "blocked_rows": 1,
                "block_reasons": "uom_missing",
                "canonical_sku": "CANON-C",
                "mapping_status": "mapped",
                "uom": "套",
                "uom_status": "known_piece",
            },
            {
                "tongtool_sku": "D",
                "ready_rows": 0,
                "blocked_rows": 1,
                "block_reasons": "sku_mapping_missing",
                "canonical_sku": "unmapped:D",
                "mapping_status": "unmapped",
                "uom": None,
                "uom_status": "missing",
            },
        ]
    )
    cov_path = root / "coverage.parquet"
    cov.to_parquet(cov_path, index=False)
    return dispo_path, cov_path


def _run(tmp_path: Path, **kwargs) -> Path:
    dispo, cov = make_inputs(tmp_path)
    cfg = F.ForecastConfig(
        decision_date=date(2026, 10, 29), max_backtest_origins=4, **kwargs
    )
    return F.run(
        disposition_path=dispo,
        coverage_path=cov,
        out_root=tmp_path / "out",
        cfg=cfg,
        run_id="test-run",
        backend=FakeBackend(),
    )


def test_month_boundary_detects_partial_months() -> None:
    df = pd.DataFrame(
        {
            "tongtool_sku": ["A", "A"],
            "demand_date": ["2022-12-20", "2026-10-05"],
            "quantity": [1.0, 2.0],
            "in_main_series": [True, True],
            "fulfillment_scope": ["self_fulfilled_candidate", "self_fulfilled_candidate"],
            "canonical_warehouse": ["w", "w"],
            "canonical_sku": ["c", "c"],
            "mapping_status": ["mapped", "mapped"],
        }
    )
    b = F.resolve_month_boundary(df)
    assert b["partial_months"] == ["2022-12", "2026-10"]
    assert b["complete_month_first"] == "2023-01"
    assert b["complete_month_last"] == "2026-09"


def test_window_weights_sum_matches_days() -> None:
    for days in (60, 90, 120):
        w = F.window_weights(date(2026, 10, 29), days)
        assert abs(sum(w.values()) - days / 30.4375) < 0.05


def test_conformal_q_returns_upper_order_statistic() -> None:
    xs = list(range(1, 11))
    assert F.conformal_q(xs, 0.8) >= 7
    assert F.conformal_q([], 0.8) == 0.0


def test_run_end_to_end_and_partial_month_excluded(tmp_path: Path) -> None:
    out = _run(tmp_path)
    frames = {
        n: pd.read_parquet(out / f"{n}.parquet")
        for n in (
            "forecast_sku_summary",
            "forecast_sku_monthly",
            "forecast_sku_windows",
            "forecast_sku_warehouse_monthly",
        )
    }
    s = frames["forecast_sku_summary"].set_index("tongtool_sku")

    # E 不在主序列
    assert "E" not in s.index
    assert set(s.index) == {"A", "B", "C", "D"}

    # 不足月不进入历史
    assert s.loc["A", "history_first_month"] == "2023-01"
    assert s.loc["A", "history_last_month"] == "2026-09"
    assert s.loc["A", "history_months"] == 45
    assert s.loc["A", "partial_month"] == "2026-10"
    assert s.loc["A", "partial_month_observed_units"] == 7.0
    assert s.loc["A", "partial_month_days"] == 10

    # 不可预测不是 0
    assert s.loc["D", "forecast_status"] == F.STATUS_NO_HISTORY
    assert pd.isna(s.loc["D", "p50_l90"])
    assert s.loc["D", "forecast_eligible"] == False  # noqa: E712

    # 短史规则
    assert s.loc["B", "forecast_status"] == "ok_short_ma3"
    assert s.loc["C", "forecast_status"] == "ok_short_naive"

    # 预测月 = 2026-10..2027-04（覆盖 L180）
    months = sorted(frames["forecast_sku_monthly"]["forecast_month"].unique())
    assert months == [
        "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04",
    ]

    # 区间顺序与未知
    ok = s[s["forecast_eligible"]]
    assert ok["p50_l90"].notna().all()
    assert (ok["p10_l90"] <= ok["p50_l90"] + 1e-6).all()
    assert (ok["p50_l90"] <= ok["p90_l90"] + 1e-6).all()


def test_warehouse_shares_and_unknown_allocation(tmp_path: Path) -> None:
    out = _run(tmp_path)
    wh = pd.read_parquet(out / "forecast_sku_warehouse_monthly.parquet")
    b = wh[wh["tongtool_sku"] == "B"]
    grouped = b.groupby("forecast_month")["allocation_share"].sum()
    assert np.allclose(grouped.values, 1.0)

    c = wh[wh["tongtool_sku"] == "C"]
    # C 有近 3 月销量（2026-09）→ 正常分配
    assert c["allocation_status"].iloc[0] == "allocated_by_recent_share"

    d = wh[wh["tongtool_sku"] == "D"]
    # D 没有完整月 → 无近期销量，分配是 null 不是 0
    assert (d["allocation_status"] == "no_recent_sales").all()
    assert d["allocation_share"].isna().all()
    assert d["p50"].isna().all()


def test_manifest_has_lineage_and_validation(tmp_path: Path) -> None:
    out = _run(tmp_path)
    man = json.loads((out / "forecast_manifest.json").read_text(encoding="utf-8"))
    assert man["schema_version"] == F.SCHEMA_VERSION
    assert man["inputs"]["disposition"]["sha256"]
    assert man["inputs"]["coverage"]["sha256"]
    assert man["run"]["data_cutoff"] == "2026-10-10"
    assert man["run"]["partial_months"] == ["2022-12", "2026-10"]
    assert man["run"]["partial_month"] == "2026-10"
    assert man["validation"]["status"] == "passed"
    assert man["reconciliation"]["check_used_equals_complete_plus_partial"] is True
    assert man["model"]["interval"]["calibrated"] is False
    assert man["model"]["horizon_policy"]["scenario_only_leads"] == [180]
    assert man["model"]["horizon_policy"]["unchanged_core_leads"] == [60, 90, 120]
    assert man["supersedes"]
    assert (out.parent / "CURRENT").read_text(encoding="utf-8") == "test-run"


def test_validate_rejects_bad_interval(tmp_path: Path) -> None:
    out = _run(tmp_path)
    s = pd.read_parquet(out / "forecast_sku_summary.parquet")
    s.loc[s["forecast_eligible"], "p10_l90"] = 10_000.0
    frames = {
        "forecast_sku_summary": s,
        "forecast_sku_monthly": pd.read_parquet(out / "forecast_sku_monthly.parquet"),
        "forecast_sku_windows": pd.read_parquet(out / "forecast_sku_windows.parquet"),
        "forecast_sku_warehouse_monthly": pd.read_parquet(
            out / "forecast_sku_warehouse_monthly.parquet"
        ),
        "forecast_uom_totals": pd.read_parquet(out / "forecast_uom_totals.parquet"),
    }
    with pytest.raises(F.ValidationError):
        F.validate_frames(frames, F.ForecastConfig())


def test_interval_direction_underforecast_expands_upper() -> None:
    """pred-actual 全为负（持续低估）→ 需求上界必须扩张，下界不扩张。"""
    p50 = np.array([20.0])
    errors = [-10.0, -10.0, -10.0, -10.0]  # 每次低估 10
    p10, p90 = F._interval_from_errors(errors, p50, 0.8)
    assert float(p10[0]) == 20.0
    assert float(p90[0]) == 30.0


def test_interval_direction_overforecast_expands_lower() -> None:
    """pred-actual 全为正（持续高估）→ 需求下界必须扩张，上界不扩张。"""
    p50 = np.array([20.0])
    errors = [10.0, 10.0, 10.0, 10.0]  # 每次高估 10
    p10, p90 = F._interval_from_errors(errors, p50, 0.8)
    assert float(p10[0]) == 10.0
    assert float(p90[0]) == 20.0


def test_interval_direction_real_sample_tt0312701() -> None:
    """真实 Top SKU TT0312701K0064561 的回测误差方向：四次全低估，上界应扩张。"""
    errors = [-133.0, -4.6666667, -81.0, -54.3333333]
    p50 = np.array([185.8284])
    p10, p90 = F._interval_from_errors(errors, p50, 0.8)
    assert float(p10[0]) <= float(p50[0])
    assert float(p90[0]) > float(p50[0])


def test_uom_totals_are_grouped_not_cross_summed(tmp_path: Path) -> None:
    out = _run(tmp_path)
    s = pd.read_parquet(out / "forecast_sku_summary.parquet")
    ut = pd.read_parquet(out / "forecast_uom_totals.parquet")
    # A/B = 个，C = 套，D = unknown
    assert set(s.loc[s["forecast_eligible"], "uom_group"]) == {"个", "套"}
    for group in ("个", "套"):
        for d in (60, 90, 120):
            expected = s[(s["uom_group"] == group) & s["forecast_eligible"]][
                f"p50_l{d}"
            ].sum()
            got = ut[(ut["uom_group"] == group) & (ut["lead_days"] == d)]["p50_sum"].iloc[0]
            assert abs(float(got) - float(expected)) < 0.01
    # unknown 组禁止合计，且没有全表统一合计行
    unknown = ut[ut["uom_group"] == "unknown"]
    assert len(unknown) == 4
    assert (~unknown["totals_allowed"]).all()
    assert "all" not in set(ut["uom_group"])


def test_zero_forecast_stats_use_correct_denominators() -> None:
    s = pd.DataFrame(
        {
            "forecast_eligible": [True, True, True, True, False],
            "p50_l90": [0.0, 0.0, 10.0, 0.0, None],
            "p90_l90": [5.0, 0.0, 20.0, 0.0, None],
            "negative_clipped": [True, False, True, True, False],
        }
    )
    z = F.zero_forecast_stats(s)
    assert z["forecastable"] == 4
    assert z["zero_p50_l90"] == 3
    assert z["negative_clipped_all"] == 3
    assert z["zero_p50_and_clipped"] == 2
    assert z["positive_p50_and_clipped"] == 1
    assert z["zero_p50_with_p90_gt_0"] == 1
    assert z["zero_p50_clipped_with_p90_gt_0"] == 1
    assert z["zero_p50_with_p90_eq_0"] == 2


def test_no_backend_uses_documented_fallback(tmp_path: Path) -> None:
    dispo, cov = make_inputs(tmp_path)
    out = F.run(
        disposition_path=dispo,
        coverage_path=cov,
        out_root=tmp_path / "out",
        cfg=F.ForecastConfig(decision_date=date(2026, 10, 29), max_backtest_origins=2),
        run_id="no-backend",
        backend=None,
    )
    s = pd.read_parquet(out / "forecast_sku_summary.parquet").set_index("tongtool_sku")
    assert s.loc["A", "forecast_method"] == "ma3"
    assert s.loc["A", "forecast_status"] == "ok_fallback_ma3"
    assert "statsforecast 不可用" in s.loc["A", "forecast_method_reason"]


def test_autoets_smoke_if_available() -> None:
    backend = F.load_backend()
    if backend is None:
        pytest.skip("statsforecast 不可用")
    y = np.array([10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17] * 3, dtype=float)
    pred, method, reason, clipped = F.fit_predict_rule(
        y, 5, backend, F.ForecastConfig()
    )
    assert method == "autoets"
    assert len(pred) == 5
    assert not clipped or (pred >= 0).all()
