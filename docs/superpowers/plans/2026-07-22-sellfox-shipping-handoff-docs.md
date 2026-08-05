# sellfox_shipping 文档交接体系刷新 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让同事与 Agent 默认只读 `AGENT_HANDOFF.md` 即可获得全貌；修正热入口过时表述；synthesis 定点修订承运人双通道与 P1C 出口；过程日记 stamp 为冷档案。

**Architecture:** 文档-only。热状态唯一落在 HANDOFF；OKF index/log 做地图与年表；synthesis/session-progress 不全书重写——文首裁决框/stamp + §2.1 定点句。权威专题文（submit-vs-autopush、lizard-api-vs-excel、vite 决策、trackNo solutions）不动正文。

**Tech Stack:** Markdown / OKF frontmatter；验证靠 `rg` grep 自检 + `python scripts/update_index.py`；无业务代码、无 pytest 变更。

## Global Constraints

- Spec 权威：`docs/superpowers/specs/2026-07-21-sellfox-shipping-handoff-docs-design.md`（含 §2.1 / §6 审计矩阵）
- **不改业务代码**；不重跑 live submit；不新建 CURRENT.md / ARCHITECTURE.md / 模块 llms.txt
- **不全文重写** `research-synthesis` / `session-progress`；leave 列表文件改正文禁止
- 分支：`feature/sellfox-shipping-handoff-docs-20260721`（已有；勿另开）
- 中文 commit：`docs(sellfox-shipping): …`；文档-only PR
- 每次改 OKF 文档后跑 `python scripts/update_index.py`（本计划 Task 5 统一跑一次亦可）
- 现行业务口径（写入 HANDOFF/裁决框时必须一致）：
  - Excel 生产默认；API 可选；承运人双通道（非互斥）
  - 通途写销售平台；赛狐自动推送关；近期目标 = 赛狐可见 `trackNo`
  - 代码 #96/#97 已合；产品 trackNo 闭环未关；live submit 曾 401

---

## File map（改前锁定）

| 文件 | 动作 |
|------|------|
| `sellfox_shipping/AGENT_HANDOFF.md` | 重写顶部热区（七块）+ 入口/禁区 |
| `sellfox_shipping/README.md` | 「当前阶段」+ 接手链改指 HANDOFF |
| `.agents/skills/sellfox-shipping/SKILL.md` | 必读顺序 + 当前阶段 |
| `sellfox_shipping/docs/index.md` | 补链接；去掉「换 Agent 必读 session」 |
| `sellfox_shipping/docs/research/index.md` | 「接手先读」第一行 = HANDOFF |
| `sellfox_shipping/docs/reference/lizard-p0-sample-path.md` | 去掉 `p1a-rest` |
| `sellfox_shipping/docs/research/ONBOARDING.md` | 默认接手走 HANDOFF；旧分支加过时提示 |
| `sellfox_shipping/docs/research/research-synthesis-2026-07-16.md` | 文首裁决框 + §2.1 定点句 |
| `sellfox_shipping/docs/research/session-progress-2026-07-16.md` | 文首冷档案 stamp |
| `sellfox_shipping/docs/research/local-vs-sellfox-status-2026-07-17.md` | 表中一行对齐通途写平台 |
| `sellfox_shipping/docs/log.md` | 追加本日条目 |
| 根 `index.md` | `scripts/update_index.py` |

**Leave（本计划禁止改正文）：** `submit-to-platform-vs-autopush`、`lizard-api-vs-excel`、`vite-httpx-vs-karrio-decision`、solutions trackNo、`comprehensive-research`、`briefing`、早期 architecture solutions、多数 `*-2026-07-17` 专题正文。

---

### Task 1: 重写 AGENT_HANDOFF 热区

**Files:**
- Modify: `sellfox_shipping/AGENT_HANDOFF.md`
- Spec: `docs/superpowers/specs/2026-07-21-sellfox-shipping-handoff-docs-design.md` §3

**Interfaces:**
- Consumes: submit-vs-autopush、#96/#97、401 探针事实（已在现 HANDOFF 后半段）
- Produces: 热入口唯一真相；后续 Task 2–4 链接均指向本文件

- [ ] **Step 1: 替换 frontmatter `updated` 与文首入口块**

将文件开头至「## 架构」之前整段替换为（保留其后命名边界/命令/凭证可精简但勿删关键 CLI）：

