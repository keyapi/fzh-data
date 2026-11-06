# -*- coding: utf-8 -*-
"""Append W2/W3 findings to the boss workbook v3 as v3b (no source changes)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

BASE = Path("D:/Work/fzh-order-store/analysis")
V3 = BASE / "D_老板版补货建议_2026-11-09_v3.xlsx"
W2 = BASE / "round15_firstlate_rescue.csv"
W3 = BASE / "round15_60cm_dnpo_audit.csv"
OUT = BASE / "D_老板版补货建议_2026-11-09_v3b.xlsx"


def style(ws):
    head_fill = PatternFill("solid", fgColor="1F4E78")
    head_font = Font(color="FFFFFF", bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for c in ws[1]:
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(vertical="center", wrap_text=True)
    widths = {}
    for row in ws.iter_rows(values_only=True):
        for i, v in enumerate(row, 1):
            widths[i] = min(46, max(widths.get(i, 10), len(str(v)) + 2))
    for i, w in widths.items():
        ws.column_dimensions[get_column_letter(i)].width = w


def main() -> int:
    w2 = pd.read_csv(W2)
    w3 = pd.read_csv(W3)
    keys = w3[w3["record_type"].astype(str) == "key"].copy()
    dn = w3[w3["record_type"].astype(str) == "dn"].copy()

    wb = load_workbook(V3)
    # 9_首批空运复算
    ws = wb.create_sheet("9_首批空运复算")
    ws.append(list(w2.columns))
    for rec in w2.itertuples(index=False):
        ws.append(list(rec))
    style(ws)

    # 10_60cm与DN-PO审计
    ws2 = wb.create_sheet("10_60cm与DN-PO审计")
    total = float(pd.to_numeric(keys["qty_v3_5"], errors="coerce").fillna(0).sum())
    po_ok = int(keys["PO状态"].astype(str).eq("exact_full").sum())
    po_missing = int(keys["PO状态"].astype(str).eq("无").sum())
    missing_qty = float(pd.to_numeric(keys["PO缺口件数"], errors="coerce").fillna(0).sum())
    top = keys.sort_values("PO缺口件数", ascending=False).head(3)
    top_txt = "、".join(f"{r.product_id.split('-60-')[-1]} {r.PO缺口件数:.0f}"
                       for r in top.itertuples(index=False))
    summary = [
        ("项", "结论"),
        ("4,001 件口径", f"{len(keys)} 个 kept_no_target 键，qty_v3_5 合计 {total:,.0f}"),
        ("C 覆盖", "exact_full %d/%d，合计 239" % (len(keys), len(keys))),
        ("EN 覆盖", "exact_full %d/%d，合计 239（同一波兰物理池，不可相加）" % (len(keys), len(keys))),
        ("PO 覆盖", f"exact_full {po_ok}/{len(keys)}；无 PO {po_missing}/{len(keys)}，缺 {missing_qty:,.0f} 件"),
        ("Top PO 缺口", top_txt),
        ("DN↔PO", f"台账 {len(dn)} 个 DN 全部 1 PO；EN 14 个 DN 中 3 个不在台账"),
        ("阶段完整性", "DN日期 71/71；Shipment 51/71；depart 10/71；arrive/warehouse_in 全空，到货/入仓不可自动确认"),
    ]
    ws2.append(summary[0])
    for r in summary[1:]:
        ws2.append(list(r))
    ws2.append([])
    ws2.append(list(keys.columns))
    for rec in keys.itertuples(index=False):
        ws2.append(list(rec))
    style(ws2)

    # append short notes to 0_老板先看
    ws0 = wb["0_老板先看"]
    extra = [
        ("首批晚于停工 4 键", "首批改空运后 4 键均可执行：CMM-140、CMKTR-100（fill95），GDR-153、CMPR-100（cycle95）；271 件，待人工确认。"),
        ("KS0321 fail", "换运输无效；总供给 85 vs 180天 p95≈94，需加约 18 件或接受风险。"),
        ("60cm 4,001 件", f"20 个保留键；C/EN 各 20/20 exact_full（239 同一物理池，不可相加）；PO 仅 {po_ok}/20，{po_missing} 键缺 {missing_qty:,.0f} 件。"),
        ("DN/PO 阶段", "台账 11 DN 全 1:1；14 EN DN 中 3 个缺失；arrive/warehouse_in 全空，到货/入仓需人工补证。"),
    ]
    for a, b in extra:
        ws0.append([a, b])
    for row in ws0.iter_rows(min_row=ws0.max_row - len(extra) + 1, max_row=ws0.max_row):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws0.column_dimensions["A"].width = 24
    ws0.column_dimensions["B"].width = 110

    wb.save(OUT)
    print("wrote", OUT)
    print("keys", len(keys), "total", total, "po_ok", po_ok, "po_missing", po_missing,
          "missing_qty", missing_qty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
