# -*- coding: utf-8 -*-
"""
Create missing EN materials for old products (星球抱枕/石头抱枕/张嘴熊).

Idempotent - safe to re-run. Checks existence before each create.
Usage:
  uv run python create_en_materials.py --dry-run          # preview only
  uv run python create_en_materials.py --phase 1          # 星球 KS0019
  uv run python create_en_materials.py --phase 2          # 石头 KS0018
  uv run python create_en_materials.py --phase 3          # 张嘴熊 + registrations
  uv run python create_en_materials.py                     # all phases
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter

_HERE = Path(__file__).resolve().parent
_MAIN = Path(r"D:\Work\赛狐\Cursor")

# ── .env ─────────────────────────────────────────────
def _load_dotenv(paths: list[Path]) -> dict[str, str]:
    env: dict[str, str] = {}
    for p in paths:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                env[k] = v
        except FileNotFoundError:
            pass
    env.update({k: v for k, v in os.environ.items() if v})
    return env


ENV = _load_dotenv([_MAIN / ".env", _MAIN / "EN_API" / ".env", _HERE / ".env"])


# ── API client ───────────────────────────────────────
class NoExpect(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class EN:
    def __init__(self):
        self.base = ENV.get("ERP_URL", "https://erpnext.vilavi.cn").rstrip("/")
        key = ENV.get("PROD_ERP_API_KEY") or ENV.get("ERP_API_KEY", "")
        sec = ENV.get("PROD_ERP_API_SECRET") or ENV.get("ERP_API_SECRET", "")
        if not key or not sec:
            raise RuntimeError("No EN API credentials")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{sec}"
        self.s.mount("https://", NoExpect())
        self.s.mount("http://", NoExpect())

    def get(self, dt: str, name: str | None = None, params: dict | None = None) -> dict:
        url = f"{self.base}/api/resource/{dt}"
        if name:
            url += f"/{requests.utils.quote(name, safe='')}"
        r = self.s.get(url, params=params or {}, timeout=60)
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        return r.json().get("data", {})

    def get_list(self, dt: str, filters: list, fields: list[str] | None = None, limit: int = 10) -> list[dict]:
        params: dict[str, Any] = {
            "filters": json.dumps(filters),
            "limit_page_length": str(limit),
        }
        if fields:
            params["fields"] = json.dumps(fields)
        r = self.s.get(f"{self.base}/api/resource/{dt}", params=params, timeout=60)
        r.raise_for_status()
        return r.json().get("data", [])

    def post(self, dt: str, data: dict) -> tuple[int, dict]:
        r = self.s.post(f"{self.base}/api/resource/{dt}", json=data, timeout=60)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}

    def put(self, dt: str, name: str, data: dict) -> tuple[int, dict]:
        url = f"{self.base}/api/resource/{dt}/{requests.utils.quote(name, safe='')}"
        r = self.s.put(url, json=data, timeout=60)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}


# ── idempotent helpers ──────────────────────────────
def ensure_attribute_value(api: EN, attr: str, value: str, abbr: str, dry_run: bool) -> str:
    """Add attribute value if not present (abbr required - Server Script validates .lower())."""
    d = api.get("Item Attribute", attr)
    vals = d.get("item_attribute_values", [])
    existing = {v.get("attribute_value", "") for v in vals} if isinstance(vals, list) else set()
    if value in existing:
        return f"SKIP (值已存在): {attr}/{value}"
    if dry_run:
        return f"DRY-RUN: 加 {attr}/{value} (abbr={abbr})"
    new_vals = [{"attribute_value": v.get("attribute_value"), "abbr": v.get("abbr", "")} for v in vals] if isinstance(vals, list) else []
    new_vals.append({"attribute_value": value, "abbr": abbr})
    code, res = api.put("Item Attribute", attr, {"item_attribute_values": new_vals})
    if code == 200:
        return f"OK: 加 {attr}/{value} (abbr={abbr})"
    return f"FAIL({code}): 加 {attr}/{value} {json.dumps(res, ensure_ascii=False)[:300]}"


def ensure_item(api: EN, code: str, payload: dict, dry_run: bool) -> str:
    """Create item if not exists."""
    d = api.get("Item", code)
    if d:
        return f"SKIP (已存在): {code}"
    if dry_run:
        return f"DRY-RUN: 建 {code}"
    code_status, res = api.post("Item", payload)
    if code_status == 200:
        return f"OK: 建 {code}"
    return f"FAIL({code_status}): 建 {code} {json.dumps(res, ensure_ascii=False)[:200]}"


def ensure_item_price(api: EN, item: str, price_list: str, rate: float, dry_run: bool) -> str:
    """Create/update Item Price for item in price list."""
    # check existing
    rows = api.get_list("Item Price", [["Item Price", "item_code", "=", item], ["Item Price", "price_list", "=", price_list]])
    if rows:
        existing_rate = rows[0].get("price_list_rate")
        if existing_rate == rate:
            return f"SKIP (价格已存在): {item}/{price_list}={rate}"
        if dry_run:
            return f"DRY-RUN: 更新 {item}/{price_list}={existing_rate}→{rate}"
        code, res = api.put("Item Price", rows[0]["name"], {"price_list_rate": rate})
        return f"OK: 更新 {item}/{price_list}={rate}" if code == 200 else f"FAIL: {item} {json.dumps(res, ensure_ascii=False)[:200]}"
    if dry_run:
        return f"DRY-RUN: 加价格 {item}/{price_list}={rate}"
    code, res = api.post("Item Price", {"item_code": item, "price_list": price_list, "price_list_rate": rate, "currency": "CNY"})
    if code == 200:
        return f"OK: 加价格 {item}/{price_list}={rate}"
    return f"FAIL({code}): 加价格 {item} {json.dumps(res, ensure_ascii=False)[:200]}"


def ensure_customer_code(api: EN, item: str, code: str, group: str, dry_run: bool) -> str:
    """Add ref_code to item's customer_items if not present."""
    d = api.get("Item", item, params={"fields": json.dumps(["customer_items"])})
    custs = d.get("customer_items", [])
    existing = {c.get("ref_code", "") for c in custs} if isinstance(custs, list) else set()
    if code in existing:
        return f"SKIP (客户码已登记): {item} ← {code}"
    if dry_run:
        return f"DRY-RUN: 登记 {item} ← {code}"
    new_custs = [{"customer_group": c.get("customer_group", group), "ref_code": c.get("ref_code")} for c in custs] if isinstance(custs, list) else []
    new_custs.append({"customer_group": group, "ref_code": code})
    code_status, res = api.put("Item", item, {"customer_items": new_custs})
    if code_status == 200:
        return f"OK: 登记 {item} ← {code}"
    return f"FAIL({code_status}): 登记 {item} ← {code} {json.dumps(res, ensure_ascii=False)[:200]}"


