#!/usr/bin/env python3
"""Board PoC runner (standalone): probe sellers → ingest xlsx → negate/harvest candidates.

Does not require IvyeaOps server up. Reuses SELLFOX_API.client and the same
column map / rule thresholds as IvyeaOps sellfox_ingest + optimizer search-term levers.

Usage (from fzh-data root):
  uv run python ai_access_poc/board/scripts/sellfox_board_poc.py --xlsx path/to.xlsx
  uv run python ai_access_poc/board/scripts/sellfox_board_poc.py --pull --shop-name TOODDLY-Daneey-US
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

BOARD = Path(__file__).resolve().parents[1]
OUT = BOARD / "out"
CACHE = BOARD / "cache"

COL_MAP = {
    "query": "用户搜索词",
    "cost": "广告花费",
    "clicks": "广告点击量",
    "orders": "广告订单量",
    "sales": "广告销售额",
    "impressions": "广告曝光量",
    "campaign_id": "广告活动ID",
    "ad_group_id": "广告组ID",
    "match_type": "匹配类型",
}


def normalize_xlsx(xlsx_path: Path) -> list[dict]:
    import pandas as pd

    df = pd.read_excel(xlsx_path)
    rows = []
    for _, r in df.iterrows():
        item = {}
        for eng, zh in COL_MAP.items():
            v = r.get(zh)
            if eng in ("cost", "sales", "clicks", "orders", "impressions"):
                try:
                    item[eng] = 0.0 if pd.isna(v) else float(v)
                except (TypeError, ValueError):
                    item[eng] = 0.0
            elif eng in ("campaign_id", "ad_group_id"):
                if pd.isna(v):
                    item[eng] = None
                else:
                    item[eng] = str(int(v)) if isinstance(v, float) else str(v)
            else:
                item[eng] = None if pd.isna(v) else str(v)
        if item.get("query"):
            rows.append(item)
    return rows


def aggregate(rows: list[dict]) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for r in rows:
        k = (str(r.get("campaign_id")), str(r.get("query")))
        b = out.get(k)
        if b is None:
            b = {
                "query": r.get("query"),
                "campaign_id": r.get("campaign_id"),
                "ad_group_id": r.get("ad_group_id"),
                "match_type": r.get("match_type"),
                "spend": 0.0,
                "sales": 0.0,
                "orders": 0.0,
                "clicks": 0.0,
                "impressions": 0.0,
            }
            out[k] = b
        b["spend"] += float(r.get("cost") or 0)
        b["sales"] += float(r.get("sales") or 0)
        b["orders"] += float(r.get("orders") or 0)
        b["clicks"] += float(r.get("clicks") or 0)
        b["impressions"] += float(r.get("impressions") or 0)
    return out


def metrics(b: dict) -> dict:
    s, sa, ck, od = b["spend"], b["sales"], b["clicks"], b["orders"]
    return {
        "spend": round(s, 2),
        "sales": round(sa, 2),
        "orders": int(od),
        "clicks": int(ck),
        "impressions": int(b["impressions"]),
        "acos": (s / sa) if sa else None,
        "rpc": (sa / ck) if ck else None,
    }


def run_rules(agg: dict, *, neg_clicks: int = 15, harvest_orders: int = 3, target_acos: float = 0.30) -> list[dict]:
    cands = []
    for (cid, q), b in agg.items():
        m = metrics(b)
        if m["clicks"] >= neg_clicks and m["orders"] == 0:
            cands.append(
                {
                    "lever": "否词",
                    "op_type": "negate_keyword",
                    "advisory_only": True,
                    "target_name": q,
                    "campaign_id": cid,
                    "metrics": m,
                    "rule": f"搜索词「{q}」{m['clicks']}点击/0单（≥{neg_clicks}）→ 否定建议",
                    "payload": {
                        "op_type": "negate_keyword",
                        "campaign_id": cid,
                        "keyword_text": q,
                        "match_type": "negativeExact",
                    },
                    "write_blocked": "sellfox ad write API absent",
                }
            )
        elif m["orders"] >= harvest_orders and m["acos"] is not None and m["acos"] <= target_acos:
            sug = round((m["rpc"] or 0) * target_acos, 2)
            cands.append(
                {
                    "lever": "收割",
                    "op_type": "add_keyword",
                    "advisory_only": True,
                    "target_name": q,
                    "campaign_id": cid,
                    "metrics": m,
                    "rule": f"搜索词「{q}」{m['orders']}单、ACOS {m['acos']:.0%} → 收割建议",
                    "harvest": {"query": q, "suggested_bid": sug, "match_type": "EXACT"},
                    "write_blocked": "sellfox ad write API absent",
                }
            )
    return cands


def probe_sellers() -> dict:
    from SELLFOX_API.client import SellfoxClient, SellfoxConfig

    c = SellfoxClient(SellfoxConfig.from_env())
    shops = c.list_shops()
    return {"ok": True, "mode": c.config.mode, "count": len(shops), "names": [s.get("name") for s in shops[:5]]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", type=Path, help="Existing Sellfox search-term xlsx")
    ap.add_argument("--pull", action="store_true", help="Live pull via proxy")
    ap.add_argument("--shop-name", default=os.environ.get("SELLFOX_POC_SHOP_NAME", "TOODDLY-Daneey-US"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--neg-clicks", type=int, default=15)
    ap.add_argument("--harvest-orders", type=int, default=3)
    ap.add_argument("--target-acos", type=float, default=0.30)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    print("=== B2 probe sellers ===")
    try:
        probe = probe_sellers()
        print(json.dumps(probe, ensure_ascii=False))
        (OUT / "sellers_probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print("probe_failed", e)
        probe = {"ok": False, "error": str(e)}

    xlsx = args.xlsx
    if args.pull:
        from SELLFOX_API.client import SellfoxClient, SellfoxConfig

        c = SellfoxClient(SellfoxConfig.from_env())
        pulled = c.pull_sp_search_term(days=args.days, shop_name=args.shop_name, out_dir=CACHE)
        xlsx = Path(pulled["filepath"])
        print("pulled", xlsx)
    if xlsx is None:
        # default shell report
        reports = ROOT / "ai_access_poc" / "open_webui" / "reports"
        cands = sorted(reports.glob("SearchTerm_TOODDLY-Daneey-US_*.xlsx"))
        if not cands:
            raise SystemExit("No xlsx; pass --xlsx or --pull")
        xlsx = cands[-1]
        print("using", xlsx)

    print("=== B4 ingest ===")
    rows = normalize_xlsx(xlsx)
    cache_payload = {
        "dataset": "sp_search_term_report",
        "mode": "aggregate",
        "shop_name": args.shop_name,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "source_xlsx": str(xlsx),
        "rows": rows,
    }
    cache_path = CACHE / "sp_search_term_report__poc.json"
    cache_path.write_text(json.dumps(cache_payload, ensure_ascii=False), encoding="utf-8")
    print("rows", len(rows), "cache", cache_path)

    print("=== B5 optimizer search-term levers (read-only) ===")
    agg = aggregate(rows)
    cands = run_rules(agg, neg_clicks=args.neg_clicks, harvest_orders=args.harvest_orders, target_acos=args.target_acos)
    by_lever = defaultdict(int)
    for c in cands:
        by_lever[c["lever"]] += 1
    summary = {
        "shop_name": args.shop_name,
        "unique_terms": len(agg),
        "candidates": len(cands),
        "by_lever": dict(by_lever),
        "write_path": "DISABLED — NotImplemented / export CSV only",
        "thresholds": {"neg_clicks": args.neg_clicks, "harvest_orders": args.harvest_orders, "target_acos": args.target_acos},
    }
    print(json.dumps(summary, ensure_ascii=False))
    (OUT / "candidates.json").write_text(
        json.dumps({"summary": summary, "candidates": cands}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_path = OUT / "candidates.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["lever", "op_type", "target_name", "campaign_id", "clicks", "orders", "spend", "sales", "acos", "rule"])
        w.writeheader()
        for c in cands:
            m = c["metrics"]
            w.writerow(
                {
                    "lever": c["lever"],
                    "op_type": c["op_type"],
                    "target_name": c["target_name"],
                    "campaign_id": c.get("campaign_id"),
                    "clicks": m["clicks"],
                    "orders": m["orders"],
                    "spend": m["spend"],
                    "sales": m["sales"],
                    "acos": m["acos"],
                    "rule": c["rule"],
                }
            )
    print("wrote", OUT / "candidates.json", csv_path)
    print("=== B6 note: review ai_access_poc/board/docs/reference/deviations.md ===")
    print("done")


if __name__ == "__main__":
    main()
