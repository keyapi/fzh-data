# -*- coding: utf-8 -*-
"""decide 编排器测试：live 重算 / 预测缺失 / SO-PO 未知 / replay 回退。

全部离线，fixture 3 个 SKU；不依赖真实客户数据。
"""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from supply_copilot.decide import COLUMNS, run, to_report


def make_pack(root: Path):
    data = root / "data"
    data.mkdir(parents=True)
    d6 = pd.DataFrame([
        {"product_id": "KS1", "池": "美中USTX", "形态": "成品", "UOM": "个",
         "q95": 100.0, "C可发供给": 0, "en_stock在途+待发": 0, "PO追加(去重)": 0,
         "SO已下": 0, "CG可调拨抵扣": 1, "净需求95": 99, "建议动作": "补",
         "新补数量": 99, "催已有量": 0, "建议数量": 99,
         "需要日": "2027-02-16", "下单日": "2026-12-28", "路线状态": "ok",
         "动作原因": "净需求>0"},
        {"product_id": "KS2", "池": "美中USTX", "形态": "半成品", "UOM": "个",
         "q95": 10.0, "C可发供给": 0, "en_stock在途+待发": 0, "PO追加(去重)": 0,
         "SO已下": 0, "CG可调拨抵扣": 0, "净需求95": 10, "建议动作": "补",
         "新补数量": 10, "催已有量": 0, "建议数量": 10,
         "需要日": None, "下单日": None, "路线状态": "ok",
         "动作原因": "净需求>0"},
        {"product_id": "KS3", "池": "美中USTX", "形态": "成品", "UOM": "个",
         "q95": 50.0, "C可发供给": 0, "en_stock在途+待发": 0, "PO追加(去重)": 0,
         "SO已下": 0, "CG可调拨抵扣": 0, "净需求95": 50, "建议动作": "补",
         "新补数量": 50, "催已有量": 0, "建议数量": 50,
         "需要日": "2027-03-01", "下单日": "2027-01-10", "路线状态": "ok",
         "动作原因": "净需求>0"},
    ])
    d5 = pd.DataFrame([
        {"product_id": sku, "pool": "美中USTX", "physical_form": form, "canonical_uom": "个",
         "horizon": 97, "p50": q59, "q90": 0, "q95": q95, "model": "ets"}
        for sku, form, q59, q95 in [("KS1", "成品", 60.0, 100.0),
                                    ("KS2", "半成品", 8.0, 10.0),
                                    ("KS3", "成品", 30.0, 50.0)]
    ])
    d3 = pd.DataFrame({"pool": []})
    with pd.ExcelWriter(data / "D6_v6_22.xlsx") as writer:
        d6.to_excel(writer, sheet_name="1_全量动作", index=False)
    with pd.ExcelWriter(data / "D5_v6_8.xlsx") as writer:
        d5.to_excel(writer, sheet_name="1_预测", index=False)
    with pd.ExcelWriter(data / "D3b_v3_11.xlsx") as writer:
        d3.to_excel(writer, sheet_name="3_分类", index=False)

    (data / "sku_map.tsv").write_text(
        "KS1\tTT1\tCUST\nKS2\tTT2\tCUST\nKS3\tTT3\tCUST\n", encoding="utf-8")
    (data / "service_policy.csv").write_text(
        "sku,pool,canonical_uom\nKS1,美中USTX,个\nKS2,美中USTX,个\nKS3,美中USTX,个\n",
        encoding="utf-8-sig")


