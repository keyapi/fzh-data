# -*- coding: utf-8 -*-
"""Amazon 账期 txt → Tax 汇总 Excel + GSheet（本地/NAS 桶，替代 Colab「税账期TXT 挂载Gdrive」）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from correction_policy import (  # noqa: E402
    PolicyError,
    build_proposals,
    load_policy,
    manifest_policy_fields,
    policy_errors,
    write_gate_errors,
)
from exchange_rate import load_exchange_rate_table  # noqa: E402
from explore_tables import build_exploration_tables  # noqa: E402
from gsheet_tax import sort_additional_fee_tax_tabs, tax_worksheet_name, write_df_to_gsheet  # noqa: E402
from normalize_dates import normalize_posted_dates  # noqa: E402
from phase3_merge import load_channel_accounts, tax_account_problems  # noqa: E402
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


def collect_strict_failures(
    read_stats: dict,
    *,
    n_skip_dup: int,
    n_out_of_period: int,
    missing_fx,
    gsheet_rows: int,
    n_accounts: int,
    n_needs_review: int = 0,
) -> list[str]:
    """`--strict` 的失败清单：SKIP-DUP / OUT-OF-PERIOD / FAIL / NEEDS-REVIEW 任一 >0 即非空。"""
    failures: list[str] = []
    if n_skip_dup:
        failures.append(f"SKIP-DUP={n_skip_dup}")
    if n_out_of_period:
        failures.append(f"OUT-OF-PERIOD={n_out_of_period}")
    if read_stats.get("files_failed"):
        failures.append(f"FAIL={read_stats['files_failed']}")
    if n_needs_review or read_stats.get("files_needs_review"):
        failures.append(f"NEEDS-REVIEW={n_needs_review or read_stats['files_needs_review']}")
    if read_stats.get("rows_mismatch"):
        failures.append(f"rows_mismatch={read_stats['rows_mismatch']}")
    missing = [str(x) for x in (missing_fx if missing_fx is not None else [])]
    if missing:
        failures.append(f"missing_fx={missing[:5]}")
    if gsheet_rows != n_accounts:
        failures.append(f"gsheet_rows={gsheet_rows}!=accounts={n_accounts}")
    return failures


def enforce_write_gate(
    *,
    strict: bool,
    strict_failures: list[str],
    master_problems: list[str],
    publish_requested: bool,
    publish_blockers: list[str] | None = None,
    policy_problems: list[str] | None = None,
) -> None:
    """写前生效的硬门禁（A3/T03 + A4/T04 + E1 文件总账 + F 修正政策）。

    - ``strict_failures`` 非空且 ``--strict``：**任何写入之前**退出，不再先写后返回 1。
    - ``master_problems`` 非空且请求发布（--write-gsheet / --upload-nas）：无论是否 strict 都拒绝，
      未知账号/缺人员/快照过期/ live 与快照不一致的 Tax 不得发布。
    - ``publish_blockers`` 非空且请求发布：源文件总账未闭合（FAIL / NEEDS-REVIEW /
      未审定跨期 / 无内部日期）时同样拒绝，不依赖 ``--strict``。
    - ``policy_problems`` 非空：用户显式给了修正政策/凭据却无效（缺/过期/未授权 T2/
      hash 变化），任何写入（含本地 xlsx）之前一律拒绝，不依赖 ``--strict`` 与发布开关。
    """
    if strict and strict_failures:
        raise SystemExit(f"STRICT 检查未通过（写前拒绝）: {'; '.join(strict_failures)}")
    if policy_problems:
        raise SystemExit("修正政策未通过（拒绝写入）: " + "; ".join(policy_problems))
    if publish_requested and publish_blockers:
        raise SystemExit(
            "源文件总账未通过（拒绝发布）: " + "; ".join(publish_blockers)
        )
    if publish_requested and master_problems:
        raise SystemExit(
            "Tax 账号/人员主数据校验未通过（拒绝发布）: " + "; ".join(master_problems)
        )


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
    ap.add_argument(
        "--correction-policy",
        default="",
        help="git 外预授权政策 JSON（F 批）：缺/过期/未授权 T2 时拒绝任何写入",
    )
    ap.add_argument(
        "--corrections",
        default="",
        help="可选 corrections JSON；配合 --correction-policy 产出 proposal/授权判定",
    )
    args = ap.parse_args()

    bucket_dir = resolve_bucket_dir(args)
    bucket_name = bucket_dir.name
    # 读写前先校验汇率月与桶一致（否则会拿 7 月汇率算 8 月 Tax）。
    exchange_month = resolve_exchange_month(bucket_name, args.exchange_month, force=args.force_month)
    args.exchange_month = exchange_month
    mirror_dir = Path(args.out_dir) if args.out_dir else None

    # F：修正政策（git 外 JSON）。无 --correction-policy 时行为不变；有则任何缺/过期/
    # 未授权 T2 都在写前拒绝发布，与 --strict 无关。
    correction_policy = None
    correction_proposals: list = []
    policy_problems: list[str] = []
    if args.correction_policy:
        try:
            correction_policy = load_policy(Path(args.correction_policy))
        except PolicyError as e:
            policy_problems.append(f"POLICY: {e}")
    elif args.corrections:
        policy_problems.append(
            "CORRECTIONS: 给了 --corrections 但缺 --correction-policy，无法授权/校验"
        )
    if correction_policy is not None:
        if args.corrections:
            try:
                payload = json.loads(Path(args.corrections).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                policy_problems.append(f"CORRECTIONS: 读取失败: {e}")
            else:
                try:
                    correction_proposals = build_proposals(payload, period=args.exchange_month)
                except PolicyError as e:
                    policy_problems.append(f"CORRECTIONS: {e}")
                else:
                    if not correction_proposals:
                        policy_problems.append(
                            f"CORRECTIONS: 凭据里没有 period={args.exchange_month} 的修正"
                        )
        policy_problems.extend(
            write_gate_errors(
                period=args.exchange_month,
                policy=correction_policy,
                proposals=correction_proposals,
            )
        )
        if not correction_proposals:
            policy_problems.extend(f"POLICY: {e}" for e in policy_errors(correction_policy))
    if policy_problems:
        print("POLICY 修正政策未通过:", "; ".join(policy_problems))

    read_stats: dict = {}
    df, read_report = read_bucket_amz_txts(
        bucket_dir,
        repair_dir=Path(args.repair_dir) if args.repair_dir else None,
        stats_out=read_stats,
        allow_out_of_period=args.allow_out_of_period,
        write_repairs=not args.dry_run,  # R05：dry-run 只读，不落修复缓存
    )
    print(
        f"bucket={bucket_dir} txt_rows={len(df)} files_ok={sum(1 for r in read_report if r.startswith('OK'))} "
        f"dup={read_stats.get('files_dup')} failed={read_stats.get('files_failed')} "
        f"out_of_period={read_stats.get('files_out_of_period')} "
        f"needs_review={read_stats.get('files_needs_review')} "
        f"rows_mismatch={read_stats.get('rows_mismatch')}"
    )
    for line in read_report:
        if line.startswith(
            ("SKIP-DUP", "FAIL", "OUT-OF-PERIOD", "NO-PERIOD-DATE", "NEEDS-REVIEW", "APPROVED-EXCLUDED", "INVENTORY")
        ):
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

    # A3/T03：发布前用 **live** 渠道主表核对每个渠道账号 + 当期运营人员（不能原样发布 unknown）。
    master_problems: list[str] = []
    _acct_view = None
    _df_explode = None
    try:
        _acct_view, _df_explode = load_channel_accounts(gc, args.exchange_month)
        master_problems = tax_account_problems(df6_gsheet, _acct_view, only_nonzero=False)
    except Exception as e:  # 主表读不到/缺当期列 = 主数据不可校验，同样是门禁失败
        master_problems = [f"渠道主表校验失败: {e}"]
    # C1：快照 metadata + live/snapshot 投影一致（仅发布时校验，诊断/本地 xlsx 不受影响）
    master_gate = None
    if args.write_gsheet or args.upload_nas:
        from channel_canonical import snapshot_path
        from master_data import default_expected_source, publish_gate_problems

        snap = None
        snap_err = None
        try:
            snap = json.loads(Path(snapshot_path()).read_text(encoding="utf-8"))
        except Exception as e:
            snap_err = f"{type(e).__name__}: {e}"
        master_gate = publish_gate_problems(
            exchange_month=args.exchange_month,
            acct_view=_acct_view,
            df_explode=_df_explode,
            snapshot=snap,
            snapshot_error=snap_err,
            batch_accounts=df6_gsheet["渠道账号"].tolist(),
            batch_aliases=df6_gsheet["渠道账号"].tolist(),
            expected_source=default_expected_source(),
        )
        master_problems.extend(master_gate.problems)
    if master_problems:
        print("MASTER 主数据校验未通过:", "; ".join(master_problems))
    if master_gate and master_gate.unknown_alias_candidates:
        print(
            "MASTER 未知别名候选（不自动写回主表）:",
            master_gate.unknown_alias_candidates[:10],
        )

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
            if ln.startswith(
                ("FAIL", "OUT-OF-PERIOD", "NO-PERIOD-DATE", "SKIP-DUP", "NEEDS-REVIEW", "APPROVED-EXCLUDED")
            )
        ],
        "ledger_blockers": list(read_stats.get("publish_blockers") or []),
        "ledger_partition": dict(read_stats.get("partition") or {}),
        "inventory": dict(read_stats.get("inventory") or {}),
        "df6_detail_rows": int(len(df6_detail)),
        "df6_gsheet_rows": int(len(df6_gsheet)),
        "unique_accounts": int(n_acct_files),
        "tax_rmb_sum": float(df6_detail["Tax amount人民币"].sum()),
        "missing_fx": [str(x) for x in missing_fx],
        "xlsx": str(xlsx_path),
        "excel_sheets": list(sheets.keys()),
    }

    strict_failures = collect_strict_failures(
        read_stats,
        n_skip_dup=n_skip_dup,
        n_out_of_period=n_out_of_period,
        missing_fx=missing_fx,
        gsheet_rows=len(df6_gsheet),
        n_accounts=n_acct_files,
        n_needs_review=int(read_stats.get("files_needs_review", 0)),
    )
    report["strict_failures"] = strict_failures
    report["master_problems"] = master_problems
    report["policy_problems"] = policy_problems
    report["unknown_alias_candidates"] = list(
        getattr(master_gate, "unknown_alias_candidates", []) or []
    )
    if strict_failures:
        print("STRICT 检查未通过:", "; ".join(strict_failures))
        for ln in report["issue_files"][:20]:
            print(" ", ln)

    publish_blockers = list(read_stats.get("publish_blockers") or [])
    if args.dry_run:
        print(json.dumps({k: report[k] for k in report if k != "files"}, ensure_ascii=False, indent=2))
        if (
            (args.strict and strict_failures)
            or master_problems
            or policy_problems
            or ((args.write_gsheet or args.upload_nas) and publish_blockers)
        ):
            raise SystemExit(1)
        return

    # A4/T04：strict 失败必须在**任何写入**（xlsx / GSheet / NAS）之前生效。
    enforce_write_gate(
        strict=args.strict,
        strict_failures=strict_failures,
        master_problems=master_problems,
        publish_requested=bool(args.write_gsheet or args.upload_nas),
        publish_blockers=publish_blockers,
        policy_problems=policy_problems,
    )

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
        try:
            mdir = Path(
                os.environ.get("PERIOD_WRITE_MANIFEST_DIR", str(Path.cwd() / "reports" / "_write_runs"))
            )
            mdir.mkdir(parents=True, exist_ok=True)
            run_id = f"{ts}_tax_{args.exchange_month}"
            mirror = report.get("mirror_xlsx")
            manifest = {
                "run_id": run_id,
                "kind": "tax",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "bucket": bucket_name,
                "bucket_dir": str(bucket_dir),
                "exchange_month": args.exchange_month,
                "tax_worksheet": ws_name,
                "rows": len(df6_gsheet),
                "tax_rmb": report.get("tax_rmb_sum"),
                "read_stats": read_stats if isinstance(read_stats, dict) else {"value": read_stats},
                "mirror_xlsx": mirror,
                "mirror_md5": (
                    hashlib.md5(Path(mirror).read_bytes()).hexdigest()
                    if mirror and Path(mirror).is_file()
                    else None
                ),
            }
            # F：发布清单绑定 policy/proposal/逐条 correction/证据 hash。
            manifest.update(
                manifest_policy_fields(
                    policy=correction_policy, proposals=correction_proposals
                )
            )
            mp = mdir / f"{run_id}.json"
            mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            report["manifest_path"] = str(mp)
            print("manifest", mp)
        except Exception as e:  # manifest 失败不影响已写入的 Tax，但必须可见
            print("[warn] tax manifest 未写入:", e)

    if args.upload_nas:
        dest = upload_excel_to_nas(xlsx_path, bucket_name)
        print("NAS upload:", dest)
        report["nas_upload"] = dest

    rep_dir = mirror_dir or bucket_dir
    rep_path = rep_dir / f"run_{bucket_name}_{ts}.json"
    rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report", rep_path)


if __name__ == "__main__":
    main()
