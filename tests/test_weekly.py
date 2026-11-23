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
HIST_FIRST_MONDAY = date(2026, 8, 31)  # 12 个完整周的第一周
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


def _make_inputs(tmp_path: Path) -> tuple[Path, Path]:
    rows = []
    # KS-A：12 个完整周都有需求，周内节奏 10,20,...,120；最后一周再加周六 8、周日 22
    for k in range(12):
        wed = HIST_FIRST_MONDAY + timedelta(days=7 * k + 2)
        rows.append(_disp_row("TT_A", "KS-A", "波兰仓", wed, 10.0 * (k + 1)))
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 21), 8.0))   # 周六
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 22), 22.0))  # 周日
    # as_of 所在周（11-23 起）的需求必须排除
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 23), 1000.0))
    # 未知 UOM 的行不参与占比
    rows.append(_disp_row("TT_A", "KS-A", "波兰仓", date(2026, 11, 18), 500.0, uom="unknown"))
    # KS-B：历史上只有 2 个完整周有需求 → even
    rows.append(_disp_row("TT_B", "KS-B", "美东仓", date(2026, 11, 5), 3.0, uom="套"))
    rows.append(_disp_row("TT_B", "KS-B", "美东仓", date(2026, 11, 9), 5.0, uom="套"))
    # KS-C：已映射但最近 12 周无需求 → even，share_weeks=0
    rows.append(_disp_row("TT_C", "KS-C", "波兰仓", date(2025, 1, 6), 7.0))

    disp = pd.DataFrame(rows)
    disp_path = tmp_path / "demand_line_disposition.parquet"
    disp.to_parquet(disp_path, index=False)

    windows = pd.DataFrame(
        [
            # 3 个正常键
            dict(tongtool_sku="TT_A", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=90, p50=130.0, p90=260.0),
            dict(tongtool_sku="TT_B", canonical_warehouse="美东仓", canonical_uom="套", lead_days=90, p50=26.0, p90=52.0),
            dict(tongtool_sku="TT_C", canonical_warehouse="波兰仓", canonical_uom="个", lead_days=90, p50=13.0, p90=13.0),
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
    part = out[(out["product_id"] == product_id) & (out["warehouse"] == warehouse) & (out["uom"] == uom)]
    return part.sort_values("week_start").reset_index(drop=True)


def test_output_columns_and_week_grid(tmp_path):
    out, stats = _run(tmp_path)
    assert list(out.columns) == OUTPUT_COLUMNS
    assert stats["rows"] == 3 * WEEKS and stats["keys"] == 3

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


def test_conservation_per_key(tmp_path):
    out, _ = _run(tmp_path)
    for (pid, wh, uom), grp in out.groupby(["product_id", "warehouse", "uom"]):
        assert grp["qty"].sum() == pytest.approx(grp["qty_p90"].sum(), abs=1e-6)
    a = _key(out, "KS-A", "波兰仓", "个")
    b = _key(out, "KS-B", "美东仓", "套")
    c = _key(out, "KS-C", "波兰仓", "个")
    assert a["qty_p90"].sum() == pytest.approx(260.0, abs=1e-6)
    assert a["qty_p50"].sum() == pytest.approx(130.0, abs=1e-6)
    assert b["qty_p90"].sum() == pytest.approx(52.0, abs=1e-6)
    assert c["qty_p90"].sum() == pytest.approx(13.0, abs=1e-6)


def test_history_shares_follow_last_12_weeks(tmp_path):
    out, stats = _run(tmp_path)
    a = _key(out, "KS-A", "波兰仓", "个")
    assert set(a["share_basis"]) == {"history_12w"}
    assert set(a["share_weeks"]) == {12}
    assert "12" in a.iloc[0]["note"]

    # 期望占比：最后一周 = 120 + 周六 8 + 周日 22 = 150；11-23 起的 1000 必须排除
    hist = [10.0 * (k + 1) for k in range(11)] + [150.0]
    total = sum(hist)
    shares = [h / total for h in hist]
    denom = 1.0 + shares[0]  # 13 周 = 12 周轮廓 + 循环的第 1 周
    expect = [260.0 * s / denom for s in shares] + [260.0 * shares[0] / denom]
    assert list(a["qty_p90"].round(9)) == [round(x, 9) for x in expect]

    assert stats["share_basis"] == {"history_12w": 1, "even": 2}
    assert stats["max_conservation_error"] < 0.01


def test_even_fallback_for_short_history_and_no_history(tmp_path):
    out, _ = _run(tmp_path)
    b = _key(out, "KS-B", "美东仓", "套")
    assert set(b["share_basis"]) == {"even"}
    assert set(b["share_weeks"]) == {2}
    assert "2" in b.iloc[0]["note"]
    assert list(b["qty_p90"].round(9)) == [round(52.0 / WEEKS, 9)] * WEEKS
    assert list(b["qty_p50"].round(9)) == [round(26.0 / WEEKS, 9)] * WEEKS

    c = _key(out, "KS-C", "波兰仓", "个")
    assert set(c["share_basis"]) == {"even"}
    assert set(c["share_weeks"]) == {0}
    assert list(c["qty_p90"].round(9)) == [round(13.0 / WEEKS, 9)] * WEEKS


def test_unknown_uom_and_unmapped_are_not_guessed(tmp_path):
    out, _ = _run(tmp_path)
    assert "unknown" not in set(out["uom"])
    assert "unmapped:TT_UNMAPPED" not in set(out["product_id"])
    assert "TT_UNMAPPED" not in set(out["product_id"])
    # 未知 UOM 的 999 不能混进 KS-A 的总量
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
