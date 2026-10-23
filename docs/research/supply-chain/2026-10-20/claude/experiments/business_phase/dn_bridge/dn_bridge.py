#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DN -> 运单号 桥接（只读，最小生产查询；不改 EN）。

Why this exists / what was searched first (see report §①):
  * EN_API/tongtool_purchase/ 只用父单 `logistic_number`（单值），没有子表；
  * PR #291 `EN_API/fulfillment/` 没有 logistic 字段；其 `fetch_delivery_notes()`
    只取 name/status/docstatus/posting_date/customer/company/is_return；
  * PR #301 的 DN handoff 文档也不含运单号；
  * 本地缓存（order_store.duckdb 53 表、wo_dn_coverage.*、g1b_en_*.json）均无
    `custom_zmt_logistic_numbers` —— 所以必须做一次最小生产只读查询。

Rules encoded here (violating any one voids the output):
  1. 一个 DN 展开 N 个运单号 ≠ DN 数量 × N；数量仍按 DN 物料行，本脚本根本不取 qty。
  2. 父单主字段与子表第一条是同一条 -> 去重（key = 运单号）。
  3. 子表没有 SKU/qty -> 不做任何数量拆分。
  4. 这是 DN<->运单桥，不证明分运单数量/ETA/可售日期。
  5. 只覆盖 creation >= 2026-08-01 的 DN；更早的标 not_covered，不外推。
  6. 子表 docstatus=0（父单 docstatus=1）-> 绝不能按子表 docstatus 过滤。

Usage:
  uv run python .../dn_bridge.py --probe      # 只探规模与 schema
  uv run python .../dn_bridge.py --run        # 全量拉取（>= 2026-08-01）+ 写产物
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[3]
OUT = CLAUDE_DIR / "out" / "business_phase"
OUT.mkdir(parents=True, exist_ok=True)
ENV_CANDIDATES = (
    Path("D:/Work/赛狐/Cursor/EN_API/.env"),      # 主仓库（worktree 里没有 .env）
    Path("D:/Work/赛狐/Cursor-claude/EN_API/.env"),
)
BASE_URL = "https://erpnext.vilavi.cn"            # 生产
COVERAGE_FROM = "2026-08-01"                       # Jack 维护范围
MAX_RETRIES = 3
PAGE = 200
SLEEP = 0.15


def load_env() -> dict:
    for p in ENV_CANDIDATES:
        if p.exists():
            env = {}
            for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
            return env
    raise SystemExit("找不到 EN_API/.env")


def auth(env):
    return {"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}"}


def get(session, path, params=None):
    last = None
    for _ in range(MAX_RETRIES):
        try:
            r = session.get(f"{BASE_URL}{path}", params=params, timeout=60)
            return r.status_code, (r.json() if r.content else {})
        except Exception as exc:                       # noqa: BLE001
            last = exc
            time.sleep(1.5)
    raise SystemExit(f"GET {path} failed: {last}")


