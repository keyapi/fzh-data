---
name: intent-router
description: >
  中文意图 → 本仓库模块路由。用 TypeSafe Jev / System One 判断一句中文需求属于
  本仓库哪个业务模块，输出模块名 + 目录 + 置信度；置信度不足或与任何模块都不匹配时
  明确回「无法判定，需人工/澄清」，不猜。
  当用户提到「该用哪个模块」「这是哪个 skill 的活」「帮我找模块」「意图分类」「路由到哪个模块」
  「intent router」「TypeSafe」「Jev」时触发。不要用于执行具体业务动作 —— 本模块只分类，
  动作交回对应模块自己的流程（如通途/赛狐/浏览器任务仍必须走 web_automation/scripts/dispatch.py）。
metadata:
  module: intent_router
  docs: intent_router/docs/reference/typesafe-contract.md
  updated: 2026-09-21
---

# 中文意图 → 本仓库模块路由

入口：`intent_router/AGENT_HANDOFF.md`；契约与实测行为：`intent_router/docs/reference/typesafe-contract.md`。

## 必须先做

1. 读 `intent_router/AGENT_HANDOFF.md`（函数表 + 边界条件）。
2. **worktree 里不要 `uv run`**（会另建 `.venv`）—— 用父仓库解释器 + `PYTHONPATH` 指向 worktree 根。
3. 凭证 `TYPESAFE_API_KEY` 在**父仓库** `D:\Work\赛狐\Cursor\.env`（worktree 内没有 `.env`）。

## 用法

| 目的 | 命令 |
|------|------|
| 路由一句中文请求 | `uv run python -m intent_router.cli route "<请求>"` |
| 看候选分布 | `uv run python -m intent_router.cli route "<请求>" --show-candidates` |
| 给脚本用 | `uv run python -m intent_router.cli route "<请求>" --json` |
| 核对目录 | `uv run python -m intent_router.cli catalog` |
| 查与 AGENTS.md 的漂移 | `python -m intent_router.catalog` |

退出码：`0` 命中 · `1` 缺凭证 · `2` API 错误 · `3` 需人工介入。

## 铁律

- **只分类，不执行**：本模块给模块名，不跑任何业务动作。
- **不冒充 dispatch.py**：退出码复用，但状态词表独立；通途/赛狐/浏览器任务仍由
  `web_automation/scripts/dispatch.py` 定状态。条目带 `web_task` 时只打印 dispatch 命令。
- **`confidence` 在本目录上恒为 1.00**（实测），`--min-confidence` 实际不触发；
  真正兜底的是 `none` 选项。别把高置信度读成"一定对"。
- **`歧义度` 不可用作闸门**：实测只跨 0.87–0.98，不具区分度，仅在「无法判定」分支显示。
- 改模块时必须**同时**改 `AGENTS.md` 模块索引表 + `intent_router/catalog.yaml` +
  本 skill 目录，否则 `tests/test_catalog.py` 的集合相等断言会红。

## 相关经验（docs/solutions）

踩过的坑与设计取舍，动手前先读：

- `docs/solutions/tooling-decisions/typesafe-jev-intent-router.md` —— 中文意图路由（intent_router）—— TypeSafe Jev + 置信度闸门
