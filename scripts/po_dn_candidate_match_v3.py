"""PO ↔ DN 候选匹配 v3（只读；在 v2 上做 5 项小修，不改匹配结果）。

v3 变化（对应 v2 复审 accept-with-findings）：
- P2#1 非正式推荐改标「候选建议→DN-…（未正式登记）」，「本 DN」只留给正式链接
- P2#2 FBA 判定补「全部明细客户码均为 FBA」分支；mixed/unknown 不算 FBA，并有测试
- P2#3 exception 逐条保留 uom/role 与 raw 别名；按 UOM 分别汇总，删除跨单位总数
- P3#4 边界与敏感性表述修正（32 FBA 含 5 取消 + 3 非 FBA 取消 + 28 分析 = 63；
  敏感性改为「27 个首选不变，部分分值与低位排序变化」）
- P3#5 新增 aliases_raw_all（保留原始 `删除` 前缀别名），清洗别名另存

v2 原有口径（F1–F5）见本文件历史与 `PO_DN候选匹配报告_2026-10-28_v2.md`。

修复要点
- F1 正式归属：official_owner 来自 EN `custom_tongtool_purchase_order` 只读导出
  （`en_dn_po_field_2026-10-28.json` + manifest），不是硬编码；评分前排除已被
  其他 DN 正式占用的 PO；`proposed_owner` 与 `official_owner` 分列；不再给非正式
  推荐写「本DN」。
- F2 逐 SKU 数量拟合：qty_fit = 1 - Σ|DN_sku - PO_sku| / ΣDN_sku（未命中 SKU 按
  全差计入），不再用总数相减；同时输出 coverage / 未匹配 SKU 数。
- F3 组件别名：保留全部别名与原始 item_code；归一后唯一才解析；多别名按显式
  「渠道别名」规则（含 FBA/BN/RR/SXQC/RS-/WHITE/BLACK/GRAY 等）过滤，仍不唯一
  的隔离（ambiguous），不参与打分。
- F4 反查别名同样清 `删除` 前缀；PO 侧别名同样清理；保留 raw alias 供审计。
- F5 补拉 manifest：通途 PO 拉取脚本记录请求/分页/状态/行数/sha256；
  「某窗口无 PO」表述收窄为「该查询窗口返回 0 行（状态 200、未触发分页上限）」。

业务分类（用户规则）
- 纯内胆 DN（全部行 ND#，无可售 KS/PK）：`纯内胆—不建PO/无需匹配`
- FBA DN（客户为 FBA 仓 / 明细全 FBA 客户码）：`FBA—不建PO/无需匹配`
- 其余 DN 才参与候选匹配
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import duckdb
import pandas as pd

DN_START = "2026-08-01"
GAP_LIMIT_DAYS = 90
DATE_SCORE_DAYS = 30
SCORE_ACCEPT = 0.60
SCORE_ALT = 0.35

WH_BY_CUSTOMER = {
    "CENTRADE": {"美东-CENTRADE"},
    "DANEEY": {"美中-FZH-DANEEY", "FZH-DANEEY-成品仓", "FZH-DANEEY-半成品仓"},
    "波兰公司": {"波兰-FZHPoland-covers"},
}

COMPONENT_SUFFIX = re.compile(r"-(FOAM|COVER)$")
# 渠道/仓库专用别名标记：这些码用于 Amazon/其他渠道或退货/质检，不是通途采购货品码
CHANNEL_ALIAS = re.compile(r"FBA|#QC|^BN|^BAI|^RR|^SXQC|^RS-|^SUK|^SUS|^VUS|^DUS|^WHITE|^BLACK|^GRAY")


def clean_code(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = re.sub(r"^删除", "", str(value).strip().upper())
    return text or None


def normalized(sku):
    if not isinstance(sku, str):
        return None
    return COMPONENT_SUFFIX.sub("", sku)


def direction_label(gap: int) -> str:
    if gap == 0:
        return "同日"
    if gap > 0:
        return f"PO 早于 DN（{gap} 天）"
    if gap >= -3:
        return "PO 晚于 DN（隔日建单 ≤3 天）"
    return f"PO 晚于 DN（回溯建单 {-gap} 天）"


def resolve_aliases(raw_aliases, use_channel_rule: bool = True) -> tuple[str | None, str]:
    """反查别名 → (canonical SKU, basis)。

    - 归一后唯一 → item_code_unique
    - 多别名但按渠道别名规则只剩一个 → item_code_channel_rule
    - 其余 → ambiguous（隔离，不参与打分）
    """
    aliases = [clean_code(a) for a in raw_aliases]
    aliases = [a for a in aliases if a]
    if not aliases:
        return None, "unresolved"
    norm_aliases = sorted({normalized(a) for a in aliases})
    if len(norm_aliases) == 1:
        return norm_aliases[0], "item_code_unique"
    if use_channel_rule:
        non_channel = [a for a in norm_aliases if not CHANNEL_ALIAS.search(a)]
        if len(non_channel) == 1:
            return non_channel[0], "item_code_channel_rule"
    return None, "ambiguous"


def per_sku_qty_fit(dn_sku_qty: dict, po_sku_qty: dict) -> tuple[float, float, list[str]]:
    """逐 SKU 数量拟合：未命中 SKU 按全差计入，避免 SKU 间误差对冲。

    返回 (qty_fit, coverage, unmatched_skus)。
    反例：DN(10,90) vs PO(90,10) → abs_error=160, qty_fit=0（旧总数法会给 1.0）。
    """
    dn_total = sum(float(v) for v in dn_sku_qty.values())
    if not dn_total:
        return 0.0, 0.0, []
    abs_error = 0.0
    covered = 0.0
    unmatched = []
    for sku, qty in dn_sku_qty.items():
        po_qty = float(po_sku_qty.get(sku, 0.0))
        abs_error += abs(float(qty) - po_qty)
        covered += min(float(qty), po_qty)
        if sku not in po_sku_qty:
            unmatched.append(sku)
    return max(0.0, 1 - abs_error / dn_total), covered / dn_total, unmatched


def is_fba_code(code) -> bool:
    """FBA 客户码判定：码本身带 FBA 标记（保守，不从单个组件别名外推）。"""
    return bool(isinstance(code, str) and re.search(r"FBA", code.upper()))


def uom_breakdown(qty_values, uom_values) -> dict[str, float]:
    out: dict[str, float] = {}
    for qty, uom in zip(qty_values, uom_values):
        unit = str(uom).strip() if uom is not None and str(uom).strip() else "unknown"
        out[unit] = out.get(unit, 0.0) + float(qty)
    return out


def format_uom_breakdown(breakdown: dict[str, float]) -> str:
    return ";".join(f"{unit}={value:g}" for unit, value in sorted(breakdown.items()))


def single_uom(breakdown: dict[str, float]) -> str:
    return next(iter(breakdown)) if len(breakdown) == 1 else "mixed"


def role_of(item_code: str) -> str:
    text = str(item_code or "")
    if text.startswith("ND#"):
        return "inner_liner"
    if text.startswith("PK#"):
        return "cover_component"
    return "other"


def load_dns(path: str, con: duckdb.DuckDBPyConnection, use_channel_rule: bool = True) -> pd.DataFrame:
    dn = pd.read_csv(path, encoding="utf-8-sig")
    dn["dn"] = dn["dn"].astype(str)
    dn = dn[dn["posting_date"] >= DN_START].copy()

    pairs = con.execute("select upper(sku) as sku, upper(item_code) as item from sku_item").df()
    reverse: dict[str, set[str]] = {}
    for _, row in pairs.iterrows():
        reverse.setdefault(row["item"], set()).add(row["sku"])

    records = []
    for _, row in dn.iterrows():
        raw_cc = row["customer_item_code"]
        item_code = clean_code(row["item_code"]) or ""
        aliases: list[str] = []
        aliases_raw: list[str] = []
        basis = None
        resolved = None
        if clean_code(raw_cc):
            resolved = clean_code(raw_cc)
            aliases = [resolved]
            aliases_raw = [str(raw_cc).strip()]
            basis = "customer_item_code"
        else:
            base = re.sub(r"^(PK#|ND#)", "", item_code)
            raw_aliases = sorted(reverse.get(base) or reverse.get(item_code) or set())
            aliases_raw = raw_aliases
            aliases = [clean_code(a) for a in raw_aliases if clean_code(a)]
            resolved, basis = resolve_aliases(raw_aliases, use_channel_rule)
        records.append(
            {
                "dn": row["dn"], "posting_date": row["posting_date"], "customer": row["customer"],
                "item_code": item_code, "raw_customer_item_code": raw_cc,
                "aliases_all": ";".join(aliases), "aliases_raw_all": ";".join(aliases_raw),
                "alias_count": len(set(aliases)),
                "resolved_sku": resolved, "resolve_basis": basis,
                "nsku": normalized(resolved), "qty": float(row["qty"]), "uom": row["uom"],
            }
        )
    items = pd.DataFrame(records)
    return items


def classify_dn(group: pd.DataFrame) -> str:
    """三类业务规则：FBA（客户名或全量 FBA 客户码）/ 纯内胆 / 可匹配。

    - 客户名含 FBA → FBA
    - 全部明细都有客户码且每一条都是 FBA 码 → FBA
    - mixed（部分 FBA）/ unknown（有行没有客户码）→ 不算 FBA，按可匹配/纯内胆继续判
    """
    if "FBA" in str(group["customer"].iloc[0]).upper():
        return "fba"
    cc_column = "raw_customer_item_code" if "raw_customer_item_code" in group.columns else "customer_item_code"
    codes = [clean_code(v) for v in group[cc_column]]
    if len(group) and all(codes) and all(is_fba_code(c) for c in codes):
        return "fba"
    item_codes = group["item_code"].astype(str)
    if len(group) and item_codes.str.startswith("ND#").all():
        return "pure_liner"
    return "matchable"


def load_pos(paths: list[str]) -> pd.DataFrame:
    frames = []
    for path in paths:
        if not Path(path).exists():
            continue
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        if rows:
            frames.append(pd.DataFrame(rows))
    po = pd.concat(frames, ignore_index=True)
    po["po_date"] = pd.to_datetime(po["createdDate"]).dt.strftime("%Y-%m-%d")
    po["raw_sku"] = po["goods_sku"].astype(str)
    po["sku"] = po["raw_sku"].map(clean_code)
    po["nsku"] = po["sku"].map(normalized)
    po = po.drop_duplicates(subset=["PONum", "raw_sku", "quantity", "warehouseName"])
    return po


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="D:/Work/fzh-order-store/order_store.duckdb")
    ap.add_argument("--dn", default="D:/Work/fzh-order-store/analysis/leadtime/dn_items_with_customer_code.csv")
    ap.add_argument("--official", default="D:/Work/fzh-order-store/analysis/en_dn_po_field_2026-10-28.json")
    ap.add_argument("--po-files", nargs="+", default=[
        "D:/Work/fzh-order-store/tongtool_po/purchase_orders_20260725_20260826_v2.jsonl",
        "D:/Work/fzh-order-store/tongtool_po/purchase_orders_20260826_20261026_v2.jsonl",
        "D:/Work/fzh-order-store/tongtool_po/purchase_orders_20261026_20261028_v2.jsonl",
    ])
    ap.add_argument("--lh-po", default="D:/Work/fzh-order-store/analysis/leadtime/dn_po_no.csv")
    ap.add_argument("--receipt-status", default="D:/Work/fzh-order-store/tongtool_po/po_receipt_status_2026-08_10.csv")
    ap.add_argument("--out-dir", default="D:/Work/fzh-order-store/analysis")
    ap.add_argument("--suffix", default="_v3")
    ap.add_argument("--no-channel-rule", action="store_true", help="敏感性测试：禁用渠道别名规则")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    items = load_dns(args.dn, con, use_channel_rule=not args.no_channel_rule)
    po = load_pos(args.po_files)

    # ---------- F1: 正式归属（来自 EN 字段导出） ----------
    en_rows = json.loads(Path(args.official).read_text(encoding="utf-8"))
    official_by_dn = {}
    official_owner = {}
    for row in en_rows:
        po_value = (row.get("custom_tongtool_purchase_order") or "").strip()
        if not po_value:
            continue
        for token in re.split(r"[,;\s]+", po_value):
            if token:
                official_by_dn.setdefault(row["name"], []).append(token)
                official_owner[token] = row["name"]
    official_by_dn = {dn: ";".join(v) for dn, v in official_by_dn.items()}

    lh = pd.read_csv(args.lh_po, encoding="utf-8-sig")
    lh["dn"] = lh["dn"].astype(str)
    lh_map = lh.set_index("dn")["po_no"].to_dict()

    receipt_status: dict[str, str] = {}
    if Path(args.receipt_status).exists():
        rs = pd.read_csv(args.receipt_status, encoding="utf-8-sig")
        for ponum, g in rs.groupby("purchaseOrderCode"):
            done = int((g["status_calc"] == "全收").sum())
            open_ = int((g["status_calc"] == "未收").sum())
            receipt_status[ponum] = "全收" if done and not open_ else ("未收" if open_ and not done else f"混合(全收{done}/未收{undone})".replace("undone", str(open_)))

    # ---------- 分类 ----------
    dn_class = {}
    for d, g in items.groupby("dn"):
        dn_class[d] = "official" if d in official_by_dn else classify_dn(g)

    pair_rows, recon_rows, exception_rows = [], [], []
    allocation_remaining: dict[tuple[str, str], float] = {}
    accepted_pairs: list[tuple[str, str]] = []

    for d, g in items.groupby("dn"):
        klass = dn_class[d]
        dn_date = pd.Timestamp(g["posting_date"].iloc[0])
        customer = g["customer"].iloc[0]
        resolvable = g[g["nsku"].notna()]
        ambiguous = g[g["resolve_basis"] == "ambiguous"]
        unresolved = g[g["resolve_basis"].isin(["unresolved"])]
        dn_sku_qty = resolvable.groupby("nsku")["qty"].sum()

        # P2#3：数量按 UOM 记账，跨单位不相加
        all_break = uom_breakdown(g["qty"], g["uom"])
        res_break = uom_breakdown(resolvable["qty"], resolvable["uom"])
        amb_break = uom_breakdown(ambiguous["qty"], ambiguous["uom"])
        unres_break = uom_breakdown(unresolved["qty"], unresolved["uom"])

        def single_total(breakdown):
            return float(sum(breakdown.values())) if len(breakdown) <= 1 else None

        base = {
            "dn": d, "dn_date": dn_date.strftime("%Y-%m-%d"), "customer": customer,
            "dn_class": {"matchable": "可匹配", "official": "正式链接", "fba": "FBA", "pure_liner": "纯内胆"}[klass],
            "dn_rows": len(g), "dn_uom": single_uom(all_break), "dn_qty_by_uom": format_uom_breakdown(all_break),
            "dn_qty_total": single_total(all_break),
            "dn_sku_count": len(dn_sku_qty), "dn_qty_resolved": single_total(res_break),
            "dn_qty_resolved_by_uom": format_uom_breakdown(res_break),
            "dn_rows_ambiguous": len(ambiguous), "dn_qty_ambiguous": single_total(amb_break),
            "dn_qty_ambiguous_by_uom": format_uom_breakdown(amb_break),
            "dn_rows_unresolved": len(unresolved), "dn_qty_unresolved": single_total(unres_break),
            "dn_qty_unresolved_by_uom": format_uom_breakdown(unres_break),
            "official_po": official_by_dn.get(d, ""), "lh_po_no": lh_map.get(d, ""),
        }

        # 不需要匹配的 DN：纯内胆 / FBA —— 正常情况，不是缺口
        if klass in ("fba", "pure_liner"):
            label = "FBA—不建PO/无需匹配" if klass == "fba" else "纯内胆—不建PO/无需匹配"
            base.update({"po": "", "status": label, "recommendation": "无需匹配", "reason": ""})
            pair_rows.append(base)
            for _, row in g.iterrows():
                exception_rows.append({
                    "type": "fba_row" if klass == "fba" else "pure_liner_row",
                    "dn": d, "dn_date": base["dn_date"], "po": "",
                    "item_code": row["item_code"], "raw_customer_item_code": row["raw_customer_item_code"],
                    "aliases_all": row["aliases_all"], "aliases_raw_all": row["aliases_raw_all"],
                    "qty": row["qty"], "uom": row["uom"], "qty_by_uom": f"{row['uom']}={row['qty']:g}",
                    "role": role_of(row["item_code"]),
                    "reason": "FBA DN 不建通途 PO（业务规则）" if klass == "fba" else "纯内胆 ND#，无独立 SKU、不建 PO（业务规则）",
                })
            continue

        # 可匹配 / 正式链接
        candidates = []
        for p, pg in po[po["warehouseName"].isin(WH_BY_CUSTOMER.get(customer, set()))].groupby("PONum"):
            owner = official_owner.get(p)
            if owner and owner != d:
                # 正式归属他人：不参与评分，但记录冲突（若本 DN 与其有 SKU 交集）
                continue
            po_date = pd.Timestamp(pg["po_date"].iloc[0])
            gap = int((dn_date - po_date).days)
            if abs(gap) > GAP_LIMIT_DAYS:
                continue
            po_sku_qty = pg.groupby("nsku")["quantity"].sum()
            shared = [s for s in dn_sku_qty.index if s in po_sku_qty.index]
            matched = len(shared)
            recalled = matched / len(dn_sku_qty) if len(dn_sku_qty) else 0.0
            # F2: 逐 SKU 差异（未命中 SKU 全差计入）
            qty_fit, coverage, unmatched_sku = per_sku_qty_fit(
                dn_sku_qty.to_dict(), po_sku_qty.to_dict()
            )
            exact = sum(1 for s in shared if dn_sku_qty[s] == po_sku_qty[s]) / (matched or 1)
            date_score = max(0.0, 1 - abs(gap) / DATE_SCORE_DAYS)
            score = 0.45 * recalled + 0.30 * qty_fit + 0.10 * exact + 0.15 * date_score
            unmatched_sku = [s for s in dn_sku_qty.index if s not in po_sku_qty.index]
            candidates.append({
                **base,
                "po": p, "po_date": po_date.strftime("%Y-%m-%d"), "po_warehouse": pg["warehouseName"].iloc[0],
                "po_lines": len(pg), "po_qty_total": float(pg["quantity"].sum()), "gap_days": gap,
                "direction": direction_label(gap), "score": round(score, 4),
                "sku_recall": round(recalled, 4), "qty_fit": round(qty_fit, 4), "coverage": round(coverage, 4),
                "exact_sku_ratio": round(exact, 4), "matched_skus": matched,
                "unmatched_sku_count": len(unmatched_sku),
                "unmatched_sku_qty": float(sum(dn_sku_qty[s] for s in unmatched_sku)),
                "unmatched_sku_list": ";".join(sorted(unmatched_sku)),
                "matched_dn_qty": float(sum(dn_sku_qty[s] for s in shared)),
                "matched_po_qty": float(sum(po_sku_qty[s] for s in shared)),
                "po_extra_skus": len([s for s in po_sku_qty.index if s not in dn_sku_qty.index]),
                "po_receipt_status": receipt_status.get(p, ""),
                "is_official": "Y" if p in official_by_dn.get(d, "") else "",
                "official_owner": official_owner.get(p, ""),
            })

        candidates.sort(key=lambda c: c["score"], reverse=True)
        chosen = next((c for c in candidates if c["score"] >= SCORE_ACCEPT), None)
        if klass == "official":
            # 正式链接：以 EN 字段为准，若其 PO 在候选中则标为采纳
            off = [c for c in candidates if c["is_official"] == "Y"]
            chosen = off[0] if off else chosen
        shown = candidates[:3] if chosen else candidates[:3]

        proposed_owner: dict[str, str] = {}
        for rank, c in enumerate(shown, start=1):
            c["rank"] = rank
            if c is chosen:
                c["recommendation"] = "建议采纳" if klass != "official" else "正式链接"
                c["status"] = "有候选" if klass != "official" else "正式链接"
                proposed_owner[c["po"]] = d
                accepted_pairs.append((d, c["po"]))
            elif c["score"] >= SCORE_ALT and c["matched_skus"] >= 3:
                c["recommendation"] = "备选"
                c["status"] = "有候选"
            else:
                c["recommendation"] = "不采纳"
                c["status"] = "有候选"
            c["reason"] = ""
        if not candidates:
            base.update({"po": "", "po_date": "", "po_warehouse": "", "po_lines": 0, "po_qty_total": 0.0,
                         "gap_days": "", "direction": "", "score": 0.0, "sku_recall": 0.0, "qty_fit": 0.0,
                         "coverage": 0.0, "exact_sku_ratio": 0.0, "matched_skus": 0, "unmatched_sku_count": len(dn_sku_qty),
                         "unmatched_sku_qty": float(dn_sku_qty.sum()), "unmatched_sku_list": ";".join(sorted(dn_sku_qty.index)),
                         "matched_dn_qty": 0.0, "matched_po_qty": 0.0, "po_extra_skus": 0, "po_receipt_status": "",
                         "is_official": "", "official_owner": "", "rank": "", "recommendation": "",
                         "status": "无候选",
                         "reason": "R1 同仓 ±90 天内无未被正式占用的 PO" if len(dn_sku_qty) else "R4 无可解析 SKU"})
            pair_rows.append(base)
            exception_rows.append({"type": "no_candidate", "dn": d, "dn_date": base["dn_date"], "po": "",
                                   "item_code": "", "raw_customer_item_code": "", "aliases_all": "",
                                   "aliases_raw_all": "", "qty": None, "uom": base["dn_uom"],
                                   "qty_by_uom": base["dn_qty_by_uom"], "role": "aggregate",
                                   "reason": base["reason"]})
        elif not chosen:
            shown[0]["reason"] = "R3 最高分低于采纳阈值（SKU/数量证据不足）"
            exception_rows.append({"type": "no_candidate", "dn": d, "dn_date": shown[0]["dn_date"], "po": "",
                                   "item_code": "", "raw_customer_item_code": "", "aliases_all": "",
                                   "aliases_raw_all": "", "qty": None, "uom": shown[0]["dn_uom"],
                                   "qty_by_uom": shown[0]["dn_qty_by_uom"], "role": "aggregate",
                                   "reason": shown[0]["reason"]})
        pair_rows.extend(shown)

        # 隔离行 & 未命中 SKU 进 exception companion
        for _, row in ambiguous.iterrows():
            exception_rows.append({"type": "ambiguous_alias", "dn": d, "dn_date": base["dn_date"], "po": "",
                                   "item_code": row["item_code"], "raw_customer_item_code": row["raw_customer_item_code"],
                                   "aliases_all": row["aliases_all"], "aliases_raw_all": row["aliases_raw_all"],
                                   "qty": row["qty"], "uom": row["uom"], "qty_by_uom": f"{row['uom']}={row['qty']:g}",
                                   "role": role_of(row["item_code"]),
                                   "reason": "反查多别名且无法用显式渠道规则唯一解析，已隔离不参与打分"})
        for _, row in unresolved.iterrows():
            exception_rows.append({"type": "unresolved_row", "dn": d, "dn_date": base["dn_date"], "po": "",
                                   "item_code": row["item_code"], "raw_customer_item_code": row["raw_customer_item_code"],
                                   "aliases_all": row["aliases_all"], "aliases_raw_all": row["aliases_raw_all"],
                                   "qty": row["qty"], "uom": row["uom"], "qty_by_uom": f"{row['uom']}={row['qty']:g}",
                                   "role": role_of(row["item_code"]),
                                   "reason": "item_code 在 sku_item 无任何映射"})
        if chosen:
            for s in chosen["unmatched_sku_list"].split(";") if chosen["unmatched_sku_list"] else []:
                rows_s = resolvable[resolvable["nsku"] == s]
                brk = uom_breakdown(rows_s["qty"], rows_s["uom"])
                exception_rows.append({"type": "unmatched_sku", "dn": d, "dn_date": chosen["dn_date"],
                                       "po": chosen["po"], "item_code": "", "raw_customer_item_code": "",
                                       "aliases_all": s,
                                       "aliases_raw_all": ";".join(sorted(set(rows_s["aliases_raw_all"]))),
                                       "qty": float(sum(brk.values())) if len(brk) <= 1 else None,
                                       "uom": single_uom(brk), "qty_by_uom": format_uom_breakdown(brk),
                                       "role": "product_sku",
                                       "reason": "DN 有该 SKU，采纳 PO 无对应行"})

    links = pd.DataFrame(pair_rows)

    # proposed_owner 按采纳结果回填（不写「本DN」给非正式）
    proposed_by_po = {}
    for row in links.itertuples():
        if getattr(row, "recommendation", "") in ("建议采纳", "正式链接"):
            proposed_by_po[row.po] = row.dn
    links["proposed_owner"] = links["po"].map(lambda p: proposed_by_po.get(p, "") if isinstance(p, str) and p else "")

    def ownership_note(row):
        """「本 DN」只留给 EN 正式链接；建议一律写「候选建议→DN-…（未正式登记）」。"""
        if isinstance(row["po"], str) and row["po"] and row["is_official"] == "Y":
            return "本 DN（正式）"
        if isinstance(row["official_owner"], str) and row["official_owner"]:
            return f"已被 {row['official_owner']} 正式占用"
        if isinstance(row["proposed_owner"], str) and row["proposed_owner"]:
            return f"候选建议→{row['proposed_owner']}（未正式登记）"
        return ""

    links["ownership_note"] = links.apply(ownership_note, axis=1)

    # ---------- 逐 SKU 对账 + 显式分配 ----------
    for d, p in accepted_pairs:
        g = items[items["dn"] == d]
        resolvable = g[g["nsku"].notna()]
        dn_sku_qty = resolvable.groupby("nsku")["qty"].sum()
        dn_skus = resolvable.groupby("nsku")["resolved_sku"].apply(lambda s: ";".join(sorted(set(s.dropna()))))
        pg = po[po["PONum"] == p]
        for s, qty in dn_sku_qty.items():
            po_rows = pg[pg["nsku"] == s]
            po_qty = float(po_rows["quantity"].sum())
            key = (p, s)
            remaining = allocation_remaining.get(key, po_qty)
            alloc = min(float(qty), remaining)
            allocation_remaining[key] = remaining - alloc
            rows_s = resolvable[resolvable["nsku"] == s]
            brk = uom_breakdown(rows_s["qty"], rows_s["uom"])
            recon_rows.append({
                "dn": d, "po": p, "sku_normalized": s,
                "dn_skus": dn_skus.get(s, ""),
                "po_raw_skus": ";".join(sorted(set(po_rows["raw_sku"]))),
                "dn_aliases_raw": ";".join(sorted(set(rows_s["aliases_raw_all"]))),
                "dn_rows": int(len(rows_s)),
                "uom": single_uom(brk), "dn_qty_by_uom": format_uom_breakdown(brk),
                "dn_qty": float(qty), "po_qty": po_qty,
                "diff_dn_minus_po": float(qty - po_qty), "alloc_qty": round(alloc, 3),
                "alloc_basis": "full" if qty == po_qty else ("po_excess" if po_qty > qty else "shortfall"),
                "match_type": "exact" if set(dn_skus.get(s, "").split(";")) & set(po_rows["sku"]) else "normalized",
            })

    recon = pd.DataFrame(recon_rows)
    links = links.sort_values(["dn", "rank"], na_position="last")
    exceptions = pd.DataFrame(exception_rows)

    # 正式占位冲突：被正式占用而未能进入候选的高分 PO（审计用）
    for d, g in items.groupby("dn"):
        if dn_class[d] in ("fba", "pure_liner"):
            continue
        dn_date = pd.Timestamp(g["posting_date"].iloc[0])
        resolvable = g[g["nsku"].notna()]
        dn_sku_qty = resolvable.groupby("nsku")["qty"].sum()
        for p, owner in official_owner.items():
            if owner == d:
                continue
            pg = po[po["PONum"] == p]
            if pg.empty:
                continue
            if pg["warehouseName"].iloc[0] not in WH_BY_CUSTOMER.get(g["customer"].iloc[0], set()):
                continue
            po_sku_qty = pg.groupby("nsku")["quantity"].sum()
            shared = [s for s in dn_sku_qty.index if s in po_sku_qty.index]
            if len(shared) >= 3:
                rows_s = resolvable[resolvable["nsku"].isin(shared)]
                brk = uom_breakdown(rows_s["qty"], rows_s["uom"])
                exceptions = pd.concat([exceptions, pd.DataFrame([{
                    "type": "official_conflict", "dn": d, "dn_date": dn_date.strftime("%Y-%m-%d"), "po": p,
                    "item_code": "", "raw_customer_item_code": "", "aliases_all": ";".join(sorted(shared)),
                    "aliases_raw_all": ";".join(sorted(set(rows_s["aliases_raw_all"]))),
                    "qty": float(sum(brk.values())) if len(brk) <= 1 else None,
                    "uom": single_uom(brk), "qty_by_uom": format_uom_breakdown(brk),
                    "role": "product_sku",
                    "reason": f"该 PO 已被 {owner} 正式占用，本 DN 评分前已排除",
                }])], ignore_index=True)

    # ---------- 输出 ----------
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    links_path = out_dir / f"po_dn_candidate_links_2026-10-28{args.suffix}.csv"
    recon_path = out_dir / f"po_dn_sku_recon_2026-10-28{args.suffix}.csv"
    exc_path = out_dir / f"po_dn_exceptions_2026-10-28{args.suffix}.csv"
    json_path = out_dir / f"po_dn_candidate_links_2026-10-28{args.suffix}.json"

    links.to_csv(links_path, index=False, encoding="utf-8-sig")
    recon.to_csv(recon_path, index=False, encoding="utf-8-sig")
    exceptions.to_csv(exc_path, index=False, encoding="utf-8-sig")

    dns = links.drop_duplicates("dn")
    official_detail = []
    for d, p in official_by_dn.items():
        sub = links[(links["dn"] == d) & (links["po"].str.split(";").apply(lambda lst: p in lst))]
        official_detail.append({"dn": d, "official_po": p, "found": bool(len(sub)),
                                "rank": int(sub["rank"].iloc[0]) if len(sub) and pd.notna(sub["rank"].iloc[0]) else None})
    # P2#3：只出分 UOM 合计，不写跨单位总数
    dn_uom_totals = uom_breakdown(items["qty"], items["uom"])
    exc_uom_by_type = {}
    if len(exceptions):
        for etype, grp in exceptions.groupby("type"):
            brk = {}
            for row in grp.itertuples():
                if getattr(row, "uom", "") not in ("", None, "mixed") and pd.notna(getattr(row, "qty", None)):
                    brk[row.uom] = brk.get(row.uom, 0.0) + float(row.qty)
                elif isinstance(getattr(row, "qty_by_uom", ""), str) and row.qty_by_uom:
                    for token in str(row.qty_by_uom).split(";"):
                        if "=" in token:
                            unit, value = token.split("=", 1)
                            brk[unit] = brk.get(unit, 0.0) + float(value)
            exc_uom_by_type[etype] = brk
    recon_uom_totals: dict[str, float] = {}
    for row in recon.itertuples():
        if getattr(row, "uom", "") in ("", None, "mixed"):
            for token in str(getattr(row, "dn_qty_by_uom", "")).split(";"):
                if "=" in token:
                    unit, value = token.split("=", 1)
                    recon_uom_totals[unit] = recon_uom_totals.get(unit, 0.0) + float(value)
        else:
            recon_uom_totals[row.uom] = recon_uom_totals.get(row.uom, 0.0) + float(row.dn_qty)

    stats = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "dn_total": int(dns["dn"].nunique()),
        "dn_rows_total": int(len(items)),
        "dn_qty_by_uom": dn_uom_totals,
        "qn_note": "数量按 UOM 分列；不做跨单位合计、不做件/套→个换算",
        "dn_rows_resolved": int(items["nsku"].notna().sum()),
        "dn_rows_ambiguous": int((items["resolve_basis"] == "ambiguous").sum()),
        "dn_rows_unresolved": int((items["resolve_basis"] == "unresolved").sum()),
        "dn_class_counts": dns["dn_class"].value_counts().to_dict(),
        "status_counts": dns["status"].value_counts().to_dict(),
        "official_links": official_detail,
        "official_regression_rank1": sum(1 for o in official_detail if o["rank"] == 1 and o["found"]),
        "proposed_links": int(dns[dns["recommendation"] == "建议采纳"]["dn"].nunique()),
        "exception_types": exceptions["type"].value_counts().to_dict() if len(exceptions) else {},
        "exception_qty_by_uom": exc_uom_by_type,
        "recon_qty_by_uom": recon_uom_totals,
        "po_universe": int(po["PONum"].nunique()),
        "po_lines": int(len(po)),
        "po_date_range": [po["po_date"].min(), po["po_date"].max()],
        "outputs": {"links": str(links_path), "recon": str(recon_path),
                    "exceptions": str(exc_path), "json": str(json_path)},
    }
    json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
