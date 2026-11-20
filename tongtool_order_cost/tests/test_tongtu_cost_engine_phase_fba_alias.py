# -*- coding: utf-8 -*-
"""Phase 4.FBA alias：归一化匹配 + 登记 dry-run 测试（不写 EN/GS）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.alias_dryrun import (  # noqa: E402
    build_alias_dryrun,
)
from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import (  # noqa: E402
    EnResolver,
    normalize_alias,
)


def _ref(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    ref = out / "item_refcode.csv"
    pd.DataFrame([
        {"name": "KS0001-DM-45-GREY", "customer_code": "SUK-SJWKDM-grey 45cm",
         "item_group": "三角靠枕", "variant_of": "KS0001"},
        {"name": "KS-B", "customer_code": "", "item_group": "三角靠枕", "variant_of": "KS-B"},
        {"name": "KS-C", "customer_code": "", "item_group": "三角靠枕", "variant_of": "KS-C"},
        {"name": "KS-AMB1", "customer_code": "LOOSE-KEY", "item_group": "三角靠枕", "variant_of": "P1"},
        {"name": "KS-AMB2", "customer_code": "LOOSEKEY", "item_group": "三角靠枕", "variant_of": "P2"},
    ]).to_csv(ref, index=False, encoding="utf-8")
    return ref


def test_normalize_alias_matches_space_hyphen_underscore(tmp_path):
    _ref(tmp_path)
    resolver = EnResolver.from_items_csv(tmp_path / "out" / "item_refcode.csv")
    expected = ("KS0001-DM-45-GREY",)
    for sku in ("SUK-SJWKDM-grey 45cm", "SUK-SJWKDM-GREY45CM",
                "SUK-SJWKDM-GREY-45CM", "SUK_SJWKDM_GREY45CM"):
        assert resolver.items_for_sku(sku) == expected, sku
    assert normalize_alias("SUK-SJWKDM-grey 45cm") == normalize_alias("SUK_SJWKDM_GREY-45CM")
    # 宽松归一化引入的歧义不猜：两个产品命中 → 返回两个 item
    assert set(resolver.items_for_sku("LOOSE-KEY")) == {"KS-AMB1", "KS-AMB2"}
    assert resolver.resolve("LOOSEKEY").status == "ambiguous"


def _whitelist(path: Path, rows: list[dict], month: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")


def test_alias_dryrun_proposals_hashes_and_classification(tmp_path):
    _ref(tmp_path)
    out = tmp_path / "out" / "fba_shadow"
    _whitelist(out / "202608" / "fba_whitelist_202608.csv", [
        {"month": "202608", "sku": "SUK_SJWKDM_GREY45CM", "qty": "2", "status": "auto_mapped",
         "auto_pref": "single_candidate", "approved_item_code": "KS0001-DM-45-GREY"},
        {"month": "202608", "sku": "UNREG-1", "qty": "3", "status": "auto_mapped",
         "auto_pref": "superset", "approved_item_code": "KS-B"},
    ], "202608")
    _whitelist(out / "202609" / "fba_whitelist_202609.csv", [
        {"month": "202609", "sku": "UNREG-1", "qty": "1", "status": "auto_mapped",
         "auto_pref": "superset", "approved_item_code": "KS-B"},
        {"month": "202609", "sku": "NEED-CONFIRM", "qty": "5",
         "status": "needs_business_confirmation", "auto_pref": "", "approved_item_code": ""},
    ], "202609")

    res = build_alias_dryrun(
        root=tmp_path,
        months=("202608", "202609"),
        proposals=(
            {"sku": "UNREG-1", "action": "add_alias", "target_item": "KS-B", "note": "n"},
            {"sku": "LOOSE-KEY-VARIANT", "action": "add_alias", "target_item": "KS-C", "note": "n"},
            {"sku": "BORROW-1", "action": "cost_borrow", "target_item": "KS-C", "note": "借成本"},
        ),
    )
    props = {p["sku"]: p for p in res["proposals"]}
    unreg = props["UNREG-1"]
    assert unreg["old_customer_code"] == ""
    assert unreg["new_customer_code"] == "UNREG-1"
    assert unreg["old_hash"] != unreg["new_hash"]
    assert unreg["affected_rows"] == 2 and unreg["affected_qty"] == 4.0
    assert unreg["months"] == "202608,202609"
    assert unreg["write"] is False
    borrow = props["BORROW-1"]
    assert borrow["action"] == "cost_borrow"
    assert borrow["old_customer_code"] == borrow["new_customer_code"]
    assert borrow["old_hash"] == borrow["new_hash"]

    cls = {c["sku"]: c for c in res["classification"]}
    assert cls["SUK_SJWKDM_GREY45CM"]["class"] == "normalization_only"  # 宽松归一化命中已登记别名
    assert cls["UNREG-1"]["class"] == "needs_registration"
    assert "NEED-CONFIRM" not in cls                           # 非 auto 不进分类
    assert res["summary"]["auto_total"] == 2
    assert res["summary"]["needs_registration"] == 1
    assert res["summary"]["normalization_only"] == 1
    # 30 个 auto SKU 也生成 add_alias 提案：已登记 → noop；未登记 → needs_review
    all_props = {p["sku"]: p for p in res["proposals"]}
    assert all_props["SUK_SJWKDM_GREY45CM"]["status"] == "noop"
    assert all_props["SUK_SJWKDM_GREY45CM"]["target_item"] == "KS0001-DM-45-GREY"
    assert all_props["UNREG-1"]["status"] == "needs_review"
    assert all_props["UNREG-1"]["old_hash"] != all_props["UNREG-1"]["new_hash"]
    assert res["summary"]["noop"] == 1
    assert res["summary"]["needs_review"] == 2
    assert res["summary"]["cost_borrow"] == 1
    run = Path(res["run_dir"])
    for name in ("proposals_all.csv", "proposals.csv", "classification.csv",
                 "summary.md", "manifest.json"):
        assert (run / name).exists()
    all_df = pd.read_csv(run / "proposals_all.csv", dtype=str, keep_default_na=False)
    for col in ("action", "sku", "target_item", "item_group", "old_customer_code",
                "new_customer_code", "old_hash", "new_hash", "affected", "note", "status"):
        assert col in all_df.columns
    assert len(all_df) == len(res["proposals"])
    manifest = __import__("json").loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dry_run"] is True and manifest["no_write"] is True
    assert manifest["inputs"]["item_refcode"]["sha256"]


def test_alias_dryrun_default_fude_has_two_actions(tmp_path):
    """默认提案：FUDE 白色既有 cost_borrow，也有 add_alias（供确认）。"""
    out = tmp_path / "out"
    out.mkdir()
    pd.DataFrame([
        {"name": "KS0007-DM-200-IVORY", "customer_code": "TT0000917K0011610",
         "item_group": "弧形PP棉靠枕", "variant_of": "KS0007"},
    ]).to_csv(out / "item_refcode.csv", index=False, encoding="utf-8")
    from tongtool_order_cost.tongtu_cost_engine.domain.alias_dryrun import DEFAULT_PROPOSALS
    res = build_alias_dryrun(root=tmp_path, months=("202608",), proposals=DEFAULT_PROPOSALS)
    fude = [p for p in res["proposals"] if p["sku"] == "FUDE-huxingdima-wh-200"]
    assert {p["action"] for p in fude} == {"cost_borrow", "add_alias"}
    add = [p for p in fude if p["action"] == "add_alias"][0]
    assert add["target_item"] == "KS0007-DM-200-IVORY"
    assert "cost_borrow_white" in add["note"]
    assert add["status"] == "needs_review"
    assert add["old_hash"] != add["new_hash"]
