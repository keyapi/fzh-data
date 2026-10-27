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
            "notes": [], "schema_version": "", "rule_version": "",
            "implementation_version": "", "as_of": ""}


def _batch(**coverage):
    return {"lines": [], "stage_balances": [], "milestones": [],
            "availability_schedule": [], "links": [],
            "manifest": {"schema_version": "supply-facts/v1",
                         "implementation_version": "impl-v1",
                         "partial": True, "coverage": coverage,
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

    def test_implementation_version_is_carried(self):
        target = _empty_target()
        batch = _batch()
        batch["manifest"]["implementation_version"] = "key_test.supply_facts@2026-10-27.3"
        self.exporter._merge(target, batch)
        self.assertEqual(target["implementation_version"],
                         "key_test.supply_facts@2026-10-27.3")

    def test_mixed_implementation_version_is_rejected(self):
        target = _empty_target()
        self.exporter._merge(target, _batch())
        batch = _batch()
        batch["manifest"]["implementation_version"] = "impl-v2"
        with self.assertRaises(self.exporter.BatchVersionError):
            self.exporter._merge(target, batch)
        self.assertEqual(target["implementation_version"], "impl-v1")
        self.assertEqual(target["lines"], [])

    def test_mixed_rule_schema_or_as_of_is_rejected(self):
        target = _empty_target()
        self.exporter._merge(target, _batch())
        for key, value in (("rule_version", "v2"), ("schema_version", "supply-facts/v2"),
                           ("as_of", "2026-10-28T00:00:00")):
            bad = _batch()
            bad["manifest"][key] = value
            with self.assertRaises(self.exporter.BatchVersionError):
                self.exporter._merge(target, bad)

    def test_batch_missing_version_is_rejected(self):
        target = _empty_target()
        for key in ("schema_version", "rule_version", "implementation_version", "as_of"):
            bad = _batch()
            del bad["manifest"][key]
            with self.assertRaises(self.exporter.BatchVersionError):
                self.exporter._merge(target, bad)


if __name__ == "__main__":
    unittest.main()
