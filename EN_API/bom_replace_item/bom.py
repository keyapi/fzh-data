import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def copy_bom_for_supporting_items(bom_name, selected_prefixes):
    """
    复制BOM为配套物料 - 通过前缀替换生成新物料代码
    
    Args:
        bom_name: BOM名称
        selected_prefixes: 用户选择的配套物料类型列表
    
    Returns:
        dict: 复制结果
    """

    try:
        # 获取原始BOM
        original_bom = frappe.get_doc("BOM", bom_name)
        original_item = original_bom.item
        
        # 前缀映射
        prefix_mapping = {
            "波兰PL包装成品#": "PLBZCP#",
            "美东USNJ包装成品#": "USNJBZCP#", 
            "美中USTX包装成品#": "USTXBZCP#"
        }
        
        # 确保 selected_prefixes 是列表
        if isinstance(selected_prefixes, str):
            # 如果是字符串，尝试解析为JSON
            try:
                import json
                selected_prefixes = json.loads(selected_prefixes)
            except:
                # 如果解析失败，当作单个前缀处理
                selected_prefixes = [selected_prefixes]
        elif not isinstance(selected_prefixes, list):
            selected_prefixes = [selected_prefixes]
        
        results = []
        
        for prefix in selected_prefixes:
            if prefix not in prefix_mapping:
                results.append({
                    'item_code': prefix,
                    'bom_name': '',
                    'status': 'failed',
                    'message': f'未知的前缀类型: {prefix}'
                })
                continue
            
            # 生成新物料代码 - 直接替换前缀
            new_item_code = generate_new_item_code(original_item, prefix_mapping[prefix])
            
            # 验证物料是否存在
            if not verify_item_exists(new_item_code):
                results.append({
                    'item_code': new_item_code,
                    'bom_name': '',
                    'status': 'failed',
                    'message': f'物料 {new_item_code} 不存在，请先创建配套物料'
                })
                continue
            
            # 检查BOM是否已存在
            existing_bom = check_bom_exists(new_item_code)
            if existing_bom:
                results.append({
                    'item_code': new_item_code,
                    'bom_name': existing_bom,
                    'status': 'skipped',
                    'message': f'BOM已存在: {existing_bom}'
                })
                continue
            
            # 复制BOM
            copy_result = copy_bom_with_new_item(original_bom, new_item_code)
            results.append(copy_result)
        
        return {
            'success': True,
            'message': 'BOM复制完成',
            'results': results
        }
        
    except Exception as e:
        frappe.log_error(f"BOM复制失败: {str(e)}", "BOM Copy Error")
        return {
            'success': False,
            'message': f'BOM复制失败: {str(e)}',
            'results': []
        }

def generate_new_item_code(original_item, new_prefix):
    """
    通过前缀替换生成新物料代码
    
    Args:
        original_item: 原始物料代码，如 SXBZCP#KS0234-45
        new_prefix: 新前缀，如 PLBZCP#
    
    Returns:
        str: 新物料代码，如 PLBZCP#KS0234-45
    """
    # 找到第一个#的位置
    hash_index = original_item.find('#')
    if hash_index == -1:
        # 如果没有#，直接替换整个字符串
        return new_prefix.rstrip('#')
    
    # 提取#后面的部分
    suffix = original_item[hash_index:]
    # 组合新前缀和原后缀
    return new_prefix.rstrip('#') + suffix

def verify_item_exists(item_code):
    """验证物料是否存在"""
    try:
        frappe.get_doc("Item", item_code)
        return True
    except frappe.DoesNotExistError:
        return False

def check_bom_exists(item_code):
    """检查BOM是否已存在"""
    try:
        # 查询已提交且激活的BOM
        bom_list = frappe.get_list("BOM", 
            filters={
                "item": item_code, 
                "is_active": 1,
                # "docstatus": 1  # 确保是已提交状态
                "docstatus": 0  # 确保是已提交状态
            },
            fields=["name"],
            limit=1
        )
        if bom_list:
            return bom_list[0].name
        return None
    except Exception:
        return None

