"""E 的单号互斥、未知、单位及非加法视图契约。"""
import pandas as pd
import pytest


def api():
    from supply_netting import e_nodes
    return e_nodes


def stock(**changes):
    values = dict(stock_key="WH:s1", warehouse_name="波兰-FZHPoland-covers",
                  sku="s1", available=10, intransit=6, waiting_shipment=2,
                  defects=1, snapshot_at="2026-11-10 05:00:00")
    values.update(changes)
    return pd.DataFrame([values])


def test_snapshot_balances_preserved_but_no_unproven_future_addition():
    e = api()
    out = e.stock_nodes(stock(), pd.DataFrame(), "2026-11-11T00:00:00+08:00", "test")
    assert out.set_index("node").qty.to_dict() == {
        "available": 10, "intransit_observed": 6, "waiting_observed": 2, "defects": 1}
    assert out.voucher_no.isna().all()
    assert out.counted_qty.isna().all()
    assert not out.additive_supply.any()
    assert out.eta.isna().all()
    assert out.uom_status.eq("unknown").all()


def test_same_stock_key_conflict_fails_instead_of_summing():
    e = api()
    with pytest.raises(ValueError, match="stock_key"):
        e.stock_nodes(pd.concat([stock(), stock(available=11)]), pd.DataFrame(),
                      "2026-11-11T00:00:00+08:00", "test")


def test_future_snapshot_not_leaked_into_asof():
    e = api()
    with pytest.raises(ValueError, match="future"):
        e.stock_nodes(stock(snapshot_at="2026-11-12 05:00:00"), pd.DataFrame(),
                      "2026-11-11T00:00:00+08:00", "test")


def test_mixed_warehouse_does_not_get_geographic_owner():
    e = api()
    out = e.stock_nodes(stock(warehouse_name="多渠道仓库"), pd.DataFrame(),
                        "2026-11-11T00:00:00+08:00", "test")
    assert out.customer.isna().all()
    assert not out.additive_supply.any()


def test_so_summary_is_check_only_and_promise_is_not_eta():
    e = api()
    items = pd.DataFrame([
        dict(so="SO1", item_code="PK#KS1", product_id="KS1", pool="波兰",
             warehouse="成品仓 - FZH", qty=6, transaction_date="2026-11-10",
             delivery_date="2026-12-01"),
        dict(so="SO1", item_code="PK#KS1", product_id="KS1", pool="波兰",
             warehouse="半成品仓 - FZH", qty=4, transaction_date="2026-11-10",
             delivery_date="2026-12-01")])
    summary = pd.DataFrame([dict(so="SO1", product_id="KS1", pool="波兰", qty=10)])
    out, recon = e.so_nodes(items, summary, "2026-11-11T00:00:00+08:00", "test")
    assert len(out) == 2 and out.qty.sum() == 10  # 不把汇总再加 10
    assert out.sku.eq("PK#KS1").all()  # 不去前缀混成成品
    assert out.eta.isna().all() and out.promised_at.notna().all()
    assert out.voucher_line_id.isna().all()
    assert out.destination_warehouse.eq("波兰-FZHPoland-covers").all()
    assert out.counted_qty.isna().all() and recon.delta.eq(0).all()
    summary.loc[0, "qty"] = 11
    with pytest.raises(ValueError, match="SO reconciliation"):
        e.so_nodes(items, summary, "2026-11-11T00:00:00+08:00", "test")


def test_proven_partial_document_line_is_partitioned_not_max_deduped():
    e = api()
    rows = e.partition_document_line("SO1:item1:batchA", "KS1", "波兰", "个",
                                    ordered=100, dn=60, shipped=20, received=5)
    assert {r.stage: float(r.qty) for r in rows} == {
        "unreleased": 40, "finished_waiting_shipment": 40,
        "shipped_in_transit": 15, "completed_sellable_delivery": 5}
    assert sum(r.qty for r in rows) == 100
    with pytest.raises(ValueError, match="monotone"):
        e.partition_document_line("SO1:item1", "KS1", "波兰", "套",
                                  ordered=10, dn=11, shipped=2, received=0)


