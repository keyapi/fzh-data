# -*- coding: utf-8 -*-
"""Amazon 账期 txt → Tax 汇总 Excel + GSheet（本地/NAS 桶，替代 Colab「税账期TXT 挂载Gdrive」）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "amazon_period_tax"
_DING = _REPO / "dingtalk" / "dingtalk_oa_approval"
for p in (_REPO, _REPO / "tongtool_order_cost", _PKG, _DING):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bucket_meta import resolve_exchange_month  # noqa: E402
from exchange_rate import load_exchange_rate_table  # noqa: E402
from explore_tables import build_exploration_tables  # noqa: E402
from gsheet_tax import sort_additional_fee_tax_tabs, tax_worksheet_name, write_df_to_gsheet  # noqa: E402
from normalize_dates import normalize_posted_dates  # noqa: E402
from read_amz_txt import read_bucket_amz_txts  # noqa: E402
from tax_aggregate import enrich_with_fx, tax_summary_df6, tax_summary_for_gsheet  # noqa: E402


def resolve_bucket_dir(args) -> Path:
    if args.bucket_dir:
        return Path(args.bucket_dir)
    from paths import local_nas_period  # noqa: E402

    return local_nas_period() / args.bucket


def upload_excel_to_nas(local_xlsx: Path, bucket: str) -> str | None:
    from nas_admin import ROOT, nas_admin  # noqa: E402

    nas = nas_admin()
    if not nas.available:
        return "NAS unavailable"
    dest_path = f"{ROOT}/{bucket}/{local_xlsx.name}"
    resp = nas._fl.upload_file(
        dest_path=dest_path,
        file_path=str(local_xlsx),
        create_parents=True,
        overwrite=True,
        progress_bar=False,
    )
    ok = isinstance(resp, dict) and resp.get("success")
    if not ok and isinstance(resp, tuple) and len(resp) >= 2:
        ok = resp[1].get("success") if isinstance(resp[1], dict) else False
    return dest_path if ok else f"upload failed: {resp!s}"[:200]


def write_excel_sheets(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for name, frame in sheets.items():
            safe = name[:31]
            frame.to_excel(w, sheet_name=safe, index=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default="账期20261004-20261103")
    ap.add_argument("--bucket-dir", default="", help="覆盖 --bucket，直接指定本地同步目录")
    ap.add_argument(
        "--exchange-month",
        default="",
        help="和财务部共享/汇率 列名 YYYYMM（默认从桶名推导；显式不一致时报错，需 --force-month）",
    )
    ap.add_argument(
        "--force-month",
        action="store_true",
        help="允许 --exchange-month 与桶账期月不一致（只在确认错配是刻意的场景用）",
    )
    ap.add_argument(
        "--allow-out-of-period",
        action="store_true",
        help="强制纳入内部 settlement-end-date 不在账期桶窗口内的 txt（默认排除，防跨月重复计入）",
    )
    ap.add_argument(
        "--out-dir",
        default="",
        help="可选镜像目录；默认定稿 xlsx 写在账期桶根目录",
    )
    ap.add_argument("--write-gsheet", action="store_true")
    ap.add_argument("--sort-gsheet-tabs", action="store_true", help="写 GSheet 后按 Colab 规则排序附加费&Tax 标签")
    ap.add_argument("--upload-nas", action="store_true")
    ap.add_argument("--phase1-only", action="store_true", help="只出 Tax 相关 sheet（跳过探索/FBA 多 sheet）")
    ap.add_argument("--dry-run", action="store_true", help="只读 txt+汇率，不写 xlsx/gsheet/NAS")
    ap.add_argument("--repair-dir", default="", help="tab 修复缓存目录（默认桶的父目录/.repair_cache_<桶名>）")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="有重复文件/读失败/行数对不上/币种未匹配/账号行数不符时非 0 退出（默认只打印）",
    )
    args = ap.parse_args()

    bucket_dir = resolve_bucket_dir(args)
    bucket_name = bucket_dir.name
    # 读写前先校验汇率月与桶一致（否则会拿 7 月汇率算 8 月 Tax）。
    exchange_month = resolve_exchange_month(bucket_name, args.exchange_month, force=args.force_month)
    args.exchange_month = exchange_month
    mirror_dir = Path(args.out_dir) if args.out_dir else None

    read_stats: dict = {}
    df, read_report = read_bucket_amz_txts(
        bucket_dir,
        repair_dir=Path(args.repair_dir) if args.repair_dir else None,
        stats_out=read_stats,
        allow_out_of_period=args.allow_out_of_period,
    )
    print(
        f"bucket={bucket_dir} txt_rows={len(df)} files_ok={sum(1 for r in read_report if r.startswith('OK'))} "
        f"dup={read_stats.get('files_dup')} failed={read_stats.get('files_failed')} "
        f"out_of_period={read_stats.get('files_out_of_period')} "
        f"rows_mismatch={read_stats.get('rows_mismatch')}"
    )
    for line in read_report:
        if line.startswith(("SKIP-DUP", "FAIL", "OUT-OF-PERIOD", "NO-PERIOD-DATE")):
            print(line)
    n_skip_dup = int(read_stats.get("files_dup", 0))
    if n_skip_dup:
        print(f"SKIP-DUP {n_skip_dup} 份同内容 txt 已忽略（只读第一份，避免 Tax 双算）")
    n_out_of_period = int(read_stats.get("files_out_of_period", 0))
    if n_out_of_period:
        print(
            f"OUT-OF-PERIOD {n_out_of_period} 份 txt 的内部结算日不在桶窗口内"
            + ("（--allow-out-of-period 已强制纳入）" if args.allow_out_of_period else "，已排除")
        )

    from tongtool_order_cost.gsheets import client as gs_client  # noqa: E402

    gc = gs_client()
    # 第一张是每个收款币种一行。第二张是货币别名拆开表，同一币种多行，
    # 按收款币种 merge 会把 Tax 乘多遍。
    df_fx, _df_fx_aliases = load_exchange_rate_table(gc, month_col=args.exchange_month)

    if df.empty:
        print("WARN: 无 Amazon txt，停止")
        for line in read_report[:30]:
            print(line)
        raise SystemExit(2)

    df = normalize_posted_dates(df)
    df1 = enrich_with_fx(df, df_fx)
    missing_fx = df1[df1["汇率"].isna()]["currency"].dropna().unique()
    if len(missing_fx):
        print("WARN 缺汇率 currency:", list(missing_fx)[:20])

    df6_detail = tax_summary_df6(df1)
    all_accounts = df1["渠道账号"].dropna().unique()
    df6_gsheet = tax_summary_for_gsheet(df6_detail, all_accounts=all_accounts)
    n_acct_files = df1["渠道账号"].nunique()
    print(
        f"df6 detail={len(df6_detail)} gsheet={len(df6_gsheet)} "
        f"unique_accounts={n_acct_files} tax_rmb={df6_detail['Tax amount人民币'].sum():.2f}"
    )
    if len(df6_gsheet) != n_acct_files:
        print(f"WARN: gsheet 行数 {len(df6_gsheet)} != 渠道账号数 {n_acct_files}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx_name = f"合并Amazon_{bucket_name}_{ts}.xlsx"
    xlsx_path = bucket_dir / xlsx_name

    if args.phase1_only:
        sheets = {
            "数据": df1,
            "账号Tax汇总": df6_detail,
            "账号Tax汇总_按渠道账号单行": df6_gsheet,
        }
    else:
        sheets = build_exploration_tables(df1, gc, bucket_name=bucket_name)

    report = {
        "bucket": bucket_name,
        "bucket_dir": str(bucket_dir),
        "exchange_month": args.exchange_month,
        "txt_rows": int(len(df)),
        "read_stats": read_stats,
        "files": read_report,
        "issue_files": [
            ln
            for ln in read_report
            if ln.startswith(("FAIL", "OUT-OF-PERIOD", "NO-PERIOD-DATE", "SKIP-DUP"))
        ],
        "df6_detail_rows": int(len(df6_detail)),
        "df6_gsheet_rows": int(len(df6_gsheet)),
        "unique_accounts": int(n_acct_files),
        "tax_rmb_sum": float(df6_detail["Tax amount人民币"].sum()),
        "missing_fx": [str(x) for x in missing_fx],
        "xlsx": str(xlsx_path),
        "excel_sheets": list(sheets.keys()),
    }

    strict_failures = []
    if n_skip_dup:
        strict_failures.append(f"SKIP-DUP={n_skip_dup}")
    if n_out_of_period:
        strict_failures.append(f"OUT-OF-PERIOD={n_out_of_period}")
    if read_stats.get("files_failed"):
        strict_failures.append(f"FAIL={read_stats['files_failed']}")
    if read_stats.get("rows_mismatch"):
        strict_failures.append(f"rows_mismatch={read_stats['rows_mismatch']}")
    if len(missing_fx):
        strict_failures.append(f"missing_fx={list(missing_fx)[:5]}")
    if len(df6_gsheet) != n_acct_files:
        strict_failures.append(f"gsheet_rows={len(df6_gsheet)}!=accounts={n_acct_files}")
    report["strict_failures"] = strict_failures
    if strict_failures:
        print("STRICT 检查未通过:", "; ".join(strict_failures))
        for ln in report["issue_files"][:20]:
            print(" ", ln)

    if args.dry_run:
        print(json.dumps({k: report[k] for k in report if k != "files"}, ensure_ascii=False, indent=2))
        if args.strict and strict_failures:
            raise SystemExit(1)
        return

    write_excel_sheets(xlsx_path, sheets)
    print("wrote", xlsx_path)
    if mirror_dir:
        mirror_dir.mkdir(parents=True, exist_ok=True)
        mirror_path = mirror_dir / xlsx_name
        write_excel_sheets(mirror_path, sheets)
        print("mirror", mirror_path)
        report["mirror_xlsx"] = str(mirror_path)

    if args.write_gsheet:
        ws_name = tax_worksheet_name(bucket_name)
        write_df_to_gsheet(df6_gsheet, gc, worksheet=ws_name)
        print(f"gsheet 附加费&Tax / {ws_name} rows={len(df6_gsheet)} (one row per 渠道账号)")
        report["gsheet_worksheet"] = ws_name
        if args.sort_gsheet_tabs:
            sort_additional_fee_tax_tabs(gc, pin_worksheet=ws_name)
            print("gsheet tabs sorted (Colab 附加费/Tax 规则)")

    if args.upload_nas:
        dest = upload_excel_to_nas(xlsx_path, bucket_name)
        print("NAS upload:", dest)
        report["nas_upload"] = dest

    rep_dir = mirror_dir or bucket_dir
    rep_path = rep_dir / f"run_{bucket_name}_{ts}.json"
    rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report", rep_path)
    if args.strict and strict_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
