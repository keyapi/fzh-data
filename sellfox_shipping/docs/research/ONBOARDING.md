# 赛狐尾程打单 — 新 Agent 开局指南

> 写给新开对话的 AI Agent（Claude Code / Codex / Cursor 等）或同事的 Agent

## 你的任务

独立调研和规划**赛狐尾程打单系统**。前端 Agent 已经做过一轮调研，但**你不应依赖其结论**。

## 开局步骤

### 1. Clone 并切换到独立分支

```bash
git clone https://github.com/keyapi/fzh-data.git
cd fzh-data
git checkout sellfox-shipping-research-agent-a    # 读取文档用
git checkout -b sellfox-shipping-research-agent-b  # 创建你自己的独立分支
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
sellfox_shipping/docs/research/research-agent-a-2026-07-15.md   # Agent A 的完整调研
docs/solutions/architecture-patterns/sellfox-shipping-research-and-architecture.md  # 已有的架构决策
```

但不要一开始就看——这会锚定你的思路。

## 你的产出

- 调研文档写入 `sellfox_shipping/docs/research/`，**按命名约定**（见下）
- 架构方案（如果不同于已有方案，写入 `docs/solutions/architecture-patterns/`）
- 代码实现（如需要）
- 提交到你自己创建的独立分支

### 文件命名约定（防止合并冲突）

所有 Agent 的调研输出写入 `sellfox_shipping/docs/research/`，但使用唯一文件名：

```
research-<agent标识>-<YYYY-MM-DD>.md
```

示例：
```
research-agent-a-2026-07-15.md   (第一个 Agent)
research-agent-b-2026-07-16.md   (第二个 Agent，你的文件名)
research-agent-c-2026-07-16.md   (第三个 Agent)
research-synthesis-2026-07-17.md (综合 Agent)
```

**绝对不要覆盖或编辑他人的调研文件。** 每个 Agent 只写自己的文件。这样即使所有分支最终合并，也不会有冲突。

### 给第4个综合 Agent 的说明

如果有 Agent 负责综合多家调研结果：
1. 分别 checkout 各分支，读取各自的 `research-*.md` 文件
2. 综合后写入 `research-synthesis-YYYY-MM-DD.md`
3. 所有源文件保持原样不动

## 注意

- 使用你自己的分支，不要直接提交到 `sellfox-shipping-research-agent-a`
- 你的调研方法、结论、架构可以完全不同——这正是用户想要的多样性
- 所有外部搜索保留原始 URL
- **只写你自己的文件，遵循命名约定**
