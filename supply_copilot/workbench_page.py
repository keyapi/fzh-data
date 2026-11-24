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
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:20px;align-items:start}
.board,.detail,.panel{background:var(--white);border:1px solid var(--line);border-radius:4px}
.board{overflow:hidden;min-width:0}
.scroll{overflow:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;font-weight:normal;font-size:10px;color:var(--muted);background:#f8f8f4;
padding:11px 12px;white-space:nowrap;position:sticky;top:0;z-index:1}
td{padding:13px 12px;border-bottom:1px solid #ecece5;vertical-align:top}
tbody tr:last-child td{border:0}
table.rows tbody tr[data-key]{cursor:pointer}
table.rows tbody tr[data-key]:hover td{background:#fafaf6}
.row-select{border:0;background:none;padding:0;text-align:left;color:var(--ink);width:100%;
font-size:12px}
.row-select strong{display:block;line-height:1.6}
.row-select small{display:block;color:var(--muted);font-size:10px;margin-top:3px}
tbody tr.selected td{background:var(--soft)}
tbody tr.selected td:first-child{box-shadow:inset 3px 0 var(--orange)}
.qty{font-family:Georgia,serif;font-size:16px}
.week{display:block;font-size:10px;color:var(--muted);margin-top:3px}
.tablefoot{padding:11px 14px;border-top:1px solid var(--line);font-size:10px;color:var(--muted);
display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.empty{padding:34px 18px;text-align:center;color:var(--muted);font-size:12px}
.detail{overflow:hidden}
.detail-head{padding:18px 20px 14px;border-bottom:1px solid var(--line)}
.detail-head h2{margin:6px 0;font-size:17px;line-height:1.5}
.detail-head .hint{margin:0;color:var(--muted);font-size:11px;line-height:1.7}
.micro{font-size:10px;letter-spacing:1px;color:var(--muted);text-transform:none}
.detail-body{padding:16px 20px}
.l0{font-size:13px;line-height:1.8;margin:0 0 12px}
.l1{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0 14px}
.l1>div{border:1px dashed #cbd8df;border-radius:6px;padding:8px;background:#fbfdfe}
.l1 strong{display:block;font-size:15px;margin-top:3px}
.l1 small{display:block;color:var(--muted);font-size:10px;margin-top:3px;line-height:1.5}
.chain{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:8px;
margin:12px 0}
.chain>div{border:1px dashed #cbd8df;border-radius:6px;padding:7px 8px;background:#fbfdfe}
.chain strong{display:block;font-size:14px;margin-top:2px}
.chain small{display:block;color:var(--muted);font-size:10px;margin-top:2px}
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
.evsec{border-top:1px solid var(--line);padding-top:12px;margin-top:14px}
.evsec h3{font-size:13px;margin-bottom:8px}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:6px 0}
.kv>div{border:1px dashed #cbd8df;border-radius:6px;padding:7px 8px;background:#fbfdfe}
.kv dt{font-size:10px;color:var(--muted)}
.kv dd{margin:2px 0 0;font-weight:bold;font-size:13px;word-break:break-all}
.unk-list{margin:0;padding-left:18px;font-size:11px;line-height:1.9;color:#4a5a66}
.unk-list .unknown{font-style:normal}
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
.detail-close{display:none}
.detail-head .detail-close{float:right;margin-left:8px}
@media (max-width:1279px){
  .workspace{grid-template-columns:1fr}
  .detail{display:none}
  .workspace.detail-open .detail{display:block;position:fixed;inset:0;z-index:45;
    border-radius:0;overflow:auto;padding-bottom:40px}
  .detail-close{display:inline-block}
  .evgrid{grid-template-columns:1fr}
  .evlist{max-height:280px;overflow:auto}
}
@media (max-width:767px){
  main{padding:16px}
  header.site{padding:13px 16px}
  .brand span{display:none}
  .sitemeta{text-align:left}
  .l1{grid-template-columns:1fr}
  table.rows,table.rows tbody,table.rows tr,table.rows td{display:block;width:100%}
  table.rows thead{display:none}
  table.rows tr{border-bottom:1px solid var(--line);padding:6px 0}
  table.rows td{border:0;padding:4px 14px}
  table.rows td[data-label]:before{content:attr(data-label) "：";color:var(--muted);
    font-size:10px}
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

  var state = {
    view: 'workbench', set: 'rec', q: '', action: '',
    flags: {decision: false, supply: false, special: false, pending: false, low: false},
    recKey: null, baseKey: null, evKey: null, evQ: '', review: false
  };
  var storageState = {available: true, message: ''};

  function byId(id) { return document.getElementById(id); }
  function esc(v) { return escapeHtml(v); }
  function unknown() { return '<span class="unknown">未知</span>'; }
  function qty(v) { var t = formatQty(v); return t === null ? unknown() : t; }
  function intq(v) { var t = formatInt(v); return t === null ? unknown() : t; }
  function day(v) { return isBlank(v) ? '' : String(v).slice(0, 10); }
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

  /* ---------------- workbench ---------------- */

  function currentRows() { return state.set === 'rec' ? REC : BASE; }

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
    var selected = key === state.recKey ? ' class="selected"' : '';
    var acts = actionParts(r);
    return '<tr data-key="' + esc(key) + '"' + selected + '>' +
      '<td data-label="商品"><button class="row-select" data-row="' + esc(key) + '">' +
      '<strong>' + esc(r.sku || '—') + '</strong><small>' +
      esc(r.customer || '归属待确认') + ' · ' + esc(r.physical_form || '—') + ' · ' +
      esc(r.uom || '—') + '</small></button></td>' +
      '<td data-label="期间"><span class="week">' + periodShort(r) + '</span></td>' +
      '<td data-label="建议">' + actionBadge(r) +
      (acts.length ? '<small class="hint" style="display:block">' + acts.join(' + ') + '</small>' : '') +
      '</td>' +
      '<td data-label="覆盖">' + qty(r.coverage) + ' 天</td>' +
      '<td data-label="原因">' + (isBlank(r.reason) ? unknown() : esc(r.reason)) + '</td>' +
      '<td data-label="标记">' + flagsHtml(r) + '</td></tr>';
  }

  function baseRowHtml(r) {
    var key = rowKey(r);
    var selected = key === state.baseKey ? ' class="selected"' : '';
    var proposed = proposals().filter(function (p) {
      return p.row_id === r.id && p.status === 'submitted';
    }).length;
    return '<tr data-key="' + esc(key) + '"' + selected + '>' +
      '<td data-label="商品"><button class="row-select" data-row="' + esc(key) + '">' +
      '<strong>' + esc(r.name || r.sku || r.product_id || '—') + '</strong><small>' +
      esc(r.sku || '') + ' · ' + esc(r.physical_form || '—') + ' · ' + esc(r.unit || r.uom || '—') +
      '</small></button></td>' +
      '<td data-label="期间"><span class="week">' + periodShort(r) + '</span></td>' +
      '<td data-label="需求基准"><span class="qty">' + qty(baselineQty(r)) + '</span>' +
      ' <span class="hint">' + esc(r.unit || r.uom || '') + '</span></td>' +
      '<td data-label="提案">' + (proposed
        ? '<span class="rec-badge decision">待模拟审核</span>' : '<span class="hint">—</span>') +
      '</td></tr>';
  }

  function renderTable() {
    var tbody = byId('wb-rows');
    var table = byId('wb-table');
    if (!tbody || !table) return;
    var rows = filtered();
    var total = currentRows().length;
    table.setAttribute('data-set', state.set);
    var head = state.set === 'rec'
      ? '<tr><th>商品 / 客户 / 形态</th><th>期间</th><th>建议</th><th>覆盖</th><th>原因</th><th>标记</th></tr>'
      : '<tr><th>商品 / SKU</th><th>期间</th><th>需求基准</th><th>提案</th></tr>';
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

  function selectRow(key) {
    if (state.set === 'rec') state.recKey = key; else state.baseKey = key;
    renderTable();
    renderDetail();
    var ws = byId('workspace');
    if (ws && window.matchMedia && window.matchMedia('(max-width:1279px)').matches) {
      ws.classList.add('detail-open');
    }
  }

  function gapText(demandKnown, supplyKnown, demand, supply, unit) {
    if (!demandKnown || !supplyKnown) return unknown();
    return intq(Number(supply) - Number(demand)) + (unit ? ' ' + esc(unit) : '');
  }

  function detailShell(title, kicker, hint, body) {
    return '<div class="detail-head">' +
      '<button type="button" class="btn small detail-close" data-close-detail="1">返回列表</button>' +
      '<div class="micro">' + kicker + '</div>' +
      '<h2>' + title + '</h2><p class="hint">' + hint + '</p></div>' +
      '<div class="detail-body">' + body + '</div>';
  }

  function renderDetail() {
    var host = byId('wb-detail');
    if (!host) return;
    if (state.set === 'rec') renderRecDetail(host); else renderBaseDetail(host);
  }

  function renderRecDetail(host) {
    var r = REC_INDEX[state.recKey];
    if (!r) {
      host.innerHTML = '<div class="empty">选择左侧补货建议行查看结论与证据入口。<br>' +
        '建议只读；演示提案只对「需求基准」行开放。</div>';
      return;
    }
    var key = rowKey(r);
    var twin = BASE_INDEX[key];
    var demandKnown = !isBlank(r.forecast);
    var supplyKnown = !isBlank(r.e_qty);
    var acts = actionParts(r);
    var conclusion = [];
    if (!demandKnown && !supplyKnown) {
      conclusion.push('缺证据，暂不能确定缺口');
    } else {
      conclusion.push(actionBadge(r) + (acts.length ? '（' + acts.join(' + ') + '）' : ''));
    }
    if (!isBlank(r.reason)) conclusion.push(esc(r.reason));
    if (flag(r, 'needs_decision')) conclusion.push('需人工拍板');
    if (flag(r, 'low_confidence')) conclusion.push('源模型标记低置信');
    if (flag(r, 'ownership_pending')) conclusion.push('归属待确认');
    var body = '';
    body += '<p class="l0">' + conclusion.join('；') + '。</p>';
    body += '<div class="l1">' +
      '<div><span class="micro">需求（预测中位 q50）</span><strong>' + qty(r.forecast) +
      '</strong><small>' + esc(r.uom || '') + ' · q50/q90/q95 ' + intq(r.q50) + '/' +
      intq(r.q90) + '/' + intq(r.q95) + '</small></div>' +
      '<div><span class="micro">供给（E 按时供给，含 C）</span><strong>' + qty(r.e_qty) +
      '</strong><small>C 当前可发 ' + qty(r.c_qty) + ' · 不含在途</small></div>' +
      '<div><span class="micro">差额（供给 − 需求，页面计算）</span><strong>' +
      gapText(demandKnown, supplyKnown, r.forecast, r.e_qty, r.uom) +
      '</strong><small>只作对照，不是补货量</small></div></div>';
    body += '<div class="note">库存快照：C ' + qty(r.c_qty) + '（快照时点 ' + esc(AS_OF) +
      '）；当前观察：静态页不可得（页面不发起任何请求）。两者分开标注，不用旧值冒充实时。</div>';
    body += '<div class="chain">' +
      '<div><span class="micro">SO 管线</span><strong>' + intq(r.so_open_qty) + '</strong>' +
      '<small>近期 ' + intq(r.so_recent_open_qty) + ' · 历史 ' + intq(r.so_history_open_qty) + '</small></div>' +
      '<div><span class="micro">生产 / DN</span><strong>未接入</strong><small>WIP / DN 未接入</small></div>' +
      '<div><span class="micro">通途 PO</span><strong>未接入</strong><small>DN 后采购入库</small></div>' +
      '<div><span class="micro">CG 抵扣</span><strong>' + intq(valueOfExtra(r, 'CG可调拨抵扣')) +
      '</strong><small>下游缓冲，不可回拨</small></div></div>';
    body += '<p class="mutednote">关联需求基准：' + (twin
      ? esc(twin.id || rowKey(twin)) + ' · 基准数量 ' + qty(baselineQty(twin))
      : '未匹配到唯一基准行（按 SKU×形态×单位对单）；不激活提案表单。') + '</p>';
    body += '<div class="actions">' +
      '<button type="button" class="btn small" data-goto-evidence="' + esc(key) + '">完整证据链 →</button>' +
      '<button type="button" class="btn small ghost" data-next="rec">下一条</button>' +
      '<button type="button" class="btn small ghost detail-close" data-close-detail="1">返回列表</button>' +
      '</div>';
    host.innerHTML = detailShell(
      esc(r.sku || '—'),
      '补货建议 · 只读 / ' + esc(r.customer || '归属待确认'),
      esc(r.physical_form || '—') + ' · ' + esc(r.uom || '—') + ' · 期间 ' + periodShort(r),
      body
    );
    bindDetail(host);
  }

  function renderBaseDetail(host) {
    var r = BASE_INDEX[state.baseKey];
    if (!r) {
      host.innerHTML = '<div class="empty">选择左侧需求基准行，查看明细并补充业务判断。' +
        '<br>提案只存本浏览器，不上传、不审批、不写 EN。</div>';
      return;
    }
    var key = rowKey(r);
    var twin = REC_INDEX[key];
    var demand = baselineQty(r);
    var demandKnown = !isBlank(demand);
    var supplyKnown = !!(twin && !isBlank(twin.e_qty));
    var unit = r.unit || r.uom || '';
    var prov = isBlank(r.baseline_qty) && !isBlank(r.demand_qty)
      ? '字段 demand_qty（本次基准导出未含 baseline_qty）' : '字段 baseline_qty';
    var body = '';
    body += '<p class="l0">本期需求基准 ' +
      (demandKnown ? qty(demand) + ' ' + esc(unit) : '缺证据，暂不能确定') +
      '；' + (supplyKnown ? '对应建议行 E 按时供给 ' + qty(twin.e_qty) : '未关联到建议行，供给未知') +
      '。</p>';
    body += '<div class="l1">' +
      '<div><span class="micro">需求（需求基准）</span><strong>' + qty(demand) +
      '</strong><small>' + esc(unit) + ' · ' + prov + '</small></div>' +
      '<div><span class="micro">供给（关联建议行 E）</span><strong>' +
      (supplyKnown ? qty(twin.e_qty) : unknown()) + '</strong><small>' +
      (twin ? '同键建议行 ' + esc(twin.sku || '') : '未匹配建议行') + '</small></div>' +
      '<div><span class="micro">差额（供给 − 需求，页面计算）</span><strong>' +
      gapText(demandKnown, supplyKnown, demand, twin ? twin.e_qty : null, unit) +
      '</strong><small>只作对照，不是补货量</small></div></div>';
    body += '<div class="note">期间：' + periodShort(r) +
      '。库存快照：C ' + (twin ? qty(twin.c_qty) : unknown()) + '（快照时点 ' + esc(AS_OF) +
      '）；当前观察：静态页不可得。空日期写「待核」，不编造。</div>';
    body += '<p class="mutednote">' + (twin
      ? '对应补货建议：' + esc(twin.action || '观察') + '（' + esc(twin.reason || '无原因字段') + '）'
      : '没有唯一匹配的补货建议行；仍可填写演示提案。') + '</p>';
    body += proposalForm(r, unit, day(r.week || r.start || r.period_start));
    body += '<p class="form-note hint">仅演示需求提案，不修改 USNJ 补货建议，不进入采购。</p>';
    host.innerHTML = detailShell(
      esc(r.name || r.sku || r.product_id || '—'),
      '需求基准 · 可填写演示提案 / ' + esc(r.branch || ''),
      esc(r.sku || '') + ' · ' + esc(r.physical_form || '—') + ' · ' + esc(unit) +
      '<br>期间 ' + periodShort(r),
      body
    );
    bindDetail(host);
    bindProposalForm(r);
  }

  function proposalForm(r, unit, start) {
    var opts = KINDS.map(function (kind) {
      return '<option value="' + kind + '">' + KIND_LABELS[kind] + '</option>';
    }).join('');
    var end = day(r.period_end) || '';
    return '<form id="proposal-form" novalidate>' +
      '<h3 class="form-title">补充你的业务判断</h3>' +
      '<label for="wb-kind">调整方式</label><select id="wb-kind">' + opts + '</select>' +
      '<label for="wb-value" id="wb-value-label">调整数量（可为负数）</label>' +
      '<input id="wb-value" type="number" step="any" placeholder="例如 20 或 -10">' +
      '<div class="hint" id="wb-preview"></div>' +
      '<div class="two">' +
      '<div><label for="wb-start">事件开始</label><input id="wb-start" type="date" value="' + esc(start) + '"></div>' +
      '<div><label for="wb-end">事件结束</label><input id="wb-end" type="date" value="' + esc(end) + '"></div></div>' +
      '<div class="hint">按该预测期提交；日期空着表示「待核」，提交前需填写。</div>' +
      '<label for="wb-event-id">业务事件 ID <span class="req">*</span></label>' +
      '<input id="wb-event-id" placeholder="例如 活动-2026双十一-上海">' +
      '<label for="wb-reason">调整原因 <span class="req">*</span></label>' +
      '<textarea id="wb-reason" placeholder="说明活动、渠道变化或异常，以及数量判断依据"></textarea>' +
      '<label for="wb-evidence">证据或补充说明</label>' +
      '<input id="wb-evidence" placeholder="活动编号或可核对的信息">' +
      '<p class="form-message" id="form-message" aria-live="polite"></p>' +
      '<div class="submitline"><span class="hint">仅写入本浏览器，不上传、不审批、不写 EN。</span>' +
      '<button class="btn accent" id="wb-submit" type="submit">保存演示提案（本浏览器）</button></div>' +
      '</form>';
  }

  function bindDetail(host) {
    Array.prototype.forEach.call(host.querySelectorAll('[data-goto-evidence]'), function (btn) {
      btn.addEventListener('click', function () {
        gotoEvidence(btn.getAttribute('data-goto-evidence'));
      });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-next]'), function (btn) {
      btn.addEventListener('click', function () {
        var rows = filtered();
        if (!rows.length) return;
        var cur = state.set === 'rec' ? state.recKey : state.baseKey;
        var at = rows.findIndex(function (r) { return rowKey(r) === cur; });
        var next = rows[(at + 1) % rows.length];
        selectRow(rowKey(next));
      });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-close-detail]'), function (btn) {
      btn.addEventListener('click', function () {
        var ws = byId('workspace');
        if (ws) ws.classList.remove('detail-open');
      });
    });
  }

  function bindProposalForm(r) {
    var form = byId('proposal-form');
    if (!form) return;
    byId('wb-kind').addEventListener('change', updatePreview);
    byId('wb-value').addEventListener('input', updatePreview);
    form.addEventListener('submit', function (event) { submitProposal(event, r); });
    updatePreview();
    if (!storageState.available) {
      setFormEnabled(false);
      message(storageState.message, true);
    }
  }

  function updatePreview() {
    var kindEl = byId('wb-kind'), valueEl = byId('wb-value'), labelEl = byId('wb-value-label');
    if (!kindEl || !valueEl || !labelEl) return;
    var kind = kindEl.value;
    var r = BASE_INDEX[state.baseKey] || {};
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
      (r.unit || r.uom || '') + '（未包含其他提案）';
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
    renderSummary();
    renderProposals();
    renderTable();
    if (ok) {
      showStorageNotice('');
      var fold = byId('proposals-fold');
      if (fold) fold.open = true;
      message('提案已保存在本浏览器（刷新仍保留；仅演示，不上传、不审批、不写 EN）。');
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
        var unit = r ? (r.unit || r.uom || '') : '';
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

  /* ---------------- evidence chain ---------------- */

  function gotoEvidence(key) {
    state.evKey = key || state.recKey || (REC.length ? rowKey(REC[0]) : null);
    setView('evidence');
  }

  function renderEvidenceList() {
    var tbody = byId('ev-rows');
    if (!tbody) return;
    var q = state.evQ.toLowerCase();
    var rows = REC.filter(function (r) {
      if (!q) return true;
      return [r.sku, r.customer, r.physical_form, r.uom, r.reason]
        .some(function (v) { return String(v === null || v === undefined ? '' : v).toLowerCase().indexOf(q) >= 0; });
    });
    byId('ev-count').textContent = '显示 ' + rows.length + ' / ' + REC.length + ' 条证据';
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
    return lines.filter(function (x) {
      var b = x.date_bucket || (x.transaction_date ? 'unknown' : 'unknown');
      return b === bucket;
    });
  }

  function unknownNotes(r) {
    var notes = [];
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
    if (isBlank(r.so_source_as_of)) {
      notes.push('so_source_as_of 缺失＝SO 取数时点未记录');
    }
    if (isBlank(r.source_hash)) notes.push('source_hash 缺失＝行哈希未记录（无伪链接）');
    if (isBlank(r.source_row)) notes.push('source_row 缺失＝源行号未记录');
    if (!Array.isArray(r.so_lines) || !r.so_lines.length) {
      notes.push('so_lines 为空＝未查到开放 SO 行（真实空集，不等于未知）');
    }
    notes.push('生产 / DN / 通途 PO＝未接入（不是 0）');
    notes.push('当前库存观察＝静态页不可得（connect-src none，无实时请求）');
    var nf = DATA.nonfinite || {};
    var nfKeys = Object.keys(nf);
    if (nfKeys.length) {
      var total = 0;
      nfKeys.forEach(function (k) { total += Number(nf[k]) || 0; });
      notes.push('源快照有 ' + total + ' 个非有限数（NaN/Inf：' + nfKeys.join('、') +
        '），已按未知展示，不补 0');
    }
    return notes;
  }

  function renderEvidencePanel() {
    var host = byId('ev-panel');
    if (!host) return;
    var r = REC_INDEX[state.evKey];
    if (!r) {
      host.innerHTML = '<div class="empty">选择左侧一条建议行，查看逐项证据。</div>';
      return;
    }
    var key = rowKey(r);
    var twin = BASE_INDEX[key];
    var lines = Array.isArray(r.so_lines) ? r.so_lines : [];
    var idx = REC.findIndex(function (x) { return rowKey(x) === key; });
    var html = '<div class="micro">证据链 L2 / L3 · 只读</div>' +
      '<h2>' + esc(r.sku || '—') + '</h2>' +
      '<p class="hint">' + esc(r.customer || '归属待确认') + ' · ' +
      esc(r.physical_form || '—') + ' · ' + esc(r.uom || '—') + '</p>';

    html += '<section class="evsec"><h3>身份与期间</h3>' +
      kv([
        ['SKU', esc(r.sku || '—')],
        ['客户 / 归属', esc(r.customer || '归属待确认')],
        ['形态 / 单位', esc(r.physical_form || '—') + ' · ' + esc(r.uom || '—')],
        ['套件标识 bundle_id', esc(r.bundle_id || '—')],
        ['规范化行键', esc(key)],
        ['期间 period_start — period_end', periodText(r)],
        ['快照时点 as_of', esc(AS_OF)],
        ['快照版本', esc(REC_VERSION || '—')]
      ]) + '</section>';

    html += '<section class="evsec"><h3>需求（预测分位，不加进建议量）</h3>' +
      kv([
        ['预测中位 forecast', qty(r.forecast) + ' ' + esc(r.uom || '')],
        ['q50 / q90 / q95', intq(r.q50) + ' / ' + intq(r.q90) + ' / ' + intq(r.q95)],
        ['模型', esc(r.model || '—')],
        ['字段来源', 'forecast, q50, q90, q95, model']
      ]) + '</section>';

    html += '<section class="evsec"><h3>供给各阶段</h3>' +
      kv([
        ['C 当前可发 c_qty', qty(r.c_qty)],
        ['E 按时供给 e_qty', qty(r.e_qty)],
        ['EN 已发运量', intq(valueOfExtra(r, 'EN已发运量'))],
        ['EN 待发量', intq(valueOfExtra(r, 'EN待发量'))],
        ['PO 追加（去重）', intq(valueOfExtra(r, 'PO追加(去重)'))],
        ['SO 已下', intq(valueOfExtra(r, 'SO已下'))],
        ['CG 抵扣', intq(valueOfExtra(r, 'CG可调拨抵扣'))],
        ['生产 / DN / 通途 PO', '未接入 / 未接入 / 未接入']
      ]) +
      '<p class="mutednote">C 与 E 字段各自带口径；SO 管线不加入建议量，PO 与 SO 不能相加替代。</p>' +
      '</section>';

    html += '<section class="evsec"><h3>SO 三段（近期 / 历史 / 未知）</h3>' +
      kv([
        ['SO 管线合计', intq(r.so_open_qty)],
        ['近期 SO', intq(r.so_recent_open_qty)],
        ['历史开放 SO', intq(r.so_history_open_qty)],
        ['SO 取数时点', esc(r.so_source_as_of || '未记录')]
      ]);
    if (!lines.length) {
      html += '<p class="mutednote">未查到开放 SO 行（空集，不是未知）。</p>';
    } else {
      [['recent', '近期 SO'], ['history', '历史开放 SO'], ['unknown', '创建日未知 SO']]
        .forEach(function (pair) {
          var items = soBucket(lines, pair[0]);
          if (!items.length) return;
          html += '<details class="raw"><summary>' + pair[1] + '（' + items.length +
            ' 行，不加入建议量）</summary>' + soTable(items) + '</details>';
        });
    }
    html += '</section>';

    html += '<section class="evsec"><h3>库存快照与当前观察</h3>' +
      kv([
        ['快照 C（时点 ' + esc(AS_OF) + '）', qty(r.c_qty)],
        ['快照 E', qty(r.e_qty)],
        ['当前库存观察', '静态页不可得'],
        ['可用性拆开说', '服务=静态 / 库存=快照 / 建议=只读']
      ]) + '</section>';

    html += '<section class="evsec"><h3>来源与哈希</h3>' +
      kv([
        ['source_row', esc(r.source_row || '未记录')],
        ['source_hash', esc(r.source_hash || '未记录')],
        ['数据来源文件', esc(DATA.version || '—')],
        ['来源备注', esc(r.source_note || '未记录')]
      ]) +
      '<p class="mutednote">文件不存在 / 无权 / 未记录行号各有状态；本快照未写入行哈希，不生成伪链接。</p>' +
      '</section>';

    html += '<section class="evsec"><h3>未知与未接入原因</h3><ul class="unk-list">' +
      unknownNotes(r).map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('') +
      '</ul></section>';

    html += '<section class="evsec"><h3>对单与抽查</h3>' +
      kv([
        ['建议行号', (idx + 1) + ' / ' + REC.length],
        ['关联需求基准', twin ? esc(twin.id || rowKey(twin)) : '仅建议（无基准行）'],
        ['对单键', 'SKU × 形态 × 单位'],
        ['整体对账', '唯一匹配 ' + (RECON.unique || 0) + ' · 仅建议 ' +
          ((RECON.only_rec || []).length) + ' · 仅基准 ' +
          ((RECON.only_base || []).length) + ' · 歧义 ' + ((RECON.ambiguous || []).length)]
      ]) +
      '<label class="check" style="margin-top:8px"><input type="checkbox" id="ev-check">' +
      ' 本次查看已核对（不持久化、不代表已批准）</label>' +
      '<div class="evnav">' +
      '<button type="button" class="btn small" data-ev-prev="1">上一条</button>' +
      '<button type="button" class="btn small" data-ev-next="1">下一条</button>' +
      '<button type="button" class="btn small" data-goto-workbench="1">返回工作台</button>' +
      '</div></section>';

    host.innerHTML = html;
    Array.prototype.forEach.call(host.querySelectorAll('[data-ev-prev]'), function (btn) {
      btn.addEventListener('click', function () { stepEvidence(-1); });
    });
    Array.prototype.forEach.call(host.querySelectorAll('[data-ev-next]'), function (btn) {
      btn.addEventListener('click', function () { stepEvidence(1); });
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

  /* ---------------- navigation ---------------- */

  function setView(view) {
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
    if (view === 'workbench') renderTable();
    if (window.scrollTo) window.scrollTo(0, 0);
  }

  function bindControls() {
    Array.prototype.forEach.call(document.querySelectorAll('nav.topnav button'), function (b) {
      b.addEventListener('click', function () { setView(b.getAttribute('data-view')); });
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-set]'), function (b) {
      b.addEventListener('click', function () {
        state.set = b.getAttribute('data-set');
        state.q = '';
        state.action = '';
        Object.keys(state.flags).forEach(function (k) { state.flags[k] = false; });
        var search = byId('wb-search');
        if (search) search.value = '';
        var actionSel = byId('wb-action');
        if (actionSel) actionSel.value = '';
        Array.prototype.forEach.call(document.querySelectorAll('[data-set]'), function (x) {
          x.classList.toggle('active', x === b);
          x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
        });
        Array.prototype.forEach.call(document.querySelectorAll('[data-flag]'), function (x) {
          x.checked = false;
        });
        var recOnly = state.set === 'rec';
        var actionWrap = byId('wb-action-wrap');
        if (actionWrap) actionWrap.hidden = !recOnly;
        renderTable();
        renderDetail();
      });
    });
    var search = byId('wb-search');
    if (search) {
      search.addEventListener('input', function () {
        state.q = search.value.trim();
        renderTable();
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
        renderTable();
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll('[data-flag]'), function (cb) {
      cb.addEventListener('change', function () {
        state.flags[cb.getAttribute('data-flag')] = cb.checked;
        renderTable();
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
        renderTable();
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
    Array.prototype.forEach.call(document.querySelectorAll('[data-view]'), function (b) {
      b.addEventListener('click', function () { state.review = b.getAttribute('data-review') === '1'; });
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
      state.recKey = REC.length ? rowKey(REC[0]) : null;
      state.evKey = state.recKey;
      state.baseKey = BASE.length ? rowKey(BASE[0]) : null;
      if (!state.baseKey) baseSwitchFallback();
      renderSummary();
      renderTable();
      renderDetail();
      renderEvidenceList();
      renderEvidencePanel();
      renderProposals();
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
    doc += "<div class='viewhead'><div><div class='eyebrow'>WORKBENCH</div>"
    doc += "<h1>工作台</h1><p class='sub'>默认看补货建议（只读）。切到需求基准才允许填写演示提案。"
    doc += "明细在右侧，不占主表。</p></div>"
    doc += f"<div class='micro' id='collab-summary'>D5 整期需求基准 {len(baseline_rows)} 行 · "
    doc += f"USNJ 补货建议 {len(rows)} 行</div></div>"
    doc += "<div class='wbtop'><div class='wbcount'>"
    doc += "<div class='setswitch' role='group' aria-label='数据视图'>"
    doc += "<button class='active' type='button' data-set='rec' aria-pressed='true'>补货建议（只读）</button>"
    doc += "<button type='button' data-set='base' aria-pressed='false'>需求基准（可演示提案）</button></div>"
    doc += "<span id='wb-count'>—</span><button class='btn small ghost' type='button' id='wb-clear'>清除筛选</button>"
    doc += "</div>"
    doc += "<div class='wbfilters'>"
    doc += "<input id='wb-search' type='search' placeholder='搜索 SKU / 客户 / 原因 / 模型' autocomplete='off' aria-label='搜索'>"
    doc += "<select id='wb-action' aria-label='筛选动作'><option value=''>全部动作</option></select>"
    doc += "<label class='check'><input type='checkbox' data-flag='decision'>需拍板</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='supply'>缺供给</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='special'>特殊品</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='pending'>归属待确认</label>"
    doc += "<label class='check'><input type='checkbox' data-flag='low'>低置信</label>"
    doc += "</div></div>"
    doc += "<div class='workspace' id='workspace'>"
    doc += "<section class='board' aria-label='列表'><div class='scroll'>"
    doc += "<table class='rows' id='wb-table' data-set='rec'><thead><tr><th>商品 / 客户 / 形态</th>"
    doc += "<th>期间</th><th>建议</th><th>覆盖</th><th>原因</th><th>标记</th></tr></thead>"
    doc += "<tbody id='wb-rows'><tr><td colspan='6' class='empty'>正在载入…</td></tr></tbody></table>"
    doc += "</div><div class='tablefoot'><span id='wb-foot'></span><span id='wb-version'></span></div></section>"
    doc += "<aside class='detail' id='wb-detail' aria-label='详情'>"
    doc += "<div class='empty'>选择左侧一行查看结论与证据入口。</div></aside></div>"
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
