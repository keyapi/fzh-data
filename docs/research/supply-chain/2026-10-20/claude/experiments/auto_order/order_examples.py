#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EN "what to order" offline examples + rule sketch (READ-ONLY).

Budget: single-threaded GET only, <=120 requests, page_length <=100,
>=200 ms interval, stop on timeout / 5xx.

Data
  * production REST (read-only): Sales Order docs, Delivery Plan linkage,
    open Purchase Orders, open Work Orders;
  * local order_store.duckdb (read-only): stock_latest (via sku_item),
    item_cover_stock, bom / bom_item for the pairing rule.

Examples: 5 from segment C (2026-01..06) and 5 from D (2026-07..10), covering
both / cover-only / cancelled / >=50 lines / with DP / without DP.
Net demand scenarios L15 / L30 / L60 use unfulfilled qty due within the horizon
minus same-warehouse stock minus known open PO/WO due in the horizon.
All numbers are conditional; no write, no auto-submit.

Outputs: out/auto_order/order_examples.md / .csv
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
MAX_GETS = 120
SLEEP_S = 0.2
TIMEOUT_S = 20
PAGE = 100
TODAY = date(2026, 10, 22)
SEGS = {"C": ("2026-01-01", "2026-07-01", "C 2026-01..06"),
        "D": ("2026-07-01", "2026-11-01", "D 2026-07..10")}
REQUIRED = {"C": ["both", "cancelled", "lines50", "dp", "no_dp"],
            "D": ["cover_only", "cancelled", "lines50", "dp", "no_dp"]}


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


def dp_linked(c, names):
    if not names:
        return set()
    res = c.get("/api/resource/Delivery Plan",
                {"fields": json.dumps(["name", "items.sales_order"]),
                 "filters": json.dumps([["Delivery Plan Item", "sales_order", "in", names]]),
                 "limit_page_length": PAGE})
    rows = (res or {}).get("data", []) if isinstance(res, dict) else []
    return {r.get("sales_order") for r in rows if r.get("sales_order") in set(names)}


def local_data():
    con = duckdb.connect(str(DB), read_only=True)
    try:
        sku_item = dict(con.execute("SELECT sku, item_code FROM sku_item").fetchall())
        stock = defaultdict(lambda: defaultdict(float))
        for wh, sku, avail in con.execute(
                "SELECT warehouse, sku, available FROM stock_latest").fetchall():
            item = sku_item.get(sku)
            if item:
                stock[item][wh] += float(avail or 0)
        boms = defaultdict(list)
        for bom, item, qty in con.execute("SELECT bom, item, quantity FROM bom").fetchall():
            boms[item].append(bom)
        comps = defaultdict(list)
        for parent, item, qty in con.execute(
                "SELECT parent, item_code, qty FROM bom_item").fetchall():
            comps[parent].append((item, float(qty or 0)))
    finally:
        con.close()
    return stock, boms, comps


def bin_stock(c, items):
    """EN Bin actual_qty per item x warehouse (read-only); returns (map, ok)."""
    out = defaultdict(dict)
    ok = True
    for chunk in _chunks(items, 30):
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


