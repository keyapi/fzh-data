#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EN Sales Order reconnaissance (READ-ONLY, strict budget).

Purpose: give the automation work a factual base for SO structure, monthly
volume, a stratified sample, association coverage and first-order patterns.

Hard limits enforced in code
  * single-threaded, GET only;
  * <= 300 GET requests;
  * page_length <= 100 on every list call;
  * >= 200 ms between requests;
  * any timeout / 5xx / 408 stops the run immediately and writes partial output.

Credentials are read from EN_API/.env (parent repo) and never printed or
written to any artifact. Only aggregated numbers and necessary sample fields
are emitted; SO/customer identifiers are hashed.

Outputs: out/auto_order/so_profile.json, so_sample.csv, recon_report.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import requests

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]          # experiments/auto_order -> claude
OUT = CLAUDE_DIR / "out" / "auto_order"
ENV = Path("D:/Work/赛狐/Cursor/EN_API/.env")
BASE = "https://erpnext.vilavi.cn"
MAX_GETS = 300
SLEEP_S = 0.2
TIMEOUT_S = 20
PAGE = 50                              # <= 100
MONTHS = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)]
MONTHS = [m for m in MONTHS if "2024-10" <= m <= "2026-09"]   # 24 months
YEARS = ("2024", "2025", "2026")


def sha(x: str) -> str:
    return hashlib.sha256(str(x).encode("utf-8")).hexdigest()[:12]


def month_range(ym: str) -> tuple[str, str]:
    y, m = int(ym[:4]), int(ym[5:7])
    nxt = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{ym}-01", f"{nxt[0]}-{nxt[1]:02d}-01"


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()
    return env


class StopRun(Exception):
    pass


class Client:
    def __init__(self, base: str, key: str, secret: str):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"token {key}:{secret}",
                               "Accept": "application/json"})
        self.gets = 0
        self.by_path = Counter()
        self.started = time.time()
        self.last = 0.0
        self.stop_reason = None
        self.errors = []

    def get(self, path: str, params: dict | None = None):
        if self.gets >= MAX_GETS:
            self.stop_reason = f"request_cap({MAX_GETS})"
            raise StopRun(self.stop_reason)
        wait = SLEEP_S - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.gets += 1
        bucket = path
        for dt in ("Sales Order", "Delivery Plan"):
            if path.startswith(f"/api/resource/{dt}/"):
                bucket = f"/api/resource/{dt}/<doc>"
        self.by_path[bucket] += 1
        self.last = time.time()
        try:
            r = self.s.get(self.base + path, params=params, timeout=TIMEOUT_S)
        except Exception as exc:
            self.stop_reason = f"timeout/connection:{type(exc).__name__}"
            self.errors.append(self.stop_reason)
            raise StopRun(self.stop_reason)
        if r.status_code in (408, 500, 502, 503, 504) or r.status_code >= 500:
            self.stop_reason = f"http_{r.status_code}"
            self.errors.append(f"{path} -> {r.status_code}")
            raise StopRun(self.stop_reason)
        if r.status_code in (401, 403):
            self.stop_reason = f"auth_{r.status_code}"
            self.errors.append(f"{path} -> {r.status_code}")
            raise StopRun(self.stop_reason)
        if r.status_code == 404:
            return None
        try:
            return r.json()
        except Exception:
            return None

    def report(self) -> dict:
        return dict(requests=self.gets, cap=MAX_GETS, interval_s=SLEEP_S,
                    page_length_max=100, elapsed_s=round(time.time() - self.started, 1),
                    by_path=dict(self.by_path), stop_reason=self.stop_reason,
                    errors=self.errors)


