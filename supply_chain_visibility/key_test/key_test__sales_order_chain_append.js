// ─────────────────────────────────────────────────────────────────────────
// 「供应链链条」内嵌 SO 表单 —— 追加到 key_test/public/js/sales_order.js **末尾**
//
// 形态（列头即标签）：
//   主表列：物料 | 客户码 | 订单量 | 已发 | 未发 | 交期 | 阶段 | 生产链条 | 出库
//   点「生产链条」→ 该列**下方**展开一个**绿色标题框**(标题就是列名)，框住 生产计划 + 工单→菲号→工序卡；
//   点「出库」→ 蓝色标题框，框住出库明细。同一行**只一个框**，点另一列即切换到它（点同一列收起）。
//   两列都有 ⤢（弹窗一次装两块）。
// 层级依据：菲号=一批(组)皮壳/半成品实物流身份证，贯穿工单全部工序。状态值过 __() 翻译。
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

const SO_CHAIN_PROD = '#0d7a3f';   // 生产 主色
const SO_CHAIN_DN = '#0a6ed1';     // 出库 主色
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
const SO_CHAIN_DEF_COLS = [
    { k: 'item', label: '订单行物料', w: 0 },      // 0 = 弹性列：吸收剩余宽度（多看物料名）
    { k: 'code', label: '客户物料号', w: 115 },
    { k: 'qty', label: '订单量', w: 54 },
    { k: 'produced', label: '已生产', w: 54 },
    { k: 'shipped', label: '已发', w: 54 },
    { k: 'deliv', label: '交期', w: 96 },
    { k: 'stage', label: '阶段', w: 106 },
    { k: 'prod', label: '生产', w: 142 },
    { k: 'dn', label: '出库', w: 106 }
];
const SO_CHAIN_COLS = SO_CHAIN_DEF_COLS.length;
function so_chain_widths() {
    const w = {};
    SO_CHAIN_DEF_COLS.forEach(function (c) { w[c.k] = c.w; });
    try {
        const saved = JSON.parse(localStorage.getItem('so_chain_colw') || '{}');
        Object.keys(saved).forEach(function (k) { if (k in w && saved[k] > 20) w[k] = saved[k]; });
    } catch (e) { }
    return w;
}
// 表头右缘拖动调整列宽；松手写入 localStorage（下次打开自动恢复）
function so_chain_make_resizable($box, widths) {
    $box.find('.so-chain-grip').each(function () {
        const key = $(this).attr('data-k');
        $(this).on('mousedown', function (e) {
            e.preventDefault(); e.stopPropagation();
            const startX = e.pageX;
            const startW = widths[key] || 100;
            const $col = $box.find('col[data-k="' + key + '"]');
            const move = function (ev) {
                const w = Math.max(50, Math.round(startW + (ev.pageX - startX)));
                widths[key] = w;
                $col.attr('style', 'width:' + w + 'px');
            };
            const up = function () {
                $(document).off('mousemove', move).off('mouseup', up);
                try { localStorage.setItem('so_chain_colw', JSON.stringify(widths)); } catch (err) { }
            };
            $(document).on('mousemove', move).on('mouseup', up);
        });
    });
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
        // 生产链条摘要（文本 = 展开框标题）
        const prodSummary = so_chain_summary_text(l, 'prod');
        const forgot = (l.forgot_complete || []);
        const forgotBadge = forgot.length
            ? ' <span class="indicator-pill yellow" title="成品工单未完工，但同行的皮壳/内胆工单已全部完成：' + so_chain_esc(forgot.join(', ')) + '">忘点完工?</span>'
            : '';
        const dialogIcon = function (i) { return '<a href="#" class="so-chain-dialog" data-i="' + i + '" title="弹窗看全图(生产+出库)" style="text-decoration:none">⤢</a>'; };
        const prodCell = l.wo_count
            ? '<a href="#" class="so-chain-toggle" data-i="' + idx + '" data-w="prod" style="color:' + SO_CHAIN_PROD + '"><b>' + prodSummary + '</b> <span class="so-chain-caret">▸</span></a>'
              + ' ' + dialogIcon(idx) + forgotBadge
            : prodSummary + forgotBadge;
        // 出库摘要（文本 = 展开框标题）
        const dns = l.dns || [];
        const dnSummary = so_chain_summary_text(l, 'dn');
        const dnCell = dns.length
            ? '<a href="#" class="so-chain-toggle" data-i="' + idx + '" data-w="dn" style="color:' + SO_CHAIN_DN + '"><b>' + dnSummary + '</b> <span class="so-chain-caret">▸</span></a> ' + dialogIcon(idx)
            : dnSummary;
        const od2 = Number(l.overdue_days || 0);
        const dd = od2 > 0 ? '<span class="text-danger" title="已过交付日期 ' + od2 + ' 天">' + so_chain_esc(l.delivery_date) + ' 超' + od2 + '天</span>'
                           : so_chain_esc(l.delivery_date || '-');
        const stageColor = { 0: 'gray', 1: 'orange', 2: 'blue', 3: 'green' }[l.stage] || 'gray';
        const codeCell = '<div style="max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'
            + 'font-size:12px;line-height:1.1" title="' + so_chain_esc(l.item_code) + '">'
            + so_chain_link('Item', l.item_code, l.item_code) + '</div>'
            + (l.item_name ? '<div class="text-muted" style="max-width:100%;overflow:hidden;text-overflow:ellipsis;'
                + 'white-space:nowrap;font-size:11px;line-height:1.1" title="' + so_chain_esc(l.item_name) + '">'
                + so_chain_esc(l.item_name) + '</div>' : '');
        return '<tr data-idx="' + idx + '">'
            + '<td style="white-space:nowrap;padding:3px 8px;overflow:hidden">' + codeCell + '</td>'
            + '<td style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="' + so_chain_esc(l.customer_item_code) + '">' + so_chain_esc(l.customer_item_code) + '</td>'
            + '<td style="text-align:right;white-space:nowrap">' + so_chain_num(l.qty) + '</td>'
            + '<td style="text-align:right;white-space:nowrap">' + so_chain_num(l.produced) + '</td>'
            + '<td style="text-align:right;white-space:nowrap">' + so_chain_num(l.delivered) + '</td>'
            + '<td style="white-space:nowrap;overflow:hidden">' + dd + '</td>'
            + '<td style="white-space:nowrap;overflow:hidden"><span class="indicator-pill ' + stageColor + '">' + l.stage + ' ' + so_chain_esc(l.substate) + '</span></td>'
            + '<td class="so-chain-cell" style="white-space:nowrap;overflow:hidden">' + prodCell + '</td>'
            + '<td class="so-chain-cell" style="white-space:nowrap;overflow:hidden">' + dnCell + '</td>'
            + '</tr>';
    }).join('');
    const W = so_chain_widths();
    const cols = SO_CHAIN_DEF_COLS.map(function (c) {
        const w = W[c.k];
        return '<col data-k="' + c.k + '"' + (w ? ' style="width:' + w + 'px"' : '') + '>';
    }).join('');
    const ths = SO_CHAIN_DEF_COLS.map(function (c) {
        return '<th style="white-space:nowrap;position:relative;overflow:hidden">' + c.label
            + '<span class="so-chain-grip" data-k="' + c.k + '" title="拖动调整列宽(自动记忆)" '
            + 'style="position:absolute;top:0;right:0;width:6px;height:100%;cursor:col-resize"></span></th>';
    }).join('');
    const html = '<div style="overflow:auto">'
        + '<table class="table table-bordered" style="margin:0;width:100%;table-layout:fixed;font-size:12px">'
        + '<colgroup>' + cols + '</colgroup>'
        + '<thead><tr>' + ths + '</tr></thead>'
        + '<tbody>' + rows + '</tbody></table>'
        + '<div class="text-muted" style="margin-top:4px;font-size:11px">'
        + '未发合计 ' + so_chain_num(tOpenQty) + '　·　列宽可拖动表头右缘调整(自动记忆)。'
        + '点「生产」＝展开 生产计划+工单→菲号→工序卡；点「出库」＝展开 出库单明细；同区切换。⤢ 弹窗看全图。'
        + '已生产=本物料工单已产之和；已发按出库单净额(含退货抵扣)。</div></div>';
    $box.html(html);
    so_chain_make_resizable($box, W);

    $box.find('.so-chain-toggle').on('click', function (e) {
        e.preventDefault();
        so_chain_toggle($box, $(this).data('i'), $(this).data('w'), data.lines[$(this).data('i')]);
    });
    $box.find('.so-chain-dialog').on('click', function (e) {
        e.preventDefault();
        so_chain_show_detail(data.lines[$(this).data('i')], data.sales_order);
    });
}

