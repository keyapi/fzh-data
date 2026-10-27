# -*- coding: utf-8 -*-
"""把 EN ``Tongtool Order`` 单据标准化为订单 / 行 / 包裹三张表。

关键口径（写进 docs/reference/en-order-schema.md）
- 时间点分开保留：sale_time（销售）/ paid_time（付款）/ despatch_complete_time（发货）/
  updated_time（源修改）/ last_sync_time（EN 采集）/ modified（EN 记录修改，做增量水位）/
  first_seen_at + last_seen_at（本地采集）。
- 拆包/拆单：单据名与 platform_order_id 都可能带 ``_1`` ``_2`` 后缀；base_order_id 去掉后缀，
  但行主键仍用完整单据名，绝不按 base 合并。
- 行身份：优先用 raw_data.orderDetails[].orderDetailsId；缺失时用
  ``doc|idx|sku|qty``，因此同单同 SKU 多行不会被吞。
- 取消：EN 的 ``invalid=1``（作废）是主要信号；状态字段本身没有"已取消"。
- 组件：``is_deliver_good=0`` → embedded_component，不并入成品需求。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable, Sequence

from . import config

_SPLIT_RE = re.compile(r"^(?P<base>.+)_(?P<n>\d+)$")


def _s(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def split_order_id(name: str, platform_order_id: str | None) -> dict:
    """识别拆单后缀。

    ``base_order_id`` 一律从**单据名**去后缀（保留渠道前缀，如 ``WFUS-CS681491427``），
    这样 EN 与 GS 的 base 口径一致；``platform_base_order_id`` 另存去后缀的平台单号。
    """
    name = name or ""
    plat = _s(platform_order_id)
    m = _SPLIT_RE.match(name)
    plat_m = _SPLIT_RE.match(plat) if plat else None
    if not m:
        return {
            "base_order_id": name or plat,
            "platform_base_order_id": plat_m.group("base") if plat_m else plat,
            "split_suffix": None,
            "split_index": None,
            "split_basis": "none",
        }
    index = int(m.group("n"))
    basis = "name_and_platform_id_suffix" if plat_m else "name_suffix_only"
    return {
        "base_order_id": m.group("base"),
        "platform_base_order_id": plat_m.group("base") if plat_m else plat,
        "split_suffix": f"_{index}",
        "split_index": index,
        "split_basis": basis,
    }


def classify_warehouse(warehouse: str | None) -> tuple[str | None, str]:
    """仅凭仓库名给出的范围判断；返回 (scope|None, evidence)。"""
    wh = _s(warehouse)
    if not wh:
        return None, "warehouse empty"
    if config.FBA_PATTERN.search(wh):
        return config.SCOPE_FBA, f"warehouse contains FBA: {wh}"
    if wh in config.THIRD_PARTY_WAREHOUSES:
        return config.SCOPE_THIRD_PARTY, (
            f"warehouse {wh}: {config.THIRD_PARTY_WAREHOUSES[wh]}"
        )
    if config.THIRD_PARTY_PATTERN.search(wh):
        return config.SCOPE_THIRD_PARTY, f"warehouse name contains 代发: {wh}"
    if wh in config.UNMAPPED_WAREHOUSES:
        return None, f"warehouse not mapped: {wh}"
    if config.OWN_WAREHOUSE_PATTERN.search(wh) or wh in config.OWN_WAREHOUSES:
        return config.SCOPE_SELF, f"own branch warehouse: {wh}"
    return None, f"warehouse not mapped: {wh}"


def classify_scope(order_type: str | None, warehouse: str | None) -> dict:
    """四分类 fulfillment_scope + 证据 + 冲突标记。

    不猜店铺名；渠道/店铺字段原样保留。
    """
    ot = _s(order_type)
    wh = _s(warehouse)
    wh_scope, wh_evidence = classify_warehouse(wh)
    conflict = None
    evidence: list[str] = []

    if ot == "FBA":
        scope = config.SCOPE_FBA
        evidence.append("order_type=FBA")
        if wh and wh_scope != config.SCOPE_FBA:
            conflict = "order_type_fba_but_warehouse_not_fba"
            evidence.append(wh_evidence)
    elif ot == "自发货":
        if wh_scope == config.SCOPE_FBA:
            scope = config.SCOPE_UNKNOWN
            conflict = "order_type_self_but_warehouse_fba"
            evidence.append("order_type=自发货")
            evidence.append(wh_evidence)
        elif wh_scope == config.SCOPE_THIRD_PARTY:
            scope = config.SCOPE_THIRD_PARTY
            evidence.append(wh_evidence)
        else:
            scope = config.SCOPE_SELF
            evidence.append("order_type=自发货")
            if wh_scope is None:
                evidence.append(wh_evidence)
    else:
        if wh_scope in (config.SCOPE_FBA, config.SCOPE_THIRD_PARTY):
            scope = wh_scope
            evidence.append(wh_evidence)
        else:
            scope = config.SCOPE_UNKNOWN
            evidence.append(f"order_type={ot or 'empty'}")
            evidence.append(wh_evidence)

    return {
        "fulfillment_scope": scope,
        "scope_evidence": "; ".join(evidence),
        "scope_conflict": conflict,
    }


def demand_kind(shipping_method: str | None, is_deliver_good) -> tuple[str, str]:
    """发货形态 → 需求类型；返回 (kind, basis)。"""
    flag = _int(is_deliver_good)
    if flag == 0:
        return config.DSHIP_EMBEDDED, "is_deliver_good=0"
    method = _s(shipping_method)
    if method in config.SHIPPING_METHOD_TO_KIND:
        return config.SHIPPING_METHOD_TO_KIND[method], f"shipping_method={method}"
    return config.DSHIP_UNKNOWN, f"shipping_method={method or 'empty'}"


def lifecycle_state(invalid, order_status: str | None, refunded_flag) -> str:
    if _int(invalid):
        return "cancelled_invalid"
    status = _s(order_status) or ""
    if status in ("已取消",):
        return "cancelled_status"
    if status in ("已退款",) or _int(refunded_flag):
        return "refunded"
    return "active"


def _raw_json(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _match_raw_details(lines: Sequence[dict], details: Sequence[dict]) -> list[dict]:
    """给每个子表行找稳定的源明细 ID（orderDetailsId）。

    匹配优先级：唯一 (webstore_item_id, webstore_sku) → 唯一 (webstore_sku, goodsMatchedSku)
    → 按 idx 位置（仅当行数一致）→ None。
    """
    result: list[dict] = [{"source_line_id": None, "line_identity_basis": None} for _ in lines]
    if not details or not lines:
        return result
    used: set[int] = set()

    def assign(line_key_fn, detail_key_fn, basis: str) -> None:
        for i, line in enumerate(lines):
            if result[i]["source_line_id"]:
                continue
            key = line_key_fn(line)
            if not key or any(v is None for v in key):
                continue
            hits = [
                j
                for j, d in enumerate(details)
                if j not in used and detail_key_fn(d) == key
            ]
            if len(hits) == 1:
                j = hits[0]
                sid = _s(details[j].get("orderDetailsId"))
                if sid:
                    used.add(j)
                    result[i] = {"source_line_id": sid, "line_identity_basis": basis}

    assign(
        lambda line: (_s(line.get("web_store_item_id")), _s(line.get("platform_sku"))),
        lambda d: (_s(d.get("webstore_item_id")), _s(d.get("webstore_sku"))),
        "order_details_id:webstore_item_id+webstore_sku",
    )
    assign(
        lambda line: (_s(line.get("platform_sku")), _s(line.get("tongtool_sku"))),
        lambda d: (_s(d.get("webstore_sku")), _s(d.get("goodsMatchedSku"))),
        "order_details_id:webstore_sku+goodsMatchedSku",
    )

    if len(details) == len(lines):
        for i, line in enumerate(lines):
            if result[i]["source_line_id"]:
                continue
            idx = _int(line.get("idx"))
            pos = (idx - 1) if idx and 1 <= idx <= len(details) else i
            if pos in used:
                continue
            sid = _s(details[pos].get("orderDetailsId"))
            if sid:
                used.add(pos)
                result[i] = {"source_line_id": sid, "line_identity_basis": "positional_idx"}

    # 源数据里同一 orderDetailsId 可能挂在多行（例如一套沙发拆成多个物料行）。
    # 这种情况不能拿它当唯一行键，否则同单多行会被下游合并。
    seen_sids: set[str] = set()
    for item in result:
        sid = item["source_line_id"]
        if not sid:
            continue
        if sid in seen_sids:
            item["line_identity_basis"] = (item["line_identity_basis"] or "source_id") + "+source_id_shared"
        else:
            seen_sids.add(sid)
    return result


def _line_key(doc: str, idx, source_line_id: str | None, platform_sku, tongtool_sku, qty) -> str:
    if source_line_id:
        return f"{doc}|src:{source_line_id}"
    # 回退键必须带 idx：同单同 SKU 多行不会互相吞掉
    return f"{doc}|idx:{idx}|sku:{tongtool_sku or platform_sku or '?'}|qty:{qty}"


def _state_payload(order: dict, lines: list[dict], packages: list[dict]) -> str:
    payload = {
        "order_status": order.get("order_status"),
        "invalid": order.get("invalid"),
        "suspended": order.get("suspended"),
        "despatch_complete_time": order.get("despatch_complete_time"),
        "paid_time": order.get("paid_time"),
        "warehouse_name": order.get("warehouse_name"),
        "tracking_number": order.get("tracking_number"),
        "lines": sorted(
            [
                [
                    l.get("idx"),
                    l.get("platform_sku"),
                    l.get("tongtool_sku"),
                    l.get("quantity"),
                    l.get("is_deliver_good"),
                    l.get("shipping_method"),
                ]
                for l in lines
            ],
            key=lambda x: (x[0] or 0, str(x[1]), str(x[2])),
        ),
        "packages": sorted(
            [[p.get("package"), p.get("tracking_number")] for p in packages],
            key=lambda x: str(x[0]),
        ),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def state_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_order(
    head: dict,
    item_rows: Iterable[dict],
    package_rows: Iterable[dict],
    run: dict,
) -> dict:
    """单据 → {order, lines, packages, raw}。缺失值保留为 None，不填 0。"""
    raw = _raw_json(head.get("raw_data"))
    doc = head["name"]
    ids = split_order_id(doc, head.get("platform_order_id"))

    scope = classify_scope(head.get("order_type"), head.get("warehouse_name"))
    refunded_flag = raw.get("isRefunded")
    invalid_raw = raw.get("isInvalid")
    lifecycle = lifecycle_state(head.get("invalid"), head.get("order_status"), refunded_flag)

    details = raw.get("orderDetails") or []
    if not isinstance(details, list):
        details = []
    raw_items = [r for r in item_rows if r.get("name") == doc]
    raw_items.sort(key=lambda r: (_int(r.get("idx")) or 0))

    matches = _match_raw_details(raw_items, details)

    lines: list[dict] = []
    seen_line_keys: set[str] = set()
    duplicates = 0
    for i, item in enumerate(raw_items):
        kind, kind_basis = demand_kind(item.get("shipping_method"), item.get("is_deliver_good"))
        idx = _int(item.get("idx"))
        qty = _int(item.get("quantity"))
        match = matches[i]
        source_line_id = match["source_line_id"]
        basis = match["line_identity_basis"] or "fallback_idx_sku_qty"
        key_source_id = None if basis.endswith("+source_id_shared") else source_line_id
        key = _line_key(
            doc,
            idx,
            key_source_id,
            item.get("platform_sku"),
            item.get("tongtool_sku"),
            qty,
        )
        if key in seen_line_keys:
            # 理论上只有污染数据会遇到；保留并显式标记，不静默丢弃
            duplicates += 1
            key = f"{key}|dup{duplicates}"
        seen_line_keys.add(key)
        lines.append(
            {
                "line_key": key,
                "en_doc_name": doc,
                "base_order_id": ids["base_order_id"],
                "idx": idx,
                "source_line_id": source_line_id,
                "line_identity_basis": basis,
                "platform_sku": _s(item.get("platform_sku")),
                "tongtool_sku": _s(item.get("tongtool_sku")),
                "erp_item_code": _s(item.get("erp_item_code")),
                "quantity": qty,
                "quantity_missing": qty is None,
                "is_deliver_good": _int(item.get("is_deliver_good")),
                "shipping_method": _s(item.get("shipping_method")),
                "demand_kind": kind,
                "demand_kind_basis": kind_basis,
                "match_status": _s(item.get("match_status")),
                "asin": _s(item.get("asin")),
                "web_store_item_id": _s(item.get("web_store_item_id")),
                "transaction_price": _num(item.get("transaction_price")),
                "calc_price_rmb": _num(item.get("calc_price_rmb")),
                "item_cost": _num(item.get("item_cost")),
            }
        )

    packages: list[dict] = []
    for order_row in package_rows:
        if order_row.get("name") != doc:
            continue
        package = _s(order_row.get("package"))
        tracking = _s(order_row.get("tracking_number"))
        if not package and not tracking:
            continue  # LEFT JOIN 的空行
        packages.append(
            {
                "en_doc_name": doc,
                "package": package,
                "tracking_number": tracking,
                "allocated_fee": _num(order_row.get("allocated_fee")),
                "currency": _s(order_row.get("currency")),
                "allocated_carrier_fee": _num(order_row.get("allocated_carrier_fee")),
                "carrier_currency": _s(order_row.get("carrier_currency")),
            }
        )
    packages.sort(key=lambda p: (p.get("package") or "", p.get("tracking_number") or ""))
    for i, pkg in enumerate(packages):
        pkg["package_index"] = i + 1
    if not packages and (_s(head.get("package_id")) or _s(head.get("tracking_number"))):
        packages.append(
            {
                "en_doc_name": doc,
                "package": _s(head.get("package_id")),
                "tracking_number": _s(head.get("tracking_number")),
                "allocated_fee": None,
                "currency": None,
                "allocated_carrier_fee": None,
                "carrier_currency": None,
                "package_index": 1,
            }
        )
        packages[0]["package_source"] = "order_head_fields"
    for pkg in packages:
        pkg.setdefault("package_source", "order_packages_child")

    qty_total = sum(l["quantity"] for l in lines if l["quantity"] is not None)
    order = {
        "en_doc_name": doc,
        "en_order_id_code": _s(head.get("order_id_code")),
        "platform_order_id": _s(head.get("platform_order_id")),
        "base_order_id": ids["base_order_id"],
        "platform_base_order_id": ids["platform_base_order_id"],
        "split_suffix": ids["split_suffix"],
        "split_index": ids["split_index"],
        "split_basis": ids["split_basis"],
        "order_type": _s(head.get("order_type")),
        "order_status": _s(head.get("order_status")),
        "invalid": _int(head.get("invalid")),
        "invalid_raw": _int(invalid_raw),
        "suspended": _int(head.get("suspended")),
        "refunded_flag": _int(refunded_flag),
        "refunded_time": _s(raw.get("refundedTime")),
        "lifecycle_state": lifecycle,
        "sale_time": _s(head.get("sale_time")),
        "sale_date": (_s(head.get("sale_time")) or "")[:10] or None,
        "paid_time": _s(head.get("paid_time")),
        "despatch_complete_time": _s(head.get("despatch_complete_time")),
        "despatch_date": (_s(head.get("despatch_complete_time")) or "")[:10] or None,
        "updated_time": _s(head.get("updated_time")),
        "last_sync_time": _s(head.get("last_sync_time")),
        "modified": _s(head.get("modified")),
        "creation": _s(head.get("creation")),
        "warehouse_name": _s(head.get("warehouse_name")),
        "package_id": _s(head.get("package_id")),
        "tracking_number": _s(head.get("tracking_number")),
        "carrier": _s(head.get("merchant_carrier_shortname")),
        "channel": _s(head.get("channel")),
        "account": _s(head.get("account")),
        "sale_account": _s(head.get("sale_account")),
        "platform_code": _s(head.get("platform_code")),
        "channel_account_en": _s(head.get("channel_account_en")),
        "order_amount": _num(head.get("order_amount")),
        "order_amount_currency": _s(head.get("order_amount_currency")),
        "fulfillment_scope": scope["fulfillment_scope"],
        "scope_evidence": scope["scope_evidence"],
        "scope_conflict": scope["scope_conflict"],
        "line_count": len(lines),
        "line_qty_total": qty_total,
        "line_count_missing_qty": sum(1 for l in lines if l["quantity"] is None),
        "line_count_embedded_component": sum(
            1 for l in lines if l["demand_kind"] == config.DSHIP_EMBEDDED
        ),
        "package_count": len(packages),
        "first_seen_at": run["started_at"],
        "last_seen_at": run["started_at"],
        "first_run_id": run["run_id"],
        "last_run_id": run["run_id"],
        "ingest_scope": run.get("ingest_scope"),
        "coverage_status": run.get("coverage_status", "complete"),
        "source": "en",
    }
    payload = _state_payload(order, lines, packages)
    order["state_hash"] = state_hash(payload)

    raw_row = {
        "en_doc_name": doc,
        "modified": order["modified"],
        "sale_time": order["sale_time"],
        # 原始 payload 按字符串保存，schema 稳定（parquet 不做嵌套推断）
        "payload": head.get("raw_data"),
        "payload_hash": hashlib.sha256(
            json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        "captured_at": run["started_at"],
        "run_id": run["run_id"],
    }
    return {"order": order, "lines": lines, "packages": packages, "raw": raw_row, "duplicates": duplicates}
