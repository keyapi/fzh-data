// 工单自定义脚本
frappe.ui.form.on('Work Order', {
    refresh: function(frm) {
        // 检查当前用户是否有生产经理角色
        const has_production_manager_role = frappe.user.has_role('Manufacturing Manager');
        
        // 检查是否是拆分工单
        if (frm.doc.custom_is_split_work_order) {
            // 添加查看批次信息按钮
            frm.add_custom_button(__('查看批次跟踪'), function() {
                show_batch_tracking_dialog(frm);
            }, __('批次'));
            
            // 添加使用批次发料按钮
            frm.add_custom_button(__('按批次发料'), function() {
                create_batch_material_issue(frm);
            }, __('批次'));
            
            // 显示批次信息
            show_batch_info(frm);
        }
        
        // 添加"打印生产工单条码"按钮（所有工单都可用）
        frm.add_custom_button(__('打印生产工单条码'), function() {
            print_work_order_barcode(frm);
        }, __('打印工具')).css({
            'background-color': '#17a2b8',
            'border-color': '#17a2b8',
            'color': 'white'
        });

        // 变更物料：支持对所需物料进行添加、修改（需求数量）、删除操作
        // 放置在「面料处理」下拉菜单中
        if (frm.doc.docstatus === 1 && frm.doc.status !== 'Completed' && frm.doc.status !== 'Closed') {
            frm.add_custom_button(__('变更物料'), function() {
                show_update_required_items_dialog(frm);
            }, __('面料处理')).css({
                'background-color': '#6c42d6',
                'border-color': '#6c42d6',
                'color': 'white'
            });

            // 重新同步 BOM：从 BOM 重新拉取所有物料
            frm.add_custom_button(__('重新同步BOM'), function() {
                show_resync_bom_dialog(frm);
            }, __('面料处理')).css({
                'background-color': '#fd7e14',
                'border-color': '#fd7e14',
                'color': 'white'
            });
        }
        
        // 只在提交状态的情况下显示一键操作按钮
        if (frm.doc.docstatus === 1) {
            // 添加一键工单入库按钮 - 仅对生产经理角色开放
            if (has_production_manager_role && 
                ["In Process", "Not Started"].includes(frm.doc.status) && 
                flt(frm.doc.produced_qty) < flt(frm.doc.qty)) {
                
                frm.add_custom_button(__('一键工单入库'), function() {
                    // 先检查库存是否足够
                    frappe.call({
                        method: "key_test.production_utils.check_stock_for_work_order",
                        args: {
                            "work_order_id": frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __("检查库存中..."),
                        callback: function(check_r) {
                            if (check_r.message && check_r.message.insufficient_items && check_r.message.insufficient_items.length > 0) {
                                // 库存不足，显示不足的物料并询问是否继续
                                let message = __("以下物料库存不足，可能无法完成工单入库：") + "<br><br>";
                                check_r.message.insufficient_items.forEach(item => {
                                    message += `<b>${item.item_code}</b>: ${item.item_name || ""} - 
                                                需要 ${item.required_qty} ${item.stock_uom}, 
                                                仓库 ${item.warehouse} 中只有 ${item.available_qty}<br>`;
                                });
                                
                                message += "<br>" + __("确定要继续创建工单入库单吗？");
                                
                                frappe.confirm(
                                    message,
                                    // 继续创建
                                    function() {
                                        create_manufacture_entry(frm);
                                    },
                                    // 取消操作
                                    function() {
                                        frappe.msgprint(__("已取消工单入库操作"));
                                    }
                                );
                            } else {
                                // 库存充足，直接创建工单入库单
                                create_manufacture_entry(frm);
                            }
                        }
                    });
                }).css({
                    'background-color': '#2490ef',
                    'color': 'white',
                    'border': 'none',
                    'border-radius': '4px',
                    'padding': '6px 12px',
                    'font-size': '14px'
                });
            } else if (!has_production_manager_role && 
                       ["In Process", "Not Started"].includes(frm.doc.status) && 
                       flt(frm.doc.produced_qty) < flt(frm.doc.qty)) {
                // 非生产经理角色，显示禁用状态的按钮
                frm.add_custom_button(__('一键工单入库（需生产经理权限）'), function() {
                    frappe.msgprint({
                        title: __('权限不足'),
                        indicator: 'red',
                        message: __('此功能仅对生产经理角色开放')
                    });
                }).css({
                    'background-color': '#cccccc',
                    'color': '#666666',
                    'border': 'none',
                    'border-radius': '4px',
                    'padding': '6px 12px',
                    'font-size': '14px',
                    'cursor': 'not-allowed',
                    'opacity': '0.7'
                });
            }
            
            // 添加绕过创建提交加工单的按钮 - 仅对生产经理角色开放
            if (has_production_manager_role) {
                frm.add_custom_button(__('绕过创建提交加工单'), function() {
                    frappe.call({
                        method: "key_test.production_utils.create_job_cards_for_operations",
                        args: {
                            work_order: frm.doc.name
                        },
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint(r.message);
                                frm.reload_doc();
                            }
                        }
                    });
                }).css({
                    'background-color': '#5cb85c',
                    'color': 'white',
                    'border': 'none',
                    'border-radius': '4px',
                    'padding': '6px 12px',
                    'font-size': '14px'
                });
            }
            
            // 添加一键完成生产的按钮，整合创建Job Card和工单入库 - 仅对生产经理角色开放
            if (has_production_manager_role && 
                frm.doc.skip_transfer && 
                ["Not Started", "In Process"].includes(frm.doc.status) && 
                flt(frm.doc.produced_qty) < flt(frm.doc.qty)) {
                
                frm.add_custom_button(__('一键完成生产'), function() {
                    frappe.confirm(
                        __('这将创建并提交所有加工单，并完成工单入库。确定继续吗？'),
                        function() {
                            // 先检查库存是否足够
                            frappe.call({
                                method: "key_test.production_utils.check_stock_for_work_order",
                                args: {
                                    "work_order_id": frm.doc.name
                                },
                                freeze: true,
                                freeze_message: __("检查库存中..."),
                                callback: function(check_r) {
                                    if (check_r.message && check_r.message.insufficient_items && check_r.message.insufficient_items.length > 0) {
                                        // 库存不足，显示不足的物料并询问是否继续
                                        let message = __("以下物料库存不足，可能无法完成工单入库：") + "<br><br>";
                                        check_r.message.insufficient_items.forEach(item => {
                                            message += `<b>${item.item_code}</b>: ${item.item_name || ""} - 
                                                        需要 ${item.required_qty} ${item.stock_uom}, 
                                                        仓库 ${item.warehouse} 中只有 ${item.available_qty}<br>`;
                                        });
                                        
                                        message += "<br>" + __("确定要继续一键完成生产操作吗？");
                                        
                                        frappe.confirm(
                                            message,
                                            // 继续创建
                                            function() {
                                                execute_one_click_complete(frm);
                                            },
                                            // 取消操作
                                            function() {
                                                frappe.msgprint(__("已取消一键完成生产操作"));
                                            }
                                        );
                                    } else {
                                        // 库存充足，直接执行一键完成
                                        execute_one_click_complete(frm);
                                    }
                                }
                            });
                        }
                    );
                }).addClass("btn-primary").css({
                    'background-color': '#ff5858',
                    'color': 'white',
                    'border': 'none',
                    'border-radius': '4px',
                    'padding': '6px 12px',
                    'font-size': '14px',
                    'font-weight': 'bold'
                });
            } else if (!has_production_manager_role && 
                       frm.doc.skip_transfer && 
                       ["Not Started", "In Process"].includes(frm.doc.status) && 
                       flt(frm.doc.produced_qty) < flt(frm.doc.qty)) {
                // 非生产经理角色，显示禁用状态的按钮
                frm.add_custom_button(__('一键完成生产（需生产经理权限）'), function() {
                    frappe.msgprint({
                        title: __('权限不足'),
                        indicator: 'red',
                        message: __('此功能仅对生产经理角色开放')
                    });
                }).addClass("btn-primary").css({
                    'background-color': '#cccccc',
                    'color': '#666666',
                    'border': 'none',
                    'border-radius': '4px',
                    'padding': '6px 12px',
                    'font-size': '14px',
                    'font-weight': 'bold',
                    'cursor': 'not-allowed',
                    'opacity': '0.7'
                });
            }
        }
    },
    
    // 监听物料需求表格更新
    required_items_on_form_rendered: function(frm) {
        if (frm.doc.custom_is_split_work_order) {
            highlight_batch_items(frm);
        }
    }
});

