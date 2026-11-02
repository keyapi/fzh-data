# -*- coding: utf-8 -*-
"""D1b v2：按 B r10 重算市场（含 60cm 同物映射）+ 形态回填 + 双市场拆行（只读）。

最终规则（Codex 2026-11-02 评审 + 项目主补充）：
1) 身份：保留原 product_id 与前缀；PK#/ND#/HM#/TJ# 仅去前缀 join；不删原行。
2) 皮壳/骨架：取同市场同形态的 B Y 行；只有 N 行时只继承关联 Y 行的市场/owner，
   netting=observation，不复制需求、不复制销量。
3) 政策优先级：ND/HM/老产品/共享政策/TJ# 终端规则 > 其余；政策行绝不进 data_gap。
4) stock_placement 只作 observation，不单独证明需求。
5) destination_pool=其他：唯一归属才归并；否则隔离。
6) 248 个双市场皮壳拆行；键=product_id×market×pool×form×uom；拆行不加需求。
7) 91 行 physical_form=无适用：90 行 B 有共享限制 → policy_excluded(shared_policy)；
   1 行成品/个 → supply_gap；不再用 form_uom_unproven 兜底。
8) 保留 60cm 映射、无适用回填、D2 demand_state_raw/censored/observed。

--dry-run 只打印对账与 checks，不写文件。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

RULE_VERSION = "D1b-v2.3-2026-11-02"
PREFIX_RE = re.compile(r"(?i)^(PK#|ND#|HM#|TJ#)")
HIST_START, HIST_END = "2025-01-01", "2026-10-31"
KEY = ["product_id", "market", "destination_pool", "physical_form", "canonical_uom"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(code) -> str:
    c = str(code).strip()
    for p in ("删除", "~", "?", "？"):
        while c.startswith(p):
            c = c[len(p):].strip()
    return c.casefold()


def base_key(pid: str) -> tuple[str, str]:
    s = str(pid).strip()
    m = PREFIX_RE.match(s)
    if m:
        return s[m.end():].strip(), f"strip_prefix:{m.group(1)}"
    return s, "exact"


def pool_of(w: str) -> str:
    s = str(w)
    if "WayfairCG" in s or s.startswith("CG"):
        return "CG"
    if "退货" in s:
        return "其他"
    if "Poland" in s or "波兰" in s:
        return "波兰"
    if "CENTRADE" in s or "美东" in s:
        return "美东USNJ"
    if "DANEEY" in s or "美中" in s:
        return "美中USTX"
    return "其他"


def main(argv=None) -> int:
    B = "D:/Work/fzh-order-store"
    ap = argparse.ArgumentParser(description="D1b v2（只读）")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--b-attrib", default=f"{B}/analysis/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--c-stock", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--d1", default=f"{B}/analysis/D_资格与契约_v2_2026-10-30.xlsx")
    ap.add_argument("--d2", default=f"{B}/analysis/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--forecast", default=f"{B}/analysis/需求预测_去库存影响_2026-10-29.xlsx")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--overrides", default=f"{B}/analysis/sku_mapping_overrides_2026-10-29.csv")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/D_资格与契约_D1b_v2_3_2026-11-02_报告.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    d1 = pd.read_excel(args.d1, sheet_name="1_资格").reset_index(drop=True)
    d1["product_id"] = d1["product_id"].astype(str)
    d1["_src"] = d1.index + 2
    d2 = pd.read_excel(args.d2, sheet_name="1_序列")
    d2["month"] = d2["month"].astype(str).str.replace(r"\.0$", "", regex=True)

    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    active = a[a["活跃分类"] != "不活跃"].copy()
    active["EN物料"] = active["EN物料"].astype(str)
    active_ids = set(active["EN物料"])

    b = pd.read_excel(args.b_attrib, sheet_name="主表")
    b["产品键"] = b["产品键"].astype(str)
    b_by_key: dict[str, list] = {}
    for r in b.to_dict("records"):
        b_by_key.setdefault(r["产品键"], []).append(r)
    try:
        cmap_df = pd.read_excel(args.b_attrib, sheet_name="60cm成员映射")
    except Exception:
        cmap_df = pd.DataFrame(columns=["产品键", "成员"])
    cmap: dict[str, str] = {}
    for r in cmap_df.to_dict("records"):
        for m in str(r["成员"]).split(";"):
            m = PREFIX_RE.sub("", m.strip())
            if m:
                cmap.setdefault(m, str(r["产品键"]))

    def resolve_b(pid: str) -> tuple[str, str]:
        base, _ = base_key(pid)
        if base in b_by_key:
            return base, "base_exact"
        if base in cmap and cmap[base] in b_by_key:
            return cmap[base], "60cm_member"
        return base, "none"

    fcast = pd.read_excel(args.forecast, sheet_name="1_需求预测")
    fcast["EN物料"] = fcast["EN物料"].astype(str)
    fc_meta = {r["EN物料"]: r for r in fcast.to_dict("records")}

    c4 = pd.read_excel(args.c_stock, sheet_name="4_可发供给")
    c4["product_id"] = c4["product_id"].astype(str)
    c_key = {(r["product_id"], r["pool"], r["uom"]): r for r in c4.to_dict("records")}

    ov = pd.read_csv(args.overrides, dtype=str)
    idx: dict[str, str] = {}
    for r in ov[ov["action"] == "map"].itertuples(index=False):
        if isinstance(r.tt, str):
            idx[norm(r.tt)] = r.en
    for r in active.itertuples(index=False):
        raw = getattr(r, "来源码")
        if isinstance(raw, str):
            for tok in re.split(r"[,;，]", raw):
                idx.setdefault(norm(tok), r[0])
    cc = pd.read_csv(args.customer_codes, dtype=str)
    for r in cc.itertuples(index=False):
        for c in str(r.customer_code).split(","):
            c = c.strip()
            if c.startswith("删除"):
                c = c[2:]
            if c:
                idx.setdefault(norm(c), r.name)
    sm = pd.read_csv(args.sku_map, sep="\t", dtype=str).iloc[:, :2]
    sm.columns = ["en", "tt"]
    for r in sm.dropna().itertuples(index=False):
        idx.setdefault(norm(r.tt), r.en)

    o = pd.read_parquet(args.orders)
    o["sale_date"] = pd.to_datetime(o["sale_date"])
    o = o[(o["sale_date"] >= HIST_START) & (o["sale_date"] <= HIST_END)].copy()
    o["month"] = o["sale_date"].dt.strftime("%Y%m")
    o["en"] = o["sku_tongtool"].map(lambda s: idx.get(norm(s)))
    o["pool"] = o["warehouse"].map(pool_of)
    pos = o[(o["en"].notna()) & (o["qty"] > 0)]
    sales_pp: dict[tuple, set] = {}
    sales_p: dict[str, set] = {}
    for en, pool, m in zip(pos["en"], pos["pool"], pos["month"]):
        sales_pp.setdefault((en, pool), set()).add(m)
        sales_p.setdefault(en, set()).add(m)

    pool_has_sales = {p for (_e, p) in sales_pp}
    d2_key = (d2.groupby(["product_id", "pool", "physical_form", "canonical_uom", "zero_class"])
              .size().unstack(fill_value=0).reset_index())
    if "stockout_censored" not in d2_key.columns:
        d2_key["stockout_censored"] = 0
    cens_map = {(r["product_id"], r["pool"], r["physical_form"], r["canonical_uom"]):
                int(r.get("stockout_censored", 0)) for r in d2_key.to_dict("records")}

    def b_rows(pid: str) -> tuple[list, str]:
        rkey, method = resolve_b(pid)
        return b_by_key.get(rkey, []), method

    def pick_form(row0, rows) -> tuple[str, str]:
        form = str(row0["physical_form"])
        if form not in ("无适用", "", "未知"):
            return form, "original"
        role = str(row0["角色"])
        forms = [str(r.get("供货形态") or "") for r in rows]
        for cand in (role, "成品", "皮壳", "套件", "主体骨架", "独立海绵"):
            if cand in forms:
                return cand, "b_r10"
        return form, "none"

    def market_options(row0, rows, form, form_basis) -> list[dict]:
        y = [r for r in rows if r.get("是否需求行") == "Y"]
        n = [r for r in rows if r.get("是否需求行") == "N"]
        kind = "demand"
        if form in ("皮壳", "主体骨架"):
            same = [r for r in y if str(r.get("供货形态")) == form]
            if same:
                src = same
            elif y:
                src, kind = y, "inherit"
            else:
                src, kind = n, "observation"
        else:
            same = [r for r in y if str(r.get("供货形态")) in (form, "成品", "套件")]
            if same:
                src = same
            elif y:
                src = y
            else:
                src, kind = n, "observation"
        if src and all(str(r.get("最强证据层级")) == "stock_placement" for r in src):
            kind = "observation"
        out, seen = [], set()
        for r in src:
            region = r.get("地区")
            owner = str(r.get("美国责任方") or "").strip()
            if region == "PL":
                market, pool = "PL", "波兰"
            elif region == "US":
                market = "US"
                pool = owner if owner in ("美东USNJ", "美中USTX") else ""
            else:
                continue
            if not pool:
                continue
            if str(row0["destination_pool"]).startswith("CG"):
                pool = str(row0["destination_pool"])
            k = (market, pool)
            if k in seen:
                continue
            seen.add(k)
            ref = str(r.get("demand_scope_id") or "")
            basis = (f"b_r10|{form_basis}|{str(r.get('最强证据层级') or '')}|"
                     f"{kind}|row={ref}")
            out.append({"market": market, "pool": pool, "owner": owner, "kind": kind,
                        "basis": basis, "ref": ref,
                        "detail": str(r.get("市场状态") or ""),
                        "conf": str(r.get("market_confidence") or "")})
        return out

    rows_out = []
    add_calls = {"original": 0, "split": 0}

    def add(row0, form, uom, market, pool, opt, origin, demand, form_basis, note="", rmethod="none"):
        add_calls[origin] = add_calls.get(origin, 0) + 1
        pid = str(row0["product_id"]); role = str(row0["角色"])
        base, _pm = base_key(pid)
        method = rmethod
        ck = c_key.get((pid, pool, uom))
        if ck is not None:
            sup = {"qty": (None if pd.isna(ck["可发供给"]) else float(ck["可发供给"])),
                   "join": ck["join_class"], "cov": ck["覆盖状态"],
                   "ident": ck["身份状态"], "src": "C物理库存"}
        elif origin == "original" and pool == str(row0["destination_pool"]):
            sup = {"qty": row0.get("supply_qty"), "join": row0.get("join_class"),
                   "cov": row0.get("coverage_status"), "ident": row0.get("identity_status"),
                   "src": row0.get("supply_source")}
        else:
            sup = {"qty": None, "join": "no_join", "cov": "未覆盖", "ident": "唯一",
                   "src": "无供给行"}
        is_nd = bool(row0.get("is_nd")) or pid.upper().startswith("ND#") or role == "内胆"
        is_hm = bool(row0.get("is_hm")) or role in ("海绵", "海绵/关联成品")
        is_kit = bool(row0.get("is_kit"))
        is_legacy = bool(row0.get("is_legacy"))
        is_cg = bool(row0.get("is_cg")) or str(pool).startswith("CG")
        kind = (opt or {}).get("kind", "none")
        proven = kind != "none" and bool((opt or {}).get("basis"))
        shared_policy = bool(row0.get("_shared_policy"))

        if is_nd:
            decision, reason = "policy_excluded", "nd_component"
        elif is_hm:
            decision, reason = "policy_excluded", "hm_component"
        elif is_legacy:
            decision, reason = "policy_excluded", "legacy_no_replenish"
        elif is_kit:
            decision, reason = "policy_excluded", "kit_terminal_rule"
        elif shared_policy:
            decision, reason = "policy_excluded", "shared_policy"
        elif not proven:
            decision, reason = "data_gap", "market_unproven"
        elif form in ("无适用", "", "未知") or uom not in ("个", "套"):
            decision, reason = "data_gap", "form_uom_unproven"
        elif pool == "其他":
            decision, reason = "active", "other_pool_observation"
        else:
            decision, reason = "active", "ok"

        # 拆行/新建行只继承证据字段，不新增需求（避免重复计数）
        dstate = demand["demand_state_raw"] if origin == "original" else "no_demand"
        fm = fc_meta.get(pid)
        own = int(demand["observed_months"])
        p_obs = len(sales_p.get(pid, set()))
        fm_ok = fm is not None and str(fm.get("forecast_status")) == "ok"
        # v2.2：observed_model 只允许本行自身序列 ≥3 个正销月且模型可评估
        if dstate == "no_demand":
            if fm is not None or p_obs > 0:
                forecast, f_basis = "fallback_model", "product_pool"
            elif pool in pool_has_sales:
                forecast, f_basis = "fallback_model", "pool_mean"
            else:
                forecast, f_basis = "not_estimable", "not_estimable"
        elif own >= 3 and fm_ok:
            forecast, f_basis = "observed_model", "own_series"
        elif own < 3:
            forecast, f_basis = "cold_start", "own_series"
        else:
            forecast, f_basis = "fallback_model", "own_series"

        if decision == "policy_excluded":
            netting = "policy_excluded"
        elif decision == "data_gap":
            netting = "data_gap"
        elif is_cg:
            netting = "observation"
        elif kind in ("observation", "inherit") or pool == "其他" or forecast == "not_estimable":
            netting = "observation"
        elif str(sup["join"]) == "join_full" and str(sup["ident"]) == "唯一":
            netting = "eligible"
        else:
            netting = "supply_gap"

        if decision == "policy_excluded":
            group = "policy"
        elif decision == "data_gap":
            group = "data"
        elif netting == "supply_gap":
            group, reason = "supply", "supply_not_full"
        elif netting == "observation":
            group = "supply" if (is_cg or kind in ("observation", "inherit")
                                 or pool == "其他") else "forecast"
        elif forecast != "observed_model":
            group = "forecast"
        else:
            group = "ok"

        _mb = (opt or {}).get("basis", "") or ""
        if decision == "policy_excluded" and not _mb:
            _mb = f"policy_exempt|{reason}"   # 政策行不需要市场证据
        rows_out.append({
            "product_id": pid, "map_base_key": base, "map_method": method,
            "map_evidence": _mb,
            "角色": role, "ship_mode": row0.get("ship_mode"),
            "market": market, "destination_pool": pool,
            "market_basis": _mb,
            "market_basis_detail": (opt or {}).get("detail", "") or "",
            "market_confidence": (opt or {}).get("conf", "") or "",
            "market_evidence_ref": (opt or {}).get("ref", "") or "",
            "us_owner": (opt or {}).get("owner", "") or "",
            "physical_form": form, "form_basis": form_basis,
            "canonical_uom": uom,
            "supply_source": sup["src"], "supply_qty": sup["qty"],
            "join_class": str(sup["join"]), "coverage_status": str(sup["cov"]),
            "identity_status": str(sup["ident"]),
            "channel": "wayfair" if is_cg else "",
            "decision_state": decision, "demand_state": dstate,
            "demand_state_raw": demand["demand_state_raw"],
            "observed_months": demand["observed_months"],
            "censored_months": demand["censored_months"],
            "demand_source_key": demand["demand_source_key"],
            "demand_inherited": int(origin != "original"),
            "forecast_state": forecast, "forecast_basis": f_basis,
            "demand_note": ("demand_inherited_no_demand" if origin == "pool_demand_split" else ""),
            "netting_state": netting,
            "reason_group": group, "reason_code": reason,
            "is_nd": is_nd, "is_hm": is_hm, "is_kit": is_kit, "is_legacy": is_legacy,
            "is_cg": is_cg, "row_origin": origin, "gap_detail": note,
            "supply_kind": kind,
            "src_d1_row": row0.get("_src"),
            "source_refs": ("C:" + str(row0.get("source_refs") or ""))
            if row0.get("source_refs") else "",
        })

    for row0 in d1.to_dict("records"):
        pid = str(row0["product_id"])
        brows, rmethod = b_rows(pid)
        form, form_basis = pick_form(row0, brows)
        row0["_shared_policy"] = bool(
            str(row0["physical_form"]) in ("无适用", "", "未知") and brows
            and any("共享" in str(r.get("限制原因") or "") for r in brows))
        uom = str(row0["canonical_uom"])
        pool0 = str(row0["destination_pool"])
        obs = len(sales_pp.get((pid, "CG" if row0.get("is_cg") else pool0), set()))
        cens = (cens_map.get((pid, pool0, form, uom), 0)
                or cens_map.get((pid, pool0, str(row0["physical_form"]), uom), 0))
        demand = {"observed_months": obs, "censored_months": int(cens),
                  "demand_state_raw": ("observed" if obs else "censored" if cens > 0
                                       else "no_demand"),
                  "demand_source_key": f"{pid}|{pool0}|{form}|{uom}"}
        opts = market_options(row0, brows, form, form_basis)
        if not opts:
            add(row0, form, uom, row0.get("market") or "未证", pool0, None, "original",
                demand, form_basis, note="B 无该 base 的任何证据（含 60cm 继承）", rmethod=rmethod)
            continue
        exact = next((o for o in opts if o["pool"] == pool0), None)
        pref = "PL" if pool0 == "波兰" else "US"
        by_region = next((o for o in opts if o["market"] == pref), None)
        chosen = dict(exact or by_region or opts[0])
        chosen_pool_b = chosen["pool"]
        chosen["pool"] = pool0
        note = "" if exact else f"pool_market_mismatch: 供给池={pool0}，B owner 池={chosen_pool_b}"
        add(row0, form, uom, chosen["market"], pool0, chosen, "original", demand,
            form_basis, note=note, rmethod=rmethod)

    base_df = pd.DataFrame(rows_out)
    existing = set(zip(base_df["product_id"], base_df["market"], base_df["destination_pool"],
                       base_df["physical_form"], base_df["canonical_uom"]))
    have_m: dict[tuple, set] = {}
    for r in base_df.to_dict("records"):
        have_m.setdefault((r["product_id"], r["physical_form"], r["canonical_uom"]),
                          set()).add(str(r["market"]))
    split_by_form: dict[str, int] = {}
    split_by_prefix: dict[str, int] = {}
    for row0 in d1.to_dict("records"):
        if str(row0.get("market") or "") not in ("未证", "其他"):
            continue
        if str(row0["physical_form"]) != "皮壳" and not str(row0["product_id"]).upper().startswith("PK#"):
            continue
        pid = str(row0["product_id"]); uom = str(row0["canonical_uom"])
        brows, _ = b_rows(pid)
        form2, fb2 = pick_form(row0, brows)
        opts = market_options(row0, brows, form2, fb2)
        pool0 = str(row0["destination_pool"])
        obs = len(sales_pp.get((pid, "CG" if row0.get("is_cg") else pool0), set()))
        cens = (cens_map.get((pid, pool0, form2, uom), 0)
                or cens_map.get((pid, pool0, str(row0["physical_form"]), uom), 0))
        demand = {"observed_months": obs, "censored_months": int(cens),
                  "demand_state_raw": ("observed" if obs else "censored" if cens > 0
                                       else "no_demand"),
                  "demand_source_key": f"{pid}|{pool0}|{form2}|{uom}"}
        row0["_shared_policy"] = False
        for m in sorted({o["market"] for o in opts} - have_m.get((pid, form2, uom), set())):
            cand = next((o for o in opts if o["market"] == m), None)
            if cand is None:
                continue
            k = (pid, m, cand["pool"], form2, uom)
            if k in existing:
                continue
            existing.add(k)
            have_m.setdefault((pid, form2, uom), set()).add(m)
            add(row0, form2, uom, m, cand["pool"], cand, "split", demand, fb2,
                rmethod=b_rows(pid)[1])
            split_by_form[form2] = split_by_form.get(form2, 0) + 1
            _pfx = "PK#" if pid.upper().startswith("PK#") else "non-PK#"
            split_by_prefix[_pfx] = split_by_prefix.get(_pfx, 0) + 1

    df = pd.DataFrame(rows_out)

    # ---------- v2.1：market × destination_pool 一致性 ----------
    def correct_pool(r):
        if r.market == "PL":
            return "波兰"
        if r.market == "US":
            if str(r.destination_pool).startswith("CG"):
                return str(r.destination_pool)
            return str(r.us_owner) if str(r.us_owner) in ("美东USNJ", "美中USTX") else ""
        return ""

    def set_supply(r, pool):
        ck = c_key.get((r.product_id, pool, r.canonical_uom))
        if ck is not None:
            return {"supply_source": "C物理库存",
                    "supply_qty": (None if pd.isna(ck["可发供给"]) else float(ck["可发供给"])),
                    "join_class": ck["join_class"], "coverage_status": ck["覆盖状态"],
                    "identity_status": ck["身份状态"]}
        return {"supply_source": "无供给行", "supply_qty": None, "join_class": "no_join",
                "coverage_status": "未覆盖", "identity_status": "唯一"}

    keys_now = set(zip(df["product_id"], df["physical_form"], df["canonical_uom"],
                       df["market"], df["destination_pool"]))
    new_rows = []
    for i, r in df.iterrows():
        cp = correct_pool(r)
        m = (r.market in ("US", "PL") and cp and r.destination_pool == cp)
        df.at[i, "market_pool_match"] = int(bool(m))
        df.at[i, "pool_basis"] = "original_supply"
        df.at[i, "pool_mismatch_reason"] = ""
        if r.market not in ("US", "PL"):
            continue
        if m:
            continue
        # (1) 未证池：按 market/us_owner 回填
        if r.destination_pool == "未证" and cp:
            df.at[i, "destination_pool"] = cp
            df.at[i, "row_origin"] = "pool_backfill"
            df.at[i, "pool_basis"] = "market_derived"
            df.at[i, "market_pool_match"] = 1
            for k, v in set_supply(r, cp).items():
                df.at[i, k] = v
            continue
        # (2) 已有正确 pool 行 → 本行仅 observation
        if (r.product_id, r.physical_form, r.canonical_uom, r.market, cp) in keys_now:
            df.at[i, "pool_basis"] = "mismatch_observation"
            df.at[i, "pool_mismatch_reason"] = f"已有正确池行 {cp}；本行池={r.destination_pool}"
            continue
        # (3) 无正确池行：供给为 0/空且非 full → 直接改池
        if (r.supply_qty is None or (isinstance(r.supply_qty, float) and r.supply_qty == 0)
                or pd.isna(r.supply_qty)) and str(r.join_class) != "join_full":
            df.at[i, "destination_pool"] = cp
            df.at[i, "row_origin"] = "pool_backfill"
            df.at[i, "pool_basis"] = "market_derived"
            df.at[i, "market_pool_match"] = 1
            for k, v in set_supply(r, cp).items():
                df.at[i, k] = v
            continue
        # (4) 原池有真实供给 → 原行 observation + 新建正确池需求行
        df.at[i, "pool_basis"] = "mismatch_observation"
        df.at[i, "pool_mismatch_reason"] = f"原池={r.destination_pool} 有真实供给；另建 {cp} 需求行"
        nr = r.to_dict()
        _fm = fc_meta.get(r.product_id)
        _p_obs = len(sales_p.get(r.product_id, set()))
        if _fm is not None or _p_obs > 0:
            _fc, _fb = "fallback_model", "product_pool"
        elif cp in pool_has_sales:
            _fc, _fb = "fallback_model", "pool_mean"
        else:
            _fc, _fb = "not_estimable", "not_estimable"
        nr.update({"destination_pool": cp, "row_origin": "pool_demand_split",
                   "market_pool_match": 1, "pool_basis": "market_derived",
                   "demand_state": "no_demand", "demand_inherited": 1,
                   "forecast_state": _fc, "forecast_basis": _fb,
                   "demand_note": "demand_inherited_no_demand",
                   "pool_mismatch_reason": f"由 {r.destination_pool} 拆分"})
        nr.update(set_supply(r, cp))
        new_rows.append(nr)
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    def eligible_of(r):
        if r.decision_state != "active":
            return None
        if int(r.market_pool_match) != 1:
            return "observation"
        if str(r.channel) == "wayfair":
            return "observation"
        if str(r.get("supply_kind")) in ("observation", "inherit"):
            return "observation"
        if str(r.physical_form) in ("皮壳", "主体骨架", "骨架", "独立海绵"):
            return "observation"  # 组件/骨架/独立海绵只作观察，不进净额
        if str(r.join_class) == "join_full" and str(r.identity_status) == "唯一":
            return "eligible"
        return "supply_gap"

    for i, r in df.iterrows():
        if r.decision_state != "active":
            continue
        e = eligible_of(r)
        if e is not None and e != r.netting_state:
            df.at[i, "netting_state"] = e
            if e == "observation" and r.netting_state == "eligible":
                df.at[i, "reason_group"] = "supply"
                df.at[i, "reason_code"] = "market_pool_mismatch"

    for col, default in (("market_pool_match", 0), ("pool_basis", ""), ("pool_mismatch_reason", "")):
        if col not in df.columns:
            df[col] = default
    df["pool_basis"] = df["pool_basis"].fillna("")

    dup = int(df.duplicated(KEY).sum())
    merged = int(df.duplicated(KEY, keep="first").sum())
    merged_tbl = df[df.duplicated(KEY, keep="first")].copy()
    if merged:
        df = df[~df.duplicated(KEY, keep="first")].copy()

    # 原行 = 每条 D1 v2 行对应的主行（original 或 pool_backfill，仍是同一原行的行级去向）
    primary = df[df["row_origin"].isin(["original", "pool_backfill"])]
    pool_backfill = int((df["row_origin"] == "pool_backfill").sum())
    pool_demand_split = int((df["row_origin"] == "pool_demand_split").sum())
    split_rows = int((df["row_origin"] == "split").sum())
    disp = {
        "original_rows": len(d1), "primary_rows": int(len(primary)),
        "kept_original_label": int((df["row_origin"] == "original").sum()),
        "pool_backfill": pool_backfill,
        "split_rows": split_rows, "pool_demand_split": pool_demand_split,
        "merged": merged, "after": int(len(df)),
        "unaccounted": int(len(d1) - len(primary) - merged),
    }

    stats = {
        "before_rows": len(d1), "after_rows": len(df),
        "split_rows": disp["split_rows"], "merged": merged, "dup": dup,
        "split_by_form": split_by_form, "split_by_prefix": split_by_prefix,
        "row_origin": df["row_origin"].value_counts().to_dict(),
        "market_pool_match": {str(k): int(v) for k, v in df["market_pool_match"].value_counts().items()},
        "pool_basis": {str(k): int(v) for k, v in df["pool_basis"].value_counts().items()},
        "pool_backfill_by_form": df.loc[df["row_origin"] == "pool_backfill",
                                        "physical_form"].value_counts().to_dict(),
        "mismatch_obs_by_form": df.loc[df["pool_basis"] == "mismatch_observation",
                                      "physical_form"].value_counts().to_dict(),
        "pool_demand_split_by_form": df.loc[df["row_origin"] == "pool_demand_split",
                                          "physical_form"].value_counts().to_dict(),
        "eligible_by_form": df.loc[df["netting_state"] == "eligible",
                                   "physical_form"].value_counts().to_dict(),
        "demand_forecast": {f"{k[0]}|{k[1]}": int(v) for k, v in
                            df.groupby(["demand_state", "forecast_state"]).size().items()},
        "forecast_basis": df["forecast_basis"].value_counts().to_dict(),
        "policy_exempt_rows": int(df["market_basis"].astype(str).str.startswith("policy_exempt").sum()),
        "unproven_pool_rows": int((df["destination_pool"] == "未证").sum()),
        "unproven_pool_by_policy": int(((df["destination_pool"] == "未证")
                                        & (df["decision_state"] == "policy_excluded")).sum()),
        "form_backfilled": int((df["form_basis"] == "b_r10").sum()),
        "resolved_60cm": int(df["map_method"].eq("60cm_member").sum()),
        "decision": df["decision_state"].value_counts().to_dict(),
        "demand": df["demand_state"].value_counts().to_dict(),
        "forecast": df["forecast_state"].value_counts().to_dict(),
        "netting": df["netting_state"].value_counts().to_dict(),
        "group": df["reason_group"].value_counts().to_dict(),
        "market_unproven": int((df["reason_code"] == "market_unproven").sum()),
        "form_uom_unproven": int((df["reason_code"] == "form_uom_unproven").sum()),
        "shared_policy": int((df["reason_code"] == "shared_policy").sum()),
        "policy_rows": int((df["decision_state"] == "policy_excluded").sum()),
    }
    gaps = df[df["decision_state"] == "data_gap"]
    gap_rows = gaps[["product_id", "market", "destination_pool", "physical_form", "canonical_uom",
                     "reason_code", "gap_detail"]].to_dict("records")

    v1_path = Path(args.out_xlsx.replace("D1b_v2", "D1b"))
    obs_moves = {}
    if v1_path.exists():
        v1 = pd.read_excel(v1_path, sheet_name="1_资格")
        k4 = ["product_id", "destination_pool", "physical_form", "canonical_uom"]
        b4 = v1.set_index(k4)["demand_state"]
        cur = kept.set_index(k4)["demand_state"]
        moved = cur[cur != b4.reindex(cur.index)]
        obs_moves = moved.value_counts().to_dict()

    checks = {
        "A 覆盖 2,337": len(set(df["product_id"]) & active_ids) == 2337,
        "行数=3241+拆行+新建−归并":
            disp["after"] == 3241 + disp["split_rows"] + disp["pool_demand_split"] - merged,
        "原行去向 100%": disp["unaccounted"] == 0,
        "policy 进 gap=0": int(((df["decision_state"] == "data_gap")
                                & (df["reason_group"] == "policy")).sum()) == 0,
        "重复键=0": dup == 0,
        "非政策行 market_basis 100%": int(((df["decision_state"] != "policy_excluded")
                                          & (df["market_basis"].astype(str).str.strip() == "")).sum()) == 0,
        "政策行 market_basis 非空 100%": int(((df["decision_state"] == "policy_excluded")
                                            & (df["market_basis"].astype(str).str.strip() == "")).sum()) == 0,
        "共享供给只计一次": int(df.loc[df["identity_status"].astype(str).str.contains("共享"),
                                      "supply_qty"].notna().sum()) == 0,
        "未证池仅 ND 政策 97 行": int((df["destination_pool"] == "未证").sum()) == 97,
        "active&mismatch&eligible=0": int(((df["decision_state"] == "active")
                                           & (df["market_pool_match"] == 0)
                                           & (df["netting_state"] == "eligible")).sum()) == 0,
        "pool_basis 非空": int(df["pool_basis"].astype(str).str.strip().eq("").sum()) == 0,
        "皮壳/骨架/独立海绵无 eligible": int(df.loc[df["netting_state"] == "eligible",
                                                   "physical_form"].isin(
            ["皮壳", "主体骨架", "骨架", "独立海绵"]).sum()) == 0,
        "pool_demand_split 不重复需求": int(df.loc[df["row_origin"] == "pool_demand_split",
                                                "demand_state"].ne("no_demand").sum()) == 0,
        "no_demand&observed_model=0": int(((df["demand_state"] == "no_demand")
                                           & (df["forecast_state"] == "observed_model")).sum()) == 0,
        "observed_model 行 own>=3": int(df.loc[df["forecast_state"] == "observed_model",
                                              "observed_months"].lt(3).sum()) == 0,
        "forecast_basis 非空": int(df["forecast_basis"].astype(str).str.strip().eq("").sum()) == 0,
        "pool_demand_split 按新池取供给": all(
            (lambda ck, r: (r["supply_source"] == "C物理库存") == (ck is not None)
             and (ck is None or abs((r["supply_qty"] or 0)
                                    - (0 if pd.isna(ck["可发供给"]) else float(ck["可发供给"]))) < 1e-9))(
                c_key.get((r["product_id"], r["destination_pool"], r["canonical_uom"])), r)
            for r in df[df["row_origin"] == "pool_demand_split"].to_dict("records")),
    }
    payload = {"disposition": disp, "stats": stats, "checks": checks, "gap_rows": gap_rows,
               "observed_moves_vs_v1": obs_moves,
               "merged_detail": merged_tbl[KEY + ["row_origin", "src_d1_row"]].head(20).to_dict("records")}
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
        return 0

    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("依据", "Codex gpt-6.1-sol 评审 + 项目主补充：B 重算市场（含 60cm）、形态回填、双市场拆行"),
        ("键", "product_id × market × destination_pool × physical_form × canonical_uom"),
        ("身份", "保留原 product_id/前缀；PK#/ND#/HM#/TJ# 仅去前缀 join"),
        ("拆分", f"拆行 {disp['split_rows']}；池回填 {disp['pool_backfill']}；"
               f"新建 {disp['pool_demand_split']}；合并 {merged}"),
        ("需求", "沿用 D1/D2 原键 demand_state_raw/censored/observed；拆行只继承不加需求"),
        ("不做什么", "不预测、不补 0、不分配共享池、不生成采购、不写 EN/通途"),
        ("输入 SHA256 · B r10", sha256(Path(args.b_attrib))),
        ("输入 SHA256 · D1 v2", sha256(Path(args.d1))),
        ("输入 SHA256 · D2 v3", sha256(Path(args.d2))),
        ("输入 SHA256 · C v14", sha256(Path(args.c_stock))),
    ], columns=["项", "内容"])
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        df.to_excel(w, sheet_name="1_资格", index=False)
        r0 = 0
        for col in ("decision_state", "demand_state", "forecast_state", "netting_state",
                    "reason_group", "reason_code"):
            t = df[col].value_counts().rename_axis("值").reset_index(name="行数")
            pd.DataFrame([[col]]).to_excel(w, sheet_name="2_统计", index=False, startrow=r0,
                                           header=False)
            t.to_excel(w, sheet_name="2_统计", index=False, startrow=r0 + 1)
            r0 += len(t) + 4
        pd.DataFrame([{"项": k, "通过": v} for k, v in checks.items()]) \
            .to_excel(w, sheet_name="3_缺口", index=False)
        gaps[["product_id", "market", "destination_pool", "physical_form", "canonical_uom",
              "reason_code", "gap_detail"]] \
            .to_excel(w, sheet_name="3_缺口", index=False, startrow=len(checks) + 3)
        _split_out = df[df["row_origin"].isin(["split", "pool_demand_split"])][
            ["row_origin", "product_id", "market", "destination_pool", "physical_form",
             "canonical_uom", "market_basis", "market_evidence_ref", "pool_mismatch_reason",
             "src_d1_row"]]
        _split_out.to_excel(w, sheet_name="4_拆行对照", index=False)
        merged_tbl[KEY + ["row_origin", "src_d1_row"]]             .to_excel(w, sheet_name="4_拆行对照", index=False,
                      startrow=len(_split_out) + 3)
        pd.DataFrame([{"自检": k, "通过": v} for k, v in checks.items()]) \
            .to_excel(w, sheet_name="5_自检", index=False)

    out_sha = sha256(out)
    Path(args.out_report).write_text(render(df, payload, out_sha, contract), encoding="utf-8")
    manifest = {
        "rule_version": RULE_VERSION,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {n: sha256(Path(p)) for n, p in [
            ("orders_unified", args.orders), ("b_r10", args.b_attrib), ("c_v14", args.c_stock),
            ("d1_v2", args.d1), ("d2_v3", args.d2)]},
        "outputs": {"xlsx": {"path": str(out), "sha256": out_sha},
                    "report": {"path": str(args.out_report),
                               "sha256": sha256(Path(args.out_report))}},
        "counts": stats,
    }
    Path(str(out).replace(".xlsx", ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"disposition": disp, "checks": checks, "decision": stats["decision"]},
                     ensure_ascii=False, indent=1, default=str))
    print("workbook:", out)
    return 0


def render(df, payload, out_sha, contract) -> str:
    disp = payload["disposition"]; stats = payload["stats"]; checks = payload["checks"]
    L = ["# D1b v2.3 资格表（B 重算市场 + 60cm 继承 + 形态回填 + 双市场拆行 + 政策市场豁免；只读）", "",
         f"- `rule_version` = **{RULE_VERSION}**",
         f"- 原行 {disp['original_rows']:,} → 主行 {disp['primary_rows']:,}"
         f"（original {disp['kept_original_label']:,} + pool_backfill {disp['pool_backfill']:,}）"
         f" + 拆行 {disp['split_rows']:,} + 新建 {disp['pool_demand_split']:,}"
         f" − 归并 {disp['merged']:,} = {disp['after']:,}；未对账 {disp['unaccounted']}",
         "", "## 1. 原行去向", "", "| 项 | 值 |", "|---|---:|"]
    for k, v in disp.items():
        L.append(f"| {k} | {v} |")
    L += ["", "## 2. 状态计数", ""]
    for col in ("decision", "demand", "forecast", "netting", "group"):
        L += [f"### {col}", "", "| 值 | 行数 |", "|---|---:|"]
        for k, v in stats[col].items():
            L.append(f"| {k} | {v:,} |")
        L.append("")
    L += ["", "## 2.1 政策行的市场证据口径", "",
          "- 政策行（ND/HM/老产品/共享政策/TJ# 终端规则）**不需要市场证据**："
          "market_basis 统一写成 `policy_exempt|<reason_code>`。",
          f"- 本版补值 **{stats.get('policy_exempt_rows', 0)} 行**：ND 97 行 "
          "`policy_exempt|nd_component` + TJ# 3 行 `policy_exempt|kit_terminal_rule`；"
          "其余政策行沿用已有 B 证据。",
          "- 自检拆成两条：非政策行 market_basis 100%、政策行 market_basis 非空 100%。",
          "", "## 3. 自检", "", "| 项 | 通过 |", "|---|---|"]
    for k, v in checks.items():
        L.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    L += ["", "## 4. data_gap 清单", "", "| product_id | market | pool | form | reason |",
          "|---|---|---|---|---|"]
    for r in payload["gap_rows"]:
        L.append(f"| {r['product_id']} | {r['market']} | {r['destination_pool']} | "
                 f"{r['physical_form']} | {r['reason_code']} |")
    L += ["", "## 5. 只读声明", "",
          "本次仅本地读表/内存计算；未调用 EN/通途，未发消息，未 push。",
          "", f"- 工作簿 SHA256：`{out_sha}`"]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
