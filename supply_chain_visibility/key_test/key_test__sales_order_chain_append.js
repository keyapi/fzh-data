// ─────────────────────────────────────────────────────────────────────────
// 「供应链链条」内嵌 SO 表单 —— 追加到 key_test/public/js/sales_order.js **末尾**
//
// 形态：一行一摘要 + 行内展开(accordion) + 弹窗(小图标)做深度。
//   主表列：物料 | 客户码 | 订单量 | 已发 | 未发 | 交期 | 阶段 | 生产计划 | 生产链条 | 销售出库
//   「生产链条」= 工单 → 菲号(默认展开) → 逐工序 Job Card；「销售出库」= DN 明细(可能一对多/含退货)。
//   两列各自独立展开。层 级依据：菲号=一批(组)皮壳/半成品实物流身份证，贯穿工单全部工序。
// 状态/选择值一律过 `__()` 取 ERPNext 翻译。容器用 frm.dashboard.parent。
// ─────────────────────────────────────────────────────────────────────────
frappe.ui.form.on('Sales Order', {
    refresh: function (frm) {
        if (frm.is_new()) return;
        const $dash = frm.dashboard.parent;
        if (!$dash.find('.so-chain-summary').length) {
            frm.dashboard.add_section('<div class="so-chain-summary"></div>', __('供应链链条'));
        }
        const $box = $dash.find('.so-chain-summary');
        $box.html('<div class="text-muted">加载中…</div>');
        frappe.call({
            method: 'key_test.so_chain.get_so_chain',
            args: { sales_order: frm.doc.name },
            callback: function (r) {
                if (!r || !r.message) { $box.html('<div class="text-muted">无数据</div>'); return; }
                so_chain_render($box, r.message);
            }
        });
    }
});

const SO_CHAIN_COLS = 10;
function so_chain_esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }
function so_chain_num(v) { const f = Number(v || 0); return (Math.round(f * 1000) / 1000).toString(); }
function so_chain_t(s) { return so_chain_esc(s == null ? '' : __(String(s))); }
function so_chain_link(doctype, name, label) {
    if (!name) return so_chain_esc(label || '');
    let slug;
    try { slug = frappe.router.slug(doctype); }
    catch (e) { slug = doctype.toLowerCase().replace(/ /g, '-'); }
    return '<a href="/app/' + slug + '/' + encodeURIComponent(name) + '" target="_blank">'
         + so_chain_esc(label || name) + '</a>';
}
function so_chain_item_type(c) {
    c = c || '';
    if (c.indexOf('PK#') === 0) return '（皮壳）';
    if (c.indexOf('ND#') === 0 || c.indexOf('DKND#') === 0) return '（内胆）';
    if (/^KS/.test(c)) return '（成品）';
    return '';
}

