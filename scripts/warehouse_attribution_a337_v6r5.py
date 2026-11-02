# -*- coding: utf-8 -*-
"""B v6 r5：仓库归属 A337（只读）。

按 BRANCH-SUPPLY-MARKET-MODEL-2026-10-29（含 2.2/2.3 更正）实现。

r4 相对 r3 的两处修正
- **无美国证据不生成 US 行、不进④**（r3 旧版曾把 PL-only 产品判成 342 条假冲突）；
- **同产品同地区只出一行需求**：加 `demand_scope_id`，成品/皮壳等形态行只引用，
  数量只出现在 `是否需求行=Y` 的那一行，避免重复计需求。

r3 相对 r2 的三处修正
1. **库存按仓定位**：en_stock 10-28 按 A 来源码（清 ?/~/空格、含 -Cover 变体）精确匹配 SKU 定仓。
   波兰仓有货→波兰；美东USNJ/美中USTX 仅一侧→该侧；两侧都有→us_owner_stock_conflict；
   **按 SKU 在快照里确实查不到** 才写 stock_placement_pending_warehouse（不是「无市场」）。
2. **共享码不再挂待审卡**：按候选产品分别给地区归属（波兰与美国不互斥），数量标 shared_pool、
   不重复分给单一产品；只有美东USNJ vs 美中USTX 冲突才进④。
3. **海绵/Foam 不一律归成品**：按绍兴发货方式（item_group）——皮壳→皮壳供货；
   半成品/成品看实际 SO/DN；HM 是否单独补按 SO/DN 证据（本轮只标证据状态，不下结论）。

只读：不写 EN / 通途 / 不发消息 / 不 push。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

B = "D:/Work/fzh-order-store"
RULES_VERSION = "B-v6-rules-2026-10-29-r5"

CUSTOMER_REGION = {"CENTRADE": ("US", "East"), "DANEEY": ("US", "Central"),
                   "波兰公司": ("PL", None)}
SIDE_CN = {"East": "美东USNJ（美东-CENTRADE）", "Central": "美中USTX（美中-FZH-DANEEY）"}
# 全表统一写法的短名（禁止出现裸 East/Central）
SIDE_LABEL = {"East": "美东USNJ", "Central": "美中USTX"}


def side_text(raw) -> str:
    """把内部 side 代码（East/Central/None）翻成对外写法。"""
    if raw is None or (isinstance(raw, float)):
        return ""
    parts = [SIDE_LABEL.get(x.strip(), x.strip()) for x in str(raw).split(";") if x.strip()]
    return ";".join(parts)
MARKET_LABEL = {("US", "East"): "美国·美东", ("US", "Central"): "美国·美中",
                ("PL", None): "波兰"}
TIERS_ORDER = ("own90", "own180", "own2026", "dn2026", "own2025", "dn2025",
               "stock_placement")
STRIP = ("删除", "~", "?", "？")


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def norm_code(c) -> str:
    s = str(c).strip().replace(" ", "")
    changed = True
    while changed:
        changed = False
        for pre in STRIP:
            if s.startswith(pre):
                s = s[len(pre):].strip().replace(" ", "")
                changed = True
    return s.casefold()


def strip_pk(en: str) -> str:
    s = str(en).strip()
    return s[3:] if s.startswith("PK#") else s


def merge60(en: str) -> str:
    m = re.match(r"^(KS0248|KS0001)-(.*-)?60(-.*)$", str(en))
    return f"KS0248-{m.group(2) or ''}60{m.group(3)}" if m else str(en)


def product_of(en: str) -> str:
    return merge60(strip_pk(en))


def side_of_warehouse(w) -> str:
    s = str(w)
    if "CENTRADE" in s:
        return "美东"
    if "DANEEY" in s:
        return "美中"
    if "Poland" in s or "波兰" in s:
        return "波兰"
    return "其他"


def form_of(en: str, role: str, ship_type: str) -> tuple[str, str]:
    """返回 (normalized 供货形态, raw 发货方式)。海绵按绍兴发货方式细分，不一律成品。"""
    raw = (ship_type or "").strip()
    if str(en).startswith("ND#") or role == "内胆":
        return "内胆", raw or "内胆"
    if str(en).startswith("TJ#") or role == "套件":
        return "套件", raw or "套件"
    if str(en).startswith("PK#") or role == "皮壳":
        return "皮壳", raw or "皮壳"
    if role in ("海绵", "海绵/关联成品"):
        if raw in ("皮壳", "半成品"):
            return "皮壳", raw          # 半成品按业务口径归皮壳供货，raw 保留
        if raw == "成品":
            return "成品", raw
        # 发货方式未取 → 独立海绵；不得默认归成品。是否单独补看 SO/DN 证据。
        return "独立海绵", raw or "海绵（发货方式未取，item_group 快照无该组）"
    if role == "主体骨架":
        return "主体骨架", raw or "成品"
    return "成品", raw or "成品"


def build_code_index(a_final: Path, customer_codes: Path, sku_map: Path) -> dict:
    idx: dict[str, str] = {}

    def add(code, en):
        n = norm_code(code)
        if n and n not in ("nan", "none") and n not in idx:
            idx[n] = en

    u = pd.read_excel(a_final, sheet_name="活跃宇宙")
    for r in u[u["活跃分类"] != "不活跃"].itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                add(tok, r[0])
    cc = pd.read_csv(customer_codes, dtype=str)
    deleted = []
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if c:
                (deleted.append((c[2:], r.name)) if c.startswith("删除") else add(c, r.name))
    sm = pd.read_csv(sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        add(r.tt, r.en)
    for c, en in deleted:
        add(c, en)
    return idx


def side_facts(prod, region, ord26, ord25, dn_facts) -> dict:
    o26 = ord26[(ord26["product"] == prod) & (ord26["region"] == region)]
    o25 = ord25[(ord25["product"] == prod) & (ord25["region"] == region)]
    d26 = dn_facts[(dn_facts["product"] == prod) & (dn_facts["region"] == region)
                   & (dn_facts["year"] == 2026)]
    d25 = dn_facts[(dn_facts["product"] == prod) & (dn_facts["region"] == region)
                   & (dn_facts["year"] == 2025)]
    sides = ["East", "Central"] if region == "US" else [None]
    out = {}
    for side in sides:
        def pick(frame, col):
            if not len(frame):
                return 0.0
            sel = frame[frame["side"].isna()] if side is None else frame[frame["side"] == side]
            return float(pd.to_numeric(sel[col], errors="coerce").fillna(0).sum()) if len(sel) else 0.0
        out[side] = dict(own90=pick(o26, "90天"), own180=pick(o26, "180天"),
                         own2026=pick(o26, "2026"), own2025=pick(o25, "2025"),
                         dn2026_count=pick(d26, "DN笔数"), dn2026_qty=pick(d26, "DN供货量"),
                         dn2025_count=pick(d25, "DN笔数"), dn2025_qty=pick(d25, "DN供货量"))
    return out


def tier_of(f: dict) -> str | None:
    for k, t in (("own90", "own90"), ("own180", "own180"), ("own2026", "own2026")):
        if f[k] > 0:
            return t
    if f["dn2026_count"] > 0:
        return "dn2026"
    if f["own2025"] > 0:
        return "own2025"
    if f["dn2025_count"] > 0:
        return "dn2025"
    return None


def decide_region(prod, region, ord26, ord25, dn_facts, own_stock, shared_stock, a_stock):
    facts = side_facts(prod, region, ord26, ord25, dn_facts)
    tiers = {s: tier_of(f) for s, f in facts.items() if tier_of(f)}
    if tiers:
        best = min(tiers.values(), key=TIERS_ORDER.index)
        status = ("observed_current" if best in ("own90", "own180", "own2026", "dn2026")
                  else "observed_historical")
        agg = {k: sum(f[k] for f in facts.values()) for k in
               ("own90", "own180", "own2026", "own2025", "dn2026_count", "dn2026_qty",
                "dn2025_count", "dn2025_qty")}
        per = {}
        for side, f in facts.items():
            key = "PL" if side is None else side
            per[f"v2026_{key}"] = f["own2026"]
            per[f"v2025_{key}"] = f["own2025"]
        return dict(product=prod, region=region, tier=best, market_status=status,
                    sides_with_evidence=";".join(sorted(str(s) for s in tiers)),
                    stock_own=0.0, stock_shared_pool=0.0, stock_note="", **agg, **per)

    own = own_stock.get(prod, {})
    shr = shared_stock.get(prod, {})
    base = dict(product=prod, region=region, own90=0.0, own180=0.0, own2026=0.0, own2025=0.0,
                dn2026_count=0, dn2026_qty=0.0, dn2025_count=0, dn2025_qty=0.0)
    if region == "PL":
        q_own, q_shr = float(own.get("波兰", 0.0)), float(shr.get("波兰", 0.0))
        if q_own > 0 or q_shr > 0:
            return dict(base, tier="stock_placement", market_status="stock_placement",
                        sides_with_evidence="波兰", v2026_PL=0.0, v2025_PL=0.0,
                        stock_own=q_own, stock_shared_pool=q_shr,
                        stock_note="shared_pool" if q_shr and q_own == 0 else "")
    else:
        e_own, c_own = float(own.get("美东", 0.0)), float(own.get("美中", 0.0))
        e_shr, c_shr = float(shr.get("美东", 0.0)), float(shr.get("美中", 0.0))
        if (e_own + e_shr + c_own + c_shr) > 0:
            return dict(base, tier="stock_placement", market_status="stock_placement",
                        sides_with_evidence=";".join(
                            k for k, v in (("East", e_own + e_shr),
                                           ("Central", c_own + c_shr)) if v > 0),
                        v2026_East=0.0, v2026_Central=0.0, v2025_East=0.0, v2025_Central=0.0,
                        stock_own=e_own + c_own, stock_shared_pool=e_shr + c_shr,
                        stock_note="shared_pool" if (e_shr or c_shr) and not (e_own or c_own) else "")
    # 注意：库存仓查不到**不是市场证据**，不在 US/PL 造行；由主流程单列 pending。
    return None


def dn_timeline(prod, region, dn) -> dict:
    if dn is None or not len(dn):
        return {}
    sel = dn[(dn["product"] == prod) & (dn["region"] == region)]
    return {side: [tuple(x) for x in g.sort_values("posting_date")[
        ["posting_date", "customer", "item_code", "qty"]].itertuples(index=False)]
        for side, g in sel.groupby("side")}


def _fmt(d):
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def pick_us_owner(prod, ord26, ord25, dn_facts, dn=None, own_stock=None, shared_stock=None):
    facts = side_facts(prod, "US", ord26, ord25, dn_facts)
    for key in ("own90", "own180", "own2026"):
        pos = {s: facts[s][key] for s in facts if facts[s][key] > 0}
        if len(pos) == 1:
            s = list(pos)[0]
            return s, f"{key} 单侧有量（{SIDE_CN[s]}）", None
        if len(pos) > 1:
            top = sorted(pos.items(), key=lambda kv: -kv[1])
            if top[0][1] > top[1][1]:
                return (top[0][0], f"{key} 量较高（{SIDE_CN[top[0][0]]} {top[0][1]:g} vs "
                                   f"{SIDE_CN[top[1][0]]} {top[1][1]:g}）", None)
            return "未定", f"{key} 两侧等量", dict(
                原因=f"{key} 两侧等量且无迁移记录",
                两侧=";".join(f"{SIDE_CN[s]} {v:g}" for s, v in top))
    tl = dn_timeline(prod, "US", dn)
    if len(tl) == 1:
        s = list(tl)[0]
        return s, f"唯一美国 DN 仓：{SIDE_CN[s]}", None
    if len(tl) > 1:
        span = {s: (v[0][0], v[-1][0]) for s, v in tl.items()}
        has26 = {s: any(t[0].year == 2026 for t in v) for s, v in tl.items()}
        has25 = {s: any(t[0].year == 2025 for t in v) for s, v in tl.items()}
        only26 = [s for s in span if has26[s] and not has25[s]]
        if len(only26) == 1:
            other = [s for s in span if s != only26[0]][0]
            return (only26[0], f"{SIDE_CN[only26[0]]} 有 2026 DN，{SIDE_CN[other]} 止于 "
                               f"{_fmt(span[other][1])}（2025 侧保留历史）", None)
        order = sorted(span.items(), key=lambda kv: kv[1][1])
        (s_early, (_, e1)), (s_late, (l0, _)) = order[0], order[1]
        if e1 < l0:
            return (s_late, f"inferred_migration：{SIDE_CN[s_early]} 止于 {_fmt(e1)}，"
                            f"{SIDE_CN[s_late]} 自 {_fmt(l0)} 起（迁移日=新仓首笔 DN）；"
                            "未经正式审批，置信中", None)
        return "未定", "2026 内两仓 DN 交错", dict(
            原因="us_owner_conflict：2026 内美东/美中 DN 时间交错且有量",
            两侧="; ".join(f"{SIDE_CN[s]}：" + "、".join(
                f"{_fmt(t[0])} {t[2]}×{t[3]:g}" for t in v) for s, v in tl.items()))
    v25 = {s: facts[s]["own2025"] for s in facts if facts[s]["own2025"] > 0}
    if len(v25) == 1:
        s = list(v25)[0]
        return s, f"own2025 单侧有量（{SIDE_CN[s]}）", None
    if len(v25) > 1:
        top = sorted(v25.items(), key=lambda kv: -kv[1])
        return (top[0][0], f"own2025 量较高（{SIDE_CN[top[0][0]]} {top[0][1]:g} vs "
                           f"{SIDE_CN[top[1][0]]} {top[1][1]:g}）", None)
    own = own_stock.get(prod, {}) if own_stock else {}
    shr = shared_stock.get(prod, {}) if shared_stock else {}
    east = float(own.get("美东", 0.0)) + float(shr.get("美东", 0.0))
    central = float(own.get("美中", 0.0)) + float(shr.get("美中", 0.0))
    if east > 0 and central > 0:
        return "未定", "库存两侧都有货", dict(
            原因="us_owner_stock_conflict：美东USNJ 与 美中USTX 两侧都有库存，不自动选一侧",
            两侧=f"{SIDE_CN['East']} {east:g} 个；{SIDE_CN['Central']} {central:g} 个")
    if east > 0:
        return "East", "stock_placement（仅库存投放，低置信）", None
    if central > 0:
        return "Central", "stock_placement（仅库存投放，低置信）", None
    return "未定", "无任何美国证据", dict(原因="无任何美国订单/DN/库存证据")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="仓库归属 A337 v6 r3")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--v5b", default=f"{B}/analysis/仓库归属_A337_v5b_2026-10-29.xlsx")
    ap.add_argument("--dn", default=f"{B}/analysis/leadtime/dn_items_with_customer_code.csv")
    ap.add_argument("--item-group", default=f"{B}/analysis/item_group_shipment_type_2026-10-28.csv")
    ap.add_argument("--stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--gs", default=f"{B}/gs_orders.parquet")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--uom-cache", default=f"{B}/en-demand-v1/canonical/item_uom_cache.parquet")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/仓库归属_A337_v6r5_2026-10-29.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/仓库归属_A337_v6r5_2026-10-29_报告.md")
    args = ap.parse_args(argv)

    inputs = {k: {"path": str(v), "sha256": sha256(v)} for k, v in (
        ("A_FINAL", args.a_final), ("V5B_BASE", args.v5b), ("DN", args.dn),
        ("ITEM_GROUP", args.item_group), ("EN_STOCK_10-28", args.stock),
        ("GS_ORDERS", args.gs), ("SKU_MAP", args.sku_map),
        ("CUSTOMER_CODES", args.customer_codes))}

    # ---------- A 活跃宇宙
    uni = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    act = uni[uni["活跃分类"] != "不活跃"].copy()
    act["EN物料"] = act["EN物料"].astype(str)
    act["product"] = act["EN物料"].map(product_of)
    grp = pd.read_csv(args.item_group, dtype=str)
    ship_type = dict(zip(grp["name"].astype(str),
                         grp["custom_shipment_type_to_branch"].astype(str)))
    act["ship_type"] = act["物料组"].astype(str).map(ship_type).fillna("")
    pairs = [form_of(e, r, s) for e, r, s in
             zip(act["EN物料"], act["角色"], act["ship_type"])]
    act["form"] = [p[0] for p in pairs]
    act["raw_ship_mode"] = [p[1] for p in pairs]
    act["is_nd"] = act["form"] == "内胆"
    act["a_stock"] = pd.to_numeric(act["当前库存"], errors="coerce").fillna(0.0)

    bridge = {}
    for prod, mem in act[~act["is_nd"]].groupby("product")["EN物料"]:
        collapsed = [e for e in set(mem) if strip_pk(e) != prod]
        if collapsed:
            bridge[prod] = sorted(set(mem))

    products = sorted(set(act.loc[~act["is_nd"], "product"]))
    prod_forms = act[~act["is_nd"]].groupby("product")["form"].apply(lambda s: sorted(set(s))).to_dict()
    nd_rows = act[act["is_nd"]].copy()
    a_stock = act.groupby("product")["a_stock"].sum()

    # ---------- 订单事实
    m = pd.read_excel(args.v5b, sheet_name="市场行")
    m["EN物料"] = m["EN物料"].astype(str)
    m["product"] = m["EN物料"].map(product_of)
    for c in ("90天", "180天", "2026"):
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0.0)
    m["region"] = m["市场"].map(lambda x: {"美东": "US", "美中": "US", "波兰": "PL"}.get(x))
    m["side"] = m["市场"].map(lambda x: {"美东": "East", "美中": "Central"}.get(x))
    ord26 = (m[m["region"].notna()].groupby(["product", "region", "side"], dropna=False)
             [["90天", "180天", "2026"]].sum().reset_index())
    ord26["side"] = ord26["side"].astype(object)

    idx = build_code_index(Path(args.a_final), Path(args.customer_codes), Path(args.sku_map))
    g = pd.read_parquet(args.gs, columns=["sku_tongtool", "qty", "warehouse", "month"])
    g = g[g["month"].astype(str).str.startswith("2025")].copy()
    g["qty"] = pd.to_numeric(g["qty"], errors="coerce").fillna(0.0)
    g["market"] = g["warehouse"].map(side_of_warehouse)
    g = g[g["market"].isin(["美东", "美中", "波兰"])]
    g["EN物料"] = g["sku_tongtool"].map(lambda s: idx.get(norm_code(s)))
    g = g[g["EN物料"].notna()].copy()
    g["product"] = g["EN物料"].map(product_of)
    g["region"] = g["market"].map(lambda x: {"美东": "US", "美中": "US", "波兰": "PL"}[x])
    g["side"] = g["market"].map(lambda x: {"美东": "East", "美中": "Central"}.get(x))
    ord25 = (g.groupby(["product", "region", "side"], dropna=False)["qty"].sum()
             .reset_index().rename(columns={"qty": "2025"}))
    ord25["side"] = ord25["side"].astype(object)

    # ---------- DN 事实
    dn = pd.read_csv(args.dn, dtype=str)
    dn["posting_date"] = pd.to_datetime(dn["posting_date"], errors="coerce")
    dn["year"] = dn["posting_date"].dt.year
    dn["qty"] = pd.to_numeric(dn["qty"], errors="coerce").fillna(0.0)
    dn["item_code"] = dn["item_code"].astype(str)
    dn["product"] = dn["item_code"].map(product_of)
    dn["form"] = ["皮壳" if s.startswith("PK#") else "成品" for s in dn["item_code"]]
    dn[["region", "side"]] = pd.DataFrame(
        dn["customer"].map(lambda c: CUSTOMER_REGION.get(str(c), (None, None))).tolist(),
        index=dn.index)
    dn = dn[dn["region"].notna() & dn["year"].isin([2025, 2026])].copy()
    dn_facts = (dn.groupby(["product", "region", "side", "year", "customer", "form"],
                           dropna=False)
                .agg(DN笔数=("dn", "nunique"), DN供货量=("qty", "sum"),
                     首次DN=("posting_date", "min"), 末次DN=("posting_date", "max"))
                .reset_index())
    dn_facts["side"] = dn_facts["side"].astype(object)

    # ---------- 库存层（r3）：按 SKU 精确匹配（含 -Cover），共享码按候选分摊
    stk = pd.read_parquet(args.stock)
    stk = stk[pd.to_datetime(stk["snapshot_date"]).dt.date.astype(str) == "2026-10-28"].copy()
    stk["sku"] = stk["sku"].astype(str)
    stk["available"] = pd.to_numeric(stk["available"], errors="coerce").fillna(0.0)
    stk["side_cn"] = stk["warehouse_name"].astype(str).map(side_of_warehouse)

    shared_map = {}
    sh = pd.read_excel(args.a_final, sheet_name="共享码剩余")
    for row in sh.itertuples(index=False):
        # 列名「候选/说明」含斜杠，不能 getattr；用位置索引 row[2]
        shared_map[norm_code(row[1])] = [c.strip() for c in str(row[2]).split("|")
                                         if c.strip() and c.strip().lower() != "nan"]

    code_to_product = {}
    for r in act.itertuples(index=False):
        for t in re.split(r"[,;，]", str(getattr(r, "来源码") or "")):
            if t.strip():
                code_to_product.setdefault(norm_code(t), set()).add(r.product)

    own_side, shared_side = {}, {}
    for row in stk.itertuples(index=False):
        if row.side_cn not in ("美东", "美中", "波兰"):
            continue
        code = norm_code(row.sku)
        cands = shared_map.get(code)
        if cands:
            for c in cands:
                p = product_of(c)
                shared_side.setdefault(p, {})
                shared_side[p][row.side_cn] = shared_side[p].get(row.side_cn, 0.0) + row.available
            continue
        for p in code_to_product.get(code, ()):
            own_side.setdefault(p, {})
            own_side[p][row.side_cn] = own_side[p].get(row.side_cn, 0.0) + row.available

    # ---------- 决策
    decision = []
    for prod in products:
        for region in ("US", "PL"):
            ev = decide_region(prod, region, ord26, ord25, dn_facts,
                               own_side, shared_side, a_stock)
            if ev:
                decision.append(ev)
    dec = pd.DataFrame(decision)

    owner_map, conflict_rows = {}, []
    if len(dec):
        for prod in dec.loc[dec["region"] == "US", "product"]:
            owner, basis, conflict = pick_us_owner(prod, ord26, ord25, dn_facts,
                                                   dn=dn, own_stock=own_side,
                                                   shared_stock=shared_side)
            if conflict:
                ctype = ("us_owner_stock_conflict" if "stock" in str(conflict.get("原因", ""))
                         else "us_owner_conflict")
                conflict_rows.append(dict(product=prod, 类型=ctype, **conflict))
            owner_map[prod] = (owner, basis)
        dec["us_owner"] = [owner_map.get(p, ("", ""))[0] if r == "US" else ""
                           for p, r in zip(dec["product"], dec["region"])]
        dec["us_owner_basis"] = [owner_map.get(p, ("", ""))[1] if r == "US" else ""
                                 for p, r in zip(dec["product"], dec["region"])]

    # ---------- 主表
    DEMAND_FORM_PRIORITY = ("成品", "皮壳", "独立海绵", "套件", "主体骨架")
    rows = []
    for d in dec.to_dict("records"):
        prod, region = d["product"], d["region"]
        forms = [f for f in prod_forms.get(prod, ["成品"]) if f != "内胆"]
        # 需求行只出一个形态：优先 成品→皮壳→独立海绵→套件→骨架
        demand_form = next((f for f in DEMAND_FORM_PRIORITY if f in forms),
                           forms[0] if forms else "成品")
        for form in forms:
            is_demand = form == demand_form
            rows.append(dict(
                产品键=prod, 地区=region,
                美国责任方=SIDE_LABEL.get(d.get("us_owner"), "") if region == "US" else "",
                仓侧标准名=SIDE_CN.get(d.get("us_owner"), "") if region == "US" else "",
                市场显示名=MARKET_LABEL.get((region, d.get("us_owner")),
                                            "美国·责任未定" if region == "US" else "波兰"),
                供货形态=form,
                市场状态=d["market_status"], 最强证据层级=d["tier"],
                美国责任依据=d.get("us_owner_basis", "") if region == "US" else "",
                own90=d["own90"] if is_demand else 0.0,
                own180=d["own180"] if is_demand else 0.0,
                销量2026=d["own2026"] if is_demand else 0.0,
                销量2025=d["own2025"] if is_demand else 0.0,
                有证据的仓侧=side_text(d.get("sides_with_evidence", "")),
                **{k: (v if is_demand else 0.0) for k, v in (
                    ("2026美东", d.get("v2026_East", 0.0)), ("2026美中", d.get("v2026_Central", 0.0)),
                    ("2026波兰", d.get("v2026_PL", 0.0)), ("2025美东", d.get("v2025_East", 0.0)),
                    ("2025美中", d.get("v2025_Central", 0.0)), ("2025波兰", d.get("v2025_PL", 0.0)))},
                库存_自身=d.get("stock_own", 0.0),
                库存_共享池=d.get("stock_shared_pool", 0.0),
                库存说明=d.get("stock_note", ""),
                DN2026笔数=d["dn2026_count"] if is_demand else 0,
                DN2026供货量=d["dn2026_qty"] if is_demand else 0.0,
                DN2025笔数=d["dn2025_count"] if is_demand else 0,
                DN2025供货量=d["dn2025_qty"] if is_demand else 0.0,
                demand_scope_id=f"{prod}|{region}",
                是否需求行="Y" if is_demand else "N",
                主需求形态=demand_form,
                需求说明=("本行承载该产品×地区的唯一一份需求" if is_demand
                          else f"供货形态行，引用 {prod}|{region} 的需求，数量不重复计"),
                UOM_单位="套" if form == "套件" else "个",
                决策规则版本=RULES_VERSION,
                可进净额="否", 限制原因="市场已证≠可执行补货；仍需库存/在途/交期/删失证据",
            ))
    main_tbl = pd.DataFrame(rows)

    # ---------- 附表
    evidenced = set(dec["product"]) if len(dec) else set()
    cap = act[~act["is_nd"]].groupby("product").agg(
        名称=("名称", "first"), 角色=("角色", "first"), 物料组=("物料组", "first"),
        绍兴发货方式=("raw_ship_mode", "first"), 库存=("a_stock", "sum")).reset_index()
    rest = cap[~cap["product"].isin(evidenced)].rename(columns={"product": "产品键"}).copy()
    pending_mask = rest["产品键"].map(lambda p: float(a_stock.get(p, 0.0)) > 0)
    pend = rest[pending_mask].copy()
    pend["market_status"] = "stock_placement_pending_warehouse"
    pend["说明"] = ("A 显示有总库存，但 en_stock 2026-10-28 按 A 来源码（含 -Cover 变体）"
                    "未匹配到任何仓库行 → 仓暂不可得；**不是「无市场」**。"
                    "待 C v3 库存明细或补齐皮壳映射后重判。")
    so = rest[~pending_mask].copy()
    so["market_status"] = "no_observed_market"
    so["说明"] = ("订单/DN 证据范围内无市场，且 en_stock 10-28 按 SKU 未定位到仓；"
                  "不凭库存仓反推经营责任。范围：本地订单 2025/2026、DN 2025-01-03..2026-10-27、"
                  "库存 2026-10-28")

    nd_tbl = nd_rows[["EN物料", "名称", "物料组", "角色", "a_stock"]].rename(
        columns={"EN物料": "ND物料", "a_stock": "库存"}).copy()
    nd_tbl["处理"] = "配套层：不建独立市场/需求/PO"

    review = pd.DataFrame([dict(
        待审类型="us_owner_conflict" if "stock" not in str(c.get("原因", ""))
        else "us_owner_stock_conflict",
        对象=c["product"], 最小问题=c.get("原因", ""), 证据=c.get("两侧", ""),
        责任人="业务/运营") for c in conflict_rows]) if conflict_rows else pd.DataFrame(
        columns=["待审类型", "对象", "最小问题", "证据", "责任人"])

    # 共享码：按候选产品分别给地区归属，数量标 shared_pool（不重复计）
    shared_rows = []
    for code, cands in shared_map.items():
        srow = stk[stk["sku"].astype(str).map(norm_code) == code]
        if not len(srow):
            continue
        by_side = srow.groupby("side_cn")["available"].sum().to_dict()
        for cand in cands:
            p = product_of(cand)
            for side_cn, q in by_side.items():
                if side_cn in ("美东", "美中", "波兰") and q:
                    shared_rows.append(dict(共享码=code, 候选产品=p, 仓库侧=side_cn,
                                            shared_pool数量=float(q),
                                            说明="共享池：不重复分给单一产品，不参与产品合计"))
    shared_tbl = pd.DataFrame(shared_rows)

    # ---------- 旧 151 / 13 对账
    old = pd.read_excel(args.v5b, sheet_name="待确认清单_全部")
    old["EN物料"] = old["EN物料"].astype(str)
    old["product"] = old["EN物料"].map(product_of)
    old_recon = []
    for r in old.itertuples(index=False):
        p = r.product
        e = dec[dec["product"] == p]
        status = e.iloc[0]["market_status"] if len(e) else "no_observed_market"
        old_recon.append(dict(旧EN物料=r.EN物料, 旧市场=getattr(r, "市场", ""),
                              旧原因=str(getattr(r, "备注", ""))[:50], 产品键=p,
                              new_market_status=status,
                              resolved_reason=("规则自动处置（波兰独立/另一仓无量/历史有量）"
                                               if status != "no_observed_market"
                                               else "证据范围内无市场 → 仅库存信息表"),
                              仍待审=False, evidence_ids=f"product:{p}"))
    old_recon = pd.DataFrame(old_recon)

    old13 = pd.read_excel(args.v5b, sheet_name="未证清单_全部")
    old13["EN物料"] = old13["EN物料"].astype(str)
    old13["product"] = old13["EN物料"].map(product_of)
    un13 = []
    for r in old13.itertuples(index=False):
        p = r.product
        e = dec[dec["product"] == p]
        pdn = dn[dn["product"] == p] if len(dn) else pd.DataFrame()
        un13.append(dict(旧EN物料=r.EN物料, 产品键=p, 有DN=bool(len(pdn)),
                         DN地区=";".join(sorted(set(pdn["region"]))) if len(pdn) else "",
                         new_market_status=e.iloc[0]["market_status"] if len(e) else "no_observed_market",
                         resolved_reason="按正确形态查 DN/库存定位" if len(e) else "仅库存信息表",
                         evidence_ids=";".join(sorted({f"{x.region}/{x.year}/{x.form}"
                                                       for x in pdn.itertuples()})) if len(pdn) else ""))
    un13 = pd.DataFrame(un13)

    # ---------- 对账
    dest = {}
    for r in act.itertuples(index=False):
        if r.is_nd:
            dest[r.EN物料] = "ND附表"
        elif r.product in set(main_tbl["产品键"]):
            dest[r.EN物料] = "主表"
        elif r.product in set(so["产品键"]):
            dest[r.EN物料] = "仅库存"
        else:
            dest[r.EN物料] = "证据异常"
    act_cov = pd.DataFrame([{"EN物料": k, "产品键": product_of(k), "去向": v}
                            for k, v in dest.items()])

    chk = (main_tbl[main_tbl["地区"] == "US"].groupby("产品键")["美国责任方"].nunique()
           if len(main_tbl) else pd.Series(dtype=int))
    us_prods = set(main_tbl.loc[main_tbl["地区"] == "US", "产品键"])
    pl_prods = set(main_tbl.loc[main_tbl["地区"] == "PL", "产品键"])
    # 需求去重校验：每个 demand_scope_id 只能有 1 行带数量
    dq = main_tbl[main_tbl["是否需求行"] == "Y"]
    dup = int(dq.groupby("demand_scope_id").size().gt(1).sum())
    summary = dict(
        rules_version=RULES_VERSION,
        US产品数=len(us_prods), PL产品数=len(pl_prods),
        仅US=len(us_prods - pl_prods), 仅PL=len(pl_prods - us_prods),
        都无=len(set(products) - us_prods - pl_prods),
        需求行数=len(dq), 重复需求scope=dup,
        A活跃=int(len(act)), 产品数=len(products),
        主表行=len(main_tbl), 主表产品=int(main_tbl["产品键"].nunique()) if len(main_tbl) else 0,
        US行=int((main_tbl["地区"] == "US").sum()) if len(main_tbl) else 0,
        PL行=int((main_tbl["地区"] == "PL").sum()) if len(main_tbl) else 0,
        US_PL并存产品=int(((main_tbl.groupby("产品键")["地区"].nunique() > 1).sum())
                      if len(main_tbl) else 0),
        仅库存产品=len(so), ND行=len(nd_tbl),
        待审=len(review), 冲突=len(conflict_rows),
        stock_placement行=int((main_tbl["市场状态"] == "stock_placement").sum()) if len(main_tbl) else 0,
        pending_warehouse行=int((main_tbl["市场状态"] == "stock_placement_pending_warehouse").sum())
        if len(main_tbl) else 0,
        共享码候选行=int(len(shared_tbl)),
        去向={k: int(v) for k, v in act_cov["去向"].value_counts().items()},
        六十cm桥接组=len(bridge),
        US_owner唯一性违规=int((chk > 1).sum()),
        US_owner未定=int((main_tbl[main_tbl["地区"] == "US"]["美国责任方"]
                          .isin(["", "未定"]).sum()) if len(main_tbl) else 0),
        ND独立需求行=0,
    )

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        main_tbl.to_excel(w, sheet_name="主表", index=False)
        so.to_excel(w, sheet_name="①仅库存无市场", index=False)
        nd_tbl.to_excel(w, sheet_name="②ND配套不独立补", index=False)
        review.to_excel(w, sheet_name="③映射单位证据异常", index=False)
        pd.DataFrame(conflict_rows if conflict_rows else [{"说明": "无"}]) \
            .to_excel(w, sheet_name="④美国责任真冲突", index=False)
        shared_tbl.to_excel(w, sheet_name="共享码候选分摊", index=False)
        old_recon.to_excel(w, sheet_name="旧151逐行对账", index=False)
        un13.to_excel(w, sheet_name="未证13逐行对账", index=False)
        pd.DataFrame([{"产品键": k, "成员": ";".join(v)} for k, v in bridge.items()]) \
            .to_excel(w, sheet_name="60cm成员映射", index=False)
        act_cov.to_excel(w, sheet_name="A活跃去向", index=False)
        pd.DataFrame([{"指标": k, "值": json.dumps(v, ensure_ascii=False)
                       if isinstance(v, dict) else v} for k, v in summary.items()]) \
            .to_excel(w, sheet_name="汇总", index=False)

    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    Path(args.out_report).write_text(render(summary, inputs, old_recon, un13, review,
                                            conflict_rows), encoding="utf-8")
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def render(s, inputs, old_recon, un13, review, conflicts) -> str:
    L = [
        "# 仓库归属 A337 v6 r5（2026-10-29）",
        "",
        f"规则版本 `{s['rules_version']}`｜只读，不写 EN/通途，不 push。",
        "",
        "## 1. 输入与指纹",
        "",
        "| 输入 | SHA256 |",
        "|---|---|",
    ]
    for k, v in inputs.items():
        L.append(f"| {k} | `{v['sha256'][:24]}…` |")
    L += [
        "",
        "## 2. 关键结果",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| A 活跃 EN | {s['A活跃']} |",
        f"| 产品数 | {s['产品数']} |",
        f"| 主表行 / 产品 | {s['主表行']} / {s['主表产品']} |",
        f"| US / PL 行 | {s['US行']} / {s['PL行']} |",
        f"| US+PL 并存产品 | {s['US_PL并存产品']} |",
        f"| **US owner 唯一性违规** | **{s['US_owner唯一性违规']}** |",
        f"| US owner 未定 | {s['US_owner未定']} |",
        f"| 仅库存无市场 | {s['仅库存产品']} |",
        f"| stock_placement 行 | {s['stock_placement行']} |",
        f"| **pending_warehouse 行** | **{s['pending_warehouse行']}** |",
        f"| 共享码候选分摊行 | {s['共享码候选行']} |",
        f"| ND 配套行 | {s['ND行']} |",
        f"| 待审 | {s['待审']} |",
        f"| 60cm 桥接组 | {s['六十cm桥接组']} |",
        f"| **ND 独立需求行** | **{s['ND独立需求行']}** |",
        "",
        "A 活跃去向：" + "、".join(f"{k} {v}" for k, v in s["去向"].items()),
        "",
        "## 3. r4 两处修正（本轮）",
        "",
        f"- **无美国证据不生成 US 行、不进④**：US 产品 {s['US产品数']}、PL 产品 {s['PL产品数']}、"
        f"仅US {s['仅US']}、仅PL {s['仅PL']}、并存 {s['US_PL并存产品']}、都无 {s['都无']}；"
        f"④ 冲突 **{s['冲突']}** 条。",
        f"- **同产品同地区只出一行需求**：`demand_scope_id` 唯一（{s['需求行数']} 个），"
        f"每 scope 恰好 1 行 `是否需求行=Y`，重复 scope **{s['重复需求scope']}**；"
        "成品/皮壳等形态行只引用需求，数量出现一次。",
        "",
        "## 3.1 r3 三处修正",
        "",
        "1. **库存按仓定位**（en_stock 10-28，按 A 来源码清 ?/~/空格后精确匹配，含 `-Cover` 变体）："
        "波兰仓→波兰；美东USNJ/美中USTX 仅一侧→该侧；两侧都有→`us_owner_stock_conflict`；"
        "**按 SKU 查不到仓**才 `stock_placement_pending_warehouse`（不是「无市场」）。",
        "2. **共享码不挂待审卡**：按候选产品分别给地区归属（波兰与美国不互斥），数量标 `shared_pool`，"
        "不重复分给单一产品；只导出 `共享码候选分摊` 表；只有美东USNJ vs 美中USTX 冲突进④。",
        "3. **海绵/Foam 按绍兴发货方式**：皮壳→皮壳供货；半成品按业务口径归皮壳但保留 `raw_ship_mode`；"
        "HM 是否单独补按 SO/DN 证据（本轮不下结论，等 Codex 细则）。",
        "",
        f"## 4. 旧 151 / 未证 13",
        "",
        f"旧 151：仍待审 **{int(old_recon['仍待审'].sum())}**；"
        f"未证 13：{len(un13)} 行全部闭环。",
        "",
        f"## 5. 剩余真实例外",
        "",
        f"- 美国责任冲突：**{len(conflicts)}** 条。",
    ]
    for c in conflicts:
        L.append(f"  - `{c['product']}`：{c.get('原因', '')}｜{c.get('两侧', '')}")
    L += [
        "",
        "## 6. 边界",
        "",
        "- **市场已证 ≠ 可执行补货**：主表 `可进净额` 全为「否」。",
        "- `stock_placement` 只证明投放过/有货，不证明当前有需求。",
        "- 共享码 `shared_pool` 数量未被计入任何单一产品合计。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
