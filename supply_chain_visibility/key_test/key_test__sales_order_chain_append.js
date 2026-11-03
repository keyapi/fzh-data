// 销售订单：表头「上传Excel(客户物料编号→物料编号)」按钮 + 无扣一致性校验
// 迁移自 Client Script「销售订单 子表 items 上传Excel  客户物料编号 转为 物料编号」(2026-10-10)
// 该 Client Script 已停用(enabled=0)，逻辑以此文件为准。

// 忽略重复值 每次点击按钮 先清空子表
frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        // 判断单据是否为草稿状态
        if (frm.doc.docstatus === 0) {  // docstatus === 0 表示草稿状态
            frm.fields_dict["custom_process_file_customer_item_code"].$wrapper.show();
        } else {
            frm.fields_dict["custom_process_file_customer_item_code"].$wrapper.hide();
        }

        // 按钮点击事件
        frm.fields_dict["custom_process_file_customer_item_code"].onclick = function() {
            const file_url = frm.doc.custom_attach_file_customer_item_code; // 获取上传文件的 URL

            // 调用后端方法，传递文件 URL
            frappe.call({
                method: 'key_test.item_utils.read_excel_file',
                args: {
                    file_url: file_url,
                    customer: frm.doc.customer,
                    customer_name: frm.doc.customer_name
                },
                callback: function(response) {
                    if (response.message) {
                        const item_codes = response.message;

                        // 清空子表 items
                        frm.clear_table('items');

                        // 遍历 item_codes 并添加新行
                        item_codes.forEach(item => {
                            frm.add_child('items', {
                                customer_item_code: item.customer_item_code,
                                item_code: item.item_code,
                                item_name: item.item_name,      // 添加物料名称
                                uom: item.uom,                  // 添加单位
                                rate: item.rate,                // 添加价格
                                qty: item.qty,                  // 添加数量
                                custom_label_combination: item.custom_label_combination, // 添加标签组合
                                description: item.description,   // 添加 description
                                delivery_date: item.delivery_date, // 添加出货日期
                                custom_fba_sku: item.custom_fba_sku, //添加 FBA SKU
                                type_of_manufacturing: item.type_of_manufacturing, // 添加生产方式
                                custom_tongtool_item_name: item.tongtool_item_name
                            });
                        });

                        frm.refresh_field('items'); // 刷新子表显示
                        frappe.msgprint(__('已成功添加项目到子表'));

                        // 执行无扣一致性校验
                        validate_no_buckle_consistency(frm);

                    } else {
                        frappe.msgprint(__('未找到任何项目'));
                    }
                }
            });
        };
    }
});

/**
 * 校验子表中“无扣”内容是否一致
 * 条件1：通途物料名称包含“无扣”但系统物料名称不包含“无扣”
 * 条件2：通途物料名称不包含“无扣”但系统物料名称包含“无扣”
 * 只对物料组属于以下物料组的行进行校验：
 * - 皮壳#三角靠枕
 * - 皮壳#三角靠枕无扣
 * - 三角靠枕无扣
 * - 三角靠枕
*/

function validate_no_buckle_consistency(frm) {
    // 调用 get_descendant_groups 获取需要校验的物料组列表
    frappe.call({
        method: 'key_test.item_utils.get_descendant_groups',
        callback: function(response) {
            if (response.message) {
                const { cp_item_groups, bcp_item_groups, log_message } = response.message;
                // cp_item_groups 和 bcp_item_groups 都是列表，包含了子孙分组
                // 根据需求，应该校验 cp_item_groups 和 bcp_item_groups 中的所有物料组
                const target_item_groups = [...cp_item_groups, ...bcp_item_groups];

                // 执行校验逻辑，传入目标物料组列表
                perform_validation(frm, target_item_groups);
                // console.log(target_item_groups)
            }
        }
    });
}
function perform_validation(frm, target_item_groups) {
    let errors = [];
    let items = frm.doc.items || [];
    let $grid_body = frm.fields_dict['items'].grid.$body;

    if (!$grid_body || $grid_body.length === 0) {
        $grid_body = $(frm.fields_dict['items'].grid.wrapper).find('.grid-body .rows');
    }
    // 清除所有行的背景颜色
    $grid_body.find('.grid-row').css('background-color', '');

    items.forEach((row, idx) => {
        // 检查当前物料组是否在目标列表中
        if (!target_item_groups.includes(row.item_group)) {
            return; // 不在列表中，跳过校验
        }

        const tongtool_name = (row.custom_tongtool_item_name || '').trim();
        const system_name = (row.item_name || '').trim();
        const tongtool_has = tongtool_name.includes('无扣');
        const system_has = system_name.includes('无扣');
        let is_conflict = false;

        if (tongtool_has && !system_has) {
            errors.push(`第 ${idx+1} 行：通途物料名称含“无扣”但系统物料名称不含（物料编码：${row.item_code || row.customer_item_code}）`);
            is_conflict = true;
        } else if (!tongtool_has && system_has) {
            errors.push(`第 ${idx+1} 行：通途物料名称不含“无扣”但系统物料名称含“无扣”（物料编码：${row.item_code || row.customer_item_code}）`);
            is_conflict = true;
        }

        if (is_conflict && $grid_body) {
            let $row = $grid_body.find('.grid-row:eq(' + idx + ')');
            $row.css('background-color', '#fff3e0');
        }
    });

    if (errors.length > 0) {
        frappe.msgprint({
            title: __('无扣信息不一致提醒'),
            indicator: 'orange',
            message: errors.join('<br>')
        });
    }
}


