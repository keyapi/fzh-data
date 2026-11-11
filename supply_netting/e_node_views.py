"""SKU×客户×节点的非加法观测、已证小计及客户生命周期。"""
import json
import re

import pandas as pd

from .e_nodes import cutoff, require

LIFECYCLE = {"unknown_pending", "active", "seasonal", "clearance", "discontinued", "blocked"}


def mapping_table(frame):
    require(frame, ["en_sku", "tongtool_sku", "customer_raw"], "SKU mapping")
    result = frame.copy().fillna("")
    for c in ["en_sku", "tongtool_sku", "customer_raw"]:
        result[c] = result[c].astype(str).str.strip()
    result = result[result.en_sku.ne("") & result.tongtool_sku.ne("")].drop_duplicates()
    result["en_candidates"] = result.groupby("tongtool_sku").en_sku.transform("nunique")
    result["tongtool_variants"] = result.groupby("en_sku").tongtool_sku.transform("nunique")
    result["mapping_status"] = result.en_candidates.map(lambda n: "unique" if n == 1 else "ambiguous")
    result["mapping_type"] = result.tongtool_variants.map(
        lambda n: "single_code" if n == 1 else "alias_or_parcel_unclassified")
    result["source"] = "sku_map.tsv;customer reference;not a quantity conversion"
    return result.reset_index(drop=True)


def enrich_identity(nodes, mapping):
    result = nodes.copy()
    lookup = {sku: a for sku, a in mapping.groupby("tongtool_sku", sort=False)}
    en_known = set(mapping.en_sku)
    variants = mapping.groupby("en_sku").tongtool_sku.nunique().to_dict()
    extras = []
    for r in result.to_dict("records"):
        raw = r["sku"]
        a = lookup.get(raw)
        en_source = r["node"] in {"so_unshipped", "dn_delivered_evidence"}
        candidates = [] if a is None else sorted(set(a.en_sku))
        if en_source or raw in en_known:
            en, status = raw, "en_direct"
        elif len(candidates) == 1:
            en, status = candidates[0], "unique"
        elif len(candidates) > 1:
            en, status = None, "ambiguous"
        else:
            en, status = r.get("en_item_code") or r.get("product_id"), "C_reference" if r.get("product_id") else "unmapped"
            if pd.isna(en):
                en = None
        product = en or raw  # 未映射的通途 SKU 仍是最小视图中的 SKU，不丢量。
        multi = variants.get(en, 0) > 1
        prior_link = r.get("linkage_status")
        if status == "ambiguous":
            link = "mapping_ambiguous"
        elif prior_link and not pd.isna(prior_link):
            link = prior_link
        elif r["node"] in {"available", "defects", "returns_observation", "cg_observation"}:
            link = "snapshot_unique"
        else:
            link = "export_only" if r["node"] == "so_unshipped" else "unlinked"
        # available 本身有唯一 stock_key；不要求虚构 DN。拆包裹/多候选仍不能合成成品数。
        confirm = (r["node"] == "available" and r.get("customer") in {"波兰", "USNJ", "USTX"}
                   and not multi and status != "ambiguous" and r.get("qty") is not None
                   and not pd.isna(r["qty"]) and r["qty"] >= 0 and r.get("c_bucket") != "规则排除")
        extras.append(dict(product_key=product, en_item_code=en, tongtool_sku=None if en_source else raw,
                           mapping_status=status, mapping_candidates=json.dumps(candidates, ensure_ascii=False),
                           mapping_type="alias_or_parcel_unclassified" if multi else "single_or_unmapped",
                           linkage_status=link, confirmed_qty=r["qty"] if confirm else None,
                           counted_qty=r["qty"] if confirm else None, additive_supply=confirm,
                           counting_reason="unique_snapshot_same_unit" if confirm else r.get("counting_reason"),
                           confirmation_basis="unique_snapshot_same_unit" if confirm else "overlap_or_mapping_unproven"))
    for c in extras[0] if extras else []:
        result[c] = [x[c] for x in extras]
    return result


def pack_metadata(nodes):
    result = nodes.copy()
    specs = []
    for r in result.to_dict("records"):
        raw = r["sku"]
        match = re.match(r"^(.*?)[-_](\d+)(?:PCS?|件套)$", str(raw), re.I)
        specs.append(dict(set_sku=raw if match else None,
                          base_sku=match.group(1) if match else raw,
                          pcs_per_set=int(match.group(2)) if match else None,
                          pack_basis="suffix_spec_not_quantity_multiplier" if match else "not_provided",
                          qty_basis="tongtool_pieces_user_confirmed" if str(r.get("source", "")).startswith(("EN:", "PO:"))
                                    else "source_uom_preserved"))
    for c in specs[0] if specs else []:
        result[c] = [s[c] for s in specs]
    result["pcs_per_set"] = pd.array(result["pcs_per_set"], dtype="Int64")
    return result