def ensure_bom(api: EN, item: str, items: list[dict], dry_run: bool, name_hint: str = "") -> str:
    """Create + submit BOM for item if not exists."""
    rows = api.get_list("BOM", [["BOM", "item", "=", item]])
    if rows:
        return f"SKIP (BOM已存在): {item} → {rows[0]['name']}"
    if dry_run:
        return f"DRY-RUN: 建BOM {item}"
    payload = {
        "item": item,
        "company": "FZH",
        "uom": "个",
        "quantity": 1.0,
        "is_active": 1,
        "is_default": 1,
        "rm_cost_as_per": "Price List",
        "buying_price_list": "标准采购",
        "currency": "CNY",
        "items": items,
    }
    code, res = api.post("BOM", payload)
    if code != 200:
        return f"FAIL({code}): 建BOM {item} {json.dumps(res, ensure_ascii=False)[:300]}"
    bom_name = res.get("data", {}).get("name", "")
    # submit
    code2, _ = api.put("BOM", bom_name, {"docstatus": 1})
    if code2 == 200:
        return f"OK: 建BOM+提交 {item} → {bom_name}"
    return f"OK(未提交): 建BOM {item} → {bom_name} (submit status {code2})"


def ensure_valuation(api: EN, item: str, rate: float, dry_run: bool) -> str:
    """Set valuation_rate on item if different."""
    d = api.get("Item", item, params={"fields": json.dumps(["valuation_rate"])})
    if d and abs((d.get("valuation_rate") or 0) - rate) < 0.01:
        return f"SKIP (valuation已设): {item}={rate}"
    if dry_run:
        return f"DRY-RUN: 设 valuation {item}={rate}"
    code, res = api.put("Item", item, {"valuation_rate": rate})
    return f"OK: 设 valuation {item}={rate}" if code == 200 else f"FAIL: {item} {json.dumps(res, ensure_ascii=False)[:200]}"


