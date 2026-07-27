#!/usr/bin/env python3
"""Ingest Sellfox SP search-term report into IvyeaOps-sellfox sellfox_cache.

Run with IvyeaOps server venv so ``app.services.sellfox_ingest`` imports work::

  # from fzh-data (after start script env, or with keys in open_webui/.env)
  powershell -File ai_access_poc/board/scripts/ingest_sellfox_for_ivyeaops.ps1

Or::

  cd <IvyeaOps-sellfox>/server
  set FZH_DATA_ROOT=...
  set SELLFOX_READONLY_POC=1
  .venv\\Scripts\\python.exe -m app...  # this file is under fzh-data

This script adds fzh-data board path and IvyeaOps server to sys.path.
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

    shop = os.environ.get("SELLFOX_POC_SHOP_NAME") or "TOODDLY-Daneey-US"
    days = int(os.environ.get("SELLFOX_POC_DAYS") or "7")
    xlsx = os.environ.get("SELLFOX_POC_XLSX", "").strip()

    # data_dir for IvyeaOps
    from app.core.config import settings  # noqa: E402

    data_dir = Path(settings.data_dir)
    from app.services import sellfox_ingest as ing  # noqa: E402
    from app.services import sellfox_openapi as sf  # noqa: E402

    sellers = sf.list_sellers_rows()
    print(json.dumps({"sellers": len(sellers), "sample": [s.get("name") for s in sellers[:5]]}, ensure_ascii=False))

    if xlsx:
        path = Path(xlsx)
        rows = ing.normalize_xlsx(path)
        # map shop name → sid
        hit = next((s for s in sellers if s.get("name") == shop), None)
        if not hit:
            print(f"shop {shop!r} not in sellers list", file=sys.stderr)
            return 3
        sid = hit["sid"]
        out = ing.write_cache(
            data_dir,
            sid,
            rows,
            meta={"shop_name": shop, "xlsx": str(path), "source": "local_xlsx"},
        )
        result = {"sid": sid, "shop_name": shop, "rows": len(rows), "cache": str(out)}
    else:
        result = ing.pull_and_ingest(data_dir, shop_name=shop, days=days)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
