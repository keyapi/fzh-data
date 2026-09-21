---
type: skill
name: ce-okf
description: 对话收尾一条龙 —— ce-compound 产学习正文 + OKF 级联登记 + 索引联动 + 凭证扫描 + 提交 + PR。取代手打「请你用 /ce-compound okf 标准 把背景 过程 结果 经验教训 记录到文档脚本skill handoff…之后 git 提交 并 pr」。
version: 0.1.0
triggers:
  - "ce-okf"
  - "ce-compound"
  - "ce-compound-refresh"
  - "okf 标准"
  - "OKF标准"
  - "收尾"
  - "沉淀"
  - "总结本次对话"
  - "总结我们本次对话"
  - "记录背景 过程 结果"
  - "包含但不限"
  - "经验教训"
  - "更新 handoff"
  - "更新文档脚本skill"
  - "不要泄露隐私"
---

# ce-okf Skill

## 这是什么

把「对话收尾」这套固定动作固化成一个命令。用户以前每次都要手打长长一段：

> 请你用 `/ce-compound`（或 `-refresh`）okf 标准，按照项目要求和以往规则，把本次对话中背景 / 过程 / 结果 / 经验教训，补充更新记录到文档、脚本、skill、handoff 文件，方便之后你自己新开对话或别的 Agent 查到并理解、不用再次踩坑，注意不要泄露隐私。之后 git 提交 并 PR。

那段话实际编码了 **AGENTS.md 第 8/9/10/11 条**硬规则 + 一套 8~11 文件的级联登记。本 skill 就是它的可执行版。

## 分工：谁是干什么的

| 组件 | 负责 | 不负责 |
|---|---|---|
| `ce-compound` / `ce-compound-refresh`（用户级，外部） | 学习正文质量：并行子代理、重叠检测、grounding 校验、`CONCEPTS.md` 词表 | **不提交、不开 PR**（写完即结束回合） |
| `okf`（本仓库 `.agents/skills/okf/`） | 三条铁律：`type` 必填 / 每目录 `index.md` / 每 bundle `log.md` | 不知道 `docs/solutions/` 的 schema |
| **`ce-okf`（本 skill）** | schema 归一化 + 级联登记 + 索引联动 + 凭证扫描 + 提交 + PR | 不重写正文 |

`ce-compound` 的 `component` 枚举是 Rails 味儿的（`rails_model` / `hotwire_turbo` / `frontend_stimulus`…），**与本仓库实际用的值不符** —— 归一化是 ce-okf 的活（见第 3 步）。

## 何时触发

用户说「收尾 / 沉淀 / 总结本次对话 / 用 ce-compound 和 okf 标准记录 / 更新文档和 handoff 之后提交 PR」，或直接打 `/ce-okf`。

## 参数

- `/ce-okf` — 默认。一路做到 PR。
- `/ce-okf refresh` — 增量模式：只补「上一次提交之后」的内容，更新既有文档而非新建。
- `/ce-okf no-pr` — 只本地提交，不 push 不开 PR。

---

## 执行流程

### 第 0 步：判定模式（先做，别写错方向）

- 本次对话**已经有过 commit 或已开 PR** → **增量模式**，走 `ce-compound-refresh` 语义。
- 否则 → **新增模式**，走 `ce-compound` 语义。

一个会话有**多个独立学习点**时，逐篇处理，**不要合并成一篇**（ce-compound 的硬约定）。

### 第 1 步：产出学习正文

调 `/ce-compound`（增量模式调 `/ce-compound-refresh`）产出 `docs/solutions/<category>/<slug>.md`。

若该 skill 不可用，自己按第 3 步的模板写。category 用现役目录：
`architecture-patterns/ best-practices/ conventions/ developer-experience/ documentation-gaps/ integration-issues/ tooling-decisions/ workflow-issues/`

### 第 2 步：确认正文小节

沿用 ce-compound 的**知识轨**小节（仓库现役写法，见 `docs/solutions/integration-issues/gls-track-public-rest-calendar.md`）：

```
Context / Guidance（本学习沉淀的做法）/ Why This Matters / When to Apply / Examples / Related
```

Bug 轨用 `Problem / Symptoms / What Didn't Work / Solution / Why This Works / Prevention / Related`。

> **不要**自创「背景 / 过程 / 结果 / 经验教训」中文小节。用户口头说的那四段话映射到上面这些小节的语义里。

### 第 3 步：归一化 frontmatter（关键，ce-compound 不会做）

对齐仓库现役的 **OKF + ce-compound 合并 schema**：

```yaml
---
okf: v0.1                    # OKF 合规标记
type: Reference              # OKF 铁律唯一必填项
title: 中文标题
date: 2026-09-21             # 首次创建日
last_updated: 2026-09-21     # 仅「更新」时加
category: integration-issues # = 所在目录名
module: gls_track            # = 模块目录名
problem_type: integration_issue
component: tracking-integration
severity: medium             # critical | high | medium | low
applies_when:                # 知识轨；bug 轨换成 symptoms/root_cause/resolution_type
  - "什么时候该翻这篇"
tags: [tag-one, tag-two]     # ≤8 个，小写连字符
---
```

**`component` 必须用本仓库的值**，不要用 ce-compound 的 Rails 枚举。现役值（新增了就往下补一行）：

| component | 用于 |
|---|---|
| `tooling` | 脚本 / skill / 工具链 |
| `tracking-integration` | 承运商跟踪（FedEx/UPS/GLS/parcel_track） |
| `api-gateway` | 代理 / 网关 / 鉴权桥 |
| `authentication` | 登录、OAuth、封号 |
| `documentation` | 文档体系本身 |

