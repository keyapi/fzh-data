"""PO ↔ DN 候选匹配（只读）。

背景：2026-08-01 后 28 张 DN 里只有 8 张在 EN 正式字段 `custom_tongtool_purchase_order`
有 PO 号；其余 20 张需要「候选匹配表」交人工确认。

输入（全部只读，不改 EN / 通途）：
- DN 明细      D:/Work/fzh-order-store/analysis/leadtime/dn_items_with_customer_code.csv
- 通途 PO 行   D:/Work/fzh-order-store/tongtool_po/purchase_orders_recent.jsonl（8/26–10/26 快照）
               purchase_orders_jul_aug_20261028.jsonl（7/25–8/26 只读补拉，确认 7/26–8/25 无 PO）
               purchase_orders_gap_20261028.jsonl（10/26–10/28 只读补拉，补 PO021743）
- 入库状态     D:/Work/fzh-order-store/tongtool_po/po_receipt_status_2026-08_10.csv
- 入库明细     D:/Work/fzh-order-store/tongtool_po/po_receipts_20260801_20261028.csv
- SKU 映射     DuckDB sku_item（item_code ↔ 通途 SKU，用于 PK#/ND# 行反查）

输出：
- po_dn_candidate_links_2026-10-28.csv   每 DN × 候选 PO（含分数、命中 SKU、日期、替代候选、原因）
- po_dn_sku_recon_2026-10-28.csv          候选对的逐 SKU 数量对账
- po_dn_candidate_links_2026-10-28.json   汇总计数

口径要点：
- PO 日期用 `createdDate`（采购单创建时间），不是 `po_no`（LH 旧编号，仅作参考列）
- 同 SKU 数量按 SKU 聚合后逐行对账（DN 行 → SKU 合计；PO 行 → SKU 合计）；
  DN 明细里无客户码的组件行（PK#/ND#）先尝试 item_code 反查，仍无映射则单列「未解析」
- 8 张已确认映射作为回归样例，必须 rank=1
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import duckdb
import pandas as pd

DN_START = "2026-08-01"
GAP_LIMIT_DAYS = 90          # 候选 PO 与 DN 的最大日期距离（双向；实测 PO 可回溯在建 DN 之后）
DATE_SCORE_DAYS = 30         # 日期接近度衰减半程
SCORE_ACCEPT = 0.60          # 建议采纳阈值
SCORE_ALT = 0.35             # 备选阈值

OFFICIAL = {
    "DN-26-00086": "PO021725",
    "DN-26-00087": "PO021724",
    "DN-26-00104-1": "PO021737",
    "DN-26-00110": "PO021738",
    "DN-26-00111": "PO021739",
    "DN-26-00112": "PO021740",
    "DN-26-00113-1": "PO021741",
    "DN-26-00115": "PO021743",
}

WH_BY_CUSTOMER = {
    "CENTRADE": {"美东-CENTRADE"},
    "DANEEY": {"美中-FZH-DANEEY", "FZH-DANEEY-成品仓", "FZH-DANEEY-半成品仓"},
    "波兰公司": {"波兰-FZHPoland-covers"},
}

COMPONENT_SUFFIX = re.compile(r"-(FOAM|COVER)$")


def clean_code(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = re.sub(r"^删除", "", str(value).strip().upper())
    return text or None


def normalized(sku: str | None) -> str | None:
    if not isinstance(sku, str):
        return None
    return COMPONENT_SUFFIX.sub("", sku)


def load_dns(path: str, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    dn = pd.read_csv(path, encoding="utf-8-sig")
    dn["dn"] = dn["dn"].astype(str)
    dn = dn[dn["posting_date"] >= DN_START].copy()

    pairs = con.execute("select upper(sku) as sku, upper(item_code) as item from sku_item").df()
    reverse: dict[str, set[str]] = {}
    for _, row in pairs.iterrows():
        reverse.setdefault(row["item"], set()).add(row["sku"])

    skus, basis = [], []
    for _, row in dn.iterrows():
        sku = clean_code(row["customer_item_code"])
        how = "customer_item_code"
        if not sku:
            item = clean_code(row["item_code"]) or ""
            base = re.sub(r"^(PK#|ND#)", "", item)
            candidates = reverse.get(base) or reverse.get(item) or set()
            sku = sorted(candidates)[0] if candidates else None
            how = "item_code_map" if sku else None
        skus.append(sku)
        basis.append(how)
    dn["resolved_sku"] = skus
    dn["resolve_basis"] = basis
    dn["nsku"] = dn["resolved_sku"].map(normalized)
    return dn


def load_pos(paths: list[str]) -> pd.DataFrame:
    frames = []
    for path in paths:
        if not Path(path).exists():
            continue
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        if rows:
            frames.append(pd.DataFrame(rows))
    po = pd.concat(frames, ignore_index=True)
    po = po.drop_duplicates(subset=["PONum", "goods_sku", "quantity", "warehouseName"])
    po["po_date"] = pd.to_datetime(po["createdDate"]).dt.strftime("%Y-%m-%d")
    po["sku"] = po["goods_sku"].astype(str).str.strip().str.upper()
    po["nsku"] = po["sku"].map(normalized)
    return po


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="D:/Work/fzh-order-store/order_store.duckdb")
    ap.add_argument("--dn", default="D:/Work/fzh-order-store/analysis/leadtime/dn_items_with_customer_code.csv")
    ap.add_argument("--po-files", nargs="+", default=[
        "D:/Work/fzh-order-store/tongtool_po/purchase_orders_recent.jsonl",
        "D:/Work/fzh-order-store/tongtool_po/purchase_orders_jul_aug_20261028.jsonl",
        "D:/Work/fzh-order-store/tongtool_po/purchase_orders_gap_20261028.jsonl",
    ])
    ap.add_argument("--lh-po", default="D:/Work/fzh-order-store/analysis/leadtime/dn_po_no.csv")
    ap.add_argument("--receipt-status", default="D:/Work/fzh-order-store/tongtool_po/po_receipt_status_2026-08_10.csv")
    ap.add_argument("--out-dir", default="D:/Work/fzh-order-store/analysis")
    ap.add_argument("--out-links", default="po_dn_candidate_links_2026-10-28.csv")
    ap.add_argument("--out-recon", default="po_dn_sku_recon_2026-10-28.csv")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    dn = load_dns(args.dn, con)
    po = load_pos(args.po_files)

    lh = pd.read_csv(args.lh_po, encoding="utf-8-sig")
    lh["dn"] = lh["dn"].astype(str)
    lh_map = lh.set_index("dn")["po_no"].to_dict()

    # 收货状态：只覆盖 PO021704–021714 / 021724 共 10 单，其余留空（不写 0、不猜）
    receipt_status: dict[str, str] = {}
    if Path(args.receipt_status).exists():
        rs = pd.read_csv(args.receipt_status, encoding="utf-8-sig")
        for ponum, g in rs.groupby("purchaseOrderCode"):
            done = int((g["status_calc"] == "全收").sum())
            open_ = int((g["status_calc"] == "未收").sum())
            if done and not open_:
                receipt_status[ponum] = "全收"
            elif open_ and not done:
                receipt_status[ponum] = "未收"
            else:
                receipt_status[ponum] = f"混合(全收{done}/未收{open_})"

    pair_rows, recon_rows = [], []
    assigned_by_dn: dict[str, str] = {}
    for d, dd in dn.groupby("dn"):
        dn_date = pd.Timestamp(dd["posting_date"].iloc[0])
        customer = dd["customer"].iloc[0]
        dn_rows = len(dd)
        dn_qty_total = float(dd["qty"].sum())
        resolved = dd.dropna(subset=["nsku"])
        unresolved = dd[dd["nsku"].isna()]
        dn_sku_qty = resolved.groupby("nsku")["qty"].sum()
        dn_sku_lines = resolved.groupby("nsku")["qty"].size()

        candidates = []
        for p, g in po[po["warehouseName"].isin(WH_BY_CUSTOMER.get(customer, set()))].groupby("PONum"):
            po_date = pd.Timestamp(g["po_date"].iloc[0])
            gap = int((dn_date - po_date).days)
            if abs(gap) > GAP_LIMIT_DAYS:
                continue
            po_sku_qty = g.groupby("nsku")["quantity"].sum()
            shared = [s for s in dn_sku_qty.index if s in po_sku_qty.index]
            recalled = len(shared) / len(dn_sku_qty) if len(dn_sku_qty) else 0.0
            dn_matched = float(sum(dn_sku_qty[s] for s in shared))
            po_matched = float(sum(po_sku_qty[s] for s in shared))
            qty_fit = 1 - abs(dn_matched - po_matched) / max(dn_matched, 1.0) if shared else 0.0
            exact = sum(1 for s in shared if dn_sku_qty[s] == po_sku_qty[s]) / (len(shared) or 1)
            date_score = max(0.0, 1 - abs(gap) / DATE_SCORE_DAYS)
            score = 0.45 * recalled + 0.30 * qty_fit + 0.10 * exact + 0.15 * date_score
            po_extra = [s for s in po_sku_qty.index if s not in dn_sku_qty.index]
            candidates.append(
                {
                    "dn": d, "dn_date": dn_date.strftime("%Y-%m-%d"), "customer": customer,
                    "dn_rows": dn_rows, "dn_qty_total": dn_qty_total,
                    "dn_sku_count": len(dn_sku_qty), "dn_qty_resolved": float(dn_sku_qty.sum()),
                    "dn_unresolved_rows": len(unresolved), "dn_unresolved_qty": float(unresolved["qty"].sum()),
                    "po": p, "po_date": po_date.strftime("%Y-%m-%d"), "po_warehouse": g["warehouseName"].iloc[0],
                    "po_lines": len(g), "po_qty_total": float(g["quantity"].sum()), "gap_days": gap,
                    "direction": direction_label(gap),
                    "score": round(score, 4), "sku_recall": round(recalled, 4),
                    "qty_fit": round(qty_fit, 4), "exact_sku_ratio": round(exact, 4),
                    "matched_skus": len(shared), "matched_dn_qty": dn_matched, "matched_po_qty": po_matched,
                    "po_extra_skus": len(po_extra), "po_extra_qty": float(sum(po_sku_qty[s] for s in po_extra)),
                    "po_receipt_status": receipt_status.get(p, ""),
                    "shared_sku_list": ";".join(sorted(shared)),
                }
            )
            for s in sorted(shared):
                po_rows = g[g["nsku"] == s]
                recon_rows.append(
                    {
                        "dn": d, "po": p, "sku_normalized": s,
                        "dn_sku": ";".join(sorted(set(dd.loc[dd["nsku"] == s, "resolved_sku"]))),
                        "po_skus": ";".join(sorted(set(po_rows["sku"]))),
                        "dn_rows": int(dn_sku_lines[s]), "dn_qty": float(dn_sku_qty[s]),
                        "po_lines": int(len(po_rows)), "po_qty": float(po_sku_qty[s]),
                        "diff_dn_minus_po": float(dn_sku_qty[s] - po_sku_qty[s]),
                        "match_type": "exact" if set(dd.loc[dd["nsku"] == s, "resolved_sku"]) & set(po_rows["sku"]) else "normalized",
                    }
                )

        # 归一化 / 组装配额：每 DN 取一个 PO（同 PO 可被多 DN 复用，按分数顺序；冲突写原因）
        candidates.sort(key=lambda c: c["score"], reverse=True)
        chosen = None
        for c in candidates:
            if c["score"] >= SCORE_ACCEPT:
                chosen = c
                break
        # 只保留前 3 个候选（采纳候选必然是 rank 1），避免把全部 PO 当噪声写进表
        shown = candidates[:3]
        for rank, c in enumerate(shown, start=1):
            c["rank"] = rank
            c["is_official"] = "Y" if OFFICIAL.get(d) == c["po"] else ""
            if c is chosen:
                c["recommendation"] = "建议采纳"
            elif c["score"] >= SCORE_ALT and c["matched_skus"] >= 3:
                c["recommendation"] = "备选"
            else:
                c["recommendation"] = "不采纳"
            c["lh_po_no"] = lh_map.get(d, "")
            c["status"] = "有候选" if chosen else "无候选"
            c["reason"] = ""
            if chosen:
                assigned_by_dn[d] = chosen["po"]
        if not candidates:
            pair_rows.append(
                {
                    "dn": d, "dn_date": dn_date.strftime("%Y-%m-%d"), "customer": customer,
                    "dn_rows": dn_rows, "dn_qty_total": dn_qty_total,
                    "dn_sku_count": len(dn_sku_qty), "dn_qty_resolved": float(dn_sku_qty.sum()),
                    "dn_unresolved_rows": len(unresolved), "dn_unresolved_qty": float(unresolved["qty"].sum()),
                    "po": "", "po_date": "", "po_warehouse": "", "po_lines": 0, "po_qty_total": 0.0,
                    "gap_days": "", "direction": "", "score": 0.0, "sku_recall": 0.0, "qty_fit": 0.0,
                    "exact_sku_ratio": 0.0, "matched_skus": 0, "matched_dn_qty": 0.0, "matched_po_qty": 0.0,
                    "po_extra_skus": 0, "po_extra_qty": 0.0, "po_receipt_status": "", "shared_sku_list": "",
                    "rank": "", "is_official": "", "recommendation": "", "lh_po_no": lh_map.get(d, ""),
                    "status": "无候选", "reason": reason_for(dd, dn_sku_qty, None),
                }
            )
        elif not chosen:
            best = shown[0]
            best["reason"] = reason_for(dd, dn_sku_qty, best)
        pair_rows.extend(shown)

    links = pd.DataFrame(pair_rows)
    # 该 PO 已被哪张 DN 采纳（人工确认时可看出候选 PO 是否被别 DN 占用）
    po_owner = {po: dn for dn, po in assigned_by_dn.items()}
    links["po_assigned_to"] = links["po"].map(lambda p: po_owner.get(p, ""))
    links.loc[links["dn"] == links["po_assigned_to"], "po_assigned_to"] = "本 DN"
    links = links.sort_values(["dn", "rank"], na_position="last")
    recon = pd.DataFrame(recon_rows)
    # 只保留每个 DN 的采纳候选 + 官方对的逐 SKU 对账，避免候选噪声
    keep = set(zip(links.loc[links["recommendation"] == "建议采纳", "dn"], links.loc[links["recommendation"] == "建议采纳", "po"]))
    keep |= {(d, p) for d, p in OFFICIAL.items()}
    recon = recon[[(r.dn, r.po) in keep for r in recon.itertuples()]]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    links_path = out_dir / args.out_links
    recon_path = out_dir / args.out_recon
    links.to_csv(links_path, index=False, encoding="utf-8-sig")
    recon.to_csv(recon_path, index=False, encoding="utf-8-sig")

    # 重复 PO 检测：同仓 + 同 SKU→数量 组合却有两个单号（如 PO021733/PO021735）
    sig = (
        po.assign(key=po["nsku"] + ":" + po["quantity"].astype(str))
        .groupby("PONum")
        .apply(lambda g: (g["warehouseName"].iloc[0], tuple(sorted(g["key"]))), include_groups=False)
    )
    dup_groups = {}
    for ponum, key in sig.items():
        dup_groups.setdefault(key, []).append(ponum)
    duplicates = [sorted(v) for v in dup_groups.values() if len(v) > 1]

    # 逐 SKU 对账汇总（采纳候选 + 官方对）
    recon_stats = {
        "pairs": int(recon.groupby(["dn", "po"]).ngroups),
        "sku_lines": int(len(recon)),
        "dn_qty": float(recon["dn_qty"].sum()),
        "po_qty": float(recon["po_qty"].sum()),
        "sku_lines_exact": int((recon["diff_dn_minus_po"] == 0).sum()),
        "sku_lines_diff": int((recon["diff_dn_minus_po"] != 0).sum()),
        "matched_by_normalized_suffix": int((recon["match_type"] == "normalized").sum()),
    }

    # 汇总
    dns = links.groupby("dn").first().reset_index()
    official_pass = []
    for d, p in OFFICIAL.items():
        sub = links[(links["dn"] == d) & (links["po"] == p)]
        official_pass.append({"dn": d, "po": p, "found": bool(len(sub)), "rank": int(sub["rank"].iloc[0]) if len(sub) else None})
    stats = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "dn_total": int(dns["dn"].nunique()),
        "dn_rows_total": int(dn.shape[0]),
        "dn_qty_total": float(dn["qty"].sum()),
        "dn_rows_resolved": int(dn["nsku"].notna().sum()),
        "dn_rows_unresolved": int(dn["nsku"].isna().sum()),
        "official_links": len(OFFICIAL),
        "official_regression_rank1": sum(1 for o in official_pass if o["rank"] == 1),
        "official_regression_detail": official_pass,
        "unlinked": int(dns["dn"].nunique() - len(OFFICIAL)),
        "unlinked_with_candidate": int(((dns["dn"].isin(OFFICIAL) == False) & (dns["status"] == "有候选")).sum()),
        "unlinked_without_candidate": int(((dns["dn"].isin(OFFICIAL) == False) & (dns["status"] == "无候选")).sum()),
        "retro_links": int(dns["direction"].str.contains("回溯建单").sum()),
        "duplicate_po_groups": duplicates,
        "recon": recon_stats,
        "po_universe": int(po["PONum"].nunique()),
        "po_lines": int(len(po)),
        "po_date_range": [po["po_date"].min(), po["po_date"].max()],
        "links_csv": str(links_path),
        "recon_csv": str(recon_path),
    }
    json_path = (out_dir / args.out_links).with_suffix(".json")
    json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def direction_label(gap: int) -> str:
    if gap == 0:
        return "同日"
    if gap > 0:
        return f"PO 早于 DN（{gap} 天）"
    if gap >= -3:
        return "PO 晚于 DN（隔日建单 ≤3 天）"
    return f"PO 晚于 DN（回溯建单 {-gap} 天）"


def reason_for(dd: pd.DataFrame, dn_sku_qty: pd.Series, best: dict | None) -> str:
    if len(dn_sku_qty) == 0:
        return "R4 DN 无可解析 SKU（仅 PK#/ND# 组件，本地物料映射缺失）"
    if best is None:
        return "R1 无同仓候选（PO 创建日期不在 ±90 天窗口内）"
    if best["matched_skus"] == 0:
        return "R2 同仓同期 PO 无 SKU 交集"
    if best["qty_fit"] < 0.3:
        return "R3 SKU 命中但数量显著不符（qty_fit<0.3）"
    return "R5 分数低于采纳阈值（候选存在但证据不足）"


if __name__ == "__main__":
    main()
