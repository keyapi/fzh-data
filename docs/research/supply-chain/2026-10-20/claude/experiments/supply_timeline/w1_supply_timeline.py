#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 供应时间线骨架（只读，SC14 字段口径）。

样本：2026-10-23 冻结的 9 个 SKU + 1 个缺额（不允许换样）。
数据：EN 生产只读 REST + 通途 MCP；不写、不下单、不改主数据。

关键口径（来自 jack-w1-answers / SC14 spec）：
- PO 与在途是两本账：都保留，`overlap_status` 标同批疑似；下游 B_min/B_max。
- 未知数量 qty=None + qty_status=unknown；绝不写 0。
- unknown 日期 available_date=None；estimated 需有日期；confirmed 需 date_proof。
- 一 DN 多号只出一行，tracking_numbers 列表，allocation_known=false。
- 外部 FBA scope=external_fba：rollup 两边都不算。
- WO produced_qty 只作 estimated remaining；JC sum_qty 放 production_progress。
- PK# 皮壳不 1:1 转成品；role/parent_sku 显式。
- SO 未履约是需求，单独输出，不进 supply 行。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent


def _find_root(start: Path) -> Path:
    for p in start.parents:
        if (p / "EN_API" / ".env").is_file() and (p / "tongtool_api").is_dir():
            return p
    raise SystemExit("repo root not found")


ROOT = _find_root(HERE)
sys.path.insert(0, str(ROOT))

COLUMNS = [
    "sku", "warehouse", "warehouse_id", "scope", "warehouse_scope", "warehouse_confidence",
    "warehouse_map_source", "warehouse_map_version", "as_of_date", "snapshot_id", "updated_at",
    "stage", "doc_type", "doc_name", "doc_line", "qty", "qty_status", "uom", "uom_proven",
    "event_date", "posting_date", "available_date", "date_confidence", "date_proof", "mode", "carrier",
    "tracking_numbers", "allocation_known", "tracking_qty", "batch_key", "overlap_status",
    "received_qty", "remaining_qty", "doc_qty", "received_booked", "received_evidenced", "received_source",
    "role", "parent_sku", "identity_confidence", "production_status", "production_progress",
    "conversion_assumed", "b_max_only", "production_conflict",
    "po_status", "po_status_semantics",
    "wo_creation", "wo_modified", "wo_state_as_of", "jc_as_of", "modified_after_as_of",
    "jc_first_op_sum", "jc_source",
    "source_key", "ledger", "notes", "counted",
]
SUPPLY_STAGES = ["on_hand", "po_open", "in_production", "shipped_in_transit", "received"]
SIGNED = {"已签收", "已上传POD", "已入仓"}
TRANSIT = {"已订舱", "已报关", "已离港", "已转运", "已到港", "清关中", "已清关"}
PO_OPEN = {"0", "1", "2"}
PO_STATUS = {"0": "waiting_arrival", "1": "partial_received_wait", "2": "partial_received_no_wait",
             "3": "received", "4": "unproven"}
KNOWN_UOMS = {"个", "套"}
DEST_MAP = {"CENTRADE": "美东-CENTRADE", "DANEEY": "美中-FZH-DANEEY",
            "波兰公司": "波兰-FZHPoland-covers"}


