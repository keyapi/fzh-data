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


# ── 同键多模板：数据驱动消歧（不取首行） ──


def shell_rows_cat(*rows):
    """带 `品类` 列的小样：行 = (品类, 键, 重量模板, sx2, us2, pl2)。"""
    h = ["品类", "品类尺寸面料编码", "EN重量模板物料号",
         "绍兴二次加工成本", "美国二次加工成本", "波兰二次加工成本"]
    return h, [list(r) for r in rows]


def test_shell_ambiguous_candidates_lists_each_template():
    sh, sr = shell_rows_cat(
        ("米白床头靠枕", "K1", "WT-A", "1", "2", "3"),
        ("米白大靠背", "K1", "WT-B", "1", "2", "3"),
    )
    cands = U.shell_ambiguous_candidates(sh, sr)
    assert {c["weight_template"] for c in cands["K1"]} == {"WT-A", "WT-B"}
    assert U.shell_ambiguous_candidates(*shell_rows(("K1", "WT1", "1", "2", "3"))) == {}


def test_resolve_shell_candidates_by_category_then_sku_then_none():
    cands = [
        {"weight_template": "WT-A", "category": "米白床头靠枕"},
        {"weight_template": "WT-B", "category": "米白大靠背"},
    ]
    assert U.resolve_shell_candidates(cands, category="米白大靠背")["weight_template"] == "WT-B"
    assert U.resolve_shell_candidates(cands, category="查无此品类") is None
    # 品类定不了 → 退到模板尾串落在 SKU 里（唯一命中）
    td = [
        {"weight_template": "ZLMB#KS0364-XNEOSTH-153x65", "category": ""},
        {"weight_template": "ZLMB#KS0423-XNEOSTH-153x65x23", "category": ""},
    ]
    got = U.resolve_shell_candidates(td, sku="KS0423-XNEOSTH-153x65x23-OFFWHITE")
    assert got["weight_template"] == "ZLMB#KS0423-XNEOSTH-153x65x23"


def test_b2_builds_candidate_rows_for_ambiguous_key():
    sh, sr = shell_rows_cat(("A", "K1", "WT-A", "1", "2", "3"),
                            ("B", "K1", "WT-B", "1", "2", "3"))
    bh, br = bom_rows(("WT-A", "皮壳", "10", "4", "6", "7"),
                      ("WT-B", "皮壳", "20", "4", "6", "9"))
    idx, dups = U.build_shell_weight_index(sh, sr)
    bidx = U.build_bom_index(bh, br)
    res = U.build_b2_catalog(idx, bidx, keys=["K1"], ambiguous_keys=[d["key"] for d in dups],
                             ambiguous_candidates=U.shell_ambiguous_candidates(sh, sr))
    assert "K1" not in res.rows                    # 不定到唯一，就不进主目录
    assert {r["weight_template"] for r in res.ambiguous_rows["K1"]} == {"WT-A", "WT-B"}


def test_compare_resolves_ambiguous_key_by_order_category():
    sh, sr = shell_rows_cat(("米白床头靠枕", "K1", "WT-A", "1", "2", "3"),
                            ("米白大靠背", "K1", "WT-B", "1", "2", "3"))
    bom = bom_rows(("WT-A", "皮壳", "10", "4", "6", "7"),
                   ("WT-B", "皮壳", "20", "4", "6", "9"))
    idx, dups = U.build_shell_weight_index(sh, sr)
    b2 = U.build_b2_catalog(idx, U.build_bom_index(*bom), keys=["K1"],
                            ambiguous_keys=[d["key"] for d in dups],
                            ambiguous_candidates=U.shell_ambiguous_candidates(sh, sr))
    b1h, b1r = b1_rows(("K1", "99"))
    b1 = U.build_b1_catalog({}, b2, keys=["K1"])
    # 订单侧品类 = 大靠背 → 唯一命中 WT-B（proc=9）
    rows = [order_row("K1", warehouse="USTX分公司", category="米白大靠背", proc="20")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"USTX分公司"},
                                  b1_catalog=b1, b2_catalog=b2,
                                  contract=_contract((sh, sr), bom, (b1h, b1r)))
    r = res.rows[0]
    assert r["B2_proc"] == 9 and r["B1_proc"] == 9   # B1 缺测算值 → formula_filled 取定夺后的 B2
    assert "ambiguous_key_resolved" not in [g["gate"] for g in res.gates]
    assert not res.conclusions_blocked


# ── 直连优先（通途SKU → EN 物料 → 重量模板），不命中回落旧键 ──


