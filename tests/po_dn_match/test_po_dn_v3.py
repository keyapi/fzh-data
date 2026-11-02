# -*- coding: utf-8 -*-
"""PO↔DN v3 小修测试（P2#1–#3、P3#5）。

覆盖：
- FBA 第二分支：全部明细客户码都是 FBA 码 → FBA；mixed / unknown 不算 FBA
- UOM 记账：按 UOM 汇总，不做跨单位相加/换算
- raw 别名：`aliases_raw_all` 保留 `删除` 前缀
- 正式/建议归属标签边界
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "po_dn_match_v3", ROOT / "scripts" / "po_dn_candidate_match_v3.py"
)
assert _SPEC and _SPEC.loader
mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mod
_SPEC.loader.exec_module(mod)


def _dn(customer, item_codes, cc_codes):
    return pd.DataFrame(
        {
            "customer": [customer] * len(item_codes),
            "item_code": item_codes,
            "raw_customer_item_code": cc_codes,
        }
    )


def test_fba_by_customer_name():
    assert mod.classify_dn(_dn("美国FBA仓", ["KS0001-DM-153-IVORY"], ["BNTESTFBA1"])) == "fba"


def test_fba_by_all_customer_codes():
    """客户是 CENTRADE，但明细客户码全部带 FBA → FBA（P2#2 第二分支）。"""
    group = _dn(
        "CENTRADE",
        ["KS0001-DM-153-IVORY", "KS0001-DM-194-GREY"],
        ["BNTESTFBA1", "DANFBA-TEST-2"],
    )
    assert mod.classify_dn(group) == "fba"


def test_mixed_fba_codes_is_not_fba():
    """只有部分行是 FBA 码 → 不算 FBA（mixed）。"""
    group = _dn(
        "CENTRADE",
        ["KS0001-DM-153-IVORY", "KS0001-DM-194-GREY"],
        ["BNTESTFBA1", "CEN961NLINEN-SAGEGREEN-194"],
    )
    assert mod.classify_dn(group) == "matchable"


def test_unknown_codes_are_not_fba():
    """有行没有客户码 → unknown，不算 FBA。"""
    group = _dn(
        "CENTRADE",
        ["KS0001-DM-153-IVORY", "KS0001-DM-194-GREY"],
        ["BNTESTFBA1", None],
    )
    assert mod.classify_dn(group) == "matchable"


def test_pure_liner_still_wins_without_customer_codes():
    group = _dn("DANEEY", ["ND#KS0001-60-CYF-WHITE"] * 2, [None, None])
    assert mod.classify_dn(group) == "pure_liner"


def test_uom_breakdown_never_sums_across_units():
    brk = mod.uom_breakdown([38422, 83805, 100], ["个", "套", "件"])
    assert brk == {"个": 38422.0, "套": 83805.0, "件": 100.0}
    assert mod.single_uom(brk) == "mixed"
    assert mod.format_uom_breakdown({"套": 83805.0, "个": 38422.0}) == "个=38422;套=83805"


def test_role_of_component_prefixes():
    assert mod.role_of("ND#KS0001-60-CYF-WHITE") == "inner_liner"
    assert mod.role_of("PK#KS0455-FHXWXNE-92x56x75-BEIGE") == "cover_component"
    assert mod.role_of("TT0031038K0062927") == "other"


def test_exceptions_keep_raw_aliases_and_uom():
    """数据级：v3 exception 保留 uom / role / raw 别名（文件不存在则跳过）。"""
    path = Path("D:/Work/fzh-order-store/analysis/po_dn_exceptions_2026-10-28_v3.csv")
    if not path.exists():
        pytest.skip("v3 exceptions 未生成")
    exc = pd.read_csv(path, encoding="utf-8-sig")
    assert {"uom", "qty_by_uom", "role", "aliases_raw_all"} <= set(exc.columns)
    pure = exc[exc["type"] == "pure_liner_row"]
    assert len(pure) and set(pure["uom"]) == {"个"}
    unresolved = exc[exc["type"] == "unresolved_row"]
    assert unresolved["uom"].notna().all()
    assert set(unresolved["role"]) <= {"inner_liner", "cover_component", "other"}
    ambiguous = exc[exc["type"] == "ambiguous_alias"]
    assert ambiguous["uom"].notna().all()
    # 严禁出现跨单位总数列
    assert "qty_total" not in exc.columns


def test_load_dns_keeps_delete_prefixed_raw_aliases():
    """P3#5：aliases_raw_all 保留 DB 原始 `删除` 前缀，aliases_all 为清洗后。"""
    duckdb = pytest.importorskip("duckdb")
    dn_csv = Path("D:/Work/fzh-order-store/analysis/leadtime/dn_items_with_customer_code.csv")
    db = Path("D:/Work/fzh-order-store/order_store.duckdb")
    if not dn_csv.exists() or not db.exists():
        pytest.skip("源数据不在本机")
    con = duckdb.connect(str(db), read_only=True)
    items = mod.load_dns(str(dn_csv), con)
    row = items[(items["dn"] == "DN-26-00086") & (items["aliases_all"].str.contains("TT0312587K0064173", na=False))]
    assert len(row) == 1
    raw = row.iloc[0]["aliases_raw_all"]
    assert "删除TT0312587K0064173" in raw
    assert "删除" not in row.iloc[0]["aliases_all"]