def month_counts(c: Client) -> list[dict]:
    out = []
    for ym in MONTHS:
        lo, hi = month_range(ym)
        flt = json.dumps([["transaction_date", ">=", lo],
                          ["transaction_date", "<", hi]])
        res = c.get("/api/method/frappe.client.get_list",
                    {"doctype": "Sales Order",
                     "fields": json.dumps(["docstatus", "count(name) as cnt"]),
                     "group_by": "docstatus", "filters": flt,
                     "limit_page_length": 0})
        rows = (res or {}).get("message", []) if isinstance(res, dict) else []
        dist = {str(r.get("docstatus")): int(r.get("cnt") or 0) for r in rows}
        temp = c.get("/api/method/frappe.client.get_count",
                     {"doctype": "Sales Order", "filters": flt})
        total = int((temp or {}).get("message") or 0) if isinstance(temp, dict) else sum(dist.values())
        out.append(dict(month=ym, total=total,
                        docstatus={k: dist.get(k, 0) for k in ("0", "1", "2")}))
    # partial current month, excluded from the 24-month table
    lo, hi = "2026-10-01", "2026-11-01"
    flt = json.dumps([["transaction_date", ">=", lo], ["transaction_date", "<", hi]])
    res = c.get("/api/method/frappe.client.get_list",
                {"doctype": "Sales Order",
                 "fields": json.dumps(["docstatus", "count(name) as cnt"]),
                 "group_by": "docstatus", "filters": flt, "limit_page_length": 0})
    rows = (res or {}).get("message", []) if isinstance(res, dict) else []
    out.append(dict(month="2026-10", partial=True,
                    total=sum(int(r.get("cnt") or 0) for r in rows),
                    docstatus={str(r.get("docstatus")): int(r.get("cnt") or 0)
                               for r in rows}))
    return out


def structure_probe(c: Client) -> dict:
    # two recent SOs, full document
    lst = c.get("/api/resource/Sales Order",
                {"fields": json.dumps(["name"]), "limit_page_length": 2,
                 "order_by": "modified desc"})
    names = [x["name"] for x in (lst or {}).get("data", [])]
    docs = []
    for n in names:
        d = c.get(f"/api/resource/Sales Order/{n}")
        if d and d.get("data"):
            docs.append(d["data"])
    # custom fields on SO / SO Item
    cf = c.get("/api/resource/Custom Field",
               {"fields": json.dumps(["dt", "fieldname", "label", "fieldtype", "options"]),
                "filters": json.dumps([["dt", "in", ["Sales Order", "Sales Order Item"]]]),
                "limit_page_length": 100, "order_by": "dt asc, fieldname asc"})
    custom = (cf or {}).get("data", []) if isinstance(cf, dict) else []
    # observed doctypes related to delivery / scanning (names only)
    dt = c.get("/api/resource/DocType",
               {"fields": json.dumps(["name"]), "limit_page_length": 50,
                "filters": json.dumps([["name", "like", "%Delivery%"]])})
    deliv_dts = [x["name"] for x in (dt or {}).get("data", [])] if isinstance(dt, dict) else []
    # Delivery Plan probe: one document, field names only (if the doctype exists)
    dp = {}
    if "Delivery Plan" in deliv_dts:
        lst = c.get("/api/resource/Delivery Plan",
                    {"fields": json.dumps(["name"]), "limit_page_length": 1,
                     "order_by": "name asc"})
        names = [x["name"] for x in (lst or {}).get("data", [])]
        if names:
            d = c.get(f"/api/resource/Delivery Plan/{names[0]}")
            if d and d.get("data"):
                doc = d["data"]
                dp = dict(dp_hash=sha(doc.get("name", "")), keys=sorted(doc.keys()),
                          item_keys=sorted((doc.get("items") or [{}])[0].keys()),
                          relevant=rel_fields(doc.keys()),
                          link_fields=sorted(k for k in doc
                                             if any(t in k.lower() for t in
                                                    ("sale", "so_", "dn", "scan", "qr"))))
    return dict(sample_sos=[dict(so_hash=sha(d.get("name", "")),
                                 keys=sorted(d.keys()),
                                 item_keys=sorted((d.get("items") or [{}])[0].keys()))
                            for d in docs],
                custom_fields=[dict(dt=x.get("dt"), fieldname=x.get("fieldname"),
                                    label=x.get("label"), fieldtype=x.get("fieldtype"),
                                    options=x.get("options")) for x in custom],
                delivery_related_doctypes=deliv_dts,
                delivery_plan_probe=dp,
                note="只记录实测字段名；不猜测字段含义")


