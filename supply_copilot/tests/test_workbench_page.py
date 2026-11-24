"""Tests for the supply-workbench single-file page generator (synthetic data only).

Step-1 UI migration: four first-class views (工作台 / 证据链 / 分析方法 / 口径),
local-workbench visual tokens, and a before/after parity check that A–E rows and
field values are unchanged.
"""
import base64
import csv
import hashlib
import html as htmllib
import json
import re
import shutil
import subprocess

import pytest

from supply_copilot.workbench_page import (
    ANALYSIS_TABS,
    COLLAB_LIB,
    LEGACY_STORAGE_KEY,
    STORAGE_KEY,
    VIEWS,
    build,
    embed_json,
    filter_usnj,
    main,
    reconcile,
)

INJECT = '<script>alert("x")</script>'


def _snapshot_rows():
    return [
        {
            "sku": INJECT,
            "customer": "经销商A",
            "physical_form": "成品",
            "uom": "个",
            "action": "补",
            "coverage": 45.0,
            "reason": "测试理由<&>",
            "forecast": 15,
            "q50": 10,
            "q90": 20,
            "q95": 30,
            "c_qty": 5,
            "e_qty": 7,
            "new_qty": 20,
            "expedite_qty": 0,
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
        {
            # Unknowns must stay unknown (never 0); key matches baseline row-b.
            "sku": "EN:KS2",
            "customer": "经销商B",
            "physical_form": "皮壳",
            "uom": "套",
            "action": "观察",
            "coverage": None,
            "reason": None,
            "forecast": None,
            "q50": None,
            "q90": None,
            "q95": None,
            "c_qty": None,
            "e_qty": None,
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
    opener = "<script type='application/json' id='supply-workbench-data'>"
    start = html.index(opener) + len(opener)
    end = html.index("</script>", start)
    return html[start:end]


def _pane(html, key):
    start = html.index("id='pane-%s'" % key)
    end = html.find("id='pane-", start + 1)
    if end < 0:
        end = html.find("</section>", start)
    return html[start:end]


def _table_rows(fragment):
    """Parse every <table> in a fragment into lists of cell text lists."""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", fragment, re.S)
    out = []
    for table in tables:
        if "<tbody>" not in table:
            continue
        body = table.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            cells = [htmllib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<td>(.*?)</td>", tr, re.S)]
            rows.append(cells)
        out.append(rows)
    return out


def _f(v):
    """Independent re-implementation of the pre-change integer formatting."""
    try:
        return f"{round(float(v)):,}"
    except Exception:
        return "—"


def _x(row, key):
    v = (row.get("extra") or {}).get(key)
    return _f(v) if v not in (None, "") else "—"


def _function_body(js, name):
    start = js.index("function " + name + "(")
    end = js.find("\n  function ", start + 1)
    return js[start:end if end > 0 else len(js)]


# ---------------------------------------------------------------- views


def test_four_first_class_views():
    assert [k for k, _ in VIEWS] == ["workbench", "evidence", "analysis", "method"]
    assert len(VIEWS) == 4
    assert len(ANALYSIS_TABS) == 5


def test_views_reachable_in_markup(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    for key, title in VIEWS:
        assert f"data-view='{key}'" in html, key
        assert f"id='view-{key}'" in html, key
        assert title in html, title
    for key, title in ANALYSIS_TABS:
        assert f"data-pane='{key}'" in html, key
        assert title in html, title
        assert f"id='pane-{key}'" in html, key
    # The old eight parallel tabs are gone.
    assert "data-t='" not in html
    assert html.count("data-view='") == 4


def test_demo_banner_and_separated_capability_chips(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert ("静态演示 · 数据快照 2026-11-13 · 提案只存本浏览器 · "
            "不上传/不审批/不写 EN") in html
    assert "静态内嵌快照（无后端）" in html
    assert "快照时点 2026-11-13（非实时）" in html
    assert "只读，不可下单" in html
    # Service / freshness / eligibility must not borrow a green "go" token.
    for green in ("#46745e", "#46745E", "#1d6b4f", "#2f6f4f", "#dff3ea", "#e5eee7"):
        assert green not in html, green
    assert "实时库存正常" not in html


def test_workbench_layout_is_local_left_table_right_detail(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    for marker in (
        "class='workspace' id='workspace'",
        "class='board'",
        "class='detail' id='wb-detail'",
        "--navy:#172e43",
        "--paper:#f5f4ef",
        "--orange:#df6b34",
        "grid-template-columns:minmax(0,1fr) 400px",
        "@media (max-width:1199px)",
        "@media (max-width:959px)",
        "@media (max-width:767px)",
    ):
        assert marker in html, marker
    # Detail starts collapsed: no row-level inline expansion markup.
    assert "<tr class=\"detail\">" not in html
    assert "<tr class='detail'>" not in html


def test_suggestions_are_readonly_baseline_has_proposal_form(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert "补货建议（只读）" in html
    assert "需求基准（可演示提案）" in html
    assert "建议只读；演示提案只对「需求基准」行开放。" in html
    js = html.split("<script>", 1)[1]
    assert js.count("proposalForm(") == 2  # one definition, one call
    assert "proposalForm(" in _function_body(js, "renderBaseDetail")
    assert "proposalForm(" not in _function_body(js, "renderRecDetail")
    assert "保存演示提案（本浏览器）" in html


# ------------------------------------------------- A–E parity (before/after)


def test_analysis_rows_and_fields_match_pre_change_semantics(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    rows = _snapshot_rows()

    # A: deduped SKU x form x UOM x customer universe.
    a_expected = sorted(
        {(r.get("sku"), r.get("physical_form"), r.get("uom"), r.get("customer")) for r in rows},
        key=lambda t: tuple("" if v is None else str(v) for v in t),
    )
    a_tables = _table_rows(_pane(html, "a"))
    assert len(a_tables) == 1
    assert len(a_tables[0]) == len(a_expected) == 3
    for got, want in zip(a_tables[0], a_expected):
        assert got == [str(v) if v is not None else "" for v in want]

    # C and E keep all nine columns, one row per snapshot row, values unchanged.
    supply_expected = [
        [r["sku"], _f(r.get("c_qty")), _x(r, "EN已发运量"), _x(r, "EN待发量"),
         _x(r, "PO追加(去重)"), _x(r, "SO已下"), _x(r, "CG可调拨抵扣"),
         _f(r.get("so_recent_open_qty")), _f(r.get("so_history_open_qty"))]
        for r in rows
    ]
    for key in ("c", "e"):
        tables = _table_rows(_pane(html, key))
        assert len(tables) == 1
        assert tables[0] == supply_expected, key

    # D keeps the six forecast columns.
    d_expected = [
        [r["sku"], _f(r.get("forecast")), _f(r.get("q50")), _f(r.get("q90")),
         _f(r.get("q95")), r.get("model") or "—"]
        for r in rows
    ]
    d_tables = _table_rows(_pane(html, "d"))
    assert d_tables[0] == d_expected

    # Row counts are conserved: 3 snapshot rows -> 3 C rows, 3 D rows, 3 E rows.
    assert "A 商品范围（3 个 SKU×形态×UOM，去重）" in html


def test_unknowns_stay_dash_and_zero_stays_zero(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    c_rows = _table_rows(_pane(html, "c"))[0]
    # Row 2 really is zero.
    assert c_rows[1][1] == "0"
    # Row 3 fields are missing -> em dash, never 0.
    assert c_rows[2][1] == "—"
    d_rows = _table_rows(_pane(html, "d"))[0]
    assert d_rows[2][1] == "—" and d_rows[0][1] == "15"


def test_b_tables_still_render_both_lists(tmp_path, inputs):
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
    tables = _table_rows(_pane(html, "b"))
    assert tables[0][0] == ["SKU-X", "USNJ", "USNJ|USTX", "确认", "10", "20"]
    assert tables[1][0] == ["SKU-Y", "待确认", "", "待确认", "0", "0"]

    # Without --b-dir the same build must still succeed with empty B lists.
    plain = build(snap_path, base_path)
    assert "B 归属清单（0 个 current USNJ）" in plain
    assert "归属待确认（0 个）" in plain


# ------------------------------------------------------------- evidence view


def test_evidence_view_sections_exist(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    for section in (
        "身份与期间",
        "需求（预测分位，不加进建议量）",
        "供给各阶段",
        "SO 三段（近期 / 历史 / 未知）",
        "库存快照与当前观察",
        "来源与哈希",
        "未知与未接入原因",
        "对单与抽查",
    ):
        assert section in html, section
    for reason in (
        "缺失＝未知，不补 0",
        "source_hash 缺失＝行哈希未记录（无伪链接）",
        "未接入（不是 0）",
        "静态页不可得",
        "本次查看已核对（不持久化、不代表已批准）",
    ):
        assert reason in html, reason
    assert "data-ev-prev" in html and "data-ev-next" in html


def test_evidence_covers_every_snapshot_row(inputs):
    snap_path, base_path, _ = inputs
    payload = json.loads(_embedded_payload(build(snap_path, base_path)))
    assert len(payload["rows"]) == 3
    assert payload["rows"][0]["sku"] == INJECT
    # Values are embedded verbatim: nulls stay null, not 0.
    assert payload["rows"][2]["e_qty"] is None


# ------------------------------------------------------------- reconciliation


def test_reconcile_counts_are_conserved(inputs):
    _, _, baseline = inputs
    rec, base = _snapshot_rows(), filter_usnj(baseline)
    recon = reconcile(rec, base)
    assert recon["rec_total"] == 3
    assert recon["base_total"] == 2
    assert recon["unique"] == 1          # EN:KS2|皮壳|套
    assert recon["only_rec"] == 2
    assert recon["only_base"] == 1       # EN:KS1|成品|个
    assert recon["ambiguous"] == []
    assert recon["rec_total"] - recon["unique"] == recon["only_rec"]
    assert recon["base_total"] - recon["unique"] == recon["only_base"]


def test_reconcile_flags_sku_only_ambiguity():
    rec = [
        {"sku": "KS9", "physical_form": "成品", "uom": "个"},
        {"sku": "KS9", "physical_form": "皮壳", "uom": "个"},
    ]
    base = [
        {"sku": "KS9", "physical_form": "成品", "unit": "个"},
        {"sku": "KS9", "physical_form": "皮壳", "unit": "个"},
    ]
    recon = reconcile(rec, base)
    # SKU alone would be one-to-many; SKU x form x UOM resolves it.
    assert recon["sku_only_ambiguous"] == 1
    assert recon["unique"] == 2 and recon["ambiguous"] == []
    assert recon["key"] == "SKU×形态×单位"


# ------------------------------------------------------------- safety: CSP


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


def test_no_inline_event_attributes(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    for attr in (" onclick=", " onchange=", " onsubmit=", " oninput=", " onload="):
        assert attr not in html, attr
    for prop in (".onclick", ".onchange", ".onsubmit", ".oninput"):
        assert prop not in html, prop
    assert "addEventListener('click'" in html
    assert "addEventListener('submit'" in html


# ------------------------------------------------------------- escaping/data


def test_data_is_embedded_and_never_terminates_the_script(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    payload_text = _embedded_payload(html)
    assert INJECT not in html
    assert "测试理由<&>" not in html
    assert "商品A<&>" not in html
    assert "<" not in payload_text and ">" not in payload_text
    payload = json.loads(payload_text)
    assert payload["rows"][0]["sku"] == INJECT
    assert payload["rows"][0]["reason"] == "测试理由<&>"
    assert payload["baseline"]["rows"][0]["name"] == "商品A<&>"
    # Client-side escaping is the only path snapshot text reaches the DOM.
    assert "escapeHtml" in html


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
    assert len(payload["baseline"]["rows"]) == 277
    assert {r["branch"] for r in payload["baseline"]["rows"]} == {"USNJ"}
    assert "other-" not in _embedded_payload(html)
    assert "波兰商品" not in html


def test_filter_usnj_keeps_only_usnj_rows(inputs):
    _, _, baseline = inputs
    assert len(filter_usnj(baseline)) == 2
    assert all(r["branch"] == "USNJ" for r in filter_usnj(baseline))


# ------------------------------------------------------------- storage copy


def test_storage_keys_and_degraded_modes(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert STORAGE_KEY == "supply-workbench:proposals:v2"
    assert LEGACY_STORAGE_KEY == "supply-workbench:proposals:v1"
    assert "readStorage(storage, STORAGE_KEY)" in html
    assert "writeStorage(storage, STORAGE_KEY, list)" in html
    assert "probeStorageAvailable(storage, STORAGE_KEY)" in html
    assert "storageOrNull()" in html
    assert "throw on property access alone" in html
    assert "Array.isArray(parsed)" in html
    assert "isValidProposal" in html
    assert "parseProposals" in html
    assert "storage.removeItem(key)" in html
    assert "本地提案数据损坏，已丢弃" in html
    assert "浏览器已禁用本地存储" in html
    assert "setFormEnabled(false)" in html
    assert "MIN_PERCENT = -100" in html
    assert "MIN_TOTAL = 0" in html
    assert "crypto.randomUUID" in html
    assert "supply-workbench:proposals:v1" in html
    assert "只读展示，不迁移、不删除" in html
    for kind in ("delta", "total", "percent", "event_only"):
        assert "'" + kind + "'" in html
    assert "status: 'submitted'" in html


def test_cli_writes_single_file(tmp_path, inputs):
    snap_path, base_path, _ = inputs
    out = tmp_path / "out" / "workbench.html"
    main(["--snapshot", str(snap_path), "--baseline", str(base_path), "--out", str(out)])
    assert out.is_file()
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


# ------------------------------------------------------------- node execution


def _run_node(tmp_path, body):
    """Execute the page's pure JS library under Node and parse its JSON output."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js 不可用，跳过执行级 JS 测试")
    script = tmp_path / "collab_lib_test.js"
    script.write_text(COLLAB_LIB + "\n" + body, encoding="utf-8")
    proc = subprocess.run(
        [node, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_unknown_is_null_not_zero_in_node(tmp_path):
    out = _run_node(tmp_path, """
const out = {};
out.nullQty = formatQty(null);
out.undefinedQty = formatQty(undefined);
out.emptyQty = formatQty('');
out.zeroQty = formatQty(0);
out.missingInt = formatInt(undefined);
out.zeroInt = formatInt(0);
out.baseDemand = baselineQty({demand_qty: 21.5});
out.baseBaseline = baselineQty({baseline_qty: 3, demand_qty: 21.5});
out.baseNone = baselineQty({});
out.keyRec = rowKey({sku: 'KS1', physical_form: '成品', uom: '个'});
out.keyBase = rowKey({sku: 'KS1', physical_form: '成品', unit: '个'});
out.keyBlank = rowKey({});
out.esc = escapeHtml('<b a="1">x</b>');
console.log(JSON.stringify(out));
""")
    assert out["nullQty"] is None
    assert out["undefinedQty"] is None
    assert out["emptyQty"] is None
    assert out["zeroQty"] == "0"
    assert out["missingInt"] is None
    assert out["zeroInt"] == "0"
    assert out["baseDemand"] == 21.5
    assert out["baseBaseline"] == 3
    assert out["baseNone"] is None
    assert out["keyRec"] == out["keyBase"] == "KS1|成品|个"
    assert out["keyBlank"] == "||"
    assert out["esc"] == "&lt;b a=&quot;1&quot;&gt;x&lt;/b&gt;"


def test_form_boundaries_execute_in_node(tmp_path):
    out = _run_node(tmp_path, """
const out = {};
out.percentBelow = validateInput('percent', '-101', 'EV', 'R', '2026-01-01', '2026-01-02');
out.percentEdge = validateInput('percent', '-100', 'EV', 'R', '2026-01-01', '2026-01-02');
out.totalNegative = validateInput('total', '-1', 'EV', 'R', '2026-01-01', '2026-01-02');
out.totalZero = validateInput('total', '0', 'EV', 'R', '2026-01-01', '2026-01-02');
out.missingEvent = validateInput('delta', '5', '', 'R', '2026-01-01', '2026-01-02');
out.missingReason = validateInput('delta', '5', 'EV', '   ', '2026-01-01', '2026-01-02');
out.missingDate = validateInput('delta', '5', 'EV', 'R', '', '2026-01-02');
out.eventOnlyBlank = validateInput('event_only', '', 'EV', 'R', '2026-01-01', '2026-01-02');
out.eventOnlyValue = validateInput('event_only', '999', 'EV', 'R', '2026-01-01', '2026-01-02');
out.deltaNegative = validateInput('delta', '-5', 'EV', 'R', '2026-01-01', '2026-01-02');
console.log(JSON.stringify(out));
""")
    assert "error" in out["percentBelow"]
    assert out["percentEdge"] == {"value": -100}
    assert "error" in out["totalNegative"]
    assert out["totalZero"] == {"value": 0}
    assert "error" in out["missingEvent"]
    assert "error" in out["missingReason"]
    assert "error" in out["missingDate"]
    assert out["eventOnlyBlank"] == {"value": None}
    assert out["eventOnlyValue"] == {"value": None}
    assert out["deltaNegative"] == {"value": -5}


def test_storage_exception_branches_execute_in_node(tmp_path):
    out = _run_node(tmp_path, """
const out = {};
out.getItemThrows = readStorage({
  getItem: function () { throw new Error('denied'); },
  removeItem: function () {}
}, 'k');
out.setItemThrows = writeStorage({
  setItem: function () { throw new Error('quota'); }
}, 'k', []);
out.probeThrows = probeStorageAvailable({
  setItem: function () { throw new Error('denied'); },
  removeItem: function () {}
}, 'k');
let removed = 0;
out.corrupt = readStorage({
  getItem: function () { return '{not json'; },
  removeItem: function () { removed++; }
}, 'k');
out.corruptRemoved = removed;
out.notArray = readStorage({
  getItem: function () { return '{"a":1}'; },
  removeItem: function () {}
}, 'k');
out.validEmpty = readStorage({
  getItem: function () { return null; },
  removeItem: function () {}
}, 'k');
const good = {
  id: 'p1', row_id: 'r1', kind: 'delta', value: 5,
  start: '2026-01-01', end: '2026-01-02', event_id: 'EV',
  reason: 'R', evidence: '', created_at: '2026-01-01T00:00:00Z',
  status: 'submitted', baseline_version: 'test-baseline'
};
out.validList = readStorage({
  getItem: function () { return JSON.stringify([good]); },
  removeItem: function () {}
}, 'k');
out.badElement = readStorage({
  getItem: function () { return JSON.stringify([{id: 'x'}]); },
  removeItem: function () {}
}, 'k');
out.badVersion = readStorage({
  getItem: function () { return JSON.stringify([Object.assign({}, good, {baseline_version: 5})]); },
  removeItem: function () {}
}, 'k');
console.log(JSON.stringify(out));
""")
    assert out["getItemThrows"]["available"] is False
    assert out["getItemThrows"]["list"] == []
    assert "禁用本地存储" in out["getItemThrows"]["message"]
    assert out["setItemThrows"]["ok"] is False
    assert out["setItemThrows"]["available"] is False
    assert "禁用本地存储" in out["setItemThrows"]["message"]
    assert out["probeThrows"]["available"] is False
    assert out["corrupt"]["corrupted"] is True
    assert out["corrupt"]["list"] == []
    assert out["corruptRemoved"] == 1
    assert out["notArray"]["corrupted"] is True
    assert out["validEmpty"]["list"] == []
    assert [p["id"] for p in out["validList"]["list"]] == ["p1"]
    assert out["badElement"]["corrupted"] is True
    assert out["badVersion"]["corrupted"] is True
