"""Tests for Tongtu warehouse name / inventory filename matching."""

from __future__ import annotations

import sys
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[2] / "web_automation" / "legacy-compatible"
sys.path.insert(0, str(LEGACY))

from tongtu_warehouses import (
    WAREHOUSES,
    inventory_download_matches_warehouse,
    should_exit_after_export_run,
)  # noqa: E402


def test_inventory_download_distinguishes_main_and_return_warehouse():
    main = "美东-CENTRADE"
    ret = "美东-CENTRADE-退货产品仓"
    main_file = "美东-CENTRADE_库存结存清单20260101_120000.xlsx"
    ret_file = "美东-CENTRADE-退货产品仓_库存结存清单20260102_120000.xlsx"

    assert inventory_download_matches_warehouse(main_file, main)
    assert not inventory_download_matches_warehouse(ret_file, main)
    assert inventory_download_matches_warehouse(ret_file, ret)
    assert not inventory_download_matches_warehouse(main_file, ret)


def test_warehouses_has_six_mainline_entries():
    assert len(WAREHOUSES) == 6


def test_skipped_empty_does_not_fail_scheduled_run():
    assert not should_exit_after_export_run([])
    assert should_exit_after_export_run(["美中-FZH-DANEEY（选仓失败）"])
