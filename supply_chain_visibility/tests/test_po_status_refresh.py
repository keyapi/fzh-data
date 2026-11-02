# -*- coding: utf-8 -*-
"""Batched PO status refresh: dedupe, batching, resume, unqueried."""

import unittest

from supply_chain_visibility.po_status_refresh import (
    dedupe_po_codes,
    refresh_po_statuses,
)


class DedupeTests(unittest.TestCase):
    def test_skus_collapse_to_unique_pos(self):
        codes = dedupe_po_codes({"SKU-1": ["PO-1", "PO-2"],
                                 "SKU-2": "PO-1",
                                 "SKU-3": []})
        self.assertEqual(codes, ["PO-1", "PO-2"])


class RefreshTests(unittest.TestCase):
    def test_batches_of_ten_and_all_codes_returned(self):
        calls = []

        def query(codes):
            calls.append(list(codes))
            return {"results": {code: {"found": True, "raw_status": "0"}
                                for code in codes}}

        codes = ["PO-%02d" % index for index in range(12)]
        result = refresh_po_statuses(codes, query)
        self.assertEqual([len(batch) for batch in calls], [10, 2])
        self.assertEqual(result["returned"], 12)
        self.assertEqual(result["unqueried"], {})
        self.assertEqual(result["termination_reason"], "completed")

    def test_resume_from_checkpoint_skips_previous_batches(self):
        calls = []
        codes = ["PO-%02d" % index for index in range(12)]

        def query(batch):
            calls.append(list(batch))
            return {"results": {code: {"found": True, "raw_status": "0"}
                                for code in batch}}

        result = refresh_po_statuses(codes, query, start_index=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["returned"], 2)

    def test_rate_limit_marks_all_remaining_unqueried(self):
        codes = ["PO-%02d" % index for index in range(25)]

        def query(batch):
            if batch[0] == "PO-10":
                return {"results": {code: {"reason": "rate_limited"}
                                    for code in batch},
                        "exhausted": True, "termination_reason": "rate_limited"}
            return {"results": {code: {"found": True, "raw_status": "0"}
                                for code in batch}}

        result = refresh_po_statuses(codes, query)
        self.assertTrue(result["exhausted"])
        self.assertEqual(result["termination_reason"], "rate_limited")
        self.assertEqual(result["unqueried"]["PO-10"], "rate_limited")
        self.assertEqual(result["unqueried"]["PO-24"], "rate_limited")
        self.assertEqual(result["statuses"]["PO-24"]["source_status"],
                         "not_queried")

    def test_missing_code_in_response_is_not_success(self):
        def query(batch):
            return {"results": {batch[0]: {"found": True, "raw_status": "0"}},
                    "partial": True, "termination_reason": "partial_not_queried"}

        result = refresh_po_statuses(["PO-1", "PO-2"], query)
        self.assertEqual(result["statuses"]["PO-2"]["source_status"],
                         "not_queried")
        self.assertEqual(result["unqueried"]["PO-2"], "missing_in_response")
        self.assertTrue(result["partial"])

    def test_source_error_is_not_known(self):
        def query(batch):
            return {"results": {batch[0]: {"reason": "source_error"}}}

        result = refresh_po_statuses(["PO-1"], query)
        self.assertEqual(result["statuses"]["PO-1"]["source_status"], "source_error")
        self.assertFalse(result["statuses"]["PO-1"]["found"])


if __name__ == "__main__":
    unittest.main()
