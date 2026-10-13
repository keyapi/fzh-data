// ─────────────────────────────────────────────────────────────────────────
// 「供应链链条」内嵌 SO 表单 —— 追加到 key_test/public/js/sales_order.js **末尾**
//
// 设计（业界主流「摘要 + 可下钻」）：
//   主表一行 = 一条 SO 行：物料 / 客户码 / 订单量 / 已发 / 未发 / 交期 / 阶段 / 生产计划 / 工单 / 菲号
//   一对多（SO行→N工单→N工序+N菲号）不塞格子，点开弹窗看只读多级表。
//   单据名一律用 **可点链接**（frappe.utils.get_form_link）便于跳转。
// 依赖服务端方法 key_test.so_chain.get_so_chain。容器用 frm.dashboard.parent。
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

function so_chain_esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }
function so_chain_num(v) { const f = Number(v || 0); return (Math.round(f * 1000) / 1000).toString(); }
// 单据跳转链接（新标签页打开；name 为空返回原样文本）
function so_chain_link(doctype, name, label) {
    if (!name) return so_chain_esc(label || '');
    let slug;
    try { slug = frappe.router.slug(doctype); }
    catch (e) { slug = doctype.toLowerCase().replace(/ /g, '-'); }
    const href = '/app/' + slug + '/' + encodeURIComponent(name);
    return '<a href="' + href + '" target="_blank">' + so_chain_esc(label || name) + '</a>';
}
function so_chain_chip(n) { return n ? n + ' ▸' : '-'; }

function so_chain_render($box, data) {
    let tOpen = 0, tShipped = 0, tOpenQty = 0;
    const rows = (data.lines || []).map(function (l, idx) {
        tOpenQty += Number(l.open_qty || 0);
        const plans = (l.plans || []).map(function (p) {
            return so_chain_link('Production Plan', p.pp, p.pp + (p.planned_qty ? ' (' + so_chain_num(p.planned_qty) + ')' : ''));
        }).join(', ') || '-';
        const woCell = l.wo_count ? '<a href="#" class="so-chain-open" data-i="' + idx + '">' + so_chain_chip(l.wo_count) + '</a>' : '-';
        const tnCell = l.tn_count ? '<a href="#" class="so-chain-open" data-i="' + idx + '">' + so_chain_chip(l.tn_count) + '</a>' : '-';
        const od = Number(l.overdue_days || 0);
        const dd = od > 0 ? '<span class="text-danger" title="已过交付日期 ' + od + ' 天">' + so_chain_esc(l.delivery_date) + ' (超' + od + '天)</span>'
                          : so_chain_esc(l.delivery_date || '-');
        const stageColor = { 0: 'gray', 1: 'orange', 2: 'blue', 3: 'green' }[l.stage] || 'gray';
        const stageChip = '<span class="indicator-pill ' + stageColor + '">' + l.stage + ' ' + so_chain_esc(l.substate) + '</span>';
        return '<tr>'
            + '<td>' + so_chain_link('Item', l.item_code, l.item_code) + '</td>'
            + '<td>' + so_chain_esc(l.customer_item_code) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.qty) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.delivered) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.open_qty) + '</td>'
            + '<td>' + dd + '</td>'
            + '<td>' + stageChip + '</td>'
            + '<td>' + plans + '</td>'
            + '<td>' + woCell + '</td>'
            + '<td>' + tnCell + '</td>'
            + '</tr>';
    }).join('');
    const html = '<div style="overflow:auto">'
        + '<table class="table table-bordered" style="margin:0">'
        + '<thead><tr><th>订单行物料</th><th>客户物料号</th><th>订单量</th><th>已发</th><th>未发</th>'
        + '<th>交期</th><th>阶段</th><th>生产计划</th><th>工单</th><th>菲号</th></tr></thead>'
        + '<tbody>' + rows + '</tbody>'
        + '<tfoot><tr><th colspan="4" style="text-align:right">未发合计</th>'
        + '<th style="text-align:right">' + so_chain_num(tOpenQty) + '</th><th colspan="5"></th></tr></tfoot></table>'
        + '<div class="text-muted" style="margin-top:4px;font-size:11px">'
        + '阶段 0–3；工单完成量取第一道工序（不跨工序求和）；已发按出库单净额(含退货抵扣)。'
        + '单据名可点跳转；点「工单/菲号」看逐道工序、工序卡与跟踪单号。</div></div>';
    $box.html(html);
    $box.find('.so-chain-open').on('click', function (e) {
        e.preventDefault();
        so_chain_show_detail(data.lines[$(this).data('i')], data.sales_order);
    });
}

