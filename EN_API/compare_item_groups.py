# -*- coding: utf-8 -*-
"""EN 生产 vs 测试系统物料组 (Item Group) 对比分析 + 备份。

限定对比范围为指定根节点（默认"产品"）及其所有子孙节点，
不包括树中其他分支的物料组。

流程:
  1. 加载 .env 凭证 (TEST_ERP_API_KEY / PROD_ERP_API_KEY)
  2. 同时连接生产与测试环境，获取全部 Item Group
  3. 筛选指定根节点（默认"产品"）的子树
  4. 多维对比 (缺失/多余/树结构/名称/类型/自定义字段)
  5. 备份测试系统全量数据 (JSON)
  6. 生成对比报告 (Excel)

使用:
  python compare_item_groups.py                        # 对比"产品"子树 + 备份
  python compare_item_groups.py --root 家具类           # 对比"家具类"子树
  python compare_item_groups.py --root-all              # 对比全部（不限根节点）
  python compare_item_groups.py --backup-only           # 仅备份测试系统
"""

from __future__ import annotations

import json
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
    _DIR / ".env",
    _DIR.parent / ".env",
    _DIR.parent.parent / ".env",
    _DIR.parent / "tongtool_bundle_to_en" / ".env",   # 实际凭证位置
])


# ── 环境配置 ─────────────────────────────────────────
_ENV_URLS: dict[str, str] = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}

_ENV_KEY_MAP: dict[str, tuple[str, str]] = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}

# ── HTTP 适配器 ──────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


# ── ERPNext 客户端 ───────────────────────────────────
class ErpnextClient:
    """ERPNext REST API 客户端（轻量）。"""

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def fetch_all_item_groups(self) -> list[dict[str, Any]]:
        """获取全部 Item Group 记录。"""
        url = f"{self.base_url}/api/resource/Item Group"
        fields = json.dumps([
            "name", "item_group_name", "parent_item_group", "is_group",
            "image", "custom_model_id",
        ])
        params = {"fields": fields, "limit_page_length": "0"}
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def _request(
        self, method: str, url: str, *,
        retries: int = 2, retry_delay: float = 3.0,
        **kwargs: Any,
    ) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 60))
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


# ── 树工具 ───────────────────────────────────────────
def build_index(data: list[dict]) -> dict[str, dict]:
    """以 name 为 key 建立索引。"""
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


def find_node_by_name(name: str, data: list[dict]) -> dict | None:
    """在数据中查找 name 或 item_group_name 匹配的节点。"""
    for d in data:
        if d.get("name") == name or d.get("item_group_name") == name:
            return d
    return None


# ── 对比分析 ─────────────────────────────────────────
def compare_item_groups(
    prod_data: list[dict], test_data: list[dict],
) -> dict[str, Any]:
    """多维对比两个系统的物料组。"""
    prod_idx = build_index(prod_data)
    test_idx = build_index(test_data)

    prod_names = set(prod_idx.keys())
    test_names = set(test_idx.keys())

    missing = prod_names - test_names
    extra = test_names - prod_names
    common = prod_names & test_names

    tree_diff: list[dict] = []
    name_diff: list[dict] = []
    type_diff: list[dict] = []
    model_diff: list[dict] = []

    for name in sorted(common):
        p = prod_idx[name]
        t = test_idx[name]

        p_parent = p.get("parent_item_group") or ""
        t_parent = t.get("parent_item_group") or ""
        if p_parent != t_parent:
            tree_diff.append({
                "物料组名称": p.get("item_group_name", ""),
                "编码": name,
                "生产上级": p_parent,
                "测试上级": t_parent,
            })

        p_name = p.get("item_group_name", "")
        t_name = t.get("item_group_name", "")
        if p_name != t_name:
            name_diff.append({
                "编码": name,
                "生产名称": p_name,
                "测试名称": t_name,
            })

        p_is_group = p.get("is_group", 0)
        t_is_group = t.get("is_group", 0)
        if bool(p_is_group) != bool(t_is_group):
            type_diff.append({
                "物料组名称": p_name,
                "编码": name,
                "生产是组": "是" if p_is_group else "否",
                "测试是组": "是" if t_is_group else "否",
            })

        p_model = p.get("custom_model_id") or ""
        t_model = t.get("custom_model_id") or ""
        if p_model != t_model:
            model_diff.append({
                "物料组名称": p_name,
                "编码": name,
                "生产custom_model_id": str(p_model),
                "测试custom_model_id": str(t_model),
            })

    missing_rows = []
    for name in sorted(missing):
        p = prod_idx[name]
        missing_rows.append({
            "物料组名称": p.get("item_group_name", ""),
            "编码": name,
            "生产上级": p.get("parent_item_group") or "",
            "生产is_group": "是" if p.get("is_group") else "否",
            "生产custom_model_id": p.get("custom_model_id") or "",
        })

    extra_rows = []
    for name in sorted(extra):
        t = test_idx[name]
        extra_rows.append({
            "物料组名称": t.get("item_group_name", ""),
            "编码": name,
            "测试上级": t.get("parent_item_group") or "",
            "测试is_group": "是" if t.get("is_group") else "否",
            "测试custom_model_id": t.get("custom_model_id") or "",
        })

    return {
        "missing": missing_rows,
        "extra": extra_rows,
        "tree_diff": tree_diff,
        "name_diff": name_diff,
        "type_diff": type_diff,
        "model_diff": model_diff,
        "_stats": {
            "生产子系统节点数": len(prod_data),
            "测试子系统节点数": len(test_data),
            "共有": len(common),
            "缺失(生产有-测试无)": len(missing),
            "多余(测试有-生产无)": len(extra),
            "树结构不一致": len(tree_diff),
            "名称不一致": len(name_diff),
            "类型不一致": len(type_diff),
            "custom_model_id不一致": len(model_diff),
        },
    }


