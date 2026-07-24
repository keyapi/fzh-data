# -*- coding: utf-8 -*-
"""按赛狐商品分类重构 EN 生产系统物料组树结构（完整版）。

功能:
  1. 备份生产系统（可选，默认执行）
  2. 读取 Commodities → SPU→分类路径映射
  3. 仅创建非叶子赛狐分类节点（叶子节点不创建）
  4. 将 EN 产品节点移动至正确赛狐分类下
  5. 验证 + 综合报告

使用:
  python restructure_prod_full.py --dry-run      # 预览（推荐先执行）
  python restructure_prod_full.py                 # 备份+执行
  python restructure_prod_full.py --skip-backup   # 跳过备份直接执行
  python restructure_prod_full.py --dry-run --skip-backup  # 仅预览不备份
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

# ── urllib3 全局补丁 — 阻止 nginx 417 Expectation Failed ──
# urllib3 自动为 POST/PUT 添加 Expect: 100-continue，
# nginx/1.18 不支持并返回 417。
# HTTPAdapter 层面的移除会被 urllib3 内部重新添加，
# 因此需要在 urllib3.connectionpool._make_request 层面拦截。
import urllib3
from urllib3.connectionpool import HTTPConnectionPool

_orig_make_request = HTTPConnectionPool._make_request

def _patched_make_request(self, conn, method, url, body=None, headers=None, *args, **kw):
    if headers and "Expect" in headers:
        del headers["Expect"]
    return _orig_make_request(self, conn, method, url, body, headers, *args, **kw)

HTTPConnectionPool._make_request = _patched_make_request

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)
_DIR_DATA = _DIR / "数据源"
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)


# ── .env 加载 ──────────────────────────────────────────
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


# ── HTTP ───────────────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        # urllib3 2.x 内部会重新添加 Expect，必须在发送前从 PreparedRequest 剥离
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.headers.pop("Expect", None)  # 防止 nginx 417
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def fetch_all_item_groups(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/Item Group"
        fields = json.dumps([
            "name", "item_group_name", "parent_item_group", "is_group",
            "image", "custom_model_id",
        ])
        params = {"fields": fields, "limit_page_length": "0"}
        resp = self._request("GET", url, params=params, retries=3, retry_delay=3)
        return resp.json().get("data", [])

    def fetch_all_full(self, fields: list[str] | None = None) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/Item Group"
        params: dict = {"limit_page_length": "0"}
        if fields is not None:
            params["fields"] = json.dumps(fields)
        else:
            params["limit"] = "0"
        resp = self._request("GET", url, params=params, retries=3, retry_delay=3,
                             timeout=(60, 120))
        return resp.json().get("data", [])

    def create_item_group(self, data: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/resource/Item Group"
        return self._request("POST", url, json=data, retries=3,
                             retry_delay=5).json().get("data", {})

    def update_item_group(self, name: str, fields: dict[str, Any]) -> dict[str, Any]:
        safe = quote(name, safe="")
        url = f"{self.base_url}/api/resource/Item Group/{safe}"
        return self._request("PUT", url, json=fields, retries=3,
                             retry_delay=5).json().get("data", {})

    def _request(self, method: str, url: str, *,
                 retries: int = 4, retry_delay: float = 3.0,
                 **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (60, 180))
        last = None
        for a in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last = e
                status = getattr(getattr(e, "response", None), "status_code", 0)
                # 500/502/503/504/417/408: 递增延迟重试
                if status in (500, 502, 503, 504, 417, 408) and a < retries:
                    delay = retry_delay * (a + 1) * 2
                    print(f"    [RETRY {a+1}/{retries}] HTTP {status}, 等待 {delay:.0f}s...")
                    time.sleep(delay)
                # 连接超时/SSL错误等也重试
                elif isinstance(e, (requests.exceptions.ConnectTimeout,
                                     requests.exceptions.ConnectionError,
                                     requests.exceptions.SSLError)):
                    if a < retries:
                        delay = retry_delay * (a + 1)
                        print(f"    [RETRY {a+1}/{retries}] {type(e).__name__}, 等待 {delay:.0f}s...")
                        time.sleep(delay)
                    else:
                        raise
                elif a < retries:
                    time.sleep(retry_delay)
        raise last


# ── 工具 ──────────────────────────────────────────────
def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


# ── 赛狐数据读取 ─────────────────────────────────────
def load_commodities(path: Path) -> tuple[dict[str, str], list[dict]]:
    """读取 Commodities xlsx，返回 (spu->分类路径映射, 分类树节点列表)."""
    df = pd.read_excel(path, sheet_name=0)

    spu_to_cat: dict[str, str] = {}
    for _, row in df.iterrows():
        spu = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""
        cat = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        if spu and cat and spu.lower() != "nan":
            spu_to_cat[spu] = cat

    cat_nodes: dict[str, dict] = {}
    for cat_path in set(spu_to_cat.values()):
        parts = cat_path.split("/")
        for i, p in enumerate(parts):
            name = p.strip()
            parent = parts[i - 1].strip() if i > 0 else ""
            key = f"{parent}|{name}" if parent else name
            if key not in cat_nodes:
                cat_nodes[key] = {"name": name, "parent": parent, "level": i + 1}

    return spu_to_cat, list(cat_nodes.values())


# ── 备份 ───────────────────────────────────────────────
def backup_production(client: ErpnextClient, out_dir: Path) -> dict[str, Any]:
    """全量备份生产系统物料组。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n── 备份生产系统 ──")

    core_fields = [
        "name", "item_group_name", "parent_item_group", "is_group",
        "image", "custom_model_id",
    ]
    data = client.fetch_all_full(core_fields)
    print(f"  物料组总数: {len(data)}")

    extra_field_batches = [
        ["name", "icon", "route", "is_website_route", "slideshow"],
        ["name", "description", "is_attribute_item_group",
         "website_image", "website_banner"],
    ]
    all_field_map: dict[str, dict] = {}
    for batch in extra_field_batches:
        try:
            batch_data = client.fetch_all_full(batch)
            for d in batch_data:
                all_field_map.setdefault(d["name"], {}).update(d)
        except requests.RequestException:
            pass
    print(f"  扩展字段: {len(all_field_map)} 条")

    merged = []
    for d in data:
        full = all_field_map.get(d["name"], {})
        merged.append({**full, **d})

    backup = {
        "metadata": {
            "backup_time": datetime.now().isoformat(),
            "environment": "生产系统",
            "total_count": len(merged),
            "fields_included": list(merged[0].keys()) if merged else [],
            "description": "EN 生产系统物料组全量备份（重构前）",
        },
        "records": merged,
    }
    backup_file = out_dir / f"生产系统备份_全量_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(backup_file) / 1024
    print(f"  备份文件: {backup_file.name} ({size_kb:.0f} KB)")

    # 归档
    archive_dir = out_dir / "备份归档"
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_file, archive_dir / backup_file.name)

    return {
        "backup_file": backup_file,
        "total": len(merged),
        "data": merged,
        "timestamp": ts,
        "all_fields": list(merged[0].keys()) if merged else [],
    }