def test_direct_template_from_item():
    assert U.direct_template_from_item("KS0423-XNEOSTH-153x65x23-OFFWHITE") == "ZLMB#KS0423-XNEOSTH-153x65x23"
    assert U.direct_template_from_item("KS0174-WGMSR-45-BROWN") == "ZLMB#KS0174-WGMSR-45"
    assert U.direct_template_from_item("KS0517-QDZZMMB-SET6-DEEPGREYMIX") == "ZLMB#KS0517-QDZZMMB-SET6"
    assert U.direct_template_from_item("X-Y") == ""       # 段数不足


def test_build_direct_index_accepts_dict_and_flags_conflict():
    idx, dups = U.build_direct_index({"S1": "KS0001-HLR-100-OFFWHITE"})
    assert idx["S1"] == "ZLMB#KS0001-HLR-100"
    assert dups == []
    # 同 SKU 指向不同模板 → 歧义，不进索引
    h = ["通途SKU", "EN物料"]
    idx2, dups2 = U.build_direct_index((h, [["S1", "KS0001-HLR-100-OFFWHITE"],
                                            ["S1", "KS0002-DM-100-OFFWHITE"]]))
    assert "S1" not in idx2 and len(dups2) == 1


def _row_with_sku(sku, key_val="K1", warehouse="USTX分公司", proc="20", category="X"):
    headers = ["品类尺寸面料编码", "发货仓库", "品类", "发货数量", "皮壳成本",
               "头程运费金额", "二次加工成本", "绍兴二次加工成本", "通途SKU"]
    cells = [key_val, warehouse, category, "1", "10", "3", proc, "0", sku]
    return FakeRow(headers, cells, row_number=2)


def test_compare_prefers_direct_by_sku_over_key():
    shell = shell_rows(("K1", "WT-KEY", "1", "2", "3"))
    # 旧键 → WT-KEY(proc 7)；直连 SKU → ZLMB#KS9000-XNEOSTH-153(proc 9)
    bom = bom_rows(("WT-KEY", "皮壳", "10", "4", "6", "7"),
                   ("ZLMB#KS9000-XNEOSTH-153", "皮壳", "10", "4", "6", "9"))
    b1h, b1r = b1_rows(("K1", "99"))
    b2 = _b2((shell[0], shell[1]), (bom[0], [r for r in bom[1] if r[0] == "WT-KEY"]), ["K1"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["K1"])
    didx, _ = U.build_direct_index({"S1": "KS9000-XNEOSTH-153-WHITE"})
    assert didx["S1"] == "ZLMB#KS9000-XNEOSTH-153"
    direct = U.build_direct_catalog(didx, U.build_bom_index(*bom), skus=["S1"])
    assert direct.rows["S1"]["processing_cost"] == 9.0
    rows = [_row_with_sku("S1")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"USTX分公司"},
                                  b1_catalog=b1, b2_catalog=b2,
                                  contract=_contract((shell[0], shell[1]), bom, (b1h, b1r)),
                                  direct_catalog=direct)
    r = res.rows[0]
    assert r["B2_proc"] == 9.0                      # 直连胜出
    assert "direct<-" in r["b2_lineage"]
    assert "b2_direct_coverage" in [g["gate"] for g in res.gates]


def test_compare_direct_miss_falls_back_to_key():
    shell = shell_rows(("K1", "WT-KEY", "1", "2", "3"))
    bom = bom_rows(("WT-KEY", "皮壳", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("K1", "99"))
    b2 = _b2(shell, bom, ["K1"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["K1"])
    direct = U.build_direct_catalog({}, U.build_bom_index(*bom), skus=[])   # 空直连
    rows = [_row_with_sku("S-NOPE")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"USTX分公司"},
                                  b1_catalog=b1, b2_catalog=b2,
                                  contract=_contract((shell[0], shell[1]), bom, (b1h, b1r)),
                                  direct_catalog=direct)
    assert res.rows[0]["B2_proc"] == 7.0            # 回落旧键


def test_compare_blocks_when_ambiguous_key_unresolvable():
    sh, sr = shell_rows_cat(("A", "K1", "WT-A", "1", "2", "3"),
                            ("B", "K1", "WT-B", "1", "2", "3"))
    bom = bom_rows(("WT-A", "皮壳", "10", "4", "6", "7"),
                   ("WT-B", "皮壳", "20", "4", "6", "9"))
    idx, dups = U.build_shell_weight_index(sh, sr)
    b2 = U.build_b2_catalog(idx, U.build_bom_index(*bom), keys=["K1"],
                            ambiguous_keys=[d["key"] for d in dups],
                            ambiguous_candidates=U.shell_ambiguous_candidates(sh, sr))
    b1 = U.build_b1_catalog({}, b2, keys=["K1"])
    b1h, b1r = b1_rows(("K1", "99"))
    # 订单侧品类/SKU 都定不了 → 不猜，B2 记 unmatched 并阻断
    rows = [order_row("K1", warehouse="USTX分公司", category="毫无关系", proc="20")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"USTX分公司"},
                                  b1_catalog=b1, b2_catalog=b2,
                                  contract=_contract((sh, sr), bom, (b1h, b1r)))
    r = res.rows[0]
    assert r["B2_proc"] == r["A_proc"] == 20          # 未定夺 → 保留 A，不硬套
    assert "ambiguous_key_resolved" in [g["gate"] for g in res.gates]
    assert res.conclusions_blocked


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