def list_dns(session, h, since: str | None, fields, limit):
    """Paged list of Delivery Note (parent fields only — constraint #5)."""
    rows, start = [], 0
    while True:
        params = {"fields": json.dumps(fields), "limit_start": start,
                  "limit_page_length": PAGE, "order_by": "creation asc"}
        if since:
            params["filters"] = json.dumps([["Delivery Note", "creation", ">=", since]])
        code, body = get(session, "/api/resource/Delivery Note", params)
        if code != 200:
            raise SystemExit(f"list DN -> HTTP {code}: {str(body)[:300]}")
        chunk = body.get("data") or []
        rows.extend(chunk)
        if len(chunk) < PAGE or (limit and len(rows) >= limit):
            break
        start += PAGE
        time.sleep(SLEEP)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--max-dn", type=int, default=0, help="safety cap for get_single fan-out")
    args = ap.parse_args()

    env = load_env()
    session = requests.Session()
    session.headers.update(auth(env))

    # ---- counts ------------------------------------------------------------
    code, body = get(session, "/api/method/frappe.client.get_count",
                     {"doctype": "Delivery Note"})
    total = body.get("message") if code == 200 else None
    code2, body2 = get(session, "/api/method/frappe.client.get_count",
                       {"doctype": "Delivery Note",
                        "filters": json.dumps([["Delivery Note", "creation", ">=", COVERAGE_FROM]])})
    since_n = body2.get("message") if code2 == 200 else None
    print(json.dumps({"dn_total": total, "dn_since_2026_08_01": since_n,
                      "count_http": [code, code2]}, ensure_ascii=False))

    if args.probe:
        rows = list_dns(session, session.headers, COVERAGE_FROM,
                        ["name", "creation", "docstatus", "posting_date", "customer"], 3)
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        if rows:
            code3, doc = get(session, f"/api/resource/Delivery Note/{rows[0]['name']}")
            d = doc.get("data") or {}
            print(json.dumps({
                "sample_dn": rows[0]["name"],
                "parent_keys_with_logistic": [k for k in d if "logistic" in k.lower()],
                "custom_zmt_logistic_numbers": d.get("custom_zmt_logistic_numbers"),
                "n_items": len(d.get("items") or []),
            }, ensure_ascii=False, indent=1)[:2000])
        return

    if not args.run:
        print("nothing to do: pass --probe or --run")
        return

    # ---- full pull ---------------------------------------------------------
    rows = list_dns(session, session.headers, COVERAGE_FROM,
                    ["name", "creation", "docstatus", "posting_date", "customer", "status"], 0)
    if args.max_dn:
        rows = rows[:args.max_dn]
    print(f"fetched {len(rows)} DN (>= {COVERAGE_FROM})")

    bridge, per_dn, errors = [], {}, []
    for i, r in enumerate(rows, 1):
        name = r["name"]
        code, doc = get(session, f"/api/resource/Delivery Note/{name}")
        if code != 200:
            errors.append({"dn": name, "http": code})
            time.sleep(SLEEP)
            continue
        d = doc.get("data") or {}
        parent_ln = (d.get("logistic_number") or "").strip()
        children = d.get("custom_zmt_logistic_numbers") or []
        numbers = []          # (number, is_primary, source)
        seen = set()
        for c in children:
            ln = (c.get("logistic_number") or "").strip()
            if not ln or ln in seen:
                continue
            seen.add(ln)
            numbers.append((ln, int(c.get("is_primary") or 0), "child"))
        if parent_ln and parent_ln not in seen:      # parent not in child -> keep, mark
            numbers.append((parent_ln, 0, "parent_only"))
        elif parent_ln and parent_ln in seen:
            numbers = [(n, p, ("parent+child" if n == parent_ln else s)) for n, p, s in numbers]
        per_dn[name] = dict(dn=name, creation=r.get("creation"), docstatus=r.get("docstatus"),
                            posting_date=r.get("posting_date"), customer=r.get("customer"),
                            status=r.get("status"),
                            parent_logistic_number=parent_ln,
                            n_items=len(d.get("items") or []),
                            child_rows=len(children),
                            n_numbers=len(numbers),
                            dedup_removed=(len([c for c in children
                                                if (c.get("logistic_number") or "").strip()])
                                           + (1 if parent_ln else 0) - len(numbers)),
                            **{"n_primary": sum(1 for _, p, _ in numbers if p)})
        for n, p, src in numbers:
            bridge.append(dict(dn=name, creation=r.get("creation"),
                               docstatus=r.get("docstatus"), logistic_number=n,
                               is_primary=p, source=src))
        if i % 50 == 0:
            print(f"  {i}/{len(rows)}")
        time.sleep(SLEEP)

    # ---- write row-level (local) ------------------------------------------
    with (OUT / "dn_bridge_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(bridge[0].keys()) if bridge else ["dn"])
        w.writeheader()
        w.writerows(bridge)
    with (OUT / "dn_bridge_dn.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(next(iter(per_dn.values())).keys()))
        w.writeheader()
        w.writerows(per_dn.values())

    print(json.dumps({"dns": len(per_dn), "bridge_rows": len(bridge),
                      "errors": len(errors), "error_sample": errors[:5]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
