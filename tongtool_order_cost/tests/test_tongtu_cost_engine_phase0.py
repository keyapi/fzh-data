# -*- coding: utf-8 -*-
"""Phase 0 单元测试：列合同与快照 manifest。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.adapters.en_snapshot import (
    freeze_snapshot,
    verify_snapshot,
)
from tongtool_order_cost.tongtu_cost_engine.writeback.contract import (
    COST_COLUMNS,
    KEY_COLUMNS_ORDER,
    ContractError,
    validate_header,
)


def test_contract_accepts_key_columns_and_extra():
    cols = list(KEY_COLUMNS_ORDER) + ["额外列"]
    validate_header(cols)  # 不抛


def test_contract_rejects_missing_and_duplicate():
    with pytest.raises(ContractError):
        validate_header(["订单号", "平台SKU"])
    with pytest.raises(ContractError):
        validate_header(list(COST_COLUMNS) + ["皮壳成本"])


def test_snapshot_roundtrip_and_tamper(tmp_path):
    src = tmp_path / "orders.csv"
    src.write_text("订单号,发货数量\nA,1\n", encoding="utf-8")
    snap_root = tmp_path / "snapshots"
    dest = freeze_snapshot("202608", {"orders": src}, snap_root)
    assert (dest / "manifest.json").exists()
    assert verify_snapshot(dest) == []

    # 篡改文件 → 校验失败
    (dest / "orders.csv").write_text("订单号,发货数量\nA,2\n", encoding="utf-8")
    assert verify_snapshot(dest)


def test_snapshot_refuses_overwrite(tmp_path):
    src = tmp_path / "orders.csv"
    src.write_text("x\n1\n", encoding="utf-8")
    dest = freeze_snapshot("202608", {"orders": src}, tmp_path / "s")
    with pytest.raises(FileExistsError):
        freeze_snapshot("202608", {"orders": src}, tmp_path / "s")
    assert dest.exists()
