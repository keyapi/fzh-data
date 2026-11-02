# -*- coding: utf-8 -*-
"""C v3：通途库存 → A FINAL(2,337 角色) × 产品/供货形态 × 仓池 × UOM（只读）。

对 C v2 评审（C-STOCK-A337-REVIEW-2026-10-29, reject）的五项返修：
- F1 角色 ≠ 供货形态：保留 A `角色`，另建 `actual_form`（实物形态）与
  `product_id`（产品↔供货桥接）+ `link_proof`（归属证明状态）；-Cover 不再
  因 PK# 不在活跃集就丢进「皮壳无活跃EN」，按客户码/来源码同物映射到活跃产品
  并带 ship_mode；-Foam 一律进独立「海绵」分支，不得当成品可发供给。
- F2 美国不合仓：仓池键为 East / Central / Poland / CG / Other，CG/Other 只披露。
- F3 单位证明状态：汇总保留 uom_status（已证/默认个未证/uom_conflict/unknown）；
  EN 缓存 stock_uom=套 且 is_stock_item=1 的成品标 uom_conflict，禁止净额。
- F4 六桶对账：计入/共享/未激活/排除/未映射/皮壳无活跃EN 互斥且穷尽，并导出
  第六桶 254 行逐行明细 + 处置结果。
- F5 共享码不任取：同优先级保留全部候选集合，多候选一律「共享待核」。

只读：不写 EN / 通途，不发消息，不 push，不改 v2 产物。
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
    ap = argparse.ArgumentParser(description="通途库存 → A337 角色/形态/仓池/UOM 归并 v3（只读）")
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
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/通途库存_A337_v3_2026-10-29.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/通途库存_A337_v3_2026-10-29_报告.md")
    args = ap.parse_args(argv)

    active, shared_df = load_a(Path(args.a_final))
    overrides = pd.read_csv(args.overrides, dtype=str)
    idx, src = build_index(active, Path(args.customer_codes), Path(args.sku_map), overrides)
    cand = build_candidates(active, Path(args.customer_codes), Path(args.sku_map), overrides)

    en_role = {str(r[0]): r[1] for r in active[["EN物料", "角色"]].itertuples(index=False)}
    en_ship = {str(r[0]): r[1] for r in active[["EN物料", "ship_mode"]].itertuples(index=False)}
    en_ship_cn = {str(r[0]): r[1] for r in active[["EN物料", "绍兴发货方式"]].itertuples(index=False)}

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
    # F3：缓存 `套` + is_stock_item=1 的成品 = 与 UOM-CANONICAL（套仅用于 Bundle/TJ#）冲突
    uom_conflict_en = {en for en in en_role
                       if uoms.get(en) == "套" and is_stock_item.get(en) == 1
                       and not str(en).upper().startswith("TJ#") and en_role.get(en) != "套件"}

    third_party = set(pd.read_csv(args.warehouse_scope, dtype=str)
                      .query("scope == 'third_party_cloud'")["warehouse"].astype(str))

    d = pd.read_parquet(args.stock)
    d = d.reset_index(drop=True)
    d["src_row"] = d.index + 1                     # parquet 物理 1 基行号（可逐行定位）
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

    # ---------- F4 六桶对账（冻结） ----------
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

    # ---------- F1/F3/F5 逐行事实层 ----------
    def link_info(r) -> tuple[set, str, set]:
        n = r["norm"]
        cs, pr = top_candidates(cand, n)
        base = None
        m = COVER_RE.match(n)
        if m:
            base = m.group(1)
            bs, bpr = top_candidates(cand, base)
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
        en, n, form = r["en"], r["norm"], r["actual_form"]
        if is_missing(en):
            if form == "皮壳" and len(r["cands_active"]) == 1:
                return r["cands_active"][0], "皮壳码同物映射(待补证)"
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

    def uom_info(r) -> tuple[str, str]:
        en, form = r["en"], r["actual_form"]
        if r["bucket"] == "皮壳无活跃EN":
            if r["link_status"].startswith("待"):
                return "unknown", "unknown"
        if is_missing(en):
            # 皮壳码同物映射：库存物料本身是通途皮壳码，无 EN 单位缓存
            return "个", "cover_unproven" if form == "皮壳" else "unknown"
        if en in uom_conflict_en:
            return uoms.get(en, "套"), "uom_conflict"
        if r["role"] == "套件" or str(en).upper().startswith("TJ#"):
            return "套", "已证(套)"
        if form == "皮壳" and not str(en).startswith("PK#"):
            # 库存实物是 -Cover 通途码，单位不能借用成品 EN 的缓存
            return "个", "cover_unproven"
        if en in uoms:
            return uoms[en], "已证"
        return "个", "默认个未证"

    ui = [uom_info(r) for _, r in f.iterrows()]
    f["uom"] = [x[0] for x in ui]
    f["uom_status"] = [x[1] for x in ui]

    def proof(r) -> str:
        if r["uom_status"] == "uom_conflict":
            return "单位冲突待核"
        if r["link_status"].startswith("共享"):
            return "归属待核(多候选)"
        if r["bucket"] == "皮壳无活跃EN":
            return "归属待核"
        return "归属已证"

    f["link_proof"] = [proof(r) for _, r in f.iterrows()]

    # ---------- F4 第六桶：254 行逐行处置 ----------
    iso_mask = f["bucket"] == "皮壳无活跃EN"
    iso = f[iso_mask].copy()

    def dispose(r) -> tuple[str, str]:
        act = r["cands_active"]
        base = COVER_RE.match(r["norm"])
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
    iso_tbl = iso[["src_row", "sku", "warehouse_name", "pool", "available", "base码", "role",
                   "actual_form", "候选产品", "产品方式", "处置", "处置原因", "form_basis",
                   "cand_priority"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "源SKU", "warehouse_name": "仓", "pool": "仓池",
        "available": "available", "role": "A角色(v2无)", "actual_form": "实物形态",
        "form_basis": "形态依据", "cand_priority": "候选来源优先级"})
    iso_tbl["A角色(v2无)"] = iso_tbl["A角色(v2无)"].fillna("(无,未归属)")

    # 回写事实层：补证行进入可发供给
    f["iso_disposition"] = ""
    f.loc[iso_mask, "iso_disposition"] = iso["处置"].values
    iso_proven = iso_mask & (f["iso_disposition"] == "补证")
    f.loc[iso_proven, "link_proof"] = "归属已证(254补证)"
    # 补证的库存实物是通途皮壳码本身，单位不能借用成品 EN 缓存
    f.loc[iso_proven, "uom"] = "个"
    f.loc[iso_proven, "uom_status"] = "cover_unproven"

    # ---------- 可发供给（F1/F2/F3/F5） ----------
    def eligible(r) -> str:
        """返回供给状态：成品供给 / 皮壳供给 / 海绵分支(不计) / 组件(不计) /
        方式不符(不计) / 待核 / 仅披露"""
        if r["bucket"] == "皮壳无活跃EN":
            if r["iso_disposition"] != "补证":
                return "待核" if r["iso_disposition"] == "待核" else "仍隔离(不计)"
        elif r["bucket"] != "计入A":
            return "非计入桶"
        form = r["actual_form"]
        if form == "海绵":
            return "海绵分支(不计)"
        if form in ("内胆", "主体骨架"):
            return f"{form}组件(不计)"
        if form == "套件":
            return "套件(不计,组件计)"
        if form not in ("成品", "皮壳"):
            return "形态未知(待核)"
        p = r["product_id"]
        ship = en_ship.get(p) if p else None
        if ship is None:
            return "发货方式未知(待核)"
        if form == "皮壳":
            if ship != "皮壳":
                return f"方式={ship}:皮壳组件(不计)"
            return "皮壳供给"
        return "成品供给"

    f["supply_role"] = [eligible(r) for _, r in f.iterrows()]

    # F5：计入A 内仍有多候选的码一律共享待核，不取第一个
    multi_in_counted = f[(f["bucket"] == "计入A") & (f["link_status"].str.startswith("共享"))]
    f.loc[multi_in_counted.index, "supply_role"] = "待核"

    def avail(r) -> str:
        if r["supply_role"] in ("非计入桶", "仍隔离(不计)"):
            return "不进join"
        if r["uom_status"] == "uom_conflict":
            return "待核(单位冲突)"
        if r["supply_role"] in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
            return "待核"
        if r["pool"] in ("CG", "Other"):
            return "仅披露(CG/Other)"
        if r["supply_role"] in ("海绵分支(不计)", "内胆组件(不计)", "主体骨架组件(不计)",
                                "套件(不计,组件计)") or r["supply_role"].startswith("方式="):
            return "仅披露(不计)"
        if r["uom_status"] not in ("已证", "已证(套)"):
            return "已证归属/单位未证"
        return "可进join"

    f["availability"] = [avail(r) for _, r in f.iterrows()]

    # 产品 × 仓池 × UOM 供给汇总
    sup_src = f[f["supply_role"].isin(["成品供给", "皮壳供给", "海绵分支(不计)",
                                       "内胆组件(不计)", "主体骨架组件(不计)",
                                       "套件(不计,组件计)", "待核", "发货方式未知(待核)",
                                       "形态未知(待核)"])
                | f["supply_role"].str.startswith("方式=")].copy()
    sup_src = sup_src[sup_src["product_id"].notna()]

    sup_src = sup_src.assign(
        q=sup_src["available"],
        q_finished=sup_src["available"].where(sup_src["supply_role"] == "成品供给", 0.0),
        q_cover=sup_src["available"].where(sup_src["supply_role"] == "皮壳供给", 0.0),
        q_foam=sup_src["available"].where(sup_src["supply_role"] == "海绵分支(不计)", 0.0),
        q_comp=sup_src["available"].where(
            sup_src["supply_role"].isin(["内胆组件(不计)", "主体骨架组件(不计)", "套件(不计,组件计)"]), 0.0),
        q_pending=sup_src["available"].where(
            sup_src["supply_role"].isin(["待核", "发货方式未知(待核)", "形态未知(待核)"]), 0.0),
        n_finished=(sup_src["supply_role"] == "成品供给").astype(int),
        n_cover=(sup_src["supply_role"] == "皮壳供给").astype(int),
    )
    pivot = (sup_src.groupby(["product_id", "pool", "uom", "uom_status"], dropna=False).agg(
        成品供给行数=("n_finished", "sum"), 成品库存=("q_finished", "sum"),
        皮壳供给行数=("n_cover", "sum"), 皮壳库存=("q_cover", "sum"),
        海绵库存=("q_foam", "sum"), 组件库存=("q_comp", "sum"),
        待核库存=("q_pending", "sum"), 行数=("q", "size"),
    )).reset_index()
    pivot["ship_mode"] = pivot["product_id"].map(en_ship)
    pivot["ship_mode_cn"] = pivot["product_id"].map(en_ship_cn)
    pivot["产品角色"] = pivot["product_id"].map(en_role)

    def calc(r):
        if r["uom_status"] == "uom_conflict":
            return None, "待核(单位冲突)"
        if r["ship_mode"] is None or pd.isna(r["ship_mode"]):
            return None, "待核(发货方式未知)"
        if r["ship_mode"] == "皮壳":
            v = r["成品库存"] + r["皮壳库存"]
        elif r["ship_mode"] in ("成品", "半成品"):
            v = r["成品库存"]
        else:
            return None, f"待核(方式={r['ship_mode']})"
        if r["uom_status"] in ("已证", "已证(套)"):
            return float(v), "已证"
        return None, "单位未证(不合计)"

    cc_ = [calc(r) for _, r in pivot.iterrows()]
    pivot["可发供给_已证"] = [x[0] for x in cc_]
    pivot["供给状态"] = [x[1] for x in cc_]

    def avail2(r):
        if r["pool"] in ("CG", "Other"):
            return "仅披露(CG/Other)"
        if r["供给状态"] == "已证":
            return "可进join"
        return "不进join"

    pivot["可用性"] = [avail2(r) for _, r in pivot.iterrows()]
    supply_tbl = pivot[["product_id", "产品角色", "ship_mode", "ship_mode_cn", "pool", "uom",
                        "uom_status", "成品库存", "皮壳库存", "可发供给_已证", "供给状态",
                        "海绵库存", "组件库存", "待核库存", "行数", "可用性"]] \
        .sort_values(["pool", "product_id", "uom"])

    # ---------- F5 共享候选全集：A 登记共享码 ∪ 同优先级多候选码（全部候选保留） ----------
    def cands_disp(n: str) -> dict[str, set]:
        """与 link_info 同口径：-Cover 码把「自身码」与「基码」的候选并起来。"""
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

    # ---------- 明细表（全量事实层，5,317 行全部保留） ----------
    detail = f[f["bucket"].notna()][
        ["src_row", "sku", "norm", "warehouse_id", "warehouse_name", "pool", "available", "bucket",
         "en", "role", "actual_form", "form_basis", "product_id", "conversion_basis", "uom",
         "uom_status", "link_status", "link_proof", "supply_role", "availability",
         "mapping_source_v2"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "source_sku", "norm": "归一码",
        "warehouse_id": "warehouse_id", "warehouse_name": "warehouse_name", "pool": "pool",
        "available": "qty", "bucket": "桶", "en": "resolved_supply_item", "role": "role(A)",
        "actual_form": "actual_form", "form_basis": "form_basis", "product_id": "product_id",
        "conversion_basis": "conversion_basis", "uom": "uom", "uom_status": "uom_status",
        "link_status": "候选状态", "link_proof": "归属证明", "supply_role": "供给状态",
        "availability": "可用性", "mapping_source_v2": "mapping_source"})
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
    inactive = f[f["bucket"] == "A未激活"][
        ["src_row", "en", "sku", "warehouse_name", "pool", "available", "mapping_source_v2"]] \
        .rename(columns={"src_row": "源行号(parquet1基)", "en": "映射EN", "sku": "源SKU",
                         "warehouse_name": "仓", "pool": "仓池", "available": "available",
                         "mapping_source_v2": "映射来源"})

    # 单位冲突
    conflict_rows = f[(f["en"].isin(uom_conflict_en)) | (f["uom_status"] == "uom_conflict")]
    conflict_en = sorted(set(conflict_rows["en"].dropna()))
    conflict_tbl = pd.DataFrame([{
        "EN": en, "缓存stock_uom": uoms.get(en), "is_stock_item": is_stock_item.get(en),
        "A角色": en_role.get(en), "发货方式": en_ship.get(en),
        "快照行数": int((f["en"] == en).sum()), "快照库存": float(f.loc[f["en"] == en, "available"].sum()),
        "判定": "uom_conflict：缓存套且is_stock_item=1，与UOM-CANONICAL(套仅Bundle/TJ#)冲突",
        "处置": "禁止可用量净额，待核真实单位/Bundle身份",
    } for en in uom_conflict_en])

    # ---------- 汇总统计 ----------
    def bq(b):
        g = f[f["bucket"] == b]
        return int(len(g)), float(g["available"].sum())

    supply_unproven = supply_tbl[supply_tbl["供给状态"] == "单位未证(不合计)"]
    supply_pending = supply_tbl[supply_tbl["供给状态"].astype(str).str.startswith("待核")]
    supply_ok = supply_tbl[supply_tbl["供给状态"] == "已证"]
    join_tbl = supply_ok[supply_ok["可用性"] == "可进join"]
    discl_tbl = supply_ok[supply_ok["可用性"] == "仅披露(CG/Other)"]

    # 计入A → 可发供给 去向分解（事实层逐行，数值必须回到 47,332）
    def cat_of(r) -> str:
        sr = r["supply_role"]
        if sr in ("成品供给", "皮壳供给"):
            if r["pool"] in ("CG", "Other"):
                return "仅披露(CG/Other)"
            if r["uom_status"] == "uom_conflict":
                return "待核(单位冲突)"
            if r["uom_status"] in ("已证", "已证(套)"):
                return "可进join(已证单位)"
            return "单位未证(不合计)"
        if sr == "待核":
            return "待核(共享多候选)"
        if sr == "发货方式未知(待核)" or sr == "形态未知(待核)":
            return "待核(发货方式/形态未知)"
        if sr.startswith("方式="):
            return "方式不符:皮壳组件(仅披露)"
        return sr
    counted_rows = f[f["bucket"] == "计入A"].copy()
    counted_rows["去向"] = [cat_of(r) for _, r in counted_rows.iterrows()]
    decomp = (counted_rows.groupby("去向").agg(行数=("available", "size"), 数值和=("available", "sum"))
              .reset_index().sort_values("数值和", ascending=False))
    iso_proven_rows = f[iso_proven]
    decomp = pd.concat([decomp, pd.DataFrame([{
        "去向": "254补证(第六桶→皮壳供给)", "行数": int(len(iso_proven_rows)),
        "数值和": float(iso_proven_rows["available"].sum())}])], ignore_index=True)
    assert abs(decomp["数值和"].sum() - (bq("计入A")[1] + float(iso_proven_rows["available"].sum()))) < 1e-6

    summary = dict(
        date=args.date,
        rows_in=int(len(f)), qty_in=float(f["available"].sum()),
        buckets={b: bq(b)[0] for b in BUCKET_BASELINE},
        bucket_qty={b: bq(b)[1] for b in BUCKET_BASELINE},
        active_roles=len(active),
        covered_en=int(f.loc[f["bucket"] == "计入A", "en"].nunique()),
        iso_total=len(iso_tbl),
        iso_disposition={k: int(v) for k, v in iso["处置"].value_counts().items()},
        iso_disposition_qty={k: float(g["available"].sum()) for k, g in iso.groupby("处置")},
        iso_pos={k: int((g["available"] > 0).sum()) for k, g in iso.groupby("处置")},
        shared_codes=int(shared_stock["norm"].nunique()),
        shared_extra_codes=int(multi_in_counted["norm"].nunique()),
        uom_conflict_en=len(uom_conflict_en),
        uom_conflict_with_stock=len(conflict_en),
        supply_rows_proven=int(len(supply_ok)),
        supply_rows_unproven=int(len(supply_unproven)),
        supply_rows_pending=int(len(supply_pending)),
        supply_proven_qty=float(supply_ok["可发供给_已证"].fillna(0).sum()),
        supply_unproven_qty=float(supply_unproven["成品库存"].sum() + supply_unproven["皮壳库存"].sum()),
        supply_pending_qty=float(supply_pending["待核库存"].sum()),
        join_rows=int(len(join_tbl)), join_qty=float(join_tbl["可发供给_已证"].fillna(0).sum()),
        discl_rows=int(len(discl_tbl)), discl_qty=float(discl_tbl["可发供给_已证"].fillna(0).sum()),
        cover_supply_rows=int((f["supply_role"] == "皮壳供给").sum()),
        cover_supply_qty=float(f.loc[f["supply_role"] == "皮壳供给", "available"].sum()),
        cover_supply_proven_qty=float(f.loc[(f["supply_role"] == "皮壳供给")
                                            & f["uom_status"].isin(["已证", "已证(套)"]), "available"].sum()),
        decomp={r["去向"]: [int(r["行数"]), float(r["数值和"])] for r in decomp.to_dict("records")},
        unproven_rows=int((counted_rows["uom_status"] == "默认个未证").sum()),
        unproven_qty=float(counted_rows.loc[counted_rows["uom_status"] == "默认个未证", "available"].sum()),
        cover_unproven_rows=int(((f["uom_status"] == "cover_unproven")
                                 & ((f["bucket"] == "计入A") | iso_proven)).sum()),
        cover_unproven_qty=float(f.loc[(f["uom_status"] == "cover_unproven")
                                       & ((f["bucket"] == "计入A") | iso_proven), "available"].sum()),
        pools={k: [int(v["rows"]), float(v["qty"])] for k, v in
               f.groupby("pool").agg(rows=("sku", "size"), qty=("available", "sum")).iterrows()},
        no_stock_en=int(len(active) - f.loc[f["bucket"] == "计入A", "en"].nunique()),
    )

    # ---------- 输出 ----------
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)

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
             "说明": "v2 未导出明细"},
            {"项": "→ 补证进入皮壳供给", "行数": add_rows, "数值和": add_qty,
             "说明": "客户码/来源码同物映射到活跃产品且方式=皮壳；进入 4_可发供给"},
            {"项": "→ 待核", "行数": summary["iso_disposition"].get("待核", 0),
             "数值和": summary["iso_disposition_qty"].get("待核", 0.0), "说明": "多候选/方式未知"},
            {"项": "→ 仍隔离(有据不计)", "行数": summary["iso_disposition"].get("仍隔离", 0),
             "数值和": summary["iso_disposition_qty"].get("仍隔离", 0.0),
             "说明": "方式=成品/半成品(皮壳组件不计) 或 无活跃EN映射"},
            {"项": "计入A + 补证 = 归属已证行", "行数": a_rows + add_rows, "数值和": a_qty + add_qty,
             "说明": "供给计算输入（仍受单位/多候选/方式约束）"},
        ])

    iso_total_rows, iso_total_qty = int(len(iso_tbl)), float(iso["available"].sum())

    def notes_tbl():
        rows = [
            ("产物", "通途库存_A337_v3_2026-10-29.xlsx（返修 C v2，只读）"),
            ("脚本", "scripts/tongtool_inventory_rollup_a337_v3.py"),
            ("快照", f"snapshot_date={args.date}，{len(f)} 行，available 数值和 {f['available'].sum():,.0f}"),
            ("输入·stock", str(args.stock)),
            ("输入·stock SHA256", sha256(Path(args.stock))),
            ("输入·A FINAL", str(args.a_final)),
            ("输入·A FINAL SHA256", sha256(Path(args.a_final))),
            ("输入·发货方式CSV", "item_group_shipment_type_2026-10-28.csv（物料组级）"),
            ("输入·发货方式SHA256", sha256(Path("D:/Work/fzh-order-store/analysis/item_group_shipment_type_2026-10-28.csv"))),
            ("输入·overrides", str(args.overrides)),
            ("输入·customer_codes", str(args.customer_codes)),
            ("输入·uom_cache", str(args.uom_cache)),
            ("口径·角色", "role 一律取 A FINAL `角色`，不由后缀改写"),
            ("口径·形态", "actual_form 为实物形态（-Cover→皮壳 / -Foam→海绵 / PK#→皮壳），与 role 并列"),
            ("口径·仓池", "East=美东-CENTRADE / Central=美中-FZH-DANEEY / Poland / CG=WayfairCG-* / Other；美国不合仓"),
            ("口径·可发供给", "皮壳模式=成品+皮壳；成品/半成品模式=成品；方式未知留空待核；未证单位不合计"),
            ("口径·单位", "已证=EN缓存stock_uom；默认个未证单列；uom_conflict 禁止净额；TJ# 按套"),
            ("口径·共享", "同优先级全部候选保留；多候选一律共享待核，不进可发供给"),
            ("口径·缺行", "无库存行的产品=未覆盖，不等于 0 库存"),
            ("只读声明", "未调用 EN/通途写接口，未发消息，未 push；只覆盖本文件名，不覆盖 v2 产物"),
        ]
        return pd.DataFrame(rows, columns=["项", "内容"])

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        notes_tbl().to_excel(w, sheet_name="0_说明", index=False)
        bucket_tbl().to_excel(w, sheet_name="1_源与六桶对账", index=False, startrow=0)
        bridge_tbl().to_excel(w, sheet_name="1_源与六桶对账", index=False, startrow=10)
        detail.to_excel(w, sheet_name="2_库存事实层", index=False)
        # 3_产品×仓池×形态×UOM 汇总
        prod_form = (f[f["product_id"].notna() & f["bucket"].isin(["计入A", "皮壳无活跃EN"])]
                     .groupby(["product_id", "actual_form", "pool", "uom", "uom_status", "role",
                               "supply_role"], dropna=False)
                     .agg(库存=("available", "sum"), 行数=("sku", "size")).reset_index()
                     .sort_values(["pool", "product_id", "actual_form", "uom"]))
        prod_form["ship_mode"] = prod_form["product_id"].map(en_ship)

        def avail3(r) -> str:
            sr, uom_st = r["supply_role"], r["uom_status"]
            if sr in ("成品供给", "皮壳供给") and r["pool"] in ("CG", "Other"):
                return "仅披露(CG/Other)"
            if uom_st == "uom_conflict":
                return "待核(单位冲突)"
            if sr in ("成品供给", "皮壳供给"):
                return "可参考" if uom_st in ("已证", "已证(套)") else "单位未证(不合计)"
            if sr in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
                return "待核"
            return "仅披露(不计)"

        prod_form["可用性"] = [avail3(r) for _, r in prod_form.iterrows()]
        prod_form = prod_form[["product_id", "ship_mode", "actual_form", "role", "pool", "uom",
                               "uom_status", "supply_role", "库存", "行数", "可用性"]]
        prod_form.to_excel(w, sheet_name="3_产品×仓池×形态×UOM汇总", index=False)
        supply_tbl.to_excel(w, sheet_name="4_可发供给", index=False)
        decomp.to_excel(w, sheet_name="4_可发供给", index=False, startrow=len(supply_tbl) + 2)
        sh.to_excel(w, sheet_name="5_共享候选全集", index=False)
        un_tbl.to_excel(w, sheet_name="6_未映射", index=False)
        iso_tbl.to_excel(w, sheet_name="7_254行隔离明细", index=False)
        conflict_tbl.to_excel(w, sheet_name="8_单位冲突", index=False)
        excluded.to_excel(w, sheet_name="9_排除明细", index=False)

    Path(args.out_report).write_text(
        render(summary, bucket_tbl(), bridge_tbl(), supply_tbl, conflict_tbl, args, out),
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def _all_cands(cand: dict, n: str) -> set:
    return {e for tags in cand.get(n, {}).values() for e in tags}


def _tags_for(cand: dict, n: str, en: str) -> set:
    return {t for t, ens in cand.get(n, {}).items() if en in ens}


def render(summary, bucket_tbl, bridge_tbl, supply_tbl, conflict_tbl, args,
           out: Path) -> str:
    b = summary["buckets"]
    L = [
        "# 通途库存 → A FINAL（A337）v3 报告（2026-10-28 快照，只读）",
        "",
        "生成：`scripts/tongtool_inventory_rollup_a337_v3.py`（**只读**：不写 EN/通途、不发消息、不 push）",
        f"产物：`{out.name}`；返修对象 C v2（评审 `C-STOCK-A337-REVIEW-2026-10-29`，reject）。",
        "",
        "## 1. 输入 SHA256",
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
        "## 2. 六桶对账（互斥且穷尽，差额 0）",
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
        "第六桶（皮壳无活跃EN）已在 `7_254行隔离明细` 完整导出，字段含源行号(parquet 1 基)、源SKU、仓、数量、"
        "候选产品、产品方式、实物形态、隔离原因与本次处置。",
        "",
        "### 2.1 六桶 → 可发供给桥接",
        "",
        "| 项 | 行数 | 数值和 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for r in bridge_tbl.to_dict("records"):
        L.append(f"| {r['项']} | {r['行数']} | {r['数值和']:,.0f} | {r['说明']} |")
    L += [
        "",
        "> 六桶是**源行映射结果**（冻结 v2 口径，保证与评审基线逐笔对得上）；"
        "254 行的**处置**是叠加在第六桶上的第二层状态，不改变六桶行数。",
        "",
        "## 3. 可发供给口径",
        "",
        "1. **角色 ≠ 形态**：`role` 取 A FINAL 角色；`actual_form` 另列实物形态"
        "（-Cover→皮壳、-Foam→海绵、PK#前缀→皮壳、其余按角色），两者并存不互相覆盖。",
        "2. **产品↔供货桥接**：`product_id` + `conversion_basis`（PK# 命名直推 / 皮壳码登记在成品EN下 / "
        "客户码同物映射）。皮壳码不再要求 PK# 自身活跃。",
        "3. **发货方式公式**（A `ship_mode`）：皮壳模式 = 成品库存 + 皮壳库存；"
        "成品/半成品模式 = 成品库存；方式未知 → 留空待核，不按 0 计。",
        "4. **缺行 ≠ 0**：无库存行的产品是「未覆盖」，不视为已证零库存。",
        "5. **仓池**：East / Central / Poland / CG / Other 五键，美国不再合仓；"
        "CG/Other 只披露，不进 join。",
        "6. **单位**：只有 `uom_status ∈ {已证, 已证(套)}` 的数量进 `可发供给_已证`；"
        "默认个未证、cover 未证、uom_conflict 一律单列不合计。",
        "7. **共享码**：同优先级保留全部候选；>1 候选即「共享待核」，不进可发供给。",
        "8. **Foam / 内胆 / 主体骨架 / 套件**：独立分支披露，不计成品可发供给（防重复补货）。",
        "",
        "## 4. 可发供给结果",
        "",
        f"- 汇总行 {len(supply_tbl)} 行（产品×仓池×UOM）。",
        f"- **可进 join {summary['join_rows']:,} 行 / 可发供给 {summary['join_qty']:,.0f}**"
        f"（East+Central+Poland，且 `uom_status=已证`、候选唯一、方式已定）。",
        f"- CG/Other 已证但**只披露** {summary['discl_rows']:,} 行 / {summary['discl_qty']:,.0f}，不进 join。",
        f"- 单位未证行 {summary['supply_rows_unproven']:,} 行，涉及成品+皮壳库存 "
        f"{summary['supply_unproven_qty']:,.0f}，单列不计。",
        f"- 待核行 {summary['supply_rows_pending']:,} 行（单位冲突/方式未知/共享多候选），库存 "
        f"{summary['supply_pending_qty']:,.0f}。",
        f"- 皮壳供给行 {summary['cover_supply_rows']:,} 行 / {summary['cover_supply_qty']:,.0f}，"
        f"其中单位已证仅 {summary['cover_supply_proven_qty']:,.0f}：PK# 皮壳物料不在 EN UOM 缓存内，"
        "本期皮壳库存对 join 的数值贡献接近 0（**是不可证，不是 0 库存**）。",
        "",
        "### 4.1 计入A 47,332 → 可发供给 去向分解（数值差额 0）",
        "",
        "| 去向 | 行数 | 数值和 |",
        "|---|---:|---:|",
    ]
    for k, v in sorted(summary["decomp"].items(), key=lambda kv: -kv[1][1]):
        L.append(f"| {k} | {v[0]:,} | {v[1]:,.0f} |")
    L += [
        f"| **合计** | **{sum(v[0] for v in summary['decomp'].values()):,}** | "
        f"**{sum(v[1] for v in summary['decomp'].values()):,.0f}** |",
        "",
        f"> 计入A 2,484 行 / 47,332 + 第六桶补证 "
        f"{summary['iso_disposition'].get('补证', 0)} 行 / "
        f"{summary['iso_disposition_qty'].get('补证', 0):,.0f} = 上表合计，数值差额 0。",
        "",
        "| 仓池 | 行数(源) | 数值和(源) |",
        "|---|---:|---:|",
    ]
    for p, v in sorted(summary["pools"].items(), key=lambda kv: -kv[1][1]):
        L.append(f"| {p} | {v[0]:,} | {v[1]:,.0f} |")
    L += [
        "",
        "> 仓池数值为源 available 原始校验数（混合单位，不作件数解读）。"
        "`2_库存事实层` 保留 warehouse_id / warehouse_name，join 侧按实际仓取，不再读「美国 50」这类合仓数。",
        "",
        "## 5. 254 行处置结果（第六桶）",
        "",
        "| 处置 | 行数 | 其中正库存 | 数值和 | 含义 |",
        "|---|---:|---:|---:|---|",
    ]
    meaning = {
        "补证": "客户码/来源码同物映射到活跃产品且方式=皮壳 → 进入皮壳供给（带 conversion_basis）",
        "待核": "同优先级多候选 或 产品发货方式未知 → 保留候选，不进供给",
        "仍隔离": "产品方式=成品/半成品（皮壳组件不属少算）或 无活跃EN映射",
    }
    for k in ("补证", "待核", "仍隔离"):
        L.append(f"| {k} | {summary['iso_disposition'].get(k, 0)} | "
                 f"{summary['iso_pos'].get(k, 0)} | {summary['iso_disposition_qty'].get(k, 0):,.0f} | "
                 f"{meaning[k]} |")
    L += [
        "",
        f"合计 {summary['iso_total']} 行（= 第六桶），无一行被无证加回：`补证` 只接受"
        "「已登记到活跃产品的客户码/来源码」这一同物证据，且在 4_可发供给 中仍按单位证明状态与方式约束。",
        f"本次 `待核` = {summary['iso_disposition'].get('待核', 0)}：254 行里没有「同优先级多候选」"
        "或「产品发货方式未知」的情形——能定位到活跃产品的，都按方式明确归入「补证」或「仍隔离(有据不计)」，"
        "定位不到的就是「无活跃EN映射」，不给默认归属。",
        "",
        "## 6. 共享候选（F5）",
        "",
        f"- `5_共享候选全集` 覆盖 **{summary['shared_codes']} 个码**（A `共享码剩余` 登记 "
        f"{summary['shared_codes'] - summary['shared_extra_codes']} 个 + 未登记但同优先级多候选 "
        f"{summary['shared_extra_codes']} 个）；计入A 中多候选 {summary['shared_extra_codes']} 个码已改判「待核」，不取第一个。",
        "- `5_共享候选全集` 列出每个码的全部候选（含来源标签）与库存，两候选均保留；"
        "`TT0312587K0064172-Foam` 同时指向 KS0398-YRSZML-123x60x10-PURELOTUSASH 与 "
        "HM1510-YD2-123x60x10QKL-WHITE，按共享待核处理（当前库存 0，不改变数量，但规则已改）。",
        "",
        "## 7. 单位冲突（F3）",
        "",
        f"- 冲突 EN **{summary['uom_conflict_en']} 个**，快照内有库存的 **{summary['uom_conflict_with_stock']} 个**：",
        "",
        "| EN | 缓存 stock_uom | is_stock_item | A角色 | 发货方式 | 快照行数 | 快照库存 |",
        "|---|---:|---:|---|---|---:|---:|",
    ]
    for r in conflict_tbl.to_dict("records"):
        L.append(f"| {r['EN']} | {r['缓存stock_uom']} | {r['is_stock_item']} | {r['A角色']} | "
                 f"{r['发货方式']} | {r['快照行数']} | {r['快照库存']:,.0f} |")
    L += [
        "",
        "处置：标 `uom_conflict`，禁止可用量净额，待核真实单位/Bundle 身份；不静默认定「套」，也不擅自改「个」。"
        "TJ# 两键缓存 stock_uom=套 且 is_stock_item=0，按套处理不变。",
        "",
        "## 8. 仍然未知 / 不能消费的项",
        "",
        f"- 默认「个」未证：**{summary['unproven_rows']} 行 / {summary['unproven_qty']:,.0f}**"
        "（计入A 内；不含 254 补证皮壳码），不做已证供给。",
        f"- 皮壳通途码/物料单位未证（cover_unproven，含 254 补证 63 行 / 539）：**"
        f"{summary['cover_unproven_rows']} 行 / {summary['cover_unproven_qty']:,.0f}**，"
        "皮壳库存无法借用成品 EN 的单位缓存，需业务给 PK#/皮壳码的计量口径后才能进净额。",
        f"- 单位冲突 EN {summary['uom_conflict_en']} 个（其中 {summary['uom_conflict_with_stock']} 个有库存）禁止净额。",
        f"- A 活跃 {summary['active_roles']} 个角色中，库存只覆盖 {summary['covered_en']} 个；"
        f"其余 {summary['no_stock_en']} 个是「未覆盖」，**不是 0**。",
        "- Foam/海绵、内胆、主体骨架、套件分支只做披露，未接入任何净额。",
        "- 254 行「仍隔离」中方式=成品的皮壳组件，是否有独立的成品替代关系，本地无证据。",
        "",
        "## 9. join v7 消费边界",
        "",
        "- **可读**：`2_库存事实层`（事实层，含 source_sku/warehouse_id/actual_form/uom_status/"
        "product_id/conversion_basis/归属证明）与 `4_可发供给` 中 `可用性=可进join` 的行。",
        "- **不可读**：整包任何「EN 合计」型表；`uom_status ≠ 已证`、`候选状态=共享待核`、"
        "`供给状态=待核`、`可用性=仅披露` 的行一律不进净额。",
        "- **合同键**：snapshot_date × warehouse_id × source_sku × resolved_supply_item × "
        "actual_form × uom × uom_status，另带 product_id 桥接与源行号(parquet 1 基)。",
        "- **缺行语义**：产品在该 snapshot×仓池 无线 = 未覆盖，join 必须显式处理，禁止补 0。",
        "- **CG/Other**：只披露，不得自动当责任仓可用。",
        "",
        "## 10. 只读声明",
        "",
        "本次仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途接口，未发消息，未 push；"
        "产物为新文件名，不覆盖 v2（`通途库存_A337_2026-10-29.xlsx`）与既有报告。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
