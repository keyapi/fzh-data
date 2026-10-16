# -*- coding: utf-8 -*-
"""stock_alert CLI。

投递按「低库存 SKU 总数」自动分档（`--small-threshold`，默认 10）：
* ≤ 阈值 → 正文直接列明细，不发文件；
* > 阈值 → 生成**按仓库分 sheet 的 Excel**，上传 ERPNext 后发 ActionCard 下载卡片。

    # 离线全链路（不调 API、不发群，只看正文；需要时也落 Excel）
    uv run python -m stock_alert.cli run --mock --dry-run

    # 真查单仓（只出正文）
    uv run python -m stock_alert.cli run --warehouses "美中-FZH-DANEEY"

    # 三仓全量 → 真推（>10 → 发 Excel 卡片）
    uv run python -m stock_alert.cli run --notify

    # 指定 Excel 路径 / 调整分档阈值
    uv run python -m stock_alert.cli run --notify --out out/低库存.xlsx --small-threshold 10

    # 探测 erp2_stocks_stocksquery 的入参 schema 与 1 页真实响应
    uv run python -m stock_alert.cli probe --warehouse "美中-FZH-DANEEY"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .client import StockRow
from .excel import write_low_stock_workbook
from .notify import DEFAULT_SMALL_THRESHOLD, build_body, default_out_path, notify
from .scan import DEFAULT_THRESHOLD, DEFAULT_WAREHOUSES, scan

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
    from .client import TongtoolStockClient

    client = TongtoolStockClient(min_interval=args.min_interval)
    return {wh: client.list_stocks(wh, page_size=args.page_size) for wh in warehouses}


def cmd_run(args) -> int:
    _load_env()
    rows_by_wh = _collect_rows(args)
    result = scan(rows_by_wh, threshold=args.threshold)
    text, need_file = build_body(result, when=args.when, small_threshold=args.small_threshold)
    if args.dry_run or not args.notify:
        print(text)
        if need_file:
            path = write_low_stock_workbook(result, args.out or default_out_path(args.when))
            print(f"\n[Excel 明细（按仓库分 sheet）] {path}")
        return 0
    resp = notify(result, out_xlsx=args.out, small_threshold=args.small_threshold, when=args.when)
    print(json.dumps(resp, ensure_ascii=False))
    return 0 if resp.get("errcode") == 0 else 1


def cmd_probe(args) -> int:
    """探测工具 schema + 1 页真实响应，落 UTF-8 文件（避免控制台中文乱码）。"""
    _load_env()
    from .client import TongtoolStockClient, business_code, extract_payload, get_tool_schema, rows_and_total

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    schema = get_tool_schema()
    schema_path = OUT_DIR / "probe_schema.json"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] schema → {schema_path}")
    if not schema.get("name") or schema.get("found") is False:
        print("[probe] 未找到 erp2_stocks_stocksquery；可用工具见上面的 schema 文件", file=sys.stderr)
        return 1

    client = TongtoolStockClient(min_interval=args.min_interval)
    payload = client._call({"warehouseName": args.warehouse, "pageNo": 1, "pageSize": args.page_size})
    payload_path = OUT_DIR / "probe_sample.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    items, total = rows_and_total(payload)
    print(f"[probe] 业务码={business_code(payload)} 行数={len(items)} total={total}")
    print(f"[probe] 1 页样本 → {payload_path}")
    return 0


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock_alert", description="通途低库存汇总 → 钉钉推送")
    sub = p.add_subparsers(dest="command", required=True)

    def _common(sp):
        sp.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="可用库存阈值，默认 5")
        sp.add_argument("--min-interval", type=float, default=13.0, help="两次 API 调用最小间隔秒（限流 5/分钟）")
        sp.add_argument("--page-size", type=int, default=100, help="分页大小，默认 100")
        sp.add_argument("--when", type=lambda s: __import__("datetime").date.fromisoformat(s), help="标题日期 YYYY-MM-DD")

    r = sub.add_parser("run", help="扫描低库存并（可选）推送")
    r.add_argument("--warehouses", help="逗号分隔仓库名；默认三仓")
    r.add_argument("--mock", action="store_true", help="离线样例，不调 API")
    r.add_argument("--dry-run", action="store_true", help="只打印正文（需要时也落 Excel），不发群")
    r.add_argument("--notify", action="store_true", help="推送钉钉（否则只打印）")
    r.add_argument("--out", help="Excel 明细输出路径，默认 stock_alert_output/通途低库存_<日期>.xlsx")
    r.add_argument("--small-threshold", type=int, default=DEFAULT_SMALL_THRESHOLD,
                   help="低库存总数 ≤ 此值时正文直接列明细、不生成 Excel（默认 10）")
    _common(r)
    r.set_defaults(func=cmd_run)

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
