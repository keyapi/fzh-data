#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EN DN linkage check for the V0.2 external SOs (READ-ONLY).

Question: are the 71 overdue external suggestion rows "really short" or
"shipped but not written back"?

For each external SO (from V0.2), read:
  * Delivery Plan linked via `Delivery Plan Item.sales_order` / `so_detail`
    and its `is_dn_pending` flag;
  * Delivery Note linked via `Delivery Note Item.against_sales_order` /
    `so_detail`, with docstatus/status.

Three observable classes per SO
  A `dn_submitted`  : at least one submitted DN (docstatus=1)
  B `dn_unsubmitted`: DN exists but only draft/cancelled (docstatus 0/2)
  C `none`          : no DN and no Delivery Plan at all
  plus `dp_only`    : Delivery Plan exists but no DN (pending outbound) — sub-count

"No DN" is never equated with "true stockout": it may be offline shipping.
Budget: <=80 GET, single-threaded, 200 ms, stop on timeout/5xx.
Outputs: out/auto_order/dn_linkage_check.csv / .md
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import build_order_suggestions as v01  # noqa: E402

OUT = HERE.parents[2] / "out" / "auto_order"
MAX_GETS = 80
SCOPE_FROM = "2026-01-01"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(v01.ENV))
    ap.add_argument("--base", default=v01.BASE)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    v01.MAX_GETS = MAX_GETS
    env = v01.load_env(Path(args.env))
    c = v01.Client(args.base, env["ERP_API_KEY"], env["ERP_API_SECRET"])

    ext = list(csv.DictReader(open(OUT / "external_view.csv", encoding="utf-8-sig")))
    hashes = {h for r in ext for h in (r.get("so_hashes") or "").split("|") if h}

    heads = v01.list_all(c, "Sales Order",
                         ["name", "docstatus", "status", "transaction_date",
                          "per_delivered", "is_internal_customer"],
                         [["docstatus", "=", 1],
                          ["status", "not in", ["Closed", "Cancelled"]],
                          ["transaction_date", ">=", SCOPE_FROM]])
    by_hash = {v01.sha(h["name"]): h for h in heads}
    names = [by_hash[h]["name"] for h in hashes if h in by_hash]

    dp_rows = v01.list_all(c, "Delivery Plan",
                           ["name", "is_dn_pending", "docstatus",
                            "items.sales_order", "items.so_detail",
                            "items.item_code", "items.qty"],
                           [["Delivery Plan Item", "sales_order", "in", names]]) if names else []
    dn_rows = v01.list_all(c, "Delivery Note",
                           ["name", "docstatus", "status",
                            "items.against_sales_order", "items.so_detail",
                            "items.item_code", "items.qty"],
                           [["Delivery Note Item", "against_sales_order", "in", names]]) if names else []

    dp_by_so = defaultdict(list)
    for r in dp_rows:
        if r.get("sales_order"):
            dp_by_so[r["sales_order"]].append(r)
    dn_by_so = defaultdict(list)
    for r in dn_rows:
        if r.get("against_sales_order"):
            dn_by_so[r["against_sales_order"]].append(r)

    # per-SO classification + per-line output (fetch external SO docs for lines)
    so_rows = []
    line_rows = []
    for h in sorted(hashes):
        meta = by_hash.get(h)
        if not meta:
            continue
        name = meta["name"]
        dps = dp_by_so.get(name, [])
        dns = dn_by_so.get(name, [])
        dn_statuses = sorted({f"{d.get('name')}:{d.get('docstatus')}" for d in dns})
        dn_codes = sorted({str(d.get("docstatus")) for d in dns})
        dp_flags = sorted({str(d.get("is_dn_pending")) for d in dps})
        if "1" in dn_codes:
            cls = "dn_submitted"
        elif dns:
            cls = "dn_unsubmitted"
        elif dps:
            cls = "dp_only"
        else:
            cls = "none"
        pd = meta.get("per_delivered")
        so_rows.append(dict(so_hash=h, status=meta.get("status"),
                            transaction_date=str(meta.get("transaction_date") or "")[:10],
                            per_delivered=pd, dp_exists=bool(dps),
                            dp_flags="|".join(dp_flags), dn_exists=bool(dns),
                            dn_statuses="|".join(dn_statuses), class_=cls,
                            submitted_dn=("1" in dn_codes),
                            pd_lt100=(pd is not None and float(pd) < 100)))
        d = c.get(f"/api/resource/Sales Order/{name}")
        if not (d and d.get("data")):
            continue
        for idx, it in enumerate(d["data"].get("items") or []):
            qty = float(it.get("qty") or 0)
            delivered = float(it.get("delivered_qty") or 0)
            line_rows.append(dict(
                so_hash=h, so_status=meta.get("status"), per_delivered=pd,
                line_idx=idx, item_code=it.get("item_code") or "",
                qty=qty, delivered=delivered,
                unfulfilled=round(max(0.0, qty - delivered), 2),
                delivery_date=str(it.get("delivery_date") or "")[:10],
                warehouse=it.get("warehouse") or "",
                dp_exists=bool(dps), dp_flags="|".join(dp_flags),
                dn_exists=bool(dns), dn_statuses="|".join(dn_statuses),
                class_=cls, note="class 为 SO 级；无 DN 不等于真缺货（可能线下发货）"))

    counts = Counter(x["class_"] for x in so_rows)
    line_counts = Counter(x["class_"] for x in line_rows)
    submitted = [x for x in so_rows if x["class_"] == "dn_submitted"]
    result_fields = ["so_hash", "so_status", "per_delivered", "line_idx",
                     "item_code", "qty", "delivered", "unfulfilled",
                     "delivery_date", "warehouse", "dp_exists", "dp_flags",
                     "dn_exists", "dn_statuses", "class_", "note"]
    with (OUT / "dn_linkage_check.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=result_fields)
        w.writeheader()
        w.writerows(line_rows)

    sub_pd = [float(x["per_delivered"]) for x in submitted if x["per_delivered"] is not None]
    sub_lines = [x for x in line_rows if x["class_"] == "dn_submitted"]
    sub_unf = sum(1 for x in sub_lines if x["unfulfilled"] > 0)
    L = ["# 外部 SO 的 DN 关联核对", "",
         "> 只读；判断“外部逾期是否已出库未回写/确实无出库记录”。",
         "> **无 DN ≠ 真缺货**：可能线下发货，单据只能证明“系统内有无记录”。", "",
         "## 0. 预算", "",
         f"- 请求 **{c.gets}** / 80；停止：{c.stop_reason or '无（正常完成）'}；"
         f"外部 SO {len(so_rows)}、外部行 {len(line_rows)}", "",
         "## 1. SO 级三类计数", "",
         "| 类别 | SO 数 | 行数 | 含义 |", "|---|---:|---:|---|",
         f"| `dn_submitted` | {counts.get('dn_submitted',0)} | {line_counts.get('dn_submitted',0)} | 有已提交 DN（docstatus=1） |",
         f"| `dn_unsubmitted` | {counts.get('dn_unsubmitted',0)} | {line_counts.get('dn_unsubmitted',0)} | 有 DN 但仅 draft/cancelled |",
         f"| `none` | {counts.get('none',0)} | {line_counts.get('none',0)} | 无任何 DN 与 DP |",
         f"| `dp_only`（补充） | {counts.get('dp_only',0)} | {line_counts.get('dp_only',0)} | 有 DP、无 DN（待出库） |", "",
         "## 2. per_delivered 与 DN 的对照", "",
         f"- 有已提交 DN 的 SO：**{len(submitted)}**；全部 `per_delivered<100`："
         f"**{sum(1 for x in submitted if x['pd_lt100'])}** 个。",
         f"- 其中 `per_delivered≥99` 的 **{sum(1 for p in sub_pd if p >= 99)}** 个（残余 <1%），"
         f"`<99` 的 **{sum(1 for p in sub_pd if p < 99)}** 个；"
         f"已提交 DN 对应的 {len(sub_lines)} 行中，仍有未履约量的 **{sub_unf}** 行。",
         "- 单据显示“DN 已提交”，但 SO 的 `per_delivered` 未达 100；"
         "差额可能是**未交付剩余**，也可能是**未回写**——DN 本身不能区分。",
         "- `dn_unsubmitted` / `dp_only` / `none` 的 SO：per_delivered 见 CSV 逐行。", "",
         "## 3. 逐行清单（摘要）", "",
         "| SO 哈希 | 状态 | per_delivered | DP | DN 状态 | class | 行数 |",
         "|---|---|---:|---|---|---|---:|"]
    for x in so_rows:
        n = sum(1 for y in line_rows if y["so_hash"] == x["so_hash"])
        L.append(f"| `{x['so_hash']}` | {x['status']} | {x['per_delivered']} | "
                 f"{'有' if x['dp_exists'] else '无'} / {x['dp_flags']} | "
                 f"{x['dn_statuses'] or '无'} | {x['class_']} | {n} |")
    L += ["", f"逐行明细（{len(line_rows)} 行）见 `dn_linkage_check.csv`。", "",
          "## 4. 能证明什么 / 不能证明什么", "",
          "- 能证明：系统内是否存在 Delivery Plan 与 Delivery Note，以及 DN 的 docstatus；"
          "对已提交 DN 的 SO，可对照 per_delivered 是否同步。",
          "- 不能证明：无 DN 的 SO 是否线下发货、DN 未提交是否已实物出库、"
          "DP `is_dn_pending` 之外的仓内状态；这些需仓储/财务确认。",
          "- **不得**把“无 DN”直接等同于“真缺货”。", "",
          "## 5. 复现", "",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_dn_linkage.py",
          "uv run python scripts/check_secrets.py",
          "```", ""]
    (OUT / "dn_linkage_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote dn_linkage_check.csv/md; requests", c.gets,
          "sos", len(so_rows), "lines", len(line_rows), "classes", dict(counts))


if __name__ == "__main__":
    main()
