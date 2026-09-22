# -*- coding: utf-8 -*-
"""导出「引用某条工艺路线的所有 BOM」及其工序子表，作为改动前的备份。

只读。用于：
  1. 生产改动前留底（可据此回滚 BOM 的工序子表与成本字段）
  2. 事先看清这批 BOM 的工序结构（各有多少道工序、工序名分布、当前工费）

使用:
  python backup_bom_ops_for_routing.py --env test
  python backup_bom_ops_for_routing.py --env prod
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
_ENV_URLS = {"prod": "https://erpnext.vilavi.cn", "test": "https://ensh.vilavi.cn"}
_ENV_KEYS = {
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
}

BOM_FIELDS = [
    "name", "docstatus", "item", "routing", "with_operations", "conversion_rate",
    "quantity", "operating_cost", "base_operating_cost", "total_cost", "base_total_cost",
    "raw_material_cost", "base_raw_material_cost", "scrap_material_cost",
    "base_scrap_material_cost", "exploded_operating_cost_qty", "is_active", "is_default",
]


def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def _request(self, method: str, path: str, *, retries: int = 2,
                 retry_delay: float = 3.0, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 180))
        url = f"{self.base_url}{path}"
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as exc:
                last = exc
                if attempt < retries:
                    time.sleep(retry_delay)
        assert last is not None
        raise last

    def get_list(self, doctype: str, filters: list | None = None,
                 fields: list[str] | None = None, limit_start: int = 0,
                 limit_page_length: int = 0) -> list[dict]:
        params: dict[str, str] = {"limit_page_length": str(limit_page_length),
                                  "limit_start": str(limit_start)}
        if filters is not None:
            params["filters"] = json.dumps(filters)
        if fields is not None:
            params["fields"] = json.dumps(fields)
        path = f"/api/resource/{quote(doctype, safe='')}"
        return self._request("GET", path, params=params).json()["data"]

    def get_doc(self, doctype: str, name: str) -> dict:
        path = f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}"
        return self._request("GET", path).json()["data"]


def main() -> int:
    ap = argparse.ArgumentParser(description="备份引用某工艺路线的 BOM 及其工序子表（只读）")
    ap.add_argument("--env", choices=["test", "prod"], default="test")
    ap.add_argument("--routing", default="包装工艺路线")
    ap.add_argument("--out-dir", type=Path, default=_DIR / "out")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    _load_dotenv([_DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env"])
    key_name, secret_name = _ENV_KEYS[args.env]
    key, secret = os.getenv(key_name, ""), os.getenv(secret_name, "")
    if not key or not secret:
        print(f"错误: 缺少 {key_name} / {secret_name}")
        return 1

    base = os.getenv("PROD_ERP_URL" if args.env == "prod" else "TEST_ERP_URL",
                     _ENV_URLS[args.env])
    client = ErpnextClient(base, key, secret)

    print(f"环境: {args.env} ({base})")
    print(f"工艺路线: {args.routing}")

    boms = client.get_list(
        "BOM",
        filters=[["routing", "=", args.routing], ["docstatus", "<", 2]],
        fields=BOM_FIELDS,
    )
    print(f"命中的 BOM: {len(boms)}")
    names = [b["name"] for b in boms]

    # 子表无法直接 list（子 doctype 无 list 权限），改为逐份取 BOM 单据（返回里自带 operations）
    operations: list[dict] = []
    docs: list[dict] = []
    workers = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(client.get_doc, "BOM", n): n for n in names}
        for i, fut in enumerate(as_completed(futures), start=1):
            nm = futures[fut]
            try:
                doc = fut.result()
            except Exception as exc:
                print(f"  [WARN] 取 BOM {nm} 失败: {exc}")
                continue
            docs.append(doc)
            for op in doc.get("operations") or []:
                op = dict(op)
                op["parent"] = doc["name"]
                operations.append(op)
            if i % 100 == 0 or i == len(names):
                print(f"  已取 {i}/{len(names)} 份，工序行累计 {len(operations)}")

    # 概要
    per_bom = Counter(op["parent"] for op in operations)
    print("\n── 概要 ──")
    print("  docstatus:", dict(Counter(b["docstatus"] for b in boms)))
    print("  with_operations:", dict(Counter(b.get("with_operations") for b in boms)))
    print("  每个 BOM 的工序数分布:", dict(sorted(Counter(per_bom.get(n, 0) for n in names).items())))
    print("  工序名分布:", dict(Counter(op.get("operation") for op in operations)))
    print("  当前 operating_cost 分布(BOM Operation):",
          dict(sorted(Counter(round(float(o.get("operating_cost") or 0), 3) for o in operations).items())))
    print("  当前 hour_rate 分布:", dict(Counter(float(o.get("hour_rate") or 0) for o in operations)))
    print("  当前 time_in_mins 分布:", dict(Counter(float(o.get("time_in_mins") or 0) for o in operations)))
    if boms:
        print("  BOM.operating_cost 分布:",
              dict(sorted(Counter(round(float(b.get("operating_cost") or 0), 3) for b in boms).items())[:20]))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.out_dir / f"bom_ops_backup_{args.env}_{ts}.json"
    payload = {
        "meta": {
            "backup_time": datetime.now().isoformat(),
            "environment": args.env,
            "base_url": base,
            "routing": args.routing,
            "bom_count": len(docs),
            "operation_count": len(operations),
            "note": "boms 元素是完整 BOM 单据（含 operations），可直接用于回滚",
        },
        "boms": docs,
        "operations": operations,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已写出: {out}  ({out.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
