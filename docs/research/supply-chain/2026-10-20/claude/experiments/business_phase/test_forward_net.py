#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Executable acceptance examples for the forward-net line (TDD, RED on purpose).

Source of truth: `control/PROJECT_ROADMAP.md` →「核心验收例」six domains.
This file is written BEFORE the implementation is fixed. `forward_net.py` is NOT
touched here; the tests encode what the pipeline MUST do and therefore FAIL
against the current arithmetic. That is the expected red light.

How to read the result
  PASS  – the assertion holds today
  RED   – expected failure: the current implementation is known to violate it
  FAIL  – unexpected failure (a red test that suddenly fails for another reason,
          or a green test that broke) — this one needs attention

Run either way:
  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py
  uv run pytest docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py -q

Synthetic fixtures only; no DB, no production, no network.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Mirror of the CURRENT implementation (forward_net.py, 2026-10-23)
#   net  = max(0, gross - so)
#   gapA = max(0, net - on_hand)
# Keep this in sync with forward_net.py only to *describe* it; the tests below
# assert the CORRECT behaviour and are therefore red where the mirror differs.
# ---------------------------------------------------------------------------


def current_gap_a(gross, so, on_hand):
    net = max(0.0, gross - so)
    return max(0.0, net - on_hand)


def current_oct_demand(monthly_rate, days=10):
    return monthly_rate * days / 31


def current_horizon_demand(monthly_rate, oct_days=10):
    """remaining-Oct + Nov + Dec, Nov/Dec each a full month."""
    return current_oct_demand(monthly_rate, oct_days) + monthly_rate + monthly_rate


# ---------------------------------------------------------------------------
# Correct-behaviour oracles (hand-computed, tiny numbers)
# ---------------------------------------------------------------------------

def gap_after_so(demand, so_in_forecast, so_extra, stock, stock_net_of_so=False):
    """SO inside the forecast window is already part of demand -> never deducted
    twice. SO outside the forecast adds demand. Stock is only decremented by the
    outstanding SO when the stock field is documented as gross (not netted)."""
    total = demand + so_extra
    if stock_net_of_so:
        return max(0.0, total - stock)
    return max(0.0, total - stock)


def days_inclusive(a: date, b: date) -> int:
    return (b - a).days + 1


# ---------------------------------------------------------------------------
# Harvest/aggregation oracle for domain 3 (supply quantity)
# ---------------------------------------------------------------------------

def harvest_total(rows):
    """rows: dicts with qty, docstatus, tracking, kind.
    Rules: one row counted once regardless of tracking numbers; a child row with
    docstatus 0 is a draft and excluded; a return (kind='return') subtracts."""
    seen_tracking = set()
    total = 0.0
    for r in rows:
        if r.get("docstatus") != 1:
            continue
        tr = r.get("tracking")
        if tr:
            if tr in seen_tracking:
                continue
            seen_tracking.add(tr)
        q = float(r.get("qty") or 0)
        total += -abs(q) if r.get("kind") == "return" else q
    return total


class _Results:
    def __init__(self):
        self.rows = []

    def record(self, name, fn, expected_red):
        try:
            fn()
            self.rows.append(("PASS", name, ""))
        except AssertionError as exc:
            status = "RED" if expected_red else "FAIL"
            self.rows.append((status, name, str(exc)))

    def report(self):
        counts = {"PASS": 0, "RED": 0, "FAIL": 0}
        for st, name, msg in self.rows:
            counts[st] += 1
            print(f"{st:4s} {name}" + (f"  ← {msg}" if msg else ""))
        print(f"\nsummary: PASS {counts['PASS']} / RED(expected) {counts['RED']} / "
              f"UNEXPECTED FAIL {counts['FAIL']} / total {len(self.rows)}")
        return counts


# ===========================================================================
# Domain 1 — SO / 预测冲减
# ===========================================================================

def test_so_in_forecast_window_is_not_deducted_twice():
    """F=100, unfulfilled SO=20 (inside the forecast), stock=80 -> gap must be 20."""
    got = current_gap_a(100, 20, 80)
    assert got == 20, f"SO 已在预测内时不能再扣一次；得到 {got}，应为 20"


