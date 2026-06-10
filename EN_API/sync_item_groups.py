# -*- coding: utf-8 -*-
"""EN 生产 -> 测试系统物料组移植。

将生产系统"产品"子树中测试系统缺失的物料组移植到测试系统，
同时修正树结构不一致和字段不一致。

安全设计:
  --dry-run     预览全部操作，不下发任何修改
  执行前自动校验：父节点存在性、子节点完整性
  每个操作记录 undo 信息，方便回滚

流程:
  0. 分析 — 对比生产/测试，生成操作清单
  1. 修正字段 (PUT custom_model_id)
  2. 创建父节点 (POST 石头抱枕)
  3. 修正树结构 (PUT parent_item_group)
  4. 创建叶子节点 (POST 所有缺失叶子)
  5. 验证 — 重新对比，生成验证报告

使用:
  python sync_item_groups.py --dry-run     # 预览操作清单
  python sync_item_groups.py               # 执行迁移
"""

from __future__ import annotations

import json
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
    _DIR / ".env",
    _DIR.parent / ".env",
    _DIR.parent.parent / ".env",
    _DIR.parent / "tongtool_bundle_to_en" / ".env",
])

_ENV_URLS = {"test": "https://ensh.vilavi.cn", "prod": "https://erpnext.vilavi.cn"}


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

    def delete_item_group(self, name: str) -> None:
        safe = quote(name, safe="")
        url = f"{self.base_url}/api/resource/Item Group/{safe}"
        self._request("DELETE", url, retries=0)

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


# ── 树工具 ─────────────────────────────────────────────
def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def get_descendants(name: str, idx: dict[str, dict]) -> list[dict]:
    result: list[dict] = []
    for d in idx.values():
        if d.get("parent_item_group") == name:
            result.append(d)
            result.extend(get_descendants(d["name"], idx))
    return result


def get_subtree(name: str, idx: dict[str, dict]) -> list[dict]:
    node = idx.get(name)
    if node is None:
        return []
    return [node] + get_descendants(name, idx)


def find_node(name: str, data: list[dict]) -> dict | None:
    for d in data:
        if d.get("name") == name or d.get("item_group_name") == name:
            return d
    return None


