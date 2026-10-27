# -*- coding: utf-8 -*-
"""审核返修回归：子仓资格、四列键、快照一致性、完整构建守恒。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from self_fulfilled_demand import config
from self_fulfilled_demand.canonical import (
    build_canonical,
    build_netting_views,
    canonicalize,
    en_kind_lookup,
    load_sku_map,
    load_warehouse_config,
    snapshot_identity,
    supply_targets,
)
from self_fulfilled_demand.normalize import normalize_order
from self_fulfilled_demand.store import ParquetStore

FIXTURES = Path(__file__).parent / "fixtures"


def demand_row(**over) -> dict:
    row = {
        "order_key": "O1",
        "tongtool_sku": "TT-1",
        "platform_sku": "P1",
        "quantity": 1,
        "sale_date": "2026-10-05",
        "warehouse_name": "美中-FZH-DANEEY",
        "fulfillment_scope": config.SCOPE_SELF,
        "source": "en_incremental",
        "coverage_status": "complete",
        "demand_kind": config.DSHIP_COVER,
        "demand_kind_basis": "shipping_method=皮壳",
    }
    row.update(over)
    return row


def demand_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([demand_row(**r) for r in rows] or [demand_row()])


def sku_map(rows: list[tuple[str, tuple[str, ...]]]) -> pd.DataFrame:
    df = pd.DataFrame(rows or [("TT-1", ("KS-OK",))], columns=["tongtool_sku", "item_codes"])
    df["n_items"] = df["item_codes"].map(len)
    df["mapping_status"] = df["n_items"].map(lambda n: "mapped" if n == 1 else "ambiguous")
    df["mapping_evidence"] = "fixture"
    return df


def uom_cache(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows or [("KS-OK", "个")], columns=["item_code", "stock_uom"])


SUBWAREHOUSES = [
    "FZH-DANEEY-半成品仓",
    "FZH-DANEEY-成品仓",
    "FZH-DANEEY-皮壳仓库",
    "FZH-DANEEY-退货产品仓",
    "FZHPoland-finished",
]


@pytest.fixture()
def wh_cfg() -> dict:
    return load_warehouse_config()


@pytest.mark.parametrize("warehouse", SUBWAREHOUSES)
def test_subwarehouses_map_to_parent_with_role_not_blocked(wh_cfg, warehouse):
    demand = demand_df([{"warehouse_name": warehouse}])
    out = canonicalize(demand, sku_map([]), uom_cache([]), wh_cfg)
    row = out.iloc[0]
    # 2026-10-27 口径：子仓归主仓 + 角色，不再按 subwarehouse_identity_unproven 阻断
    assert row["warehouse_merge_status"] == "role_mapped"
    assert row["canonical_warehouse"] in {"美中-FZH-DANEEY", "波兰-FZHPoland-covers"}
    assert row["warehouse_role"] in {"cover", "semi", "finished", "return"}
    assert "subwarehouse_identity_unproven" not in row["netting_block_reason"]
    assert row["netting_block_primary"] != "subwarehouse_identity_unproven"


@pytest.mark.parametrize("warehouse", [None, "", "   ", "星链海外仓", "休斯顿1号仓", "北美之路-LA01"])
def test_unknown_warehouses_including_empty_are_blocked(wh_cfg, warehouse):
    demand = demand_df([{"warehouse_name": warehouse}])
    out = canonicalize(demand, sku_map([]), uom_cache([]), wh_cfg)
    row = out.iloc[0]
    assert row["warehouse_status"] == "unknown"
    assert bool(row["netting_allowed"]) is False
    assert "warehouse_identity_unknown" in row["netting_block_reason"]


def test_composite_block_reasons_and_primary_order(wh_cfg):
    demand = demand_df(
        [
            {
                "tongtool_sku": "TT-MISSING",
                "warehouse_name": "星链海外仓",
                "fulfillment_scope": config.SCOPE_UNKNOWN,
            }
        ]
    )
    out = canonicalize(demand, sku_map([("TT-OTHER", ("KS-X",))]), uom_cache([("KS-X", "个")]), wh_cfg)
    row = out.iloc[0]
    assert row["netting_block_reason"].split(";") == [
        "sku_mapping_missing",
        "uom_missing",
        "warehouse_identity_unknown",
        "scope_unknown",
    ]
    assert row["netting_block_primary"] == "sku_mapping_missing"


def test_quantity_invalid_is_blocked_and_preserved(wh_cfg):
    demand = demand_df([{"quantity": None}])
    out = canonicalize(demand, sku_map([]), uom_cache([]), wh_cfg)
    row = out.iloc[0]
    assert pd.isna(row["quantity"])
    assert bool(row["netting_allowed"]) is False
    assert "quantity_invalid" in row["netting_block_reason"]


def test_empty_input_and_missing_date_do_not_crash(wh_cfg):
    empty = pd.DataFrame(columns=demand_df([]).columns)
    out = canonicalize(empty, sku_map([]), uom_cache([]), wh_cfg)
    assert len(out) == 0
    assert "netting_allowed" in out.columns

    demand = demand_df([{"sale_date": None}])
    out = canonicalize(demand, sku_map([]), uom_cache([]), wh_cfg)
    assert len(out) == 1
    assert pd.isna(out.iloc[0]["sale_date"])


def test_uom_missing_empty_and_whitespace(wh_cfg):
    demand = demand_df(
        [
            {"order_key": f"U{i}", "tongtool_sku": f"TT-U{i}"}
            for i in range(3)
        ]
    )
    sm = sku_map([(f"TT-U{i}", (f"KS-U{i}",)) for i in range(3)])
    cache = pd.DataFrame(
        [("KS-U0", None), ("KS-U1", ""), ("KS-U2", "   ")], columns=["item_code", "stock_uom"]
    )
    out = canonicalize(demand, sm, cache, wh_cfg)
    assert set(out["uom_status"]) == {"missing"}
    assert out["uom"].isna().all()
    assert not out["netting_allowed"].any()
    assert set(out["netting_block_primary"]) == {"uom_missing"}


def test_netting_key_is_unique_and_sums_duplicate_slices():
    # 审核点名的真实键：同一四列键下 known semi_finished 1 件 + unknown 1 件
    base = {
        "demand_date": "2025-07-01",
        "canonical_sku": "KS0390-CTTM-120x120x70-CREAMYBEIGE",
        "canonical_warehouse": "FZH-DANEEY-半成品仓",
        "canonical_uom": "个",
        "quantity": 1,
        "order_key": "O1",
        "fulfillment_scope": config.SCOPE_SELF,
        "source": "gs_legacy",
        "coverage_status": "complete",
        "netting_allowed": True,
        "in_default_series": True,
        "netting_block_primary": "",
        "netting_block_reason": "",
    }
    disp = pd.DataFrame(
        [
            {**base, "demand_kind": config.DSHIP_SEMI},
            {**base, "demand_kind": config.DSHIP_UNKNOWN, "order_key": "O2"},
        ]
    )
    netting, blocked = build_netting_views(disp)
    assert len(netting) == 1
    assert netting.iloc[0]["quantity"] == 2  # 不是 1，也没有任取一行
    assert (
        netting.duplicated(
            ["demand_date", "canonical_sku", "canonical_warehouse", "canonical_uom"]
        ).sum()
        == 0
    )
    targets = supply_targets(netting)
    assert len(targets) == 1 and targets.iloc[0]["quantity"] == 2
    assert len(blocked) == 0


def test_supply_targets_reject_unknown_uom_and_warehouse():
    base = {
        "demand_date": "2026-10-01",
        "quantity": 2,
        "quantity_default": 2,
        "quantity_third_party": 0,
        "order_count": 1,
        "demand_kind_mix": "cover",
        "scope_mix": "self_fulfilled_candidate",
    }
    netting = pd.DataFrame(
        [
            {**base, "canonical_sku": "KS-A", "canonical_warehouse": "美中-FZH-DANEEY", "canonical_uom": "个"},
            {**base, "canonical_sku": "KS-B", "canonical_warehouse": "美中-FZH-DANEEY", "canonical_uom": "<unknown>"},
            {**base, "canonical_sku": "KS-C", "canonical_warehouse": "<unknown>", "canonical_uom": "个"},
        ]
    )
    targets = supply_targets(netting)
    assert list(targets["canonical_sku"]) == ["KS-A"]


def test_load_sku_map_drops_empty_fields(tmp_path: Path):
    p = tmp_path / "sku.tsv"
    p.write_text("\tTT-EMPTY\t\nKS-A\t\t\nKS-B\tTT-2\t\n", encoding="utf-8")
    m = load_sku_map(p)
    assert list(m["tongtool_sku"]) == ["TT-2"]


def _ingest_batch1(store: ParquetStore) -> None:
    data = json.loads((FIXTURES / "orders_batch1.json").read_text(encoding="utf-8"))
    run = {
        "run_id": "run-canon",
        "started_at": "2026-10-27T10:00:00+08:00",
        "ingest_scope": "sale_window",
        "coverage_status": "complete",
    }
    records = [normalize_order(o["head"], o["items"], o["packages"], run) for o in data["orders"]]
    store.ingest(records, run)


def test_full_build_conservation_and_manifest(tmp_path: Path):
    store = ParquetStore(tmp_path / "en-demand-v1")
    _ingest_batch1(store)

    skus = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "FOAM-1"]
    sku_path = tmp_path / "sku.tsv"
    sku_path.write_text("".join(f"KS-{s}\tTT-SKU-{s}\t\n" for s in skus), encoding="utf-8")
    cache_path = tmp_path / "uom.parquet"
    pd.DataFrame([(f"KS-{s}", "个") for s in skus], columns=["item_code", "stock_uom"]).to_parquet(
        cache_path, index=False
    )

    out = tmp_path / "canonical"
    manifest = build_canonical(
        store.root,
        FIXTURES / "gs_orders_small.csv",
        "2026-09-01",
        "2026-10-31",
        out,
        sku_map_path=sku_path,
        uom_cache_path=cache_path,
        fetch_uom=False,
        client=None,
    )
    disp = pd.read_parquet(out / "demand_line_disposition.parquet")
    netting = pd.read_parquet(out / "demand_netting.parquet")
    blocked = pd.read_parquet(out / "demand_blocked.parquet")
    detailed = pd.read_parquet(out / "demand_canonical.parquet")

    input_qty = float(pd.to_numeric(disp["quantity"], errors="coerce").sum())
    assert abs(netting["quantity"].sum() + blocked["quantity"].sum() - input_qty) < 1e-6
    assert abs(detailed["quantity"].sum() - input_qty) < 1e-6
    assert (
        netting.duplicated(
            ["demand_date", "canonical_sku", "canonical_warehouse", "canonical_uom"]
        ).sum()
        == 0
    )
    assert manifest["counts"]["four_key_duplicates_in_netting"] == 0
    assert manifest["counts"]["fba_rows_excluded"] >= 1
    assert "EN-004" not in set(disp["order_key"])  # FBA 端到端排除

    current = store.read_current()
    snap = manifest["sources"]["en_snapshot"]
    assert snap["commit_id"] == current["commit_id"]
    assert len(snap["orders_sha256"]) == 64 and len(snap["lines_sha256"]) == 64
    assert snap["orders_rows"] == len(store.load_orders())


def test_snapshot_switch_does_not_mix_reads(tmp_path: Path):
    root = tmp_path / "en-demand-v1"
    store_a = ParquetStore(root)
    _ingest_batch1(store_a)
    commit_a = store_a.read_current()["commit_id"]

    with store_a.pinned():
        orders_a = store_a.load_orders()
        kind_a = en_kind_lookup(store_a)

        store_b = ParquetStore(root)
        data = json.loads((FIXTURES / "orders_batch2.json").read_text(encoding="utf-8"))
        run = {
            "run_id": "run-b",
            "started_at": "2026-10-28T10:00:00+08:00",
            "ingest_scope": "sale_window",
            "coverage_status": "complete",
        }
        records = [normalize_order(o["head"], o["items"], o["packages"], run) for o in data["orders"]]
        store_b.ingest(records, run)

        assert store_b.read_current()["commit_id"] != commit_a
        orders_again = store_a.load_orders()
        kind_again = en_kind_lookup(store_a)
        identity = snapshot_identity(store_a)

    assert orders_again.equals(orders_a)
    assert kind_again.equals(kind_a)
    assert identity["commit_id"] == commit_a


def test_en_kind_lookup_accepts_multiple_lines_same_kind(tmp_path: Path):
    store = ParquetStore(tmp_path / "en-demand-v1")
    _ingest_batch1(store)
    lookup = en_kind_lookup(store)
    # EN-002 两条同 SKU、同形态（成品）行 → 集合只有一个形态，可沿用
    assert lookup.loc[("EN-002", "TT-SKU-B")] == frozenset({config.DSHIP_FINISHED})
    # 没有 EN 行的 GS 订单 → 查不到，保持 unknown
    assert ("NO-SUCH-ORDER", "TT-X") not in lookup.index
