"""近端缺口的调拨/加急候选 v2（只读，口径修正）。

v2 修正（对应 near-term-rescue-review-2026-10-28 的 F1–F3）：
- F1 不再重复扣库存：原型 Q97 = max(0, 需求+SS−IP)，IP 已含 10/28 当前可发；
  救急行的「旧35天参考量」也已扣过 opening。**本表直接用已净额量作为对应视界的参考缺口**，
  不再减当前可发。CMKTR-140 保留 Q97=124.269；CMPR-194 旧参考 4、调 2 后仍缺 2。
- F2 拆两列：`长窗补量参考Q97_已净额`（47 行，长窗、已净额、非救急量）与
  `旧35天净缺口_仅救急行`（1 行，对照用）；不把两者相加成「近端总量」，
  只在报告给「混合视界参考合计」并注明不是统一近端口径。
- F3 跨洲排除供给必须披露：同国来源只在允许仓池内筛；仓池外的 PO/在途另列
  `跨洲排除供给` 并写理由（如 KS0001-DM-100-YELLOW×波兰：美中 PO021728 开放 123、
  10/28 美中在途 123，可能同批，不抵扣、不跨洲）。

只读：不写 EN/通途、不 push、不编造运费/时效/到货日。
"""

from __future__ import annotations

import argparse
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
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/46近端缺口_调拨候选_2026-10-28_v2.csv")
    args = ap.parse_args()

    proto = pd.read_csv(args.proto, encoding="utf-8-sig")
    classify = pd.read_csv(args.classify, encoding="utf-8-sig")

    near = classify[classify["近端兜底"].astype(str) == NEAR_FLAG][
        ["SKU", "仓库", "分类", "首次缺口周", "旧35天参考量", "当前可发(10-28同仓)", "近端兜底"]
    ].copy()
    merged = near.merge(
        proto[["SKU", "仓库", "Q_97目标", "需求_97目标_102天", "IP_已证"]],
        on=["SKU", "仓库"], how="left",
    )

    con = duckdb.connect(args.db, read_only=True)
    pairs = con.execute("select upper(sku) sku, upper(item_code) item from sku_item").df()
    tt_by_item: dict[str, set[str]] = {}
    for _, row in pairs.iterrows():
        tt_by_item.setdefault(row["item"], set()).add(row["sku"])

    stock = pd.read_parquet(args.stock)
    stock = stock[stock["snapshot_date"].astype(str) == SNAPSHOT].copy()
    stock["sku"] = stock["sku"].astype(str).str.upper()
    avail = stock.groupby(["warehouse_name", "sku"])["available"].sum()
    intransit = stock.groupby(["warehouse_name", "sku"])["intransit"].sum()
    all_warehouses = sorted(stock["warehouse_name"].unique())

    po = pd.read_csv(args.po, encoding="utf-8-sig")
    po["sku"] = po["goods_sku"].map(clean_sku)
    po["open_qty"] = pd.to_numeric(po.get("open"), errors="coerce").fillna(0)
    open_po = po[po["open_qty"] > 0].groupby(["warehouseName", "sku"])["open_qty"].sum()

    def qty_at(series, warehouse: str, item: str) -> float:
        return float(sum(float(series.get((warehouse, tt), 0.0)) for tt in tt_by_item.get(item, set())))

    def describe_supply(warehouse: str, item: str) -> str:
        parts = []
        a = qty_at(avail, warehouse, item)
        t = qty_at(intransit, warehouse, item)
        p = qty_at(open_po, warehouse, item) if len(open_po) else 0.0
        if a > 0:
            parts.append(f"可用 {a:g}")
        if t > 0:
            parts.append(f"在途 {t:g}")
        if p > 0:
            parts.append(f"开放PO {p:g}")
        return "；".join(parts)

    consumed: dict[tuple[str, str], float] = {}
    rows = []

    for _, row in merged.iterrows():
        sku, dest = row["SKU"], row["仓库"]
        is_pl = dest in PL_WAREHOUSES
        allowed_sources = [w for w in (PL_WAREHOUSES if is_pl else US_WAREHOUSES) if w != dest]

        q97 = row.get("Q_97目标")
        old_ref = row.get("旧35天参考量")
        if pd.notna(q97):
            reference = float(q97)
            q97_col = round(reference, 3)
            old_col = None
            basis = "长窗补量参考 Q97（已净额：需求+SS−IP，IP 已含 10/28 当前可发；非救急量）"
            basis_short = "Q97（长窗、已净额）"
        else:
            reference = float(old_ref or 0)
            q97_col = None
            old_col = round(reference, 3)
            basis = "旧35天净缺口（救急行对照；已扣 opening，不再扣当前可发；非统一近端口径）"
            basis_short = "旧35天净缺口（救急行）"

        source_name, source_avail, same_country = "", 0.0, "否"
        transferable = 0.0
        same_po = same_transit = ""
        for src in allowed_sources:
            key = (src, sku)
            left = max(0.0, qty_at(avail, src, sku) - consumed.get(key, 0.0))
            po_left = qty_at(open_po, src, sku) if len(open_po) else 0.0
            transit_left = qty_at(intransit, src, sku)
            if left > 0 or po_left > 0 or transit_left > 0:
                source_name, source_avail, same_country = src, left, "是"
                transferable = min(left, reference)
                consumed[key] = consumed.get(key, 0.0) + transferable
                same_po = f"{po_left:g}" if po_left > 0 else ""
                same_transit = f"{transit_left:g}" if transit_left > 0 else ""
                break

        remaining = max(0.0, reference - transferable)

        # F3：允许仓池之外的所有供给（跨洲/第三方）披露，不抵扣
        excluded = []
        for wh in all_warehouses:
            if wh == dest or wh in allowed_sources:
                continue
            desc = describe_supply(wh, sku)
            if desc:
                excluded.append(f"{wh}：{desc}")
        excluded_text = "；".join(excluded)
        if excluded_text and "在途" in excluded_text and "开放PO" in excluded_text:
            excluded_note = "跨洲/仓池外供给，不可抵扣、不可跨洲调拨（在途与开放 PO 可能同批，未去重）"
        elif excluded_text:
            excluded_note = "跨洲/仓池外供给，不可抵扣、不可跨洲调拨"
        else:
            excluded_note = ""

        if transferable > 0:
            action = "可同国调拨（上限=min(源仓可用, 参考缺口)），剩余缺口另议"
            confirm = "调拨运费/时效未评估；源仓库存是否可动需仓库确认；跨分公司调拨需审批"
        elif is_pl:
            action = "无可调，需加急/接受缺货"
            confirm = "波兰无第二仓；美国仓不可跨洲调拨；是否加急/接受缺货需业务决定"
        else:
            action = "无可调，需加急/接受缺货"
            confirm = "同国源仓该 SKU 10-28 无可用；是否加急/接受缺货需业务决定"
        if transferable > 0 and remaining > 0:
            confirm += "；调拨后仍有缺口，剩余需加急或接受缺货"
        if excluded_text:
            confirm += "；仓池外供给仅披露，如需动用需另立跨洲方案与审批"

        rows.append({
            "SKU": sku,
            "目的仓": dest,
            "分类": row["分类"],
            "数据来源": "48 原型（待定量）" if pd.notna(q97) else "53 分类（救急，无 Q97）",
            "首次缺口周": row["首次缺口周"],
            "长窗补量参考Q97_已净额": q97_col,
            "旧35天净缺口_仅救急行": old_col,
            "参考口径": basis,
            "调拨对比依据": basis_short,
            "当前可发_10-28同仓_仅参考不扣减": float(row["当前可发(10-28同仓)"] or 0),
            "源仓": source_name,
            "源仓可用_10-28": round(source_avail, 3),
            "建议调拨上限": round(transferable, 3),
            "调拨后仍缺": round(remaining, 3),
            "是否同国": same_country,
            "潜在改配_同国开放PO": same_po,
            "潜在改配_同国在途": same_transit,
            "跨洲排除供给": excluded_text,
            "跨洲排除说明": excluded_note,
            "建议动作": action,
            "需业务确认项": confirm,
        })

    out = pd.DataFrame(rows).sort_values(["目的仓", "长窗补量参考Q97_已净额"], ascending=[True, False])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")

    q97_total = float(out["长窗补量参考Q97_已净额"].fillna(0).sum())
    old_total = float(out["旧35天净缺口_仅救急行"].fillna(0).sum())
    transfer_total = float(out["建议调拨上限"].sum())
    print(f"rows={len(out)}")
    print(f"参考: Q97合计={q97_total:.3f} + 旧35天净缺口={old_total:.3f} = 混合参考合计 {q97_total+old_total:.3f}（非统一近端缺口）")
    print(f"可调行={(out['建议调拨上限']>0).sum()} 总上限={transfer_total:.3f} 调后剩余合计={(q97_total+old_total)-transfer_total:.3f}")
    print(f"无可调行={(out['建议调拨上限']<=0).sum()}（波兰 {int(((out['目的仓'].isin(PL_WAREHOUSES)) & (out['建议调拨上限']<=0)).sum())}）")
    print(f"跨洲排除披露行={(out['跨洲排除供给'].astype(str)!='').sum()}")
    print(f"output={args.out}")


if __name__ == "__main__":
    main()
