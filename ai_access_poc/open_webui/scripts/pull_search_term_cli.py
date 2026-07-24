#!/usr/bin/env python3
"""Host-side smoke test for Sellfox SP search-term pull (no Open WebUI)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "SELLFOX_API"))

from client import SellfoxClient, SellfoxConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull SP search-term report via SellfoxClient")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--shop", type=str, default=None, help="Shop id")
    parser.add_argument("--shop-name", type=str, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reports",
    )
    args = parser.parse_args()

    client = SellfoxClient(SellfoxConfig.from_env())
    client.authenticate()
    result = client.pull_sp_search_term(
        days=args.days,
        shop_id=args.shop,
        shop_name=args.shop_name,
        out_dir=args.out,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