def load_env(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        values[k.strip()] = v.strip().strip("\"'")
    return values


def load_frozen_config(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(
            "frozen config not found: %s\n"
            "公开仓库只保留 schema + sha256；请把本地值文件放到该路径，或用 --config 指定。" % p)
    return json.loads(p.read_text(encoding="utf-8"))


def load_wo_audit(path):
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("wos", {})


def num(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def day(value):
    if not value:
        return None
    return str(value)[:10]


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def dedupe(rows, key="name"):
    seen, out = set(), []
    for row in rows:
        k = row.get(key)
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return out


def chunks(seq, n=40):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def jc_completed_qty(jc) -> float:
    if (jc.get("status") or "") != "Completed":
        return 0.0
    q = num(jc.get("total_completed_qty"))
    return q if q > 0 else num(jc.get("for_quantity"))


def wo_progress(wo, jcs) -> tuple[float, str, str]:
    ops = wo.get("operations") or []
    first = min(ops, key=lambda o: (o.get("sequence_id") or 0)) if ops else None
    if first:
        q = sum(jc_completed_qty(j) for j in jcs if j.get("operation") == first.get("operation"))
        if q > 0:
            return q, "jc_first_op", "first_op_sum"
    by_op = defaultdict(float)
    for j in jcs:
        by_op[j.get("operation")] += jc_completed_qty(j)
    if by_op:
        q = max(by_op.values())
        return q, "jc_max_op", "max_op_sum"
    if jcs:
        return 0.0, "jc_not_completed", ""
    return num(wo.get("produced_qty")), "wo_produced_qty", ""


def po_remaining(row) -> float:
    return max(num(row.get("quantity")) - num(row.get("in_quantity")), 0.0)


def role_of(item_code: str, meta: dict) -> tuple[str, str, str]:
    if item_code in meta:
        m = meta[item_code]
        return m["role"], m["sku"], m.get("identity_confidence", "derived")
    if not item_code:
        return "unknown", "", "unproven"
    if item_code.startswith("PK#"):
        return "cover", "", "derived"
    if item_code.startswith("ND#"):
        return "component", "", "derived"
    if item_code.startswith("KS"):
        return "finished", "", "derived"
    return "component", "", "derived"


class Cache:
    def __init__(self, root: Path, refresh: bool = False):
        self.root = root
        self.refresh = refresh
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, *parts) -> str:
        return hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def get(self, key: str):
        if self.refresh:
            return None
        p = self.root / (key + ".json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, key: str, value) -> None:
        (self.root / (key + ".json")).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class EnClient:
    def __init__(self, cache: Cache):
        import requests

        creds = load_env(ROOT / "EN_API" / ".env")
        key, secret = creds.get("PROD_ERP_API_KEY"), creds.get("PROD_ERP_API_SECRET")
        if not key or not secret:
            raise SystemExit("missing PROD_ERP_API_KEY/SECRET")
        self.base = "https://erpnext.vilavi.cn"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": "token %s:%s" % (key, secret), "Accept": "application/json"})
        self.cache = cache
        self.calls = 0

    def get_list(self, resource, filters, fields, order_by=None, page_len=200, max_pages=20):
        key = self.cache.key("en", resource, filters, fields, order_by, page_len)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        out = []
        for page in range(max_pages):
            params = {"filters": json.dumps(filters or [], ensure_ascii=False),
                      "fields": json.dumps(fields, ensure_ascii=False),
                      "limit_start": page * page_len, "limit_page_length": page_len}
            if order_by:
                params["order_by"] = order_by
            resp = self.session.get(self.base + "/api/resource/" + quote(resource), params=params, timeout=120)
            self.calls += 1
            if resp.status_code != 200:
                raise RuntimeError("%s HTTP %s: %s" % (resource, resp.status_code, resp.text[:300]))
            rows = resp.json().get("data") or []
            out.extend(rows)
            if len(rows) < page_len:
                break
        self.cache.put(key, out)
        return out

    def get_doc(self, doctype, name):
        key = self.cache.key("en-doc", doctype, name)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        resp = self.session.get(self.base + "/api/resource/%s/%s" % (quote(doctype), quote(name)), timeout=120)
        self.calls += 1
        if resp.status_code != 200:
            raise RuntimeError("%s/%s HTTP %s: %s" % (doctype, name, resp.status_code, resp.text[:300]))
        doc = resp.json().get("data") or {}
        self.cache.put(key, doc)
        return doc


class TongClient:
    def __init__(self, cache: Cache, interval: float = 13.0):
        self.client = None
        self.cache = cache
        self.interval = interval
        self.last_call = 0.0
        self.calls = 0

    def _ensure(self):
        if self.client is not None:
            return
        from tongtool_api.mcp_http import McpClient, primary_credentials

        key, secret = primary_credentials()
        self.client = McpClient(key, secret)

    @staticmethod
    def payload(resp: dict) -> dict:
        content = (resp.get("result") or {}).get("content") or []
        text = content[0].get("text") if content else ""
        if not text:
            raise RuntimeError("empty MCP response")
        data = json.loads(text)
        if str(data.get("code")) != "200":
            raise RuntimeError("Tongtool code %s: %s" % (data.get("code"), data.get("message")))
        return data

    def call(self, tool: str, args: dict) -> dict:
        key = self.cache.key("tong", tool, args)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        self._ensure()
        for attempt in range(4):
            wait = self.interval - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                data = self.payload(self.client.call(tool, args))
                self.last_call = time.monotonic()
                self.calls += 1
                self.cache.put(key, data)
                return data
            except Exception as exc:
                self.last_call = time.monotonic()
                if "526" in str(exc) and attempt < 3:
                    time.sleep(30 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("Tongtool retries exhausted")


# ── 取数 ────────────────────────────────────────────────────────────────
def fetch_stock(tong, warehouses, skus):
    rows = []
    for wh in warehouses:
        data = tong.call("erp2_stocks_stocksquery", {"warehouseName": wh, "skus": skus,
                                                    "pageNo": 1, "pageSize": 100})
        rows.extend((data.get("datas") or {}).get("array") or [])
    return rows


def fetch_pos(tong, skus, since, until):
    rows, page = [], 1
    while page <= 8:
        data = tong.call("erp2_purchase_purchaseorderquery", {
            "skus": skus, "purchaseDateFrom": since + " 00:00:00",
            "purchaseDateTo": until + " 23:59:59",
            "pageNo": page, "pageSize": 100})
        arr = (data.get("datas") or {}).get("array") or []
        rows.extend(arr)
        if len(arr) < 100:
            break
        page += 1
    return rows


def fetch_so_lines(en, skus, since, until):
    try:
        heads = en.get_list("Sales Order",
                            [["Sales Order Item", "customer_item_code", "in", skus],
                             ["docstatus", "=", 1], ["transaction_date", ">=", since],
                             ["transaction_date", "<=", until]],
                            ["name", "status", "docstatus", "transaction_date", "delivery_date",
                             "customer", "set_warehouse"], order_by="transaction_date desc")
    except Exception:
        heads = []
        for sku in skus:
            heads.extend(en.get_list("Sales Order",
                                     [["Sales Order Item", "customer_item_code", "like", "%" + sku + "%"],
                                      ["docstatus", "=", 1], ["transaction_date", ">=", since],
                                      ["transaction_date", "<=", until]],
                                     ["name", "status", "docstatus", "transaction_date", "delivery_date",
                                      "customer", "set_warehouse"], order_by="transaction_date desc"))
        heads = dedupe(heads, "name")
    out, seen = [], set()
    for head in heads:
        doc = en.get_doc("Sales Order", head["name"])
        for line in doc.get("items") or []:
            code = str(line.get("customer_item_code") or "")
            matched = [s for s in skus if code and (code == s or s.lower() in code.lower() or code.lower() in s.lower())]
            for sku in matched:
                key = (doc.get("name"), line.get("name"), sku)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"sku": sku, "so": doc.get("name"), "so_status": doc.get("status"),
                            "transaction_date": doc.get("transaction_date"),
                            "delivery_date": line.get("delivery_date") or doc.get("delivery_date"),
                            "item_code": line.get("item_code"), "item_name": line.get("item_name"),
                            "uom": line.get("uom"), "qty": num(line.get("qty")),
                            "delivered_qty": num(line.get("delivered_qty")),
                            "warehouse": line.get("warehouse") or doc.get("set_warehouse"),
                            "customer": doc.get("customer"), "line_id": line.get("name")})
    return out


def fetch_open_wos(en, items, since, until):
    if not items:
        return []
    heads = en.get_list("Work Order",
                        [["production_item", "in", items], ["docstatus", "=", 1],
                         ["creation", ">=", since], ["creation", "<=", until],
                         ["status", "not in", ["Completed", "Closed", "Stopped", "Cancelled"]]],
                        ["name", "status", "docstatus", "sales_order", "production_item", "qty",
                         "produced_qty", "planned_start_date", "planned_end_date", "bom_no",
                         "wip_warehouse", "fg_warehouse", "company"], order_by="planned_end_date asc")
    out = []
    for r in dedupe(heads, "name"):
        doc = en.get_doc("Work Order", r["name"])
        merged = dict(r)
        merged.update({"operations": doc.get("operations") or [],
                       "produced_qty": num(doc.get("produced_qty")),
                       "stock_uom": doc.get("stock_uom") or "",
                       "status": doc.get("status") or r.get("status")})
        out.append(merged)
    return out


def fetch_job_cards(en, wo_names):
    out = []
    for chunk in chunks(wo_names):
        out.extend(en.get_list("Job Card", [["work_order", "in", chunk], ["docstatus", "<", 2]],
                               ["name", "work_order", "operation", "status", "for_quantity",
                                "total_completed_qty", "actual_start_date", "actual_end_date"]))
    return out


def fetch_dn_lines(en, items, since, until):
    if not items:
        return []
    heads = en.get_list("Delivery Note",
                        [["Delivery Note Item", "item_code", "in", items], ["docstatus", "=", 1],
                         ["creation", ">=", since], ["creation", "<=", until + " 23:59:59"]],
                        ["name", "status", "docstatus", "posting_date", "customer", "company",
                         "is_return", "custom_zmt_shipment"])
    out = []
    for head in dedupe(heads, "name"):
        doc = en.get_doc("Delivery Note", head["name"])
        numbers = [r.get("logistic_number") for r in (doc.get("custom_zmt_logistic_numbers") or [])
                   if r.get("logistic_number")]
        for line in doc.get("items") or []:
            if line.get("item_code") not in items:
                continue
            out.append({"dn": doc.get("name"), "dn_status": doc.get("status"),
                        "posting_date": doc.get("posting_date"), "customer": doc.get("customer"),
                        "is_return": doc.get("is_return"), "item_code": line.get("item_code"),
                        "uom": line.get("uom"), "qty": num(line.get("qty")),
                        "warehouse": line.get("warehouse"), "line_id": line.get("name"),
                        "shipment": doc.get("custom_zmt_shipment"), "numbers": numbers})
    return out


def fetch_dn_lines_by_customer(en, skus, since, until):
    """按 customer_item_code 兜底拉 DN 行：覆盖状态缺失/组件行未映射到 item 的情况。"""
    if not skus:
        return []
    heads = en.get_list("Delivery Note",
                        [["Delivery Note Item", "customer_item_code", "in", skus],
                         ["docstatus", "=", 1], ["creation", ">=", since],
                         ["creation", "<=", until + " 23:59:59"]],
                        ["name", "status", "docstatus", "posting_date", "customer", "company",
                         "is_return", "custom_zmt_shipment"])
    out = []
    for head in dedupe(heads, "name"):
        doc = en.get_doc("Delivery Note", head["name"])
        numbers = [r.get("logistic_number") for r in (doc.get("custom_zmt_logistic_numbers") or [])
                   if r.get("logistic_number")]
        for line in doc.get("items") or []:
            out.append({"dn": doc.get("name"), "dn_status": doc.get("status"),
                        "posting_date": doc.get("posting_date"), "customer": doc.get("customer"),
                        "is_return": doc.get("is_return"), "item_code": line.get("item_code"),
                        "customer_item_code": line.get("customer_item_code"),
                        "uom": line.get("uom"), "qty": num(line.get("qty")),
                        "warehouse": line.get("warehouse"), "line_id": line.get("name"),
                        "shipment": doc.get("custom_zmt_shipment"), "numbers": numbers})
    return out


def fetch_shipments(en, numbers):
    numbers = [n for n in numbers if n]
    out = {}
    for chunk in chunks(numbers):
        rows = en.get_list("Shipment",
                           [["custom_zmt_logistic_number", "in", chunk]],
                           ["name", "custom_zmt_logistic_number", "custom_zmt_status11",
                            "custom_zmt_eta", "custom_zmt_atd", "custom_zmt_ata",
                            "custom_zmt_clr", "custom_zmt_dlvr", "custom_zmt_tracking",
                            "custom_zmt_transport", "custom_zmt_last_node",
                            "custom_zmt_match_status", "carrier"])
        for row in rows:
            out[row.get("custom_zmt_logistic_number")] = row
    return out


def fetch_shipments_by_name(en, names):
    out = {}
    for name in names:
        if name:
            doc = en.get_doc("Shipment", name)
            out[doc.get("name")] = doc
    return out


def fetch_receipts(en, items, warehouses, since, until):
    if not items or not warehouses:
        return []
    heads = en.get_list("Stock Entry",
                        [["Stock Entry Detail", "item_code", "in", items], ["docstatus", "=", 1],
                         ["posting_date", ">=", since], ["posting_date", "<=", until],
                         ["to_warehouse", "in", warehouses]],
                        ["name", "stock_entry_type", "posting_date", "to_warehouse", "from_warehouse",
                         "work_order", "purchase_order", "delivery_note_no", "purchase_receipt_no"],
                        order_by="posting_date desc")
    out = []
    for head in dedupe(heads, "name"):
        doc = en.get_doc("Stock Entry", head["name"])
        for line in doc.get("items") or []:
            if line.get("item_code") not in items:
                continue
            out.append({"name": doc.get("name"), "stock_entry_type": doc.get("stock_entry_type"),
                        "posting_date": doc.get("posting_date"), "to_warehouse": doc.get("to_warehouse"),
                        "from_warehouse": doc.get("from_warehouse"), "work_order": doc.get("work_order"),
                        "purchase_order": doc.get("purchase_order"),
                        "delivery_note_no": doc.get("delivery_note_no"),
                        "item_code": line.get("item_code"), "uom": line.get("uom"),
                        "qty": num(line.get("qty")), "line_id": line.get("name")})
    return out


# ── 行构造 ──────────────────────────────────────────────────────────────
def make_row(**kw):
    base = {c: "" for c in COLUMNS}
    base.update({
        "qty": None, "qty_status": "unknown", "available_date": None, "date_confidence": "unknown",
        "date_proof": "", "tracking_numbers": [], "allocation_known": 0, "tracking_qty": None,
        "batch_key": None, "overlap_status": "unknown", "received_qty": None,
        "remaining_qty": None, "doc_qty": None, "received_booked": 0, "received_evidenced": 0,
        "uom_proven": 0, "role": "unknown", "parent_sku": "", "identity_confidence": "unproven",
        "production_status": "", "production_progress": "", "counted": 0, "ledger": "",
        "conversion_assumed": 0, "b_max_only": 0, "production_conflict": 0,
    })
    base.update(kw)
    for b in ("allocation_known", "received_booked", "received_evidenced", "uom_proven", "counted",
              "conversion_assumed", "b_max_only", "production_conflict", "modified_after_as_of"):
        base[b] = 1 if base.get(b) else 0
    for d in ("event_date", "available_date"):
        if base.get(d) == "":
            base[d] = None
    if base.get("qty") == "":
        base["qty"] = None
    return base


def build(cfg, wmap, args, stock, pos, so_lines, wos, jcs, dn_lines, shipments, receipts):
    supply, demand, excluded, exceptions = [], [], [], []
    slots = [s for s in cfg["slots"] if s.get("sku")]
    skus = [s["sku"] for s in slots]
    slot_by_sku = {s["sku"]: s for s in slots}
    item_meta = {}
    for s in slots:
        for it in (s.get("items") or []) + (s.get("production_items") or []):
            item_meta[it["item_code"]] = {"sku": s["sku"], "role": it["role"],
                                           "identity_confidence": it.get("identity_confidence", "derived")}
    # 成品对应的皮壳 WO 物料：PK# + 成品码（sample10：WO production_item 全是 PK#）
    for s in slots:
        for it in s.get("items") or []:
            if it.get("role") == "finished":
                pk = "PK#" + it["item_code"]
                item_meta.setdefault(pk, {"sku": s["sku"], "role": "cover",
                                          "identity_confidence": "derived"})
    items = sorted(item_meta)
    for line in so_lines:
        if line.get("item_code") and line["item_code"] not in item_meta:
            role, parent, conf = role_of(line["item_code"], item_meta)
            item_meta[line["item_code"]] = {"sku": line.get("sku") or "", "role": role,
                                            "identity_confidence": conf}
    wh_by_name = {w["name"]: w for w in wmap["warehouses"]}
    fba = wmap["external_fba"]
    fzh = wmap["fzh"]
    stock_whs = [w["name"] for w in wmap["warehouses"]]
    run_tag = "w1:%s:%s" % (args.as_of, sha(cfg)[:8])
    snaps = cfg.get("snapshots", {})
    frozen_mode = getattr(args, "snapshot", "frozen") == "frozen"
    live_date = date.today().isoformat()
    stock_as_of = snaps.get("stock") if frozen_mode else live_date
    po_as_of = snaps.get("po") if frozen_mode else live_date
    wo_as_of = snaps.get("wo") if frozen_mode else live_date
    snap_tag = "frozen" if frozen_mode else "provisional_live"
    updated_at = datetime.now().isoformat(timespec="seconds")

    def whinfo(name):
        if name == fzh.get("warehouse"):
            w = dict(fzh)
            w["name"] = name
            w["warehouse_id"] = ""
            w.setdefault("warehouse_map_version", wmap["version"])
            return w
        if name == fba.get("warehouse"):
            w = dict(fba)
            w["name"] = name
            w["warehouse_id"] = ""
            w.setdefault("warehouse_map_version", wmap["version"])
            return w
        if name in wh_by_name:
            w = dict(wh_by_name[name])
            w.setdefault("warehouse_map_version", wmap["version"])
            return w
        return {"name": name, "warehouse_id": "", "scope": "in_house", "warehouse_scope": "unknown",
                "warehouse_confidence": "unmapped", "warehouse_map_source": "unmapped_en",
                "warehouse_map_version": wmap["version"], "en_finished": None}

    def base_fields(sku, wh, stage, doc_type, doc_name, doc_line, source_key, ledger,
                    snapshot_id, role="finished", parent_sku=None, identity="derived", as_of=None):
        w = whinfo(wh)
        return dict(sku=sku, warehouse=w.get("name", wh), warehouse_id=w.get("warehouse_id", ""),
                    scope=w.get("scope", "in_house"), warehouse_scope=w.get("warehouse_scope", "unknown"),
                    warehouse_confidence=w.get("warehouse_confidence", "unmapped"),
                    warehouse_map_source=w.get("warehouse_map_source", "unmapped"),
                    warehouse_map_version=w.get("warehouse_map_version", wmap["version"]),
                    as_of_date=as_of or args.as_of, snapshot_id=snapshot_id, updated_at=updated_at,
                    stage=stage, doc_type=doc_type, doc_name=doc_name, doc_line=doc_line,
                    source_key=source_key, ledger=ledger, role=role,
                    parent_sku=parent_sku if parent_sku is not None else sku,
                    identity_confidence=identity)

    # 1) 通途库存：on_hand / intransit / waiting 两本账
    stock_by_key = {}
    for r in stock:
        sku = str(r.get("goodsSku") or "").strip()
        if sku not in slot_by_sku:
            continue
        wh = r.get("warehouseName") or ""
        stock_by_key[(sku, wh)] = r
        f = base_fields(sku, wh, "on_hand", "Tongtool Stock", wh, sku,
                        "tongtool:stock:%s:%s:on_hand:%s" % (wh, sku, sha(r)[:8]), "stock",
                        "tongtool_stock_%s:%s" % (snap_tag, stock_as_of), as_of=stock_as_of)
        avail = num(r.get("availableStockQuantity"))
        supply.append(make_row(**f, qty=avail, qty_status="known", uom="", uom_proven=0,
                               event_date=stock_as_of, available_date=stock_as_of,
                               date_confidence="confirmed", date_proof="tongtool_stock_%s:%s" % (snap_tag, stock_as_of),
                               counted=1, notes="available; stock_snapshot=%s; source=%s" % (
                                   stock_as_of, snap_tag)))
        transit = num(r.get("intransitStockQuantity"))
        if transit > 0:
            f2 = base_fields(sku, wh, "shipped_in_transit", "Tongtool Stock", wh, sku,
                             "tongtool:stock:%s:%s:intransit:%s" % (wh, sku, sha(r)[:8]), "stock_intransit",
                             "tongtool_stock_%s:%s" % (snap_tag, stock_as_of), as_of=stock_as_of)
            supply.append(make_row(**f2, qty=transit, qty_status="known", uom="", uom_proven=0,
                                   counted=1, notes="通途在途聚合；ETA 未证"))
        waiting = num(r.get("waitingShipmentStockQuantity"))
        if waiting > 0:
            f2 = base_fields(sku, wh, "po_open", "Tongtool Stock", wh, sku,
                             "tongtool:stock:%s:%s:waiting:%s" % (wh, sku, sha(r)[:8]), "waiting",
                             "tongtool_stock_%s:%s" % (snap_tag, stock_as_of), as_of=stock_as_of)
            supply.append(make_row(**f2, qty=waiting, qty_status="known", uom="", uom_proven=0,
                                   counted=0, notes="waiting_shipment；与 PO 关系未证，不计入 B_min"))
        defects = num(r.get("defectsStockQuantity"))
        if defects > 0:
            excluded.append(base_fields(sku, wh, "on_hand", "Tongtool Stock", wh, sku,
                                        "tongtool:stock:%s:%s:defects" % (wh, sku), "defects",
                                        "tongtool_stock_%s:%s" % (snap_tag, stock_as_of), as_of=stock_as_of) | {
                "qty": defects, "qty_status": "known", "notes": "defects; not supply"})

    # 1b) 通途返回缺失的 SKU×仓：qty=null + unknown
    for sku in skus:
        for wh in stock_whs:
            if (sku, wh) in stock_by_key:
                continue
            f = base_fields(sku, wh, "on_hand", "Tongtool Stock", wh, sku,
                            "tongtool:stock:%s:%s:on_hand" % (wh, sku), "unknown",
                            "tongtool_stock_%s:%s" % (snap_tag, stock_as_of), as_of=stock_as_of)
            supply.append(make_row(**f, qty=None, qty_status="unknown", uom="", uom_proven=0,
                                   counted=0, notes=("stock_not_reported" if frozen_mode else "stock_not_listed") + "；未知不写 0"))

    # 2) 通途 PO：两本账都保留
    po_by_key = defaultdict(float)
    for p in pos:
        sku = str(p.get("goods_sku") or "").strip()
        if sku not in slot_by_sku:
            continue
        status = str(p.get("status") or "")
        bmax = bool(p.get("b_max_only"))
        if status not in PO_OPEN and not bmax:
            continue
        remaining = po_remaining(p)
        if remaining <= 0:
            continue
        wh = p.get("warehouseName") or ""
        if not bmax:
            po_by_key[(sku, wh)] += remaining
        will = day(p.get("willArriveDate"))
        f = base_fields(sku, wh, "po_open", "Tongtool PO", p.get("PONum") or "", p.get("goods_sku") or "",
                        "tongtool:po:%s:%s:%s:%s" % (p.get("PONum"), sku, wh, sha(p)[:8]),
                        "po_bmax" if bmax else "po",
                        "tongtool_po_%s:%s" % (snap_tag, po_as_of), as_of=po_as_of)
        mapped = f.get("warehouse_confidence") != "unmapped"
        supply.append(make_row(
            **f, qty=remaining, qty_status="known", uom="", uom_proven=0,
            event_date=day(p.get("purchaseDate")), available_date=will,
            date_confidence="estimated" if will else "unknown",
            date_proof=("po_will_arrive:%s" % p.get("PONum")) if will else "",
            counted=0 if (bmax or not mapped) else 1,
            b_max_only=1 if bmax else 0,
            po_status=status,
            po_status_semantics="unproven" if status == "4" else "",
            notes="status=%s(%s) qty=%s in_qty=%s%s" % (
                status, PO_STATUS.get(status, "?"), num(p.get("quantity")), num(p.get("in_quantity")),
                "；status=4 语义未证，仅进 B_max，不等同于已关闭" if bmax
                else ("" if mapped else "；warehouse_unmapped，不计入 B_min/B_max"))))

    # 2b) PO / 在途同量：两本账 + overlap_status；B_min 排除 PO
    for (sku, wh), po_qty in po_by_key.items():
        transit = num((stock_by_key.get((sku, wh)) or {}).get("intransitStockQuantity"))
        status = "unknown"
        if po_qty > 0 and transit > 0:
            status = "same_batch_suspected" if abs(po_qty - transit) < 1e-6 else "unknown"
        for r in supply:
            if r["sku"] == sku and r["warehouse"] == wh and r["stage"] in ("po_open", "shipped_in_transit"):
                if r["ledger"] == "po":
                    r["overlap_status"] = status
                    if status == "same_batch_suspected":
                        r["counted"] = 0
                        r["notes"] = (r["notes"] + "；与通途在途同量，B_min 排除，B_max 保留").strip("；")
                elif r["ledger"] == "stock_intransit":
                    r["overlap_status"] = status

    # 3) 在产：WO remaining = estimated；JC 作 progress；皮壳不 1:1 转成品
    jc_by_wo = defaultdict(list)
    for j in jcs:
        jc_by_wo[j.get("work_order")].append(j)
    for wo in wos:
        item = wo.get("production_item")
        meta = item_meta.get(item)
        if not meta:
            continue
        jc_done, jc_src, progress_src = wo_progress(wo, jc_by_wo.get(wo.get("name"), []))
        produced = num(wo.get("produced_qty"))
        qty_wo = num(wo.get("qty"))
        jc_first = wo.get("jc_first_op_sum")
        conflict = bool(wo.get("production_conflict")) or (produced == 0 and jc_done > qty_wo > 0)
        if conflict:
            exceptions.append(make_row(
                **base_fields(meta["sku"], fzh["warehouse"], "in_production", "Work Order",
                              wo.get("name"), item, "en:wo:%s:%s" % (wo.get("name"), item), "exception",
                              "en_wo_%s:%s" % (snap_tag, wo_as_of), role=meta["role"],
                              identity=meta["identity_confidence"], as_of=wo_as_of),
                qty=None, qty_status="unknown", uom=wo.get("stock_uom") or "",
                uom_proven=1 if (wo.get("stock_uom") in KNOWN_UOMS) else 0,
                production_status=wo.get("status") or "", production_conflict=1,
                production_progress="produced_qty=%.3f; jc_%s=%.3f%s" % (
                    produced, jc_src, jc_done,
                    ("; jc_first_op_sum=%.3f" % jc_first) if jc_first is not None else ""),
                wo_creation=wo.get("wo_creation") or "", wo_modified=wo.get("wo_modified") or "",
                wo_state_as_of=wo.get("wo_state_as_of") or "", jc_as_of=wo.get("jc_as_of") or "",
                modified_after_as_of=1 if wo.get("modified_after_as_of") else 0,
                jc_first_op_sum=jc_first, jc_source=wo.get("jc_source") or "",
                counted=0,
                notes="production_conflict：%s；不计供给" % (
                    wo.get("conflict_note") or "produced_qty=0 但 JC 首工序 %.3f > qty %.3f" % (jc_done, qty_wo))))
            continue
        # JQ-02：produced_qty 只作 estimated remaining；JC sum_qty 只作 progress，不改变 remaining
        remaining = max(qty_wo - produced, 0.0)
        if remaining <= 0:
            continue
        end = day(wo.get("planned_end_date"))
        f = base_fields(meta["sku"], fzh["warehouse"], "in_production", "Work Order", wo.get("name"),
                        item, "en:wo:%s:%s" % (wo.get("name"), item), "wo",
                        "en_wo_%s:%s" % (snap_tag, wo_as_of), role=meta["role"],
                        identity=meta["identity_confidence"], as_of=wo_as_of)
        supply.append(make_row(
            **f, qty=remaining, qty_status="estimated", uom=wo.get("stock_uom") or "",
            uom_proven=1 if (wo.get("stock_uom") in KNOWN_UOMS) else 0,
            event_date=end, available_date=end,
            date_confidence="estimated" if end else "unknown",
            date_proof=("wo_planned_end:%s" % wo.get("name")) if end else "",
            production_status=wo.get("status") or "",
            production_progress="produced_qty=%.3f; jc_%s=%.3f; jc=%d%s" % (
                produced, jc_src, jc_done, len(jc_by_wo.get(wo.get("name"), [])),
                ("; jc_first_op_sum=%.3f" % jc_first) if jc_first is not None else ""),
            wo_creation=wo.get("wo_creation") or "", wo_modified=wo.get("wo_modified") or "",
            wo_state_as_of=wo.get("wo_state_as_of") or "", jc_as_of=wo.get("jc_as_of") or "",
            modified_after_as_of=1 if wo.get("modified_after_as_of") else 0,
            jc_first_op_sum=jc_first, jc_source=wo.get("jc_source") or "",
            counted=1, conversion_assumed=1 if meta["role"] == "cover" else 0,
            notes="remaining estimated from produced_qty; JC 仅 progress；PK# 不 1:1 转成品" +
                  ("；conversion_assumed" if meta["role"] == "cover" else "") +
                  ("；sample10_wo_not_listed" if wo.get("sample10_wo_not_listed") else "")))

    # 4) SO 未履约：需求上下文，单独输出
    for line in so_lines:
        unfulfilled = max(line["qty"] - line["delivered_qty"], 0.0)
        if unfulfilled <= 0:
            continue
        meta = item_meta.get(line.get("item_code"), {})
        demand.append(make_row(
            sku=line["sku"], warehouse=line.get("warehouse") or "FZH", warehouse_id="",
            scope="in_house", warehouse_scope="own", warehouse_confidence="assumed",
            warehouse_map_source="en_so", warehouse_map_version=wmap["version"],
            as_of_date=snaps.get("stock", args.as_of), snapshot_id="en_so:%s" % snaps.get("stock", args.as_of),
            updated_at=updated_at,
            stage="so_unfulfilled", doc_type="Sales Order", doc_name=line["so"],
            doc_line=line["line_id"], qty=unfulfilled, qty_status="known", uom=line.get("uom") or "",
            uom_proven=1 if line.get("uom") in KNOWN_UOMS else 0,
            event_date=day(line.get("delivery_date")), date_confidence="unknown",
            role=meta.get("role", "finished"), parent_sku=line["sku"],
            identity_confidence=meta.get("identity_confidence", "derived"),
            source_key="en:so:%s:%s" % (line["so"], line["line_id"]), ledger="demand",
            counted=0, notes="SO status=%s qty=%s delivered=%s" % (
                line.get("so_status"), line["qty"], line["delivered_qty"])))

    # 5) DN/Shipment：一 DN 行一行；不按运单号复制数量
    for line in dn_lines:
        item = line.get("item_code")
        meta = item_meta.get(item)
        if not meta:
            code = str(line.get("customer_item_code") or "")
            sku_match = next((s for s in skus if code and (code == s or s.lower() in code.lower() or code.lower() in s.lower())), None)
            if not sku_match:
                continue
            role, _, conf = role_of(item, item_meta)
            meta = {"sku": sku_match, "role": role, "identity_confidence": conf}
        numbers = line.get("numbers") or ([line["shipment"]] if line.get("shipment") else [])
        ships = [shipments.get(n) for n in numbers if shipments.get(n)]
        customer = str(line.get("customer") or "")
        is_fba = "FBA" in customer
        dest = next((v for k, v in DEST_MAP.items() if k in customer), "")
        wh = fba["warehouse"] if is_fba else (dest or "unknown")
        scope = "external_fba" if is_fba else "in_house"
        signed = [s for s in ships if s.get("custom_zmt_dlvr") or str(s.get("custom_zmt_status11") or "").strip() in SIGNED]
        transit = [s for s in ships if str(s.get("custom_zmt_status11") or "").strip() in TRANSIT and s not in signed]
        unknown_ships = [s for s in ships if s not in signed and s not in transit]
        etas = sorted(day(s.get("custom_zmt_eta")) for s in transit if day(s.get("custom_zmt_eta")))
        dlvrs = sorted(day(s.get("custom_zmt_dlvr")) for s in signed if day(s.get("custom_zmt_dlvr")))
        common = dict(
            sku=meta["sku"], warehouse=wh, warehouse_id=whinfo(wh).get("warehouse_id", ""),
            scope=scope, warehouse_scope=("fba" if is_fba else whinfo(wh).get("warehouse_scope", "unknown")),
            warehouse_confidence=whinfo(wh).get("warehouse_confidence", "unmapped"),
            warehouse_map_source=whinfo(wh).get("warehouse_map_source", "unmapped"),
            warehouse_map_version=wmap["version"], as_of_date=snaps.get("stock", args.as_of),
            snapshot_id="en_dn:%s" % snaps.get("stock", args.as_of), updated_at=updated_at,
            doc_type="Delivery Note", doc_name=line["dn"], doc_line=line["line_id"],
            uom=line.get("uom") or "", uom_proven=1 if line.get("uom") in KNOWN_UOMS else 0,
            event_date=day(line.get("posting_date")), posting_date=day(line.get("posting_date")), mode="",
            carrier=", ".join(sorted({s.get("carrier") or "" for s in ships if s.get("carrier")})),
            tracking_numbers=numbers, allocation_known=0, tracking_qty=None,
            batch_key=None, role=meta["role"], parent_sku=meta["sku"],
            identity_confidence=meta["identity_confidence"],
            conversion_assumed=1 if meta["role"] == "cover" else 0,
            doc_qty=line["qty"],
        )
        if signed and not transit and not unknown_ships:
            supply.append(make_row(
                **common, stage="received", qty=None, qty_status="unknown",
                available_date=dlvrs[-1] if dlvrs else None,
                date_confidence="confirmed" if dlvrs else "unknown",
                date_proof=("shipment_dlvr:%s" % ",".join(s.get("name") or "" for s in signed)) if dlvrs else "",
                received_evidenced=1, received_source="shipment_signed", counted=0, ledger="received_evidenced",
                source_key="en:dn:%s:%s:received" % (line["dn"], line["line_id"]),
                notes="已签收到达；数量未证，已计入 on_hand，不重复计"))
        elif transit and not signed and not unknown_ships:
            supply.append(make_row(
                **common, stage="shipped_in_transit", qty=line["qty"], qty_status="known",
                available_date=etas[0] if etas else None,
                date_confidence="estimated" if etas else "unknown",
                date_proof=("shipment_eta:%s" % ",".join(s.get("name") or "" for s in transit)) if etas else "",
                counted=0, ledger="dn_trace",
                source_key="en:dn:%s:%s:transit" % (line["dn"], line["line_id"]),
                notes="Shipment 在途；trace_only，前瞻供给用通途在途，避免重复"))
        elif signed and transit:
            exceptions.append(make_row(
                **common, stage="partially_received", qty=None, qty_status="unknown",
                date_confidence="unknown", received_evidenced=1, received_source="shipment_partial",
                counted=0, ledger="exception",
                source_key="en:dn:%s:%s:partial" % (line["dn"], line["line_id"]),
                notes="多号部分签收，分配未知；SC14 需 partially_received + allocation_unknown"))
        else:
            # Q01：unknown 阶段可带 known qty，但日期必须 unknown；只进 supply_unknown
            supply.append(make_row(
                **common, stage="unknown", qty=line["qty"], qty_status="known",
                date_confidence="unknown", available_date=None, counted=0, ledger="unknown",
                source_key="en:dn:%s:%s:unknown" % (line["dn"], line["line_id"]),
                notes="无匹配 Shipment/状态缺失/混合未知；不猜在途也不猜已到"))

    # 6) Stock Entry 实收（若有）：单独 ledger，避免与 on_hand 重复
    for r in receipts:
        meta = item_meta.get(r.get("item_code"))
        if not meta:
            continue
        wh = next((w["name"] for w in wmap["warehouses"] if r.get("to_warehouse") == w.get("en_finished")), "")
        f = base_fields(meta["sku"], wh or (r.get("to_warehouse") or "unknown"), "received",
                        "Stock Entry", r.get("name"), r.get("line_id"),
                        "en:se:%s:%s:received" % (r.get("name"), r.get("line_id")), "received_booked",
                        "en_se:%s" % snaps.get("stock", args.as_of), role=meta["role"],
                        identity=meta["identity_confidence"], as_of=snaps.get("stock", args.as_of))
        supply.append(make_row(**f, qty=r.get("qty"), qty_status="known", uom=r.get("uom") or "",
                               uom_proven=1 if r.get("uom") in KNOWN_UOMS else 0,
                               event_date=day(r.get("posting_date")), posting_date=day(r.get("posting_date")),
                               available_date=day(r.get("posting_date")),
                               date_confidence="confirmed", date_proof="stock_entry:%s" % r.get("name"),
                               received_booked=1, received_source="stock_entry", received_qty=r.get("qty"),
                               doc_qty=r.get("qty"), counted=0,
                               notes="Stock Entry 实收；若已在 on_hand，不重复计"))

    # 映射风险标记 + 角色/转换假设（Q06/Q07）
    for r in supply:
        slot = slot_by_sku.get(r["sku"])
        if slot:
            slot_role = (slot.get("items") or [{}])[0].get("role", "finished")
            if r["role"] in ("finished", "unknown", ""):
                r["role"] = slot_role
            if slot_role == "cover":
                r["conversion_assumed"] = 1
                if "conversion_assumed" not in r["notes"]:
                    r["notes"] = (r["notes"] + "；conversion_assumed").strip("；")
            if slot.get("ambiguous") or slot.get("needs_business_review"):
                extra = ["mapping_ambiguous"] if slot.get("ambiguous") else []
                extra += ["mapping_needs_review"] if slot.get("needs_business_review") else []
                r["notes"] = (r["notes"] + "；" + "|".join(extra)).strip("；")

    return supply, demand, excluded, exceptions


def serialise(r):
    out = dict(r)
    if isinstance(out.get("tracking_numbers"), list):
        out["tracking_numbers"] = json.dumps(out["tracking_numbers"], ensure_ascii=False)
    for k in COLUMNS:
        if out.get(k) is None:
            out[k] = ""
    return out


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(serialise(r))


ALL_LEDGERS = ("stock", "wo", "stock_intransit", "po", "po_bmax", "received_booked")


def bridge_exclude_reason(row, mode):
    if row["ledger"] not in ALL_LEDGERS:
        return "not_in_ledger"
    if row["warehouse_confidence"] == "unmapped":
        return "unmapped"
    if row["scope"] == "external_fba":
        return "external_fba"
    if row["qty"] is None:
        return "qty_unknown"
    if mode == "min":
        if row["b_max_only"]:
            return "b_max_only"
        if row["ledger"] == "po" and not row["counted"]:
            return "po_not_counted"
        if row["role"] == "cover":       # Q07：B_min 只放已证转换
            return "cover_conversion_unproven"
    return ""


def build_bridge(supply):
    bucket = defaultdict(lambda: {"rows": 0, "qty": 0.0, "b_max": 0.0, "b_min": 0.0,
                                  "excluded_max": defaultdict(float),
                                  "excluded_min": defaultdict(float)})
    for r in supply:
        key = (r["ledger"] or "(none)", r["role"] or "(unknown)", r["uom"] or "(unknown)")
        b = bucket[key]
        b["rows"] += 1
        amount = num(r["qty"]) if r["qty"] is not None else 0.0
        b["qty"] += amount
        for mode in ("max", "min"):
            reason = bridge_exclude_reason(r, mode)
            if reason:
                b["excluded_" + mode][reason] += amount
            else:
                b["b_" + mode] += amount
    return [{"ledger": k[0], "role": k[1], "uom": k[2], "rows": v["rows"],
             "qty": round(v["qty"], 3), "b_max": round(v["b_max"], 3), "b_min": round(v["b_min"], 3),
             "b_max_excluded": {rk: round(rv, 3) for rk, rv in v["excluded_max"].items()},
             "b_min_excluded": {rk: round(rv, 3) for rk, rv in v["excluded_min"].items()}}
            for k, v in sorted(bucket.items())]


def build_po_bridge(supply):
    out = []
    for r in supply:
        if r["ledger"] != "po":
            continue
        out.append({
            "doc_name": r["doc_name"],
            "sku": r["sku"],
            "warehouse": r["warehouse"],
            "open_qty": r["qty"],
            "po_status": r["po_status"],
            "overlap_status": r["overlap_status"],
            "date_confidence": r["date_confidence"],
            "b_min": 0.0 if bridge_exclude_reason(r, "min") else num(r["qty"]),
            "b_max": 0.0 if bridge_exclude_reason(r, "max") else num(r["qty"]),
            "b_min_exclusion_reason": bridge_exclude_reason(r, "min"),
            "b_max_exclusion_reason": bridge_exclude_reason(r, "max"),
        })
    return out


def build_recon(cfg, args, supply, demand, excluded, exceptions, counts, en, tong):
    by_stage = defaultdict(lambda: {"rows": 0, "counted_rows": 0, "qty_by_uom": Counter()})
    for r in supply:
        b = by_stage[r["stage"]]
        b["rows"] += 1
        if r["counted"]:
            b["counted_rows"] += 1
        if r["qty"] is not None:
            b["qty_by_uom"][r["uom"] or "(unknown)"] += num(r["qty"])

    frozen_mode = getattr(args, "snapshot", "frozen") == "frozen"

    def ledger_sum(ledgers, mode):
        d = defaultdict(float)
        for r in supply:
            if r["ledger"] not in ledgers:
                continue
            if bridge_exclude_reason(r, mode):
                continue
            d[r["uom"] or "(unknown)"] += num(r["qty"])
        return dict(d)

    b_max = defaultdict(float)
    b_min = defaultdict(float)
    if frozen_mode:
        for ledger in ALL_LEDGERS:
            for u, q in ledger_sum([ledger], "max").items():
                b_max[u] += q
        for ledger in ALL_LEDGERS:
            for u, q in ledger_sum([ledger], "min").items():
                b_min[u] += q

    bridge = build_bridge(supply) if frozen_mode else []
    po_bridge = build_po_bridge(supply) if frozen_mode else []
    po_bridge_summary = {
        "rows": len(po_bridge),
        "open_qty": round(sum(num(x["open_qty"]) for x in po_bridge), 3),
        "by_reason": dict(Counter(x["b_min_exclusion_reason"] for x in po_bridge)),
        "by_overlap": dict(Counter(x["overlap_status"] for x in po_bridge)),
        "by_date_confidence": dict(Counter(x["date_confidence"] for x in po_bridge)),
    }
    if frozen_mode:
        for mode, totals in (("b_max", b_max), ("b_min", b_min)):
            for uom, expected in totals.items():
                got = sum(x[mode] for x in bridge if x["uom"] == uom)
                if abs(got - expected) > 1e-6:
                    raise AssertionError("bridge %s %s: %s != %s" % (mode, uom, got, expected))

    po_rows = [r for r in supply if r["ledger"] == "po"]
    overlap = [{"sku": r["sku"], "warehouse": r["warehouse"], "qty": r["qty"],
                "overlap_status": r["overlap_status"], "doc_name": r["doc_name"]}
               for r in po_rows if r["overlap_status"] == "same_batch_suspected"]
    unknown_rows = [r for r in supply if r["qty"] is None or r["date_confidence"] == "unknown"
                    or r["warehouse_confidence"] == "unmapped"]
    summary = defaultdict(lambda: defaultdict(lambda: Counter()))
    for r in supply:
        if r["counted"]:
            summary[(r["sku"], r["warehouse"])][r["stage"]][r["uom"] or "(unknown)"] += num(r["qty"])
    received_rows = [r for r in supply if r["ledger"] == "received_evidenced"]
    received_audit = {
        "rows": len(received_rows),
        "doc_lines": len({(r["doc_name"], r["doc_line"]) for r in received_rows}),
        "dns": sorted({r["doc_name"] for r in received_rows}),
        "per_sku": dict(Counter(r["sku"] for r in received_rows)),
        "doc_qty_sum": round(sum(num(r["doc_qty"]) for r in received_rows), 3),
        "posting_dates": sorted({r["event_date"] for r in received_rows if r["event_date"]}),
        "out_of_sample": 0,
        "out_of_sample_scope": "not_fetched_by_design",
        "note": "W1 只抓 9 SKU；SC04 的 6 张 received DN 中 1 张在样本内，5 张不在样本内且按设计不抓取",
    }
    return {
        "as_of": args.as_of,
        "since": args.since,
        "trace_since": args.trace_since,
        "snapshot_mode": "frozen" if frozen_mode else "provisional_live",
        "snapshot_expected": cfg.get("snapshots", {}),
        "stock_snapshot": (cfg.get("snapshots", {}).get("stock") if frozen_mode else date.today().isoformat()),
        "provisional_live": not frozen_mode,
        "snapshot_mismatch": not frozen_mode,
        "b_min_rule": "frozen only; exclude role=cover (conversion unproven), PO same_batch_suspected, b_max_only, unmapped, external_fba",
        "b_max_rule": "frozen only; include covers, all open PO incl. b_max_only; exclude unmapped/external_fba",
        "sample_version": cfg.get("version"),
        "sample_slots": len(cfg["slots"]),
        "sample_skus": len([s for s in cfg["slots"] if s.get("sku")]),
        "shortfalls": [s["slot"] for s in cfg["slots"] if s.get("status") == "shortfall"],
        "by_stage": {k: {"rows": v["rows"], "counted_rows": v["counted_rows"],
                         "qty_by_uom": dict(v["qty_by_uom"])} for k, v in by_stage.items()},
        "summary_by_sku_warehouse": {
            "%s|%s" % k: {stage: dict(uoms) for stage, uoms in v.items()}
            for k, v in summary.items()
        },
        "b_min": dict(b_min),
        "b_max": dict(b_max),
        "b_bridge": bridge,
        "b_bridge_po_summary": po_bridge_summary,
        "b_bridge_po": po_bridge,
        "received_audit": received_audit,
        "po_overlap_suspected": overlap,
        "unknown_rows": len(unknown_rows),
        "exceptions": len(exceptions),
        "excluded": len(excluded),
        "demand_rows": len(demand),
        "counts": counts,
        "inputs": {"sample_skus_sha": sha(cfg)[:16]},
        "en_calls": en.calls,
        "tong_calls": tong.calls,
        "boundaries": [
            "PO 与通途在途两本账都保留；same_batch_suspected 时 B_min 排除 PO，B_max 保留。",
            "qty=null + qty_status=unknown；未知不写 0。",
            "DN/Shipment 在途为 trace_only；前瞻供给用通途在途。",
            "received 仅证到达；实收数量未证，已计入 on_hand 的不重复。",
            "WO produced_qty 仅作 estimated remaining；JC 作 progress；PK# 不 1:1 转成品。",
            "仓库 EN 映射仍 assumed；未映射保留并进 unknown。",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="W1 supply timeline (SC14 schema, read-only)")
    ap.add_argument("--live", action="store_true", help="call EN; live snapshot also calls Tongtool")
    ap.add_argument("--snapshot", choices=["frozen", "live"], default="frozen",
                    help="frozen=10-22/10-20/10-19 官方基准；live=provisional_live")
    ap.add_argument("--config", default=str(HERE / "local" / "frozen_20261022.json"),
                    help="local-only frozen values file (public repo keeps only schema + sha256)")
    ap.add_argument("--wo-audit", default=str(HERE / "local" / "wo_audit_20261022.json"),
                    help="local-only WO audit metadata (optional)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--trace-since", default="2026-08-01")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--interval", type=float, default=13.0)
    args = ap.parse_args()

    cfg = json.loads((HERE / "config" / "sample_skus.json").read_text(encoding="utf-8"))
    wmap = json.loads((HERE / "config" / "warehouse_map.json").read_text(encoding="utf-8"))
    args.as_of = args.as_of or cfg.get("as_of") or date.today().isoformat()
    skus = [s["sku"] for s in cfg["slots"] if s.get("sku")]
    items = sorted({it["item_code"] for s in cfg["slots"]
                    for it in (s.get("items") or []) + (s.get("production_items") or [])})
    stock_whs = [w["name"] for w in wmap["warehouses"]]
    finished_whs = [w["en_finished"] for w in wmap["warehouses"] if w.get("en_finished")]
    snaps = cfg.get("snapshots", {})
    wo_items = sorted(set(items) | {"PK#" + i for i in items if i.startswith("KS")})
    frozen = load_frozen_config(args.config) if args.snapshot == "frozen" else None
    wo_audit = load_wo_audit(args.wo_audit) if frozen else {}

    cache = Cache(HERE / "cache", refresh=args.refresh)
    en = EnClient(cache)
    tong = TongClient(cache, interval=args.interval)
    stock, pos, wos, jcs = [], [], [], []
    so_lines, dn_lines, shipments, receipts = [], [], {}, []
    if args.live:
        if frozen:
            stock = [{"goodsSku": x["sku"], "warehouseName": x["warehouse"],
                      "availableStockQuantity": x["available"], "intransitStockQuantity": x["intransit"],
                      "waitingShipmentStockQuantity": x["waiting"], "defectsStockQuantity": x["defects"]}
                     for x in frozen["stock"]]
            pos = [{"goods_sku": x["sku"], "warehouseName": x["warehouse"], "PONum": x["ponum"],
                    "quantity": x["quantity"], "in_quantity": x["in_quantity"], "status": x["status"],
                    "willArriveDate": None, "b_max_only": x.get("b_max_only", False)}
                   for x in frozen["po"]]
            wos = [{"name": x["wo"], "production_item": x["item_code"], "qty": x["qty"],
                    "produced_qty": x["produced_qty"], "status": x["status"], "operations": [],
                    "stock_uom": "个", "production_conflict": x.get("production_conflict", False),
                    "conflict_note": x.get("conflict_note", ""),
                    "sample10_wo_not_listed": x.get("sample10_wo_not_listed", False),
                    "wo_creation": (wo_audit.get(x["wo"]) or {}).get("creation", ""),
                    "wo_modified": (wo_audit.get(x["wo"]) or {}).get("modified", ""),
                    "wo_state_as_of": (wo_audit.get(x["wo"]) or {}).get("wo_state_as_of", ""),
                    "jc_as_of": (wo_audit.get(x["wo"]) or {}).get("jc_as_of", ""),
                    "modified_after_as_of": (wo_audit.get(x["wo"]) or {}).get("modified_after_as_of", False),
                    "jc_first_op_sum": (wo_audit.get(x["wo"]) or {}).get("jc_first_op_sum"),
                    "jc_source": (wo_audit.get(x["wo"]) or {}).get("jc_source", "")}
                   for x in frozen["wo"]]
        else:
            stock = fetch_stock(tong, stock_whs, skus)
            pos = fetch_pos(tong, skus, args.since, snaps.get("po", args.as_of))
            wos = fetch_open_wos(en, wo_items, args.since, snaps.get("wo", args.as_of))
            jcs = fetch_job_cards(en, [w["name"] for w in wos]) if wos else []
        so_lines = fetch_so_lines(en, skus, args.since, snaps.get("stock", args.as_of))
        dn_by_item = fetch_dn_lines(en, items, args.trace_since, snaps.get("stock", args.as_of))
        dn_by_cust = fetch_dn_lines_by_customer(en, skus, args.trace_since, snaps.get("stock", args.as_of))
        merged = {}
        for line in dn_by_item + dn_by_cust:
            merged[(line.get("dn"), line.get("line_id"), line.get("item_code"))] = line
        dn_lines = list(merged.values())
        numbers = [n for l in dn_lines for n in (l.get("numbers") or [])]
        if not numbers:
            numbers = [l["shipment"] for l in dn_lines if l.get("shipment")]
        shipments = fetch_shipments(en, numbers) if numbers else {}
        names = [l["shipment"] for l in dn_lines if l.get("shipment") and l["shipment"] not in shipments]
        if names:
            shipments.update(fetch_shipments_by_name(en, names))
        receipts = fetch_receipts(en, items, finished_whs, args.trace_since,
                                  snaps.get("stock", args.as_of))

    supply, demand, excluded, exceptions = build(cfg, wmap, args, stock, pos, so_lines,
                                                 wos, jcs, dn_lines, shipments, receipts)
    counts = {"stock_rows": len(stock), "po_rows": len(pos), "so_lines": len(so_lines),
              "open_wos": len(wos), "job_cards": len(jcs), "dn_lines": len(dn_lines),
              "shipments": len(shipments), "receipts": len(receipts), "supply_rows": len(supply)}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "supply_timeline_rows.csv", supply)
    write_csv(out / "demand_context.csv", demand)
    write_csv(out / "excluded_nonsupply.csv", [make_row(**e) for e in excluded])
    write_csv(out / "exceptions.csv", exceptions)
    unknown_rows = [r for r in supply
                    if r["qty"] is None or r["qty_status"] == "unknown"
                    or r["date_confidence"] == "unknown"
                    or r["warehouse_confidence"] == "unmapped"
                    or r["stage"] == "unknown"] + exceptions
    write_csv(out / "unknowns.csv", unknown_rows)
    recon = build_recon(cfg, args, supply, demand, excluded, exceptions, counts, en, tong)
    (out / "recon.json").write_text(json.dumps(recon, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out / "b_bridge.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ledger", "role", "uom", "rows", "qty", "b_max", "b_min",
                    "b_max_excluded", "b_min_excluded"])
        for x in recon.get("b_bridge", []):
            w.writerow([x["ledger"], x["role"], x["uom"], x["rows"], x["qty"], x["b_max"], x["b_min"],
                        json.dumps(x["b_max_excluded"], ensure_ascii=False),
                        json.dumps(x["b_min_excluded"], ensure_ascii=False)])
    with (out / "b_bridge_po.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["doc_name", "sku", "warehouse", "open_qty", "po_status", "overlap_status",
                    "date_confidence", "b_min", "b_max", "b_min_exclusion_reason", "b_max_exclusion_reason"])
        for x in recon.get("b_bridge_po", []):
            w.writerow([x["doc_name"], x["sku"], x["warehouse"], x["open_qty"], x["po_status"],
                        x["overlap_status"], x["date_confidence"], x["b_min"], x["b_max"],
                        x["b_min_exclusion_reason"], x["b_max_exclusion_reason"]])
    with (out / "recon_by_sku_warehouse.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "warehouse", "stage", "uom", "qty"])
        for key, stages in recon["summary_by_sku_warehouse"].items():
            sku, wh = key.split("|", 1)
            for stage, uoms in stages.items():
                for uom, qty in uoms.items():
                    w.writerow([sku, wh, stage, uom, qty])
    print("W1_SUPPLY", len(supply), "DEMAND", len(demand), "EXCLUDED", len(excluded), "EXCEPTIONS", len(exceptions))
    print("W1_B_MIN", json.dumps(recon["b_min"], ensure_ascii=False), "B_MAX", json.dumps(recon["b_max"], ensure_ascii=False))
    print("W1_RECON", json.dumps({k: recon[k] for k in ("sample_skus", "shortfalls", "unknown_rows", "en_calls", "tong_calls")}, ensure_ascii=False))
    print("W1_OUT", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
