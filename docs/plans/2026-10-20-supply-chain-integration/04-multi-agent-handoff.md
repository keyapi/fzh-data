---
okf: v0.1
type: Handoff
title: 供应链整合 — 独立并行调研约定（Claude / Codex / Cursor 各做一遍）
description: 不分工、不共享中间结论：每个工具独立用子 Agent 穷尽调研（先搜再造、把湖煮干），各自独立分支与 PR；全部完成后做共识/分歧对比
date: 2026-10-20
---

# 04 — 独立并行调研约定

> **本节是用户 2026-10-20 的明确要求，优先于任何「分工」建议。**
>
> - **不按工具拆调研线**（不采用 Claude=A / Codex=B / Cursor=C 的分工）。
> - **Claude / Codex / Cursor 各自独立完成同一份调研**，各自用子 Agent 并行，各自独立分支、独立 PR。
> - 目的：**穷尽调研 + 交叉验证**，避免单一模型/单一信息源的偏差；**先搜再造，避免重复造轮子**。
> - 三家在调研期间**互不共享中间结论**（避免锚定），完成后再对比。

## 1. 每家都要做的三阶段搜索

### 阶段 0：搜项目内（必须先做）

不要一上来就上网。先把仓库里**已有的**答案找干净，包括：

1. `main` 上的代码与文档；
2. **所有本地/远程分支**（`git fetch --all`）；
3. **所有 open PR + closed 未合并 PR**（`gh pr list`，见 01 §5.5）；
4. 仓库外但属于公司的资料：钉钉表、Notion、Google Sheet、Colab、WorkBuddy（向用户要位置）；
5. 历史对话/交接文档（`docs/handoffs/`、`docs/plans/`、`docs/solutions/`、各模块 `AGENT_HANDOFF.md`）。

输出：`01-existing-assets.md` —— 逐项写「路径/分支/PR + 能复用什么 + 局限」。
**找不到也要写「找不到」，并给出检索命令与范围**（否定结论必须可复核）。

### 阶段 1：搜网上（穷尽）

三类信息都要覆盖，不能只看一类：

| 类别 | 要回答 |
|---|---|
| **业界实践** | S&OP/IBP、DDMRP、MEIO、MRP/APS、控制塔、预测治理、资金约束补货 |
| **AI/Agent SOTA** | 时序基础模型、LLM 做预测的边界、agentic 架构、MCP、LLM+OR、HITL、评测与护栏 |
| **开源方案** | 编排、存储/变换、BI、预测库、优化库、ERP/计划、Agent 框架；License、活跃度、TCO |

每个结论必须有：**URL + 访问日期 + 证据强度（强/中/弱）**；厂商宣传单独标注。

### 阶段 2：再自己造（只在确认没有现成方案后）

- 先写「为什么现成方案不够」；
- 再做 1~3 天能完成的最小验证（装库、跑样例、对比基线）；
- 不要在调研阶段写业务代码。

## 2. 每个工具的产出（独立目录，互不冲突）

分支：`research/supply-chain-<tool>`（`claude` / `codex` / `cursor`）

```text
docs/research/supply-chain/2026-10-20/<tool>/
├── 00-plan.md                 # 先规划：问题分解、子 Agent 分工、时间盒、验收清单
├── 01-existing-assets.md      # 项目内（含全部分支与 PR）
├── 02-industry-practices.md   # 业界实践
├── 03-ai-agent-sota.md        # AI / Agent
├── 04-open-source.md          # 开源方案 + 最小验证结果
├── 05-synthesis.md            # 候选架构 3 个 + 推荐 + 不选理由 + 成本
├── 06-open-questions.md       # 需要用户/老板拍板的问题
├── sources.md                 # 全部来源（URL/日期/关键句/强度）
└── log.md                     # 过程记录（含失败与放弃的方向）
```

> **同一个工具内部**可以用子 Agent 并行（按 02/03/04 三条线），但 `05-synthesis.md`
> 必须由主 Agent 自己写，不能把综合交给子 Agent。
> **跨工具**不要共用文件；三家各自写自己的目录。

## 3. 文件所有权与提交规则

- 每个工具只写自己的 `docs/research/supply-chain/2026-10-20/<tool>/`；
- 交接包（本目录 00–04）**只读**，发现问题写进自己的 `06-open-questions.md`；
- 独立分支、独立 PR；**不要等别人**，也不要基于别人的研究分支；
- 提交前：
  ```bash
  uv run python scripts/check_secrets.py
  uv run python scripts/update_index.py
  ```
- 不写客户名、员工名、邮箱、IP、凭证；价格/成本按已有脱敏口径。

