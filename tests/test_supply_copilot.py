import json
from pathlib import Path

import pandas as pd

from supply_copilot.recommend import recommend, to_report


def make_pack(root: Path):
    data = root / "data"; data.mkdir(parents=True)
    d6 = pd.DataFrame([{
        "product_id": "KS1", "池": "美东USNJ", "形态": "成品", "UOM": "个",
        "q95": 100, "C可发供给": 40, "en_stock在途+待发": 10, "PO追加(去重)": 0,
        "SO已下": 0, "CG可调拨抵扣": 0, "净需求95": 50, "建议动作": "补",
        "新补数量": 50, "催已有量": 0, "建议数量": 50,
        "需要日": "2026-12-01", "下单日": "2026-11-10", "路线状态": "pool_route_observed",
        "动作原因": "净需求>0 且无迟到在途",
    }])
    d5 = pd.DataFrame([{
        "product_id": "KS1", "pool": "美东USNJ", "physical_form": "成品",
        "canonical_uom": "个", "horizon": 97, "p50": 70, "q90": 90, "q95": 100,
        "model": "ets_ann",
    }])
    d3 = pd.DataFrame([{
        "product_id": "KS1", "pool": "美东USNJ", "physical_form": "成品",
        "canonical_uom": "个", "adopted_model": "ets_ann", "holdout_wape": 0.2,
        "demand_pattern": "smooth",
    }])
    with pd.ExcelWriter(data / "D6_v6_22.xlsx") as w:
        d6.to_excel(w, sheet_name="1_全量动作", index=False)
    with pd.ExcelWriter(data / "D5_v6_8.xlsx") as w:
        d5.to_excel(w, sheet_name="1_预测", index=False)
    with pd.ExcelWriter(data / "D3b_v3_11.xlsx") as w:
        d3.to_excel(w, sheet_name="3_分类", index=False)


def test_recommend_reads_pack_and_reports_evidence(tmp_path):
    make_pack(tmp_path)
    frame = recommend(tmp_path, "USNJ", "KS1")
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["建议动作"] == "补" and row["新补数量"] == 50
    assert row["p50d5"] == 70 and row["q95d5"] == 100
    report = to_report(frame, "USNJ", "2026-11-13", "test")
    assert "结论：补" in report
    assert "C 40" in report and "q95 100" in report


def test_unknown_branch_fails(tmp_path):
    make_pack(tmp_path)
    try:
        recommend(tmp_path, "NOPE", "KS1")
    except SystemExit as exc:
        assert "未找到" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_exact_sku_does_not_match_prefix(tmp_path):
    make_pack(tmp_path)
    # replace D6 with KS100 and KS1000 rows
    data = tmp_path / "data"
    d6 = pd.read_excel(data / "D6_v6_22.xlsx")
    extra = d6.copy(); extra["product_id"] = "KS1000"
    both = pd.concat([d6.assign(product_id="KS100"), extra], ignore_index=True)
    with pd.ExcelWriter(data / "D6_v6_22.xlsx") as w:
        both.to_excel(w, sheet_name="1_全量动作", index=False)
    exact = recommend(tmp_path, "USNJ", "KS100")
    assert list(exact["product_id"]) == ["KS100"]
    pref = recommend(tmp_path, "USNJ", "KS100", like=True)
    assert set(pref["product_id"]) == {"KS100", "KS1000"}


def test_no_silent_50_row_truncation(tmp_path):
    make_pack(tmp_path)
    data = tmp_path / "data"
    d6 = pd.read_excel(data / "D6_v6_22.xlsx")
    rows = pd.concat([d6.assign(product_id=f"KS{i:03d}") for i in range(60)], ignore_index=True)
    with pd.ExcelWriter(data / "D6_v6_22.xlsx") as w:
        rows.to_excel(w, sheet_name="1_全量动作", index=False)
    all_rows = recommend(tmp_path, "USNJ")
    assert len(all_rows) == 60
    assert all_rows.attrs["total"] == 60
