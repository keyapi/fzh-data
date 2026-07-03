---
title: "ERPNext 工作流设计器画布自动布局算法"
date: 2026-07-03
category: architecture-patterns
module: frappe_workflow
problem_type: architecture_pattern
component: development_workflow
severity: medium
applies_when:
  - "通过 FAC MCP 或 REST API 程序化创建 ERPNext 工作流"
  - "需要自动生成 workflow_data JSON 使设计器开箱即显示直观布局"
  - "工作流节点全部堆在一条线上，需要手动拖拽排列"
tags:
  - erpnext
  - workflow
  - canvas-layout
  - workflow_data
  - node-positioning
  - design-pattern
---

# ERPNext 工作流设计器画布自动布局算法

## 背景

ERPNext v15 的工作流设计器（Workflow Builder）是一个前端拖拽式可视化编辑器。画布上每个状态节点和操作节点的位置由 `Workflow` 文档的 `workflow_data` 字段（JSON 格式）控制。通过 FAC MCP 或 REST API 创建的工作流，`workflow_data` 为 null，导致设计器打开时所有节点堆在原点 (0,0)，挤成一条线。用户需手动拖拽排列才能看到清晰的流转图。

分析用户手动排列后的布局数据和 4 个生产工作流的布局数据，发现了一套一致的布局规律，可以编码为自动生成算法。

## 布局规律分析

### 数据来源

分析了两个样本：
- **销售出库单审批**（用户手动排列，7 状态 + 8 操作）
- **采购入库V3**（生产系统，9 状态 + 11 操作）

### 核心规律

```
y≈0:    [Draft]──Submit──[待财务]──Approve──[待供应链]──Approve──[Approved]──取消──[已取消]
                            │                    │
y≈140:                      Reject─┐             Reject─┐
                            │      │             │      │
y≈200~310:              Submit◄─[财务已拒绝]   Submit◄─[供应链已拒绝]
```

**规则 1：审批主线路（y≈0）**
- 所有"前进"路径上的状态节点和操作节点排在同一水平线上
- x 坐标从左到右均匀递增，间距约 300-500px
- Approve、Submit（首次提交）等正向操作放在状态之间

**规则 2：拒绝环挂在下面**
- 每个 Reject 操作从主线路分叉向下 → 到达已拒绝状态（y≈200-350）
- 已拒绝状态的 x 坐标约等于触发它的审批状态的 x 坐标
- Submit（重新提交）从已拒绝状态向左上方回到主线上的审批状态
- 形成视觉上"挂在主线下面的环"

**规则 3：节点尺寸**
- 状态节点：宽度取决于标签长度（81-162px），高度 53-74px
- 操作节点：统一约 51×33px

### 从销售出库单审批提取的坐标（关键参考）

**主线路节点（y≈0）：**

| 节点 ID | 类型 | 名称 | x | y |
|---------|------|------|---|---|
| 1 | state | Draft | 481 | 5 |
| action-1 | action | Submit | 783 | 7 |
| 2 | state | 待财务主管确认报税 | 957 | -3 |
| action-2 | action | Approve | 1474 | 13 |
| 4 | state | 待供应链经理确认运费 | 1713 | -12 |
| action-6 | action | Approve | 2204 | 4 |
| 6 | state | Approved | 2347 | -5 |
| action-10 | action | 取消 | 2749 | 3 |
| 7 | state | 已取消 | 2919 | -6 |

**拒绝环 #1（财务）：**

| 节点 ID | 类型 | 名称 | x | y |
|---------|------|------|---|---|
| action-3 | action | Reject | 1262 | 143 |
| 3 | state | 财务主管已拒绝 | 892 | 310 |
| action-4 | action | Submit | 727 | 197 |

**拒绝环 #2（供应链）：**

| 节点 ID | 类型 | 名称 | x | y |
|---------|------|------|---|---|
| action-7 | action | Reject | 1996 | 112 |
| 5 | state | 供应链经理已拒绝 | 1995 | 241 |
| action-8 | action | Submit | 1562 | 218 |

### 采购入库V3 的复杂布局验证