// 高亮显示带批次的物料行
function highlight_batch_items(frm) {
    frm.doc.required_items.forEach(function(item, i) {
        if (item.custom_batch_no) {
            $(`div[data-fieldname="required_items"] .grid-row[data-idx="${i+1}"]`)
                .css("background-color", "rgba(212, 244, 252, 0.3)");
            
            // 在行内显示批次信息
            let batch_info = $(`<div class="batch-tag">批次: ${item.custom_batch_no}</div>`)
                .css({
                    "color": "#2490ef",
                    "font-weight": "bold",
                    "margin-top": "5px"
                });
                
            $(`div[data-fieldname="required_items"] .grid-row[data-idx="${i+1}"] .grid-static-col:last`)
                .append(batch_info);
        }
    });
}

// 显示批次信息指示器
function show_batch_info(frm) {
    // 清除原有内容
    frm.dashboard.clear_headline();
    
    // 查询批次状态
    frappe.call({
        method: "work_order_task.work_order_task.utils.stock_entry.get_batch_consumed_qty",
        args: {
            work_order_name: frm.doc.name
        },
        callback: function(r) {
            if (r.message) {
                let data = r.message;
                if (data.key_material && data.batch_no) {
                    // 创建批次信息显示
                    let batch_info = $(`
                        <div class="batch-tracking-info">
                            <span class="indicator ${data.pending_qty > 0 ? 'orange' : 'green'}" data-toggle="tooltip" 
                                title="关键物料: ${data.key_material}, 批次: ${data.batch_no}">
                                <span>批次跟踪: ${data.batch_no}</span>
                            </span>
                            <span class="usage-info ml-2">
                                计划用量: ${data.actual_usage} | 已消耗: ${data.consumed_qty} | 待消耗: ${data.pending_qty}
                            </span>
                        </div>
                    `).css({
                        "font-size": "12px",
                        "margin-top": "10px"
                    });
                    
                    frm.dashboard.set_headline_alert(batch_info);
                }
            }
        }
    });
}

