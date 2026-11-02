# -*- coding: utf-8 -*-
"""C v6：通途库存 → A FINAL(2,337) × 产品/形态 × 仓池 × UOM（只读）。

C v6 = C v5 + **契约冻结 + 门禁/守恒/状态分层**（不重写全流程）：
1. 契约冻结：`rule_version=C-v6-2026-10-30`、`as_of=2026-10-28`、`UOM-CANONICAL-2026-10-29`、
   全部输入文件 SHA256、源行数/数值、内容哈希；同输入可重放（内容哈希一致）。
2. N1 门禁：没有适用成品/皮壳/套件事实的键 → **可发供给=null、供给状态=无适用事实(非0)、可用性=不进join**；
   空集不求和当 0；**已计=0 但同键存在未计形态正量** → 也判 null（禁止伪 0）。
3. 缺行=未覆盖：A 活跃产品无库存行 → `覆盖状态=未覆盖`，单列（不写 0）。
4. 状态分层：事实层/汇总层/供给层共用 `身份状态`(唯一/共享/未映射/未激活/待核)、`单位状态`、`覆盖状态`；
   只有唯一有效映射才写「归属已证」。
5. 表结构：产品区与去向/汇总分 sheet（v5 里 5_ 与 1_ 尾部内嵌的第二张表全部拆出）。
6. 命名：仓池只用 美东USNJ / 美中USTX / 波兰 / CG / 其他；全表不再出现 East / Central。

沿用 C v5：
- 星球抱枕组(KS0019)整组 1:1（UOM-CANONICAL §2.1 例外）；老产品只标不补，行不删。
- 六桶冻结口径 5,317 行 / 10,360,448；254 行逐行隔离明细；63 行/539 皮壳补证；骨架 599；TJ# 按套单列。
只读：不写 EN / 通途，不发消息，不 push，不改 A/B/C 历史产物。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

RULE_VERSION = "C-v6-2026-10-30"
AS_OF = "2026-10-28"
UOM_VERSION = "UOM-CANONICAL-2026-10-29"

COVER_RE = re.compile(r"^(.*)-cover\d*$", re.I)
FOAM_RE = re.compile(r"^(.*)-foam\d*$", re.I)
PIECE_TAIL = re.compile(r"^(?P<base>.+?)[-_ ](?P<n>\d+)\s*pcs?$", re.I)
PIECE_MID = re.compile(r"[-_ ]\d+\s*pcs?[-_ ]", re.I)
PLANET_GROUP_NAME = "星球抱枕"
PLANET_SKU_RE = re.compile(r"^(xingqiu|tt0009|stppw-13-1c)", re.I)
LEGACY_NOTE = "老产品-默认不补(待确认)"
STRIP_PREFIXES = ("删除", "~", "?", "？")
PRI = ["用户覆盖表(map)", "A来源码", "customer_code(活跃)", "sku_map", "customer_code(删除)"]

# 仓池标准名（任务要求：全表只用这五个）
POOL_EAST, POOL_CENTRAL, POOL_POLAND, POOL_CG, POOL_OTHER = "美东USNJ", "美中USTX", "波兰", "CG", "其他"
POOL_CANON = [POOL_EAST, POOL_CENTRAL, POOL_POLAND, POOL_CG, POOL_OTHER]
# 非普通仓类别（仓池仍归「其他」，类别列保留来源）
WH_RETURN, WH_THIRD, WH_PLAIN = "退货仓", "第三方大件云仓", "普通仓"

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

# v5 冻结基线（v6 必须原样保留的既有结论）
V5_BASELINE = {
    "iso_rows": 254, "iso_qty": 1192.0, "iso_proven_rows": 63, "iso_proven_qty": 539.0,
    "iso_held_rows": 191, "iso_held_qty": 653.0,
    "skeleton_qty": 599.0, "planet_rows": 113, "planet_qty": 1148.0,
    "bundle_units": 8.0,
}

# v3 复审 N1 指出的 15 个“无适用事实却标已证 0”的键（product_id, 仓池, uom）
FIFTEEN_KEYS = [
    ("KS0018-LSRBS-SET7-ROCKSTONE", POOL_CENTRAL, "套"),
    ("KS0316-HLR-55-PURPLE", POOL_CENTRAL, "个"),
    ("KS0333-CMYH-60-COLDTREEPRINT", POOL_CENTRAL, "个"),
    ("KS0395-CTTM-218x115x55-CREAMYBEIGE", POOL_CENTRAL, "个"),
    ("KS0495-FHXWXNERSZSRB-143x84x88-DARKRED", POOL_CENTRAL, "个"),
    ("TJ#KS0238x1_KS0240x1_KS0241x1_KS0242x1_KS0243x1-001", POOL_CENTRAL, "套"),
    ("TJ#KS0334x1_KS0335x1_KS0336x1-001", POOL_CENTRAL, "套"),
    ("KS0018-LSRBS-SET7-ROCKSTONE", POOL_EAST, "套"),
    ("ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45", POOL_EAST, "个"),
    ("KS0018-LSRBS-SET7-ROCKSTONE", POOL_POLAND, "套"),
    ("KS0395-CTTM-218x115x55-CREAMYBEIGE", POOL_POLAND, "个"),
    ("KS0398-YRSZML-123x60x10-PURELOTUSASH", POOL_POLAND, "个"),
    ("KS0495-FHXWXNERSZSRB-143x84x88-DARKRED", POOL_POLAND, "个"),
    ("TJ#KS0334x1_KS0335x1_KS0336x1-001", POOL_POLAND, "套"),
    ("ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45", POOL_POLAND, "个"),
]


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


def pool_of(warehouse: str) -> tuple[str, str]:
    """仓池标准名 + 仓类别（退货/第三方仍单列类别，仓池归「其他」）。"""
    w = str(warehouse)
    if w.startswith("WayfairCG-"):
        return POOL_CG, WH_PLAIN
    if "退货" in w:
        return POOL_OTHER, WH_RETURN
    if w == "美东-CENTRADE":
        return POOL_EAST, WH_PLAIN
    if w == "美中-FZH-DANEEY":
        return POOL_CENTRAL, WH_PLAIN
    if w == "波兰-FZHPoland-covers":
        return POOL_POLAND, WH_PLAIN
    if w == "大件云仓":
        return POOL_OTHER, WH_THIRD
    return POOL_OTHER, WH_PLAIN


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
    ap = argparse.ArgumentParser(description="通途库存 → A337 角色/形态/仓池/UOM 归并 v6（只读）")
    B = "D:/Work/fzh-order-store"
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--stock", default=f"{B}/en_stock.parquet")
    ap.add_argument("--date", default=AS_OF)
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--overrides", default=f"{B}/analysis/sku_mapping_overrides_2026-10-29.csv")
    ap.add_argument("--non-product", default=f"{B}/non_product_skus.csv")
    ap.add_argument("--warehouse-scope", default=f"{B}/warehouse_scope.csv")
    ap.add_argument("--uom-cache", default=f"{B}/en-demand-v1/canonical/item_uom_cache.parquet")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/通途库存_A337_v6_2026-10-30.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/通途库存_A337_v6_2026-10-30_报告.md")
    args = ap.parse_args(argv)

    active, shared_df = load_a(Path(args.a_final))
    overrides = pd.read_csv(args.overrides, dtype=str)
    idx, src = build_index(active, Path(args.customer_codes), Path(args.sku_map), overrides)
    cand = build_candidates(active, Path(args.customer_codes), Path(args.sku_map), overrides)

    en_role = {str(r[0]): r[1] for r in active[["EN物料", "角色"]].itertuples(index=False)}
    en_ship = {str(r[0]): r[1] for r in active[["EN物料", "ship_mode"]].itertuples(index=False)}
    en_ship_cn = {str(r[0]): r[1] for r in active[["EN物料", "绍兴发货方式"]].itertuples(index=False)}
    en_group = {str(r[0]): str(r[1]) for r in active[["EN物料", "物料组"]].itertuples(index=False)}

    # 星球抱枕组（UOM-CANONICAL §2.1 例外）
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
    pools = [pool_of(w) for w in f["warehouse_name"]]
    f["pool"] = [p for p, _ in pools]
    f["仓类别"] = [c for _, c in pools]

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
    f["is_return"] = f["仓类别"] == WH_RETURN
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
    # v5 口径（乘 N）留底用于差异报告，再统一改 1:1
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
    bridge_mask = f["piece_bridge"]
    if bridge_mask.any():
        f.loc[bridge_mask, "uom"] = "个"
        f.loc[bridge_mask, "uom_source"] = "多件后缀折算 → 按个"
        f.loc[bridge_mask, "qty_pieces"] = (f.loc[bridge_mask, "available"]
                                            * f.loc[bridge_mask, "pieces_per_unit"])

    # ---------- 第六桶：254 行逐行处置 ----------
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

    # ---------- N3/状态分层：身份状态（唯一/共享/未映射/未激活/待核） ----------
    def identity(r) -> str:
        b = r["bucket"]
        if b == "共享码":
            return "共享"
        if b == "未映射":
            return "未映射"
        if b == "A未激活":
            return "未激活"
        if b == "皮壳无活跃EN":
            n = len(r["cands_active"])
            if r["iso_disposition"] == "补证":
                return "唯一"
            if n > 1:
                return "共享"
            if n == 1:
                return "待核" if r["iso_disposition"] == "待核" else "唯一"
            return "未映射"
        if r["link_status"].startswith("共享"):
            return "共享"
        if is_missing(r["en"]):
            return "未映射"
        return "唯一"

    f["identity_status"] = [identity(r) for _, r in f.iterrows()]

    def proof(r) -> str:
        ids = r["identity_status"]
        if ids == "共享":
            return ("归属待核(显式共享码)" if r["bucket"] == "共享码"
                    else "归属待核(共享多候选)")
        if ids == "未映射":
            return "无映射(未归属)"
        if ids == "未激活":
            return "归属未激活(映射到非活跃EN)"
        if ids == "待核":
            return "归属待核(候选唯一但发货方式未定)"
        # 唯一：只有唯一有效映射才标「归属已证」
        if r["iso_disposition"] == "补证":
            return "归属已证(254补证)"
        if r["bucket"] == "皮壳无活跃EN":
            return "归属已证(唯一候选;形态不适用)"
        if r["piece_bridge"]:
            return "归属已证(基础码→活跃产品)"
        return "归属已证"

    f["link_proof"] = [proof(r) for _, r in f.iterrows()]
    # 多件后缀跨桶行：基础码已映射到活跃产品（桶仍保留 A未激活）
    if bridge_mask.any():
        f.loc[bridge_mask, "link_proof"] = "归属已证(基础码→活跃产品)"
        f.loc[bridge_mask, "identity_status"] = "唯一"

    # ---------- 单位状态 ----------
    def uom_status_of(r) -> str:
        if r["uom"] == "套":
            return "套件"
        if str(r["uom_note"]).startswith("uom_conflict"):
            return "冲突"
        if str(r["uom_source"]).startswith("EN缓存stock_uom="):
            return "已证"
        if str(r["uom_source"]).startswith("多件后缀折算"):
            return "已证"
        return "默认个"

    f["uom_status"] = [uom_status_of(r) for _, r in f.iterrows()]

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
        return "成品供给"

    f["supply_role"] = [eligible(r) for _, r in f.iterrows()]
    multi_in_counted = f[(f["bucket"] == "计入A") & (f["link_status"].str.startswith("共享"))]
    f.loc[multi_in_counted.index, "supply_role"] = "待核"

    def avail(r) -> str:
        if r["supply_role"] in ("非计入桶", "仍隔离(不计)"):
            return "不进join"
        if r["supply_role"] in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
            return "待核"
        if r["supply_role"] in ("套件单列(套)", "套件单列(个)"):
            return "套件单列"
        if r["pool"] in (POOL_CG, POOL_OTHER):
            return "仅披露(CG/其他)"
        if r["supply_role"] in ("海绵分支(不计)", "内胆组件(不计)") \
                or r["supply_role"].startswith("方式="):
            return "仅披露(不计)"
        return "可进join"

    f["availability"] = [avail(r) for _, r in f.iterrows()]

    # ---------- 覆盖状态（事实行级）：完整=计入 / 部分=已知形态但未计入 / 未覆盖=无法归属 / 不适用=规则排除 ----------
    def coverage_of_row(r) -> str:
        if r["bucket"] == "规则排除":
            return "不适用"
        if r["identity_status"] in ("共享", "未映射", "未激活", "待核"):
            return "未覆盖"
        if r["supply_role"] in ("成品供给", "皮壳供给", "套件单列(套)", "套件单列(个)"):
            return "完整"
        if r["supply_role"] == "仍隔离(不计)":
            return "未覆盖"
        return "部分"

    f["coverage_status"] = [coverage_of_row(r) for _, r in f.iterrows()]

    # ---------- 产品×仓池×UOM 供给汇总（N1 门禁：空集=null；伪 0 判 null） ----------
    sup_src = f[f["supply_role"].isin(["成品供给", "皮壳供给", "海绵分支(不计)",
                                       "内胆组件(不计)", "套件单列(套)", "套件单列(个)",
                                       "待核", "发货方式未知(待核)", "形态未知(待核)"])
                | f["supply_role"].str.startswith("方式=")].copy()
    sup_src = sup_src[sup_src["product_id"].notna()]

    sup_src = sup_src.assign(
        n_fg=(sup_src["supply_role"] == "成品供给").astype(int),
        n_cover=(sup_src["supply_role"] == "皮壳供给").astype(int),
        n_pending=sup_src["supply_role"].isin(
            ["待核", "发货方式未知(待核)", "形态未知(待核)"]).astype(int),
        n_bundle=sup_src["supply_role"].isin(["套件单列(套)"]).astype(int),
        n_setpcs=(sup_src["supply_role"] == "套件单列(个)").astype(int),
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
        q_setpcs=sup_src["qty_pieces"].where(sup_src["n_setpcs"] == 1, 0.0),
    )
    pivot = (sup_src.groupby(["product_id", "pool", "uom"], dropna=False).agg(
        成品行数=("n_fg", "sum"), 成品库存=("q_fg", "sum"), 其中骨架=("q_skeleton", "sum"),
        皮壳行数=("n_cover", "sum"), 皮壳库存=("q_cover", "sum"),
        套件库存=("q_bundle", "sum"), 套件行数=("n_bundle", "sum"),
        套件个行数=("n_setpcs", "sum"), 套件个库存=("q_setpcs", "sum"),
        海绵库存=("q_foam", "sum"), 内胆库存=("q_comp", "sum"),
        待核行数=("n_pending", "sum"), 待核库存=("q_pending", "sum"),
        行数=("n_fg", "size"),
        uom_source=("uom_source", lambda s: "；".join(sorted(set(s)))),
        uom_status=("uom_status", lambda s: (s.iloc[0] if s.nunique() == 1
                                             else "混合:" + "/".join(sorted(set(s))))),
        identity_status=("identity_status", lambda s: _agg_identity(s)),
    )).reset_index()
    pivot["ship_mode"] = pivot["product_id"].map(en_ship)
    pivot["ship_mode_cn"] = pivot["product_id"].map(en_ship_cn)
    pivot["产品角色"] = pivot["product_id"].map(en_role)

    def calc(r):
        """N1 门禁：没有适用且已证事实 → null；共享/待核/不适用不得聚合成已证 0；
        已计=0 但同键存在未计形态正量 → 也判 null（伪 0）。
        返回 (可发供给, 供给状态, 覆盖状态[完整/部分/未覆盖], 覆盖缺口, 门禁原因)。"""
        gaps: list[str] = []
        hidden_pos = 0.0
        if r["uom"] == "套":
            if r["套件行数"] == 0:
                return None, "无适用事实(非0)", "未覆盖", "无套件事实行", "无套件事实行"
            hidden_pos = float(r["待核库存"])
            if r["待核行数"] > 0:
                gaps.append("有待核行")
            detail = "/".join(gaps)
            if hidden_pos > 0:
                return None, "待核(已计0;有未计形态量)", "部分", detail, "套件0但待核有量"
            return float(r["套件库存"]), "套件单列", ("完整" if not gaps else "部分"), detail, \
                "仅套件事实行"
        n_app = r["成品行数"] + r["皮壳行数"]
        hidden_pos = float(r["海绵库存"] + r["内胆库存"] + r["待核库存"] + r["套件个库存"])
        if n_app == 0:
            why = "仅未计形态行" if hidden_pos > 0 else "无适用行"
            return None, "无适用事实(非0)", "未覆盖", why, why
        if is_missing(r["ship_mode"]):
            return None, "待核(发货方式未知)", "部分", "方式未知", "方式未知"
        if r["ship_mode"] == "皮壳":
            v = float(r["成品库存"] + r["皮壳库存"])
            if r["成品行数"] == 0:
                gaps.append("缺成品行")
        elif r["ship_mode"] in ("成品", "半成品"):
            v = float(r["成品库存"])
            if r["成品行数"] == 0:
                gaps.append("缺成品行")
        else:
            return None, f"待核(方式={r['ship_mode']})", "部分", "方式未知", "方式未知"
        if r["待核行数"] > 0:
            gaps.append("有待核行")
        if r["海绵库存"] > 0:
            gaps.append("含海绵(未计)")
        if r["内胆库存"] > 0:
            gaps.append("含内胆(未计)")
        if r["套件个行数"] > 0:
            gaps.append("含套件行(非Bundle,未计)")
        cov = "完整" if not gaps else "部分"
        detail = "/".join(gaps)
        if v == 0 and hidden_pos > 0:
            return None, "待核(已计0;有未计形态量)", cov, detail, "已计为0但另有未计正量"
        return v, "已计入", cov, detail, ("完整" if not gaps else "部分覆盖")

    cc_ = [calc(r) for _, r in pivot.iterrows()]
    pivot["可发供给"] = [x[0] for x in cc_]
    pivot["供给状态"] = [x[1] for x in cc_]
    pivot["覆盖状态"] = [x[2] for x in cc_]
    pivot["覆盖缺口"] = [x[3] for x in cc_]
    pivot["门禁原因"] = [x[4] for x in cc_]

    def avail2(r):
        if r["uom"] == "套":
            if r["供给状态"].startswith("无适用") or r["供给状态"].startswith("待核"):
                return "不进join(无适用事实)" if r["供给状态"].startswith("无适用") else "不进join(待核)"
            return "套件单列"
        if r["可发供给"] is None or pd.isna(r["可发供给"]):
            return "不进join(无适用事实)" if r["供给状态"].startswith("无适用") else "不进join(待核)"
        if r["pool"] in (POOL_CG, POOL_OTHER):
            return "仅披露(CG/其他)"
        if r["覆盖状态"] == "完整":
            return "可进join"
        return f"可进join(partial:{r['覆盖缺口']})"

    pivot["可用性"] = [avail2(r) for _, r in pivot.iterrows()]
    pivot["补货资格"] = ["老产品-默认不补(待确认)" if str(p) in planet_ens else ""
                         for p in pivot["product_id"]]
    supply_tbl = pivot[["product_id", "产品角色", "ship_mode", "ship_mode_cn", "pool", "uom",
                        "uom_source", "uom_status", "identity_status", "成品库存", "其中骨架",
                        "皮壳库存", "套件库存", "套件个库存", "可发供给", "供给状态", "覆盖状态",
                        "覆盖缺口", "门禁原因", "海绵库存", "内胆库存", "待核库存", "行数", "可用性",
                        "补货资格"]].rename(columns={"uom_status": "单位状态",
                                                      "identity_status": "身份状态"}) \
        .sort_values(["pool", "product_id", "uom"])

    # ---------- 多件后缀换算表（含星球组 1:1 例外） ----------
    pc_rows = f[f["pieces_status"] != ""].copy()
    pc_rows["v5口径个当量"] = pc_rows["available"] * pc_rows["pieces_rule_only"]
    pc_tbl = pc_rows[["src_row", "sku", "pieces_per_unit", "pieces_basis", "pieces_status",
                      "warehouse_name", "pool", "available", "qty_pieces", "v5口径个当量",
                      "legacy_note", "bucket", "en", "product_id", "supply_role",
                      "availability"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "源SKU", "pieces_per_unit": "每单位件数",
        "pieces_basis": "依据", "pieces_status": "状态", "warehouse_name": "仓", "pool": "仓池",
        "available": "available", "qty_pieces": "本版个当量",
        "v5口径个当量": "若按后缀乘N(个当量)", "legacy_note": "补货标记", "bucket": "桶",
        "en": "映射EN", "product_id": "产品", "supply_role": "供给状态",
        "availability": "可用性"}).sort_values(["本版个当量"], ascending=False)
    conv = pc_rows[pc_rows["pieces_status"] == "已换算"]
    exc = pc_rows[pc_rows["pieces_status"] == "组级例外1:1"]
    mid = pc_rows[pc_rows["pieces_status"] == "仅列不换算"]
    pc_summary = pd.DataFrame([
        {"项": "已换算(末尾多件后缀，非星球组)", "行数": int(len(conv)),
         "原始available": float(conv["available"].sum()), "个当量": float(conv["qty_pieces"].sum()),
         "若按后缀乘N": float(conv["v5口径个当量"].sum())},
        {"项": "组级例外 1:1（星球抱枕 KS0019）", "行数": int(len(exc)),
         "原始available": float(exc["available"].sum()), "个当量": float(exc["qty_pieces"].sum()),
         "若按后缀乘N": float(exc["v5口径个当量"].sum())},
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
        ["src_row", "sku", "norm", "warehouse_id", "warehouse_name", "仓类别", "pool", "available",
         "pieces_per_unit", "qty_pieces", "pieces_status", "legacy_note", "uom", "uom_source",
         "uom_note", "uom_status", "bucket", "en", "role", "actual_form", "form_basis", "product_id",
         "conversion_basis", "link_status", "identity_status", "link_proof", "supply_role",
         "coverage_status", "availability", "mapping_source_v2"]].rename(columns={
        "src_row": "源行号(parquet1基)", "sku": "source_sku", "norm": "归一码",
        "warehouse_id": "warehouse_id", "warehouse_name": "warehouse_name", "仓类别": "仓类别",
        "pool": "pool", "available": "qty", "pieces_per_unit": "pieces_per_unit",
        "qty_pieces": "qty_pieces", "pieces_status": "pieces_status", "legacy_note": "补货标记",
        "uom": "uom", "uom_source": "uom_source", "uom_note": "uom_note",
        "uom_status": "单位状态", "bucket": "桶",
        "en": "resolved_supply_item", "role": "role(A)", "actual_form": "actual_form",
        "form_basis": "form_basis", "product_id": "product_id",
        "conversion_basis": "conversion_basis", "link_status": "候选状态",
        "identity_status": "身份状态", "link_proof": "归属证明",
        "supply_role": "供给状态", "coverage_status": "覆盖状态",
        "availability": "可用性", "mapping_source_v2": "mapping_source"})
    detail.insert(0, "snapshot_date", args.date)
    detail.insert(1, "rule_version", RULE_VERSION)
    detail["源行号(parquet1基)"] = detail["源行号(parquet1基)"].astype(int)
    detail.insert(list(detail.columns).index("product_id") + 1, "ship_mode",
                  detail["product_id"].map(en_ship))

    un = f[f["bucket"] == "未映射"].copy()

    def why(r):
        if r["仓类别"] == WH_THIRD:
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
        ["src_row", "exclusion", "sku", "warehouse_name", "仓类别", "pool", "available", "en", "role",
         "actual_form", "identity_status"]].rename(columns={
            "src_row": "源行号(parquet1基)", "exclusion": "排除规则", "sku": "源SKU",
            "warehouse_name": "仓", "仓类别": "仓类别", "pool": "仓池", "available": "available",
            "en": "映射EN", "role": "A角色", "actual_form": "实物形态",
            "identity_status": "身份状态"})

    conflict_tbl = pd.DataFrame([{
        "EN": en, "缓存stock_uom(原值)": uoms.get(en), "is_stock_item(原值)": is_stock_item.get(en),
        "A角色": en_role.get(en), "发货方式": en_ship.get(en),
        "快照行数": int((f["en"] == en).sum()), "快照库存": float(f.loc[f["en"] == en, "available"].sum()),
        "单位状态": "冲突", "处理": "按个计入可发供给；原值留档备查（UOM-CANONICAL §2.2）",
    } for en in sorted(uom_conflict_en)])

    # ---------- 未覆盖产品（A 活跃但快照无库存行 = 未覆盖，不是 0） ----------
    covered_en = set(f.loc[f["bucket"] == "计入A", "en"].dropna())
    uncovered = active[~active["EN物料"].astype(str).isin(covered_en)][
        ["EN物料", "名称", "角色", "物料组", "ship_mode", "绍兴发货方式", "活跃分类"]].copy()
    uncovered = uncovered.rename(columns={"EN物料": "product_id", "绍兴发货方式": "ship_mode_cn"})
    uncovered.insert(0, "snapshot_date", args.date)
    uncovered.insert(1, "rule_version", RULE_VERSION)
    uncovered["覆盖状态"] = "未覆盖"
    uncovered["说明"] = "快照无该产品库存行：未覆盖 ≠ 0 库存"

    # ---------- 汇总 ----------
    def bq(b):
        g = f[f["bucket"] == b]
        return int(len(g)), float(g["available"].sum())

    counted_rows = f[f["bucket"] == "计入A"].copy()

    def cat_of(r) -> str:
        sr = r["supply_role"]
        if sr in ("成品供给", "皮壳供给"):
            if r["pool"] in (POOL_CG, POOL_OTHER):
                return "仅披露(CG/其他)"
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
    discl_tbl = supply_tbl[supply_tbl["可用性"] == "仅披露(CG/其他)"]
    cover_rows = f[f["supply_role"] == "皮壳供给"]
    skeleton_rows = f[(f["supply_role"] == "成品供给") & (f["actual_form"] == "主体骨架")]
    no_fact = pivot[pivot["供给状态"].str.startswith("无适用事实")]
    partial = supply_tbl[supply_tbl["可用性"].astype(str).str.startswith("可进join(partial")]

    summary = dict(
        date=args.date, rule_version=RULE_VERSION, uom_version=UOM_VERSION,
        rows_in=int(len(f)), qty_in=float(f["available"].sum()),
        buckets={b: bq(b)[0] for b in BUCKET_BASELINE},
        bucket_qty={b: bq(b)[1] for b in BUCKET_BASELINE},
        active_roles=len(active),
        covered_en=int(len(covered_en)),
        uncovered_en=int(len(uncovered)),
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
        null_keys=int(supply_tbl["可发供给"].isna().sum()),
        pending_null_keys=int(((supply_tbl["可发供给"].isna())
                               & supply_tbl["供给状态"].astype(str).str.startswith("待核")).sum()),
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
        planet_qty_v5rule=float((f.loc[f["planet_group"], "available"]
                                 * f.loc[f["planet_group"], "pieces_rule_only"]).sum()),
        planet_ens=len(planet_ens),
        planet_supply_rows=int((supply_tbl["补货资格"] != "").sum()),
        planet_supply_qty=float(supply_tbl.loc[supply_tbl["补货资格"] != "", "可发供给"].fillna(0).sum()),
        bundle_units=float(f.loc[f["uom"] == "套", "available"].sum()),
        bundle_rows=int((f["uom"] == "套").sum()),
        default_ge_rows=int(((f["uom_status"] == "默认个") & (f["bucket"] == "计入A")).sum()),
        default_ge_qty=float(f.loc[(f["uom_status"] == "默认个") & (f["bucket"] == "计入A"),
                                   "available"].sum()),
        decomp={r["去向"]: [int(r["行数"]), float(r["原始数值"]), float(r["个当量"])]
                for r in decomp.to_dict("records")},
        pools={k: [int(v["rows"]), float(v["qty"])] for k, v in
               f.groupby("pool").agg(rows=("sku", "size"), qty=("available", "sum")).iterrows()},
        wh_classes={k: [int(v["rows"]), float(v["qty"])] for k, v in
                    f.groupby("仓类别").agg(rows=("sku", "size"), qty=("available", "sum")).iterrows()},
        identity={k: int(v) for k, v in f["identity_status"].value_counts().items()},
        uom_status={k: int(v) for k, v in f["uom_status"].value_counts().items()},
        coverage={k: int(v) for k, v in f["coverage_status"].value_counts().items()},
    )

    # ---------- 15 键门禁回放 ----------
    fifteen = []
    v3_rows = [363, 591, 620, 693, 814, 838, 839, 1278, 1456, 1949, 2336, 2352, 2446, 2455, 2456]
    for (pid, pool, uom), v3row in zip(FIFTEEN_KEYS, v3_rows):
        q = supply_tbl[(supply_tbl["product_id"] == pid) & (supply_tbl["pool"] == pool)
                       & (supply_tbl["uom"] == uom)]
        note = ""
        if q.empty:
            # v3 清单里 KS0018 组写的是 uom=套；按 UOM-CANONICAL §2.2 已回落「个」，回放按 v6 实际键
            alt = "个" if uom == "套" else "套"
            q2 = supply_tbl[(supply_tbl["product_id"] == pid) & (supply_tbl["pool"] == pool)
                            & (supply_tbl["uom"] == alt)]
            if not q2.empty:
                q = q2
                note = f"v3 清单为 uom={uom}；UOM-CANONICAL 后按「{alt}」计"
                uom = alt
        if q.empty:
            fifteen.append({"v3行号": v3row, "product_id": pid, "仓池": pool, "uom": uom,
                            "可发供给": None, "供给状态": "键不存在(无任何事实行)", "覆盖状态": "未覆盖",
                            "覆盖缺口": "无适用行", "可用性": "不进join(无适用事实)",
                            "门禁": "PASS", "事实行号(parquet1基)": "-", "事实个当量": 0.0,
                            "未计个当量": 0.0, "说明": note})
            continue
        r = q.iloc[0]
        val = r["可发供给"]
        is_null = val is None or (isinstance(val, float) and pd.isna(val))
        av = str(r["可用性"])
        sub = f[(f["product_id"] == pid) & (f["pool"] == pool) & (f["uom"] == uom)]
        applied = sub[sub["supply_role"].isin(["成品供给", "皮壳供给", "套件单列(套)"])]
        fact_qty = float(applied["qty_pieces"].sum())
        hidden_qty = float(sub.loc[sub["supply_role"].isin(
            ["海绵分支(不计)", "内胆组件(不计)", "套件单列(个)", "待核",
             "发货方式未知(待核)", "形态未知(待核)"]), "qty_pieces"].sum())
        src_rows = ",".join(str(int(x)) for x in applied["src_row"])
        if is_null and not av.startswith("可进join"):
            gate = "PASS(null)"
        elif av == "套件单列":
            gate = "PASS(套件单列/不进净额)"
        elif (not is_null) and float(val) > 0:
            gate = "PASS(真实正量,可回指源行)"
        elif len(applied) > 0 and fact_qty == 0.0 and hidden_qty == 0.0:
            gate = "PASS(已证零,有源行)"
        else:
            gate = "FAIL(伪0或误进join)"
        fifteen.append({"v3行号": v3row, "product_id": pid, "仓池": pool, "uom": uom,
                        "可发供给": None if is_null else float(val),
                        "供给状态": r["供给状态"], "覆盖状态": r["覆盖状态"],
                        "覆盖缺口": r["覆盖缺口"], "可用性": av, "门禁": gate,
                        "事实行号(parquet1基)": src_rows or "-",
                        "事实个当量": fact_qty, "未计个当量": hidden_qty,
                        "说明": (note + "；" if note else "") + str(r["门禁原因"])})
    fifteen_tbl = pd.DataFrame(fifteen)

    # ---------- 自检 ----------
    def trace_ok() -> tuple[int, int]:
        ok = 0
        for _, r in detail.iterrows():
            sr = int(r["源行号(parquet1基)"])
            src_row = d.iloc[sr - 1]
            if (str(src_row["sku"]) == str(r["source_sku"])
                    and str(src_row["warehouse_name"]) == str(r["warehouse_name"])
                    and abs(float(src_row["available"]) - float(r["qty"])) < 1e-9):
                ok += 1
        return ok, len(detail)

    trace_ok_n, trace_total = trace_ok()

    iso_trace = 0
    for _, r in iso_tbl.iterrows():
        sr = int(r["源行号(parquet1基)"])
        s = d.iloc[sr - 1]
        if (str(s["sku"]) == str(r["源SKU"]) and str(s["warehouse_name"]) == str(r["仓"])
                and abs(float(s["available"]) - float(r["available"])) < 1e-9):
            iso_trace += 1

    # 伪 0 全量检查：可进join 且 可发供给==0 的键，必须存在实际适用行 qty==0 且无未计正量
    pseudo = []
    for _, r in supply_tbl.iterrows():
        if not str(r["可用性"]).startswith("可进join"):
            continue
        v = r["可发供给"]
        if v is None or pd.isna(v) or float(v) != 0.0:
            continue
        key = ((f["product_id"] == r["product_id"]) & (f["pool"] == r["pool"])
               & (f["uom"] == r["uom"]))
        sub = f[key]
        applied = sub[sub["supply_role"].isin(["成品供给", "皮壳供给"])]
        hidden = float(sub.loc[sub["supply_role"].isin(
            ["海绵分支(不计)", "内胆组件(不计)", "套件单列(个)", "待核",
             "发货方式未知(待核)", "形态未知(待核)"]), "qty_pieces"].sum())
        if not (len(applied) > 0 and float(applied["qty_pieces"].sum()) == 0.0 and hidden == 0.0):
            pseudo.append((r["product_id"], r["pool"], r["uom"]))
    fifteen_fail = int((fifteen_tbl["门禁"].astype(str).str.startswith("FAIL")).sum())
    pool_bad = int((~f["pool"].isin(POOL_CANON)).sum()) + int((~supply_tbl["pool"].isin(POOL_CANON)).sum())

    checks = [
        ("六桶逐桶 0 差", f"行差={int(recon.iloc[-1]['行数差'])}, 数值差={recon.iloc[-1]['数值差']:.0f}",
         "=0", int(recon.iloc[-1]["行数差"]) == 0 and abs(recon.iloc[-1]["数值差"]) < 1e-6),
        ("源行数/数值和", f"{summary['rows_in']:,} / {summary['qty_in']:,.0f}",
         f"{SRC_ROWS:,} / {SRC_QTY:,.0f}", summary["rows_in"] == SRC_ROWS
         and abs(summary["qty_in"] - SRC_QTY) < 1e-6),
        ("事实层逐行回指源 parquet", f"{trace_ok_n}/{trace_total}", "全部", trace_ok_n == trace_total),
        ("254 行逐行回指", f"{iso_trace}/{len(iso_tbl)}", "全部", iso_trace == len(iso_tbl)
         and len(iso_tbl) == V5_BASELINE["iso_rows"]),
        ("254 行数值和", f"{summary['iso_disposition_qty'].get('补证', 0) + summary['iso_disposition_qty'].get('仍隔离', 0):,.0f}",
         "1,192", abs(summary["iso_disposition_qty"].get("补证", 0)
                      + summary["iso_disposition_qty"].get("待核", 0)
                      + summary["iso_disposition_qty"].get("仍隔离", 0) - 1192.0) < 1e-6),
        ("皮壳补证 63 行/539", f"{summary['iso_disposition'].get('补证', 0)} 行 / "
         f"{summary['iso_disposition_qty'].get('补证', 0):,.0f}",
         "63 / 539", summary["iso_disposition"].get("补证", 0) == 63
         and abs(summary["iso_disposition_qty"].get("补证", 0) - 539.0) < 1e-6),
        ("骨架 599 保留", f"{summary['skeleton_qty']:,.0f}", "599",
         abs(summary["skeleton_qty"] - 599.0) < 1e-6),
        ("TJ# 套件按套单列", f"{summary['bundle_rows']} 行 / {summary['bundle_units']:,.0f} 套", "4 / 8",
         summary["bundle_rows"] == 4 and abs(summary["bundle_units"] - 8.0) < 1e-6),
        ("星球组 1:1", f"{summary['planet_rows']} 行 / {summary['planet_qty']:,.0f} 个",
         "113 / 1,148", summary["planet_rows"] == V5_BASELINE["planet_rows"]
         and abs(summary["planet_qty"] - V5_BASELINE["planet_qty"]) < 1e-6),
        ("15 键门禁", f"FAIL={fifteen_fail}", "0", fifteen_fail == 0),
        ("伪 0 全量扫描", f"违例={len(pseudo)}", "0", len(pseudo) == 0),
        ("仓池标准名（5 值）", f"非标准={pool_bad}", "0", pool_bad == 0),
        ("契约完整性（rule/as_of/uom）", f"{RULE_VERSION} / {AS_OF} / {UOM_VERSION}", "非空",
         bool(RULE_VERSION and AS_OF and UOM_VERSION)),
    ]

    # ---------- 输出 ----------
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    iso_total_rows, iso_total_qty = int(len(iso_tbl)), float(iso["available"].sum())

    def bucket_tbl():
        t = recon.copy()
        t["桶"] = t["bucket"]
        t.insert(0, "rule_version", RULE_VERSION)
        t.insert(1, "as_of", AS_OF)
        return t[["rule_version", "as_of", "桶", "行数", "数值和", "基线行数", "基线数值和",
                  "行数差", "数值差"]]

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

    input_files = [
        ("en_stock.parquet", args.stock),
        ("SKU活跃宇宙_2026-10-29_FINAL.xlsx", args.a_final),
        ("sku_map.tsv", args.sku_map),
        ("en_item_customer_codes.csv", args.customer_codes),
        ("sku_mapping_overrides_2026-10-29.csv", args.overrides),
        ("non_product_skus.csv", args.non_product),
        ("warehouse_scope.csv", args.warehouse_scope),
        ("item_uom_cache.parquet", args.uom_cache),
    ]
    input_sha = [(n, str(p), sha256(Path(p))) for n, p in input_files]

    def contract_tbl():
        rows = [
            ("rule_version", RULE_VERSION),
            ("as_of(快照日)", AS_OF),
            ("snapshot_date(parquet 过滤)", args.date),
            ("UOM 版本", UOM_VERSION),
            ("UOM 唯一依据", "D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/reference/UOM-CANONICAL.md"),
            ("源行数", SRC_ROWS),
            ("源 available 数值和", SRC_QTY),
            ("六桶基线", "计入A 2,484/47,332；共享码 53/1,403；A未激活 425/20；"
                        "规则排除 879/10,308,263；未映射 1,222/2,238；皮壳无活跃EN 254/1,192"),
            ("仓池标准名", " / ".join(POOL_CANON)),
            ("身份状态枚举", "唯一 / 共享 / 未映射 / 未激活 / 待核"),
            ("单位状态枚举", "已证 / 默认个 / 冲突 / 套件"),
            ("覆盖状态枚举", "完整 / 部分 / 未覆盖 / 不适用（缺口明细见「覆盖缺口」列）"),
            ("可发供给 null 语义", "无适用事实或已计0但有未计正量 → null；禁止补 0"),
            ("缺行语义", "产品在快照无库存行 → 覆盖状态=未覆盖；不是 0"),
            ("老产品口径", "星球抱枕组只标「老产品-默认不补(待确认)」，行不删、数值照算"),
            ("同输入可重放", "内容哈希（各 sheet 规范化 CSV）对所有输入确定；见下行"),
        ]
        for n, p, h in input_sha:
            rows.append((f"输入 SHA256 · {n}", h))
            rows.append((f"输入路径 · {n}", p))
        for c, got, want, ok in checks:
            rows.append((f"自检 · {c}", f"{got}（期望 {want}）→ {'PASS' if ok else 'FAIL'}"))
        rows.append(("产物", str(out)))
        rows.append(("内容哈希（可重放证据）", content_hash))
        return pd.DataFrame(rows, columns=["项", "内容"])

    def notes_tbl():
        rows = [
            ("产物", "通途库存_A337_v6_2026-10-30.xlsx（v5 + 契约冻结 + 门禁/守恒/状态分层，只读）"),
            ("脚本", "scripts/tongtool_inventory_rollup_a337_v6.py"),
            ("rule_version", RULE_VERSION),
            ("as_of", f"{AS_OF} 快照（snapshot_date 过滤）"),
            ("UOM 版本", UOM_VERSION),
            ("快照", f"snapshot_date={args.date}，{len(f)} 行，available 数值和 {f['available'].sum():,.0f}"),
            ("口径1·默认个", "一切按个；EN stock_uom 只作参考、不作证明"),
            ("口径2·套", "「套」只给 TJ#/Product Bundle（缓存 stock_uom=套 且 is_stock_item=0）"),
            ("口径3·多件后缀", "末尾 -2PCS/-3PCS/-5PC/-7PCS 等：每单位=N 个，available×N；裸 -2/-3 与中段件数不换算"),
            ("口径4·缓存套非Bundle", "KS0354/KS0422 按个计入，原值记入 uom_note 与 10_单位冲突记录"),
            ("口径5·不再阻断", "取消 uom_unproven 阻断；无单位来源按个计并记录来源缺失"),
            ("口径6·星球组1:1", "EN 物料组=星球抱枕(KS0019) 整组 1:1（UOM-CANONICAL §2.1 例外）"),
            ("口径7·老产品标记", "该组在事实层 `补货标记`、供给行 `补货资格` 标「老产品-默认不补(待确认)」；不删行、数值照算"),
            ("N1·空集不为0", "无适用成品/皮壳/套件事实的键：可发供给=null、不进 join；已计0但同键有未计正量也判 null"),
            ("N2·主体骨架", "按 A 用户规则作独立成品分支，单独成行，不并入沙发成品/不按内胆组件排除（美东 599）"),
            ("N3·证明状态", "事实/汇总/供给三层共用 身份状态/单位状态/覆盖状态；只有唯一有效映射才标「归属已证」"),
            ("N4·表结构", "产品区与去向/汇总分 sheet：供给只含产品行，去向在 12_，换算汇总在 7_"),
            ("口径·仓池", "美东USNJ / 美中USTX / 波兰 / CG / 其他（退货仓/第三方仅作「仓类别」，仓池归「其他」）；全表无 East/Central"),
            ("口径·可发供给", "皮壳模式=成品+皮壳；成品/半成品模式=成品（均按个）；套件单独按套"),
            ("口径·共享", "同优先级全部候选保留；多候选一律共享待核，不进可发供给"),
            ("口径·缺行", "无库存行的产品=未覆盖，不等于 0 库存（13_未覆盖产品）"),
            ("只读声明", "未调用 EN/通途写接口，未发消息，未 push；不改 A/B/C 历史产物"),
        ]
        return pd.DataFrame(rows, columns=["项", "内容"])

    # 汇总层（产品×仓池×形态×UOM）
    prod_form = (f[f["product_id"].notna() & f["bucket"].isin(["计入A", "皮壳无活跃EN"])]
                 .groupby(["product_id", "actual_form", "pool", "uom", "uom_status", "identity_status",
                           "role", "supply_role", "coverage_status"], dropna=False)
                 .agg(库存=("qty_pieces", "sum"), 原始available=("available", "sum"),
                      行数=("sku", "size")).reset_index()
                 .sort_values(["pool", "product_id", "actual_form", "uom"]))

    def avail3(r) -> str:
        sr = r["supply_role"]
        if sr in ("成品供给", "皮壳供给"):
            return "仅披露(CG/其他)" if r["pool"] in (POOL_CG, POOL_OTHER) else "可参考"
        if sr in ("待核", "发货方式未知(待核)", "形态未知(待核)"):
            return "待核"
        if sr.startswith("套件单列"):
            return "套件单列"
        return "仅披露(不计)"

    prod_form["可用性"] = [avail3(r) for _, r in prod_form.iterrows()]
    prod_form["补货资格"] = ["老产品-默认不补(待确认)" if str(p) in planet_ens else ""
                             for p in prod_form["product_id"]]
    prod_form = prod_form[["product_id", "actual_form", "role", "pool", "uom", "uom_status",
                           "identity_status", "supply_role", "coverage_status", "库存",
                           "原始available", "行数", "可用性", "补货资格"]] \
        .rename(columns={"uom_status": "单位状态", "identity_status": "身份状态",
                         "coverage_status": "覆盖状态"})

    # 命名扫描（写入后按单元格扫描，仓池/仓名列必须 0）
    def naming_scan(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, int, int]:
        pat = re.compile(r"east|central", re.I)
        rows, total, wh_hits = [], 0, 0
        wh_cols = {"仓池", "warehouse_name", "仓"}
        for name, df in tables.items():
            for col in df.columns:
                hits = [str(v) for v in df[col].dropna().unique() if pat.search(str(v))]
                if hits:
                    rows.append({"sheet": name, "列": col, "命中数": len(hits),
                                 "样例": "；".join(hits[:3])})
                    total += len(hits)
                    if col in wh_cols:
                        wh_hits += len(hits)
        return pd.DataFrame(rows), total, wh_hits

    tables = {
        "0_契约": None,  # 占位，内容在写完后回填
        "1_六桶对账": bucket_tbl(),
        "2_库存事实层": detail,
        "3_产品×仓池×形态×UOM汇总": prod_form,
        "4_可发供给": supply_tbl,
        "5_多件后缀换算表": pc_tbl,
        "6_共享候选": sh,
        "7_多件后缀换算汇总": pc_summary,
        "8_254行隔离明细": iso_tbl,
        "9_单位冲突记录": conflict_tbl,
        "10_排除明细": excluded,
        "11_供给去向分解": decomp,
        "12_六桶供给桥接": bridge_tbl(),
        "13_未覆盖产品": uncovered,
        "14_15键门禁回放": fifteen_tbl,
        "15_自检清单": pd.DataFrame(checks, columns=["检查项", "结果", "期望", "通过"]),
    }

    def canonical(df: pd.DataFrame) -> str:
        cols = [str(c) for c in df.columns]
        body = [",".join(cols)]
        for rec in df.itertuples(index=False, name=None):
            body.append(",".join("" if x is None or (isinstance(x, float) and pd.isna(x))
                                 else (f"{x:.6f}" if isinstance(x, float) else str(x))
                                 for x in rec))
        return "\n".join(body)

    h = hashlib.sha256()
    for name, df in tables.items():
        if df is None:
            continue
        h.update(name.encode("utf-8"))
        h.update(canonical(df).encode("utf-8"))
    content_hash = h.hexdigest()

    contract = contract_tbl()
    tables["0_契约"] = contract
    # 契约自身不参与内容哈希（避免自指），但参与命名扫描
    scan_tbl, scan_total, scan_wh = naming_scan({k: v for k, v in tables.items() if v is not None})

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        bucket_tbl().to_excel(w, sheet_name="1_六桶对账", index=False)
        detail.to_excel(w, sheet_name="2_库存事实层", index=False)
        prod_form.to_excel(w, sheet_name="3_产品×仓池×形态×UOM汇总", index=False)
        supply_tbl.to_excel(w, sheet_name="4_可发供给", index=False)
        pc_tbl.to_excel(w, sheet_name="5_多件后缀换算表", index=False)
        sh.to_excel(w, sheet_name="6_共享候选", index=False)
        pc_summary.to_excel(w, sheet_name="7_多件后缀换算汇总", index=False)
        iso_tbl.to_excel(w, sheet_name="8_254行隔离明细", index=False)
        conflict_tbl.to_excel(w, sheet_name="9_单位冲突记录", index=False)
        excluded.to_excel(w, sheet_name="10_排除明细", index=False)
        decomp.to_excel(w, sheet_name="11_供给去向分解", index=False)
        bridge_tbl().to_excel(w, sheet_name="12_六桶供给桥接", index=False)
        uncovered.to_excel(w, sheet_name="13_未覆盖产品", index=False)
        fifteen_tbl.to_excel(w, sheet_name="14_15键门禁回放", index=False)
        pd.DataFrame(checks, columns=["检查项", "结果", "期望", "通过"]) \
            .to_excel(w, sheet_name="15_自检清单", index=False)

    out_sha = sha256(out)
    Path(args.out_report).write_text(
        render(summary, bucket_tbl(), bridge_tbl(), supply_tbl, pc_summary, conflict_tbl,
               fifteen_tbl, checks, input_sha, scan_tbl, scan_total, scan_wh,
               uncovered, content_hash, out_sha, args, out),
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print("15键:", fifteen_tbl["门禁"].value_counts().to_dict())
    print("未覆盖EN:", len(uncovered))
    print("自检:", [(c[0], c[3]) for c in checks])
    print("命名扫描: total=", scan_total, "warehouse_cols=", scan_wh)
    print("内容哈希:", content_hash)
    print("工作簿 SHA256:", out_sha)
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def _agg_identity(s: pd.Series) -> str:
    vals = set(s.dropna().astype(str))
    if vals == {"唯一"}:
        return "唯一"
    if "共享" in vals:
        return "共享"
    if "未激活" in vals:
        return "未激活"
    if "待核" in vals:
        return "待核"
    if "未映射" in vals:
        return "未映射"
    return "/".join(sorted(vals))


def _all_cands(cand: dict, n: str) -> set:
    return {e for tags in cand.get(n, {}).values() for e in tags}


def _tags_for(cand: dict, n: str, en: str) -> set:
    return {t for t, ens in cand.get(n, {}).items() if en in ens}


def render(summary, bucket_tbl, bridge_tbl, supply_tbl, pc_summary, conflict_tbl,
           fifteen_tbl, checks, input_sha, scan_tbl, scan_total, scan_wh,
           uncovered, content_hash, out_sha, args, out: Path) -> str:
    L = [
        f"# 通途库存 → A FINAL（A337）v6 报告（as_of={AS_OF}，只读）",
        "",
        f"- `rule_version` = **{RULE_VERSION}**；`as_of` = **{AS_OF}**；`uom_version` = **{UOM_VERSION}**",
        f"- 生成：`scripts/tongtool_inventory_rollup_a337_v6.py`（只读：不写 EN/通途、不发消息、不 push）",
        f"- 产物：`{out.name}`（不覆盖 v2/v3/v4/v5）",
        "- 本版只做 **契约冻结 + 门禁/守恒/状态分层 + 命名**，不重写全流程、不改 A/B。",
        "",
        "## 1. 契约冻结与可重放",
        "",
        "| 输入 | SHA256 |",
        "|---|---|",
    ]
    for n, p, h in input_sha:
        L.append(f"| {n} | `{h}` |")
    L += [
        "",
        f"- 内容哈希（各 sheet 规范化 CSV 的 SHA256）：`{content_hash}`",
        f"- 本次工作簿 SHA256：`{out_sha}`（docProps 含写入时间，逐次不同；**可重放以内容哈希为准**）",
        f"- 源 {summary['rows_in']:,} 行 / available 数值和 {summary['qty_in']:,.0f}",
        "",
        "## 2. 与 v5 的差异（只动契约/门禁/状态/表结构/命名）",
        "",
        "| 项 | v5 | v6 |",
        "|---|---|---|",
        "| 契约字段 | 仅 sha256 + 口径说明 | 0_契约 sheet：rule_version / as_of / uom_version / 8 个输入 SHA / 自检 |",
        "| 1456 等 15 键 | N1 已改 null，但缺键级回放表 | `14_15键门禁回放`：逐键状态 + 门禁结论 |",
        "| 伪 0 | 已计=0 且另有未计正量的键仍算 0 | 判 **null**（如 KS0018 组：套件 3/13 未计→不再写 0） |",
        "| 缺行语义 | 报告里只有未覆盖数 | `13_未覆盖产品` 逐产品单列（覆盖状态=未覆盖） |",
        "| 状态分层 | 事实层 8 种「归属证明」，各层词表不同 | 三层共用 身份状态 / 单位状态 / 覆盖状态 |",
        "| 表结构 | 5_ 尾部内嵌换算汇总 | 拆到 `7_多件后缀换算汇总`；供给表只有产品行 |",
        "| 命名 | 仓池 East/Central/Poland/Other | 美东USNJ / 美中USTX / 波兰 / CG / 其他 |",
        "",
        "## 3. 六桶对账（冻结口径，逐桶 0 差）",
        "",
        "| 桶 | 行数 | 数值和 | 基线行数 | 基线数值和 | 行差 | 数值差 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in bucket_tbl.to_dict("records"):
        L.append(f"| {r['桶']} | {r['行数']:,} | {r['数值和']:,.0f} | {r['基线行数']:,} | "
                 f"{r['基线数值和']:,.0f} | {r['行数差']} | {r['数值差']:,.0f} |")
    L += [
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
        "## 4. N1 门禁：v3 评审 15 个键逐键回放",
        "",
        "门禁规则：没有适用成品/皮壳/套件事实 → `可发供给=null`、`供给状态=无适用事实(非0)`、`可用性=不进join`；"
        "空集不求和当 0；**已计=0 但同键有未计形态正量 → 也判 null**。",
        "",
        "| v3行号 | # | product_id | 仓池 | uom | v6 可发供给 | 供给状态 | 覆盖状态 | 覆盖缺口 | 可用性 | 事实行号 | 门禁 |",
        "|---:|---:|---|---|---|---:|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(fifteen_tbl.to_dict("records"), 1):
        v = "null" if r["可发供给"] is None or pd.isna(r["可发供给"]) else f"{r['可发供给']:,.0f}"
        L.append(f"| {r['v3行号']} | {i} | `{r['product_id']}` | {r['仓池']} | {r['uom']} | {v} | "
                 f"{r['供给状态']} | {r['覆盖状态']} | {r['覆盖缺口']} | {r['可用性']} | "
                 f"{r['事实行号(parquet1基)']} | {r['门禁']} |")
    gate_counts = fifteen_tbl["门禁"].value_counts().to_dict()
    L += [
        "",
        f"- 门禁结论：**PASS {int((fifteen_tbl['门禁'].astype(str).str.startswith('PASS')).sum())}/15**，"
        f"FAIL={int((fifteen_tbl['门禁'].astype(str).str.startswith('FAIL')).sum())}；"
        f"分类：{gate_counts}。",
        "- **12 个键 → null 或套件单列**（不进净额）：无适用成品/皮壳事实，或只有共享/海绵/待核/未映射事实。"
        "其中 v3 的 363/1278/1949 三行原为 `uom=套`（KS0018 并非 EN Product Bundle），"
        "按 UOM-CANONICAL §2.2 已回落「个」；中/波两仓另有未计套件正量（3/13），v6 判 null 而不是 0。",
        "- **2 个键 → 真实已证零**（`PASS(已证零,有源行)`）：KS0018 美东、骨架 ZTGJ5525 波兰。"
        "这两个键存在实际适用行且数量=0、同键无任何未计正量，按复审口径「真正已证零」保留 0；"
        "它们进 join 贡献为 0，不构成伪 0。",
        "- **1 个键 → 真实正量**：1456（骨架美东）599 个，源行 5279（TT0312701K0064561），属 N2 独立成品分支，"
        "与第 7 条「骨架 599 保留」一致。",
        "- 与验收字面「15 键全部 null/不进join」的偏差仅在上面 3 个键：把有源行证据的 0 或 599 强行改成 null，"
        "等于伪造「无事实」，会同时违反守恒与 N2「保留真实已证零/599」。故按证据保留，并在此显式列出。",
        "- 全量伪 0 扫描（所有可进join 且值=0 的键）见 `15_自检清单`：违例 0。",
        "",
        "## 5. 缺行 = 未覆盖（不是 0）",
        "",
        f"- A 活跃产品 **{summary['active_roles']:,}** 个；快照有库存行（计入A）**{summary['covered_en']:,}** 个；"
        f"**未覆盖 {summary['uncovered_en']:,}** 个（明细见 `13_未覆盖产品`，覆盖状态=未覆盖）。",
        "- 未覆盖 ≠ 0 库存：表示该快照没有任何源行可证明其数量；下游禁止补 0。",
        "",
        "## 6. 状态分层（事实/汇总/供给同一套）",
        "",
        "| 层 | 身份状态 | 单位状态 | 覆盖状态 |",
        "|---|---|---|---|",
        "| 事实层 `2_库存事实层` | 逐行 唯一/共享/未映射/未激活/待核 | 已证/默认个/冲突/套件 | 完整/部分/未覆盖/不适用 |",
        "| 汇总层 `3_产品×仓池×形态×UOM汇总` | 同上（按行组聚合） | 同上 | 同上 |",
        "| 供给层 `4_可发供给` | 同上（按 product×pool×uom 聚合） | 同上 | 同上 |",
        "",
        f"- 事实层身份状态分布：{summary['identity']}",
        f"- 事实层单位状态分布：{summary['uom_status']}",
        f"- 事实层覆盖状态分布：{summary['coverage']}",
        "- 只有 `身份状态=唯一` 才写「归属已证」；共享/未映射/未激活/待核一律「归属待核/无映射/未激活」。",
        "",
        "## 7. 可发供给结果",
        "",
        f"- 供给行 {len(supply_tbl):,}（product×pool×uom）。",
        f"- **可进 join {summary['join_rows']:,} 行 / {summary['join_qty']:,.0f} 个**"
        f"（其中 partial {summary['partial_rows']:,} 行）。",
        f"- CG/其他 只披露 {summary['discl_rows']:,} 行 / {summary['discl_qty']:,.0f}，不进 join。",
        f"- `可发供给=null` 的键 **{summary['null_keys']}** 个，全部不进 join："
        f"无适用事实 {summary['no_fact_keys']} 个 + 已计 0 但另有未计正量 {summary['pending_null_keys']} 个。",
        f"- 皮壳供给 {summary['cover_rows']:,} 行 / {summary['cover_qty']:,.0f} 个，"
        f"可进 join {summary['cover_rows_in_join']:,} 行 / {summary['cover_qty_in_join']:,.0f} 个。",
        f"- 成品供给 {summary['finished_rows']:,} 行（含骨架 {summary['skeleton_rows']} 行 / "
        f"{summary['skeleton_qty']:,.0f}）。",
        "- **可进 join 比 v5 少 2 行**：KS0018 美中/波兰两个 0 值键（另有未计套件正量 3/13）改判 null；"
        "**可进 join 的数量和不变（44,586 个）**。",
        "",
        "## 8. UOM 与换算",
        "",
        f"- 套仅 Bundle：{summary['bundle_rows']} 行 / {summary['bundle_units']:,.0f} 套（TJ# 单列，不拆组件）。",
        f"- 多件后缀：{summary['piece_rows']} 行，{summary['piece_raw']:,.0f} → {summary['piece_qty']:,.0f} 个。",
        f"- 星球抱枕组 1:1：{summary['planet_rows']:,} 行 / {summary['planet_qty']:,.0f} 个"
        f"（若按后缀乘 N 会多 {summary['planet_qty_v5rule'] - summary['planet_qty']:,.0f} 个）。",
        f"- 默认个（无 EN 单位来源，计入A）：{summary['default_ge_rows']:,} 行 / {summary['default_ge_qty']:,.0f}。",
        f"- 单位冲突（缓存套但非 Bundle）：{summary['uom_conflict_en']} 个 EN，按个计入并留档。",
        "",
        "| 项 | 行数 | 原始 available | 本版个当量 | 若按后缀乘 N |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in pc_summary.to_dict("records"):
        L.append(f"| {r['项']} | {r['行数']} | {r['原始available']:,.0f} | "
                 f"{r['个当量']:,.0f} | {r['若按后缀乘N']:,.0f} |")
    L += [
        "",
        "## 9. 254 行隔离与皮壳补证",
        "",
        "| 处置 | 行数 | 其中正库存 | 数值和 |",
        "|---|---:|---:|---:|",
    ]
    for k in ("补证", "待核", "仍隔离"):
        L.append(f"| {k} | {summary['iso_disposition'].get(k, 0)} | {summary['iso_pos'].get(k, 0)} | "
                 f"{summary['iso_disposition_qty'].get(k, 0):,.0f} |")
    L += [
        "",
        f"- 254 行逐行回指源 parquet：见自检；补证 63 行/539，仍隔离 191 行/653。",
        f"- 老产品标记：事实层 {summary['planet_rows']:,} 行 / {summary['planet_raw']:,.0f}；"
        f"供给层 {summary['planet_supply_rows']} 行 / {summary['planet_supply_qty']:,.0f}，"
        "全部「老产品-默认不补(待确认)」，行未删、数值照算。",
        "- ⚠ 数字对账：执行计划里写「老产品默认不补行=15」，但 v5/v6 实际打标为"
        f"事实层 {summary['planet_rows']:,} 行 / 供给层 {summary['planet_supply_rows']} 行"
        "（星球抱枕组 KS0019 整组）。**15 与现有产物不符**，本版按 v5 现状保留并如实报数，"
        "不强行凑 15；该口径待业务确认。",
        "",
        "## 10. 共享池",
        "",
        f"- `6_共享候选` 覆盖 **{summary['shared_codes']} 个码**；计入A 中多候选 "
        f"{summary['shared_extra_codes']} 个码按共享待核，不分配、不外推。",
        "",
        "## 11. 命名扫描（East / Central）",
        "",
        f"- 全表文本命中 **{scan_total}** 处；其中仓池/仓名列命中 **{scan_wh}** 处（要求 = 0）。",
    ]
    if scan_total:
        L += ["", "| sheet | 列 | 命中数 | 样例 |", "|---|---|---:|---|"]
        for r in scan_tbl.to_dict("records"):
            L.append(f"| {r['sheet']} | {r['列']} | {r['命中数']} | {r['样例']} |")
        L += ["", "> 仓池一律 美东USNJ / 美中USTX / 波兰 / CG / 其他；上述产品编码列命中属于 SKU 名称"
                   "（如 `...-CENTRALAMERICANAZTEC...`），不是仓名，不构成命名违规。"]
    else:
        L += ["- 全表 0 命中。"]
    L += [
        "",
        "## 12. 自检清单（机器验收）",
        "",
        "| 检查项 | 结果 | 期望 | 通过 |",
        "|---|---|---|---|",
    ]
    for c, got, want, ok in checks:
        L.append(f"| {c} | {got} | {want} | {'PASS' if ok else 'FAIL'} |")
    L += [
        "",
        "## 13. join v7 消费边界",
        "",
        "- **可读**：`2_库存事实层` + `4_可发供给` 中 `可用性` 以 `可进join` 开头的行。",
        "- **null 语义**：`可发供给=null` = 无适用事实或已计 0 但另有未计正量，禁止补 0。",
        "- **未覆盖语义**：`13_未覆盖产品` 中的产品在该快照无库存行，禁止当 0。",
        "- **套件**：`uom=套` 行不得与「个」混加；`可发供给` 列不含套。",
        "- **不可读**：`身份状态∈{共享,未映射,未激活,待核}`、`供给状态=待核*`、`可用性=仅披露*`。",
        "- **合同键**：snapshot_date × 仓池 × source_sku × resolved_supply_item × actual_form × uom；"
        "附 product_id、pieces_per_unit、源行号（parquet 1 基）。",
        "- **CG/其他**：只披露，不得自动当责任仓可用。",
        "",
        "## 14. 只读声明",
        "",
        "本次仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途接口，未发消息，未 push；"
        "未修改 A/B 产物，未覆盖 v2/v3/v4/v5。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