采购入库V3 包含条件分支（`is_return==1`），验证了多分支场景下同样的规律：
- 主审批线：Draft(347,108) → 待财务主管审批(1420,122) → Approved(1909,109)
- 条件分支状态（待仓库确认、待仓库确认退货）分布在主线的上下方
- 拒绝状态（财务主管已拒绝）挂在 y=578 的下方
- 取消子流程形成第二条水平线：取消待审批(2387,96) → 已取消(2955,94)

## 自动布局算法

### 算法输入

- `states`: 工作流的状态列表（顺序为创建顺序）
- `transitions`: 工作流的转换规则列表

### 算法步骤

**Step 1: 分类转换**

```python
def classify_transitions(transitions, states):
    """将每条转换分类为 forward / reject / resubmit / other"""
    state_names = {s["state"] for s in states}
    rejected = {t["next_state"] for t in transitions 
                if t["action"] in ("Reject", "拒绝")}
    
    for t in transitions:
        if t["action"] in ("Reject", "拒绝"):
            t["category"] = "reject"
        elif t["state"] in rejected and t["action"] in ("Submit",):
            t["category"] = "resubmit"
        elif t["next_state"] not in rejected:
            t["category"] = "forward"
        else:
            t["category"] = "other"
```

**Step 2: 确定主线路状态顺序**

从 Draft 出发，沿 forward 转换遍历，得到主线路上的状态序列。

```python
def find_main_line(transitions, start="Draft"):
    order = [start]
    current = start
    while True:
        forward = [t for t in transitions 
                   if t["state"] == current and t["category"] == "forward"]
        if not forward:
            break
        nxt = forward[0]["next_state"]
        if nxt in order:  # 避免环
            break
        order.append(nxt)
        current = nxt
    return order
```

**Step 3: 计算坐标**

```python
# 常量
STATE_SPACING_X = 450   # 状态之间的水平间距
ACTION_OFFSET_X = 200   # 操作节点距源状态的偏移
REJECT_Y = 150          # 拒绝操作 y 坐标
REJECTED_STATE_Y = 300  # 已拒绝状态 y 坐标
RESUBMIT_Y = 200        # 重新提交操作 y 坐标

def compute_layout(main_line, transitions, states):
    nodes = []
    
    # 主线路状态
    for i, s_name in enumerate(main_line):
        x = 500 + i * STATE_SPACING_X
        width = max(80, len(s_name) * 16 + 40)  # 估算宽度
        nodes.append({
            "type": "state", "id": str(i + 1),
            "position": {"x": x, "y": 0},
            "dimensions": {"width": width, "height": 53}
        })
    
    # 主线路上的正向操作（Approve/Submit）
    action_id = 1
    for t in transitions:
        if t["category"] != "forward":
            continue
        src_idx = main_line.index(t["state"])
        dst_idx = main_line.index(t["next_state"])
        x = 500 + src_idx * STATE_SPACING_X + ACTION_OFFSET_X
        nodes.append({
            "type": "action", "id": f"action-{action_id}",
            "position": {"x": x, "y": 5},
            "data": {"from_id": str(src_idx + 1), "to_id": str(dst_idx + 1)}
        })
        action_id += 1
    
    # 拒绝环
    for t in transitions:
        if t["category"] != "reject":
            continue
        src_idx = main_line.index(t["state"])
        src_x = 500 + src_idx * STATE_SPACING_X
        
        # Reject 操作：从主线向右下偏移
        nodes.append({
            "type": "action", "id": f"action-{action_id}",
            "position": {"x": src_x + 250, "y": REJECT_Y},
            "data": {"from_id": str(src_idx + 1), "to_id": str(len(nodes) + 1)}
        })
        action_id += 1
        
        # 已拒绝状态：在 Reject 操作下方
        rejected_id = str(len([n for n in nodes if n["type"] == "state"]) + 1)
        rej_name = t["next_state"]
        width = max(120, len(rej_name) * 16 + 40)
        nodes.append({
            "type": "state", "id": rejected_id,
            "position": {"x": src_x - 50, "y": REJECTED_STATE_Y},
            "dimensions": {"width": width, "height": 53}
        })
        
        # 找对应的 resubmit
        resubmit = [tr for tr in transitions 
                    if tr["category"] == "resubmit" and tr["state"] == t["next_state"]]
        if resubmit:
            nodes.append({
                "type": "action", "id": f"action-{action_id}",
                "position": {"x": src_x - 250, "y": RESUBMIT_Y},
                "data": {"from_id": rejected_id, "to_id": str(src_idx + 1)}
            })
            action_id += 1
    
    return nodes
```

