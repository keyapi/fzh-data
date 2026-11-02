import importlib.util
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "tongtool_inventory_rollup_a337_v14.py"
SPEC = importlib.util.spec_from_file_location("c_refresh", SCRIPT)
C_REFRESH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C_REFRESH)


def test_refresh_args_carry_snapshot_date_and_offline_cg_path():
    args = C_REFRESH.build_parser().parse_args([
        "--date", "2026-11-02",
        "--cg-cache", "D:/snapshots/cg.parquet",
        "--run-mode", "refresh",
    ])

    assert args.date == "2026-11-02"
    assert args.cg_cache == "D:/snapshots/cg.parquet"
    assert args.run_mode == "refresh"


def test_refresh_default_outputs_are_date_scoped_and_do_not_replace_baseline():
    args = C_REFRESH.build_parser().parse_args(["--date", "2026-11-02"])

    C_REFRESH.configure_output_paths(args)

    assert args.out_xlsx.endswith("通途库存_A337_v14_refresh_2026-11-02.xlsx")
    assert args.out_report.endswith("通途库存_A337_v14_refresh_2026-11-02_报告.md")
    assert args.out_cg_cache.endswith("cg_stock_latest_2026-11-02_v14.parquet")


def test_stock_filter_uses_requested_snapshot_date():
    stock = pd.DataFrame({
        "snapshot_date": ["2026-10-28", "2026-11-02"],
        "sku": ["OLD", "NEW"],
        "available": [1, 9],
    })

    filtered = C_REFRESH.filter_stock_snapshot(stock, "2026-11-02")

    assert filtered["sku"].tolist() == ["NEW"]
    assert filtered["src_row"].tolist() == [2]


def test_cg_cache_path_is_offline_and_skips_api(monkeypatch, tmp_path):
    cache = tmp_path / "cg.parquet"
    expected = pd.DataFrame({"warehouse_id": ["CG"]})
    calls = []

    monkeypatch.setattr(C_REFRESH, "fetch_cg_stock", lambda *a, **k: calls.append("api"))
    monkeypatch.setattr(C_REFRESH.pd, "read_parquet", lambda path: expected)

    actual = C_REFRESH.load_cg_snapshot(str(cache), {}, "https://invalid.example")

    assert actual is expected
    assert calls == []


def test_cg_cache_can_be_copied_to_requested_output_path(tmp_path):
    frame = pd.DataFrame({"warehouse_id": ["CG"], "available": [7]})
    output = tmp_path / "outputs" / "cg.parquet"

    saved = C_REFRESH.persist_cg_snapshot(frame, output)

    assert saved == output
    assert pd.read_parquet(output).equals(frame)


def test_refresh_bucket_reconciliation_checks_conservation_without_old_totals():
    stock = pd.DataFrame({
        "bucket": ["计入A", "规则排除"],
        "sku": ["A", "B"],
        "available": [12.0, 5.0],
    })

    recon = C_REFRESH.reconcile_buckets(stock, "refresh")

    total = recon.loc[recon["bucket"] == "合计"].iloc[0]
    assert total["行数"] == 2
    assert total["数值和"] == 17.0
    assert total["行数差"] == 0
    assert total["数值差"] == 0
    assert recon.loc[recon["bucket"] != "合计", "基线行数"].isna().all()


def test_refresh_report_formats_unavailable_historical_baseline_as_dash():
    assert C_REFRESH.format_baseline_value(None) == "—"
    assert C_REFRESH.format_baseline_value(1234) == "1,234"
    assert C_REFRESH.format_baseline_value(1234.6) == "1,235"


def test_refresh_marks_only_historical_fixture_checks_not_applicable():
    checks = [
        ("源行数/数值和", "2 / 17", "baseline", False),
        ("C8-3 十键回放", "0/10", "10/10", False),
        ("C8-2 共享池数量守恒", "池原量=5 / 源行=1", "事实行原生量=5", True),
        ("UOM单位冲突", "0", "0", True),
    ]

    prepared, skipped = C_REFRESH.apply_run_mode_checks(checks, "refresh")

    assert skipped == 2
    assert prepared[0][1] == "not_applicable_historical_fixture"
    assert prepared[1][3] == "not_applicable_historical_fixture"
    assert prepared[2][3] is True
    assert prepared[3][3] is True


def test_refresh_report_omits_baseline_pass_claims_and_labels_historical_replays_na():
    summary = {
        "date": "2026-11-02", "rows_in": 2, "qty_in": 17.0,
        "checks_not_applicable_historical_fixture": 2,
        "uncovered_en": 4, "uom_conflict_en": 1,
        "shared_codes": 1, "c8_shared_pools": 1, "c8_shared_pool_qty": 5.0,
        "c8_shared_allocation": 0.0, "join_class": {"join_full": [1, 10.0]},
        "identity": {"唯一": 1}, "uom_status": {"已证": 2},
        "coverage": {"完整": 1, "未覆盖": 1},
        "cg_source": "offline_parquet_cache", "cg_run_id": ["run-x"],
        "cg_snapshot_at": ["2026-11-02 07:20:00"], "cg_rows": 1,
        "cg_available": 2.0, "cg_detail_rows": 1, "cg_detail_sum": 2.0,
        "cg_reconcile_ok": 1, "cg_stale": 1, "cg_avail_missing": 0,
        "cg_eligible": 0, "cg_pending": 1, "cg_owner_rows": 1,
        "cg_unknown_owner": 0, "cg_unmapped": 0, "cg_mapped_inactive": 0,
        "cg_source_rows": 2, "cg_source_stale_rows": 2,
        "cg_source_available_missing_rows": 0,
        "attribution_source": "B-v6-r10",
    }
    buckets = pd.DataFrame([
        {"桶": "计入A", "行数": 1, "数值和": 10.0, "基线行数": None,
         "基线数值和": None, "行数差": 0, "数值差": 0.0},
        {"桶": "合计", "行数": 2, "数值和": 17.0, "基线行数": 2,
         "基线数值和": 17.0, "行数差": 0, "数值差": 0.0},
    ])
    checks = [
        ("源行数/数值和", "2 / 17", "5317 / 10,360,448", False),
        ("C8-3 十键回放", "0/10", "10/10", False),
        ("15 键门禁", "FAIL=1", "0", False),
        ("C10 stale=0", "1", "0", False),
    ]
    checks, _ = C_REFRESH.apply_run_mode_checks(checks, "refresh")

    report = C_REFRESH.render_refresh_report(
        summary, buckets, checks, [("stock", "stock.parquet", "sha")],
        "content-sha", "xlsx-sha",
        Namespace(date="2026-11-02", run_mode="refresh", cg_cache="cg.parquet"),
        Path("refresh.xlsx"),
    )

    assert "not_applicable_historical_fixture" in report
    assert "与 v13 的差异" not in report
    assert "10/10" not in report
    assert "N1 门禁" not in report
    assert "stale=1" in report
    assert "eligible 0 / pending 1" in report

