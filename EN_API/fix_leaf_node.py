# -*- coding: utf-8 -*-
"""通用叶子节点修复工具。

当赛狐分类中的叶子节点在 EN 系统中被脚本误转为组节点(is_group=1)时，
此脚本可：创建 XXX类 父节点，将子节点和产品移过去，将原节点恢复为叶子。

使用:
  python fix_leaf_node.py --name 平条靠枕 --env test --dry-run   # 预览
  python fix_leaf_node.py --name 平条靠枕 --env test              # 执行(测试)
  python fix_leaf_node.py --name 平条靠枕 --env prod              # 执行(生产)
"""

from __future__ import annotations
import os, time, json
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
    ap = argparse.ArgumentParser(description="通用叶子节点修复工具")
    ap.add_argument("--name", required=True, help="叶子节点名称（如 三角靠枕、平条靠枕）")
    ap.add_argument("--env", choices=["test", "prod"], default="test")
    ap.add_argument("--parent", default=None, help="XXX类 的父节点（默认自动从 Commodities 推断）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    leaf_name = args.name.strip()
    class_name = f"{leaf_name}类"

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
    print(f"叶子: {leaf_name}  →  {class_name}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '执行'}\n")

    def get(doc, name):
        r = s.get(f"{url}/api/resource/{doc}/{quote(name, safe='')}", timeout=30)
        return r.json().get("data") if r.ok else None

    def put(doc, name, fields):
        r = s.put(f"{url}/api/resource/{doc}/{quote(name, safe='')}", json=fields, timeout=30)
        return r.ok

    def post(doc, data):
        r = s.post(f"{url}/api/resource/{doc}", json=data, timeout=30)
        return r.ok

    # 获取当前状态
    leaf = get("Item Group", leaf_name)
    class_node = get("Item Group", class_name)
    print(f"{leaf_name}: {'已存在' if leaf else '不存在'} is_group={leaf.get('is_group') if leaf else 'N/A'}")
    print(f"{class_name}: {'已存在' if class_node else '不存在'}")

    if not leaf:
        print(f"错误: {leaf_name} 不存在，无需修复")
        return 1

    # 获取子物料组
    r = s.get(f"{url}/api/resource/Item Group", params={
        "fields": json.dumps(["name", "item_group_name", "parent_item_group", "is_group"]),
        "filters": json.dumps([["parent_item_group", "=", leaf_name]]),
        "limit_page_length": "50"
    }, timeout=30)
    children = r.json().get("data", [])
    print(f"子物料组: {len(children)} 个")
    for c in children:
        print(f"  {c['item_group_name']} (is_group={c.get('is_group')})")

    # 获取直接产品
    r2 = s.get(f"{url}/api/resource/Item", params={
        "fields": json.dumps(["name", "item_name", "item_group"]),
        "filters": json.dumps([["item_group", "=", leaf_name]]),
        "limit_page_length": "200"
    }, timeout=30)
    items = r2.json().get("data", [])
    print(f"直接产品: {len(items)} 个")

    # 确定 class_node 的父节点 — 使用叶子当前的父节点
    leaf_parent = leaf.get("parent_item_group", "产品")
    class_parent = args.parent or leaf_parent
    print(f"\n{class_name} 父节点: {class_parent}")

    # Step 1: 创建 XXX类
    print(f"\n-- 操作1: {'创建' if not class_node else '已存在'} {class_name} --")
    if not class_node and not args.dry_run:
        ok = post("Item Group", {
            "item_group_name": class_name,
            "parent_item_group": class_parent,
            "is_group": 1,
        })
        print(f"  创建 {class_name}: {'OK' if ok else 'FAIL'}")
    elif args.dry_run:
        print(f"  [DRY] 创建 {class_name} (parent={class_parent})")

    # Step 2: 移动子物料组
    print(f"\n-- 操作2: 移动子节点 ({len(children)} 个) --")
    ok_cnt = 0
    for c in children:
        if not args.dry_run:
            ok = put("Item Group", c["name"], {"parent_item_group": class_name})
            print(f"  {'OK' if ok else 'FAIL'} {c['item_group_name']}: {leaf_name} -> {class_name}")
            if ok: ok_cnt += 1
            time.sleep(0.3)
        else:
            print(f"  [DRY] MOVE {c['item_group_name']}: {leaf_name} -> {class_name}")

    # Step 3: 移动产品
    print(f"\n-- 操作3: 移动产品 ({len(items)} 个) --")
    item_ok = 0
    for it in items:
        if not args.dry_run:
            ok = put("Item", it["name"], {"item_group": class_name})
            if ok: item_ok += 1
            time.sleep(0.2)
        else:
            print(f"  [DRY] MOVE {it.get('item_name','')}: item_group {leaf_name} -> {class_name}")
    if not args.dry_run:
        print(f"  产品移动: {item_ok}/{len(items)}")

    # Step 4: 将叶子放在 XXX类 下，设为 is_group=0
    print(f"\n-- 操作4: 设置 {leaf_name} parent={class_name}, is_group=0 --")
    if not args.dry_run:
        ok1 = put("Item Group", leaf_name, {"parent_item_group": class_name, "is_group": 0})
        print(f"  {'OK' if ok1 else 'FAIL'} {leaf_name} -> {class_name}, is_group=0")
    else:
        print(f"  [DRY] UPDATE {leaf_name}: parent={class_name}, is_group=0")

    print(f"\n{'='*50}")
    if not args.dry_run:
        print(f"完成！子节点: {ok_cnt}/{len(children)}, 产品: {item_ok}/{len(items)}")
    else:
        print(f"DRY-RUN 完成")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