def make_live(root: Path):
    stock = pd.DataFrame([
        {"snapshot_date": "2026-11-23", "snapshot_at": "2026-11-23T08:00:00+08:00",
         "warehouse_name": "美中-FZH-DANEEY", "sku": "TT1", "available": 10,
         "intransit": 2, "run_id": "r1"},
        {"snapshot_date": "2026-11-23", "snapshot_at": "2026-11-23T08:00:00+08:00",
         "warehouse_name": "美中-FZH-DANEEY", "sku": "TT2", "available": 5,
         "intransit": 0, "run_id": "r1"},
        {"snapshot_date": "2026-11-23", "snapshot_at": "2026-11-23T08:00:00+08:00",
         "warehouse_name": "美中-FZH-DANEEY", "sku": "TT3", "available": 0,
         "intransit": 0, "run_id": "r1"},
        {"snapshot_date": "2026-11-23", "snapshot_at": "2026-11-23T08:00:00+08:00",
         "warehouse_name": "WayfairCG-Romeoville仓", "sku": "TT1", "available": 3,
         "intransit": 0, "run_id": "r1"},
    ])
    stock_path = root / "stock.csv"
    stock.to_csv(stock_path, index=False, encoding="utf-8")

    backlog = pd.DataFrame([
        {"canonical_sku": "KS1", "canonical_warehouse": "美中-FZH-DANEEY",
         "canonical_uom": "个", "quantity": 3},
    ])
    backlog_path = root / "backlog.csv"
    backlog.to_csv(backlog_path, index=False, encoding="utf-8")

    po_path = root / "po_open.tsv"
    po_path.write_text("PO-1\tTT1\t20\t4\t美中-FZH-DANEEY\n", encoding="utf-8")
    return stock_path, backlog_path, po_path


def _call(root, **kwargs):
    return run(root, "USTX", "2026-11-23T09:00:00+08:00",
               pack_manifest={"version": "test", "as_of": "2026-11-23"}, **kwargs)


def test_live_d6_recompute_columns_and_quantities(tmp_path):
    make_pack(tmp_path)
    stock, backlog, po = make_live(tmp_path)
    frame, meta = _call(tmp_path, stock_path=stock, backlog_path=backlog, po_path=po)

    assert meta["mode"] == "live"
    assert meta["demand_source"] == "d6_pack_q95"
    assert list(frame.columns) == COLUMNS
    assert len(frame) == 3 and frame["sku"].tolist() == ["KS1", "KS2", "KS3"]

    row = frame.set_index("sku").loc["KS1"]
    assert row["action"] == "补"
    # 需求 100（SO 不加需求、不抵扣主建议）− (期初 10 + max(在途 2, 按时 PO 0) + min(CG 3, D6 1)) = 87
    assert row["new_qty"] == 87
    assert row["cg_source"] == "live_capped_by_d6"
    # 条件供给不到时：100 − (10 + 0 + min(3,1)) = 89
    assert row["new_qty_if_conditional_late"] == 89
    assert row["demand_qty"] == 100  # SO 不加进需求
    assert row["supply_so"] == 3
    assert row["supply_cg"] == 1 and row["cg_source"] == "live_capped_by_d6"
    assert row["demand_source"] == "d6_pack_q95"
    assert row["stock_snapshot_at"] == "2026-11-23 08:00:00+08:00"
    assert len(row["so_sha256"]) == 64 and len(row["po_sha256"]) == 64
    assert str(row["source"]).startswith("live:")

    # D6 供给列被 live 数值替换，而不是沿用包内 C/PO/SO/CG
    assert row["supply_opening"] == 10 and row["supply_intransit"] == 2
    assert row["supply_po"] == 4

    # 未知日期不虚构
    ks2 = frame.set_index("sku").loc["KS2"]
    assert pd.isna(ks2["need_date"]) and pd.isna(ks2["order_date"])

    report = to_report(frame, meta)
    assert "结论：补" in report and "D6 q95" in report
    assert meta["stock"]["snapshot_at"] == "2026-11-23 08:00:00+08:00"
    assert any("预测未接入" in w for w in meta["warnings"])


def test_forecast_missing_falls_back_to_d6_with_warning(tmp_path):
    make_pack(tmp_path)
    stock, backlog, po = make_live(tmp_path)
    frame, meta = _call(tmp_path, stock_path=stock, backlog_path=backlog,
                        po_path=po, forecast_root=tmp_path / "no-forecast")

    assert meta["mode"] == "live"
    assert meta["demand_source"] == "d6_pack_q95"
    assert any("预测 CURRENT 不存在" in w or "预测未接入" in w for w in meta["warnings"])
    assert frame.set_index("sku").loc["KS1", "demand_qty"] == 100