function so_chain_set_caret($box, idx, which) {
    const $row = $box.find('tr[data-idx="' + idx + '"]');
    $row.find('.so-chain-caret').text('▸');
    $row.find('.so-chain-toggle[data-w="' + which + '"] .so-chain-caret').text('▾');
}

// 摘要文本（列里显示的、也是展开框的**标题**）
function so_chain_summary_text(l, which) {
    if (which === 'dn') {
        const dns = l.dns || [];
        if (!dns.length) return '无出库';
        const ship = dns.filter(function (d) { return d.docstatus === 1 && !d.is_return; }).reduce(function (a, d) { return a + Number(d.qty || 0); }, 0);
        const ret = dns.filter(function (d) { return d.docstatus === 1 && d.is_return; }).reduce(function (a, d) { return a + Number(d.qty || 0); }, 0);
        return dns.length + '单·已发' + so_chain_num(ship) + (ret ? '·退' + so_chain_num(-ret) : '');
    }
    const pg = l.prog;
    const progTxt = pg ? (pg.min === pg.max ? pg.max + '/' + pg.total : pg.min + '–' + pg.max + '/' + pg.total) : '';
    return (l.wo_count ? l.wo_count + '工单' : '无工单') + '·' + (l.tn_count ? l.tn_count + '菲号' : '0菲号')
        + (progTxt ? '·工序' + progTxt : '');
}

