---
okf: v0.1
type: Research
title: DeepSeek V4.1 Flash-1017 Agent Harness 选型调研（Claude Code / DSH / OpenCode / Pi / WorkBuddy）
date: 2026-10-19
tags: [deepseek, deepseek-v4, flash-1017, claude-code, deepseek-harness, dsh, opencode, pi, workbuddy, agent-harness, prompt-cache, windows]
source: Web research + local verification on 2026-10-19
---

# DeepSeek V4.1 Flash-1017 Agent Harness 选型调研

> 调研日期：2026-10-19。结论基于公开资料 + 本机实测；A/B 细节见
> [`2026-10-19-ab-harness-results.md`](2026-10-19-ab-harness-results.md)。

## 一句话结论

**有更好的工具，但不是“换掉 Claude 生态”。** 本机最划算的升级是把 Claude Desktop 3P 内嵌的
Claude Code **2.1.119** 换成独立 CLI（已升到 **2.1.303**）；1017 原生体验用官方
DeepSeek Harness **0.2.1-rc.2** 在隔离的 ASCII 工作区试跑；OpenCode 不作为 Windows 日常主力。
实测结果：Claude Code 在仓库工作流和编码任务上更快、更稳；DSH 的 token/缓存效率更好，
但 Windows 沙箱摩擦明显（详见 A/B 报告）。

---

## 二、本机已核实的事实

| 项目 | 实测值 |
|---|---|
| 当前会话入口 | `CLAUDE_CODE_ENTRYPOINT=claude-desktop-3p` |
| 3P 内嵌 Claude Code | **2.1.119**（`...\Claude-3p\claude-code\2.1.119\claude.exe`） |
| 独立 Claude Code CLI | 升级前 **2.1.224** → 升级后 **2.1.303** |
| npm 最新 Claude Code | **2.1.303** |
| 上次自动更新 | 2026-08-07 失败：`update_apply_exe_locked`，停在 2.1.224 |
| 网关 Anthropic 端点 | `https://api.vilavi.cn/`（3P 宿主注入） |
| 网关 OpenAI 兼容端点 | `https://api.vilavi.cn/v1`（WorkBuddy / DSH / OpenCode 用） |
| 网关模型 ID | `deepseek-flash`、`deepseek-v4-flash`、`deepseek-v4-flash-vision-exp`、`deepseek-v4-pro`、若干 GPT |
| “1017”如何调用 | **没有 `deepseek-v4-flash-1017` 这个模型 ID**；1017 权重在 `deepseek-flash` / `deepseek-v4-flash` 后面 |
| 环境变量作用域 | `ANTHROPIC_*` 只由 3P 宿主注入，**不是用户级/机器级**；独立 CLI 从普通终端启动时拿不到 |
| 机器 | i3-12100，**31.7 GB RAM** |
| 已装 | Claude Desktop `1.4758.0.0`、WorkBuddy 桌面、OpenCode 桌面目录；`dsh` 已装 `0.2.1-rc.2` |

**直接结论：** 当前不是“Claude Desktop 很好、CLI 更好”的对比，而是“桌面端内嵌了一个
105 个版本前的 Claude Code（2.1.119）”。最便宜的升级不是换生态，而是换入口。

---

## 三、1017 本身的关键事实

- 2026-10-17 无预告上线，API 模型名不变，仍用 `deepseek-flash` / `deepseek-v4-flash`。
- 官方自报 11 项基准全涨：Terminal-Bench 4.0 31.2→42.3，DeepSWE 74.2→77.0，ProgramBench 20.3→29.1。
- 截至 10/19 **无 AA/Vals 独立复测**；Terminal-Bench 跑在 Claude Code 框架、DeepSWE 用
  Mini-SWE-V2，分数是“该 harness 配置下”的分数。
- 能力方向是“自反馈 RL / 许愿式编程”：能从头把项目做出来，但**自检纠错仍是短板**。
- 官方原文：**“Optimized for DeepSeek Harness, Tencent CodeBuddy, WorkBuddy, and more.”**
  即 **DeepSeek 针对这些平台做了优化**，不是 WorkBuddy 反过来优化 DeepSeek。
