# -*- coding: utf-8 -*-
"""First-pass shadow benchmark: standard forecast models vs D5 on frozen inputs.

Scope:
- monthly demand from D3b v3.8 current series
- sample: zero-median keys + stable + short-history
- models: MA3, SeasonalNaive, AutoETS, CrostonSBA, TSB, ADIDA
- rolling origins, horizons 4 and 6 months
- metrics: WAPE / MAE / bias; zero-median keys reported separately

This is a method-suitability screen, not a winner declaration.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from statsforecast import models as sfm

BASE = Path("D:/Work/fzh-order-store/analysis")
SERIES = BASE / "D3b_v3_8_series_current_2026-11-07.parquet"
CLS = BASE / "D_历史归一与回测_D3b_v3_8_2026-11-07.xlsx"
D5 = BASE / "D5v6_6-60cm/D_概率与服务_D5_v6_6_2026-11-07.xlsx"
OUT = BASE / "forecast_benchmark_20261107.xlsx"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
MAX_ZERO, MAX_STABLE, MAX_SHORT = 30, 10, 10


def fit_model(name, y, h):
    if name == "MA3":
        return np.repeat(float(np.mean(y[-3:])), h)
    if name == "SeasonalNaive":
        m = sfm.SeasonalNaive(season_length=12)
    elif name == "AutoETS":
        m = sfm.AutoETS(season_length=12)
    elif name == "CrostonSBA":
        m = sfm.CrostonSBA()
    elif name == "TSB":
        m = sfm.TSB()
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
    cls = pd.read_excel(CLS, sheet_name="3_分类").rename(
        columns={"pool": "pool", "physical_form": "physical_form",
                 "canonical_uom": "canonical_uom"})
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5["horizon"].astype(str) == "97"].rename(
        columns={"pool": "pool", "physical_form": "physical_form",
                 "canonical_uom": "canonical_uom"})
    meta = cls[KEYS + ["n_obs", "n_pos", "demand_pattern", "eligible"]].merge(
        d5[KEYS + ["p50", "q95"]], on=KEYS, how="inner")
    meta["zero_median"] = (meta["p50"].fillna(0) <= 0) & (meta["q95"].fillna(0) > 0)
    zero = meta[meta["zero_median"]].head(MAX_ZERO)
    stable = meta[(~meta["zero_median"]) & (meta["p50"] > 0)
                  & meta["demand_pattern"].isin(["smooth", "intermittent"])
                  & (meta["n_pos"] >= 6)].nlargest(MAX_STABLE, "q95")
    short = meta[(~meta["zero_median"]) & (meta["p50"] > 0)
                 & (meta["n_obs"] <= 6)].nlargest(MAX_SHORT, "q95")
    zero["segment"] = "zero_median"; stable["segment"] = "stable"; short["segment"] = "short"
    sample = pd.concat([zero, stable, short]).drop_duplicates(KEYS)
    sample.to_csv(BASE / "forecast_benchmark_20261107_sample.csv", index=False,
                  encoding="utf-8-sig")

    hist = monthly.merge(sample[KEYS + ["segment"]], on=KEYS, how="inner")
    rows = []
    for key, g in hist.groupby(KEYS):
        y_all = g.sort_values("month")["qty"].astype(float).to_numpy()
        seg = g["segment"].iat[0]
        if len(y_all) < 8:
            continue
        for h in (4, 6):
            origins = [len(y_all) - h, len(y_all) - 2 * h]
            for oi, origin in enumerate(origins):
                if origin < 6:
                    continue
                train = y_all[:origin]
                test = y_all[origin:origin + h]
                if len(test) < h:
                    continue
                for name in ("MA3", "SeasonalNaive", "AutoETS", "CrostonSBA", "TSB", "ADIDA"):
                    try:
                        pred = fit_model(name, train, h)
                        pred = np.maximum(0.0, pred[:h])
                        err = pred - test
                        rows.append(dict(
                            segment=seg, product_id=key[0], pool=key[1],
                            form=key[2], uom=key[3], h=h, origin_idx=oi,
                            model=name, actual=float(test.sum()),
                            pred=float(pred.sum()),
                            abs_err=float(np.abs(err).sum()),
                            bias=float(err.sum())))
                    except Exception as e:
                        rows.append(dict(
                            segment=seg, product_id=key[0], pool=key[1],
                            form=key[2], uom=key[3], h=h, origin_idx=oi,
                            model=name, actual=float(test.sum()), pred=np.nan,
                            abs_err=np.nan, bias=np.nan,
                            error=f"{type(e).__name__}: {e}"[:80]))
    detail = pd.DataFrame(rows)
    detail.to_csv(BASE / "forecast_benchmark_20261107_detail.csv", index=False,
                  encoding="utf-8-sig")
    summ = (detail.dropna(subset=["pred"]).groupby(["segment", "h", "model"])
            .agg(n=("pred", "size"), actual=("actual", "sum"),
                 pred=("pred", "sum"), abs_err=("abs_err", "sum"),
                 bias=("bias", "sum")).reset_index())
    summ["WAPE"] = summ["abs_err"] / summ["actual"].replace(0, np.nan)
    summ["bias_rate"] = summ["bias"] / summ["actual"].replace(0, np.nan)
    summ = summ.round(4)
    notes = pd.DataFrame([
        ("目的", "首轮方法适配性筛查，不宣布胜者"),
        ("样本", f"zero {len(zero)} / stable {len(stable)} / short {len(short)}，去重后 {len(sample)}"),
        ("输入", str(SERIES)),
        ("模型", "MA3 / SeasonalNaive(12) / AutoETS / CrostonSBA / TSB / ADIDA"),
        ("验证", "月度滚动，h=4/6，两个 origin；不是 97/157 天逐日"),
        ("指标", "WAPE / bias；零中位数段另看 MAE（actual 可能为 0）"),
        ("未覆盖", "q95 区间校准、补货库存指标、全量 SKU；下一轮再做"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        notes.to_excel(w, sheet_name="0_说明", index=False)
        summ.to_excel(w, sheet_name="1_汇总", index=False)
        sample.to_excel(w, sheet_name="2_样本", index=False)
        detail.to_excel(w, sheet_name="3_逐键逐模型", index=False)
    print(summ.to_string(index=False))
    print("\nwrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