`problem_type` 沿用 ce-compound 枚举（`integration_issue` / `best_practice` / `workflow_issue` / `developer_experience` / `architecture_pattern` / `design_pattern` / `tooling_decision` / `convention` / `documentation_gap` / 以及 bug 轨那 9 个）。

**别去"修正"已知的不一致**：`<module>/AGENT_HANDOFF.md` 用的是 `type: Handoff`（不在 okf 枚举里）和 `updated:`（不在 okf 字段表里）—— 这是现役事实，保持原样。

### 第 4 步：OKF 级联登记

按顺序改这些（有才改，没有就跳过）：

| # | 文件 | 动作 |
|---|---|---|
| 1 | `docs/solutions/<category>/<slug>.md` | 新建/更新学习文档 |
| 2 | `docs/solutions/<category>/index.md` | 追加一行。**各 category 表头不统一**（`integration-issues` 是 `\| 日期 \| 标题 \| 文件 \|`，`tooling-decisions` 是 `\| 标题 \| 文件 \|`）—— 以该文件现役表头为准，别硬套 |
| 3 | `docs/solutions/<category>/log.md` | 加当日 `- **新增**: …` |
| 4 | `docs/solutions/index.md` | 加一行 |
| 5 | `docs/solutions/log.md` | 加当日条目 |
| 6 | `<module>/AGENT_HANDOFF.md` | 更新模块详情 / 新增 pitfall |
| 7 | `<module>/docs/index.md` + `<module>/docs/log.md` | 新模块全套建；老模块只追加 log |
| 8 | `.agents/skills/<related>/SKILL.md` | 涉及某模块时，补触发词 / "新对话必读"链接 |
| 9 | `AGENTS.md` 模块索引表 | 只有新模块才加行 |
| 10 | `CONCEPTS.md` | 出现新的领域术语才加 |
| 11 | 根 `index.md` | 第 5 步自动生成，不要手改 |

`log.md` 条目按日期**倒序**，格式 `- **新增**/**更新**/**修复**: 做了什么、为什么`。

### 第 5 步：索引联动（AGENTS.md 第 11 条）

```bash
uv run python scripts/update_index.py    # 重生成根 index.md，纳入本次提交
```

完成后**必须**输出：`已同步更新根目录索引`。

两条实测（踩过的坑，别当门禁用）：

- `--check` 是**逐字节比对**，而文件头的 `generated:` 是**分钟级**时间戳 —— 所以 `--check` 只在"刚生成完的同一分钟内"才通过，**绝大多数时候会误报 STALE**。判断同步与否要看**内容**（新文档有没有进索引表），不要看它退出码。
- 脚本优先取 **git commit 日期**，未跟踪文件回落 mtime。所以「先提交、后生成」会让被改文件的 `Updated` 列显示本次提交日期；「先生成、后提交」则显示上一次的日期。仓库现役习惯是**和文档放同一个 commit**（如 `3ee5ca8`），即日期列滞后一个 commit —— 这是可接受的，不必为了对齐日期再补一个 commit。

### 第 6 步：隐私与凭证清关（第 9 条）

```bash
uv run python scripts/check_secrets.py
git diff origin/main...HEAD | grep -iE "(api_key|api_secret|password|token|ghp_|github_pat_)\s*=\s*['\"]?\w{8,}"
git diff origin/main...HEAD | grep -iE '"[^"]*:\s*[A-Za-z0-9+/=_-]{20,}[^"]*"'
git diff origin/main...HEAD | grep -iE '(token|key|api_key)\s*[:|]\s*`?[A-Za-z0-9+/=_-]{20,}'
git diff origin/main...HEAD | grep -iE 'x-api-key:\s*[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9_-]{20,}'
```

**全部必须零输出。** 另外：

- 文档里不写明文凭证、真实客户名、真实员工名；示例值写 `<your_key>` / `***`。
- 主题本身敏感时（例如用户要求「不要出现盗版 / D版 / 正版等字样」），**改用技术中性措辞**记录 —— 记录到，但别扎眼。
- 顺带扫一眼仓库根有没有游离的数据文件（`*.json` / `*.csv` / `*.xlsx`）混进来。

### 第 7 步：提交 + PR（第 8 条）

**绝不直接推 main。** 任何改动（包括纯文档）都走分支。

```bash
# 分支：当前已在 feature/claude 分支就直接用；在 main 上则先建
git checkout -b claude/ce-okf-<topic>

# 按文件名逐个 add，不要 git add -A
git add <具体文件>...

git commit -m "$(cat <<'EOF'
docs(<scope>): <中文描述>

- <改了什么> → <文件>
- <改了什么> → <文件>

已同步更新根目录索引。无客户数据/凭证；无隐私外泄。
EOF
)"

git push -u origin HEAD

# PR body 必须走 --body-file，不要 stdin/heredoc（否则 body 可能静默为空）
gh pr create --title "<70 字以内>" --body-file "$BODY_FILE"
```

- commit 类型：`docs(<scope>)`，纯文档；夹带脚本用 `feat(<scope>)`。
- 结尾**固定**加清关语：`无客户数据/凭证；无隐私外泄。`
- PR body：做了什么 / 为什么 / 怎么测；`no-pr` 参数时跳过 push 和 PR。

### 第 8 步：报告

结束时给用户四件事，别啰嗦：

1. PR 链接（或「已本地提交，未推」）
2. 改了哪些文件
3. `已同步更新根目录索引`
4. 遗留 / 存疑项

---

## 首次安装到新机器

本 skill 在 `.agents/skills/ce-okf/`，需要软链才能被 Claude Code / Claude Desktop 看到：

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

（`setup.ps1` 把 `.agents/skills/*` 链进 `~/.claude/skills/`；Codex 用户不需要这步。）
