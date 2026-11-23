# -*- coding: utf-8 -*-
"""独立决策规则（纯函数）：日期重算 / 交期取值 / CG 抵扣上界 / 通途 PO 开放行。

为什么独立成模块：``decide.py`` 当前的 ``需要日 / 下单日 / CG 抵扣`` 直接沿用
D6 包（``date_source=d6_pack``），在 live 模式下会拿历史时点当今天用。这里只提供
可被编排器调用的**纯计算**，不依赖 D6 包里的固定日期或 CG 值：

- :func:`recalc_dates` —— 需要日 + 交期 → 下单日 + 未来/过期状态；
- :func:`lead_days_for` —— 从 ``service_policy`` 行取交期（列名不统一，识别常见写法）；
- :func:`cg_allowance` —— 只汇总 ``WayfairCG-*`` 仓的可用量作为**上界证据**；
  没有 ``rule.max_share`` 时**不给** ``allowed``（不抵扣）；
- :func:`po_open_from_purchase_jsonl` —— 解析通途 ``purchaseOrderQuery`` 落地 JSONL。

共同约束：

- 纯函数：只读入参/本地 JSONL，不发网络请求、不读写凭证；
- 缺失/歧义一律 ``None`` / ``unknown``，不猜、不写 0；
- 未映射 SKU、仓不落本分公司等行**保留并计数**，不静默丢弃。
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import (
    load_warehouse_config,
    resolve_warehouse_role,
)

CG_WAREHOUSE_PREFIX = "WayfairCG"

# 通途 purchaseOrderQuery 的 status 口径（与 supply_netting.supply 一致）
PO_OPEN_STATUSES = frozenset({"0", "1", "2"})
PO_CANCELLED_STATUSES = frozenset({"4"})

PO_COLUMNS = [
    "document_key", "sku", "product_id", "warehouse", "open_qty", "eta",
    "status", "date_unproven", "identity_status", "warehouse_out_of_branch",
]

# 识别交期列的常见写法；匹配前统一去空白/下划线/连字符并转小写。
LEAD_COLUMNS = frozenset({
    "leaddays", "leadday", "leadtime", "leadtimes", "leadtimedays",
    "交期", "交期天", "交期天数", "采购交期", "采购交期天", "采购交期天数",
    "备货天", "备货天数", "生产周期", "生产周期天", "生产周期天数",
})

_LEAD_TEXT = re.compile(r"(\d+)\s*(?:天|日|d|days?)?", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _norm_name(value) -> str:
    text = str(value).strip().lower()
    for ch in (" ", "\t", "_", "-"):
        text = text.replace(ch, "")
    return text


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    return str(value).strip()


def _number(value):
    """数字 → float；缺失/非数值 → None（已知的 0 保留为 0）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text or text.lower() in ("nan", "none", "null"):
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_date(value):
    """ISO 日期/时间（含 pandas.Timestamp）→ ``datetime.date``；缺失/非法 → None。"""
    if value is None:
        return None
    if isinstance(value, datetime):        # datetime 含 pandas.Timestamp
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text or text.lower() in ("nan", "nat", "none", "null"):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _positive_int(value):
    """正整数（日历天）→ int；0/负数/小数/非数值 → None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        match = _LEAD_TEXT.fullmatch(text)
        number = int(match.group(1)) if match else None
    else:
        number = _number(value)
        if number is not None and not number.is_integer():
            number = None
    if number is None:
        return None
    return int(number) if number > 0 else None


def _rows(frame):
    """DataFrame → records；可迭代 mapping → list[dict]；None → []。"""
    if frame is None:
        return []
    if isinstance(frame, pd.DataFrame):
        return frame.to_dict("records")
    return [dict(row) for row in frame]


def _max_share(rule):
    """rule 里的 ``max_share``（0..1）；未给 → None；非法值直接报错，不静默忽略。"""
    if not rule:
        return None
    try:
        raw = rule.get("max_share")
    except AttributeError as exc:
        raise ValueError("rule 必须是映射（如 {'max_share': 0.5}）") from exc
    if raw is None:
        return None
    try:
        share = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"rule.max_share 必须是 0..1 的数：{raw!r}") from exc
    if not math.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError(f"rule.max_share 超出 0..1：{raw!r}")
    return share


def _canonical_warehouse(raw_name: str, warehouse_cfg) -> str:
    if not raw_name or warehouse_cfg is None:
        return raw_name
    resolved = resolve_warehouse_role(raw_name, warehouse_cfg)
    return str(resolved.get("canonical_warehouse") or raw_name)


# --------------------------------------------------------------------------- #
# 1) 日期重算
# --------------------------------------------------------------------------- #
def recalc_dates(need_date, as_of, lead_days) -> dict:
    """``需要日 − 交期`` → 下单日 + 状态（不虚构）。

    参数
    ----
    need_date : ISO 日期/时间（也接受 ``date`` / ``datetime`` / ``None``）
    as_of : 决策时点（ISO 日期/时间）；取其中的日期与下单日比较
    lead_days : 正整数，**日历天**

    返回 dict
    --------
    ``need_date`` / ``lead_days`` / ``as_of`` / ``order_date`` / ``status``

    - ``status`` ∈ ``future`` / ``past_due`` / ``unknown``；
      下单日**等于** as_of 当天算 ``future``（当天还能下），与 ``decide`` 口径一致。
    - ``need_date`` 或 ``lead_days`` 缺失/非法 → ``order_date=None``、``status=unknown``；
      ``as_of`` 缺失只影响状态，不影响可算出的 ``order_date``。
    """
    need = _as_date(need_date)
    days = _positive_int(lead_days)
    as_of_day = _as_date(as_of)
    result = {
        "need_date": need.isoformat() if need else None,
        "lead_days": days,
        "as_of": as_of_day.isoformat() if as_of_day else None,
        "order_date": None,
        "status": "unknown",
    }
    if need is None or days is None:
        return result
    order = need - timedelta(days=days)
    result["order_date"] = order.isoformat()
    if as_of_day is None:
        return result
    result["status"] = "past_due" if order < as_of_day else "future"
    return result


# --------------------------------------------------------------------------- #
# 2) 交期取值
# --------------------------------------------------------------------------- #
def lead_days_for(sku, policy_rows, default=None):
    """从 ``service_policy`` 行取该 SKU 的交期（正整数日历天）。

    - ``policy_rows`` 接受 DataFrame 或 mapping 序列；SKU 列名必须是 ``sku``。
    - 交期列名识别 :data:`LEAD_COLUMNS`（``lead_days`` / ``leadtime`` / ``交期`` 等，
      忽略大小写、空格、下划线、连字符）。
    - 找不到该 SKU、没有可识别列、值非正整数、或同一 SKU 给出**冲突值** →
      返回 ``default``；不做中位数/最大值的猜测。
    """
    target = _text(sku)
    if not target:
        return default
    rows = [{_norm_name(key): value for key, value in row.items()}
            for row in _rows(policy_rows)]
    if not rows or "sku" not in rows[0]:
        return default
    values = set()
    for row in rows:
        if _text(row.get("sku")) != target:
            continue
        for key, value in row.items():
            if key == "sku" or key not in LEAD_COLUMNS:
                continue
            days = _positive_int(value)
            if days is not None:
                values.add(days)
    if len(values) != 1:
        return default
    return values.pop()


# --------------------------------------------------------------------------- #
# 3) CG 抵扣上界
# --------------------------------------------------------------------------- #
def cg_allowance(stock_df, lookup, *, warehouse_prefix=CG_WAREHOUSE_PREFIX, rule=None):
    """只汇总 ``WayfairCG-*`` 仓的 ``available``，按 ``product_id`` 聚合。

    参数
    ----
    stock_df : 库存快照（列 ``sku`` / ``warehouse_name`` / ``available``）
    lookup : 通途 SKU → ``product_id``（EN 物料码）
    warehouse_prefix : 只认仓库名以此开头的行
    rule : ``{"max_share": 0..1}``；**默认 None = 不抵扣**，只给上界证据

    返回 ``(per_sku_available, evidence)``

    - ``per_sku_available``：``{product_id: 可用量合计}``；未映射 SKU 不进这里。
    - ``evidence["by_sku"]``：每个 SKU 的 ``available`` / ``upper_bound``，以及
      **只有** ``rule.max_share`` 明确给出时才有的 ``allowed``。
    - ``conditional=True`` 表示可调拨量只有上界、**没有可执行调拨日期**；
      ``transfer_date`` 恒为 ``None``。
    - 未映射 SKU 的原始码保留在 ``evidence["unmapped_skus"]``，行数单列计数。
    """
    share = _max_share(rule)
    conditional = share is not None
    per_sku: dict[str, float] = {}
    unmapped_skus: list[str] = []
    warehouses: set[str] = set()
    evidence = dict(
        warehouse_prefix=warehouse_prefix,
        rows=0,
        mapped_rows=0,
        unmapped_rows=0,
        unmapped_skus=unmapped_skus,
        rows_missing_available=0,
        warehouses=[],
        quantity=0.0,
        max_share=share,
        conditional=conditional,
        allowed_source="rule.max_share" if conditional else None,
        transfer_date=None,            # 没有可执行调拨日期，不虚构
        by_sku={},
    )

    for row in _rows(stock_df):
        warehouse = _text(row.get("warehouse_name"))
        if not warehouse.startswith(warehouse_prefix):
            continue
        evidence["rows"] += 1
        warehouses.add(warehouse)
        raw_sku = _text(row.get("sku"))
        product_id = lookup.get(raw_sku) if lookup else None
        if not product_id:
            evidence["unmapped_rows"] += 1
            if raw_sku not in unmapped_skus:
                unmapped_skus.append(raw_sku)
            continue
        evidence["mapped_rows"] += 1
        amount = _number(row.get("available"))
        if amount is None:
            evidence["rows_missing_available"] += 1
            continue
        per_sku[product_id] = per_sku.get(product_id, 0.0) + amount

    for product_id, available in per_sku.items():
        evidence["by_sku"][product_id] = dict(
            available=available,
            upper_bound=available,
            allowed=(available * share if conditional else None),
            conditional=conditional,
            transfer_date=None,
        )
    evidence["warehouses"] = sorted(warehouses)
    evidence["quantity"] = round(sum(per_sku.values()), 6)
    return per_sku, evidence


# --------------------------------------------------------------------------- #
# 4) 通途开放 PO
# --------------------------------------------------------------------------- #
def po_open_from_purchase_jsonl(path, lookup=None, warehouse_cfg=None,
                                branch_prefix=None):
    """解析通途 ``purchaseOrderQuery`` 落地 JSONL → 开放 PO 行 + 证据。

    - ``status`` 0/1/2 视为开放、4 作废；其余状态不当作开放（单列计数）。
    - 开放量 = ``quantity − in_quantity``，只保留 > 0 的行。
    - ETA 取 ``willArriveDate`` / ``purchaseArrivalDate``；都为空 →
      ``eta=None``、``date_unproven=True``，不填日期。
    - ``sku`` 是通途 ``goods_sku``；``product_id`` 由 ``lookup`` 映射。
      未映射行保留、``identity_status="unmapped"``；``lookup=None`` 时标
      ``identity_status="not_checked"``（不冒充已映射）。
    - ``warehouse_cfg`` 给定时按规范仓名判断是否落本分公司前缀；不落的行保留、
      ``warehouse_out_of_branch=True``。``branch_prefix=None`` 时无法判断 → False。

    返回 ``(frame, evidence)``；``frame`` 列见 :data:`PO_COLUMNS`。
    """
    path = Path(path)
    evidence = dict(
        source=str(path), exists=path.exists(), rows_in=0, open_rows=0,
        quantity=0.0, with_eta=0, date_unproven=0,
        cancelled_rows=0, cancelled_quantity=0.0,
        unsupported_status_rows=0, missing_quantity=0, zero_open=0,
        identity_missing=0, warehouse_out_of_branch=0,
        identity=("not_checked" if lookup is None else "lookup"),
        branch_prefix=branch_prefix,
        open_statuses=sorted(PO_OPEN_STATUSES),
        cancelled_statuses=sorted(PO_CANCELLED_STATUSES),
    )
    if not path.exists():
        return pd.DataFrame(columns=PO_COLUMNS), evidence

    if warehouse_cfg is None and branch_prefix:
        try:
            warehouse_cfg = load_warehouse_config()
        except (OSError, ValueError, json.JSONDecodeError):
            warehouse_cfg = None

    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"第 {lineno} 行不是合法 JSON：{exc.msg}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"第 {lineno} 行不是 JSON 对象")
        evidence["rows_in"] += 1

        status = _text(record.get("status"))
        quantity = _number(record.get("quantity"))
        received = _number(record.get("in_quantity"))
        if status in PO_CANCELLED_STATUSES:
            evidence["cancelled_rows"] += 1
            if quantity is not None:
                evidence["cancelled_quantity"] += quantity
            continue
        if status not in PO_OPEN_STATUSES:
            evidence["unsupported_status_rows"] += 1
            continue
        if quantity is None or received is None:
            evidence["missing_quantity"] += 1
            continue
        open_qty = quantity - received
        if open_qty <= 0:
            evidence["zero_open"] += 1
            continue

        raw_sku = _text(record.get("goods_sku"))
        if lookup is None:
            product_id, identity_status = None, "not_checked"
        else:
            product_id = lookup.get(raw_sku)
            identity_status = "mapped" if product_id else "unmapped"
            if not product_id:
                evidence["identity_missing"] += 1

        warehouse = _text(record.get("warehouseName"))
        canonical = _canonical_warehouse(warehouse, warehouse_cfg)
        out_of_branch = bool(branch_prefix) and not canonical.startswith(branch_prefix)
        if out_of_branch:
            evidence["warehouse_out_of_branch"] += 1

        eta = (_text(record.get("willArriveDate"))
               or _text(record.get("purchaseArrivalDate")))
        eta = eta or None
        if eta is None:
            evidence["date_unproven"] += 1
        else:
            evidence["with_eta"] += 1

        rows.append(dict(
            document_key=_text(record.get("PONum")) or _text(record.get("purchaseOrderId")),
            sku=raw_sku,
            product_id=product_id,
            warehouse=warehouse,
            open_qty=open_qty,
            eta=eta,
            status=status,
            date_unproven=eta is None,
            identity_status=identity_status,
            warehouse_out_of_branch=out_of_branch,
        ))
        evidence["quantity"] += open_qty

    frame = pd.DataFrame(rows, columns=PO_COLUMNS)
    evidence["open_rows"] = int(len(frame))
    evidence["quantity"] = round(evidence["quantity"], 6)
    evidence["cancelled_quantity"] = round(evidence["cancelled_quantity"], 6)
    return frame, evidence
