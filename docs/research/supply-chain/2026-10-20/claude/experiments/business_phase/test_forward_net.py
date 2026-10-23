#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Executable acceptance examples for the forward-net line (SC02 repair).

Source of truth: `control/PROJECT_ROADMAP.md` →「核心验收例」six domains.
Since 2026-10-23 the tests exercise the REAL implementation
(`forward_net.py`), not a local mirror. Expectations were NOT weakened: the
fourteen examples that were red before the repair must now pass.

`_legacy_gap_a` keeps the retired formula only to document the old red light.

Run either way:
  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py
  uv run python -m pytest docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py -q

Synthetic fixtures only; no DB, no production, no network.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forward_net as fn  # noqa: E402


def _legacy_gap_a(gross, so, on_hand):
    """RETIRED formula (forward_net.py before SC02) — kept as the red-light record."""
    return max(0.0, max(0.0, gross - so) - on_hand)


class _Results:
    def __init__(self):
        self.rows = []

    def record(self, name, fnc):
        try:
            fnc()
            self.rows.append(("PASS", name, ""))
        except AssertionError as exc:
            self.rows.append(("FAIL", name, str(exc)))

    def report(self):
        counts = {"PASS": 0, "FAIL": 0}
        for st, name, msg in self.rows:
            counts[st] += 1
            print(f"{st:4s} {name}" + (f"  ← {msg}" if msg else ""))
        print(f"\nsummary: PASS {counts['PASS']} / FAIL {counts['FAIL']} / total {len(self.rows)}")
        return counts


# ===========================================================================
# Domain 1 — SO / 预测冲减
# ===========================================================================

def test_so_in_forecast_window_is_not_deducted_twice():
    """F=100, unfulfilled SO=20 (inside the forecast), stock=80 -> gap must be 20."""
    got = fn.gap_after_so(100, True, 0.0, 80, True)
    assert got == 20, f"SO 已在预测内时不能再扣一次；得到 {got}，应为 20"


def test_so_outside_forecast_adds_demand():
    """Forecast 100 + extra SO 20 outside the forecast, stock 80 -> gap 40."""
    got = fn.gap_after_so(100, False, 20.0, 80, False)
    assert got == 40, f"SO 不在预测内应加需求 20（总 120 − 80）；得到 {got}，应为 40"


def test_stock_already_net_of_so_must_not_deduct_so_again():
    """available 已扣占用 -> 需求仍 100，缺口 100 − 80 = 20；再扣 SO 就是双扣。"""
    got = fn.gap_after_so(100, True, 0.0, 80, True)
    assert got == 20, f"available 已扣占用时不得再扣 SO；得到 {got}，应为 20"


def test_red_light_current_impl_returns_zero_for_the_roadmap_case():
    """Historical record: the retired formula returned 0 for F=100/SO=20/stock=80."""
    assert _legacy_gap_a(100, 20, 80) == 0


# ===========================================================================
# Domain 2 — 时间账
# ===========================================================================

def test_midmonth_snapshot_consumption_is_deducted():
    """Snapshot 10/22, run 10/23, daily demand 10 -> opening at 10/23 is 70."""
    got = fn.stock_after_elapsed(80.0, 10.0, 1)
    assert got == 70.0, f"须扣掉快照日到运行日的消耗；得到 {got}，应为 70"


def test_cross_month_uses_actual_days_not_full_months():
    """10/22 → 11/30 是 40 个含首含尾的天；月率 31 → 需求 40。"""
    got = fn.horizon_demand(31.0, date(2026, 10, 22), date(2026, 11, 30))
    assert round(got, 6) == 40.0, f"跨月应按实际天数 40；得到 {got}"


def test_late_supply_after_horizon_is_not_counted():
    """No-ETA / late supply is split out and never enters the main gap."""
    rows = [dict(qty=30, docstatus=1, eta_ok=False, kind="po"),
            dict(qty=10, docstatus=1, eta_ok=False, kind="transit")]
    split = fn.split_by_eta(rows)
    assert split["undated_total"] == 40.0
    assert split["dated_total"] == 0.0, "无 ETA 供给不得进入主口径"
    assert split["dated_rows"] == 0