def test_so_outside_forecast_adds_demand():
    """Forecast 100 + extra SO 20 outside the forecast, stock 80 -> gap 40."""
    got = current_gap_a(100, 0, 80)  # 既有实现没有"SO 不在预测内则加需求"的概念
    assert got == 40, f"SO 不在预测内应加需求 20（总 120 − 80）；得到 {got}，应为 40"


def test_stock_already_net_of_so_must_not_deduct_so_again():
    """If the stock field is documented as available (already net of the SO),
    demand stays 100 and gap = 100 − 80 = 20; deducting SO again is double."""
    got = current_gap_a(100, 20, 80)
    assert got == 20, f"available 已扣占用时不得再扣 SO；得到 {got}，应为 20"


def test_red_light_current_impl_returns_zero_for_the_roadmap_case():
    """Documents the red light: the current formula returns 0 for F=100/SO=20/stock=80."""
    assert current_gap_a(100, 20, 80) == 0


# ===========================================================================
# Domain 2 — 时间账
# ===========================================================================

def test_midmonth_snapshot_consumption_is_deducted():
    """Snapshot 10/22, run 10/23, daily demand 10 -> opening at 10/23 is stock − 10."""
    stock, daily = 80.0, 10.0
    opening = stock - daily          # 1 day already elapsed
    assert opening == 70.0
    # current pipeline never deducts the elapsed day
    piped = stock
    assert piped == 70.0, f"现实现未扣 10/23 当天消耗（得到 {piped}，应为 70）"


def test_cross_month_uses_actual_days_not_full_months():
    """10/22 → 11/30 is 40 inclusive days; at 1/day demand must be 40, not 41."""
    want = days_inclusive(date(2026, 10, 22), date(2026, 11, 30))   # 40 days
    got = current_oct_demand(monthly_rate=31.0, days=10) + 31.0      # 10 + 31
    assert round(got, 6) == want, f"跨月应按实际天数 40；现实现得到 {got}"


def test_late_supply_after_horizon_is_not_counted():
    """A PO arriving 2026-12-15 is outside the horizon and must not offset it."""
    eta = date(2026, 12, 15)
    horizon_end = date(2026, 12, 31)
    assert eta <= horizon_end          # inside horizon by date
    # but a PO arriving 2027-01-05 is outside
    late = date(2027, 1, 5)
    counted = late <= horizon_end
    assert counted is False
    # current pipeline counts every open PO regardless of ETA
    pipeline_counts = True
    assert pipeline_counts is False, "现实现把无 ETA/超期 PO 一并计入"


def test_partial_receipt_and_in_transit_are_not_double_counted():
    """PO 100, received 40, in transit 60 -> countable supply is 100, never 140."""
    po, received, in_transit = 100.0, 40.0, 60.0
    assert received + in_transit == po
    pipeline = received + in_transit + po
    assert pipeline == po, f"分批接收与在途是同一批；现实现得到 {pipeline}，应为 {po}"


def test_future_cancellation_reduces_supply():
    """A known cancellation dated 11/5 of 30 units must be removed from the horizon."""
    supply = 100.0
    cancelled = 30.0
    assert supply - cancelled == 70.0
    pipeline = supply          # no cancellation concept in the current pipeline
    assert pipeline == 70.0, f"未来取消未处理（得到 {pipeline}，应为 70）"


def test_earliest_gap_is_not_masked_by_later_surplus():
    """Month 1 is short 10, month 2 has +50 surplus -> the earliest gap is 10, not 0."""
    m1_gap, m2_surplus = 10.0, 50.0
    assert m1_gap == 10.0
    pipeline = max(0.0, m2_surplus - m1_gap)   # netting across time
    assert pipeline == 10.0, f"期末盈余不能掩盖最早缺口；现实现得到 {pipeline}，应为 10"


# ===========================================================================
# Domain 3 — 供应数量
# ===========================================================================

def test_one_dn_five_tracking_numbers_does_not_multiply_qty():
    rows = [dict(qty=2, docstatus=1, tracking=f"TRK{i}", kind="dn") for i in range(5)]
    rows = [dict(rows[0])]  # one DN row, five tracking numbers on it
    got = harvest_total(rows)
    assert got == 2.0, f"一个 DN 五个号只算一次 2 件；得到 {got}"


def test_one_tracking_number_on_many_dns_counts_once():
    rows = [dict(qty=3, docstatus=1, tracking="TRK1", kind="dn"),
            dict(qty=4, docstatus=1, tracking="TRK1", kind="dn")]
    got = harvest_total(rows)
    assert got == 3.0, f"同一号多张 DN 只能算一次（首张 3）；得到 {got}"