# ── 备份 ─────────────────────────────────────────────
def backup_test_data(data: list[dict], out_dir: Path) -> Path:
    """备份测试系统全量数据为 JSON。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"物料组备份_测试_EN_{ts}.json"
    payload = {
        "backup_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "EN测试系统 (ensh.vilavi.cn)",
        "doctype": "Item Group",
        "count": len(data),
        "data": data,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ── 报告生成 ─────────────────────────────────────────
def _write_sheet(writer: pd.ExcelWriter, sheet_name: str,
                 rows: list[dict], columns: list[str]) -> None:
    if rows:
        df = pd.DataFrame(rows)
        df = df[[c for c in columns if c in df.columns]]
    else:
        df = pd.DataFrame([{"说明": "（无数据）"}])
    df.to_excel(writer, sheet_name=sheet_name, index=False)


def _make_test_rows(test_data: list[dict]) -> list[dict]:
    rows = []
    for d in sorted(test_data, key=lambda x: (x.get("parent_item_group") or "", x.get("item_group_name") or "")):
        rows.append({
            "编码": d.get("name", ""),
            "物料组名称": d.get("item_group_name", ""),
            "上级": d.get("parent_item_group") or "",
            "is_group": "是" if d.get("is_group") else "否",
            "custom_model_id": d.get("custom_model_id") or "",
            "image": d.get("image") or "",
        })
    return rows


def write_report(
    result: dict[str, Any],
    backup_path: Path | None,
    root_name: str,
    prod_all: list[dict],
    test_all: list[dict],
    prod_sub: list[dict],
    test_sub: list[dict],
    out_dir: Path,
) -> Path:
    """生成多 sheet 对比报告 Excel。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"物料组对比报告_{ts}.xlsx"
    stats = result["_stats"]

    summary_rows = [
        {"指标": "对比范围", "数值": f"根节点「{root_name}」及其子孙"},
        {"指标": "生产系统该子树节点数", "数值": len(prod_sub)},
        {"指标": "测试系统该子树节点数", "数值": len(test_sub)},
        {"指标": "生产系统全量", "数值": len(prod_all)},
        {"指标": "测试系统全量", "数值": len(test_all)},
    ]
    for k, v in stats.items():
        summary_rows.append({"指标": k, "数值": v})
    if backup_path:
        summary_rows.append({"指标": "备份文件", "数值": backup_path.name})
        summary_rows.append({"指标": "备份记录数", "数值": len(test_all)})

    test_rows = _make_test_rows(test_sub)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="汇总", index=False)

        _write_sheet(writer, "缺失节点(生产有-测试无)", result["missing"],
                      ["物料组名称", "编码", "生产上级", "生产is_group", "生产custom_model_id"])
        _write_sheet(writer, "多余节点(测试有-生产无)", result["extra"],
                      ["物料组名称", "编码", "测试上级", "测试is_group", "测试custom_model_id"])
        _write_sheet(writer, "树结构不一致", result["tree_diff"],
                      ["物料组名称", "编码", "生产上级", "测试上级"])
        _write_sheet(writer, "名称不一致", result["name_diff"],
                      ["编码", "生产名称", "测试名称"])
        _write_sheet(writer, "类型(is_group)不一致", result["type_diff"],
                      ["物料组名称", "编码", "生产是组", "测试是组"])
        _write_sheet(writer, "custom_model_id不一致", result["model_diff"],
                      ["物料组名称", "编码", "生产custom_model_id", "测试custom_model_id"])

        df_test = pd.DataFrame(test_rows)
        if df_test.empty:
            df_test = pd.DataFrame([{"说明": "（无数据）"}])
        df_test.to_excel(writer, sheet_name="测试子树完整备份", index=False)

    return path