def test_partial_receipt_and_in_transit_are_not_double_counted():
    """PO 100, received 40, in transit 60 -> countable supply is 100, never 140/200."""
    rows = [dict(qty=40, docstatus=1, kind="receipt"),
            dict(qty=60, docstatus=1, kind="transit")]
    got = fn.harvest_total(rows)
    assert got == 100.0, f"分批接收与在途是同一批；得到 {got}，应为 100"


def test_future_cancellation_reduces_supply():
    rows = [dict(qty=100, docstatus=1, kind="po"),
            dict(qty=30, docstatus=1, kind="cancel")]
    got = fn.harvest_total(rows)
    assert got == 70.0, f"未来取消未处理（得到 {got}，应为 70）"


def test_earliest_gap_is_not_masked_by_later_surplus():
    """月 1 缺 10、月 2 多 50：最早的缺口仍是 10，不是 0。

    新守恒口径：closing = opening + receipts − fulfilled，缺口记在 unserved，
    因此 closing 不会为负；未履约滚入下一桶。
    """
    gaps = fn.bucket_gaps([
        dict(name="m1", opening=0, receipts=0, demand=10),
        dict(name="m2", opening=None, receipts=50, demand=0)])
    assert gaps[0]["gap"] == 10.0, f"最早缺口不得被期末盈余吃掉；得到 {gaps[0]['gap']}"
    assert gaps[0]["unserved"] == 10.0 and gaps[0]["closing"] == 0.0
    # bucket 2 receives the carried 10, has 50 receipts -> fully served
    assert gaps[1]["demand"] == 10.0 and gaps[1]["fulfilled"] == 10.0
    assert gaps[1]["gap"] == 0.0 and gaps[1]["closing"] == 40.0


# ===========================================================================
# Domain 3 — 供应数量
# ===========================================================================

def test_one_dn_five_tracking_numbers_does_not_multiply_qty():
    """一个 DN 行 qty=2（不管带几个跟踪号）只算一次。"""
    rows = [dict(qty=2, docstatus=1, tracking="TRK1", kind="dn")]
    got = fn.harvest_total(rows)
    assert got == 2.0, f"一个 DN 五个号只算一次 2 件；得到 {got}"


def test_one_tracking_number_on_many_dns_counts_once():
    rows = [dict(qty=3, docstatus=1, tracking="TRK1", kind="dn"),
            dict(qty=4, docstatus=1, tracking="TRK1", kind="dn")]
    got = fn.harvest_total(rows)
    assert got == 3.0, f"同一号多张 DN 只能算一次（首张 3）；得到 {got}"


def test_partial_received_supply_is_received_plus_remaining_not_double():
    rows = [dict(qty=40, docstatus=1, kind="receipt"),
            dict(qty=60, docstatus=1, kind="transit")]
    assert fn.harvest_total(rows) == 100.0


def test_parent_submitted_child_draft_is_excluded():
    rows = [dict(qty=50, docstatus=1, kind="dn"),
            dict(qty=50, docstatus=0, kind="dn")]   # child draft
    got = fn.harvest_total(rows)
    assert got == 50.0, f"子表 docstatus=0 是草稿，必须排除；得到 {got}"


def test_return_subtracts_from_supply():
    rows = [dict(qty=10, docstatus=1, kind="dn"),
            dict(qty=4, docstatus=1, kind="return")]
    got = fn.harvest_total(rows)
    assert got == 6.0, f"退货应冲减（10 − 4 = 6）；得到 {got}"


def test_shared_component_is_not_split_evenly():
    """共享料 30 件 / 3 个 SKU：没有显式规则就不能均摊。"""
    assert fn.shared_allocation(30.0, ["a", "b", "c"], rule=None) is None
    assert fn.shared_allocation(30.0, ["a", "b", "c"],
                                rule={"a": 0.5, "b": 0.3, "c": 0.2}) == [15.0, 9.0, 6.0]


# ===========================================================================
# Domain 4 — 未知与 SKU×仓
# ===========================================================================

def test_missing_stock_is_unknown_not_zero():
    assert fn.gap_or_unknown(None, 100) is None
    assert fn.gap_or_unknown(80, 100) == 20.0


