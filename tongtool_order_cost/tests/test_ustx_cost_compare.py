# -*- coding: utf-8 -*-
"""ustx_cost_compare（美中 USTX 三方案对比）单元测试 —— 全程离线。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost import ustx_cost_compare as U  # noqa: E402


# ── 小样构造 ──


def shell_rows(*triples):
    h = ["品类尺寸面料编码", "EN重量模板物料号", "绍兴二次加工成本", "美国二次加工成本", "波兰二次加工成本"]
    return h, [list(t) for t in triples]


def bom_rows(*rows):
    h = ["重量模板, 编号", "绍兴发货方式", "皮壳成本", "绍兴包装半成品成本",
         "绍兴包装成品成本", "美中加工成本, USTX"]
    return h, [list(r) for r in rows]


def b1_rows(*rows):
    h = ["品类尺寸面料编码", "二次加工成本*系数多月202411"]
    return h, [list(r) for r in rows]


class FakeKey:
    def __init__(self, order_id="O1", package_id="P1", tongtool_sku="S1",
                 platform_sku="PS1", occurrence_index=0):
        self.order_id = order_id
        self.package_id = package_id
        self.tongtool_sku = tongtool_sku
        self.platform_sku = platform_sku
        self.occurrence_index = occurrence_index


class FakeRow:
    def __init__(self, headers, cells, *, sheet="写回2026年7月订单", row_number=2, key=None):
        self.source_sheet = sheet
        self.row_number = row_number
        self.headers = tuple(headers)
        self.cells = tuple(cells)
        self.key = key or FakeKey()

    def get(self, column):
        for i, h in enumerate(self.headers):
            if h == column:
                return str(self.cells[i]).strip() if i < len(self.cells) else ""
        return ""


def order_row(key_val="SX-A-45-DM", warehouse="FZH-DANEEY", qty="2",
              pk="10", head="3", proc="20", sx2="0", *, row_number=2, key=None, category="三角"):
    headers = ["品类尺寸面料编码", "发货仓库", "品类", "发货数量",
               "皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本"]
    cells = [key_val, warehouse, category, qty, pk, head, proc, sx2]
    return FakeRow(headers, cells, row_number=row_number, key=key)


# ── 列合同 ──


def test_validate_contract_ok():
    sh, _ = shell_rows(("K1", "WT1", "1", "2", "3"))
    bh, _ = bom_rows(("WT1", "皮壳", "10", "0", "5", "7"))
    b1h, _ = b1_rows(("K1", "9"))
    c = U.validate_formula_contract(sh, bh, b1h)
    assert c.key_column == U.KEY_COL
    assert c.component_columns == U.COMPONENT_COLS


def test_validate_contract_missing_column_raises():
    sh, _ = shell_rows(("K1", "WT1", "1", "2", "3"))
    bh, _ = bom_rows(("WT1", "皮壳", "10", "0", "5"))  # 缺 美中加工成本
    bh = [h for h in bh if h != "美中加工成本, USTX"]
    b1h, _ = b1_rows(("K1", "9"))
    with pytest.raises(U.ContractError):
        U.validate_formula_contract(sh, bh, b1h)


# ── B2 目录 ──


def _b2(shell, bom, keys):
    sh, sr = shell
    bh, br = bom
    idx, dups = U.build_shell_weight_index(sh, sr)
    bidx = U.build_bom_index(bh, br)
    return U.build_b2_catalog(idx, bidx, keys=keys, ambiguous_keys=[d["key"] for d in dups])


def test_b2_shell_max_and_ustx_and_sx2_by_ship_method():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(
        ("WT1", "半成品", "10", "4", "6", "7"),
        ("WT1", "半成品", "12", "4", "6", "7"),   # 皮壳取 max=12
    )
    res = _b2(shell, bom, ["K1"])
    row = res.rows["K1"]
    assert row["shell_cost"] == 12.0
    assert row["processing_cost"] == 7.0
    assert row["sx_processing_cost"] == 4.0     # 半成品 → 绍兴包装半成品成本
    assert row["head_freight"] is None          # import 无来源
    assert row["shipping_method"] == "半成品"
    assert row["source_kind"] == U.SRC_IMPORT


def test_b2_ship_method_finished_and_shell():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"), ("K2", "WT2", "1", "2", "3"))
    bom = bom_rows(
        ("WT1", "成品", "10", "4", "6", "7"),
        ("WT2", "皮壳", "10", "4", "6", "8"),
    )
    res = _b2(shell, bom, ["K1", "K2"])
    assert res.rows["K1"]["sx_processing_cost"] == 6.0   # 成品 → 绍兴包装成品成本
    assert res.rows["K2"]["sx_processing_cost"] == 0.0   # 皮壳 → 0


def test_b2_unmatched_when_no_shell_or_bom():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT9", "皮壳", "10", "4", "6", "7"))
    res = _b2(shell, bom, ["K1", "KX"])
    reasons = {u["key"]: u["reason"] for u in res.unmatched}
    assert reasons["K1"] == "missing_bom_import"
    assert reasons["KX"] == "missing_shell_import"


def test_b2_blocks_on_ambiguous_shipping_method():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(
        ("WT1", "半成品", "10", "4", "6", "7"),
        ("WT1", "成品", "10", "4", "6", "7"),
    )
    res = _b2(shell, bom, ["K1"])
    assert res.blocked_reasons


def test_shell_conflicting_weight_template_is_duplicate():
    sh, sr = shell_rows(("K1", "WT1", "1", "2", "3"), ("K1", "WT2", "1", "2", "3"))
    idx, dups = U.build_shell_weight_index(sh, sr)
    assert len(dups) == 1 and dups[0]["key"] == "K1"
    assert "K1" not in idx          # 歧义键不进索引（不猜首/末行）


def test_b2_excludes_ambiguous_shell_key():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"), ("K1", "WT2", "1", "2", "3"),
                       ("K2", "WT3", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "0", "0", "7"),
                   ("WT2", "皮壳", "99", "0", "0", "7"),
                   ("WT3", "皮壳", "10", "0", "0", "8"))
    res = _b2(shell, bom, ["K1", "K2"])
    assert "K1" not in res.rows
    assert {u["key"]: u["reason"] for u in res.unmatched}["K1"] == "ambiguous_shell_key"
    assert res.rows["K2"]["processing_cost"] == 8.0
    assert res.duplicate_keys and res.duplicate_keys[0]["key"] == "K1"


# ── B1 目录 ──


def test_b1_measured_preferred_over_formula():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b2 = _b2(shell, bom, ["K1"])
    b1 = U.build_b1_catalog({"K1": 99.0}, b2, keys=["K1"])
    assert b1.rows["K1"]["source_kind"] == U.SRC_MEASURED
    assert b1.rows["K1"]["processing_cost"] == 99.0
    assert b1.source_counts[U.SRC_MEASURED] == 1


def test_b1_formula_filled_when_estimate_missing():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b2 = _b2(shell, bom, ["K1"])
    b1 = U.build_b1_catalog({}, b2, keys=["K1"])
    assert b1.rows["K1"]["source_kind"] == U.SRC_FORMULA_FILLED
    assert b1.rows["K1"]["processing_cost"] == 7.0
    assert any("formula_filled" in x for x in b1.rows["K1"]["lineage"])


def test_b1_unmatched_when_neither_source():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT9", "皮壳", "10", "4", "6", "7"))
    b2 = _b2(shell, bom, ["K1"])
    b1 = U.build_b1_catalog({}, b2, keys=["K1"])
    assert "K1" not in b1.rows
    assert b1.unmatched[0]["key"] == "K1"


def test_b1_source_counts_close():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"), ("K2", "WT2", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b2 = _b2(shell, bom, ["K1", "K2"])
    b1 = U.build_b1_catalog({"K1": 5.0}, b2, keys=["K1", "K2"])
    c = b1.source_counts
    assert c[U.SRC_MEASURED] + c[U.SRC_FORMULA_FILLED] + c["unmatched"] == len(b1.rows) + len(b1.unmatched)


# ── 全月比较 ──


def _contract(shell, bom, b1):
    return U.validate_formula_contract(shell[0], bom[0], b1[0])


def test_compare_non_ustx_rows_copy_a_exactly():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("K1", "99"))
    # 该用例无美中行 → 目录按空键集建（否则 b1_source_conservation 会（正确地）报不闭合）
    b2 = _b2(shell, bom, [])
    b1 = U.build_b1_catalog({}, b2, keys=[])
    rows = [order_row("K1", warehouse="美东-CENTRADE", pk="10", head="3", proc="20", sx2="0")]
    raw = []
    res = U.compare_monthly_costs(rows, raw, ustx_warehouse_names={"FZH-DANEEY"},
                                  b1_catalog=b1, b2_catalog=b2, contract=_contract(shell, bom, (b1h, b1r)))
    r = res.rows[0]
    assert r["is_ustx"] is False
    for k in ("pk", "head", "proc", "sx2"):
        assert r[f"d1_{k}"] == 0 and r[f"d2_{k}"] == 0
    assert r["b1_source"] == U.SRC_NOT_USTX and r["b2_source"] == U.SRC_NOT_USTX
    assert res.gates and all(g["status"] == "pass" for g in res.gates if g["blocking"])


def test_compare_ustx_three_scenarios_and_identity():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "成品", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("K1", "99"))
    b2 = _b2(shell, bom, ["K1"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["K1"])
    rows = [order_row("K1", warehouse="FZH-DANEEY", qty="3", pk="10", head="3", proc="20", sx2="0")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"FZH-DANEEY"},
                                  b1_catalog=b1, b2_catalog=b2, contract=_contract(shell, bom, (b1h, b1r)))
    r = res.rows[0]
    assert r["is_ustx"] is True
    # A 保留现状
    assert r["A_pk"] == 10 and r["A_proc"] == 20 and r["A_sx2"] == 0
    # B1 只改二次加工
    assert r["B1_proc"] == 99 and r["B1_pk"] == 10 and r["B1_sx2"] == 0
    assert r["d1_proc"] == 79
    # B2 四项重建
    assert r["B2_pk"] == 10 and r["B2_proc"] == 7 and r["B2_sx2"] == 6 and r["B2_head"] == 3
    # 四项恒等
    for scen in ("d1", "d2"):
        s = sum(r[f"{scen}_{k}"] for k in ("pk", "head", "proc", "sx2"))
        assert abs(s - r[f"d_unit_{'B1' if scen=='d1' else 'B2'}"]) < 0.01


def test_compare_row_count_conserved_and_raw_coverage_reported():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("K1", "99"))
    b2 = _b2(shell, bom, ["K1"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["K1"])
    rows = [order_row("K1", key=FakeKey(order_id=f"O{i}", occurrence_index=i), row_number=i + 2) for i in range(5)]
    raw = [order_row("K1", key=FakeKey(order_id="O0"), row_number=2),
           order_row("K1", key=FakeKey(order_id="ONLYRAW"), row_number=99)]
    res = U.compare_monthly_costs(rows, raw, ustx_warehouse_names={"FZH-DANEEY"},
                                  b1_catalog=b1, b2_catalog=b2, contract=_contract(shell, bom, (b1h, b1r)))
    assert len(res.rows) == 5
    buckets = {b["bucket"]: b["rows"] for b in res.raw_coverage}
    assert buckets["raw_input"] == 2 and buckets["writeback_input"] == 5
    assert buckets["raw_only"] == 1


# ── 头程（按绍兴发货方式） ──


def _en_bom(*rows):
    h = ["重量模板, 编号", "绍兴发货方式",
         "头程皮壳运费, 美中USTX", "头程半成品运费, 美中USTX", "头程成品运费, 美中USTX",
         "皮壳单重, (g)", "半成品计费重量, (kg)", "成品计费重量, (kg)"]
    return h, [list(r) for r in rows]


def test_head_freight_index_by_shipping_method_with_shell_fallback():
    h, r = _en_bom(
        ("WT1", "半成品", "3.5", "19.55", "21.02", "360", "2.0", "2.16"),
        ("WT1", "半成品", "3.5", "19.55", "21.02", "360", "2.0", "2.16"),
        ("WT2", "皮壳", "8.5", "", "48.65", "1000", "", "5.0"),
    )
    idx = U.build_head_freight_index(h, r)
    assert idx.by_template["WT1"]["半成品"] == 19.55
    assert idx.by_template["WT1"]["成品"] == 21.02
    assert idx.by_template["WT2"]["皮壳"] == 8.5

    amt, src = idx.resolve("WT1", "半成品")
    assert amt == 19.55 and "半成品" in src
    # 半成品头程缺失 → 回退皮壳头程
    amt2, src2 = idx.resolve("WT2", "半成品")
    assert amt2 == 8.5 and "兜底" in src2
    amt3, _ = idx.resolve("NOPE", "皮壳")
    assert amt3 is None


def test_compare_b2_head_freight_from_en_bom_by_shipping_method():
    shell = shell_rows(("SX-A-45-DM", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "半成品", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("SX-A-45-DM", "99"))
    b2 = _b2(shell, bom, ["SX-A-45-DM"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["SX-A-45-DM"])
    eh, er = _en_bom(("WT1", "半成品", "3.5", "19.55", "21.02", "360", "2.0", "2.16"))
    head = U.build_head_freight_index(eh, er)
    rows = [order_row("SX-A-45-DM", warehouse="FZH-DANEEY", qty="2", pk="10", head="8.5", proc="20", sx2="0")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"FZH-DANEEY"},
                                  b1_catalog=b1, b2_catalog=b2,
                                  contract=_contract(shell, bom, (b1h, b1r)), head_index=head)
    r = res.rows[0]
    assert r["A_head"] == 8.5            # A 保留现值
    assert r["B2_head"] == 19.55         # B2 按发货方式(半成品)取头程
    assert r["B1_head"] == 8.5           # B1 不改头程
    assert abs(r["d2_head"] - (19.55 - 8.5)) < 0.001
    assert r["head_src"]


# ── 闸门得真会失败（不能写成恒真） ──


def test_gate_b1_source_conservation_catches_uncovered_key():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"), ("K2", "WT2", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"), ("WT2", "皮壳", "10", "4", "6", "8"))
    b2 = _b2(shell, bom, ["K1", "K2"])
    b1h, b1r = b1_rows(("K1", "99"))
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["K1", "K2"])
    b1.rows.pop("K2")          # 人为破坏：目录漏掉 K2
    rows = [order_row("K1"), order_row("K2")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"FZH-DANEEY"},
                                  b1_catalog=b1, b2_catalog=b2, contract=_contract(shell, bom, (b1h, b1r)))
    gate = next(g for g in res.gates if g["gate"] == "b1_source_conservation")
    assert gate["status"] == "fail" and gate["blocking"] is True
    assert res.conclusions_blocked is True


def test_gate_raw_coverage_conservation_is_partition_check():
    shell = shell_rows(("K1", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("K1", "99"))
    b2 = _b2(shell, bom, ["K1"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["K1"])
    rows = [order_row("K1", key=FakeKey(order_id="O1"), row_number=2)]
    raw = [order_row("K1", key=FakeKey(order_id="O1"), row_number=2),
           order_row("K1", key=FakeKey(order_id="O2"), row_number=3)]
    res = U.compare_monthly_costs(rows, raw, ustx_warehouse_names={"FZH-DANEEY"},
                                  b1_catalog=b1, b2_catalog=b2, contract=_contract(shell, bom, (b1h, b1r)))
    gate = next(g for g in res.gates if g["gate"] == "raw_coverage_conservation")
    assert gate["status"] == "pass"
    buckets = {b["bucket"]: b["rows"] for b in res.raw_coverage}
    # 三个桶恰好划分并集：raw_only + wb_only + both == |raw ∪ wb|
    assert buckets["raw_only"] + buckets["writeback_only"] + buckets["both"] == 2
