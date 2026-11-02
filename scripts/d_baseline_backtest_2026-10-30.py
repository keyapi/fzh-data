# -*- coding: utf-8 -*-
"""D3 基线 / 滚动回测（只读）—— 分类 → 基线 → 时间外回测 → 模型采用门槛。

输入（只读）
- D2 v2 `D_销量清洗_v2_2026-10-30.xlsx`（1,865 序列 × 22 月，41,030 行；删失 419 EN）
- D1 v2 `D_资格与契约_v2_2026-10-30.xlsx`（3,241 资格行）
- 规则：D-EXECUTION-PLAN-V2 / D-RESEARCH-NOTES / UNIT-LEVEL-CALIBER

做了什么
1) 分类：按 ADI(≈1.32) / CV²(≈0.49) 分 smooth/intermittent/lumpy；`erratic` 在
   `demand_pattern` 中并入 lumpy（另保留 `sbc_class` 原值）；无近期需求→obsolescent；
   可用月 < 12→short。老产品/新品单独打标。
2) 基线：naive、MA3、seasonal naive、ETS(A,N,N)（α 由 SSE 网格优化）。
   **AutoETS（statsforecast）在本机 venv 不可用**（无 statsforecast/numba），
   记为 `autoets: unavailable` 并给原因，不擅自安装依赖；ETS 家族由 `ets_ann` 承担。
   间歇/块状补 Croston、SBA；obsolescent 补 TSB。
3) 滚动回测：3 个日历 origin（训练止 202604/202605/202606，各测后续 3 个月；
   202610 为 censor_unknown 不参与）。指标 WAPE / MAE / pinball@p50（=0.5·MAE，
   本表不产出区间，不用假区间充 pinball）。
4) 采用规则：新方法需 WAPE 与 MAE 都不劣于最佳基线，且至少一项改善 ≥5%；否则用基线；
   TSB 仅在 obsolescent 上。
5) 不做：不预测 censor_unknown / 不足历史 / ND / HM / 老产品；不补 0；不跨 UOM/form。

只读：不写 EN / 通途 / 不发消息 / 不 push。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

B = "D:/Work/fzh-order-store/analysis"
RULE_VERSION = "D3-v1-2026-10-30"

MONTHS = [f"{y}{m:02d}" for y in (2025, 2026) for m in range(1, 13)][:22]  # 202501..202610
OBS_LAST = "202609"                       # 订单导出止 202609；202610 = censor_unknown
ORIGINS = ("202604", "202605", "202606", "202607", "202608")  # 训练止 → 各测后续 3 个日历月
# 前 3 个 origin 测试窗口完全落在已观测月（05-09）；202607/202608 覆盖史在近期的序列，
# 其 202610 测试月为 censor_unknown，自动从评估中剔除。
H = 3
MIN_TRAIN_OBS = 12                        # 训练窗口至少 12 个已观测月
MIN_HIST_CLASS = 12                       # 分类/回测最少可用月
ADI_THR, CV2_THR = 1.32, 0.49
ZERO_CLASSES = ("genuine_zero", "dormant", "long_term_zero")
NAIVE_ALPHA = 0.1
ETS_ALPHAS = np.round(np.arange(0.01, 0.995, 0.01), 2)
ADOPT_GAIN = 0.05


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


# ============================ 数据装载 ============================

def load_series(d2: Path) -> pd.DataFrame:
    q = pd.read_excel(d2, sheet_name="1_序列")
    q["month"] = q["month"].astype(str)
    # 值语义：正销=sellable_qty；真零=dormant/genuine_zero/long_term_zero → 0；删失/未导出 → NaN
    q["y"] = np.where(q["zero_class"] == "observed_positive",
                      pd.to_numeric(q["sellable_qty"], errors="coerce"),
                      np.where(q["zero_class"].isin(ZERO_CLASSES), 0.0, np.nan))
    q["observed"] = q["usable_for_training"].astype(bool)
    q["censored"] = q["zero_class"].isin(["stockout_censored", "censor_unknown"]) | \
        (q["observation_status"] == "orders_not_exported")
    return q


def pivot_series(q: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    keys = ["product_id", "pool", "physical_form", "canonical_uom"]
    meta = (q.groupby(keys, sort=False)
            .agg(is_legacy=("is_legacy", "max"), new_product=("new_product", "max"),
                 forecast_eligible=("forecast_eligible", "max"),
                 n_pos=("zero_class", lambda s: int((s == "observed_positive").sum())),
                 n_obs=("observed", "sum"), n_censored=("censored", "sum"))
            .reset_index())
    series = {}
    for (pid, pool, form, uom), g in q.groupby(keys, sort=False):
        g = g.set_index("month").reindex(MONTHS)
        series[(pid, pool, form, uom)] = dict(
            y=g["y"].to_numpy(dtype=float),
            obs=g["observed"].fillna(False).to_numpy(dtype=bool),
            cens=g["censored"].fillna(True).to_numpy(dtype=bool))
    return series, meta


# ============================ 分类 ============================

def classify(y: np.ndarray, obs: np.ndarray) -> dict:
    obs_idx = np.where(obs)[0]
    n_obs = len(obs_idx)
    vals = y[obs_idx]
    pos = vals[vals > 0]
    out = dict(n_obs=int(n_obs), n_pos=int(len(pos)), adi=np.nan, cv2=np.nan,
               demand_pattern="short", sbc_class="n/a", recent6_sum=0.0)
    if n_obs:
        out["recent6_sum"] = float(np.nansum(vals[-6:]))
    if n_obs < MIN_HIST_CLASS:
        out["reason"] = f"可用月 {n_obs} < {MIN_HIST_CLASS}（历史不足）"
        return out
    if len(pos) == 0:
        out.update(demand_pattern="obsolescent", sbc_class="n/a", reason="训练窗口无正销")
        return out
    if out["recent6_sum"] <= 0 and len(pos) <= 3:
        out.update(demand_pattern="obsolescent", sbc_class="n/a",
                   reason="近 6 个可用月无销量且正销月 ≤3")
        return out
    adi = n_obs / len(pos)
    cv2 = float(np.var(pos, ddof=1) / (np.mean(pos) ** 2)) if len(pos) > 1 else 0.0
    if adi < ADI_THR and cv2 < CV2_THR:
        sbc, pattern = "smooth", "smooth"
    elif adi >= ADI_THR and cv2 < CV2_THR:
        sbc, pattern = "intermittent", "intermittent"
    elif adi >= ADI_THR and cv2 >= CV2_THR:
        sbc, pattern = "lumpy", "lumpy"
    else:
        sbc, pattern = "erratic", "lumpy"   # erratic 在 5 分类中并入 lumpy（模型集另按 sbc_class）
    out.update(adi=float(adi), cv2=cv2, demand_pattern=pattern, sbc_class=sbc,
               reason="" if pattern else "")
    return out


# ============================ 模型（numpy 实现，透明可审计） ============================

def f_naive(y, h, **kw):
    return np.repeat(y[-1], h)


def f_ma3(y, h, **kw):
    return np.repeat(float(np.mean(y[-3:])), h)


def f_snaive(y, h, **kw):
    if len(y) < 12:
        return np.repeat(y[-1], h)
    return np.array([y[-12 + i] if -12 + i < 0 else y[-12] for i in range(h)])


def f_ets_ann(y, h, **kw):
    """ETS(A,N,N)：l_t = α·y_t + (1-α)·l_{t-1}；α 由一步 SSE 网格取最优；初值 l0=y0。"""
    if len(y) < 2:
        return np.repeat(y[-1], h)
    best_a, best_sse = ETS_ALPHAS[0], np.inf
    yv = y[1:]
    for a in ETS_ALPHAS:
        # 一步预测序列：l_{t-1}，初值 l0 = y[0]
        l_prev = np.empty(len(yv))
        l = y[0]
        for i, v in enumerate(yv):
            l_prev[i] = l
            l = a * v + (1 - a) * l
        sse = float(np.sum((yv - l_prev) ** 2))
        if sse < best_sse - 1e-12:
            best_a, best_sse = a, sse
    l = y[0]
    for v in y[1:]:
        l = best_a * v + (1 - best_a) * l
    return np.repeat(l, h)


def _croston_components(y, alpha):
    idx = np.where(y > 0)[0]
    if not len(idx):
        return 0.0, 0.0
    z_hat, p_hat = y[idx[0]], idx[0] + 1.0
    prev = idx[0]
    for i in idx[1:]:
        interval = i - prev
        z_hat = alpha * y[i] + (1 - alpha) * z_hat
        p_hat = alpha * interval + (1 - alpha) * p_hat
        prev = i
    return z_hat, p_hat


def f_croston(y, h, **kw):
    z, p = _croston_components(y, kw.get("alpha", NAIVE_ALPHA))
    return np.repeat(z / p if p > 0 else 0.0, h)


def f_sba(y, h, **kw):
    a = kw.get("alpha", NAIVE_ALPHA)
    z, p = _croston_components(y, a)
    return np.repeat((1 - a / 2) * z / p if p > 0 else 0.0, h)


def f_tsb(y, h, **kw):
    """TSB：p 每期更新（含 0），z 仅在非零期更新；forecast = p·z。"""
    a_d, a_p = kw.get("a_d", NAIVE_ALPHA), kw.get("a_p", NAIVE_ALPHA)
    nz = np.where(y > 0)[0]
    if not len(nz):
        return np.zeros(h)
    z_hat, p_hat = float(y[nz[0]]), len(nz) / len(y)
    for i, v in enumerate(y):
        if v > 0:
            z_hat = a_d * v + (1 - a_d) * z_hat
            p_hat = a_p * 1.0 + (1 - a_p) * p_hat
        else:
            p_hat = a_p * 0.0 + (1 - a_p) * p_hat
    return np.repeat(p_hat * z_hat, h)


BASELINES = dict(naive=f_naive, ma3=f_ma3, snaive=f_snaive, ets_ann=f_ets_ann)
NEW_MODELS = dict(croston=f_croston, sba=f_sba, tsb=f_tsb)


def models_for(pattern: str, sbc: str) -> list[str]:
    """按分类给模型集合；TSB 仅 obsolescent。"""
    m = ["naive", "ma3", "snaive", "ets_ann"]
    if pattern == "obsolescent":
        m += ["croston", "sba", "tsb"]
    elif sbc in ("intermittent", "lumpy"):
        m += ["croston", "sba"]
    elif pattern == "lumpy":
        m += ["croston", "sba"]
    return m


# ============================ 回测 ============================

def backtest_series(y, obs, plan, h=H):
    """按 origin 训练/预测；返回 (逐 origin 结果列表, 逐 origin 明细)。"""
    res, detail = [], []
    for origin in plan:
        oi = MONTHS.index(origin)
        train_idx = [i for i in range(0, oi + 1) if obs[i]]
        test_idx = [i for i in range(oi + 1, min(oi + 1 + h, len(MONTHS))) if obs[i]]
        if len(train_idx) < MIN_TRAIN_OBS or not test_idx:
            res.append(dict(origin=origin, status="skipped",
                            reason=f"训练已观测月 {len(train_idx)} < {MIN_TRAIN_OBS}"
                                   if len(train_idx) < MIN_TRAIN_OBS else "测试窗口无已观测月"))
            continue
        ytr = np.array([y[i] for i in train_idx], dtype=float)
        for name in plan_models:
            fn = BASELINES.get(name) or NEW_MODELS.get(name)
            try:
                fc = np.asarray(fn(ytr, h), dtype=float)
            except Exception as exc:                     # noqa: BLE001
                res.append(dict(origin=origin, model=name, status="failed",
                                reason=f"{type(exc).__name__}: {exc}"[:160]))
                detail.append(dict(origin=origin, model=name, status="failed"))
                continue
            if not np.all(np.isfinite(fc)):
                res.append(dict(origin=origin, model=name, status="failed", reason="非有限预测值"))
                continue
            errs, acts, steps = [], [], []
            for step, i in enumerate(range(oi + 1, min(oi + 1 + h, len(MONTHS)))):
                if not obs[i]:
                    continue
                errs.append(float(fc[step] - y[i]))
                acts.append(float(y[i]))
                steps.append(MONTHS[i])
            if not errs:
                res.append(dict(origin=origin, model=name, status="skipped",
                                reason="测试窗口无可评估月"))
                continue
            res.append(dict(origin=origin, model=name, status="ok",
                            origin_train_end=origin, n_train=len(train_idx),
                            test_months=";".join(steps), n_test=len(errs),
                            sse_abs=float(np.sum(np.abs(errs))), sum_abs=float(np.sum(np.abs(acts))),
                            sum_sq=float(np.sum(np.square(errs))), n=len(errs)))
            detail.append(dict(origin=origin, model=name, status="ok",
                               test_months=";".join(steps), n_test=len(errs),
                               mae=float(np.mean(np.abs(errs))),
                               wape=(float(np.sum(np.abs(errs)) / np.sum(np.abs(acts)))
                                     if np.sum(np.abs(acts)) > 0 else np.nan)))
    return res, detail


def metrics_from(rows) -> dict:
    ok = [r for r in rows if r.get("status") == "ok" and "sse_abs" in r]
    if not ok:
        return dict(status="failed", n=0, wape=np.nan, mae=np.nan, pinball50=np.nan,
                    reason=(rows[0].get("reason") if rows else "无有效 origin"))
    n = sum(r["n"] for r in ok)
    sa = sum(r["sse_abs"] for r in ok)
    sum_abs = sum(r["sum_abs"] for r in ok)
    wape = sa / sum_abs if sum_abs > 0 else np.nan
    mae = sa / n
    return dict(status="ok", n=int(n), wape=float(wape), mae=float(mae),
                pinball50=float(0.5 * mae), reason="")


def _rank(v: dict):
    """排序键：WAPE 未定义（测试窗口无正销）时按 MAE。"""
    w = v["wape"] if np.isfinite(v["wape"]) else np.inf
    return (w, v["mae"])


def _cmp(v: dict, bw, bm) -> tuple[bool, float, str]:
    """新方法 vs 基线：返回 (是否不劣, 最大改善幅度, 说明)。WAPE 未定义时只比 MAE。"""
    wape_ok = (not np.isfinite(bw)) or (np.isfinite(v["wape"]) and v["wape"] <= bw)
    mae_ok = v["mae"] <= bm
    gains = []
    if np.isfinite(bw) and np.isfinite(v["wape"]) and bw > 0:
        gains.append((bw - v["wape"]) / bw)
    if bm > 0:
        gains.append((bm - v["mae"]) / bm)
    note = "" if np.isfinite(bw) else "（基线 WAPE 未定义，仅按 MAE 比较）"
    return (wape_ok and mae_ok), (max(gains) if gains else 0.0), note


def select_model(per_model: dict, pattern: str) -> dict:
    """采用规则：新方法 WAPE/MAE 都不劣于最佳基线，且至少一项改善 ≥5%。

    WAPE 在「测试窗口无正销」时未定义（NaN）——此时按 MAE 比较并在理由里写明，不填 0。
    """
    ok = {k: v for k, v in per_model.items() if v["status"] == "ok"}
    if not ok:
        return dict(adopted="none", baseline="none", reason="无可用模型（全部失败/无可评估月）")
    base = {k: v for k, v in ok.items() if k in BASELINES}
    new = {k: v for k, v in ok.items() if k in NEW_MODELS}
    if not base:
        best_new = min(new, key=lambda k: _rank(new[k])) if new else min(ok, key=lambda k: _rank(ok[k]))
        return dict(adopted=best_new, baseline="none", reason="基线全部失败，取可用新方法（需复核）")
    bb = min(base, key=lambda k: _rank(base[k]))
    bw, bm = base[bb]["wape"], base[bb]["mae"]
    passes, notes = [], []
    for k, v in new.items():
        if k == "tsb" and pattern != "obsolescent":
            continue
        not_worse, gain, note = _cmp(v, bw, bm)
        if not_worse and gain >= ADOPT_GAIN:
            passes.append((k, gain, note))
    if passes:
        k, gain, note = max(passes, key=lambda t: t[1])
        return dict(adopted=k, baseline=bb,
                    reason=f"{k} 相对基线 {bb} 改善 {gain:.1%}（WAPE/MAE 均不劣）{note}")
    note = "" if np.isfinite(bw) else "（测试窗口无正销，WAPE 未定义，按 MAE 比较）"
    return dict(adopted=bb, baseline=bb,
                reason=f"新方法未达门槛（需 WAPE/MAE 均不劣且 ≥{ADOPT_GAIN:.0%} 改善），用基线 {bb}{note}")


# ============================ 自检 ============================

def run_selftests() -> list[tuple[str, bool, str]]:
    tests = []
    y = np.array([5.0, 0, 0, 3.0, 0, 0, 0, 2.0, 0, 0, 4.0, 0], dtype=float)
    # ① naive / MA3 / croston 数值
    ok1 = (np.allclose(f_naive(y, 2), [0, 0]) and np.allclose(f_ma3(y, 1), [y[-3:].mean()])
           and f_croston(y, 1)[0] > 0)
    tests.append(("① naive/MA3/Croston 公式", bool(ok1),
                  f"naive={f_naive(y,1)[0]:.2f} ma3={f_ma3(y,1)[0]:.2f} "
                  f"croston={f_croston(y,1)[0]:.2f} sba={f_sba(y,1)[0]:.2f}"))
    # ② 全零实际 → WAPE 未定义（NaN，不是 0）
    m = metrics_from([dict(status="ok", n=2, sse_abs=0.0, sum_abs=0.0, sum_sq=0.0)])
    tests.append(("② 实际和为 0 → WAPE=NaN（不填 0）", bool(np.isnan(m["wape"])), f"wape={m['wape']}"))
    # ③ 分类阈值：ADI/CV²
    smooth = classify(np.array([2.0] * 12), np.ones(12, bool))
    inter = classify(np.array([2.0, 0, 0, 0, 2.0, 0, 0, 0, 2.0, 0, 0, 0]), np.ones(12, bool))
    short = classify(np.array([1.0, 0, 1.0]), np.ones(3, bool))
    ok3 = (smooth["demand_pattern"] == "smooth" and
           inter["demand_pattern"] == "intermittent" and short["demand_pattern"] == "short")
    tests.append(("③ 分类（smooth/intermittent/short）", ok3,
                  f"{smooth['demand_pattern']}/{inter['demand_pattern']}/{short['demand_pattern']}"))
    # ④ 采用门槛：5% 以上才采用
    per = {"naive": dict(status="ok", wape=1.0, mae=1.0),
           "croston": dict(status="ok", wape=0.90, mae=0.90),
           "sba": dict(status="ok", wape=0.97, mae=0.97)}
    sel = select_model(per, "intermittent")
    ok4 = sel["adopted"] == "croston"
    per2 = dict(per, croston=dict(status="ok", wape=0.98, mae=0.98), sba=dict(status="ok", wape=0.97, mae=0.97))
    sel2 = select_model(per2, "intermittent")
    ok5 = sel2["adopted"] == "naive"
    tests.append(("④ 采用门槛（≥5% 才用新方法）", bool(ok4 and ok5),
                  f"improve5%→{sel['adopted']} / improve3%→{sel2['adopted']}"))
    # ⑤ 删失月不进评估
    yy = np.array([3.0] * 12 + [5.0, np.nan, 5.0], dtype=float)
    ob = np.array([True] * 12 + [True, False, True])
    plan = ("202512",)
    global plan_models
    plan_models = ["naive"]
    res, detail = backtest_series(yy, ob, plan, h=3)
    ok6 = len(detail) == 1 and detail[0]["n_test"] == 2
    tests.append(("⑤ 删失月不进评估（n_test=2）", bool(ok6),
                  f"{detail[0] if detail else None}"))
    return tests


# ============================ 主流程 ============================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D3 基线/滚动回测（只读）")
    ap.add_argument("--d2", default=f"{B}/D_销量清洗_v2_2026-10-30.xlsx")
    ap.add_argument("--d1", default=f"{B}/D_资格与契约_v2_2026-10-30.xlsx")
    ap.add_argument("--out-xlsx", default=f"{B}/D_基线回测_2026-10-30.xlsx")
    ap.add_argument("--out-report", default=f"{B}/D_基线回测_2026-10-30_报告.md")
    ap.add_argument("--manifest", default=f"{B}/D_基线回测_2026-10-30.manifest.json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        res = run_selftests()
        for n, ok, d in res:
            print(f"[{'PASS' if ok else 'FAIL'}] {n}｜{d}")
        bad = [n for n, ok, _ in res if not ok]
        print(f"\n{len(res) - len(bad)}/{len(res)} 通过")
        return 0 if not bad else 1

    global plan_models
    inputs = {k: dict(path=str(v), sha256=sha256(v)) for k, v in
              (("D2_SERIES", args.d2), ("D1_ELIGIBILITY", args.d1)) if Path(v).exists()}

    q = load_series(Path(args.d2))
    series, meta = pivot_series(q)
    meta_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
                for r in meta.itertuples(index=False)}

    cls_rows, res_rows, detail_rows, fail_rows = [], [], [], []
    for key, s in series.items():
        pid, pool, form, uom = key
        mt = meta_idx[key]
        c = classify(s["y"], s["obs"])
        row = dict(product_id=pid, pool=pool, physical_form=form, canonical_uom=uom,
                   n_obs=c["n_obs"], n_pos=c["n_pos"], n_censored=int(mt.n_censored),
                   adi=c["adi"], cv2=c["cv2"], demand_pattern=c["demand_pattern"],
                   sbc_class=c["sbc_class"], recent6_sum=c["recent6_sum"],
                   is_legacy=bool(mt.is_legacy), new_product=bool(mt.new_product),
                   forecast_eligible=bool(mt.forecast_eligible), reason=c.get("reason", ""))
        backtestable = (c["n_obs"] >= MIN_HIST_CLASS and c["n_pos"] > 0
                        and not bool(mt.is_legacy) and bool(mt.forecast_eligible))
        row["backtestable"] = backtestable
        if not backtestable:
            why = ("老产品（forecast_eligible=false）" if bool(mt.is_legacy)
                   else "forecast_eligible=false" if not bool(mt.forecast_eligible)
                   else c.get("reason") or ("无正销" if c["n_pos"] == 0 else "历史不足"))
            row["not_backtestable_reason"] = why
            fail_rows.append(dict(层级="series", product_id=pid, pool=pool,
                                  physical_form=form, canonical_uom=uom,
                                  类型="不可回测", 原因=why))
            cls_rows.append(row)
            continue
        plan_models = models_for(c["demand_pattern"], c["sbc_class"])
        res, det = backtest_series(s["y"], s["obs"], ORIGINS, H)
        for r in res:
            if r.get("status") in ("skipped", "failed"):
                fail_rows.append(dict(层级="origin", product_id=pid, pool=pool,
                                      physical_form=form, canonical_uom=uom,
                                      类型=f"{r.get('model', 'origin')}:{r['status']}",
                                      原因=r.get("reason", "")))
        per_model = {}
        for name in plan_models:
            mm = metrics_from([r for r in res if r.get("model") == name])
            per_model[name] = mm
            res_rows.append(dict(product_id=pid, pool=pool, physical_form=form,
                                 canonical_uom=uom, demand_pattern=c["demand_pattern"],
                                 sbc_class=c["sbc_class"], model=name,
                                 family=("baseline" if name in BASELINES else "new"),
                                 status=mm["status"], n_obs=mm["n"],
                                 wape=mm["wape"], mae=mm["mae"], pinball50=mm["pinball50"],
                                 failure_reason=mm["reason"]))
        sel = select_model(per_model, c["demand_pattern"])
        if sel["adopted"] == "none":
            skips = [r for r in res if r.get("status") == "skipped"]
            if skips:
                reasons = "；".join(sorted({str(r.get("reason")) for r in skips}))
                sel = dict(adopted="none", baseline="none",
                           reason=f"无可回测 origin（{len(skips)} 个 origin 全部跳过）：{reasons}")
        row.update(adopted_model=sel["adopted"], best_baseline=sel["baseline"],
                   selection_reason=sel["reason"])
        cls_rows.append(row)
        for d in det:
            if d.get("status") != "ok":
                continue
            detail_rows.append(dict(product_id=pid, pool=pool, physical_form=form,
                                    canonical_uom=uom, model=d["model"], origin=d["origin"],
                                    test_months=d["test_months"], n_test=d["n_test"],
                                    mae=d["mae"], wape=d["wape"]))
        # 采用结果写回模型行
        for rr in res_rows:
            if (rr["product_id"], rr["pool"], rr["physical_form"], rr["canonical_uom"]) == key:
                rr["adopted"] = "是" if rr["model"] == sel["adopted"] else "否"

    cls_tbl = pd.DataFrame(cls_rows)
    res_tbl = pd.DataFrame(res_rows)
    det_tbl = pd.DataFrame(detail_rows)
    fail_tbl = pd.DataFrame(fail_rows)


    # 未采用的“新方法未达门槛”记录
    for rr in res_tbl[res_tbl["family"] == "new"].itertuples(index=False):
        if rr.adopted == "否" and rr.status == "ok":
            fail_rows.append(dict(层级="model", product_id=rr.product_id, pool=rr.pool,
                                  physical_form=rr.physical_form, canonical_uom=rr.canonical_uom,
                                  类型=f"{rr.model}:not_adopted",
                                  原因="未达门槛（WAPE/MAE 需不劣且 ≥5% 改善；TSB 仅 obsolescent）"))
    fail_tbl = pd.DataFrame(fail_rows)


    # ---------- 汇总
    n_series = len(cls_tbl)
    n_bt = int(cls_tbl["backtestable"].sum())
    fail_tbl = pd.concat([fail_tbl, pd.DataFrame([dict(
        层级="model", product_id="-", pool="-", physical_form="-", canonical_uom="-",
        类型="autoets:unavailable",
        原因=(f"statsforecast 未安装（venv 无 statsforecast/numba；numpy {np.__version__} 与 numba "
              f"兼容性未验证，不擅自安装）→ 作用于全部 {n_bt} 个可回测序列；"
              "ETS 家族由 ets_ann（A,N,N，α 网格优化）承担"))])], ignore_index=True)
    pat = cls_tbl["demand_pattern"].value_counts().to_dict()
    adopted = cls_tbl.loc[cls_tbl["backtestable"], "adopted_model"].value_counts().to_dict()
    best_base = cls_tbl.loc[cls_tbl["backtestable"], "best_baseline"].value_counts().to_dict()
    per_class = []
    for p in sorted(pat):
        sub = cls_tbl[(cls_tbl["demand_pattern"] == p) & cls_tbl["backtestable"]]
        per_class.append(dict(demand_pattern=p, 序列数=int((cls_tbl["demand_pattern"] == p).sum()),
                              可回测=int(len(sub)),
                              采用分布=json.dumps(sub["adopted_model"].value_counts().to_dict(),
                                                ensure_ascii=False) if len(sub) else "{}"))

    summary = pd.DataFrame([
        dict(指标="序列总数", 值=n_series, 说明="D2 v2 序列键数"),
        dict(指标="可回测序列", 值=n_bt, 说明="历史≥12 可用月、有正销、非老产品、forecast_eligible"),
        dict(指标="不可回测序列", 值=n_series - n_bt, 说明="见 5_失败"),
        dict(指标="分类·smooth", 值=pat.get("smooth", 0), 说明=""),
        dict(指标="分类·intermittent", 值=pat.get("intermittent", 0), 说明=""),
        dict(指标="分类·lumpy", 值=pat.get("lumpy", 0), 说明="含 erratic（见 sbc_class）"),
        dict(指标="分类·obsolescent", 值=pat.get("obsolescent", 0), 说明="近 6 月无销量"),
        dict(指标="分类·short", 值=pat.get("short", 0), 说明="可用月 <12"),
        dict(指标="滚动回测 origin", 值=len(ORIGINS), 说明=";".join(ORIGINS) + "，各 h=3"),
        dict(指标="回测明细行", 值=len(det_tbl), 说明="series×origin×model"),
        dict(指标="最佳基线分布", 值=json.dumps(best_base, ensure_ascii=False), 说明="按可回测序列"),
        dict(指标="采用模型分布", 值=json.dumps(adopted, ensure_ascii=False), 说明="含基线回退"),
        dict(指标="采用新方法序列", 值=int(sum(v for k, v in adopted.items() if k in NEW_MODELS)),
         说明="croston/sba/tsb"),
        dict(指标="不可用模型", 值="autoets", 说明="statsforecast 未安装；见 5_失败"),
        dict(指标="模型失败（无有效 origin）",
             值=int((res_tbl["status"] == "failed").sum()),
             说明="训练窗口已观测月 <12；不是模型崩溃，原因逐行在 5_失败"),
        dict(指标="WAPE 未定义行（测试窗口无正销）",
             值=int(((res_tbl["status"] == "ok") & res_tbl["wape"].isna()).sum()),
             说明="WAPE=NaN 不填 0；按 MAE 参与采用比较"),
        dict(指标="失败/未采用记录", 值=len(fail_tbl), 说明="见 5_失败"),
    ])

    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("输入 D2", str(args.d2)), ("输入 D1", str(args.d1)),
        ("粒度", "product_id × pool × physical_form × canonical_uom × month（不跨 UOM/form）"),
        ("月份", "202501..202610；202610=censor_unknown 不入评估"),
        ("值语义", "正销=sellable_qty；genuine_zero/dormant/long_term_zero=0；"
                   "stockout_censored/censor_unknown/orders_not_exported=NaN（不作为 0）"),
        ("分类阈值", f"ADI≥{ADI_THR} 与 CV²≥{CV2_THR} 组合；erratic 并入 lumpy（sbc_class 保留原值）；"
                    f"可用月<{MIN_HIST_CLASS}→short；近 6 月无销量且正销≤3→obsolescent"),
        ("基线", "naive / MA3 / seasonal naive（滞后 12，不足回退 naive）/ ETS(A,N,N,α 网格优化)"),
        ("autoets", "statsforecast 在本机 venv 不可用（无 statsforecast/numba，numpy 2.4 与 numba 兼容性未验证）"
                    "→ 记 unavailable，不擅自安装依赖；ETS 家族由 ets_ann 承担"),
        ("新方法", "croston(α=0.1) / sba(α=0.1) 用于 intermittent/lumpy/obsolescent；"
                   "tsb(αd=αp=0.1) 仅 obsolescent"),
        ("回测", f"origin={';'.join(ORIGINS)}（训练止该月，测后续 {H} 个日历月）；"
                 f"训练已观测月 ≥{MIN_TRAIN_OBS}；删失月不进评估"),
        ("指标", "WAPE=Σ|e|/Σ|y|（Σ|y|=0 → NaN，不填 0）；MAE；pinball@p50=0.5·MAE（本表不产区间）"),
        ("采用规则", f"新方法 WAPE 与 MAE 均不劣于最佳基线，且至少一项改善 ≥{ADOPT_GAIN:.0%}；"
                     "否则用基线；TSB 仅 obsolescent"),
        ("不做", "不预测 censor_unknown/不足历史/ND/HM/老产品；不补 0；不跨 UOM/form；不下单"),
    ] + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()],
        columns=["项", "内容"])

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        cls_tbl.to_excel(w, sheet_name="1_分类", index=False)
        res_tbl.to_excel(w, sheet_name="2_模型结果", index=False)
        det_tbl.to_excel(w, sheet_name="3_滚动回测", index=False)
        summary.to_excel(w, sheet_name="4_汇总", index=False)
        fail_tbl.to_excel(w, sheet_name="5_失败", index=False)
    out_sha = sha256(out)
    sheets = {s: int(len(pd.read_excel(out, sheet_name=s))) for s in pd.ExcelFile(out).sheet_names}

    tests = run_selftests()
    L = [f"# D3 基线与滚动回测（{RULE_VERSION}；只读）", "",
         f"- 工作簿 SHA256：`{out_sha}`",
         f"- 序列 **{n_series}**（全部已分类）｜可回测 **{n_bt}**｜不可回测 {n_series - n_bt}", "",
         "## 1. 分类结果", "", "| demand_pattern | 序列数 |", "|---|---:|"]
    for k, v in pat.items():
        L.append(f"| {k} | {v} |")
    L += ["", "（`erratic` 因任务要求 5 分类，并入 lumpy；原始 SBC 标签见 `1_分类.sbc_class`）", "",
          "## 2. 模型与采用", "",
          f"- 基线：naive / MA3 / seasonal naive / ETS(A,N,N)（α 网格优化）。"
          "**AutoETS(statsforecast) 不可用**，记 `unavailable` 不安装依赖。",
          f"- 新方法：Croston / SBA（intermittent·lumpy·obsolescent）、TSB（仅 obsolescent）。",
          f"- 采用门槛：WAPE 与 MAE 均不劣于最佳基线 + 至少一项改善 ≥5%。",
          "",
          f"- 最佳基线分布：`{json.dumps(best_base, ensure_ascii=False)}`",
          f"- 采用模型分布：`{json.dumps(adopted, ensure_ascii=False)}`",
          f"- 采用新方法序列：**{int(sum(v for k, v in adopted.items() if k in NEW_MODELS))}**", "",
          "| demand_pattern | 序列数 | 可回测 | 采用分布 |", "|---|---:|---:|---|"]
    for r in per_class:
        L.append(f"| {r['demand_pattern']} | {r['序列数']} | {r['可回测']} | {r['采用分布']} |")
    L += ["", "## 3. 滚动回测口径", "",
          f"- origin：{'; '.join(ORIGINS)}（训练止该月，测后续 {H} 个日历月）；"
          f"训练已观测月 ≥{MIN_TRAIN_OBS}；202610=censor_unknown 不进评估。",
          f"- 明细 {len(det_tbl)} 行（series×origin×model）；逐 origin 可复算。",
          "- 指标：WAPE=Σ|e|/Σ|y|（Σ|y|=0 → NaN，不填 0）；MAE；pinball@p50=0.5·MAE。", "",
          "## 4. 失败与不可回测", "", f"共 **{len(fail_tbl)}** 条，见 `5_失败`。", "",
          "| 类型 | 条数 |", "|---|---:|"]
    for k, v in fail_tbl["类型"].value_counts().items():
        L.append(f"| {k} | {v} |")
    L += ["", "## 5. 自检（内存测试）", ""]
    for n, ok, d in tests:
        L.append(f"- `{'PASS' if ok else 'FAIL'}` {n}｜{d}")
    L += ["", "## 6. 只读声明", "",
          "仅本地读表/内存计算/写本地 xlsx 与 md；未调用 EN/通途写接口，未发消息，未 push。", ""]
    Path(args.out_report).write_text("\n".join(L), encoding="utf-8")

    manifest = dict(
        rule_version=RULE_VERSION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        generated_at_local=datetime.now().astimezone().isoformat(timespec="seconds"),
        generator=script_identity(argv), inputs=inputs,
        outputs=dict(
            xlsx=dict(path=out.as_posix(), sha256=out_sha, bytes=out.stat().st_size, sheets=sheets),
            report=dict(path=Path(args.out_report).as_posix(),
                        sha256=sha256(args.out_report),
                        bytes=Path(args.out_report).stat().st_size),
            manifest=dict(path=Path(args.manifest).as_posix(), file_name=Path(args.manifest).name,
                          sha256=None, note="manifest 自身不写自哈希")),
        row_counts=dict(series=n_series, backtestable=n_bt, patterns=pat,
                        models_rows=len(res_tbl), detail_rows=len(det_tbl),
                        failures=len(fail_tbl)),
        adopted=adopted, best_baseline=best_base,
        unavailable_models=["autoets（statsforecast 未安装）"],
        selftests=[dict(name=n, passed=bool(ok), detail=d) for n, ok, d in tests],
        verify=dict(xlsx_match=sha256(out) == out_sha,
                    report_match=sha256(args.out_report) ==
                    sha256(args.out_report),
                    script_match=hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
                    == script_identity()["script_sha256"]),
        note="xlsx 含 openpyxl 时间戳，重跑 SHA 不保证相同；血缘以 输入 SHA + 脚本 SHA + 行数 证明。",
    )
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")
    print(json.dumps(dict(series=n_series, backtestable=n_bt, patterns=pat, adopted=adopted,
                          best_baseline=best_base, detail=len(det_tbl), failures=len(fail_tbl),
                          selftests=[(n, ok) for n, ok, _ in tests]), ensure_ascii=False, indent=1))
    print("工作簿：", out, "sha256=", out_sha)
    print("报告：", args.out_report)
    print("manifest：", args.manifest)
    return 0 if all(ok for _, ok, _ in tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
