#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1 数据拉取：从 43 张通途月表抽取 PB 楔形枕 8 个 SKU 的逐日发货行。

只读 Google Sheets；输出到 experiments/e1_forecast/data/。
不写任何业务系统。

月份归属统一用「发货日期」解析（支持 YYYY-MM-DD / YYYY/M/D / datetime），
不用月表名，也不用 date[:7]。解析失败的行保留在 raw 并把 month 置空，
绝不当作 0 需求。

R02 修正：
- 非法发货数量（空 / 非数字 / 负数 / 非有限值 / 非整数件数）不再转成 0：
  保留该行，qty 留空，qty_status=bad，qty_reason 记录原因；按月计数写入 pull_log。
- batch_get 各列长度可能不一致：先取最大长度，短列补 ""，不静默 zip 截断；
  每张月表记录 column_length_mismatch 与各列长度。
- 每张月表记录 source_rows（sheet row_count，含表头）与 extracted_rows
  （对齐后的数据行数），便于人工核对；这只证明本月表被完整读取，
  不能证明跨月发货行没有缺失（见 README 完整性说明）。
"""

import csv
import math
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

QTY_BAD_REASONS = ("empty", "non_numeric", "negative", "non_finite", "non_integer_pieces")


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


def parse_qty(value):
    """解析发货数量；返回 (qty:int|None, reason:str)。

    reason 为空字符串表示合法。非法值一律返回 (None, reason)，
    调用方保留行、qty 留空，绝不转成 0。
    """
    if value is None:
        return None, "empty"
    if isinstance(value, bool):
        return None, "non_numeric"
    if isinstance(value, (int, float)):
        f = float(value)
    else:
        s = str(value).strip()
        if not s:
            return None, "empty"
        try:
            f = float(s)
        except ValueError:
            return None, "non_numeric"
    if not math.isfinite(f):
        return None, "non_finite"
    if f < 0:
        return None, "negative"
    if f != int(f):
        return None, "non_integer_pieces"
    return int(f), ""


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


def align_columns(cols):
    """把长度不一致的列补 "" 对齐到同一长度；返回 (aligned, lengths, mismatch)。"""
    lengths = [len(c) for c in cols]
    max_len = max(lengths) if lengths else 0
    aligned = [c + [""] * (max_len - len(c)) for c in cols]
    return aligned, lengths, len(set(lengths)) > 1


def main():
    gc = gspread.service_account(filename=SA)
    rows = []
    log = []
    total_bad = 0
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
        source_rows = ws.row_count  # 含表头
        ranges = [
            f"{col_letter(idx[f])}2:{col_letter(idx[f])}{source_rows}" for f in FIELDS
        ]
        res = batch_retry(ws, ranges)
        if res is None:
            log.append(f"{name}: BATCH_FAILED")
            continue
        cols = [[r[0] if r else "" for r in vr] for vr in res]
        cols, lengths, mismatch = align_columns(cols)
        extracted_rows = len(cols[0]) if cols else 0
        dates, skus, qtys, chans, whs = cols
        n_hit = 0
        n_bad_date = 0
        n_empty_date = 0
        bad_reason_counts = {r: 0 for r in QTY_BAD_REASONS}
        for d, s, q, c, w in zip(dates, skus, qtys, chans, whs):
            s = str(s).strip()
            if s not in TARGET:
                continue
            if not str(d).strip():
                n_empty_date += 1
                continue
            qn, reason = parse_qty(q)
            if qn is None:
                bad_reason_counts[reason] += 1
                total_bad += 1
            month = parse_month(d)
            if month is None:
                n_bad_date += 1
            rows.append((
                str(d).strip(),
                s,
                "" if qn is None else qn,
                "ok" if qn is not None else "bad",
                reason,
                str(c).strip(),
                str(w).strip(),
                month or "",
            ))
            n_hit += 1
        n_bad = sum(bad_reason_counts.values())
        reasons_txt = ",".join(
            f"{k}:{v}" for k, v in bad_reason_counts.items() if v) or "-"
        log.append(
            f"{name}: {cands[0]} source_rows={source_rows} "
            f"extracted_rows={extracted_rows} blank_tail={source_rows - 1 - extracted_rows} "
            f"hits={n_hit} empty_date={n_empty_date} bad_qty={n_bad} "
            f"bad_reasons={reasons_txt} bad_date={n_bad_date} "
            f"col_mismatch={'yes' if mismatch else 'no'} "
            f"lengths={','.join(map(str, lengths))}"
        )
        print(
            f"{name}: hits={n_hit} bad_qty={n_bad} empty_date={n_empty_date} "
            f"bad_date={n_bad_date} col_mismatch={mismatch}",
            flush=True,
        )

    raw_path = OUT / "wedge_raw.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["date", "sku", "qty", "qty_status", "qty_reason",
             "channel", "warehouse", "month"]
        )
        w.writerows(rows)

    agg = {}
    bad_agg = {}
    for d, s, q, status, reason, c, wh, mo in rows:
        if not mo:
            continue  # 日期解析失败，无法归月；不做任何补值
        key = (s[-4:], mo)
        a = agg.setdefault(key, [0, 0])
        if status != "bad":
            a[0] += q
            if "DANEEY" in wh.upper():
                a[1] += q
        else:
            bad_agg[key] = bad_agg.get(key, 0) + 1

    monthly_path = OUT / "wedge_monthly.csv"
    with monthly_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "month", "qty_all", "qty_daneey", "bad_rows"])
        for key in sorted(set(agg) | set(bad_agg)):
            qa, qd = agg.get(key, [0, 0])
            w.writerow([key[0], key[1], qa, qd, bad_agg.get(key, 0)])

    (OUT / "pull_log.txt").write_text("\n".join(log), encoding="utf-8")
    print(f"\nraw rows={len(rows)} bad_qty_rows={total_bad} -> {raw_path}", flush=True)
    print(f"monthly rows={len(agg)} -> {monthly_path}", flush=True)


if __name__ == "__main__":
    main()
