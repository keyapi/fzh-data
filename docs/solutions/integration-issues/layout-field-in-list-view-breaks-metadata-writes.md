---
okf: v0.1
type: Reference
title: 布局类字段带 in_list_view=1 会让整个 DocType 的元数据写不进去（现象是「每次登录都弹窗」）
date: 2026-10-08
category: integration-issues
module: erpnext
problem_type: integration_issue
component: erpnext-metadata
severity: high
applies_when:
  - "用户每次登录后都弹 `'In List View' not allowed for type ... in row N`，刷新就没事"
  - "任何 Custom Field / Property Setter / DocType / Customize Form 的保存报 above 错误（不是这一条字段本身）"
  - "fixtures 或 create_custom_fields(..., ignore_validate=True) 导入的字段把布局类字段标了 in_list_view"
  - "要排查「谁在登录时写元数据」（on_session_creation / after_migrate 钩子）"
tags: [erpnext, frappe, custom-field, property-setter, fixtures, on-session-creation, doctype-meta, login-popup, work-order-task, key-test]
---

# 布局类字段带 in_list_view=1 会让整个 DocType 的元数据写不进去

## Context

2026-10-08 用户反馈：生产 `erpnext.vilavi.cn` 与测试 `ensh.vilavi.cn` 上**每个用户每次登录后都会弹一次** Message 弹窗，点刷新就好：

```
'In List View' not allowed for type Section Break in row 197   （生产）
'In List View' not allowed for type Section Break in row 196   （测试）
```

三个现象需要同时解释：① 所有用户都弹；② 两台都弹；③ 刷新就不弹。答案不是「有段 JS 报错」，而是**登录时会写元数据，而元数据的校验被一个坏字段永久挡死**。

## 根因

### 1. 坏字段：布局类字段不许进列表视图

Frappe 对「不落库的字段类型」做了硬限制。`check_in_list_view()`（`frappe/core/doctype/doctype/doctype.py`）在保存任何 DocType / Custom Field / Property Setter / Customize Form 时都会跑：

```python
d.in_list_view and d.fieldtype in not_allowed_in_list_view   →   frappe.throw(
    "'{property_label}' not allowed for type {fieldtype} in row {idx}")
```

`not_allowed_in_list_view` = `no_value_fields` + `Attach Image`：

```
Section Break / Column Break / Tab Break / HTML /
Table / Table MultiSelect / Button / Image / Fold / Heading
```

**子表（istable=1）例外**：`Button` / `HTML` 在子表里合法（报错文案会变成 `In Grid View`）。判定逻辑见 `get_fields_not_allowed_in_list_view(meta)`。

本次实际坏的 6 条（**都在 Custom Field 表里，来自 `work_order_task` 应用的 fixtures**）：

| dt | fieldname | fieldtype | 生产 idx | 测试 idx |
|---|---|---|---|---|
| Item | `item_languages_section` | Section Break | 196 | 195 |
| Item | `item_languages` | Table | 197 | 196 |
| Tracking Number | `stock_level_section` | Section Break | 19 | 20 |
| Tracking Number | `stock_level_display` | HTML | 20 | 21 |
| Tracking Number | `usage_detail_section` | Section Break | 21 | 22 |
| Tracking Number | `usage_detail_display` | HTML | 22 | 23 |

### 2. 行号怎么读

弹窗里的 `row N` 是 **合并后字段顺序的序号**（`df.idx`，DocField + Custom Field 一起排），不是 `tabCustom Field.idx` 本身。本次 `Item` 合并后共 214 个字段，`item_languages_section` 在第 196 位（测试）——比它自己的 `idx=195` 大 1。**对齐行号的唯一可靠办法是把 doctype 的字段顺序拉出来数**（`frappe.get_meta(dt, cached=False).fields`，或 REST/FAC 拿 `get_doctype_info`）。

### 3. 触发点＝登录，不是后台任务

`key_test` 应用的 `hooks.py`：

```python
on_session_creation = [
    "key_test.setup.after_migrate",
    "key_test.monkey_patches.report_patches.apply_all_patches"
]
```

**每次会话创建（即每次登录）都会跑**，而 `key_test/setup.py:after_migrate()` 干的是：

```python
create_custom_fields(get_custom_fields(), update=True)          # 写 Item/其它 doctype 的自定义字段
make_property_setter('Item', 'weight_template_variant', 'in_list_view', 0, 'Check')   # 写 Item 的 Property Setter
```

