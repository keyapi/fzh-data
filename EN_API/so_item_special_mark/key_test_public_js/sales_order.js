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
