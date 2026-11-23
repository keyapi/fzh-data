# -*- coding: utf-8 -*-
"""USNJ 补货协同工作台（单文件静态页生成器，演示用）。

版式与字段镜像自 ``supply_copilot/usnj_page.py``（提交 666cd700 的六页签
决策/A/B/C/D/E/口径），在其基础上新增第 8 个页签「运营协同」。

运营协同页签的提案只写入浏览器 ``localStorage``（键
``supply-workbench:proposals:v1``），页面不发起任何网络请求、不写 EN、
不提供下单/改量/真实审批入口。

输入：
  --snapshot   recommend/batch 产出的快照 JSON（含 rows 数组与 as_of/版本）
  --baseline   需求基准 JSON（含 rows 数组），只取 branch == "USNJ" 的行
  --b-dir      可选：B_*.csv 所在目录（B_USNJ归属清单.csv / B_待确认.csv）
  --out        输出 HTML 路径

输出：单文件只读 HTML。生产部署见 ``supply_copilot/en_page/README.md``。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from .usnj_page import action, b_table, badge, esc, extra, i, read_b, so_lines

STORAGE_KEY = "supply-workbench:proposals:v1"
BRANCH = "USNJ"

TABS = [
    ("home", "决策"),
    ("a", "A SKU宇宙"),
    ("b", "B 归属"),
    ("c", "C 库存"),
    ("d", "D 预估"),
    ("e", "E 供给"),
    ("method", "口径"),
    ("collab", "运营协同"),
]

DEMO_BANNER = (
    "演示模式：数据为内嵌快照，页面不发起网络请求。运营协同页签的提案只保存在"
    "本浏览器（localStorage 键 <code>supply-workbench:proposals:v1</code>）："
    "刷新保留；清理浏览器数据或换浏览器看不到本浏览器的提案；"
    "不上传、不审批、不写 EN。本页面不区分身份；同一浏览器/同账号共享本地演示数据，"
    "仅用于演示。"
)

CSP_STATIC = (
    "default-src 'none'; style-src 'unsafe-inline'; "
    "connect-src 'none'; form-action 'none'; base-uri 'none'; img-src data:"
)


def csp_hash(text: str) -> str:
    """CSP sha256 source for an inline script's exact text content."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


# Pure, DOM-free JS extracted as one block so tests can execute it under Node.
# The page embeds it verbatim through the /*__COLLAB_LIB__*/ placeholder.
COLLAB_LIB = """
  var KINDS = ['delta', 'total', 'percent', 'event_only'];
  var STATUSES = ['submitted', 'approved', 'rejected'];
  var STATUS_LABELS = {submitted: '待模拟审核', approved: '模拟通过', rejected: '模拟驳回'};
  var MIN_PERCENT = -100;
  var MIN_TOTAL = 0;
  var STORAGE_DISABLED_MSG = '浏览器已禁用本地存储，提案表单已停用；页面其余内容仍可浏览。';
  var STORAGE_CORRUPT_MSG = '本地提案数据损坏，已丢弃；不影响查看与重新提交。';

  function isPlainObject(v) { return !!v && typeof v === 'object' && !Array.isArray(v); }

  function isValidProposal(p) {
    if (!isPlainObject(p)) return false;
    if (typeof p.id !== 'string' || !p.id) return false;
    if (typeof p.row_id !== 'string' || !p.row_id) return false;
    if (KINDS.indexOf(p.kind) < 0) return false;
    if (!(p.value === null || (typeof p.value === 'number' && isFinite(p.value)))) return false;
    if (typeof p.start !== 'string' || typeof p.end !== 'string') return false;
    if (typeof p.event_id !== 'string' || !p.event_id) return false;
    if (typeof p.reason !== 'string' || !p.reason) return false;
    if (typeof p.evidence !== 'string') return false;
    if (typeof p.created_at !== 'string' || !p.created_at) return false;
    if (STATUSES.indexOf(p.status) < 0) return false;
    return true;
  }

  function parseProposals(raw) {
    if (raw === null || raw === undefined || raw === '') return {corrupted: false, list: []};
    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      return {corrupted: true, list: []};
    }
    if (!Array.isArray(parsed)) return {corrupted: true, list: []};
    for (var i = 0; i < parsed.length; i++) {
      if (!isValidProposal(parsed[i])) return {corrupted: true, list: []};
    }
    return {corrupted: false, list: parsed};
  }

  function readStorage(storage, key) {
    var raw;
    try {
      raw = storage.getItem(key);
    } catch (e) {
      return {available: false, list: [], corrupted: false, message: STORAGE_DISABLED_MSG};
    }
    var parsed = parseProposals(raw);
    if (parsed.corrupted) {
      try { storage.removeItem(key); } catch (e) { /* ignore */ }
      return {available: true, list: [], corrupted: true, message: STORAGE_CORRUPT_MSG};
    }
    return {available: true, list: parsed.list, corrupted: false, message: ''};
  }

  function writeStorage(storage, key, list) {
    try {
      storage.setItem(key, JSON.stringify(list));
      return {ok: true, available: true, message: ''};
    } catch (e) {
      return {ok: false, available: false, message: STORAGE_DISABLED_MSG};
    }
  }

  function probeStorageAvailable(storage, key) {
    try {
      storage.setItem(key + ':probe', '1');
      storage.removeItem(key + ':probe');
      return {available: true, message: ''};
    } catch (e) {
      return {available: false, message: STORAGE_DISABLED_MSG};
    }
  }

  function validateInput(kind, rawValue, eventId, reason, start, end) {
    eventId = String(eventId === null || eventId === undefined ? '' : eventId).trim();
    reason = String(reason === null || reason === undefined ? '' : reason).trim();
    if (!eventId) return {error: '请填写业务事件 ID。'};
    if (!reason) return {error: '请填写调整原因。'};
    if (!start || !end) return {error: '请填写事件开始与结束日期。'};
    if (end < start) return {error: '事件结束日期不能早于开始日期。'};
    if (kind === 'event_only') return {value: null};
    if (KINDS.indexOf(kind) < 0) return {error: '未知的调整方式。'};
    if (rawValue === '' || rawValue === null || rawValue === undefined) {
      return {error: '请填写数值。'};
    }
    var value = Number(rawValue);
    if (!isFinite(value)) return {error: '数值必须是数字。'};
    if (kind === 'percent' && value < MIN_PERCENT) {
      return {error: '比例调整不能低于 ' + MIN_PERCENT + '%。'};
    }
    if (kind === 'total' && value < MIN_TOTAL) {
      return {error: '调整为总量不能小于 ' + MIN_TOTAL + '。'};
    }
    return {value: value};
  }
"""