function so_chain_cell($row, which) {
    return $row.children('td.so-chain-cell').eq(which === 'dn' ? 1 : 0);
}
// 只清**本行**的高亮（多行可同时展开，不能清别人）
function so_chain_clear_cells($row) {
    $row.find('td.so-chain-cell').each(function () {
        this.style.borderColor = ''; this.style.background = ''; this.style.boxShadow = '';
        this.style.borderRadius = ''; this.style.position = ''; this.style.zIndex = '';
    });
    $row.find('.so-chain-cover').remove();
}

// 点列 → **该单元格本身**上色框线(下边不封) + 下面同色边框明细面板，连成一体(模拟标签页)；
// 点同列收起(取消框线)、点另一列切换。
function so_chain_toggle($box, idx, which, line) {
    const $row = $box.find('tr[data-idx="' + idx + '"]');
    const $ex = $box.find('tr.so-chain-inline[data-key="' + idx + '"]');
    if ($ex.length && $ex.attr('data-tab') === which) {          // 收起
        $ex.remove(); so_chain_clear_cells($row); so_chain_set_caret($box, idx, null); return;
    }
    if ($ex.length) { $ex.remove(); }
    so_chain_clear_cells($row);                                   // 只清本行(切换)
    const color = which === 'dn' ? SO_CHAIN_DN : SO_CHAIN_PROD;
    const body = which === 'dn' ? so_chain_dn_html(line) : so_chain_tree_html(line);
    // 被点单元格整体上色（上/左/右边框 + 圆角，下边留空 → 与下面面板连成一体）
    // 被点单元格：inset 画 上/左/右 三边；再用**格内绝对定位覆盖条**盖掉下方明细面板顶边 → 彻底连贯
    const $cell = so_chain_cell($row, which);
    $cell.css({
        'border-color': 'transparent',
        'background': 'var(--fg-color)',
        'box-shadow': 'inset 1px 0 0 ' + color + ', inset -1px 0 0 ' + color + ', inset 0 1px 0 ' + color,
        'border-radius': '6px 6px 0 0',
        'position': 'relative', 'z-index': 3
    });
    $cell.append('<span class="so-chain-cover" style="position:absolute;left:0;right:0;bottom:-2px;'
        + 'height:2px;background:var(--fg-color);pointer-events:none;z-index:3"></span>');
    const panel = '<div style="border:1px solid ' + color + ';border-radius:0 0 6px 6px;padding:8px 10px">' + body + '</div>';
    $row.after('<tr class="so-chain-inline" data-key="' + idx + '" data-tab="' + which + '">'
        + '<td colspan="' + SO_CHAIN_COLS + '" style="padding:0;border:none">' + panel + '</td></tr>');
    so_chain_set_caret($box, idx, which);
}

