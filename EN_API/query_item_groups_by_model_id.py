# -*- coding: utf-8 -*-
"""查询 EN ERPNext 物料组 (Item Group)，按 custom_model_id 前缀过滤。

用途:
  在测试/生产系统中查询指定前缀的款式ID物料组，例如查询 custom_model_id 以 "LG" 开头的记录。
  输出 Excel 报告 + 可选 JSON 备份。

使用:
  python query_item_groups_by_model_id.py                          # 默认: 测试环境, LG 前缀
  python query_item_groups_by_model_id.py --env prod               # 生产环境
  python query_item_groups_by_model_id.py --prefix KS              # 查 KS 前缀
  python query_item_groups_by_model_id.py --dry-run                # 预览统计
  python query_item_groups_by_model_id.py --json                   # 同时输出 JSON 备份

输出:
  out/{前缀}物料组查询结果_{timestamp}.xlsx  (Excel 报告)
  out/{前缀}物料组查询结果_{timestamp}.json  (可选 JSON 备份)
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

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)

# ── 环境配置 ─────────────────────────────────────────
_ENV_URLS: dict[str, str] = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}

_ENV_KEY_MAP: dict[str, tuple[str, str]] = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}

_DEFAULT_PREFIX = "LG"
_DEFAULT_ENV = "test"

# ── 报告列名 ─────────────────────────────────────────
COL_NAME = "名称"
COL_ITEM_GROUP_NAME = "物料组名"
COL_PARENT = "父级"
COL_IS_GROUP = "类型"
COL_MODEL_ID = "custom_model_id"
COL_IMAGE = "有图片"
COL_PATH = "完整路径"
COL_DEPTH = "深度"
COL_ROOT = "所属根节点"


# ── .env 加载 (stdlib only) ──────────────────────────
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


# ── HTTP 适配器 ──────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    """移除 Expect 头，解决 nginx 417 问题。"""
    def send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


# ── ERPNext 客户端 ───────────────────────────────────
class ErpnextClient:
    """ERPNext REST API 客户端。"""

    def __init__(self, base_url: str, api_key: str, api_secret: str,
                 label: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label or base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def fetch_all(self, fields: list[str] | None = None) -> list[dict[str, Any]]:
        """获取全部物料组。fields=None 返回全部字段。"""
        url = f"{self.base_url}/api/resource/Item Group"
        params: dict = {"limit_page_length": "0"}
        if fields is not None:
            params["fields"] = json.dumps(fields)
        else:
            params["limit"] = "0"
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def fetch_by_filter(
        self, filters: list[list[str]], fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """按过滤条件查询物料组。

        filters 格式: [["Item Group", "custom_model_id", "like", "LG%"]]
        """
        url = f"{self.base_url}/api/resource/Item Group"
        params: dict[str, str] = {
            "filters": json.dumps(filters),
            "limit_page_length": "0",
        }
        if fields is not None:
            params["fields"] = json.dumps(fields)
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

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


# ── 树工具函数 (复用 backup_prod.py 模式) ────────────
def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def get_ancestors(node_name: str, idx: dict[str, dict]) -> list[str]:
    parts: list[str] = []
    current = node_name
    visited: set[str] = set()
    while current and current in idx and current not in visited:
        parts.insert(0, current)
        visited.add(current)
        current = idx[current].get("parent_item_group", "")
    return parts


def get_tree_depth(node_name: str, idx: dict[str, dict]) -> int:
    return len(get_ancestors(node_name, idx))


def get_root(node_name: str, idx: dict[str, dict]) -> str:
    ancestors = get_ancestors(node_name, idx)
    return ancestors[0] if ancestors else node_name


def _to_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and (math.isnan(val) or val != val):
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null", ""):
        return ""
    return s


# ── 查询与报告 ───────────────────────────────────────
def query_and_report(
    client: ErpnextClient,
    prefix: str,
    dry_run: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    查询指定前缀的物料组。

    三步策略:
      1. 先尝试服务端 LIKE 过滤
      2. 如果结果为空但不确定是否因过滤不生效，回退全量拉取 + 客户端过滤
      3. 返回 (匹配结果, 所有结果)

    返回 (matched, all_fetched)
    """
    label = client.label
    prefix_upper = prefix.upper()

    print(f"\n── 查询 {label}  custom_model_id LIKE '{prefix}%' ──")

    # === 策略1: 服务端 LIKE 过滤 ===
    fields = ["name", "item_group_name", "parent_item_group",
              "is_group", "custom_model_id", "image"]
    filters = [["Item Group", "custom_model_id", "like", f"{prefix}%"]]

    try:
        matched = client.fetch_by_filter(filters, fields)
        print(f"  服务端 LIKE 过滤: {len(matched)} 条匹配")
    except requests.RequestException as e:
        print(f"  服务端 LIKE 过滤失败: {e}")
        matched = []

    # === 策略2: 如果结果为空，用全量拉取 + 客户端过滤验证 ===
    all_fetched = []
    if len(matched) == 0:
        print(f"  服务端 LIKE 返回 0 条，尝试全量拉取 + 客户端过滤...")
        try:
            all_data = client.fetch_all(fields)
            all_fetched = all_data
            matched = [
                d for d in all_data
                if _to_str(d.get("custom_model_id")).upper().startswith(prefix_upper)
            ]
            print(f"  全量数据共 {len(all_data)} 条，客户端过滤后匹配 {len(matched)} 条")
        except requests.RequestException as e:
            print(f"  全量拉取失败: {e}")
            all_fetched = []
    else:
        all_fetched = matched  # 服务端已过滤

    # 打印匹配结果概览
    if matched:
        print(f"\n  ── 匹配清单 ({len(matched)} 条) ──")
        for d in matched:
            model_id = _to_str(d.get("custom_model_id"))
            ig_name = d.get("item_group_name", "")
            parent = d.get("parent_item_group", "")
            gtype = "组" if d.get("is_group") else "叶"
            print(f"    {model_id:20s} | {ig_name:30s} | parent={parent:20s} | {gtype}")
    else:
        print(f"\n  [INFO] 未找到 custom_model_id 以 '{prefix}' 开头的物料组。")

    return matched, all_fetched