function so_chain_show_detail(line, so) {
    let h = '<div style="max-height:72vh;overflow:auto">';
    h += '<div style="margin-bottom:6px"><b>' + so_chain_link('Item', line.item_code, line.item_code) + '</b>'
       + '　订单 ' + so_chain_num(line.qty) + '　已发 ' + so_chain_num(line.delivered)
       + '　未发 ' + so_chain_num(line.open_qty) + '　交期 ' + so_chain_esc(line.delivery_date || '-')
       + (Number(line.overdue_days) > 0 ? ' <span class="text-danger">(超 ' + line.overdue_days + ' 天)</span>' : '')
       + '　' + line.stage + ' ' + so_chain_esc(line.substate)
       + (line.customer_item_code ? '　客户码 ' + so_chain_esc(line.customer_item_code) : '') + '</div>';
    if (line.plans && line.plans.length) {
        h += '<div style="margin:6px 0"><b>生产计划</b>：' + line.plans.map(function (p) {
            return so_chain_link('Production Plan', p.pp, p.pp) + (p.pending_qty ? '（待产 ' + so_chain_num(p.pending_qty) + '）' : '');
        }).join('、') + '</div>';
    }
    if (!line.work_orders || !line.work_orders.length) {
        h += '<div class="text-muted">无工单</div></div>';
    } else {
        line.work_orders.forEach(function (w) {
            h += '<div style="border:1px solid var(--border-color);border-radius:6px;padding:8px;margin:8px 0">';
            h += '<div><b>' + so_chain_link('Work Order', w.wo, w.wo) + '</b>　工单量 ' + so_chain_num(w.qty)
               + '　完成 ' + so_chain_num(w.done) + '　头部状态 ' + so_chain_esc(w.status)
               + (w.produced_head ? '（已产 ' + so_chain_num(w.produced_head) + '）' : '')
               + (w.last_end ? '　最后报工 ' + so_chain_esc(w.last_end) : '') + '</div>';
            if (w.operations && w.operations.length) {
                h += '<table class="table table-bordered" style="margin:6px 0;font-size:12px">'
                   + '<thead><tr><th>工序</th><th>序</th><th>状态</th><th>完成量</th><th>工序卡（Job Card）</th></tr></thead><tbody>';
                w.operations.forEach(function (o) {
                    const jcs = (o.job_cards || []).map(function (jc) {
                        return so_chain_link('Job Card', jc.name, jc.name)
                             + ' <span class="text-muted">[' + so_chain_esc(jc.status) + ' ' + so_chain_num(jc.qty)
                             + (jc.employee ? ' ' + so_chain_esc(jc.employee) : '') + ']</span>';
                    }).join('<br>') || '<span class="text-muted">无</span>';
                    h += '<tr><td>' + so_chain_esc(o.operation) + '</td><td>' + so_chain_esc(o.seq)
                       + '</td><td>' + so_chain_esc(o.status) + '</td>'
                       + '<td style="text-align:right">' + so_chain_num(o.done) + '</td>'
                       + '<td>' + jcs + '</td></tr>';
                });
                h += '</tbody></table>';
            } else {
                h += '<div class="text-muted">无工序路由</div>';
            }
            if (w.tracking_numbers && w.tracking_numbers.length) {
                h += '<div style="margin-top:4px"><b>菲号（跟踪单号）</b> ' + w.tracking_numbers.length + ' 个'
                   + '<table class="table table-bordered" style="margin:4px 0;font-size:12px">'
                   + '<thead><tr><th>菲号</th><th>数量</th><th>开料工单</th><th>交付物料</th></tr></thead><tbody>';
                w.tracking_numbers.forEach(function (t) {
                    h += '<tr><td>' + so_chain_link('Tracking Number', t.tn, t.tn) + '</td>'
                       + '<td style="text-align:right">' + so_chain_num(t.qty) + '</td>'
                       + '<td>' + (t.iwo ? so_chain_link('Initial Work Order', t.iwo, t.iwo) : '<span class="text-muted">未开料</span>') + '</td>'
                       + '<td>' + (t.mat ? so_chain_link('Item', t.mat, t.mat) : '') + '</td></tr>';
                });
                h += '</tbody></table></div>';
            } else {
                h += '<div class="text-muted" style="margin-top:4px">无菲号（未开料）</div>';
            }
            h += '</div>';
        });
        h += '</div>';
    }
    const d = new frappe.ui.Dialog({
        title: __('链条明细：') + so + ' / ' + (line.item_name || line.item_code),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'html' }],
    });
    d.fields_dict.html.$wrapper.html(h);
    d.show();
}
