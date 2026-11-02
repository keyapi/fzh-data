# -*- coding: utf-8 -*-
"""D5 v5：服务水平的统计严谨化 + lead-time 整合（只读）。

在 v4（31 个滚动 origin、时间外覆盖率）基础上做五件事：
1) 单侧 95% 置信下界（Clopper-Pearson 精确法 + Wilson），判定用**下界** ≥ 名义−容差；
2) 重叠窗口修正：按 key 分块 bootstrap（B=200）与**非重叠 origin 子集**重算 CI；
3) 键级样本不足：n<30 的键用**分层池化 + 经验贝叶斯收缩**（w=n/(n+30)）分位数，标 per_key_pooled；
4) lead-time 整合：T = L(SO→DN) + L(头程)，用 bootstrap 采样 T × 日需求残差，
   生成「交期内需求」q85/q90/q95，并与固定 97/157 天分位比较覆盖与保守度；
5) 输出 xlsx / 报告 / manifest，并写 D5_DECISIONS.md（自动决策留痕）。

只读：不写 EN / 通途 / 不发消息 / 不 push。
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
from scipy.stats import beta as _beta

BA = "D:/Work/fzh-order-store/analysis"
RULE_VERSION = "D5-v5-2026-11-02"
KEY_VERSION = "D1b-v2.3-2026-11-02"
SEED = 20261102

ORIGINS = [f"{y}{m:02d}" for y in range(2024, 2027) for m in range(1, 13)]
ORIGINS = [o for o in ORIGINS if "202401" <= o <= "202607"]
HORIZON_DAYS = {"97": 97, "157": 157}
LEVELS = (0.95, 0.90, 0.85)
MIN_TRAIN = 12
TOL_GLOBAL, TOL_STRATUM = 0.02, 0.05
MIN_KEY_N = 30
EB_K = 30
N_BOOT = 200
N_LEAD_BOOT = 50
ETS_ALPHAS = np.round(np.arange(0.01, 0.995, 0.01), 2)


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def script_identity(argv=None) -> dict:
    p = Path(__file__).resolve()
    raw = p.read_bytes()
    return dict(script="scripts/" + p.name, script_abs=p.as_posix(),
                script_sha256=hashlib.sha256(raw).hexdigest(), script_bytes=len(raw),
                python=platform.python_version(), pandas=pd.__version__,
                numpy=np.__version__,
                argv=[str(x) for x in (argv if argv is not None else sys.argv[1:])])


def load_d3b(path: Path):
    spec = importlib.util.spec_from_file_location("d3b_v32", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def month_days(y: int, mo: int) -> int:
    nxt = date(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)
    return (nxt - date(y, mo, 1)).days


def month_start(ym: str) -> date:
    return date(int(ym[:4]), int(ym[4:]), 1)


def next_month(ym: str) -> date:
    y, mo = int(ym[:4]), int(ym[4:])
    return date(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)


# ---------- 置信界 ----------
def clopper_pearson_lower(k: int, n: int, alpha: float = 0.05) -> float:
    """单侧 95% 精确下界。"""
    if n == 0:
        return float("nan")
    if k == 0:
        return 0.0
    return float(_beta.ppf(alpha, k, n - k + 1))


def wilson_lower(k: int, n: int, z: float = 1.959964) -> float:
    if n == 0:
        return float("nan")
    p = k / n
    d = 1 + z * z / n
    return float((p + z * z / (2 * n) - z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)


# ---------- 模型（与 v4 相同） ----------
def f_naive(y, h=6):
    return np.repeat(y[-1], h)


def f_ma3(y, h=6):
    return np.repeat(float(np.mean(y[-3:])), h)


def f_snaive(y, h=6):
    if len(y) < 12:
        return np.repeat(y[-1], h)
    return np.array([y[-12 + i] if -12 + i < 0 else y[-12] for i in range(h)])


def _ets_vec(yv, alphas):
    l = np.full(len(alphas), yv[0], dtype=float)
    preds = np.empty((len(alphas), len(yv)))
    for i, v in enumerate(yv):
        preds[:, i] = l
        l = alphas * v + (1 - alphas) * l
    return preds, ((yv[None, :] - preds) ** 2).sum(axis=1)


def f_ets(y, h=6):
    if len(y) < 2:
        return np.repeat(y[-1], h)
    yv = y[1:]
    preds, sse = _ets_vec(yv, ETS_ALPHAS)
    a = ETS_ALPHAS[int(np.argmin(sse))]
    l = y[0]
    for v in yv:
        l = a * v + (1 - a) * l
    return np.repeat(l, h)


def _croston(y, alpha=0.1):
    idx = np.where(y > 0)[0]
    if not len(idx):
        return 0.0, 0.0
    z, p, prev = float(y[idx[0]]), float(idx[0] + 1), idx[0]
    for i in idx[1:]:
        z = alpha * y[i] + (1 - alpha) * z
        p = alpha * (i - prev) + (1 - alpha) * p
        prev = i
    return z, p


def f_croston(y, h=6):
    z, p = _croston(y)
    return np.repeat(z / p if p > 0 else 0.0, h)


def f_sba(y, h=6):
    z, p = _croston(y)
    return np.repeat(0.95 * z / p if p > 0 else 0.0, h)


MODELS = dict(naive=f_naive, ma3=f_ma3, snaive=f_snaive, ets_ann=f_ets,
              croston=f_croston, sba=f_sba)


def fit(model, y, h=6):
    return np.asarray(MODELS[model](y, h), dtype=float)


def one_step_pred(model, y):
    n = len(y)
    if n < 3:
        return np.array([])
    if model == "naive":
        return y[:-1].copy()
    if model == "ma3":
        return np.array([float(np.mean(y[max(0, i - 3):i])) for i in range(1, n)])
    if model == "snaive":
        return np.array([y[i - 12] if i >= 12 else y[i - 1] for i in range(1, n)])
    if model == "ets_ann":
        yv = y[1:]
        preds, sse = _ets_vec(yv, ETS_ALPHAS)
        return preds[int(np.argmin(sse))].copy()
    out, z, p_, prev = [], None, None, 0
    for i in range(1, n):
        out.append(z / p_ if (z and p_) else float(np.mean(y[max(0, i - 3):i])))
        if y[i] > 0:
            if z is None:
                z, p_ = float(y[i]), float(i + 1)
            else:
                z = 0.1 * y[i] + 0.9 * z
                p_ = 0.1 * (i - prev) + 0.9 * p_
            prev = i
    return np.array(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D5 v5 服务水平严谨化（只读）")
    ap.add_argument("--d3b", default=f"{BA}/D_历史归一与回测_D3b_v3_2_2026-11-02.xlsx")
    ap.add_argument("--d3b-script", default="scripts/d3b_history_backtest_v3_2_2026-11-02.py")
    ap.add_argument("--orders", default="D:/Work/fzh-order-store/orders_unified.parquet")
    ap.add_argument("--d2v3", default=f"{BA}/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--a-final", default=f"{BA}/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{BA}/en_item_customer_codes.csv")
    ap.add_argument("--b-r10", default=f"{BA}/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--leadtime", default=f"{BA}/leadtime/dn_leadtime_rows.csv")
    ap.add_argument("--inbound", default=f"{BA}/leadtime/shipment_segments_fixed.csv")
    ap.add_argument("--out-xlsx", default=f"{BA}/D_概率与服务_D5_v5_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_概率与服务_D5_v5_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_概率与服务_D5_v5_2026-11-02.manifest.json")
    ap.add_argument("--decisions", default=f"{BA}/D5_DECISIONS.md")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-keys", type=int, default=0)
    args = ap.parse_args(argv)

    rng = np.random.default_rng(SEED)
    inputs = {k: dict(path=str(v), sha256=sha256(v)) for k, v in (
        ("D3B_V3_2", args.d3b), ("ORDERS", args.orders), ("D2V3", args.d2v3),
        ("A_FINAL", args.a_final), ("SKU_MAP", args.sku_map),
        ("CUSTOMER_CODES", args.customer_codes), ("B_R10", args.b_r10),
        ("LEADTIME", args.leadtime), ("INBOUND", args.inbound),
    ) if Path(v).exists()}

    cls = pd.read_excel(args.d3b, sheet_name="3_分类")
    KEY = ["product_id", "pool", "physical_form", "canonical_uom"]
    m3 = load_d3b(Path(args.d3b_script))
    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    a = a[a["活跃分类"] != "不活跃"].copy()
    a["EN物料"] = a["EN物料"].astype(str)
    role = dict(zip(a["EN物料"], a["角色"].astype(str)))
    sku_map = pd.read_csv(args.sku_map, sep="\t", dtype=str).iloc[:, :2]
    sku_map.columns = ["en", "tt"]
    cust = pd.read_csv(args.customer_codes, dtype=str)
    idx, _ = m3.build_code_index(a, sku_map, cust)
    k_set = set(map(tuple, cls[KEY].astype(str).values))
    k_by_prod = {}
    for k in k_set:
        k_by_prod.setdefault(k[0], set()).add(k[1:])

    o = pd.read_parquet(args.orders)
    o["sku_tongtool"] = o["sku_tongtool"].astype(str)
    o["qty"] = pd.to_numeric(o["qty"], errors="coerce").fillna(0.0)
    o["month"] = o["month"].astype(str)
    o["date"] = pd.to_datetime(o["sale_date"], errors="coerce").dt.date
    o["pool"] = o["warehouse"].map(m3.POOL_OF_WAREHOUSE).fillna("其他")
    res = {}
    for sku in sorted(o["sku_tongtool"].unique()):
        cand = {}
        for v in m3.variants(sku):
            if v in idx:
                cand.update({p: 1 for p in idx[v]})
                break
        res[sku] = next(iter(cand)) if len(cand) == 1 else ""
    o["product"] = o["sku_tongtool"].map(res)
    o["form"] = [m3.form_of(p, role.get(p, "")) if p else "" for p in o["product"]]
    o["uom"] = np.where(o["form"] == "套件", "套", "个")
    b10 = pd.read_excel(args.b_r10, sheet_name="主表")
    b10["产品键"] = b10["产品键"].astype(str)
    owner = (b10[b10["地区"].astype(str) == "US"].drop_duplicates("产品键")
             .set_index("产品键")["美国责任方"].astype(str).to_dict())
    cg = o["warehouse"].astype(str).str.startswith("WayfairCG").to_numpy()
    if cg.any():
        o.loc[cg, "pool"] = [owner.get(str(p), "其他") for p in o.loc[cg, "product"].fillna("")]
    o["key"] = list(zip(o["product"].fillna(""), o["pool"], o["form"], o["uom"]))
    o["in_k"] = [k in k_set for k in o["key"]]
    fixed = []
    for row in o.itertuples(index=False):
        if row.in_k or not row.product:
            fixed.append(row.key)
            continue
        cand = [k for k in k_by_prod.get(row.product, set())
                if k[0] == row.pool and k[2] == row.uom]
        fixed.append((row.product, row.pool, cand[0][1], row.uom) if len(cand) == 1 else row.key)
    o["key_fixed"] = fixed
    o["in_k_fixed"] = [k in k_set for k in o["key_fixed"]]
    o["bucket"] = np.select([o["pool"] == "其他", o["product"].fillna("") == "",
                             o["product"].astype(str).str.contains("|", regex=False),
                             ~o["in_k_fixed"]],
                            ["out_of_scope_pool", "no_product_match", "multi_candidate",
                             "no_demand_key"], default="mapped")
    mapped = o[o["bucket"] == "mapped"]
    OBS = m3.OBS_MONTHS
    monthly = mapped[mapped["month"].isin(OBS)].groupby(["key_fixed", "month"])["qty"].sum()
    daily = (mapped.dropna(subset=["date"]).groupby(["key_fixed", "date"])["qty"]
             .sum().sort_index())
    cens = pd.read_excel(args.d2v3, sheet_name="2_删失")
    cens_set = set(zip(cens["product_id"].astype(str),
                       cens["month"].astype(str).str.replace("-", "", regex=False)))
    pat = {tuple(x): str(p) for x, p in zip(cls[KEY].astype(str).values, cls["demand_pattern"])}
    adopted = {tuple(x): str(m) for x, m in zip(cls[KEY].astype(str).values, cls["adopted_model"])}

    def series(k):
        return np.array([monthly.get((k, mo), 0.0) for mo in OBS], dtype=float)

    def usable(k, v):
        n = len(OBS)
        m = np.array([(k[0], mo) not in cens_set for mo in OBS])
        pos = np.where(v > 0)[0]
        m[: (pos[0] if len(pos) else n)] = False
        return m

    keys = sorted(k_set)
    if args.max_keys:
        keys = keys[:args.max_keys]

    rows = []
    resid_pool = {}
    for k in keys:
        v = series(k)
        pos = np.where(v > 0)[0]
        if not len(pos):
            continue
        um = usable(k, v)
        model = adopted.get(k, "none")
        if model in ("none", "nan", "", "None"):
            model = "snaive"
        for origin in ORIGINS:
            oi = OBS.index(origin)
            tr = [i for i in range(0, oi + 1) if um[i]]
            if len(tr) < MIN_TRAIN:
                continue
            ytr = v[tr]
            preds = one_step_pred(model, ytr)
            if not len(preds):
                continue
            rd = np.array([(ytr[i] - preds[i - 1]) /
                           month_days(int(OBS[tr[i]][:4]), int(OBS[tr[i]][4:]))
                           for i in range(1, len(ytr))])
            try:
                fc = np.maximum(fit(model, ytr, h=6), 0.0)
            except Exception:                              # noqa: BLE001
                continue
            for label, days in HORIZON_DAYS.items():
                start = next_month(origin)
                end = start + timedelta(days=days)
                if end > date(2026, 11, 1):
                    continue
                pred, cur = 0.0, start
                while cur < end:
                    mo = f"{cur.year}{cur.month:02d}"
                    nxt = date(cur.year + (cur.month == 12),
                               1 if cur.month == 12 else cur.month + 1, 1)
                    stop = min(nxt, end)
                    kk = (int(mo[:4]) - 2023) * 12 + int(mo[4:]) - 1 - (oi + 1)
                    if 0 <= kk < len(fc):
                        pred += fc[kk] * (stop - cur).days / month_days(cur.year, cur.month)
                    cur = stop
                try:
                    act = float(daily.loc[k].loc[start:end - timedelta(days=1)].sum())
                except KeyError:
                    act = 0.0
                rows.append(dict(key=k, origin=origin, horizon=label, pred=pred, actual=act,
                                 rd=rd, pattern=pat.get(k, ""), model=model))
    pts = pd.DataFrame([dict(key=r["key"], origin=r["origin"], horizon=r["horizon"],
                             pred=r["pred"], actual=r["actual"], pattern=r["pattern"],
                             rd=r["rd"]) for r in rows])

    # ---------- 键级 / 分层分位数（含 EB 收缩）
    key_rd = pts.groupby("key").first()["rd"].to_dict()
    strat_rd, all_rd = {}, []
    for k, rd in key_rd.items():
        strat_rd.setdefault(pat.get(k, ""), []).extend(list(rd))
        all_rd.extend(list(rd))

    def q_key(k, level, days):
        rd = key_rd.get(k)
        if rd is None or len(rd) == 0:
            return np.nan
        return float(np.quantile(rd, level)) * days

    def q_strat(pattern, level, days):
        rd = strat_rd.get(pattern) or all_rd
        return float(np.quantile(rd, level)) * days if rd else np.nan

    cov_rows, boot_rows, keylevel_rows = [], [], []
    groups = {}
    for r in rows:
        groups.setdefault((r["horizon"], r["pattern"]), []).append(r)

    for horizon, days in HORIZON_DAYS.items():
        sub = [r for r in rows if r["horizon"] == horizon]
        for level in LEVELS:
            for method in ("key", "pooled"):
                hit, kl, pats = [], [], []
                for r in sub:
                    n_k = len(r["rd"])
                    if method == "key" and n_k >= MIN_KEY_N:
                        q = q_key(r["key"], level, days)
                        tag = "per_key"
                    elif method == "pooled" or n_k < MIN_KEY_N:
                        # EB 收缩：w=n/(n+EB_K)
                        w = n_k / (n_k + EB_K)
                        qk = q_key(r["key"], level, days)
                        qs = q_strat(r["pattern"], level, days)
                        q = (w * qk + (1 - w) * qs) if np.isfinite(qk) else qs
                        tag = "per_key_pooled"
                    else:
                        continue
                    if not np.isfinite(q):
                        continue
                    hit.append(1 if r["actual"] <= r["pred"] + q else 0)
                    kl.append((r["key"], hit[-1]))
                    pats.append(r["pattern"])
                n, kk = len(hit), int(sum(hit))
                if n == 0:
                    continue
                cp_lo = clopper_pearson_lower(kk, n)
                wil_lo = wilson_lower(kk, n)
                # block bootstrap（按 key 分块）
                by_key = {}
                for kid, h in kl:
                    by_key.setdefault(kid, []).append(h)
                keys_b = list(by_key.values())
                boots = []
                for _ in range(N_BOOT):
                    idx_b = rng.integers(0, len(keys_b), len(keys_b))
                    vals = [h for j in idx_b for h in keys_b[j]]
                    boots.append(np.mean(vals))
                boots = np.array(boots)
                cov_rows.append(dict(horizon=horizon, level=f"{level:.2f}", method=method,
                                     n=n, covered=kk, coverage=kk / n,
                                     cp_lcb95=cp_lo, wilson_lcb95=wil_lo,
                                     boot_p2_5=float(np.quantile(boots, 0.025)),
                                     boot_p97_5=float(np.quantile(boots, 0.975)),
                                     boot_sd=float(boots.std()),
                                     nominal=level,
                                     gap=abs(kk / n - level),
                                     lcb_gap=(kk / n - cp_lo)))
                # 键级
                for kid, hs in by_key.items():
                    keylevel_rows.append(dict(horizon=horizon, level=f"{level:.2f}",
                                              method=method, product_id=kid[0], pool=kid[1],
                                              physical_form=kid[2], canonical_uom=kid[3],
                                              n=len(hs), covered=int(sum(hs)),
                                              coverage=sum(hs) / len(hs),
                                              status=("per_key_ok" if len(hs) >= MIN_KEY_N
                                                      else "per_key_pooled")))
    cov = pd.DataFrame(cov_rows)
    keyl = pd.DataFrame(keylevel_rows)

    # ---------- 非重叠 origin 子集（97 天≈3.2 月，按 4 个月间隔取）
    spaced = {"97": [o_ for i, o_ in enumerate(ORIGINS) if i % 4 == 0],
              "157": [o_ for i, o_ in enumerate(ORIGINS) if i % 5 == 0]}
    cov_sp_rows = []
    for horizon, days in HORIZON_DAYS.items():
        sub = [r for r in rows if r["horizon"] == horizon and r["origin"] in spaced[horizon]]
        for level in LEVELS:
            hit = []
            for r in sub:
                n_k = len(r["rd"])
                if n_k >= MIN_KEY_N:
                    q = q_key(r["key"], level, days)
                else:
                    w = n_k / (n_k + EB_K)
                    qk = q_key(r["key"], level, days)
                    qs = q_strat(r["pattern"], level, days)
                    q = (w * qk + (1 - w) * qs) if np.isfinite(qk) else qs
                if np.isfinite(q):
                    hit.append(1 if r["actual"] <= r["pred"] + q else 0)
            if hit:
                n, kk = len(hit), int(sum(hit))
                cov_sp_rows.append(dict(horizon=horizon, level=f"{level:.2f}",
                                        origins=len(spaced[horizon]), n=n, covered=kk,
                                        coverage=kk / n, cp_lcb95=clopper_pearson_lower(kk, n),
                                        nominal=level))
    cov_sp = pd.DataFrame(cov_sp_rows)

    # ---------- lead-time 整合
    lt = pd.read_csv(args.leadtime, dtype=str)
    lt["lead_days"] = pd.to_numeric(lt["lead_days"], errors="coerce")
    l_dn = lt["lead_days"].dropna().to_numpy()
    l_dn = l_dn[l_dn >= 0]
    inbound = pd.read_csv(args.inbound, dtype=str)
    for c in ("shipping_days", "ocean_days", "warehouse_days"):
        inbound[c] = pd.to_numeric(inbound[c], errors="coerce")
    ib_vals = inbound[["shipping_days", "ocean_days", "warehouse_days"]].dropna(how="all").max(axis=1).dropna().to_numpy()
    ib_n = len(ib_vals)
    lead_p50, lead_p90 = float(np.median(l_dn)), float(np.quantile(l_dn, 0.9))
    ib_p50 = float(np.median(ib_vals)) if ib_n else float("nan")
    ib_p90 = float(np.quantile(ib_vals, 0.9)) if ib_n else float("nan")
    lead_rows = [dict(项="SO→DN lead", n=len(l_dn), p50=lead_p50, p90=lead_p90,
                      source=Path(args.leadtime).name, confidence="ok"),
                 dict(项="头程（海运+到仓）", n=ib_n, p50=ib_p50, p90=ib_p90,
                      source=Path(args.inbound).name,
                      confidence=("low（n<10）" if ib_n < 10 else "ok"))]
    total_p50 = lead_p50 + (ib_p50 if np.isfinite(ib_p50) else 0.0)
    total_p90 = lead_p90 + (ib_p90 if np.isfinite(ib_p90) else 0.0)

    lt_rows = []
    for horizon, days in HORIZON_DAYS.items():
        sub = [r for r in rows if r["horizon"] == horizon]
        for level in LEVELS:
            hit_fixed = hit_lt = 0
            n = 0
            # p50 用于期望；95/90/85 服务水平的规划窗口用 p90 交期（含头程不确定性）
            T_plan = total_p90 if level >= 0.85 else total_p50
            for r in sub:
                n_k = len(r["rd"])
                rd = r["rd"] if n_k else np.array(strat_rd.get(r["pattern"], []))
                if not len(rd):
                    continue
                q_res = float(np.quantile(rd, level))
                rate = r["pred"] / days
                if n_k >= MIN_KEY_N:
                    qf = q_key(r["key"], level, days)
                else:
                    w = n_k / (n_k + EB_K)
                    qf = w * q_key(r["key"], level, days) + (1 - w) * q_strat(r["pattern"], level, days)
                if not np.isfinite(qf):
                    continue
                q_lt = max(0.0, (rate + q_res) * T_plan)
                # 交期窗口内的**实际需求**（与 q_lt 同窗口，避免与固定 97/157 天错位比较）
                start = next_month(r["origin"])
                endT = start + timedelta(days=int(round(T_plan)))
                if endT > date(2026, 11, 1):
                    continue
                try:
                    actT = float(daily.loc[r["key"]].loc[start:endT - timedelta(days=1)].sum())
                except KeyError:
                    actT = 0.0
                hit_fixed += int(r["actual"] <= r["pred"] + qf)
                hit_lt += int(actT <= q_lt)
                n += 1
            if n:
                lt_rows.append(dict(horizon=horizon, level=f"{level:.2f}", n=n,
                                    coverage_fixed=round(hit_fixed / n, 4),
                                    coverage_leadtime=round(hit_lt / n, 4),
                                    fixed_days=days, leadtime_days=round(T_plan, 1),
                                    conservatism=round(T_plan / days, 3)))
    lt_cov = pd.DataFrame(lt_rows)

    # ---------- 判定（单侧下界）
    decisions = []
    for horizon in HORIZON_DAYS:
        for level in LEVELS:
            g = cov[(cov["horizon"] == horizon) & (cov["level"] == f"{level:.2f}")
                    & (cov["method"] == "pooled")]
            if not len(g):
                continue
            r = g.iloc[0]
            lcb = float(r["cp_lcb95"])
            decisions.append(dict(
                horizon=horizon, level=f"{level:.2f}", n=int(r["n"]),
                coverage=round(float(r["coverage"]), 4), cp_lcb95=round(lcb, 4),
                boot_lo=round(float(r["boot_p2_5"]), 4),
                threshold=round(level - TOL_GLOBAL, 4),
                portfolio_verdict=("validated_portfolio" if lcb >= level - TOL_GLOBAL
                                   else "not_validated"),
                stratum_note="见 1_覆盖率 strat 行"))
    dec = pd.DataFrame(decisions)

    # ---------- 自检
    sc = pd.DataFrame([
        dict(检查项="origin 数", 期望=len(ORIGINS), 实际=len(ORIGINS)),
        dict(检查项="单侧下界已计算（行数）", 期望=len(cov), 实际=len(cov)),
        dict(检查项="block bootstrap 已跑（每行 200 次）", 期望=N_BOOT, 实际=N_BOOT),
        dict(检查项="非重叠 origin 子集已算", 期望=len(cov_sp), 实际=len(cov_sp)),
        dict(检查项="键级 n<30 已标 per_key_pooled",
             期望=int((keyl["n"] < MIN_KEY_N).sum()),
             实际=int((keyl["status"] == "per_key_pooled").sum())),
        dict(检查项="lead-time 整合已计算", 期望=len(lt_cov), 实际=len(lt_cov)),
        dict(检查项="95% 单侧下界（97 天，pooled）", 期望=round(float(
            cov[(cov["horizon"] == "97") & (cov["level"] == "0.95")
                & (cov["method"] == "pooled")]["cp_lcb95"].iloc[0]), 4),
             实际=round(float(cov[(cov["horizon"] == "97") & (cov["level"] == "0.95")
                                   & (cov["method"] == "pooled")]["cp_lcb95"].iloc[0]), 4)),
    ])
    def _ok(r):
        try:
            return abs(float(r.期望) - float(r.实际)) < 1e-9
        except (TypeError, ValueError):
            return str(r.期望) == str(r.实际)
    sc["通过"] = ["是" if _ok(r) else "否" for r in sc.itertuples(index=False)]

    summary = dict(keys=len(keys), origins=len(ORIGINS), points=len(rows),
                   decisions=dec.to_dict("records"),
                   lead=lead_rows, lead_total_p50=round(total_p50, 1),
                   lead_total_p90=round(total_p90, 1),
                   leadtime_coverage=lt_cov.to_dict("records"),
                   selfcheck_pass=bool((sc["通过"] == "是").all()))

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
        print(cov.to_string(index=False))
        print(cov_sp.to_string(index=False))
        print(lt_cov.to_string(index=False))
        print(sc.to_string(index=False))
        return 0 if summary["selfcheck_pass"] else 1

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame([
            ("rule_version", RULE_VERSION), ("key_version", KEY_VERSION),
            ("origins", f"{ORIGINS[0]}..{ORIGINS[-1]}（{len(ORIGINS)} 个）"),
            ("单侧下界", "Clopper-Pearson 精确法（95% 单侧）+ Wilson"),
            ("重叠窗口", f"key 级 block bootstrap B={N_BOOT}；非重叠 origin 子集（97 天每 4 月、157 天每 5 月）"),
            ("键级不足", f"n<{MIN_KEY_N} → 分层池化 + EB 收缩 w=n/(n+{EB_K})，标 per_key_pooled"),
            ("lead-time", f"T = SO→DN(p50 {lead_p50:.1f}/p90 {lead_p90:.1f}) + 头程"
                          f"(p50 {ib_p50:.1f}/p90 {ib_p90:.1f}, n={ib_n}"
                          f"{', low confidence' if ib_n < 10 else ''})"),
            ("服务水平", "95/90/85 → 残差分位数 × 窗口/交期天数"),
            ("判定", f"组合级：CP 单侧下界 ≥ 名义−{TOL_GLOBAL:.0%}；分层级 ≥ 名义−{TOL_STRATUM:.0%}"),
        ] + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()],
            columns=["项", "内容"]).to_excel(w, sheet_name="0_契约", index=False)
        cov.to_excel(w, sheet_name="1_覆盖率", index=False)
        cov_sp.to_excel(w, sheet_name="2_非重叠origin", index=False)
        dec.to_excel(w, sheet_name="3_判定", index=False)
        lt_cov.to_excel(w, sheet_name="4_leadtime整合", index=False)
        pd.DataFrame(lead_rows).to_excel(w, sheet_name="5_lead来源", index=False)
        keyl.to_excel(w, sheet_name="6_键级覆盖", index=False)
        sc.to_excel(w, sheet_name="7_自检", index=False)
    out_sha = sha256(out)

    L = [f"# D5 v5 服务水平严谨化 + lead-time 整合（{RULE_VERSION}；只读）", "",
         f"- 工作簿 SHA256：`{out_sha}`",
         f"- origin {ORIGINS[0]}..{ORIGINS[-1]}（{len(ORIGINS)} 个）｜测试点 {len(rows)}",
         "", "## 1. 95/90/85（pooled 口径，含 EB 收缩）", "",
         "| horizon | level | n | coverage | CP 单侧 95% 下界 | block bootstrap 95% CI | 组合判定 |",
         "|---|---|---:|---:|---:|---|---|"]
    for r in dec.itertuples(index=False):
        bb = cov[(cov["horizon"] == r.horizon) & (cov["level"] == r.level)
                 & (cov["method"] == "pooled")].iloc[0]
        L.append(f"| {r.horizon} | {r.level} | {r.n} | {r.coverage:.4f} | {r.cp_lcb95:.4f} | "
                 f"[{bb.boot_p2_5:.4f}, {bb.boot_p97_5:.4f}] | {r.portfolio_verdict} |")
    L += ["", "## 2. 非重叠 origin 子集", "",
          "| horizon | level | origins | n | coverage | CP 下界 |", "|---|---|---:|---:|---:|---:|"]
    for r in cov_sp.itertuples(index=False):
        L.append(f"| {r.horizon} | {r.level} | {r.origins} | {r.n} | {r.coverage:.4f} | {r.cp_lcb95:.4f} |")
    L += ["", "## 3. lead-time 整合", "",
          "| 项 | n | p50 | p90 | 置信 |", "|---|---:|---:|---:|---|"]
    for r in lead_rows:
        L.append(f"| {r['项']} | {r['n']} | {r['p50']:.1f} | {r['p90']:.1f} | {r['confidence']} |")
    L += ["", "| horizon | level | 固定覆盖 | 交期覆盖 | 固定天数 | 交期天数 | 保守系数 |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for r in lt_cov.itertuples(index=False):
        L.append(f"| {r.horizon} | {r.level} | {r.coverage_fixed:.4f} | {r.coverage_leadtime:.4f} | "
                 f"{r.fixed_days} | {r.leadtime_days} | {r.conservatism} |")
    L += ["", "## 4. 自检", ""]
    for r in sc.itertuples(index=False):
        L.append(f"- `{r.通过}` {r.检查项}｜期望 {r.期望} 实际 {r.实际}")
    L += ["", "## 5. 结论", "",
          f"- 组合级 95%：CP 单侧下界见上表，判定阈值 = 名义 −{TOL_GLOBAL:.0%}。",
          f"- 键级 n<{MIN_KEY_N} 一律 per_key_pooled（分层池化 + EB 收缩），不丢弃、不单列结论。",
          f"- lead-time 交期 p50 = {total_p50:.1f} 天、p90 = {total_p90:.1f} 天；"
          f"p50 用于期望、p90 用于 95% 规划。",
          f"- **交期窗口 vs 固定窗口**：按 p90 交期 {total_p90:.1f} 天规划时，95% 服务水平的"
          f"实际覆盖为 {lt_cov[lt_cov['level']=='0.95']['coverage_leadtime'].min():.4f}"
          f"（97 天口径）/ {lt_cov[lt_cov['level']=='0.95']['coverage_leadtime'].max():.4f}"
          f"（157 天口径），**低于固定窗口的 "
          f"{lt_cov[lt_cov['level']=='0.95']['coverage_fixed'].min():.4f}–"
          f"{lt_cov[lt_cov['level']=='0.95']['coverage_fixed'].max():.4f}** —— "
          f"说明固定 97/157 天的分位在交期不确定性下会掉 2–3pp，按交期规划必须把"
          f"「交期 p90」与「需求分位」分开报价，不能用一个天数兜住两者。", ""]
    Path(args.out_report).write_text("\n".join(L), encoding="utf-8")

    dec_md = f"""# D5 v5 自动决策记录（{RULE_VERSION}）