// 批次跟踪对话框
function show_batch_tracking_dialog(frm) {
    frappe.call({
        method: "work_order_task.work_order_task.utils.stock_entry.get_batch_consumed_qty",
        args: {
            work_order_name: frm.doc.name
        },
        callback: function(r) {
            if (r.message) {
                let data = r.message;
                
                // 创建对话框
                let d = new frappe.ui.Dialog({
                    title: __('批次跟踪信息'),
                    fields: [
                        {
                            fieldname: 'key_material_section',
                            fieldtype: 'Section Break',
                            label: __('关键物料信息')
                        },
                        {
                            fieldname: 'key_material',
                            fieldtype: 'Link',
                            label: __('关键物料'),
                            options: 'Item',
                            read_only: 1,
                            default: data.key_material
                        },
                        {
                            fieldname: 'batch_no',
                            fieldtype: 'Link',
                            label: __('批次'),
                            options: 'Batch',
                            read_only: 1,
                            default: data.batch_no
                        },
                        {
                            fieldname: 'col_break1',
                            fieldtype: 'Column Break'
                        },
                        {
                            fieldname: 'actual_usage',
                            fieldtype: 'Float',
                            label: __('计划用量'),
                            read_only: 1,
                            default: data.actual_usage
                        },
                        {
                            fieldname: 'available_qty',
                            fieldtype: 'Float',
                            label: __('批次可用数量'),
                            read_only: 1,
                            default: data.available_qty
                        },
                        {
                            fieldname: 'tracking_section',
                            fieldtype: 'Section Break',
                            label: __('批次消耗跟踪')
                        },
                        {
                            fieldname: 'consumed_qty',
                            fieldtype: 'Float',
                            label: __('已消耗数量'),
                            read_only: 1,
                            default: data.consumed_qty
                        },
                        {
                            fieldname: 'pending_qty',
                            fieldtype: 'Float',
                            label: __('待消耗数量'),
                            read_only: 1,
                            default: data.pending_qty
                        },
                    ],
                    primary_action_label: __('确定'),
                    primary_action: function() {
                        d.hide();
                    }
                });
                
                d.show();
            }
        }
    });
}

// 创建批次物料发料
function create_batch_material_issue(frm) {
    frappe.call({
        method: "work_order_task.work_order_task.utils.stock_entry.make_material_issue_for_split_work_order",
        args: {
            work_order: frm.doc.name
        },
        callback: function(r) {
            if (r.message) {
                let stock_entry = r.message;
                frappe.model.sync(stock_entry);
                frappe.set_route("Form", stock_entry.doctype, stock_entry.name);
            }
        }
    });
}

// 为工单物料子表添加事件
frappe.ui.form.on('Work Order Item', {
    form_render: function(frm, cdt, cdn) {
        // 高亮显示自定义字段
        let row = locals[cdt][cdn];
        if (row.custom_batch_no) {
            let field_area = frm.fields_dict.required_items.grid.grid_rows_by_docname[cdn].grid_form
                .fields_dict.custom_batch_no.$wrapper;
                
            field_area.css('background-color', 'rgba(212, 244, 252, 0.3)');
        }
    }
}); 

/**
 * 打印生产工单条码
 * 使用已创建的打印格式模板来生成条码标签
 * @param {Object} frm - 表单对象
 */
function print_work_order_barcode(frm) {

    // 定义目标状态列表
    const target_statuses = ['Completed', 'Closed', 'Cancelled'];
    const status_map = {
        'Completed': '已完成',
        'Closed': '已关闭',
        'Cancelled': '已取消'
    };
    // 检查工单状态
    if (target_statuses.includes(frm.doc.status)) {
        frappe.msgprint({
            title: __('提示'),
            message: `${status_map[frm.doc.status]} 状态的工单不允许再次打印条码`,
            indicator: 'orange'
        });
        return;
    }

    // 检查工单状态
    if (!frm.doc.name) {
        frappe.msgprint({
            title: '提示',
            message: '请先保存工单',
            indicator: 'orange'
        });
        return;
    }
    
    // 检查必要字段
    if (!frm.doc.production_item) {
        frappe.msgprint({
            title: '提示',
            message: '工单缺少成品信息',
            indicator: 'orange'
        });
        return;
    }
    
    // 显示加载提示
    frappe.show_alert({
        message: '正在准备打印格式...',
        indicator: 'blue'
    }, 2);
    
    // 构建打印格式URL
    const docType = frm.doctype;
    const docName = frm.doc.name;
    const printFormatName = '打印 生产工单 标签'; // 使用您创建的打印格式名称
    
    // 使用Frappe标准打印格式URL
    const printUrl = `/app/print/${encodeURIComponent(docType)}/${encodeURIComponent(docName)}?format=${encodeURIComponent(printFormatName)}&_print_source=work_order_barcode_button`;
    
    // 在新窗口中打开打印预览
    openWorkOrderPrintPreview(printUrl);
}

