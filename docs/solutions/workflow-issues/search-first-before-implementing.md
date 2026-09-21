---
okf: v0.1
type: Reference
title: "Search First Before Implementing: Always Check Official and Project Documentation Before Making Changes"
date: 2026-07-14
last_updated: 2026-09-21
category: workflow-issues
module: development_workflow
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "Configuring third-party tools or services where official docs specify exact package names and versions"
  - "Editing configuration files in environments with multiple config paths (e.g., Claude vs Claude-3p)"
  - "Working in a project that already has documentation covering the task at hand"
  - "Setting up integrations (MCP servers, API clients, SDKs) with version-pinned dependencies"
  - "拼自己系统的内部 URL / 深链 / 错误码约定 —— 这类内部约定优先搜项目已有实现"
  - "评估第三方方案（该抄它们的「能力清单」，不只是拿来对比后自建）"
symptoms:
  - "Agent edits the wrong configuration file multiple times without effect"
  - "Configuration changes have no observable impact despite correct syntax"
  - "Time wasted on trial-and-error cycles that existing documentation would have prevented"
  - "Agent uses incorrect package names or unversioned '@latest' references"
  - "Agent misses environment-specific configuration paths documented in the project"
root_cause: inadequate_documentation
resolution_type: workflow_improvement
tags: [agent-workflow, mcp-configuration, search-first, claude-desktop-3p, tavily, internal-conventions, third-party-eval]
---

# Search First Before Implementing: Always Check Official and Project Documentation Before Making Changes

## Context

在配置第三方 MCP 服务（Tavily MCP）时，Agent 在未查阅官方文档和项目已有文档的情况下直接开始编辑配置文件，导致两个错误：

1. **使用了错误的 MCP key 和版本号**：将 key 设为 `"tavily"` 而非官方指定的 `"tavily-mcp"`，版本号用 `@latest` 而非官方推荐的固定版本 `@0.1.2`
2. **编辑了错误的配置文件路径**：在 3P 模式下，应该编辑 `Claude-3p\claude_desktop_config.json`，但 Agent 多次编辑了 `Claude\claude_desktop_config.json`

这两个错误的根因相同：**在动手之前没有先搜索已有的信息和文档**。项目文档 `docs/fac-mcp-setup.md` 早已记录了 3P 模式路径差异，`AGENTS.md` 也已将"先搜再造"列为第 1 条 Workflow Principle，但都被忽略了。

## Guidance

### 核心原则："先搜再造"（Search First, Then Create）

在任何实现/配置任务开始前，按以下顺序搜索：

1. **官方文档**：目标工具/服务的官方文档，获取最新、最准确的配置说明
2. **项目已有文档**：特别是 `docs/`、`docs/solutions/`、`docs/lessons/` 下的相关记录
3. **项目指令文件**：`AGENTS.md` / `CLAUDE.md` 中的相关原则和规则

具体到 MCP 配置场景：

```
步骤 1: 搜索目标服务的官方配置文档
  例如：Tavily 的配置文档在 docs.tavily.com/documentation/mcp#configuring-mcp-clients

步骤 2: 搜索项目中是否已有相关文档
  例如：本项目 docs/fac-mcp-setup.md 已记录 3P 模式的配置路径差异

步骤 3: 确认目标环境的特殊性后再动手
  例如：检查用户使用的是普通模式还是 3P 模式，确认配置文件路径
```

### Claude Desktop 3P 模式的配置路径

3P 模式（使用第三方 API 如 DeepSeek）与普通模式的配置路径不同：

| 模式 | 配置文件路径 |
|------|-------------|
| 普通模式 | `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` |
| 3P 模式 | `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude-3p\claude_desktop_config.json` |

3P 模式的配置文件还包含 `"deploymentMode": "3p"` 字段。

### 标准 Tavily MCP 配置（3P 模式）

```json
{
  "deploymentMode": "3p",
  "mcpServers": {
    "tavily-mcp": {
      "command": "npx",
      "args": ["-y", "tavily-mcp@0.1.2"],
      "env": {
        "TAVILY_API_KEY": "<your-api-key>"
      }
    }
  }
}
```

关键字段：
- `"tavily-mcp"`：MCP key 名称，**必须与包名一致**，不能简化为 `"tavily"`
- `"tavily-mcp@0.1.2"`：**必须固定版本号**，不能用 `@latest`。固定版本避免上游 breaking change
- `"TAVILY_API_KEY"`：环境变量名必须全大写，与包文档一致

## Why This Matters

**时间成本**：本次案例中，因未查文档导致的反复修改浪费约 15-20 分钟。如果一开始就查阅官方和项目文档，配置可在 3 分钟内完成。

**信任成本**：当 Agent 反复犯低级错误（编辑错误文件、使用错误配置）时，用户必须介入纠正，降低信任度。

**知识复用失效**：项目文档 `docs/fac-mcp-setup.md` 已记录 3P 模式路径差异，但 Agent 没有搜索就不知道它的存在——已有知识没有发挥应有效用，这正是"compound engineering"的反面。

**破坏性风险**：编辑错误的配置文件可能修改正确但路径不对的文件导致无效果（低级错误），或修改了正确文件但配置被错误值污染（高危错误）。

## When to Apply

以下场景**必须**执行"先搜再造"：

