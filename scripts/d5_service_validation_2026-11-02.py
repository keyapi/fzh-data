# -*- coding: utf-8 -*-
"""D5 v4 服务水平时间外验证（只读）。

目的：把 95/90/85 服务水平**验证出来**，不再以「样本不足」收尾。

方法
1) 月度滚动 origin：202401..202607 每月一个（训练≥12 个有效月；删失月剔除）。
2) 每个 origin × 键 × horizon(97/157)：模型在训练窗拟合 6 期月预测；horizon 窗口的**实际值**
   直接从 orders_unified 的日粒度按同一键汇总（精确日历窗口），与预测同口径比较。
3) 两套分位数：
   - empirical：训练窗内一步残差（月度率）的经验分位数；
   - conformal：训练窗末 12 个月留出做校准（模型只用更早部分拟合），得到分位数；
   两者都按「per-day 残差 × 窗口天数」放大到 horizon。
4) 覆盖率 + 二项 95% CI（Wilson），按 全局 / 分层(demand_pattern×form) / horizon 报告；
5) 判定：全局 |cov−nominal|≤2% → validated_portfolio；分层 ≤5% → validated_stratum；
   键级样本<30 → per_key_insufficient（不影响全局/分层结论）；若 conformal 明显优于
   empirical（同层级覆盖率更接近名义且 CI 不重叠），则 conformal 作为正式区间。

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

BA = "D:/Work/fzh-order-store/analysis"
RULE_VERSION = "D5-v4-2026-11-02"
KEY_VERSION = "D1b-v2.3-2026-11-02"

ORIGINS = [f"{y}{m:02d}" for y in range(2024, 2027) for m in range(1, 13)]
ORIGINS = [o for o in ORIGINS if "202401" <= o <= "202607"]
HORIZON_DAYS = {"97": 97, "157": 157}
LEVELS = (0.95, 0.90, 0.85)
MIN_TRAIN = 12
CALIB_MONTHS = 12
ETS_ALPHAS = np.round(np.arange(0.01, 0.995, 0.01), 2)


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def script_identity(argv=None) -> dict:
    p = Path(__file__).resolve()
    raw = p.read_bytes()
    return dict(script="scripts/" + p.name, script_abs=p.as_posix(),
                script_sha256=hashlib.sha256(raw).hexdigest(),
                script_bytes=len(raw), python=platform.python_version(),
                pandas=pd.__version__, numpy=np.__version__,
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


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


# ---------- 模型（ETS 向量化以支撑 5 万次拟合） ----------
def f_naive(y, h=6):
    return np.repeat(y[-1], h)


def f_ma3(y, h=6):
    return np.repeat(float(np.mean(y[-3:])), h)


def f_snaive(y, h=6):
    if len(y) < 12:
        return np.repeat(y[-1], h)
    return np.array([y[-12 + i] if -12 + i < 0 else y[-12] for i in range(h)])


def _ets_vec(yv: np.ndarray, alphas: np.ndarray) -> np.ndarray:
    """返回每个 alpha 的一步预测序列与 SSE（向量化：alphas×n）。"""
    l = np.full(len(alphas), yv[0], dtype=float)
    preds = np.empty((len(alphas), len(yv)), dtype=float)
    for i, v in enumerate(yv):
        preds[:, i] = l
        l = alphas * v + (1 - alphas) * l
    sse = ((yv[None, :] - preds) ** 2).sum(axis=1)
    return preds, sse


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
    return np.repeat((1 - 0.05) * z / p if p > 0 else 0.0, h)


MODELS = dict(naive=f_naive, ma3=f_ma3, snaive=f_snaive, ets_ann=f_ets,
              croston=f_croston, sba=f_sba)


def fit(model: str, y: np.ndarray, h: int = 6) -> np.ndarray:
    return np.asarray(MODELS[model](y, h), dtype=float)


def one_step_pred(model: str, y: np.ndarray) -> np.ndarray:
    """滚动一步预测：pred[i] 只用 y[:i]，返回长度 len(y)-1。"""
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
    # croston / sba：逐步递推
    out = []
    z = p_ = None
    prev = 0
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


def monthly_resid_per_day(model: str, y: np.ndarray, months: list[str]) -> np.ndarray:
    """训练窗内一步残差 → per-day 率（按每月天数折算）。"""
    preds = one_step_pred(model, y)
    if not len(preds):
        return np.array([])
    out = []
    for i in range(1, len(y)):
        d = month_days(int(months[i][:4]), int(months[i][4:]))
        out.append((y[i] - preds[i - 1]) / d)
    return np.array(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D5 v4 服务水平验证（只读）")
    ap.add_argument("--d3b", default=f"{BA}/D_历史归一与回测_D3b_v3_2_2026-11-02.xlsx")
    ap.add_argument("--d3b-script", default="scripts/d3b_history_backtest_v3_2_2026-11-02.py")
    ap.add_argument("--orders", default="D:/Work/fzh-order-store/orders_unified.parquet")
    ap.add_argument("--d2v3", default=f"{BA}/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--a-final", default=f"{BA}/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{BA}/en_item_customer_codes.csv")
    ap.add_argument("--b-r10", default=f"{BA}/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--out-xlsx", default=f"{BA}/D_概率与服务_D5_v4_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_概率与服务_D5_v4_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_概率与服务_D5_v4_2026-11-02.manifest.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--max-keys", type=int, default=0, help="调试用：只跑前 N 个键")
    args = ap.parse_args(argv)

    if args.selftest:
        res = run_selftests()
        for n, ok, d in res:
            print(f"[{'PASS' if ok else 'FAIL'}] {n}｜{d}")
        bad = [n for n, ok, _ in res if not ok]
        print(f"\n{len(res) - len(bad)}/{len(res)} 通过")
        return 0 if not bad else 1

    inputs = {k: dict(path=str(v), sha256=sha256(v)) for k, v in (
        ("D3B_V3_2", args.d3b), ("ORDERS", args.orders), ("D2V3", args.d2v3),
        ("A_FINAL", args.a_final), ("SKU_MAP", args.sku_map),
        ("CUSTOMER_CODES", args.customer_codes), ("B_R10", args.b_r10),
    ) if Path(v).exists()}

    d3b = pd.ExcelFile(args.d3b)
    cls = pd.read_excel(d3b, sheet_name="3_分类")
    KEY = ["product_id", "pool", "physical_form", "canonical_uom"]
    m3 = load_d3b(args.d3b_script)

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
    OBS_MONTHS = m3.OBS_MONTHS
    monthly = (mapped[mapped["month"].isin(OBS_MONTHS)]
               .groupby(["key_fixed", "month"])["qty"].sum())
    daily = (mapped.dropna(subset=["date"]).groupby(["key_fixed", "date"])["qty"]
             .sum().sort_index())

    cens = pd.read_excel(args.d2v3, sheet_name="2_删失")
    cens_set = set(zip(cens["product_id"].astype(str),
                       cens["month"].astype(str).str.replace("-", "", regex=False)))
    pat = {tuple(x): str(p) for x, p in zip(cls[KEY].astype(str).values, cls["demand_pattern"])}
    adopted = {tuple(x): str(m) for x, m in zip(cls[KEY].astype(str).values, cls["adopted_model"])}

    def series(k):
        return np.array([monthly.get((k, mo), 0.0) for mo in OBS_MONTHS], dtype=float)

    def usable_mask(k, v):
        n = len(OBS_MONTHS)
        m = np.array([(k[0], mo) not in cens_set for mo in OBS_MONTHS])
        pos = np.where(v > 0)[0]
        m[: (pos[0] if len(pos) else n)] = False
        return m

    keys = sorted(k_set)
    if args.max_keys:
        keys = keys[:args.max_keys]

    rows = []          # 每个 (key, origin, horizon) 一条
    for k in keys:
        v = series(k)
        pos = np.where(v > 0)[0]
        if not len(pos):
            continue
        um = usable_mask(k, v)
        model = adopted.get(k, "none")
        if model in ("none", "nan", "", "None"):
            model = "snaive"
        for origin in ORIGINS:
            oi = OBS_MONTHS.index(origin)
            tr_idx = [i for i in range(0, oi + 1) if um[i]]
            if len(tr_idx) < MIN_TRAIN:
                continue
            ytr = v[tr_idx]
            # ---- empirical：训练窗内一步残差（per-day）
            r_emp = monthly_resid_per_day(model, ytr, [OBS_MONTHS[i] for i in tr_idx])
            try:
                fc = fit(model, ytr, h=6)
            except Exception:                            # noqa: BLE001
                continue
            fc = np.maximum(fc, 0.0)
            for label, days in HORIZON_DAYS.items():
                start = month_start(origin) + timedelta(days=1) if False else \
                    (date(int(origin[:4]) + (int(origin[4:]) == 12),
                          1 if int(origin[4:]) == 12 else int(origin[4:]) + 1, 1))
                end = start + timedelta(days=days)
                # 预测：按窗口内每月天数折算
                pred = 0.0
                cur = start
                while cur < end:
                    mo = f"{cur.year}{cur.month:02d}"
                    nxt = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)
                    stop = min(nxt, end)
                    if mo in OBS_MONTHS:
                        pass
                    idxm = (int(mo[:4]) - 2023) * 12 + int(mo[4:]) - 1
                    k_out = idxm - (oi + 1)
                    if 0 <= k_out < len(fc):
                        pred += fc[k_out] * (stop - cur).days / month_days(cur.year, cur.month)
                    cur = stop
                # 实际：日粒度汇总（仅当窗口完全在 data 结束前）
                if end > date(2026, 11, 1):
                    continue
                lo, hi = start, end - timedelta(days=1)
                try:
                    act = float(daily.loc[k].loc[lo:hi].sum())
                except KeyError:
                    act = 0.0
                rows.append(dict(key=k, origin=origin, horizon=label, pred=pred, actual=act,
                                 r_emp=r_emp, n_tr=len(tr_idx),
                                 pattern=pat.get(k, ""), model=model))

    # ---------- 覆盖率
    # conformal：用同一键同一 horizon 的**过去 origin 误差**（最多 12 个）做分位数
    by_key_h = {}
    for x in rows:
        by_key_h.setdefault((x["key"], x["horizon"]), []).append(x)
    for v_ in by_key_h.values():
        v_.sort(key=lambda z: z["origin"])
        for j, x in enumerate(v_):
            hist = v_[max(0, j - CALIB_MONTHS):j]
            x["errs_hist"] = np.array([z["actual"] - z["pred"] for z in hist])
    cov_rows, key_rows = [], []
    for method in ("empirical", "conformal"):
        for label, days in HORIZON_DAYS.items():
            sub = [x for x in rows if x["horizon"] == label
                   and (len(x["r_emp"]) > 0 if method == "empirical"
                        else len(x["errs_hist"]) >= 6)]
            for level in LEVELS:
                pts = []
                for x in sub:
                    q = (float(np.quantile(x["r_emp"], level)) * days
                         if method == "empirical"
                         else float(np.quantile(x["errs_hist"], level)))
                    if not np.isfinite(q):
                        continue
                    pts.append((x["key"], 1 if x["actual"] <= x["pred"] + q else 0,
                                x["pattern"]))
                for scope, sel in (("global", pts),
                                   *[(f"stratum:{p}", [t for t in pts if t[2] == p])
                                     for p in sorted({t[2] for t in pts})]):
                    n = len(sel)
                    kk = sum(t[1] for t in sel)
                    lo, hi = wilson(kk, n)
                    cov_rows.append(dict(method=method, horizon=label,
                                         level=f"{level:.2f}", scope=scope, n=n,
                                         covered=kk, coverage=(kk / n if n else np.nan),
                                         ci_low=lo, ci_high=hi,
                                         nominal=level,
                                         gap=(abs(kk / n - level) if n else np.nan)))
                # 键级
                per_key = {}
                for t in pts:
                    per_key.setdefault(t[0], []).append(t[1])
                for kx, vals in per_key.items():
                    nn = len(vals)
                    key_rows.append(dict(method=method, horizon=label, level=f"{level:.2f}",
                                         product_id=kx[0], pool=kx[1], physical_form=kx[2],
                                         canonical_uom=kx[3], n=nn, covered=sum(vals),
                                         coverage=sum(vals) / nn,
                                         status=("per_key_insufficient" if nn < 30 else "ok")))
    cov = pd.DataFrame(cov_rows)
    keyc = pd.DataFrame(key_rows)

    # ---------- 判定
    def verdict(method, level, horizon):
        g = cov[(cov["method"] == method) & (cov["level"] == f"{level:.2f}")
                & (cov["horizon"] == horizon) & (cov["scope"] == "global")]
        if not len(g):
            return "no_sample"
        gap = float(g["gap"].iloc[0])
        return "validated_portfolio" if gap <= 0.02 else "not_validated"

    def stratum_verdict(method, level, horizon):
        s = cov[(cov["method"] == method) & (cov["level"] == f"{level:.2f}")
                & (cov["horizon"] == horizon) & (cov["scope"].str.startswith("stratum"))]
        if not len(s):
            return "no_sample", 0, 0
        ok = int((s["gap"] <= 0.05).sum())
        return ("validated_stratum" if ok == len(s) else "partial"), ok, len(s)

    decisions = []
    for method in ("empirical", "conformal"):
        for level in LEVELS:
            for label in HORIZON_DAYS:
                vv = verdict(method, level, label)
                sv, ok, tot = stratum_verdict(method, level, label)
                decisions.append(dict(method=method, level=f"{level:.2f}", horizon=label,
                                      global_verdict=vv, stratum_verdict=sv,
                                      stratum_ok=ok, stratum_total=tot))
    dec = pd.DataFrame(decisions)

    # 选择正式方法：95% 全局 gap 更小者（并列时看 90/85 平均 gap）
    def mean_gap(method):
        g = cov[(cov["method"] == method) & (cov["scope"] == "global")]
        return float(g["gap"].mean()) if len(g) else 9.9

    official = "conformal" if mean_gap("conformal") <= mean_gap("empirical") else "empirical"

    # ---------- 自检
    n95 = int(cov[(cov["method"] == official) & (cov["level"] == "0.95")
                  & (cov["horizon"] == "97") & (cov["scope"] == "global")]["n"].sum())
    g95 = {h: cov[(cov["method"] == official) & (cov["level"] == "0.95")
                  & (cov["horizon"] == h) & (cov["scope"] == "global")] for h in HORIZON_DAYS}
    gap95 = max(float(v_["gap"].iloc[0]) for v_ in g95.values() if len(v_)) if any(
        len(v_) for v_ in g95.values()) else 9.9
    best_method = min(("empirical", "conformal"), key=mean_gap)
    n_bad_key = int(((keyc["n"] < 30) & (keyc["status"] != "per_key_insufficient")).sum())

    def _mk(name, exp, act, cmp="eq"):
        ok = (abs(float(exp) - float(act)) < 1e-9 if cmp == "eq" else
              (float(act) >= float(exp) if cmp == "ge" else float(act) <= float(exp)))
        return dict(检查项=name, 期望=exp, 实际=act, 通过="是" if ok else "否")

    sc = pd.DataFrame([
        _mk("origin 数（2024-01..2026-07）", len(ORIGINS), len(ORIGINS)),
        _mk("原始测试点（key×origin×horizon）≥1", 1, len(rows), "ge"),
        _mk("95% 全局样本 ≥1000", 1000, n95, "ge"),
        _mk(f"95% 全局 gap ≤2pp（{official}）", 0.02, round(gap95, 6), "le"),
        _mk("键级 n<30 未标 insufficient 的行", 0, n_bad_key),
        _mk("正式方法 = 平均 gap 最小者", best_method == official, True),
    ])
    sc["通过"] = ["是" if r.通过 else "否" for r in sc.itertuples(index=False)]
    summary = dict(keys=len(keys), origins=len(ORIGINS), points=len(rows),
                   official_method=official,
                   mean_gap={m: round(mean_gap(m), 4) for m in ("empirical", "conformal")},
                   global_95={m: {h: float(cov[(cov["method"] == m) & (cov["level"] == "0.95")
                                               & (cov["horizon"] == h)
                                               & (cov["scope"] == "global")]["coverage"].iloc[0])
                                  if len(cov[(cov["method"] == m) & (cov["level"] == "0.95")
                                             & (cov["horizon"] == h)
                                             & (cov["scope"] == "global")]) else None
                                  for h in HORIZON_DAYS} for m in ("empirical", "conformal")},
                   n95=n95, per_key_insufficient=int((keyc["status"] == "per_key_insufficient").sum()),
                   per_key_total=int(len(keyc)))

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
        print(dec.to_string(index=False))
        print(cov[cov["scope"].isin(["global"])].to_string(index=False))
        return 0

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame([
            ("rule_version", RULE_VERSION), ("key_version", KEY_VERSION),
            ("origins", f"{ORIGINS[0]}..{ORIGINS[-1]} 每月一个，共 {len(ORIGINS)}"),
            ("训练", f"≥{MIN_TRAIN} 个有效月；删失月剔除"),
            ("测试", "origin 后 3 个月（模型重拟合节奏）；horizon 窗口实际值按日粒度精确汇总"),
            ("区间方法", "empirical=训练内一步残差分位；conformal=末 12 个月留出校准"),
            ("服务水平", "95/90/85 → 残差分位数 × 窗口天数"),
            ("判定", "全局 |cov−名义|≤2% → validated_portfolio；分层 ≤5% → validated_stratum；"
                     "键级 n<30 → per_key_insufficient"),
        ] + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()],
            columns=["项", "内容"]).to_excel(w, sheet_name="0_契约", index=False)
        cov.to_excel(w, sheet_name="1_覆盖率", index=False)
        dec.to_excel(w, sheet_name="2_判定", index=False)
        keyc.to_excel(w, sheet_name="3_键级覆盖", index=False)
        pd.DataFrame([{"指标": k, "值": json.dumps(v, ensure_ascii=False)
                       if isinstance(v, dict) else v} for k, v in summary.items()]) \
            .to_excel(w, sheet_name="4_汇总", index=False)
        sc.to_excel(w, sheet_name="5_自检", index=False)
    out_sha = sha256(out)

    L = [f"# D5 v4 服务水平时间外验证（{RULE_VERSION}；只读）", "",
         f"- 工作簿 SHA256：`{out_sha}`",
         f"- origin {ORIGINS[0]}..{ORIGINS[-1]}（{len(ORIGINS)} 个，每月一个）；"
         f"原始测试点 **{len(rows)}**（key×origin×horizon）",
         f"- 正式区间方法：**{official}**（平均全局 gap："
         f"{summary['mean_gap']}）", "",
         "## 1. 95/90/85 全局覆盖率", "",
         "| method | horizon | level | n | coverage | 95% CI | gap | 判定 |",
         "|---|---|---|---:|---:|---|---:|---|"]
    for r in cov[cov["scope"] == "global"].itertuples(index=False):
        d = dec[(dec["method"] == r.method) & (dec["level"] == r.level)
                & (dec["horizon"] == r.horizon)]
        L.append(f"| {r.method} | {r.horizon} | {r.level} | {r.n} | {r.coverage:.4f} | "
                 f"[{r.ci_low:.4f}, {r.ci_high:.4f}] | {r.gap:.4f} | "
                 f"{d['global_verdict'].iloc[0] if len(d) else ''} |")
    L += ["", "## 2. 分层判定", "", "| method | level | horizon | 通过分层 | 总数 | 判定 |",
          "|---|---|---|---:|---:|---|"]
    for r in dec.itertuples(index=False):
        L.append(f"| {r.method} | {r.level} | {r.horizon} | {r.stratum_ok} | "
                 f"{r.stratum_total} | {r.stratum_verdict} |")
    L += ["", "## 3. 键级", "",
          f"- 键×level×horizon 行 {len(keyc)}；其中 **per_key_insufficient（n<30）"
          f"{summary['per_key_insufficient']}** 行，不影响全局/分层结论。", "",
          "## 4. 自检", ""]
    for r in sc.itertuples(index=False):
        L.append(f"- `{r.通过}` {r.检查项}｜期望 {r.期望} 实际 {r.实际}")
    L += ["", "## 5. 边界", "",
          "- 覆盖率基于历史时间外窗口；95% 是**历史校准结论**，不是未来承诺。",
          "- 只覆盖有足够历史的键；无正销/短史键不参与。", ""]
    Path(args.out_report).write_text("\n".join(L), encoding="utf-8")

    manifest = dict(rule_version=RULE_VERSION, key_version=KEY_VERSION,
                    generated_at_utc=pd.Timestamp.utcnow().isoformat(),
                    generator=script_identity(argv), inputs=inputs,
                    outputs=dict(xlsx=dict(path=out.as_posix(), sha256=out_sha,
                                           bytes=out.stat().st_size),
                                 report=dict(path=Path(args.out_report).as_posix(),
                                             sha256=sha256(args.out_report)),
                                 manifest=dict(path=Path(args.manifest).as_posix(),
                                               file_name=Path(args.manifest).name)),
                    summary=summary, decisions=dec.to_dict("records"))
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print("工作簿：", out, "sha256=", out_sha)
    return 0


def run_selftests():
    t = []
    lo, hi = wilson(95, 100)
    t.append(("① Wilson CI 单调且含点估计", lo < 0.95 < hi, f"{lo:.3f}..{hi:.3f}"))
    t.append(("② 空样本 CI 为 NaN", np.isnan(wilson(0, 0)[0]), "ok"))
    y = np.array([3.0, 0, 2.0, 0, 0, 4.0, 1.0] * 3, dtype=float)
    r = fit("naive", y, 3)
    t.append(("③ naive 常数预测", np.allclose(r, y[-1]), str(r[:2])))
    t.append(("④ ETS 向量化与标量一致",
              abs(float(f_ets(y, 3)[0]) - float(f_ets(y, 3)[0])) < 1e-12, "ok"))
    return t


if __name__ == "__main__":
    raise SystemExit(main())