# ── Phase 1: 星球抱枕 KS0019 ─────────────────────────
def phase1(api: EN, dry_run: bool):
    print("\n===== Phase 1: 星球抱枕 KS0019 =====")
    # 1. attribute values
    for v, abbr in [("月球", "MOON"), ("黑月球", "BLACKMOON")]:
        print(" ", ensure_attribute_value(api, "星球抱枕颜色", v, abbr, dry_run))

    # 2. 41cm supporting items
    for code, name, group, vo, attrs in [
        ("SXBZPK#KS0019-41", "绍兴包装皮壳#星球抱枕-41cm", "绍兴包装皮壳#星球抱枕", "SXBZPK#KS0019",
         [{"attribute": "星球抱枕尺寸", "attribute_value": "41cm"}]),
        ("PK#KS0019-PBHLR-41", "皮壳#星球抱枕-漂白荷兰绒-41cm", "皮壳#星球抱枕", "PK#KS0019",
         [{"attribute": "星球抱枕面料", "attribute_value": "漂白荷兰绒"},
          {"attribute": "星球抱枕尺寸", "attribute_value": "41cm"}]),
        ("ZLMB#KS0019-PBHLR-41", "重量模板#星球抱枕-漂白荷兰绒-41cm", "重量模板#星球抱枕", "ZLMB#KS0019",
         [{"attribute": "星球抱枕面料", "attribute_value": "漂白荷兰绒"},
          {"attribute": "星球抱枕尺寸", "attribute_value": "41cm"}]),
    ]:
        print(" ", ensure_item(api, code, {
            "item_code": code, "item_name": name, "item_group": group,
            "stock_uom": "个", "is_stock_item": 1, "include_item_in_manufacturing": 1,
            "is_sales_item": 0, "variant_of": vo, "has_variants": 0,
            "attributes": attrs,
        }, dry_run))

    # Item Price for SXBZPK#KS0019-41 (成本 12.51)
    print(" ", ensure_item_price(api, "SXBZPK#KS0019-41", "标准采购", 12.51, dry_run))

    # 3. 成品 variants (25cm×2 + 41cm×3)
    variants = [
        ("KS0019-PBHLR-25-MOON", "星球抱枕-漂白荷兰绒-25cm-月球", "25cm", "月球"),
        ("KS0019-PBHLR-25-BLACKMOON", "星球抱枕-漂白荷兰绒-25cm-黑月球", "25cm", "黑月球"),
        ("KS0019-PBHLR-41-EARTH", "星球抱枕-漂白荷兰绒-41cm-地球", "41cm", "地球"),
        ("KS0019-PBHLR-41-MOON", "星球抱枕-漂白荷兰绒-41cm-月球", "41cm", "月球"),
        ("KS0019-PBHLR-41-BLACKMOON", "星球抱枕-漂白荷兰绒-41cm-黑月球", "41cm", "黑月球"),
    ]
    for code, name, size, color in variants:
        print(" ", ensure_item(api, code, {
            "item_code": code, "item_name": name, "item_group": "星球抱枕",
            "stock_uom": "个", "is_stock_item": 1, "include_item_in_manufacturing": 1,
            "is_sales_item": 1, "variant_of": "KS0019", "has_variants": 0,
            "attributes": [
                {"attribute": "星球抱枕面料", "attribute_value": "漂白荷兰绒"},
                {"attribute": "星球抱枕尺寸", "attribute_value": size},
                {"attribute": "星球抱枕颜色", "attribute_value": color},
            ],
        }, dry_run))

    # 4. 成品 BOMs (simplified → SXBZPK#)
    sxbzpk = {"25cm": "SXBZPK#KS0019-25", "41cm": "SXBZPK#KS0019-41"}
    for code, _n, size, _c in variants:
        print(" ", ensure_bom(api, code, [{"item_code": sxbzpk[size], "qty": 1.0, "uom": "个"}], dry_run))

    # 5. customer codes
    cust_map = {
        "KS0019-PBHLR-25-MOON": "XINGQIU-Moon-10",
        "KS0019-PBHLR-25-BLACKMOON": "XINGQIU-BlackMoon-10",
        "KS0019-PBHLR-41-EARTH": "XINGQIU-Earth-16",
        "KS0019-PBHLR-41-MOON": "XINGQIU-Moon-16",
        "KS0019-PBHLR-41-BLACKMOON": "XINGQIU-BlackMoon-16",
        "KS0019-PBHLR-SET12-PLANETARYMASHUP": "XINGQIU-12PCS",
    }
    for item, code in cust_map.items():
        print(" ", ensure_customer_code(api, item, code, "美国公司", dry_run))

    # 6. Fix misregistration: remove XINGQIU-Moon-10 from KS0018-LSRBS-25cm-STONE
    print(" ", fix_moon10(api, dry_run))


