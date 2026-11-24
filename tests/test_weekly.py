# -*- coding: utf-8 -*-
"""supply_copilot.weekly 的离线单元测试（合成数据，不联网）。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from supply_copilot.weekly import OUTPUT_COLUMNS, build_weekly_plan

AS_OF = "2026-11-25"  # 周三；所在周周一 = 2026-11-23
CUR_MONDAY = date(2026, 11, 23)
LAST_WEEK = date(2026, 11, 16)  # 最后一个完整周（周一）
HIST_FIRST_MONDAY = date(2026, 8, 31)  # KS-A 12 周历史的第一周
WEEKS = 13


def _disp_row(sku: str, canonical: str, warehouse: str, day: date, qty: float, uom: str = "个"):
    return {
        "tongtool_sku": sku,
        "demand_date": day.isoformat(),
        "quantity": qty,
        "canonical_sku": canonical,
        "canonical_warehouse": warehouse,
        "uom": uom,
        "mapping_status": "mapped",
    }


def _weekly_rows(sku: str, canonical: str, warehouse: str, uom: str, values: list[float]):
    """values 依次映射到以 LAST_WEEK 结尾的完整周（周三落数）；0 不落行。"""
    rows = []
    n = len(values)
    for i, v in enumerate(values):
        if v == 0:
            continue
        week = LAST_WEEK - timedelta(days=7 * (n - 1 - i))
        rows.append(_disp_row(sku, canonical, warehouse, week + timedelta(days=2), v, uom))
    return rows


def _long_series() -> dict[str, list[float]]:
    """78 周（>=52）的四种长期模式 + 一个回退场景。"""
    smooth = [5.0 + 0.5 * k for k in range(78)]
    intermittent = [10.0 if k % 4 == 0 else 0.0 for k in range(78)]
    lumpy, i = [], 0
    for k in range(78):
        if k % 5 == 0:
            lumpy.append(2.0 if i % 2 == 0 else 30.0)
            i += 1
        else:
            lumpy.append(0.0)
    # 周度模型全部给不出正预测（大额退货 + 尾段急跌/负值），但最近 12 周仍有正需求
    fallback = [5.0] * 78
    fallback[55] = -1000.0
    for k in range(66, 70):
        fallback[k] = 10.0
    for k, v in zip(range(70, 78), [30, 20, 10, 5, 2, 0, -100, 1]):
        fallback[k] = v
    return {"D": smooth, "E": intermittent, "F": lumpy, "G": fallback}


def _make_inputs(tmp_path: Path) -> tuple[Path, Path]:
    rows = []
    # KS-A：12 个完整周都有需求（周内节奏 10..120；最后一周再加周六 8、周日 22）
    for k in range(12):
        wed = HIST_FIRST_MONDAY + timedelta(days=7 * k + 2)
        rows.append(_disp_row("TT_A", "KS-A", "波兰仓", wed, 10.0 * (k + 1)))
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 21), 8.0))   # 周六
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 22), 22.0))  # 周日
    # as_of 所在周（11-23 起）的需求必须排除
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 23), 1000.0))
    # 未知 UOM 的行不参与拟合
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 18), 500.0, uom="unknown"))

    # KS-B：只有 2 个完整周 → even_split
    rows += _weekly_rows("TT_B", "KS-B", "美东仓", "套", [3.0, 5.0])
    # KS-C：已映射但只有未知 UOM 的历史 → 无有效历史 → even_split
    rows.append(_disp_row("TT_C", "KS-C", "波兰仓", date(2025, 1, 6), 7.0, uom="unknown"))

    # KS-D..G：>=52 周长期历史
    long_rows = _long_series()
    rows += _weekly_rows("TT_D", "KS-D", "波兰仓", "个", long_rows["D"])
    rows += _weekly_rows("TT_E", "KS-E", "美东仓", "个", long_rows["E"])
    rows += _weekly_rows("TT_F", "KS-F", "美东仓", "套", long_rows["F"])
    rows += _weekly_rows("TT_G", "KS-G", "波兰仓", "个", long_rows["G"])

    disp = pd.DataFrame(rows)
    disp_path = tmp_path / "demand_line_disposition.parquet"
    disp.to_parquet(disp_path, index=False)

    windows = pd.DataFrame(
        [
            dict(tongtool_sku="TT_A", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=90, p50=130.0, p90=260.0),
            dict(tongtool_sku="TT_B", canonical_warehouse="美东仓", canonical_uom="套", lead_days=90, p50=26.0, p90=52.0),
            dict(tongtool_sku="TT_C", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=90, p50=6.5, p90=13.0),
            dict(tongtool_sku="TT_D", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=90, p50=130.0, p90=260.0),
            dict(tongtool_sku="TT_E", canonical_warehouse="美东仓", canonical_uom="个", lead_days=90, p50=26.0, p90=52.0),
            dict(tongtool_sku="TT_F", canonical_warehouse="美东仓", canonical_uom="套", lead_days=90, p50=65.0, p90=130.0),
            dict(tongtool_sku="TT_G", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=90, p50=19.5, p90=39.0),
            # 其他窗口不计
            dict(tongtool_sku="TT_A", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=60, p50=1000.0, p90=2000.0),
            # 未知 UOM 不猜
            dict(tongtool_sku="TT_A", canonical_warehouse="波兰仓", canonical_uom="unknown", lead_days=90, p50=999.0, p90=999.0),
            # 未映射 SKU 不输出
            dict(tongtool_sku="TT_UNMAPPED", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=90, p50=50.0, p90=50.0),
            # service=p90 为空 → 该行不参与
            dict(tongtool_sku="TT_B", canonical_warehouse="美东仓", canonical_uom="套", lead_days=90, p50=999.0, p90=None),
        ]
    )
    windows_path = tmp_path / "forecast_sku_warehouse_windows.parquet"
    windows.to_parquet(windows_path, index=False)
    return disp_path, windows_path


def _run(tmp_path: Path, *, service: str = "p90", as_of=AS_OF):
    disp_path, windows_path = _make_inputs(tmp_path)
    out_path = tmp_path / "weekly_plan.parquet"
    stats = build_weekly_plan(
        disp_path, windows_path, out_path, as_of=as_of, weeks=WEEKS, service=service
    )
    return pd.read_parquet(out_path), stats


def _key(out: pd.DataFrame, product_id: str, warehouse: str, uom: str) -> pd.DataFrame:
    part = out[
        (out["product_id"] == product_id)
        & (out["warehouse"] == warehouse)
        & (out["uom"] == uom)
    ]
    return part.sort_values("week_start").reset_index(drop=True)



def _uniform_expected(total: float, frame) -> list[float]:
    """按 covered_days 折算后的均匀周量（首尾部分周）。"""
    cov = [int(x) for x in frame["covered_days"].tolist()]
    return [total * c / sum(cov) for c in cov]

def test_output_columns_and_week_grid(tmp_path):
    out, stats = _run(tmp_path)
    assert list(out.columns) == OUTPUT_COLUMNS
    assert stats["rows"] == 7 * WEEKS and stats["keys"] == 7

    for _, grp in out.groupby(["product_id", "warehouse", "uom"]):
        starts = pd.to_datetime(grp.sort_values("week_start")["week_start"])
        assert len(starts) == WEEKS
        assert all(s.weekday() == 0 for s in starts), "周起点必须是周一"
        assert starts.iloc[0].date() == CUR_MONDAY
        ends = pd.to_datetime(grp.sort_values("week_start")["week_end"])
        assert all(e.weekday() == 6 for e in ends), "周终点必须是周日"

    assert stats["dropped"] == {
        "other_lead_days": 1,
        "no_forecast": 1,
        "unknown_uom": 1,
        "unmapped_sku": 1,
    }
    assert stats["method_counts"] == {
        "ets": 1,
        "sba": 1,
        "tsb": 1,
        "share_12w": 1,
        "ma_4_8w": 1,
        "even_split": 2,
    }
    assert stats["backtest"]["keys"] == 3


def test_conservation_per_key(tmp_path):
    out, _ = _run(tmp_path)
    for _, grp in out.groupby(["product_id", "warehouse", "uom"]):
        assert grp["qty"].sum() == pytest.approx(grp["qty_p90"].sum(), abs=1e-6)
        assert grp["qty_p50"].sum() == pytest.approx(grp["qty_p50"].sum(), abs=1e-6)
    expected_p90 = {"KS-A": 260.0, "KS-B": 52.0, "KS-C": 13.0, "KS-D": 260.0,
                    "KS-E": 52.0, "KS-F": 130.0, "KS-G": 39.0}
    for pid, total in expected_p90.items():
        grp = out[out["product_id"] == pid]
        assert grp["qty_p90"].sum() == pytest.approx(total, abs=1e-6)


def test_short_history_uses_recent_mean(tmp_path):
    out, _ = _run(tmp_path)
    a = _key(out, "KS-A", "波兰仓", "个")
    assert set(a["method"]) == {"ma_4_8w"}
    assert set(a["share_basis"]) == {"history_4_8w"}
    assert set(a["share_weeks"]) == {12}
    assert set(a["fallback_reason"]) == {"history_weeks_12_lt_52"}
    assert list(a["qty_p90"].round(6)) == [round(x, 6) for x in _uniform_expected(260.0, a)]
    assert list(a["qty_p50"].round(6)) == [round(x, 6) for x in _uniform_expected(130.0, a)]


def test_even_fallback_for_tiny_or_no_history(tmp_path):
    out, _ = _run(tmp_path)
    b = _key(out, "KS-B", "美东仓", "套")
    assert set(b["method"]) == {"even_split"}
    assert set(b["share_weeks"]) == {2}
    assert set(b["fallback_reason"]) == {"history_weeks_2_lt_4"}
    assert list(b["qty_p90"].round(6)) == [round(x, 6) for x in _uniform_expected(52.0, b)]
    assert list(b["qty_p50"].round(6)) == [round(x, 6) for x in _uniform_expected(26.0, b)]

    c = _key(out, "KS-C", "波兰仓", "个")
    assert set(c["method"]) == {"even_split"}
    assert set(c["share_weeks"]) == {0}
    assert set(c["fallback_reason"]) == {"no_history"}
    assert list(c["qty_p90"].round(6)) == [round(x, 6) for x in _uniform_expected(13.0, c)]


def test_long_smooth_history_uses_ets_with_backtest(tmp_path):
    out, stats = _run(tmp_path)
    d = _key(out, "KS-D", "波兰仓", "个")
    assert set(d["method"]) == {"ets"}
    assert set(d["share_basis"]) == {"model"}
    assert set(d["share_weeks"]) == {78}
    assert set(d["fallback_reason"]) == {""}
    assert d["backtest_wape"].notna().all()
    assert (d["backtest_wape"] >= 0).all()
    # 线性上升 → ETS 周形状递增
    qty = d["qty_p90"].tolist()
    assert all(b > a - 1e-9 for a, b in zip(qty, qty[1:]))
    assert d["qty_p90"].sum() == pytest.approx(260.0, abs=1e-6)
    assert stats["backtest"]["median_cumulative_wape"] is not None


def test_long_intermittent_and_lumpy_use_sba_tsb(tmp_path):
    out, _ = _run(tmp_path)
    e = _key(out, "KS-E", "美东仓", "个")
    f = _key(out, "KS-F", "美东仓", "套")
    assert set(e["method"]) == {"sba"} and set(f["method"]) == {"tsb"}
    assert set(e["share_basis"]) == {"model"} and set(f["share_basis"]) == {"model"}
    # SBA/TSB 给的是周均速率 → 周形状均匀
    assert list(e["qty_p90"].round(6)) == [round(x, 6) for x in _uniform_expected(52.0, e)]
    assert list(f["qty_p90"].round(6)) == [round(x, 6) for x in _uniform_expected(130.0, f)]
    assert e["backtest_wape"].notna().all() and f["backtest_wape"].notna().all()


def test_share_12w_is_last_resort_not_default(tmp_path):
    out, _ = _run(tmp_path)
    g = _key(out, "KS-G", "波兰仓", "个")
    assert set(g["method"]) == {"share_12w"}
    assert set(g["share_basis"]) == {"share_12w"}
    assert all("no_positive_forecast" in r for r in g["fallback_reason"])
    assert g["backtest_wape"].isna().all()
    assert g["qty_p90"].sum() == pytest.approx(39.0, abs=1e-6)
    assert 0 < (g["qty_p90"] > 0).sum() < WEEKS  # 12 周轮廓铺到 13 周，形状不恒定


def test_unknown_uom_and_unmapped_are_not_guessed(tmp_path):
    out, _ = _run(tmp_path)
    assert "unknown" not in set(out["uom"])
    assert "unmapped:TT_UNMAPPED" not in set(out["product_id"])
    assert "TT_UNMAPPED" not in set(out["product_id"])
    a = _key(out, "KS-A", "波兰仓", "个")
    assert a["qty_p90"].sum() == pytest.approx(260.0, abs=1e-6)


def test_service_p50_selects_p50_column_and_accepts_date(tmp_path):
    out, stats = _run(tmp_path, service="p50", as_of=date(2026, 11, 25))
    a = _key(out, "KS-A", "波兰仓", "个")
    assert stats["service"] == "p50"
    assert a["qty"].sum() == pytest.approx(130.0, abs=1e-6)
    assert (a["qty"] - a["qty_p50"]).abs().max() < 1e-9


def test_rejects_bad_service(tmp_path):
    disp_path, windows_path = _make_inputs(tmp_path)
    with pytest.raises(ValueError):
        build_weekly_plan(
            disp_path, windows_path, tmp_path / "x.parquet", as_of=AS_OF, service="p95"
        )
