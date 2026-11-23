# -*- coding: utf-8 -*-
"""PROMO-CLEARANCE v2 用例：UOM 分列、缺断货证据降级、撤回过度结论、边界保留。"""

from __future__ import annotations

import json

import pandas as pd

from supply_netting.promo_clearance_v2 import (
    CATEGORIES,
    CAUSE_ALIAS,
    WITHDRAWN,
    build,
    classify,
    summarise,
)


def frame():
    """三档输入：有在途 / 有零库存+降价 / 只有降价没有零库存证据（含未证单位）。"""
    rows = [
        # 零库存 + 在途快照 → 断货回补+有在途
        dict(sku="A", aug_zero=4, on_order=20, price_chg=-0.05, ratio=2.1, cause="断货回补+有补货"),
        # 零库存 + 降价 + 无在途 → 线索
        dict(sku="B", aug_zero=4, on_order=0, price_chg=-0.12, ratio=2.5,
             cause="断货回补后降价清库存嫌疑"),
        # 零库存 + 无降价 → 回补未补货
        dict(sku="C", aug_zero=4, on_order=0, price_chg=0.02, ratio=2.2, cause="断货回补(未补货)"),
        # 无零库存证据 + 单价不动 → 非价格因素
        dict(sku="D", aug_zero=0, on_order=0, price_chg=0.005, ratio=2.4, cause="非价格因素"),
        # 无零库存证据 + 降价 → v2 降为「其他/需确认」，不再是清库存
        dict(sku="E", aug_zero=0, on_order=0, price_chg=-0.20, ratio=3.0, cause="降价清库存嫌疑"),
        # 未证单位 + 降价 → 其他/需确认，且数量不得进「个」合计
        dict(sku="PP10LB", aug_zero=0, on_order=0, price_chg=-0.06, ratio=10.0, cause="其他/需确认"),
    ]
    demo = pd.DataFrame(rows)
    for month in range(1, 10):
        demo[f"2026-{month:02d}"] = 10.0
    demo["2026-09"] = [10, 22, 13, 12, 30, 10]
    demo["2026-08"] = 5.0
    return demo


UOM_MAP = {
    "A": dict(uom="个", evidence="test"),
    "B": dict(uom="个", evidence="test"),
    "C": dict(uom="个", evidence="test"),
    "D": dict(uom="个", evidence="test"),
    "E": dict(uom="个", evidence="test"),
    "PP10LB": dict(uom="unknown", evidence="EN Item not found"),
}


def test_f1_missing_stockout_evidence_is_downgraded():
    out = classify(frame(), UOM_MAP).set_index("sku")
    # 没有零库存观测的降价者不得叫清库存
    assert out.loc["E", "category"] == "其他/需确认"
    assert out.loc["PP10LB", "category"] == "其他/需确认"
    assert bool(out.loc["E", "clearance_lead"]) is False
    assert bool(out.loc["E", "manual_review_required"]) is True
    # 有零库存观测 + 降价 + 无在途 才是线索
    assert out.loc["B", "category"] == "回补后降价线索"
    assert bool(out.loc["B", "clearance_lead"]) is True
    assert set(out["category"]) <= set(CATEGORIES)


def test_f2_no_auto_exclusion_and_nothing_confirmed():
    out = classify(frame(), UOM_MAP)
    assert not out["auto_exclusion"].any()
    assert not out["clearance_confirmed"].any()
    assert set(out["evidence_state"]) <= {"lead", "observed_only"}
    # 线索只给待核/敏感性，不给「可进训练」
    b = out.set_index("sku").loc["B"]
    assert "待核" in b["training_treatment"] and "敏感" in b["training_treatment"]
    a = out.set_index("sku").loc["A"]
    assert "可进训练" not in str(a["training_treatment"])
    # 有在途组也不再被判「正常训练」
    assert "可进训练" not in " ".join(out["category_note"])


def test_f3_uom_split_no_cross_unit_total():
    out = classify(frame(), UOM_MAP)
    summary = summarise(out)
    assert summary["no_cross_uom_total"] is True
    piece = summary["by_uom"]["个"]
    unknown = summary["by_uom"]["unknown"]
    # PP10LB 的 10 个原始数量只能落在 unknown，不进「个」
    assert piece["candidates"] == 5 and piece["sept_qty"] == 87.0
    assert unknown["candidates"] == 1 and unknown["sept_qty"] == 10.0
    assert piece["leads"] == 1 and piece["lead_sept_qty"] == 22.0
    # 不存在跨单位合计字段
    assert "clearance_sept_qty" not in summary and "all_sept_qty" not in summary
    # uom 未证行必须带证据说明
    assert "not found" in out.set_index("sku").loc["PP10LB", "uom_evidence"]


def test_withdrawn_claims_and_boundaries(tmp_path):
    cand = tmp_path / "c.csv"
    frame().to_csv(cand, index=False, encoding="utf-8-sig")
    out = tmp_path / "out"
    manifest = build(str(cand), str(out), disposition=None)

    assert manifest["status"] == "pending"
    assert set(WITHDRAWN) <= set(manifest["withdrawn"])
    assert "312" in manifest["withdrawn"][3]

    text = (out / "report.md").read_text(encoding="utf-8")
    # 三条边界保留
    assert "isPromotion 不可得" in text
    assert "不虚构因果" in text
    assert "不建促销日历" in text
    # 撤回的结论只能以「撤回」条目的形式出现，不得作为现行建议
    for banned in ("排除 2026-09 销量", "销量可进训练"):
        hits = [ln for ln in text.splitlines() if banned in ln]
        assert hits, f"{banned} 应作为撤回条目出现"
        assert all(any(k in ln for k in ("撤回", "不再写")) for ln in hits), \
            f"{banned} 出现在非撤回语境"
    assert "不跨单位合计" in text
    # 无单位来源时全部落到 unknown，且不产生跨单位合计
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert set(summary["by_uom"]) == {"unknown"}
    assert summary["auto_excluded"] == 0


