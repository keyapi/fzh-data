# -*- coding: utf-8 -*-
"""Sellfox 调整单（数量调整）写链路验证。

实测链路（2026-09-18，`sellfox-main` 生产账号，无审批流）：

    库存明细 → createV2 建单 ──→ 直接完成并落库存（status=3）
                              └─ 有审批流时才停在待调整(2)，需 batchConfirmAdjust

三个反直觉点：

1. ``createV2`` 的响应 ``data`` 恒为 ``null``，**不回传 adjustNo**，必须回查 pageList。
2. 本账号没有审批流，``createV2`` 一步就把单推到「已完成」并扣减库存。
   因此 ``batchConfirmAdjust`` 在该单上会报「非待调整状态无法进行该操作」。
3. ``originId`` 必须来自《查询库存明细》的 ``id`` —— 调整单列表里
   ``warehouseItemId`` 恒为 null，无法从历史单据反推。

Dry-run by default; pass ``--apply`` to actually create.

默认目标：POLAND 主仓 (warehouseId=279841) 的 test001-white 扣减 3 个。
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from client import SellfoxClient, SellfoxConfig
from repo_root import find_main_root

INVENTORY_PATH = "/api/warehouseManage/warehouseItemList.json"
CREATE_PATH = "/api/ware/adjust/createV2.json"
CONFIRM_PATH = "/api/ware/adjust/batchConfirmAdjust.json"
LIST_PATH = "/api/ware/adjust/pageList.json"

DEFAULT_WAREHOUSE_ID = "279841"  # POLAND 主仓
DEFAULT_SKU = "test001-white"
DEFAULT_DELTA = -3


def make_client() -> SellfoxClient:
    root = find_main_root(start=Path(__file__).resolve().parent)
    return SellfoxClient(SellfoxConfig.from_env(root / ".env", root / "EN_API" / ".env"))


def find_item(client: SellfoxClient, warehouse_id: str, sku: str) -> dict[str, Any]:
    """库存明细 → 唯一条目（其 id 即 originId）。"""
    data = client.signed_post(
        INVENTORY_PATH,
        {
            "pageNo": "1",
            "pageSize": "50",
            "warehouseId": warehouse_id,
            "commoditySkus": [sku],
            "isHidden": "false",
        },
    )
    rows = (data or {}).get("rows") or []
    if len(rows) != 1:
        raise SystemExit(
            f"库存明细命中 {len(rows)} 条，期望 1 条 (warehouseId={warehouse_id} sku={sku})"
        )
    return rows[0]


def build_payload(warehouse_id: str, origin_id: str, delta: int) -> dict[str, Any]:
    return {
        "type": "0",
        "warehouseId": warehouse_id,
        "remark": "API 链路验证：扣减 3 个",
        "items": [
            {
                "originId": origin_id,
                # 数量调整下 targetId 必须与 originId 一致
                "targetId": origin_id,
                "available": str(delta),
                "defective": "0",
            }
        ],
    }


def list_today(client: SellfoxClient, warehouse_id: str) -> list[dict[str, Any]]:
    data = client.signed_post(
        LIST_PATH,
        {
            "pageNo": "1",
            "pageSize": "50",
            "dateType": 1,
            "startDate": date.today().isoformat(),
            "endDate": date.today().isoformat(),
            "warehouseId": warehouse_id,
        },
    )
    return (data or {}).get("rows") or []


def latest_create_time(orders: list[dict[str, Any]]) -> str:
    return max((o.get("createTime") or "" for o in orders), default="")


def find_new_order(
    client: SellfoxClient,
    warehouse_id: str,
    sku: str,
    delta: int,
    since: str,
) -> dict[str, Any]:
    """回查刚建的调整单 —— createV2 的 data 为 null，不回传单号。"""
    for row in list_today(client, warehouse_id):
        if (row.get("createTime") or "") <= since:
            continue
        for item in row.get("itemList") or []:
            if item.get("commoditySku") == sku and item.get("targetAvailable") == delta:
                return row
    raise SystemExit(f"回查不到新调整单 (warehouseId={warehouse_id} sku={sku} delta={delta})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="真正建单并确认（默认 dry-run）")
    parser.add_argument("--warehouse-id", default=DEFAULT_WAREHOUSE_ID)
    parser.add_argument("--sku", default=DEFAULT_SKU)
    parser.add_argument("--delta", type=int, default=DEFAULT_DELTA, help="可用量增量，负数扣减")
    args = parser.parse_args()

    client = make_client()

    # --- Step 0: 定位 originId ---
    item = find_item(client, args.warehouse_id, args.sku)
    origin_id = str(item["id"])
    before = item["stockAvailable"]
    print(f"[库存明细] id={origin_id} sku={item['commoditySku']} 可用={before} 次品={item['stockDefective']}")

    payload = build_payload(args.warehouse_id, origin_id, args.delta)
    print(f"[createV2 payload] {json.dumps(payload, ensure_ascii=False)}")

    if not args.apply:
        print("[dry-run] 未建单。加 --apply 执行。")
        return 0

    since = latest_create_time(list_today(client, args.warehouse_id))

    # --- Step 1: 建单 ---
    created = client.signed_post(CREATE_PATH, payload)
    print(f"[createV2 返回] {json.dumps(created, ensure_ascii=False)}")

    # --- Step 2: 回查单号（createV2 的 data 为 null，不回传 adjustNo） ---
    order = find_new_order(client, args.warehouse_id, args.sku, args.delta, since)
    adjust_no = order["adjustNo"]
    status = order["adjustStatus"]
    print(
        f"[新单] {adjust_no} status={status} type={order['type']} "
        f"processInstanceId={order.get('processInstanceId')!r} canReview={order.get('canReview')!r}"
    )

    # --- Step 3: 确认（仅当单据停在待调整态；无审批流时 createV2 已直接完成） ---
    if status == 3:
        print("[确认] 单据已直接完成，跳过 batchConfirmAdjust")
    elif status == 2:
        result = client.signed_post(CONFIRM_PATH, {"adjustNoList": [adjust_no]})
        print(f"[batchConfirmAdjust] {json.dumps(result, ensure_ascii=False)}")
        if (result or {}).get("fail"):
            print("!! 确认存在失败项")
            return 1
    else:
        print(f"!! 单据停在 status={status}，未自动完成，需人工处理")
        return 1

    # --- Step 4: 复查 ---
    after_item = find_item(client, args.warehouse_id, args.sku)
    after = after_item["stockAvailable"]
    expected = str(int(before) + args.delta)
    print(f"[复查] 可用 {before} → {after} (期望 {expected})")
    if after != expected:
        print("!! 库存未达预期，需人工确认")
        return 1
    print("[OK] 链路跑通")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
