# -*- coding: utf-8 -*-
"""D2b v2 正式输入版：历史库存快照做删失上限（只读）。

- 键：D3b v3.1（1,853 键），不再用 D2 v3 旧键；
- 需求：orders_unified.parquet 直接按 (product×pool×month) 聚合；
- 删失：stockout_monthly_flags（EN×月 censored）；
- 历史上限：input_stock_status_daily（warehouse×sku×日）→ (EN,pool,月) min/mean/max available；
- 点估计：rate_upper（仅证据充分子集）；区间：NB-EM sensitivity-only（不声称 adopted）；
- C_cap_basis：historical_snapshot / current_snapshot_sensitivity / none。

--dry-run 只打印覆盖、方法与自检，不写文件。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

RULE_VERSION = "D2b-v2-2026-11-02"
STATUS = "exploratory"
MONTHS = [f"{y}{m:02d}" for y in (2025, 2026) for m in range(1, 13)][:22]
KEY = ["product_id", "pool", "physical_form", "canonical_uom"]
STOCK_MONTHS = {"202604", "202605", "202606", "202607", "202608", "202609", "202610"}


def _load_v1():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "d2b_v1", here / "d2b_censor_estimate_2026-11-02.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v1 = _load_v1()


def norm(code) -> str:
    c = str(code).strip()
    for p_ in ("删除", "~", "?", "？"):
        while c.startswith(p_):
            c = c[len(p_):].strip()
    return c.casefold()


def pool_of(w: str) -> str:
    s_ = str(w)
    if "WayfairCG" in s_ or s_.startswith("CG"):
        return "CG"
    if "退货" in s_:
        return "其他"
    if "Poland" in s_ or "波兰" in s_:
        return "波兰"
    if "CENTRADE" in s_ or "美东" in s_:
        return "美东USNJ"
    if "DANEEY" in s_ or "美中" in s_:
        return "美中USTX"
    return "其他"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    B = "D:/Work/fzh-order-store"
    ap = argparse.ArgumentParser(description="D2b v2 历史快照版（只读）")
    ap.add_argument("--d3b", default=f"{B}/analysis/D_历史归一与回测_D3b_v3_1_2026-11-02.xlsx")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--flags", default=f"{B}/en-demand-v1/stockout-censoring-2026-10-28/stockout_monthly_flags.parquet")
    ap.add_argument("--stock-daily", default=f"{B}/en-demand-v1/stockout-censoring-2026-10-28/input_stock_status_daily.parquet")
    ap.add_argument("--a-final", default=f"{B}/analysis/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--c-stock", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--customer-codes", default=f"{B}/analysis/en_item_customer_codes.csv")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--overrides", default=f"{B}/analysis/sku_mapping_overrides_2026-10-29.csv")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/D_删失需求估计_D2b_v2_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/D_删失需求估计_D2b_v2_2026-11-02_报告.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    # ---------- 键 ----------
    d3 = pd.read_excel(args.d3b, sheet_name="2_有效历史")
    d3["product_id"] = d3["product_id"].astype(str)
    keys = d3[KEY].drop_duplicates().reset_index(drop=True)

    # ---------- SKU → EN 映射 ----------
    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    active = a[a["活跃分类"] != "不活跃"].copy()
    active["EN物料"] = active["EN物料"].astype(str)
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

    # ---------- 需求（orders_unified） ----------
    o = pd.read_parquet(args.orders)
    o["sale_date"] = pd.to_datetime(o["sale_date"])
    o = o[(o["sale_date"] >= "2025-01-01") & (o["sale_date"] <= "2026-10-31")].copy()
    o["month"] = o["sale_date"].dt.strftime("%Y%m")
    o["en"] = o["sku_tongtool"].map(lambda s: idx.get(norm(s)))
    o["pool"] = o["warehouse"].map(pool_of)
    pos = o[o["en"].notna()]
    sales = (pos.groupby(["en", "pool", "month"])["qty"].sum().reset_index())
    sales_map = {(r["en"], r["pool"], r["month"]): float(r["qty"]) for r in sales.to_dict("records")}

    # ---------- 删失 flags ----------
    fl = pd.read_parquet(args.flags)
    fl["month"] = fl["month"].astype(str).str.replace("-", "")
    fl["en"] = fl["sku"].map(lambda s: idx.get(norm(s)))
    cens_set = {(r["en"], r["month"]) for r in fl[fl["censored"] == True].to_dict("records")
                if isinstance(r["en"], str)}

    # ---------- 历史库存上限 ----------
    st = pd.read_parquet(args.stock_daily)
    st["d"] = pd.to_datetime(st["d"])
    st["month"] = st["d"].dt.strftime("%Y%m")
    st["en"] = st["sku"].map(lambda s: idx.get(norm(s)))
    st["pool"] = st["warehouse"].map(pool_of)
    st = st[st["en"].notna()]
    daily = (st.groupby(["en", "pool", "d"])["available"].sum().reset_index())
    daily["month"] = daily["d"].dt.strftime("%Y%m")
    cap = (daily.groupby(["en", "pool", "month"])["available"]
           .agg(["min", "mean", "max"]).reset_index())
    cap_map = {(r["en"], r["pool"], r["month"]): (float(r["min"]), float(r["mean"]), float(r["max"]))
               for r in cap.to_dict("records")}

    # C v14 快照（无历史月份的敏感性回退）
    c4 = pd.read_excel(args.c_stock, sheet_name="4_可发供给")
    c4["product_id"] = c4["product_id"].astype(str)
    c_sup = {(r["product_id"], r["pool"], r["uom"]): r["可发供给"] for r in c4.to_dict("records")}

    key_out, month_out, fail_out = [], [], []
    cens_total = cens_with_hist = cens_with_snap = cens_unknown = 0
    for k in keys.to_dict("records"):
        pid, pool, form, uom = k["product_id"], k["pool"], k["physical_form"], k["canonical_uom"]
        rows = []
        n_obs = n_cens = 0
        hist_caps = []
        for m in MONTHS:
            q = sales_map.get((pid, pool, m), 0.0)
            m_dash = f"{m[:4]}-{m[4:]}"
            is_stock_month = m in STOCK_MONTHS
            cens_flag = (pid, m) in cens_set and is_stock_month
            hist = cap_map.get((pid, pool, m))
            snap = c_sup.get((pid, pool, uom))
            snap = None if snap is None or pd.isna(snap) else float(snap)
            if q > 0:
                state = "observed"
                n_obs += 1
            elif cens_flag:
                state = "censored"
                n_cens += 1
                hist_caps.append(hist)
            elif is_stock_month and hist is not None:
                state = "genuine_zero"
            else:
                state = "censor_unknown"
            if state == "censored":
                cens_total += 1
                if hist is not None:
                    cens_with_hist += 1
                elif snap is not None:
                    cens_with_snap += 1
                else:
                    cens_unknown += 1
            rows.append({"month": m, "observed": q, "state": state,
                         "hist_cap": hist, "snap_cap": snap})
        observed_demand = float(sum(r["observed"] for r in rows if r["state"] == "observed"))
        cap_basis = ("historical_snapshot" if n_cens and all(c is not None for c in hist_caps)
                     else "current_snapshot_sensitivity" if n_cens and any(
                         r["snap_cap"] is not None for r in rows if r["state"] == "censored")
                     else "none")
        if n_cens > 0 and n_obs >= 3:
            mu_vis = observed_demand / n_obs
            point = observed_demand + mu_vis * n_cens
            method = "rate_upper"
            # NB-EM 敏感性区间（historical cap 优先，缺失用 snap 或 1.5×均值）
            caps = []
            for r in rows:
                if r["state"] != "censored":
                    continue
                if r["hist_cap"] is not None:
                    caps.append(r["hist_cap"][2])
                elif r["snap_cap"] is not None:
                    caps.append(r["snap_cap"])
                else:
                    caps.append(mu_vis * 1.5)
            y = np.array([r["observed"] for r in rows
                          if r["state"] in ("observed", "genuine_zero")])
            mu, rr = v1.fit_moments(y) if len(y) else (mu_vis, 50.0)
            # 用上限跑一次 NB-EM（敏感性）
            y_all = np.array([r["observed"] for r in rows
                              if r["state"] in ("observed", "genuine_zero")])
            cens_arr = np.array([r["state"] == "censored" for r in rows
                                 if r["state"] in ("observed", "genuine_zero", "censored")])
            y_c = np.array([r["observed"] for r in rows
                            if r["state"] in ("observed", "genuine_zero", "censored")])
            caps_full = np.zeros(len(y_c))
            j = 0
            for i, r in enumerate([r for r in rows
                                   if r["state"] in ("observed", "genuine_zero", "censored")]):
                if r["state"] == "censored" and j < len(caps):
                    caps_full[i] = caps[j]
                    j += 1
            mu2, r2 = v1.em_key(y_c, cens_arr, caps_full, mu_vis)
            _mx = float(np.max(y)) if len(y) else mu_vis
            em_total = float(observed_demand + sum(
                min(v1.trunc_mean(mu2, r2, c), 3 * _mx, c) for c in caps)) if caps else point
            p10, p50, p90 = v1.nb_total_quantiles(mu2, r2, max(n_obs + n_cens, 1))
        else:
            method = "none" if n_cens == 0 else "censor_unknown"
            point = observed_demand
            em_total = observed_demand
            p10 = p50 = p90 = observed_demand
        if method == "censor_unknown":
            fail_out.append({"product_id": pid, "pool": pool, "physical_form": form,
                             "canonical_uom": uom, "fail_reason": "insufficient_history",
                             "n_censored_months": n_cens})
            continue
        key_out.append({
            "product_id": pid, "pool": pool, "physical_form": form, "canonical_uom": uom,
            "observed_demand": observed_demand, "estimated_demand": point,
            "estimated_p10": max(0.0, min(p10, point)), "estimated_p50": max(0.0, p50),
            "estimated_p90": max(0.0, max(p90, point)),
            "censor_method": method, "C_cap_basis": cap_basis,
            "interval_method": ("nb_em_sensitivity_only" if n_cens else "none"),
            "n_censored_months": n_cens, "n_observed_months": n_obs,
            "source_refs": f"D3b-v3.1:{pid}|{pool}|{form}|{uom};"
                           f"cap={cap_basis};histmonths={sorted({r['month'] for r in rows if r['hist_cap']})}",
        })
        for r in rows:
            month_out.append({
                "product_id": pid, "pool": pool, "physical_form": form,
                "canonical_uom": uom, "month": r["month"], "observed": r["observed"],
                "zero_class": r["state"],
                "C_lower": (r["hist_cap"][0] if r["hist_cap"] else None),
                "C_base": (r["hist_cap"][1] if r["hist_cap"] else None),
                "C_upper": (r["hist_cap"][2] if r["hist_cap"] else None),
                "C_snapshot": r["snap_cap"],
                "C_cap_basis": ("historical_snapshot" if r["hist_cap"] else
                                ("current_snapshot_sensitivity" if r["snap_cap"] else "none")),
            })

    key_df = pd.DataFrame(key_out)
    month_df = pd.DataFrame(month_out)
    fail_df = pd.DataFrame(fail_out, columns=["product_id", "pool", "physical_form",
                                              "canonical_uom", "fail_reason", "n_censored_months"])

    # ---------- 遮断回测（历史快照上限） ----------
    bt_rows = []
    for k in keys.to_dict("records"):
        pid, pool, form, uom = k["product_id"], k["pool"], k["physical_form"], k["canonical_uom"]
        series = [(m, sales_map.get((pid, pool, m), 0.0)) for m in MONTHS]
        if any((pid, m) in cens_set for m, _ in series):
            continue
        obs_idx = [i for i, (m, q) in enumerate(series) if q > 0]
        if len(obs_idx) < 8:
            continue
        for hid in (1, 2, 3):
            hide = obs_idx[-hid:]
            true_total = float(sum(series[i][1] for i in hide))
            if true_total <= 0:
                continue
            vis = [q for i, (m, q) in enumerate(series) if i not in hide]
            stratum = v1.classify_series(np.array(vis))
            mean_vis = float(np.mean(vis))
            caps = []
            for i in hide:
                h = cap_map.get((pid, pool, series[i][0]))
                caps.append(h[2] if h is not None else mean_vis * 1.5)
            y_c = np.array([q for i, (m, q) in enumerate(series) if i not in hide] + [0.0] * hid)
            cens_arr = np.array([False] * (len(series) - hid) + [True] * hid)
            caps_full = np.array([0.0] * (len(series) - hid) + caps)
            mu, rr = v1.em_key(y_c, cens_arr, caps_full, mean_vis)
            _mx = float(np.max(vis)) if vis else mu
            em = float(sum(min(v1.trunc_mean(mu, rr, c), 3 * _mx, c) for c in caps))
            p10, p50, p90 = v1.nb_total_quantiles(mu, rr, hid)
            for name, est, lo, hi in (("label_only", 0.0, 0.0, 0.0),
                                      ("rate_upper", mean_vis * hid, mean_vis * hid * 0.5,
                                       mean_vis * hid * 1.5),
                                      ("nb_em", em, p10, p90)):
                bt_rows.append({"horizon": hid, "stratum": stratum, "method": name,
                                "true": true_total, "est": est,
                                "wape_num": abs(est - true_total),
                                "mae_num": abs(est - true_total),
                                "covered80": int(lo <= true_total <= hi),
                                "bias_num": est - true_total})
    bt = pd.DataFrame(bt_rows)
    if len(bt):
        bt_agg = (bt.groupby(["stratum", "method"])
                  .agg(n=("true", "size"), true_sum=("true", "sum"),
                       wape=("wape_num", "sum"), mae=("mae_num", "mean"),
                       coverage80=("covered80", "mean"), bias=("bias_num", "sum"))
                  .reset_index())
        bt_agg["wape"] = bt_agg["wape"] / bt_agg["true_sum"]
        bt_agg["bias_rate"] = bt_agg["bias"] / bt_agg["true_sum"]
    else:
        bt_agg = pd.DataFrame()
    adopt = {}
    for stratum, g in bt_agg.groupby("stratum") if len(bt_agg) else []:
        base = g[g["method"].isin(["label_only", "rate_upper"])].sort_values("wape")
        emr = g[g["method"] == "nb_em"]
        if base.empty or emr.empty:
            continue
        b, e = base.iloc[0], emr.iloc[0]
        adopt[stratum] = bool(e["wape"] <= b["wape"] and e["mae"] <= b["mae"]
                              and (e["wape"] <= b["wape"] * 0.95 or e["mae"] <= b["mae"] * 0.95))

    checks = {
        "键数守恒": len(key_df) + len(fail_df) == len(keys),
        "非删失键 estimated=observed":
            int((key_df.loc[key_df["n_censored_months"] == 0, "estimated_demand"]
                 != key_df.loc[key_df["n_censored_months"] == 0, "observed_demand"]).sum()) == 0,
        "删失键 estimated>=observed":
            int((key_df.loc[key_df["n_censored_months"] > 0, "estimated_demand"]
                 < key_df.loc[key_df["n_censored_months"] > 0, "observed_demand"]).sum()) == 0,
        "p10<=p50<=p90": bool(((key_df["estimated_p10"] <= key_df["estimated_p50"])
                               & (key_df["estimated_p50"] <= key_df["estimated_p90"])).all()),
        "无负值": bool((key_df[["estimated_demand", "estimated_p10",
                                "estimated_p50", "estimated_p90"]] >= 0).all().all()),
        "source_refs 非空": bool(key_df["source_refs"].astype(str).str.strip().ne("").all()),
    }
    payload = {
        "keys": int(len(keys)), "output_keys": int(len(key_df)),
        "failed_keys": int(len(fail_df)),
        "censored_months": int(cens_total),
        "censored_with_historical_cap": int(cens_with_hist),
        "censored_with_snapshot_only": int(cens_with_snap),
        "censored_unknown": int(cens_unknown),
        "method_counts": key_df["censor_method"].value_counts().to_dict(),
        "cap_basis": key_df["C_cap_basis"].value_counts().to_dict(),
        "demand_lift": float(key_df["estimated_demand"].sum() - key_df["observed_demand"].sum()),
        "backtest": bt_agg.to_dict("records") if len(bt_agg) else [],
        "adoption": [{"stratum": k, "adopted": v} for k, v in adopt.items()],
        "checks": checks,
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
        return 0

    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("status", "exploratory（探索版）"),
        ("key_source", "D3b v3.1（1,853 键）；不使用 D2 v3 旧键"),
        ("point_method", "rate_upper（可见月均值 × 删失月；仅证据充分子集 n_obs>=3）"),
        ("interval_method", "nb_em_sensitivity_only / uncalibrated_conservative（不声称 adopted）"),
        ("C_cap_basis", "historical_snapshot（有快照月）/ current_snapshot_sensitivity（无快照）/ none"),
        ("历史库存来源", "input_stock_status_daily.parquet（2026-04..10，primary_sellable 三仓）"
                     "；货盘逐日 available 按 EN×池 汇总取月 min/mean/max"),
        ("删失来源", "stockout_monthly_flags.parquet（EN×月 censored）"),
        ("覆盖月份", "历史快照 2026-04..2026-10；2025-01..2026-03 无库存证据 → censor_unknown"),
        ("formal_blocker", "无（已有历史快照）；仍为探索版，需 D3b v3 键复核后转正式"),
        ("输入 SHA256 · D3b v3.1", sha256(Path(args.d3b))),
        ("输入 SHA256 · orders_unified", sha256(Path(args.orders))),
        ("输入 SHA256 · stock_daily", sha256(Path(args.stock_daily))),
        ("输入 SHA256 · stockout_flags", sha256(Path(args.flags))),
    ], columns=["项", "内容"])
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        key_df.to_excel(w, sheet_name="1_键级估计", index=False)
        month_df.to_excel(w, sheet_name="2_月度估计", index=False)
        pd.DataFrame([{"自检": k, "通过": v} for k, v in checks.items()]) \
            .to_excel(w, sheet_name="3_自检", index=False)
        fail_df.to_excel(w, sheet_name="4_失败与回退", index=False)
    out_sha = sha256(out)
    Path(args.out_report).write_text(render(payload, key_df, fail_df, out_sha), encoding="utf-8")
    manifest = {
        "rule_version": RULE_VERSION, "status": STATUS,
        "point_method": "rate_upper",
        "interval_method": "nb_em_sensitivity_only / uncalibrated_conservative",
        "C_cap_basis": "historical_snapshot | current_snapshot_sensitivity",
        "inputs": {n: sha256(Path(p)) for n, p in [
            ("d3b_v3_1", args.d3b), ("orders_unified", args.orders),
            ("stock_daily", args.stock_daily), ("stockout_flags", args.flags)]},
        "outputs": {"xlsx": {"path": str(out), "sha256": out_sha},
                    "report": {"path": str(args.out_report),
                               "sha256": sha256(Path(args.out_report))}},
        "counts": payload,
    }
    Path(str(out).replace(".xlsx", ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("keys", "output_keys", "failed_keys",
                                              "censored_months", "censored_with_historical_cap",
                                              "censored_unknown", "method_counts", "checks")},
                     ensure_ascii=False, indent=1, default=str))
    print("workbook:", out)
    return 0


def render(payload, key_df, fail_df, out_sha) -> str:
    L = ["# D2b v2 删失需求估计（历史快照版；探索）", "",
         f"- `rule_version` = **{RULE_VERSION}**；**status = exploratory**",
         f"- 键 {payload['keys']}；输出 {payload['output_keys']} + 失败 {payload['failed_keys']}",
         "", "## 1. 历史快照覆盖", "",
         "| 项 | 数 |", "|---|---:|",
         f"| 删失月合计 | {payload['censored_months']:,} |",
         f"| 有历史快照上限 | {payload['censored_with_historical_cap']:,} |",
         f"| 仅当前快照（sensitivity） | {payload['censored_with_snapshot_only']:,} |",
         f"| 仍 censor_unknown | {payload['censored_unknown']:,} |",
         "", "## 2. 方法与上限口径", "",
         "| censor_method | 键数 |", "|---|---:|"]
    for k, v in payload["method_counts"].items():
        L.append(f"| {k} | {v:,} |")
    L += ["", "| C_cap_basis | 键数 |", "|---|---:|"]
    for k, v in payload["cap_basis"].items():
        L.append(f"| {k} | {v:,} |")
    L += ["", "## 2.1 遮断回测（历史快照上限）", "",
          "| 分层 | 方法 | n | WAPE | MAE | coverage80 | 上偏率 |", "|---|---|---:|---:|---:|---:|---:|"]
    for r in payload.get("backtest", []):
        L.append(f"| {r['stratum']} | {r['method']} | {int(r['n'])} | {r['wape']:.3f} | "
                 f"{r['mae']:.3f} | {r['coverage80']:.3f} | {r['bias_rate']:.3f} |")
    L += ["", "采用判断（NB-EM vs 最优基线）：", ""]
    for r in payload.get("adoption", []):
        L.append(f"- {r['stratum']}: **{'adopted' if r['adopted'] else 'not_adopted（仅敏感性）'}**")
    L += ["", "## 3. 自检", "", "| 项 | 通过 |", "|---|---|"]
    for k, v in payload["checks"].items():
        L.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    L += ["", "## 4. 失败与回退", "", "| product_id | pool | form | uom | reason |",
          "|---|---|---|---|---|"]
    for r in fail_df.head(50).to_dict("records"):
        L.append(f"| {r['product_id']} | {r['pool']} | {r['physical_form']} | "
                 f"{r['canonical_uom']} | {r['fail_reason']} |")
    L += ["", "## 5. 边界", "",
          "点估计 rate_upper；区间 NB-EM 仅敏感性、未校准；不覆盖 raw、不填 0、不进净额；"
          "未写 EN/通途、未 push。", "", f"- 工作簿 SHA256：`{out_sha}`"]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
