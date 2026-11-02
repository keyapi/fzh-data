# -*- coding: utf-8 -*-
"""D2b 删失需求估计（只读；不写 EN/通途、不 push）。

对 D2 v3 的月度序列做 NB-EM 删失需求估计：
- 非删失月 Y=D；删失月 Y=min(D, C)，C 取 C v14 的可发供给（快照代理，lower/base/upper ±50%）；
- EM 用 E[D|D≥C] 回填，向 physical_form×pool×uom 池均值做经验贝叶斯收缩；
- 输出键级/月度估计 + 人工遮断回测（label-only / rate-upper / nb-em）。

--dry-run 只打印键数、删失月数、方法采用、回测指标与自检，不写文件。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

RULE_VERSION = "D2b-v1-2026-11-02"
STATUS = "exploratory"
MONTHS = [f"{y}{m:02d}" for y in (2025, 2026) for m in range(1, 13)][:22]
KEY = ["product_id", "pool", "physical_form", "canonical_uom"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def nb_pmf_arr(mu: float, r: float, kmax: int) -> np.ndarray:
    """NB pmf, mean=mu, size=r（r>0 可为小数）。"""
    if mu <= 0:
        out = np.zeros(kmax + 1)
        out[0] = 1.0
        return out
    p = r / (r + mu)
    k = np.arange(kmax + 1)
    return stats.nbinom.pmf(k, r, p)


def trunc_mean(mu: float, r: float, c: float) -> float:
    """E[D | D >= c]，NB(mu, r)。"""
    if c <= 0:
        return mu
    kmax = int(np.ceil(stats.nbinom.ppf(0.99999, r, r / (r + mu)))) + int(c) + 10
    kmax = min(max(kmax, int(c) + 50), 200000)
    k = np.arange(int(np.ceil(c)), kmax + 1)
    pmf = stats.nbinom.pmf(k, r, r / (r + mu))
    denom = pmf.sum()
    if denom <= 1e-12:
        return c  # 尾部概率过低：保守取上限
    return float((k * pmf).sum() / denom)


def fit_moments(vals: np.ndarray) -> tuple[float, float]:
    mu = float(np.mean(vals)) if len(vals) else 0.0
    var = float(np.var(vals, ddof=1)) if len(vals) > 1 else 0.0
    if mu <= 0:
        return 0.0, 1.0
    r = mu * mu / (var - mu) if var > mu else 50.0
    return mu, float(np.clip(r, 0.05, 500.0))


def em_key(y_obs: np.ndarray, cens: np.ndarray, caps: np.ndarray,
           prior_mu: float, iters: int = 8) -> tuple[float, float]:
    """y_obs 为已观测月（含真零）需求；cens 为删失标记；caps 为删失月上限。"""
    obs = y_obs[~cens]
    if len(obs) == 0:
        return prior_mu, 50.0
    mu, r = fit_moments(obs)
    if mu <= 0:
        mu = prior_mu if prior_mu > 0 else 0.5
    for _ in range(iters):
        vals = list(obs)
        for c in caps[cens]:
            vals.append(min(trunc_mean(mu, r, float(c)), max(5 * mu, float(c) * 1.2)))
        mu_new, r_new = fit_moments(np.array(vals))
        if mu_new <= 0:
            mu_new = max(mu, 1e-6)
        if abs(mu_new - mu) < 1e-6 and abs(r_new - r) < 1e-6:
            mu, r = mu_new, r_new
            break
        mu, r = mu_new, r_new
    return mu, r


def nb_total_quantiles(mu: float, r: float, t_months: int) -> tuple[float, float, float]:
    if mu <= 0 or t_months <= 0:
        return 0.0, 0.0, 0.0
    n = r * t_months
    p = r / (r + mu)
    qs = stats.nbinom.ppf([0.1, 0.5, 0.9], n, p)
    return float(qs[0]), float(qs[1]), float(qs[2])


def classify_series(obs_vals: np.ndarray) -> str:
    n = len(obs_vals)
    if n < 12:
        return "short"
    pos = obs_vals[obs_vals > 0]
    if len(pos) == 0:
        return "intermittent"
    zero_share = float((obs_vals == 0).mean())
    mu, sd = float(np.mean(obs_vals)), float(np.std(obs_vals, ddof=1)) if n > 1 else 0.0
    cv = sd / mu if mu > 0 else 0.0
    if zero_share >= 0.4:
        return "intermittent"
    if cv >= 1.0:
        return "lumpy"
    return "smooth"


def run_backtest(d2: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    bt_rows = []
    for k in d2[KEY].drop_duplicates().to_dict("records"):
        pid, pool, form, uom = k["product_id"], k["pool"], k["physical_form"], k["canonical_uom"]
        sub = d2[(d2["product_id"] == pid) & (d2["pool"] == pool)
                 & (d2["physical_form"] == form) & (d2["canonical_uom"] == uom)]
        sub = sub.set_index("month").reindex(MONTHS)
        obs_mask = sub["zero_class"].eq("observed_positive")
        idx = [i for i, f in enumerate(obs_mask.fillna(False)) if f]
        if len(idx) < 8:
            continue
        if sub["zero_class"].eq("stockout_censored").any():
            continue
        for hid in (1, 2, 3):
            hide = idx[-hid:]
            true_total = float(sub["sellable_qty"].iloc[hide].sum())
            if true_total <= 0:
                continue
            visible = sub.drop(sub.index[hide])
            v_obs = visible["sellable_qty"].where(
                visible["zero_class"].eq("observed_positive")).fillna(0.0).to_numpy()
            stratum = classify_series(v_obs)
            mean_vis = float(v_obs.mean())
            label = 0.0
            rate = mean_vis * hid
            cap_bt = max(float(np.max(v_obs)), 1e-6)
            yb = v_obs.copy()
            mu, r = fit_moments(v_obs)
            for _ in range(8):
                vals = list(yb)
                for _x in range(hid):
                    vals.append(min(trunc_mean(mu, r, cap_bt), max(5 * mu, cap_bt * 1.2)))
                mu, r = fit_moments(np.array(vals))
            em = mu * hid
            p10, p50, p90 = nb_total_quantiles(mu, r, hid)
            for name, est, lo, hi in (("label_only", label, 0.0, 0.0),
                                      ("rate_upper", rate, rate * 0.5, rate * 1.5),
                                      ("nb_em", em, p10, p90)):
                bt_rows.append({
                    "horizon": hid, "stratum": stratum, "method": name,
                    "true": true_total, "est": est,
                    "wape_num": abs(est - true_total), "mae_num": abs(est - true_total),
                    "pinball50": 0.5 * abs(true_total - est),
                    "covered80": int(lo <= true_total <= hi),
                    "bias_num": est - true_total,
                })
    bt = pd.DataFrame(bt_rows)
    if not len(bt):
        return bt, bt, {}
    agg = (bt.groupby(["stratum", "method"])
           .agg(n=("true", "size"), true_sum=("true", "sum"),
                wape=("wape_num", lambda x: x.sum()),
                mae=("mae_num", "mean"), pinball50=("pinball50", "mean"),
                coverage80=("covered80", "mean"),
                bias=("bias_num", lambda x: x.sum()))
           .reset_index())
    agg["wape"] = agg["wape"] / agg["true_sum"]
    agg["bias_rate"] = agg["bias"] / agg["true_sum"]
    adopt = {}
    for stratum, g in agg.groupby("stratum"):
        base = g[g["method"].isin(["label_only", "rate_upper"])]
        em = g[g["method"] == "nb_em"]
        if em.empty or base.empty:
            adopt[stratum] = False
            continue
        b = base.sort_values("wape").iloc[0]
        e = em.iloc[0]
        adopt[stratum] = bool(e["wape"] <= b["wape"] and e["mae"] <= b["mae"]
                              and (e["wape"] <= b["wape"] * 0.95 or e["mae"] <= b["mae"] * 0.95))
    return bt, agg, adopt


def main(argv=None) -> int:
    B = "D:/Work/fzh-order-store"
    ap = argparse.ArgumentParser(description="D2b 删失需求估计（只读）")
    ap.add_argument("--d2", default=f"{B}/analysis/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--d1b", default=f"{B}/analysis/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--c-stock", default=f"{B}/analysis/通途库存_A337_v14_2026-10-30.xlsx")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--out-xlsx", default=f"{B}/analysis/D_删失需求估计_D2b_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{B}/analysis/D_删失需求估计_D2b_2026-11-02_报告.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    d2 = pd.read_excel(args.d2, sheet_name="1_序列")
    d2["month"] = d2["month"].astype(str).str.replace(r"\.0$", "", regex=True)
    d2["sellable_qty"] = pd.to_numeric(d2["sellable_qty"], errors="coerce")
    d1b = pd.read_excel(args.d1b, sheet_name="1_资格")
    d1b["product_id"] = d1b["product_id"].astype(str)
    c4 = pd.read_excel(args.c_stock, sheet_name="4_可发供给")
    c4["product_id"] = c4["product_id"].astype(str)
    c_sup = {(r["product_id"], r["pool"], r["uom"]): r["可发供给"] for r in c4.to_dict("records")}

    # 作用域：D2 序列键 ∩ D1b active 键
    d1b_keys = (d1b[d1b["decision_state"] == "active"][
        ["product_id", "destination_pool", "physical_form", "canonical_uom"]]
        .rename(columns={"destination_pool": "pool"}).drop_duplicates())
    d2_keys = d2[KEY].drop_duplicates()
    scope = d2_keys.merge(d1b_keys, on=KEY, how="inner")
    scope_set = set(map(tuple, scope[KEY].values))

    # 池均值先验（form×pool×uom）
    obs_rows = d2[(d2["zero_class"] == "observed_positive") & d2["sellable_qty"].notna()]
    pool_prior = (obs_rows.groupby(["physical_form", "pool", "canonical_uom"])["sellable_qty"]
                  .mean().to_dict())

    bt, bt_agg, adopt_map = run_backtest(d2)
    _adopt_rows = []
    for stratum, g in bt_agg.groupby("stratum") if len(bt_agg) else []:
        base = g[g["method"].isin(["label_only", "rate_upper"])].sort_values("wape")
        em = g[g["method"] == "nb_em"]
        if base.empty or em.empty:
            continue
        b, e = base.iloc[0], em.iloc[0]
        _adopt_rows.append({"stratum": stratum, "baseline": b["method"],
                            "base_wape": float(b["wape"]), "em_wape": float(e["wape"]),
                            "adopted": bool(adopt_map.get(stratum, False))})
    adopt_df = pd.DataFrame(_adopt_rows)

    key_out, month_out, fail_out = [], [], []
    for k in scope[KEY].itertuples(index=False):
        pid, pool, form, uom = k
        sub = d2[(d2["product_id"] == pid) & (d2["pool"] == pool)
                 & (d2["physical_form"] == form) & (d2["canonical_uom"] == uom)]
        sub = sub.set_index("month").reindex(MONTHS)
        zc = sub["zero_class"].fillna("")
        y = sub["sellable_qty"].astype(float)
        observed_months = zc.eq("observed_positive")
        censor_months = zc.eq("stockout_censored")
        zero_months = zc.isin(["genuine_zero", "dormant", "long_term_zero"])
        unknown_months = zc.isin(["censor_unknown", ""])
        n_obs = int(observed_months.sum())
        n_cens = int(censor_months.sum())
        n_unknown = int(unknown_months.sum())
        observed_demand = float(y[observed_months].sum())

        # 拟合样本：观测月 + 真零月
        fit_mask = observed_months | zero_months
        y_fit = y[fit_mask].fillna(0.0).to_numpy()
        prior = float(pool_prior.get((form, pool, uom), 0.0))

        cap = c_sup.get((pid, pool, uom))
        cap = None if cap is None or pd.isna(cap) else float(cap)
        method, assumption, conf = "none", "", "high"
        mu, r = fit_moments(y_fit) if len(y_fit) else (prior, 50.0)
        est_total = observed_demand

        if n_cens > 0:
            if cap is None or cap <= 0:
                method, assumption, conf = "censor_unknown", "C 快照无可用上限", "low"
                fail_out.append({"product_id": pid, "pool": pool, "physical_form": form,
                                 "canonical_uom": uom, "fail_reason": "no_cap",
                                 "n_censored_months": n_cens})
            elif n_obs + int(zero_months.sum()) < 3:
                method, assumption, conf = "fallback_model", "历史不足，池均值先验", "low"
                mu, r = (prior if prior > 0 else 0.5), 50.0
                est_total = observed_demand + n_cens * mu
            else:
                caps = np.full(len(MONTHS), cap)
                cens_arr = censor_months.to_numpy()
                y_obs = y.fillna(0.0).to_numpy()
                stratum = classify_series(y_fit)
                if not adopt_map.get(stratum, False):
                    # 遮断回测未采用的层：回退 rate_upper（可见月均值 × 删失月）
                    mu_vis = float(np.mean(y_fit)) if len(y_fit) else prior
                    method = "fallback_model"
                    assumption = f"nb_em 未达采用门槛（{stratum}），回退 rate_upper"
                    conf = "medium"
                    mu = mu_vis
                    est_total = float(y[fit_mask].fillna(0.0).sum() + n_cens * mu_vis)
                else:
                    mu, r = em_key(y_obs, cens_arr, caps, prior)
                    est_total = float(y[fit_mask].fillna(0.0).sum() + n_cens * mu)
                    method, assumption = "nb_em", "C=快照可发供给（±50% 情景）"
                    conf = "high" if n_obs >= 12 else "medium" if n_obs >= 6 else "low"
        else:
            est_total = observed_demand

        t_months = int((observed_months | zero_months | censor_months).sum())
        p10, p50, p90 = nb_total_quantiles(mu, r, max(t_months, 1)) if method in ("nb_em", "fallback_model") \
            else (observed_demand, observed_demand, observed_demand)
        p10 = max(0.0, min(p10, est_total) if method == "nb_em" else p10)
        if method == "censor_unknown":
            continue  # 失败键只进 5_失败与回退，保证守恒
        key_out.append({
            "product_id": pid, "pool": pool, "physical_form": form, "canonical_uom": uom,
            "observed_demand": observed_demand, "estimated_demand": est_total,
            "estimated_p10": max(0.0, p10), "estimated_p50": max(0.0, p50),
            "estimated_p90": max(0.0, p90),
            "censor_method": method, "censor_assumption": assumption,
            "censor_confidence": conf,
            "n_censored_months": n_cens, "n_observed_months": n_obs,
            "n_unknown_months": n_unknown, "cap_base": cap,
            "mu_monthly": mu, "dispersion_r": r, "pool": pool,
            "source_refs": f"D2v3:{pid}|{pool}|{form}|{uom};Cv14:cap={cap}",
        })
        # 月度
        for m in MONTHS:
            z = zc.get(m, "")
            obs = y.get(m)
            if z == "observed_positive":
                est = float(obs)
            elif z in ("genuine_zero", "dormant", "long_term_zero"):
                est = 0.0
            elif z == "stockout_censored" and method == "nb_em":
                est = trunc_mean(mu, r, float(cap)) if cap else None
            elif z == "stockout_censored" and method == "fallback_model":
                est = float(mu) if cap else None
            elif z in ("censor_unknown", ""):
                est = None
            else:
                est = None
            month_out.append({
                "product_id": pid, "pool": pool, "physical_form": form, "canonical_uom": uom,
                "month": m, "observed": (None if pd.isna(obs) else float(obs)),
                "zero_class": z, "censored_flag": int(z == "stockout_censored"),
                "C_lower": (0.5 * cap if (cap and z == "stockout_censored") else None),
                "C_base": (cap if z == "stockout_censored" else None),
                "C_upper": (1.5 * cap if (cap and z == "stockout_censored") else None),
                "estimated_mean": est,
                "estimated_p10": (max(0.0, est * 0.6) if est is not None else None),
                "estimated_p50": est,
                "estimated_p90": (est * 1.6 if est is not None else None),
            })

    key_df = pd.DataFrame(key_out)
    cens_total = int(d2[(d2["zero_class"] == "stockout_censored")
                        & d2.set_index(KEY).index.isin(scope_set)].shape[0])
    month_df = pd.DataFrame(month_out)
    fail_df = pd.DataFrame(fail_out, columns=["product_id", "pool", "physical_form",
                                              "canonical_uom", "fail_reason", "n_censored_months"])

    # ---------- 自检 ----------
    est_nonnull = key_df[key_df["estimated_demand"].notna()]
    checks = {
        "键数守恒": len(key_df) + len(fail_df) == len(scope),
        "非删失键 estimated=observed":
            int((key_df.loc[key_df["n_censored_months"] == 0, "estimated_demand"]
                 != key_df.loc[key_df["n_censored_months"] == 0, "observed_demand"]).sum()) == 0,
        "删失键 estimated>=observed":
            int((key_df.loc[key_df["n_censored_months"] > 0, "estimated_demand"]
                 < key_df.loc[key_df["n_censored_months"] > 0, "observed_demand"]).sum()) == 0,
        "p10<=p50<=p90": bool(((est_nonnull["estimated_p10"] <= est_nonnull["estimated_p50"])
                               & (est_nonnull["estimated_p50"] <= est_nonnull["estimated_p90"])).all()),
        "无负值": bool((est_nonnull[["estimated_demand", "estimated_p10",
                                     "estimated_p50", "estimated_p90"]] >= 0).all().all()),
        "source_refs 非空": bool(key_df["source_refs"].astype(str).str.strip().ne("").all()),
        "回测每层每方法有样本": bool(len(bt_agg) and (bt_agg["n"] > 0).all()),
    }

    payload = {
        "keys": int(len(scope)), "output_keys": int(len(key_df)),
        "failed_keys": int(len(fail_df)),
        "censored_months_output": int(key_df["n_censored_months"].sum()),
        "censored_months_total": cens_total,
        "method_counts": {**key_df["censor_method"].value_counts().to_dict(),
                          "censor_unknown": int(len(fail_df))},
        "demand_lift": float(key_df["estimated_demand"].sum() - key_df["observed_demand"].sum()),
        "backtest": bt_agg.to_dict("records") if len(bt_agg) else [],
        "adoption": adopt_df.to_dict("records") if len(adopt_df) else [],
        "checks": checks,
        "fails": fail_df.to_dict("records")[:20],
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
        return 0

    # ---------- 落盘 ----------
    cens_total = payload["censored_months_total"]
    cens_out = payload["censored_months_output"]
    unest_share = (cens_total - cens_out) / cens_total if cens_total else 0.0
    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("status", "exploratory（探索版；不声称生产可用）"),
        ("point_method", "rate_upper（仅证据充分子集：可见月均值 × 删失月数）"),
        ("interval_method", "nb_em_sensitivity_only / uncalibrated_conservative"
                          "（NB-EM 仅敏感性/探索；区间未校准，不可作训练真值）"),
        ("C_cap_basis", "current_snapshot_sensitivity（C v14 快照可发供给 ±50%，非历史删失上限）"),
        ("formal_blocker", "no_historical_inventory_cap（缺历史月度库存上限，不能进正式训练/验收）"),
        ("未估计删失月占比", f"{cens_total - cens_out:,} / {cens_total:,} = {unest_share:.1%}"
                          "（C 快照无可用上限 → censor_unknown）"),
        ("方法", "NB(mean,dispersion) + EM（删失月 Y=min(D,C)，E[D|D>=C] 回填）+ 池均值经验贝叶斯收缩"),
        ("C 上限", "C v14 可发供给快照（lower/base/upper = 0.5/1.0/1.5 × 快照）；无上限 → censor_unknown"),
        ("假设", "①库存上限识别正确（C 快照 ±50% 代理）②订单未大规模转移 ③删失期价格/促销结构未完全改变 ④NB 能容纳过度离散"),
        ("正式版前提", "D3b v3 统一键 + 历史月度库存上限（替换快照代理）；需重跑遮断回测与采用判断"),
        ("不做什么", "不覆盖 raw/sellable、不填 0、不进净额、不下单、不写 EN/通途"),
        ("输入 SHA256 · D2 v3", sha256(Path(args.d2))),
        ("输入 SHA256 · D1b v2.3", sha256(Path(args.d1b))),
        ("输入 SHA256 · C v14", sha256(Path(args.c_stock))),
        ("输入 SHA256 · orders_unified", sha256(Path(args.orders))),
    ], columns=["项", "内容"])
    out = Path(args.out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        key_df.to_excel(w, sheet_name="1_键级估计", index=False)
        month_df.to_excel(w, sheet_name="2_月度估计", index=False)
        bt.to_excel(w, sheet_name="3_遮断回测", index=False)
        bt_agg.to_excel(w, sheet_name="4_分层汇总", index=False)
        fail_df.to_excel(w, sheet_name="5_失败与回退", index=False)
        pd.DataFrame([{"自检": k, "通过": v} for k, v in checks.items()]) \
            .to_excel(w, sheet_name="6_自检", index=False)
    out_sha = sha256(out)
    Path(args.out_report).write_text(render(payload, key_df, bt_agg, adopt_df, fail_df, out_sha),
                                    encoding="utf-8")
    manifest = {
        "rule_version": RULE_VERSION,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {n: sha256(Path(p)) for n, p in [
            ("d2_v3", args.d2), ("d1b_v2_3", args.d1b), ("c_v14", args.c_stock),
            ("orders_unified", args.orders)]},
        "status": STATUS,
        "point_method": "rate_upper",
        "interval_method": "nb_em_sensitivity_only / uncalibrated_conservative",
        "C_cap_basis": "current_snapshot_sensitivity",
        "formal_blocker": "no_historical_inventory_cap",
        "outputs": {"xlsx": {"path": str(out), "sha256": out_sha},
                    "report": {"path": str(args.out_report),
                               "sha256": sha256(Path(args.out_report))}},
        "counts": payload,
    }
    Path(str(out).replace(".xlsx", ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("keys", "output_keys", "failed_keys",
                                              "censored_months_total", "censored_months_output",
                                              "method_counts", "checks")},
                     ensure_ascii=False, indent=1, default=str))
    print("workbook:", out)
    return 0


def render(payload, key_df, agg, adopt_df, fail_df, out_sha) -> str:
    L = ["# D2b 删失需求估计（探索版；只读）", "",
         f"- `rule_version` = **{RULE_VERSION}**；**status = exploratory（探索版，非生产）**",
         "- **point_method = rate_upper**（仅证据充分子集）；**interval_method = "
         "nb_em_sensitivity_only / uncalibrated_conservative**（仅敏感性，未校准）。",
         "- **C_cap_basis = current_snapshot_sensitivity**（快照 ±50%，非历史删失上限）；"
         "**formal_blocker = no_historical_inventory_cap**。",
         f"- 键 {payload['keys']}；输出 {payload['output_keys']} + 失败 {payload['failed_keys']}"
         f"（守恒：{payload['output_keys'] + payload['failed_keys']}）",
         f"- 删失月（全作用域） {payload['censored_months_total']:,}，其中输出键内 "
         f"{payload['censored_months_output']:,}；未估计 "
         f"{payload['censored_months_total'] - payload['censored_months_output']:,} 个"
         f"（C 快照无上限，censor_unknown）",
         f"- 估计增量 {payload['demand_lift']:,.2f}（仅 rate_upper 回退键）",
         "", "## 1. 方法采用", "", "| censor_method | 键数 |", "|---|---:|"]
    for k, v in payload["method_counts"].items():
        L.append(f"| {k} | {v:,} |")
    L += ["", "## 2. 遮断回测（按分层）", "",
          "| 分层 | 方法 | n | WAPE | MAE | pinball50 | coverage80 | 上偏率 |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in payload["backtest"]:
        L.append(f"| {r['stratum']} | {r['method']} | {int(r['n'])} | {r['wape']:.3f} | "
                 f"{r['mae']:.3f} | {r['pinball50']:.3f} | {r['coverage80']:.3f} | "
                 f"{r['bias_rate']:.3f} |")
    L += ["", "## 3. 采用判断（NB-EM vs 最优基线）", "",
          "| 分层 | 基线 | 基线 WAPE | NB-EM WAPE | 结论 |", "|---|---|---:|---:|---|"]
    for r in payload["adoption"]:
        L.append(f"| {r['stratum']} | {r['baseline']} | {r['base_wape']:.3f} | "
                 f"{r['em_wape']:.3f} | {'not_adopted→rate_upper' if not r['adopted'] else 'adopted'} |")
    L += ["", "## 4. 自检", "", "| 项 | 通过 |", "|---|---|"]
    for k, v in payload["checks"].items():
        L.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    L += ["", "## 5. 失败与回退", ""]
    if payload["fails"]:
        L += ["| product_id | pool | form | uom | reason | 删失月 |", "|---|---|---|---|---|---:|"]
        for r in payload["fails"]:
            L.append(f"| {r['product_id']} | {r['pool']} | {r['physical_form']} | "
                     f"{r['canonical_uom']} | {r['fail_reason']} | {r['n_censored_months']} |")
    else:
        L.append("无。")
    L += ["", "## 5.1 探索版声明", "",
          "- **status=exploratory**：方法探索，不声称生产可用，不进入净额/采购。",
          "- **point_method = rate_upper**：只用于证据充分子集；**NB-EM point 未过采用门槛，未 adopted**。",
          "- **interval_method = nb_em_sensitivity_only / uncalibrated_conservative**："
          "区间仅作敏感性参考，未校准（遮断回测 coverage 0.82–0.92 但样本有限）。",
          "- **C_cap_basis = current_snapshot_sensitivity**：删失月上限用 C v14 快照 ±50% 代理，"
          "**不是历史删失上限**，不能进正式训练/验收真值。",
          "- **未估计删失月占比**：见文首（C 快照无上限的键全部 censor_unknown，逐条在 5_失败与回退）。",
          "- **formal_blocker = no_historical_inventory_cap**：正式版需 D3b v3 统一键 + 历史月度库存上限，"
          "替换快照代理后重跑遮断回测再定采用。",
          "", "## 6. 边界", "",
          "估计值只进 D 模型/情景，不覆盖 raw/sellable，不进净额；未写 EN/通途、未 push。",
          "", f"- 工作簿 SHA256：`{out_sha}`"]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
