---
okf: v0.1
type: Spec
title: 壳 PoC 验收（S1–S4）
description: 对照统一 AI 接入计划的壳成功标准与实测证据
tags: [spec, acceptance, open-webui, sellfox]
timestamp: 2026-07-24
depends_on:
  - docs/research/2026-07-24-unified-ai-access-poc-plan.md
---

# 壳 PoC 验收

计划要求：浏览器 Chat 触发拉取指定店铺近 N 天 SP 搜索词 → 落盘可下载；Open Terminal **仅 Docker**；凭证走环境变量；报告 gitignore；**无广告写**。

| ID | 任务 | 结果 | 证据 |
|----|------|------|------|
| S1 | compose OWUI + Open Terminal | **Pass** | `docker-compose.yml`；Terminal 无宿主机端口 |
| S2 | api.vilavi.cn 冒烟 | **Pass** | 模型可选；chat 冒烟 pong |
| S3 | sellfox Tool 真拉取 | **Pass** | Tool v0.3 + proxy；xlsx 落 `./reports`；summary JSON |
| S4 | Skill + 试用步骤 | **Pass** | Skill 导入；`fzh-sellfox-ops` 绑定；README 步骤 |

## 超额验证（非计划硬性，但锁定天花板）

| 项 | 结果 |
|----|------|
| Tool summary 驱动分析 | Pass（模型可基于 totals/top CSV 写结论） |
| Open Terminal 深挖 xlsx | Pass（openpyxl；pandas 不可用） |
| Code Interpreter Pyodide | Pass（浏览器 `execute_code`；与 Terminal 互斥；legacy） |

## 样例数据（验收日）

店铺 **TOODDLY-Daneey-US**，近 7 天：rows 1922，spend 1663.32，sales 4697.22，orders 68，ACOS 0.3541。

## 壳判定

**绿** — 计划成功标准已满足。后续主线转为板 PoC，不继续堆壳功能。
