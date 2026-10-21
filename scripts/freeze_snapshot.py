# -*- coding: utf-8 -*-
"""冻结补货原型：记录代码版本、输入哈希、表行数与关键参数

用法：
  uv run python scripts/freeze_snapshot.py --label 2026-10-21-prototype
输出：
  D:/Work/fzh-order-store/FREEZE_<label>.json / .md
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import duckdb

DEFAULT_OUT = Path("D:/Work/fzh-order-store")
INPUTS = [
    "bom.tsv", "bom_items.tsv", "items_attr.tsv", "bin.tsv", "po_items.tsv",
    "ks_items.tsv", "item_groups.tsv", "item_groups_full.tsv",
    "nd_items.tsv", "variant_attrs.tsv", "sku_map.tsv", "po_open.tsv",
]
SCRIPTS = [
    "scripts/forecast_order_store.py", "scripts/forecast_ensemble.py",
    "scripts/forecast_replenishment_v3.py", "scripts/forecast_shipment_plan.py",
    "scripts/nd_button_gap_report.py", "scripts/replenishment_trace.py",
    "scripts/tongtool_stock_snapshot.py", "scripts/tongtool_po_snapshot.py",
    "scripts/warehouse_map.py", "scripts/freeze_snapshot.py",
]
TABLES = [
    "gs_orders", "orders_unified", "fba_demand", "sku_map", "monthly_series",
    "forecast_sku_wh", "backtest_summary", "tongtool_stock", "stock_latest",
    "tongtool_po", "tongtool_po_open", "replenishment_v3", "replenishment_pool",
    "replenishment_pool_ship", "three_pl_stock", "bom", "bom_item", "bom_exploded",
    "component_ship_plan", "component_ship_summary", "button_overadd_candidates",
    "input_health",
]


def sha(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--label", default=dt.date.today().isoformat() + "-prototype")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()
    out = Path(args.out)
    repo = Path(args.repo)

    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "-C", str(repo), "branch", "--show-current"],
                            capture_output=True, text=True).stdout.strip()

    con = duckdb.connect(str(out / "order_store.duckdb"), read_only=True)
    counts = {}
    for t in TABLES:
        try:
            counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        except Exception:
            counts[t] = None
    health = con.execute("SELECT * FROM input_health").df().to_dict("records")
    con.close()

    payload = {
        "label": args.label,
        "frozen_at": dt.datetime.now().isoformat(timespec="seconds"),
        "status": "experimental prototype — 未验收，不得直接用于下单",
        "git": {"branch": branch, "commit": commit},
        "parameters": {
            "forecast": {"methods": ["ma3", "ma6", "ma12", "croston", "tsb", "ens5"],
                         "horizon_months": 3, "origins": 6, "min_months": 3,
                         "backtest_min_sold_months": 12},
            "replenishment": {"lead_days_finished": 45, "safety_days_finished": 30,
                              "rop_days": 75},
            "supply": "available + GREATEST(intransit, PO open)",
        },
        "inputs": {f: {"sha256": sha(out / f), "exists": (out / f).exists()} for f in INPUTS},
        "scripts": {f: {"sha256": sha(repo / f), "exists": (repo / f).exists()} for f in SCRIPTS},
        "tables": counts,
        "input_health": health,
        "known_limits": [
            "预测/补货为原型，未经 #300/#301 验收",
            "intransit 与 PO 重叠已按 max 计一次，但仍有 27 个 SKU×仓 PO > intransit（可能含未发货部分）",
            "皮壳 -Cover 与不带后缀 SKU 是独立数量桶；实物同池未证",
            "3PL 只有 Cranbury 有库存，权威仍是 Wayfair 后台导出",
            "内胆无独立库存口径；KS BOM 不含 PP 棉/包装",
            "PO 源缺失时 suggested_qty 为 NULL，不当作 0 供给",
        ],
    }

    (out / f"FREEZE_{args.label}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 补货原型冻结：{args.label}",
        "",
        f"- 冻结时间：{payload['frozen_at']}",
        f"- 代码：`{branch}` @ `{commit}`",
        f"- 状态：**{payload['status']}**",
        "",
        "## 输入文件（SHA256）",
        "",
        "| 文件 | 存在 | SHA256 |",
        "|---|---|---|",
    ]
    for f, v in payload["inputs"].items():
        lines.append(f"| {f} | {v['exists']} | `{(v['sha256'] or '')[:16]}` |")
    lines += ["", "## 表行数", "", "| 表 | 行数 |", "|---|---|"]
    for t, n in counts.items():
        lines.append(f"| {t} | {n if n is not None else '—'} |")
    lines += ["", "## 输入健康度", "", "```json",
              json.dumps(health, ensure_ascii=False, indent=2), "```", "", "## 已知限制", ""]
    lines += [f"- {x}" for x in payload["known_limits"]]
    (out / f"FREEZE_{args.label}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"frozen: {out/('FREEZE_'+args.label+'.md')}")


if __name__ == "__main__":
    main()
