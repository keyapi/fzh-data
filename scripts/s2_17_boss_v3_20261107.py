# -*- coding: utf-8 -*-
"""v3 readability layer for the boss/ops replenishment workbook.

Reads v2 (read-only), copies every existing sheet and its data verbatim, then:
  1. appends a three-company bucket table below the notes on 0_老板先看
  2. adds 7_本周行动清单 (action list grouped by status)
  3. adds 8_使用说明 (legend, filtering, dates, numbers that must not be summed)
  4. applies print setup: 0 sheet landscape / one page wide; every sheet frozen
     header row, autofilter and readable column widths.

The source workbook is never written.  Acceptance invariants (row counts, boss
key figures) are asserted before the process exits.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

BASE = Path("D:/Work/fzh-order-store/analysis")
SRC = BASE / "D_老板版补货建议_2026-11-07_v2.xlsx"
OUT = BASE / "D_老板版补货建议_2026-11-09_v3.xlsx"

BRANCHES = ["美东USNJ", "美中USTX", "波兰"]
BRANCH_ORD = {b: i for i, b in enumerate(BRANCHES)}

# Status -> fill colour, kept identical to the fills already used on sheet 1.
FILLS = {
    "可以补-待确认": "C6EFCE",
    "补-待排期": "DDEBF7",
    "补-下单日已过-需重排": "FCE4D6",
    "先换运输再补": "FFF2CC",
    "首批要改空运/提前": "FCE4D6",
    "方案未达95%-需调整": "FCE4D6",
    "可能断货-需拍板": "F8CBAD",
    "新增资格-待复审": "E4DFEC",
    "需求看不清-先别补": "D9E1F2",
    "需求异常-不判定": "D9E1F2",
    "催已有订单": "FFF2CC",
    "不用补": "EDEDED",
    "继续观察": "EDEDED",
}
COLOR_NAMES = {
    "C6EFCE": "绿色",
    "DDEBF7": "浅蓝色",
    "FCE4D6": "浅橙色",
    "FFF2CC": "浅黄色",
    "F8CBAD": "深橙色",
    "E4DFEC": "浅紫色",
    "D9E1F2": "蓝灰色",
    "EDEDED": "灰色",
}
STATUS_NOTES = {
    "可以补-待确认": "轨迹模拟达到 95% 服务，且没有首批晚于停工/断货/模型异常；运营确认后即可下单。",
    "补-待排期": "D6 认为要补，但不在春节方案内；需单独排期/审核。",
    "补-下单日已过-需重排": "D6 候选但下单日已过，需重新排期。",
    "先换运输再补": "原运输晚于断货日，但更快运输可赶上；需确认舱位/运价。",
    "催已有订单": "催在途/PO，不是新增采购。",
    "首批要改空运/提前": "首批到仓晚于 1/24 停工；需改空运或提前。",
    "方案未达95%-需调整": "模拟跑完但没到 95% 服务；需加量/提前/升舱或接受风险。",
    "可能断货-需拍板": "所有已验证运输都晚于断货日；需业务决定接受风险/需求抑制/加急。",
    "新增资格-待复审": "60cm 供给恢复后观察转补的键；不在春节包，需单独资格复审。",
    "需求看不清-先别补": "p50=0、q95>0；模型待验证，建议量 0，禁止执行。",
    "需求异常-不判定": "需求尾部极厚；模拟不稳定，单列不判定。",
    "继续观察": "覆盖足够或政策/数据原因；不是“没需求”。",
    "不用补": "覆盖足够；不是“没需求”。",
}

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
SECTION_FILL = PatternFill("solid", fgColor="305496")
SECTION_FONT = Font(color="FFFFFF", bold=True, size=11)
SUMMARY_FILL = PatternFill("solid", fgColor="EDEDED")
BOLD = Font(bold=True)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def disp_len(value: object) -> int:
    """Approximate Excel display width: CJK chars count 2, ASCII 1."""
    return sum(1 if ord(ch) < 128 else 2 for ch in str(value))


def fmt_qty(value: object) -> int | str:
    v = pd.to_numeric(value, errors="coerce")
    if pd.isna(v):
        return "—"
    return int(round(float(v)))


def dash(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return text if text and text.lower() != "nan" else "—"


def read_source() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_excel(SRC, sheet_name="1_逐商品建议")
    boss = pd.read_excel(SRC, sheet_name="0_老板先看")
    return d, boss


# --------------------------------------------------------------------------- #
# 0_老板先看: append the three-company bucket table
# --------------------------------------------------------------------------- #
BUCKET_LABELS = [
    ("需求键数", "需求键数"),
    ("可以补-待确认", "可以补-待确认"),
    ("先换运输再补", "先换运输再补"),
    ("首批要改空运/提前", "首批要改空运/提前"),
    ("补-待排期", "补-待排期"),
    ("补-下单日已过-需重排", "补-下单日已过-需重排"),
    ("可能断货-需拍板", "可能断货-需拍板"),
    ("方案未达95%", "方案未达95%-需调整"),
    ("需求看不清", "需求看不清-先别补"),
    ("不用补", "不用补"),
    ("继续观察", "继续观察"),
]
# Everything except the row-total column; the row total is len(sub), not a status.
BUCKET_METRICS = [(label, status) for label, status in BUCKET_LABELS
                  if label != "需求键数"]


def append_bucket_table(ws, d: pd.DataFrame) -> None:
    first_free = ws.max_row + 2  # one blank row after the notes
    caption_row = first_free
    header_row = caption_row + 1
    first_branch_row = header_row + 1
    last_branch_row = first_branch_row + len(BRANCHES) - 1
    total_row = last_branch_row + 1
    note_row = total_row + 2

    n_cols = 2 + len(BUCKET_METRICS)  # 分公司 + 需求键数 + 10 bucket columns

    # Merge the long explanation column of the existing notes so the bucket
    # table can use compact 12-13 wide columns underneath.
    for r in range(1, caption_row - 1):
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=n_cols)
        cell = ws.cell(row=r, column=2)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        # merged cells do not auto-fit; size the row from the text itself
        capacity = 137  # widths B..L after formatting, in Excel character units
        lines = max(1, math.ceil(disp_len(cell.value) / capacity))
        ws.row_dimensions[r].height = max(18, 16 * lines + 4)

    # Header row of the notes (A1:B1) now spans the merged range visually.
    for c in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    # Caption
    ws.merge_cells(start_row=caption_row, start_column=1,
                   end_row=caption_row, end_column=n_cols)
    cap = ws.cell(row=caption_row, column=1,
                  value="三家公司分桶表（值 = 需求键数，单位：个）")
    cap.font = Font(bold=True, size=12)
    cap.fill = PatternFill("solid", fgColor="DDEBF7")
    cap.alignment = Alignment(vertical="center")
    ws.row_dimensions[caption_row].height = 22

    # Column headers
    headers = ["分公司"] + [label for label, _ in BUCKET_LABELS]
    for i, name in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=i, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[header_row].height = 46

    # Branch rows + total row
    bucket_values: list[list[int]] = []
    for br in BRANCHES:
        sub = d[d["分公司"].eq(br)]
        vc = sub["一句话建议"].value_counts()
        bucket_values.append(
            [len(sub)] + [int(vc.get(status, 0)) for _, status in BUCKET_METRICS])
    totals = [sum(col) for col in zip(*bucket_values)]

    for idx, (br, vals) in enumerate(zip(BRANCHES, bucket_values)):
        r = first_branch_row + idx
        ws.cell(row=r, column=1, value=br).font = BOLD
        for c, v in enumerate(vals, 2):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = Alignment(horizontal="center")
        for c in range(1, n_cols + 1):
            ws.cell(row=r, column=c).border = BORDER

    ws.cell(row=total_row, column=1, value="合计").font = BOLD
    for c, v in enumerate(totals, 2):
        cell = ws.cell(row=total_row, column=c, value=v)
        cell.font = BOLD
        cell.alignment = Alignment(horizontal="center")
    for c in range(1, n_cols + 1):
        cell = ws.cell(row=total_row, column=c)
        cell.border = BORDER
        cell.fill = SUMMARY_FILL

    os_status = {
        "催已有订单": int((d["一句话建议"] == "催已有订单").sum()),
        "新增资格-待复审": int((d["一句话建议"] == "新增资格-待复审").sum()),
        "需求异常-不判定": int((d["一句话建议"] == "需求异常-不判定").sum()),
    }
    off_sum = sum(os_status.values())
    listed = sum(totals[1:])
    footnote = (
        f"说明：需求键数 {totals[0]:,} 含全部 13 种状态；本表 10 个分桶列不含"
        f"“催已有订单 {os_status['催已有订单']}、新增资格-待复审 "
        f"{os_status['新增资格-待复审']}、需求异常-不判定 "
        f"{os_status['需求异常-不判定']}”（合计 {off_sum} 键），"
        f"因此 10 列横向相加 = {listed:,}，不等于需求键数 {totals[0]:,}。"
    )
    ws.merge_cells(start_row=note_row, start_column=1,
                   end_row=note_row, end_column=n_cols)
    note = ws.cell(row=note_row, column=1, value=footnote)
    note.alignment = Alignment(wrap_text=True, vertical="top")
    note.font = Font(italic=True, color="595959")
    capacity = 150
    lines = max(1, math.ceil(disp_len(footnote) / capacity))
    ws.row_dimensions[note_row].height = max(18, 16 * lines + 4)

    # Print setup: landscape, one page wide.
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_area = f"A1:{get_column_letter(n_cols)}{note_row}"

    # Filter on the bucket table only (notes above stay unfiltered).
    ws.auto_filter.ref = (
        f"A{header_row}:{get_column_letter(n_cols)}{total_row}")

    widths = {"A": 28}
    widths.update({get_column_letter(c): 12.5 for c in range(2, n_cols + 1)})
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


# --------------------------------------------------------------------------- #
# 7_本周行动清单
# --------------------------------------------------------------------------- #
ACTION_COLS = ["序号", "状态", "分公司", "商品名称", "商品编码", "键数",
               "建议补多少", "首批下单日", "首批到仓/要求到仓",
               "需要谁决定", "证据链摘要"]


def evidence_brief(row: pd.Series) -> str:
    status = str(row.get("一句话建议", ""))
    parts: list[str] = []
    lead = {
        "可能断货-需拍板": "全部已验证运输都晚于断货日",
        "先换运输再补": "原运输晚于断货日，更快运输可赶上",
        "首批要改空运/提前": "首批到仓晚于 1/24 停工",
        "需求看不清-先别补": "p50=0、q95>0，模型待验证",
    }.get(status)
    if lead:
        parts.append(lead)
    basis = dash(row.get("依据"))
    if basis != "—":
        parts.append(basis)
    if str(row.get("方案类型")) == "春节方案":
        first_qty = fmt_qty(row.get("首批数量"))
        parts.append(f"首批 {first_qty} 件 @ {dash(row.get('首批到仓/要求到仓'))}")
        second_qty = pd.to_numeric(row.get("第二批数量"), errors="coerce")
        if pd.notna(second_qty) and float(second_qty) > 0:
            parts.append(f"二批 {int(round(float(second_qty)))} 件 "
                         f"@ {dash(row.get('第二批到仓'))}")
    else:
        parts.append(f"要求到仓 {dash(row.get('首批到仓/要求到仓'))}")
    remark = str(row.get("风险/备注", ""))
    remark = "；".join(p for p in remark.split("；") if p.strip() and p.strip() != "nan")
    if remark:
        parts.append(f"备注：{remark}")
    text = "；".join(parts)
    return text if len(text) <= 220 else text[:217] + "…"


def build_action_rows(d: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    seq = 0
    sections = [
        ("可以补-待确认", True, False,
         "今天可以确认，运营确认后即可下单"),
        ("先换运输再补", True, False,
         "物流确认更快运输的舱位与运价后即可补"),
        ("首批要改空运/提前", True, False,
         "首批到仓晚于 1/24 停工，需改空运或提前"),
        ("补-下单日已过-需重排", True, True,
         "先看分公司汇总，再逐条重排下单日"),
        ("可能断货-需拍板", False, True,
         "按分公司汇总；所有已验证运输都晚于断货日，需业务拍板"),
        ("需求看不清-先别补", False, True,
         "按分公司汇总；建议补量 0，禁止执行"),
    ]
    for num, (status, with_detail, with_summary, subtitle) in enumerate(sections, 1):
        sub = d[d["一句话建议"].eq(status)].copy()
        sub["_b"] = sub["分公司"].map(BRANCH_ORD).fillna(99)
        sub = sub.sort_values(["_b", "建议补多少"], ascending=[True, False])
        qty = int(sub["建议补多少"].sum())
        cn_num = "一二三四五六七八九十"[num - 1]
        title = f"【{cn_num}】{status} · {len(sub)} 键 / {qty:,} 件 —— {subtitle}"
        rows.append({"kind": "section", "title": title})

        if with_summary:
            for br in BRANCHES:
                bsub = sub[sub["分公司"].eq(br)]
                rows.append({
                    "kind": "summary", "状态": "小计", "分公司": br,
                    "商品名称": "本分公司合计", "商品编码": "—",
                    "键数": len(bsub),
                    "建议补多少": int(bsub["建议补多少"].sum()),
                    "首批下单日": "—", "首批到仓/要求到仓": "—",
                    "需要谁决定": "—",
                    "证据链摘要": f"{status}：{len(bsub)} 键 / "
                                  f"{int(bsub['建议补多少'].sum()):,} 件"
                                  + ("；仅汇总，逐条见 1_逐商品建议"
                                     if not with_detail else "；明细见下"),
                })
            rows.append({
                "kind": "summary", "状态": "合计", "分公司": "合计",
                "商品名称": "三家公司合计", "商品编码": "—",
                "键数": len(sub), "建议补多少": qty,
                "首批下单日": "—", "首批到仓/要求到仓": "—",
                "需要谁决定": "—",
                "证据链摘要": f"{status} 合计 {len(sub)} 键 / {qty:,} 件",
            })

        if with_detail:
            for _, row in sub.iterrows():
                seq += 1
                rows.append({
                    "kind": "detail", "序号": seq, "状态": status,
                    "分公司": row["分公司"],
                    "商品名称": dash(row["商品名称"]),
                    "商品编码": dash(row["商品编码"]),
                    "键数": "",
                    "建议补多少": int(row["建议补多少"]),
                    "首批下单日": dash(row["首批下单日"]),
                    "首批到仓/要求到仓": dash(row["首批到仓/要求到仓"]),
                    "需要谁决定": dash(row["需要谁决定"]),
                    "证据链摘要": evidence_brief(row),
                })
    return rows


def write_action_sheet(ws, rows: list[dict]) -> None:
    for c, name in enumerate(ACTION_COLS, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[1].height = 30

    r = 2
    for item in rows:
        if item["kind"] == "section":
            ws.merge_cells(start_row=r, start_column=1,
                           end_row=r, end_column=len(ACTION_COLS))
            cell = ws.cell(row=r, column=1, value=item["title"])
            cell.fill = SECTION_FILL
            cell.font = SECTION_FONT
            cell.alignment = Alignment(vertical="center")
            for c in range(1, len(ACTION_COLS) + 1):
                ws.cell(row=r, column=c).border = BORDER
            ws.row_dimensions[r].height = 24
        else:
            values = [item.get(col, "") for col in ACTION_COLS]
            for c, v in enumerate(values, 1):
                cell = ws.cell(row=r, column=c, value=v)
                cell.border = BORDER
                cell.alignment = Alignment(vertical="top",
                                           wrap_text=(c in (4, 11)))
                if c == 7:
                    cell.number_format = "#,##0"
                    cell.alignment = Alignment(horizontal="right",
                                               vertical="top")
                elif c == 6:
                    cell.alignment = Alignment(horizontal="center",
                                               vertical="top")
            if item["kind"] == "summary":
                fill = SUMMARY_FILL
                for c in range(1, len(ACTION_COLS) + 1):
                    cell = ws.cell(row=r, column=c)
                    cell.fill = fill
                    cell.font = BOLD
            else:
                status = item["状态"]
                if status in FILLS:
                    ws.cell(row=r, column=2).fill = PatternFill(
                        "solid", fgColor=FILLS[status])
        r += 1

    widths = {"A": 6, "B": 22, "C": 10, "D": 34, "E": 30, "F": 8, "G": 11,
              "H": 12, "I": 13, "J": 12, "K": 88}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:K{r - 1}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_area = f"A1:K{r - 1}"
    ws.print_title_rows = "1:1"


# --------------------------------------------------------------------------- #
# 8_使用说明
# --------------------------------------------------------------------------- #
def build_usage_rows(d: pd.DataFrame) -> list[dict]:
    vc = d["一句话建议"].value_counts()
    now_order = ["可以补-待确认", "补-待排期", "补-下单日已过-需重排",
                 "先换运输再补", "催已有订单", "首批要改空运/提前",
                 "方案未达95%-需调整", "可能断货-需拍板", "新增资格-待复审",
                 "需求看不清-先别补", "需求异常-不判定", "继续观察", "不用补"]
    winter_keys = int(d["方案类型"].eq("春节方案").sum())
    winter_qty = int(d.loc[d["方案类型"].eq("春节方案"), "建议补多少"].sum())
    daily_keys = int(d["一句话建议"].isin(["补-待排期", "补-下单日已过-需重排"]).sum())
    daily_qty = int(d.loc[d["一句话建议"].isin(
        ["补-待排期", "补-下单日已过-需重排"]), "建议补多少"].sum())
    off_sum = int(vc.get("催已有订单", 0) + vc.get("新增资格-待复审", 0)
                  + vc.get("需求异常-不判定", 0))
    bucket_sum = int(len(d) - off_sum)

    rows: list[dict] = []

    def section(title: str) -> None:
        rows.append({"kind": "section", "title": title})

    def item(topic: str, status: str, note: str) -> None:
        rows.append({"kind": "row", "主题": topic, "状态": status, "说明": note})

    section("一、颜色图例（1_逐商品建议 的“一句话建议”列、7_本周行动清单 的“状态”列）")
    for status in now_order:
        count = int(vc.get(status, 0))
        color = FILLS.get(status, "FFFFFF")
        item("颜色图例", status,
             f"{COLOR_NAMES.get(color, color)}｜{STATUS_NOTES[status]}"
             f"（本表 {count} 键）")

    section("二、怎么筛选")
    item("筛选分公司", "自动筛选",
         "每张数据表首行已开启自动筛选。点“分公司”表头右侧的 ▼，勾选需要看的"
         "分公司（美东USNJ / 美中USTX / 波兰）。")
    item("筛选状态", "自动筛选",
         "1_逐商品建议 点“一句话建议”；7_本周行动清单 点“状态”。可多选，例如"
         "同时勾选“可以补-待确认”和“先换运输再补”。")
    item("按颜色找", "看颜色",
         "颜色只是提示。绿色=可确认，浅橙=已过期需重排或需改空运，"
         "深橙=断货风险，浅黄=换运输/催已有，灰=不用补/继续观察。")
    item("看证据", "证据链",
         "每一行都带“证据链摘要”（7 表）或“证据链”（1 表），写明需求 q95、"
         "可用 C、EN 在途/PO、下单日与到仓日；需要追根溯源时看 6_证据链。")

    section("三、数据日期与口径")
    item("数据日期", "2026-11-02 / 2026-11-05",
         "需求预测截至 2026-11-02；库存与在途快照截至 2026-11-05；"
         "决策基准日 2026-11-06。文件名中的 2026-11-09 是交付批次日期，"
         "数据口径未变。")
    item("分公司", "美东USNJ / 美中USTX / 波兰",
         "三个海外仓/公司在同一张表内并列，互不替代；同一商品编码可在不同"
         "分公司各成一行（各自的库存和需求不同）。")
    item("需求键", "商品 × 分公司 × 形态 × 单位",
         "一个“键”= 一个分公司下、一种形态、一种单位的一条商品需求；"
         "本表 1,564 个键，不能按商品编码去重后直接说“1,564 个商品”。")

    section("四、哪些数字不能相加（重点）")
    item("春节方案 ≠ 日常补货候选", f"{winter_keys} 键 / {winter_qty:,} 件 vs "
                                    f"{daily_keys} 键 / {daily_qty:,} 件",
         "春节排期方案与 D6 日常补货候选是两套口径，覆盖范围有重叠；"
         "两者不能相加，也不能互相替代。")
    item("分桶表横向不能相加", f"1,564 vs {bucket_sum:,}",
         f"“需求键数”含全部 13 种状态；分桶 10 列不含“催已有订单 "
         f"{int(vc.get('催已有订单', 0))}、新增资格-待复审 "
         f"{int(vc.get('新增资格-待复审', 0))}、需求异常-不判定 "
         f"{int(vc.get('需求异常-不判定', 0))}”（合计 {off_sum} 键），"
         f"所以横向相加 = {bucket_sum:,}，不等于 1,564。")
    item("可能断货 ≠ 已批准", "110 键 / 7,436 件",
         "“可能断货-需拍板”只是风险提示，未经业务拍板不能下单；"
         "不能直接计入本周采购量。")
    item("需求看不清 ≠ 0 需求", "66 键",
         "这 66 键建议补量为 0，是因为 p50=0、模型待验证，不代表市场没有需求；"
         "禁止当成“不用补”处理。")
    item("催已有订单 ≠ 新增采购", f"{int(vc.get('催已有订单', 0))} 键",
         "“催已有订单”是催在途/PO，不产生新的采购量，不能计入补货总量。")
    item("键数 ≠ 件数", "—",
         "键是需求行，件是数量；不同键的件数差异很大，汇总时请同时看键数和件数。")

    section("五、读表顺序建议")
    item("第 1 步", "0_老板先看",
         "先看总览与三家公司分桶表，确认今天能确认多少、哪些要拍板。")
    item("第 2 步", "7_本周行动清单",
         "按状态分节；先处理“可以补-待确认”，再处理“先换运输”和"
         "“首批改空运”，最后重排已过下单日的 199 键。")
    item("第 3 步", "1_逐商品建议",
         "需要逐商品核对或筛选时使用；可按分公司、状态、建议补多少排序。")
    item("第 4 步", "2_需要拍板 / 3_分公司汇总 / 6_证据链",
         "拍板清单、分公司汇总和逐项证据链；6_证据链与 1 表逐行对应。")

    return rows


def write_usage_sheet(ws, rows: list[dict]) -> None:
    headers = ["主题", "状态", "说明"]
    for c, name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER

    r = 2
    for item in rows:
        if item["kind"] == "section":
            ws.merge_cells(start_row=r, start_column=1,
                           end_row=r, end_column=3)
            cell = ws.cell(row=r, column=1, value=item["title"])
            cell.fill = SECTION_FILL
            cell.font = SECTION_FONT
            cell.alignment = Alignment(vertical="center")
            for c in range(1, 4):
                ws.cell(row=r, column=c).border = BORDER
            ws.row_dimensions[r].height = 22
        else:
            for c, key in enumerate(headers, 1):
                cell = ws.cell(row=r, column=c, value=item.get(key, ""))
                cell.border = BORDER
                cell.alignment = Alignment(vertical="top",
                                           wrap_text=(c == 3))
            status = item.get("状态", "")
            if status in FILLS and item.get("主题") == "颜色图例":
                ws.cell(row=r, column=2).fill = PatternFill(
                    "solid", fgColor=FILLS[status])
        r += 1

    for col, width in {"A": 16, "B": 30, "C": 96}.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:C{r - 1}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_area = f"A1:C{r - 1}"


# --------------------------------------------------------------------------- #
# Verification and main
# --------------------------------------------------------------------------- #
EXPECTED = {
    "可以补-待确认": 27,
    "先换运输再补": 8,
    "首批要改空运/提前": 4,
    "补-下单日已过-需重排": 199,
    "可能断货-需拍板": 110,
    "需求看不清-先别补": 66,
}


def verify(d: pd.DataFrame, action_rows: list[dict]) -> dict:
    detail_counts = {}
    summary_sums = {}
    for row in action_rows:
        if row["kind"] == "detail":
            detail_counts[row["状态"]] = detail_counts.get(row["状态"], 0) + 1
        if row["kind"] == "summary" and row["状态"] == "合计":
            summary_sums[row["证据链摘要"].split(" 合计")[0]] = row["键数"]
    assert detail_counts.get("可以补-待确认") == EXPECTED["可以补-待确认"]
    assert detail_counts.get("先换运输再补") == EXPECTED["先换运输再补"]
    assert detail_counts.get("首批要改空运/提前") == EXPECTED["首批要改空运/提前"]
    assert detail_counts.get("补-下单日已过-需重排") == EXPECTED["补-下单日已过-需重排"]
    for status in ("可能断货-需拍板", "需求看不清-先别补"):
        assert summary_sums.get(status) == EXPECTED[status], (status, summary_sums)
    for status, expected in EXPECTED.items():
        assert int((d["一句话建议"] == status).sum()) == expected, status
    return {"detail": detail_counts, "summary": summary_sums}


def main() -> int:
    d, boss_old = read_source()
    action_rows = build_action_rows(d)
    usage_rows = build_usage_rows(d)
    stats = verify(d, action_rows)

    shutil.copyfile(SRC, OUT)
    wb = load_workbook(OUT)

    ws0 = wb["0_老板先看"]
    append_bucket_table(ws0, d)

    ws7 = wb.create_sheet("7_本周行动清单")
    write_action_sheet(ws7, action_rows)

    ws8 = wb.create_sheet("8_使用说明")
    write_usage_sheet(ws8, usage_rows)

    # Every sheet: frozen first row, autofilter (sheet 0 keeps its own table
    # range), and a readable header style. Existing data sheets already carry
    # their filters from v2.
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        if ws.title not in ("0_老板先看", "7_本周行动清单", "8_使用说明"):
            ws.auto_filter.ref = ws.dimensions
            for c in ws[1]:
                c.alignment = Alignment(vertical="center", wrap_text=True)

    # ---- assertions before saving: no forbidden phrase, source untouched ----
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for value in row:
                if isinstance(value, str) and "8 款" in value:
                    raise AssertionError(f"forbidden wording in {ws.title}: {value}")
    assert (d["一句话建议"].value_counts().get("可以补-待确认") == 27)
    assert len(d) == 1564
    assert int(boss_old.shape[0]) == 11

    wb.save(OUT)

    # ---- post-save verification against v2 ----
    v2 = pd.ExcelFile(SRC)
    v3 = pd.ExcelFile(OUT)
    assert v3.sheet_names == v2.sheet_names + ["7_本周行动清单", "8_使用说明"], \
        v3.sheet_names
    for sheet in v2.sheet_names:
        old = pd.read_excel(SRC, sheet_name=sheet)
        new = pd.read_excel(OUT, sheet_name=sheet)
        if sheet == "0_老板先看":
            assert list(old.columns) == list(new.columns[:2])
            head = new.iloc[:len(old), :2].reset_index(drop=True)
            pd.testing.assert_frame_equal(
                old, head.set_axis(old.columns, axis=1), check_dtype=False)
        else:
            pd.testing.assert_frame_equal(old, new)
    check = pd.read_excel(OUT, sheet_name="1_逐商品建议")
    assert len(check) == 1564

    # Saved sheet 7 counts, read back from disk.
    s7 = pd.read_excel(OUT, sheet_name="7_本周行动清单")
    vc7 = s7["状态"].value_counts()
    for status in ("可以补-待确认", "先换运输再补", "首批要改空运/提前",
                   "补-下单日已过-需重排"):
        assert int(vc7.get(status, 0)) == EXPECTED[status], (status, vc7.get(status))
    subtotal = s7[s7["状态"].eq("小计")]
    assert int(subtotal["键数"].sum()) == 110 + 66 + 199, subtotal["键数"].sum()

    print("wrote", OUT)
    print("detail counts:", stats["detail"])
    print("summary totals:", stats["summary"])
    print("status counts:")
    print(d["一句话建议"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