// frappe.ui.form.on('Sales Order', {
//     refresh: function(frm) {
//         frm.fields_dict["custom_process_file_customer_item_code"].onclick = function() {
//             const file_url = frm.doc.custom_attach_file_customer_item_code; // 获取上传文件的 URL

//             // 调用后端方法，传递文件 URL
//             frappe.call({
//                 method: 'key_test.item_utils.read_excel_file',
//                 args: {
//                     file_url: file_url
//                 },
//                 callback: function(response) {
//                     if (response.message) {
//                         const item_codes = response.message;
//                         const existing_customer_item_codes = frm.doc.items.map(item => item.customer_item_code);

//                         // 遍历 item_codes 并处理重复项
//                         item_codes.forEach(item => {
//                             if (existing_customer_item_codes.includes(item.customer_item_code)) {
//                                 frappe.msgprint(__('已存在相同的 customer_item_code: ') + item.customer_item_code);
//                                 // 删除已有的行
//                                 frm.doc.items = frm.doc.items.filter(existing_item => existing_item.customer_item_code !== item.customer_item_code);
//                             }

//                             // 添加新行
//                             frm.add_child('items', {
//                                 customer_item_code: item.customer_item_code,
//                                 item_code: item.item_code,
//                                 item_name: item.item_name,      // 添加物料名称
//                                 uom: item.uom,                  // 添加单位
//                                 rate: item.rate,                // 添加价格
//                                 qty: item.qty,                  // 添加数量
//                                 custom_label_combination: item.custom_label_combination, // 添加标签组合
//                                 description: item.description,   // 添加 description
//                                 delivery_date: item.delivery_date // 添加出货日期
//                             });
//                         });