1. **配置任何新的 MCP 服务**：第一步永远是查阅其官方文档中的配置说明
2. **修改已有配置**：检查项目文档中是否记录了该配置的背景、特殊注意事项或已知问题
3. **在特殊环境下操作**：如 3P 模式、MSIX 打包版本、Sandbox 模式等——这些环境往往有不同于标准安装的配置文件路径
4. **用户提供了任何文档链接或文件路径**：先阅读再动手
5. **任何非代码的配置类任务**：环境变量、JSON/YAML 配置、平台设置等

以下场景可以跳过：

- 纯代码逻辑修改（项目内业务代码，无外部依赖变更）
- 使用非常熟悉的日常工具（如 git、npm 基础命令）
- 用户明确说"不需要查文档，按我说的做"

## Examples

### 错误做法

```
用户: "帮我配置 Tavily MCP"

Agent 行为:
1. 直接打开 %APPDATA%\...\Claude\claude_desktop_config.json
2. 添加:
   "tavily": {
     "command": "npx",
     "args": ["-y", "tavily-mcp@latest"],
     "env": { "TAVILY_API_KEY": "..." }
   }
3. 失败后再次修改同一个错误文件，反复尝试
4. 用户不得不介入

结果: 浪费时间，用户信任度下降
```

### 正确做法

```
用户: "帮我配置 Tavily MCP"

Agent 行为:
1. 搜索 Tavily 官方文档 → 获得正确的 key 名和版本号
2. 搜索项目中已有文档 → 发现 docs/fac-mcp-setup.md 记录了 3P 模式路径差异
3. 确认用户当前环境（普通模式还是 3P 模式）
4. 使用正确路径和正确配置，一次成功

结果: 快速、准确、用户信任
```

搜索命令示例：

```bash
# 搜索项目中的 MCP 相关文档
grep -r "mcp\|MCP\|tavily\|claude_desktop_config" docs/ --include="*.md" -l

# 搜索项目中的 3P 模式相关文档
grep -r "3p\|Claude-3p\|deploymentMode" docs/ --include="*.md" -l
```

## Case 2（2026-09-21 补充）: 搜「项目内已有实现」，不只是文档

原文只强调搜**文档**。但内部约定（URL 格式、错误码含义、字段枚举）**常常只在代码里**，不一定是文档。
2026-09-21 接 NAS MCP 时，我在这上面栽了一次：

**做错的**：要给 NAS 路径生成 File Station 深链，我**自己猜了格式** `?launch=FileStation&path=<encoded>`，
还写进文档当成结论。

**实际**：EN 的**产品物料库**早就在做这件事。用户点了一句「EN 里 NAS 相关代码主要在 产品物料库 那个 app」，
去测试服务器一搜就找到：

```
vilavi_pim/api/nas.py                       ← NAS 核心（SynologyNAS 类）
work_order_task/.../item_group_nas_path.py  ← encode_filestation_link()  ← 真正的深链实现
```

真格式是**双层 URL 编码**，和我猜的完全不同：

```python
first  = quote(path, safe="");  second = quote(first, safe="")
link = f"https://{domain}/?launchApp=SYNO.SDS.App.FileStation3.Instance&launchParam=openfile%3D{second}"
```

顺带还对齐出两处细节：会话失效错误码是 **105/106/107**（我原本只判 106/107）；
Thumb API 的 `path` **要加双引号**（spec 要求）。**这两条自己猜是猜不出来的。**

**做法**：找内部约定时，**搜代码**而不只是搜文档：

```bash
# 在 EN 测试服务器上（bench 目录）
ls /home/frappe/frappe-bench/apps/
sudo grep -rln "<关键词>" /home/frappe/frappe-bench/apps/<app>/ --include="*.py" --include="*.js"
```

关键词用**功能词**（如 `launchApp` / `NAS` / `syncing` / 字段名），比搜中文更有效。

## Case 3（2026-09-21 补充）: 第三方方案的「能力清单」也要抄

评估第三方方案时，**不要只写对比表然后自建** —— 至少把候选方案的**工具/功能清单**抄下来当 checklist。

2026-09-21 评 3 个开源群晖 MCP 时，我只做对比就选了自建，结果自建的功能面远小于现成方案，
变成「用户要一个功能我加一个」。事后抄 mrquj 的工具表才发现一次漏了 7 项
（搜索 / 缩略图 / 文件夹大小 / 校验和 / 分享链接 / 压缩包 / 读图）。

**做法**：即便决定自建，也先把候选方案的功能表抄成 checklist，再对照底层 API 的能力上限，
**一次性补齐**，而不是等用户点菜。

## Why This Matters（Case 2/3 补充）

内部约定**猜错的代价特别高**：它不是「写错了会报错」，而是**看着能跑、结果不对**。
我猜的深链格式照样返回 200，用户点开才发现进不去 —— 与「吞异常」那类 bug 同性质。
而这类约定**项目里通常已经有唯一正解**，搜一次就能省掉整轮返工。

## Related

- [mcp-to-chatgpt-bringup-lessons.md](mcp-to-chatgpt-bringup-lessons.md) — ChatGPT 连接器接入 FAC 的实测记录（同批 NAS MCP 工作）
- [docs/fac-mcp-setup.md](../../../docs/fac-mcp-setup.md) — FAC MCP 配置文档，已记录 3P 模式与普通模式的配置文件路径差异
- [docs/lessons/tavily-mcp-setup.md](../../../docs/lessons/tavily-mcp-setup.md) — Tavily MCP 配置教训记录（Codex 平台）
- [Tavily MCP 官方文档](https://docs.tavily.com/documentation/mcp#configuring-mcp-clients) — 正确的 key 名称和版本号
