"""Tests for the supply-workbench single-file page generator (synthetic data only)."""
import base64
import csv
import hashlib
import json
import re

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


def _embedded_payload(html):
    opener = "<script type='application/json' id='supply-workbench-baseline'>"
    start = html.index(opener) + len(opener)
    end = html.index("</script>", start)
    return html[start:end]


def test_all_eight_tabs_present(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert len(TABS) == 8
    for key, title in TABS:
        assert f"data-t='{key}'" in html, key
        assert title in html, title
    assert "data-t='collab'>运营协同" in html
    assert "审核视角（模拟）" in html
    assert html.count("data-t=") == 8


def test_usnj_filter_keeps_only_usnj_rows(inputs):
    _, _, baseline = inputs
    assert len(filter_usnj(baseline)) == 2
    assert all(r["branch"] == "USNJ" for r in filter_usnj(baseline))


def test_counts_are_conserved(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    # 2 recommendation rows from the snapshot, 2 USNJ baseline rows (PL excluded).
    assert "USNJ 补货建议（2 行，只读）" in html
    assert "D5 整期需求基准（2 行，仅 USNJ）" in html
    assert "<b>2</b>USNJ 建议行" in html
    assert "<b>2</b>D5 需求基准行" in html
    # PL-only row must not leak into the embedded baseline data.
    assert "row-c" not in html
    assert "波兰商品" not in html


def test_copy_and_semantic_separation(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert "刷新或换浏览器会丢失" not in html
    assert "刷新保留；清理浏览器数据或换浏览器看不到本浏览器的提案" in html
    assert "保存本地演示提案" in html
    assert "模拟通过" in html and "模拟驳回" in html
    assert "审核视角（模拟）" in html
    assert "<dt>D5 整期需求基准</dt>" in html
    assert "仅演示需求提案，不修改 USNJ 补货建议，不进入采购" in html
    assert "不相加、不替代" in html


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
    payload_text = _embedded_payload(html)
    assert "<" not in payload_text
    assert ">" not in payload_text
    payload = json.loads(payload_text)
    assert len(payload["rows"]) == 2


def test_embed_json_round_trips_and_neutralizes_tags():
    text = embed_json({"v": "</script><script>alert(1)</script>", "q": "\"'"})
    assert "</" not in text and "<" not in text and ">" not in text
    assert json.loads(text)["v"] == "</script><script>alert(1)</script>"


def test_only_usnj_rows_embedded_with_real_counts(tmp_path):
    """1513 synthetic baseline rows (277 USNJ + 1236 other) -> only 277 embedded."""
    baseline_rows = []
    for i in range(277):
        baseline_rows.append({
            "id": f"usnj-{i}", "branch": "USNJ", "name": f"U{i}", "sku": f"EN:U{i}",
            "product_id": f"U{i}", "physical_form": "成品", "unit": "个",
            "week": "2026-11-02", "period_end": "2026-11-08",
            "baseline_qty": 1, "inventory_qty": None, "supply_note": "",
        })
    for i in range(1236):
        baseline_rows.append({
            "id": f"other-{i}", "branch": "PL" if i % 2 else "USTX", "name": f"O{i}",
            "sku": f"EN:O{i}", "product_id": f"O{i}", "physical_form": "成品",
            "unit": "个", "week": "2026-11-02", "period_end": "2026-11-08",
            "baseline_qty": 1, "inventory_qty": None, "supply_note": "",
        })
    assert len(baseline_rows) == 1513
    assert sum(1 for r in baseline_rows if r["branch"] == "USNJ") == 277
    assert sum(1 for r in baseline_rows if r["branch"] != "USNJ") == 1236

    snap_path = tmp_path / "snapshot.json"
    base_path = tmp_path / "baseline.json"
    snap_path.write_text(json.dumps({
        "as_of": "2026-11-13", "version": "synthetic", "rows": _snapshot_rows(),
    }, ensure_ascii=False), encoding="utf-8")
    base_path.write_text(json.dumps({
        "as_of": "2026-11-12", "version": "synthetic-baseline", "rows": baseline_rows,
    }, ensure_ascii=False), encoding="utf-8")

    html = build(snap_path, base_path)
    payload = json.loads(_embedded_payload(html))
    assert len(payload["rows"]) == 277
    assert {r["branch"] for r in payload["rows"]} == {"USNJ"}
    assert "other-" not in _embedded_payload(html)


def test_csp_present_and_hashes_match_scripts(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert 'http-equiv="Content-Security-Policy"' in html
    match = re.search(r'Content-Security-Policy" content="([^"]+)"', html)
    assert match, "CSP meta tag missing"
    csp = match.group(1)
    for directive in (
        "default-src 'none'",
        "style-src 'unsafe-inline'",
        "connect-src 'none'",
        "form-action 'none'",
        "base-uri 'none'",
        "img-src data:",
    ):
        assert directive in csp, directive

    script_src = [d.strip() for d in csp.split(";") if d.strip().startswith("script-src")]
    assert len(script_src) == 1
    assert "'unsafe-inline'" not in script_src[0]

    blocks = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    assert len(blocks) == 2
    for content in blocks:
        digest = base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode()
        assert ("'sha256-" + digest + "'") in script_src[0], "script hash missing from CSP"


def test_no_inline_event_attributes(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    for attr in (" onclick=", " onchange=", " onsubmit=", " oninput=", " onload="):
        assert attr not in html, attr
    for prop in (".onclick", ".onchange", ".onsubmit", ".oninput"):
        assert prop not in html, prop
    assert "addEventListener('click'" in html
    assert "addEventListener('submit'" in html


def test_storage_corruption_and_disabled_handling(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert STORAGE_KEY == "supply-workbench:proposals:v1"
    assert "window.localStorage.setItem(STORAGE_KEY" in html
    assert "window.localStorage.getItem(STORAGE_KEY" in html
    assert "Array.isArray(parsed)" in html
    assert "isValidProposal" in html
    assert "window.localStorage.removeItem(STORAGE_KEY)" in html
    assert "本地提案数据损坏，已丢弃" in html
    assert "浏览器已禁用本地存储" in html
    assert "probeStorage" in html
    assert "setFormEnabled(false)" in html
    assert "MIN_PERCENT = -100" in html
    assert "MIN_TOTAL = 0" in html
    assert "crypto.randomUUID" in html
    for kind in ("delta", "total", "percent", "event_only"):
        assert "'" + kind + "'" in html
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
        "src=",
        "href=",
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
