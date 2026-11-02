"""46/47 行近端缺口的调拨/加急候选表（只读）。

规则（用户 2026-10-28）
1. 只处理「近端兜底 = 调拨/加急/接受缺货（待定）」的行；
2. 同国可调：美东 ↔ 美中；波兰 ↔ 美国不可互调；
3. 源仓可用量只分配一次（按 (源仓, SKU) 扣减，本批无同 SKU 多目的仓）；
4. 每行给：目的仓 / Q97 / 当前可发 / 源仓 / 源仓可用 / 建议调拨上限 / 调拨后仍缺 / 是否同国 / 需业务确认项；
5. 开放 PO / 在途只作「潜在改配」另列，不计入现在可用；
6. 不编造运费、时效、到货日；
7. 无来源 → 「无可调，需加急/接受缺货」。

输入只读：原型 v2、53 v3、en_stock(10-28)、po_receipt_status、sku_item（DuckDB read_only）。
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

US_WAREHOUSES = ["美东-CENTRADE", "美中-FZH-DANEEY"]
PL_WAREHOUSES = ["波兰-FZHPoland-covers"]
SNAPSHOT = "2026-10-28"
NEAR_FLAG = "调拨/加急/接受缺货（待定）"


def clean_sku(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper().removeprefix("删除")
    return text or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", default="D:/Work/fzh-order-store/analysis/48待定量_97_157_原型_2026-10-28_v2.csv")
    ap.add_argument("--classify", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28_v3.csv")
    ap.add_argument("--stock", default="D:/Work/fzh-order-store/en_stock.parquet")
    ap.add_argument("--po", default="D:/Work/fzh-order-store/tongtool_po/po_receipt_status_2026-08_10.csv")
    ap.add_argument("--db", default="D:/Work/fzh-order-store/order_store.duckdb")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/46近端缺口_调拨候选_2026-10-28.csv")
    args = ap.parse_args()

    proto = pd.read_csv(args.proto, encoding="utf-8-sig")
    classify = pd.read_csv(args.classify, encoding="utf-8-sig")

    # 1) 近端行 = 53 v3 中带兜底标记的行；与原型交集 47 行，另 1 行「救急」不在原型
    near = classify[classify["近端兜底"].astype(str) == NEAR_FLAG][
        ["SKU", "仓库", "分类", "首次缺口周", "旧35天参考量", "当前可发(10-28同仓)", "近端兜底"]
    ].copy()
    merged = near.merge(
        proto[["SKU", "仓库", "Q_97目标", "需求_97目标_102天", "IP_已证", "Q<1_97"]],
        on=["SKU", "仓库"], how="left",
    )

    # 2) SKU 映射：EN 物料码 → 通途 SKU（sku_item，TT→item 一对一）
    con = duckdb.connect(args.db, read_only=True)
    pairs = con.execute("select upper(sku) sku, upper(item_code) item from sku_item").df()
    tt_by_item: dict[str, set[str]] = {}
    for _, row in pairs.iterrows():
        tt_by_item.setdefault(row["item"], set()).add(row["sku"])

    # 3) 10-28 各仓可用 / 在途
    stock = pd.read_parquet(args.stock)
    stock = stock[stock["snapshot_date"].astype(str) == SNAPSHOT].copy()
    stock["sku"] = stock["sku"].astype(str).str.upper()
    avail = stock.groupby(["warehouse_name", "sku"])["available"].sum()
    intransit = stock.groupby(["warehouse_name", "sku"])["intransit"].sum()

    # 4) 开放 PO（open>0）按仓×SKU
    po = pd.read_csv(args.po, encoding="utf-8-sig")
    po["sku"] = po["goods_sku"].map(clean_sku)
    po["open_qty"] = pd.to_numeric(po.get("open"), errors="coerce").fillna(0)
    open_po = po[po["open_qty"] > 0].groupby(["warehouseName", "sku"])["open_qty"].sum()

    def qty_at(frame, warehouse: str, item: str) -> float:
        total = 0.0
        for tt in tt_by_item.get(item, set()):
            total += float(frame.get((warehouse, tt), 0.0))
        return total

    consumed: dict[tuple[str, str], float] = {}
    rows = []

    for _, row in merged.iterrows():
        sku, dest = row["SKU"], row["仓库"]
        is_pl = dest in PL_WAREHOUSES
        sources = [w for w in (PL_WAREHOUSES if is_pl else US_WAREHOUSES) if w != dest]

        q97 = row.get("Q_97目标")
        current = float(row["当前可发(10-28同仓)"] or 0)
        if pd.notna(q97):
            gap = max(0.0, float(q97) - current)
            gap_basis = "Q97（102 天桶界）− 当前可发"
        else:
            # 救急行不在原型：用 53 分类的旧 35 天参考缺口，显式标注
            gap = max(0.0, float(row["旧35天参考量"] or 0) - current)
            gap_basis = "旧35天参考量 − 当前可发（该行不在 48 原型，无 Q97）"

        source_name, source_avail, same_country = "", 0.0, "否"
        transferable = 0.0
        remaining = gap
        potential_po = ""
        potential_transit = ""

        for src in sources:
            key = (src, sku)
            left = qty_at(avail, src, sku) - consumed.get(key, 0.0)
            left = max(0.0, left)
            po_left = qty_at(open_po, src, sku) if len(open_po) else 0.0
            transit_left = qty_at(intransit, src, sku)
            if left > 0 or po_left > 0 or transit_left > 0:
                source_name = src
                source_avail = left
                same_country = "是"
                transferable = min(left, gap)
                consumed[key] = consumed.get(key, 0.0) + transferable
                remaining = max(0.0, gap - transferable)
                potential_po = f"{src} 开放 PO {po_left:g}" if po_left > 0 else ""
                potential_transit = f"{src} 在途 {transit_left:g}" if transit_left > 0 else ""
                break

        if source_name and transferable > 0:
            action = "可同国调拨（上限见左），剩余缺口另议"
            confirm = "调拨运费/时效未评估；源仓库存是否可动需仓库确认；跨分公司调拨需审批"
        elif is_pl:
            action = "无可调，需加急/接受缺货"
            confirm = "波兰无第二仓可调；美国仓不可跨洲调拨；是否加急/接受缺货需业务决定"
        else:
            action = "无可调，需加急/接受缺货"
            confirm = "同国源仓该 SKU 10-28 无可用；是否加急/接受缺货需业务决定"
        if remaining > 0 and transferable > 0:
            confirm += "；调拨后仍有缺口，剩余需加急或接受缺货"

        rows.append({
            "SKU": sku,
            "目的仓": dest,
            "分类": row["分类"],
            "数据来源": "48 原型（待定量）" if pd.notna(q97) else "53 分类（救急，无 Q97）",
            "首次缺口周": row["首次缺口周"],
            "Q97总需求": None if pd.isna(q97) else round(float(q97), 3),
            "缺口口径": gap_basis,
            "当前可发_10-28同仓": current,
            "近端缺口量": round(gap, 3),
            "源仓": source_name,
            "源仓可用_10-28": round(source_avail, 3),
            "建议调拨上限": round(transferable, 3),
            "调拨后仍缺": round(remaining, 3),
            "是否同国": same_country,
            "潜在改配_开放PO": potential_po,
            "潜在改配_在途": potential_transit,
            "潜在改配说明": "开放 PO/在途只作改配线索，未计入当前可用；改配需审批",
            "建议动作": action,
            "需业务确认项": confirm,
        })

    out = pd.DataFrame(rows).sort_values(["目的仓", "近端缺口量"], ascending=[True, False])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")

    same_country_rows = int((out["是否同国"] == "是").sum())
    transfer_rows = int((out["建议调拨上限"] > 0).sum())
    no_source_rows = int((out["建议调拨上限"] <= 0).sum())
    pl_rows = int((out["目的仓"].isin(PL_WAREHOUSES)).sum())
    pl_no_transfer = int(((out["目的仓"].isin(PL_WAREHOUSES)) & (out["建议调拨上限"] <= 0)).sum())
    print(f"rows={len(out)}")
    print(f"有同国可调行={transfer_rows} 总可调上限={out['建议调拨上限'].sum():.3f}")
    print(f"无可调行={no_source_rows}（其中波兰 {pl_no_transfer}；美国同国无货源 {no_source_rows - pl_no_transfer}）")
    print(f"波兰行数={pl_rows}（全部不可与美国互调）")
    print(f"总缺口={out['近端缺口量'].sum():.3f} 调拨后仍缺合计={out['调拨后仍缺'].sum():.3f}")
    print(f"output={args.out}")


if __name__ == "__main__":
    main()
