"""fedex_track CLI — 批量查询 FedEx 跟踪节点（仿 ups_track）。

示例::

    # 离线演示（无凭证也能看流程与输出格式）
    python -m fedex_track.cli query --input tracking.txt --out result --mock

    # 真实查询（凭证来自 env：FEDEX_API_KEY / FEDEX_SECRET_KEY / FEDEX_ENV）
    python -m fedex_track.cli query --input 通途非FBA订单202608.xlsx --env production --out result --filter-carrier fedex

产出三件套（同一前缀）：
    <out>.summary.csv    每号一行：当前状态/已交付/已取消/建标时间/站点收件时间/交付时间/错误
    <out>.timeline.csv   每号每个节点一行（**完整状态历史**）
    <out>.raw.json       每号原始响应（留档 / 断点续跑依据）
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import sys
from typing import Any

from . import __version__
from .batch import Record, load_input_file, merge_resumed_done, run_batch
from .client import DEFAULT_PROD_BASE, DEFAULT_SANDBOX_BASE, FedexTrackClient
from .models import FdxTrackInfo, parse_track_payload


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fedex_track", description="FedEx 跟踪码批量查询工具")
    p.add_argument("--version", action="version", version=f"fedex_track {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", help="批量查询跟踪节点")
    q.add_argument("--input", required=True, help="清单：txt 每行一个号 / CSV / xlsx；自动识别跟踪号列")
    q.add_argument("--out", help="输出前缀（缺省=输入文件同名加 -fedex）")
    q.add_argument("--env", choices=["production", "sandbox"], default=None,
                   help="默认按环境变量 FEDEX_ENV，未设则 production")
    q.add_argument("--base-url", help="显式覆盖 base URL")
    q.add_argument("--proxy", help="HTTP(S) 代理；缺省读 env FEDEX_HTTP_PROXY")
    q.add_argument("--filter-carrier", help="只保留备注里含该承运关键词的行（如 fedex 用于滤掉 UPS/USPS）")
    q.add_argument("--workers", type=int, default=4, help="并行 chunk 数")
    q.add_argument("--retries", type=int, default=1, help="可重试失败最多额外次数")
    q.add_argument("--resume", action="store_true", help="断点续跑：跳过上次已成功单号")
    q.add_argument("--limit", type=int, default=0, help="只处理前 N 个")
    q.add_argument("--delay", type=float, default=0.0, help="每个 chunk 后额外间隔秒")
    q.add_argument("--mock", action="store_true", help="离线演示")
    return p


# ── 离线 mock（走真实 parse_track_payload）────────────────────
def _mock_payload(number: str) -> dict[str, Any]:
    seed = sum(ord(c) for c in number)
    delivered = seed % 3 != 0
    cancelled = (not delivered) and (seed % 4 == 0)
    base = _dt.datetime.now() - _dt.timedelta(days=2)
    def iso(offset_min: int) -> str:
        return (base + _dt.timedelta(minutes=offset_min)).isoformat()
    ev = [
        {"date": iso(0), "eventType": "OC", "eventDescription": "Shipment information sent to FedEx",
         "derivedStatus": "Label created", "derivedStatusCode": "IN",
         "scanLocation": {"city": "East Hanover", "stateOrProvinceCode": "NJ", "postalCode": "07936"}},
        {"date": iso(-600), "eventType": "PU", "eventDescription": "Picked up",
         "derivedStatus": "Picked up", "derivedStatusCode": "PU",
         "scanLocation": {"city": "East Hanover", "stateOrProvinceCode": "NJ", "postalCode": "07936"}},
    ]
    latest = {"code": "PU", "description": "Picked up", "scanLocation": {"city": "East Hanover", "stateOrProvinceCode": "NJ"}}
    if delivered:
        ev.append({"date": iso(-1200), "eventType": "DL", "eventDescription": "Delivered",
                   "derivedStatus": "Delivered", "derivedStatusCode": "DL",
                   "scanLocation": {"city": "Newark", "stateOrProvinceCode": "DE", "postalCode": "19702"}})
        latest = {"code": "DL", "description": "Delivered", "scanLocation": {"city": "Newark", "stateOrProvinceCode": "DE"}}
    if cancelled:
        latest = {"code": "CA", "description": "Shipment cancelled by sender"}
    return {
        "output": {
            "completeTrackResults": [{
                "trackingNumber": number,
                "trackResults": [{
                    "trackingNumberInfo": {"trackingNumber": number, "carrierCode": "FDXG"},
                    "latestStatusDetail": latest,
                    "scanEvents": ev,
                    "deliveryDetails": {"actualDeliveryAddress": {"city": "Newark", "stateOrProvinceCode": "DE"}} if delivered else {},
                }]
            }]
        }
    }


def _mock_query(number: str) -> FdxTrackInfo:
    return parse_track_payload(number, _mock_payload(number))


def _mock_many(numbers: list[str]) -> dict[str, FdxTrackInfo]:
    return {n.strip().upper(): _mock_query(n) for n in numbers}


def _base_for(args: argparse.Namespace) -> str:
    if args.base_url:
        return args.base_url
    env_mode = (os.getenv("FEDEX_ENV") or "production").strip().lower()
    mode = args.env or ("production" if env_mode in ("production", "prod") else "sandbox")
    base = os.getenv("FEDEX_BASE_URL")
    if base:
        return base
    return DEFAULT_PROD_BASE if mode == "production" else DEFAULT_SANDBOX_BASE


def _build_query(args: argparse.Namespace):
    if args.mock:
        return None, _mock_many
    key = os.getenv("FEDEX_API_KEY", "")
    secret = os.getenv("FEDEX_SECRET_KEY", "")
    if not key or not secret:
        print("缺少 FEDEX_API_KEY/FEDEX_SECRET_KEY。设好环境变量，或用 --mock 离线演示。", file=sys.stderr)
        raise SystemExit(2)
    client = FedexTrackClient(api_key=key, secret_key=secret, base_url=_base_for(args),
                              proxy=args.proxy or os.getenv("FEDEX_HTTP_PROXY") or None)
    return client, client.track_many


def _out_prefix(args: argparse.Namespace) -> str:
    if args.out:
        return args.out
    src = args.input
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(os.path.dirname(src) or ".", f"{base}-fedex")


def _write_summary(path: str, records: list[Record]) -> None:
    fieldnames = list(records[0].to_summary_row().keys()) if records else [
        "跟踪号", "备注", "成功", "已交付", "已取消", "当前状态", "状态码", "建标时间",
        "站点收件时间", "交付时间", "交付城市", "交付州", "最近节点时间", "节点数", "错误", "尝试次数",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r.to_summary_row())


def _write_timeline(path: str, records: list[Record]) -> None:
    fieldnames = ["跟踪号", "备注", "节点时间", "事件码", "描述", "派生状态", "城市", "州", "邮编", "国家"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            for row in r.timeline_rows():
                writer.writerow(row)


def _write_raw(path: str, records: list[Record]) -> None:
    data: dict[str, Any] = {}
    for r in records:
        data[r.number] = r.to_raw_entry()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _report(records: list[Record]) -> None:
    total = len(records)
    ok = sum(1 for r in records if r.ok)
    failed = total - ok
    delivered = sum(1 for r in records if r.ok and r.info and r.info.delivered)
    cancelled = sum(1 for r in records if r.ok and r.info and r.info.cancelled)
    in_transit = sum(1 for r in records if r.ok and r.info and not r.info.delivered and not r.info.cancelled and not r.info.not_found)
    not_found = sum(1 for r in records if r.ok and r.info and r.info.not_found)
    print(f"共 {total}：成功 {ok}（已交付 {delivered} / 已取消 {cancelled} / 在途 {in_transit} / 查无此号 {not_found}）失败 {failed}")


def _on_progress(done: int, total: int, item: Any, _ok: bool) -> None:
    print(f"\r[{done}/{total}] {item.number}", end="", file=sys.stderr, flush=True)
    if done == total:
        print("", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _make_parser().parse_args(argv)
    if args.command != "query":
        print(f"未知子命令: {args.command}", file=sys.stderr)
        return 2

    prefix = _out_prefix(args)
    raw_path = f"{prefix}.raw.json"
    try:
        items = load_input_file(args.input)
    except FileNotFoundError:
        print(f"清单文件不存在: {args.input}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"读取清单失败: {exc}", file=sys.stderr)
        return 2
    if args.filter_carrier:
        kw = args.filter_carrier.lower()
        items = [it for it in items if kw in it.remark.lower()]
        print(f"按承运 {args.filter_carrier} 过滤后: {len(items)} 个", file=sys.stderr)
    # 去重：同一单号只查一次（保留首次备注）
    seen: set[str] = set()
    uniq: list[Any] = []
    for it in items:
        if it.number in seen:
            continue
        seen.add(it.number)
        uniq.append(it)
    items = uniq
    if not items:
        print(f"清单为空(或全被过滤): {args.input}", file=sys.stderr)
        return 2
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    print(f"待查 {len(items)} 个跟踪号 → 输出前缀 {prefix}", file=sys.stderr)

    client, query = _build_query(args)
    if query is None:
        print("缺少客户端构建", file=sys.stderr)
        return 2
    try:
        resume_from = raw_path if args.resume else None
        results = run_batch(query, items, workers=args.workers, retries=args.retries,
                            resume_from=resume_from, delay=args.delay, on_progress=_on_progress)
        results = merge_resumed_done(results, resume_from)
    finally:
        if client is not None:
            client.close()

    _write_summary(f"{prefix}.summary.csv", results)
    _write_timeline(f"{prefix}.timeline.csv", results)
    _write_raw(raw_path, results)
    print(f"\n已写入:\n  {prefix}.summary.csv\n  {prefix}.timeline.csv\n  {raw_path}")
    _report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