`CustomField.on_update` / `PropertySetter.on_update` 都会调
`validate_fields_for_doctype(self.dt)` → 校验该 doctype 的**全部**合并字段 → 撞上坏字段 → `frappe.throw`。
于是：**登录写 Item 元数据 → 抛错 → 错误跟着登录响应回到浏览器 → 弹窗**。

- 为什么所有人都会遇到：`on_session_creation` 对每个新会话都跑。
- 为什么两台都弹：`key_test` 生产/测试都装了。
- **为什么刷新就好**：刷新不新建会话，不再跑 hook（会话 Cookie 已经建立，刷新直接进 Desk）。
- 为什么 Error Log 里查不到：`frappe.throw` 的 ValidationError 只回给请求方，不进 Error Log / Scheduled Job Log（这也反过来证明了**它不是后台任务**）。

### 4. 坏值为什么能落库

fixtures 同步 / `create_custom_fields(..., ignore_validate=True)` 会**跳过校验**，所以 `in_list_view: 1` 一路进库（`is_system_generated=1`、`modified` 被钉在源 JSON 的日期上，就是这类导入的指纹）。

## 检测（只读盘点）

盘点必须用**完整**的布局类型集合——只查 `Section Break` 会漏掉 `Table` / `HTML` / `Attach Image`（本次第一遍就漏了 Table，导致修完第一条又冒出下一条）：

```bash
# 生产 = 阿里云-FZH-ERPNext-frappe ；测试 = sh-erpnext-test-frappe
ssh <host> 'cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn mariadb' < inventory.sql
```

```sql
SELECT cf.name, cf.dt, cf.fieldtype, dt.istable
  FROM `tabCustom Field` cf JOIN `tabDocType` dt ON dt.name = cf.dt
 WHERE cf.fieldtype IN ('Section Break','Column Break','Tab Break','HTML','Table','Table MultiSelect','Button','Image','Fold','Heading','Attach Image')
   AND cf.in_list_view = 1 AND NOT (dt.istable = 1 AND cf.fieldtype IN ('Button','HTML'));

SELECT df.parent, df.fieldname, df.fieldtype, dt.istable
  FROM `tabDocField` df JOIN `tabDocType` dt ON dt.name = df.parent
 WHERE df.fieldtype IN ('Section Break','Column Break','Tab Break','HTML','Table','Table MultiSelect','Button','Image','Fold','Heading','Attach Image')
   AND df.in_list_view = 1 AND NOT (dt.istable = 1 AND df.fieldtype IN ('Button','HTML'));

SELECT ps.doc_type, ps.field_name, df.fieldtype
  FROM `tabProperty Setter` ps JOIN `tabDocField` df ON df.parent = ps.doc_type AND df.fieldname = ps.field_name
 WHERE ps.property='in_list_view' AND ps.value='1' AND df.fieldtype IN (... 同上一串 ...)
UNION ALL SELECT ps.doc_type, ps.field_name, cf.fieldtype
  FROM `tabProperty Setter` ps JOIN `tabCustom Field` cf ON cf.dt = ps.doc_type AND cf.fieldname = ps.field_name
 WHERE ps.property='in_list_view' AND ps.value='1' AND cf.fieldtype IN (... 同上一串 ...);
```

现成脚本：`EN_API/check_layout_in_list_view.py`（默认只读盘点，`--apply` 才写）。

## 修复

**不能走正常保存**：`CustomField.on_update` / `PropertySetter.on_update` 会跑同一个校验，被坏字段挡住（鸡生蛋）。只能 DB 层写入 + 清缓存：

```sql
UPDATE `tabCustom Field` SET in_list_view = 0, modified = NOW(), modified_by = 'Administrator'
 WHERE name IN ('Item-item_languages_section','Item-item_languages',
                'Tracking Number-stock_level_section','Tracking Number-stock_level_display',
                'Tracking Number-usage_detail_section','Tracking Number-usage_detail_display')
   AND fieldtype IN ('Section Break','HTML','Table') AND in_list_view = 1;
```

```bash
ssh <host> 'cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn mariadb' < fix.sql
ssh <host> 'cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn clear-cache'
```

（Section Break / HTML / Table 都没有数据列，`in_list_view` 也不是 schema 属性，改它不动表结构。）

**还要修源头**，否则会复发：`fixtures` 同步会**更新**已存在的 Custom Field，下次 `bench migrate` 就把 `in_list_view: 1` 写回来。

