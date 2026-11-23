# -*- coding: utf-8 -*-
"""live_rules 纯函数测试：日期重算 / 交期列识别 / CG 上界 / 通途 PO JSONL。

全部离线，用假 SKU（TT1→KS1）与假仓配置；不依赖真实客户数据。
"""

import json

import pandas as pd
import pytest

from supply_copilot.live_rules import (
    PO_OPEN_STATUSES,
    cg_allowance,
    lead_days_for,
    po_open_from_purchase_jsonl,
    recalc_dates,
)

WAREHOUSE_CFG = {
    "aliases": {
        "FZH-DANEEY": {"canonical": "美中-FZH-DANEEY",
                       "status": "alias_confirmed", "evidence": "test"},
        "CENTRADE": {"canonical": "美东-CENTRADE",
                     "status": "alias_confirmed", "evidence": "test"},
    },
    "third_party": {},
    "roles": {},
    "not_merged": {},
    "declared": {},
    "canonical_roles": {},
}


# --------------------------------------------------------------------------- #
# 1) recalc_dates
# --------------------------------------------------------------------------- #
def test_recalc_dates_future():
    result = recalc_dates("2027-02-16", "2026-11-23", 30)
    assert result["order_date"] == "2027-01-17"
    assert result["status"] == "future"
    assert result["need_date"] == "2027-02-16"
    assert result["lead_days"] == 30
    assert result["as_of"] == "2026-11-23"


def test_recalc_dates_past_due():
    result = recalc_dates("2026-12-01", "2026-11-23", 30)
    assert result["order_date"] == "2026-11-01"
    assert result["status"] == "past_due"


def test_recalc_dates_order_day_equals_as_of_is_future():
    # 下单日 == 决策当天：还没过，算 future（与 decide._date_status 一致）
    result = recalc_dates("2026-12-23", "2026-11-23", 30)
    assert result["order_date"] == "2026-11-23"
    assert result["status"] == "future"


def test_recalc_dates_accepts_iso_datetime_with_offset():
    result = recalc_dates("2026-12-15 00:00:00",
                          "2026-11-23T10:47:42+08:00", 10)
    assert result["order_date"] == "2026-12-05"
    assert result["status"] == "future"


@pytest.mark.parametrize("need_date,lead_days", [
    (None, 30),
    ("2027-02-16", None),
    ("2027-02-16", 0),
    ("2027-02-16", -5),
    ("2027-02-16", 1.5),
    ("2027-02-16", "abc"),
    ("not-a-date", 30),
])
def test_recalc_dates_unknown_when_missing(need_date, lead_days):
    result = recalc_dates(need_date, "2026-11-23", lead_days)
    assert result["order_date"] is None
    assert result["status"] == "unknown"


def test_recalc_dates_without_as_of_keeps_order_date_but_unknown_status():
    result = recalc_dates("2027-02-16", None, 30)
    assert result["order_date"] == "2027-01-17"
    assert result["status"] == "unknown"


# --------------------------------------------------------------------------- #
# 2) lead_days_for
# --------------------------------------------------------------------------- #
POLICY_ROWS = [
    {"sku": "KS1", "pool": "美中USTX", "lead_days": 30},
    {"sku": "KS2", "pool": "美中USTX", "交期": "45天"},
    {"sku": "KS3", "pool": "美中USTX", "lead_time": 20},
    {"sku": "KS4", "pool": "美中USTX", "canonical_uom": "个"},   # 无交期列
]


def test_lead_days_from_common_column_names():
    assert lead_days_for("KS1", POLICY_ROWS) == 30
    assert lead_days_for("KS2", POLICY_ROWS) == 45
    assert lead_days_for("KS3", POLICY_ROWS) == 20


def test_lead_days_accepts_dataframe():
    frame = pd.DataFrame(POLICY_ROWS)
    assert lead_days_for("KS2", frame) == 45


def test_lead_days_missing_returns_default():
    assert lead_days_for("KS4", POLICY_ROWS) is None
    assert lead_days_for("KS4", POLICY_ROWS, default=60) == 60
    assert lead_days_for("UNKNOWN", POLICY_ROWS, default=60) == 60


def test_lead_days_without_recognized_column_returns_default():
    rows = [{"sku": "KS1", "service_level_prior": 0.85}]
    assert lead_days_for("KS1", rows, default=7) == 7


