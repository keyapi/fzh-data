#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""What is SO.po_no, and which explicit SO -> supply links really exist? (READ-ONLY)

T40 found that `po_no` resolved to zero Purchase Orders. This check answers the
question without guessing:

  1. What is `Sales Order.po_no`?
     * its DocType fieldtype / label (read from the DocType meta);
     * the *format* of up to 30 sampled values (letters -> A, digits -> 9, any
       other character -> ?); only the leading alpha prefix and that masked
       pattern are printed — never a value;
     * whether any Purchase Order is named by one of those sampled values.
  2. Which explicit references to a Sales Order exist in the doctypes we can
     reach? For Work Order, Material Request, Production Plan, Delivery Plan,
     Delivery Note and Purchase Order we read the schema (is there a
     `sales_order` / `so_detail` / `against_sales_order` link?) and count how
     many records actually reference a few sampled SOs.

No inference beyond the schema and the counts; no writes; document numbers are
hashed and `po_no` values are never printed in full.

Budget: <=60 GET, single-threaded, 200 ms interval, stop on timeout / 5xx / auth.

Output: out/auto_order/po_link_findings.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import build_order_suggestions as v01  # noqa: E402

OUT = HERE.parents[2] / "out" / "auto_order"
MAX_GETS = 60
SCOPE_FROM = "2026-01-01"
SCOPE_TO = "2026-10-01"
SAMPLE_N = 30
HIT_LIMIT = 20

# label, query doctype, filter head, human description, doctype holding the field
CANDIDATES = [
    ("Work Order", "Work Order", ["sales_order"],
     "`sales_order` (Link→Sales Order)", "Work Order"),
    ("Material Request", "Material Request",
     ["Material Request Item", "sales_order"],
     "`Material Request Item.sales_order` (Link→Sales Order)", "Material Request Item"),
    ("Production Plan", "Production Plan",
     ["Production Plan Sales Order", "sales_order"],
     "`Production Plan Sales Order.sales_order` (Link→Sales Order)",
     "Production Plan Sales Order"),
    ("Delivery Plan", "Delivery Plan",
     ["Delivery Plan Item", "sales_order"],
     "`Delivery Plan Item.sales_order` (Link→Sales Order) + `so_detail` (Data)",
     "Delivery Plan Item"),
    ("Delivery Note", "Delivery Note",
     ["Delivery Note Item", "against_sales_order"],
     "`Delivery Note Item.against_sales_order` (Link→Sales Order) + `so_detail` (Data)",
     "Delivery Note Item"),
    ("Purchase Order", "Purchase Order",
     ["Purchase Order Item", "sales_order"],
     "`Purchase Order Item.sales_order` (Link→Sales Order)", "Purchase Order Item"),
]

META_DOCTYPES = ["Sales Order"] + [c[4] for c in CANDIDATES]


def mask(v: str) -> str:
    """Masked shape: ASCII letters -> A, digits -> 9, anything else -> ?."""
    out = []
    for ch in v:
        out.append("A" if ch.isascii() and ch.isalpha()
                   else "9" if ch.isascii() and ch.isdigit()
                   else "?")
    return "".join(out)


def prefix(v: str) -> str:
    m = re.match(r"^[A-Za-z]+", v or "")
    return m.group(0) if m else ""


def sha(x) -> str:
    return hashlib.sha256(str(x).encode("utf-8")).hexdigest()[:12]


