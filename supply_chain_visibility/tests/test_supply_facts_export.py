"""Conservative merge tests for the supply facts batch exporter."""
import importlib.util
from pathlib import Path
import unittest


def _load_exporter():
    path = Path(__file__).resolve().parents[2] / "EN_API" / "supply_facts_export.py"
    spec = importlib.util.spec_from_file_location("supply_facts_export_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _empty_target():
    return {"lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [], "partial": False,
            "counts": {}, "coverage": {}, "sources": {}, "source_timestamps": {},
            "restricted": {}, "external_sources": {},
            "notes": [], "rule_version": "", "as_of": ""}


def _batch(**coverage):
    return {"lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [],
            "manifest": {"partial": True, "coverage": coverage,
                         "notes": ["note"], "counts": {"input": 1},
                         "rule_version": "v1", "as_of": "2026-10-27"}}


class MergeSemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exporter = _load_exporter()

    def test_restricted_is_or_and_sources_is_and(self):
        target = _empty_target()
        self.exporter._merge(target, _batch(
            sources={"delivery_note": True, "work_order": True},
            restricted={"delivery_note": True, "work_order": False}))
        self.exporter._merge(target, _batch(
            sources={"delivery_note": False, "work_order": True},
            restricted={"delivery_note": False, "work_order": False}))
        self.assertTrue(target["restricted"]["delivery_note"])
        self.assertFalse(target["restricted"]["work_order"])
        self.assertFalse(target["sources"]["delivery_note"])
        self.assertTrue(target["sources"]["work_order"])
        self.assertTrue(target["partial"])

    def test_external_sources_and_timestamps_are_conservative(self):
        target = _empty_target()
        self.exporter._merge(target, _batch(
            external_sources={"receipt": "not_integrated"},
            source_timestamps={"delivery_note": "2026-10-27T10:00:00"}))
        self.exporter._merge(target, _batch(
            external_sources={"receipt": "integrated"},
            source_timestamps={"delivery_note": "2026-10-27T09:00:00"}))
        self.assertEqual(target["external_sources"]["receipt"], "not_integrated")
        self.assertEqual(target["source_timestamps"]["delivery_note"],
                         "2026-10-27T09:00:00")

    def test_empty_reason_is_preserved(self):
        target = _empty_target()
        self.exporter._merge(target, _batch(empty_reason="no_matching_lines"))
        self.assertEqual(target["coverage"]["empty_reason"], "no_matching_lines")


if __name__ == "__main__":
    unittest.main()
