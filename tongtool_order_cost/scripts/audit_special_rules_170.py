#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1.7.0 特殊规则核验：算术断言 + 未命中规则/订单 + 审计簿。

只读本地快照，不联网、不写 GSheet/EN。

用法：
  uv run python tongtool_order_cost/scripts/audit_special_rules_170.py \
    --snapshot "tongtool_order_cost/out/profitability_audit/2026年7月订单-特殊规则" \
    --rules     "tongtool_order_cost/out/profitability_audit/2026年7月订单/rules_170/Jeck特殊规则-订单改销售额成本.csv" \
    --month 202607 \
    --out "tongtool_order_cost/out/profitability_audit/2026年7月订单-特殊规则/special_rules_202607_audit.xlsx"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import pandas as pd  # noqa: E402

from tongtool_order_cost.audit import write_audit_workbook  # noqa: E402
from tongtool_order_cost.engine_170 import apply_special_rules  # noqa: E402
from tongtool_order_cost.io_loaders import load_fx_table  # noqa: E402
from tongtool_order_cost import profitability_audit as P  # noqa: E402

TOL = 0.005  # 分位容差（输出保留 2 位小数）


def load_orders(snapshot: Path) -> pd.DataFrame:
    """优先用 `check`（含 运营人员 等规则键，且 = 非FBA+FBA 合并）；退化到 `writeback`。"""
    base = snapshot
    for key in ("check", "writeback"):
        files = list((base / key).glob("*.csv"))
        if files:
            df = pd.read_csv(files[0], encoding="utf-8-sig", low_memory=False)
            if "渠道账号" in df.columns and "渠道账号不含国家" not in df.columns:
                df["渠道账号不含国家"] = df["渠道账号"].astype(str).str.strip().str[:-2]
            return df
    raise SystemExit(f"快照里找不到 check/writeback: {base}")


def assert_events(events: pd.DataFrame) -> pd.DataFrame:
    """逐事件验算：coeff → after=before×coeff；ref → after=ref×fx（单件）/×数量（合计）。

    返回带 `expected/ok/why` 的明细（不通过的行会被挑出）。
    """
    rows = []
    for ev in events.itertuples(index=False):
        mode = str(getattr(ev, "mode", ""))
        before = float(getattr(ev, "before") or 0)
        after = float(getattr(ev, "after") or 0)
        qty = float(getattr(ev, "发货数量") or 0)
        fx = float(getattr(ev, "fx") or 0)
        ref_usd = getattr(ev, "ref_usd", None)
        coeff = getattr(ev, "coeff_val", None)
        col = str(getattr(ev, "column", ""))
        ref_col = str(getattr(ev, "ref_col", "") or "")
        why, expected = "", None
        if mode == "coeff":
            if coeff is None or pd.isna(coeff):
                why = "coeff 缺失"
            else:
                expected = before * float(coeff)
        elif mode == "ref":
            if ref_col == "发货数量1订单尾程运费":
                # FBA 正/0 跳过不入事件；自发货整行覆盖；负数按账期差异写差值
                expected = None
                why = "尾程参考（按设计，可能为差值，非纯乘）"
            elif ref_usd is None or pd.isna(ref_usd):
                why = "ref_usd 缺失"
            else:
                unit = float(ref_usd) * fx
                expected = unit if col in _UNIT_COLS else unit * qty
        else:
            why = f"未知 mode={mode}"
        ok = "" if expected is None else ("1" if abs(after - expected) <= TOL else "0")
        rows.append({"column": col, "mode": mode, "before": before, "after": after,
                     "expected": expected, "qty": qty, "fx": fx, "coeff": coeff,
                     "ref_usd": ref_usd, "ok": ok, "why": why})
    return pd.DataFrame(rows)


# 参考值模式下「单件」列（其余作为「数量」列）
_UNIT_COLS = {
    "皮壳含包装成本", "皮壳不含包装成本", "皮壳成本", "皮壳成本*系数",
    "绍兴二次加工成本", "绍兴二次加工成本*系数",
    "二次加工成本", "二次加工成本*系数",
    "头程运费金额", "海外仓成本",
}


