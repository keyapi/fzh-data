---
okf: v0.1
type: Log
title: 经验教训变更日志
description: docs/lessons 目录变更历史
tags: [lessons, log]
---

# 变更日志

## 2026-09-20

- **修复（链接）**：本 bundle 失效相对链接。`index.md` 指向 ERPNext 工单教训的链接由 `../erpnext/...`（多退一级）改为 `../../erpnext/...`；本 `log.md` 中指向根 `AGENTS.md` / `CONCEPTS.md` 的链接由 `../../../` 改为 `../../`。
- **修复（链接）**：`docs/fac-mcp-setup.md` 指向 `docs/mcp-setup.md` 的链接由 `../mcp-setup.md` 改为同级 `mcp-setup.md`。
- **修复（链接）**：`.agents/skills/workbuddy-config/SKILL.md` 指向仓库 `docs/` 的 3 条链接少退两级，统一改为 `../../../docs/...`。

## 2026-09-18

- **新增**: [../mcp-setup.md](../mcp-setup.md) — **MCP 选型与安装指南**（canonical 入口）。含选型表（每个 MCP 干什么 / 要什么凭证 / 谁该装）、宿主差异表（Claude Desktop 3P / 普通 / Codex / Cursor 的配置路径与重启要求）、3P 通用事实、启停与裁剪、排错、各 server 详细文档索引。**目标：同事读 main 即可自选要装的 MCP。**
- **收敛**: 3P 的通用事实（配置路径、`mcp-remote` 桥接、重启要求、`~/.mcp-auth` 排错）原先散在 `fac-mcp-setup.md` / `tavily-mcp-setup.md` / `notion-mcp-setup.md` **各写一遍**（三份说同一件事 = 迟早互相矛盾），现以 `docs/mcp-setup.md` 为唯一来源，三份文档改为指向它、只保留各自特有内容。
- **更新**: [../../../AGENTS.md](../../AGENTS.md) — ① §4「安装 MCP 服务器」由 Codex-only 散列改为「按需选装 + 指向 `docs/mcp-setup.md`」，并补 Claude Desktop 3P 视角与「3P/普通是两个独立文件、改错静默无效」警告；② 文档体系树补入 `docs/mcp-setup.md` 与 `docs/lessons/`；③ 修正首行「CLAUDE.md 应为此文件 symlink」的失实描述（实为一行 `AGENTS.md` 的入口文件）。
- **清理**: [../../../CONCEPTS.md](../../CONCEPTS.md)「3P 模式」词条移除字面文件路径与配置字段值（CONCEPTS.md 规范禁止实现细节），改为描述行为差异；路径信息以 `docs/mcp-setup.md` 为准。
- **修复**: `scripts/update_index.py` 的「Updated」原先取文件 **mtime**，而新 clone / worktree 会把所有 mtime 重置成检出时间 → 每次检出都产生几百行假日期 churn（本次实测 791 行里 789 行是假变化）。改为取 **git 提交日期**（单次 `git log --name-only` 建映射，未跟踪文件回退 mtime）。重新生成后日期变为真实提交日期，**幂等验证通过**（连续两次生成除时间戳外完全一致）。

- **更新**: [notion-mcp-setup.md](notion-mcp-setup.md) — 新增「停用某个 Server 但保留配置」。Claude Desktop 无原生 per-connector 停用开关；通行做法是把条目移入 `_disabled_mcpServers` 顶层键（Claude Desktop 只读 `mcpServers`，忽略未知键），配置原样保留、恢复即挪回 + 重启，OAuth token 不受影响。三个独立第三方工具（mcp-server-manager / claude-config-manager / @wyattjoh/mcp-manager）均用此法。**本项目用法：`notion-personal` 常驻（常用），`notion-company` 移入 `_disabled_mcpServers` 备用（仅测试用）。**

