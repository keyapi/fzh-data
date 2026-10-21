# -*- coding: utf-8 -*-
"""补货算例追溯：给定 EN 物料，输出预测→供给→建议→发货形态的完整链路

用法：
  uv run python scripts/replenishment_trace.py --items KS0001-QDKTR-100-DEEPGREY,KS0230-WGMSRKQCLG-60-WHITE
输出：
  D:/Work/fzh-order-store/trace_examples.md
  D:/Work/fzh-order-store/trace_examples.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

DEFAULT_OUT = Path("D:/Work/fzh-order-store")


def table(df) -> str:
    return "```\n" + df.to_string(index=False) + "\n```"


DEFAULT_ITEMS = [
    "KS0001-QDKTR-100-DEEPGREY",   # 皮壳
    "KS0230-WGMSRKQCLG-60-WHITE",  # 成品
    "KS0153-KQCLG-78-WHITEKHAKI",  # 半成品
    "KS0316-HLR-55-LINEPURPLE",    # cover_only
    "KS0249-QRJL-153-QIRUOJINLAN", # BOM 内胆停用
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--items", default=",".join(DEFAULT_ITEMS))
    args = ap.parse_args()
    out = Path(args.out)
    items = [x.strip() for x in args.items.split(",") if x.strip()]

    con = duckdb.connect(str(out / "order_store.duckdb"), read_only=True)
    md = ["# 补货算例追溯（原型，未验收，不用于下单）", ""]
    payload = {}

    for item in items:
        pool = con.execute(
            "SELECT * FROM replenishment_pool_ship WHERE item_code = ? ORDER BY suggested_qty DESC NULLS LAST",
            [item]).df()
        if pool.empty:
            md.append(f"## {item}\n\n（补货池无记录）\n")
            continue
        row = pool.iloc[0]
        wh = row["warehouse"]

        stock = con.execute("""
            SELECT s.sku,
                   CASE WHEN lower(s.sku) LIKE '%-cover' THEN 'cover' ELSE 'non-cover' END AS kind,
                   s.available, s.intransit
            FROM stock_latest s JOIN sku_map m ON m.tongtool_sku = s.sku
            WHERE m.item_code = ? AND s.warehouse = ?
            ORDER BY kind, s.available DESC
        """, [item, wh]).df()
        pos = con.execute("""
            SELECT p.sku, SUM(p.on_order) AS on_order
            FROM po_open_latest p JOIN sku_map m ON m.tongtool_sku = p.sku
            WHERE m.item_code = ? AND p.warehouse = ?
            GROUP BY 1 HAVING SUM(p.on_order) > 0
            ORDER BY 2 DESC
        """, [item, wh]).df()
        fcast = con.execute("""
            SELECT f.month, SUM(f.forecast_qty) AS qty
            FROM forecast_sku_wh f JOIN sku_map m ON m.tongtool_sku = f.sku
            WHERE m.item_code = ? AND f.warehouse = ? AND f.method = 'ens5'
              AND f.month >= strftime(CURRENT_DATE, '%Y-%m')
            GROUP BY 1 ORDER BY 1
        """, [item, wh]).df()
        hist = con.execute("""
            SELECT month, SUM(qty) AS qty FROM monthly_series
            WHERE sku IN (SELECT tongtool_sku FROM sku_map WHERE item_code = ?)
              AND warehouse = ? AND month >= '2026-07'
            GROUP BY 1 ORDER BY 1
        """, [item, wh]).df()
        comps = con.execute("""
            SELECT component_item, component_name, qty_per_unit, component_qty, flag
            FROM component_ship_plan
            WHERE en_item_code = ? AND suggested_qty > 0
            ORDER BY component_item
        """, [item]).df()

        md.append(f"## {item} @ {wh}")
        md.append(f"- 发货形态：`{row['ship_type']}`；池提示：`{row['pool_note']}`；数据标记：`{row['data_flags']}`")
        md.append(f"- 预测日均：{row['daily_forecast']}；ROP 天数：{row['rop_days']}；ROP：{row['rop_qty']}；建议：**{row['suggested_qty']}**")
        md.append(f"- 供给（{row['supply_basis']}）：{row['supply_in_rop']} = available_all {row['available_all']}"
                  f" + max(intransit {row['intransit_all']}, PO {row['on_order']})"
                  f"{'；成品扣除 cover' if row['ship_type'] not in ('皮壳', '半成品') else '；含 cover'}")
        md.append(f"- cover：available {row['cover_available']} / intransit {row['cover_intransit']} / PO {row['cover_on_order']}")
        md.append("\n**最近 3 个月实际（GS 发货口径）**\n")
        md.append(table(hist))
        md.append("\n**未来月预测（ens5）**\n")
        md.append(table(fcast))
        md.append("\n**通途库存（同物料同仓）**\n")
        md.append(table(stock))
        md.append("\n**采购未入库（同物料同仓）**\n")
        md.append(table(pos) if not pos.empty else "（无）")
        md.append("\n**发货组件（BOM 第一层）**\n")
        md.append(table(comps) if not comps.empty else "（成品直发 / 无组件）")
        md.append("")

        payload[item] = {
            "warehouse": wh, "ship_type": row["ship_type"],
            "daily_forecast": row["daily_forecast"], "rop_qty": row["rop_qty"],
            "suggested_qty": row["suggested_qty"], "supply_in_rop": row["supply_in_rop"],
            "available_all": int(row["available_all"]), "intransit_all": int(row["intransit_all"]),
            "on_order": float(row["on_order"]), "cover_available": int(row["cover_available"]),
            "cover_intransit": int(row["cover_intransit"]), "cover_on_order": float(row["cover_on_order"]),
            "data_flags": row["data_flags"], "pool_note": row["pool_note"],
            "components": comps.to_dict("records"),
            "stock": stock.to_dict("records"),
            "po": pos.to_dict("records"),
        }

    con.close()
    (out / "trace_examples.md").write_text("\n".join(md), encoding="utf-8")
    (out / "trace_examples.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out/'trace_examples.md'} ({len(items)} items)")


if __name__ == "__main__":
    main()
