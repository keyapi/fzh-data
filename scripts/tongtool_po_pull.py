"""只读补拉通途采购单（PO）行，带请求/分页/完整性 manifest。

- 只用 MCP 读接口 `erp2_purchase_purchaseorderquery`（GET 语义，无写）
- 分页直到返回空页，记录每页状态/行数/参数
- 输出 JSONL + .manifest.json（含 sha256 / 行数 / PO 号 / 查询窗口）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tongtool_api.mcp_http import McpClient, load_env  # noqa: E402

ENV_PATH = pathlib.Path("D:/Work/赛狐/Cursor/tongtool_api/.env")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", required=True, help="yyyy-MM-dd HH:mm:ss")
    ap.add_argument("--to", dest="date_to", required=True, help="yyyy-MM-dd HH:mm:ss")
    ap.add_argument("--out", required=True)
    ap.add_argument("--page-size", type=int, default=500)
    ap.add_argument("--sleep", type=float, default=13.0)
    args = ap.parse_args()

    env = load_env(ENV_PATH)
    client = McpClient(env["TONGTOOL_ERP2_PRIMARY_KEY"], env["TONGTOOL_ERP2_PRIMARY_SECRET"])
    rows: list[dict] = []
    pages = []
    page = 1
    while True:
        resp = client.call(
            "erp2_purchase_purchaseorderquery",
            {
                "purchaseDateFrom": args.date_from,
                "purchaseDateTo": args.date_to,
                "pageNo": page,
                "pageSize": args.page_size,
            },
        )
        payload = json.loads(resp["result"]["content"][0]["text"])
        code = payload.get("code")
        data = payload.get("datas") or {}
        arr = data.get("array") or []
        pages.append({"pageNo": page, "pageSize": args.page_size, "code": code, "rows": len(arr)})
        if code != 200:
            break
        rows.extend(arr)
        if len(arr) < args.page_size:
            break
        page += 1
        time.sleep(args.sleep)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {
        "pulled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "Tongtool ERP2 MCP erp2_purchase_purchaseorderquery (read-only)",
        "request": {
            "purchaseDateFrom": args.date_from,
            "purchaseDateTo": args.date_to,
            "page_size": args.page_size,
            "pagination": "pageNo 从 1 递增，直到返回行数 < page_size",
        },
        "pages": pages,
        "rows": len(rows),
        "po_count": len({r.get("PONum") for r in rows}),
        "po_list": sorted({r.get("PONum") for r in rows}),
        "complete": bool(pages) and pages[-1]["code"] == 200 and pages[-1]["rows"] < args.page_size,
        "output": str(out),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    pathlib.Path(str(out) + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
