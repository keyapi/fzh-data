"""WF CG 来源归类（worker E）— Wayfair 自发货订单的 SKU 来源仓归因。

口径（用户/YTQ）：
- 期间：2026-08-01 .. 2026-10-28（订单实际覆盖见汇总页；EN 到 10-26，GS 到 09-30）
- 只看 Wayfair 自发货（GS/EN 中 warehouse = WayfairCG-* 仓，account = WFCastleGateUS）
- 判断每个 SKU 的 CG 库存来自 美东-CENTRADE 还是 美中-FZH-DANEEY
- 例外：退货到美中（FZH-DANEEY-退货产品仓）后重发 —— 只标记候选，不代替 YTQ 判断

数据（全部本地只读，不写生产、不改主表）：
1. GS 月表   D:/Work/fzh-order-store/gs_orders.parquet（至 2026-09-30）
2. EN 订单   D:/Work/fzh-order-store/en-demand-v1/en_orders.parquet + en_order_lines.parquet
3. 通途库存  2026-08-07 合并结存 xlsx；2026-10-23 美东/美中结存 xlsx；DuckDB tongtool_stock（10-21）
4. Wayfair  Castlegate/Dropship AllInventoryExport 2026-10-23（CG 各仓在库）
5. 映射      DuckDB sku_item / sku_map / item_attr

关键限制（写入 Excel「口径与缺口说明」）：
- 通途「库存变动明细」API 只能查最近 7 天（updatedDateFrom），无法回查 8–9 月调拨单；
  CG 仓库存的来源只能靠“窗口出库路径 + 库存位置”推断，不是调拨凭证。
- 订单侧 CG 仓只出现 WayfairCG-Cranbury仓；McDonough/Perris/PortWentworth/Romeoville
  只出现在 Wayfair 自己的库存表里，不进入订单仓字段。
- 退货仓库存无快照；退货用「退货仓出库件数」作候选证据。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

WINDOW_START = "2026-08-01"
WINDOW_END = "2026-10-28"
PRIOR6_START = "2026-02-01"
PRIOR6_END = "2026-07-31"
RET_START = "2025-08-01"

CG_WAREHOUSE_PREFIX = "WayfairCG-"
FIVE_CG = {
    "NJ - Cranbury Small Parcel": "Cranbury",
    "GA - McDonough": "McDonough",
    "CA - Perris Small Parcel": "Perris",
    "GA - Port Wentworth (Savannah)": "PortWentworth",
    "IL - Romeoville": "Romeoville",
}


def pool_of(warehouse: str) -> str | None:
    """来源池映射：退货仓不算正常供给池（单独统计，用于例外标记）。"""
    w = str(warehouse)
    if "退货" in w:
        return None
    if w in ("CENTRADE", "美东-CENTRADE"):
        return "美东"
    if w.startswith("FZH-DANEEY") or w.startswith("美中"):
        return "美中"
    return None


def read_stock_export(path: str | Path) -> pd.DataFrame:
    """读通途库存结存清单：兼容「标题 2 行 + 表头」与「首行即表头」两种导出格式。"""
    raw = pd.read_excel(path, header=None)
    header_row = 0
    for i in range(min(6, len(raw))):
        if "SKU" in [str(c).strip() for c in raw.iloc[i].tolist()]:
            header_row = i
            break
    header = [str(c).strip() for c in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 1 :].copy()
    df.columns = header
    df = df[df["SKU"].notna()]
    df = df[~df["SKU"].astype(str).str.contains("总计", na=False)]
    for col in ("可用库存", "在途库存", "待发库存", "故障品库存"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    df["sku"] = df["SKU"].astype(str).str.strip().str.upper()
    df["pname"] = df.get("货品名称/规格")
    df["warehouse"] = df["仓库"].astype(str)
    return df


def load_orders(db_path: str, gs_path: str, en_dir: str) -> pd.DataFrame:
    """统一订单行：doc, sale_date, sku, qty, warehouse, src。EN 优先，GS 补 8/1–8/25。"""
    gs = pd.read_parquet(gs_path)
    gs["sku"] = gs["sku_tongtool"].astype(str).str.strip().str.upper()
    gs["sale_day"] = gs["sale_date"].astype(str).str[:10]
    gs_rows = gs[["order_id", "sku", "qty", "sale_day", "warehouse"]].rename(
        columns={"order_id": "doc", "qty": "units"}
    )
    gs_rows["src"] = "gs"

    o = pd.read_parquet(Path(en_dir) / "en_orders.parquet")
    lines = pd.read_parquet(Path(en_dir) / "en_order_lines.parquet")
    lines["sku"] = lines["tongtool_sku"].astype(str).str.strip().str.upper()
    en = lines.merge(
        o[["en_doc_name", "sale_date", "warehouse_name"]], on="en_doc_name", how="inner"
    )
    en["sale_day"] = en["sale_date"].astype(str).str[:10]
    en_rows = en[["en_doc_name", "sku", "quantity", "sale_day", "warehouse_name"]].rename(
        columns={"en_doc_name": "doc", "quantity": "units", "warehouse_name": "warehouse"}
    )
    en_rows["src"] = "en"

    # EN 覆盖到的单据整单用 EN，GS 只补 EN 没有的单据
    overlap = set(en_rows["doc"]) & set(gs_rows["doc"])
    gs_extra = gs_rows[~gs_rows["doc"].isin(overlap)]
    unified = pd.concat([en_rows, gs_extra], ignore_index=True)
    unified["units"] = pd.to_numeric(unified["units"], errors="coerce").fillna(0)
    unified["pool"] = unified["warehouse"].map(pool_of)
    return unified


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="D:/Work/fzh-order-store/order_store.duckdb")
    ap.add_argument("--gs", default="D:/Work/fzh-order-store/gs_orders.parquet")
    ap.add_argument("--en-dir", default="D:/Work/fzh-order-store/en-demand-v1")
    ap.add_argument("--aug-stock", default="D:/Work/赛狐/网页自动化/output/通途合并库存结存清单 20260807_1631.xlsx")
    ap.add_argument("--oct-dong", default="D:/Work/尹/wayfair/库存结存清单2026-10-2316_40_55.xlsx")
    ap.add_argument("--oct-zhong", default="D:/Work/尹/wayfair/库存结存清单2026-10-2316_55_33.xlsx")
    ap.add_argument("--wayfair", default="D:/Work/尹/wayfair/AllInventoryExport_2026-10-23 (1)(1).csv")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/wf-cg-source-map-2026-10-28.xlsx")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(args.db, read_only=True)
    sku_item = con.execute("select sku, item_code, ship_type from sku_item").df()
    sku_item["sku"] = sku_item["sku"].astype(str).str.strip().str.upper()
    item_attr = con.execute("select item, item_name from item_attr").df()

    # ---------- 订单 ----------
    orders = load_orders(args.db, args.gs, args.en_dir)
    cg_orders = orders[
        orders["warehouse"].astype(str).str.startswith(CG_WAREHOUSE_PREFIX)
        & (orders["sale_day"] >= WINDOW_START)
        & (orders["sale_day"] <= WINDOW_END)
    ].copy()
    cg_skus = sorted(cg_orders["sku"].unique())

    # 来源池出库（窗口 / 前 6 月 / 退货仓）
    pool_orders = orders[orders["pool"].notna()]
    win = pool_orders[(pool_orders["sale_day"] >= WINDOW_START) & (pool_orders["sale_day"] <= WINDOW_END)]
    prior6 = pool_orders[(pool_orders["sale_day"] >= PRIOR6_START) & (pool_orders["sale_day"] <= PRIOR6_END)]
    ret = orders[
        orders["warehouse"].astype(str).str.contains("退货", na=False)
        & (orders["sale_day"] >= RET_START)
    ]
    ret_win = ret[ret["sale_day"] >= WINDOW_START]

    def by_pool(df: pd.DataFrame) -> pd.DataFrame:
        return df.groupby(["sku", "pool"])["units"].sum().unstack("pool").fillna(0)

    win_p, prior_p = by_pool(win), by_pool(prior6)
    ret_q = ret.groupby("sku")["units"].sum()
    ret_win_q = ret_win.groupby("sku")["units"].sum()

    # ---------- 库存 ----------
    aug = read_stock_export(args.aug_stock)
    aug["pool"] = aug["warehouse"].map(pool_of)
    aug_p = (
        aug.dropna(subset=["pool"])
        .groupby(["sku", "pool"])[["可用库存", "在途库存"]]
        .sum()
        .assign(total=lambda d: d["可用库存"].fillna(0) + d["在途库存"].fillna(0))["total"]
        .unstack("pool")
        .fillna(0)
    )

    oct_dong = read_stock_export(args.oct_dong)
    oct_zhong = read_stock_export(args.oct_zhong)
    oct_parts = []
    for df, pool in ((oct_dong, "美东"), (oct_zhong, "美中")):
        d = df.copy()
        d["pool"] = pool
        d["total"] = d["可用库存"].fillna(0) + d["在途库存"].fillna(0)
        oct_parts.append(d[["sku", "pool", "total", "pname"]])
    oct_all = pd.concat(oct_parts)
    oct_p = oct_all.groupby(["sku", "pool"])["total"].sum().unstack("pool").fillna(0)
    name_map = (
        oct_all.dropna(subset=["pname"])
        .drop_duplicates("sku")
        .set_index("sku")["pname"]
    )

    # ---------- Wayfair CG 库存 ----------
    wf = pd.read_csv(args.wayfair, encoding="utf-8-sig")
    wf["part_no"] = wf["Part Number"].astype(str).str.strip()
    wf["sku"] = wf["part_no"].str.upper()
    # Wayfair 侧对部分皮壳仍用旧料号（OLD_ 前缀），归一后再匹配
    wf["nsku"] = wf["sku"].str.replace(r"^OLD_", "", regex=True)
    wf_cg = wf[(wf["Warehouse Type"] == "Castlegate") & (wf["In Stock"].fillna(0) > 0)]
    # Wayfair dropship 侧（NJ=美东 / TX=美中）作为独立旁证
    wf_drop = wf[wf["Warehouse Type"] == "Dropship"].copy()
    wf_drop["drop_pool"] = wf_drop["Warehouse Name"].map(
        lambda n: "美东" if "NJ" in str(n) else ("美中" if "TX" in str(n) else None)
    )

    # ---------- 逐 SKU ----------
    def val(frame: pd.DataFrame, sku: str, pool: str) -> float:
        try:
            return float(frame.loc[sku, pool])
        except KeyError:
            return 0.0

    rows = []
    for sku in cg_skus:
        g = cg_orders[cg_orders["sku"] == sku]
        win_d, win_z = val(win_p, sku, "美东"), val(win_p, sku, "美中")
        p6_d, p6_z = val(prior_p, sku, "美东"), val(prior_p, sku, "美中")
        aug_d, aug_z = val(aug_p, sku, "美东"), val(aug_p, sku, "美中")
        oct_d, oct_z = val(oct_p, sku, "美东"), val(oct_p, sku, "美中")
        rq, rqw = float(ret_q.get(sku, 0)), float(ret_win_q.get(sku, 0))

        # 噪声阈值：另一池 <3 件的历史出库视为个案，不据此降置信度/不单独标记
        noise_floor = 3
        p6_z_eff = p6_z if p6_z >= noise_floor else 0.0
        p6_d_eff = p6_d if p6_d >= noise_floor else 0.0

        # 归类
        if win_d > 0 and win_z == 0:
            source = "美东"
            confidence = "强" if (p6_z_eff == 0 and oct_z == 0) else "中"
        elif win_z > 0 and win_d == 0:
            source = "美中"
            confidence = "强" if (p6_d_eff == 0 and oct_d == 0) else "中"
        elif win_d > 0 and win_z > 0:
            if win_d >= 5 * win_z:
                source, confidence = "美东", "弱"
            elif win_z >= 5 * win_d:
                source, confidence = "美中", "弱"
            else:
                source, confidence = "无法判断", "—"
        else:  # 窗口无来源池出库
            if p6_d > 0 and p6_z == 0:
                source, confidence = "美东", "弱"
            elif p6_z > 0 and p6_d == 0:
                source, confidence = "美中", "弱"
            elif p6_d > 0 and p6_z > 0:
                source, confidence = "无法判断", "—"
            elif oct_d > 0 and oct_z == 0:
                source, confidence = "美东", "弱"
            elif oct_z > 0 and oct_d == 0:
                source, confidence = "美中", "弱"
            else:
                source, confidence = "无法判断", "—"

        # CG 仓（Wayfair 10-23）
        wfr = wf_cg[wf_cg["nsku"] == sku]
        cg_wh_short = "; ".join(
            f"{FIVE_CG.get(r['Warehouse Name'], r['Warehouse Name'])}={int(r['In Stock'])}"
            for _, r in wfr.iterrows()
        )
        if not cg_wh_short:
            cg_wh_short = "10-23 无在库（订单仓 " + "; ".join(
                sorted(g["warehouse"].astype(str).unique())
            ) + "）"
        outside_five = wfr[~wfr["Warehouse Name"].isin(FIVE_CG)]
        alias_parts = sorted({p for p in wfr["part_no"] if p.upper() != sku})

        # Wayfair dropship 旁证（NJ=美东 / TX=美中）
        wfd = wf_drop[wf_drop["nsku"] == sku]
        drop_nj = float(wfd[wfd["drop_pool"] == "美东"]["Available"].fillna(0).sum())
        drop_tx = float(wfd[wfd["drop_pool"] == "美中"]["Available"].fillna(0).sum())

        flags = []
        if rqw > 0 and source in ("美东", "美中"):
            label = "退货重发候选" if source == "美东" else "美中退货仓有出库"
            flags.append(f"{label}(窗口退货仓出库{int(rqw)}件)")
        elif rq >= 5:
            flags.append(f"退货仓历史出库{int(rq)}件(窗口内0)")
        if p6_d_eff > 0 and p6_z_eff > 0:
            flags.append(f"前6月两池均有出库(美东{int(p6_d)}/美中{int(p6_z)})")
        if win_d > 0 and win_z > 0:
            flags.append(f"窗口两池均有出库(美东{int(win_d)}/美中{int(win_z)})")
        if len(outside_five) > 0:
            flags.append("CG仓超出五项清单: " + "; ".join(sorted(outside_five["Warehouse Name"].unique())))
        if wfr.empty:
            flags.append("Wayfair 10-23 无 Castlegate 在库")
        if alias_parts:
            flags.append("Wayfair 用旧料号匹配: " + "; ".join(alias_parts))

        item_code = None
        m = sku_item[sku_item["sku"] == sku]
        if len(m):
            item_code = m.iloc[0]["item_code"]
        ship_type = m.iloc[0]["ship_type"] if len(m) else None
        product = name_map.get(sku)
        if not product and item_code:
            ia = item_attr[item_attr["item"] == item_code]
            if len(ia):
                product = ia.iloc[0]["item_name"]

        evidence = (
            f"窗口出库 美东{int(win_d)}/美中{int(win_z)}件；"
            f"前6月 美东{int(p6_d)}/美中{int(p6_z)}；"
            f"10-23库存(可用+在途) 美东{int(oct_d)}/美中{int(oct_z)}；"
            f"8-07库存(可用+在途) 美东{int(aug_d)}/美中{int(aug_z)}；"
            f"退货仓出库 {int(rq)}件(窗口{int(rqw)})；"
            f"WF dropship 可用 美东NJ{int(drop_nj)}/美中TX{int(drop_tx)}"
        )
        if source == "美东" and drop_tx > 0 and drop_nj == 0:
            flags.append(f"Wayfair dropship 仅 TX 有货{int(drop_tx)}件，与美东判断相反")
        elif source == "美中" and drop_nj > 0 and drop_tx == 0:
            flags.append(f"Wayfair dropship 仅 NJ 有货{int(drop_nj)}件，与美中判断相反")
        if drop_nj == 0 and drop_tx == 0:
            flags.append("仅通途侧证据(Wayfair dropship 无位置信息)")

        rows.append(
            {
                "SKU": sku,
                "产品名": product,
                "item_code": item_code,
                "发货形态": ship_type,
                "来源仓": source,
                "置信度": confidence,
                "CG仓(Wayfair 10-23 库存)": cg_wh_short,
                "订单记录仓": "; ".join(sorted(g["warehouse"].astype(str).unique())),
                "订单数": int(g["doc"].nunique()),
                "件数": int(g["units"].sum()),
                "首单日": g["sale_day"].min(),
                "末单日": g["sale_day"].max(),
                "例外标记": "; ".join(flags) if flags else "",
                "窗口出库_美东": int(win_d),
                "窗口出库_美中": int(win_z),
                "前6月出库_美东": int(p6_d),
                "前6月出库_美中": int(p6_z),
                "10-23库存_美东": int(oct_d),
                "10-23库存_美中": int(oct_z),
                "8-07库存_美东": int(aug_d),
                "8-07库存_美中": int(aug_z),
                "退货仓出库_累计": int(rq),
                "退货仓出库_窗口": int(rqw),
                "WF_dropship_NJ可用_美东": int(drop_nj),
                "WF_dropship_TX可用_美中": int(drop_tx),
                "证据": evidence,
            }
        )
    main_df = pd.DataFrame(rows).sort_values(["来源仓", "件数"], ascending=[True, False])

    # ---------- 明细 ----------
    detail = cg_orders[["doc", "sale_day", "sku", "units", "warehouse", "src"]].copy()
    detail["来源仓"] = detail["sku"].map(main_df.set_index("SKU")["来源仓"])
    detail = detail.sort_values(["sale_day", "doc"])

    # ---------- 汇总 ----------
    by_source = main_df.groupby("来源仓").agg(
        SKU数=("SKU", "nunique"), 订单数=("订单数", "sum"), 件数=("件数", "sum")
    ).reset_index()
    total_row = pd.DataFrame(
        [{"来源仓": "合计", "SKU数": main_df["SKU"].nunique(),
          "订单数": main_df["订单数"].sum(), "件数": main_df["件数"].sum()}]
    )
    by_source = pd.concat([by_source, total_row], ignore_index=True)

    NON_ACTIONABLE = "Wayfair 10-23 无 Castlegate 在库"
    is_actionable = main_df["例外标记"].apply(
        lambda s: any(f.strip() != NON_ACTIONABLE for f in str(s).split(";")) if s else False
    )
    excl = main_df[is_actionable][
        ["SKU", "产品名", "来源仓", "置信度", "订单数", "件数", "例外标记", "证据"]
    ]
    unknown = main_df[main_df["来源仓"] == "无法判断"][
        ["SKU", "产品名", "订单数", "件数", "例外标记", "证据"]
    ]

    gaps = pd.DataFrame(
        [
            ["订单覆盖", "EN 2026-08-26..2026-10-26；GS 2026-08-01..2026-09-30（CG 单实际到 09-18）",
             "10-27..10-28 无订单数据；EN 为 10 月 modified 窗口，跨月未更新单据可能缺失"],
            ["CG 仓字段", "订单侧只有 WayfairCG-Cranbury仓（GS/EN 一致）",
             "McDonough/Perris/PortWentworth/Romeoville 只在 Wayfair 库存表出现，订单字段无法区分"],
            ["CG 各仓库存", "Wayfair AllInventoryExport 2026-10-23 单快照（Castlegate 9 个仓）",
             "无历史快照；无法按 CG 仓做去程/时效分析"],
            ["调拨凭证", "通途「库存变动明细」API 仅最近 7 天（updatedDateFrom），无 8–9 月调拨单",
             "来源仓为“窗口出库路径 + 库存位置”推断，不是调拨单凭证"],
            ["退货仓", "无退货仓库存快照；用退货仓出库件数作候选证据",
             "无法确认某件 CG 货是否为退货重发，只能标 SKU 级候选"],
            ["来源判断口径", "窗口（8/1–10/26）内每个 SKU 只从一个来源池出库",
             "前 6 月两池都有出库的 SKU，按窗口口径归类并加标记"],
        ],
        columns=["项", "结论", "限制/缺口"],
    )

    coverage = pd.DataFrame(
        [
            ["订单来源-1", "GS 月表 gs_orders.parquet", "2026-08-01..2026-09-30（CG 单到 09-18）"],
            ["订单来源-2", "EN Tongtool Order（en-demand-v1）", "2026-08-26..2026-10-26"],
            ["合并规则", "同单据 EN 优先，GS 只补 EN 未覆盖的 8/1–8/25 单", f"{len(cg_orders)} 单 / {int(cg_orders['units'].sum())} 件"],
            ["库存-1", "通途合并库存结存 20260807（美东/美中+子仓）", "2026-08-07"],
            ["库存-2", "通途库存结存 2026-10-23 美东 / 美中（YTQ 导出）", "2026-10-23"],
            ["库存-3", "DuckDB tongtool_stock", "2026-10-21"],
            ["CG 库存", "Wayfair AllInventoryExport 2026-10-23（Castlegate/Dropship）", "2026-10-23 单快照"],
        ],
        columns=["数据", "文件/来源", "覆盖"],
    )

    wh_presence = (
        wf_cg[wf_cg["sku"].isin(cg_skus)]
        .groupby("Warehouse Name")
        .agg(SKU数=("sku", "nunique"), 在库件数=("In Stock", "sum"))
        .reset_index()
        .sort_values("在库件数", ascending=False)
    )

    # 交叉验证：Wayfair dropship NJ/TX 的库存位置 vs 通途窗口出库路径
    def _drop_pool(row):
        nj, tx = row["WF_dropship_NJ可用_美东"], row["WF_dropship_TX可用_美中"]
        if nj > 0 and tx == 0:
            return "美东"
        if tx > 0 and nj == 0:
            return "美中"
        return None

    cross = main_df.apply(_drop_pool, axis=1)
    cross_df = pd.DataFrame(
        [
            ["Wayfair dropship 有位置信息", int(cross.notna().sum()), len(main_df)],
            ["与通途窗口出库路径一致", int((cross == main_df["来源仓"]).sum()), int(cross.notna().sum())],
            ["不一致", int(((cross.notna()) & (cross != main_df["来源仓"])).sum()), int(cross.notna().sum())],
            ["无 dropship 位置信息", int(cross.isna().sum()), len(main_df)],
        ],
        columns=["交叉验证项", "SKU数", "分母"],
    )

    method = pd.DataFrame(
        [
            ["期间", f"{WINDOW_START} .. {WINDOW_END}"],
            ["订单来源", "GS 月表 + EN Tongtool Order（EN 单据优先，GS 只补 EN 未覆盖的 8/1–8/25 单）"],
            ["CG 订单口径", "warehouse 以 WayfairCG- 开头；渠道 WFCastleGateUS（Wayfair 自发货）"],
            ["来源仓判定", "窗口内该 SKU 在美东/美中池的出库件数（不含 CG/波兰/退货仓）"],
            ["置信度-强", "窗口单侧出库>0、另一侧=0，且前6月与 10-23 库存均不反证"],
            ["置信度-中", "窗口单侧出库>0，但前6月或库存显示另一池也有"],
            ["置信度-弱", "窗口无来源池出库，仅靠前6月或当前库存单侧推断；或比例 ≥5:1 倾斜"],
            ["例外口径", "退货到美中后重发：只标 SKU 级候选（美中退货仓出库件数），不扣减件数"],
            ["不做什么", "不合并主表、不改订单/库存、不下结论代替 YTQ 确认"],
        ],
        columns=["项", "口径"],
    )

    conf = (
        main_df.groupby(["来源仓", "置信度"])
        .agg(SKU数=("SKU", "nunique"), 件数=("件数", "sum"))
        .reset_index()
        .sort_values(["来源仓", "置信度"])
    )

    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        row = 0
        by_source.to_excel(xw, sheet_name="汇总", index=False, startrow=row)
        row += len(by_source) + 2
        conf.to_excel(xw, sheet_name="汇总", index=False, startrow=row)
        row += len(conf) + 2
        cross_df.to_excel(xw, sheet_name="汇总", index=False, startrow=row)
        row += len(cross_df) + 2
        wh_presence.to_excel(xw, sheet_name="汇总", index=False, startrow=row)
        row += len(wh_presence) + 2
        coverage.to_excel(xw, sheet_name="汇总", index=False, startrow=row)
        row += len(coverage) + 2
        method.to_excel(xw, sheet_name="汇总", index=False, startrow=row)
        main_df.to_excel(xw, sheet_name="来源归类", index=False)
        excl.to_excel(xw, sheet_name="例外清单", index=False)
        unknown.to_excel(xw, sheet_name="无法判断", index=False)
        gaps.to_excel(xw, sheet_name="口径与缺口说明", index=False)
        detail.to_excel(xw, sheet_name="订单明细", index=False)

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "window": [WINDOW_START, WINDOW_END],
        "output": str(out_path),
        "orders": {"docs": int(cg_orders["doc"].nunique()), "units": int(cg_orders["units"].sum()),
                   "skus": int(len(cg_skus)), "first": str(cg_orders["sale_day"].min()),
                   "last": str(cg_orders["sale_day"].max())},
        "by_source": by_source.to_dict(orient="records"),
        "cross_check_dropship": cross_df.to_dict(orient="records"),
        "exceptions": int(len(excl)),
        "unknown": int(len(unknown)),
        "unknown_units": int(unknown["件数"].sum()) if len(unknown) else 0,
    }
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
