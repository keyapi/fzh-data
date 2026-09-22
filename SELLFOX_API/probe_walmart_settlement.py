"""一次性探针：验证赛狐 Walmart 账期（结算明细）API 是否真的可用。

背景见 plan / docs/research/2026-09-21-sellfox-walmart-settlement-api.md：
Walmart 是赛狐里唯一带账期字段（periodStartDate/periodEndDate）的结算端点，
但仓库里从没跑过财务类端点，权限与字段均为文档推断。

只读。用法：

    # 阶段 1：列 Walmart 店铺
    uv run python probe_walmart_settlement.py --list-shops

    # 阶段 2：单店铺窄时间窗拉结算明细（598030 = Centrade US，唯一 Walmart 店）
    uv run python probe_walmart_settlement.py --shop-id 598030 \
        --start 2026-08-01 --end 2026-09-21

为什么不用 client.signed_post()：它在 code != 0 时直接抛异常，会吃掉
40021「访问的接口暂无权限」这类关键错误码。探针必须看到原始 code/msg。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from client import SellfoxClient, SellfoxConfig  # noqa: E402
from repo_root import find_main_root  # noqa: E402

SHOP_LIST_PATH = "/api/multiplatform/shop/list.json"
STATEMENT_DETAIL_PATH = "/api/financial/walmartReport/queryStatementDetail.json"

# 代理约 1 rps；探针调用少但保持节奏，避免 429 污染结论
PACING_S = 2.0
RATE_LIMIT_MAX_RETRIES = 6

KEY_FIELDS = [
    "periodStartDate",
    "periodEndDate",
    "transactionPostedDate",
    "transactionType",
    "amountType",
    "transactionDescription",
    "amount",
    "currency",
    "fulfillmentType",
    "purchaseOrder",
    "partnerItemId",
    "partnerGtin",
    "shipQty",
    "shopId",
    "shopName",
    "marketplaceCode",
    "marketplaceName",
]


def _retry_after_seconds(result: dict) -> float:
    """代理限流有两种形态：code=40019，或 HTTP 层 {"detail": "...Retry after 0.3s"}。"""
    detail = result.get("detail")
    if isinstance(detail, str):
        m = re.search(r"Retry after ([\d.]+)s", detail)
        if m:
            return float(m.group(1))
    return 0.0


def _is_rate_limited(result: dict) -> bool:
    detail = str(result.get("detail") or "")
    return result.get("code") == 40019 or "rate limit" in detail.lower()


def raw_post(client: SellfoxClient, path: str, body: dict) -> dict[str, Any]:
    """无异常版 POST：始终返回原始响应 dict（含 code/msg），限流自动重试。"""
    if client.config.mode != "proxy":
        raise SystemExit(
            "本机不在赛狐 VPS 白名单，仅支持 proxy 模式；"
            "请确认根 .env 有 SELLFOX_PROXY_API_KEY"
        )
    last: dict[str, Any] = {}
    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        result, _ = client._post_once_proxy(path, body)
        if not _is_rate_limited(result):
            time.sleep(PACING_S)
            return result
        last = result
        wait = max(_retry_after_seconds(result), PACING_S * (attempt + 1))
        print(f"  · 限流，{wait:.1f}s 后重试 ({attempt + 1}/{RATE_LIMIT_MAX_RETRIES})")
        time.sleep(wait)
    return last


def dump(out_dir: Path, name: str, payload: Any) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  → 样本落盘: {path}")
    return path


def report(code: Any, msg: Any, result: dict | None = None) -> None:
    if code == 0:
        print("  [OK] code=0")
        return
    if code is None and result and _is_rate_limited(result):
        print(f"  [RATE-LIMIT] 限流未恢复: {result.get('detail')}")
        return
    print(f"  [FAIL] code={code} msg={msg}")
    if code == 40021:
        print(
            "  ⚠ 40021 = 该 App 未开通此接口权限。"
            "停手，不要绕私有接口，需走赛狐开放平台申请权限。"
        )


def list_shops(client: SellfoxClient, out_dir: Path, platform: str) -> list[dict]:
    body = {"platformType": platform, "pageNo": 1, "pageSize": 100}
    print(f"[阶段1] POST {SHOP_LIST_PATH} body={json.dumps(body, ensure_ascii=False)}")
    result = raw_post(client, SHOP_LIST_PATH, body)
    dump(out_dir, f"shops_{platform.lower()}.json", result)

    code = result.get("code")
    report(code, result.get("msg"), result)
    if code != 0:
        return []

    rows = ((result.get("data") or {}).get("rows")) or []
    print(f"  共 {len(rows)} 家 {platform} 店铺")
    print(f"  {'id':>8}  {'站点':<6} {'币种':<5} {'状态':<5} {'店铺类型':<12} 名称")
    for s in rows:
        status = {0: "正常", 1: "过期"}.get(s.get("status"), str(s.get("status")))
        print(
            f"  {str(s.get('id')):>8}  {str(s.get('marketplaceCode') or ''):<6} "
            f"{str(s.get('currency') or ''):<5} {status:<5} "
            f"{str(s.get('shopTypeName') or ''):<12} {s.get('name')}"
        )
    return rows


def value_dist(rows: list[dict], field: str) -> Counter:
    return Counter(
        str(r.get(field)) for r in rows if r.get(field) not in (None, "")
    )


def statement_detail(
    client: SellfoxClient,
    out_dir: Path,
    shop_id: str,
    start: str,
    end: str,
    page_size: int,
    page_no: str = "1",
) -> dict:
    body = {
        "transactionPostedStartDate": start,
        "transactionPostedEndDate": end,
        "shopId": [int(shop_id)],
        "pageNo": str(page_no),
        "pageSize": str(page_size),
    }
    print(
        f"[阶段2] POST {STATEMENT_DETAIL_PATH} "
        f"body={json.dumps(body, ensure_ascii=False)}"
    )
    result = raw_post(client, STATEMENT_DETAIL_PATH, body)
    dump(
        out_dir,
        f"statement_shop{shop_id}_{start}_{end}_p{page_no}_n{page_size}.json",
        result,
    )

    code = result.get("code")
    report(code, result.get("msg"), result)
    if code != 0:
        return result

    data = result.get("data") or {}
    rows = (data.get("rows") if isinstance(data, dict) else None) or []
    if isinstance(data, dict) and not rows and data.get("detailPageVoList"):
        rows = data["detailPageVoList"]  # 兜底：万一代理换了响应结构
    print(f"  返回 {len(rows)} 行；data 结构键={list(data) if isinstance(data, dict) else type(data)}")
    if not rows:
        print("  ⚠ 0 行 —— 可能是该窗口无结算数据，也可能 shopId 不对。换个更宽的窗口复测再下结论。")
        return result

    print("\n  --- 关键字段 ---")
    for f in KEY_FIELDS:
        vals = [r.get(f) for r in rows]
        filled = [v for v in vals if v not in (None, "")]
        if not filled:
            print(f"  {f:<24} 全空")
        else:
            uniq = list(dict.fromkeys(str(v) for v in filled))[:3]
            print(f"  {f:<24} 非空 {len(filled)}/{len(rows)}  例: {uniq}")

    period_rows = [
        r for r in rows if r.get("periodStartDate") and r.get("periodEndDate")
    ]
    print(
        f"\n  ★ periodStartDate/periodEndDate 均有值: {len(period_rows)}/{len(rows)}"
        "  ← 账期可用性的决定性指标"
    )

    for f in ("amountType", "transactionType", "fulfillmentType"):
        dist = value_dist(rows, f)
        if dist:
            print(f"\n  {f} 分布:")
            for k, n in dist.most_common(15):
                print(f"    {n:>4}  {k}")

    print("\n  --- 首行样本 ---")
    print(json.dumps(rows[0], ensure_ascii=False, indent=4))
    return result


def fetch_all_pages(
    client: SellfoxClient,
    shop_id: str,
    start: str,
    end: str,
    page_size: int = 200,
    max_pages: int = 80,
) -> list[dict]:
    """翻页拉完一个结算时间窗口。

    ★ 响应 `data` 里只有 `rows`，**没有 totalSize/totalPage** —— 只能翻到
    某页返回条数 < pageSize 为止，不能靠元数据判断结束。
    """
    all_rows: list[dict] = []
    for page in range(1, max_pages + 1):
        body = {
            "transactionPostedStartDate": start,
            "transactionPostedEndDate": end,
            "shopId": [int(shop_id)],
            "pageNo": str(page),
            "pageSize": str(page_size),
        }
        result = raw_post(client, STATEMENT_DETAIL_PATH, body)
        if result.get("code") != 0:
            print(f"  第 {page} 页失败: code={result.get('code')} msg={result.get('msg')}")
            break
        rows = ((result.get("data") or {}).get("rows")) or []
        all_rows += rows
        print(f"  第 {page} 页 {len(rows)} 行（累计 {len(all_rows)}）")
        if len(rows) < page_size:
            break
    return all_rows


def discover_periods(rows: list[dict]) -> list[tuple[str, str, int, str, str]]:
    """按 (periodStartDate, periodEndDate) 归组，返回账期清单。

    返回 (期初, 期末, 行数, 最早结算时间, 最晚结算时间)，按期初升序。
    账期用 periodStart/End 标识；transactionPostedDate 落在账期区间内，
    所以「取某个账期的全部行」= 用该账期的起止日去查 transactionPostedDate。
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r.get("periodStartDate") or "", r.get("periodEndDate") or "")
        groups.setdefault(key, []).append(r)
    out = []
    for (ps, pe), rs in groups.items():
        posted = sorted(x.get("transactionPostedDate") or "" for x in rs)
        out.append((ps, pe, len(rs), posted[0] if posted else "", posted[-1] if posted else ""))
    return sorted(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-shops", action="store_true", help="只列 Walmart 店铺")
    ap.add_argument("--platform", default="WALMART", help="平台类型，默认 WALMART")
    ap.add_argument("--shop-id", help="店铺ID（阶段1 输出里的 id）")
    ap.add_argument("--start", help="transactionPostedStartDate，yyyy-MM-dd")
    ap.add_argument("--end", help="transactionPostedEndDate，yyyy-MM-dd")
    ap.add_argument("--page-size", type=int, default=5, help="每页条数，最大 200")
    ap.add_argument("--page-no", default="1")
    ap.add_argument(
        "--discover-periods",
        action="store_true",
        help="翻完整个窗口，列出其中的账期(periodStart/End)清单及行数",
    )
    ap.add_argument(
        "--pull-period",
        metavar="START:END",
        help="按账期起止日整账期拉全量行，如 2026-08-08:2026-09-05",
    )
    ap.add_argument(
        "--out-dir",
        help="样本输出目录，默认 <repo_root>/out/sellfox_walmart_probe",
    )
    args = ap.parse_args()

    root = find_main_root()
    out_dir = Path(args.out_dir) if args.out_dir else root / "out" / "sellfox_walmart_probe"
    print(f"repo_root = {root}\nout_dir   = {out_dir}")

    client = SellfoxClient(SellfoxConfig.from_env(root / ".env"))
    print(f"赛狐 client mode = {client.config.mode}\n")

    if args.list_shops or not (args.shop_id or args.pull_period):
        list_shops(client, out_dir, args.platform)

    if args.discover_periods:
        if not (args.shop_id and args.start and args.end):
            raise SystemExit("--discover-periods 需要同时给 --shop-id --start --end")
        print(f"[发现账期] 翻窗口 {args.start} → {args.end}")
        rows = fetch_all_pages(client, args.shop_id, args.start, args.end, 200)
        dump(out_dir, f"allrows_{args.shop_id}_{args.start}_{args.end}.json",
             {"rows": rows})
        print(f"\n  共 {len(rows)} 行，发现账期：")
        print(f"  {'期初':<12} {'期末':<12} {'行数':>6}  {'最早结算':<12} {'最晚结算':<12}")
        for ps, pe, n, lo, hi in discover_periods(rows):
            print(f"  {ps:<12} {pe:<12} {n:>6}  {lo:<12} {hi:<12}")

    if args.shop_id and args.start and args.end and not args.discover_periods:
        statement_detail(
            client, out_dir, args.shop_id, args.start, args.end,
            args.page_size, args.page_no,
        )

    if args.pull_period:
        if not args.shop_id:
            raise SystemExit("--pull-period 需要 --shop-id")
        ps, _, pe = args.pull_period.partition(":")
        if not (ps and pe):
            raise SystemExit("--pull-period 格式应为 START:END，如 2026-08-08:2026-09-05")
        print(f"[拉账期] {ps} → {pe}")
        rows = fetch_all_pages(client, args.shop_id, ps, pe, 200)
        dump(out_dir, f"period_{args.shop_id}_{ps}_{pe}.json", {"rows": rows})
        print(f"  账期 {ps}→{pe} 共 {len(rows)} 行")


if __name__ == "__main__":
    main()