/**
 * 打开工单打印预览
 * @param {string} printUrl - 打印预览URL
 */
function openWorkOrderPrintPreview(printUrl) {
    try {
        // 在新窗口中打开打印预览
        const printWindow = window.open(printUrl, '_blank');
        if (!printWindow) {
            frappe.msgprint({
                title: '错误',
                message: '无法打开新窗口，请检查浏览器弹窗设置',
                indicator: 'red'
            });
            return;
        }
        
        // 显示成功提示
        frappe.show_alert({
            message: '打印预览已打开，请查看工单条码标签',
            indicator: 'green'
        }, 5);
        
        // 监听窗口关闭事件，提供额外提示
        const checkClosed = setInterval(() => {
            if (printWindow.closed) {
                clearInterval(checkClosed);
                frappe.show_alert({
                    message: '打印预览已关闭',
                    indicator: 'blue'
                }, 2);
            }
        }, 1000);
        
    } catch (e) {
        frappe.msgprint({
            title: '错误',
            message: `打开打印预览失败: ${e.message}`,
            indicator: 'red'
        });
    }
}

/**
 * 变更物料对话框
 * 支持对所需物料进行添加、修改（需求数量）、删除操作
 * @param {Object} frm - 表单对象
 */
function show_update_required_items_dialog(frm) {
    if (!frm.doc.name) {
        frappe.msgprint({ title: __('提示'), message: __('请先保存工单'), indicator: 'orange' });
        return;
    }

    // 获取子表元数据
    const child_meta = frappe.get_meta('Work Order Item');
    const get_precision = (fieldname) => {
        const field = child_meta.fields.find((f) => f.fieldname === fieldname);
        return field ? field.precision : 2;
    };

    // 准备数据：包含关键字段
    const data = frm.doc.required_items.map((d, idx) => {
        return {
            docname: d.name,
            idx: idx + 1,
            item_code: d.item_code,
            item_name: d.item_name,
            required_qty: d.required_qty,
            source_warehouse: d.source_warehouse,
            transferred_qty: d.transferred_qty || 0,
            consumed_qty: d.consumed_qty || 0,
            operation: d.operation,
        };
    });

    // 定义表格字段
    const fields = [
        {
            fieldtype: 'Data',
            fieldname: 'docname',
            read_only: 1,
            hidden: 1,
            label: __('ID'),
        },
        {
            fieldtype: 'Link',
            fieldname: 'item_code',
            options: 'Item',
            in_list_view: 1,
            read_only: 0,
            disabled: 0,
            label: __('物料'),
            get_query: function() {
                return {
                    query: 'erpnext.controllers.queries.item_query',
                    filters: { is_stock_item: 1 },
                };
            },
            onchange: function() {
                // 这段要足够健壮：定位不到当前行就安静跳过，绝不抛错。
                // 旧版直接读 me.doc.idx —— this.doc 为空时抛 TypeError，
                // 后面那次 get_item_details 就根本不会发出，物料名称留空。
                try {
                    const me = this;
                    const code = me.value;
                    if (!code) return;

                    const grid = dialog.fields_dict.trans_items.grid;
                    const rows = dialog.fields_dict.trans_items.df.data || [];

                    // 行定位：this.doc 不一定存在（整表 grid.refresh() 之后会丢），依次回退
                    const row = me.doc
                        || (grid && grid.current_row && grid.current_row.doc)
                        || null;
                    const row_data =
                        rows.find((d) => d && row && String(d.idx) === String(row.idx))
                        || rows.slice().reverse().find(
                            (d) => d && d.item_code === code && !d.item_name
                        )
                        || null;

                    if (!row_data) return;

                    // 获取物料详情
                    frappe.call({
                        method: 'erpnext.stock.doctype.item.item.get_item_details',
                        args: {
                            item_code: code,
                            company: frm.doc.company,
                        },
                        callback: function(r) {
                            if (!r.message) return;
                            const details = r.message;
                            Object.assign(row_data, {
                                item_name: details.item_name || '',
                                source_warehouse: details.default_warehouse || '',
                            });
                            dialog.fields_dict.trans_items.grid.refresh();
                        },
                    });
                } catch (e) {
                    // 名称没带出不影响其它操作：提交前 primary_action 还会统一补一次
                }
            },
        },
        {
            fieldtype: 'Data',
            fieldname: 'item_name',
            read_only: 1,
            label: __('物料名称'),
            in_list_view: 1,
        },
        {
            fieldtype: 'Float',
            fieldname: 'required_qty',
            default: 0,
            in_list_view: 1,
            label: __('需求数量'),
            precision: get_precision('required_qty'),
        },
        {
            fieldtype: 'Link',
            fieldname: 'source_warehouse',
            options: 'Warehouse',
            label: __('来源仓库'),
            get_query: function() {
                return {
                    filters: {
                        company: frm.doc.company,
                        is_group: 0,
                    },
                };
            },
        },
        {
            fieldtype: 'Float',
            fieldname: 'transferred_qty',
            read_only: 1,
            label: __('已转移数量'),
            precision: get_precision('transferred_qty'),
        },
        {
            fieldtype: 'Float',
            fieldname: 'consumed_qty',
            read_only: 1,
            label: __('已消耗数量'),
            precision: get_precision('consumed_qty'),
        },
    ];

    // 创建对话框
    const dialog = new frappe.ui.Dialog({
        title: __('变更物料 - 所需物料'),
        size: 'extra-large',
        fields: [
            {
                fieldname: 'hint',
                fieldtype: 'HTML',
                options: `<div class="alert alert-info" style="margin-bottom:10px;">
                    ${__('说明：')}
                    <ul style="margin:5px 0 0 20px;padding-left:0;">
                        <li>${__('修改「需求数量」可直接编辑表格中的数值')}</li>
                        <li>${__('删除物料：删除整行（该行将从所需物料中移除）')}</li>
                        <li>${__('添加物料：点击「添加行」按钮新增一行')}</li>
                    </ul>
                </div>`,
            },
            {
                fieldname: 'trans_items',
                fieldtype: 'Table',
                label: __('所需物料'),
                cannot_add_rows: false,
                in_place_edit: true,
                reqd: 1,
                data: data,
                get_data: function() {
                    return data;
                },
                fields: fields,
            },
        ],
        primary_action_label: __('确认变更'),
        primary_action: function() {
            const values = this.get_values();
            if (!values || !values.trans_items) {
                frappe.msgprint({ title: __('错误'), message: __('请至少保留一行数据'), indicator: 'red' });
                return;
            }

            const trans_items = values.trans_items.filter((item) => !!item.item_code);

            if (trans_items.length === 0) {
                frappe.msgprint({ title: __('错误'), message: __('物料不能为空'), indicator: 'red' });
                return;
            }

            const confirm_and_run = function() {
                // 确认对话框
                frappe.confirm(
                    __('确认变更「所需物料」吗？此操作将更新物料列表。'),
                    function() {
                        execute_update_required_items(frm, trans_items);
                        dialog.hide();
                    }
                );
            };

            // 兜底：把「物料名称 / 来源仓库」还是空白的行补齐。
            // 网格里 item_code 的 onchange 不一定每次都触发（旧版第二次新增就不触发），
            // 而服务端只会原样接收前端传来的 item_name / source_warehouse，所以这里必须补一次。
            const pending = trans_items.filter((it) => !it.item_name || !it.source_warehouse);
            if (!pending.length) {
                confirm_and_run();
                return;
            }

            frappe.dom.freeze(__('正在补全物料名称 / 来源仓库…'));
            Promise.all(
                pending.map(
                    (it) =>
                        new Promise(function(resolve) {
                            frappe.call({
                                method: 'erpnext.stock.doctype.item.item.get_item_details',
                                args: { item_code: it.item_code, company: frm.doc.company },
                                callback: function(r) {
                                    const d = (r && r.message) || {};
                                    if (!it.item_name) it.item_name = d.item_name || '';
                                    if (!it.source_warehouse) it.source_warehouse = d.default_warehouse || '';
                                    resolve();
                                },
                                error: function() {
                                    resolve();
                                },
                            });
                        })
                )
            ).then(() => {
                frappe.dom.unfreeze();
                confirm_and_run();
            });
        },
    });

    // 显示对话框
    dialog.show();

    // ── 兜底：自动带出物料名称 ─────────────────────────────────────────────
    // 网格列自带的 onchange 实测只在弹窗刚打开时生效一次，之后新增行就不再触发
    //（旧版还会抛 this.doc 的 TypeError），所以不能依赖它。
    // 策略：
    //   1) 直接扫一遍（不防抖）—— 供轮询调用，选完物料立刻补
    //   2) change/blur 事件 —— 用户手动编辑时立刻响应
    //   3) 弹窗存活期间每 400ms 扫一遍 —— 兜住"不触发任何事件"的情况
    function mirror_to_data(row, grow, updates) {
        // 同步回 df.data（primary_action 的 get_values / get_data 取的是它）
        const data = dialog.fields_dict.trans_items.df.data || [];
        let target = data[grow.idx - 1];
        if (!target || target.item_code !== row.item_code) {
            target = data
                .slice()
                .reverse()
                .find(function(d) {
                    return d && d.item_code === row.item_code;
                });
        }
        if (!target) return;
        Object.keys(updates).forEach(function(k) {
            if (!target[k]) target[k] = updates[k];
        });
    }

    function do_fill_missing_item_names() {
        const grid = dialog.fields_dict.trans_items.grid;
        (grid.grid_rows || []).forEach(function(grow) {
            const row = grow.doc;
            if (!row || !row.item_code) return;
            // 名称和发料仓都齐了就不用再查
            if (row.item_name && row.source_warehouse) return;
            // 同一行同一个物料只查一次，避免轮询反复打接口
            if (row.__lookup_pending || row.__looked_up_code === row.item_code) return;

            row.__lookup_pending = true;
            row.__looked_up_code = row.item_code;
            frappe.call({
                method: 'erpnext.stock.doctype.item.item.get_item_details',
                args: { item_code: row.item_code, company: frm.doc.company },
                callback: function(res) {
                    row.__lookup_pending = false;
                    const details = (res && res.message) || {};
                    const updates = {};
                    if (!row.item_name && details.item_name) {
                        updates.item_name = details.item_name;
                    }
                    if (!row.source_warehouse && details.default_warehouse) {
                        updates.source_warehouse = details.default_warehouse;
                    }
                    if (!Object.keys(updates).length) return;
                    Object.assign(row, updates);
                    mirror_to_data(row, grow, updates);
                    if (grow.refresh_field) {
                        Object.keys(updates).forEach(function(k) {
                            grow.refresh_field(k);
                        });
                    }
                },
                error: function() {
                    row.__lookup_pending = false;
                },
            });
        });
    }

    const fill_missing_item_names = frappe.utils.debounce(do_fill_missing_item_names, 200);

    dialog.$wrapper.on('change blur', 'input, select, textarea', fill_missing_item_names);
    dialog.$wrapper.on('click', '.grid-add-row, .grid-remove-row, .grid-remove-rows', function() {
        setTimeout(do_fill_missing_item_names, 50);
    });

    // 轮询兜底：轮询到弹窗关闭为止（避免"要等点到别处才显示"）
    const name_fill_timer = setInterval(function() {
        if (!dialog.$wrapper || !dialog.$wrapper.is(':visible')) {
            clearInterval(name_fill_timer);
            return;
        }
        do_fill_missing_item_names();
    }, 400);
}