# ── B3 工资率情景 ──

_SHEET_H = ["美中包装成品, USTX 编号", "重量模板, 编号", "美中加工成本, USTX"]
_BOMS_H = ["bom_name", "item_code", "total_cost", "time_in_mins", "hour_rate_labour"]


def test_wage_delta_index_matches_by_value_and_zero_for_no_bom():
    sheet_r = [["USTX#A", "WT1", "100"], ["USTX#B", "WT2", "50"]]   # B 无 BOM
    boms_r = [
        ["B-A", "USTX#A", "100", "30", "167.8"],
        ["B-A", "USTX#A", "100", "0", "0"],     # 非美中工站工序（labour=0）不计
    ]
    delta, stats = U.build_wage_delta_index(_SHEET_H, sheet_r, _BOMS_H, boms_r)
    assert abs(delta["WT1"] - (-(30 / 60) * (167.8 - 105))) < 1e-9
    assert "WT2" not in delta                     # 无 BOM → valuation_rate 回退 → 不随工资率变
    assert stats["matched"] == 1 and stats["no_bom"] == 1


def test_wage_delta_conflicting_same_template_not_guessed():
    # 同一重量模板 WT1 上的两个物料 BOM 工时不同 → Δ 不同 → 判歧义、不取首/末
    sheet_r = [["USTX#A", "WT1", "100"], ["USTX#B", "WT1", "100"]]
    boms_r = [
        ["B-A", "USTX#A", "100", "30", "167.8"],
        ["B-B", "USTX#B", "100", "60", "167.8"],
    ]
    delta, stats = U.build_wage_delta_index(_SHEET_H, sheet_r, _BOMS_H, boms_r)
    assert "WT1" not in delta and stats["wt_conflicts"] == 1


def test_wage_delta_requires_columns():
    with pytest.raises(U.ContractError):
        U.build_wage_delta_index(_SHEET_H, [], ["bom_name"], [])


def test_compare_b3_applies_wage_delta_only_to_b2():
    shell = shell_rows(("SX-A-45-DM", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("SX-A-45-DM", "99"))
    b2 = _b2(shell, bom, ["SX-A-45-DM"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["SX-A-45-DM"])
    rows = [order_row("SX-A-45-DM", warehouse="FZH-DANEEY", qty="2", pk="10", head="3", proc="7", sx2="0")]
    res = U.compare_monthly_costs(
        rows, [], ustx_warehouse_names={"FZH-DANEEY"},
        b1_catalog=b1, b2_catalog=b2, contract=_contract(shell, bom, (b1h, b1r)),
        wage_delta_by_template={"WT1": -5.0},
    )
    r = res.rows[0]
    assert r["B2_proc"] == 7 and r["B3_proc"] == 2          # 只动二次加工
    assert r["B3_pk"] == r["B2_pk"] and r["B3_sx2"] == r["B2_sx2"]
    assert r["b3_wage_delta"] == -5.0 and abs(r["d_unit_B3"] - (2 - 7)) < 1e-9
    assert any(g["gate"] == "b3_wage_sim_coverage" for g in res.gates)


def test_compare_without_wage_delta_b3_equals_b2():
    shell = shell_rows(("SX-A-45-DM", "WT1", "1", "2", "3"))
    bom = bom_rows(("WT1", "皮壳", "10", "4", "6", "7"))
    b1h, b1r = b1_rows(("SX-A-45-DM", "99"))
    b2 = _b2(shell, bom, ["SX-A-45-DM"])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=["SX-A-45-DM"])
    rows = [order_row("SX-A-45-DM", warehouse="FZH-DANEEY", proc="7")]
    res = U.compare_monthly_costs(rows, [], ustx_warehouse_names={"FZH-DANEEY"},
                                  b1_catalog=b1, b2_catalog=b2, contract=_contract(shell, bom, (b1h, b1r)))
    r = res.rows[0]
    assert r["B3_proc"] == r["B2_proc"] and r["b3_wage_delta"] == 0.0
    assert not any(g["gate"] == "b3_wage_sim_coverage" for g in res.gates)
