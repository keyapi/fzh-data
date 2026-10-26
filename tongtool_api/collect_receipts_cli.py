#!/usr/bin/env python3
"""Run a bounded, overlapping-window receipt collection (read-only)."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tongtool_api.mcp_http import McpClient, primary_credentials
from tongtool_api.receipt_collector import (
    assert_outside_repo,
    build_summary,
    collect_receipts,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect Tongtool purchase receipts in overlapping windows (read-only)"
    )
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    parser.add_argument("--po-code", default=None)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--overlap-days", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--interval", type=float, default=13.0)
    parser.add_argument("--cache-dir", default=str(Path(tempfile.gettempdir()) / "tongtool_receipt_cache"))
    parser.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "tongtool_receipt_summary.json"))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--allow-truncated", action="store_true")
    args = parser.parse_args()

    cache_dir = None if args.no_cache else Path(args.cache_dir)
    out_path = Path(args.out)
    if cache_dir is not None:
        assert_outside_repo(cache_dir, "cache-dir")
    assert_outside_repo(out_path, "out")

    key, secret = primary_credentials()
    client = McpClient(key, secret, client_name="fzh-receipt-collector")
    result = collect_receipts(
        client.call,
        args.date_from,
        args.date_to,
        window_days=args.window_days,
        overlap_days=args.overlap_days,
        po_code=args.po_code,
        page_size=args.page_size,
        max_pages=args.max_pages,
        cache_dir=cache_dir,
        interval=args.interval,
    )
    summary = build_summary(result)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        k: summary[k] for k in (
            "input_count", "unique_count", "overlap_duplicate_count",
            "possible_duplicate_count", "distinct_po", "distinct_sku",
            "cache_hits", "truncated_windows",
        )
    }, ensure_ascii=False))
    print("OUT", out_path)
    if summary["truncated_windows"] and not args.allow_truncated:
        print("TRUNCATED", json.dumps(summary["truncated_windows"], ensure_ascii=False), file=sys.stderr)
        print("Incomplete: increase --max-pages or narrow the window, then rerun.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
