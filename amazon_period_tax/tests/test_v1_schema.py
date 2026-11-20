# -*- coding: utf-8 -*-
"""V1 结算表（price-type/price-amount 族）→ V2 长表规范化。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from read_amz_txt import _normalize_v1_schema, expected_parsed_rows, read_amz_txt_file

V1_COLS = (
    "settlement-id",
    "currency",
    "transaction-type",
    "sku",
    "shipment-fee-type",
    "shipment-fee-amount",
    "order-fee-type",
    "order-fee-amount",
    "price-type",
    "price-amount",
    "item-related-fee-type",
    "item-related-fee-amount",
    "misc-fee-amount",
    "other-fee-amount",
    "other-fee-reason-description",
    "promotion-type",
    "promotion-amount",
    "direct-payment-type",
    "direct-payment-amount",
    "other-amount",
)
V1_HEADER = "\t".join(V1_COLS)


def _v1_text(*rows: dict) -> str:
    """按列名构造 V1 txt：``{"price-type": "Tax", "price-amount": 8}``。"""
    lines = [V1_HEADER]
    for row in rows:
        lines.append("\t".join("" if row.get(c) is None else str(row.get(c)) for c in V1_COLS))
    return "\n".join(lines) + "\n"

V2_HEADER = (
    "settlement-id\tcurrency\tamount-type\tamount-description\tamount\ttransaction-type\tsku"
)


def _v1_df() -> pd.DataFrame:
    """一行汇总（只有 currency/settlement-id）+ 两行明细，模拟真实 V1 导出。"""
    return pd.DataFrame(
        {
            "settlement-id": ["S1", None, None],
            "currency": ["USD", None, None],
            "transaction-type": ["TransactionTotalAmount", "Order", "Order"],
            "sku": [None, "SKU1", "SKU2"],
            "shipment-fee-type": [None, None, None],
            "shipment-fee-amount": [None, None, None],
            "order-fee-type": [None, None, None],
            "order-fee-amount": [None, None, None],
            "price-type": [None, "Principal", "Tax"],
            "price-amount": [None, 100.0, 8.0],
            "item-related-fee-type": [None, "Commission", None],
            "item-related-fee-amount": [None, -15.0, None],
            "misc-fee-amount": [None, None, None],
            "other-fee-amount": [None, None, None],
            "other-fee-reason-description": [None, None, None],
            "promotion-type": [None, "Principal", None],
            "promotion-amount": [None, -5.0, None],
            "direct-payment-type": [None, None, None],
            "direct-payment-amount": [None, None, None],
            "other-amount": [None, None, None],
        }
    )


def test_v1_detected_and_expanded():
    out = _normalize_v1_schema(_v1_df())
    assert "amount-type" in out.columns
    # 汇总行没有金额族 → 被丢弃；SKU1 展开 price+fee+promotion 共 3 行，SKU2 展开 price 共 1 行
    assert len(out) == 4


def test_price_expansion_to_item_price():
    out = _normalize_v1_schema(_v1_df())
    prices = out[out["amount-type"] == "ItemPrice"]
    assert sorted(zip(prices["amount-description"], prices["amount"])) == [
        ("Principal", 100.0),
        ("Tax", 8.0),
    ]


def test_item_related_fee_expansion():
    out = _normalize_v1_schema(_v1_df())
    fees = out[(out["amount-type"] == "ItemFees") & (out["amount-description"] == "Commission")]
    assert len(fees) == 1
    assert fees["amount"].iloc[0] == -15.0


def test_shipment_and_order_fee_expansion():
    df = pd.DataFrame(
        {
            "settlement-id": ["S1"],
            "currency": ["USD"],
            "price-type": [None],
            "price-amount": [None],
            "shipment-fee-type": ["FBAPerUnitFulfillmentFee"],
            "shipment-fee-amount": [-2.5],
            "order-fee-type": ["ShippingChargeback"],
            "order-fee-amount": [-1.0],
        }
    )
    out = _normalize_v1_schema(df)
    got = set(zip(out["amount-type"], out["amount-description"], out["amount"]))
    assert got == {
        ("ItemFees", "FBAPerUnitFulfillmentFee", -2.5),
        ("ItemFees", "ShippingChargeback", -1.0),
    }


def test_promotion_expansion():
    out = _normalize_v1_schema(_v1_df())
    promo = out[out["amount-type"] == "Promotion"]
    assert len(promo) == 1
    assert promo["amount-description"].iloc[0] == "Principal"
    assert promo["amount"].iloc[0] == -5.0


def test_marketplace_facilitator_goes_to_withheld_tax_not_item_price():
    df = pd.DataFrame(
        {
            "settlement-id": ["S1"],
            "currency": ["USD"],
            "price-type": ["MarketplaceFacilitatorTax-Principal"],
            "price-amount": [-8.0],
        }
    )
    out = _normalize_v1_schema(df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["amount-type"] == "ItemWithheldTax"
    assert row["amount-description"] == "MarketplaceFacilitatorTax-Principal"
    assert (out["amount-type"] == "ItemPrice").sum() == 0


def test_blank_type_not_expanded():
    df = pd.DataFrame(
        {
            "settlement-id": ["S1"],
            "currency": ["USD"],
            "price-type": [None],
            "price-amount": [99.0],
            "item-related-fee-type": ["  "],
            "item-related-fee-amount": [50.0],
        }
    )
    out = _normalize_v1_schema(df)
    assert "amount-type" not in out.columns or out["amount-type"].isna().all()


def test_currency_and_settlement_id_forward_filled():
    out = _normalize_v1_schema(_v1_df())
    assert out["currency"].notna().all()
    assert out["settlement-id"].notna().all()
    assert set(out["currency"]) == {"USD"}
    assert set(out["settlement-id"]) == {"S1"}


def test_v2_left_untouched():
    df = pd.DataFrame(
        {
            "settlement-id": ["S1"],
            "currency": ["USD"],
            "amount-type": ["ItemPrice"],
            "amount-description": ["Tax"],
            "amount": [8.0],
        }
    )
    out = _normalize_v1_schema(df)
    pd.testing.assert_frame_equal(out, df)


def test_expected_parsed_rows_v1_counts_amount_cells():
    text = _v1_text(
        {"settlement-id": "S1", "currency": "USD", "transaction-type": "TransactionTotalAmount"},
        {
            "settlement-id": "S1",
            "transaction-type": "Order",
            "sku": "SKU1",
            "price-type": "Principal",
            "price-amount": 100,
            "item-related-fee-type": "Commission",
            "item-related-fee-amount": -15,
            "promotion-type": "Principal",
            "promotion-amount": -5,
        },
        {"settlement-id": "S1", "transaction-type": "Order", "sku": "SKU2", "price-type": "Tax", "price-amount": 8},
    )
    # 第 2 行 3 个非空金额（price+fee+promotion）+ 第 3 行 1 个 = 4
    assert expected_parsed_rows(text) == 4


def test_expected_parsed_rows_v1_requires_both_type_and_amount():
    text = _v1_text(
        {
            "settlement-id": "S1",
            "currency": "USD",
            "transaction-type": "Order",
            "sku": "SKU1",
            "price-type": "Principal",
            "item-related-fee-type": "Commission",
            "item-related-fee-amount": -15,
        }
    )
    # price-type 有但 price-amount 空 → 不计数；只有 Commission 一行
    assert expected_parsed_rows(text) == 1


def test_expected_parsed_rows_v2_is_line_count():
    text = V2_HEADER + "\nS1\tUSD\tItemPrice\tTax\t8\tOrder\tSKU1\n\nS1\tUSD\tItemFees\tCommission\t-15\tOrder\tSKU1\n"
    assert expected_parsed_rows(text) == 2


def test_expected_parsed_rows_empty_text():
    assert expected_parsed_rows("") == 0


def test_read_v1_file_end_to_end(tmp_path: Path):
    text = _v1_text(
        {"settlement-id": "S1", "currency": "USD", "transaction-type": "TransactionTotalAmount"},
        {
            "settlement-id": "S1",
            "transaction-type": "Order",
            "sku": "SKU1",
            "price-type": "Principal",
            "price-amount": 100,
            "item-related-fee-type": "Commission",
            "item-related-fee-amount": -15,
            "promotion-type": "Principal",
            "promotion-amount": -5,
        },
        {"settlement-id": "S1", "transaction-type": "Order", "sku": "SKU2", "price-type": "Tax", "price-amount": 8},
    )
    path = tmp_path / "AMZTestUS-2026-10-08.txt"
    path.write_text(text, encoding="utf-8")

    df = read_amz_txt_file(path)
    assert df is not None
    assert len(df) == 4
    # amount 已转 float，Tax 行为 8.0
    tax = df[df["amount-description"] == "Tax"]["amount"].iloc[0]
    assert float(tax) == 8.0
    assert df["currency"].notna().all()
    # 渠道账号列已按文件名补
    assert df["渠道账号"].iloc[0] == "AMZTestUS"
