#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1b：把 EN 单据只读查询结果落成结构化 JSON（单个客户码 / 物料）。

复用 EN_API/item_shipment_status.py 的 build_context，不重复实现查询。
只输出数量/单据号/物料/仓库，不输出客户名、地址等 PII。

关键修正：
  - DN 保留 Delivery Note Item.name（dn_line_id），不再拿 so_line_id 当 DN 行键。
  - Job Card 按工序聚合，不再跨工序求和；首道/末道分开，无卡为 unknown。
  - 补 Manufacture Stock Entry（已提交）作为生产入库事实；不再用 JC 求和替代。
  - 未发量给出互斥分解（死单/在产/无计划/超发），并与 totals.open_qty 对平。

用法：
  uv run python g1b_en_extract.py --customer-code "C/Linen-Natural-194-688-wow"
  uv run python g1b_en_extract.py --item "PK#KS0001-XMMBS-194-HEMPNATURAL"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
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


def _op_order(wo: dict) -> list[str]:
    ops = wo.get("operations") or []

    def seq(o):
        v = o.get("sequence_id")
        if v is None:
            v = o.get("sequence")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    values = [seq(o) for o in ops]
    if any(v is not None and v != 0 for v in values):
        ordered = sorted(ops, key=lambda o: (seq(o) if seq(o) is not None else 10**9))
    else:
        ordered = ops  # 保留路由原始顺序，不能按工序名重排
    order = [str(o.get("operation")) for o in ordered if o.get("operation")]
    return list(dict.fromkeys(order))


def jc_summary(jc_map: dict, wos: list[dict]) -> dict:
    """按工序聚合 JC；同一工序多卡求和（批量/菲号卡），不跨工序求和。"""
    wo_by_name = {w.get("name"): w for w in wos}
    out = {}
    for wo_name, cards in (jc_map or {}).items():
        wo = wo_by_name.get(wo_name, {})
        by_op: dict[str, list[dict]] = defaultdict(list)
        for c in cards:
            by_op[str(c.get("operation") or "?")].append(c)
        ops = {}
        for op, rows in by_op.items():
            qty = [float(c.get("total_completed_qty") or 0) for c in rows]
            ops[op] = {
                "cards": len(rows),
                "sum_qty": round(sum(qty), 2) if qty else None,
                "max_qty": round(max(qty), 2) if qty else None,
                "for_quantity_sum": round(sum(float(c.get("for_quantity") or 0) for c in rows), 2),
                "jc_ids": [c.get("name") for c in rows if c.get("name")],
                "statuses": sorted({c.get("status") for c in rows if c.get("status")}),
                "docstatuses": sorted({c.get("docstatus") for c in rows
                                       if c.get("docstatus") is not None}),
            }
        order = _op_order(wo)
        first_op = order[0] if order else None
        last_op = order[-1] if order else None
        with_cards = [op for op in order if op in ops]
        last_card_op = with_cards[-1] if with_cards else None
        out[wo_name] = {
            "cards": len(cards),
            "operations": ops,
            "operation_order": order,
            "first_operation": first_op,
            "last_operation": last_op,
            "first_op_qty": ops.get(first_op, {}).get("sum_qty") if first_op else None,
            "last_op_qty": ops.get(last_op, {}).get("sum_qty") if last_op else None,
            "last_card_operation": last_card_op,
            "last_card_qty": ops.get(last_card_op, {}).get("sum_qty") if last_card_op else None,
            "statuses": sorted({c.get("status") for c in cards if c.get("status")}),
        }
    return out


def open_breakdown(so_rows: list[dict], totals: dict) -> dict:
    """未发量互斥分解：死单 / 在产 / 无计划 / 超发；作废单单列。"""
    voided = 0.0
    dead = 0.0
    in_progress = 0.0
    no_plan = 0.0
    over = 0.0
    buckets = {"dead": [], "in_progress": [], "no_plan": [], "over_delivered": []}
    for r in so_rows:
        open_qty = float(r.get("open_qty") or 0)
        status = str(r.get("so_status") or "")
        docstatus = r.get("so_docstatus")
        is_voided = (docstatus == 2) or (status == "Cancelled")
        if is_voided:
            voided += open_qty
            continue
        if open_qty < 0:
            over += open_qty
            buckets["over_delivered"].append({"so": r.get("so"), "open_qty": open_qty})
            continue
        if open_qty == 0:
            continue
        anoms = r.get("anomalies") or []
        item = {"so": r.get("so"), "open_qty": open_qty}
        if "死单(Closed未发)" in anoms:
            dead += open_qty
            buckets["dead"].append(item)
        elif r.get("wos"):
            in_progress += open_qty
            buckets["in_progress"].append(item)
        else:
            no_plan += open_qty
            buckets["no_plan"].append(item)
    total = dead + in_progress + no_plan + over
    report_open = float(totals.get("open_qty") or 0)
    return {
        "voided_qty": round(voided, 2),
        "dead_qty": round(dead, 2),
        "in_progress_qty": round(in_progress, 2),
        "no_plan_qty": round(no_plan, 2),
        "over_delivered_qty": round(over, 2),
        "reconciled_open_qty": round(total, 2),
        "reported_open_qty": round(report_open, 2),
        "difference": round(total - report_open, 2),
        "buckets": buckets,
        "note": "有效单未发 = 死单 + 在产 + 无计划 + 超发(负)；作废单不计入 open",
    }


