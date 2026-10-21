"""Fixed-ref repair checks and negative probes; synthetic data, no business/API access."""
import ast
from collections import defaultdict
from datetime import datetime
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from contextlib import redirect_stdout

import g1b_review_probes as probe

REF = "aad55822d942706bc0ba7177e5523c757d0d6cf7"
probe.REF = REF  # Reuse offline AST selector, not the old revision's expected defects.


def snapshot(path, complete, stamp, value, wh="美东-CENTRADE"):
    vals = {"available": value, "intransit": 0, "defects": 0, "waiting": 0}
    path.write_text(json.dumps({"complete": complete, "fetched_at": stamp, "warehouses": [wh],
        "by_sku": [{"sku": "synthetic-A", "warehouses": {wh: vals}}]}), encoding="utf-8")


def run():
    observations = []
    covenv = probe.functions("g1b_coverage.py", {"load_stock", "coverage", "wh_branch_and_kind"},
                             {"Path": Path, "json": json, "defaultdict": defaultdict, "MONTHS": list(range(6))})
    demand = {"months_observed": 6, "by_sku_branch": {("USNJ", "synthetic-A"): {"gross": 6}}}
    with TemporaryDirectory(prefix="g1b-round2-synthetic-") as temp:
        root = Path(temp)
        old, new = root / "old.json", root / "new.json"
        snapshot(old, True, "2026-10-20", 10)
        snapshot(new, False, "2026-10-21", 0)
        stock = covenv["load_stock"]([old, new]); row = covenv["coverage"](demand, stock)[0]
        assert row["supply"] == 0 and row["supply_status"] == "sampled_complete"
        observations.append("R01 old complete tag leaks onto selected new incomplete snapshot")
        payload = json.loads(old.read_text(encoding="utf-8"))
        payload["by_sku"].append({"sku": "synthetic-A", "warehouses": {"美东-CENTRADE": {
            "available": 99, "intransit": 0, "defects": 0, "waiting": 0}}})
        old.write_text(json.dumps(payload), encoding="utf-8")
        stock = covenv["load_stock"]([old]); row = covenv["coverage"](demand, stock)[0]
        assert stock["duplicate_conflicts"] == 1 and row["supply_status"] == "sampled_complete"
        observations.append("R02 reported duplicate conflict does not downgrade coverage completeness")
        snapshot(new, True, "2026-10-21", 5, "WayfairCG-Cranbury")
        wayfair_demand = {"months_observed": 6, "by_sku_branch": {("3PL", "synthetic-A"): {"gross": 6}}}
        row = covenv["coverage"](wayfair_demand, covenv["load_stock"]([new]))[0]
        assert row["supply_status"] == "sampled_complete"
        observations.append("R03 complete Tongtool Wayfair stock can become authoritative 3PL supply without source gate")

        class Parser:
            def add_argument(self, *a, **k):
                pass
            def parse_args(self):
                return SimpleNamespace(all_skus=True, backup_dir=str(root), out=str(root / "converted.json"), warehouses="", bom="unused")
        converter = probe.functions("g1b_from_daily_backup.py", {"main"},
            {"argparse": SimpleNamespace(ArgumentParser=Parser), "Path": Path, "json": json, "BOM": "unused"})["main"]
        raw = root / "synthetic.jsonl"
        values = {"goodsSku": "synthetic-A", "warehouseName": "美东-CENTRADE", "availableStockQuantity": None,
                  "intransitStockQuantity": 0, "defectsStockQuantity": 0, "waitingShipmentStockQuantity": 0}
        raw.write_text(json.dumps(values) + "\n" + json.dumps({**values, "availableStockQuantity": 99}) + "\n", encoding="utf-8")
        manifest = {"snapshot_at": "2026-10-21", "warehouses": [{"warehouseName": "美东-CENTRADE", "file": str(raw), "complete": True}]}
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            converter()
        converted = json.loads((root / "converted.json").read_text(encoding="utf-8"))
        assert converted["complete"] is True and converted["by_sku"][0]["available"] == 0
        observations.append("R04 daily converter turns missing number into0 and silently discards conflicting duplicate while complete=true")
        manifest["warehouses"][0]["file"] = str(root / "missing.jsonl")
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            converter()
        converted = json.loads((root / "converted.json").read_text(encoding="utf-8"))
        assert converted["complete"] is True and converted["warehouses"] == []
        observations.append("R05 missing JSONL still produces global complete=true (downstream currently has no sampled warehouse)")
        backup = probe.functions("stock_daily_backup.py", {"backup_warehouse", "rows_of"},
            {"Path": Path, "datetime": datetime, "json": json,
             "Client": object, "STOCK_QUERY_TOOL": "synthetic", "FIELDS": ("goodsSku", "warehouseName")})
        fake_client = SimpleNamespace(call=lambda *a: {"code": 200, "datas": {"unexpected": "shape"}})
        result = backup["backup_warehouse"](fake_client, {"warehouseName": "synthetic-wh", "warehouseId": "synthetic"}, root, 100, 2)
        assert result["complete"] is True and result["rows"] == 0
        observations.append("R06 daily backup unrecognized response yields complete empty warehouse")

    jc = probe.functions("g1b_en_extract.py", {"jc_summary", "_op_order"}, {"defaultdict": defaultdict})["jc_summary"]
    route = [{"name": "WO-synthetic", "operations": [{"operation": "cut", "sequence_id": 1}, {"operation": "sew", "sequence_id": 2}]}]
    cards = {"WO-synthetic": [{"operation": "sew", "total_completed_qty": 4, "docstatus": 2, "status": "Cancelled"}]}
    result = jc(cards, route)["WO-synthetic"]
    assert result["first_operation"] == "sew" and result["first_op_qty"] == 4
    observations.append("R07 missing first operation is replaced by later card; cancelled card contributes quantity")
    fake_iss = SimpleNamespace(IN_CHUNK=100, chunks=lambda rows, size: [rows],
        paginated_get=lambda *a, **k: [{"name": "SE-synthetic"}], dedupe_by=lambda rows, key: rows,
        get_single=lambda *a: None)
    fetch = probe.functions("g1b_en_extract.py", {"fetch_manufacture_stock_entries"}, {"iss": fake_iss})["fetch_manufacture_stock_entries"]
    rows, error = fetch(["WO-synthetic"], ["item-synthetic"], "", "", "", 0)
    assert rows[0]["status"] == "missing_doc" and error is None
    observations.append("R08 missing SE detail returns no query error; main's aggregation can substitute missing WO total with0")
    breakdown = probe.functions("g1b_en_extract.py", {"open_breakdown"})["open_breakdown"]
    so = [{"so": "synthetic-dead", "open_qty": 421, "anomalies": ["死单(Closed未发)"]},
          {"so": "synthetic-wip", "open_qty": 622, "wos": ["WO-synthetic"]},
          {"so": "synthetic-no-plan", "open_qty": 9}, {"so": "synthetic-over", "open_qty": -16}]
    assert breakdown(so, {"open_qty": 1036})["difference"] == 0
    class Sheet:
        def iter_rows(self, values_only):
            return iter([("产品编号", "客户物料号"), ("KS0001-A", "synthetic-A"), ("KS0248-B", "synthetic-A")])
    class Book:
        sheetnames = ["synthetic"]
        def __getitem__(self, name):
            return Sheet()
        def close(self):
            pass
    bom = probe.functions("g1b_coverage.py", {"load_bom", "cell"},
        {"BOM": None, "FAMILIES": ("KS0001", "KS0248"),
         "openpyxl": SimpleNamespace(load_workbook=lambda *a, **k: Book())})
    mapping, ambiguous = bom["load_bom"]()
    assert "synthetic-A" not in mapping and ambiguous == ["synthetic-A"]
    tree = ast.parse(probe.source("g1b_stock_snapshot.py"))
    method = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == "StockClient"
                  for n in c.body if isinstance(n, ast.FunctionDef) and n.name == "query_chunk")
    env = probe.functions("g1b_stock_snapshot.py", {"business_code", "rows_of"}, {"CODE_OK": 200, "json": json})
    exec(compile(ast.Module(body=[method], type_ignores=[]), "query_chunk", "exec"), env)
    fake = SimpleNamespace(_call_with_retry=lambda args: {"code": 200, "datas": [{"goodsSku": "synthetic-A"}]})
    _, meta = env["query_chunk"](fake, "synthetic-wh", ["synthetic-A"], 1, 1)
    assert meta["truncated"] is True and meta["complete"] is False
    numeric = probe.functions("g1b_stock_snapshot.py", {"_to_num"})["_to_num"]
    assert numeric(None) is None and numeric("bad") is None
    print(json.dumps({"ref": REF, "scope": "synthetic offline re-review only", "remaining_defects_reproduced": len(observations),
        "observations": observations, "positive_checks": ["421+622+9-16=1036; breakdown difference0", "BOM ambiguity removes mapping", "direct snapshot full page cap returns incomplete/truncated", "direct snapshot missing/bad number is None"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