def test_so_summary_combined_vouchers_are_membership_not_extra_orders():
    e = api()
    items = pd.DataFrame([dict(so=so, item_code="ND#KS1", product_id="KS1", pool="波兰",
                               warehouse="半成品仓 - FZH", qty=q, transaction_date="2026-11-10",
                               delivery_date="2026-12-01") for so, q in [("SO1", 100), ("SO2", 30)]])
    summary = pd.DataFrame([dict(so="SO1,SO2", product_id="KS1", pool="波兰", qty=130)])
    out, recon = e.so_nodes(items, summary, "2026-11-11T00:00:00+08:00", "test")
    assert set(out.voucher_no) == {"SO1", "SO2"}
    assert len(out) == 2 and out.qty.sum() == 130 and recon.delta.eq(0).all()
    # 汇总 SO 集合重叠时，不能把同一明细再归入第二组。
    bad = pd.concat([summary, pd.DataFrame([dict(so="SO1", product_id="KS1", pool="波兰", qty=100)])])
    with pytest.raises(ValueError, match="SO reconciliation"):
        e.so_nodes(items, bad, "2026-11-11T00:00:00+08:00", "test")


def test_coverage_missing_nodes_are_null_not_zero():
    e = api()
    cov = e.coverage_table(pd.DataFrame(columns=e.NODE_COLUMNS))
    missing = cov[cov.node.isin(["po_open", "wip", "dn_unshipped", "external_sold_unposted"])]
    assert len(missing) == 12
    assert missing.qty.isna().all() and missing.status.eq("unknown").all()


def test_duplicate_observation_is_rejected():
    e = api()
    a = e.stock_nodes(stock(), pd.DataFrame(), "2026-11-11T00:00:00+08:00", "test")
    with pytest.raises(ValueError, match="duplicate"):
        e.validate_nodes(pd.concat([a, a]))


def test_c_view_preserves_unknown_and_units_not_second_node_stock():
    e = api()
    c = pd.DataFrame([
        dict(product_id="KS1", pool="波兰", physical_form="成品", canonical_uom="个", **{"可发供给": 10}),
        dict(product_id="TJ#KS2", pool="波兰", physical_form="套件", canonical_uom="套", **{"可发供给": 2}),
        dict(product_id="KS3", pool="波兰", physical_form="无适用", canonical_uom="个", **{"可发供给": None})])
    out = e.available_view(c, "2026-11-11T00:00:00+08:00")
    assert out.supply_qty.isna().sum() == 1
    assert out.groupby("canonical_uom").supply_qty.sum().to_dict() == {"个": 10, "套": 2}
    assert out.non_additive_with_raw.all()


def test_missing_schema_and_nonfinite_qty_fail():
    e = api()
    with pytest.raises(ValueError, match="missing"):
        e.stock_nodes(stock().drop(columns=["defects"]), pd.DataFrame(),
                      "2026-11-11T00:00:00+08:00", "test")
    with pytest.raises(ValueError, match="finite"):
        e.stock_nodes(stock(intransit=float("inf")), pd.DataFrame(),
                      "2026-11-11T00:00:00+08:00", "test")


def test_history_readonly_future_rows_and_same_day_sources_stay_separate(tmp_path):
    import duckdb
    from supply_netting.e_node_history import load_history
    paths = []
    for filename, schema, table in [
        ("wx_inventory_history.duckdb", "wx_inventory", "observations"),
        ("pengjian_inventory_history.duckdb", "pengjian_inventory", "daily_snapshot")]:
        path = tmp_path / filename
        with duckdb.connect(str(path)) as con:
            con.execute(f"create schema {schema}")
            con.execute(f"create table {schema}.{table} as select 'a.csv' source_file, 'sha' source_sha256, "
                        "date '2026-10-01' snapshot_date, '波兰仓' warehouse_raw, 's1' sku, 10.0 available")
            con.execute(f"insert into {schema}.{table} select 'b.csv','sha2',date '2026-12-01','波兰仓','s1',20.0")
        paths.append(path)
    before = [api().digest(p) for p in paths]
    history, audits = load_history(paths, "2026-11-11T00:00:00+08:00")
    assert before == [api().digest(p) for p in paths]
    assert len(history) == 2  # 两个源同日同SKU各自保留，不求和成当前20
    assert history.warehouse.eq("波兰-FZHPoland-covers").all()
    assert not history.additive_with_current.any()
    assert [a["future_rows"] for a in audits] == [1, 1]
    assert all(a["input_rows"] == a["retained_rows"] + a["future_rows"] for a in audits)


def test_history_subwarehouse_gets_customer_but_is_not_merged_to_sellable():
    from supply_netting.e_node_history import ALIASES
    target, customer, basis = ALIASES["FZH-DANEEY-退货产品仓"]
    assert target == "FZH-DANEEY-退货产品仓" and customer == "USTX"
    assert "not_merged" in basis