- Harness 要求 ≥ `0.2.1-rc.1`；当前 npm `next` 为 `0.2.1-rc.2`。
- Search & Fetch API 在 DSH / Claude Code / Codex 中服务端调用免费到
  **2026-10-31 16:00 UTC（北京时间 11-01 00:00）**，之后 $0.75/千次。

---

## 四、横向评测

### 4.1 Composio：同一 DeepSeek V4 Flash，8 个 Harness 跑 30 项任务

| Harness | 成功 | 单次成功任务成本 | 中位耗时 |
|---|---|---|---|
| **Pi** | **20/30 (66.7%)** | **$0.028** | 132.2s |
| Oh My Pi | 17/30 | — | — |
| **Claude Code** | 16/30 | **$0.195（约 Pi 的 7 倍）** | 122.7s |
| Codex / Deep Agents | 16/30 | — | — |
| Prime Agent / Hermes | 15/30 | — | — |
| **OpenCode** | **14/30（最低）** | — | 129.7s |

**关键结论：** 同一模型只换 harness，成功率从 46.7% 到 66.7%，成本差 7 倍。差距主要来自
**缓存纪律**：工具少且顺序固定、会话只追加不重写、系统提示静态、中间数据外置。

### 4.2 腾讯 WorkBuddy Bench：Claude Code vs CodeBuddy Code

- 260 道真实任务，7 个模型 × 2 套 harness，28 组同模型对比。
- 总计 **Claude Code 17:11**；**代码领域 7:0 全胜**；Web 和办公 CodeBuddy 小幅领先。

---

## 五、各工具的真实问题

### 5.1 Claude Code CLI

**优点**
- 与现有 `AGENTS.md` / `.agents/skills` / hooks / worktrees / MCP 完全兼容。
- 独立 CLI 2.1.303 比 3P 内嵌 2.1.119 新 100+ 个版本。
- 实测 T1/T2 都是最快、最稳；T2 精确命令一次通过。

**真实问题**
| 问题 | 状态/说明 |
|---|---|
| 子 Agent 400：`thinking options type cannot be disabled when reasoning_effort is set` | 2.1.166 引入，社区称 2.1.170 已修；2.1.303 在其后 |
| thinking 块未回传：`content[].thinking must be passed back` | DeepSeek thinking 模式要求 tool call 后的 reasoning_content 回传；多轮/切模型时可能 400 |
| `thinking.type=adaptive` / `reasoning_effort` 不被支持 | 需要代理剥离；社区方案 `dsv4-subagent-fix`（只清子 Agent）、`dsv4-cc-proxy`（全量归一化） |
| 未知模型窗口 | 实测提示不认识 `deepseek-v4-flash`，默认按 200k；**模型名加 `[1m]`** + `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000` |
| Claude 专属能力 | `/ultrareview`、Task budgets、xhigh、部分 Skills 签名依赖 Anthropic 后端，第三方端点会降级 |
| `total_cost_usd` 不可信 | 对未知模型 `costBasis: unknown`，它按 Anthropic 价估算；实际账单看 new-api |

### 5.2 DeepSeek Harness（DSH）

**优点**
- 官方原生适配 1017，Search/Fetch 服务端工具免费到 11/1。
- MIT 开源，“一切皆插件”；PTC 模式省 token；append-only 会话日志；内置沙箱。
- 官方桌面版（2026-09-29 起）开箱即用；npm `next` 当前 `0.2.1-rc.2`。
- 实测 token 效率更好：T1 缓存命中 74.9%，T2 95.7%，新输入 token 明显少于 Claude Code。

