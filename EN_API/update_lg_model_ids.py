# -*- coding: utf-8 -*-
"""更新 LG 前缀物料组款式ID: LGxxx → LG{子孙最小款式ID}。

流程:
  1. 全量拉取测试系统物料组
  2. 找出 custom_model_id 以 LG 开头的物料组
  3. 逐个查询其子孙后代中最小 custom_model_id
  4. 构建新 ID = "LG" + 最小子孙ID (如 LGKS0496)
  5. 冲突检测（新 ID 不能与已有 ID 重复）
  6. 执行 PUT 更新 (支持 --dry-run)
  7. 生成变更报告 Excel
  8. 更新交接文档

使用:
  python update_lg_model_ids.py              # 执行更新（测试系统）
  python update_lg_model_ids.py --dry-run    # 预览（不实际写入）
  python update_lg_model_ids.py --env prod   # 生产系统（慎用）
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)

_ENV_URLS = {"test": "https://ensh.vilavi.cn", "prod": "https://erpnext.vilavi.cn"}
_ENV_KEY_MAP = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}


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
])


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str,
                 label: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label or base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def fetch_all(self, fields: list[str] | None = None) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/Item Group"
        params: dict = {"limit_page_length": "0"}
        if fields is not None:
            params["fields"] = json.dumps(fields)
        else:
            params["limit"] = "0"
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def update_item_group(self, name: str, fields: dict[str, Any]) -> dict[str, Any]:
        safe = quote(name, safe="")
        url = f"{self.base_url}/api/resource/Item Group/{safe}"
        resp = self._request("PUT", url, json=fields)
        return resp.json().get("data", {})

    def _request(self, method: str, url: str, *,
                 retries: int = 2, retry_delay: float = 3.0,
                 **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (60, 120))
        last = None
        for a in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last = e
                if a < retries:
                    time.sleep(retry_delay)
        raise last


def to_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and (math.isnan(val) or val != val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null", "") else s


def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def get_descendants(parent_name: str, idx: dict[str, dict],
                    data: list[dict]) -> list[dict]:
    result = []
    stack = [parent_name]
    while stack:
        name = stack.pop()
        node = idx.get(name)
        if node:
            result.append(node)
            for d in data:
                if d.get("parent_item_group") == name and d["name"] != name:
                    stack.append(d["name"])
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="更新 LG 前缀物料组款式ID: LGxxx → LG{子孙最小款式ID}"
    )
    ap.add_argument("--env", default="test", choices=list(_ENV_URLS.keys()),
                    help="目标环境 (默认 test)")
    ap.add_argument("--dry-run", action="store_true",
                    help="预览模式，不实际写入")
    args = ap.parse_args()

    env = args.env
    env_url = _ENV_URLS[env]
    key_name, secret_name = _ENV_KEY_MAP[env]
    api_key = os.getenv(key_name, "")
    api_secret = os.getenv(secret_name, "")
    if not api_key or not api_secret:
        print(f"错误: 请设置 {key_name} / {secret_name}")
        return 1

    env_label = f"{env}[{env_url}]"
    client = ErpnextClient(env_url, api_key, api_secret, label=env_label)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "DRY-RUN（预览）" if args.dry_run else "实际执行"

    print(f"╔{'='*60}╗")
    print(f"║  LG 款式ID 更新")
    print(f"║  环境: {env_label}")
    print(f"║  模式: {mode}")
    print(f"╚{'='*60}╝")

    # Step 1: 获取全量数据
    print(f"\n── Step 1: 获取全量物料组 ──")
    fields = ["name", "item_group_name", "parent_item_group",
              "is_group", "custom_model_id", "image"]
    data = client.fetch_all(fields)
    idx = build_index(data)
    print(f"  物料组总数: {len(data)}")

    # Step 2: 找出 LG 节点
    lg_nodes = [
        d for d in data
        if to_str(d.get("custom_model_id")).startswith("LG")
    ]
    lg_nodes.sort(key=lambda x: to_str(x.get("custom_model_id", "")))
    print(f"  LG 前缀节点: {len(lg_nodes)}")

    if not lg_nodes:
        print("  [INFO] 无 LG 前缀节点，无需更新")
        return 0

    # Step 3: 计算映射
    print(f"\n── Step 2: 计算新款式ID ──")
    mappings = []
    existing_ids = {to_str(d.get("custom_model_id")) for d in data if to_str(d.get("custom_model_id"))}

    for node in lg_nodes:
        old_id = to_str(node.get("custom_model_id"))
        descendants = get_descendants(node["name"], idx, data)
        children = [d for d in descendants if d["name"] != node["name"]]
        with_model = [d for d in children if to_str(d.get("custom_model_id"))]

        min_id = None
        min_node = None
        for d in with_model:
            mid = to_str(d.get("custom_model_id"))
            if mid and (min_id is None or mid < min_id):
                min_id = mid
                min_node = d

        if not min_id:
            print(f"  ⚠️  {old_id} ({node['item_group_name']}): 无含款式ID的子孙，跳过")
            continue

        new_id = f"LG{min_id}"
        has_conflict = new_id in existing_ids and new_id != old_id

        mappings.append({
            "name": node["name"],
            "item_group_name": node["item_group_name"],
            "old_custom_model_id": old_id,
            "min_child_id": min_id,
            "min_child_name": min_node["item_group_name"],
            "new_custom_model_id": new_id,
            "descendant_count": len(children),
            "has_conflict": has_conflict,
        })
        status = "[CONFLICT]" if has_conflict else "[OK]"
        msg = f"  {status} {old_id:8s} -> {new_id:14s}  (子孙最小: {min_id:8s} 来自: {min_node['item_group_name']})"
        print(msg)

    # Step 4: 冲突分析
    print(f"\n── Step 3: 冲突分析 ──")
    conflict_nodes = [m for m in mappings if m["has_conflict"]]
    safe_nodes = [m for m in mappings if not m["has_conflict"]]
    print(f"  无冲突: {len(safe_nodes)} 条")
    print(f"  有冲突: {len(conflict_nodes)} 条")

    if conflict_nodes:
        print(f"\n  ⚠️  冲突明细:")
        for m in conflict_nodes:
            conflict_with = [
                d for d in data
                if to_str(d.get("custom_model_id")) == m["new_custom_model_id"]
                and d["name"] != m["name"]
            ]
            for c in conflict_with:
                print(f"    {m['old_custom_model_id']} → {m['new_custom_model_id']} 与 [{c['name']}] 冲突")
        if not args.dry_run:
            print("\n  [ABORT] 存在冲突，需要先解决再执行。请使用 --dry-run 预览。")
            return 1

    # Step 5: 执行更新
    print(f"\n── Step 4: {'执行更新' if not args.dry_run else '预览更新'} ──")
    results = []
    for m in safe_nodes:
        print(f"  {'[DRY]' if args.dry_run else '[PUT]'} {m['name']}: "
              f"{m['old_custom_model_id']} → {m['new_custom_model_id']}", end="")

        if args.dry_run:
            results.append({**m, "status": "预览（未写入）", "response": ""})
            print()
            continue

        try:
            resp = client.update_item_group(m["name"], {
                "custom_model_id": m["new_custom_model_id"],
            })
            results.append({**m, "status": "成功", "response": "OK"})
            print(" [OK]")
            time.sleep(0.3)
        except Exception as e:
            results.append({**m, "status": "失败", "response": str(e)})
            print(f" [FAIL] {e}")

    # Step 6: 生成报告
    print(f"\n── Step 5: 生成报告 ──")

    # 汇总统计
    success = sum(1 for r in results if r["status"] == "成功")
    failed = sum(1 for r in results if r["status"] == "失败")
    skipped = len(mappings) - len(results)

    summary = [
        {"指标": "环境", "值": env_label},
        {"指标": "执行模式", "值": mode},
        {"指标": "执行时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"指标": "LG 物料组总数", "值": len(lg_nodes)},
        {"指标": "需更新数（无冲突）", "值": len(safe_nodes)},
        {"指标": "更新成功", "值": success},
        {"指标": "更新失败", "值": failed},
        {"指标": "因冲突跳过", "值": len(conflict_nodes)},
        {"指标": "冲突数", "值": len(conflict_nodes)},
    ]

    # 变更明细
    detail_rows = []
    for r in results:
        detail_rows.append({
            "物料组名称": r["item_group_name"],
            "原款式ID": r["old_custom_model_id"],
            "新款式ID": r["new_custom_model_id"],
            "子孙最小款式ID": r["min_child_id"],
            "最小款式来源": r["min_child_name"],
            "子孙节点数": r["descendant_count"],
            "状态": r["status"],
        })
    # 冲突记录（如果有）
    for m in conflict_nodes:
        detail_rows.append({
            "物料组名称": m["item_group_name"],
            "原款式ID": m["old_custom_model_id"],
            "新款式ID": m["new_custom_model_id"],
            "子孙最小款式ID": m["min_child_id"],
            "最小款式来源": m["min_child_name"],
            "子孙节点数": m["descendant_count"],
            "状态": "跳过（冲突）",
        })

    # 写入 Excel
    report_path = _DIR_OUT / f"LG款式ID更新结果_{env}_{ts}.xlsx"
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        if detail_rows:
            pd.DataFrame(detail_rows).to_excel(writer, sheet_name="变更明细", index=False)

    # 写入 JSON（备份）
    json_path = _DIR_OUT / f"LG款式ID更新结果_{env}_{ts}.json"
    backup = {
        "metadata": {
            "execution_time": datetime.now().isoformat(),
            "environment": env_label,
            "mode": mode,
            "total_lg_nodes": len(lg_nodes),
            "updated": success,
            "failed": failed,
            "conflict_skipped": len(conflict_nodes),
        },
        "mappings": mappings,
        "results": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)

    print(f"  报告: {report_path.name}")
    print(f"  JSON: {json_path.name}")

    # 最终汇总
    print(f"\n{'='*60}")
    print(f"  环境:    {env_label}")
    print(f"  模式:    {mode}")
    print(f"  总LG数:  {len(lg_nodes)}")
    print(f"  成功:    {success}")
    print(f"  失败:    {failed}")
    print(f"  冲突:    {len(conflict_nodes)}")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
