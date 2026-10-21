"""Fourth fixed-ref re-review; synthetic fixtures and AST only, no production access."""
import ast
from collections import defaultdict
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import g1b_review_probes as probe

REF = "f14c97097b054cd2e55353c3baa89a8446c35d46"
probe.REF = REF
REQUIRED = {"USNJ": ("美东-CENTRADE",), "USTX": ("美中-FZH-DANEEY",), "PL": ("波兰-FZHPoland-covers",)}


def run():
    passed = []
    env = probe.functions("g1b_coverage.py", {"load_stock", "coverage", "wh_branch_and_kind"},
        {"Path": Path, "json": json, "defaultdict": defaultdict, "math": math,
         "MONTHS": list(range(6)), "REQUIRED_SUPPLY_WAREHOUSES": REQUIRED})
    demand = {"months_observed": 6, "window_complete": True,
              "by_sku_branch": {("USNJ", "synthetic-A"): {"gross": 6}}}
    with TemporaryDirectory(prefix="g1b-round4-synthetic-") as temp:
        root = Path(temp)
        raw = root / "fixture.jsonl"
        args = SimpleNamespace(all_skus=True, backup_dir=str(root), out=str(root / "converted.json"),
                               warehouses="", bom="unused", allow_missing_hash=False)
        class Parser:
            def add_argument(self, *a, **k):
                pass
            def parse_args(self):
                return args
        convert = probe.functions("g1b_from_daily_backup.py", {"main", "parse_qty", "sha256"},
            {"argparse": SimpleNamespace(ArgumentParser=Parser), "Path": Path, "json": json,
             "math": math, "hashlib": hashlib, "defaultdict": defaultdict,
             "QTY_FIELDS": ("available", "intransit", "defects", "waiting"), "BOM": "unused"})["main"]
        value = {"goodsSku": "synthetic-A", "warehouseName": "美东-CENTRADE", "availableStockQuantity": 0,
                 "intransitStockQuantity": 0, "defectsStockQuantity": 0, "waitingShipmentStockQuantity": 0}
        raw.write_text(json.dumps(value) + "\n", encoding="utf-8")
        manifest = {"run_id": "synthetic-run", "snapshot_at": "2026-10-21", "warehouses": [
            {"warehouseName": "美东-CENTRADE", "file": str(raw), "complete": True,
             "file_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}]}
        def conversion():
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                convert()
            return json.loads((root / "converted.json").read_text(encoding="utf-8"))
        result = conversion()
        stock = env["load_stock"]([root / "converted.json"])
        row = env["coverage"](demand, stock)[0]
        assert row["quantity_status"] == "observed_zero" and row["supply"] == 0
        missing = env["coverage"]({**demand, "by_sku_branch": {("USNJ", "synthetic-missing"): {"gross": 6}}}, stock)
        missing_row = next(r for r in missing if r["sku"] == "synthetic-missing")
        assert missing_row["quantity_status"] == "missing" and missing_row["supply"] is None
        passed.append("T01 explicit observed0 remains0; absent SKU is missing/None")
        manifest["warehouses"][0]["file_sha256"] = "0" * 64
        result = conversion()
        assert result["complete"] is False and not result["read_warehouses"] and result["hash_mismatches"]
        manifest["warehouses"][0]["file_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        passed.append("T02 manifest hash mismatch rejected; matching hash accepted")
        args.warehouses = "美东-CENTRADE,synthetic-absent-warehouse"
        result = conversion()
        assert len(result["requested_warehouses"]) == 2 and result["complete"] is False
        assert result["missing_requested"] == ["synthetic-absent-warehouse"]
        args.warehouses = ""
        passed.append("T03 requested absent warehouse retained and incomplete")
        manifest["warehouses"].append({"warehouseName": "美中-FZH-DANEEY", "file": str(root / "missing.jsonl"), "complete": False})
        result = conversion()
        stock = env["load_stock"]([root / "converted.json"])
        assert result["complete"] is False and stock["selected_complete"]["美东-CENTRADE"] is True
        assert "美东-CENTRADE" in stock["complete_warehouses"]
        passed.append("T04 healthy warehouse remains complete under partial global batch")
        partial = {**demand, "months_observed": 5, "window_complete": False}
        rows = env["coverage"](partial, stock)
        tree = ast.parse(probe.source("g1b_coverage.py"))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        start = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "headline_eligible" for t in n.targets))
        finish = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "result" for t in n.targets))
        local = {"demand": partial, "complete_branches": {"USNJ"}, "rows": rows}
        exec(compile(ast.Module(body=main.body[start:finish], type_ignores=[]), "headline", "exec"), local)
        assert local["headline_eligible"] is False and not local["no_supply"] and not local["below_2"]
        passed.append("T06 partial demand window blocked from headline")

    source = ast.parse(probe.source("g1b_en_extract.py"))
    main = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    start = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "four_way" for t in n.targets))
    finish = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "result" for t in n.targets))
    def fetch_and_aggregate(documents):
        good = {"work_order": "WO-synthetic", "docstatus": 1, "items": [
            {"name": "line-good", "item_code": "item-synthetic", "qty": 5,
             "uom": "Nos", "stock_uom": "Nos", "is_finished_item": 1}]}
        fake_iss = SimpleNamespace(IN_CHUNK=100, chunks=lambda rows, size: [rows],
            paginated_get=lambda *a, **k: documents, dedupe_by=lambda rows, key: rows,
            get_single=lambda doctype, name, *a: good if name == "SE-good" else None)
        fetch = probe.functions("g1b_en_extract.py", {"fetch_manufacture_stock_entries"},
            {"iss": fake_iss, "time": SimpleNamespace(sleep=lambda *a: None)})["fetch_manufacture_stock_entries"]
        rows, error = fetch(["WO-synthetic"], ["item-synthetic"], "", "", "", 0)
        context = {"defaultdict": defaultdict, "se_rows": rows, "se_error": error,
                   "ctx": {"wos": [{"name": "WO-synthetic"}]}, "jc": {}}
        exec(compile(ast.Module(body=main.body[start:finish], type_ignores=[]), "four_way", "exec"), context)
        return rows, error, context["four_way"]["WO-synthetic"]
    rows, error, total = fetch_and_aggregate([{"name": "SE-missing", "work_order": "WO-synthetic"}])
    assert rows[0]["work_order"] == "WO-synthetic" and total["se_finished_qty"] is None
    passed.append("T05 located missing detail retains WO and remains unknown")
    rows, error, total = fetch_and_aggregate([{"name": "SE-unlocated"}])
    assert error == "missing_doc_without_work_order" and total["se_finished_qty"] is None
    passed.append("T05 only-unlocated failure marks candidate WO unknown")
    rows, error, total = fetch_and_aggregate([{"name": "SE-good", "work_order": "WO-synthetic"}, {"name": "SE-unlocated"}])
    assert error == "missing_doc_without_work_order" and total["se_status"] == "ok" and total["se_finished_qty"] == 5
    print(json.dumps({"ref": REF, "scope": "synthetic offline only", "repair_checks": passed,
        "remaining_defect": "U01 mixed known-good SE and unlocated missing SE bypasses query-error guard; partial5 reported ok"},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