def test_so_unknown_is_null_not_zero(tmp_path):
    make_pack(tmp_path)
    stock, _backlog, po = make_live(tmp_path)
    frame, meta = _call(tmp_path, stock_path=stock, po_path=po)

    assert meta["mode"] == "live"
    assert any("SO 未接入" in w for w in meta["warnings"])
    for _, row in frame.iterrows():
        assert row["action"] == "待核"
        assert pd.isna(row["new_qty"]) or row["new_qty"] is None
        assert "unknown_so" in row["qty_status"]
        assert pd.isna(row["supply_so"]) or row["supply_so"] is None


def test_po_unknown_is_null_not_zero(tmp_path):
    make_pack(tmp_path)
    stock, backlog, _po = make_live(tmp_path)
    frame, meta = _call(tmp_path, stock_path=stock, backlog_path=backlog)

    assert any("PO 未接入" in w for w in meta["warnings"])
    for _, row in frame.iterrows():
        assert row["action"] == "待核"
        assert pd.isna(row["new_qty"]) or row["new_qty"] is None
        assert "unknown_po" in row["qty_status"]


def test_no_live_stock_uses_replay_fallback(tmp_path):
    make_pack(tmp_path)
    frame, meta = _call(tmp_path)

    assert meta["mode"] == "replay_fallback"
    assert any("退回 D6 包 replay" in w for w in meta["warnings"])
    # 回退时数量沿用 D6 包（新补数量），不是 live 重算
    row = frame.set_index("sku").loc["KS1"]
    assert row["new_qty"] == 99 and row["action"] == "补"
    assert row["qty_status"] == "replay"
    assert row["stock_snapshot_at"] is None


def test_forecast_refresh_replaces_d6_demand(tmp_path):
    pytest.importorskip("pyarrow")
    make_pack(tmp_path)
    stock, backlog, po = make_live(tmp_path)

    forecast_root = tmp_path / "forecast"
    run_dir = forecast_root / "run-1"
    run_dir.mkdir(parents=True)
    windows = pd.DataFrame([
        {"schema_version": "en-demand-forecast-v1", "tongtool_sku": "TT1",
         "canonical_warehouse": "美中-FZH-DANEEY", "lead_days": 90,
         "window_start": "2026-11-01", "window_end": "2027-01-30", "p50": 80.0,
         "canonical_uom": "个", "netting_eligible": True, "netting_block_reason": ""},
        {"schema_version": "en-demand-forecast-v1", "tongtool_sku": "TT3",
         "canonical_warehouse": "美中-FZH-DANEEY", "lead_days": 90,
         "window_start": "2026-11-01", "window_end": "2027-01-30", "p50": 20.0,
         "canonical_uom": "个", "netting_eligible": True, "netting_block_reason": ""},
    ])
    windows_path = run_dir / "forecast_sku_warehouse_windows.parquet"
    windows.to_parquet(windows_path, index=False)
    digest = hashlib.sha256(windows_path.read_bytes()).hexdigest()
    (run_dir / "forecast_manifest.json").write_text(json.dumps({
        "schema_version": "en-demand-forecast-v1", "run_id": "run-1",
        "generated_at": "2026-11-22T10:00:00+08:00",
        "run": {"decision_date": "2026-11-22", "data_cutoff": "2026-11-21"},
        "outputs": [{"file": windows_path.name, "rows": 2, "sha256": digest}],
    }), encoding="utf-8")
    (forecast_root / "CURRENT").write_text("run-1", encoding="utf-8")

    frame, meta = _call(tmp_path, stock_path=stock, backlog_path=backlog,
                        po_path=po, forecast_root=forecast_root)

    assert meta["demand_source"] == "forecast_refresh"
    assert meta["forecast"]["run_id"] == "run-1"
    by_sku = frame.set_index("sku")
    assert by_sku.loc["KS1", "demand_qty"] == 80
    assert by_sku.loc["KS1", "d6_q95"] == 100          # D6 仅作对照
    assert by_sku.loc["KS1", "new_qty"] == 67          # 80 − (10+max(2,0)+min(3,1))
    # 预测未覆盖 KS2 → 退回 D6 q95 并标注
    assert by_sku.loc["KS2", "demand_qty"] == 10
    assert "预测未覆盖" in str(by_sku.loc["KS2", "warnings"])
    assert by_sku.loc["KS3", "new_qty"] == 20
    assert any("预测未覆盖" in w for w in [by_sku.loc["KS2", "warnings"]])


