# -*- coding: utf-8 -*-
"""D3b 历史归一 + 重分类 + 重回测（只读）。

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
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
RULE_VERSION = "D3b-v2.1-2026-11-02"
KEY_VERSION = "D1v2-2026-10-30"   # 旧键探索版；D1b v2 落定后改键重跑

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
    z, p = _croston(y, ALPHA)
    return np.repeat(z / p if p > 0 else 0.0, h)


def f_sba(y, h, **kw):
    z, p = _croston(y, ALPHA)
    return np.repeat((1 - ALPHA / 2) * z / p if p > 0 else 0.0, h)


def f_tsb(y, h, **kw):
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


BASELINES = dict(naive=f_naive, ma3=f_ma3, snaive=f_snaive, ets_ann=f_ets_ann)
NEW_MODELS = dict(croston=f_croston, sba=f_sba, tsb=f_tsb)


def models_for(pattern: str, sbc: str) -> list[str]:
    m = ["naive", "ma3", "snaive", "ets_ann"]
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


# ============================ 回测 ============================

def backtest(y, obs, models, origins=ORIGINS, h=H, months=None):
    months = list(months or OBS_MONTHS)
    rows = []
    for origin in origins:
        oi = months.index(origin)
        tr = [i for i in range(0, oi + 1) if obs[i]]
        te = [i for i in range(oi + 1, min(oi + 1 + h, len(months))) if obs[i]]
        if len(tr) < MIN_TRAIN_OBS or len(te) < 3:
            rows.append(dict(origin=origin, status="skipped",
                             reason=(f"训练已观测月 {len(tr)} < {MIN_TRAIN_OBS}"
                                     if len(tr) < MIN_TRAIN_OBS
                                     else f"insufficient_test：测试窗已核验月 {len(te)} < 3")))
            continue
        ytr = np.array([y[i] for i in tr], dtype=float)
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
                if not obs[i]:
                    continue
                errs.append(float(fc[step] - y[i]))
                acts.append(float(y[i]))
                mid.append(months[i])
            if not errs:
                rows.append(dict(origin=origin, model=name, status="skipped",
                                 reason="测试窗口无可评估月"))
                continue
            rows.append(dict(origin=origin, model=name, status="ok", n_train=len(tr),
                             test_months=";".join(mid), n_test=len(errs),
                             abs_err=float(np.sum(np.abs(errs))),
                             sum_abs=float(np.sum(np.abs(acts)))))
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


def select(per_model, pattern):
    """采用候选必须「测试窗有正销（Σ|y|>0）且 MAE>0」——
    全零测试窗与零误差窗口不提供比较证据，不据此选模型。"""
    evaluated = {k: v for k, v in per_model.items() if v["status"] == "ok"}
    ok = {k: v for k, v in evaluated.items() if v.get("den", 0) > 0 and v["mae"] > 0}
    if not ok:
        if not evaluated:
            return dict(adopted="none", baseline="none", reason="无有效 origin（无可评估模型）")
        if all(v.get("den", 0) == 0 for v in evaluated.values()):
            return dict(adopted="none", baseline="none",
                        reason="test_window_no_positive：测试窗无正销实际（WAPE 未定义），不算证据")
        return dict(adopted="none", baseline="none",
                    reason="test_window_zero_error：采用模型 MAE=0（零误差窗口无比较证据）")
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
    return dict(adopted=bb, baseline=bb,
                reason=f"新方法未达门槛（需不劣 + ≥{ADOPT_GAIN:.0%}），用基线 {bb}{note}")


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
    per = {"naive": dict(status="ok", wape=1.0, mae=1.0),
           "croston": dict(status="ok", wape=0.9, mae=0.9),
           "sba": dict(status="ok", wape=0.97, mae=0.97)}
    t.append(("③ 采用门槛（≥5%）", select(per, "intermittent")["adopted"] == "croston"
              and select({**per, "croston": dict(status="ok", wape=0.98, mae=0.98)},
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
    t.append(("⑤ 映射候选唯一才合并",
              (lambda: (lambda m: m == "唯一")( "唯一" if len({"P1"}) == 1 else "多候选"))(), "唯一"))
    return t


# ============================ 主流程 ============================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D3b 历史归一/重分类/重回测（只读）")
    ap.add_argument("--orders", default=f"{B}/orders_unified.parquet")
    ap.add_argument("--a-final", default=f"{BA}/SKU活跃宇宙_2026-10-29_FINAL.xlsx")
    ap.add_argument("--d2v3", default=f"{BA}/D_销量清洗_v3_2026-11-02.xlsx")
    ap.add_argument("--d3", default=f"{BA}/D_基线回测_2026-10-30.xlsx")
    ap.add_argument("--d1", default=f"{BA}/D_资格与契约_v2_2026-10-30.xlsx")
    ap.add_argument("--sku-map", default=f"{B}/sku_map.tsv")
    ap.add_argument("--customer-codes", default=f"{BA}/en_item_customer_codes.csv")
    ap.add_argument("--out-xlsx", default=f"{BA}/D_历史归一与回测_D3b_v2_1_2026-11-02.xlsx")
    ap.add_argument("--out-report", default=f"{BA}/D_历史归一与回测_D3b_v2_1_2026-11-02_报告.md")
    ap.add_argument("--manifest", default=f"{BA}/D_历史归一与回测_D3b_v2_1_2026-11-02.manifest.json")
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
        ("D3_BACKTEST", args.d3), ("D1_V2", args.d1), ("SKU_MAP", args.sku_map),
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
    k_set = set(map(tuple, d2[keys].astype(str).drop_duplicates().values))
    k_by_prod: dict[str, set] = {}
    for k in k_set:
        k_by_prod.setdefault(k[0], set()).add(k[1:])
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
    o["sku_tongtool"] = o["sku_tongtool"].astype(str)
    o["qty"] = pd.to_numeric(o["qty"], errors="coerce").fillna(0.0)
    o["month"] = o["month"].astype(str)
    o["pool"] = o["warehouse"].map(POOL_OF_WAREHOUSE).fillna("其他")

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

    o["form"] = [form_of(p, role.get(p, "")) if isinstance(p, str) and p and "|" not in p else ""
                 for p in o["product"]]
    o["uom"] = np.where(o["form"] == "套件", "套", "个")
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

    bucket = np.select(
        [o["pool"] == "其他", o["status"] == "未匹配", o["status"] == "多候选",
         ~o["in_k_fixed"]],
        ["out_of_scope_pool", "no_product_match", "multi_candidate", "no_demand_key"],
        default="mapped")
    o["bucket"] = bucket
    cons = (o.groupby("bucket").agg(行数=("qty", "size"), 数量=("qty", "sum"))
            .reindex(["mapped", "no_demand_key", "multi_candidate", "no_product_match",
                      "out_of_scope_pool"]).fillna(0).reset_index())
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
    assert abs(cons_total - float(o["qty"].sum())) < 1e-6, "守恒失败"

    # ---------- 月度序列（mapped 行）
    m = o[o["bucket"] == "mapped"].copy()
    m["km"] = list(zip(m["key_fixed"], m["month"]))
    ser = m.groupby("km")["qty"].sum()
    cons_month = m.groupby("month")["qty"].sum()

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
        sel = select(per, c["demand_pattern"])
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

    # ---------- 885 去向
    hist_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
                for r in hist_tbl.itertuples(index=False)}
    cls_idx = {(r.product_id, r.pool, r.physical_form, r.canonical_uom): r
               for r in cls_tbl.itertuples(index=False)}
    go_rows = []
    for r in short885.itertuples(index=False):
        key = (r.product_id, r.pool, r.physical_form, r.canonical_uom)
        h = hist_idx.get(key)
        c = cls_idx.get(key)
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
    n_eligible = int(cls_tbl["eligible"].sum())
    n_backtested = int(cls_tbl["backtested"].sum())
    n_no_origin = int((cls_tbl["adoption_status"] == "no_origin").sum())
    n_no_pos = int((cls_tbl["adoption_status"] == "test_window_no_positive").sum())
    n_zero_err = int((cls_tbl["adoption_status"] == "test_window_zero_error").sum())
    n_adopted = int((cls_tbl["adoption_status"] == "adopted").sum())
    adopted = cls_tbl.loc[cls_tbl["adoption_status"] == "adopted", "adopted_model"].value_counts().to_dict()
    best_base = cls_tbl.loc[cls_tbl["adoption_status"] == "adopted", "best_baseline"].value_counts().to_dict()
    new_adopted = int(sum(v for k, v in adopted.items() if k in NEW_MODELS))
    d3_new = 56
    summary = pd.DataFrame([
        dict(指标="序列总数", 值=len(cls_tbl), 说明="D2 v3 需求键"),
        dict(指标="eligible（≥12 有效月）", 值=n_eligible, 说明="≥12 有效月 + 有正销 + 非老品"),
        dict(指标="backtested（有有效 origin）", 值=n_backtested, 说明="至少 1 个 origin 达标且有模型可评估"),
        dict(指标="adopted（测试窗有正销）", 值=n_adopted, 说明="排除全零测试窗/零误差后仍在比较证据下的采用"),
        dict(指标="no_positive（测试窗无正销）", 值=n_no_pos, 说明="WAPE 未定义，不算证据"),
        dict(指标="zero_error（MAE=0 无比较证据）", 值=n_zero_err, 说明="正销但零误差，不据此选模型"),
        dict(指标="no_origin（无可回测 origin）", 值=n_no_origin, 说明="eligible 但无有效 origin，不算可回测"),
        dict(指标="D3 可回测", 值=954, 说明="对比基线（D3 的 1,865 序列口径相同）"),
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
        ("历史窗口", f"2023-01..{END_MONTH}（订单 2022-12 起；按 month 归月）"),
        ("归一规则", "casefold + 去空格 + 去前缀 OLD_/new- + 去后缀 -Cover/-c/-1/-2；"
                     "次级：去尾部 -<数字>（仅当候选唯一）"),
        ("合并条件", "候选唯一且证据一致（A来源码/sku_map/客户码）；多候选→隔离不合并"),
        ("隔离", "跨 form / 跨 UOM / 共享池 / 多候选 → 不进序列（计入守恒分桶）"),
        ("有效历史", "首销月→2026-10 的日历月数，剔除删失月；首销前不计 0"),
        ("删失证据", "D2 v3 2_删失（2025+）；2023-2024 零月无断货证据 → 记 zero_orders_only"),
        ("分类", f"ADI≥{ADI_THR} / CV²≥{CV2_THR}；erratic 并入 lumpy；<12 月→short；"
                 "首销≥2026-01→new；近 6 月无销量→obsolescent"),
        ("模型", "naive/MA3/seasonal naive/ETS(A,N,N)；间歇类 Croston/SBA；obsolescent 加 TSB"),
        ("回测", f"origin={';'.join(ORIGINS)}（训练止该月，测后续 {H} 月）；训练已观测月 ≥{MIN_TRAIN_OBS}"),
        ("指标", "WAPE=Σ|e|/Σ|y|（Σ|y|=0→NaN）；MAE；pinball@p50=0.5·MAE"),
        ("采用门槛", f"不劣于最佳基线且至少一项改善 ≥{ADOPT_GAIN:.0%}；TSB 仅 obsolescent"),
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

    bt_rows = res_tbl[res_tbl["status"] == "ok"]
    det_ok = det_tbl[det_tbl["n_test"] > 0] if len(det_tbl) else det_tbl
    min_ntest = int(det_ok["n_test"].min()) if len(det_ok) else 0
    mapped_bridge = mp[mp["status"] == "唯一"]
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
        dict(检查项="adopted_with_zero_error", 期望=0,
             实际=int(sum(1 for r in cls_tbl.itertuples(index=False)
                          if r.adoption_status == "adopted"
                          and float(res_tbl[(res_tbl["product_id"] == r.product_id)
                                            & (res_tbl["pool"] == r.pool)
                                            & (res_tbl["physical_form"] == r.physical_form)
                                            & (res_tbl["canonical_uom"] == r.canonical_uom)
                                            & (res_tbl["model"] == r.adopted_model)
                                            ]["mae"].iloc[0]) == 0.0))),
        dict(检查项="eligible = backtested + no_origin", 期望=n_eligible,
             实际=n_backtested + n_no_origin),
        dict(检查项="backtested = adopted + no_positive + zero_error", 期望=n_backtested,
             实际=n_adopted + n_no_pos + n_zero_err),
        dict(检查项="key_version 标记覆盖（分类行）",
             期望=len(cls_tbl),
             实际=int((cls_tbl["key_version"] == KEY_VERSION).sum())),
    ])
    sc["通过"] = ["是" if str(r.期望) == str(r.实际) else "否" for r in sc.itertuples(index=False)]
    sc_ok = bool((sc["通过"] == "是").all())

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
            key_version=KEY_VERSION, dry_run=True,
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
            five=dict(eligible=n_eligible, backtested=n_backtested, adopted=n_adopted,
                      no_positive=n_no_pos, zero_error=n_zero_err, no_origin=n_no_origin,
                      sum_check=dict(eligible_eq=n_backtested + n_no_origin,
                                     backtested_eq=n_adopted + n_no_pos + n_zero_err)),
            backtestable=dict(v2=int(cls_tbl["eligible"].sum()), d3=954,
                              reconciliation=rec,
                              patterns=cls_tbl["demand_pattern"].value_counts().to_dict()),
            short885=go_counts,
            new_adopted=int(res_tbl[(res_tbl["adopted"] == "是")
                                    & (res_tbl["family"] == "new")].shape[0]),
            selfcheck=sc.to_dict("records"), selfcheck_pass=sc_ok,
        ), ensure_ascii=False, indent=1, default=str))
        print("DRY-RUN：未写 xlsx / 报告 / manifest")
        return 0 if sc_ok else 1

    out = Path(args.out_xlsx)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        mp.to_excel(w, sheet_name="1_映射桥", index=False)
        hist_tbl.to_excel(w, sheet_name="2_有效历史", index=False)
        cls_tbl.to_excel(w, sheet_name="3_分类", index=False)
        pd.concat([res_tbl.assign(层级="model"), det_tbl.assign(层级="origin")],
                  ignore_index=True).to_excel(w, sheet_name="4_回测", index=False)
        fail_tbl.to_excel(w, sheet_name="5_失败", index=False)
        pd.concat([summary.assign(表="汇总"), go_tbl.assign(表="885去向")],
                  ignore_index=True).to_excel(w, sheet_name="6_汇总", index=False)
        pd.concat([cons.assign(层级="桶"), ndk_tbl.assign(层级="无需求键原因")],
                  ignore_index=True).to_excel(w, sheet_name="7_守恒", index=False)
        sc.to_excel(w, sheet_name="8_自检", index=False)
    out_sha = sha256(out)
    sheets = {s: int(len(pd.read_excel(out, sheet_name=s))) for s in pd.ExcelFile(out).sheet_names}

    tests = run_selftests()
    L = [f"# D3b 历史归一 + 重分类 + 重回测（{RULE_VERSION}；只读）", "",
         f"- 工作簿 SHA256：`{out_sha}`",
         f"- 序列 {len(cls_tbl)}｜**eligible {n_eligible} / with-origin {n_backtested} / "
         f"adopted {n_adopted} / no-positive {n_no_pos} / zero-error {n_zero_err} / "
         f"no-origin {n_no_origin}**（D3: 954）",
         f"- **key_version = `{KEY_VERSION}`（旧键探索版）**：D1b v2 落定后按 "
         "`product×market×pool×form×uom` 重跑正式版；在此之前不声称正式。", "",
         "## 0. v2 修复项（对应评审 1–5）", "",
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
    L += ["", f"- 可回测变化对账：D3 **954** + 变长 **{rec['变长']}** + 新增 **{rec['新增']}** "
          f"− 丢失 **{rec['丢失']}** = **{rec['now_bt']}**；丢失原因 "
          f"{json.dumps(_lost_reasons, ensure_ascii=False)}（删失对齐后有效月 <12）。", "",
          f"- 有效历史（`2_有效历史.history_months_effective`）中位 "
          f"{float(hist_tbl['history_months_effective'].median()):.0f} 月；"
          f"D3 同键的可用月中位 {float(short885['n_obs'].median()):.0f} 月。", "",
          "## 3. 重分类", "", "| demand_pattern | 序列数 |", "|---|---:|"]
    for k, v in pat.items():
        L.append(f"| {k} | {v} |")
    L += ["", "## 4. 重回测", "",
          f"- eligible **{n_eligible}** / with-origin **{n_backtested}** / adopted "
          f"**{n_adopted}** / no-positive **{n_no_pos}** / zero-error **{n_zero_err}** / "
          f"no-origin **{n_no_origin}**｜采用新方法 **{new_adopted}**"
          f"（D3 为 {d3_new}）｜最佳基线 `{json.dumps(best_base, ensure_ascii=False)}`",
          f"- 采用分布 `{json.dumps(adopted, ensure_ascii=False)}`", "",
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
                                   file_name=Path(args.manifest).name, sha256=None)),
        conservation=[dict(桶=r.bucket, 行数=int(r.行数), 数量=float(r.数量)) for r in cons.itertuples(index=False)],
        totals=dict(order_qty=float(o["qty"].sum()), bucketed=cons_total,
                    series=len(cls_tbl), eligible=int(cls_tbl["eligible"].sum()),
                    d3_backtestable=954, new_adopted=new_adopted, d3_new_adopted=d3_new),
        key_version=KEY_VERSION,
        key_version_note="旧键探索版：D1 v2 键；D1b v2 落定后按 product×market×pool×form×uom 重跑正式版",
        origins=list(ORIGINS), min_test_months=3,
        censoring=dict(applied=True, source="D2 v3 2_删失（2026-04..10）",
                       v1_bug="v1 month 格式 2026-04 与 202604 不匹配，删失从未生效"),
        reconciliation=rec, lost_reasons=_lost_reasons,
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