def copy_bom_with_new_item(original_bom, new_item_code):
    """复制BOM并替换物料"""
    try:
        # 获取新物料的名称
        new_item_name = frappe.get_value("Item", new_item_code, "item_name")
        if not new_item_name:
            return {
                'item_code': new_item_code,
                'bom_name': '',
                'status': 'failed',
                'message': f'无法获取物料 {new_item_code} 的名称'
            }
        
        # 复制当前BOM
        new_bom = frappe.copy_doc(original_bom)
        
        # 更新物料信息
        new_bom.item = new_item_code
        new_bom.item_name = new_item_name

        # 修改成本配置（物料单价基于、价格表）
        buying_price_list_mapping = {
            "PLBZCP": "波兰PL标准采购",
            "USNJBZCP": "美东USNJ标准采购", 
            "USTXBZCP": "美中USTX标准采购"
        }

        new_bom.rm_cost_as_per = "Price List" # 将 成本价Valuation Rate 修改为 价格表Price List
        for key in buying_price_list_mapping:
            if key in new_bom.item:
                new_bom.buying_price_list = buying_price_list_mapping[key] # 将价格表字段值 修改为对应国外分公司的标准采购
        
        # 物料子表 只保留物料组为 PP棉的 物料信息
        # 1. 批量获取物料组信息
        item_codes = [item.item_code for item in new_bom.items]
        # 使用集合推导式只获取物料组是PP棉 的物料
        pp_cotton_items = {
            item.name: item 
            for item in frappe.get_all(
                "Item",
                filters={"name": ("in", item_codes), "item_group": "PP棉"},
                fields=["name", "item_group"]
            )
        }
        # 2. 过滤子表物料
        filtered_items = []
        item_idx = 0
        for item in new_bom.items:
            # 保留物料组为PP棉的物料
            if item.item_code in pp_cotton_items:
                # 特殊物料替换：PPM1500-7D51-SILICONIZED-NEW -> PPM1500-15D64-SILICONIZED-NEW
                if item.item_code == "PPM1500-7D51-SILICONIZED-NEW":
                    item.item_code = "PPM1500-15D64-SILICONIZED-NEW"
                    # 更新物料名称
                    item.item_name = frappe.get_value("Item", "PPM1500-15D64-SILICONIZED-NEW", "item_name")
                
                item.idx = item_idx + 1
                item_idx += 1
                filtered_items.append(item)
        new_bom.items = filtered_items

        # 工序子表，针对 包装的工序 替换工站类型（波兰PL包装、美东USNJ包装、美中USTX包装）
        workstation_type_list_mapping = {
            "PLBZCP": "波兰PL包装",
            "USNJBZCP": "美东USNJ包装", 
            "USTXBZCP": "美中USTX包装"
        }
        # 1) 若存在工序子表记录，再判断是否存在“包装”的工站类型
        try:
            if getattr(new_bom, "operations", None):
                # 判断物料前缀是否在映射表中
                matched_prefix = None
                for prefix_key in workstation_type_list_mapping.keys():
                    if prefix_key in new_bom.item:
                        matched_prefix = prefix_key
                        break

                if matched_prefix:
                    target_workstation_name = workstation_type_list_mapping[matched_prefix]
                    # 查找同名工站（若找不到，则不做任何替换）
                    ws = frappe.get_all(
                        "Workstation",
                        filters={"workstation_name": target_workstation_name},
                        fields=["name"],
                        limit=1
                    )

                    if ws:
                        target_ws_name = ws[0].name
                        
                        # 获取目标工站的成本费率
                        target_workstation = frappe.get_doc("Workstation", target_ws_name)
                        # 工资
                        target_hour_rate_labour = getattr(target_workstation, 'hour_rate_labour', 0) or 0
                        # 管理费率
                        target_hour_rate_manage = getattr(target_workstation, 'hour_rate_manage', 0) or 0
                        # 净工费率
                        target_hour_rate = getattr(target_workstation, 'hour_rate', 0) or 0
                        
                        # 仅对工站类型为"包装"的工序进行替换
                        for op in new_bom.operations:
                            # workstation_type 字段为文本/Link，界面显示为"包装"
                            workstation_type_obj = getattr(op, "workstation_type", None)
                            # if getattr(op, "workstation_type", None) in ("包装",):
                            if workstation_type_obj in ("包装",) or not workstation_type_obj:
                                op.workstation_type = None
                                op.workstation = target_ws_name
                                
                                # 更新工站相关的成本字段
                                op.hour_rate_labour = target_hour_rate_labour
                                op.hour_rate_manage = target_hour_rate_manage
                                op.hour_rate = target_hour_rate
                                
                                # 重新计算工序成本
                                time_in_mins = getattr(op, 'time_in_mins', 0) or 0

                                # 计算工序工资
                                if time_in_mins > 0 and target_hour_rate_labour >= 0:
                                    wage_per_minute = target_hour_rate_labour / 60
                                    op.operation_labour = wage_per_minute * time_in_mins
                                else:
                                    op.operation_labour = 0
                                
                                # 计算工序管理费
                                if time_in_mins > 0 and target_hour_rate_manage >= 0:
                                    manage_per_minute = target_hour_rate_manage / 60
                                    op.operation_manage_cost = manage_per_minute * time_in_mins
                                else:
                                    op.operation_manage_cost = 0
                                
                                # 计算工费成本
                                if time_in_mins > 0 and target_hour_rate >= 0:
                                    hour_rate_per_minute = target_hour_rate / 60
                                    op.operating_cost = hour_rate_per_minute * time_in_mins
                                else:
                                    op.operating_cost = 0


                    # 如果未找到目标工站，则保持复制过来的原值（不做任何处理）
        except Exception:
            # 任何异常都不影响BOM复制流程，保持原始值
            pass
        
        # 设置为草稿状态
        new_bom.docstatus = 0
        new_bom.is_active = 1
        
        # 保存新BOM
        new_bom.insert()
        
        # # 提交BOM以确保可以被查询到
        new_bom.submit()
        
        return {
            'item_code': new_item_code,
            'bom_name': new_bom.name,
            'status': 'created',
            'message': f'BOM创建成功: {new_bom.name}'
        }
        
    except Exception as e:
        return {
            'item_code': new_item_code,
            'bom_name': '',
            'status': 'failed',
            'message': f'BOM复制失败: {str(e)}'
        }