def test_missing_inputs_are_not_read_as_zero():
    """缺值不得 fillna(0)：未知库存/在途 → 其他/需确认，不是「无断货」也不是「无在途」。"""
    demo = frame().copy()
    demo.loc[demo["sku"] == "B", "on_order"] = None      # 在途未知
    demo.loc[demo["sku"] == "C", "aug_zero"] = None      # 零库存观测未知
    demo.loc[demo["sku"] == "D", "price_chg"] = None     # 价格未知
    out = classify(demo, UOM_MAP).set_index("sku")
    for sku in ("B", "C", "D"):
        assert out.loc[sku, "category"] == "其他/需确认", sku
        assert bool(out.loc[sku, "clearance_lead"]) is False, sku
        assert "missing=" in out.loc[sku, "evidence"], sku
    assert bool(out.loc["B", "on_order_known"]) is False
    assert pd.isna(out.loc["B", "on_order_snapshot"])
    # 齐备的行仍按原规则判，说明不是一刀切
    assert out.loc["A", "category"] == "断货回补+有在途"


def test_v1_category_column_matches_v1_module_exactly():
    """对照列必须等于 v1 的判定——直接对拍 v1 模块，防止人工维护的复刻漂移。"""
    from supply_netting.promo_clearance import classify as classify_v1

    demo = frame()
    v1 = classify_v1(demo.copy())
    v2 = classify(demo, UOM_MAP)
    assert list(v1["sku"]) == list(v2["sku"])
    assert list(v1["category"]) == list(v2["v1_category"])

    # 缺值路径也要一致（v1 用 fillna(0)，复刻版必须同样处理）
    dirty = demo.copy()
    dirty.loc[dirty["sku"] == "B", "on_order"] = None
    dirty.loc[dirty["sku"] == "C", "aug_zero"] = None
    assert (list(classify_v1(dirty.copy())["category"])
            == list(classify(dirty, UOM_MAP)["v1_category"]))


def test_v1_category_changes_only_the_downgraded_rows():
    out = classify(frame(), UOM_MAP).set_index("sku")
    # 那 5 个「无零库存观测 + 降价」在 v1 里是清库存，v2 降级 → 算真改类
    assert out.loc["E", "v1_category"] == "回补后降价清库存"
    assert out.loc["E", "category"] == "其他/需确认"
    assert bool(out.loc["E", "category_changed_from_v1"]) is True
    assert out.loc["PP10LB", "v1_category"] == "回补后降价清库存"
    assert bool(out.loc["PP10LB", "category_changed_from_v1"]) is True
    # 纯改名的等价行不算改类
    assert out.loc["A", "v1_category"] == "断货回补+有补货"
    assert bool(out.loc["A", "category_changed_from_v1"]) is False
    assert out.loc["B", "v1_category"] == "回补后降价清库存"
    assert bool(out.loc["B", "category_changed_from_v1"]) is False
    assert int(out["category_changed_from_v1"].sum()) == 2


def test_manifest_and_csv_carry_cross_version_columns(tmp_path):
    cand = tmp_path / "c.csv"
    frame().to_csv(cand, index=False, encoding="utf-8-sig")
    out = tmp_path / "out"
    manifest = build(str(cand), str(out), disposition=None)

    skus = pd.read_csv(out / "promo_clearance_skus.csv")
    assert {"v1_category", "category_changed_from_v1"} <= set(skus.columns)
    assert set(skus["v1_category"]) <= set(
        ["断货回补+有补货", "回补后降价清库存", "回补未补货", "非价格因素", "其他/需确认"])

    mapping = manifest["category_mapping"]
    assert mapping["changed_skus"] == 2
    assert mapping["equivalent"]["断货回补+有补货"] == "断货回补+有在途"
    assert mapping["crosstab"]["回补后降价清库存"]["其他/需确认"] == 2

    # 输出身份：每个产物都有 sha256
    outputs = manifest["outputs"]
    assert len(outputs) == 6
    assert all(len(info["sha256"]) == 64 for info in outputs.values())
    assert _sha256_of(out / "report.md") == outputs["report.md"]["sha256"]

    text = (out / "report.md").read_text(encoding="utf-8")
    assert "跨版本可比" in text and "仅改名" in text


def _sha256_of(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cause_alias_makes_agreement_meaningful():
    out = classify(frame(), UOM_MAP).set_index("sku")
    # 归一化后 A/B/C/D 与 v2 类别一致；E、PP10LB 不一致（v1 曾判清库存）
    assert bool(out.loc["A", "agree_with_original"]) is True
    assert bool(out.loc["B", "agree_with_original"]) is True
    assert bool(out.loc["C", "agree_with_original"]) is True
    assert bool(out.loc["E", "agree_with_original"]) is False
    assert CAUSE_ALIAS["降价清库存嫌疑"] == "回补后降价线索"
