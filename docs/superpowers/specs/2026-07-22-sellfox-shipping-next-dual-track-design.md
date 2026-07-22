# sellfox_shipping — 下一阶段双轨规划（框架对照 + 规则引擎调研开局）

## Context

交接文档体系已由 PR #96–#98 合入：`AGENT_HANDOFF.md` 为唯一热入口；承运人双通道与 P1C 出口裁决已写入 synthesis 文首。

**现状判断：**

- **文档/代码骨架：** 阶段性可用（同步、审核、Excel 批次、Intent/CAS dry-run、蜴 API 可选、VITE httpx 决策等）。
- **产品门 trackNo：** 赛狐客服口径下，Amazon 订单经 API 填号仍走 `submitToPlatform`；该 API **不解耦**「写入赛狐」与「推销售平台」。通途仍写平台时真测成本高。**本阶段明确不做** live 写回探针（含网页自动化备选）。
- **框架实情：** 大量能力仍是「已实现待验」或「仅骨架」；下一主线是对照表 + 实现/验证打磨，不是关 trackNo。
- **同事并行：** 需要全貌交接 + 以 CENTRADE/DANEEY 2026-04–06 实绩为底座的**美国尾程规则引擎**调研开局（先事实与规则落地推演，本切片不写引擎代码）。

**目标：** 一份双章设计契约——① 你侧框架对照与下一刀排序；② 同事侧全貌话术 + 规则引擎调研开局；分头执行，事后用 HANDOFF / log / solutions 统一汇总。

**非目标：** 本设计落地阶段不要求 live `submitToPlatform`、不实现规则引擎、不新建第二热入口（无 `CURRENT.md` / `roadmap-status.md`）、不重写 synthesis 全书。

---

## §1 章① — 框架对照与下一刀排序（主线）

### 1.1 对照表

实现时落盘为 `sellfox_shipping/docs/research/framework-gap-2026-07-22.md`（或同日命名），并在 HANDOFF「下一步」用 ≤3 条摘要回写。Spec 定列与初判：

| 列 | 含义 |
|----|------|
| 规划项 | 来自 synthesis 阶段 / HANDOFF 七块 |
| 状态 | **已关** / **已实现待验** / **仅骨架** / **延期** |
| 证据 | PR、测试、文档链接 |
| 缺口一句话 | 还差什么才算「验过」 |

**初判（实现时可微调，不得无证据改成「已关」）：**

| 规划项 | 状态 |
|--------|------|
| P0 样例与列映射 | 已关（mapping 文；① 赛狐导出可后补） |
| P1A 同步/审核/列表 | 已实现待验 |
| P1B Excel 导出·导入·Batch/Artifact | 已实现待验 |
| P1C Intent/CAS/限流/dry-run | 已实现待验 |
| VITE httpx 决策 | 已关；**生产编排挂载** = 仅骨架 |
| 蜴国际 API 可选 | 客户端+编排有；UI/CLI 与 Excel 同等等级挂载 = 待验/骨架 |
| OIDC | 路径就绪、默认关 = 仅骨架（公网开 = 可选/延期） |
| trackNo / submitToPlatform 真探针 | **延期** |
| 承运人选择规则引擎 | 不在章①实现范围 → 章② |

### 1.2 trackNo 认知备忘（延期，非下一刀）

- 文档化 API 入口仍是 `submitToPlatform`；不解耦填号 vs 推平台。
- 可测备选（**本阶段不执行**）：预留赛狐未发货单 + 通途真实运单号上传。
- 网页自动化「不推 Amazon」选项：记作备选，不通途切走前难测。
- 权威边界文：`submit-to-platform-vs-autopush-2026-07-20.md`、solutions trackNo 文。HANDOFF 下一步**不再**把「修 401 → 立刻探针」列为默认第一刀。

### 1.3 建议下一刀排序

1. 对照表落盘 + 改 HANDOFF「下一步」（框架打磨优先）。  
2. 从「已实现待验」开 **Excel 闭环回归清单**（真实/半真实样例；**不写**赛狐 trackNo）。  
3. 表中列出双通道挂载缺口（蜴 API / VITE 编排）；不强制本轮实现。  
4. trackNo：仅认知 + 可测协议备忘；真测须你另行点头。

### 1.4 章①明确不做

live submit、网页自动化上传、规则引擎实现、新建第二热入口。

---

## §2 章② — 同事全貌交接 + 规则引擎调研开局

### 2.1 全貌交接话术（复制即用）