- 应用仓库 `keyapi/work_order_task` → `work_order_task/fixtures/custom_field.json` 的 6 处 `"in_list_view": 1` 改为 `0`（[PR #2](https://github.com/keyapi/work_order_task/pull/2)，diff 只有 6 行）。**已按 EN 自定义 app 流程走完**（2026-10-08）：测试系统分支验证 → 合并 main（`331d5c6`）→ 两台 `git pull` + `migrate` + `clear-cache` +（生产）`bench restart`。生产该 app 的远端名是 **`upstream`**（不是 `origin`），流程见 `CONTRIBUTING.md`「EN 自定义 app 的开发与发布流程」。
- 顺带核对 `work_order_task/work_order_task/commands/install_custom_fields.py`（`after_migrate` 钩子，`create_custom_fields(..., ignore_validate=True)`）与 `key_test/setup.py` 的 `get_custom_fields()` 是否也定义这些字段——本次核对均未命中。

## 验证

```bash
# A. 元数据校验（只读，修前必抛、修后应打印 VALIDATE_OK）
ssh <host> 'cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn console'
>>> from frappe.core.doctype.doctype.doctype import validate_fields_for_doctype
>>> validate_fields_for_doctype("Item"); validate_fields_for_doctype("Tracking Number")
# B. 重放登录时那段 hook（等价于一次登录；幂等）
>>> from key_test import setup; setup.after_migrate(); frappe.db.commit()
# C. 浏览器真实登录：登录后不应再有弹窗；并复查盘点 SQL 无命中
```

**「hook 真的跑了」的旁证**：登录后看 `tabProperty Setter` 里 `Item-weight_template_variant-*` 的 `modified` 是否＝刚才（hook 每次登录都写它）。本次生产登录 11:10:01 写入、页面无弹窗 ⇒ 登录路径确实被校验过且通过。

**判弹窗别 grep 原始 HTML**：Frappe 会把整份消息模板（含 `'In List View' not allowed for type {0} in row {1}` 及其翻译）塞进每个 Desk 页面的 `**.js` 里，`page.content()` 里必然出现这句话。要看「有没有真弹窗」，得看渲染出来的对话框（Playwright 的 a11y snapshot / `document.querySelector('.modal.show, .msgprint-dialog')`），否则必然误报。

## 遗留 / 边界

- **同类潜伏**：`Item Group Image.image_file`（`Attach Image`，子表 `Item Group Image`，module `Vilavi PIM`）在**两台**都带 `in_list_view=1`。子表只豁免 `Button`/`HTML`，`Attach Image` 不豁免 → 保存该 doctype 的元数据会报 `'In Grid View' not allowed for type Attach Image in row 1`（2026-10-08 在测试实测复现）。它是应用自带 DocField（不是本次登录弹窗的原因），**未动**——清掉会移除子表里的缩略图，属功能取舍。已交给应用负责人：[keyapi/vilavi_pim#1](https://github.com/keyapi/vilavi_pim/issues/1)（附件里 `item_group_image.json` 的 `"in_list_view": 1` 需改 0）。
- **放大器**：`key_test` 把 `setup.after_migrate` 挂在 `on_session_creation` 上（每次登录写元数据）本身是隐患——它把「一次元数据错误」放大成「每个用户每次登录都报错」。建议单独评估，本次未改。
- `Customize Form` 里对 `in_list_view` 有一份**同文案的 `frappe.msgprint`**（`frappe/custom/doctype/customize_form/customize_form.py:361-367`，不抛异常）；弹窗标题是 "Message" 时可能是它，也可能是 `throw` 的响应——两者文案一致，靠「有没有落库失败」和上面的链路区分。

## 相关文件

| 位置 | 说明 |
|---|---|
| `apps/work_order_task/work_order_task/fixtures/custom_field.json` | 坏值源头（6 处），PR 在 `keyapi/work_order_task` |
| `apps/key_test/key_test/hooks.py` / `setup.py` | `on_session_creation` → 每次登录写 Item 元数据 |
| `apps/frappe/frappe/core/doctype/doctype/doctype.py` | `check_in_list_view()` / `get_fields_not_allowed_in_list_view()` |
| `apps/frappe/frappe/custom/doctype/custom_field/custom_field.py` | `on_update` → `validate_fields_for_doctype` |
| `apps/frappe/frappe/custom/doctype/property_setter/property_setter.py` | 同上（`validate_fields_for_doctype` 默认 True，`ignore_validate=True` 可跳过） |
| `EN_API/check_layout_in_list_view.py` | 只读盘点 / `--apply` 修复脚本 |
| `docs/solutions/conventions/erpnext-workflow-operations-guide.md` | 改 Custom Field 的常规姿势（正常保存路径） |
