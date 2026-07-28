"""Pull SP core 7 reports for audit shop via SellfoxClient (proxy preferred).

Usage:
  uv run python advertise/scripts/pull_sp7_verify.py --shop-id 596841 --days 30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from SELLFOX_API.client import SellfoxClient, SellfoxConfig  # noqa: E402

REPORTS = [
    ("campaign", "adCampaignReport", "Campaign"),
    ("targeting", "adTargeringReport", "Targeting"),
    ("search_term", "adSearchTermReport", "SearchTerm"),
    ("placement", "adSpaceReport", "Placement"),
    ("ad_group", "adGroupReport", "AdGroup"),
    ("ad_product", "adProductReport", "AdvertisedProduct"),
    ("purchased_item", "adPurchasedItemReport", "PurchasedItem"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop-id", default="596841")
    ap.add_argument("--shop-name", default="BJRYECLTD-US")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "advertise" / "data")
    ap.add_argument("--max-wait", type=int, default=420)
    args = ap.parse_args()

    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    client = SellfoxClient(SellfoxConfig.from_env())
    print(f"mode={client.config.mode} shop={args.shop_id} range={start_date}..{end_date}")

    tasks: dict[str, dict] = {}
    for key, code, label in REPORTS:
        tid = client.create_report_task(args.shop_id, code, start_date, end_date)
        tasks[key] = {"id": tid, "code": code, "label": label}
        print(f"  created {label}: {tid}")
        time.sleep(2)

    pending = {t["id"] for t in tasks.values()}
    results_meta: dict[str, dict] = {}
    waited = 0
    while pending and waited < args.max_wait:
        time.sleep(5)
        waited += 5
        status = client.check_tasks(list(pending))
        for key, t in tasks.items():
            tid = t["id"]
            if tid not in pending:
                continue
            state, row = status.get(tid, ("unknown", {}))
            if state == "已生成":
                urls = row.get("downloadUrl") or []
                if not urls:
                    results_meta[key] = {"ok": False, "error": "no downloadUrl", "row_keys": list(row.keys())}
                    pending.discard(tid)
                    print(f"  FAIL {t['label']}: no URL")
                    continue
                fpath = out_dir / f"{t['label']}_{args.shop_name}_{start_date}_{end_date}.xlsx"
                size = client.download_file(urls[0], fpath)
                results_meta[key] = {
                    "ok": True,
                    "filepath": str(fpath),
                    "bytes": size,
                    "task_id": tid,
                    "code": t["code"],
                    "label": t["label"],
                    "start_date": start_date,
                    "end_date": end_date,
                    "shop_id": args.shop_id,
                    "shop_name": args.shop_name,
                    "waited_s": waited,
                }
                pending.discard(tid)
                print(f"  DONE {t['label']} ({size} bytes) -> {fpath.name}")
            elif state == "失败":
                results_meta[key] = {"ok": False, "error": "task failed", "row": row}
                pending.discard(tid)
                print(f"  FAIL {t['label']}: {row}")
        if pending:
            print(f"  [{waited}s] waiting {len(pending)}...")

    for key, t in tasks.items():
        if t["id"] in pending:
            results_meta[key] = {"ok": False, "error": "timeout", "task_id": t["id"]}

    report = {
        "pulled_at": datetime.now().isoformat(timespec="seconds"),
        "mode": client.config.mode,
        "shop_id": args.shop_id,
        "shop_name": args.shop_name,
        "start_date": start_date,
        "end_date": end_date,
        "reports": results_meta,
        "ok_count": sum(1 for v in results_meta.values() if v.get("ok")),
        "fail_count": sum(1 for v in results_meta.values() if not v.get("ok")),
    }
    meta_path = out_dir / f"_pull_meta_{args.shop_name}_{start_date}_{end_date}.json"
    meta_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"meta -> {meta_path}")
    print(f"ok={report['ok_count']} fail={report['fail_count']}")
    return 0 if report["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
