---
okf: v0.1
type: Reference
title: Claude Desktop 的 MCP「Server disconnected」——先读 mcp-server-<name>.log，多半是 npx @latest 装包被打断
date: 2026-11-11
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "Claude Desktop 启动弹窗 `MCP <name>: Server disconnected`"
  - "本地 MCP 用 `npx @latest` 启动，且最近重启过机器或上游刚发新版"
  - "需要判断这是系统更新、网络还是 npm 装包的问题"
tags: [claude-desktop, mcp, npx, npm-cache, playwright, windows, troubleshooting]
---

# Claude Desktop 的 MCP「Server disconnected」——先读 mcp-server-<name>.log

## Context

2026-11-11，Claude Desktop 3P 模式（配置在 `%APPDATA%\Claude-3p\claude_desktop_config.json`）启动后弹窗
`MCP playwright: Server disconnected.`。前一天 Windows 推送了更新、机器发卡，用户重启装更新后才出现，
很容易归因于「Windows 更新把环境搞坏了」。

实际时间线推翻了这个归因：**安装发生在重启之后，重启并没有打断任何正在进行的安装**。真正的原因是
`@playwright/mcp@latest` 在重启后的首次启动里自动升级到 0.0.85，安装过程解包失败，入口 `cli.js` 缺失，
node 立即退出。约两分钟后另一次 npx（新会话触发的）把目录补装完整，所以「另一个对话里浏览器 MCP 又能用了」。

## Guidance

### 第一步永远是读对日志

- 每个 MCP 子进程有独立日志：`%APPDATA%\Claude-3p\logs\mcp-server-<name>.log`
  （普通模式对应 `%APPDATA%\Claude\logs\`；两个模式的配置与日志目录相互独立）。
- 汇总日志 `mcp.log` 只有一行 `Server disconnected`，**看不到子进程的 stderr**；只查它等于没查。
- npm 自己的 debug 日志在 `%LOCALAPPDATA%\npm-cache\_logs\`，默认只保留最近 10 份（`logs-max=10`）。
  几轮 npm 命令就能把事发那份挤掉 —— 需要证据要当场复制。

### 判读模式（本次的真实日志）

```
13:53:30  Server started and connected successfully
13:53:34  Message from client: initialize
npm warn exec The following package was not found and will be installed: @playwright/mcp@0.0.85
npm warn tar TAR_ENTRY_ERROR ENOENT: ... playwright-core\types\structs.d.ts
npm warn tar TAR_ENTRY_ERROR ENOENT: ... playwright-core\types\types.d.ts
Error: Cannot find module '...\_npx\<hash>\node_modules\@playwright\mcp\cli.js'
13:53:51  Server transport closed unexpectedly, this is likely due to the process exiting early
13:53:51  [error] Server disconnected
13:55     （第二次 npx）同一目录被补装完整
```

四条判读规则：

1. **`will be installed` = 用户没升级，是 `@latest` 自己升级了**。npx 每次启动都会向 registry 解析 tag；
   上游发新版后的第一次启动就是一次联网安装。
2. **`TAR_ENTRY_ERROR ENOENT ... open <文件>` 不是「文件被占用」**，而是解包时目标父目录不存在 ——
   安装目录状态不一致，典型的解包被打断或写入冲突。
3. **`MODULE_NOT_FOUND ... cli.js` = 包没装完就被拿去执行**。npm 对解包错误**只 warn、不重试、
   不校验安装完整性**，然后照常启动入口。
4. **Claude Desktop 只看到「进程退出」**，同一会话不会自动重拉 MCP。所以失败不会当场自愈，
   只有下一次启动/新会话触发的 npx 会顺带补好。

### 可以排掉的伪原因

- **磁盘满**：`df -h /c` 当时还有 12G 空闲。
- **重启打断安装**：安装时间戳在重启之后，且失败时刻没有第二次重启、没有进程被杀的记录（node 是
  自己报错退出的）。
- **系统更新改坏了配置**：配置文件与缓存目录的 mtime 都只是本次安装产生，配置内容未被改动。

具体到「解包为什么被打断」无法给出单点结论：npm 的事发 debug 日志已被轮转删除。最合理的解释是刚重启
完系统仍在收尾（Windows 更新后台任务、杀软扫描），解包写盘被干扰。**不能把推断说成事实**，但修复动作
不依赖这个单点原因。

### 恢复

1. **最省事**：再开一个会话或重启应用，让 npx 重跑一次把包装完（本次是这样恢复的）。
2. **还不行**：删掉该 MCP 的 npx 缓存目录再装。缓存目录名是 npx 按包 spec 生成的 hash，可在日志里看到：
   ```bash
   rm -rf ~/AppData/Local/npm-cache/_npx/<hash>
   npx -y @playwright/mcp@latest --help   # 预热，确认能起来
   ```
   只删报错的那一个 hash，不要动其他 `_npx/*`（fac / tavily / notion 的缓存也在里面）。
3. **自检不需要打开 Claude**：直接走 MCP 握手 + 工具列表，见 Examples。

### 是否固定版本

| | `@latest` | 固定 `@x.y.z` + `-y` |
|---|---|---|
| 自动升级 | 有 | 无，需手动 |
| 启动 | 每次解析 tag，新版首次启动要联网安装 | 直接用缓存，秒开 |
| 风险 | 新版首次安装失败就重演本问题 | 风险只出现在手动升级时 |

本次用户选择**保留 `@latest`**、不加自愈包装脚本。若以后升级又失败，按上面「恢复」第 2 步处理即可。
想彻底消灭这个窗口，可以给 MCP 套一个启动包装脚本：检查入口文件存在性，缺失就删缓存重装后再启动。

## Why This Matters

这类报错的现象（弹窗、系统刚更新过）非常容易让人去查 Windows、查网络、查账户，花大量时间也找不到问题；
而根因其实在 `mcp-server-*.log` 里写得明明白白。知道「先看独立日志、先找 `will be installed` 和
`TAR_ENTRY_ERROR`」能把排查从小时级压到分钟级，也避免误判为系统故障而去做无谓的系统级改动。

## When to Apply

- Claude Desktop 启动弹 `MCP xxx: Server disconnected`。
- 该 MCP 用 `npx <pkg>` / `npx -y <pkg>@latest` 启动。
- 机器刚重启过、或上游刚发了新版本。
- 同一会话里工具列表缺失，但换一个会话又好了。

## Examples

直接验证某个 playwright MCP 版本能否正常起服务（不打开 Claude）：

```bash
{ printf '%s\n' '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"probe","version":"0.1"}}}'; sleep 4; \
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'; sleep 1; \
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'; sleep 3; } \
  | npx -y @playwright/mcp@0.0.85 --headless --isolated 2>&1 | grep '"id":1'
```

返回里出现 `"tools":[...]` 就说明包完整、可启动；报 `MODULE_NOT_FOUND` 则是装包损坏，按「恢复」处理。

查看某个 MCP 的独立日志尾部：

```bash
tail -n 40 "$APPDATA/Claude-3p/logs/mcp-server-playwright.log"
```

## Related

- [Codex (ChatGPT Desktop) 更新后 Windows 安装失败与对话历史恢复](codex-chatgpt-windows-setup-config-recovery.md) —— 同样是桌面端自动更新引发的启动失败，思路一致：先定位应用自己的日志与配置，别先怀疑系统。
- [Windows 上 worktree 的 CLAUDE.md：symlink 还是 stub](windows-worktree-claude-md-symlink.md) —— 另一个「Windows 环境状态」类问题。
- `docs/mcp-setup.md` 第五节「排错」—— MCP 选型、启停与通用排错。
