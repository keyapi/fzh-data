# -*- coding: utf-8 -*-
"""统计 EN 系统"产品"子树下物料组 custom_pim_images 子表图片缺失情况。

用途:
  遍历"产品"及其所有子孙物料组，逐条查询完整物料组数据，
  检查 custom_pim_images 子表是否为空，统计缺失图片记录的物料组。
  输出 Excel 报告。

使用:
  python analyze_pim_images.py                        # 默认测试环境
  python analyze_pim_images.py --env prod              # 生产环境
  python analyze_pim_images.py --root "宠物类"          # 指定其他根节点
  python analyze_pim_images.py --dry-run               # 仅预览统计

输出:
  out/PIM图片缺失统计_{timestamp}.xlsx
"""

from __future__ import annotations

import argparse
import json
import os
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
_ITEM_GROUP = "Item Group"


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
        """获取全部物料组。fields=None 返回全部字段（仅限单文档字段，不含子表）。"""
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}"
        params: dict = {"limit_page_length": "0"}
        if fields is not None:
            params["fields"] = json.dumps(fields)
        else:
            params["limit"] = "0"
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def get_full(self, docname: str) -> dict[str, Any] | None:
        """获取单个物料组完整数据（含子表 custom_pim_images）。"""
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}/{docname}"
        try:
            resp = self._request("GET", url)
            return resp.json().get("data")
        except requests.RequestException as e:
            print(f"    [错误] 获取 {docname} 完整数据失败: {e}")
            return None

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
    if isinstance(val, float):
        s = str(val)
        if s.lower() in ("nan", "inf", "-inf"):
            return ""
    return str(val).strip()


