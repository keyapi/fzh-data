"""ups_track CLI — 批量查询 UPS 跟踪节点。

示例::

    # 离线演示（无凭证也能看流程与输出格式）
    python -m ups_track.cli query --input tracking.txt --out result --mock

    # 真实查询（凭证来自 env：UPS_CLIENT_ID / UPS_CLIENT_SECRET）
    python -m ups_track.cli query --input tracking.csv --env prod --out result

产出三件套（同一前缀）：
    <out>.summary.csv    每号一行：当前状态/交付/三时点/错误
    <out>.timeline.csv   每号每个节点一行（完整时间线）
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

from . import DEFAULT_CIE_BASE, DEFAULT_PROD_BASE, __version__
from .batch import (
    Record,
    load_input_file,
    merge_resumed_done,
    run_batch,
)
from .client import UpsTrackClient
from .models import parse_track_payload


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ups_track", description="UPS 跟踪码批量查询工具"
    )
    p.add_argument("--version", action="version", version=f"ups_track {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", help="批量查询跟踪节点")
    q.add_argument("--input", required=True, help="清单：txt 每行一个号；CSV 首列跟踪号、其余列作备注")
    q.add_argument("--out", help="输出前缀（缺省=输入文件同名加 -ups）。产出 .summary.csv/.timeline.csv/.raw.json")
    q.add_argument("--env", choices=["cie", "prod"], default=None,
                   help="默认按环境变量 UPS_API_ENV，未设则 cie（测试）；prod 才用生产 onlinetools")
    q.add_argument("--base-url", help="显式覆盖 base URL（一般用 --env 即可）")
    q.add_argument("--proxy", help="HTTP(S) 代理；缺省读 env UPS_HTTP_PROXY")
    q.add_argument("--workers", type=int, default=4, help="并发线程数")
    q.add_argument("--retries", type=int, default=1, help="可重试失败（限流/5xx/网络）最多额外重试次数")
    q.add_argument("--resume", action="store_true", help="断点续跑：跳过上次已成功单号（读 <out>.raw.json）")
    q.add_argument("--limit", type=int, default=0, help="只处理前 N 个（调试用）")
    q.add_argument("--delay", type=float, default=0.0, help="每号请求后额外间隔秒（温和节流）")
    q.add_argument("--mock", action="store_true", help="离线演示：用内置模拟响应，无需凭证/网络")
    return p


# ── 离线 mock（走真实 parse_track_payload，方便核对输出格式）──────────────────
def _mock_payload(number: str) -> dict[str, Any]:
    seed = sum(ord(c) for c in number)
    delivered = seed % 2 == 0
    days = 3 + seed % 12  # 距今天往前的天数，造一条"近单"
    base = _dt.datetime.now() - _dt.timedelta(days=days)
    def date_at(offset: int) -> str:
        return (base + _dt.timedelta(days=offset)).strftime("%Y%m%d")
    events = [
        {"location": {"address": {"city": "Stafford", "stateProvince": "TX", "postalCode": "77477"}},
         "status": {"type": "M", "code": "MP", "description": "Shipper created a label, UPS has not received the package"},
         "date": date_at(0), "time": "090000"},
        {"location": {"address": {"city": "Stafford", "stateProvince": "TX", "postalCode": "77477"}},
         "status": {"type": "MV", "code": "OR", "description": "We Have Your Package"},
         "date": date_at(1), "time": "183000"},
        {"location": {"address": {"city": "Houston", "stateProvince": "TX", "postalCode": "77001"}},
         "status": {"type": "I", "code": "DP", "description": "Departed from Facility"},
         "date": date_at(2), "time": "021500"},
    ]
    cur_type, cur_desc, cur_code = "I", "In Transit", "IT"
    if delivered:
        events.append(
            {"location": {"address": {"city": "Columbus", "stateProvince": "OH", "postalCode": "43215"}},
             "status": {"type": "D", "code": "FS", "description": "Delivered"},
             "date": date_at(3), "time": "141500"})
        cur_type, cur_desc, cur_code = "D", "Delivered", "FS"
    return {
        "trackResponse": {
            "shipment": [{
                "inquiryNumber": number,
                "currentStatus": {"type": cur_type, "code": cur_code, "description": cur_desc},
                "package": [{"trackingNumber": number, "activity": events}],
                "deliveryInformation": {"signedBy": "FRONT DOOR" if delivered else None},
            }]
        }
    }


def _mock_query(number: str) -> Any:
    return parse_track_payload(number, _mock_payload(number))


def _base_for(args: argparse.Namespace) -> str:
    if args.base_url:
        return args.base_url
    env_mode = (os.getenv("UPS_API_ENV") or "").strip().lower()
    mode = args.env or env_mode or "cie"
    base = os.getenv("UPS_BASE_URL")
    if base:
        return base
    return DEFAULT_PROD_BASE if mode == "prod" else DEFAULT_CIE_BASE


def _build_query(args: argparse.Namespace):
    if args.mock:
        return _mock_query
    cid = os.getenv("UPS_CLIENT_ID", "")
    secret = os.getenv("UPS_CLIENT_SECRET", "")
    if not cid or not secret:
        print(
            "缺少 UPS_CLIENT_ID/UPS_CLIENT_SECRET。设好环境变量，或用 --mock 离线演示。",
            file=sys.stderr,
        )
        raise SystemExit(2)
    client = UpsTrackClient(
        client_id=cid,
        client_secret=secret,
        base_url=_base_for(args),
        proxy=args.proxy or os.getenv("UPS_HTTP_PROXY") or None,
    )
    return client, client.track


def _out_prefix(args: argparse.Namespace) -> str:
    if args.out:
        return args.out
    src = args.input
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(os.path.dirname(src) or ".", f"{base}-ups")


def _write_summary(path: str, records: list[Record]) -> None:
    fieldnames = list(records[0].to_summary_row().keys()) if records else [
        "跟踪号", "备注", "成功", "已交付", "当前状态", "交付日期", "交付城市",
        "交付州", "签收人", "建标时间", "实际发货时间", "最近节点时间", "错误", "尝试次数",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r.to_summary_row())


def _write_timeline(path: str, records: list[Record]) -> None:
    fieldnames = ["跟踪号", "备注", "节点时间", "状态类型", "状态码", "描述", "城市", "州", "邮编"]
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
    undelivered = sum(1 for r in records if r.ok and r.info and not r.info.delivered and not r.info.not_found)
    not_found = sum(1 for r in records if r.ok and r.info and r.info.not_found)
    print(f"共 {total}：成功 {ok}（已交付 {delivered} / 在途 {undelivered} / 查无此号 {not_found}）失败 {failed}")


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
    if not items:
        print(f"清单为空: {args.input}", file=sys.stderr)
        return 2
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    print(f"待查 {len(items)} 个跟踪号 → 输出前缀 {prefix}", file=sys.stderr)

    query = _build_query(args)
    if isinstance(query, tuple):
        client, track = query
    else:
        client, track = None, query
    try:
        resume_from = raw_path if args.resume else None
        results = run_batch(
            track,
            items,
            workers=args.workers,
            retries=args.retries,
            resume_from=resume_from,
            delay=args.delay,
            on_progress=_on_progress,
        )
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
