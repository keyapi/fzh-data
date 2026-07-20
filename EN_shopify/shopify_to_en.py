# -*- coding: utf-8 -*-
"""独立站 (daneey.com) 产品链接写入 EN 系统。

数据流：
  独立站产品数据 (CSV / API)
    → 解析为统一格式
    → TT-SKU 匹配 EN 系统物料组
    → 写入 Item Group.daneey_product_details

使用:
  # CSV 模式 — dry-run 预览匹配（先执行这个）
  python shopify_to_en.py --mode csv --dry-run --env test

  # CSV 模式 — 写入测试系统
  python shopify_to_en.py --mode csv --env test

  # CSV 模式 — 写入生产系统
  python shopify_to_en.py --mode csv --env prod

  # API 模式（后续增量维护）
  python shopify_to_en.py --mode api --dry-run --env test
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 确保 common 可导入 ──────────────────────────────
_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))

from common.env import load_dotenv, get_erpnext_url, get_erpnext_credentials
from common.erpnext_client import ErpnextClient
from common.report import generate_match_report

# 延迟导入（可能在 common 初始化后才能正常工作）
shopify_source = None
en_matcher = None
en_writer = None

_CSV_DEFAULT = _DIR / "数据源" / "products_export_1.csv"
_OUT_DIR = _DIR / "out"
_OUT_DIR.mkdir(parents=True, exist_ok=True)

_STORE_URL = "https://daneey.com"


def _lazy_imports():
    global shopify_source, en_matcher, en_writer
    if shopify_source is None:
        import shopify_source as ss
        import en_matcher as em
        import en_writer as ew
        shopify_source = ss
        en_matcher = em
        en_writer = ew


def _progress_cb(current: int, total: int):
    """匹配进度回调。"""
    if total > 0 and current % 50 == 0:
        pct = current / total * 100
        print(f"    进度: {current}/{total} ({pct:.0f}%)")


def cmd_csv(args: argparse.Namespace) -> int:
    """CSV 模式：从文件读取产品数据。"""
    csv_path = Path(args.csv_path) if args.csv_path else _CSV_DEFAULT
    if not csv_path.exists():
        print(f"[ERROR] CSV 文件不存在: {csv_path}")
        return 1

    print(f"── 读取 CSV: {csv_path} ──")
    _lazy_imports()
    products = shopify_source.from_csv(str(csv_path), store_url=_STORE_URL)
    shopify_source.print_stats(products)
    return _process(products, args)


def cmd_api(args: argparse.Namespace) -> int:
    """API 模式：从 Shopify API 拉取实时数据。"""
    print(f"── 从 {_STORE_URL} API 拉取产品数据 ──")
    _lazy_imports()
    products = shopify_source.from_api(store_url=_STORE_URL,
                                       max_products=args.max_products)
    shopify_source.print_stats(products)
    return _process(products, args)


def _process(products: list[dict], args: argparse.Namespace) -> int:
    """处理产品数据：匹配 → 报告 → （可选）写入。"""
    if not products:
        print("[ERROR] 无产品数据，终止")
        return 1

    # ── 建立连接 ──
    # 匹配阶段：
    #   - API 部署在测试系统时: match_env = "test"
    #   - API 部署到生产后:      match_env = "prod"（数据最全）
    match_env = "prod"  # 使用生产系统 API（数据最全）
    write_env = args.env

    match_url = get_erpnext_url(match_env)
    match_key, match_secret = get_erpnext_credentials(match_env)

    write_url = get_erpnext_url(write_env)
    write_key, write_secret = get_erpnext_credentials(write_env)

    if not match_key or not match_secret:
        print(f"[ERROR] 缺少生产环境的 API 凭证（匹配必需）。请检查 .env 文件。")
        return 1

    match_client = ErpnextClient(match_url, match_key, match_secret,
                                 label=f"匹配({match_env})")
    print(f"\n── 匹配源: {match_env} ({match_url}) ──")

    if write_env != match_env:
        if not write_key or not write_secret:
            print(f"[ERROR] 缺少 {write_env} 环境的 API 凭证。")
            return 1
        write_client = ErpnextClient(write_url, write_key, write_secret,
                                     label=f"写入({write_env})")
        print(f"── 写入目标: {write_env} ({write_url}) ──")
    else:
        write_client = match_client
        print(f"── 写入目标: 同匹配源 ({write_env}) ──")

    # ── 匹配 ──
    print(f"\n── 匹配 {len(products)} 个产品 ──")
    matcher = en_matcher.EnMatcher(match_client)

    t0 = time.time()
    results = matcher.match_batch(products, progress_cb=_progress_cb)
    elapsed = time.time() - t0

    # 统计
    matched = [r for r in results if r["match_status"] == "ok"]
    unmatched = [r for r in results if r["match_status"] == "no_match"]

    stats = {
        "数据源模式": "CSV" if args.mode == "csv" else "API",
        "匹配环境": f"prod ({match_url})",
        "写入环境": f"{write_env} ({write_url})",
        "产品总数": len(results),
        "匹配成功": len(matched),
        "匹配失败": len(unmatched),
        "匹配率": f"{len(matched)/len(results)*100:.1f}%",
        "缓存命中": matcher.cache_size,
        "耗时(秒)": f"{elapsed:.1f}",
        "运行模式": "DRY-RUN" if args.dry_run else "执行",
        "执行时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    print(f"\n── 匹配统计 ──")
    print(f"  总产品: {stats['产品总数']}")
    print(f"  匹配成功: {stats['匹配成功']}")
    print(f"  匹配失败: {stats['匹配失败']}")
    print(f"  匹配率: {stats['匹配率']}")

    # ── 生成报告 ──
    report_path = generate_match_report(
        results=matched,
        unmatched=unmatched,
        stats=stats,
        out_dir=_OUT_DIR,
        dry_run=args.dry_run,
    )

    # ── 写入 EN 系统（全量覆盖） ──
    writer = en_writer.EnWriter(write_client)

    if matched:
        log = writer.write_all(matched, dry_run=args.dry_run)
        if not args.dry_run:
            writer.print_summary()
    else:
        print("\n  [SKIP] 无匹配产品，跳过写入")

    print(f"\n[OK] 完成! 报告: {report_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="独立站产品链接写入 EN 系统物料组",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--mode", choices=["csv", "api"], default="csv",
        help="数据源模式: csv=从文件读取(默认), api=从Shopify API拉取"
    )
    ap.add_argument(
        "--csv-path", default=None,
        help=f"CSV 文件路径（默认: {_CSV_DEFAULT}）"
    )
    ap.add_argument(
        "--env", choices=["test", "prod"], default="test",
        help="目标 EN 系统环境: test(默认) / prod"
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="预览模式：只生成匹配报告，不写入 EN 系统"
    )
    ap.add_argument(
        "--max-products", type=int, default=None,
        help="API 模式：最大拉取产品数（默认全部）"
    )

    args = ap.parse_args()

    if args.mode == "csv":
        return cmd_csv(args)
    else:
        return cmd_api(args)


if __name__ == "__main__":
    sys.exit(main())