/**
 * 执行变更物料后端调用
 * @param {Object} frm - 表单对象
 * @param {Array} trans_items - 变更后的物料数据
 */
function execute_update_required_items(frm, trans_items) {
    frappe.dom.freeze(__('处理中…'));

    frappe.call({
        method: 'work_order_task.work_order_task.overrides.work_order_override.update_required_items',
        args: {
            work_order_name: frm.doc.name,
            items: JSON.stringify(trans_items),
        },
        callback: function(r) {
            frappe.dom.unfreeze();
            if (r.exc) {
                frappe.msgprint({ title: __('错误'), message: r.exc, indicator: 'red' });
                return;
            }
            if (r.message && r.message.success) {
                frappe.show_alert({ message: r.message.message, indicator: 'green' }, 5);
                frm.reload_doc();
            } else if (r.message && r.message.error) {
                frappe.msgprint({ title: __('错误'), message: r.message.error, indicator: 'red' });
            }
        },
        error: function() {
            frappe.dom.unfreeze();
        },
    });
}

/**
 * 重新同步 BOM 对话框
 * 先获取 BOM 物料预览，再显示确认
 * @param {Object} frm - 表单对象
 */
function show_resync_bom_dialog(frm) {
    if (!frm.doc.bom_no) {
        frappe.msgprint({ title: __('错误'), message: __('工单未关联 BOM，无法同步'), indicator: 'red' });
        return;
    }

    const current_items_count = frm.doc.required_items ? frm.doc.required_items.length : 0;

    // 先获取 BOM 物料预览
    frappe.call({
        method: 'work_order_task.work_order_task.overrides.work_order_override.get_bom_items_preview',
        args: { work_order_name: frm.doc.name },
        callback: function(r) {
            if (r.exc) {
                frappe.msgprint({ title: __('错误'), message: r.exc, indicator: 'red' });
                return;
            }
            if (!r.message || !r.message.success) {
                frappe.msgprint({ title: __('错误'), message: r.message.error || __('获取 BOM 预览失败'), indicator: 'red' });
                return;
            }

            const bom_data = r.message;

            // 构建 BOM 物料预览 HTML 表格
            let items_html = '';
            if (bom_data.items && bom_data.items.length > 0) {
                const rows = bom_data.items.map(function(item) {
                    return `<tr>
                        <td style="padding:6px 8px;border-bottom:1px solid #eee;">${frappe.utils.escape_html(item.item_code || '')}</td>
                        <td style="padding:6px 8px;border-bottom:1px solid #eee;">${frappe.utils.escape_html(item.item_name || '')}</td>
                        <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">${item.qty}</td>
                        <td style="padding:6px 8px;border-bottom:1px solid #eee;">${frappe.utils.escape_html(item.uom || '')}</td>
                    </tr>`;
                }).join('');
                items_html = `<table style="width:100%;border-collapse:collapse;font-size:13px;">
                    <thead>
                        <tr style="background:#f8f9fa;">
                            <th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:left;">物料编码</th>
                            <th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:left;">物料名称</th>
                            <th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:right;">数量</th>
                            <th style="padding:8px;border-bottom:2px solid #dee2e6;text-align:left;">单位</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>`;
            } else {
                items_html = '<div style="padding:20px;text-align:center;color:#999;">BOM 中无物料</div>';
            }

            // 构建确认对话框内容
            const dialog_content = `
                <div style="max-height:400px;overflow-y:auto;">
                    <div style="margin-bottom:15px;">
                        <div style="margin-bottom:8px;">
                            <strong>BOM 编号：</strong>${frappe.utils.escape_html(bom_data.bom_no || '')}
                        </div>
                        <div style="margin-bottom:8px;">
                            <strong>当前物料行数：</strong>${current_items_count} 行
                        </div>
                        <div style="margin-bottom:8px;">
                            <strong>同步后物料行数：</strong>${bom_data.items_count} 行
                        </div>
                    </div>

                    <div style="margin-bottom:10px;font-weight:bold;">BOM 物料预览（共 ${bom_data.items_count} 项）：</div>
                    ${items_html}

                    <div style="margin-top:15px;padding:10px;background:#fff3cd;border-radius:4px;font-size:12px;">
                        <strong>⚠️ 影响范围：</strong><br>
                        • 将清空现有物料列表，重新从 BOM 加载<br>
                        • 手动调整的物料仓库/数量将被覆盖<br>
                        • 已发料/已消耗的物料不受影响<br><br>
                        <strong><span style="color:#dc3545;">注意：此操作不可逆！</span></strong>
                    </div>
                </div>
            `;

            const d = new frappe.ui.Dialog({
                title: __('重新同步 BOM 物料预览'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'preview_html',
                        options: dialog_content
                    }
                ],
                primary_action_label: __('确认同步'),
                primary_action: function() {
                    d.hide();
                    execute_resync_bom(frm);
                }
            });

            d.show();
        },
        error: function() {
            frappe.msgprint({ title: __('错误'), message: __('获取 BOM 预览失败'), indicator: 'red' });
        }
    });
}

