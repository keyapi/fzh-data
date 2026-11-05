# -*- coding: utf-8 -*-
"""Phase 3.6 测试：成本块 + 系数块补全（self/FBA/merged）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost.tongtu_cost_engine.domain.phase36_fill import (  # noqa: E402
    build_phase36,
)

SELF_COLS = ["订单号", "平台SKU", "平台SKU_统一", "通途SKU", "发货数量", "售价*汇率",
             "运费", "海外仓成本", "皮壳含包装成本", "皮壳不含包装成本",
             "绍兴成本系数", "二次加工成本系数", "绍兴二次加工成本系数"]
SRC_COLS = ["订单号", "通途SKU", "平台SKU_统一", "皮壳成本", "绍兴二次加工成本",
            "二次加工成本", "头程运费金额", "运费", "海外仓成本", "cost_status",
            "绍兴成本系数", "二次加工成本系数", "绍兴二次加工成本系数", "source_row"]
FBA_COLS = ["站点", "MSKU", "SKU", "发货数量", "售价*汇率", "销售额", "运费", "海外仓成本",
            "皮壳含包装成本", "皮壳不含包装成本", "绍兴成本系数", "二次加工成本系数",
            "绍兴二次加工成本系数"]


def _setup(tmp_path: Path):
    out = tmp_path / "out"
    (out / "snapshots" / "202608").mkdir(parents=True)
    pd.DataFrame([{"order_id_code": "O4", "invalid": "1"}]).to_csv(
        out / "snapshots" / "202608" / "order_flags.csv", index=False, encoding="utf-8")
    (out / "writeback_rehearsal" / "202608").mkdir(parents=True)
    (out / "fba_shadow" / "202608").mkdir(parents=True)

    self_t = pd.DataFrame([
        {"订单号": "O1", "平台SKU": "P1", "平台SKU_统一": "P1", "通途SKU": "S1",
         "发货数量": "2", "售价*汇率": "100", "运费": "5", "海外仓成本": "",
         "皮壳含包装成本": "11", "皮壳不含包装成本": "10",
         "绍兴成本系数": "1.2", "二次加工成本系数": "0", "绍兴二次加工成本系数": "1"},
        {"订单号": "O1", "平台SKU": "P2", "平台SKU_统一": "P2", "通途SKU": "C1",
         "发货数量": "2", "售价*汇率": "100", "运费": "5", "海外仓成本": "",
         "皮壳含包装成本": "11", "皮壳不含包装成本": "10",
         "绍兴成本系数": "", "二次加工成本系数": "", "绍兴二次加工成本系数": ""},
        {"订单号": "O3", "平台SKU": "P3", "平台SKU_统一": "P3", "通途SKU": "S2",
         "发货数量": "1", "售价*汇率": "50", "运费": "0", "海外仓成本": "",
         "皮壳含包装成本": "", "皮壳不含包装成本": "",
         "绍兴成本系数": "", "二次加工成本系数": "", "绍兴二次加工成本系数": ""},
        {"订单号": "O4", "平台SKU": "P4", "平台SKU_统一": "P4", "通途SKU": "S4",
         "发货数量": "1", "售价*汇率": "60", "运费": "0", "海外仓成本": "",
         "皮壳含包装成本": "9", "皮壳不含包装成本": "8",
         "绍兴成本系数": "1", "二次加工成本系数": "1", "绍兴二次加工成本系数": "1"},
    ], columns=SELF_COLS)
    self_t.to_csv(out / "wb_fresh_202608.csv", index=False, encoding="utf-8")

    src = pd.DataFrame([
        {"订单号": "O1", "通途SKU": "S1", "平台SKU_统一": "P1", "皮壳成本": "10",
         "绍兴二次加工成本": "2", "二次加工成本": "1", "头程运费金额": "3",
         "运费": "5", "海外仓成本": "0", "cost_status": "ok",
         "绍兴成本系数": "1.2", "二次加工成本系数": "0", "绍兴二次加工成本系数": "1",
         "source_row": "0"},
        {"订单号": "O3", "通途SKU": "S2", "平台SKU_统一": "P3", "皮壳成本": "4",
         "绍兴二次加工成本": "1", "二次加工成本": "0", "头程运费金额": "2",
         "运费": "0", "海外仓成本": "0", "cost_status": "ok",
         "绍兴成本系数": "", "二次加工成本系数": "", "绍兴二次加工成本系数": "",
         "source_row": "1"},
    ], columns=SRC_COLS)
    src.to_csv(out / "writeback_rehearsal" / "202608" / "writeback_new_202608.csv",
               index=False, encoding="utf-8")

    old = pd.DataFrame([
        {"订单号": "O1", "通途SKU": "S1", "平台SKU": "P1", "皮壳成本": "10",
         "皮壳含包装成本": "11", "皮壳不含包装成本": "10",
         "绍兴成本系数": "1.2", "二次加工成本系数": "0", "绍兴二次加工成本系数": "1"},
        {"订单号": "O4", "通途SKU": "S4", "平台SKU": "P4", "皮壳成本": "8",
         "皮壳含包装成本": "9", "皮壳不含包装成本": "8",
         "绍兴成本系数": "1", "二次加工成本系数": "1", "绍兴二次加工成本系数": "1"},
        {"订单号": "O1", "通途SKU": "C1", "平台SKU": "P2", "皮壳成本": "0",
         "皮壳含包装成本": "0", "皮壳不含包装成本": "0",
         "绍兴成本系数": "1.5", "二次加工成本系数": "0", "绍兴二次加工成本系数": "1"},
    ])
    old.to_csv(out / "writeback_202608.csv", index=False, encoding="utf-8")

    fba_t = pd.DataFrame([
        {"站点": "AMZ_A", "MSKU": "M1", "SKU": "F1", "发货数量": "8",
         "售价*汇率": "80", "销售额": "80", "运费": "0", "海外仓成本": "",
         "皮壳含包装成本": "4", "皮壳不含包装成本": "4",
         "绍兴成本系数": "1", "二次加工成本系数": "1", "绍兴二次加工成本系数": "1"},
        {"站点": "AMZ_A", "MSKU": "M1", "SKU": "F1", "发货数量": "0",
         "售价*汇率": "0", "销售额": "0", "运费": "0", "海外仓成本": "",
         "皮壳含包装成本": "4", "皮壳不含包装成本": "4",
         "绍兴成本系数": "1", "二次加工成本系数": "1", "绍兴二次加工成本系数": "1"},
    ], columns=FBA_COLS)
    fba_t.to_csv(out / "wb_fba_202608.csv", index=False, encoding="utf-8")

    sh = pd.DataFrame([
        {"site": "AMZ_A", "平台SKU": "M1", "通途SKU": "F1", "bridge_status": "ok",
         "皮壳成本": "4", "绍兴二次加工成本": "3", "二次加工成本": "0",
         "头程运费金额": "2"},
    ])
    sh.to_csv(out / "fba_shadow" / "202608" / "fba_shadow_202608.csv",
              index=False, encoding="utf-8")

    merged = pd.DataFrame([
        {"订单号": "O1", "平台SKU": "P1", "通途SKU": "S1", "渠道账号": "",
         "发货数量": "2", "售价*汇率": "100", "运费": "5", "海外仓成本": ""},
        {"订单号": "O1", "平台SKU": "P2", "通途SKU": "C1", "渠道账号": "",
         "发货数量": "2", "售价*汇率": "100", "运费": "5", "海外仓成本": ""},
        {"订单号": "O3", "平台SKU": "P3", "通途SKU": "S2", "渠道账号": "",
         "发货数量": "1", "售价*汇率": "50", "运费": "0", "海外仓成本": ""},
        {"订单号": "O4", "平台SKU": "P4", "通途SKU": "S4", "渠道账号": "",
         "发货数量": "1", "售价*汇率": "60", "运费": "0", "海外仓成本": ""},
        {"订单号": "FB1", "平台SKU": "M1", "通途SKU": "F1", "渠道账号": "AMZ_A",
         "发货数量": "8", "售价*汇率": "80", "运费": "0", "海外仓成本": ""},
        {"订单号": "FB2", "平台SKU": "M1", "通途SKU": "F1", "渠道账号": "AMZ_A",
         "发货数量": "0", "售价*汇率": "0", "运费": "0", "海外仓成本": ""},
    ])
    merged.to_csv(out / "merged_202608.csv", index=False, encoding="utf-8")
    return tmp_path


def test_phase36_fills_cost_and_coef_blocks(tmp_path):
    _setup(tmp_path)
    res = build_phase36(month="202608", root=tmp_path)
    assert res["summary"]["rows"] == {"self": 4, "fba": 2, "merged": 6}
    assert res["summary"]["violations"] == {"self": 0, "fba": 0, "merged": 0}
    assert res["summary"]["blocks"] == {"coef_conflict": 1, "invalid_original": 1}
    assert res["summary"]["invalid_original_rows"] == 1
    assert res["summary"]["recon_95_78"] == {"metric_diffs": 0, "key_diff_rows": 0}
    assert res["summary"]["overlap_self_fba"] == 0
    out = Path(res["out_dir"])

    s = pd.read_csv(out / "wb_fresh_202608.csv", dtype=str, keep_default_na=False)
    o1 = s[s["通途SKU"] == "S1"].iloc[0].to_dict()
    assert o1["皮壳成本"] == "10" and o1["绍兴二次加工成本"] == "2"
    assert o1["1件产品成本"] == "13" and o1["产品成本*数量"] == "26"
    assert o1["订单总成本"] == "37" and o1["订单利润"] == "63"
    assert o1["皮壳成本*系数"] == "12" and o1["绍兴二次加工成本*系数"] == "2"
    assert o1["二次加工成本*系数"] == "0" and o1["1件产品成本*系数"] == "14"
    assert o1["订单总成本*系数"] == "39" and o1["订单利润*系数"] == "61"
    # 组内系数冲突 → 阻断留空
    o2 = s[s["通途SKU"] == "C1"].iloc[0].to_dict()
    assert o2["cost_status"] == "coef_conflict"
    assert o2["皮壳成本"] == "" and o2["1件产品成本"] == ""
    # 基础系数空 → 保留空；派生按 1.0 计算
    o3 = s[s["通途SKU"] == "S2"].iloc[0].to_dict()
    assert o3["绍兴成本系数"] == ""
    assert o3["皮壳成本*系数"] == "4" and o3["1件产品成本*系数"] == "5"

    f = pd.read_csv(out / "wb_fba_202608.csv", dtype=str, keep_default_na=False)
    f1 = f[f["发货数量"] == "8"].iloc[0].to_dict()
    assert f1["1件产品成本"] == "7" and f1["产品成本*数量"] == "56"
    assert f1["订单总成本"] == "72" and f1["订单利润"] == "8"
    f0 = f[f["发货数量"] == "0"].iloc[0].to_dict()
    assert f0["产品成本*数量"] == "0" and f0["订单利润"] == "0"

    m = pd.read_csv(out / "merged_202608.csv", dtype=str, keep_default_na=False)
    assert m.iloc[0]["1件产品成本"] == "13"
    assert m[m["通途SKU"] == "F1"].iloc[0]["1件产品成本"] == "7"
    for name in ("crosswalk_self.csv", "crosswalk_fba.csv", "fill_rates.csv",
                 "blanks.csv", "summary.md", "manifest.json",
                 "recon_95_78.csv", "recon_95_78_totals.csv", "overlap_self_fba.csv",
                 "invalid_original_backup.csv"):
        assert (out / name).exists()
    # 作废原单：保留行与销售，成本/系数全空，旧值只进备份
    o4 = s[s["通途SKU"] == "S4"].iloc[0].to_dict()
    assert o4["cost_status"] == "invalid_original"
    assert o4["售价*汇率"] == "60"
    assert o4["皮壳成本"] == "" and o4["1件产品成本"] == "" and o4["订单利润"] == ""
    assert o4["绍兴成本系数"] == "" and o4["产品成本*系数*数量"] == ""
    backup = pd.read_csv(out / "invalid_original_backup.csv", dtype=str, keep_default_na=False)
    assert len(backup) == 1 and backup.iloc[0]["皮壳成本"] == "8"
    # GS-ready：严格模板列，无审计列
    for name, cols in (("self", SELF_COLS), ("fba", FBA_COLS)):
        gs_file = {"self": "wb_fresh_202608.csv", "fba": "wb_fba_202608.csv"}[name]
        gs = pd.read_csv(out / "gs_ready" / gs_file, dtype=str, keep_default_na=False)
        assert list(gs.columns) == cols
    gs_m = pd.read_csv(out / "gs_ready" / "merged_202608.csv", dtype=str, keep_default_na=False)
    assert "cost_status" not in gs_m.columns and len(gs_m) == 6