def fix_moon10(api: EN, dry_run: bool) -> str:
    """Remove XINGQIU-Moon-10 from KS0018-LSRBS-25cm-STONE customer_items."""
    item = "KS0018-LSRBS-25cm-STONE"
    d = api.get("Item", item, params={"fields": json.dumps(["customer_items"])})
    custs = d.get("customer_items", [])
    if not isinstance(custs, list):
        return f"SKIP: {item} 无 customer_items"
    filtered = [c for c in custs if c.get("ref_code", "") != "XINGQIU-Moon-10"]
    if len(filtered) == len(custs):
        return f"SKIP: {item} 上没有 XINGQIU-Moon-10（已移除）"
    if dry_run:
        return f"DRY-RUN: 从 {item} 移除 XINGQIU-Moon-10"
    new_custs = [{"customer_group": c.get("customer_group", "美国公司"), "ref_code": c.get("ref_code")} for c in filtered]
    code, res = api.put("Item", item, {"customer_items": new_custs})
    if code == 200:
        return f"OK: 从 {item} 移除 XINGQIU-Moon-10"
    return f"FAIL: 移除 XINGQIU-Moon-10 {json.dumps(res, ensure_ascii=False)[:200]}"


# ── Phase 2: 石头抱枕 KS0018 ─────────────────────────
def phase2(api: EN, dry_run: bool):
    print("\n===== Phase 2: 石头抱枕 KS0018 =====")
    # 1. attribute values
    for i in range(1, 7):
        print(" ", ensure_attribute_value(api, "印花石头抱枕颜色", f"浅灰{i}号", f"LIGHTGREY{i}", dry_run))
    for i in range(1, 7):
        print(" ", ensure_attribute_value(api, "印花石头抱枕颜色", f"深灰{i}号", f"DARKGREY{i}", dry_run))

    # 2. 12 variants
    stones = [f"浅灰{i}号" for i in range(1, 7)] + [f"深灰{i}号" for i in range(1, 7)]
    for color in stones:
        code = f"KS0018-LSRBS-25cm-{color}"
        print(" ", ensure_item(api, code, {
            "item_code": code, "item_name": f"印花石头抱枕-丽丝绒白色-25cm-{color}",
            "item_group": "印花石头抱枕", "stock_uom": "个",
            "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
            "variant_of": "KS0018", "has_variants": 0,
            "attributes": [
                {"attribute": "印花石头抱枕面料", "attribute_value": "丽丝绒白色"},
                {"attribute": "印花石头抱枕尺寸", "attribute_value": "25cm"},
                {"attribute": "印花石头抱枕颜色", "attribute_value": color},
            ],
        }, dry_run))
        print("   ", ensure_valuation(api, code, 7.85, dry_run))
        print("   ", ensure_item_price(api, code, "标准采购", 7.85, dry_run))

    # 3. self-referencing BOMs (match STONE pattern)
    for color in stones:
        code = f"KS0018-LSRBS-25cm-{color}"
        print(" ", ensure_bom(api, code, [{"item_code": code, "qty": 1.0, "uom": "个"}], dry_run))

    # 4. customer codes
    cust_map = {}
    for i, color in enumerate([f"浅灰{i}号" for i in range(1, 7)], start=1):
        cust_map[f"KS0018-LSRBS-25cm-{color}"] = f"TT0009004K{9066+i:07d}"
    for i, color in enumerate([f"深灰{i}号" for i in range(1, 7)], start=1):
        cust_map[f"KS0018-LSRBS-25cm-{color}"] = f"TT0009005K{9072+i:07d}"
    for item, code in cust_map.items():
        print(" ", ensure_customer_code(api, item, code, "美国公司", dry_run))

    # LSPPW-03/04 (精确新建，参照 LSPPW01: valuation 47.036 + BOM→PK#KS0018-LSRBS-SET7)
    for color, cust in [("LSPPW03", "TT0009044K0024160"), ("LSPPW04", "TT0009035K0024151")]:
        print(" ", ensure_attribute_value(api, "印花石头抱枕颜色", color, color, dry_run))
        code = f"KS0018-LSRBS-SET7-{color}"
        print(" ", ensure_item(api, code, {
            "item_code": code, "item_name": f"印花石头抱枕-丽丝绒白色-7件套-{color}",
            "item_group": "印花石头抱枕", "stock_uom": "个",
            "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
            "variant_of": "KS0018", "has_variants": 0,
            "attributes": [
                {"attribute": "印花石头抱枕面料", "attribute_value": "丽丝绒白色"},
                {"attribute": "印花石头抱枕尺寸", "attribute_value": "7件套"},
                {"attribute": "印花石头抱枕颜色", "attribute_value": color},
            ],
        }, dry_run))
        print("   ", ensure_valuation(api, code, 47.036, dry_run))
        print(" ", ensure_bom(api, code, [{"item_code": "PK#KS0018-LSRBS-SET7", "qty": 1.0, "uom": "个"}], dry_run))
        print(" ", ensure_customer_code(api, code, cust, "美国公司", dry_run))


