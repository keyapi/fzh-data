# -*- coding: utf-8 -*-
"""Shadow benchmark v3b: observed-month windows + monthly inventory policy metrics.

This is a monthly proxy for 97/157-day windows; a true daily/weekly run is blocked
by the source data (only sale-date rows, no continuous daily observations).
"""
from __future__ import annotations
from pathlib import Path
import math
import numpy as np
import pandas as pd
from statsforecast import models as sfm

BASE = Path("D:/Work/fzh-order-store/analysis")
SERIES = BASE / "D3b_v3_8_series_current_2026-11-07.parquet"
CLS = BASE / "D_历史归一与回测_D3b_v3_8_2026-11-07.xlsx"
D5 = BASE / "D5v6_6-60cm/D_概率与服务_D5_v6_6_2026-11-07.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v7.xlsx"
CENSOR = BASE / "D_销量清洗_v3_2026-11-02.xlsx"
D6 = BASE / "D6v6_15-final/D_Top50沙盒_D6_v6_15_2026-11-07.xlsx"
OUT = BASE / "forecast_benchmark_20261107_v3b.xlsx"
PROD = {"美东USNJ": 30.0, "美中USTX": 35.2, "波兰": 43.6}
MODE_DAYS = {"空运": 14, "快船": 30, "普船": 55, "专线": 60}
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


def inv_sim(forecast, actual, init_stock, lead_months):
    stock = max(0.0, float(init_stock))
    pipeline = [0.0] * max(1, int(lead_months))
    short_units = 0.0
    short_weeks = 0
    stock_path = []
    for t, dem in enumerate(actual):
        stock += pipeline.pop(0)
        short = max(0.0, dem - stock)
        short_units += short
        short_weeks += 1 if short > 0 else 0
        stock = max(0.0, stock - dem)
        target = float(np.sum(forecast[t:t + len(pipeline) + 1])) + float(np.mean(forecast))
        on_order = float(np.sum(pipeline))
        pipeline.append(max(0.0, target - stock - on_order))
        stock_path.append(stock)
    total = float(np.sum(actual))
    return dict(short_units=short_units, short_weeks=short_weeks,
                fill=(1 - short_units / total) if total > 0 else 1.0,
                avg_stock=float(np.mean(stock_path)) if stock_path else 0.0,
                end_stock=float(stock_path[-1]) if stock_path else 0.0,
                end_in_transit=float(np.sum(pipeline)))


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
    d6 = pd.read_excel(D6, sheet_name="1_全量动作").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    sample = sample.merge(d6[KEYS + ["C可发供给", "推荐main_haul"]], on=KEYS, how="left")
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
                    mode = str(sr.get("推荐main_haul", "空运")).replace("海运", "")
                    lead_m = max(1, math.ceil((PROD.get(str(key[1]), 30.0) + 2
                                               + MODE_DAYS.get(mode, 30)) / 30))
                    init = sr.get("C可发供给")
                    inv = (inv_sim(pred, test, init, lead_m) if pd.notna(init)
                           else dict(short_units=np.nan, short_weeks=np.nan,
                                     fill=np.nan, avg_stock=np.nan, end_stock=np.nan,
                                     end_in_transit=np.nan))
                    rows.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                     form=key[2], uom=key[3], h=h, origin_idx=oi,
                                     model=name, actual=float(test.sum()),
                                     pred=float(pred.sum()),
                                     abs_err=float(np.abs(err).sum()),
                                     bias=float(err.sum()),
                                     common_ok=common_ok,
                                     lead_months=lead_m, init_stock=init, **inv))
    detail = pd.DataFrame(rows)
    skip = pd.DataFrame(skips)
    detail.to_csv(BASE / "forecast_benchmark_20261107_v3b_detail.csv", index=False,
                  encoding="utf-8-sig")
    skip.to_csv(BASE / "forecast_benchmark_20261107_v3b_skips.csv", index=False,
                encoding="utf-8-sig")
    common = detail[detail["common_ok"] & detail["model"].isin(MODELS)].copy()
    summ = (common.groupby(["segment", "h", "model"])
            .agg(n=("pred", "size"), actual=("actual", "sum"), pred=("pred", "sum"),
                 abs_err=("abs_err", "sum"), bias=("bias", "sum"),
                 short_units=("short_units", "sum"), short_weeks=("short_weeks", "sum"),
                 avg_stock=("avg_stock", "mean"), end_stock=("end_stock", "mean"),
                 end_in_transit=("end_in_transit", "mean"))
            .reset_index())
    summ["WAPE"] = summ["abs_err"] / summ["actual"].replace(0, np.nan)
    summ["bias_rate"] = summ["bias"] / summ["actual"].replace(0, np.nan)
    summ["fill"] = 1 - summ["short_units"] / summ["actual"].replace(0, np.nan)
    summ = summ.round(4)
    cover = (detail.groupby(["segment", "h"])
             .agg(windows=("pred", "size"), keys=("product_id", "nunique"))
             .reset_index().round(4))
    notes = pd.DataFrame([
        ("目的", "97/157 天窗口的月度代理 + 固定政策库存模拟；不宣布胜者"),
        ("样本", f"zero {len(zero)} / stable {len(stable)} / short {len(short)}，去重 {len(sample)}"),
        ("零中位数来源", "仅取 CNY v7 的 66 个零中位数键"),
        ("观测状态", "series=真实观测销量；D2删失=缺货证据，不当覆盖；训练/测试都要求全观测"),
        ("粒度", "月度 4/6 个月代理 97/157 天；真实日/周级因只有成交日、无连续观测，v4 已证明跑不出共同窗口"),
        ("模型", "MA3 / SeasonalNaive(12) / AutoETS / CrostonSBA / TSB(0.2,0.2) / ADIDA"),
        ("库存", "固定政策模拟：初始 C 可发、lead=生产+prehaul2+运输、order-up-to；不是历史还原"),
        ("未覆盖", "q95区间/真实日级/资金占用；下一轮"),
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