def publish_to_gsheet(
    spreadsheet: str,
    frame: pd.DataFrame,
    review_blocks: list[list[list]],
    *,
    frame_title: str,
    review_title: str,
    chunk: int = 1500,
) -> dict[str, int]:
    """把「规则后整帧」+「核验摘要」写成 gsheet 新表（**只增表，不动既有表**）。

    仅当显式传 `--write-gsheet` 时才调用；默认全程只读。
    """
    import gspread  # noqa: F401 - 运行时依赖

    from tongtool_order_cost import gsheets
    from tongtool_order_cost.audit_sources import _retry

    sh = _retry(lambda: gsheets.client().open(spreadsheet))
    gids: dict[str, int] = {}

    def _fresh(title: str, rows: int, cols: int):
        try:
            sh.del_worksheet(_retry(lambda: sh.worksheet(title)))
        except Exception:  # noqa: BLE001 - 不存在即跳过
            pass
        return _retry(lambda: sh.add_worksheet(title=title, rows=rows, cols=cols))

    vals = frame.fillna("")
    hdr = [str(c) for c in vals.columns]
    data = vals.values.tolist()
    ws = _fresh(frame_title, len(data) + 2, len(hdr))
    _retry(lambda: ws.update([hdr], "A1"))
    for i in range(0, len(data), chunk):
        part = data[i : i + chunk]
        _retry(lambda p=part, i=i: ws.update(p, f"A{i + 2}"))
    gids[frame_title] = ws.id

    def _block(rows: list[list]) -> list[list]:
        w = max((len(r) for r in rows), default=1)
        return [[("" if c is None else c) for c in r] + [""] * (w - len(r)) for r in rows]

    review = _fresh(review_title, 6000, 40)
    flat: list[list] = []
    for rows in review_blocks:
        flat += _block(rows)
        flat += [[""]]
    flat = _block(flat)
    _retry(lambda: review.update(flat, "A1"))
    gids[review_title] = review.id
    return gids


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--month", default="202607")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dedup-keep", choices=("last", "first"), default="last")
    ap.add_argument("--write-gsheet", default="", metavar="SPREADSHEET",
                    help="显式指定要写入的 gsheet 名（默认不写，全程只读）")
    args = ap.parse_args(argv)

    snapshot = Path(args.snapshot)
    orders = load_orders(snapshot)
    rules = pd.read_csv(args.rules, encoding="utf-8-sig", low_memory=False)
    fx, fx_source = load_fx_table(orders=orders)

    result = apply_special_rules(
        orders, rules, args.month, fx,
        dedup_keep=args.dedup_keep, fx_source=fx_source, verbose=False,
    )
    events = result.change_events if result.change_events is not None else pd.DataFrame()

    checks = assert_events(events) if len(events) else pd.DataFrame()
    if len(checks):
        bad = checks[checks["ok"] == "0"]
        skipped = checks[checks["ok"] == ""]
    else:
        bad = skipped = pd.DataFrame()

    # 未被任何规则命中的订单
    touched = set()
    if len(events):
        touched = set(events["order_key"].astype(str))
    all_keys = orders.apply(
        lambda r: "|".join(str(r.get(c, "")) for c in
                           ["运营人员", "发货仓按销售汇总分类", "发货区域",
                            "渠道账号不含国家", "渠道账号", "通途SKU"]), axis=1)
    untouched = pd.DataFrame({"order_key": sorted(set(all_keys) - touched)})

    print(f"orders={orders.shape[0]} rules={rules.shape[0]} events={len(events)}")
    print(f"算术断言: 通过={int((checks['ok']=='1').sum()) if len(checks) else 0} "
          f"不通过={len(bad)} 跳过(按设计)={len(skipped)}")
    if len(bad):
        print(bad.head(10).to_string())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_audit_workbook(result, out)
    # 追加本核验专属的几张表
    with pd.ExcelWriter(out, engine="openpyxl", mode="a") as writer:
        checks.to_excel(writer, sheet_name="07_算术断言", index=False)
        bad.to_excel(writer, sheet_name="08_断言不通过", index=False)
        untouched.to_excel(writer, sheet_name="09_未被命中订单", index=False)
    print(f"审计簿: {out}")

    if args.write_gsheet:
        gids = publish_to_gsheet(
            args.write_gsheet,
            result.orders,
            [
                [["【总览】"]] + block_from_xlsx(out, "00_总览"),
                [["【实际应用的规则】"]] + block_from_xlsx(out, "02_按规则汇总"),
                [["【未命中规则】"]] + block_from_xlsx(out, "05_未命中规则"),
            ],
            frame_title="特殊规则_写回2026年7月FBA订单和非FBA订单",
            review_title="特殊规则_1.7.0规则核验%s" % args.month,
        )
        print("已写入 gsheet:", gids)
    return 0


def block_from_xlsx(path: Path, sheet: str) -> list[list]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    return [list(r) for r in wb[sheet].iter_rows(values_only=True)]


if __name__ == "__main__":
    raise SystemExit(main())
