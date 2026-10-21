#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日通途全量库存备份（API 版，只读）。

与 browser 的 `tongtu.stock.export` 不同：浏览器导出包含 `downloads/` 原始库存结存和
`output/通途合并库存结存清单`，同时派生「通途导入_头程运费_其他费用」成本模板；
本脚本用 `erp2_stocks_stocksquery` 拉全部启用仓，输出全仓 JSONL + manifest，便于服务器化。

输出（默认 D:/Work/库存备份）：
  YYYY-MM-DD/run=<run_id>/warehouse=<warehouseId>_<name>.jsonl
  YYYY-MM-DD/run=<run_id>/manifest.json
  YYYY-MM-DD/manifest.json（最后原子发布的选定 run 指针）

注意：通途商户级限流 5 次/分钟；默认 13 秒/页。全量 6 仓可能数十分钟到数小时，
建议凌晨跑，避开 EN 的 01:00 / 02:45 / 04:30 三个通途 API 同步任务。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
from datetime import datetime
from pathlib import Path

REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "tongtool_api" / "mcp_http.py").exists()),
    Path(__file__).resolve().parents[7],
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tongtool_api.mcp_http import McpClient, load_env  # noqa: E402

STOCK_QUERY_TOOL = "erp2_stocks_stocksquery"
WAREHOUSE_TOOL = "erp2_basedata_warehousequery"
CODE_OK = 200
CODE_RATE_LIMIT = 526

FIELDS = (
    "goodsSku", "warehouseName", "availableStockQuantity", "intransitStockQuantity",
    "defectsStockQuantity", "waitingShipmentStockQuantity", "goodsIdKey", "warehouseIdKey",
)


def default_env_file() -> Path:
    return Path(os.environ.get("TONGTOOL_ENV_FILE", r"D:/Work/赛狐/Cursor/tongtool_api/.env"))


def extract_payload(resp: dict) -> dict:
    if "error" in resp:
        raise RuntimeError(f"MCP error: {resp['error']}")
    texts = [c.get("text", "") for c in resp.get("result", {}).get("content", [])
             if c.get("type") == "text"]
    raw = "\n".join(texts).strip()
    if not raw:
        return {}
    if raw[0] in "{[":
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"datas": parsed}
    return {"text": raw}


def business_code(payload: dict):
    for key in ("code", "businessCode", "statusCode"):
        if isinstance(payload, dict) and key in payload:
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                return None
    return None


def rows_of(payload: dict) -> list:
    """Return a row array; raise on unrecognized shape (legal empty array is OK)."""
    datas = payload.get("datas") if isinstance(payload, dict) else None
    if isinstance(datas, list):
        return datas
    if isinstance(datas, dict):
        for key in ("array", "list", "records", "dataList", "items", "rows", "stocks"):
            if isinstance(datas.get(key), list):
                return datas[key]
        raise ValueError(f"datas 无行数组: {list(datas)[:10]}")
    raise ValueError("响应缺少 datas")


class Client:
    def __init__(self, mcp: McpClient, min_interval: float):
        self.mcp = mcp
        self.min_interval = min_interval
        self.last = 0.0
        self.requests = 0

    def _throttle(self):
        wait = self.min_interval - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()

    def call(self, name: str, args: dict) -> dict:
        self._throttle()
        self.requests += 1
        last = None
        for attempt in range(3):
            try:
                payload = extract_payload(self.mcp.call(name, args))
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
                if attempt < 2:
                    wait = 10 * (attempt + 1)
                    print(f"  [net] {type(e).__name__}，等待 {wait}s 重试", file=sys.stderr)
                    time.sleep(wait)
                    self.requests += 1
        else:
            raise last
        code = business_code(payload)
        if code == CODE_RATE_LIMIT:
            delay = 60.0
            for _ in range(4):
                print(f"  [526] 限流，等待 {delay:.0f}s", file=sys.stderr)
                time.sleep(delay)
                self.requests += 1
                payload = extract_payload(self.mcp.call(name, args))
                if business_code(payload) != CODE_RATE_LIMIT:
                    break
                delay *= 2
        code = business_code(payload)
        if code != CODE_OK:
            raise RuntimeError(f"{name} 业务码 {code}: {json.dumps(payload, ensure_ascii=False)[:300]}")
        return payload