def _chunks(xs, n=30):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def open_po(c, items):
    if not items:
        return {}, False
    out, ok = defaultdict(float), True
    for chunk in _chunks(items):
        res = c.get("/api/resource/Purchase Order",
                    {"fields": json.dumps(["name", "status", "items.item_code", "items.qty",
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
        for r in res["data"]:
            code = r.get("item_code")
            if not code:
                continue
            qty = float(r.get("qty") or 0) - float(r.get("received_qty") or 0)
            out[(code, r.get("warehouse"), str(r.get("schedule_date") or "")[:10])] += \
                max(0.0, qty)
    return out, ok


def open_wo(c, items):
    if not items:
        return {}, False
    out, ok = defaultdict(float), True
    for chunk in _chunks(items):
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
        for r in res["data"]:
            out[(r.get("production_item"), str(r.get("planned_end_date") or "")[:10])] += \
                max(0.0, float(r.get("qty") or 0) - float(r.get("produced_qty") or 0))
    return out, ok


def classify(doc, linked):
    items = doc.get("items") or []
    codes = [x.get("item_code") or "" for x in items]
    pk = any(x.startswith("PK#") for x in codes)
    nd = any(x.startswith("ND#") for x in codes)
    return dict(both=pk and nd, cover_only=pk and not nd,
                inner_only=nd and not pk, neither=not pk and not nd,
                cancelled=doc.get("docstatus") == 2,
                lines50=len(items) >= 50, dp=doc["name"] in linked,
                no_dp=doc["name"] not in linked, lines=len(items))


def due_within(delivery, days):
    if not delivery:
        return False
    try:
        d = datetime.strptime(delivery[:10], "%Y-%m-%d").date()
    except Exception:
        return False
    return d <= TODAY + timedelta(days=days)


def poi_within(rows, item, wh, days):
    tot = 0.0
    for (code, warehouse, sched), qty in rows.items():
        if code != item or warehouse != wh:
            continue
        if not sched or due_within(sched, days):
            tot += qty
    return tot


def wi_within(rows, item, days):
    """WO rows are keyed by (item, planned_end_date); no warehouse dimension."""
    tot = 0.0
    for (code, sched), qty in rows.items():
        if code != item:
            continue
        if not sched or due_within(sched, days):
            tot += qty
    return tot


def compute_example(doc, linked, stock, boms, comps, po, wo):
    items = doc.get("items") or []
    so_hash = sha(doc["name"])
    cancelled = doc.get("docstatus") == 2
    rows = []
    for idx, it in enumerate(items):
        code = it.get("item_code") or ""
        qty = float(it.get("qty") or 0)
        delivered = float(it.get("delivered_qty") or 0)
        unfulfilled = 0.0 if cancelled else max(0.0, qty - delivered)
        wh = it.get("warehouse") or ""
        ddate = str(it.get("delivery_date") or "")[:10]
        # pairing rule from local BOM (only if a single BOM and it has PK#/ND#)
        rule, pairs = "规则未证", []
        if code.startswith(("PK#", "ND#")):
            rule, pairs = "直接物料", [("-", code, 1.0)]
        elif len(boms.get(code, [])) == 1:
            comp = comps.get(boms[code][0], [])
            pk = [c for c in comp if c[0].startswith("PK#")]
            nd = [c for c in comp if c[0].startswith("ND#")]
            if pk and nd:
                rule = "BOM"
                pairs = [("PK#", pk[0][0], pk[0][1]), ("ND#", nd[0][0], nd[0][1])]
        targets = pairs if pairs else [("-", code, 1.0)]
        for key, target, per in targets:
            nets = {}
            item_stock = stock.get(target)
            s = (float(item_stock.get(wh))
                 if item_stock is not None and wh in item_stock else None)
            for h in (15, 30, 60):
                due = unfulfilled * per if due_within(ddate, h) else 0.0
                p = poi_within(po, target, wh, h)
                w = wi_within(wo, target, h)
                nets[f"due_L{h}"] = round(due, 2)
                nets[f"po_L{h}"] = round(p, 2)
                nets[f"wo_L{h}"] = round(w, 2)
                nets[f"net_L{h}"] = (round(max(0.0, due - s - p - w), 2)
                                     if s is not None else None)
            need = ""
            if unfulfilled > 0 and ddate:
                ndate = max(ddate, TODAY.isoformat())
                need = ndate + ("（原交期已过）" if ddate < TODAY.isoformat() else "")
            rows.append(dict(
                example_id=None, so_hash=so_hash, so_status=doc.get("status"),
                so_docstatus=doc.get("docstatus"),
                transaction_date=str(doc.get("transaction_date") or "")[:10],
                line_idx=idx, src_item=code, qty=qty, delivered=delivered,
                unfulfilled=round(unfulfilled, 2), delivery_date=ddate,
                warehouse=wh, target_item=target, rule=rule, qty_per=per,
                stock=(round(s, 2) if s is not None else None),
                stock_status=("recorded" if s is not None else "no_record"),
                need_date=need, cancelled=cancelled,
                **nets))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ENV))
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = load_env(Path(args.env))
    c = Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])
    stock, boms, comps = local_data()
    stock_source = "local stock_latest"

    selected, notes = [], []
    try:
        for seg, (lo, hi, human) in SEGS.items():
            heads = list_all(c, "Sales Order",
                             ["name", "docstatus", "status", "transaction_date",
                              "per_delivered"], [["transaction_date", ">=", lo],
                                                 ["transaction_date", "<", hi]])
            names = [h["name"] for h in heads]
            # candidates: all cancelled + first 30 by name (docs are 1 GET each)
            cand = [n for n in names if next(h for h in heads if h["name"] == n)["docstatus"] == 2][:2]
            cand += [n for n in names[:30] if n not in cand]
            linked = set()
            # Delivery Plan linkage in batches of 100 names
            for i in range(0, len(cand), PAGE):
                linked |= dp_linked(c, cand[i:i + PAGE])
            docs = []
            for n in cand:
                d = c.get(f"/api/resource/Sales Order/{n}")
                if d and d.get("data"):
                    docs.append(d["data"])
            by = {d["name"]: d for d in docs}
            cls = {n: classify(by[n], linked) for n in by}
            picked = []
            for tag in REQUIRED[seg]:
                hit = next((n for n in sorted(cls) if cls[n][tag] and n not in picked), None)
                if hit:
                    picked.append(hit)
                else:
                    notes.append(f"{seg}: 未找到覆盖 {tag} 的候选")
            for n in sorted(cls):
                if len(picked) >= 5:
                    break
                if n not in picked:
                    picked.append(n)
            for n in picked[:5]:
                selected.append(dict(seg=seg, human=human, doc=by[n], cls=cls[n],
                                     coverage=[k for k, v in cls[n].items() if v is True]))
        # PO / WO for all selected items + BOM components
        all_items = set()
        for s in selected:
            for it in s["doc"].get("items") or []:
                code = it.get("item_code") or ""
                all_items.add(code)
                if len(boms.get(code, [])) == 1:
                    all_items |= {x[0] for x in comps.get(boms[code][0], [])}
        po, po_ok = open_po(c, sorted(all_items))
        wo, wo_ok = open_wo(c, sorted(all_items))
        bin_map, bin_ok = bin_stock(c, sorted(all_items))
        if bin_ok:
            stock = bin_map
            stock_source = "EN Bin actual_qty"
    except StopRun:
        po, wo, po_ok, wo_ok = {}, {}, False, False
        notes.append(f"停止：{c.stop_reason}")

    rows = []
    for i, s in enumerate(selected, 1):
        r = compute_example(s["doc"], set([s["doc"]["name"]]), stock, boms, comps, po, wo)
        for x in r:
            x["example_id"] = f"E{i:02d}"
            x["segment"] = s["seg"]
            x["coverage"] = "|".join(s["coverage"])
        rows.extend(r)
    result = dict(
        schema_version="en_order_examples/1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        budget=dict(requests=c.gets, cap=MAX_GETS, interval_s=SLEEP_S,
                    page_length_max=PAGE,
                    elapsed_s=round(time.time() - c.started, 1),
                    by_path=dict(c.by_path), stop_reason=c.stop_reason,
                    errors=c.errors),
        selected=[dict(example_id=f"E{i:02d}", segment=s["seg"], so_hash=sha(s["doc"]["name"]),
                       so_status=s["doc"].get("status"),
                       docstatus=s["doc"].get("docstatus"),
                       transaction_date=str(s["doc"].get("transaction_date") or "")[:10],
                       lines=s["cls"]["lines"], coverage=s["coverage"]) for i, s in enumerate(selected, 1)],
        notes=notes,
        horizon_today=str(TODAY),
        queries=dict(po_ok=po_ok, wo_ok=wo_ok,
                     stock_source=stock_source,
                     po_note="查询成功但无记录" if po_ok and not po else
                             ("未取得（查询失败）" if not po_ok else "有记录"),
                     wo_note="查询成功但无记录" if wo_ok and not wo else
                             ("未取得（查询失败）" if not wo_ok else "有记录")),
        assumptions=[
            "库存=EN Bin actual_qty（只读）；无记录=未取得、不按 0；fallback 本地 stock_latest",
            "净需求 = 未履约且交期≤horizon − 同仓库存 − 同仓/同物料的已知未结 PO/在产（按日期可得者）",
            "PO/WO 日期缺失时计入所有 horizon 并标注；查询失败记“未取得”",
            "配套规则仅当本地 BOM 唯一且含 PK#+ND# 时成立，否则记“规则未证”；直接物料不拆",
            "样本算例之间不共享库存预留；不是下单指令"],
    )
    (OUT / "order_examples.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    fields = ["example_id", "segment", "coverage", "so_hash", "so_status", "so_docstatus",
              "transaction_date", "line_idx", "src_item", "qty", "delivered",
              "unfulfilled", "delivery_date", "warehouse", "target_item", "rule",
              "qty_per", "due_L15", "due_L30", "due_L60", "stock", "stock_status",
              "po_L15", "po_L30", "po_L60", "wo_L15", "wo_L30", "wo_L60",
              "net_L15", "net_L30", "net_L60", "need_date", "cancelled"]
    with (OUT / "order_examples.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # markdown
    L = ["# EN “该下什么单” 离线算例（草稿）", "",
         "> 只读；预算 ≤120 GET、page_length ≤100、间隔 200ms。**只是建议草稿，不自动提交、不下单。**",
         "> 净需求为条件计算；未知写“未取得/未证”，不填 0。", "",
         "## 0. 预算", "",
         f"- 请求 **{c.gets}** / 120；耗时 **{result['budget']['elapsed_s']} s**；"
         f"停止：{c.stop_reason or '无（正常完成）'}",
         f"- 按路径：{dict(c.by_path)}", "",
         "## 1. 规则草图（需求 → 净需求 → 配套 → 建议）", "",
         "```text",
         "for each open SO line:",
         "    unfulfilled = max(0, qty − delivered)",
         "    for H in [15,30,60]:",
         "        due_H = unfulfilled if delivery_date <= today+H else 0",
         "        net_H = max(0, due_H − stock_same_wh − open_PO_due_H − open_WO_due_H)",
         "    pairing:",
         "        if BOM unique and has PK# + ND#:",
         "            for comp in [PK#, ND#]:",
         "                comp_due_H = due_H × qty_per",
         "                comp_net_H = max(0, comp_due_H − comp_stock_same_wh − comp_PO/WO_due_H)",
         "        else:",
         "            rule = 未证 → 只对成品/原物料给建议，不拆配套",
         "    suggestion:",
         "        按 target_item 汇总 net_H；需要日 = 该 target 最早 due 的交期（已过则 today）",
         "```",
         "",
         "证据要求：① 库存=EN Bin actual_qty（同仓）；② PO/WO 需有物料、数量、仓库、日期；"
         "③ 配套需 BOM 唯一且含 PK#+ND#；④ 缺任一证据则只出“待补证”草稿。"
         "首期只出建议草稿，人工审批后才可提交。", "",
         "## 2. 算例", ""]
    for i, s in enumerate(selected, 1):
        ex = f"E{i:02d}"
        rr = [x for x in rows if x["example_id"] == ex]
        d = s["doc"]
        L += [f"### {ex} · `{sha(d['name'])}` · {s['human']}", "",
              f"- 状态：{d.get('status')} / docstatus {d.get('docstatus')}；"
              f"下单日 {str(d.get('transaction_date') or '')[:10]}；"
              f"覆盖：{'、'.join(s['coverage'])}",
              f"- 行数 {s['cls']['lines']}；本算例输出 {len(rr)} 条 target 行；"
              f"PO 查询：{result['queries']['po_note']}；WO 查询：{result['queries']['wo_note']}", ""]
        if d.get("docstatus") == 2:
            L.append("- **本单已取消**：未履约量按 0 计，不产生任何下单建议。")
            L.append("")
        if s["cls"]["lines"] <= 12:
            L += ["| 物料 | 数量 | 已交付 | 未履约 | 交期 | 仓 |", "|---|---:|---:|---:|---|---|"]
            for it in d.get("items") or []:
                L.append(f"| `{it.get('item_code')}` | {it.get('qty')} | "
                         f"{it.get('delivered_qty')} | "
                         f"{max(0.0, float(it.get('qty') or 0) - float(it.get('delivered_qty') or 0)):.2f} | "
                         f"{str(it.get('delivery_date') or '')[:10]} | {it.get('warehouse')} |")
        else:
            L.append("- 行数较多，明细见 `order_examples.csv`；下表为按 target 汇总的净需求。")
        L += ["", "| target | rule | 库存(同仓) | PO(L30) | WO(L30) | L15 净 | L30 净 | L60 净 | L30 建议量 | 需要日 |",
              "|---|---|---|---:|---:|---|---|---|---|---|"]
        by_target = defaultdict(lambda: dict(stock=None, missing=False, po=0, wo=0,
                                             n15=0, n30=0, n60=0, need=""))
        for x in rr:
            t = by_target[x["target_item"]]
            t["rule"] = x["rule"]
            if x["stock"] is None:
                t["missing"] = True
            else:
                t["stock"] = x["stock"]
            t["po"] += x["po_L30"]
            t["wo"] += x["wo_L30"]
            for h in (15, 30, 60):
                v = x[f"net_L{h}"]
                if v is None:
                    t["missing"] = True
                else:
                    t[f"n{h}"] += v
            if x["unfulfilled"] > 0 and (not t["need"] or x["delivery_date"] < t["need"]):
                t["need"] = x["delivery_date"]
        for target, t in by_target.items():
            stock_s = "未取得" if t["stock"] is None else f"{t['stock']:.2f}"
            def fmt(v):
                return "待补证" if t["missing"] else f"{v:.2f}"
            need = t["need"] or ""
            if need and need < TODAY.isoformat():
                need = f"{TODAY.isoformat()}（原交期 {need} 已过）"
            L.append(f"| `{target}` | {t['rule']} | {stock_s} | {t['po']:.2f} | "
                     f"{t['wo']:.2f} | {fmt(t['n15'])} | {fmt(t['n30'])} | {fmt(t['n60'])} | "
                     f"**{fmt(t['n30'])}** | {need or '—'} |")
        L += ["", "- 假设：库存/PO/WO 为同仓可用；未共享预留；配套仅 BOM 唯一时成立。"]
        missing = []
        if any(x["stock"] is None for x in rr):
            missing.append("部分物料无 Bin 库存记录（记“未取得”，未按 0）")
        if any(x["rule"] == "规则未证" for x in rr):
            missing.append("部分成品无唯一 BOM（配套规则未证，不拆 PK#/ND#）")
        if not result["queries"]["po_ok"]:
            missing.append("PO 未取得（查询失败）")
        if not result["queries"]["wo_ok"]:
            missing.append("WO 未取得（查询失败）")
        L.append("- 缺证：" + ("；".join(missing) if missing else
                                "无（本算例所需证据在本轮范围内可取）"))
        L.append("")
    L += ["## 3. 能算到哪一步 / 缺什么", "",
          "- 能算：未履约量、按仓库存、已知 PO/在产（有日期者）、L15/L30/L60 净需求、"
          "BOM 唯一时的配套建议、按需要日的草稿数量。",
          "- 必须人工/补证：PO 到货日与去重、在产完工日、BOM 唯一性/版本、库存快照时点、"
          "MOQ/包装/成本、跨仓调拨规则；缺这些时只能出“待补证”草稿。",
          "- **不自动提交**：首期只出建议草稿，人工审批后才可下单。", "",
          "## 4. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/"
          "experiments/auto_order/order_examples.py",
          "uv run python scripts/check_secrets.py",
          "```", ""]
    (OUT / "order_examples.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote order_examples.md/csv; requests", c.gets, "examples", len(selected),
          "rows", len(rows), "stop", c.stop_reason)


if __name__ == "__main__":
    main()