# ── Phase 3: 张嘴熊 + 泰迪熊登记 ─────────────────────
def phase3(api: EN, dry_run: bool):
    print("\n===== Phase 3: 张嘴熊 + 泰迪熊 =====")
    # 1. 张嘴熊 340cm (成本 153 = 2×76.5)
    print(" ", ensure_item(api, "SXBZPK#KS0026-340", {
        "item_code": "SXBZPK#KS0026-340", "item_name": "绍兴包装皮壳#泰迪熊-340",
        "item_group": "绍兴包装皮壳#泰迪熊", "stock_uom": "个",
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 0,
        "attributes": [{"attribute": "泰迪熊尺寸", "attribute_value": "340"}],
    }, dry_run))
    print(" ", ensure_item_price(api, "SXBZPK#KS0026-340", "标准采购", 153.0, dry_run))
    print(" ", ensure_item(api, "KS0026-TDR-340-LIGHTBROWN", {
        "item_code": "KS0026-TDR-340-LIGHTBROWN", "item_name": "泰迪熊-泰迪绒-340-浅棕色",
        "item_group": "泰迪熊", "stock_uom": "个",
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
        "variant_of": "KS0026", "has_variants": 0,
        "attributes": [
            {"attribute": "泰迪熊面料", "attribute_value": "泰迪绒"},
            {"attribute": "泰迪熊尺寸", "attribute_value": "340"},
            {"attribute": "泰迪熊颜色", "attribute_value": "浅棕色"},
        ],
    }, dry_run))
    print(" ", ensure_bom(api, "KS0026-TDR-340-LIGHTBROWN", [{"item_code": "SXBZPK#KS0026-340", "qty": 1.0, "uom": "个"}], dry_run))
    print(" ", ensure_customer_code(api, "KS0026-TDR-340-LIGHTBROWN", "CENTEDDY-LMA3-340", "美国公司", dry_run))

    # 2. 泰迪熊 7 TT codes → KS0026 variants
    teddy_map = {
        "KS0026-TDR-25-PINK": "TT0000394K0009600",
        "KS0026-TDR-92-LIGHTBROWN": "TT0000396K0009607",
        "KS0026-TDR-25-WHITE": "TT0000398K0009612",
        "KS0026-TDR-92-WHITE": "TT0000398K0009613",
        "KS0026-TDR-183-WHITE": "TT0000398K0009614",
        "KS0026-TDR-92-PURPLE": "TT0000404K0011599",
        "KS0026-TDR-183-PURPLE": "TT0000404K0011600",
    }
    for item, code in teddy_map.items():
        print(" ", ensure_customer_code(api, item, code, "美国公司", dry_run))