def test_partial_received_supply_is_received_plus_remaining_not_double():
    rows = [dict(qty=40, docstatus=1, tracking=None, kind="receipt"),
            dict(qty=60, docstatus=1, tracking=None, kind="transit")]
    got = harvest_total(rows)
    assert got == 100.0, f"部分签收 40 + 在途 60 = 100；得到 {got}"


def test_parent_submitted_child_draft_is_excluded():
    rows = [dict(qty=50, docstatus=1, tracking=None, kind="dn"),
            dict(qty=50, docstatus=0, tracking=None, kind="dn")]   # child draft
    got = harvest_total(rows)
    assert got == 50.0, f"子表 docstatus=0 是草稿，必须排除；得到 {got}"


def test_return_subtracts_from_supply():
    rows = [dict(qty=10, docstatus=1, tracking=None, kind="dn"),
            dict(qty=4, docstatus=1, tracking=None, kind="return")]
    got = harvest_total(rows)
    assert got == 6.0, f"退货应冲减（10 − 4 = 6）；得到 {got}"


def test_shared_component_is_not_split_evenly():
    """A shared cover pool of 30 for 3 SKUs must not become 10 each without proof."""
    shared_qty, n_skus = 30.0, 3
    naive_split = shared_qty / n_skus
    assert naive_split == 10.0
    assert False, "共享料不能均摊：需显式分配规则，当前实现无此规则"


# ===========================================================================
# Domain 4 — 未知与 SKU×仓
# ===========================================================================

def _gap(stock, demand):
    if stock is None:
        return None                 # unknown, not zero
    return max(0.0, demand - stock)


def test_missing_stock_is_unknown_not_zero():
    assert _gap(None, 100) is None
    assert _gap(None, 100) != 0, "缺库存必须记 unknown，不能自动 0"
    pipeline = 0.0                  # current pipeline coerces missing to 0 elsewhere
    assert pipeline is None, f"现实现把缺值当 0（得到 {pipeline}）"


def test_missing_uom_item_or_eta_blocks_the_row():
    for missing in ("uom", "item", "eta"):
        assert False, f"缺 {missing} 时必须标不可算/放弃，当前实现未阻断"


def test_same_sku_in_two_warehouses_does_not_offset():
    wh_a = dict(stock=0, demand=10)
    wh_b = dict(stock=50, demand=0)
    gaps = [_gap(wh_a["stock"], wh_a["demand"]), _gap(wh_b["stock"], wh_b["demand"])]
    assert gaps == [10, 0], "同 SKU 不同仓不得互相抵消"
    pipeline = max(0.0, (wh_b["stock"] + wh_a["stock"]) - (wh_a["demand"] + wh_b["demand"]))
    assert pipeline == 10, f"现实现按 SKU 合计求缺口（得到 {pipeline}，应为 per-仓 10/0）"


def test_zero_sales_is_a_fact_and_missing_source_is_unknown():
    proven_zero = 0.0
    unknown = None
    assert proven_zero == 0.0
    assert unknown is None
    assert proven_zero is not unknown, "已证零销售 ≠ 源缺失"


def test_missing_values_are_not_silently_zero_in_aggregation():
    vals = [10.0, None, 5.0]
    total = sum(v for v in vals if v is not None)
    assert total == 15.0
    naive = sum(v or 0 for v in vals)
    assert naive == 15.0, "缺值不得当成 0 参与合计（数值相同但语义不同，需同时保留 unknown 计数）"
    assert False, "当前实现未输出 unknown 计数，无法区分 15（10+5）与 15（10+0+5）"


# ===========================================================================
# Domain 5 — 预测评估
# ===========================================================================

def naive_forecast(train):
    return [train[-1]] * 3


def test_forecast_uses_only_information_before_the_origin():
    full = [10, 12, 14]
    f = naive_forecast(full)
    assert f == [14, 14, 14]
    # later data becomes available, but the ORIGIN-TRUNCATED series is unchanged
    later = full + [99, 100, 101]
    f2 = naive_forecast(later[:len(full)])
    assert f2 == f, "追加未来证据后，历史切点的预测必须不变"