### 简化实现（完整可用的 Python 函数）

```python
import json

def generate_workflow_data(states, transitions):
    """
    根据工作流的状态和转换定义，生成设计器画布布局 JSON。
    
    states: [{"state": "Draft", ...}, ...]
    transitions: [{"state": "Draft", "action": "Submit", "next_state": "待审批", ...}, ...]
    返回: workflow_data JSON 字符串
    """
    H_SPACING = 450
    Y_MAIN = 0
    Y_REJECT_ACTION = 150
    Y_REJECTED = 310
    Y_RESUBMIT = 200
    
    state_names = [s["state"] for s in states]
    rejected_states = {t["next_state"] for t in transitions if t["action"] in ("Reject",)}
    
    # 主线路：从 Draft 沿非拒绝转换遍历
    main_line = []
    visited = set()
    queue = ["Draft"] if "Draft" in state_names else [state_names[0]]
    while queue:
        s = queue.pop(0)
        if s in visited:
            continue
        visited.add(s)
        main_line.append(s)
        for t in transitions:
            if t["state"] == s and t["next_state"] not in rejected_states and t["next_state"] not in visited:
                queue.append(t["next_state"])
    
    # 分配到主线路的节点编号
    state_ids = {name: str(i + 1) for i, name in enumerate(state_names)}
    main_ids = {name: str(i + 1) for i, name in enumerate(main_line)}
    
    nodes = []
    action_counter = 1
    
    # 主线路状态
    for i, s in enumerate(main_line):
        nodes.append({
            "type": "state",
            "id": main_ids[s],
            "position": {"x": 480 + i * H_SPACING, "y": Y_MAIN},
            "dimensions": {"width": max(80, len(s) * 14 + 50), "height": 53},
            "handleBounds": {"source": [
                {"id": "top", "position": "top", "x": 36, "y": -11, "width": 7, "height": 7},
                {"id": "right", "position": "right", "x": 82, "y": 23, "width": 7, "height": 7},
                {"id": "bottom", "position": "bottom", "x": 36, "y": 57, "width": 7, "height": 7},
                {"id": "left", "position": "left", "x": -11, "y": 23, "width": 7, "height": 7}
            ]},
            "computedPosition": {"x": 480 + i * H_SPACING, "y": Y_MAIN, "z": 0}
        })
    
    # 主线路正向操作
    for t in transitions:
        if t["state"] in main_line and t["next_state"] in main_line and t["action"] not in ("Reject",):
            src_idx = main_line.index(t["state"])
            nodes.append({
                "type": "action",
                "id": f"action-{action_counter}",
                "position": {"x": 480 + src_idx * H_SPACING + 250, "y": Y_MAIN + 5},
                "dimensions": {"width": 51, "height": 33},
                "data": {"from_id": main_ids[t["state"]], "to_id": main_ids[t["next_state"]]}
            })
            action_counter += 1
    
    # 拒绝环
    for t in transitions:
        if t["action"] not in ("Reject",):
            continue
        src = t["state"]
        if src not in main_line:
            continue
        src_idx = main_line.index(src)
        src_x = 480 + src_idx * H_SPACING
        
        # Reject 操作
        aid = f"action-{action_counter}"
        nodes.append({
            "type": "action",
            "id": aid,
            "position": {"x": src_x + 280, "y": Y_REJECT_ACTION},
            "data": {"from_id": main_ids[src], "to_id": state_ids[t["next_state"]]}
        })
        action_counter += 1
        
        # 已拒绝状态
        nodes.append({
            "type": "state",
            "id": state_ids[t["next_state"]],
            "position": {"x": src_x - 50, "y": Y_REJECTED},
            "dimensions": {"width": max(150, len(t["next_state"]) * 14 + 50), "height": 53},
        })
        
        # re-submit 操作
        resubmit = [tr for tr in transitions 
                    if tr["state"] == t["next_state"] and tr["action"] in ("Submit",)]
        if resubmit:
            nodes.append({
                "type": "action",
                "id": f"action-{action_counter}",
                "position": {"x": src_x - 270, "y": Y_RESUBMIT},
                "data": {"from_id": state_ids[t["next_state"]], "to_id": main_ids[src]}
            })
            action_counter += 1
    
    # 已取消状态（挂在最后）
    for s in state_names:
        if s == "已取消" and s not in main_line:
            last_x = 480 + (len(main_line) - 1) * H_SPACING
            nodes.append({
                "type": "state",
                "id": state_ids[s],
                "position": {"x": last_x + H_SPACING, "y": Y_MAIN},
                "dimensions": {"width": 95, "height": 53},
            })
    
    return json.dumps(nodes, ensure_ascii=False)
```

