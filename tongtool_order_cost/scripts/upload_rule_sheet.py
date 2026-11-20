# -*- coding: utf-8 -*-
"""Dry-run / apply upload of a special-rule xlsx to the finance Google Sheet tab."""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.engine_170 import COEFF_COLS, REF_COLS
from tongtool_order_cost.gsheets import client

EXPECTED_COLS = [
    "运营人员",
    "发货仓按销售汇总分类",
    "发货区域",
    "渠道账号不含国家",
    "渠道账号",
    "通途SKU",
    "产品名称",
    "销售额系数",
    "皮壳成本系数",
    "绍兴二次加工成本系数",
    "二次加工成本系数",
    "头程运费系数",
    "海外仓成本系数",
    "尾程运费系数",
    "执行开始时间",
    "执行结束时间",
    "备注",
    "收款币种",
    "发货数量1皮壳成本*系数参考值",
    "发货数量1绍兴二次加工成本*系数参考值",
    "发货数量1二次加工成本*系数参考值",
    "发货数量1头程运费参考值",
    "发货数量1海外仓成本参考值",
    "发货数量1订单尾程运费",
]


def retry(fn, *args, attempts: int = 6, **kwargs):
    """googleapis 偶发 SSL UNEXPECTED_EOF；对幂等调用重试。"""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"[retry {i + 1}/{attempts}] {type(exc).__name__}: {str(exc)[:120]}")
            time.sleep(3)
    raise last


def cell_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value).strip()


def load_rule_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    df = pd.read_excel(path, dtype=object)
    header = [str(c).strip() for c in df.columns]
    if header != EXPECTED_COLS:
        missing = [c for c in EXPECTED_COLS if c not in header]
        extra = [c for c in header if c not in EXPECTED_COLS]
        raise SystemExit(
            f"规则表列名不符：缺少={missing} 多余={extra}\n"
            f"实际列名={header}"
        )
    rows = [[cell_text(v) for v in row] for row in df.itertuples(index=False, name=None)]
    return header, rows


def build_report(header: list[str], rows: list[list[str]]) -> dict:
    df = pd.DataFrame(rows, columns=header)
    has_coef = df[COEFF_COLS].apply(lambda r: any(v != "" for v in r), axis=1)
    has_ref = df[REF_COLS].apply(lambda r: any(v != "" for v in r), axis=1)
    start = pd.to_datetime(df["执行开始时间"].replace("", pd.NA), errors="coerce")
    end = pd.to_datetime(df["执行结束时间"].replace("", pd.NA), errors="coerce")
    mixed_idx = df.index[has_coef & has_ref].tolist()
    mixed = []
    for i in mixed_idx:
        mixed.append(
            {
                "excel_row": i + 2,
                "发货仓按销售汇总分类": df.at[i, "发货仓按销售汇总分类"],
                "通途SKU": df.at[i, "通途SKU"],
                "旧/新期间": f"{df.at[i, '执行开始时间']}~{df.at[i, '执行结束时间']}",
            }
        )
    return {
        "rows": len(df),
        "cols": len(header),
        "coef_only": int((has_coef & ~has_ref).sum()),
        "ref_only": int((~has_coef & has_ref).sum()),
        "mixed": int((has_coef & has_ref).sum()),
        "neither": int((~has_coef & ~has_ref).sum()),
        "empty_sku": int((df["通途SKU"] == "").sum()),
        "missing_start": int(start.isna().sum()),
        "end_before_start": int(((end < start) & start.notna() & end.notna()).sum()),
        "duplicate_rows": sum(c - 1 for c in Counter(map(tuple, rows)).values() if c > 1),
        "mixed_rows": mixed,
    }


def print_report(report: dict) -> None:
    print(f"规则表: {report['rows']} 行 x {report['cols']} 列")
    print(
        "口径: "
        f"系数={report['coef_only']} 参考值={report['ref_only']} "
        f"混合={report['mixed']} 空={report['neither']}"
    )
    print(
        f"空SKU={report['empty_sku']} 缺开始时间={report['missing_start']} "
        f"结束早于开始={report['end_before_start']} 完全重复行={report['duplicate_rows']}"
    )
    if report["mixed_rows"]:
        print("\n混合模式行（引擎会整行跳过）:")
        for r in report["mixed_rows"]:
            print(
                f"  行{r['excel_row']:>4} | {r['发货仓按销售汇总分类']} | "
                f"{r['通途SKU']} | {r['旧/新期间']}"
            )


def read_back(ws) -> tuple[list[str], list[list[str]]]:
    values = ws.get_all_values()
    if not values:
        return [], []
    body = [r for r in values[1:] if any(str(x).strip() for x in r)]
    return [str(c).strip() for c in values[0]], body


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="上传特殊规则 xlsx → Google Sheet（默认 dry-run）")
    p.add_argument("--xlsx", required=True, help="规则表 xlsx")
    p.add_argument("--sheet", default="和财务部共享", help="Google 表格标题")
    p.add_argument("--ws", default="黄-特殊规则-订单改销售额成本", help="worksheet 名")
    p.add_argument("--apply", action="store_true", help="实际写入（默认只预检）")
    p.add_argument("--overwrite", action="store_true", help="覆盖已有内容")
    p.add_argument("--allow-mixed", action="store_true", help="允许混合模式行存在")
    args = p.parse_args(argv)

    path = Path(args.xlsx)
    if not path.exists():
        raise SystemExit(f"xlsx 不存在: {path}")
    header, rows = load_rule_rows(path)
    report = build_report(header, rows)
    print_report(report)

    if not args.apply:
        print("\nDRY-RUN：未写入。确认后加 --apply。")
        return 0
    if report["mixed"] and not args.allow_mixed:
        raise SystemExit(
            f"存在 {report['mixed']} 行混合模式；确认后可加 --allow-mixed 再写入。"
        )
    if report["empty_sku"] or report["end_before_start"]:
        raise SystemExit("存在空 SKU 或结束时间早于开始时间，拒绝写入。")

    gc = retry(client)
    sh = retry(gc.open, args.sheet)
    ws = retry(sh.worksheet, args.ws)
    existing = [
        r for r in retry(ws.get_all_values)[1:] if any(str(x).strip() for x in r)
    ]
    if existing and not args.overwrite:
        raise SystemExit(
            f"目标 ws 已有 {len(existing)} 行数据；如确认覆盖请加 --overwrite。"
        )

    values = [header] + rows
    retry(ws.resize, rows=len(values), cols=len(header))
    if args.overwrite:
        retry(ws.clear)
    retry(ws.update, values, "A1", value_input_option="RAW")

    got_header, got_rows = retry(read_back, ws)
    if got_header != header:
        raise SystemExit(f"回读表头不一致: {got_header}")
    src, got = Counter(map(tuple, rows)), Counter(map(tuple, got_rows))
    same = sum((src & got).values())
    print(
        f"\n写入完成：回读 {len(got_rows)} 行；逐行一致 {same} 行；"
        f"仅源表有 {sum((src - got).values())} 行；仅线上有 {sum((got - src).values())} 行。"
    )
    if same != len(rows) or got != src:
        raise SystemExit("回读与源表不一致，请检查。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