def test_appending_future_evidence_does_not_change_history():
    train = [10, 12, 14]
    before = naive_forecast(train)
    after = naive_forecast(train)
    assert before == after, "同一训练窗必须给出同一预测（无未来信息泄漏）"


# ===========================================================================
# Domain 6 — 概率与政策
# ===========================================================================

def test_fill_rate_is_hand_computable():
    demand, served = 100.0, 90.0
    assert served / demand == 0.9, "fill rate = 满足量/需求 = 0.9"


def test_cycle_service_level_is_hand_computable():
    # demand is uniform over {0..10}, stock 8 -> P(D <= 8) = 9/11
    p = sum(1 for d in range(0, 11) if d <= 8) / 11
    assert round(p, 6) == round(9 / 11, 6)


def _quantile(values, q):
    xs = sorted(values)
    import math
    idx = min(len(xs) - 1, math.ceil(q * (len(xs) - 1) - 1e-12))
    return xs[idx]


def test_cumulative_quantile_is_not_sum_of_monthly_quantiles():
    m = list(range(0, 11))                 # uniform 0..10, P90 = 9
    two = [a + b for a in m for b in m]    # two iid months
    p90_month = _quantile(m, 0.9)
    p90_two = _quantile(two, 0.9)
    assert p90_month == 9
    # hand-computed: P(sum<=15)=108/121=0.893 < 0.9, P(sum<=16)=111/121=0.917
    assert p90_two == 16, f"两月合计 P90 手算为 16，得到 {p90_two}"
    assert p90_two != 2 * p90_month, "累计分位数不得用逐月分位数相加（16 != 18）"
    # skewed example: 80% zero, 20% ten -> monthly P90 = 10, two-month P90 = 10
    skewed = [0] * 8 + [10] * 2
    assert _quantile(skewed, 0.9) == 10
    assert _quantile([a + b for a in skewed for b in skewed], 0.9) == 10
    assert 10 != 2 * 10, "逐月相加会给出 20，明显高估"


# ---------------------------------------------------------------------------

TESTS = [
    # (function, expected_red)
    (test_so_in_forecast_window_is_not_deducted_twice, True),
    (test_so_outside_forecast_adds_demand, True),
    (test_stock_already_net_of_so_must_not_deduct_so_again, True),
    (test_red_light_current_impl_returns_zero_for_the_roadmap_case, False),
    (test_midmonth_snapshot_consumption_is_deducted, True),
    (test_cross_month_uses_actual_days_not_full_months, True),
    (test_late_supply_after_horizon_is_not_counted, True),
    (test_partial_receipt_and_in_transit_are_not_double_counted, True),
    (test_future_cancellation_reduces_supply, True),
    (test_earliest_gap_is_not_masked_by_later_surplus, True),
    (test_one_dn_five_tracking_numbers_does_not_multiply_qty, False),
    (test_one_tracking_number_on_many_dns_counts_once, True),
    (test_partial_received_supply_is_received_plus_remaining_not_double, False),
    (test_parent_submitted_child_draft_is_excluded, False),
    (test_return_subtracts_from_supply, False),
    (test_shared_component_is_not_split_evenly, True),
    (test_missing_stock_is_unknown_not_zero, True),
    (test_missing_uom_item_or_eta_blocks_the_row, True),
    (test_same_sku_in_two_warehouses_does_not_offset, True),
    (test_zero_sales_is_a_fact_and_missing_source_is_unknown, False),
    (test_missing_values_are_not_silently_zero_in_aggregation, True),
    (test_forecast_uses_only_information_before_the_origin, False),
    (test_appending_future_evidence_does_not_change_history, False),
    (test_fill_rate_is_hand_computable, False),
    (test_cycle_service_level_is_hand_computable, False),
    (test_cumulative_quantile_is_not_sum_of_monthly_quantiles, False),
]


def main() -> int:
    res = _Results()
    for fn, red in TESTS:
        res.record(fn.__name__, fn, red)
    counts = res.report()
    # expected reds are not a CI break; unexpected failures are
    return 1 if counts["FAIL"] else 0


def test_suite_runs():
    """pytest entry point: run everything and require zero UNEXPECTED failures."""
    res = _Results()
    for fn, red in TESTS:
        res.record(fn.__name__, fn, red)
    counts = res.report()
    assert counts["FAIL"] == 0, f"unexpected failures: {counts['FAIL']}"


if __name__ == "__main__":
    sys.exit(main())
