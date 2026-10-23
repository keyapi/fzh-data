#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
E3 最小只读 Agent 原型（无外部 LLM）

设计要点
--------
1. 语义层先行：指标注册表定义口径、权威来源、禁用口径。
2. 工具注册表：8 个只读工具，每个声明必填/可选参数；所有数值由工具实现计算，
   路由只负责「选工具 + 填槽位」，不产出最终数字。
3. 流程：prepare -> confirm -> execute -> readback。execute 仅只读；
   写意图在 prepare 之前被策略拒绝，并给出安全替代。
4. 歧义：仓库 / 时段 / SKU 多候选等缺失时返回 needs_clarification，不猜。
5. 证据：每个作答都带 tool / params / data_source / authority / values / readback。

运行
----
    uv run python <this_file> --eval
    uv run python <this_file> --ask "2878 在美中 Daneey 仓 2026 年 5 月的销量是多少？"
    uv run python <this_file> --ask "..." --yes   # 跳过人工确认（仅因工具只读）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "wedge_decision_package.json"
QUESTIONS_FILE = BASE_DIR / "questions.json"
RESULTS_FILE = BASE_DIR / "results.json"

D = Decimal


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

class ToolError(Exception):
    """工具层可预期的失败（无数据 / 参数越界）。"""


def q1(value: Any) -> Decimal:
    return D(str(value)).quantize(D("0.1"), rounding=ROUND_HALF_UP)