/**
 * 执行重新同步 BOM
 * @param {Object} frm - 表单对象
 */
function execute_resync_bom(frm) {
    if (!frm.doc.bom_no) {
        frappe.msgprint({ title: __('错误'), message: __('工单未关联 BOM，无法同步'), indicator: 'red' });
        return;
    }

    frappe.dom.freeze(__('正在从 BOM 同步物料…'));

    frappe.call({
        method: 'work_order_task.work_order_task.overrides.work_order_override.resync_bom_items',
        args: {
            work_order_name: frm.doc.name,
        },
        callback: function(r) {
            frappe.dom.unfreeze();
            if (r.exc) {
                frappe.msgprint({ title: __('错误'), message: r.exc, indicator: 'red' });
                return;
            }
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: __('已同步 {0} 行物料', [r.message.items_count]),
                    indicator: 'green'
                }, 5);
                frm.reload_doc();
            } else if (r.message && r.message.error) {
                frappe.msgprint({ title: __('错误'), message: r.message.error, indicator: 'red' });
            }
        },
        error: function() {
            frappe.dom.unfreeze();
        },
    });
}

// ==========================================
// 一键工单入库 / 一键完成生产 功能（从 key_test 移植）
// ==========================================

/**
 * 创建工单入库单
 * @param {Object} frm - 表单对象
 */
