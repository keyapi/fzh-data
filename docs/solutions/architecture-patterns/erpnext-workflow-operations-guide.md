---
title: "ERPNext 工作流操作指南：跨系统管理与设计模式"
date: 2026-07-03
category: architecture-patterns
module: frappe_workflow
problem_type: architecture_pattern
component: development_workflow
severity: medium
applies_when:
  - "在 ERPNext 环境之间复制工作流（生产→测试）"
  - "从零开始为任意 DocType 构建新的审批工作流"
  - "调试静默失败的工作流状态转换"
  - "在审批链中设置拒绝/回退路径"
  - "跨系统对齐工作流依赖（State, Action, Role, Translation）"
tags:
  - erpnext
  - workflow
  - approval
  - design-pattern
  - cross-environment
  - frappe-v15
  - role-permissions
---

# ERPNext 工作流操作指南：跨系统管理与设计模式

## 背景

ERPNext (v15) 工作流横跨 4 个关联的 DocType 和两套系统。生产系统 (`erpnext.vilavi.cn`) 运行实际业务工作流；测试系统 (`ensh.vilavi.cn`) 是新工作流开发和复制的试验场。两套系统的访问方式不同：生产系统需要带 token 认证的 REST API，测试系统则有 FAC MCP 工具集。本文档记录了从生产系统复制 Purchase Receipt 工作流 V3 到测试系统、以及从零在测试系统中构建新的 Delivery Note（销售出库单）审批工作流的过程中总结的模式和经验。

## 操作指南

### 1. 工作流依赖层级

每个 Workflow 在创建之前有四层依赖必须存在：

| 层级 | DocType | 作用 |
|-------|---------|---------|
| 1 | Workflow State | 定义工作流状态引用的状态名 |
| 2 | Workflow Action Master | 定义转换规则引用的操作名 |
| 3 | Role | 定义每个状态谁可编辑、每个转换谁可执行 |
| 4 | Workflow | 主文档，将状态、转换、角色串联起来 |

**创建顺序是严格的。** 不能创建一个引用了不存在的状态、操作或角色的 Workflow。

**差距发现模式：**

```python
# 通过 REST API 获取生产系统工作流 JSON 后：
wf = resp.json()["data"]
states_needed = {s["state"] for s in wf["states"]}
actions_needed = {t["action"] for t in wf["transitions"]}
roles_needed = {s["allow_edit"] for s in wf["states"]} | {t["allowed"] for t in wf["transitions"]}

# 然后通过 FAC MCP list_documents 逐一检查测试系统
# 按依赖顺序创建缺失项
```

**实际案例：** 复制 Purchase Receipt V3 需要在测试系统中先创建 7 个 Workflow State、4 个 Workflow Action Master 和 1 个 Role（Purchase Receipt Operator），然后才能创建工作流本身。

### 2. FAC MCP vs REST API 分工

生产和测试使用不同的访问方式：

| 操作 | 生产 (REST API) | 测试 (FAC MCP) |
|-----------|----------------------|----------------|
| 查询 Workflow | `GET /api/resource/Workflow/{name}` | `get_document("Workflow", name)` |
| 创建 Workflow（含子表） | `POST /api/resource/Workflow` + JSON body | `create_document("Workflow", {...})` |
| 创建依赖项 | `POST /api/resource/{doctype}` | `create_document(doctype, {...})` |
| 执行工作流操作 | Workflow action API | `run_workflow(doctype, name, action)` |
| 列表查询 | `GET /api/resource/{doctype}` + filters | `list_documents(doctype, filters)` |

**REST API 调用示例（生产系统）：**

```python
import requests, json

session = requests.Session()
session.headers["Authorization"] = f"token {api_key}:{api_secret}"
session.headers["Accept"] = "application/json"
resp = session.get(
    "https://erpnext.vilavi.cn/api/resource/Workflow/采购入库 退库 和 取消 审批V3"
)
wf = resp.json()["data"]  # 返回包含 states 和 transitions 子表的完整 JSON
```

**FAC MCP 创建示例（测试系统）：**

```python
create_document("Workflow", {
    "workflow_name": "销售出库单审批",
    "document_type": "Delivery Note",
    "is_active": 1,
    "send_email_alert": 1,
    "states": [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Workflow Stock User"},
        {"state": "待财务主管确认报税", "doc_status": "0", "allow_edit": "Finance Supervisor"},
    ],
    "transitions": [
        {"state": "Draft", "action": "Submit", "next_state": "待财务主管确认报税",
         "allowed": "Workflow Stock User"},
    ]
})
```

注意 `create_document` 直接接受子表数组 —— FAC MCP 内部处理了关系关联。

### 3. 命名规范

