#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为「通途订单YYYYMM」创建「数据透视表-报税成本YYYYMM」。

口径与 202607 既有透视表一致：
  行：渠道账号 → 发货仓按销售汇总分类 → 通途SKU
  值：发货数量 / 皮壳成本*系数*数量 / 绍兴二次加工成本*系数*数量 /
      二次加工成本*系数*数量 / 头程运费*数量 / 运费（全部 SUM）

用法：
  GSPREAD_SERVICE_ACCOUNT_FILE=<父仓库>/secrets/gsheets-service-account.json \
  uv run python tongtool_order_cost/scripts/create_monthly_tax_pivot.py \
      --month 202608 --month 202609                 # dry-run，只看计划
      --month 202608 --month 202609 --apply         # 实际创建
      --month 202608 --verify-only                  # 只对账已有透视表
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from tongtool_order_cost.gsheets import load_credentials  # noqa: E402
from tongtool_order_cost.gsheets_pivot import (
    ROW_FIELDS,
    VALUE_FIELDS,
    build_create_requests,
    build_pivot_spec,
    column_letter,
    estimated_grid_rows,
    expected_output_header,
    required_names,
    resolve_offsets,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
KEY_NAMES = [f["name"] for f in ROW_FIELDS]
TOLERANCE = 0.01
POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 120


def sheets_service():
    creds = Credentials.from_service_account_info(load_credentials(), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def gspread_client():
    import gspread

    return gspread.service_account_from_dict(load_credentials())


def derive_titles(month: str) -> tuple[str, str, str]:
    """'202608' → (spreadsheet, source_ws, target_ws)"""
    y, m = int(month[:4]), int(month[4:6])
    if not (1 <= m <= 12):
        raise SystemExit(f"月份非法: {month}")
    return (
        f"通途订单{month}",
        f"写回{y}年{m}月FBA订单和非FBA订单",
        f"数据透视表-报税成本{month}",
    )


def open_spreadsheet(gc, title: str, attempts: int = 5):
    for i in range(attempts):
        try:
            return gc.open(title)
        except Exception as e:  # 503 等瞬时错误
            if i == attempts - 1:
                raise
            print(f"  [重试 {i + 1}] open({title}) {type(e).__name__}: {str(e)[:60]}")
            time.sleep(5)


def sheet_properties(svc, spreadsheet_id: str) -> list[dict]:
    meta = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute()
    return [s["properties"] for s in meta.get("sheets", [])]


def find_sheet(props: list[dict], title: str) -> dict | None:
    for p in props:
        if p.get("title") == title:
            return p
    return None


def read_header(svc, spreadsheet_id: str, source_ws: str, end_col: int) -> list[str]:
    vr = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{source_ws}'!A1:{column_letter(end_col)}1",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = vr.get("values", [])
    return [str(v).strip() for v in rows[0]] if rows else []


def read_source_frame(
    svc, spreadsheet_id: str, source_ws: str, row_count: int, offsets: dict[str, int]
) -> pd.DataFrame:
    names = required_names()
    col_letters = [column_letter(offsets[n] + 1) for n in names]
    ranges = [f"'{source_ws}'!{c}2:{c}{row_count}" for c in col_letters]
    res = svc.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=ranges,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()

    n = max(row_count - 1, 0)
    columns: dict[str, list] = {}
    for name, vr in zip(names, res.get("valueRanges", [])):
        vals = [row[0] if row else None for row in vr.get("values", [])]
        vals += [None] * (n - len(vals))
        columns[name] = vals[:n]

    df = pd.DataFrame(columns)
    for name in KEY_NAMES:
        df[name] = df[name].map(lambda v: "" if v is None else str(v).strip())
    for name in VALUE_FIELDS:
        df[name] = pd.to_numeric(df[name], errors="coerce").fillna(0.0)
    return df


def group_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    grouped = (
        df.groupby(KEY_NAMES, dropna=False, sort=False)[list(VALUE_FIELDS)]
        .sum()
        .reset_index()
    )
    counts = {
        "rows": len(df),
        "groups": len(grouped),
        "accounts": df[KEY_NAMES[0]].nunique(dropna=False),
        "account_warehouses": df.groupby(KEY_NAMES[:2], dropna=False).ngroups,
    }
    return grouped, counts


def fetch_pivot_spec(svc, spreadsheet_id: str, ws_title: str) -> dict | None:
    for attempt in range(3):
        try:
            res = svc.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                ranges=[f"'{ws_title}'!A1"],
                includeGridData=True,
                fields="sheets(properties(title),data(rowData(values(pivotTable))))",
            ).execute()
            break
        except HttpError:
            if attempt == 2:
                raise
            time.sleep(2)
    for sh in res.get("sheets", []):
        for d in sh.get("data", []):
            for row in d.get("rowData", []):
                for cell in row.get("values", []):
                    if "pivotTable" in cell:
                        return cell["pivotTable"]
    return None


def fetch_values(
    svc, spreadsheet_id: str, ws_title: str, last_col: str, last_row: int
) -> list[list]:
    vr = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{ws_title}'!A1:{last_col}{last_row}",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    return vr.get("values", [])


def wait_for_pivot(svc, spreadsheet_id: str, ws_title: str, last_row: int):
    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        try:
            spec = fetch_pivot_spec(svc, spreadsheet_id, ws_title)
            rows = fetch_values(svc, spreadsheet_id, ws_title, "I", min(last_row, 10))
            if spec and len(rows) >= 2:
                return spec
        except HttpError:
            pass
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError(f"透视表 {ws_title} 在 {POLL_TIMEOUT_S}s 内未就绪")


def norm_key(v) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s in ("(空白)", "（空白）") else s


def safe_float(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def compare_pivot_spec(actual: dict, expected: dict) -> list[str]:
    problems = []
    for key in ("source", "rows", "values"):
        if actual.get(key) != expected.get(key):
            problems.append(f"pivot.{key} 不一致（实际 {actual.get(key)} / 期望 {expected.get(key)}）")
    extra = [k for k in actual if k not in ("source", "rows", "values")]
    if extra:
        print(f"  注：API 额外返回 pivot 字段 {extra}（不影响口径）")
    return problems


def verify(
    svc,
    spreadsheet_id: str,
    target_ws: str,
    expected_spec: dict,
    grouped: pd.DataFrame,
    counts: dict,
    grid_rows: int,
) -> bool:
    spec = wait_for_pivot(svc, spreadsheet_id, target_ws, grid_rows)
    rows = fetch_values(svc, spreadsheet_id, target_ws, "I", grid_rows)

    problems = compare_pivot_spec(spec, expected_spec)

    header = [norm_key(v) for v in (list(rows[0]) + [""] * 9)[:9]] if rows else []
    if header != expected_output_header():
        problems.append(f"输出表头不一致: {header}")

    leaf: dict[tuple, list[float]] = {}
    duplicates: list[tuple] = []
    total_row: list[float] | None = None
    for raw in rows[1:]:
        r = list(raw) + [""] * (9 - len(raw))
        cells = [norm_key(v) for v in r[:3]]
        if cells[0] == "总计" and not cells[1] and not cells[2]:
            total_row = [safe_float(v) for v in r[3:9]]
            continue
        if any(v == "" for v in cells) or any("总计" in v for v in cells):
            continue  # 小计行
        key = tuple(cells)
        if key in leaf:
            duplicates.append(key)
        leaf[key] = [safe_float(v) for v in r[3:9]]

    source = {
        tuple(str(row[n]) for n in KEY_NAMES): [float(row[v]) for v in VALUE_FIELDS]
        for _, row in grouped.iterrows()
    }
    missing = sorted(set(source) - set(leaf))
    extra = sorted(set(leaf) - set(source))
    diffs = [
        (k, leaf[k], source[k])
        for k in source
        if k in leaf and any(abs(a - b) > TOLERANCE for a, b in zip(leaf[k], source[k]))
    ]

    if duplicates:
        problems.append(f"透视明细存在重复键 {len(duplicates)} 个，例: {duplicates[:3]}")
    if missing:
        problems.append(f"透视缺少 {len(missing)} 组，例: {missing[:3]}")
    if extra:
        problems.append(f"透视多出 {len(extra)} 组，例: {extra[:3]}")
    if diffs:
        problems.append(f"数值不一致 {len(diffs)} 组，例: {diffs[:3]}")

    leaf_totals = [sum(v[i] for v in leaf.values()) for i in range(len(VALUE_FIELDS))]
    source_totals = [float(grouped[v].sum()) for v in VALUE_FIELDS]
    if any(abs(a - b) > TOLERANCE for a, b in zip(leaf_totals, source_totals)):
        problems.append(f"明细合计≠源表合计: {leaf_totals} / {source_totals}")
    if total_row is None:
        problems.append("未找到「总计」行")
    elif any(abs(a - b) > TOLERANCE for a, b in zip(total_row, source_totals)):
        problems.append(f"总计行≠源表合计: {total_row} / {source_totals}")

    print(
        f"  源 {counts['rows']} 行 → {counts['groups']} 组 → "
        f"透视明细 {len(leaf)} 行；缺 {len(missing)} / 多 {len(extra)} / 差异 {len(diffs)}"
    )
    if problems:
        print("  [FAIL]")
        for p in problems:
            print("   - " + p)
        return False
    print("  [OK] 透视规格、组数、6 个汇总值与总计行全部一致")
    return True


def process_month(svc, gc, month: str, apply: bool, verify_only: bool) -> bool:
    book_title, source_ws, target_ws = derive_titles(month)
    print(f"\n=== {book_title} ===")
    sh = open_spreadsheet(gc, book_title)
    props = sheet_properties(svc, sh.id)
    source = find_sheet(props, source_ws)
    if source is None:
        similar = [p["title"] for p in props if "写回" in p.get("title", "")]
        raise SystemExit(f"找不到源工作表「{source_ws}」；现有写回表: {similar}")

    row_count = int(source["gridProperties"]["rowCount"])
    end_col = int(source["gridProperties"]["columnCount"])
    source_id = int(source["sheetId"])
    source_index = int(source.get("index", 0))

    header = read_header(svc, sh.id, source_ws, end_col)
    offsets = resolve_offsets(header)
    print(
        f"源 ws: {source_ws} (sheetId={source_id}, index={source_index}, "
        f"{row_count} 行 × {end_col} 列)"
    )
    print("列偏移: " + ", ".join(f"{n}={i}" for n, i in offsets.items()))

    df = read_source_frame(svc, sh.id, source_ws, row_count, offsets)
    grouped, counts = group_frame(df)
    grid_rows = estimated_grid_rows(
        counts["groups"], counts["accounts"], counts["account_warehouses"]
    )
    print(
        f"分组: {counts['groups']} 组（账号 {counts['accounts']}，"
        f"账号×仓 {counts['account_warehouses']}），目标网格行数 {grid_rows}"
    )

    expected_spec = build_pivot_spec(header, source_id, row_count, end_col)
    target = find_sheet(props, target_ws)

    if verify_only:
        if target is None:
            print(f"[FAIL] 目标透视表「{target_ws}」不存在")
            return False
        return verify(svc, sh.id, target_ws, expected_spec, grouped, counts, grid_rows)

    if target is not None:
        print(f"目标「{target_ws}」已存在，不重建，改为对账")
        return verify(svc, sh.id, target_ws, expected_spec, grouped, counts, grid_rows)

    if not apply:
        print(f"[dry-run] 将新建「{target_ws}」并写入透视表；加 --apply 执行")
        return True

    new_sheet_id = max(int(p["sheetId"]) for p in props) + 1
    if new_sheet_id >= 2**31:
        raise SystemExit("sheetId 超出 int32，需人工处理")
    requests = build_create_requests(
        sheet_id=new_sheet_id,
        title=target_ws,
        index=source_index + 1,
        row_count=grid_rows,
        spec=expected_spec,
    )
    print(f"创建「{target_ws}」于源表右侧（index={source_index + 1}, sheetId={new_sheet_id}）")
    try:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=sh.id, body={"requests": requests}
        ).execute()
    except HttpError:
        # 写请求超时后可能已落地：以服务端实际状态为准，不重复创建。
        if find_sheet(sheet_properties(svc, sh.id), target_ws) is None:
            raise
        print("  batchUpdate 报错但目标已存在，继续对账")

    return verify(svc, sh.id, target_ws, expected_spec, grouped, counts, grid_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", action="append", required=True, help="YYYYMM，可重复")
    parser.add_argument("--apply", action="store_true", help="实际创建（默认 dry-run）")
    parser.add_argument("--verify-only", action="store_true", help="只对账，不创建")
    args = parser.parse_args()

    months = list(dict.fromkeys(args.month))
    for m in months:
        if len(m) != 6 or not m.isdigit():
            raise SystemExit(f"月份格式应为 YYYYMM: {m}")

    svc = sheets_service()
    gc = gspread_client()
    ok = True
    for month in months:
        try:
            ok = process_month(svc, gc, month, args.apply, args.verify_only) and ok
        except Exception as e:  # 每月独立报错，继续下一个月
            print(f"[ERROR] {month}: {type(e).__name__}: {e}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