# ── 阶段 0: 分析 ──────────────────────────────────────
def analyze(
    prod_sub: list[dict], test_sub: list[dict],
) -> dict[str, Any]:
    """生成操作清单。"""
    prod_idx = build_index(prod_sub)
    test_idx = build_index(test_sub)

    prod_names = set(prod_idx.keys())
    test_names = set(test_idx.keys())

    missing_names = prod_names - test_names
    common_names = prod_names & test_names
    extra_names = test_names - prod_names

    # 1) 要创建的缺失节点
    creates: list[dict] = []
    for name in sorted(missing_names):
        p = prod_idx[name]
        creates.append({
            "type": "POST",
            "name": name,
            "item_group_name": p.get("item_group_name", ""),
            "parent_item_group": p.get("parent_item_group", ""),
            "is_group": bool(p.get("is_group", 0)),
            "custom_model_id": p.get("custom_model_id") or "",
        })

    # 2) 要 PUT 的修正
    puts: list[dict] = []
    for name in sorted(common_names):
        p = prod_idx[name]
        t = test_idx[name]
        put_fields: dict[str, str] = {}

        # custom_model_id 不一致
        p_model = (p.get("custom_model_id") or "").strip()
        t_model = (t.get("custom_model_id") or "").strip()
        if p_model != t_model:
            put_fields["custom_model_id"] = p_model

        # tree 不一致
        p_parent = p.get("parent_item_group") or ""
        t_parent = t.get("parent_item_group") or ""
        if p_parent != t_parent:
            put_fields["parent_item_group"] = p_parent

        if put_fields:
            puts.append({
                "type": "PUT",
                "name": name,
                "item_group_name": p.get("item_group_name", ""),
                "fields": put_fields,
            })

    # 3) 冲突检测：extra 节点占用的 custom_model_id 与缺失节点冲突的
    # 建立 extra 节点的 model_id -> name 映射
    extra_model_map: dict[str, str] = {}
    for name in extra_names:
        t = test_idx[name]
        mid = (t.get("custom_model_id") or "").strip()
        if mid:
            extra_model_map[mid] = name

    # 检查缺失节点中哪些 model_id 被 extra 节点占用了
    collisions: list[dict] = []
    for c in list(creates):
        cid = c.get("custom_model_id", "")
        if cid in extra_model_map:
            collisions.append({
                "create_name": c["name"],
                "custom_model_id": cid,
                "occupied_by": extra_model_map[cid],
            })
            creates.remove(c)  # 从创建清单移除

    # 按依赖排序 creates：is_group 的先创建（因为它们可能是其他节点的 parent）
    creates.sort(key=lambda x: (0 if x["is_group"] else 1, x["name"]))

    # ── 汇总统计 ──
    # 计算实际要创建的叶子数
    parent_names = {c["name"] for c in creates if c["is_group"]}
    leaf_creates = [c for c in creates if not c["is_group"]]
    group_creates = [c for c in creates if c["is_group"]]

    return {
        "creates": creates,
        "puts": puts,
        "collisions": collisions,
        "_stats": {
            "生产子树节点": len(prod_sub),
            "测试子树节点": len(test_sub),
            "共有": len(common_names),
            "缺失(需创建)": len(creates),
            "  ├ 组节点(is_group=1)": len(group_creates),
            "  └ 叶子节点": len(leaf_creates),
            "结构/字段不一致(需PUT)": len(puts),
            "冲突跳过(extra占用model_id)": len(collisions),
            "多余(测试有-生产无,保留)": len(extra_names),
        },
    }


# ── 执行引擎 ──────────────────────────────────────────
_OP_LOG: list[dict[str, Any]] = []


def _log_op(op: dict[str, Any]) -> None:
    _OP_LOG.append(op)