def sample_names(c: Client, companies: list[str]) -> dict:
    picked = defaultdict(list)
    for y in YEARS:
        lo, hi = f"{y}-01-01", f"{int(y)+1}-01-01"
        for comp in companies:
            flt = json.dumps([["transaction_date", ">=", lo],
                              ["transaction_date", "<", hi],
                              ["company", "=", comp]])
            res = c.get("/api/resource/Sales Order",
                        {"fields": json.dumps(["name"]),
                         "filters": flt, "limit_page_length": 20,
                         "order_by": "name asc"})
            names = [x["name"] for x in (res or {}).get("data", [])]
            picked[(y, comp)] = names
    # snapshot the original stratum sizes (picked is consumed below)
    strata_counts = {f"{y}|{comp}": len(v) for (y, comp), v in picked.items()}
    selected, seen = [], set()
    keys = list(picked)
    i = 0
    while len(selected) < PAGE and any(picked[k] for k in keys):
        k = keys[i % len(keys)]
        if picked[k]:
            n = picked[k].pop(0)
            if n not in seen:
                seen.add(n)
                selected.append((k[0], k[1], n))
        i += 1
    backfill = 0
    # if the company strata are sparse, backfill by year (no company filter)
    if len(selected) < PAGE:
        for y in YEARS:
            need = PAGE - len(selected)
            if need <= 0:
                break
            flt = json.dumps([["transaction_date", ">=", f"{y}-01-01"],
                              ["transaction_date", "<", f"{int(y)+1}-01-01"]])
            res = c.get("/api/resource/Sales Order",
                        {"fields": json.dumps(["name", "company"]), "filters": flt,
                         "limit_page_length": min(100, need + 20),
                         "order_by": "name asc"})
            for x in (res or {}).get("data", []):
                n = x["name"]
                if len(selected) >= PAGE:
                    break
                if n not in seen:
                    seen.add(n)
                    selected.append((y, x.get("company") or "", n))
                    backfill += 1
    return dict(selected=selected, strata=strata_counts, backfill=backfill)


def fetch_docs(c: Client, picked: list[tuple[str, str, str]]) -> list[dict]:
    docs = []
    for year, comp, name in picked:
        d = c.get(f"/api/resource/Sales Order/{name}")
        if d and d.get("data"):
            doc = d["data"]
            doc["_year"] = year
            doc["_company"] = comp
            docs.append(doc)
    return docs


RELEVANT = ("deliver", "ship", "scan", "plan", "code", "qr", "status",
            "pack", "pick", "cover", "inner", "warehouse", "pair", "dispatch")


def rel_fields(keys) -> list[str]:
    return sorted(k for k in keys if any(t in k.lower() for t in RELEVANT))


