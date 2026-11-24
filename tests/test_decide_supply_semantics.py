# -*- coding: utf-8 -*-
"""外部复审反例：SO 方向、阶段重叠、PO 迟到、PO 身份。"""
import json
from pathlib import Path

import pandas as pd

from supply_copilot.decide import run


def make_pack(root: Path, q95=150.0, need_date="2026-12-10"):
    data = root / "data"
    data.mkdir(parents=True)
    d6 = pd.DataFrame([{
        "product_id": "KS1", "池": "美中USTX", "形态": "成品", "UOM": "个",
        "q95": q95, "C可发供给": 0, "en_stock在途+待发": 0, "PO追加(去重)": 0,
        "SO已下": 0, "CG可调拨抵扣": 0, "净需求95": q95, "建议动作": "补",
        "新补数量": q95, "催已有量": 0, "建议数量": q95,
        "需要日": need_date, "下单日": "2026-09-01", "路线状态": "ok",
        "动作原因": "净需求>0",
    }])
    d5 = pd.DataFrame([{
        "product_id": "KS1", "pool": "美中USTX", "physical_form": "成品",
        "canonical_uom": "个", "horizon": 97, "p50": 120.0, "q90": 140.0,
        "q95": q95, "model": "ets",
    }])
    with pd.ExcelWriter(data / "D6_v6_22.xlsx") as w:
        d6.to_excel(w, sheet_name="1_全量动作", index=False)
    with pd.ExcelWriter(data / "D5_v6_8.xlsx") as w:
        d5.to_excel(w, sheet_name="1_预测", index=False)
    with pd.ExcelWriter(data / "D3b_v3_11.xlsx") as w:
        pd.DataFrame({"pool": []}).to_excel(w, sheet_name="3_分类", index=False)
    (data / "sku_map.tsv").write_text("KS1\tTT1\tCUST\n", encoding="utf-8")
    (data / "service_policy.csv").write_text(
        "sku,pool,canonical_uom\nKS1,美中USTX,个\n", encoding="utf-8-sig")


def stock(root: Path, **rows):
    frame = pd.DataFrame(rows["rows"])
    path = root / "stock.csv"
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def base_stock(**extra):
    row = {"snapshot_date": "2026-11-24", "snapshot_at": "2026-11-24T06:00:00+08:00",
           "warehouse_name": "美中-FZH-DANEEY", "sku": "TT1", "available": 0,
           "intransit": 0, "run_id": "r1"}
    row.update(extra)
    return row


def call(root, **kwargs):
    return run(root, "USTX", "2026-11-24T09:00:00+08:00",
               pack_manifest={"version": "t", "as_of": "2026-11-24"}, **kwargs)


def test_open_branch_so_is_supply_not_demand(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[base_stock()])
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame([{"canonical_sku": "KS1", "canonical_warehouse": "美中-FZH-DANEEY",
                   "canonical_uom": "个", "quantity": 100}]).to_csv(backlog, index=False)
    po = tmp_path / "po.tsv"
    po.write_text("", encoding="utf-8")
    frame, meta = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po)
    row = frame.set_index("sku").loc["KS1"]
    assert row["demand_qty"] == 150          # SO 不加进需求
    assert row["supply_so"] == 100
    assert row["new_qty"] == 150             # 无可靠到货日的 SO 不抵扣主建议
    assert row["new_qty_if_conditional_late"] == 150
    assert row["action"] == "补"


def test_same_batch_intransit_and_po_not_doubled(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[base_stock(intransit=100)])
    po = tmp_path / "po.tsv"
    po.write_text("PO-1\tTT1\t100\t100\t美中-FZH-DANEEY\n", encoding="utf-8")
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame(columns=["canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"]).to_csv(backlog, index=False)
    frame, meta = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po)
    row = frame.set_index("sku").loc["KS1"]
    assert row["supply_expected"] == 100     # 不是 200
    assert row["new_qty"] == 50
    assert row["new_qty_if_conditional_late"] == 150


def test_late_po_not_counted_on_time(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[base_stock()])
    po = tmp_path / "po.tsv"
    po.write_text("PO-1\tTT1\t200\t200\t美中-FZH-DANEEY\t2027-12-31\n", encoding="utf-8")
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame(columns=["canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"]).to_csv(backlog, index=False)
    frame, meta = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po)
    row = frame.set_index("sku").loc["KS1"]
    assert row["supply_po"] == 200
    assert row["supply_expected"] == 0       # ETA 晚于需要日，不计按时
    assert row["new_qty"] == 150
    assert "未证按时" in (row["warnings"] or "")


