#!/usr/bin/env python
"""SC14 — Jack W1/W3 接口契约的参考实现（纯标准库，离线可跑）。

我方验收规格的可执行版本：对 W1 供应行做结构/语义校验（`validate_w1`），
并按周汇总成 W3 的 confirmed / expected / unknown 三列（`rollup`）。

设计原则（与 SC04 / SC02-R4 既有口径一致）：
  1. 未知不得写成 0：qty 未知 → qty=None + qty_status='unknown'，绝不落 0。
  2. 日期未证不得当到货：date_confidence='unknown' 的行不进 confirmed/expected，只进 unknown。
  3. 一 DN 多号不复制数量：tracking 是**一个行的列表**，qty 是批次总量；分配未知时没有分号数量。
  4. 部分到货不整单抵扣：必须拆成 received + shipped_in_transit 两行，且两行之和 = 单据总量。
  5. 外部 FBA 已签收：既不算我方在手、也不算在途。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable

STAGES = ("on_hand", "po_open", "in_production", "shipped_in_transit", "received",
          "partially_received", "unknown")
DATE_CONFIDENCE = ("confirmed", "estimated", "unknown")
SCOPES = ("in_house", "external_fba")
UOM_KNOWN = ("个", "套")

# 硬性必填（缺一个就拒收）
MUST = (
    "sku", "warehouse", "as_of_date", "stage", "doc_type", "doc_name", "doc_line",
    "qty", "uom", "event_date", "available_date", "date_confidence", "source_key",
)
# 我方消费需要、Jack 字段表里没有的（当前按“未证”降级处理，见 SC14 报告 §5）
SHOULD = ("scope", "qty_status", "allocation_known", "tracking_numbers", "batch_key")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str        # error / warning
    row: int             # -1 = 整表
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_w1(rows: Iterable[dict]) -> list[Finding]:
    """对 W1 供应行做验收校验。返回 findings；空列表 = 可接收。"""
    rows = list(rows)
    out: list[Finding] = []

    # 同批重复：同一 DN 行被按运单号复制成多行
    groups: dict[tuple, list[tuple[int, dict]]] = {}
    for i, r in enumerate(rows):
        groups.setdefault((r.get("doc_name"), r.get("doc_line")), []).append((i, r))

    for key, items in groups.items():
        if len(items) < 2:
            continue
        qs = {it[1].get("qty") for it in items}
        trk = [it[1].get("tracking_numbers") or [] for it in items]
        if len(qs) == 1 and all(len(t) == 1 for t in trk) and len({t[0] for t in trk}) == len(items):
            out.append(Finding(
                "E_DUPLICATED_QTY", "error", items[0][0],
                f"{key[0]}/{key[1]} 被按 {len(items)} 个运单号拆成 {len(items)} 行、每行 qty 相同 → "
                "数量被复制 N 倍；一 DN 多号应写成单行 + tracking_numbers 列表 + allocation_known=false"))

    for i, r in enumerate(rows):
        missing = [f for f in MUST if f not in r]
        if missing:
            out.append(Finding("E_REQUIRED", "error", i, f"缺少必填字段: {', '.join(missing)}"))
            continue
        null_keys = [k for k in ("sku", "warehouse", "stage", "doc_name", "source_key", "date_confidence")
                     if r.get(k) in (None, "")]
        if null_keys:
            out.append(Finding("E_REQUIRED_NULL", "error", i,
                               f"必填字段为 null/空: {', '.join(null_keys)}（组件行须给父 SKU 或单独 scope）"))

        stage = r["stage"]
        if stage not in STAGES:
            out.append(Finding("E_STAGE", "error", i, f"stage 不在枚举内: {stage!r}"))
        if r["date_confidence"] not in DATE_CONFIDENCE:
            out.append(Finding("E_CONFIDENCE", "error", i,
                               f"date_confidence 必须是 {DATE_CONFIDENCE}，收到 {r['date_confidence']!r}"))

        # --- 未知 ≠ 0 -------------------------------------------------
        qty, qstat = r["qty"], r.get("qty_status")
        if qty is None and qstat != "unknown":
            out.append(Finding("E_NULL_QTY_SILENT", "error", i,
                               "qty=null 但 qty_status 不是 'unknown'：未知数量不得静默留空"))
        if qstat == "unknown" and qty is not None:
            out.append(Finding("E_UNKNOWN_AS_NUMBER", "error", i,
                               f"qty_status='unknown' 却给了 qty={qty!r}；未知不得写成 0 或任何数字"))
        if not (qty is None or _is_num(qty)):
            out.append(Finding("E_QTY_TYPE", "error", i, f"qty 必须是数字或 null，收到 {qty!r}"))
        elif _is_num(qty) and qty < 0:
            out.append(Finding("E_QTY_NEGATIVE", "error", i, f"qty 为负: {qty}"))

        # --- 未知日期 ≠ 到货 ------------------------------------------
        if r["date_confidence"] == "unknown" and r["available_date"] is not None:
            out.append(Finding("E_UNKNOWN_HAS_DATE", "error", i,
                               "date_confidence='unknown' 却给了 available_date：未证日期不得当作可用日"))
        if r["date_confidence"] in ("confirmed", "estimated") and r["available_date"] is None:
            out.append(Finding("E_DATE_MISSING", "error", i,
                               f"date_confidence={r['date_confidence']} 但 available_date 为空"))
        if r["date_confidence"] == "confirmed" and stage in ("po_open", "in_production", "shipped_in_transit"):
            if not r.get("date_proof"):
                out.append(Finding("W_CONFIRMED_WITHOUT_PROOF", "warning", i,
                                   "confirmed 但未给 date_proof（单据/节点来源）：我方只能按 estimated 处理"))

        # --- 一 DN 多号 --------------------------------------------------
        trk = r.get("tracking_numbers")
        if trk is not None and not isinstance(trk, list):
            out.append(Finding("E_TRACKING_TYPE", "error", i, "tracking_numbers 必须是列表"))
        alloc = r.get("allocation_known")
        if isinstance(trk, list) and len(trk) > 1 and alloc is True:
            if r.get("tracking_qty") is None:
                out.append(Finding("E_TRACKING_ALLOC", "error", i,
                                   "声明 allocation_known=true 但没给 tracking_qty（分号数量）"))

        # --- 部分到货 ----------------------------------------------------
        recv, rem, docq = r.get("received_qty"), r.get("remaining_qty"), r.get("doc_qty")
        partial = any(v is not None for v in (recv, rem))
        if partial:
            if None in (recv, rem, docq):
                out.append(Finding("E_PARTIAL_INCOMPLETE", "error", i,
                                   "部分到货必须同时给 received_qty / remaining_qty / doc_qty"))
            elif recv + rem != docq:
                out.append(Finding("E_PARTIAL_SUM", "error", i,
                                   f"received_qty({recv}) + remaining_qty({rem}) ≠ doc_qty({docq})"))
            elif stage == "received" and qty != recv:
                out.append(Finding("E_PARTIAL_STAGE_QTY", "error", i,
                                   "stage='received' 的 qty 必须等于 received_qty（不得整单抵扣）"))
            elif stage == "shipped_in_transit" and qty != rem:
                out.append(Finding("E_PARTIAL_STAGE_QTY", "error", i,
                                   "stage='shipped_in_transit' 的 qty 必须等于 remaining_qty（不得整单抵扣）"))
            elif stage not in ("received", "shipped_in_transit", "partially_received"):
                out.append(Finding("E_PARTIAL_STAGE", "error", i,
                                   "部分到货只能出现在 received / shipped_in_transit / partially_received 上"))
        if stage == "shipped_in_transit" and _is_num(recv) and recv > 0 and rem is None:
            out.append(Finding("E_PARTIAL_AS_FULL", "error", i,
                               "已部分签收却整单记为在途：必须拆行"))
        if r.get("partial") is True and (recv is None or rem is None):
            out.append(Finding("E_PARTIAL_UNALLOCATED", "error", i,
                               "部分签收但未拆行、也未给 received_qty/remaining_qty："
                               "不得把整单当在途（分配未知必须显式）"))

        # --- 新增阶段：partially_received / unknown ----------------------
        # partially_received 只用于“分配未知”的部分签收：知道总量，但不知道
        # 已收/剩余各自落在哪；数量必须 null，不得猜一个数。
        if stage == "partially_received":
            if None in (recv, rem, docq) and not partial:
                out.append(Finding("E_PARTIAL_INCOMPLETE", "error", i,
                                   "partially_received 必须给 received_qty / remaining_qty / doc_qty"))
            if not (r.get("allocation_unknown") is True or r.get("allocation_known") is False):
                out.append(Finding("E_PARTIAL_ALLOCATION_REQUIRED", "error", i,
                                   "partially_received 只用于分配未知：必须 allocation_unknown=true "
                                   "或 allocation_known=false"))
            if qty is not None or qstat != "unknown":
                out.append(Finding("E_PARTIAL_QTY_UNKNOWN", "error", i,
                                   "partially_received 的 qty 必须为 null 且 qty_status='unknown'"))
            if r["date_confidence"] != "unknown" or r["available_date"] is not None:
                out.append(Finding("E_PARTIAL_DATE_UNKNOWN", "error", i,
                                   "partially_received 必须 date_confidence='unknown' 且 available_date=null"))

        # unknown 阶段：知道数量、但不知道处于哪一段（例如 DN 状态缺失）。
        # 数量可以是 known；但可用日必须 unknown，且不进入 confirmed/expected。
        if stage == "unknown":
            if r["date_confidence"] != "unknown" or r["available_date"] is not None:
                out.append(Finding("E_UNKNOWN_STAGE_DATE", "error", i,
                                   "stage='unknown' 必须 date_confidence='unknown' 且 available_date=null"))

        # --- 外部 FBA ----------------------------------------------------
        scope = r.get("scope")
        if scope is None:
            out.append(Finding("W_SCOPE_MISSING", "warning", i,
                               "缺 scope（in_house / external_fba）：我方无法判断是否该排除"))
        elif scope not in SCOPES:
            out.append(Finding("E_SCOPE", "error", i, f"scope 不在枚举内: {scope!r}"))

        # --- 单位 --------------------------------------------------------
        if r["uom"] not in UOM_KNOWN:
            out.append(Finding("W_UOM_UNPROVEN", "warning", i, f"uom={r['uom']!r} 不在已证单位内"))
        if r.get("uom_proven") is False:
            out.append(Finding("W_UOM_FLAG", "warning", i, "uom_proven=false：不得跨单位合计"))

    # 同一 source_key 只能出现一次（阶段互斥）
    seen: dict[str, int] = {}
    for i, r in enumerate(rows):
        k = r.get("source_key")
        if k is None:
            continue
        if k in seen:
            out.append(Finding("E_STAGE_DUP", "error", i,
                               f"source_key={k!r} 在行 {seen[k]} 与 {i} 重复出现：同一数量不得跨阶段重复计"))
        seen[k] = i
    return out


def rollup(rows: Iterable[dict], week_start: str | None = None) -> dict:
    """把 W1 供应行汇总成 W3 的三列（confirmed / expected / unknown）＋在手。

    - 外部 FBA：既不算在手、也不算在途（只登记 excluded）。
    - date_confidence=unknown：只进 unknown，**不进** confirmed / expected。
    - qty=null 的行：数量保持 null，绝不补 0。
    """
    rows = list(rows)
    opening: dict[str, float] = {}
    confirmed: list[dict] = []
    expected: list[dict] = []
    unknown: list[dict] = []
    excluded: list[dict] = []
    null_qty: list[dict] = []

    def add(store: dict[str, float], uom: str, qty: float | None):
        if qty is None:
            return
        store[uom] = store.get(uom, 0.0) + qty

    for r in rows:
        scope = r.get("scope") or "in_house"
        qty = r.get("qty")
        uom = r.get("uom")
        rec = {"sku": r.get("sku"), "warehouse": r.get("warehouse"), "stage": r.get("stage"),
               "qty": qty, "uom": uom, "available_date": r.get("available_date"),
               "date_confidence": r.get("date_confidence"), "doc_name": r.get("doc_name"),
               "tracking_numbers": r.get("tracking_numbers"), "source_key": r.get("source_key")}
        if qty is None:
            null_qty.append(rec)
        if scope == "external_fba":
            excluded.append(rec)
            continue
        if r.get("stage") in ("partially_received", "unknown"):
            # 阶段/分配未知：数量可以 known，但可用性未知，只进 unknown。
            unknown.append(rec)
            continue
        if r.get("stage") == "on_hand":
            add(opening, uom, qty)
            continue
        if r.get("stage") == "received":
            add(opening, uom, qty)          # 已入库 → 在手
            continue
        conf = r.get("date_confidence")
        if conf == "confirmed" and r.get("available_date"):
            confirmed.append(rec)
        elif conf == "estimated" and r.get("available_date"):
            expected.append(rec)
        else:
            unknown.append(rec)
    return {
        "week_start": week_start,
        "opening_by_uom": opening,
        "confirmed": confirmed,
        "expected": expected,
        "unknown": unknown,
        "excluded_external_fba": excluded,
        "null_qty": null_qty,
    }


def w3_columns(roll: dict) -> dict:
    """W3 输出的三列；数量按 uom 分列，不跨单位合计。"""
    def total(items):
        d: dict[str, float] = {}
        for it in items:
            if _is_num(it["qty"]):
                d[it["uom"]] = d.get(it["uom"], 0.0) + it["qty"]
        return d
    return {
        "supply_confirmed": total(roll["confirmed"]),
        "supply_expected": total(roll["expected"]),
        "supply_unknown": {"rows": len(roll["unknown"]),
                           "qty_known": total(roll["unknown"]),
                           "qty_null_rows": len(roll["null_qty"])},
    }


def validate_w3(rows: Iterable[dict]) -> list[Finding]:
    """W3 周表：unknown 不得被折进 confirmed/expected；demand 未知时 gap 必须 null。"""
    out: list[Finding] = []
    for i, r in enumerate(rows):
        for f in ("sku", "warehouse", "week", "supply_confirmed", "supply_expected", "supply_unknown"):
            if f not in r:
                out.append(Finding("E_REQUIRED", "error", i, f"W3 缺少必填字段: {f}"))
        for f in ("supply_confirmed", "supply_expected", "supply_unknown", "demand", "gap"):
            v = r.get(f)
            if v is not None and not isinstance(v, (dict, int, float)):
                out.append(Finding("E_W3_TYPE", "error", i, f"{f} 必须是数字/字典或 null"))
        if r.get("demand") is None and r.get("gap") not in (None, 0):
            out.append(Finding("E_GAP_WITHOUT_DEMAND", "error", i,
                               "demand 未知却给出 gap：缺口不得在需求未知时落数"))
        if r.get("confidence") is None:
            out.append(Finding("W_W3_NO_CONFIDENCE", "warning", i, "缺 confidence：无法判断该周可用性"))
    return out
