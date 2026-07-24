# -*- coding: utf-8 -*-
"""验证 Layer 2 方案：按 ERPNext 产品树在 NAS 上复刻层级。

用 KS0001 / KS0002 验证祖先链路径。
输出 NAS 树结构预览，不实际创建任何文件夹。

使用:
  uv run python verify_tree_structure.py
"""

from __future__ import annotations

import json
import os
import sys; sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
_NAS_API = _DIR.parent / "NAS_API"
sys.path.insert(0, str(_DIR.parent))


# ── .env loading ─────────────────────────────────────────

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
    _NAS_API / ".env",
    _DIR / ".env",
])


# ── HTTP adapter ─────────────────────────────────────────

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

    def fetch_all_item_groups(self) -> list[dict]:
        url = f"{self.base_url}/api/resource/Item Group"
        fields = json.dumps([
            "name", "parent_item_group", "is_group", "custom_model_id",
        ])
        params = {"fields": fields, "limit_page_length": "0"}
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def _request(self, method, url, *, retries=2, retry_delay=3.0, **kwargs):
        last = None
        for a in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=(30, 60), **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last = e
                if a < retries:
                    time.sleep(retry_delay)
        raise last


# ── Tree helpers ─────────────────────────────────────────

def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def get_ancestors(name: str, idx: dict[str, dict]) -> list[str]:
    """Get ancestor chain from name up to root, excluding root."""
    chain = []
    node = idx.get(name)
    while node:
        parent = node.get("parent_item_group", "")
        if not parent or parent not in idx:
            break
        chain.append(parent)
        node = idx.get(parent)
    chain.reverse()  # root-first order
    return chain


def get_descendants(name: str, idx: dict[str, dict]) -> list[dict]:
    result: list[dict] = []
    for d in idx.values():
        if d.get("parent_item_group") == name:
            result.append(d)
            result.extend(get_descendants(d["name"], idx))
    return result


# ── Sanitize ─────────────────────────────────────────────

_FORBIDDEN = str.maketrans({
    "/": "_", "\\": "_", ":": "_", "*": "_", "?": "_",
    '"': "_", "<": "_", ">": "_", "|": "_",
})


def safe_name(s: str) -> str:
    return s.translate(_FORBIDDEN).strip()


# ── Main ─────────────────────────────────────────────────

def main() -> None:
    erp_url = os.getenv("ERP_URL", "https://erpnext.vilavi.cn")
    erp_key = os.getenv("ERP_API_KEY", "")
    erp_secret = os.getenv("ERP_API_SECRET", "")
    erp = ErpnextClient(erp_url, erp_key, erp_secret)

    target_folder = os.getenv("NAS_TARGET_FOLDER", "/产品信息")
    ig_root = os.getenv("ITEM_GROUP_ROOT", "产品")

    print(f"Connecting to ERPNext: {erp_url}")
    all_ig = erp.fetch_all_item_groups()
    idx = build_index(all_ig)
    print(f"  Total item groups: {len(all_ig)}")

    # Verify root
    if ig_root not in idx:
        print(f"ERROR: root '{ig_root}' not found")
        sys.exit(1)

    # Test items
    test_models = ["KS0001", "KS0002"]
    for mid in test_models:
        leaf = next((d for d in all_ig if d.get("custom_model_id") == mid), None)
        if not leaf:
            print(f"\n{mid}: NOT FOUND")
            continue

        name = leaf["name"]
        chain = get_ancestors(name, idx)
        # Filter chain to only include nodes under ig_root
        if ig_root in chain:
            chain = chain[chain.index(ig_root):]  # from ig_root onward

        # Build NAS path
        nas_parts = [target_folder.rstrip("/")] + [safe_name(n) for n in chain]
        nas_path = "/".join(nas_parts)

        print(f"\n{'=' * 60}")
        print(f"  {mid} = {name}")
        print(f"  ERPNext 祖先链: {' > '.join(chain + [name])}")
        print(f"  NAS 路径: {nas_path}/{safe_name(mid)}_{safe_name(name)}/")
        print(f"  子文件夹: 调研报告, 设计稿, 图片, 视频")

    # ── Summary: tree depth stats ──
    print(f"\n{'=' * 60}")
    print("产品树统计:")
    subtree = [idx[ig_root]] + get_descendants(ig_root, idx)
    leaves = [d for d in subtree if d.get("is_group") == 0 and d.get("custom_model_id")]
    depths: dict[int, int] = {}
    for leaf in leaves:
        chain = get_ancestors(leaf["name"], idx)
        if ig_root in chain:
            depth = len(chain) - chain.index(ig_root)
        else:
            depth = len(chain) + 1
        depths[depth] = depths.get(depth, 0) + 1

    print(f"  叶子节点总数: {len(leaves)}")
    print(f"  深度分布:")
    for d in sorted(depths):
        print(f"    {d} 层: {depths[d]} 个")
    max_depth = max(depths) if depths else 0
    print(f"  最深: {max_depth} 层")
    if max_depth > 3:
        print(f"  WARNING: 最深 {max_depth} 层可能导致 NAS 点击过多")


if __name__ == "__main__":
    main()
