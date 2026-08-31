# -*- coding: utf-8 -*-
"""
Fix: 方形枕套 KS0013 缺颜色 — 宽边正方形枕头只有 面料+尺寸，缺 颜色。

错误: 之前建了 KS0013-HLR-80 (无颜色)。方形枕套是咖啡色，应含颜色。

修复:
1. 建 宽边正方形枕头颜色 attribute (引用 All Color, 值 咖啡色/COFFEE)
2. 更新 KS0013 模板 attributes 加入 宽边正方形枕头颜色
3. 建 KS0013-HLR-80-COFFEE (荷兰绒/80*80*18/咖啡色) + BOM
4. 禁用 KS0013-HLR-80 (错误的无颜色变体)
5. 登记客户码 TT0000779K0054313 → KS0013-HLR-80-COFFEE

用法: uv run python fix_ks0013_color.py [--dry-run]
"""
import json, os, sys
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter

_HERE = Path(__file__).resolve().parent
_MAIN = Path(r"D:\Work\赛狐\Cursor")

def _load_dotenv(paths):
    env = {}
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

class NoExpect(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)

class EN:
    def __init__(self):
        self.base = ENV.get("ERP_URL", "https://erpnext.vilavi.cn").rstrip("/")
        key = ENV.get("PROD_ERP_API_KEY") or ENV.get("ERP_API_KEY", "")
        sec = ENV.get("PROD_ERP_API_SECRET") or ENV.get("ERP_API_SECRET", "")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{sec}"
        self.s.mount("https://", NoExpect()); self.s.mount("http://", NoExpect())
    def get(self, dt, name=None, params=None):
        url = f"{self.base}/api/resource/{dt}"
        if name:
            url += f"/{requests.utils.quote(name, safe='')}"
        r = self.s.get(url, params=params or {}, timeout=60)
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        return r.json().get("data", {})
    def post(self, dt, data):
        r = self.s.post(f"{self.base}/api/resource/{dt}", json=data, timeout=60)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:300]}
    def put(self, dt, name, data):
        r = self.s.put(f"{self.base}/api/resource/{dt}/{requests.utils.quote(name, safe='')}", json=data, timeout=60)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:300]}

