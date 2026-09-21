"""
probe_batches.py
查「某个 SKU 的库存是哪些单据来的」——为「按仓库+SKU 改成本」定位目标单据

为什么需要它：
  成本补录单只能**按单据**改，海外仓备货单的头程也只能**逐单**改。
  但一个 (仓库, SKU) 往往有几十上百张历史单据，绝大多数货早已出完。
  真正要改的，是**货还在库里的那些批次**对应的来源单。

数据来源：海外仓批次  `POST /api/overseaBatch/page.json`
  - 参数: searchType=commoditySku + searchContent=<SKU> + 大日期范围
    （注意：不是 commoditySku 参数，那样不会过滤）
  - 关键字段: oriNo(来源单号) / goodsAva(可用量) / inventoryCost(批次采购成本)
              / transportCost(批次头程费用) / type / warehouseName
  - type=5 且 oriNo 以 OWS 开头 → 海外仓备货单（可改头程、可做成本补录-按单据）
    其它（AD… = 库存调整 等）→ 不是备货单，改成本走不了备货单那条路

用法:
  uv run python probe_batches.py KS0248-DM-60-WHITE
  uv run python probe_batches.py test001-white KS0248-DM-60-WHITE
  uv run python probe_batches.py --sku-file 待查SKU.txt
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
CLICK_BASED = SCRIPT_DIR.parent / "web_automation" / "click-based"
sys.path.insert(0, str(CLICK_BASED))

from sellfox_import_cost_adjust import (  # noqa: E402
    LOGIN_URL, PROFILE_DIR, _dismiss_blocking_dialogs, is_logged_in, try_auto_login, wait_for_login,
)

PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/batchManagement/index.html"
BATCH_API = "https://www.sellfox.com/api/overseaBatch/page.json"

# 批次类型 → 单据性质。5=海外仓备货单（实测「海外仓批次」页 类型 列显示「海外仓备货」）
STOCK_ORDER_TYPE = 5
PAGE_SIZE = 200
MAX_PAGES = 12


def fetch_batches(page, sku: str) -> list[dict]:
    rows, seen = [], set()
    for p in range(1, MAX_PAGES + 1):
        resp = page.request.post(
            BATCH_API,
            data=json.dumps({
                "warehouseIds": "", "dateType": "", "startDate": "2024-01-01", "endDate": "2099-12-31",
                "searchType": "commoditySku", "searchContent": sku,
                "type": [], "brandIds": [], "state": "",
                "pageSize": PAGE_SIZE, "pageNo": p, "orderBy": "", "desc": "",
            }, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
            timeout=30000,
        )
        j = resp.json()
        if j.get("code") != 0:
            print(f"    [!] 批次接口返回 code={j.get('code')} msg={j.get('msg')}")
            break
        batch = [r for r in ((j.get("data") or {}).get("rows") or []) if r.get("commoditySku") == sku]
        # 去重（按批次 id），避免分页边界重复
        new = [r for r in batch if r.get("id") not in seen]
        for r in new:
            seen.add(r.get("id"))
        rows.extend(new)
        if len((j.get("data") or {}).get("rows") or []) < PAGE_SIZE:
            break
    return rows


def summarize(sku: str, rows: list[dict]) -> dict:
    in_stock = [r for r in rows if (r.get("goodsAva") or 0) > 0]
    groups: dict[tuple, dict] = {}
    for r in in_stock:
        key = (r.get("oriNo"), r.get("warehouseName"), r.get("type"))
        g = groups.setdefault(key, {
            "oriNo": r.get("oriNo"), "wh": r.get("warehouseName"), "type": r.get("type"),
            "qty": 0, "cost_sum": 0.0, "fee_sum": 0.0, "batches": 0,
        })
        q = r.get("goodsAva") or 0
        g["qty"] += q
        g["cost_sum"] += (r.get("inventoryCost") or 0) * q
        g["fee_sum"] += (r.get("transportCost") or 0) * q
        g["batches"] += 1

    orders = []
    for g in groups.values():
        q = g["qty"]
        orders.append({
            "来源单号": g["oriNo"], "仓库": g["wh"], "类型": g["type"],
            "是否备货单": g["type"] == STOCK_ORDER_TYPE or str(g["oriNo"] or "").startswith("OWS"),
            "批次数": g["batches"], "可用量": q,
            "采购单价": round(g["cost_sum"] / q, 4) if q else None,
            "单位费用": round(g["fee_sum"] / q, 4) if q else None,
        })
    orders.sort(key=lambda o: -o["可用量"])

    tq = sum(o["可用量"] for o in orders)
    tc = sum(o["可用量"] * o["采购单价"] for o in orders)
    tf = sum(o["可用量"] * o["单位费用"] for o in orders)
    return {
        "sku": sku, "批次总数": len(rows), "有货批次数": len(in_stock), "可用总量": tq,
        "加权采购单价": round(tc / tq, 4) if tq else None,
        "加权单位费用": round(tf / tq, 4) if tq else None,
        "单据": orders,
        "备货单来源可用量": sum(o["可用量"] for o in orders if o["是否备货单"]),
    }


def print_report(s: dict):
    print(f"\n{'=' * 72}")
    print(f"SKU: {s['sku']}")
    print(f"{'=' * 72}")
    if not s["可用总量"]:
        print(f"  批次总数 {s['批次总数']}，但没有任何有货批次（可用量=0）")
        return
    print(f"  批次总数 {s['批次总数']}，有货批次 {s['有货批次数']}，可用总量 {s['可用总量']}")
    print(f"  加权采购单价 {s['加权采购单价']}   加权单位费用 {s['加权单位费用']}")
    print(f"\n  {'来源单号':<20}{'仓库':<10}{'type':<6}{'备货单':<8}{'批次':<6}{'可用量':<8}{'采购单价':<10}{'单位费用':<10}")
    for o in s["单据"]:
        print(f"  {str(o['来源单号']):<20}{str(o['仓库']):<10}{str(o['类型']):<6}"
              f"{'是' if o['是否备货单'] else '否':<8}{o['批次数']:<6}{o['可用量']:<8}"
              f"{str(o['采购单价']):<10}{str(o['单位费用']):<10}")
    non_so = [o for o in s["单据"] if not o["是否备货单"]]
    if non_so:
        print(f"\n  [!] 有 {len(non_so)} 个来源不是海外仓备货单（合计可用 "
              f"{sum(o['可用量'] for o in non_so)} 件）——这部分"
              f"{'无法' if not [o for o in s['单据'] if o['是否备货单']] else '只能'}用备货单那条路改头程。")
    else:
        print("\n  [OK] 有货批次全部来自海外仓备货单，可直接按这些单改采购成本/头程。")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--sku-file" in sys.argv:
        idx = sys.argv.index("--sku-file")
        src = Path(sys.argv[idx + 1])
        skus = [l.strip() for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        skus = args
    if not skus:
        print(__doc__)
        return

    headless = "--headless" in sys.argv
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=headless)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(3000)
        if not is_logged_in(page):
            print("[!] 未登录 → 打开登录页")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_timeout(2000)
            if not try_auto_login(page) and not wait_for_login(page):
                print("FAILURE_CODE=AUTH_FAILED")
                context.close()
                return
        _dismiss_blocking_dialogs(page)

        for sku in skus:
            print(f"\n查询 {sku} ...")
            rows = fetch_batches(page, sku)
            print_report(summarize(sku, rows))

        context.close()


if __name__ == "__main__":
    main()