```markdown
---
okf: v0.1
type: Handoff
title: sellfox_shipping — Agent 交接说明
description: 包裹中心架构、当前实现、运行方式与后续阶段边界
updated: 2026-07-22
---

# sellfox_shipping — Agent 交接说明

> **赛狐尾程打单系统** — 包裹批次工作流  
> 人读文档: [README.md](README.md)  
> **新 Agent：只读本文件即可接手。** 细节经 [docs/index.md](docs/index.md) 按需深挖。  
> 过程日记 / 规划底稿（非默认入口）：[session-progress](docs/research/session-progress-2026-07-16.md)、[research-synthesis](docs/research/research-synthesis-2026-07-16.md)

## 新对话 / 换 Agent 接手（30 秒）

1. 读完本文件（全貌七块 + 禁区 + 命令）
2. 跑验证：`uv run pytest tests/sellfox_shipping -q`
3. 需要细节时经 [docs/index.md](docs/index.md) 点进单篇

**不要**默认先读 session-progress / synthesis。

## 全貌七块

### 1. 背景 / 现行目的

Excel 本地闭环（审核 → 导出 → 人工上传物流商 → 导入对账）+ **通途写销售平台**；赛狐**自动推送关**。  
近期产品目标：验证赛狐包裹详情能否显示正确 `trackNo`（非默认推 Amazon）。

### 2. 阶段图

`P0 → P1A → P1B → P1C → P2+`  
代码主路径已合入 main（PR **#96** 集成、**#97** 文档/边界）。  
**产品** trackNo 可见性闭环**未关**（live submit 曾 401）。

### 3. 已完成

- 同步 / 审核 / 蜴国际 Excel 导出·导入 / Artifact·Batch / Intent·CAS·限流
- OIDC 启用路径就绪（**默认关**）
- 蜴国际 API 客户端 + 可选编排（**Excel 仍生产默认**）
- VITE httpx spike + 决策（不做 Karrio VITE connector）
- 边界文档：submit vs 通途/自动推送；trackNo 写路径 solutions

### 4. 波折

- live `submitToPlatform`（`P2AMA9T726848`）→ 代理 **401**；scope `UNKNOWN_BLOCKED`；赛狐 `trackNo` 未变
- **禁盲重放**；本地 `lizard-import` ≠ 赛狐 UI `trackNo`

### 5. 教训（深挖）

- [submit-to-platform-vs-autopush-2026-07-20.md](docs/research/submit-to-platform-vs-autopush-2026-07-20.md)
- [sellfox-trackno-write-path-vs-local-import.md](../docs/solutions/architecture-patterns/sellfox-trackno-write-path-vs-local-import.md)

### 6. 下一步（≤3）

1. 修赛狐写权限 / 代理 401
2. 新 `to_process` 测试包裹做 trackNo 可见性探针
3. （可选）公网打开 OIDC

### 7. 重规划裁决

- **不**整本作废 synthesis；修订 P1C 出口与承运人双通道（见 synthesis 文首裁决框）
- **承运人双通道：** `SpreadsheetCarrierAdapter` 与 `ApiCarrierAdapter` 同等级；同一承运人可两者皆有；**生产默认 Excel**；有 API 另挂可选路径（蜴国际 API 已有，不替表）
- 平台推送非本阶段默认；Intent/CLI 真调路径保留备用

## 禁区

- 不盲重放 `submitToPlatform`；真调须用户确认测试包裹
- 不把 legacy `store.py` 订单模型当生产闭环
- 不从文档/HANDOFF 拷明文 API Key
- 赛狐导入/回写前必须确认范围（默认测试商品）
```

其后保留：快速启动命令块、项目结构（可把 session-progress 注释改为「冷档案」）、命名边界、阶段细节表、数据流、凭证。  
**必须删除**任何 `feature/sellfox-shipping-p1a-rest`、`暂不提 PR`、以及「先读 session-progress」句。

- [ ] **Step 2: 自检 HANDOFF**

```powershell
rg -n "暂不提 PR|p1a-rest|先读 session|新 Agent 必读.*session" sellfox_shipping/AGENT_HANDOFF.md
```

Expected: 无匹配。

- [ ] **Step 3: Commit**

```powershell
git add sellfox_shipping/AGENT_HANDOFF.md
git commit -m "docs(sellfox-shipping): 重写 HANDOFF 热区为唯一接手入口"
```

---

### Task 2: 刷新入口卫星文件（README / skill / 两处 index / sample-path / ONBOARDING）

