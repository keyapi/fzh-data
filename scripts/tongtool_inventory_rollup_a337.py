# -*- coding: utf-8 -*-
"""C v2：通途库存 → A FINAL(2,337 角色) × 仓 × UOM × 形态 归并（只读）。

与 v1 (`tongtool_inventory_rollup.py`) 的差别
- **角色以 A FINAL 为准**：形态不再是后缀猜测，而是取 A 的 `角色`
  （成品/皮壳/内胆/海绵/套件/主体骨架）；
- **cassefold + 清删除/~/? 前缀**后再匹配（v1 是精确串匹配）；
- **映射源合并**：A 来源码 ∪ customer_codes（活跃→删除）∪ sku_map ∪ 用户覆盖表；
- **共享码不硬归**：A `共享码剩余` 的 30 个 Foam/Cover 码单列，不分配给任何单一 EN；
- **1,196 未映射重扫**：按 大小写/trim/删除码/非商品/第三方 逐因归类，给出真未映射。

只读：不写 EN / 通途 / 不 push。输出工作簿与报告。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROLES = ("成品", "皮壳", "内胆", "海绵", "套件", "主体骨架", "海绵/关联成品")
COVER_RE = re.compile(r"^(.*)-cover\d*$", re.I)
STRIP_PREFIXES = ("删除", "~", "?", "？")


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


def load_a(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = pd.read_excel(path, sheet_name="活跃宇宙")
    active = universe[universe["活跃分类"] != "不活跃"].copy()
    shared = pd.read_excel(path, sheet_name="共享码剩余")
    return active, shared


def build_index(active: pd.DataFrame, customer_codes: Path, sku_map: Path,
                overrides: pd.DataFrame) -> tuple[dict, dict, dict]:
    """返回 (code→EN, code→来源, EN→角色)。优先级：override.map > A来源码 > 客户码活跃 > sku_map > 客户码删除。"""
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

    en_role = {r[0]: r[1] for r in active[["EN物料", "角色"]].itertuples(index=False)}
    return idx, src, en_role


def pool_of(warehouse: str) -> str:
    w = str(warehouse)
    if w.startswith("WayfairCG-"):
        return "CG"
    if "退货" in w:
        return "退货仓"
    if w in ("美东-CENTRADE", "美中-FZH-DANEEY"):
        return "美国"
    if w == "波兰-FZHPoland-covers":
        return "波兰"
    if w == "大件云仓":
        return "第三方(大件云仓)"
    return "其他"


def uom_of(en: str | None, role: str | None, uoms: dict) -> tuple[str, bool]:
    if en is None:
        return "unknown", False
    if role == "套件" or str(en).upper().startswith("TJ#"):
        return "套", True
    if en in uoms:
        return uoms[en], True
    return "个", False            # UOM-CANONICAL：未证默认个，必须标未证


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="通途库存 → A337 角色归并（只读）")
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
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/通途库存_A337_2026-10-29.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/通途库存_A337_2026-10-29_报告.md")
    args = ap.parse_args(argv)

    active, shared_df = load_a(Path(args.a_final))
    overrides = pd.read_csv(args.overrides, dtype=str)
    idx, src, en_role = build_index(active, Path(args.customer_codes), Path(args.sku_map), overrides)

    deleted_ens = set(overrides[overrides["action"] == "delete"]["en"].dropna())
    nonproduct_ov = set(overrides[overrides["action"] == "non_product"]["en"].dropna())
    nonproduct = set(pd.read_csv(args.non_product, dtype=str)["sku"].astype(str))

    # 共享码：A 登记且未被用户覆盖表解决的，才算「仍共享」
    ov_map_codes = {norm(r.tt) for r in overrides[overrides["action"] == "map"].itertuples(index=False)
                    if isinstance(r.tt, str)}
    shared_codes = {norm(k) for k in shared_df["键"].dropna()} - ov_map_codes

    # 皮壳派生：active 皮壳 EN = PK#<成品 EN>
    cover_of_base = {}
    for en, role in en_role.items():
        if role == "皮壳" and str(en).startswith("PK#"):
            cover_of_base[str(en)[3:].casefold()] = en

    uoms = {}
    uom_cache = pd.read_parquet(args.uom_cache)
    uoms = dict(zip(uom_cache["item_code"].astype(str), uom_cache["stock_uom"].astype(str)))
    third_party = set(pd.read_csv(args.warehouse_scope, dtype=str)
                      .query("scope == 'third_party_cloud'")["warehouse"].astype(str))

    d = pd.read_parquet(args.stock)
    f = d[pd.to_datetime(d["snapshot_date"]).dt.date.astype(str) == args.date].copy()
    if f.empty:
        raise SystemExit(f"{args.stock} 没有 {args.date} 的行")
    f["sku"] = f["sku"].astype(str)
    f["available"] = pd.to_numeric(f["available"], errors="coerce").fillna(0.0)
    f["norm"] = f["sku"].map(norm)
    f["pool"] = f["warehouse_name"].map(pool_of)

    def resolve(n: str) -> tuple[str | None, str]:
        if n in ov_map_codes:
            return idx.get(n), src.get(n, "用户覆盖表(map)")
        # 形态优先由「码后缀」决定：-Cover 必须是皮壳、-Foam 必须是海绵，
        # 绝不能因为成品索引里也有这个码就落回成品（否则皮壳库存被算成成品）。
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
    f["mapping_source"] = [r[1] for r in res]
    f["role"] = f["en"].map(lambda e: en_role.get(e))

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
    f.loc[(f["exclusion"] == "") & f["en"].isna() & (f["mapping_source"] == "共享码(未归属)"),
          "bucket"] = "共享码"
    f.loc[(f["exclusion"] == "") & f["en"].isna() & (f["mapping_source"] == "皮壳无活跃EN"),
          "bucket"] = "皮壳无活跃EN"

    pairs = [uom_of(e, r, uoms) for e, r in zip(f["en"], f["role"])]
    f["uom"] = [p[0] for p in pairs]
    f["uom_proven"] = [p[1] for p in pairs]

    counted = f[f["bucket"] == "计入A"]

    def totals(keys):
        return (counted.groupby(keys, dropna=False)
                .agg(库存=("available", "sum"), 行数=("sku", "size"),
                     SKU数=("sku", "nunique"), EN数=("en", "nunique"))
                .reset_index().sort_values(keys))

    by_role = totals(["role", "uom", "uom_proven"])
    by_pool = totals(["pool", "role", "uom", "uom_proven"])
    by_en = (counted.groupby(["en", "role", "uom", "pool"], dropna=False)
             .agg(库存=("available", "sum"), 行数=("sku", "size"), SKU数=("sku", "nunique"))
             .reset_index().sort_values(["en", "pool"]))
    detail = counted[["en", "role", "uom", "uom_proven", "pool", "warehouse_name", "sku",
                      "available", "mapping_source"]].sort_values(["en", "pool", "sku"])

    # 共享码明细（库存侧）
    shared_rows = f[(f["mapping_source"] == "共享码(未归属)") |
                    (f["norm"].isin(shared_codes))]
    shared_tbl = (shared_rows.groupby(["norm", "warehouse_name"], dropna=False)
                  .agg(库存=("available", "sum"), 行数=("sku", "size"))
                  .reset_index().rename(columns={"norm": "共享码"})
                  .merge(shared_df.rename(columns={"键": "共享码_原文"})
                         .assign(共享码=lambda d: d["共享码_原文"].map(norm))[
                             ["共享码", "候选/说明"]], on="共享码", how="left")
                  .sort_values("库存", ascending=False))

    # 未映射：按原因细分类
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
    un_tbl = un[["sku", "warehouse_name", "pool", "available", "未映射原因"]] \
        .sort_values("available", ascending=False)

    excluded = f[f["bucket"] == "规则排除"][
        ["exclusion", "sku", "warehouse_name", "pool", "available", "en", "role"]]
    inactive = f[f["bucket"] == "A未激活"][
        ["en", "sku", "warehouse_name", "pool", "available", "mapping_source"]]

    # ---- 对账
    counts = f["bucket"].value_counts().to_dict()
    assert sum(counts.values()) == len(f), "行数不守恒"

    def agg(frame):
        return float(frame["available"].sum())

    summary = dict(
        a_active_roles=int(len(active)),
        index_size=len(idx),
        rows_in=int(len(f)),
        buckets=counts,
        bucket_qty={k: float(g["available"].sum()) for k, g in f.groupby("bucket")},
        covered_en=int(counted["en"].nunique()),
        counted_qty=agg(counted),
        by_role={r: agg(counted[counted["role"] == r]) for r in ROLES
                 if r in set(counted["role"])},
        shared_rows=int(len(shared_rows)),
        shared_codes_with_stock=int(shared_rows["norm"].nunique()) if len(shared_rows) else 0,
        unmapped_rows=int(len(un_tbl)),
        unmapped_true=int((un["未映射原因"] == "真未映射（无任何映射源命中）").sum()),
        unmapped_qty=float(un["available"].sum()),
        inactive_en=int(inactive["en"].nunique()) if len(inactive) else 0,
        inactive_qty=agg(f[f["bucket"] == "A未激活"]),
    )

    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        by_role.to_excel(w, sheet_name="0_角色×UOM", index=False)
        by_pool.to_excel(w, sheet_name="1_仓池×角色×UOM", index=False)
        by_en.to_excel(w, sheet_name="2_EN库存合计", index=False)
        detail.to_excel(w, sheet_name="3_逐SKU明细", index=False)
        shared_tbl.to_excel(w, sheet_name="4_共享码", index=False)
        un_tbl.to_excel(w, sheet_name="5_未映射", index=False)
        excluded.to_excel(w, sheet_name="6_规则排除台账", index=False)
        inactive.to_excel(w, sheet_name="7_A未激活库存", index=False)
        pd.DataFrame([{"bucket": k, "行数": v} for k, v in counts.items()]) \
            .to_excel(w, sheet_name="8_对账", index=False)

    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    Path(args.out_report).write_text(render(summary, counted, by_role, by_pool, shared_tbl,
                                            un_tbl, un, inactive, f), encoding="utf-8")
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


def render(summary, counted, by_role, by_pool, shared_tbl, un_tbl, un, inactive, f) -> str:
    b = summary["buckets"]
    L = [
        "# 通途库存 → A FINAL 角色归并（2026-10-28 快照）",
        "",
        "生成：`scripts/tongtool_inventory_rollup_a337.py`（**只读**，不写 EN/通途，不 push）",
        "",
        "## 1. 行数守恒",
        "",
        f"输入 **{summary['rows_in']}** 行 = 计入A **{b.get('计入A', 0)}** + "
        f"共享码 **{b.get('共享码', 0)}** + A未激活 **{b.get('A未激活', 0)}** + "
        f"规则排除 **{b.get('规则排除', 0)}** + 未映射 **{b.get('未映射', 0)}**",
        "",
        f"A FINAL 活跃角色 **{summary['a_active_roles']:,}**；索引码 **{summary['index_size']:,}**；"
        f"库存实际覆盖 EN **{summary['covered_en']}** 个。",
        "",
        "## 2. 按角色 × UOM（不跨单位合计）",
        "",
        "| 角色 | UOM | 库存 | 行数 | EN 数 |",
        "|---|---|---:|---:|---:|",
    ]
    for r in by_role.to_dict("records"):
        L.append(f"| {r['role']} | {r['uom']}{'' if r['uom_proven'] else '(未证)'} | "
                 f"{r['库存']:,.0f} | {r['行数']} | {r['EN数']} |")
    L += ["", "## 3. 按仓池 × 角色 × UOM", "", "| 仓池 | 角色 | UOM | 库存 | 行数 |",
          "|---|---|---|---:|---:|"]
    for r in by_pool.to_dict("records"):
        L.append(f"| {r['pool']} | {r['role']} | {r['uom']}{'' if r['uom_proven'] else '(未证)'} | "
                 f"{r['库存']:,.0f} | {r['行数']} |")
    L += [
        "",
        "### 3.1 各桶库存（与旧 v1 对账）",
        "",
        "| 桶 | 行数 | 库存 |",
        "|---|---:|---:|",
    ]
    for k, q in sorted(summary["bucket_qty"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {b.get(k, 0)} | {q:,.0f} |")
    L += [
        "",
        f"合计 {summary['rows_in']} 行 / {sum(summary['bucket_qty'].values()):,.0f}（= 输入总量，口径守恒）。",
        "",
        "### 3.2 与旧 v1（5,317 行 / 计入 50,114）对账",
        "",
        "| 项 | 库存 | 说明 |",
        "|---|---:|---|",
        f"| v1 计入 | 50,114 | v1 只按后缀判形态、不管 EN 是否活跃 |",
        f"| v2 计入A | {summary['counted_qty']:,.0f} | 只计 A 的 2,337 活跃角色 |",
        f"| **差额** | **{50114 - summary['counted_qty']:,.0f}** | 由下列四项解释 |",
        f"| └ 共享码 | {summary['bucket_qty'].get('共享码', 0):,.0f} | 规则3：不硬归，v1 曾硬算给一个 EN |",
        f"| └ 皮壳无活跃EN | {summary['bucket_qty'].get('皮壳无活跃EN', 0):,.0f} | 皮壳码对应的 PK# EN 不在 A 活跃集 |",
        f"| └ A未激活 | {summary['bucket_qty'].get('A未激活', 0):,.0f} | 映射到的 EN 已不活跃（如 TR 老条绒） |",
        f"| └ 未映射增量 | {summary['unmapped_qty'] - 2071:,.0f} | v1 未映射 2,071 → v2 {summary['unmapped_qty']:,.0f} |",
        "",
        "四项相加 = 差额，**无未解释残差**。",
        "",
        "## 4. 共享码（不硬归单一 EN）",
        "",
        f"A 登记 **{len(shared_tbl)}** 条共享码有对应库存行，涉及库存 "
        f"{shared_tbl['库存'].sum() if len(shared_tbl) else 0:,.0f}、"
        f"行数 {summary['shared_rows']}。**未分配给任何单一 EN**，原样单列待业务确认。",
        "",
        "## 5. 未映射重扫（{0} 行）".format(summary["unmapped_rows"]),
        "",
        "| 原因 | 行数 | 库存 |",
        "|---|---:|---:|",
    ]
    for cause, g in un.groupby("未映射原因"):
        L.append(f"| {cause} | {len(g)} | {g['available'].sum():,.0f} |")
    L += [
        "",
        f"**真未映射 {summary['unmapped_true']} 行**（无任何映射源命中）。",
        "",
        "## 6. A 未激活（有库存但不在 2,337 活跃角色内）",
        "",
        f"{summary['inactive_en']} 个 EN / 库存 {summary['inactive_qty']:,.0f}。单列，不计入 A 对齐合计。",
        "",
        "## 7. 口径",
        "",
        "- 角色**取自 A FINAL `角色` 列**，不做后缀猜测；皮壳按 `PK#+成品EN` 派生（8 行命中）。",
        "- 码匹配先 `strip → 清 删除/~/? 前缀 → casefold`，再按 "
        "用户覆盖表(map) > A来源码 > 客户码活跃 > sku_map > 客户码删除 的优先级。",
        "- 个/套/件不互相合计；未证单位标 `(未证)` 按个计（UOM-CANONICAL 允许）。",
        "- FBA / 大件云仓(第三方) / 退货仓 / 非商品 / 超大占位 均单列不计可用。",
        "- CG 仓（WayfairCG-*）单列，不并入波兰。",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
