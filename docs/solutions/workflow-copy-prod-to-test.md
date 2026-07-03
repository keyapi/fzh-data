---
type: solution
category: erpnext-workflow
created: 2026-07-03
tags: [erpnext, workflow, prod-to-test, fac-mcp, rest-api]
---

# 从生产系统复制 Purchase Receipt 工作流 V3 到测试系统

## 任务

将生产系统 (`erpnext.vilavi.cn`) 的 Purchase Receipt 工作流 "采购入库 退库 和 取消 审批V3 退货 先仓库后财务确认" 完整复制到测试系统 (`ensh.vilavi.cn`)。

## 执行结果：成功

| 项目 | 结果 |
|------|------|
| 工作流创建 | ✅ 测试系统已有同名工作流，9 状态 + 11 转换 |
| 工作流激活 | ✅ is_active=1，send_email_alert=1 |
| 与生产对比 | ✅ 状态、转换、角色、条件 完全一致 |

---

## 工作流结构（Purchase Receipt V3）

### 两条核心设计

1. **正常入库 vs 退货分叉** — Draft 提交时根据 `doc.is_return` 条件走向不同路径
2. **取消审批子流程** — 已审批单据可发起取消，走财务主管独立审批

### 9 个状态

| # | 状态名 | DocStatus | 可编辑角色 |
|---|--------|-----------|-----------|
| 1 | Draft | 0 | Purchase Receipt Operator |
| 2 | 待仓库确认 | 0 | Purchase Receipt Operator |
| 3 | 待财务主管审批 | 1 | Finance Supervisor |
| 4 | 财务主管已拒绝 | 1 | Purchase Receipt Operator |
| 5 | 待仓库确认退货 | 0 | Finance Supervisor |
| 6 | Approved | 1 | Purchase Receipt Operator |
| 7 | 取消待财务主管审批 | 1 | Finance Supervisor |
| 8 | 取消审批被拒绝 | 1 | Purchase Receipt Operator |
| 9 | 已取消 | 2 | Finance Supervisor |

### 11 条转换

| # | 从 | 操作 | 到 | 角色 | 条件 |
|---|----|------|----|------|------|
| 1 | 待财务主管审批 | Reject | 财务主管已拒绝 | Finance Supervisor | — |
| 2 | 财务主管已拒绝 | Submit | 待财务主管审批 | Purchase Receipt Operator | — |
| 3 | Approved | 提交取消审批 | 取消待财务主管审批 | Purchase Receipt Operator | — |
| 4 | 取消待财务主管审批 | 批准取消 | 已取消 | Finance Supervisor | — |
| 5 | 取消待财务主管审批 | Reject | 取消审批被拒绝 | Finance Supervisor | — |
| 6 | 取消审批被拒绝 | 返回 | Approved | Purchase Receipt Operator | — |
| 7 | Draft | Submit | 待仓库确认退货 | Purchase Receipt Operator | `doc.is_return == 1` |
| 8 | 待仓库确认退货 | Submit | 待财务主管审批 | Purchase Receipt Operator | — |
| 9 | Draft | Submit | 待仓库确认 | Purchase Receipt Operator | `doc.is_return == 0` |
| 10 | 待财务主管审批 | Apporve | Approved | Finance Supervisor | — |
| 11 | 待仓库确认 | Apporve | Approved | Purchase Receipt Operator | — |

### 业务流程

```
正常入库 (is_return==0):
  Draft → 待仓库确认 → Approved (仓库自批，不经过财务)

退货入库 (is_return==1):
  Draft → 待仓库确认退货 → 待财务主管审批 → Approved (仓库+财务双重审批)

取消已审批:
  Approved → 取消待财务主管审批 → 已取消 (docstatus=2)
                    ├── Reject → 取消审批被拒绝 → 返回 Approved
```

---

## 操作步骤复盘

### 前置条件

| 环境 | 访问方式 | URL |
|------|---------|-----|
| 生产系统 | REST API (token) | `erpnext.vilavi.cn` |
| 测试系统 | FAC MCP | `ensh.vilavi.cn` |

> ⚠️ 生产系统未安装 FAC App，只能通过 REST API 查询。
> 测试系统有 FAC MCP，可以创建/修改文档。
> 两个系统当前使用相同的 API Key/Secret。

### Step 1: 查询生产系统工作流

