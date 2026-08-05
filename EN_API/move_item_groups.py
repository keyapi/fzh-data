# -*- coding: utf-8 -*-
"""EN 测试系统物料组重新归类工具。

将指定物料组移动到新的父物料组下。

使用:
  python move_item_groups.py --dry-run      # 预览
  python move_item_groups.py                 # 执行
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

_ENVS = {
    "test": {"url": "https://ensh.vilavi.cn", "key": "TEST_ERP_API_KEY", "sec": "TEST_ERP_API_SECRET", "label": "测试系统"},
    "prod": {"url": "https://erpnext.vilavi.cn", "key": "PROD_ERP_API_KEY", "sec": "PROD_ERP_API_SECRET", "label": "生产系统"},
}


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
            "name", "item_group_name", "parent_item_group", "is_group", "custom_model_id",
        ])
        params = {"fields": fields, "limit_page_length": "0"}
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def update_item_group(self, name: str, fields: dict[str, Any]) -> dict[str, Any]:
        safe = quote(name, safe="")
        url = f"{self.base_url}/api/resource/Item Group/{safe}"
        return self._request("PUT", url, json=fields).json().get("data", {})

    def rebuild_tree(self) -> bool:
        url = f"{self.base_url}/api/method/frappe.utils.nestedset.rebuild_tree"
        resp = self._request("POST", url, json={
            "doctype": "Item Group",
            "parent_field": "parent_item_group",
        })
        return resp.ok

    def _request(self, method: str, url: str, *,
                 retries: int = 3, retry_delay: float = 3.0,
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
                # 500/502/503/504/417/408: 递增延迟重试
                status = getattr(getattr(e, "response", None), "status_code", 0)
                if status in (500, 502, 503, 504, 417, 408) and a < retries:
                    delay = retry_delay * (a + 1) * 2
                    print(f"    [RETRY {a+1}/{retries}] HTTP {status}, 等待 {delay:.0f}s...")
                    time.sleep(delay)
                elif isinstance(e, (requests.exceptions.ConnectTimeout,
                                    requests.exceptions.ConnectionError)):
                    if a < retries:
                        delay = retry_delay * (a + 1)
                        print(f"    [RETRY {a+1}/{retries}] {type(e).__name__}, 等待 {delay:.0f}s...")
                        time.sleep(delay)
                    elif a >= retries:
                        raise
                elif a < retries:
                    time.sleep(retry_delay)
        raise last


# ── 移动清单 ──────────────────────────────────────────
# 格式: (源物料组名称, 目标父节点名称)
MOVE_LIST: list[tuple[str, str]] = [
    # → 儿童类
    ("笔记本地垫", "儿童类"),
    ("薯条沙发升级款", "儿童类"),
    ("汉堡地板坐垫", "儿童类"),
    # → 功能枕类
    ("五件套靠枕", "功能枕类"),
    ("手臂支撑枕", "功能枕类"),
    # → 床上用品
    ("床上用品印花套装- 小长方形枕", "床上用品"),
    ("床上用品印花套装-大长方形枕头", "床上用品"),
    ("床上用品印花套装-方抱枕", "床上用品"),
    ("床上用品印花套装-三角靠枕", "床上用品"),
    # → 其他靠枕
    ("印花款-星球床头靠枕", "其他靠枕"),
    ("贝壳床头靠垫", "其他靠枕"),
    # → 坐垫
    ("异形沙包坐墩", "坐垫"),
    # → 单人沙发
    ("抽条大兔毛系列-圆沙发-延长脚凳", "单人沙发"),
]


def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def verify_moves(client: ErpnextClient, dry_run: bool) -> dict[str, Any]:
    """验证移动清单中的所有节点是否存在，返回验证结果。"""
    data = client.fetch_all_item_groups()
    idx = build_index(data)

    results: list[dict[str, Any]] = []
    all_ok = True

    print(f"\n── 验证物料组 ({len(data)} 个) ──")
    for src_name, tgt_parent in MOVE_LIST:
        src = idx.get(src_name)
        tgt = idx.get(tgt_parent)

        src_ok = src is not None
        tgt_ok = tgt is not None

        status = "✅" if src_ok and tgt_ok else "❌"
        if not src_ok:
            all_ok = False
        if not tgt_ok:
            all_ok = False

        current_parent = src.get("parent_item_group", "") if src else "N/A"
        is_group = src.get("is_group", "N/A") if src else "N/A"

        results.append({
            "源物料组": src_name,
            "源存在": "是" if src_ok else "否",
            "当前父级": current_parent,
            "is_group": is_group,
            "目标父节点": tgt_parent,
            "目标存在": "是" if tgt_ok else "否",
            "状态": status,
        })

    df = pd.DataFrame(results)
    print(df.to_string(index=False))

    if not dry_run and all_ok:
        # 执行模式 + 全部验证通过 → 执行移动
        _execute_moves(client, idx, data, results)
    elif dry_run:
        print(f"\n[DRY-RUN] 预览完成。共 {len(MOVE_LIST)} 个待移动物料组。")
    else:
        print(f"\n[FAIL] 验证未通过，请修复后再执行。")

    return {"all_ok": all_ok, "results": results, "data": data}


def _execute_moves(
    client: ErpnextClient,
    idx: dict[str, dict],
    all_data: list[dict],
    verify_results: list[dict],
) -> bool:
    """执行物料组移动。"""
    print(f"\n{'='*60}")
    print(f"  开始执行移动 ({len(MOVE_LIST)} 个)")
    print(f"{'='*60}")

    success = 0
    fail = 0
    op_log: list[dict[str, Any]] = []

    for src_name, tgt_parent in MOVE_LIST:
        src = idx.get(src_name)
        current_parent = src.get("parent_item_group", "") if src else ""

        print(f"\n  移动: {src_name}")
        print(f"    当前: {current_parent}  →  目标: {tgt_parent}")

        op_log.append({
            "源物料组": src_name,
            "当前父级": current_parent,
            "目标父级": tgt_parent,
        })

        try:
            fields: dict[str, Any] = {"parent_item_group": tgt_parent}
            client.update_item_group(src_name, fields)
            print(f"    ✅ 成功")
            op_log[-1]["状态"] = "OK"
            success += 1
        except requests.RequestException as e:
            body = _get_error_body(e)
            # 若因叶子节点失败，设 is_group=1 重试
            if body and "不能是一个叶节点" in body:
                try:
                    fields = {"parent_item_group": tgt_parent, "is_group": 1}
                    client.update_item_group(src_name, fields)
                    print(f"    ✅ 成功 (is_group=1)")
                    op_log[-1]["状态"] = "OK (is_group=1)"
                    success += 1
                except requests.RequestException as e2:
                    print(f"    ❌ 失败 (叶节点重试): {e2}")
                    op_log[-1]["状态"] = f"FAIL: {e2}"
                    fail += 1
            else:
                print(f"    ❌ 失败: {e}")
                op_log[-1]["状态"] = f"FAIL: {e}"
                fail += 1

        time.sleep(0.3)

    # ── 重建嵌套集树 ──
    print(f"\n── 重建嵌套集树 ──")
    try:
        client.rebuild_tree()
        print(f"  ✅ 重建成功")
    except requests.RequestException as e:
        print(f"  ⚠️ 重建失败: {e}")

    # ── 摘要 ──
    print(f"\n{'='*60}")
    print(f"  完成! 成功={success}, 失败={fail}")
    print(f"{'='*60}")

    # ── 写入报告 ──
    _write_report(verify_results, op_log)

    return fail == 0


def _write_report(verify_results: list[dict], op_log: list[dict]) -> Path:
    """输出 Excel 操作报告。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _DIR_OUT / f"物料组重新归类_{ts}.xlsx"

    summary = [
        {"指标": "操作时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"指标": "环境", "值": "测试系统 (ensh.vilavi.cn)"},
        {"指标": "待移动", "值": len(MOVE_LIST)},
        {"指标": "成功", "值": sum(1 for o in op_log if o.get("状态", "").startswith("OK"))},
        {"指标": "失败", "值": sum(1 for o in op_log if o.get("状态", "").startswith("FAIL"))},
    ]

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(verify_results).to_excel(writer, sheet_name="验证清单", index=False)
        pd.DataFrame(op_log).to_excel(writer, sheet_name="操作日志", index=False)

    print(f"\n操作报告: {path}")
    return path


def _get_error_body(exc: requests.RequestException) -> str:
    resp = getattr(exc, "response", None)
    if resp is None:
        return ""
    try:
        data = resp.json()
        return data.get("exception", "") or data.get("_server_messages", "")
    except Exception:
        return resp.text


# ── 主入口 ─────────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="EN 物料组重新归类")
    ap.add_argument("--env", choices=list(_ENVS.keys()), default="test", help="目标环境")
    ap.add_argument("--dry-run", action="store_true", help="预览模式，不下发修改")
    args = ap.parse_args()

    env_info = _ENVS[args.env]
    api_key = os.getenv(env_info["key"], "")
    api_secret = os.getenv(env_info["sec"], "")
    if not api_key or not api_secret:
        print(f"错误: 请设置 {env_info['key']} / {env_info['sec']}")
        return 1

    client = ErpnextClient(env_info["url"], api_key, api_secret)
    print(f"{env_info['label']}: {env_info['url']}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '执行'}")
    print(f"待移动物料组: {len(MOVE_LIST)} 个")

    result = verify_moves(client, dry_run=args.dry_run)

    if not result["all_ok"] and not args.dry_run:
        print("\n[FAIL] 验证未通过，已中止执行。")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
