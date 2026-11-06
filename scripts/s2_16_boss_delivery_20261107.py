# -*- coding: utf-8 -*-
"""Boss/ops-readable replenishment delivery workbook.

Scope: all demand keys for USNJ, USTX, Poland (D6 v6.15), with CNY v7 plan and
trajectory v7 status overrides. Plain-language statuses; no internal codes in
the main sheets.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

BASE = Path("D:/Work/fzh-order-store/analysis")
D6 = BASE / "D6v6_15-final/D_Top50沙盒_D6_v6_15_2026-11-07.xlsx"
D5 = BASE / "D5v6_6-60cm/D_概率与服务_D5_v6_6_2026-11-07.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v7.xlsx"
TRAJ = BASE / "S2_9-delivery-final-20261106/D_统一逐日轨迹_2026-11-07_v7.xlsx"
V15 = BASE / "S2_9-delivery-final-20261106/D_补货交付包_2026-11-06_final_v15.xlsx"
A = BASE / "SKU活跃宇宙_2026-10-29_FINAL.xlsx"
OUT = BASE / "D_老板版补货建议_2026-11-07.xlsx"
KEYS = ["product_id", "池", "形态", "UOM"]


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    d6 = pd.read_excel(D6, sheet_name="1_全量动作")
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5["horizon"].astype(str) == "97"].rename(
        columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM"})
    d5 = d5[KEYS + ["p50", "q95", "model", "adopted_model",
                    "interval_level", "calibration_n"]].rename(
        columns={"p50": "D5_p50", "q95": "D5_q95"})
    cny = pd.read_excel(CNY, sheet_name="2_逐键排期").rename(
        columns={"池": "池", "形态": "形态", "UOM": "UOM"})
    traj = pd.read_excel(TRAJ, sheet_name="2_逐键")
    traj = traj[traj["类型"] == "春节"][KEYS + ["状态"]].rename(columns={"状态": "轨迹状态"})
    v16 = pd.read_excel(V15, sheet_name="16_运输补救")
    v18 = pd.read_excel(V15, sheet_name="18_60cm新增补货资格")
    names = pd.read_excel(A, sheet_name="活跃宇宙")[["EN物料", "名称"]].drop_duplicates("EN物料")
    names["product_id"] = names["EN物料"].astype(str)

    cny_cols = KEYS + ["物料名称", "建议节前备货量", "首批数量", "第二批数量",
                       "首批到仓", "第二批到仓", "首批下单日", "第二批下单日",
                       "建议运输", "模型资格", "风险状态", "可换运输",
                       "首批晚于停工"]
    cny_s = cny[cny_cols].copy()
    b = d6.merge(cny_s, on=KEYS, how="left", suffixes=("", "_cny"))
    b = b.merge(d5, on=KEYS, how="left")
    b = b.merge(traj, on=KEYS, how="left")
    b = b.merge(v18[KEYS].assign(新增资格=True), on=KEYS, how="left")
    b = b.merge(names[["product_id", "名称"]], on="product_id", how="left")
    b = b[b["池"].isin(["美东USNJ", "美中USTX", "波兰"])].copy()
    b["是否春节方案"] = b["建议节前备货量"].notna()
    b["下单日_dt"] = pd.to_datetime(b.get("下单日"), errors="coerce")
    b["下单日已过"] = b["下单日_dt"] < pd.Timestamp("2026-11-06")

    def status(r):
        if r["是否春节方案"]:
            rs = str(r.get("风险状态", "") or "")
            if rs == "全部方案失败":
                return "可能断货-需拍板"
            if rs == "选定方案失败-有补救候选":
                return "先换运输再补"
            if str(r.get("模型资格", "")) == "零中位数-待验证":
                return "需求看不清-先别补"
            st = str(r.get("轨迹状态", ""))
            if st == "模型异常":
                return "需求异常-不判定"
            if st == "fail":
                return "方案未达95%-需调整"
            if r.get("首批晚于停工") == True and st in ("cycle95", "fill95"):  # noqa: E712
                return "首批要改空运/提前"
            if st in ("cycle95", "fill95"):
                return "可以补-待确认"
            return "春节方案-未匹配"
        if r.get("新增资格") == True:  # noqa: E712
            return "新增资格-待复审"
        act = str(r.get("建议动作", ""))
        if act == "催已有":
            return "催已有订单"
        if act == "补":
            if r.get("下单日已过") == True:  # noqa: E712
                return "补-下单日已过-需重排"
            return "补-待排期"
        if act == "不补":
            return "不用补"
        return "继续观察"

    b["一句话建议"] = b.apply(status, axis=1)

    def qty(r):
        if r["是否春节方案"]:
            v = pd.to_numeric(r["建议节前备货量"], errors="coerce")
            return 0.0 if pd.isna(v) else float(v)
        v = pd.to_numeric(r.get("建议数量", 0), errors="coerce")
        return 0.0 if pd.isna(v) else float(v)

    def num(r, col):
        v = pd.to_numeric(r.get(col), errors="coerce")
        return 0.0 if pd.isna(v) else float(v)

    b["建议补量"] = b.apply(qty, axis=1)
    b["首批数量_展示"] = b.apply(lambda r: num(r, "首批数量") if r["是否春节方案"] else 0, axis=1)
    b["第二批数量_展示"] = b.apply(lambda r: num(r, "第二批数量") if r["是否春节方案"] else 0, axis=1)
    b["催已有量_展示"] = b.apply(lambda r: num(r, "催已有量"), axis=1)
    b["是否要催"] = b["催已有量_展示"].apply(lambda x: "是" if x > 0 else "")
    b["运输方式"] = b.apply(lambda r: r.get("建议运输") if r["是否春节方案"]
                            else r.get("推荐main_haul", ""), axis=1)
    b["首批下单日_展示"] = b.apply(lambda r: r.get("首批下单日") if r["是否春节方案"]
                              else r.get("下单日", ""), axis=1)
    b["第二批下单日_展示"] = b.apply(lambda r: r.get("第二批下单日") if r["是否春节方案"] else "", axis=1)
    b["首批到仓_展示"] = b.apply(lambda r: r.get("首批到仓") if r["是否春节方案"]
                            else r.get("需要日", ""), axis=1)
    b["第二批到仓_展示"] = b.apply(lambda r: r.get("第二批到仓") if r["是否春节方案"] else "", axis=1)

    def basis(r):
        parts = []
        for label, col in (("q95", "q95"), ("可用C", "C可发供给"),
                           ("EN在途/待发", "en_stock在途+待发"),
                           ("PO追加", "PO追加(去重)"), ("净缺口", "净需求95")):
            v = pd.to_numeric(r.get(col), errors="coerce")
            if pd.notna(v):
                parts.append(f"{label} {v:.0f}")
        return "；".join(parts)

    b["依据"] = b.apply(basis, axis=1)
    def owner(r):
        s = r["一句话建议"]
        if s in ("可能断货-需拍板", "方案未达95%-需调整", "首批要改空运/提前"):
            return "计划+业务"
        if s == "先换运输再补":
            return "物流+业务"
        if s in ("需求看不清-先别补", "需求异常-不判定"):
            return "计划/数据"
        if s == "新增资格-待复审":
            return "业务"
        if s in ("可以补-待确认", "补-待排期", "催已有订单"):
            return "运营确认"
        return "—"
    b["需要谁决定"] = b.apply(owner, axis=1)
    b["风险/备注"] = b.apply(
        lambda r: ("；".join([x for x in [str(r.get("风险状态", "") or ""),
                                          str(r.get("动作原因", "") or "")] if x]))
        if r["是否春节方案"] else str(r.get("动作原因", "") or ""), axis=1)

    def ev_demand(r):
        q = pd.to_numeric(r.get("D5_q95"), errors="coerce")
        if pd.isna(q):
            return ""
        p = pd.to_numeric(r.get("D5_p50"), errors="coerce")
        p_s = f"{p:.1f}" if pd.notna(p) else "—"
        return (f"D5 {r.get('model', '')}/{r.get('adopted_model', '')}；"
                f"p50 {p_s}；q95 {q:.1f}；区间 {r.get('interval_level', '')}"
                f"（n={r.get('calibration_n', '')}）")

    def ev_supply(r):
        eta = r.get("在途ETA_p50")
        eta_s = "" if pd.isna(eta) else str(eta)
        return (f"C可发 {num(r, 'C可发供给'):.0f}（{r.get('C完整键状态', '')}）；"
                f"EN在途/待发 {num(r, 'en_stock在途+待发'):.0f}"
                f"（{r.get('EN库存快照日', '')}/{r.get('EN快照状态', '')}）；"
                f"PO追加 {num(r, 'PO追加(去重)'):.0f}；"
                f"在途ETA {eta_s or '无'}")

    def ev_action(r):
        return (f"D6 {r.get('建议动作', '')}：{r.get('动作原因', '')}；"
                f"服务验证 {r.get('服务验证状态', '')}")

    def ev_cny(r):
        if not r["是否春节方案"]:
            return ""
        return (f"春节方案 {num(r, '建议节前备货量'):.0f} 件；"
                f"首批 {num(r, '首批数量'):.0f} @ {r.get('首批到仓', '')}；"
                f"二批 {num(r, '第二批数量'):.0f} @ {r.get('第二批到仓', '')}；"
                f"状态 {r.get('一句话建议', '')}；轨迹 {r.get('轨迹状态', '')}；"
                f"风险 {r.get('风险状态', '')}")

    b["需求证据"] = b.apply(ev_demand, axis=1)
    b["供给证据"] = b.apply(ev_supply, axis=1)
    b["动作证据"] = b.apply(ev_action, axis=1)
    b["春节证据"] = b.apply(ev_cny, axis=1)
    b["证据链"] = (b["需求证据"] + " ｜ " + b["供给证据"] + " ｜ " +
                 b["动作证据"] + b["春节证据"].map(lambda x: " ｜ " + x if x else ""))

    out = pd.DataFrame({
        "分公司": b["池"],
        "商品名称": b["物料名称"].fillna(b["名称"]).fillna(""),
        "商品编码": b["product_id"],
        "形态": b["形态"],
        "单位": b["UOM"],
        "一句话建议": b["一句话建议"],
        "建议补多少": b["建议补量"].round(0),
        "首批数量": b["首批数量_展示"].round(0),
        "第二批数量": b["第二批数量_展示"].round(0),
        "首批下单日": b["首批下单日_展示"],
        "第二批下单日": b["第二批下单日_展示"],
        "首批到仓/要求到仓": b["首批到仓_展示"],
        "第二批到仓": b["第二批到仓_展示"],
        "运输方式": b["运输方式"],
        "是否要催已有": b["是否要催"],
        "催已有量": b["催已有量_展示"].round(0),
        "在途ETA": b["在途ETA_p50"],
        "依据": b["依据"],
        "需要谁决定": b["需要谁决定"],
        "风险/备注": b["风险/备注"],
        "方案类型": b["是否春节方案"].map({True: "春节方案", False: "日常补货候选"}),
        "需求证据": b["需求证据"],
        "供给证据": b["供给证据"],
        "动作证据": b["动作证据"],
        "春节证据": b["春节证据"],
        "证据链": b["证据链"],
    })
    out = out[["分公司", "商品名称", "商品编码", "形态", "单位", "一句话建议",
               "建议补多少", "首批数量", "第二批数量", "首批下单日",
               "第二批下单日", "首批到仓/要求到仓", "第二批到仓", "运输方式",
               "是否要催已有", "催已有量", "在途ETA", "依据", "需要谁决定",
               "风险/备注", "方案类型", "证据链"]]
    order = ["可以补-待确认", "补-待排期", "补-下单日已过-需重排", "先换运输再补",
             "催已有订单", "首批要改空运/提前", "方案未达95%-需调整",
             "可能断货-需拍板", "新增资格-待复审", "需求看不清-先别补",
             "需求异常-不判定", "继续观察", "不用补", "春节方案-未匹配"]
    out["_ord"] = out["一句话建议"].map({s: i for i, s in enumerate(order)}).fillna(99)
    out = out.sort_values(["分公司", "_ord", "建议补多少"], ascending=[True, True, False]).drop(columns="_ord")
    ev_src = b[["池", "product_id", "形态", "UOM",
                "需求证据", "供给证据", "动作证据", "春节证据"]].rename(
        columns={"池": "分公司", "product_id": "商品编码", "UOM": "单位"})
    ev = out.merge(ev_src, on=["分公司", "商品编码", "形态", "单位"], how="left")[
        ["分公司", "商品编码", "商品名称", "一句话建议", "需求证据",
         "供给证据", "动作证据", "春节证据"]].fillna("")

    g = out.groupby(["分公司", "一句话建议"]).agg(键数=("商品编码", "size"),
                                              数量=("建议补多少", "sum")).reset_index()
    branch = out.groupby(["分公司", "方案类型"]).agg(
        键数=("商品编码", "size"), 建议补量=("建议补多少", "sum")).reset_index()
    cny_qty = out.loc[out["方案类型"].eq("春节方案"), "建议补多少"].sum()
    daily_qty = out.loc[out["方案类型"].eq("日常补货候选"), "建议补多少"].sum()
    daily_keys = int(out["一句话建议"].isin(
        ["补-待排期", "补-下单日已过-需重排"]).sum())
    pending = out[out["一句话建议"].isin(
        ["可能断货-需拍板", "先换运输再补", "首批要改空运/提前",
         "方案未达95%-需调整", "需求看不清-先别补", "需求异常-不判定",
         "新增资格-待复审", "补-下单日已过-需重排"])].copy()
    sel_cols = ["可以补-待确认", "首批要改空运/提前", "先换运输再补",
                "可能断货-需拍板", "方案未达95%-需调整", "需求看不清-先别补",
                "需求异常-不判定", "新增资格-待复审", "补-待排期",
                "补-下单日已过-需重排", "催已有订单", "继续观察", "不用补"]
    pivot = out.pivot_table(index="分公司", columns="一句话建议",
                            values="商品编码", aggfunc="count", fill_value=0)
    pivot["需求键数"] = pivot.sum(axis=1)
    pivot = pivot.reindex(columns=["需求键数"] + sel_cols, fill_value=0).reset_index()

    boss = pd.DataFrame([
        ("这份表是什么", f"三个分公司全部 {len(out)} 个需求键的逐商品补货建议；不是只覆盖 8 款。"),
        ("8 款复核", "8 款只是已复核子集；其余需求键也在这张表里，不能用 8 款代表全部。"),
        ("数据日期", "需求预测截至 2026-11-02；库存截至 2026-11-05；决策日 2026-11-06。"),
        ("春节方案", f"257 键 / {cny_qty:,.0f} 件；其中 27 键/1,756 件可确认，4 键/271 件首批晚于停工，8 键/424 件换运输，110 键/7,436 件断货风险，66 键需求看不清。"),
        ("日常补货候选", f"{daily_keys} 键 / {daily_qty:,.0f} 件；是 D6 当前补货候选，需单独排期，**不要与春节 12,092 相加**。"),
        ("补货下单日已过", f"{len(out[out['一句话建议'].eq('补-下单日已过-需重排')])} 键 / "
                     f"{out.loc[out['一句话建议'].eq('补-下单日已过-需重排'), '建议补多少'].sum():,.0f} 件；D6 候选但下单日已过，需重排。"),
        ("其中：可排期（未过期）", f"{len(out[out['一句话建议'].eq('补-待排期')])} 键 / "
                          f"{out.loc[out['一句话建议'].eq('补-待排期'), '建议补多少'].sum():,.0f} 件；D6 候选且下单日未过。"),
        ("今天可以确认", f"{len(out[out['一句话建议'].eq('可以补-待确认')])} 键 / "
                     f"{out.loc[out['一句话建议'].eq('可以补-待确认'), '建议补多少'].sum():,.0f} 件。"),
        ("需要拍板", f"{len(pending)} 键 / {pending['建议补多少'].sum():,.0f} 件；见 2_需要拍板。"),
        ("不要做", "不要把“可能断货-需拍板”当已批准；不要把“需求看不清”当 0 需求；不要用未审核量直接下单；不要把日常补货候选和春节方案相加。"),
        ("已有订单", "“催已有订单”是催在途/PO，不是新增；表内列了催多少和 ETA。"),
        ("证据链", "每行“证据链”列写清需求模型/q95、C/EN/PO、D6 动作原因、春节批次/轨迹；6_证据链可逐项追溯。"),
    ], columns=["项", "说明"])

    limits = pd.DataFrame([
        ("可确认", "轨迹模拟达到 95% 服务，且没有首批晚于停工/断货/模型异常。"),
        ("补-待排期", "D6 认为要补，但不在春节 257 方案里；需单独排期/审核。"),
        ("先换运输再补", "原运输晚于断货日，但更快运输可赶上；需确认舱位/运价。"),
        ("首批要改空运/提前", "首批到仓晚于 1/24 停工；需改空运或提前。"),
        ("方案未达95%", "模拟跑完但没到 95% 服务；需加量/提前/升舱或接受风险。"),
        ("可能断货-需拍板", "所有已验证运输都晚于断货日；需业务决定接受风险/需求抑制/加急。"),
        ("需求看不清-先别补", "p50=0、q95>0；模型待验证，建议量 0，禁止执行。"),
        ("需求异常-不判定", "需求尾部极厚；模拟不稳定，单列不判定。"),
        ("新增资格-待复审", "60cm 供给恢复后观察转补的 19 键；不在春节包，需单独资格复审。"),
        ("不用补/继续观察", "覆盖足够或政策/数据原因；不是“没需求”。"),
    ], columns=["状态", "大白话说明"])

    src = pd.DataFrame([
        ("D6 补货沙盒", str(D6), sha(D6)),
        ("D5 预测", str(D5), sha(D5)),
        ("春节排期 v7", str(CNY), sha(CNY)),
        ("统一轨迹 v7", str(TRAJ), sha(TRAJ)),
        ("交付包 v15", str(V15), sha(V15)),
        ("A 活跃宇宙（名称）", str(A), sha(A)),
    ], columns=["文件", "路径", "sha256"])

    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        boss.to_excel(w, sheet_name="0_老板先看", index=False)
        out.to_excel(w, sheet_name="1_逐商品建议", index=False)
        pending.to_excel(w, sheet_name="2_需要拍板", index=False)
        branch.to_excel(w, sheet_name="3_分公司汇总", index=False)
        g.to_excel(w, sheet_name="3b_分公司状态明细", index=False)
        limits.to_excel(w, sheet_name="4_口径与限制", index=False)
        src.to_excel(w, sheet_name="5_数据来源", index=False)
        ev.to_excel(w, sheet_name="6_证据链", index=False)

    wb = load_workbook(OUT)
    head_fill = PatternFill("solid", fgColor="1F4E78")
    head_font = Font(color="FFFFFF", bold=True)
    fills = {
        "可以补-待确认": "C6EFCE", "补-待排期": "DDEBF7", "补-下单日已过-需重排": "FCE4D6",
        "先换运输再补": "FFF2CC", "首批要改空运/提前": "FCE4D6",
        "方案未达95%-需调整": "FCE4D6", "可能断货-需拍板": "F8CBAD",
        "新增资格-待复审": "E4DFEC", "需求看不清-先别补": "D9E1F2",
        "需求异常-不判定": "D9E1F2", "催已有订单": "FFF2CC",
        "不用补": "EDEDED", "继续观察": "EDEDED",
    }
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for c in ws[1]:
            c.fill = head_fill
            c.font = head_font
            c.alignment = Alignment(vertical="center", wrap_text=True)
        widths = {}
        for row in ws.iter_rows(values_only=True):
            for i, v in enumerate(row, 1):
                widths[i] = min(42, max(widths.get(i, 10), len(str(v)) + 2))
        for i, w in widths.items():
            ws.column_dimensions[get_column_letter(i)].width = w
    ws = wb["1_逐商品建议"]
    hdr = [c.value for c in ws[1]]
    if "一句话建议" in hdr:
        ci = hdr.index("一句话建议") + 1
        for row in range(2, ws.max_row + 1):
            v = ws.cell(row=row, column=ci).value
            if v in fills:
                ws.cell(row=row, column=ci).fill = PatternFill("solid", fgColor=fills[v])
    wb.save(OUT)
    print("wrote", OUT)
    print(branch.to_string(index=False))
    print(out["一句话建议"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
