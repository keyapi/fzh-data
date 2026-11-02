"""只读导出 EN `Delivery Note` 的正式 PO 字段（custom_tongtool_purchase_order）。

- 只发 GET /api/resource/Delivery Note（REST 列表查询），不写任何数据
- 分页拉全，记录请求参数/状态/行数/时间/文件 sha256 到 manifest
- 输出：en_dn_po_field_2026-10-28.json + .manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ENV_PATH = Path("D:/Work/赛狐/Cursor/EN_API/.env")
BASE = "https://erpnext.vilavi.cn"
DOCTYPE = "Delivery Note"
FIELDS = ["name", "posting_date", "customer", "custom_tongtool_purchase_order", "docstatus", "status"]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-01")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/en_dn_po_field_2026-10-28.json")
    ap.add_argument("--page-size", type=int, default=200)
    args = ap.parse_args()

    env = load_env(ENV_PATH)
    key, secret = env.get("ERP_API_KEY"), env.get("ERP_API_SECRET")
    if not key or not secret:
        raise SystemExit("missing ERP_API_KEY/ERP_API_SECRET")

    session = requests.Session()
    session.headers["Authorization"] = f"token {key}:{secret}"
    session.headers.pop("Expect", None)
    url = f"{BASE}/api/resource/{quote(DOCTYPE, safe='')}"

    filters = [["posting_date", ">=", args.since]]
    rows: list[dict] = []
    pages = []
    start = 0
    while True:
        params = {
            "filters": json.dumps(filters),
            "fields": json.dumps(FIELDS),
            "limit_page_length": str(args.page_size),
            "limit_start": str(start),
            "order_by": "posting_date asc",
        }
        resp = session.get(url, params=params, timeout=90)
        page_rows = resp.json().get("data", []) if resp.status_code == 200 else []
        pages.append({"limit_start": start, "status": resp.status_code, "rows": len(page_rows)})
        rows.extend(page_rows)
        if resp.status_code != 200 or len(page_rows) < args.page_size:
            break
        start += args.page_size

    out = Path(args.out)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    manifest = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "system": "EN production erpnext.vilavi.cn (read-only)",
        "doctype": DOCTYPE,
        "method": "GET /api/resource/Delivery Note",
        "filters": filters,
        "fields": FIELDS,
        "order_by": "posting_date asc",
        "page_size": args.page_size,
        "pages": pages,
        "rows": len(rows),
        "dn_count": len({r["name"] for r in rows}),
        "with_po_field": sum(1 for r in rows if (r.get("custom_tongtool_purchase_order") or "").strip()),
        "output": str(out),
        "sha256": digest,
        "note": "只读 GET；未写 EN；凭证取自父仓库 EN_API/.env，未落盘",
    }
    Path(str(out) + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