# ── 主入口 ─────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="EN 生产 vs 测试系统物料组对比分析 + 备份（限定根节点子树）")
    ap.add_argument("--root", default="产品",
                    help="根节点名称（name 或 item_group_name），默认「产品」，仅对比该节点及其子孙")
    ap.add_argument("--root-all", action="store_true",
                    help="对比全部物料组（不限根节点）")
    ap.add_argument("--backup-only", action="store_true",
                    help="仅备份测试系统，不做对比")
    ap.add_argument("--out-dir", type=Path, default=_DIR_OUT,
                    help="输出目录 (默认 out/)")
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    prod_key = os.getenv("PROD_ERP_API_KEY", "")
    prod_secret = os.getenv("PROD_ERP_API_SECRET", "")
    test_key = os.getenv("TEST_ERP_API_KEY", "")
    test_secret = os.getenv("TEST_ERP_API_SECRET", "")

    if not all([prod_key, prod_secret, test_key, test_secret]):
        print("错误: 请确保 .env 文件中设置了以下环境变量:")
        print("  PROD_ERP_API_KEY / PROD_ERP_API_SECRET")
        print("  TEST_ERP_API_KEY / TEST_ERP_API_SECRET")
        return 1

    prod_url = _ENV_URLS["prod"]
    test_url = _ENV_URLS["test"]

    # ── 仅备份模式 ──
    if args.backup_only:
        print(f"测试环境: {test_url}")
        print("正在获取测试系统物料组...")
        client = ErpnextClient(test_url, test_key, test_secret)
        test_data = client.fetch_all_item_groups()
        print(f"  获取到 {len(test_data)} 条记录")
        bp = backup_test_data(test_data, out_dir)
        print(f"备份完成: {bp}")
        return 0

    # ── 获取数据 ──
    print(f"生产环境: {prod_url}")
    print(f"测试环境: {test_url}")

    prod_client = ErpnextClient(prod_url, prod_key, prod_secret)
    test_client = ErpnextClient(test_url, test_key, test_secret)

    try:
        prod_all = prod_client.fetch_all_item_groups()
        print(f"  生产系统: {len(prod_all)} 条记录")
    except requests.RequestException as e:
        print(f"错误: 连接生产系统失败: {e}")
        return 1

    try:
        test_all = test_client.fetch_all_item_groups()
        print(f"  测试系统: {len(test_all)} 条记录")
    except requests.RequestException as e:
        print(f"错误: 连接测试系统失败: {e}")
        return 1

    # ── 确定对比范围 ──
    if args.root_all:
        prod_sub = prod_all
        test_sub = test_all
        root_name = "全部物料组"
        print("对比范围: 全部物料组")
    else:
        root_name = args.root
        # 先在生产系统找根节点
        root_node = find_node_by_name(root_name, prod_all)
        if root_node is None:
            print(f"错误: 在生产系统中找不到名为「{root_name}」的节点")
            print("可用 --root-all 对比全部物料组")
            return 1

        actual_root_name = root_node["name"]
        print(f"根节点: {actual_root_name} ({root_node.get('item_group_name', '')})")

        prod_idx = build_index(prod_all)
        test_idx = build_index(test_all)

        prod_sub = get_subtree(actual_root_name, prod_idx)
        test_sub = get_subtree(actual_root_name, test_idx)

        if actual_root_name in test_idx:
            test_sub_incl = test_sub  # 测试也有该节点
        else:
            test_sub_incl = []  # 测试没有该根节点

        print(f"  生产系统该子树: {len(prod_sub)} 个节点")
        print(f"  测试系统该子树: {len(test_sub)} 个节点")

    # ── 对比分析 ──
    print("正在对比分析...")
    result = compare_item_groups(prod_sub, test_sub)
    stats = result["_stats"]
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # ── 备份测试系统全量 ──
    bp = backup_test_data(test_all, out_dir)
    print(f"测试系统全量备份: {bp}")

    # ── 生成报告 ──
    # 报告中的"测试系统完整备份"sheet 只包含子树范围的数据
    rpt = write_report(result, bp, root_name,
                       prod_all, test_all, prod_sub, test_sub, out_dir)
    print(f"对比报告: {rpt}")
    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
