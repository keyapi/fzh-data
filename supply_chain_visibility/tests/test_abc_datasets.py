"""Structured A/B/C contract: versions, hashes, dependencies, fail-closed."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from supply_chain_visibility.abc_datasets import (
    AbcDatasetError,
    load_abc_datasets,
    load_dataset,
    rows_sha256,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "abc"
AS_OF = "2026-11-02"
AS_OF_TIME = "2026-11-02T00:00:00+00:00"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _rehash(envelope):
    envelope["row_count"] = len(envelope["rows"])
    envelope["sha256"] = rows_sha256(envelope["rows"])
    return envelope


class StructuredAbcTests(unittest.TestCase):
    def test_happy_path_reuses_readiness_and_attribution(self):
        result = load_abc_datasets(
            FIXTURES / "a.json", FIXTURES / "b.json", FIXTURES / "c.json",
            as_of=AS_OF, max_stock_age_days=1, as_of_time=AS_OF_TIME)
        self.assertEqual(result["schema_version"], "abc-frozen/v4")
        self.assertEqual(result["approved_items"], ["ITEM-1", "ITEM-3"])
        row = next(item for item in result["inventory"]
                   if item["item_code"] == "ITEM-1")
        self.assertEqual(row["market"], "US")
        self.assertEqual(row["product_form"], "finished")
        self.assertEqual(row["attribution_status"], "attributed")
        self.assertEqual(row["inventory_qty"], "10")
        self.assertEqual(row["inventory_current_available_qty"], "10")
        without = next(item for item in result["inventory"]
                       if item["item_code"] == "ITEM-3")
        self.assertIsNone(without["inventory_qty"])
        self.assertIn("b_missing_same_product_pool", without["reasons"])
        report = result["report"]
        self.assertEqual(report["dataset_versions"]["B"], "Bv1")
        self.assertEqual(report["version_relation"], "match")

    def test_missing_b_column_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = _load(FIXTURES / "b.json")
            b["rows"][0].pop("market")
            _write(Path(tmp) / "b.json", _rehash(b))
            with self.assertRaises(AbcDatasetError) as ctx:
                load_abc_datasets(FIXTURES / "a.json", Path(tmp) / "b.json",
                                  FIXTURES / "c.json", as_of=AS_OF,
                                  max_stock_age_days=1)
            self.assertIn("missing field", str(ctx.exception))

    def test_alias_conflict_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = _load(FIXTURES / "b.json")
            b["rows"][0]["warehouse"] = "WH-OTHER"
            _write(Path(tmp) / "b.json", _rehash(b))
            with self.assertRaises(AbcDatasetError) as ctx:
                load_dataset(Path(tmp) / "b.json", "B")
            self.assertIn("alias conflict", str(ctx.exception))

    def test_row_count_and_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = _load(FIXTURES / "a.json")
            a["row_count"] = 99
            path = _write(Path(tmp) / "a.json", a)
            with self.assertRaises(AbcDatasetError):
                load_dataset(path, "A")
            a = _load(FIXTURES / "a.json")
            a["sha256"] = "0" * 64
            path = _write(Path(tmp) / "a.json", a)
            with self.assertRaises(AbcDatasetError):
                load_dataset(path, "A")

    def test_unknown_field_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = _load(FIXTURES / "a.json")
            a["rows"][0]["guessed_market"] = "US"
            path = _write(Path(tmp) / "a.json", _rehash(a))
            with self.assertRaises(AbcDatasetError) as ctx:
                load_dataset(path, "A")
            self.assertIn("unknown field", str(ctx.exception))

    def test_dependency_version_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _load(FIXTURES / "c.json")
            c["dependency_versions"]["B"]["version"] = "Bv-OLD"
            path = _write(Path(tmp) / "c.json", _rehash(c))
            with self.assertRaises(AbcDatasetError) as ctx:
                load_abc_datasets(FIXTURES / "a.json", FIXTURES / "b.json",
                                  path, as_of=AS_OF, max_stock_age_days=1)
            self.assertIn("depends on B", str(ctx.exception))

    def test_c_row_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _load(FIXTURES / "c.json")
            c["rows"][0]["b_hash"] = "1" * 64
            path = _write(Path(tmp) / "c.json", _rehash(c))
            with self.assertRaises(AbcDatasetError) as ctx:
                load_abc_datasets(FIXTURES / "a.json", FIXTURES / "b.json",
                                  path, as_of=AS_OF, max_stock_age_days=1)
            self.assertIn("b_hash", str(ctx.exception))

    def test_non_finite_c_quantity_is_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                c = _load(FIXTURES / "c.json")
                c["rows"][0]["qty"] = value
                path = _write(Path(tmp) / "c.json", _rehash(c))
                with self.assertRaises(AbcDatasetError):
                    load_dataset(path, "C")

    def test_market_is_not_inferred_when_b_omits_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = _load(FIXTURES / "b.json")
            b["rows"][0]["market"] = None
            path = _write(Path(tmp) / "b.json", _rehash(b))
            b_sha = rows_sha256(b["rows"])
            c = _load(FIXTURES / "c.json")
            c["rows"][0]["b_hash"] = b_sha
            c["dependency_versions"]["B"]["sha256"] = b_sha
            c_path = _write(Path(tmp) / "c.json", _rehash(c))
            result = load_abc_datasets(FIXTURES / "a.json", path, c_path,
                                       as_of=AS_OF, max_stock_age_days=1,
                                       as_of_time=AS_OF_TIME)
            row = next(item for item in result["inventory"]
                       if item["item_code"] == "ITEM-1")
            self.assertIsNone(row["market"])
            self.assertEqual(row["product_form"], "finished")

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "requires pyarrow")
    def test_parquet_dataset_with_sidecar_manifest(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as tmp:
            envelope = _load(FIXTURES / "a.json")
            rows = envelope.pop("rows")
            pq.write_table(pa.Table.from_pylist(rows),
                           Path(tmp) / "a.parquet")
            (Path(tmp) / "a.manifest.json").write_text(
                json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
            loaded = load_dataset(Path(tmp) / "a.parquet", "A")
            self.assertEqual(len(loaded["rows"]), 3)
            self.assertEqual(loaded["sha256"], rows_sha256(rows))


if __name__ == "__main__":
    unittest.main()
