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


def parse_child_specs(specs: Sequence[str]) -> tuple[tuple[str, int], ...]:
    result: list[tuple[str, int]] = []
    for spec in specs:
        sku, num = spec.split(":", 1)
        result.append((sku.strip(), int(num)))
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
    if (
        bundle.item_name
        and bundle.new_item_code_name
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
    if name and str(row.get("name") or "") != name:
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
) -> SyncPlan:
    skip = set(skip_skus)
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
        combo = sellfox_by_sku.get(sku)
        missing_bottoms = tuple(
            child.item_code
            for child in bundle.items
            if child.item_code not in bottoms_present
        )
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
        if not children_ok or not group_ok:
            rows.append(
                PlanRow(
                    sku=sku,
                    action="mismatch",
                    reason="composition_or_isGroup_differs",
                    name=bundle.new_item_code_name,
                    expected_children=expected,
                    actual_children=combo.child_skus,
                    problems=(() if children_ok else ("childSkus",))
                    + (() if group_ok else ("isGroup",)),
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
