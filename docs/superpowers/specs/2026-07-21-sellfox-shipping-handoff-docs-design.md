# sellfox_shipping — 文档交接体系刷新（OKF + HANDOFF）

## Context

`sellfox_shipping` 已有 OKF bundle（`docs/index.md` / `log.md` / `research/*`）、`AGENT_HANDOFF.md`、长篇 `session-progress` / `research-synthesis`，以及 `docs/solutions/` 中的 trackNo 固化文。PR #96 / #97 已合入 main。

问题不是「没有文档」，而是**热状态分散且入口过时**：真相在 session-progress §34–§36、`submit-to-platform-vs-autopush`、solutions trackNo 文；HANDOFF / README / `docs/index` 仍残留错误分支、`暂不提 PR`、P1A-only 表述；synthesis 仍以「submit E2E 推平台」为 P1C 出口，缺少显式「是否重规划」裁决。

2026-07 外部实践（OKF v0.1 Draft、AGENTS.md 分层、Compound Engineering）与团队 2026-06 决定一致：**保持 OKF + HANDOFF，不另建 CURRENT.md**。风险是「多个热叙事」，不是缺第四个状态文件。

**目标：** 同事与 Agent 默认只读 `AGENT_HANDOFF.md` 即可获得全貌（背景、目的、规划判断、完成度、波折、教训链、下一步、是否重规划）；细节经 OKF index 按需深挖。

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
| `AGENT_HANDOFF.md` | 重写顶部热区 | 必改：删错误分支/`暂不提 PR`；加全貌七块；入口改为「只读本文件」；稳定命令区可保留并去陈旧表述 |
| `README.md` | 刷新「当前阶段」与链接 | 与 HANDOFF 对齐一句完成度；接手指向 HANDOFF |
| `docs/index.md` | 补全链接 + 分组 | 热入口 / 决策与边界 / 承运人专题 / 过程档案；链 solutions trackNo |
| `docs/research/index.md` | 改「接手先读」表 | 第一行 HANDOFF；session-progress / synthesis 标为深挖 |
| `docs/log.md` | 追加一条 | 记录本次文档交接刷新 |
| `docs/research/research-synthesis-2026-07-16.md` | 不重写全书 | 文首加「2026-07-21 现行口径 / 重规划裁决」短框 |
| `docs/research/session-progress-2026-07-16.md` | 轻触 | 文首「冷档案；以 HANDOFF 为准」；更新 frontmatter 日期反映末节；不重写早期章节全文 |
| `.agents/skills/sellfox-shipping/SKILL.md` | 改必读顺序 + 当前阶段 | HANDOFF 优先；对齐 #96/#97 / 401 |
| `docs/reference/lizard-p0-sample-path.md` | 一行修正 | 去掉过时分支名 |
| 根 `index.md` | 跑 `scripts/update_index.py` | OKF 索引联动 |

**可选（默认不做）：** 根 `AGENTS.md` 加一行「模块状态以各模块 HANDOFF 为准」——仅当实现时仍发现根索引误导再开。

---

## §3 HANDOFF 热区内容（全貌七块）

顶部固定顺序：

1. **背景 / 现行目的**（5–10 行）：生产默认 Excel 本地闭环 + 通途写销售平台；赛狐自动推送关闭；近期产品目标是验证赛狐包裹详情可见正确 `trackNo`，暂不要求本系统推 Amazon。
2. **阶段图**：P0 → P1A → P1B → P1C → P2+；标明代码主线已合 PR #96；产品闭环（赛狐 UI trackNo）未关。
3. **已完成**（带日期要点）：包裹同步/审核、蜥蜴 Excel 导出导入与 Batch/Artifact、Intent/CAS/限流/回读骨架、OIDC 路径（默认关）、蜥蜴 API 客户端与可选编排（Excel 仍默认）等。
4. **波折 / 阻塞**：代理对 `submitToPlatform` 返回 HTTP 401；`has_shipped` / blocked intent 禁止盲重放；本地 `lizard-import` ≠ 赛狐 `packageDetail.trackNo`。
5. **教训**：一行摘要 + 链到 `docs/solutions/architecture-patterns/sellfox-trackno-write-path-vs-local-import.md`（及 research `submit-to-platform-vs-autopush-2026-07-20.md`）。
6. **下一步（≤3）**：修代理 Key/`submitToPlatform` 写权限 → 新建 `to_process` intent 做填号探针（勿重放 blocked）→（可选）运维打开公网 OIDC。
7. **重规划裁决（显式）**：
   - **不整本作废** `research-synthesis` 的架构与 Intent/CAS 安全协议。
   - **修订 P1C 出口定义**：由「submitToPlatform E2E 推销售平台」改为「赛狐可见 trackNo 探针通过；或证明在关自动推送条件下该 API 不可安全用于仅填号并记产品缺口」。
   - 生产默认仍 Excel；通途继续写 Amazon；赛狐自动推送保持关闭。

其后保留：禁区清单、验证命令、精简项目结构、凭证表（禁止硬编码密钥；真调须用户确认范围）。

HANDOFF 整体宜保持可扫读（约 ≤200 行量级）；细节外链，不内嵌长 chronicle。

---

## §4 维护仪式

每次可交付切片结束，Agent 必须：

1. 更新 HANDOFF：`updated:` 日期，并刷新七块中至少「已完成 / 下一步 / 阻塞」。
2. `docs/log.md` 追加一日记。
3. 若规划假设变化：在 synthesis 文首裁决框补一行，或新增 research 并更新 index。

**禁止**把「当前真相」只写进 `session-progress` 末节而不回写 HANDOFF。

---

## §5 范围外

- 不改业务代码；不重跑 live `submitToPlatform`
- 不全文重写 `research-synthesis` / `session-progress`
- 不新建 CURRENT.md、ARCHITECTURE.md、模块级 llms.txt
- 不把根 `AGENTS.md` 扩成模块状态镜像（可选一行指针除外）

---

## 成功标准

- 新 Agent 仅读 HANDOFF 即可正确回答：现行目的、代码是否已合、产品缺口、禁区、下一步、是否整本重规划。
- README / `docs/index` / research index / skill 的「先读」指引与 HANDOFF 一致，无「暂不提 PR」或错误功能分支名。
- synthesis 文首可见重规划裁决，与 2026-07-20 业务事实一致。
- 无 CURRENT.md；OKF `log` + 根 `index.md` 已更新。

---

## 实现顺序（交给 writing-plans）

1. 重写 `AGENT_HANDOFF.md` 热区（§3）
2. 对齐 README、skill、两处 index、sample-path、session-progress 文首、synthesis 文首裁决框、log
3. `python scripts/update_index.py`
4. 自检：搜索残留「暂不提 PR」「feature/sellfox-shipping-p1a-rest」、skill「当前阶段（P1A）」等
5. 分支提交 → PR（文档-only）

---

## 参考

- 审计与外部调研结论见 brainstorming 会话（2026-07-21）；模块事实锚点：PR #96/#97、`submit-to-platform-vs-autopush-2026-07-20.md`、solutions `sellfox-trackno-write-path-vs-local-import.md`
- OKF：项目 `.claude/skills/okf/SKILL.md`；上游 [OKF SPEC](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
