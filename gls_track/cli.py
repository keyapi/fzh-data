"""gls_track CLI — GLS 单号批量查轨迹（公开 REST，免登录）。

用法：
  python -m gls_track.cli query --input <tongtu.xlsx|number.txt|number.csv> --out result

输入：
  - .xlsx/.xls：通途导出；自动按 邮寄方式 前缀(默认 gls-poland) 筛出 GLS 行、
    **一格多号自动拆分**(逗号/空格)、按 跟踪号 去重、取 邮编（目的邮编，明细需要）。
    无邮编的行只出摘要（状态）。非 GLS 号(UPS 1Z/allegro …U/碎片)会照查并 404 → 报表落「数据异常/查无」待清源。
  - .txt：每行一个跟踪号，可后接目的邮编（空格分隔）；无邮编只出摘要。
  - .csv：表头含 跟踪号（+可选 邮编）；否则按 txt 处理。

输出（同前缀）：
  - {out}.summary.csv ：每包裹一行：状态/是否交付/交付·数据录入·交接GLS·最近事件时间/错误
  - {out}.timeline.csv：每事件一行（有邮编+明细时）
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from concurrent.futures import ThreadPoolExecutor, as_completed

from .client import DEFAULT_BASE, GlsTrackClient, GlsTrackError

SUMMARY_COLS = [
    "跟踪号", "国家/地区", "邮编", "当前状态", "状态说明", "已交付",
    "交付时间", "数据录入时间", "交接GLS时间", "最近事件时间", "客户引用", "事件数", "错误",
]
TIMELINE_COLS = ["跟踪号", "事件时间", "事件", "城市", "国家代码"]


def _split_cell(v: str) -> list[str]:
    """拆 跟踪号 单元格：一格可能塞多号(逗号/空格分隔)，逐个拆开。"""
    import re as _re
    return [t for t in _re.split(r"[,，;；\s]+", str(v).strip()) if t]


def _load_records(input_path: str, carrier_prefix: str, limit: int | None) -> list[dict]:
    p = Path(input_path)
    ext = p.suffix.lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(p)
        for col in ("邮寄方式", "跟踪号"):
            if col not in df.columns:
                raise SystemExit(f"xlsx 缺列 {col!r}（需要 邮寄方式/跟踪号；可给 邮编/国家/地区）")
        df["邮寄方式"] = df["邮寄方式"].fillna("").astype(str)
        df["跟踪号"] = df["跟踪号"].fillna("").astype(str).str.strip()
        df = df[df["邮寄方式"].str.lower().str.startswith(carrier_prefix.lower())]
        df = df[df["跟踪号"] != ""]
        has_postal = "邮编" in df.columns
        has_country = "国家/地区" in df.columns
        # 一格多号 → 逐号拆开（同包裹/订单多号不再整格 404），按号去重
        seen: set[str] = set()
        records: list[dict] = []
        for _, row in df.iterrows():
            postal = str(row["邮编"]).strip() if has_postal and pd.notna(row["邮编"]) else ""
            country = str(row["国家/地区"]).strip() if has_country and pd.notna(row["国家/地区"]) else ""
            for tok in _split_cell(row["跟踪号"]):
                if tok in seen:
                    continue
                seen.add(tok)
                records.append({"跟踪号": tok, "邮编": postal, "国家/地区": country})
    else:
        records = []
        text = p.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            toks = line.split()
            rec = {"跟踪号": toks[0], "邮编": "", "国家/地区": ""}
            if len(toks) > 1:
                rec["邮编"] = toks[1]
            records.append(rec)
        if ext == ".csv" and records and records[0]["跟踪号"].lower() in ("tracking", "跟踪号"):
            records = records[1:]
    if limit and limit > 0:
        records = records[:limit]
    return records


def _fmt(dt) -> str:
    return dt.isoformat(sep=" ") if dt is not None else ""


def _run_query(args: argparse.Namespace) -> int:
    records = _load_records(args.input, args.carrier_prefix, args.limit)
    if not records:
        print(f"no records to query from {args.input}", file=sys.stderr)
        return 1

    # --resume：跳过已产出 summary 里已有的号（断点续跑，避免整月重查）
    out = Path(args.out)
    summary_path = Path(f"{out}.summary.csv")
    if args.resume and summary_path.exists():
        prev = pd.read_csv(summary_path, encoding="utf-8-sig", dtype={"跟踪号": str})
        skip = {str(x).strip() for x in prev["跟踪号"] if pd.notna(x)}
        records = [r for r in records if r["跟踪号"] not in skip]
        print(f"resume: skip {len(skip)} already-queried; remaining {len(records)}")
    if not records:
        print("no new records to query")
        return 0

    summary_rows: list[dict] = []
    timeline_rows: list[dict] = []
    ok = 0

    # 共享连接池（httpx.Client 线程安全）；限流调研：≤8 并发无 429/403，默认保守 4
    with GlsTrackClient(base_url=args.base_url) as client:

        def one(rec: dict) -> tuple[dict, list[dict]]:
            no = rec["跟踪号"]
            postal = rec.get("邮编", "")
            p = None
            err = ""
            for attempt in range(2):
                try:
                    p = client.track(no, postal or None)
                    err = ""
                    break
                except GlsTrackError as exc:
                    err = str(exc)
                    if attempt == 0 and exc.retriable:
                        time.sleep(1.0)
                        continue
                    break
            row = {
                "跟踪号": no,
                "国家/地区": rec.get("国家/地区", ""),
                "邮编": postal,
                "当前状态": getattr(p, "current_status", "") or "",
                "状态说明": getattr(p, "current_status_text", "") or "",
                "已交付": "是" if getattr(p, "delivered", False) else ("否" if p else ""),
                "交付时间": _fmt(getattr(p, "delivered_dt", None)),
                "数据录入时间": _fmt(getattr(p, "data_entered_dt", None)),
                "交接GLS时间": _fmt(getattr(p, "handed_dt", None)),
                "最近事件时间": _fmt(getattr(p, "last_event_dt", None)),
                "客户引用": getattr(p, "cust_ref", "") or "",
                "事件数": len(getattr(p, "events", []) or []),
                "错误": err,
            }
            tls = []
            if p is not None and p.events:
                for e in p.events:
                    tls.append({
                        "跟踪号": no,
                        "事件时间": _fmt(e.dt),
                        "事件": e.description or "",
                        "城市": e.city or "",
                        "国家代码": e.country_code or "",
                    })
            return row, tls

        def emit(row: dict, tls: list[dict], i: int) -> None:
            nonlocal ok
            summary_rows.append(row)
            timeline_rows.extend(tls)
            if not row["错误"]:
                ok += 1
            detail = row["错误"] or f"{row['事件数']} events"
            print(f"[{i}/{len(records)}] {row['跟踪号']} -> {row['当前状态'] or 'ERROR'} ({detail})")

        if args.workers > 1:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(one, r): r for r in records}
                for i, fut in enumerate(as_completed(futs), 1):
                    rec = futs[fut]
                    try:
                        row, tls = fut.result()
                    except Exception as exc:  # 兜底：未知异常记为该号错误
                        row, tls = {
                            "跟踪号": rec["跟踪号"], "国家/地区": rec.get("国家/地区", ""), "邮编": rec.get("邮编", ""),
                            "当前状态": "", "状态说明": "", "已交付": "", "交付时间": "", "数据录入时间": "",
                            "交接GLS时间": "", "最近事件时间": "", "客户引用": "", "事件数": 0,
                            "错误": f"unexpected: {type(exc).__name__}: {exc}"}, []
                    emit(row, tls, i)
        else:
            for i, rec in enumerate(records, 1):
                emit(*one(rec), i)
                if args.delay and i < len(records):
                    time.sleep(args.delay)

    pd.DataFrame(summary_rows, columns=SUMMARY_COLS).to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(timeline_rows, columns=TIMELINE_COLS).to_csv(Path(f"{out}.timeline.csv"), index=False, encoding="utf-8-sig")
    print(f"wrote {out}.summary.csv ({len(summary_rows)} rows) + {out}.timeline.csv ({len(timeline_rows)} rows); ok={ok} err={len(summary_rows) - ok}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m gls_track.cli", description=__doc__)
    ap.add_argument("--base-url", default=DEFAULT_BASE, help="GLS 公开 REST 前缀")
    sub = ap.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", help="批量查 GLS 轨迹")
    q.add_argument("--input", required=True, help="通途 xlsx 或 txt/csv（每行: 号 [邮编]）")
    q.add_argument("--out", required=True, help="输出前缀，生成 .summary.csv/.timeline.csv")
    q.add_argument("--carrier-prefix", default="gls-poland", help="xlsx 按 邮寄方式 前缀筛选（默认 gls-poland）")
    q.add_argument("--limit", type=int, default=0, help="只查前 N 个包裹（调试/小样本）")
    q.add_argument("--workers", type=int, default=4, help="并发线程数（实测 ≤8 无 429/403；公开接口无 SLA，默认 4 保守）")
    q.add_argument("--delay", type=float, default=0.2, help="每号间隔秒数（仅串行 workers=1 生效；公开接口请温和节流）")
    q.add_argument("--resume", action="store_true", help="跳过 {out}.summary.csv 里已有的号（断点续跑）")
    q.set_defaults(func=_run_query)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
