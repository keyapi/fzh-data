---
module: sellfox_shipping
date: 2026-07-16
problem_type: workflow_issue
component: development_workflow
severity: medium
tags:
  - multi-agent-research
  - independent-research
  - parallel-exploration
  - grill-first
  - worktree-isolation
  - breadth-first
---

# 多 Agent 独立并行调研方法论 — 赛狐尾程打单 P1

## Context

赛狐尾程打单系统 P1 阶段需要技术调研和架构决策。用户启动了 3 条完全独立的调研路径（路径 A/B/C），每条路径在不同的 git worktree 上由不同的 AI Agent 独立执行，策略各不相同：
- 路径 A: 深度优先 2-3 个方向 → 后 grill
- 路径 B: 深度优先完全独立 → 后 grill
- 路径 C (本文档): **广度优先，先 grill 再调研**

目的是获得多样化的视角，避免单一 Agent 的调研结论锚定后续决策。

## Guidance

### 1. 开局流程：新 Agent 独立上手的标准步骤

每条独立路径的 Agent 开局遵循 `ONBOARDING.md`：

1. **Clone + 独立分支**：从 `feature/sellfox-shipping-p1-research` 创建独立 worktree 分支，如 `sellfox-shipping-research-agent-c`
2. **读简报**（唯一入口）：`sellfox_shipping/docs/research/briefing-for-independent-agent.md` — 只有事实和需求，不含已有结论
3. **读项目背景**：`docs/company-context.md`, `AGENTS.md`, `CONCEPTS.md`
4. **了解基础设施**：赛狐 API 文档、`sellfox-api-proxy/`
5. **独立调研**：自行设计调研方案，不参考已有调研

### 2. Grill-First 策略：先质疑，后调研

路径 C 的核心区别是**先 grill 再调研**：

- **13 个 grill 问题**分为三类：业务假设 (G1-G5)、技术选型 (G6-G10)、流程设计 (G11-G13)
- Grill 必须在调研**之前**完成——避免被搜索结果的"表面权威"锚定
- 每个问题基于 briefing 文档 + 公司背景 + 代码阅读做出独立判断
- 关键产出：**核心立场声明**（如"Excel 是主力工作流，不是兜底"），用于指导后续调研方向

### 3. 广度优先调研：覆盖更多主题，每项不深入

与深度优先（2-3 个方向深挖）不同，广度优先的目标是：

- **覆盖差异化的领域**：寻找已有调研未覆盖或覆盖不足的盲区
- **每项 ≤ 30 分钟**：2-3 次搜索 + 快速合成
- **8 个主题**覆盖：电商痛点、赛狐物流能力边界、开源失败案例、标签替代方案、规则引擎替代、Excel 工作流自动化、ERPNext 社区情况、Docker 运维现实

### 4. 交叉对比：调研后与已有结论对照

完成独立调研后，系统性对比：
- 哪些一致（互相验证）→ 4 处
- 哪些不同（提供多样性）→ 4 处
- 哪些补充（已有调研未覆盖）→ 5 处

## Why This Matters

单 Agent 调研存在以下风险：
- **锚定效应**：第一个搜索结果会影响后续所有判断
- **深度陷阱**：深入 2-3 个方向后，容易忽略其他重要的维度
- **确认偏误**：Agent 倾向于寻找支持初始假设的证据

多路径并行 + 不同策略组合可以显著降低这些风险。3 条路径的结论交由用户（或汇总 Agent）裁决策，而非任何单一路径主导。

## When to Apply

- 涉及重大技术选型或架构决策的新项目
- 问题域有多个可行的技术方向，没有明显的最优解
- 用户愿意投入额外的 Agent 对话资源换取更全面的视角
- 每条路径的文档必须写入**独立分支**，避免 merge 冲突

## Examples

### 路径 C 的具体执行流程

```bash
# 1. 创建独立 worktree
git worktree add -b sellfox-shipping-research-agent-c \
  worktrees/sellfox-shipping-research-agent-c feature/sellfox-shipping-p1-research

# 2. 读简报（不读已有调研）
cat sellfox_shipping/docs/research/briefing-for-independent-agent.md

# 3. 写独立调研文档（含 grill + 调研）
# → sellfox_shipping/docs/research/research-agent-c-2026-07-16.md

# 4. 提交到独立分支（不修改共享的 index.md/log.md 以避免 merge 冲突）
git add sellfox_shipping/docs/research/research-agent-c-*.md
git commit -m "docs(sellfox-shipping): independent research agent C"
```

### Grill 问题的组织方式

```
业务假设 (G1-G5): 质疑"API 优先"是否真实、Excel 手动上传是否可行、
                 赛狐规则引擎是否已足够、SQLite 是否够用、为什么犹豫 ERPNext

技术选型 (G6-G10): 质疑 FastMCP 绑定风险、三界面是否过度设计、
                  SQLite 迁移成本、Karrio 模式是否适用、服务器资源是否够

流程设计 (G11-G13): 质疑 P1 骨架价值、为什么等 FedEx API、数据模型范围
```

### 文档命名避免冲突

多条路径写入同一目录 `sellfox_shipping/docs/research/` 时，用 agent 标识区分：

```
research-agent-a-2026-07-16.md   # Agent A: 深度优先
research-agent-b-2026-07-16.md   # Agent B: 深度优先完全独立
research-agent-c-2026-07-16.md   # Agent C: 广度优先 + grill-first
```

**共享文件（index.md, log.md）由汇总 Agent 统一更新**，各路径不修改。

## Prevention

- **不要让 Agent 先看已有调研再开始**——这会产生锚定效应，丧失独立路径的价值
- **每条路径使用独立 git worktree**——避免文件冲突，确保真正的隔离
- **简报文档只写事实和需求**——不包含已有结论或架构建议
- **调研完成后才交叉对比**——不要边调研边参考其他路径
- **所有外部搜索保留原始 URL**——方便用户和其他 Agent 验证