@frappe.whitelist()
def auto_copy_bom_for_sxbzcp_on_submit(docname):
    """
    当BOM的item以SXBZCP开头时, 在提交后自动执行复制BOM逻辑
    自动选择所有三个国外分公司选项，无需用户手动选择
    
    Args:
        docname: BOM文档名称
    
    Returns:
        dict: 执行结果
    """
    try:
        # 获取BOM文档
        bom_doc = frappe.get_doc("BOM", docname)
        
        # 检查条件：item是否以SXBZCP开头
        if not bom_doc.item or not bom_doc.item.startswith('SXBZCP'):
            return {
                'success': False,
                'message': 'BOM物料不是SXBZCP开头，跳过自动复制',
                'results': []
            }
        
        # 检查BOM物料子表中是否存在物料组为"PP棉"的物料
        has_pp_cotton = check_pp_cotton_in_bom_items(bom_doc)
        if not has_pp_cotton:
            return {
                'success': False,
                'message': 'BOM物料子表中不存在物料组为"PP棉"的物料，无法执行自动复制',
                'results': []
            }
        
        # 自动设置所有三个国外分公司选项
        selected_prefixes = [
            "波兰PL包装成品#",
            "美东USNJ包装成品#",
            "美中USTX包装成品#"
        ]
        
        # 第一步：先创建配套物料及变体
        create_result = create_supporting_items_for_auto_copy(bom_doc, selected_prefixes)
        if not create_result.get('success'):
            return {
                'success': False,
                'message': f'配套物料创建失败: {create_result.get("message", "")}',
                'results': []
            }
        
        # 第二步：再复制BOM
        result = copy_bom_for_supporting_items(bom_doc.name, selected_prefixes)
        
        return result
        
    except Exception as e:
        # 记录错误但不影响BOM的正常提交
        frappe.log_error(
            f"BOM自动复制失败 - BOM: {docname}, 错误: {str(e)}",
            "BOM Auto Copy Error"
        )
        return {
            'success': False,
            'message': f'BOM自动复制失败: {str(e)}',
            'results': []
        }

