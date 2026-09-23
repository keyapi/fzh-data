// ─────────────────────────────────────────────────────────────────────
// 「创建通途采购单」按钮 —— 插入 delivery_plan/public/js/delivery_note.js
//
// 插入位置：frappe.ui.form.on('Delivery Note', { refresh: ... }) 内，
//          「导出报关单据」按钮之后。
// 配套后端：delivery_plan/api/tongtool_purchase_api.py
// 改完需 clear-cache + 浏览器硬刷新（JS 无需 restart）。
// ─────────────────────────────────────────────────────────────────────

// ---- ① 插进 refresh 里，紧跟「导出报关单据」按钮之后 ----
//
// 注意：支持客户列表在服务端 delivery_plan/utils/tongtool_purchase.py
// 的 COMPANY_CUSTOMER_GROUP 里，此处仅为置灰用的镜像，服务端仍会再校验一次。

        // 创建通途采购单按钮（仅已提交状态显示；非三大客户置灰）
        if (frm.doc.docstatus === 1) {
            var ttp_supported = ["CENTRADE", "DANEEY", "波兰公司"].indexOf(frm.doc.customer) >= 0;
            frm.add_custom_button(__("创建通途采购单"), function() {
                if (!ttp_supported) {
                    frappe.msgprint(__("仅 CENTRADE（美东）/ DANEEY（美中）/ 波兰公司 的销售出库单可创建通途采购单。"));
                    return;
                }
                tongtool_open_purchase_dialog(frm);
            }, __("工具"));
            if (!ttp_supported) {
                var $ttp_btn = frm.custom_buttons[__("创建通途采购单")];
                if ($ttp_btn) {
                    $ttp_btn.prop("disabled", true).addClass("disabled")
                        .attr("title", __("仅 CENTRADE / DANEEY / 波兰公司 可创建"));
                }
            }
        }

// ---- ② 文件末尾（module 作用域）追加以下函数 ----

// 配置里存的是 ID（通途的 purchaseUserId / warehouseIdKey / supplierId），
// 下拉框显示 label；建「label → ID」索引。
// rows 原样返回，给 Autocomplete 用（它自己认 {label, value}）。
function tongtool_build_options(rows) {
    var map = {};
    var options = [];
    var raw = [];
    (rows || []).forEach(function(row) {
        if (!row.label) return;
        map[row.label] = row.value;
        options.push(row.label);
        raw.push({ label: row.label, value: row.value });
    });
    return { map: map, options: options, rows: raw };
}

function tongtool_preview_html(preview) {
    var html = '<div class="ttp-preview">';

    if (preview.message) {
        html += '<p class="text-danger">' + frappe.utils.escape_html(preview.message) + '</p>';
    }

    if (preview.lines && preview.lines.length) {
        html += "<p>" + __("将创建 {0} 行采购明细：", [preview.lines.length]) + "</p>";
        html += '<table class="table table-bordered" style="margin-bottom:8px">';
        html += "<thead><tr><th>" + __("物料") + "</th><th>" + __("通途SKU") + "</th>"
              + "<th>" + __("数量") + "</th></tr></thead><tbody>";
        preview.lines.forEach(function(line) {
            html += "<tr><td>" + frappe.utils.escape_html(line.item_code)
                  + (line.note ? '<br><small class="text-muted">' + frappe.utils.escape_html(line.note) + '</small>' : "")
                  + "</td><td>" + frappe.utils.escape_html(line.tt_sku) + "</td>"
                  + "<td>" + line.qty + "</td></tr>";
        });
        html += "</tbody></table>";
    } else if (!preview.message) {
        html += '<p class="text-danger">' + __("没有任何明细行匹配到通途货品，无法创建采购单。") + "</p>";
    }

    if (preview.merged && preview.merged.length) {
        html += '<p style="margin-bottom:4px"><b>' + __("实际将采购（按货品合计）：") + "</b></p>";
        html += '<table class="table table-bordered" style="margin-bottom:8px">';
        html += "<thead><tr><th>" + __("通途SKU") + "</th><th>" + __("合计数量") + "</th></tr></thead><tbody>";
        preview.merged.forEach(function(m) {
            html += "<tr><td>" + frappe.utils.escape_html(m.tt_sku) + "</td><td>" + m.qty + "</td></tr>";
        });
        html += "</tbody></table>";
    }

    if (preview.unmatched && preview.unmatched.length) {
        html += '<p class="text-danger">' + __("以下 {0} 行未匹配，不会被采购：", [preview.unmatched.length]) + "</p>";
        html += '<ul class="text-danger" style="margin-bottom:8px">';
        preview.unmatched.forEach(function(row) {
            html += "<li>" + frappe.utils.escape_html(row.item_code) + " — "
                  + frappe.utils.escape_html(row.reason) + "</li>";
        });
        html += "</ul>";
    }

    html += "</div>";
    return html;
}

