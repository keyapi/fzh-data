"""美国/波兰仓库归属 v6：加双仓销售（2026 / 近6月）与判定。

基于 v5 工作簿（只读打开），新增：
- 1_美国归属与补货 追加三列：双仓销售2026 / 双仓销售近6月 / 双仓判定（实质/少量/单仓）
- 实质双仓（两边各 ≥10% 总销量）的「美国归属」「美国补货建议」改为双仓表述
- 少量双仓在「运营备注」追加一行备注
- 新增 sheet `11_双仓销售`：25 个双仓 SKU + 阈值说明
- `0_说明` 追加 v6 变更说明

阈值：2026 美东>0 且 美中>0 → 双仓；两边各 ≥10% 总销量 → 实质双仓；否则少量双仓。
只读输入；输出 v6，保留 v5。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SHEET_US = "1_美国归属与补货"
COL_E = "2026销售-美东USNJ(1-10月)"
COL_Z = "2026销售-美中USTX(1-10月)"
COL_E6 = "近6月销售-美东"
COL_Z6 = "近6月销售-美中"
THRESHOLD = 0.10


def fmt(x) -> str:
    value = float(x or 0)
    return f"{value:g}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="D:/Work/fzh-order-store/analysis/美国与波兰仓库归属_2026-10-28_v5.xlsx")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/美国与波兰仓库归属_2026-10-28_v6.xlsx")
    args = ap.parse_args()

    df = pd.read_excel(args.src, sheet_name=SHEET_US)
    required = [COL_E, COL_Z, COL_E6, COL_Z6]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"v5 缺少列：{missing}")

    e = pd.to_numeric(df[COL_E], errors="coerce").fillna(0)
    z = pd.to_numeric(df[COL_Z], errors="coerce").fillna(0)
    e6 = pd.to_numeric(df[COL_E6], errors="coerce").fillna(0)
    z6 = pd.to_numeric(df[COL_Z6], errors="coerce").fillna(0)
    total = e + z
    share_z = z.where(total > 0, 0) / total.where(total > 0, 1)

    both = (e > 0) & (z > 0)
    substantive = both & (share_z >= THRESHOLD) & (share_z <= 1 - THRESHOLD)
    small = both & ~substantive
    single = ~both

    def judge(i: int) -> str:
        if substantive.iat[i]:
            return "实质双仓"
        if small.iat[i]:
            return "少量双仓"
        return "单仓"

    df["双仓销售2026"] = [f"美东{fmt(a)} / 美中{fmt(b)}" for a, b in zip(e, z)]
    df["双仓销售近6月"] = [f"美东{fmt(a)} / 美中{fmt(b)}" for a, b in zip(e6, z6)]
    df["双仓判定（实质/少量/单仓）"] = [judge(i) for i in range(len(df))]

    for col in ("运营备注", "美国归属", "美国补货建议"):
        if col in df.columns:
            df[col] = df[col].astype(object)

    changed_owner, changed_advice, noted = [], [], []
    for i in range(len(df)):
        if substantive.iat[i]:
            df.at[i, "美国归属"] = f"双仓（美东{fmt(e.iat[i])} / 美中{fmt(z.iat[i])}）"
            df.at[i, "美国补货建议"] = (
                f"双仓销售：美东{fmt(e.iat[i])}/美中{fmt(z.iat[i])}，按两仓分别补/核")
            changed_owner.append(df.at[i, "EN物料"])
        elif small.iat[i]:
            minor = "美中" if share_z.iat[i] < 0.5 else "美东"
            minor_share = share_z.iat[i] if minor == "美中" else 1 - share_z.iat[i]
            share_text = f"{minor_share:.0%}" if minor_share >= 0.01 else f"{minor_share:.1%}"
            note = (f"双仓少量：美东{fmt(e.iat[i])}/美中{fmt(z.iat[i])}"
                    f"（另一仓占比 {share_text}），仍按主仓；例外时核对{minor}")
            old = df.at[i, "运营备注"] if isinstance(df.at[i, "运营备注"], str) else ""
            df.at[i, "运营备注"] = (old + "；" if old else "") + note
            noted.append(df.at[i, "EN物料"])

    # ---- 写回工作簿 ----
    wb = load_workbook(args.src)
    ws = wb[SHEET_US]
    headers = [c.value for c in ws[1]]
    new_cols = ["双仓销售2026", "双仓销售近6月", "双仓判定（实质/少量/单仓）"]
    start = ws.max_column + 1
    for offset, name in enumerate(new_cols):
        cell = ws.cell(row=1, column=start + offset, value=name)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E1F2")
        ws.column_dimensions[get_column_letter(start + offset)].width = 26

    idx = {name: i for i, name in enumerate(headers)}
    for r in range(2, ws.max_row + 1):
        row = r - 2
        if row >= len(df):
            break
        for offset, name in enumerate(new_cols):
            ws.cell(row=r, column=start + offset, value=df.at[row, name])
        # 实质双仓：覆盖归属与建议；少量：写备注
        if df.at[row, "双仓判定（实质/少量/单仓）"] == "实质双仓":
            if "美国归属" in idx:
                ws.cell(row=r, column=idx["美国归属"] + 1, value=df.at[row, "美国归属"])
            if "美国补货建议" in idx:
                ws.cell(row=r, column=idx["美国补货建议"] + 1, value=df.at[row, "美国补货建议"])
        elif "运营备注" in idx:
            ws.cell(row=r, column=idx["运营备注"] + 1, value=df.at[row, "运营备注"])

    # ---- 新 sheet 11_双仓销售 ----
    dual = df[both].copy()
    dual["_e"] = e[both]
    dual["_z"] = z[both]
    dual["_share"] = share_z[both]
    dual["_substantive"] = substantive[both]
    dual = dual.sort_values(["_substantive", "_share"], ascending=[False, False])
    ws2 = wb.create_sheet("11_双仓销售")
    ws2["A1"] = ("双仓销售（2026 美东>0 且 美中>0）：%d 个；其中两边各≥%d%% 总销量＝实质双仓 %d 个。"
                 "阈值：实质双仓需 min(美东,美中)/合计 ≥ %.0f%%；否则为少量双仓。"
                 % (len(dual), int(THRESHOLD * 100), int(substantive.sum()), THRESHOLD * 100))
    ws2["A1"].font = Font(bold=True)
    ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=14)
    ws2["A2"] = ("来源：本工作簿 1_美国归属与补货 的 2026销售/近6月销售（美东 USNJ / 美中 USTX）；近6月列沿用 v5 "
                 "口径。判定只看 2026 全年销量占比；近6月仅展示，不改变判定。"
                 "实质双仓的归属/建议已改为「按两仓分别补/核」；少量双仓写在运营备注。")
    ws2["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws2.merge_cells(start_row=2, start_column=1, end_row=2, end_column=14)
    ws2.row_dimensions[2].height = 42

    head = ["EN物料", "物料名称", "分组", "绍兴发货方式", "美东2026", "美中2026", "合计2026",
            "美中占比", "判定", "近6月美东", "近6月美中", "当前归属(v5原文)", "调整后归属", "建议"]
    for j, name in enumerate(head, start=1):
        cell = ws2.cell(row=4, column=j, value=name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3864")
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for i, (_, row) in enumerate(dual.iterrows(), start=5):
        verdict = "实质双仓" if row["双仓判定（实质/少量/单仓）"] == "实质双仓" else "少量双仓"
        values = [
            row["EN物料"], row["物料名称"], row.get("分组"), row.get("绍兴发货方式"),
            int(row["_e"]), int(row["_z"]), int(row["_e"] + row["_z"]),
            f"{float(row['_share']):.1%}", verdict,
            int(pd.to_numeric(pd.Series([row[COL_E6]]), errors="coerce").fillna(0).iloc[0]),
            int(pd.to_numeric(pd.Series([row[COL_Z6]]), errors="coerce").fillna(0).iloc[0]),
            row.get("美国归属(v5原文)") if "美国归属(v5原文)" in row else None,
            (f"双仓（美东{fmt(row['_e'])} / 美中{fmt(row['_z'])}）" if verdict == "实质双仓"
             else (f"仍按美中（美东少量 {1 - row['_share']:.1%}）" if row["_share"] >= 0.5
                   else f"仍按美东（美中少量 {row['_share']:.1%}）")),
            row["美国补货建议"] if verdict == "实质双仓" else "按主仓补；例外时核对另一仓",
        ]
        for j, value in enumerate(values, start=1):
            cell = ws2.cell(row=i, column=j, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # 当前归属(v5原文) 从原表读取
    original_owner = pd.read_excel(args.src, sheet_name=SHEET_US)["美国归属"].tolist()
    original_map = dict(zip(pd.read_excel(args.src, sheet_name=SHEET_US)["EN物料"], original_owner))
    for i, (_, row) in enumerate(dual.iterrows(), start=5):
        ws2.cell(row=i, column=12, value=original_map.get(row["EN物料"]))

    widths = [26, 34, 20, 12, 10, 10, 10, 9, 10, 10, 10, 16, 24, 34]
    for j, w in enumerate(widths, start=1):
        ws2.column_dimensions[get_column_letter(j)].width = w
    ws2.freeze_panes = "A5"

    # ---- 0_说明 追加 ----
    ws0 = wb["0_说明"]
    base = ws0.max_row + 1
    ws0.cell(row=base, column=1, value="v6（2026-10-29）：新增双仓销售分析")
    ws0.cell(row=base, column=1).font = Font(bold=True)
    notes = [
        f"1）2026 美东>0 且 美中>0 共 {int(both.sum())} 个；两边各≥{int(THRESHOLD*100)}% 总销量＝实质双仓 {int(substantive.sum())} 个。",
        "2）1_美国归属与补货 追加三列：双仓销售2026 / 双仓销售近6月 / 双仓判定（实质/少量/单仓）。",
        f"3）实质双仓 {len(changed_owner)} 行的「美国归属」「美国补货建议」已改为双仓表述：按两仓分别补/核。",
        f"4）少量双仓 {len(noted)} 行在「运营备注」注明另一仓占比，仍按主仓。",
        "5）新增 sheet 11_双仓销售：25 个双仓 SKU 明细 + 阈值说明。",
        "6）v5 原文件保留；本 v6 只读并入，不改 v5。",
    ]
    for k, text in enumerate(notes, start=1):
        ws0.cell(row=base + k, column=1, value=text)

    out = Path(args.out)
    wb.save(out)
    print(f"both={int(both.sum())} substantive={int(substantive.sum())} small={int(small.sum())} "
          f"changed_owner={len(changed_owner)} noted={len(noted)} out={out}")
    print("实质双仓 SKU：")
    for sku in changed_owner:
        r = df[df["EN物料"] == sku].iloc[0]
        print(" ", sku, r["双仓销售2026"], "|", df.loc[df["EN物料"] == sku, "美国补货建议"].iloc[0])


if __name__ == "__main__":
    main()
