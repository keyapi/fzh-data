# -*- coding: utf-8 -*-
"""C v5：通途库存 → A FINAL(2,337) × 产品/形态 × 仓池 × UOM（只读）。

在 C v4 基础上并入用户 2026-10-29 新规则（写入 UOM-CANONICAL §2.1 例外）：
- **EN 物料组「星球抱枕」(KS0019) 整组 1:1**：不按通途 SKU 后缀乘 N。
  覆盖 `XINGQIU-12PCS`（→ KS0019-PBHLR-SET12-PLANETARYMASHUP）、`XINGQIU-*-10/16`
  （10/16 是尺寸不是件数）、`TT0009*`、`STPPW-13-1C` 等；库存与销量都按 1:1。
- **老产品-默认不补（待确认）**：该组行在事实层与供给行标记，**不硬删行**，数值照算，
  只给下游一个「不要据此自动补货」的资格位。

沿用 C v4 已关闭项：
A. UOM 新口径（默认个 / 套只给 TJ# Bundle / 多件后缀×N / 缓存套非Bundle按个 / 不再阻断）
B. C v3 复审 N1–N4（空集不为 0、骨架独立成品、证明状态一致、4_可发供给 单表）

只读：不写 EN / 通途，不发消息，不 push，不改 v2 / v3 / v4 产物。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

COVER_RE = re.compile(r"^(.*)-cover\d*$", re.I)
FOAM_RE = re.compile(r"^(.*)-foam\d*$", re.I)
PIECE_TAIL = re.compile(r"^(?P<base>.+?)[-_ ](?P<n>\d+)\s*pcs?$", re.I)
PIECE_MID = re.compile(r"[-_ ]\d+\s*pcs?[-_ ]", re.I)
# 星球抱枕组：物料组="星球抱枕"(KS0019)；用户点名的码形（兜底，映射不到时也认）
PLANET_GROUP_NAME = "星球抱枕"
PLANET_SKU_RE = re.compile(r"^(xingqiu|tt0009|stppw-13-1c)", re.I)
LEGACY_NOTE = "老产品-默认不补(待确认)"
STRIP_PREFIXES = ("删除", "~", "?", "？")
PRI = ["用户覆盖表(map)", "A来源码", "customer_code(活跃)", "sku_map", "customer_code(删除)"]

# 六桶冻结口径（C v2 评审 F4 基线，单位：行 / 原始 available 数值和）
BUCKET_BASELINE = {
    "计入A": (2484, 47332.0),
    "共享码": (53, 1403.0),
    "A未激活": (425, 20.0),
    "规则排除": (879, 10308263.0),
    "未映射": (1222, 2238.0),
    "皮壳无活跃EN": (254, 1192.0),
}
SRC_ROWS, SRC_QTY = 5317, 10360448.0

# C v3 基线（报告「与 v3 的差异」用）
V3_BASELINE = {"join_rows": 1805, "join_qty": 41940.0, "cover_proven_qty": 0.0,
               "unproven_rows": 488, "unproven_qty": 3872.0,
               "cover_unproven_rows": 64, "cover_unproven_qty": 540.0,
               "skeleton_qty": 0.0}


def norm(code) -> str:
    """客户码/通途码规范化：trim → 清 删除/~/? 前缀 → casefold。"""
    c = str(code).strip()
    changed = True
    while changed:
        changed = False
        for p in STRIP_PREFIXES:
            if c.startswith(p):
                c = c[len(p):].strip()
                changed = True
    return c.casefold()


def is_missing(x) -> bool:
    """None / NaN 统一判定（NaN 为 truthy，不能用 `if not x`）。"""
    return x is None or (isinstance(x, float) and pd.isna(x)) or x is pd.NaT


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def piece_info(sku: str) -> tuple[int, str, str]:
    """多件后缀 → (每单位件数, 依据, 状态)。只认末尾明确的 -NPCS/-NPC。"""
    s = str(sku).strip()
    m = PIECE_TAIL.match(s)
    if m and int(m.group("n")) > 1:
        return int(m.group("n")), f"后缀-{m.group('n')}PCS", "已换算"
    if PIECE_MID.search(s):
        return 1, "名称中段含件数（套装名，不是每单位件数）", "仅列不换算"
    return 1, "", ""


def load_a(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = pd.read_excel(path, sheet_name="活跃宇宙")
    active = universe[universe["活跃分类"] != "不活跃"].copy()
    shared = pd.read_excel(path, sheet_name="共享码剩余")
    return active, shared


def build_index(active: pd.DataFrame, customer_codes: Path, sku_map: Path,
                overrides: pd.DataFrame) -> tuple[dict, dict]:
    """v2 冻结解析索引（first-wins）：override.map > A来源码 > 客户码活跃 > sku_map > 客户码删除。"""
    idx: dict[str, str] = {}
    src: dict[str, str] = {}

    def add(code, en, tag):
        n = norm(code)
        if not n or n in ("nan", "none"):
            return
        if n not in idx:
            idx[n] = en
            src[n] = tag

    ov_map = {norm(r.tt): r.en for r in overrides[overrides["action"] == "map"].itertuples(index=False)
              if isinstance(r.tt, str)}
    for n, en in ov_map.items():
        idx[n] = en
        src[n] = "用户覆盖表(map)"

    for r in active.itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                add(tok, r[0], "A来源码")

    cc = pd.read_csv(customer_codes, dtype=str)
    deleted_pool = []
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if not c:
                continue
            if c.startswith("删除"):
                deleted_pool.append((c[2:], r.name))
            else:
                add(c, r.name, "customer_code(活跃)")
    for c, en in deleted_pool:
        add(c, en, "customer_code(删除)")

    sm = pd.read_csv(sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        add(r.tt, r.en, "sku_map")
    return idx, src


def build_candidates(active: pd.DataFrame, customer_codes: Path, sku_map: Path,
                     overrides: pd.DataFrame) -> dict[str, dict[str, set]]:
    """F5：同一归一码 → 各优先级下的全部候选 EN 集合（不取首个）。"""
    cand: dict[str, dict[str, set]] = {}

    def add(code, en, tag):
        n = norm(code)
        if not n or n in ("nan", "none"):
            return
        cand.setdefault(n, {}).setdefault(tag, set()).add(en)

    for n, en in {norm(r.tt): r.en for r in overrides[overrides["action"] == "map"].itertuples(index=False)
                  if isinstance(r.tt, str)}.items():
        add(n, en, "用户覆盖表(map)")
    for r in active.itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                add(tok, r[0], "A来源码")
    cc = pd.read_csv(customer_codes, dtype=str)
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if not c:
                continue
            if c.startswith("删除"):
                add(c[2:], r.name, "customer_code(删除)")
            else:
                add(c, r.name, "customer_code(活跃)")
    sm = pd.read_csv(sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        add(r.tt, r.en, "sku_map")
    return cand


def top_candidates(cand: dict, n: str) -> tuple[set, str]:
    """返回最高优先级的全部候选（不取首个）。"""
    d = cand.get(n)
    if not d:
        return set(), ""
    for pr in PRI:
        if pr in d and d[pr]:
            return set(d[pr]), pr
    return set(), ""


def pool_of(warehouse: str) -> str:
    """F2：仓池键保留实际仓（East/Central/Poland/CG/Other），美国不再合仓。"""
    w = str(warehouse)
    if w.startswith("WayfairCG-"):
        return "CG"
    if "退货" in w:
        return "退货仓"
    if w == "美东-CENTRADE":
        return "East"
    if w == "美中-FZH-DANEEY":
        return "Central"
    if w == "波兰-FZHPoland-covers":
        return "Poland"
    if w == "大件云仓":
        return "第三方(大件云仓)"
    return "Other"


def form_of_suffix(n: str, role: str | None, en: str | None) -> tuple[str, str]:
    """实物形态（actual_form）与判定依据。形态来自「实物证据」（后缀/PK# 命名），
    不覆盖 A 的 role，两者并列输出。"""
    if en and str(en).startswith("PK#"):
        return "皮壳", "EN命名(PK#前缀)"
    if COVER_RE.match(n):
        return "皮壳", "通途码后缀(-Cover)"
    if FOAM_RE.match(n):
        return "海绵", "通途码后缀(-Foam)"
    if role == "海绵/关联成品":
        return "海绵", "A角色(海绵/关联成品)"
    if role in ("内胆", "海绵", "主体骨架", "套件"):
        return role, f"A角色({role})"
    if role == "皮壳":
        return "皮壳", "A角色(皮壳)"
    if role == "成品":
        return "成品", "A角色(成品)"
    return "unknown", "无证据"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="通途库存 → A337 角色/形态/仓池/UOM 归并 v5（只读）")
    B = "D:/Work/fzh-order-store"
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--date", default="2026-10-28")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--overrides", default=f"{B}/analysis/sku_mapping_overrides_2026-10-29.csv")
    ap.add_argument("--non-product", default=f"{B}/non_product_skus.csv")
    ap.add_argument("--warehouse-scope", default=f"{B}/warehouse_scope.csv")
    ap.add_argument("--uom-cache", default=f"{B}/en-demand-v1/canonical/item_uom_cache.parquet")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/通途库存_A337_v5_2026-10-29.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/通途库存_A337_v5_2026-10-29_报告.md")
    args = ap.parse_args(argv)

    active, shared_df = load_a(Path(args.a_final))
    overrides = pd.read_csv(args.overrides, dtype=str)
    idx, src = build_index(active, Path(args.customer_codes), Path(args.sku_map), overrides)
    cand = build_candidates(active, Path(args.customer_codes), Path(args.sku_map), overrides)

    en_role = {str(r[0]): r[1] for r in active[["EN物料", "角色"]].itertuples(index=False)}
    en_ship = {str(r[0]): r[1] for r in active[["EN物料", "ship_mode"]].itertuples(index=False)}
    en_ship_cn = {str(r[0]): r[1] for r in active[["EN物料", "绍兴发货方式"]].itertuples(index=False)}

    # 星球抱枕组（UOM-CANONICAL §2.1 例外）：物料组=星球抱枕 / KS0019 前缀
    en_group = {str(r[0]): str(r[1]) for r in active[["EN物料", "物料组"]].itertuples(index=False)}
    planet_ens = {en for en, g in en_group.items() if g.strip() == PLANET_GROUP_NAME}
    planet_ens |= {en for en in en_role if str(en).startswith("KS0019")}
    planet_codes = {n for n, tags in cand.items()
                    if any(e in planet_ens for s in tags.values() for e in s)}

    deleted_ens = set(overrides[overrides["action"] == "delete"]["en"].dropna())
    nonproduct_ov = set(overrides[overrides["action"] == "non_product"]["en"].dropna())
    nonproduct = set(pd.read_csv(args.non_product, dtype=str)["sku"].astype(str))

    ov_map_codes = {norm(r.tt) for r in overrides[overrides["action"] == "map"].itertuples(index=False)
                    if isinstance(r.tt, str)}
    shared_codes = {norm(k) for k in shared_df["键"].dropna()} - ov_map_codes
    shared_cand = {norm(r["键"]): str(r["候选/说明"]) for _, r in shared_df.iterrows()
                   if isinstance(r.get("键"), str)}

    cover_of_base = {}
    for en, role in en_role.items():
        if role == "皮壳" and str(en).startswith("PK#"):
            cover_of_base[str(en)[3:].casefold()] = en

    uom_cache = pd.read_parquet(args.uom_cache)
    uoms = dict(zip(uom_cache["item_code"].astype(str), uom_cache["stock_uom"].astype(str)))
    is_stock_item = dict(zip(uom_cache["item_code"].astype(str), uom_cache["is_stock_item"].astype(int)))
    uom_conflict_en = {en for en in en_role
                       if uoms.get(en) == "套" and is_stock_item.get(en) == 1
                       and not str(en).upper().startswith("TJ#") and en_role.get(en) != "套件"}

    third_party = set(pd.read_csv(args.warehouse_scope, dtype=str)
                      .query("scope == 'third_party_cloud'")["warehouse"].astype(str))

    d = pd.read_parquet(args.stock)
    d = d.reset_index(drop=True)
    d["src_row"] = d.index + 1
    f = d[pd.to_datetime(d["snapshot_date"]).dt.date.astype(str) == args.date].copy()
    if f.empty:
        raise SystemExit(f"{args.stock} 没有 {args.date} 的行")
    f["sku"] = f["sku"].astype(str)
    f["available"] = pd.to_numeric(f["available"], errors="coerce").fillna(0.0)
    f["norm"] = f["sku"].map(norm)
    f["pool"] = f["warehouse_name"].map(pool_of)

    # ---------- v2 冻结解析（六桶基线） ----------
    def resolve(n: str) -> tuple[str | None, str]:
        if n in ov_map_codes:
            return idx.get(n), src.get(n, "用户覆盖表(map)")
        m = COVER_RE.match(n)
        if m:
            if n in shared_codes:
                return None, "共享码(未归属)"
            base_en = idx.get(m.group(1)) or idx.get(n)
            if base_en and base_en.casefold() in cover_of_base:
                return cover_of_base[base_en.casefold()], "皮壳派生(PK#+成品)"
            return None, "皮壳无活跃EN"
        if n in shared_codes:
            return None, "共享码(未归属)"
        en = idx.get(n)
        if en:
            tag = src.get(n, "?")
            if en in deleted_ens:
                return None, f"已按用户规则删除({tag})"
            return en, tag
        return None, "未映射"

    res = [resolve(n) for n in f["norm"]]
    f["en"] = [r[0] for r in res]
    f["mapping_source_v2"] = [r[1] for r in res]
    f["role"] = f["en"].map(lambda e: en_role.get(e) if e else None)

    f["is_fba"] = f["sku"].str.contains("FBA", case=False, na=False)
    f["is_third_party"] = f["warehouse_name"].astype(str).isin(third_party)
    f["is_return"] = f["pool"] == "退货仓"
    f["is_nonproduct"] = f["sku"].isin(nonproduct) | f["en"].isin(nonproduct_ov)
    f["is_big"] = f["available"] >= 100000

    f["exclusion"] = ""
    for flag, label in (("is_fba", "FBA 不计可用"),
                        ("is_third_party", "第三方云仓不补"),
                        ("is_return", "退货仓单列"),
                        ("is_nonproduct", "非商品/原料"),
                        ("is_big", "超大占位")):
        f.loc[(f["exclusion"] == "") & f[flag], "exclusion"] = label

    f["bucket"] = "未映射"
    f.loc[f["exclusion"] != "", "bucket"] = "规则排除"
    mapped = (f["exclusion"] == "") & f["en"].notna()
    f.loc[mapped & f["role"].notna(), "bucket"] = "计入A"
    f.loc[mapped & f["role"].isna(), "bucket"] = "A未激活"
    f.loc[(f["exclusion"] == "") & f["en"].isna() & (f["mapping_source_v2"] == "共享码(未归属)"),
          "bucket"] = "共享码"
    f.loc[(f["exclusion"] == "") & f["en"].isna() & (f["mapping_source_v2"] == "皮壳无活跃EN"),
          "bucket"] = "皮壳无活跃EN"

    # ---------- 六桶对账（冻结） ----------
    recon = (f.groupby("bucket").agg(行数=("sku", "size"), 数值和=("available", "sum"))
             .reindex(list(BUCKET_BASELINE)).reset_index())
    recon["基线行数"] = [BUCKET_BASELINE[b][0] for b in recon["bucket"]]
    recon["基线数值和"] = [BUCKET_BASELINE[b][1] for b in recon["bucket"]]
    recon["行数差"] = recon["行数"] - recon["基线行数"]
    recon["数值差"] = recon["数值和"] - recon["基线数值和"]
    total_row = {"bucket": "合计", "行数": int(recon["行数"].sum()),
                 "数值和": float(recon["数值和"].sum()),
                 "基线行数": SRC_ROWS, "基线数值和": SRC_QTY,
                 "行数差": int(recon["行数"].sum()) - SRC_ROWS,
                 "数值差": float(recon["数值和"].sum()) - SRC_QTY}
    recon = pd.concat([recon, pd.DataFrame([total_row])], ignore_index=True)
    if total_row["行数差"] != 0 or abs(total_row["数值差"]) > 1e-6:
        raise SystemExit(f"六桶对账不平：{total_row}")
    assert f["bucket"].notna().all()

    # ---------- F1/F5 逐行事实层 ----------
    def link_info(r) -> tuple[set, str, set]:
        n = r["norm"]
        cs, pr = top_candidates(cand, n)
        m = COVER_RE.match(n)
        if m:
            bs, bpr = top_candidates(cand, m.group(1))
            if bs:
                cs = cs | bs
                pr = pr or bpr
        return cs, pr, {e for e in cs if e in en_role}

    links = [link_info(r) for _, r in f.iterrows()]
    f["cands_all"] = [sorted(c) for c, _, _ in links]
    f["cand_priority"] = [p for _, p, _ in links]
    f["cands_active"] = [sorted(a) for _, _, a in links]
    f["n_cands_active"] = [len(a) for _, _, a in links]

    def link_status(r) -> str:
        if r["bucket"] == "共享码":
            return "显式共享码(A登记)"
        if r["bucket"] == "皮壳无活跃EN":
            return "待判定"
        if is_missing(r["en"]):
            return "无候选"
        if r["n_cands_active"] > 1:
            return "共享待核(同优先级多候选)"
        if r["en"] in en_role and len(r["cands_active"]) == 1:
            return "唯一候选"
        return "唯一候选(v2已归属)"

    f["link_status"] = [link_status(r) for _, r in f.iterrows()]

    forms = [form_of_suffix(n, role, en) for n, role, en in zip(f["norm"], f["role"], f["en"])]
    f["actual_form"] = [x[0] for x in forms]
    f["form_basis"] = [x[1] for x in forms]

    def product_of(r) -> tuple[str | None, str]:
        en, form = r["en"], r["actual_form"]
        if is_missing(en):
            if form == "皮壳" and len(r["cands_active"]) == 1:
                return r["cands_active"][0], "皮壳码同物映射(254补证)"
            return None, ""
        if str(en).startswith("PK#"):
            base = str(en)[3:]
            if base in en_role:
                return base, "PK#→成品EN(命名直推)"
            return base, "PK#→成品EN(命名直推,母EN未激活)"
        if form == "皮壳" and r["role"] == "成品":
            return en, "皮壳码登记在成品EN下(同物)"
        if form == "海绵" and r["role"] == "成品":
            return en, "海绵码登记在成品EN下(同物)"
        return en, f"A角色直连({r['role']})"

    po = [product_of(r) for _, r in f.iterrows()]
    f["product_id"] = [x[0] for x in po]
    f["conversion_basis"] = [x[1] for x in po]

    # ---------- 多件后缀换算（用户口径 3） ----------
    pk = [piece_info(s) for s in f["sku"]]
    f["pieces_per_unit"] = [x[0] for x in pk]
    f["pieces_basis"] = [x[1] for x in pk]
    f["pieces_status"] = [x[2] for x in pk]
    f["qty_pieces"] = f["available"] * f["pieces_per_unit"]
    f["piece_bridge"] = False

    # ---------- 星球抱枕组 1:1 例外（UOM-CANONICAL §2.1） ----------
    def in_planet(r) -> bool:
        en = r["en"]
        if not is_missing(en) and str(en) in planet_ens:
            return True
        n = r["norm"]
        if n in planet_codes:
            return True
        m = COVER_RE.match(n)
        if m and m.group(1) in planet_codes:
            return True
        pm = PIECE_TAIL.match(n)
        if pm and norm(pm.group("base")) in planet_codes:
            return True
        return bool(PLANET_SKU_RE.match(str(r["sku"]).strip()))

    f["planet_group"] = [in_planet(r) for _, r in f.iterrows()]
    # v4 口径（乘 N）留底用于差异报告，再统一改 1:1
    f["pieces_rule_only"] = f["pieces_per_unit"].copy()
    f.loc[f["planet_group"], "pieces_per_unit"] = 1
    f.loc[f["planet_group"], "pieces_status"] = "组级例外1:1"
    f.loc[f["planet_group"], "pieces_basis"] = "星球抱枕整组 1:1（UOM-CANONICAL §2.1 例外）"
    f.loc[f["planet_group"], "qty_pieces"] = f.loc[f["planet_group"], "available"]
    f["legacy_note"] = ""
    f.loc[f["planet_group"], "legacy_note"] = LEGACY_NOTE

    for i, r in f[f["pieces_per_unit"] > 1].iterrows():
        m = PIECE_TAIL.match(r["sku"])
        base_en = idx.get(norm(m.group("base"))) if m else None
        if base_en and base_en in en_role:
            f.at[i, "product_id"] = base_en
            f.at[i, "actual_form"] = "成品"
            f.at[i, "form_basis"] = f"多件后缀折算：{m.group('base')} → {base_en}"
            f.at[i, "conversion_basis"] = (
                f"SKU 后缀 -{r['pieces_per_unit']}PCS：基础码 {m.group('base')} 对应产品"
                f"（每单位 {r['pieces_per_unit']} 个）")
            # 套件包按件折算后归入成品供给（即使原 EN 不在 A 活跃集）
            if r["bucket"] != "计入A":
                f.at[i, "piece_bridge"] = True

    # ---------- UOM（用户 2026-10-29 口径） ----------
    def uom_info(r) -> tuple[str, str, str]:
        en = r["en"]
        if not is_missing(en):
            cached = uoms.get(str(en))
            stockable = is_stock_item.get(str(en))
            if cached == "套" and stockable == 0:
                return "套", "TJ#/Product Bundle（缓存stock_uom=套, is_stock_item=0）", ""
            if cached == "套" and stockable == 1:
                return ("个", "缓存为套但非Bundle → 按个",
                        "uom_conflict：缓存 stock_uom=套, is_stock_item=1（EN 缓存不准，按用户口径按个）")
            if cached:
                return "个", f"EN缓存stock_uom={cached}", ""
            return "个", "EN缓存无该物料 → 按个", "无单位来源：EN 缓存无该物料"
        return "个", "通途码无 EN 单位 → 按个", "无单位来源：皮壳/海绵通途码无 EN 缓存"

    ui = [uom_info(r) for _, r in f.iterrows()]
    f["uom"] = [x[0] for x in ui]
    f["uom_source"] = [x[1] for x in ui]
    f["uom_note"] = [x[2] for x in ui]
    f.loc[f["uom"] == "套", "qty_pieces"] = f.loc[f["uom"] == "套", "available"]
    # 多件后缀行一律按个（用户口径 3 优先于缓存套）
    bridge_mask = f["piece_bridge"]
    if bridge_mask.any():
        f.loc[bridge_mask, "uom"] = "个"
        f.loc[bridge_mask, "uom_source"] = "多件后缀折算 → 按个"
        f.loc[bridge_mask, "qty_pieces"] = (f.loc[bridge_mask, "available"]
                                            * f.loc[bridge_mask, "pieces_per_unit"])

    # ---------- 第六桶：254 行逐行处置（口径不变） ----------
    iso_mask = f["bucket"] == "皮壳无活跃EN"
    iso = f[iso_mask].copy()

    def dispose(r) -> tuple[str, str]:
        act = r["cands_active"]
        if len(act) > 1:
            return "待核", "多候选同优先级（保留全部候选，不任取）"
        if len(act) == 1:
            p = act[0]
            ship = en_ship.get(p)
            role = en_role.get(p)
            if role not in ("成品", "套件") and not str(p).startswith("PK#"):
                return "仍隔离", f"映射到非成品角色({role})，不构成成品供给"
            if ship == "皮壳":
                return "补证", "客户码/来源码同物映射→活跃产品且方式=皮壳：进入皮壳供给"
            if ship in ("成品", "半成品"):
                return "仍隔离", f"产品方式={ship}：皮壳组件不计可发供给（不属少算）"
            if ship is None:
                return "待核", "产品发货方式未知"
        return "仍隔离", "无活跃EN映射（码未登记到任何活跃产品）"

    disp = [dispose(r) for _, r in iso.iterrows()]
    iso["处置"] = [x[0] for x in disp]
    iso["处置原因"] = [x[1] for x in disp]
    iso["base码"] = [COVER_RE.match(n).group(1) if COVER_RE.match(n) else "" for n in iso["norm"]]
    iso["候选产品"] = [",".join(c) for c in iso["cands_active"]]
    iso["产品方式"] = [",".join(str(en_ship.get(c, "")) for c in c) for c in iso["cands_active"]]
    iso_tbl = iso[["src_row", "sku", "warehouse_name", "pool", "available", "qty_pieces", "uom",
                   "uom_source", "base码", "role", "actual_form", "候选产品", "产品方式",
                   "处置", "处置原因", "form_basis", "cand_priority"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "源SKU", "warehouse_name": "仓", "pool": "仓池",
        "available": "available", "qty_pieces": "个当量", "uom": "uom", "uom_source": "单位来源",
        "role": "A角色(v2无)", "actual_form": "实物形态", "form_basis": "形态依据",
        "cand_priority": "候选来源优先级"})
    iso_tbl["A角色(v2无)"] = iso_tbl["A角色(v2无)"].fillna("(无,未归属)")

    f["iso_disposition"] = ""
    f.loc[iso_mask, "iso_disposition"] = iso["处置"].values
    iso_proven = iso_mask & (f["iso_disposition"] == "补证")

    # ---------- N3：证明状态与候选状态一致 ----------
    def proof(r) -> str:
        b, ls, disp_ = r["bucket"], r["link_status"], r["iso_disposition"]
        if b == "未映射":
            return "无映射(未归属)"
        if b == "共享码":
            return "归属待核(显式共享码)"
        if b == "A未激活":
            return "映射到未激活EN"
        if b == "规则排除":
            return "不适用(规则排除)"
        if b == "皮壳无活跃EN":
            if disp_ == "补证":
                return "归属已证(254补证)"
            if disp_ == "待核":
                return "归属待核(多候选/方式未知)"
            return "无活跃映射(仍隔离)"
        if ls.startswith("共享"):
            return "归属待核(共享多候选)"
        return "归属已证"

    f["link_proof"] = [proof(r) for _, r in f.iterrows()]
    # 多件后缀跨桶行：基础码已映射到活跃产品，归属按已证记（桶仍保留 A未激活）
    f.loc[bridge_mask, "link_proof"] = "归属已证(基础码→活跃产品)"

    # ---------- 供给状态（N2：骨架按独立成品；套单列） ----------
    def eligible(r) -> str:
        if r["piece_bridge"]:
            return "成品供给"
        if r["bucket"] == "皮壳无活跃EN":
            if r["iso_disposition"] != "补证":
                return "待核" if r["iso_disposition"] == "待核" else "仍隔离(不计)"
        elif r["bucket"] != "计入A":
            return "非计入桶"
        if r["uom"] == "套":
            return "套件单列(套)"
        form = r["actual_form"]
        if form == "海绵":
            return "海绵分支(不计)"
        if form == "内胆":
            return "内胆组件(不计)"
        if form == "套件":
            return "套件单列(个)"
        if form not in ("成品", "皮壳", "主体骨架"):
            return "形态未知(待核)"
        p = r["product_id"]
        ship = en_ship.get(p) if p else None
        if ship is None:
            return "发货方式未知(待核)"
        if form == "皮壳":
            if ship != "皮壳":
                return f"方式={ship}:皮壳组件(不计)"
            return "皮壳供给"
        # 成品 / 主体骨架（N2：骨架独立销售，单独成行，不并入沙发成品）
        return "成品供给"

    f["supply_role"] = [eligible(r) for _, r in f.iterrows()]
    multi_in_counted = f[(f["bucket"] == "计入A") & (f["link_status"].str.startswith("共享"))]
    f.loc[multi_in_counted.index, "supply_role"] = "待核"

    def avail(r) -> str:
        if r["supply_role"] in ("非计入桶", "仍隔离(不计)"):
            return "不进join"
        if r["supply_role"] in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
            return "待核"
        if r["supply_role"] == "套件单列(套)":
            return "套件单列"
        if r["supply_role"] == "套件单列(个)":
            return "套件按个折算"
        if r["pool"] in ("CG", "Other"):
            return "仅披露(CG/Other)"
        if r["supply_role"] in ("海绵分支(不计)", "内胆组件(不计)") \
                or r["supply_role"].startswith("方式="):
            return "仅披露(不计)"
        return "可进join"

    f["availability"] = [avail(r) for _, r in f.iterrows()]

    # ---------- 产品×仓池×UOM 供给汇总（N1：保留适用行数，空集不求和） ----------
    sup_src = f[f["supply_role"].isin(["成品供给", "皮壳供给", "海绵分支(不计)",
                                       "内胆组件(不计)", "套件单列(个)", "套件单列(套)",
                                       "待核", "发货方式未知(待核)", "形态未知(待核)"])
                | f["supply_role"].str.startswith("方式=")].copy()
    sup_src = sup_src[sup_src["product_id"].notna()]

    # 先落状态列（assign 的右侧只对调用前的 frame 求值，必须分两步）
    sup_src = sup_src.assign(
        n_fg=(sup_src["supply_role"] == "成品供给").astype(int),
        n_cover=(sup_src["supply_role"] == "皮壳供给").astype(int),
        n_pending=sup_src["supply_role"].isin(
            ["待核", "发货方式未知(待核)", "形态未知(待核)"]).astype(int),
        n_bundle=sup_src["supply_role"].isin(["套件单列(套)", "套件单列(个)"]).astype(int),
    )
    sup_src = sup_src.assign(
        q_fg=sup_src["qty_pieces"].where(sup_src["n_fg"] == 1, 0.0),
        q_skeleton=sup_src["qty_pieces"].where(
            (sup_src["n_fg"] == 1) & (sup_src["actual_form"] == "主体骨架"), 0.0),
        q_cover=sup_src["qty_pieces"].where(sup_src["n_cover"] == 1, 0.0),
        q_foam=sup_src["qty_pieces"].where(sup_src["supply_role"] == "海绵分支(不计)", 0.0),
        q_comp=sup_src["qty_pieces"].where(sup_src["supply_role"] == "内胆组件(不计)", 0.0),
        q_pending=sup_src["qty_pieces"].where(sup_src["n_pending"] == 1, 0.0),
        q_bundle=sup_src["available"].where(sup_src["n_bundle"] == 1, 0.0),
    )
    pivot = (sup_src.groupby(["product_id", "pool", "uom"], dropna=False).agg(
        成品行数=("n_fg", "sum"), 成品库存=("q_fg", "sum"), 其中骨架=("q_skeleton", "sum"),
        皮壳行数=("n_cover", "sum"), 皮壳库存=("q_cover", "sum"),
        套件库存=("q_bundle", "sum"), 套件行数=("n_bundle", "sum"),
        海绵库存=("q_foam", "sum"), 内胆库存=("q_comp", "sum"),
        待核行数=("n_pending", "sum"), 待核库存=("q_pending", "sum"),
        行数=("n_fg", "size"),
        uom_source=("uom_source", lambda s: "；".join(sorted(set(s)))),
    )).reset_index()
    pivot["ship_mode"] = pivot["product_id"].map(en_ship)
    pivot["ship_mode_cn"] = pivot["product_id"].map(en_ship_cn)
    pivot["产品角色"] = pivot["product_id"].map(en_role)

    def calc(r):
        """N1：没有适用且已证事实 → null；共享/待核/不适用不得聚合成已证 0。"""
        if r["uom"] == "套":
            if r["套件行数"] == 0:
                return None, "无适用事实(非0)", "无适用行"
            return float(r["套件库存"]), "套件单列", "仅套件行"
        n_app = r["成品行数"] + r["皮壳行数"]
        if n_app == 0:
            return None, "无适用事实(非0)", "无适用行"
        if is_missing(r["ship_mode"]):
            return None, "待核(发货方式未知)", "方式未知"
        if r["ship_mode"] == "皮壳":
            v = r["成品库存"] + r["皮壳库存"]
            missing = ["缺成品行"] if r["成品行数"] == 0 else []
        elif r["ship_mode"] in ("成品", "半成品"):
            v = r["成品库存"]
            missing = ["缺成品行"] if r["成品行数"] == 0 else []
        else:
            return None, f"待核(方式={r['ship_mode']})", "方式未知"
        if r["待核行数"] > 0:
            missing.append("有待核行")
        if r["海绵库存"] > 0 or r["内胆库存"] > 0:
            missing.append("含海绵/内胆(未计)")
        return float(v), "已计入", ("完整" if not missing else "部分:" + "/".join(missing))

    cc_ = [calc(r) for _, r in pivot.iterrows()]
    pivot["可发供给"] = [x[0] for x in cc_]
    pivot["供给状态"] = [x[1] for x in cc_]
    pivot["覆盖完整性"] = [x[2] for x in cc_]

    def avail2(r):
        if r["uom"] == "套":
            return "套件单列"
        if r["可发供给"] is None or pd.isna(r["可发供给"]):
            return "不进join(无适用事实)" if r["供给状态"].startswith("无适用") else "不进join(待核)"
        if r["pool"] in ("CG", "Other"):
            return "仅披露(CG/Other)"
        if r["覆盖完整性"] == "完整":
            return "可进join"
        return f"可进join(partial:{r['覆盖完整性'][3:]})"

    pivot["可用性"] = [avail2(r) for _, r in pivot.iterrows()]
    pivot["补货资格"] = ["老产品-默认不补(待确认)" if str(p) in planet_ens else ""
                         for p in pivot["product_id"]]
    supply_tbl = pivot[["product_id", "产品角色", "ship_mode", "ship_mode_cn", "pool", "uom",
                        "uom_source", "成品库存", "其中骨架", "皮壳库存", "套件库存",
                        "可发供给", "供给状态", "覆盖完整性", "海绵库存", "内胆库存",
                        "待核库存", "行数", "可用性", "补货资格"]].sort_values(["pool", "product_id", "uom"])

    # ---------- 多件后缀换算表（含星球组 1:1 例外） ----------
    pc_rows = f[f["pieces_status"] != ""].copy()
    pc_rows["v4口径个当量"] = pc_rows["available"] * pc_rows["pieces_rule_only"]
    pc_tbl = pc_rows[["src_row", "sku", "pieces_per_unit", "pieces_basis", "pieces_status",
                      "warehouse_name", "pool", "available", "qty_pieces", "v4口径个当量",
                      "legacy_note", "bucket", "en", "product_id", "supply_role",
                      "availability"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "源SKU", "pieces_per_unit": "每单位件数",
        "pieces_basis": "依据", "pieces_status": "状态", "warehouse_name": "仓", "pool": "仓池",
        "available": "available", "qty_pieces": "本版个当量",
        "v4口径个当量": "若按后缀乘N(个当量)", "legacy_note": "补货标记", "bucket": "桶",
        "en": "映射EN", "product_id": "产品", "supply_role": "供给状态",
        "availability": "可用性"}).sort_values(["本版个当量"], ascending=False)
    conv = pc_rows[pc_rows["pieces_status"] == "已换算"]
    exc = pc_rows[pc_rows["pieces_status"] == "组级例外1:1"]
    mid = pc_rows[pc_rows["pieces_status"] == "仅列不换算"]
    pc_summary = pd.DataFrame([
        {"项": "已换算(末尾多件后缀，非星球组)", "行数": int(len(conv)),
         "原始available": float(conv["available"].sum()), "个当量": float(conv["qty_pieces"].sum()),
         "若按后缀乘N": float(conv["v4口径个当量"].sum())},
        {"项": "组级例外 1:1（星球抱枕 KS0019）", "行数": int(len(exc)),
         "原始available": float(exc["available"].sum()), "个当量": float(exc["qty_pieces"].sum()),
         "若按后缀乘N": float(exc["v4口径个当量"].sum())},
        {"项": "仅列不换算(名称中段件数)", "行数": int(len(mid)),
         "原始available": float(mid["available"].sum()), "个当量": float(mid["qty_pieces"].sum()),
         "若按后缀乘N": float(mid["available"].sum())},
    ])

    # ---------- F5 共享候选全集 ----------
    def cands_disp(n: str) -> dict[str, set]:
        out: dict[str, set] = {}
        for e in _all_cands(cand, n):
            out.setdefault(e, set()).update(_tags_for(cand, n, e))
        m = COVER_RE.match(n)
        if m:
            for e in _all_cands(cand, m.group(1)):
                out.setdefault(e, set()).update(_tags_for(cand, m.group(1), e))
        return out

    shared_stock = f[(f["mapping_source_v2"] == "共享码(未归属)") | (f["norm"].isin(shared_codes))
                     | (f["n_cands_active"] > 1)]
    sh = (shared_stock.groupby(["norm", "warehouse_name", "pool"], dropna=False)
          .agg(行数=("sku", "size"), 库存=("available", "sum")).reset_index()
          .rename(columns={"norm": "归一码", "warehouse_name": "仓"}))
    sh["A登记候选"] = sh["归一码"].map(lambda n: shared_cand.get(n, ""))
    sh["本次全部候选(含来源)"] = sh["归一码"].map(
        lambda n: " | ".join(f"{en}<-{'/'.join(sorted(t))}"
                             for en, t in sorted(cands_disp(n).items())))
    sh["候选数"] = sh["归一码"].map(lambda n: len(cands_disp(n)))
    sh["触发来源"] = sh["归一码"].map(
        lambda n: "A共享码登记+多候选" if (n in shared_codes and len(cands_disp(n)) > 1)
        else ("A共享码登记" if n in shared_codes else "同优先级多候选(未登记)"))
    sh["处理"] = sh["归一码"].map(lambda n: "共享待核：保留全部候选，不分配单一EN"
                                  if len(cands_disp(n)) > 1 else "共享待核(A登记)")

    # ---------- 明细表（全量事实层） ----------
    detail = f[f["bucket"].notna()][
        ["src_row", "sku", "norm", "warehouse_id", "warehouse_name", "pool", "available",
         "pieces_per_unit", "qty_pieces", "pieces_status", "legacy_note", "uom", "uom_source",
         "uom_note", "bucket", "en", "role", "actual_form", "form_basis", "product_id",
         "conversion_basis", "link_status", "link_proof", "supply_role", "availability",
         "mapping_source_v2"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "source_sku", "norm": "归一码",
        "warehouse_id": "warehouse_id", "warehouse_name": "warehouse_name", "pool": "pool",
        "available": "qty", "pieces_per_unit": "pieces_per_unit", "qty_pieces": "qty_pieces",
        "pieces_status": "pieces_status", "legacy_note": "补货标记",
        "uom": "uom", "uom_source": "uom_source", "uom_note": "uom_note", "bucket": "桶",
        "en": "resolved_supply_item", "role": "role(A)", "actual_form": "actual_form",
        "form_basis": "form_basis", "product_id": "product_id",
        "conversion_basis": "conversion_basis", "link_status": "候选状态",
        "link_proof": "归属证明", "supply_role": "供给状态", "availability": "可用性",
        "mapping_source_v2": "mapping_source"})
    detail.insert(0, "snapshot_date", args.date)
    detail["源行号(parquet1基)"] = detail["源行号(parquet1基)"].astype(int)
    detail.insert(list(detail.columns).index("product_id") + 1, "ship_mode",
                  detail["product_id"].map(en_ship))

    un = f[f["bucket"] == "未映射"].copy()

    def why(r):
        if r["pool"] == "第三方(大件云仓)":
            return "第三方云仓（不计补货）"
        if r["is_fba"]:
            return "FBA 码（不计自发货）"
        if r["is_nonproduct"]:
            return "非商品/原料"
        if r["is_big"]:
            return "超大占位"
        return "真未映射（无任何映射源命中）"

    un["未映射原因"] = [why(r) for _, r in un.iterrows()]
    un_tbl = un[["src_row", "sku", "warehouse_name", "pool", "available", "未映射原因",
                 "cands_all", "n_cands_active"]] \
        .sort_values("available", ascending=False).rename(columns={
            "src_row": "源行号(parquet1基)", "sku": "源SKU", "warehouse_name": "仓", "pool": "仓池",
            "available": "available", "cands_all": "全部候选", "n_cands_active": "活跃候选数"})

    excluded = f[f["bucket"] == "规则排除"][
        ["src_row", "exclusion", "sku", "warehouse_name", "pool", "available", "en", "role",
         "actual_form"]].rename(columns={"src_row": "源行号(parquet1基)", "exclusion": "排除规则",
                                         "sku": "源SKU", "warehouse_name": "仓", "pool": "仓池",
                                         "available": "available", "en": "映射EN",
                                         "role": "A角色", "actual_form": "实物形态"})

    conflict_tbl = pd.DataFrame([{
        "EN": en, "缓存stock_uom(原值)": uoms.get(en), "is_stock_item(原值)": is_stock_item.get(en),
        "A角色": en_role.get(en), "发货方式": en_ship.get(en),
        "快照行数": int((f["en"] == en).sum()), "快照库存": float(f.loc[f["en"] == en, "available"].sum()),
        "v3 处理": "uom_conflict → 禁止可用量净额",
        "v4 处理": "按个计入可发供给；保留原值备查（用户 2026-10-29 口径 4）",
    } for en in sorted(uom_conflict_en)])

    # ---------- 汇总 ----------
    def bq(b):
        g = f[f["bucket"] == b]
        return int(len(g)), float(g["available"].sum())

    counted_rows = f[f["bucket"] == "计入A"].copy()

    def cat_of(r) -> str:
        sr = r["supply_role"]
        if sr in ("成品供给", "皮壳供给"):
            if r["pool"] in ("CG", "Other"):
                return "仅披露(CG/Other)"
            return "成品供给(独立骨架)" if r["actual_form"] == "主体骨架" else f"{sr}(按个)"
        if sr == "待核":
            return "待核(共享多候选)"
        if sr in ("发货方式未知(待核)", "形态未知(待核)"):
            return "待核(发货方式/形态未知)"
        if sr.startswith("方式="):
            return "方式不符:皮壳组件(仅披露)"
        if sr == "套件单列(个)":
            return "套件按个折算"
        if sr == "套件单列(套)":
            return "套件单列(套)"
        return sr

    counted_rows["去向"] = [cat_of(r) for _, r in counted_rows.iterrows()]
    decomp = (counted_rows.groupby("去向").agg(行数=("available", "size"),
                                               原始数值=("available", "sum"),
                                               个当量=("qty_pieces", "sum"))
              .reset_index().sort_values("个当量", ascending=False))
    iso_proven_rows = f[iso_proven]
    decomp = pd.concat([decomp, pd.DataFrame([{
        "去向": "254补证(第六桶→皮壳供给)", "行数": int(len(iso_proven_rows)),
        "原始数值": float(iso_proven_rows["available"].sum()),
        "个当量": float(iso_proven_rows["qty_pieces"].sum())}])], ignore_index=True)
    bridge_rows = f[f["piece_bridge"]]
    if len(bridge_rows):
        decomp = pd.concat([decomp, pd.DataFrame([{
            "去向": "多件后缀跨桶折算(A未激活→成品供给)", "行数": int(len(bridge_rows)),
            "原始数值": float(bridge_rows["available"].sum()),
            "个当量": float(bridge_rows["qty_pieces"].sum())}])], ignore_index=True)

    join_tbl = supply_tbl[supply_tbl["可用性"].astype(str).str.startswith("可进join")]
    discl_tbl = supply_tbl[supply_tbl["可用性"] == "仅披露(CG/Other)"]
    cover_rows = f[f["supply_role"] == "皮壳供给"]
    skeleton_rows = f[(f["supply_role"] == "成品供给") & (f["actual_form"] == "主体骨架")]
    no_fact = pivot[(pivot["供给状态"] == "无适用事实(非0)")]
    partial = supply_tbl[supply_tbl["可用性"].astype(str).str.startswith("可进join(partial")]

    summary = dict(
        date=args.date,
        rows_in=int(len(f)), qty_in=float(f["available"].sum()),
        buckets={b: bq(b)[0] for b in BUCKET_BASELINE},
        bucket_qty={b: bq(b)[1] for b in BUCKET_BASELINE},
        active_roles=len(active),
        covered_en=int(counted_rows["en"].nunique()),
        iso_total=len(iso_tbl),
        iso_disposition={k: int(v) for k, v in iso["处置"].value_counts().items()},
        iso_disposition_qty={k: float(g["available"].sum()) for k, g in iso.groupby("处置")},
        iso_pos={k: int((g["available"] > 0).sum()) for k, g in iso.groupby("处置")},
        shared_codes=int(shared_stock["norm"].nunique()),
        shared_extra_codes=int(multi_in_counted["norm"].nunique()),
        uom_conflict_en=len(uom_conflict_en),
        join_rows=int(len(join_tbl)), join_qty=float(join_tbl["可发供给"].fillna(0).sum()),
        discl_rows=int(len(discl_tbl)), discl_qty=float(discl_tbl["可发供给"].fillna(0).sum()),
        partial_rows=int(len(partial)),
        no_fact_keys=int(len(no_fact)),
        no_fact_raw=float(no_fact["成品库存"].sum() + no_fact["皮壳库存"].sum()
                          + no_fact["套件库存"].sum()),
        cover_rows=int(len(cover_rows)), cover_qty=float(cover_rows["qty_pieces"].sum()),
        cover_rows_in_join=int((cover_rows["availability"].astype(str).str.startswith("可进join")).sum()),
        cover_qty_in_join=float(cover_rows.loc[cover_rows["availability"].astype(str)
                                               .str.startswith("可进join"), "qty_pieces"].sum()),
        finished_rows=int((f["supply_role"] == "成品供给").sum()),
        skeleton_rows=int(len(skeleton_rows)), skeleton_qty=float(skeleton_rows["qty_pieces"].sum()),
        piece_rows=int(len(conv)), piece_raw=float(conv["available"].sum()),
        piece_qty=float(conv["qty_pieces"].sum()),
        piece_mid_rows=int(len(mid)), piece_mid_raw=float(mid["available"].sum()),
        piece_bridge_rows=int(len(bridge_rows)),
        piece_bridge_qty=float(bridge_rows["qty_pieces"].sum()),
        planet_rows=int(f["planet_group"].sum()),
        planet_raw=float(f.loc[f["planet_group"], "available"].sum()),
        planet_qty=float(f.loc[f["planet_group"], "qty_pieces"].sum()),
        planet_qty_v4rule=float((f.loc[f["planet_group"], "available"]
                                 * f.loc[f["planet_group"], "pieces_rule_only"]).sum()),
        planet_ens=len(planet_ens),
        planet_supply_rows=int((supply_tbl["补货资格"] != "").sum()),
        planet_supply_qty=float(supply_tbl.loc[supply_tbl["补货资格"] != "", "可发供给"].fillna(0).sum()),
        planet_join_delta=float(((f.loc[f["planet_group"], "available"]
                                  * f.loc[f["planet_group"], "pieces_rule_only"])
                                 - f.loc[f["planet_group"], "qty_pieces"])
                                .where(f.loc[f["planet_group"], "availability"]
                                       .astype(str).str.startswith("可进join"), 0.0).sum()),
        bundle_units=float(f.loc[f["uom"] == "套", "available"].sum()),
        bundle_rows=int((f["uom"] == "套").sum()),
        default_ge_rows=int(((f["uom_source"].str.startswith("EN缓存无该物料"))
                             & (f["bucket"] == "计入A")).sum()),
        default_ge_qty=float(f.loc[(f["uom_source"].str.startswith("EN缓存无该物料"))
                                   & (f["bucket"] == "计入A"), "available"].sum()),
        cover_noen_rows=int(((f["uom_source"].str.startswith("通途码无 EN 单位"))
                             & f["bucket"].isin(["计入A", "皮壳无活跃EN"])).sum()),
        cover_noen_qty=float(f.loc[(f["uom_source"].str.startswith("通途码无 EN 单位"))
                                   & f["bucket"].isin(["计入A", "皮壳无活跃EN"]), "available"].sum()),
        decomp={r["去向"]: [int(r["行数"]), float(r["原始数值"]), float(r["个当量"])]
                for r in decomp.to_dict("records")},
        pools={k: [int(v["rows"]), float(v["qty"])] for k, v in
               f.groupby("pool").agg(rows=("sku", "size"), qty=("available", "sum")).iterrows()},
        no_stock_en=int(len(active) - counted_rows["en"].nunique()),
    )

    # ---------- 输出 ----------
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    iso_total_rows, iso_total_qty = int(len(iso_tbl)), float(iso["available"].sum())

    def bucket_tbl():
        t = recon.copy()
        t["桶"] = t["bucket"]
        return t[["桶", "行数", "数值和", "基线行数", "基线数值和", "行数差", "数值差"]]

    def bridge_tbl():
        a_rows, a_qty = bq("计入A")
        add_rows = int((iso["处置"] == "补证").sum())
        add_qty = float(iso.loc[iso["处置"] == "补证", "available"].sum())
        return pd.DataFrame([
            {"项": "第六桶(皮壳无活跃EN)", "行数": iso_total_rows, "数值和": iso_total_qty,
             "说明": "逐行明细见 7_254行隔离明细"},
            {"项": "→ 补证进入皮壳供给", "行数": add_rows, "数值和": add_qty,
             "说明": "客户码/来源码同物映射到活跃产品且方式=皮壳（按个）"},
            {"项": "→ 待核", "行数": summary["iso_disposition"].get("待核", 0),
             "数值和": summary["iso_disposition_qty"].get("待核", 0.0), "说明": "多候选/方式未知"},
            {"项": "→ 仍隔离(有据不计)", "行数": summary["iso_disposition"].get("仍隔离", 0),
             "数值和": summary["iso_disposition_qty"].get("仍隔离", 0.0),
             "说明": "方式=成品/半成品(皮壳组件不计) 或 无活跃EN映射"},
            {"项": "计入A + 补证 = 供给输入", "行数": a_rows + add_rows, "数值和": a_qty + add_qty,
             "说明": "仍受多候选/方式约束；单位按用户口径不再阻断"},
        ])

    def notes_tbl():
        rows = [
            ("产物", "通途库存_A337_v5_2026-10-29.xlsx（v4 + 星球组 1:1 + 老产品标记，只读）"),
            ("脚本", "scripts/tongtool_inventory_rollup_a337_v5.py"),
            ("快照", f"snapshot_date={args.date}，{len(f)} 行，available 数值和 {f['available'].sum():,.0f}"),
            ("输入·stock", str(args.stock)),
            ("输入·stock SHA256", sha256(Path(args.stock))),
            ("输入·A FINAL", str(args.a_final)),
            ("输入·A FINAL SHA256", sha256(Path(args.a_final))),
            ("输入·发货方式CSV", "item_group_shipment_type_2026-10-28.csv（物料组级）"),
            ("输入·发货方式SHA256", sha256(Path("D:/Work/fzh-order-store/analysis/item_group_shipment_type_2026-10-28.csv"))),
            ("输入·uom_cache", str(args.uom_cache)),
            ("口径1·默认个", "一切按个；EN stock_uom 只作参考、不作证明"),
            ("口径2·套", "「套」只给 TJ#/Product Bundle（缓存 stock_uom=套 且 is_stock_item=0）"),
            ("口径3·多件后缀", "末尾 -2PCS/-3PCS/-5PC/-7PCS 等：每单位=N 个，available×N；裸 -2/-3 与中段件数不换算"),
            ("口径4·缓存套非Bundle", "KS0354/KS0422 按个计入，原值记入 uom_note 与 8_单位冲突记录"),
            ("口径5·不再阻断", "取消 uom_unproven 阻断；无单位来源按个计并记录来源缺失"),
            ("口径6·星球组1:1", "EN 物料组=星球抱枕(KS0019) 整组 1:1：XINGQIU-12PCS / XINGQIU-*-10/16 / "
                               "TT0009* / STPPW-13-1C 等 pieces_per_unit=1（UOM-CANONICAL §2.1 例外）"),
            ("口径7·老产品标记", "该组在事实层 `补货标记`、供给行 `补货资格` 标「老产品-默认不补(待确认)」；不删行、数值照算"),
            ("N1·空集不为0", "无适用成品/皮壳事实的键：可发供给=null、不进 join；共享/待核不被聚合成已证 0"),
            ("N2·主体骨架", "按 A 用户规则作独立成品分支，单独成行，不并入沙发成品/不按内胆组件排除"),
            ("N3·证明状态", "未映射=无映射，显式共享=归属待核，A未激活=映射到未激活EN，规则排除=不适用"),
            ("N4·表结构", "4_可发供给 只有产品表；套件以 uom=套 同表单列；去向分解在 10_供给去向分解"),
            ("口径·仓池", "East=美东-CENTRADE / Central=美中-FZH-DANEEY / Poland / CG=WayfairCG-* / Other；美国不合仓"),
            ("口径·可发供给", "皮壳模式=成品+皮壳；成品/半成品模式=成品（均按个）；套件单独按套"),
            ("口径·共享", "同优先级全部候选保留；多候选一律共享待核，不进可发供给"),
            ("口径·缺行", "无库存行的产品=未覆盖，不等于 0 库存"),
            ("只读声明", "未调用 EN/通途写接口，未发消息，未 push；不改 v2/v3 产物"),
        ]
        return pd.DataFrame(rows, columns=["项", "内容"])

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        notes_tbl().to_excel(w, sheet_name="0_说明", index=False)
        bucket_tbl().to_excel(w, sheet_name="1_六桶对账", index=False, startrow=0)
        bridge_tbl().to_excel(w, sheet_name="1_六桶对账", index=False, startrow=10)
        detail.to_excel(w, sheet_name="2_库存事实层", index=False)

        prod_form = (f[f["product_id"].notna() & f["bucket"].isin(["计入A", "皮壳无活跃EN"])]
                     .groupby(["product_id", "actual_form", "pool", "uom", "uom_source", "role",
                               "supply_role"], dropna=False)
                     .agg(库存=("qty_pieces", "sum"), 原始available=("available", "sum"),
                          行数=("sku", "size")).reset_index()
                     .sort_values(["pool", "product_id", "actual_form", "uom"]))
        prod_form["ship_mode"] = prod_form["product_id"].map(en_ship)

        def avail3(r) -> str:
            sr = r["supply_role"]
            if sr in ("成品供给", "皮壳供给"):
                return "仅披露(CG/Other)" if r["pool"] in ("CG", "Other") else "可参考"
            if sr in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
                return "待核"
            if sr.startswith("套件单列"):
                return "套件单列"
            return "仅披露(不计)"

        prod_form["可用性"] = [avail3(r) for _, r in prod_form.iterrows()]
        prod_form["补货资格"] = ["老产品-默认不补(待确认)" if str(p) in planet_ens else ""
                                 for p in prod_form["product_id"]]
        prod_form = prod_form[["product_id", "ship_mode", "actual_form", "role", "pool", "uom",
                               "uom_source", "supply_role", "库存", "原始available", "行数",
                               "可用性", "补货资格"]]
        prod_form.to_excel(w, sheet_name="3_产品×仓池×形态×UOM汇总", index=False)

        supply_tbl.to_excel(w, sheet_name="4_可发供给", index=False)
        pc_tbl.to_excel(w, sheet_name="5_多件后缀换算表", index=False)
        pc_summary.to_excel(w, sheet_name="5_多件后缀换算表", index=False, startrow=len(pc_tbl) + 2)
        sh.to_excel(w, sheet_name="6_共享候选", index=False)
        iso_tbl.to_excel(w, sheet_name="7_254行隔离明细", index=False)
        conflict_tbl.to_excel(w, sheet_name="8_单位冲突记录", index=False)
        excluded.to_excel(w, sheet_name="9_排除明细", index=False)
        decomp.to_excel(w, sheet_name="10_供给去向分解", index=False)

    Path(args.out_report).write_text(
        render(summary, bucket_tbl(), bridge_tbl(), supply_tbl, pc_summary,
               conflict_tbl, args, out),
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def _all_cands(cand: dict, n: str) -> set:
    return {e for tags in cand.get(n, {}).values() for e in tags}


def _tags_for(cand: dict, n: str, en: str) -> set:
    return {t for t, ens in cand.get(n, {}).items() if en in ens}


def render(summary, bucket_tbl, bridge_tbl, supply_tbl, pc_summary,
           conflict_tbl, args, out: Path) -> str:
    v3 = V3_BASELINE
    L = [
        "# 通途库存 → A FINAL（A337）v5 报告（2026-10-28 快照，只读）",
        "",
        "生成：`scripts/tongtool_inventory_rollup_a337_v5.py`（**只读**：不写 EN/通途、不发消息、不 push）",
        f"产物：`{out.name}`；在 v4 基础上并入 **星球抱枕组 1:1** 与 **老产品-默认不补(待确认)** 标记，"
        "不覆盖 v2 / v3 / v4。",
        "",
        "## 1. 与 v4 的差异（只改星球组，其余口径不动）",
        "",
        "| 项 | v4 口径 | v5 | 变化 |",
        "|---|---:|---:|---|",
        f"| 星球抱枕组库存（个当量）| {summary['planet_qty_v4rule']:,.0f} | "
        f"{summary['planet_qty']:,.0f} | -{summary['planet_qty_v4rule'] - summary['planet_qty']:,.0f} |",
        f"| 星球组涉及行 | — | {summary['planet_rows']:,} 行 / 原始 {summary['planet_raw']:,.0f} | "
        f"pieces_per_unit 全部置 1 |",
        f"| 多件后缀换算总量（个当量）| 多 {summary['planet_qty_v4rule'] - summary['planet_qty']:,.0f} | "
        f"{summary['piece_qty']:,.0f} | 组级例外不再乘 N |",
        f"| 可进 join（个）| 同批行会多 {summary['planet_join_delta']:,.0f} | "
        f"{summary['join_qty']:,.0f} | 仅星球组差异 |",
        "| 老产品标记 | 无 | 事实层 `补货标记` / 供给行 `补货资格` | 不硬删行 |",
        "",
        "> v4 未产出冻结文件（运行时中断），故 v4 列按「把星球组按后缀乘 N」解析计算，"
        "其余口径与 v4 完全一致。",
        "",
        "### 1.1 仍保留的 v3 → v4 既有修正",
        "",
        "| 项 | v3 | 本版（沿用 v4） |",
        "|---|---:|---:|",
        f"| 皮壳可发供给（可进 join，个）| {v3['cover_proven_qty']:,.0f} | "
        f"{summary['cover_qty_in_join']:,.0f} |",
        f"| 默认个未证（计入A）| {v3['unproven_rows']} 行 / {v3['unproven_qty']:,.0f} | "
        f"{summary['default_ge_rows']} 行 / {summary['default_ge_qty']:,.0f} 全部按个计入 |",
        f"| 皮壳通途码单位未证 | {v3['cover_unproven_rows']} 行 / {v3['cover_unproven_qty']:,.0f} | "
        f"{summary['cover_noen_rows']} 行 / {summary['cover_noen_qty']:,.0f} 按个计入 |",
        f"| 主体骨架供给（个）| {v3['skeleton_qty']:,.0f}（被当组件排除）| "
        f"{summary['skeleton_qty']:,.0f}（N2 独立成品）|",
        "| 空集伪 0 键 | 15 个标「可进join」 | 全部改判 null / 不进 join（N1）|",
        "| 事实层证明状态 | 未映射/共享也标「归属已证」 | 分别编码（N3）|",
        "| 4_可发供给 结构 | 尾部混入「去向」表 | 仅产品表；去向在 10_（N4）|",
        "",
        "## 2. 输入 SHA256",
        "",
        "| 输入 | SHA256 |",
        "|---|---|",
        f"| en_stock.parquet | `{sha256(Path(args.stock))}` |",
        f"| A FINAL SKU活跃宇宙_2026-10-29_FINAL.xlsx | `{sha256(Path(args.a_final))}` |",
        f"| item_group_shipment_type_2026-10-28.csv | `{sha256(Path('D:/Work/fzh-order-store/analysis/item_group_shipment_type_2026-10-28.csv'))}` |",
        f"| sku_mapping_overrides_2026-10-29.csv | `{sha256(Path(args.overrides))}` |",
        f"| en_item_customer_codes.csv | `{sha256(Path(args.customer_codes))}` |",
        f"| item_uom_cache.parquet | `{sha256(Path(args.uom_cache))}` |",
        "",
        "## 3. 六桶对账（口径未动，仍 0 差）",
        "",
        "| 桶 | 行数 | 数值和 | 基线行数 | 基线数值和 | 行差 | 数值差 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in bucket_tbl.to_dict("records"):
        L.append(f"| {r['桶']} | {r['行数']:,} | {r['数值和']:,.0f} | {r['基线行数']:,} | "
                 f"{r['基线数值和']:,.0f} | {r['行数差']} | {r['数值差']:,.0f} |")
    L += [
        "",
        f"源 {summary['rows_in']:,} 行 / {summary['qty_in']:,.0f} = 六桶之和；行差与数值差均为 0。",
        "",
        "### 3.1 六桶 → 供给输入桥接",
        "",
        "| 项 | 行数 | 数值和 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for r in bridge_tbl.to_dict("records"):
        L.append(f"| {r['项']} | {r['行数']} | {r['数值和']:,.0f} | {r['说明']} |")
    L += [
        "",
        "## 4. UOM 执行结果",
        "",
        "1. **默认个**：所有非 Bundle 行按个；`uom_source` 记录来源。",
        f"2. **套仅 Bundle**：{summary['bundle_rows']} 行 / {summary['bundle_units']:,.0f} 套，"
        "在 4_可发供给 以 `uom=套` 同表单列。",
        f"3. **多件后缀**：末尾明确多件 {summary['piece_rows']} 行，"
        f"{summary['piece_raw']:,.0f} → **{summary['piece_qty']:,.0f} 个**（+"
        f"{summary['piece_qty'] - summary['piece_raw']:,.0f}）。",
        f"4. **缓存套但非 Bundle**：{summary['uom_conflict_en']} 个 EN 按个计入，原值留档（8_单位冲突记录）。",
        "5. **不再阻断**：v3 的「单位未证不合计」已取消。",
        f"6. **星球抱枕组 1:1（§2.1 例外）**：{summary['planet_rows']:,} 行 / 原始 "
        f"{summary['planet_raw']:,.0f}，`pieces_per_unit` 一律 1；若按后缀乘 N 会是 "
        f"{summary['planet_qty_v4rule']:,.0f} 个，本版按 1:1 = **{summary['planet_qty']:,.0f} 个**。",
        "7. **老产品-默认不补(待确认)**：该组在事实层 `补货标记`、供给行 `补货资格` 打标，"
        "数值照算、行不删，仅提示下游不要据此自动补货。",
        "",
        "## 5. v3 复审 N1–N4 关闭说明",
        "",
        "### N1（P1）空集不得求和成「已证 0」",
        "",
        f"- 汇总按 product×pool×uom 保留 **成品行数 / 皮壳行数 / 待核行数**；"
        f"无适用成品/皮壳事实的键 **{summary['no_fact_keys']} 个**，可发供给 = **null**，"
        "可用性 = `不进join(无适用事实)`，不再出现「已证 0 / 可进join」。",
        f"- 仍有适用事实但缺另一形态行或含待核行的，数值照算但标 `覆盖完整性=部分:…`，"
        f"可用性写 `可进join(partial:…)`（共 {summary['partial_rows']} 行），避免把部分覆盖当完整。",
        "- 共享待核行不再因原 qty=0 被聚合成已证；「真正已证零」只有在该键存在实际适用行且 qty=0 时出现。",
        "",
        "### N2（P1）主体骨架独立成品分支",
        "",
        f"- ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45 等骨架按 A 用户规则作**独立成品**："
        f"供给角色 = 成品供给，单独成行（product_id=骨架自身，不并入沙发成品），"
        f"本次 {summary['skeleton_rows']} 行 / **{summary['skeleton_qty']:,.0f} 个**（美东 599 保留）。",
        "- 但仍只是库存事实，不外推采购建议。",
        "",
        "### N3（P2）证明状态与候选状态一致",
        "",
        "- 事实层 `归属证明` 取值：`归属已证`（唯一候选）/ `归属已证(254补证)` / "
        "`归属待核(共享多候选)` / `归属待核(显式共享码)` / `无映射(未归属)` / "
        "`映射到未激活EN` / `不适用(规则排除)` / `无活跃映射(仍隔离)`。",
        f"- 未映射 {summary['buckets']['未映射']:,} 行、显式共享 {summary['buckets']['共享码']:,} 行"
        "不再标「归属已证」。",
        "",
        "### N4（P3）表结构",
        "",
        "- `4_可发供给` 只含产品记录（含 uom=套 的套件行）；去向分解移到 `10_供给去向分解`。",
        "- 消费侧仍应校验必填键（product_id 非空、uom ∈ {个,套}），不把文字行当产品。",
        "",
        "## 6. 可发供给结果（个；套件单列）",
        "",
        f"- 产品行 {len(supply_tbl):,}（product×pool×uom）。",
        f"- **可进 join {summary['join_rows']:,} 行 / {summary['join_qty']:,.0f} 个**"
        f"（其中 partial {summary['partial_rows']:,} 行，见覆盖完整性）。",
        f"- CG/Other 只披露 {summary['discl_rows']:,} 行 / {summary['discl_qty']:,.0f}，不进 join。",
        f"- 无适用事实（null，不进 join）的键 {summary['no_fact_keys']} 个。",
        f"- **皮壳供给 {summary['cover_rows']:,} 行 / {summary['cover_qty']:,.0f} 个**，"
        f"可进 join {summary['cover_rows_in_join']:,} 行 / {summary['cover_qty_in_join']:,.0f} 个"
        f"（v3 为 0）。",
        f"- 成品供给 {summary['finished_rows']:,} 行（含骨架 {summary['skeleton_rows']} 行 / "
        f"{summary['skeleton_qty']:,.0f}）。",
        "",
        "### 6.1 去向分解（详见 10_供给去向分解）",
        "",
        "| 去向 | 行数 | 原始数值 | 个当量 |",
        "|---|---:|---:|---:|",
    ]
    for k, v in sorted(summary["decomp"].items(), key=lambda kv: -kv[1][2]):
        L.append(f"| {k} | {v[0]:,} | {v[1]:,.0f} | {v[2]:,.0f} |")
    L += [
        "",
        "| 仓池 | 行数(源) | 数值和(源) |",
        "|---|---:|---:|",
    ]
    for p, v in sorted(summary["pools"].items(), key=lambda kv: -kv[1][1]):
        L.append(f"| {p} | {v[0]:,} | {v[1]:,.0f} |")
    L += [
        "",
        "> 仓池数值为源 available 原始校验数（混合单位）；个当量见 `2_库存事实层.qty_pieces`。",
        "",
        "## 7. 多件后缀换算明细",
        "",
        "| 项 | 行数 | 原始 available | 本版个当量 | 若按后缀乘 N |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in pc_summary.to_dict("records"):
        L.append(f"| {r['项']} | {r['行数']} | {r['原始available']:,.0f} | "
                 f"{r['个当量']:,.0f} | {r['若按后缀乘N']:,.0f} |")
    L += [
        "",
        f"- **星球抱枕组**：`XINGQIU-12PCS`、`XINGQIU-*-10/16`（10/16 是尺寸）、`TT0009*`、"
        f"`STPPW-13-1C` 等全部 1:1；本版 {summary['planet_rows']:,} 行按 1:1 计 "
        f"{summary['planet_qty']:,.0f} 个（若按后缀乘 N 会多 "
        f"{summary['planet_qty_v4rule'] - summary['planet_qty']:,.0f} 个）。",
        f"- 跨桶折算（原 EN 不在 A 活跃集、但基础码对应活跃产品的套件包）："
        f"{summary['piece_bridge_rows']} 行 → {summary['piece_bridge_qty']:,.0f} 个，"
        "已并入对应成品供给（TT0031038K0062927-2PCS 波兰 10→20、-3PCS 波兰 10→30）。",
        "- 名称中段件数（如 `PPL-RockStone-7PCS-Cover`）按个不换算；裸 `-2/-3` 多为尺寸，按个。",
        "",
        "### 7.1 星球抱枕组与「老产品-默认不补(待确认)」",
        "",
        f"- 组内 EN {summary['planet_ens']} 个；命中库存 {summary['planet_rows']:,} 行 / 原始 "
        f"{summary['planet_raw']:,.0f}、1:1 个当量 {summary['planet_qty']:,.0f}。",
        f"- 其中落在可发供给表 {summary['planet_supply_rows']:,} 行 / {summary['planet_supply_qty']:,.0f} 个，"
        "全部带 `补货资格=老产品-默认不补(待确认)`；**行未删、数值照算**，只是不给自动补货资格。",
        "- 库存与销量都按 1:1（销量侧不在本工作簿范围，口径已在 UOM-CANONICAL §2.1 登记）。",
        "",
        "## 8. 单位冲突记录（口径 4）",
        "",
        f"共 **{summary['uom_conflict_en']} 个 EN**，v4 一律按个计入并保留原值：",
        "",
        "| EN | 缓存 stock_uom(原值) | is_stock_item | A角色 | 发货方式 | 快照行数 | 快照库存 |",
        "|---|---:|---:|---|---|---:|---:|",
    ]
    for r in conflict_tbl.to_dict("records"):
        L.append(f"| {r['EN']} | {r['缓存stock_uom(原值)']} | {r['is_stock_item(原值)']} | "
                 f"{r['A角色']} | {r['发货方式']} | {r['快照行数']} | {r['快照库存']:,.0f} |")
    L += [
        "",
        "## 9. 254 行处置结果（第六桶，口径不变）",
        "",
        "| 处置 | 行数 | 其中正库存 | 数值和 | 含义 |",
        "|---|---:|---:|---:|---|",
    ]
    meaning = {
        "补证": "客户码/来源码同物映射到活跃产品且方式=皮壳 → 进入皮壳供给（v4 按个计入）",
        "待核": "同优先级多候选 或 产品发货方式未知 → 保留候选，不进供给",
        "仍隔离": "产品方式=成品/半成品（皮壳组件不属少算）或 无活跃EN映射",
    }
    for k in ("补证", "待核", "仍隔离"):
        L.append(f"| {k} | {summary['iso_disposition'].get(k, 0)} | {summary['iso_pos'].get(k, 0)} | "
                 f"{summary['iso_disposition_qty'].get(k, 0):,.0f} | {meaning[k]} |")
    L += [
        "",
        "## 10. 共享候选",
        "",
        f"- `6_共享候选` 覆盖 **{summary['shared_codes']} 个码**；计入A 中多候选 "
        f"{summary['shared_extra_codes']} 个码按共享待核，不外推。",
        "",
        "## 11. 剩余未知项",
        "",
        f"- 无单位来源、按个计：EN缓存无该物料 {summary['default_ge_rows']:,} 行 / "
        f"{summary['default_ge_qty']:,.0f}；通途码无 EN 单位 {summary['cover_noen_rows']:,} 行 / "
        f"{summary['cover_noen_qty']:,.0f}。",
        f"- 共享待核 {summary['shared_extra_codes']} 个码仍不进供给。",
        f"- 无适用事实（null）{summary['no_fact_keys']} 个键：不是 0 库存，是缺事实。",
        f"- A 活跃 {summary['active_roles']} 个角色中库存只覆盖 {summary['covered_en']} 个，"
        f"其余 {summary['no_stock_en']} 个「未覆盖」，**不是 0**。",
        "- 海绵/内胆分支只披露；套件只按套单列，不拆组件。",
        "",
        "## 12. join v7 消费边界",
        "",
        "- **可读**：`2_库存事实层` + `4_可发供给` 中 `可用性` 以 `可进join` 开头的行。",
        "- **null 语义**：可发供给为空 = 无适用事实，禁止补 0；`可进join(partial:…)` 只能当部分覆盖。",
        "- **套件**：uom=套 的行不得与个混加。",
        "- **不可读**：`候选状态=共享待核`、`供给状态=待核`、`可用性=仅披露`。",
        "- **合同键**：snapshot_date × warehouse_id × source_sku × resolved_supply_item × "
        "actual_form × uom；另带 product_id、pieces_per_unit、源行号(parquet 1 基)。",
        "- **缺行语义**：产品在该 snapshot×仓池 无线 = 未覆盖，禁止补 0。",
        "- **CG/Other**：只披露，不得自动当责任仓可用。",
        "",
        "## 13. 只读声明",
        "",
        "本次仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途接口，未发消息，未 push；"
        "产物为新文件名，不覆盖 v2 / v3 / v4。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
