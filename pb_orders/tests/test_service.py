#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务层：成功路径、硬校验失败、无货拆分、离线缓存缺失。"""

from __future__ import annotations

import pytest

import service

from conftest import SKUS, write_order_csv, write_packslip_pdf


def test_extracts_pdf_pages(pb_env):
    df = service.sps_pb_pdf.build_page_df(pb_env.pdf)
    assert len(df) == 3
    assert int(df[service.sps_pb_pdf.COL_PO].isna().sum()) == 0
    assert int(df[service.sps_pb_pdf.COL_ITEM].isna().sum()) == 0


def test_order_csv_expands_to_page_count(pb_env):
    df = service.pb_tongtu_excel.build_order_df(pb_env.csv)
    assert len(df) == 3
    assert df.shape[1] <= 100


def test_full_run_produces_expected_artifacts(pb_env):
    out = pb_env.tmp / "out"
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(cache_only=True, sku_cache_path=pb_env.cache),
        out,
    )
    kinds = {a.kind for a in result.artifacts}
    assert kinds == {"tongtool", "label", "back_label"}

    label = next(a for a in result.artifacts if a.kind == "label")
    back = next(a for a in result.artifacts if a.kind == "back_label")
    assert label.path.is_file() and back.path.is_file()
    # 3 页输入 -> 6 页标签（每页拆打包单 + UPS 面单）
    assert result.report["outputs"][1]["pages"] == 6
    assert result.report["outputs"][2]["pages"] == 3


def test_reconciliation_is_balanced(pb_env):
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(cache_only=True, sku_cache_path=pb_env.cache),
        pb_env.tmp / "out",
    )
    for row in result.report["reconciliation"]:
        assert row["diff"] == 0, row
    assert result.report["one_to_one"]["ok"] is True
    assert result.report["join"]["unmatched"] == 0


def test_validate_only_writes_nothing(pb_env):
    out = pb_env.tmp / "out"
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(validate_only=True, cache_only=True, sku_cache_path=pb_env.cache),
        out,
    )
    assert result.artifacts == []
    assert not out.exists() or not any(out.iterdir())
    assert result.report["validate_only"] is True


def test_dry_run_without_output_dir_ignores_outputs(pb_env):
    result = service.run_job(pb_env.pdf, pb_env.csv, service.JobOptions())
    assert result.artifacts == []
    assert result.report["pdf"]["pages"] == 3


def test_no_stock_split_produces_separate_subsets(pb_env):
    out = pb_env.tmp / "out"
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(no_stock=["STYLE-B"], cache_only=True, sku_cache_path=pb_env.cache),
        out,
    )
    kinds = {a.kind for a in result.artifacts}
    assert kinds == {
        "tongtool", "tongtool_no_stock", "tongtool_importable",
        "label", "back_label", "label_no_stock", "back_label_no_stock",
    }
    split = result.report["split"]
    assert split["enabled"] is True
    assert split["in_stock_pages"] == 2 and split["no_stock_pages"] == 1
    # 主标签只有有货页：2 页 -> 4 页；无货子集 1 页 -> 2 页
    pages = {o["kind"]: o.get("pages") for o in result.report["outputs"]}
    assert pages["label"] == 4
    assert pages["label_no_stock"] == 2
    assert pages["back_label"] == 2
    assert pages["back_label_no_stock"] == 1
    # 总数必须等于各分项之和，否则对账列自相矛盾
    rec = {r["label"]: r for r in result.report["reconciliation"]}
    assert rec["标签页"]["total"] == 6 and rec["标签页"]["diff"] == 0
    assert rec["背贴页"]["total"] == 3 and rec["背贴页"]["diff"] == 0
    for row in result.report["reconciliation"]:
        assert row["diff"] == 0, row


def test_no_stock_without_hit_warns_and_keeps_full_output(pb_env):
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(no_stock=["NOT-IN-BATCH"], cache_only=True, sku_cache_path=pb_env.cache),
        pb_env.tmp / "out",
    )
    assert result.report["split"]["enabled"] is False
    assert any("本批都没有" in w for w in result.report["warnings"])


def test_one_to_one_mismatch_raises(pb_env):
    extra = write_packslip_pdf(
        pb_env.tmp / "Packslip extra.pdf",
        [("137943090", "1069914"), ("137943090", "1069915"),
         ("137943091", "1069916"), ("137943099", "1069917")],
    )
    with pytest.raises(service.PBJobError) as exc:
        service.run_job(extra, pb_env.csv, service.JobOptions(), pb_env.tmp / "out")
    assert exc.value.code == "one_to_one_failed"
    assert "Qty per Carton" in exc.value.hint


def test_join_unmatched_raises_and_can_be_allowed(pb_env):
    bad_csv = write_order_csv(
        pb_env.tmp / "mismatch.csv",
        rows=[
            ("137943090", "2", "D", 1, "STYLE-A", 10.0, "USA", "2026-09-21"),
            ("137943090", "1", "D", 1, "STYLE-B", 12.0, "USA", "2026-09-21"),
            ("137943091", "1", "D", 1, "STYLE-C", 9.0, "USA", "2026-09-21"),
        ],
        # catalog 全部改名，制造未匹配
        catalogs=["9999991", "9999992", "9999993"],
    )

    with pytest.raises(service.PBJobError) as exc:
        service.run_job(pb_env.pdf, bad_csv, service.JobOptions(), pb_env.tmp / "out")
    assert exc.value.code == "join_unmatched"

    allowed = service.run_job(
        pb_env.pdf, bad_csv,
        service.JobOptions(allow_unmatched=True, cache_only=True, sku_cache_path=pb_env.cache),
        pb_env.tmp / "out2",
    )
    assert allowed.report["join"]["unmatched"] == 3


