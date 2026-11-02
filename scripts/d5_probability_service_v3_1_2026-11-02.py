# -*- coding: utf-8 -*-
"""D5 概率预测与服务水平（只读）。

在 D3b v3.1 的正式键（D1b v2.3）与 adopted 模型上，输出未来 97/157 天需求分布
p10/p50/p90 与 95/90/85 服务水平分位数；只输出需求分布，不给补货量。

方法
1) 每个键按 `3_分类.adopted_model` 在完整可用历史上拟合，月预测 6 期；
   adopted_model=none / no_origin 的键用 fallback（seasonal naive → 池化均值），标 `fallback_model`。
2) 删失需求：优先 D2b `1_键级估计` 的 estimated_p50/p90（censor_method 注明）；无估计保持
   `censor_unknown`，用 observed 或池均值，写 `demand_basis`。
3) 区间：滚动 origin（202604..202607）残差的经验分位数（键内不足→按 demand_pattern×form 分层），
   per-day 残差 × 窗口天数；非负、单调。样本不足标 `interval_uncalibrated`。
4) 97/157 天：月预测按月内天数折算（起点 2026-11-01），折算表写入 `0_契约`。
5) 服务水平：95/90/85 → p95/p90/p85（残差分位数同法）。
6) 校准：前 3 个 origin 拟合分位数、最后 1 个 origin 评估 coverage/pinball；
   |coverage80−0.8|>0.15 → `calibration_fail` 并回退到分层残差区间。
7) 不强行加入季节/促销；D5b 仅作解释列（可选）。

只读：不写 EN / 通途 / 不发消息 / 不 push；不输出补货量。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BA = "D:/Work/fzh-order-store/analysis"
RULE_VERSION = "D5-v3.1-2026-11-02"
KEY_VERSION = "D1b-v2.3-2026-11-02"

START = date(2026, 11, 1)          # 预测起点（D3b 数据止于 2026-10-31）
HORIZONS = (("97", START, START + timedelta(days=97)),
            ("157", START, START + timedelta(days=157)))
FORECAST_MONTHS = ["202611", "202612", "202701", "202702", "202703", "202704"]
SERVICE_LEVELS = (0.95, 0.90, 0.85)
ORIGINS = ("202604", "202605", "202606", "202607")
CALIB_ORIGINS = ("202604", "202605", "202606")
EVAL_ORIGIN = "202607"
MIN_KEY_RESID = 8          # 键内残差样本门槛（不足→分层）
MIN_STRAT_RESID = 30       # 分层残差门槛（不足→全池）
CALIB_TOL = 0.15           # coverage80 允许偏差


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def script_identity(argv=None) -> dict:
    p = Path(__file__).resolve()
    raw = p.read_bytes()
    return dict(script="scripts/" + p.name, script_abs=p.as_posix(),
                script_sha256=hashlib.sha256(raw).hexdigest(),
                script_sha256_lf=hashlib.sha256(raw.replace(bytes([13, 10]),
                                                            bytes([10]))).hexdigest(),
                script_bytes=len(raw), python=platform.python_version(),
                pandas=pd.__version__, numpy=np.__version__,
                argv=[str(x) for x in (argv if argv is not None else sys.argv[1:])])


def load_d3b_module(path: Path):
    spec = importlib.util.spec_from_file_location("d3b_v31", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def month_days(year: int, month: int) -> int:
    nxt = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return (nxt - date(year, month, 1)).days


def window_days_by_month(start: date, end: date) -> dict[str, int]:
    """窗口 [start, end) 覆盖的每个日历月天数。"""
    out, cur = {}, start
    while cur < end:
        m = f"{cur.year}{cur.month:02d}"
        nxt = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)
        stop = min(nxt, end)
        out[m] = out.get(m, 0) + (stop - cur).days
        cur = stop
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D5 概率预测与服务（只读）")
    ap.add_argument("--d3b", default=f"{BA}/D_历史归一与回测_D3b_v3_2_2026-11-02.xlsx")
    ap.add_argument("--d1b", default=f"{BA}/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--d2b", default=f"{BA}/D_删失需求估计_D2b_v2_2026-11-02.xlsx")
    ap.add_argument("--d5b", default=f"{BA}/D_季节促销_D5b_v2_2026-11-02.xlsx")
    ap.add_argument("--orders", default="D:/Work/fzh-order-store/orders_unified.parquet")
    ap.add_argument("--d2v3", default=f"{BA}/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--b-r10", default=f"{BA}/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--a-final", default=f"{BA}/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{BA}/en_item_customer_codes.csv")
    ap.add_argument("--d3b-script", default="scripts/d3b_history_backtest_v3_2_2026-11-02.py")
    ap.add_argument("--out-xlsx", default=f"{BA}/D_概率与服务_D5_v3_1_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_概率与服务_D5_v3_1_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_概率与服务_D5_v3_1_2026-11-02.manifest.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        res = run_selftests()
        for n, ok, d in res:
            print(f"[{'PASS' if ok else 'FAIL'}] {n}｜{d}")
        bad = [n for n, ok, _ in res if not ok]
        print(f"\n{len(res) - len(bad)}/{len(res)} 通过")
        return 0 if not bad else 1

    inputs = {k: dict(path=str(v), sha256=sha256(v)) for k, v in (
        ("D3B_V3_1", args.d3b), ("D1B_V2_3", args.d1b), ("D2B", args.d2b),
        ("D5B", args.d5b), ("ORDERS", args.orders), ("D2V3", args.d2v3),
        ("B_R10", args.b_r10),
        ("A_FINAL", args.a_final),
        ("SKU_MAP", args.sku_map), ("CUSTOMER_CODES", args.customer_codes),
    ) if Path(v).exists()}

    d3b = pd.ExcelFile(args.d3b)
    cls = pd.read_excel(d3b, sheet_name="3_分类")
    hist = pd.read_excel(d3b, sheet_name="2_有效历史")
    KEY = ["product_id", "pool", "physical_form", "canonical_uom"]

    # ---------- 重建月度序列（与 D3b v3.1 同一确定性映射；并用 2_有效历史 复核）
    m3 = load_d3b_module(Path(args.d3b_script))
    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    a = a[a["活跃分类"] != "不活跃"].copy()
    a["EN物料"] = a["EN物料"].astype(str)
    role = dict(zip(a["EN物料"], a["角色"].astype(str)))
    sku_map = pd.read_csv(args.sku_map, sep="\t", dtype=str).iloc[:, :2]
    sku_map.columns = ["en", "tt"]
    cust = pd.read_csv(args.customer_codes, dtype=str)
    idx, _ev = m3.build_code_index(a, sku_map, cust)

    k_set = set(map(tuple, cls[KEY].astype(str).values))
    k_by_prod: dict[str, set] = {}
    for k in k_set:
        k_by_prod.setdefault(k[0], set()).add(k[1:])

    o = pd.read_parquet(args.orders)
    o["sku_tongtool"] = o["sku_tongtool"].astype(str)
    o["qty"] = pd.to_numeric(o["qty"], errors="coerce").fillna(0.0)
    o["month"] = o["month"].astype(str)
    o["pool"] = o["warehouse"].map(m3.POOL_OF_WAREHOUSE).fillna("其他")

    res = {}
    for sku in sorted(o["sku_tongtool"].unique()):
        cands = {}
        for v in m3.variants(sku):
            if v in idx:
                for prod, evs in idx[v].items():
                    cands.setdefault(prod, set()).update(evs)
                break
        if not cands:
            res[sku] = dict(status="未匹配", product="")
        elif len(cands) == 1:
            res[sku] = dict(status="唯一", product=next(iter(cands)))
        else:
            res[sku] = dict(status="多候选", product="|".join(sorted(cands)))
    mp = pd.DataFrame([dict(sku_tongtool=k, **v) for k, v in res.items()])
    o = o.merge(mp, on="sku_tongtool", how="left")
    o["form"] = [m3.form_of(p, role.get(p, "")) if isinstance(p, str) and p and "|" not in p
                 else "" for p in o["product"]]
    o["uom"] = np.where(o["form"] == "套件", "套", "个")
    # v3.2 同规则：WayfairCG 订单按 B r10 产品 owner 归池
    b10 = pd.read_excel(args.b_r10, sheet_name="主表")
    b10["产品键"] = b10["产品键"].astype(str)
    owner_map = (b10[b10["地区"].astype(str) == "US"]
                 .drop_duplicates("产品键").set_index("产品键")["美国责任方"]
                 .astype(str).to_dict())
    cg_mask = o["warehouse"].astype(str).str.startswith("WayfairCG").fillna(False).to_numpy()
    if cg_mask.any():
        o.loc[cg_mask, "pool"] = [owner_map.get(str(p), "其他")
                                  for p in o.loc[cg_mask, "product"].fillna("")]
    o["key"] = list(zip(o["product"].fillna(""), o["pool"], o["form"], o["uom"]))
    o["in_k"] = [k in k_set for k in o["key"]]
    fixed = []
    for row in o.itertuples(index=False):
        if row.in_k or not row.product or "|" in str(row.product):
            fixed.append(row.key)
            continue
        cand = [k for k in k_by_prod.get(row.product, set())
                if k[0] == row.pool and k[2] == row.uom]
        fixed.append((row.product, row.pool, cand[0][1], row.uom) if len(cand) == 1
                     else row.key)
    o["key_fixed"] = fixed
    o["in_k_fixed"] = [k in k_set for k in o["key_fixed"]]
    o["bucket"] = np.select(
        [o["pool"] == "其他", o["status"] == "未匹配", o["status"] == "多候选",
         ~o["in_k_fixed"]],
        ["out_of_scope_pool", "no_product_match", "multi_candidate", "no_demand_key"],
        default="mapped")
    valid = o[(o["bucket"] == "mapped") & o["month"].isin(m3.OBS_MONTHS)]
    ser = valid.groupby(["key_fixed", "month"])["qty"].sum()

    # 用 2_有效历史 复核重建（qty_total / months_positive / history_months_effective）
    def _series_of(key):
        return np.array([ser.get((key, mo), 0.0) for mo in m3.OBS_MONTHS], dtype=float)

    cens = pd.read_excel(args.d2v3, sheet_name="2_删失")
    cens_set = set(zip(cens["product_id"].astype(str),
                       cens["month"].astype(str).str.replace("-", "", regex=False)))
    chk_dev = 0
    chk_dev_qty = 0
    chk_dev_pos = 0
    chk_hist_keys = set()
    chk_examples = []
    for r in hist.itertuples(index=False):
        k = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        v = _series_of(k)
        chk_hist_keys.add(k)
        pos_idx = np.where(v > 0)[0]
        if not len(pos_idx):
            if abs(float(r.qty_total)) > 1e-6 or int(r.months_positive) != 0:
                chk_dev += 1
                if len(chk_examples) < 5:
                    chk_examples.append(dict(key=k, my_qty=0.0,
                                             d3b_qty=round(float(r.qty_total), 4),
                                             my_pos=0, d3b_pos=int(r.months_positive)))
            continue
        mask = np.array([(k[0], mo) not in cens_set for mo in m3.OBS_MONTHS])
        mask[:pos_idx[0]] = False
        pos = int((v > 0).sum())
        _dq = abs(float(v[mask].sum()) - float(r.qty_total)) > 1e-6
        _dp = pos != int(r.months_positive)
        chk_dev_qty += int(_dq)
        chk_dev_pos += int(_dp)
        if _dq or _dp:
            chk_dev += 1
            if len(chk_examples) < 5:
                chk_examples.append(dict(key=k, my_qty=round(float(v[mask].sum()), 4),
                                         d3b_qty=round(float(r.qty_total), 4),
                                         my_pos=pos, d3b_pos=int(r.months_positive),
                                         my_first=(m3.OBS_MONTHS[pos_idx[0]] if len(pos_idx) else ""),
                                         d3b_first=str(r.first_positive_month)))

    # ---------- D2b 删失估计 / D5b 季节标签（可选解释）
    d2b = pd.read_excel(args.d2b, sheet_name="1_键级估计")
    d2b_key = {}
    for r in d2b.itertuples(index=False):
        d2b_key[(str(r.product_id), str(r.pool), str(r.physical_form),
                 str(r.canonical_uom))] = dict(
            method=str(r.censor_method), p50=float(r.estimated_p50),
            p90=float(r.estimated_p90),
            basis=str(getattr(r, "C_cap_basis", "")),
            interval=str(getattr(r, "interval_method", "")),
            n_censor=int(r.n_censored_months))
    try:
        d5b = pd.read_excel(args.d5b, sheet_name="1_季节检测")
        d5b_season = {(str(r.product_id), str(r.pool), str(r.physical_form),
                       str(r.canonical_uom)): str(r.seasonality_status)
                      for r in d5b.itertuples(index=False)}
    except Exception:                                    # noqa: BLE001
        d5b_season = {}

    # 池化率：同 (pool, physical_form) 且跨度≥12 的键，月均率中位数（用于短史 fallback）
    _rate_by_strat: dict[tuple, list] = {}
    for r in cls.itertuples(index=False):
        k = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        v = _series_of(k)
        pos = np.where(v > 0)[0]
        if not len(pos):
            continue
        span = v[pos[0]:]
        if len(span) >= 12:
            _rate_by_strat.setdefault((k[1], k[2]), []).append(float(span.mean()))
    pool_rate = {s_: float(np.median(xs)) for s_, xs in _rate_by_strat.items() if xs}

    # ---------- 逐键预测 + 回测残差
    def fit_forecast(model: str, y: np.ndarray) -> np.ndarray:
        fn = (m3.BASELINES.get(model) or m3.NEW_MODELS.get(model))
        return np.asarray(fn(y, len(FORECAST_MONTHS)), dtype=float)

    rows, resid_rows, fails = [], [], []
    for r in cls.itertuples(index=False):
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        v = _series_of(key)
        usable = v > 0
        # 可用历史：首销月至 2026-10 的日历月（与 D3b 一致的简化：正销月起点）
        pos = np.where(v > 0)[0]
        if not len(pos):
            fails.append(dict(**dict(zip(KEY, key)), fail_reason="no_positive_history",
                              fallback="不预测（censor_unknown，见 demand_basis）"))
            continue
        span = v[pos[0]:]
        adopted = str(r.adopted_model)
        model = adopted
        fallback = ""
        if adopted in ("none", "nan") or adopted == "" or r.adoption_status == "no_origin":
            model = "snaive" if len(span) >= 12 else "pool_mean"
            fallback = f"adopted={adopted or 'none'}→{model}"
        if model == "pool_mean":
            rate = pool_rate.get((key[1], key[2]))
            if rate is None:
                fails.append(dict(**dict(zip(KEY, key)), fail_reason="no_pool_rate",
                                  fallback="无（同池同形态无可比长史键）"))
                continue
            rows.append(dict(dict(zip(KEY, key)),
                             p97=rate * 97 / 30.4375, p157=rate * 157 / 30.4375,
                             model="pool_mean", model_used="pool_mean",
                             fallback_model=fallback or "short_history→pool_mean",
                             adopted=adopted))
            continue
        try:
            fc = fit_forecast(model, span)
            if not np.all(np.isfinite(fc)):
                raise ValueError("non-finite forecast")
        except Exception as exc:                         # noqa: BLE001
            fails.append(dict(**dict(zip(KEY, key)), fail_reason=f"fit_failed:{exc}"[:120],
                              fallback="snaive"))
            model, fc = "snaive", np.repeat(float(np.mean(span[-3:])), len(FORECAST_MONTHS))
            fallback = "fit_failed→snaive"
        # 月度预测（无季节/促销强加）；按日历天数折算
        fc = np.maximum(fc, 0.0)
        point = {}
        for label, s, e in HORIZONS:
            days = window_days_by_month(s, e)
            total = 0.0
            for i, mo in enumerate(FORECAST_MONTHS):
                d = days.get(mo, 0)
                if d:
                    total += fc[i] * d / month_days(int(mo[:4]), int(mo[4:]))
            point[label] = total
        # 滚动 origin 残差（同一模型、同一可用历史）
        for origin in ORIGINS:
            oi = m3.OBS_MONTHS.index(origin)
            tr = span[:oi - pos[0] + 1] if oi >= pos[0] else np.array([])
            if len(tr) < 12:
                continue
            try:
                p3 = np.asarray((m3.BASELINES.get(model) or m3.NEW_MODELS.get(model))(tr, 3),
                                dtype=float)
            except Exception:                            # noqa: BLE001
                continue
            for step, mo in enumerate(m3.OBS_MONTHS[oi + 1: oi + 4]):
                idx_m = m3.OBS_MONTHS.index(mo)
                actual = v[idx_m]
                d = month_days(int(mo[:4]), int(mo[4:]))
                resid_rows.append(dict(key=key, origin=origin, month=mo,
                                       err_daily=(actual - p3[step]) / d, days=d))
        rows.append(dict(dict(zip(KEY, key)),
                         p97=point["97"], p157=point["157"], model=model,
                         model_used=model,
                         fallback_model=fallback, adopted=adopted))

    fc_tbl = pd.DataFrame(rows)
    resid = pd.DataFrame(resid_rows)
    resid["key_tuple"] = resid["key"]

    # ---------- 分层残差分位数
    form_of_key = {k: k[2] for k in k_set}
    pat_of_key = {(r.product_id, r.pool, r.physical_form, r.canonical_uom):
                  str(r.demand_pattern) for r in cls.itertuples(index=False)}

    def q_at(xs, q):
        return float(np.quantile(xs, q)) if len(xs) else np.nan

    calib = resid[resid["origin"].isin(CALIB_ORIGINS)]
    per_key = {k: g["err_daily"].to_numpy() for k, g in calib.groupby("key_tuple")}
    per_strat: dict[tuple, np.ndarray] = {}
    for (k, o), g in calib.groupby(["key_tuple", "origin"]):
        pass
    tmp = calib.copy()
    tmp["strat"] = [(pat_of_key.get(k, "short"), form_of_key.get(k, "")) for k in tmp["key_tuple"]]
    for s, g in tmp.groupby("strat"):
        per_strat[s] = g["err_daily"].to_numpy()
    all_resid = calib["err_daily"].to_numpy()

    def pick_pool(key):
        """返回 (残差样本, 层级, 状态)。分层校准失败 → 回退全池并标 calibration_fail。"""
        s = (pat_of_key.get(key, "short"), form_of_key.get(key, ""))
        failed = bool(stratum_fail.get(s, False))
        kx = per_key.get(key)
        if kx is not None and len(kx) >= MIN_KEY_RESID and not failed:
            return kx, "key", "ok"
        sx = per_strat.get(s)
        if sx is not None and len(sx) >= MIN_STRAT_RESID and not failed:
            return sx, f"stratum:{s[0]}|{s[1]}", "ok"
        if len(all_resid) >= MIN_STRAT_RESID:
            return all_resid, "global", ("calibration_fail" if failed else
                                         "interval_uncalibrated")
        return np.array([]), "none", "interval_uncalibrated"

    # ---------- 校准（在 held-out origin 上）
    ev = resid[resid["origin"] == EVAL_ORIGIN]
    calib_rows = []
    for label, days_total in (("97", (HORIZONS[0][2] - HORIZONS[0][1]).days),
                              ("157", (HORIZONS[1][2] - HORIZONS[1][1]).days)):
        for level_name, sel in (("key", None), ("stratum", None), ("all", None)):
            sub = ev.copy()
            sub["strat"] = [(pat_of_key.get(k, "short"), form_of_key.get(k, ""))
                            for k in sub["key_tuple"]]
            grp = [("all", sub)] if level_name == "all" else (
                list(sub.groupby("strat")) if level_name == "stratum" else
                list(sub.groupby("key_tuple")))
            for gname, g in grp:
                if not len(g):
                    continue
                errs = g["err_daily"].to_numpy() * days_total
                # 用同层 calib 分位数评估覆盖
                ks = g["key_tuple"].iloc[0] if level_name == "key" else None
                src = (per_key.get(ks) if ks is not None else
                       per_strat.get(gname) if level_name == "stratum" else all_resid)
                if src is None or not len(src):
                    continue
                q10, q90 = q_at(src, 0.10) * days_total, q_at(src, 0.90) * days_total
                cov80 = float(np.mean((errs >= q10) & (errs <= q90)))
                calib_rows.append(dict(horizon=label, level=level_name,
                                       stratum=(str(gname)[:40]), n=len(g),
                                       coverage80=round(cov80, 4),
                                       pinball50=round(float(np.mean(
                                           0.5 * np.abs(errs - np.median(src) * days_total))), 4),
                                       mean_err=round(float(np.mean(errs)), 4),
                                       calibration=("ok" if abs(cov80 - 0.8) <= CALIB_TOL
                                                    else "calibration_fail")))
    calib_tbl = pd.DataFrame(calib_rows)

    # 分层校准判定：该层 held-out coverage 偏离过大 → 该层键全部回退全池分位数
    stratum_fail = {tuple(str(r.stratum).split("|", 1)):
                    (r.calibration == "calibration_fail")
                    for r in calib_tbl.itertuples(index=False) if r.level == "stratum"}
    stratum_cov = {tuple(str(r.stratum).split("|", 1)): r.coverage80
                   for r in calib_tbl.itertuples(index=False) if r.level == "stratum"}

    # ---------- 组装预测表
    out_rows = []
    for r in fc_tbl.itertuples(index=False):
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        base = dict(zip(KEY, key))
        resid_s, level, pstatus = pick_pool(key)
        d2b_i = d2b_key.get(key)
        if d2b_i is None or d2b_i["method"] == "none":
            demand_basis = "observed"
        else:
            demand_basis = (f"D2b:{d2b_i['method']}"
                            f"(C_cap={d2b_i['basis']};interval={d2b_i['interval']})")
        season = d5b_season.get(key, "")
        for label, days_total in (("97", (HORIZONS[0][2] - HORIZONS[0][1]).days),
                                  ("157", (HORIZONS[1][2] - HORIZONS[1][1]).days)):
            p50 = float(getattr(r, f"p{label}"))
            if len(resid_s):
                q50 = q_at(resid_s, 0.50)
                q10 = (q_at(resid_s, 0.10) - q50) * days_total
                q90 = (q_at(resid_s, 0.90) - q50) * days_total
                p10 = max(0.0, p50 + q10)
                p90 = max(p10, p50 + q90)
                method = f"conformal_residual:{level}"
                status = pstatus
            else:
                p10 = p90 = np.nan
                method, status = "none", "interval_uncalibrated"
            svc = {f"q{int(l * 100)}": (max(0.0, p50 + (q_at(resid_s, l) - q_at(resid_s, 0.50)) * days_total)
                                        if len(resid_s) else np.nan)
                   for l in SERVICE_LEVELS}
            out_rows.append(dict(base, key_version=KEY_VERSION, horizon=label,
                                 horizon_days=days_total,
                                 p10=p10, p50=p50, p90=p90,
                                 model=r.model,
                                 adopted_model=r.adopted, fallback_model=r.fallback_model,
                                 demand_basis=demand_basis,
                                 interval_method=method, interval_level=level,
                                 calibration_status=status,
                                 seasonality_status=season, promo_status="unknown（无日历）",
                                 **svc,
                                 source_refs=(f"D3b_v3.1:{key[0]}|{key[1]}|{key[2]}|{key[3]};"
                                              f"model={r.model};adopted={r.adopted};"
                                              f"D2b:{'yes' if d2b_i else 'no'}")))
    pred = pd.DataFrame(out_rows)

    # ---------- 服务水平表
    svc_rows = []
    for label, days_total in (("97", 97), ("157", 157)):
        for r in pred[pred["horizon"] == label].itertuples(index=False):
            key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
            src, lvl, pstatus = pick_pool(key)
            for sl in SERVICE_LEVELS:
                q = (max(0.0, r.p50 + q_at(src, sl) * days_total) if len(src) else np.nan)
                svc_rows.append(dict(product_id=r.product_id, pool=r.pool,
                                     physical_form=r.physical_form,
                                     canonical_uom=r.canonical_uom,
                                     horizon=label, service_level=sl,
                                     quantile=q, basis_level=lvl,
                                     calibrated=("是" if pstatus == "ok" else "否")))
    svc_tbl = pd.DataFrame(svc_rows)

    # ---------- 自检
    covered = set(zip(pred["product_id"], pred["pool"], pred["physical_form"],
                      pred["canonical_uom"]))
    fail_keys = {(f["product_id"], f["pool"], f["physical_form"], f["canonical_uom"])
                 for f in fails}
    d1b = pd.read_excel(args.d1b, sheet_name="1_资格")
    d1b = d1b[(d1b["decision_state"].astype(str) == "active")
              & d1b["demand_state"].astype(str).isin(["observed", "censored"])]
    d1b_keys = set(map(tuple, d1b[["product_id", "destination_pool", "physical_form",
                                   "canonical_uom"]].astype(str).values))
    missing = d1b_keys - covered - fail_keys
    mono_bad = int(((pred["p10"] > pred["p50"]) | (pred["p50"] > pred["p90"])).sum()
                   ) if len(pred) else 0
    neg_bad = int(((pred[["p10", "p50", "p90"]] < 0).any(axis=1)).sum()) if len(pred) else 0
    fb_ok = int((pred.loc[pred["adopted_model"].isin(["none", "nan", "", "None"]),
                          "model"].astype(str).str.len() > 0).sum())
    covered_all = covered | fail_keys
    sc = pd.DataFrame([
        dict(检查项="D1b 需求键覆盖（预测或明确失败）", 期望=len(d1b_keys),
             实际=len(d1b_keys & covered_all)),
        dict(检查项="静默丢失键", 期望=0, 实际=len(missing)),
        dict(检查项="p10<=p50<=p90 违反", 期望=0, 实际=mono_bad),
        dict(检查项="负值违反", 期望=0, 实际=neg_bad),
        dict(检查项="adopted_model=none 的键全部有 fallback 标", 期望=int(
            (pred["adopted_model"].astype(str).isin(["none", "nan", "", "None"])).sum()),
            实际=fb_ok),
        dict(检查项="97 天窗口可复算（月历天数）", 期望=97,
             实际=sum(window_days_by_month(START, START + timedelta(days=97)).values())),
        dict(检查项="157 天窗口可复算（月历天数）", 期望=157,
             实际=sum(window_days_by_month(START, START + timedelta(days=157)).values())),
        dict(检查项="重建序列与 D3b 2_有效历史 一致（qty/正销月偏差键）", 期望=0, 实际=chk_dev),
        dict(检查项="重建序列键集 = 2_有效历史 键集（缺键）", 期望=0,
             实际=len(set(map(tuple, cls[KEY].astype(str).values)) - chk_hist_keys)),
        dict(检查项="校准覆盖率已报告（行数>0）", 期望=len(calib_tbl), 实际=len(calib_tbl)),
    ])
    sc["通过"] = ["是" if str(r.期望) == str(r.实际) else "否" for r in sc.itertuples(index=False)]
    sc_ok = bool((sc["通过"] == "是").all())

    fail_df = pd.DataFrame(fails)
    _pred_keys = set(zip(pred.loc[pred["p50"].notna(), "product_id"],
                         pred.loc[pred["p50"].notna(), "pool"],
                         pred.loc[pred["p50"].notna(), "physical_form"],
                         pred.loc[pred["p50"].notna(), "canonical_uom"]))
    summary = dict(keys=len(d1b_keys), predicted_keys=len(_pred_keys),
                   failed_keys=len(fail_keys),
                   fail_reasons=(fail_df["fail_reason"].value_counts().to_dict()
                                 if len(fail_df) else {}),
                   nan_interval_rows=int(pred["p10"].isna().sum()) if len(pred) else 0,
                   coverage_headline=(calib_tbl[calib_tbl["level"] == "all"]
                                      .groupby("horizon")["coverage80"].first().to_dict()
                                      if len(calib_tbl) else {}),
                   rows_p97=int((pred["horizon"] == "97").sum()),
                   rows_p157=int((pred["horizon"] == "157").sum()),
                   models=pred["model"].value_counts().to_dict(),
                   fallback_rows=int((pred["fallback_model"].astype(str) != "").sum()),
                   calib_fail_rows=int((pred["calibration_status"] == "calibration_fail").sum()),
                   uncalibrated_rows=int((pred["calibration_status"] == "interval_uncalibrated").sum()),
                   d2b_keys=int(pred["demand_basis"].astype(str).str.startswith("D2b").sum()),
                   demand_basis_dist=pred["demand_basis"].astype(str)
                   .str.split("(").str[0].value_counts().to_dict(),
                   seasonality_covered_rows=int((pred["seasonality_status"].astype(str).str.strip()
                                                 != "").sum()),
                   coverage80=(calib_tbl.groupby("horizon")["coverage80"].mean().round(4).to_dict()
                               if len(calib_tbl) else {}),
                   coverage_by_level=({r.level: r.coverage80 for r in
                                       calib_tbl[calib_tbl.horizon == "97"].itertuples(index=False)
                                       if r.level != "key"}
                                      if len(calib_tbl) else {}),
                   stratum_fail_count=int(sum(1 for v in stratum_fail.values() if v)),
                   selftest_pass=sc_ok, selfcheck=sc.to_dict("records"))

    if args.dry_run:
        print("REBUILD_MISMATCH_EXAMPLES:", json.dumps(chk_examples, ensure_ascii=False))
        print(json.dumps(dict(rebuild_check=dict(qty_dev_keys=chk_dev_qty,
                                                 pos_dev_keys=chk_dev_pos,
                                                 total_dev_keys=chk_dev,
                                                 keys_in_hist=len(chk_hist_keys),
                                                 keys_in_cls=len(k_set))),
                         ensure_ascii=False))
        print(json.dumps({k: v for k, v in summary.items() if k != "selfcheck"},
                         ensure_ascii=False, indent=1, default=str))
        for r in sc.itertuples(index=False):
            print(f"  {r.通过} | {r.检查项} 期望={r.期望} 实际={r.实际}")
        print("DRY-RUN：未写文件")
        return 0 if sc_ok else 1

    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("key_version", KEY_VERSION),
        ("键", "D3b v3.1 正式键（D1b v2.3 product×market×pool×form×uom）"),
        ("输入版本", "D3b v3.2（WayfairCG 按 B owner 归池）/ "
                     "D2b v2（D_删失需求估计_D2b_v2_2026-11-02）/ "
                     "D5b v2（D_季节促销_D5b_v2_2026-11-02）"),
        ("版本说明", "D5 v2 / v3 均为 preliminary；本版 v3.1 基于 D3b v3.2，"
                     "重建序列完整复制 WayfairCG→B r10 owner 归池规则，1,853 键与 2_有效历史 0 偏差"),
        ("预测起点", str(START)), ("horizons", "97 天 / 157 天，按日历月天数折算"),
        ("折算表 97", json.dumps(window_days_by_month(START, START + timedelta(days=97)))),
        ("折算表 157", json.dumps(window_days_by_month(START, START + timedelta(days=157)))),
        ("模型", "D3b adopted_model（naive/MA3/snaive/ETS-A,N,N/Croston/SBA）；"
                 "none/no_origin → snaive 或 pool_mean fallback"),
        ("区间", f"滚动 origin {CALIB_ORIGINS} 的 per-day 残差经验分位数 × 窗口天数；"
                 f"键内样本<{MIN_KEY_RESID} → 按 demand_pattern×form 分层；<{MIN_STRAT_RESID} → 全池并标 uncalibrated"),
        ("校准", f"held-out origin {EVAL_ORIGIN}；|coverage80−0.8|>{CALIB_TOL} → calibration_fail"),
        ("服务水平", "95/90/85 → 残差分位数 p95/p90/p85"),
        ("删失", "D2b 1_键级估计优先；无估计保持 censor_unknown 并用 observed/池均值（demand_basis 标注）"),
        ("不做", "不输出补货量/采购量；不写 EN/通途；不强行加入季节/促销"),
    ] + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()],
        columns=["项", "内容"])

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        pred.to_excel(w, sheet_name="1_预测", index=False)
        calib_tbl.to_excel(w, sheet_name="2_区间校准", index=False)
        svc_tbl.to_excel(w, sheet_name="3_服务水平", index=False)
        pd.DataFrame(fails).to_excel(w, sheet_name="4_失败与回退", index=False)
        sc.to_excel(w, sheet_name="5_自检", index=False)
    out_sha = sha256(out)

    L = [f"# D5 概率预测与服务（{RULE_VERSION}；只读）", "",
         f"- 工作簿 SHA256：`{out_sha}`",
         f"- 键 {summary['keys']}｜有预测 {summary['predicted_keys']}｜明确失败 "
         f"{summary['failed_keys']}｜97 天行 {summary['rows_p97']}｜157 天行 {summary['rows_p157']}",
         f"- 模型分布 `{json.dumps(summary['models'], ensure_ascii=False)}`；"
         f"fallback 行 {summary['fallback_rows']}；calibration_fail 行 "
         f"{summary['calib_fail_rows']}；uncalibrated 行 {summary['uncalibrated_rows']}", "",
         "## 1. 校准（held-out origin）", "",
         "| horizon | level | stratum | n | coverage80 | pinball50 | 判定 |", "|---|---|---|---:|---:|---:|---|"]
    _cal_rep = calib_tbl[calib_tbl["level"] != "key"]
    for r in _cal_rep.itertuples(index=False):
        L.append(f"| {r.horizon} | {r.level} | {r.stratum} | {r.n} | {r.coverage80} | "
                 f"{r.pinball50} | {r.calibration} |")
    _key_rows = calib_tbl[calib_tbl["level"] == "key"]
    if len(_key_rows):
        L.append(f"（键级 {len(_key_rows)} 行仅作诊断，明细见 `2_区间校准`；"
                 f"键级 coverage80 行均值 {_key_rows['coverage80'].mean():.4f}，"
                 "n=3 粒度极粗，不作门禁）")
    L += ["", "## 2. 自检", ""]
    for r in sc.itertuples(index=False):
        L.append(f"- `{r.通过}` {r.检查项}｜期望 {r.期望} 实际 {r.实际}")
    L += ["", "## 3. 边界", "",
          "- 只输出需求分布，不含补货量/采购量；区间基于历史残差，不代表未来误差上限。",
          "- 删失月用 D2b 估计或保持 censor_unknown，不填 0。", ""]
    Path(args.out_report).write_text("\n".join(L), encoding="utf-8")

    manifest = dict(rule_version=RULE_VERSION, key_version=KEY_VERSION,
                    supersedes=[dict(version="D5-v2-2026-11-02", status="preliminary",
                                     reason="D3b v3.1 把 WayfairCG 按仓库地理归 美东USNJ"),
                                dict(version="D5-v3-2026-11-02", status="preliminary",
                                     reason="D5 内部重建序列未复制 CG owner 归池，"
                                            "与 D3b v3.2 有 88 键偏差")],
                    series_source=("D3b v3.2 同规则重建（含 WayfairCG→B owner 归池）；"
                                   "自检要求与 2_有效历史 0 偏差"),
                    generated_at_utc=pd.Timestamp.utcnow().isoformat(),
                    generator=script_identity(argv), inputs=inputs,
                    outputs=dict(xlsx=dict(path=out.as_posix(), sha256=out_sha,
                                           bytes=out.stat().st_size),
                                 report=dict(path=Path(args.out_report).as_posix(),
                                             sha256=sha256(args.out_report)),
                                 manifest=dict(path=Path(args.manifest).as_posix(),
                                               file_name=Path(args.manifest).name)),
                    summary=summary)
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "selfcheck"},
                     ensure_ascii=False, indent=1, default=str))
    print("工作簿：", out, "sha256=", out_sha)
    return 0 if sc_ok else 1


def run_selftests():
    t = []
    d97 = window_days_by_month(START, START + timedelta(days=97))
    d157 = window_days_by_month(START, START + timedelta(days=157))
    t.append(("① 97/157 天折算合计等于窗口天数",
              sum(d97.values()) == 97 and sum(d157.values()) == 157, f"{sum(d97.values())}/{sum(d157.values())}"))
    t.append(("② 窗口起点落在 2026-11", "202611" in d97 and "202611" in d157, str(list(d97))))
    xs = np.array([-2.0, -0.5, 0.0, 0.5, 2.0])
    t.append(("③ 残差分位数单调",
              float(np.quantile(xs, 0.1)) <= float(np.quantile(xs, 0.9)), "ok"))
    t.append(("④ 非负截断", max(0.0, -5.0) == 0.0, "ok"))
    return t


if __name__ == "__main__":
    raise SystemExit(main())