//                         frm.refresh_field('items'); // 刷新子表显示
//                         frappe.msgprint(__('已成功添加项目到子表'));
//                     } else {
//                         frappe.msgprint(__('未找到任何项目'));
//                     }
//                 }
//             });
//         };
//     }
// });
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
const SO_CHAIN_HEAD = '#6f42c1';   // 头程物流 主色
function so_chain_esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }
function so_chain_num(v) {
    if (v === null || v === undefined || v === '') return '—';
    const f = Number(v);
    if (!isFinite(f)) return '—';
    return (Math.round(f * 1000) / 1000).toString();
}
// 后端 evidence_status() 的统一口径：known / estimated / unknown
function so_chain_is_known(status) { return status === 'known'; }
// 按状态选数量：known→proven；estimated→estimated（估算）；unknown→—
function so_chain_qty_by_status(proven, estimated, status) {
    if (status === 'known') {
        return (proven === null || proven === undefined) ? '—' : so_chain_num(proven);
    }
    if (status === 'estimated') {
        return (estimated === null || estimated === undefined)
            ? '—' : so_chain_num(estimated) + '（估算）';
    }
    if (status === null || status === undefined) {
        if (proven !== null && proven !== undefined) return so_chain_num(proven);
        if (estimated !== null && estimated !== undefined) return so_chain_num(estimated) + '（估算）';
    }
    return '—';
}
function so_chain_t(s) { return so_chain_esc(s == null ? '' : __(String(s))); }
function so_chain_link(doctype, name, label) {
    if (!name) return so_chain_esc(label || '');
    let url;
    try {
        url = frappe.utils.get_form_link(doctype, name);
    } catch (e) {
        url = '/app/' + doctype.toLowerCase().replace(/ /g, '-') + '/' + encodeURIComponent(name);
    }
    return '<a href="' + so_chain_esc(url) + '" target="_blank" rel="noopener noreferrer">'
         + so_chain_esc(label || name) + '</a>';
}
const SO_CHAIN_DEF_COLS = [
    { k: 'item', label: '订单行物料', w: 0 },      // 0 = 弹性列：吸收剩余宽度（多看物料名）
    { k: 'code', label: '客户物料号', w: 115 },
    { k: 'qty', label: '订单量', w: 54 },
    { k: 'reported', label: '全工序', w: 60 },     // 全工序已证量（production evidence）
    { k: 'instock', label: '入库净额', w: 60 },    // Stock Entry 已提交净额
    { k: 'shipped', label: '已发', w: 54 },
    { k: 'deliv', label: '交期', w: 96 },
    { k: 'stage', label: '阶段', w: 106 },
    { k: 'prod', label: '生产', w: 142 },
    { k: 'dn', label: '出库', w: 106 }
];
const SO_CHAIN_COLS = SO_CHAIN_DEF_COLS.length;
const SO_CHAIN_COL_TITLE = {
    reported: '全工序：全工序已证完成量（proven）；估算/未知不当作已证',
    instock: '入库净额：已提交 Manufacture 入库单成品行净额（毛额 − 规范化退货）',
    shipped: '已发：销售出库净额（含退货抵扣）'
};
function so_chain_widths() {
    const w = {};
    SO_CHAIN_DEF_COLS.forEach(function (c) { w[c.k] = c.w; });
    try {
        const saved = JSON.parse(localStorage.getItem('so_chain_colw') || '{}');
        Object.keys(saved).forEach(function (k) { if (k in w && saved[k] > 20) w[k] = saved[k]; });
    } catch (e) { }
    return w;
}
// ── 列宽：成熟交互（参考 AG Grid / Frappe DataTable / Excel）────────────────
//  · 表头右缘一条**始终可见**的细分隔条，悬停变主色 + col-resize 光标 → 一眼看出可拖
//  · 拖拽改变**该列宽度**并同步**整表总宽**：总宽超出容器时**下方出现横向滚动条**，不再压缩首列
//  · **双击**分隔条 = 该列自适应内容宽度
//  · 宽度记忆在 localStorage['so_chain_colw']
function so_chain_inject_css() {
    if (document.getElementById('so-chain-css')) return;
    const css = ''
        + '.so-chain-tbl{table-layout:fixed;width:100%;margin:0;font-size:12px}'
        + '.so-chain-tbl th{position:relative;overflow:hidden}'
        + '.so-chain-tbl th .so-chain-grip{position:absolute;top:0;right:0;width:8px;height:100%;cursor:col-resize;z-index:6}'
        + '.so-chain-tbl th .so-chain-grip::after{content:"";position:absolute;top:18%;bottom:18%;right:2px;width:3px;'
        + 'border-radius:2px;background:var(--gray-400);transition:background .1s}'
        + '.so-chain-tbl th:hover .so-chain-grip::after{background:var(--primary)}'
        + '.so-chain-tbl .so-chain-grip:hover::after,.so-chain-tbl .so-chain-grip.so-chain-drag::after{background:var(--primary)}'
        + 'body.so-chain-resizing,body.so-chain-resizing *{cursor:col-resize !important;user-select:none !important}';
    const st = document.createElement('style');
    st.id = 'so-chain-css';
    st.textContent = css;
    document.head.appendChild(st);
}
function so_chain_th_widths($box) {
    const ws = [];
    $box.find('thead th').each(function () { ws.push(Math.round($(this).outerWidth())); });
    return ws;
}
// 把当前「占满容器」的渲染宽度固化为 px（首列原本无 width）；之后拖拽改总宽，不再压缩首列
function so_chain_bake($box, widths) {
    const cur = so_chain_th_widths($box);
    SO_CHAIN_DEF_COLS.forEach(function (c, i) { if (cur[i] > 0) widths[c.k] = cur[i]; });
    so_chain_apply_widths($box, widths);
}
function so_chain_apply_widths($box, widths) {
    let total = 0;
    SO_CHAIN_DEF_COLS.forEach(function (c) {
        const w = Math.max(30, Math.round(widths[c.k] || 0));
        widths[c.k] = w; total += w;
        $box.find('col[data-k="' + c.k + '"]').attr('style', 'width:' + w + 'px');
    });
    $box.find('table').css('width', total + 'px');
}
function so_chain_autofit($box, widths, key) {
    so_chain_bake($box, widths);
    const idx = SO_CHAIN_DEF_COLS.map(function (c) { return c.k; }).indexOf(key);
    const cv = so_chain_autofit._cv || (so_chain_autofit._cv = document.createElement('canvas'));
    const ctx = cv.getContext('2d');
    const cs = getComputedStyle($box.find('table')[0]);
    ctx.font = (cs.fontWeight || 'normal') + ' ' + cs.fontSize + ' ' + cs.fontFamily;
    let max = 0;
    const measure = function (t) { max = Math.max(max, ctx.measureText((t || '').trim()).width); };
    $box.find('thead th').eq(idx).each(function () { measure($(this).text()); });
    $box.find('tbody tr').not('.so-chain-inline').each(function () {
        const td = $(this).children('td').eq(idx);
        measure(td.find('a,span,div').first().text() || td.text());
    });
    widths[key] = Math.min(460, Math.max(30, Math.ceil(max) + 24));
    so_chain_apply_widths($box, widths);
}
function so_chain_make_resizable($box, widths) {
    so_chain_inject_css();
    $box.find('.so-chain-grip').each(function () {
        const key = $(this).attr('data-k');
        $(this).on('mousedown', function (e) {
            if (e.which !== 1) return;
            e.preventDefault(); e.stopPropagation();
            so_chain_bake($box, widths);                 // 首次拖拽即固化（此时表格必定可见）
            const startX = e.pageX, startW = widths[key];
            $(this).addClass('so-chain-drag');
            $('body').addClass('so-chain-resizing');
            const move = function (ev) {
                widths[key] = Math.max(30, Math.round(startW + (ev.pageX - startX)));
                so_chain_apply_widths($box, widths);
            };
            const up = function () {
                $(document).off('mousemove', move).off('mouseup', up);
                $('body').removeClass('so-chain-resizing');
                $box.find('.so-chain-grip').removeClass('so-chain-drag');
                try { localStorage.setItem('so_chain_colw', JSON.stringify(widths)); } catch (err) { }
            };
            $(document).on('mousemove', move).on('mouseup', up);
        });
        $(this).on('dblclick', function (e) {
            e.preventDefault(); e.stopPropagation();
            so_chain_autofit($box, widths, key);
            try { localStorage.setItem('so_chain_colw', JSON.stringify(widths)); } catch (err) { }
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
        // 全工序 / 入库净额 两列；只有两侧都是 known(proven) 才比较差异
        const bothKnown = so_chain_is_known(l.reported_status) && so_chain_is_known(l.instock_status);
        const diff = bothKnown && Math.abs(Number(l.reported) - Number(l.instock)) > 1e-6;
        const hi = diff ? ' background:#fff9e6' : '';
        const hiTitle = diff ? ' title="全工序与入库不一致 —— 全工序 ' + so_chain_num(l.reported) + ' / 入库净额 '
            + so_chain_num(l.instock) + (l.report_note ? '（' + so_chain_esc(l.report_note) + '）' : '') + '"' : '';
        // 生产链条摘要（文本 = 展开框标题）+ 证据状态/QC/冲突
        const evTxt = '·证据' + (l.reported_status || 'unknown')
            + (l.qc_passed_status ? '·QC ' + so_chain_esc(l.qc_passed_status)
                : (l.qc_status ? '·QC ' + so_chain_esc(l.qc_status) : ''))
            + ((l.evidence_conflicts || []).length
                ? '·冲突:' + so_chain_esc(l.evidence_conflicts.join(',')) : '');
        const prodSummary = so_chain_summary_text(l, 'prod') + evTxt;
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
            + '<td style="text-align:right;white-space:nowrap' + hi + '"' + hiTitle + '>'
                + (diff ? '<b>' : '') + so_chain_qty_by_status(l.reported, l.all_process_estimated, l.reported_status) + (diff ? '</b>' : '') + '</td>'
            + '<td style="text-align:right;white-space:nowrap' + hi + '"' + hiTitle + '>'
                + (diff ? '<b>' : '') + so_chain_qty_by_status(l.instock, l.instock_estimated, l.instock_status) + (diff ? '</b>' : '') + '</td>'
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
        const t = SO_CHAIN_COL_TITLE[c.k] ? ' title="' + so_chain_esc(SO_CHAIN_COL_TITLE[c.k]) + '"' : '';
        return '<th style="white-space:nowrap;position:relative;overflow:hidden"' + t + '>' + c.label
            + '<span class="so-chain-grip" data-k="' + c.k + '" title="拖动调整列宽（双击=自适应内容）"></span></th>';
    }).join('');
    const html = '<div style="margin-bottom:4px"><a href="#" class="so-chain-delivery-so" style="color:' + SO_CHAIN_HEAD + '"><b>本 SO 实际交付</b></a>'
        + '　<a href="#" class="so-chain-delivery-global" style="color:' + SO_CHAIN_HEAD + '">全局实际交付</a>'
        + '<span class="text-muted" style="font-size:11px;margin-left:8px">DN 明细为锚；未关联不猜 SO</span></div>'
        + '<div style="overflow:auto">'
        + '<table class="table table-bordered so-chain-tbl" style="margin:0;width:100%;table-layout:fixed;font-size:12px">'
        + '<colgroup>' + cols + '</colgroup>'
        + '<thead><tr>' + ths + '</tr></thead>'
        + '<tbody>' + rows + '</tbody></table>'
        + '<div class="text-muted" style="margin-top:4px;font-size:11px">'
        + '未发合计 ' + so_chain_num(tOpenQty) + '　·　'
        + '列宽：拖拽表头右缘分隔条调整、双击自适应（自动记忆）。'
        + '点「生产」＝展开 生产计划+工单→菲号→工序卡；点「出库」＝展开 出库单明细；同区切换。⤢ 弹窗看全图。'
        + '全工序=全工序已证完成量（proven；估算/未知不计）；入库=已提交 Manufacture 入库净额（毛额−退货）；两者均为已知且不一致时标黄。已发按出库单净额(含退货抵扣)。</div></div>';
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
    $box.find('.so-chain-delivery-so').on('click', function (e) {
        e.preventDefault();
        so_chain_show_delivery(data.sales_order, true);
    });
    $box.find('.so-chain-delivery-global').on('click', function (e) {
        e.preventDefault();
        so_chain_show_delivery(data.sales_order, false);
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
    if (line.reported_status !== undefined) {
        h += '<div style="margin-bottom:6px;font-size:12px"><b>生产证据</b>：全工序 '
           + so_chain_qty_by_status(line.reported, line.all_process_estimated, line.reported_status)
           + '（' + so_chain_esc(line.reported_confidence || 'unknown') + '）'
           + '　入库净额 ' + so_chain_qty_by_status(line.instock, line.instock_estimated, line.instock_status)
           + (line.qc_passed_status ? '　QC ' + so_chain_esc(line.qc_passed_status)
               : (line.qc_status ? '　QC ' + so_chain_esc(line.qc_status) : ''))
           + ((line.evidence_reasons || []).length
               ? '　原因: ' + so_chain_esc(line.evidence_reasons.join(',')) : '')
           + ((line.evidence_conflicts || []).length
               ? '　冲突: ' + so_chain_esc(line.evidence_conflicts.join(',')) : '')
           + '</div>';
    }
    if (line.subassemblies && line.subassemblies.length) {
        h += '<div style="margin-bottom:6px;font-size:12px"><b>子装配件（独立证据，不计入成品）</b>'
           + '<table class="table table-bordered" style="margin:4px 0;font-size:12px">'
           + '<thead><tr><th>物料</th><th>工单</th><th>全工序</th><th>入库净额</th><th>置信度</th></tr></thead><tbody>';
        line.subassemblies.forEach(function (s) {
            const ev = s.all_process_done || {};
            const stock = s.stock_in_posted || {};
            h += '<tr><td>' + so_chain_link('Item', s.production_item, s.production_item || '')
               + '</td><td>' + so_chain_link('Work Order', s.wo, s.wo || '')
               + '</td><td style="text-align:right">' + so_chain_qty_by_status(ev.qty_proven, ev.qty_estimated, ev.qty_status)
               + '</td><td style="text-align:right">' + so_chain_qty_by_status(stock.qty_proven, stock.qty_estimated, stock.qty_status)
               + '</td><td>' + so_chain_esc(ev.confidence || 'unknown') + '</td></tr>';
        });
        h += '</tbody></table></div>';
    }
    if (line.shipment_progress && line.shipment_progress.length) {
        h += '<div style="margin-bottom:6px;font-size:12px"><b>物流进度</b>'
           + '<table class="table table-bordered" style="margin:4px 0;font-size:12px">'
           + '<thead><tr><th>运单</th><th>最新进度</th><th>阶段</th><th>签收</th><th>通途入库</th><th>库存包含</th><th>可售</th></tr></thead><tbody>';
        line.shipment_progress.forEach(function (s) {
            const conflict = !!s.identity_conflict;
            const stageTxt = conflict ? '身份冲突（不展示确定状态）'
                : s.stage === 'signed_pending_tongtool_receipt' ? '已签收·待通途入库'
                : s.stage === 'tongtool_received' ? '通途已入库'
                : s.stage === 'shipped_in_transit' ? '运输中' : '未知/冲突';
            const receipt = (s.receipt_completion && s.receipt_completion !== 'unknown')
                ? s.receipt_completion : '通途入库未接入';
            const incl = s.inventory_inclusion_status === 'included' ? '已包含'
                : (s.inventory_inclusion_status || 'unknown');
            h += '<tr><td>' + so_chain_esc(s.logistic_number || '—')
               + (conflict && (s.shipment_candidates || []).length
                    ? '<br><span class="text-danger" style="font-size:11px">候选: '
                      + so_chain_esc((s.shipment_candidates || []).join(', ')) + '</span>' : '')
               + '</td><td>' + (conflict ? '—' : so_chain_esc(s.latest_progress_status || '—'))
               + '</td><td>' + stageTxt
               + '</td><td>' + (conflict ? '—' : so_chain_esc(s.shipment_signed_at || '—'))
               + '</td><td>' + (conflict ? '—' : so_chain_esc(receipt))
               + '</td><td>' + (conflict ? '—' : so_chain_esc(incl))
               + '</td><td>不可售</td></tr>';
        });
        h += '</tbody></table></div>';
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
           + (w.cancelled ? ' <span class="indicator-pill red">已取消（入库事实保留）</span>' : '')
           + (w.pp ? '　计划 ' + so_chain_link('Production Plan', w.pp, w.pp) : '')
           + (isForgot ? ' <span class="indicator-pill yellow" title="成品工单未完工，但同行的皮壳/内胆已全部完成 —— 疑似忘了点完工">忘点完工?</span>' : '')
           + '　工单量 ' + so_chain_num(w.qty) + '　完成 ' + so_chain_num(w.done)
           + (w.all_process_status ? '（' + so_chain_esc(w.all_process_status) + '）' : '')
           + '　入库 ' + so_chain_num(w.stock_in_posted)
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
        + '<thead><tr><th>出库单</th><th>日期</th><th>状态</th><th>行数</th><th>数量</th><th>类型</th></tr></thead><tbody>';
    dns.forEach(function (d) {
        const ship = (d.docstatus === 1) && !d.is_return;
        const lines = d.lines || [];
        const qtyTxt = (d.is_return ? '<span class="text-danger">' + so_chain_num(d.qty) + '</span>' : so_chain_num(d.qty));
        h += '<tr>'
           + '<td>' + so_chain_link('Delivery Note', d.dn, d.dn) + '</td>'
           + '<td>' + so_chain_esc(d.date) + '</td>'
           + '<td>' + so_chain_t(d.status) + (d.docstatus === 0 ? ' <span class="text-muted">(草稿)</span>' : '') + '</td>'
           + '<td style="text-align:right">' + lines.length + '</td>'
           + '<td style="text-align:right">' + qtyTxt + '</td>'
           + '<td>' + (d.is_return ? '退货(抵扣)' : (ship ? '出库' : '—')) + '</td></tr>';
        if (lines.length > 1) {
            const breakdown = lines.map(function (x) { return so_chain_num(x.qty); }).join(' + ');
            h += '<tr><td colspan="6" style="border-top:none;padding:1px 8px 5px">'
               + '<span class="text-muted" style="font-size:11px">该出库单 ' + lines.length + ' 行：'
               + breakdown + ' = ' + so_chain_num(d.qty) + '</span></td></tr>';
        }
    });
    return h + '</tbody></table>';
}

// ── 数量阶段 / 里程碑 / 分批可售（与批量导出同一份 supply facts）────────────
const SO_CHAIN_STAGE_LABEL = {
    not_planned: '未排产', in_production: '在产', produced_pending_dn: '全工序完成待出库',
    shipped_in_transit: '运输中', arrived_not_sellable: '到货未可售',
    delivered_sellable: '已可售交付', cancelled: '已取消', returned: '退货',
    draft_dn: '草稿出库', over_produced: '超产现存', unknown: '未知'
};
const SO_CHAIN_NODE_LABEL = {
    order_placed: '下单', promised_delivery: '订单交期', production_start: '开工',
    production_end: '完工', dispatch: '出库', departure: '离港',
    arrival: '到港', delivery: '签收'
};

function so_chain_facts_html(facts) {
    const manifest = facts.manifest || {};
    let h = '';
    if (manifest.partial) {
        h += '<div class="text-danger" style="font-size:11px;margin-bottom:6px">部分来源无权限：'
           + so_chain_esc((manifest.notes || []).join('；')) + '</div>';
    }
    const stages = facts.stage_balances || [];
    h += '<div style="font-weight:600;font-size:12px;margin:4px 0">数量阶段（互斥）</div>';
    if (stages.length) {
        h += '<table class="table table-bordered" style="margin:0 0 10px;font-size:12px">'
           + '<thead><tr><th>阶段</th><th>数量</th><th>单位</th><th>明细</th><th>依据/排除</th></tr></thead><tbody>';
        stages.forEach(function (r) {
            h += '<tr><td>' + so_chain_t(SO_CHAIN_STAGE_LABEL[r.stage] || r.stage) + '</td>'
               + '<td style="text-align:right">' + (r.qty == null ? '未知' : so_chain_num(r.qty)) + '</td>'
               + '<td>' + so_chain_esc(r.uom || '-') + '</td>'
               + '<td>' + so_chain_esc(r.stage_detail || '') + '</td>'
               + '<td class="text-muted">' + so_chain_esc(r.exclusion_reason || '') + '</td></tr>';
        });
        h += '</tbody></table>';
    } else {
        h += '<div class="text-muted" style="font-size:12px">无阶段余额</div>';
    }

    const miles = facts.milestones || [];
    h += '<div style="font-weight:600;font-size:12px;margin:4px 0">节点（原计划 / 最新预计 / 实际）</div>';
    if (miles.length) {
        h += '<table class="table table-bordered" style="margin:0 0 10px;font-size:12px">'
           + '<thead><tr><th>节点</th><th>原计划</th><th>承诺</th><th>最新预计</th><th>实际</th><th>来源</th></tr></thead><tbody>';
        miles.forEach(function (m) {
            h += '<tr><td>' + so_chain_t(SO_CHAIN_NODE_LABEL[m.node] || m.node) + '</td>'
               + '<td>' + so_chain_esc(m.baseline_planned_at || '-') + '</td>'
               + '<td>' + so_chain_esc(m.committed_due_at || '-') + '</td>'
               + '<td>' + so_chain_esc(m.latest_expected_at || '-') + '</td>'
               + '<td>' + so_chain_esc(m.actual_at || '-') + '</td>'
               + '<td class="text-muted">' + so_chain_esc(m.source_record || '') + '</td></tr>';
        });
        h += '</tbody></table>';
    } else {
        h += '<div class="text-muted" style="font-size:12px">无节点证据</div>';
    }

    const tranches = facts.availability_schedule || [];
    h += '<div style="font-weight:600;font-size:12px;margin:4px 0">分批可售计划</div>';
    if (tranches.length) {
        h += '<table class="table table-bordered" style="margin:0;font-size:12px">'
           + '<thead><tr><th>片段</th><th>数量</th><th>可售日</th><th>最新预计</th><th>情景</th><th>排除原因</th></tr></thead><tbody>';
        tranches.forEach(function (t) {
            const qty = t.qty == null ? '分配未知' : so_chain_num(t.qty);
            h += '<tr><td>' + so_chain_esc(t.batch_key || t.tranche_id) + '</td>'
               + '<td style="text-align:right">' + qty + '</td>'
               + '<td>' + so_chain_esc(t.available_date || '未知') + '</td>'
               + '<td>' + so_chain_esc(t.latest_expected_at || '-') + '</td>'
               + '<td>' + so_chain_t(t.scenario || '') + '</td>'
               + '<td class="text-muted">' + so_chain_esc(t.exclusion_reason || '') + '</td></tr>';
        });
        h += '</tbody></table>';
    } else {
        h += '<div class="text-muted" style="font-size:12px">无可售片段</div>';
    }
    return h;
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
    const factsId = 'so-chain-facts-' + String(line.so_line || 'line').replace(/[^A-Za-z0-9_-]/g, '');
    const d = new frappe.ui.Dialog({
        title: __('链条明细：') + so + ' / ' + (line.item_name || line.item_code),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'html' }],
    });
    d.fields_dict.html.$wrapper.html('<div style="max-height:72vh;overflow:auto">' + head
        + sec(SO_CHAIN_PROD, '生产链条', so_chain_tree_html(line))
        + sec(SO_CHAIN_DN, '出库', so_chain_dn_html(line))
        + '<div id="' + factsId + '" style="margin-top:10px"></div>'
        + '</div>');
    d.show();
    frappe.call({
        method: 'key_test.supply_facts.get_supply_facts',
        args: { filters: { sales_order: so, so_line: line.so_line, include_delivered: 1 } },
        callback: function (response) {
            const box = document.getElementById(factsId);
            if (box && response && response.message) {
                box.innerHTML = so_chain_facts_html(response.message);
            }
        },
        error: function () {
            const box = document.getElementById(factsId);
            if (box) box.innerHTML = '<div class="text-muted">数量事实加载失败或无权限</div>';
        },
    });
}

// ── 头程物流（独立弹窗）：DN → 运单号 → Shipment 状态/里程碑 + 轨迹 ──────────
function so_chain_head_leg_html(dns) {
    if (!dns || !dns.length) return '<div class="text-muted">无销售出库</div>';
    let anyNumbers = false;
    let h = '';
    dns.forEach(function (d) {
        const numbers = d.numbers || [];
        if (numbers.length) anyNumbers = true;
        h += '<div style="margin:8px 0 4px"><b>' + so_chain_link('Delivery Note', d.dn, d.dn) + '</b>'
           + '　' + so_chain_esc(d.date || '-') + '　' + so_chain_t(d.status)
           + (d.docstatus === 0 ? ' <span class="text-muted">(草稿)</span>' : '')
           + (d.is_return ? ' <span class="text-danger">(退货)</span>' : '') + '</div>';
        if (!numbers.length) {
            h += '<div class="text-muted" style="font-size:12px;margin-left:8px">该出库单未填运单号</div>';
            return;
        }
        h += '<table class="table table-bordered" style="margin:0 0 4px;font-size:12px">'
           + '<thead><tr><th>运单号</th><th>状态</th><th>最新节点</th><th>ETA</th>'
           + '<th>离港</th><th>到港</th><th>签收</th><th>匹配</th></tr></thead><tbody>';
        numbers.forEach(function (n) {
            const events = n.events || [];
            const conflict = !!n.identity_conflict;
            const evidence = n.shipment_evidence || [];
            h += '<tr>'
               + '<td>' + (conflict
                    ? '运单号 ' + so_chain_esc(n.number)
                      + ' <span class="indicator-pill red">身份冲突</span>'
                    : (n.shipment ? so_chain_link('Shipment', n.shipment, n.number) : so_chain_esc(n.number)))
               + (!conflict && n.primary ? ' <span class="text-muted">(主)</span>' : '') + '</td>'
               + '<td>' + (conflict
                    ? '<span class="text-danger">身份冲突：不展示确定状态</span>'
                    : (n.status11 ? so_chain_t(n.status11) : '<span class="text-muted">状态未知</span>')) + '</td>'
               + '<td>' + (conflict ? '-' : so_chain_esc(n.last_node || '-')) + '</td>'
               + '<td>' + (conflict ? '-' : so_chain_esc(n.eta || '-')) + '</td>'
               + '<td>' + (conflict ? '-' : so_chain_esc(n.atd || '-')) + '</td>'
               + '<td>' + (conflict ? '-' : so_chain_esc(n.ata || '-')) + '</td>'
               + '<td>' + (conflict ? '-' : so_chain_esc(n.dlvr || '-')) + '</td>'
               + '<td>' + (conflict ? '-' : so_chain_esc(n.match_status || '-')) + '</td></tr>';
            if (conflict) {
                h += '<tr><td colspan="8" style="border-top:none;padding:2px 8px 6px">'
                   + '<div class="text-danger" style="font-size:11px;margin-bottom:2px">同一运单号对应 '
                   + evidence.length + ' 张 Shipment，拒绝任选代表；以下原值待人工核对。</div>'
                   + '<table class="table" style="margin:4px 0;font-size:11px"><thead><tr>'
                   + '<th>Shipment</th><th>status11</th><th>status4</th><th>离港</th><th>到港</th><th>签收</th></tr></thead><tbody>';
                evidence.forEach(function (e) {
                    h += '<tr><td>' + so_chain_link('Shipment', e.shipment, e.shipment) + '</td>'
                       + '<td>' + so_chain_esc(e.status11 || '-') + '</td>'
                       + '<td>' + so_chain_esc(e.status4 || '-') + '</td>'
                       + '<td>' + so_chain_esc(e.atd || '-') + '</td>'
                       + '<td>' + so_chain_esc(e.ata || '-') + '</td>'
                       + '<td>' + so_chain_esc(e.dlvr || '-') + '</td></tr>';
                });
                h += '</tbody></table></td></tr>';
            } else if (events.length) {
                h += '<tr><td colspan="8" style="border-top:none;padding:2px 8px 6px">'
                   + '<details><summary class="text-muted" style="font-size:11px;cursor:pointer">轨迹 '
                   + events.length + ' 个节点</summary>'
                   + '<table class="table" style="margin:4px 0;font-size:11px"><thead><tr>'
                   + '<th>时间</th><th>节点</th><th>地点</th><th>描述</th></tr></thead><tbody>';
                events.forEach(function (e) {
                    h += '<tr><td>' + so_chain_esc(e.time || e.date || '') + '</td>'
                       + '<td>' + so_chain_esc(e.name || '') + '</td>'
                       + '<td>' + so_chain_esc(e.location || '') + '</td>'
                       + '<td>' + so_chain_esc(e.description || '') + '</td></tr>';
                });
                h += '</tbody></table></details></td></tr>';
            }
        });
        h += '</tbody></table>';
    });
    return (anyNumbers ? '' : '<div class="text-muted" style="margin-bottom:6px">有出库单，但未填运单号</div>') + h;
}

function so_chain_show_logistics(data, so) {
    const perms = data.permissions || {};
    const eventStatus = (data.source_status || {}).shipment_logistics_event || {};
    const eventWarn = eventStatus.available === false
        ? '<div class="text-danger" style="margin-bottom:6px">物流事件读取失败（'
          + so_chain_esc(eventStatus.reason || 'unknown')
          + '），状态/轨迹不完整（partial）。</div>' : '';
    const head = '<div style="margin-bottom:6px"><b>'
        + so_chain_link('Item', data.item_code, data.item_code) + '</b>'
        + (data.item_name ? '　' + so_chain_esc(data.item_name) : '') + '</div>';
    let body;
    if (perms.delivery_note === false) {
        body = '<div class="text-muted">无 Delivery Note 读取权限，无法显示头程物流。</div>';
    } else if (perms.shipment === false) {
        body = '<div class="text-muted">无 Shipment 读取权限，运单状态不可见。</div>';
    } else {
        body = eventWarn + so_chain_head_leg_html(data.dns || []);
    }
    const d = new frappe.ui.Dialog({
        title: __('头程物流：') + so + ' / ' + (data.item_name || data.item_code),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'html' }],
    });
    d.fields_dict.html.$wrapper.html('<div style="max-height:72vh;overflow:auto">' + head
        + '<div style="border:1px solid ' + SO_CHAIN_HEAD + ';border-radius:4px;padding:8px 10px">'
        + body + '</div></div>');
    d.show();
}

// ── 实际交付 / 未关联 SO（DN 明细为锚，独立只读事实层）────────────────────
function so_chain_delivery_html(msg) {
    msg = msg || {};
    const lines = msg.delivery_lines || [];
    const cov = msg.coverage || {};
    const pg = msg.pagination || {};
    let h = '<div style="font-size:12px;margin-bottom:6px">'
        + '范围 ' + so_chain_esc((msg.scope || {}).version || 'unknown')
        + '　·　DN ' + so_chain_num(cov.delivery_notes ? cov.delivery_notes.total : 0)
        + '　·　行 ' + so_chain_num(pg.total || lines.length)
        + '　·　' + so_chain_esc(pg.termination_reason || '')
        + (cov.restricted ? '　<span class="text-danger">含受限来源（partial）</span>' : '')
        + '</div>'
        + '<div class="text-muted" style="font-size:11px;margin-bottom:4px">'
        + '未关联/冲突/范围外行保留原值；候选 SO 仅供人工审核，不自动回写。</div>'
        + '<table class="table table-bordered" style="margin:0;font-size:12px">'
        + '<thead><tr><th>DN</th><th>商品</th><th>客户</th><th>日期</th><th>数量</th>'
        + '<th>实际</th><th>关联</th><th>范围</th><th>目标仓</th><th>物流</th><th>原因</th></tr></thead><tbody>';
    lines.forEach(function (l) {
        const highlight = l.association_status === 'unlinked'
            ? ' background:#fff9e6' : '';
        h += '<tr style="' + highlight + '">'
            + '<td>' + so_chain_link('Delivery Note', l.delivery_note, l.delivery_note)
            + '<div class="text-muted" style="font-size:10px">' + so_chain_esc(l.delivery_note_item) + '</div></td>'
            + '<td>' + so_chain_esc(l.item_code || '-') + '</td>'
            + '<td>' + so_chain_esc(l.customer || '-') + '</td>'
            + '<td>' + so_chain_esc(l.posting_date || '-') + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.qty) + ' ' + so_chain_esc(l.uom || '') + '</td>'
            + '<td style="text-align:right">' + so_chain_num(l.actual_qty) + '</td>'
            + '<td>' + so_chain_esc(l.association_status || 'unknown') + '</td>'
            + '<td>' + so_chain_esc(l.relevance_status || 'unknown') + '</td>'
            + '<td>' + so_chain_esc(l.target_warehouse || '未知') + '</td>'
            + '<td>' + so_chain_esc(l.logistics_status || 'unknown') + '</td>'
            + '<td>' + so_chain_esc((l.conflicts || []).concat(l.unknown_reasons || []).join(',')) + '</td></tr>';
    });
    if (!lines.length) {
        h += '<tr><td colspan="11" class="text-muted">当前筛选无记录（不代表 0）</td></tr>';
    }
    return h + '</tbody></table>';
}

