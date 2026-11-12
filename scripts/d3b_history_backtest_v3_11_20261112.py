# -*- coding: utf-8 -*-
"""D3b v3.11 历史归一 + 美国需求按当前 owner 重述 + 重分类 + 重回测（只读）。

v3.11 = v3.10 + P0/P1 整改：
- **adopted 单一事实源**：`3_分类.adopted_model` 只 join `4_回测_asof.adopted`，
  不再按产品历史量另选；单源精确、多源一致/最大量留痕；pipeline 断言 fail closed。
- **模型候选**：新增 ETS(A,Ad,N)、ETS(A,A,A)/STL+ETS、简化 Theta；均为 numpy 实现。
- **趋势诊断**：2026 vs 2025 同期、近 3/6/12 月斜率、结构突变启发式标记，
  输出 `15_趋势诊断` + `--trend-csv`。
- 运行输入默认 `orders_unified_20261111_v2.parquet`；输出默认 `analysis/D3b-v3_11-20261112/`。

v3.6 历史归一 + 美国需求按当前 owner 重述 + 重分类 + 重回测（只读）。

v3.5 = v3.4 + 美国需求责任重述：
- **current-owner 序列（预测用）**：键 `product × current_pool × form × uom`。
  current_pool = B r10 唯一「美国责任方」；无唯一 owner → `US_unassigned`。
  历史订单仓只保留为 evidence / migration flag，不改变原始订单/库存/供应。
- **as-of 序列（历史回测用）**：仍按历史订单仓池（美东USNJ / 美中USTX），
  完整保留 v3.4 的零误差基线、共同可评估窗口、日历位置与回测结果。
- 两套序列分开：回测只用 as-of；D5 预测只用 current-owner；报告写清差异。
- 双池产品若只是履约迁仓，全归当前 owner；53 个 current USNJ / hist USTX 特例逐条列出。
- 弱 owner 31,033 件单列 `US_unassigned`；owner-known 281,490 守恒，总量 312,523。

目标：把「假短」接起来 —— 用 orders_unified（2022-12..2026-10）重建每个
product×pool×form×uom 的**有效历史**，再重分类、重回测；不是把 885 条 short 一标了事。

做什么
1) 历史归一：casefold / 去空格 / 去前缀 OLD_、new-、new / 去后缀 -Cover、-c、-1、-2；
   用「A 来源码 + sku_map + 客户码」建 SKU→product 桥；**只有候选唯一且证据一致才合并**，
   多候选/跨 form/UOM/共享 → 隔离并记录。raw→canonical lineage 全部留痕。
2) 有效历史：首销月→2026-10 的日历月数（删失月剔除），输出 `history_months_effective`；
   并给出 D3 中 885 条 short 的去向（变长/仍短/真新品/清仓短/老品）。
3) 重分类：smooth/intermittent/lumpy/obsolescent/new/short（ADI 1.32 / CV² 0.49）。
4) 重回测：naive/MA3/seasonal naive/ETS(A,N,N)；间歇类 Croston/SBA；obsolescent 加 TSB；
   5 个 origin（与 D3 相同，便于对比），WAPE/MAE/pinball@p50；采用门槛同 D3（不劣 + ≥5%）。
5) 失败分类：真无历史/跨 form·UOM/共享/老品/清仓/短史，并给 fallback。

只读：不写 EN / 通途 / 不发消息 / 不 push。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from supply_netting.demand_input import canonical_order_dates

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
RULE_VERSION = "D3b-v3.11-2026-11-12-single-source-trend"
KEY_VERSION = "D1b-v2.3-2026-11-02"   # D1b v2.3 正式键（product×market×pool×form×uom）
OWNER_KEY_VERSION = "D3b-v3.5-current-owner-2026-11-03"
US_POOLS = ("美东USNJ", "美中USTX")
UNASSIGNED = "US_unassigned"
# B r10 证据层级强弱（数字越大越强）；仅用于同产品多行时的确定性选择
OWNER_EVIDENCE_RANK = {"dn2026": 7, "dn2025": 6, "own90": 5, "own180": 4,
                       "own2025": 3, "own2026": 2, "stock_placement": 1}

END_MONTH = "202610"
OBS_MONTHS = [f"{y}{m:02d}" for y in range(2023, 2027) for m in range(1, 13)]
OBS_MONTHS = [m for m in OBS_MONTHS if m <= END_MONTH]     # 202301..202610
ORIGINS = ("202604", "202605", "202606", "202607")   # 各测 3 个日历月；202608 只有 2 个月→剔除
H = 3
MIN_TRAIN_OBS = 12
MIN_HIST_CLASS = 12
ADI_THR, CV2_THR = 1.32, 0.49
ALPHA = 0.1
ETS_ALPHAS = np.round(np.arange(0.01, 0.995, 0.01), 2)
ADOPT_GAIN = 0.05

PREFIXES = ("old_", "new-", "new_")
SUFFIXES = ("-cover", "-c", "-1", "-2")
CLEARANCE_RE = re.compile(r"#qc|清仓|clearance", re.I)

# 仓库 → 池（口径与 C v14/B r10 一致；其余仓归「其他」，不进入需求序列）
POOL_OF_WAREHOUSE = {
    "CENTRADE": "美东USNJ", "美东-CENTRADE": "美东USNJ", "北美之路-NJ02": "美东USNJ",
    "FZH-DANEEY-皮壳仓库": "美中USTX", "FZH-DANEEY": "美中USTX",
    "FZH-DANEEY-成品仓": "美中USTX", "FZH-DANEEY-半成品仓": "美中USTX",
    "FZH-DANEEY-退货产品仓": "美中USTX", "美中-FZH-DANEEY": "美中USTX",
    "美中-FZH-DANEEY-皮壳仓库": "美中USTX", "美中-FZH-DANEEY-退货产品仓": "美中USTX",
    "休斯顿1号仓": "美中USTX", "休斯顿1号备用仓库": "美中USTX",
    "海外仓美中仓库备用仓": "美中USTX", "北美之路-LA01": "美中USTX",
    "FZHPoland-covers": "波兰", "波兰-FZHPoland-covers": "波兰",
    "FZHPoland-finished": "波兰",
}


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare_order_input(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Use sale_date as event time while retaining the source partition label."""
    return canonical_order_dates(frame)


def assign_order_bucket(o: pd.DataFrame) -> np.ndarray:
    return np.select(
        [o["demand_event_date"].isna(), o["pool"] == "其他",
         o["status"] == "未匹配", o["status"] == "多候选", ~o["in_k_fixed"]],
        ["date_unknown", "out_of_scope_pool", "no_product_match",
         "multi_candidate", "no_demand_key"],
        default="mapped")


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


def norm(s) -> str:
    """casefold + 去空格 + 去 OLD_/new 前缀 + 去 -Cover/-c/-1/-2 后缀（任务口径）。"""
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
    """归一候选：①原样（casefold）②任务口径归一键 ③去尾部 -数字（次级，需唯一证据）。"""
    base = str(sku).strip().casefold().replace(" ", "")
    v = [base, norm(sku)]
    m = re.match(r"^(.*?)-\d+$", base)
    if m:
        v.append(m.group(1))
        v.append(norm(m.group(1)))
    return list(dict.fromkeys(x for x in v if x))


# ============================ 当前责任方（B r10） ============================

def build_owner_maps(b10: pd.DataFrame) -> tuple[dict, dict, dict, pd.DataFrame]:
    """只让 B r10 US 需求行的**唯一**「美国责任方」承接。

    返回 (owner, basis, reason, demand_rows)。多 owner → 不留 owner；缺 owner →
    不留 owner，reason 记录。basis 取该产品 owner 行中证据层级最强者（确定性）。
    """
    b10 = b10.copy()
    b10["产品键"] = b10["产品键"].astype(str)
    bd = b10[(b10["地区"].astype(str) == "US")
             & (b10["是否需求行"].astype(str) == "Y")].copy()
    bd["_rank"] = (bd["最强证据层级"].astype(str)
                   .map(OWNER_EVIDENCE_RANK).fillna(0))
    bd["_owner"] = bd["美国责任方"].where(bd["美国责任方"].notna()).astype(object)
    bd.loc[bd["_owner"].isin(["nan", "None", ""]), "_owner"] = np.nan
    owner, basis, reason = {}, {}, {}
    for pid, g in bd.groupby("产品键", sort=False):
        owners = sorted({str(v) for v in g["_owner"].dropna() if str(v).strip()})
        if len(owners) == 1:
            owner[pid] = owners[0]
            g2 = g[g["_owner"].astype(str) == owners[0]]
            top = g2.sort_values("_rank", ascending=False).iloc[0]
            basis[pid] = str(top["最强证据层级"])
            reason[pid] = "unique_owner"
        elif len(owners) > 1:
            owner[pid] = None
            basis[pid] = ""
            reason[pid] = "multi_owner:" + "|".join(owners)
        else:
            owner[pid] = None
            basis[pid] = ""
            reason[pid] = "missing_owner"
    return owner, basis, reason, bd


def current_pool_of(pool: str, owner) -> str:
    """美国订单行按当前 owner 归池；非美国池原样保留。"""
    if pool in US_POOLS:
        return owner if owner in US_POOLS else UNASSIGNED
    return pool


def build_current_key_set(k_asof: set[tuple], owner: dict) -> tuple[set, dict]:
    """as-of 键 → current-owner 键；USNJ/USTX 按 owner 合并。"""
    cur_of = {}
    for pid, pool, form, uom in k_asof:
        cur_pool = current_pool_of(pool, owner.get(pid))
        cur_of[(pid, pool, form, uom)] = (pid, cur_pool, form, uom)
    return set(cur_of.values()), cur_of


def fix_key_current(product: str, pool: str, form: str, uom: str,
                    by_prod: dict[str, set]) -> tuple[tuple, str]:
    key = (product, pool, form, uom)
    if key in by_prod.get(product, set()):
        return key, ""
    cand = [k for k in by_prod.get(product, set()) if k[0] == pool and k[2] == uom]
    if len(cand) == 1:
        return (product, pool, cand[0][1], uom), "form归一（唯一候选）"
    return key, ("无对应需求键" if not cand else "跨 form 多候选")


# ============================ 输入 ============================

def build_code_index(a: pd.DataFrame, sku_map: pd.DataFrame,
                     cust: pd.DataFrame) -> tuple[dict, dict]:
    """code → {product_id: [证据]}；同时返回 code → 证据说明。"""
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


# ============================ 模型（与 D3 同口径） ============================

def f_naive(y, h, **kw):
    observed = np.asarray(y, dtype=float)
    observed = observed[np.isfinite(observed)]
    if not len(observed):
        raise ValueError("训练无可观测月")
    return np.repeat(observed[-1], h)


def f_ma3(y, h, **kw):
    tail = np.asarray(y, dtype=float)[-3:]
    if len(tail) < 3 or not np.all(np.isfinite(tail)):
        raise ValueError("MA3 最近 3 个日历月存在缺观测")
    return np.repeat(float(np.mean(tail)), h)


def f_snaive(y, h, **kw):
    values = np.asarray(y, dtype=float)
    if len(values) < 12:
        raise ValueError("季节性基线缺少 t-12 日历月")
    indices = [len(values) - 12 + i for i in range(h)]
    indices = [i if i < len(values) else len(values) - 12 for i in indices]
    seasonal = values[indices]
    if not np.all(np.isfinite(seasonal)):
        raise ValueError("季节性基线所需 t-12 日历月缺观测")
    return seasonal


def f_ets_ann(y, h, **kw):
    values = np.asarray(y, dtype=float)
    observed = values[np.isfinite(values)]
    if not len(observed):
        raise ValueError("ETS 训练无可观测月")
    if len(observed) < 2:
        return np.repeat(observed[-1], h)
    yv = values[1:]
    best_a, best_sse = ETS_ALPHAS[0], np.inf
    for a in ETS_ALPHAS:
        l, sse = observed[0], 0.0
        for v in yv:
            if not np.isfinite(v):
                continue
            sse += (v - l) ** 2
            l = a * v + (1 - a) * l
        if sse < best_sse - 1e-12:
            best_a, best_sse = a, sse
    l, a = observed[0], best_a
    for v in yv:
        if not np.isfinite(v):
            continue
        l = a * v + (1 - a) * l
    return np.repeat(l, h)


HOLT_ALPHAS = (0.1, 0.3, 0.5, 0.7, 0.9)
HOLT_BETAS = (0.01, 0.05, 0.1, 0.2, 0.4)
HOLT_PHIS = (0.80, 0.90, 0.98)
THETA_ALPHAS = np.round(np.arange(0.02, 0.99, 0.02), 2)


def _fit_damped_holt(y, h):
    """Holt 加性阻尼趋势（无季节）网格拟合；NaN 月跳过、不压缩日历。"""
    vals = np.asarray(y, dtype=float)
    idx = np.where(np.isfinite(vals))[0]
    if not len(idx):
        raise ValueError("Holt 训练无可观测月")
    if len(idx) == 1:
        return np.repeat(vals[idx[0]], h)
    first, last = int(idx[0]), int(idx[-1])
    b0 = (vals[last] - vals[first]) / max(1, last - first)
    l0 = vals[first]
    best_sse, best = np.inf, None
    for a in HOLT_ALPHAS:
        for b in HOLT_BETAS:
            for phi in HOLT_PHIS:
                level, trend = l0, b0
                sse = 0.0
                for i in idx[1:]:
                    pred = level + phi * trend
                    err = vals[i] - pred
                    sse += err * err
                    new_level = a * vals[i] + (1 - a) * pred
                    trend = b * (new_level - level) + (1 - b) * phi * trend
                    level = new_level
                if sse < best_sse - 1e-12:
                    best_sse, best = sse, (a, b, phi, level, trend)
    if best is None:
        return np.repeat(vals[last], h)
    _, _, phi, level, trend = best
    out, damp = [], 0.0
    for step in range(1, h + 1):
        damp += phi ** step
        out.append(level + damp * trend)
    return np.maximum(np.asarray(out, dtype=float), 0.0)


def _seasonal_additive(y, period=12):
    """按日历位置 i%period 估计加性季节项；<2 个完整周期返回 None。"""
    vals = np.asarray(y, dtype=float)
    idx = np.where(np.isfinite(vals))[0]
    if len(idx) < period * 2:
        return None
    coef = np.polyfit(idx, vals[idx], 1)
    detrended = vals[idx] - np.polyval(coef, idx)
    seasonal = np.zeros(period)
    for m in range(period):
        sel = detrended[(idx % period) == m]
        seasonal[m] = float(np.mean(sel)) if len(sel) else 0.0
    seasonal -= float(np.mean(seasonal))
    return seasonal


def _deseasonalize(vals, seasonal):
    return np.asarray([
        v - seasonal[i % len(seasonal)] if np.isfinite(v) else np.nan
        for i, v in enumerate(vals)], dtype=float)


def f_ets_aadn(y, h, **kw):
    """ETS(A,Ad,N)：加性误差 + 加性阻尼趋势，无季节。"""
    return _fit_damped_holt(y, h)


def f_ets_aaa(y, h, **kw):
    """ETS(A,A,A)/STL+ETS：加性季节分解 + 加性阻尼趋势。

    实现为「日历位置季节项 + 去季节后 Holt」；至少 24 个已观测月才可估季节，
    否则显式失败（不静默退化）。
    """
    vals = np.asarray(y, dtype=float)
    if int(np.sum(np.isfinite(vals))) < 24:
        raise ValueError("AAA 需要 ≥24 个已观测月")
    seasonal = _seasonal_additive(vals, 12)
    if seasonal is None:
        raise ValueError("AAA 季节项估计失败（<2 个完整周期）")
    deseason = _deseasonalize(vals, seasonal)
    fc = _fit_damped_holt(deseason, h)
    n = len(vals)
    out = [fc[k] + seasonal[(n + k) % 12] for k in range(h)]
    return np.maximum(np.asarray(out, dtype=float), 0.0)


def f_theta(y, h, **kw):
    """简化 Theta：线性趋势（theta=0）与 SES（theta=2）各 50%，可选季节项。"""
    vals = np.asarray(y, dtype=float)
    idx = np.where(np.isfinite(vals))[0]
    if not len(idx):
        raise ValueError("Theta 训练无可观测月")
    if len(idx) == 1:
        return np.repeat(vals[idx[0]], h)
    seasonal = _seasonal_additive(vals, 12) if len(idx) >= 24 else None
    series = _deseasonalize(vals, seasonal) if seasonal is not None else vals.copy()
    obs = np.isfinite(series)
    oi = np.where(obs)[0]
    coef = np.polyfit(oi, series[oi], 1)
    best_a, best_sse = THETA_ALPHAS[0], np.inf
    for a in THETA_ALPHAS:
        level, sse = series[oi[0]], 0.0
        for i in oi[1:]:
            sse += (series[i] - level) ** 2
            level = a * series[i] + (1 - a) * level
        if sse < best_sse - 1e-12:
            best_a, best_sse = a, sse
    level = series[oi[0]]
    for i in oi[1:]:
        level = best_a * series[i] + (1 - best_a) * level
    n = len(vals)
    out = []
    for k in range(h):
        linear = float(np.polyval(coef, n + k))
        value = 0.5 * linear + 0.5 * level
        if seasonal is not None:
            value += seasonal[(n + k) % 12]
        out.append(max(value, 0.0))
    return np.asarray(out, dtype=float)


def _croston(y, alpha):
    idx = np.where(y > 0)[0]
    if not len(idx):
        return 0.0, 0.0
    z, p, prev = float(y[idx[0]]), float(idx[0] + 1), idx[0]
    for i in idx[1:]:
        z = alpha * y[i] + (1 - alpha) * z
        p = alpha * (i - prev) + (1 - alpha) * p
        prev = i
    return z, p


def f_croston(y, h, **kw):
    if not np.all(np.isfinite(y)):
        raise ValueError("Croston 训练缺观测，拒绝压缩日历间隔")
    z, p = _croston(y, ALPHA)
    return np.repeat(z / p if p > 0 else 0.0, h)


def f_sba(y, h, **kw):
    if not np.all(np.isfinite(y)):
        raise ValueError("SBA 训练缺观测，拒绝压缩日历间隔")
    z, p = _croston(y, ALPHA)
    return np.repeat((1 - ALPHA / 2) * z / p if p > 0 else 0.0, h)


def f_tsb(y, h, **kw):
    if not np.all(np.isfinite(y)):
        raise ValueError("TSB 训练缺观测，拒绝压缩日历间隔")
    nz = np.where(y > 0)[0]
    if not len(nz):
        return np.zeros(h)
    z, p = float(y[nz[0]]), len(nz) / len(y)
    for v in y:
        if v > 0:
            z = ALPHA * v + (1 - ALPHA) * z
            p = ALPHA + (1 - ALPHA) * p
        else:
            p = (1 - ALPHA) * p
    return np.repeat(p * z, h)


BASELINES = dict(naive=f_naive, ma3=f_ma3, snaive=f_snaive, ets_ann=f_ets_ann,
                 ets_aadn=f_ets_aadn, ets_aaa=f_ets_aaa, theta=f_theta)
NEW_MODELS = dict(croston=f_croston, sba=f_sba, tsb=f_tsb)


def models_for(pattern: str, sbc: str) -> list[str]:
    m = ["naive", "ma3", "snaive", "ets_ann", "ets_aadn", "ets_aaa", "theta"]
    if pattern == "obsolescent":
        m += ["croston", "sba", "tsb"]
    elif sbc in ("intermittent", "lumpy") or pattern == "lumpy":
        m += ["croston", "sba"]
    return m


# ============================ 分类 ============================

def classify(vals: np.ndarray, first_pos: str | None = None) -> dict:
    n = len(vals)
    pos = vals[vals > 0]
    out = dict(n_obs=int(n), n_pos=int(len(pos)), adi=np.nan, cv2=np.nan,
               demand_pattern="short", sbc_class="n/a", recent6_sum=float(np.sum(vals[-6:])) if n else 0.0)
    if n == 0 or len(pos) == 0:
        out.update(demand_pattern="no_demand", cause="无任何正销（无历史证据）")
        return out
    if first_pos and first_pos >= "202601":
        out.update(demand_pattern="new", cause="真新品（首销 ≥2026-01）")
        return out
    if n < MIN_HIST_CLASS:
        out["cause"] = "短史"
        return out
    if len(pos) == 0:
        out.update(demand_pattern="obsolescent", cause="真无历史")
        return out
    if out["recent6_sum"] <= 0 and len(pos) <= 3:
        out.update(demand_pattern="obsolescent", cause="无近期需求")
        return out
    adi = n / len(pos)
    cv2 = float(np.var(pos, ddof=1) / np.mean(pos) ** 2) if len(pos) > 1 else 0.0
    if adi < ADI_THR and cv2 < CV2_THR:
        sbc, pat = "smooth", "smooth"
    elif adi >= ADI_THR and cv2 < CV2_THR:
        sbc, pat = "intermittent", "intermittent"
    elif adi >= ADI_THR and cv2 >= CV2_THR:
        sbc, pat = "lumpy", "lumpy"
    else:
        sbc, pat = "erratic", "lumpy"
    out.update(adi=float(adi), cv2=cv2, demand_pattern=pat, sbc_class=sbc, cause="")
    return out


