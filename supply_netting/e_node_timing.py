"""ETA 规划情景；不把独立抽样、未测交接段或 PO 计划冒充服务承诺。"""
import json

import numpy as np
import pandas as pd

from .e_nodes import cutoff
from .e_node_extra_sources import EN_CUSTOMERS

MODES = ("普船", "快船", "空运")


def timing_samples(dn, shipment, as_of):
    end = cutoff(as_of).tz_localize(None)
    start = end.normalize().replace(day=1) - pd.DateOffset(months=6)
    date = pd.to_datetime(dn.posting_date, errors="coerce")
    a = dn[date.ge(start) & date.le(end) & dn.so.notna() & pd.to_numeric(dn.lead_days, errors="coerce").ge(0)].copy()
    a = a.sort_values("posting_date").drop_duplicates(["so", "customer"])
    production = {EN_CUSTOMERS[c]: x.lead_days.astype(float).to_numpy()
                  for c, x in a.groupby("customer") if c in EN_CUSTOMERS}
    z = shipment.copy()
    dest = {"波兰": "波兰", "PL/波兰": "波兰", "POLAND": "波兰", "FBM-PL": "波兰",
            "美东": "USNJ", "USE": "USNJ", "美中": "USTX", "USM": "USTX"}
    z["customer"] = z.dest.map(dest)
    def mode(value):
        t = str(value)
        return "空运" if "空运" in t else "快船" if any(s in t for s in ["美森", "快船", "速快"]) else "普船" if "海运" in t or "普船" in t else None
    z["mode"] = z.transport.map(mode)
    delivered = pd.to_datetime(z.dlvr, errors="coerce")
    valid = delivered.notna() & delivered.le(end) & pd.to_numeric(z.full_lt, errors="coerce").gt(0)
    raw_completed = int(valid.sum())
    # 快照的 name 不是已证物理运单：去掉完全相同的里程碑签名，仍标样本独立性未证。
    signature = [c for c in ["transport", "way", "carrier", "wms_in_time", "atd", "ata", "dlvr", "dest", "full_lt"] if c in z]
    z = z[valid].drop_duplicates(signature)
    haul = {(c, m): x.full_lt.astype(float).to_numpy()
            for (c, m), x in z.dropna(subset=["customer", "mode"]).groupby(["customer", "mode"])}
    audit = dict(production_input_rows=len(dn), production_unique_so_samples=len(a),
                 production_window_start=str(start.date()), production_window_end=str(end.date()),
                 headhaul_input_rows=len(shipment), completed_rows=raw_completed,
                 completed_unique_signatures=len(z), incomplete_or_invalid_rows=len(shipment)-raw_completed,
                 headhaul_route_unmapped_rows=int(z.customer.isna().sum()),
                 limitations="completed-only survival bias; sample independence and DN-to-forwarder gap unproven; no winsorization",
                 production_n={c: len(x) for c, x in production.items()},
                 haul_n={f"{c}:{m}": len(x) for (c, m), x in haul.items()})
    return production, haul, audit


def eta_scenarios(nodes, production, haul, as_of, needs=None):
    needs = pd.DataFrame() if needs is None else needs
    if len(needs) and needs.duplicated(["sku", "customer"]).any():
        raise ValueError("duplicate SKU/customer need date")
    lookup = {(r["sku"], r["customer"]): r["need_date"] for r in needs.to_dict("records")} if len(needs) else {}
    now = cutoff(as_of).tz_localize(None).normalize()
    rng = np.random.default_rng(20261111)
    rows = []
    for r in nodes[nodes.node.eq("so_unshipped")].to_dict("records"):
        for mode in MODES:
            prod = np.asarray(production.get(r["customer"], []), dtype=float)
            transit = np.asarray(haul.get((r["customer"], mode), []), dtype=float)
            need = lookup.get((r["product_key"], r["customer"]))
            row = dict(node_id=r["node_id"], sku=r["product_key"], customer=r["customer"],
                       mode=mode, qty=r["qty"], uom=r["uom"], n_production=len(prod), n_headhaul=len(transit),
                       eta_status="unknown", eta_confidence="unknown", eta_p50=None, eta_p90=None,
                       lead_days_p50=None, lead_days_p90=None, latest_order_date=None,
                       need_date=need, review_due=str(now.date()),
                       recommended_next="核实阶段/运输方式/需要日", service_guarantee=False,
                       assumptions="independent bootstrap; completed transport only; DN→forwarder gap=0 scenario ONLY; not a joint-service validation")
            anchor = pd.to_datetime(r.get("event_at"), errors="coerce")
            if len(prod) and len(transit) and pd.notna(anchor):
                if anchor.tzinfo:
                    anchor = anchor.tz_convert("Asia/Shanghai").tz_localize(None)
                elapsed = max(0., (now-anchor).total_seconds()/86400)
                total = rng.choice(prod, 2000, replace=True) + rng.choice(transit, 2000, replace=True)
                remaining = total[total > elapsed] - elapsed
                row.update(lead_days_p50=float(np.quantile(total, .5)), lead_days_p90=float(np.quantile(total, .9)))
                if len(remaining):
                    row.update(eta_status="scenario", eta_confidence="low_scenario",
                               eta_p50=str((now+pd.Timedelta(days=float(np.quantile(remaining,.5)))).date()),
                               eta_p90=str((now+pd.Timedelta(days=float(np.quantile(remaining,.9)))).date()),
                               recommended_next="核实实际阶段/运输方式；日期仅供规划")
                else:
                    row["recommended_next"] = "已超样本交期尾部，立即核实；不回填已到货"
                if need:
                    latest = pd.Timestamp(need).normalize()-pd.Timedelta(days=row["lead_days_p90"])
                    row["latest_order_date"] = str(latest.date())
                    row["recommended_next"] = "立即复核下单/催单：情景最迟日已过" if latest<now else "按情景最迟日排程，先确认交期与需要日"
            rows.append(row)
    return pd.DataFrame(rows)


def attach_eta_evidence(nodes, evidence, as_of):
    """只接受指向现有 source_record_id 的显式时效证据，不做 SKU 模糊配运单。"""
    if not len(evidence):
        return nodes
    required = {"source_record_id", "eta", "eta_status", "evidence", "observed_at"}
    if not required <= set(evidence) or evidence.source_record_id.duplicated().any():
        raise ValueError("ETA evidence requires unique source_record_id and full evidence fields")
    if not set(evidence.source_record_id) <= set(nodes.source_record_id):
        raise ValueError("ETA evidence points to absent source record")
    result = nodes.copy()
    for r in evidence.to_dict("records"):
        observed = pd.Timestamp(r["observed_at"])
        if observed.tzinfo is None or observed > cutoff(as_of) or not str(r["evidence"]).strip():
            raise ValueError("ETA evidence observation time/proof unverified")
        if r["eta_status"] not in {"estimated", "confirmed"}:
            raise ValueError("ETA evidence status must be estimated/confirmed")
        pd.Timestamp(r["eta"])
        mask = result.source_record_id.eq(r["source_record_id"])
        if r["eta_status"] == "confirmed" and not result.loc[mask, "voucher_line_id"].notna().all():
            raise ValueError("confirmed ETA needs explicit document line; quantity remains visible regardless")
        result.loc[mask, ["eta", "eta_status", "eta_evidence"]] = [r["eta"], r["eta_status"], r["evidence"]]
    return result
