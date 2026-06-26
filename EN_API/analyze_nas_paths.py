# -*- coding: utf-8 -*-
"""统计 EN 测试系统"产品"子树下物料组 custom_nas_path_link 路径缺失情况。

用途:
  遍历"产品"及其所有子孙物料组，检查 custom_nas_path_link 字段中
  图片 / 设计稿 / 视频 / 调研报告 四类路径的存在情况，统计缺失项。
  输出 Excel 报告，每个缺失类别一个 Sheet。

使用:
  python analyze_nas_paths.py                        # 默认测试环境
  python analyze_nas_paths.py --env prod              # 生产环境
  python analyze_nas_paths.py --root "宠物类"          # 指定其他根节点
  python analyze_nas_paths.py --dry-run               # 仅预览统计

输出:
  out/NAS路径缺失统计_{timestamp}.xlsx
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
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

# ── 环境配置 ──────────────────────────────────────────
_ENV_URLS: dict[str, str] = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}

_ENV_KEY_MAP: dict[str, tuple[str, str]] = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}

_DEFAULT_ENV = "test"
_DEFAULT_ROOT = "产品"

# 需要检查的路径类别
_CATEGORIES = ["图片", "设计稿", "视频", "调研报告"]


# ── .env 加载 (stdlib only) ───────────────────────────
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


# ── ERPNext 客户端 ────────────────────────────────────
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
        raise last  # type: ignore[misc]


# ── 树工具函数 ───────────────────────────────────────
def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def get_descendants(name: str, idx: dict[str, dict]) -> list[dict]:
    """递归获取指定节点下的所有子孙节点（不包含自身）。"""
    result: list[dict] = []
    children = [d for d in idx.values() if d.get("parent_item_group") == name]
    for c in children:
        result.append(c)
        result.extend(get_descendants(c["name"], idx))
    return result


def get_subtree(name: str, idx: dict[str, dict]) -> list[dict]:
    """获取指定节点及其所有子孙节点。"""
    node = idx.get(name)
    if node is None:
        return []
    return [node] + get_descendants(name, idx)


def get_ancestors(node_name: str, idx: dict[str, dict]) -> list[str]:
    """从节点到根构建路径列表。"""
    parts: list[str] = []
    current = node_name
    visited: set[str] = set()
    while current and current in idx and current not in visited:
        parts.insert(0, current)
        visited.add(current)
        current = idx[current].get("parent_item_group", "")
    return parts


def _to_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and (val != val or val != val):  # NaN check
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null", ""):
        return ""
    return s


# ── NAS 路径解析 ─────────────────────────────────────
def parse_nas_paths(nas_html: str | None) -> dict[str, str]:
    """解析 custom_nas_path_link HTML 字段，返回 {类别: 路径} 字典。

    ERPNext 富文本编辑器将数据存为 HTML 格式：
      <p><strong>图片:</strong> <a href="..." target="_blank">/产品信息/.../图片</a></p>
      <p><strong>设计稿:</strong> <a href="..." target="_blank">/产品信息/.../设计稿</a></p>

    输出:
      {"图片": "/产品信息/.../图片",
       "设计稿": "/产品信息/.../设计稿"}
    """
    result: dict[str, str] = {}
    if not nas_html:
        return result
    # 匹配 <strong>标签:</strong> <a ...>路径</a>
    for m in re.finditer(
        r"<strong>\s*(.+?)\s*:\s*</strong>\s*<a\s[^>]*>\s*(/.+?)\s*</a>",
        nas_html,
    ):
        label = m.group(1).strip()
        path = m.group(2).strip()
        result[label] = path
    return result


# ── 主分析逻辑 ───────────────────────────────────────
def analyze(
    client: ErpnextClient,
    root_name: str,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    执行分析流程，返回每个物料组的路径情况明细。
    每条记录包含: 名称、物料组名、完整路径、类型、custom_nas_path_link、各路径存在状态。
    """
    label = client.label
    print(f"\n── 拉取 {label} 全量物料组数据 ──")

    # 1. 全量拉取（显式指定字段确保 custom_nas_path_link 被返回）
    all_data = client.fetch_all(fields=[
        "name", "item_group_name", "parent_item_group", "is_group",
        "custom_model_id", "custom_nas_path_link",
    ])
    print(f"  共 {len(all_data)} 条物料组记录")

    # 2. 构建索引
    idx = build_index(all_data)
    root_node = idx.get(root_name)
    if root_node is None:
        print(f"错误: 未找到根节点「{root_name}」")
        return []

    # 3. 获取子树
    subtree = get_subtree(root_name, idx)
    # 排除根节点自身（只统计子孙）
    descendants = [d for d in subtree if d["name"] != root_name]
    print(f"  根节点「{root_name}」下共 {len(descendants)} 个子孙物料组")

    if not descendants:
        print("  没有需要分析的子孙节点。")
        return []

    # 4. 解析每个物料组的 NAS 路径
    results: list[dict[str, Any]] = []
    total_with_field = 0
    cat_count: Counter = Counter()

    for d in descendants:
        item_name = d["name"]
        ig_name = d.get("item_group_name", "")
        is_group = d.get("is_group", 0)
        nas_raw = d.get("custom_nas_path_link", None)
        nas_text = _to_str(nas_raw)
        parent = d.get("parent_item_group", "")
        model_id = _to_str(d.get("custom_model_id", ""))
        ancestors = get_ancestors(item_name, idx)
        full_path = " / ".join(ancestors)

        parsed = parse_nas_paths(nas_text)

        record: dict[str, Any] = {
            "name": item_name,
            "item_group_name": ig_name,
            "parent_item_group": parent,
            "is_group": "组" if is_group else "叶子",
            "full_path": full_path,
            "custom_model_id": model_id,
            "has_nas_field": bool(nas_text),
            "nas_path_count": len(parsed),
        }

        if nas_text:
            total_with_field += 1

        # 标记每个类别是否存在
        for cat in _CATEGORIES:
            record[f"has_{cat}"] = cat in parsed
            if cat in parsed:
                cat_count[cat] += 1
                record[f"{cat}_path"] = parsed[cat]
            else:
                record[f"{cat}_path"] = ""

        results.append(record)

    # 5. 汇总信息
    group_count = sum(1 for d in descendants if d.get("is_group"))
    leaf_count = sum(1 for d in descendants if not d.get("is_group"))

    print(f"  其中组节点: {group_count}，叶节点: {leaf_count}")
    print(f"  有 NAS 路径配置: {total_with_field}")
    print(f"  各类别覆盖数: {dict(cat_count)}")
    print()

    # dry-run 打印概览
    if dry_run:
        print(f"  ── NAS 路径缺失概览 (前 20 条) ──")
        missing_rows = []
        for r in results:
            missing = [c for c in _CATEGORIES if not r[f"has_{c}"]]
            if missing:
                missing_rows.append((r["item_group_name"], missing))
        for ig, miss in missing_rows[:20]:
            print(f"    {ig:30s} | 缺失: {', '.join(miss)}")
        if len(missing_rows) > 20:
            print(f"    ... 还有 {len(missing_rows)-20} 条")
        print(f"  共 {len(missing_rows)} 个物料组存在路径缺失")
        print()

    return results


