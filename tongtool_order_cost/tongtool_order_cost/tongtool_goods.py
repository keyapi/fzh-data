# -*- coding: utf-8 -*-
"""Read-only Tongtool goodsQuery via official MCP HTTP (erp2_product_goodsquery)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tongtool_api.mcp_http import McpClient, primary_credentials

GOODS_QUERY_TOOL = "erp2_product_goodsquery"


def _payload_from_call(resp: dict):
    if "error" in resp:
        raise RuntimeError(f"MCP error: {resp['error']}")
    texts = [
        c.get("text", "")
        for c in resp.get("result", {}).get("content", [])
        if c.get("type") == "text"
    ]
    raw = "\n".join(texts).strip()
    if not raw:
        return {}
    if raw.startswith("{") or raw.startswith("["):
        return json.loads(raw)
    return {"text": raw}


def goods_query(skus: list[str], product_type: str = "0", page_size: int = 20) -> dict:
    """One ERP2 business call. Keep SKU list ≤ 10 (Tongtool goodsQuery limit)."""
    if len(skus) > 10:
        raise ValueError("goodsQuery skus length must be <= 10")
    key, secret = primary_credentials()
    gc = McpClient(key, secret, client_name="fzh-goods-query")
    resp = gc.call(
        GOODS_QUERY_TOOL,
        {
            "pageNo": 1,
            "pageSize": page_size,
            "productType": product_type,
            "skus": list(skus),
        },
    )
    return _payload_from_call(resp)


def summarize_existence(payload: dict, needles: list[str]) -> dict[str, bool]:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    return {s: s.lower() in blob for s in needles}