function so_chain_show_delivery(so, onlySo) {
    let offset = 0;
    const limit = 200;
    const d = new frappe.ui.Dialog({
        title: (onlySo ? __('本 SO 实际交付：') : __('全局实际交付：')) + (so || ''),
        size: 'extra-large',
        fields: [
            { fieldtype: 'Data', fieldname: 'customer', label: __('客户') },
            { fieldtype: 'Data', fieldname: 'item_code', label: __('商品') },
            { fieldtype: 'Date', fieldname: 'from_date', label: __('从') },
            { fieldtype: 'Date', fieldname: 'to_date', label: __('到') },
            { fieldtype: 'Select', fieldname: 'association_status', label: __('关联状态'),
              options: '
linked
so_header_only
unlinked
ambiguous
conflict
restricted' },
            { fieldtype: 'Check', fieldname: 'include_unlinked', label: __('含未关联'),
              default: onlySo ? 0 : 1 },
            { fieldtype: 'HTML', fieldname: 'html' },
        ],
    });
    const refresh = function () {
        const values = d.get_values() || {};
        const filters = {
            limit: limit, offset: offset,
            include_unlinked: onlySo ? 0 : (values.include_unlinked ? 1 : 0),
        };
        if (onlySo && so) filters.sales_order = so;
        ['customer', 'item_code', 'from_date', 'to_date', 'association_status'].forEach(function (key) {
            if (values[key]) filters[key] = values[key];
        });
        frappe.call({
            method: 'key_test.delivery_facts.get_delivery_facts',
            args: { filters: JSON.stringify(filters) },
            callback: function (r) {
                const msg = r.message || {};
                const pg = msg.pagination || {};
                const total = Number(pg.total || 0);
                const pageNo = Math.floor(offset / limit) + 1;
                const pages = Math.max(1, Math.ceil(total / limit));
                const nav = '<div style="margin:6px 0;font-size:12px">'
                    + '<a href="#" class="delivery-prev" style="margin-right:12px">上一页</a>'
                    + '第 ' + pageNo + ' / ' + pages + ' 页　共 ' + total + ' 行'
                    + '<a href="#" class="delivery-next" style="margin-left:12px">下一页</a></div>';
                d.fields_dict.html.$wrapper.html(so_chain_delivery_html(msg) + nav);
                d.fields_dict.html.$wrapper.find('.delivery-prev').on('click', function (e) {
                    e.preventDefault();
                    if (offset >= limit) { offset -= limit; refresh(); }
                });
                d.fields_dict.html.$wrapper.find('.delivery-next').on('click', function (e) {
                    e.preventDefault();
                    if (offset + limit < total) { offset += limit; refresh(); }
                });
            },
        });
    };
    d.fields_dict.html.$wrapper.html('<div class="text-muted">加载中…</div>');
    d.show();
    refresh();
    ['customer', 'item_code', 'from_date', 'to_date',
     'association_status', 'include_unlinked'].forEach(function (name) {
        const field = d.fields_dict[name];
        if (field && field.$input) {
            field.$input.on('change', function () { offset = 0; refresh(); });
        }
    });
}