def test_po_en_item_code_identity_is_accepted(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[base_stock()])
    po = tmp_path / "po.tsv"
    po.write_text("PO-1\tKS1\t100\t100\t美中-FZH-DANEEY\n", encoding="utf-8")
    _, meta = call(tmp_path, stock_path=s, po_path=po)
    assert meta["po"]["identity_missing"] == 0
    assert meta["po"]["rows"] == 1


def test_mixed_po_eta_buckets_by_line(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[base_stock()])
    po = tmp_path / "po.tsv"
    po.write_text(
        "PO-1\tTT1\t40\t40\t美中-FZH-DANEEY\t2026-12-01\n"
        "PO-2\tTT1\t60\t60\t美中-FZH-DANEEY\t2027-12-31\n", encoding="utf-8")
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame(columns=["canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"]).to_csv(backlog, index=False)
    frame, _ = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po)
    row = frame.set_index("sku").loc["KS1"]
    assert row["supply_po"] == 100
    assert row["supply_expected"] == 40       # 只计早到 40，不按最早 ETA 抵整组
    assert row["new_qty"] == 110


def test_so_delivery_date_used_when_present(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[base_stock()])
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame([{"canonical_sku": "KS1", "canonical_warehouse": "美中-FZH-DANEEY",
                   "canonical_uom": "个", "quantity": 100,
                   "delivery_date": "2026-12-01"}]).to_csv(backlog, index=False)
    po = tmp_path / "po.tsv"
    po.write_text("", encoding="utf-8")
    frame, _ = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po)
    row = frame.set_index("sku").loc["KS1"]
    assert row["supply_so"] == 100
    assert row["supply_expected"] == 100     # 按时到仓的 SO 可抵扣
    assert row["new_qty"] == 50


def test_independent_supply_scenario_reported(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[base_stock(intransit=100)])
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame([{"canonical_sku": "KS1", "canonical_warehouse": "美中-FZH-DANEEY",
                   "canonical_uom": "个", "quantity": 100,
                   "delivery_date": "2026-12-01"}]).to_csv(backlog, index=False)
    po = tmp_path / "po.tsv"
    po.write_text("PO-1\tTT1\t100\t100\t美中-FZH-DANEEY\t2026-12-01\n", encoding="utf-8")
    frame, _ = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po)
    row = frame.set_index("sku").loc["KS1"]
    assert row["supply_expected"] == 100     # 全重叠假设
    assert row["supply_independent"] == 300  # 独立供给情景
    assert row["new_qty_if_independent"] == 0


def test_cg_allocated_by_b_ownership_not_warehouse_geo(tmp_path):
    make_pack(tmp_path)
    s = stock(tmp_path, rows=[
        base_stock(),
        {**base_stock(), "warehouse_name": "WayfairCG-Cranbury仓", "available": 100},
    ])
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame(columns=["canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"]).to_csv(backlog, index=False)
    po = tmp_path / "po.tsv"
    po.write_text("", encoding="utf-8")
    frame, _ = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po)
    row = frame.set_index("sku").loc["KS1"]
    # USTX 行也能用 Cranbury 的 CG：按 B SKU 归属，不按仓库地理位置
    assert row["supply_cg"] == 100
    assert row["cg_source"] == "live_stock.cg"


def test_leadtime_snapshot_recalculates_order_date(tmp_path):
    make_pack(tmp_path, need_date="2026-12-10")
    s = stock(tmp_path, rows=[base_stock()])
    backlog = tmp_path / "backlog.csv"
    pd.DataFrame(columns=["canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"]).to_csv(backlog, index=False)
    po = tmp_path / "po.tsv"
    po.write_text("", encoding="utf-8")
    lead = tmp_path / "leadtime_snapshot_20261123.json"
    lead.write_text(json.dumps({"so_dn": {"2026_recent_6m": {
        "overall": {"p90": 10},
        "customer": {"DANEEY": {"p90": 10}}}}}, ensure_ascii=False), encoding="utf-8")
    frame, meta = call(tmp_path, stock_path=s, backlog_path=backlog, po_path=po,
                       leadtime_path=lead)
    row = frame.set_index("sku").loc["KS1"]
    assert row["order_date"] == "2026-11-30"
    assert row["date_source"].startswith("so_dn_p90")
    assert meta["leadtime"]["days"] == 10