def check_pp_cotton_in_bom_items(bom_doc):
    """
    检查BOM物料子表中是否存在物料组为"PP棉"的物料
    
    Args:
        bom_doc: BOM文档对象
    
    Returns:
        bool: 是否存在PP棉物料
    """
    try:
        # 获取BOM物料子表中的所有物料代码
        bom_items = bom_doc.get('items', [])
        
        if not bom_items:
            return False
        
        # 提取所有物料代码
        item_codes = [item.item_code for item in bom_items if item.item_code]
        
        if not item_codes:
            return False
        
        # 批量获取物料的物料组信息
        items_data = frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]},
            fields=["name", "item_group"]
        )
        
        # 检查是否有物料组为"PP棉"的物料
        return any(item.item_group == 'PP棉' for item in items_data)
        
    except Exception as e:
        frappe.log_error(f"检查PP棉物料失败: {str(e)}", "BOM Check PP Cotton Error")
        return False

@frappe.whitelist()
def trigger_batch_process_sxbzcp_boms(batch_size=20, limit=None, dry_run=False, force_update=False):
    """
    触发SXBZCP BOM批量处理
    供前端列表页面按钮调用
    
    Args:
        batch_size: 每批处理数量
        limit: 总处理数量限制
        dry_run: 是否模拟运行
        force_update: 是否强制更新已存在的BOM
    
    Returns:
        dict: 处理结果
    """
    try:
        from work_order_task.work_order_task.utils.bom_batch_process import batch_process_sxbzcp_boms
        
        # 转换参数类型
        batch_size = int(batch_size) if batch_size else 20
        limit = int(limit) if limit else None
        dry_run = str(dry_run).lower() in ('true', '1', 'yes')
        force_update = str(force_update).lower() in ('true', '1', 'yes')
        
        # 执行批处理
        result = batch_process_sxbzcp_boms(
            batch_size=batch_size,
            limit=limit,
            dry_run=dry_run,
            force_update=force_update
        )
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'message': f'批量处理失败: {str(e)}',
            'summary': None
        }

