# -*- coding: utf-8 -*-
"""盈利审计核心：稳定行身份 / 订单·包裹·成品件·行 grain / 数量对账（U2）。

原则（plan KTD3 / R11–R15 / R17）：
- **保留原始行身份**：每行带 `(source_sheet, source_row_number)`；业务键只用来**派生**视图，
  绝不按 Excel 行位置拼接。
- **重复值不重复计**：订单级字段（如订单总售价/总成本）在订单视图里只取一次，
  但每一行原始值仍在行级血缘里可见。
- **件数沿用既有规则**：复用 `order_side_input.count_pieces`，不重造。
- 纯函数，不联网。
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from tongtool_order_cost.order_side_input import (
    Item,
    count_pieces,
    is_cover,
    is_part,
    order_base,
)

# 原始表 / 写回表通用列名
ORDER_COL = "订单号"
SKU_COL = "通途SKU"
PLATFORM_SKU_COL = "平台SKU"
QTY_COL = "发货数量"
PACKAGE_COL = "包裹号"
WAREHOUSE_COL = "发货仓库"
ACCOUNT_COL = "渠道账号"

# 业务键：订单级明细表（非 FBA）
DEFAULT_BUSINESS_KEYS = (ORDER_COL, PACKAGE_COL, SKU_COL, PLATFORM_SKU_COL)
# 业务键：FBA 是按 MSKU 汇总的表（**没有订单行/包裹**）
FBA_BUSINESS_KEYS = ("MSKU", "SKU", "站点")

# 行处置口径
MATCHED = "matched"
UNMATCHED = "unmatched"
FAILED = "failed"
EXCLUDED = "excluded"


def load_snapshot_csv(path: Path | str) -> tuple[list[str], list[list[str]]]:
    """读回快照 CSV（U1 落盘格式：utf-8-sig，首行表头）。离线分析只吃它。"""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        rows = [row for row in csv.reader(fh)]
    if not rows:
        return [], []
    return [str(h) for h in rows[0]], [list(r) for r in rows[1:]]


def _first_index(headers: Sequence[str], column: str) -> int:
    for i, h in enumerate(headers):
        if str(h).strip() == column:
            return i
    return -1


@dataclass(frozen=True)
class LineageKey:
    source_sheet: str
    source_row: int
    occurrence_index: int
    order_id: str
    base_order_id: str
    package_id: str
    tongtool_sku: str
    platform_sku: str
    ambiguous: bool
    incomplete: bool


@dataclass(frozen=True)
class SourceRow:
    """一行原始数据，保留全部单元格与稳定身份。"""

    source_sheet: str
    row_number: int          # 表内数据行号（表头=1，数据从 2 起）
    headers: tuple[str, ...]
    cells: tuple[str, ...]
    key: LineageKey

    def get(self, column: str) -> str:
        i = _first_index(self.headers, column)
        if i < 0 or i >= len(self.cells):
            return ""
        return str(self.cells[i]).strip()


def _norm(value: str | None) -> str:
    return str(value or "").strip()


def build_source_rows(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    source_sheet: str,
    key_columns: Sequence[str] = DEFAULT_BUSINESS_KEYS,
) -> list[SourceRow]:
    """构造带稳定身份与**确定性重复序号**的行视图。

    业务键 = `key_columns` 的取值元组（默认 订单号+包裹号+通途SKU+平台SKU；
    FBA 汇总表传 `FBA_BUSINESS_KEYS`）。同键重复行按出现顺序给
    `occurrence_index`(0,1,2…)，并标 `ambiguous=True`。
    """
    idx = {c: _first_index(headers, c) for c in key_columns}
    oi = _first_index(headers, ORDER_COL)
    si = _first_index(headers, SKU_COL)
    pi = _first_index(headers, PACKAGE_COL)
    psi = _first_index(headers, PLATFORM_SKU_COL)

    def cell(cells: Sequence[str], i: int) -> str:
        return _norm(cells[i]) if 0 <= i < len(cells) else ""

    seen: dict[tuple[str, ...], int] = {}
    out: list[SourceRow] = []
    for offset, cells in enumerate(rows):
        business = tuple(cell(cells, idx[c]) for c in key_columns)
        occ = seen.get(business, 0)
        seen[business] = occ + 1
        order_id = cell(cells, oi)
        sku = cell(cells, si)
        key = LineageKey(
            source_sheet=source_sheet,
            source_row=offset + 2,
            occurrence_index=occ,
            order_id=order_id,
            base_order_id=order_base(order_id),
            package_id=cell(cells, pi),
            tongtool_sku=sku,
            platform_sku=cell(cells, psi),
            ambiguous=occ > 0,
            incomplete=(order_id == "" or sku == "")
            if key_columns is DEFAULT_BUSINESS_KEYS
            else any(part == "" for part in business),
        )
        out.append(
            SourceRow(
                source_sheet=source_sheet,
                row_number=offset + 2,
                headers=tuple(str(h) for h in headers),
                cells=tuple(str(c) for c in cells),
                key=key,
            )
        )
    return out


@dataclass
class Conservation:
    input: int = 0
    matched: int = 0
    unmatched: int = 0
    failed: int = 0
    excluded: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    @property
    def closes(self) -> bool:
        return self.input == self.matched + self.unmatched + self.failed + self.excluded

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "failed": self.failed,
            "excluded": self.excluded,
            "reasons": dict(self.reasons),
            "closes": self.closes,
        }


def row_conservation(
    rows: Sequence[SourceRow],
    *,
    excluded_reason: dict[int, str] | None = None,
    failed_rows: Iterable[int] = (),
) -> Conservation:
    """input = matched + unmatched + failed + excluded_with_reason（R13）。"""
    cons = Conservation()
    failed_set = set(failed_rows)
    excluded_reason = excluded_reason or {}
    for row in rows:
        cons.input += 1
        if row.row_number in failed_set:
            cons.failed += 1
        elif row.row_number in excluded_reason:
            cons.excluded += 1
            reason = excluded_reason[row.row_number]
            cons.reasons[reason] = cons.reasons.get(reason, 0) + 1
        elif row.key.order_id == "":
            cons.unmatched += 1
        else:
            cons.matched += 1
    return cons


@dataclass
class OrderGrain:
    canonical_id: str
    order_ids: tuple[str, ...]        # 该 canonical 下的原始订单号（别名）
    row_numbers: tuple[int, ...]
    piece_count: int
    piece_rule: str
    sums: dict[str, float]
    firsts: dict[str, str]
    ambiguous: bool


def _to_float(text: str) -> float:
    t = str(text).strip().replace(",", "")
    if t in ("", "-", "nan", "None"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def order_grain(
    rows: Sequence[SourceRow],
    *,
    sum_columns: Sequence[str] = (),
    first_columns: Sequence[str] = (),
    key: str = "canonical",
) -> list[OrderGrain]:
    """按 canonical 订单（order_base）聚合。

    - `sum_columns`：真需要累加的列（如行级成本*数量）。
    - `first_columns`：订单级重复列（如订单总售价）——**只取出现的第一行一次**，
      避免在多行订单里被重复相乘。
    """
    groups: dict[str, list[SourceRow]] = {}
    for row in rows:
        cid = row.key.base_order_id if key == "canonical" else row.key.order_id
        groups.setdefault(cid, []).append(row)

    out: list[OrderGrain] = []
    for cid, group in groups.items():
        items = [
            Item(r.key.tongtool_sku, int(_to_float(r.get(QTY_COL))))
            for r in group
        ]
        pieces, rule = count_pieces(items)
        sums = {c: sum(_to_float(r.get(c)) for r in group) for c in sum_columns}
        firsts: dict[str, str] = {}
        for c in first_columns:
            firsts[c] = next((r.get(c) for r in group if r.get(c) != ""), "")
        out.append(
            OrderGrain(
                canonical_id=cid,
                order_ids=tuple(dict.fromkeys(r.key.order_id for r in group)),
                row_numbers=tuple(r.row_number for r in group),
                piece_count=pieces,
                piece_rule=rule,
                sums=sums,
                firsts=firsts,
                ambiguous=any(r.key.ambiguous for r in group),
            )
        )
    return out


@dataclass
class PackageGrain:
    order_id: str
    package_id: str
    row_numbers: tuple[int, ...]
    sums: dict[str, float]
    firsts: dict[str, str]


def package_grain(
    rows: Sequence[SourceRow],
    *,
    sum_columns: Sequence[str] = (),
    first_columns: Sequence[str] = (),
) -> list[PackageGrain]:
    """按 (订单号, 包裹号) 聚合；包裹级费用只取一次，避免按行重复。"""
    groups: dict[tuple[str, str], list[SourceRow]] = {}
    for row in rows:
        groups.setdefault((row.key.order_id, row.key.package_id), []).append(row)
    out: list[PackageGrain] = []
    for (oid, pid), group in groups.items():
        out.append(
            PackageGrain(
                order_id=oid,
                package_id=pid,
                row_numbers=tuple(r.row_number for r in group),
                sums={c: sum(_to_float(r.get(c)) for r in group) for c in sum_columns},
                firsts={
                    c: next((r.get(c) for r in group if r.get(c) != ""), "")
                    for c in first_columns
                },
            )
        )
    return out


@dataclass
class AggregateGrain:
    business_key: tuple[str, ...]
    row_numbers: tuple[int, ...]
    sums: dict[str, float]
    firsts: dict[str, str]


def aggregate_grain(
    rows: Sequence[SourceRow],
    *,
    key_columns: Sequence[str],
    sum_columns: Sequence[str] = (),
    first_columns: Sequence[str] = (),
) -> list[AggregateGrain]:
    """按任意业务键列的**取值元组**聚合（FBA 汇总表等）。"""
    groups: dict[tuple[str, ...], list[SourceRow]] = {}
    for row in rows:
        bkey = tuple(row.get(c) for c in key_columns)
        groups.setdefault(bkey, []).append(row)
    out: list[AggregateGrain] = []
    for bkey, group in groups.items():
        out.append(
            AggregateGrain(
                business_key=bkey,
                row_numbers=tuple(r.row_number for r in group),
                sums={c: sum(_to_float(r.get(c)) for r in group) for c in sum_columns},
                firsts={
                    c: next((r.get(c) for r in group if r.get(c) != ""), "")
                    for c in first_columns
                },
            )
        )
    return out


def canonical_alias_report(rows: Sequence[SourceRow]) -> dict[str, Any]:
    """原始唯一订单号 → canonical（base）的别名对账。

    每个 canonical 有 1..N 个别名（子单/补发）；`aliases` 里按首次出现顺序列出。
    """
    uniq = list(dict.fromkeys(r.key.order_id for r in rows if r.key.order_id))
    by_canon: dict[str, list[str]] = {}
    for oid in uniq:
        by_canon.setdefault(order_base(oid), []).append(oid)
    alias_only = {
        canon: ids for canon, ids in by_canon.items() if len(ids) > 1
    }
    return {
        "unique_order_ids": len(uniq),
        "canonical_orders": len(by_canon),
        "relationship_alias_orders": sum(len(ids) - 1 for ids in by_canon.values()),
        "multi_member_canonicals": alias_only,
    }


# ---------------------------------------------------------------------------
# EN 成本证据（U3）：Item / 标准采购价 / 自套 BOM —— 只读，不建不改
# ---------------------------------------------------------------------------

STANDARD_PRICE_LIST = "标准采购"

# 缺失成本证据的分类（R16/R18）
COST_NO_ITEM = "missing_item"                    # EN 里没有这个物料
COST_SELF_BOM_PRESENT = "self_bom_present"       # 已有自套 BOM → 成本应有
COST_MISSING_SELF_BOM = "missing_self_bom_candidate"  # 有采购价但没自套 BOM → 候选
COST_MISSING_PURCHASE_PRICE = "missing_purchase_price"  # 连标准采购价都没有


@dataclass(frozen=True)
class CostEvidence:
    item_code: str
    exists: bool
    standard_price: float | None = None
    price_list: str = ""
    has_active_default_bom: bool = False
    has_self_bom: bool = False
    bom_name: str = ""
    note: str = ""


def classify_cost_evidence(ev: CostEvidence) -> str:
    """把「某物料为什么没有成本数字」归类（纯函数，便于测试）。

    顺序：无物料 → 有自套 BOM → 有采购价但缺自套 BOM → 连采购价都缺。
    """
    if not ev.exists:
        return COST_NO_ITEM
    if ev.has_self_bom:
        return COST_SELF_BOM_PRESENT
    if ev.standard_price is not None:
        return COST_MISSING_SELF_BOM
    return COST_MISSING_PURCHASE_PRICE


def classify_self_bom_candidate(ev: CostEvidence) -> bool:
    """是否属于「该建自套 BOM 但没建」的候选（有采购价、无自套 BOM）。"""
    return classify_cost_evidence(ev) == COST_MISSING_SELF_BOM


def _is_self_bom(item_code: str, bom: dict) -> bool:
    """父物料 == 唯一组件物料（自套 BOM）。支持嵌套 items 与扁平 components。"""
    items = bom.get("items")
    if items:
        codes = [str(i.get("item_code") or "").strip() for i in items]
    else:
        codes = [str(c).strip() for c in (bom.get("components") or [])]
    return bool(codes) and all(c == item_code for c in codes)


class ErpnextEvidenceClient:
    """EN 只读证据客户端：订单/明细/包裹 + Item/ItemPrice/BOM 成本证据。

    **不提供**任何 create/submit/update/cancel/delete 方法。
    """

    def __init__(self, order_client) -> None:
        self._c = order_client

    # --- 订单侧 ---
    def list_orders(self, order_ids: list[str]) -> list[dict]:
        return self._c.list_orders_by_ids(order_ids, chunk_size=100)

    def list_items(self, order_ids: list[str]) -> list[dict]:
        return self._c.list_order_items_by_order_ids(order_ids, chunk_size=20)

    def list_packages(self, order_ids: list[str]) -> list[dict]:
        return self._c.list_documents(
            "Tongtool Order Package",
            ["name", "parent", "package", "tracking_number",
             "allocated_fee", "currency", "allocated_carrier_fee", "carrier_currency"],
            page_size=200,
            params={
                "parent": "Tongtool Order",
                "filters": json.dumps([["parent", "in", order_ids]], ensure_ascii=False),
            },
        )

    # --- 成本证据 ---
    def item_exists(self, item_code: str) -> bool:
        rows = self._c.list_documents(
            "Item", ["name"], page_size=1,
            params={"filters": json.dumps([["name", "=", item_code]], ensure_ascii=False)},
        )
        return bool(rows)

    def standard_purchase_price(self, item_code: str) -> float | None:
        rows = self._c.list_documents(
            "Item Price", ["name", "price_list", "price_list_rate"], page_size=5,
            params={"filters": json.dumps(
                [["item_code", "=", item_code], ["price_list", "=", STANDARD_PRICE_LIST]],
                ensure_ascii=False)},
        )
        for r in rows:
            rate = r.get("price_list_rate")
            if rate not in (None, ""):
                return float(rate)
        return None

    def bom_evidence(self, item_code: str) -> list[dict]:
        """该物料的所有 BOM，每条附带 `components`（组件物料码列表）。

        Frappe 的 `items.item_code` 会**扁平化**成顶层 `item_code`（多子件时只剩最后一个），
        所以改用 `BOM Item` 子表按 parent 精确取组件，避免误判自套 BOM。
        """
        boms = self._c.list_documents(
            "BOM",
            ["name", "item", "is_active", "is_default", "total_cost"],
            page_size=50,
            params={"filters": json.dumps([["item", "=", item_code]], ensure_ascii=False)},
        )
        out: list[dict] = []
        for b in boms:
            name = str(b.get("name") or "")
            comps = self._c.list_documents(
                "BOM Item",
                ["item_code", "qty"],
                page_size=200,
                params={"parent": "BOM", "filters": json.dumps([["parent", "=", name]], ensure_ascii=False)},
            )
            out.append({**b, "components": [str(c.get("item_code") or "").strip() for c in comps]})
        return out

    def cost_evidence(self, item_code: str) -> CostEvidence:
        exists = self.item_exists(item_code)
        if not exists:
            return CostEvidence(item_code=item_code, exists=False)
        price = self.standard_purchase_price(item_code)
        boms = self.bom_evidence(item_code)
        active_default = [b for b in boms if _truthy(b.get("is_active")) and _truthy(b.get("is_default"))]
        self_boms = [b for b in active_default if _is_self_bom(item_code, b)]
        any_self = [b for b in boms if _is_self_bom(item_code, b)]
        return CostEvidence(
            item_code=item_code,
            exists=True,
            standard_price=price,
            price_list=STANDARD_PRICE_LIST if price is not None else "",
            has_active_default_bom=bool(active_default),
            has_self_bom=bool(self_boms or any_self),
            bom_name=(self_boms or any_self or active_default or [{}])[0].get("name", ""),
        )


def _truthy(value: object) -> bool:
    return value in (1, "1", True, "true", "True", "是")


# ---------------------------------------------------------------------------
# 指标口径矩阵与复现（U4 / R6–R10）
# ---------------------------------------------------------------------------

METRIC_REPRODUCED = "reproduced"
METRIC_UNREPRODUCED = "unreproduced"
METRIC_UNDEFINED = "undefined"

# 分母类型
DEN_ROWS = "rows"
DEN_NONZERO_ROWS = "nonzero_rows"
DEN_ORDERS = "orders"
DEN_PACKAGES = "packages"
DEN_PIECES = "pieces"
DEN_COLUMN = "column"


@dataclass(frozen=True)
class MetricSpec:
    """一条指标口径。**分母必须显式**，不允许出现无标注的「平均值」。"""

    name: str
    numerator_column: str
    denominator_kind: str                 # rows|nonzero_rows|orders|packages|pieces|column
    denominator_column: str = ""
    grain: str = "row"
    track: str = "ordinary"               # ordinary | coefficient
    fba_scope: str = "non_fba"            # non_fba | fba | combined
    zero_policy: str = "include"          # include | exclude_zero


@dataclass(frozen=True)
class MetricRecord:
    name: str
    grain: str
    track: str
    fba_scope: str
    numerator_column: str
    numerator: float
    denominator_kind: str
    denominator_column: str
    denominator: float
    value: float | None
    zero_policy: str
    status: str
    filters: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "grain": self.grain,
            "track": self.track,
            "fba_scope": self.fba_scope,
            "numerator_column": self.numerator_column,
            "numerator": self.numerator,
            "denominator_kind": self.denominator_kind,
            "denominator_column": self.denominator_column,
            "denominator": self.denominator,
            "value": self.value,
            "zero_policy": self.zero_policy,
            "status": self.status,
            "filters": dict(self.filters),
        }


def _denominator_value(
    rows: Sequence[SourceRow], spec: MetricSpec, filtered: Sequence[SourceRow]
) -> float:
    kind = spec.denominator_kind
    if kind == DEN_ROWS:
        return float(len(filtered))
    if kind == DEN_NONZERO_ROWS:
        return float(sum(1 for r in filtered if _to_float(r.get(spec.numerator_column)) != 0))
    if kind == DEN_ORDERS:
        return float(len({r.key.base_order_id for r in filtered}))
    if kind == DEN_PACKAGES:
        return float(len({(r.key.order_id, r.key.package_id) for r in filtered if r.key.package_id}))
    if kind == DEN_PIECES:
        return float(
            sum(o.piece_count for o in order_grain(filtered))
        )
    if kind == DEN_COLUMN:
        return float(sum(_to_float(r.get(spec.denominator_column)) for r in filtered))
    raise ValueError(f"未知分母类型: {kind}")


def evaluate_metric(rows: Sequence[SourceRow], spec: MetricSpec) -> MetricRecord:
    """算一条指标：显式记录 分子/分母/口径/零值策略；分母为 0 → `undefined`。"""
    filtered = list(rows)
    if spec.zero_policy == "exclude_zero":
        filtered = [r for r in filtered if _to_float(r.get(spec.numerator_column)) != 0]
    numerator = float(sum(_to_float(r.get(spec.numerator_column)) for r in filtered))
    denominator = _denominator_value(rows, spec, filtered)
    if denominator == 0:
        value: float | None = None
        status = METRIC_UNDEFINED
    else:
        value = numerator / denominator
        status = "ok"
    return MetricRecord(
        name=spec.name,
        grain=spec.grain,
        track=spec.track,
        fba_scope=spec.fba_scope,
        numerator_column=spec.numerator_column,
        numerator=numerator,
        denominator_kind=spec.denominator_kind,
        denominator_column=spec.denominator_column,
        denominator=denominator,
        value=value,
        zero_policy=spec.zero_policy,
        status=status,
    )


def metric_matrix(rows: Sequence[SourceRow], specs: Sequence[MetricSpec]) -> list[MetricRecord]:
    return [evaluate_metric(rows, spec) for spec in specs]


def default_metric_specs(
    *, track: str = "ordinary", fba_scope: str = "non_fba"
) -> list[MetricSpec]:
    """7 月主指标的口径矩阵（产品成本 / 运费 / 收入 / 利润 / 利润率）。"""
    def s(name, col, kind, **kw):
        return MetricSpec(name=name, numerator_column=col, denominator_kind=kind,
                          track=track, fba_scope=fba_scope, **kw)

    return [
        s("产品成本_行均值", "1件产品成本", DEN_ROWS, grain="row"),
        s("产品成本_件均(数量加权)", "产品成本*数量", DEN_COLUMN, denominator_column="发货数量", grain="piece"),
        s("产品成本_订单均", "产品成本*数量", DEN_ORDERS, grain="order"),
        s("运费_行均值", "运费", DEN_ROWS, grain="row"),
        s("运费_包裹均", "运费", DEN_PACKAGES, grain="package"),
        s("运费_订单均", "运费", DEN_ORDERS, grain="order"),
        s("收入_行均值", "售价*汇率", DEN_ROWS, grain="row"),
        s("收入_订单均", "售价*汇率", DEN_ORDERS, grain="order"),
        s("订单总成本_行均值", "订单总成本", DEN_ROWS, grain="row"),
        s("订单利润_行均值", "订单利润", DEN_ROWS, grain="row"),
        s("毛利率", "订单利润", DEN_COLUMN, denominator_column="售价*汇率", grain="order"),
    ]


def reproduce(
    records: Sequence[MetricRecord],
    targets: dict[str, float],
    *,
    currency_tol: float = 0.01,
    rate_tol: float = 0.0001,
) -> dict[str, dict]:
    """把候选指标与「老板给的目标值」比对。

    命中 → `reproduced`；都不命中 → `unreproduced`（并列出各候选差值）；
    没有给目标值 → 不声称命中，只回 `no_target`。
    """
    out: dict[str, dict] = {}
    for name, target in targets.items():
        candidates = [r for r in records if r.name == name] or list(records)
        diffs = []
        matched = None
        for rec in candidates:
            if rec.value is None:
                continue
            diff = rec.value - target
            diffs.append({"metric": rec.name, "grain": rec.grain, "value": rec.value, "diff": diff})
            if abs(diff) <= currency_tol or (
                abs(target) > 0 and abs(diff / target) <= rate_tol
            ):
                matched = rec
                break
        out[name] = {
            "target": target,
            "status": METRIC_REPRODUCED if matched else METRIC_UNREPRODUCED,
            "matched_metric": matched.to_dict() if matched else None,
            "differences": diffs,
        }
    return out


# ---------------------------------------------------------------------------
# 异常分类器（U5 / R16–R21）
# ---------------------------------------------------------------------------

# 产品成本
COST_PRESENT = "cost_present"
COST_DILUTION = "cost_dilution"
COST_ON_ONE_LINE = "cost_on_one_line"
COST_MISSING = "cost_missing_anywhere"

# 运费
FREIGHT_ACTUAL = "freight_actual_present"
FREIGHT_ESTIMATE_ONLY = "freight_estimate_only"
FREIGHT_MISSING_BOTH = "freight_missing_both"
FREIGHT_REPEATED = "freight_repeated_across_rows"
FREIGHT_SOURCE_MISMATCH = "freight_source_mismatch"

# FBA 尾程
FBA_TAIL_SKIPPED = "fba_tail_skipped_by_design"
FBA_TAIL_NEGATIVE = "fba_tail_negative_difference"

# 置信度 / 决定人
PROVEN = "proven"
STRONG = "strong_evidence"
UNRESOLVED = "unresolved"
OWNER_TECH = "technical"
OWNER_FINANCE = "finance"
OWNER_MASTER = "master_data"


@dataclass(frozen=True)
class Finding:
    """一条可下钻到源行的异常/结论记录。"""

    category: str
    scope: str                     # order|package|row|cohort
    key: str
    severity: str
    evidence: dict
    monetary_effect: float | None
    confidence: str
    decision_owner: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "scope": self.scope,
            "key": self.key,
            "severity": self.severity,
            "evidence": dict(self.evidence),
            "monetary_effect": self.monetary_effect,
            "confidence": self.confidence,
            "decision_owner": self.decision_owner,
        }


def classify_product_cost(
    rows: Sequence[SourceRow],
    *,
    cost_col: str = "产品成本*数量",
    unit_col: str = "1件产品成本",
) -> list[Finding]:
    """按订单给「产品成本」分类：有/稀释/只落一行/全缺。

    **先判算术稀释，再判缺失**——订单成本闭合时不能因为行均低就说成本缺失。
    """
    groups: dict[str, list[SourceRow]] = {}
    for r in rows:
        groups.setdefault(r.key.base_order_id, []).append(r)
    out: list[Finding] = []
    for cid, group in groups.items():
        vals = [_to_float(r.get(cost_col)) for r in group]
        total = sum(vals)
        nonzero = sum(1 for v in vals if v != 0)
        n = len(group)
        if total == 0:
            out.append(Finding(
                category=COST_MISSING, scope="order", key=cid, severity="high",
                evidence={"rows": n, "unit_col_nonzero": sum(
                    1 for r in group if _to_float(r.get(unit_col)) != 0)},
                monetary_effect=None, confidence=PROVEN, decision_owner=OWNER_MASTER))
        elif nonzero < n:
            zero_rows = [r for r in group if _to_float(r.get(cost_col)) == 0]
            # 零成本行**全是部件/占位行** → 只是行均被稀释；否则成本孤悬在一行
            all_component = all(_is_component_row(r) for r in zero_rows)
            out.append(Finding(
                category=COST_DILUTION if all_component else COST_ON_ONE_LINE,
                scope="order", key=cid,
                severity="low" if all_component else "medium",
                evidence={"rows": n, "zero_rows": n - nonzero, "order_cost": total},
                monetary_effect=None, confidence=PROVEN, decision_owner=OWNER_TECH))
        else:
            out.append(Finding(
                category=COST_PRESENT, scope="order", key=cid, severity="info",
                evidence={"rows": n, "order_cost": total},
                monetary_effect=None, confidence=PROVEN, decision_owner=OWNER_TECH))
    return out


def _is_component_row(row: SourceRow) -> bool:
    """部件/占位行：空 SKU、皮壳行、部件行（Cover/Foam/骨架/内胆…）。"""
    sku = row.key.tongtool_sku
    name = row.get("产品名称")
    return (not sku.strip()) or is_cover(sku, name) or is_part(sku, name)


def find_repeated_package_freight(
    rows: Sequence[SourceRow], *, observed_col: str = "物流商运费"
) -> list[Finding]:
    """同一包裹多行且**运费值相同** → 逐行求和会重复计。

    `monetary_effect` = 重复多出来的金额 (n-1)*X；值不同则是按件分摊，不算重复。
    """
    groups: dict[tuple[str, str], list[SourceRow]] = {}
    for r in rows:
        if r.key.package_id:
            groups.setdefault((r.key.order_id, r.key.package_id), []).append(r)
    out: list[Finding] = []
    for (oid, pid), group in groups.items():
        nz = [_to_float(r.get(observed_col)) for r in group]
        nz = [v for v in nz if v != 0]
        if len(nz) >= 2 and len(set(nz)) == 1:
            out.append(Finding(
                category=FREIGHT_REPEATED, scope="package", key=f"{oid}|{pid}",
                severity="medium",
                evidence={"rows": len(group), "value": nz[0]},
                monetary_effect=(len(nz) - 1) * nz[0],
                confidence=PROVEN, decision_owner=OWNER_TECH))
    return out


def classify_freight(
    rows: Sequence[SourceRow],
    *,
    observed_col: str = "物流商运费",
    estimate_col: str = "通途运费",
    parcel_col: str = "包裹总运费",
) -> list[Finding]:
    """运费列的**总体**口径结论：实收/仅估算/都缺/口径不一致。

    只标口径与金额，不替换任何列；估算值不计入"实收覆盖"。
    """
    actual_rows = est_rows = missing_rows = mismatch_rows = 0
    actual_sum = est_sum = mismatch_sum = 0.0
    for r in rows:
        obs = _to_float(r.get(observed_col))
        est = _to_float(r.get(estimate_col))
        if obs != 0:
            actual_rows += 1
            actual_sum += obs
            if est != 0 and abs(obs - est) > 0.01:
                mismatch_rows += 1
                mismatch_sum += obs - est
        elif est != 0:
            est_rows += 1
            est_sum += est
        else:
            missing_rows += 1
    total = len(rows)
    return [
        Finding(FREIGHT_ACTUAL, "row", observed_col, "info",
                {"rows": actual_rows, "of": total}, actual_sum, PROVEN, OWNER_TECH),
        Finding(FREIGHT_ESTIMATE_ONLY, "row", estimate_col, "high",
                {"rows": est_rows, "of": total}, est_sum, PROVEN, OWNER_TECH),
        Finding(FREIGHT_MISSING_BOTH, "row", f"{observed_col}/{estimate_col}", "medium",
                {"rows": missing_rows, "of": total}, None, UNRESOLVED, OWNER_TECH),
        Finding(FREIGHT_SOURCE_MISMATCH, "row", f"{observed_col}-{estimate_col}", "medium",
                {"rows": mismatch_rows}, mismatch_sum, STRONG, OWNER_FINANCE),
    ]


def classify_fba_tail_reference(ref_usd: float) -> str:
    """FBA 尾程参考值：>=0 由账期承担（按设计跳过）；<0 是账期差异，应单列。"""
    return FBA_TAIL_NEGATIVE if ref_usd < 0 else FBA_TAIL_SKIPPED


def summarize_findings(findings: Sequence[Finding]) -> dict[str, dict]:
    """按类别汇总条数与金额，便于放进 00_管理摘要 / JSON。"""
    out: dict[str, dict] = {}
    for f in findings:
        row = out.setdefault(f.category, {"count": 0, "monetary_effect": 0.0, "owners": set()})
        row["count"] += 1
        if f.monetary_effect:
            row["monetary_effect"] += f.monetary_effect
        row["owners"].add(f.decision_owner)
    return {
        cat: {"count": v["count"], "monetary_effect": round(v["monetary_effect"], 2),
              "owners": sorted(v["owners"])}
        for cat, v in out.items()
    }


# ---------------------------------------------------------------------------
# 利润倒挂 / 队列可比性（U6 / R22–R24）
# ---------------------------------------------------------------------------

PROFIT_TRACK_CONFUSION = "profit_track_confusion"
PROFIT_INVERSION = "profit_inversion"
MIX_DIFFERENCE = "mix_difference"

FEE_VAT = "VAT"
FEE_CHANNEL = "渠道成交费(人民币)"
FEE_PAYPAL = "PayPal fee(人民币)"
FEE_COLUMNS = (FEE_VAT, FEE_CHANNEL, FEE_PAYPAL)


def cohort_summary(
    rows: Sequence[SourceRow],
    *,
    key_col: str,
    revenue_col: str = "售价*汇率",
    profit_col: str = "订单利润",
    extra_sum: Sequence[str] = (),
) -> list[dict]:
    """按某一维度（账号/仓库/…）汇总收入与利润，供**可比队列**使用。"""
    groups: dict[str, list[SourceRow]] = {}
    for r in rows:
        groups.setdefault(r.get(key_col), []).append(r)
    out: list[dict] = []
    for key, group in groups.items():
        rev = sum(_to_float(r.get(revenue_col)) for r in group)
        prof = sum(_to_float(r.get(profit_col)) for r in group)
        orders = len({r.key.base_order_id for r in group})
        pieces = sum(o.piece_count for o in order_grain(group))
        out.append({
            "key": key,
            "rows": len(group),
            "orders": orders,
            "pieces": pieces,
            "revenue": round(rev, 2),
            "profit": round(prof, 2),
            "margin": round(prof / rev, 4) if rev else None,
            "extra": {c: round(sum(_to_float(r.get(c)) for r in group), 2) for c in extra_sum},
        })
    return out


def profit_decomposition(rows: Sequence[SourceRow], cols: Sequence[str]) -> dict[str, float]:
    """把队列利润拆成收入 − 各成本/费用科目。"""
    return {c: round(sum(_to_float(r.get(c)) for r in rows), 2) for c in cols}


def find_profit_inversions(
    cohorts: Sequence[dict],
    *,
    min_revenue: float = 0.0,
    top: int = 20,
) -> list[Finding]:
    """找出「回款额低于整体、但毛利率高于整体」的倒挂队列（按利润降序）。

    只做**队列内可比**的陈述（同账号/同仓库/同 FBA 状态），不做跨口径硬比。
    """
    pools = [c for c in cohorts if c["revenue"] and c["margin"] is not None]
    if not pools:
        return []
    total_rev = sum(c["revenue"] for c in pools)
    total_prof = sum(c["profit"] for c in pools)
    overall_margin = total_prof / total_rev if total_rev else 0.0
    mean_rev = total_rev / len(pools)
    out: list[Finding] = []
    for c in pools:
        if c["revenue"] < mean_rev and c["margin"] > overall_margin and c["revenue"] >= min_revenue:
            out.append(Finding(
                category=PROFIT_INVERSION, scope="cohort", key=str(c["key"]),
                severity="high",
                evidence={
                    "revenue": c["revenue"], "profit": c["profit"],
                    "margin": c["margin"], "overall_margin": round(overall_margin, 4),
                    "orders": c["orders"], "rows": c["rows"],
                },
                monetary_effect=c["profit"], confidence=STRONG, decision_owner=OWNER_FINANCE))
    out.sort(key=lambda f: -(f.monetary_effect or 0))
    return out[:top]


def flag_track_confusion(
    ordinary_profit: float, coefficient_profit: float, *, tol: float = 0.01
) -> Finding | None:
    """普通轨与 `*系数` 轨利润不一致时，**两条都保留**并标口径混用风险。

    普通轨 = 售价*汇率 − 订单总成本；系数轨 = 售价*汇率 − 订单总成本*系数。
    """
    if abs(ordinary_profit - coefficient_profit) <= tol:
        return None
    return Finding(
        category=PROFIT_TRACK_CONFUSION, scope="cohort", key="ordinary-vs-coefficient",
        severity="medium",
        evidence={"ordinary_profit": round(ordinary_profit, 2),
                  "coefficient_profit": round(coefficient_profit, 2),
                  "delta": round(coefficient_profit - ordinary_profit, 2)},
        monetary_effect=round(coefficient_profit - ordinary_profit, 2),
        confidence=PROVEN, decision_owner=OWNER_FINANCE)


def zero_column_evidence(rows: Sequence[SourceRow], cols: Sequence[str]) -> list[Finding]:
    """某费用/税列**整列全零** → 不是"没发生"，而是"没进这个口径"的证据（交财务判定）。"""
    out: list[Finding] = []
    for c in cols:
        vals = [_to_float(r.get(c)) for r in rows]
        nonzero = sum(1 for v in vals if v != 0)
        if nonzero == 0:
            out.append(Finding(
                category=f"column_all_zero:{c}", scope="row", key=c, severity="high",
                evidence={"rows": len(rows), "nonzero": 0},
                monetary_effect=None, confidence=PROVEN, decision_owner=OWNER_FINANCE))
    return out


# ---------------------------------------------------------------------------
# 规则轨差异（U6 补 / 已验证口径）：表内 `*系数` 列 vs 普通列
# ---------------------------------------------------------------------------

RULE_TRACK_DELTA = "rule_track_delta"

# 普通列 ↔ 对应 `*系数` 列（同表内直接比，不依赖独立重放）
TRACK_PAIRS = (
    ("皮壳成本", "皮壳成本*系数"),
    ("二次加工成本", "二次加工成本*系数"),
    ("绍兴二次加工成本", "绍兴二次加工成本*系数"),
    ("头程运费金额", "头程运费金额"),
    ("订单总成本", "订单总成本*系数"),
    ("订单利润", "订单利润*系数"),
)


def rule_track_delta(
    rows: Sequence[SourceRow], *, pairs: Sequence[tuple[str, str]] = TRACK_PAIRS
) -> list[Finding]:
    """**用表内自带的两套列**算规则轨差异（唯一被验证过的口径）。

    独立跑 `engine_170` 会因规则快照/基线不同得到假象（实测 −116k vs 真值 +1,070），
    所以常规审计**只比表内两列**；`engine_170` 只作为交叉校验，不一致时标 unresolved。
    """
    out: list[Finding] = []
    for plain, coeff in pairs:
        if plain == coeff:
            continue
        a = sum(_to_float(r.get(plain)) for r in rows)
        b = sum(_to_float(r.get(coeff)) for r in rows)
        affected = sum(
            1 for r in rows if abs(_to_float(r.get(plain)) - _to_float(r.get(coeff))) >= 0.01
        )
        out.append(Finding(
            RULE_TRACK_DELTA, "cohort", f"{plain}->{coeff}",
            "info" if abs(b - a) < 0.01 else "medium",
            {"plain_sum": round(a, 2), "coeff_sum": round(b, 2),
             "delta": round(b - a, 2), "affected_rows": affected, "rows": len(rows)},
            round(b - a, 2), PROVEN, OWNER_FINANCE))
    return out


# ---------------------------------------------------------------------------
# 仓库口径体检：美中/海外仓的「二次加工成本来源」是否仍在借用绍兴
# ---------------------------------------------------------------------------

WAREHOUSE_COST_SOURCE_ASYMMETRY = "warehouse_cost_source_asymmetry"


def warehouse_cost_source_check(
    rows: Sequence[SourceRow],
    *,
    warehouse_col: str = "发货仓库",
    source_col: str = "二次加工成本来源编码",
    region_col: str = "发货区域",
    cost_col: str = "二次加工成本*数量",
    borrowed_sources: Sequence[str] = ("2CJG-SX",),
) -> list[Finding]:
    """体检：**非绍兴发货**却用 `2CJG-SX`（绍兴二次加工）当加工成本的行。

    这是已知历史妥协（美中/海外仓没有本地加工成本，借用绍兴）。**报出来，不自动改**。
    """
    groups: dict[tuple[str, str, str], list[SourceRow]] = {}
    for r in rows:
        src = r.get(source_col)
        if src in borrowed_sources:
            groups.setdefault((r.get(warehouse_col), src, r.get(region_col)), []).append(r)
    out: list[Finding] = []
    for (wh, src, region), group in groups.items():
        if region == "其它" and wh in ("德国", "其他仓库", "扬州仓库"):
            continue  # 真·绍兴自发货，借用是对的
        cost = sum(_to_float(r.get(cost_col)) for r in group)
        out.append(Finding(
            WAREHOUSE_COST_SOURCE_ASYMMETRY, "cohort", f"{wh}|{region}",
            "medium",
            {"warehouse": wh, "region": region, "source": src,
             "rows": len(group), "cost_sum": round(cost, 2)},
            round(cost, 2), STRONG, OWNER_MASTER))
    out.sort(key=lambda f: -(f.monetary_effect or 0))
    return out


# ---------------------------------------------------------------------------
# 分渠道成本审计（cell_222 口径）：按渠道拆成本并验恒等式
# ---------------------------------------------------------------------------

CHANNEL_COST_MISMATCH = "channel_cost_mismatch"

# cell_222 里各渠道标准成本的**定义**（普通轨）。USNJ/PL 用含包装，其余不含包装；
# 二次加工来源编码按渠道不同（USNJ=2CJG-US、PL=2CJG-PL、其余=2CJG-SX）。
CHANNEL_COST_DEFS: dict[str, dict[str, str]] = {
    "美国分公司_USNJ": {"包装": "含包装", "头程": "HEAD-US", "二次加工": "2CJG-US"},
    "美国FBA_USFBA": {"包装": "不含包装", "头程": "HEAD-USFBA", "二次加工": "2CJG-SX"},
    "美国海外仓_USHWC": {"包装": "不含包装", "头程": "HEAD-USHWC", "二次加工": "2CJG-SX"},
    "波兰分公司_PL": {"包装": "含包装", "头程": "HEAD-PL", "二次加工": "2CJG-PL"},
    "欧洲海外仓_EUHWC": {"包装": "不含包装", "头程": "HEAD-EUHWC", "二次加工": "2CJG-SX"},
    "日本FBA_JPFBA": {"包装": "不含包装", "头程": "HEAD-JPFBA", "二次加工": "2CJG-SX"},
    "绍兴自发货_SX": {"包装": "不含包装", "头程": "", "二次加工": "2CJG-SX"},
}
# ⚠️ cell_222 **只**在 `*系数` 块里定义了 `美国分公司_USTX*系数`，**没有普通口径列**
#    `美国分公司_USTX`；且它用「皮壳**不含包装**成本」，与 `美国分公司_USNJ` 的「含包装」不同。
CHANNEL_KNOWN_ISSUES = (
    "美国分公司_USTX 只有 *系数 列、没有普通列（cell_222 不一致）",
    "美国分公司_USTX*系数 用「皮壳不含包装成本」，与美国分公司_USNJ 的「含包装」不同口径",
    "*系数 渠道列里「头程」用未乘系数的列，而「皮壳/二次加工」用 *系数 列（三科目口径不一致）",
)


def channel_cost_decomposition(
    rows: Sequence[SourceRow],
    *,
    group_col: str = "发货仓按销售汇总分类",
    component_cols: Sequence[str] = ("皮壳成本*数量", "绍兴二次加工成本*数量", "二次加工成本*数量"),
    freight_col: str = "头程运费*数量",
    last_leg_col: str = "运费",
    product_cost_col: str = "产品成本*数量",
    total_cost_col: str = "订单总成本",
    tol: float = 0.01,
) -> tuple[list[dict], list[Finding]]:
    """按渠道拆产品成本/头程/尾程，并验两条恒等式。

    - `产品成本*数量 == 皮壳成本*数量 + 绍兴二次加工成本*数量 + 二次加工成本*数量`
    - `订单总成本 == 产品成本*数量 + 头程运费*数量 + 运费`

    Returns (渠道明细行, 恒等式不成立的 Finding)。
    """
    groups: dict[str, list[SourceRow]] = {}
    for r in rows:
        groups.setdefault(r.get(group_col), []).append(r)

    sheet: list[dict] = []
    findings: list[Finding] = []
    for channel, group in groups.items():
        sums = {c: round(sum(_to_float(r.get(c)) for r in group), 2) for c in component_cols}
        freight = round(sum(_to_float(r.get(freight_col)) for r in group), 2)
        last_leg = round(sum(_to_float(r.get(last_leg_col)) for r in group), 2)
        product_cost = round(sum(_to_float(r.get(product_cost_col)) for r in group), 2)
        total_cost = round(sum(_to_float(r.get(total_cost_col)) for r in group), 2)
        pieces = sum(o.piece_count for o in order_grain(group))
        comp_sum = round(sum(sums.values()), 2)
        id1 = round(product_cost - comp_sum, 2)
        id2 = round(total_cost - (product_cost + freight + last_leg), 2)
        packaging = _packaging_mode(group)
        src_codes = sorted({r.get("二次加工成本来源编码") for r in group if r.get("二次加工成本来源编码")})
        sheet.append({
            group_col: channel, "rows": len(group), "pieces": pieces,
            **sums, "产品成本*数量": product_cost,
            freight_col: freight, last_leg_col: last_leg, total_cost_col: total_cost,
            "产品成本恒等式差": id1, "订单总成本恒等式差": id2,
            "皮壳包装口径": packaging, "二次加工来源编码": ",".join(src_codes),
        })
        if abs(id1) > tol:
            findings.append(Finding(
                CHANNEL_COST_MISMATCH, "cohort", f"{channel}|产品成本", "high",
                {"product_cost": product_cost, "components_sum": comp_sum, "diff": id1},
                id1, PROVEN, OWNER_TECH))
        if abs(id2) > tol:
            findings.append(Finding(
                CHANNEL_COST_MISMATCH, "cohort", f"{channel}|订单总成本", "high",
                {"total_cost": total_cost, "recomputed": round(product_cost + freight + last_leg, 2),
                 "diff": id2},
                id2, PROVEN, OWNER_TECH))
    return sheet, findings


def _packaging_mode(group: Sequence[SourceRow]) -> str:
    """该渠道实际用的皮壳口径（含包装/不含包装）是否一致。"""
    has_inc = any(_to_float(r.get("皮壳含包装成本")) != 0 for r in group)
    has_exc = any(_to_float(r.get("皮壳不含包装成本")) != 0 for r in group)
    if has_inc and has_exc:
        return "混合"
    if has_inc:
        return "含包装"
    if has_exc:
        return "不含包装"
    return "无"
