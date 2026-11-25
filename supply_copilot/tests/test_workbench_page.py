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
        "class='workbench-shell' id='workbench-shell'",
        "class='workspace' id='workspace'",
        "class='board'",
        "class='detail-slot' id='detail-slot'",
        "class='detail detail-content' id='detail-content'",
        "container-type:inline-size",
        "container-name:workbench",
        "grid-template-columns:minmax(0,1fr) 420px",
        "grid-template-columns:minmax(0,1fr) 380px",
        "grid-template-columns:minmax(0,1fr) 340px",
        "@container workbench (max-width:1099.9px)",
        "@container workbench (min-width:721px) and (max-width:899.9px)",
        "@container workbench (max-width:720px)",
        "dialog class='sheet' id='detail-sheet'",
        "sheet-handle",
        "--navy:#172e43",
        "--paper:#f5f4ef",
        "--orange:#df6b34",
    ):
        assert marker in html, marker
    # The old viewport-based full-screen overlay + "back to list" model is gone.
    assert "max-width:1279px" not in html
    assert "@media (max-width:1199px)" not in html
    assert "detail-open" not in html
    assert "position:fixed;inset:0" not in html
    assert "返回列表" not in html
    # Detail starts collapsed: no row-level inline expansion markup.
    assert "<tr class=\"detail\">" not in html
    assert "<tr class='detail'>" not in html


