"""Review U01 closure and SO family PoC, with offline source functions and synthetic docs."""
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import g1b_review_probes as probe

REF = "e696fa652ced786be052117fe6b2db0cb8666694"
probe.REF = REF


def line(name, item, customer="synthetic-customer", group="synthetic-group"):
    return {"name": name, "item_code": item, "customer_item_code": customer,
            "item_group": group, "qty": 1, "delivered_qty": 0, "uom": "Nos"}


def run():
    build = probe.functions("g1b_en_extract.py", {"build_four_way"}, {"defaultdict": defaultdict})["build_four_way"]
    wos = [{"name": "WO-A"}, {"name": "WO-B"}]
    jc = {"WO-A": {"last_op_qty": 6}}
    ses = [{"se": "SE-good", "work_order": "WO-A", "status": "ok", "finished_qty": 5},
           {"se": "SE-missing", "work_order": None, "status": "missing_doc", "finished_qty": None}]
    result = build(wos, jc, ses, "missing_doc_without_work_order")
    assert all(r["se_status"] == "query_incomplete" and r["se_finished_qty"] is None
               and r["produced_pending_stock_in"] is None for r in result.values())
    assert result["WO-A"]["se_known_subtotal"] == 5
    assert build(wos, jc, ses[:1], None)["WO-A"]["se_finished_qty"] == 5
    observed = []
    with TemporaryDirectory(prefix="family-so-synthetic-") as temp:
        root = Path(temp)
        def execute(case, documents, discoveries, pilots=(), max_sos=500):
            directory = root / case
            args = SimpleNamespace(date_from="2026-04-01", date_to="2026-09-30", groups="synthetic-group",
                bom="synthetic-unused", no_item_codes=False, out=str(directory / "rows.jsonl"), max_sos=max_sos)
            class Parser:
                def add_argument(self, *a, **k):
                    pass
                def parse_args(self):
                    return args
            iss = SimpleNamespace(load_credentials=lambda *a: ("x", "y"), resolve_env_files=lambda: [],
                ENV_URLS={"prod": "synthetic://offline"}, SO_FIELDS=[], IN_CHUNK=40,
                child_filter=lambda *a: [], chunks=lambda values, size: [values],
                paginated_get=lambda *a, **k: discoveries.get(k["label"], []),
                find_sales_orders_by_customer_code=lambda *a: list(pilots),
                dedupe_by=lambda rows, key: list({r[key]: r for r in rows}.values()),
                get_single=lambda doctype, name, *a: documents.get(name))
            main = probe.functions("en_family_poc.py", {"main"}, {
                "argparse": SimpleNamespace(ArgumentParser=lambda **k: Parser()), "iss": iss,
                "Path": Path, "json": json, "datetime": datetime,
                "time": SimpleNamespace(sleep=lambda *a: None), "DEFAULT_GROUPS": ["synthetic-group"],
                "BOM": "synthetic-unused", "FAMILY_PREFIXES": ("KS0001", "KS0248"),
                "PILOT_CODES": {"synthetic-pilot"}, "load_family_items": lambda *a: ["KS0001-A"]})["main"]
            with redirect_stdout(io.StringIO()):
                code = main()
            manifest = json.loads((directory / "family_poc_manifest.json").read_text(encoding="utf-8"))
            rows = [json.loads(r) for r in (directory / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
            return code, manifest, rows
        old = {"name": "SO-old", "transaction_date": "2025-01-01", "delivery_date": "2025-02-01",
               "items": [line("L-old", "KS0001-A", customer="synthetic-pilot")]}
        code, manifest, rows = execute("date-window", {"SO-old": old}, {}, [{"name": "SO-old"}])
        assert code == 0 and len(rows) == 1 and rows[0]["transaction_date"] < manifest["date_from"]
        observed.append("S01 undated pilot discovery includes a wholly out-of-window SO in dated output")
        doc = {"name": "SO-family", "transaction_date": "2026-05-01", "delivery_date": "2026-06-01",
               "items": [line("L-KS", "KS0001-A"), line("L-PK", "PK#KS0001-A", group="synthetic-packaging-group")]}
        found = {"SO(group_delivery)": [{"name": "SO-family"}]}
        code, manifest, rows = execute("packaging", {"SO-family": doc}, found)
        assert manifest["family_lines"] == 1 and manifest["non_family_sibling_lines"] == 1
        assert all(r["item_code"] != "PK#KS0001-A" for r in rows)
        observed.append("S02 known-family PK# role candidate without pilot/group is classified as non-family sibling")
        other = {**doc, "name": "SO-other"}
        code, manifest, rows = execute("cap", {"SO-family": doc, "SO-other": other},
            {"SO(group_delivery)": [{"name": "SO-family"}, {"name": "SO-other"}]}, max_sos=1)
        assert code == 0 and manifest["so_headers"] == 1 and "truncated" not in manifest
        observed.append("S03 max_sos truncates discovered parents without manifest partial/truncated status")
        code, manifest, rows = execute("detail-failure", {"SO-family": doc},
            {"SO(group_delivery)": [{"name": "SO-family"}, {"name": "SO-missing"}]})
        assert code == 0 and len(manifest["field_issues"]) == 1 and "complete" not in manifest
        observed.append("S04 missing parent detail is recorded but run still exits0 with no completeness gate")
    print(json.dumps({"ref": REF, "scope": "synthetic offline only", "U01": "PASS: all candidates unknown, known_subtotal5 retained; complete-query positive5",
                      "poc_counterexamples": observed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
