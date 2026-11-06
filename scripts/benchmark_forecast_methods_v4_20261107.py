# -*- coding: utf-8 -*-
"""Benchmark v4: 97/157-day windows at weekly buckets + inventory policy simulation.

Why weekly: the daily series only has sale-date rows (median 41 days/key), so a
true daily zero-filled series would fabricate observations. Weekly aggregation
is the smallest bucket with enough observed periods; unknown weeks are skipped.

Inventory is a fixed-policy simulation, not a historical replay:
- initial stock = current C available (same for every model)
- lead weeks = ceil((production + prehaul 2 + transport days)/7)
- order-up-to forecast demand over lead + 1 safety week
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
D6 = BASE / "D6v6_15-final/D_Top50沙盒_D6_v6_15_2026-11-07.xlsx"
D2 = BASE / "D_销量清洗_v3_2026-11-02.xlsx"
CNY = BASE / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-06_v7.xlsx"
OUT = BASE / "forecast_benchmark_20261107_v4.xlsx"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]
MODELS = ("MA3", "SeasonalNaive", "AutoETS", "CrostonSBA", "TSB", "ADIDA")
H_WEEKS = (14, 22)  # 97/157 days
PROD = {"美东USNJ": 30.0, "美中USTX": 35.2, "波兰": 43.6}
MODE_DAYS = {"空运": 14, "快船": 30, "普船": 55, "专线": 60}


def fit_model(name, y, h):
    if name == "MA3":
        return np.repeat(float(np.mean(y[-3:])), h)
    if name == "SeasonalNaive":
        m = sfm.SeasonalNaive(season_length=4)
    elif name == "AutoETS":
        m = sfm.AutoETS(season_length=4)
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


def inv_sim(forecast, actual, init_stock, lead_weeks):
    stock = max(0.0, float(init_stock))
    pipeline = [0.0] * max(1, int(lead_weeks))
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
    s["date"] = pd.to_datetime(s["date"])
    s["week"] = s["date"].dt.to_period("W-MON").dt.start_time.dt.strftime("%Y-%m-%d")
    weekly = s.groupby(KEYS + ["week"], as_index=False)["qty"].sum()
    cls = pd.read_excel(CLS, sheet_name="3_分类")
    d5 = pd.read_excel(D5, sheet_name="1_预测")
    d5 = d5[d5["horizon"].astype(str) == "97"].drop_duplicates(KEYS)
    meta = cls[KEYS + ["n_obs", "n_pos", "demand_pattern"]].merge(
        d5[KEYS + ["p50", "q95"]], on=KEYS, how="inner")
    meta["zero_median"] = (meta["p50"].fillna(0) <= 0) & (meta["q95"].fillna(0) > 0)
    cny = pd.read_excel(CNY, sheet_name="2_逐键排期").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    zero_keys = set(map(tuple, cny[cny["模型资格"].astype(str).eq("零中位数-待验证")][KEYS].values))
    meta["in_66"] = [tuple(x) in zero_keys for x in meta[KEYS].values]
    zero = meta[meta["in_66"]].head(30).copy()
    stable = meta[(~meta["zero_median"]) & (meta["p50"] > 0)
                  & meta["demand_pattern"].isin(["smooth", "intermittent"])
                  & (meta["n_pos"] >= 6)].nlargest(10, "q95").copy()
    short = meta[(~meta["zero_median"]) & (meta["p50"] > 0)
                 & (meta["n_obs"] <= 10)].nlargest(10, "q95").copy()
    zero["segment"] = "zero_median"; stable["segment"] = "stable"; short["segment"] = "short"
    sample = pd.concat([zero, stable, short]).drop_duplicates(KEYS)
    d6 = pd.read_excel(D6, sheet_name="1_全量动作").rename(
        columns={"池": "pool", "形态": "physical_form", "UOM": "canonical_uom"})
    sample = sample.merge(d6[KEYS + ["C可发供给", "推荐main_haul"]], on=KEYS, how="left")
    d2 = pd.read_excel(D2, sheet_name="1_序列",
                       usecols=["product_id", "pool", "physical_form", "canonical_uom",
                                "month", "observation_status"])
    d2["month"] = d2["month"].astype(str)
    covered_months = {
        tuple(k): set(g["month"]) for k, g in
        d2[d2["observation_status"].astype(str).eq("observed")].groupby(KEYS)}

    hist = weekly.merge(sample[KEYS + ["segment"]], on=KEYS, how="inner")
    hist_map = {k: g.set_index("week")["qty"].astype(float).to_dict()
                for k, g in hist.groupby(KEYS)}
    rows, skips = [], []
    for _, sr in sample.iterrows():
        key = tuple(sr[k] for k in KEYS)
        seg = sr["segment"]
        months = sorted(covered_months.get(key, set()))
        if len(months) < 8:
            skips.append(dict(segment=seg, product_id=key[0], pool=key[1], form=key[2],
                              uom=key[3], reason="covered months<8", detail=f"n={len(months)}"))
            continue
        starts = [pd.Period(f"{m[:4]}-{m[4:]}", freq="M").start_time for m in months]
        ends = [pd.Period(f"{m[:4]}-{m[4:]}", freq="M").end_time for m in months]
        week_set = set()
        for st, en in zip(starts, ends):
            for p in pd.period_range(st, en, freq="W-MON"):
                week_set.add(p)
        idx = sorted(week_set)
        if len(idx) < 8:
            skips.append(dict(segment=seg, product_id=key[0], pool=key[1], form=key[2],
                              uom=key[3], reason="covered weeks<8", detail=f"n={len(idx)}"))
            continue
        week_str = [p.start_time.strftime("%Y-%m-%d") for p in idx]
        cov = np.ones(len(week_str), dtype=bool)
        qty = np.array([hist_map.get(key, {}).get(w, 0.0) for w in week_str])
        mode = str(sr.get("推荐main_haul", "空运")).replace("海运", "")
        lead_weeks = max(1, math.ceil((PROD.get(str(key[1]), 30.0) + 2
                                       + MODE_DAYS.get(mode, 30)) / 7))
        init = sr.get("C可发供给")
        for h in H_WEEKS:
            for oi, origin in enumerate((len(qty) - h, len(qty) - 2 * h)):
                if origin < 6:
                    skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                      form=key[2], uom=key[3], reason="train<6w",
                                      detail=f"h={h}"))
                    continue
                if not cov[origin:origin + h].all():
                    skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                      form=key[2], uom=key[3], reason="uncovered_test_week",
                                      detail=f"h={h}"))
                    continue
                if not cov[:origin].all():
                    skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                      form=key[2], uom=key[3], reason="uncovered_train_week",
                                      detail=f"h={h}"))
                    continue
                train, test = qty[:origin], qty[origin:origin + h]
                ok = {}
                for name in MODELS:
                    try:
                        pred = np.maximum(0.0, fit_model(name, train, h)[:h])
                        if not np.all(np.isfinite(pred)):
                            raise ValueError("non-finite")
                        ok[name] = pred
                    except Exception as e:
                        skips.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                          form=key[2], uom=key[3],
                                          reason=f"model_fail:{name}", detail=str(e)[:80]))
                if len(ok) != len(MODELS):
                    continue
                for name, pred in ok.items():
                    err = pred - test
                    inv = (inv_sim(pred, test, init, lead_weeks)
                           if pd.notna(init) else dict(short_units=np.nan, short_weeks=np.nan,
                                                       fill=np.nan, avg_stock=np.nan,
                                                       end_stock=np.nan))
                    rows.append(dict(segment=seg, product_id=key[0], pool=key[1],
                                     form=key[2], uom=key[3], h_weeks=h, origin_idx=oi,
                                     model=name, actual=float(test.sum()),
                                     pred=float(pred.sum()),
                                     abs_err=float(np.abs(err).sum()),
                                     bias=float(err.sum()),
                                     lead_weeks=lead_weeks, init_stock=init,
                                     **inv))
    detail = pd.DataFrame(rows)
    skip = pd.DataFrame(skips)
    if detail.empty:
        print("NO COMMON WINDOWS")
        if not skip.empty:
            print(skip["reason"].value_counts().to_string())
        empty = pd.DataFrame(columns=["segment", "h_weeks", "model", "n", "actual",
                                      "pred", "abs_err", "bias", "WAPE", "fill",
                                      "short_units", "short_weeks", "avg_stock", "end_stock"])
        notes = pd.DataFrame([
            ("目的", "97/157 天窗口的周级初筛；当前无共同窗口"),
            ("原因", "周级严格观测下，训练/测试周存在未知周；现有日序列只有成交日，无法形成连续观测周"),
            ("结论", "v4 不能在该数据上跑;需补日级库存/销量观测或退回月度口径"),
        ], columns=["项", "内容"])
        with pd.ExcelWriter(OUT, engine="openpyxl") as w:
            notes.to_excel(w, sheet_name="0_说明", index=False)
            empty.to_excel(w, sheet_name="1_汇总", index=False)
            sample.to_excel(w, sheet_name="2_样本", index=False)
            skip.to_excel(w, sheet_name="4_失败与跳过", index=False)
        return 0
    detail.to_csv(BASE / "forecast_benchmark_20261107_v4_detail.csv", index=False,
                  encoding="utf-8-sig")
    skip.to_csv(BASE / "forecast_benchmark_20261107_v4_skips.csv", index=False,
                encoding="utf-8-sig")
    fsum = (detail.groupby(["segment", "h_weeks", "model"])
            .agg(n=("pred", "size"), actual=("actual", "sum"), pred=("pred", "sum"),
                 abs_err=("abs_err", "sum"), bias=("bias", "sum"),
                 short_units=("short_units", "sum"), short_weeks=("short_weeks", "sum"),
                 avg_stock=("avg_stock", "mean"), end_stock=("end_stock", "mean"))
            .reset_index())
    fsum["WAPE"] = fsum["abs_err"] / fsum["actual"].replace(0, np.nan)
    fsum["fill"] = 1 - fsum["short_units"] / fsum["actual"].replace(0, np.nan)
    fsum = fsum.round(4)
    notes = pd.DataFrame([
        ("目的", "97/157 天窗口的周级初筛 + 固定政策库存模拟；不宣布胜者"),
        ("样本", f"zero {len(zero)} / stable {len(stable)} / short {len(short)}"),
        ("周级原因", "日序列只有成交日（中位 41 天/键），日级补零会伪造观测；按周聚合，只算真实观测周"),
        ("模型", "MA3 / SeasonalNaive(4) / AutoETS(4) / CrostonSBA / TSB(0.2,0.2) / ADIDA"),
        ("窗口", "14 周≈97 天；22 周≈157 天；只汇总 6 模型都成功的同一窗口"),
        ("库存", "固定政策模拟：初始 C 可发、lead=生产+prehaul2+运输、order-up-to；不是历史还原"),
        ("跳过", "逐条见 4_失败与跳过；未知周、模型失败都不进分母"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        notes.to_excel(w, sheet_name="0_说明", index=False)
        fsum.to_excel(w, sheet_name="1_汇总", index=False)
        sample.to_excel(w, sheet_name="2_样本", index=False)
        detail.to_excel(w, sheet_name="3_逐键逐模型", index=False)
        skip.to_excel(w, sheet_name="4_失败与跳过", index=False)
    print(fsum.to_string(index=False))
    if skip.empty:
        print("\nskips: none")
    else:
        print("\nskips:\n", skip["reason"].value_counts().to_string())
    print("\nwrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
