# -*- coding: utf-8 -*-
"""stock_alert CLI：低库存单卡汇总/下载 + 分段采购入库。

    # 离线全链路（不调 API、不发群）
    uv run python -m stock_alert.cli run --mock --dry-run

    # 真查三仓低库存（不推）
    uv run python -m stock_alert.cli run --dry-run

    # 三仓全量 → 真推（一张汇总卡片，含新增/全部下载）
    uv run python -m stock_alert.cli run --notify

    # 采购入库（统计昨日，不推 / 真推）
    uv run python -m stock_alert.cli inbound --dry-run --date 2026-11-16
    uv run python -m stock_alert.cli inbound --notify

    # 探测 OpenAPI
    uv run python -m stock_alert.cli probe --warehouse "美中-FZH-DANEEY"
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

from .client import StockRow
from .en_client import EnStockClient, StockSyncIncomplete
from .inbound import InboundResult, aggregate as aggregate_inbound
from .tongtool_inbound import collect_inbound as collect_tongtool_inbound
from .names import NameCache
from .notify import (
    notify_inbound,
    notify_low_stock,
    notify_sync_incomplete,
    sync_incomplete_body,
)
from .scan import (
    DEFAULT_THRESHOLD,
    DEFAULT_WAREHOUSES,
    apply_names,
    baseline_by_sku,
    mark_new,
    scan,
)

OUT_DIR = Path(__file__).resolve().parents[1] / "stock_alert_output"


def _load_env() -> None:
    """依次加载 .env（override=False）：仓库根 → 向上找到 AGENTS.md 那层。

    依赖 python-dotenv。不吞 ImportError——静默失败会让定时任务缺凭证时莫名其妙。
    """
    from dotenv import load_dotenv

    start = str(Path(__file__).resolve().parents[1])
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


def _parse_warehouses(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_WAREHOUSES)
    return [w.strip() for w in value.split(",") if w.strip()]


def _make_en(args) -> EnStockClient:
    base = os.environ.get("ERP_URL", "https://erpnext.vilavi.cn")
    key = os.environ.get("ERP_API_KEY", "").strip()
    secret = os.environ.get("ERP_API_SECRET", "").strip()
    if not key or not secret:
        raise RuntimeError("缺少 ERP_API_KEY/ERP_API_SECRET（读 EN）")
    return EnStockClient(base, key, secret)


def _synthetic_rows(warehouses: list[str], threshold: float) -> dict[str, list[StockRow]]:
    """离线样例：每仓给几行，含低于阈值与高于阈值各若干。"""
    out: dict[str, list[StockRow]] = {}
    for i, wh in enumerate(warehouses):
        out[wh] = [
            StockRow(wh, f"DEMO-{i}-A", available=threshold - 1, intransit=2),
            StockRow(wh, f"DEMO-{i}-B", available=0, intransit=0),
            StockRow(wh, f"DEMO-{i}-C", available=threshold + 10, intransit=5),
        ]
    return out


def _collect_rows(args) -> dict[str, list[StockRow]]:
    warehouses = _parse_warehouses(args.warehouses)
    if args.mock:
        return _synthetic_rows(warehouses, args.threshold)

    source = getattr(args, "source", "en")
    if source == "en":
        try:
            en = _make_en(args)
            ok, detail = en.check_freshness(args.when)
            if not ok:
                raise StockSyncIncomplete(detail)
            return {wh: en.list_stocks(wh) for wh in warehouses}
        except StockSyncIncomplete:
            raise
        except Exception as exc:  # EN 不可达/缺凭证 → 回退 OpenAPI
            print(f"[warn] EN 读取失败，回退 OpenAPI：{type(exc).__name__}: {exc}", file=sys.stderr)

    from .client import TongtoolStockClient

    client = TongtoolStockClient(min_interval=args.min_interval)
    return {wh: client.list_stocks(wh, page_size=args.page_size) for wh in warehouses}


def _cached_names(path: Path, skus: list[str]) -> dict[str, str]:
    """名称 API 不可用时，退回本地缓存（仍缺失的留空，调用方用 SKU 兜底）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = data.get("names") or {}
        return {sku: (names.get(sku) or {}).get("name") or "" for sku in skus}
    except Exception:  # noqa: BLE001 - 缓存损坏/不存在都降级
        return {}