**Files:**
- Modify: `sellfox_shipping/README.md`
- Modify: `.agents/skills/sellfox-shipping/SKILL.md`
- Modify: `sellfox_shipping/docs/index.md`
- Modify: `sellfox_shipping/docs/research/index.md`
- Modify: `sellfox_shipping/docs/reference/lizard-p0-sample-path.md`
- Modify: `sellfox_shipping/docs/research/ONBOARDING.md`

**Interfaces:**
- Consumes: Task 1 HANDOFF 为唯一默认入口
- Produces: 所有热入口一致指向 HANDOFF

- [ ] **Step 1: README — 改「架构」链接与「当前阶段」**

`## 架构` 段改为只链 HANDOFF + docs/index（去掉 session-progress「换 Agent 交接」）：

```markdown
## 架构

详见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md) 与 [docs/index.md](docs/index.md)。
```

`## 当前阶段` 整段替换为：

```markdown
## 当前阶段

**P1A–P1C 代码主路径已合入 main（PR #96 / #97）。** Excel 本地闭环可用；Intent/CAS 默认 dry-run。  
产品缺口：赛狐可见 `trackNo`（live 曾 401）。通途写平台；自动推送关。Excel 生产默认；API 可选。

接手：只读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
```

更新 frontmatter `updated: 2026-07-22`。

- [ ] **Step 2: Skill — 必读顺序 + 当前阶段**

将「## 新对话必读」与「## 当前阶段（P1A）」替换为：

```markdown
## 新对话必读

1. `sellfox_shipping/AGENT_HANDOFF.md`（唯一默认入口）
2. 需要细节时：`sellfox_shipping/docs/index.md`

阶段口径：现行 **P0 → P1A → P1B → P1C → P2+**。legacy 订单 Web/MCP/store 勿当生产闭环。

## 当前阶段（P1C 产品缺口）

已完成：同步、审核、蜴国际 Excel、Batch/Artifact、Intent/CAS/限流、OIDC 路径（默认关）、VITE httpx 决策、蜴国际 API 可选。  
未关：公网 OIDC、成功的 live 填号（赛狐 `trackNo` 可见性）。  
Excel 仍生产默认。赛狐回写前必须用户确认范围。
```

- [ ] **Step 3: `docs/index.md` — 接手链 + 补 07-20 链接**

- frontmatter `updated: 2026-07-22`
- 「调研 / 交接」中 session-progress 行改为「过程日记（冷档案，勿当现状）」
- research-synthesis 行改为「规划底稿；先看文首裁决框，现行以 HANDOFF 为准」
- 在列表中确保有（若缺则补）：
  - `research/submit-to-platform-vs-autopush-2026-07-20.md`
  - `research/vite-httpx-vs-karrio-decision-2026-07-17.md`
  - `research/lizard-api-vs-excel-2026-07-17.md`
  - `research/pr-slice-guide-2026-07-20.md`
- AGENT_HANDOFF 行说明改为「**默认接手入口**（全貌七块）」

- [ ] **Step 4: `docs/research/index.md` — 改「当前推荐入口」表**

表第一行改为：

```markdown
| **接手继续实现**（新对话 / 换 Agent） | [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) → 细节经本 index / [docs/index.md](../index.md) |
| **读目标架构与阶段规划** | [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) — **先看文首裁决框**；现行状态以 HANDOFF 为准 |
| **过程日记（冷档案）** | [session-progress-2026-07-16.md](session-progress-2026-07-16.md) — 勿当现状 |
| **从零独立再调研**（刻意不看结论） | [ONBOARDING.md](ONBOARDING.md) → [briefing-for-independent-agent.md](briefing-for-independent-agent.md) |
```

删掉/改写 bullet 中「换 Agent 必读」session-progress 措辞；文末「会话进度文档是当前推荐的实现交接入口」改为「实现交接以 HANDOFF 为准；session-progress 为冷档案」。  
`timestamp` / 文首可改为 2026-07-22。

- [ ] **Step 5: sample-path — 去掉旧分支名**

表中「分支」行改为：

```markdown
| 分支 | 以当前工作分支为准；样例映射见 lizard-p0-column-mapping（历史曾用 `p1a-rest`，已过时） |
```

- [ ] **Step 6: ONBOARDING — 默认接手改指 HANDOFF**

文首提示块改为：

```markdown
> **若你的任务是接手继续实现（不是从零再调研）：** 不要按本文路径走。  
> **只读** [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)。  
> 本文 + 旧 research 分支名仅用于刻意独立再调研；`feature/sellfox-shipping-p1-research` 等为历史分支，可能已不存在。
```

