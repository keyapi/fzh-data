# FAC 开发实战笔记

> 最后更新：2026-06-09  
> 面向：B 类技术开发同事  
> 前提：已部署 FAC MCP（见 [fac-mcp-setup.md](fac-mcp-setup.md)）  
> 用途：记录了在测试站使用 FAC 过程中发现的能力、限制和踩坑经验

---

## FAC 能力速览

FAC 通过 MCP 暴露了 24 个工具，覆盖日常 ERP 操作：

| 类别 | 工具 | 已验证 |
|------|------|--------|
| 查询 | `list_documents`, `get_document`, `search_documents` | ✅ |
| 写入 | `create_document`, `update_document`, `delete_document` | ✅ |
| 提交 | `submit_document` | ✅ |
| 报表 | `report_list`, `report_requirements`, `generate_report` | ✅ |
| 工作流 | `get_pending_approvals`, `run_workflow` | ✅ |
| 元数据 | `get_doctype_info` | ✅ |

### 已验证的操作

- 查询 Work Order（生产工单）、Initial Work Order（开料工单）
- 查询 Work Order 的 BOM 物料子表和工序子表
- 生成自定义 Script Report（BOM Cost List，1,042 行 × 70 列）
- 查看待审批单据

---

## Lesson 62: 已提交工单不能通过 API 修改核心字段

**现象**：Work Order（docstatus=1, Submitted）通过 `update_document` 修改 `qty` 会失败。ERPNext 标准 API 不允许编辑已提交单据的核心字段。

**可行路径**：
1. **Cancel + Amend**：取消原单 → ERPNext 自动生成修正版本 → 在新单上改数量
2. **bench console**：`frappe.db.set_value("Work Order", "WO-xxx", "qty", 9)` 直接用 DB 层 API 绕过业务校验（风险：BOM 需求量、物料预留不会自动重算）
3. **自定义 App 功能**：如果 `work_order_task` 等自定义 App 有"变更物料"按钮，它内部可能用了 `db_set` 或自己处理了副作用

**教训**：FAC 走的是标准 REST API，不提供 DB 直写能力。涉及已提交单据的修改，要么走标准工作流（Cancel+Amend），要么写 `bench execute` 脚本。

---

## Lesson 63: 中文 DocType 名称 FAC 搜不到——用英文原名

**现象**：用 `list_documents("开料工单")` 报错 `('DocType', '开料工单')`，用 `list_documents("Initial Work Order")` 成功。

**原因**：FAC 的 DocType 查找是按数据库表名（英文），不支持中文 UI label。自定义 App 的 DocType 即使 label 是中文，system name 也是英文。

**教训**：
- 不确定英文名 → 用 `search_doctype` 或 `get_doctype_info` 查
- App 自定义的 DocType 名可以在 ERPNext UI **设置 → 文档类型** 里查到
- AGENT_HANDOFF.md 或 CLAUDE.md 里可以预记录常用自定义 DocType 的中英对照表

---

## Lesson 64: 自定义 Script Report 的 Filter 自动发现可能静默失败

**现象**：`report_requirements("BOM Cost List")` 返回空 filter 定义，实际有 6 个 filter（`item_group`, `show_disabled`, `simplified_column_view`, `sum_columns_at_end`, `show_ref_code`, `pllc_sfg_missing_use_cover`）。

