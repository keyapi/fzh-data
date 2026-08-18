from __future__ import annotations

import pandas as pd

from .report import FEEDBACK_VALUES


def validate_feedback(frame: pd.DataFrame, catalog_skus: set[str]) -> pd.DataFrame:
    result = frame.copy()
    confirmed = []
    for index, row in result.iterrows():
        decision = str(row.get("人工结论") or "").strip()
        if not decision:
            confirmed.append("")
            continue
        if decision not in FEEDBACK_VALUES:
            raise ValueError(f"Invalid feedback decision at row {index + 2}: {decision}")
        if decision.startswith("确认Top"):
            sku = str(row.get(f"{decision.removeprefix('确认')} SKU") or "").strip()
        elif decision == "正确SKU另填":
            sku = str(row.get("正确SKU另填") or "").strip()
        else:
            sku = ""
        if sku and sku not in catalog_skus:
            raise ValueError(f"Feedback SKU is outside candidate catalog: {sku}")
        if decision in {"确认Top1", "确认Top2", "确认Top3", "正确SKU另填"} and not sku:
            raise ValueError(f"Feedback decision requires a SKU at row {index + 2}")
        confirmed.append(sku)
    result["confirmed_sku"] = confirmed
    return result
