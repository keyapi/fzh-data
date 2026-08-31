# -*- coding: utf-8 -*-
"""
Fix: 石头单石 KS0018 物料编号用中文颜色值 → 改为英文 abbr。

错误: KS0018-LSRBS-25cm-浅灰1号 (中文颜色值在编号里) 违反 EN 命名约定
正确: KS0018-LSRBS-25cm-LIGHTGREY1 (用 abbr) — 赛狐也要求英文编号

对每个: 建新abbr编号 → valuation/ItemPrice/BOM → 迁移客户码 → 禁用旧中文编号
用法: uv run python fix_ks0018_stone_codes.py [--dry-run]
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

# 颜色 → (abbr, 客户码)
STONES = []
for i in range(1, 7):
    STONES.append((f"浅灰{i}号", f"LIGHTGREY{i}", f"TT0009004K{9066+i:07d}"))
for i in range(1, 7):
    STONES.append((f"深灰{i}号", f"DARKGREY{i}", f"TT0009005K{9072+i:07d}"))

def main():
    dry = "--dry-run" in sys.argv
    api = EN()
    print(f"模式: {'DRY-RUN' if dry else 'REAL'}")
    print(f"EN: {api.base}\n")

    for color, abbr, cust in STONES:
        old_code = f"KS0018-LSRBS-25cm-{color}"
        new_code = f"KS0018-LSRBS-25cm-{abbr}"
        print(f"=== {color} → {abbr} ===")

        # 1. 建新 abbr 编号物料
        if api.get("Item", new_code):
            print(f"  SKIP: {new_code} 已存在")
        elif dry:
            print(f"  DRY-RUN: 建 {new_code}")
        else:
            code, res = api.post("Item", {
                "item_code": new_code, "item_name": f"印花石头抱枕-丽丝绒白色-25cm-{color}",
                "item_group": "印花石头抱枕", "stock_uom": "个",
                "is_stock_item": 1, "include_item_in_manufacturing": 1, "is_sales_item": 1,
                "variant_of": "KS0018", "has_variants": 0,
                "attributes": [
                    {"attribute": "印花石头抱枕面料", "attribute_value": "丽丝绒白色"},
                    {"attribute": "印花石头抱枕尺寸", "attribute_value": "25cm"},
                    {"attribute": "印花石头抱枕颜色", "attribute_value": color},
                ],
            })
            print(f"  {'OK' if code==200 else 'FAIL('+str(code)+') '+json.dumps(res,ensure_ascii=False)[:200]}: 建 {new_code}")

        # 2. valuation + Item Price
        if dry:
            print(f"  DRY-RUN: valuation/price {new_code}=7.85")
        else:
            if api.get("Item", new_code, params={"fields": json.dumps(["valuation_rate"])}).get("valuation_rate") != 7.85:
                api.put("Item", new_code, {"valuation_rate": 7.85})
                print(f"  OK: valuation {new_code}=7.85")
            # Item Price
            ips = api.s.get(f"{api.base}/api/resource/Item Price", params={
                "filters": json.dumps([["Item Price","item_code","=",new_code],["Item Price","price_list","=","标准采购"]]),
                "limit_page_length": "3"}, timeout=60).json().get("data", [])
            if not ips:
                api.post("Item Price", {"item_code": new_code, "price_list": "标准采购", "price_list_rate": 7.85, "currency": "CNY"})
                print(f"  OK: ItemPrice {new_code}=7.85")
            else:
                print(f"  SKIP: ItemPrice 已存在 {new_code}")

        # 3. 自引用 BOM
        r = api.s.get(f"{api.base}/api/resource/BOM", params={
            "filters": json.dumps([["BOM","item","=",new_code]]), "limit_page_length": "3"}, timeout=60)
        if r.json().get("data"):
            print(f"  SKIP: BOM 已存在 {new_code}")
        elif dry:
            print(f"  DRY-RUN: 建BOM {new_code}")
        else:
            code, res = api.post("BOM", {
                "item": new_code, "company": "FZH", "uom": "个", "quantity": 1.0,
                "is_active": 1, "is_default": 1, "rm_cost_as_per": "Price List",
                "buying_price_list": "标准采购", "currency": "CNY",
                "items": [{"item_code": new_code, "qty": 1.0, "uom": "个"}],
            })
            if code == 200:
                api.put("BOM", res.get("data",{}).get("name",""), {"docstatus": 1})
                print(f"  OK: 建BOM+提交 {new_code}")
            else:
                print(f"  FAIL({code}): 建BOM {new_code} {json.dumps(res,ensure_ascii=False)[:200]}")

        # 4. 迁移客户码: 旧 → 新
        if dry:
            print(f"  DRY-RUN: 迁移客户码 {cust} {old_code}→{new_code}")
        else:
            # remove from old
            od = api.get("Item", old_code, params={"fields": json.dumps(["customer_items"])})
            old_custs = [c for c in od.get("customer_items", []) if c.get("ref_code") != cust]
            api.put("Item", old_code, {"customer_items": [{"customer_group": c.get("customer_group","美国公司"), "ref_code": c.get("ref_code")} for c in old_custs]})
            # add to new
            nd = api.get("Item", new_code, params={"fields": json.dumps(["customer_items"])})
            new_custs = [{"customer_group": c.get("customer_group","美国公司"), "ref_code": c.get("ref_code")} for c in nd.get("customer_items", [])]
            new_custs.append({"customer_group": "美国公司", "ref_code": cust})
            code, res = api.put("Item", new_code, {"customer_items": new_custs})
            print(f"  {'OK' if code==200 else 'FAIL'}: 迁移客户码 {cust} → {new_code}")

        # 5. 禁用旧中文编号
        if dry:
            print(f"  DRY-RUN: 禁用 {old_code}")
        else:
            od = api.get("Item", old_code)
            if not od.get("disabled"):
                code, res = api.put("Item", old_code, {"disabled": 1})
                print(f"  {'OK' if code==200 else 'FAIL'}: 禁用 {old_code}")
            else:
                print(f"  SKIP: {old_code} 已禁用")

    print("\n完成。")

if __name__ == "__main__":
    main()
