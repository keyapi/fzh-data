import pandas as pd
import pytest


def views():
    from supply_netting import e_node_views
    return e_node_views


def node(**change):
    from supply_netting.e_nodes import _node
    result = _node(node_id="n1", sku="TT1", customer="波兰", warehouse="波兰-FZHPoland-covers",
                   node="available", qty=20, uom="个", product_id="EN1", source="EN:test",
                   source_record_id="W:TT1", source_as_of="2026-11-10", as_of="2026-11-11T23:59:59+08:00")
    result.update(change)
    return result


def test_mapping_many_to_many_is_preserved_without_multiplying_stock():
    v = views()
    mapping = v.mapping_table(pd.DataFrame([
        ["EN1", "TT1", ""], ["EN1", "TT2", ""], ["EN2", "TT2", ""]],
        columns=["en_sku", "tongtool_sku", "customer_raw"]))
    out = v.enrich_identity(pd.DataFrame([node(sku="TT2")]), mapping)
    assert len(mapping) == 3 and len(out) == 1 and out.qty.sum() == 20
    assert out.iloc[0].mapping_status == "ambiguous"
    assert out.iloc[0].linkage_status == "mapping_ambiguous"
    assert out.confirmed_qty.isna().all()


def test_document_missing_quantity_is_still_in_minimum_view():
    v = views()
    a = pd.DataFrame([node(node="so_unshipped", qty=10, confirmed_qty=None,
                           product_key="EN1", linkage_status="export_only"),
                      node(node_id="n2", node="intransit_observed", qty=20, confirmed_qty=None,
                           product_key="EN1", linkage_status="unlinked")])
    detail, total = v.quantity_views(a)
    assert detail.observed_total.sum() == 30
    assert total.iloc[0].observed_total == 30
    assert pd.isna(total.iloc[0].confirmed_total)
    assert not total.iloc[0].confirmed_complete and total.iloc[0].observed_non_additive


def test_confirmed_is_labeled_lower_bound_not_whole_supply():
    v = views()
    a = pd.DataFrame([node(confirmed_qty=20, product_key="EN1", linkage_status="snapshot_unique"),
                      node(node_id="n2", node="so_unshipped", qty=10, confirmed_qty=None,
                           product_key="EN1", linkage_status="export_only")])
    _, total = v.quantity_views(a)
    assert total.iloc[0].observed_total == 30 and total.iloc[0].confirmed_total == 20
    assert not total.iloc[0].confirmed_complete


@pytest.mark.parametrize("pcs", [1, 4, 6, 9, 12])
def test_pack_suffix_is_spec_not_quantity_multiplier(pcs):
    v = views()
    a = pd.DataFrame([node(sku=f"WALL-GREY-{pcs}PCS")])
    a = v.pack_metadata(a)
    assert a.iloc[0].pcs_per_set == pcs and a.iloc[0].base_sku == "WALL-GREY"
    assert a.iloc[0].qty == 20 and a.iloc[0].uom == "个"


def test_customer_lifecycle_does_not_inherit_disabled():
    v = views()
    a = pd.DataFrame([node(product_key="KS0307", en_disabled=True),
                      node(node_id="n2", product_key="KS0307", customer="USNJ", en_disabled=True)])
    policy = pd.DataFrame([dict(sku="KS0307", customer="波兰", lifecycle_status="active", evidence="business"),
                           dict(sku="KS0307", customer="USNJ", lifecycle_status="discontinued", evidence="business")])
    life = v.lifecycle_table(a, policy, pd.DataFrame(), "2026-11-11T23:59:59+08:00")
    life = life.set_index("customer")
    assert life.loc["波兰", "replenishment_eligible"]
    assert not life.loc["USNJ", "replenishment_eligible"]


def test_user_sales_examples_are_candidates_not_auto_lifecycle():
    v = views()
    a = pd.DataFrame([node(product_key=sku, customer=c, node_id=f"{sku}:{c}")
                      for sku in ["KS0307-KQC-26-WHITE", "KS0198-DRKQC-116-GREY"]
                      for c in ["波兰", "USNJ", "USTX"]])
    life = v.lifecycle_table(a, pd.DataFrame(), pd.DataFrame(), "2026-11-11T23:59:59+08:00")
    assert life.lifecycle_status.eq("unknown_pending").all()
    assert not life.replenishment_eligible.any()
    assert set(life[life.customer.eq("波兰")].inferred_status) == {"active_candidate"}
    assert set(life[life.customer.eq("USNJ")].inferred_status) == {"dormant_candidate", "discontinued_candidate"}
    assert life.evidence.str.contains("user_20261111").all()


def test_seasonal_requires_explicit_valid_window():
    v = views()
    a = pd.DataFrame([node(product_key="EN1")])
    policy = pd.DataFrame([dict(sku="EN1", customer="波兰", lifecycle_status="seasonal",
                                season_start="2026-12-01", season_end="2027-01-15", evidence="business")])
    life = v.lifecycle_table(a, policy, pd.DataFrame(), "2026-11-11T23:59:59+08:00")
    assert not life.iloc[0].replenishment_eligible
    policy.loc[0, "season_start"] = "2026-11-01"
    assert v.lifecycle_table(a, policy, pd.DataFrame(), "2026-11-11T23:59:59+08:00").iloc[0].replenishment_eligible


def test_timing_scenario_is_computable_but_not_confirmed():
    from supply_netting.e_node_timing import eta_scenarios
    a = pd.DataFrame([node(node="so_unshipped", event_at="2026-11-10", product_key="EN1")])
    prod = {"波兰": [10, 20, 30]}
    haul = {("波兰", "普船"): [5, 10, 15]}
    needs = pd.DataFrame([dict(sku="EN1", customer="波兰", need_date="2026-12-15")])
    result = eta_scenarios(a, prod, haul, "2026-11-11T23:59:59+08:00", needs)
    assert len(result) == 3
    sea = result[result["mode"].eq("普船")].iloc[0]
    assert pd.notna(sea.eta_p50) and pd.notna(sea.latest_order_date)
    assert sea.eta_confidence == "low_scenario" and sea.eta_status == "scenario"
    assert not sea.service_guarantee
    assert result[result["mode"].eq("空运")].eta_p50.isna().all()


def test_historical_dn_without_so_stays_observed_not_current_transit():
    from supply_netting.e_node_extra_sources import dn_nodes
    payload = dict(fetched_at_utc="2026-10-30T00:00:00Z", results=[
        dict(dn="DN1", doc=dict(name="DN1", customer="波兰公司", posting_date="2026-10-01", docstatus=1),
             items=[dict(name="line1", item_code="EN1", qty=12, uom="个", warehouse="工厂仓", so_detail=None)])])
    a = dn_nodes(payload, "2026-11-11T23:59:59+08:00", "local")
    assert len(a) == 1 and a.iloc[0].qty == 12
    assert a.iloc[0].node == "dn_delivered_evidence"
    assert a.iloc[0].voucher_no == "DN1" and not a.iloc[0].additive_supply
    assert a.iloc[0].linkage_status == "document_line_proven_SO_unlinked"
