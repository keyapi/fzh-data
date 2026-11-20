# -*- coding: utf-8 -*-
"""用赛狐结算中心 V2 的逐笔明细，合成一份 Amazon 结算 flat-file（.txt）作为缺失附件的临时替代。

只用于「钉钉附件丢失/传错、但赛狐 V2 有该结算组逐笔明细」的场景。合成前必须验证：
- 逐笔金额合计 == 结算组 transferAmount
- 行数、币种、结算号一致
7 月已知结算（27080868331）用它合成后 Tax=273.10，与官方 txt 完全一致，可作为忠实度校验。

默认 dry-run（只打印校验结果）；`--write` 才落盘。
"""
from __future__ import annotations

import argparse
import collections
import sys
from datetime import date, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO,):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from SELLFOX_API.client import SellfoxClient, SellfoxConfig  # noqa: E402

GROUP_PATH = "/api/financial/v2/settlementSummary/groupPage.json"
DETAIL_PATH = "/api/financial/v2/settlementSummary/detailPage.json"

# Amazon 结算 V2 flat-file 列（只保留读取/税务需要的列，其余留空）
COLS = [
    "settlement-id", "settlement-start-date", "settlement-end-date", "deposit-date",
    "total-amount", "currency", "transaction-type", "order-id", "merchant-order-id",
    "adjustment-id", "shipment-id", "marketplace-name", "amount-type", "amount-description",
    "amount", "fulfillment-id", "posted-date", "posted-date-time", "order-item-code",
    "merchant-order-item-id", "merchant-adjustment-item-id", "sku", "quantity-purchased",
    "promotion-id",
]


def _iso(value) -> str:
    return str(value or "").replace("/", "-").replace(" UTC", "").strip()


def fetch_group(client, shop_id: int, settlement_id: str, start: str, end: str) -> dict:
    data = client.signed_post(
        GROUP_PATH,
        {
            "timeType": "settlementEndTime",
            "startTime": start,
            "endTime": end,
            "pageNo": "1",
            "pageSize": "200",
            "isSite": True,
        },
    )
    for gr in (data or {}).get("groupVoList", []):
        if str(gr.get("shopId")) == str(shop_id) and str(gr.get("settlementId")) == settlement_id:
            return gr
    raise SystemExit(f"未找到结算组 shopId={shop_id} settlementId={settlement_id} ({start}..{end})")


def fetch_details(client, shop_id: int, currency: str, start: str, end: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        data = client.signed_post(
            DETAIL_PATH,
            {
                "startTime": start,
                "endTime": end,
                "pageNo": str(page),
                "pageSize": "200",
                "shopIds": [shop_id],
                "currency": currency,
                "isSite": True,
                "desc": False,
                "orderBy": "postedDateTimeStr",
            },
        )
        lst = (data or {}).get("detailPageVoList") or []
        rows.extend(lst)
        total = int((data or {}).get("totalPage") or 1)
        if page >= total or not lst:
            break
        page += 1
    return rows


def build_txt_lines(settlement_id: str, group: dict, detail_rows: list[dict]) -> list[str]:
    """把结算组 + 逐笔明细映射成 Amazon V2 flat-file 的 TSV 行。"""
    lines = ["\t".join(COLS)]
    summary = [""] * len(COLS)
    summary[COLS.index("settlement-id")] = settlement_id
    summary[COLS.index("settlement-start-date")] = _iso(group.get("groupStartStr"))
    summary[COLS.index("settlement-end-date")] = _iso(group.get("groupEndStr"))
    summary[COLS.index("deposit-date")] = _iso(
        group.get("utcFundTransferDateStr") or group.get("siteFundTransferDateStr")
    )
    summary[COLS.index("total-amount")] = str(group.get("transferAmount"))
    summary[COLS.index("currency")] = group.get("currency") or "USD"
    lines.append("\t".join(summary))
    for r in detail_rows:
        row = [""] * len(COLS)
        row[COLS.index("settlement-id")] = settlement_id
        row[COLS.index("currency")] = r.get("currency") or group.get("currency") or ""
        row[COLS.index("transaction-type")] = r.get("transactionType") or ""
        row[COLS.index("order-id")] = r.get("orderId") or ""
        row[COLS.index("marketplace-name")] = group.get("marketplaceName") or ""
        row[COLS.index("amount-type")] = r.get("amountType") or ""
        row[COLS.index("amount-description")] = r.get("amountDescription") or ""
        row[COLS.index("amount")] = "" if r.get("amount") is None else r.get("amount")
        row[COLS.index("fulfillment-id")] = r.get("fulfillmentId") or ""
        row[COLS.index("posted-date")] = (r.get("siteTimeStr") or "")[:10]
        row[COLS.index("posted-date-time")] = r.get("postedDateTimeStr") or ""
        row[COLS.index("sku")] = r.get("msku") or ""
        row[COLS.index("quantity-purchased")] = r.get("quantityPurchased") or ""
        lines.append("\t".join(str(x) for x in row))
    return lines


def tax_of(detail_rows: list[dict]) -> float:
    total = 0.0
    for r in detail_rows:
        at = str(r.get("amountType") or "")
        ad = str(r.get("amountDescription") or "")
        if at in ("ItemPrice", "Promotion") and "tax" in ad.lower():
            total += float(r.get("amount") or 0)
    return total


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop-id", type=int, required=True)
    ap.add_argument("--settlement-id", required=True)
    ap.add_argument("--start", required=True, help="结算区间起 YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="结算区间止 YYYY-MM-DD")
    ap.add_argument("--out", required=True, help="输出 txt 路径")
    ap.add_argument("--write", action="store_true", help="真正落盘（默认 dry-run）")
    ap.add_argument("--lookback-days", type=int, default=30)
    args = ap.parse_args()

    c = SellfoxClient(SellfoxConfig.from_env())
    q_start = (date.fromisoformat(args.start) - timedelta(days=args.lookback_days)).isoformat()
    q_end = (date.fromisoformat(args.end) + timedelta(days=7)).isoformat()
    group = fetch_group(c, args.shop_id, args.settlement_id, q_start, q_end)
    currency = group.get("currency") or "USD"
    rows = fetch_details(c, args.shop_id, currency, q_start, q_end)
    sel = [r for r in rows if str(r.get("settlementId")) == args.settlement_id]
    if not sel:
        raise SystemExit("明细为空，停止")
    amt = sum(float(r.get("amount") or 0) for r in sel)
    expected = float(group.get("transferAmount") or 0)
    ok = abs(amt - expected) <= 0.01
    print(
        f"settlement={args.settlement_id} rows={len(sel)} sum={amt:.4f} "
        f"transfer={expected:.4f} match={ok} tax={tax_of(sel):.6f} currency={currency}"
    )
    if not ok:
        raise SystemExit("逐笔合计与转账额不一致，拒绝生成")
    lines = build_txt_lines(args.settlement_id, group, sel)
    if not args.write:
        print(f"(dry-run) 将写入 {args.out}，{len(lines)} 行")
        return
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
