# -*- coding: utf-8 -*-
"""把分层费率发布结果转成 EN `History Last Leg Fee Record Item` 导入行。

分析层与线上模型之间只通过这个显式契约连接：列名、单位（kg）、层级命名
（L1..L8）与匹配语义都写在这里，避免「分析脚本改了、线上字段没改」的漂移。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .history_last_leg_analysis import ORIGIN_ZIP5

# 线上子表字段（History Last Leg Fee Record Item）
IMPORT_COLUMNS: tuple[str, ...] = (
    "model_key",
    "match_level",
    "nation",
    "tongtool_sku",
    "origin_warehouse",
    "origin_zip",
    "destination_zip3",
    "destination_zip1",
    "destination_zone",
    "carrier",
    "shipping_channel",
    "carrier_service",
    "weight_lower_kg",
    "weight_upper_kg",
    "avg_per_shipping_cost",
    "median_cost",
    "trimmed_mean_cost",
    "p25_cost",
    "p75_cost",
    "sample_count",
    "coverage_months",
    "outlier_count",
    "confidence_level",
    "quality_status",
    "fee_source",
)

# 线上解析器使用的层级名（必须与 tongtool_integration.history_last_leg_fee 完全一致）
LEVEL_NAMES: tuple[str, ...] = (
    "L1_SKU_ZIP3_重量",
    "L1b_SKU_ZIP1_重量",
    "L2_SKU_重量",
    "L3_ZIP3_重量",
    "L3b_ZIP1_重量",
    "L4_ZIP3",
    "L5_重量",
    "L5b_国家重量",
    "L6_仓库渠道",
    "L7_仓库",
    "L8_国家",
)

_TIER_PATTERN = re.compile(r"^\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\]kg$")


def _is_missing(value: Any) -> bool:
    """统一识别 None / NaN / pandas.NA / NaT，避免把 "<NA>" 当成文本写进导入文件。"""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_text(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _as_float(value: Any) -> float:
    if _is_missing(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_weight_tier(tier: Any) -> tuple[float, float]:
    """把 `(4,5]kg` 解析成 (4.0, 5.0)；下界开、上界闭，与线上匹配口径一致。"""
    match = _TIER_PATTERN.match(_as_text(tier))
    if not match:
        return 0.0, 0.0
    return float(match.group(1)), float(match.group(2))


def build_model_key(row: dict[str, Any]) -> str:
    """稳定模型键，与 EN 端重复键校验使用同一组合。"""
    parts = [
        str(row.get("match_level") or "").strip(),
        str(row.get("nation") or "").strip().upper(),
        str(row.get("tongtool_sku") or "").strip().upper(),
        str(row.get("origin_warehouse") or "").strip().upper(),
        str(row.get("destination_zip3") or "").strip().upper(),
        str(row.get("destination_zip1") or "").strip().upper(),
        str(row.get("carrier") or "").strip().upper(),
        str(row.get("shipping_channel") or "").strip().upper(),
        str(row.get("carrier_service") or "").strip().upper(),
        "{0:.3f}".format(float(row.get("weight_lower_kg") or 0)),
        "{0:.3f}".format(float(row.get("weight_upper_kg") or 0)),
    ]
    return "|".join(parts)


@dataclass(frozen=True)
class ExportContract:
    """发布契约：模型标识、适用期、回测指标，一并写进 parent。"""

    model_version: str
    data_source: str
    generated_at: str
    applicable_from: str = ""
    applicable_to: str = ""
    priority: int = 10
    backtest_mae: float = 0.0
    backtest_mdae: float = 0.0
    backtest_bias: float = 0.0
    backtest_p90: float = 0.0
    backtest_coverage_percent: float = 0.0

    def as_parent_fields(self) -> dict[str, Any]:
        return {
            "model_status": "Draft",
            "model_version": self.model_version,
            "data_source": self.data_source,
            "generated_at": self.generated_at,
            "applicable_from": self.applicable_from or None,
            "applicable_to": self.applicable_to or None,
            "priority": self.priority,
            "weight_unit": "kg",
            "backtest_mae": self.backtest_mae,
            "backtest_mdae": self.backtest_mdae,
            "backtest_bias": self.backtest_bias,
            "backtest_p90": self.backtest_p90,
            "backtest_coverage_percent": self.backtest_coverage_percent,
        }


def build_import_rows(publishable: pd.DataFrame, *, fee_column: str = "中位数") -> pd.DataFrame:
    """把可发布费率层转成线上子表行；样本不足的层不在此处出现（已由分析层合并）。

    线上报价字段 `avg_per_shipping_cost` 取稳健估计（默认去异常中位数），
    其余分位数与样本量一并带出，便于日后复核证据。
    """
    columns = list(IMPORT_COLUMNS)
    if publishable is None or len(publishable) == 0:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for _, source in publishable.iterrows():
        lower, upper = parse_weight_tier(source.get("观察重量阶梯"))
        warehouse = _as_text(source.get("标准仓库"))
        estimate = source.get(fee_column)
        if estimate is None or pd.isna(estimate):
            estimate = source.get("中位数")
        row = {
            "match_level": _as_text(source.get("匹配层级")),
            "nation": _as_text(source.get("国家")).upper(),
            "tongtool_sku": _as_text(source.get("通途SKU")),
            "origin_warehouse": warehouse,
            "origin_zip": ORIGIN_ZIP5.get(warehouse, ""),
            "destination_zip3": _as_text(source.get("美国ZIP3")),
            "destination_zip1": _as_text(source.get("目的地邮编首位")),
            "destination_zone": "",
            "carrier": "",
            "shipping_channel": _as_text(source.get("标准渠道")),
            "carrier_service": "",
            "weight_lower_kg": round(lower, 3),
            "weight_upper_kg": round(upper, 3),
            "avg_per_shipping_cost": round(_as_float(estimate), 4),
            "median_cost": round(_as_float(source.get("中位数")), 4),
            "trimmed_mean_cost": round(_as_float(source.get("截尾均值", source.get("平均值"))), 4),
            "p25_cost": round(_as_float(source.get("P25")), 4),
            "p75_cost": round(_as_float(source.get("P75")), 4),
            "sample_count": int(_as_float(source.get("样本数"))),
            "coverage_months": int(_as_float(source.get("覆盖月份数"))),
            "outlier_count": int(_as_float(source.get("异常数"))),
            "confidence_level": _as_text(source.get("置信等级")),
            "quality_status": "Eligible",
            "fee_source": _as_text(source.get("费用来源")),
        }
        row["model_key"] = build_model_key(row)
        rows.append(row)

    frame = pd.DataFrame(rows, columns=columns)
    unknown = sorted(set(frame["match_level"]) - set(LEVEL_NAMES))
    if unknown:
        raise ValueError(
            "出现线上解析器不认识的匹配层级，导入前必须对齐契约: " + ", ".join(unknown)
        )
    duplicates = frame["model_key"].duplicated(keep=False)
    if duplicates.any():
        raise ValueError(
            "发布层存在重复模型键，导入前必须先合并: "
            + ", ".join(sorted(set(frame.loc[duplicates, "model_key"]))[:5])
        )
    return frame


def write_import_rows(rows: pd.DataFrame, path: Path | str) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(out_path, index=False)
    return out_path
