# -*- coding: utf-8 -*-
"""赛狐「海外仓备货单」改单个头程费用 —— 私有接口客户端。

背景：库存的「单位费用」由批次的头程驱动力决定，而**头程（单位费用）无法走成本补录单**
（海外仓备货单类型不许填单位费用）。唯一路径是改备货单的「单个头程费用」——
前端只有页面点击，Excel 也没有对应字段（`pickingOrderUpdateTemplate` 只覆盖
物流商/分摊方式/日期/备注，无任何费用字段）。

故走**私有接口**（undocumented internal API，业界亦称 shadow API）::

    GET  /api/oversea/detail.json?id=<pickId>   → 整个单据对象（含 items[]）
    改   items[].headFee / logisticsCost / totalHeadFee
    POST /api/oversea/edit.json                 → 整坨发回去

要点：
  * **派生值要一起改**：`logisticsCost` 与 `totalHeadFee` = `headFee × quantity`，
    格式是两位小数字符串（如 ``"250.00"``）。
  * `items[].singleLogisticsCost` 是**服务端派生**：照着旧值发回去，服务端仍会按新
    `headFee` 重算（实测 0.2 → 0.25）。别手动改它。
  * 生效口径：库存「单位费用」按**剩余数量**加权重算。实测把某批次 headFee 0.20→0.25，
    该批次剩 997 件（原 1000），`(997×0.25 + 1000×1.0)/1997 = 0.6256` —— 与实际完全吻合。
  * payload 是 `detail.json` 的**原样回填** —— 上百个字段（shelfIn / logistics[] /
    customInfo / 装箱规格…）都要带上，少传很可能被当成全量覆盖。
  * 改头程**按批次生效**，不是单单据：同一批次若被其他单据引用，那些单据的成本也会同步变。
  * `pickId` **不在 URL 上传**：app 靠 localStorage
    （`EditStockOrder_edit` / `DetailStockOrder_detail` 里的 `{"params":{"id":N}}`）取目标单。
    但走 API 时我们直接带 `?id=`，不受此影响。

用法::

    uv run python sellfox_restock_headfee_api.py --pick-id 11498 --sku test001-white --new-fee 0.25
    uv run python sellfox_restock_headfee_api.py ... --apply     # 真改

默认 dry-run：只打印将要发送的变更摘要，不发写请求。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent / "web_automation"

API = "https://www.sellfox.com/api/oversea"
BATCH_API = "https://www.sellfox.com/api/overseaBatch/page.json"
LIST_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/stockOrder/index.html"
DEFAULT_PROFILE = WEB_ROOT / "sellfox-profile"

# edit.json 的耗时与明细行数**超线性**增长：1 行瞬时，500 行实测 16~18 秒。
# Playwright page.request 默认超时 30s，行数再多就会超时 —— 必须显式放宽。
READ_TIMEOUT_MS = 60_000
EDIT_TIMEOUT_MS = 300_000
BIG_ORDER_ITEMS = 200


class SellfoxError(RuntimeError):
    """赛狐返回 code != 0，或响应形状不符合预期。"""


class RestockHeadFeeClient:
    """海外仓备货单头程客户端。所有调用借 Playwright 的 page.request 走浏览器登录态。"""

    def __init__(self, page: Any) -> None:
        self.page = page

    def _get(self, path: str) -> Any:
        resp = self.page.request.get(f"{API}{path}", timeout=READ_TIMEOUT_MS)
        if resp.status != 200:
            raise SellfoxError(f"GET {path} -> HTTP {resp.status}")
        payload = resp.json()
        if payload.get("code") != 0:
            raise SellfoxError(f"GET {path} -> code={payload.get('code')} msg={payload.get('msg')}")
        return payload.get("data")

    def _post_abs(self, url: str, body: Any, timeout_ms: int = READ_TIMEOUT_MS) -> Any:
        resp = self.page.request.post(
            url, {"data": body, "headers": {"Content-Type": "application/json"}, "timeout": timeout_ms}
        )
        if resp.status != 200:
            raise SellfoxError(f"POST {url} -> HTTP {resp.status}")
        payload = resp.json()
        if payload.get("code") != 0:
            raise SellfoxError(f"POST {url} -> code={payload.get('code')} msg={payload.get('msg')}")
        return payload.get("data")

    def _post(self, path: str, body: Any, timeout_ms: int = READ_TIMEOUT_MS) -> Any:
        return self._post_abs(f"{API}{path}", body, timeout_ms)

    # ── 读 ──────────────────────────────────────────────────

    def detail(self, pick_id: int) -> dict:
        """整张备货单。``items[]`` 带 ``headFee``（单个头程费用）。"""
        return self._get(f"/detail.json?id={pick_id}") or {}

    def list_orders(self, sku: str, status: str = "", page_size: int = 50) -> list[dict]:
        """按 SKU 查备货单。

        注意 ``searchType`` 必须传 ``'sku'`` —— 传 ``commoditySku`` 等其它值会被**静默忽略**，
        返回未过滤的全量列表（一度因此误判"搜不到"）。``data.totalSize`` 也不可信，用 ``rows``。
        """
        body = {
            "fromIds": "", "toIds": "", "createIds": "", "dateType": "createDate",
            "status": status, "startDate": "2020-01-01",
            "endDate": time.strftime("%Y-%m-%d"), "searchMode": "exact",
            "searchType": "sku", "searchContent": sku, "searchMoreList": [],
            "logisticIds": "", "logistics": "", "orderStatus": "", "packingStatus": [],
            "receiveMode": None, "shopIds": [], "overseaMode": "",
            "pageSize": page_size, "pageNo": 1,
        }
        return (self._post("/page.json", body) or {}).get("rows") or []

    # ── 批次构成（判断改动覆盖面） ──────────────────────────

    def in_stock_batches(self, sku: str) -> list[dict]:
        """该 SKU 的**在库批次**构成（``goodsAva > 0``）。

        改某张备货单的头程，**只影响它自己那个批次**，加权单位费用的变化量是
        ``ΔheadFee × (该批次可用量 / 该SKU总可用量)``。所以改之前先看构成，
        否则会误以为「改一张单就能把整个 SKU 的单位费用拉到目标值」。

        批次 ``type``：5=海外仓备货单；3=库存调整-**增加**（**自建独立批次，不跟随备货单**）；
        4=库存调整-**减少**（引用已有批次，共享成本，会跟随）。
        """
        body = {
            "warehouseIds": "", "dateType": "", "startDate": "2024-01-01",
            "endDate": "2099-12-31", "searchType": "commoditySku", "searchContent": sku,
            "type": [], "brandIds": [], "state": "",
            "pageSize": 200, "pageNo": 1, "orderBy": "", "desc": "",
        }
        rows = self._post_abs(f"{BATCH_API}", body) or {}
        return [r for r in (rows.get("rows") or [])
                if r.get("commoditySku") == sku and (r.get("goodsAva") or 0) > 0]

    @staticmethod
    def project_unit_fee(batches: list[dict], source_no: str, new_fee: float) -> dict:
        """预测改 ``source_no`` 的头程后，加权单位费用会变成多少。"""
        total = sum(b.get("goodsAva") or 0 for b in batches) or 1
        before = sum((b.get("goodsAva") or 0) * (b.get("transportCost") or 0) for b in batches) / total
        after = sum(
            (b.get("goodsAva") or 0) * (new_fee if b.get("oriNo") == source_no else (b.get("transportCost") or 0))
            for b in batches
        ) / total
        hit = sum(b.get("goodsAva") or 0 for b in batches if b.get("oriNo") == source_no)
        return {"total": total, "covered": hit, "share": round(hit / total, 4),
                "unitFeeBefore": round(before, 4), "unitFeeAfter": round(after, 4)}

    # ── 写 ──────────────────────────────────────────────────

    def build_payload(self, pick_id: int, sku: str, new_fee: float) -> tuple[dict, dict]:
        """读取整单 → 改目标 SKU 的 headFee 及派生值。返回 (payload, 变更摘要)。"""
        order = self.detail(pick_id)
        items = order.get("items") or []
        target = next((i for i in items if i.get("commoditySku") == sku), None)
        if target is None:
            have = [i.get("commoditySku") for i in items]
            raise SellfoxError(f"备货单 {pick_id} 里没有 SKU {sku}（现有: {have}）")

        qty = target.get("quantity") or target.get("signNum") or 0
        old_fee = target.get("headFee")
        total = f"{new_fee * qty:.2f}"
        target["headFee"] = new_fee
        # 派生值：UI 的「总头程费用 / 物流费用」= 单价 × 数量，两位小数字符串
        target["logisticsCost"] = total
        target["totalHeadFee"] = total

        summary = {
            "pickSn": order.get("pickSn"),
            "pickId": order.get("id"),
            "sku": sku,
            "quantity": qty,
            "oldHeadFee": old_fee,
            "newHeadFee": new_fee,
            "newTotalHeadFee": total,
        }
        if len(items) >= BIG_ORDER_ITEMS:
            summary["warning"] = (
                f"该单有 {len(items)} 个明细行，edit.json 耗时随行数超线性增长"
                f"（500 行实测约 18 秒），提交请留足时间、不要并发"
            )
        return order, summary

    def edit(self, payload: dict) -> Any:
        """整坨提交。改头程按**批次**生效。

        耗时随明细行数超线性增长（500 行实测 16~18s），故用 ``EDIT_TIMEOUT_MS``。
        """
        return self._post("/edit.json", payload, timeout_ms=EDIT_TIMEOUT_MS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pick-id", type=int, required=True, help="备货单 id（detail.json 的 id，非单号）")
    parser.add_argument("--sku", required=True)
    parser.add_argument("--new-fee", type=float, required=True, help="新的单个头程费用")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--apply", action="store_true", help="真提交（默认 dry-run）")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    from browser_launch import launch_persistent

    with sync_playwright() as p:
        context = launch_persistent(p, args.profile, headless=args.headless)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LIST_URL)
        for _ in range(150):
            if "login" not in page.url.lower() and "sellfox.com" in page.url:
                break
            time.sleep(2)

        client = RestockHeadFeeClient(page)

        payload, summary = client.build_payload(args.pick_id, args.sku, args.new_fee)
        batches = client.in_stock_batches(args.sku)
        projection = client.project_unit_fee(batches, summary["pickSn"], args.new_fee)

        print("[批次构成]")
        for b in batches:
            print(f"  {b.get('oriNo'):<20} type={b.get('type')} batchNo={b.get('batchNo')} "
                  f"可用={b.get('goodsAva'):<6} 采购单价={b.get('inventoryCost')} 头程={b.get('transportCost')}")
        print(f"[预测] 本单批次占 {projection['covered']}/{projection['total']} "
              f"({projection['share']}) → 单位费用 {projection['unitFeeBefore']} → {projection['unitFeeAfter']}")
        print("[变更摘要] " + json.dumps(summary, ensure_ascii=False, indent=1))
        print(f"[payload] items {len(payload.get('items') or [])} 条 / {len(json.dumps(payload))} 字节")

        if not args.apply:
            print("[dry-run] 未提交。加 --apply 真改（会改动库存单位费用）。")
            context.close()
            return 0

        client.edit(payload)
        after = client.detail(args.pick_id)
        item = next(i for i in (after.get("items") or []) if i.get("commoditySku") == args.sku)
        print(f"[生效] headFee={item.get('headFee')} logisticsCost={item.get('logisticsCost')} "
              f"totalHeadFee={item.get('totalHeadFee')}")
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