```python
# REST API 调用
GET https://erpnext.vilavi.cn/api/resource/Workflow/{workflow_name}
Header: Authorization: token {api_key}:{api_secret}
```

返回包含完整 states 和 transitions 子表的 JSON。

### Step 2: 分析依赖差距

对比生产工作流引用的 Workflow State / Workflow Action Master / Role，检查测试系统是否已存在：

```python
# 用 FAC MCP
list_documents("Workflow State")
list_documents("Workflow Action Master")
list_documents("Role")
```

发现测试系统缺少：
- 7 个 Workflow State（系统自带 6 个，但缺本工作流特用的）
- 4 个 Workflow Action Master（系统自带 3 个：Approve/Reject/Review）
- 1 个 Role：Purchase Receipt Operator

### Step 3: 创建依赖项（测试系统，FAC MCP）

**创建顺序很关键**：先创建 Workflow State 和 Workflow Action Master（独立引用），再创建 Role，最后才创建工作流（引用前三者）。

```python
# 7 个 Workflow States
create_document("Workflow State", {"workflow_state_name": "待仓库确认", "style": "Warning"})
create_document("Workflow State", {"workflow_state_name": "待财务主管审批", "style": "Warning"})
create_document("Workflow State", {"workflow_state_name": "财务主管已拒绝", "style": "Danger"})
create_document("Workflow State", {"workflow_state_name": "待仓库确认退货", "style": "Warning"})
create_document("Workflow State", {"workflow_state_name": "取消待财务主管审批", "style": "Warning"})
create_document("Workflow State", {"workflow_state_name": "取消审批被拒绝", "style": "Warning"})
create_document("Workflow State", {"workflow_state_name": "已取消", "style": "Inverse"})

# 4 个 Workflow Action Masters
create_document("Workflow Action Master", {"workflow_action_name": "Submit"})
create_document("Workflow Action Master", {"workflow_action_name": "提交取消审批"})
create_document("Workflow Action Master", {"workflow_action_name": "批准取消"})
create_document("Workflow Action Master", {"workflow_action_name": "返回"})

# Role
create_document("Role", {"role_name": "Purchase Receipt Operator", "desk_access": 1})
```

### Step 4: 创建工作流（含子表）

```python
create_document("Workflow", {
    "workflow_name": "采购入库 退库 和 取消 审批V3 退货 先仓库后财务确认",
    "document_type": "Purchase Receipt",
    "is_active": 1,
    "override_status": 1,
    "send_email_alert": 1,
    "workflow_state_field": "workflow_state",
    "states": [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Purchase Receipt Operator"},
        # ... 9 个状态
    ],
    "transitions": [
        {"state": "Draft", "action": "Submit", "next_state": "待仓库确认退货",
         "allowed": "Purchase Receipt Operator", "condition": "doc.is_return == 1"},
        # ... 11 条转换
    ]
})
```

### Step 5: 验证

用 FAC MCP `fetch("Workflow/工作流名")` 读取刚创建的工作流，逐项对比 production JSON 中的 states 和 transitions。

---

## 关键经验 (Lessons)

### Lesson 67: 工作流复制四层依赖

创建 Workflow 前必须确保以下依赖在目标系统存在：

| 层级 | DocType | 说明 |
|------|---------|------|
| 1 | Workflow State | 所有 state 引用的状态名必须已存在 |
| 2 | Workflow Action Master | 所有 transition 的 action 必须已存在 |
| 3 | Role | 所有 allow_edit 和 allowed 引用的角色必须已存在 |
| 4 | DocType | document_type 指定的 DocType 必须有 workflow_state 字段 |

**缺失检查方法**：
```python
# 提取工作流用到的引用
states_needed = {s["state"] for s in wf["states"]}
actions_needed = {t["action"] for t in wf["transitions"]}
roles_needed = {s["allow_edit"] for s in wf["states"]} | {t["allowed"] for t in wf["transitions"]}
```

### Lesson 68: FAC MCP vs REST API 分工

| 操作 | FAC MCP (测试) | REST API (生产) |
|------|:-:|:-:|
| 查询 Workflow | ✅ | ✅ |
| 创建 Workflow (含子表) | ✅ | ✅ |
| 创建 Workflow State | ✅ | ✅ |
| 创建 Role | ✅ | ✅ |
| Workflow 激活互斥 | ⚠️ 手动处理 | ⚠️ 手动处理 |

