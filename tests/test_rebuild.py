# -*- coding: utf-8 -*-
"""rebuild.build_demand / rebuild 的离线测试：无网络、无 statsforecast。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from supply_copilot.rebuild import DISPOSITION_COLUMNS, build_demand, rebuild

ALIASES = Path(__file__).resolve().parents[1] / "self_fulfilled_demand" / "warehouse_aliases.json"


@pytest.fixture()
def dataset(tmp_path: Path) -> dict[str, Path]:
    """10 行合成订单：映射/未映射/歧义、FBA、第三方仓、无日期、无 SKU、零数量。"""
    orders = pd.DataFrame(
        [
            # sku, sale_date, qty, warehouse
            ("TT-MAPPED", "2026-01-05", 2, "CENTRADE"),
            ("TT-MAPPED", "2026-02-03", 1, "CENTRADE"),
            ("TT-NO-UOM", "2026-01-10", 1, "FZH-DANEEY"),
            ("TT-UNMAPPED", "2026-01-11", 3, "休斯顿1号仓"),
            ("TT-AMBIG", "2026-01-12", 1, "FZHPoland-covers"),
            ("TT-FBA", "2026-01-13", 5, "美国FBA仓"),
            ("TT-TP", "2026-01-14", 4, "WayfairCG-Cranbury仓"),
            ("TT-NODATE", None, 1, "CENTRADE"),
            (None, "2026-01-15", 2, "CENTRADE"),
            ("TT-ZERO", "2026-01-16", 0, "CENTRADE"),
        ],
        columns=["sku_tongtool", "sale_date", "qty", "warehouse"],
    )
    orders["sale_date"] = pd.to_datetime(orders["sale_date"])
    orders_path = tmp_path / "orders.parquet"
    orders.to_parquet(orders_path, index=False)

    sku_map = tmp_path / "sku_map.tsv"
    sku_map.write_text(
        "\n".join(
            [
                "KS-A\tTT-MAPPED\t",
                "KS-B\tTT-NO-UOM\t",
                "KS-Z\tTT-ZERO\t",
                # 一对多 → ambiguous
                "KS-AMB1\tTT-AMBIG\t",
                "KS-AMB2\tTT-AMBIG\t",
                "",
            ]
        ),
        encoding="utf-8",
    )

    uom = pd.DataFrame(
        [
            {"item_code": "KS-A", "stock_uom": "个", "item_name": "A", "is_stock_item": 1, "fetched_at": "t", "source": "test"},
            {"item_code": "KS-Z", "stock_uom": "个", "item_name": "Z", "is_stock_item": 1, "fetched_at": "t", "source": "test"},
            # KS-B 故意缺失 → uom_missing
        ]
    )
    uom_path = tmp_path / "uom.parquet"
    uom.to_parquet(uom_path, index=False)

    return {
        "orders": orders_path,
        "sku_map": sku_map,
        "uom": uom_path,
        "out": tmp_path / "out",
    }


def test_build_demand_partitions_and_conserves(dataset, tmp_path):
    stats = build_demand(
        dataset["orders"],
        sku_map_path=dataset["sku_map"],
        warehouse_aliases=ALIASES,
        uom_cache_path=dataset["uom"],
        out_dir=dataset["out"],
    )

    disp = pd.read_parquet(dataset["out"] / "demand_line_disposition.parquet")
    # 列：forecast 的 8 列全在（外加 uom 证据列）
    assert set(DISPOSITION_COLUMNS).issubset(disp.columns)
    for col in DISPOSITION_COLUMNS:
        assert col in disp.columns
    # 只写纳入行，且全部在主序列
    assert len(disp) == 6
    assert disp["in_main_series"].all()
    assert set(disp["fulfillment_scope"]) == {"self_fulfilled_candidate"}

    # 统计守恒：入 = 出 + 排除
    assert stats["input_rows"] == 10
    assert stats["output_rows"] == 6
    assert stats["excluded_rows"] == 4
    assert stats["input_rows"] == stats["output_rows"] + sum(stats["excluded"].values())
    assert stats["excluded"] == {"no_sku": 1, "no_date": 1, "fba": 1, "third_party": 1}
    assert pd.Timestamp(stats["output_date_min"]) <= pd.Timestamp(stats["output_date_max"])

    # 映射口径：未知不猜，写 unmapped:/ambiguous:
    sku_to_canonical = dict(zip(disp["tongtool_sku"], disp["canonical_sku"]))
    assert sku_to_canonical["TT-UNMAPPED"] == "unmapped:TT-UNMAPPED"
    assert sku_to_canonical["TT-AMBIG"] == "ambiguous:TT-AMBIG"
    assert sku_to_canonical["TT-MAPPED"] == "KS-A"
    assert stats["mapping"]["mapping_rate"] == pytest.approx(4 / 6, abs=1e-4)

    # 仓库别名解析
    wh = dict(zip(disp["tongtool_sku"], disp["canonical_warehouse"]))
    assert wh["TT-MAPPED"] == "美东-CENTRADE"
    assert wh["TT-AMBIG"] == "波兰-FZHPoland-covers"


def test_coverage_keeps_block_reasons_and_forecast_columns(dataset):
    build_demand(
        dataset["orders"],
        sku_map_path=dataset["sku_map"],
        warehouse_aliases=ALIASES,
        uom_cache_path=dataset["uom"],
        out_dir=dataset["out"],
    )
    cov = pd.read_parquet(dataset["out"] / "sku_coverage.parquet")
    # forecast.assemble 需要这些列
    for col in ("tongtool_sku", "ready_rows", "blocked_rows", "block_reasons",
                "canonical_sku", "mapping_status", "uom", "uom_status"):
        assert col in cov.columns

    by_sku = cov.set_index("tongtool_sku")
    assert by_sku.loc["TT-MAPPED", "ready_rows"] == 2
    assert by_sku.loc["TT-MAPPED", "blocked_rows"] == 0
    assert "quantity_invalid" in by_sku.loc["TT-ZERO", "block_reasons"]
    assert "sku_mapping_missing" in by_sku.loc["TT-UNMAPPED", "block_reasons"]
    assert "uom_missing" in by_sku.loc["TT-NO-UOM", "block_reasons"]
    assert "sku_mapping_ambiguous" in by_sku.loc["TT-AMBIG", "block_reasons"]
    assert "warehouse_identity_unknown" in by_sku.loc["TT-UNMAPPED", "block_reasons"]
    # 已知件类单位才写具体 UOM，否则 unknown
    assert by_sku.loc["TT-MAPPED", "uom"] == "个"
    assert by_sku.loc["TT-NO-UOM", "uom_status"] == "missing"
    assert "__TOTAL__" in by_sku.index


def test_as_of_filters_future_orders(dataset):
    stats = build_demand(
        dataset["orders"],
        sku_map_path=dataset["sku_map"],
        warehouse_aliases=ALIASES,
        uom_cache_path=dataset["uom"],
        out_dir=dataset["out"],
        as_of="2026-01-16",
    )
    # 2026-02-03 的那行被 as_of 截掉
    assert stats["as_of_filtered_rows"] == 1
    assert stats["input_rows"] == 9
    assert stats["input_rows"] == stats["output_rows"] + sum(stats["excluded"].values())


def test_rebuild_writes_manifest(monkeypatch, dataset):
    from supply_copilot import rebuild as rebuild_mod

    calls = {}

    def fake_run_forecast(out_dir, *, decision_date, lead_days=90, no_statsforecast=False, **kwargs):
        calls["decision_date"] = decision_date
        return {"run_id": "RUN-TEST", "run_dir": str(Path(out_dir) / "forecast" / "RUN-TEST")}

    monkeypatch.setattr(rebuild_mod, "run_forecast", fake_run_forecast)
    manifest = rebuild(
        dataset["orders"],
        dataset["out"],
        sku_map_path=dataset["sku_map"],
        warehouse_aliases=ALIASES,
        uom_cache_path=dataset["uom"],
        decision_date="2026-02-03",
    )
    on_disk = json.loads((dataset["out"] / "rebuild_manifest.json").read_text(encoding="utf-8"))
    assert on_disk["forecast"]["run_id"] == "RUN-TEST"
    assert on_disk["counts"]["input_rows"] == 10
    assert on_disk["excluded"] == {"no_sku": 1, "no_date": 1, "fba": 1, "third_party": 1}
    assert len(on_disk["orders"]["sha256"]) == 64
    assert calls["decision_date"] == "2026-02-03"
    assert manifest["counts"]["output_rows"] == 6