### 条件分支处理（v3 改进）

当工作流包含条件分支（同一状态有多条 forward 转换，如 `is_return==0` vs `is_return==1`）时：

```python
from collections import Counter

# 1. 检测分支点：出度 > 1 的状态
out_degree = Counter(t['state'] for t in forward)
branch_points = {s for s, cnt in out_degree.items() if cnt > 1}

# 2. 检测合并点：被 >1 个 forward 转换指向的状态
merge_targets = Counter(t['next_state'] for t in forward)
merge_points = {s for s, cnt in merge_targets.items() if cnt > 1}

# 3. 主线路保留第一条分支，其余分支做垂直偏移
BRANCH_Y_OFFSET = 120
for bp in branch_points:
    branch_targets = [t['next_state'] for t in forward if t['state'] == bp]
    primary = branch_targets[0]  # 第一条为主路径
    for bt in branch_targets[1:]:  # 其余为分支
        branch_states[bt] = True  # 标记为分支状态

# 4. 布局时分支状态给予 y 偏移
for i, s in enumerate(main_line):
    y = Y_MAIN
    if s in branch_states:
        y = Y_MAIN - BRANCH_Y_OFFSET * (branch_count + 1)
    # ...
```

### 操作防重叠

当同一源状态有多条 forward 转换时，错开位置：

```python
action_offsets = {}
for t in forward:
    key = t['state']
    offset_idx = action_offsets.get(key, 0)
    x = X_START + src_idx * H_SPACING + 220 + offset_idx * 60
    y = Y_MAIN + 5 + offset_idx * 25
    action_offsets[key] = offset_idx + 1
```

### 非标准回退

部分 resubmit 操作不回到拒绝源状态（如 `取消审批被拒绝 --返回--> Approved`），需要按实际目标定位：

```python
resubmits = [t for t in transitions if t['state'] == rej_name and t['action'] in ('Submit', '返回')]
for r in resubmits:
    target = r['next_state']
    if target in main_line:
        dst_idx = main_line.index(target)
        x = (src_x + X_START + dst_idx * H_SPACING) / 2  # 源和目标的中间
```

### 自循环拒绝

当 Reject 的目标就是自身时（如 `Draft --Reject--> Draft`），放在主线下方不远处：

```python
if t['action'] in ('Reject',) and t['state'] == t['next_state']:
    # 自循环 — 放在状态下方 y=120 处
    nodes.append({
        'type': 'action', 'id': f'action-{action_counter}',
        'position': {'x': src_x - 80, 'y': 120},
        'data': {'from_id': state_ids[s], 'to_id': state_ids[s]}
    })
```

## 为什么重要

`workflow_data` 虽然不影响审批功能，但直接影响工作流设计器的可用性。一个自动生成的合理布局能：
1. 省去每次创建后手动拖拽的 5-10 分钟
2. 让审批流程的拓扑结构一目了然（主线 vs 拒绝环）
3. 在复制工作流到生产系统时，保持一致的视觉呈现

## 适用场景

- 通过 API 程序化创建新的审批工作流
- 从生产复制工作流到测试时，同步恢复布局数据
- 想要批量生成多个工作流且每个都有清晰的视觉布局

## 相关文档

- [ERPNext 工作流操作指南](erpnext-workflow-operations-guide.md) — 第 7 节涵盖 workflow_data 陷阱和保存方法
- [ERPNext 工作流配置完整指南](../erpnext-workflow-configuration.md) — workflow_data 字段定义
- [生产→测试工作流复制实录](../workflow-copy-prod-to-test.md) — Lesson 69: workflow_data 非必需但影响设计器
- [销售出库单审批布局快照](../../../EN_API/prod_wf_销售出库单审批_layout.json) — 用户手动排列的参考布局
- [自动生成布局测试输出](../../../EN_API/gen_wf_layout_v2.json) — 算法生成的布局 JSON