def active_warehouses(client: Client) -> list[dict]:
    payload = client.call(WAREHOUSE_TOOL, {})
    rows = rows_of(payload)
    out = []
    for r in rows:
        if str(r.get("status")) == "1" and r.get("warehouseName"):
            out.append({"warehouseId": str(r.get("warehouseId") or ""),
                        "warehouseName": str(r.get("warehouseName"))})
    if not out:
        raise RuntimeError("仓库列表为空或没有 status=1 的仓")
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_warehouse(client: Client, wh: dict, outdir: Path, page_size: int,
                     max_pages: int) -> dict:
    name = wh["warehouseName"]
    wid = wh["warehouseId"] or "unknown"
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    path = outdir / f"warehouse={wid}_{safe}.jsonl"
    tmp = outdir / f"warehouse={wid}_{safe}.jsonl.tmp"
    start = datetime.now()
    pages = 0
    rows = 0
    bad = 0
    page_terminated = False
    with tmp.open("w", encoding="utf-8") as f:
        for page in range(1, max_pages + 1):
            payload = client.call(STOCK_QUERY_TOOL, {
                "warehouseName": name, "pageNo": page, "pageSize": page_size,
            })
            batch = rows_of(payload)
            pages += 1
            for r in batch:
                row = {k: r.get(k) for k in FIELDS}
                if not row.get("goodsSku") or not row.get("warehouseName"):
                    bad += 1
                    continue
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows += 1
            if len(batch) < page_size:
                page_terminated = True
                break
    os.replace(tmp, path)
    end = datetime.now()
    complete = bool(page_terminated and bad == 0)
    return {
        "warehouseId": wid,
        "warehouseName": name,
        "file": str(path),
        "file_sha256": sha256(path),
        "pages": pages,
        "rows": rows,
        "bad_rows": bad,
        "complete": complete,
        "truncated": bool(not page_terminated and pages >= max_pages),
        "capture_start": start.isoformat(timespec="seconds"),
        "capture_end": end.isoformat(timespec="seconds"),
    }


def main():
    ap = argparse.ArgumentParser(description="每日通途全量库存备份（API 只读）")
    ap.add_argument("--outdir", default=r"D:/Work/库存备份")
    ap.add_argument("--warehouses", default="", help="逗号分隔；空=全部启用仓")
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=1000)
    ap.add_argument("--min-interval", type=float, default=13.0)
    ap.add_argument("--env-file", default=str(default_env_file()))
    args = ap.parse_args()

    root = Path(args.outdir)
    day = datetime.now().strftime("%Y-%m-%d")
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    day_dir = root / day
    run_dir = day_dir / f"run={run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = root / ".lock"
    if lock.exists():
        print(f"✗ 已有任务在跑：{lock}", file=sys.stderr)
        return 2
    lock.write_text(str(os.getpid()), encoding="utf-8")

    try:
        env = load_env(Path(args.env_file))
        key = env.get("TONGTOOL_ERP2_PRIMARY_KEY", "")
        secret = env.get("TONGTOOL_ERP2_PRIMARY_SECRET", "")
        if not key or not secret:
            print(f"✗ 缺少通途凭证：{args.env_file}", file=sys.stderr)
            return 2
        mcp = McpClient(key, secret, client_name="fzh-stock-daily-backup")
        client = Client(mcp, args.min_interval)

        all_whs = active_warehouses(client)
        wanted = {w.strip() for w in args.warehouses.split(",") if w.strip()}
        whs = [w for w in all_whs if not wanted or w["warehouseName"] in wanted]
        requested_names = sorted(wanted or {w["warehouseName"] for w in all_whs})
        found_names = {w["warehouseName"] for w in whs}
        missing_requested = sorted(set(requested_names) - found_names)
        if not whs:
            raise RuntimeError(f"请求仓均未命中: {requested_names}")

        print(f"备份日 {day} run={run_id}；启用/请求仓 {len(whs)}/{len(requested_names)}；输出 {run_dir}")
        results = []
        for wh in whs:
            print(f"\n仓库 {wh['warehouseName']} ({wh['warehouseId']})")
            try:
                r = backup_warehouse(client, wh, run_dir, args.page_size, args.max_pages)
                results.append(r)
                print(f"  pages={r['pages']} rows={r['rows']} complete={r['complete']}")
            except Exception as e:  # noqa: BLE001 - 单仓失败不阻断其他仓
                msg = f"{wh['warehouseName']}: {type(e).__name__}: {e}"
                print(f"  ✗ {msg}", file=sys.stderr)
                results.append({"warehouseId": wh["warehouseId"],
                                "warehouseName": wh["warehouseName"],
                                "error": msg, "complete": False})
        for name in missing_requested:
            results.append({"warehouseName": name, "error": "not_in_active_warehouse_list",
                            "complete": False})

        manifest = {
            "run_id": run_id,
            "script_version": "stock_daily_backup/1.1",
            "snapshot_date": day,
            "snapshot_at": datetime.now().isoformat(timespec="seconds"),
            "source": "tongtool erp2_stocks_stocksquery",
            "requests": client.requests,
            "requested_warehouses": requested_names,
            "read_warehouses": sorted(found_names),
            "missing_warehouses": missing_requested,
            "warehouses": results,
            "complete": bool(
                requested_names
                and not missing_requested
                and all(r.get("complete") is True and not r.get("error") for r in results)
            ),
        }
        tmp_manifest = run_dir / "manifest.json.tmp"
        tmp_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp_manifest, run_dir / "manifest.json")
        # day/manifest.json 是“选定 run”的指针；最后原子发布，避免混读半成品。
        day_tmp = day_dir / "manifest.json.tmp"
        day_tmp.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(day_tmp, day_dir / "manifest.json")
        print(f"\nOK: {day_dir / 'manifest.json'} (run={run_id}) complete={manifest['complete']}")
        return 0 if manifest["complete"] else 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