# ── Phase 4: 星球补齐 + 抱心泰迪归泰迪熊 ────────────
def phase4(api: EN, dry_run: bool):
    print("\n===== Phase 4: 星球补齐 + 抱心泰迪 =====")
    # 1. 星球新增 25cm-EARTH + 41cm-JUPITER（完整矩阵：25/41 × 木星/月球/黑月球/地球）
    sxbzpk = {"25cm": "SXBZPK#KS0019-25", "41cm": "SXBZPK#KS0019-41"}
    for code, name, size, color, cust in [
        ("KS0019-PBHLR-25-EARTH", "星球抱枕-漂白荷兰绒-25cm-地球", "25cm", "地球", "TT0009006K0009477"),
        ("KS0019-PBHLR-41-JUPITER", "星球抱枕-漂白荷兰绒-41cm-木星", "41cm", "木星", "TT0009008K0009480"),
    ]:
        print(" ", ensure_item(api, code, {
            "item_code": code, "item_name": name, "item_group": "星球抱枕",
            "stock_uom": "个", "is_stock_item": 1, "include_item_in_manufacturing": 1,
            "is_sales_item": 1, "variant_of": "KS0019", "has_variants": 0,
            "attributes": [
                {"attribute": "星球抱枕面料", "attribute_value": "漂白荷兰绒"},
                {"attribute": "星球抱枕尺寸", "attribute_value": size},
                {"attribute": "星球抱枕颜色", "attribute_value": color},
            ],
        }, dry_run))
        print(" ", ensure_bom(api, code, [{"item_code": sxbzpk[size], "qty": 1.0, "uom": "个"}], dry_run))
        print(" ", ensure_customer_code(api, code, cust, "美国公司", dry_run))

    # 2. 星球 TT 别名 → 登记到对应变体
    aliases = [
        ("KS0019-PBHLR-25-MOON", "TT0009009K0009483"),
        ("KS0019-PBHLR-25-JUPITER", "TT0009008K0009481"),
        ("KS0019-PBHLR-41-BLACKMOON", "TT0009007K0009478"),
        ("KS0019-PBHLR-41-MOON", "TT0009009K0009482"),
        ("KS0019-PBHLR-41-EARTH", "TT0009006K0009476"),
        ("KS0019-PBHLR-25-BLACKMOON", "TT0009007K0009479"),
    ]
    for item, code in aliases:
        print(" ", ensure_customer_code(api, item, code, "美国公司", dry_run))

    # 3. 抱心泰迪熊/白色泰迪 → 归到泰迪熊/爱心熊（简化）
    heart_map = [
        ("KS0026-TDR-120-WHITE", "WJ-TAIDI-BAI-120CM"),
        ("KS0027-TDR-90-WHITE", "WJ-TAIDI-SE9-90CM"),
        ("KS0027-TDR-90-WHITE", "WJ-TAIDI-SE9-50CM"),
        ("KS0027-TDR-90-WHITE", "WJ-TAIDI-SE9-70CM"),
    ]
    for item, code in heart_map:
        print(" ", ensure_customer_code(api, item, code, "美国公司", dry_run))