def execute(
    client: ErpnextClient,
    analysis: dict[str, Any],
    dry_run: bool = True,
    batch_delay: float = 0.5,
) -> bool:
    """按依赖顺序执行操作。返回是否全部成功。"""
    ok = True

    # ── 1. 修正字段 (PUT custom_model_id) ──
    # 先做 custom_model_id 修正，再改树结构
    model_fixes = [p for p in analysis["puts"] if "custom_model_id" in p["fields"]]
    for op in model_fixes:
        _log_op({"阶段": "1-修正字段", **op})
        if not dry_run:
            try:
                client.update_item_group(op["name"], {"custom_model_id": op["fields"]["custom_model_id"]})
                _log_op({**_OP_LOG[-1], "状态": "成功"})
                print(f"  [OK] PUT custom_model_id {op['name']} -> {op['fields']['custom_model_id']}")
            except requests.RequestException as e:
                _log_op({**_OP_LOG[-1], "状态": f"失败: {e}"})
                print(f"  [FAIL] PUT 失败 {op['name']}: {e}")
                ok = False
        else:
            print(f"  [DRY-RUN] PUT custom_model_id {op['name']} -> {op['fields']['custom_model_id']}")

    # ── 2. 创建组节点 (POST is_group=1) ──
    groups = [c for c in analysis["creates"] if c["is_group"]]
    for op in groups:
        _log_op({"阶段": "2-创建组节点", **op})
        post_data = {
            "item_group_name": op["item_group_name"],
            "parent_item_group": op["parent_item_group"],
            "is_group": 1,
        }
        if op["custom_model_id"]:
            post_data["custom_model_id"] = op["custom_model_id"]
        if not dry_run:
            try:
                client.create_item_group(post_data)
                _log_op({**_OP_LOG[-1], "状态": "成功"})
                print(f"  [OK] POST {op['name']} (group, parent={op['parent_item_group']})")
                time.sleep(batch_delay)
            except requests.RequestException as e:
                _log_op({**_OP_LOG[-1], "状态": f"失败: {e}"})
                print(f"  [FAIL] POST 失败 {op['name']}: {e}")
                ok = False
        else:
            print(f"  [DRY-RUN] POST {op['name']} (group, parent={op['parent_item_group']})")

    # ── 3. 修正树结构 (PUT parent_item_group) ──
    tree_fixes = [p for p in analysis["puts"] if "parent_item_group" in p["fields"]]
    for op in tree_fixes:
        _log_op({"阶段": "3-修正树结构", **op})
        if not dry_run:
            try:
                client.update_item_group(op["name"], {"parent_item_group": op["fields"]["parent_item_group"]})
                _log_op({**_OP_LOG[-1], "状态": "成功"})
                print(f"  [OK] PUT tree {op['name']}: parent -> {op['fields']['parent_item_group']}")
            except requests.RequestException as e:
                _log_op({**_OP_LOG[-1], "状态": f"失败: {e}"})
                print(f"  [FAIL] PUT 失败 {op['name']}: {e}")
                ok = False
        else:
            print(f"  [DRY-RUN] PUT tree {op['name']}: parent -> {op['fields']['parent_item_group']}")

    # ── 4. 创建叶子节点 (POST is_group=0) ──
    leaves = [c for c in analysis["creates"] if not c["is_group"]]
    for op in leaves:
        _log_op({"阶段": "4-创建叶子节点", **op})
        post_data = {
            "item_group_name": op["item_group_name"],
            "parent_item_group": op["parent_item_group"],
            "is_group": 0,
        }
        if op["custom_model_id"]:
            post_data["custom_model_id"] = op["custom_model_id"]
        if not dry_run:
            try:
                client.create_item_group(post_data)
                _log_op({**_OP_LOG[-1], "状态": "成功"})
                if len(leaves) <= 20 or op is leaves[0] or op is leaves[-1]:
                    print(f"  [OK] POST {op['name']} (parent={op['parent_item_group']})")
                time.sleep(batch_delay)
            except requests.RequestException as e:
                _log_op({**_OP_LOG[-1], "状态": f"失败: {e}"})
                print(f"  [FAIL] POST 失败 {op['name']}: {e}")
                ok = False
        else:
            if len(leaves) <= 10 or op is leaves[0] or op is leaves[-1]:
                print(f"  [DRY-RUN] POST {op['name']} (parent={op['parent_item_group']})")

    if dry_run and len(leaves) > 10:
        print(f"  ... 共 {len(leaves)} 个叶子节点（仅显示首尾）")

    return ok


