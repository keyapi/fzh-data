# -*- coding: utf-8 -*-
"""工作簿 v4 用例：窗口动作重算、SO 按 UOM、边界披露、证据入口。"""

from __future__ import annotations

import json

import openpyxl
import pandas as pd
import pytest

from supply_netting.business_review_v4 import build_workbook_v4

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]


def _write_inputs(tmp_path):
    windows = pd.DataFrame([
        dict(window_days=d, uom="个", bucket_id=f"w{d}", bucket_end="2027-04-26",
             actual_days=a, buckets_count=d // 7, forecast_demand=100.0 * d,
             cum_unserved=10.0 * d, gap_keys=1, suggestion_keys=1, qty_current=50.0 * d,
             qty_higher=60.0 * d, usage="review_candidate", note="累计窗口")
        for d, a in ((30, 35), (60, 63), (90, 91), (150, 154), (180, 182))
    ])
    keys = pd.DataFrame([
        dict(window_days=d, bucket_end="2027-04-26", canonical_sku="S1",
             canonical_warehouse="W", canonical_uom="个", forecast_demand=100.0,
             cum_unserved=90.0, qty_current=gap, qty_higher=gap + 14, gap=True)
        for d, gap in ((90, 40.0), (150, 60.0), (180, 90.0))
    ])
    actions = pd.DataFrame([
        dict(canonical_sku="S1", canonical_warehouse="W", canonical_uom="个",
             destination="建议补货", action="催发运", action_qty=999.0, residual_gap=0.0,
             so_stage_produced_pending_dn=25.0, so_stage_in_production=0.0,
             so_stage_in_transit=50.0, so_stage_not_planned=0.0,
             so_stage_unknown_missing_start=0.0, so_stage_unknown_other=0.0,
             conditional_supply_qty=0.0, po_qty=0.0, intransit_qty=0.0,
             w1_confidence="measured", action_source_so="SO-1", action_source_wo=None),
        dict(canonical_sku="S9", canonical_warehouse="W", canonical_uom="个",
             destination="待核", action=None, action_qty=None, residual_gap=None,
             so_stage_produced_pending_dn=0.0, so_stage_in_production=0.0,
             so_stage_in_transit=0.0, so_stage_not_planned=0.0,
             so_stage_unknown_missing_start=0.0, so_stage_unknown_other=0.0,
             conditional_supply_qty=0.0, po_qty=0.0, intransit_qty=0.0,
             w1_confidence=None, action_source_so=None, action_source_wo=None),
    ])
    audit = pd.DataFrame([dict(SO="SO-1", 处置建议="可作条件供给", 开放量=100.0,
                               异常="无", 日期置信度="estimated", 预计到仓="2027-04-05")])
    w1_lines = [
        dict(payload=dict(lines=[
            dict(so="SO-1", uom="个", qty=80.0, delivered_qty=0.0, customer="DANEEY"),
            dict(so="SO-1", uom="套", qty=5.0, delivered_qty=0.0, customer="DANEEY"),
            dict(so="SO-2", uom="件", qty=3.0, delivered_qty=0.0, customer="CENTRADE"),
        ]))
    ]
    paths = {}
    for name, frame, writer in (("windows", windows, "csv"), ("keys", keys, "csv"),
                                ("audit", audit, "csv"), ("actions", actions, "parquet")):
        path = tmp_path / f"{name}.{writer}"
        (frame.to_csv(path, index=False) if writer == "csv"
         else frame.to_parquet(path, index=False))
        paths[name] = path
    w1 = tmp_path / "w1.jsonl"
    w1.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in w1_lines), encoding="utf-8")
    paths["w1"] = w1
    r6 = tmp_path / "r6_manifest.json"
    r6.write_text(json.dumps({"run_id": "r6"}), encoding="utf-8")
    paths["r6"] = r6
    return paths


def build(tmp_path):
    paths = _write_inputs(tmp_path)
    out = tmp_path / "review-v4.xlsx"
    manifest = build_workbook_v4(windows_csv=paths["windows"], keys_csv=paths["keys"],
                                 actions_parquet=paths["actions"], so_audit_csv=paths["audit"],
                                 w1_jsonl=paths["w1"], r6_manifest=paths["r6"], out_path=out)
    return openpyxl.load_workbook(out), manifest


def test_actions_are_recomputed_per_window_not_inherited(tmp_path):
    book, _ = build(tmp_path)
    rows = {}
    for sheet in ("2_90天主表", "4_180天情景"):
        ws = book[sheet]
        header = [c.value for c in ws[1]]
        record = dict(zip(header, [c.value for c in ws[2]]))
        rows[sheet] = record
    # 90 天：缺口 40，阶段证据里在途 50 → 覆盖 40，剩余 0
    assert rows["2_90天主表"]["建议量（逐键向上取整）"] == 40
    assert rows["2_90天主表"]["动作量"] == 40
    assert rows["2_90天主表"]["剩余需补"] == 0
    # 180 天：缺口 90，按「覆盖优先、同覆盖按 完工→在产→在途」取第一层
    # → 完工待发运 25 先入选（不足以全覆盖），动作量 25、剩余 65
    assert rows["4_180天情景"]["动作量"] == 25
    assert rows["4_180天情景"]["剩余需补"] == 65
    # 不是照抄动作层的 999
    assert rows["2_90天主表"]["动作量"] != 999
    assert "按 90 天窗口缺口重算" in str(rows["2_90天主表"]["动作口径"])


def test_g_column_renamed_and_buffer_kept(tmp_path):
    book, _ = build(tmp_path)
    header = [c.value for c in book["2_90天主表"][1]]
    assert "加缓冲后总量" in header
    assert "参考缓冲（+14 天）" not in header
    record = dict(zip(header, [c.value for c in book["2_90天主表"][2]]))
    assert record["加缓冲后总量"] == 54        # 建议量 40 + 14


def test_so_summary_is_split_by_uom_without_total(tmp_path):
    book, manifest = build(tmp_path)
    ws = book["7_SO审计摘要"]
    rows = [list(r) for r in ws.iter_rows(max_row=5, values_only=True)]
    assert rows[0][0] == "单位"
    units = {r[0]: r[1] for r in rows[1:] if r[0]}
    assert units == {"个": 80.0, "套": 5.0, "件": 3.0}
    assert not any(str(r[0]) in ("合计", "总计", "全部", "all") for r in rows[1:] if r[0])
    assert all(float(r[1]) != 88.0 for r in rows[1:] if r[1] is not None)   # 不出现跨单位总量
    assert "非可抵扣量" in str(rows[1][4])
    assert "个 80" in manifest["sheets"]["7_SO审计摘要"]


def test_boundaries_disclose_blind_window_and_action_source(tmp_path):
    book, _ = build(tmp_path)
    ws = book["1_说明与边界"]
    text = "\n".join(f"{ws.cell(r, 1).value}｜{ws.cell(r, 2).value}"
                     for r in range(2, ws.max_row + 1))
    for key in ("2.779 天", "未进入净额基线", "14 天参考缓冲", "实际天数",
                "189 天", "按各页窗口缺口重算"):
        assert key in text


def test_manifest_records_evidence_and_recompute_rule(tmp_path):
    _, manifest = build(tmp_path)
    assert manifest["action_recompute"]["evidence_source"].startswith("h180")
    assert "不使用 h180" in manifest["action_recompute"]["not_reused"]
    assert manifest["inputs"]["r6_manifest_sha256"]
    assert manifest["counts"]["main90"] == 1 and manifest["counts"]["scenario180"] == 1
