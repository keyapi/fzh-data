// ─────────────────────────────────────────────────────────────────────────
// 「供应链链条」内嵌 SO 表单 —— 追加到 key_test/public/js/sales_order.js **末尾**
//
// 形态（按调研：一行一摘要 + 行内展开 + 弹窗留给深度；不用 hover —— 触屏失效/可访问性坑/v15 无官方 hover 卡）：
//   主表一行 = 一条 SO 行；右侧「链条」列 = 「N 张 · M 菲号」+「工序 d/t」摘要，**点击就地展开**（不弹窗）。
//   展开内容 = 工单 → **菲号(<details open> 默认展开)** → 逐工序 Job Card；另有「弹窗」列做深度查看。
//   层级依据：菲号 = 一批(组)皮壳/半成品实物流身份证，开料按组生成，贯穿该工单全部工序；
//             每个菲号在每个工序恰 1 张 Job Card → 唯一键 = (菲号, 工序)。
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
function so_chain_t(s) { return so_chain_esc(s == null ? '' : __(String(s))); }   // 过翻译
function so_chain_link(doctype, name, label) {
    if (!name) return so_chain_esc(label || '');
    let slug;
    try { slug = frappe.router.slug(doctype); }
    catch (e) { slug = doctype.toLowerCase().replace(/ /g, '-'); }
    return '<a href="/app/' + slug + '/' + encodeURIComponent(name) + '" target="_blank">'
         + so_chain_esc(label || name) + '</a>';
}

function so_chain_render($box, data) {
    let tOpenQty = 0;
    const rows = (data.lines || []).map(function (l, idx) {
        tOpenQty += Number(l.open_qty || 0);
        const plans = (l.plans || []).map(function (p) {
            return so_chain_link('Production Plan', p.pp, p.pp + (p.planned_qty ? ' (' + so_chain_num(p.planned_qty) + ')' : ''));
        }).join(', ') || '-';
        // 摘要：工单/菲号数 + 完成工序合计
        let od = 0, ot = 0;
        (l.work_orders || []).forEach(function (w) { od += (w.ops_done || 0); ot += (w.ops_total || 0); });
        const summary = (l.wo_count ? l.wo_count + ' 张' : '-') + ' · ' + (l.tn_count ? l.tn_count + ' 菲号' : '0 菲号')
            + (ot ? '　<span class="text-muted">工序 ' + od + '/' + ot + '</span>' : '');
        const chainCell = l.wo_count
            ? '<a href="#" class="so-chain-toggle" data-i="' + idx + '"><b>' + summary + '</b> <span class="so-chain-caret">▸</span></a>'
            : summary;
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
            + '<td>' + chainCell + '</td>'
            + '<td>' + (l.wo_count ? '<a href="#" class="so-chain-dialog" data-i="' + idx + '">弹窗</a>' : '-') + '</td>'
            + '</tr>';
    }).join('');
    const html = '<div style="overflow:auto">'
        + '<table class="table table-bordered" style="margin:0">'
        + '<thead><tr><th>订单行物料</th><th>客户物料号</th><th>订单量</th><th>已发</th><th>未发</th>'
        + '<th>交期</th><th>阶段</th><th>生产计划</th><th>链条</th><th></th></tr></thead>'
        + '<tbody>' + rows + '</tbody>'
        + '<tfoot><tr><th colspan="4" style="text-align:right">未发合计</th>'
        + '<th style="text-align:right">' + so_chain_num(tOpenQty) + '</th><th colspan="5"></th></tr></tfoot></table>'
        + '<div class="text-muted" style="margin-top:4px;font-size:11px">'
        + '阶段 0–3；完成量取第一道工序(不跨工序求和)；已发按出库单净额(含退货抵扣)。'
        + '点「链条」就地展开 工单→菲号→逐工序工序卡；点「弹窗」看大图。</div></div>';
    $box.html(html);

    $box.find('.so-chain-toggle').on('click', function (e) {
        e.preventDefault();
        so_chain_toggle($box, $(this).data('i'), data.lines[$(this).data('i')]);
    });
    $box.find('.so-chain-dialog').on('click', function (e) {
        e.preventDefault();
        so_chain_show_detail(data.lines[$(this).data('i')], data.sales_order);
    });
}

// 行内展开/收起（accordion row）
function so_chain_toggle($box, idx, line) {
    const $row = $box.find('tr[data-idx="' + idx + '"]');
    const $next = $row.next('.so-chain-inline');
    if ($next.length) { $next.remove(); $row.find('.so-chain-caret').text('▸'); return; }
    $box.find('.so-chain-inline').remove();
    $box.find('.so-chain-caret').text('▸');
    $row.find('.so-chain-caret').text('▾');
    $row.after('<tr class="so-chain-inline"><td colspan="' + SO_CHAIN_COLS + '" style="background:var(--fg-color)">'
        + so_chain_tree_html(line) + '</td></tr>');
}

// 树：工单 → 菲号(默认展开) → 逐工序 Job Card
function so_chain_tree_html(line) {
    if (!line.work_orders || !line.work_orders.length) return '<div class="text-muted">无工单</div>';
    let h = '<div style="padding:2px 4px">';
    line.work_orders.forEach(function (w) {
        const tns = w.tracking_numbers || [];
        h += '<div style="border:1px solid var(--border-color);border-radius:6px;padding:8px;margin:6px 0">';
        h += '<div><b>' + so_chain_link('Work Order', w.wo, w.wo) + '</b>　工单量 ' + so_chain_num(w.qty)
           + '　完成 ' + so_chain_num(w.done) + '　头部状态 ' + so_chain_t(w.status)
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
    const total = (w.operations || []).length;
    const doneSteps = (t.steps || []).filter(function (s) { return s.status === 'Completed'; }).length;
    let h = '<details open style="margin:4px 0;border-left:3px solid var(--border-color);padding-left:8px">'
        + '<summary style="cursor:pointer"><b>菲号 ' + so_chain_link('Tracking Number', t.tn, t.tn) + '</b>'
        + '　数量 ' + so_chain_num(t.qty) + '　工序完成 ' + doneSteps + '/' + total
        + (t.iwo ? '　开料 ' + so_chain_link('Initial Work Order', t.iwo, t.iwo) : '') + '</summary>';
    if (t.steps && t.steps.length) {
        h += '<table class="table table-bordered" style="margin:4px 0;font-size:12px">'
           + '<thead><tr><th>工序</th><th>序</th><th>工序卡</th><th>状态</th><th>数量</th><th>完工时间</th></tr></thead><tbody>';
        t.steps.forEach(function (s) {
            h += '<tr><td>' + so_chain_t(s.operation) + '</td><td>' + so_chain_esc(s.seq) + '</td>'
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
    d.fields_dict.html.$wrapper.html('<div style="max-height:72vh;overflow:auto">' + head + plans + so_chain_tree_html(line) + '</div>');
    d.show();
}