def _resolve_names(skus, args) -> dict[str, str]:
    """SKU → 产品名称；任何失败都降级（绝不阻断推送）。"""
    wanted = [s for s in dict.fromkeys(str(s).strip() for s in (skus or [])) if s]
    if not wanted:
        return {}
    path = OUT_DIR / "sku_names.json"
    try:
        from tongtool_api.mcp_http import primary_credentials
        from tongtool_api.openapi_client import TongtoolOpenApiClient

        # Names are optional: keep retries bounded so an outage cannot hold the report for many minutes.
        api = TongtoolOpenApiClient(*primary_credentials(), min_interval=args.min_interval, max_retries=1)
        print(f"[names] 查询 {len(wanted)} 个 SKU 的名称（可降级）", file=sys.stderr, flush=True)
        return NameCache(api, path).resolve(wanted)
    except Exception as exc:  # noqa: BLE001 - 名称只是锦上添花
        # Authentication URLs can contain credentials; do not log exception URLs.
        print(f"[warn] 产品名称查询失败，降级为缓存/SKU：{type(exc).__name__}", file=sys.stderr)
        return _cached_names(path, wanted)


def _load_baseline(en: EnStockClient, warehouses: list[str], day: _dt.date) -> dict[str, dict[str, float]]:
    """昨日各仓 {sku: available}；单仓失败返回空映射（触发「基线缺失」兜底）。"""
    out: dict[str, dict[str, float]] = {}
    for wh in warehouses:
        try:
            out[wh] = baseline_by_sku(en.stock_history(wh, day.isoformat(), day.isoformat()))
        except Exception as exc:  # noqa: BLE001 - 基线失败不影响低库存主流程
            print(f"[warn] 昨日基线读取失败（{wh}）：{type(exc).__name__}: {exc}", file=sys.stderr)
            out[wh] = {}
    return out


INBOUND_STATE = OUT_DIR / "inbound_state.json"