def test_lead_days_conflicting_values_not_guessed():
    rows = [{"sku": "KS1", "lead_days": 30}, {"sku": "KS1", "lead_days": 45}]
    assert lead_days_for("KS1", rows, default=60) == 60


def test_lead_days_invalid_value_not_guessed():
    rows = [{"sku": "KS1", "lead_days": 0}, {"sku": "KS1", "lead_days": "unknown"}]
    assert lead_days_for("KS1", rows, default=60) == 60


# --------------------------------------------------------------------------- #
# 3) cg_allowance
# --------------------------------------------------------------------------- #
def make_stock():
    return pd.DataFrame([
        {"sku": "TT1", "warehouse_name": "WayfairCG-Cranbury仓", "available": 3},
        {"sku": "TT1", "warehouse_name": "WayfairCG-Romeoville仓", "available": 2},
        {"sku": "TT2", "warehouse_name": "WayfairCG-Cranbury仓", "available": -1},
        {"sku": "TT2", "warehouse_name": "WayfairCG-Cranbury仓", "available": "abc"},
        {"sku": "TT9", "warehouse_name": "WayfairCG-Cranbury仓", "available": 4},
        {"sku": "TT1", "warehouse_name": "美中-FZH-DANEEY", "available": 100},
    ])


LOOKUP = {"TT1": "KS1", "TT2": "KS2"}


def test_cg_without_rule_gives_upper_bound_only():
    per_sku, evidence = cg_allowance(make_stock(), LOOKUP)
    assert per_sku == {"KS1": 5.0, "KS2": -1.0}
    assert evidence["by_sku"]["KS1"]["upper_bound"] == 5.0
    assert evidence["by_sku"]["KS1"]["allowed"] is None
    assert evidence["by_sku"]["KS1"]["conditional"] is False
    assert evidence["conditional"] is False
    assert evidence["max_share"] is None
    assert evidence["transfer_date"] is None
    # 只认 WayfairCG-*：本分公司仓的 100 不进
    assert evidence["quantity"] == 4.0


def test_cg_unmapped_sku_is_counted_not_guessed():
    per_sku, evidence = cg_allowance(make_stock(), LOOKUP)
    assert "TT9" not in per_sku
    assert evidence["unmapped_rows"] == 1
    assert evidence["unmapped_skus"] == ["TT9"]
    assert evidence["rows"] == 5
    assert evidence["rows_missing_available"] == 1


def test_cg_with_rule_gives_conditional_allowed():
    per_sku, evidence = cg_allowance(make_stock(), LOOKUP,
                                     rule={"max_share": 0.5})
    assert per_sku["KS1"] == 5.0
    assert evidence["by_sku"]["KS1"]["allowed"] == pytest.approx(2.5)
    assert evidence["by_sku"]["KS1"]["conditional"] is True
    assert evidence["conditional"] is True
    assert evidence["allowed_source"] == "rule.max_share"
    assert evidence["transfer_date"] is None   # 没有可执行调拨日期


@pytest.mark.parametrize("rule", [{"max_share": 1.5}, {"max_share": -0.1},
                                  {"max_share": "half"}])
def test_cg_invalid_rule_raises(rule):
    with pytest.raises(ValueError):
        cg_allowance(make_stock(), LOOKUP, rule=rule)


def test_cg_rule_without_max_share_is_not_a_deduction():
    per_sku, evidence = cg_allowance(make_stock(), LOOKUP, rule={"note": "x"})
    assert evidence["by_sku"]["KS1"]["allowed"] is None
    assert evidence["conditional"] is False


# --------------------------------------------------------------------------- #
# 4) po_open_from_purchase_jsonl
# --------------------------------------------------------------------------- #
def write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8")
    return path