def embed_json(obj) -> str:
    """JSON for a <script type="application/json"> block.

    ``</`` is rewritten to ``<\\/`` and every remaining angle bracket is
    unicode-escaped so data can never terminate the script element early.
    """
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("</", "<\\/")
    text = text.replace("<", "\\u003c").replace(">", "\\u003e")
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return text


def filter_usnj(baseline: dict) -> list:
    """Keep only demand-baseline rows owned by the USNJ branch."""
    rows = baseline.get("rows") or []
    return [r for r in rows if str(r.get("branch") or "").strip() == BRANCH]


def load_baseline(path: Path):
    """Return (document, USNJ rows) from a demand-baseline JSON file."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc, filter_usnj(doc)


def _decision_rows(rows) -> str:
    out = []
    for r in rows:
        out.append(f"""
<tr>
<td><strong>{esc(r.get('sku'))}</strong><br><small>{esc(r.get('customer') or '归属待确认')} · {esc(r.get('physical_form'))} · {esc(r.get('uom'))}</small></td>
<td>{action(r)}</td><td>{i(r.get('coverage'))} 天</td><td>{esc(r.get('reason'))}</td><td>{badge(r)}</td>
</tr>
<tr class="detail"><td colspan="5">
<div class="grid">
<div><b>C 当前可发</b><br>{i(r.get('c_qty'))}</div>
<div><b>E 按时供给</b><br>{i(r.get('e_qty'))}</div>
<div><b>EN 已发运/待发</b><br>{extra(r, 'EN已发运量')} / {extra(r, 'EN待发量')}</div>
<div><b>PO / SO</b><br>{extra(r, 'PO追加(去重)')} / {extra(r, 'SO已下')}</div>
<div><b>CG 抵扣</b><br>{extra(r, 'CG可调拨抵扣')}</div>
<div><b>预测 q50</b><br>{i(r.get('forecast'))}</div>
<div><b>q50/q90/q95</b><br>{i(r.get('q50'))}/{i(r.get('q90'))}/{i(r.get('q95'))}</div>
<div><b>模型</b><br>{esc(r.get('model') or '—')}</div>
</div>
<div class="chain"><span>SO 管线 <b>{i(r.get('so_open_qty'))}</b></span>
<span>近期 <b>{i(r.get('so_recent_open_qty'))}</b></span><span>历史 <b>{i(r.get('so_history_open_qty'))}</b></span>
<span>生产 <b>未接入</b></span><span>DN <b>未接入</b></span><span>通途 PO <b>未接入</b></span></div>
<details><summary>SO 明细（W1 截至 {esc(r.get('so_source_as_of') or '—')}，不加入建议量）</summary>{so_lines(r)}</details>
</td></tr>""")
    return "".join(out)


def _sku_universe(rows) -> list:
    return sorted({
        (r.get("sku"), r.get("physical_form"), r.get("uom"), r.get("customer"))
        for r in rows
    })


def _forecast_rows(rows) -> str:
    return "".join(
        f"<tr><td>{esc(r.get('sku'))}</td><td>{i(r.get('forecast'))}</td><td>{i(r.get('q50'))}</td>"
        f"<td>{i(r.get('q90'))}</td><td>{i(r.get('q95'))}</td><td>{esc(r.get('model') or '—')}</td></tr>"
        for r in rows
    )


def _supply_rows(rows) -> str:
    return "".join(
        f"<tr><td>{esc(r.get('sku'))}</td><td>{i(r.get('c_qty'))}</td><td>{extra(r, 'EN已发运量')}</td>"
        f"<td>{extra(r, 'EN待发量')}</td><td>{extra(r, 'PO追加(去重)')}</td><td>{extra(r, 'SO已下')}</td>"
        f"<td>{extra(r, 'CG可调拨抵扣')}</td><td>{i(r.get('so_recent_open_qty'))}</td>"
        f"<td>{i(r.get('so_history_open_qty'))}</td></tr>"
        for r in rows
    )


_COLLAB_JS = """
(function () {
  'use strict';

  /*__COLLAB_LIB__*/

  var STORAGE_KEY = 'supply-workbench:proposals:v1';
  var KIND_LABELS = {
    delta: '增减数量', total: '调整为总量',
    percent: '按比例调整', event_only: '仅记录事件'
  };
  var storageState = {available: true, message: ''};

  var dataEl = document.getElementById('supply-workbench-baseline');
  var BASELINE = {rows: [], version: null, as_of: null};
  if (dataEl) {
    try { BASELINE = JSON.parse(dataEl.textContent); } catch (e) { BASELINE = {rows: []}; }
  }
  var ROWS = Array.isArray(BASELINE.rows) ? BASELINE.rows : [];
  var ROW_INDEX = {};
  ROWS.forEach(function (r) { ROW_INDEX[String(r.id)] = r; });
  var selectedId = null;
  var view = 'operator';

  function byId(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function num(v) {
    if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '未知';
    return Number(v).toLocaleString('zh-CN', {maximumFractionDigits: 2});
  }
  function day(v) { return String(v === null || v === undefined ? '' : v).slice(0, 10); }
  function period(r) {
    var start = day(r.week);
    var end = day(r.period_end);
    return (start || '—') + ' – ' + (end || '—');
  }
  function newId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'p-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }
  function message(text, isError) {
    var el = byId('collab-message');
    if (!el) return;
    el.textContent = text || '';
    el.className = isError ? 'form-message error' : 'form-message';
  }

  function showStorageNotice(text) {
    var el = byId('collab-storage-notice');
    if (!el) return;
    if (!text) { el.hidden = true; el.textContent = ''; return; }
    el.hidden = false;
    el.textContent = text;
  }
  function probeStorage() {
    var res = probeStorageAvailable(window.localStorage, STORAGE_KEY);
    storageState.available = res.available;
    storageState.message = res.message;
  }
  function readProposals() {
    var res = readStorage(window.localStorage, STORAGE_KEY);
    if (!res.available) {
      storageState.available = false;
      storageState.message = res.message;
    }
    if (res.message) showStorageNotice(res.message);
    return res.list;
  }
  function writeProposals(list) {
    if (!storageState.available) return false;
    var res = writeStorage(window.localStorage, STORAGE_KEY, list);
    if (!res.ok) {
      storageState.available = false;
      storageState.message = res.message;
      showStorageNotice(res.message);
      if (selectedId) renderDetail();
    }
    return res.ok;
  }

  function renderSummary() {
    var proposals = readProposals();
    var pending = proposals.filter(function (p) { return p.status === 'submitted'; }).length;
    var approved = proposals.filter(function (p) { return p.status === 'approved'; }).length;
    var el = byId('collab-summary');
    if (el) {
      el.textContent = 'D5 整期需求基准 ' + ROWS.length + ' 行 · USNJ 补货建议 ' +
        (BASELINE.recommendation_rows || 0) + ' 行 · 本地提案 ' + proposals.length +
        '（待模拟审核 ' + pending + ' / 模拟通过 ' + approved + '）';
    }
    var count = byId('collab-proposal-count');
    if (count) count.textContent = proposals.length ? '（' + proposals.length + ' 条）' : '（0 条）';
  }

  function renderTable() {
    var tbody = byId('collab-rows');
    if (!tbody) return;
    var q = String((byId('collab-search') || {}).value || '').trim().toLowerCase();
    var rows = ROWS.filter(function (r) {
      if (!q) return true;
      return [r.name, r.sku, r.product_id].join(' ').toLowerCase().indexOf(q) >= 0;
    });
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted">没有匹配的需求行</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      var cls = String(r.id) === selectedId ? ' class="selected"' : '';
      return '<tr data-row-id="' + esc(r.id) + '"' + cls + '>' +
        '<td><strong>' + esc(r.name || r.product_id) + '</strong><br>' +
        '<small class="muted">' + esc(r.sku || '') + '</small></td>' +
        '<td>' + esc(r.physical_form || '—') + '</td>' +
        '<td>' + esc(r.unit || '—') + '</td>' +
        '<td>' + esc(period(r)) + '</td>' +
        '<td class="num">' + num(r.baseline_qty) + '</td></tr>';
    }).join('');
    Array.prototype.forEach.call(tbody.querySelectorAll('tr[data-row-id]'), function (tr) {
      tr.addEventListener('click', function () { selectRow(tr.getAttribute('data-row-id')); });
    });
  }

  function selectRow(id) {
    selectedId = String(id);
    renderTable();
    renderDetail();
  }

  function setFormEnabled(enabled) {
    var form = byId('collab-form');
    if (!form) return;
    Array.prototype.forEach.call(
      form.querySelectorAll('input, select, textarea, button'),
      function (el) { el.disabled = !enabled; }
    );
  }

  function renderDetail() {
    var host = byId('collab-detail');
    if (!host) return;
    var r = ROW_INDEX[selectedId];
    if (!r) {
      host.innerHTML = '<p class="muted">选择左侧需求行，查看明细并补充业务判断。</p>';
      return;
    }
    var start = day(r.week);
    var end = day(r.period_end);
    var inventory = (r.inventory_qty === null || r.inventory_qty === undefined || r.inventory_qty === '')
      ? '未知' : num(r.inventory_qty) + ' ' + esc(r.unit || '');
    host.innerHTML = '' +
      '<div class="detail-head"><div class="micro">需求详情 / ' + esc(r.branch || '') + '</div>' +
      '<h2>' + esc(r.name || r.product_id) + '</h2>' +
      '<p class="hint">' + esc(r.sku || '') + ' · ' + esc(r.physical_form || '—') + ' · ' + esc(r.unit || '—') + '</p></div>' +
      '<dl class="kv">' +
      '<div><dt>期间</dt><dd>' + esc(period(r)) + '</dd></div>' +
      '<div><dt>D5 整期需求基准</dt><dd>' + num(r.baseline_qty) + ' ' + esc(r.unit || '') + '</dd></div>' +
      '<div><dt>当前库存</dt><dd>' + inventory + '</dd></div>' +
      '</dl>' +
      '<p class="note">' + esc(r.supply_note || '暂无供应补充说明。') + '</p>' +
      '<form id="collab-form" novalidate>' +
      '<h3 class="form-title">补充你的业务判断</h3>' +
      '<label for="wb-kind">调整方式</label>' +
      '<select id="wb-kind">' +
      KINDS.map(function (kind) {
        return '<option value="' + kind + '">' + KIND_LABELS[kind] + '</option>';
      }).join('') +
      '</select>' +
      '<label for="wb-value" id="wb-value-label">调整数量（可为负数）</label>' +
      '<input id="wb-value" type="number" step="any" placeholder="例如 20 或 -10">' +
      '<div class="hint" id="wb-preview"></div>' +
      '<div class="two">' +
      '<div><label for="wb-start">事件开始</label><input id="wb-start" type="date" value="' + esc(start) + '"></div>' +
      '<div><label for="wb-end">事件结束</label><input id="wb-end" type="date" value="' + esc(end) + '"></div>' +
      '</div>' +
      '<label for="wb-event-id">业务事件 ID <span class="req">*</span></label>' +
      '<input id="wb-event-id" placeholder="例如 活动-2026双十一-上海">' +
      '<label for="wb-reason">调整原因 <span class="req">*</span></label>' +
      '<textarea id="wb-reason" placeholder="说明活动、渠道变化或异常，以及数量判断依据"></textarea>' +
      '<label for="wb-evidence">证据或补充说明</label>' +
      '<input id="wb-evidence" placeholder="活动编号或可核对的信息">' +
      '<div class="submitline"><span class="hint">仅写入本浏览器，不上传、不审批、不写 EN。</span>' +
      '<button class="btn accent" id="wb-submit" type="submit">保存本地演示提案</button></div>' +
      '</form>' +
      '<p class="form-note">仅演示需求提案，不修改 USNJ 补货建议，不进入采购。</p>';
    byId('wb-kind').addEventListener('change', updatePreview);
    byId('wb-value').addEventListener('input', updatePreview);
    byId('collab-form').addEventListener('submit', submitProposal);
    updatePreview();
    if (!storageState.available) {
      setFormEnabled(false);
      message(storageState.message, true);
    }
  }

  function updatePreview() {
    var kindEl = byId('wb-kind');
    var valueEl = byId('wb-value');
    var labelEl = byId('wb-value-label');
    if (!kindEl || !valueEl || !labelEl) return;
    var kind = kindEl.value;
    var r = ROW_INDEX[selectedId] || {};
    var base = Number(r.baseline_qty);
    valueEl.disabled = kind === 'event_only';
    valueEl.min = kind === 'total' ? String(MIN_TOTAL) : kind === 'percent' ? String(MIN_PERCENT) : '';
    labelEl.textContent = kind === 'percent' ? '调整比例（20 表示增加 20%）' :
      kind === 'total' ? '调整后的总量' : '调整数量（可为负数）';
    var preview = byId('wb-preview');
    if (!preview) return;
    if (kind === 'event_only') {
      preview.textContent = '仅留存业务事件，不改变需求数量。';
      return;
    }
    if (valueEl.value === '' || !isFinite(Number(valueEl.value)) || !isFinite(base)) {
      preview.textContent = '保存后仅在本浏览器可见，待本地审核视角确认。';
      return;
    }
    var value = Number(valueEl.value);
    var total = kind === 'total' ? value : kind === 'percent' ? base * (1 + value / 100) : base + value;
    preview.textContent = '本条提案预览：' + num(base) + ' → ' + num(total) + ' ' + (r.unit || '') + '（未包含其他提案）';
  }

  function collectProposal(r) {
    var kind = byId('wb-kind').value;
    var eventId = byId('wb-event-id').value.trim();
    var reason = byId('wb-reason').value.trim();
    var evidence = byId('wb-evidence').value.trim();
    var start = byId('wb-start').value;
    var end = byId('wb-end').value;
    var check = validateInput(kind, byId('wb-value').value, eventId, reason, start, end);
    if (check.error) return {error: check.error};
    var value = check.value;
    return {proposal: {
      id: newId(), row_id: r.id, kind: kind, value: value,
      start: start, end: end, event_id: eventId, reason: reason,
      evidence: evidence, created_at: new Date().toISOString(), status: 'submitted'
    }};
  }

  function submitProposal(event) {
    event.preventDefault();
    if (!storageState.available) {
      message('浏览器已禁用本地存储，无法保存提案。', true);
      return;
    }
    var r = ROW_INDEX[selectedId];
    if (!r) { message('请先在左侧选择需求行。', true); return; }
    var out = collectProposal(r);
    if (out.error) { message(out.error, true); return; }
    var list = readProposals();
    list.push(out.proposal);
    var ok = writeProposals(list);
    renderSummary();
    renderProposals();
    if (ok) showStorageNotice('');
    message(ok ? '提案已保存在本浏览器（刷新仍保留；仅演示，不上传、不审批、不写 EN）。'
               : '浏览器已禁用本地存储，无法保存提案。', !ok);
  }

  function renderProposals() {
    var host = byId('collab-proposals');
    if (!host) return;
    var proposals = readProposals().slice().reverse();
    if (!proposals.length) {
      host.innerHTML = '<p class="muted">还没有提案。选择需求行，补充第一条业务判断。</p>';
      return;
    }
    host.innerHTML = proposals.map(function (p) {
      var r = ROW_INDEX[String(p.row_id)] || {};
      var amount = p.kind === 'event_only' ? '不调整数量' :
        p.kind === 'percent' ? num(p.value) + '%' : num(p.value) + ' ' + (r.unit || '');
      var actions = '';
      if (view === 'reviewer' && p.status === 'submitted') {
        actions = '<div class="actions">' +
          '<button class="btn small" data-decision="approved" data-id="' + esc(p.id) + '">模拟通过</button>' +
          '<button class="btn small" data-decision="rejected" data-id="' + esc(p.id) + '">模拟驳回</button>' +
          '</div>';
      }
      return '<article class="proposal">' +
        '<div><h4>' + esc(r.name || r.sku || p.row_id) + ' <span class="muted">' + esc(r.branch || '') + '</span></h4>' +
        '<p>' + esc(KIND_LABELS[p.kind] || p.kind) + ' · ' + esc(amount) +
        ' <span class="muted">/ ' + esc(day(p.start)) + ' — ' + esc(day(p.end)) + '</span></p>' +
        '<p>' + esc(p.reason) + '</p>' +
        (p.evidence ? '<p class="meta">依据：' + esc(p.evidence) + '</p>' : '') +
        '<p class="meta">事件 ' + esc(p.event_id) + ' · ' + esc(p.created_at) + '</p>' +
        actions + '</div>' +
        '<div><span class="status ' + esc(p.status) + '">' + esc(STATUS_LABELS[p.status] || p.status) + '</span></div>' +
        '</article>';
    }).join('');
    Array.prototype.forEach.call(host.querySelectorAll('[data-decision]'), function (btn) {
      btn.addEventListener('click', function () {
        setStatus(btn.getAttribute('data-id'), btn.getAttribute('data-decision'));
      });
    });
  }

  function setStatus(id, status) {
    var list = readProposals().map(function (p) {
      if (String(p.id) === String(id)) p.status = status;
      return p;
    });
    writeProposals(list);
    renderSummary();
    renderProposals();
    message('本地状态已更新为「' + (STATUS_LABELS[status] || status) + '」，仅保存在本浏览器。');
  }

  function bindViewSwitch() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-view]'), function (btn) {
      btn.addEventListener('click', function () {
        view = btn.getAttribute('data-view');
        Array.prototype.forEach.call(document.querySelectorAll('[data-view]'), function (x) {
          x.classList.toggle('active', x === btn);
        });
        renderProposals();
      });
    });
  }

  function init() {
    try {
      probeStorage();
      bindViewSwitch();
      var search = byId('collab-search');
      if (search) search.addEventListener('input', renderTable);
      renderSummary();
      renderTable();
      renderProposals();
      if (!storageState.available) showStorageNotice(storageState.message);
    } catch (e) {
      showStorageNotice('页面初始化失败：' + (e && e.message ? e.message : String(e)));
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


def build(snapshot_path: Path, baseline_path: Path, b_dir: Path | None = None) -> str:
    snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    rows = snap["rows"]
    baseline_doc, baseline_rows = load_baseline(Path(baseline_path))

    b1 = read_b(b_dir, "B_USNJ归属清单.csv")
    b2 = read_b(b_dir, "B_待确认.csv")
    a_rows = _sku_universe(rows)

    summary = {k: sum(1 for r in rows if r.get(k)) for k in
               ("needs_decision", "low_confidence", "special", "ownership_pending")}

    payload = {
        "version": baseline_doc.get("version"),
        "as_of": baseline_doc.get("as_of"),
        "demo": baseline_doc.get("demo"),
        "branch": BRANCH,
        "recommendation_rows": len(rows),
        "rows": baseline_rows,
    }

    tab_js = (
        "document.querySelectorAll('nav button').forEach(function (b) {"
        "b.addEventListener('click', function () {"
        "document.querySelectorAll('nav button').forEach(function (x) {x.classList.remove('active')});"
        "b.classList.add('active');"
        "document.querySelectorAll('main > section').forEach(function (s) {s.classList.remove('active')});"
        "var t = document.getElementById(b.dataset.t);if (t) {t.classList.add('active')}"
        "window.scrollTo(0, 0)})});"
    )
    data_text = embed_json(payload)
    main_js = tab_js + _COLLAB_JS.replace("/*__COLLAB_LIB__*/", COLLAB_LIB)
    csp = CSP_STATIC + "; script-src " + csp_hash(main_js) + " " + csp_hash(data_text)

    nav = "".join(
        "<button%s data-t='%s'>%s</button>" % (
            " class='active'" if key == "home" else "", key, esc(title))
        for key, title in TABS
    )

    doc = "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
    doc += f"<meta http-equiv=\"Content-Security-Policy\" content=\"{csp}\">"
    doc += "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    doc += "<title>USNJ 补货协同工作台（只读演示）</title><style>"
    doc += "body{font-family:'Microsoft YaHei',Arial,sans-serif;margin:0;background:#f4f7f9;color:#16324a}"
    doc += "header{background:#16324a;color:#fff;padding:18px 28px}header h1{margin:0;font-size:22px}header p{margin:6px 0 0;color:#cfe0ea}"
    doc += "main{padding:20px 28px}.cards{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}.card{background:#fff;border-radius:8px;padding:12px 16px;flex:1;min-width:120px;border-left:4px solid #19a08c}.card b{font-size:24px;display:block}"
    doc += "nav button{border:0;background:#e3edf2;padding:10px 16px;margin-right:6px;margin-bottom:6px;border-radius:6px;cursor:pointer;font-size:14px}nav button.active{background:#16324a;color:#fff}"
    doc += "section{display:none;background:#fff;border-radius:8px;padding:16px;margin-top:12px}section.active{display:block}table{width:100%;border-collapse:collapse;font-size:13px}"
    doc += "th,td{padding:8px;border-bottom:1px solid #e1ebf0;text-align:left;vertical-align:top}th{background:#16324a;color:#fff}tr.detail td{background:#f8fbfc}"
    doc += ".grid{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;margin:8px 0}.grid div{background:#fff;border:1px dashed #cbd8df;border-radius:6px;padding:6px}"
    doc += ".chain{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.chain span{background:#eef5f8;border-radius:6px;padding:6px 10px}.b{display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;margin:1px}"
    doc += ".b.red{background:#fde8e8;color:#a12}.b.warn{background:#fff1d6;color:#8a5a00}.b.purple{background:#efe6ff;color:#5b2b9a}.b.gray{background:#e8edf0;color:#456}.small{font-size:12px}.muted{color:#6b7f8c}details summary{cursor:pointer;color:#19a08c;margin:4px 0}"
    doc += ".demo-banner{background:#fff1d6;color:#7a4b00;border:1px solid #f0d49a;border-radius:8px;padding:10px 14px;margin:0 0 14px;font-size:13px;line-height:1.6}"
    doc += ".demo-banner code{background:#fff;border:1px solid #f0d49a;border-radius:4px;padding:1px 5px;font-size:12px}"
    doc += ".datachips{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.datachips .chip{border:1px solid #2f5871;border-radius:20px;padding:4px 12px;font-size:12px;color:#dceaf2}.datachips .chip.alt{border-color:#19a08c;color:#a9e4da}"
    doc += ".form-note{background:#eef5f8;border-left:3px solid #19a08c;padding:8px 10px;font-size:12px;color:#345;margin:8px 0 0}"
    doc += ".storage-notice{background:#fde8e8;color:#a12;border:1px solid #f0b3b3;border-radius:6px;padding:8px 12px;font-size:12px;margin:8px 0}"
    doc += ".collab-toolbar{display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}"
    doc += ".viewswitch button{border:1px solid #cbd8df;background:#eef5f8;padding:7px 14px;border-radius:6px;cursor:pointer}.viewswitch button.active{background:#16324a;color:#fff;border-color:#16324a}"
    doc += ".collab-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:16px}@media(max-width:980px){.collab-grid{grid-template-columns:1fr}}"
    doc += ".collab-left input[type=search]{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #cbd8df;border-radius:6px;margin-bottom:8px}"
    doc += ".table-scroll{max-height:60vh;overflow:auto;border:1px solid #e1ebf0;border-radius:6px}#collab-table th{position:sticky;top:0}"
    doc += "#collab-table tr[data-row-id]{cursor:pointer}#collab-table tr[data-row-id]:hover td{background:#f0f7f9}#collab-table tr.selected td{background:#e3f1ef}#collab-table td.num{text-align:right}"
    doc += ".collab-right{border:1px solid #e1ebf0;border-radius:6px;padding:14px;background:#fbfdfe;min-height:200px}"
    doc += ".detail-head .micro{font-size:10px;letter-spacing:2px;color:#19a08c;font-weight:bold}.detail-head h2{margin:6px 0 4px;font-size:19px}.detail-head .hint{margin:0;color:#6b7f8c;font-size:12px}"
    doc += ".kv{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.kv div{background:#fff;border:1px dashed #cbd8df;border-radius:6px;padding:8px}.kv dt{font-size:11px;color:#6b7f8c}.kv dd{margin:2px 0 0;font-weight:bold}"
    doc += ".note{background:#fff;border-left:3px solid #19a08c;padding:8px 10px;font-size:12px;color:#345}"
    doc += "#collab-form{margin-top:12px;display:flex;flex-direction:column;gap:6px}#collab-form label{font-size:12px;font-weight:bold;margin-top:4px}#collab-form input,#collab-form select,#collab-form textarea{padding:7px 9px;border:1px solid #cbd8df;border-radius:6px;font:inherit;font-size:13px;box-sizing:border-box;width:100%}#collab-form textarea{min-height:64px;resize:vertical}"
    doc += "#collab-form .two{display:grid;grid-template-columns:1fr 1fr;gap:10px}#collab-form .two>div{display:flex;flex-direction:column}#collab-form .req{color:#c0392b}"
    doc += ".form-title{margin:10px 0 2px;font-size:15px}.submitline{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:8px}"
    doc += "#collab-form .hint{font-size:11px;color:#6b7f8c}"
    doc += ".btn{border:0;border-radius:6px;padding:8px 14px;cursor:pointer;background:#e3edf2;color:#16324a;font:inherit}.btn.accent{background:#19a08c;color:#fff}.btn.small{padding:5px 10px;font-size:12px}"
    doc += ".form-message{min-height:18px;font-size:12px;color:#46745e}.form-message.error{color:#c0392b}"
    doc += ".proposal{border:1px solid #e1ebf0;border-radius:8px;padding:12px 14px;margin-bottom:10px;display:flex;justify-content:space-between;gap:14px;background:#fbfdfe}"
    doc += ".proposal h4{margin:0 0 4px;font-size:14px}.proposal p{margin:3px 0;font-size:13px}.proposal .meta{color:#6b7f8c;font-size:12px}.actions{display:flex;gap:8px;margin-top:8px}"
    doc += ".status{display:inline-block;padding:3px 8px;border-radius:4px;font-size:11px;white-space:nowrap;background:#e8edf0;color:#456}.status.submitted{background:#fff1d6;color:#8a5a00}.status.approved{background:#dff3ea;color:#1d6b4f}.status.rejected{background:#fde8e8;color:#a12}"
    doc += "</style></head><body>"

    doc += "<header><h1>USNJ 补货协同工作台（只读演示）</h1>"
    doc += f"<p>数据包 {esc(snap.get('version') or snap.get('source_name'))} · as_of {esc(snap.get('as_of'))} · 不直接下单；采购/运营需复核</p>"
    doc += "<div class='datachips'>"
    doc += f"<span class='chip'>USNJ 补货建议（{len(rows)} 行，只读）</span>"
    doc += f"<span class='chip alt'>D5 整期需求基准（{len(baseline_rows)} 行，仅 USNJ）</span></div></header>"
    doc += "<main>"
    doc += f"<div class='demo-banner' role='note'>{DEMO_BANNER}</div>"
    doc += (f"<div class='cards'><div class='card'><b>{summary['needs_decision']}</b>需拍板</div>"
            f"<div class='card'><b>{summary['low_confidence']}</b>低置信</div>"
            f"<div class='card'><b>{summary['special']}</b>特殊品</div>"
            f"<div class='card'><b>{summary['ownership_pending']}</b>归属待确认</div>"
            f"<div class='card'><b>{len(rows)}</b>USNJ 建议行</div>"
            f"<div class='card'><b>{len(baseline_rows)}</b>D5 需求基准行</div></div>")
    doc += f"<nav>{nav}</nav>"

    doc += "<section id='home' class='active'><table><thead><tr><th>SKU / 客户 / 形态</th><th>建议</th><th>覆盖</th><th>原因</th><th>标记</th></tr></thead><tbody>"
    doc += _decision_rows(rows) + "</tbody></table></section>"

    doc += f"<section id='a'><h3>A SKU 宇宙（{len(a_rows)} 个 SKU×形态×UOM）</h3>"
    doc += "<table><thead><tr><th>SKU</th><th>形态</th><th>UOM</th><th>客户</th></tr></thead><tbody>"
    doc += "".join(f"<tr><td>{esc(x[0])}</td><td>{esc(x[1])}</td><td>{esc(x[2])}</td><td>{esc(x[3])}</td></tr>"
                  for x in a_rows)
    doc += "</tbody></table></section>"

    doc += f"<section id='b'><h3>B 归属清单（{len(b1)} 个 current USNJ）</h3>{b_table(b1)}"
    doc += f"<h3>归属待确认（{len(b2)} 个）</h3>{b_table(b2)}</section>"

    doc += "<section id='c'><h3>C 库存（当前可发，不含在途；CG 为下游缓冲不可回拨）</h3>"
    doc += "<table><thead><tr><th>SKU</th><th>C</th><th>EN已发运</th><th>EN待发</th><th>PO</th><th>SO</th><th>CG</th><th>近期SO</th><th>历史SO</th></tr></thead><tbody>"
    doc += _supply_rows(rows) + "</tbody></table></section>"

    doc += "<section id='d'><h3>D 预估（q50 中位，不是补货量；D5 v6.8）</h3>"
    doc += "<table><thead><tr><th>SKU</th><th>预测 q50</th><th>q50</th><th>q90</th><th>q95</th><th>模型</th></tr></thead><tbody>"
    doc += _forecast_rows(rows) + "</tbody></table></section>"

    doc += "<section id='e'><h3>E 供给（SO/EN/PO/C/CG；SO 不加入建议量）</h3>"
    doc += "<table><thead><tr><th>SKU</th><th>C</th><th>EN已发运</th><th>EN待发</th><th>PO</th><th>SO</th><th>CG</th><th>近期SO</th><th>历史SO</th></tr></thead><tbody>"
    doc += _supply_rows(rows) + "</tbody></table></section>"

    doc += ("<section id='method'><h3>口径与限制</h3><ul>"
            "<li>这是历史回放，不是今天的执行建议；页面显示数据包 as_of。</li>"
            "<li>C = 当前可发，不含在途；E = 按时供给；CG = 下游缓冲，不可回拨。</li>"
            "<li>SO 是 EN 分公司生产/交付单；通途 PO 是 DN 后采购入库；两者不能相加替代。</li>"
            "<li>SO 管线未加入建议量；生产/DN/通途 PO 尚未接入。</li>"
            "<li>缺失=未知，不补 0；无改量、审批、下单入口。</li>"
            "<li>USNJ 补货建议（只读）与 D5 整期需求基准（仅 USNJ）是两类不同数据：不相加、不替代。</li>"
            "<li>运营协同页签的提案只保存在本浏览器 localStorage：刷新保留，清理浏览器数据或换浏览器看不到本浏览器的提案；不上传、不审批、不写 EN。</li>"
            "</ul></section>")

    doc += "<section id='collab'>"
    doc += f"<div class='demo-banner' role='note'>{DEMO_BANNER}</div>"
    doc += "<div class='collab-toolbar'><div class='viewswitch' role='group' aria-label='本地视角'>"
    doc += "<button type='button' class='active' data-view='operator'>运营视角</button>"
    doc += "<button type='button' data-view='reviewer'>审核视角（模拟）</button></div>"
    doc += f"<span class='muted' id='collab-summary'>D5 整期需求基准 {len(baseline_rows)} 行 · USNJ 补货建议 {len(rows)} 行</span></div>"
    doc += "<p class='storage-notice' id='collab-storage-notice' role='alert' hidden></p>"
    doc += "<div class='collab-grid'><div class='collab-left'>"
    doc += "<input id='collab-search' type='search' placeholder='搜索商品 / SKU' autocomplete='off'>"
    doc += "<div class='table-scroll'><table class='small' id='collab-table'>"
    doc += "<thead><tr><th>商品 / SKU</th><th>形态</th><th>单位</th><th>预测期</th><th>D5 整期需求基准</th></tr></thead>"
    doc += "<tbody id='collab-rows'><tr><td colspan='5' class='muted'>正在载入…</td></tr></tbody></table></div></div>"
    doc += "<div class='collab-right' id='collab-detail'><p class='muted'>选择左侧需求行，查看明细并补充业务判断。</p></div></div>"
    doc += "<h3>本浏览器中的提案 <span id='collab-proposal-count' class='muted'>（0 条）</span></h3>"
    doc += "<div id='collab-proposals'><p class='muted'>还没有提案。</p></div>"
    doc += "<p class='form-message' id='collab-message' aria-live='polite'></p>"
    doc += "</section></main>"

    doc += f"<script type='application/json' id='supply-workbench-baseline'>{data_text}</script>"
    doc += "<script>" + main_js + "</script></body></html>"
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description="USNJ 补货协同工作台（单文件静态页）")
    ap.add_argument("--snapshot", required=True, help="快照 JSON 路径")
    ap.add_argument("--baseline", required=True, help="需求基准 JSON 路径")
    ap.add_argument("--b-dir", default=None, help="B_*.csv 目录（可选）")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    args = ap.parse_args(argv)

    doc = build(
        Path(args.snapshot),
        Path(args.baseline),
        Path(args.b_dir) if args.b_dir else None,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(out, len(doc))


if __name__ == "__main__":
    main()
