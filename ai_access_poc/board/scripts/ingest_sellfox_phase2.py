#!/usr/bin/env python3
"""Phase2 ingest: entities + Targeting/Campaign reports + asin_profit → sellfox_cache.

OPTIONAL warm-up / boil-the-lake. On-demand path is fetch_dataset → ensure_dataset;
colleagues do not need this script to use 数据浏览 / 优化建议.

Default shop: BJRYECLTD-US (596841). Search-term alone: ingest_sellfox_search_term.py.

Run via::

  powershell -File ai_access_poc/board/scripts/ingest_sellfox_phase2.ps1
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    fzh = Path(os.environ.get("FZH_DATA_ROOT") or Path(__file__).resolve().parents[3])
    ivy = Path(os.environ.get("IVYEAOPS_ROOT") or (fzh.parent / "IvyeaOps-sellfox"))
    server = ivy / "server"
    if not (server / "app").is_dir():
        print(f"IvyeaOps server not found: {server}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(server))
    os.environ.setdefault("FZH_DATA_ROOT", str(fzh))
    os.environ.setdefault("SELLFOX_READONLY_POC", "1")
    os.environ.setdefault("SELLFOX_WINDOW_MODE", "aggregate")

    shop = os.environ.get("SELLFOX_POC_SHOP_NAME") or "BJRYECLTD-US"
    days = int(os.environ.get("SELLFOX_POC_DAYS") or "30")
    skip_reports = os.environ.get("SELLFOX_POC_SKIP_REPORTS", "").strip() in ("1", "true", "yes")
    skip_profit = os.environ.get("SELLFOX_POC_SKIP_PROFIT", "").strip() in ("1", "true", "yes")

    from app.core.config import settings  # noqa: E402
    from app.services import sellfox_ingest as ing  # noqa: E402
    from app.services import sellfox_openapi as sf  # noqa: E402

    data_dir = Path(settings.data_dir)
    client = sf._client()
    shop_id, shop_name = client.resolve_shop(shop_name=shop)

    report: dict = {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "days": days,
        "steps": {},
    }

    # 1) entities first (bid / budget / product ads)
    ent = ing.ingest_entities(
        data_dir, shop_id=shop_id, shop_name=shop_name, client=client
    )
    report["steps"]["entities"] = ent
    print(json.dumps({"entities": ent}, ensure_ascii=False, indent=2))

    # 2) performance reports
    if not skip_reports:
        for dataset, code, prefix in (
            ("sp_search_term_report", "adSearchTermReport", "SearchTerm"),
            ("sp_keyword_report", "adTargeringReport", "Targeting"),
            ("sp_campaign_report", "adCampaignReport", "Campaign"),
        ):
            step = ing.pull_and_ingest_report(
                data_dir,
                dataset=dataset,
                report_type_code=code,
                file_prefix=prefix,
                shop_name=shop_name,
                days=days,
                client=client,
            )
            report["steps"][dataset] = step
            print(json.dumps({dataset: step}, ensure_ascii=False, indent=2))

    # 3) profit
    if not skip_profit:
        profit = ing.ingest_asin_profit(
            data_dir,
            shop_id=shop_id,
            shop_name=shop_name,
            days=min(days, 30),
            client=client,
        )
        report["steps"]["asin_profit"] = profit
        print(json.dumps({"asin_profit": profit}, ensure_ascii=False, indent=2))

    # boil-the-lake summary
    summary = {
        "shop": shop_name,
        "shop_id": shop_id,
        "sid": ent.get("sid"),
        "counts": {
            k: (v.get("rows") if isinstance(v, dict) else None)
            for k, v in report["steps"].items()
            if k != "entities"
        },
        "entity_counts": (ent.get("datasets") or {}),
    }
    report["summary"] = summary
    out = Path(fzh) / "ai_access_poc" / "board" / "out"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"phase2_ingest_{shop_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "wrote": str(path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
