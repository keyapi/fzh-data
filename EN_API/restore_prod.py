# -*- coding: utf-8 -*-
"""从备份 JSON 恢复生产系统物料组状态（回滚重构操作）。

使用:
  python restore_prod.py --dry-run              # 预览将恢复的内容
  python restore_prod.py                         # 执行恢复
  python restore_prod.py --backup out/生产系统备份_全量_20260610_163718.json  # 指定备份文件
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter


_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)
_DIR_OUT = _DIR / "out"


# ── .env 加载 ──
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


_load_dotenv([
    _DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env",
    _DIR.parent / "tongtool_bundle_to_en" / ".env",
])


# ── HTTP ──
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.headers.pop("Expect", None)
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def get_item_group(self, name: str) -> dict | None:
        safe = quote(name, safe="")
        r = self.session.get(
            f"{self.base_url}/api/resource/Item Group/{safe}",
            timeout=60,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("data")

    def update_item_group(self, name: str, fields: dict[str, Any]) -> bool:
        safe = quote(name, safe="")
        r = self.session.put(
            f"{self.base_url}/api/resource/Item Group/{safe}",
            json=fields,
            timeout=60,
        )
        if r.ok:
            return True
        # 如果失败是因为"不能是一个叶节点"，补 is_group=1
        body = r.text
        if "不能是一个叶节点" in body or "can not be a leaf node" in body.lower():
            fields["is_group"] = 1
            r2 = self.session.put(
                f"{self.base_url}/api/resource/Item Group/{safe}",
                json=fields,
                timeout=60,
            )
            return r2.ok
        return False

    def delete_item_group(self, name: str) -> bool:
        safe = quote(name, safe="")
        r = self.session.delete(
            f"{self.base_url}/api/resource/Item Group/{safe}",
            timeout=60,
        )
        return r.status_code in (200, 202, 204)


def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="从备份恢复生产系统物料组")
    ap.add_argument("--dry-run", action="store_true", help="预览不执行")
    ap.add_argument("--backup", type=Path,
                    default=_DIR_OUT / "生产系统备份_全量_20260610_163718.json",
                    help="备份 JSON 文件路径")
    ap.add_argument("--batch", type=float, default=0.3, help="请求间隔")
    args = ap.parse_args()

    # 加载备份
    backup_path = args.backup
    if not backup_path.is_file():
        print(f"错误: 备份文件不存在 {backup_path}")
        return 1
    with open(backup_path, "r", encoding="utf-8") as f:
        backup = json.load(f)
    backup_records = backup["records"]
    backup_idx = build_index(backup_records)
    print(f"备份文件: {backup_path.name}")
    print(f"备份时间: {backup['metadata']['backup_time']}")
    print(f"备份节点数: {len(backup_records)}")

    # 连接生产系统
    prod_key = os.getenv("PROD_ERP_API_KEY", "")
    prod_secret = os.getenv("PROD_ERP_API_SECRET", "")
    if not prod_key or not prod_secret:
        print("错误: 请设置 PROD_ERP_API_KEY / PROD_ERP_API_SECRET")
        return 1

    client = ErpnextClient("https://erpnext.vilavi.cn", prod_key, prod_secret)
    print(f"\n生产环境: https://erpnext.vilavi.cn")
    print(f"模式: {'DRY-RUN' if args.dry_run else '执行'}")

    # 获取当前系统数据
    print("\n获取当前生产系统数据...")
    r = client.session.get(
        "https://erpnext.vilavi.cn/api/resource/Item Group",
        params={
            "fields": json.dumps(["name", "item_group_name", "parent_item_group", "is_group"]),
            "limit_page_length": "0",
        },
        timeout=120,
    )
    current_data = r.json().get("data", [])
    current_idx = build_index(current_data)
    print(f"当前节点数: {len(current_data)}")

    # ── 分析需要恢复的内容 ──
    # 1. 需要恢复 parent_item_group 的产品（被移动过的）
    restore_moves: list[dict] = []
    for name, backup_node in backup_idx.items():
        current_node = current_idx.get(name)
        if current_node is None:
            # 备份中存在但当前不存在 — 已删除，需忽略
            continue
        backup_parent = backup_node.get("parent_item_group") or ""
        current_parent = current_node.get("parent_item_group") or ""
        if backup_parent != current_parent:
            restore_moves.append({
                "name": name,
                "item_group_name": backup_node.get("item_group_name", name),
                "from": current_parent,
                "to": backup_parent,
            })

    # 2. 需要删除的新建节点 — 直接按 item_group_name 检查 5 个目标节点
    #    避免 name 字段编码不一致导致的漏判
    target_names = {"家具类", "宠物类", "枕头类", "抱枕靠枕", "沙发"}
    # 备份中已有的目标节点（宠物类已在备份中）不应删除
    backup_item_names = {r.get("item_group_name") for r in backup_records}
    new_nodes: list[dict] = []
    for name, current_node in current_idx.items():
        gn = current_node.get("item_group_name", "")
        if gn in target_names and gn not in backup_item_names:
            new_nodes.append({
                "name": name,
                "item_group_name": gn,
                "parent": current_node.get("parent_item_group", ""),
            })

    # ── 输出恢复计划 ──
    print(f"\n{'='*60}")
    print(f"恢复计划")
    print(f"{'='*60}")
    print(f"\n需恢复 parent 的产品: {len(restore_moves)} 个")
    for m in restore_moves[:10]:
        print(f"  {m['item_group_name']}: {m['from']} -> {m['to']}")
    if len(restore_moves) > 10:
        print(f"  ... 共 {len(restore_moves)} 个")

    print(f"\n需删除的新建节点: {len(new_nodes)} 个")
    for d in new_nodes:
        print(f"  DELETE {d['item_group_name']} (parent={d['parent']})")

    # ── 执行 ──
    if args.dry_run:
        print(f"\n[DRY-RUN] 预览完成，共 {len(restore_moves)} 个恢复 + {len(new_nodes)} 个删除")
        return 0

    print(f"\n{'='*60}")
    print(f"开始执行恢复")
    print(f"{'='*60}")

    # 阶段1: 恢复 parent
    ok_count = 0
    fail_count = 0
    print(f"\n── 阶段1: 恢复 parent ({len(restore_moves)} 个) ──")
    for i, m in enumerate(restore_moves):
        ok = client.update_item_group(m["name"], {"parent_item_group": m["to"]})
        if ok:
            ok_count += 1
            if len(restore_moves) <= 20 or i < 3 or i >= len(restore_moves) - 3:
                print(f"  [OK] {m['item_group_name']}: {m['from']} -> {m['to']}")
        else:
            fail_count += 1
            print(f"  [FAIL] {m['item_group_name']}: {m['from']} -> {m['to']}")
        time.sleep(args.batch)

    print(f"  恢复结果: 成功={ok_count}, 失败={fail_count}")

    # 阶段2: 删除新建节点
    del_ok = 0
    del_fail = 0
    print(f"\n── 阶段2: 删除新建节点 ({len(new_nodes)} 个) ──")
    for d in new_nodes:
        ok = client.delete_item_group(d["name"])
        if ok:
            del_ok += 1
            print(f"  [OK] DELETE {d['item_group_name']}")
        else:
            del_fail += 1
            print(f"  [FAIL] DELETE {d['item_group_name']}")
        time.sleep(args.batch)

    print(f"  删除结果: 成功={del_ok}, 失败={del_fail}")

    # ── 验证 ──
    print(f"\n── 验证 ──")
    r2 = client.session.get(
        "https://erpnext.vilavi.cn/api/resource/Item Group",
        params={
            "fields": json.dumps(["name", "item_group_name", "parent_item_group"]),
            "limit_page_length": "0",
        },
        timeout=120,
    )
    final_data = r2.json().get("data", [])
    final_idx = build_index(final_data)

    still_wrong = 0
    for name, backup_node in backup_idx.items():
        cur = final_idx.get(name)
        if cur is None:
            still_wrong += 1
            continue
        if (cur.get("parent_item_group") or "") != (backup_node.get("parent_item_group") or ""):
            still_wrong += 1

    created_still_exist = sum(1 for d in new_nodes if d["name"] in final_idx)

    print(f"  最终节点数: {len(final_data)} (期望 ~{len(backup_records)})")
    print(f"  仍不匹配: {still_wrong}")
    print(f"  新节点残留: {created_still_exist}")

    if still_wrong == 0 and created_still_exist == 0:
        print(f"\n[OK] 恢复完成！数据已还原至备份状态。")
    else:
        print(f"\n[WARN] 恢复部分完成，仍有差异。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