// 生产链条面板内容：生产计划 + 工单→菲号→工序卡
function so_chain_tree_html(line) {
    let h = '';
    if (line.plans && line.plans.length) {
        h += '<div style="margin-bottom:6px"><b>生产计划</b>：' + line.plans.map(function (p) {
            return so_chain_link('Production Plan', p.pp, p.pp)
                 + (p.planned_qty ? ' (计划 ' + so_chain_num(p.planned_qty) + ')' : '')
                 + (p.pending_qty ? '（待产 ' + so_chain_num(p.pending_qty) + '）' : '');
          }).join('、') + '</div>';
    }
    if (!line.work_orders || !line.work_orders.length) {
        return h + '<div class="text-muted">无工单</div>';
    }
    const forgot = line.forgot_complete || [];
    h += '<div style="padding:2px 0">';
    line.work_orders.forEach(function (w) {
        const tns = w.tracking_numbers || [];
        const isForgot = forgot.indexOf(w.wo) >= 0;
        h += '<div style="border:1px solid ' + (isForgot ? '#e6b800' : 'var(--border-color)') + ';'
           + (isForgot ? 'background:#fff9e6;' : '') + 'border-radius:6px;padding:8px;margin:6px 0">';
        h += '<div><b>' + so_chain_link('Work Order', w.wo, w.wo) + '</b>'
           + (w.item_code ? '　' + so_chain_link('Item', w.item_code, w.item_code)
              + (w.item_name ? ' <span class="text-muted" style="font-size:11px">: ' + so_chain_esc(w.item_name) + '</span>' : '')
              + so_chain_item_type(w.item_code) : '')
           + (w.docstatus === 0 ? ' <span class="indicator-pill gray">草稿</span>' : '')
           + (w.pp ? '　计划 ' + so_chain_link('Production Plan', w.pp, w.pp) : '')
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

function so_chain_dn_html(line) {
    const dns = line.dns || [];
    if (!dns.length) return '<div class="text-muted">无销售出库</div>';
    let h = '<table class="table table-bordered" style="margin:0;font-size:12px">'
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
    return h + '</tbody></table>';
}

function so_chain_show_detail(line, so) {
    const head = '<div style="margin-bottom:6px"><b>' + so_chain_link('Item', line.item_code, line.item_code) + '</b>'
        + '　订单 ' + so_chain_num(line.qty) + '　已发 ' + so_chain_num(line.delivered)
        + '　未发 ' + so_chain_num(line.open_qty) + '　交期 ' + so_chain_esc(line.delivery_date || '-')
        + (Number(line.overdue_days) > 0 ? ' <span class="text-danger">(超 ' + line.overdue_days + ' 天)</span>' : '')
        + '　' + line.stage + ' ' + so_chain_esc(line.substate)
        + (line.customer_item_code ? '　客户码 ' + so_chain_esc(line.customer_item_code) : '') + '</div>';
    const sec = function (color, title, body) {
        return '<div style="margin-top:10px"><div style="background:' + color + ';color:#fff;padding:3px 10px;'
            + 'border-radius:4px 4px 0 0;font-weight:600;font-size:12px">' + title + '</div>'
            + '<div style="border:1px solid ' + color + ';border-top:none;border-radius:0 0 4px 4px;padding:8px 10px">'
            + body + '</div></div>';
    };
    const d = new frappe.ui.Dialog({
        title: __('链条明细：') + so + ' / ' + (line.item_name || line.item_code),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'html' }],
    });
    d.fields_dict.html.$wrapper.html('<div style="max-height:72vh;overflow:auto">' + head
        + sec(SO_CHAIN_PROD, '生产链条', so_chain_tree_html(line))
        + sec(SO_CHAIN_DN, '出库', so_chain_dn_html(line))
        + '</div>');
    d.show();
}
