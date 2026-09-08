"""parcel_track CLI：通途订单 → UPS/FedEx/GLS 查询 → 运营异常 Excel。"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

from .orchestrate import run_report


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="parcel_track", description="通途订单混合尾程跟踪 + 运营异常报表")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("report", help="读通途 xlsx，分流查询，写异常 Excel")
    r.add_argument("--tt", required=True, help="通途非FBA订单 xlsx")
    r.add_argument("--out", required=True, help="输出 Excel")
    r.add_argument("--prefix", help="summary 前缀，默认与 --out 同目录同名")
    r.add_argument("--mock", action="store_true", help="离线 mock，不打官方 API / GLS 公开 REST")
    r.add_argument("--limit", type=int, default=0, help="每个承运商最多查 N 个")
    return p


def _mock_gls(number: str, postal: str | None = None):
    """离线 GLS：形状对齐 gls_track.models.GlsParcel，供 classify 使用。"""
    from gls_track.models import GlsParcel

    p = GlsParcel(parcel_no=number, current_status="DELIVERED", delivered=True)
    base = _dt.datetime.now() - _dt.timedelta(days=5)
    p.data_entered_dt = base
    p.handed_dt = base + _dt.timedelta(days=1)
    p.delivered_dt = base + _dt.timedelta(days=2)
    p.last_event_dt = p.delivered_dt
    return p


def _ups_query(mock: bool):
    if mock:
        from ups_track.cli import _mock_query
        return None, _mock_query
    from ups_track.cli import _build_query
    args = argparse.Namespace(mock=False, env="prod", base_url=None, proxy=None)
    built = _build_query(args)
    if isinstance(built, tuple):
        return built
    return None, built


def _fedex_query(mock: bool):
    if mock:
        from fedex_track.cli import _mock_many
        return None, _mock_many
    from fedex_track.cli import _build_query
    args = argparse.Namespace(mock=False, env="production", base_url=None, proxy=None)
    return _build_query(args)


def _gls_query(mock: bool):
    if mock:
        return None, _mock_gls
    from gls_track.client import GlsTrackClient
    client = GlsTrackClient.from_env()
    return client, client.track


def main(argv: list[str] | None = None) -> int:
    args = _make_parser().parse_args(argv)
    if args.command != "report":
        return 2
    prefix = args.prefix
    if not prefix:
        base = os.path.splitext(args.out)[0]
        prefix = base
    uc, uq = _ups_query(args.mock)
    fc, fq = _fedex_query(args.mock)
    gc, gq = _gls_query(args.mock)
    try:
        stats = run_report(
            args.tt, args.out, prefix=prefix, mock=args.mock,
            ups_query=uq, fedex_query=fq, gls_query=gq, limit=args.limit or 0,
        )
    finally:
        if uc is not None:
            uc.close()
        if fc is not None:
            fc.close()
        if gc is not None:
            gc.close()
    print(
        f"入 {stats['in']} → UPS {stats['ups']} / FedEx {stats['fedex']} / GLS {stats['gls']} "
        f"/ 停放 {stats['parked']} → 分类 {stats['classified']}\nwritten {stats['out']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