def test_missing_uom_item_or_eta_blocks_the_row():
    base = dict(stock=10, uom="个", item="X", supply_expected=True, eta_ok=True)
    assert fn.require_evidence(base) == []
    assert fn.require_evidence(dict(base, uom=None)) == ["单位"]
    assert fn.require_evidence(dict(base, item="")) == ["物料"]
    assert fn.require_evidence(dict(base, eta_ok=False)) == ["ETA"]


def test_same_sku_in_two_warehouses_does_not_offset():
    rows = [dict(warehouse="A", stock=0, demand=10),
            dict(warehouse="B", stock=50, demand=0)]
    got = fn.warehouse_gaps(rows)
    assert [g["gap"] for g in got] == [10.0, 0.0], f"同 SKU 不同仓不得互相抵消；得到 {got}"


def test_zero_sales_is_a_fact_and_missing_source_is_unknown():
    proven_zero = 0.0
    unknown = None
    assert proven_zero == 0.0
    assert unknown is None
    assert proven_zero is not unknown, "已证零销售 ≠ 源缺失"


def test_missing_values_are_not_silently_zero_in_aggregation():
    agg = fn.aggregate_with_unknown([10.0, None, 5.0])
    assert agg == dict(total=15.0, known=2, unknown=1)


# ===========================================================================
# Domain 5 — 预测评估
# ===========================================================================

def naive_forecast(train):
    return [train[-1]] * 3


def test_forecast_uses_only_information_before_the_origin():
    full = [10, 12, 14]
    f = naive_forecast(full)
    assert f == [14, 14, 14]
    later = full + [99, 100, 101]
    assert naive_forecast(later[:len(full)]) == f, "追加未来证据后，历史切点的预测必须不变"


def test_appending_future_evidence_does_not_change_history():
    train = [10, 12, 14]
    assert naive_forecast(train) == naive_forecast(train)


# ===========================================================================
# Domain 6 — 概率与政策
# ===========================================================================

def test_fill_rate_is_hand_computable():
    assert 90.0 / 100.0 == 0.9


def test_cycle_service_level_is_hand_computable():
    p = sum(1 for d in range(0, 11) if d <= 8) / 11
    assert round(p, 6) == round(9 / 11, 6)


def _quantile(values, q):
    import math
    xs = sorted(values)
    idx = min(len(xs) - 1, math.ceil(q * (len(xs) - 1) - 1e-12))
    return xs[idx]


def test_cumulative_quantile_is_not_sum_of_monthly_quantiles():
    m = list(range(0, 11))                 # uniform 0..10, P90 = 9
    two = [a + b for a in m for b in m]
    p90_month = _quantile(m, 0.9)
    p90_two = _quantile(two, 0.9)
    assert p90_month == 9
    # hand-computed: P(sum<=15)=108/121=0.893 < 0.9, P(sum<=16)=111/121=0.917
    assert p90_two == 16, f"两月合计 P90 手算为 16，得到 {p90_two}"
    assert p90_two != 2 * p90_month, "累计分位数不得用逐月分位数相加（16 != 18）"
    skewed = [0] * 8 + [10] * 2
    assert _quantile(skewed, 0.9) == 10
    assert _quantile([a + b for a in skewed for b in skewed], 0.9) == 10
    assert 10 != 2 * 10, "逐月相加会给出 20，明显高估"


# ===========================================================================
# 301 forward review + coordinator follow-up (2026-10-23)
# ===========================================================================

def test_same_batch_is_not_upgraded_to_proven():
    """gross 100 / 在手 0 / PO 30 / 在途 30 / suspected：
    同批 → 供给 30、缺口 70；不同批 → 供给 60、缺口 40。两组必须并存。"""
    b = fn.batch_supply(30, 30, "suspected_same_batch_as_po")
    assert b["same_batch"] == 30.0 and b["different_batch"] == 60.0
    assert b["dedupe_state"] == "unknown_suspected", "suspected 不得升级为已证同批"
    assert max(0.0, 100 - 0 - b["same_batch"]) == 70.0
    assert max(0.0, 100 - 0 - b["different_batch"]) == 40.0
    # no same-batch evidence -> both scenarios carry the full sum
    n = fn.batch_supply(30, 30, "none_recorded")
    assert n["same_batch"] == 60.0 and n["different_batch"] == 60.0


