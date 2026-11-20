# -*- coding: utf-8 -*-
"""Phase 4.FBA canary 测试：最小桶 / 四列 / 旧值备份 / 门禁 / 回读 / 状态保留。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.fba_run_package import (  # noqa: E402
    TARGET_COLUMNS,
    build_fba_run_package,
)
from tongtool_order_cost.tongtu_cost_engine.domain.fba_shadow import MERGED_COLUMNS  # noqa: E402


def _row(site, msku, sku, *, qty="1", shell="10", sx="2", proc="0", head="3",
         status="ok", reason="", auto_pref="") -> dict:
    rec = {c: "" for c in MERGED_COLUMNS}
    rec.update({
        "订单号": f"FBA|202608|{site}|{msku}",
        "平台SKU": msku, "通途SKU": sku, "发货数量": qty,
        "皮壳成本": shell, "绍兴二次加工成本": sx, "二次加工成本": proc,
        "头程运费金额": head,
        "皮壳成本*数量": shell, "绍兴二次加工成本*数量": sx,
        "二次加工成本*数量": proc, "头程运费*数量": head,
        "1件产品成本": "12", "产品成本*数量": "12",
        "fulfillment": "FBA", "site": site,
        "bridge_status": status, "bridge_reason": reason,
        "auto_pref": auto_pref,
        "unique_key": f"FBA|202608|{site}|{msku}|{sku}",
    })
    return rec


def _fixture(tmp_path: Path, rows: list[dict], gs_rows: list[dict],
             old_rows: list[dict] | None = None) -> dict:
    shadow = tmp_path / "shadow.csv"
    pd.DataFrame(rows).to_csv(shadow, index=False, encoding="utf-8")
    gs = tmp_path / "raw_fba.csv"
    pd.DataFrame(gs_rows).to_csv(gs, index=False, encoding="utf-8")
    en = tmp_path / "en.csv"
    pd.DataFrame(columns=["order_id_code", "tongtool_sku"]).to_csv(en, index=False)
    bom = tmp_path / "bom.csv"
    pd.DataFrame(columns=["item_fg", "cost_fg"]).to_csv(bom, index=False)
    bundle = tmp_path / "bundle.csv"
    pd.DataFrame([{"bundle_item": "TJ#X", "component_item": "C1", "qty": "1",
                   "bundle_version": "v1|abc"}]).to_csv(bundle, index=False)
    ref = tmp_path / "ref.csv"
    pd.DataFrame(columns=["name", "customer_code", "item_group", "variant_of"]).to_csv(ref, index=False)
    wl = tmp_path / "whitelist.csv"
    pd.DataFrame(columns=["month", "sku", "status"]).to_csv(wl, index=False)
    old = tmp_path / "old_target.csv"
    old_cols = ["渠道账号", "平台SKU", "通途SKU", "发货数量", "皮壳成本",
                "绍兴二次加工成本", "二次加工成本", "头程运费金额", "1件产品成本", "发货仓分类"]
    pd.DataFrame(old_rows or [], columns=old_cols).to_csv(old, index=False, encoding="utf-8")
    return {
        "shadow_csv": shadow, "gs_csv": gs, "en_csv": en, "bom_csv": bom,
        "bundle_csv": bundle, "ref_map_csv": ref, "whitelist_csv": wl,
        "old_source_csv": old,
    }


def _run(tmp_path: Path, files: dict, **kw):
    return build_fba_run_package(
        month="202608", runs_root=tmp_path / "runs", **files, **kw)


def test_fba_canary_smallest_bucket_and_readback(tmp_path):
    rows = [
        _row("AMZ_B", "M-B1", "SKU-B1", qty="1", shell="10", sx="2", head="3"),
        _row("AMZ_B", "OSKBG-RSUS-FBA", "OSKBG-RSUS-FBA", status="pending",
             reason="en_item_missing", shell="", sx="", proc="", head=""),
        _row("AMZ_A", "M-A1", "SKU-A1"),
        _row("AMZ_A", "M-A2", "SKU-A2"),
    ]
    gs = [
        {"站点": "AMZ_B", "MSKU": "M-B1", "SKU": "SKU-B1", "销量": "1",
         "成本": "12", "头程费用": "4"},
        {"站点": "AMZ_A", "MSKU": "M-A1", "SKU": "SKU-A1", "销量": "1",
         "成本": "12", "头程费用": "3"},
    ]
    old = [
        {"渠道账号": "AMZ_B", "平台SKU": "M-B1", "通途SKU": "SKU-B1",
         "发货数量": "1", "皮壳成本": "9", "绍兴二次加工成本": "0",
         "二次加工成本": "3", "头程运费金额": "3", "1件产品成本": "12",
         "发货仓分类": "FBA"},
        {"渠道账号": "AMZ_B", "平台SKU": "M-B1", "通途SKU": "SKU-B1",
         "发货数量": "0", "皮壳成本": "9", "绍兴二次加工成本": "0",
         "二次加工成本": "3", "头程运费金额": "3", "1件产品成本": "12",
         "发货仓分类": "FBA"},
    ]
    files = _fixture(tmp_path, rows, gs, old)
    pkg = _run(tmp_path, files)
    assert pkg.ok
    assert pkg.summary["bucket"] == "AMZ_B"
    assert pkg.summary["rows"] == 1              # OSKBG 已排除
    assert pkg.summary["status_counts"] == {"priced": 1}
    assert pkg.summary["totals"] == {"皮壳成本": 10.0, "绍兴二次加工成本": 2.0,
                                     "二次加工成本": 0.0, "头程运费金额": 3.0}
    d = pkg.summary["diff_totals"]
    assert d["皮壳"] == {"old": 9.0, "new": 10.0, "diff": 1.0}
    assert d["绍兴侧"] == {"old": 3.0, "new": 2.0, "diff": -1.0}
    assert d["头程"] == {"old": 3.0, "new": 3.0, "diff": 0.0}
    assert d["1件合计"] == {"old": 12.0, "new": 12.0, "diff": 0.0}
    assert pkg.summary["old_source"]["kind"] == "writeback"
    assert pkg.summary["old_source"]["rows"] == 2
    diff = pd.read_csv(pkg.run_dir / "diff.csv", dtype=str, keep_default_na=False)
    row = diff[diff["status"] == "matched"].iloc[0].to_dict()
    assert row["diff_reason"] == "bom_version_change"
    assert "绍兴侧" in row["caliber_note"]
    assert pkg.run_dir.name.startswith("fba-202608-AMZ_B-")
    for name in ("manifest.json", "audit.log", "readback.json", "diff.csv", "summary.md",
                 "fba_canary_202608_AMZ_B.csv", "old_values_202608_AMZ_B.csv"):
        assert (pkg.run_dir / name).exists(), name
    manifest = json.loads((pkg.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["excluded_skus"] == ["OSKBG-RSUS-FBA"]
    assert manifest["bundle_versions"] == ["v1|abc"]
    assert manifest["old_values_sha256"]
    assert manifest["whitelist_sha256"]
    assert all("sha256" in v for v in manifest["inputs"].values())
    assert {g["gate"]: g["status"] for g in pkg.gates}["duplicate_keys"] == "pass"
    assert all(c["status"] == "pass" for c in pkg.readback)
    canary = pd.read_csv(pkg.run_dir / "fba_canary_202608_AMZ_B.csv",
                         dtype=str, keep_default_na=False)
    assert len(canary) == 1
    assert canary.iloc[0]["unique_key"] == "FBA|202608|AMZ_B|M-B1|SKU-B1"
    assert canary.iloc[0]["cost_status"] == "priced"
    assert all(c in canary.columns for c in MERGED_COLUMNS)


def test_fba_canary_pending_row_keeps_status_blank_costs(tmp_path):
    rows = [
        _row("AMZ_P", "M-P1", "SKU-P1"),
        _row("AMZ_P", "M-P2", "SKU-P2", status="pending", reason="en_item_missing",
             shell="", sx="", proc="", head=""),
    ]
    gs = [{"站点": "AMZ_P", "MSKU": "M-P1", "SKU": "SKU-P1", "销量": "1",
           "成本": "12", "头程费用": "3"}]
    files = _fixture(tmp_path, rows, gs)
    pkg = _run(tmp_path, files, run_id="fba-test-p1")
    assert pkg.summary["bucket"] == "AMZ_P"
    assert pkg.summary["rows"] == 2
    assert pkg.summary["status_counts"]["pending:en_item_missing"] == 1
    assert {g["gate"]: g["status"] for g in pkg.gates}["pending_status_preserved"] == "pass"
    canary = pd.read_csv(pkg.run_dir / "fba_canary_202608_AMZ_P.csv",
                         dtype=str, keep_default_na=False)
    pending = canary[canary["cost_status"] == "pending:en_item_missing"].iloc[0]
    assert all(pending[c] == "" for c in TARGET_COLUMNS)
    assert pending["bridge_reason"] == "en_item_missing"
    checks = {c["check"]: c["status"] for c in pkg.readback}
    assert checks["待审成本留空"] == "pass"


def test_fba_canary_direct_purchase_zero_status(tmp_path):
    rows = [_row("AMZ_D", "NeckBlue", "NeckBlue", qty="8", shell="48", sx="0",
                 proc="0", head="11.9", reason="direct_purchase_zero")]
    gs = [{"站点": "AMZ_D", "MSKU": "NeckBlue", "SKU": "NeckBlue", "销量": "8",
           "成本": "384", "头程费用": "95.2"}]
    files = _fixture(tmp_path, rows, gs)
    pkg = _run(tmp_path, files, bucket="AMZ_D", run_id="fba-test-d1")
    assert pkg.summary["status_counts"] == {"direct_purchase_zero": 1}
    assert pkg.summary["totals"]["绍兴二次加工成本"] == 0.0
    checks = {c["check"]: c["status"] for c in pkg.readback}
    assert checks["直采绍兴二次=0"] == "pass"
    assert checks["非目标列零变化"] == "pass"


def test_fba_canary_immutable_and_duplicate_fingerprint(tmp_path):
    rows = [_row("AMZ_B", "M-B1", "SKU-B1")]
    gs = [{"站点": "AMZ_B", "MSKU": "M-B1", "SKU": "SKU-B1", "销量": "1",
           "成本": "12", "头程费用": "3"}]
    old = [{"渠道账号": "AMZ_B", "平台SKU": "M-B1", "通途SKU": "SKU-B1",
            "发货数量": "1", "皮壳成本": "10", "绍兴二次加工成本": "2",
            "二次加工成本": "0", "头程运费金额": "3", "1件产品成本": "12",
            "发货仓分类": "FBA"}]
    files = _fixture(tmp_path, rows, gs, old)
    _run(tmp_path, files, run_id="fba-run-a")
    with pytest.raises(FileExistsError):
        _run(tmp_path, files, run_id="fba-run-a")
    with pytest.raises(RuntimeError):
        _run(tmp_path, files, run_id="fba-run-b")


def test_fba_canary_duplicate_keys_gate(tmp_path):
    rows = [
        _row("AMZ_X", "M-X1", "SKU-X1"),
        _row("AMZ_X", "M-X1", "SKU-X1"),  # 同 unique_key → 重复
    ]
    gs = [{"站点": "AMZ_X", "MSKU": "M-X1", "SKU": "SKU-X1", "销量": "1",
           "成本": "12", "头程费用": "3"}]
    files = _fixture(tmp_path, rows, gs)
    pkg = _run(tmp_path, files, run_id="fba-test-dup")
    assert not pkg.ok
    assert {g["gate"]: g["status"] for g in pkg.gates}["duplicate_keys"] == "fail"
    assert {c["check"]: c["status"] for c in pkg.readback}["键唯一"] == "fail"
