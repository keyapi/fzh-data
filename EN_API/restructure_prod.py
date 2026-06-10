# -*- coding: utf-8 -*-
"""按赛狐商品分类重构 EN 生产系统物料组树结构。

使用 Commodities 导出文件中的 SPU -> 分类映射来确定
每个 EN 产品（custom_model_id）应该归属的赛狐分类。

流程:
  1. 读取 Commodities xlsx → (SPU → 分类路径) 映射
  2. 获取 EN 生产系统当前 Item Group
  3. 创建赛狐分类节点（如不存在）
  4. 将 EN 产品节点移动到对应赛狐分类下
  5. 验证

使用:
  python restructure_prod.py --dry-run    # 预览（推荐先执行）
  python restructure_prod.py              # 执行
"""

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

_ENV_URLS = {"prod": "https://erpnext.vilavi.cn"}


# ── HTTP ───────────────────────────────────────────────
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

    def create_item_group(self, data: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/resource/Item Group"
        return self._request("POST", url, json=data).json().get("data", {})

    def update_item_group(self, name: str, fields: dict[str, Any]) -> dict[str, Any]:
        safe = quote(name, safe="")
        url = f"{self.base_url}/api/resource/Item Group/{safe}"
        return self._request("PUT", url, json=fields).json().get("data", {})

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


# ── 工具 ──────────────────────────────────────────────
def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


# ── 读取赛狐商品导出 ─────────────────────────────────
def load_commodities(path: Path) -> tuple[dict[str, str], list[dict]]:
    """读取 Commodities xlsx，返回 (spu->分类路径映射, 分类树节点列表)。"""
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


# ── 映射建立 ─────────────────────────────────────────
def build_moves(
    en_data: list[dict],
    spu_to_cat: dict[str, str],
) -> list[dict]:
    """基于 SPU 映射建立移动清单。"""
    idx = build_index(en_data)
    moves: list[dict] = []

    for en_name, en_node in idx.items():
        mid = str(en_node.get("custom_model_id") or "").strip()
        if not mid or mid == "nan" or mid == "None":
            continue

        cat_path = spu_to_cat.get(mid)
        if not cat_path:
            continue

        current_parent = en_node.get("parent_item_group") or ""
        parts = cat_path.split("/")
        target_parent = parts[-1].strip()

        # 若目标分类名与产品自身名称相同，则上移一级
        if target_parent == en_name and len(parts) > 1:
            target_parent = parts[-2].strip()

        if current_parent == target_parent:
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
    return moves


# ── 分析 ──────────────────────────────────────────────
def en_node_exists(name: str, parent: str, en_data: list[dict]) -> bool:
    name, parent = name.strip(), parent.strip()
    for d in en_data:
        if d.get("item_group_name") == name and (d.get("parent_item_group") or "") == parent:
            return True
    return False


def analyze(
    cat_nodes: list[dict],
    en_data: list[dict],
    moves: list[dict],
) -> dict[str, Any]:
    to_create: list[dict] = []
    for n in sorted(cat_nodes, key=lambda x: (x["level"], x["name"])):
        parent = n["parent"] or "产品"
        if not en_node_exists(n["name"], parent, en_data):
            to_create.append(n)

    total_mapped = len({m["en_name"] for m in moves})

    return {
        "to_create": to_create,
        "moves": moves,
        "_stats": {
            "赛狐分类节点(总)": len(cat_nodes),
            "需创建": len(to_create),
            "EN产品需移动": len(moves),
            "EN产品有映射": total_mapped,
        },
    }


def en_name_exists(name: str, en_data: list[dict]) -> bool:
    name = name.strip()
    for d in en_data:
        if d.get("item_group_name") == name:
            return True
    return False


# ── 执行 ──────────────────────────────────────────────
_OP_LOG: list[dict[str, Any]] = []


def _log_op(op: dict) -> None:
    _OP_LOG.append(op)


def execute(
    client: ErpnextClient,
    analysis: dict[str, Any],
    dry_run: bool = True,
    batch_delay: float = 0.3,
) -> bool:
    ok = True

    creates = analysis["to_create"]
    creates.sort(key=lambda x: (x["level"], x["name"]))
    print(f"\n── 阶段 1: 创建分类节点 ({len(creates)} 个) ──")

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

    moves = analysis["moves"]
    print(f"\n── 阶段 2: 移动产品节点 ({len(moves)} 个) ──")

    for m in moves:
        _log_op({"阶段": "2-移动", "操作": "PUT",
                  "name": m["en_name"],
                  "from": m["current_parent"], "to": m["target_parent"]})
        if not dry_run:
            try:
                fields: dict[str, Any] = {"parent_item_group": m["target_parent"]}
                client.update_item_group(m["en_name"], fields)
                _log_op({**_OP_LOG[-1], "状态": "OK"})
                if len(moves) <= 20 or m is moves[0] or m is moves[-1]:
                    print(f"  [OK] MOVE {m['en_name']}: {m['current_parent']} -> {m['target_parent']}")
                time.sleep(batch_delay * 0.5)
            except requests.RequestException as e:
                body_text = _get_error_body(e)
                if body_text and "不能是一个叶节点" in body_text:
                    try:
                        fields = {"parent_item_group": m["target_parent"], "is_group": 1}
                        client.update_item_group(m["en_name"], fields)
                        _log_op({**_OP_LOG[-1], "状态": "OK (is_group=1)"})
                        print(f"  [OK] MOVE {m['en_name']} (is_group=1): {m['current_parent']} -> {m['target_parent']}")
                        time.sleep(batch_delay * 0.5)
                    except requests.RequestException as e2:
                        _log_op({**_OP_LOG[-1], "状态": f"FAIL: {e2}"})
                        print(f"  [FAIL] MOVE {m['en_name']}: {e2}")
                        ok = False
                else:
                    _log_op({**_OP_LOG[-1], "状态": f"FAIL: {e}"})
                    print(f"  [FAIL] MOVE {m['en_name']}: {e}")
                    ok = False
        else:
            if len(moves) <= 20 or m is moves[0] or m is moves[-1]:
                print(f"  [DRY] MOVE {m['en_name']}({m.get('custom_model_id','')}): {m['current_parent']} -> {m['target_parent']}")

    if not dry_run and len(moves) > 20:
        print(f"  ... 共 {len(moves)} 个移动")

    return ok


# ── 验证 & 报告 ──────────────────────────────────────
def verify(
    client: ErpnextClient,
    cat_nodes: list[dict],
    moves: list[dict],
    out_dir: Path,
) -> dict[str, Any]:
    print("\n── 验证 ──")
    data = client.fetch_all_item_groups()
    idx = build_index(data)

    missing_nodes = []
    for n in cat_nodes:
        if not en_name_exists(n["name"], data):
            missing_nodes.append(n["name"])

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
        "分类节点已创建": len(cat_nodes) - len(missing_nodes),
        "分类节点未创建": len(missing_nodes),
        "产品位置正确": correct,
        "产品位置仍不对": len(still_wrong),
        "状态": "一致" if (not missing_nodes and not still_wrong) else "有差异",
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rpt = out_dir / f"生产系统重构验证_{ts}.xlsx"
    with pd.ExcelWriter(rpt, engine="openpyxl") as writer:
        pd.DataFrame([stats]).to_excel(writer, sheet_name="汇总", index=False)
        if still_wrong:
            sw_rows = [{"名称": s["en_name"], "目标": s["target_parent"], "原因": s.get("原因", "")} for s in still_wrong]
            pd.DataFrame(sw_rows).to_excel(writer, sheet_name="位置不正确", index=False)
        if missing_nodes:
            pd.DataFrame([{"缺失": n} for n in missing_nodes]).to_excel(writer, sheet_name="缺失分类", index=False)

    print(f"验证报告: {rpt}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return stats


def _get_error_body(exc: requests.RequestException) -> str:
    resp = getattr(exc, "response", None)
    if resp is None:
        return ""
    try:
        data = resp.json()
        return data.get("exception", "") or data.get("_server_messages", "")
    except Exception:
        return resp.text


def write_op_report(
    analysis: dict[str, Any],
    log: list[dict],
    verify_stats: dict[str, Any] | None,
    dry_run: bool,
    out_dir: Path,
) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "预览" if dry_run else "执行"
    path = out_dir / f"生产系统重构操作{tag}_{ts}.xlsx"

    stats = analysis["_stats"]
    summary = [{"指标": k, "数值": v} for k, v in stats.items()]
    summary.insert(0, {"指标": "模式", "数值": "DRY-RUN" if dry_run else "执行"})

    log_rows = []
    for op in log:
        log_rows.append({
            "阶段": op.get("阶段", ""),
            "操作": op.get("操作", ""),
            "名称": op.get("name", ""),
            "详情": op.get("parent", "") or op.get("to", ""),
            "状态": op.get("状态", "待执行"),
        })

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(log_rows).to_excel(writer, sheet_name="操作日志", index=False)
        if verify_stats:
            pd.DataFrame([verify_stats]).to_excel(writer, sheet_name="验证结果", index=False)

    return path


# ── 主入口 ─────────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="按赛狐分类重构 EN 生产系统物料组")
    ap.add_argument("--dry-run", action="store_true", help="预览操作，不下发修改")
    ap.add_argument("--batch", type=float, default=0.3, help="请求间隔秒数")
    ap.add_argument("--out-dir", type=Path, default=_DIR_OUT)
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    prod_key = os.getenv("PROD_ERP_API_KEY", "")
    prod_secret = os.getenv("PROD_ERP_API_SECRET", "")
    if not prod_key or not prod_secret:
        print("错误: 请设置 PROD_ERP_API_KEY / PROD_ERP_API_SECRET")
        return 1

    client = ErpnextClient(_ENV_URLS["prod"], prod_key, prod_secret)
    print(f"生产环境: {_ENV_URLS['prod']}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '执行'}")

    # ── 读取 Commodities ──
    xlsx_files = sorted([f for f in _DIR_DATA.iterdir()
                         if f.suffix == ".xlsx" and not f.name.startswith("~$")])
    commod_files = [f for f in xlsx_files if "Commodities" in f.name or "commodities" in f.name]
    if not commod_files:
        print(f"错误: {_DIR_DATA} 下找不到 Commodities .xlsx 文件")
        print(f"  可用文件: {[f.name for f in xlsx_files]}")
        return 1
    commod_path = commod_files[-1]
    print(f"\n赛狐商品文件: {commod_path.name}")

    spu_to_cat, cat_nodes = load_commodities(commod_path)
    print(f"  SPU->分类映射: {len(spu_to_cat)} 条")
    print(f"  分类树节点: {len(cat_nodes)} 个")

    # ── 获取 EN 生产数据 ──
    print("获取生产系统数据...")
    try:
        en_data = client.fetch_all_item_groups()
        print(f"  生产系统: {len(en_data)} 条记录")
    except requests.RequestException as e:
        print(f"错误: {e}")
        return 1

    # ── 建立移动清单 ──
    moves = build_moves(en_data, spu_to_cat)
    print(f"\n  可匹配的产品: {len(moves)} 个")

    idx = build_index(en_data)
    unmatched = []
    for name, node in idx.items():
        mid = str(node.get("custom_model_id") or "").strip()
        if mid and mid not in ("nan", "None", "") and mid not in spu_to_cat:
            unmatched.append(f"{name}({mid})")
    if unmatched:
        print(f"  未匹配产品: {len(unmatched)} 个 (将留在原位)")
        for u in unmatched[:10]:
            print(f"    {u}")
        if len(unmatched) > 10:
            print(f"    ... 共 {len(unmatched)} 个")

    # ── 分析 ──
    analysis = analyze(cat_nodes, en_data, moves)
    print(f"\n── 分析结果 ──")
    for k, v in analysis["_stats"].items():
        print(f"  {k}: {v}")
    if analysis["to_create"]:
        print(f"  需创建的节点: {[n['name'] for n in analysis['to_create']]}")

    # ── 执行 ──
    ok = execute(client, analysis, dry_run=args.dry_run, batch_delay=args.batch)

    # ── 验证 ──
    if not args.dry_run:
        vstats = verify(client, cat_nodes, moves, out_dir)
    else:
        vstats = None

    # ── 报告 ──
    rpt = write_op_report(analysis, _OP_LOG, vstats, args.dry_run, out_dir)
    print(f"\n操作报告: {rpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