1. 只读 `sellfox_shipping/AGENT_HANDOFF.md`  
2. 细节 → `sellfox_shipping/docs/index.md`  
3. 一句现状：网页 + 赛狐 API 拉包裹；承运人 **Excel 默认 / API 可选**；通途写销售平台；trackNo 真写赛狐本阶段不测；规则引擎未实现，先做事实调研  

**展现形式提纲：**

| 问题 | 现行答案 |
|------|----------|
| UI | FastAPI/Jinja 网页 + Typer JSON CLI |
| 包裹来源 | 赛狐订单处理 API → 本地 SQLite（非通途主路径） |
| 承运人 | 双通道 Spreadsheet / API；生产默认 Excel |
| 蜴 / VITE / GLS | 蜴 Excel 主 + API 可选；VITE 决策 httpx（编排挂载未齐）；波兰自发货主要 GLS |
| 平台运单 | 通途写平台；赛狐自动推送关；`submitToPlatform` 不解耦，真测延期 |

### 2.2 规则引擎调研切片

| 要 | 不要 |
|----|------|
| ERPNext/通途 **2026-04–06**，仓 **CENTRADE / DANEEY**，已发货 | 本切片不实现规则引擎代码 |
| 发货仓、地址、邮编、重尺（订单子表/包裹尺寸）、实际承运商/产品 | 不改赛狐生产；不写 trackNo |
| 尾程同事已有规则 vs 实绩差异；产出 research + 可机器化规则假设清单 | 波兰非主战场（仅注明 GLS） |
| 与另一同事：先对齐双方已有摘要/聊天结论再推演 | 无本仓上下文的空聊当结论 |

**分支建议：** `research/<name>-carrier-rules-centrade-daneey-20260406`（或同事自定 `research/…`）；文档-only PR 优先。

**回写：** HANDOFF「已完成/下一步」相关一句 + `docs/log.md` +（可复用）`docs/solutions/`；research 挂 `docs/index.md` / `docs/research/index.md`。

### 2.3 引擎目标（调研要服务的终局，本切片只到假设清单）

面向**美国**尾程：输入订单/仓/地址/邮编/重尺 → 对照历史实绩与既有人工规则 → 将来自动建议「哪家承运商 + 什么产品/服务」以优化成本与时效。本切片只产出事实与规则假设，不写推荐服务。

---

## §3 统一汇总、范围外、成功标准

### 3.1 分头后统一汇总（热入口仍唯一）

不新建常青 roadmap 文件。每次可交付切片结束：

1. 更新 `AGENT_HANDOFF.md`：`updated:` + 七块中「已完成 / 下一步 / 阻塞」  
2. `sellfox_shipping/docs/log.md` 追加  
3. 可复用教训 → `docs/solutions/`（ce-compound 规范）  
4. 两章合并检查：对照表勾选是否更新；章② research 是否挂 index；HANDOFF 是否至少改过一次  

### 3.2 范围外

- 不执行 trackNo live 探针 / 不修 401 作为本设计必达  
- 不实现规则引擎服务或 UI  
- 不新建 `CURRENT.md` / `roadmap-status.md` / 模块 llms.txt  
- 不把同事聊天记录无审校地当仓库真相  

### 3.3 成功标准

- 只读 HANDOFF 可知：框架打磨优先、trackNo 延期、规则引擎未做但有调研开局指引。  
- 存在一篇 framework-gap 对照表，状态有证据列。  
- 同事 Agent 凭 §2.1 话术能答展现形式提纲，并能在独立分支开 CENTRADE/DANEEY 调研。  
- 分头结束后可用 §3.1 清单完成一次汇总，无第二热入口漂移。  

---

## 实现顺序（交给 writing-plans）

1. 新建 `framework-gap-2026-07-22.md` + 更新两处 index  
2. 改 HANDOFF「下一步」与 trackNo 延期一句；`log.md` 追加  
3. 章②：交接话术可放进 HANDOFF 短链或 `docs/research/` 一页「规则引擎调研开局」；挂 index  
4. （可选）synthesis 文首裁决框补一行「trackNo 真测延期；下一主线框架对照」  
5. 提交 → PR（文档-only）  

---

## 参考

- `sellfox_shipping/AGENT_HANDOFF.md`  
- `docs/superpowers/specs/2026-07-21-sellfox-shipping-handoff-docs-design.md`  
- `submit-to-platform-vs-autopush-2026-07-20.md`、solutions trackNo 文  
- `research-synthesis-2026-07-16.md`（文首裁决框）  
