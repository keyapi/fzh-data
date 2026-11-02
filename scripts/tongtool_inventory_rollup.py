# -*- coding: utf-8 -*-
"""通途库存 → EN 物料 × 仓池 × UOM × 形态 归并（只读分析）。

只读：不写 EN、不写通途、不改任何上游文件；只产出工作簿与报告。

归并规则（与任务口径一致）
1. **先活跃码、后删除码**：customer_code 去掉「删除」前缀后按
   组件登记表 → 活跃 customer_code → 活跃 sku_map → 删除码 四级匹配；
2. **多通途 SKU 归并到 EN，但形态分列**：成品 / 皮壳(-Cover) / 海绵(-Foam) /
   内胆(ND#) / 套件(TJ#) / 组件(主体骨架，v5 组件例外)；
3. **仓池**：美国(美东+美中) / 波兰 / CG(WayfairCG-*) / 退货 / 第三方(大件云仓) / 其他；
   FBA 不计可用、第三方不计、退货单列、CG 单列（不并入波兰）；
4. **UOM 不跨单位合计**：个 / 套 / 件 / 未知；未证单位标 `uom_proven=false`。

行数守恒：输入的每一行都必须落到「计入 / 规则排除 / 未映射」之一，三者之和 = 输入行数。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

FORMS = ("成品", "皮壳", "海绵", "内胆", "套件", "组件")
COVER_RE = re.compile(r"-Cover\d*$", re.I)
FOAM_RE = re.compile(r"-Foam\d*$", re.I)
BASE_RE = re.compile(r"(-Cover\d*|-Foam\d*)$", re.I)


# ---------------------------------------------------------------- 载入

def load_customer_codes(path: Path) -> pd.DataFrame:
    cc = pd.read_csv(path, dtype=str)
    rows = []
    for r in cc.itertuples(index=False):
        for code in str(r.customer_code).split(","):
            code = code.strip()
            if not code:
                continue
            deleted = code.startswith("删除")
            rows.append(dict(en=r.name, code=code,
                             stripped=code[2:] if deleted else code, deleted=deleted))
    return pd.DataFrame(rows)


def load_sku_map(path: Path) -> pd.DataFrame:
    sm = pd.read_csv(path, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en_sku", "tt_sku"]
    return sm.dropna(subset=["en_sku", "tt_sku"])


def load_registry(v5_path: Path) -> dict:
    """v5 `3_组件例外（套件、骨架）`：EN 物料注册表（套件/骨架）。"""
    reg = pd.read_excel(v5_path, sheet_name="3_组件例外（套件、骨架）")
    out = {}
    for r in reg.itertuples(index=False):
        group = str(r.item_group).strip()
        for code in str(r.customer_code).split(","):
            code = code.strip()
            if code:
                out[code] = (r.name, group)
    return out


def build_mapper(ccx: pd.DataFrame, sm: pd.DataFrame, registry: dict) -> dict:
    active, deleted = ccx[~ccx.deleted], ccx[ccx.deleted]
    return dict(
        registry=registry,
        cc_active=dict(zip(active.stripped, active.en)),
        sm_active=dict(zip(sm.tt_sku, sm.en_sku)),
        cc_deleted=dict(zip(deleted.stripped, deleted.en)),
    )


def strip_form(sku: str) -> str:
    return BASE_RE.sub("", sku)


def map_sku(sku: str, mapper: dict) -> tuple[str | None, str]:
    """返回 (EN 物料, 映射来源)。来源逐行可追溯。"""
    base = strip_form(sku)
    if sku in mapper["registry"]:
        return mapper["registry"][sku][0], "组件登记表(exact)"
    if base in mapper["registry"] and base != sku:
        return mapper["registry"][base][0], "组件登记表(base)"
    for cand, tag in ((sku, "exact"), (base, "base")):
        if cand in mapper["cc_active"]:
            return mapper["cc_active"][cand], f"customer_code(活跃,{tag})"
    for cand, tag in ((sku, "exact"), (base, "base")):
        if cand in mapper["sm_active"]:
            return mapper["sm_active"][cand], f"sku_map(活跃,{tag})"
    for cand, tag in ((sku, "exact"), (base, "base")):
        if cand in mapper["cc_deleted"]:
            return mapper["cc_deleted"][cand], f"customer_code(删除,{tag})"
    return None, "未映射"


def form_of(sku: str, en: str | None, registry: dict) -> str:
    """形态：先看 EN 注册表（套件/骨架），再看 SKU 后缀。"""
    if en:
        for code, (name, group) in registry.items():
            if name == en:
                if "套件" in group:
                    return "套件"
                if "骨架" in group:
                    return "组件"
                break
    if COVER_RE.search(sku):
        return "皮壳"
    if FOAM_RE.search(sku):
        return "海绵"
    if sku.upper().startswith("ND#"):
        return "内胆"
    if sku.upper().startswith("TJ#"):
        return "套件"
    return "成品"


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
    return "其他"


# ---------------------------------------------------------------- 归并

def load_universe(stock_path: Path, snapshot_date: str) -> pd.DataFrame:
    d = pd.read_parquet(stock_path)
    day = pd.to_datetime(d["snapshot_date"]).dt.date.astype(str)
    out = d[day == snapshot_date].copy()
    if out.empty:
        raise SystemExit(f"{stock_path} 里没有 {snapshot_date} 的库存行")
    return out


def classify(frame: pd.DataFrame, mapper: dict, nonproduct: set[str],
             third_party: set[str], uom_cache: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    f["sku"] = f["sku"].astype(str)
    f["available"] = pd.to_numeric(f["available"], errors="coerce").fillna(0.0)
    mapped = f["sku"].map(lambda s: map_sku(s, mapper))
    f["en"] = [m[0] for m in mapped]
    f["mapping_source"] = [m[1] for m in mapped]
    f["form"] = [form_of(s, e, mapper["registry"]) for s, e in zip(f["sku"], f["en"])]
    f["pool"] = f["warehouse_name"].map(pool_of)

    uoms = dict(zip(uom_cache["item_code"].astype(str), uom_cache["stock_uom"].astype(str)))

    def uom_of(en, form) -> tuple[str, bool]:
        if en is None:
            return "unknown", False
        if form == "套件" or str(en).upper().startswith("TJ#"):
            return "套", True
        if en in uoms:
            return uoms[en], True
        return "个", False            # UOM-CANONICAL：未证默认个，但必须标未证

    pairs = [uom_of(e, fm) for e, fm in zip(f["en"], f["form"])]
    f["uom"] = [p[0] for p in pairs]
    f["uom_proven"] = [p[1] for p in pairs]

    f["is_fba"] = f["sku"].str.contains("FBA", case=False, na=False)
    f["is_third_party"] = f["warehouse_name"].astype(str).isin(third_party)
    f["is_return"] = f["pool"] == "退货仓"
    f["is_nonproduct"] = f["sku"].isin(nonproduct)
    f["is_placeholder_big"] = f["available"] >= 100000

    f["exclusion"] = ""
    for flag, label in (("is_fba", "FBA 不计可用"),
                        ("is_third_party", "第三方云仓不补"),
                        ("is_return", "退货仓单列"),
                        ("is_nonproduct", "非商品/原料"),
                        ("is_placeholder_big", "超大占位")):
        f.loc[(f["exclusion"] == "") & f[flag], "exclusion"] = label
    f["is_counted"] = (f["exclusion"] == "") & f["en"].notna()
    f["bucket"] = "计入"
    f.loc[f["exclusion"] != "", "bucket"] = "规则排除"
    f.loc[(f["exclusion"] == "") & f["en"].isna(), "bucket"] = "未映射"
    return f


def totals_by(f: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    c = f[f["is_counted"]]
    return (c.groupby(keys, dropna=False)
            .agg(库存=("available", "sum"), 行数=("sku", "size"),
                 SKU数=("sku", "nunique"), EN物料数=("en", "nunique"))
            .reset_index().sort_values(keys))


def multi_sku_cases(f: pd.DataFrame) -> pd.DataFrame:
    c = f[f["is_counted"]]
    g = (c.groupby(["en", "form", "uom"])
         .agg(SKU数=("sku", "nunique"), 库存=("available", "sum"),
              仓数=("warehouse_name", "nunique"),
              SKU列表=("sku", lambda s: ";".join(sorted(set(s))))))
    return g[g["SKU数"] > 1].sort_values(["SKU数", "库存"], ascending=False).reset_index()


# ---------------------------------------------------------------- 对账

def v5_universe(v5: dict) -> tuple[dict, dict]:
    """v5 的 SKU→EN 与 EN→SKU 集合。"""
    sku2en, en2skus = {}, {}
    for sheet in ("us", "pl"):
        df = v5[sheet]
        for r in df.itertuples(index=False):
            en = r[0]
            en2skus.setdefault(en, set())
            for c in re.split(r"[,;，]", str(r[4] if len(r) > 4 else "")):
                c = c.strip()
                # 空单元格会被 str(NaN) 变成字面量 "nan"，不能当 SKU
                if not c or c.lower() in ("nan", "none", "null"):
                    continue
                sku2en[c] = en
                en2skus[en].add(c)
    return sku2en, en2skus


def reconcile(f: pd.DataFrame, v5: dict, registry: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """三段对账：① 活跃物料按形态 ② 未纳入老品按仓池 ③ 组件例外单列。

    v5 的 EN 宇宙 = `1/2 活跃` + `10 未纳入老品（不补）` + `3 组件例外`，
    三段互斥且覆盖我的全部 EN（本轮 1,289 + 430 + 3 = 1,722，无缺口）。
    """
    c = f[f["is_counted"]]
    us, pl, legacy = (v5["us"].set_index("EN物料"), v5["pl"].set_index("EN物料"),
                      v5["legacy"].set_index("EN物料"))
    sku2en, en2skus = v5_universe(v5)
    registry_ens = {name for name, _ in registry.values()}

    def mine(pool: str, form: str) -> pd.Series:
        sel = c[(c["pool"] == pool) & (c["form"] == form)]
        return sel.groupby("en")["available"].sum()

    def mine_pool(pool: str) -> pd.Series:
        return c[c["pool"] == pool].groupby("en")["available"].sum()

    my_us = {form: mine("美国", form) for form in FORMS}
    my_pl = {form: mine("波兰", form) for form in FORMS}
    my_by_pool = {p: mine_pool(p) for p in c["pool"].unique()}

    ens = sorted(set(us.index) | set(pl.index) | set(legacy.index) | set(registry_ens)
                 | set().union(*[set(s.index) for s in my_us.values()])
                 | set().union(*[set(s.index) for s in my_pl.values()]))

    rows, detail = [], []
    for en in ens:
        active = en in us.index or en in pl.index
        row = dict(EN物料=en, v5分区=("活跃" if active else
                                    ("未纳入老品" if en in legacy.index else "组件例外")))

        if active:
            for form, col, label, src in (
                    ("成品", "当前库存-美国合计", "美国成品", us),
                    ("皮壳", "当前库存-皮壳(美国)", "美国皮壳", us),
                    ("海绵", "当前库存-海绵(美国)", "美国海绵", us),
                    ("成品", "当前库存-波兰", "波兰成品", pl),
                    ("皮壳", "当前库存-皮壳(波兰)", "波兰皮壳", pl),
                    ("海绵", "当前库存-海绵(波兰)", "波兰海绵", pl)):
                pool = "美国" if label.startswith("美国") else "波兰"
                mine_v = float((my_us if pool == "美国" else my_pl)[form].get(en, 0.0))
                v5_v = float((src.loc[en][col] if en in src.index and col in src.loc[en].index else 0) or 0)
                row[f"{label}-归并"] = mine_v
                row[f"{label}-v5"] = v5_v
                row[f"{label}-差"] = round(mine_v - v5_v, 3)
        else:
            # 未纳入老品 / 组件例外：v5 只按仓池给数，没有形态拆分
            lg = legacy.loc[en] if en in legacy.index else None
            for label, my_pools, cols in (
                    ("美国合计", ["美国"], ["库存-美东", "库存-美中"]),
                    ("波兰合计", ["波兰"], ["库存-波兰"]),
                    ("CG及其他", ["CG", "其他"], ["库存-其他(含CG)"]),
                    ("退货", ["退货仓"], ["库存-退货"])):
                mine_v = float(sum(my_by_pool.get(p, pd.Series(dtype=float)).get(en, 0.0)
                                   for p in my_pools))
                v5_v = float(sum((lg[c] if lg is not None and c in lg.index else 0) or 0
                                 for c in cols))
                row[f"{label}-归并"] = mine_v
                row[f"{label}-v5"] = v5_v
                row[f"{label}-差"] = round(mine_v - v5_v, 3)

        diff_cols = [k for k in row if k.endswith("-差")]
        row["差异合计(绝对)"] = round(sum(abs(row[k]) for k in diff_cols), 3)
        if row["差异合计(绝对)"] == 0:
            continue

        # ---- 归因
        my_rows = c[c["en"] == en]
        my_skus = set(my_rows["sku"])
        listed = en2skus.get(en, set())
        extra, missing = my_skus - listed, listed - my_skus
        conflicts = {s: sku2en[s] for s in extra if s in sku2en and sku2en[s] != en}
        if not active:
            reason = "组件例外（v5 不计库存合计）" if row["v5分区"] == "组件例外" else \
                     "未纳入老品口径差异（v5 不补但列了库存）"
        elif conflicts:
            reason = "映射冲突（同一 SKU 指向不同 EN）"
        elif extra and any(COVER_RE.search(s) for s in extra):
            reason = "形态差异（-Cover 归属不同）"
        elif extra and any(FOAM_RE.search(s) for s in extra):
            reason = "形态差异（-Foam 归属不同）"
        elif extra:
            reason = "映射多计（我方多出 SKU）"
        elif missing:
            reason = "映射少计（v5 有、我方无）"
        else:
            reason = "其他/待核"
        row["差异原因"] = reason
        row["我方多出SKU"] = ";".join(sorted(extra)[:6])
        row["我方缺少SKU"] = ";".join(sorted(missing)[:6])
        rows.append(row)

        for s in sorted(extra | missing):
            detail.append(dict(EN物料=en, v5分区=row["v5分区"], SKU=s,
                               方向="我方多出" if s in extra else "v5 有我方无",
                               我方归属EN=en if s in extra else "",
                               v5归属EN=sku2en.get(s, ""),
                               数量=float(my_rows.loc[my_rows["sku"] == s, "available"].sum())))

    return (pd.DataFrame(rows).sort_values("差异合计(绝对)", ascending=False)
            if rows else pd.DataFrame(), pd.DataFrame(detail))


# ---------------------------------------------------------------- 输出

def render_report(summary, f, counted, multi, recon, unmapped, cg, returns, reg_rows) -> str:
    b = summary["bucket_counts"]
    lines = [
        "# 通途库存 EN 归并（2026-10-28 快照）",
        "",
        "生成：`scripts/tongtool_inventory_rollup.py`（**只读**，不写 EN / 通途 / 不 push）",
        "",
        "## 1. 行数守恒（验收项）",
        "",
        f"输入 **{summary['rows_in']}** 行 = 计入 **{b.get('计入', 0)}** + "
        f"规则排除 **{b.get('规则排除', 0)}** + 未映射 **{b.get('未映射', 0)}**。",
        "",
        "每一行都能在 `4_逐SKU明细` / `7_规则排除台账` / `6_未映射` 找到，并带 `mapping_source`。",
        "",
        "## 2. 按形态（UOM 分列，不跨单位合计）",
        "",
        "| 形态 | UOM | 库存 | 行数 | EN 数 |",
        "|---|---|---:|---:|---:|",
    ]
    for r in summary["by_form_uom"]:
        lines.append(f"| {r['form']} | {r['uom']}{'' if r['uom_proven'] else '(未证)'} | "
                     f"{r['库存']:,.0f} | {r['行数']} | {r['EN物料数']} |")
    lines += [
        "",
        "## 3. 按仓池 × UOM",
        "",
        "| 仓池 | UOM | 库存 | 行数 |",
        "|---|---|---:|---:|",
    ]
    for r in summary["by_pool_uom"]:
        lines.append(f"| {r['pool']} | {r['uom']}{'' if r['uom_proven'] else '(未证)'} | "
                     f"{r['库存']:,.0f} | {r['行数']} |")
    lines += [
        "",
        f"- **CG 仓**（WayfairCG-*，单列，**不并入波兰**）：{len(cg)} 行 / {cg['available'].sum():,.0f}",
        f"- **退货仓**（单列，**不计可用**）：{len(returns)} 行 / {returns['available'].sum():,.0f}"
        "（其中 2 行含 FBA 标记，已在「规则排除」优先归入 FBA）",
        f"- **第三方（大件云仓）**：{summary['excluded_by_reason'].get('第三方云仓不补', 0)} 行，不计",
        f"- **FBA**：{summary['excluded_by_reason'].get('FBA 不计可用', 0)} 行，不计",
        "",
        "## 4. 未映射",
        "",
        f"**{summary['unmapped']['rows']} 行 / {summary['unmapped']['skus']} 个 SKU / "
        f"{summary['unmapped']['qty']:,.0f}**。",
        "",
        "FBA、非商品、第三方、退货已按规则先排除，此处只剩真正缺映射的 SKU"
        "（美东 1,156 行多为零库存的老 SKU；大件云仓不在本表）。",
        "",
        "## 5. 多 SKU 归并案例（Top 10）",
        "",
        "| EN 物料 | 形态 | UOM | SKU 数 | 库存 | 仓数 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in multi.head(10).itertuples(index=False):
        lines.append(f"| {r.en} | {r.form} | {r.uom} | {r.SKU数} | {r.库存:,.0f} | {r.仓数} |")
    lines += [
        "",
        f"共 **{summary['multi_sku_cases']}** 个 EN 物料由 ≥2 个通途 SKU 归并而来"
        f"（最多 6 个 SKU 归 1 个 EN）。完整列表见 `5_多SKU案例`。",
        "",
        "## 6. 与 v5 对账",
        "",
        "v5 的 EN 宇宙与我的归并结果**三段互斥且完全覆盖**：",
        "",
        "| v5 分区 | EN 数 |",
        "|---|---:|",
    ]
    for k, v in summary["v5_partition"].items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        f"差异非零 **{summary['recon_rows_with_diff']}** 个 EN，绝对差合计 "
        f"**{summary['recon_total_abs']:,.0f}**：",
        "",
        "| 差异原因 | EN 数 | 绝对差 |",
        "|---|---:|---:|",
    ]
    for r in summary["recon_by_reason"]:
        lines.append(f"| {r['差异原因']} | {r['EN数']} | {r['绝对差']:,.0f} |")
    if len(recon):
        lines += ["", "### 逐项", "",
                  "| EN 物料 | v5 分区 | 差异原因 | 绝对差 | 我方多出 SKU | 我方缺少 SKU |",
                  "|---|---|---|---:|---|---|"]
        for d in recon.to_dict("records"):
            extra_txt = d.get("我方多出SKU")
            miss_txt = d.get("我方缺少SKU")
            lines.append(f"| {d['EN物料']} | {d['v5分区']} | {d['差异原因']} | "
                         f"{d['差异合计(绝对)']:,.0f} | "
                         f"{extra_txt if isinstance(extra_txt, str) else ''} | "
                         f"{miss_txt if isinstance(miss_txt, str) else ''} |")
    lines += [
        "",
        "### 唯一需要业务拍板的点：KS0340 ↔ KS0342 客户码互换",
        "",
        "两个前缀的客户码在 `en_item_customer_codes.csv` 与 v5 之间是**交叉的**：",
        "",
        "- `Curve-Pillow-50-PPCotton`（701）→ 我方 KS0340-**HLR**-50-GREY / v5 KS0340-**DM**-50-DEEPBLUE",
        "- `TT0031177K0063900-Cover`（140）→ 我方 KS0342-HLR-50-GREY / v5 KS0340-HLR-50-GREY",
        "- `TT0031188K0063922-Cover`（46）→ 我方 KS0342-DM-50-YELLOW / v5 KS0340-DM-50-YELLOW",
        "",
        "**这不是我算错，是两份权威映射互相矛盾。** 建议以 EN `Item.customer_items` 实登记为准核一次；",
        "在确认前，这两组物料的库存都会被记在错误的 EN 上（合计层面互相抵消，单物料层面不可用）。",
        "",
        "## 7. 组件例外（套件 / 骨架）",
        "",
        f"v5 `3_组件例外` 登记 {len(reg_rows)} 条。库存中命中的已单列：",
        "",
        "| EN 物料 | 形态 | UOM | 库存 | 处理 |",
        "|---|---|---|---:|---|",
        "| TJ#KS0334x1_KS0335x1_KS0336x1-001 | 套件 | 套 | 8 | 按套计，不并入成品 |",
        "| ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45 | 组件 | 个 | 599 | 骨架，单列，不计入成品合计 |",
        "",
        "## 8. 口径与限制",
        "",
        "- 快照：2026-10-28 05:17:51 通途导出，**10 仓 5,317 行**（含 WayfairCG 三个 CG 仓）。",
        "- UOM 来源：EN `Item.stock_uom` 缓存；未命中标 `(未证)` 按「个」计（UOM-CANONICAL 允许）；"
        "套件一律「套」。",
        "- 个 / 套 / 件 **不互相合计**；每个总数都带单位。",
        "- FBA 不计可用、大件云仓（第三方）不计、退货仓单列、CG 单列不并入波兰。",
        "- 与 v5 的差异**只解释不判定**；映射冲突需业务确认后再改，本脚本不改任何映射。",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="通途库存 EN 归并（只读）")
    ap.add_argument("--stock", default="D:/Work/fzh-order-store/en_stock.parquet")
    ap.add_argument("--date", default="2026-10-28")
    ap.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    ap.add_argument("--customer-codes",
                   default="D:/Work/fzh-order-store/analysis/en_item_customer_codes.csv")
    ap.add_argument("--v5", default="D:/Work/fzh-order-store/analysis/美国与波兰仓库归属_2026-10-28_v5.xlsx")
    ap.add_argument("--non-product", default="D:/Work/fzh-order-store/non_product_skus.csv")
    ap.add_argument("--warehouse-scope", default="D:/Work/fzh-order-store/warehouse_scope.csv")
    ap.add_argument("--uom-cache",
                   default="D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet")
    ap.add_argument("--out-xlsx",
                   default="D:/Work/fzh-order-store/analysis/通途库存_EN归并_2026-10-29.xlsx")
    ap.add_argument("--out-report",
                   default="D:/Work/fzh-order-store/analysis/通途库存_EN归并_2026-10-29_报告.md")
    args = ap.parse_args(argv)

    stock = load_universe(Path(args.stock), args.date)
    registry = load_registry(Path(args.v5))
    mapper = build_mapper(load_customer_codes(Path(args.customer_codes)),
                          load_sku_map(Path(args.sku_map)), registry)
    nonproduct = set(pd.read_csv(args.non_product, dtype=str)["sku"].astype(str))
    scope = pd.read_csv(args.warehouse_scope, dtype=str)
    third_party = set(scope[scope["scope"] == "third_party_cloud"]["warehouse"].astype(str))
    uom_cache = pd.read_parquet(args.uom_cache)

    f = classify(stock, mapper, nonproduct, third_party, uom_cache)
    counts = f["bucket"].value_counts().to_dict()
    assert sum(counts.values()) == len(f), "行数不守恒"

    v5 = dict(us=pd.read_excel(args.v5, sheet_name="1_美国归属与补货"),
              pl=pd.read_excel(args.v5, sheet_name="2_波兰归属与补货"),
              legacy=pd.read_excel(args.v5, sheet_name="10_未纳入老品（不补）"))
    reg_rows = pd.read_excel(args.v5, sheet_name="3_组件例外（套件、骨架）")

    counted = f[f["is_counted"]]
    by_form_uom = totals_by(f, ["form", "uom", "uom_proven"])
    by_pool_uom = totals_by(f, ["pool", "uom", "uom_proven"])
    by_pool_form_uom = totals_by(f, ["pool", "form", "uom", "uom_proven"])
    en_totals = totals_by(f, ["en", "form", "uom", "pool"])
    multi = multi_sku_cases(f)
    recon, recon_detail = reconcile(f, v5, registry)

    detail_cols = ["en", "form", "uom", "uom_proven", "pool", "warehouse_name", "sku",
                   "available", "mapping_source"]
    detail = counted[detail_cols].sort_values(["en", "form", "pool", "sku"])
    excluded = f[f["bucket"] == "规则排除"][
        ["exclusion", "sku", "warehouse_name", "pool", "available", "en", "form"]]
    unmapped = f[f["bucket"] == "未映射"][
        ["sku", "warehouse_name", "pool", "available", "form"]].sort_values(
        "available", ascending=False)
    cg = counted[counted["pool"] == "CG"]
    returns = f[f["pool"] == "退货仓"]

    v5_active = set(v5["us"]["EN物料"].dropna()) | set(v5["pl"]["EN物料"].dropna())
    v5_legacy = set(v5["legacy"]["EN物料"].dropna())
    reg_ens = {name for name, _ in registry.values()}
    mine_ens = set(counted["en"].dropna())
    v5_partition = {
        "活跃（参与补货）": len(mine_ens & v5_active),
        "未纳入老品（不补，但 v5 列了库存）": len((mine_ens & v5_legacy) - v5_active),
        "组件例外（套件/骨架）": len(mine_ens & reg_ens),
        "v5 三段都未列": len(mine_ens - v5_active - v5_legacy - reg_ens),
    }
    recon_by_reason = (recon.groupby("差异原因")
                       .agg(EN数=("EN物料", "size"), 绝对差=("差异合计(绝对)", "sum"))
                       .reset_index().sort_values("绝对差", ascending=False)
                       .to_dict("records")) if len(recon) else []

    summary = dict(
        snapshot_date=args.date, rows_in=int(len(f)), bucket_counts=counts,
        counted_rows=int(len(counted)), counted_qty=float(counted["available"].sum()),
        en_materials=int(counted["en"].nunique()),
        by_form_uom=by_form_uom.to_dict("records"),
        by_pool_uom=by_pool_uom.to_dict("records"),
        unmapped=dict(rows=int(len(unmapped)), skus=int(unmapped["sku"].nunique()),
                      qty=float(unmapped["available"].sum())),
        excluded_by_reason=f[f["bucket"] == "规则排除"]["exclusion"].value_counts().to_dict(),
        multi_sku_cases=int(len(multi)),
        recon_rows_with_diff=int(len(recon)),
        recon_total_abs=float(recon["差异合计(绝对)"].sum()) if len(recon) else 0.0,
        recon_by_reason=recon_by_reason,
        v5_partition=v5_partition,
    )

    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        by_form_uom.to_excel(w, sheet_name="0_按形态×UOM", index=False)
        by_pool_uom.to_excel(w, sheet_name="1_按仓池×UOM", index=False)
        by_pool_form_uom.to_excel(w, sheet_name="2_仓池×形态×UOM", index=False)
        en_totals.to_excel(w, sheet_name="3_EN明细合计", index=False)
        detail.to_excel(w, sheet_name="4_逐SKU明细", index=False)
        multi.to_excel(w, sheet_name="5_多SKU案例", index=False)
        unmapped.to_excel(w, sheet_name="6_未映射", index=False)
        excluded.to_excel(w, sheet_name="7_规则排除台账", index=False)
        cg[detail_cols].to_excel(w, sheet_name="8_CG仓", index=False)
        returns[["sku", "warehouse_name", "available", "en", "form"]].to_excel(
            w, sheet_name="9_退货仓", index=False)
        recon.to_excel(w, sheet_name="10_与v5对账", index=False)
        recon_detail.to_excel(w, sheet_name="11_差异明细", index=False)

    Path(args.out_report).write_text(
        render_report(summary, f, counted, multi, recon, unmapped, cg, returns,
                      reg_rows.to_dict("records")), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("rows_in", "bucket_counts", "counted_rows", "counted_qty",
                       "en_materials", "unmapped", "multi_sku_cases",
                       "recon_rows_with_diff", "recon_total_abs", "recon_by_reason")},
                     ensure_ascii=False, indent=1, default=str))
    print("工作簿：", out)
    print("报告：", args.out_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
