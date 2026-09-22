// BOM物料清单 自定义脚本
frappe.ui.form.on('BOM', {
    refresh: function(frm) {
        // 直接获取主单据的item字段值
        const main_item = frm.doc.item;
        // 条件判断：主单据item是否以SXBZCP开头
        const show_button = main_item && main_item.startsWith('SXBZCP');

        // 条件显示按钮（仅当条件满足时添加）
        if (show_button) {
            // 添加 复制BOM到国外分公司 按钮
            frm.add_custom_button(__('复制BOM'), function() {
                copy_bom_to_overseas_branches(frm);
            }).css({
                'background-color': '#db40c1',
                'color': 'white',
                'border': 'none',
                'border-radius': '4px',
                'padding': '6px 12px',
                'font-size': '14px'
            });
        }

        // 替换面料：把本 BOM 子表里的旧物料替换为新物料（名称/描述取新料，单价与成本由服务端重算）
        frm.add_custom_button(__('替换面料'), function() {
            replace_bom_item_dialog(frm);
        });

        // 添加按钮到表单右上角，用于强制重建底层物料工费成本子表
        frm.add_custom_button(__('更新底层物料工费成本'), function() {
            frappe.confirm(
                __('确认要重建并覆盖当前 BOM 的底层物料工费成本子表吗？此操作会覆盖现有数据。'),
                function() {
                    frappe.show_progress(__('Updating'), 1, 1);
                    frappe.call({
                        method: 'work_order_task.work_order_task.utils.routing.rebuild_exploded_operation_cost_items_for_bom',
                        args: {
                            bom_name: frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __('正在重建底层物料工费成本...'),
                        callback: function(r) {
                            frappe.hide_progress();
                            if (!r.exc && r.message && r.message.success) {
                                frappe.msgprint(__('已重建 {0} 条记录，汇总工费总成本: {1}', [r.message.added || 0, r.message.total_operating_cost_qty || 0]));
                                // 刷新表单以显示子表变化
                                frm.reload_doc();
                            } else {
                                frappe.msgprint(__('重建失败: {0}', [r.message && r.message.error || (r.exc && r.exc[0]) || '未知错误']));
                            }
                        }
                    });
                }
            );
        });
    },

    // 勾选"是否默认委外"时，自动勾选"委外"
    is_default_subcontracting: function(frm) {
        if (frm.doc.is_default_subcontracting) {
            frm.set_value('subcontracting', 1);
        }
    },

    // 取消勾选"委外"时，自动取消勾选"是否默认委外"
    subcontracting: function(frm) {
        if (!frm.doc.subcontracting) {
            frm.set_value('is_default_subcontracting', 0);
        }
    },
});

function copy_bom_to_overseas_branches(frm) {
    // 首先检查BOM物料子表中是否存在物料组为"PP棉"的物料
    check_pp_cotton_in_bom_items(frm, function(has_pp_cotton) {
        if (!has_pp_cotton) {
            frappe.msgprint({
                title: __('检查失败'),
                message: __('BOM物料子表中不存在物料组为"PP棉"的物料，无法执行复制操作'),
                indicator: 'red'
            });
            return;
        }

        // 如果存在PP棉，继续执行原有逻辑
        execute_copy_bom_logic(frm);
    });
}

function execute_copy_bom_logic(frm) {
    // 调用自定义服务器端方法获取符合条件的物料组
    frappe.call({
        method: 'key_test.update_variant_valuation_rate.get_item_groups_descendants',
        args: {
            parent_item_group_names: ['产品']
        },
        callback: function(response) {
            var item_group_names = response.message;

            // 检查当前物料组是否在符合条件的物料组列表中
            // if (item_group_names.includes(frm.doc.item_group)) {
                // frm.add_custom_button(__('一键创建配套物料及变体'), function() {
            // 定义所有可选的前缀
            const all_prefixes = [
                "波兰PL包装成品#",
                "美东USNJ包装成品#",
                "美中USTX包装成品#",
            ];

            // 创建选择对话框
            let prefix_dialog = new frappe.ui.Dialog({
                title: __('选择要创建的配套物料类型'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'select_buttons',
                        options: `
                            <div style="margin-bottom: 10px;">
                                <button class="btn btn-sm btn-default" data-action="select-all">
                                    ${__('全选')}
                                </button>
                                <button class="btn btn-sm btn-default" data-action="deselect-all" style="margin-left: 10px;">
                                    ${__('全不选')}
                                </button>
                            </div>
                        `
                    },
                    {
                        fieldtype: 'Column Break'
                    }
                ].concat(all_prefixes.map(prefix => ({
                    fieldtype: 'Check',
                    label: prefix,
                    fieldname: prefix.replace(/#/g, '_hash_'),
                    default: 0
                }))),
                primary_action_label: __('执行'),
                primary_action: function() {
                    // 获取选中的前缀
                    let selected_prefixes = all_prefixes.filter(prefix =>
                        this.get_value(prefix.replace(/#/g, '_hash_'))
                    );

                    if (selected_prefixes.length === 0) {
                        frappe.msgprint(__('请至少选择一个配套物料类型'));
                        return;
                    }

                    // 从BOM物料字段提取模板物料代码
                    // SXBZCP#KS0234-45 → KS0234
                    let template_item_code = '';
                    if (frm.doc.item && frm.doc.item.includes('#')) {
                        let parts = frm.doc.item.split('#');
                        if (parts.length >= 2) {
                            template_item_code = parts[1].split('-')[0]; // 取#后面的部分，去掉-后面的规格
                        }
                    }

                    if (!template_item_code) {
                        frappe.msgprint(__('无法从BOM物料字段提取模板物料代码'));
                        return;
                    }

                    // 获取模板物料单据信息
                    frappe.call({
                        method: 'frappe.client.get',
                        args: {
                            doctype: 'Item',
                            name: template_item_code
                        },
                        callback: function(template_response) {
                            if (template_response.message) {
                                let template_item = template_response.message;

                                // 获取模板物料的属性
                                let attributes = [];
                                if (template_item.attributes && template_item.attributes.length > 0) {
                                    attributes = template_item.attributes.map(attr => ({
                                        attribute: attr.attribute
                                    }));
                                }

                                // 获取物料组的 custom_model_id（参考物料页面的逻辑）
                                frappe.call({
                                    method: 'frappe.client.get',
                                    args: {
                                        doctype: 'Item Group',
                                        name: template_item.item_group
                                    },
                                    callback: function(group_response) {
                                        if (group_response.message) {
                                            let custom_model_id = group_response.message.custom_model_id;

                                            // 调用服务器端方法创建配套物料
                                            frappe.call({
                                                method: 'key_test.add_item_semi.create_supporting_items_and_variants',
                                                args: {
                                                    item_group: template_item.item_group,
                                                    item_template_name: template_item.item_name,
                                                    custom_model_id: custom_model_id,
                                                    attributes: JSON.stringify(attributes),
                                                    prefixes: JSON.stringify(selected_prefixes)
                                                },
                                                freeze: true,
                                                freeze_message: __('正在创建配套物料及变体...'),
                                                callback: function(r) {
                                                    if (r.message) {
                                                        // 显示配套物料创建结果
                                                        let result_dialog = new frappe.ui.Dialog({
                                                            title: __('配套物料创建结果'),
                                                            fields: [{
                                                                fieldtype: 'HTML',
                                                                fieldname: 'message_html',
                                                                options: `<div style="max-height: 300px; overflow-y: auto;">
                                                                    ${r.message.join('<br>')}
                                                                </div>`
                                                            }],
                                                            primary_action_label: __('复制BOM'),
                                                            primary_action: function() {
                                                                result_dialog.hide();

                                                                // 自动执行BOM复制
                                                                copy_bom_for_supporting_items(frm, selected_prefixes);
                                                            }
                                                        });
                                                        result_dialog.show();
                                                    }
                                                }
                                            });
                                        } else {
                                            frappe.msgprint(__('无法获取物料组的 custom_model_id'));
                                        }
                                    }
                                });
                            } else {
                                frappe.msgprint(__('无法获取模板物料单据信息: ') + template_item_code);
                            }
                        }
                    });

                    prefix_dialog.hide();
                },
                secondary_action_label: __('取消'),
                secondary_action: function() {
                    prefix_dialog.hide();
                }
            });

            // 绑定全选/全不选按钮事件
            prefix_dialog.$wrapper.find('[data-action="select-all"]').on('click', function() {
                all_prefixes.forEach(prefix => {
                    prefix_dialog.set_value(prefix.replace(/#/g, '_hash_'), 1);
                });
            });

            prefix_dialog.$wrapper.find('[data-action="deselect-all"]').on('click', function() {
                all_prefixes.forEach(prefix => {
                    prefix_dialog.set_value(prefix.replace(/#/g, '_hash_'), 0);
                });
            });

            prefix_dialog.show();
        }
    });
}

function check_pp_cotton_in_bom_items(frm, callback) {
    /**
     * 检查BOM物料子表中是否存在物料组为"PP棉"的物料
     * @param {Object} frm - 表单对象
     * @param {Function} callback - 回调函数，参数为boolean值表示是否存在PP棉
     */

    // 获取BOM物料子表中的所有物料代码
    const bom_items = frm.doc.items || [];

    if (bom_items.length === 0) {
        callback(false);
        return;
    }

    // 提取所有物料代码
    const item_codes = bom_items.map(item => item.item_code).filter(Boolean);

    if (item_codes.length === 0) {
        callback(false);
        return;
    }

    // 批量获取物料的物料组信息
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Item',
            filters: { name: ['in', item_codes] },
            fields: ['name', 'item_group']
        },
        callback: function(response) {
            let has_pp_cotton = false;

            if (response.message) {
                // 检查是否有物料组为"PP棉"的物料
                has_pp_cotton = response.message.some(item => item.item_group === 'PP棉');
            }

            callback(has_pp_cotton);
        },
        error: function() {
            // 如果获取失败，默认返回false
            callback(false);
        }
    });
}

function copy_bom_for_supporting_items(frm, selected_prefixes) {
    /**
     * 复制BOM为配套物料
     * @param {Object} frm - 表单对象
     * @param {Array} selected_prefixes - 选中的前缀列表
     */

    frappe.call({
        method: 'work_order_task.work_order_task.utils.bom.copy_bom_for_supporting_items',
        args: {
            bom_name: frm.doc.name,
            selected_prefixes: selected_prefixes
        },
        freeze: true,
        freeze_message: __('正在复制BOM...'),
        callback: function(response) {
            if (response.message) {
                let result = response.message;

                if (result.success) {
                    // 显示BOM复制结果
                    show_bom_copy_results(result.results);
                } else {
                    frappe.msgprint({
                        title: __('BOM复制失败'),
                        message: result.message,
                        indicator: 'red'
                    });
                }
            }
        }
    });
}

function show_bom_copy_results(results) {
    /**
     * 显示BOM复制结果
     * @param {Array} results - 复制结果数组
     */

    let message = "BOM复制结果:\n\n";
    let has_results = false;

    results.forEach(result => {
        has_results = true;
        if (result.status === 'created') {
            message += `✅ ${result.item_code}: ${result.message}\n`;
        } else if (result.status === 'skipped') {
            message += `⏭️ ${result.item_code}: ${result.message}\n`;
        } else if (result.status === 'failed') {
            message += `❌ ${result.item_code}: ${result.message}\n`;
        }
    });

    if (!has_results) {
        message = "没有需要复制的BOM";
    }

    frappe.msgprint({
        title: __('BOM复制完成'),
        message: message,
        indicator: 'blue'
    });
}


// 定义计算函数
function calculateOperationCosts(frm, cdt, cdn, newHourRateLabour, newHourRateManage) {
    const row = locals[cdt][cdn];
    const timeInMins = flt(row.time_in_mins);

    // 如果传入了新的工资率，则更新当前行的hour_rate_labour
    if (newHourRateLabour !== undefined) {
        // 如果新值和当前值不同，则设置
        if (flt(row.hour_rate_labour) !== flt(newHourRateLabour)) {
            frappe.model.set_value(cdt, cdn, 'hour_rate_labour', newHourRateLabour);
        }
    }
    if (newHourRateManage !== undefined) {
        if (flt(row.hour_rate_manage) !== flt(newHourRateManage)) {
            frappe.model.set_value(cdt, cdn, 'hour_rate_manage', newHourRateManage);
        }
    }

    // 使用新值（如果传入了）或者当前行的值
    const hourRateLabour = newHourRateLabour !== undefined ? newHourRateLabour : flt(row.hour_rate_labour);
    const hourRateManage = newHourRateManage !== undefined ? newHourRateManage : flt(row.hour_rate_manage);

    let operationLabour = 0;
    let operationManageCost = 0;

    // 计算工序工资
    if (timeInMins > 0 && hourRateLabour >= 0) {
        const wagePerMinute = hourRateLabour / 60;
        operationLabour = wagePerMinute * timeInMins;
    }

    // 计算工序管理费
    if (timeInMins > 0 && hourRateManage >= 0) {
        const managePerMinute = hourRateManage / 60;
        operationManageCost = managePerMinute * timeInMins;
    }

    // 设置字段，如果值有变化才设置
    if (flt(row.operation_labour) !== flt(operationLabour)) {
        frappe.model.set_value(cdt, cdn, 'operation_labour', operationLabour);
    }
    if (flt(row.operation_manage_cost) !== flt(operationManageCost)) {
        frappe.model.set_value(cdt, cdn, 'operation_manage_cost', operationManageCost);
    }
}

frappe.ui.form.on('BOM Operation', {
    workstation(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.workstation) return;

        frappe.db.get_value('Workstation', row.workstation, ['hour_rate_labour', 'hour_rate_manage'])
            .then(r => {
                const wage = r?.message?.hour_rate_labour ?? 0;
                const manageRate = r?.message?.hour_rate_manage ?? 0;

                // 调用计算函数，并传入新的工资率和管理费率
                calculateOperationCosts(frm, cdt, cdn, wage, manageRate);
            });
    },

    time_in_mins(frm, cdt, cdn) {
        // 直接调用计算函数，不传入新的工资率和管理费率，使用当前行的值
        calculateOperationCosts(frm, cdt, cdn);
    },
    // 由于只读 暂不考虑
    // hour_rate_labour(frm, cdt, cdn) {
    //     calculateOperationCosts(frm, cdt, cdn);
    // },

    // hour_rate_manage(frm, cdt, cdn) {
    //     calculateOperationCosts(frm, cdt, cdn);
    // }
});

// ===== 替换面料：把本 BOM 子表里的旧物料替换为新物料 =====
function replace_bom_item_dialog(frm) {
    if (frm.is_new()) {
        frappe.msgprint(__('请先保存 BOM 再使用「替换面料」'));
        return;
    }

    // 「旧物料」下拉只列本 BOM 子表里出现过的物料（去重），避免把全库物料都拉出来
    const bom_item_codes = [...new Set((frm.doc.items || [])
        .map(it => it.item_code)
        .filter(Boolean))];
    if (!bom_item_codes.length) {
        frappe.msgprint(__('本 BOM 的物料子表是空的，没有可替换的物料'));
        return;
    }

    const d = new frappe.ui.Dialog({
        title: __('替换面料'),
        fields: [
            {
                fieldtype: 'Link',
                fieldname: 'old_item',
                label: __('旧物料'),
                options: 'Item',
                reqd: 1,
                get_query: () => ({
                    filters: { name: ['in', bom_item_codes] }
                }),
                description: __('只列出本 BOM 子表里出现过的物料（共 {0} 个）', [bom_item_codes.length])
            },
            {
                fieldtype: 'Link',
                fieldname: 'new_item',
                label: __('新物料'),
                options: 'Item',
                reqd: 1,
                get_query: () => ({ filters: { disabled: 0 } })
            },
            {
                fieldtype: 'HTML',
                fieldname: 'hint',
                options: '<div class="text-muted small">' +
                    __('将把本 BOM 子表中「旧物料」的行替换为「新物料」；新料单价按本 BOM 的取价方式重新取得，BOM 成本会自动重算。') +
                    '</div>'
            }
        ],
        primary_action_label: __('替换'),
        primary_action(values) {
            if (values.old_item === values.new_item) {
                frappe.msgprint(__('新旧物料不能相同'));
                return;
            }
            d.hide();
            frappe.call({
                method: 'work_order_task.work_order_task.utils.bom.replace_bom_item',
                args: {
                    bom_name: frm.doc.name,
                    old_item: values.old_item,
                    new_item: values.new_item
                },
                freeze: true,
                freeze_message: __('正在替换面料...'),
                callback: function(r) {
                    const res = r.message;
                    if (!res) return;
                    if (!res.success) {
                        frappe.msgprint({
                            title: __('未替换'),
                            indicator: 'orange',
                            message: res.message || __('本 BOM 中没有找到该旧物料')
                        });
                        return;
                    }
                    const lines = (res.details || []).map(x =>
                        __('第 {0} 行：{1} → {2}（单价 {3} → {4}）',
                            [x.idx, x.old_item_code, res.new_item_code,
                             flt(x.old_rate, 3), flt(x.new_rate, 3)]));
                    frappe.msgprint({
                        title: __('替换完成'),
                        indicator: 'green',
                        message: [
                            __('共替换 {0} 行', [res.matched]),
                            res.new_item_code + ' / ' + (res.new_item_name || '')
                        ].concat(lines).concat([
                            __('BOM 原材料成本：{0}，总成本：{1}',
                                [flt(res.raw_material_cost, 3), flt(res.total_cost, 3)])
                        ]).join('<br>')
                    });
                    if (res.warnings && res.warnings.length) {
                        frappe.msgprint({
                            title: __('注意'),
                            indicator: 'orange',
                            message: res.warnings.join('<br>')
                        });
                    }
                    frm.reload_doc();
                }
            });
        }
    });
    d.show();
}
