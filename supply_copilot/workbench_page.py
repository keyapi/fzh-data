# -*- coding: utf-8 -*-
"""USNJ 补货协同工作台（单文件静态页生成器，演示用）。

第 1 步 UI 迁移：把本地需求工作台（``demand_collaboration/static/index.html``）
的视觉与「左表 + 右详情」结构移植到本生成器，导航收敛为四个一级视图：

    工作台 / 证据链 / 分析方法 / 口径

- 工作台：补货建议（默认，只读）/ 需求基准（唯一允许演示提案的一方）切换，
  明细默认收起在右侧，不在主表内展开。
- 证据链：逐行 L2/L3 证据（身份、期间、需求、供给各阶段、SO 三段、库存快照、
  来源哈希、未知道原因），上一条/下一条与返回主表。
- 分析方法：A/B/C/D/E 五张表（字段与行数与迁移前完全一致，服务端渲染）。
- 口径：业务定义、模式语义与字段来源。

数据契约不变：只读快照 + 需求基准 + 可选 B_*.csv。所有提案只写入本浏览器
``localStorage``（键 ``supply-workbench:proposals:v2``），页面不发起任何网络
请求、不写 EN、不提供下单/改量/真实审批入口。旧键
``supply-workbench:proposals:v1`` 只作为「旧演示记录」只读展示，不迁移、不删除。

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
from collections import Counter
from pathlib import Path

from .usnj_page import action, b_table, badge, esc, extra, i, read_b, so_lines

STORAGE_KEY = "supply-workbench:proposals:v2"
LEGACY_STORAGE_KEY = "supply-workbench:proposals:v1"
BRANCH = "USNJ"

# 四个一级视图（迁移前是 8 个并列页签）。
VIEWS = [
    ("workbench", "工作台"),
    ("evidence", "证据链"),
    ("analysis", "分析方法"),
    ("method", "口径"),
]

# 分析方法下的二级页签，内容取自迁移前的 A–E 页签，字段一个不少。
ANALYSIS_TABS = [
    ("a", "A 商品范围"),
    ("b", "B 归属"),
    ("c", "C 库存"),
    ("d", "D 需求预估"),
    ("e", "E 到期供给"),
]

BANNER_TEXT = "静态演示 · 数据快照 {as_of} · 提案只存本浏览器 · 不上传/不审批/不写 EN"

# 三件事分开标识：服务可用 ≠ 库存实时 ≠ 建议可执行。均不使用绿色。
MODE_CHIPS = [
    ("服务", "静态内嵌快照（无后端）"),
    ("库存", "快照时点 {as_of}（非实时）"),
    ("建议", "只读，不可下单"),
]

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

  function isBlank(v) { return v === null || v === undefined || v === ''; }

  function escapeHtml(v) {
    return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  // Display helpers live here so they can be executed under Node in tests.
  // Unknown stays null (never 0); formatting is a separate step.
  function formatQty(v) {
    if (isBlank(v)) return null;
    var n = Number(v);
    if (!isFinite(n)) return null;
    return n.toLocaleString('zh-CN', {maximumFractionDigits: 2});
  }

  function formatInt(v) {
    if (isBlank(v)) return null;
    var n = Number(v);
    if (!isFinite(n)) return null;
    return Math.round(n).toLocaleString('zh-CN');
  }

  // The 11-24 baseline export names this field demand_qty; older fixtures use
  // baseline_qty. Both mean "本期需求基准数量" — never coerce a missing one to 0.
  function baselineQty(row) {
    if (!row) return null;
    if (!isBlank(row.baseline_qty)) return row.baseline_qty;
    if (!isBlank(row.demand_qty)) return row.demand_qty;
    return null;
  }

  // Normalized business key: SKU x 形态 x 单位. SKU alone is one-to-many.
  function rowKey(row) {
    if (!row) return '';
    var u = isBlank(row.uom) ? row.unit : row.uom;
    return [
      isBlank(row.sku) ? '' : String(row.sku),
      isBlank(row.physical_form) ? '' : String(row.physical_form),
      isBlank(u) ? '' : String(u)
    ].join('|');
  }

  // Row-key multiplicity per side. A suggestion may only open the linked
  // baseline form when its key is unique on BOTH sides; anything else is
  // reported instead of silently picking the first row.
  function countKeys(rows) {
    var out = {};
    (rows || []).forEach(function (r) {
      var k = rowKey(r);
      out[k] = (out[k] || 0) + 1;
    });
    return out;
  }

  function matchKind(recCounts, baseCounts, key) {
    var rc = (recCounts && recCounts[key]) || 0;
    var bc = (baseCounts && baseCounts[key]) || 0;
    if (rc === 1 && bc === 1) return 'unique';
    if (rc > 0 && bc > 0) return 'ambiguous';
    if (rc > 0) return 'only_rec';
    if (bc > 0) return 'only_base';
    return 'none';
  }

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
    if (!(p.baseline_version === undefined || p.baseline_version === null ||
          typeof p.baseline_version === 'string')) return false;
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


# CSS tokens lifted from the local workbench page (demand_collaboration/static):
# paper #f5f4ef / navy #172e43 / ink #203548 / line #dedfd8 / orange #df6b34.
# Deliberately no green status tokens: availability must not read as "can buy".
STYLE = """
:root{--navy:#172e43;--ink:#203548;--muted:#74808a;--paper:#f5f4ef;--line:#dedfd8;
--orange:#df6b34;--white:#fffefa;--warn:#a35b29;--warnbg:#f9ead9;--cool:#2b5e7d;
--coolbg:#e3eef4;--reject:#b54735;--soft:#f0f3ef}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font-family:"Microsoft YaHei UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:14px}
button,input,select,textarea{font:inherit}
button{cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
input,select,textarea{border:1px solid var(--line);border-radius:3px;background:var(--white);
padding:8px 10px;color:var(--ink);min-width:0}
label{font-size:11px;color:#596a77}
h1,h2,h3,h4{margin:0}
.topstack{position:sticky;top:0;z-index:30}
.modebanner{background:var(--warn);color:#fff;padding:8px 16px;font-size:12px;line-height:1.5;
display:flex;gap:10px 14px;flex-wrap:wrap;align-items:center;justify-content:space-between}
.modebanner .mb-main{font-weight:bold;letter-spacing:.3px}
.mchips{display:flex;gap:6px;flex-wrap:wrap}
.mchip{border:1px solid rgba(255,255,255,.55);border-radius:10px;padding:2px 9px;
font-size:11px;white-space:nowrap}
.mchip b{font-weight:bold;margin-right:4px}
header.site{background:var(--navy);color:#fff;padding:15px 28px;display:flex;
justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.brand{font-family:Georgia,serif;letter-spacing:2px;font-size:21px}
.brand span{font:11px "Microsoft YaHei UI",sans-serif;letter-spacing:3px;color:#b9c8d2;
margin-left:14px}
.sitemeta{font-size:11px;color:#c8d3dc;text-align:right;line-height:1.8}
.datachips{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.datachips .chip{border:1px solid #2f5871;border-radius:20px;padding:3px 11px;font-size:11px;
color:#dceaf2}
nav.topnav{background:var(--navy);display:flex;gap:2px;padding:0 22px;overflow-x:auto;
border-top:1px solid #2b4459}
nav.topnav button{border:0;background:none;color:#b9c8d2;padding:11px 18px;font-size:14px;
border-bottom:3px solid transparent;white-space:nowrap}
nav.topnav button.active{color:#fff;border-bottom-color:var(--orange);font-weight:bold}
main{padding:22px 28px 44px}
.view{display:none}.view.active{display:block}
.viewhead{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
margin-bottom:14px;flex-wrap:wrap}
.viewhead h1{font-size:22px;line-height:1.4}
.eyebrow{color:var(--orange);font-size:10px;letter-spacing:2px;font-weight:bold;
margin-bottom:6px}
.sub{color:var(--muted);font-size:12px;margin:6px 0 0;line-height:1.7;max-width:78ch}
.btn{border:1px solid var(--line);border-radius:3px;background:var(--white);color:var(--ink);
padding:8px 13px;font-size:12px}
.btn.primary{background:var(--navy);color:#fff;border-color:var(--navy)}
.btn.accent{background:var(--orange);color:#fff;border-color:var(--orange)}
.btn.small{padding:5px 9px;font-size:11px}
.btn.ghost{background:none}
.setswitch{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden;
background:var(--white)}
.setswitch button{border:0;background:none;padding:8px 14px;color:var(--muted);font-size:13px}
.setswitch button.active{background:var(--navy);color:#fff}
.wbtop{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}
.wbfilters{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.wbfilters input[type=search]{flex:1;min-width:210px}
.wbfilters select{width:132px}
.check{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);
white-space:nowrap}
.wbcount{font-size:11px;color:var(--muted);display:flex;gap:12px;align-items:center;
flex-wrap:wrap}
/* Workbench shell: the ONLY layout basis is its own content width (container
   query), never the viewport. W >= 1100 two-column 420px detail; 900-1099 380px;
   721-899 340px; <= 720 single column + bottom sheet. */
.workbench-shell{container-type:inline-size;container-name:workbench;min-width:0}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:16px;
align-items:stretch;height:var(--ws-h,560px);min-height:0}
.board,.detail,.panel{background:var(--white);border:1px solid var(--line);border-radius:4px}
.board{overflow:hidden;min-width:0;min-height:0;display:flex;flex-direction:column}
.board-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain}
.scroll{overflow:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;font-weight:normal;font-size:10px;color:var(--muted);background:#f8f8f4;
padding:11px 12px;white-space:nowrap;position:sticky;top:0;z-index:1}
td{padding:13px 12px;border-bottom:1px solid #ecece5;vertical-align:top;overflow-wrap:anywhere}
tbody tr:last-child td{border:0}
table.rows tbody tr[data-key]{cursor:pointer}
table.rows tbody tr[data-key]:hover td{background:#fafaf6}
.row-select{border:0;background:none;padding:0;text-align:left;color:var(--ink);width:100%;
font-size:12px}
.row-select strong{display:block;line-height:1.6}
.row-select small{display:block;color:var(--muted);font-size:10px;margin-top:3px}
tbody tr.selected td{background:var(--soft)}
tbody tr.selected td:first-child{box-shadow:inset 3px 0 var(--orange)}
tbody tr[data-key] td:first-child{position:relative}
/* Absolutely placed so selecting a row never changes its height (no list jitter). */
.sel-tag{display:none}
tr.selected .sel-tag{display:inline-block;position:absolute;right:10px;top:10px;
padding:2px 7px;border-radius:3px;background:var(--orange);color:#fff;font-size:10px;
letter-spacing:1px}
.sheet-hint{display:none}
.sub-merged,.row-select .sub-merged{display:none}
.qty{font-family:Georgia,serif;font-size:16px}
.week{display:block;font-size:10px;color:var(--muted);margin-top:3px}
.tablefoot{padding:11px 14px;border-top:1px solid var(--line);font-size:10px;color:var(--muted);
display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;flex:0 0 auto}
.empty{padding:34px 18px;text-align:center;color:var(--muted);font-size:12px}
.detail-slot{min-width:0;min-height:0;height:100%}
.detail{overflow:hidden;min-width:0;min-height:0}
.detail-content{height:100%;overflow:auto;background:var(--white);border:1px solid var(--line);
border-radius:4px;overflow-wrap:anywhere;overscroll-behavior:contain}
.detail-head{position:sticky;top:0;z-index:3;background:var(--white);
padding:18px 20px 14px;border-bottom:1px solid var(--line)}
.detail-head h2{margin:6px 0;font-size:17px;line-height:1.5;outline:none}
.detail-head .hint{margin:0;color:var(--muted);font-size:11px;line-height:1.7}
.detail-anchors{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.detail-anchors button{border:1px solid var(--line);background:var(--soft);border-radius:20px;
padding:4px 11px;font-size:11px;color:var(--ink)}
.dsec{border-top:1px solid var(--line);padding-top:12px;margin-top:14px;
scroll-margin-top:130px;outline:none}
.dsec:first-child{border-top:0;margin-top:0;padding-top:0}
.dsec>h3{font-size:11px;letter-spacing:1px;color:var(--muted);margin:0 0 8px}
.lay{border:1px solid #e6e8e0;border-radius:6px;margin:7px 0;background:#fbfdfe}
.lay>summary{cursor:pointer;padding:8px 10px;font-size:12px;line-height:1.8;
list-style:none;overflow-wrap:anywhere}
.lay>summary::-webkit-details-marker{display:none}
.lay>summary::before{content:"\\25B8";color:var(--muted);margin-right:5px}
.lay[open]>summary::before{content:"\\25BE"}
.lay>summary b{font-weight:bold}
.lay>summary strong{font-family:Georgia,serif;font-size:14px;margin:0 2px}
.lay .lay-body{padding:0 10px 10px;border-top:1px dashed #e2e6e1}
.ev-warn{background:var(--warnbg);color:#7a4318;border-left:3px solid var(--warn);
padding:8px 10px;font-size:11px;line-height:1.7;margin:8px 0;overflow-wrap:anywhere}
.ev-warn b{display:block;margin-bottom:3px}
.ev-warn ul{margin:0;padding-left:17px}
.ev-warn li{margin:2px 0}
.readonly-reason{font-size:11px;line-height:1.8;color:#33454f;background:#eef1ec;
border-left:3px solid var(--muted);padding:7px 10px;margin:8px 0}
.readonly-reason.warn{background:var(--warnbg);border-left-color:var(--warn);color:var(--warn)}
.target-note{font-size:11px;line-height:1.8;background:var(--coolbg);color:#234a60;
border-left:3px solid var(--cool);padding:7px 10px;margin:8px 0}
.draft-note{margin:6px 0 0;color:var(--warn)}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;
clip:rect(0 0 0 0);white-space:nowrap;border:0}
/* bottom sheet (narrow container only; wide keeps the inline right column) */
dialog.sheet{position:fixed;inset:auto 0 0 0;width:100%;max-width:none;
height:max(220px, min(65dvh, calc(100dvh - var(--stack-h,0px) - 25dvh)));
max-height:75dvh;margin:0;padding:0;border:0;
border-radius:12px 12px 0 0;background:var(--white);color:var(--ink);
box-shadow:0 -10px 34px rgba(23,46,67,.28);overflow:hidden}
dialog.sheet::backdrop{background:rgba(23,46,67,.28)}
.sheet-wrap{display:flex;flex-direction:column;height:100%}
.sheet-bar{position:relative;flex:0 0 auto;display:flex;align-items:center;
justify-content:flex-end;padding:14px 14px 8px;border-bottom:1px solid var(--line);
background:var(--white)}
.sheet-handle{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
display:block;width:56px;height:5px;border-radius:3px;background:#c9d2d8;
cursor:grab;touch-action:none}
.sheet-close{margin-left:auto}
.sheet-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain}
.sheet-scroll .detail-content{height:auto;overflow:visible;border:0;border-radius:0}
.sheet-scroll .detail-head{padding-top:10px}
@media (max-height:360px){dialog.sheet{height:auto;max-height:75%}}
@container workbench (max-width:1099.9px){
  .workspace{grid-template-columns:minmax(0,1fr) 380px;gap:12px}
}
/* 900-1099: 商品/期间/建议/覆盖/标记 take priority in the table; the reason
   lives in the right-hand summary (any remaining columns scroll inside the table). */
@container workbench (min-width:900px) and (max-width:1099.9px){
  .col-reason{display:none}
}
@container workbench (min-width:721px) and (max-width:899.9px){
  .workspace{grid-template-columns:minmax(0,1fr) 340px;gap:12px}
  .col-period,.col-coverage,.col-flags{display:none}
  .sub-merged,.row-select .sub-merged{display:block}
}
@container workbench (max-width:720px){
  .workspace{display:block;grid-template-columns:1fr;height:auto;gap:0}
  .board{display:block}
  .board-scroll{overflow:visible}
  .detail-slot{display:none}
  .l1{grid-template-columns:1fr}
  table.rows,table.rows tbody,table.rows tr,table.rows td{display:block;width:100%}
  table.rows thead{display:none}
  table.rows tr{border-bottom:1px solid var(--line);padding:6px 0}
  table.rows td{border:0;padding:4px 14px}
  table.rows td[data-label]:before{content:attr(data-label) "：";color:var(--muted);
    font-size:10px}
  tr.selected .sheet-hint{display:block;position:absolute;right:12px;top:10px;
    font-size:10px;color:var(--orange)}
  tr.selected .sel-tag{display:none}
}
.micro{font-size:10px;letter-spacing:1px;color:var(--muted);text-transform:none}
.detail-body{padding:16px 20px}
.l0{font-size:13px;line-height:1.8;margin:0 0 12px}
.l1{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0 14px}
.l1>div{border:1px dashed #cbd8df;border-radius:6px;padding:8px;background:#fbfdfe}
.l1 strong{display:block;font-size:15px;margin-top:3px}
.l1 small{display:block;color:var(--muted);font-size:10px;margin-top:3px;line-height:1.5}
.note{background:#eef1ec;border-left:3px solid var(--orange);padding:8px 10px;font-size:11px;
color:#345;line-height:1.7;margin:12px 0}
.mutednote{font-size:10px;color:var(--muted);line-height:1.7}
.unknown{color:var(--warn);font-style:italic}
.rec-badge{display:inline-block;padding:3px 7px;margin:1px 4px 1px 0;border-radius:3px;
font-size:10px;background:#eeeee8;color:var(--muted)}
.rec-badge.decision,.rec-badge.warn{background:var(--warnbg);color:var(--warn)}
.rec-badge.restock,.rec-badge.expedite{background:var(--coolbg);color:var(--cool)}
.rec-badge.special{background:#efe6f3;color:#6b4a7d}
.rec-badge.approved{background:var(--coolbg);color:var(--cool)}
.rec-badge.rejected{background:#fde8e8;color:var(--reject)}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.form-title{font-size:14px;margin:16px 0 6px}
#proposal-form{display:flex;flex-direction:column;gap:5px;margin-top:10px}
#proposal-form label{font-weight:bold;margin-top:5px}
#proposal-form input,#proposal-form select,#proposal-form textarea{width:100%}
#proposal-form textarea{min-height:60px;resize:vertical}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.two>div{display:flex;flex-direction:column}
.hint{font-size:10px;color:var(--muted);line-height:1.7;margin-top:5px}
.req{color:var(--reject)}
.submitline{display:flex;justify-content:space-between;align-items:center;gap:10px;
margin-top:10px;flex-wrap:wrap}
.form-message{min-height:18px;font-size:12px;color:#33454f;margin:10px 0 0}
.form-message.error{color:var(--reject)}
.storage-notice{background:#fde8e8;color:var(--reject);border:1px solid #f0b3b3;
border-radius:6px;padding:8px 12px;font-size:12px;margin:0 0 14px}
.panel-fold{margin-top:18px;background:var(--white);border:1px solid var(--line);
border-radius:4px;padding:0 16px 14px}
.panel-fold>summary{cursor:pointer;padding:13px 0;font-size:14px;font-weight:bold}
.viewswitch button{border:1px solid var(--line);background:var(--soft);padding:6px 12px;
border-radius:4px;cursor:pointer;font-size:12px;margin-right:6px}
.viewswitch button.active{background:var(--navy);color:#fff;border-color:var(--navy)}
.proposal{border:1px solid var(--line);border-radius:6px;padding:11px 13px;margin-bottom:9px;
display:flex;justify-content:space-between;gap:14px;background:#fbfdfe}
.proposal h4{margin:0 0 4px;font-size:13px}
.proposal p{margin:3px 0;font-size:12px;line-height:1.6}
.proposal .meta{color:var(--muted);font-size:10px}
.status{display:inline-block;padding:3px 8px;border-radius:3px;font-size:10px;
white-space:nowrap;background:#eeeee8;color:var(--muted)}
.status.submitted{background:var(--warnbg);color:var(--warn)}
.status.approved{background:var(--coolbg);color:var(--cool)}
.status.rejected{background:#fde8e8;color:var(--reject)}
/* evidence view */
.evgrid{display:grid;grid-template-columns:minmax(0,320px) minmax(0,1fr);gap:20px;
align-items:start}
.evlist{border:1px solid var(--line);border-radius:4px;background:var(--white);overflow:hidden}
.evlist .searchline{padding:10px}
.evlist .searchline input{width:100%}
.evlist table{font-size:11px}
.evlist td{padding:9px 10px}
.evpanel{border:1px solid var(--line);border-radius:4px;background:var(--white);padding:18px 20px}
.evpanel h2{font-size:17px;margin:4px 0 6px}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:6px 0}
.kv>div{border:1px dashed #cbd8df;border-radius:6px;padding:7px 8px;background:#fbfdfe}
.kv dt{font-size:10px;color:var(--muted)}
.kv dd{margin:2px 0 0;font-weight:bold;font-size:13px;word-break:break-all}
details.raw>summary{cursor:pointer;color:var(--cool);font-size:11px;margin:6px 0}
.evnav{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
/* analysis view */
.analysis-nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.analysis-nav button{border:1px solid var(--line);background:var(--white);padding:8px 13px;
border-radius:4px;font-size:12px;color:var(--muted)}
.analysis-nav button.active{background:var(--navy);color:#fff;border-color:var(--navy)}
.analysis-pane{display:none;background:var(--white);border:1px solid var(--line);
border-radius:4px;padding:16px}
.analysis-pane.active{display:block}
.analysis-pane h2{font-size:16px;margin-bottom:6px}
.analysis-pane h3{font-size:13px;margin:14px 0 8px}
.analysis-pane p.intro{font-size:11px;color:var(--muted);line-height:1.7;margin:6px 0 12px}
.analysis-pane .scroll-x{overflow-x:auto}
.analysis-pane table{min-width:560px}
/* method view */
.method{border:1px solid var(--line);border-radius:4px;background:var(--white);padding:20px 24px}
.method h2{font-size:16px;margin:18px 0 8px}.method h2:first-child{margin-top:0}
.method ul{margin:0;padding-left:20px;font-size:12px;line-height:2;color:#33454f}
.method table{min-width:0;margin:8px 0}
.method td{padding:7px 10px}
/* analysis / audit views keep their own (viewport) media rules: they are not
   part of the container-driven workbench layout. */
@media (max-width:959px){
  .evgrid{grid-template-columns:1fr}
  .evlist{max-height:280px;overflow:auto}
}
@media (max-width:767px){
  main{padding:16px}
  header.site{padding:13px 16px}
  .brand span{display:none}
  .sitemeta{text-align:left}
  .method{padding:14px}
}
@media (prefers-reduced-motion:no-preference){
  .view.active{animation:enter .2s ease-out}
  @keyframes enter{from{opacity:.5}to{opacity:1}}
}
"""


# Browser-side app: view switching, workbench table + detail, evidence chain,
# proposals. Everything reads the embedded JSON; there is no transport at all.
APP_JS = """
(function () {
  'use strict';

  /*__COLLAB_LIB__*/

  var STORAGE_KEY = 'supply-workbench:proposals:v2';
  var LEGACY_KEY = 'supply-workbench:proposals:v1';
  var UI_KEY_PREFIX = 'supply-workbench:ui:v1';
  var KIND_LABELS = {
    delta: '增减数量', total: '调整为总量',
    percent: '按比例调整', event_only: '仅记录事件'
  };
  var FLAGS = [
    ['decision', 'needs_decision', '需拍板'],
    ['supply', 'missing_supply', '缺供给'],
    ['special', 'special', '特殊品'],
    ['pending', 'ownership_pending', '归属待确认'],
    ['low', 'low_confidence', '低置信']
  ];

  var dataEl = document.getElementById('supply-workbench-data');
  var DATA = {};
  if (dataEl) { try { DATA = JSON.parse(dataEl.textContent) || {}; } catch (e) { DATA = {}; } }
  var REC = Array.isArray(DATA.rows) ? DATA.rows : [];
  var BASEDOC = DATA.baseline || {};
  var BASE = Array.isArray(BASEDOC.rows) ? BASEDOC.rows : [];
  var AS_OF = DATA.as_of || BASEDOC.as_of || '未知';
  var REC_VERSION = DATA.version || '';
  var BASE_VERSION = BASEDOC.version || '';
  var RECON = DATA.recon || {};
  var REC_INDEX = {}, BASE_INDEX = {};
  REC.forEach(function (r) { REC_INDEX[rowKey(r)] = r; });
  BASE.forEach(function (r) { BASE_INDEX[rowKey(r)] = r; });
  var REC_COUNT = countKeys(REC), BASE_COUNT = countKeys(BASE);
  var DATA_KEY = 'v:' + (REC_VERSION || '-') + '|b:' + (BASE_VERSION || '-') +
    '|' + (DATA.branch || 'USNJ');

  var state = {
    view: 'workbench', set: 'rec', q: '', action: '',
    flags: {decision: false, supply: false, special: false, pending: false, low: false},
    recKey: null, baseKey: null,
    activated: {},          // rec row key -> baseline row id whose form is open
    evKey: null, evQ: '', review: false,
    outOfFilter: false
  };
  var mode = 'wide';
  var sheetOpen = false;
  var sheetRestore = null;
  var storageState = {available: true, message: ''};
  var drafts = {};      // DATA_KEY|rowId -> form values (this page only)
  var foldState = {};   // DATA_KEY|set|prefix|rowId|index -> 1/0
  var viewScroll = {};  // view -> {y, detail}

  function byId(id) { return document.getElementById(id); }
  function esc(v) { return escapeHtml(v); }
  function unknown() { return '<span class="unknown">未知</span>'; }
  function qty(v) { var t = formatQty(v); return t === null ? unknown() : t; }
  function intq(v) { var t = formatInt(v); return t === null ? unknown() : t; }
  function day(v) { return isBlank(v) ? '' : String(v).slice(0, 10); }
  function unitOf(r) { return r && (r.uom || r.unit) ? String(r.uom || r.unit) : ''; }
  // Short form for tables: an empty period is "待核" (the reason lives in 证据链).
  function periodShort(r) {
    var s = day(r.week || r.start || r.period_start);
    var e = day(r.period_end);
    if (!s && !e) return '<span class="unknown">待核</span>';
    return esc((s || '待核') + ' — ' + (e || '待核'));
  }
  function periodText(r) {
    var s = day(r.week || r.start || r.period_start);
    var e = day(r.period_end);
    if (!s && !e) return unknown() + '（源快照未提供期间字段）';
    return esc((s || '待核') + ' — ' + (e || '待核'));
  }
  function flag(r, field) { return !!(r && r[field]); }
  function valueOfExtra(r, key) {
    var x = r && r.extra ? r.extra[key] : null;
    return isBlank(x) ? null : x;
  }
  function actionParts(r) {
    var out = [];
    if (!isBlank(r.expedite_qty) && Number(r.expedite_qty) > 0) {
      out.push('催已有 ' + intq(r.expedite_qty));
    }
    var n = isBlank(r.new_qty) ? r.new_order_qty : r.new_qty;
    if (!isBlank(n) && Number(n) > 0) out.push('新补 ' + intq(n));
    return out;
  }
  function actionBadge(r) {
    var label = esc(r.action || '观察');
    return '<span class="rec-badge ' + esc(String(r.action || '')) + '">' + label + '</span>';
  }
  function flagsHtml(r) {
    var out = '';
    if (flag(r, 'ownership_pending')) out += '<span class="rec-badge decision">归属待确认</span>';
    if (flag(r, 'needs_decision')) out += '<span class="rec-badge decision">需拍板</span>';
    if (flag(r, 'special')) out += '<span class="rec-badge special">特殊品</span>';
    if (flag(r, 'missing_supply')) out += '<span class="rec-badge warn">缺供给</span>';
    if (flag(r, 'low_confidence')) out += '<span class="rec-badge warn">低置信</span>';
    return out || '<span class="hint">—</span>';
  }
  function announce(text) {
    var el = byId('wb-announce');
    if (el) el.textContent = text || '';
  }

  /* ---------------- workbench list ---------------- */

  function currentRows() { return state.set === 'rec' ? REC : BASE; }
  function currentIndex() { return state.set === 'rec' ? REC_INDEX : BASE_INDEX; }
  function currentRow() {
    var k = state.set === 'rec' ? state.recKey : state.baseKey;
    return k ? currentIndex()[k] : null;
  }
  function currentKey() { return state.set === 'rec' ? state.recKey : state.baseKey; }
  function setCurrentKey(k) {
    if (state.set === 'rec') state.recKey = k; else state.baseKey = k;
  }

  function matchesFlags(r) {
    for (var i = 0; i < FLAGS.length; i++) {
      var f = FLAGS[i];
      if (state.flags[f[0]] && !flag(r, f[1])) return false;
    }
    return true;
  }
  function recMatches(r) {
    if (state.action && r.action !== state.action) return false;
    if (!matchesFlags(r)) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase();
    return [r.sku, r.customer, r.physical_form, r.uom, r.reason, r.model, r.action, r.bundle_id]
      .some(function (v) { return String(v === null || v === undefined ? '' : v).toLowerCase().indexOf(q) >= 0; });
  }
  function baseMatches(r) {
    if (!matchesFlags(r)) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase();
    return [r.sku, r.name, r.product_id, r.branch, r.physical_form, r.unit, r.uom]
      .some(function (v) { return String(v === null || v === undefined ? '' : v).toLowerCase().indexOf(q) >= 0; });
  }
  function filtered() {
    var rows = currentRows();
    return rows.filter(state.set === 'rec' ? recMatches : baseMatches);
  }

  function recRowHtml(r) {
    var key = rowKey(r);
    var selected = key === state.recKey;
    var acts = actionParts(r);
    return '<tr data-key="' + esc(key) + '"' + (selected ? ' class="selected"' : '') + '>' +
      '<td data-label="商品"><button type="button" class="row-select" data-row="' + esc(key) + '"' +
      (selected ? ' aria-current="true"' : '') + '>' +
      '<strong>' + esc(r.sku || '—') + '</strong><small>' +
      esc(r.customer || '归属待确认') + ' · ' + esc(r.physical_form || '—') + ' · ' +
      esc(r.uom || '—') + '</small>' +
      '<small class="sub-merged">期间 ' + periodShort(r) + '</small></button>' +
      '<span class="sel-tag">已选</span><span class="sheet-hint">查看详情</span></td>' +
      '<td data-label="期间" class="col-period"><span class="week">' + periodShort(r) + '</span></td>' +
      '<td data-label="建议">' + actionBadge(r) +
      (acts.length ? '<small class="hint" style="display:block">' + acts.join(' + ') + '</small>' : '') +
      '<small class="sub-merged">覆盖 ' + qty(r.coverage) + ' 天 · ' + flagsHtml(r) + '</small>' +
      '</td>' +
      '<td data-label="覆盖" class="col-coverage">' + qty(r.coverage) + ' 天</td>' +
      '<td data-label="原因" class="col-reason">' +
      (isBlank(r.reason) ? unknown() : esc(r.reason)) + '</td>' +
      '<td data-label="标记" class="col-flags">' + flagsHtml(r) + '</td></tr>';
  }

  function baseRowHtml(r) {
    var key = rowKey(r);
    var selected = key === state.baseKey;
    var proposed = proposals().filter(function (p) {
      return p.row_id === r.id && p.status === 'submitted';
    }).length;
    return '<tr data-key="' + esc(key) + '"' + (selected ? ' class="selected"' : '') + '>' +
      '<td data-label="商品"><button type="button" class="row-select" data-row="' + esc(key) + '"' +
      (selected ? ' aria-current="true"' : '') + '>' +
      '<strong>' + esc(r.name || r.sku || r.product_id || '—') + '</strong><small>' +
      esc(r.sku || '') + ' · ' + esc(r.physical_form || '—') + ' · ' + esc(unitOf(r)) +
      '</small><small class="sub-merged">期间 ' + periodShort(r) + '</small></button>' +
      '<span class="sel-tag">已选</span><span class="sheet-hint">查看详情</span></td>' +
      '<td data-label="期间" class="col-period"><span class="week">' + periodShort(r) + '</span></td>' +
      '<td data-label="需求基准"><span class="qty">' + qty(baselineQty(r)) + '</span>' +
      ' <span class="hint">' + esc(unitOf(r)) + '</span></td>' +
      '<td data-label="提案">' + (proposed
        ? '<span class="rec-badge decision">待模拟审核</span>' : '<span class="hint">—</span>') +
      '</td></tr>';
  }

  function focusedRowKey() {
    var el = document.activeElement;
    return el && el.getAttribute ? el.getAttribute('data-row') : null;
  }
  function findRowButton(key) {
    if (!key) return null;
    var tbody = byId('wb-rows');
    if (!tbody) return null;
    var btns = tbody.querySelectorAll('[data-row]');
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].getAttribute('data-row') === key) return btns[i];
    }
    return null;
  }

  function renderTable(opts) {
    opts = opts || {};
    var tbody = byId('wb-rows');
    var table = byId('wb-table');
    if (!tbody || !table) return;
    var scroller = byId('board-scroll');
    var top = scroller ? scroller.scrollTop : 0;
    var left = scroller ? scroller.scrollLeft : 0;
    var focusKey = opts.focusKey !== undefined ? opts.focusKey : focusedRowKey();
    var rows = filtered();
    var total = currentRows().length;
    table.setAttribute('data-table-set', state.set);
    var head = state.set === 'rec'
      ? '<tr><th>商品 / 客户 / 形态</th><th class="col-period">期间</th><th>建议</th>' +
        '<th class="col-coverage">覆盖</th><th class="col-reason">原因</th>' +
        '<th class="col-flags">标记</th></tr>'
      : '<tr><th>商品 / SKU</th><th class="col-period">期间</th><th>需求基准</th><th>提案</th></tr>';
    var thead = table.querySelector('thead');
    if (thead) thead.innerHTML = head;
    var colspan = state.set === 'rec' ? 6 : 4;
    if (!rows.length) {
      var hint = '没有匹配的行。';
      if (state.flags.supply && !REC.some(function (r) { return 'missing_supply' in r; })) {
        hint = '本次快照没有 missing_supply 字段，筛选结果 0 行（未知不等于缺供给，不补值）。';
      }
      tbody.innerHTML = '<tr><td colspan="' + colspan + '" class="empty">' + hint + '</td></tr>';
    } else {
      tbody.innerHTML = rows.map(state.set === 'rec' ? recRowHtml : baseRowHtml).join('');
    }
    bindRowHandlers(tbody);
    if (scroller) { scroller.scrollTop = top; scroller.scrollLeft = left; }
    var btn = findRowButton(focusKey);
    if (btn) { try { btn.focus({preventScroll: true}); } catch (e) { btn.focus(); } }
    var count = byId('wb-count');
    if (count) {
      count.textContent = '显示 ' + rows.length + ' / ' + total +
        (state.set === 'rec' ? ' 条补货建议' : ' 条需求基准');
    }
    var foot = byId('wb-foot');
    if (foot) {
      foot.textContent = state.set === 'rec'
        ? '补货建议只读，不可下单；与需求基准不相加。'
        : '需求基准是唯一允许填写演示提案的数据；建议行只读。';
    }
    var ver = byId('wb-version');
    if (ver) {
      ver.textContent = state.set === 'rec'
        ? '快照 ' + (REC_VERSION || '—') + ' · ' + AS_OF
        : '基准 ' + (BASE_VERSION || '—') + ' · ' + (BASEDOC.as_of || '—');
    }
  }

  function bindRowHandlers(tbody) {
    Array.prototype.forEach.call(tbody.querySelectorAll('[data-row]'), function (btn) {
      btn.addEventListener('click', function () { selectRow(btn.getAttribute('data-row')); });
    });
    Array.prototype.forEach.call(tbody.querySelectorAll('tr[data-key]'), function (tr) {
      tr.addEventListener('click', function (e) {
        if (e.target.closest && e.target.closest('[data-row]')) return;
        selectRow(tr.getAttribute('data-key'));
      });
    });
  }

  function applySelection() {
    var tbody = byId('wb-rows');
    if (!tbody) return;
    var key = currentKey();
    Array.prototype.forEach.call(tbody.querySelectorAll('tr[data-key]'), function (tr) {
      var on = tr.getAttribute('data-key') === key;
      tr.classList.toggle('selected', on);
      var btn = tr.querySelector('[data-row]');
      if (btn) {
        if (on) btn.setAttribute('aria-current', 'true');
        else btn.removeAttribute('aria-current');
      }
    });
  }

  // Selecting a row never routes, never rebuilds the list and never scrolls the
  // page: it only repaints the row + right column. The click target keeps focus.
  function selectRow(key, opts) {
    opts = opts || {};
    var prev = currentKey();
    if (prev === key) {
      if (mode === 'narrow' && !sheetOpen) openSheet();
      return;
    }
    setCurrentKey(key);
    state.outOfFilter = false;
    applySelection();
    renderDetail({scrollTop: true});
    saveUiState();
    var row = currentIndex()[key];
    announce('已选择：' + (row ? (row.sku || row.name || key) : key) +
      (mode === 'narrow' ? '，详情在底部抽屉' : '，详情在右侧'));
    if (mode === 'narrow') openSheet();
  }

  function nextRow(delta) {
    var rows = filtered();
    if (!rows.length) return;
    var cur = currentKey();
    var at = -1;
    for (var i = 0; i < rows.length; i++) { if (rowKey(rows[i]) === cur) { at = i; break; } }
    var next = rows[(at + delta + rows.length) % rows.length];
    if (!next) return;
    selectRow(rowKey(next));
    if (mode === 'wide') {
      var btn = findRowButton(rowKey(next));
      if (btn) { try { btn.focus({preventScroll: true}); } catch (e) { btn.focus(); } }
    }
  }

  // Drop a selection the current filter no longer contains. Keeps the memory
  // draft (it is keyed by row), but never leaves a submittable stale form.
  function reconcileSelection() {
    var key = currentKey();
    if (!key) { state.outOfFilter = false; applySelection(); return false; }
    var rows = filtered();
    var present = false;
    for (var i = 0; i < rows.length; i++) {
      if (rowKey(rows[i]) === key) { present = true; break; }
    }
    if (present) { state.outOfFilter = false; applySelection(); return false; }
    setCurrentKey(null);
    state.outOfFilter = true;
    applySelection();
    if (sheetOpen) { var d = byId('detail-sheet'); if (d && d.open) d.close(); }
    renderDetail({force: true});
    announce('所选行不在当前筛选中');
    return true;
  }

  /* ---------------- detail: summary / evidence / actions ---------------- */

  function matchKindFor(row) { return matchKind(REC_COUNT, BASE_COUNT, rowKey(row)); }

  function matchBadge(ctx) {
    if (ctx.kind === 'unique') return '<span class="rec-badge approved">唯一匹配</span>';
    if (ctx.kind === 'ambiguous') return '<span class="rec-badge warn">歧义</span>';
    if (ctx.kind === 'only_rec') return '<span class="rec-badge">仅建议</span>';
    if (ctx.kind === 'only_base') return '<span class="rec-badge">仅基准</span>';
    return '<span class="rec-badge">未匹配</span>';
  }

  function contextFor(row, set) {
    var key = rowKey(row);
    var kind = matchKindFor(row);
    var twin = null;
    if (kind === 'unique') {
      twin = set === 'rec' ? (BASE_INDEX[key] || null) : (REC_INDEX[key] || null);
    }
    return {row: row, set: set, key: key, kind: kind, twin: twin};
  }

  function foldKey(ctx, prefix, idx) {
    var id = ctx.row && (ctx.row.id || rowKey(ctx.row));
    return DATA_KEY + '|' + ctx.set + '|' + prefix + '|' + id + '|' + idx;
  }

  function kv(items) {
    return '<dl class="kv">' + items.map(function (it) {
      return '<div><dt>' + it[0] + '</dt><dd>' + it[1] + '</dd></div>';
    }).join('') + '</dl>';
  }

  function soTable(lines) {
    return '<table><thead><tr><th>SO</th><th>行</th><th>创建日</th><th>交付日</th>' +
      '<th>已交 / 未交</th><th>逾期</th><th>状态</th></tr></thead><tbody>' +
      lines.map(function (x) {
        return '<tr><td>' + esc(x.so) + '</td><td>' + esc(x.so_line) + '</td>' +
          '<td>' + esc(x.transaction_date || '未知') + '</td>' +
          '<td>' + esc(x.delivery_date || '未知') + '</td>' +
          '<td>' + intq(x.delivered) + ' / ' + intq(x.open_qty) + '</td>' +
          '<td>' + intq(x.overdue_days) + '</td><td>' + esc(x.status) + '</td></tr>';
      }).join('') + '</tbody></table>';
  }

  function soBucket(lines, bucket) {
    return lines.filter(function (x) { return (x.date_bucket || 'unknown') === bucket; });
  }

  function unknownNotes(ctx) {
    var r = ctx.row;
    var notes = [];
    if (ctx.set === 'rec') {
      var numeric = [
        ['c_qty', 'C 当前可发'], ['e_qty', 'E 按时供给'], ['forecast', '预测（中位 q50）'],
        ['q50', '需求 q50'], ['q90', '需求 q90'], ['q95', '需求 q95'],
        ['coverage', '源覆盖天数'], ['so_open_qty', 'SO 管线']
      ];
      numeric.forEach(function (pair) {
        if (isBlank(r[pair[0]])) notes.push(pair[0] + '（' + pair[1] + '）缺失＝未知，不补 0');
      });
      if (isBlank(r.period_start) && isBlank(r.period_end) && isBlank(r.week)) {
        notes.push('period_start / period_end 缺失＝期间待核（源快照未提供）');
      }
      if (isBlank(r.so_source_as_of)) notes.push('so_source_as_of 缺失＝SO 取数时点未记录');
      if (isBlank(r.source_hash)) notes.push('source_hash 缺失＝行哈希未记录（无伪链接）');
      if (isBlank(r.source_row)) notes.push('source_row 缺失＝源行号未记录');
      if (!Array.isArray(r.so_lines) || !r.so_lines.length) {
        notes.push('so_lines 为空＝未查到开放 SO 行（真实空集，不等于未知）');
      }
      notes.push('生产 / DN / 通途 PO＝未接入（不是 0）');
      var nf = DATA.nonfinite || {};
      var nfKeys = Object.keys(nf);
      if (nfKeys.length) {
        var total = 0;
        nfKeys.forEach(function (k) { total += Number(nf[k]) || 0; });
        notes.push('源快照有 ' + total + ' 个非有限数（NaN/Inf：' + nfKeys.join('、') +
          '），已按未知展示，不补 0');
      }
    } else {
      if (isBlank(baselineQty(r))) notes.push('需求基准数量缺失＝未知，不补 0');
      if (!ctx.twin) {
        notes.push('未关联到唯一补货建议行：供给阶段 / SO / 库存 / 来源不可用，不套用其他行证据');
      }
      if (isBlank(r.period_start) && isBlank(r.period_end) && isBlank(r.week)) {
        notes.push('期间字段缺失＝待核（源基准未提供）');
      }
    }
    notes.push('当前库存观察＝静态页不可得（connect-src none，无实时请求）');
    return notes;
  }

  function warnSummary(ctx) {
    var notes = unknownNotes(ctx);
    return '<div class="ev-warn"><b>缺失与未知（' + notes.length + ' 项，不补 0）</b><ul>' +
      notes.map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('') +
      '</ul></div>';
  }

  function layer(ctx, prefix, idx, title, keyHtml, bodyHtml) {
    var fk = foldKey(ctx, prefix, idx);
    var open = foldState[fk] ? ' open' : '';
    return '<details class="lay" data-fold-key="' + esc(fk) + '"' + open + '>' +
      '<summary><b>' + title + '</b> ' + keyHtml + '</summary>' +
      '<div class="lay-body">' + bodyHtml + '</div></details>';
  }

  function identityKey(ctx) {
    var r = ctx.row;
    return '形态 ' + esc(r.physical_form || '—') + ' · 单位 ' + esc(unitOf(r) || '—') +
      ' · ' + matchBadge(ctx);
  }

  function identityFull(ctx) {
    var r = ctx.row;
    var items = [
      ['SKU', esc(r.sku || '—')],
      ['客户 / 归属', esc(r.customer || r.branch || (ctx.set === 'rec' ? '归属待确认' : '—'))],
      ['形态 / 单位', esc(r.physical_form || '—') + ' · ' + esc(unitOf(r) || '—')],
      ['套件标识 bundle_id', esc(r.bundle_id || '—')],
      ['规范化行键', esc(ctx.key)],
      ['匹配状态', matchBadge(ctx) + (ctx.kind === 'unique' ? ' 同键唯一' :
        ctx.kind === 'ambiguous' ? ' 同键多行，不取第一条' : ' 只有本侧行')]
    ];
    return kv(items);
  }

  function periodKey(ctx) {
    return periodText(ctx.row) + ' · 快照 ' + esc(AS_OF);
  }

  function periodFull(ctx) {
    var r = ctx.row;
    return kv([
      ['期间起 week / period_start', esc(day(r.week || r.start || r.period_start) || '待核')],
      ['期间止 period_end', esc(day(r.period_end) || '待核')],
      ['快照时点 as_of', esc(AS_OF)],
      ['基准时点', esc(BASEDOC.as_of || '—')],
      ['待核说明', '空日期写「待核」，不编造']
    ]);
  }

  function demandKey(ctx) {
    var r = ctx.row;
    if (ctx.set === 'base') {
      return '基准 <strong>' + qty(baselineQty(r)) + '</strong> ' + esc(unitOf(r));
    }
    return '预测 q50 <strong>' + qty(r.forecast) + '</strong> ' + esc(unitOf(r)) +
      ' · q50/q90/q95 ' + intq(r.q50) + '/' + intq(r.q90) + '/' + intq(r.q95);
  }

  function demandFull(ctx) {
    var r = ctx.row;
    if (ctx.set === 'base') {
      var prov = isBlank(r.baseline_qty) && !isBlank(r.demand_qty)
        ? '字段 demand_qty（本次基准导出未含 baseline_qty）' : '字段 baseline_qty';
      var items = [
        ['需求基准数量', qty(baselineQty(r)) + ' ' + esc(unitOf(r))],
        ['字段来源', prov]
      ];
      if (ctx.twin) {
        items.push(['关联建议预测中位', qty(ctx.twin.forecast) + ' ' + esc(unitOf(ctx.twin))]);
      } else {
        items.push(['关联建议预测', unknown() + '（未关联）']);
      }
      return kv(items);
    }
    return kv([
      ['预测中位 forecast', qty(r.forecast) + ' ' + esc(unitOf(r))],
      ['q50 / q90 / q95', intq(r.q50) + ' / ' + intq(r.q90) + ' / ' + intq(r.q95)],
      ['模型', esc(r.model || '—')],
      ['字段来源', 'forecast, q50, q90, q95, model']
    ]);
  }

  function supplyKey(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<span class="unknown">未关联</span>';
    return 'C <strong>' + qty(r.c_qty) + '</strong> · E <strong>' + qty(r.e_qty) + '</strong>' +
      (ctx.set === 'base' ? '（关联建议）' : '');
  }

  function supplyFull(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<p class="mutednote">未关联到唯一补货建议行，本层不可用；不借用其他行。</p>';
    return kv([
      ['C 当前可发 c_qty', qty(r.c_qty)],
      ['E 按时供给 e_qty', qty(r.e_qty)],
      ['EN 已发运量', intq(valueOfExtra(r, 'EN已发运量'))],
      ['EN 待发量', intq(valueOfExtra(r, 'EN待发量'))],
      ['PO 追加（去重）', intq(valueOfExtra(r, 'PO追加(去重)'))],
      ['SO 已下', intq(valueOfExtra(r, 'SO已下'))],
      ['CG 抵扣', intq(valueOfExtra(r, 'CG可调拨抵扣'))],
      ['生产 / DN / 通途 PO', '未接入 / 未接入 / 未接入']
    ]) +
      '<p class="mutednote">C 与 E 字段各自带口径；SO 管线不加入建议量，PO 与 SO 不能相加替代。</p>';
  }

  function soLinesFor(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    return r && Array.isArray(r.so_lines) ? r.so_lines : [];
  }

  function soKey(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<span class="unknown">未关联</span>';
    var lines = soLinesFor(ctx);
    return '合计 <strong>' + intq(r.so_open_qty) + '</strong> · 近期 ' + intq(r.so_recent_open_qty) +
      ' · 历史 ' + intq(r.so_history_open_qty) +
      (lines.length ? ' · 明细 ' + lines.length + ' 行（默认折叠）' : ' · 未查到开放 SO 行');
  }

  function soFull(ctx, prefix) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<p class="mutednote">未关联到唯一补货建议行，本层不可用。</p>';
    var lines = soLinesFor(ctx);
    var html = kv([
      ['SO 管线合计', intq(r.so_open_qty)],
      ['近期 SO', intq(r.so_recent_open_qty)],
      ['历史开放 SO', intq(r.so_history_open_qty)],
      ['SO 取数时点', esc(r.so_source_as_of || '未记录')]
    ]);
    if (!lines.length) {
      html += '<p class="mutednote">未查到开放 SO 行（空集，不是未知）。</p>';
      return html;
    }
    [['recent', '近期 SO'], ['history', '历史开放 SO'], ['unknown', '创建日未知 SO']]
      .forEach(function (pair) {
        var items = soBucket(lines, pair[0]);
        if (!items.length) return;
        html += '<details class="raw"><summary>' + pair[1] + '（' + items.length +
          ' 行，不加入建议量）</summary>' + soTable(items) + '</details>';
      });
    return html;
  }

  function stockKey(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<span class="unknown">未关联</span>';
    return '快照 C <strong>' + qty(r.c_qty) + '</strong>（' + esc(AS_OF) + '）· 当前观察不可得';
  }

  function stockFull(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<p class="mutednote">未关联到唯一补货建议行，本层不可用。</p>';
    return kv([
      ['快照 C（时点 ' + esc(AS_OF) + '）', qty(r.c_qty)],
      ['快照 E', qty(r.e_qty)],
      ['当前库存观察', '静态页不可得'],
      ['可用性拆开说', '服务=静态 / 库存=快照 / 建议=只读']
    ]);
  }

  function sourceKey(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<span class="unknown">未关联</span>';
    return '文件 ' + esc(DATA.version || '—') + ' · 哈希 ' +
      esc(r.source_hash ? String(r.source_hash).slice(0, 16) : '未记录');
  }

  function sourceFull(ctx) {
    var r = ctx.set === 'rec' ? ctx.row : ctx.twin;
    if (!r) return '<p class="mutednote">未关联到唯一补货建议行，本层不可用。</p>';
    return kv([
      ['source_row', esc(r.source_row || '未记录')],
      ['source_hash', esc(r.source_hash || '未记录')],
      ['数据来源文件', esc(DATA.version || '—')],
      ['来源备注', esc(r.source_note || '未记录')]
    ]) +
      '<p class="mutednote">文件不存在 / 无权 / 未记录行号各有状态；本快照未写入行哈希，不生成伪链接。</p>';
  }

  function reconFold(ctx, prefix) {
    var idx = ctx.set === 'rec'
      ? REC.findIndex(function (x) { return rowKey(x) === ctx.key; })
      : BASE.findIndex(function (x) { return rowKey(x) === ctx.key; });
    var total = ctx.set === 'rec' ? REC.length : BASE.length;
    var twinLabel = ctx.twin
      ? esc(ctx.twin.id || rowKey(ctx.twin))
      : (ctx.kind === 'ambiguous' ? '同键多行（歧义），不取第一条' : '未匹配');
    return '<details class="lay" data-fold-key="' + esc(foldKey(ctx, prefix, 7)) + '">' +
      '<summary><b>对单与抽查</b> <span class="hint">唯一匹配 ' + (RECON.unique || 0) +
      ' · 仅建议 ' + ((RECON.only_rec || []).length) + ' · 仅基准 ' +
      ((RECON.only_base || []).length) + ' · 歧义 ' + ((RECON.ambiguous || []).length) +
      '</span></summary><div class="lay-body">' +
      kv([
        [ctx.set === 'rec' ? '建议行号' : '基准行号', (idx + 1) + ' / ' + total],
        ['关联' + (ctx.set === 'rec' ? '需求基准' : '补货建议'), twinLabel],
        ['对单键', 'SKU × 形态 × 单位'],
        ['整体对账', '唯一匹配 ' + (RECON.unique || 0) + ' · 仅建议 ' +
          ((RECON.only_rec || []).length) + ' · 仅基准 ' +
          ((RECON.only_base || []).length) + ' · 歧义 ' + ((RECON.ambiguous || []).length)]
      ]) +
      '<label class="check" style="margin-top:8px"><input type="checkbox" id="' + prefix +
      '-check"> 本次查看已核对（不持久化、不代表已批准）</label>' +
      '</div></details>';
  }

  // Side-effect free: the same markup feeds the in-detail evidence block and the
  // cross-row audit view (different id prefixes keep ids unique).
  function evidenceSections(ctx, prefix) {
    return '<h3>证据链（七层，本行）</h3>' +
      warnSummary(ctx) +
      layer(ctx, prefix, 0, '① 身份', identityKey(ctx), identityFull(ctx)) +
      layer(ctx, prefix, 1, '② 期间', periodKey(ctx), periodFull(ctx)) +
      layer(ctx, prefix, 2, '③ 需求', demandKey(ctx), demandFull(ctx)) +
      layer(ctx, prefix, 3, '④ 供给阶段', supplyKey(ctx), supplyFull(ctx)) +
      layer(ctx, prefix, 4, '⑤ SO 三段', soKey(ctx), soFull(ctx, prefix)) +
      layer(ctx, prefix, 5, '⑥ 库存', stockKey(ctx), stockFull(ctx)) +
      layer(ctx, prefix, 6, '⑦ 来源哈希', sourceKey(ctx), sourceFull(ctx)) +
      reconFold(ctx, prefix);
  }

  function detailHeader(ctx) {
    var r = ctx.row;
    var title = ctx.set === 'rec'
      ? (r.sku || '—')
      : (r.name || r.sku || r.product_id || '—');
    var kicker = ctx.set === 'rec'
      ? '补货建议 · 只读' + (r.customer ? ' / ' + esc(r.customer) : '')
      : '需求基准 · 可填写演示提案' + (r.branch ? ' / ' + esc(r.branch) : '');
    var ident = ctx.set === 'rec'
      ? esc(r.physical_form || '—') + ' · ' + esc(unitOf(r) || '—') + ' · 期间 ' + periodShort(r)
      : esc(r.sku || '') + ' · ' + esc(r.physical_form || '—') + ' · ' + esc(unitOf(r) || '—') +
        ' · 期间 ' + periodShort(r);
    return '<div class="detail-head">' +
      '<div class="micro">' + kicker + '</div>' +
      '<h2 id="detail-title" tabindex="-1">' + esc(title) + '</h2>' +
      '<p class="hint">' + ident + '</p>' +
      '<div class="detail-anchors" role="group" aria-label="详情内定位">' +
      '<button type="button" data-anchor="detail-summary">摘要</button>' +
      '<button type="button" data-anchor="detail-evidence">证据</button>' +
      '<button type="button" data-anchor="detail-actions">运营判断</button>' +
      '</div></div>';
  }

  function tile(label, value, note) {
    return '<div><span class="micro">' + label + '</span><strong>' + value + '</strong>' +
      '<small>' + note + '</small></div>';
  }

  function recSummaryHtml(r) {
    var demandKnown = !isBlank(r.forecast);
    var supplyKnown = !isBlank(r.e_qty);
    var acts = actionParts(r);
    var concl = [];
    if (!demandKnown && !supplyKnown) concl.push('缺证据，暂不能确定缺口');
    else concl.push(actionBadge(r) + (acts.length ? '（' + acts.join(' + ') + '）' : ''));
    if (!isBlank(r.reason)) concl.push(esc(r.reason));
    if (flag(r, 'needs_decision')) concl.push('需人工拍板');
    if (flag(r, 'low_confidence')) concl.push('源模型标记低置信');
    if (flag(r, 'ownership_pending')) concl.push('归属待确认');
    return '<p class="l0">' + concl.join('；') + '。</p>' +
      '<div class="l1">' +
      tile('需求（预测中位 q50）', qty(r.forecast),
        esc(unitOf(r)) + ' · q50/q90/q95 ' + intq(r.q50) + '/' + intq(r.q90) + '/' + intq(r.q95)) +
      tile('供给（E 按时供给，含 C）', qty(r.e_qty),
        'C 当前可发 ' + qty(r.c_qty) + ' · 不含在途') +
      tile('差额（供给 − 需求，页面计算）',
        gapText(demandKnown, supplyKnown, r.forecast, r.e_qty, unitOf(r)),
        '只作对照，不是补货量') +
      '</div>' +
      '<div class="note">库存快照：C ' + qty(r.c_qty) + '（快照时点 ' + esc(AS_OF) +
      '）；当前观察：静态页不可得（页面不发起任何请求）。两者分开标注，不用旧值冒充实时。</div>' +
      '<div class="actions">' +
      '<button type="button" class="btn small" data-expand-evidence="1">展开证据明细</button>' +
      '<button type="button" class="btn small ghost" data-goto-audit="1">跨行审计视图 →</button>' +
      '<button type="button" class="btn small ghost" data-next-row="1">下一条</button>' +
      '</div>';
  }

  function gapText(demandKnown, supplyKnown, demand, supply, unit) {
    if (!demandKnown || !supplyKnown) return unknown();
    return intq(Number(supply) - Number(demand)) + (unit ? ' ' + esc(unit) : '');
  }

  function baseSummaryHtml(r) {
    var demand = baselineQty(r);
    var demandKnown = !isBlank(demand);
    var twin = REC_INDEX[rowKey(r)] || null;
    var supplyKnown = !!(twin && !isBlank(twin.e_qty));
    var unit = unitOf(r);
    return '<p class="l0">本期需求基准 ' +
      (demandKnown ? qty(demand) + ' ' + esc(unit) : '缺证据，暂不能确定') + '；' +
      (supplyKnown ? '对应建议行 E 按时供给 ' + qty(twin.e_qty) : '未关联到建议行，供给未知') +
      '。</p>' +
      '<div class="l1">' +
      tile('需求（需求基准）', qty(demand), esc(unit) +
        ' · ' + (isBlank(r.baseline_qty) && !isBlank(r.demand_qty) ? '字段 demand_qty' : '字段 baseline_qty')) +
      tile('供给（关联建议行 E）', supplyKnown ? qty(twin.e_qty) : unknown(),
        twin ? '同键建议行 ' + esc(twin.sku || '') : '未匹配建议行') +
      tile('差额（供给 − 需求，页面计算）',
        gapText(demandKnown, supplyKnown, demand, twin ? twin.e_qty : null, unit),
        '只作对照，不是补货量') +
      '</div>' +
      '<div class="note">期间：' + periodShort(r) + '。库存快照：C ' +
      (twin ? qty(twin.c_qty) : unknown()) + '（快照时点 ' + esc(AS_OF) +
      '）；当前观察：静态页不可得。空日期写「待核」，不编造。</div>' +
      '<div class="actions">' +
      '<button type="button" class="btn small" data-expand-evidence="1">展开证据明细</button>' +
      '<button type="button" class="btn small ghost" data-goto-audit="1">跨行审计视图 →</button>' +
      '<button type="button" class="btn small ghost" data-next-row="1">下一条</button>' +
      '</div>';
  }

  function recActionsHtml(r, kind, twin) {
    var key = rowKey(r);
    var html = '<h3>运营举措 / 判断</h3>' +
      '<p class="readonly-reason">补货建议本身只读：本页没有下单、催单或审批入口；' +
      '建议数量与口径不被页面改写。</p>';
    if (kind === 'unique' && twin) {
      html += '<p class="target-note">表单目标基准：<b>' +
        esc(twin.name || twin.sku || twin.id) + '</b> · 期间 ' + periodShort(twin) +
        ' · 基准版本 ' + esc(BASE_VERSION || '—') + '</p>';
      if (state.activated[key] === String(twin.id || key)) {
        html += proposalBlock(twin);
        html += '<p class="form-note hint">表单写的是上面这条需求基准；左侧仍选中原补货建议，' +
          '不改变建议本体。</p>';
        html += '<div class="actions"><button type="button" class="btn small ghost" ' +
          'data-cancel-activate="1">收起表单</button></div>';
      } else {
        html += '<div class="actions"><button type="button" class="btn small accent" ' +
          'data-activate="1">对关联基准填写演示判断</button></div>';
        html += '<p class="hint">点击后在原地激活这条基准的表单；建议行保持只读。</p>';
      }
    } else if (kind === 'ambiguous') {
      html += '<p class="readonly-reason warn">同键存在多条基准行（歧义），不自动取第一条；' +
        '请到「需求基准」里明确选择后再填。</p>' +
        '<div class="actions"><button type="button" class="btn small" disabled>' +
        '对关联基准填写演示判断</button></div>';
    } else {
      html += '<p class="readonly-reason">未匹配到唯一需求基准行（仅建议），无法在本页填写提案；' +
        '不按 SKU 猜配。</p>' +
        '<div class="actions"><button type="button" class="btn small" disabled>' +
        '对关联基准填写演示判断</button></div>';
    }
    return html;
  }

  function baseActionsHtml(r, kind, twinRec) {
    var html = '<h3>运营举措 / 判断</h3>';
    if (kind === 'unique' && twinRec) {
      html += '<p class="target-note">唯一关联建议：<b>' + esc(twinRec.sku || '') + '</b> · ' +
        esc(twinRec.action || '观察') + ' · 期间 ' + periodShort(twinRec) + '</p>';
    } else {
      html += '<p class="readonly-reason">没有唯一匹配的补货建议行；仍可填写演示提案。</p>';
    }
    html += '<p class="readonly-reason">需求基准是唯一允许填写演示提案的一方；' +
      '提案只存本浏览器，不上传、不审批、不写 EN。</p>';
    html += proposalBlock(r);
    html += '<p class="form-note hint">仅演示需求提案，不修改 USNJ 补货建议，不进入采购。</p>';
    return html;
  }

  function proposalBlock(r) {
    return proposalForm(r, unitOf(r), day(r.week || r.start || r.period_start));
  }

  function proposalForm(r, unit, start) {
    var d = draftFor(r);
    var selectedKind = d['wb-kind'] || KINDS[0];
    var opts = KINDS.map(function (kind) {
      return '<option value="' + kind + '"' +
        (kind === selectedKind ? ' selected' : '') + '>' + KIND_LABELS[kind] + '</option>';
    }).join('');
    var field = function (k, fallback) {
      return d[k] !== undefined ? esc(d[k]) : esc(fallback);
    };
    var end = d['wb-end'] !== undefined ? d['wb-end'] : (day(r.period_end) || '');
    return '<form id="proposal-form" novalidate>' +
      '<h3 class="form-title">补充你的业务判断</h3>' +
      '<label for="wb-kind">调整方式</label><select id="wb-kind">' + opts + '</select>' +
      '<label for="wb-value" id="wb-value-label">调整数量（可为负数）</label>' +
      '<input id="wb-value" type="number" step="any" placeholder="例如 20 或 -10" value="' +
      field('wb-value', '') + '">' +
      '<div class="hint" id="wb-preview"></div>' +
      '<div class="two">' +
      '<div><label for="wb-start">事件开始</label><input id="wb-start" type="date" value="' +
      field('wb-start', start) + '"></div>' +
      '<div><label for="wb-end">事件结束</label><input id="wb-end" type="date" value="' +
      esc(end) + '"></div></div>' +
      '<div class="hint">按该预测期提交；日期空着表示「待核」，提交前需填写。</div>' +
      '<label for="wb-event-id">业务事件 ID <span class="req">*</span></label>' +
      '<input id="wb-event-id" placeholder="例如 活动-2026双十一-上海" value="' +
      field('wb-event-id', '') + '">' +
      '<label for="wb-reason">调整原因 <span class="req">*</span></label>' +
      '<textarea id="wb-reason" placeholder="说明活动、渠道变化或异常，以及数量判断依据">' +
      (d['wb-reason'] !== undefined ? esc(d['wb-reason']) : '') + '</textarea>' +
      '<label for="wb-evidence">证据或补充说明</label>' +
      '<input id="wb-evidence" placeholder="活动编号或可核对的信息" value="' +
      field('wb-evidence', '') + '">' +
      '<p class="hint draft-note">' + (hasDraft(r)
        ? '已恢复本页内未保存输入（刷新后仍会丢失）。'
        : '未保存输入刷新后丢失（本页内切行不丢）。') + '</p>' +
      '<p class="form-message" id="form-message" aria-live="polite"></p>' +
      '<div class="submitline"><span class="hint">仅写入本浏览器，不上传、不审批、不写 EN。</span>' +
      '<button class="btn accent" id="wb-submit" type="submit">保存演示提案（本浏览器）</button></div>' +
      '</form>';
  }

  function draftKeyFor(r) { return DATA_KEY + '|' + (r && (r.id || rowKey(r)) || '-'); }
  function draftFor(r) { return drafts[draftKeyFor(r)] || {}; }
  function hasDraft(r) {
    var d = draftFor(r);
    return Object.keys(d).some(function (k) {
      return k !== 'wb-kind' && d[k] !== '' && d[k] !== null && d[k] !== undefined;
    });
  }
  function saveDraft(r) {
    var out = {};
    ['wb-kind', 'wb-value', 'wb-start', 'wb-end', 'wb-event-id', 'wb-reason', 'wb-evidence']
      .forEach(function (id) { var el = byId(id); if (el) out[id] = el.value; });
    drafts[draftKeyFor(r)] = out;
  }
  function clearDraft(r) { delete drafts[draftKeyFor(r)]; }

  function formTarget() {
    if (state.set === 'base') return BASE_INDEX[state.baseKey] || null;
    var r = REC_INDEX[state.recKey];
    if (!r) return null;
    var key = rowKey(r);
    if (state.activated[key] && matchKindFor(r) === 'unique') return BASE_INDEX[key] || null;
    return null;
  }

  function bindProposalForm(r) {
    var form = byId('proposal-form');
    if (!form) return;
    byId('wb-kind').addEventListener('change', function () { updatePreview(r); saveDraft(r); });
    byId('wb-value').addEventListener('input', function () { updatePreview(r); saveDraft(r); });
    ['wb-start', 'wb-end', 'wb-event-id', 'wb-reason', 'wb-evidence'].forEach(function (id) {
      var el = byId(id);
      if (el) el.addEventListener('input', function () { saveDraft(r); });
    });
    form.addEventListener('submit', function (event) { submitProposal(event, r); });
    updatePreview(r);
    if (!storageState.available) {
      setFormEnabled(false);
      message(storageState.message, true);
    }
  }

  function updatePreview(r) {
    var kindEl = byId('wb-kind'), valueEl = byId('wb-value'), labelEl = byId('wb-value-label');
    if (!kindEl || !valueEl || !labelEl) return;
    var kind = kindEl.value;
    var base = Number(baselineQty(r));
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
    var formatted = formatQty(baselineQty(r));
    if (valueEl.value === '' || !isFinite(Number(valueEl.value)) || formatted === null) {
      preview.textContent = formatted === null
        ? '基准数量未知，保存后仍只存本浏览器；未知不补 0。'
        : '保存后仅在本浏览器可见，待本地审核视角确认。';
      return;
    }
    var value = Number(valueEl.value);
    var total = kind === 'total' ? value : kind === 'percent' ? base * (1 + value / 100) : base + value;
    preview.textContent = '本条提案预览：' + formatted + ' → ' +
      Number(total).toLocaleString('zh-CN', {maximumFractionDigits: 2}) + ' ' +
      unitOf(r) + '（未包含其他提案）';
  }

  function setFormEnabled(enabled) {
    var form = byId('proposal-form');
    if (!form) return;
    Array.prototype.forEach.call(
      form.querySelectorAll('input, select, textarea, button'),
      function (el) { el.disabled = !enabled; }
    );
  }

  function message(text, isError) {
    // The fold's message hides when the fold is collapsed, so the inline copy
    // in the detail pane carries validation errors where the user can see them.
    ['collab-message', 'form-message'].forEach(function (id) {
      var el = byId(id);
      if (!el) return;
      el.textContent = text || '';
      el.className = isError ? 'form-message error' : 'form-message';
    });
  }

  function detailScroller() {
    return sheetOpen ? byId('sheet-scroll') : byId('detail-content');
  }

  function scrollDetailTo(id) {
    var sc = detailScroller(), el = byId(id);
    if (!sc || !el) return;
    var head = sc.querySelector ? sc.querySelector('.detail-head') : null;
    var offset = head ? head.getBoundingClientRect().height : 0;
    var delta = el.getBoundingClientRect().top - sc.getBoundingClientRect().top - offset - 6;
    sc.scrollTop = Math.max(0, sc.scrollTop + delta);
    try { el.focus({preventScroll: true}); } catch (e) { el.focus(); }
  }

  function saveFold(el) {
    var k = el.getAttribute('data-fold-key');
    if (k) foldState[k] = el.open ? 1 : 0;
  }
  function bindFolds(host) {
    Array.prototype.forEach.call(host.querySelectorAll('details[data-fold-key]'), function (d) {
      d.addEventListener('toggle', function () { saveFold(d); });
    });
  }
  function expandEvidence(host) {
    var scope = host.querySelector('#detail-evidence') || host;
    Array.prototype.forEach.call(scope.querySelectorAll('details.lay'), function (d) {
      d.open = true;
      saveFold(d);
    });
    scrollDetailTo('detail-evidence');
  }

  function activateLinked() {
    var r = REC_INDEX[state.recKey];
    if (!r) return;
    var key = rowKey(r);
    if (matchKindFor(r) !== 'unique') return;
    var twin = BASE_INDEX[key];
    if (!twin) return;
    state.activated[key] = String(twin.id || key);
    renderDetail({force: true});
    var kind = byId('wb-kind');
    if (kind) { try { kind.focus(); } catch (e) {} }
    announce('已激活关联基准的演示表单；左侧仍选中原补货建议');
  }

  function cancelActivated() {
    var r = REC_INDEX[state.recKey];
    if (!r) return;
    delete state.activated[rowKey(r)];
    renderDetail({force: true});
    var btn = document.querySelector('[data-activate]');
    if (btn) { try { btn.focus(); } catch (e) {} }
  }

  function bindDetailHost(host) {
    bindFolds(host);
    Array.prototype.forEach.call(host.querySelectorAll('[data-anchor]'), function (b) {
      b.addEventListener('click', function () { scrollDetailTo(b.getAttribute('data-anchor')); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-expand-evidence]'), function (b) {
      b.addEventListener('click', function () { expandEvidence(host); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-goto-audit]'), function (b) {
      b.addEventListener('click', function () {
        if (state.set === 'rec' && state.recKey) state.evKey = state.recKey;
        setView('evidence');
      });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-next-row]'), function (b) {
      b.addEventListener('click', function () { nextRow(1); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-activate]'), function (b) {
      b.addEventListener('click', function () { activateLinked(); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-cancel-activate]'), function (b) {
      b.addEventListener('click', function () { cancelActivated(); });
    });
    if (host.querySelector('#proposal-form')) {
      var target = formTarget();
      if (target) bindProposalForm(target);
    }
  }

  function emptyDetailHtml() {
    if (state.outOfFilter) {
      return '<div class="empty">所选行不在当前筛选中。<br>清除筛选或重新选择一行后再操作。</div>';
    }
    return '<div class="empty">选择左侧一行查看结论、证据和可用操作。<br>' +
      '补货建议只读；唯一关联到需求基准时可在本栏填写演示判断。</div>';
  }

  function recDetailHtml(r) {
    var ctx = contextFor(r, 'rec');
    return detailHeader(ctx) + '<div class="detail-body">' +
      '<section id="detail-summary" class="dsec" tabindex="-1">' + recSummaryHtml(r) + '</section>' +
      '<section id="detail-evidence" class="dsec" tabindex="-1">' +
      evidenceSections(ctx, 'd') + '</section>' +
      '<section id="detail-actions" class="dsec" tabindex="-1">' +
      recActionsHtml(r, ctx.kind, ctx.twin) + '</section></div>';
  }

  function baseDetailHtml(r) {
    var ctx = contextFor(r, 'base');
    return detailHeader(ctx) + '<div class="detail-body">' +
      '<section id="detail-summary" class="dsec" tabindex="-1">' + baseSummaryHtml(r) + '</section>' +
      '<section id="detail-evidence" class="dsec" tabindex="-1">' +
      evidenceSections(ctx, 'd') + '</section>' +
      '<section id="detail-actions" class="dsec" tabindex="-1">' +
      baseActionsHtml(r, ctx.kind, ctx.twin) + '</section></div>';
  }

  function renderDetail(opts) {
    opts = opts || {};
    var host = byId('detail-content');
    if (!host) return;
    var key = currentKey();
    var sig = state.set + '|' + (key || '') + '|' +
      (state.set === 'rec' && key ? (state.activated[key] || '') : '');
    if (!opts.force && key && host.getAttribute('data-sig') === sig) {
      if (opts.scrollTop) { var sc = detailScroller(); if (sc) sc.scrollTop = 0; }
      return;
    }
    var row = key ? currentIndex()[key] : null;
    if (!row) host.innerHTML = emptyDetailHtml();
    else if (state.set === 'rec') host.innerHTML = recDetailHtml(row);
    else host.innerHTML = baseDetailHtml(row);
    host.setAttribute('data-sig', sig);
    bindDetailHost(host);
    if (opts.scrollTop) { var top = detailScroller(); if (top) top.scrollTop = 0; }
  }

  /* ---------------- narrow sheet + container mode ---------------- */

  function finishSheet() {
    if (!sheetOpen) return;
    sheetOpen = false;
    var content = byId('detail-content'), slot = byId('detail-slot');
    if (content && slot) slot.appendChild(content);
    if (sheetRestore && sheetRestore.htmlOverflow !== undefined) {
      document.documentElement.style.overflow = sheetRestore.htmlOverflow;
    }
    var focusKey = sheetRestore ? sheetRestore.focusKey : null;
    sheetRestore = null;
    var btn = findRowButton(focusKey);
    if (btn) { try { btn.focus({preventScroll: true}); } catch (e) { btn.focus(); } }
    else { var s = byId('wb-search'); if (s) { try { s.focus({preventScroll: true}); } catch (e) {} } }
    announce('详情已关闭，列表保持原位');
  }

  function openSheet() {
    var dlg = byId('detail-sheet');
    var content = byId('detail-content');
    var sc = byId('sheet-scroll');
    if (!dlg || !content || !sc || sheetOpen || !currentKey()) return;
    if (typeof dlg.showModal !== 'function') return;
    sheetRestore = {
      focusKey: currentKey(),
      htmlOverflow: document.documentElement.style.overflow
    };
    sc.appendChild(content);
    document.documentElement.style.overflow = 'hidden';
    dlg.showModal();
    sheetOpen = true;
    var title = byId('detail-title');
    if (title) { try { title.focus({preventScroll: true}); } catch (e) { title.focus(); } }
  }

  function bindSheet() {
    var dlg = byId('detail-sheet');
    if (!dlg) return;
    var close = byId('sheet-close');
    if (close) close.addEventListener('click', function () { dlg.close(); });
    dlg.addEventListener('close', finishSheet);
    var handle = byId('sheet-handle');
    if (handle) {
      var startY = null, dy = 0;
      handle.addEventListener('pointerdown', function (e) {
        startY = e.clientY; dy = 0;
        try { handle.setPointerCapture(e.pointerId); } catch (err) {}
      });
      handle.addEventListener('pointermove', function (e) {
        if (startY === null) return;
        dy = Math.max(0, e.clientY - startY);
      });
      handle.addEventListener('pointerup', function () {
        if (startY === null) return;
        var shouldClose = dy > 64;
        startY = null;
        if (shouldClose) dlg.close();
      });
      handle.addEventListener('pointercancel', function () { startY = null; });
    }
  }

  function measureWorkspace() {
    var shell = byId('workbench-shell');
    if (!shell) return;
    var stack = document.querySelector('.topstack');
    var stackH = stack ? stack.getBoundingClientRect().height : 0;
    var vh = (window.visualViewport && window.visualViewport.height) || window.innerHeight || 0;
    if (!vh) return;
    var h = Math.max(240, Math.round(vh - stackH - 56));
    shell.style.setProperty('--ws-h', h + 'px');
    document.documentElement.style.setProperty('--stack-h', Math.round(stackH) + 'px');
  }

  function measureShell() {
    var shell = byId('workbench-shell');
    if (!shell) return;
    measureWorkspace();
    var next = shell.clientWidth <= 720 ? 'narrow' : 'wide';
    if (next === mode) return;
    mode = next;
    shell.classList.toggle('mode-narrow', next === 'narrow');
    shell.classList.toggle('mode-wide', next === 'wide');
    if (next === 'wide' && sheetOpen) {
      var dlg = byId('detail-sheet');
      if (dlg && dlg.open) dlg.close();
    }
  }

  function observeLayout() {
    var shell = byId('workbench-shell');
    if (shell && typeof ResizeObserver === 'function') {
      try { new ResizeObserver(function () { measureShell(); }).observe(shell); } catch (e) {}
    }
    window.addEventListener('resize', measureShell);
    if (window.visualViewport) window.visualViewport.addEventListener('resize', measureShell);
  }

  /* ---------------- session UI state (not drafts, not proposals) ---------------- */

  function uiKey() { return UI_KEY_PREFIX + ':' + DATA_KEY; }

  function saveUiState() {
    try {
      sessionStorage.setItem(uiKey(), JSON.stringify({
        set: state.set, recKey: state.recKey, baseKey: state.baseKey,
        q: state.q, action: state.action, flags: state.flags,
        y: (window.scrollY || window.pageYOffset || 0)
      }));
    } catch (e) { /* optional: read-only browsing must keep working */ }
  }

  function restoreUiState() {
    var raw;
    try { raw = sessionStorage.getItem(uiKey()); } catch (e) { return false; }
    if (!raw) return false;
    var saved;
    try { saved = JSON.parse(raw); } catch (e) { return false; }
    if (!saved || typeof saved !== 'object') return false;
    if (saved.set === 'base' || saved.set === 'rec') state.set = saved.set;
    state.q = typeof saved.q === 'string' ? saved.q : '';
    state.action = typeof saved.action === 'string' ? saved.action : '';
    if (saved.flags && typeof saved.flags === 'object') {
      Object.keys(state.flags).forEach(function (k) { state.flags[k] = !!saved.flags[k]; });
    }
    var search = byId('wb-search');
    if (search) search.value = state.q;
    var actionSel = byId('wb-action');
    if (actionSel) actionSel.value = state.action;
    Object.keys(state.flags).forEach(function (k) {
      var cb = document.querySelector('[data-flag="' + k + '"]');
      if (cb) cb.checked = state.flags[k];
    });
    var recKey = typeof saved.recKey === 'string' ? saved.recKey : null;
    var baseKey = typeof saved.baseKey === 'string' ? saved.baseKey : null;
    if (recKey && REC_INDEX[recKey] && recMatches(REC_INDEX[recKey])) state.recKey = recKey;
    if (baseKey && BASE_INDEX[baseKey] && baseMatches(BASE_INDEX[baseKey])) state.baseKey = baseKey;
    syncSetSwitch();
    if (typeof saved.y === 'number') {
      try { window.scrollTo(0, saved.y); } catch (e) {}
    }
    return true;
  }

  /* ---------------- proposals ---------------- */

  function storageOrNull() {
    // Some browsers throw on property access alone (not just on read/write).
    try { return window.localStorage; } catch (e) { return null; }
  }
  function showStorageNotice(text) {
    var el = byId('collab-storage-notice');
    if (!el) return;
    if (!text) { el.hidden = true; el.textContent = ''; return; }
    el.hidden = false;
    el.textContent = text;
  }
  function probeStorage() {
    var storage = storageOrNull();
    if (!storage) {
      storageState.available = false;
      storageState.message = STORAGE_DISABLED_MSG;
      return;
    }
    var res = probeStorageAvailable(storage, STORAGE_KEY);
    storageState.available = res.available;
    storageState.message = res.message;
  }
  function proposals() {
    var storage = storageOrNull();
    if (!storage) {
      storageState.available = false;
      storageState.message = STORAGE_DISABLED_MSG;
      return [];
    }
    var res = readStorage(storage, STORAGE_KEY);
    if (!res.available) {
      storageState.available = false;
      storageState.message = res.message;
    }
    if (res.message) showStorageNotice(res.message);
    return res.list;
  }
  function legacyProposals() {
    var storage = storageOrNull();
    if (!storage) return [];
    try {
      var res = parseProposals(storage.getItem(LEGACY_KEY));
      return res.list;
    } catch (e) { return []; }
  }
  function writeProposals(list) {
    var storage = storageOrNull();
    if (!storage || !storageState.available) return false;
    var res = writeStorage(storage, STORAGE_KEY, list);
    if (!res.ok) {
      storageState.available = false;
      storageState.message = res.message;
      showStorageNotice(res.message);
      var form = byId('proposal-form');
      if (form) setFormEnabled(false);
    }
    return res.ok;
  }

  function renderSummary() {
    var list = proposals();
    var pending = list.filter(function (p) { return p.status === 'submitted'; }).length;
    var approved = list.filter(function (p) { return p.status === 'approved'; }).length;
    var el = byId('collab-summary');
    if (el) {
      el.textContent = 'D5 整期需求基准 ' + BASE.length + ' 行 · USNJ 补货建议 ' +
        REC.length + ' 行 · 本地提案 ' + list.length +
        '（待模拟审核 ' + pending + ' / 模拟通过 ' + approved + '）';
    }
    var count = byId('proposal-count');
    if (count) count.textContent = '（' + list.length + ' 条）';
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
    return {proposal: {
      id: newId(), row_id: r.id, kind: kind, value: check.value,
      start: start, end: end, event_id: eventId, reason: reason,
      evidence: evidence, created_at: new Date().toISOString(), status: 'submitted',
      baseline_version: BASE_VERSION || null
    }};
  }

  function newId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'p-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  function submitProposal(event, r) {
    event.preventDefault();
    if (!storageState.available) {
      message('浏览器已禁用本地存储，无法保存提案。', true);
      return;
    }
    var out = collectProposal(r);
    if (out.error) { message(out.error, true); return; }
    var list = proposals();
    list.push(out.proposal);
    var ok = writeProposals(list);
    clearDraft(r);
    renderSummary();
    renderProposals();
    renderTable({focusKey: null});
    if (ok) {
      showStorageNotice('');
      var fold = byId('proposals-fold');
      if (fold) fold.open = true;
      message('提案已保存在本浏览器（刷新仍保留；仅演示，不上传、不审批、不写 EN）。');
      var submit = byId('wb-submit');
      if (submit) { try { submit.focus({preventScroll: true}); } catch (e) {} }
    } else {
      message('浏览器已禁用本地存储，无法保存提案。', true);
    }
  }

  function renderProposals() {
    var host = byId('proposals');
    if (!host) return;
    var list = proposals().slice().reverse();
    var html = '';
    if (!list.length) {
      host.innerHTML = '<p class="mutednote">还没有提案。在「需求基准」里选择一行，补充第一条业务判断。</p>';
    } else {
      html = list.map(function (p) {
        var r = null;
        for (var i = 0; i < BASE.length; i++) {
          if (BASE[i].id === p.row_id) { r = BASE[i]; break; }
        }
        var unit = r ? unitOf(r) : '';
        var amount = p.kind === 'event_only' ? '不调整数量' :
          p.kind === 'percent' ? qty(p.value) + '%' : qty(p.value) + ' ' + esc(unit);
        var actions = '';
        if (state.review && p.status === 'submitted') {
          actions = '<div class="actions">' +
            '<button type="button" class="btn small" data-decision="approved" data-id="' + esc(p.id) + '">模拟通过</button>' +
            '<button type="button" class="btn small" data-decision="rejected" data-id="' + esc(p.id) + '">模拟驳回</button>' +
            '</div>';
        }
        var stale = p.baseline_version && BASE_VERSION && p.baseline_version !== BASE_VERSION
          ? ' <span class="rec-badge warn">旧基准 ' + esc(p.baseline_version) + '</span>' : '';
        return '<article class="proposal"><div>' +
          '<h4>' + esc(r ? (r.name || r.sku) : p.row_id) + stale + '</h4>' +
          '<p>' + esc(KIND_LABELS[p.kind] || p.kind) + ' · ' + amount +
          ' <span class="hint">/ ' + esc(day(p.start) || '待核') + ' — ' + esc(day(p.end) || '待核') + '</span></p>' +
          '<p>' + esc(p.reason) + '</p>' +
          (p.evidence ? '<p class="meta">依据：' + esc(p.evidence) + '</p>' : '') +
          '<p class="meta">事件 ' + esc(p.event_id) + ' · ' + esc(p.created_at) + '</p>' +
          actions + '</div>' +
          '<div><span class="status ' + esc(p.status) + '">' +
          esc(STATUS_LABELS[p.status] || p.status) + '</span></div></article>';
      }).join('');
      host.innerHTML = html;
    }
    Array.prototype.forEach.call(host.querySelectorAll('[data-decision]'), function (btn) {
      btn.addEventListener('click', function () {
        setStatus(btn.getAttribute('data-id'), btn.getAttribute('data-decision'));
      });
    });
    var legacy = legacyProposals();
    var legacyEl = byId('legacy-proposals');
    if (legacyEl) {
      legacyEl.hidden = !legacy.length;
      legacyEl.textContent = legacy.length
        ? '另有旧演示记录 ' + legacy.length + ' 条（键 supply-workbench:proposals:v1）：只读展示，不迁移、不删除。'
        : '';
    }
  }

  function setStatus(id, status) {
    var list = proposals().map(function (p) {
      if (String(p.id) === String(id)) p.status = status;
      return p;
    });
    writeProposals(list);
    renderSummary();
    renderProposals();
    message('本地状态已更新为「' + (STATUS_LABELS[status] || status) + '」，仅保存在本浏览器。');
  }

  /* ---------------- cross-row audit view (一级「证据链」) ---------------- */

  function renderEvidenceList() {
    var tbody = byId('ev-rows');
    if (!tbody) return;
    var q = state.evQ.toLowerCase();
    var rows = REC.filter(function (r) {
      if (!q) return true;
      return [r.sku, r.customer, r.physical_form, r.uom, r.reason]
        .some(function (v) { return String(v === null || v === undefined ? '' : v).toLowerCase().indexOf(q) >= 0; });
    });
    var count = byId('ev-count');
    if (count) count.textContent = '显示 ' + rows.length + ' / ' + REC.length + ' 条证据';
    tbody.innerHTML = rows.map(function (r) {
      var key = rowKey(r);
      return '<tr data-ev="' + esc(key) + '"' + (key === state.evKey ? ' class="selected"' : '') + '>' +
        '<td><strong>' + esc(r.sku || '—') + '</strong><small class="hint" style="display:block">' +
        esc(r.customer || '归属待确认') + ' · ' + esc(r.physical_form || '—') + '</small></td>' +
        '<td>' + intq(r.e_qty) + '</td></tr>';
    }).join('') || '<tr><td colspan="2" class="empty">没有匹配的行</td></tr>';
    Array.prototype.forEach.call(tbody.querySelectorAll('[data-ev]'), function (tr) {
      tr.addEventListener('click', function () {
        state.evKey = tr.getAttribute('data-ev');
        renderEvidenceList();
        renderEvidencePanel();
      });
    });
  }

  function renderEvidencePanel() {
    var host = byId('ev-panel');
    if (!host) return;
    var r = REC_INDEX[state.evKey];
    if (!r) {
      host.innerHTML = '<div class="empty">选择左侧一条建议行，查看逐项证据。</div>';
      return;
    }
    var ctx = contextFor(r, 'rec');
    var html = '<div class="micro">证据链 L2 / L3 · 只读 · 跨行审计</div>' +
      '<h2 id="ev-title" tabindex="-1">' + esc(r.sku || '—') + '</h2>' +
      '<p class="hint">' + esc(r.customer || '归属待确认') + ' · ' +
      esc(r.physical_form || '—') + ' · ' + esc(r.uom || '—') + '</p>' +
      evidenceSections(ctx, 'ev') +
      '<div class="evnav">' +
      '<button type="button" class="btn small" data-ev-prev="1">上一条</button>' +
      '<button type="button" class="btn small" data-ev-next="1">下一条</button>' +
      '<button type="button" class="btn small" data-locate="1">在工作台定位</button>' +
      '<button type="button" class="btn small ghost" data-goto-workbench="1">返回工作台</button>' +
      '</div>';
    host.innerHTML = html;
    bindFolds(host);
    Array.prototype.forEach.call(host.querySelectorAll('[data-ev-prev]'), function (btn) {
      btn.addEventListener('click', function () { stepEvidence(-1); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-ev-next]'), function (btn) {
      btn.addEventListener('click', function () { stepEvidence(1); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-locate]'), function (btn) {
      btn.addEventListener('click', function () { locateInWorkbench(); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-goto-workbench]'), function (btn) {
      btn.addEventListener('click', function () { setView('workbench'); });
    });
  }

  function stepEvidence(delta) {
    if (!REC.length) return;
    var at = REC.findIndex(function (x) { return rowKey(x) === state.evKey; });
    if (at < 0) at = 0;
    var next = (at + delta + REC.length) % REC.length;
    state.evKey = rowKey(REC[next]);
    renderEvidenceList();
    renderEvidencePanel();
  }

  function locateInWorkbench() {
    var r = REC_INDEX[state.evKey];
    if (!r) return;
    var key = rowKey(r);
    state.set = 'rec';
    state.recKey = key;
    state.outOfFilter = false;
    syncSetSwitch();
    setView('workbench');
    applySelection();
    renderDetail({force: true, scrollTop: true});
    var btn = findRowButton(key);
    if (btn) { try { btn.focus({preventScroll: true}); } catch (e) { btn.focus(); } }
    if (reconcileSelection()) renderDetail({force: true});
    saveUiState();
  }

  /* ---------------- navigation ---------------- */

  function setView(view) {
    if (state.view === view) return;
    viewScroll[state.view] = {
      y: (window.scrollY || window.pageYOffset || 0),
      detail: (function () { var sc = detailScroller(); return sc ? sc.scrollTop : 0; })()
    };
    state.view = view;
    Array.prototype.forEach.call(document.querySelectorAll('nav.topnav button'), function (b) {
      var on = b.getAttribute('data-view') === view;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    Array.prototype.forEach.call(document.querySelectorAll('main > section.view'), function (s) {
      s.classList.toggle('active', s.id === 'view-' + view);
    });
    if (view === 'evidence') { renderEvidenceList(); renderEvidencePanel(); }
    if (view === 'workbench') {
      renderTable({focusKey: null});
      renderDetail();
      var savedDetail = viewScroll.workbench ? viewScroll.workbench.detail : 0;
      var sc = detailScroller();
      if (sc && typeof savedDetail === 'number') sc.scrollTop = savedDetail;
    }
    var saved = viewScroll[view];
    if (saved && typeof saved.y === 'number') {
      try { window.scrollTo(0, saved.y); } catch (e) {}
    }
    saveUiState();
  }

  function syncSetSwitch() {
    Array.prototype.forEach.call(document.querySelectorAll('.setswitch [data-set]'), function (b) {
      var on = b.getAttribute('data-set') === state.set;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    var actionWrap = byId('wb-action-wrap');
    if (actionWrap) actionWrap.hidden = state.set !== 'rec';
  }

  function switchSet(next) {
    state.set = next;
    state.outOfFilter = false;
    syncSetSwitch();
    renderTable({focusKey: null});
    if (!reconcileSelection()) { applySelection(); renderDetail({force: true}); }
    saveUiState();
  }

  function onFilterChange() {
    renderTable({focusKey: null});
    reconcileSelection();
    saveUiState();
  }

  function bindControls() {
    Array.prototype.forEach.call(document.querySelectorAll('nav.topnav button'), function (b) {
      b.addEventListener('click', function () { setView(b.getAttribute('data-view')); });
    });
    Array.prototype.forEach.call(document.querySelectorAll('.setswitch [data-set]'), function (b) {
      b.addEventListener('click', function () { switchSet(b.getAttribute('data-set')); });
    });
    var search = byId('wb-search');
    if (search) {
      search.addEventListener('input', function () {
        state.q = search.value.trim();
        onFilterChange();
      });
    }
    var actionSel = byId('wb-action');
    if (actionSel) {
      var actions = [];
      REC.forEach(function (r) { if (r.action && actions.indexOf(r.action) < 0) actions.push(r.action); });
      actions.sort();
      actionSel.innerHTML = '<option value="">全部动作</option>' + actions.map(function (a) {
        return '<option value="' + esc(a) + '">' + esc(a) + '</option>';
      }).join('');
      actionSel.addEventListener('change', function () {
        state.action = actionSel.value;
        onFilterChange();
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll('[data-flag]'), function (cb) {
      cb.addEventListener('change', function () {
        state.flags[cb.getAttribute('data-flag')] = cb.checked;
        onFilterChange();
      });
    });
    var clear = byId('wb-clear');
    if (clear) {
      clear.addEventListener('click', function () {
        state.q = ''; state.action = '';
        Object.keys(state.flags).forEach(function (k) { state.flags[k] = false; });
        if (byId('wb-search')) byId('wb-search').value = '';
        if (byId('wb-action')) byId('wb-action').value = '';
        Array.prototype.forEach.call(document.querySelectorAll('[data-flag]'), function (x) {
          x.checked = false;
        });
        onFilterChange();
      });
    }
    var focusDetail = byId('wb-focus-detail');
    if (focusDetail) {
      focusDetail.addEventListener('click', function () {
        if (!currentKey()) { announce('先选择一行再查看详情'); return; }
        if (mode === 'narrow') { openSheet(); return; }
        var title = byId('detail-title');
        if (title) { try { title.focus({preventScroll: true}); } catch (e) { title.focus(); } }
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll('[data-pane]'), function (b) {
      b.addEventListener('click', function () {
        var pane = b.getAttribute('data-pane');
        Array.prototype.forEach.call(document.querySelectorAll('[data-pane]'), function (x) {
          x.classList.toggle('active', x === b);
        });
        Array.prototype.forEach.call(document.querySelectorAll('.analysis-pane'), function (p) {
          p.classList.toggle('active', p.id === 'pane-' + pane);
        });
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-goto-workbench]'), function (b) {
      b.addEventListener('click', function () { setView('workbench'); });
    });
    var evSearch = byId('ev-search');
    if (evSearch) {
      evSearch.addEventListener('input', function () {
        state.evQ = evSearch.value.trim();
        renderEvidenceList();
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll('[data-review-mode]'), function (b) {
      b.addEventListener('click', function () {
        state.review = b.getAttribute('data-review-mode') === 'reviewer';
        Array.prototype.forEach.call(document.querySelectorAll('[data-review-mode]'), function (x) {
          x.classList.toggle('active', x === b);
        });
        renderProposals();
      });
    });
  }

  function init() {
    try {
      probeStorage();
      bindControls();
      bindSheet();
      restoreUiState();
      if (!BASE.length) baseSwitchFallback();
      state.evKey = state.recKey || (REC.length ? rowKey(REC[0]) : null);
      renderSummary();
      renderTable({focusKey: null});
      applySelection();
      renderDetail();
      renderEvidenceList();
      renderEvidencePanel();
      renderProposals();
      measureShell();
      observeLayout();
      if (!storageState.available) showStorageNotice(storageState.message);
    } catch (e) {
      showStorageNotice('页面初始化失败：' + (e && e.message ? e.message : String(e)));
    }
  }

  function baseSwitchFallback() {
    var btn = document.querySelector('[data-set="base"]');
    if (btn) btn.disabled = true;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


def embed_json(obj) -> str:
    """JSON for a <script type="application/json"> block.

    ``</`` is rewritten to ``<\\/`` and every remaining angle bracket is
    unicode-escaped so data can never terminate the script element early.
    ``allow_nan=False``: NaN/Infinity are not JSON, and ``json.loads`` in the
    browser would reject the whole payload. Callers must run ``json_safe``.
    """
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    text = text.replace("</", "<\\/")
    text = text.replace("<", "\\u003c").replace(">", "\\u003e")
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return text


def json_safe(obj, counts: dict | None = None, key: str | None = None):
    """Copy ``obj`` with non-finite floats (NaN/±Infinity) replaced by None.

    The 11-24 export contains NaN cells. JSON has no NaN, and the page must not
    invent 0 for them, so they travel as null (= unknown) and every occurrence
    is counted by field so the page can report it instead of hiding it.
    """
    if counts is None:
        counts = {}
    if isinstance(obj, dict):
        return {k: json_safe(v, counts, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v, counts, key) for v in obj]
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        counts[key or "?"] = counts.get(key or "?", 0) + 1
        return None
    return obj


def filter_usnj(baseline: dict) -> list:
    """Keep only demand-baseline rows owned by the USNJ branch."""
    rows = baseline.get("rows") or []
    return [r for r in rows if str(r.get("branch") or "").strip() == BRANCH]


def load_baseline(path: Path):
    """Return (document, USNJ rows) from a demand-baseline JSON file."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc, filter_usnj(doc)


def _key(row: dict) -> tuple:
    unit = row.get("uom")
    if unit in (None, ""):
        unit = row.get("unit")
    return (str(row.get("sku") or ""), str(row.get("physical_form") or ""), str(unit or ""))


def reconcile(rec_rows: list, base_rows: list) -> dict:
    """Full outer join of suggestion vs baseline rows on SKU x 形态 x 单位.

    SKU alone is one-to-many in this snapshot (same SKU sold as 成品 and 皮壳),
    so a SKU-only join would silently pick a row. Counts are kept on both sides.
    """
    rec_counts = Counter(_key(r) for r in rec_rows)
    base_counts = Counter(_key(r) for r in base_rows)
    rec_keys, base_keys = set(rec_counts), set(base_counts)
    only_rec = sorted(rec_keys - base_keys)
    only_base = sorted(base_keys - rec_keys)
    ambiguous = sorted(k for k in rec_keys & base_keys if rec_counts[k] > 1 or base_counts[k] > 1)
    unique = len(rec_keys & base_keys) - len(ambiguous)
    sku_counts = Counter(str(r.get("sku") or "") for r in rec_rows)
    sku_counts_base = Counter(str(r.get("sku") or "") for r in base_rows)
    dup_skus = {k for k, v in sku_counts.items() if v > 1} | {
        k for k, v in sku_counts_base.items() if v > 1}
    return {
        "key": "SKU×形态×单位",
        "unique": unique,
        "only_rec": len(only_rec),
        "only_base": len(only_base),
        "ambiguous": ambiguous,
        "only_rec_keys": ["|".join(k) for k in only_rec],
        "only_base_keys": ["|".join(k) for k in only_base],
        "rec_total": len(rec_rows),
        "base_total": len(base_rows),
        "sku_only_ambiguous": len(dup_skus),
    }


def _sku_universe(rows) -> list:
    return sorted(
        {(r.get("sku"), r.get("physical_form"), r.get("uom"), r.get("customer")) for r in rows},
        key=lambda t: tuple("" if v is None else str(v) for v in t),
    )


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


def _decision_cards(summary: dict, rec_total: int, base_total: int, recon: dict) -> str:
    cards = [
        (summary["needs_decision"], "需拍板"),
        (summary["low_confidence"], "低置信"),
        (summary["special"], "特殊品"),
        (summary["ownership_pending"], "归属待确认"),
        (rec_total, "补货建议行（只读）"),
        (base_total, "需求基准行（仅 USNJ）"),
        (f"{recon['unique']}/{recon['rec_total']}", "同键唯一对单"),
    ]
    return "".join(f"<div class='metric'><b>{v}</b><span class='label'>{t}</span></div>"
                   for v, t in cards)


def _analysis_a(rows) -> str:
    a_rows = _sku_universe(rows)
    body = "".join(
        f"<tr><td>{esc(x[0])}</td><td>{esc(x[1])}</td><td>{esc(x[2])}</td><td>{esc(x[3])}</td></tr>"
        for x in a_rows)
    return (f"<h2>A 商品范围（{len(a_rows)} 个 SKU×形态×UOM，去重）</h2>"
            "<p class='intro'>同一 SKU 可能以不同形态出现在建议里；这里是去重后的商品宇宙，"
            "不改变建议行数量。</p>"
            "<div class='scroll-x'><table id='table-a'><thead><tr><th>SKU</th><th>形态</th>"
            "<th>UOM</th><th>客户</th></tr></thead><tbody>" + body + "</tbody></table></div>")


def _analysis_b(b1, b2) -> str:
    return (f"<h2>B 归属（{len(b1)} 个 current USNJ / {len(b2)} 个待确认）</h2>"
            "<p class='intro'>归属以 B 清单为准；待确认行不并入 current，也不静默丢弃。</p>"
            f"<h3>B 归属清单（{len(b1)} 个 current USNJ）</h3><div class='scroll-x'>{b_table(b1)}</div>"
            f"<h3>归属待确认（{len(b2)} 个）</h3><div class='scroll-x'>{b_table(b2)}</div>")


def _analysis_c(rows) -> str:
    return ("<h2>C 库存（当前可发，不含在途）</h2>"
            "<p class='intro'>C = 当前可发，不含在途；EN 已发运/待发、PO、SO、CG 同表列出但各自口径，"
            "不能相加替代；CG 是下游缓冲，不可回拨。</p>"
            "<div class='scroll-x'><table id='table-c'><thead><tr><th>SKU</th><th>C</th>"
            "<th>EN已发运</th><th>EN待发</th><th>PO</th><th>SO</th><th>CG</th><th>近期SO</th>"
            "<th>历史SO</th></tr></thead><tbody>" + _supply_rows(rows) + "</tbody></table></div>")


def _analysis_d(rows) -> str:
    return ("<h2>D 需求预估（q50 中位，不是补货量）</h2>"
            "<p class='intro'>分位与模型来自预测快照；预测不加进建议量，也不与需求基准相加。</p>"
            "<div class='scroll-x'><table id='table-d'><thead><tr><th>SKU</th><th>预测 q50</th>"
            "<th>q50</th><th>q90</th><th>q95</th><th>模型</th></tr></thead><tbody>"
            + _forecast_rows(rows) + "</tbody></table></div>")


def _analysis_e(rows) -> str:
    return ("<h2>E 到期供给（SO/EN/PO/C/CG）</h2>"
            "<p class='intro'>按需要日汇总的到期供给；SO 管线不加入建议量；生产/DN/通途 PO 尚未接入，"
            "显示缺失而非 0。</p>"
            "<div class='scroll-x'><table id='table-e'><thead><tr><th>SKU</th><th>C</th>"
            "<th>EN已发运</th><th>EN待发</th><th>PO</th><th>SO</th><th>CG</th><th>近期SO</th>"
            "<th>历史SO</th></tr></thead><tbody>" + _supply_rows(rows) + "</tbody></table></div>")


def _analysis_nav() -> str:
    return "".join(
        "<button type='button' data-pane='%s'%s>%s</button>" % (
            key, " class='active'" if key == "a" else "", esc(title))
        for key, title in ANALYSIS_TABS)


def _method_view(recon: dict, as_of: str, nonfinite: dict) -> str:
    nf_total = sum(nonfinite.values())
    if nf_total:
        nf_text = (
            f"<li>本次快照有 {nf_total} 个非有限数值（NaN/Infinity），按未知展示、不补 0："
            + "、".join(f"<code>{esc(k)}</code> {v} 处" for k, v in nonfinite.items())
            + "。源文件不是严格 JSON，生成器在写页前已把 NaN 置空并在此计数。</li>"
        )
    else:
        nf_text = "<li>本次快照无非有限数值（NaN/Infinity）。</li>"
    return (
        "<div class='viewhead'><div><div class='eyebrow'>METHOD</div><h1>口径</h1>"
        "<p class='sub'>业务定义、字段来源与模式语义的唯一说明处；分析方法各页只放算法简介。</p></div></div>"
        "<div class='method'>"
        "<h2>数据与模式</h2><ul>"
        f"<li>数据为内嵌快照（as_of {esc(as_of)}），页面不发起任何网络请求；"
        "CSP 保留 <code>connect-src 'none'</code>。</li>"
        "<li>本页永远不显示「刚刚刷新实时库存」：服务可用、库存实时、建议可执行是三件事，分开标识。</li>"
        "<li>提案只写入本浏览器 <code>supply-workbench:proposals:v2</code>：刷新保留，"
        "清理浏览器数据或换浏览器看不到本浏览器的提案；不上传、不审批、不写 EN。</li>"
        "<li>旧键 <code>supply-workbench:proposals:v1</code> 的记录只读展示，不迁移、不删除。</li>"
        "<li>禁用本浏览器存储时提案表单停用，其余内容仍可浏览。</li>"
        "</ul>"
        "<h2>数据口径</h2><ul>"
        "<li>这是历史回放，不是今天的执行建议；页面显示数据包 as_of 与快照版本。</li>"
        "<li>C = 当前可发，不含在途；E = 按时供给；CG = 下游缓冲，不可回拨。</li>"
        "<li>SO 是 EN 分公司生产/交付单；通途 PO 是 DN 后采购入库；两者不能相加替代。</li>"
        "<li>SO 管线未加入建议量；生产/DN/通途 PO 尚未接入，显示「未接入」而不是 0。</li>"
        "<li>USNJ 补货建议（只读）与 D5 整期需求基准（仅 USNJ）是两类不同数据：不相加、不替代。</li>"
        "<li>缺失=未知，不补 0；空日期写「待核」；无单位不显示可比较的量。</li>"
        + nf_text +
        "<li>差额 = 供给 − 需求是页面内的对照计算，不是补货量，也不改写任何字段。</li>"
        "</ul>"
        "<h2>字段来源</h2>"
        "<table><thead><tr><th>视图</th><th>字段</th><th>来源</th></tr></thead><tbody>"
        "<tr><td>工作台（建议）</td><td>action, reason, coverage, forecast, q50/q90/q95, "
        "c_qty, e_qty, extra.*, so_*, flags</td><td>快照 rows（原样，不重算）</td></tr>"
        "<tr><td>工作台（基准）</td><td>id, branch, sku, physical_form, uom/unit, "
        "baseline_qty 或 demand_qty</td><td>需求基准 rows（仅 USNJ）</td></tr>"
        "<tr><td>分析方法 A–E</td><td>同快照字段，按页投影</td><td>快照 + B_*.csv</td></tr>"
        "<tr><td>证据链</td><td>全部原始字段 + source_row/source_hash/so_lines</td>"
        "<td>快照 rows；缺失写「未记录」</td></tr>"
        "</tbody></table>"
        "<h2>行键与对账</h2><ul>"
        f"<li>对单键 = SKU × 形态 × 单位；本次唯一匹配 {recon['unique']} / "
        f"建议 {recon['rec_total']} 行 / 基准 {recon['base_total']} 行。</li>"
        f"<li>仅建议 {recon['only_rec']} · 仅基准 {recon['only_base']} · 歧义 "
        f"{len(recon['ambiguous'])}；两边总数分别守恒。</li>"
        f"<li>若只按 SKU 对单，本次会有 {recon['sku_only_ambiguous']} 个 SKU 一对多"
        "（同一 SKU 同时以成品/皮壳出现），因此不按 SKU 单列 join、不取第一条。</li>"
        "<li>页面从 SKU×形态×单位派生「规范化行键」仅用于定位，不写入数据。</li>"
        "</ul>"
        "<h2>本阶段不做</h2><ul>"
        "<li>不改业务计算、不扩范围、不做周桶重分配、不生成订单。</li>"
        "<li>不做真实身份/审批后端，不接 WO/DN 新数据，不替换预测模型。</li>"
        "<li>不引入前端框架或表格库；保持单文件、无外链、无网络。</li>"
        "</ul>"
        "</div>")


def build(snapshot_path: Path, baseline_path: Path, b_dir: Path | None = None) -> str:
    snap = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    rows = snap["rows"]
    baseline_doc, baseline_rows = load_baseline(Path(baseline_path))

    b1 = read_b(b_dir, "B_USNJ归属清单.csv")
    b2 = read_b(b_dir, "B_待确认.csv")
    as_of = snap.get("as_of") or baseline_doc.get("as_of") or "未知"
    recon = reconcile(rows, baseline_rows)

    summary = {k: sum(1 for r in rows if r.get(k)) for k in
               ("needs_decision", "low_confidence", "special", "ownership_pending")}

    payload = {
        "version": snap.get("version"),
        "as_of": as_of,
        "demo": baseline_doc.get("demo"),
        "branch": BRANCH,
        "recommendation_rows": len(rows),
        "recon": recon,
        "baseline": {
            "version": baseline_doc.get("version"),
            "as_of": baseline_doc.get("as_of"),
            "demo": baseline_doc.get("demo"),
            "rows": baseline_rows,
        },
        "rows": rows,
    }
    nonfinite: dict = {}
    payload = json_safe(payload, nonfinite)
    payload["nonfinite"] = dict(sorted(nonfinite.items()))

    data_text = embed_json(payload)
    main_js = APP_JS.replace("/*__COLLAB_LIB__*/", COLLAB_LIB)
    csp = CSP_STATIC + "; script-src " + csp_hash(main_js) + " " + csp_hash(data_text)

    nav = "".join(
        "<button%s type='button' data-view='%s' role='tab' aria-selected='%s'>%s</button>" % (
            " class='active'" if key == "workbench" else "", key,
            "true" if key == "workbench" else "false", esc(title))
        for key, title in VIEWS
    )
    chips = "".join(
        "<span class='mchip'><b>%s</b>%s</span>" % (esc(k), esc(v.format(as_of=as_of)))
        for k, v in MODE_CHIPS
    )

    doc = "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
    doc += f"<meta http-equiv=\"Content-Security-Policy\" content=\"{csp}\">"
    doc += "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    doc += "<title>USNJ 补货协同工作台（静态演示）</title>"
    doc += "<style>" + STYLE + "</style></head><body>"

    doc += "<div class='topstack'>"
    doc += "<div class='modebanner' role='note'>"
    doc += f"<span class='mb-main'>{esc(BANNER_TEXT.format(as_of=as_of))}</span>"
    doc += f"<span class='mchips'>{chips}</span></div>"
    doc += "<header class='site'><div><div class='brand'>USNJ 补货协同工作台"
    doc += "<span>STATIC DEMO</span></div>"
    doc += "<div class='datachips'>"
    doc += f"<span class='chip'>补货建议 {len(rows)} 行（只读）</span>"
    doc += f"<span class='chip'>需求基准 {len(baseline_rows)} 行（仅 USNJ）</span>"
    doc += (f"<span class='chip'>对单 {recon['unique']}/{recon['rec_total']}（"
            f"{esc(recon['key'])}）</span></div></div>")
    doc += "<div class='sitemeta'>"
    doc += f"快照 {esc(snap.get('version') or snap.get('source_name'))} · as_of {esc(as_of)}<br>"
    doc += f"基准 {esc(baseline_doc.get('version'))} · {esc(baseline_doc.get('as_of'))}<br>"
    doc += "不直接下单；采购/运营需复核</div></header>"
    doc += f"<nav class='topnav' role='tablist' aria-label='一级视图'>{nav}</nav>"
    doc += "</div>"

    doc += "<main>"
    doc += "<p class='storage-notice' id='collab-storage-notice' role='alert' hidden></p>"

    # ---- 工作台 ----
    doc += "<section class='view active' id='view-workbench' role='tabpanel'>"
    doc += "<div class='workbench-shell' id='workbench-shell'>"
    doc += "<div class='viewhead'><div><div class='eyebrow'>WORKBENCH</div>"
    doc += "<h1>工作台</h1><p class='sub'>默认看补货建议（只读）。切到需求基准才允许填写演示提案。"
    doc += "工作区宽度大于 720px 时始终左表 + 右详情；窄屏改为底部抽屉，列表仍留在背后。</p></div>"
    doc += f"<div class='micro' id='collab-summary'>D5 整期需求基准 {len(baseline_rows)} 行 · "
    doc += f"USNJ 补货建议 {len(rows)} 行</div></div>"
    doc += "<div class='wbtop'><div class='wbcount'>"
    doc += "<div class='setswitch' role='group' aria-label='数据视图'>"
    doc += "<button class='active' type='button' data-set='rec' aria-pressed='true'>补货建议（只读）</button>"
    doc += "<button type='button' data-set='base' aria-pressed='false'>需求基准（可演示提案）</button></div>"
    doc += "<span id='wb-count'>—</span><button class='btn small ghost' type='button' id='wb-clear'>清除筛选</button>"
    doc += "<button class='btn small ghost' type='button' id='wb-focus-detail'>查看详情</button>"
    doc += "</div>"
    doc += "<div class='wbfilters'>"
    doc += "<input id='wb-search' type='search' placeholder='搜索 SKU / 客户 / 原因 / 模型' autocomplete='off' aria-label='搜索'>"
    doc += "<span id='wb-action-wrap'><select id='wb-action' aria-label='筛选动作'><option value=''>全部动作</option></select></span>"
    doc += "<label class='check'><input type='checkbox' data-flag='decision'>需拍板</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='supply'>缺供给</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='special'>特殊品</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='pending'>归属待确认</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='low'>低置信</label>"
    doc += "</div></div>"
    doc += "<div class='workspace' id='workspace'>"
    doc += "<section class='board' aria-label='列表'><div class='board-scroll' id='board-scroll'>"
    doc += "<table class='rows' id='wb-table' data-table-set='rec'><thead><tr><th>商品 / 客户 / 形态</th>"
    doc += "<th class='col-period'>期间</th><th>建议</th><th class='col-coverage'>覆盖</th>"
    doc += "<th class='col-reason'>原因</th><th class='col-flags'>标记</th></tr></thead>"
    doc += "<tbody id='wb-rows'><tr><td colspan='6' class='empty'>正在载入…</td></tr></tbody></table>"
    doc += "</div><div class='tablefoot'><span id='wb-foot'></span><span id='wb-version'></span></div></section>"
    doc += "<div class='detail-slot' id='detail-slot' aria-label='详情'>"
    doc += "<div class='detail detail-content' id='detail-content'>"
    doc += "<div class='empty'>选择左侧一行查看结论、证据和可用操作。<br>"
    doc += "补货建议只读；唯一关联到需求基准时可在本栏填写演示判断。</div>"
    doc += "</div></div></div>"
    doc += "<p class='sr-only' id='wb-announce' aria-live='polite'></p>"
    doc += "<dialog class='sheet' id='detail-sheet' aria-label='详情'>"
    doc += "<div class='sheet-wrap'><div class='sheet-bar'>"
    doc += "<span class='sheet-handle' id='sheet-handle' aria-hidden='true'></span>"
    doc += "<button type='button' class='btn small sheet-close' id='sheet-close'>关闭详情 ×</button></div>"
    doc += "<div class='sheet-scroll' id='sheet-scroll'></div></div></dialog>"
    doc += "<details class='panel-fold' id='proposals-fold'>"
    doc += "<summary>本浏览器演示提案 <span class='muted' id='proposal-count'>（0 条）</span></summary>"
    doc += "<p class='hint'>提案只存在本浏览器；刷新保留，清理浏览器数据或换浏览器看不到。"
    doc += "「模拟通过/模拟驳回」只是本地状态，不代表审批。</p>"
    doc += "<div class='viewswitch' role='group' aria-label='本地视角'>"
    doc += "<button type='button' data-review-mode='operator' class='active'>运营视角</button>"
    doc += "<button type='button' data-review-mode='reviewer'>审核视角（模拟）</button></div>"
    doc += "<p class='mutednote' id='legacy-proposals' hidden></p>"
    doc += "<div id='proposals'><p class='mutednote'>还没有提案。</p></div>"
    doc += "<p class='form-message' id='collab-message' aria-live='polite'></p></details>"
    doc += "</div>"
    doc += "</section>"

    # ---- 证据链 ----
    doc += "<section class='view' id='view-evidence' role='tabpanel'>"
    doc += "<div class='viewhead'><div><div class='eyebrow'>EVIDENCE</div><h1>证据链</h1>"
    doc += "<p class='sub'>逐行 L2 证据：身份、期间、需求、供给各阶段、SO 三段、库存快照、"
    doc += "来源哈希与未知道原因。每个数字都能定位到字段；缺字段写缺失，不补 0。</p></div>"
    doc += "<span class='micro' id='ev-count'>—</span></div>"
    doc += "<div class='evgrid'><div class='evlist'>"
    doc += "<div class='searchline'><input id='ev-search' type='search' placeholder='搜索 SKU / 客户 / 形态' autocomplete='off' aria-label='搜索证据行'></div>"
    doc += "<div class='scroll'><table><thead><tr><th>商品</th><th>E 供给</th></tr></thead>"
    doc += "<tbody id='ev-rows'><tr><td colspan='2' class='empty'>正在载入…</td></tr></tbody></table></div></div>"
    doc += "<div class='evpanel' id='ev-panel'><div class='empty'>选择左侧一条建议行，查看逐项证据。</div></div></div>"
    doc += "</section>"

    # ---- 分析方法 ----
    doc += "<section class='view' id='view-analysis' role='tabpanel'>"
    doc += "<div class='viewhead'><div><div class='eyebrow'>ANALYSIS</div><h1>分析方法</h1>"
    doc += "<p class='sub'>同一快照的分析投影，不是第二套决策列表：A 商品范围 / B 归属 / C 库存 / "
    doc += "D 需求预估 / E 到期供给。字段与迁移前一致。</p></div>"
    doc += "<button type='button' class='btn small' data-goto-workbench='1'>返回所选建议</button></div>"
    doc += f"<div class='analysis-nav' role='group' aria-label='分析方法页签'>{_analysis_nav()}</div>"
    doc += f"<div class='analysis-pane active' id='pane-a'>{_analysis_a(rows)}</div>"
    doc += f"<div class='analysis-pane' id='pane-b'>{_analysis_b(b1, b2)}</div>"
    doc += f"<div class='analysis-pane' id='pane-c'>{_analysis_c(rows)}</div>"
    doc += f"<div class='analysis-pane' id='pane-d'>{_analysis_d(rows)}</div>"
    doc += f"<div class='analysis-pane' id='pane-e'>{_analysis_e(rows)}</div>"
    doc += "</section>"

    # ---- 口径 ----
    doc += "<section class='view' id='view-method' role='tabpanel'>"
    doc += _method_view(recon, as_of, payload["nonfinite"])
    doc += "</section>"
    doc += "</main>"

    doc += "<noscript><p class='storage-notice'>本页交互依赖内联脚本（CSP 仅允许哈希脚本）。"
    doc += "脚本被禁用时分析方法 A–E 与口径仍可阅读，工作台/证据链需要启用脚本。</p></noscript>"

    doc += f"<script type='application/json' id='supply-workbench-data'>{data_text}</script>"
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