function so_chain_render($box, data) {
    let tOpenQty = 0;
    const rows = (data.lines || []).map(function (l, idx) {
        tOpenQty += Number(l.open_qty || 0);
        const plans = (l.plans || []).map(function (p) {
            return so_chain_link('Production Plan', p.pp, p.pp + (p.planned_qty ? ' (' + so_chain_num(p.planned_qty) + ')' : ''));
        }).join(', ') || '-';
        // 生产链条摘要
        const pg = l.prog;
        const progTxt = pg ? (pg.min === pg.max ? pg.max + '/' + pg.total : pg.min + '–' + pg.max + '/' + pg.total) : '';
        const prodSummary = (l.wo_count ? l.wo_count + ' 工单' : '无工单') + ' · ' + (l.tn_count ? l.tn_count + ' 菲号' : '0 菲号')
            + (progTxt ? '　<span class="text-muted" title="必经工序完成数(最慢–最快菲号)/总数，已排除返工分支">工序 ' + progTxt + '</span>' : '');
        const forgot = (l.forgot_complete || []);
        const forgotBadge = forgot.length
            ? ' <span class="indicator-pill yellow" title="成品工单未完工，但同行的皮壳/内胆工单已全部完成：' + so_chain_esc(forgot.join(', ')) + '">忘点完工?</span>'
            : '';
        const prodCell = l.wo_count
            ? '<a href="#" class="so-chain-toggle" data-i="' + idx + '" data-w="prod" style="color:#0d7a3f"><b>' + prodSummary + '</b> <span class="so-chain-caret">▸</span></a>'
              + ' <a href="#" class="so-chain-dialog" data-i="' + idx + '" title="弹窗看大图" style="text-decoration:none">⤢</a>' + forgotBadge
            : prodSummary + forgotBadge;
        // 出库摘要（列名简称「出库」）
        const dns = l.dns || [];
        const shipSum = dns.filter(function (d) { return d.docstatus === 1 && !d.is_return; }).reduce(function (a, d) { return a + Number(d.qty || 0); }, 0);
        const retSum = dns.filter(function (d) { return d.docstatus === 1 && d.is_return; }).reduce(function (a, d) { return a + Number(d.qty || 0); }, 0);
        const dnSummary = dns.length
            ? dns.length + ' 单 · 已发 ' + so_chain_num(shipSum) + (retSum ? '（退 ' + so_chain_num(-retSum) + '）' : '')
            : '无';
        const dnCell = dns.length
            ? '<a href="#" class="so-chain-toggle" data-i="' + idx + '" data-w="dn" style="color:#0a6ed1"><b>' + dnSummary + '</b> <span class="so-chain-caret">▸</span></a>'
            : dnSummary;
        const od2 = Number(l.overdue_days || 0);
        const dd = od2 > 0 ? '<span class="text-danger" title="已过交付日期 ' + od2 + ' 天">' + so_chain_esc(l.delivery_date) + ' (超' + od2 + '天)</span>'
                           : so_chain_esc(l.delivery_date || '-');
        const stageColor = { 0: 'gray', 1: 'orange', 2: 'blue', 3: 'green' }[l.stage] || 'gray';
        return '<tr data-idx="' + idx + '">'
            + '<td>' + so_chain_link('Item', l.item_code, l.item_code) + '</td>'
            + '<td>' + so_chain_esc(l.customer_item_code) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.qty) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.delivered) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.open_qty) + '</td>'
            + '<td>' + dd + '</td>'
            + '<td><span class="indicator-pill ' + stageColor + '">' + l.stage + ' ' + so_chain_esc(l.substate) + '</span></td>'
            + '<td>' + plans + '</td>'
            + '<td>' + prodCell + '</td>'
            + '<td>' + dnCell + '</td>'
            + '</tr>';
    }).join('');
    const html = '<div style="overflow:auto">'
        + '<table class="table table-bordered" style="margin:0">'
        + '<thead><tr><th>订单行物料</th><th>客户物料号</th><th>订单量</th><th>已发</th><th>未发</th>'
        + '<th>交期</th><th>阶段</th><th>生产计划</th><th>生产链条</th><th>出库</th></tr></thead>'
        + '<tbody>' + rows + '</tbody>'
        + '<tfoot><tr><th colspan="4" style="text-align:right">未发合计</th>'
        + '<th style="text-align:right">' + so_chain_num(tOpenQty) + '</th><th colspan="5"></th></tr></tfoot></table>'
        + '<div class="text-muted" style="margin-top:4px;font-size:11px">'
        + '点绿色「生产链条」＝展开 工单→菲号→工序卡；点蓝色「出库」＝展开 出库单明细。两列各自独立展开；⤢ 弹窗看大图。'
        + '完成量取第一道工序(不跨工序求和)；已发按出库单净额(含退货抵扣)。</div></div>';
    $box.html(html);

    $box.find('.so-chain-toggle').on('click', function (e) {
        e.preventDefault();
        so_chain_toggle($box, $(this).data('i'), $(this).data('w'), data.lines[$(this).data('i')]);
    });
    // 标签切换（一个容器内切 生产链条 / 出库）
    $box.off('click.sochaintab').on('click.sochaintab', '.so-chain-tab', function () {
        const $wrap = $(this).closest('.so-chain-tabwrap');
        const $inline = $wrap.closest('tr.so-chain-inline');
        const idx = parseInt($inline.attr('data-key'), 10);
        const t = $(this).data('t');
        const line = data.lines[idx];
        $wrap.html(so_chain_tabs_html(t) + '<div class="so-chain-tabbody">' + so_chain_panel_html(line, t) + '</div>');
        $inline.attr('data-tab', t);
        so_chain_set_caret($box.find('tr[data-idx="' + idx + '"]'), t);
    });
    $box.find('.so-chain-dialog').on('click', function (e) {
        e.preventDefault();
        so_chain_show_detail(data.lines[$(this).data('i')], data.sales_order);
    });
}

// 单个标签的内容面板（左侧色条 + 标题，明显区别于普通子表）
function so_chain_panel_html(line, which) {
    const accent = which === 'dn' ? '#0a6ed1' : '#0d7a3f';
    const inner = which === 'dn' ? so_chain_dn_html(line) : so_chain_tree_html(line);
    return '<div style="border-left:4px solid ' + accent + ';background:#f8f9fa;border-radius:0 6px 6px 0;padding:8px 12px">'
        + inner + '</div>';
}
// 标签栏（生产链条=绿 / 出库=蓝）
function so_chain_tabs_html(active) {
    const mk = function (t, label, color) {
        const on = t === active;
        return '<button class="so-chain-tab" data-t="' + t + '" style="cursor:pointer;border:none;'
            + 'border-bottom:2px solid ' + (on ? color : 'transparent') + ';background:none;'
            + 'color:' + (on ? color : 'var(--text-muted)') + ';font-weight:' + (on ? '600' : '400') + ';'
            + 'padding:4px 12px;font-size:13px">' + label + '</button>';
    };
    return '<div style="border-bottom:1px solid var(--border-color);margin-bottom:6px">'
        + mk('prod', '生产链条', '#0d7a3f') + mk('dn', '出库', '#0a6ed1') + '</div>';
}
function so_chain_set_caret($row, which) {
    $row.find('.so-chain-caret').text('▸');
    $row.find('.so-chain-toggle[data-w="' + which + '"] .so-chain-caret').text('▾');
}