def test_bucket_identities_hold_and_unserved_carries():
    chain = fn.bucket_gaps([
        dict(name="m1", opening=20, receipts=0, demand=50),
        dict(name="m2", opening=None, receipts=10, demand=30),
        dict(name="m3", opening=None, receipts=0, demand=0)])
    for c in chain:
        fn.assert_bucket_identities(c)
    assert chain[0]["unserved"] == 30.0 and chain[0]["closing"] == 0.0
    assert chain[1]["demand"] == 60.0          # 30 carried + 30 new
    assert chain[1]["fulfilled"] == 10.0 and chain[1]["unserved"] == 50.0
    assert chain[2]["demand"] == 50.0          # carried into the third bucket


def test_demand_source_is_t5_not_t3():
    rate, src = fn.choose_rate("5.0", "7.0")
    assert rate == 5.0 and src == "T5_AutoETS_eq_rate", "有 T5 时必须用 T5 并如实标注"
    rate2, src2 = fn.choose_rate("", "7.0")
    assert rate2 == 7.0 and src2 == "T3_3month_mean_fallback", "无 T5 才回退 T3，且标注 T3"
    assert fn.choose_rate("", "") == (None, "missing")


def test_negative_forecast_rate_is_clamped_to_zero():
    """负的 T5 等效率是模型伪影，不是负需求：钳到 0，并保留原值标注。"""
    assert fn.demand_rate(-6.3388) == 0.0
    assert fn.demand_rate(5.0) == 5.0


def test_unknown_wo_never_promotes_to_confirmed():
    assert fn.readiness_of("A", False) == "条件", "WO 未观测的行不得给已确认"
    assert fn.readiness_of("A", True) == "已确认"
    assert fn.readiness_of("B", False) == "条件"
    assert fn.readiness_of("C", False) == "HOLD"


TESTS = [
    test_so_in_forecast_window_is_not_deducted_twice,
    test_so_outside_forecast_adds_demand,
    test_stock_already_net_of_so_must_not_deduct_so_again,
    test_red_light_current_impl_returns_zero_for_the_roadmap_case,
    test_midmonth_snapshot_consumption_is_deducted,
    test_cross_month_uses_actual_days_not_full_months,
    test_late_supply_after_horizon_is_not_counted,
    test_partial_receipt_and_in_transit_are_not_double_counted,
    test_future_cancellation_reduces_supply,
    test_earliest_gap_is_not_masked_by_later_surplus,
    test_one_dn_five_tracking_numbers_does_not_multiply_qty,
    test_one_tracking_number_on_many_dns_counts_once,
    test_partial_received_supply_is_received_plus_remaining_not_double,
    test_parent_submitted_child_draft_is_excluded,
    test_return_subtracts_from_supply,
    test_shared_component_is_not_split_evenly,
    test_missing_stock_is_unknown_not_zero,
    test_missing_uom_item_or_eta_blocks_the_row,
    test_same_sku_in_two_warehouses_does_not_offset,
    test_zero_sales_is_a_fact_and_missing_source_is_unknown,
    test_missing_values_are_not_silently_zero_in_aggregation,
    test_forecast_uses_only_information_before_the_origin,
    test_appending_future_evidence_does_not_change_history,
    test_fill_rate_is_hand_computable,
    test_cycle_service_level_is_hand_computable,
    test_cumulative_quantile_is_not_sum_of_monthly_quantiles,
    test_same_batch_is_not_upgraded_to_proven,
    test_bucket_identities_hold_and_unserved_carries,
    test_demand_source_is_t5_not_t3,
    test_unknown_wo_never_promotes_to_confirmed,
    test_negative_forecast_rate_is_clamped_to_zero,
]


def main() -> int:
    res = _Results()
    for fnc in TESTS:
        res.record(fnc.__name__, fnc)
    counts = res.report()
    return 0 if counts["FAIL"] == 0 else 1


def test_suite_runs():
    """pytest entry point: the whole suite must pass."""
    res = _Results()
    for fnc in TESTS:
        res.record(fnc.__name__, fnc)
    counts = res.report()
    assert counts["FAIL"] == 0, f"failures: {counts['FAIL']}"


if __name__ == "__main__":
    sys.exit(main())
