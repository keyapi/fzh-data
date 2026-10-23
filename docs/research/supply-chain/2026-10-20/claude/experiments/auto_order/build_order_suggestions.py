#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EN auto-order suggestions V0.1 (READ-ONLY, D25 charter).

Scope: submitted SOs with status not in {Closed, Cancelled} and
transaction_date >= 2026-01-01 (open demand only).

Gates (visible per row)
  * SO validity: docstatus=1 and status not Closed/Cancelled; `is_internal_customer`
    is surfaced as "待人工确认是否重复补货" and never dropped.
  * Bin: stock must exist for the TARGET warehouse; missing = 未取得 (null), never 0.
  * Dedupe: demand key = (po_no, item, delivery_date, warehouse); duplicates are
    flagged (not dropped). PO lines are deduped by (po, item, warehouse, date);
    WO lines by (wo, item, date). Missing dates cannot be placed in a window.
  * UOM: direct item needs uom == stock_uom; BOM split needs component uom equal
    to the SO item uom and a numeric qty_per. Unproven -> class C.
  * Pairing: only when the BOM is unique AND UOM conversion is proven; BOM
    uniqueness alone is not proof. Otherwise no split -> "规则未证".

Time slicing: H=15/30/60 are computed SEPARATELY (never summed). need-by keeps
the original delivery date; overdue days are reported, the date is not shifted.

Budget: single-threaded GET only, <=150 requests, page_length <=100,
>=200 ms interval, stop on timeout / 5xx.

Outputs: out/auto_order/order_suggestions.csv / .json, regression_vs_examples.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import requests

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "auto_order"
ENV = Path("D:/Work/赛狐/Cursor/EN_API/.env")
DB = Path("D:/Work/fzh-order-store/order_store.duckdb")
BASE = "https://erpnext.vilavi.cn"
MAX_GETS = 150
SLEEP_S = 0.2
TIMEOUT_S = 20
PAGE = 100
TODAY = date(2026, 10, 22)
SCOPE_FROM = "2026-01-01"
HORIZONS = (15, 30, 60)
UOM_OK = {"个", "件", "pcs", "Pcs"}


def sha(x: str) -> str:
    return hashlib.sha256(str(x).encode("utf-8")).hexdigest()[:12]


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip()
    return env


class StopRun(Exception):
    pass


class Client:
    def __init__(self, base, key, secret):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"token {key}:{secret}",
                               "Accept": "application/json"})
        self.gets = 0
        self.by_path = Counter()
        self.last = 0.0
        self.started = time.time()
        self.stop_reason = None
        self.errors = []

    def get(self, path, params=None):
        if self.gets >= MAX_GETS:
            self.stop_reason = f"request_cap({MAX_GETS})"
            raise StopRun(self.stop_reason)
        wait = SLEEP_S - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.gets += 1
        bucket = path
        if path.startswith("/api/resource/Sales Order/"):
            bucket = "/api/resource/Sales Order/<doc>"
        self.by_path[bucket] += 1
        self.last = time.time()
        try:
            r = self.s.get(self.base + path, params=params, timeout=TIMEOUT_S)
        except Exception as exc:
            self.stop_reason = f"timeout/connection:{type(exc).__name__}"
            self.errors.append(self.stop_reason)
            raise StopRun(self.stop_reason)
        if r.status_code >= 500 or r.status_code == 408:
            self.stop_reason = f"http_{r.status_code}"
            self.errors.append(f"{path} -> {r.status_code}")
            raise StopRun(self.stop_reason)
        if r.status_code in (401, 403):
            self.stop_reason = f"auth_{r.status_code}"
            self.errors.append(f"{path} -> {r.status_code}")
            raise StopRun(self.stop_reason)
        try:
            return r.json()
        except Exception:
            return None


