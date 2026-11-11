"""整单齐套（opt-in，蓝图 §7.2）：按成品 BOM 展开必需配套件，逐件算可信可用量。

权威来源 = ERPNext 的**成品 BOM**（`BOM.items`），**不**靠 `KS`/`PK#`/`ND#` 前缀猜（蓝图 §7.2）。
三种 BOM 模式：全 BOM（皮壳+内胆）/ 简化（→`SXBZPK#`）/ 自引用（无真实组件）；
后两者展开不出真实配套件，标「无法展开」，**不**报齐套。

可信可用量 = 组件**已完工量**（工序卡第一道工序，复用引擎口径）+ **工厂侧库存**。
工厂侧 = 仓库名含公司（FZH）、排除「到货仓」（国外到货仓库存不算齐套可用量，蓝图 §5/§13）。
⚠ 这是默认口径，如需改（例如含国外仓）由业务确认后调整。
"""
from __future__ import annotations

import time

from item_shipment_status import (chunks, get_single, jobcards_by_wo, num,
                                  op_progress, paginated_get)

BOM_FIELDS = ["name", "item", "quantity"]
BIN_FIELDS = ["item_code", "actual_qty", "warehouse"]

# 工厂侧仓：含公司后缀且不含「到货仓」（到货仓 = 国外到货，不算齐套可用量）
_ARRIVAL = "到货仓"


def finished_item(ordered_item: str) -> str:
    """订单行物料 → 成品码：剥皮壳/内胆前缀；已是成品则原样。"""
    s = ordered_item or ""
    for pre in ("PK#", "DKND#", "ND#"):
        if s.startswith(pre):
            return s[len(pre):]
    return s


def fetch_bom(finished: str, base_url, key, secret):
    """返回 (mode, components)。mode ∈ full | simplified | self_ref | none。"""
    rows = paginated_get(
        "BOM", base_url, key, secret,
        [["item", "=", finished], ["is_active", "=", 1], ["is_default", "=", 1], ["docstatus", "=", 1]],
        BOM_FIELDS, fallback_fields=["name", "item"], label="BOM")
    if not rows:
        return "none", []
    doc = get_single("BOM", rows[0]["name"], base_url, key, secret)
    comps = [{"item_code": it.get("item_code"), "qty": num(it.get("qty")) or 1.0}
             for it in (doc.get("items") or []) if it.get("item_code")]
    if not comps:
        return "self_ref", []
    if all((c["item_code"] or "").startswith("SXBZ") for c in comps):
        return "simplified", comps
    return "full", comps


def component_supply(item_code, base_url, key, secret, sleep_s=0.15):
    """组件的可信可用量 = 已完工量（工序卡第一道工序）+ 工厂侧库存。"""
    from item_shipment_status import (fetch_job_cards, fetch_work_order_details,
                                      fetch_work_orders)

    wos = fetch_work_order_details(fetch_work_orders([item_code], base_url, key, secret),
                                   base_url, key, secret, sleep_s)
    jc_map = jobcards_by_wo(fetch_job_cards([w["name"] for w in wos], base_url, key, secret))
    produced = sum(op_progress(w, jc_map.get(w["name"], []))["done_qty"] for w in wos)

    bins = paginated_get("Bin", base_url, key, secret,
                         [["item_code", "=", item_code], ["actual_qty", "!=", 0]],
                         BIN_FIELDS, fallback_fields=["item_code", "actual_qty"], label="Bin")
    factory_stock = sum(num(b.get("actual_qty")) for b in bins
                        if _ARRIVAL not in (b.get("warehouse") or ""))
    foreign_stock = sum(num(b.get("actual_qty")) for b in bins
                        if _ARRIVAL in (b.get("warehouse") or ""))
    return {"produced": produced, "factory_stock": factory_stock, "foreign_stock": foreign_stock,
            "supply": produced + factory_stock}


def evaluate_kit(lines, base_url, key, secret, sleep_s=0.15):
    """给每条履约行算齐套（就地写回 line.kit）。按成品码缓存，减少重复请求。"""
    bom_cache, supply_cache = {}, {}
    for ln in lines:
        fin = finished_item(ln.item_code)
        if fin not in bom_cache:
            mode, comps = fetch_bom(fin, base_url, key, secret)
            bom_cache[fin] = (mode, comps)
            time.sleep(sleep_s)
        mode, comps = bom_cache[fin]
        if mode != "full":
            ln.kit = {"finished": fin, "mode": mode, "components": [],
                      "ready_qty": None,
                      "note": {"none": "无成品 BOM，无法展开", "self_ref": "自引用 BOM（无真实组件），无法展开",
                               "simplified": "简化 BOM（→SXBZPK#，无工序），无法展开"}[mode]}
            continue
        detail, ready_equiv = [], []
        for c in comps:
            ic = c["item_code"]
            if ic not in supply_cache:
                supply_cache[ic] = component_supply(ic, base_url, key, secret, sleep_s)
                time.sleep(sleep_s)
            s = supply_cache[ic]
            ready_equiv.append(s["supply"] / c["qty"])
            detail.append({"item_code": ic, "qty": c["qty"], **s})
        ln.kit = {"finished": fin, "mode": "full", "components": detail,
                  "ready_qty": min(ready_equiv) if ready_equiv else 0.0,
                  "note": ""}
