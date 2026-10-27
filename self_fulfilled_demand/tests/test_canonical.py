# -*- coding: utf-8 -*-
"""规范需求适配层离线测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from self_fulfilled_demand import config
from self_fulfilled_demand.canonical import (
    _coverage,
    build_canonical,
    build_netting_views,
    canonicalize,
    en_kind_lookup,
    ensure_uom_cache,
    load_sku_map,
    load_uom_cache,
    load_warehouse_config,
    resolve_warehouse,
    resolve_warehouse_role,
    snapshot_identity,
    supply_targets,
)
from self_fulfilled_demand.normalize import normalize_order
from self_fulfilled_demand.store import ParquetStore


def demand_df(rows: list[dict]) -> pd.DataFrame:
    base = pd.DataFrame(
        {
            "order_key": ["O1"],
            "tongtool_sku": ["TT-1"],
            "platform_sku": ["P1"],
            "quantity": [1],
            "sale_date": ["2026-10-05"],
            "warehouse_name": ["美中-FZH-DANEEY"],
            "fulfillment_scope": [config.SCOPE_SELF],
            "source": ["en_incremental"],
            "coverage_status": ["complete"],
            "demand_kind": [config.DSHIP_COVER],
            "demand_kind_basis": ["shipping_method=皮壳"],
        }
    )
    out = pd.concat([base, pd.DataFrame(rows)], ignore_index=True) if rows else base
    return out


def sku_map(rows: list[tuple[str, tuple[str, ...]]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["tongtool_sku", "item_codes"])
    df["n_items"] = df["item_codes"].map(len)
    df["mapping_status"] = df["n_items"].map(lambda n: "mapped" if n == 1 else "ambiguous")
    df["mapping_evidence"] = "fixture"
    return df


def uom_cache(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["item_code", "stock_uom"])


@pytest.fixture()
def wh_cfg() -> dict:
    return load_warehouse_config()


def test_one_to_many_is_blocked_not_picked(wh_cfg):
    demand = demand_df([])
    sm = sku_map([("TT-1", ("KS-A", "KS-B"))])
    out = canonicalize(demand, sm, uom_cache([("KS-A", "个"), ("KS-B", "个")]), wh_cfg)
    row = out.iloc[0]
    assert row["mapping_status"] == "ambiguous"
    assert row["canonical_sku"] == "ambiguous:TT-1"
    assert bool(row["netting_allowed"]) is False
    assert row["netting_block_primary"] == "sku_mapping_ambiguous"
    assert "sku_mapping_ambiguous" in row["netting_block_reason"]
    assert "uom_missing" in row["netting_block_reason"]


def test_cover_and_finished_are_not_merged(wh_cfg):
    demand = demand_df(
        [
            {
                "order_key": "O2", "tongtool_sku": "TT-2", "platform_sku": "P2",
                "quantity": 1, "sale_date": "2026-10-05",
                "warehouse_name": "美东-CENTRADE", "fulfillment_scope": config.SCOPE_SELF,
                "source": "en_incremental", "coverage_status": "complete",
                "demand_kind": config.DSHIP_FINISHED, "demand_kind_basis": "shipping_method=成品",
            }
        ]
    )
    # 第一行复用 TT-1；再加两行 fixture 默认行会重复，这里只保留 O1/O2
    demand = demand.iloc[:2]
    demand.loc[demand.index[0], "tongtool_sku"] = "TT-COVER"
    sm = sku_map([("TT-COVER", ("PK#KS0001-A",)), ("TT-2", ("KS0001-A",))])
    out = canonicalize(
        demand,
        sm,
        uom_cache([("PK#KS0001-A", "个"), ("KS0001-A", "个")]),
        wh_cfg,
    )
    assert set(out["canonical_sku"]) == {"PK#KS0001-A", "KS0001-A"}
    assert out["canonical_sku"].nunique() == 2


def test_warehouse_alias_merges_and_subwarehouse_maps_to_parent_role(wh_cfg):
    assert resolve_warehouse("CENTRADE", wh_cfg)["canonical_warehouse"] == "美东-CENTRADE"
    sub = resolve_warehouse_role("FZH-DANEEY-皮壳仓库", wh_cfg)
    # 2026-10-27 口径：子仓是同一分公司的不同角色/成本来源，归到主仓并带角色，不再阻断
    assert sub["canonical_warehouse"] == "美中-FZH-DANEEY"
    assert sub["warehouse_role"] == "cover"
    assert sub["conversion_assumed"] is True
    assert sub["warehouse_merge_status"] == "role_mapped"
    assert resolve_warehouse("星链海外仓", wh_cfg)["warehouse_status"] == "unknown"

    demand = demand_df([])
    demand.loc[demand.index[0], "warehouse_name"] = "FZH-DANEEY-皮壳仓库"
    out = canonicalize(demand, sku_map([("TT-1", ("KS-OK",))]), uom_cache([("KS-OK", "个")]), wh_cfg)
    row = out.iloc[0]
    assert row["canonical_warehouse"] == "美中-FZH-DANEEY"
    assert row["warehouse_role"] == "cover"
    assert bool(row["netting_allowed"]) is True
    assert "subwarehouse_identity_unproven" not in row["netting_block_reason"]


def test_return_subwarehouse_keeps_demand_but_is_not_available_supply(wh_cfg):
    demand = demand_df([])
    demand.loc[demand.index[0], "warehouse_name"] = "FZH-DANEEY-退货产品仓"
    out = canonicalize(demand, sku_map([("TT-1", ("KS-OK",))]), uom_cache([("KS-OK", "个")]), wh_cfg)
    row = out.iloc[0]
    assert row["canonical_warehouse"] == "美中-FZH-DANEEY"
    assert row["warehouse_role"] == "return"
    assert row["counts_as_available"] is False or row["counts_as_available"] == 0
    assert bool(row["netting_allowed"]) is True


def test_uom_unknown_and_not_piece_block(wh_cfg):
    demand = demand_df(
        [
            {
                "order_key": "O3", "tongtool_sku": "TT-M", "platform_sku": "P3",
                "quantity": 2, "sale_date": "2026-10-05",
                "warehouse_name": "美中-FZH-DANEEY", "fulfillment_scope": config.SCOPE_SELF,
                "source": "en_incremental", "coverage_status": "complete",
                "demand_kind": config.DSHIP_COVER, "demand_kind_basis": "fixture",
            }
        ]
    )
    sm = sku_map([("TT-1", ("KS-OK",)), ("TT-M", ("KS-METER",))])
    out = canonicalize(demand, sm, uom_cache([("KS-OK", "个"), ("KS-METER", "米")]), wh_cfg)
    by_sku = out.set_index("tongtool_sku")
    assert bool(by_sku.loc["TT-1", "netting_allowed"]) is True
    assert by_sku.loc["TT-M", "uom_status"] == "not_piece"
    assert bool(by_sku.loc["TT-M", "netting_allowed"]) is False
    assert by_sku.loc["TT-M", "netting_block_reason"] == "uom_not_piece"


def test_gs_kind_inferred_only_when_unique(wh_cfg):
    demand = pd.DataFrame(
        [
            {
                "order_key": "G1", "tongtool_sku": "TT-1", "platform_sku": "P1",
                "quantity": 1, "sale_date": "2026-09-29",
                "warehouse_name": "美中-FZH-DANEEY", "fulfillment_scope": config.SCOPE_SELF,
                "source": "gs_legacy", "coverage_status": "complete",
                "demand_kind": config.DSHIP_UNKNOWN,
                "demand_kind_basis": "gs_monthly_sheet_has_no_shipping_method",
            },
            {
                "order_key": "G2", "tongtool_sku": "TT-1", "platform_sku": "P1",
                "quantity": 1, "sale_date": "2026-09-29",
                "warehouse_name": "美中-FZH-DANEEY", "fulfillment_scope": config.SCOPE_SELF,
                "source": "gs_legacy", "coverage_status": "complete",
                "demand_kind": config.DSHIP_UNKNOWN,
                "demand_kind_basis": "gs_monthly_sheet_has_no_shipping_method",
            },
        ]
    )
    kind = pd.Series(
        [frozenset({config.DSHIP_COVER}), frozenset({config.DSHIP_COVER, config.DSHIP_FINISHED})],
        index=pd.MultiIndex.from_tuples([("G1", "TT-1"), ("G2", "TT-1")]),
    )
    out = canonicalize(demand, sku_map([("TT-1", ("KS-OK",))]), uom_cache([("KS-OK", "个")]), wh_cfg, kind)
    by_order = out.set_index("order_key")
    assert by_order.loc["G1", "demand_kind"] == config.DSHIP_COVER
    assert by_order.loc["G1", "demand_kind_basis"] == "en_line_match"
    assert by_order.loc["G2", "demand_kind"] == config.DSHIP_UNKNOWN
    assert by_order.loc["G2", "demand_kind_basis"] == "en_line_conflict"


def test_third_party_retained_unknown_scope_blocked(wh_cfg):
    demand = pd.DataFrame(
        [
            {
                "order_key": "T1", "tongtool_sku": "TT-1", "platform_sku": "P1",
                "quantity": 1, "sale_date": "2026-10-05",
                "warehouse_name": "枫筝海外仓-多伦多-代发仓",
                "fulfillment_scope": config.SCOPE_THIRD_PARTY,
                "source": "en_incremental", "coverage_status": "complete",
                "demand_kind": config.DSHIP_COVER, "demand_kind_basis": "fixture",
            },
            {
                "order_key": "U1", "tongtool_sku": "TT-1", "platform_sku": "P1",
                "quantity": 1, "sale_date": "2026-10-05",
                "warehouse_name": "星链海外仓",
                "fulfillment_scope": config.SCOPE_UNKNOWN,
                "source": "en_incremental", "coverage_status": "complete",
                "demand_kind": config.DSHIP_COVER, "demand_kind_basis": "fixture",
            },
        ]
    )
    out = canonicalize(demand, sku_map([("TT-1", ("KS-OK",))]), uom_cache([("KS-OK", "个")]), wh_cfg)
    t = out[out.order_key == "T1"].iloc[0]
    u = out[out.order_key == "U1"].iloc[0]
    assert bool(t["netting_allowed"]) is True
    assert bool(t["in_default_series"]) is False
    assert bool(u["netting_allowed"]) is False
    assert "warehouse_identity_unknown" in u["netting_block_reason"]
    assert "scope_unknown" in u["netting_block_reason"]


def test_coverage_reconciles_rows_and_qty(wh_cfg):
    demand = demand_df(
        [
            {
                "order_key": "O9", "tongtool_sku": "TT-X", "platform_sku": "P9",
                "quantity": 3, "sale_date": "2026-10-05",
                "warehouse_name": "美中-FZH-DANEEY", "fulfillment_scope": config.SCOPE_SELF,
                "source": "en_incremental", "coverage_status": "complete",
                "demand_kind": config.DSHIP_COVER, "demand_kind_basis": "fixture",
            }
        ]
    )
    sm = sku_map([("TT-1", ("KS-OK",)), ("TT-X", ("KS-X",))])
    out = canonicalize(demand, sm, uom_cache([("KS-OK", "个")]), wh_cfg)  # TT-X 无 UOM
    cov = _coverage(out, len(out), float(out["quantity"].sum()))
    total = cov[cov["tongtool_sku"] == "__TOTAL__"].iloc[0]
    assert total["demand_rows"] == len(out)
    assert total["ready_rows"] + total["blocked_rows"] == len(out)
    assert total["ready_qty"] + total["blocked_qty"] == out["quantity"].sum()
    assert total["blocked_qty"] == 3


def test_load_sku_map_marks_ambiguity(tmp_path: Path):
    p = tmp_path / "sku.tsv"
    p.write_text("KS-A\tTT-1\t\nKS-B\tTT-1\t\nKS-C\tTT-2\t\n", encoding="utf-8")
    m = load_sku_map(p).set_index("tongtool_sku")
    assert m.loc["TT-1", "mapping_status"] == "ambiguous"
    assert m.loc["TT-2", "mapping_status"] == "mapped"


class FakeItemClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def get_list(self, doctype, fields, filters=None, limit_page_length=0):
        self.calls += 1
        wanted = set(filters[0][3])
        return [r for r in self.rows if r["name"] in wanted]


def test_uom_cache_bounded_and_cached(tmp_path: Path):
    cache = tmp_path / "uom.parquet"
    client = FakeItemClient([{"name": "KS-A", "stock_uom": "个", "item_name": "A", "is_stock_item": 1}])
    df = ensure_uom_cache(client, ["KS-A", "KS-B"], cache, max_items=10)
    assert set(df["item_code"]) == {"KS-A", "KS-B"}
    assert pd.isna(df.set_index("item_code").loc["KS-B", "stock_uom"])
    calls = client.calls
    ensure_uom_cache(client, ["KS-A", "KS-B"], cache, max_items=10)
    assert client.calls == calls  # 已有缓存不再查
    with pytest.raises(ValueError, match="超过上限"):
        ensure_uom_cache(client, [f"KS-{i}" for i in range(20)], cache, max_items=10)