def main():
    dry = "--dry-run" in sys.argv
    mode = "DRY-RUN" if dry else "REAL"
    api = EN()
    print(f"模式: {mode}")
    print(f"EN: {api.base}\n")

    # 1. 建 宽边正方形枕头颜色 attribute
    attr_name = "宽边正方形枕头颜色"
    d = api.get("Item Attribute", attr_name)
    if d:
        print(f"  SKIP: {attr_name} 已存在")
    elif dry:
        print(f"  DRY-RUN: 建 {attr_name}")
    else:
        code, res = api.post("Item Attribute", {
            "attribute_name": attr_name,
            "custom_item_group": "宽边正方形枕头",
            "custom_select_doctype": "Item Attribute Value All Color",
            "custom_select_from_all_attribute_values": 1,
            "item_attribute_values": [{"attribute_value": "咖啡色", "abbr": "COFFEE"}],
        })
        print(f"  {'OK' if code==200 else 'FAIL('+str(code)+')'}: 建 {attr_name} {json.dumps(res,ensure_ascii=False)[:200] if code!=200 else ''}")

    # 2. 更新 KS0013 模板 attributes 加入 颜色
    t = api.get("Item", "KS0013")
    cur = t.get("attributes", [])
    cur_attrs = [a.get("attribute") for a in cur] if isinstance(cur, list) else []
    if attr_name in cur_attrs:
        print(f"  SKIP: KS0013 模板已含 {attr_name}")
    elif dry:
        print(f"  DRY-RUN: KS0013 模板加 {attr_name}")
    else:
        new_attrs = [{"attribute": a.get("attribute"), "attribute_value": a.get("attribute_value")} for a in cur] if isinstance(cur, list) else []
        new_attrs.append({"attribute": attr_name})
        code, res = api.put("Item", "KS0013", {"attributes": new_attrs})
        print(f"  {'OK' if code==200 else 'FAIL('+str(code)+') '+json.dumps(res,ensure_ascii=False)[:200]}: KS0013 模板加 {attr_name}")

    # 3. 建 KS0013-HLR-80-COFFEE (正确带颜色)
    code_new = "KS0013-HLR-80-COFFEE"
    if api.get("Item", code_new):
        print(f"  SKIP: {code_new} 已存在")
    elif dry:
        print(f"  DRY-RUN: 建 {code_new}")
    else:
        code, res = api.post("Item", {
            "item_code": code_new, "item_name": "宽边正方形枕头-荷兰绒-80*80*18-咖啡色",
            "item_group": "宽边正方形枕头", "stock_uom": "个",
            "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
            "variant_of": "KS0013", "has_variants": 0,
            "attributes": [
                {"attribute": "宽边正方形枕头面料", "attribute_value": "荷兰绒"},
                {"attribute": "宽边正方形枕头尺寸", "attribute_value": "80*80*18"},
                {"attribute": "宽边正方形枕头颜色", "attribute_value": "咖啡色"},
            ],
        }, )
        print(f"  {'OK' if code==200 else 'FAIL('+str(code)+') '+json.dumps(res,ensure_ascii=False)[:300]}: 建 {code_new}")

    # 4. 禁用 KS0013-HLR-80 (错误无颜色变体)
    old = "KS0013-HLR-80"
    od = api.get("Item", old)
    if not od:
        print(f"  SKIP: {old} 不存在")
    elif od.get("disabled"):
        print(f"  SKIP: {old} 已禁用")
    elif dry:
        print(f"  DRY-RUN: 禁用 {old}")
    else:
        code, res = api.put("Item", old, {"disabled": 1})
        print(f"  {'OK' if code==200 else 'FAIL'}: 禁用 {old}")

    # 5. 登记客户码 → KS0013-HLR-80-COFFEE
    item = code_new
    d = api.get("Item", item, params={"fields": json.dumps(["customer_items"])})
    custs = d.get("customer_items", [])
    existing = {c.get("ref_code", "") for c in custs} if isinstance(custs, list) else set()
    if "TT0000779K0054313" in existing:
        print(f"  SKIP: 客户码已登记 {item}")
    elif dry:
        print(f"  DRY-RUN: 登记 {item} ← TT0000779K0054313")
    else:
        new_custs = [{"customer_group": c.get("customer_group", "美国公司"), "ref_code": c.get("ref_code")} for c in custs] if isinstance(custs, list) else []
        new_custs.append({"customer_group": "美国公司", "ref_code": "TT0000779K0054313"})
        code, res = api.put("Item", item, {"customer_items": new_custs})
        print(f"  {'OK' if code==200 else 'FAIL'}: 登记 {item} ← TT0000779K0054313")

    # 6. 建 BOM (简化 → SXBZPK#KS0013-80)
    r = api.s.get(f"{api.base}/api/resource/BOM", params={"filters": json.dumps([["BOM","item","=",code_new]]), "limit_page_length": "3"}, timeout=60)
    rows = r.json().get("data", [])
    if rows:
        print(f"  SKIP: BOM 已存在 {code_new}")
    elif dry:
        print(f"  DRY-RUN: 建BOM {code_new}")
    else:
        code, res = api.post("BOM", {
            "item": code_new, "company": "FZH", "uom": "个", "quantity": 1.0,
            "is_active": 1, "is_default": 1, "rm_cost_as_per": "Price List",
            "buying_price_list": "标准采购", "currency": "CNY",
            "items": [{"item_code": "SXBZPK#KS0013-80", "qty": 1.0, "uom": "个"}],
        })
        if code == 200:
            bom_name = res.get("data", {}).get("name", "")
            api.put("BOM", bom_name, {"docstatus": 1})
            print(f"  OK: 建BOM+提交 {code_new} → {bom_name}")
        else:
            print(f"  FAIL({code}): 建BOM {code_new} {json.dumps(res,ensure_ascii=False)[:200]}")

    print("\n完成。")

if __name__ == "__main__":
    main()
