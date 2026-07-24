# sellfox_shipping — 文档交接体系刷新（OKF + HANDOFF）

## Context

`sellfox_shipping` 已有 OKF bundle（`docs/index.md` / `log.md` / `research/*`）、`AGENT_HANDOFF.md`、长篇 `session-progress` / `research-synthesis`，以及 `docs/solutions/` 中的 trackNo 固化文。PR #96 / #97 已合入 main。

问题不是「没有文档」，而是**热状态分散且入口过时**：真相在 session-progress §34–§36、`submit-to-platform-vs-autopush`、solutions trackNo 文；HANDOFF / README / `docs/index` 仍残留错误分支、`暂不提 PR`、P1A-only 表述；synthesis 仍以「submit E2E 推平台」为 P1C 出口，且把「一家承运人 = 一种适配器」写死。

2026-07 外部实践与团队 2026-06 决定一致：**保持 OKF + HANDOFF，不另建 CURRENT.md**。

**目标：** 同事与 Agent 默认只读 `AGENT_HANDOFF.md` 即可获得全貌；细节经 OKF index 按需深挖。

**非目标：** 改业务代码；重跑 live submit；全文重写 synthesis / session-progress；新建 CURRENT.md / ARCHITECTURE.md / 模块 llms.txt。

---

## §1 文档分层与接手协议

### 四层（热 → 冷）

| 层 | 文件 | 职责 |
|----|------|------|
| 热状态（唯一） | `sellfox_shipping/AGENT_HANDOFF.md` | 全貌七块 + 禁区 + 验证命令 + 精简结构/凭证 |
| 地图 | `docs/index.md`、`docs/research/index.md` | 导航 + 一行说明；不写长叙事 |
| 年表 | `docs/log.md` | 按日追加；接手只看最近 1–2 条 |
| 冷知识 | `docs/research/*`、`docs/solutions/*`、根 `CONCEPTS.md` | 按需；不再标为「新 Agent 必读」默认入口 |

### 默认接手路径

1. 只读 `AGENT_HANDOFF.md`
2. `uv run pytest tests/sellfox_shipping -q`
3. 需要细节时经 `docs/index.md` 点进单篇

### 明确不做

- 不新建 `CURRENT.md` / `STATUS.md`
- 不把 `session-progress` / `research-synthesis` 继续当作默认必读（降为冷档案 / 规划底稿）

---

## §2 文件改动清单

| 文件 | 动作 | 程度 |
|------|------|------|
| `AGENT_HANDOFF.md` | 重写顶部热区 | 必改：删错误分支/`暂不提 PR`；加全貌七块；入口改为「只读本文件」 |
| `README.md` | 刷新「当前阶段」与链接 | 接手指向 HANDOFF |
| `docs/index.md` | 补全链接 + 分组 | 含 solutions trackNo、07-20 决策文 |
| `docs/research/index.md` | 改「接手先读」表 | 第一行 HANDOFF；长文标深挖 |
| `docs/log.md` | 追加一条 | 本次文档交接刷新 |
| `research-synthesis-2026-07-16.md` | 文首裁决框 + **定点修订**（见 §2.1） | 不重写全书 |
| `session-progress-2026-07-16.md` | 文首冷档案声明 + frontmatter 日期 | 不重写早期 §；可选在 §1 表加「见文首/HANDOFF」 |
| `local-vs-sellfox-status-2026-07-17.md` | 定点一句 | 「将来写回亚马逊 = 本系统 submit」→ 对齐通途写平台 / 填号目标 |
| `.agents/skills/sellfox-shipping/SKILL.md` | 必读顺序 + 当前阶段 | HANDOFF 优先 |
| `docs/reference/lizard-p0-sample-path.md` | 一行 | 去掉过时分支名 |
| `ONBOARDING.md` | 轻触 | 标明仅独立再调研；默认接手走 HANDOFF；旧分支名加过时提示 |
| 根 `index.md` | `scripts/update_index.py` | 索引联动 |

**默认不改正文（仅依赖入口降级）：** `comprehensive-research-2026-07-15.md`、`briefing-for-independent-agent.md`、早期 solutions `sellfox-shipping-research-and-architecture.md`、已正确的 `lizard-api-vs-excel` / `vite-httpx-vs-karrio-decision` / `submit-to-platform-vs-autopush` / solutions trackNo 文。