- **更新**: [notion-mcp-setup.md](notion-mcp-setup.md) — 新增「五、上下文开销实测与减压结论」。`/context` ground truth：168 个 MCP 工具 = **57.3k token**，两个 Notion 站合计 37k = 1M 上下文的 3.7%，**不构成问题**。
- **更正**: 排查中曾用 `tools/list` 原始 JSON 字节数排序，得出「`notion-query-data-sources` 77.8KB 是大头」——**完全错误**。实测该工具仅 **630 token**（跌出前十），而 `notion-update-page`（15.7KB）实为 1.8k token（第一）。原因：原始 JSON 含完整 JSON Schema，模型收到的是精简渲染版，单站 232KB 原始 JSON ≈ 仅 18.5k token（约 6 倍差距）。**铁律：判断 MCP 开销用 `/context` 实测，勿用字节数换算。**
- **A/B 实证**: `ENABLE_TOOL_SEARCH` 设 `true` / `false` 两次重启后 `/context` **均为 57.3k / 168**，完全一致 → Tool Search 在本环境被 `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` 挡住，设置无效（`~/.claude/settings.json` 已还原）。不建议为它动该变量：收益仅约 4.8%，风险是会话起不来。
- **结论**: 不做进一步减压。保留 `--ignore-tool` 裁掉计划不可用的 3 个工具（约省 1.4k/站，纯赚）。
- **更新**: [notion-mcp-setup.md](notion-mcp-setup.md) — 新增「三、多工作区并存」小节。Notion 托管 MCP 一次 OAuth 只绑定一个工作区；用 `MCP_REMOTE_CONFIG_DIR` 给其中一个 Server 指独立凭证目录即可并存多个工作区。代码级依据（mcp-remote v0.14.2）：`const baseConfigDir = process.env.MCP_REMOTE_CONFIG_DIR || path.join(os.homedir(), ".mcp-auth")`。**未给 Notion 授权服务器发送任何额外参数，零兼容风险。**
- **排除**: 不用 `--resource` 做区分。它虽参与 token 缓存 hash（`getServerUrlHash(serverUrl, authorizeResource, headers, authorizeParams, clientMetadataUrl, tokenEndpoint)`），但 Notion 的 `oauth-protected-resource` 明确发布 `{"resource":"https://mcp.notion.com"}` 并对其校验，传非标准值有 `invalid_target` 风险。
- **落地**: 3P 配置 `mcpServers` 现为 `playwright` / `fac` / `tavily-mcp` / `notion-company` / `notion-personal`；`notion-company` 复用已有 token（免重新授权），`notion-personal` 走独立凭证目录需首次 OAuth。
- **实测记录**: 首次授权（2026-09-18 08:57）连通 `Notion MCP v1.2.0`，工作区为 `mxdeals1023@gmail.com` 名下新建工作区，其内容仅 Notion 模板示例数据（「你的第一个项目」「你的第一个文档」等）。免费版限制：`ai_search` / `query_meeting_notes` 需 Business，`query_multiple_data_sources` 需 full version；`search` / `fetch` / `create_pages` / `update_page` 均可用。

## 2026-09-17

- **新增**: [notion-mcp-setup.md](notion-mcp-setup.md) — Notion 托管 MCP 在 Claude Desktop 3P 模式的接入记录。要点：① 本环境 MCP 配置来源是 `Claude-3p\claude_desktop_config.json`（非 `~/.claude.json`、非仓库 `.mcp.json`，后两者 `mcpServers` 均为空）；② 生效的三个 MCP（playwright/fac/tavily-mcp）**全是 stdio**，`url` 类型从未在 3P 配置里测试过；③ Notion 托管 MCP 只支持交互式 OAuth，裸 `url` 完成不了授权流程，故必须走 `mcp-remote` → 配置 `{"command":"npx","args":["-y","mcp-remote","https://mcp.notion.com/mcp"]}`。
- **更正**: [../fac-mcp-setup.md](../fac-mcp-setup.md) 故障排除表原记「3P 模式不支持 `url` 字段」，经复查**降级为未验证断言**并补「更正说明」小节。反证：`CONCEPTS.md`「3P 模式」词条与 [tavily-mcp-setup.md](tavily-mcp-setup.md) 踩坑 5 均写「配置格式与普通模式相同，唯一区别是路径」；该行无日期无版本；`logs/main.log`/`main1.log` 搜 `not a valid` 零命中。更可能的真实原因是 fac endpoint 需要 OAuth 而裸 `url` 不携带授权流程 —— 与 PR #84 误诊同类（见 tavily 踩坑 5）。
- **背景**: 该断言在接入 Notion 时曾被当作既定事实引用，经用户要求全量核查所有已装 MCP 配置与踩坑记录后发现矛盾。
