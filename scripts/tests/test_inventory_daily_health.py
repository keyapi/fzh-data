from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "web_automation" / "legacy-compatible"))

import inventory_daily_health as health  # noqa: E402
from tongtu_urls import is_inventory_url, looks_like_erp_url  # noqa: E402


def test_parse_snapshot_date() -> None:
    assert health.parse_snapshot_date(Path("通途合并库存结存清单 20261022_0253.xlsx")) == date(2026, 10, 22)
    assert health.parse_snapshot_date(Path("通途合并库存结存清单20261021_0217.xlsx")) == date(2026, 10, 21)
    assert health.parse_snapshot_date(Path("not-a-snapshot.xlsx")) is None


def test_count_deviation_boundaries() -> None:
    assert health.count_deviation(100, None) == (None, None)
    assert health.count_deviation(110, 100) == (None, pytest.approx(0.10))
    assert health.count_deviation(125, 100)[0] == health.WARN
    assert health.count_deviation(160, 100)[0] == health.FAIL
    assert health.count_deviation(0, 100)[0] == health.FAIL


def test_worst_and_finish_status() -> None:
    assert health.worst([health.OK, health.WARN, health.OK]) == health.WARN
    assert health.worst([health.OK, health.FAIL, health.WARN]) == health.FAIL
    assert health.finish_status([], []) == health.OK
    assert health.finish_status([], ["warn"]) == health.WARN
    assert health.finish_status(["fail"], ["warn"]) == health.FAIL


def test_looks_like_erp_url() -> None:
    assert looks_like_erp_url("https://erp102.tongtool.com/dashboard/homepage/index.htm")
    assert looks_like_erp_url("https://erp102.tongtool.com/j_security_check?ticket=x")
    assert not looks_like_erp_url("https://passport.tongtool.com/?u=https%3A%2F%2Ferp102.tongtool.com")
    assert not looks_like_erp_url("")
    assert not looks_like_erp_url(None)
    assert is_inventory_url("https://erp102.tongtool.com/warehouse/goodsbalance/index.htm?warehouse=1")
    assert not is_inventory_url("https://erp102.tongtool.com/dashboard/homepage/index.htm")


def _write_snapshot(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "通途合并库存结存清单 20260101_0200.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_parity_check_counts_and_diffs(tmp_path: Path) -> None:
    excel = _write_snapshot(
        tmp_path,
        [
            {"SKU": "A", "仓库": "美东-CENTRADE", "可用库存": 10, "在途库存": 1, "待发库存": 0, "故障品库存": 0},
            {"SKU": "B", "仓库": "美东-CENTRADE", "可用库存": 5, "在途库存": 0, "待发库存": 0, "故障品库存": 0},
        ],
    )
    day_dir = tmp_path / "api" / "2026-01-01"
    _write_jsonl(
        day_dir / "warehouse=1_美东-CENTRADE.jsonl",
        [
            {"goodsSku": "A", "warehouseName": "美东-CENTRADE", "availableStockQuantity": 10,
             "intransitStockQuantity": 1, "waitingShipmentStockQuantity": 0, "defectsStockQuantity": 0},
            {"goodsSku": "B", "warehouseName": "美东-CENTRADE", "availableStockQuantity": 4,
             "intransitStockQuantity": 0, "waitingShipmentStockQuantity": 0, "defectsStockQuantity": 0},
            {"goodsSku": "C", "warehouseName": "美东-CENTRADE", "availableStockQuantity": 9,
             "intransitStockQuantity": 0, "waitingShipmentStockQuantity": 0, "defectsStockQuantity": 0},
        ],
    )
    manifest = {
        "complete": True,
        "warehouses": [
            {"warehouseName": "美东-CENTRADE", "file": str(day_dir / "warehouse=1_美东-CENTRADE.jsonl"), "rows": 3},
        ],
    }
    manifest_path = day_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    result = health.parity_check(
        date(2026, 1, 1),
        {"file": str(excel), "status": "OK"},
        {"manifest": str(manifest_path), "status": "OK"},
        tmp_path / "api",
    )
    assert result["overlap"] == 2
    assert result["excel_only"] == 0
    assert result["api_only"] == 1
    assert result["api_only_nonzero"] == 1
    assert result["diff_rows"] == 1
    assert result["diff_fields"]["可用库存"] == 1
    # 1/2 overlap differs = 50% -> FAIL
    assert result["status"] == health.FAIL


def test_parity_check_skips_when_side_missing(tmp_path: Path) -> None:
    result = health.parity_check(
        date(2026, 1, 1),
        {"file": None, "status": health.FAIL},
        {"manifest": None, "status": health.FAIL},
        tmp_path,
    )
    assert result["status"] == "SKIPPED"
    assert result["reasons"]


def test_read_excel_full_requires_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    pd.DataFrame([{"SKU": "A", "仓库": "美东-CENTRADE"}]).to_excel(path, index=False)
    _, missing = health.read_excel_full(path)
    assert "可用库存" in missing
