#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1b：把 EN 单据只读查询结果落成结构化 JSON（单个客户码 / 物料）。

复用 EN_API/item_shipment_status.py 的 build_context，不重复实现查询。
只输出数量/单据号/物料/仓库，不输出客户名、地址等 PII。

用法：
  uv run python g1b_en_extract.py --customer-code "C/Linen-Natural-194-688-wow"
  uv run python g1b_en_extract.py --item "PK#KS0001-XMMBS-194-HEMPNATURAL"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
OUT.mkdir(parents=True, exist_ok=True)

REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "EN_API" / "item_shipment_status.py").exists()),
    Path(__file__).resolve().parents[7],
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import EN_API.item_shipment_status as iss  # noqa: E402


def jc_summary(jc_map: dict) -> dict:
    out = {}
    for wo, cards in (jc_map or {}).items():
        out[wo] = {
            "cards": len(cards),
            "completed_qty": round(sum(float(c.get("total_completed_qty") or 0) for c in cards), 2),
            "operations": sorted({c.get("operation") for c in cards if c.get("operation")}),
            "statuses": sorted({c.get("status") for c in cards if c.get("status")}),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description="G1b EN 单据结构化导出（只读）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--customer-code")
    g.add_argument("--item")
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    key, secret = iss.load_credentials("prod", iss.resolve_env_files())
    if not key or not secret:
        print("✗ EN 生产凭证未配置", file=sys.stderr)
        return 2

    ns = SimpleNamespace(
        customer_code=args.customer_code,
        item=args.item,
        test=False,
        env_file=None,
        lead_months=3,
        sleep=args.sleep,
    )
    ctx = iss.build_context(ns, iss.ENV_URLS["prod"], key, secret)
    if ctx.get("empty"):
        print("无匹配销售订单")
        return 0

    so_rows = []
    for r in ctx.get("so_rows", []):
        so_rows.append({
            "so": r.get("so"),
            "so_status": r.get("so_status"),
            "so_docstatus": r.get("so_docstatus"),
            "transaction_date": r.get("transaction_date"),
            "so_delivery_date": r.get("so_delivery_date"),
            "line_id": r.get("line_id"),
            "item_code": r.get("item_code"),
            "customer_item_code": r.get("customer_item_code"),
            "warehouse": r.get("warehouse"),
            "uom": r.get("uom"),
            "qty": r.get("qty"),
            "delivered_qty": r.get("delivered_qty"),
            "shipped_dn": r.get("shipped_dn"),
            "draft_dn": r.get("draft_dn"),
            "open_qty": r.get("open_qty"),
            "lead_date": r.get("lead_date"),
            "anomalies": r.get("anomalies", []),
            "wos": [w.get("name") for w in (r.get("wos") or [])],
            "pps": [p.get("pp") for p in (r.get("pps") or [])],
        })

    dn_rows = []
    for d in ctx.get("dn_rows", []):
        dn_rows.append({
            "dn": d.get("dn"),
            "dn_date": d.get("dn_date"),
            "dn_status": d.get("dn_status"),
            "dn_docstatus": d.get("dn_docstatus"),
            "is_return": d.get("is_return"),
            "so": d.get("so"),
            "so_line_id": d.get("so_line_id"),
            "item_code": d.get("item_code"),
            "warehouse": d.get("warehouse"),
            "qty": d.get("qty"),
        })

    wos = []
    for w in ctx.get("wos", []):
        wos.append({
            "name": w.get("name"),
            "status": w.get("status"),
            "docstatus": w.get("docstatus"),
            "sales_order": w.get("sales_order"),
            "production_item": w.get("production_item"),
            "qty": w.get("qty"),
            "produced_qty": w.get("produced_qty"),
            "planned_start_date": w.get("planned_start_date"),
            "planned_end_date": w.get("planned_end_date"),
            "bom_no": w.get("bom_no"),
        })

    pp_rows = []
    for p in ctx.get("pp_rows", []):
        pp_rows.append({
            "pp": p.get("pp"),
            "pp_status": p.get("pp_status"),
            "pp_date": p.get("pp_date"),
            "item_code": p.get("item_code"),
            "planned_qty": p.get("planned_qty"),
            "produced_qty": p.get("produced_qty"),
            "pending_qty": p.get("pending_qty"),
            "so": p.get("so"),
            "so_line_id": p.get("so_line_id"),
            "work_order": p.get("work_order"),
            "warehouse": p.get("warehouse"),
        })

    result = {
        "okf": "v0.1",
        "type": "Experiment-Results",
        "title": "G1b EN 单据结构化导出（只读）",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "system": iss.ENV_URLS["prod"],
        "query": {"customer_code": args.customer_code, "item": args.item},
        "item_codes": ctx.get("item_codes", []),
        "master_items": [
            {"name": m.get("name"), "item_name": m.get("item_name"), "item_group": m.get("item_group")}
            for m in ctx.get("master_items", [])
        ],
        "totals": ctx.get("totals", {}),
        "so_rows": so_rows,
        "dn_rows": dn_rows,
        "wos": wos,
        "jc_summary": jc_summary(ctx.get("jc_map", {})),
        "pp_rows": pp_rows,
        "anomalies": ctx.get("anomalies", []),
    }

    out = Path(args.out) if args.out else OUT / f"g1b_en_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {out}")
    print(f"  SO {len(so_rows)}；DN {len(dn_rows)}；WO {len(wos)}；PP {len(pp_rows)}")
    print(f"  totals: {json.dumps(result['totals'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
