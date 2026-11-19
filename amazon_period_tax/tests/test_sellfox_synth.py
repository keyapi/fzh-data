# -*- coding: utf-8 -*-
"""sellfox_synth_txt: 赛狐结算明细 → Amazon flat-file 的映射与税务口径。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "scripts" / "sellfox_synth_txt.py"
_spec = importlib.util.spec_from_file_location("sellfox_synth_txt", _MOD)
m = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(m)

GROUP = {
    "settlementId": "1",
    "marketplaceName": "美国",
    "groupStartStr": "2026/07/28 01:03:22",
    "groupEndStr": "2026/08/11 01:03:22",
    "siteFundTransferDateStr": "2026/08/11 22:46:28",
    "utcFundTransferDateStr": "2026/08/12 05:46:28",
    "transferAmount": 752.64,
    "currency": "USD",
}
ROWS = [
    {"settlementId": "1", "currency": "USD", "transactionType": "Order", "orderId": "o1",
     "amountType": "ItemPrice", "amountDescription": "Principal", "amount": "1000.00",
     "fulfillmentId": "FBA", "siteTimeStr": "2026-08-01 10:00:00",
     "postedDateTimeStr": "2026-08-02 01:00:00", "msku": "SKU1", "quantityPurchased": "1"},
    {"settlementId": "1", "currency": "USD", "transactionType": "Order", "orderId": "o1",
     "amountType": "ItemPrice", "amountDescription": "Tax", "amount": "50.00"},
    {"settlementId": "1", "currency": "USD", "transactionType": "Order", "orderId": "o1",
     "amountType": "ItemFees", "amountDescription": "Commission", "amount": "-150.00"},
]


def test_header_and_summary_row():
    lines = m.build_txt_lines("1", GROUP, ROWS)
    assert lines[0].split("\t") == m.COLS
    summary = lines[1].split("\t")
    assert summary[m.COLS.index("settlement-id")] == "1"
    assert summary[m.COLS.index("settlement-end-date")] == "2026-08-11 01:03:22"
    assert summary[m.COLS.index("deposit-date")] == "2026-08-12 05:46:28"
    assert summary[m.COLS.index("total-amount")] == "752.64"
    assert summary[m.COLS.index("currency")] == "USD"


def test_transaction_rows_mapping():
    lines = m.build_txt_lines("1", GROUP, ROWS)
    assert len(lines) == 1 + 1 + len(ROWS)
    first = lines[2].split("\t")
    assert first[m.COLS.index("amount-type")] == "ItemPrice"
    assert first[m.COLS.index("amount-description")] == "Principal"
    assert first[m.COLS.index("amount")] == "1000.00"
    assert first[m.COLS.index("sku")] == "SKU1"
    assert first[m.COLS.index("posted-date")] == "2026-08-01"


def test_tax_only_itemprice_promotion():
    assert m.tax_of(ROWS) == 50.0
    rows = ROWS + [{"amountType": "ItemFees", "amountDescription": "Tax", "amount": "999"}]
    assert m.tax_of(rows) == 50.0  # 非 ItemPrice/Promotion 的 Tax 不计入
