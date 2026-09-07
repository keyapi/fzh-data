"""通途 xlsx → 分流查询 UPS/FedEx → 共享异常表。"""

from __future__ import annotations

import csv
import datetime as _dt
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from fedex_track.batch import BatchItem as FdxItem
from fedex_track.batch import Record as FdxRecord
from fedex_track.batch import run_batch as run_fedex
from ups_track.batch import BatchItem as UpsItem
from ups_track.batch import Record as UpsRecord
from ups_track.batch import run_batch as run_ups

from .ingest import IngestReport, ingest_tongtu
from .normalize import classified_row, fedex_record_to_summaries, ups_record_to_summaries
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


def run_report(
    tt_xlsx: str,
    out_xlsx: str,
    *,
    prefix: str,
    mock: bool = False,
    ups_query: Callable | None = None,
    fedex_query: Callable | None = None,
    limit: int = 0,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    report = ingest_tongtu(tt_xlsx)
    ups_rows = report.ups
    fdx_rows = report.fedex
    if limit:
        ups_rows = ups_rows[:limit]
        fdx_rows = fdx_rows[:limit]
    called = {"ups": False, "fedex": False}
    ups_recs: list[UpsRecord] = []
    fdx_recs: list[FdxRecord] = []
    if ups_rows:
        called["ups"] = True
        items = [UpsItem(number=r.number, remark=r.ident.get("邮寄方式", "")) for r in ups_rows]
        if ups_query is None:
            raise ValueError("缺少 UPS query")
        ups_recs = run_ups(ups_query, items, workers=1, retries=0)
    if fdx_rows:
        called["fedex"] = True
        items = [FdxItem(number=r.number, remark=r.ident.get("邮寄方式", "")) for r in fdx_rows]
        if fedex_query is None:
            raise ValueError("缺少 FedEx query")
        fdx_recs = run_fedex(fedex_query, items, workers=1, retries=0)
    ident = _ident_map(report)
    now = now or pd.Timestamp(_dt.datetime.now())
    classified = []
    ups_sum, fdx_sum = [], []
    for rec in ups_recs:
        for s in ups_record_to_summaries(rec):
            ups_sum.append(s)
            classified.append(classified_row(s, ident.get(rec.number, {}), now, "ups"))
    for rec in fdx_recs:
        for s in fedex_record_to_summaries(rec):
            fdx_sum.append(s)
            classified.append(classified_row(s, ident.get(rec.number, {}), now, "fedex"))
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
        "parked": len(report.parked),
        "classified": len(classified),
        "called": called,
        "out": out_xlsx,
    }