function create_manufacture_entry(frm) {
    frappe.call({
        method: "key_test.production_utils.create_and_submit_manufacture_entry",
        args: {
            "work_order_id": frm.doc.name,
            "qty": flt(frm.doc.qty) - flt(frm.doc.produced_qty)
        },
        freeze: true,
        freeze_message: __("创建工单入库中..."),
        callback: function(r) {
            if (r.message) {
                if (r.message.success) {
                    // 创建并提交库存条目成功
                    frappe.show_alert({
                        message: __('工单入库单已创建并提交：') + r.message.stock_entry,
                        indicator: 'green'
                    }, 5);
                    
                    frappe.msgprint({
                        title: __("工单入库成功"),
                        indicator: "green",
                        message: __("工单入库已完成，您可以查看") + 
                                ` <a href="/app/stock-entry/${r.message.stock_entry}">
                                    ${r.message.stock_entry}
                                 </a>`
                    });
                    
                    // 刷新页面显示最新状态
                    frm.reload_doc();
                } else {
                    // 处理未能提交的情况
                    if (r.message.stock_entry) {
                        // 创建了Stock Entry但未能提交
                        let indicator = "orange";
                        let title = __("工单入库单创建成功但未提交");
                        
                        // 如果是库存不足错误，使用红色指示器
                        if (r.message.error_type === "库存不足" || 
                            (r.message.error && (r.message.error.includes("库存不足") || 
                                               r.message.error.includes("insufficient") || 
                                               r.message.error.includes("缺")))) {
                            indicator = "red";
                            title = __("库存不足");
                        }
                        
                        frappe.msgprint({
                            title: title,
                            indicator: indicator,
                            message: r.message.message + "<br><br>" +
                                    __("您可以查看并手动处理此工单入库单：") + 
                                    ` <a href="/app/stock-entry/${r.message.stock_entry}">
                                        ${r.message.stock_entry}
                                     </a>`
                        });
                    } else if (r.message.details) {
                        // 库存检查失败，显示详细信息
                        frappe.msgprint({
                            title: __("库存不足"),
                            indicator: "red",
                            message: __("无法创建工单入库单，以下物料库存不足：") + "<br><br>" + r.message.details
                        });
                    } else {
                        // 完全失败的情况
                        frappe.msgprint({
                            title: __("工单入库失败"),
                            indicator: "red",
                            message: r.message.error || __("未知错误")
                        });
                    }
                }
            }
        }
    });
}

