# `special_mark` 字段 —— delivery_plan fixtures 片段（留档）

**用途**：在 EN 的「客户物料」子表 `Item Customer Detail` 上加 `special_mark`（Data，标签「特殊标记」），
供 `Item.customer_items` 行打「碎海绵」等特殊标记。**必须走 fixtures**（否则生产不会有该字段）。

**已完成**：2026-10-09 在**测试机** `apps/delivery_plan/` 改好并 `bench migrate` 验证通过
（删字段 → migrate → 从 fixtures 重建成功）。**测试机为未提交改动**（`git status`：`M fixtures/custom_field.json`、`M hooks.py`）。
**生产（无 SSH）尚未部署**。

---

## 改动 1 — `delivery_plan/fixtures/custom_field.json`

在数组末尾**追加**一条（最小追加，勿跑 `export-fixtures` 整份重写）：

```json
 {
  "allow_in_quick_entry": 0,
  "allow_on_submit": 0,
  "bold": 0,
  "collapsible": 0,
  "collapsible_depends_on": null,
  "columns": 0,
  "default": null,
  "depends_on": null,
  "description": null,
  "docstatus": 0,
  "doctype": "Custom Field",
  "dt": "Item Customer Detail",
  "fetch_from": null,
  "fetch_if_empty": 0,
  "fieldname": "special_mark",
  "fieldtype": "Data",
  "hidden": 0,
  "hide_border": 0,
  "hide_days": 0,
  "hide_seconds": 0,
  "ignore_user_permissions": 0,
  "ignore_xss_filter": 0,
  "in_global_search": 0,
  "in_list_view": 0,
  "in_preview": 0,
  "in_standard_filter": 0,
  "insert_after": "ref_code",
  "is_system_generated": 0,
  "is_virtual": 0,
  "label": "特殊标记",
  "length": 0,
  "link_filters": null,
  "mandatory_depends_on": null,
  "modified": "2026-10-09 17:56:00.000000",
  "module": null,
  "name": "Item Customer Detail-special_mark",
  "no_copy": 1,
  "non_negative": 0,
  "options": null,
  "permlevel": 0,
  "placeholder": null,
  "precision": null,
  "print_hide": 0,
  "print_hide_if_no_value": 0,
  "print_width": null,
  "read_only": 0,
  "read_only_depends_on": null,
  "report_hide": 0,
  "reqd": 0,
  "search_index": 0,
  "show_dashboard": 0,
  "sort_options": 0,
  "translatable": 0,
  "unique": 0,
  "width": null
 }
```

## 改动 2 — `delivery_plan/hooks.py`（fixtures 白名单）

在 `"Tongtool Settings-custom_purchase_suppliers",` 之后插入：

```python
				# 客户物料「特殊标记」(Item Customer Detail 子表; 见 EN_API/item_customer_special_mark/AGENT_HANDOFF.md)
				"Item Customer Detail-special_mark",
```

（缩进为 4 个 tab，与同区块一致。）

---

## 生产部署步骤

1. 提交并推送 `delivery_plan`（上述 2 个文件），在生产拉取部署。
2. `bench --site erpnext.vilavi.cn migrate`。
3. 只读校验：`GET /api/resource/Custom Field/Item Customer Detail-special_mark` 返回记录；
   `SHOW COLUMNS FROM tabItem Customer Detail` 出现 `special_mark varchar(140)`。
4. 之后才能执行数据写入（`EN_API/item_customer_special_mark/set_special_mark.py apply --yes`）。

## 回滚
生产删 `Custom Field` 记录 `Item Customer Detail-special_mark` 并 migrate；或 revert app 提交后再 migrate。