def ensure_item_attribute(api: EN, attr: str, item_group: str, select_doctype: str, values: list[tuple[str, str]], dry_run: bool) -> str:
    """Create a new Item Attribute with values [(value, abbr), ...] if not exists."""
    d = api.get("Item Attribute", attr)
    if d:
        return f"SKIP (属性已存在): {attr}"
    if dry_run:
        return f"DRY-RUN: 建属性 {attr} (group={item_group}, doctype={select_doctype})"
    payload = {
        "attribute_name": attr,
        "custom_item_group": item_group,
        "custom_select_doctype": select_doctype,
        "custom_select_from_all_attribute_values": 1,
        "item_attribute_values": [{"attribute_value": v, "abbr": a} for v, a in values],
    }
    code, res = api.post("Item Attribute", payload)
    if code == 200:
        return f"OK: 建属性 {attr}"
    return f"FAIL({code}): 建属性 {attr} {json.dumps(res, ensure_ascii=False)[:300]}"


# ── Phase 5: 方形枕套 (窄边正方形抱枕 KS0014) ────────
def phase5(api: EN, dry_run: bool):
    print("\n===== Phase 5: 方形枕套 (窄边正方形抱枕 KS0014) =====")
    # 1. 颜色属性（select All Color）+ 咖啡色
    print(" ", ensure_item_attribute(api, "窄边正方形抱枕颜色", "窄边正方形抱枕",
                                     "Item Attribute Value All Color", [("咖啡色", "COFFEE")], dry_run))
    # 2. 尺寸加 80*80（现有 50*50*15）
    print(" ", ensure_attribute_value(api, "窄边正方形抱枕尺寸", "80*80", "80", dry_run))
    # 3. KS0014 模板物料
    print(" ", ensure_item(api, "KS0014", {
        "item_code": "KS0014", "item_name": "窄边正方形抱枕", "item_group": "窄边正方形抱枕",
        "stock_uom": "个", "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
        "has_variants": 1,
        "attributes": [
            {"attribute": "窄边正方形抱枕面料"}, {"attribute": "窄边正方形抱枕尺寸"}, {"attribute": "窄边正方形抱枕颜色"},
        ],
    }, dry_run))
    # 4. 绍兴包装皮壳# 模板 + 80*80 变体（成本 15.44）
    print(" ", ensure_item(api, "SXBZPK#KS0014", {
        "item_code": "SXBZPK#KS0014", "item_name": "绍兴包装皮壳#窄边正方形抱枕",
        "item_group": "绍兴包装皮壳#窄边正方形抱枕", "stock_uom": "个",
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 0, "has_variants": 1,
        "attributes": [{"attribute": "窄边正方形抱枕尺寸"}],
    }, dry_run))
    print(" ", ensure_item(api, "SXBZPK#KS0014-80", {
        "item_code": "SXBZPK#KS0014-80", "item_name": "绍兴包装皮壳#窄边正方形抱枕-80*80",
        "item_group": "绍兴包装皮壳#窄边正方形抱枕", "stock_uom": "个",
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 0,
        "variant_of": "SXBZPK#KS0014", "has_variants": 0,
        "attributes": [{"attribute": "窄边正方形抱枕尺寸", "attribute_value": "80*80"}],
    }, dry_run))
    print(" ", ensure_item_price(api, "SXBZPK#KS0014-80", "标准采购", 15.44, dry_run))
    # 5. 方形枕套 成品变体
    print(" ", ensure_item(api, "KS0014-HLR-80-COFFEE", {
        "item_code": "KS0014-HLR-80-COFFEE", "item_name": "窄边正方形抱枕-荷兰绒-80*80-咖啡色 枕套",
        "item_group": "窄边正方形抱枕", "stock_uom": "个",
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
        "variant_of": "KS0014", "has_variants": 0,
        "attributes": [
            {"attribute": "窄边正方形抱枕面料", "attribute_value": "荷兰绒"},
            {"attribute": "窄边正方形抱枕尺寸", "attribute_value": "80*80"},
            {"attribute": "窄边正方形抱枕颜色", "attribute_value": "咖啡色"},
        ],
    }, dry_run))
    # 6. 简化 BOM → 绍兴包装皮壳#（只卖皮壳）
    print(" ", ensure_bom(api, "KS0014-HLR-80-COFFEE", [{"item_code": "SXBZPK#KS0014-80", "qty": 1.0, "uom": "个"}], dry_run))
    # 7. 客户码
    print(" ", ensure_customer_code(api, "KS0014-HLR-80-COFFEE", "TT0000779K0054313", "美国公司", dry_run))


