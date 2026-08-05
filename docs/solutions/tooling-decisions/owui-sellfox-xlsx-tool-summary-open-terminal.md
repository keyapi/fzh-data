---
module: ai_access_poc
date: 2026-07-24
problem_type: tooling_decision
component: tooling
severity: high
tags:
  - open-webui
  - sellfox
  - code-interpreter
  - open-terminal
  - xlsx
  - pyodide
applies_when:
  - building or operating the Open WebUI shell PoC for Sellfox read-only reports
  - chat models claim they cannot read xlsx or fail to analyze search-term downloads
  - choosing between Code Interpreter (Pyodide) and Open Terminal for analysis
related_components:
  - documentation
  - development_workflow
---

# OWUI 壳：赛狐 xlsx 分析靠 Tool JSON summary + Docker Open Terminal

## Context

C′ 壳 PoC（`ai_access_poc/open_webui/`，实施中见 PR #113）要让运营在浏览器里：拉指定店铺近 N 天 SP 搜索词报告 → 落盘 → 做只读分析。实测中模型常说「读不了 xlsx」；若只开 Code Interpreter（Pyodide）又摸不到容器内 `/data/sellfox_reports`，且官方已将 Pyodide/Jupyter 标为 legacy。

## Guidance

1. **Tool 必须返回可分析文本**，不要指望聊天模型直接读二进制 xlsx。`sellfox_pull_sp_search_term` 在下载后调用 `_summarize_search_term_xlsx`，返回 `summary.totals` 与 `summary.top_by_spend_csv`（见 `ai_access_poc/open_webui/tools/sellfox_pull_sp_search_term.py`）。已有文件用 `sellfox_summarize_search_term_xlsx`。
2. **深挖默认走 Open Terminal（Docker only）**，挂载 `./reports` → `/data/sellfox_reports`。官方 slim 镜像有 openpyxl、**无 pandas / 无 pip**；解析赛狐导出时 **不要** `load_workbook(..., read_only=True)`（会只看到残缺列）。
3. **Code Interpreter（引擎 pyodide）是 legacy 路径**：Admin 可开，但与 Open Terminal **同一会话互斥**。真执行在浏览器 UI；`/api/chat/completions` 往往只让模型贴代码、不跑 Pyodide。适合贴 CSV 小算盘，不适合读容器卷上的 xlsx。
4. **模型绑定**：自定义模型（如 `fzh-sellfox-ops`）默认挂 Tool+Skill，`function_calling=native`；裸基座模型需手动勾 Available Tools。
5. **只读**：禁止自动否词/改价；结论标明只读建议。赛狐广告写 API 未上线前不做写。

## Why This Matters

- 不返回 summary → 运营以为「AI 不会分析报告」，壳 PoC 验收假失败。
- 误选 Pyodide 当主路径 → 无法复用 Docker 卷、包能力弱、与 Terminal 抢开关，和官方推荐方向相反。
- Terminal slim + 错误 openpyxl 模式 → 「容器里也读不了表」，浪费排障时间。

## When to Apply

- 维护 `ai_access_poc/open_webui` Tool / Skill / compose
- 教运营：选「FZH 赛狐只读分析」模型 → 优先 summary；要分组过滤时开 ☁ Terminal，不要同时开 CI
- 写第二期板 PoC / Portal 时，复用「拉数 Tool 出文本摘要 + 沙箱深挖」分工，不要为每个分析步骤造一个 Tool

## Examples

**拉数后 Tool JSON（概念形状）**

```json
{
  "ok": true,
  "filepath": "/data/sellfox_reports/SearchTerm_....xlsx",
  "summary": {
    "totals": {"rows": 1922, "spend": 1663.32, "sales": 4697.22, "acos": 0.3541},
    "top_by_spend_csv": "search_term,spend,sales,orders,..."
  }
}
```

**验收对照（本机实测，TOODDLY-Daneey-US 近 7 天）**

| 路径 | 结果 |
|------|------|
| Tool summary | 1922 行；spend/sales/ACOS 如上 |
| Open Terminal + openpyxl | 浪费词 Top3 与高效词 Top3 可复现 |
| 浏览器 CI + 粘贴 CSV | `execute_code` 跑通，数字与 Terminal 对账；**不能**直读容器 xlsx |

**反例**：仅改 `.env` 里的 `OPENAI_API_KEY`，而首次启动曾写入 `sk-replace-me` → 须在 Admin → Connections 改 DB 内 Key。

## Related

- 计划：`docs/research/2026-07-24-unified-ai-access-poc-plan.md`（壳 S1–S4）
- 子项目：`ai_access_poc/open_webui/AGENT_HANDOFF.md`、`ai_access_poc/docs/`
- 调研结论（选型，非本运行模式）：`docs/solutions/integration-issues/fzh-unified-ai-access-conclusion.md`
- PR：[#113](https://github.com/keyapi/fzh-data/pull/113)（壳实现，收口时更新）