**根因**（已提交 bug: [FAC #203](https://github.com/buildswithpaul/Frappe_Assistant_Core/issues/203)）：

FAC 的 filter 发现有两条路径，对自定义报表都可能失败：

```
路 A (Python import):
  {module}.report.{report_name_lower} → get_filters() / filters 变量
  对自定义报表通常不存在 (No module named 'key_test.report.bom_cost_list')

路 B (JS 文件解析):
  apps/{app}/{module}/report/{report_name}/{report_name}.js → 括号计数 + 正则
  对自定义报表可能静默失败（路径不对/parser bug）
```

**绕过方案**：
1. **对话中直接告诉 Claude filter 定义**（最可靠）
2. **在 Python 模块中增加 `filters = [...]` 变量**（让路 A 能走通）
3. **在项目文档中记录常用报表的 filter 字典**，Claude 读 CLUADE.md 后能自己查

**教训**：你的自定义报表如果 `report_requirements` 返回空，**不要反复试**——直接给 filter 定义。可以在 `AGENT_HANDOFF.md` 或模块文档里记录。

---

## Lesson 65: 给 FAC 提 Issue 时带上诊断结果

**经验**：FAC 的工具返回很"干净"——静默失败时不输出中间诊断信息。给 Paul 提 issue 时，需要在 ERPNext 服务器上跑诊断脚本：

```python
import frappe, os

report_name = "BOM Cost List"
report_doc = frappe.get_doc("Report", report_name)
module = report_doc.module

# 1. Python 模块导入
py_module = f"{module}.report.{report_name.lower().replace(' ', '_')}"
try:
    m = frappe.get_module(py_module)
    print(f"Python filters: {getattr(m, 'filters', 'NOT FOUND')}")
except Exception as e:
    print(f"Python import failed: {e}")

# 2. JS 文件路径
app_path = frappe.get_app_path(module)
js_path = f"{app_path}/{module}/report/{report_name.lower().replace(' ','_')}/{report_name.lower().replace(' ','_')}.js"
print(f"JS path: {js_path}")
print(f"Exists: {os.path.exists(js_path)}")
print(f"Readable: {os.access(js_path, os.R_OK)}")
```

**步骤**：
1. 跑诊断脚本，截图结果
2. 用 `gh issue create --repo buildswithpaul/Frappe_Assistant_Core` 提交（需要 GitHub token）
3. 把诊断结果和 FAC 的原始返回一起附上

---

## Lesson 66: 用 `search_documents` 的搜索范围有限

**现象**：`search_documents("开料工单")` 搜不到自定义 App 的 DocType。

**原因**：`search_documents` 用的是 OpenAI Vector Store，只索引了有限的 DocType 集合（User, DocType, Contact, Customer, Supplier, Item, Company, Employee, Task, Project）。自定义 App 的 DocType **不在索引范围内**。

**教训**：找自定义 DocType 应该用：
1. `search_doctype("DocType", "关键词")` — 在 DocType 注册表里搜
2. 直接 `list_documents("英文名")` — 已知名称时直接查
3. 不要依赖 `search_documents` 找自定义内容

---

## FAC 工具使用提示

### 查询技巧

- `list_documents` 的 filters 格式：`{"field": [">", "value"]}`，值转字符串
- `get_doctype_info` 返回完整字段树（含 Section/Column Break），适合了解结构
- 子表数据随主表一起返回，不需要单独查子表 DocType

### 报表技巧

- **先跑 `report_requirements`**：即使对自定义报表可能返回空，也要先试（能减少瞎猜）
- **Prepared Report 第一次跑慢**：允许背景生成，第二次同 filter 走缓存秒出
- **日期 filter 用 ISO 格式**：`"2026-01-01"`

### 缺陷记录

| 缺陷 | 影响 | 绕过 |
|------|------|------|
| 自定义报表 filter 静默失败 | `generate_report` 盲跑可能 0 行 | 手动提供 filter 名 |
| 中文 DocType 搜不到 | 无法发现新 App 的自定义表 | 用英文原名 |
| 已提交单据不能改 | 不能直接改生产工单数量 | Cancel+Amend 或 bench console |
| `search_documents` 范围有限 | 搜不到自定义 DocType | 用 `search_doctype` |

---

## 相关文档

- [FAC MCP 部署指南](fac-mcp-setup.md) — 如何连接测试站
- [Agent 开发指南](agent-guide.md) — Agent 行为规则和代码约定
- [FAC GitHub](https://github.com/buildswithpaul/Frappe_Assistant_Core) — 源码 + Issues
- [FAC Issue #203](https://github.com/buildswithpaul/Frappe_Assistant_Core/issues/203) — 自定义报表 filter 自动发现 Bug