- [ ] **Step 7: 入口卫星自检**

```powershell
rg -n "暂不提 PR|p1a-rest|当前阶段（P1A）|换 Agent 必读|先读 session" `
  sellfox_shipping/README.md `
  .agents/skills/sellfox-shipping/SKILL.md `
  sellfox_shipping/docs/index.md `
  sellfox_shipping/docs/research/index.md `
  sellfox_shipping/docs/reference/lizard-p0-sample-path.md `
  sellfox_shipping/docs/research/ONBOARDING.md
```

Expected: 无「必读 session」/「P1A 未做」类热入口匹配；`p1a-rest` 仅允许出现在「已过时」说明句中（sample-path）。

- [ ] **Step 8: Commit**

```powershell
git add sellfox_shipping/README.md .agents/skills/sellfox-shipping/SKILL.md `
  sellfox_shipping/docs/index.md sellfox_shipping/docs/research/index.md `
  sellfox_shipping/docs/reference/lizard-p0-sample-path.md `
  sellfox_shipping/docs/research/ONBOARDING.md
git commit -m "docs(sellfox-shipping): 入口文件统一指向 HANDOFF"
```

---

### Task 3: synthesis 文首裁决框 + §2.1 定点句

**Files:**
- Modify: `sellfox_shipping/docs/research/research-synthesis-2026-07-16.md`
- Spec: §2.1

**Interfaces:**
- Consumes: Global Constraints 业务口径；leave 专题文不改正文
- Produces: Agent 读摘要不再被承运人互斥 / 样例未收集 / P1C=推平台误导

- [ ] **Step 1: 替换文首引用块（约 L12–15）为裁决框**

```markdown
> **现行状态以 [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) 为准。** 本文是 2026-07-16 规划底稿，非热状态日记。
>
> **2026-07-22 裁决（读正文前先读本框）：**
> 1. **目的：** Excel 本地闭环 + 通途写销售平台；赛狐自动推送关；近期验证赛狐可见 `trackNo`。
> 2. **承运人双通道：** Spreadsheet / API 同等级；同一承运人可两者皆有；**生产默认 Excel**；蜴国际 API 已有仍不替表。
> 3. **P1C 出口修订：** 以赛狐 `trackNo` 探针（或证明不可用并记缺口）为准；**平台推送非本阶段默认**。详见 [submit-to-platform-vs-autopush-2026-07-20.md](submit-to-platform-vs-autopush-2026-07-20.md)。
> 4. **进度：** PR #96/#97 已合；live submit 曾代理 401；勿盲重放。
> 5. 过程细节见 [session-progress](session-progress-2026-07-16.md)（冷档案）。
```

- [ ] **Step 2: 改 §1 第 3 条（承运人互斥 → 双通道）**

将：

```markdown
3. 将蜴国际实现为 `SpreadsheetCarrierAdapter`，将 VITE、FedEx 等实现为 `ApiCarrierAdapter`；二者共享批次、制品、追踪号分配、审核、审计和回写能力。
```

改为：

```markdown
3. **通道与承运人解耦：** `SpreadsheetCarrierAdapter` 与 `ApiCarrierAdapter` 是同等级通道；同一承运人可两者皆有。生产默认 Excel（含蜴国际及仍依赖表的物流）；API 为可选路径（蜴国际已有客户端+可选编排；VITE 走 httpx）。二者共享批次、制品、追踪号分配、审核、审计和回写能力。
```

- [ ] **Step 3: 改 §1 样例句（L32 附近）**

将「三类真实样例尚未收集…当前最大风险」改为：

```markdown
P0 样例**已收集并映射**（见 [lizard-p0-column-mapping-2026-07-17.md](lizard-p0-column-mapping-2026-07-17.md)）；早期「列名/可解析性」风险已缓解。输入契约仍重要，但不再是未开工的硬阻断。
```

- [ ] **Step 4: §2.1「目前只有 Excel」加脚注**

在「目前只有 Excel 流程。」后追加：

```markdown
（**2026-07-16 事实**；其后蜴国际 API 已验通，见 [lizard-api-vs-excel-2026-07-17.md](lizard-api-vs-excel-2026-07-17.md)。**Excel 仍为生产默认。**）
```

同节「真实上传文件…尚未收集」句末加：`→ 已由 P0 映射文档覆盖；本句保留为当时记录。`

- [ ] **Step 5: §4.3 / §5.1 图旁加双通道注**

在方案 C 描述「Spreadsheet… / Api…」列表后加一句：

```markdown
**注（2026-07-22）：** 上表是通道类型，不是「一家承运人只能选一种」。共享批次/制品/对账/审核/审计/回写不变。
```

若 §5.1 架构图旁有「蜴国际=Spreadsheet / VITE=Api」暗示，同样加该注（或脚注链到文首裁决框）。

- [ ] **Step 6: §7.5 改「不为蜴国际开发 API」误读**

将「因此应实现公司自己的 `SpreadsheetCarrierAdapter`，不为蜴国际开发 Karrio connector。」确保语义为：

```markdown
因此应实现公司自己的 `SpreadsheetCarrierAdapter` 作为一等通道；**不为蜴国际做 Karrio connector**。公司自建 Excel 一等 + **可选** API（客户端已落地，不替代 Excel 生产默认）。
```

- [ ] **Step 7: §8 VITE spike — 钉死决策一句**

在 spike 开放决策段落后加：

```markdown
**决策已定（2026-07-17）：** 采用直接 httpx；近期不做 Karrio custom connector。见 [vite-httpx-vs-karrio-decision-2026-07-17.md](vite-httpx-vs-karrio-decision-2026-07-17.md)。
```

- [ ] **Step 8: P1C 退出门 + 附录闭环对齐裁决框**

`### P1C` 的 **退出门** 改为：