### §2.1 synthesis 定点修订（相对「只加文首」的增量）

文首短框仍写：现行目的、通途/自动推送、P1C 出口修订、#96/#97、401、链 HANDOFF。

**必须改正文关键句（否则 Agent 读摘要仍被误导）：**

| 位置 | 现行问题 | 改为 |
|------|----------|------|
| §1 第 3 条 | 蜴国际=Spreadsheet；VITE/FedEx=Api（互斥） | **通道与承运人解耦**：`SpreadsheetCarrierAdapter` 与 `ApiCarrierAdapter` 是同等级通道；同一承运人可两者皆有。**生产默认 Excel**（含蜴国际及仍依赖表的物流）；API 为可选路径（蜴国际已有客户端+可选编排；VITE 走 httpx） |
| §1 / 附录「样例尚未收集」 | 与 §10 P0 进度矛盾 | 摘要改为「P0 样例已收集并映射，见 lizard-p0-column-mapping；细节风险降为已缓解」 |
| §2.1「目前只有 Excel」 | 历史事实，但无后续修订 | 保留为 2026-07-16 事实 + 脚注：**其后**蜴国际 API 已验；Excel 仍生产默认 |
| §4.3 / §5.1 | 图旁暗示一对一绑定 | 注明双通道；共享批次/制品/对账/审核/审计/回写不变 |
| §7.5 | 「不为蜴国际开发 API / 只做 Spreadsheet」易读成禁止 API | 改为：不为蜴国际做 **Karrio** connector；公司自建 Excel 一等 + **可选** API（已落地客户端，不替 Excel） |
| §8 / 结论 VITE spike 开放决策 | 决策已定 httpx | 加一句：决策见 `vite-httpx-vs-karrio-decision-2026-07-17.md`（采用 httpx，近期不做 Karrio custom） |
| P1C 退出门 / 附录闭环 | submit 推平台 E2E | 与裁决框一致：赛狐可见 trackNo 探针（或证明不可用并记缺口）；平台推送非本阶段默认 |

---

## §3 HANDOFF 热区内容（全貌七块）

1. **背景 / 现行目的**：Excel 本地闭环 + 通途写平台；自动推送关；近期验证赛狐可见 `trackNo`。
2. **阶段图**：P0→P1A→P1B→P1C→P2+；代码 #96 已合；产品 trackNo 闭环未关。
3. **已完成**：同步/审核/Excel/Batch/Intent·CAS·限流、OIDC 默认关、蜥蜴 API 可选等。
4. **波折**：submit 代理 401；禁盲重放；本地 import ≠ UI trackNo。
5. **教训** → solutions trackNo 文 + submit-vs-autopush。
6. **下一步 ≤3**：修写权限 → 新 to_process 探针 →（可选）公网 OIDC。
7. **重规划裁决**：不整本作废 synthesis；修订 P1C 出口；Excel 默认；承运人双通道（见 §2.1）。

其后：禁区、命令、结构、凭证。目标约 ≤200 行可扫读。

---

## §6 过时表述审计矩阵（2026-07-22）

原则：**热入口与会误导入手的摘要句 → must-fix**；过程日记早期章节 → **stamp（文首声明）**；已被更新专题文覆盖的历史调研 → **leave**。

### must-fix（实现时必改）

| 路径 | 问题摘要 | 类别 |
|------|----------|------|
| `AGENT_HANDOFF.md` | 分支 `p1a-rest`、`暂不提 PR`、先读 session+synthesis | D 入口/阶段 |
| `README.md` | 「当前阶段」仍像 P1A-only；交接链 session-progress | D |
| `docs/index.md` | 缺 07-20 / 多数 07-17；updated 旧 | D 地图 |
| `docs/research/index.md` | 「接手先读」仍 session→synthesis→HANDOFF | G 入口 |
| `.agents/skills/sellfox-shipping/SKILL.md` | 必读 session+synthesis；「当前阶段（P1A）」；OIDC/Excel/submit「未做」 | D/F |
| `research-synthesis-…` §1 第3条、样例句、§7.5、P1C/附录闭环 | 承运人互斥；样例未收集；P1C=推平台 | A/C/B |
| `local-vs-sellfox-status-…` 表「将来写回亚马逊=本系统 submit」 | 与通途写平台/填号目标冲突 | B |
| `docs/reference/lizard-p0-sample-path.md` | 仍写 `p1a-rest` | D |
| `ONBOARDING.md` | 旧 research 分支；易被当成默认接手 | G |