// 同一行只放**一个**展开容器；点「生产链条」「出库」任一 → 打开容器并切到对应标签
function so_chain_toggle($box, idx, which, line) {
    const $row = $box.find('tr[data-idx="' + idx + '"]');
    const $ex = $box.find('tr.so-chain-inline[data-key="' + idx + '"]');
    if ($ex.length && $ex.attr('data-tab') === which) {   // 同一列再点 → 收起
        $ex.remove(); $row.find('.so-chain-caret').text('▸'); return;
    }
    if ($ex.length) { $ex.remove(); }
    $row.after('<tr class="so-chain-inline" data-key="' + idx + '" data-tab="' + which + '">'
        + '<td colspan="' + SO_CHAIN_COLS + '" style="background:var(--fg-color);padding:6px 8px">'
        + '<div class="so-chain-tabwrap">' + so_chain_tabs_html(which)
        + '<div class="so-chain-tabbody">' + so_chain_panel_html(line, which) + '</div></div></td></tr>');
    so_chain_set_caret($row, which);
}

// 生产链条：工单 → 菲号(默认展开) → 逐工序 Job Card
function so_chain_tree_html(line) {
    if (!line.work_orders || !line.work_orders.length) return '<div class="text-muted">无工单</div>';
    const forgot = line.forgot_complete || [];
    let h = '<div style="padding:2px 4px">';
    line.work_orders.forEach(function (w) {
        const tns = w.tracking_numbers || [];
        const isForgot = forgot.indexOf(w.wo) >= 0;
        h += '<div style="border:1px solid ' + (isForgot ? '#e6b800' : 'var(--border-color)') + ';'
           + (isForgot ? 'background:#fff9e6;' : '') + 'border-radius:6px;padding:8px;margin:6px 0">';
        h += '<div><b>' + so_chain_link('Work Order', w.wo, w.wo) + '</b>'
           + (w.item_code ? '　' + so_chain_link('Item', w.item_code, w.item_code) + so_chain_item_type(w.item_code) : '')
           + (isForgot ? ' <span class="indicator-pill yellow" title="成品工单未完工，但同行的皮壳/内胆已全部完成 —— 疑似忘了点完工">忘点完工?</span>' : '')
           + '　工单量 ' + so_chain_num(w.qty) + '　完成 ' + so_chain_num(w.done)
           + '　头部状态 ' + so_chain_t(w.status)
           + (w.produced_head ? '（已产 ' + so_chain_num(w.produced_head) + '）' : '')
           + (w.ops_total ? '　工序 ' + w.ops_done + '/' + w.ops_total : '')
           + (w.last_end ? '　最后报工 ' + so_chain_esc(w.last_end) : '') + '</div>';
        tns.forEach(function (t) { h += so_chain_tn_html(t, w); });
        if (w.unassigned && w.unassigned.length) {
            h += '<div class="text-muted" style="margin-top:4px">未绑定菲号的报工 ' + w.unassigned.length + ' 条</div>'
               + '<table class="table table-bordered" style="margin:4px 0;font-size:12px">'
               + '<thead><tr><th>工序</th><th>工序卡</th><th>状态</th><th>数量</th><th>完工时间</th></tr></thead><tbody>';
            w.unassigned.forEach(function (u) {
                h += '<tr><td>' + so_chain_t(u.operation) + '</td><td>' + so_chain_link('Job Card', u.jc, u.jc) + '</td>'
                   + '<td>' + so_chain_t(u.status) + '</td><td style="text-align:right">' + so_chain_num(u.qty) + '</td>'
                   + '<td>' + so_chain_esc(u.end) + '</td></tr>';
            });
            h += '</tbody></table>';
        }
        if (!tns.length && !(w.unassigned && w.unassigned.length)) {
            h += '<div class="text-muted" style="margin-top:4px">无菲号（未开料）</div>';
        }
        h += '</div>';
    });
    return h + '</div>';
}