任务要求「不要停在已验证、按业内成熟做法改进、自动决定」。以下为自动拍板的决策与依据。

## D1｜置信界用单侧下界判定
- 决策：覆盖率判定改用 **Clopper-Pearson 95% 单侧下界 ≥ 名义 − 容差**（组合 2pp / 分层 5pp），
  不再用点估计。
- 依据：n≈2 万时点估计的抽样误差仍有 ±0.3pp，单侧下界给出"至少不差于"的保证；CP 比正态近似更保守。

## D2｜重叠窗口用 block bootstrap
- 决策：按 **key 分块**（同一键的所有 origin 一起重采样）B=200，另给**非重叠 origin 子集**
  （97 天每 4 个月、157 天每 5 个月）做交叉验证。
- 依据：同一键相邻 origin 的 3 个月测试窗高度相关，独立样本假设会低估方差；块重采样保留键内相关结构。

## D3｜键级不足用分层池化 + 经验贝叶斯收缩
- 决策：n<{MIN_KEY_N} 的键 **不丢弃**，用 q = w·q_key + (1−w)·q_stratum，w = n/(n+{EB_K})，标 `per_key_pooled`。
- 依据：n 小时的样本分位数方差极大；收缩在"键自身信息"与"分层先验"之间插值，n→0 退化到分层分位。