**真实问题（本机实测 + 社区）**
- 仍是 **developer preview，未做安全审计**；API 可能破坏性变更。
- **Windows 沙箱是主要摩擦**：
  - `D:\` 上 `write ACL` 失败：`SetNamedSecurityInfoW failed (Win32 5): grantWrite(...)`。
    `C:\Users\zhang\dsh-workspace` 这类用户目录可以正常写。
  - 只读模式会挡住 `uv` 缓存写入（`Failed to initialize cache ... 拒绝访问`），
    导致 T1 的 `uv run python scripts/check_secrets.py` 根本跑不起来。
  - **可解**：同一 T1 换 `DSH_PERMISSION_MODE=danger-full-access` 后扫描 exit 0、
    22.4s、¥0.0375，仓库 `git status` 无改动；或 `workspace-write` + C: 用户目录 +
    `UV_CACHE_DIR` 放工作区内。D 盘 `grantWrite` 失败（Win32 5）需提权修 ACL 或改用 WSL2。
  - `workspace-write` 下 pytest 缓存目录会留下 `pytest-cache-files-*` 并触发 ACL 拒绝；
    需要 `-p no:cacheprovider` / `--ignore-glob='pytest-cache-files-*'` / `TMP` 放工作区内。
- **PTC 不是自动省钱开关**：`DSH_TOOLS_MODE=ptc` 在 headless 可用，但本任务上
  92.8s / ¥0.0778，反而比 native 的 64.0s / ¥0.0486 更慢更贵；需要按 workload 实测。
- **实测成本**：T2 稳态 DSH native 约 Claude Code 的 **0.37x**（¥0.0486 vs ¥0.1297 高峰），
  缓存命中 95% vs 69%；代价是慢约 2x。
- **WSL2 不是银弹**：官方 Windows 兼容页（2026-08-27 核对）未把 WSL 列为支持面，
  只建议 Windows 用 Node CLI/Web/headless；社区 2026-10-09 实测明确“官方不支持 WSL”，
  需要 `dsh-wsl-desktop` / `dsh-plugin-wsl-env` 等插件，并引入 403/trustedHosts、
  目录选择器、3080/代理、TTY、bubblewrap、pnpm 版本、`/mnt/d` 9P 慢等新问题。
  详见 A/B 报告第八节。
  - V8 old-space 默认约 4GB；8 个子 Agent 并发在 4090MB 报 `heap out of memory`，
    SIGABRT(134) 整个会话崩溃。需 `NODE_OPTIONS=--max-old-space-size=8192`。
  - `npx @deepseek-ai/dsh web` 在 Windows 可能因循环 peer 依赖卡死；建议 `npm install -g`。
  - Node 26 + 源码安装可能 `fs-ext → node-gyp → MSBuild` 失败；建议 Node 24 LTS。
  - 中文路径可能被静默截断；工作区用纯 ASCII、无空格、非盘符根目录。
  - **Web UI 默认 host 实测不监听**；必须显式 `--host 127.0.0.1` 才能起来；且通过
    PowerShell 启动器 `dsh-gw.cmd web` 会静默挂起，实测用 `cmd /c dsh web ...` 或 bash 直接启动可行。
- 网关兼容：DSH 默认发 `developer` role，new-api/DeepSeek 不接受；
  已在 provider `compat` 加 `supportsDeveloperRole: false`，并在 `compat.thinkingFormat: deepseek`。
- 插件生态粗糙：101 个社区插件实测仅 11 个 npm 开箱即用，81 个要从 GitHub 源码装。
- 长会话每轮全量重发，60K 上下文一轮 6–54 秒，缓存命中率可能降到 35%。

### 5.3 OpenCode

| 版本 | 内存表现 |
|---|---|
| 1.x | 多会话 1.9–3GB；长会话 10GB+、极端 70GB+；MCP 孤儿进程每次约 300MB；每个 workspace 独立拉 MCP（5 MCP × 3 项目 × 5 workspace = 75 实例） |
| 2.x | 常驻 daemon 宣称 86MB，用户实测客户端 132MB、全套约 665MB；但仍有 TUI resize 触发 **24–28GB OOM** 的 open issue #51761 |
| Windows | 反馈尤其差；Linux 约 400MB，Windows 可达 2.8GB；Electron 桌面端另有约 200MB idle |

其他：
- 2.0 把 Bun 换 Node、Tauri 换 Electron，**API 不兼容、旧插件启动崩溃**；beta 期不建议生产。
- Composio 30 项任务成功率最低（14/30）。
- DeepSeek 缓存：官方 API + 稳定前缀常见 90–98%；`opencode-go/zen` 中转截至 v0.20.0
  **缓存标记被禁用**，可能全程 full re-bill；还有上游 replica/eviction 导致相同请求 44% 冷 miss。
- 结论：**不建议在这台 Windows 机器上把 OpenCode 当日常主力**；要试就用 V2 + 极少 MCP + WSL。

### 5.4 Pi

- Composio 20/30 成功率第一，$0.028/任务，约为 Claude Code 的 1/7。
- 开发者实测近 10 亿 input token，**缓存命中 99.93%**，实付 $2.65（无缓存约 $132）。
- 设计：默认只有 4 个工具，会话只追加，系统提示静态；原生适配 DeepSeek。
- **Pi 1.0（2026-10-01）已加入原生 MCP**（0.99 起内置 `builtin:mcp`，支持 stdio/HTTP/OAuth），
  但刚发布、生态未验证；本轮不纳入 A/B。
- Windows 必须有 bash（Git Bash 即可）；支持 Agent Skills 目录，可复用 `.agents/skills/`。
- 适合做“成本对照组”或批处理，不适合直接替换现有 Claude Code 工作流。

### 5.5 WorkBuddy / CodeBuddy

- **方向澄清**：是 DeepSeek 官方把 1017 **针对 WorkBuddy / CodeBuddy / DSH 做了优化**，
  不是 WorkBuddy 反过来优化 DeepSeek。
- WorkBuddy Intl 已切 1017，**2026-10-31 前应用内免费**（不是免费 API；有账号/每日额度限制）。
- 办公 Agent，1100 万 PC 月活，支持微信/企微/QQ/钉钉/飞书远程下发任务。
- 腾讯自己的 WorkBuddy Bench：代码领域 Claude Code 7:0 胜 CodeBuddy Code；
  Web/办公 CodeBuddy 小幅领先。
- 结论：**办公/非技术同事合适；工程主力仍是 Claude Code**。

---

## 六、推荐

### 主力：独立 Claude Code CLI 2.1.303 + 公司网关

- 保留现有 skills / hooks / MCP / worktrees / `AGENTS.md`。
- 用户级启动器：`C:\Users\zhang\.claude\bin\claude-gw.cmd`（token 从父仓库 `.env` 读取，不落仓库）。
- 模型名必须带 `[1m]`，并设 `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000`。
- 若出现 thinking/子 Agent 400，再加 `dsv4-subagent-fix`（16890）做最小侵入代理。

### 1017 原生尝鲜：DSH 0.2.1-rc.2

- 用 `C:\Users\zhang\dsh-workspace`（纯 ASCII、用户目录，能改 ACL）。
- 用户级启动器：`C:\Users\zhang\.claude\bin\dsh-gw.cmd`；Web UI 需显式
  `--host 127.0.0.1 --port 3080`。
- `NODE_OPTIONS=--max-old-space-size=8192`。
- 需要 `uv` / pytest 写缓存时，把 `UV_CACHE_DIR` 放到工作区内，或使用
  `DSH_PERMISSION_MODE=danger-full-access`（仅可信任务/隔离目录；实测 T1 扫描通过且仓库无改动）。
- 不要把生产仓库的 `.env` 整个暴露给 DSH。
- **成本**：T2 稳态 DSH native 约 Claude 的 **0.37x**（¥0.0486 vs ¥0.1297 高峰），
  缓存 95% vs 69%；代价是慢约 2x。PTC 在本任务上不省钱，按 workload 实测。
- **WSL2**：只在 DSH 成为日常主力、且愿意把仓库迁到 WSL ext4、安装 Linux Node 24 /
  bubblewrap / pnpm 时考虑；否则用 C: 用户工作区。

### 成本实验：Pi

- 适合批处理/长任务；先只做对照，不替换日常入口。
- 1.0 的 MCP 刚落地，等生态稳定再考虑。

### 不推荐

- **OpenCode 作为 Windows 日常主力**：内存问题系统性存在，V2 仍未完全解决，成功率最低。
- **直接在生产仓库跑 DSH 预览版**：先在隔离目录验证。
- **把 token 写进仓库或项目 settings**：只放用户级配置/环境变量。

---

## 七、安全备注（本机发现）

父仓库 `D:\Work\赛狐\Cursor\.env` 有两个格式问题，**不要再用 bash `source` 读取**：

- line 1 有 UTF-8 BOM。
- line 6 的 `VITE_API_KEY` 值含空格（首段长度 3，形如 `Key: <token>`），`source` 会把后半段
  当命令执行并把内容打印到终端。

**2026-10-19 已修复**：备份到 `C:\Users\zhang\.claude\backups\.env.bak-20261019-154524`；
去掉 BOM；line 6 改为标准 `VITE_API_KEY=<token>`；其余行内容未变；
`claude-gw.cmd` / `dsh-gw.cmd` 冒烟仍正常。若该值是真凭证且可能外泄，仍建议轮换。

通用 Windows 约定：写文本优先 `pwsh` 7 的 `utf8NoBOM`，不要用 PowerShell 5.1 的
`Set-Content -Encoding UTF8`（会加 BOM）；Python 读带 BOM 的文件用 `encoding='utf-8-sig'`；
不要整体 `source` `.env`。

---

## 八、长对话与 Pi 的使用场景

### 8.1 Pi 一般用在什么场景

Pi 的定位是**极简、成本敏感、稳定前缀**的 agent harness，不是“全家桶 IDE”：

- **成本敏感的长 agent 循环 / 批处理**：默认 4 个工具（read/write/edit/bash），
  Composio 30 项任务 20/30、$0.028/任务，缓存命中 99.93%。
- **CI / 远程 / 自托管模型**：20+ provider、300+ 模型，可在服务器/Raspberry Pi 上跑；
  1.0 已加原生 MCP、Codemode、deferred tool loading。
- **长任务**：`pi-long-task` 把目标转成 spec → TODO → worker → reviewer，最长 48 小时；
  `pi-delegate` 让 Claude Code 把实现交给 Pi（多文件任务成本约 -33%，微小改动反而 +11%）。
- **业务 agent**：1.0 的 MCP + Codemode 可以读文档、算指标、出报告。
- **不适合**：重 IDE/UX、复杂 MCP 生态、Windows 原生、需要开箱安全护栏
  （Pi 默认偏 YOLO，要装 `pi-permission-system` 之类扩展）。
- **长对话能力**：auto-compaction 默认开启（reserve 16k / keep 20k），支持
  `/compact`、session tree/fork/clone、`pi -c` / `pi -r` / `--session`；
  还有 `pi-fold` 无损上下文折叠、`pi-fuel-gauge` 上下文监控等扩展。

### 8.2 本机 Claude Desktop 长对话现状（重要）

- Desktop 3P 的 Code 会话元数据在
  `...\Claude-3p\claude-code-sessions\...\local_*.json`，共 **173** 个；
  每条含 `cliSessionId`、`cwd`、`model`、`title`、`lastActivityAt`。
- 其中 **42 个**能在 `~/.claude/projects/<cwd>/<cliSessionId>.jsonl` 找到完整 transcript，
  合计 **200.7 MB**，最大单会话 **22.9 MB**。
- **131 个没有 transcript，且全部超过 30 天**；40 个近期会话（+2 个较老的）都有 transcript。
  这高度吻合 Claude Code 默认的 **`cleanupPeriodDays = 30`** 清理策略。
- **行动建议**：
  - 在 `~/.claude/settings.json` 设 `"cleanupPeriodDays": 3650`（或更大），
    防止后续长对话被清掉；没有官方“永不清理”开关，0 不合法。
  - 定期把 `~/.claude/projects/` 归档到 Claude 管理目录之外。
  - 已缺失的 131 个 transcript 不能从 Claude Code 恢复；只能看是否有其他备份/导出。
- **可迁移性**：
  - 已匹配的 Code 会话可直接用独立 Claude Code CLI `--resume <cliSessionId>` 继续
    （同一 `~/.claude/projects` 目录）。
  - DSH / Pi 的 session 格式不同，**不能直接读 Claude Code JSONL**；需要转换或 handoff。
  - Chat（非 Code）会话另存（IndexedDB/本地存储），可用 `claude-explorer` /
    `unified-cowork` 等第三方工具导出 Markdown；没有官方 DSH/Pi 导入。

### 8.3 长对话谁有优势

| 场景 | 优势 | 理由 |
|---|---|---|
| **继续已有 Desktop 对话** | **Claude Desktop / Claude Code** | transcript 已在本地，42 个可直接 resume；换 DSH/Pi 要转换，工具调用/权限/环境不一致 |
| **新的长自主任务** | **Pi / DSH** | Pi auto-compaction + session tree + 99.93% cache；DSH append-only + 80% compaction + resume/fork |
| **成本敏感的长循环** | **Pi** | 稳定前缀、少工具、缓存命中最高 |
| **官方 1017 + Web UI** | **DSH** | 官方适配、Search/Fetch、可视化；但 Windows 沙箱摩擦 |
| **仓库 skills / IDE 体验** | **Claude Code** | 现有 skills/hooks/MCP/worktrees；系统提示大，成本更高 |

**建议：** 老对话留在 Claude Desktop/Claude Code，用 CLI resume；
新长任务用 DSH/Pi + 一段 **handoff brief**（把老对话压成 Markdown 提纲），
不要整段导入。这样既保留上下文，又拿到缓存/成本优势。
模板见 [`docs/handoff-brief-template.md`](../handoff-brief-template.md)。

---

## 九、主要来源

- DeepSeek 1017 官方说明：https://api-docs.deepseek.com/news/news261017/
- DeepSeek Anthropic API 兼容：https://api-docs.deepseek.com/zh-cn/guides/anthropic_api/
- DeepSeek Harness 官方：https://www.deepseek.com/harness/
- DSH providers 文档：https://github.com/deepseek-ai/DeepSeek-Harness/blob/master/docs/user/guide/providers.md
- DSH Windows 兼容性：https://github.com/sandbaseai/deepseek-harness-handbook/blob/main/docs/en/troubleshooting/windows-compatibility.md
- DSH V8 堆崩溃 PR：https://github.com/dsh-tauri/deepseek-harness-desktop/pull/703
- DSH 安装卡死讨论：https://github.com/deepseek-ai/deepseek-harness/discussions/5542
- Claude Code v2.1.224 release notes：https://www.claudeupdates.dev/version/2.1.224
- Claude Code npm：https://www.npmjs.com/package/@anthropic-ai/claude-code
- Claude Desktop 3P 文档：https://claude.com/docs/third-party/claude-desktop/overview
- Claude Code + DeepSeek 兼容坑：https://pypi.org/project/dsv4-cc-proxy/ ；
  https://github.com/Sunleich/dsv4-subagent-fix ；
  https://github.com/deepseek-ai/awesome-deepseek-agent/issues/193
- Composio 8-harness 评测：https://www.infoq.cn/article/XpFUaftcEE3iLgGzYGZi ；
  https://www.c114.net.cn/chipnews/109656.html
- Pi 缓存 99.93%：https://www.dshbase.com/blog/pi-deepseek-cache/ ；
  https://www.c114.net.cn/industry/110354.html
- Pi 0.99 / 1.0 加 MCP：https://pi.dev/changelog/releases/0.99.0 ；
  https://gigazine.net/gsc_news/en/20261002-pi-1-0
- WorkBuddy Bench：https://followin.io/zh-Hans/feed/26914103
- WorkBuddy Intl 接 1017（10/31 前应用内免费）：https://ai.lzw.me/ai-news/item/xgj246drlw70qbgypibz6atla
- OpenCode 内存 issue：https://github.com/anomalyco/opencode/issues/7261 ；
  https://github.com/anomalyco/opencode/issues/14171 ；
  https://github.com/anomalyco/opencode/issues/21115 ；
  https://github.com/anomalyco/opencode/issues/51761
- OpenCode + DeepSeek 缓存：https://github.com/anomalyco/opencode/issues/50258 ；
  https://github.com/NousResearch/hermes-agent/issues/24617
- OpenCode 2.0 重写代价：https://quidproquo.cc/posts/tech/2026-08-22-opencode-2-electron-rewrite-coding-agent/
- Codex CLI 接 DeepSeek：https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/codex/
- DSH vs Claude Code 实测：https://www.datacamp.com/zh/blog/deepseek-harness-vs-claude-code