/**
 * 执行一键完成生产
 * @param {Object} frm - 表单对象
 */
function execute_one_click_complete(frm) {
    frappe.show_alert({
        message: __('正在处理中，请稍候...'),
        indicator: 'blue'
    }, 3);
    
    frappe.call({
        method: "key_test.production_utils.one_click_complete_production",
        args: {
            "work_order_id": frm.doc.name
        },
        freeze: true,
        freeze_message: __("正在完成生产，请稍候..."),
        callback: function(r) {
            if (r.message) {
                // 先显示加工单结果的简短提示
                let jobcard_alert = r.message.job_card_message || "";
                
                // 右下角显示操作总结
                if (r.message.success) {
                    frappe.show_alert({
                        message: __('生产完成！加工单已创建并提交，工单入库已创建并提交'),
                        indicator: 'green'
                    }, 5);
                } else if (r.message.stock_entry) {
                    frappe.show_alert({
                        message: __('加工单已完成，工单入库已创建未能成功提交，可点击查看') + `: <a href="/app/stock-entry/${r.message.stock_entry}" target="_blank">${r.message.stock_entry}</a>`,
                        indicator: 'orange'
                    }, 15);
                } else {
                    frappe.show_alert({
                        message: __('仅创建了加工单，工单入库创建失败'),
                        indicator: 'red'
                    }, 5);
                }
                
                // 构建详细消息内容 - 先加入Job Card结果
                let message = __('加工单创建结果: ') + r.message.job_card_message + '<br><br>';
                
                // 添加工单入库结果的详细信息
                if (r.message.success) {
                    // 全部成功的情况 - 工单入库成功
                    message += __('工单入库成功：工单入库已完成，您可以查看') + 
                               ` <a href="/app/stock-entry/${r.message.stock_entry}">
                                   ${r.message.stock_entry}
                               </a>`;
                               
                    // 显示完整的成功消息
                    frappe.msgprint({
                        title: __('生产完成'),
                        indicator: 'green',
                        message: message
                    });
                } else if (r.message.stock_entry) {
                    // 加工单成功，但工单入库创建却未提交
                    let indicator = "orange";
                    let title = __('部分完成');
                    let stock_entry_msg = "";
                    
                    // 检查是否是库存不足导致的失败
                    if (r.message.error_type === "库存不足" || 
                        (r.message.error && (r.message.error.includes("库存不足") || 
                                           r.message.error.includes("insufficient") || 
                                           r.message.error.includes("缺")))) {
                        indicator = "red";
                        title = __('库存不足');
                        
                        // 添加库存不足详细信息
                        if (r.message.stock_entry_details) {
                            stock_entry_msg = __('工单入库未能提交，库存不足：') + '<br>' + 
                                           r.message.stock_entry_details + '<br><br>';
                        } else if (r.message.insufficient_items && r.message.insufficient_items.length) {
                            stock_entry_msg = __('工单入库未能提交，以下物料库存不足：') + '<br>';
                            r.message.insufficient_items.forEach(item => {
                                stock_entry_msg += `<b>${item.item_code}</b>: ${item.item_name || ""} - 
                                            需要 ${item.required_qty} ${item.stock_uom}, 
                                            仓库 ${item.warehouse} 中只有 ${item.available_qty}<br>`;
                            });
                            stock_entry_msg += '<br>';
                        }
                    }
                    
                    // 添加工单入库状态消息
                    stock_entry_msg += r.message.stock_entry_message || 
                                   (r.message.error ? 
                                    __('工单入库单已创建但未能提交: ') + r.message.error :
                                    __('工单入库单已创建但未能提交'));
                    
                    stock_entry_msg += '<br><br>' + __('您可以查看并手动处理此工单入库单：') + 
                               ` <a href="/app/stock-entry/${r.message.stock_entry}">
                                   ${r.message.stock_entry}
                               </a>`;
                    
                    // 添加到主消息中
                    message += stock_entry_msg;
                    
                    frappe.msgprint({
                        title: title,
                        indicator: indicator,
                        message: message
                    });
                } else if (r.message.error && r.message.error.includes("现有入库单") && r.message.error.includes("总入库数量已超工单数量")) {
                    // 特殊情况：工单已经有足够的入库单
                    message += __('工单入库失败: ') + r.message.error;
                    
                    frappe.msgprint({
                        title: __('无需工单入库'),
                        indicator: 'blue',
                        message: message
                    });
                } else {
                    // 只有加工单成功，工单入库完全失败
                    message += __('工单入库失败: ') + (r.message.error || __("未知错误"));
                    
                    frappe.msgprint({
                        title: __('部分完成'),
                        indicator: 'orange',
                        message: message
                    });
                }
                
                frm.reload_doc();
            } else {
                frappe.msgprint({
                    title: __('操作失败'),
                    indicator: 'red',
                    message: __('一键完成生产失败，未收到返回结果')
                });
            }
        }
    });
}