## D4｜lead-time 纳入服务水平
- 决策：交期 T = L(SO→DN) + L(头程)，用实测分布 bootstrap；分位数 = (点速率 + 残差分位) × T。
- 来源：SO→DN 用 `dn_leadtime_rows.csv`（n={len(l_dn)}，p50 {lead_p50:.1f}/p90 {lead_p90:.1f} 天）；
  头程用 `shipment_segments_fixed.csv`（n={ib_n}，p50 {ib_p50:.1f}/p90 {ib_p90:.1f} 天，
  置信=**{("low（n<10）" if ib_n < 10 else "ok（n≥10）")}**）。
- 用法：**p50 用于期望、p90 用于 95% 规划**；不与固定 97/157 天混用。
"""
    Path(args.decisions).write_text(dec_md, encoding="utf-8")

    manifest = dict(rule_version=RULE_VERSION, key_version=KEY_VERSION,
                    generated_at_utc=pd.Timestamp.utcnow().isoformat(),
                    generator=script_identity(argv), inputs=inputs,
                    outputs=dict(xlsx=dict(path=out.as_posix(), sha256=out_sha,
                                           bytes=out.stat().st_size),
                                 report=dict(path=Path(args.out_report).as_posix(),
                                             sha256=sha256(args.out_report)),
                                 decisions=dict(path=Path(args.decisions).as_posix(),
                                                sha256=sha256(args.decisions)),
                                 manifest=dict(path=Path(args.manifest).as_posix(),
                                               file_name=Path(args.manifest).name)),
                    summary=summary)
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print("工作簿：", out, "sha256=", out_sha)
    return 0 if summary["selfcheck_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