def test_requires_timezone(tmp_path):
    make_pack(tmp_path)
    with pytest.raises(ValueError, match="时区"):
        run(tmp_path, "USTX", "2026-11-23T09:00:00")


# --------------------------------------------------------------------------- #
# P0 反例：po_on_time 必须与需要日比较（不能退化成"有 ETA"）
# --------------------------------------------------------------------------- #
def _empty_backlog(path: Path):
    pd.DataFrame(columns=["canonical_sku", "canonical_warehouse",
                          "canonical_uom", "quantity"]).to_csv(path, index=False)
    return path


def test_po_eta_compared_to_need_date_not_boolean(tmp_path):
    make_pack(tmp_path)
    stock, _backlog, _po = make_live(tmp_path)
    backlog = _empty_backlog(tmp_path / "backlog_empty.csv")

    po_jsonl = tmp_path / "po_tongtool.jsonl"
    records = [
        # KS1 需要日 2027-02-16：ETA 当天 → 按时
        {"status": "1", "quantity": 20, "in_quantity": 0, "goods_sku": "TT1",
         "warehouseName": "美中-FZH-DANEEY", "willArriveDate": "2027-02-16"},
        # KS1 同键另一行无 ETA → 不计按时，计入 missing_eta
        {"status": "1", "quantity": 5, "in_quantity": 0, "goods_sku": "TT1",
         "warehouseName": "美中-FZH-DANEEY"},
        # KS3 需要日 2027-03-01：ETA 晚一天 → 不计按时
        {"status": "1", "quantity": 7, "in_quantity": 0, "goods_sku": "TT3",
         "warehouseName": "美中-FZH-DANEEY", "willArriveDate": "2027-03-02"},
    ]
    po_jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records),
                        encoding="utf-8")

    frame, meta = _call(tmp_path, stock_path=stock, backlog_path=backlog,
                        po_tongtool_path=po_jsonl)
    po = meta["po"]
    assert po["rows"] == 3
    assert po["quantity"] == 32
    assert po["with_eta"] == 2 and po["with_eta_qty"] == 27
    assert po["missing_eta"] == 1 and po["missing_eta_qty"] == 5
    # 回归点：若 ETA 被退化成 bool，这里会是 0
    assert po["on_time_qty"] == 20
    assert po["late_qty"] == 7
    assert po["unproven_qty"] == 12          # 5 无 ETA + 7 迟到

    by_sku = frame.set_index("sku")
    ks1 = by_sku.loc["KS1"]
    # 100 − (期初 10 + max(在途 2, 按时 PO 20) + min(CG 3, D6 1)) = 69
    assert ks1["supply_po"] == 25
    assert ks1["supply_expected"] == 31 and ks1["new_qty"] == 69
    assert ks1["supply_proven"] == 31
    # KS3：7 件迟到 PO 不进 expected/proven
    ks3 = by_sku.loc["KS3"]
    assert ks3["supply_po"] == 7 and ks3["supply_expected"] == 0
    assert ks3["new_qty"] == 50


