#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读钉钉表格 → 控制台 / Excel / CSV。

```
# 列出一个文档的所有 sheet
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/QOG9lyrgJPjjrl10uXDDw7RwWzN67Mw4" \
    --operator-env DINGTALK_OPERATOR_ORDER --list

# 读某张表
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url ".../nodes/QOG9..." --sheet "2026年度订单明细" \
    --range A1:P500 --operator-env DINGTALK_OPERATOR_ORDER --out EN_API/out/订单明细.xlsx

# 精确匹配某一列的值（找 SO / 批次号 等）
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url ".../nodes/QOG9..." --sheet "2026年度订单明细" \
    --range A1:P2000 --operator-env DINGTALK_OPERATOR_ORDER \
    --find-col B --find SO-26-00101
```

`--operator-env` 指定用哪个 unionId 变量（文档接口必填，且必须对本文档有权限）。
unionId 只放本机 .env，不要写进仓库。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import client as dc  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def col_index(letter: str) -> int:
    """A→0, B→1, ... Z→25, AA→26"""
    n = 0
    for ch in (letter or "").strip().upper():
        if not ch.isalpha():
            continue
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return max(n - 1, 0)


def trim(row: list) -> list:
    out = [("" if c is None else str(c)) for c in row]
    while out and out[-1] == "":
        out.pop()
    return out


def write_xlsx(path: Path, sheets: list[tuple[str, list[list[str]]]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        safe = title[:31] or "Sheet"
        ws = wb.create_sheet(title=safe)
        for r in rows:
            ws.append(trim(r))
        if ws.max_row >= 1:
            for c in range(1, ws.max_column + 1):
                ws.cell(row=1, column=c).font = Font(bold=True)
                ws.cell(row=1, column=c).fill = PatternFill("solid", fgColor="DDEBF7")
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="读钉钉表格（只读）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="alidocs 链接或裸 baseId")
    ap.add_argument("--sheet", help="sheet 名（--list 时不需要）")
    ap.add_argument("--range", default="A1:Z1000", help="A1 区域（默认 A1:Z1000）")
    ap.add_argument("--all", action="store_true",
                    help="整表读取（自动分块翻页、剔除接口补齐的空行）；与 --range 互斥")
    ap.add_argument("--cols", type=int, default=20, help="--all 时的列数（默认 20，即 A..T）")
    ap.add_argument("--list", action="store_true", help="只列出所有 sheet")
    ap.add_argument("--operator-env", default="DINGTALK_OPERATOR_ID",
                    help="存放该文档 unionId 的环境变量名（默认 DINGTALK_OPERATOR_ID）")
    ap.add_argument("--find-col", help="在指定列（如 B）里精确匹配 --find")
    ap.add_argument("--find", help="要匹配的值")
    ap.add_argument("-o", "--out", help="导出 xlsx 路径")
    ap.add_argument("--env-file", help="指定 .env")
    ap.add_argument("--max-rows", type=int, default=40, help="控制台最多打印行数")
    args = ap.parse_args()

    env = dc.load_env(Path(args.env_file) if args.env_file else None)
    token = dc.get_access_token(env)
    base = dc.parse_base_id(args.url)

    sheets = dc.list_sheets(base, _op(env, args.operator_env), token)
    if args.list:
        print(f"文档 {base} 共 {len(sheets)} 张 sheet：")
        for s in sheets:
            print(f"  {s.get('id'):<28} {s.get('name')}")
        return 0
    if not args.sheet:
        print("需要 --sheet（或 --list）", file=sys.stderr)
        return 2

    sid = dc.sheet_id_by_name(sheets, args.sheet)
    if args.all:
        rows = dc.read_sheet_all(base, sid, _op(env, args.operator_env), token,
                                 n_cols=args.cols)
        print(f"sheet {args.sheet} ({sid}) 整表 → 真实数据 {len(rows)} 行")
    else:
        rows = dc.read_range(base, sid, _op(env, args.operator_env), token, args.range)
        print(f"sheet {args.sheet} ({sid}) 区域 {args.range} → {len(rows)} 行"
              f"（注意：接口会用空行把请求区域补满，此处含尾部空行）")
    rows = [trim(r) for r in rows]

    hits = []
    if args.find:
        ci = col_index(args.find_col or "A")
        for i, r in enumerate(rows, 1):
            if ci < len(r) and r[ci].strip() == args.find.strip():
                hits.append(i)
        print(f"列 {args.find_col or 'A'} 匹配 {args.find!r}: {len(hits)} 行 → {hits[:30]}")

    if args.out:
        write_xlsx(Path(args.out), [(args.sheet, rows)])
        print(f"OK: {args.out}")

    show = rows[:args.max_rows]
    for i, r in enumerate(show, 1):
        print(f"  R{i}: " + " | ".join(c.replace("\n", "⏎")[:22] for c in r[:16]))
    if len(rows) > len(show):
        print(f"  … 其余 {len(rows) - len(show)} 行未打印")
    return 0


def _op(env: dict, name: str) -> str:
    v = (env.get(name) or "").strip()
    if not v:
        raise SystemExit(
            f"缺少 {name}（该文档可读的同事 unionId）。\n"
            f"  .env 里加一行 {name}=<unionId>；两个文档可能要两个人的 unionId。")
    return v


if __name__ == "__main__":
    raise SystemExit(main())