---

## 验证记录（2026-07-03）

### 验证方法

1. 备份用户手工排列的 `workflow_data` → `EN_API/prod_wf_销售出库单审批_layout_backup.json`
2. 运行 `generate_workflow_data()` 生成新布局 → 保存至 `EN_API/gen_wf_layout_v2.json`
3. 通过 REST API `PUT /api/resource/Workflow/销售出库单审批` 写入测试系统
4. 更新 6 条 transition 的 `workflow_builder_id` 对齐画布 action 节点（FAC MCP `update_document`）
5. 读取回工作流验证数据结构完整性
6. 恢复用户原始手工布局 + 原始 builder_id

### 验证结果

**数据结构**：算法生成了 7 个 state 节点 + 8 个 action 节点，ID 全部唯一，`from_id`/`to_id` 映射正确。

**坐标对比**：

| 节点类型 | 用户手工 | 算法生成 | 偏差 |
|---------|---------|---------|------|
| Draft | (481, 5) | (480, 5) | ~0 |
| 待财务主管确认报税 | (957, -3) | (930, 5) | x-27 |
| 待供应链经理确认运费 | (1713, -12) | (1380, 5) | x-333 |
| Approved | (2347, -5) | (1830, 5) | x-517 |
| 已取消 | (2919, -6) | (2280, 5) | x-639 |
| 财务主管已拒绝 | (892, 310) | (890, 310) | ~0 |
| 供应链经理已拒绝 | (1995, 241) | (1340, 310) | x-655 |
| Reject action (财务) | (1262, 143) | (1210, 150) | ≈ |
| Reject action (供应链) | (1996, 112) | (1660, 150) | ≈ |

**关键发现**：

1. **y 轴定位精准**：主线路 y≈5（用户 y≈-12~5），拒绝操作 y=150（用户 y=112~143），已拒绝状态 y=310（用户 y=241~310）——拒绝环的垂直分层完全正确。

2. **x 轴间距偏紧**：算法使用固定 H_SPACING=450，用户实际间距更大（用户总宽约 2438px，算法总宽约 1800px）。原因：用户拖拽时给宽标签状态（待财务主管确认报税、待供应链经理确认运费）留了更多空间。

3. **builder_id 对齐**：算法生成的 action ID 序列（action-1~action-8）与 transition 子表的 builder_id 不匹配（用户手动保存后为 action-1~4,6~8,10）。需要额外一步更新 transition 的 builder_id 来对齐画布节点。

4. **缺失元素**：算法未生成 `handleBounds`（连接点锚点）和 `computedPosition`（布局计算位置）字段，但设计器打开时会自动补全，不影响显示。

### 改进方向

- 根据状态名长度动态调整 H_SPACING（中文约占 16px/字）
- action ID 应与 transition 创建顺序保持一致（而非按拓扑分类重排）
- 补充 `handleBounds` 模板数据避免设计器首次加载闪烁

### 二次验证：测试报价工作流（2026-07-03）

**工作流结构**：3 状态 + 4 转换，两条自循环拒绝（Draft→Reject→Draft, Approved by Sales Manager→Reject→同状态）

**算法结果**：正确生成 3 状态在主线 + 2 自循环操作在下方 y=120。与现有布局（斜线排列）相比更直观。

### 三次验证：采购入库V3（2026-07-03）

**工作流结构**：9 状态 + 11 转换，含条件分支（`is_return==1`/`is_return==0`）、合并点、取消子流程、非标准回退（`返回→Approved`）

**v3 改进**：
- 分支检测：Draft 有 2 条 Submit → 待仓库确认（分支，y=-115）和待仓库确认退货（主路，y=5）
- 操作防重叠：两条 Submit 分别放在 (700,10) 和 (760,35)
- 非标准回退：`返回` 从取消审批被拒绝正确指向 Approved（取两点中点）

**对比生产布局**：主线结构一致（Draft→审批→取消顺序正确），分支偏移方向正确。生产布局更宽松（间距更大）且分支放在 Draft 上方而非合并到主线中。
