"""Minimal, explainable forecast entry used when a full D5 run is not available.

This is deliberately labelled ``lite``: it is not D5 q95 and must not be
reported as the production forecast. It exists so an external agent can compute
a transparent baseline from history when the private pack lacks a D5 run.
"""
from __future__ import annotations
import math
import pandas as pd


def forecast_entry(history, horizon: int = 97, method: str = "ma3"):
    series = pd.to_numeric(pd.Series(history), errors="coerce").dropna()
    if series.empty:
        return {"method": method, "horizon": horizon, "p50": None, "note": "no history"}
    if method == "naive":
        rate = float(series.iloc[-1])
    elif method == "seasonal_naive" and len(series) >= 12:
        rate = float(series.iloc[-12])
    else:
        rate = float(series.tail(3).mean())
    p50 = max(0.0, rate * horizon)
    return {"method": method, "horizon": horizon, "p50": p50,
            "note": "lite baseline, not D5 q95"}
