// ─────────────────────────────────────────────────────────────────────────
// 「供应链链条」内嵌 SO 表单 —— 追加到 key_test/public/js/sales_order.js **末尾**
//
// 原因：hooks.py 的 doctype_js 对 Sales Order 只允许**一个** JS 文件，故并进该文件。
// Frappe 允许对同一 doctype 多次 frappe.ui.form.on(...)。
//
// 设计（参考业界主流「摘要 + 可下钻」模式）：
//   主表一行 = 一条 SO 行：物料 / 客户码 / 订单量 / 已发 / 未发 / 阶段 / 生产计划
//                          / 工单(点开 N 张) / 菲号(点开 M 个)
//   一对多（SO行→N工单→N工序+N菲号）**不塞格子**，点开弹窗看只读多级表。
// 依赖服务端方法 key_test.so_chain.get_so_chain。
// 容器用 frm.dashboard.parent（jQuery），不用不存在的 frm.dashboard.wrapper。
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

function so_chain_render($box, data) {
    const rows = (data.lines || []).map(function (l, idx) {
        const plans = (l.plans || []).map(function (p) {
            return so_chain_esc(p.pp) + (p.planned_qty ? ' (' + so_chain_num(p.planned_qty) + ')' : '');
        }).join(', ') || '-';
        const woCell = l.wo_count
            ? '<a href="#" class="so-chain-open" data-i="' + idx + '">' + l.wo_count + ' 张 ▸</a>'
            : '-';
        const tnCell = l.tn_count
            ? '<a href="#" class="so-chain-open" data-i="' + idx + '">' + l.tn_count + ' 个 ▸</a>'
            : '-';
        return '<tr>'
            + '<td>' + so_chain_esc(l.item_code) + '</td>'
            + '<td>' + so_chain_esc(l.customer_item_code) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.qty) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.delivered) + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.open_qty) + '</td>'
            + '<td>' + l.stage + ' ' + so_chain_esc(l.substate) + '</td>'
            + '<td>' + plans + '</td>'
            + '<td>' + woCell + '</td>'
            + '<td>' + tnCell + '</td>'
            + '</tr>';
    }).join('');
    const html = '<div style="overflow:auto">'
        + '<table class="table table-bordered" style="margin:0">'
        + '<thead><tr><th>订单行物料</th><th>客户物料号</th><th>订单量</th><th>已发</th><th>未发</th>'
        + '<th>阶段</th><th>生产计划</th><th>工单</th><th>菲号</th></tr></thead>'
        + '<tbody>' + rows + '</tbody></table>'
        + '<div class="text-muted" style="margin-top:4px;font-size:11px">'
        + '阶段 0–3；工单完成量取第一道工序（不跨工序求和）；已发按出库单净额（含退货抵扣）。'
        + '点「工单/菲号」看逐道工序与跟踪单号。</div></div>';
    $box.html(html);
    $box.find('.so-chain-open').on('click', function (e) {
        e.preventDefault();
        so_chain_show_detail(data.lines[$(this).data('i')], data.sales_order);
    });
}

function so_chain_show_detail(line, so) {
    let h = '<div style="max-height:70vh;overflow:auto">';
    h += '<div style="margin-bottom:6px"><b>' + so_chain_esc(line.item_code) + '</b>'
       + '　订单 ' + so_chain_num(line.qty) + '　已发 ' + so_chain_num(line.delivered)
       + '　未发 ' + so_chain_num(line.open_qty) + '　阶段 ' + line.stage + ' ' + so_chain_esc(line.substate)
       + (line.customer_item_code ? '　客户码 ' + so_chain_esc(line.customer_item_code) : '') + '</div>';
    if (line.plans && line.plans.length) {
        h += '<div style="margin:6px 0"><b>生产计划</b>：' + line.plans.map(function (p) {
            return so_chain_esc(p.pp) + (p.pending_qty ? '（待产 ' + so_chain_num(p.pending_qty) + '）' : '');
        }).join('、') + '</div>';
    }
    if (!line.work_orders || !line.work_orders.length) {
        h += '<div class="text-muted">无工单</div></div>';
    } else {
        line.work_orders.forEach(function (w) {
            h += '<div style="border:1px solid var(--border-color);border-radius:6px;padding:8px;margin:8px 0">';
            h += '<div><b>' + so_chain_esc(w.wo) + '</b>　工单量 ' + so_chain_num(w.qty)
               + '　完成 ' + so_chain_num(w.done)
               + '　头部状态 ' + so_chain_esc(w.status)
               + (w.produced_head ? '（已产 ' + so_chain_num(w.produced_head) + '）' : '') + '</div>';
            if (w.operations && w.operations.length) {
                h += '<table class="table table-bordered" style="margin:6px 0;font-size:12px">'
                   + '<thead><tr><th>工序</th><th>序</th><th>状态</th><th>完成量</th></tr></thead><tbody>';
                w.operations.forEach(function (o) {
                    h += '<tr><td>' + so_chain_esc(o.operation) + '</td><td>' + so_chain_esc(o.seq)
                       + '</td><td>' + so_chain_esc(o.status) + '</td>'
                       + '<td style="text-align:right">' + so_chain_num(o.done) + '</td></tr>';
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
                    h += '<tr><td>' + so_chain_esc(t.tn) + '</td>'
                       + '<td style="text-align:right">' + so_chain_num(t.qty) + '</td>'
                       + '<td>' + (t.iwo ? so_chain_esc(t.iwo) : '<span class="text-muted">未开料</span>') + '</td>'
                       + '<td>' + so_chain_esc(t.mat) + '</td></tr>';
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
