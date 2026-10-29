# -*- coding: utf-8 -*-
"""Contract tests for final logistics progress adjudication (pure)."""
import unittest

from key_test.shipment_progress import (
    SIGNED_PENDING_STAGE,
    TRANSPORT_STAGE,
    UNKNOWN_STAGE,
    ProgressEvidence,
    adjudicate_progress,
    classify_stage,
)


def ev(status, at=None, kind="actual", source="carrier", updated=None,
       record=None):
    return ProgressEvidence(
        raw_status=status, normalized_status=status, event_kind=kind,
        event_at=at, source_updated_at=updated, source=source,
        source_record=record or "%s@%s" % (source, status))


class TerminalStickinessTests(unittest.TestCase):
    def test_signed_yesterday_beats_manual_in_transit_today(self):
        result = adjudicate_progress([
            ev("已签收", "2026-10-28T10:00:00+08:00", source="carrier"),
            ev("运输中", "2026-10-29T10:00:00+08:00", source="manual"),
        ])
        self.assertEqual(result["latest_progress_status"], "已签收")
        self.assertEqual(result["latest_progress_at"], "2026-10-28T10:00:00+08:00")
        self.assertTrue(result["is_final"])
        self.assertTrue(result["conflict_flag"])
        self.assertIn("terminal_over_nonterminal", result["conflict_reasons"])
        self.assertEqual(len(result["progress_candidates"]), 2)

    def test_later_sailing_does_not_override_signed(self):
        result = adjudicate_progress([
            ev("已签收", "2026-10-28T10:00:00+08:00"),
            ev("已离港", "2026-10-29T10:00:00+08:00", source="manual"),
        ])
        self.assertEqual(result["latest_progress_status"], "已签收")
        self.assertTrue(result["is_final"])

    def test_two_terminals_pick_later_and_flag_status_conflict(self):
        result = adjudicate_progress([
            ev("已签收", "2026-10-28T10:00:00+08:00"),
            ev("已上传POD", "2026-10-29T10:00:00+08:00"),
        ])
        self.assertEqual(result["latest_progress_status"], "已上传POD")
        self.assertEqual(result["latest_progress_at"], "2026-10-29T10:00:00+08:00")
        self.assertTrue(result["is_final"])
        self.assertTrue(result["conflict_flag"])

    def test_same_time_different_terminal_is_unknown_conflict(self):
        result = adjudicate_progress([
            ev("已签收", "2026-10-29T10:00:00+08:00"),
            ev("已上传POD", "2026-10-29T10:00:00+08:00"),
        ])
        self.assertIsNone(result["latest_progress_status"])
        self.assertFalse(result["is_final"])
        self.assertTrue(result["conflict_flag"])


class ActualOverEstimatedTests(unittest.TestCase):
    def test_actual_arrival_beats_later_eta(self):
        result = adjudicate_progress([
            ev("已到港", "2026-10-20T08:00:00+08:00", kind="actual"),
            ev("ETA", "2026-10-30T08:00:00+08:00", kind="estimated"),
        ])
        self.assertEqual(result["latest_progress_status"], "已到港")
        self.assertEqual(result["latest_progress_at"], "2026-10-20T08:00:00+08:00")
        self.assertFalse(result["is_final"])

    def test_late_eta_does_not_move_actual_stage(self):
        result = adjudicate_progress([
            ev("派送中", "2026-10-20T08:00:00+08:00", kind="actual"),
            ev("ETA", "2026-12-31T08:00:00+08:00", kind="estimated",
               source="manual", updated="2026-10-29T09:00:00+08:00"),
        ])
        self.assertEqual(result["latest_progress_status"], "派送中")


