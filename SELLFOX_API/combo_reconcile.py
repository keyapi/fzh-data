# -*- coding: utf-8 -*-
"""Pure EN Product Bundle ↔ Sellfox combo reconciliation.

No network I/O. Used by sellfox_combo_ops.py and unit tests.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_FULL_CID = "428697-"
TJ_SERIAL_RE = re.compile(r"^TJ#.+\-\d{3}$")
HISTORICAL_SKIP_SKUS = frozenset({"FXLSSF3030"})
WRITABLE = frozenset({"create", "set_category"})
PAGE_SIZE = 50


@dataclass(frozen=True)
class BundleChild:
    item_code: str
    qty: int


@dataclass(frozen=True)
class EnBundle:
    name: str
    new_item_code: str
    new_item_code_name: str
    items: tuple[BundleChild, ...]
    item_code: str = ""
    item_name: str = ""
    item_group: str = ""


@dataclass(frozen=True)
class SellfoxCombo:
    sku: str
    name: str = ""
    is_group: str = ""
    full_cid: str = ""
    child_skus: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class PlanRow:
    sku: str
    action: str
    reason: str
    name: str = ""
    expected_children: tuple[tuple[str, int], ...] = ()
    actual_children: tuple[tuple[str, int], ...] = ()
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncPlan:
    rows: tuple[PlanRow, ...]
    counts: dict[str, int]
    input_en: int
    output_rows: int


def composition_key(
    children: Iterable[tuple[str, int] | BundleChild],
) -> tuple[tuple[str, int], ...]:
    normalized: list[tuple[str, int]] = []
    for child in children:
        if isinstance(child, BundleChild):
            normalized.append((str(child.item_code), int(child.qty)))
        else:
            normalized.append((str(child[0]), int(child[1])))
    return tuple(sorted(normalized))


def require_positive_int(qty: Any, *, label: str) -> int:
    if isinstance(qty, bool) or not isinstance(qty, int):
        raise ValueError(f"子件数量必须是正整数: {label}:{qty!r}")
    if qty <= 0:
        raise ValueError(f"子件数量必须是正整数: {label}:{qty}")
    return qty


def parse_child_specs(specs: Sequence[str]) -> tuple[tuple[str, int], ...]:
    result: list[tuple[str, int]] = []
    for spec in specs:
        raw = str(spec).strip()
        if ":" not in raw:
            raise ValueError(f"子件必须是 SKU:qty，收到: {raw!r}")
        sku, num = raw.split(":", 1)
        sku = sku.strip()
        num = num.strip()
        if not sku:
            raise ValueError(f"子件 SKU 不能为空: {raw!r}")
        try:
            qty = int(num)
        except ValueError as exc:
            raise ValueError(f"子件数量必须是整数: {raw!r}") from exc
        if str(qty) != num:
            raise ValueError(f"子件数量必须是正整数: {raw!r}")
        qty = require_positive_int(qty, label=sku)
        result.append((sku, qty))
    if not result:
        raise ValueError("至少需要一个 SKU:qty 子件")
    return tuple(result)


def parse_sellfox_children(child_skus: Any) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    for child in child_skus or []:
        if isinstance(child, Mapping):
            sku = str(child.get("sku") or "")
            num = int(child.get("num") or 0)
        else:
            sku, num = str(child[0]), int(child[1])
        rows.append((sku, num))
    return tuple(rows)


def sellfox_combo_from_row(row: Mapping[str, Any]) -> SellfoxCombo:
    return SellfoxCombo(
        sku=str(row.get("sku") or ""),
        name=str(row.get("name") or ""),
        is_group=str(row.get("isGroup") if row.get("isGroup") is not None else ""),
        full_cid=str(row.get("fullCid") or ""),
        child_skus=parse_sellfox_children(row.get("childSkus")),
    )


def _is_group(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def validate_en_bundle(bundle: EnBundle) -> tuple[str, ...]:
    problems: list[str] = []
    if not bundle.items:
        problems.append("empty_items")
    if bundle.name != bundle.new_item_code:
        problems.append("name_ne_new_item_code")
    if not bundle.item_code:
        problems.append("missing_item")
    elif bundle.item_code != bundle.new_item_code:
        problems.append("item_code_ne_new_item_code")
    if not str(bundle.new_item_code_name or "").strip():
        problems.append("missing_new_item_code_name")
    elif (
        bundle.item_name
        and bundle.item_name != bundle.new_item_code_name
    ):
        problems.append("item_name_ne_new_item_code_name")
    if not TJ_SERIAL_RE.match(bundle.name or ""):
        problems.append("invalid_tj_serial")
    serial = bundle.name[-4:] if bundle.name else ""
    if bundle.new_item_code_name and serial and not bundle.new_item_code_name.endswith(
        serial
    ):
        problems.append("name_serial_mismatch")
    if bundle.item_group and bundle.item_group != "套件#":
        problems.append("item_group_not_bundle")
    for child in bundle.items:
        if not str(child.item_code).strip():
            problems.append("empty_child_item_code")
        if int(child.qty) <= 0:
            problems.append(f"non_positive_qty:{child.item_code}")
    return tuple(problems)


def assert_combo_row(
    row: Mapping[str, Any] | None,
    *,
    sku: str,
    name: str,
    children: Sequence[tuple[str, int]],
    full_cid: str = DEFAULT_FULL_CID,
) -> tuple[str, ...]:
    if not row:
        return ("missing",)
    failures: list[str] = []
    if str(row.get("sku") or "") != sku:
        failures.append("sku")
    if not _is_group(row.get("isGroup")):
        failures.append("isGroup")
    if full_cid and str(row.get("fullCid") or "") != full_cid:
        failures.append("fullCid")
    if str(row.get("name") or "") != name:
        failures.append("name")
    actual = parse_sellfox_children(row.get("childSkus"))
    if composition_key(actual) != composition_key(children):
        failures.append("childSkus")
    return tuple(failures)


def plan_sync(
    en_bundles: Sequence[EnBundle],
    sellfox_by_sku: Mapping[str, SellfoxCombo],
    bottoms_present: set[str],
    *,
    expected_full_cid: str = DEFAULT_FULL_CID,
    skip_skus: Iterable[str] = HISTORICAL_SKIP_SKUS,
    duplicate_skus: Iterable[str] = (),
    duplicate_bottom_skus: Iterable[str] = (),
) -> SyncPlan:
    skip = set(skip_skus)
    dups = set(duplicate_skus)
    bottom_dups = set(duplicate_bottom_skus)
    rows: list[PlanRow] = []
    for bundle in en_bundles:
        sku = bundle.new_item_code or bundle.name
        expected = tuple((child.item_code, child.qty) for child in bundle.items)
        if sku in skip:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="skip_historical",
                    reason="historical_not_new_rule",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                )
            )
            continue
        problems = validate_en_bundle(bundle)
        if problems:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="blocked_en",
                    reason="en_invalid",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                    problems=problems,
                )
            )
            continue
        if sku in dups:
            combo = sellfox_by_sku.get(sku)
            rows.append(
                PlanRow(
                    sku=sku,
                    action="blocked_duplicate",
                    reason="sellfox_sku_duplicated",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                    actual_children=combo.child_skus if combo else (),
                    problems=("duplicate_sku",),
                )
            )
            continue
        combo = sellfox_by_sku.get(sku)
        missing_bottoms = tuple(
            child.item_code
            for child in bundle.items
            if child.item_code not in bottoms_present
        )
        duplicate_bottoms = tuple(
            child.item_code
            for child in bundle.items
            if child.item_code in bottom_dups
        )
        if duplicate_bottoms:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="blocked_duplicate",
                    reason="sellfox_bottom_duplicated",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                    actual_children=combo.child_skus if combo else (),
                    problems=duplicate_bottoms,
                )
            )
            continue
        if combo is None and missing_bottoms:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="blocked_bottoms",
                    reason="sellfox_bottom_missing",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                    problems=missing_bottoms,
                )
            )
            continue
        if combo is None:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="create",
                    reason="sellfox_missing",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                )
            )
            continue
        children_ok = composition_key(combo.child_skus) == composition_key(expected)
        group_ok = _is_group(combo.is_group)
        name_ok = combo.name == bundle.new_item_code_name
        if not children_ok or not group_ok or not name_ok:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="mismatch",
                    reason="composition_isGroup_or_name_differs",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                    actual_children=combo.child_skus,
                    problems=(() if children_ok else ("childSkus",))
                    + (() if group_ok else ("isGroup",))
                    + (() if name_ok else ("name",)),
                )
            )
            continue
        if expected_full_cid and combo.full_cid != expected_full_cid:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="set_category",
                    reason="category_differs",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                    actual_children=combo.child_skus,
                )
            )
            continue
        rows.append(
            PlanRow(
                sku=sku,
                action="ok",
                reason="en_sellfox_consistent",
                name=bundle.new_item_code_name,
                expected_children=expected,
                actual_children=combo.child_skus,
            )
        )
    counts = dict(Counter(row.action for row in rows))
    return SyncPlan(
        rows=tuple(rows),
        counts=counts,
        input_en=len(en_bundles),
        output_rows=len(rows),
    )


def duplicate_skus(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        sku = str(row.get("sku") or "")
        if sku:
            counts[sku] += 1
    return {sku for sku, n in counts.items() if n > 1}


def index_sellfox_combos(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, SellfoxCombo], set[str]]:
    dups = duplicate_skus(rows)
    by_sku: dict[str, SellfoxCombo] = {}
    for row in rows:
        sku = str(row.get("sku") or "")
        if not sku:
            continue
        by_sku[sku] = sellfox_combo_from_row(row)
    return by_sku, dups


def page_count(payload: Mapping[str, Any], *, page_size: int = PAGE_SIZE) -> int:
    raw_pages = payload.get("totalPage")
    if raw_pages not in (None, ""):
        try:
            pages = int(raw_pages)
            if pages > 0:
                return pages
        except (TypeError, ValueError):
            pass
    raw_total = payload.get("totalSize")
    if raw_total not in (None, ""):
        try:
            total = int(raw_total)
            if total <= 0:
                return 1
            return max(1, (total + page_size - 1) // page_size)
        except (TypeError, ValueError):
            pass
    return 1


def collect_page_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [row for row in (payload.get("rows") or []) if row.get("sku")]


def writable_actions(plan: SyncPlan) -> set[str]:
    return {row.action for row in plan.rows if row.action in WRITABLE}


def summarize_plan(plan: SyncPlan) -> dict[str, Any]:
    unmatched = [
        _row_to_dict(row)
        for row in plan.rows
        if row.action not in {"ok", "create", "set_category"}
    ]
    return {
        "input_en": plan.input_en,
        "output_rows": plan.output_rows,
        "counts": plan.counts,
        "rows": [_row_to_dict(row) for row in plan.rows],
        "unmatched": unmatched,
        "writable": sorted(writable_actions(plan)),
    }


def _row_to_dict(row: PlanRow) -> dict[str, Any]:
    data = asdict(row)
    data["expected_children"] = [list(item) for item in row.expected_children]
    data["actual_children"] = [list(item) for item in row.actual_children]
    data["problems"] = list(row.problems)
    return data