function tongtool_open_purchase_dialog(frm) {
    // 已有采购单号：先尝试清空。
    // 服务端只允许「通途那边已作废(status=4)」的情况，未作废会直接报错。
    if (frm.doc.custom_tongtool_purchase_order) {
        frappe.confirm(
            __("该销售出库单已有通途采购单 <b>{0}</b>。<br><br>若它已在通途作废，将清空单号并重新创建；<b>未作废则会被拒绝</b>。",
               [frm.doc.custom_tongtool_purchase_order]),
            function () {
                frappe.call({
                    method: "delivery_plan.api.tongtool_purchase_api.reset_purchase_order",
                    args: { delivery_note: frm.doc.name },
                    callback: function (r) {
                        if (!r.message) return;
                        frappe.show_alert({
                            message: __("已清空采购单号 {0}（通途已作废）", [r.message.cleared]),
                            indicator: "green"
                        });
                        frm.doc.custom_tongtool_purchase_order = null;
                        if (frm.fields_dict.custom_tongtool_purchase_order) {
                            frm.refresh_field("custom_tongtool_purchase_order");
                        }
                        tongtool_fetch_and_show(frm);
                    }
                });
            }
        );
        return;
    }
    tongtool_fetch_and_show(frm);
}

function tongtool_fetch_and_show(frm) {
    frappe.dom.freeze(__("正在解析通途货品，请稍候…"));

    frappe.call({
        method: "delivery_plan.api.tongtool_purchase_api.get_purchase_options",
        callback: function(opt_res) {
            if (!opt_res.message) { frappe.dom.unfreeze(); return; }
            frappe.call({
                method: "delivery_plan.api.tongtool_purchase_api.preview_purchase_order",
                args: { delivery_note: frm.doc.name },
                callback: function(prev_res) {
                    frappe.dom.unfreeze();
                    if (!prev_res.message) return;
                    tongtool_show_purchase_dialog(frm, opt_res.message, prev_res.message);
                },
                error: function() { frappe.dom.unfreeze(); }
            });
        },
        error: function() { frappe.dom.unfreeze(); }
    });
}

function tongtool_show_purchase_dialog(frm, options, preview) {
    var users = tongtool_build_options(options.purchase_users);
    var warehouses = tongtool_build_options(options.warehouses);
    var suppliers = tongtool_build_options(options.suppliers);
    var currency = preview.currency || options.currency || "USD";

    var dialog = new frappe.ui.Dialog({
        title: __("创建通途采购单") + " · " + frm.doc.name,
        size: "large",
        fields: [
            { fieldtype: "HTML", fieldname: "preview_html", options: tongtool_preview_html(preview) },
            { fieldtype: "Section Break", label: __("采购单参数") },
            {
                fieldtype: "Select", fieldname: "purchase_user", label: __("采购人员"), reqd: 1,
                options: users.options,
                default: users.options.length === 1 ? users.options[0] : ""
            },
            {
                fieldtype: "Select", fieldname: "warehouse", label: __("采购仓库"), reqd: 1,
                options: warehouses.options,
                default: warehouses.options.length === 1 ? warehouses.options[0] : ""
            },
            {
                fieldtype: "Autocomplete", fieldname: "supplier", label: __("供应商"), reqd: 1,
                options: suppliers.rows,
                description: __("输入任意关键字模糊搜索（如「绍兴」「宝安」）")
            },
            { fieldtype: "Column Break" },
            { fieldtype: "Data", fieldname: "currency_display", label: __("币种"), read_only: 1, default: currency },
            { fieldtype: "Data", fieldname: "external_display", label: __("外部流水号"),
              read_only: 1, default: preview.logistic_number || "",
              description: __("取自销售出库的物流单号，创建后不可修改") },
            { fieldtype: "Float", fieldname: "shipping_fee", label: __("运费"), default: preview.logistic_cost || 0 },
            { fieldtype: "Small Text", fieldname: "remark", label: __("备注") }
        ],
        primary_action_label: __("创建通途采购单"),
        primary_action: function(values) {
            var line_count = (preview.lines || []).length;
            if (!line_count) {
                frappe.msgprint(__("没有可采购的明细行。"));
                return;
            }
            var msg = __("将向通途创建 1 张采购单，共 {0} 行明细。", [line_count]);
            if (preview.unmatched && preview.unmatched.length) {
                msg += "<br><span class='text-danger'>"
                     + __("另有 {0} 行未匹配，不会被采购。", [preview.unmatched.length]) + "</span>";
            }
            msg += "<br><br>" + __("确认真实写入通途？");

            frappe.confirm(msg, function() {
                dialog.disable_primary_action();
                frappe.call({
                    method: "delivery_plan.api.tongtool_purchase_api.create_purchase_order",
                    args: {
                        delivery_note: frm.doc.name,
                        purchase_user_id: users.map[values.purchase_user],
                        warehouse_id_key: warehouses.map[values.warehouse],
                        // Autocomplete 已经把 label 映射回 value 了，直接用
                        supplier_id: values.supplier,
                        currency: currency,
                        shipping_fee: values.shipping_fee || 0,
                        remark: values.remark || null,
                        lines: preview.lines
                    },
                    callback: function(r) {
                        if (!r.message) { dialog.enable_primary_action(); return; }
                        dialog.hide();
                        frappe.msgprint({
                            title: __("通途采购单已创建"),
                            indicator: "green",
                            message: __("采购单号：{0}", [r.message.purchase_order_code])
                        });
                        frm.reload_doc();
                    },
                    error: function() { dialog.enable_primary_action(); }
                });
            });
        }
    });

    dialog.show();
}
