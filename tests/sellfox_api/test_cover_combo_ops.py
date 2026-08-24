# -*- coding: utf-8 -*-
"""Unit tests for cover combo planning (no network)."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

from cover_combo_plan import (  # noqa: E402
    BomCost,
    EnItemBrief,
    SellfoxSkuBrief,
    build_bom_cost,
    format_cost_remark,
    pk_sku_for_ks,
    plan_cover_combos,
    plan_one,
    summarize_plan,
)


def test_pk_sku_for_ks():
    assert pk_sku_for_ks("KS0001-HLR-153-TAN") == "PK#KS0001-HLR-153-TAN"
    assert pk_sku_for_ks("KS0248-DM-153-RED") == "PK#KS0248-DM-153-RED"
    assert pk_sku_for_ks("KS9999-X") is None


def test_build_bom_cost_ok():
    bom = build_bom_cost(cover_cost=41.632, usnj=7.872, ustx=8.16, pl=12.48)
    assert not bom.cost_missing
    assert bom.freight_avg == 9.504
    assert bom.purchase_cost == 51.136
    remark = format_cost_remark(bom)
    assert "绍兴皮壳成本41.632" in remark
    assert "USNJ{7.872}" in remark


def test_build_bom_cost_missing():
    bom = build_bom_cost(cover_cost=41.632, usnj=None, ustx=8.16, pl=12.48)
    assert bom.cost_missing
    assert bom.purchase_cost is None
    assert format_cost_remark(bom) == ""


def test_plan_create():
    row = plan_one(
        ks=SellfoxSkuBrief(sku="KS0001-HLR-153-TAN", name="三角靠枕-荷兰绒-153-驼色", is_group="0", full_cid="342807-", id="1"),
        en_product=EnItemBrief("KS0001-HLR-153-TAN", "三角靠枕-荷兰绒-153-驼色"),
        en_cover=EnItemBrief("PK#KS0001-HLR-153-TAN", "皮壳#三角靠枕-荷兰绒-153-驼色"),
        existing_pk=None,
        bom=build_bom_cost(cover_cost=41.632, usnj=7.872, ustx=8.16, pl=12.48),
    )
    assert row.action == "create"
    assert row.pk_sku == "PK#KS0001-HLR-153-TAN"
    assert row.purchase_cost == 51.136


def test_plan_ok_existing_combo():
    row = plan_one(
        ks=SellfoxSkuBrief(sku="KS0001-HLR-153-BLACK", name="x", is_group="0", id="2"),
        en_product=EnItemBrief("KS0001-HLR-153-BLACK", "成品黑"),
        en_cover=EnItemBrief("PK#KS0001-HLR-153-BLACK", "皮壳黑"),
        existing_pk=SellfoxSkuBrief(
            sku="PK#KS0001-HLR-153-BLACK",
            is_group="1",
            child_skus=(("KS0001-HLR-153-BLACK", 1),),
        ),
        bom=None,
    )
    assert row.action == "ok"
    assert row.cost_missing is True


def test_plan_mismatch_not_combo():
    row = plan_one(
        ks=SellfoxSkuBrief(sku="KS0001-A-1-B", name="x", is_group="0"),
        en_product=EnItemBrief("KS0001-A-1-B", "p"),
        en_cover=EnItemBrief("PK#KS0001-A-1-B", "c"),
        existing_pk=SellfoxSkuBrief(sku="PK#KS0001-A-1-B", is_group="0"),
        bom=None,
    )
    assert row.action == "mismatch"
    assert row.reason == "pk_exists_but_not_combo"


def test_plan_disabled_en_product_still_creates():
    row = plan_one(
        ks=SellfoxSkuBrief(sku="KS0001-QDKTR-100-RED", name="三角靠枕-全涤宽条绒-100-红色", is_group="0"),
        en_product=EnItemBrief("KS0001-QDKTR-100-RED", "三角靠枕-全涤宽条绒-100-红色", disabled=True),
        en_cover=EnItemBrief("PK#KS0001-QDKTR-100-RED", "皮壳#三角靠枕-全涤宽条绒-100-红色"),
        existing_pk=None,
        bom=None,
    )
    assert row.action == "create"
    assert row.en_pk_name.startswith("皮壳#")


def test_plan_missing_en_cover_uses_fallback_name():
    row = plan_one(
        ks=SellfoxSkuBrief(sku="KS0248-DM-153-RED", name="三角靠枕无扣-涤麻-153-红色", is_group="0"),
        en_product=EnItemBrief("KS0248-DM-153-RED", "p"),
        en_cover=None,
        existing_pk=None,
        bom=None,
    )
    assert row.action == "create"
    assert row.en_pk_name == "皮壳#三角靠枕无扣-涤麻-153-红色"


def test_plan_batch_counts():
    rows = plan_cover_combos(
        sellfox_ks_rows=[
            SellfoxSkuBrief(sku="KS0001-HLR-153-TAN", is_group="0", id="1"),
            SellfoxSkuBrief(sku="KS0001-HLR-153-BLACK", is_group="0", id="2"),
        ],
        en_products={
            "KS0001-HLR-153-TAN": EnItemBrief("KS0001-HLR-153-TAN", "t"),
            "KS0001-HLR-153-BLACK": EnItemBrief("KS0001-HLR-153-BLACK", "b"),
        },
        en_covers={
            "PK#KS0001-HLR-153-TAN": EnItemBrief("PK#KS0001-HLR-153-TAN", "pt"),
            "PK#KS0001-HLR-153-BLACK": EnItemBrief("PK#KS0001-HLR-153-BLACK", "pb"),
        },
        sellfox_pk_rows={
            "PK#KS0001-HLR-153-TAN": SellfoxSkuBrief(
                sku="PK#KS0001-HLR-153-TAN",
                is_group="1",
                child_skus=(("KS0001-HLR-153-TAN", 1),),
            ),
        },
        bom_by_ks={},
    )
    summary = summarize_plan(rows)
    assert summary["input_ks"] == 2
    assert summary["output_rows"] == 2
    assert summary["counts"]["ok"] == 1
    assert summary["counts"]["create"] == 1


def test_classify_plan_against_live():
    from cover_combo_ops import classify_plan_against_live

    plan = [
        {
            "pk_sku": "PK#KS0001-A-1-B",
            "ks_sku": "KS0001-A-1-B",
            "en_pk_name": "皮壳#x",
        },
        {
            "pk_sku": "PK#KS0001-A-1-C",
            "ks_sku": "KS0001-A-1-C",
            "en_pk_name": "皮壳#y",
        },
    ]
    live = {
        "PK#KS0001-A-1-B": {
            "sku": "PK#KS0001-A-1-B",
            "isGroup": "1",
            "name": "皮壳#x",
            "childSkus": [{"sku": "KS0001-A-1-B", "num": 1}],
        }
    }
    out = classify_plan_against_live(plan, live)
    assert [r["pk_sku"] for r in out["already_ok"]] == ["PK#KS0001-A-1-B"]
    assert [r["pk_sku"] for r in out["need_create"]] == ["PK#KS0001-A-1-C"]
