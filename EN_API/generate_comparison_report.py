# -*- coding: utf-8 -*-
"""将重构后的 EN 测试系统与赛狐导出数据进行多维度对比，生成详细报告。"""
from __future__ import annotations

import json
import os
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
_DIR_DATA = _DIR / "数据源"
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)


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

    def fetch_all_item_groups(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/Item Group"
        fields = json.dumps([
            "name", "item_group_name", "parent_item_group", "is_group",
            "image", "custom_model_id",
        ])
        params = {"fields": fields, "limit_page_length": "0"}
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def _request(self, method: str, url: str, *,
                 retries: int = 2, retry_delay: float = 3.0,
                 **kwargs: Any) -> requests.Response:
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
        raise last


# ── 工具 ──
def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


# ── 读取赛狐分类导出 ──
def load_saihu_categories(path: Path) -> list[dict]:
    """读取商品分类导出，返回分类树节点列表（含完整路径）。"""
    df = pd.read_excel(path, sheet_name=0)
    nodes: list[dict] = []
    seen = set()

    for _, row in df.iterrows():
        levels = []
        # 列索引: 0=一级, 2=二级, 4=三级, 6=四级
        for idx in [0, 2, 4, 6]:
            val = row.iloc[idx]
            if pd.notna(val) and str(val).strip():
                levels.append(str(val).strip())
            else:
                break
        if not levels:
            continue

        full_path = "/".join(levels)
        for i, name in enumerate(levels):
            parent = levels[i - 1] if i > 0 else ""
            # 根节点 parent=""，后续处理为"产品"
            key = f"{parent}|{name}"
            if key not in seen:
                seen.add(key)
                nodes.append({
                    "name": name,
                    "parent": parent,
                    "level": i + 1,
                    "full_path": full_path if i == len(levels) - 1 else "/".join(levels[:i+1]),
                })
    return nodes


# ── 读取 Commodities ──
def load_commodities(path: Path) -> tuple[dict[str, str], pd.DataFrame]:
    """读取 Commodities xlsx，返回 (spu→分类路径映射, 完整DataFrame)。"""
    df = pd.read_excel(path, sheet_name=0)
    spu_to_cat: dict[str, str] = {}
    for _, row in df.iterrows():
        spu = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""
        cat = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        if spu and cat and spu.lower() != "nan":
            spu_to_cat[spu] = cat
    return spu_to_cat, df


# ── 主对比逻辑 ──
def main() -> int:
    # ── 1. 连接EN ──
    test_key = os.getenv("TEST_ERP_API_KEY", "")
    test_secret = os.getenv("TEST_ERP_API_SECRET", "")
    if not test_key or not test_secret:
        print("错误: 请设置 TEST_ERP_API_KEY / TEST_ERP_API_SECRET")
        return 1
    client = ErpnextClient("https://ensh.vilavi.cn", test_key, test_secret)
    print("获取EN测试系统数据...")
    en_data = client.fetch_all_item_groups()
    en_idx = build_index(en_data)
    print(f"  EN节点数: {len(en_data)}")

    # ── 2. 读取赛狐分类导出 ──
    cat_file = sorted([f for f in _DIR_DATA.iterdir()
                       if "商品分类" in f.name])[-1]
    print(f"\n读取分类导出: {cat_file.name}")
    expected_cats = load_saihu_categories(cat_file)
    print(f"  赛狐分类节点: {len(expected_cats)}")

    # ── 3. 读取Commodities ──
    commod_files = sorted([f for f in _DIR_DATA.iterdir()
                          if "Commodities" in f.name or "commodities" in f.name])
    if not commod_files:
        print(f"错误: 找不到 Commodities 文件")
        print(f"  可用文件: {[f.name for f in _DIR_DATA.iterdir() if f.suffix=='.xlsx']}")
        return 1
    commod_file = commod_files[-1]
    print(f"\n读取商品文件: {commod_file.name}")
    spu_to_cat, commod_df = load_commodities(commod_file)
    print(f"  SPU→分类映射: {len(spu_to_cat)} 条")
    print(f"  商品总行数: {len(commod_df)}")

    # ════════════════════════════════════════════════
    # 对比维度1: 分类结构对比
    # ════════════════════════════════════════════════
    print("\n── 维度1: 分类结构对比 ──")
    cat_rows = []
    for n in expected_cats:
        # 查找EN中是否存在 (item_group_name, parent) 组合
        parent = n["parent"] or "产品"
        en_name = n["name"]
        en_match = None
        for d in en_data:
            if (d.get("item_group_name") == en_name
                    and (d.get("parent_item_group") or "") == parent):
                en_match = d
                break

        status = "一致"
        notes = ""
        if en_match:
            en_is_group = bool(en_match.get("is_group", 0))
            expected_is_group = True  # 赛狐分类节点都是组
            if en_is_group != expected_is_group:
                status = "类型不匹配"
                notes = f"EN is_group={en_is_group}, 期望=True"
            # 检查祖先路径
            ancestors_ok = _check_ancestors(en_match, en_idx, n, expected_cats)
            if not ancestors_ok:
                status = "路径不完整"
                notes = "上级节点缺失"
        else:
            status = "缺失"
            notes = f"EN中无 ({en_name}, {parent}) 组合"

        cat_rows.append({
            "层级": n["level"],
            "赛狐分类名称": n["name"],
            "赛狐父级": n["parent"],
            "完整路径": n["full_path"],
            "状态": status,
            "备注": notes,
            "EN名称": en_match["name"] if en_match else "",
            "EN父级": en_match.get("parent_item_group", "") if en_match else "",
            "EN is_group": en_match.get("is_group", "") if en_match else "",
        })

    df_cats = pd.DataFrame(cat_rows)
    cat_ok = len([r for r in cat_rows if r["状态"] == "一致"])
    cat_missing = len([r for r in cat_rows if r["状态"] == "缺失"])
    cat_mismatch = len([r for r in cat_rows if r["状态"] != "一致"])

    # ════════════════════════════════════════════════
    # 对比维度2: SPU产品映射对比
    # ════════════════════════════════════════════════
    print("── 维度2: SPU产品映射对比 ──")
    spu_rows = []

    # EN中所有有custom_model_id的节点
    en_by_model: dict[str, list[dict]] = {}
    for d in en_data:
        mid = str(d.get("custom_model_id") or "").strip()
        if mid and mid.lower() not in ("nan", "none", ""):
            en_by_model.setdefault(mid, []).append(d)

    # 遍历Commodities中所有唯一的SPU
    unique_spus = commod_df.iloc[:, 3].dropna().unique()
    matched = 0
    unmatched = 0
    match_detail_rows = []

    for spu in unique_spus:
        spu = str(spu).strip()
        if not spu or spu.lower() == "nan":
            continue

        expected_cat = spu_to_cat.get(spu, "")
        expected_leaf = expected_cat.split("/")[-1].strip() if expected_cat else ""
        en_nodes = en_by_model.get(spu, [])

        if not en_nodes:
            unmatched += 1
            spu_rows.append({
                "SPU": spu,
                "预期分类路径": expected_cat,
                "预期应位于": expected_leaf,
                "EN节点数": 0,
                "状态": "EN中无此SPU",
                "EN节点名称": "",
                "EN实际父级": "",
            })
            continue

        # 检查每个EN节点位置
        for en_node in en_nodes:
            en_name = en_node.get("item_group_name", "")
            current_parent = en_node.get("parent_item_group", "") or ""
            current_path = _get_path(en_node, en_idx)

            # 判断是否正确
            is_correct = current_parent == expected_leaf
            # 判断是否是产品即分类的例外
            is_conflict = (not is_correct and expected_leaf == en_name)

            if is_correct:
                status = "正确"
            elif is_conflict:
                status = "例外(产品即分类)"
            else:
                status = "位置不对"
            if is_correct:
                matched += 1

    df_spu = pd.DataFrame(spu_rows)

    # ════════════════════════════════════════════════
    # 对比维度3: EN中custom_model_id的分布
    # ════════════════════════════════════════════════
    print("── 维度3: EN custom_model_id 覆盖率 ──")
    en_model_ids = set(en_by_model.keys())
    commod_spus = {str(s).strip() for s in unique_spus
                   if str(s).strip().lower() != "nan" and str(s).strip()}
    covered = en_model_ids & commod_spus
    en_only = en_model_ids - commod_spus
    commod_only = commod_spus - en_model_ids

    coverage_rows = [
        {"类别": "赛狐SPU总数", "数量": len(commod_spus)},
        {"类别": "EN中有custom_model_id的SPU数", "数量": len(en_model_ids)},
        {"类别": "双方匹配的SPU数", "数量": len(covered)},
        {"类别": "赛狐有但EN无的SPU", "数量": len(commod_only)},
        {"类别": "EN有但赛狐无的SPU", "数量": len(en_only)},
        {"类别": "覆盖率 (EN/赛狐)", "数量": f"{len(covered)/len(commod_spus)*100:.1f}%" if commod_spus else "N/A"},
    ]
    df_coverage = pd.DataFrame(coverage_rows)

    # 赛狐有但EN无的明细
    commod_only_rows = []
    for spu in sorted(commod_only):
        cat = spu_to_cat.get(spu, "")
        commod_only_rows.append({"SPU": spu, "预期分类": cat, "可能原因": "EN中无此custom_model_id的产品"})
    df_commod_only = pd.DataFrame(commod_only_rows)

    # EN有但赛狐无的明细
    en_only_rows = []
    for spu in sorted(en_only):
        nodes = en_by_model[spu]
        for n in nodes:
            en_only_rows.append({
                "SPU": spu,
                "EN节点名": n.get("item_group_name", ""),
                "所在分类": n.get("parent_item_group", ""),
                "可能原因": "赛狐未导出此SPU或已废弃",
            })
    df_en_only = pd.DataFrame(en_only_rows)

    # ════════════════════════════════════════════════
    # 对比维度4: 商品行级映射（变体级别）
    # ════════════════════════════════════════════════
    print("── 维度4: SKU变体级映射 ──")
    # 给Commodities每行添加EN对照信息
    commod_rows = []
    for _, row in commod_df.iterrows():
        sku = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        cat = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        spu = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""
        img = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ""

        # 在EN中查找custom_model_id为该SPU的节点
        en_nodes = en_by_model.get(spu, [])
        en_names = [n.get("item_group_name", "") for n in en_nodes]
        en_parents = [n.get("parent_item_group", "") for n in en_nodes]
        cat_leaf = cat.split("/")[-1].strip() if cat else ""
        en_is_correct = any(
            n.get("parent_item_group", "") == cat_leaf
            for n in en_nodes
        ) if en_nodes and cat else False

        # 判断: 产品名=分类名的例外(产品本身就是赛狐分类节点)
        is_name_conflict = False
        if en_nodes and cat and not en_is_correct:
            en_gn = en_nodes[0].get("item_group_name", "")
            if en_gn == cat_leaf:
                is_name_conflict = True

        if en_is_correct:
            status = "正确"
        elif is_name_conflict:
            status = "例外(产品即分类)"
        else:
            status = "位置不对" if en_nodes else "EN中无此SPU"

        commod_rows.append({
            "SKU": sku,
            "品名": name,
            "赛狐分类路径": cat,
            "SPU": spu,
            "图片": img,
            "EN匹配节点数": len(en_nodes),
            "EN节点名": "; ".join(en_names) if en_names else "",
            "EN所在父级": "; ".join(en_parents) if en_parents else "",
            "状态": status,
        })
    df_commod_detail = pd.DataFrame(commod_rows)

    # ════════════════════════════════════════════════
    # 写出报告
    # ════════════════════════════════════════════════
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = _DIR_OUT / f"重构对比报告_{ts}.xlsx"

    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        # Sheet 1: 汇总
        summary = [
            {"指标": "数据源", "值": f"Commodities: {commod_file.name}"},
            {"指标": "", "值": f"分类导出: {cat_file.name}"},
            {"指标": "EN测试系统节点数", "值": len(en_data)},
            {"指标": "赛狐分类节点(预期)", "值": len(expected_cats)},
            {"指标": "分类节点一致", "值": cat_ok},
            {"指标": "分类节点缺失", "值": cat_missing},
            {"指标": "分类节点不匹配", "值": cat_mismatch},
            {"指标": "赛狐SPU总数", "值": len(commod_spus)},
            {"指标": "EN有custom_model_id的SPU", "值": len(en_model_ids)},
            {"指标": "SPU匹配数", "值": len(covered)},
            {"指标": "SPU覆盖率", "值": f"{len(covered)/len(commod_spus)*100:.1f}%" if commod_spus else "N/A"},
            {"指标": "赛狐有EN无的SPU", "值": len(commod_only)},
            {"指标": "EN有赛狐无的SPU", "值": len(en_only)},
            {"指标": "商品行总数(Commodities)", "值": len(commod_df)},
            {"指标": "商品行映射正确", "值": len([r for r in commod_rows if r["状态"] == "正确"])},
            {"指标": "商品行例外(产品即分类)", "值": len([r for r in commod_rows if r["状态"] == "例外(产品即分类)"])},
            {"指标": "商品行EN中无此SPU", "值": len([r for r in commod_rows if r["状态"] == "EN中无此SPU"])},
            {"指标": "商品行位置不对", "值": len([r for r in commod_rows if r["状态"] == "位置不对"])},
            {"指标": "报告生成时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        ]
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)

        # Sheet 2: 分类对比
        df_cats.to_excel(writer, sheet_name="分类结构对比", index=False)

        # Sheet 3: SPU映射
        df_spu.to_excel(writer, sheet_name="SPU产品映射", index=False)

        # Sheet 4: SPU覆盖率
        df_coverage.to_excel(writer, sheet_name="SPU覆盖率", index=False)

        # Sheet 5: 赛狐有EN无的SPU
        if not df_commod_only.empty:
            df_commod_only.to_excel(writer, sheet_name="赛狐有EN无的SPU", index=False)

        # Sheet 6: EN有赛狐无的SPU
        if not df_en_only.empty:
            df_en_only.to_excel(writer, sheet_name="EN有赛狐无的SPU", index=False)

        # Sheet 7: 商品行级详情（取前2000行避免过大）
        df_commod_detail.to_excel(writer, sheet_name="商品行映射详情", index=False)

    print(f"\n报告已生成: {report_path}")
    return 0


def _check_ancestors(en_node: dict, en_idx: dict, cat_node: dict,
                     expected_cats: list[dict]) -> bool:
    """检查EN节点的祖先路径是否完整。"""
    parent = en_node.get("parent_item_group", "")
    cat_parent = cat_node.get("parent", "")
    if not cat_parent:
        return True  # 根节点，已在产品下
    parent_node = en_idx.get(parent) if parent else None
    if parent_node is None:
        return False
    # 递归检查父级
    parent_cat = next((c for c in expected_cats if c["name"] == cat_parent), None)
    if parent_cat:
        return _check_ancestors(parent_node, en_idx, parent_cat, expected_cats)
    return True


def _get_path(en_node: dict, en_idx: dict) -> str:
    """追溯EN节点的完整路径。"""
    parts = [en_node.get("item_group_name", "")]
    parent = en_node.get("parent_item_group", "")
    depth = 0
    while parent and depth < 10:
        parts.insert(0, parent)
        parent_node = en_idx.get(parent)
        parent = parent_node.get("parent_item_group", "") if parent_node else ""
        depth += 1
    return " / ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
