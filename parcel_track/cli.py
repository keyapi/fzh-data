"""parcel_track CLI：通途订单 → UPS/FedEx/GLS 查询 → 运营异常 Excel。"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path

from .orchestrate import run_report


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="parcel_track", description="通途订单混合尾程跟踪 + 运营异常报表")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("report", help="读通途 xlsx，分流查询，写异常 Excel")
    r.add_argument("--tt", required=True, help="通途非FBA订单 xlsx；给目录则取其中最新的 .xlsx")
    r.add_argument("--out", help="输出 Excel，默认 parcel_track_output/ops_<日期>.xlsx")
    r.add_argument("--prefix", help="summary 前缀，默认与 --out 同目录同名")
    r.add_argument("--mock", action="store_true", help="离线 mock，不打官方 API / GLS 公开 REST")
    r.add_argument("--limit", type=int, default=0, help="每个承运商最多查 N 个")
    r.add_argument("--workers", type=int, default=4, help="UPS/FedEx/GLS 并发（--mock 时强制 1）")
    r.add_argument("--notify", action="store_true", help="跑完把 Excel 推到钉钉群（复用 dingtalk_robot）")
    r.add_argument("--dry-run", action="store_true", help="配合 --notify：只打印卡片正文，不发群")
    r.add_argument("--title", help="钉钉卡片标题，默认「尾程运营异常 · <日期>」")
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


def _load_env() -> None:
    """依次加载 .env（override=False，只补未设变量）：模块所在仓库根 → 向上找到 AGENTS.md 那层。

    依赖 python-dotenv（pyproject 已声明）。**不要**再吞 ImportError——静默失败会让定时任务
    在缺凭证时表现成莫名其妙的 KeyError。
    """
    from dotenv import load_dotenv

    start = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    seen: set[str] = set()

    def _one(path: str) -> None:
        if os.path.isfile(path) and path not in seen:
            load_dotenv(path, override=False)
            seen.add(path)

    _one(os.path.join(start, ".env"))
    cur = start
    while True:
        if os.path.isfile(os.path.join(cur, "AGENTS.md")):
            _one(os.path.join(cur, ".env"))
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent


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


def _resolve_tt(tt: str) -> str:
    """--tt 给目录时取其中最新的 .xlsx，供无人值守跑（导出落盘后直接跑）。"""
    if not os.path.isdir(tt):
        return tt
    candidates = [p for p in Path(tt).glob("*.xlsx") if not p.name.startswith("~$")]
    if not candidates:
        raise FileNotFoundError(f"{tt} 下没有 .xlsx")
    return str(max(candidates, key=lambda p: p.stat().st_mtime))


def _resolve_out(out: str | None) -> str:
    """--out 省略时用带日期的默认名；父目录不存在则建（无人值守首次跑常见）。"""
    if not out:
        out = os.path.join("parcel_track_output", f"ops_{_dt.date.today():%Y%m%d}.xlsx")
    parent = os.path.dirname(os.path.abspath(out))
    os.makedirs(parent, exist_ok=True)
    return out


def _alert(exc: BaseException) -> None:
    """无人值守跑挂时也要出声：发一条钉钉纯文本告警。"""
    try:
        from .notify import notify_failure

        notify_failure(f"{type(exc).__name__}: {exc}")
        print("已发出失败告警到钉钉", file=sys.stderr)
    except Exception as alert_exc:      # 告警本身失败不能盖住原始异常
        print(f"失败告警发送不成功：{alert_exc}", file=sys.stderr)


def _push(args, stats: dict) -> None:
    from .notify import notify_report

    result = notify_report(args.out, stats, title=args.title, dry_run=args.dry_run)
    if result.get("dry_run"):
        print("--- 钉钉卡片预览（dry-run，未发送）---")
        print(f"标题：{result['title']}\n{result['text']}")
        return
    if result.get("errcode") != 0:
        raise RuntimeError(f"钉钉推送失败：{result}")
    print("已推送到钉钉群")


def main(argv: list[str] | None = None) -> int:
    args = _make_parser().parse_args(argv)
    if args.command != "report":
        return 2
    # --mock 只表示不打承运商 API；--notify 仍需 .env 里的钉钉/ERPNext 凭证。
    # 纯 mock 跑（离线测试）不加载 .env，保持测试与环境无关。
    if not args.mock or args.notify:
        _load_env()
    args.tt = _resolve_tt(args.tt)
    args.out = _resolve_out(args.out)
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
            workers=1 if args.mock else args.workers,
        )
    except Exception as exc:
        if args.notify:
            _alert(exc)
        raise
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
    if args.notify:
        _push(args, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