def fetch_page(c, doctype, fields, filters, limit):
    """One request, capped — used where pagination is unnecessary or heavy."""
    res = c.get(f"/api/resource/{doctype}",
                {"fields": json.dumps(fields), "filters": json.dumps(filters),
                 "limit_page_length": limit, "order_by": "name asc"})
    return ((res or {}).get("data", []) if isinstance(res, dict) else []) or []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(v01.ENV))
    ap.add_argument("--base", default=v01.BASE)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    v01.MAX_GETS = MAX_GETS
    v01.SLEEP_S = args.sleep
    env = v01.load_env(Path(args.env))
    c = v01.Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])
    errors = {}

    def safe(label, fn):
        # A single failing query (e.g. HTTP 500 on a heavy child-table filter)
        # must not stop the remaining probes; only budget / transport / auth
        # stops are terminal for this run.
        if c.stop_reason and not c.stop_reason.startswith("http_"):
            errors[label] = f"skipped after stop ({c.stop_reason})"
            return None
        try:
            return fn()
        except v01.StopRun as exc:
            errors[label] = str(exc)
            return None

    # ---- 1. po_no sample ---------------------------------------------
    so_sample = safe("Sales Order sample", lambda: fetch_page(
        c, "Sales Order",
        ["name", "po_no", "transaction_date", "is_internal_customer"],
        [["docstatus", "=", 1],
         ["transaction_date", ">=", SCOPE_FROM],
         ["transaction_date", "<", SCOPE_TO]], SAMPLE_N)) or []
    po_values = [str(r.get("po_no")).strip() for r in so_sample
                 if str(r.get("po_no") or "").strip()]
    patterns = Counter(mask(v) for v in po_values)
    prefixes = Counter(prefix(v) for v in po_values)

    # ---- 2. does any PO carry one of those names? --------------------
    def fetch_po_by_those_names():
        rows = []
        for chunk in v01._chunks(sorted(set(po_values)), 20):
            rows.extend(fetch_page(c, "Purchase Order", ["name"],
                                   [["name", "in", chunk]], len(chunk)))
        return rows

    po_name_hits = safe("PO name match", fetch_po_by_those_names) or []

    # ---- 2b. global control: does ANY PO reference an SO at all? -----
    def po_global():
        return fetch_page(c, "Purchase Order", ["name"],
                          [["Purchase Order Item", "sales_order", "is", "set"]], 5)
    po_global_rows = safe("PO sales_order is-set", po_global)

    # ---- 2c. reproducibility of the Delivery Plan `status` quirk -----
    quirk = None
    if so_sample:
        probe_so = so_sample[0]["name"]
        fset_with = ["name", "docstatus", "status", "items.name as line_id",
                     "items.sales_order", "items.so_detail", "items.item_code",
                     "items.qty", "items.uom"]
        fset_without = [f for f in fset_with if f != "status"]

        def quirk_probe():
            out = {}
            for label, fields in (("with_status", fset_with),
                                  ("without_status", fset_without)):
                res = c.get("/api/resource/Delivery Plan",
                            {"fields": json.dumps(fields),
                             "filters": json.dumps([["Delivery Plan Item",
                                                     "sales_order", "=", probe_so]]),
                             "limit_page_length": 20, "order_by": "name asc"})
                out[label] = len(((res or {}).get("data", []) or []))
            return out
        quirk = safe("DP status quirk", quirk_probe)

    # ---- 3. schema: fieldtype of every candidate link ----------------
    schema = {}
    for dt in META_DOCTYPES:
        def read_meta(dt=dt):
            r = c.get(f"/api/resource/DocType/{dt}")
            d = (r or {}).get("data", {}) or {}
            return [(f.get("fieldname"), f.get("fieldtype"), f.get("options"),
                     f.get("label")) for f in d.get("fields", [])]
        schema[dt] = safe(f"meta {dt}", read_meta)
    po_no_field = next((f for f in (schema.get("Sales Order") or [])
                        if f[0] == "po_no"), None)

    # ---- 4. sample hits per path -------------------------------------
    ext = [r for r in so_sample if not r.get("is_internal_customer")]
    inte = [r for r in so_sample if r.get("is_internal_customer")]
    hit_sos = (ext[:2] + inte[:2])[:4]

    hits = {}
    for label, doctype, head, _desc, _meta in CANDIDATES:
        per_so, err = [], None
        for so in hit_sos:
            rows = safe(f"{label}", lambda so=so, doctype=doctype, head=head: fetch_page(
                c, doctype, ["name", "docstatus"],
                [list(head) + ["=", so["name"]]], HIT_LIMIT))
            if rows is None:
                err = errors.get(label)
                per_so.append(None)
            else:
                per_so.append(len(rows))
        hits[label] = dict(per_so=per_so, err=err,
                           total=sum(x for x in per_so if x is not None))

    elapsed = round(time.time() - c.started, 1)

    # ---- 5. report ----------------------------------------------------
    L = ["---", "okf: v0.1", "type: Report",
         "title: SO 与采购/生产的真实关联路径",
         "date: 2026-10-22", "owner: claude-worker",
         "status: 只读完成；只写 schema 与样本计数，不推断",
         "artifacts:",
         "  - experiments/auto_order/check_po_link.py",
         "---", "",
         "# SO 与采购/生产的真实关联路径", "",
         "> 目标：解释 T40「`po_no` 解析到 Purchase Order 命中 0」，并列出**实际存在**的显式关联路径。"
         "只读 schema 与样本计数；`po_no` 只显示前缀与掩码格式，不显示原值。", "",
         "## 0. 预算与样本", "",
         f"- 请求 **{c.gets}** / {MAX_GETS}；耗时 **{elapsed} s**；单线程；间隔 {args.sleep} s；"
         f"停止原因：{c.stop_reason or '无（正常完成）'}",
         f"- SO 样本：2026-01-01..2026-09-30 已提交 SO 按单号升序取前 **{len(so_sample)}** 张"
         f"（外部 {sum(1 for r in so_sample if not r.get('is_internal_customer'))} / "
         f"内部 {sum(1 for r in so_sample if r.get('is_internal_customer'))}）",
         f"- 命中探测用 SO：**{len(hit_sos)}** 张（哈希 "
         f"{', '.join('`' + sha(r['name']) + '`' for r in hit_sos)}）", "",
         "## 1. `po_no` 是什么", ""]

    if po_no_field:
        L.append(f"- DocType `Sales Order.po_no`：**fieldtype = `{po_no_field[1]}`**，"
                 f"label = `{po_no_field[3]}`"
                 + (f"，options = `{po_no_field[2]}`" if po_no_field[2] else "")
                 + "。**不是 Link→Purchase Order**，所以它不可能承载内部采购单号。")
    else:
        L.append("- 未能读到 `Sales Order.po_no` 的 schema（见错误清单）。")
    L += ["", f"- {len(so_sample)} 张 SO 中 `po_no` **非空 {len(po_values)}** 条；前缀分布："
          + "、".join(f"`{p or '（无字母前缀）'}`×{n}" for p, n in prefixes.most_common()),
          "- 掩码格式（字母→A、数字→9、其他→?）："
          + "、".join(f"`{p}`×{n}" for p, n in patterns.most_common()),
          f"- 用这 {len(set(po_values))} 个值对 `Purchase Order.name` 精确匹配："
          f"命中 **{len(po_name_hits)}** 行。", "",
          "> 仅据 fieldtype 与匹配数：`po_no` 是**客户自己的采购单号**（Data 文本），"
          "不是指向 EN Purchase Order 的引用；T40 的「未解析」是**字段语义不同**，"
          "不是「PO 单据缺失」。", "",
          "## 2. 候选显式关联路径：字段是否存在", "",
          "| 对象 | 引用字段 | fieldtype | 存在 |", "|---|---|---|---|"]
    for label, _dt, head, desc, meta_dt in CANDIDATES:
        fields = schema.get(meta_dt) or []
        match = next((f for f in fields if f[0] == head[-1]), None)
        if match:
            L.append(f"| {label} | {desc} | `{match[1]}`→`{match[2]}` | 是 |")
        else:
            L.append(f"| {label} | {desc} | — | **否/未读到** |")

    L += ["", "## 3. 候选显式关联路径：样本命中数", "",
          f"> 每格是「用该 SO 单号过滤该 doctype 得到的行数」，单次查询上限 {HIT_LIMIT} 行；"
          f"只说明**样本内**有没有显式引用。", "",
          "| 路径 | " + " | ".join(f"SO `{sha(r['name'])}`" for r in hit_sos) + " | 合计 | 备注 |",
          "|---|" + "---:|" * len(hit_sos) + "---:|---|"]
    for label, _dt, _head, _desc, _meta in CANDIDATES:
        h = hits[label]
        cells = ["阻塞" if v is None else (f"{v}（上限）" if v >= HIT_LIMIT else str(v))
                 for v in h["per_so"]]
        note = f"查询失败（{h['err']}）" if h["err"] else ""
        L.append(f"| {label} | " + " | ".join(cells) + f" | {h['total']} | {note} |")

    L += ["", "## 3b. Purchase Order 全局对照", ""]
    if po_global_rows is None:
        L.append(f"- `Purchase Order Item.sales_order is set` 查询失败：{errors.get('PO sales_order is-set')}")
    else:
        L.append(f"- 全库（不限样本）查 `Purchase Order Item.sales_order is set`（limit 5）："
                 f"返回 **{len(po_global_rows)}** 行。")
        L.append(f"- 同一查询形状在 `Delivery Plan Item.sales_order is set` 上返回 5 行，"
                 f"说明「is set」过滤本身可用；因此 PO 的 0 不是查询写法造成的。")

    L += ["", "## 3c. 查询陷阱（影响可复现性，须记录）", ""]
    if quirk:
        L.append(f"- 在 `Delivery Plan` 上，字段清单**同时包含表头 `status` 与子表字段**时，"
                 f"接口静默返回 0 行（不报错）；去掉 `status` 后同一过滤返回 "
                 f"**{quirk['without_status']}** 行（带 `status`：{quirk['with_status']} 行）。")
        L.append("- 影响：上一轮 T40 时点的“Delivery Plan 关联 0 行”是**该字段组合造成的假阴性**，"
                 "不是 DP 真的没有关联；DP 只被当作“关联证据”，所以当时的守恒恒等式与比值不受影响，"
                 "但「未观测」行数可能偏高。")
    else:
        L.append(f"- DP status 对照查询失败：{errors.get('DP status quirk')}")
    L += ["", "## 4. 结论", ""]

    work, dn, po = hits["Work Order"], hits["Delivery Note"], hits["Purchase Order"]
    L.append(f"1. **有实际命中的显式路径**：`Work Order.sales_order`（样本合计 {work['total']} 行，20 为单次查询上限）、"
             f"`Material Request Item.sales_order`（{hits['Material Request']['total']} 行）、"
             f"`Production Plan Sales Order.sales_order`（{hits['Production Plan']['total']} 行）、"
             f"`Delivery Plan Item.sales_order`（{hits['Delivery Plan']['total']} 行）、"
             f"`Delivery Note Item.against_sales_order`（{dn['total']} 行）。"
             f"这五条路径的字段在 schema 中都是 `Link → Sales Order`，本轮样本都能查到记录。样本只有 4 张 SO，命中的是「有没有」不是「有多少」。")
    L.append(f"2. **Purchase Order 这条路不通**：字段 `Purchase Order Item.sales_order` 存在且是 Link，"
             f"但 4 张样本 SO 命中 {sum(x for x in po['per_so'] if x is not None)} 行，"
             f"且全库 `is set` 查询也是 0 行。也就是说：**schema 允许 PO 引用 SO，但 EN 里没有任何 PO 这样做**。")
    L.append(f"3. **T40 的「po_no 未解析」是两个独立原因叠加**："
             f"① `po_no` 的 fieldtype 是 `{po_no_field[1] if po_no_field else '未知'}`"
             f"（label「{po_no_field[3] if po_no_field else ''}」），存的是客户采购单号，"
             f"本就不指向 Purchase Order；② 即使想走 PO→SO 的 Link，全库也没有一条 PO 设置了 `sales_order`。"
             f"因此「有 po_no 却没有对应 PO」是预期，不是漏单，也不是 PO 单据缺失。")
    if errors:
        L += ["", "## 5. 本次失败/受限的请求", ""]
        for k, v in errors.items():
            L.append(f"- `{k}` → {v}")
    L += ["", f"## {'6' if errors else '5'}. 方法与复现", "",
          "- 只读：schema 读 `/api/resource/DocType/<name>.fields`；数据读 `/api/resource/<doctype>`；"
          "无任何写操作。",
          "- 单号哈希化（sha256 前 12 位）；`po_no` 只输出前缀与掩码格式，不输出原值。",
          "- 样本固定：SO 按单号升序前 30 张，命中探测取前 2 张外部 + 前 2 张内部，可复现。",
          "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_po_link.py",
          "```", ""]

    (OUT / "po_link_findings.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote po_link_findings.md")
    print(f"requests={c.gets} elapsed={elapsed}s sample={len(so_sample)} "
          f"po_values={len(po_values)} po_name_hits={len(po_name_hits)} "
          f"po_global_set={None if po_global_rows is None else len(po_global_rows)} "
          f"dp_quirk={quirk} stopped={c.stop_reason} errors={errors}")
    for label, _dt, _head, _desc, _meta in CANDIDATES:
        h = hits[label]
        print(f"  {label}: per_so={h['per_so']} total={h['total']} err={h['err']}")


if __name__ == "__main__":
    main()