# ── 主分析逻辑 ───────────────────────────────────────
def analyze(
    client: ErpnextClient,
    root_name: str,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """执行分析流程，返回每个物料组的 PIM 图片状态明细。"""
    label = client.label
    print(f"\n── 拉取 {label} 全量物料组列表 ──")

    # 1. 获取树结构
    all_data = client.fetch_all(fields=[
        "name", "item_group_name", "parent_item_group", "is_group", "custom_model_id",
    ])
    print(f"  共 {len(all_data)} 条物料组记录")

    idx = build_index(all_data)
    root_node = idx.get(root_name)
    if root_node is None:
        print(f"错误: 未找到根节点「{root_name}」")
        return []

    # 2. 获取子树
    subtree = get_subtree(root_name, idx)
    descendants = [d for d in subtree if d["name"] != root_name]
    print(f"  根节点「{root_name}」下共 {len(descendants)} 个子孙物料组")

    if not descendants:
        print("  没有需要分析的子孙节点。")
        return []

    group_count = sum(1 for d in descendants if d.get("is_group"))
    leaf_count = len(descendants) - group_count
    print(f"  其中组节点: {group_count}，叶节点: {leaf_count}")

    # 3. 逐条查询完整数据（含子表）
    print(f"\n── 逐条查询完整物料组数据 (共 {len(descendants)} 条) ──")
    results: list[dict[str, Any]] = []
    has_pim_count = 0
    no_pim_count = 0
    error_count = 0
    leaf_has_pim = 0
    leaf_no_pim = 0

    for i, d in enumerate(descendants, 1):
        name = d["name"]
        ig_name = d.get("item_group_name", "")
        is_group = d.get("is_group", 0)
        model_id = _to_str(d.get("custom_model_id", ""))
        ancestors = get_ancestors(name, idx)
        full_path = " / ".join(ancestors)

        # 进度提示（每 10% 或每 50 条）
        if i == 1 or i % max(1, len(descendants) // 10) == 0 or i == len(descendants):
            print(f"  [{i}/{len(descendants)}] 处理中... ({has_pim_count} 有图, {no_pim_count} 无图)")

        # 获取完整数据
        full = client.get_full(name)
        if full is None:
            error_count += 1
            results.append({
                "name": name,
                "item_group_name": ig_name,
                "parent_item_group": d.get("parent_item_group", ""),
                "is_group": "组" if is_group else "叶子",
                "full_path": full_path,
                "custom_model_id": model_id,
                "has_pim_images": False,
                "pim_image_count": 0,
                "pim_image_list": "",
                "status": "错误(获取失败)",
            })
            continue

        pim_rows = full.get("custom_pim_images") or []
        pim_count = len(pim_rows)
        has_pim = pim_count > 0

        if has_pim:
            has_pim_count += 1
            if not is_group:
                leaf_has_pim += 1
            # 提取图片文件名摘要
            pim_files = []
            for r in pim_rows:
                f = r.get("file_url", "") or r.get("image_file", "")
                # 只取文件名部分
                fname = Path(f).name if f else ""
                purpose = r.get("purpose", "")
                pim_files.append(f"{fname}({purpose})" if purpose else fname)
            pim_summary = "; ".join(pim_files[:5])
            if len(pim_files) > 5:
                pim_summary += f"... 共{pim_count}张"
        else:
            no_pim_count += 1
            if not is_group:
                leaf_no_pim += 1
            pim_summary = ""

        results.append({
            "name": name,
            "item_group_name": ig_name,
            "parent_item_group": d.get("parent_item_group", ""),
            "is_group": "组" if is_group else "叶子",
            "full_path": full_path,
            "custom_model_id": model_id,
            "has_pim_images": has_pim,
            "pim_image_count": pim_count,
            "pim_image_list": pim_summary,
            "status": "正常" if has_pim else "缺失",
        })

    # 4. 汇总输出
    print(f"\n── 分析完成 ──")
    print(f"  有 PIM 图片: {has_pim_count}")
    print(f"  无 PIM 图片: {no_pim_count}")
    if error_count:
        print(f"  查询失败:   {error_count}")
    print(f"  叶节点有图: {leaf_has_pim} / 叶节点无图: {leaf_no_pim}")

    if dry_run:
        print(f"\n  ── 缺失 PIM 图片概览 (前 20 条) ──")
        missing = [r for r in results if not r["has_pim_images"]]
        for r in missing[:20]:
            g = "(组)" if r["is_group"] == "组" else ""
            print(f"    {r['item_group_name']:30s} {g:5s} | {r['custom_model_id']:15s} | {r['full_path']}")
        if len(missing) > 20:
            print(f"    ... 还有 {len(missing)-20} 条")
        print(f"  共 {len(missing)} 个物料组缺失 PIM 图片")
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
    """生成 Excel 报告。"""
    report_path = out_dir / f"PIM图片缺失统计_{ts}.xlsx"

    total = len(results)
    has_pim = [r for r in results if r["has_pim_images"]]
    no_pim = [r for r in results if not r["has_pim_images"]]
    errors = [r for r in results if r["status"] == "错误(获取失败)"]
    leaf_no_pim = [r for r in no_pim if r["is_group"] == "叶子"]

    # ── Sheet 1: 汇总 ──
    pct_missing = round(len(no_pim) / total * 100, 1) if total else 0
    pct_leaf_missing = round(len(leaf_no_pim) / total * 100, 1) if total else 0

    summary = [
        {"统计项": "目标环境", "值": env_label},
        {"统计项": "根节点", "值": root_name},
        {"统计项": "子孙物料组总数", "值": total},
        {"统计项": "有 PIM 图片", "值": len(has_pim)},
        {"统计项": "无 PIM 图片", "值": len(no_pim)},
        {"统计项": "其中叶子节点缺失", "值": f"{len(leaf_no_pim)} ({pct_leaf_missing}%)"},
        {"统计项": "查询失败", "值": len(errors)},
        {"统计项": "缺失率", "值": f"{pct_missing}%"},
        {"统计项": "分析时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ]

    # ── Sheet 2: 缺失明细 ──
    columns = [
        ("item_group_name", "物料组名"),
        ("custom_model_id", "款式ID"),
        ("is_group", "类型"),
        ("parent_item_group", "父级"),
        ("full_path", "完整路径"),
    ]

    # ── Sheet 3: 有 PIM 图片明细（备查） ──
    detail_cols = columns + [
        ("pim_image_count", "图片数"),
        ("pim_image_list", "图片列表"),
    ]

    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        # 汇总
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)

        # 缺失明细
        if no_pim:
            rows = [{col[1]: r[col[0]] for col in columns} for r in no_pim]
            pd.DataFrame(rows).to_excel(writer, sheet_name="缺失PIM图片", index=False)
        else:
            pd.DataFrame(columns=[col[1] for col in columns]).to_excel(
                writer, sheet_name="缺失PIM图片", index=False,
            )

        # 有 PIM 图片的明细（备查）
        if has_pim:
            rows = [{col[1]: r[col[0]] for col in detail_cols} for r in has_pim]
            pd.DataFrame(rows).to_excel(writer, sheet_name="有PIM图片", index=False)
        else:
            pd.DataFrame(columns=[col[1] for col in detail_cols]).to_excel(
                writer, sheet_name="有PIM图片", index=False,
            )

        # 查询失败（如有）
        if errors:
            rows = [{col[1]: r[col[0]] for col in columns} for r in errors]
            pd.DataFrame(rows).to_excel(writer, sheet_name="查询失败", index=False)

    print(f"  报告: {report_path.name}")
    return report_path


# ── 主入口 ────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="统计物料组 custom_pim_images 子表图片缺失情况"
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

    no_pim = sum(1 for r in results if not r["has_pim_images"])
    total = len(results)
    print(f"\n── 结果摘要 ──")
    print(f"  环境:        {env_label}")
    print(f"  根节点:      {root_name}")
    print(f"  子孙总数:    {total}")
    print(f"  缺失 PIM 图片: {no_pim}/{total} ({round(no_pim/total*100, 1)}%)")

    if not args.dry_run:
        report_path = generate_report(results, root_name, env_label, ts, _DIR_OUT)
        print(f"\n[OK] 分析完成，结果已保存。")
    else:
        print(f"\n[dry-run 模式] 未写入任何文件。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