def make_po_records():
    return [
        # 开放、无 ETA
        {"PONum": "P1", "goods_sku": "TT1", "quantity": 10, "in_quantity": 4,
         "status": "0", "warehouseName": "FZH-DANEEY"},
        # 开放、willArriveDate
        {"PONum": "P2", "goods_sku": "TT1", "quantity": 5, "in_quantity": 0,
         "status": "1", "warehouseName": "FZH-DANEEY",
         "willArriveDate": "2026-12-20"},
        # 开放、purchaseArrivalDate 兜底
        {"PONum": "P3", "goods_sku": "TT2", "quantity": 2, "in_quantity": 1,
         "status": "2", "warehouseName": "FZH-DANEEY",
         "purchaseArrivalDate": "2026-12-25"},
        # 作废
        {"PONum": "P4", "goods_sku": "TT1", "quantity": 7, "in_quantity": 0,
         "status": "4", "warehouseName": "FZH-DANEEY"},
        # 收满 → open=0
        {"PONum": "P5", "goods_sku": "TT1", "quantity": 3, "in_quantity": 3,
         "status": "0", "warehouseName": "FZH-DANEEY"},
        # 未映射 SKU + 仓不落本分公司
        {"PONum": "P6", "goods_sku": "TT9", "quantity": 8, "in_quantity": 0,
         "status": "0", "warehouseName": "CENTRADE"},
        # 缺数量
        {"PONum": "P7", "goods_sku": "TT1", "in_quantity": 0,
         "status": "0", "warehouseName": "FZH-DANEEY"},
        # 不支持的状态
        {"PONum": "P8", "goods_sku": "TT1", "quantity": 9, "in_quantity": 0,
         "status": "9", "warehouseName": "FZH-DANEEY"},
    ]


def test_po_open_parses_open_cancelled_eta(tmp_path):
    path = write_jsonl(tmp_path / "po.jsonl", make_po_records())
    frame, evidence = po_open_from_purchase_jsonl(
        path, LOOKUP, warehouse_cfg=WAREHOUSE_CFG, branch_prefix="美中-")

    assert list(frame.columns) == [
        "document_key", "sku", "product_id", "warehouse", "open_qty", "eta",
        "status", "date_unproven", "identity_status", "warehouse_out_of_branch",
    ]
    assert set(frame["status"]) <= PO_OPEN_STATUSES
    by_doc = frame.set_index("document_key")

    assert by_doc.loc["P1", "open_qty"] == 6
    assert by_doc.loc["P1", "product_id"] == "KS1"
    assert by_doc.loc["P1", "identity_status"] == "mapped"
    assert by_doc.loc["P1", "eta"] is None
    assert bool(by_doc.loc["P1", "date_unproven"]) is True

    assert by_doc.loc["P2", "eta"] == "2026-12-20"
    assert bool(by_doc.loc["P2", "date_unproven"]) is False
    assert by_doc.loc["P3", "open_qty"] == 1
    assert by_doc.loc["P3", "eta"] == "2026-12-25"

    assert "P4" not in by_doc.index      # 作废
    assert "P5" not in by_doc.index      # open=0
    assert "P7" not in by_doc.index      # 缺数量
    assert "P8" not in by_doc.index      # 非开放状态

    assert evidence["cancelled_rows"] == 1
    assert evidence["cancelled_quantity"] == 7
    assert evidence["zero_open"] == 1
    assert evidence["missing_quantity"] == 1
    assert evidence["unsupported_status_rows"] == 1
    assert evidence["with_eta"] == 2
    assert evidence["date_unproven"] == 2
    # P1/P2/P3 + 未映射但保留的 P6
    assert evidence["open_rows"] == 4
    assert evidence["quantity"] == pytest.approx(6 + 5 + 1 + 8)


def test_po_unmapped_sku_and_out_of_branch_kept_but_flagged(tmp_path):
    path = write_jsonl(tmp_path / "po.jsonl", make_po_records())
    frame, evidence = po_open_from_purchase_jsonl(
        path, LOOKUP, warehouse_cfg=WAREHOUSE_CFG, branch_prefix="美中-")
    row = frame.set_index("document_key").loc["P6"]
    assert row["open_qty"] == 8
    assert row["identity_status"] == "unmapped"
    assert pd.isna(row["product_id"])
    assert bool(row["warehouse_out_of_branch"]) is True
    assert evidence["identity_missing"] == 1
    assert evidence["warehouse_out_of_branch"] == 1


def test_po_without_lookup_does_not_claim_mapped(tmp_path):
    path = write_jsonl(tmp_path / "po.jsonl", make_po_records()[:1])
    frame, evidence = po_open_from_purchase_jsonl(path)
    assert frame.iloc[0]["identity_status"] == "not_checked"
    assert pd.isna(frame.iloc[0]["product_id"])
    assert evidence["identity"] == "not_checked"


def test_po_missing_file_returns_empty_frame(tmp_path):
    frame, evidence = po_open_from_purchase_jsonl(tmp_path / "missing.jsonl")
    assert frame.empty
    assert evidence["exists"] is False