## 4. 「把湖煮干」的覆盖清单

每份调研必须逐项打勾（写进 `00-plan.md`，完成情况写进 `05-synthesis.md`）：

- [ ] 项目内：main / 全部分支 / 全部 open PR / closed 未合并 PR / 模块 HANDOFF / docs/solutions
- [ ] 项目外：钉钉表、Notion、GSheet、Colab、WorkBuddy（能拿到的都看）
- [ ] 业界：S&OP、DDMRP、MEIO、MRP/APS、控制塔、预测治理、资金约束
- [ ] AI：时序基础模型、LLM 边界、Agent 架构、MCP、LLM+OR、HITL、评测/护栏
- [ ] 开源：每一层至少 2 个候选，含 License/活跃度/TCO/国内可达性
- [ ] 反例：至少 1 个「业界这么做但我们不该抄」、1 个「AI 不该做」
- [ ] 最小验证：至少跑通 1 个预测库或 1 个编排/看板样例
- [ ] 成本：自建 vs 采购 vs 开源的年度成本区间
- [ ] 未匹配/未找到：单列，不静默丢弃

## 5. 三家完成后的对比（另开一次会话做）

等三个 PR 都完成后，再做一次**对比会话**（不写新调研，只做合并）：

1. 三方各自列出「结论 + 证据来源」；
2. **只保留三方都能在来源里找到的共识**；
3. 分歧点单列，回到一手来源裁决 —— **不投票、不看谁说得响**；
4. 输出 `docs/research/supply-chain/2026-10-20/00-comparison.md`：
   - 共识；
   - 分歧与裁决依据；
   - 三方都遗漏的问题；
   - 推荐架构与下一步。

> 这一步的目的不是选出「哪个模型更聪明」，而是**用冗余降低漏项和偏差**。

## 6. 可直接复制的开场提示词（三家通用）

```text
项目：供应链整合决策系统（销售分析 → 需求预测 → 库存/下单/生产/出库/头程在途 →
下单建议 → 排产建议 → 老板审批）。

第一步：只做规划，不写业务代码。
请先读：
  docs/plans/2026-10-20-supply-chain-integration/ 下全部文件（index 起）
  （若 main 上没有，先 `git fetch --all`，读 origin/docs/supply-chain-integration-handoff 分支）
然后产出你的 `docs/research/supply-chain/2026-10-20/<你的工具名>/00-plan.md`：
  - 问题分解
  - 子 Agent 分工（若有）
  - 时间盒与验收清单
  - 你打算检索的项目内范围（main / 全部分支 / 全部 PR / 文档 / 外部资料）
规划写完后先发给我确认，再开始调研。

调研要求（确认后执行）：
1. 先搜项目内：main、所有分支、所有 open PR、closed 未合并 PR、模块 HANDOFF、
   docs/solutions、docs/research；找不到要写「找不到 + 检索命令」。
2. 再搜网上：业界实践 + AI/Agent SOTA + 开源方案，每条结论带 URL/日期/证据强度。
3. 最后才考虑自己造：先写清「为什么现成方案不够」，再做 1~3 天的最小验证。
4. 不得只依赖单一来源；厂商宣传与独立证据分开。
5. 输出到 docs/research/supply-chain/2026-10-20/<你的工具名>/（00–06 + sources + log）。
6. 独立分支 research/supply-chain-<tool>，独立 PR；不要改别人的文件，不要等别人。
7. 不写客户名/员工名/邮箱/IP/凭证；价格按脱敏口径。
```

## 7. 反模式

1. **三家分工**（本项目明确不做）—— 会漏掉交叉验证。
2. **调研期间共享中间结论** —— 会互相锚定，失去独立性。
3. **只看 main** —— 最相关的成果在未合并分支/PR。
4. **只看主分支的 open PR** —— closed 未合并的 PR 里也有可复用内容。
5. **先选框架再找证据**。
6. **把厂商 benchmark 当独立结论**。
7. **用 LLM 直接生成预测数字并当事实**。
8. **静默丢弃未匹配/未找到**。

## 8. 每家完成定义（DoD）

- [ ] `00-plan.md` 经用户确认；
- [ ] `01-existing-assets.md` 覆盖 main + 全部分支 + open/closed PR，附检索命令；
- [ ] `02/03/04` 三份调研均有来源表与证据强度；
- [ ] `04` 至少 1 个最小验证实际跑通；
- [ ] `05-synthesis.md` 给出 3 个候选架构 + 推荐 + 成本 + 风险；
- [ ] `06-open-questions.md` 列出需要拍板的问题；
- [ ] 独立 PR 已开，通过凭证扫描；
- [ ] `sources.md` 可直接复核。
