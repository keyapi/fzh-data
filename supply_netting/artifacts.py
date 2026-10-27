# -*- coding: utf-8 -*-
"""把净额结果落成「同一底层事实」：Parquet + manifest + 人工审核工作簿。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .demand import NETTING_KEY, sha256_of

SCHEMA_VERSION = "supply-netting-v1"
RULE_VERSION = "netting-rules-2026-10-27"
DATE_ADAPTER_RULE = "day-level dates placed at 00:00 in the as_of timezone; recorded here, not assumed downstream"


def _rows_frame(net_result) -> pd.DataFrame:
    records = []
    for target in net_result["targets"]:
        sku, warehouse, uom = target["key"]
        for row in target["rows"]:
            records.append(dict(
                canonical_sku=sku, canonical_warehouse=warehouse, canonical_uom=uom,
                scenario=row["scenario"], bucket_id=row["bucket_id"],
                opening=row["opening"], receipts=row["receipts"], demand=row["demand"],
                fulfilled=row["fulfilled"], closing=row["closing"], unserved=row["unserved"],
                gap=row["gap"], conditional_receipts=row["conditional_receipts"],
                has_unresolved=row["has_unresolved"], supply_evidence=row["supply_evidence"],
                status=row["status"], unknown_reason=row.get("unknown_reason"),
            ))
    return pd.DataFrame(records)


def _facts_frame(net_result, evidence: list[dict]) -> pd.DataFrame:
    records = []
    for target in net_result["targets"]:
        sku, warehouse, uom = target["key"]
        for fact in target.get("opening_facts", ()):
            record = dict(fact)
            record.update(canonical_sku=sku, canonical_warehouse=warehouse, canonical_uom=uom,
                          scenario="any")
            records.append(record)
        for scenario, payload in target["scenarios"].items():
            for fact in payload["facts"]:
                record = dict(fact)
                record.update(canonical_sku=sku, canonical_warehouse=warehouse, canonical_uom=uom,
                              scenario=scenario)
                records.append(record)
    for fact in evidence:
        record = dict(fact)
        record.update(canonical_sku=None, canonical_warehouse=fact.get("warehouse"),
                      canonical_uom=fact.get("uom"), scenario="any")
        records.append(record)
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    return frame


def _summary_frame(net_result) -> pd.DataFrame:
    records = []
    for target in net_result["targets"]:
        sku, warehouse, uom = target["key"]
        expected = {r["bucket_id"]: r for r in target["rows"] if r["scenario"] == "expected"}
        conservative = {r["bucket_id"]: r for r in target["rows"] if r["scenario"] == "conservative"}
        if not expected:
            continue
        protect = expected.get("protect", {})
        last = list(expected.values())[-1]
        cond = expected.get("protect", {}).get("conditional_receipts")
        status = protect.get("status")
        records.append(dict(
            canonical_sku=sku, canonical_warehouse=warehouse, canonical_uom=uom,
            opening=target["opening"],
            protect_demand=_num(protect.get("demand")),
            protect_gap=_num(protect.get("gap")),
            horizon_unserved=_num(last.get("unserved")),
            conservative_protect_gap=_num(conservative.get("protect", {}).get("gap")),
            conditional_supply_qty=_num(cond),
            status=status,
            needs_review={
                "unknown": "无库存基准：该仓/物料在最新快照里没有行，按未知保留，不填 0",
                "conditional": "供应来源未齐或有未知 ETA：缺口为情景值，需核实",
            }.get(status, ""),
            demand_before_as_of=_num(target["demand_hidden_qty"]),
        ))
    return pd.DataFrame(records)


def _num(value):
    return None if value is None else float(value)


def _third_party_frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["canonical_sku", "canonical_warehouse", "canonical_uom",
                                     "quantity", "replenishment_owner", "note"])
    frame = pd.DataFrame([dict(
        canonical_sku=r["canonical_sku"], canonical_warehouse=r["canonical_warehouse"],
        canonical_uom=r["canonical_uom"], quantity=float(r["quantity"]),
        replenishment_owner="unknown",
        note="3PL/代发需求保留，不并入自发货净额；补货责任未定",
    ) for r in rows])
    return frame.groupby(["canonical_sku", "canonical_warehouse", "canonical_uom",
                          "replenishment_owner", "note"], as_index=False)["quantity"].sum()


def build_tables(net_result, evidence) -> dict[str, pd.DataFrame]:
    return {
        "supply_netting": _rows_frame(net_result),
        "supply_facts": _facts_frame(net_result, evidence),
        "replenishment_review": _summary_frame(net_result),
    }


def disposition_counts(facts: pd.DataFrame) -> dict:
    if facts.empty:
        return {}
    counted = facts.groupby(["scenario", "disposition_reason"], dropna=False).size()
    return {"|".join(map(str, key)): int(value) for key, value in counted.items()}


def write_parquet(tables: dict[str, pd.DataFrame], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, frame in tables.items():
        path = out_dir / f"{name}.parquet"
        frame.to_parquet(path, index=False, compression="zstd")
        paths[name] = str(path)
    return paths


def write_workbook(tables: dict[str, pd.DataFrame], manifest: dict, out_dir: Path) -> str:
    path = out_dir / "replenishment_review.xlsx"
    review = tables["replenishment_review"].copy()
    detail = tables["supply_netting"].copy()
    facts = tables["supply_facts"].copy()
    manifest_rows = pd.DataFrame([{"key": key, "value": _stringify(value)}
                                 for key, value in manifest.items()])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _sheet(writer, review, "补货审核")
        _sheet(writer, detail, "逐桶明细")
        _sheet(writer, facts, "供应事实去向")
        _sheet(writer, manifest_rows, "Manifest")
    return str(path)


def _sheet(writer, frame: pd.DataFrame, name: str) -> None:
    if frame.empty:
        frame = pd.DataFrame({"说明": ["本次没有行"]})
    frame.to_excel(writer, sheet_name=name, index=False)
    sheet = writer.sheets[name]
    for index, column in enumerate(frame.columns, start=1):
        width = max(10, min(46, max([len(str(column))] + [len(str(v)) for v in frame[column].head(200)]) + 2))
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    sheet.freeze_panes = "A2"


def _stringify(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_manifest(manifest: dict, out_dir: Path) -> str:
    for name, path in list(manifest.get("outputs", {}).items()):
        if Path(path).exists():
            manifest["outputs"][name + "_sha256"] = sha256_of(path)
    path = out_dir / "supply_netting_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(path)


def base_manifest(*, as_of: datetime, buckets, demand_meta: dict, blocked_meta: dict,
                  stock_meta: dict, po_meta: dict, backlog_meta: dict, extra: dict) -> dict:
    return dict(
        schema_version=SCHEMA_VERSION, rules_version=RULE_VERSION,
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        as_of=as_of.isoformat(),
        buckets=[dict(bucket_id=b.bucket_id, start=b.start.isoformat(), end=b.end.isoformat())
                 for b in buckets],
        scenarios=dict(
            conservative="只计已证 B_min 供应（保守）",
            expected="计入 B_max 供应，按当前预计可售日（条件情景）",
        ),
        date_adapter_rule=DATE_ADAPTER_RULE,
        inputs=dict(demand_netting=demand_meta, demand_blocked=blocked_meta,
                    inventory_snapshot=stock_meta, po_open=po_meta, backlog=backlog_meta),
        contract=dict(
            demand_source="demand_netting.parquet only",
            demand_canonical_participates=False,
            demand_blocked_participates=False,
            demand_four_key=NETTING_KEY,
            default_series_uses="quantity_default",
            in_default_series_vs_netting_allowed="separate fields; never substituted",
            supply_row="supply_chain_visibility.supply_row.SupplyRow",
            overlap_gates="supply_chain_visibility.overlap_gates.apply_overlap_gates",
            receipt_buckets="supply_chain_visibility.receipt_buckets.bucket_receipts (from b08acc05)",
            ledger_math="bucket_gaps / assert_bucket_identities / allocate_so (from aa93773b forward_net)",
        ),
        **extra,
    )


def sha256_text(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return hashlib.sha256(p.read_bytes()).hexdigest()
