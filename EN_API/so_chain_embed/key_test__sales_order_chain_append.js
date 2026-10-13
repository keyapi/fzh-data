// ─────────────────────────────────────────────────────────────────────────
// 「供应链链条摘要」内嵌 SO 表单 —— 追加到 key_test/public/js/sales_order.js **末尾**
//
// 原因：hooks.py 的 doctype_js 对 Sales Order 只允许**一个** JS 文件
// （"Sales Order": "public/js/sales_order.js"），所以要并进该文件，
// 不能新建第二个文件。Frappe 允许对同一 doctype 多次 frappe.ui.form.on(...)。
//
// 依赖服务端方法 key_test.so_chain.get_so_chain（见 key_test__so_chain.py）。
// ─────────────────────────────────────────────────────────────────────────
frappe.ui.form.on('Sales Order', {
    refresh: function (frm) {
        if (frm.is_new()) return;
        // 复用同一个容器，避免每次 refresh 重复叠加 section
        let $box = frm.dashboard.wrapper.find('.so-chain-summary');
        if (!$box.length) {
            frm.dashboard.add_section('<div class="so-chain-summary"></div>', __('供应链链条'));
            $box = frm.dashboard.wrapper.find('.so-chain-summary');
        }
        $box.html('<div class="text-muted">加载中…</div>');
        frappe.call({
            method: 'key_test.so_chain.get_so_chain',
            args: { sales_order: frm.doc.name },
            callback: function (r) {
                if (!r || !r.message) {
                    $box.html('<div class="text-muted">无数据</div>');
                    return;
                }
                $box.html(so_chain_html(r.message));
            }
        });
    }
});

function so_chain_html(data) {
    const esc = frappe.utils.escape_html;
    const rows = (data.lines || []).map(function (l) {
        const wo = (l.work_orders || []).map(function (w) {
            return esc(w.wo) + ' ' + esc(w.text);
        }).join(' | ') || '-';
        return '<tr>'
            + '<td>' + esc(l.item_code || '') + '</td>'
            + '<td>' + esc(l.customer_item_code || '') + '</td>'
            + '<td style="text-align:right">' + l.qty + '</td>'
            + '<td style="text-align:right">' + l.delivered + '</td>'
            + '<td style="text-align:right">' + l.open_qty + '</td>'
            + '<td>' + l.stage + ' ' + esc(l.substate || '') + '</td>'
            + '<td style="font-size:11px">' + wo + '</td>'
            + '</tr>';
    }).join('');
    return ''
        + '<div style="overflow:auto">'
        + '<table class="table table-bordered" style="margin:0">'
        + '<thead><tr>'
        + '<th>订单行物料</th><th>客户物料号</th><th>订单量</th><th>已发</th><th>未发</th>'
        + '<th>阶段</th><th>工单/工序</th>'
        + '</tr></thead><tbody>' + rows + '</tbody></table>'
        + '<div class="text-muted" style="margin-top:4px;font-size:11px">'
        + '阶段 0–3；进度取第一道工序完成量（不跨工序求和）；已发按出库单净额（含退货抵扣）。'
        + '</div></div>';
}