```markdown
**退出门：** 赛狐可见 `trackNo` 探针通过（或证明 `submitToPlatform` 在关自动推送下不可用并记缺口）；无盲重放；VITE 决策材料已归档（httpx）。**平台推送非本阶段默认。**
```

附录「P1 闭环」中「再逐条调用赛狐 submitToPlatform」改为注明：历史规划路径；现行以裁决框 / submit-vs-autopush 为准。  
「样例尚未收集」类附录句改为「P0 已映射」。

- [ ] **Step 9: synthesis 自检**

```powershell
rg -n "三类真实样例尚未收集|将蜴国际实现为 Spreadsheet|先读 session-progress，再读本文" `
  sellfox_shipping/docs/research/research-synthesis-2026-07-16.md
```

Expected: 「三类真实样例尚未收集」与「将蜴国际实现为 Spreadsheet，将 VITE」互斥句无匹配（或仅出现在已标注过时的历史引用中）。文首须含「现行状态以」与「双通道」或「生产默认 Excel」。

- [ ] **Step 10: Commit**

```powershell
git add sellfox_shipping/docs/research/research-synthesis-2026-07-16.md
git commit -m "docs(sellfox-shipping): synthesis 裁决框与承运人双通道定点修订"
```

---

### Task 4: session-progress stamp + local-vs-sellfox 一句

**Files:**
- Modify: `sellfox_shipping/docs/research/session-progress-2026-07-16.md`
- Modify: `sellfox_shipping/docs/research/local-vs-sellfox-status-2026-07-17.md`

**Interfaces:**
- Consumes: stamp 原则（§6）；不逐段改早期「未做」「暂不提 PR」
- Produces: 早期章节可读为历史；热入口不再误导

- [ ] **Step 1: session-progress 文首 stamp**

将 L12–13 引用块替换为：

```markdown
> **冷档案（2026-07-22）：** 本文是过程日记，**现行状态以 [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) 为准。**  
> 早期章节中的「submit/Excel/OIDC 未做」「暂不提 PR」、旧分支名等保留为**当时记录**，不要据此判断现状。  
> 目标架构底稿见 [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md)（先看文首裁决框）。
```

可选：frontmatter 加 `updated: 2026-07-22`（保留原 `timestamp: 2026-07-16`）。

- [ ] **Step 2: local-vs-sellfox 表行修正**

将：

```markdown
| 将来把追踪号写回亚马逊/平台 | **本系统**确认后调 `submitToPlatform`（未做；测试阶段禁止） |
```

改为：

```markdown
| 写回销售平台（Amazon 等） | **通途**负责；赛狐自动推送已关。本系统近期目标是赛狐可见 `trackNo`（`submitToPlatform` 为文档化填号入口，真调须确认；见 submit-vs-autopush） |
```

- [ ] **Step 3: Commit**

```powershell
git add sellfox_shipping/docs/research/session-progress-2026-07-16.md `
  sellfox_shipping/docs/research/local-vs-sellfox-status-2026-07-17.md
git commit -m "docs(sellfox-shipping): session-progress 冷档案 stamp 与写回口径对齐"
```

