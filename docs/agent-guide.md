# Agent 开发指南

> 本文档面向维护和扩展 fzh-data 项目的 AI Agent（Claude Code / Codex CLI 等）。

## 运行规则

- 永远用 `uv run python`（uv 管理的 venv）
- 永远用 `uv add <包名>` 加依赖
- 每个脚本从模块目录运行：`cd <module_dir> && uv run python <script>.py`

## 代码约定

- **Column names in Chinese**: Excel 列名用 UPPER_CASE 常量，如 `COL_SKU = "产品编号"`
- **`os.chdir()` pattern**: 每个脚本启动时 `os.chdir(Path(__file__).resolve().parent)`
- **自动文件选择**: 按 `st_mtime` 选最新文件，排除 `~$` 锁文件
- **Excel 输出**: 所有 `.xlsx` gitignored，带时间戳文件名 `*_YYYYMMDD_HHMMSS.xlsx`

## Git 约定

- Commit 消息**中文**，格式 `type(scope): description`
- 类型: `feat`, `fix`, `docs`, `init`, `refactor`
- 开发在分支上进行，merge 到 main

## Skill 管理规则

### 编写原则

| 原则 | 说明 |
|------|------|
| **SKILL.md < 300 行** | 只保留触发条件、约束、管道概要 |
| **AGENT_HANDOFF.md 放细节** | 函数表、字段映射、CLI 参数、边界条件 |
| **去重** | SKILL.md 不重复 AGENTS.md 内容，不重复 AGENT_HANDOFF.md 内容 |
| **发现即更新** | 每次改脚本或发现新边界条件，立即更新 AGENT_HANDOFF.md |

### SKILL.md description 编写

- 包含用户真正会说出口的词：模块名、动词、数据源名
- 中英文都要覆盖（如 "库存初始值"+"stock_init"+"通途库存"）
- 明确 NOT 情况：什么情况下**不要**触发此 skill
- 触发词类型覆盖：模块名中英文、核心动词、数据源名、用户习惯说法

### 模块结构

```
module_dir/
├── <script>.py / README.md / AGENT_HANDOFF.md
├── __init__.py (for uv build)
├── 数据源/ (gitignored)
└── out/ (gitignored)
```

## 文档更新 checklist

```
[ ] .py files changed? → AGENT_HANDOFF.md 变更在同一 diff 中?
[ ] 新 pitfall 发现? → 加到子模块 AGENT_HANDOFF.md 中
[ ] 模块 scope 变化? → SKILL.md description 更新?
```

如果故意不更新文档（typo fix, reformatting），在 commit message 中说明原因。

## 数据管道报告规范

所有模块的输出 Excel 必须包含两个 sheet，格式统一：

### 汇总 sheet

单行，涵盖所有状态计数：
```
总行数 | 唯一 SKU 数 | 成功 | 跳过(同SKU) | 无匹配 | 失败 | 处理时间
```

### 明细 sheet

每行一条记录，必有列：
```
序号 | SKU/文件名 | 数据来源 | 处理结果 | 状态 | 备注/失败原因
```

### 数量可追溯（推荐）

报告中的数据流必须可对账：
```
入 N 行 → （匹配 M 行 + 无匹配 K 行 + 跳过 J 行 + 失败 F 行）→ 出 M 行
N = M + K + J + F（如有差数，在备注中解释）
```

### 未匹配记录（推荐）

被过滤/跳过的行不丢弃，保留在明细 sheet 中并标记状态和原因。例如：
- `状态="无匹配"，备注="ERPNext 中未找到 custom_model_id=KS0001 的 Item Group"`
- `状态="跳过"，备注="同 SPU 已在前面行处理"`

> 目前各模块实现程度不同（stock_init 和 warehouse_restock 最完整），新增模块按此标准。

## 先搜再造 — 三层搜索

接到任务后，按顺序搜索，不跳过：

1. **搜项目内**：AGENTS.md 模块索引 → 定位模块 → 读 AGENT_HANDOFF.md → 复用已有函数/API/模式
2. **搜网上**：GitHub 搜索成熟项目 / 开源库 / 用户评价 / 最佳实践 / 类似方案的踩坑记录。Web UI 类任务尤其重要（先找 FilePond/SortableJS 而非从零写拖拽）
3. **自己造**：确认前两层没有成熟方案后，才从零实现。并在 commit message 中说明为什么没复用

## 经验教训索引

所有经验教训已按主题分散到各子模块 AGENT_HANDOFF.md 中，AGENTS.md 本身保留关键几条：

- **通用编码陷阱** (Lesson 1-4)：见 AGENTS.md Karpathy 守则
- **EN_API 踩坑** (Lesson 17-21, 56-59)：见 EN_API/AGENT_HANDOFF.md
- **赛狐平台踩坑** (Lesson 23-53)：见各模块 AGENT_HANDOFF.md（warehouse_restock, other_outbound 等）
- **开发环境** (Lesson 8, 22, 54, 55, 57, 58)：见本文档各节
- **MCP 工具配置** (Lesson 61)：FAC MCP 部署（OAuth + mcp-remote 桥接），见 [docs/fac-mcp-setup.md](fac-mcp-setup.md)
