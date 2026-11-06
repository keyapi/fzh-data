# -*- coding: utf-8 -*-
"""Shadow benchmark v3: observed-month-only windows; no D5 proxy row.

v3 fixes vs v2:
- D2 censoring is stockout evidence, not demand coverage; censored months are excluded
- training and test windows both require all months to be real sales observations
- unknown/censored train or test months are skipped and reported separately
- current D5 proxy WAPE removed (future forecast vs ended history, different error basis)
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from statsforecast import models as sfm

BASE = Path("D:/Work/fzh-order-store/analysis")
SERIES = BASE / "D3b_v3_8_series_current_2026-11-07.parquet"
CLS = BASE / "D_历史归一与回测_D3b_v3_8_2026-11-07.xlsx"
D5 = BASE / "D5v6_6-60cm/D_概率与服务_D5_v6_6_2026-11-07.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v7.xlsx"
CENSOR = BASE / "D_销量清洗_v3_2026-11-02.xlsx"
OUT = BASE / "forecast_benchmark_20261107_v3.xlsx"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
MODELS = ("MA3", "SeasonalNaive", "AutoETS", "CrostonSBA", "TSB", "ADIDA")
MAX_ZERO, MAX_STABLE, MAX_SHORT = 30, 10, 10


def fit_model(name: str, y: np.ndarray, h: int) -> np.ndarray:
    if name == "MA3":
        return np.repeat(float(np.mean(y[-3:])), h)
    if name == "SeasonalNaive":
        m = sfm.SeasonalNaive(season_length=12)
    elif name == "AutoETS":
        m = sfm.AutoETS(season_length=12)
    elif name == "CrostonSBA":
        m = sfm.CrostonSBA()
    elif name == "TSB":
        m = sfm.TSB(alpha_d=0.2, alpha_p=0.2)
    elif name == "ADIDA":
        m = sfm.ADIDA()
    else:
        raise ValueError(name)
    m.fit(np.asarray(y, dtype=np.float64))
    return np.asarray(m.predict(h=h)["mean"], dtype=float)


def main() -> int:
    s = pd.read_parquet(SERIES)
    s["month"] = s["month"].astype(str)
    monthly = s.groupby(KEYS + ["month"], as_index=False)["qty"].sum()
    cls = pd.read_excel(CLS, sheet_name="3_分类")
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5_97 = d5[d5["horizon"].astype(str) == "97"].drop_duplicates(KEYS)
    meta = cls[KEYS + ["n_obs", "n_pos", "demand_pattern"]].merge(
        d5_97[KEYS + ["p50", "q95"]], on=KEYS, how="inner")
    meta["zero_median"] = (meta["p50"].fillna(0) <= 0) & (meta["q95"].fillna(0) > 0)

    cny = pd.read_excel(CNY, sheet_name="2_逐键排期").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    zero_keys = set(map(tuple, cny[cny["模型资格"].astype(str).eq("零中位数-待验证")][KEYS].values))
    meta["in_66"] = [tuple(x) in zero_keys for x in meta[KEYS].values]

    zero = meta[meta["in_66"]].head(MAX_ZERO).copy()
    stable = meta[(~meta["zero_median"]) & (meta["p50"] > 0)
                  & meta["demand_pattern"].isin(["smooth", "intermittent"])
                  & (meta["n_pos"] >= 6)].nlargest(MAX_STABLE, "q95").copy()
    short = meta[(~meta["zero_median"]) & (meta["p50"] > 0)
                 & (meta["n_obs"] <= 10)].nlargest(MAX_SHORT, "q95").copy()
    zero["segment"] = "zero_median"; stable["segment"] = "stable"; short["segment"] = "short"
    sample = pd.concat([zero, stable, short]).drop_duplicates(KEYS)
    sample.to_csv(BASE / "forecast_benchmark_20261107_v3_sample.csv", index=False,
                  encoding="utf-8-sig")

    # 观测状态：series=真实观测销量；D2 删失=缺货证据，不等于覆盖；其余=未知
    cen = pd.read_excel(CENSOR, sheet_name="2_删失")
    cen["month"] = cen["month"].astype(str).str.replace("-", "", regex=False)
    covered, censored = {}, {}
    for key, g in monthly.groupby(KEYS):
        covered.setdefault(key, set()).update(g["month"].astype(str))
    for _, r in cen.iterrows():
        pid = str(r["product_id"])
        for key in sample[KEYS].values:
            if str(key[0]) == pid and str(r["month"]) not in covered.get(tuple(key), set()):
                censored.setdefault(tuple(key), set()).add(str(r["month"]))
    hist = monthly.merge(sample[KEYS + ["segment"]], on=KEYS, how="inner")
    hist_map = {k: g.set_index("month")["qty"].astype(float).to_dict()
                for k, g in hist.groupby(KEYS)}
    rows, skips = [], []
    for _, sr in sample.iterrows():
        key = tuple(sr[k] for k in KEYS)
        seg = sr["segment"]
        months = sorted(covered.get(key, set()) | censored.get(key, set()))
        if len(months) < 8:
            skips.append(dict(segment=seg, product_id=key[0], pool=key[1], form=key[2],
                              uom=key[3], reason="history<8 observed/censored months",
                              detail=f"n={len(months)}"))
            continue
        idx = pd.period_range(pd.Period(months[0], freq="M"),
                              pd.Period(months[-1], freq="M"), freq="M")
        month_str = [p.strftime("%Y%m") for p in idx]
        qty = np.array([hist_map.get(key, {}).get(m, 0.0) for m in month_str])
        cov = np.array([m in covered.get(key, set()) for m in month_str])
        cens = np.array([m in censored.get(key, set()) for m in month_str])
        for h in (4, 6):
            for oi, origin in enumerate((len(qty) - h, len(qty) - 2 * h)):
                if origin < 6:
                    skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                      form=key[2], uom=key[3],
                                      reason="train<6 months", detail=f"origin={origin},h={h}"))
                    continue
                if not cov[origin:origin + h].all():
                    bad_c = int(cens[origin:origin + h].sum())
                    reason = "censored_test_month" if bad_c else "unknown_test_month"
                    skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                      form=key[2], uom=key[3], reason=reason, detail=f"h={h}"))
                    continue
                if not cov[:origin].all():
                    bad_c = int(cens[:origin].sum())
                    reason = "censored_train_month" if bad_c else "unknown_train_month"
                    skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                      form=key[2], uom=key[3], reason=reason, detail=f"h={h}"))
                    continue
                train = qty[:origin]
                test = qty[origin:origin + h]
                ok = {}
                for name in MODELS:
                    try:
                        pred = fit_model(name, train, h)
                        pred = np.maximum(0.0, pred[:h])
                        if not np.all(np.isfinite(pred)):
                            raise ValueError("non-finite forecast")
                        ok[name] = pred
                    except Exception as e:
                        skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                          form=key[2], uom=key[3],
                                          reason=f"model_fail:{name}", detail=str(e)[:80]))
                common_ok = len(ok) == len(MODELS)
                for name, pred in ok.items():
                    err = pred - test
                    rows.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                     form=key[2], uom=key[3], h=h, origin_idx=oi,
                                     model=name, actual=float(test.sum()),
                                     pred=float(pred.sum()),
                                     abs_err=float(np.abs(err).sum()),
                                     bias=float(err.sum()),
                                     common_ok=common_ok))
    detail = pd.DataFrame(rows)
    skip = pd.DataFrame(skips)
    detail.to_csv(BASE / "forecast_benchmark_20261107_v3_detail.csv", index=False,
                  encoding="utf-8-sig")
    skip.to_csv(BASE / "forecast_benchmark_20261107_v3_skips.csv", index=False,
                encoding="utf-8-sig")
    common = detail[detail["common_ok"] & detail["model"].isin(MODELS)].copy()
    summ = (common.groupby(["segment", "h", "model"])
            .agg(n=("pred", "size"), actual=("actual", "sum"), pred=("pred", "sum"),
                 abs_err=("abs_err", "sum"), bias=("bias", "sum")).reset_index())
    summ["WAPE"] = summ["abs_err"] / summ["actual"].replace(0, np.nan)
    summ["bias_rate"] = summ["bias"] / summ["actual"].replace(0, np.nan)
    summ = summ.round(4)
    cover = (detail.groupby(["segment", "h"])
             .agg(windows=("pred", "size"), keys=("product_id", "nunique"))
             .reset_index().round(4))
    notes = pd.DataFrame([
        ("目的", "修正观测状态/TSB/分母后的首轮对照；不宣布胜者"),
        ("样本", f"zero {len(zero)} / stable {len(stable)} / short {len(short)}，去重 {len(sample)}"),
        ("零中位数来源", "仅取 CNY v7 的 66 个零中位数键"),
        ("观测状态", "series=真实观测销量；D2删失=缺货证据，不当覆盖；其余=未知；训练/测试都要求全观测"),
        ("模型", "MA3 / SeasonalNaive(12) / AutoETS / CrostonSBA / TSB(0.2,0.2) / ADIDA"),
        ("共同窗口", "只汇总 6 个模型都成功的同一窗口；失败/跳过逐条见 4_失败与跳过"),
        ("D5", "v3 不比较 D5：未来预测 vs 已结束历史、horizon/误差定义不同；下一轮同 cutoff 再做"),
        ("未覆盖", "q95区间/补货库存指标/97-157天逐日，下一轮"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        notes.to_excel(w, sheet_name="0_说明", index=False)
        summ.to_excel(w, sheet_name="1_汇总", index=False)
        sample.to_excel(w, sheet_name="2_样本", index=False)
        detail.to_excel(w, sheet_name="3_逐键逐模型", index=False)
        skip.to_excel(w, sheet_name="4_失败与跳过", index=False)
        cover.to_excel(w, sheet_name="5_日历覆盖", index=False)
    print(summ.to_string(index=False))
    print("\nskips:\n", skip["reason"].value_counts().to_string())
    print("\nwrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