function so_chain_tn_html(t, w) {
    let h = '<details open style="margin:4px 0;border-left:3px solid var(--border-color);padding-left:8px">'
        + '<summary style="cursor:pointer"><b>菲号 ' + so_chain_link('Tracking Number', t.tn, t.tn) + '</b>'
        + '　数量 ' + so_chain_num(t.qty)
        + (t.ops_total ? '　必经工序 ' + (t.ops_done || 0) + '/' + t.ops_total : '')
        + (t.iwo ? '　开料 ' + so_chain_link('Initial Work Order', t.iwo, t.iwo) : '') + '</summary>';
    if (t.steps && t.steps.length) {
        h += '<table class="table table-bordered" style="margin:4px 0;font-size:12px">'
           + '<thead><tr><th>工序</th><th>序</th><th>工序卡</th><th>状态</th><th>数量</th><th>完工时间</th></tr></thead><tbody>';
        t.steps.forEach(function (s) {
            h += '<tr' + (s.corrective ? ' style="color:var(--text-muted)"' : '') + '>'
               + '<td>' + so_chain_t(s.operation) + (s.corrective ? ' <span class="text-muted">(返工分支)</span>' : '') + '</td>'
               + '<td>' + so_chain_esc(s.seq) + '</td>'
               + '<td>' + so_chain_link('Job Card', s.jc, s.jc) + '</td><td>' + so_chain_t(s.status) + '</td>'
               + '<td style="text-align:right">' + so_chain_num(s.qty) + '</td><td>' + so_chain_esc(s.end) + '</td></tr>';
        });
        h += '</tbody></table>';
    } else {
        h += '<div class="text-muted">该菲号暂无工序卡</div>';
    }
    if (t.fgw && t.fgw !== w.wo) {
        h += '<div class="text-muted" style="font-size:11px">成品工单：' + so_chain_link('Work Order', t.fgw, t.fgw) + '</div>';
    }
    return h + '</details>';
}

// 销售出库：DN 明细（一对多 / 含退货）
function so_chain_dn_html(line) {
    const dns = line.dns || [];
    if (!dns.length) return '<div class="text-muted">无销售出库</div>';
    let h = '<table class="table table-bordered" style="margin:4px 0;font-size:12px">'
        + '<thead><tr><th>出库单</th><th>日期</th><th>状态</th><th>数量</th><th>类型</th></tr></thead><tbody>';
    dns.forEach(function (d) {
        const ship = (d.docstatus === 1) && !d.is_return;
        const qtyTxt = (d.is_return ? '<span class="text-danger">' + so_chain_num(d.qty) + '</span>' : so_chain_num(d.qty));
        h += '<tr>'
           + '<td>' + so_chain_link('Delivery Note', d.dn, d.dn) + '</td>'
           + '<td>' + so_chain_esc(d.date) + '</td>'
           + '<td>' + so_chain_t(d.status) + (d.docstatus === 0 ? ' <span class="text-muted">(草稿)</span>' : '') + '</td>'
           + '<td style="text-align:right">' + qtyTxt + '</td>'
           + '<td>' + (d.is_return ? '退货(抵扣)' : (ship ? '出库' : '—')) + '</td></tr>';
    });
    h += '</tbody></table>';
    return '<div style="padding:2px 4px">' + h + '</div>';
}

function so_chain_show_detail(line, so) {
    const head = '<div style="margin-bottom:6px"><b>' + so_chain_link('Item', line.item_code, line.item_code) + '</b>'
        + '　订单 ' + so_chain_num(line.qty) + '　已发 ' + so_chain_num(line.delivered)
        + '　未发 ' + so_chain_num(line.open_qty) + '　交期 ' + so_chain_esc(line.delivery_date || '-')
        + (Number(line.overdue_days) > 0 ? ' <span class="text-danger">(超 ' + line.overdue_days + ' 天)</span>' : '')
        + '　' + line.stage + ' ' + so_chain_esc(line.substate)
        + (line.customer_item_code ? '　客户码 ' + so_chain_esc(line.customer_item_code) : '') + '</div>';
    const plans = (line.plans && line.plans.length)
        ? '<div style="margin:6px 0"><b>生产计划</b>：' + line.plans.map(function (p) {
            return so_chain_link('Production Plan', p.pp, p.pp) + (p.pending_qty ? '（待产 ' + so_chain_num(p.pending_qty) + '）' : '');
          }).join('、') + '</div>'
        : '';
    const d = new frappe.ui.Dialog({
        title: __('链条明细：') + so + ' / ' + (line.item_name || line.item_code),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'html' }],
    });
    d.fields_dict.html.$wrapper.html('<div style="max-height:72vh;overflow:auto">'
        + head + plans
        + '<div style="margin-top:8px"><b>生产链条</b>' + so_chain_tree_html(line) + '</div>'
        + '<div style="margin-top:8px"><b>销售出库</b>' + so_chain_dn_html(line) + '</div>'
        + '</div>');
    d.show();
}