# ── 映射建立 ─────────────────────────────────────────
def build_moves(
    en_data: list[dict],
    spu_to_cat: dict[str, str],
    en_idx: dict[str, dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """基于 SPU 映射建立移动清单。

    返回 (moves, leaf_skipped):
    - moves: 待执行的移动清单
    - leaf_skipped: 因源节点是叶子(is_group=0)而跳过的移动（需用户确认）
    """
    if en_idx is None:
        en_idx = build_index(en_data)
    moves: list[dict] = []
    leaf_skipped: list[dict] = []

    for en_name, en_node in en_idx.items():
        mid = str(en_node.get("custom_model_id") or "").strip()
        if not mid or mid == "nan" or mid == "None":
            continue

        cat_path = spu_to_cat.get(mid)
        if not cat_path:
            continue

        current_parent = en_node.get("parent_item_group") or ""
        parts = cat_path.split("/")
        target_parent = parts[-1].strip()

        # 若目标分类名与产品自身名称相同，上移一级避免自引用
        if target_parent == en_name and len(parts) > 1:
            target_parent = parts[-2].strip()

        # 跳过已在正确位置的产品
        if current_parent == target_parent:
            continue

        # ⚠ 叶子节点(is_group=0)不做移动，需用户确认
        if en_node.get("is_group") == 0:
            leaf_skipped.append({
                "en_name": en_name,
                "en_group_name": en_node.get("item_group_name", ""),
                "custom_model_id": mid,
                "current_parent": current_parent,
                "target_parent": target_parent,
                "target_path": cat_path,
            })
            continue

        moves.append({
            "en_name": en_name,
            "en_group_name": en_node.get("item_group_name", ""),
            "custom_model_id": mid,
            "current_parent": current_parent,
            "target_parent": target_parent,
            "target_path": cat_path,
        })

    moves.sort(key=lambda x: (x["target_path"], x["en_name"]))
    return moves, leaf_skipped


# ── 分析 ──────────────────────────────────────────────
def en_node_exists(name: str, parent: str, en_data: list[dict]) -> bool:
    name, parent = name.strip(), parent.strip()
    for d in en_data:
        if d.get("item_group_name") == name and (d.get("parent_item_group") or "") == parent:
            return True
    return False


def en_name_exists(name: str, en_data: list[dict]) -> bool:
    name = name.strip()
    for d in en_data:
        if d.get("item_group_name") == name:
            return True
    return False


def analyze(
    cat_nodes: list[dict],
    en_data: list[dict],
    moves: list[dict],
) -> dict[str, Any]:
    """生成操作清单。

    对每个赛狐分类节点检查其在 EN 系统中的状态：
    - 若已存在且是组(is_group=1)：跳过
    - 若已存在且是叶子(is_group=0)：标记为 leaf_warning，用户需确认
    - 若不存在：加入 to_create
    """
    en_by_name: dict[str, dict] = {}
    for d in en_data:
        g = d.get("item_group_name", "")
        if g:
            en_by_name[g] = d

    to_create: list[dict] = []
    leaf_warning: list[dict] = []

    for n in sorted(cat_nodes, key=lambda x: (x["level"], x["name"])):
        name = n["name"]
        parent = n["parent"] or "产品"

        existing = en_by_name.get(name)
        if existing is not None:
            # 节点已存在 — 检查是否是叶子
            is_grp = existing.get("is_group", 0)
            if is_grp == 0:
                leaf_warning.append({
                    "name": name,
                    "parent": existing.get("parent_item_group", ""),
                    "desired_parent": parent,
                })
            # 已存在(is_group=0 或 1)都不创建
            continue

        if not en_node_exists(name, parent, en_data):
            to_create.append(n)

    total_mapped = len({m["en_name"] for m in moves})

    return {
        "to_create": to_create,
        "leaf_warning": leaf_warning,
        "moves": moves,
        "_stats": {
            "赛狐分类节点(总)": len(cat_nodes),
            "需创建": len(to_create),
            "已有叶子节点(需确认)": len(leaf_warning),
            "EN产品需移动": len(moves),
            "EN产品有映射": total_mapped,
        },
    }


# ── 执行 ──────────────────────────────────────────────
_OP_LOG: list[dict[str, Any]] = []


def _log_op(op: dict) -> None:
    _OP_LOG.append(op)


def _get_error_body(exc: requests.RequestException) -> str:
    resp = getattr(exc, "response", None)
    if resp is None:
        return ""
    try:
        data = resp.json()
        return data.get("exception", "") or data.get("_server_messages", "")
    except Exception:
        return resp.text


def execute(
    client: ErpnextClient,
    analysis: dict[str, Any],
    dry_run: bool = True,
    batch_delay: float = 0.3,
) -> bool:
    ok = True

    # ── 1. 创建赛狐分类节点（仅非叶子） ──
    creates = analysis["to_create"]
    creates.sort(key=lambda x: (x["level"], x["name"]))
    print(f"\n── 阶段1: 创建分类节点 ({len(creates)} 个) ──")
    for n in creates:
        parent = n["parent"] or "产品"
        _log_op({"阶段": "1-创建分类", "操作": "POST",
                  "name": n["name"], "parent": parent, "level": n["level"]})
        if not dry_run:
            try:
                client.create_item_group({
                    "item_group_name": n["name"],
                    "parent_item_group": parent,
                    "is_group": 1,
                })
                _log_op({**_OP_LOG[-1], "状态": "OK"})
                print(f"  [OK] POST {n['name']} (parent={parent})")
                time.sleep(batch_delay)
            except requests.RequestException as e:
                _log_op({**_OP_LOG[-1], "状态": f"FAIL: {e}"})
                print(f"  [FAIL] POST {n['name']}: {e}")
                ok = False
        else:
            print(f"  [DRY] POST {n['name']} (parent={parent})")

    # ── 2. 移动节点 ──
    moves = analysis["moves"]
    print(f"\n── 阶段2: 移动产品节点 ({len(moves)} 个) ──")
    success_count = 0
    fail_count = 0
    for i, m in enumerate(moves):
        _log_op({"阶段": "2-移动", "操作": "PUT",
                  "name": m["en_name"],
                  "from": m["current_parent"], "to": m["target_parent"]})
        if not dry_run:
            try:
                fields: dict[str, Any] = {"parent_item_group": m["target_parent"]}
                client.update_item_group(m["en_name"], fields)
                _log_op({**_OP_LOG[-1], "状态": "OK"})
                success_count += 1
                if len(moves) <= 30 or i < 3 or i >= len(moves) - 3:
                    print(f"  [OK] MOVE {m['en_name']}: {m['current_parent']} -> {m['target_parent']}")
                time.sleep(batch_delay * 0.5)
            except requests.RequestException as e:
                body_text = _get_error_body(e)
                if body_text and "不能是一个叶节点" in body_text:
                    try:
                        fields = {"parent_item_group": m["target_parent"], "is_group": 1}
                        client.update_item_group(m["en_name"], fields)
                        _log_op({**_OP_LOG[-1], "状态": "OK (is_group=1)"})
                        success_count += 1
                        print(f"  [OK] MOVE {m['en_name']} (is_group=1): {m['current_parent']} -> {m['target_parent']}")
                        time.sleep(batch_delay * 0.5)
                    except requests.RequestException as e2:
                        _log_op({**_OP_LOG[-1], "状态": f"FAIL: {e2}"})
                        fail_count += 1
                        print(f"  [FAIL] MOVE {m['en_name']}: {e2}")
                        ok = False
                else:
                    _log_op({**_OP_LOG[-1], "状态": f"FAIL: {e}"})
                    fail_count += 1
                    print(f"  [FAIL] MOVE {m['en_name']}: {e}")
                    ok = False
        else:
            if len(moves) <= 30 or i < 3 or i >= len(moves) - 3:
                print(f"  [DRY] MOVE {m['en_name']}({m.get('custom_model_id','')}): {m['current_parent']} -> {m['target_parent']}")

    if not dry_run:
        print(f"  移动结果: 成功={success_count}, 失败={fail_count}")
    elif len(moves) > 30:
        print(f"  ... 共 {len(moves)} 个移动 (DRY-RUN 仅显示首尾)")

    return ok


# ── 验证 ──────────────────────────────────────────────
def verify(
    client: ErpnextClient,
    cat_nodes: list[dict],
    moves: list[dict],
    out_dir: Path,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    print("\n── 验证 ──")
    try:
        data = client.fetch_all_item_groups()
    except requests.RequestException as e:
        print(f"  验证获取数据失败: {e}")
        return {"状态": "验证失败", "错误": str(e)}
    idx = build_index(data)

    # 赛狐非叶子节点是否存在
    missing_nodes = []
    created_nodes = analysis["to_create"] if analysis else []
    for n in created_nodes:
        if not en_name_exists(n["name"], data):
            missing_nodes.append(n["name"])

    # 产品是否在正确位置
    still_wrong = []
    correct = 0
    for m in moves:
        d = idx.get(m["en_name"])
        if d is None:
            still_wrong.append({**m, "原因": "节点不存在"})
            continue
        curr = d.get("parent_item_group") or ""
        if curr == m["target_parent"]:
            correct += 1
        else:
            still_wrong.append({**m, "原因": f"当前在: {curr}"})

    stats = {
        "生产系统节点数": len(data),
        "应创建节点": len(created_nodes),
        "已成功创建": len(created_nodes) - len(missing_nodes),
        "创建失败": len(missing_nodes),
        "产品位置正确": correct,
        "产品位置仍不对": len(still_wrong),
        "状态": "一致" if (not missing_nodes and not still_wrong) else "有差异",
    }

    print(f"  总节点: {len(data)}")
    print(f"  创建: {stats['已成功创建']}/{len(created_nodes)}")
    print(f"  移动正确: {correct}/{len(moves)}")
    if still_wrong:
        print(f"  仍不对: {len(still_wrong)} 个")
        for s in still_wrong[:5]:
            print(f"    {s['en_name']}: {s.get('原因','')}")
    if missing_nodes:
        print(f"  创建失败: {missing_nodes}")

    return stats


# ── 报告 ──────────────────────────────────────────────
def write_comprehensive_report(
    backup_result: dict[str, Any] | None,
    analysis: dict[str, Any],
    log: list[dict],
    verify_stats: dict[str, Any] | None,
    dry_run: bool,
    out_dir: Path,
    env_label: str = "生产系统",
) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "预览" if dry_run else "执行"
    path = out_dir / f"物料组重构{tag}_{ts}.xlsx"

    stats = analysis["_stats"]

    # ── 执行摘要 ──
    summary_rows = [
        {"指标": "模式", "数值": "DRY-RUN" if dry_run else "执行"},
        {"指标": "环境", "数值": env_label},
        {"指标": "数据源", "数值": "Commodities 赛狐导出"},
        {"指标": "赛狐分类节点(总)", "数值": stats.get("赛狐分类节点(总)", "")},
        {"指标": "需创建", "数值": stats.get("需创建", "")},
        {"指标": "EN产品需移动", "数值": stats.get("EN产品需移动", "")},
        {"指标": "EN产品有映射", "数值": stats.get("EN产品有映射", "")},
        {"指标": "报告生成时间", "数值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ]
    if not dry_run:
        summary_rows.insert(0, {"指标": "备份文件", "数值": backup_result["backup_file"].name if backup_result else "无"})

    # ── 赛狐结构 ──
    cat_rows = []
    for n in sorted(analysis["to_create"], key=lambda x: (x["level"], x["name"])):
        cat_rows.append({
            "层级": n.get("level", ""),
            "名称": n["name"],
            "父级": n.get("parent", ""),
            "操作": "创建",
        })

    # ── 操作日志 ──
    log_rows = []
    for op in log:
        log_rows.append({
            "阶段": op.get("阶段", ""),
            "操作": op.get("操作", ""),
            "名称": op.get("name", ""),
            "详情": op.get("parent", "") or op.get("to", "") or op.get("from", ""),
            "状态": op.get("状态", "待执行"),
        })

    # ── 移动清单 ──
    move_rows = []
    for m in analysis["moves"]:
        move_rows.append({
            "产品名称": m.get("en_name", ""),
            "产品组名": m.get("en_group_name", ""),
            "SPU": m.get("custom_model_id", ""),
            "当前父级": m.get("current_parent", ""),
            "目标父级": m.get("target_parent", ""),
            "赛狐路径": m.get("target_path", ""),
        })

    # ── 验证结果 ──
    verify_rows = []
    if verify_stats:
        for k, v in verify_stats.items():
            verify_rows.append({"指标": k, "数值": v})

    # ── 错误记录 ──
    error_rows = []
    for op in log:
        status = op.get("状态", "")
        if status and status not in ("OK", "待执行", "OK (is_group=1)"):
            error_rows.append({
                "阶段": op.get("阶段", ""),
                "操作": op.get("操作", ""),
                "名称": op.get("name", ""),
                "错误": status,
            })

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="执行摘要", index=False)
        pd.DataFrame(cat_rows).to_excel(writer, sheet_name="赛狐结构", index=False)
        pd.DataFrame(log_rows).to_excel(writer, sheet_name="操作日志", index=False)
        pd.DataFrame(move_rows).to_excel(writer, sheet_name="移动清单", index=False)
        if verify_rows:
            pd.DataFrame(verify_rows).to_excel(writer, sheet_name="验证结果", index=False)
        if error_rows:
            pd.DataFrame(error_rows).to_excel(writer, sheet_name="错误记录", index=False)

    print(f"\n综合报告: {path}")
    return path


# ── 主入口 ─────────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="按赛狐分类重构 EN 物料组树结构")
    ap.add_argument("--env", choices=["prod", "test"], default="prod", help="目标环境")
    ap.add_argument("--dry-run", action="store_true", help="预览操作，不下发修改")
    ap.add_argument("--skip-backup", action="store_true", help="跳过备份（仅执行模式）")
    ap.add_argument("--batch", type=float, default=0.3, help="请求间隔秒数")
    ap.add_argument("--out-dir", type=Path, default=_DIR_OUT)
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    _ENVS = {
        "prod": {"url": "https://erpnext.vilavi.cn", "key": "PROD_ERP_API_KEY", "sec": "PROD_ERP_API_SECRET", "label": "生产系统"},
        "test": {"url": "https://ensh.vilavi.cn", "key": "TEST_ERP_API_KEY", "sec": "TEST_ERP_API_SECRET", "label": "测试系统"},
    }
    env_info = _ENVS[args.env]
    api_key = os.getenv(env_info["key"], "")
    api_secret = os.getenv(env_info["sec"], "")
    if not api_key or not api_secret:
        print(f"错误: 请设置 {env_info['key']} / {env_info['sec']}")
        return 1

    client = ErpnextClient(env_info["url"], api_key, api_secret)
    print(f"{env_info['label']}: {env_info['url']}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '执行'}")

    # ── 备份 ──
    backup_result = None
    if not args.dry_run and not args.skip_backup:
        backup_result = backup_production(client, out_dir)

    # ── 读取 Commodities ──
    xlsx_files = sorted([f for f in _DIR_DATA.iterdir()
                         if f.suffix == ".xlsx" and not f.name.startswith("~$")])
    commod_files = [f for f in xlsx_files if "Commodities" in f.name or "commodities" in f.name]
    if not commod_files:
        print(f"错误: {_DIR_DATA} 下找不到 Commodities .xlsx 文件")
        print(f"  可用文件: {[f.name for f in xlsx_files]}")
        return 1
    # 优先使用重构版（若存在），否则用最新的原版
    refactored = [f for f in commod_files if "重构版" in f.name]
    commod_path = refactored[-1] if refactored else commod_files[-1]
    print(f"\n赛狐商品文件: {commod_path.name}")

    spu_to_cat, cat_nodes = load_commodities(commod_path)
    print(f"  SPU->分类映射: {len(spu_to_cat)} 条")
    print(f"  分类树节点: {len(cat_nodes)} 个")

    # ── 获取 EN 数据 ──
    print(f"\n获取{env_info['label']}数据...")
    try:
        en_data = client.fetch_all_item_groups()
        print(f"  {env_info['label']}: {len(en_data)} 条记录")
    except requests.RequestException as e:
        print(f"错误: {e}")
        return 1

    # ── 建立移动清单 ──
    en_idx = build_index(en_data)
    moves, leaf_skipped = build_moves(en_data, spu_to_cat, en_idx)
    print(f"\n  可匹配的产品: {len(moves)} 个")
    if leaf_skipped:
        print(f"  ⚠ 其中 {len(leaf_skipped)} 个是叶子节点(is_group=0)，已跳过（需用户确认）：")
        for ls in leaf_skipped[:5]:
            print(f"      {ls['en_name']}: {ls['current_parent']} -> {ls['target_parent']}")
        if len(leaf_skipped) > 5:
            print(f"      ... 共 {len(leaf_skipped)} 个")

    # 未匹配的 EN 产品
    unmatched = []
    for name, node in en_idx.items():
        mid = str(node.get("custom_model_id") or "").strip()
        if mid and mid not in ("nan", "None", "") and mid not in spu_to_cat:
            unmatched.append(f"{name}({mid})")
    if unmatched:
        print(f"  未匹配产品: {len(unmatched)} 个 (将留在原位)")

    # ── 分析 ──
    analysis = analyze(cat_nodes, en_data, moves)
    print(f"\n── 分析结果 ──")
    for k, v in analysis["_stats"].items():
        print(f"  {k}: {v}")
    if analysis["to_create"]:
        print(f"  将创建的节点: {[n['name'] for n in analysis['to_create']]}")
    lw = analysis.get("leaf_warning", [])
    if lw:
        print(f"\n  ⚠ 以下节点在 EN 中已存在且是叶子节点(is_group=0)")
        print(f"     脚本不会自动处理它们。如需调整，请联系用户确认：")
        for n in lw:
            print(f"      - {n['name']} (当前parent={n['parent']}, 目标parent={n['desired_parent']})")

    # ── 执行 ──
    ok = execute(client, analysis, dry_run=args.dry_run, batch_delay=args.batch)

    # ── 验证 ──
    if not args.dry_run:
        vstats = verify(client, cat_nodes, moves, out_dir, analysis)
    else:
        vstats = None

    # ── 报告 ──
    rpt = write_comprehensive_report(backup_result, analysis, _OP_LOG, vstats,
                                      args.dry_run, out_dir, env_info["label"])
    print(f"\n[{'OK' if ok else '有错误'}] 完成！")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
