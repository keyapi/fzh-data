---
okf: v0.1
type: Reference
title: Tool / Skill / 模型约定
tags: [reference, sellfox, open-webui]
timestamp: 2026-07-24
resource: ai_access_poc/open_webui/tools/sellfox_pull_sp_search_term.py
---

# Tool / Skill / 模型

## Tool：`sellfox_sp_search_term_pull`

源码：`open_webui/tools/sellfox_pull_sp_search_term.py`（v0.3+）

| 方法 | 作用 |
|------|------|
| `sellfox_list_shops` | 列店铺 |
| `sellfox_pull_sp_search_term` | createTask → 下载 xlsx → **summary JSON** |
| `sellfox_summarize_search_term_xlsx` | 对已有路径再摘要 |

Valves 关键：`REPORT_DIR=/data/sellfox_reports`，`SUMMARY_TOP_N`，代理/直连凭证。

## Skill：`sellfox-search-term-pull`

文件：`open_webui/skills/sellfox-search-term-pull.md`  
聊天触发：`$赛狐搜索词拉取` 或绑到模型。强制：用 summary、禁止自动否词。

## 自定义模型：`fzh-sellfox-ops`

- 显示名：FZH 赛狐只读分析 (DeepSeek Flash)  
- `meta.toolIds`: `sellfox_sp_search_term_pull`  
- `meta.skillIds`: `sellfox-search-term-pull`  
- `params.function_calling`: `native`  
- 默认 `capabilities.code_interpreter: false`（偏 Terminal）
