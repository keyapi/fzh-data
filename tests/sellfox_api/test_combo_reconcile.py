"""Pure-logic tests for EN Product Bundle ↔ Sellfox combo reconciliation."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

import requests  # noqa: E402

from combo_en import (  # noqa: E402
    EnRestClient,
    assert_en_create_payload,
    en_create_payload,
)
from combo_reconcile import (  # noqa: E402
    BundleChild,
    EnBundle,
    PlanRow,
    SellfoxCombo,
    assert_combo_row,
    composition_key,
    parse_child_specs,
    parse_sellfox_children,
    plan_sync,
    summarize_plan,
    validate_en_bundle,
    writable_actions,
)


def _bundle(**kwargs) -> EnBundle:
    defaults = dict(
        name="TJ#KS0443x2-001",
        new_item_code="TJ#KS0443x2-001",
        new_item_code_name="套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
        items=(BundleChild("KS0443-DM-70x70x25-GRASSGREEN", 2),),
        item_code="TJ#KS0443x2-001",
        item_name="套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
        item_group="套件#",
    )
    defaults.update(kwargs)
    return EnBundle(**defaults)


def test_composition_key_is_order_independent():
    a = composition_key([("B", 1), ("A", 2)])
    b = composition_key([("A", 2), ("B", 1)])
    assert a == b == (("A", 2), ("B", 1))


def test_parse_child_specs_from_cli():
    assert parse_child_specs(["KS1:2", "KS2:1"]) == (("KS1", 2), ("KS2", 1))


def test_parse_sellfox_children_accepts_string_nums():
    children = parse_sellfox_children(
        [{"sku": "KS1", "num": "2", "childId": "1"}, {"sku": "KS2", "num": 1}]
    )
    assert children == (("KS1", 2), ("KS2", 1))


def test_validate_empty_items_is_blocked():
    problems = validate_en_bundle(_bundle(items=()))
    assert "empty_items" in problems


def test_validate_name_ne_new_item_code():
    problems = validate_en_bundle(_bundle(name="NEW-KS0443-tmp"))
    assert "name_ne_new_item_code" in problems
    assert "invalid_tj_serial" in problems


def test_validate_item_code_mismatch():
    problems = validate_en_bundle(_bundle(item_code="OTHER"))
    assert "item_code_ne_new_item_code" in problems


def test_validate_item_name_mismatch():
    problems = validate_en_bundle(_bundle(item_name="别的名字-001"))
    assert "item_name_ne_new_item_code_name" in problems


def test_validate_zero_qty():
    problems = validate_en_bundle(
        _bundle(items=(BundleChild("KS0443-DM-70x70x25-GRASSGREEN", 0),))
    )
    assert "non_positive_qty:KS0443-DM-70x70x25-GRASSGREEN" in problems


def test_validate_missing_item():
    problems = validate_en_bundle(_bundle(item_code=""))
    assert "missing_item" in problems


def test_validate_good_bundle_has_no_problems():
    assert validate_en_bundle(_bundle()) == ()


def test_plan_create_when_sellfox_missing_and_bottoms_exist():
    plan = plan_sync(
        [_bundle()],
        sellfox_by_sku={},
        bottoms_present={"KS0443-DM-70x70x25-GRASSGREEN"},
    )
    assert [row.action for row in plan.rows] == ["create"]
    assert plan.counts["create"] == 1


def test_plan_ok_when_children_and_category_match():
    combo = SellfoxCombo(
        sku="TJ#KS0443x2-001",
        name="套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
        is_group="1",
        full_cid="428697-",
        child_skus=(("KS0443-DM-70x70x25-GRASSGREEN", 2),),
    )
    plan = plan_sync(
        [_bundle()],
        sellfox_by_sku={"TJ#KS0443x2-001": combo},
        bottoms_present={"KS0443-DM-70x70x25-GRASSGREEN"},
    )
    assert plan.rows[0].action == "ok"


def test_plan_set_category_when_only_category_wrong():
    combo = SellfoxCombo(
        sku="TJ#KS0443x2-001",
        is_group="1",
        full_cid="",
        child_skus=(("KS0443-DM-70x70x25-GRASSGREEN", 2),),
    )
    plan = plan_sync(
        [_bundle()],
        sellfox_by_sku={"TJ#KS0443x2-001": combo},
        bottoms_present={"KS0443-DM-70x70x25-GRASSGREEN"},
    )
    assert plan.rows[0].action == "set_category"


def test_plan_mismatch_does_not_become_update():
    combo = SellfoxCombo(
        sku="TJ#KS0443x2-001",
        is_group="1",
        full_cid="428697-",
        child_skus=(("KS0443-DM-70x70x25-GRASSGREEN", 3),),
    )
    plan = plan_sync(
        [_bundle()],
        sellfox_by_sku={"TJ#KS0443x2-001": combo},
        bottoms_present={"KS0443-DM-70x70x25-GRASSGREEN"},
    )
    assert plan.rows[0].action == "mismatch"
    assert "create" not in writable_actions(plan)
    assert "set_category" not in writable_actions(plan)


def test_plan_not_group_is_mismatch():
    combo = SellfoxCombo(
        sku="TJ#KS0443x2-001",
        is_group="0",
        full_cid="428697-",
        child_skus=(("KS0443-DM-70x70x25-GRASSGREEN", 2),),
    )
    plan = plan_sync(
        [_bundle()],
        sellfox_by_sku={"TJ#KS0443x2-001": combo},
        bottoms_present={"KS0443-DM-70x70x25-GRASSGREEN"},
    )
    assert plan.rows[0].action == "mismatch"


def test_plan_blocked_bottoms_when_creating():
    plan = plan_sync(
        [_bundle()],
        sellfox_by_sku={},
        bottoms_present=set(),
    )
    assert plan.rows[0].action == "blocked_bottoms"
    assert plan.rows[0].problems == ("KS0443-DM-70x70x25-GRASSGREEN",)


def test_plan_blocked_en_empty_items():
    plan = plan_sync(
        [_bundle(items=())],
        sellfox_by_sku={},
        bottoms_present=set(),
    )
    assert plan.rows[0].action == "blocked_en"


def test_plan_skip_historical_fxlssf3030():
    hist = _bundle(
        name="FXLSSF3030",
        new_item_code="FXLSSF3030",
        new_item_code_name="历史老套件",
        item_code="FXLSSF3030",
        item_name="历史老套件",
        items=(BundleChild("KS0001-A", 1),),
    )
    plan = plan_sync([hist], sellfox_by_sku={}, bottoms_present={"KS0001-A"})
    assert plan.rows[0].action == "skip_historical"


def test_plan_keeps_001_and_002_as_separate_skus():
    b1 = _bundle()
    b2 = _bundle(
        name="TJ#KS0443x2-002",
        new_item_code="TJ#KS0443x2-002",
        new_item_code_name="套件#麻将沙发纯色版-涤麻-70x70x25cm-象牙白色x2件-002",
        item_code="TJ#KS0443x2-002",
        item_name="套件#麻将沙发纯色版-涤麻-70x70x25cm-象牙白色x2件-002",
        items=(BundleChild("KS0443-DM-70x70x25-IVORY", 2),),
    )
    plan = plan_sync(
        [b1, b2],
        sellfox_by_sku={},
        bottoms_present={
            "KS0443-DM-70x70x25-GRASSGREEN",
            "KS0443-DM-70x70x25-IVORY",
        },
    )
    assert [row.sku for row in plan.rows] == [
        "TJ#KS0443x2-001",
        "TJ#KS0443x2-002",
    ]
    assert plan.counts["create"] == 2


def test_assert_combo_row_detects_child_qty_and_is_group():
    row = {
        "sku": "TJ#KS0443x2-001",
        "name": "套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
        "isGroup": "1",
        "fullCid": "428697-",
        "childSkus": [{"sku": "KS0443-DM-70x70x25-GRASSGREEN", "num": "1"}],
    }
    failures = assert_combo_row(
        row,
        sku="TJ#KS0443x2-001",
        name="套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
        children=(("KS0443-DM-70x70x25-GRASSGREEN", 2),),
        full_cid="428697-",
    )
    assert failures == ("childSkus",)


def test_assert_combo_row_passes_when_consistent():
    row = {
        "sku": "TJ#KS0443x2-001",
        "name": "套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
        "isGroup": 1,
        "fullCid": "428697-",
        "childSkus": [{"sku": "KS0443-DM-70x70x25-GRASSGREEN", "num": "2"}],
    }
    assert (
        assert_combo_row(
            row,
            sku="TJ#KS0443x2-001",
            name="套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
            children=(("KS0443-DM-70x70x25-GRASSGREEN", 2),),
            full_cid="428697-",
        )
        == ()
    )


def test_existing_combo_mismatch_is_not_ok_skip():
    combo = SellfoxCombo(
        sku="TJ#KS0443x2-001",
        is_group="1",
        full_cid="428697-",
        child_skus=(("WRONG", 1),),
    )
    plan = plan_sync(
        [_bundle()],
        sellfox_by_sku={"TJ#KS0443x2-001": combo},
        bottoms_present={"KS0443-DM-70x70x25-GRASSGREEN"},
    )
    assert plan.rows[0].action == "mismatch"
    assert plan.rows[0].action != "ok"


def test_summarize_plan_preserves_unmatched_and_traces_counts():
    plan = plan_sync(
        [_bundle(), _bundle(items=())],
        sellfox_by_sku={},
        bottoms_present={"KS0443-DM-70x70x25-GRASSGREEN"},
    )
    summary = summarize_plan(plan)
    assert summary["input_en"] == 2
    assert summary["output_rows"] == 2
    assert summary["counts"]["create"] == 1
    assert summary["counts"]["blocked_en"] == 1
    unmatched_actions = {row["action"] for row in summary["unmatched"]}
    assert unmatched_actions == {"blocked_en"}
    assert summary["input_en"] - summary["output_rows"] == 0


def test_plan_row_dataclass_roundtrip_fields():
    row = PlanRow(
        sku="TJ#KS0443x2-001",
        action="create",
        reason="sellfox_missing",
        name="套件#x2-001",
        expected_children=(("KS1", 2),),
    )
    assert row.sku.startswith("TJ#")


def test_en_create_payload_is_items_only():
    payload = en_create_payload((("KS0443-DM-70x70x25-GRASSGREEN", 2),))
    assert list(payload) == ["items"]
    assert payload["items"] == [
        {"item_code": "KS0443-DM-70x70x25-GRASSGREEN", "qty": 2}
    ]
    assert_en_create_payload(payload)


def test_en_create_payload_rejects_temp_code_fields():
    payload = en_create_payload((("KS1", 1),))
    payload["new_item_code"] = "NEW-KS0443-tmp"
    try:
        assert_en_create_payload(payload)
    except ValueError as exc:
        assert "new_item_code" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_en_create_payload_rejects_empty_items():
    try:
        en_create_payload(())
    except ValueError as exc:
        assert "items" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_en_list_requires_explicit_scope():
    client = EnRestClient("https://example.invalid", requests.Session())
    try:
        client.list_bundle_names(name_like=None, names=None)
    except ValueError as exc:
        assert "禁止无范围" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_cmd_create_existing_mismatch_is_not_silent_skip():
    import argparse
    from sellfox_combo_ops import cmd_create

    class FakeClient:
        def signed_post(self, url, payload):
            return {
                "rows": [
                    {
                        "sku": "TJ#KS0443x2-001",
                        "name": "套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
                        "isGroup": "1",
                        "fullCid": "428697-",
                        "childSkus": [
                            {"sku": "KS0443-DM-70x70x25-GRASSGREEN", "num": "9"}
                        ],
                    }
                ]
            }

    args = argparse.Namespace(
        sku="TJ#KS0443x2-001",
        name="套件#麻将沙发纯色版-涤麻-70x70x25cm-草绿色x2件-001",
        child=["KS0443-DM-70x70x25-GRASSGREEN:2"],
        full_cid="428697-",
        auto_calc_weight="true",
        apply=False,
    )
    try:
        cmd_create(FakeClient(), args)
    except SystemExit as exc:
        assert "回读断言失败" in str(exc)
        assert "childSkus" in str(exc)
    else:
        raise AssertionError("expected SystemExit")
