"""48 个「可补单—待定量」的人工决策草稿（DRAFT，只读）。

输入：48 原型 v2、53 分类 v3、46 近端调拨候选 v2、DuckDB（item_name/ship_type，read_only）。
输出：D:/Work/fzh-order-store/analysis/48待定量_人工决策草稿_2026-10-29.xlsx
       D:/Work/fzh-order-store/analysis/48待定量_人工决策草稿说明_2026-10-29.md

5 列：商品/目的仓/发货角色 · 现在是什么情况 · 系统决定做什么 · 什么时候/不做会怎样 · 人只确认什么
不新增推断、不填补空白；所有数字来自输入文件。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

WH_SHORT = {
    "美东-CENTRADE": "美东",
    "美中-FZH-DANEEY": "美中",
    "波兰-FZHPoland-covers": "波兰",
}
HEADERS = ["商品 / 目的仓 / 发货角色", "现在是什么情况", "系统决定做什么",
           "什么时候 / 不做会怎样", "人只确认什么"]


def short_date(value) -> str:
    text = str(value)
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return text
    return f"{match.group(2)}-{match.group(3)}"


def short_week(value) -> str:
    text = str(value)
    match = re.match(r"(\d{4}-\d{2}-\d{2})→(\d{4}-\d{2}-\d{2})", text)
    if match:
        return f"{short_date(match.group(1))}—{short_date(match.group(2))}（右端不含）"
    return text


def num(value, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", default="D:/Work/fzh-order-store/analysis/48待定量_97_157_原型_2026-10-28_v2.csv")
    ap.add_argument("--classify", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28_v3.csv")
    ap.add_argument("--transfer", default="D:/Work/fzh-order-store/analysis/46近端缺口_调拨候选_2026-10-28_v2.csv")
    ap.add_argument("--db", default="D:/Work/fzh-order-store/order_store.duckdb")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/48待定量_人工决策草稿_2026-10-29.xlsx")
    args = ap.parse_args()

    proto = pd.read_csv(args.proto, encoding="utf-8-sig")
    classify = pd.read_csv(args.classify, encoding="utf-8-sig")[["SKU", "仓库", "近端兜底", "分类"]]
    transfer = pd.read_csv(args.transfer, encoding="utf-8-sig")[
        ["SKU", "目的仓", "建议调拨上限", "调拨后仍缺", "跨洲排除供给"]].rename(columns={"目的仓": "仓库"})

    con = duckdb.connect(args.db, read_only=True)
    names = con.execute(
        "select upper(item) item, any_value(item_name) item_name from item_attr group by 1").df()
    roles = con.execute(
        "select upper(item_code) item, any_value(ship_type) ship_type from sku_item group by 1").df()

    df = proto.merge(classify, on=["SKU", "仓库"], how="left")
    df = df.merge(transfer, on=["SKU", "仓库"], how="left")
    df = df.merge(names, left_on="SKU", right_on="item", how="left").drop(columns="item")
    df = df.merge(roles, left_on="SKU", right_on="item", how="left").drop(columns="item")

    rows = []
    ordered = df.sort_values(["仓库", "Q_97目标"], ascending=[True, False]).to_dict("records")
    for idx, r in enumerate(ordered, start=1):
        wh = WH_SHORT.get(r["仓库"], r["仓库"])
        role = r["ship_type"] if isinstance(r.get("ship_type"), str) and str(r["ship_type"]).strip() else "角色未登记"
        name = r["item_name"] if isinstance(r.get("item_name"), str) and str(r["item_name"]).strip() else "（商品名未登记）"

        near = str(r.get("近端兜底")) == "调拨/加急/接受缺货（待定）"
        cur = float(r.get("当前可发_10-28同仓") or 0)
        q97 = float(r.get("Q_97目标") or 0)
        q157 = float(r.get("Q_157目标") or 0)
        ss_applied = str(r.get("安全库存政策")).startswith("应用")
        tier = r.get("档位") if isinstance(r.get("档位"), str) else ""
        up = float(r.get("建议调拨上限") or 0)
        remain = float(r.get("调拨后仍缺") or 0)
        cross = r.get("跨洲排除供给") if isinstance(r.get("跨洲排除供给"), str) else ""

        col1 = f"{idx:02d}  {name}\n{r['SKU']}\n{wh}｜绍兴发{role}｜{r['单位']}"

        col2 = "\n".join([
            f"10/28 同仓可发：{num(cur)} 个",
            f"97 天补量参考：{num(q97)} 个（102 天桶界）",
            f"157 天补量参考：{num(q157)} 个（158 天桶界）",
            f"首次缺口：{short_week(r['首次缺口周'])}",
            "近端：新单赶不上" if near else "非近端（11/16 起）",
            f"可同国调拨：上限 {num(up)}，调后仍缺 {num(remain)}" if up > 0 else "同国可调：无可调来源",
            f"仓池外供给（不可调）：{cross}" if cross else "",
        ]).strip()

        col3_lines = ["系统决定：待定量（不是采购量）"]
        col3_lines.append("近端：普通新单赶不上，先定调拨/加急/接受缺货" if near
                          else "非近端：等下一次刷新后再看")
        col3_lines.append(f"SS 政策：{tier} 档（政策情景；σ 为历史销量波动代理，服务未校准）"
                          if ss_applied else "SS：未应用销量波动代理/缺 σ")
        if q97 < 1 and q157 < 1:
            col3_lines.append(f"97/157 两窗口量近零（Q={num(q97)}/{num(q157)}），需人工复核")
        elif q97 < 1:
            col3_lines.append(f"97 天量近零（Q={num(q97)}），157 天为 {num(q157)}（>1），按窗口分别看")
        col3_lines.append("本次可审批采购量：未释放")
        col3 = "\n".join(col3_lines)

        col4 = "\n".join([
            f"最晚下单：{short_date(r['最晚下单日_P50'])}（已过）｜规划 {short_date(r['最晚下单日_规划'])}（已过）",
            f"10/29 下单→P50 {short_date(r['10-29下单到仓_P50'])}；规划 {short_date(r['10-29下单到仓_规划'])}",
            f"不做：长窗补量参考 {num(remain)} 个仍无着落（非救急量）",
            "口径：2.779 天盲区未估算；σ 未校准",
        ])

        col5_lines = ["只确认：仓库实物与内胆配套；是否有未登记在途"]
        if cur > 0:
            col5_lines.append(f"10/28 的 {num(cur)} 个是否真可售")
        if near:
            col5_lines.append("近端：加急还是接受缺货（待定）")
        col5_lines.append("例外：合同/活动/停产等外部事实")
        col5 = "\n".join(col5_lines)

        rows.append([col1, col2, col3, col4, col5])

    # ---------- 工作簿 ----------
    wb = Workbook()
    ws = wb.active
    ws.title = "48个决策"

    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:E1")
    ws["A1"] = "补货决策草稿｜48 个「可补单—待定量」"
    ws["A1"].font = Font(bold=True, size=16, color="1F3864")

    ws.merge_cells("A2:E2")
    ws["A2"] = "DRAFT｜设计未验收｜数字来自 97/157 原型，不是采购量；48 行全部未释放审批"
    ws["A2"].font = Font(bold=True, color="C00000")
    ws["A2"].fill = PatternFill("solid", fgColor="FFF2CC")

    ws.merge_cells("A3:E3")
    ws["A3"] = ("决策日 2026-10-29 · 库存 10/28 快照 · 需求为周桶积分（97 目标→102 天、157 目标→158 天）"
                " · 10/26→10/29 有 2.779 天盲区未估算 · 单位：个")
    ws["A3"].alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[3].height = 30

    header_row = 5
    for col, title in enumerate(HEADERS, start=1):
        cell = ws.cell(row=header_row, column=col, value=title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3864")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[header_row].height = 26

    for i, values in enumerate(rows, start=header_row + 1):
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=i, column=col, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = border
            cell.font = Font(size=10)
        ws.row_dimensions[i].height = 96

    footer = header_row + len(rows) + 2
    ws.merge_cells(start_row=footer, start_column=1, end_row=footer, end_column=5)
    ws.cell(row=footer, column=1,
            value=("说明：本表是 DRAFT，不是采购单。待定量=系统按 L+R 视界算出的补量参考，未释放审批；"
                   "近端行普通新单赶不上，只能调拨/加急/接受缺货；所有原值与口径见「口径与来源」。"))
    ws.cell(row=footer, column=1).font = Font(italic=True, color="595959")
    ws.cell(row=footer, column=1).alignment = Alignment(wrap_text=True, vertical="top")

    for i, width in enumerate([30, 48, 42, 42, 42], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A6"

    guide = wb.create_sheet("怎么看")
    guide_data = [
        ("怎么看这张表｜2 分钟完成一个决定", ""),
        ("", ""),
        ("这张表替你做什么", "系统先算 97/157 天补量、判断近端赶不赶得上、算最晚下单日；你只确认外部事实和例外。"),
        ("先看第 3 列｜系统决定", "48 行全是「待定量」，本次没有可审批采购量；近端行系统已判定普通新单赶不上。"),
        ("再看第 4 列｜赶不赶得上", "「首次缺口」只到周，不是精确断货日；最晚下单日都已在 10/28 之前过去。"),
        ("数量怎么读", "97/157 是周桶积分（102/158 天桶界），SS 只在 8 行有销量波动代理；都不是采购批准量。"),
        ("你只做三类事", "仓库确认实物与内胆；物流确认未登记在途；负责人决定加急或接受缺货、批准例外。"),
        ("单位和地区", "个/套分开；美东与美中可调拨，波兰与美国不可互调（波兰 32 行无可调来源）。"),
        ("口径提醒", "10/26→10/29 有 2.779 天需求盲区未估算；σ 是历史销量波动代理、服务水平未校准。"),
        ("看完后怎么做", "确认事实后由系统重算并释放；未回复不默认同意。"),
        ("", ""),
        ("记住：你确认事实/例外；系统负责算数、查重、定量、定期限。", ""),
    ]
    for i, (a, b) in enumerate(guide_data, start=1):
        guide.cell(row=i, column=1, value=a).font = Font(bold=(i == 1), size=12 if i == 1 else 10)
        guide.cell(row=i, column=2, value=b).alignment = Alignment(wrap_text=True, vertical="top")
    guide.column_dimensions["A"].width = 28
    guide.column_dimensions["B"].width = 100

    src = wb.create_sheet("口径与来源")
    src_rows = [
        ("口径与来源（DRAFT）", ""),
        ("", ""),
        ("输入 1", "48待定量_97_157_原型_2026-10-28_v2.csv（Q97/Q157、SS、IP、最晚下单日、10-29 到仓）"),
        ("输入 2", "53补单逐键分类_2026-10-28_v3.csv（近端兜底标记）"),
        ("输入 3", "46近端缺口_调拨候选_2026-10-28_v2.csv（建议调拨上限、调拨后仍缺、仓池外供给）"),
        ("输入 4", "order_store.duckdb item_attr / sku_item（商品名、发货角色；read_only）"),
        ("需求口径", "forecast-20261027-r4 → run-2026-10-26-r6 周桶；97 目标→w14（102 天）、157 目标→w22（158 天），不插值"),
        ("盲区", "run manifest forecast.gap_from_as_of_days=2.779：10/26→10/29 无需求数据、未估算"),
        ("IP", "10/28 同仓已证可发 + 已证未到货；未证在途/PO/SO 不抵扣"),
        ("SS", "政策情景 A 1.5×/95%、B 1.0×/90%、C 1.0×/85%；σ=近 90 天历史销量 std（波动代理），未校准"),
        ("调拨", "同国可调仅美东↔美中；波兰无第二仓；仓池外供给只披露、不抵扣"),
        ("未做", "未按近端逐桶重算；混合视界（Q97 + 旧35天净缺口）不是统一近端缺口"),
        ("边界", "只读；不写 EN/通途；不改生产包；不是采购单"),
    ]
    for i, (a, b) in enumerate(src_rows, start=1):
        src.cell(row=i, column=1, value=a).font = Font(bold=(i == 1), size=12 if i == 1 else 10)
        src.cell(row=i, column=2, value=b).alignment = Alignment(wrap_text=True, vertical="top")
    src.column_dimensions["A"].width = 16
    src.column_dimensions["B"].width = 110

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"rows={len(rows)} near={sum(1 for r in rows if '近端：新单赶不上' in r[1])} "
          f"transfer={sum(1 for r in rows if '可同国调拨' in r[1])} out={out}")


if __name__ == "__main__":
    main()
