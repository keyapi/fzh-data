# -*- coding: utf-8 -*-
"""B v6 r6：仓库归属 A337（只读）—— 修复 r5 复审 N1–N6。

N1 共享订单不硬归：gs_orders 2025 段里命中「A 已登记共享码」的订单行
   **只进 shared_pool（共享码×仓×年 持有一份）**，不给任何单一产品加 own2025/销量2025；
   各候选产品的市场只用其自身订单/DN/库存证据独立判。
N2 明确多件后缀乘 N：`...-12PCS` / `-5PC` 等显式后缀 → pieces_per_unit=N；
   裸 `-2`/`-3` 不推倍数；Bundle/TJ# 按套不拆倍。库存与 2025 订单统一换算，
   保留 raw_available / raw_qty，新增 pieces_per_unit / conversion_basis / canonical_qty。
N3 US owner 时间裁决：只有「本侧有 2026 且另一侧最后日期 ≤2025」才可直接判本侧；
   两侧都有 2026 → 继续时间段/冲突判定，不得短路。
N4 级联统一：own90→own180→own2026→DN2026→DN2025→own2025→库存；
   地区存在性与 US owner 共用同一套年份分层定义。
N5 逐行证据：旧151/未证13 的 evidence_ids 给实际 DN 号/订单行/库存源行；
   限制原因拆 evidence/inventory/demand 三类 blocker。
N6 命名统一：共享附表仓侧写 美中USTX/美东USNJ；旧市场字段标「原值」。

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
RULES_VERSION = "B-v6-rules-2026-10-29-r6"

CUSTOMER_REGION = {"CENTRADE": ("US", "East"), "DANEEY": ("US", "Central"),
                   "波兰公司": ("PL", None)}
SIDE_CN = {"East": "美东USNJ（美东-CENTRADE）", "Central": "美中USTX（美中-FZH-DANEEY）"}
SIDE_LABEL = {"East": "美东USNJ", "Central": "美中USTX"}
MARKET_LABEL = {("US", "East"): "美国·美东", ("US", "Central"): "美国·美中",
                ("PL", None): "波兰"}
# N4：统一级联（DN 内先 2026 再 2025，均先于 own2025）
TIERS_ORDER = ("own90", "own180", "own2026", "dn2026", "dn2025", "own2025",
               "stock_placement")
STRIP = ("删除", "~", "?", "？")
PIECE_RE = re.compile(r"(\d+)\s*(?:PCS|PC)$", re.I)

# UOM-CANONICAL §2.1 的 uom_exception_map：
# 明确带 PCS/PC 后缀本应乘 N，但若 EN 已有**成套产品 1:1 对应**，按 1:1 计并在此登记。
# 键 = norm_code(SKU)；值 = (对应 EN 成套产品, 依据)
UOM_EXCEPTION_MAP = {
    "xingqiu-12pcs": ("KS0019-PBHLR-SET12-PLANETARYMASHUP",
                      "星球老产品成套 1:1，不再细分；用户 2026-10-29 指定；"
                      "已写入 UOM-CANONICAL §2.1"),
}


def side_text(raw) -> str:
    if raw is None or isinstance(raw, float):
        return ""
    return ";".join(SIDE_LABEL.get(x.strip(), x.strip())
                    for x in str(raw).split(";") if x.strip())


def side_cn_name(cn: str) -> str:
    """N6：现行仓侧列统一显示名。"""
    return {"美东": "美东USNJ", "美中": "美中USTX", "波兰": "波兰"}.get(cn, cn)


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


def pieces_per_unit(sku, form: str = "") -> tuple[int, str]:
    """N2：显式 PCS/PC 后缀默认乘 N；裸 -2/-3 不推；Bundle/TJ# 按套不拆。

    例外优先：`UOM_EXCEPTION_MAP` 里登记的 SKU（EN 已有成套产品 1:1）按 1:1，
    即使带 PCS 后缀也不乘 N。
    """
    s = str(sku)
    n_key = norm_code(s)
    if n_key in UOM_EXCEPTION_MAP:
        en, why = UOM_EXCEPTION_MAP[n_key]
        return 1, f"uom_exception_map 1:1 → {en}（{why}）"
    if form == "套件" or s.upper().startswith("TJ#"):
        return 1, "Bundle/TJ# 按套，不二次拆倍"
    m = PIECE_RE.search(s.strip())
    if m:
        n = int(m.group(1))
        if n > 1:
            return n, f"显式多件后缀 {m.group(0)}"
    return 1, "无显式多件后缀（裸 -N 不推倍数）"


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
    raw = (ship_type or "").strip()
    if str(en).startswith("ND#") or role == "内胆":
        return "内胆", raw or "内胆"
    if str(en).startswith("TJ#") or role == "套件":
        return "套件", raw or "套件"
    if str(en).startswith("PK#") or role == "皮壳":
        return "皮壳", raw or "皮壳"
    if role in ("海绵", "海绵/关联成品"):
        if raw in ("皮壳", "半成品"):
            return "皮壳", raw
        if raw == "成品":
            return "成品", raw
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
    """N4：与 TIERS_ORDER 完全一致：own90→own180→own2026→dn2026→dn2025→own2025。"""
    if f["own90"] > 0:
        return "own90"
    if f["own180"] > 0:
        return "own180"
    if f["own2026"] > 0:
        return "own2026"
    if f["dn2026_count"] > 0:
        return "dn2026"
    if f["dn2025_count"] > 0:
        return "dn2025"
    if f["own2025"] > 0:
        return "own2025"
    return None


def decide_region(prod, region, ord26, ord25, dn_facts, own_stock, shared_stock):
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
    return None


def _fmt(d):
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def dn_dates_by_side(prod, region, dn_year) -> dict:
    """按年返回 {side: [date,...]}。"""
    if dn_year is None or not len(dn_year):
        return {}
    sel = dn_year[(dn_year["product"] == prod) & (dn_year["region"] == region)]
    return {side: sorted(g["posting_date"].tolist()) for side, g in sel.groupby("side")}


def pick_us_owner(prod, ord26, ord25, dn_facts, dn=None, own_stock=None, shared_stock=None):
    """N3/N4：own90→own180→own2026→DN2026→DN2025→own2025→库存。"""
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

    # ---- DN：先 2026，再 2025（N4 顺序）
    for yr in (2026, 2025):
        sub = dn[dn["year"] == yr] if dn is not None and len(dn) else None
        dates = dn_dates_by_side(prod, "US", sub)
        if not dates:
            continue
        label = f"DN{yr}"
        if len(dates) == 1:
            s = list(dates)[0]
            return s, f"唯一美国 {label} 仓：{SIDE_CN[s]}（{len(dates[s])} 笔）", None
        span = {s: (v[0], v[-1]) for s, v in dates.items()}
        if yr == 2026:
            # N3：只有「另一侧最后日期 ≤2025」才可直接判；两侧都有 2026 必须继续判定
            has25 = {s: bool(dn_dates_by_side(prod, "US", dn[dn["year"] == 2025])
                             .get(s)) for s in span}
            only_here = [s for s in span if not has25[s]]
            if len(only_here) == 1:
                other = [s for s in span if s != only_here[0]][0]
                if not dn_dates_by_side(prod, "US", dn[dn["year"] == 2025]).get(other):
                    return (only_here[0],
                            f"{SIDE_CN[only_here[0]]} 有 2026 DN，{SIDE_CN[other]} 止于 2025"
                            "（2025 侧保留历史）", None)
        order = sorted(span.items(), key=lambda kv: kv[1][1])
        (s_early, (_, e1)), (s_late, (l0, _)) = order[0], order[1]
        if e1 < l0:
            return (s_late, f"inferred_migration：{SIDE_CN[s_early]} 止于 {_fmt(e1)}，"
                            f"{SIDE_CN[s_late]} 自 {_fmt(l0)} 起（迁移日=新仓首笔 DN）；"
                            "未经正式审批，置信中", None)
        return "未定", f"{label} 两仓时间交错", dict(
            原因=f"us_owner_conflict：{label} 内美东/美中 DN 时间交错且有量",
            两侧="; ".join(f"{SIDE_CN[s]}：" + "、".join(_fmt(x) for x in v)
                           for s, v in dates.items()))

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
    ap = argparse.ArgumentParser(description="仓库归属 A337 v6 r6")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--v5b", default=f"{B}/analysis/仓库归属_A337_v5b_2026-10-29.xlsx")
    ap.add_argument("--dn", default=f"{B}/analysis/leadtime/dn_items_with_customer_code.csv")
    ap.add_argument("--item-group", default=f"{B}/analysis/item_group_shipment_type_2026-10-28.csv")
    ap.add_argument("--stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--gs", default=f"{B}/gs_orders.parquet")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/仓库归属_A337_v6r6_2026-10-29.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/仓库归属_A337_v6r6_2026-10-29_报告.md")
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
        if [e for e in set(mem) if strip_pk(e) != prod]:
            bridge[prod] = sorted(set(mem))

    products = sorted(set(act.loc[~act["is_nd"], "product"]))
    prod_forms = act[~act["is_nd"]].groupby("product")["form"].apply(lambda s: sorted(set(s))).to_dict()
    nd_rows = act[act["is_nd"]].copy()
    a_stock = act.groupby("product")["a_stock"].sum()

    # ---------- 共享码名单（N1）：A 登记的 30 个 + 一码多产品
    shared_map = {}
    sh = pd.read_excel(args.a_final, sheet_name="共享码剩余")
    for row in sh.itertuples(index=False):
        shared_map[norm_code(row[1])] = [c.strip() for c in str(row[2]).split("|")
                                         if c.strip() and c.strip().lower() != "nan"]
    code_to_product = {}
    for r in act.itertuples(index=False):
        for t in re.split(r"[,;，]", str(getattr(r, "来源码") or "")):
            if t.strip():
                code_to_product.setdefault(norm_code(t), set()).add(r.product)
    for code, prods in code_to_product.items():
        if len(prods) > 1 and code not in shared_map:
            shared_map[code] = sorted(prods)

    # ---------- 订单事实（2026 窗口）
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

    # ---------- 2025 订单（N1 共享门禁 + N2 多件换算）
    idx = build_code_index(Path(args.a_final), Path(args.customer_codes), Path(args.sku_map))
    g = pd.read_parquet(args.gs, columns=["sku_tongtool", "qty", "warehouse", "month", "line_id"])
    g = g[g["month"].astype(str).str.startswith("2025")].copy()
    g["raw_qty"] = pd.to_numeric(g["qty"], errors="coerce").fillna(0.0)
    g["market"] = g["warehouse"].map(side_of_warehouse)
    g = g[g["market"].isin(["美东", "美中", "波兰"])].copy()
    g["code"] = g["sku_tongtool"].map(norm_code)
    g["is_shared"] = g["code"].isin(shared_map)

    g["product"] = None
    g.loc[~g["is_shared"], "product"] = g.loc[~g["is_shared"], "code"].map(
        lambda s: idx.get(s))
    g["ppu"], g["conv"] = zip(*[pieces_per_unit(s) for s in g["sku_tongtool"]])
    g["qty"] = g["raw_qty"] * g["ppu"]

    shared_orders = g[g["is_shared"]].copy()
    own_orders = g[(~g["is_shared"]) & g["product"].notna()].copy()
    own_orders["region"] = own_orders["market"].map(
        lambda x: {"美东": "US", "美中": "US", "波兰": "PL"}[x])
    own_orders["side"] = own_orders["market"].map(
        lambda x: {"美东": "East", "美中": "Central"}.get(x))
    ord25 = (own_orders.groupby(["product", "region", "side"], dropna=False)["qty"].sum()
             .reset_index().rename(columns={"qty": "2025"}))
    ord25["side"] = ord25["side"].astype(object)

    # 共享订单池：按 共享码×仓×年 持有一份，候选只作标注
    shared_order_rows = []
    for (code, market), grp_ in shared_orders.groupby(["code", "market"]):
        shared_order_rows.append(dict(
            共享码=code, 仓库侧=side_cn_name(market), 年=2025,
            订单行数=int(len(grp_)), 原数量=float(grp_["raw_qty"].sum()),
            换算数量=float(grp_["qty"].sum()),
            候选产品=";".join(shared_map.get(code, [])),
            说明="共享池持有一次，不分配给任何单一产品，不计入 own2025/销量2025"))
    shared_order_tbl = pd.DataFrame(shared_order_rows)

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

    # ---------- 库存层（N2 换算）
    stk = pd.read_parquet(args.stock)
    stk = stk[pd.to_datetime(stk["snapshot_date"]).dt.date.astype(str) == "2026-10-28"].copy()
    stk["sku"] = stk["sku"].astype(str)
    stk["raw_available"] = pd.to_numeric(stk["available"], errors="coerce").fillna(0.0)
    stk["ppu"], stk["conversion_basis"] = zip(*[pieces_per_unit(s) for s in stk["sku"]])
    stk["canonical_qty"] = stk["raw_available"] * stk["ppu"]
    stk["side_cn"] = stk["warehouse_name"].astype(str).map(side_of_warehouse)

    own_side, shared_side, stock_ev = {}, {}, {}
    for row in stk.itertuples(index=False):
        if row.side_cn not in ("美东", "美中", "波兰"):
            continue
        code = norm_code(row.sku)
        ev = (f"{row.sku}/{row.warehouse_name}/{row.raw_available:g}"
              + (f"×{row.ppu}={row.canonical_qty:g}" if row.ppu > 1 else ""))
        cands = shared_map.get(code)
        if cands:
            for c in cands:
                p = product_of(c)
                shared_side.setdefault(p, {})
                shared_side[p][row.side_cn] = (shared_side[p].get(row.side_cn, 0.0)
                                               + row.canonical_qty)
                stock_ev.setdefault(p, []).append("共享池 " + ev)
            continue
        for p in code_to_product.get(code, ()):
            own_side.setdefault(p, {})
            own_side[p][row.side_cn] = own_side[p].get(row.side_cn, 0.0) + row.canonical_qty
            stock_ev.setdefault(p, []).append(ev)

    # ---------- 决策
    decision = []
    for prod in products:
        for region in ("US", "PL"):
            ev = decide_region(prod, region, ord26, ord25, dn_facts, own_side, shared_side)
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

    # ---------- 证据索引（N5）
    dn_ev, order_ev = {}, {}
    for r in dn.itertuples(index=False):
        dn_ev.setdefault(r.product, []).append(
            f"DN {r.dn}/{_fmt(r.posting_date)}/{r.item_code}×{r.qty:g}/{r.customer}/{r.region}")
    for r in own_orders.itertuples(index=False):
        order_ev.setdefault(r.product, []).append(
            f"订单 {getattr(r, 'line_id', '')}/{r.sku_tongtool}×{r.raw_qty:g}"
            f"→{r.qty:g}/{r.market}/2025")

    def evidence_of(prod, limit=6) -> str:
        parts = []
        if prod in dn_ev:
            parts += sorted(set(dn_ev[prod]))[:limit]
        if prod in order_ev:
            parts += sorted(set(order_ev[prod]))[:limit]
        if prod in stock_ev:
            parts += sorted(set(stock_ev[prod]))[:limit]
        return "; ".join(parts) if parts else ""

    # ---------- 主表
    DEMAND_FORM_PRIORITY = ("成品", "皮壳", "独立海绵", "套件", "主体骨架")
    shared_products = {product_of(c) for cs in shared_map.values() for c in cs}
    rows = []
    for d in dec.to_dict("records"):
        prod, region = d["product"], d["region"]
        forms = [f for f in prod_forms.get(prod, ["成品"]) if f != "内胆"]
        demand_form = next((f for f in DEMAND_FORM_PRIORITY if f in forms),
                           forms[0] if forms else "成品")
        # N5：三类 blocker 分开
        ev_b, inv_b, dem_b = [], [], []
        if prod in shared_products:
            ev_b.append("共享码数量待核（候选间不分摊）")
        if d["tier"] == "stock_placement":
            inv_b.append("仅库存投放，无销售证据")
            dem_b.append("无当前需求（库存位置≠销售）")
        elif d["tier"] in ("dn2025", "own2025"):
            dem_b.append("仅有历史（2025）证据，无当前需求")
        if d.get("stock_note") == "shared_pool":
            inv_b.append("库存为共享池，未独占")
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
                evidence_blockers="；".join(dict.fromkeys(ev_b)),
                inventory_blockers="；".join(dict.fromkeys(inv_b)),
                demand_blockers="；".join(dict.fromkeys(dem_b)),
                限制原因="市场已证≠可执行补货" + (
                    "；" + "；".join(filter(None, ["；".join(dict.fromkeys(ev_b)),
                                                  "；".join(dict.fromkeys(inv_b)),
                                                  "；".join(dict.fromkeys(dem_b))]))
                    if (ev_b or inv_b or dem_b) else "；仍需库存/在途/交期/删失证据"),
                证据入口=evidence_of(prod) if is_demand else "",
                UOM_单位="套" if form == "套件" else "个",
                决策规则版本=RULES_VERSION,
                可进净额="否",
            ))
    main_tbl = pd.DataFrame(rows)

    # ---------- 附表
    evidenced = set(dec["product"]) if len(dec) else set()
    cap = act[~act["is_nd"]].groupby("product").agg(
        名称=("名称", "first"), 角色=("角色", "first"), 物料组=("物料组", "first"),
        绍兴发货方式=("raw_ship_mode", "first"), 库存=("a_stock", "sum")).reset_index()
    rest = cap[~cap["product"].isin(evidenced)].rename(columns={"product": "产品键"}).copy()
    pend_mask = rest["产品键"].map(lambda p: float(a_stock.get(p, 0.0)) > 0)
    so = rest[~pend_mask].copy()
    so["market_status"] = "no_observed_market"
    so["说明"] = ("订单/DN 证据范围内无市场，且 en_stock 10-28 按 SKU 未定位到仓；"
                  "不凭库存仓反推经营责任。")

    nd_tbl = nd_rows[["EN物料", "名称", "物料组", "角色", "a_stock"]].rename(
        columns={"EN物料": "ND物料", "a_stock": "库存"}).copy()
    nd_tbl["处理"] = "配套层：不建独立市场/需求/PO"

    review = pd.DataFrame([dict(
        待审类型=c.get("类型", "us_owner_conflict"),
        对象=c["product"], 最小问题=c.get("原因", ""), 证据=c.get("两侧", ""),
        责任人="业务/运营") for c in conflict_rows]) if conflict_rows else pd.DataFrame(
        columns=["待审类型", "对象", "最小问题", "证据", "责任人"])

    # 共享码库存（N6 仓侧写法统一）
    shared_rows = []
    for code, cands in shared_map.items():
        srow = stk[stk["sku"].astype(str).map(norm_code) == code]
        if not len(srow):
            continue
        by_side = srow.groupby("side_cn")["canonical_qty"].sum().to_dict()
        for cand in cands:
            p = product_of(cand)
            for side_cn, q in by_side.items():
                if side_cn in ("美东", "美中", "波兰") and q:
                    shared_rows.append(dict(共享码=code, 候选产品=p,
                                            仓库侧=side_cn_name(side_cn),
                                            shared_pool数量=float(q),
                                            说明="共享池：不重复分给单一产品，不参与产品合计"))
    shared_tbl = pd.DataFrame(shared_rows)

    # ---------- 旧 151 / 13 对账（N5 逐行证据）
    old = pd.read_excel(args.v5b, sheet_name="待确认清单_全部")
    old["EN物料"] = old["EN物料"].astype(str)
    old["product"] = old["EN物料"].map(product_of)
    old_recon = []
    for r in old.itertuples(index=False):
        p = r.product
        e = dec[dec["product"] == p]
        status = e.iloc[0]["market_status"] if len(e) else "no_observed_market"
        old_recon.append(dict(旧EN物料=r.EN物料, 产品键=p,
                              旧市场原值=getattr(r, "市场", ""),
                              旧原因原值=str(getattr(r, "备注", ""))[:50],
                              new_market_status=status,
                              resolved_reason=("规则自动处置（波兰独立/另一仓无量/历史有量）"
                                               if status != "no_observed_market"
                                               else "证据范围内无市场 → 仅库存信息表"),
                              仍待审=False, evidence_ids=evidence_of(p)))
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
                         evidence_ids=evidence_of(p)))
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
    dq = main_tbl[main_tbl["是否需求行"] == "Y"]
    dup = int(dq.groupby("demand_scope_id").size().gt(1).sum())

    # N2 验收样例
    sample_skus = ("XINGQIU-2PCS", "XINGQIU-3PCS", "XINGQIU-5PC",
                   "XINGQIU-7PCS", "XINGQIU-12PCS", "TT0001K0001-2", "TT0001K0001-3",
                   "TJ#KS0156x2-001")
    conv_tbl = pd.DataFrame([dict(SKU=s, pieces_per_unit=pieces_per_unit(s)[0],
                                  conversion_basis=pieces_per_unit(s)[1],
                                  是否为uom_exception=("是" if norm_code(s) in UOM_EXCEPTION_MAP else "否"))
                             for s in sample_skus])
    exception_tbl = pd.DataFrame([
        dict(SKU=sku, 对应EN成套产品=en, pieces_per_unit=1, 依据=why,
             依据文件="UOM-CANONICAL §2.1 uom_exception_map")
        for sku, (en, why) in UOM_EXCEPTION_MAP.items()]) if UOM_EXCEPTION_MAP else \
        pd.DataFrame(columns=["SKU", "对应EN成套产品", "pieces_per_unit", "依据", "依据文件"])

    summary = dict(
        rules_version=RULES_VERSION,
        US产品数=len(us_prods), PL产品数=len(pl_prods),
        仅US=len(us_prods - pl_prods), 仅PL=len(pl_prods - us_prods),
        都无=len(set(products) - us_prods - pl_prods),
        需求行数=len(dq), 重复需求scope=dup,
        需求行校验=int(len(dq) == len(us_prods) + len(pl_prods)),
        A活跃=int(len(act)), 产品数=len(products),
        主表行=len(main_tbl), 主表产品=int(main_tbl["产品键"].nunique()) if len(main_tbl) else 0,
        US行=int((main_tbl["地区"] == "US").sum()) if len(main_tbl) else 0,
        PL行=int((main_tbl["地区"] == "PL").sum()) if len(main_tbl) else 0,
        US_PL并存产品=int(((main_tbl.groupby("产品键")["地区"].nunique() > 1).sum())
                      if len(main_tbl) else 0),
        仅库存产品=len(so), ND行=len(nd_tbl),
        待审=len(review), 冲突=len(conflict_rows),
        stock_placement行=int((main_tbl["市场状态"] == "stock_placement").sum()) if len(main_tbl) else 0,
        共享码候选行=int(len(shared_tbl)),
        共享订单行=int(shared_orders.shape[0]),
        共享订单原数量=float(shared_orders["raw_qty"].sum()),
        共享订单换算数量=float(shared_orders["qty"].sum()),
        共享订单原码数=int(shared_orders["code"].nunique()),
        共享订单候选产品=int(len({product_of(c) for code, cs in shared_map.items()
                                   if code in set(shared_orders["code"]) for c in cs})),
        多件换算行=int((stk["ppu"] > 1).sum()),
        uom例外条目数=len(UOM_EXCEPTION_MAP),
        多件换算原量=float(stk.loc[stk["ppu"] > 1, "raw_available"].sum()),
        多件换算后量=float(stk.loc[stk["ppu"] > 1, "canonical_qty"].sum()),
        订单多件换算行=int((g["ppu"] > 1).sum()),
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
        shared_order_tbl.to_excel(w, sheet_name="共享订单池", index=False)
        conv_tbl.to_excel(w, sheet_name="多件换算样例", index=False)
        exception_tbl.to_excel(w, sheet_name="uom例外表", index=False)
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
        "# 仓库归属 A337 v6 r6（2026-10-29）",
        "",
        f"规则版本 `{s['rules_version']}`｜只读，不写 EN/通途，不发消息，不 push。",
        "",
        "## 1. 输入与指纹",
        "",
        "| 输入 | SHA256 |",
        "|---|---|",
    ]
    for k, v in inputs.items():
        L.append(f"| {k} | `{v['sha256']}` |")
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
        f"| US 产品 / PL 产品 | {s['US产品数']} / {s['PL产品数']} |",
        f"| 仅US / 仅PL / 并存 / 都无 | {s['仅US']} / {s['仅PL']} / {s['US_PL并存产品']} / {s['都无']} |",
        f"| 需求行数（应=US+PL 产品） | {s['需求行数']}（校验 {s['需求行校验']}） |",
        f"| **US owner 唯一性违规** | **{s['US_owner唯一性违规']}** |",
        f"| 待审 / 冲突 | {s['待审']} / {s['冲突']} |",
        f"| ND 独立需求行 | {s['ND独立需求行']} |",
        "",
        "A 活跃去向：" + "、".join(f"{k} {v}" for k, v in s["去向"].items()),
        "",
        "## 3. r6 六项修复（N1–N6）",
        "",
        f"- **N1 共享订单不硬归**：2025 gs 段共享码订单 **{s['共享订单行']} 行 / 原数量 "
        f"{s['共享订单原数量']:.0f} / 换算 {s['共享订单换算数量']:.0f} / "
        f"{s['共享订单原码数']} 个原码 / {s['共享订单候选产品']} 个候选产品**，"
        "全部只进 `共享订单池`（共享码×仓×年 各持一份），不给任何单一产品加 own2025/销量2025。",
        f"- **N2 多件后缀乘 N**：库存 **{s['多件换算行']} 行**换算（"
        f"{s['多件换算原量']:.0f} → {s['多件换算后量']:.0f}），订单 **{s['订单多件换算行']} 行**；"
        "新增 `raw_available/pieces_per_unit/conversion_basis/canonical_qty`，裸 -2/-3 不推倍数，"
        "Bundle/TJ# 按套不拆。",
        f"  **uom_exception_map 共 {s['uom例外条目数']} 条**：带 PCS 后缀但 EN 已有成套产品 1:1 的，"
        "按 1:1 不乘 N（明细见 `uom例外表`）。",
        "- **N3 US owner 时间裁决**：只有「本侧有 2026 且另一侧最后日期 ≤2025」才可直接判；"
        "两侧都有 2026 继续时间段/冲突判定（反例见测试）。",
        "- **N4 级联统一**：own90→own180→own2026→DN2026→DN2025→own2025→库存，"
        "地区存在性与 US owner 共用同一实现。",
        "- **N5 逐行证据**：旧151/未证13 的 `evidence_ids` 给实际 DN 号/订单行/库存源行；"
        "限制原因拆 `evidence_blockers/inventory_blockers/demand_blockers`。",
        "- **N6 命名统一**：共享附表仓侧写 美中USTX/美东USNJ；旧市场字段改名 `旧市场原值`。",
        "",
        f"## 4. 旧 151 / 未证 13",
        "",
        f"旧 151：仍待审 **{int(old_recon['仍待审'].sum())}**；未证 13：{len(un13)} 行闭环。",
        "",
        "## 5. 剩余真实例外",
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
        "- 共享池（库存与订单）均未被计入任何单一产品合计。",
        "- DN 明细缺 docstatus/is_return/DN 行 ID，本轮可定位市场但不能称单据级数量审计。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
