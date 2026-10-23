#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC01 输入基线：机械复核（只读，不做分析）。

对 `out/business_phase/sc01_input_manifest.json` 里登记的每个输入，重算 sha256 / 行数，
并与清单比对；再核对母集对账（1,328 / 2,309 / 2,553 / 1,225）、快照日、UOM 口径。

用法：
  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc01/sc01_input_manifest.py

预期：所有检查行都是 OK，末行 `ALL CHECKS PASS`。
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[2]
BP = CLAUDE / "out" / "business_phase"
MANIFEST = BP / "sc01_input_manifest.json"
DB = Path("D:/Work/fzh-order-store/order_store.duckdb")

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    checks.append((name, bool(ok), detail))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))

    # 1) 文件 hash / 行数
    for name, meta in man["inputs"].items():
        p = CLAUDE / meta["path"]
        check(f"sha256:{name}", sha(p) == meta["sha256"], sha(p)[:16] + "…")
        rows = meta.get("rows")
        if rows is not None:
            if name.endswith(".csv"):
                n = sum(1 for _ in csv.DictReader(p.open(encoding="utf-8-sig", newline="")))
            else:
                n = len(json.loads(p.read_text(encoding="utf-8"))["rows"])
            check(f"rows:{name}", n == rows, f"{n} vs {rows}")

    # 2) DB hash
    db_meta = man["database"]
    h = sha(DB)
    check("sha256:order_store.duckdb", h == db_meta["sha256"], h[:16] + "…")

    import duckdb
    con = duckdb.connect(str(DB), read_only=True)
    try:
        for t, n in db_meta["tables"].items():
            got = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            check(f"table_rows:{t}", got == n, f"{got} vs {n}")
        dates = sorted(str(r[0]) for r in con.execute(
            "SELECT DISTINCT snapshot_date FROM stock_history").fetchall())
        check("stock_snapshot_dates", dates == man["stock_snapshot"]["dates"], ",".join(dates))
        unknown = con.execute(
            "SELECT count(*) FROM stock_history WHERE uom_basis='unknown'").fetchone()[0]
        total = con.execute("SELECT count(*) FROM stock_history").fetchone()[0]
        check("uom_basis_all_unknown", unknown == total, f"{unknown}/{total}")
        n_hist = con.execute("SELECT count(DISTINCT sku) FROM monthly_series").fetchone()[0]
        check("monthly_series_skus", n_hist == man["mother_reconciliation"]["full_history_skus"],
              f"{n_hist} vs {man['mother_reconciliation']['full_history_skus']}")
    finally:
        con.close()

    # 3) 母集对账
    mr = man["mother_reconciliation"]
    check("mother_1328", mr["sku_level"] == 1328, str(mr["sku_level"]))
    check("sku_wh_2309", mr["sku_warehouse_level"] == 2309, str(mr["sku_warehouse_level"]))
    bundle = list(csv.DictReader((BP / "final_bundle.csv").open(encoding="utf-8-sig", newline="")))
    check("bundle_rows_2309", len(bundle) == 2309, str(len(bundle)))
    check("bundle_distinct_sku_1328", len({r["SKU"] for r in bundle}) == 1328,
          str(len({r["SKU"] for r in bundle})))
    check("bundle_distinct_warehouses_11", len({r["仓"] for r in bundle}) == 11,
          str(len({r["仓"] for r in bundle})))
    dist: dict[int, int] = {}
    for cnt in {s: sum(1 for r in bundle if r["SKU"] == s) for s in {r["SKU"] for r in bundle}}.values():
        dist[cnt] = dist.get(cnt, 0) + 1
    check("rows_per_sku", dist == {int(k): v for k, v in mr["rows_per_sku"].items()}, json.dumps(dist))
    check("equation_1328_1225_2553",
          mr["sku_level"] + mr["outside_mother"] == mr["full_history_skus"],
          f"{mr['sku_level']}+{mr['outside_mother']}={mr['full_history_skus']}")

    bad = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"{'OK  ' if ok else 'FAIL'} {name:34s} {detail}")
    print(f"\n{len(checks) - len(bad)}/{len(checks)} passed")
    print("ALL CHECKS PASS" if not bad else f"FAILURES: {len(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
