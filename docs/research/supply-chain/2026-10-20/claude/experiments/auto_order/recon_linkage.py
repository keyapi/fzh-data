#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EN Sales Order linkage & policy timeline reconnaissance (READ-ONLY).

Budget: single-threaded GET only, <=200 requests, page_length <=100,
>=200 ms interval, stop on timeout / 5xx.

Segments
  A 2024-11 .. 2025-05   (start-up)
  B 2025-06 .. 2025-12   (delivery_plan period)
  C 2026-01 .. 2026-06   (scan linkage + policy switch)
  D 2026-07 .. 2026-10   (recent)

What is full vs sample
  * SO counts, cancelled ratio, submitted per_delivered<100 ratio and
    type_of_manufacturing distributions: FULL population of each segment
    (header list, paginated).
  * Delivery Plan linkage, item-level policy fields and cover/inner pairing:
    SAMPLE of up to 15 SOs per segment (first 15 by name asc), because the
    item/DP queries are per-SO. This is stated everywhere it is used.
  * DP->DN status uses the sampled linked Delivery Plans only.

Outputs: out/auto_order/linkage_profile.json, policy_timeline.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import requests

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "auto_order"
ENV = Path("D:/Work/赛狐/Cursor/EN_API/.env")
BASE = "https://erpnext.vilavi.cn"
MAX_GETS = 200
SLEEP_S = 0.2
TIMEOUT_S = 20
PAGE = 100
SAMPLE_PER_SEG = 15
SEGMENTS = [
    ("A", "2024-11-01", "2025-06-01", "2024-11..2025-05"),
    ("B", "2025-06-01", "2026-01-01", "2025-06..2025-12"),
    ("C", "2026-01-01", "2026-07-01", "2026-01..2026-06"),
    ("D", "2026-07-01", "2026-11-01", "2026-07..2026-10"),
]
POLICY_RE = re.compile(r"approv|price|discount|rate|credit|limit|authoriz", re.I)


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
        for dt in ("Sales Order", "Sales Order Item", "Delivery Plan",
                   "Delivery Plan Item"):
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

    def report(self):
        return dict(requests=self.gets, cap=MAX_GETS, interval_s=SLEEP_S,
                    page_length_max=PAGE, elapsed_s=round(time.time() - self.started, 1),
                    by_path=dict(self.by_path), stop_reason=self.stop_reason,
                    errors=self.errors)


def list_all(c: Client, doctype: str, fields: list[str], filters: list,
             order_by: str = "name asc") -> list[dict]:
    """Paginated list call; each page <= PAGE (100)."""
    out, start = [], 0
    while True:
        res = c.get(f"/api/resource/{doctype}",
                    {"fields": json.dumps(fields),
                     "filters": json.dumps(filters),
                     "limit_page_length": PAGE, "limit_start": start,
                     "order_by": order_by})
        rows = (res or {}).get("data", []) if isinstance(res, dict) else []
        out.extend(rows)
        if len(rows) < PAGE:
            break
        start += PAGE
    return out


def custom_fields(c: Client) -> list[dict]:
    res = c.get("/api/resource/Custom Field",
                {"fields": json.dumps(["dt", "fieldname", "label", "fieldtype", "options"]),
                 "filters": json.dumps([["dt", "in", ["Sales Order", "Sales Order Item"]]]),
                 "limit_page_length": 100, "order_by": "dt asc, fieldname asc"})
    return (res or {}).get("data", []) if isinstance(res, dict) else []


def dp_rows(c: Client, names: list[str]) -> list[dict]:
    """Delivery Plan item rows (flattened) linked to the given SO names.

    Child-list reads are 403, but the parent list accepts a child-doctype filter
    (`["Delivery Plan Item", "sales_order", "in", names]`) and expands items.*
    fields. This returns only linked rows, so no full scan is needed.
    """
    fields = ["name", "is_dn_pending", "items.sales_order", "items.so_detail",
              "items.item_code", "items.qty", "items.planned_delivery_qty", "creation"]
    filters = [["Delivery Plan Item", "sales_order", "in", names]]
    out, start = [], 0
    while True:
        res = c.get("/api/resource/Delivery Plan",
                    {"fields": json.dumps(fields), "filters": json.dumps(filters),
                     "limit_page_length": PAGE, "limit_start": start,
                     "order_by": "name asc"})
        rows = (res or {}).get("data", []) if isinstance(res, dict) else []
        out.extend(rows)
        if len(rows) < PAGE:
            break
        start += PAGE
    return out