def generate_report(
    matched: list[dict[str, Any]],
    all_data: list[dict[str, Any]],
    prefix: str,
    env_label: str,
    ts: str,
    out_dir: Path,
) -> Path:
    """生成 Excel 报告。"""
    idx = build_index(all_data)

    # 基础统计
    summary = [
        {"指标": "目标环境", "值": env_label},
        {"指标": "查询前缀", "值": prefix},
        {"指标": "匹配物料组数", "值": len(matched)},
        {"指标": "全量物料组数", "值": len(all_data)},
        {"指标": "查询时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ]

    if matched:
        groups = [d for d in matched if d.get("is_group")]
        leaves = [d for d in matched if not d.get("is_group")]
        summary.append({"指标": "匹配中组节点", "值": len(groups)})
        summary.append({"指标": "匹配中叶节点", "值": len(leaves)})

        # 按根节点分组统计
        root_count: dict[str, int] = {}
        for d in matched:
            root = get_root(d["name"], idx)
            root_count[root] = root_count.get(root, 0) + 1
        for root, cnt in sorted(root_count.items()):
            summary.append({"指标": f"  根节点「{root}」下匹配数", "值": cnt})

    # 匹配节点明细
    rows = []
    for d in matched:
        model_id = _to_str(d.get("custom_model_id"))
        path = " / ".join(get_ancestors(d["name"], idx))
        depth = get_tree_depth(d["name"], idx)
        root = get_root(d["name"], idx)
        rows.append({
            COL_NAME: d["name"],
            COL_ITEM_GROUP_NAME: d.get("item_group_name", ""),
            COL_PARENT: d.get("parent_item_group", ""),
            COL_IS_GROUP: "组" if d.get("is_group") else "叶子",
            COL_MODEL_ID: model_id,
            COL_IMAGE: "是" if d.get("image") else "否",
            COL_PATH: path,
            COL_DEPTH: depth,
            COL_ROOT: root,
        })

    report_path = out_dir / f"{prefix}物料组查询结果_{ts}.xlsx"
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        if rows:
            pd.DataFrame(rows).to_excel(writer, sheet_name="匹配清单", index=False)
        else:
            pd.DataFrame(columns=list(rows[0].keys()) if rows else [
                COL_NAME, COL_ITEM_GROUP_NAME, COL_MODEL_ID
            ]).to_excel(writer, sheet_name="匹配清单", index=False)

    print(f"\n  报告: {report_path.name}")
    return report_path


# ── 主入口 ────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="查询物料组 (Item Group) 按 custom_model_id 前缀"
    )
    ap.add_argument("--env", default=_DEFAULT_ENV, choices=list(_ENV_URLS.keys()),
                    help=f"目标环境 (默认 {_DEFAULT_ENV})")
    ap.add_argument("--prefix", default=_DEFAULT_PREFIX,
                    help=f"款式ID前缀 (默认 {_DEFAULT_PREFIX})")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅预览，不写文件")
    ap.add_argument("--json", action="store_true",
                    help="同时输出 JSON 备份")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    env = args.env
    env_url = _ENV_URLS[env]
    prefix = args.prefix.upper()

    # 取凭证
    key_name, secret_name = _ENV_KEY_MAP[env]
    api_key = os.getenv(key_name, "")
    api_secret = os.getenv(secret_name, "")
    if not api_key or not api_secret:
        print(f"错误: 请设置 {key_name} / {secret_name} 环境变量或写入 .env 文件")
        return 1

    env_label = f"{env}[{env_url}]"
    client = ErpnextClient(env_url, api_key, api_secret, label=env_label)

    # 查询
    matched, all_data = query_and_report(client, prefix, dry_run=args.dry_run)

    print(f"\n── 结果摘要 ──")
    print(f"  环境:        {env_label}")
    print(f"  前缀:        {prefix}")
    print(f"  匹配数:      {len(matched)}")
    print(f"  全量(参考):  {len(all_data)}")

    # 写入文件（非 dry-run）
    if not args.dry_run:
        report_path = generate_report(matched, all_data, prefix, env_label, ts, _DIR_OUT)

        # 可选 JSON 备份
        if args.json:
            json_path = _DIR_OUT / f"{prefix}物料组查询结果_{ts}.json"
            backup = {
                "metadata": {
                    "query_time": datetime.now().isoformat(),
                    "environment": env_label,
                    "prefix": prefix,
                    "total_matched": len(matched),
                    "total_all": len(all_data),
                    "description": f"EN 物料组 custom_model_id LIKE '{prefix}%' 查询结果",
                },
                "matched_records": matched,
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(backup, f, ensure_ascii=False, indent=2)
            print(f"  JSON:        {json_path.name}")

        print(f"\n[OK] 查询完成，结果已保存。")
    else:
        print(f"\n[dry-run 模式] 未写入任何文件。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