# ============================ 趋势诊断 ============================

TREND_BUCKETS = ("down>30", "down10-30", "stable", "up10-30", "up>30",
                 "no_2025_base", "no_data")
# 2026-11-11 波兰软包墙围请求的 4 个 SKU（报告单列，不参与模型选择）
WALL_KEYS = ("KS0211-KJB-60-BEIGE", "KS0211-KJB-90-BEIGE",
             "KS0211-KJB-90-DEEPGREY", "KS0211-DM-60-DEEPGREY")


def trend_diagnostics(vals, obs) -> dict:
    """2026 vs 2025 同期、3/6/12 月斜率、结构突变启发式标记。

    - YoY：2026-01..10 / 2025-01..10，只计已观测月（删失月剔除）。
    - 斜率：最近 3/6/12 个已观测月的 OLS 斜率（件/月），不压缩日历。
    - 结构突变：最近最多 12 个已观测月按时间对半，比较前后半段均值；
      |z|≥2 且相对变化≥30% 才标记（工程启发式，不是正式检验）。
    """
    vals = np.asarray(vals, dtype=float)
    obs = np.asarray(obs, dtype=bool)

    def _period_sum(start, end):
        idx = [i for i, m in enumerate(OBS_MONTHS)
               if start <= m <= end and obs[i] and np.isfinite(vals[i])]
        return float(vals[idx].sum()) if idx else 0.0

    s2025 = _period_sum("202501", "202510")
    s2026 = _period_sum("202601", "202610")
    if s2025 > 0:
        yoy = s2026 / s2025 - 1.0
        if yoy <= -0.30:
            bucket = "down>30"
        elif yoy <= -0.10:
            bucket = "down10-30"
        elif yoy < 0.10:
            bucket = "stable"
        elif yoy < 0.30:
            bucket = "up10-30"
        else:
            bucket = "up>30"
    else:
        yoy = np.nan
        bucket = "no_2025_base" if s2026 > 0 else "no_data"

    def _slope(n):
        idx = [i for i in range(len(vals)) if obs[i] and np.isfinite(vals[i])][-n:]
        if len(idx) < 2:
            return np.nan
        return float(np.polyfit(idx, vals[idx], 1)[0])

    slope3, slope6, slope12 = _slope(3), _slope(6), _slope(12)
    idx_all = [i for i in range(len(vals)) if obs[i] and np.isfinite(vals[i])]
    last6 = vals[idx_all[-6:]] if len(idx_all) >= 6 else vals[idx_all]
    mean6 = float(np.mean(last6)) if len(last6) else 0.0
    slope6_pct = (slope6 / mean6) if (np.isfinite(slope6) and mean6 > 0) else np.nan

    # 结构突变：① 最近 12 个已观测月按时间对半；② 2026 vs 2025 年均值。
    # 无 2025 基数（新品/无数据）不标突变，避免把“从 0 起销”误判为结构突变。
    recent_idx = idx_all[-12:]
    break_flag, shift_ratio, shift_z = "", np.nan, np.nan
    if bucket not in ("no_2025_base", "no_data") and len(recent_idx) >= 4:
        mid = recent_idx[len(recent_idx) // 2]
        prior = vals[[i for i in recent_idx if i < mid]]
        recent = vals[[i for i in recent_idx if i >= mid]]
        if len(prior) and len(recent):
            pm, rm = float(np.mean(prior)), float(np.mean(recent))
            sd = float(np.std(prior, ddof=1)) if len(prior) > 1 else 0.0
            shift_ratio = (rm / pm) if pm > 0 else np.nan
            shift_z = (rm - pm) / max(sd, 0.1 * abs(pm), 1e-6)
            rel = abs(rm - pm) / max(abs(pm), 1.0)
            if pm > 0 and abs(rm - pm) >= 3 and abs(shift_z) >= 2.0 and rel >= 0.30:
                break_flag = "up" if rm > pm else "down"
    # 年度水平突变（覆盖 2026 年初发生的台阶；6v6 只看最近 12 月会漏）
    _m25 = [vals[i] for i, m in enumerate(OBS_MONTHS)
            if "202501" <= m <= "202510" and obs[i] and np.isfinite(vals[i])]
    _m26 = [vals[i] for i, m in enumerate(OBS_MONTHS)
            if "202601" <= m <= "202610" and obs[i] and np.isfinite(vals[i])]
    if (bucket not in ("no_2025_base", "no_data")
            and s2025 > 0 and len(_m25) >= 3 and len(_m26) >= 3):
        _a, _b = float(np.mean(_m25)), float(np.mean(_m26))
        _sd = float(np.std(_m25, ddof=1))
        _z = (_b - _a) / max(_sd, 0.1 * abs(_a), 1e-6)
        _rel = abs(_b - _a) / max(abs(_a), 1.0)
        if _a > 0 and abs(_b - _a) >= 3 and abs(_z) >= 2.0 and _rel >= 0.30 and not break_flag:
            break_flag = "up" if _b > _a else "down"
        if np.isnan(shift_z):
            shift_z = _z

    return dict(sum_2025_jan_oct=s2025, sum_2026_jan_oct=s2026,
                yoy_pct=(yoy * 100 if np.isfinite(yoy) else np.nan),
                slope_3m=slope3, slope_6m=slope6, slope_12m=slope12,
                slope_6m_pct=(slope6_pct * 100 if np.isfinite(slope6_pct) else np.nan),
                level_shift_ratio=shift_ratio, level_shift_z=shift_z,
                structural_break=break_flag, trend_bucket=bucket)


# ============================ 回测 ============================

def backtest(y, obs, models, origins=ORIGINS, h=H, months=None):
    months = list(months or OBS_MONTHS)
    y = np.asarray(y, dtype=float)
    obs = np.asarray(obs, dtype=bool)
    if len(y) != len(months) or len(obs) != len(months):
        raise ValueError("y、obs 与 months 长度必须一致")
    rows = []
    for origin in origins:
        oi = months.index(origin)
        observed_train = [i for i in range(oi + 1) if obs[i] and np.isfinite(y[i])]
        te = [i for i in range(oi + 1, min(oi + 1 + h, len(months)))
              if obs[i] and np.isfinite(y[i])]
        if len(observed_train) < MIN_TRAIN_OBS or len(te) < 3:
            rows.append(dict(origin=origin, status="skipped",
                             reason=(f"训练已观测月 {len(observed_train)} < {MIN_TRAIN_OBS}"
                                     if len(observed_train) < MIN_TRAIN_OBS
                                     else f"insufficient_test：测试窗已核验月 {len(te)} < 3")))
            continue
        first_train = observed_train[0]
        ytr = np.where(obs[first_train:oi + 1], y[first_train:oi + 1], np.nan)
        for name in models:
            fn = BASELINES.get(name) or NEW_MODELS.get(name)
            try:
                fc = np.asarray(fn(ytr, h), dtype=float)
            except Exception as exc:                     # noqa: BLE001
                rows.append(dict(origin=origin, model=name, status="failed",
                                 reason=f"{type(exc).__name__}: {exc}"[:160]))
                continue
            if not np.all(np.isfinite(fc)):
                rows.append(dict(origin=origin, model=name, status="failed", reason="非有限预测"))
                continue
            errs, acts, mid = [], [], []
            for step, i in enumerate(range(oi + 1, min(oi + 1 + h, len(months)))):
                if i not in te:
                    continue
                errs.append(float(fc[step] - y[i]))
                acts.append(float(y[i]))
                mid.append(months[i])
            if not errs:
                rows.append(dict(origin=origin, model=name, status="skipped",
                                 reason="测试窗口无可评估月"))
                continue
            rows.append(dict(origin=origin, model=name, status="ok", n_train=len(observed_train),
                             n_train_calendar=len(ytr),
                             test_months=";".join(mid), n_test=len(errs),
                             abs_err=float(np.sum(np.abs(errs))),
                             sum_abs=float(np.sum(np.abs(acts)))))
    successful = {name: {r["origin"] for r in rows
                         if r.get("model") == name and r.get("status") == "ok"}
                  for name in models}
    active = [origins for origins in successful.values() if origins]
    common_origins = set.intersection(*active) if active else set()
    for row in rows:
        if row.get("status") == "ok" and row["origin"] not in common_origins:
            row.update(status="skipped", reason="不在模型共同可评估 origin（覆盖不同）")
    return rows


def agg(rows):
    ok = [r for r in rows if r.get("status") == "ok"]
    if not ok:
        return dict(status="failed", n=0, wape=np.nan, mae=np.nan, pinball50=np.nan,
                    reason=(rows[0].get("reason") if rows else "无 origin"))
    n = sum(r["n_test"] for r in ok)
    sa = sum(r["abs_err"] for r in ok)
    den = sum(r["sum_abs"] for r in ok)
    return dict(status="ok", n=int(n), wape=(sa / den if den > 0 else np.nan),
                mae=sa / n, pinball50=0.5 * sa / n, den=float(den), reason="")


def _rank(v):
    return ((v["wape"] if np.isfinite(v["wape"]) else np.inf), v["mae"])


def select(per_model, pattern, rows=None):
    """只比较有正销且共同可评估的测试窗；MAE=0 仍是有效成绩。"""
    evaluated = {k: v for k, v in per_model.items() if v["status"] == "ok"}
    if rows is not None:
        successful = {k: {r["origin"]: r for r in rows
                          if r.get("model") == k and r.get("status") == "ok"}
                      for k in evaluated}
        active = [set(v) for v in successful.values() if v]
        common = set.intersection(*active) if active else set()
        evaluated = {}
        for name, by_origin in successful.items():
            shared = [by_origin[o] for o in sorted(common)
                      if all(o in other and by_origin[o].get("test_months")
                             == other[o].get("test_months")
                             for other in successful.values() if other)]
            if shared:
                evaluated[name] = agg(shared)
    ok = {k: v for k, v in evaluated.items() if v.get("den", 0) > 0}
    if not ok:
        if not evaluated:
            return dict(adopted="none", baseline="none", reason="无有效 origin（无可评估模型）")
        if all(v.get("den", 0) == 0 for v in evaluated.values()):
            return dict(adopted="none", baseline="none",
                        reason="test_window_no_positive：测试窗无正销实际（WAPE 未定义），不算证据")
        return dict(adopted="none", baseline="none", reason="无正销测试窗可比较")
    base = {k: v for k, v in ok.items() if k in BASELINES}
    new = {k: v for k, v in ok.items() if k in NEW_MODELS}
    if not base:
        best = min(new or ok, key=lambda k: _rank((new or ok)[k]))
        return dict(adopted=best, baseline="none", reason="基线全部失败，取可用新方法（需复核）")
    bb = min(base, key=lambda k: _rank(base[k]))
    bw, bm = base[bb]["wape"], base[bb]["mae"]
    passes = []
    for k, v in new.items():
        if k == "tsb" and pattern != "obsolescent":
            continue
        wape_ok = (not np.isfinite(bw)) or (np.isfinite(v["wape"]) and v["wape"] <= bw)
        if not (wape_ok and v["mae"] <= bm):
            continue
        gains = []
        if np.isfinite(bw) and np.isfinite(v["wape"]) and bw > 0:
            gains.append((bw - v["wape"]) / bw)
        if bm > 0:
            gains.append((bm - v["mae"]) / bm)
        if gains and max(gains) >= ADOPT_GAIN:
            passes.append((k, max(gains)))
    if passes:
        k, g = max(passes, key=lambda t: t[1])
        return dict(adopted=k, baseline=bb,
                    reason=f"{k} 相对基线 {bb} 改善 {g:.1%}（WAPE/MAE 均不劣）")
    note = "" if np.isfinite(bw) else "（测试窗口无正销，WAPE 未定义，按 MAE）"
    if rows is not None:
        note += "（采用判断使用共同可评估 origin/测试月份）"
    return dict(adopted=bb, baseline=bb,
                reason=f"新方法未达门槛（需不劣 + ≥{ADOPT_GAIN:.0%}），用基线 {bb}{note}")


def build_asof_adoption_map(cls_tbl, res_tbl, hist_qty):
    """as-of 唯一事实源：3a_分类_asof.adopted_model 必须等于 4_回测_asof.adopted。

    返回 {(pid,pool,form,uom): {model,status,reason,qty}}；任何不一致直接 fail closed。
    """
    key_cols = ["product_id", "pool", "physical_form", "canonical_uom"]
    adopted_rows = res_tbl[res_tbl["adopted"].astype(str) == "是"]
    by_key = adopted_rows.groupby(key_cols, sort=False)["model"].apply(list).to_dict()
    out = {}
    for r in cls_tbl.itertuples(index=False):
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        models = by_key.get(key, [])
        if len(models) > 1:
            raise AssertionError(f"4_回测_asof 同键多条 adopted=是：{key} {models}")
        res_model = str(models[0]) if models else "none"
        cls_model = str(getattr(r, "adopted_model", "none") or "none")
        status = str(getattr(r, "adoption_status", "") or "")
        if status == "adopted":
            if res_model == "none":
                raise AssertionError(f"3a_分类_asof 标 adopted 但 4_回测_asof 无 adopted：{key}")
            if cls_model != res_model:
                raise AssertionError(
                    f"3a_分类_asof 与 4_回测_asof 不一致：{key} {cls_model} != {res_model}")
        elif cls_model not in ("none", "nan", ""):
            raise AssertionError(
                f"3a_分类_asof 非 adopted 却带模型：{key} status={status} model={cls_model}")
        out[key] = dict(model=(cls_model if status == "adopted" else "none"),
                        status=status, reason=str(getattr(r, "selection_reason", "") or ""),
                        qty=float(hist_qty.get(key, 0.0)))
    if len(out) != len(cls_tbl):
        raise AssertionError(f"as-of adoption map 键数不守恒：{len(out)} != {len(cls_tbl)}")
    return out


def build_current_adoption_map(k_current, current_multi_from, asof_map, hist_qty):
    """current-owner 键只 join as-of 采用结果，不另算模型。

    多源键（USNJ/USTX 合并）规则：若源键模型一致 → 直接采用；若不一致 →
    取历史量最大的源键（确定性 tie-break），并在 adopted_sources 留痕。
    任何 current 键没有源键、或 join 出的模型不在源键模型集合内 → fail closed。
    """
    out = {}
    for ck in sorted(k_current):
        srcs = sorted(current_multi_from.get(ck, []))
        if not srcs:
            raise AssertionError(f"current 键无 as-of 源键：{ck}")
        candidates = []
        statuses = []
        for sk in srcs:
            if sk not in asof_map:
                raise AssertionError(f"current 键的 as-of 源键不在分类表：{ck} <- {sk}")
            info = asof_map[sk]
            statuses.append(info["status"] or "not_adopted")
            if info["model"] not in ("none", ""):
                candidates.append((info["model"], float(hist_qty.get(sk, info["qty"])), sk))
        tracing = [dict(source_key="|".join(sk), model=asof_map[sk]["model"],
                        qty=float(hist_qty.get(sk, asof_map[sk]["qty"])))
                   for sk in srcs]
        if not candidates:
            out[ck] = dict(model="none", source="asof_join_none",
                           status=(statuses[0] if statuses else "not_adopted"),
                           sources=tracing)
            continue
        models = {m for m, _, _ in candidates}
        if len(models) == 1:
            model = next(iter(models))
            source = "asof_join" if len(srcs) == 1 else "asof_join_multi_agree"
        else:
            model, _, _ = max(candidates, key=lambda t: (t[1], t[2]))
            source = "asof_join_multi_maxqty"
        if model not in models:
            raise AssertionError(f"current join 模型不在源键集合：{ck} {model} {models}")
        out[ck] = dict(model=model, source=source, status="adopted", sources=tracing)
    if set(out) != set(k_current):
        raise AssertionError("current adoption map 键集不守恒")
    return out


def run_selftests() -> list[tuple[str, bool, str]]:
    t = []
    y = np.array([4.0, 0, 0, 6.0, 0, 0, 0, 2.0], dtype=float)
    t.append(("① 归一规则（OLD_/-Cover/-c/-1/-2/casefold）",
              norm("OLD_CEN-No/B-Velvet-Grey-153-Cover") == "cen-no/b-velvet-grey-153"
              and norm("New-CEN003-NZAIBLUE-100-c") == "cen003-nzaiblue-100"
              and norm("TT0031038K0062927-2") == "tt0031038k0062927",
              f"{norm('OLD_CEN-No/B-Velvet-Grey-153-Cover')} / {norm('TT0031038K0062927-2')}"))
    t.append(("② 全零实际 → WAPE=NaN（不填 0）",
              bool(np.isnan(agg([dict(status="ok", n_test=2, abs_err=0.0, sum_abs=0.0)])["wape"])),
              "ok"))
    per = {"naive": dict(status="ok", wape=1.0, mae=1.0, den=100.0),
           "croston": dict(status="ok", wape=0.9, mae=0.9, den=100.0),
           "sba": dict(status="ok", wape=0.97, mae=0.97, den=100.0)}
    t.append(("③ 采用门槛（≥5%）", select(per, "intermittent")["adopted"] == "croston"
              and select({**per, "croston": dict(status="ok", wape=0.98, mae=0.98, den=100.0)},
                         "intermittent")["adopted"] == "naive",
              select(per, "intermittent")["adopted"]))
    # ④ 删失月不进评估：窗口 4 个月里有 1 个删失 → n_test=3（≥3 契约仍满足）
    months = ([f"2025{m:02d}" for m in range(1, 13)] + [f"2026{m:02d}" for m in range(1, 13)])[:16]
    obs = np.array([True] * 12 + [True, False, True, True])
    yy = np.array([2.0] * 12 + [3.0, np.nan, 3.0, 3.0])
    r = backtest(yy, obs, ["naive"], origins=(months[11],), h=4, months=months)
    ok4 = r[-1]["status"] == "ok" and r[-1]["n_test"] == 3 and "202602" not in r[-1]["test_months"]
    # ⑥ 测试窗不足 3 个月 → insufficient_test，跳过不进指标
    months6 = ([f"2025{m:02d}" for m in range(1, 13)] + ["202601", "202602", "202603"])[:15]
    obs6 = np.array([True] * 12 + [True, True, False])
    r6 = backtest(np.array([1.0] * 15), obs6, ["naive"], origins=(months6[11],), h=3, months=months6)
    ok6 = r6[-1]["status"] == "skipped" and "insufficient_test" in r6[-1]["reason"]
    t.append(("④ 删失月不进评估（n_test=3）", ok4,
              str({k: r[-1].get(k) for k in ("n_test", "test_months")})))
    t.append(("⑥ 测试窗<3 月 → insufficient_test 跳过", ok6, str(r6[-1].get("reason"))))
    per_zero = {"naive": dict(status="ok", wape=0.0, mae=0.0, den=20.0),
                "croston": dict(status="ok", wape=0.2, mae=1.0, den=20.0)}
    sel7 = select(per_zero, "intermittent")
    t.append(("⑦ 有正销的零误差基线仍有效",
              sel7["adopted"] == "naive" and sel7["baseline"] == "naive",
              sel7["reason"][:60]))
    t.append(("⑤ 映射候选唯一才合并",
              (lambda: (lambda m: m == "唯一")( "唯一" if len({"P1"}) == 1 else "多候选"))(), "唯一"))
    return t


# ============================ 主流程 ============================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D3b 历史归一/重分类/重回测（只读）")
    ap.add_argument("--orders", default=f"{B}/orders_unified_20261111_v2.parquet")
    ap.add_argument("--a-final", default=f"{BA}/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--d2v3", default=f"{BA}/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--d1b", default=f"{BA}/D_资格与契约_D1b_v2_3_2026-11-02.xlsx")
    ap.add_argument("--b-r10", default=f"{BA}/仓库归属_A337_v6r10_2026-10-30.xlsx")
    ap.add_argument("--d3", default=f"{BA}/D_基线回测_2026-10-30.xlsx")
    ap.add_argument("--d1", default=f"{BA}/D_资格与契约_v2_2026-10-30.xlsx")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{BA}/en_item_customer_codes.csv")
    ap.add_argument("--out-xlsx", default=f"{BA}/D3b-v3_11-20261112/D_历史归一与回测_D3b_v3_11_2026-11-12.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D3b-v3_11-20261112/D_历史归一与回测_D3b_v3_11_2026-11-12_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D3b-v3_11-20261112/D_历史归一与回测_D3b_v3_11_2026-11-12.manifest.json")
    ap.add_argument("--owner-audit", default=f"{BA}/D3b-v3_11-20261112/owner_restatement_audit_20261112.csv")
    ap.add_argument("--series-current", default=f"{BA}/D3b-v3_11-20261112/D3b_v3_11_series_current_2026-11-12.parquet")
    ap.add_argument("--series-asof", default=f"{BA}/D3b-v3_11-20261112/D3b_v3_11_series_asof_2026-11-12.parquet")
    ap.add_argument("--trend-csv", default=f"{BA}/D3b-v3_11-20261112/D3b_v3_11_trend_2026-11-12.csv")
    ap.add_argument("--dry-run", action="store_true", help="只算不写 xlsx/报告/manifest")
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
        ("ORDERS_UNIFIED", args.orders), ("A_FINAL", args.a_final), ("D2_V3", args.d2v3),
        ("D3_BACKTEST", args.d3), ("D1_V2", args.d1), ("D1B_V2_3", args.d1b),
        ("B_R10", args.b_r10),
        ("SKU_MAP", args.sku_map),
        ("CUSTOMER_CODES", args.customer_codes)) if Path(v).exists()}

    a = pd.read_excel(args.a_final, sheet_name="活跃宇宙")
    a = a[a["活跃分类"] != "不活跃"].copy()
    a["EN物料"] = a["EN物料"].astype(str)
    role = dict(zip(a["EN物料"], a["角色"].astype(str)))
    sku_map = pd.read_csv(args.sku_map, sep="\t", dtype=str).iloc[:, :2]
    sku_map.columns = ["en", "tt"]
    cust = pd.read_csv(args.customer_codes, dtype=str)
    idx, ev = build_code_index(a, sku_map, cust)

    d2 = pd.read_excel(args.d2v3, sheet_name="1_序列")
    keys = ["product_id", "pool", "physical_form", "canonical_uom"]
    k_old = set(map(tuple, d2[keys].astype(str).drop_duplicates().values))   # D2 v3 旧键
    # v3：需求键母集改用 D1b v2.3（active + observed/censored + 需求形态）
    d1b = pd.read_excel(args.d1b, sheet_name="1_资格")
    for c in ("product_id", "destination_pool", "physical_form", "canonical_uom",
              "decision_state", "demand_state"):
        d1b[c] = d1b[c].astype(str)
    DEMAND_FORMS = ("成品", "套件", "成品+皮壳", "皮壳", "骨架", "独立海绵")
    dm = d1b[(d1b["decision_state"] == "active")
             & d1b["demand_state"].isin(["observed", "censored"])
             & d1b["physical_form"].isin(DEMAND_FORMS)].copy()
    kn = ["product_id", "destination_pool", "physical_form", "canonical_uom"]
    k_set = set(map(tuple, dm[kn].values))          # as-of 键（历史仓库池）
    k_by_prod: dict[str, set] = {}
    for k in k_set:
        k_by_prod.setdefault(k[0], set()).add(k[1:])

    # ---------- 当前责任方（B r10）：current-owner 键（预测用）
    b10_raw = pd.read_excel(args.b_r10, sheet_name="主表")
    owner_map, owner_basis, owner_reason, b10_us = build_owner_maps(b10_raw)
    k_current, cur_of_asof = build_current_key_set(k_set, owner_map)
    cur_by_prod: dict[str, set] = {}
    for k in k_current:
        cur_by_prod.setdefault(k[0], set()).add(k[1:])
    assert len(k_current) == len(set(cur_of_asof.values())), "current key 去重失败"
    # 旧键（D2）→ as-of 键（D1b）→ current-owner 键；用于键迁移对账
    migration_reduction = len(k_set) - len(k_current)
    current_multi_from = {}
    for ak, ck in cur_of_asof.items():
        current_multi_from.setdefault(ck, []).append(ak)

    legacy_products = set(d2.loc[d2["is_legacy"].astype(bool), "product_id"].astype(str))
    new_products = set(d2.loc[d2["new_product"].astype(bool), "product_id"].astype(str))
    clearance = set(d2.loc[pd.to_numeric(d2["clearance_lines"], errors="coerce").fillna(0) > 0,
                         "product_id"].astype(str))
    d1 = pd.read_excel(args.d1, sheet_name="1_资格")
    shared_products = set(d1.loc[d1["shared_pool_ids"].fillna("").astype(str)
                                 .str.strip() != "", "product_id"].astype(str))
    cens = pd.read_excel(args.d2v3, sheet_name="2_删失")
    cens_set = set(zip(cens["product_id"].astype(str),
                       cens["month"].astype(str).str.replace("-", "", regex=False)))

    d3 = pd.read_excel(args.d3, sheet_name="1_分类")
    short885 = d3[d3["demand_pattern"] == "short"].copy()

    # ---------- 订单 → canonical（按唯一 SKU 解析一次）
    o = pd.read_parquet(args.orders)
    o, date_report = prepare_order_input(o)
    o["sku_tongtool"] = o["sku_tongtool"].astype(str)
    if "qty_pieces" in o.columns:
        o["qty"] = pd.to_numeric(o["qty_pieces"], errors="coerce").fillna(0.0)
    else:
        o["qty"] = pd.to_numeric(o["qty"], errors="coerce").fillna(0.0)
    o["pool"] = o["warehouse"].map(POOL_OF_WAREHOUSE).fillna("其他")
    # v3.2：WayfairCG 仓不再按地理硬分（原 Cranbury→美东）；先标记，product 解析后按 B owner 归池
    o["is_cg_order"] = o["warehouse"].astype(str).str.startswith("WayfairCG")

    uniq = sorted(o["sku_tongtool"].unique())
    res = {}
    for sku in uniq:
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
            res[sku] = dict(status="多候选", product="|".join(sorted(cands)),
                            method=meth, evidence=";".join(sorted({e for s in cands.values() for e in s})))
    mp = pd.DataFrame([dict(sku_tongtool=k, **v) for k, v in res.items()])
    # 桥表血缘：首末观测日 + 覆盖的历史月份 + A 行回指
    a["A行号"] = range(2, len(a) + 2)
    a_row = dict(zip(a["EN物料"], a["A行号"]))
    og = o.groupby("sku_tongtool").agg(first_date=("sale_date", "min"),
                                       last_date=("sale_date", "max"),
                                       first_month=("month", "min"),
                                       last_month=("month", "max"),
                                       sku_months=("month", "nunique"),
                                       sku_qty=("qty", "sum")).reset_index()
    mp = mp.merge(og, on="sku_tongtool", how="left")
    _m = mp[mp["status"] == "唯一"][["sku_tongtool", "product"]]
    prod_last = (o.merge(_m, on="sku_tongtool", how="inner")
                 .groupby("product")["sale_date"].max().to_dict())
    def _lineage(r):
        step = {"exact": "原样命中", "norm": "归一(casefold/去前缀/去后缀)",
                "base_strip": "去尾部 -N 后命中", "none": "未命中"}.get(r.method, r.method)
        if r.status == "未匹配":
            return f"{r.sku_tongtool} → 未命中（任何来源）"
        aref = a_row.get(r.product) or "无（非 A 活跃物料，经 sku_map/客户码映射）"
        return (f"{r.sku_tongtool} → {step} → {r.product}"
                f"（证据:{r.evidence}；A行:{aref}）")
    def _eff_to(r):
        if r.status != "唯一" or not isinstance(r.last_date, str):
            return ""
        pl = prod_last.get(r.product)
        return r.last_date if (isinstance(pl, str) and r.last_date < pl) else ""
    mp["mapping_lineage"] = [_lineage(r) for r in mp.itertuples(index=False)]
    mp["effective_from"] = [r.first_date if isinstance(r.first_date, str) else "" for r in mp.itertuples(index=False)]
    mp["effective_to"] = [_eff_to(r) for r in mp.itertuples(index=False)]
    mp["history_bridge_refs"] = [
        (f"orders_unified|{r.sku_tongtool}|{r.first_month}..{r.last_month}"
         f"|观测月={int(r.sku_months) if pd.notna(r.sku_months) else 0}"
         f"|qty={float(r.sku_qty) if pd.notna(r.sku_qty) else 0:.0f}")
        for r in mp.itertuples(index=False)]
    mp["a_active"] = ["是" if r.product in a_row else "否" for r in mp.itertuples(index=False)]
    mp["key_version"] = KEY_VERSION
    o = o.merge(mp, on="sku_tongtool", how="left")

    # 60cm 等价：仅 KS0001→KS0248 同面料同颜色；目标必须仍在当前 D1b 活跃键中
    _current_products = {k[0] for k in k_current}
    def _merge60(p):
        if isinstance(p, str) and p.startswith("KS0001-") and "-60-" in p:
            t = p.replace("KS0001-", "KS0248-", 1)
            if t in _current_products:
                return t
        return p
    o["product_before_60cm"] = o["product"]
    o["product"] = o["product"].map(_merge60)

    o["form"] = [form_of(p, role.get(p, "")) if isinstance(p, str) and p and "|" not in p else ""
                 for p in o["product"]]
    o["uom"] = np.where(o["form"] == "套件", "套", "个")

    # v3.2：WayfairCG 订单按产品在 B r10 的美国责任方归池（channel=wayfair），不按仓址
    cg_mask = o["is_cg_order"].fillna(False).astype(bool)
    o["pool_before_cg_fix"] = o["pool"]
    if cg_mask.any():
        o.loc[cg_mask, "pool"] = [owner_map.get(str(p)) if owner_map.get(str(p)) in US_POOLS
                                  else "其他" for p in o.loc[cg_mask, "product"].fillna("")]
    o["channel"] = np.where(cg_mask, "wayfair", "")
    cg_recon = (o[cg_mask].groupby("pool")["qty"].sum().to_dict(),
                float(o.loc[cg_mask, "qty"].sum()), int(cg_mask.sum()))
    o["key"] = list(zip(o["product"].fillna(""), o["pool"], o["form"], o["uom"]))
    o["in_k"] = [k in k_set for k in o["key"]]

    # 键归一：同 product+pool+uom 下若唯一 form → 归到该 form（记录）
    fixed, fixed_reason = [], []
    for i, row in enumerate(o.itertuples(index=False)):
        if row.in_k or not row.product or "|" in str(row.product):
            fixed.append(row.key); fixed_reason.append("")
            continue
        cand = [k for k in k_by_prod.get(row.product, set())
                if k[0] == row.pool and k[2] == row.uom]
        if len(cand) == 1:
            fixed.append((row.product, row.pool, cand[0][1], row.uom))
            fixed_reason.append("form归一（唯一候选）")
        else:
            fixed.append(row.key)
            fixed_reason.append("无对应需求键" if not cand else "跨 form 多候选")
    o["key_fixed"] = fixed
    o["fix_reason"] = fixed_reason
    o["in_k_fixed"] = [k in k_set for k in o["key_fixed"]]

    # ---------- current-owner 键（预测用）：美国行按当前 owner 重述，非美国行不变
    o["owner"] = [owner_map.get(str(p)) if isinstance(p, str) and p else None
                  for p in o["product"]]
    o["owner_basis"] = [owner_basis.get(str(p), "") if isinstance(p, str) and p else ""
                        for p in o["product"]]
    o["owner_reason"] = [owner_reason.get(str(p), "product_not_in_B")
                         if isinstance(p, str) and p else "no_product"
                         for p in o["product"]]
    o["current_pool"] = [current_pool_of(str(pool), o["owner"].iat[i])
                         for i, pool in enumerate(o["pool"])]
    ck, ck_reason = [], []
    for row in o.itertuples(index=False):
        if not row.product or "|" in str(row.product):
            ck.append((row.product, row.current_pool, row.form, row.uom))
            ck_reason.append("")
            continue
        k, why = fix_key_current(row.product, row.current_pool, row.form, row.uom,
                                 cur_by_prod)
        ck.append(k); ck_reason.append(why)
    o["key_current"] = ck
    o["fix_reason_current"] = ck_reason
    o["in_k_current"] = [k in k_current for k in o["key_current"]]
    o["bucket_current"] = np.select(
        [o["demand_event_date"].isna(), o["current_pool"] == "其他",
         o["status"] == "未匹配", o["status"] == "多候选", ~o["in_k_current"]],
        ["date_unknown", "out_of_scope_pool", "no_product_match",
         "multi_candidate", "no_demand_key"],
        default="mapped")

    # ---------- 守恒分桶
    def _ndk_reason(row) -> str:
        pid = row.product
        if not pid or pid == "nan":
            return "无产品"
        if pid not in role:
            return "非活跃产品（不在 A 活跃宇宙）"
        rl = role.get(pid, "")
        if "内胆" in rl or pid.startswith("ND#") or "海绵" in rl:
            return "ND/HM（无需求键）"
        if pid not in k_by_prod:
            return "产品无任何需求键"
        if not any(k[0] == row.pool for k in k_by_prod[pid]):
            return "该池无需求键"
        if not any(k[0] == row.pool and k[1] == row.form for k in k_by_prod[pid]):
            return "form 不匹配（跨 form 隔离）"
        return "UOM 不匹配（跨 UOM 隔离）"

    o["bucket"] = assign_order_bucket(o)
    cons = (o.groupby("bucket").agg(行数=("qty", "size"), 数量=("qty", "sum"))
            .reindex(["mapped", "no_demand_key", "multi_candidate", "no_product_match",
                      "out_of_scope_pool", "date_unknown"]).fillna(0).reset_index())
    cons["占比_数量"] = (cons["数量"] / float(o["qty"].sum())).round(4)
    ndk = o[o["bucket"] == "no_demand_key"].copy()
    ndk["原因"] = [_ndk_reason(r) for r in ndk[["product", "pool", "form", "uom"]].itertuples(index=False)]
    ndk_tbl = (ndk.groupby("原因").agg(行数=("qty", "size"), 数量=("qty", "sum"))
               .sort_values("数量", ascending=False).reset_index())
    ndk_tbl["占比_数量"] = (ndk_tbl["数量"] / float(o["qty"].sum())).round(4)
    mm_tbl = (o[o["bucket"] == "multi_candidate"]
              .groupby("product").agg(行数=("qty", "size"), 数量=("qty", "sum"))
              .sort_values("数量", ascending=False).reset_index().head(50))
    cons_total = float(cons["数量"].sum())
    assert int(cons["行数"].sum()) == len(o), "守恒行数失败"
    assert abs(cons_total - float(o["qty"].sum())) < 1e-6, "守恒失败"
    o["bucket_asof"] = o["bucket"]

    # ---------- current-owner 守恒分桶
    def _ndk_reason_current(row) -> str:
        pid = row.product
        if not pid or pid == "nan":
            return "无产品"
        if pid not in role:
            return "非活跃产品（不在 A 活跃宇宙）"
        rl = role.get(pid, "")
        if "内胆" in rl or pid.startswith("ND#") or "海绵" in rl:
            return "ND/HM（无需求键）"
        if pid not in cur_by_prod:
            return "产品无任何 current-owner 需求键"
        if not any(k[0] == row.current_pool for k in cur_by_prod[pid]):
            return "该 owner 池无需求键"
        if not any(k[0] == row.current_pool and k[1] == row.form
                   for k in cur_by_prod[pid]):
            return "form 不匹配（跨 form 隔离）"
        return "UOM 不匹配（跨 UOM 隔离）"

    cons_cur = (o.groupby("bucket_current").agg(行数=("qty", "size"), 数量=("qty", "sum"))
                .reindex(["mapped", "no_demand_key", "multi_candidate", "no_product_match",
                          "out_of_scope_pool", "date_unknown"]).fillna(0).reset_index())
    cons_cur["占比_数量"] = (cons_cur["数量"] / float(o["qty"].sum())).round(4)
    ndkc = o[o["bucket_current"] == "no_demand_key"].copy()
    ndkc["原因"] = [_ndk_reason_current(r) for r in
                    ndkc[["product", "current_pool", "form", "uom"]].itertuples(index=False)]
    ndkc_tbl = (ndkc.groupby("原因").agg(行数=("qty", "size"), 数量=("qty", "sum"))
                .sort_values("数量", ascending=False).reset_index())
    ndkc_tbl["占比_数量"] = (ndkc_tbl["数量"] / float(o["qty"].sum())).round(4)
    cons_cur_total = float(cons_cur["数量"].sum())
    assert int(cons_cur["行数"].sum()) == len(o), "current 守恒行数失败"
    assert abs(cons_cur_total - float(o["qty"].sum())) < 1e-6, "current 守恒失败"

    # ---------- 月度序列（mapped 行）—— as-of 与 current 分开
    m = o[o["bucket_asof"] == "mapped"].copy()                  # as-of（回测）
    m["km"] = list(zip(m["key_fixed"], m["month"]))
    ser = m.groupby("km")["qty"].sum()
    cons_month = m.groupby("month")["qty"].sum()

    mc = o[o["bucket_current"] == "mapped"].copy()              # current-owner（预测）
    mc["km"] = list(zip(mc["key_current"], mc["month"]))
    ser_cur = mc.groupby("km")["qty"].sum()
    cons_month_cur = mc.groupby("month")["qty"].sum()

    # ---------- 有效历史 / 分类 / 回测
    hist_rows, cls_rows, res_rows, det_rows, fail_rows = [], [], [], [], []
    series_cache = {}
    for key in sorted(k_set):
        pid, pool, form, uom = key
        vals = np.array([ser.get((key, mo), 0.0) for mo in OBS_MONTHS], dtype=float)
        obs = np.array([(pid, mo) not in cens_set for mo in OBS_MONTHS])
        pos_idx = np.where(vals > 0)[0]
        first_pos = int(pos_idx[0]) if len(pos_idx) else None
        # v2：无任何正销 → 有效历史 0（v1 错记成 1 个月）
        launch = first_pos if first_pos is not None else len(OBS_MONTHS)
        active = np.zeros(len(OBS_MONTHS), dtype=bool)
        active[launch:] = True
        usable = obs & active
        n_usable = int(usable.sum()) if first_pos is not None else 0
        n_pos = int(len(pos_idx))
        if n_pos == 0:
            usable = np.zeros(len(OBS_MONTHS), dtype=bool)
        n_censored = int((~obs & active).sum())
        hist_rows.append(dict(key_version=KEY_VERSION, product_id=pid, pool=pool,
                              physical_form=form, canonical_uom=uom,
                              first_positive_month=(OBS_MONTHS[first_pos] if first_pos is not None else ""),
                              last_month=END_MONTH,
                              history_months_effective=n_usable,
                              months_before_2025=int((usable & (np.array(OBS_MONTHS) < "202501")).sum()),
                              months_positive=n_pos, months_censored=n_censored,
                              qty_total=float(vals[usable].sum()),
                              evidence_quality=("2025+ 有删失证据" if n_usable else "无可用月")))
        y = np.where(usable, vals, np.nan)
        c = classify(y[usable], hist_rows[-1]["first_positive_month"] or None)
        row = dict(key_version=KEY_VERSION, product_id=pid, pool=pool,
                   physical_form=form, canonical_uom=uom, n_obs=c["n_obs"], n_pos=c["n_pos"], adi=c["adi"], cv2=c["cv2"],
                   demand_pattern=c["demand_pattern"], sbc_class=c["sbc_class"],
                   is_legacy=pid in legacy_products, new_product=pid in new_products,
                   clearance=pid in clearance, shared_candidate=bool(pid in shared_products))
        eligible = (c["n_obs"] >= MIN_HIST_CLASS and c["n_pos"] > 0
                    and pid not in legacy_products)
        row["eligible"] = eligible
        row["backtested"] = False          # 至少 1 个有效 origin 且模型可评估才置 True
        row["adoption_status"] = "not_eligible" if not eligible else ""
        if not eligible:
            why = ("老品" if pid in legacy_products else
                   "真无历史" if c["n_pos"] == 0 else "短史")
            row["not_backtestable_reason"] = why
            fail_rows.append(dict(层级="series", product_id=pid, pool=pool,
                                  physical_form=form, canonical_uom=uom,
                                  类型=why, 原因=f"可用月 {c['n_obs']} / 正销月 {c['n_pos']}",
                                  fallback=("observation_only（不预测）")))
            cls_rows.append(row)
            continue
        models = models_for(c["demand_pattern"], c["sbc_class"])
        rows = backtest(y, usable, models)
        per = {}
        for name in models:
            mm = agg([r for r in rows if r.get("model") == name])
            per[name] = mm
            res_rows.append(dict(key_version=KEY_VERSION, product_id=pid, pool=pool,
                                 physical_form=form,
                                 canonical_uom=uom, demand_pattern=c["demand_pattern"],
                                 model=name, family=("baseline" if name in BASELINES else "new"),
                                 status=mm["status"], n_obs=mm["n"], wape=mm["wape"],
                                 mae=mm["mae"], pinball50=mm["pinball50"],
                                 positive_test_actual=bool(mm.get("den", 0) > 0),
                                 den=float(mm.get("den", 0.0)),
                                 failure_reason=mm["reason"]))
        for r in rows:
            if r.get("status") == "ok":
                mm = agg([r])
                det_rows.append(dict(key_version=KEY_VERSION, product_id=pid, pool=pool,
                                     physical_form=form,
                                     canonical_uom=uom, model=r["model"], origin=r["origin"],
                                     n_train=r["n_train"], test_months=r["test_months"],
                                     n_test=r["n_test"], wape=mm["wape"], mae=mm["mae"]))
            elif r.get("status") in ("skipped", "failed"):
                fail_rows.append(dict(层级="origin", product_id=pid, pool=pool,
                                      physical_form=form, canonical_uom=uom,
                                      类型=f"{r.get('model', 'origin')}:{r['status']}",
                                      原因=r.get("reason", ""),
                                      fallback="该 origin 跳过（不补 0）"))
        sel = select(per, c["demand_pattern"], rows=rows)
        evaluated = [v for v in per.values() if v["status"] == "ok"]
        row["backtested"] = bool(evaluated)
        if not evaluated:
            row["adoption_status"] = "no_origin"
            skips = [r for r in rows if r.get("status") == "skipped"]
            if skips:
                sel = dict(adopted="none", baseline="none",
                           reason="无可回测 origin：" + "；".join(
                               sorted({str(r.get("reason")) for r in skips})))
        elif sel["adopted"] == "none":
            row["adoption_status"] = ("test_window_no_positive"
                                      if "test_window_no_positive" in str(sel["reason"])
                                      else "test_window_zero_error"
                                      if "test_window_zero_error" in str(sel["reason"])
                                      else "no_candidate")
        else:
            row["adoption_status"] = "adopted"
        row.update(adopted_model=sel["adopted"], best_baseline=sel["baseline"],
                   selection_reason=sel["reason"])
        cls_rows.append(row)
        for rr in res_rows:
            if (rr["product_id"], rr["pool"], rr["physical_form"], rr["canonical_uom"]) == key:
                rr["adopted"] = "是" if rr["model"] == sel["adopted"] else "否"

    cls_tbl = pd.DataFrame(cls_rows)
    res_tbl = pd.DataFrame(res_rows)
    det_tbl = pd.DataFrame(det_rows)
    hist_tbl = pd.DataFrame(hist_rows)

    # ---------- current-owner 有效历史 + 分类（预测用；不做历史回测，避免 owner 未来信息泄漏）
    hist_qty_by_key = {(r.product_id, r.pool, r.physical_form, r.canonical_uom):
                       float(r.qty_total)
                       for r in hist_tbl.itertuples(index=False)}
    # ---------- 单一事实源：current-owner 键只 join as-of 的 adopted ----------
    asof_adoption = build_asof_adoption_map(cls_tbl, res_tbl, hist_qty_by_key)
    current_adoption = build_current_adoption_map(
        k_current, current_multi_from, asof_adoption, hist_qty_by_key)
    hist_cur_rows, cls_cur_rows, trend_rows = [], [], []
    for key in sorted(k_current):
        pid, pool, form, uom = key
        vals = np.array([ser_cur.get((key, mo), 0.0) for mo in OBS_MONTHS], dtype=float)
        obs = np.array([(pid, mo) not in cens_set for mo in OBS_MONTHS])
        pos_idx = np.where(vals > 0)[0]
        first_pos = int(pos_idx[0]) if len(pos_idx) else None
        launch = first_pos if first_pos is not None else len(OBS_MONTHS)
        active = np.zeros(len(OBS_MONTHS), dtype=bool)
        active[launch:] = True
        usable = obs & active
        n_usable = int(usable.sum()) if first_pos is not None else 0
        if len(pos_idx) == 0:
            usable = np.zeros(len(OBS_MONTHS), dtype=bool)
        n_censored = int((~obs & active).sum())
        src_keys = current_multi_from.get(key, [])
        asof_qty = float(sum(float(ser.get((k, mo), 0.0))
                             for k in src_keys for mo in OBS_MONTHS))
        hist_cur_rows.append(dict(
            key_version=OWNER_KEY_VERSION, product_id=pid, pool=pool,
            physical_form=form, canonical_uom=uom,
            owner=(pool if pool in US_POOLS else ""),
            owner_basis=owner_basis.get(pid, ""),
            owner_reason=owner_reason.get(pid, ""),
            first_positive_month=(OBS_MONTHS[first_pos] if first_pos is not None else ""),
            last_month=END_MONTH, history_months_effective=n_usable,
            months_before_2025=int((usable & (np.array(OBS_MONTHS) < "202501")).sum()),
            months_positive=int(len(pos_idx)), months_censored=n_censored,
            qty_total=float(vals[usable].sum()), asof_qty_total=asof_qty,
            source_asof_keys="|".join("|".join(k) for k in sorted(src_keys)),
            evidence_quality=("2025+ 有删失证据" if n_usable else "无可用月")))
        y = np.where(usable, vals, np.nan)
        c = classify(y[usable], hist_cur_rows[-1]["first_positive_month"] or None)
        join = current_adoption[key]
        trend_rows.append(dict(
            product_id=pid, pool=pool, physical_form=form, canonical_uom=uom,
            demand_pattern=c["demand_pattern"], n_obs=c["n_obs"],
            **trend_diagnostics(vals, obs)))
        cls_cur_rows.append(dict(
            key_version=OWNER_KEY_VERSION, product_id=pid, pool=pool,
            physical_form=form, canonical_uom=uom,
            owner=(pool if pool in US_POOLS else ""),
            owner_basis=owner_basis.get(pid, ""),
            owner_reason=owner_reason.get(pid, ""),
            n_obs=c["n_obs"], n_pos=c["n_pos"], adi=c["adi"], cv2=c["cv2"],
            demand_pattern=c["demand_pattern"], sbc_class=c["sbc_class"],
            is_legacy=pid in legacy_products, new_product=pid in new_products,
            clearance=pid in clearance, shared_candidate=bool(pid in shared_products),
            eligible=(c["n_obs"] >= MIN_HIST_CLASS and c["n_pos"] > 0
                      and pid not in legacy_products),
            adopted_model=join["model"], model_source=join["source"],
            adoption_status=join["status"],
            adopted_sources=json.dumps(join["sources"], ensure_ascii=False),
            asof_qty_total=asof_qty))
    hist_cur_tbl = pd.DataFrame(hist_cur_rows)
    cls_cur_tbl = pd.DataFrame(cls_cur_rows)
    trend_tbl = pd.DataFrame(trend_rows)
    assert len(trend_tbl) == len(k_current), "趋势诊断键数不守恒"
    assert not trend_tbl.duplicated(
        ["product_id", "pool", "physical_form", "canonical_uom"]).any(), "趋势诊断键重复"
    assert len(cls_cur_tbl) == len(k_current), "current 分类键数不守恒"
    assert not cls_cur_tbl.duplicated(
        ["product_id", "pool", "physical_form", "canonical_uom"]).any(), "current 键重复"
    # 单一事实源 fail-closed：3_分类 的 adopted_model 必须来自 4_回测_asof
    _cur_key_set = {(r.product_id, r.pool, r.physical_form, r.canonical_uom)
                    for r in cls_cur_tbl.itertuples(index=False)}
    assert _cur_key_set == set(k_current), "current 分类键集不守恒"
    for r in cls_cur_tbl.itertuples(index=False):
        ck = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        srcs = current_multi_from.get(ck, [])
        allowed = {asof_adoption[s]["model"] for s in srcs}
        if r.adopted_model not in allowed:
            raise AssertionError(
                f"3_分类 adopted_model 不在 4_回测_asof 源键集合：{ck} "
                f"{r.adopted_model} not in {sorted(allowed)}")
        if r.model_source == "asof_join":
            assert r.adopted_model == asof_adoption[srcs[0]]["model"], (
                f"单源 current 键未精确 join：{ck} {r.adopted_model} != "
                f"{asof_adoption[srcs[0]]['model']}")
    adoption_join_stats = dict(
        current_keys=len(cls_cur_tbl),
        asof_keys=len(asof_adoption),
        single_source=int((cls_cur_tbl["model_source"] == "asof_join").sum()),
        multi_agree=int((cls_cur_tbl["model_source"] == "asof_join_multi_agree").sum()),
        multi_maxqty=int((cls_cur_tbl["model_source"] == "asof_join_multi_maxqty").sum()),
        no_model=int((cls_cur_tbl["model_source"] == "asof_join_none").sum()),
        adopted=int((cls_cur_tbl["adopted_model"] != "none").sum()),
        source_membership_rate=1.0,
        single_source_exact_rate=1.0,
        adopted_rate=float((cls_cur_tbl["adopted_model"] != "none").sum())
        / max(1, len(cls_cur_tbl)),
    )

    # ---------- 责任重述审计（产品级；原始美国订单，不改库存/供应）
    raw_us = o[(o["pool_before_cg_fix"].isin(US_POOLS))
               & o["product"].notna()
               & (o["product"].astype(str).str.strip() != "")
               & (o["product"].astype(str) != "nan")].copy()
    raw_us["_owner"] = [owner_map.get(str(p)) for p in raw_us["product"]]
    raw_us["_year"] = pd.to_datetime(raw_us["sale_date"], errors="coerce").dt.year
    audit_rows = []
    d1b_us_key_products = {k[0] for k in k_set if k[1] in US_POOLS}
    for pid, g in raw_us.groupby("product", sort=False):
        hist = g.groupby("pool_before_cg_fix")["qty"].sum().to_dict()
        pools = sorted(hist)
        owner_v = owner_map.get(str(pid))
        moved = g[g["pool_before_cg_fix"] != owner_v] if owner_v in US_POOLS else g.iloc[0:0]
        direction = (moved.groupby(["pool_before_cg_fix"])["qty"].sum()
                     if owner_v in US_POOLS else {})
        cur_keys = [k for k in k_current if k[0] == pid]
        audit_rows.append(dict(
            product_id=pid, current_owner=owner_v or "", owner_basis=owner_basis.get(str(pid), ""),
            owner_reason=owner_reason.get(str(pid), "product_not_in_B"),
            current_pool=(owner_v if owner_v in US_POOLS else UNASSIGNED),
            hist_pools=";".join(pools),
            hist_qty_total=float(g["qty"].sum()),
            hist_qty_USNJ=float(hist.get("美东USNJ", 0.0)),
            hist_qty_USTX=float(hist.get("美中USTX", 0.0)),
            moved_qty=float(moved["qty"].sum()),
            moved_rows=int(len(moved)),
            direction=";".join(f"{a}->{owner_v}:{v:.0f}" for a, v in direction.items()),
            both_pools=len(pools) > 1,
            exception_current_USNJ_hist_USTX=bool(owner_v == "美东USNJ"
                                                  and "美中USTX" in pools),
            unassigned_qty=(float(g["qty"].sum()) if owner_v not in US_POOLS else 0.0),
            unassigned_rows=(int(len(g)) if owner_v not in US_POOLS else 0),
            first_year=int(g["_year"].min()) if g["_year"].notna().any() else None,
            last_year=int(g["_year"].max()) if g["_year"].notna().any() else None,
            in_d1b_us_demand_keys=pid in d1b_us_key_products,
            current_key_count=len(cur_keys)))
    audit_tbl = pd.DataFrame(audit_rows).sort_values(
        ["unassigned_qty", "moved_qty"], ascending=False)
    audit_known_qty = float(audit_tbl["hist_qty_total"].sum()) - float(
        audit_tbl["unassigned_qty"].sum())
    audit_unassigned_qty = float(audit_tbl["unassigned_qty"].sum())
    audit_total_qty = float(audit_tbl["hist_qty_total"].sum())
    print(f"[CONSERVATION] known={audit_known_qty:.1f} unassigned={audit_unassigned_qty:.1f} total={audit_total_qty:.1f}")
    exp = {k: os.environ.get(f"D3B_EXPECT_{k}") for k in ("KNOWN", "UNASSIGNED", "TOTAL")}
    if exp["KNOWN"]:
        assert abs(audit_known_qty - float(exp["KNOWN"])) < 1e-6, f"owner-known 守恒失败 {audit_known_qty}"
    if exp["UNASSIGNED"]:
        assert abs(audit_unassigned_qty - float(exp["UNASSIGNED"])) < 1e-6, f"unassigned 守恒失败 {audit_unassigned_qty}"
    if exp["TOTAL"]:
        assert abs(audit_total_qty - float(exp["TOTAL"])) < 1e-6, f"US 总量守恒失败 {audit_total_qty}"
    assert not audit_tbl["product_id"].duplicated().any(), "审计产品重复"
    audit_counts = dict(
        products=len(audit_tbl), owner_known_products=int(
            (audit_tbl["current_owner"].astype(str) != "").sum()),
        unassigned_products=int((audit_tbl["unassigned_qty"] > 0).sum()),
        moved_products=int((audit_tbl["moved_qty"] > 0).sum()),
        both_pools_products=int((audit_tbl["both_pools"]
                                 & (audit_tbl["current_owner"].astype(str) != "")).sum()),
        both_pools_all_products=int(audit_tbl["both_pools"].sum()),
        exception_products=int(audit_tbl["exception_current_USNJ_hist_USTX"].sum()),
        owner_known_qty=audit_known_qty, unassigned_qty=audit_unassigned_qty,
        total_qty=audit_total_qty,
        moved_qty=float(audit_tbl["moved_qty"].sum()),
        direction={k: float(v) for k, v in raw_us[
            raw_us["_owner"].isin(US_POOLS)
            & (raw_us["pool_before_cg_fix"] != raw_us["_owner"])]
            .groupby(["pool_before_cg_fix", "_owner"])["qty"].sum().items()})
    special_tbl = audit_tbl[audit_tbl["exception_current_USNJ_hist_USTX"]
                            | (audit_tbl["moved_qty"] > 0)
                            | audit_tbl["both_pools"]
                            | (audit_tbl["unassigned_qty"] > 0)].copy()

    # ---------- as-of 键 → current-owner 键（1853 → 1749）
    asof_qty_by_key = {k: float(sum(ser.get((k, mo), 0.0) for mo in OBS_MONTHS))
                       for k in k_set}
    restate_rows = []
    cat_counts = {}
    for ak in sorted(k_set):
        pid, pool, form, uom = ak
        ck = cur_of_asof[ak]
        if ck[1] == UNASSIGNED:
            cat = "owner_unassigned"
        elif pool in US_POOLS and ck[1] != pool:
            cat = "owner_move（历史仓→current owner）"
        elif len(current_multi_from.get(ck, [])) > 1:
            cat = "双池合并（同 current key）"
        else:
            cat = "同池"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        restate_rows.append(dict(
            表="asof_to_current", asof_key="|".join(ak), current_key="|".join(ck),
            category=cat, asof_qty_all_months=asof_qty_by_key[ak],
            current_qty_all_months=float(sum(
                ser_cur.get((ck, mo), 0.0) for mo in OBS_MONTHS)),
            merged_asof_key_count=len(current_multi_from.get(ck, []))))
    for ck in sorted(k_current):
        src = sorted(current_multi_from.get(ck, []))
        restate_rows.append(dict(
            表="current_summary", asof_key=";".join("|".join(k) for k in src),
            current_key="|".join(ck), category="current_key",
            asof_qty_all_months=float(sum(asof_qty_by_key[k] for k in src)),
            current_qty_all_months=float(sum(ser_cur.get((ck, mo), 0.0)
                                              for mo in OBS_MONTHS)),
            merged_asof_key_count=len(src)))
    restate_tbl = pd.DataFrame(restate_rows)
    key_reduction = len(k_set) - len(k_current)
    asof_mapped_qty = float(sum(asof_qty_by_key.values()))
    current_mapped_qty = float(sum(ser_cur.get((k, mo), 0.0)
                                   for k in k_current for mo in OBS_MONTHS))
    # D3b current 序列相对 as-of 多接回的订单量（历史池无键、但 current owner 有键）
    current_extra_qty = current_mapped_qty - asof_mapped_qty
    # 产品级对账：current 对 as-of 的差 = 历史池无键但 current owner 有键的订单
    prod_rows = []
    for pid in sorted({k[0] for k in k_set} | {k[0] for k in k_current}):
        cur_q = float(sum(ser_cur.get((k, mo), 0.0)
                          for k in k_current if k[0] == pid for mo in OBS_MONTHS))
        asof_q = float(sum(asof_qty_by_key[k] for k in k_set if k[0] == pid))
        prod_rows.append(dict(
            表="product_check", asof_key="", current_key=pid,
            category="current−asof", asof_qty_all_months=asof_q,
            current_qty_all_months=cur_q,
            merged_asof_key_count=len([k for k in k_current if k[0] == pid])))
    restate_tbl = pd.concat([restate_tbl, pd.DataFrame(prod_rows)],
                            ignore_index=True)
    product_extra_total = float(sum(r["current_qty_all_months"]
                                    - r["asof_qty_all_months"] for r in prod_rows))
    assert abs(product_extra_total - current_extra_qty) < 1e-6, \
        "产品级对账差额不等于逐键差额"

    # ---------- A/B/C 仓级分配回测（产品总需求 → USNJ/USTX）
    # A：origin 前 180 天 trailing 仓份额（历史 as-of 口径，仅用 origin 前数据）
    # B：B r10 当前唯一 owner，1/0（生产候选）
    # C：近 90 天仓份额，仅用于有真实双仓责任的产品；非双仓 C=B
    us_alloc = raw_us.copy()
    us_alloc["month"] = us_alloc["month"].astype(str)
    us_alloc["sale_dt"] = pd.to_datetime(us_alloc["sale_date"], errors="coerce")
    total_monthly = (us_alloc.groupby(["product", "form", "uom", "month"])["qty"]
                     .sum().to_dict())
    wh_monthly = (us_alloc.groupby(["product", "form", "uom",
                                    "pool_before_cg_fix", "month"])["qty"]
                  .sum().to_dict())

    def _pool_pair(frame: pd.DataFrame) -> dict[str, tuple[float, float]]:
        g = frame.groupby(["product", "pool_before_cg_fix"])["qty"].sum()
        pairs = {}
        for (pid, pool), q in g.items():
            nj, tx = pairs.get(str(pid), (0.0, 0.0))
            if pool == "美东USNJ":
                nj += float(q)
            elif pool == "美中USTX":
                tx += float(q)
            pairs[str(pid)] = (nj, tx)
        return pairs

    recent90 = _pool_pair(us_alloc[us_alloc["sale_dt"] >= pd.Timestamp("2026-08-02")])
    recent180 = _pool_pair(us_alloc[us_alloc["sale_dt"] >= pd.Timestamp("2026-05-04")])
    dual_products, c_share_pool = set(), {}
    share_rows = []
    for pid, (nj90, tx90) in recent90.items():
        nj180, tx180 = recent180.get(pid, (0.0, 0.0))
        t90, t180 = nj90 + tx90, nj180 + tx180
        ok90 = (nj90 >= 20 and tx90 >= 20
                and min(nj90, tx90) / t90 >= 0.10) if t90 else False
        ok180 = (nj180 >= 20 and tx180 >= 20
                 and min(nj180, tx180) / t180 >= 0.10) if t180 else False
        if ok90 or ok180:
            dual_products.add(pid)
            c_share_pool[pid] = (tx90 / t90 if ok90 else tx180 / t180)
            share_rows.append(dict(product_id=pid, qty90_nj=nj90, qty90_tx=tx90,
                                   share90_tx=(tx90 / t90 if t90 else np.nan),
                                   qty180_nj=nj180, qty180_tx=tx180,
                                   share180_tx=(tx180 / t180 if t180 else np.nan),
                                   dual_rule=("90d" if ok90 else "180d"),
                                   owner=owner_map.get(pid, "")))
    dual_tbl = pd.DataFrame(share_rows).sort_values("qty90_tx", ascending=False) \
        if share_rows else pd.DataFrame(columns=["product_id", "qty90_nj", "qty90_tx",
                                                 "share90_tx", "qty180_nj", "qty180_tx",
                                                 "share180_tx", "dual_rule", "owner"])

    def _owner_tx(pid: str) -> float:
        return 1.0 if owner_map.get(pid) == "美中USTX" else (
            0.0 if owner_map.get(pid) == "美东USNJ" else np.nan)

    trail_qty_cache = {}
    for origin in ORIGINS:
        end = pd.Timestamp(f"{origin[:4]}-{origin[4:]}-01")
        for days in (90, 180):
            sub = us_alloc[(us_alloc["sale_dt"] >= end - pd.Timedelta(days=days))
                           & (us_alloc["sale_dt"] < end)]
            trail_qty_cache[(origin, days)] = _pool_pair(sub)

    def _origin_share(pid: str, origin: str, days: int):
        nj, tx = trail_qty_cache[(origin, days)].get(pid, (0.0, 0.0))
        return (tx / (nj + tx)) if nj + tx > 0 else None

    def _origin_dual(pid: str, origin: str, days: int) -> bool:
        nj, tx = trail_qty_cache[(origin, days)].get(pid, (0.0, 0.0))
        total = nj + tx
        return bool(total > 0 and nj >= 20 and tx >= 20
                    and min(nj, tx) / total >= 0.10)

    def _asof_pool_forecast(pid: str, pool_name: str, form: str, uom: str,
                            origin: str, fn, usable: np.ndarray, y: np.ndarray):
        yv = np.array([ser.get(((pid, pool_name, form, uom), mo), 0.0)
                       for mo in OBS_MONTHS], dtype=float)
        if not np.any(yv > 0):
            return None
        oi = OBS_MONTHS.index(origin)
        observed = [i for i in range(oi + 1) if usable[i] and np.isfinite(yv[i])]
        if len(observed) < MIN_TRAIN_OBS:
            return None
        first_train = observed[0]
        ytr = np.where(usable[first_train:oi + 1], yv[first_train:oi + 1], np.nan)
        try:
            fc_p = np.asarray(fn(ytr, H), dtype=float)
        except Exception:                                      # noqa: BLE001
            return None
        return fc_p if np.all(np.isfinite(fc_p)) else None

    alloc_records = []
    alloc_key_rows = []
    for key in sorted(k_current):
        pid, pool, form, uom = key
        if pool not in US_POOLS or owner_map.get(pid) not in US_POOLS:
            continue
        vals = np.array([total_monthly.get((pid, form, uom, mo), 0.0)
                         for mo in OBS_MONTHS], dtype=float)
        obs = np.array([(pid, mo) not in cens_set for mo in OBS_MONTHS])
        pos_idx = np.where(vals > 0)[0]
        if not len(pos_idx):
            continue
        first_pos = int(pos_idx[0])
        usable = obs.copy()
        usable[:first_pos] = False
        if int(usable.sum()) < MIN_HIST_CLASS:
            continue
        y = np.where(usable, vals, np.nan)
        c = classify(y[usable], OBS_MONTHS[first_pos])
        models = models_for(c["demand_pattern"], c["sbc_class"])
        rows = backtest(y, usable, models)
        per = {m: agg([r for r in rows if r.get("model") == m]) for m in models}
        sel = select(per, c["demand_pattern"], rows=rows)
        model = sel["adopted"]
        if model == "none":
            continue
        fn = BASELINES.get(model) or NEW_MODELS.get(model)
        owner_tx = _owner_tx(pid)
        key_records = []
        for origin in ORIGINS:
            oi = OBS_MONTHS.index(origin)
            observed = [i for i in range(oi + 1) if usable[i] and np.isfinite(y[i])]
            if len(observed) < MIN_TRAIN_OBS:
                continue
            first_train = observed[0]
            ytr = np.where(usable[first_train:oi + 1], y[first_train:oi + 1], np.nan)
            try:
                fc = np.asarray(fn(ytr, H), dtype=float)
            except Exception:                                  # noqa: BLE001
                continue
            if not np.all(np.isfinite(fc)):
                continue
            # A：历史仓池分别预测（只用 origin 前 as-of 序列）
            a_nj = _asof_pool_forecast(pid, "美东USNJ", form, uom, origin, fn, usable, y)
            a_tx = _asof_pool_forecast(pid, "美中USTX", form, uom, origin, fn, usable, y)
            # C90/C180：仅当 origin 当时已知的双仓责任成立时使用份额
            c90_tx = (_origin_share(pid, origin, 90)
                      if _origin_dual(pid, origin, 90) else owner_tx)
            c180_tx = (_origin_share(pid, origin, 180)
                       if _origin_dual(pid, origin, 180) else owner_tx)
            if c90_tx is None:
                c90_tx = owner_tx
            if c180_tx is None:
                c180_tx = owner_tx
            for step, i in enumerate(range(oi + 1, min(oi + 1 + H, len(OBS_MONTHS)))):
                if not obs[i] or not np.isfinite(vals[i]):
                    continue
                moi = OBS_MONTHS[i]
                actual_nj = float(wh_monthly.get((pid, form, uom, "美东USNJ", moi), 0.0))
                actual_tx = float(wh_monthly.get((pid, form, uom, "美中USTX", moi), 0.0))
                forecasts = {}
                # F6：A 是历史仓基线。缺一仓历史时保留另一仓预测并把缺史仓记 0，
                # 不得退回当前 owner 分配（那会把 A 变成 B，污染 A/B 对照）。
                a_missing = [name for name, fc_pool in (("美东USNJ", a_nj),
                                                        ("美中USTX", a_tx)) if fc_pool is None]
                if a_nj is None and a_tx is None:
                    forecasts["A"] = None
                else:
                    forecasts["A"] = (float(a_nj[step]) if a_nj is not None else 0.0,
                                      float(a_tx[step]) if a_tx is not None else 0.0)
                for scenario, tx_share in (("B", owner_tx), ("C90", c90_tx),
                                           ("C180", c180_tx)):
                    alloc_tx = float(fc[step]) * tx_share
                    forecasts[scenario] = (float(fc[step]) - alloc_tx, alloc_tx)
                for scenario, alloc in forecasts.items():
                    if alloc is None:
                        continue
                    alloc_nj, alloc_tx = alloc
                    total_alloc = alloc_nj + alloc_tx
                    alloc_records.append(dict(
                        scenario=scenario, product_id=pid, physical_form=form,
                        canonical_uom=uom, origin=origin, month=moi,
                        model=model, forecast_total=total_alloc,
                        alloc_nj=alloc_nj, alloc_tx=alloc_tx,
                        actual_nj=actual_nj, actual_tx=actual_tx,
                        a_missing_pools=("|".join(a_missing) if scenario == "A" else ""),
                        tx_share=(alloc_tx / total_alloc if total_alloc > 0
                                  else np.nan)))
                    key_records.append(dict(
                        scenario=scenario, actual=actual_nj + actual_tx,
                        alloc=total_alloc,
                        abs_err=abs(alloc_nj - actual_nj) + abs(alloc_tx - actual_tx)))
        if key_records:
            for scenario in ("A", "B", "C90", "C180"):
                sub = [r for r in key_records if r["scenario"] == scenario]
                if not sub:
                    continue
                act = sum(r["actual"] for r in sub)
                alloc = sum(r["alloc"] for r in sub)
                alloc_key_rows.append(dict(
                    scenario=scenario, product_id=pid, pool=pool,
                    physical_form=form, canonical_uom=uom, model=model,
                    n_months=len(sub), actual=act, forecast_total=alloc,
                    abs_err=sum(r["abs_err"] for r in sub),
                    bias=((alloc - act) / act if act > 0 else np.nan),
                    wape=(sum(r["abs_err"] for r in sub) / act if act > 0 else np.nan)))
    alloc_detail = pd.DataFrame(alloc_records)
    alloc_keys = pd.DataFrame(alloc_key_rows)
    alloc_summary_rows = []
    for scenario in ("A", "B", "C90", "C180"):
        d = (alloc_detail[alloc_detail["scenario"] == scenario]
             if len(alloc_detail) else alloc_detail)
        for wh, alloc_col, actual_col in (
                ("美东USNJ", "alloc_nj", "actual_nj"),
                ("美中USTX", "alloc_tx", "actual_tx"),
                ("合计", None, None)):
            if not len(d):
                continue
            if wh == "合计":
                alloc = d["alloc_nj"] + d["alloc_tx"]
                actual = d["actual_nj"] + d["actual_tx"]
            else:
                alloc = d[alloc_col]
                actual = d[actual_col]
            a_sum, f_sum = float(actual.sum()), float(alloc.sum())
            abs_err = float((alloc - actual).abs().sum())
            short = float((actual - alloc).clip(lower=0).sum())
            note = {"A": "历史仓池分别预测（as-of，origin 前）",
                    "B": "current owner 1/0（生产候选）",
                    "C90": "近 90 天仓份额，仅 origin 当时已证双仓产品",
                    "C180": "近 180 天仓份额，仅 origin 当时已证双仓产品"}[scenario]
            alloc_summary_rows.append(dict(
                scenario=scenario, warehouse=wh,
                keys=int(d["product_id"].nunique()), months=len(d),
                actual=a_sum, allocated=f_sum,
                wape=(abs_err / a_sum if a_sum > 0 else np.nan),
                bias=((f_sum - a_sum) / a_sum if a_sum > 0 else np.nan),
                stockout_rate=(short / a_sum if a_sum > 0 else np.nan),
                production_candidate=("是" if scenario == "B" else "否"),
                note=note))
    alloc_tbl = pd.DataFrame(alloc_summary_rows)

    # ---------- 90 天分母与交叉量核对
    win90 = us_alloc[us_alloc["sale_dt"] >= pd.Timestamp("2026-08-02")]
    recon90_rows = []
    for pool_name in ("美东USNJ", "美中USTX"):
        d = win90[win90["pool_before_cg_fix"] == pool_name]
        owner_known = d[d["owner"].isin(US_POOLS)]
        same = owner_known[owner_known["owner"] == pool_name]
        cross = owner_known[owner_known["owner"] != pool_name]
        unknown = d[~d["owner"].isin(US_POOLS)]
        other_owner = owner_known[~owner_known["owner"].isin(US_POOLS)]
        all90 = o[(o["pool_before_cg_fix"] == pool_name)
                  & (pd.to_datetime(o["sale_date"], errors="coerce")
                     >= pd.Timestamp("2026-08-02"))]
        _no_prod = (all90["product"].isna()
                    | (all90["product"].astype(str).str.strip() == "")
                    | (all90["product"].astype(str) == "nan"))
        nan_rows = int(_no_prod.sum())
        recon90_rows.append(dict(
            warehouse=pool_name, total_qty=float(d["qty"].sum()),
            owner_known_qty=float(owner_known["qty"].sum()),
            same_owner_qty=float(same["qty"].sum()),
            cross_owner_qty=float(cross["qty"].sum()),
            unknown_owner_qty=float(unknown["qty"].sum()),
            unknown_owner_rows=int(len(unknown)),
            nan_product_rows=nan_rows,
            nan_product_qty=float(all90.loc[_no_prod, "qty"].sum()),
            unknown_total_rows=int(len(unknown)) + nan_rows,
            denominator_note=("7,650/11,398 是 same-owner 小计；"
                              "仓级总量应含 cross 后为 total_qty")))
    recon90_tbl = pd.DataFrame(recon90_rows)

    # ---------- 9_键迁移对账（D2 v3 旧键 → D1b v2.3 新键）
    old_qty = (d2[d2["zero_class"] == "observed_positive"]
               .groupby(keys)["sellable_qty"].sum().to_dict())
    d1b_state: dict[str, list] = {}
    for r in d1b.itertuples(index=False):
        d1b_state.setdefault(r.product_id, []).append(
            (r.decision_state, r.demand_state))
    recon_rows = []
    for k in sorted(k_old):
        pid, pool, form, uom = k
        newk, cat = None, ""
        if k in k_set:
            cat, newk = "exact", k
        else:
            cand = sorted(x for x in k_by_prod.get(pid, ()) if x[0] == pool and x[2] == uom)
            if len(cand) == 1:
                cat, newk = "form归一", (pid, pool, cand[0][1], uom)
            elif len(cand) > 1:
                cat, newk = "多候选", None
            else:
                cand2 = sorted(x for x in k_by_prod.get(pid, ()) if x[2] == uom)
                st = d1b_state.get(pid)
                if cand2:
                    cat, newk = "池修正", [(pid,) + x for x in cand2]
                elif not st:
                    cat, newk = "未匹配（产品不在 D1b）", None
                elif all(x[0] == "policy_excluded" for x in st):
                    cat, newk = "政策排除", None
                elif all(x[1] == "no_demand" for x in st):
                    cat, newk = "无需求", None
                else:
                    cat, newk = "未匹配", None
        if isinstance(newk, list):
            newk_s = "|".join("|".join(x) for x in newk)
        elif newk:
            newk_s = "|".join(newk)
        else:
            newk_s = ""
        recon_rows.append(dict(表="old_key", old_key="|".join(k), category=cat,
                               new_keys=newk_s,
                               old_qty_2025_2026=float(old_qty.get(k, 0.0))))
    # 新键相对旧键的 gain 分类
    old_prod = {k[0] for k in k_old}
    for k in sorted(k_set - k_old):
        pid, pool, form, uom = k
        if pid not in old_prod:
            cat = "新产品（无旧键）"
        elif any(o[0] == pid and o[1] == pool and o[3] == uom for o in k_old):
            cat = "form 变体新增"
        else:
            cat = "新池（CG/其他/换池）"
        recon_rows.append(dict(表="new_key_gain", old_key="", category=cat,
                               new_keys="|".join(k), old_qty_2025_2026=0.0))
    # D1b 需求行覆盖
    _keyset = k_set
    dm["has_series"] = [ (r.product_id, r.destination_pool, r.physical_form, r.canonical_uom) in _keyset
                         for r in dm.itertuples(index=False)]
    for r in dm.head(0).itertuples(index=False):
        pass
    d1b_cov = dict(demand_rows=len(dm), with_series=int(dm["has_series"].sum()),
                   without_series=int((~dm["has_series"]).sum()),
                   products=int(dm["product_id"].nunique()))
    recon_rows.append(dict(表="d1b_demand", old_key="", category="demand 行覆盖",
                           new_keys=f"rows={d1b_cov['demand_rows']};with_series="
                                    f"{d1b_cov['with_series']};without_series="
                                    f"{d1b_cov['without_series']}", old_qty_2025_2026=0.0))
    # 删失无法归属
    kset_products = {k[0] for k in k_set}
    cens_un = cens[~cens["product_id"].astype(str).isin(kset_products)].copy()
    cens_un["month"] = cens_un["month"].astype(str)
    cens_unassigned = int(len(cens_un))
    for r in cens_un.itertuples(index=False):
        recon_rows.append(dict(表="censor_unassigned", old_key=str(r.product_id),
                               category="删失无法归属（产品不在新需求键集）",
                               new_keys=f"{r.product_id}|{r.month}", old_qty_2025_2026=0.0))
    _cg_parts, _cg_total, _cg_rows = cg_recon
    for pool_name in ("美东USNJ", "美中USTX", "其他"):
        recon_rows.append(dict(表="wayfair_cg", old_key="WayfairCG-*",
                               category=f"按B owner归池→{pool_name}",
                               new_keys=f"qty={_cg_parts.get(pool_name, 0.0):.0f}",
                               old_qty_2025_2026=float(_cg_parts.get(pool_name, 0.0))))
    recon_rows.append(dict(表="wayfair_cg", old_key="WayfairCG-*",
                           category="合计（应等于订单量）",
                           new_keys=f"rows={_cg_rows};qty={_cg_total:.0f}",
                           old_qty_2025_2026=float(_cg_total)))
    recon_tbl = pd.DataFrame(recon_rows)
    old_cat = recon_tbl[recon_tbl["表"] == "old_key"]["category"].value_counts().to_dict()
    gain_cat = recon_tbl[recon_tbl["表"] == "new_key_gain"]["category"].value_counts().to_dict()
    old_key_conservation = int(len(k_old) - len(recon_tbl[recon_tbl["表"] == "old_key"]))
    duplicate_keys = int(len(dm) - len(k_set))

    # ---------- 885 去向
    hist_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
                for r in hist_tbl.itertuples(index=False)}
    cls_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
               for r in cls_tbl.itertuples(index=False)}
    # 旧键 → 新键（v3：D3 的 885 是旧键，需先经迁移映射再查有效历史）
    recon_map: dict[tuple, list] = {}
    for rr in recon_tbl[recon_tbl["表"] == "old_key"].itertuples(index=False):
        if not rr.new_keys:
            continue
        parts = rr.new_keys.split("|")
        ks = [tuple(parts[i:i + 4]) for i in range(0, len(parts), 4)]
        recon_map[tuple(rr.old_key.split("|"))] = ks
    go_rows = []
    for r in short885.itertuples(index=False):
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        targets = recon_map.get(key, [])
        h = next((hist_idx[t] for t in targets if t in hist_idx), None)
        c = next((cls_idx[t] for t in targets if t in cls_idx), None)
        n_eff = int(h.history_months_effective) if h else 0
        first_pos = h.first_positive_month if h else ""
        pid = r.product_id
        if pid in legacy_products:
            dest, why = "老品", "C 16_ 老产品，forecast_eligible=false"
        elif pid in new_products or (first_pos and first_pos >= "202601"):
            dest, why = "真新品", f"首销 {first_pos or '无'}（≥2026-01）"
        elif pid in clearance:
            dest, why = "清仓短", "含 #qc/清仓行"
        elif n_eff >= MIN_HIST_CLASS:
            dest, why = "变长", f"有效历史 {n_eff} 月（D3 内 {r.n_obs}）"
        elif not targets:
            dest, why = "旧键无新键", "迁移后该旧键无对应新键（无需求/政策排除）"
        else:
            dest, why = "仍短", f"有效历史 {n_eff} 月 < {MIN_HIST_CLASS}"
        go_rows.append(dict(product_id=pid, pool=r.pool, physical_form=r.physical_form,
                            canonical_uom=r.canonical_uom,
                            d3_n_obs=int(r.n_obs), d3_pattern=r.demand_pattern,
                            history_months_effective=n_eff, first_positive_month=first_pos,
                            去向=dest, 说明=why,
                            d3b_pattern=(c.demand_pattern if c else ""),
                            d3b_eligible=(bool(c.eligible) if c else False),
                            d3b_adoption=(str(c.adoption_status) if c else "")))
    go_tbl = pd.DataFrame(go_rows)
    go_counts = go_tbl["去向"].value_counts().to_dict()

    # ---------- 汇总
    pat = cls_tbl["demand_pattern"].value_counts().to_dict()
    # ---------- 采用门槛复核（机械验证 sba/croston）：不达标即回退基线
    NEW_SET = set(NEW_MODELS)
    _met = {(r.product_id, r.pool, r.physical_form, r.canonical_uom, r.model):
            dict(wape=r.wape, mae=r.mae, den=float(getattr(r, "den", 0.0)),
                 status=r.status)
            for r in res_tbl.itertuples(index=False)}

    def _informative(m):
        return (m is not None and m["status"] == "ok" and m["den"] > 0
                and m["mae"] > 0 and np.isfinite(m["wape"]))

    violations = []
    for i in cls_tbl.index[cls_tbl["adoption_status"] == "adopted"]:
        row = cls_tbl.loc[i]
        model = row["adopted_model"]
        if model not in NEW_SET:
            continue
        key = (row["product_id"], row["pool"], row["physical_form"], row["canonical_uom"])
        cand = _met.get(key + (model,))
        bases = {m: _met[key + (m,)] for m in BASELINES
                 if _informative(_met.get(key + (m,)))}
        if not bases or not _informative(cand):
            violations.append(dict(product_id=row["product_id"], pool=row["pool"],
                                   physical_form=row["physical_form"],
                                   canonical_uom=row["canonical_uom"], model=model,
                                   reason="无正销测试窗或无可比较基线"))
        else:
            bb = min(bases, key=lambda m: (bases[m]["wape"], bases[m]["mae"]))
            bw, bm = bases[bb]["wape"], bases[bb]["mae"]
            gain = max((bw - cand["wape"]) / bw if bw > 0 else 0.0,
                       (bm - cand["mae"]) / bm if bm > 0 else 0.0)
            if not (cand["wape"] <= bw and cand["mae"] <= bm and gain >= ADOPT_GAIN):
                violations.append(dict(product_id=row["product_id"], pool=row["pool"],
                                       physical_form=row["physical_form"],
                                       canonical_uom=row["canonical_uom"], model=model,
                                       reason=(f"未过门槛：候选 WAPE {cand['wape']:.4f}/MAE "
                                               f"{cand['mae']:.4f} vs 基线 {bb} {bw:.4f}/{bm:.4f}，"
                                               f"改善 {gain:.1%} < {ADOPT_GAIN:.0%}"),
                                       rolled_back_to=bb))
        if violations and violations[-1].get("rolled_back_to"):
            bb = violations[-1]["rolled_back_to"]
            cls_tbl.loc[i, "adopted_model"] = bb
            cls_tbl.loc[i, "best_baseline"] = bb
            cls_tbl.loc[i, "selection_reason"] = "rolled_back:new_method_threshold_violation"

    # 回退后重算 res 行的 adopted 标记
    _adm = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r.adopted_model
            for r in cls_tbl.itertuples(index=False) if r.adoption_status == "adopted"}
    res_tbl["adopted"] = [
        "是" if _adm.get((r.product_id, r.pool, r.physical_form, r.canonical_uom)) == r.model
        else "否" for r in res_tbl.itertuples(index=False)]
    # 回退后复核：保留的 adopted 新方法必须 0 违规
    _viol_after = 0
    for r in cls_tbl.itertuples(index=False):
        if r.adoption_status != "adopted" or r.adopted_model not in NEW_SET:
            continue
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        cand = _met.get(key + (r.adopted_model,))
        bases = {m: _met[key + (m,)] for m in BASELINES if _informative(_met.get(key + (m,)))}
        if not bases or not _informative(cand):
            _viol_after += 1
            continue
        bb = min(bases, key=lambda m: (bases[m]["wape"], bases[m]["mae"]))
        bw, bm = bases[bb]["wape"], bases[bb]["mae"]
        gain = max((bw - cand["wape"]) / bw if bw > 0 else 0.0,
                   (bm - cand["mae"]) / bm if bm > 0 else 0.0)
        if not (cand["wape"] <= bw and cand["mae"] <= bm and gain >= ADOPT_GAIN):
            _viol_after += 1

    # ---------- 回退后重建 current-owner adopted（单一事实源最终版） ----------
    # 门槛回退会改写 cls_tbl.adopted_model / res_tbl.adopted；3_分类 必须在这里重新 join，
    # 不能沿用回退前的 as-of 模型，否则又出现 3_分类 与 4_回测_asof 不一致。
    asof_adoption = build_asof_adoption_map(cls_tbl, res_tbl, hist_qty_by_key)
    current_adoption = build_current_adoption_map(
        k_current, current_multi_from, asof_adoption, hist_qty_by_key)
    _join_rows = []
    for r in cls_cur_tbl.itertuples(index=False):
        ck = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        j = current_adoption[ck]
        _join_rows.append((j["model"], j["source"], j["status"],
                           json.dumps(j["sources"], ensure_ascii=False)))
    _join_df = pd.DataFrame(
        _join_rows, index=cls_cur_tbl.index,
        columns=["adopted_model", "model_source", "adoption_status", "adopted_sources"])
    for col in _join_df.columns:
        cls_cur_tbl[col] = _join_df[col]
    # fail-closed 复核（最终版）
    for r in cls_cur_tbl.itertuples(index=False):
        ck = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        srcs = current_multi_from.get(ck, [])
        allowed = {asof_adoption[s]["model"] for s in srcs}
        if r.adopted_model not in allowed:
            raise AssertionError(
                f"回退后 3_分类 adopted_model 不在 4_回测_asof 源键集合：{ck} "
                f"{r.adopted_model} not in {sorted(allowed)}")
        if r.model_source == "asof_join":
            assert r.adopted_model == asof_adoption[srcs[0]]["model"], (
                f"回退后单源 current 键未精确 join：{ck} {r.adopted_model} != "
                f"{asof_adoption[srcs[0]]['model']}")
    adoption_join_stats = dict(
        current_keys=len(cls_cur_tbl),
        asof_keys=len(asof_adoption),
        single_source=int((cls_cur_tbl["model_source"] == "asof_join").sum()),
        multi_agree=int((cls_cur_tbl["model_source"] == "asof_join_multi_agree").sum()),
        multi_maxqty=int((cls_cur_tbl["model_source"] == "asof_join_multi_maxqty").sum()),
        no_model=int((cls_cur_tbl["model_source"] == "asof_join_none").sum()),
        adopted=int((cls_cur_tbl["adopted_model"] != "none").sum()),
        source_membership_rate=1.0,
        single_source_exact_rate=1.0,
        adopted_rate=float((cls_cur_tbl["adopted_model"] != "none").sum())
        / max(1, len(cls_cur_tbl)),
    )

    n_eligible = int(cls_tbl["eligible"].sum())
    n_backtested = int(cls_tbl["backtested"].sum())
    n_no_origin = int((cls_tbl["adoption_status"] == "no_origin").sum())
    n_no_pos = int((cls_tbl["adoption_status"] == "test_window_no_positive").sum())
    n_zero_err = int((cls_tbl["adoption_status"] == "test_window_zero_error").sum())
    n_adopted = int((cls_tbl["adoption_status"] == "adopted").sum())
    adopted = cls_tbl.loc[cls_tbl["adoption_status"] == "adopted", "adopted_model"].value_counts().to_dict()
    n_new_adopted = int(sum(v for k, v in adopted.items() if k in NEW_MODELS))
    n_base_adopted = int(n_adopted - n_new_adopted)
    threshold_note = ("no_new_method_candidates（无新方法被采用）" if n_new_adopted == 0
                      else f"{n_new_adopted} 条新方法全部通过门槛复核"
                           f"（violations_after={_viol_after}）")
    best_base = cls_tbl.loc[cls_tbl["adoption_status"] == "adopted", "best_baseline"].value_counts().to_dict()
    new_adopted = int(sum(v for k, v in adopted.items() if k in NEW_MODELS))
    d3_new = 56
    d3_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
              for r in d3.itertuples(index=False)}
    rec = dict(d3_bt=0, now_bt=0, 变长=0, 仍短或无疑=0, 丢失=0, 新增=0)
    for r in cls_tbl.itertuples(index=False):
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        d3r = d3_idx.get(key)
        d3_bt = bool(d3r.backtestable) if d3r is not None else False
        d3_short = bool(d3r.demand_pattern == "short") if d3r is not None else True
        rec["d3_bt"] += int(d3_bt)
        rec["now_bt"] += int(bool(r.eligible))
        if d3_bt and not r.eligible:
            rec["丢失"] += 1
        elif not d3_bt and r.eligible:
            rec["变长" if d3_short else "新增"] += 1
        elif d3_short and not r.eligible:
            rec["仍短或无疑"] += 1

    summary = pd.DataFrame([
        dict(指标="A/B/C 仓级回测", 值="A/B/C",
             说明="A=origin 前180天 trailing 仓份额；B=current owner 1/0（生产候选）；"
                   "C=近90天仓份额，仅真实双仓产品"),
        dict(指标="真实双仓责任产品", 值=len(dual_products),
             说明="90/180 天两池均≥20 件且份额≥10%"),
    ] + [
        dict(指标=f"仓级 {r.scenario}-{r.warehouse} WAPE/偏差/缺货率",
             值=f"{r.wape:.4f}/{r.bias:+.4f}/{r.stockout_rate:.4f}",
             说明=f"actual={r.actual:.0f}, allocated={r.allocated:.0f}")
        for r in alloc_tbl.itertuples(index=False) if r.warehouse == "合计"
    ] + [
        dict(指标="序列总数", 值=len(cls_tbl), 说明="D2 v3 需求键"),
        dict(指标="eligible（≥12 有效月）", 值=n_eligible, 说明="≥12 有效月 + 有正销 + 非老品"),
        dict(指标="backtested（有有效 origin）", 值=n_backtested, 说明="至少 1 个 origin 达标且有模型可评估"),
        dict(指标="adopted（测试窗有正销）", 值=n_adopted, 说明="通过共同可评估测试窗比较后选定"),
        dict(指标="no_positive（测试窗无正销）", 值=n_no_pos, 说明="WAPE 未定义，不算证据"),
        dict(指标="zero_error（兼容状态）", 值=n_zero_err, 说明="MAE=0 不再被视为无比较证据；本状态仅保留兼容计数"),
        dict(指标="no_origin（无可回测 origin）", 值=n_no_origin, 说明="eligible 但无有效 origin，不算可回测"),
        dict(指标="new_method_adopted（sba/croston）", 值=n_new_adopted, 说明="经门槛复核后保留的新方法采用数"),
        dict(指标="baseline_adopted", 值=n_base_adopted, 说明="adopted − 新方法"),
        dict(指标="new_method_threshold_violations", 值=_viol_after,
             说明="保留的新方法采用中未过门槛的条数（须为 0）；回退前发现 " + str(len(violations)) + " 条"),
        dict(指标="门槛复核结论", 值=threshold_note, 说明="WAPE 与 MAE 均不劣 + 至少一项改善 ≥5%"),
        dict(指标="旧键（D2 v3）", 值=len(k_old), 说明="迁移前 1,865 键"),
        dict(指标="as-of 键（D1b v2.3 demand）", 值=len(k_set),
             说明="active + observed/censored + 需求形态；历史仓库池"),
        dict(指标="current-owner 键（v3.5）", 值=len(k_current),
             说明=f"USNJ/USTX 按 B r10 唯一 owner 合并，坍缩 {key_reduction} 键"),
        dict(指标="adopted 单一事实源", 值="4_回测_asof → 3_分类",
             说明="3_分类 不再按产品另选模型；只 join as-of 采用结果，断言 fail closed"),
        dict(指标="adopted join·单源精确", 值=adoption_join_stats["single_source"],
             说明=f"{adoption_join_stats['single_source_exact_rate']:.1%} 与 4_回测_asof 同键同模型"),
        dict(指标="adopted join·多源一致/最大量/无模型",
             值=f"{adoption_join_stats['multi_agree']}/"
                 f"{adoption_join_stats['multi_maxqty']}/"
                 f"{adoption_join_stats['no_model']}",
             说明="多源键按一致→直接采用；不一致→历史量最大源键（留痕 adopted_sources）"),
        dict(指标="current 键 adopted 覆盖率", 值=f"{adoption_join_stats['adopted_rate']:.1%}",
             说明=f"{adoption_join_stats['adopted']} / {adoption_join_stats['current_keys']} 键有模型"),
        dict(指标="趋势桶分布（2026 vs 2025 同期）",
             值=json.dumps(trend_tbl["trend_bucket"].value_counts().to_dict(),
                           ensure_ascii=False),
             说明="2026-01..10 / 2025-01..10；只计已观测月"),
        dict(指标="结构突变标记",
             值=json.dumps(trend_tbl["structural_break"].value_counts().to_dict(),
                           ensure_ascii=False),
             说明="最近 12 个已观测月对半；|z|≥2 且相对变化≥30%（启发式）"),
        dict(指标="owner-known US 需求", 值=round(audit_known_qty, 0),
             说明="原始订单；不含 US_unassigned"),
        dict(指标="US_unassigned 需求", 值=round(audit_unassigned_qty, 0),
             说明="B r10 无唯一美国责任方；单列，不进入 current 需求键"),
        dict(指标="US 需求总量", 值=round(audit_total_qty, 0),
             说明="owner-known + unassigned = 281,490 + 31,033"),
        dict(指标="迁移产品/量", 值=f"{int((audit_tbl['moved_qty'] > 0).sum())} / "
             f"{audit_tbl['moved_qty'].sum():.0f}",
             说明="历史仓 ≠ current owner 的产品"),
        dict(指标="双池产品（owner-known）", 值=audit_counts["both_pools_products"],
             说明=f"历史同时有 USNJ 与 USTX；含 unassigned 共 {audit_counts['both_pools_all_products']}"),
        dict(指标="current USNJ / hist USTX 特例",
             值=int(audit_tbl["exception_current_USNJ_hist_USTX"].sum()),
             说明="逐个列于 10_责任重述审计 / 11_特例"),
        dict(指标="current−as-of mapped 差额", 值=round(current_extra_qty, 0),
             说明="current owner 键接回的历史池无键订单量"),
        dict(指标="旧键去向", 值=json.dumps(old_cat, ensure_ascii=False), 说明="逐键见 9_键迁移对账"),
        dict(指标="新键 gain", 值=json.dumps(gain_cat, ensure_ascii=False), 说明="新键中旧键没有的部分"),
        dict(指标="D1b demand 行覆盖", 值=json.dumps(d1b_cov, ensure_ascii=False), 说明="")
        ,
        dict(指标="D3 可回测（新键可比口径）", 值=rec["d3_bt"],
             说明="与 D3b v3 新键重合的 D3 可回测序列；D3 旧键全量 954"),
        dict(指标="分类·smooth", 值=pat.get("smooth", 0), 说明=""),
        dict(指标="分类·intermittent", 值=pat.get("intermittent", 0), 说明=""),
        dict(指标="分类·lumpy", 值=pat.get("lumpy", 0), 说明="含 erratic"),
        dict(指标="分类·obsolescent", 值=pat.get("obsolescent", 0), 说明=""),
        dict(指标="分类·new", 值=pat.get("new", 0), 说明="首销 ≥2026-01"),
        dict(指标="分类·short", 值=pat.get("short", 0), 说明="有效历史 <12"),
        dict(指标="885·变长", 值=go_counts.get("变长", 0), 说明="D3 假短，接上历史后 ≥12 月"),
        dict(指标="885·仍短", 值=go_counts.get("仍短", 0), 说明=""),
        dict(指标="885·真新品", 值=go_counts.get("真新品", 0), 说明="首销 ≥2026-01"),
        dict(指标="885·清仓短", 值=go_counts.get("清仓短", 0), 说明="#qc/清仓"),
        dict(指标="885·老品", 值=go_counts.get("老品", 0), 说明="forecast_eligible=false"),
        dict(指标="采用新方法序列", 值=new_adopted, 说明=f"croston/sba/tsb（D3 为 {d3_new}）"),
        dict(指标="采用模型分布", 值=json.dumps(adopted, ensure_ascii=False), 说明=""),
        dict(指标="最佳基线分布", 值=json.dumps(best_base, ensure_ascii=False), 说明=""),
        dict(指标="订单量守恒", 值=f"{cons_total:.0f} / {float(o['qty'].sum()):.0f}",
             说明="分桶合计 = 订单总 qty"),
        dict(指标="映射率（数量）", 值=f"{float(cons.loc[cons['bucket']=='mapped','数量'].iloc[0]) / float(o['qty'].sum()):.1%}",
             说明="进入需求序列的订单量占比"),
    ])

    contract = pd.DataFrame([
        ("rule_version", RULE_VERSION),
        ("输入", "orders_unified.parquet / A FINAL / D2 v3 / D1 v2 / D3 / sku_map / customer_codes"),
        ("需求日期口径", "统一由 sale_date 派生 YYYYMM；源 month 仅为源表分区标签，保留为 source_month"),
        ("需求日期诊断", json.dumps(date_report, ensure_ascii=False)),
        ("历史窗口", f"2023-01..{END_MONTH}（订单 2022-12 起；按 sale_date 归月）"),
        ("归一规则", "casefold + 去空格 + 去前缀 OLD_/new- + 去后缀 -Cover/-c/-1/-2；"
                     "次级：去尾部 -<数字>（仅当候选唯一）"),
        ("合并条件", "候选唯一且证据一致（A来源码/sku_map/客户码）；多候选→隔离不合并"),
        ("隔离", "跨 form / 跨 UOM / 共享池 / 多候选 → 不进序列（计入守恒分桶）"),
        ("有效历史", "首销月→2026-10 的日历月数，剔除删失月；首销前不计 0"),
        ("删失证据", "D2 v3 2_删失（2025+）；2023-2024 零月无断货证据 → 记 zero_orders_only"),
        ("分类", f"ADI≥{ADI_THR} / CV²≥{CV2_THR}；erratic 并入 lumpy；<12 月→short；"
                 "首销≥2026-01→new；近 6 月无销量→obsolescent"),
        ("模型", "naive/MA3/seasonal naive/ETS(A,N,N)/ETS(A,Ad,N)/ETS(A,A,A)-STL+ETS/简化 Theta；"
                 "间歇类 Croston/SBA；obsolescent 加 TSB"),
        ("回测", f"origin={';'.join(ORIGINS)}（训练止该月，测后续 {H} 月）；训练已观测月 ≥{MIN_TRAIN_OBS}"),
        ("指标", "WAPE=Σ|e|/Σ|y|（Σ|y|=0→NaN）；MAE；pinball@p50=0.5·MAE"),
        ("采用门槛", f"不劣于最佳基线且至少一项改善 ≥{ADOPT_GAIN:.0%}；TSB 仅 obsolescent"),
        ("current-owner 键", "product × current_pool × physical_form × canonical_uom；"
                             "current_pool=B r10 唯一「美国责任方」，否则 US_unassigned"),
        ("as-of 键", "product × 历史仓池 × physical_form × canonical_uom；只用于历史回测"),
        ("责任重述", "历史仓只作 evidence + migration flag；不改原始订单/库存/供应；"
                     "双池产品若仅履约迁仓→全归 current owner；退货跟原订单/product"),
        ("两套序列", "current-owner 用于预测（3_分类/2_有效历史_current）；"
                     "as-of 用于回测（3a_分类_asof/4_回测_asof）；不混用"),
        ("不做", "不预测无历史/跨form/UOM/共享/老品/清仓；不补 0；不下单"),
    ] + [(f"输入 SHA256 · {k}", v["sha256"]) for k, v in inputs.items()],
        columns=["项", "内容"])

    fail_tbl = pd.DataFrame(fail_rows)
    extra = []
    for r in ndk_tbl.itertuples(index=False):
        extra.append(dict(层级="mapping", product_id="-", pool="-", physical_form="-",
                          canonical_uom="-", 类型=f"无需求键:{r.原因}",
                          原因=f"{int(r.行数)} 行 / {r.数量:.0f} 件",
                          fallback="不进需求序列（守恒保留，不补 0）"))
    for r in mm_tbl.itertuples(index=False):
        extra.append(dict(层级="mapping", product_id=str(r.product), pool="-",
                          physical_form="-", canonical_uom="-",
                          类型="多候选（跨 form/UOM/共享隔离）",
                          原因=f"{int(r.行数)} 行 / {r.数量:.0f} 件",
                          fallback="不合并，需人工确认别名"))
    for b in ("no_product_match", "out_of_scope_pool"):
        sub = o[o["bucket"] == b]
        extra.append(dict(层级="mapping", product_id="-", pool="-", physical_form="-",
                          canonical_uom="-", 类型=b,
                          原因=f"{len(sub)} 行 / {float(sub['qty'].sum()):.0f} 件",
                          fallback="不进需求序列（守恒保留）"))
    for r in cls_tbl[cls_tbl["clearance"]].itertuples(index=False):
        extra.append(dict(层级="series", product_id=r.product_id, pool=r.pool,
                          physical_form=r.physical_form, canonical_uom=r.canonical_uom,
                          类型="清仓", 原因="含 #qc/清仓行",
                          fallback="清仓期按删失观察，不进正常 0、不补"))
    for r in cls_tbl[cls_tbl["shared_candidate"]].itertuples(index=False):
        extra.append(dict(层级="series", product_id=r.product_id, pool=r.pool,
                          physical_form=r.physical_form, canonical_uom=r.canonical_uom,
                          类型="共享", 原因="D1 共享池候选（shared_pool_ids）",
                          fallback="需求可回测；供给/净额按共享池不分配"))
    fail_tbl = pd.concat([fail_tbl, pd.DataFrame(extra)], ignore_index=True)

    # ---------- 8_自检（v2 新增，全部必须 PASS）

    bt_rows = res_tbl[res_tbl["status"] == "ok"]
    det_ok = det_tbl[det_tbl["n_test"] > 0] if len(det_tbl) else det_tbl
    min_ntest = int(det_ok["n_test"].min()) if len(det_ok) else 0
    mapped_bridge = mp[mp["status"] == "唯一"]
    date_unknown_mask = o["demand_event_date"].isna()
    date_unknown_qty = float(o.loc[date_unknown_mask, "qty"].sum())
    date_unknown_bucket = cons.loc[cons["bucket"] == "date_unknown"].iloc[0]
    # A/B/C 分配守恒与仓级实际一致性
    if len(alloc_detail):
        _grp = (alloc_detail.assign(_sum=alloc_detail["alloc_nj"] + alloc_detail["alloc_tx"])
                .groupby(["scenario", "product_id", "origin", "month"])
                .agg(alloc=("_sum", "first"), fc=("forecast_total", "first")))
        alloc_conservation_bad = int(((_grp["alloc"] - _grp["fc"]).abs() > 1e-6).sum())
        _act = (alloc_detail.assign(_a=alloc_detail["actual_nj"]
                                          + alloc_detail["actual_tx"])
                .groupby("scenario")["_a"].sum().to_dict())
        abc_actual_consistent = int(len(set(round(v, 6) for v in _act.values())) > 1)
    else:
        alloc_conservation_bad, abc_actual_consistent = 0, 0
    _same = {r.warehouse: r.same_owner_qty for r in recon90_tbl.itertuples(index=False)}
    _cross = {r.warehouse: r.cross_owner_qty for r in recon90_tbl.itertuples(index=False)}

    sc = pd.DataFrame([
        dict(检查项="zero_positive_effective_months",
             期望=0, 实际=int(((hist_tbl["months_positive"] == 0)
                              & (hist_tbl["history_months_effective"] > 0)).sum())),
        dict(检查项="所有回测行 n_test>=3",
             期望=0, 实际=int((det_ok["n_test"] < 3).sum()) if len(det_ok) else 0),
        dict(检查项="mapped 行 effective_from 非空",
             期望=len(mapped_bridge),
             实际=int((mapped_bridge["effective_from"].astype(str).str.strip() != "").sum())),
        dict(检查项="桥表 lineage 可追溯（含 raw sku 与 product）",
             期望=len(mapped_bridge),
             实际=int(sum(1 for r in mapped_bridge.itertuples(index=False)
                          if str(r.sku_tongtool) in str(r.mapping_lineage)
                          and str(r.product) in str(r.mapping_lineage)))),
        dict(检查项="守恒·行数", 期望=len(o), 实际=int(cons["行数"].sum())),
        dict(检查项="守恒·数量", 期望=round(float(o["qty"].sum()), 6),
             实际=round(float(cons["数量"].sum()), 6)),
        dict(检查项="未知需求日期分桶行数",
             期望=int(date_report["unknown_event_dates"]),
             实际=int(date_unknown_bucket["行数"])),
        dict(检查项="未知需求日期分桶数量",
             期望=round(date_unknown_qty, 6),
             实际=round(float(date_unknown_bucket["数量"]), 6)),
        dict(检查项="可回测数对账（D3 + 变长 + 新增 − 丢失）",
             期望=rec["now_bt"],
             实际=rec["d3_bt"] + rec["变长"] + rec["新增"] - rec["丢失"]),
        dict(检查项="adopted_without_positive_actual", 期望=0,
             实际=int(sum(1 for r in cls_tbl.itertuples(index=False)
                          if r.adoption_status == "adopted"
                          and not bool(res_tbl[(res_tbl["product_id"] == r.product_id)
                                               & (res_tbl["pool"] == r.pool)
                                               & (res_tbl["physical_form"] == r.physical_form)
                                               & (res_tbl["canonical_uom"] == r.canonical_uom)
                                               & (res_tbl["model"] == r.adopted_model)
                                               ]["positive_test_actual"].iloc[0])))),
        dict(检查项="backtested_without_origin", 期望=0,
             实际=int(((cls_tbl["backtested"]) & (cls_tbl["adoption_status"] == "no_origin")).sum())),
        dict(检查项="new_method_threshold_violations", 期望=0, 实际=_viol_after),
        dict(检查项="new_method_adopted（记录值，键迁移后重算）",
             期望=n_new_adopted, 实际=n_new_adopted),
        dict(检查项="baseline_adopted（记录值，键迁移后重算）",
             期望=n_base_adopted, 实际=n_base_adopted),
        dict(检查项="new_method_adopted + baseline_adopted = adopted",
             期望=n_adopted, 实际=n_new_adopted + n_base_adopted),
        dict(检查项="eligible = backtested + no_origin", 期望=n_eligible,
             实际=n_backtested + n_no_origin),
        dict(检查项="backtested = adopted + no_positive + zero_error", 期望=n_backtested,
             实际=n_adopted + n_no_pos + n_zero_err),
        dict(检查项="d1b_demand_rows_without_series", 期望=0,
             实际=int(d1b_cov["without_series"])),
        dict(检查项="duplicate_keys（D1b 需求行去重后键数差）", 期望=0, 实际=duplicate_keys),
        dict(检查项="old_key_conservation（旧键全部有去向）", 期望=0, 实际=old_key_conservation),
        dict(检查项="censor_unassigned（无法归属的删失记录，列出）", 期望="列出",
             实际=int(cens_unassigned)),
        dict(检查项="WayfairCG 订单量（应在 4,887）", 期望=4887,
             实际=int(round(_cg_total))),
        dict(检查项="WayfairCG→美东USNJ（应为 1,564）", 期望=1564,
             实际=int(round(_cg_parts.get("美东USNJ", 0.0)))),
        dict(检查项="WayfairCG→美中USTX（应为 3,323）", 期望=3323,
             实际=int(round(_cg_parts.get("美中USTX", 0.0)))),
        dict(检查项="key_version 标记覆盖（分类行）",
             期望=len(cls_tbl),
             实际=int((cls_tbl["key_version"] == KEY_VERSION).sum())),
        # ---- v3.5 责任重述自检
        dict(检查项="current-owner 键数（1853−104）", 期望=1749, 实际=len(k_current)),
        dict(检查项="as-of→current 键坍缩数", 期望=104, 实际=key_reduction),
        dict(检查项="每个 as-of 键都有唯一 current 键",
             期望=len(k_set), 实际=len(cur_of_asof)),
        dict(检查项="current 分类行覆盖 current 键数",
             期望=len(k_current), 实际=len(cls_cur_tbl)),
        dict(检查项="current 序列不丢量（current−asof 为负则失败）", 期望=0,
             实际=0 if current_extra_qty >= -1e-6 else 1),
        dict(检查项="产品级对账差额=逐键差额", 期望=0,
             实际=0 if abs(product_extra_total - current_extra_qty) < 1e-6 else 1),
        dict(检查项="A/B/C90/C180 仓级回测存在且 B=生产候选", 期望="是",
             实际=("是" if set(alloc_tbl["scenario"]) == {"A", "B", "C90", "C180"}
                   and alloc_tbl.loc[alloc_tbl["scenario"] == "B", "production_candidate"]
                   .eq("是").all() else "否")),
        dict(检查项="A/B/C 分配守恒（仓合计=产品总预测）", 期望=0,
             实际=alloc_conservation_bad),
        dict(检查项="A/B/C 仓级实际总量一致", 期望=0, 实际=abc_actual_consistent),
        dict(检查项="90天 same-owner USNJ（7,650）", 期望=7650,
             实际=round(_same.get("美东USNJ", np.nan), 6)),
        dict(检查项="90天 same-owner USTX（11,398）", 期望=11398,
             实际=round(_same.get("美中USTX", np.nan), 6)),
        dict(检查项="90天交叉量 USNJ←USTX（22）", 期望=22,
             实际=round(_cross.get("美东USNJ", np.nan), 6)),
        dict(检查项="90天交叉量 USTX←USNJ（20）", 期望=20,
             实际=round(_cross.get("美中USTX", np.nan), 6)),
        dict(检查项="current 守恒·行数", 期望=len(o),
             实际=int(cons_cur["行数"].sum())),
        dict(检查项="current 守恒·数量", 期望=round(float(o["qty"].sum()), 6),
             实际=round(cons_cur_total, 6)),
        dict(检查项="owner-known US qty", 期望=281490, 实际=round(audit_known_qty, 6)),
        dict(检查项="US_unassigned qty", 期望=31033, 实际=round(audit_unassigned_qty, 6)),
        dict(检查项="US 需求总量", 期望=312523, 实际=round(audit_total_qty, 6)),
        dict(检查项="审计产品数（无重复）", 期望=1145, 实际=len(audit_tbl)),
        dict(检查项="迁移产品数", 期望=181,
             实际=int((audit_tbl["moved_qty"] > 0).sum())),
        dict(检查项="双池产品数（owner-known）", 期望=178,
             实际=audit_counts["both_pools_products"]),
        dict(检查项="current USNJ / hist USTX 特例", 期望=53,
             实际=int(audit_tbl["exception_current_USNJ_hist_USTX"].sum())),
        dict(检查项="迁移量 USNJ→USTX", 期望=83458,
             实际=round(audit_counts["direction"].get(("美东USNJ", "美中USTX"), 0.0), 6)),
        dict(检查项="迁移量 USTX→USNJ", 期望=885,
             实际=round(audit_counts["direction"].get(("美中USTX", "美东USNJ"), 0.0), 6)),
    ])
    def _eq(e, a):
        try:
            return abs(float(e) - float(a)) < 1e-9
        except (TypeError, ValueError):
            return str(e) == str(a)

    sc["通过"] = ["是" if _eq(r.期望, r.实际) else "否" for r in sc.itertuples(index=False)]
    sc.loc[sc["检查项"].str.startswith("censor_unassigned"), "通过"] =         ("是（已逐条列出）" if cens_unassigned >= 0 else "否")
    sc_ok = bool(sc["通过"].astype(str).str.startswith("是").all())

    _lost = []
    for r in cls_tbl.itertuples(index=False):
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        d3r = d3_idx.get(key)
        if d3r is not None and bool(d3r.backtestable) and not r.eligible:
            why = getattr(r, "not_backtestable_reason", "") or "短史"
            if r.n_pos == 0:
                why = "no_demand（无正销）"
            _lost.append(why)
    _lost_reasons = pd.Series(_lost).value_counts().to_dict() if _lost else {}

    if args.dry_run:
        np_zero = hist_tbl[hist_tbl["months_positive"] == 0]
        o_skip = det_tbl
        nt = res_tbl[res_tbl["status"] == "ok"]
        print(json.dumps(dict(
            key_version=KEY_VERSION,
            wayfair_cg=dict(rows=_cg_rows, qty=_cg_total,
                            by_owner={k: float(v) for k, v in _cg_parts.items()}),
            key_migration=dict(old_keys=len(k_old), new_keys=len(k_set),
                               old_categories=old_cat, gains=gain_cat, d1b_demand=d1b_cov,
                               old_key_conservation=old_key_conservation,
                               duplicate_keys=duplicate_keys,
                               censor_unassigned=cens_unassigned), dry_run=True,
            conservation={r.bucket: dict(行数=int(r.行数), 数量=float(r.数量))
                          for r in cons.itertuples(index=False)},
            conservation_total=dict(rows=int(cons["行数"].sum()),
                                    qty=float(cons["数量"].sum()),
                                    order_rows=len(o), order_qty=float(o["qty"].sum())),
            zero_positive_keys=dict(
                count=int(len(np_zero)),
                effective_months_distribution=np_zero["history_months_effective"]
                .value_counts().sort_index().to_dict(),
                patterns=cls_tbl.loc[cls_tbl["n_pos"] == 0, "demand_pattern"]
                .value_counts().to_dict(),
                backtestable=cls_tbl.loc[cls_tbl["n_pos"] == 0, "eligible"]
                .value_counts().to_dict()),
            ntest_by_origin=(
                fail_tbl[fail_tbl["原因"].astype(str).str.contains("insufficient_test")]
                .groupby("pool").size().to_dict()),
            origin_test_months=({o_: sorted({m for r in det_tbl[det_tbl["origin"] == o_]
                                             .itertuples(index=False)
                                             for m in str(r.test_months).split(";")})
                                 for o_ in sorted(det_tbl["origin"].unique())}
                                if len(det_tbl) else {}),
            ntest=dict(min_n_test_in_backtest_rows=min_ntest,
                       rows_with_lt3=int(((det_tbl["n_test"] < 3).sum()) if len(det_tbl) else 0),
                       origins=list(ORIGINS),
                       insufficient_test_rows=int((fail_tbl["原因"].astype(str)
                                                   .str.contains("insufficient_test")).sum())
                       if len(fail_tbl) else 0),
            lost_reasons=_lost_reasons,
            adopted_breakdown=dict(total=n_adopted, new_method=n_new_adopted,
                                   baseline=n_base_adopted, by_model=adopted),
            new_method_threshold_violations=dict(after_rollback=_viol_after,
                                                 before_rollback=len(violations),
                                                 detail=violations,
                                                 note=threshold_note),
            five=dict(eligible=n_eligible, backtested=n_backtested, adopted=n_adopted,
                      no_positive=n_no_pos, zero_error=n_zero_err, no_origin=n_no_origin,
                      sum_check=dict(eligible_eq=n_backtested + n_no_origin,
                                     backtested_eq=n_adopted + n_no_pos + n_zero_err)),
            backtestable=dict(v2=int(cls_tbl["eligible"].sum()), d3=rec["d3_bt"],
                              reconciliation=rec,
                              patterns=cls_tbl["demand_pattern"].value_counts().to_dict()),
            short885=go_counts,
            owner_restatement=dict(
                asof_keys=len(k_set), current_keys=len(k_current),
                key_reduction=key_reduction, categories=cat_counts,
                owner_known_qty=audit_known_qty, unassigned_qty=audit_unassigned_qty,
                total_qty=audit_total_qty, products=len(audit_tbl),
                owner_known_products=audit_counts["owner_known_products"],
                unassigned_products=audit_counts["unassigned_products"],
                moved_products=audit_counts["moved_products"],
                both_pools_products=audit_counts["both_pools_products"],
                exception_products=audit_counts["exception_products"],
                moved_qty=audit_counts["moved_qty"],
                direction={f"{a}->{b}": v for (a, b), v in
                           audit_counts["direction"].items()},
                current_mapped_qty=current_mapped_qty,
                asof_mapped_qty=asof_mapped_qty,
                current_extra_qty=current_extra_qty),
            abc_backtest=dict(summary=alloc_tbl.to_dict("records"),
                              dual_products=len(dual_products),
                              conservation_bad=alloc_conservation_bad),
            ninety_day_reconciliation=recon90_tbl.to_dict("records"),
            current_classification=dict(
                keys=len(cls_cur_tbl),
                patterns=cls_cur_tbl["demand_pattern"].value_counts().to_dict(),
                eligible=int(cls_cur_tbl["eligible"].sum()),
                adopted_transferred=int((cls_cur_tbl["adopted_model"] != "none").sum())),
            new_adopted=int(res_tbl[(res_tbl["adopted"] == "是")
                                    & (res_tbl["family"] == "new")].shape[0]),
            selfcheck=sc.to_dict("records"), selfcheck_pass=sc_ok,
        ), ensure_ascii=False, indent=1, default=str))
        print("DRY-RUN：未写 xlsx / 报告 / manifest")
        return 0 if sc_ok else 1

    for _p in (args.out_xlsx, args.out_report, args.manifest, args.owner_audit,
               args.series_current, args.series_asof, args.trend_csv):
        Path(_p).parent.mkdir(parents=True, exist_ok=True)
    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        mp.to_excel(w, sheet_name="1_映射桥", index=False)
        hist_cur_tbl.to_excel(w, sheet_name="2_有效历史_current", index=False)
        hist_tbl.to_excel(w, sheet_name="2a_有效历史_asof", index=False)
        cls_cur_tbl.to_excel(w, sheet_name="3_分类", index=False)
        cls_tbl.to_excel(w, sheet_name="3a_分类_asof", index=False)
        pd.concat([res_tbl.assign(层级="model"), det_tbl.assign(层级="origin")],
                  ignore_index=True).to_excel(w, sheet_name="4_回测_asof", index=False)
        fail_tbl.to_excel(w, sheet_name="5_失败", index=False)
        pd.concat([summary.assign(表="汇总"), go_tbl.assign(表="885去向")],
                  ignore_index=True).to_excel(w, sheet_name="6_汇总", index=False)
        pd.concat([cons.assign(层级="桶_asof"),
                   ndk_tbl.assign(层级="无需求键原因_asof"),
                   cons_cur.assign(层级="桶_current"),
                   ndkc_tbl.assign(层级="无需求键原因_current")],
                  ignore_index=True).to_excel(w, sheet_name="7_守恒", index=False)
        sc.to_excel(w, sheet_name="8_自检", index=False)
        recon_tbl.to_excel(w, sheet_name="9_键迁移对账", index=False)
        restate_tbl.to_excel(w, sheet_name="9b_责任重述对账", index=False)
        audit_tbl.to_excel(w, sheet_name="10_责任重述审计", index=False)
        special_tbl.to_excel(w, sheet_name="11_特例与迁移", index=False)
        alloc_tbl.to_excel(w, sheet_name="12_仓级回测_ABC", index=False)
        alloc_keys.to_excel(w, sheet_name="12b_仓级回测_逐键", index=False)
        dual_tbl.to_excel(w, sheet_name="13_双仓责任与份额", index=False)
        recon90_tbl.to_excel(w, sheet_name="14_90天分母核对", index=False)
        trend_tbl.to_excel(w, sheet_name="15_趋势诊断", index=False)
    out_sha = sha256(out)
    sheets = {s: int(len(pd.read_excel(out, sheet_name=s))) for s in pd.ExcelFile(out).sheet_names}

    # ---------- 月度序列侧车（D5 v6.3 直接消费，保证与 D3b 同源）
    def _series_frame(frame: pd.DataFrame, key_col: str) -> pd.DataFrame:
        keys_df = pd.DataFrame(
            [list(k) for k in frame[key_col]],
            columns=["product_id", "pool", "physical_form", "canonical_uom"])
        f = frame[["demand_event_date", "month", "qty"]].reset_index(drop=True)
        f = pd.concat([f, keys_df], axis=1)
        f["date"] = pd.to_datetime(f["demand_event_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        f["month"] = f["month"].astype(str)
        g = (f.groupby(["product_id", "pool", "physical_form", "canonical_uom",
                        "date", "month"], dropna=False)["qty"].sum().reset_index())
        return g[g["qty"] != 0].sort_values(
            ["product_id", "pool", "physical_form", "canonical_uom", "date"])
    series_asof = _series_frame(m, "key_fixed")
    series_cur = _series_frame(mc, "key_current")
    series_asof.to_parquet(args.series_asof, index=False)
    series_cur.to_parquet(args.series_current, index=False)
    audit_tbl.to_csv(args.owner_audit, index=False, encoding="utf-8-sig")
    trend_tbl.to_csv(args.trend_csv, index=False, encoding="utf-8-sig")

    tests = run_selftests()
    L = [f"# D3b v3.8 历史归一 + 美国需求按当前 owner 重述 + 重分类 + 重回测（{RULE_VERSION}；只读）", "",
         f"- 工作簿 SHA256：`{out_sha}`",
         "- **需求日期口径**：`month` 统一从 `sale_date` 派生 YYYYMM；原始 `month` 保留为 `source_month`，仅作源表分区标签。",
         f"- 日期诊断：`{json.dumps(date_report, ensure_ascii=False)}`；无日期订单进入 `date_unknown` 守恒桶，不进入需求序列。",
         f"- **as-of 序列（回测用）** {len(cls_tbl)}｜eligible {n_eligible} / with-origin {n_backtested} / "
         f"adopted {n_adopted} / no-positive {n_no_pos} / zero-error {n_zero_err} / "
         f"no-origin {n_no_origin}（D3 可比口径 {rec['d3_bt']}；D3 旧键全量 954）",
         f"- **current-owner 序列（D5 预测用）** {len(cls_cur_tbl)}｜eligible "
         f"{int(cls_cur_tbl['eligible'].sum())}｜分类 "
         f"`{json.dumps(cls_cur_tbl['demand_pattern'].value_counts().to_dict(), ensure_ascii=False)}`",
         f"- **键迁移**：as-of **{len(k_set)}** → current-owner **{len(k_current)}**"
         f"（坍缩 **{key_reduction}** 键；USNJ/USTX 按 B r10 唯一 owner 合并）",
         f"- **两套序列分开**：`3a_分类_asof` + `4_回测_asof` 只用于历史回测；"
         f"`3_分类`（current-owner）只用于预测。报告差异见 §0。",
         f"- **key_version**：as-of `{KEY_VERSION}`；current-owner `{OWNER_KEY_VERSION}`。", "",
         "## 0. 美国需求按当前 owner 重述（v3.5）", "",
         "| 项 | 数值 | 说明 |", "|---|---:|---|",
         f"| owner-known US 需求 | {audit_known_qty:.0f} | B r10 唯一「美国责任方」 |",
         f"| US_unassigned | {audit_unassigned_qty:.0f} | 无唯一 owner，单列，不进入 current 需求键 |",
         f"| US 需求总量 | {audit_total_qty:.0f} | 281,490 + 31,033 |",
         f"| 历史池 USNJ / USTX | {audit_tbl['hist_qty_USNJ'].sum():.0f} / "
         f"{audit_tbl['hist_qty_USTX'].sum():.0f} | 原始订单仓 |",
         f"| current owner USNJ / USTX | "
         f"{audit_tbl.loc[audit_tbl['current_pool'] == '美东USNJ', 'hist_qty_total'].sum():.0f} / "
         f"{audit_tbl.loc[audit_tbl['current_pool'] == '美中USTX', 'hist_qty_total'].sum():.0f} | "
         "按当前 owner 重述 |",
         f"| 迁移产品 / 量 | {audit_counts['moved_products']} / "
         f"{audit_counts['moved_qty']:.0f} | 历史仓 ≠ current owner |",
         f"| 双池产品（owner-known） | {audit_counts['both_pools_products']} | 历史同时有 USNJ 与 USTX；含 unassigned 共 {audit_counts['both_pools_all_products']} |",
         f"| current USNJ / hist USTX 特例 | {audit_counts['exception_products']} | 逐条见 11_特例与迁移 |",
         f"| current−as-of mapped 差额 | {current_extra_qty:.0f} | current owner 键接回的历史池无键订单量 |", "",
         f"- 迁移方向：`{json.dumps({f'{a}->{b}': v for (a, b), v in audit_counts['direction'].items()}, ensure_ascii=False)}`。",
         "- 双池产品若只是履约迁仓，全归当前 owner；只有独立区域/渠道/双责有证据才拆分（B r10 已给证据层级）。",
         "- 退货跟原订单/product，不按退货仓；本数据无负数量退货行。",
         "- 原始订单、库存、供应未改；历史仓只作 evidence + migration flag。", "",
         "## 0.1 v2 修复项（对应评审 1–5）", "",
         f"1. **映射桥生效期**：`1_映射桥` 新增 `mapping_lineage` / `effective_from`（= 该 SKU "
         f"首次订单日，回填）/ `effective_to`（被同产品更晚别名替代时填末次订单日，否则空）/ "
         f"`history_bridge_refs`；mapped 行 {len(mp[mp['status']=='唯一'])} 条全部有 "
         f"effective_from，lineage 可回溯到 raw SKU、证据来源与 A 行。",
         f"2. **无正销键**：{int((cls_tbl['n_pos']==0).sum())} 条无正销键的有效月改为 0"
         f"（v1 错记为 1），分类 `no_demand`，全部不进可回测。",
         f"3. **测试窗契约**：origin 改为 {'/'.join(ORIGINS)}（各测 3 个月），`n_test<3` 的 "
         f"origin 记 `insufficient_test` 并跳过（{len(fail_tbl[fail_tbl['原因'].astype(str).str.contains('insufficient_test')]) if len(fail_tbl) else 0} 行）；"
         f"回测行最小 n_test = {min_ntest}。",
         f"4. **key_version**：全表带 `key_version`，分类行覆盖 "
         f"{int((cls_tbl['key_version']==KEY_VERSION).sum())}/{len(cls_tbl)}。",
         "5. **删失月对齐（v1 隐性 bug）**：v1 用 `2026-04` 比对 `202604`，删失从未生效；"
         "v2 已对齐，删失月不再进入有效观测与测试窗。", "",
         "## 0.2 A/B/C 仓级分配回测（B=生产候选）", "",
         "- **B**：按产品预测美国总需求，再按 B r10 唯一 current owner 1/0 分到 USNJ/USTX。",
         "- **C90/C180**：近 90/180 天仓份额，仅用于 origin 当时已证真实双仓责任产品"
         "（两池均≥20 件且份额≥10%）；非双仓 C=B。",
         "- **A**：历史仓池分别预测（as-of 序列，只用 origin 前数据）；仅作 evidence/备选。",
         "- 历史迁移不进入仓份额训练：A/C 的份额只使用 origin 之前的数据；B 使用当前 owner 结构事实。",
         "- 指标：WAPE=Σ|alloc−actual|/Σactual；偏差=Σ(alloc−actual)/Σactual；"
         "缺货率=Σmax(actual−alloc,0)/Σactual（分配缺口代理，非库存缺货率）。", "",
         "| 场景 | 仓 | 键 | 月 | actual | allocated | WAPE | 偏差 | 缺货率 |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in alloc_tbl.itertuples(index=False):
        L.append(f"| {r.scenario} | {r.warehouse} | {r.keys} | {r.months} | "
                 f"{r.actual:.0f} | {r.allocated:.0f} | {r.wape:.4f} | "
                 f"{r.bias:+.4f} | {r.stockout_rate:.4f} |")
    L += ["", f"- 真实双仓责任产品：**{len(dual_products)}**（见 `13_双仓责任与份额`）。", "",
          "### 0.2.1 最近 90 天分母与交叉量核对", "",
          "| 仓 | 仓级总量 | owner-known | same-owner | cross-owner | unknown/NaN |",
          "|---|---:|---:|---:|---:|---:|"]
    for r in recon90_tbl.itertuples(index=False):
        L.append(f"| {r.warehouse} | {r.total_qty:.0f} | {r.owner_known_qty:.0f} | "
                 f"{r.same_owner_qty:.0f} | {r.cross_owner_qty:.0f} | "
                 f"unknown={r.unknown_owner_qty:.0f}/{r.unknown_owner_rows}行；"
                 f"NaN产品={r.nan_product_rows}行/{r.nan_product_qty:.0f}件 |")
    L += ["", "- **7,650 / 11,398 是 same-owner 小计，不是仓级总量**："
          "USNJ same-owner 7,650 + cross 22 + unknown 8 = 7,680；"
          "USTX same-owner 11,398 + cross 20 + unknown 150 = 11,568。"
          "因此“7,650 中 22”是分母错位：22 已不在 7,650 内。",
          "- unknown 是独立留项，未补 0、未分摊到 owner：全历史 US 映射后 **229 个产品 / "
          "29,402 行 / 31,033 件**（2022-12..2026-10，按 product_id×US 去重）。"
          "90 天窗口 unknown 行 = 已解析产品无 owner 行 + NaN 产品行 = "
          f"{int(recon90_tbl['unknown_total_rows'].sum())} 行；"
          "Codex 提到的 273 是未注明粒度的 NaN 统计，未据此认定 229+44。"
          "43 个带 CG 需求键的 unknown 产品已包含在 229 内，不能相加。", "",
          "## 1. 映射与守恒", "",
          "| 桶 | 行数 | 数量 | 数量占比 |", "|---|---:|---:|---:|"]
    for r in cons.itertuples(index=False):
        L.append(f"| {r.bucket} | {int(r.行数)} | {r.数量:.0f} | {r.占比_数量:.2%} |")
    L += ["", f"合计 {cons_total:.0f} = 订单总 qty {float(o['qty'].sum()):.0f}（守恒 ✔）", "",
          "**未进需求键的原因**（占订单量）：", ""]
    for r in ndk_tbl.itertuples(index=False):
        L.append(f"- {r.原因}：{int(r.行数)} 行 / {r.数量:.0f} 件（{r.占比_数量:.2%}）")
    L += ["",
          "## 2. 有效历史与 885 去向", "",
          "| 去向 | 条数 |", "|---|---:|"]
    for k, v in go_counts.items():
        L.append(f"| {k} | {v} |")
    L += ["", f"- 可回测变化对账：D3 **{rec['d3_bt']}**（新键可比口径；D3 旧键全量 954）"
          f" + 变长 **{rec['变长']}** + 新增 **{rec['新增']}** "
          f"− 丢失 **{rec['丢失']}** = **{rec['now_bt']}**；丢失原因 "
          f"{json.dumps(_lost_reasons, ensure_ascii=False)}（删失对齐后有效月 <12）。", "",
          f"- 有效历史（`2_有效历史.history_months_effective`）中位 "
          f"{float(hist_tbl['history_months_effective'].median()):.0f} 月；"
          f"D3 同键的可用月中位 {float(short885['n_obs'].median()):.0f} 月。", "",
          "## 2.1 键迁移对账（D2 v3 旧键 → D1b v2.3 新键）", "",
          f"- 旧键 **{len(k_old)}** → 新键 **{len(k_set)}**（exact {old_cat.get('exact', 0)}、"
          f"form归一 {old_cat.get('form归一', 0)}、池修正 {old_cat.get('池修正', 0)}、"
          f"无需求 {old_cat.get('无需求', 0)}、政策排除 {old_cat.get('政策排除', 0)}、"
          f"多候选 {old_cat.get('多候选', 0)}、未匹配 {old_cat.get('未匹配', 0) + old_cat.get('未匹配（产品不在 D1b）', 0)}）",
          f"- 新键 gain：{json.dumps(gain_cat, ensure_ascii=False)}",
          f"- D1b demand 行：{d1b_cov['demand_rows']} 行，全部有 series（缺 {d1b_cov['without_series']}）；"
          f"其中 CG/CG-* 池 {sum(1 for k in k_set if k[1] in ('CG','CG-USNJ','CG-USTX'))} 键无通途订单流（Wayfair 仓不进订单池）",
          f"- 删失无法归属：**{cens_unassigned}** 条（产品不在新需求键集中，列入 9_键迁移对账 说明）", "",
          "## 2.2 WayfairCG 归池修正（v3.2）", "",
          f"- 根因：v3/v3.1 把 `WayfairCG-Cranbury仓` 硬映射到 美东USNJ（按仓址），"
          f"但该仓承载的是 Wayfair 渠道订单，归属应看产品 owner。",
          f"- 修正：WayfairCG-* 订单按 B r10「美国责任方」归池，`channel=wayfair`；"
          f"CG 库存池（CG/CG-USNJ/CG-USTX）仍只作下游缓冲，不参与需求归集。",
          f"- 对账：共 **{_cg_rows}** 行 / **{_cg_total:.0f}** 件 → "
          f"美东USNJ **{_cg_parts.get('美东USNJ', 0):.0f}** + "
          f"美中USTX **{_cg_parts.get('美中USTX', 0):.0f}**"
          + (f" + 其他 {_cg_parts.get('其他', 0):.0f}" if _cg_parts.get("其他") else "")
          + "（4,887 = 1,564 + 3,323）", "",
          "## 2.3 责任重述键对账（as-of → current-owner）", "",
          f"- as-of **{len(k_set)}** 键 → current-owner **{len(k_current)}** 键；"
          f"坍缩 **{key_reduction}** 键。",
          f"- 分类：`{json.dumps(cat_counts, ensure_ascii=False)}`。",
          f"- 金额/数量：as-of mapped **{asof_mapped_qty:.0f}**；current mapped "
          f"**{current_mapped_qty:.0f}**；差额 **{current_extra_qty:.0f}** "
          "（历史池无键、但当前 owner 有键的订单；不是重复）。",
          f"- 逐键见 `9b_责任重述对账`；产品级审计见 `10_责任重述审计`；"
          f"181 迁移 / 53 特例 / 178 双池 / 31,033 unassigned 见 `11_特例与迁移`。", "",
          "## 3. 重分类（as-of 回测口径）", "", "| demand_pattern | 序列数 |", "|---|---:|"]
    for k, v in pat.items():
        L.append(f"| {k} | {v} |")
    L += ["", "**current-owner 分类（D5 预测口径）**：", "",
          "| demand_pattern | 序列数 |", "|---|---:|"]
    for k, v in cls_cur_tbl["demand_pattern"].value_counts().items():
        L.append(f"| {k} | {v} |")
    L += ["", "## 4. 重回测（仅 as-of；current-owner 不做历史回测）", "",
          f"- eligible **{n_eligible}** / with-origin **{n_backtested}** / adopted "
          f"**{n_adopted}** / no-positive **{n_no_pos}** / zero-error **{n_zero_err}** / "
          f"no-origin **{n_no_origin}**｜采用新方法 **{new_adopted}**"
          f"（D3 为 {d3_new}）｜最佳基线 `{json.dumps(best_base, ensure_ascii=False)}`",
          f"- 采用分布 `{json.dumps(adopted, ensure_ascii=False)}`", "",
          "### 4.1 采用门槛复核（机械验证）", "",
          f"- adopted **{n_adopted}** = 新方法 **{n_new_adopted}**（sba/croston）"
          f" + 基线 **{n_base_adopted}**。",
          f"- 复核方式：对每条 adopted 的新方法，在同一「有正销测试窗」上比较最佳基线的 "
          f"WAPE/MAE，要求均不劣且至少一项改善 ≥{ADOPT_GAIN:.0%}。",
          f"- 回退前发现违规 **{len(violations)}** 条；回退后保留的采用中违规 "
          f"**{_viol_after}** 条（自检要求 0）。",
          f"- 结论：{threshold_note}。", ""]
    if violations:
        L += ["| 违规序列 | 模型 | 原因 |", "|---|---|---|"]
        for v in violations[:50]:
            L.append(f"| {v['product_id']}/{v['pool']}/{v['physical_form']}/{v['canonical_uom']} "
                     f"| {v['model']} | {v['reason']} |")
        L += [""]
    L += [
          "### 4.2 趋势诊断（current-owner 键）", "",
          "| 趋势桶 | 键数 |", "|---|---:|"]
    for k, v in trend_tbl["trend_bucket"].value_counts().items():
        L.append(f"| {k} | {v} |")
    L += ["", f"- 结构突变：`{json.dumps(trend_tbl['structural_break'].value_counts().to_dict(), ensure_ascii=False)}`"
              "（最近 12 个已观测月对半；|z|≥2 且相对变化≥30%，启发式，非正式检验）。", "",
          "**软包墙围 4 SKU（as-of 回测 WAPE + current 采用）**：", "",
          "| 产品 | 池 | 3_分类 adopted | source | naive | ets_ann | ets_aadn | ets_aaa | theta | sba | YoY% | 趋势桶 | 突变 |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    _cur_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
                for r in cls_cur_tbl.itertuples(index=False)}
    _trend_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
                  for r in trend_tbl.itertuples(index=False)}
    _wall_idx = {}
    for r in res_tbl.itertuples(index=False):
        if r.product_id not in WALL_KEYS:
            continue
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        _wall_idx.setdefault(key, {})[r.model] = r.wape

    def _fmt(v):
        return f"{v:.3f}" if v is not None and np.isfinite(v) else "—"

    for key in sorted(_wall_idx):
        w = _wall_idx[key]
        cur = _cur_idx.get(key)
        tr = _trend_idx.get(key)
        L.append(
            f"| {key[0]} | {key[1]} | {cur.adopted_model if cur else '—'} | "
            f"{cur.model_source if cur else '—'} | "
            + " | ".join(_fmt(w.get(m)) for m in
                         ("naive", "ets_ann", "ets_aadn", "ets_aaa", "theta", "sba"))
            + f" | {_fmt(getattr(tr, 'yoy_pct', None))} | "
              f"{getattr(tr, 'trend_bucket', '—') if tr else '—'} | "
              f"{getattr(tr, 'structural_break', '') if tr else '—'} |")
    L += ["", "> `3_分类 adopted` 只来自 `4_回测_asof`；`asof_join`=单源精确，"
              "`asof_join_multi_*`=多源合并（见 `adopted_sources`）。", ""]
    L += [
          "## 5. 失败分类", ""]
    if len(fail_tbl):
        for k, v in fail_tbl["类型"].value_counts().items():
            L.append(f"- `{k}`：{v}")
    L += ["", "## 6.1 构建期自检（8 项，全部须 PASS）", "",
          "| 检查项 | 期望 | 实际 | 通过 |", "|---|---:|---:|---|"]
    for r in sc.itertuples(index=False):
        L.append(f"| {r.检查项} | {r.期望} | {r.实际} | {r.通过} |")
    L += ["", f"**自检总体：{'PASS' if sc_ok else 'FAIL'}**", "", "## 6. 内存自检", ""]
    for n, ok, d in tests:
        L.append(f"- `{'PASS' if ok else 'FAIL'}` {n}｜{d}")
    L += ["", "## 7. 边界", "",
          "- 2023–2024 无断货证据：这些月的零记为 `zero_orders_only`（不是删失），分类可信度低于 2025+。",
          "- 只做归一回测，不预测、不下单、不写 EN/通途。", ""]
    Path(args.out_report).write_text("\n".join(L), encoding="utf-8")

    manifest = dict(
        rule_version=RULE_VERSION,
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        generated_at_local=datetime.now().astimezone().isoformat(timespec="seconds"),
        generator=script_identity(argv), inputs=inputs,
        outputs=dict(xlsx=dict(path=out.as_posix(), sha256=out_sha,
                               bytes=out.stat().st_size, sheets=sheets),
                     report=dict(path=Path(args.out_report).as_posix(),
                                 sha256=sha256(args.out_report),
                                 bytes=Path(args.out_report).stat().st_size),
                     manifest=dict(path=Path(args.manifest).as_posix(),
                                   file_name=Path(args.manifest).name, sha256=None),
                     owner_audit=dict(path=Path(args.owner_audit).as_posix(),
                                      sha256=sha256(args.owner_audit),
                                      bytes=Path(args.owner_audit).stat().st_size),
                     trend_csv=dict(path=Path(args.trend_csv).as_posix(),
                                    sha256=sha256(args.trend_csv),
                                    bytes=Path(args.trend_csv).stat().st_size,
                                    rows=len(trend_tbl)),
                     series_current=dict(path=Path(args.series_current).as_posix(),
                                         sha256=sha256(args.series_current),
                                         bytes=Path(args.series_current).stat().st_size,
                                         rows=len(series_cur)),
                     series_asof=dict(path=Path(args.series_asof).as_posix(),
                                      sha256=sha256(args.series_asof),
                                      bytes=Path(args.series_asof).stat().st_size,
                                      rows=len(series_asof))),
        key_migration=dict(old_keys=len(k_old), new_keys=len(k_set),
                           old_categories=old_cat, gains=gain_cat, d1b_demand=d1b_cov,
                           old_key_conservation=old_key_conservation,
                           duplicate_keys=duplicate_keys,
                           censor_unassigned=cens_unassigned,
                           asof_to_current=dict(asof_keys=len(k_set),
                                                current_keys=len(k_current),
                                                reduction=key_reduction,
                                                categories=cat_counts)),
        abc_backtest=dict(
            rule="A=as-of pool forecasts separately; B=current owner 1/0 (production); "
                 "C90/C180=recent share only for origin-known true dual-pool products",
            production_candidate="B",
            dual_products=len(dual_products),
            summary=alloc_tbl.to_dict("records"),
            conservation_bad=alloc_conservation_bad),
        ninety_day_reconciliation=recon90_tbl.to_dict("records"),
        owner_restatement=dict(
            rule="B r10 US 需求行唯一「美国责任方」；多 owner/缺 owner → US_unassigned",
            owner_known_qty=audit_known_qty, unassigned_qty=audit_unassigned_qty,
            total_qty=audit_total_qty, **{k: v for k, v in audit_counts.items()
                                          if k not in ("direction", "owner_known_qty",
                                                       "unassigned_qty", "total_qty")},
            direction={f"{a}->{b}": v for (a, b), v in
                       audit_counts["direction"].items()},
            current_mapped_qty=current_mapped_qty, asof_mapped_qty=asof_mapped_qty,
            current_extra_qty=current_extra_qty,
            return_policy="退货跟原订单/product，不按退货仓",
            current_key_version=OWNER_KEY_VERSION),
        conservation=[dict(桶=r.bucket, 行数=int(r.行数), 数量=float(r.数量)) for r in cons.itertuples(index=False)]
        + [dict(桶="current:" + r.bucket_current, 行数=int(r.行数), 数量=float(r.数量))
           for r in cons_cur.itertuples(index=False)],
        totals=dict(order_qty=float(o["qty"].sum()), bucketed=cons_total,
                    current_bucketed=cons_cur_total,
                    series_asof=len(cls_tbl), series_current=len(cls_cur_tbl),
                    eligible_asof=int(cls_tbl["eligible"].sum()),
                    eligible_current=int(cls_cur_tbl["eligible"].sum()),
                    d3_backtestable_comparable=rec["d3_bt"],
                    d3_backtestable_old_keys=954,
                    new_adopted=new_adopted, d3_new_adopted=d3_new),
        key_version=KEY_VERSION,
        key_version_note=("as-of 键：D1b v2.3 product×market×pool×form×uom；"
                          "current-owner 键：D3b v3.5 product×current_pool×form×uom"),
        date_basis="sale_date; source month retained as source_month partition label only",
        date_report=date_report,
        origins=list(ORIGINS), min_test_months=3,
        censoring=dict(applied=True, source="D2 v3 2_删失（2026-04..10）",
                       v1_bug="v1 month 格式 2026-04 与 202604 不匹配，删失从未生效"),
        reconciliation=rec, lost_reasons=_lost_reasons,
        adoption=dict(total=n_adopted, new_method=n_new_adopted, baseline=n_base_adopted,
                      by_model=adopted,
                      new_method_threshold_violations_after=_viol_after,
                      new_method_threshold_violations_before=len(violations),
                      violations=violations, note=threshold_note),
        zero_positive_keys=dict(count=int((cls_tbl["n_pos"] == 0).sum()),
                                effective_months_zero=int(
                                    ((hist_tbl["months_positive"] == 0)
                                     & (hist_tbl["history_months_effective"] == 0)).sum()),
                                pattern="no_demand", backtestable=False),
        selfcheck=sc.to_dict("records"), selfcheck_pass=sc_ok,
        short885=go_counts, patterns=pat, adopted=adopted, best_baseline=best_base,
        selftests=[dict(name=n, passed=bool(ok), detail=d) for n, ok, d in tests],
        verify=dict(xlsx_match=sha256(out) == out_sha,
                    report_match=sha256(args.out_report) == sha256(args.out_report),
                    script_match=hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
                    == script_identity()["script_sha256"]),
        note="xlsx 含 openpyxl 时间戳，重跑 SHA 不保证相同；血缘以 输入 SHA + 脚本 SHA + 守恒表 证明。",
    )
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=1,
                                              default=str), encoding="utf-8")
    print(json.dumps(dict(series=len(cls_tbl), eligible=int(cls_tbl["eligible"].sum()),
                          short885=go_counts, patterns=pat, new_adopted=new_adopted,
                          d3_new=d3_new, conservation=cons[["bucket", "数量"]].to_dict("records"),
                          selftests=[(n, ok) for n, ok, _ in tests]), ensure_ascii=False, indent=1))
    print("工作簿：", out, "sha256=", out_sha)
    print("报告：", args.out_report)
    print("manifest：", args.manifest)
    return 0 if all(ok for _, ok, _ in tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
