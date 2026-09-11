# -*- coding: utf-8 -*-
"""从财务共享表的「钉钉账期提交时间不对挪动记录」生成跨月剔除键文件。

钉钉只能按**发起时间**导出，迟交单会混进下个月的导出。算某个账期月之前，用本脚本
把那批单的唯一键导出来，喂给：

    filter_export_by_period.py --period 2026-08 --exclude-keys <本脚本产物>

键由 `ding_xlsx.build_key()` 生成 —— 和导出侧**同一个函数**，避免金额写法（`0` vs `0.0`）
或日期写法差一点就静默漏剔除。表里自带的「唯一键」列只作人工核对，不直接采用。

只读 Google 表，不写回。凭证走 `secrets/gsheets-service-account.json`。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from ding_xlsx import build_key, pick_amount

REGISTRY_SHEET_ID = "1UhFiMF9tLmndoOaz7PaEP_Fz1ZGYK9GVT6hiIYLM8Go"
REGISTRY_WORKSHEET = "钉钉账期提交时间不对挪动记录"
EXCLUDE_COL = "后续账期须剔除"


def keys_for_period(header: list[str], rows: list[list[str]], period: str) -> tuple[list[str], list[str]]:
    """返回 (剔除键, 跳过的行说明)。

    header/rows 是 worksheet.get_all_values() 的形态（首行表头，其余按位置对齐）。
    period 为 `YYYY-MM`；只取 `后续账期须剔除` 里含该月的行。
    """
    cols = {name: i for i, name in enumerate(header)}
    for need in ("审批编号", EXCLUDE_COL):
        if need not in cols:
            raise SystemExit(f"登记表缺列「{need}」；实际表头：{header}")

    keys: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for n, row in enumerate(rows, start=2):  # 2 = 表头下一行，便于对照表格行号
        cells = {name: (row[i] if i < len(row) else "") for name, i in cols.items()}
        must = str(cells.get(EXCLUDE_COL) or "")
        months = [m.strip() for m in must.replace(";", ",").split(",") if m.strip()]
        if period not in months:
            continue
        key = build_key(
            cells.get("审批编号"),
            _first_present(cells, ("账期日期",)),
            _first_present(cells, ("销售账户", "销售账户_展开")),
            pick_amount(cells),
        )
        if not key or key.count("|") != 3 or not key.split("|")[0]:
            skipped.append(f"第{n}行：键不完整 {key!r}（审批编号={cells.get('审批编号')!r}）")
            continue
        if key in seen:
            skipped.append(f"第{n}行：与前面重复 {key!r}")
            continue
        seen.add(key)
        keys.append(key)
    return sorted(keys), skipped


def _first_present(cells: dict, names: tuple[str, ...]):
    for name in names:
        v = cells.get(name)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in {"nan", "none"}:
            return v
    return ""


def fetch_registry(sheet_id: str, worksheet: str) -> tuple[list[str], list[list[str]]]:
    """读 Google 表。gspread 只在真正联网时才 import，方便单测跑纯函数。"""
    repo_root = _HERE.parents[1]
    sys.path.insert(0, str(repo_root / "tongtool_order_cost"))
    from tongtool_order_cost.gsheets import client

    sh = client().open_by_key(sheet_id)
    ws = sh.worksheet(worksheet)
    vals = ws.get_all_values()
    if not vals:
        raise SystemExit(f"worksheet「{worksheet}」是空的")
    return vals[0], vals[1:]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="导出某账期月的跨月剔除键")
    ap.add_argument("--period", required=True, help="账期月 YYYY-MM，例如 2026-08")
    ap.add_argument("--out", required=True, help="写出的键文件（每行一个唯一键）")
    ap.add_argument("--sheet-id", default=REGISTRY_SHEET_ID)
    ap.add_argument("--worksheet", default=REGISTRY_WORKSHEET)
    ap.add_argument("--print", dest="show", action="store_true", help="同时打印键")
    args = ap.parse_args()

    header, rows = fetch_registry(args.sheet_id, args.worksheet)
    keys, skipped = keys_for_period(header, rows, args.period)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# 由 late_submission_keys.py 生成；继续沿用请勿手改\n"
        + "".join(f"{k}\n" for k in keys),
        encoding="utf-8",
    )
    print(f"period={args.period} rows={len(rows)} exclude_keys={len(keys)} wrote={out}")
    for line in skipped:
        print(f"  skip {line}")
    if args.show:
        for k in keys:
            print(f"  {k}")


if __name__ == "__main__":
    main()