def test_po_tsv_eta_equal_and_next_day(tmp_path):
    make_pack(tmp_path)
    stock, _backlog, _po = make_live(tmp_path)
    backlog = _empty_backlog(tmp_path / "backlog_empty.csv")
    po = tmp_path / "po_open.tsv"
    po.write_text(
        "PO-1\tTT1\t20\t20\t美中-FZH-DANEEY\t2027-02-16\n"   # 当天 → 按时
        "PO-2\tTT3\t7\t7\t美中-FZH-DANEEY\t2027-03-02\n",    # 晚一天 → 不按时
        encoding="utf-8")
    frame, meta = _call(tmp_path, stock_path=stock, backlog_path=backlog, po_path=po)
    assert meta["po"]["on_time_qty"] == 20
    assert meta["po"]["late_qty"] == 7
    assert meta["po"]["missing_eta_qty"] == 0
    assert frame.set_index("sku").loc["KS3", "supply_expected"] == 0


# --------------------------------------------------------------------------- #
# P0 反例：SO 事实键 canonical 归一；不能归一的行走 evidence，不得静默变 0
# --------------------------------------------------------------------------- #
def test_en_so_rows_canonicalized_and_unresolved_counted(tmp_path):
    make_pack(tmp_path)
    # 额外一个可映射到 D6 宇宙之外物料的通途 SKU，用于造 UOM 缺失
    with open(tmp_path / "data" / "sku_map.tsv", "a", encoding="utf-8") as fh:
        fh.write("X9\tTT9\tCUST\n")
    stock, _backlog, po = make_live(tmp_path)

    so = pd.DataFrame([
        # 1 已规范：EN 成品码直接命中
        {"so": "SO-1", "customer": "DANEEY", "warehouse": "成品仓 - FZH",
         "item_code": "KS1", "open_qty": 3, "uom": "个"},
        # 2 皮壳 PK#：不能当成品 → 身份缺失
        {"so": "SO-2", "customer": "DANEEY", "warehouse": "半成品仓 - FZH",
         "item_code": "PK#KS1-DM", "open_qty": 4, "uom": "个"},
        # 3 别家客户 → 客户池不符
        {"so": "SO-3", "customer": "CENTRADE", "warehouse": "成品仓 - FZH",
         "item_code": "KS1", "open_qty": 6, "uom": "个"},
        # 4 通途 SKU 映射到宇宙外物料且无 UOM → UOM 缺失
        {"so": "SO-4", "customer": "DANEEY", "warehouse": "成品仓 - FZH",
         "item_code": "TT9", "open_qty": 5, "uom": ""},
        # 5 通途 SKU 经 sku_map 归一到 KS2
        {"so": "SO-5", "customer": "DANEEY", "warehouse": "成品仓 - FZH",
         "item_code": "TT2", "open_qty": 1, "uom": "个"},
        # 6 行仓明确属于别家分公司 → 仓归属不符
        {"so": "SO-6", "customer": "DANEEY", "warehouse": "美东-CENTRADE",
         "item_code": "KS1", "open_qty": 9, "uom": "个"},
    ])
    so_path = tmp_path / "so_raw.csv"
    so.to_csv(so_path, index=False, encoding="utf-8")

    frame, meta = _call(tmp_path, stock_path=stock, backlog_path=so_path, po_path=po,
                        so_in_forecast=True)
    so_ev = meta["so"]
    assert so_ev["format"] == "en_sales_orders"
    assert so_ev["rows"] == 6
    assert so_ev["accepted_rows"] == 2                 # SO-1 + SO-5
    assert so_ev["identity_missing"] == 1              # SO-2
    assert so_ev["customer_pool_mismatch"] == 1        # SO-3
    assert so_ev["uom_missing"] == 1                   # SO-4
    assert so_ev["warehouse_out_of_branch"] == 1       # SO-6
    assert so_ev["rejected_rows"] == 4
    assert so_ev["quantity"] == 4                      # 3 + 1
    reasons = {s["reason"] for s in so_ev["unresolved_samples"]}
    assert reasons == {"identity_missing", "customer_pool_mismatch",
                       "uom_missing", "warehouse_out_of_branch"}
    assert [s["row"] for s in so_ev["unresolved_samples"]] == [2, 3, 4, 6]
    assert {s["so"] for s in so_ev["unresolved_samples"]} == {"SO-2", "SO-3", "SO-4", "SO-6"}

    by_sku = frame.set_index("sku")
    assert by_sku.loc["KS1", "supply_so"] == 3          # 只有可归一行命中
    assert by_sku.loc["KS2", "supply_so"] == 1
    # 未归一的行不改变总量为 0 的假象：KS1 仍按 100 需求算出 87
    assert by_sku.loc["KS1", "demand_qty"] == 100
    assert by_sku.loc["KS1", "new_qty"] == 87