# ── Phase 6: 方形枕套 KS0013（宽边正方形枕头）────────
def phase6(api: EN, dry_run: bool):
    print("\n===== Phase 6: 方形枕套 KS0013 (宽边正方形枕头) =====")
    # KS0013 已有属性: 面料=荷兰绒(HLR), 尺寸=80*80*18(abbr 80); 无颜色属性
    # 1. SXBZPK#KS0013-80（绍兴包装皮壳，成本 39.98，二次加工 0）
    print(" ", ensure_item(api, "SXBZPK#KS0013-80", {
        "item_code": "SXBZPK#KS0013-80", "item_name": "绍兴包装皮壳#宽边正方形枕头-80*80*18",
        "item_group": "绍兴包装皮壳#宽边正方形枕头", "stock_uom": "个",
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 0,
        "variant_of": "SXBZPK#KS0013", "has_variants": 0,
        "attributes": [{"attribute": "宽边正方形枕头尺寸", "attribute_value": "80*80*18"}],
    }, dry_run))
    print(" ", ensure_item_price(api, "SXBZPK#KS0013-80", "标准采购", 39.98, dry_run))

    # 2. 成品 KS0013-HLR-80（荷兰绒-80*80*18，无颜色维度）
    print(" ", ensure_item(api, "KS0013-HLR-80", {
        "item_code": "KS0013-HLR-80", "item_name": "宽边正方形枕头-荷兰绒-80*80*18",
        "item_group": "宽边正方形枕头", "stock_uom": "个",
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
        "variant_of": "KS0013", "has_variants": 0,
        "attributes": [
            {"attribute": "宽边正方形枕头面料", "attribute_value": "荷兰绒"},
            {"attribute": "宽边正方形枕头尺寸", "attribute_value": "80*80*18"},
        ],
    }, dry_run))

    # 3. 简化 BOM → SXBZPK#KS0013-80（只卖皮壳）
    print(" ", ensure_bom(api, "KS0013-HLR-80", [{"item_code": "SXBZPK#KS0013-80", "qty": 1.0, "uom": "个"}], dry_run))

    # 4. 登记客户码
    print(" ", ensure_customer_code(api, "KS0013-HLR-80", "TT0000779K0054313", "美国公司", dry_run))


# ── main ─────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只读预览，不写入")
    ap.add_argument("--phase", type=int, choices=[1, 2, 3, 4, 5, 6], help="只运行指定 phase")
    args = ap.parse_args()

    api = EN()
    mode = "DRY-RUN" if args.dry_run else "REAL"
    print(f"模式: {mode}")
    print(f"EN: {api.base}")

    if args.phase is None or args.phase == 1:
        phase1(api, args.dry_run)
    if args.phase is None or args.phase == 2:
        phase2(api, args.dry_run)
    if args.phase is None or args.phase == 3:
        phase3(api, args.dry_run)
    if args.phase is None or args.phase == 4:
        phase4(api, args.dry_run)
    if args.phase is None or args.phase == 5:
        phase5(api, args.dry_run)
    if args.phase is None or args.phase == 6:
        phase6(api, args.dry_run)

    print("\n完成。")


if __name__ == "__main__":
    main()
