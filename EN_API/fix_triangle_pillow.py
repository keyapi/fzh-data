# -*- coding: utf-8 -*-
"""修复三角靠枕叶子节点被误转为组节点的问题。

操作:
  1. 创建 三角靠枕类（测试系统）
  2. 将 三角靠枕 的子物料组移至 三角靠枕类
  3. 将直接属于 三角靠枕 的产品移至 三角靠枕类
  4. 将 三角靠枕 设回叶子节点(is_group=0)

使用:
  python fix_triangle_pillow.py --env test --dry-run   # 预览
  python fix_triangle_pillow.py --env test              # 执行(测试)
  python fix_triangle_pillow.py --env prod              # 执行(生产)
"""

from __future__ import annotations
import os, time, json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)

def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file(): continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"): v = v[1:-1]
            os.environ.setdefault(k, v)

_load_dotenv([
    _DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env",
    _DIR.parent / "tongtool_bundle_to_en" / ".env",
])

_ENV_MAP = {
    "test": {"url": "https://ensh.vilavi.cn", "key": "TEST_ERP_API_KEY", "sec": "TEST_ERP_API_SECRET"},
    "prod": {"url": "https://erpnext.vilavi.cn", "key": "PROD_ERP_API_KEY", "sec": "PROD_ERP_API_SECRET"},
}

class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="修复三角靠枕叶子节点")
    ap.add_argument("--env", choices=["test", "prod"], default="test")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = _ENV_MAP[args.env]
    url = env["url"]
    key = os.getenv(env["key"], "")
    secret = os.getenv(env["sec"], "")
    if not key or not secret:
        print(f"错误: 未设置 {env['key']}/{env['sec']}")
        return 1

    s = requests.Session()
    s.headers["Authorization"] = f"token {key}:{secret}"
    s.mount("https://", _NoExpectAdapter())
    s.headers.pop("Expect", None)

    print(f"环境: {args.env} ({url})")
    print(f"模式: {'DRY-RUN' if args.dry_run else '执行'}\n")

    # Step 1: Check current state
    def get(doc, name):
        r = s.get(f"{url}/api/resource/{doc}/{quote(name, safe='')}", timeout=30)
        return r.json().get("data") if r.ok else None

    def update(doc, name, fields):
        r = s.put(f"{url}/api/resource/{doc}/{quote(name, safe='')}", json=fields, timeout=30)
        return r.ok

    def create(doc, data):
        r = s.post(f"{url}/api/resource/{doc}", json=data, timeout=30)
        return r.ok, r.json().get("data") if r.ok else None

    tri = get("Item Group", "三角靠枕")
    tri_class = get("Item Group", "三角靠枕类")
    print(f"三角靠枕: {'已存在' if tri else '不存在'} is_group={tri.get('is_group') if tri else 'N/A'}")
    print(f"三角靠枕类: {'已存在' if tri_class else '不存在'}")

    # Get children of 三角靠枕
    r = s.get(f"{url}/api/resource/Item Group", params={
        "fields": json.dumps(["name", "item_group_name", "parent_item_group", "is_group"]),
        "filters": json.dumps([["parent_item_group", "=", "三角靠枕"]]),
        "limit_page_length": "50"
    }, timeout=30)
    children = r.json().get("data", [])
    print(f"三角靠枕的子物料组: {len(children)} 个")
    for c in children:
        print(f"  {c['item_group_name']} (is_group={c.get('is_group')})")

    # Get items directly assigned to 三角靠枕
    r2 = s.get(f"{url}/api/resource/Item", params={
        "fields": json.dumps(["name", "item_name", "item_group"]),
        "filters": json.dumps([["item_group", "=", "三角靠枕"]]),
        "limit_page_length": "100"
    }, timeout=30)
    items = r2.json().get("data", [])
    print(f"直接属于三角靠枕的产品: {len(items)} 个")

    # Step 2: Create 三角靠枕类 if not exists
    print(f"\n-- 操作1: {'创建' if not tri_class else '已存在'} 三角靠枕类 --")
    if not tri_class and not args.dry_run:
        ok, data = create("Item Group", {
            "item_group_name": "三角靠枕类",
            "parent_item_group": "床头靠枕",
            "is_group": 1,
        })
        print(f"  创建三角靠枕类: {'OK' if ok else 'FAIL'}")
        if ok:
            tri_class = data
    elif args.dry_run:
        print(f"  [DRY] 创建 三角靠枕类 (parent=床头靠枕)")

    # Step 3: Move child Item Groups from 三角靠枕 to 三角靠枕类
    print(f"\n-- 操作2: 移动子节点 ({len(children)} 个) --")
    ok_count = 0
    for c in children:
        if not args.dry_run:
            ok = update("Item Group", c["name"], {"parent_item_group": "三角靠枕类"})
            print(f"  {'OK' if ok else 'FAIL'} {c['item_group_name']}: 三角靠枕 -> 三角靠枕类")
            if ok: ok_count += 1
            time.sleep(0.3)
        else:
            print(f"  [DRY] MOVE {c['item_group_name']}: 三角靠枕 -> 三角靠枕类")

    # Step 4: Move Items from 三角靠枕 to 三角靠枕类
    print(f"\n-- 操作3: 移动产品 ({len(items)} 个) --")
    item_ok = 0
    for it in items:
        if not args.dry_run:
            ok = update("Item", it["name"], {"item_group": "三角靠枕类"})
            print(f"  {'OK' if ok else 'FAIL'} {it.get('item_name','')}")
            if ok: item_ok += 1
            time.sleep(0.2)
        else:
            print(f"  [DRY] MOVE {it.get('item_name','')}: item_group 三角靠枕 -> 三角靠枕类")

    # Step 5: Set 三角靠枕 to leaf
    print(f"\n-- 操作4: 设置三角靠枕为叶子节点(is_group=0) --")
    if not args.dry_run:
        ok = update("Item Group", "三角靠枕", {"is_group": 0})
        print(f"  {'OK' if ok else 'FAIL'} 三角靠枕 is_group=0")
    else:
        print(f"  [DRY] UPDATE 三角靠枕 is_group=0")

    print(f"\n{'='*50}")
    if not args.dry_run:
        print(f"完成！子节点移动: {ok_count}/{len(children)}, 产品移动: {item_ok}/{len(items)}")
    else:
        print(f"DRY-RUN 完成，以上为预览操作")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
