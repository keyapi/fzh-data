---
okf: v0.1
type: Log
title: intent_router 变更日志
---
# 变更日志

## 2026-09-21

- **初始化模块**: 建立 `intent_router/` —— 用 TypeSafe Jev / System One 把中文请求路由到本仓库
  本仓库各业务模块。动机：触发词匹配是关键词而非语义，`item-cost`/`stock-init`/`warehouse-restock`
  同吃 EN BOM 成本，触发词天然分不开。
- **契约探针先行**: 实现前先用 2 选项 payload 打了一发真实请求，确认 criteria 的 object 形式被接受
  （HTTP 200，无 422），并确认 `noul` 答案的键名。避开了计划里标为「首要风险」的一项。
- **确定目录真源**: 实测自动派生不可行（`.agents/skills/` 的目录数比 AGENTS.md 模块索引表多十几个、
  触发信息三种形状；目录多对一），改为人工策展 `catalog.yaml` + 集合相等测试卡漂移。
- **修复 YAML 标量强制转换**: `examples` 里裸写的 `401` 被 YAML 解析成 int，导致 string 形式
  criteria 渲染崩溃。数据加引号 + 渲染层显式 `str()`，并加回归测试。
- **修复 .env 的 worktree 陷阱**: 本仓库既有三个加载器都假设仓库根 = `parents[1]`，在 worktree 里
  取不到父仓库 `.env`。改为有界上溯（实测命中 `parents[4]`）。
- **实测发现（写入 README/AGENT_HANDOFF）**:
  - `confidence` 在本目录上**恒为 1.00**（含 `none` 胜出时），`--min-confidence` 实际不触发；
    真正兜底的是 `none` 选项（模糊请求与域外请求均正确落 `none`）。
  - `ambiguity` 只跨 0.87–0.98，清晰请求 0.95 与域外请求 0.96 几乎重叠，**不具区分度**，
    方向正确但不可用作闸门 → 只在「无法判定」分支显示，避免命中时误导。
  - 因此默认**总是**打印 top-3 候选，并滤掉概率 < 0.005 的填充项。
- **验证**: 离线 176 项通过（12 项 live 默认 skip）；真实调用 10 条标注样例 10/10 命中，
  模糊/域外请求均落 `none`；错误路径 401 不重试、缺凭证退出 1、`--json` 可解析。