def test_so_in_forecast_switch_adds_only_resolved_so_once(tmp_path):
    make_pack(tmp_path)
    stock, backlog, po = make_live(tmp_path)          # canonical SO: KS1=3

    frame_on, meta_on = _call(tmp_path, stock_path=stock, backlog_path=backlog,
                              po_path=po, so_in_forecast=True)
    frame_off, meta_off = _call(tmp_path, stock_path=stock, backlog_path=backlog,
                                po_path=po, so_in_forecast=False)

    assert meta_on["so_in_forecast"] is True
    assert meta_on["so"]["attached_qty"] == 0
    assert meta_on["totals"]["so_attached_qty"] == 0
    assert "已含在预测内" in frame_on.set_index("sku").loc["KS1", "warnings"]

    assert meta_off["so_in_forecast"] is False
    assert meta_off["so"]["attached_qty"] == 3
    assert meta_off["totals"]["so_attached_qty"] == 3
    warnings = frame_off.set_index("sku").loc["KS1", "warnings"]
    assert "已叠加到需求" in warnings and "双计" in warnings

    # 同一条 SO 只计一次：净需求差恰好等于 SO 余额 3，不是 6
    on_qty = frame_on.set_index("sku").loc["KS1", "new_qty"]
    off_qty = frame_off.set_index("sku").loc["KS1", "new_qty"]
    assert off_qty - on_qty == 3
    # demand_qty 仍是预测/D6 需求原值；SO 叠加只体现在 reason 与净需求
    assert frame_on.set_index("sku").loc["KS1", "demand_qty"] == 100
    assert frame_off.set_index("sku").loc["KS1", "demand_qty"] == 100
    assert "含未履约 SO 3" in (frame_off.set_index("sku").loc["KS1", "reason"] or "")


def test_so_in_forecast_not_double_counted_for_duplicate_keys(tmp_path):
    make_pack(tmp_path)
    d6_path = tmp_path / "data" / "D6_v6_22.xlsx"
    d6 = pd.read_excel(d6_path, sheet_name="1_全量动作")
    dup = d6[d6["product_id"] == "KS1"].iloc[[0]].copy()
    dup["形态"] = "半成品"          # 同一 (SKU, 主仓, UOM) 键的第二行
    pd.concat([d6, dup], ignore_index=True).to_excel(
        d6_path, sheet_name="1_全量动作", index=False)

    stock, backlog, po = make_live(tmp_path)
    frame_on, _ = _call(tmp_path, stock_path=stock, backlog_path=backlog,
                        po_path=po, so_in_forecast=True)
    frame_off, meta = _call(tmp_path, stock_path=stock, backlog_path=backlog,
                            po_path=po, so_in_forecast=False)
    ks1_on = frame_on[frame_on["sku"] == "KS1"]
    ks1_off = frame_off[frame_off["sku"] == "KS1"]
    assert len(ks1_on) == 2 and len(ks1_off) == 2
    assert meta["so"]["attached_qty"] == 3
    # 同一 SO 在重复键上只叠加一次：两行合计净需求 +3，不是 +6
    assert ks1_off["new_qty"].sum() - ks1_on["new_qty"].sum() == 3
    assert any("重复行" in str(w) for w in ks1_off["warnings"])