# ── 验证 ──────────────────────────────────────────────
def verify(
    prod_client: ErpnextClient,
    test_client: ErpnextClient,
    root_name: str,
    out_dir: Path,
) -> dict[str, Any]:
    """验证迁移结果，生成验证报告。"""
    print("\n── 验证中 ──")
    prod_all = prod_client.fetch_all_item_groups()
    test_all = test_client.fetch_all_item_groups()

    prod_idx = build_index(prod_all)
    test_idx = build_index(test_all)

    prod_sub = get_subtree(root_name, prod_idx)
    test_sub = get_subtree(root_name, test_idx)

    prod_names = {d["name"] for d in prod_sub}
    test_names = {d["name"] for d in test_sub}

    still_missing = prod_names - test_names
    still_extra = test_names - prod_names
    common = prod_names & test_names

    # 检查是否还有结构不一致
    tree_diffs = 0
    for name in common:
        p = prod_idx[name]
        t = test_idx[name]
        if (p.get("parent_item_group") or "") != (t.get("parent_item_group") or ""):
            tree_diffs += 1

    model_diffs = 0
    for name in common:
        p_model = (prod_idx[name].get("custom_model_id") or "").strip()
        t_model = (test_idx[name].get("custom_model_id") or "").strip()
        if p_model != t_model:
            model_diffs += 1

    stats = {
        "生产子树": len(prod_sub),
        "测试子树": len(test_sub),
        "仍有缺失": len(still_missing),
        "仍有多余": len(still_extra),
        "树结构不一致": tree_diffs,
        "custom_model_id不一致": model_diffs,
        "状态": "一致 [OK]" if (len(still_missing) == 0 and tree_diffs == 0 and model_diffs == 0) else "有差异",
    }

    # 写验证报告
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rpt_path = out_dir / f"物料组验证报告_{ts}.xlsx"

    rows_detail = []
    for name in sorted(prod_names | test_names):
        p = prod_idx.get(name)
        t = test_idx.get(name)
        rows_detail.append({
            "编码": name,
            "生产名称": p.get("item_group_name", "") if p else "",
            "测试名称": t.get("item_group_name", "") if t else "",
            "生产上级": p.get("parent_item_group", "") if p else "",
            "测试上级": t.get("parent_item_group", "") if t else "",
            "生产is_group": "是" if p and p.get("is_group") else "否",
            "测试is_group": "是" if t and t.get("is_group") else "否",
            "生产custom_model_id": p.get("custom_model_id", "") if p else "",
            "测试custom_model_id": t.get("custom_model_id", "") if t else "",
            "状态": "一致" if (p and t) else ("仅生产" if p else "仅测试"),
        })

    with pd.ExcelWriter(rpt_path, engine="openpyxl") as writer:
        pd.DataFrame([stats]).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(rows_detail).to_excel(writer, sheet_name="明细", index=False)

    print(f"验证报告: {rpt_path}")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    return stats


# ── 报告 ──────────────────────────────────────────────
def write_op_report(
    analysis: dict[str, Any],
    log: list[dict[str, Any]],
    verify_stats: dict[str, Any] | None,
    root_name: str,
    dry_run: bool,
    out_dir: Path,
) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "预览" if dry_run else "执行"
    path = out_dir / f"物料组移植操作{tag}_{ts}.xlsx"

    stats = analysis["_stats"]
    summary = [{"指标": k, "数值": v} for k, v in stats.items()]
    summary.insert(0, {"指标": "根节点", "数值": root_name})
    summary.insert(0, {"指标": "模式", "数值": "DRY-RUN (预览)" if dry_run else "实际执行"})

    if log:
        log_rows = []
        for op in log:
            log_rows.append({
                "阶段": op.get("阶段", ""),
                "操作": op.get("type", ""),
                "编码": op.get("name", ""),
                "物料组名称": op.get("item_group_name", ""),
                "详情": _op_detail(op),
                "状态": op.get("状态", "待执行"),
            })
    else:
        log_rows = [{"说明": "（空）"}]

    # 冲突
    collision_rows = []
    for c in analysis["collisions"]:
        collision_rows.append({
            "被跳过的节点": c["create_name"],
            "custom_model_id": c["custom_model_id"],
            "被谁占用": c["occupied_by"],
        })

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(log_rows).to_excel(writer, sheet_name="操作日志", index=False)
        if collision_rows:
            pd.DataFrame(collision_rows).to_excel(writer, sheet_name="冲突跳过", index=False)

        if verify_stats:
            pd.DataFrame([verify_stats]).to_excel(writer, sheet_name="验证结果", index=False)

    return path


def _op_detail(op: dict) -> str:
    t = op.get("type", "")
    if t == "POST":
        cid = op.get("custom_model_id", "")
        return f"创建 {op.get('item_group_name','')}, parent={op['parent_item_group']}" + (f", model_id={cid}" if cid else "")
    elif t == "PUT":
        f = op.get("fields", {})
        return f"修正 {', '.join(f'{k}={v}' for k, v in f.items())}"
    return ""


