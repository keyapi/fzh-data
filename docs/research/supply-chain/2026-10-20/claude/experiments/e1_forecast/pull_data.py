#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1 数据拉取：从 43 张通途月表抽取 PB 楔形枕 8 个 SKU 的逐日发货行。

只读 Google Sheets；输出到 experiments/e1_forecast/data/。
不写任何业务系统。

月份归属统一用「发货日期」解析（支持 YYYY-MM-DD / YYYY/M/D / datetime），
不用月表名，也不用 date[:7]。解析失败的行保留在 raw 并把 month 置空，
绝不当作 0 需求。
"""

import csv
import re
import time
from datetime import datetime
from pathlib import Path

import gspread

SA = r"D:/Work/赛狐/Cursor/secrets/gsheets-service-account.json"
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = {
    "TT0031010K0062870",
    "TT0031010K0062871",
    "TT0031010K0062876",
    "TT0031010K0062877",
    "TT0031010K0062878",
    "TT0031010K0062879",
    "TT0031010K0062880",
    "TT0031010K0062881",
}
FIELDS = ["发货日期", "通途SKU", "发货数量", "渠道", "发货仓库"]
MONTHS = [
    (y, m)
    for y in range(2023, 2027)
    for m in range(1, 13)
    if (y, m) <= (2026, 7)
]
DATE_PATTERNS = [
    re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$"),
    re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})(?:[ T].*)?$"),
    re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:[ T].*)?$"),
    re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?(?:[ T].*)?$"),
    re.compile(r"^(\d{4})-(\d{1,2})$"),
]


def parse_month(value):
    """把 发货日期 解析为 YYYY-MM；失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    s = str(value).strip()
    if not s:
        return None
    for pat in DATE_PATTERNS:
        m = pat.match(s)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            return f"{y}-{mo:02d}" if 1 <= mo <= 12 else None
    try:
        return datetime.fromisoformat(s.replace("/", "-")).strftime("%Y-%m")
    except ValueError:
        return None


def col_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def open_retry(gc, name, tries=7):
    for i in range(tries):
        try:
            return gc.open(name)
        except Exception as e:  # noqa: BLE001 - network flakiness
            print(f"  retry open {name} {i + 1}: {type(e).__name__}", flush=True)
            time.sleep(2 + i * 2)
    return None


def batch_retry(ws, ranges, tries=5):
    for i in range(tries):
        try:
            return ws.batch_get(ranges)
        except Exception as e:  # noqa: BLE001
            print(f"  retry batch {ws.title} {i + 1}: {type(e).__name__}", flush=True)
            time.sleep(2 + i * 2)
    return None


def find_col(headers, name, fallbacks=()):
    for cand in (name, *fallbacks):
        for i, h in enumerate(headers):
            if str(h).strip() == cand:
                return i
    return None


def main():
    gc = gspread.service_account(filename=SA)
    rows = []
    log = []
    for y, m in MONTHS:
        name = f"通途订单{y}{m:02d}"
        sh = open_retry(gc, name)
        if sh is None:
            log.append(f"{name}: OPEN_FAILED")
            continue
        titles = [w.title for w in sh.worksheets()]
        cands = [t for t in titles if re.match(r"^\d{4}年\d{1,2}月订单$", t)]
        if not cands:
            log.append(f"{name}: NO_RAW_TAB ({titles[:5]})")
            continue
        ws = sh.worksheet(cands[0])
        hdr = ws.row_values(1)
        idx = {f: find_col(hdr, f) for f in FIELDS}
        idx["发货数量"] = find_col(hdr, "发货数量", ("数量", "发货数"))
        if any(v is None for v in idx.values()):
            log.append(f"{name}: MISSING_COLS {idx}")
            continue
        n = ws.row_count
        ranges = [
            f"{col_letter(idx[f])}2:{col_letter(idx[f])}{n}" for f in FIELDS
        ]
        res = batch_retry(ws, ranges)
        if res is None:
            log.append(f"{name}: BATCH_FAILED")
            continue
        cols = [[r[0] if r else "" for r in vr] for vr in res]
        dates, skus, qtys, chans, whs = cols
        n_hit = 0
        n_bad_date = 0
        for d, s, q, c, w in zip(dates, skus, qtys, chans, whs):
            s = str(s).strip()
            if s not in TARGET or not str(d).strip():
                continue
            try:
                qn = int(float(q))
            except (TypeError, ValueError):
                qn = 0
            month = parse_month(d)
            if month is None:
                n_bad_date += 1
            rows.append(
                (str(d).strip(), s, qn, str(c).strip(), str(w).strip(), month or "")
            )
            n_hit += 1
        log.append(
            f"{name}: {cands[0]} rows={n} hits={n_hit} bad_date={n_bad_date}"
        )
        print(f"{name}: hits={n_hit} bad_date={n_bad_date}", flush=True)

    raw_path = OUT / "wedge_raw.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "sku", "qty", "channel", "warehouse", "month"])
        w.writerows(rows)

    agg = {}
    for d, s, q, c, wh, mo in rows:
        key = (s[-4:], mo)
        a = agg.setdefault(key, [0, 0])
        a[0] += q
        if "DANEEY" in wh.upper():
            a[1] += q

    monthly_path = OUT / "wedge_monthly.csv"
    with monthly_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "month", "qty_all", "qty_daneey"])
        for (sku, mo), (qa, qd) in sorted(agg.items()):
            w.writerow([sku, mo, qa, qd])

    (OUT / "pull_log.txt").write_text("\n".join(log), encoding="utf-8")
    print(f"\nraw rows={len(rows)} -> {raw_path}", flush=True)
    print(f"monthly rows={len(agg)} -> {monthly_path}", flush=True)


if __name__ == "__main__":
    main()