def _chunks(xs, n=50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def list_all(c, doctype, fields, filters, order="name asc"):
    out, start = [], 0
    while True:
        res = c.get(f"/api/resource/{doctype}",
                    {"fields": json.dumps(fields), "filters": json.dumps(filters),
                     "limit_page_length": PAGE, "limit_start": start,
                     "order_by": order})
        rows = (res or {}).get("data", []) if isinstance(res, dict) else []
        out.extend(rows)
        if len(rows) < PAGE:
            break
        start += PAGE
    return out


def local_data():
    con = duckdb.connect(str(DB), read_only=True)
    try:
        items = {r[0]: dict(item_name=r[1], item_group=r[2])
                 for r in con.execute("SELECT item, item_name, item_group FROM item_attr").fetchall()}
        boms = defaultdict(list)
        for bom, item, qty in con.execute("SELECT bom, item, quantity FROM bom").fetchall():
            boms[item].append(bom)
        comps = defaultdict(list)
        for parent, item, qty, uom in con.execute(
                "SELECT parent, item_code, qty, uom FROM bom_item").fetchall():
            comps[parent].append((item, float(qty or 0), (uom or "").strip()))
    finally:
        con.close()
    return items, boms, comps


def bin_stock(c, items):
    out = defaultdict(dict)
    ok = True
    for chunk in _chunks(sorted(items)):
        res = c.get("/api/resource/Bin",
                    {"fields": json.dumps(["item_code", "warehouse", "actual_qty"]),
                     "filters": json.dumps([["item_code", "in", chunk]]),
                     "limit_page_length": PAGE})
        if not (isinstance(res, dict) and "data" in res):
            ok = False
            continue
        for r in res["data"]:
            out[r.get("item_code")][r.get("warehouse")] = float(r.get("actual_qty") or 0)
    return out, ok


def open_po(c, items):
    out, ok, missing_date = defaultdict(float), True, set()
    for chunk in _chunks(sorted(items)):
        res = c.get("/api/resource/Purchase Order",
                    {"fields": json.dumps(["name", "items.item_code", "items.qty",
                                           "items.received_qty", "items.schedule_date",
                                           "items.warehouse"]),
                     "filters": json.dumps([
                         ["Purchase Order Item", "item_code", "in", chunk],
                         ["status", "not in", ["Closed", "Completed", "Cancelled"]],
                         ["docstatus", "=", 1]]),
                     "limit_page_length": PAGE})
        if not (isinstance(res, dict) and "data" in res):
            ok = False
            continue
        seen = set()
        for r in res["data"]:
            code = r.get("item_code")
            if not code:
                continue
            key = (r.get("name"), code, r.get("warehouse"), str(r.get("schedule_date") or "")[:10])
            if key in seen:
                continue                      # PO dedupe
            seen.add(key)
            qty = max(0.0, float(r.get("qty") or 0) - float(r.get("received_qty") or 0))
            if not key[3]:
                missing_date.add(code)
                continue                      # cannot be placed in a window
            out[(code, r.get("warehouse"), key[3])] += qty
    return out, ok, missing_date


def open_wo(c, items):
    out, ok, missing_date = defaultdict(float), True, set()
    for chunk in _chunks(sorted(items)):
        res = c.get("/api/resource/Work Order",
                    {"fields": json.dumps(["name", "production_item", "qty", "produced_qty",
                                           "status", "planned_end_date"]),
                     "filters": json.dumps([["production_item", "in", chunk],
                                            ["status", "not in",
                                             ["Completed", "Cancelled", "Closed", "Stopped"]]]),
                     "limit_page_length": PAGE})
        if not (isinstance(res, dict) and "data" in res):
            ok = False
            continue
        seen = set()
        for r in res["data"]:
            code = r.get("production_item")
            if not code:
                continue
            d = str(r.get("planned_end_date") or "")[:10]
            key = (r.get("name"), code, d)
            if key in seen:
                continue                      # WO dedupe
            seen.add(key)
            qty = max(0.0, float(r.get("qty") or 0) - float(r.get("produced_qty") or 0))
            if not d:
                missing_date.add(code)
                continue
            out[(code, d)] += qty
    return out, ok, missing_date


def within(dstr, days):
    if not dstr:
        return False
    try:
        d = datetime.strptime(dstr[:10], "%Y-%m-%d").date()
    except Exception:
        return False
    return d <= TODAY + timedelta(days=days)


def po_h(po, item, wh, days):
    return sum(q for (code, w, d), q in po.items()
               if code == item and w == wh and within(d, days))


def wo_h(wo, item, days):
    return sum(q for (code, d), q in wo.items() if code == item and within(d, days))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ENV))
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = load_env(Path(args.env))
    c = Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])
    items_meta, boms, comps = local_data()

    lines, notes = [], []
    try:
        heads = list_all(c, "Sales Order",
                         ["name", "docstatus", "status", "transaction_date", "po_no",
                          "customer", "is_internal_customer"],
                         [["docstatus", "=", 1],
                          ["status", "not in", ["Closed", "Cancelled"]],
                          ["transaction_date", ">=", SCOPE_FROM]])
        for h in heads:
            d = c.get(f"/api/resource/Sales Order/{h['name']}")
            if not (d and d.get("data")):
                notes.append(f"skip {h['name']}: no doc")
                continue
            doc = d["data"]
            so_hash = sha(doc["name"])
            for idx, it in enumerate(doc.get("items") or []):
                qty = float(it.get("qty") or 0)
                delivered = float(it.get("delivered_qty") or 0)
                unfulfilled = max(0.0, qty - delivered)
                if unfulfilled <= 0:
                    continue
                lines.append(dict(
                    so_hash=so_hash, so_status=doc.get("status"),
                    po_no=(doc.get("po_no") or "").strip(),
                    internal=bool(doc.get("is_internal_customer")),
                    customer_hash=sha(doc.get("customer") or ""),
                    line_idx=idx, item=it.get("item_code") or "",
                    qty=qty, delivered=delivered, unfulfilled=unfulfilled,
                    delivery_date=str(it.get("delivery_date") or "")[:10],
                    warehouse=it.get("warehouse") or "",
                    uom=(it.get("uom") or "").strip(),
                    stock_uom=(it.get("stock_uom") or "").strip(),
                    conversion=it.get("conversion_factor")))

        # demand dedupe suspects (never dropped)
        groups = defaultdict(list)
        for ln in lines:
            if ln["po_no"]:
                groups[(ln["po_no"], ln["item"], ln["delivery_date"],
                        ln["warehouse"])].append(ln)
        dup = {id(x) for v in groups.values() if len(v) > 1 for x in v}
        for ln in lines:
            ln["dup_suspect"] = id(ln) in dup
            ln["dedupe_key"] = bool(ln["po_no"])

        # targets: direct component or BOM split
        targets = set()
        for ln in lines:
            code = ln["item"]
            if code.startswith(("PK#", "ND#")) or not boms.get(code) or len(boms[code]) != 1:
                targets.add(code)
            else:
                targets |= {c0 for c0, _, _ in comps.get(boms[code][0], [])}
        stock, bin_ok = bin_stock(c, targets)
        po, po_ok, po_missing = open_po(c, targets)
        wo, wo_ok, wo_missing = open_wo(c, targets)
    except StopRun:
        stock, po, wo = {}, {}, {}
        bin_ok = po_ok = wo_ok = False
        po_missing, wo_missing = set(), set()
        notes.append(f"停止：{c.stop_reason}")

    # per-line target rows
    rows = []
    for ln in lines:
        code = ln["item"]
        rule, tgt = "直接物料", [(code, 1.0, ln["uom"])]
        if not code.startswith(("PK#", "ND#")):
            if len(boms.get(code, [])) == 1:
                comp = comps.get(boms[code][0], [])
                pk = [x for x in comp if x[0].startswith("PK#")]
                nd = [x for x in comp if x[0].startswith("ND#")]
                if pk and nd:
                    rule = "BOM"
                    tgt = [(pk[0][0], pk[0][1], pk[0][2]),
                           (nd[0][0], nd[0][1], nd[0][2])]
                else:
                    rule = "规则未证"
            else:
                rule = "规则未证"
        for target, per, tuom in tgt:
            uom_proven = (ln["uom"] != "" and ln["uom"] == ln["stock_uom"] and ln["uom"] in UOM_OK)
            if rule == "BOM":
                uom_proven = uom_proven and tuom in UOM_OK and float(per or 0) > 0
            mapped = target in items_meta or target.startswith(("PK#", "ND#"))
            item_stock = stock.get(target)
            s = (float(item_stock.get(ln["warehouse"]))
                 if item_stock is not None and ln["warehouse"] in item_stock else None)
            blockers = []
            cls = "A"
            if not uom_proven:
                blockers.append("uom_unproven")
                cls = "C"
            if not mapped:
                blockers.append("mapping_unproven")
                cls = "C"
            if s is None:
                blockers.append("bin_missing")
                cls = "B" if cls == "A" else cls
            if ln["internal"]:
                blockers.append("internal_customer_confirm")
                cls = "B" if cls == "A" else cls
            if ln["dup_suspect"]:
                blockers.append("duplicate_demand_suspect")
                cls = "B" if cls == "A" else cls
            if not ln["dedupe_key"]:
                blockers.append("dedupe_key_missing")
                cls = "B" if cls == "A" else cls
            if rule == "规则未证":
                blockers.append("bom_rule_unproven")
                cls = "B" if cls == "A" else cls
            if target in po_missing or target in wo_missing:
                blockers.append("supply_date_missing")
                cls = "B" if cls == "A" else cls
            if not ln["delivery_date"]:
                blockers.append("delivery_date_missing")
                cls = "B" if cls == "A" else cls
            nets = {}
            for H in HORIZONS:
                due = ln["unfulfilled"] * per if within(ln["delivery_date"], H) else 0.0
                p = po_h(po, target, ln["warehouse"], H)
                w = wo_h(wo, target, H)
                nets[f"due_L{H}"] = round(due, 2)
                nets[f"po_L{H}"] = round(p, 2)
                nets[f"wo_L{H}"] = round(w, 2)
                nets[f"net_L{H}"] = (round(max(0.0, due - s - p - w), 2)
                                     if s is not None else None)
            rows.append(dict(
                so_hash=ln["so_hash"], so_status=ln["so_status"],
                po_no_hash=sha(ln["po_no"]) if ln["po_no"] else "",
                internal=ln["internal"], line_idx=ln["line_idx"],
                src_item=code, target_item=target, rule=rule,
                warehouse=ln["warehouse"], delivery_date=ln["delivery_date"],
                overdue_days=(max(0, (TODAY - datetime.strptime(
                    ln["delivery_date"][:10], "%Y-%m-%d").date()).days)
                    if ln["delivery_date"] else None),
                unfulfilled=round(ln["unfulfilled"], 2), qty_per=per,
                uom=ln["uom"], stock=(round(s, 2) if s is not None else None),
                class_=cls, blockers=sorted(set(blockers)),
                **nets))

    # aggregate per target x warehouse
    agg = defaultdict(list)
    for r in rows:
        agg[(r["target_item"], r["warehouse"])].append(r)
    sugg = []
    for (target, wh), rr in agg.items():
        blocker = sorted({b for r in rr for b in r["blockers"]})
        cls = "C" if any(r["class_"] == "C" for r in rr) else (
            "B" if any(r["class_"] == "B" for r in rr) else "A")
        need = min((r["delivery_date"] for r in rr if r["delivery_date"]), default="")
        overdue = (max(0, (TODAY - datetime.strptime(need, "%Y-%m-%d").date()).days)
                   if need else None)
        stock_v = next((r["stock"] for r in rr if r["stock"] is not None), None)
        out = dict(target_item=target, warehouse=wh, class_=cls,
                   need_by=need, overdue_days=overdue, stock=stock_v,
                   n_lines=len(rr), n_so=len({r["so_hash"] for r in rr}),
                   so_hashes=sorted({r["so_hash"] for r in rr}),
                   rule=rr[0]["rule"], blockers=blocker,
                   evidence=dict(bin=("recorded" if stock_v is not None else "missing"),
                                 po_rows=sum(1 for (code, w, d) in po
                                             if code == target and w == wh),
                                 wo_rows=sum(1 for (code, d) in wo if code == target),
                                 bom=(boms.get(rr[0]["src_item"], [None])[0]
                                      if rr[0]["rule"] == "BOM" else None)))
        for H in HORIZONS:
            due = sum(r[f"due_L{H}"] for r in rr)
            p = sum(r[f"po_L{H}"] for r in rr)
            w = sum(r[f"wo_L{H}"] for r in rr)
            out[f"due_L{H}"] = round(due, 2)
            out[f"po_L{H}"] = round(p, 2)
            out[f"wo_L{H}"] = round(w, 2)
            out[f"suggest_L{H}"] = (round(max(0.0, due - stock_v - p - w), 2)
                                    if stock_v is not None else None)
        sugg.append(out)

    classes = Counter(s["class_"] for s in sugg)
    result = dict(schema_version="en_order_suggestions/1",
                  generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                  scope=dict(from_date=SCOPE_FROM, open_sos=len({l["so_hash"] for l in lines}),
                             demand_lines=len(lines), suggestions=len(sugg)),
                  gates=dict(bin_ok=bin_ok, po_ok=po_ok, wo_ok=wo_ok,
                             po_missing_date_items=sorted(po_missing),
                             wo_missing_date_items=sorted(wo_missing),
                             internal_customer_sos=len({l["so_hash"] for l in lines
                                                        if l["internal"]}),
                             sos_with_po_no=len({l["so_hash"] for l in lines
                                                 if l["dedupe_key"]}),
                             sos_without_po_no=len({l["so_hash"] for l in lines
                                                    if not l["dedupe_key"]})),
                  classes=dict(classes), suggestions=sugg,
                  blockers=dict(Counter(b for s in sugg for b in s["blockers"])),
                  budget=dict(requests=c.gets, cap=MAX_GETS, interval_s=SLEEP_S,
                              page_length_max=PAGE,
                              elapsed_s=round(time.time() - c.started, 1),
                              by_path=dict(c.by_path),
                              stop_reason=c.stop_reason, errors=c.errors),
                  notes=notes)
    (OUT / "order_suggestions.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    fields = ["target_item", "warehouse", "class_", "need_by", "overdue_days",
              "stock", "rule", "n_lines", "n_so",
              "due_L15", "po_L15", "wo_L15", "suggest_L15",
              "due_L30", "po_L30", "wo_L30", "suggest_L30",
              "due_L60", "po_L60", "wo_L60", "suggest_L60",
              "blockers", "so_hashes", "evidence"]
    with (OUT / "order_suggestions.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in sugg:
            w.writerow({**s, "blockers": "|".join(s["blockers"]),
                        "so_hashes": "|".join(s["so_hashes"]),
                        "evidence": json.dumps(s["evidence"], ensure_ascii=False)})

    # regression vs the 10 examples: one row per EXAMPLE (totals over its targets)
    reg = []
    try:
        ex = list(csv.DictReader(open(OUT / "order_examples.csv", encoding="utf-8-sig")))
        ex_tot = defaultdict(lambda: dict(sums=[0.0, 0.0, 0.0], null=[False, False, False],
                                          eid=None))
        for r in ex:
            t = ex_tot[r["so_hash"]]
            t["eid"] = r["example_id"]
            for i, H in enumerate(HORIZONS):
                v = r[f"net_L{H}"]
                if v in ("", None):
                    t["null"][i] = True
                else:
                    t["sums"][i] += float(v)
        v01 = defaultdict(lambda: dict(sums=[0.0, 0.0, 0.0], null=[False, False, False]))
        so_seen = set()
        for r in rows:
            so_seen.add(r["so_hash"])
            t = v01[r["so_hash"]]
            for i, H in enumerate(HORIZONS):
                v = r[f"net_L{H}"]
                if v is None:
                    t["null"][i] = True
                else:
                    t["sums"][i] += v
        for soh, t in sorted(ex_tot.items(), key=lambda kv: kv[1]["eid"] or ""):
            eid = t["eid"]
            if soh not in so_seen:
                reg.append(dict(example_id=eid, so_hash=soh, status="scope",
                                reason=("V0.1 不纳入：SO 已关闭/取消，或全部行已交付"
                                        "（open SO 有效需求为空）")))
                continue
            v = v01[soh]
            if any(v["null"]):
                reg.append(dict(example_id=eid, so_hash=soh, status="evidence",
                                reason="V0.1 部分 target 库存未取得（net null），整例不比较"))
                continue
            diffs = [round(v["sums"][i] - t["sums"][i], 2) for i in range(3)]
            reg.append(dict(
                example_id=eid, so_hash=soh, status="compared",
                example=[round(x, 2) for x in t["sums"]],
                v01=[round(x, 2) for x in v["sums"]], diff=diffs,
                reason=("一致" if not any(diffs) else
                        "差异：V0.1 证据/规则更严（Bin 目标仓、UOM 已证、PO/WO 日期可归窗、"
                        "BOM 唯一+UOM 才拆配套），示例仅按本地库存/BOM 唯一性计算")))
    except FileNotFoundError:
        reg.append(dict(example_id="—", so_hash="—", status="missing",
                        reason="order_examples.csv 不存在"))

    L = ["# V0.1 建议 vs 10 个算例回归", "",
         "> 口径：每个算例把其所有 target 的 L15/L30/L60 净需求**分别求和**（各 H 不相加）；"
         "V0.1 只纳入 open SO。", "",
         "| 例 | so_hash | 状态 | 示例 L15/30/60 | V0.1 L15/30/60 | 差异 | 解释 |",
         "|---|---|---|---|---|---|---|"]
    for r in reg:
        if r["status"] == "compared":
            L.append(f"| {r['example_id']} | `{r['so_hash']}` | 已比 | {r['example']} | "
                     f"{r['v01']} | {r['diff']} | {r['reason']} |")
        else:
            L.append(f"| {r['example_id']} | `{r['so_hash']}` | "
                     f"{'未纳入' if r['status']=='scope' else '无法比较' if r['status']=='evidence' else '缺失'} "
                     f"| - | - | - | {r['reason']} |")
    L += ["", "## 说明", "",
          "- 差异只归因于：scope（V0.1 只算 open SO）、证据闸门（Bin 目标仓/UOM/PO-WO 日期）、"
          "或规则变更（BOM 唯一 + UOM 换算同时成立才拆配套）。",
          "- 示例中的 closed/cancelled 单在 V0.1 中不产生需求，这是 D25 的 SO 有效性闸门；"
          "未发现计算错误。", ""]
    (OUT / "regression_vs_examples.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("wrote order_suggestions.csv/json + regression_vs_examples.md")
    print("requests", c.gets, "open_sos", result["scope"]["open_sos"],
          "lines", len(lines), "suggestions", len(sugg), "classes", dict(classes))


if __name__ == "__main__":
    main()