def test_detail_three_blocks_in_order_with_anchors(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    header = _function_body(js, "detailHeader")
    for anchor in ("detail-summary", "detail-evidence", "detail-actions"):
        assert 'data-anchor="' + anchor + '"' in header, anchor
    for fn in ("recDetailHtml", "baseDetailHtml"):
        body = _function_body(js, fn)
        i1 = body.index('id="detail-summary"')
        i2 = body.index('id="detail-evidence"')
        i3 = body.index('id="detail-actions"')
        assert i1 < i2 < i3, fn
    # Seven evidence layers + always-visible missing summary + folded recon.
    for title in ("① 身份", "② 期间", "③ 需求", "④ 供给阶段",
                  "⑤ SO 三段", "⑥ 库存", "⑦ 来源哈希", "对单与抽查"):
        assert title in html, title
    assert "缺失与未知" in html
    assert "完整证据链" not in js
    assert "展开证据明细" in js


def test_suggestions_are_readonly_baseline_has_proposal_form(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    assert "补货建议（只读）" in html
    assert "需求基准（可演示提案）" in html
    assert "补货建议只读；唯一关联到需求基准时可在本栏填写演示判断。" in html
    js = html.split("<script>", 1)[1]
    assert js.count("proposalForm(") == 2  # one definition, one call
    assert "proposalForm(" not in _function_body(js, "recDetailHtml")
    assert "baseActionsHtml(" in _function_body(js, "baseDetailHtml")
    assert "proposalBlock(" in _function_body(js, "baseActionsHtml")
    assert "proposalBlock(" in _function_body(js, "recActionsHtml")
    assert js.count('<form id="proposal-form"') == 1
    assert "保存演示提案（本浏览器）" in html
    assert "对关联基准填写演示判断" in js


def test_selection_updates_detail_without_rebuilding_the_list(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    select = _function_body(js, "selectRow")
    assert "renderTable(" not in select
    assert "applySelection(" in select
    assert "renderDetail(" in select
    assert "aria-current" in js
    assert "aria-live" in html
    # setView no longer forces the document back to the top unconditionally.
    assert "window.scrollTo(0, 0)" not in js
    assert "window.scrollTo(0, saved.y)" not in js
    assert "boardTop" in _function_body(js, "saveUiState")
    # A filter that drops the selected row clears the detail, not keeps a form.
    reconcile = _function_body(js, "reconcileSelection")
    assert "outOfFilter" in reconcile
    assert "renderDetail(" in reconcile
    assert "所选行不在当前筛选中" in js


def test_narrow_mode_is_a_bottom_sheet_not_a_route(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    for marker in ("showModal(", "finishSheet", "close", "pointerdown", "dy > 64"):
        assert marker in js, marker
    assert "pushState" not in js
    assert "location.hash" not in js
    assert "ResizeObserver" in js
    assert "matchMedia('(max-width:1279px)')" not in js
    # Drafts live in memory only and the notice says refresh loses them.
    assert "未保存输入刷新后丢失" in js
    assert "localStorage" not in _function_body(js, "saveDraft")
    assert "sessionStorage" in _function_body(js, "saveUiState")


def test_bounded_shell_and_detail_segments(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    assert "class='app-shell'" in html
    assert "height:100dvh" in html
    assert "Math.max(240" not in js
    assert "--ws-h" not in html
    assert 'role="tablist" aria-label="详情内定位"' in js
    assert "function showDetailSection(" in js
    from pathlib import Path
    controller = Path(__file__).parents[1] / "en_page/supply_workbench/supply_workbench.js"
    source = controller.read_text(encoding="utf-8")
    assert "min-height:700px" not in source
    assert "getBoundingClientRect().top" in source
    assert "orientationchange" in source


def test_evidence_same_source_for_detail_and_audit(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    body = _function_body(js, "evidenceSections")
    for layer_title in ("① 身份", "② 期间", "③ 需求", "④ 供给阶段",
                        "⑤ SO 三段", "⑥ 库存", "⑦ 来源哈希"):
        assert layer_title in body, layer_title
    assert "evidenceSections(ctx, 'd')" in _function_body(js, "recDetailHtml")
    assert "evidenceSections(ctx, 'base'" not in body
    assert "evidenceSections(ctx, 'ev')" in _function_body(js, "renderEvidencePanel")


def test_match_kind_only_activates_on_unique_key(tmp_path):
    out = _run_node(tmp_path, """
const rec = [
  {sku: 'K1', physical_form: '成品', uom: '个'},
  {sku: 'K2', physical_form: '成品', uom: '个'},
  {sku: 'K2', physical_form: '成品', uom: '个'},
  {sku: 'K3', physical_form: '皮壳', uom: '套'}
];
const base = [
  {sku: 'K1', physical_form: '成品', unit: '个'},
  {sku: 'K2', physical_form: '成品', unit: '个'},
  {sku: 'K2', physical_form: '成品', unit: '个'},
  {sku: 'K4', physical_form: '成品', unit: '个'}
];
const rc = countKeys(rec), bc = countKeys(base);
console.log(JSON.stringify({
  unique: matchKind(rc, bc, 'K1|成品|个'),
  ambiguous: matchKind(rc, bc, 'K2|成品|个'),
  onlyRec: matchKind(rc, bc, 'K3|皮壳|套'),
  onlyBase: matchKind(rc, bc, 'K4|成品|个'),
  none: matchKind(rc, bc, 'K9|成品|个')
}));
""")
    assert out == {
        "unique": "unique",
        "ambiguous": "ambiguous",
        "onlyRec": "only_rec",
        "onlyBase": "only_base",
        "none": "none",
    }


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
        "① 身份",
        "② 期间",
        "③ 需求",
        "④ 供给阶段",
        "⑤ SO 三段",
        "⑥ 库存",
        "⑦ 来源哈希",
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
    assert "data-locate" in html


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


# ------------------------------------------------------ snapshot_v2 evidence

def _v2_snapshot():
    """Synthetic snapshot_v2: no private data, exercises every v2 empty-state."""
    return {
        "schema_version": "supply-workbench-snapshot-v2",
        "display_version": "v2.1.0-test",
        "version": "test-v2",
        "bundle_id": "b" * 64,
        "branch": "美东USNJ",
        "as_of": "2026-11-24T16:00:00+08:00",
        "computed_at": "2026-11-24T16:00:00+08:00",
        "horizon_days": 90,
        "period_start": "2026-11-24",
        "period_end": "2027-02-22",
        "period_basis": "full_period",
        "model": {
            "policy": "classified",
            "policy_version": "classified-map+pattern@test",
            "rule_version": "autoets_m3_naive@test",
            "run_id": "run-1",
            "as_of": "2026-11-24",
        },
        "config_version": "classified-map+pattern@test",
        "unknown_policy": "null_with_reason",
        "quantile_note": "只独立产出 p50/p90；q90/q95 与 p90 相同或未校准",
        "service_level_note": "p90 是需求分位，不是满足率/不缺货率",
        "limits": ["缺口是窗口总量口径，不是某一天的缺货日"],
        "assumptions": None,
        "executable": False,
        "executable_reasons": ["68 行预测未覆盖，退回 D6 q95", "存在已过下单日"],
        "warnings": ["未接入 supply_netting 的批次去重"],
        "gate": {
            "open": False,
            "message": "总提示：本批结果不可直接下单；采购/运营复核后才可下单",
            "row_can_order_count": 0,
            "row_blocked_count": 4,
            "blocking_reason_counts": {"下单日已过": 2, "需求未知": 1, "重复形态，不单独计": 1},
        },
        "sources": {
            "pack": {"version": "2026-11-13.1", "as_of": "2026-11-13"},
            "stock": {"run_id": "stock-1", "snapshot_at": "2026-11-24 05:00:00",
                      "snapshot_date": "2026-11-24", "sha256": "1" * 64,
                      "used_in_decision": True, "age_hours_at_compute": 10.7,
                      "freshness_at_compute": "fresh", "fresh_at_view": None},
            "forecast": {"run_id": "run-1", "lead_days": 90, "sha256": "2" * 64},
            "so": {"rows": 317, "keys": 96, "decision_scope_rows": 142,
                   "outside_scope_rows": 175, "export_scope": "live_export_current_run",
                   "as_of": "2026-11-24", "sha256": "3" * 64,
                   "history_available": False,
                   "history_reason": "历史 SO 未接入；不能证明历史余额为 0"},
            "po": {"rows": 141, "as_of": "2026-11-24", "sha256": "4" * 64,
                   "stage_detail_available": False,
                   "stage_detail_reason": "当前只有聚合 supply.po"},
        },
        "totals": {
            "rows": 4, "unique_keys": 4, "duplicate_rows": 1,
            "demand_origin": {"forecast": 2, "d6_q95_fallback": 0, "unknown": 1,
                              "forecast_zero": 0, "zero_recent_share": 0},
            "quantile_status": {"p90_alias": 2, "unavailable": 1, "zero": 0,
                                "zero_recent_share": 0},
            "so_decision_scope": {"keys_with_so": 82, "source_rows": 142,
                                  "lines": 142, "qty": 6414.0},
        },
        "rows": [
            {
                "sku": "V2-A", "customer": "美东USNJ", "physical_form": "成品", "uom": "个",
                "action": "补", "new_qty": 10, "forecast": 12, "c_qty": 2, "e_qty": 3,
                "coverage": 30, "reason": "需求 12 > 供给 3",
                "branch": "美东USNJ", "warehouse": "仓-A", "pool": "池-A",
                "period_start": "2026-11-24", "period_end": "2027-02-22",
                "period_basis": "full_period", "horizon_days": 90,
                "demand": {
                    "forecast": 12, "d6_q95": 15, "source": "forecast",
                    "origin": "forecast", "origin_reason": "本地预测覆盖该键",
                    "decide_demand_source": "forecast_refresh",
                    "evidence": "forecast window p90", "model": "autoets", "pattern": "smooth",
                    "p50": 9, "p90": 12, "q90": 12, "q95": 12,
                    "q95_independent": False, "q95_service_commitment": False,
                    "quantile_status": "p90_alias",
                    "quantile_reason": "q90/q95 与 p90 相同",
                },
                "supply": {
                    "opening": 2, "intransit": 1, "po": 0, "cg": 0, "so": 20,
                    "so_on_time": 20, "so_conditional": 0, "expected": 3, "proven": 3,
                },
                "stock": {"run_id": "stock-1", "snapshot_at": "2026-11-24 05:00:00",
                          "snapshot_date": "2026-11-24", "sha256": "1" * 64,
                          "used_in_decision": True, "age_hours_at_compute": 10.7,
                          "freshness_at_compute": "fresh", "fresh_at_view": None},
                "row_can_order": False,
                "row_can_order_reason": "全局 gate 未放行（executable=false）",
                "blocking_reasons": ["下单日已过", "预测未覆盖，退回 D6 q95"],
                "forecast_run": {"run_id": "run-1", "as_of": "2026-11-24",
                                 "lead_days": 90, "windows_sha256": "2" * 64},
                "provenance": {"so_sha256": "3" * 64, "po_sha256": "4" * 64,
                               "source_row": None, "source_hash": None,
                               "source_row_reason": "decide 不含逐行源指针"},
                "so_open_qty": 20, "so_current_export_open_qty": 20,
                "so_recent_open_qty": None,
                "so_recent_open_qty_reason": "语义已拆分：见 so_current_export_open_qty",
                "so_history_open_qty": None,
                "so_history_open_qty_reason": "历史 SO 未接入；不能证明历史余额为 0",
                "so_history_status": "not_connected",
                "so_source_as_of": "2026-11-24T16:00:00+08:00",
                "so_lines_status": "ok",
                "so_lines": [{
                    "so": "SO-1", "so_line": None, "so_line_reason": "无行号",
                    "status": "open_balance", "status_reason": "只给开放余额",
                    "open_qty": 20, "delivered_qty": None,
                    "delivered_qty_reason": "未给已交付", "delivery_date": "2026-08-30",
                    "export_scope": "live_export_current_run", "created_at": None,
                    "created_at_reason": "backlog 导出无创建时间",
                    "delivery_bucket": "past", "delivery_relation": "past",
                    "date_bucket": None,
                    "date_bucket_reason": "已拆分，不表示创建时间",
                }],
                "coverage_basis": None,
                "coverage_basis_reason": "导出未定义 coverage 语义",
                "confidence_level": "normal", "service_level": "p90",
                "assumptions": ["需求=90 天 p90"],
            },
            {
                "sku": "V2-B", "customer": "美东USNJ", "physical_form": "皮壳", "uom": "套",
                "action": "观察", "forecast": None, "c_qty": 0, "e_qty": 0,
                "branch": "美东USNJ", "warehouse": None, "pool": "池-B",
                "period_start": "2026-11-24", "period_end": "2027-02-22",
                "period_basis": "full_period", "horizon_days": 90,
                "demand": {"forecast": None, "p50": None, "p90": None, "q90": None, "q95": None,
                           "origin": "unknown", "origin_reason": "源快照未给需求",
                           "q95_independent": False, "q95_service_commitment": False,
                           "quantile_status": "unavailable",
                           "quantile_reason": "本地预测未覆盖该键；需求退回 D6 q95"},
                "supply": {"opening": 0, "intransit": 0, "po": None, "cg": 0, "so": 0,
                           "so_on_time": 0, "so_conditional": 0, "expected": 0, "proven": 0},
                "stock": {"run_id": "stock-1", "snapshot_at": "2026-11-24 05:00:00",
                          "snapshot_date": "2026-11-24", "sha256": "1" * 64,
                          "used_in_decision": True, "age_hours_at_compute": 10.7,
                          "freshness_at_compute": "fresh", "fresh_at_view": None},
                "row_can_order": False,
                "row_can_order_reason": "全局 gate 未放行（executable=false）",
                "blocking_reasons": ["需求未知", "待核（需求未知）"],
                "forecast_run": {"run_id": "run-1", "as_of": "2026-11-24",
                                 "lead_days": 90, "windows_sha256": "2" * 64},
                "provenance": {"so_sha256": "3" * 64, "po_sha256": "4" * 64,
                               "source_row": None, "source_hash": None},
                "so_open_qty": 0, "so_current_export_open_qty": 0,
                "so_recent_open_qty": None, "so_history_open_qty": None,
                "so_history_status": "not_connected",
                "so_lines_status": "empty_in_export", "so_lines": [],
                "coverage_basis": None,
                "coverage_basis_reason": "导出未定义 coverage 语义",
                "confidence_level": "low", "service_level": "p90",
            },
            {
                "sku": "V2-C", "customer": "美东USNJ", "physical_form": "成品", "uom": "个",
                "action": "补", "forecast": 5, "c_qty": 0, "e_qty": 0,
                "branch": "美东USNJ", "warehouse": "仓-C", "pool": "池-C",
                "period_start": "2026-11-24", "period_end": "2027-02-22",
                "period_basis": "full_period", "horizon_days": 90,
                "demand": {"forecast": 5, "p50": 4, "p90": 5, "q90": 5, "q95": 5,
                           "origin": "forecast_zero", "origin_reason": "模型输出为 0",
                           "q95_independent": False, "q95_service_commitment": False,
                           "quantile_status": "zero"},
                "supply": {"opening": 0, "intransit": 0, "po": 0, "cg": 0, "so": 0,
                           "so_on_time": 0, "so_conditional": 0, "expected": 0, "proven": 0},
                "stock": {"run_id": "stock-1", "snapshot_at": "2026-11-24 05:00:00",
                          "snapshot_date": "2026-11-24", "sha256": "1" * 64,
                          "used_in_decision": True, "age_hours_at_compute": 10.7,
                          "freshness_at_compute": "fresh", "fresh_at_view": None},
                "row_can_order": False,
                "row_can_order_reason": "全局 gate 未放行（executable=false）",
                "blocking_reasons": ["下单日已过"],
                "forecast_run": {"run_id": "run-1", "as_of": "2026-11-24",
                                 "lead_days": 90, "windows_sha256": "2" * 64},
                "provenance": {"so_sha256": "3" * 64, "po_sha256": "4" * 64,
                               "source_row": None, "source_hash": None},
                "so_open_qty": 3, "so_current_export_open_qty": 3,
                "so_recent_open_qty": None, "so_history_open_qty": None,
                "so_history_status": "not_connected",
                "so_lines_status": "line_sum_mismatch",
                "so_lines": [{"so": "SO-2", "so_line": 1, "open_qty": 1,
                              "delivery_date": "2026-12-01", "delivery_relation": "in_period",
                              "delivery_bucket": "in_period", "date_bucket": None,
                              "status": "open_balance"}],
                "coverage_basis": None, "confidence_level": "normal", "service_level": "p90",
            },
            {
                # Duplicate form: the SO amount lives on the main form only. The
                # page must not add this row's supply.so into SO evidence again.
                "sku": "V2-D", "customer": "美东USNJ", "physical_form": "皮壳", "uom": "套",
                "action": "观察", "forecast": 1, "c_qty": 0, "e_qty": 20,
                "branch": "美东USNJ", "warehouse": "仓-D", "pool": "池-D",
                "period_start": "2026-11-24", "period_end": "2027-02-22",
                "period_basis": "full_period", "horizon_days": 90,
                "demand": {"forecast": 1, "p50": 1, "p90": 1, "q90": 1, "q95": 1,
                           "origin": "zero_recent_share",
                           "origin_reason": "近期无本分公司份额，按 0 分配；需人工确认",
                           "q95_independent": False, "q95_service_commitment": False,
                           "quantile_status": "zero_recent_share"},
                "supply": {"opening": 0, "intransit": 0, "po": 0, "cg": 0, "so": 20,
                           "so_on_time": 20, "so_conditional": 0, "expected": 20, "proven": 20},
                "stock": {"run_id": "stock-1", "snapshot_at": "2026-11-24 05:00:00",
                          "snapshot_date": "2026-11-24", "sha256": "1" * 64,
                          "used_in_decision": True, "age_hours_at_compute": 10.7,
                          "freshness_at_compute": "fresh", "fresh_at_view": None},
                "row_can_order": False,
                "row_can_order_reason": "全局 gate 未放行（executable=false）",
                "blocking_reasons": ["重复形态，不单独计"],
                "duplicate_form": True,
                "so_open_qty": 20, "so_current_export_open_qty": 20,
                "so_recent_open_qty": None, "so_history_open_qty": None,
                "so_history_status": "not_connected",
                "so_lines_status": "duplicate_form", "so_lines": [],
                "coverage_basis": None, "confidence_level": "normal", "service_level": "p90",
            },
        ],
    }


@pytest.fixture()
def inputs_v2(tmp_path):
    snap = _v2_snapshot()
    baseline = {
        "as_of": "2026-11-12", "version": "test-baseline", "demo": True,
        "rows": _baseline_rows(),
    }
    snap_path = tmp_path / "snapshot_v2.json"
    base_path = tmp_path / "baseline.json"
    snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    base_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    return snap_path, base_path, snap


def test_v2_meta_embedded_and_header_strip(inputs_v2):
    snap_path, base_path, snap = inputs_v2
    html = build(snap_path, base_path)
    payload = json.loads(_embedded_payload(html))
    meta = payload["meta"]
    assert payload["schema_version"] == "supply-workbench-snapshot-v2"
    assert meta["period_start"] == "2026-11-24"
    assert meta["period_end"] == "2027-02-22"
    assert meta["horizon_days"] == 90
    assert meta["computed_at"] == snap["computed_at"]
    assert meta["bundle_id"] == snap["bundle_id"]
    assert meta["config_version"] == "classified-map+pattern@test"
    assert meta["model"]["run_id"] == "run-1"
    # Page header strip (server-rendered, compact).
    assert "class='metastrip'" in html
    # The visible line is exactly version · period/window · as_of; everything
    # else collapses into the 快照信息 details.
    assert "v2.1.0-test</b> · 2026-11-24 ~ 2027-02-22/90天 · as_of 2026-11-24T16:00:00+08:00" in html
    assert "class='metafold'" in html and "快照信息" in html
    assert "class='navrow'" in html
    for text in ("期间", "2026-11-24", "2027-02-22", "窗口", "90 天",
                 "bundle", "配置", "classified-map+pattern@test", "分支", "美东USNJ",
                 "computed", "模型", "run-1"):
        assert text in html, text
    # SO totals are surfaced in the evidence header.
    assert "2 个键有明细" in html and "2 条明细" in html


def test_v2_rows_are_embedded_verbatim_with_nulls(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    payload = json.loads(_embedded_payload(build(snap_path, base_path)))
    rows = {r["sku"]: r for r in payload["rows"]}
    assert rows["V2-A"]["demand"]["quantile_status"] == "p90_alias"
    assert rows["V2-A"]["supply"]["proven"] == 3
    assert rows["V2-B"]["demand"]["forecast"] is None       # unknown, not 0
    assert rows["V2-B"]["supply"]["po"] is None             # unconnected, not 0
    assert rows["V2-B"]["warehouse"] is None                # explicit null
    assert rows["V2-B"]["provenance"]["source_row"] is None
    assert rows["V2-A"]["forecast_run"]["windows_sha256"] == "2" * 64


def test_v2_quantile_status_wording(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    assert "p90_alias" in js
    assert "q90/q95 与 p90 相同" in js
    assert "不应当作更高服务水平" in js
    assert "unavailable" in js
    assert "本地预测未覆盖该键" in js
    assert "p90 是需求分位，不是满足率" in html


def test_v2_so_status_semantics_and_expandable_lines(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    assert "empty_in_export" in js
    assert "本次导出真实无开放 SO（不是未知）" in js
    assert "line_sum_mismatch" in js
    assert "SO 明细行合计与管线合计不一致" in js
    # v2 SO table columns: 单据号 / 行 / 开放量 / 交付日 / 日期关系.
    tbl = _function_body(js, "soTable")
    for head in ("SO 单据号", "开放量", "交付日", "日期关系"):
        assert head in tbl, head
    assert "delivery_relation" in tbl and "relationLabel" in tbl


def test_v2_unconnected_stages_stay_unavailable(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path)
    js = html.split("<script>", 1)[1]
    supply = _function_body(js, "supplyFull")
    assert "PO 聚合 supply.po" in supply
    assert "生产单 / DN 阶段" in supply
    assert "未接入（null，不补 0）" in supply
    # No silent zero-filling: the display helper returns null for blank.
    assert "function qty(v) { var t = formatQty(v); return t === null ? unknown() : t; }" in js


def test_v2_sources_sha_and_notes_in_method_view(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path)
    method = html[html.index("id='view-method'"):]
    for text in ("快照 v2 元数据（证据完整版）", "quantile_note", "service_level_note",
                 "只独立产出 p50/p90", "p90 是需求分位", "已知限制 limits",
                 "缺口是窗口总量口径", "来源与版本 sources", "stock-1", "run-1",
                 "1111111111111111", "2222222222222222", "未知与空集语义",
                 "empty_in_export", "顶层 assumptions 未提供（null）"):
        assert text in method, text


def test_v2_detail_functions_prefer_new_fields(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    js = build(snap_path, base_path).split("<script>", 1)[1]
    assert "isV2(" in js
    for fn in ("identityFull", "periodFull", "demandFull", "supplyFull", "soFull",
               "stockFull", "sourceFull"):
        body = _function_body(js, fn)
        assert ("rowDemand" in body or "rowSupply" in body or "rowStock" in body or
                "rowProvenance" in body or "so_lines_status" in body or "isV2" in body), fn
    identity = _function_body(js, "identityFull")
    assert "warehouseText" in identity and "未提供" in js
    stock = _function_body(js, "stockFull")
    assert "used_in_decision" in stock and "freshness_at_compute" in stock
    assert "fresh_at_view" in stock and "按浏览时间" in stock
    assert "已废弃" in stock   # current_for_decision is only mentioned as deprecated
    source = _function_body(js, "sourceFull")
    assert "coverage_basis" in source and "source_row_reason" in js


def test_v2_missing_notes_do_not_flag_present_period(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    js = build(snap_path, base_path).split("<script>", 1)[1]
    notes = _function_body(js, "unknownNotes")
    # v2 branch guards the period-missing note behind an explicit absence check.
    assert "r.period_start || r.period_end || r.period_basis" in notes
    assert "demand.forecast 缺失" in notes
    assert "r.so_lines_status === 'empty_in_export'" not in notes   # facts live in knownFacts
    facts = _function_body(js, "knownFacts")
    assert "empty_in_export" in facts and "p90_alias" in facts


def test_v2_is_backward_compatible_with_flat_snapshot(inputs):
    snap_path, base_path, _ = inputs
    html = build(snap_path, base_path)
    payload = json.loads(_embedded_payload(html))
    # No v2 metadata: page still builds, meta is null-filled, legacy keys render.
    assert payload["meta"]["schema_version"] is None
    assert "class='metastrip'" not in html
    js = html.split("<script>", 1)[1]
    assert "预测中位 forecast" in js and "E 按时供给 e_qty" in js
    assert "旧版扁平快照（无 snapshot_v2 元数据）" in html


def test_v2_so_summary_counts_match_rows(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    payload = json.loads(_embedded_payload(build(snap_path, base_path)))
    assert payload["meta"]["so_summary"] == {
        "keys_with_lines": 2, "lines_total": 2,
        "empty_in_export": 1, "line_sum_mismatch": 1, "duplicate_form": 1,
    }


# ------------------------------------------------------------ v2.1 release semantics


def _release_stub():
    """Manifest-shaped release dict. File/hash verification is tested separately
    in test_release_manifest.py."""
    return {
        "manifest": {
            "release_id": "20261125T095418+0800",
            "display_version": "v2.1.0-20261125",
            "parent_bundle": "b" * 64,
            "counts": {
                "so_full_export": {"rows": 317, "keys": 96,
                                   "decision_scope_rows": 142, "outside_scope_rows": 175},
            },
            "source_times": {"stock_age_hours_at_compute": 10.7},
            "remaining_gaps": [
                {"item": "PO 阶段明细/ETA/来源", "status": "pending",
                 "reason": "当前只有聚合 supply.po", "owner": "A"},
                {"item": "历史 SO 余额", "status": "pending",
                 "reason": "历史包未接入", "owner": "A/供应数据"},
            ],
        }
    }


def test_v21_gate_banner_headline_and_freshness_placeholder(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path, release=_release_stub())
    assert "class='gatebanner'" in html
    assert "整体 gate 关闭 · 本批不可直接下单" in html
    assert "可下单行 0 / 阻断 4" in html
    assert "class='gate-reasons-inline'" in html and "class='gate-more'" in html
    assert "总提示：本批结果不可直接下单" in html
    assert "68 行预测未覆盖" in html
    assert "即使各行数据齐全，本批也一律不放行" in html
    # View-time freshness is computed by the page, never hard-coded.
    assert "id='stock-fresh-view'" in html
    assert "按浏览时间" in html


def test_v21_gate_repeated_in_list_detail_and_analysis(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path, release=_release_stub())
    js = html.split("<script>", 1)[1]
    for fn in ("gateClosed", "rowCanOrder", "gateBadge", "gateRowHtml", "gatePresent"):
        assert "function %s(" % fn in js, fn
    row = _function_body(js, "gateRowHtml")
    assert "row_can_order=false" in row and "不可下单" in row
    table_row = _function_body(js, "recRowHtml")
    assert "gateBadge(r)" in table_row
    assert "gateRowHtml(r)" in _function_body(js, "recSummaryHtml")
    assert "gateRowHtml(ctx.row)" in _function_body(js, "evidenceSections")
    analysis = html.split("id='view-analysis'", 1)[1]
    assert "gatebar" in analysis and "整体 gate 关闭" in analysis


def test_v21_export_carries_gate_origin_and_identity(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path, release=_release_stub())
    js = html.split("<script>", 1)[1]
    export = _function_body(js, "exportText")
    for token in ("display_version=", "release_id=", "parent_bundle=", "period=",
                  "gate.open=", "executable_reasons=", "demand_origin",
                  "quantile_status", "q95_independent", "row_can_order",
                  "blocking_reasons", "row_can_order_reason"):
        assert token in export, token
    # Export moved to the top action row: one click downloads the same CSV.
    assert "id='export-csv'" in html and "id='export-note'" in html
    assert "id='export-fold'" not in html and "id='export-text'" not in html
    download = _function_body(js, "downloadExport")
    assert "Blob" in download and "download" in download


def test_v21_five_demand_origins_and_quantile_flags(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path, release=_release_stub())
    method = html[html.index("id='view-method'"):]
    for code in ("forecast", "forecast_zero", "zero_recent_share",
                 "d6_q95_fallback", "unknown"):
        assert code in method, code
    assert "本地预测未覆盖，退回 D6 q95" in method
    assert "近期无本分公司份额" in method
    assert "需求未知（null，不是 0）" in method
    assert "q95_independent=false" in html and "q95_service_commitment=false" in html
    js = html.split("<script>", 1)[1]
    demand = _function_body(js, "demandFull")
    assert "demand.origin" in demand and "quantileFlagsHtml" in demand
    assert "ORIGIN_LABELS" in js and "originHtml" in js


def test_v21_four_quantile_statuses(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    js = build(snap_path, base_path).split("<script>", 1)[1]
    q = _function_body(js, "quantileStatusHtml")
    for status in ("p90_alias", "zero", "zero_recent_share", "unavailable"):
        assert status in q, status
    assert "不应当作更高服务水平" in q


def test_v21_stock_uses_decision_and_view_time_not_legacy_flag(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    js = build(snap_path, base_path).split("<script>", 1)[1]
    assert "current_for_decision ===" not in js   # legacy flag is never read
    fresh = _function_body(js, "freshnessAtView")
    assert "Date.now()" in fresh and "24" in fresh
    stock = _function_body(js, "stockFull")
    for token in ("used_in_decision", "age_hours_at_compute", "freshness_at_compute",
                  "fresh_at_view", "按浏览时间", "已废弃"):
        assert token in stock, token


def test_v21_so_scope_duplicate_and_history(inputs_v2):
    snap_path, base_path, _ = inputs_v2
    html = build(snap_path, base_path, release=_release_stub())
    js = html.split("<script>", 1)[1]
    bucket = _function_body(js, "soBucket")
    assert "delivery_bucket" in bucket
    sofull = _function_body(js, "soFull")
    assert "so_current_export_open_qty" in sofull
    assert "决策证据合计" in sofull
    assert "全量导出（不进决策证据）" in sofull
    assert "不重复挂载" in sofull
    assert "不能证明余额为 0" in sofull
    assert "不能再叫「近期 = 创建时间」" in sofull
    # Evidence totals come from totals.so_decision_scope, not from summing rows.
    assert "6414" in html


def test_v21_evidence_totals_not_summed_from_duplicate_rows(inputs_v2):
    """V2-A contributes 20 and V2-D (duplicate_form) also carries 20; the
    evidence total must stay 6,414 from totals, never 40 or 6,434."""
    snap_path, base_path, snap = inputs_v2
    payload = json.loads(_embedded_payload(build(snap_path, base_path,
                                                release=_release_stub())))
    assert payload["totals"]["so_decision_scope"]["qty"] == 6414.0
    rows = {r["sku"]: r for r in payload["rows"]}
    assert rows["V2-D"]["duplicate_form"] is True
    assert rows["V2-D"]["so_lines"] == []


def test_v21_baseline_v2_joins_on_complete_key(tmp_path):
    def row(sku, form, uom, wh, pool, start, end, qty, origin):
        return {"id": "%s|%s|%s" % (sku, wh, form), "branch": "美东USNJ", "sku": sku,
                "physical_form": form, "uom": uom, "warehouse": wh, "pool": pool,
                "period_start": start, "period_end": end, "horizon_days": 90,
                "demand_qty": qty, "demand_origin": origin, "parent_bundle": "p" * 64}

    snap = {
        "schema_version": "supply-workbench-snapshot-v2",
        "display_version": "v2.1.0-test", "version": "t", "bundle_id": "b" * 64,
        "branch": "美东USNJ", "as_of": "2026-11-24T16:00:00+08:00",
        "horizon_days": 90, "period_start": "2026-11-24", "period_end": "2027-02-22",
        "gate": {"open": False, "message": "不可下单"},
        "totals": {"rows": 2},
        "rows": [
            {"sku": "KSX", "physical_form": "成品", "uom": "个", "warehouse": "仓-1",
             "pool": "池-1", "period_start": "2026-11-24", "period_end": "2027-02-22",
             "demand": {"forecast": 1}, "row_can_order": False},
            {"sku": "KSX", "physical_form": "成品", "uom": "个", "warehouse": "仓-2",
             "pool": "池-2", "period_start": "2026-11-24", "period_end": "2027-02-22",
             "demand": {"forecast": 2}, "row_can_order": False},
        ],
    }
    baseline = {
        "schema_version": "supply-workbench-baseline-v2", "version": "b",
        "as_of": "2026-11-24T16:00:00+08:00", "branch": "美东USNJ",
        "period_start": "2026-11-24", "period_end": "2027-02-22",
        "rows": [
            row("KSX", "成品", "个", "仓-1", "池-1", "2026-11-24", "2027-02-22", 11, "forecast"),
            row("KSX", "成品", "个", "仓-2", "池-2", "2026-11-24", "2027-02-22", 22, "unknown"),
        ],
    }
    snap_path = tmp_path / "snapshot_v2.json"
    base_path = tmp_path / "baseline_v2.json"
    snap_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    base_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    html = build(snap_path, base_path)
    payload = json.loads(_embedded_payload(html))
    recon = payload["recon"]
    assert recon["full_key"] is True
    assert recon["unique"] == 2 and recon["ambiguous"] == []
    assert recon["only_rec"] == 0 and recon["only_base"] == 0
    assert payload["baseline"]["schema_version"] == "supply-workbench-baseline-v2"
    js = html.split("<script>", 1)[1]
    assert "BASELINE_V2" in js and "fullKeyOf" in js
    twin = _function_body(js, "twinRow")
    assert "fullKeyOf" in twin
    assert "set === 'rec' ? (BASE_FULL[fk] || null)" in twin
    identity = _function_body(js, "identityFull")
    assert "BASELINE_V2" in identity and "parent_bundle" in identity