---

### Task 5: log + 根索引 + 全库 grep 自检

**Files:**
- Modify: `sellfox_shipping/docs/log.md`
- Modify: 根 `index.md`（经脚本）
- Verify: must-fix 热路径

- [ ] **Step 1: 在 `log.md` 顶部追加（旧「暂不提 PR」条目不改）**

```markdown
## 2026-07-22 — 文档交接体系刷新

- 热入口唯一：`AGENT_HANDOFF.md`（全貌七块）；session-progress / synthesis 降为冷档案/规划底稿
- synthesis：文首裁决框 + 承运人双通道 / P1C 出口 / 样例进度定点修订
- skill / README / 两处 index / ONBOARDING / sample-path 对齐
- Spec：`docs/superpowers/specs/2026-07-21-sellfox-shipping-handoff-docs-design.md`
```

frontmatter `updated: 2026-07-22`。

- [ ] **Step 2: 更新根索引**

```powershell
python scripts/update_index.py
```

Expected: 退出码 0；输出含更新提示。完成后在回复中写「已同步更新根目录索引」。

- [ ] **Step 3: 全库 must-fix grep（热路径）**

```powershell
rg -n "暂不提 PR" sellfox_shipping/AGENT_HANDOFF.md sellfox_shipping/README.md .agents/skills/sellfox-shipping/SKILL.md
rg -n "p1a-rest" sellfox_shipping/AGENT_HANDOFF.md sellfox_shipping/README.md .agents/skills/sellfox-shipping/SKILL.md sellfox_shipping/docs/index.md sellfox_shipping/docs/research/index.md sellfox_shipping/docs/reference/lizard-p0-sample-path.md
rg -n "当前阶段（P1A）" .agents/skills/sellfox-shipping/SKILL.md
rg -n "三类真实样例尚未收集" sellfox_shipping/docs/research/research-synthesis-2026-07-16.md
rg -n "将蜴国际实现为 Spreadsheet" sellfox_shipping/docs/research/research-synthesis-2026-07-16.md
rg -n "换 Agent 必读|新 Agent 必读.*session|接手继续实现.*session-progress" sellfox_shipping/AGENT_HANDOFF.md sellfox_shipping/docs/index.md sellfox_shipping/docs/research/index.md .agents/skills/sellfox-shipping/SKILL.md
```

Expected:
- 热入口文件对「暂不提 PR」「当前阶段（P1A）」「三类真实样例尚未收集」「将蜴国际实现为 Spreadsheet」→ **零命中**
- `p1a-rest` → 热入口零命中；sample-path 仅允许「已过时」句
- session-progress / log **允许**保留历史「暂不提 PR」（stamp 原则）

- [ ] **Step 4: Commit**

```powershell
git add sellfox_shipping/docs/log.md index.md
git commit -m "docs(sellfox-shipping): 交接刷新记入 log 并同步根索引"
```

- [ ] **Step 5: 准备文档-only PR（执行阶段末尾；需用户确认再 push）**

```powershell
git push -u origin HEAD
gh pr create --title "docs(sellfox-shipping): 交接体系刷新 — HANDOFF 唯一热入口" --body "## Summary
- 重写 AGENT_HANDOFF 全貌七块；入口卫星统一指向 HANDOFF
- synthesis 文首裁决框 + 承运人双通道 / P1C / 样例定点修订
- session-progress 冷档案 stamp；log + 根索引同步

## Test plan
- [ ] 仅读 HANDOFF 可答目的/完成度/缺口/禁区/下一步/双通道
- [ ] Task 5 grep 自检全绿（热路径）
- [ ] leave 列表专题文无正文误改
"
```

---

## Self-review（写计划后核对）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| HANDOFF 热区七块 | Task 1 |
| README / skill / 两 index / sample-path / ONBOARDING | Task 2 |
| synthesis 文首 + §2.1 定点 | Task 3 |
| session stamp + local-vs-sellfox | Task 4 |
| log + update_index + grep + PR | Task 5 |
| leave 列表不改正文 | Global Constraints + File map |
| 不改业务代码 / 不重写全书 | Global Constraints |

Placeholder scan: 无 TBD/TODO；各 Step 含具体替换文案与命令。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-sellfox-shipping-handoff-docs.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — 每 Task 派一个新 subagent，Task 间人工过目  
2. **Inline Execution** — 本会话用 executing-plans 连续改，按 Task 设检查点  

**Which approach?**
