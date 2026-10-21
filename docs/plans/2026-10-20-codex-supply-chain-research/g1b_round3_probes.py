"""Third G1b review: fixed-ref closures and remaining defects, synthetic offline only."""
import ast
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import g1b_review_probes as probe

REF = "f4797aa06bf5bb9168c02bc3841a31b0549ea0ed"
probe.REF = REF
REQUIRED = {"USNJ": ("美东-CENTRADE",), "USTX": ("美中-FZH-DANEEY",), "PL": ("波兰-FZHPoland-covers",)}


def write_snapshot(path, complete, stamp, value, wh="美东-CENTRADE"):
    vals = {"available": value, "intransit": 0, "defects": 0, "waiting": 0}
    path.write_text(json.dumps({"complete": complete, "fetched_at": stamp, "warehouses": [wh],
        "by_sku": [{"sku": "synthetic-A", "warehouses": {wh: vals}}]}), encoding="utf-8")


def run():
    closed, remaining = [], []
    env = probe.functions("g1b_coverage.py", {"load_stock", "coverage", "wh_branch_and_kind"},
        {"Path": Path, "json": json, "defaultdict": defaultdict, "math": math,
         "MONTHS": list(range(6)), "REQUIRED_SUPPLY_WAREHOUSES": REQUIRED})
    demand = {"months_observed": 6, "by_sku_branch": {("USNJ", "synthetic-A"): {"gross": 6}}}
    with TemporaryDirectory(prefix="g1b-round3-synthetic-") as temp:
        root = Path(temp)
        old, new = root / "old.json", root / "new.json"
        write_snapshot(old, True, "2026-10-20", 10)
        write_snapshot(new, False, "2026-10-21", 0)
        row = env["coverage"](demand, env["load_stock"]([old, new]))[0]
        assert row["supply_status"] != "sampled_complete"
        closed.append("old complete no longer authorizes selected incomplete snapshot")
        payload = json.loads(old.read_text(encoding="utf-8"))
        payload["by_sku"].append({"sku": "synthetic-A", "warehouses": {"美东-CENTRADE": {
            "available": 99, "intransit": 0, "defects": 0, "waiting": 0}}})
        old.write_text(json.dumps(payload), encoding="utf-8")
        assert env["coverage"](demand, env["load_stock"]([old]))[0]["supply_status"] != "sampled_complete"
        closed.append("conflicting duplicate downgrades warehouse")
        write_snapshot(new, True, "2026-10-21", 5, "WayfairCG-Cranbury")
        wf = {"months_observed": 6, "by_sku_branch": {("3PL", "synthetic-A"): {"gross": 6}}}
        assert env["coverage"](wf, env["load_stock"]([new]))[0]["supply_status"] == "unknown_authority"
        closed.append("Tongtool Wayfair complete is not inventory authority")
        absent = env["coverage"](demand, {"complete_warehouses": ["美东-CENTRADE"], "by_sku_branch": {}})[0]
        assert absent["supply_status"] == "sampled_complete" and absent["supply"] == 0
        remaining.append("T01 absent SKU in complete warehouse still becomes confirmed supply0")

        args = SimpleNamespace(all_skus=True, backup_dir=str(root), out=str(root / "converted.json"), warehouses="", bom="unused")
        class Parser:
            def add_argument(self, *a, **k):
                pass
            def parse_args(self):
                return args
        convert = probe.functions("g1b_from_daily_backup.py", {"main", "parse_qty", "sha256"},
            {"argparse": SimpleNamespace(ArgumentParser=Parser), "Path": Path, "json": json,
             "math": math, "hashlib": hashlib, "defaultdict": defaultdict,
             "QTY_FIELDS": ("available", "intransit", "defects", "waiting"), "BOM": "unused"})["main"]
        raw = root / "fixture.jsonl"
        vals = {"goodsSku": "synthetic-A", "warehouseName": "美东-CENTRADE", "availableStockQuantity": 2,
                "intransitStockQuantity": 0, "defectsStockQuantity": 0, "waitingShipmentStockQuantity": 0}
        manifest = {"snapshot_at": "2026-10-21", "warehouses": [{"warehouseName": "美东-CENTRADE", "file": str(raw), "complete": True}]}
        def conversion(rows):
            raw.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                convert()
            return json.loads((root / "converted.json").read_text(encoding="utf-8"))
        result = conversion([{**vals, "availableStockQuantity": None}])
        assert result["complete"] is False and result["bad_rows_total"] == 1
        closed.append("converter missing quantity remains bad, not0")
        result = conversion([vals, {**vals, "availableStockQuantity": 9}])
        assert result["complete"] is False and result["duplicate_conflicts"] == 1 and result["by_sku"] == []
        closed.append("converter conflicting key is removed and warehouse incomplete")
        manifest["warehouses"][0]["file"] = str(root / "missing.jsonl")
        result = conversion([vals])
        assert result["complete"] is False and result["missing_files"]
        closed.append("converter missing file is incomplete")
        manifest["warehouses"][0]["file"] = str(raw)
        manifest["warehouses"][0]["file_sha256"] = "0" * 64
        result = conversion([vals])
        assert result["complete"] is True and result["file_hashes"]["美东-CENTRADE"] != "0" * 64
        remaining.append("T02 converter records new hash but accepts mismatch against manifest expected hash")
        args.warehouses = "美东-CENTRADE,synthetic-missing-warehouse"
        result = conversion([vals])
        assert result["complete"] is True and "synthetic-missing-warehouse" not in result["requested_warehouses"]
        remaining.append("T03 requested warehouse missing from manifest is silently dropped from request set")
        args.warehouses = ""
        manifest["warehouses"].append({"warehouseName": "美中-FZH-DANEEY", "file": str(root / "missing.jsonl"), "complete": False})
        result = conversion([vals])
        assert result["by_warehouse"]["美东-CENTRADE"]["complete"] is True and result["complete"] is False
        stock = env["load_stock"]([root / "converted.json"])
        assert "美东-CENTRADE" not in stock["complete_warehouses"]
        remaining.append("T04 load_stock ignores per-warehouse complete and downgrades healthy warehouse under partial batch")

    incomplete_demand = {**demand, "months_observed": 5, "window_complete": False}
    test_stock = {"complete_warehouses": ["美东-CENTRADE"], "by_sku_branch": {
        ("USNJ", "synthetic-A"): {"available": 0, "intransit": 0}}}
    rows = env["coverage"](incomplete_demand, test_stock)
    coverage_main = next(n for n in ast.parse(probe.source("g1b_coverage.py")).body if isinstance(n, ast.FunctionDef) and n.name == "main")
    filters = [n for n in coverage_main.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id in {"no_supply", "below_2"} for t in n.targets)]
    filter_env = {"rows": rows}
    exec(compile(ast.Module(body=filters, type_ignores=[]), "coverage_filters", "exec"), filter_env)
    assert len(filter_env["no_supply"]) == len(filter_env["below_2"]) == 1
    remaining.append("T06 incomplete demand window still enters headline shortage filters")

    rows_of = probe.functions("stock_daily_backup.py", {"rows_of"})["rows_of"]
    assert rows_of({"code": 200, "datas": []}) == []
    try:
        rows_of({"code": 200, "datas": {"unexpected": "shape"}})
    except ValueError:
        closed.append("daily backup distinguishes malformed response from legal empty array")
    else:
        raise AssertionError("malformed response accepted")
    jc = probe.functions("g1b_en_extract.py", {"jc_summary", "_op_order"}, {"defaultdict": defaultdict})["jc_summary"]
    route = [{"name": "WO-synthetic", "operations": [{"operation": "cut", "sequence_id": 1}, {"operation": "sew", "sequence_id": 2}]}]
    result = jc({"WO-synthetic": [{"operation": "sew", "total_completed_qty": 4}]}, route)["WO-synthetic"]
    assert result["first_operation"] == "cut" and result["first_op_qty"] is None
    closed.append("missing true first operation remains unknown")
    fake_iss = SimpleNamespace(IN_CHUNK=100, chunks=lambda rows, size: [rows],
        paginated_get=lambda *a, **k: [{"name": "SE-synthetic", "work_order": "WO-synthetic"}],
        dedupe_by=lambda rows, key: rows, get_single=lambda *a: None)
    fetch = probe.functions("g1b_en_extract.py", {"fetch_manufacture_stock_entries"}, {"iss": fake_iss})["fetch_manufacture_stock_entries"]
    se_rows, se_error = fetch(["WO-synthetic"], ["item-synthetic"], "", "", "", 0)
    main = next(n for n in ast.parse(probe.source("g1b_en_extract.py")).body if isinstance(n, ast.FunctionDef) and n.name == "main")
    start = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "four_way" for t in n.targets))
    finish = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "result" for t in n.targets))
    context = {"defaultdict": defaultdict, "se_rows": se_rows, "se_error": se_error, "ctx": {"wos": route}, "jc": {}}
    exec(compile(ast.Module(body=main.body[start:finish], type_ignores=[]), "four_way", "exec"), context)
    assert se_rows[0]["status"] == "missing_doc" and context["four_way"]["WO-synthetic"]["se_finished_qty"] == 0
    remaining.append("T05 missing SE detail loses WO foreign key and main aggregation still substitutes0")
    print(json.dumps({"ref": REF, "scope": "synthetic offline only", "repair_positive_checks": closed,
                      "remaining_counterexamples": remaining}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