def _load_inbound_state() -> dict:
    try:
        return json.loads(INBOUND_STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 状态损坏/不存在按首次检查处理
        return {}


def _save_inbound_state(day: _dt.date, at: _dt.datetime) -> None:
    INBOUND_STATE.parent.mkdir(parents=True, exist_ok=True)
    INBOUND_STATE.write_text(
        json.dumps({"day": day.isoformat(), "last_checked_at": at.isoformat()},
                   ensure_ascii=False),
        encoding="utf-8",
    )


def cmd_run(args) -> int:
    _load_env()
    try:
        rows_by_wh = _collect_rows(args)
    except StockSyncIncomplete as exc:
        if args.dry_run or not args.notify:
            print(sync_incomplete_body(str(exc), when=args.when))
            return 0
        resp = notify_sync_incomplete(str(exc), when=args.when)
        print(json.dumps(resp, ensure_ascii=False))
        return 0 if resp.get("errcode") == 0 else 1

    result = scan(rows_by_wh, threshold=args.threshold)
    skus = [item.sku for wh in result.warehouses for item in wh.low]
    names = {} if args.mock else _resolve_names(skus, args)
    apply_names(result, names)

    day = args.when or _dt.date.today()
    baseline = None
    if not args.no_baseline and not args.mock:
        try:
            en = _make_en(args)
            baseline = _load_baseline(en, [w.warehouse for w in result.warehouses], day - _dt.timedelta(days=1))
        except Exception as exc:  # noqa: BLE001 - 拿不到 EN 就不标记新增
            print(f"[warn] 无法读取昨日基线，跳过今日新增：{type(exc).__name__}: {exc}", file=sys.stderr)
    mark_new(result, baseline, threshold=args.threshold)

    new_count = sum(1 for wh in result.warehouses for item in wh.low if item.is_new)
    print(json.dumps({"mode": "low_stock", "input_rows": sum(len(rows) for rows in rows_by_wh.values()),
                      "low_rows": result.total_low, "new_rows": new_count,
                      "skipped": {
                          "at_or_above_threshold": sum(row.available >= args.threshold for rows in rows_by_wh.values() for row in rows),
                          "zero_stock_without_transit": sum(row.available < args.threshold and row.available == 0 and row.intransit == 0
                                                            for rows in rows_by_wh.values() for row in rows),
                      },
                      "baseline_available": baseline is not None,
                      "names_missing": sum(not names.get(sku) for sku in skus)}, ensure_ascii=False), file=sys.stderr)

    preview = args.dry_run or not args.notify
    resp = notify_low_stock(result, when=day, out_xlsx=args.out, dry_run=preview)
    return _show_notification(resp, preview=preview)


def _show_notification(resp: dict, *, preview: bool) -> int:
    if preview:
        for message in resp["messages"]:
            print(message)
        for item in resp["files"]:
            print(f"[{item['title']}] {item['path']}")
        if resp.get("card_image"):
            print(f"[卡片图片] {resp['card_image']}")
        if resp.get("card_preview"):
            print("\n[互动卡片变量 cardParamMap]")
            print(json.dumps(resp["card_preview"], ensure_ascii=False, indent=2))
        for error in resp["file_errors"]:
            print(error, file=sys.stderr)
    else:
        print(json.dumps(resp, ensure_ascii=False))
    return 0 if resp.get("errcode") == 0 else 1


def cmd_inbound(args) -> int:
    _load_env()
    today = _dt.date.today()
    day = args.date or (today if args.today else today - _dt.timedelta(days=1))
    warehouses = _parse_warehouses(args.warehouses)
    source = getattr(args, "source", "en")
    label = ""
    as_of = ""
    state_update = None

    if args.mock:
        rows_by_wh = {
            wh: [{"sku": f"DEMO-IN-{i}", "voucher_type": "02", "available_increase": 10 + i}]
            for i, wh in enumerate(warehouses)
        }
        if args.today:
            now = _dt.datetime.now()
            label = f"截至 {now:%H:%M}"
            as_of = f"{now:%H:%M}"
    elif source == "tongtool":
        now = _dt.datetime.now()
        if args.today:
            since = _dt.datetime.combine(day, _dt.time.min)
            state = _load_inbound_state()
            if state.get("day") == day.isoformat():
                try:
                    last = _dt.datetime.fromisoformat(str(state.get("last_checked_at") or ""))
                    if last.date() == day and last > since:
                        since = last
                except ValueError:
                    pass
            until = now
            label = f"{since:%H:%M}–{until:%H:%M} 新增"
            as_of = f"{until:%H:%M}"
            state_update = (day, until)
        else:
            since = _dt.datetime.combine(day, _dt.time.min)
            until = _dt.datetime.combine(day, _dt.time.max)
            label = "全日"
        rows_by_wh = collect_tongtool_inbound(warehouses, since, until,
                                              min_interval=args.min_interval)
    else:
        en = _make_en(args)
        rows_by_wh = {
            wh: en.stock_changes(wh, day.isoformat(), day.isoformat(), voucher_type="02", limit=5000)
            for wh in warehouses
        }
        if args.today:
            now = _dt.datetime.now()
            label = f"截至 {now:%H:%M}"
            as_of = f"{now:%H:%M}"

    result = aggregate_inbound(rows_by_wh, day=day, label=label, as_of=as_of)
    skus = [item.sku for wh in result.warehouses for item in wh.items]
    names = {} if args.mock else _resolve_names(skus, args)
    for wh in result.warehouses:
        for item in wh.items:
            item.name = names.get(item.sku, "")
    print(json.dumps({"mode": "inbound", "source": source, "window": label,
                      "input_rows": result.input_rows,
                      "accepted_rows": result.accepted_rows, "skipped": result.skipped,
                      "output_skus": result.total_skus, "total_qty": result.total_qty},
                     ensure_ascii=False), file=sys.stderr)

    preview = args.dry_run or not args.notify
    pieces = [
        InboundResult(day=result.day, warehouses=[wh],
                      input_rows=result.input_rows, accepted_rows=result.accepted_rows,
                      skipped=result.skipped, label=result.label, as_of=result.as_of)
        for wh in result.warehouses if wh.items
    ]
    responses = []
    rc = 0
    for piece in pieces:
        resp = notify_inbound(piece, dry_run=preview)
        responses.append(resp)
        if preview:
            rc = max(rc, _show_notification(resp, preview=True))
        else:
            rc = max(rc, 0 if resp.get("errcode") == 0 else 1)
    if not preview:
        print(json.dumps(responses, ensure_ascii=False))
    if not preview and rc == 0 and state_update:
        _save_inbound_state(*state_update)
    return rc


def cmd_probe(args) -> int:
    """探测 OpenAPI：认证 → 仓库列表(status=1) → 1 页库存；落 UTF-8 文件。"""
    _load_env()
    from tongtool_api.mcp_http import primary_credentials
    from tongtool_api.openapi_client import TongtoolOpenApiClient
    from .client import rows_and_total

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key, secret = primary_credentials()
    api = TongtoolOpenApiClient(key, secret, min_interval=args.min_interval)
    merchant = api.authenticate()
    print(f"[probe] merchantId={merchant}")

    wh_payload = api.warehouses(page_size=200)
    warehouses, _ = rows_and_total(wh_payload)
    active = [w for w in warehouses if str(w.get("status")) == "1"]
    wh_path = OUT_DIR / "probe_warehouses.json"
    wh_path.write_text(json.dumps(wh_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] 仓库 {len(warehouses)} 个（status=1: {len(active)}）→ {wh_path}")

    payload = api.stocks(args.warehouse, 1, args.page_size)
    items, total = rows_and_total(payload)
    sample_path = OUT_DIR / "probe_sample.json"
    sample_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] {args.warehouse}: 行数={len(items)} total={total} → {sample_path}")
    return 0


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock_alert", description="通途库存汇总 → 钉钉推送")
    sub = p.add_subparsers(dest="command", required=True)

    def _common(sp):
        sp.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="可用库存阈值，默认 5")
        sp.add_argument("--min-interval", type=float, default=13.0, help="两次 API 调用最小间隔秒（限流 5/分钟）")
        sp.add_argument("--page-size", type=int, default=100, help="分页大小，默认 100")
        sp.add_argument("--when", type=lambda s: _dt.date.fromisoformat(s), help="标题日期 YYYY-MM-DD")

    r = sub.add_parser("run", help="扫描低库存并（可选）推送")
    r.add_argument("--warehouses", help="逗号分隔仓库名；默认三仓")
    r.add_argument("--mock", action="store_true", help="离线样例，不调 API")
    r.add_argument("--dry-run", action="store_true", help="只打印正文（需要时也落 Excel），不发群")
    r.add_argument("--notify", action="store_true", help="推送钉钉（否则只打印）")
    r.add_argument("--source", choices=["en", "openapi"], default="en",
                   help="取数来源：en=Tongtool Stock Latest（默认，含新鲜度门禁）；openapi=直连通途")
    r.add_argument("--out", help="Excel 输出路径，默认 stock_alert_output/通途新增低库存_<日期>.xlsx")
    r.add_argument("--no-baseline", action="store_true", help="不拉昨日基线（不生成今日新增 Excel）")
    _common(r)
    r.set_defaults(func=cmd_run)

    i = sub.add_parser("inbound", help="汇总采购入库（支持白天实时检查）")
    i.add_argument("--warehouses", help="逗号分隔仓库名；默认三仓")
    i.add_argument("--mock", action="store_true", help="离线样例，不调 API")
    i.add_argument("--dry-run", action="store_true", help="只打印正文，不发群")
    i.add_argument("--notify", action="store_true", help="推送钉钉（否则只打印）")
    i.add_argument("--date", type=lambda s: _dt.date.fromisoformat(s),
                   help="统计日期 YYYY-MM-DD，默认昨天")
    i.add_argument("--today", action="store_true", help="统计今天（增量窗口从上次成功检查开始）")
    i.add_argument("--source", choices=["en", "tongtool"], default="en",
                   help="en=EN stock_change（日更，默认）；tongtool=直连通途（实时）")
    i.add_argument("--min-interval", type=float, default=13.0, help="两次 API 调用最小间隔秒（限流 5/分钟）")
    i.set_defaults(func=cmd_inbound, page_size=100, when=None, threshold=DEFAULT_THRESHOLD)

    pr = sub.add_parser("probe", help="探测 stocksquery schema 与 1 页响应")
    pr.add_argument("--warehouse", default=DEFAULT_WAREHOUSES[0])
    _common(pr)
    pr.set_defaults(func=cmd_probe)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _make_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
