"""Offline regression probes against a fixed Claude revision, using synthetic data.

No module imports from the reviewed tree, business files, credentials or API calls.
A reproduced defect is a review finding, not a production-data verification.
"""
import ast
from collections import defaultdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace

REF = "2ae0650b7e701fd0726e6c32748fc5a041ed7d6c"
PREFIX = "docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/"


def source(name):
    return subprocess.check_output(["git", "show", f"{REF}:{PREFIX}{name}"], encoding="utf-8")


def functions(name, names, environment=None):
    tree = ast.parse(source(name))
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(selected) == len(names)
    env = dict(environment or {})
    exec(compile(ast.Module(body=selected, type_ignores=[]), name, "exec"), env)
    return env


def run():
    report = []
    cov = functions("g1b_coverage.py", {"coverage"}, {"MONTHS": list(range(6))})["coverage"]
    demand = {"by_sku_branch": {("3PL", "synthetic-A"): {"gross": 6, "reissue": 0}}}
    rows = cov(demand, {"by_sku_branch": {}})
    assert rows[0]["supply"] == 0 and rows[0]["coverage_months_gross"] == 0
    report.append("P01: unqueried 3PL inventory becomes supply0/coverage0 and enters all-branch shortage filters")

    class Sheet:
        def iter_rows(self, values_only):
            return iter([("产品编号", "客户物料号"), ("KS0001-A", "synthetic-A"), ("KS0248-B", "synthetic-A")])
    class Book:
        sheetnames = ["synthetic"]
        def __getitem__(self, name):
            return Sheet()
        def close(self):
            pass
    bom = functions("g1b_coverage.py", {"load_bom", "cell"},
                    {"BOM": None, "FAMILIES": ("KS0001", "KS0248"),
                     "openpyxl": SimpleNamespace(load_workbook=lambda *a, **k: Book())})
    mapping, ambiguity = bom["load_bom"]()
    assert ambiguity == 1 and mapping["synthetic-A"] == "KS0001-A"
    report.append("P02: ambiguous customer code is reported but still mapped to first item")

    numeric = functions("g1b_stock_snapshot.py", {"_to_num"})["_to_num"]
    assert numeric(None) == numeric("bad") == 0 and numeric("1.5") == 1.5
    report.append("P03: missing/bad stock quantities become0; fractional quantities pass")

    summary = functions("g1b_en_extract.py", {"jc_summary"})["jc_summary"]
    cards = [{"operation": op, "total_completed_qty": 40, "status": "Completed"} for op in ("cut", "sew")]
    assert summary({"WO-synthetic": cards})["WO-synthetic"]["completed_qty"] == 80
    report.append("P04: two successive operations on same40 pieces aggregate to completed_qty80")

    tree = ast.parse(source("g1b_stock_snapshot.py"))
    method = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == "StockClient"
                  for n in c.body if isinstance(n, ast.FunctionDef) and n.name == "query_chunk")
    env = functions("g1b_stock_snapshot.py", {"business_code", "rows_of"}, {"CODE_OK": 200})
    exec(compile(ast.Module(body=[method], type_ignores=[]), "query_chunk", "exec"), env)
    fake = SimpleNamespace(_call_with_retry=lambda args: {"code": 200, "datas": [{"goodsSku": "synthetic-A"}]})
    assert len(env["query_chunk"](fake, "synthetic-wh", ["synthetic-A"], 1, 1)) == 1
    empty = SimpleNamespace(_call_with_retry=lambda args: {"text": "unrecognized envelope"})
    assert env["query_chunk"](empty, "synthetic-wh", ["synthetic-A"], 1, 1) == []
    report.append("P05: full last allowed page and unrecognized response both return success-shaped rows, no incompleteness signal")

    load = functions("g1b_coverage.py", {"load_stock", "wh_branch_and_kind"},
                     {"Path": Path, "json": json, "defaultdict": defaultdict})["load_stock"]
    with TemporaryDirectory(prefix="g1b-synthetic-") as temp:
        path = Path(temp) / "fixture.json"
        path.write_text(json.dumps({"by_sku": [{"sku": "synthetic-A", "warehouses": {
            "美中-FZH-DANEEY": {"available": 4, "intransit": 0}}}]}), encoding="utf-8")
        stock = load([path, path])
    assert stock["by_branch"]["USTX"]["available"] == 8
    report.append("P06: same snapshot provided twice doubles on-hand4 to8 without rejection")
    assert 421 + 622 == 1043 and 1043 != 1036
    report.append("P07: report open balance421+622=1043, differs from stated1036 by7")
    print(json.dumps({"ref": REF, "scope": "synthetic offline defect reproductions only",
                      "reproduced": len(report), "observations": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