**带 Workflow 前缀的角色：**
- 英文名: `Workflow-` 前缀（如 `Workflow Stock User`、`Workflow Supply Chain Manager`）
- 中文显示名（通过 Translation doctype）: `审批流-` 前缀（如 `审批流-仓管员`、`审批流-供应链经理`）

**不带 Workflow 前缀的存量角色（未改名，改动风险大）：**
- `Finance Supervisor`、`Chief Financial Officer` —— 跨多个工作流使用，创建早于命名规范

**Workflow State:** 直接用中文，描述审批阶段：
- `待财务主管确认报税`、`待仓库确认`、`供应链经理已拒绝`

**Workflow Action:** 中文或英文，尽量复用已有的：
- `Approve`、`Reject`、`Submit` —— 系统默认
- `取消`、`批准取消`、`返回` —— 按需自定义中文操作

### 4. 翻译管理

角色在中文界面中的显示名通过 `Translation` doctype 管理，而非直接在 Role doctype 中设置：

```python
create_document("Translation", {
    "language": "zh",
    "source_text": "Workflow Supply Chain Manager",
    "translated_text": "审批流-供应链经理"
})
```

生产和测试两套系统应保持翻译对齐。创建 Role 后应立即创建对应的 Translation。

### 5. 工作流设计模式

研究了 4 个生产系统活跃工作流后，总结出三个一致的模式：

**拒绝状态模式：**
- `allow_edit` = 执行拒绝的审批者（打回人，可以批注/修正文档）
- `Submit` 转换（从已拒绝回到待审批）= 上游角色（重新提交审批的人）
- 示例：`财务主管已拒绝` 状态 —— allow_edit=`Finance Supervisor`，Submit 转换 allowed=`Workflow Stock User`

**中间状态 doc_status=0 模式：**
- 最终审批之前的所有状态保持 `doc_status=0`（允许指定角色编辑）
- 只有最终的 Approved 状态设 `doc_status=1`（触发真正的文档提交）
- 已取消状态设 `doc_status=2`
- 这样避免了提交验证过早触发 —— 对于 Delivery Note，库存验证只在 doc_status=1 时运行

**简单拒绝模式（无级联）：**
- 每个拒绝创建一个单步循环：拒绝 → 重新提交回同一个审批者
- 避免多步级联回退，除非业务逻辑要求上游重新审核

### 6. 跨系统对齐流程

1. **从生产导出**（REST API）：拉取工作流 JSON 及全部子表数据
2. **与测试对比**：用 FAC MCP `list_documents` 检查测试系统已有内容
3. **按依赖顺序创建缺失项**：State → Action → Role → Translation → Workflow
4. **核验数量对齐**：对比状态数、转换数、角色分配

指导本文档的会话完成了一次全面对齐：在测试系统中创建了 21 个 Workflow State + 4 个 Workflow Action Master + 14 个 Role + 15 个 Translation，与生产系统完全匹配。

### 7. 常见陷阱

**Administrator 不会自动拥有工作流角色。**
用户 `Administrator` 必须显式分配工作流角色（Workflow Stock User、Finance Supervisor 等）。没有这些角色，工作流操作按钮在 UI 中不可见。工作流转换是基于具体 Role 控制的，而非系统级权限。

**FAC App 的 WorkflowTransitionError bug。**
Frappe v15 中不存在 `frappe.exceptions.WorkflowTransitionError`。当工作流 Approve 触发 doc 提交但验证失败时，FAC 抛出 `AttributeError` 而非传播真实错误（如"库存不足"）。遇到 Approve 报 AttributeError 时，先检查底层文档的提交验证。

**库存验证阻碍 doc_status=1 的转换。**
当 Approved 状态设 `doc_status=1` 时，底层文档的 `on_submit` 验证会执行。对于 Delivery Note，这意味着必须有可用库存。测试时使用有实际库存的商品。

**中文 URL 编码。**
Python `requests` 库自动处理 URL 编码。curl 等其他工具不会。使用 curl 时需要手动百分号编码中文字符。

**workflow_data 和 workflow_builder_id 无功能影响，但影响设计器显示。**
这两个字段存储可视化构建器的画布坐标和节点 ID。通过 FAC MCP / REST API 创建的工作流，`workflow_data` 为 null，`workflow_builder_id` 为空——这会导致用工作流设计器打开时，所有状态节点和操作节点挤在一条线上。需要在设计器中手动拖拽布局，保存后 `workflow_data` 才会填充。

**因此，在复制工作流或保存工作流快照时，应同时保存 `workflow_data` 字段**，以便将来重建时设计器能直接显示直观的图形布局。保存后的布局 JSON 快照应放入 `EN_API/` 目录供后续参考。

还可以通过算法自动生成合理的布局数据，详见 [工作流设计器画布自动布局算法](workflow-builder-layout-algorithm.md)。