def fetch_manufacture_stock_entries(wo_names: list[str], item_codes: list[str],
                                    base_url: str, key: str, secret: str, sleep_s: float):
    """已提交 Manufacture Stock Entry 的成品入库量。返回 (rows, error)。"""
    if not wo_names:
        return [], None
    raw = []
    try:
        for chunk in iss.chunks(wo_names, iss.IN_CHUNK):
            filters = [
                ["Stock Entry", "stock_entry_type", "=", "Manufacture"],
                ["Stock Entry", "docstatus", "=", 1],
                ["Stock Entry", "work_order", "in", chunk],
            ]
            raw.extend(iss.paginated_get(
                "Stock Entry", base_url, key, secret, filters,
                ["name", "stock_entry_type", "docstatus", "posting_date", "work_order",
                 "from_warehouse", "to_warehouse", "company"],
                fallback_fields=["name", "stock_entry_type", "docstatus", "posting_date",
                                 "work_order"],
                label="SE(Manufacture)",
            ))
    except Exception as e:  # noqa: BLE001 - 查询失败要显式返回，不能当没有 SE
        return [], f"{type(e).__name__}: {e}"

    ses = iss.dedupe_by(raw, "name")
    item_set = set(item_codes)
    out = []
    unlocated_missing = False
    for i, se in enumerate(ses):
        d = iss.get_single("Stock Entry", se["name"], base_url, key, secret)
        if i + 1 < len(ses):
            time.sleep(sleep_s)
        if not d:
            wo = se.get("work_order")
            if not wo:
                unlocated_missing = True
            out.append({"se": se["name"], "work_order": wo, "status": "missing_doc",
                        "finished_qty": None, "lines": []})
            continue
        lines = []
        finished = 0.0
        finished_lines = 0
        matched_lines = 0
        uom_issue = False
        for line in d.get("items", []):
            rec = {
                "line": line.get("name"),
                "item_code": line.get("item_code"),
                "qty": float(line.get("qty") or 0),
                "uom": line.get("uom"),
                "stock_uom": line.get("stock_uom"),
                "is_finished_item": bool(line.get("is_finished_item")),
                "target_warehouse": line.get("t_warehouse"),
                "source_warehouse": line.get("s_warehouse"),
            }
            lines.append(rec)
            if not rec["is_finished_item"]:
                continue
            finished_lines += 1
            if rec["item_code"] not in item_set:
                continue
            matched_lines += 1
            if not rec["uom"] or not rec["stock_uom"]:
                uom_issue = True
            elif rec["uom"] != rec["stock_uom"]:
                uom_issue = True
            finished += rec["qty"]
        if finished_lines == 0:
            status = "no_finished_lines"
        elif matched_lines == 0:
            status = "no_matching_finished_line"
        elif uom_issue:
            status = "uom_unknown"
        else:
            status = "ok"
        out.append({
            "se": se["name"],
            "posting_date": d.get("posting_date"),
            "docstatus": d.get("docstatus"),
            "work_order": d.get("work_order") or se.get("work_order"),
            "from_warehouse": d.get("from_warehouse"),
            "to_warehouse": d.get("to_warehouse"),
            "status": status,
            "finished_qty": round(finished, 2) if status == "ok" else None,
            "finished_lines": finished_lines,
            "matched_finished_lines": matched_lines,
            "lines": lines,
        })
    return out, ("missing_doc_without_work_order" if unlocated_missing else None)


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

    field_issues = []
    so_rows = []
    for r in ctx.get("so_rows", []):
        if float(r.get("open_qty") or 0) > 0:
            for f in ("so_delivery_date", "warehouse", "uom"):
                if not r.get(f):
                    field_issues.append({"so": r.get("so"), "missing": f})
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
            "anomalies": r.get("anomalies", []),
            "wos": [w.get("name") for w in (r.get("wos") or [])],
            "pps": [p.get("pp") for p in (r.get("pps") or [])],
        })

    dn_rows = []
    for d in ctx.get("dn_rows", []):
        dn_rows.append({
            "dn": d.get("dn"),
            "dn_line_id": d.get("dn_line_id"),
            "dn_date": d.get("dn_date"),
            "dn_status": d.get("dn_status"),
            "dn_docstatus": d.get("dn_docstatus"),
            "is_return": d.get("is_return"),
            "so": d.get("so"),
            "so_line_id": d.get("so_line_id"),
            "item_code": d.get("item_code"),
            "warehouse": d.get("warehouse"),
            "uom": d.get("uom"),
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

    jc = jc_summary(ctx.get("jc_map", {}), ctx.get("wos", []))
    se_rows, se_error = fetch_manufacture_stock_entries(
        [w["name"] for w in wos], ctx.get("item_codes", []),
        iss.ENV_URLS["prod"], key, secret, args.sleep,
    )

    four_way = {}
    se_by_wo: dict[str, list[dict]] = defaultdict(list)
    for s in se_rows:
        if s.get("work_order"):
            se_by_wo[s["work_order"]].append(s)
    for w in ctx.get("wos", []):
        wo_name = w.get("name")
        j = jc.get(wo_name, {})
        last_qty = j.get("last_op_qty")
        se_for_wo = se_by_wo.get(wo_name, [])
        bad_se = [s for s in se_for_wo if s.get("status") != "ok"]
        if se_for_wo and not bad_se:
            se_qty = sum(float(s.get("finished_qty") or 0) for s in se_for_wo)
            se_status = "ok"
        elif bad_se:
            se_qty = None
            se_status = bad_se[0].get("status") or "unknown"
        elif se_error:
            se_qty = None
            se_status = "query_error"
        else:
            se_qty = 0.0
            se_status = "none"
        pending = None
        if last_qty is not None and se_qty is not None:
            pending = round(last_qty - se_qty, 2)
        last_card_qty = j.get("last_card_qty")
        pending_last_card = None
        if last_card_qty is not None and se_qty is not None:
            pending_last_card = round(last_card_qty - se_qty, 2)
        four_way[wo_name] = {
            "jc_present": bool(j),
            "first_operation": j.get("first_operation"),
            "last_operation": j.get("last_operation"),
            "first_op_qty": j.get("first_op_qty"),
            "last_op_qty": last_qty,
            "last_card_operation": j.get("last_card_operation"),
            "last_card_qty": last_card_qty,
            "se_status": se_status,
            "se_finished_qty": round(se_qty, 2) if se_qty is not None else None,
            "produced_pending_stock_in": pending,
            "produced_pending_stock_in_last_card": pending_last_card,
        }

    result = {
        "okf": "v0.1",
        "type": "Experiment-Results",
        "title": "G1b EN 单据结构化导出（只读）",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "system": iss.ENV_URLS["prod"],
        "query": {"customer_code": args.customer_code, "item": args.item},
        "legacy_lead_display_excluded": True,
        "item_codes": ctx.get("item_codes", []),
        "master_items": [
            {"name": m.get("name"), "item_name": m.get("item_name"), "item_group": m.get("item_group")}
            for m in ctx.get("master_items", [])
        ],
        "totals": ctx.get("totals", {}),
        "open_breakdown": open_breakdown(so_rows, ctx.get("totals", {})),
        "so_rows": so_rows,
        "dn_rows": dn_rows,
        "wos": wos,
        "jc_summary": jc,
        "se_rows": se_rows,
        "se_query_error": se_error,
        "production_four_way": four_way,
        "pp_rows": pp_rows,
        "anomalies": ctx.get("anomalies", []),
        "field_issues": field_issues,
    }

    out = Path(args.out) if args.out else OUT / f"g1b_en_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {out}")
    print(f"  SO {len(so_rows)}；DN 行 {len(dn_rows)}；WO {len(wos)}；PP {len(pp_rows)}；"
          f"SE {len(se_rows)} err={se_error}")
    print(f"  totals: {json.dumps(result['totals'], ensure_ascii=False)}")
    print(f"  open: {json.dumps(result['open_breakdown'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