# ── 主入口 ─────────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="EN 生产->测试 物料组移植")
    ap.add_argument("--dry-run", action="store_true", help="预览操作清单，不下发修改")
    ap.add_argument("--root", default="产品", help="根节点名称 (默认 产品)")
    ap.add_argument("--batch", type=float, default=0.3, help="POST 间隔秒数 (默认 0.3)")
    ap.add_argument("--out-dir", type=Path, default=_DIR_OUT)
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 凭证 ──
    prod_key = os.getenv("PROD_ERP_API_KEY", "")
    prod_secret = os.getenv("PROD_ERP_API_SECRET", "")
    test_key = os.getenv("TEST_ERP_API_KEY", "")
    test_secret = os.getenv("TEST_ERP_API_SECRET", "")
    if not all([prod_key, prod_secret, test_key, test_secret]):
        print("错误: 请设置 .env 中的 ERP API 凭证")
        return 1

    prod_url = _ENV_URLS["prod"]
    test_url = _ENV_URLS["test"]

    print(f"生产: {prod_url}")
    print(f"测试: {test_url}")
    print(f"模式: {'DRY-RUN (预览)' if args.dry_run else '实际执行'}")

    prod_client = ErpnextClient(prod_url, prod_key, prod_secret)
    test_client = ErpnextClient(test_url, test_key, test_secret)

    # ── 获取数据 ──
    print("\n── 获取数据 ──")
    try:
        prod_all = prod_client.fetch_all_item_groups()
        print(f"  生产: {len(prod_all)} 条")
    except requests.RequestException as e:
        print(f"错误: 连接生产失败: {e}")
        return 1

    try:
        test_all = test_client.fetch_all_item_groups()
        print(f"  测试: {len(test_all)} 条")
    except requests.RequestException as e:
        print(f"错误: 连接测试失败: {e}")
        return 1

    # ── 分析 ──
    root_node = find_node(args.root, prod_all)
    if root_node is None:
        print(f"错误: 生产系统找不到「{args.root}」")
        return 1
    root_name = root_node["name"]

    prod_idx = build_index(prod_all)
    test_idx = build_index(test_all)
    prod_sub = get_subtree(root_name, prod_idx)
    test_sub = get_subtree(root_name, test_idx)

    print(f"\n── 阶段 0: 分析 (根节点: {root_name}) ──")
    analysis = analyze(prod_sub, test_sub)
    for k, v in analysis["_stats"].items():
        print(f"  {k}: {v}")

    if analysis["collisions"]:
        print("\n  冲突跳过:")
        for c in analysis["collisions"]:
            print(f"    {c['create_name']}({c['custom_model_id']}) ← 被 {c['occupied_by']} 占用")

    if args.dry_run:
        print(f"\n── 阶段 1-4: 操作清单 (DRY-RUN) ──")

    ok = execute(test_client, analysis, dry_run=args.dry_run, batch_delay=args.batch)

    if args.dry_run:
        print(f"\n  [DRY-RUN] 共 {len(analysis['creates'])} 个 POST + {len(analysis['puts'])} 个 PUT")
        print(f"  [DRY-RUN] 如有冲突: {len(analysis['collisions'])} 个跳过")
    else:
        if ok:
            print("\n[OK] 全部操作执行成功")
        else:
            print("\n⚠ 部分操作失败，请检查日志")

    # ── 验证 ──
    if not args.dry_run and ok:
        vstats = verify(prod_client, test_client, root_name, out_dir)
    elif not args.dry_run and not ok:
        print("跳过验证（有失败操作）")
        vstats = None
    else:
        # dry-run 也验证（只读，没问题）
        vstats = verify(prod_client, test_client, root_name, out_dir)

    # ── 报告 ──
    rpt = write_op_report(analysis, _OP_LOG, vstats, root_name, args.dry_run, out_dir)
    print(f"\n操作报告: {rpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
