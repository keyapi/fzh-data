# -*- coding: utf-8 -*-
"""D 批只读命令：单期 Amazon 三方对账（赛狐 groupPage ↔ 账期桶 txt ↔ 钉钉 OA）。

    uv run python amazon_period_tax/scripts/reconcile_period.py \
        --period 2026-07 \
        --bucket-dir "<本地同步盘>/账期20260704-20260803" \
        --oa-export "<工作目录>/核算定稿_202607.xlsx" \
        --groups-cache "<工作目录>/_d_groups_2026-07.json" \
        --out "<工作目录>/recon_2026-07.json"

- **只读**：只写 ``--out`` 指定的 JSON 报告；不写 GSheet / NAS / Excel，不刷新快照，
  不落 tab 修复缓存（``write_repairs=False``）。
- tx 事实来自 E1 ``read_bucket_amz_txts`` 的同一次读取（不重复扫描）。
- ``--date-tolerance-days`` 是**诊断**参数；没有已批准 ``DATE_TOLERANCE`` 例外时保持 0。
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date

from pathlib import Path

_HERE = Path(__file__).resolve()
_PKG = _HERE.parents[1]
_REPO = _HERE.parents[2]
_DING = _REPO / "dingtalk" / "dingtalk_oa_approval"
for _p in (_REPO, _PKG, _DING, _REPO / "SELLFOX_API"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from bucket_meta import bucket_period_range, bucket_yyyymm  # noqa: E402
from channel_canonical import canonical_account  # noqa: E402
from ding_xlsx import enrich, read_dingtalk_xlsx  # noqa: E402
from parse import keep_approval  # noqa: E402
from read_amz_txt import read_bucket_amz_txts  # noqa: E402
from reconciliation import (  # noqa: E402
    ExceptionBook,
    fetch_groups,
    load_cached_groups,
    oa_facts_from_frame,
    reconcile,
    store_account_map,
    summary_lines,
    txt_facts_from_read,
)
from source_ledger import SourceLedger  # noqa: E402


def month_range(period: str, buffer_days: int = 0) -> tuple[str, str]:
    y, m = int(period[:4]), int(period[5:7])
    last = calendar.monthrange(y, m)[1]
    start = date(y, m, 1)
    end = date(y, m, last)
    from datetime import timedelta

    return (start - timedelta(days=buffer_days)).isoformat(), (end + timedelta(days=buffer_days)).isoformat()


def load_store_map(path: str | Path | None) -> dict[str, str]:
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return {str(k): canonical_account(str(v)) for k, v in raw.items()}
    default = _REPO / "channel_account_sync" / "out" / "channel_account_gsheet.json"
    if not default.is_file():
        return {}
    raw = json.loads(default.read_text(encoding="utf-8"))
    mapping = store_account_map(raw.get("header") or [], raw.get("rows") or [])
    # 店铺账号也要走同一套别名规范化（如 AMZRUYANGUS → AMZBJRYECLTDUS），否则与 txt/OA 身份不一致。
    return {store: canonical_account(account) for store, account in mapping.items()}


def load_oa_frame(path: str | Path) -> tuple[pd.DataFrame, dict]:
    frame = enrich(read_dingtalk_xlsx(Path(path)))
    if frame.empty:
        return frame, {"rows_read": 0, "rows_dropped_not_approved": 0}
    status = frame["审批状态"] if "审批状态" in frame.columns else pd.Series([""] * len(frame))
    result = frame["审批结果"] if "审批结果" in frame.columns else pd.Series([""] * len(frame))

    def _clean(v) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        return str(v).strip()

    keep = [keep_approval(_clean(s), _clean(r)) for s, r in zip(status, result)]
    return frame.loc[keep].copy(), {
        "rows_read": int(len(frame)),
        "rows_dropped_not_approved": int(len(frame) - sum(keep)),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True, help="YYYY-MM")
    ap.add_argument("--bucket-dir", required=True, help="账期桶目录（只读）")
    ap.add_argument("--oa-export", required=True, help="OA 销售收款确认单定稿 xlsx")
    ap.add_argument("--groups-cache", default="", help="离线 groupPage 原始 JSON（优先于联网）")
    ap.add_argument("--save-groups", default="", help="联网拉取后保存 groupPage 原始 JSON（只写这里）")
    ap.add_argument("--env-file", action="append", default=[], help="Sellfox 凭证 .env（可重复）")
    ap.add_argument("--out", required=True, help="只读对账 JSON 输出")
    ap.add_argument("--exceptions", default="", help="批准例外 JSON")
    ap.add_argument("--store-map", default="", help="店铺→渠道账号 JSON（缺省读渠道主数据快照）")
    ap.add_argument("--date-tolerance-days", type=int, default=0, help="诊断用日期容差；默认 0")
    ap.add_argument("--window-buffer-days", type=int, default=0, help="groupPage 查询窗口外扩天数（迟交边界）")
    ap.add_argument("--force-month", action="store_true", help="允许 --period 与桶名账期月不一致")
    args = ap.parse_args()

    period = args.period
    bucket_dir = Path(args.bucket_dir)
    if not bucket_dir.is_dir():
        raise SystemExit(f"账期桶不存在: {bucket_dir}")
    bucket_month = bucket_yyyymm(bucket_dir.name)
    if bucket_month and bucket_month[:4] + "-" + bucket_month[4:6] != period and not args.force_month:
        raise SystemExit(f"--period {period} 与桶 {bucket_dir.name} 账期月不一致；确认请加 --force-month")

    store_map = load_store_map(args.store_map or None)

    # 1) 赛狐应有集（只读）
    fetch_meta: dict = {}
    if args.groups_cache:
        fetched = load_cached_groups(args.groups_cache, store_map)
        fetch_meta = {
            "source": "cache",
            "path": args.groups_cache,
            "window": [fetched.start, fetched.end],
            "pages": fetched.pages,
            "total_size": fetched.total_size,
        }
    else:
        from client import SellfoxClient, SellfoxConfig  # noqa: E402

        cfg = SellfoxConfig.from_env(*[Path(p) for p in args.env_file])
        client = SellfoxClient(cfg)
        start, end = month_range(period, args.window_buffer_days)
        fetched = fetch_groups(client.signed_post, start, end, store_to_account=store_map)
        fetch_meta = {
            "source": "api",
            "mode": cfg.mode,
            "window": [start, end],
            "pages": fetched.pages,
            "total_size": fetched.total_size,
        }
        if args.save_groups:
            Path(args.save_groups).write_text(
                json.dumps(
                    {"period": period, "window": [start, end], "pages": fetched.pages,
                     "total_size": fetched.total_size, "groups": [g.raw for g in fetched.groups]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    # 2) 桶 txt（复用 E1 同一次读取；只读，不落修复缓存）
    stats: dict = {}
    ledger = SourceLedger(bucket_dir.name, str(bucket_dir))
    df, _reports = read_bucket_amz_txts(
        bucket_dir,
        repair_dir=None,
        stats_out=stats,
        period_range=bucket_period_range(bucket_dir.name),
        write_repairs=False,
        ledger_out=ledger,
    )
    txt_facts, txt_inventory = txt_facts_from_read(df, ledger)

    # 3) OA
    oa_frame, oa_filter = load_oa_frame(args.oa_export)
    book = ExceptionBook.from_json(args.exceptions) if args.exceptions else ExceptionBook()
    oa_facts, oa_out, _problems = oa_facts_from_frame(
        oa_frame,
        period,
        book=book,
        canonical_account=canonical_account,
    )
    # 只保留本期边界相关行（其它平台行只计数，完整明细属于 N 批/非 Amazon 证据）
    from collections import Counter

    out_counts = Counter((r.get("reason"), r.get("platform")) for r in oa_out)
    oa_out_compact = {
        "counts": {f"{reason}:{platform or '-'}": n for (reason, platform), n in sorted(out_counts.items())},
        "other_period_amazon": [r for r in oa_out if r.get("reason") == "other_period"],
    }

    # 4) 对账
    result = reconcile(
        period,
        fetched.groups,
        txt_facts,
        oa_facts,
        book=book,
        txt_inventory=txt_inventory,
        oa_out_of_scope=oa_out_compact,
        fetch_meta={**fetch_meta, "e1_stats": {k: v for k, v in stats.items() if k != "partition"}, "oa_filter": oa_filter},
        default_tolerance_days=max(0, args.date_tolerance_days),
    )
    payload = result.to_dict()
    payload["diagnostic"] = {
        "date_tolerance_days": max(0, args.date_tolerance_days),
        "ratified": bool(args.date_tolerance_days and args.exceptions),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(summary_lines(result)))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
