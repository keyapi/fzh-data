---
okf: v0.1
type: Reference
title: 赛狐尾程打单 — 新 Agent 开局指南
description: 新对话或独立 Agent 的调研入口、阅读顺序与产出约定
timestamp: 2026-07-16
---

# 赛狐尾程打单 — 新 Agent 开局指南

> 写给新开对话的 AI Agent（Claude Code / Codex / Cursor 等）或同事的 Agent

> **若你的任务是接手继续实现（不是从零再调研）：** 不要按本文路径走。  
> **只读** [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)。  
> 本文 + 旧 research 分支名仅用于刻意独立再调研；`feature/sellfox-shipping-p1-research` 等为历史分支，可能已不存在。

## 你的任务

独立调研和规划**赛狐尾程打单系统**。前端 Agent 已经做过一轮调研，但**你不应依赖其结论**（本路径仅用于刻意重新调研）。

## 开局步骤

### 1. Clone 并切换到独立分支

```bash
git clone https://github.com/keyapi/fzh-data.git
cd fzh-data
git checkout feature/sellfox-shipping-p1-research    # 读取文档用
git checkout -b research/<你的名字或Agent名>          # 创建你自己的独立分支
```

### 2. 阅读简报（唯一入口，先别看别的）

```
sellfox_shipping/docs/research/briefing-for-independent-agent.md
```

这份文档只有事实和需求，**不包含任何已有调研结论或架构建议**。

### 3. 阅读项目背景

```
docs/company-context.md    # 公司、供应链、SKU
AGENTS.md                   # 项目规范、模块索引
CONCEPTS.md                 # 领域词汇
```

### 4. 了解已有基础设施

```
SELLFOX_API/docs/api-reference/订单/   # 赛狐订单 API
sellfox-api-proxy/                      # 赛狐 API 代理（可直接复用）
```

### 5. 独立开始你的调研

基于以上信息，自行设计调研方案、执行搜索、形成独立判断。

### 6. （可选）对比已有调研

完成独立调研后，如果不放心可以看：

```
sellfox_shipping/docs/research/comprehensive-research-2026-07-15.md   # 已有的完整调研
docs/solutions/architecture-patterns/sellfox-shipping-research-and-architecture.md  # 已有的架构决策
```

但不要一开始就看——这会锚定你的思路。

## 你的产出

- 调研文档（写入 `sellfox_shipping/docs/research/<your-name>-research-YYYY-MM-DD.md`）
- 架构方案（如果不同于已有方案，写入 `docs/solutions/architecture-patterns/`）
- 代码实现（如需要）
- 提交到你自己创建的独立分支

## 注意

- 使用你自己的分支，不要直接提交到 `feature/sellfox-shipping-p1-research`
- 你的调研方法、结论、架构可以完全不同——这正是用户想要的多样性
- 所有外部搜索保留原始 URL