def test_missing_cache_in_cache_only_mode_fails(pb_env):
    with pytest.raises(FileNotFoundError):
        service.run_job(
            pb_env.pdf, pb_env.csv,
            service.JobOptions(cache_only=True, sku_cache_path=pb_env.tmp / "nope.csv"),
            pb_env.tmp / "out",
        )


def test_missing_input_raises(pb_env):
    with pytest.raises(service.PBJobError) as exc:
        service.run_job(pb_env.tmp / "gone.pdf", pb_env.csv)
    assert exc.value.code == "input_missing"


def test_shipment_report_flags_short_skus(pb_env):
    import pandas as pd

    asn = pb_env.tmp / "shipment x3.csv"
    pd.DataFrame({
        "Vdr Item #": [SKUS["1069914"], SKUS["1069915"], SKUS["1069916"]],
        "Qty Ship": ["1", "1", "0"],
    }).to_csv(asn, index=False)

    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(check_shipment=True, cache_only=True, sku_cache_path=pb_env.cache),
        pb_env.tmp / "out",
        shipment_csv=asn,
    )
    short = {s["sku"]: s for s in result.report["shipment"]["short"]}
    assert "STYLE-C" in short
    assert short["STYLE-C"]["diff"] == -1


def test_scan_dir_picks_latest_inputs(pb_env):
    result = service.scan_dir(pb_env.tmp, options=service.JobOptions(validate_only=True))
    assert result.report["inputs"]["packslip"] == pb_env.pdf.name
    assert result.report["inputs"]["order_csv"] == pb_env.csv.name


def test_tongtool_name_uses_csv_stem_by_default(pb_env):
    """命令行路径：产物名用订单 CSV 自己的词干（与从前一致）。"""
    out = pb_env.tmp / "out-cli"
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(cache_only=True, sku_cache_path=pb_env.cache),
        out,
    )
    tongtool = next(a for a in result.artifacts if a.kind == "tongtool")
    assert tongtool.path.name.startswith(f"PB_0_导入_原始_{pb_env.csv.stem}_on_")


def test_tongtool_name_prefers_options_csv_stem(pb_env):
    """网页路径：磁盘名固定是 order.csv，得用页面上的原始文件名词干命名。

    回归：以前网页出的产物叫 `PB_0_导入_原始_order_on_…`，看不出是哪一批。
    """
    out = pb_env.tmp / "out-web"
    result = service.run_job(
        pb_env.pdf, pb_env.csv,
        service.JobOptions(
            cache_only=True, sku_cache_path=pb_env.cache,
            csv_stem="checked0stock order x40 20260921_0159_334423",
        ),
        out,
    )
    tongtool = next(a for a in result.artifacts if a.kind == "tongtool")
    assert tongtool.path.name.startswith(
        "PB_0_导入_原始_checked0stock order x40 20260921_0159_334423_on_"
    )


def test_tongtool_name_sanitizes_unsafe_and_empty_stems(pb_env):
    """词干来自用户文件名，必须洗掉非法字符；洗空了就回落。"""
    assert service._output_csv_stem(
        service.JobOptions(csv_stem="批次: 2026/09?*"), pb_env.csv
    ) == "批次- 2026-09"   # 非法字符换 -，再剥掉首尾的空白/点/横线
    assert service._output_csv_stem(service.JobOptions(csv_stem="..."), pb_env.csv) == "order"
    assert service._output_csv_stem(service.JobOptions(), pb_env.csv) == pb_env.csv.stem


def test_order_csv_missing_required_column_says_which(pb_env):
    """缺列时要说清楚缺哪几列，不能只给 `KeyError: 'Ship To Country'`。

    回归：实测拿 7 列的瘦 CSV 走出件，页面只显示「输入数据有问题：'Ship To Country'」。
    """
    import pandas as pd

    thin = pb_env.tmp / "thin.csv"
    pd.DataFrame({
        "PO Number": ["137943090"], "PO Line #": ["1"], "Record Type": ["D"],
        "Qty Ordered": ["1"], "Vendor Style": ["STYLE-A"],
        "Buyers Catalog or Stock Keeping #": ["1069914"], "Customer Order #": ["USA"],
    }).to_csv(thin, index=False)

    with pytest.raises(ValueError) as exc:
        service.pb_tongtu_excel.build_order_df(thin)
    message = str(exc.value)
    assert "Ship To Country" in message and "Unit Price" in message
    assert "缺少必需列" in message
    assert "**" not in message  # 纯文本，别混 markdown 记号


def test_missing_column_becomes_readable_pbjob_error(pb_env):
    """经 service 跑时，缺列要变成带正确指引的 PBJobError（不是通用「不是同一批」）。"""
    import pandas as pd

    thin = pb_env.tmp / "thin2.csv"
    pd.DataFrame({
        "PO Number": ["137943090"], "Record Type": ["D"], "Qty Ordered": ["1"],
        "Vendor Style": ["STYLE-A"],
    }).to_csv(thin, index=False)

    with pytest.raises(service.PBJobError) as exc:
        service.run_job(pb_env.pdf, thin, service.JobOptions(validate_only=True))
    assert exc.value.code == "order_csv_invalid"
    assert "缺少必需列" in exc.value.message
    assert "订单 CSV 重新提交" in exc.value.hint


def test_full_width_sample_has_every_required_column(pb_env):
    """正常夹具（含全部必需列）不该被上面那道检查挡住。"""
    df = service.pb_tongtu_excel.build_order_df(pb_env.csv)
    assert len(df) == 3