# ── 报告生成 ─────────────────────────────────────────
def generate_report(
    results: list[dict[str, Any]],
    root_name: str,
    env_label: str,
    ts: str,
    out_dir: Path,
) -> Path:
    """生成 Excel 报告，包含汇总和每个缺失类别的明细 Sheet。"""
    report_path = out_dir / f"NAS路径缺失统计_{ts}.xlsx"

    # ── Sheet 1: 汇总 ──
    total_items = len(results)
    items_with_field = sum(1 for r in results if r["has_nas_field"])
    items_without_field = total_items - items_with_field

    # 各缺失类别的计数
    missing_counts: dict[str, int] = {}
    for cat in _CATEGORIES:
        missing_counts[cat] = sum(1 for r in results if not r[f"has_{cat}"])

    summary_rows = [
        {"统计项": "目标环境", "值": env_label},
        {"统计项": "根节点", "值": root_name},
        {"统计项": "子孙物料组总数", "值": total_items},
        {"统计项": "有 NAS 路径配置", "值": items_with_field},
        {"统计项": "无 NAS 路径配置(完全缺失)", "值": items_without_field},
        {"统计项": "分析时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ]
    # 添加空行方便阅读
    summary_rows.append({"统计项": "", "值": ""})
    summary_rows.append({"统计项": "各类别缺失统计", "值": ""})
    for cat in _CATEGORIES:
        pct = round(missing_counts[cat] / total_items * 100, 1) if total_items else 0
        summary_rows.append({
            "统计项": f"  缺失「{cat}」路径",
            "值": f"{missing_counts[cat]} 个物料组 ({pct}%)",
        })

    # ── Sheet 2-5: 各缺失类别明细 ──
    columns = [
        ("name", "名称"),
        ("item_group_name", "物料组名"),
        ("parent_item_group", "父级"),
        ("is_group", "类型"),
        ("full_path", "完整路径"),
        ("custom_model_id", "款式ID"),
    ]
    # 加上路径列
    detail_cols = columns + [(f"{cat}_path", f"{cat}路径") for cat in _CATEGORIES]

    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        # 汇总 Sheet
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="汇总", index=False)

        # 每个类别一个 Sheet
        for cat in _CATEGORIES:
            missing_items = [r for r in results if not r[f"has_{cat}"]]
            sheet_name = f"缺失_{cat}"
            if missing_items:
                rows = []
                for r in missing_items:
                    row = {col[1]: r[col[0]] for col in columns}
                    # 追加所有路径列，方便对照
                    for c in _CATEGORIES:
                        row[f"{c}路径"] = r.get(f"{c}_path", "")
                    rows.append(row)
                pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                # 无缺失时放空表头
                headers = [col[1] for col in columns] + [f"{c}路径" for c in _CATEGORIES]
                pd.DataFrame(columns=headers).to_excel(
                    writer, sheet_name=sheet_name, index=False,
                )

        # 额外: 完全无 NAS 路径配置的物料组
        no_field_items = [r for r in results if not r["has_nas_field"]]
        if no_field_items:
            rows = [{col[1]: r[col[0]] for col in columns} for r in no_field_items]
            pd.DataFrame(rows).to_excel(
                writer, sheet_name="完全无NAS路径", index=False,
            )
        else:
            headers = [col[1] for col in columns]
            pd.DataFrame(columns=headers).to_excel(
                writer, sheet_name="完全无NAS路径", index=False,
            )

    print(f"  报告: {report_path.name}")
    return report_path


# ── 主入口 ────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="统计物料组 NAS 存储路径 custom_nas_path_link 缺失情况"
    )
    ap.add_argument("--env", default=_DEFAULT_ENV, choices=list(_ENV_URLS.keys()),
                    help=f"目标环境 (默认 {_DEFAULT_ENV})")
    ap.add_argument("--root", default=_DEFAULT_ROOT,
                    help=f"根节点名称 (默认 {_DEFAULT_ROOT})")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅预览统计，不写文件")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    env = args.env
    env_url = _ENV_URLS[env]
    root_name = args.root

    # 取凭证
    key_name, secret_name = _ENV_KEY_MAP[env]
    api_key = os.getenv(key_name, "")
    api_secret = os.getenv(secret_name, "")
    if not api_key or not api_secret:
        print(f"错误: 请设置 {key_name} / {secret_name} 环境变量或写入 .env 文件")
        return 1

    env_label = f"{env}[{env_url}]"
    client = ErpnextClient(env_url, api_key, api_secret, label=env_label)

    # 执行分析
    results = analyze(client, root_name, dry_run=args.dry_run)

    if not results:
        print("没有分析结果。")
        return 0

    # 汇总输出
    missing_counts = {
        cat: sum(1 for r in results if not r[f"has_{cat}"])
        for cat in _CATEGORIES
    }
    print(f"── 结果摘要 ──")
    print(f"  环境:        {env_label}")
    print(f"  根节点:      {root_name}")
    print(f"  子孙总数:    {len(results)}")
    for cat in _CATEGORIES:
        pct = round(missing_counts[cat] / len(results) * 100, 1)
        print(f"  缺失「{cat}」: {missing_counts[cat]}/{len(results)} ({pct}%)")

    # 写入文件（非 dry-run）
    if not args.dry_run:
        report_path = generate_report(results, root_name, env_label, ts, _DIR_OUT)
        print(f"\n[OK] 分析完成，结果已保存。")
    else:
        print(f"\n[dry-run 模式] 未写入任何文件。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
