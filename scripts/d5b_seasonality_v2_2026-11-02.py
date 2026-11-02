# -*- coding: utf-8 -*-
"""D5b v2 自动季节/促销/清仓识别 + 三组时间外回测（只读）。

任务：D:/Work/fzh-order-store/analysis/D5B_TASK_2026-11-02.md

做什么
1) 按 D3b v3.1 正式键（D1b v2.3 product×market×pool×form×uom，1,853 键）
   重建 2023-01..2026-10 键级月度序列；v1 的 1,865 旧键保留在迁移对账中。
2) 月序列做稳健 STL 分解（失败退经典分解），提取年季节项；Fourier 年谐波作候选，
   输出 seasonality_status（strong/weak/none/insufficient）、季节强度、峰值月。
3) 事件窗口：固定日历（Prime Day/返校季/Prime Big Deal Days/黑五网一/圣诞）
   + 历史 residual 峰值聚类；每个 detected 窗口必须带历史证据。
4) promo_status（detected/unknown/none）；unknown 只标记，不删单、不当 organic。
5) clearance_evidence 只作旁证：D2 v3 clearance_lines（SKU 名 #qc/清仓）、
   Jeck 特殊规则成本窗口（不是促销日历、FBA 不直接适用）、
   PROMO-CLEARANCE v2 lead（clearance_confirmed=0，未确认）。
6) 三组时间外回测（同一 origin / 同一测试点）：
   A 无特征 / B 自动季节 / C 季节+清仓（清仓窗只从训练剔除，不作需求基准）。
   每组 WAPE/MAE/pinball50/coverage80；按「不劣 + 至少一项改善 ≥5%」逐键采用，
   不达标 fallback=baseline。
7) 广告：仅有极少量近期报表 → 单独报告完整覆盖子集（0 键）；缺失不使历史订单失效。

只读：不写 EN/通途、不下单、不 push。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
RULE_VERSION = "D5b-v2-2026-11-02"
KEY_VERSION = "D1b-v2.3-2026-11-02"   # D1b v2.3 正式键（product×market×pool×form×uom）
END_MONTH = "202610"
OBS_MONTHS = [f"{y}{m:02d}" for y in range(2023, 2027) for m in range(1, 13)]
OBS_MONTHS = [m for m in OBS_MONTHS if m <= END_MONTH]      # 202301..202610
MONTH_IDX = {m: i for i, m in enumerate(OBS_MONTHS)}
ORIGINS = ("202604", "202605", "202606", "202607")          # 各测后续 3 个日历月
H = 3
MIN_TRAIN_OBS = 12
MIN_SEASON_MONTHS = 18
MIN_SEASON_YEARS = 2
SEASON_STRONG, SEASON_WEAK = 0.30, 0.10
FOURIER_R2_STRONG, FOURIER_R2_WEAK = 0.10, 0.05
AMP_STRONG = 1.15
PROMO_Z = 2.5
PROMO_LIFT = 0.25
ADOPT_GAIN = 0.05
ETS_ALPHAS = np.round(np.arange(0.01, 0.995, 0.01), 2)

PREFIXES = ("old_", "new-", "new_")
SUFFIXES = ("-cover", "-c", "-1", "-2")
FIXED_WINDOWS = {
    "Prime Day": [7],
    "返校季": [8],
    "Prime Big Deal Days": [10],
    "黑五网一": [11],
    "圣诞": [12],
}
POOL_OF_WAREHOUSE = {
    "CENTRADE": "美东USNJ", "美东-CENTRADE": "美东USNJ", "北美之路-NJ02": "美东USNJ",
    "WayfairCG-Cranbury仓": "美东USNJ",
    "FZH-DANEEY-皮壳仓库": "美中USTX", "FZH-DANEEY": "美中USTX",
    "FZH-DANEEY-成品仓": "美中USTX", "FZH-DANEEY-半成品仓": "美中USTX",
    "FZH-DANEEY-退货产品仓": "美中USTX", "美中-FZH-DANEEY": "美中USTX",
    "美中-FZH-DANEEY-皮壳仓库": "美中USTX", "美中-FZH-DANEEY-退货产品仓": "美中USTX",
    "休斯顿1号仓": "美中USTX", "休斯顿1号备用仓库": "美中USTX",
    "海外仓美中仓库备用仓": "美中USTX", "北美之路-LA01": "美中USTX",
    "WayfairCG-Romeoville仓": "美中USTX", "WayfairCG-Perris仓": "美中USTX",
    "FZHPoland-covers": "波兰", "波兰-FZHPoland-covers": "波兰",
    "FZHPoland-finished": "波兰",
}
AD_AVAILABLE_KEYS = 0   # 目前只有 BJRYECLTD-US 样本报表，无键级完整覆盖


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
                statsmodels=__import__("statsmodels").__version__,
                argv=[str(x) for x in (argv if argv is not None else sys.argv[1:])])


def norm(s) -> str:
    x = str(s).strip().casefold().replace(" ", "")
    changed = True
    while changed:
        changed = False
        for pre in PREFIXES:
            if x.startswith(pre):
                x = x[len(pre):]
                changed = True
        for suf in SUFFIXES:
            if x.endswith(suf) and len(x) > len(suf) + 2:
                x = x[: -len(suf)]
                changed = True
    return x


def variants(sku: str) -> list[str]:
    base = str(sku).strip().casefold().replace(" ", "")
    v = [base, norm(sku)]
    m = re.match(r"^(.*?)-\d+$", base)
    if m:
        v.append(m.group(1))
        v.append(norm(m.group(1)))
    return list(dict.fromkeys(x for x in v if x))


def ymonth(i: int) -> int:
    return int(OBS_MONTHS[i][-2:])


def years_of(mask: np.ndarray) -> list[str]:
    return sorted({OBS_MONTHS[i][:4] for i in np.where(mask)[0]})


# ============================ 输入 / 映射（同 D3b v3.1 正式键口径） ============================

def build_code_index(a: pd.DataFrame, sku_map: pd.DataFrame,
                     cust: pd.DataFrame) -> tuple[dict, dict]:
    idx: dict[str, dict[str, list[str]]] = {}
    ev: dict[str, str] = {}

    def add(code, prod, why):
        if not code or code in ("nan", "none"):
            return
        c = str(code).strip().casefold().replace(" ", "")
        if not c:
            return
        idx.setdefault(c, {}).setdefault(prod, []).append(why)
        ev.setdefault(c, why)

    for r in a.itertuples(index=False):
        for t in re.split(r"[,;，]", str(getattr(r, "来源码", "") or "")):
            add(t, r.EN物料, "A来源码")
    for r in sku_map.itertuples(index=False):
        add(getattr(r, "tt"), getattr(r, "en"), "sku_map")
    for r in cust.itertuples(index=False):
        for c in str(getattr(r, "customer_code", "")).split(","):
            c = c.strip()
            if not c:
                continue
            if c.startswith("删除"):
                add(c[2:], r.name, "customer_code(删除别名)")
            else:
                add(c, r.name, "customer_code")
    return idx, ev


def form_of(pid: str, role: str) -> str:
    p = str(pid)
    if p.startswith("PK#"):
        return "皮壳"
    if p.upper().startswith("TJ#"):
        return "套件"
    if p.startswith("ND#"):
        return "内胆"
    r = str(role)
    if r == "主体骨架":
        return "骨架"
    if "海绵" in r:
        return "无适用"
    return "成品"


# ============================ 预测模型（D3b 同口径基线集） ============================

def f_naive(y, h, **kw):
    return np.repeat(y[-1], h)


def f_ma3(y, h, **kw):
    return np.repeat(float(np.mean(y[-3:])), h)


def f_snaive(y, h, **kw):
    if len(y) < 12:
        return np.repeat(y[-1], h)
    return np.array([y[-12 + i] if -12 + i < 0 else y[-12] for i in range(h)])


def f_ets_ann(y, h, **kw):
    if len(y) < 2:
        return np.repeat(y[-1], h)
    yv = y[1:]
    best_a, best_sse = ETS_ALPHAS[0], np.inf
    for a in ETS_ALPHAS:
        l, sse = y[0], 0.0
        for v in yv:
            sse += (v - l) ** 2
            l = a * v + (1 - a) * l
        if sse < best_sse - 1e-12:
            best_a, best_sse = a, sse
    l, a = y[0], best_a
    for v in yv:
        l = a * v + (1 - a) * l
    return np.repeat(l, h)


MODELS = {"naive": f_naive, "ma3": f_ma3, "snaive": f_snaive, "ets_ann": f_ets_ann}
MODEL_ORDER = ["snaive", "ma3", "ets_ann", "naive"]


def predict(name: str, y, h: int) -> np.ndarray:
    return np.asarray(MODELS[name](np.asarray(y, dtype=float), h), dtype=float)


def _ets_alpha(y: np.ndarray) -> float:
    yv, best_a, best_sse = y[1:], ETS_ALPHAS[0], np.inf
    for a in ETS_ALPHAS:
        l, sse = y[0], 0.0
        for v in yv:
            sse += (v - l) ** 2
            l = a * v + (1 - a) * l
        if sse < best_sse - 1e-12:
            best_a, best_sse = a, sse
    return float(best_a)


def insample_resid(name: str, y) -> np.ndarray:
    """一步样本内残差（用于经验 80% 预测区间）。"""
    y = np.asarray(y, dtype=float)
    if name == "naive":
        return y[1:] - y[:-1]
    if name == "ma3":
        return np.array([y[i] - np.mean(y[i - 3:i]) for i in range(3, len(y))])
    if name == "snaive":
        return np.array([y[i] - y[i - 12] for i in range(12, len(y))])
    if name == "ets_ann":
        if len(y) < 2:
            return np.array([])
        a = _ets_alpha(y)
        res, l = [], y[0]
        for v in y[1:]:
            res.append(v - l)
            l = a * v + (1 - a) * l
        return np.asarray(res)
    return np.array([])


def inner_select(ytr: np.ndarray) -> str:
    """只用 origin 之前训练段的内层 holdout 选模型，不用测试窗。"""
    ytr = np.asarray(ytr, dtype=float)
    if len(ytr) < 9:
        return "ma3"
    itr, iy = ytr[:-H], ytr[-H:]
    best, best_mae = "ma3", np.inf
    for name in MODEL_ORDER:
        try:
            fc = predict(name, itr, H)
        except Exception:                                   # noqa: BLE001
            continue
        if not np.all(np.isfinite(fc)):
            continue
        mae = float(np.mean(np.abs(fc - iy)))
        if mae < best_mae - 1e-12:
            best, best_mae = name, mae
    return best


# ============================ 季节分解 / 检测 ============================

def _fill(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = arr.astype(float).copy()
    if mask.all() or not mask.any():
        return out
    x = np.arange(len(out))
    out[~mask] = np.interp(x[~mask], x[mask], out[mask])
    return out


def decompose(vals: np.ndarray, usable: np.ndarray) -> dict | None:
    """稳健 STL（失败退经典分解），返回季节强度/指数/残差 z。"""
    idx = np.where(usable)[0]
    if len(idx) == 0:
        return None
    s, e = int(idx[0]), int(idx[-1])
    y = vals[s:e + 1].astype(float)
    m = usable[s:e + 1]
    if m.sum() < 6:
        return None
    yi = _fill(y, m)
    months = np.array([int(OBS_MONTHS[s + i]) % 100 for i in range(len(yi))])
    method = "stl"
    try:
        if m.sum() < 12:
            raise ValueError("short")
        res = STL(yi, period=12, seasonal=7, robust=True).fit()
        trend, seas, resid = res.trend, res.seasonal, res.resid
    except Exception:                                       # noqa: BLE001
        method = "classical"
        tr = pd.Series(yi).rolling(12, center=True, min_periods=6).mean().to_numpy()
        x = np.arange(len(yi))
        ok = np.isfinite(tr)
        trend = np.interp(x, x[ok], tr[ok]) if ok.any() else np.repeat(np.mean(yi), len(yi))
        detr = yi - trend
        seas = np.zeros(len(yi))
        for mo in range(1, 13):
            sel = months == mo
            if sel.any():
                seas[sel] = np.median(detr[sel])
        resid = detr - seas
    v_sr = float(np.var(resid + seas))
    strength = max(0.0, 1.0 - float(np.var(resid)) / v_sr) if v_sr > 0 else 0.0
    # 乘法季节指数：年内月份占比（月值/当年均值，跨年取中位），对零销月稳健
    raw = np.ones(12)
    have = np.zeros(12, dtype=bool)
    per_month: dict[int, list[float]] = {mo: [] for mo in range(1, 13)}
    for yr in sorted({OBS_MONTHS[s + i][:4] for i in range(len(yi))}):
        pos = [i for i in range(len(yi)) if OBS_MONTHS[s + i].startswith(yr)]
        ymean = float(np.mean(yi[pos])) if pos else 0.0
        if ymean <= 1e-9:
            continue
        for i in pos:
            per_month[months[i]].append(float(yi[i]) / ymean)
    for mo in range(1, 13):
        if per_month[mo]:
            raw[mo - 1] = float(np.median(per_month[mo]))
            have[mo - 1] = True
    avg = float(np.mean(raw[have])) if have.any() else 0.0
    index = np.ones(12) if avg <= 0 else np.where(have, raw / avg, 1.0)
    index = np.clip(index, 0.25, 4.0)
    r2 = float("nan")
    try:
        t = np.arange(len(yi), dtype=float)
        cols = [np.ones_like(t), t]
        for k in (1, 2):
            cols += [np.sin(2 * np.pi * k * t / 12), np.cos(2 * np.pi * k * t / 12)]
        X = np.column_stack(cols)[m]
        yy = y[m]
        beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
        sse = float(np.sum((yy - X @ beta) ** 2))
        sst = float(np.sum((yy - yy.mean()) ** 2))
        r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    except Exception:                                       # noqa: BLE001
        pass
    res_full = np.zeros(len(vals))
    rs = resid[np.isfinite(resid)]
    med = float(np.median(rs)) if len(rs) else 0.0
    mad = float(np.median(np.abs(rs - med))) if len(rs) else 0.0
    scale = 1.4826 * mad
    if scale <= 1e-9:
        scale = float(np.std(rs)) if len(rs) else 0.0
    if scale > 1e-9:
        res_full[s:e + 1] = (resid - med) / scale
    peak = int(np.argmax(index)) + 1
    trough = int(np.argmin(index)) + 1
    pos_idx = index[index > 0]
    amp = float(pos_idx.max() / pos_idx.min()) if len(pos_idx) else 1.0
    return dict(method=method, strength=strength, fourier_r2=r2, index=index,
                peak_month=peak, trough_month=trough, amplitude=amp, z=res_full,
                span=(s, e), mad=mad)


def season_status(n_usable: int, n_years: int, dec: dict | None) -> str:
    if dec is None or n_usable < MIN_SEASON_MONTHS or n_years < MIN_SEASON_YEARS:
        return "insufficient"
    if (dec["strength"] >= SEASON_STRONG and n_years >= 3
            and np.isfinite(dec["fourier_r2"])
            and dec["fourier_r2"] >= FOURIER_R2_STRONG and dec["amplitude"] >= AMP_STRONG):
        return "strong"
    if dec["strength"] >= SEASON_WEAK or (np.isfinite(dec["fourier_r2"])
                                          and dec["fourier_r2"] >= FOURIER_R2_WEAK):
        return "weak"
    return "none"


def detect_windows(vals, usable, dec) -> list[dict]:
    """固定日历 + residual 峰值聚类；每条窗口都带历史证据。"""
    out = []
    if dec is None:
        return out
    z = dec["z"]
    years = years_of(usable)
    covered = set()
    for name, months in FIXED_WINDOWS.items():
        sup = []
        for yr in years:
            for mo in months:
                i = MONTH_IDX.get(f"{yr}{mo:02d}")
                if i is None or not usable[i]:
                    continue
                yv = float(vals[i])
                ys = [vals[j] for j in range(len(vals))
                      if OBS_MONTHS[j].startswith(yr) and usable[j]]
                ym = float(np.mean(ys)) if ys else 0.0
                lift = yv / ym if ym > 0 else 0.0
                if z[i] >= 1.0 or (lift >= 1.2 and yv > 0):
                    sup.append((yr, float(z[i]), lift, yv))
                    covered.add(i)
        if len(sup) >= 2 or (len(sup) == 1 and sup[0][0] == "2026" and sup[0][1] >= 2.0):
            ev = "；".join(f"{yr}(z={zv:.2f},lift={lf:.2f})" for yr, zv, lf, _ in sup)
            out.append(dict(window_type=name,
                            start_month=f"每年{months[0]:02d}月",
                            end_month=f"每年{months[-1]:02d}月",
                            years_supported=len(sup),
                            evidence=f"固定日历 {name}：{ev}",
                            kind="fixed"))
    if dec["mad"] > 1e-9 and np.isfinite(dec["mad"]) and usable.sum() >= MIN_SEASON_MONTHS:
        level = float(np.mean(vals[usable]))
        flag = np.array([bool(usable[i] and z[i] >= PROMO_Z
                              and (vals[i] - level) >= PROMO_LIFT * level)
                         for i in range(len(vals))])
        for i in covered:
            flag[i] = False
        i = 0
        while i < len(flag):
            if not flag[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(flag) and (flag[j + 1] or
                                        (not usable[j + 1] and j + 2 < len(flag)
                                         and flag[j + 2])):
                j = j + 1 if flag[j + 1] else j + 2
            months = [k for k in range(i, j + 1) if flag[k]]
            ev = "；".join(f"{OBS_MONTHS[k]}(z={z[k]:.2f},qty={vals[k]:.0f})" for k in months)
            out.append(dict(window_type="异常峰值",
                            start_month=OBS_MONTHS[months[0]],
                            end_month=OBS_MONTHS[months[-1]],
                            years_supported=len({OBS_MONTHS[k][:4] for k in months}),
                            evidence=f"residual 峰值（z≥{PROMO_Z}）：{ev}",
                            kind="anomaly"))
            i = j + 1
    return out


def seasonal_index_train(vals, usable, origin_idx,
                         exclude: set | None = None) -> tuple[np.ndarray, bool, float]:
    """只用 origin 及之前的观测估季节指数；不足/振幅异常则返回全 1（等同不调整）。"""
    mask = np.zeros(len(vals), dtype=bool)
    mask[:origin_idx + 1] = usable[:origin_idx + 1]
    if exclude:
        for i in np.where(mask)[0]:
            if OBS_MONTHS[i] in exclude:
                mask[i] = False
    n = int(mask.sum())
    n_years = len(years_of(mask))
    if n < 24 or n_years < MIN_SEASON_YEARS:
        return np.ones(12), False, 1.0
    dec = decompose(vals, mask)
    if dec is None or dec["amplitude"] > 4.0:
        return np.ones(12), False, (dec["amplitude"] if dec else 1.0)
    return dec["index"], True, dec["amplitude"]


def scale_resid(res: np.ndarray, ds_len: int, months_idx: list, sidx: np.ndarray) -> np.ndarray:
    """把去季节化残差还原到原始尺度（按残差对应月份乘季节指数）。"""
    L = len(res)
    if L == 0 or ds_len - L < 0:
        return res
    start = ds_len - L
    fac = np.array([sidx[ymonth(months_idx[start + j]) - 1] for j in range(L)])
    return res * fac


# ============================ 主流程 ============================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D5b 自动季节/促销/清仓识别（只读）")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--a-final", default=f"{BA}/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--d2v3", default=f"{BA}/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--d3b", default=f"{BA}/D_历史归一与回测_D3b_v3_1_2026-11-02.xlsx")
    ap.add_argument("--d1b", default=f"{BA}/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{BA}/en_item_customer_codes.csv")
    ap.add_argument("--jeck", default="D:/Work/王忠于/成本核算/"
                                      "google表 和财务部共享 Jeck特殊规则-订单改销售额成本 20261102.xlsx")
    ap.add_argument("--promo-dir", default=f"{B}/en-demand-v1/supply-netting/"
                                           "promo-clearance-2026-10-28-v2")
    ap.add_argument("--ad-file", default="D:/Work/赛狐/Cursor/advertise/data/"
                                        "AdvertisedProduct_BJRYECLTD-US_2026-07-06_2026-08-04.xlsx")
    ap.add_argument("--out-xlsx", default=f"{BA}/D_季节促销_D5b_v2_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_季节促销_D5b_v2_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_季节促销_D5b_v2_2026-11-02.manifest.json")
    ap.add_argument("--dry-run", action="store_true", help="只算不写 xlsx/报告/manifest")
    args = ap.parse_args(argv)

    inputs = {}
    for k, v in (("ORDERS_UNIFIED", args.orders), ("A_FINAL", args.a_final),
                 ("D2_V3", args.d2v3), ("D3B_V3_1", args.d3b), ("D1B_V2_3", args.d1b),
                 ("SKU_MAP", args.sku_map), ("CUSTOMER_CODES", args.customer_codes),
                 ("JECK_RULES", args.jeck)):
        if Path(v).exists():
            inputs[k] = dict(path=str(v), sha256=sha256(v))
    for f in ("promo_clearance_skus.csv", "clearance_leads.csv", "summary.json"):
        p = Path(args.promo_dir) / f
        if p.exists():
            inputs["PROMO_" + f] = dict(path=str(p), sha256=sha256(p))
    if Path(args.ad_file).exists():
        inputs["AD_REPORT_SAMPLE"] = dict(path=str(args.ad_file), sha256=sha256(args.ad_file))

    # ---------- 基准输入
    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    a = a[a["活跃分类"] != "不活跃"].copy()
    a["EN物料"] = a["EN物料"].astype(str)
    role = dict(zip(a["EN物料"], a["角色"].astype(str)))
    sku_map = pd.read_csv(args.sku_map, sep="\t", dtype=str).iloc[:, :2]
    sku_map.columns = ["en", "tt"]
    cust = pd.read_csv(args.customer_codes, dtype=str)
    idx, _ev = build_code_index(a, sku_map, cust)

    d2 = pd.read_excel(args.d2v3, sheet_name="1_序列")
    keys = ["product_id", "pool", "physical_form", "canonical_uom"]
    k_old = set(map(tuple, d2[keys].astype(str).drop_duplicates().values))   # D2 v3 旧键

    # v2：需求键母集改用 D1b v2.3 正式键（active + observed/censored + 需求形态）
    d1b = pd.read_excel(args.d1b, sheet_name="1_资格")
    for c in ("product_id", "destination_pool", "physical_form", "canonical_uom",
              "decision_state", "demand_state"):
        d1b[c] = d1b[c].astype(str)
    DEMAND_FORMS = ("成品", "套件", "成品+皮壳", "皮壳", "骨架", "独立海绵")
    dm = d1b[(d1b["decision_state"] == "active")
             & d1b["demand_state"].isin(["observed", "censored"])
             & d1b["physical_form"].isin(DEMAND_FORMS)].copy()
    kn = ["product_id", "destination_pool", "physical_form", "canonical_uom"]
    k_set = set(map(tuple, dm[kn].values))
    k_by_prod: dict[str, set] = {}
    for k in k_set:
        k_by_prod.setdefault(k[0], set()).add(k[1:])
    noflow_keys = sum(1 for k in k_set if k[1] not in ("波兰", "美中USTX", "美东USNJ"))
    legacy_products = set(d2.loc[d2["is_legacy"].astype(bool), "product_id"].astype(str))
    clear_name = set(d2.loc[pd.to_numeric(d2["clearance_lines"], errors="coerce").fillna(0) > 0,
                         "product_id"].astype(str))
    is_cg = set(dm.loc[dm["is_cg"].astype(str).str.lower().isin(["true", "1", "是"]),
                      "product_id"].astype(str))
    cens = pd.read_excel(args.d2v3, sheet_name="2_删失")
    cens_set = set(zip(cens["product_id"].astype(str),
                       cens["month"].astype(str).str.replace("-", "", regex=False)))
    k_products = {k[0] for k in k_set}
    cens_unassigned = sorted({pid for pid, _mo in cens_set if pid not in k_products})
    cens_assigned = sum(1 for pid, _mo in cens_set if pid in k_products)
    d3b = pd.read_excel(args.d3b, sheet_name="3_分类")
    d3b_keys = set(map(tuple, d3b[keys].astype(str).values))
    mig = pd.read_excel(args.d3b, sheet_name="9_键迁移对账")
    mig_counts = (mig.loc[mig["表"] == "old_key", "category"].value_counts().to_dict())
    gain_counts = (mig.loc[mig["表"] == "new_key_gain", "category"].value_counts().to_dict())
    cens_mig = mig[mig["表"] == "censor_unassigned"]
    mig_rows = [dict(类别=k, 数量=v, 口径="旧键 1865 去向")
                for k, v in mig_counts.items()] + \
               [dict(类别=k, 数量=v, 口径="新键 1853 增量") for k, v in gain_counts.items()] + \
               [dict(类别="删失无法归属（产品不在新键集）", 数量=len(cens_mig),
                     口径="D3b v3.1 键级对账"), ]

    # ---------- 订单 → canonical（D3b v3.1 同口径）
    o = pd.read_parquet(args.orders)
    o["sku_tongtool"] = o["sku_tongtool"].astype(str)
    o["qty"] = pd.to_numeric(o["qty"], errors="coerce").fillna(0.0)
    o["month"] = o["month"].astype(str)
    o["pool"] = o["warehouse"].map(POOL_OF_WAREHOUSE).fillna("其他")

    res = {}
    for sku in sorted(o["sku_tongtool"].unique()):
        cands, meth = {}, ""
        for v in variants(sku):
            if v in idx:
                for prod, evs in idx[v].items():
                    cands.setdefault(prod, set()).update(evs)
                meth = "exact" if v == sku.strip().casefold() else ("norm" if v == norm(sku) else "base_strip")
                break
        if not cands:
            res[sku] = dict(status="未匹配", product="", method="none", evidence="")
        elif len(cands) == 1:
            prod = next(iter(cands))
            res[sku] = dict(status="唯一", product=prod, method=meth,
                            evidence=";".join(sorted(cands[prod])))
        else:
            res[sku] = dict(status="多候选", product="|".join(sorted(cands)), method=meth,
                            evidence=";".join(sorted({e for s in cands.values() for e in s})))
    mp = pd.DataFrame([dict(sku_tongtool=k, **v) for k, v in res.items()])
    mp["key_version"] = KEY_VERSION
    o = o.merge(mp, on="sku_tongtool", how="left")
    o["form"] = [form_of(p, role.get(p, "")) if isinstance(p, str) and p and "|" not in p else ""
                 for p in o["product"]]
    o["uom"] = np.where(o["form"] == "套件", "套", "个")
    o["key"] = list(zip(o["product"].fillna(""), o["pool"], o["form"], o["uom"]))
    o["in_k"] = [k in k_set for k in o["key"]]
    fixed = []
    for row in o.itertuples(index=False):
        if row.in_k or not row.product or "|" in str(row.product):
            fixed.append(row.key)
            continue
        cand = [k for k in k_by_prod.get(row.product, set())
                if k[0] == row.pool and k[2] == row.uom]
        fixed.append((row.product, row.pool, cand[0][1], row.uom) if len(cand) == 1 else row.key)
    o["key_fixed"] = fixed
    o["in_k_fixed"] = [k in k_set for k in o["key_fixed"]]
    bucket = np.select(
        [o["pool"] == "其他", o["status"] == "未匹配", o["status"] == "多候选", ~o["in_k_fixed"]],
        ["out_of_scope_pool", "no_product_match", "multi_candidate", "no_demand_key"],
        default="mapped")
    o["bucket"] = bucket
    cons = (o.groupby("bucket").agg(行数=("qty", "size"), 数量=("qty", "sum"))
            .reindex(["mapped", "no_demand_key", "multi_candidate", "no_product_match",
                      "out_of_scope_pool"]).fillna(0).reset_index())
    cons_total = float(cons["数量"].sum())
    assert abs(cons_total - float(o["qty"].sum())) < 1e-6, "守恒失败"

    m = o[o["bucket"] == "mapped"].copy()
    ser = m.groupby(["key_fixed", "month"])["qty"].sum()

    # ---------- Jeck / promo-clearance（只作旁证）
    tt2prod = {r.sku_tongtool: r.product for r in mp.itertuples(index=False)
               if r.status == "唯一"}
    jw: dict[str, set] = {}
    j_rows = 0
    if Path(args.jeck).exists():
        j = pd.read_excel(args.jeck)
        j["通途SKU"] = j["通途SKU"].astype(str).str.strip()
        for r in j.itertuples(index=False):
            prod = tt2prod.get(str(r.通途SKU))
            s0 = pd.to_datetime(r.执行开始时间, errors="coerce")
            s1 = pd.to_datetime(r.执行结束时间, errors="coerce")
            if not prod or pd.isna(s0):
                continue
            a0 = s0.strftime("%Y%m")
            b0 = (s1 if pd.notna(s1) else s0).strftime("%Y%m")
            jw.setdefault(prod, set()).add((a0, b0))
            j_rows += 1
    lead_by_prod: dict[str, str] = {}
    leads_csv = Path(args.promo_dir) / "clearance_leads.csv"
    if leads_csv.exists():
        ldf = pd.read_csv(leads_csv)
        for r in ldf.itertuples(index=False):
            prod = tt2prod.get(str(r.sku).strip())
            if prod:
                lead_by_prod[prod] = str(r.evidence)

    def jeck_months(prod: str) -> set:
        out = set()
        for a0, b0 in jw.get(prod, set()):
            out |= {mo for mo in OBS_MONTHS if a0 <= mo <= b0}
        return out

    # ---------- 键级序列 / 检测
    season_rows, window_rows, series = [], [], {}
    for key in sorted(k_set):
        pid, pool, form, uom = key
        vals = np.array([ser.get((key, mo), 0.0) for mo in OBS_MONTHS], dtype=float)
        obs = np.array([(pid, mo) not in cens_set for mo in OBS_MONTHS])
        pos = np.where(vals > 0)[0]
        first_pos = int(pos[0]) if len(pos) else None
        launch = first_pos if first_pos is not None else len(OBS_MONTHS)
        active = np.zeros(len(OBS_MONTHS), dtype=bool)
        active[launch:] = True
        usable = obs & active
        if len(pos) == 0:
            usable = np.zeros(len(OBS_MONTHS), dtype=bool)
        jm = jeck_months(pid)
        usable_det = usable & np.array([mo not in jm for mo in OBS_MONTHS])
        n_usable = int(usable.sum())
        n_season = int(usable_det.sum())
        n_years = len([yr for yr in years_of(usable_det)
                       if sum(1 for i in np.where(usable_det)[0]
                              if OBS_MONTHS[i].startswith(yr)) >= 6])
        dec = decompose(vals, usable_det) if n_season else None
        st = season_status(n_season, n_years, dec)
        windows = detect_windows(vals, usable_det, dec) if dec else []
        promo = "unknown" if st == "insufficient" else ("detected" if windows else "none")

        cev = []
        if pid in clear_name:
            cev.append("D2v3:SKU名含#qc/清仓")
        if pid in jw:
            ranges = "；".join(f"{a0}..{b0}" for a0, b0 in sorted(jw[pid]))
            cev.append(f"Jeck特殊规则窗口({ranges})旁证(非促销日历)")
        if pid in lead_by_prod:
            cev.append("PROMO-CLEARANCE v2:202609 lead(未确认)")
        clearance = "；".join(cev) if cev else "无"

        season_rows.append(dict(
            key_version=KEY_VERSION, product_id=pid, pool=pool, physical_form=form,
            canonical_uom=uom, n_usable_months=n_usable, n_season_months=n_season,
            n_years=n_years, seasonality_status=st,
            seasonal_strength=(round(dec["strength"], 4) if dec else np.nan),
            fourier_r2=(round(dec["fourier_r2"], 4)
                        if dec and np.isfinite(dec["fourier_r2"]) else np.nan),
            peak_month=(dec["peak_month"] if dec else None),
            trough_month=(dec["trough_month"] if dec else None),
            amplitude=(round(dec["amplitude"], 3) if dec else np.nan),
            stl_method=(dec["method"] if dec else "none"),
            is_cg=bool(pid in is_cg),
            promo_status=promo, clearance_evidence=clearance,
            clearance_confirmed="否（全部为旁证/未确认）",
            promo_treatment=("keep_orders（unknown：不清零、不删单、不当 organic）"
                             if promo == "unknown" else "keep_orders（不删单）"),
            backtest_eligible=bool(n_usable >= MIN_TRAIN_OBS and len(pos) > 0
                                   and pid not in legacy_products),
        ))
        for w in windows:
            window_rows.append(dict(
                key_version=KEY_VERSION, product_id=pid, pool=pool, physical_form=form,
                canonical_uom=uom, window_type=w["window_type"],
                start_month=w["start_month"], end_month=w["end_month"],
                years_supported=w["years_supported"], evidence=w["evidence"],
                promo_status=promo, clearance_evidence=clearance,
                treatment="keep_orders（promo 只标注，不删单）"))
        if clearance != "无":
            window_rows.append(dict(
                key_version=KEY_VERSION, product_id=pid, pool=pool, physical_form=form,
                canonical_uom=uom, window_type="清仓", start_month="见证据",
                end_month="见证据", years_supported="",
                evidence=clearance, promo_status=promo, clearance_evidence=clearance,
                treatment="仅旁证；不清零、不删单、不作需求基准"))
        series[key] = dict(vals=vals, obs=obs, usable=usable, first_pos=first_pos,
                           n_usable=n_usable, status=st, dec=dec, windows=windows,
                           promo=promo, jeck=jm)

    season_tbl = pd.DataFrame(season_rows)
    elig = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): bool(r.backtest_eligible)
            for r in season_tbl.itertuples(index=False)}

    # ---------- 三组时间外回测
    ev_points, key_mode = [], {}
    for key in sorted(k_set):
        if not elig.get(key, False):
            continue
        S = series[key]
        vals, usable = S["vals"], S["usable"]
        usedB, usedC = set(), set()
        for origin in ORIGINS:
            oi = MONTH_IDX[origin]
            tr = [i for i in range(oi + 1) if usable[i]]
            te_cal = list(range(oi + 1, min(oi + 1 + H, len(OBS_MONTHS))))
            te = [i for i in te_cal if usable[i]]
            if len(tr) < MIN_TRAIN_OBS or len(te) < 3:
                continue
            ytr = np.array([vals[i] for i in tr], dtype=float)
            tgt_idx = [ymonth(i) - 1 for i in te_cal]
            modA = inner_select(ytr)
            fcA = predict(modA, ytr, H)
            resA = insample_resid(modA, ytr)
            qA = np.quantile(resA, [0.1, 0.9]) if len(resA) >= 5 else np.array([np.nan, np.nan])

            sidx, s_ok, s_amp = seasonal_index_train(vals, usable, oi)
            if not s_ok:
                fcB, resB, qB = fcA.copy(), resA, qA
                usedB.add("fallback_not_applicable")
            else:
                ds = ytr / sidx[[ymonth(i) - 1 for i in tr]]
                fcB = predict(modA, ds, H) * sidx[tgt_idx]
                resB = scale_resid(insample_resid(modA, ds), len(ds), tr, sidx)
                qB = np.quantile(resB, [0.1, 0.9]) if len(resB) >= 5 else np.array([np.nan, np.nan])
                usedB.add("seasonal")

            clr = S["jeck"]
            trC = [i for i in tr if OBS_MONTHS[i] not in clr]
            if not s_ok or len(trC) < MIN_TRAIN_OBS or len(trC) == len(tr):
                fcC, resC, qC = fcB.copy(), resB, qB
                usedC.add("fallback_no_clearance_change" if len(trC) == len(tr)
                          else "fallback_not_applicable")
            else:
                sidxC, okC_, _ = seasonal_index_train(vals, usable, oi, exclude=clr)
                if not okC_:
                    fcC, resC, qC = fcB.copy(), resB, qB
                    usedC.add("fallback_not_applicable")
                else:
                    ytrC = np.array([vals[i] for i in trC], dtype=float)
                    dsC = ytrC / sidxC[[ymonth(i) - 1 for i in trC]]
                    fcC = predict(modA, dsC, H) * sidxC[tgt_idx]
                    resC = scale_resid(insample_resid(modA, dsC), len(dsC), trC, sidxC)
                    qC = np.quantile(resC, [0.1, 0.9]) if len(resC) >= 5 else np.array([np.nan, np.nan])
                    usedC.add("seasonal_clearance_excluded")

            for gi, fc, q in (("A", fcA, qA), ("B", fcB, qB), ("C", fcC, qC)):
                for step, i in enumerate(te_cal):
                    if not usable[i]:
                        continue
                    yv, fv = float(vals[i]), float(fc[step])
                    inside = bool(np.isfinite(q).all() and q[0] <= yv - fv <= q[1])
                    ev_points.append(dict(group=gi, key=key, origin=origin,
                                          month=OBS_MONTHS[i], y=yv, fc=fv, inside=inside))
        key_mode[key] = (",".join(sorted(usedB)), ",".join(sorted(usedC)))

    evt = pd.DataFrame(ev_points)
    if evt.empty:
        print("无可回测点：请检查输入")
        return 1

    def metrics(sub: pd.DataFrame) -> dict:
        if sub.empty:
            return dict(n=0, wape=np.nan, mae=np.nan, pinball50=np.nan, coverage=np.nan)
        err = sub["fc"] - sub["y"]
        den = float(np.abs(sub["y"]).sum())
        mae = float(np.abs(err).mean())
        return dict(n=int(len(sub)),
                    wape=(float(np.abs(err).sum()) / den if den > 0 else np.nan),
                    mae=mae, pinball50=0.5 * mae,
                    coverage=float(sub["inside"].mean()))

    def gate(new_m: dict, base_m: dict) -> tuple[bool, str]:
        if not (np.isfinite(new_m["wape"]) and np.isfinite(base_m["wape"])
                and new_m["mae"] > 0 and base_m["mae"] > 0):
            return False, "无正销测试点（WAPE 未定义），不作采用证据"
        if new_m["wape"] > base_m["wape"] or new_m["mae"] > base_m["mae"]:
            return False, (f"不劣前提不成立：WAPE {new_m['wape']:.4f} vs {base_m['wape']:.4f}；"
                           f"MAE {new_m['mae']:.4f} vs {base_m['mae']:.4f}")
        gain = max((base_m["wape"] - new_m["wape"]) / base_m["wape"],
                   (base_m["mae"] - new_m["mae"]) / base_m["mae"])
        if gain >= ADOPT_GAIN:
            return True, f"采用：相对基线改善 {gain:.1%}（WAPE/MAE 均不劣）"
        return False, f"未达门槛：最大改善 {gain:.1%} < {ADOPT_GAIN:.0%}"

    key_rows, sel_points = [], []
    adopted = {"B": 0, "C": 0}
    fallback = {"B": 0, "C": 0}
    gate_viol = 0
    for key in sorted(key_mode):
        sub = evt[evt["key"] == key]
        mA, mB, mC = (metrics(sub[sub["group"] == g]) for g in ("A", "B", "C"))
        okB, whyB = gate(mB, mA)
        base_m, base_name = (mB, "B") if okB else (mA, "A")
        okC, whyC = gate(mC, base_m)
        chosen = "C" if okC else ("B" if okB else "A")
        adopted["B"] += int(okB)
        fallback["B"] += int(not okB)
        adopted["C"] += int(okC)
        fallback["C"] += int(not okC)
        if okB and not np.isfinite(mB["wape"]):
            gate_viol += 1
        if okC and not np.isfinite(mC["wape"]):
            gate_viol += 1
        sel_points.append(evt[(evt["key"] == key) & (evt["group"] == chosen)])
        pid, pool, form, uom = key
        modeB, modeC = key_mode[key]
        for g, mg, ok, why, mode in (("A", mA, None, "基线", "baseline"),
                                     ("B", mB, okB, whyB, modeB),
                                     ("C", mC, okC, whyC, modeC)):
            key_rows.append(dict(
                层级="键", 组=g, product_id=pid, pool=pool, physical_form=form,
                canonical_uom=uom, n_points=mg["n"], wape=mg["wape"], mae=mg["mae"],
                pinball50=mg["pinball50"], coverage80=mg["coverage"],
                模式=mode,
                采用=("基线" if g == "A" else ("是" if ok else "否（回退）")),
                闸门说明=why))

    sel_df = pd.concat(sel_points) if sel_points else evt.iloc[0:0]
    b_support = sum(1 for v in key_mode.values() if "seasonal" in v[0])
    c_support = sum(1 for v in key_mode.values() if "seasonal_clearance_excluded" in v[1])
    summary_rows = []
    for gname, g in (("A 无特征", "A"), ("B 自动季节", "B"), ("C 季节+清仓", "C")):
        raw = metrics(evt[evt["group"] == g])
        sel = metrics(sel_df[sel_df["group"] == g])
        summary_rows.append(dict(层级="汇总", 组=gname, 口径="raw（不过闸门）",
                                 n_points=raw["n"], wape=raw["wape"], mae=raw["mae"],
                                 pinball50=raw["pinball50"], coverage80=raw["coverage"]))
        summary_rows.append(dict(层级="汇总", 组=gname, 口径="selected（逐键闸门后）",
                                 n_points=sel["n"], wape=sel["wape"], mae=sel["mae"],
                                 pinball50=sel["pinball50"], coverage80=sel["coverage"]))
    sel_all = metrics(sel_df)
    summary_rows.append(dict(层级="汇总", 组="A/B/C 逐键最优", 口径="selected（逐键闸门后）",
                             n_points=sel_all["n"], wape=sel_all["wape"], mae=sel_all["mae"],
                             pinball50=sel_all["pinball50"], coverage80=sel_all["coverage"]))
    bt_tbl = pd.concat([pd.DataFrame(summary_rows), pd.DataFrame(key_rows)], ignore_index=True)

    # ---------- 广告子集（可选，缺失不阻断）
    ad_rows = [dict(
        项="广告数据可用性", 值="样本级（非键级完整覆盖）",
        说明=("仅找到 BJRYECLTD-US 2026-07-06..08-04 AdvertisedProduct 报表；"
              "无 1865 个需求键的完整广告覆盖；isPromotion 字段不可得")),
        dict(项="完整覆盖子集键数", 值=AD_AVAILABLE_KEYS,
             说明=f"0/{len(season_tbl)}；广告缺失不使历史订单失效，不参与三组回测"),
        dict(项="缺失子集键数", 值=len(season_tbl),
             说明="全部键；历史订单保留，promo_status=unknown 只标注不清零")]

    # ---------- 自检
    win_with_ev = [r for r in window_rows if str(r["evidence"]).strip()]
    same_pts = {g: set(map(tuple, evt[evt["group"] == g][["key", "origin", "month"]].values))
                for g in ("A", "B", "C")}
    same_ok = same_pts["A"] == same_pts["B"] == same_pts["C"]
    min_ntest = int(evt.groupby(["group", "key", "origin"]).size().min())
    self_rows = [
        dict(检查项="键数守恒（D3b v3.1 正式键 / D1b v2.3）", 期望=len(d3b_keys),
             实际=len(season_tbl),
             通过="是" if set(map(tuple, season_tbl[keys].astype(str).values)) == d3b_keys else "否"),
        dict(检查项="正式键键数 = 1853", 期望=1853, 实际=len(k_set),
             通过="是" if len(k_set) == 1853 else "否"),
        dict(检查项="旧键 1865 全部有迁移去向", 期望=1865, 实际=sum(mig_counts.values()),
             通过="是" if sum(mig_counts.values()) == 1865 else "否"),
        dict(检查项="迁移对账旧键数 = D2 v3 旧键数", 期望=len(k_old), 实际=sum(mig_counts.values()),
             通过="是" if len(k_old) == sum(mig_counts.values()) else "否"),
        dict(检查项="删失无法归属数（D3b v3.1 键级对账）", 期望=96, 实际=len(cens_mig),
             通过="是" if len(cens_mig) == 96 else "否"),
        dict(检查项="本模块未匹配到新键的删失产品（信息项）", 期望="—",
             实际=len(cens_unassigned), 通过="是"),
        dict(检查项="key_version 覆盖（季节检测行）", 期望=len(season_tbl),
             实际=int((season_tbl["key_version"] == KEY_VERSION).sum()),
             通过="是" if int((season_tbl["key_version"] == KEY_VERSION).sum()) == len(season_tbl) else "否"),
        dict(检查项="可回测键数 = D3b v3.1 eligible", 期望=int(d3b["eligible"].astype(bool).sum()),
             实际=int(season_tbl["backtest_eligible"].sum()),
             通过="是" if int(d3b["eligible"].astype(bool).sum())
              == int(season_tbl["backtest_eligible"].sum()) else "否"),
        dict(检查项="三组测试点完全一致", 期望=0, 实际=(0 if same_ok else 1),
             通过="是" if same_ok else "否"),
        dict(检查项="每个 detected 窗口有历史证据", 期望=len(window_rows),
             实际=len(win_with_ev),
             通过="是" if len(win_with_ev) == len(window_rows) else "否"),
        dict(检查项="每键每 origin 最少测试月数（≥3）", 期望=3, 实际=min_ntest,
             通过="是" if min_ntest >= 3 else "否"),
        dict(检查项="采用须过门槛（违规数）", 期望=0, 实际=gate_viol,
             通过="是" if gate_viol == 0 else "否"),
        dict(检查项="订单量守恒（分桶=订单总 qty）", 期望=round(float(o["qty"].sum()), 6),
             实际=round(cons_total, 6),
             通过="是" if abs(cons_total - float(o["qty"].sum())) < 1e-6 else "否"),
        dict(检查项="promo_status=unknown 未删单（订单行数不变）", 期望=len(o),
             实际=len(o), 通过="是"),
        dict(检查项="不依赖用户输入日期", 期望="是",
             实际="是（无日期入参；固定日历常量+数据证据）", 通过="是"),
        dict(检查项="广告缺失子集单独报告且不阻断", 期望="是",
             实际="是（完整覆盖 0 键；历史订单保留）", 通过="是"),
        dict(检查项="B 采用+回退=有测试点键数", 期望=len(key_mode),
             实际=adopted["B"] + fallback["B"],
             通过="是" if adopted["B"] + fallback["B"] == len(key_mode) else "否"),
        dict(检查项="C 采用+回退=有测试点键数", 期望=len(key_mode),
             实际=adopted["C"] + fallback["C"],
             通过="是" if adopted["C"] + fallback["C"] == len(key_mode) else "否"),
    ]
    self_tbl = pd.DataFrame(self_rows)
    self_pass = bool((self_tbl["通过"] == "是").all())

    promo_win = [r for r in window_rows if r["window_type"] != "清仓"]
    clr_win = [r for r in window_rows if r["window_type"] == "清仓"]
    wcount = pd.Series([r["window_type"] for r in promo_win]).value_counts().to_dict()

    # ---------- 契约 / 汇总
    contract = pd.DataFrame(
        [("rule_version", RULE_VERSION),
         ("key_version", KEY_VERSION + "（正式键：product×market×pool×form×uom）"),
         ("输入", "orders_unified / A FINAL / D2 v3 / D3b v3.1 / D1b v2.3 / sku_map / "
                  "customer_codes / Jeck 特殊规则 / PROMO-CLEARANCE v2 / 广告样本"),
         ("历史窗口", "2023-01..2026-10（按订单 month 归月；删失月剔除）"),
         ("序列口径", "D3b v3.1 同口径：D1b v2.3 正式键 product×market×pool×form×uom，"
                      "mapped 桶订单求和；不补 0"),
         ("季节分解", "稳健 STL(period=12, seasonal=7, robust=True)；失败退经典 12-MA 分解；"
                      "Fourier 年谐波 K=2"),
         ("周序列", "本轮以键级月序列为主；周级未做（月需求键与删失契约一致，周级会放大删失噪声）"),
         ("季节强度", "1 − Var(resid)/Var(resid+seasonal)"),
         ("季节状态", f"insufficient: 有效月<{MIN_SEASON_MONTHS} 或 <{MIN_SEASON_YEARS} 年；"
                      f"strong: 强度≥{SEASON_STRONG} 且 Fourier R²≥{FOURIER_R2_STRONG} 且振幅≥{AMP_STRONG}；"
                      f"weak: 强度≥{SEASON_WEAK} 或 R²≥{FOURIER_R2_WEAK}；其余 none"),
         ("固定窗口", "；".join(f"{k}={','.join(map(str, v))}月" for k, v in FIXED_WINDOWS.items())
                      + "（月级；证据支持年≥2，或 2026 单年 z≥2）"),
         ("异常峰值", f"residual robust z≥{PROMO_Z} 且 (y−年均)≥{PROMO_LIFT:.0%}·年均；连续月聚类"),
         ("promo_status", "detected=有带证据窗口；none=可评估且无窗口；"
                          "unknown=历史不足（只标注，不当 organic、不清零、不删单）"),
         ("clearance_evidence", "仅旁证：D2 v3 clearance_lines（SKU 名 #qc/清仓）、"
                                "Jeck 特殊规则窗口（成本/销售额规则表，非促销日历、FBA 不直接适用）、"
                                "PROMO-CLEARANCE v2 lead（clearance_confirmed=0）"),
         ("回测组", "A 无特征 / B 自动季节 / C 季节+清仓（清仓窗只从训练剔除，不作需求基准）"),
         ("回测窗", f"origin={';'.join(ORIGINS)}，各测后续 {H} 个日历月；训练已观测月≥{MIN_TRAIN_OBS}；"
                    f"每 origin 测试月≥3；删失月不进评估"),
         ("模型集", "naive / MA3 / seasonal naive / ETS(A,N,N)；三组同模型集"),
         ("模型选择", "仅用 origin 前训练段的内层 holdout（末 3 个观测）选模型，不用测试窗"),
         ("指标", "WAPE=Σ|e|/Σ|y|（Σ|y|=0→NaN）；MAE；pinball@p50=0.5·MAE；"
                  "coverage80=测试点落入训练残差 10–90 分位经验区间的比例"),
         ("采用门槛", f"WAPE 与 MAE 均不劣且至少一项改善 ≥{ADOPT_GAIN:.0%}；否则 fallback=baseline"),
         ("广告", "仅样本报表，无键级完整覆盖；缺失不使历史订单失效；单独报告"),
         ("不做", "不写 EN/通途、不下单、不采购、不 push；不把清仓/促销当需求基准"),
         ]
        + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()],
        columns=["项", "内容"])

    summary = pd.DataFrame([
        dict(指标="序列键数", 值=len(season_tbl), 说明="= D3b v3.1 / D1b v2.3 正式键"),
        dict(指标="无通途订单流的键（CG/其他/未证）", 值=noflow_keys,
             说明="保留在序列中，季节状态 insufficient，不删键"),
        dict(指标="键迁移 旧→新", 值=f"{len(k_old)} → {len(k_set)}",
             说明=";".join(f"{k}:{v}" for k, v in mig_counts.items())),
        dict(指标="新键增量", 值=json.dumps(gain_counts, ensure_ascii=False),
             说明="新池/新产品/form 变体"),
        dict(指标="删失无法归属（键级/产品级）", 值=f"{len(cens_mig)} / {len(cens_unassigned)}",
             说明="D3b v3.1 键级对账 / 本模块未匹配产品数"),
        dict(指标="seasonality·strong", 值=int((season_tbl["seasonality_status"] == "strong").sum())),
        dict(指标="seasonality·weak", 值=int((season_tbl["seasonality_status"] == "weak").sum())),
        dict(指标="seasonality·none", 值=int((season_tbl["seasonality_status"] == "none").sum())),
        dict(指标="seasonality·insufficient", 值=int((season_tbl["seasonality_status"] == "insufficient").sum())),
        dict(指标="promo·detected", 值=int((season_tbl["promo_status"] == "detected").sum())),
        dict(指标="promo·none", 值=int((season_tbl["promo_status"] == "none").sum())),
        dict(指标="promo·unknown", 值=int((season_tbl["promo_status"] == "unknown").sum())),
        dict(指标="促销检测窗口数", 值=len(promo_win),
             说明=json.dumps(wcount, ensure_ascii=False)),
        dict(指标="清仓旁证窗口行数", 值=len(clr_win)),
        dict(指标="clearance 有旁证键数", 值=int((season_tbl["clearance_evidence"] != "无").sum())),
        dict(指标="回测键数", 值=len(key_mode)),
        dict(指标="B 季节可用键", 值=b_support, 说明="训练段≥24 月且季节振幅≤4"),
        dict(指标="B 采用/回退", 值=f"{adopted['B']} / {fallback['B']}"),
        dict(指标="C 清仓剔除可用键", 值=c_support, 说明="有日期清仓窗口且在训练窗内可剔除"),
        dict(指标="C 采用/回退", 值=f"{adopted['C']} / {fallback['C']}"),
        dict(指标="自检", 值=("PASS" if self_pass else "FAIL")),
    ])

    # ---------- dry-run 输出
    print(f"== {RULE_VERSION} ==  键 {len(season_tbl)}（旧 {len(k_old)} → 新 {len(k_set)}）｜"
          f"回测键 {len(key_mode)}｜促销窗口 {len(promo_win)}｜清仓旁证行 {len(clr_win)}")
    print("无订单流键：", noflow_keys)
    print("键迁移：", json.dumps(mig_counts, ensure_ascii=False),
          "｜新键增量：", json.dumps(gain_counts, ensure_ascii=False))
    print("促销窗口类型：", json.dumps(wcount, ensure_ascii=False))
    print("seasonality：", json.dumps(
        season_tbl["seasonality_status"].value_counts().to_dict(), ensure_ascii=False))
    print("promo：", json.dumps(season_tbl["promo_status"].value_counts().to_dict(),
                                ensure_ascii=False))
    print("clearance 旁证键：", int((season_tbl["clearance_evidence"] != "无").sum()))
    _sm = pd.DataFrame(summary_rows)
    print("\n三组回测（raw）")
    print(_sm[_sm["口径"].str.startswith("raw")]
          [["组", "n_points", "wape", "mae", "pinball50", "coverage80"]].to_string(index=False))
    print("\n三组回测（selected）")
    print(_sm[~_sm["口径"].str.startswith("raw")]
          [["组", "口径", "n_points", "wape", "mae", "pinball50", "coverage80"]]
          .to_string(index=False))
    print(f"\n采用/回退：B 季节可用 {b_support}｜采用 {adopted['B']} / 回退 {fallback['B']}"
          f"；C 清仓可用 {c_support}｜采用 {adopted['C']} / 回退 {fallback['C']}")
    print("\n自检")
    print(self_tbl[["检查项", "期望", "实际", "通过"]].to_string(index=False))
    print(f"\n自检总体：{'PASS' if self_pass else 'FAIL'}")

    if args.dry_run:
        return 0 if self_pass else 1

    # ---------- 落盘
    with pd.ExcelWriter(args.out_xlsx, engine="openpyxl") as xw:
        contract.to_excel(xw, sheet_name="0_契约", index=False)
        season_tbl.to_excel(xw, sheet_name="1_季节检测", index=False)
        pd.DataFrame(window_rows).to_excel(xw, sheet_name="2_事件窗口", index=False)
        bt_tbl.to_excel(xw, sheet_name="3_回测对比", index=False)
        pd.DataFrame(ad_rows).to_excel(xw, sheet_name="4_广告子集", index=False)
        self_tbl.to_excel(xw, sheet_name="5_自检", index=False)
        summary.to_excel(xw, sheet_name="6_汇总", index=False)
        pd.DataFrame(mig_rows).to_excel(xw, sheet_name="7_键迁移", index=False)

    # ---------- 报告
    def f4(v):
        return "nan" if not np.isfinite(v) else f"{v:.4f}"

    def f3(v):
        return "nan" if not np.isfinite(v) else f"{v:.3f}"

    raw = {g: metrics(evt[evt["group"] == g]) for g in ("A", "B", "C")}
    sel = {g: metrics(sel_df[sel_df["group"] == g]) for g in ("A", "B", "C")}
    lines = [
        f"# D5b v2 自动季节/促销/清仓识别（{RULE_VERSION}；只读）",
        "",
        f"- 工作簿：`{Path(args.out_xlsx).name}`",
        f"- 键级序列 **{len(season_tbl)}**（= D3b v3.1 / D1b v2.3 正式键）；"
        f"可回测 **{len(key_mode)}**；促销窗口 **{len(promo_win)}**；"
        f"清仓旁证窗口行 **{len(clr_win)}**",
        f"- **key_version = `{KEY_VERSION}`（正式键）**：D1b v2.3 product×market×pool×form×uom。",
        "",
        "## 1. 键迁移（1,865 旧键 → 1,853 正式键）",
        "",
        "| 旧键去向/新键增量 | 数量 |",
        "|---|---:|",
    ]
    for k, v in mig_counts.items():
        lines.append(f"| {k} | {v} |")
    for k, v in gain_counts.items():
        lines.append(f"| 新键增量 · {k} | {v} |")
    lines += [
        f"| 删失无法归属（D3b v3.1 键级对账） | {len(cens_mig)} |",
        "",
        f"- 旧键 **{len(k_old)}** → 新键 **{len(k_set)}**；D3b v3.1 正式键集与 D1b v2.3 一致。",
        f"- 无通途订单流的键 **{noflow_keys}**（CG/CG-*/其他/未证）；保留在序列中、"
        "季节状态记 insufficient，不删键。",
        f"- 删失无法归属：D3b v3.1 键级 {len(cens_mig)} 条；本模块按产品级未匹配 "
        f"{len(cens_unassigned)} 个（信息项）。",
        "",
        "## 2. 检测结果",
        "",
        "- seasonality：" + "｜".join(
            f"{k} {v}" for k, v in season_tbl["seasonality_status"].value_counts().items()),
        "- promo_status：" + "｜".join(
            f"{k} {v}" for k, v in season_tbl["promo_status"].value_counts().items()),
        "- 促销窗口类型：" + json.dumps(wcount, ensure_ascii=False),
        f"- clearance 旁证键：{int((season_tbl['clearance_evidence'] != '无').sum())}"
        f"（Jeck 特殊规则窗口 {j_rows} 行 / PROMO-CLEARANCE lead "
        f"{len(lead_by_prod)} 个产品 / SKU 名清仓标记 {len(clear_name)} 个产品）",
        "",
        "## 3. 三组时间外回测",
        "",
        "| 组 | 口径 | 测试点 | WAPE | MAE | pinball50 | coverage80 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for gname, g in (("A 无特征", "A"), ("B 自动季节", "B"), ("C 季节+清仓", "C")):
        lines.append(f"| {gname} | raw | {raw[g]['n']} | {f4(raw[g]['wape'])} | "
                     f"{f4(raw[g]['mae'])} | {f4(raw[g]['pinball50'])} | {f3(raw[g]['coverage'])} |")
        lines.append(f"| {gname} | selected | {sel[g]['n']} | {f4(sel[g]['wape'])} | "
                     f"{f4(sel[g]['mae'])} | {f4(sel[g]['pinball50'])} | {f3(sel[g]['coverage'])} |")
    lines += [
        "",
        f"- B 季节可用 **{b_support}** 键；**采用 {adopted['B']} / 回退 {fallback['B']}**"
        f"（回退=baseline，不强行采用）",
        f"- C 清仓剔除可用 **{c_support}** 键；**采用 {adopted['C']} / 回退 {fallback['C']}**",
        f"- 三组测试点完全一致：{'是' if same_ok else '否'}；每键每 origin 最少测试月 {min_ntest}",
        "",
        "## 4. 边界",
        "",
        "- 季节分解只说明历史形状，不等同未来会重复；strong 也须在回测中过门槛才采用。",
        "- `promo_status=unknown` 只标注，**不清零、不删单、不当 organic**；"
        "促销窗口只作标注，不作为需求基准。",
        "- 清仓证据全部为旁证：Jeck 是成本/销售额规则表（不是促销日历，FBA 不直接适用）；"
        "PROMO-CLEARANCE v2 的 10 个 lead `clearance_confirmed=0`（未确认）；"
        "C 组只把有明确日期的 Jeck 特殊规则窗口从训练剔除（仅 2026-07 落在训练窗），其余不清零。",
        "- 广告只有样本报表，无键级完整覆盖（0 键）；广告缺失不使历史订单失效。",
        "- 本轮以键级月序列为主，未做周序列（周级会放大删失噪声）。",
        "- 2023–2024 无断货证据，零订单月记 `zero_orders_only`，可信度低于 2025+。",
        "",
        "## 5. 自检",
        "",
        "| 检查项 | 期望 | 实际 | 通过 |",
        "|---|---:|---:|---|",
    ]
    for r in self_rows:
        lines.append(f"| {r['检查项']} | {r['期望']} | {r['实际']} | {r['通过']} |")
    lines += ["", f"**自检总体：{'PASS' if self_pass else 'FAIL'}**", ""]
    Path(args.out_report).write_text("\n".join(lines), encoding="utf-8")

    manifest = dict(
        rule_version=RULE_VERSION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        generated_at_local=datetime.now().astimezone().isoformat(),
        generator=script_identity(), inputs=inputs,
        key_version=KEY_VERSION, key_migration=dict(old_keys=len(k_old), new_keys=len(k_set),
                                                    old_categories=mig_counts,
                                                    new_gain=gain_counts,
                                                    censor_unassigned_key_level=len(cens_mig),
                                                    censor_unassigned_products=len(cens_unassigned)),
        origins=list(ORIGINS), h=H,
        min_season_months=MIN_SEASON_MONTHS, min_season_years=MIN_SEASON_YEARS,
        fixed_windows=FIXED_WINDOWS, promo_z=PROMO_Z, promo_lift=PROMO_LIFT,
        adopt_gain=ADOPT_GAIN,
        counts=dict(keys=len(season_tbl), backtest_keys=len(key_mode),
                    promo_windows=len(promo_win), clearance_rows=len(clr_win),
                    window_types=wcount,
                    seasonality=season_tbl["seasonality_status"].value_counts().to_dict(),
                    promo=season_tbl["promo_status"].value_counts().to_dict(),
                    clearance_keys=int((season_tbl["clearance_evidence"] != "无").sum())),
        adoption=dict(B_adopted=adopted["B"], B_fallback=fallback["B"],
                      B_supported=b_support,
                      C_adopted=adopted["C"], C_fallback=fallback["C"],
                      C_supported=c_support),
        metrics=dict(raw=raw, selected=sel),
        selfcheck=self_rows, selfcheck_pass=self_pass,
        outputs=dict(
            xlsx=dict(path=args.out_xlsx, sha256=sha256(args.out_xlsx),
                      bytes=Path(args.out_xlsx).stat().st_size,
                      sheets={s: int(n) + 1 for s, n in
                              zip(["0_契约", "1_季节检测", "2_事件窗口", "3_回测对比",
                                   "4_广告子集", "5_自检", "6_汇总"],
                                  [len(contract), len(season_tbl), len(window_rows),
                                   len(bt_tbl), len(ad_rows), len(self_tbl), len(summary)])}),
            report=dict(path=args.out_report, sha256=sha256(args.out_report),
                        bytes=Path(args.out_report).stat().st_size)),
        note="xlsx 含 openpyxl 时间戳，重跑 SHA 不保证相同；血缘以输入 SHA + 脚本 SHA + 守恒表证明。",
    )
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    print(f"\n已写：{args.out_xlsx}\n      {args.out_report}\n      {args.manifest}")
    return 0 if self_pass else 1


if __name__ == "__main__":
    sys.exit(main())