两个系统当前共享同一套 API 凭证（`ERP_API_KEY` / `ERP_API_SECRET`），但 `.env.example` 已更新为支持 `PROD_` / `TEST_` 前缀分离。

### Lesson 69: workflow_data 和 workflow_builder_id 非必需

工作流复制时，以下字段可以留空/不填：
- `workflow_data` — 可视化编辑器画布坐标数据，对功能无影响
- `workflow_builder_id` — 子表行的画布 ID 映射，同样非功能性

这些字段仅服务于可视化工作流构建器 UI，不影响审批逻辑。

### Lesson 70: 激活互斥 — 同 DocType 只能有一个活跃工作流

如果测试系统已有一个 Purchase Receipt 的活跃工作流，需要先将旧工作流的 `is_active` 设为 0，再激活新的。否则创建时会静默覆盖（ERPNext 的 Workflow.save() 会自动 deactivate 旧的）。

### Lesson 71: REST API 中文 URL 编码

查询中文名称的工作流时，Python `requests` 库自动处理 URL 编码，不需要手动 `urllib.parse.quote()`。但 curl 命令需要手动编码或用 `--data-urlencode`。

### Lesson 72: 跨系统工作流复制检查清单

```
□ 1. 用 REST API 从生产拉取 Workflow JSON
□ 2. 提取 states/transitions 中引用的 State/Action/Role
□ 3. 在目标系统检查缺失项
     □ Workflow State 是否全有
     □ Workflow Action Master 是否全有
     □ Role 是否全有
     □ DocType 是否存在且支持 workflow
□ 4. 按顺序创建: State → Action → Role → Workflow
□ 5. 验证: fetch 回来逐条对比
□ 6. (可选) 设置 is_active=1
```

---

## 相关文件

- [ERPNext 工作流配置完整指南](erpnext-workflow-configuration.md) — 所有字段和行为规则
- [FAC MCP 部署指南](../fac-mcp-setup.md) — 测试系统 MCP 连接方式
- [FAC 开发实战笔记](../fac-dev-notes.md) — FAC 工具使用技巧和踩坑
- [.env.example](../../EN_API/.env.example) — API 凭证配置模板

---

## 追加：销售出库单审批流（Delivery Note）

### 创建时间：2026-07-03

参考 4 个生产活跃工作流的设计模式，在测试系统新建。

**DocType**: Delivery Note | **7 状态 + 10 转换** | 活动

### 角色

| # | 英文名 | 中文翻译 | 职责 | 来源 |
|---|--------|---------|------|------|
| 1 | Workflow Stock User | 审批流-仓管员 | 填单 + 所有拒绝后的重提 | 已有 |
| 2 | Finance Supervisor | 审批流-财务主管 | 确认是否报税 | 已有 |
| 3 | Workflow Supply Chain Manager | 审批流-供应链经理 | 填总运费 + 最终提交 | **新建** |

### 流程

```
Draft (doc=0)
  ↓ Submit [仓管员]
待财务主管确认报税 (doc=0)
  ↓ Approve [财务主管]          Reject → 财务主管已拒绝 → Submit 回/s Reject 回 Draft
待供应链经理确认运费 (doc=0)
  ↓ Approve [供应链经理]        Reject → 供应链经理已拒绝 → Submit 回/s Reject 级联到财务主管已拒绝
Approved (doc=1)
  ↓ 取消 [供应链经理]
已取消 (doc=2)
```

### 设计要点

- 所有中间状态 doc_status=0，只在 Approved 设 doc_status=1
- 级联回退：供应链经理已拒绝 --Reject[仓管员]--> 财务主管已拒绝 --Reject[仓管员]--> Draft
- 无自循环 Action（中间状态 doc=0 可直接编辑）
- 取消仅从 Approved，使用简单 `取消` Action

### 新建依赖

- 3 个 Workflow State: 待财务主管确认报税, 待供应链经理确认运费, 供应链经理已拒绝
- 1 个 Role: Workflow Supply Chain Manager
- 1 个 Translation: Workflow Supply Chain Manager → 审批流-供应链经理

### URL

测试系统: http://ensh.vilavi.cn/app/workflow/销售出库单审批
- [workflow_prod_output.json](../../EN_API/workflow_prod_output.json) — 生产系统工作流原始 JSON
