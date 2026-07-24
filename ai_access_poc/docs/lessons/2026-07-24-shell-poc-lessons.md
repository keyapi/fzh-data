---
okf: v0.1
type: Lesson
title: 壳 PoC 经验教训（2026-07-24）
description: Open WebUI + 赛狐只读 Tool + Open Terminal / CI 实测坑点
tags: [lesson, open-webui, sellfox, pyodide]
timestamp: 2026-07-24
resource: ai_access_poc/open_webui/
---

# 壳 PoC 经验教训

## 1. HF / 嵌入卡住导致 unhealthy

国内拉 `sentence-transformers` 常卡 0%。compose 默认 `HF_ENDPOINT=https://hf-mirror.com` 且 `RAG_EMBEDDING_ENGINE=openai`（RAG 非关键路径）。

## 2. 占位 API Key 写入 OWUI DB

首次用 `sk-replace-me` 启动后，只改 `.env` 不够 → Admin → Connections 改真实 Token。

## 3. 模型读不了 xlsx ≠ 分析失败

LLM 不能读二进制。Tool 必须返回 `summary.totals` / `top_by_spend_csv`；Skill 禁止助手声称「无法读 xlsx」。

## 4. Open Terminal slim 包能力

有 openpyxl、无 pandas、无 pip。深挖用 openpyxl + stdlib。赛狐 xlsx：**禁止** `read_only=True`（列会坏）。

## 5. CI（Pyodide）vs Open Terminal

- 官方：Open Terminal = 推荐；Pyodide/Jupyter = legacy  
- 同聊互斥  
- CI 真跑在浏览器；API completions 常只出代码  
- CI 适合贴 CSV；读 `/data/sellfox_reports` 用 Terminal  

## 6. Tool 要绑模型

裸基座不会自动带 Tool。用 `fzh-sellfox-ops` 或 Workspace → Models 勾选。

## 7. 赛狐访问优先代理

`SELLFOX_PROXY_API_KEY` → `api.vilavi.cn/sellfox`；直连仅白名单 IP。client 需限流重试。

## 8. 只读边界

无广告写 API → 任何「否词/改价」只能是建议；PoC 禁止执行写。
