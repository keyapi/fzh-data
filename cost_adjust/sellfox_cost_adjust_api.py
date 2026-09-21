# -*- coding: utf-8 -*-
"""赛狐「成本补录单」私有接口客户端（读 + 写）。

术语：本文的**私有接口**指 undocumented internal API（业界亦称 shadow API 影子 API）——
厂商自己前端在用、但未写进公开 OpenAPI 的端点。它和公开 OpenAPI 是两套完全不同的调用面：
鉴权不同（站点 cookie vs OAuth2 签名/Bearer）、权限不同、稳定性不同（**私有接口无版本承诺**）。
不要把两者混为一谈——同一个功能常常「公开 OpenAPI 没有、私有接口有」。
判据与用词约定见 docs/research/2026-09-18-sellfox-private-api-terminology.md。

为什么不走公开 OpenAPI：成本补录单在公开 OpenAPI 下**只有查询一个端点**
（`/api/fba/cost/adjustment/pageList.json`，且 `status`/`warehouseIds`/`createTime`/
`searchField=sku` 等过滤字段会报 `40021 访问的接口暂无权限`）。创建与审核是**私有接口**，
必须带赛狐站点 cookie，因此本模块通过 Playwright 的 ``page.request`` 调用。

端点契约（2026-09-18 生产实测）::

    读  GET  /api/fba/cost/adjustment/getItemsByNoAndSearchValue.json?adjustType=&no=
        GET  /api/fba/cost/adjustment/count.json
        GET  /api/fba/cost/adjustment/detailByRelationNo.json?relationNo=&adjustType=
        POST /api/fba/cost/adjustment/pageList.json
    写  POST /api/fba/cost/adjustment/create.json   body = 完整 items 回填后整坨
        POST /api/fba/cost/adjustment/audit.json    body = [adjustId, ...]
        POST /api/fba/cost/adjustment/delete.json   body = [adjustId, ...]
        POST /api/fba/cost/adjustment/reject.json   body = {"adjustId": N, "reason": "..."}

未解析：``edit.json`` / ``updateRemark.json`` —— 接口存在（打包产物里有），但成本补录单
页面没有触发入口，payload 未知。疑似供「库存调整单」页面复用。

用法::

    uv run python sellfox_cost_adjust_api.py --no OWS294A9T700030 --sku test001-white --new-cost 1.48
    uv run python sellfox_cost_adjust_api.py ... --apply        # 真建单并审核

默认 dry-run：只打印将要发送的 payload 与变更预览，不发写请求。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WEB_ROOT = REPO_ROOT / "web_automation"

sys.path.insert(0, str(WEB_ROOT / "legacy-compatible"))

API = "https://www.sellfox.com/api/fba/cost/adjustment"

# 成本补录单的「关联单据类型」。文档只列到 5（发货单/采购单/调拨单/其他入库/库存明细），
# 实测海外仓备货单是 6。
ADJUST_TYPE_OVERSEA_RESTOCK = 6

LOGIN_URL_FRAGMENT = "login"
DEFAULT_PROFILE = WEB_ROOT / "sellfox-profile"


class SellfoxError(RuntimeError):
    """赛狐返回 code != 0，或响应形状不符合预期。"""


def _num(value: float) -> float | int:
    """整数值去掉小数点 —— UI 发的是 ``1500`` 而不是 ``1500.0``，照抄以免上游比较类型。"""
    return int(value) if float(value).is_integer() else value


class CostAdjustClient:
    """成本补录单客户端。所有调用都借 Playwright 的 page.request 走浏览器登录态。"""

    def __init__(self, page: Any) -> None:
        self.page = page

    # ── 底层 ────────────────────────────────────────────────

    def _request(self, method: str, path: str, *, params: str = "", data: Any = None) -> Any:
        url = f"{API}{path}{params}"
        kwargs: dict[str, Any] = {"headers": {"Content-Type": "application/json"}}
        if data is not None:
            kwargs["data"] = data
        resp = getattr(self.page.request, method)(url, **kwargs)
        if resp.status != 200:
            raise SellfoxError(f"{method.upper()} {path} -> HTTP {resp.status}")
        payload = resp.json()
        if payload.get("code") != 0:
            raise SellfoxError(
                f"{method.upper()} {path} -> code={payload.get('code')} msg={payload.get('msg')}"
            )
        return payload.get("data")

    def _get(self, path: str, params: str = "") -> Any:
        return self._request("get", path, params=params)

    def _post(self, path: str, data: Any) -> Any:
        return self._request("post", path, data=data)

    # ── 读 ──────────────────────────────────────────────────

    def count(self) -> dict:
        """各状态计数：{all, to_audit, has_passed, has_rejected}。"""
        return self._get("/count.json")

    def list_orders(self, **filters: Any) -> dict:
        """列表查询。注意公开 OpenAPI 下多数过滤字段无权限，走浏览器会话则不受限。"""
        body = {"pageNo": "1", "pageSize": "20"}
        body.update({k: str(v) for k, v in filters.items()})
        return self._post("/pageList.json", body)

    def _items_data(self, no: str, adjust_type: int) -> dict:
        """按来源单据号拉取信封 —— 顶层带 warehouseId/targetWarehouseId，rows 是商品行。"""
        params = (
            "?fullCid=&searchField=&searchValue=&searchType=exact&userIds=&isGroups="
            f"&brandIdList=&state=&pageNo=1&pageSize=100&adjustType={adjust_type}&no={no}"
        )
        return self._get("/getItemsByNoAndSearchValue.json", params) or {}

    def items_by_order_no(
        self, no: str, adjust_type: int = ADJUST_TYPE_OVERSEA_RESTOCK
    ) -> list[dict]:
        """按来源单据号拉可补录的商品明细（``no`` = 海外仓备货单号）。

        返回的每行都带 ``perPurchase``（当前采购单价）与 ``goods``（数量）。
        """
        return self._items_data(no, adjust_type).get("rows") or []

    def items_by_relation_no(
        self, relation_no: str, adjust_type: int = ADJUST_TYPE_OVERSEA_RESTOCK
    ) -> list[dict]:
        """按关联单号查已存在的补录单明细。"""
        return (
            self._get(
                "/detailByRelationNo.json",
                f"?relationNo={relation_no}&adjustType={adjust_type}",
            )
            or []
        )

    # ── 写 ──────────────────────────────────────────────────

    def build_payload(
        self,
        no: str,
        new_costs: dict[str, float],
        adjust_type: int = ADJUST_TYPE_OVERSEA_RESTOCK,
        reason: str = "",
    ) -> dict:
        """按「读取结果回填」构造 create 的请求体。

        必须整坨回填 —— 有几个字段不能自己造：``warehouseId``（虚拟仓库）与
        ``targetWarehouseId``（真实海外仓）是两个不同仓库；``newPerFee`` 传 ``0``
        而 ``oriPerFee`` 是 ``null``；``oriTotalPerFee`` 是**空字符串**不是 ``0``。
        2026-09-18 实测：本函数输出与 UI 实际发出的请求体逐字段一致。
        """
        data = self._items_data(no, adjust_type)
        rows = data.get("rows") or []
        if not rows:
            raise SellfoxError(f"单据 {no} 下没有可补录的商品（adjustType={adjust_type}）")

        by_sku = {r["commoditySku"]: r for r in rows}
        missing = set(new_costs) - set(by_sku)
        if missing:
            raise SellfoxError(f"单据 {no} 下找不到这些 SKU: {sorted(missing)}")

        head = {
            "currency": data.get("currency") or rows[0]["currency"],
            "currencyIcon": data.get("currencyIcon") or rows[0]["currencyIcon"],
            "relationNo": no,
            "adjustType": adjust_type,
            "warehouseId": data["warehouseId"],
            "targetWarehouseId": data["targetWarehouseId"],
        }
        items = []
        for sku, spec in by_sku.items():
            if sku not in new_costs:
                continue
            per = spec["perPurchase"]
            qty = spec["goods"]
            new = new_costs[sku]
            items.append(
                {
                    "id": spec["id"],
                    "shopId": spec["shopId"],
                    "amazonShipmentId": spec.get("amazonShipmentId"),
                    "sellerSku": spec.get("sellerSku"),
                    "fnSku": spec.get("fnSku"),
                    "shippingOrderItemId": spec["id"],
                    "shippingOrderId": spec["shippingOrderId"],
                    "commodityId": spec["commodityId"],
                    "commodityName": spec["commodityName"],
                    "commoditySku": sku,
                    "shipCount": qty,
                    "oriPurchaseCost": per,
                    "newPurchaseCost": new,
                    "oriPerFee": spec.get("perFee"),
                    "childSkus": spec.get("childSkus"),
                    "newPerFee": 0,
                    "oriTotalPurchaseCost": _num(per * qty),
                    "newTotalPurchaseCost": _num(new * qty),
                    "oriTotalPerFee": "",
                    "newTotalPerFee": "",
                    "auxFee": "",
                    "currency": spec["currency"],
                    "currencyIcon": spec["currencyIcon"],
                    "platform": spec["platform"],
                }
            )
        return {**head, "reason": reason, "items": items}

    def create(self, payload: dict) -> dict:
        """建单。返回 {adjustSn, id, status, ...}，状态为 ``to_audit``。"""
        return self._post("/create.json", payload)

    def audit(self, adjust_ids: list[int]) -> dict:
        """批量审核通过 —— 生效并改动库存成本。body 是裸的 adjustId 数组。"""
        return self._post("/audit.json", adjust_ids)

    def delete(self, adjust_ids: list[int]) -> dict:
        """批量删除（仅待审核可删）。body 同 audit。"""
        return self._post("/delete.json", adjust_ids)

    def reject(self, adjust_id: int, reason: str) -> dict:
        """驳回。body 是对象而非数组 —— {adjustId, reason}。"""
        return self._post("/reject.json", {"adjustId": adjust_id, "reason": reason})

    # ── 编排 ────────────────────────────────────────────────

    def change_cost(
        self,
        no: str,
        new_costs: dict[str, float],
        *,
        adjust_type: int = ADJUST_TYPE_OVERSEA_RESTOCK,
        reason: str = "",
        apply: bool = False,
    ) -> dict:
        """端到端：读明细 → 建单 → （apply 时）审核生效。

        ``apply=False`` 时只建单不审核 —— 单据停在「待审核」，**不改动库存成本**。
        """
        payload = self.build_payload(no, new_costs, adjust_type, reason)
        created = self.create(payload)
        result = {"created": created, "payload": payload}
        if apply:
            adjust_id = int(created["id"])
            result["audit"] = self.audit([adjust_id])
        return result


def preview(payload: dict) -> str:
    """把将发送的变更渲染成人读的对照表。"""
    lines = [
        f"单据 {payload['relationNo']}  adjustType={payload['adjustType']}  "
        f"仓库 {payload['warehouseId']} → {payload['targetWarehouseId']}",
    ]
    total = 0.0
    for it in payload["items"]:
        delta = it["newTotalPurchaseCost"] - it["oriTotalPurchaseCost"]
        total += delta
        lines.append(
            f"  {it['commoditySku']:<40} {it['shipCount']:>6} 件  "
            f"{it['oriPurchaseCost']:.4f} → {it['newPurchaseCost']:.4f}  "
            f"金额差额 {delta:+.2f}"
        )
    lines.append(f"  合计金额差额 {total:+.2f}")
    return "\n".join(lines)


def wait_for_login(page: Any, timeout_s: int = 300) -> None:
    """SPA 登录页轮询。已登录会立刻返回。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        url = page.url
        if url and LOGIN_URL_FRAGMENT not in url and "sellfox.com" in url:
            return
        time.sleep(2)
    raise SystemExit(f"等待赛狐登录超时（{timeout_s}s）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no", required=True, help="来源单据号（海外仓备货单号）")
    parser.add_argument("--sku", required=True, help="要改的 SKU")
    parser.add_argument("--new-cost", type=float, required=True, help="新的采购单价")
    parser.add_argument("--adjust-type", type=int, default=ADJUST_TYPE_OVERSEA_RESTOCK)
    parser.add_argument("--reason", default="")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="浏览器登录态目录")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--apply", action="store_true", help="真建单并审核（默认 dry-run）")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    from browser_launch import launch_persistent

    with sync_playwright() as p:
        context = launch_persistent(p, args.profile, headless=args.headless)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.sellfox.com/amzup-web-main/web/fba/adjust/index.html")
        wait_for_login(page)

        client = CostAdjustClient(page)
        payload = client.build_payload(
            args.no, {args.sku: args.new_cost}, args.adjust_type, args.reason
        )
        print(preview(payload))
        print("\n[create payload]")
        print(json.dumps(payload, ensure_ascii=False))

        if not args.apply:
            print("\n[dry-run] 未发送写请求。加 --apply 建单并审核。")
            context.close()
            return 0

        created = client.create(payload)
        print(f"\n[建单] {created.get('adjustSn')} id={created.get('id')} status={created.get('status')}")
        audit = client.audit([int(created["id"])])
        print(f"[审核] {json.dumps(audit, ensure_ascii=False)}")
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