```python
# 保存工作流布局数据
layout = {
    'workflow_name': wf['workflow_name'],
    'workflow_data': wf['workflow_data'],  # 画布坐标
}
# 每个子表行也有 workflow_builder_id，用于关联画布上的节点
for s in wf['states']:
    s_id = s.get('workflow_builder_id')  # 如 "1", "2", "3"...
for t in wf['transitions']:
    t_id = t.get('workflow_builder_id')  # 如 "action-1", "action-2"...
```

**列表视图默认不显示 workflow_state。**
`workflow_state` 自定义字段自动创建时 `hidden=1` 且 `in_list_view=0`。要使其在文档列表页可见，需更新 Custom Field：

```python
update_document("Custom Field", "Delivery Note-workflow_state", {
    "hidden": 0,
    "in_list_view": 1
})
```

### 8. 创建工作流后的设置步骤

1. **为测试/管理员用户分配工作流角色** —— Administrator 不会自动拥有工作流角色；使用 `update_document("User", "Administrator", {"roles": [{"role": "Workflow Stock User"}, ...]})`
2. **在列表视图中显示 workflow_state** —— 更新自动创建的 Custom Field，设置 `hidden=0, in_list_view=1`
3. **验证自定义字段已创建** —— `workflow_state` 字段在工作流首次以 `is_active=1` 保存时，由系统在 DocType 上自动创建

### 9. 工作流测试策略

1. 创建测试文档时使用有实际库存的商品（针对可提交 DocType）
2. 用 `run_workflow` 逐条走一遍每条转换
3. 验证每个状态的 `next_available_actions` 与预期转换一致
4. 同时测试审批路径和拒绝路径
5. 从 Approved 状态测试取消
6. 验证 doc_status 递进：中间状态始终 0，Approved 时 0→1，已取消时 1→2

Delivery Note 工作流测试序列示例：

```python
# 用有库存的商品创建测试文档
create_document("Delivery Note", {"customer": "波兰公司", "items": [{"item_code": "PK#KS0001-DM-194-YELLOW", "qty": 1}]})

# 走通完整路径
run_workflow("Delivery Note", "DN-xxxx", "Submit")  # Draft → 待财务主管确认报税 (doc=0)
run_workflow("Delivery Note", "DN-xxxx", "Approve")  # → 待供应链经理确认运费 (doc=0)
run_workflow("Delivery Note", "DN-xxxx", "Approve")  # → Approved (doc=1)
run_workflow("Delivery Note", "DN-xxxx", "取消")      # → 已取消 (doc=2)

# 测试拒绝路径
run_workflow("Delivery Note", "DN-yyyy", "Reject")   # → 财务主管已拒绝
run_workflow("Delivery Note", "DN-yyyy", "Submit")   # → 待财务主管确认报税 (重新提交)
```

## 为什么重要

ERPNext 工作流的搭建容易出错、调试成本高。缺失依赖项导致静默失败。缺失角色导致操作按钮消失却不报错。doc_status 字段静默控制文档验证是否运行。遵循本文档的模式可以创建在不同环境中行为一致的工作流。

## 适用场景

- 将现有生产工作流复制到测试系统
- 为任意 DocType 从零构建新的审批工作流
- 排查工作流操作按钮不可见的问题
- 调试 FAC MCP 中的工作流转换失败
- 为已有工作流添加新角色
- 对齐生产和测试系统的工作流翻译

## 示例

**从生产复制 Purchase Receipt V3 到测试：**

1. 从生产拉取：`GET /api/resource/Workflow/采购入库 退库 和 取消 审批V3`
2. 提取需要：7 个 State、4 个 Action、1 个 Role
3. 按顺序创建缺失依赖：State → Action → Role
4. 创建 Workflow（含完整 states 和 transitions 子表）
5. 验证：9 状态 + 11 转换，与生产一致

**从零构建 Delivery Note 审批工作流：**

1. 研究 4 个生产工作流，提取设计模式
2. 定义 7 个状态：Draft、待财务主管确认报税、财务主管已拒绝、待供应链经理确认运费、供应链经理已拒绝、Approved、已取消
3. 定义 8 条转换，每条带角色分配（每个拒绝状态通过上游角色的 Submit 回到待审批）
4. 创建新依赖：3 个 Workflow State、1 个 Role、1 个 Translation
5. 创建 Workflow
6. 用有库存的商品测试全部路径 —— 8 条转换全部验证通过

## 相关文档

- [ERPNext 工作流配置完整指南（字段参考）](../erpnext-workflow-configuration.md)
- [生产→测试工作流复制实录（Purchase Receipt V3 + 销售出库单）](../workflow-copy-prod-to-test.md)
- [FAC 开发实战笔记（Lessons 62-72）](../../fac-dev-notes.md)
- [生产系统工作流 JSON 快照](../../../EN_API/workflow_prod_output.json)
- [API 凭证模板](../../../EN_API/.env.example)