def create_supporting_items_for_auto_copy(bom_doc, selected_prefixes):
    """
    为自动复制BOM创建配套物料及变体
    模拟前端调用key_test.add_item_semi.create_supporting_items_and_variants的逻辑
    
    Args:
        bom_doc: BOM文档对象
        selected_prefixes: 选中的前缀列表
    
    Returns:
        dict: 创建结果
    """
    try:
        # 从BOM物料字段提取模板物料代码
        # SXBZCP#KS0234-45 → KS0234
        template_item_code = ''
        if bom_doc.item and '#' in bom_doc.item:
            parts = bom_doc.item.split('#')
            if len(parts) >= 2:
                template_item_code = parts[1].split('-')[0]  # 取#后面的部分，去掉-后面的规格
        
        if not template_item_code:
            return {
                'success': False,
                'message': '无法从BOM物料字段提取模板物料代码'
            }
        
        # 获取模板物料单据信息
        template_item = frappe.get_doc("Item", template_item_code)
        if not template_item:
            return {
                'success': False,
                'message': f'无法获取模板物料单据信息: {template_item_code}'
            }
        
        # 获取模板物料的属性
        attributes = []
        if template_item.attributes and len(template_item.attributes) > 0:
            attributes = [{"attribute": attr.attribute} for attr in template_item.attributes]
        
        # 将attributes转换为JSON字符串
        import json
        attributes_json = json.dumps(attributes)
        
        # 获取物料组的 custom_model_id
        item_group_doc = frappe.get_doc("Item Group", template_item.item_group)
        custom_model_id = item_group_doc.custom_model_id if hasattr(item_group_doc, 'custom_model_id') else None
        
        if not custom_model_id:
            return {
                'success': False,
                'message': '无法获取物料组的 custom_model_id'
            }
        
        # 调用服务器端方法创建配套物料
        try:
            # 导入创建配套物料的函数
            from key_test.add_item_semi import create_supporting_items_and_variants
            
            # 将prefixes也转换为JSON字符串
            prefixes_json = json.dumps(selected_prefixes)
            
            # 调用创建函数
            create_result = create_supporting_items_and_variants(
                item_group=template_item.item_group,
                item_template_name=template_item.item_name,
                custom_model_id=custom_model_id,
                attributes=attributes_json,
                prefixes=prefixes_json
            )
            
            # 检查是否有失败的项目
            if create_result and isinstance(create_result, list):
                failed_items = [item for item in create_result if '失败' in str(item) or '错误' in str(item) or '不存在' in str(item)]
                if failed_items:
                    # 只记录失败数量，不记录完整结果
                    frappe.log_error(
                        f"配套物料创建部分失败 - BOM: {bom_doc.name}, 失败数量: {len(failed_items)}",
                        "BOM Auto Copy - Partial Create Failure"
                    )
                    return {
                        'success': False,
                        'message': f'配套物料创建失败，失败数量: {len(failed_items)}',
                        'create_result': create_result
                    }
                else:
                    return {
                        'success': True,
                        'message': '配套物料创建成功',
                        'create_result': create_result
                    }
            else:
                return {
                    'success': False,
                    'message': '配套物料创建返回异常结果',
                    'create_result': create_result
                }
            
        except ImportError:
            # 如果无法导入key_test模块，记录警告但继续执行BOM复制
            frappe.log_error(
                f"无法导入key_test.add_item_semi模块，跳过配套物料创建 - BOM: {bom_doc.name}",
                "BOM Auto Copy - Missing Module"
            )
            return {
                'success': True,
                'message': '跳过配套物料创建（模块不可用），直接执行BOM复制',
                'create_result': None
            }
        
    except Exception as e:
        frappe.log_error(
            f"创建配套物料失败 - BOM: {bom_doc.name}, 错误: {str(e)}",
            "BOM Auto Copy - Create Supporting Items Error"
        )
        return {
            'success': False,
            'message': f'创建配套物料失败: {str(e)}'
        }


