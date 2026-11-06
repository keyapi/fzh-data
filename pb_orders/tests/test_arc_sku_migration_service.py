#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务层：旧通途 SKU 自动转换、PB 料号校验与断货别名匹配。"""

from __future__ import annotations

import pandas as pd
import pytest

import service
import stock_precheck

from conftest import write_packslip_pdf

COLUMNS = [
    "PO Number",
    "PO Line #",
    "Record Type",
    "Qty Ordered",
    "Vendor Style",
    "Buyers Catalog or Stock Keeping #",
    "Ship To Country",
    "Unit Price",
]


def write_arc_csv(path, rows):
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_csv(path, index=False)
    return path


def arc_cache(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"通途SKU": "TT0312672K0064328", "中文名称": "弧形颈枕灰", "西班牙语名称": "Gris"},
        {"通途SKU": "TT0312673K0064329", "中文名称": "弧形颈枕象牙白", "西班牙语名称": "Marfil"},
    ]).to_csv(path, index=False)
    return path


def test_run_job_converts_old_skus_and_emits_converted_csv(pb_env):
    pdf = write_packslip_pdf(
        pb_env.tmp / "Packslip 美中 x2 arc.pdf",
        pages=[("137943090", "5938375"), ("137943090", "4020032")],
    )
    csv_path = write_arc_csv(
        pb_env.tmp / "checked0stock arc.csv",
        [
            ["137943090", "", "H", "", "", "", "USA", ""],
            ["137943090", "1", "D", 1, "TT0031058K0062965", "5938375", "USA", "10"],
            ["137943090", "2", "D", 1, "TT0031059K0062966", "4020032", "USA", "10"],
        ],
    )
    cache = arc_cache(pb_env.data / "us_sku_name_cache.csv")
    out = pb_env.tmp / "out_arc"

    result = service.run_job(
        pdf, csv_path, service.JobOptions(cache_only=True, sku_cache_path=cache), out
    )

    migration = result.report["sku_migration"]
    assert migration["enabled"] is True
    assert migration["applied"] is True
    pairs = {(row["old"], row["new"]) for row in migration["replacements"]}
    assert pairs == {
        ("TT0031058K0062965", "TT0312672K0064328"),
        ("TT0031059K0062966", "TT0312673K0064329"),
    }
    kinds = {a.kind for a in result.artifacts}
    assert "converted_order" in kinds
    converted = next(a for a in result.artifacts if a.kind == "converted_order")
    text = converted.path.read_text(encoding="utf-8-sig")
    assert "TT0312672K0064328" in text and "TT0312673K0064329" in text
    assert "TT0031058K0062965" not in text and "TT0031059K0062966" not in text


def test_run_job_blocks_when_pb_sku_pairs_wrong_old_sku(pb_env):
    pdf = write_packslip_pdf(
        pb_env.tmp / "Packslip 美中 x1 arc.pdf",
        pages=[("137943090", "5938375")],
    )
    csv_path = write_arc_csv(
        pb_env.tmp / "checked0stock arc conflict.csv",
        [
            ["137943090", "", "H", "", "", "", "USA", ""],
            ["137943090", "1", "D", 1, "TT0031059K0062966", "5938375", "USA", "10"],
        ],
    )

    with pytest.raises(service.PBJobError) as excinfo:
        service.run_job(
            pdf, csv_path,
            service.JobOptions(cache_only=True, sku_cache_path=pb_env.cache),
            pb_env.tmp / "out_conflict",
        )

    assert excinfo.value.code == "sku_migration_blocked"
    assert "5938375" in excinfo.value.hint
    assert not (pb_env.tmp / "out_conflict").exists()


def test_run_job_blocks_deep_blue_without_mapping(pb_env):
    pdf = write_packslip_pdf(
        pb_env.tmp / "Packslip 美中 x1 blue.pdf",
        pages=[("137943090", "9999999")],
    )
    csv_path = write_arc_csv(
        pb_env.tmp / "checked0stock blue.csv",
        [
            ["137943090", "", "H", "", "", "", "USA", ""],
            ["137943090", "1", "D", 1, "TT0312674K0064330", "9999999", "USA", "10"],
        ],
    )

    with pytest.raises(service.PBJobError) as excinfo:
        service.run_job(
            pdf, csv_path,
            service.JobOptions(cache_only=True, sku_cache_path=pb_env.cache),
            pb_env.tmp / "out_blue",
        )

    assert excinfo.value.code == "sku_migration_blocked"
    assert "TT0312674K0064330" in excinfo.value.hint


def test_stock_precheck_treats_old_and_new_sku_as_same():
    _snapshot, wanted = stock_precheck._normalized_skus(["TT0312672K0064328"])

    assert "tt0312672k0064328" in wanted
    assert "tt0031058k0062965" in wanted