def analyse(docs: list[dict]) -> dict:
    header_keys = sorted({k for d in docs for k in d})
    item_keys = sorted({k for d in docs for it in (d.get("items") or []) for k in it})
    header_nonempty = {}
    for f in rel_fields(header_keys):
        vals = [d.get(f) for d in docs]
        header_nonempty[f] = dict(present=sum(1 for v in vals if v is not None),
                                  nonempty=sum(1 for v in vals
                                               if v not in (None, "", 0, [], {})))
    item_nonempty = {}
    for f in rel_fields(item_keys):
        vals = [it.get(f) for d in docs for it in (d.get("items") or [])]
        item_nonempty[f] = dict(present=len(vals),
                                nonempty=sum(1 for v in vals
                                             if v not in (None, "", 0, [], {})))

    pairs = Counter()
    lines, qtys, o2d = [], [], []
    status = Counter()
    unshipped = overdue = so_total = 0
    today = date(2026, 10, 22)
    for d in docs:
        items = d.get("items") or []
        lines.append(len(items))
        codes = [it.get("item_code") or "" for it in items]
        has_cover = any(c.startswith("PK#") for c in codes)
        has_inner = any(c.startswith("ND#") for c in codes)
        pairs["both" if has_cover and has_inner else
              "cover_only" if has_cover else
              "inner_only" if has_inner else "neither"] += 1
        status[str(d.get("status"))] += 1
        if d.get("docstatus") == 1:
            so_total += 1
            pd = d.get("per_delivered")
            if pd is not None and float(pd) < 100:
                unshipped += 1
        for it in items:
            if it.get("qty") is not None:
                qtys.append(float(it["qty"]))
            if it.get("delivery_date") and d.get("transaction_date"):
                try:
                    a = datetime.strptime(it["delivery_date"][:10], "%Y-%m-%d").date()
                    b = datetime.strptime(d["transaction_date"][:10], "%Y-%m-%d").date()
                    o2d.append((a - b).days)
                except Exception:
                    pass
                if d.get("docstatus") == 1 and d.get("per_delivered") is not None \
                        and float(d.get("per_delivered")) < 100:
                    try:
                        a = datetime.strptime(it["delivery_date"][:10], "%Y-%m-%d").date()
                        if a < today:
                            overdue += 1
                    except Exception:
                        pass
    q = sorted(qtys)
    def pct(p):
        return round(q[min(len(q) - 1, int(len(q) * p))], 2) if q else None
    return dict(
        sample=dict(so=len(docs), items=sum(lines),
                    companies=dict(Counter(d.get("_company") for d in docs)),
                    years=dict(Counter(d.get("_year") for d in docs)),
                    warehouses=dict(Counter(it.get("warehouse")
                                            for d in docs for it in (d.get("items") or []))),
                    docstatus=dict(Counter(str(d.get("docstatus")) for d in docs))),
        association=dict(header=header_nonempty, item=item_nonempty,
                         note="仅样本内 present/nonempty 计数，不推测全量覆盖率"),
        patterns=dict(
            pairing=dict(pairs),
            lines_per_so=dict(min=min(lines) if lines else None,
                              median=statistics.median(lines) if lines else None,
                              max=max(lines) if lines else None),
            qty_per_line=dict(n=len(q), p10=pct(0.1), p50=pct(0.5), p90=pct(0.9),
                              max=max(q) if q else None),
            order_to_delivery_days=dict(n=len(o2d),
                                        median=statistics.median(o2d) if o2d else None,
                                        min=min(o2d) if o2d else None,
                                        max=max(o2d) if o2d else None),
            unshipped=dict(so_total=so_total, unshipped=unshipped,
                           ratio=(round(unshipped / so_total, 4) if so_total else None)),
            overdue_unshipped_item_rows=overdue,
            status=dict(status)),
        note="只描述样本内看到的事实；不下单、不推断全量")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ENV))
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = load_env(Path(args.env))
    c = Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])
    structure, monthly, sample_meta, docs = {}, [], {}, []
    try:
        comp = c.get("/api/resource/Company",
                     {"fields": json.dumps(["name"]), "limit_page_length": 50})
        companies = [x["name"] for x in (comp or {}).get("data", [])]
        structure = structure_probe(c)
        monthly = month_counts(c)
        sample_meta = sample_names(c, companies)
        docs = fetch_docs(c, sample_meta["selected"])
    except StopRun:
        pass

    analysis = analyse(docs) if docs else {}
    result = dict(
        schema_version="en_so_recon/1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        base_url=args.base,
        budget=c.report(),
        structure=structure,
        companies=companies if "companies" in locals() else [],
        monthly=monthly,
        months_expected=MONTHS,
        sample_requested=dict(plan=("3 years x companies, up to 20 names per stratum, "
                                    "round-robin to 50; year backfill if company strata are sparse"),
                              strata=sample_meta.get("strata", {}),
                              backfill=sample_meta.get("backfill", 0),
                              selected=len(docs)),
        analysis=analysis,
        facts=[
            ("结构：SO header 实测含 delivery_date/delivery_status/per_delivered/status 等；"
             "Delivery Plan 是独立 doctype，header 含 sale_orders、item 含 sales_order/so_detail；"
             "SO/Item/Delivery Plan 均未发现 scan/qr 字段"),
            (f"月度：2024-10..2026-09 共 {sum(m['total'] for m in monthly if not m.get('partial'))} 单；"
             f"零单月份：{ [m['month'] for m in monthly if not m.get('partial') and m['total']==0] }；"
             f"2026-10 部分月 {next((m['total'] for m in monthly if m.get('partial')), 0)} 单"),
            (f"样本：{analysis.get('sample', {}).get('so')} 单 / "
             f"{analysis.get('sample', {}).get('items')} 行；"
             f"配对 {analysis.get('patterns', {}).get('pairing')}；"
             f"未发货 {analysis.get('patterns', {}).get('unshipped')}；"
             f"交期代理 {analysis.get('patterns', {}).get('order_to_delivery_days')}"),
        ],
        limits=["只读 GET；无写入", "样本内计数，不外推全量",
                "不猜测字段含义/不写下单建议"],
    )
    (OUT / "so_profile.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    fields = ["so_hash", "year", "company", "docstatus", "status",
              "transaction_date", "per_delivered", "delivery_status",
              "customer_hash", "line_idx", "item_code", "qty",
              "delivery_date", "warehouse", "delivered_qty",
              "is_cover", "is_inner"]
    with (OUT / "so_sample.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for d in docs:
            for i, it in enumerate(d.get("items") or [{}]):
                code = it.get("item_code") or ""
                w.writerow(dict(
                    so_hash=sha(d.get("name", "")), year=d.get("_year"),
                    company=d.get("_company"), docstatus=d.get("docstatus"),
                    status=d.get("status"), transaction_date=d.get("transaction_date"),
                    per_delivered=d.get("per_delivered"),
                    delivery_status=d.get("delivery_status"),
                    customer_hash=sha(d.get("customer") or ""),
                    line_idx=i, item_code=code, qty=it.get("qty"),
                    delivery_date=it.get("delivery_date"),
                    warehouse=it.get("warehouse"),
                    delivered_qty=it.get("delivered_qty"),
                    is_cover=code.startswith("PK#"), is_inner=code.startswith("ND#")))

    # report
    L = ["# EN 销售订单（SO）代表性侦察", "",
         "> 只读 GET；预算：单线程、≤300 次、page_length ≤100、间隔 ≥200ms。",
         "> 只写看到的字段/数字；不猜测含义、不写“应如何下单”。", "",
         "## 1. 预算与请求", "",
         f"- 请求 **{c.gets}** 次（上限 300）；耗时 **{result['budget']['elapsed_s']} s**；"
         f"停止原因：{c.stop_reason or '无（正常完成）'}",
         f"- 按路径：{dict(c.by_path)}", ""]
    if c.errors:
        L += ["- 错误："] + [f"  - {e}" for e in c.errors] + [""]
    L += ["## 2. 结构与字段（实测）", ""]
    if structure.get("sample_sos"):
        L += ["- 样本 SO 的 header 字段数 / item 字段数："
              + "；".join(f"{x['so_hash']} header {len(x['keys'])} / item {len(x['item_keys'])}"
                          for x in structure["sample_sos"])]
        rel = rel_fields(structure["sample_sos"][0]["keys"])
        L += ["- header 中与发货/计划/扫码相关的实测字段："
              + (", ".join(f"`{x}`" for x in rel) or "未发现")]
    if structure.get("custom_fields"):
        L += ["- Custom Field（Sales Order / Sales Order Item，最多 100 条）：", "",
              "| dt | fieldname | label | fieldtype | options |", "|---|---|---|---|---|"]
        for x in structure["custom_fields"][:40]:
            L.append(f"| {x['dt']} | `{x['fieldname']}` | {x['label']} | "
                     f"{x['fieldtype']} | {x['options'] or ''} |")
    if structure.get("delivery_related_doctypes"):
        L += ["", f"- 名称含 Delivery 的 doctype：{structure['delivery_related_doctypes']}"]
    dp = structure.get("delivery_plan_probe") or {}
    if dp:
        L += ["", f"- `Delivery Plan` 单条实测：`{dp.get('dp_hash')}`，"
                  f"header {len(dp.get('keys', []))} 字段 / item {len(dp.get('item_keys', []))} 字段；"
                  f"相关字段：{dp.get('relevant')}；"
                  f"关联键候选：{dp.get('link_fields')}"]
    L += ["", "## 3. 月度规模（2024-10..2026-09，24 个月）", "",
          "| 月份 | 总数 | draft(0) | submitted(1) | cancelled(2) |",
          "|---|---:|---:|---:|---:|"]
    for m in monthly:
        if m.get("partial"):
            continue
        L.append(f"| {m['month']} | {m['total']} | {m['docstatus'].get('0', 0)} | "
                 f"{m['docstatus'].get('1', 0)} | {m['docstatus'].get('2', 0)} |")
    part = next((m for m in monthly if m.get("partial")), None)
    if part:
        L += ["", f"- 2026-10 为**部分月**（截至扫描日），不计入 24 个月：总数 {part['total']}，"
                  f"docstatus {part['docstatus']}。"]
    L += ["", "## 4. 代表性样本（50 条，分层）", "",
          f"- 分层：3 年 × {len(result['companies'])} 家公司，每层最多 20 条，轮转取 50；"
          f"公司层不足时按年回填（回填 {sample_meta.get('backfill', 0)} 条）。",
          f"- 实际取得 **{len(docs)}** 条；样本构成：{analysis.get('sample', {})}", "",
          "## 5. 关联覆盖（仅样本内）", ""]
    assoc = analysis.get("association", {})
    if assoc:
        L += ["| 位置 | 字段 | present | nonempty |", "|---|---|---:|---:|"]
        for loc in ("header", "item"):
            for f, v in (assoc.get(loc) or {}).items():
                L.append(f"| {loc} | `{f}` | {v['present']} | {v['nonempty']} |")
        L += ["", f"- {assoc.get('note')}"]
    L += ["", "## 6. 模式初判（样本内数字）", ""]
    p = analysis.get("patterns", {})
    if p:
        L += [f"- 皮壳/内胆配对：{p['pairing']}",
              f"- 每单行数：{p['lines_per_so']}",
              f"- 单行数量：{p['qty_per_line']}",
              f"- 下单→交期天数（代理）：{p['order_to_delivery_days']}",
              f"- 未发货（submitted 且 per_delivered<100）：{p['unshipped']}",
              f"- 已过交期且未发（item 行）：{p['overdue_unshipped_item_rows']}",
              f"- 状态分布：{p['status']}"]
    L += ["", "## 7. 看到 / 看不到", "",
          "- 看到：SO header/item 的实际字段名；`Delivery Plan` 是独立 doctype，header 有 "
          "`sale_orders`、item 有 `sales_order`/`so_detail`（可作 SO↔出库计划关联键）；"
          "24 个月 SO 数量与 docstatus；50 条样本的 items、发货字段与样本内模式数字。",
          "- 看不到：字段的业务含义（只测到存在与取值）、全量覆盖率（样本内计数）、"
          "SO 文档内没有直接的 Delivery Plan 链接字段；**SO / SO Item / Delivery Plan 实测量"
          "均未出现 scan/qr 字段**，扫码关联未在本轮看到。",
          "- 本报告不给出下单建议，也不推断未观测到的关系。", "",
          "## 8. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/recon_so.py",
          "uv run python scripts/check_secrets.py",
          "```", "",
          "凭证从 `EN_API/.env` 读取，未打印/未落盘；输出只含哈希 id 与必要字段。", ""]
    (OUT / "recon_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print("wrote", OUT.name, "requests", c.gets, "docs", len(docs),
          "stop", c.stop_reason)


if __name__ == "__main__":
    main()
