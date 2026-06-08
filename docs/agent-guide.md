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

## 经验教训索引

所有经验教训已按主题分散到各子模块 AGENT_HANDOFF.md 中，AGENTS.md 本身保留关键几条：

- **通用编码陷阱** (Lesson 1-4)：见 AGENTS.md Karpathy 守则
- **EN_API 踩坑** (Lesson 17-21, 56-59)：见 EN_API/AGENT_HANDOFF.md
- **赛狐平台踩坑** (Lesson 23-53)：见各模块 AGENT_HANDOFF.md（warehouse_restock, other_outbound 等）
- **开发环境** (Lesson 8, 22, 54, 55, 57, 58)：见本文档各节