@frappe.whitelist()
def replace_bom_item(bom_name, old_item, new_item):
    """把本 BOM 子表里的 old_item 行替换成 new_item（BOM 表单「替换面料」按钮调用）。

    行为：
      - item_name / description / image 取新物料主数据（新料该字段为空时保留原值）
      - 新旧料 stock_uom 必须一致，否则整单中止（避免做出单位不一致的坏 BOM）
      - 单价与成本不自己算：改完 item_code 后 save()，由 ERPNext 的
        BOM.validate() -> calculate_cost() 按本 BOM 的 rm_cost_as_per 重新取价，
        并重算 amount / raw_material_cost / base_raw_material_cost / total_cost
      - 命中 0 行时不做任何写入，直接返回
      - 已提交 BOM 沿用 ERPNext 自己 update_cost() 的做法：
        flags.ignore_permissions + flags.ignore_validate_update_after_submit

    Args:
        bom_name: BOM 名称
        old_item: 要被替换掉的物料编码
        new_item: 新物料编码

    Returns:
        dict: success / matched / details / raw_material_cost / total_cost / warnings
    """
    bom_name = (bom_name or "").strip()
    old_item = (old_item or "").strip()
    new_item = (new_item or "").strip()

    if not (bom_name and old_item and new_item):
        frappe.throw(_("bom_name / old_item / new_item 都不能为空"))
    if old_item == new_item:
        frappe.throw(_("新旧物料相同，无需替换"))
    if not frappe.db.exists("BOM", bom_name):
        frappe.throw(_("BOM {0} 不存在").format(bom_name))
    if not frappe.has_permission("BOM", "write", doc=bom_name):
        frappe.throw(_("没有修改该 BOM 的权限"), frappe.PermissionError)

    new_doc = frappe.db.get_value(
        "Item",
        new_item,
        ["name", "item_name", "description", "image", "stock_uom", "disabled"],
        as_dict=True,
    )
    if not new_doc:
        frappe.throw(_("新物料 {0} 不存在").format(new_item))
    if new_doc.disabled:
        frappe.throw(_("新物料 {0} 已停用").format(new_item))

    # 单位一致性的判据用「新旧物料的 stock_uom」，不用 BOM 行的 stock_uom
    # —— 后者可能是历史脏数据，ERPNext 的 validate() -> set_default_uom() 会自己纠正
    old_uom = frappe.db.get_value("Item", old_item, "stock_uom") or ""

    bom = frappe.get_doc("BOM", bom_name)

    matched = []
    for row in bom.items:
        if row.item_code != old_item:
            continue

        if old_uom and new_doc.stock_uom and old_uom != new_doc.stock_uom:
            frappe.throw(
                _("第 {0} 行单位不一致：原物料 {1}（{2}），新物料 {3}（{4}），已中止").format(
                    row.idx, old_item, old_uom, new_item, new_doc.stock_uom
                )
            )

        matched.append({
            "idx": row.idx,
            "old_item_code": row.item_code,
            "old_item_name": row.item_name,
            "old_rate": flt(row.rate),
        })
        row.item_code = new_item
        row.item_name = new_doc.item_name
        if new_doc.description:
            row.description = new_doc.description
        if new_doc.image:
            row.image = new_doc.image

    if not matched:
        return {
            "success": False,
            "matched": 0,
            "message": _("本 BOM 中没有物料 {0}").format(old_item),
        }

    bom.flags.ignore_permissions = True
    if bom.docstatus == 1:
        bom.flags.ignore_validate_update_after_submit = True
    bom.save()

    # 注意：只 save() 不会刷新单价。ERPNext v15.43 的 calculate_rm_cost 里是
    #   if not self.bom_creator and d.is_stock_item: d.rate = self.get_rm_rate(...)
    # —— 实测（测试机 BOM-PK#KS0001-DM-120-RED-001-1）改完 item_code 后 save()，
    # 行的 rate 仍停在旧料的价（14.5），必须显式调用 ERPNext 自己的 update_cost()
    # 才会按本 BOM 的 rm_cost_as_per 重新取价并重算 raw_material_cost / total_cost。
    # update_parent=False：只动这一张 BOM，父级 BOM 的成本不跟着变（如需级联改成 True）。
    # from_child_bom=True 只是为了压掉 ERPNext 那句 "成本已更新" 的 msgprint。
    bom.update_cost(update_parent=False, from_child_bom=True, update_hour_rate=False)
    bom.reload()
    rates = {}
    for row in bom.items:
        if row.item_code == new_item:
            rates[row.idx] = flt(row.rate)

    warnings = []
    for detail in matched:
        detail["new_rate"] = rates.get(detail["idx"], 0)
        if not detail["new_rate"]:
            warnings.append(_("第 {0} 行未取到新料单价，请手工核对").format(detail["idx"]))

    return {
        "success": True,
        "matched": len(matched),
        "new_item_code": new_item,
        "new_item_name": new_doc.item_name,
        "details": matched,
        "raw_material_cost": flt(bom.raw_material_cost),
        "total_cost": flt(bom.total_cost),
        "warnings": warnings,
    }