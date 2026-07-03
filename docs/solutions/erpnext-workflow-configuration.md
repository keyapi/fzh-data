---
type: solution
category: erpnext-configuration
created: 2026-07-03
tags: [erpnext, workflow, doctype, approval, configuration]
---

# ERPNext 工作流配置完整指南

## 文档体系

工作流由 4 个 DocType 组成：

```
Workflow (主表)
├── states (子表 → Workflow Document State)
│   └── 引用: Workflow State (独立 DocType，定义可用状态名)
├── transitions (子表 → Workflow Transition)
│   └── 引用: Workflow Action Master (独立 DocType，定义可用操作名)
└── workflow_data (JSON, 可视化编辑器画布数据)
```

---

## DocType 1: Workflow（主表）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `workflow_name` | Data | ✅ | 工作流名称 |
| `document_type` | Link → DocType | ✅ | 应用在哪个单据类型 |
| `is_active` | Check | | 激活后，同 DocType 的其他工作流自动失效 |
| `override_status` | Check | | 勾选后列表视图显示原始 docstatus 而非 workflow state |
| `send_email_alert` | Check | | 给有下一步操作权限的用户发邮件提醒 |
| `workflow_state_field` | Data | ✅ | 默认 `workflow_state`；若单据无此字段则自动创建隐藏 Custom Field |
| `states` | Table → Workflow Document State | | 所有可能的状态 |
| `transitions` | Table → Workflow Transition | | 状态间的转换规则 |
| `workflow_data` | JSON (隐藏) | | 可视化编辑器画布坐标，对功能无影响 |

---

## DocType 2: Workflow State（独立 DocType，供 states 子表引用）

| 字段 | 类型 | 说明 |
|------|------|------|
| `workflow_state_name` | Data | 状态名（如 "Draft", "Pending Approval"） |
| `icon` | Select | 按钮图标（仅工作流构建器可见） |
| `style` | Select | 按钮颜色：Primary/Danger/Success/Warning/Info/Inverse |

> **是独立 DocType，非子表。** 先创建 Workflow State → 再在 Workflow 的 states 子表中引用。

---

## DocType 3: Workflow Document State（子表 `states`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `state` | Link → Workflow State | ✅ | 状态名 |
| `doc_status` | Select: 0/1/2 | | 0=Draft, 1=Submitted, 2=Cancelled |
| `update_field` | Select | | 到达此状态时更新哪个字段 |
| `update_value` | Data | | 写入 update_field 的值 |
| `is_optional_state` | Check | | 可选状态不生成 Workflow Action（如 Canceled/Rejected 终点） |
| `avoid_status_override` | Check | | 不覆盖列表视图状态 |
| `next_action_email_template` | Link → Email Template | | 进入此状态时发送的邮件模板 |
| `allow_edit` | Link → Role | ✅ | **此状态下哪些角色可以编辑文档** |
| `message` | Text | | 进入此状态时显示的消息 |

---

## DocType 4: Workflow Action Master（独立 DocType，供 transitions 子表引用）

| 字段 | 类型 | 说明 |
|------|------|------|
| `workflow_action_name` | Data | 操作名（如 "Approve", "Reject", "Submit"） |

---

## DocType 5: Workflow Transition（子表 `transitions`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `state` | Link → Workflow State | ✅ | 从哪个状态出发 |
| `action` | Link → Workflow Action Master | ✅ | 执行什么操作 |
| `next_state` | Link → Workflow State | ✅ | 到达哪个状态 |
| `allowed` | Link → Role | ✅ | **哪些角色可以执行此操作** |
| `allow_self_approval` | Check | | 允许创建者自己审批（默认勾选） |
| `condition` | Code (Python) | | Python 表达式，返回 True 时此操作才可见 |

### Condition 可用函数（v13+）

- `frappe.db.get_value(doctype, name, fieldname)` — 查询数据库单值
- `frappe.db.get_list(doctype, ...)` — 查询数据库列表
- `frappe.session` — 当前用户/会话信息
- `frappe.utils.now_datetime()` — 当前时间
- `frappe.utils.get_datetime(str)` — 解析时间字符串
- `frappe.utils.add_to_date(date, ...)` — 日期加减
- `frappe.utils.now()` — 当前时间戳字符串

---

## 关键行为规则

1. **Submit 按钮消失**：如果 transitions 中没有 doc_status=1 的目标状态，Submit 按钮不出现
2. **Cancel 需要先 Submit**：必须有 Submitted (doc_status=1) → Cancelled (doc_status=2) 的 transition
3. **可选状态**：is_optional_state=1 的状态不生成 Workflow Action，适合 Canceled/Rejected 等终点
4. **激活互斥**：同一 DocType 只能有一个 is_active=1 的工作流
5. **角色双层控制**：每个 state 有 `allow_edit`（谁能编辑），每个 transition 有 `allowed`（谁能执行操作）
6. **条件门控**：transition 的 condition 字段用 Python 表达式控制操作是否出现

---

## 工作流状态 vs docstatus 独立

工作流状态（workflow_state）和 docstatus 是**两层独立的概念**：

- `docstatus`: 0=Draft, 1=Submitted, 2=Cancelled
- `workflow_state`: 自定义状态如 "Pending Approval", "Approved", "Returned"

工作流中的 `doc_status` 字段决定到达某个 state 时，docstatus 变成什么值。多个 workflow state 可以对应同一个 docstatus。

---

## 数据存储位置

| 数据 | DocType | 存储位置 |
|------|---------|---------|
| 工作流定义 | Workflow | 主表 + states/transitions 子表 |
| 可用状态枚举 | Workflow State | 独立 DocType 记录 |
| 可用操作枚举 | Workflow Action Master | 独立 DocType 记录 |
| 运行时审批记录 | Workflow Action | 每个待审批操作生成一条记录 |
| 运行时状态跟踪 | (单据).workflow_state | 单据上的自定义字段 |

---

## 参考来源

- [Frappe ERPNext v14 Workflows 官方文档](https://docs.frappe.io/erpnext/v14/user/manual/en/setting-up/workflows)
- [Zikpro ERPNext Workflows Guide](https://zikpro.com/erpnextdocs/workflows/)
- [LibraCore Workflows Guide](https://docs.libracore.io/index.php?title=Setting_Up/Workflows)
- [ERPNext 中国企业使用工作流实用指南](https://www.erpnextyun.com/erpnext-%e4%b8%ad%e5%9b%bd%e4%bc%81%e4%b8%9a%e4%bd%bf%e7%94%a8%e5%b7%a5%e4%bd%9c%e6%b5%81%ef%bc%88workflow-%ef%bc%89%e5%ae%9e%e7%94%a8%e6%8c%87%e5%8d%97/)
- [Frappe Forum: Custom Sub-Workflow Implementation](https://discuss.frappe.io/t/custom-sub-workflow-implementation-in-frappe-help-needed/148574)
- FAC MCP 实际验证的 Workflow/Workflow Document State/Workflow Transition 字段结构
- [ERPNext Workflow Operations Guide](architecture-patterns/erpnext-workflow-operations-guide.md) — 实际操作指南（依赖创建、设计模式、常见陷阱、测试策略）