class StageOrderTests(unittest.TestCase):
    def test_higher_stage_wins_even_if_earlier(self):
        result = adjudicate_progress([
            ev("派送中", "2026-10-20T08:00:00+08:00"),
            ev("已到港", "2026-10-25T08:00:00+08:00"),
        ])
        self.assertEqual(result["latest_progress_status"], "派送中")
        self.assertTrue(result["conflict_flag"])
        self.assertIn("stage_regression", result["conflict_reasons"])

    def test_same_stage_uses_later_actual_event(self):
        # 已到港 and 清关中 are different stages; same-stage example uses the
        # same normalized status at different times.
        result = adjudicate_progress([
            ev("运输中", "2026-10-20T08:00:00+08:00"),
            ev("运输中", "2026-10-25T08:00:00+08:00"),
        ])
        self.assertEqual(result["latest_progress_at"], "2026-10-25T08:00:00+08:00")
        self.assertFalse(result["conflict_flag"])

    def test_arrival_clearance_dispatch_remain_transport(self):
        for status in ("已到港", "清关中", "已清关", "已转运", "派送中"):
            result = adjudicate_progress([ev(status, "2026-10-20T08:00:00+08:00")])
            self.assertEqual(classify_stage(result), TRANSPORT_STAGE, status)

    def test_signed_enters_pending_receipt_stage(self):
        result = adjudicate_progress([ev("已签收", "2026-10-20T08:00:00+08:00")])
        self.assertEqual(classify_stage(result), SIGNED_PENDING_STAGE)

    def test_conflict_stage_is_unknown(self):
        result = adjudicate_progress([
            ev("已到港", "2026-10-20T10:00:00+08:00"),
            ev("清关中", "2026-10-20T10:00:00+08:00"),
        ])
        self.assertEqual(result["latest_progress_status"], None)
        self.assertEqual(classify_stage(result), UNKNOWN_STAGE)


class ExceptionAndMissingTimeTests(unittest.TestCase):
    def test_exception_without_terminal_is_unknown_conflict(self):
        result = adjudicate_progress([
            ev("已到港", "2026-10-20T08:00:00+08:00"),
            ev("异常", "2026-10-21T08:00:00+08:00", source="manual"),
        ])
        self.assertIsNone(result["latest_progress_status"])
        self.assertTrue(result["conflict_flag"])
        self.assertIn("exception_present", result["conflict_reasons"])

    def test_exception_does_not_override_terminal(self):
        result = adjudicate_progress([
            ev("已签收", "2026-10-20T08:00:00+08:00"),
            ev("撤销", None, source="manual"),
        ])
        self.assertEqual(result["latest_progress_status"], "已签收")
        self.assertTrue(result["is_final"])
        self.assertTrue(result["conflict_flag"])

    def test_one_missing_time_uses_stage_order_and_flags(self):
        result = adjudicate_progress([
            ev("已离港", "2026-10-20T08:00:00+08:00"),
            ev("运输中", None, source="manual"),
        ])
        self.assertEqual(result["latest_progress_status"], "运输中")
        self.assertTrue(result["conflict_flag"])
        self.assertIn("missing_time", result["conflict_reasons"])

    def test_both_missing_time_same_status_is_stable(self):
        result = adjudicate_progress([
            ev("运输中", None),
            ev("运输中", None, source="manual"),
        ])
        self.assertEqual(result["latest_progress_status"], "运输中")
        self.assertFalse(result["conflict_flag"])

    def test_both_missing_time_different_status_uses_stage_order(self):
        result = adjudicate_progress([
            ev("运输中", None),
            ev("已到港", None, source="manual"),
        ])
        self.assertEqual(result["latest_progress_status"], "已到港")
        self.assertTrue(result["conflict_flag"])
        self.assertIn("missing_time", result["conflict_reasons"])


class SourceRevisionTests(unittest.TestCase):
    def test_source_updated_at_cannot_promote_stage(self):
        stale = ev("已离港", "2026-10-20T08:00:00+08:00", source="carrier",
                   updated="2026-10-29T09:00:00+08:00")
        newer_event = ev("运输中", "2026-10-25T08:00:00+08:00", source="carrier",
                         updated="2026-10-25T09:00:00+08:00")
        result = adjudicate_progress([stale, newer_event])
        # Same source and same stage family: later actual event wins, the
        # later source_updated_at on the older event cannot promote it back.
        self.assertEqual(result["latest_progress_at"], "2026-10-25T08:00:00+08:00")

    def test_order_invariance(self):
        rows = [
            ev("已到港", "2026-10-20T10:00:00+08:00"),
            ev("清关中", "2026-10-20T10:00:00+08:00"),
            ev("已签收", "2026-10-28T10:00:00+08:00"),
        ]
        forward = adjudicate_progress(rows)
        reverse = adjudicate_progress(list(reversed(rows)))
        self.assertEqual(forward, reverse)


class EstimatedOnlyTests(unittest.TestCase):
    def test_eta_only_is_not_a_progress_status(self):
        result = adjudicate_progress([
            ev("ETA", "2026-11-18T00:00:00+08:00", kind="estimated",
               source="carrier_eta"),
        ])
        self.assertEqual(result["latest_progress_status"], "ETA")
        self.assertFalse(result["is_final"])
        self.assertFalse(result["conflict_flag"])
        self.assertEqual(classify_stage(result), TRANSPORT_STAGE)


if __name__ == "__main__":
    unittest.main()
