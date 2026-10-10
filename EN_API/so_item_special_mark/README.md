# 销售订单明细 description / 通途产品名 加「碎海绵」前缀（key_test 后端 + Client Script）

**需求**：上传 Excel 生成销售订单明细时，**同时满足以下 3 个条件**才加前缀：
1. **当前销售订单为 FBA** —— `customer` / `customer_name` 含「FBA」（如「美国FBA仓」）；
2. 该行客户物料号（通途SKU / `Item Customer Detail.ref_code`）的 `special_mark` = `碎海绵`；
3. 该行**命中了 EN 物料**（未命中占位行不加）。

命中时：`description` 与 `custom_tongtool_item_name` 前都加 `碎海绵 `。
例：`成品 三角靠枕-荷兰绒-153-驼色` → `碎海绵 成品 三角靠枕-荷兰绒-153-驼色`。

## 关键澄清：取值在后端，FBA 判定需要 SO 上下文

- Client Script `销售订单 子表 items 上传Excel  客户物料编号 转为 物料编号` 只做搬运；
  `description` / `custom_tongtool_item_name` 的取值在后端 `key_test.item_utils.read_excel_file`。
- 但「当前订单是否 FBA」是**销售订单头**的信息，后端原本拿不到 → 需由 Client Script 把
  `frm.doc.customer` / `frm.doc.customer_name` 传进后端。

## 改动（两处）

### A. 后端 `apps/key_test/key_test/item_utils.py` → `read_excel_file()`
1. 签名加参：`read_excel_file(file_url, customer=None, customer_name=None)`。
2. 函数开头：`so_is_fba = "FBA" in f"{customer or ''} {customer_name or ''}".upper()`。
3. 读行后按 `ref_code` 查 `special_mark` → `special_mark_prefix = "碎海绵 " if (so_is_fba and special_mark=='碎海绵') else ""`。
4. 两处 `description`（命中 / 截短重试）与两处 `custom_tongtool_item_name`（同两个命中分支）加此前缀；
   **未命中占位行不加**。

补丁：`key_test__item_utils.special_mark_prefix.patch`

### B. Client Script（DB 记录，**测试/生产原本完全一致**）
`销售订单 子表 items 上传Excel  客户物料编号 转为 物料编号`，`frappe.call` 的 `args` 加两参：
```js
args: {
    file_url: file_url,
    customer: frm.doc.customer,
    customer_name: frm.doc.customer_name
},
```
补丁：`client_script_upload.patch`（以 prod 原稿为基线，纯 +3 行，行尾保持 CRLF）。
⚠️ Client Script 是**数据库记录**——生产需用 REST `PUT /api/resource/Client Script/<name>` 或后台改；
本文件是"贴进 script 字段"的补丁，不是文件补丁。

## 状态（2026-10-10）

- ✅ **测试机已部署并验证**：
  - 后端：`item_utils.py` 已改 + `bench restart`；备份 `/tmp/item_utils.py.bak4_20261010_103408`。
  - Client Script：已通过 REST PUT 更新（7977 字符，CRLF 一致，lone-LF=0）。
  - 验证（同一标 `碎海绵` 的行）：`customer=美国FBA仓` → 两字段均 `碎海绵 …` ✅；`customer=某某普通公司` → 均无前缀 ✅。
- ⏳ **生产未部署**（需同步 A + B 两处）。
  ⚠️ 生产后端 `item_utils.py` **未比对过**（无 SSH）；Client Script 已比对以 prod 原稿为基线。

## 部署 prod 步骤

```bash
# A. 后端（prod frappe 用户）
cd ~/frappe-bench/apps/key_test        # 备份 item_utils.py
# 手工改那 4 处（或 patch -p1 < key_test__item_utils.special_mark_prefix.patch）
python3 -c "import ast; ast.parse(open('key_test/item_utils.py',encoding='utf-8').read())"
cd ~/frappe-bench && sudo -u frappe bench restart
# B. Client Script：REST PUT 或后台把 args 那 3 行加进 script
#    然后清缓存：frappe.clear_cache(doctype='Sales Order') + 浏览器清 _doctype 缓存
```

## 迁移到 app 文件（2026-10-10，测试机已做 ✅）

原 Client Script 是 **DB 记录**，不便 git 管理 → 迁进 key_test app：
- 新文件 **`key_test/public/js/sales_order.js`**（内容 = 原 Client Script + 3 行头注释；行尾统一 LF）。
- **`key_test/hooks.py`** 的 `doctype_js` 增加 `"Sales Order": "public/js/sales_order.js"`。
- 原 Client Script 置 **`enabled=0`**（防与 app 文件双跑；记录保留可回退，需要时可再删）。

部署/缓存要点：
- 改 `hooks.py` 后必须 `bench restart`（hooks 进程内缓存）；再 `bench --site <site> clear-cache`（DocType meta）。
- 浏览器侧清 `_doctype:Sales Order`（localStorage）后再刷新。
- `sites/assets/key_test` 是软链 → 改 JS **无需 `bench build`**（但 hooks 改动要 restart）。
- **验证**：`GET /api/method/frappe.desk.form.load.getdoctype?doctype=Sales Order` →
  文件内容在 **`__js`**（app 的 doctype_js 汇总，实测含头注释），停用的 Client Script 已不在 **`__custom_js`**。

产物：`key_test_public_js/sales_order.js`、`key_test_git_diff.patch`（含 hooks 改动 + 新文件）。

## 关联

- 打标记的数据来源与范围修正见 `../item_customer_special_mark/AGENT_HANDOFF.md`
  （本轮把范围收敛为 item_group 含「三角」「平条」的 **42 行**，清掉 12 行）。
