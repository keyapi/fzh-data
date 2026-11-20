# -*- coding: utf-8 -*-
"""写回表列合同：只校验关键列与重复列，未知新列原样透传。"""
from __future__ import annotations

from typing import Iterable

# 写回表关键列（来自 166 列/78 列合同；按名称匹配，不依赖位置）
KEY_COLUMNS_ORDER: tuple[str, ...] = (
    "订单号",
    "平台SKU",
    "通途SKU",
    "品类尺寸面料编码",
    "发货仓库",
    "发货仓按销售汇总分类",
    "发货数量",
    "售价",
    "售价*汇率",
    "运费",
    "当月给分公司发货类型",
    "是否皮壳",
    "皮壳成本",
    "头程运费金额",
    "二次加工成本",
    "绍兴二次加工成本",
    "头程运费来源编码",
    "二次加工成本来源编码",
)

# 成本四列（顺序固定）
COST_COLUMNS: tuple[str, ...] = (
    "皮壳成本",
    "头程运费金额",
    "二次加工成本",
    "绍兴二次加工成本",
)


class ContractError(ValueError):
    """列合同不满足。"""


def validate_header(columns: Iterable[str], *, required: Iterable[str] = KEY_COLUMNS_ORDER) -> None:
    """校验列头：无重复、包含全部关键列。未知列允许存在（透传）。"""
    cols = [str(c).strip() for c in columns]
    if not cols:
        raise ContractError("列头为空")
    dup = sorted({c for c in cols if cols.count(c) > 1})
    if dup:
        raise ContractError(f"重复列: {dup}")
    missing = [c for c in required if c not in cols]
    if missing:
        raise ContractError(f"缺少关键列: {missing}")


def ensure_cost_columns(columns: Iterable[str]) -> None:
    validate_header(columns, required=COST_COLUMNS)