### stamp-historical（文首/脚注即可，不重写全书）

| 路径 | 处理 |
|------|------|
| `session-progress-…` | 文首：「冷档案；现行以 HANDOFF 为准」。早期 §1「submit/Excel/OIDC 未做」、§15「暂不提 PR」保留为当时记录，不逐段改写 |
| `research-synthesis` 附录 A「2026-07-16 只有 Excel」 | 保留历史 + 脚注 API 已出现 |
| `pr-slice-guide` 中的长分支名 | 历史 PR 指南；可加一行「#96 已合」 |
| `log.md` 旧「暂不提 PR」条目 | 年表，不改历史日 |

### leave（已正确或纯档案）

| 路径 | 理由 |
|------|------|
| `submit-to-platform-vs-autopush-2026-07-20.md` | 现行边界权威 |
| `lizard-api-vs-excel-2026-07-17.md` | 已写 Excel 默认 + API 可选 |
| `vite-httpx-vs-karrio-decision-2026-07-17.md` | VITE 决策已钉死 |
| `docs/solutions/.../sellfox-trackno-write-path-vs-local-import.md` | 现行教训 |
| `comprehensive-research-2026-07-15.md`、`briefing-…` | 独立再调研档案；index 标明勿当现状 |
| `docs/solutions/.../sellfox-shipping-research-and-architecture.md` | 早期 compound；勿当现状 |
| 多数 `*-2026-07-17.md` 专题（carton、pnumber、artifact、async…） | 专题事实仍有效 |

### 承运人双通道（回答「旧讨论要不要更新」）

- **仍有效：** Excel 与 API 同等级；共享批次/制品/对账/审核/审计/回写；不为人工 Excel 硬套 Karrio Custom Carrier。
- **过时：** 「蜴国际=仅 Spreadsheet；VITE/FedEx=仅 Api」的**互斥绑定**。
- **现行：** 物流（含蜴国际）**保留 Excel**；有 API 的另挂 `ApiCarrierAdapter` 路径；生产默认 Excel，直至业务明确切流。

---

## §4 维护仪式

每次可交付切片：① 更新 HANDOFF `updated:` + 七块关键项；② `log.md` 追加；③ 规划假设变则改 synthesis 裁决框或新 research。  
禁止只写 session-progress 末节不回写 HANDOFF。

---

## §5 范围外

- 不改业务代码；不重跑 live submit  
- 不全文重写 synthesis / session-progress  
- 不新建 CURRENT.md / ARCHITECTURE.md / 模块 llms.txt  
- 不镜像模块状态进根 AGENTS.md（可选一行指针除外）

---

## 成功标准

- 仅读 HANDOFF 即可答：目的、完成度、缺口、禁区、下一步、重规划裁决、承运人双通道。
- 入口文件无「暂不提 PR」、错误功能分支、skill「P1A 未做 Excel」。
- synthesis 文首 + §1/§7.5/P1C 与双通道及 07-20 业务一致。
- 过时日记有 stamp；权威专题文未被错误「刷新」覆盖。

---

## 实现顺序（交给 writing-plans）

1. 重写 `AGENT_HANDOFF.md` 热区  
2. README、skill、两处 index、sample-path、ONBOARDING 轻触  
3. synthesis：文首框 + §2.1 定点句  
4. session-progress 文首 stamp；`local-vs-sellfox-status` 一句  
5. `log.md` + `scripts/update_index.py`  
6. 自检 grep：`暂不提 PR`、`p1a-rest`、`当前阶段（P1A）`、`三类真实样例尚未收集`、`将蜴国际实现为 Spreadsheet`  
7. 提交 → PR（文档-only）

---

## 参考

- 模块锚点：PR #96/#97、`submit-to-platform-vs-autopush`、`lizard-api-vs-excel`、`vite-httpx-vs-karrio-decision`、solutions trackNo  
- OKF：`.claude/skills/okf/SKILL.md`；[OKF SPEC](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