def quantity_views(nodes):
    require(nodes, ["product_key", "customer", "node", "qty", "uom", "confirmed_qty"], "node view")
    # 不能跨单位相加；physical_form 作为来源证据保留，观测总量本身明确非加法。
    def aggregate(keys):
        rows = []
        for key, a in nodes.groupby(keys, dropna=False, sort=True):
            if not isinstance(key, tuple):
                key = (key,)
            uncertain = a.confirmed_qty.isna() & (a.qty.isna() | a.qty.ne(0))
            rows.append(dict(zip(keys, key)) | dict(
                observed_total=a.qty.sum(min_count=1), confirmed_total=a.confirmed_qty.sum(min_count=1),
                observed_rows=len(a), unknown_qty_rows=int(a.qty.isna().sum()),
                unconfirmed_rows=int(uncertain.sum()), confirmed_complete=not uncertain.any(),
                confirmed_is_lower_bound=bool(uncertain.any()), coverage_complete=False,
                observed_non_additive=True,
                raw_skus=json.dumps(sorted(set(a.sku.dropna())), ensure_ascii=False),
                physical_forms=json.dumps(sorted(set(a.physical_form.dropna())) if "physical_form" in a else [], ensure_ascii=False),
                linkage_status=json.dumps(sorted(set(a.linkage_status.dropna())) if "linkage_status" in a else []),
                warning="观测总量可能重叠；已证量只是已覆盖来源的小计；C视图不再相加"))
        return pd.DataFrame(rows)
    return (aggregate(["product_key", "customer", "node", "uom"]),
            aggregate(["product_key", "customer", "uom"]))


def sales_evidence_from_b(b):
    require(b, ["产品键", "地区", "美国责任方", "是否需求行", "销量2026", "销量2025"], "B sales")
    out = b[b["是否需求行"].eq("Y")].copy()
    out["customer"] = out.apply(lambda r: "波兰" if r["地区"] == "PL" else
                                 {"美东USNJ": "USNJ", "美中USTX": "USTX"}.get(r["美国责任方"]), axis=1)
    out = out.rename(columns={"产品键": "sku", "销量2026": "sales_2026", "销量2025": "sales_2025"})
    out["evidence"] = "B_r10 customer demand row;2025..2026-10;annual counts;monthly-zero coverage unverified"
    return out[["sku", "customer", "sales_2026", "sales_2025", "evidence"]].drop_duplicates()


def lifecycle_table(nodes, policy, sales, as_of):
    pairs = nodes[["product_key", "customer"]].drop_duplicates()
    pairs = pairs[pairs.customer.isin(["波兰", "USNJ", "USTX"])]
    policies = {}
    if len(policy):
        require(policy, ["sku", "customer", "lifecycle_status", "evidence"], "lifecycle policy")
        if policy.duplicated(["sku", "customer"]).any() or not policy.lifecycle_status.isin(LIFECYCLE).all():
            raise ValueError("lifecycle duplicate key/invalid status")
        if policy.evidence.isna().any() or policy.evidence.astype(str).str.strip().eq("").any():
            raise ValueError("lifecycle authority requires evidence")
        policies = {(r["sku"], r["customer"]): r for r in policy.to_dict("records")}
    evidence_lookup = {(r["sku"], r["customer"]): r for r in sales.to_dict("records")} if len(sales) else {}
    rows = []
    for r in pairs.to_dict("records"):
        sku, customer = r["product_key"], r["customer"]
        p = policies.get((sku, customer), {})
        status = p.get("lifecycle_status", "unknown_pending")
        evidence, candidate = [], "unknown_pending"
        s = evidence_lookup.get((sku, customer))
        if s:
            evidence.append(s)
            if pd.notna(s.get("sales_2026")) and s["sales_2026"] > 0:
                candidate = "active_candidate"
            # 年度零/缺行不证明连续12月完整零销量，保持候选未知。
        base = re.sub(r"^(PK#|ND#|HM#|TJ#)", "", str(sku))
        family = next((x for x in ["KS0307", "KS0198"] if base == x or base.startswith(x+"-")), None)
        if family:
            pl_qty = 126 if family == "KS0307" else 93
            candidate = "active_candidate" if customer == "波兰" else (
                "dormant_candidate" if family == "KS0307" else "discontinued_candidate")
            evidence.insert(0, dict(source="user_20261111", scope="model_prefix/US_market_not_variant_sales",
                                    model=family, sales_2026=pl_qty if customer == "波兰" else 0,
                                    note="美国2026为0" if family == "KS0307" else "美国2025起为0；2024及以前有量"))
        eligible = status == "active"
        start, end = p.get("season_start"), p.get("season_end")
        if status == "seasonal":
            eligible = bool(pd.notna(start) and pd.notna(end) and
                            pd.Timestamp(start).date() <= cutoff(as_of).date() <= pd.Timestamp(end).date())
        disabled = nodes.loc[nodes.product_key.eq(sku), "en_disabled"].dropna() if "en_disabled" in nodes else pd.Series(dtype=object)
        rows.append(dict(sku=sku, customer=customer, lifecycle_status=status,
                         inferred_status=candidate, evidence_status="provisional" if evidence else "missing",
                         evidence=json.dumps(evidence, ensure_ascii=False, default=str),
                         authority_evidence=p.get("evidence"), season_start=start, season_end=end,
                         en_disabled=disabled.iloc[0] if len(disabled) and disabled.nunique()==1 else None,
                         replenishment_eligible=eligible, requires_confirmation=not bool(p), as_of=as_of))
    return pd.DataFrame(rows)
