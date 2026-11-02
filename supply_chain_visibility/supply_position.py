# -*- coding: utf-8 -*-
"""Supply position: PO creation manifests + status -> consumption table.

Rules (batch 2):

* a completed PO only closes its ``included`` lines; ``mapping_failed``,
  ``outcome_pending`` and ``error`` lines stay uncovered and keep prompting;
* partial arrival never allocates quantities to SKUs (``allocation_unknown``);
* voided POs contribute nothing; unknown status/source errors stay unknown;
* legacy POs without an audit manifest never get fabricated lines;
* inventory snapshots that already include a PO are flagged and never
  double-counted; completion after the snapshot stays visible as a delta;
* stages are mutually exclusive per identity; no cross-batch/date totals.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

SCHEMA_VERSION = "supply-position/v1"
RULE_VERSION = "2026-11-02.1"
IMPLEMENTATION_VERSION = "fzh.supply_position@2026-11-02.1"

INCLUDED = "included"
UNCLOSED_OUTCOMES = ("mapping_failed", "outcome_pending", "error")
OUTCOMES = (INCLUDED, "rule_excluded") + UNCLOSED_OUTCOMES

STATUS_STAGES = {
    "0": "po_open",
    "1": "po_partial_allocation_unknown",
    "2": "po_partial_allocation_unknown",
    "3": "po_completed",
    "4": "po_voided",
}


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return number if number.is_finite() and number >= 0 else None


def _text(value):
    return "" if value is None else str(value).strip()


@dataclass(frozen=True)
class ManifestLine:
    dn_item: str
    item_code: str
    outcome: str = INCLUDED
    qty: object = None
    uom: Optional[str] = None
    tt_sku: str = ""
    goods_detail_id: str = ""
    merged_goods_detail_id: str = ""
    contribution_qty: object = None
    reason: str = ""


@dataclass(frozen=True)
class PoManifest:
    po_code: str
    dn_name: str = ""
    source: str = "audit"          # audit | legacy
    status: Optional[str] = None
    completed_at: Optional[str] = None
    as_of: Optional[str] = None
    lines: tuple = ()
    warehouse: str = ""
    scope: str = "in_house"
    branch: str = ""


@dataclass(frozen=True)
class PoStatus:
    po_code: str
    found: bool = False
    raw_status: Optional[str] = None
    is_voided: bool = False
    as_of: Optional[str] = None
    source_status: str = "known"   # known | source_error | not_queried


@dataclass(frozen=True)
class InventoryPosition:
    sku: str
    warehouse: str
    uom: Optional[str]
    available: object = None
    as_of: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    includes_po_codes: tuple = ()
    source_status: str = "known"   # known | unavailable
    scope: str = "in_house"
    branch: str = ""
    batch_key: str = ""
    role: str = "finished"


@dataclass(frozen=True)
class DemandPosition:
    sku: str
    uom: Optional[str]
    open_qty: object = None
    warehouse: str = ""
    scope: str = "in_house"
    branch: str = ""
    source_status: str = "known"


@dataclass(frozen=True)
class ProofReceipt:
    sku: str
    warehouse: str
    uom: Optional[str]
    qty: object
    proof_type: str = ""
    receipt_identity: str = ""
    included_in_snapshot: bool = False


def _row(*, item_code, uom, warehouse, stage, qty, qty_status, source_layer,
         po_code=None, dn_item=None, scope="in_house", branch="", batch_key="",
         available_date=None, reason="", flags=()):
    return {
        "item_code": _text(item_code), "uom": _text(uom) or None,
        "warehouse": _text(warehouse), "pool": _text(warehouse),
        "scope": scope, "branch": _text(branch), "batch_key": _text(batch_key),
        "stage": stage, "qty": None if qty is None else str(qty),
        "qty_status": qty_status, "source_layer": source_layer,
        "po_code": po_code, "dn_item": dn_item,
        "available_date": available_date, "reason": reason,
        "flags": sorted(set(flags)),
    }


def _status_stage(status: PoStatus, fallback):
    if status.source_status in ("source_error", "not_queried"):
        return "po_status_unknown", "status_" + status.source_status
    if not status.found:
        return "po_status_unknown", "status_not_found"
    raw = _text(status.raw_status)
    if status.is_voided or raw == "4":
        return "po_voided", "po_voided"
    return STATUS_STAGES.get(raw, "po_status_unknown"), (
        STATUS_STAGES.get(raw) and "" or "status_unknown_raw")


def build_supply_position(manifests: Iterable[PoManifest],
                          statuses: Iterable[PoStatus] = (),
                          inventory: Iterable[InventoryPosition] = (),
                          demand: Iterable[DemandPosition] = (),
                          receipts: Iterable[ProofReceipt] = ()) -> dict:
    manifests = list(manifests)
    status_by_po = {row.po_code: row for row in statuses}
    inventory = list(inventory)
    rows = []
    legacy = []
    stage_counts = Counter()
    line_counts = Counter()

    snapshot_ok = any(item.source_status == "known" for item in inventory)
    windows = [(item.window_start, item.window_end, item.as_of)
               for item in inventory if item.source_status == "known"]
    included_po_codes = {code for item in inventory
                         for code in (item.includes_po_codes or ())}

    for manifest in manifests:
        for line in manifest.lines:
            line_counts[line.outcome if line.outcome in OUTCOMES else "error"] += 1

        if manifest.source != "audit" or not manifest.lines:
            legacy.append({
                "po_code": manifest.po_code, "dn_name": manifest.dn_name,
                "source": "legacy",
                "reason": "no_creation_audit_manifest" if manifest.source != "audit"
                          else "audit_manifest_without_lines",
                "qty": None, "qty_status": "unknown",
                "note": "legacy PO: no fabricated lines; does not block other goods",
            })
            continue

        status = status_by_po.get(manifest.po_code)
        if status is None:
            status = PoStatus(po_code=manifest.po_code,
                              found=manifest.status not in (None, ""),
                              raw_status=manifest.status,
                              source_status=("known" if manifest.status not in (None, "")
                                             else "not_queried"))
        stage, reason = _status_stage(status, manifest.status)
        in_snapshot = manifest.po_code in included_po_codes
        after_snapshot = _completed_after_snapshot(manifest, windows)

        for line in manifest.lines:
            qty = _decimal(line.contribution_qty if line.contribution_qty is not None
                           else line.qty)
            base = dict(item_code=line.item_code, uom=line.uom,
                        warehouse=manifest.warehouse,
                        scope=manifest.scope, branch=manifest.branch,
                        po_code=manifest.po_code, dn_item=line.dn_item)

            if line.outcome in UNCLOSED_OUTCOMES:
                rows.append(_row(stage="dn_goods_unclosed", qty=None,
                                 qty_status="unknown", source_layer="po_manifest",
                                 reason=line.reason or line.outcome,
                                 flags=("dn_goods_not_closed", line.outcome),
                                 **base))
                stage_counts["dn_goods_unclosed"] += 1
                continue
            if line.outcome == "rule_excluded":
                continue

            if stage == "po_voided":
                rows.append(_row(stage=stage, qty=Decimal("0"),
                                 qty_status="known", source_layer="po_manifest",
                                 reason=reason, **base))
            elif stage == "po_open":
                if in_snapshot:
                    rows.append(_row(stage="po_in_snapshot", qty=Decimal("0"),
                                     qty_status="known",
                                     source_layer="po_manifest",
                                     reason="inventory_include_declared",
                                     flags=("inventory_includes_po",), **base))
                    stage_counts["po_in_snapshot"] += 1
                    continue
                rows.append(_row(stage="po_open", qty=qty,
                                 qty_status="known" if qty is not None else "unknown",
                                 source_layer="po_manifest", **base))
            elif stage == "po_completed":
                flags = ["po_completed_assumed"]
                if after_snapshot:
                    flags.append("post_snapshot_completion")
                if not snapshot_ok:
                    flags.append("inventory_source_unavailable")
                if not in_snapshot and snapshot_ok:
                    flags.append("completed_not_in_snapshot")
                rows.append(_row(stage=stage, qty=Decimal("0"), qty_status="known",
                                 source_layer="po_manifest", reason=reason,
                                 flags=flags, **base))
            else:  # partial / status unknown
                flags = ["allocation_unknown"] if stage.startswith("po_partial") else []
                rows.append(_row(stage=stage, qty=None, qty_status="unknown",
                                 source_layer="po_manifest", reason=reason,
                                 flags=flags, **base))
            stage_counts[stage] += 1

    for item in inventory:
        qty = _decimal(item.available) if item.source_status == "known" else None
        rows.append(_row(
            item_code=item.sku, uom=item.uom, warehouse=item.warehouse,
            stage="on_hand", qty=qty,
            qty_status="known" if qty is not None else "unknown",
            source_layer="inventory_snapshot", scope=item.scope,
            branch=item.branch, batch_key=item.batch_key,
            available_date=item.as_of,
            reason="" if item.source_status == "known"
            else "inventory_source_" + item.source_status,
            flags=() if item.source_status == "known"
            else ("inventory_source_unavailable",),
        ))
        stage_counts["on_hand"] += 1

    for item in receipts:
        qty = _decimal(item.qty) if item.included_in_snapshot else None
        rows.append(_row(
            item_code=item.sku, uom=item.uom, warehouse=item.warehouse,
            stage="received_proven" if item.included_in_snapshot else "receipt_unproven",
            qty=qty,
            qty_status="known" if qty is not None else "unknown",
            source_layer="receipt_event",
            reason="" if item.included_in_snapshot else "receipt_inclusion_unproven",
        ))
        stage_counts[rows[-1]["stage"]] += 1

    demand_rows = []
    for item in demand:
        qty = _decimal(item.open_qty) if item.source_status == "known" else None
        row = _row(item_code=item.sku, uom=item.uom, warehouse=item.warehouse,
                   stage="demand", qty=qty,
                   qty_status="known" if qty is not None else "unknown",
                   source_layer="demand", scope=item.scope, branch=item.branch,
                   reason="" if item.source_status == "known"
                   else "demand_source_" + item.source_status,
                   flags=() if item.source_status == "known"
                   else ("demand_source_unavailable",))
        demand_rows.append(row)
        rows.append(row)
        stage_counts["demand"] += 1

    summary = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "manifests": len(manifests),
        "legacy_manifests": len(legacy),
        "outcomes": dict(sorted(line_counts.items())),
        "stages": dict(sorted(stage_counts.items())),
        "rows": len(rows),
        "unknown_rows": sum(1 for row in rows if row["qty_status"] == "unknown"),
        "stage_mutually_exclusive": True,
        "global_qty_total": None,
        "inventory_snapshot_available": snapshot_ok,
        "note": "Row-level consumption table; no cross-item totals; final decisions stay upstream.",
    }
    return {"rows": rows, "legacy": legacy, "summary": summary,
            "net": net_position(rows, demand_rows)}


def _completed_after_snapshot(manifest, windows):
    if not manifest.completed_at or not windows:
        return False
    completed = _text(manifest.completed_at)
    ends = [end for (_, end, _as_of) in windows if end]
    return any(completed > _text(end) for end in ends)


def filter_positions(rows, *, scope=None, branch=None, warehouse=None):
    """Filter by FBA/in-house scope, branch and warehouse (server-side)."""
    out = []
    for row in rows:
        if scope and row["scope"] != scope:
            continue
        if branch and row["branch"] != branch:
            continue
        if warehouse and row["warehouse"] != warehouse:
            continue
        out.append(row)
    return out


def net_position(rows, demand_rows=()):
    """Grouped A/B/C/D building blocks; never sums across identity keys."""
    keys = defaultdict(lambda: {
        "on_hand": Decimal("0"), "po_open": Decimal("0"),
        "in_transit": Decimal("0"), "demand": Decimal("0"),
        "unknown": 0, "post_snapshot": 0,
    })
    for row in rows:
        key = (row["item_code"], row["uom"] or "", row["warehouse"],
               row["scope"], row["branch"], row["batch_key"])
        bucket = keys[key]
        if "post_snapshot_completion" in row["flags"]:
            bucket["post_snapshot"] += 1
        qty = _decimal(row["qty"])
        if row["qty_status"] == "unknown":
            bucket["unknown"] += 1
            continue
        if row["stage"] == "on_hand":
            bucket["on_hand"] += qty or Decimal("0")
        elif row["stage"] == "po_open":
            bucket["po_open"] += qty or Decimal("0")
        elif row["stage"] in ("in_transit", "received_proven"):
            bucket["in_transit"] += qty or Decimal("0")
        elif row["stage"] == "demand":
            bucket["demand"] += qty or Decimal("0")
    out = []
    for key, bucket in sorted(keys.items()):
        net_min = bucket["on_hand"] + bucket["in_transit"] - bucket["demand"]
        net_max = net_min + bucket["po_open"]
        out.append({
            "item_code": key[0], "uom": key[1], "warehouse": key[2],
            "scope": key[3], "branch": key[4], "batch_key": key[5],
            "on_hand_qty": str(bucket["on_hand"]),
            "po_open_qty": str(bucket["po_open"]),
            "in_transit_qty": str(bucket["in_transit"]),
            "demand_qty": str(bucket["demand"]),
            "net_min_qty": str(net_min), "net_max_qty": str(net_max),
            "qty_status": "unknown" if bucket["unknown"] else "partial",
            "unknown_rows": bucket["unknown"],
            "post_snapshot_rows": bucket["post_snapshot"],
        })
    return {"rows": out, "note": "A/B/C/D building blocks; no cross-key totals."}
