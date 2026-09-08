"""通途 xlsx → 分流查询 UPS/FedEx/GLS → 共享异常表。"""

from __future__ import annotations

import csv
import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from fedex_track.batch import BatchItem as FdxItem
from fedex_track.batch import Record as FdxRecord
from fedex_track.batch import run_batch as run_fedex
from ups_track.batch import BatchItem as UpsItem
from ups_track.batch import Record as UpsRecord
from ups_track.batch import run_batch as run_ups

from .ingest import IngestReport, TongtuRow, ingest_tongtu
from .normalize import classified_row, fedex_record_to_summaries, gls_record_to_summaries, ups_record_to_summaries
from .ops_excel import write_ops_workbook


def _write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8-sig")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _ident_map(report: IngestReport) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in report.rows:
        if row.number and row.number not in out:
            out[row.number] = row.ident
    return out


def _unique_rows(rows: list[TongtuRow]) -> list[TongtuRow]:
    seen: set[str] = set()
    out: list[TongtuRow] = []
    for r in rows:
        if not r.number or r.number in seen:
            continue
        seen.add(r.number)
        out.append(r)
    return out


@dataclass
class GlsQueryResult:
    number: str
    ok: bool
    error: str = ""
    parcel: Any = None


def _query_gls(query: Callable, rows: list[TongtuRow], workers: int = 1) -> list[GlsQueryResult]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from gls_track.client import GlsTrackError

    def _one(r: TongtuRow) -> GlsQueryResult:
        postal = (r.ident.get("邮编") or "").strip() or None
        try:
            parcel = query(r.number, postal)
            return GlsQueryResult(number=r.number, ok=True, parcel=parcel)
        except GlsTrackError as exc:
            return GlsQueryResult(number=r.number, ok=False, error=str(exc))
        except Exception as exc:
            return GlsQueryResult(number=r.number, ok=False, error=f"{type(exc).__name__}: {exc}")

    if workers <= 1 or len(rows) <= 1:
        return [_one(r) for r in rows]
    recs: list[GlsQueryResult | None] = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, r): i for i, r in enumerate(rows)}
        for fut in as_completed(futs):
            recs[futs[fut]] = fut.result()
    return [r for r in recs if r is not None]


def run_report(
    tt_xlsx: str,
    out_xlsx: str,
    *,
    prefix: str,
    mock: bool = False,
    ups_query: Callable | None = None,
    fedex_query: Callable | None = None,
    gls_query: Callable | None = None,
    limit: int = 0,
    workers: int = 1,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    report = ingest_tongtu(tt_xlsx)
    ups_rows = _unique_rows(report.ups)
    fdx_rows = _unique_rows(report.fedex)
    gls_rows = _unique_rows(report.gls)
    if limit:
        ups_rows = ups_rows[:limit]
        fdx_rows = fdx_rows[:limit]
        gls_rows = gls_rows[:limit]
    called = {"ups": False, "fedex": False, "gls": False}
    ups_recs: list[UpsRecord] = []
    fdx_recs: list[FdxRecord] = []
    gls_recs: list[GlsQueryResult] = []
    w = 1 if mock else max(1, workers)
    retries = 0 if mock else 1
    print(
        f"query UPS {len(ups_rows)} / FedEx {len(fdx_rows)} / GLS {len(gls_rows)} "
        f"workers={w} retries={retries}",
        flush=True,
    )
    if ups_rows:
        called["ups"] = True
        items = [UpsItem(number=r.number, remark=r.ident.get("邮寄方式", "")) for r in ups_rows]
        if ups_query is None:
            raise ValueError("缺少 UPS query")
        ups_recs = run_ups(ups_query, items, workers=w, retries=retries)
        print(f"UPS done {sum(1 for r in ups_recs if r.ok)}/{len(ups_recs)}", flush=True)
    if fdx_rows:
        called["fedex"] = True
        items = [FdxItem(number=r.number, remark=r.ident.get("邮寄方式", "")) for r in fdx_rows]
        if fedex_query is None:
            raise ValueError("缺少 FedEx query")
        fdx_recs = run_fedex(fedex_query, items, workers=w, retries=retries)
        print(f"FedEx done {sum(1 for r in fdx_recs if r.ok)}/{len(fdx_recs)}", flush=True)
    if gls_rows:
        called["gls"] = True
        if gls_query is None:
            raise ValueError("缺少 GLS query")
        gls_recs = _query_gls(gls_query, gls_rows, workers=w)
        print(f"GLS done {sum(1 for r in gls_recs if r.ok)}/{len(gls_recs)}", flush=True)
    ident = _ident_map(report)
    now = now or pd.Timestamp(_dt.datetime.now())
    classified = []
    ups_sum, fdx_sum, gls_sum = [], [], []
    for rec in ups_recs:
        for s in ups_record_to_summaries(rec):
            ups_sum.append(s)
            classified.append(classified_row(s, ident.get(rec.number, {}), now, "ups"))
    for rec in fdx_recs:
        for s in fedex_record_to_summaries(rec):
            fdx_sum.append(s)
            classified.append(classified_row(s, ident.get(rec.number, {}), now, "fedex"))
    for rec in gls_recs:
        for s in gls_record_to_summaries(rec):
            gls_sum.append(s)
            classified.append(classified_row(s, ident.get(rec.number, {}), now, "gls"))
    parked_rows = []
    for r in report.parked:
        parked_rows.append({
            "跟踪号": r.number,
            "跳过原因": r.route.reason,
            "邮寄方式": r.ident.get("邮寄方式", ""),
            "渠道": r.ident.get("渠道", ""),
            "订单号": r.ident.get("订单号", ""),
            "包裹号": r.ident.get("包裹号", ""),
        })
    _write_csv(f"{prefix}-ups.summary.csv", ups_sum)
    _write_csv(f"{prefix}-fedex.summary.csv", fdx_sum)
    _write_csv(f"{prefix}-gls.summary.csv", gls_sum)
    merged = [{k: v for k, v in row.items() if k != "_key"} for row in classified]
    _write_csv(f"{prefix}.summary.csv", merged)
    df = pd.DataFrame(classified)
    parked = pd.DataFrame(parked_rows)
    write_ops_workbook(
        df if len(df) else pd.DataFrame(columns=["_key"]),
        out_xlsx,
        title="尾程运营异常总览（Amazon 口径 · 营业日）",
        slow_label="承运延误",
        notes_title="混合承运商异常报表口径",
        parked=parked,
    )
    return {
        "in": len(report.rows),
        "ups": len(ups_rows),
        "fedex": len(fdx_rows),
        "gls": len(gls_rows),
        "parked": len(report.parked),
        "classified": len(classified),
        "called": called,
        "out": out_xlsx,
    }