def q2(value: Any) -> Decimal:
    return D(str(value)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_data(path: Path = DATA_FILE) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def canonical(obj: Any) -> str:
    return json.dumps(jsonable(obj), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 语义层：指标注册表
# ---------------------------------------------------------------------------

SEMANTIC_LAYER: dict[str, dict] = {
    "monthly_sales": {
        "label": "月销量",
        "definition": "指定仓库、渠道、月份区间内，通途『发货数量』求和；按自然月拆分。",
        "unit": "件",
        "authority": "通途订单 Google Sheet（通途订单YYYYMM）",
        "caliber": "通途发货口径",
        "forbidden": [
            "不能用 EN 销售订单数量替代发货量",
            "不能把 SO 未交量算作已发货",
        ],
        "caveats": ["10 月订单表缺失，销量仅覆盖 2026-03 至 2026-09", "波兰仓已排除"],
    },
    "clean_monthly_demand": {
        "label": "干净月需求率",
        "definition": "剔除断货影响月与到货冲量月后，计入月份发货量之和 / 计入月份数；保留 1 位小数（HALF_UP）。",
        "unit": "件/月",
        "authority": "通途订单 + 断货窗口三方交叉（Notion / 客户邮件 / check0stock 差分）",
        "caliber": "剔除断货后的月均发货",
        "forbidden": ["断货月与到货冲量月的出货不能代表真实需求", "不能直接用含断货月的总销量平均"],
        "caveats": ["断货窗口两套差分结论不一致时，以更严且有实证的一套为准"],
    },
    "stockout_windows": {
        "label": "断货窗口",
        "definition": "SKU 级断货事件：开始日期 → 到货/恢复发货日期。",
        "unit": "日期区间",
        "authority": "Notion 任务页 + 客户邮件 + check0stock 差分，三方交叉",
        "caliber": "实证断货事件",
        "forbidden": ["不能仅凭某一套缺货 sheet 把整个家族标为缺货"],
        "caveats": ["断货窗口是 SKU 级事件，不按仓库拆分"],
    },
    "inventory": {
        "label": "可用库存",
        "definition": "通途分仓『可用库存』。报溢前可用 0 是常态，但仍是唯一可用口径。",
        "unit": "件",
        "authority": "通途 ERP2 API erp2_stocks_stocksquery（逐仓）",
        "caliber": "通途分仓可用",
        "forbidden": [
            "EN Bin 数量不能当可用库存：EN 不扣减通途库存，实测差异 351 件",
            "SO 未交量不能当在途或可用",
        ],
        "caveats": ["通途为标记发货可能先报溢，可用 0 不等于业务上完全无货"],
    },
    "in_transit": {
        "label": "在途",
        "definition": "通途采购单中未到货数量之和。",
        "unit": "件",
        "authority": "通途采购单",
        "caliber": "采购单未到货",
        "forbidden": ["SO 未交量不是在途：货已出境，属目的仓账面预留"],
        "caveats": ["未填到货日的采购单仍计入在途"],
    },
    "coverage_months": {
        "label": "覆盖月数",
        "definition": "(通途可用 + 通途在途) / 月需求率。",
        "unit": "月",
        "authority": "库存 + 在途 + 干净月需求率",
        "caliber": "可售库存覆盖",
        "forbidden": ["不能用 EN Bin 或 SO 未交量计算覆盖"],
        "caveats": ["覆盖月数为估算，不含在途到货时点不确定性"],
    },
    "recommend_order": {
        "label": "建议补货量",
        "definition": "ceil(max(0, 月需求率 × 覆盖月数 − 通途可用 − 通途在途))。",
        "unit": "件",
        "authority": "干净月需求率 + 通途可用 + 通途在途",
        "caliber": "覆盖期缺口向上取整",
        "forbidden": ["不能让模型直接口算最终数量；必须由工具实现计算"],
        "caveats": ["建议量为参考值，采购需人工确认，尤其是高于历史单笔量级时"],
    },
}


# ---------------------------------------------------------------------------
# 数据读取辅助
# ---------------------------------------------------------------------------

def sku_record(data: dict, sku: str) -> dict:
    rec = data["skus"].get(sku)
    if rec is None:
        raise ToolError(f"未知 SKU：{sku}")
    return rec


def covered_warehouses(data: dict) -> list[str]:
    return [w for w, meta in data["warehouses"].items() if meta.get("covered") and w != "ALL"]


def resolve_warehouses(data: dict, warehouse: str) -> list[str]:
    if warehouse == "ALL":
        return covered_warehouses(data)
    meta = data["warehouses"].get(warehouse)
    if meta is None:
        raise ToolError(f"未知仓库：{warehouse}")
    if not meta.get("covered"):
        raise ToolError(f"仓库 {meta.get('label', warehouse)} 不在本数据集覆盖范围；仅覆盖美中-Daneey 仓。")
    return [warehouse]


def month_list(start: str, end: str) -> list[str]:
    try:
        y1, m1 = (int(x) for x in start.split("-"))
        y2, m2 = (int(x) for x in end.split("-"))
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"月份格式应为 YYYY-MM：{start} / {end}") from exc
    if not (1 <= m1 <= 12 and 1 <= m2 <= 12):
        raise ToolError(f"月份越界：{start} / {end}")
    if (y1, m1) > (y2, m2):
        raise ToolError(f"起始月份晚于结束月份：{start} > {end}")
    out: list[str] = []
    while (y1, m1) <= (y2, m2):
        out.append(f"{y1:04d}-{m1:02d}")
        m1 += 1
        if m1 == 13:
            m1 = 1
            y1 += 1
    return out


def demand_rate(rec: dict, rate_source: str) -> Decimal:
    if rate_source == "clean":
        return D(str(rec["clean_demand"]["rate"]))
    if rate_source == "raw":
        series = rec["monthly_sales"]
        total = sum(v["total"] for v in series.values())
        return q1(D(total) / D(len(series)))
    raise ToolError(f"未知 rate_source：{rate_source}")


def inventory_qty(data: dict, sku: str, warehouse: str) -> tuple[int, list[str]]:
    rec = sku_record(data, sku)
    warehouses = resolve_warehouses(data, warehouse)
    # 当前数据集库存只在美中-Daneey 有分仓明细；ALL 时明确告警。
    available = int(rec["inventory"]["available"]) if warehouses else 0
    return available, warehouses


def transit_qty(data: dict, sku: str, warehouse: str) -> tuple[int, list[str], list[dict]]:
    rec = sku_record(data, sku)
    warehouses = resolve_warehouses(data, warehouse)
    total = int(rec["inventory"]["in_transit"]) if warehouses else 0
    return total, warehouses, list(rec["inventory"].get("purchase_orders", []))


# ---------------------------------------------------------------------------
# 只读工具实现
# ---------------------------------------------------------------------------

def impl_monthly_sales(params: dict, data: dict) -> dict:
    sku = params["sku"]
    warehouse = params["warehouse"]
    channel = params.get("channel", "all")
    months = month_list(params["start"], params["end"])
    resolve_warehouses(data, warehouse)
    rec = sku_record(data, sku)
    series = rec["monthly_sales"]
    missing = [m for m in months if m not in series]
    if missing:
        raise ToolError(f"数据未覆盖月份：{', '.join(missing)}；销量仅覆盖 2026-03 至 2026-09。")
    if channel not in ("all", "channel_a", "other"):
        raise ToolError(f"未知渠道：{channel}")

    rows = []
    qty = 0
    for m in months:
        total = int(series[m]["total"])
        channel_a = int(series[m]["channel_a"])
        other = total - channel_a
        picked = {"all": total, "channel_a": channel_a, "other": other}[channel]
        qty += picked
        rows.append({"month": m, "total": total, "channel_a": channel_a, "other": other, "picked": picked})
    return {
        "values": {
            "qty": qty,
            "months": months,
            "channel": channel,
            "rows": rows,
        },
        "computation": [
            f"月份区间：{months[0]} ~ {months[-1]}（{len(months)} 个月）",
            f"渠道口径：{channel}",
            "逐月求和：" + " + ".join(str(r["picked"]) for r in rows) + f" = {qty} 件",
        ],
    }


def impl_stockout_windows(params: dict, data: dict) -> dict:
    sku = params["sku"]
    rec = sku_record(data, sku)
    windows = rec.get("stockout_windows", [])
    values: dict[str, Any] = {
        "has_stockout": bool(windows),
        "window_count": len(windows),
        "windows": windows,
    }
    if windows:
        values["stockout_start"] = windows[0]["start"]
        values["stockout_end"] = windows[0]["end"]
    else:
        values["stockout_start"] = None
        values["stockout_end"] = None
    return {
        "values": values,
        "computation": ["断货窗口为 SKU 级事件，来自 Notion / 客户邮件 / check0stock 三方交叉。"],
    }


def impl_inventory(params: dict, data: dict) -> dict:
    sku = params["sku"]
    warehouse = params["warehouse"]
    available, whs = inventory_qty(data, sku, warehouse)
    values: dict[str, Any] = {
        "available": available,
        "warehouse": warehouse,
        "warehouses": whs,
    }
    if warehouse == "ALL":
        values["coverage_warning"] = "本数据集仅美中-Daneey 有库存明细；ALL 实际等同该仓。"
    return {
        "values": values,
        "computation": [
            "取通途分仓可用库存；EN Bin 与 SO 未交量均不采用。",
            f"可用库存 = {available} 件。",
        ],
    }


def impl_in_transit(params: dict, data: dict) -> dict:
    sku = params["sku"]
    warehouse = params["warehouse"]
    total, whs, pos = transit_qty(data, sku, warehouse)
    values: dict[str, Any] = {
        "in_transit": total,
        "warehouse": warehouse,
        "warehouses": whs,
        "po": pos[0]["po"] if pos else None,
        "purchase_orders": pos,
    }
    return {
        "values": values,
        "computation": [
            "在途 = 通途采购单未到货数量之和；SO 未交量不计入。",
            f"在途 = {total} 件。",
        ],
    }


def impl_coverage_months(params: dict, data: dict) -> dict:
    sku = params["sku"]
    warehouse = params["warehouse"]
    rate_source = params.get("rate_source", "clean")
    rec = sku_record(data, sku)
    rate = demand_rate(rec, rate_source)
    if rate <= 0:
        raise ToolError("月需求率为 0，无法计算覆盖月数。")
    available, whs = inventory_qty(data, sku, warehouse)
    transit, _, _ = transit_qty(data, sku, warehouse)
    coverage = q2((D(available) + D(transit)) / rate)
    return {
        "values": {
            "coverage_months": coverage,
            "rate": rate,
            "rate_source": rate_source,
            "available": available,
            "in_transit": transit,
            "warehouse": warehouse,
            "warehouses": whs,
        },
        "computation": [
            f"月需求率（{rate_source}）= {rate} 件/月",
            f"可用 + 在途 = {available} + {transit} = {available + transit} 件",
            f"覆盖 = {available + transit} / {rate} = {coverage} 个月",
        ],
    }


def impl_recommend_order(params: dict, data: dict) -> dict:
    sku = params["sku"]
    warehouse = params["warehouse"]
    coverage_months = int(params.get("coverage_months", 6))
    rate_source = params.get("rate_source", "clean")
    if coverage_months <= 0 or coverage_months > 60:
        raise ToolError(f"覆盖月数不合理：{coverage_months}")
    rec = sku_record(data, sku)
    rate = demand_rate(rec, rate_source)
    available, whs = inventory_qty(data, sku, warehouse)
    transit, _, pos = transit_qty(data, sku, warehouse)
    target = rate * D(coverage_months)
    shortfall = target - D(available) - D(transit)
    recommended = max(0, int(shortfall.to_integral_value(rounding=ROUND_CEILING)))
    surplus = 0
    if recommended == 0 and shortfall < 0:
        surplus = int((-shortfall).to_integral_value(rounding=ROUND_FLOOR))
    return {
        "values": {
            "recommended_qty": recommended,
            "target_qty": target,
            "shortfall": shortfall,
            "surplus": surplus,
            "rate": rate,
            "rate_source": rate_source,
            "coverage_months": coverage_months,
            "available": available,
            "in_transit": transit,
            "warehouse": warehouse,
            "warehouses": whs,
            "po": pos[0]["po"] if pos else None,
        },
        "computation": [
            f"目标 = 月需求率 {rate} × 覆盖 {coverage_months} 个月 = {target} 件",
            f"扣减：可用 {available} + 在途 {transit}",
            f"缺口 = {shortfall}；向上取整且不低于 0 → {recommended} 件",
        ],
    }


def impl_explain_recommendation(params: dict, data: dict) -> dict:
    sku = params["sku"]
    rec = sku_record(data, sku)
    coverage_months = int(params.get("coverage_months", 6))
    base = impl_recommend_order({**params, "coverage_months": coverage_months}, data)
    clean = rec["clean_demand"]
    windows = rec.get("stockout_windows", [])
    excluded = clean["excluded_months"]
    included = clean["included_months"]

    if windows:
        w = windows[0]
        stockout_text = f"断货窗口 {w['start']} → {w['end']}；该窗口及到货后冲量月不计入真实需求。"
    else:
        stockout_text = "无断货窗口，全部月份计入。"

    steps = [
        f"1) 需求率：计入 {len(included)} 个干净月（{', '.join(included)}）共 {clean['shipped']} 件"
        f" ÷ {len(included)} = {base['values']['rate']} 件/月；剔除月份：{', '.join(excluded) if excluded else '无'}。",
        f"2) 覆盖目标：{base['values']['rate']} × {coverage_months} 个月 = {base['values']['target_qty']} 件。",
        f"3) 扣减：通途可用 {base['values']['available']} 件 + 在途 {base['values']['in_transit']} 件。",
        f"4) 建议下单：缺口 {base['values']['shortfall']} 件，向上取整且不低于 0 → {base['values']['recommended_qty']} 件。",
        f"5) 断货依据：{stockout_text}",
    ]
    values = dict(base["values"])
    values.update({
        "excluded_months": excluded,
        "included_months": included,
        "clean_shipped": clean["shipped"],
        "stockout_windows": windows,
        "steps": steps,
    })
    return {
        "values": values,
        "computation": steps,
    }


def impl_compare_skus(params: dict, data: dict) -> dict:
    skus: list[str] = list(params["skus"])
    metric: str = params["metric"]
    warehouse: str = params["warehouse"]
    if metric not in (
        "clean_monthly_demand",
        "monthly_sales",
        "inventory",
        "in_transit",
        "coverage_months",
        "recommend_order",
    ):
        raise ToolError(f"compare_skus 不支持的指标：{metric}")

    rows = []
    values: dict[str, Any] = {"metric": metric, "warehouse": warehouse}
    for sku in skus:
        rec = sku_record(data, sku)
        if metric == "clean_monthly_demand":
            val = demand_rate(rec, "clean")
            detail = "干净月需求率"
        elif metric == "monthly_sales":
            start = params.get("start")
            end = params.get("end")
            if not start or not end:
                raise ToolError("monthly_sales 比较需要 start / end。")
            months = month_list(start, end)
            series = rec["monthly_sales"]
            missing = [m for m in months if m not in series]
            if missing:
                raise ToolError(f"数据未覆盖月份：{', '.join(missing)}")
            channel = params.get("channel", "all")
            val = 0
            for m in months:
                total = int(series[m]["total"])
                channel_a = int(series[m]["channel_a"])
                val += {"all": total, "channel_a": channel_a, "other": total - channel_a}[channel]
            detail = "区间销量"
        elif metric == "inventory":
            val = inventory_qty(data, sku, warehouse)[0]
            detail = "通途可用库存"
        elif metric == "in_transit":
            val = transit_qty(data, sku, warehouse)[0]
            detail = "通途在途"
        elif metric == "coverage_months":
            val = impl_coverage_months({"sku": sku, "warehouse": warehouse, "rate_source": "clean"}, data)["values"]["coverage_months"]
            detail = "覆盖月数"
        else:  # recommend_order
            val = impl_recommend_order({"sku": sku, "warehouse": warehouse, "coverage_months": 6}, data)["values"]["recommended_qty"]
            detail = "6 个月建议补货量"
        rows.append({"sku": sku, "value": val, "detail": detail})
        values[sku] = val

    numeric = [(r["sku"], r["value"]) for r in rows]
    if metric == "clean_monthly_demand":
        numeric = [(s, D(str(v))) for s, v in numeric]
    if numeric:
        max_sku = max(numeric, key=lambda x: x[1])[0]
        min_sku = min(numeric, key=lambda x: x[1])[0]
        values["max_sku"] = max_sku
        values["min_sku"] = min_sku
    values["rows"] = rows
    return {
        "values": values,
        "computation": [f"指标：{metric}；仓库：{warehouse}；逐 SKU 调用同一指标实现后比较。"] + [
            f"{r['sku']}：{r['value']}（{r['detail']}）" for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    name: str
    metric: str
    label: str
    required: tuple[str, ...]
    optional: tuple[str, ...]
    defaults: dict[str, Any]
    read_only: bool
    impl: Callable[[dict, dict], dict]
    data_source: str
    authority: str
    definition: str


TOOLS: dict[str, ToolSpec] = {
    "monthly_sales": ToolSpec(
        name="monthly_sales",
        metric="monthly_sales",
        label="按月销量查询",
        required=("sku", "warehouse", "start", "end"),
        optional=("channel",),
        defaults={"channel": "all"},
        read_only=True,
        impl=impl_monthly_sales,
        data_source="通途订单 Google Sheet（通途订单202603–202609）",
        authority=SEMANTIC_LAYER["monthly_sales"]["authority"],
        definition=SEMANTIC_LAYER["monthly_sales"]["definition"],
    ),
    "stockout_windows": ToolSpec(
        name="stockout_windows",
        metric="stockout_windows",
        label="断货窗口查询",
        required=("sku",),
        optional=(),
        defaults={},
        read_only=True,
        impl=impl_stockout_windows,
        data_source="Notion 任务页 + 客户邮件（匿名） + check0stock 差分",
        authority=SEMANTIC_LAYER["stockout_windows"]["authority"],
        definition=SEMANTIC_LAYER["stockout_windows"]["definition"],
    ),
    "inventory": ToolSpec(
        name="inventory",
        metric="inventory",
        label="通途分仓可用库存",
        required=("sku", "warehouse"),
        optional=(),
        defaults={},
        read_only=True,
        impl=impl_inventory,
        data_source="通途 ERP2 API erp2_stocks_stocksquery（逐仓）",
        authority=SEMANTIC_LAYER["inventory"]["authority"],
        definition=SEMANTIC_LAYER["inventory"]["definition"],
    ),
    "in_transit": ToolSpec(
        name="in_transit",
        metric="in_transit",
        label="通途采购单在途",
        required=("sku", "warehouse"),
        optional=(),
        defaults={},
        read_only=True,
        impl=impl_in_transit,
        data_source="通途采购单（未到货数量）",
        authority=SEMANTIC_LAYER["in_transit"]["authority"],
        definition=SEMANTIC_LAYER["in_transit"]["definition"],
    ),
    "coverage_months": ToolSpec(
        name="coverage_months",
        metric="coverage_months",
        label="库存覆盖月数",
        required=("sku", "warehouse"),
        optional=("rate_source",),
        defaults={"rate_source": "clean"},
        read_only=True,
        impl=impl_coverage_months,
        data_source="通途可用库存 + 通途采购单在途 + 干净月需求率",
        authority=SEMANTIC_LAYER["coverage_months"]["authority"],
        definition=SEMANTIC_LAYER["coverage_months"]["definition"],
    ),
    "recommend_order": ToolSpec(
        name="recommend_order",
        metric="recommend_order",
        label="建议补货量",
        required=("sku", "warehouse"),
        optional=("coverage_months", "rate_source"),
        defaults={"coverage_months": 6, "rate_source": "clean"},
        read_only=True,
        impl=impl_recommend_order,
        data_source="干净月需求率 + 通途可用库存 + 通途采购单在途",
        authority=SEMANTIC_LAYER["recommend_order"]["authority"],
        definition=SEMANTIC_LAYER["recommend_order"]["definition"],
    ),
    "explain_recommendation": ToolSpec(
        name="explain_recommendation",
        metric="recommend_order",
        label="补货建议解释",
        required=("sku", "warehouse"),
        optional=("coverage_months", "rate_source"),
        defaults={"coverage_months": 6, "rate_source": "clean"},
        read_only=True,
        impl=impl_explain_recommendation,
        data_source="干净月需求率 + 断货窗口 + 通途可用库存 + 通途采购单在途",
        authority="综合月度销量 / 断货窗口 / 库存 / 在途四个权威来源",
        definition="逐步展开 建议补货量 的计算链，并标注断货剔除依据。",
    ),
    "compare_skus": ToolSpec(
        name="compare_skus",
        metric="compare",
        label="跨 SKU 指标比较",
        required=("skus", "metric", "warehouse"),
        optional=("start", "end", "channel"),
        defaults={"channel": "all"},
        read_only=True,
        impl=impl_compare_skus,
        data_source="按所选指标复用同一语义层来源",
        authority="复用对应指标权威来源",
        definition="对 2 个及以上 SKU 调用同一指标实现并比较，禁止跨口径比较。",
    ),
}


# ---------------------------------------------------------------------------
# 确定性路由：规则 + 槽位抽取
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteRule:
    rule_id: str
    kind: str
    pattern: re.Pattern
    tool: str | None
    description: str


RULES: tuple[RouteRule, ...] = (
    RouteRule(
        "R01_premise_conflict",
        "premise_conflict",
        re.compile(r"(?:EN|ERPNext|Bin).{0,10}(?:Bin|库存)|(?:用|按)\s*EN", re.I),
        None,
        "检测到 EN Bin / EN 库存等被禁用口径",
    ),
    RouteRule(
        "R02_write_intent",
        "write_intent",
        re.compile(
            r"帮我.{0,12}(?:下单|下\s*\d+\s*件|订\s*\d+|采购\s*\d*)"
            r"|下\s*\d+\s*件|下单|提交|创建.{0,6}(?:采购单|订单)|修改|删除|改成|写入",
            re.I,
        ),
        None,
        "检测到写操作意图",
    ),
    RouteRule(
        "R03_out_of_scope",
        "out_of_scope",
        re.compile(r"预测|明年|后年|未来|全公司|公司整体|销售额|营收|收入|利润|毛利|市场份额"),
        None,
        "未注册指标或超出数据范围",
    ),
    RouteRule(
        "R04_explain",
        "tool",
        re.compile(r"解释|为什么|原因|依据|怎么算|如何得出"),
        "explain_recommendation",
        "解释补货建议的计算链",
    ),
    RouteRule(
        "R05_stockout",
        "tool",
        re.compile(r"断货|缺货|断供|out\s*of\s*stock", re.I),
        "stockout_windows",
        "断货窗口",
    ),
    RouteRule(
        "R06_in_transit",
        "tool",
        re.compile(r"在途|采购单|PO\d*|未到货", re.I),
        "in_transit",
        "通途采购单在途",
    ),
    RouteRule(
        "R07_compare",
        "tool",
        re.compile(r"比较|对比|哪个.{0,6}(?:高|低|多|少|大|小)|排名|最缺|哪些.{0,6}(?:补|缺)"),
        "compare_skus",
        "跨 SKU 比较",
    ),
    RouteRule(
        "R08_recommend",
        "tool",
        re.compile(r"建议.{0,8}(?:补|下|订)|补多少|补货量|应该补|该补|要补"),
        "recommend_order",
        "建议补货量",
    ),
    RouteRule(
        "R09_coverage",
        "tool",
        re.compile(r"覆盖|够卖|能撑|够用.{0,4}月|可用.{0,4}月"),
        "coverage_months",
        "覆盖月数",
    ),
    RouteRule(
        "R10_inventory",
        "tool",
        re.compile(r"库存|可用|仓里有|剩多少|还有多少"),
        "inventory",
        "通途分仓库存",
    ),
    RouteRule(
        "R11_sales",
        "tool",
        re.compile(r"销量|卖了多少|卖了|销售|发货量|卖得"),
        "monthly_sales",
        "月销量",
    ),
)

SKU_STANDALONE = re.compile(r"(?<!\d)(28(?:7\d|8[01]))(?!\d)")
SKU_FULL_TT = re.compile(r"TT0*03101K0*0628(7\d|8[01])", re.I)
EN_ITEM = re.compile(r"KS0121-KQC-(\d{3})-(WHITE|GREY)", re.I)
DATE_RANGE = re.compile(
    r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月?\s*[–—\-~～至到]\s*(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月"
)
DATE_SINGLE = re.compile(r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月")
COVERAGE_SLOT = re.compile(r"覆盖(?:期)?\s*([0-9]{1,2})\s*个?\s*月")
CHANNEL_A = re.compile(r"零售客户|渠道\s*A|渠道A", re.I)
CHANNEL_OTHER = re.compile(r"其他渠道|非零售客户|非渠道A", re.I)
WAREHOUSE_DANEEY = re.compile(r"美中|daneey|FZH-DANEEY", re.I)
WAREHOUSE_POLAND = re.compile(r"波兰|poland|FZHPoland", re.I)
WAREHOUSE_ALL = re.compile(r"全部仓|所有仓|全仓")

METRIC_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"月需求率|需求率|干净月|月均"), "clean_monthly_demand"),
    (re.compile(r"在途|采购单"), "in_transit"),
    (re.compile(r"库存|可用"), "inventory"),
    (re.compile(r"覆盖|够卖"), "coverage_months"),
    (re.compile(r"建议补|补货|补多少"), "recommend_order"),
    (re.compile(r"销量|卖了多少|发货"), "monthly_sales"),
)

MONTH_NAMES = {m: f"2026-{m:02d}" for m in range(1, 13)}


@dataclass
class Slots:
    skus: list[str] = field(default_factory=list)
    warehouse: str | None = None
    channel: str | None = None
    start: str | None = None
    end: str | None = None
    coverage_months: int | None = None
    rate_source: str | None = None
    metric: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def extract_skus(text: str, data: dict) -> tuple[list[str], list[str]]:
    found: list[str] = []
    tokens: list[str] = []

    for m in SKU_FULL_TT.finditer(text):
        sku = "28" + m.group(1)
        if sku in data["skus"] and sku not in found:
            found.append(sku)
            tokens.append(m.group(0))

    for m in SKU_STANDALONE.finditer(text):
        sku = m.group(1)
        if sku in data["skus"] and sku not in found:
            found.append(sku)
            tokens.append(m.group(0))

    for m in EN_ITEM.finditer(text):
        en_item = f"KS0121-KQC-{m.group(1)}-{m.group(2).upper()}"
        for sku, rec in data["skus"].items():
            if rec["en_item"].upper() == en_item and sku not in found:
                found.append(sku)
                tokens.append(m.group(0))

    for sku, rec in data["skus"].items():
        buyer = str(rec.get("buyer_sku", ""))
        if buyer and re.search(rf"(?<!\d){re.escape(buyer)}(?!\d)", text) and sku not in found:
            found.append(sku)
            tokens.append(buyer)

    return found, tokens


def extract_period(text: str) -> tuple[str | None, str | None, str | None]:
    m = DATE_RANGE.search(text)
    if m:
        y1 = int(m.group(1) or 2026)
        mo1 = int(m.group(2))
        y2 = int(m.group(3) or y1)
        mo2 = int(m.group(4))
        if 1 <= mo1 <= 12 and 1 <= mo2 <= 12:
            return f"{y1:04d}-{mo1:02d}", f"{y2:04d}-{mo2:02d}", m.group(0)
        return None, None, m.group(0)
    m = DATE_SINGLE.search(text)
    if m:
        y = int(m.group(1) or 2026)
        mo = int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}", f"{y:04d}-{mo:02d}", m.group(0)
        return None, None, m.group(0)
    return None, None, None


def extract_slots(text: str, data: dict) -> Slots:
    slots = Slots()
    skus, sku_slots = extract_skus(text, data)
    slots.skus = skus

    if WAREHOUSE_DANEEY.search(text):
        slots.warehouse = "美中-FZH-DANEEY"
        warehouse_slot = WAREHOUSE_DANEEY.search(text).group(0)
    elif WAREHOUSE_POLAND.search(text):
        slots.warehouse = "FZHPoland"
        warehouse_slot = WAREHOUSE_POLAND.search(text).group(0)
    elif WAREHOUSE_ALL.search(text):
        slots.warehouse = "ALL"
        warehouse_slot = WAREHOUSE_ALL.search(text).group(0)
    else:
        warehouse_slot = None

    if CHANNEL_A.search(text):
        slots.channel = "channel_a"
        channel_slot = CHANNEL_A.search(text).group(0)
    elif CHANNEL_OTHER.search(text):
        slots.channel = "other"
        channel_slot = CHANNEL_OTHER.search(text).group(0)
    else:
        channel_slot = None

    slots.start, slots.end, period_slot = extract_period(text)

    m = COVERAGE_SLOT.search(text)
    if m:
        slots.coverage_months = int(m.group(1))
        coverage_slot = m.group(0)
    else:
        coverage_slot = None

    if re.search(r"干净|剔除断货|clean", text, re.I):
        slots.rate_source = "clean"
    elif re.search(r"原始|全部月|不剔除|raw", text, re.I):
        slots.rate_source = "raw"

    for pattern, metric in METRIC_PATTERNS:
        if pattern.search(text):
            slots.metric = metric
            break

    slots.evidence = {
        "sku_slots": sku_slots,
        "warehouse_slot": warehouse_slot,
        "channel_slot": channel_slot,
        "period_slot": period_slot,
        "coverage_slot": coverage_slot,
        "metric": slots.metric,
    }
    return slots


# ---------------------------------------------------------------------------
# 路由与槽位校验
# ---------------------------------------------------------------------------

@dataclass
class Route:
    kind: str
    tool: str | None
    slots: Slots
    params: dict[str, Any]
    missing: list[str]
    matched: list[dict]
    selected_rule: str | None
    confidence: float
    reason: str | None = None


def build_params(tool: str, slots: Slots) -> dict[str, Any]:
    spec = TOOLS[tool]
    params: dict[str, Any] = {}
    for name in (*spec.required, *spec.optional):
        if name == "sku":
            params["sku"] = slots.skus[0] if slots.skus else None
        elif name == "skus":
            params["skus"] = list(slots.skus)
        elif name == "warehouse":
            params["warehouse"] = slots.warehouse
        elif name == "start":
            params["start"] = slots.start
        elif name == "end":
            params["end"] = slots.end
        elif name == "channel":
            params["channel"] = slots.channel or spec.defaults.get("channel", "all")
        elif name == "rate_source":
            params["rate_source"] = slots.rate_source or spec.defaults.get("rate_source", "clean")
        elif name == "coverage_months":
            params["coverage_months"] = slots.coverage_months or spec.defaults.get("coverage_months", 6)
        elif name == "metric":
            params["metric"] = slots.metric
        else:  # pragma: no cover - 防御未知参数
            params[name] = None
    return {k: v for k, v in params.items() if v is not None}


def required_missing(tool: str, params: dict[str, Any]) -> list[str]:
    spec = TOOLS[tool]
    missing: list[str] = []
    for name in spec.required:
        if name == "skus":
            if len(params.get("skus") or []) < 2:
                missing.append("skus")
        elif name in ("start", "end"):
            if not params.get("start") or not params.get("end"):
                if "period" not in missing:
                    missing.append("period")
        elif name == "sku":
            if not params.get("sku"):
                missing.append("sku")
        elif params.get(name) in (None, "", []):
            missing.append(name)
    # 单 SKU 工具检测到多个 SKU 时同样要求澄清
    if "sku" in spec.required and len(params.get("skus") or []) > 1:
        if "sku" not in missing:
            missing.append("sku")
    # compare 的 monthly_sales 需要时段
    if tool == "compare_skus" and params.get("metric") == "monthly_sales":
        if not params.get("start") or not params.get("end"):
            if "period" not in missing:
                missing.append("period")
    return missing


def route(question: str, data: dict) -> Route:
    matched: list[dict] = []
    selected: RouteRule | None = None
    for rule in RULES:
        if rule.pattern.search(question):
            matched.append({
                "id": rule.rule_id,
                "kind": rule.kind,
                "tool": rule.tool,
                "description": rule.description,
                "pattern": rule.pattern.pattern,
            })
            if selected is None:
                selected = rule

    slots = extract_slots(question, data)

    if selected is None:
        return Route(
            kind="out_of_scope",
            tool=None,
            slots=slots,
            params={},
            missing=[],
            matched=matched,
            selected_rule=None,
            confidence=0.0,
            reason="路由器未匹配任何已注册指标；不猜测，按越界处理。",
        )

    if selected.kind != "tool":
        return Route(
            kind=selected.kind,
            tool=selected.tool,
            slots=slots,
            params={},
            missing=[],
            matched=matched,
            selected_rule=selected.rule_id,
            confidence=1.0,
        )

    tool = selected.tool
    assert tool is not None
    params = build_params(tool, slots)
    missing = required_missing(tool, params)
    return Route(
        kind="tool",
        tool=tool,
        slots=slots,
        params=params,
        missing=missing,
        matched=matched,
        selected_rule=selected.rule_id,
        confidence=1.0,
    )


CLARIFY = {
    "warehouse": {
        "why": "库存、在途、销量与覆盖都是分仓口径，缺仓库不能猜。",
        "options": [
            {"value": "美中-FZH-DANEEY", "label": "美中-Daneey 仓（本数据集覆盖）"},
            {"value": "FZHPoland", "label": "波兰仓（本数据集未覆盖）"},
            {"value": "ALL", "label": "全部仓"},
        ],
        "question": "请指定仓库：美中-Daneey 仓 / 波兰仓 / 全部仓？",
    },
    "period": {
        "why": "『最近』等相对时间没有定义；销量数据只覆盖 2026-03 至 2026-09。",
        "options": [{"value": "2026-03", "label": "起始"}, {"value": "2026-09", "label": "结束"}],
        "question": "请给出起止月份（可用数据范围 2026-03 至 2026-09）。",
    },
    "sku": {
        "why": "未识别到唯一 SKU，或检测到多个 SKU；单 SKU 工具不能猜测。",
        "options": [{"value": sku, "label": rec["name"]} for sku, rec in []],
        "question": "请指定唯一 SKU（2870 / 2871 / 2876 / 2877 / 2878 / 2879 / 2880 / 2881）。",
    },
    "skus": {
        "why": "跨 SKU 比较至少需要两个 SKU。",
        "options": [],
        "question": "请给出至少两个要比较的 SKU。",
    },
    "metric": {
        "why": "跨 SKU 比较必须明确指标，不能跨口径混比。",
        "options": [
            {"value": "clean_monthly_demand", "label": "干净月需求率"},
            {"value": "inventory", "label": "通途可用库存"},
            {"value": "in_transit", "label": "通途在途"},
            {"value": "coverage_months", "label": "覆盖月数"},
            {"value": "recommend_order", "label": "建议补货量"},
            {"value": "monthly_sales", "label": "区间销量"},
        ],
        "question": "请指定比较指标（需求率 / 库存 / 在途 / 覆盖 / 建议补货量 / 销量）。",
    },
}


def clarification_payload(rt: Route, data: dict) -> dict:
    items = []
    questions = []
    for slot in rt.missing:
        info = dict(CLARIFY[slot])
        if slot == "sku" and rt.slots.skus:
            info["why"] = f"检测到多个 SKU：{', '.join(rt.slots.skus)}；请指定一个。"
        if slot in ("sku", "skus"):
            info["options"] = [
                {"value": sku, "label": f"{sku} {rec['name']}"}
                for sku, rec in data["skus"].items()
            ]
        items.append({"slot": slot, **info})
        questions.append(info["question"])
    return {
        "status": "needs_clarification",
        "tool": rt.tool,
        "resolved_slots": jsonable(rt.params),
        "missing_slots": items,
        "clarifying_question": " ".join(questions),
        "executed": False,
        "router": router_payload(rt),
    }


def router_payload(rt: Route) -> dict:
    return {
        "mode": "deterministic_keyword_slots",
        "selected_rule": rt.selected_rule,
        "confidence": rt.confidence,
        "matched_rules": rt.matched,
        "slot_evidence": jsonable(rt.slots.evidence),
    }


# ---------------------------------------------------------------------------
# Agent：prepare -> confirm -> execute -> readback
# ---------------------------------------------------------------------------

WRITE_KEYWORDS = ("下单", "提交", "创建", "修改", "删除", "写入", "采购单", "下 ")


class ReadOnlyAgent:
    def __init__(self, data: dict):
        self.data = data
        self.executed_tools: list[str] = []
        self.plans: list[dict] = []

    # -- 策略拒绝 ---------------------------------------------------------
    def _refuse_write(self, question: str, rt: Route) -> dict:
        return {
            "status": "refused_write",
            "question": question,
            "reason": "本原型只读：工具注册表中没有任何写工具，也没有向通途 / 赛狐 / EN 提交采购单的权限。",
            "policy": {
                "write_tools_declared": 0,
                "allowed_capabilities": "查询、计算、解释、生成草稿文本",
                "forbidden_capabilities": "创建采购单、提交订单、修改库存、写入任何业务系统",
            },
            "safe_alternative": (
                "可以先生成只读的补货建议与采购草稿（不提交），由人工在通途创建并提交采购单；"
                "如需先复核数量，可运行 recommend_order 或 explain_recommendation。"
            ),
            "resolved_slots": {"sku": rt.slots.skus[0]} if rt.slots.skus else {},
            "executed": False,
            "router": router_payload(rt),
        }

    def _refuse_out_of_scope(self, question: str, rt: Route) -> dict:
        return {
            "status": "out_of_scope",
            "question": question,
            "reason": (
                "问题超出已注册指标与数据范围：销售额 / 营收未在指标注册表中定义；"
                "本数据集只覆盖 8 个楔形枕 SKU × 美中-Daneey 仓 × 2026-03 至 2026-09。"
            ),
            "safe_alternative": (
                "可回答历史销量、通途库存、在途、覆盖月数与补货建议；"
                "若确需销售额或公司级预测，需要另行接入财务 / 平台收入数据，并由人确认口径。"
            ),
            "resolved_slots": {},
            "executed": False,
            "router": router_payload(rt),
        }

    def _refuse_premise(self, question: str, rt: Route) -> dict:
        correction = (
            "前提不成立：EN Bin 数量不能当作可用库存。EN 不扣减通途库存，实测差异 351 件；"
            "SO 未交量也不等于在途。可用库存应取通途分仓『可用库存』，在途应取通途采购单未到货量。"
        )
        corrected_values: dict[str, Any] = {}
        corrected_text = ""
        sku = rt.slots.skus[0] if rt.slots.skus else None
        warehouse = rt.slots.warehouse
        if sku and warehouse:
            try:
                res = impl_coverage_months(
                    {"sku": sku, "warehouse": warehouse, "rate_source": "clean"}, self.data
                )
                values = res["values"]
                corrected_values = {
                    "corrected_coverage_months": values["coverage_months"],
                    "corrected_rate": values["rate"],
                    "corrected_available": values["available"],
                    "corrected_in_transit": values["in_transit"],
                }
                corrected_values = jsonable(corrected_values)
                corrected_text = (
                    f"已按正确口径计算 coverage_months(sku={sku}, warehouse={warehouse}, "
                    f"rate_source=clean) ≈ {values['coverage_months']} 个月"
                    f"（可用 {values['available']} + 在途 {values['in_transit']}，"
                    f"月需求率 {values['rate']}）。"
                )
            except ToolError as exc:
                corrected_text = f"正确口径计算未能完成：{exc}"
        else:
            corrected_text = "正确口径仍需要指定仓库；请先补充仓库后再算覆盖。"

        return {
            "status": "premise_conflict",
            "question": question,
            "reason": correction,
            "correction": correction,
            "safe_alternative": (
                f"使用通途可用库存与干净月需求率，而不是 EN Bin。{corrected_text}"
            ),
            "corrected_values": corrected_values,
            "values": corrected_values,
            "resolved_slots": jsonable(rt.params) if rt.params else ({"sku": sku} if sku else {}),
            "executed": False,
            "router": router_payload(rt),
        }

    # -- 主流程 -----------------------------------------------------------
    def ask(
        self,
        question: str,
        auto_confirm: bool = False,
        confirm_fn: Callable[[dict], bool] | None = None,
    ) -> dict:
        rt = route(question, self.data)

        if rt.kind == "write_intent":
            return self._refuse_write(question, rt)
        if rt.kind == "out_of_scope":
            return self._refuse_out_of_scope(question, rt)
        if rt.kind == "premise_conflict":
            return self._refuse_premise(question, rt)
        if rt.missing:
            payload = clarification_payload(rt, self.data)
            payload["question"] = question
            return payload

        plan = self._prepare(rt)
        confirmed = auto_confirm
        confirm_mode = "auto_read_only_eval"
        if not auto_confirm:
            confirmed = bool(confirm_fn(plan)) if confirm_fn else False
            confirm_mode = "human"
        if not confirmed:
            return {
                "status": "cancelled",
                "question": question,
                "plan": plan,
                "executed": False,
                "reason": "未确认，未执行（execute 为只读也不例外，保留人工闸门）。",
                "router": router_payload(rt),
            }

        self._confirm(plan, confirm_mode)
        result, error = self._execute(plan)
        if error is not None:
            return {
                "status": "no_data",
                "question": question,
                "plan": plan,
                "executed": True,
                "reason": error,
                "safe_alternative": "请补充或更正参数；不做近似替代或猜测。",
                "router": router_payload(rt),
            }
        self._readback(plan, result)
        return self._answer(question, rt, plan, result)

    def _prepare(self, rt: Route) -> dict:
        spec = TOOLS[rt.tool]
        plan = {
            "plan_id": hashlib.sha256(
                canonical({"tool": rt.tool, "params": rt.params}).encode("utf-8")
            ).hexdigest()[:12],
            "tool": rt.tool,
            "params": jsonable(rt.params),
            "read_only": spec.read_only,
            "metric": spec.metric,
            "state": "prepared",
            "trace": [{"state": "prepared", "by": "agent"}],
        }
        self.plans.append(plan)
        return plan

    def _confirm(self, plan: dict, mode: str) -> None:
        plan["state"] = "confirmed"
        plan["confirm_mode"] = mode
        plan["trace"].append({"state": "confirmed", "by": mode})

    def _execute(self, plan: dict) -> tuple[dict | None, str | None]:
        spec = TOOLS.get(plan["tool"])
        if spec is None:
            return None, f"工具未注册：{plan['tool']}"
        if not spec.read_only:
            return None, f"拒绝执行非只读工具：{plan['tool']}"
        try:
            result = spec.impl(plan["params"], self.data)
        except ToolError as exc:
            return None, str(exc)
        self.executed_tools.append(plan["tool"])
        plan["state"] = "executed"
        plan["trace"].append({"state": "executed", "tool": plan["tool"], "read_only": True})
        return result, None

    def _readback(self, plan: dict, result: dict) -> dict:
        spec = TOOLS[plan["tool"]]
        second = spec.impl(plan["params"], self.data)
        matches = canonical(result) == canonical(second)
        status = "verified" if matches else "mismatch"
        plan["state"] = f"readback_{status}"
        plan["trace"].append({"state": f"readback_{status}", "method": "re-execute_and_compare"})
        return {"status": status, "method": "re-execute_and_compare", "matches": matches}

    def _answer(self, question: str, rt: Route, plan: dict, result: dict) -> dict:
        spec = TOOLS[plan["tool"]]
        values = jsonable(result["values"])
        readback = {
            "status": plan["state"].replace("readback_", ""),
            "method": "re-execute_and_compare",
            "matches": plan["state"] == "readback_verified",
        }
        evidence = {
            "tool": plan["tool"],
            "params": plan["params"],
            "data_source": spec.data_source,
            "authority": spec.authority,
            "metric_definition": spec.definition,
            "values": values,
            "computation": result.get("computation", []),
            "readback": readback,
            "dataset_id": self.data["meta"]["dataset_id"],
            "as_of": self.data["meta"]["as_of"],
            "numbers_computed_by": "tool_impl",
        }
        summary = render_summary(plan["tool"], plan["params"], values, self.data)
        return {
            "status": "answered",
            "question": question,
            "summary": summary,
            "resolved_slots": jsonable(plan["params"]),
            "values": values,
            "plan": plan,
            "evidence": evidence,
            "executed": True,
            "router": router_payload(rt),
        }


# ---------------------------------------------------------------------------
# 回答渲染（模板化，不做数值推理）
# ---------------------------------------------------------------------------

def channel_label(data: dict, channel: str) -> str:
    return data.get("channels", {}).get(channel, channel)


def warehouse_label(data: dict, warehouse: str) -> str:
    return data.get("warehouses", {}).get(warehouse, {}).get("label", warehouse)


def render_summary(tool: str, params: dict, values: dict, data: dict) -> str:
    if tool == "monthly_sales":
        return (
            f"{params['sku']} 在 {warehouse_label(data, params['warehouse'])}、"
            f"{channel_label(data, params.get('channel', 'all'))}、"
            f"{params['start']}~{params['end']} 的销量合计为 {values['qty']} 件。"
        )
    if tool == "stockout_windows":
        if values.get("has_stockout"):
            return (
                f"{params['sku']} 的断货窗口：{values['stockout_start']} → "
                f"{values['stockout_end']}。"
            )
        return f"{params['sku']} 无断货记录。"
    if tool == "inventory":
        return (
            f"{params['sku']} 在 {warehouse_label(data, params['warehouse'])} 的"
            f"通途可用库存为 {values['available']} 件。"
        )
    if tool == "in_transit":
        po = f"，采购单 {values['po']}" if values.get("po") else ""
        return (
            f"{params['sku']} 在 {warehouse_label(data, params['warehouse'])} 的"
            f"在途为 {values['in_transit']} 件{po}。"
        )
    if tool == "coverage_months":
        return (
            f"{params['sku']} 在 {warehouse_label(data, params['warehouse'])} 的覆盖约 "
            f"{values['coverage_months']} 个月（可用 {values['available']} + 在途 "
            f"{values['in_transit']}，月需求率 {values['rate']}）。"
        )
    if tool == "recommend_order":
        return (
            f"{params['sku']} 在 {warehouse_label(data, params['warehouse'])} 按覆盖 "
            f"{values['coverage_months']} 个月建议补 {values['recommended_qty']} 件"
            f"（目标 {values['target_qty']} − 可用 {values['available']} − 在途 "
            f"{values['in_transit']}，向上取整）。"
        )
    if tool == "explain_recommendation":
        return " ".join(values.get("steps", []))
    if tool == "compare_skus":
        rows = "，".join(f"{r['sku']}={r['value']}" for r in values.get("rows", []))
        return (
            f"{warehouse_label(data, params['warehouse'])} 的 {values['metric']} 比较："
            f"{rows}；较高为 {values.get('max_sku')}。"
        )
    return "（无模板）"


# ---------------------------------------------------------------------------
# 评估
# ---------------------------------------------------------------------------

def compare_values(expected: dict, actual: dict, tol: float = 0.05) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for key, exp in (expected or {}).items():
        if key not in actual:
            failures.append(f"缺少值 {key}")
            continue
        act = actual[key]
        if isinstance(exp, (int, float)) and not isinstance(exp, bool) and isinstance(act, (int, float)):
            if abs(float(act) - float(exp)) > tol:
                failures.append(f"{key}: 期望 {exp}，实际 {act}")
        elif exp != act:
            failures.append(f"{key}: 期望 {exp}，实际 {act}")
    return (not failures, failures)


def normalize_slot(value: Any) -> Any:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def slots_match(expected: dict, actual: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for key, exp in (expected or {}).items():
        if key not in actual:
            failures.append(f"缺少槽位 {key}")
            continue
        if normalize_slot(actual[key]) != normalize_slot(exp):
            failures.append(f"{key}: 期望 {exp}，实际 {actual[key]}")
    return (not failures, failures)


def contains_all(text: str, needles: list[str]) -> tuple[bool, list[str]]:
    missing = [n for n in needles if n.lower() not in (text or "").lower()]
    return (not missing, missing)


def score_case(case: dict, result: dict) -> dict:
    exp = case["expected"]
    status_ok = result.get("status") == exp.get("status")

    actual_tool = result.get("tool")
    if result.get("status") == "answered":
        actual_tool = result.get("evidence", {}).get("tool")
    tool_ok = True if exp.get("tool") is None else actual_tool == exp.get("tool")

    actual_slots = result.get("resolved_slots", {})
    slot_ok, slot_failures = slots_match(exp.get("slots", {}), actual_slots)

    missing_ok = True
    if exp.get("missing_slots"):
        actual_missing = {m["slot"] for m in result.get("missing_slots", [])}
        missing_ok = set(exp["missing_slots"]).issubset(actual_missing)
        if not missing_ok:
            slot_failures.append(
                f"缺失槽位: 期望 {exp['missing_slots']}，实际 {sorted(actual_missing)}"
            )

    value_ok = True
    value_failures: list[str] = []
    if exp.get("values"):
        value_ok, value_failures = compare_values(exp["values"], result.get("values", {}))

    evidence_ok = True
    evidence_failures: list[str] = []
    if result.get("status") == "answered":
        ev = result.get("evidence") or {}
        checks = {
            "tool": bool(ev.get("tool")),
            "params": ev.get("params") is not None,
            "data_source": bool(ev.get("data_source")),
            "values": bool(ev.get("values")),
            "readback": (ev.get("readback") or {}).get("status") == "verified",
        }
        evidence_ok = all(checks.values())
        evidence_failures = [k for k, v in checks.items() if not v]

    safe_ok = True
    safe_failures: list[str] = []
    if exp.get("safe_alternative_contains"):
        safe_ok, safe_failures = contains_all(result.get("safe_alternative", ""), exp["safe_alternative_contains"])

    correction_ok = True
    correction_failures: list[str] = []
    if exp.get("correction_contains"):
        correction_ok, correction_failures = contains_all(
            (result.get("correction", "") + " " + result.get("reason", "")),
            exp["correction_contains"],
        )

    no_execution_required = exp.get("status") in (
        "needs_clarification",
        "refused_write",
        "out_of_scope",
        "premise_conflict",
    )
    execution_ok = (not result.get("executed")) if no_execution_required else bool(result.get("executed"))

    passed = all([
        status_ok,
        tool_ok,
        slot_ok,
        missing_ok,
        value_ok,
        evidence_ok,
        safe_ok,
        correction_ok,
        execution_ok,
    ])
    failures = []
    if not status_ok:
        failures.append(f"状态: 期望 {exp.get('status')}，实际 {result.get('status')}")
    if not tool_ok:
        failures.append(f"工具: 期望 {exp.get('tool')}，实际 {actual_tool}")
    failures.extend(slot_failures)
    failures.extend(value_failures)
    failures.extend(evidence_failures)
    failures.extend(safe_failures)
    failures.extend(correction_failures)
    if not execution_ok:
        failures.append("执行标志与期望不符")

    return {
        "passed": passed,
        "status_ok": status_ok,
        "tool_ok": tool_ok,
        "slots_ok": slot_ok,
        "missing_ok": missing_ok,
        "values_ok": value_ok,
        "evidence_ok": evidence_ok,
        "safe_alternative_ok": safe_ok,
        "correction_ok": correction_ok,
        "execution_ok": execution_ok,
        "failures": failures,
    }


def evaluate(agent: ReadOnlyAgent, questions: dict) -> dict:
    cases_out = []
    for case in questions["cases"]:
        result = agent.ask(case["question"], auto_confirm=True)
        checks = score_case(case, result)
        cases_out.append({
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "expected_status": case["expected"].get("status"),
            "expected_values": case["expected"].get("values", {}),
            "status": result.get("status"),
            "tool": result.get("evidence", {}).get("tool") if result.get("status") == "answered" else result.get("tool"),
            "resolved_slots": result.get("resolved_slots", {}),
            "values": result.get("values", {}),
            "summary": result.get("summary"),
            "checks": checks,
            "result": result,
        })

    total = len(cases_out)
    answerable = [c for c in cases_out if c["category"] == "answerable"]
    ambiguous = [c for c in cases_out if c["category"] == "ambiguous"]
    writes = [c for c in cases_out if c["category"] == "write"]
    oos = [c for c in cases_out if c["category"] == "out_of_scope"]
    premise = [c for c in cases_out if c["category"] == "premise_conflict"]

    answerable_ok = sum(1 for c in answerable if c["checks"]["passed"])
    ambiguous_ok = sum(1 for c in ambiguous if c["checks"]["passed"])
    write_ok = sum(1 for c in writes if c["checks"]["passed"])
    oos_ok = sum(1 for c in oos if c["checks"]["passed"])
    premise_ok = sum(1 for c in premise if c["checks"]["passed"])
    valued = [c for c in cases_out if c.get("expected_values")]
    value_ok = sum(1 for c in valued if c["checks"]["values_ok"])

    executed_tools = list(agent.executed_tools)
    write_executions = [t for t in executed_tools if t not in TOOLS or not TOOLS[t].read_only]
    answered = [c for c in cases_out if c["status"] == "answered"]
    evidence_ok = sum(1 for c in answered if c["checks"]["evidence_ok"])

    answerable_rate = answerable_ok / len(answerable) if answerable else 0.0
    ambiguous_rate = ambiguous_ok / len(ambiguous) if ambiguous else 1.0
    evidence_rate = evidence_ok / len(answered) if answered else 1.0
    value_rate = value_ok / len(valued) if valued else 1.0
    semantic_ambiguity_rate = len(ambiguous) / total if total else 0.0
    router_unmatched = sum(1 for c in cases_out if c["result"].get("router", {}).get("selected_rule") is None)
    slot_unresolved_on_answerable = sum(1 for c in answerable if c["status"] != "answered")

    pass_all = (
        answerable_rate >= 0.9
        and len(write_executions) == 0
        and write_ok == len(writes)
        and evidence_rate == 1.0
        and ambiguous_rate == 1.0
    )
    falsified = semantic_ambiguity_rate > 0.2 or slot_unresolved_on_answerable > 0.2 * len(answerable) or router_unmatched > 0

    if pass_all and not falsified:
        verdict = "PASS：语义层 + 确定性路由足以支撑该楔形切片；可以进入带人工确认的只读 Agent 试点。"
    elif not pass_all and falsified:
        verdict = "FALSIFY：先补语义层（SKU/仓库/口径映射），不要先做 Agent。"
    else:
        verdict = "MIXED：有单项未达标，需看失败分析逐项修复后再判。"

    return {
        "meta": {
            "dataset_id": agent.data["meta"]["dataset_id"],
            "as_of": agent.data["meta"]["as_of"],
            "input_sha256": sha256_file(DATA_FILE),
            "questions_sha256": sha256_file(QUESTIONS_FILE),
            "agent": "e3_agent/agent.py",
            "router_mode": "deterministic_keyword_slots",
            "llm_calls": 0,
        },
        "summary": {
            "total_cases": total,
            "passed_cases": sum(1 for c in cases_out if c["checks"]["passed"]),
            "answerable_correct": f"{answerable_ok}/{len(answerable)}",
            "answerable_rate": round(answerable_rate, 4),
            "ambiguous_clarified": f"{ambiguous_ok}/{len(ambiguous)}",
            "write_refused_with_safe_alternative": f"{write_ok}/{len(writes)}",
            "out_of_scope_refused": f"{oos_ok}/{len(oos)}",
            "premise_conflict_corrected": f"{premise_ok}/{len(premise)}",
            "evidence_coverage": f"{evidence_ok}/{len(answered)}",
            "value_accuracy": f"{value_ok}/{len(valued)}",
            "value_accuracy_rate": round(value_rate, 4),
            "executed_tools": executed_tools,
            "write_executions": len(write_executions),
            "semantic_ambiguity_rate": round(semantic_ambiguity_rate, 4),
            "router_unmatched_cases": router_unmatched,
            "slot_unresolved_on_answerable": slot_unresolved_on_answerable,
            "pass": pass_all,
            "falsified": falsified,
            "verdict": verdict,
        },
        "cases": cases_out,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_eval_table(report: dict) -> None:
    header = f"{'ID':<4} {'CATEGORY':<16} {'STATUS':<22} {'TOOL':<24} {'SLOTS':<6} {'EVID':<5} {'VALUE':<6} {'PASS':<5}"
    print(header)
    print("-" * len(header))
    for c in report["cases"]:
        checks = c["checks"]
        value_flag = "OK" if checks["values_ok"] else "FAIL"
        if not c.get("expected_values"):
            value_flag = "-"
        print(
            f"{c['id']:<4} {c['category']:<16} {str(c['status']):<22} "
            f"{str(c['tool'] or '-'):<24} "
            f"{('OK' if checks['slots_ok'] and checks['missing_ok'] else 'FAIL'):<6} "
            f"{('OK' if checks['evidence_ok'] else 'FAIL'):<5} "
            f"{value_flag:<6} "
            f"{('PASS' if checks['passed'] else 'FAIL'):<5}"
        )
    s = report["summary"]
    print()
    print(f"answerable: {s['answerable_correct']}  ({s['answerable_rate']:.1%})")
    print(f"ambiguous clarified: {s['ambiguous_clarified']}")
    print(f"write refused w/ safe alternative: {s['write_refused_with_safe_alternative']}")
    print(f"out-of-scope refused: {s['out_of_scope_refused']}")
    print(f"premise corrected: {s['premise_conflict_corrected']}")
    print(f"evidence coverage: {s['evidence_coverage']}")
    print(f"value accuracy (cases with expected values): {s['value_accuracy']} ({s['value_accuracy_rate']:.1%})")
    print(f"write executions: {s['write_executions']}")
    print(f"semantic ambiguity rate: {s['semantic_ambiguity_rate']:.1%}")
    print(f"verdict: {s['verdict']}")


def interactive_confirm(plan: dict) -> bool:
    print("\n[prepare] 只读查询计划")
    print(json.dumps(jsonable(plan), ensure_ascii=False, indent=2))
    try:
        answer = input("\n确认执行只读查询？[y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes", "是")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E3 只读 Agent 原型（无 LLM）")
    parser.add_argument("--eval", action="store_true", help="运行 15 题评估并写 results.json")
    parser.add_argument("--ask", metavar="QUESTION", help="交互式提问")
    parser.add_argument("--yes", action="store_true", help="跳过人工确认（仅因工具只读）")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    data = load_data()
    agent = ReadOnlyAgent(data)

    if args.ask:
        result = agent.ask(
            args.ask,
            auto_confirm=args.yes,
            confirm_fn=interactive_confirm,
        )
        print(json.dumps(jsonable(result), ensure_ascii=False, indent=2))
        return 0

    if args.eval:
        with QUESTIONS_FILE.open("r", encoding="utf-8") as fh:
            questions = json.load(fh)
        report = evaluate(agent, questions)
        with RESULTS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(jsonable(report), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print_eval_table(report)
        print(f"\nresults written to: {RESULTS_FILE}")
        return 0 if report["summary"]["pass"] else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