def pct(x, n):
    return round(x / n, 4) if n else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ENV))
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = load_env(Path(args.env))
    c = Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])

    result = dict(schema_version="en_so_linkage/1",
                  generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                  base_url=args.base, sample_rule=(
                      "SO 级统计=分段全量；Delivery Plan 关联、item 级政策字段、配对="
                      f"每段按 name 升序取前 {SAMPLE_PER_SEG} 单的样本"),
                  segments={}, policy=dict(), reference=dict(), limits=[
                      "只读 GET；无写入/无下单/无配置变更",
                      "样本与全量在每张表注明；不做全量外推", "不解释字段业务含义"])
    try:
        cf = custom_fields(c)
        so_custom = [x["fieldname"] for x in cf
                     if x.get("dt") == "Sales Order" and x.get("fieldname")]
        item_custom = [x["fieldname"] for x in cf
                       if x.get("dt") == "Sales Order Item" and x.get("fieldname")]
        policy_so = [f for f in so_custom
                     if POLICY_RE.search(f + " " + str(next(
                         (x.get("label") for x in cf if x.get("fieldname") == f), "")))]
        policy_item = [f for f in item_custom
                       if POLICY_RE.search(f + " " + str(next(
                           (x.get("label") for x in cf if x.get("fieldname") == f), "")))]
        result["reference"]["custom_fields"] = cf
        result["reference"]["policy_fields"] = dict(so=policy_so, item=policy_item)

        header_fields = (["name", "docstatus", "status", "transaction_date",
                          "per_delivered", "delivery_status", "type_of_manufacturing",
                          "company", "customer"] + policy_so)
        item_fields = (["parent", "item_code", "qty", "delivery_date", "warehouse",
                        "type_of_manufacturing"] + policy_item)

        for label, lo, hi, human in SEGMENTS:
            flt = [["transaction_date", ">=", lo], ["transaction_date", "<", hi]]
            sos = list_all(c, "Sales Order", header_fields, flt)
            total = len(sos)
            cancelled = sum(1 for d in sos if d.get("docstatus") == 2)
            submitted = [d for d in sos if d.get("docstatus") == 1]
            unshipped = sum(1 for d in submitted
                            if d.get("per_delivered") is not None
                            and float(d["per_delivered"]) < 100)
            sample = sos[:SAMPLE_PER_SEG]
            names = [d["name"] for d in sample]

            # items for sample SOs via the SO document (child doctype list is 403)
            docs = []
            for nm in names:
                d = c.get(f"/api/resource/Sales Order/{nm}")
                if d and d.get("data"):
                    docs.append(d["data"])
            items = [it for d in docs for it in (d.get("items") or [])]
            groups = defaultdict(list)
            for it in items:
                groups[it.get("parent")].append(it)
            pairing = Counter()
            for nm in names:
                codes = [x.get("item_code") or "" for x in groups.get(nm, [])]
                cover = any(x.startswith("PK#") for x in codes)
                inner = any(x.startswith("ND#") for x in codes)
                pairing["both" if cover and inner else
                        "cover_only" if cover else
                        "inner_only" if inner else "neither"] += 1

            # Delivery Plan linkage for sample SOs: parent list + child filter
            dp_all = dp_rows(c, names) if names else []
            name_set = set(names)
            dp_items = [x for x in dp_all if x.get("sales_order") in name_set]
            linked_so = {x.get("sales_order") for x in dp_items if x.get("sales_order")}
            so_detail_nonempty = sum(1 for x in dp_items if x.get("so_detail"))
            parent_status = {x.get("name"): x.get("is_dn_pending") for x in dp_items
                             if x.get("name")}
            dp_parents = sorted(parent_status)
            dn_pending = Counter(str(v) for v in parent_status.values())
            status = Counter(str(x.get("status")) for x in sos)
            tom = Counter(str(x.get("type_of_manufacturing")) for x in sos)
            month_tom = defaultdict(Counter)
            for x in sos:
                m = str(x.get("transaction_date") or "")[:7]
                if m:
                    month_tom[m][str(x.get("type_of_manufacturing"))] += 1
            pol_so_vals = {f: Counter(str(x.get(f)) for x in sos) for f in policy_so}
            pol_item_vals = {f: Counter(str(x.get(f)) for x in items) for f in policy_item}

            result["segments"][label] = dict(
                window=human, full=dict(so=total, cancelled=cancelled,
                                        cancelled_ratio=pct(cancelled, total),
                                        submitted=len(submitted), unshipped=unshipped,
                                        unshipped_ratio=pct(unshipped, len(submitted)),
                                        status=dict(status),
                                        type_of_manufacturing=dict(tom)),
                sample=dict(n=len(names), so_hashes=[sha(n) for n in names],
                            items=len(items), pairing=dict(pairing),
                            dp=dict(so_linked=len(linked_so),
                                    so_link_ratio=pct(len(linked_so), len(names)),
                                    dp_items=len(dp_items),
                                    so_detail_nonempty=so_detail_nonempty,
                                    dp_parents=len(dp_parents),
                                    dn_pending=dict(dn_pending),
                                    total_planned_qty=round(sum(
                                        float(x.get("planned_delivery_qty") or 0)
                                        for x in dp_items), 2),
                                    total_actual_delivered_qty=None),
                            policy_so={f: dict(v) for f, v in pol_so_vals.items()},
                            policy_item={f: dict(v) for f, v in pol_item_vals.items()}),
                monthly_type={m: dict(v) for m, v in sorted(month_tom.items())},
            )

        def abrupt(monthly: dict) -> list[dict]:
            """Only report a month-over-month top-value share jump (>50 pp)."""
            months = sorted(monthly)
            out = []
            for a, b in zip(months, months[1:]):
                na = sum(monthly[a].values())
                nb = sum(monthly[b].values())
                if na < 5 or nb < 5:
                    continue
                ta = max(monthly[a], key=monthly[a].get)
                tb = max(monthly[b], key=monthly[b].get)
                sa, sb = monthly[a][ta] / na, monthly[b][tb] / nb
                if ta != tb or abs(sa - sb) >= 0.5:
                    out.append(dict(before=a, after=b,
                                    top_before=ta, top_after=tb,
                                    share_before=round(sa, 3),
                                    share_after=round(sb, 3)))
            return out

        result["policy"]["monthly_type"] = {
            k: v.get("monthly_type", {}) for k, v in result["segments"].items()}
        result["policy"]["abrupt_changes"] = {
            k: abrupt(v.get("monthly_type", {})) for k, v in result["segments"].items()}
        # first month each value appears (chronological segments A..D)
        first_seen = {}
        for k in ("A", "B", "C", "D"):
            for m, dist in (result["segments"].get(k, {}).get("monthly_type", {})).items():
                for v in dist:
                    first_seen.setdefault(v, m)
        result["policy"]["first_seen_by_value"] = first_seen
        result["policy"]["custom_fields_found"] = dict(
            so=bool(policy_so), item=bool(policy_item))

        # month-level policy timeline from the full header lists is not stored
        # per segment here; re-derive from the same headers would need them kept.
        # Instead, policy timeline is reported per segment + monthly top-value
        # changes are computed from the SO list retrieved above when available.
        # (Headers are recomputed once more below only if budget allows.)
        result["policy"]["note"] = ("按段分布为全量；月份级突变检测使用各段全量 header 的 "
                                    "transaction_date × type_of_manufacturing，见 monthly_type")
        result["budget"] = c.report()
    except StopRun:
        result["budget"] = c.report()
        result["stopped"] = c.stop_reason

    (OUT / "linkage_profile.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # markdown
    L = ["# EN SO 关联覆盖与政策时间线", "",
         "> 只读 GET；预算 ≤200 次、page_length ≤100、间隔 ≥200ms；超时/5xx 即停。",
         "> 全量/样本在每张表注明；不解释字段业务含义、不写下单建议。", "",
         "## 1. 预算", "",
         f"- 请求 **{c.gets}** 次 / 上限 200；耗时 **{round(time.time()-c.started,1)} s**；"
         f"停止：{c.stop_reason or '无（正常完成）'}",
         f"- 按路径：{dict(c.by_path)}", ""]
    if c.errors:
        L += ["- 错误：" + "；".join(c.errors), ""]
    L += ["## 2. 分段统计（SO 级 = 全量）", "",
          "| 段 | 窗口 | SO 数 | cancelled | cancelled 比例 | submitted | 未发(<100) | 未发比例 |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for k in ("A", "B", "C", "D"):
        s = result["segments"].get(k)
        if not s:
            continue
        f = s["full"]
        L.append(f"| {k} | {s['window']} | {f['so']} | {f['cancelled']} | "
                 f"{f['cancelled_ratio']} | {f['submitted']} | {f['unshipped']} | "
                 f"{f['unshipped_ratio']} |")
    L += ["", "## 3. Delivery Plan 关联（样本：每段前 15 单）", "",
          "| 段 | 样本 SO | 有 DP 关联 SO | 关联率 | DP item 行 | so_detail 非空 | DP 单数 | "
          "is_dn_pending | 计划量合计 |",
          "|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for k in ("A", "B", "C", "D"):
        s = result["segments"].get(k)
        if not s:
            continue
        d = s["sample"]["dp"]
        L.append(f"| {k} | {s['sample']['n']} | {d['so_linked']} | {d['so_link_ratio']} | "
                 f"{d['dp_items']} | {d['so_detail_nonempty']} | {d['dp_parents']} | "
                 f"{d['dn_pending']} | {d['total_planned_qty']} |")
    L += ["", "关联字段实测：`Delivery Plan Item.sales_order` / `.so_detail`；"
              "`Delivery Plan` header 有 `sale_orders`（未按该字段查询）；"
              "SO 文档本身无直接 DP 链接字段。", "",
          "## 4. 皮壳/内胆配对（样本：每段前 15 单）", "",
          "| 段 | both | cover_only | inner_only | neither |", "|---|---:|---:|---:|---:|"]
    for k in ("A", "B", "C", "D"):
        s = result["segments"].get(k)
        if not s:
            continue
        p = s["sample"]["pairing"]
        L.append(f"| {k} | {p.get('both', 0)} | {p.get('cover_only', 0)} | "
                 f"{p.get('inner_only', 0)} | {p.get('neither', 0)} |")
    L += ["", "口径：`PK#` 为皮壳、`ND#` 为内胆；同一 SO 内同现=both；"
              "仅按 item_code 前缀判定，不看数量或 BOM。", "",
          "## 5. 政策字段时间线", "",
          "### 5.1 `type_of_manufacturing`（SO header，全量按段）", ""]
    keys = sorted({k for s in result["segments"].values()
                   for k in s["full"]["type_of_manufacturing"]})
    L += ["| 段 | " + " | ".join(f"`{k}`" for k in keys) + " |",
          "|---|" + "---:|" * len(keys)]
    for k in ("A", "B", "C", "D"):
        s = result["segments"].get(k)
        if not s:
            continue
        L.append(f"| {k} | " + " | ".join(str(s["full"]["type_of_manufacturing"].get(x, 0))
                                          for x in keys) + " |")
    L += ["", "### 5.1b 月份级 `type_of_manufacturing` 分布（全量）", "",
          "| 段 | 月份 | 分布 |", "|---|---|---|"]
    for k in ("A", "B", "C", "D"):
        s = result["segments"].get(k)
        if not s:
            continue
        for m, dist in s.get("monthly_type", {}).items():
            L.append(f"| {k} | {m} | {dist} |")
    L += ["", "- 突变检测（仅当相邻两月各 ≥5 单且 top 值占比变化 ≥50pp 或 top 值变化）："]
    any_abrupt = False
    for k in ("A", "B", "C", "D"):
        ch = (result.get("policy", {}).get("abrupt_changes", {}) or {}).get(k, [])
        if ch:
            any_abrupt = True
            L.append(f"  - 段 {k}：{ch}")
    if not any_abrupt:
        L.append("  - 未发现满足阈值的月份突变（这是“未见突变”，不是“政策未变”）。")
    fs = (result.get("policy", {}) or {}).get("first_seen_by_value", {})
    if fs:
        L.append(f"  - 各取值首次出现的月份：{fs}（只记现象，不解释原因）。")
    L += ["", "### 5.2 审批/价格相关自定义字段", ""]
    ref = result.get("reference", {})
    L += [f"- 识别的字段（SO）：{ref.get('policy_fields', {}).get('so', [])}",
          f"- 识别的字段（SO Item）：{ref.get('policy_fields', {}).get('item', [])}"]
    if not (ref.get("policy_fields", {}).get("so") or
            ref.get("policy_fields", {}).get("item")):
        L.append("- **未发现** label/fieldname 匹配 approve/price/rate/discount/credit/limit/"
                 "authoriz 的 SO 或 Item 自定义字段；本节无取值分布可报。")
    for k in ("A", "B", "C", "D"):
        s = result["segments"].get(k)
        if not s:
            continue
        if s["sample"]["policy_so"] or s["sample"]["policy_item"]:
            L.append(f"- 段 {k}：SO 字段分布 {s['sample']['policy_so']}；"
                     f"item 字段分布 {s['sample']['policy_item']}")
    L += ["", "> 只记录存在与取值分布，不解释业务含义；如某字段在某月前后分布突变，"
              "只记现象与月份，不下结论。", "",
          "## 6. 看到 / 看不到", "",
          "- 看到：四段的 SO 全量计数/cancelled/未发比例；样本内的 DP 关联与 "
          "`is_dn_pending` 分布；`type_of_manufacturing` 全量分段分布；配对比例；"
          "审批/价格相关自定义字段的存在与样本取值。",
          "- 看不到：DP 关联的全量覆盖率（样本 15/段）、字段业务含义、"
          "扫码关联（SO/Item/DP 实测未见 scan/qr 字段）、政策变化的因果。",
          "- 不给下单建议，不做全量外推。", "",
          "## 7. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/"
          "experiments/auto_order/recon_linkage.py",
          "uv run python scripts/check_secrets.py",
          "```", ""]
    (OUT / "policy_timeline.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote linkage_profile.json / policy_timeline.md; requests", c.gets,
          "stop", c.stop_reason)


if __name__ == "__main__":
    main()
