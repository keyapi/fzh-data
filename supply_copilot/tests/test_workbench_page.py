"""Tests for the supply-workbench single-file page generator (synthetic data only)."""
import csv
import json
import shutil
from pathlib import Path

import pytest

from supply_copilot.workbench_page import (
    STORAGE_KEY,
    TABS,
    build,
    embed_json,
    filter_usnj,
    main,
)

INJECT = '<script>alert("x")</script>'


def _snapshot_rows():
    return [
        {
            "sku": INJECT,
            "customer": "经销商A",
            "physical_form": "成品",
            "uom": "个",
            "action": "补货",
            "coverage": 45.0,
            "reason": "测试理由<&>",
            "forecast": 15,
            "q50": 10,
            "q90": 20,
            "q95": 30,
            "c_qty": 5,
            "e_qty": 7,
            "needs_decision": True,
            "low_confidence": True,
            "special": False,
            "ownership_pending": True,
            "extra": {"EN已发运量": 3},
            "so_lines": [],
        },
        {
            "sku": "KS2",
            "customer": "经销商B",
            "physical_form": "皮壳",
            "uom": "套",
            "action": "观察",
            "coverage": 90.0,
            "reason": "测试理由二",
            "forecast": 0,
            "q50": 0,
            "q90": 0,
            "q95": 0,
            "c_qty": 0,
            "e_qty": 0,
            "needs_decision": False,
            "low_confidence": False,
            "special": True,
            "ownership_pending": False,
            "extra": {},
            "so_lines": [],
        },
    ]


def _baseline_rows():
    return [
        {
            "id": "row-a",
            "branch": "USNJ",
            "name": "商品A<&>",
            "sku": "EN:KS1",
            "product_id": "KS1",
            "physical_form": "成品",
            "unit": "个",
            "week": "2026-11-02",
            "period_end": "2026-11-08",
            "baseline_qty": 12.5,
            "inventory_qty": None,
            "supply_note": "说明<&>",
        },
        {
            "id": "row-b",
            "branch": "USNJ",
            "name": "商品B",
            "sku": "EN:KS2",
            "product_id": "KS2",
            "physical_form": "皮壳",
            "unit": "套",
            "week": "2026-11-02",
            "period_end": "2026-11-08",
            "baseline_qty": 0,
            "inventory_qty": 4,
            "supply_note": "",
        },
        {
            "id": "row-c",
            "branch": "PL",
            "name": "波兰商品",
            "sku": "EN:KS3",
            "product_id": "KS3",
            "physical_form": "成品",
            "unit": "个",
            "week": "2026-11-02",
            "period_end": "2026-11-08",
            "baseline_qty": 99,
            "inventory_qty": None,
            "supply_note": "",
        },
    ]


@pytest.fixture()
def inputs(tmp_path):
    snap = {
        "as_of": "2026-11-13",
        "version": "test-pack",
        "source_name": "synthetic.csv",
        "rows": _snapshot_rows(),
    }
    baseline = {
        "as_of": "2026-11-12",
        "version": "test-baseline",
        "demo": True,
        "rows": _baseline_rows(),
    }
    snap_path = tmp_path / "snapshot.json"
    base_path = tmp_path / "baseline.json"
    snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    base_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    return snap_path, base_path, baseline


def test_all_eight_tabs_present(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert len(TABS) == 8
    for key, title in TABS:
        assert f"data-t='{key}'" in html, key
        assert title in html, title
    assert "data-t='collab'>运营协同" in html
    assert html.count("data-t=") == 8


def test_usnj_filter_keeps_only_usnj_rows(inputs):
    _, _, baseline = inputs
    assert len(filter_usnj(baseline)) == 2
    assert all(r["branch"] == "USNJ" for r in filter_usnj(baseline))


def test_counts_are_conserved(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    # 2 recommendation rows from the snapshot, 2 USNJ baseline rows (PL excluded).
    assert "建议 2 行" in html
    assert "需求基准 2 行" in html
    assert "<b>2</b>建议行" in html
    assert "<b>2</b>需求基准行" in html
    # PL-only row must not leak into the embedded baseline data.
    assert "row-c" not in html
    assert "波兰商品" not in html


def test_data_is_html_escaped(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert INJECT not in html
    assert "测试理由<&>" not in html
    # Python-side escaping of snapshot text.
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "测试理由&lt;&amp;&gt;" in html
    # Baseline names are only embedded as JSON, never raw HTML.
    assert "商品A<&>" not in html


def test_embedded_json_cannot_close_script_tag(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    opener = "<script type='application/json' id='supply-workbench-baseline'>"
    start = html.index(opener) + len(opener)
    end = html.index("</script>", start)
    payload_text = html[start:end]
    assert "<" not in payload_text
    assert ">" not in payload_text
    payload = json.loads(payload_text)
    assert len(payload["rows"]) == 2


def test_embed_json_round_trips_and_neutralizes_tags():
    text = embed_json({"v": "</script><script>alert(1)</script>", "q": "\"'"})
    assert "</" not in text and "<" not in text and ">" not in text
    assert json.loads(text)["v"] == "</script><script>alert(1)</script>"


def test_localstorage_contract_and_validation_constants(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert STORAGE_KEY == "supply-workbench:proposals:v1"
    assert "supply-workbench:proposals:v1" in html
    assert "window.localStorage.setItem(STORAGE_KEY" in html
    assert "window.localStorage.getItem(STORAGE_KEY" in html
    assert "MIN_PERCENT = -100" in html
    assert "MIN_TOTAL = 0" in html
    assert "crypto.randomUUID" in html
    for kind in ("delta", "total", "percent", "event_only"):
        assert "'" + kind + "'" in html
    assert "event_id" in html
    assert "reason" in html
    assert "status: 'submitted'" in html
    assert "inventory_qty === null" in html


def test_no_network_or_credentials(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "http://",
        "https://",
        "ERP_API",
        "api_key",
        "api_secret",
        "<link",
    ):
        assert forbidden not in html, forbidden


def test_b_dir_is_optional_and_renders_tables(tmp_path, inputs):
    snap_path, base_path, _ = inputs
    b_dir = tmp_path / "bdata"
    b_dir.mkdir()
    with (b_dir / "B_USNJ归属清单.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["product_id", "current_owner", "hist_pools", "标记", "2025总销量", "2026总销量"])
        writer.writerow(["SKU-X", "USNJ", "USNJ|USTX", "确认", "10", "20"])
    with (b_dir / "B_待确认.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["product_id", "current_owner", "hist_pools", "标记", "2025总销量", "2026总销量"])
        writer.writerow(["SKU-Y", "待确认", "", "待确认", "0", "0"])

    html = build(snap_path, base_path, b_dir)
    assert "B 归属清单（1 个 current USNJ）" in html
    assert "归属待确认（1 个）" in html
    assert "SKU-X" in html and "SKU-Y" in html

    # Without --b-dir the same build must still succeed.
    assert "B 归属清单（0 个 current USNJ）" in build(snap_path, base_path)


def test_cli_writes_single_file(tmp_path, inputs):
    snap_path, base_path, _ = inputs
    out = tmp_path / "out" / "workbench.html"
    main(["--snapshot", str(snap_path), "--baseline", str(base_path), "--out", str(out)])
    assert out.is_file()
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
