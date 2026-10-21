---
okf: v0.1
type: Reference
title: 生产只读统一预算闸门（prod_budget.py）
description: 两取数工具共用的 requests / 响应字节 / 墙钟预算、跨进程账本、日志对账与停止规则
date: 2026-10-21
module: supply-chain-integration
tags: [supply-chain, production-readonly, budget, gate, safety]
---

# 生产只读统一预算闸门

实现任务书 `control/reviews/2026-10-21-gate-task.md`；原始批准与先决条件见
`control/reviews/2026-10-21-decision3-production-gate.md`。

**本模块只做闸门，不授权生产访问。** 未获用户对范围/额度的授权前，只能用离线 mock 验证。

## 文件

| 文件 | 作用 |
|---|---|
| `prod_budget.py` | `ProductionBudget` / `BudgetExhausted` / `iss_budget()`；唯一 HTTP 出口 |
| `test_prod_budget.py` | 26 条离线单测（零预算、边界、超大响应、超时、429、续跑、对账、工具接入） |
| `g1b_en_extract.py` | 所有分页/逐单 GET 经 `iss_budget` 接入同一账本 |
| `g1b_dn_wo_jc_se.py` | SE 明细补齐、WO 探针、翻页与重试经同一账本 |

## CLI（两工具同名同义）

```bash
--max-requests N        # 请求数上限（含重试/429/翻页；dn 工具缺省沿用 --max-http）
--max-mib M             # 响应传输字节上限（MiB；同一上限也约束解压后字节）
--max-minutes T         # 跨进程累计墙钟上限（分钟）
--budget-file PATH      # 账本 JSON；日志为同名 .log（缺省 out-dir/prod_budget.json）
--min-interval S        # 请求最小间隔秒；闸门模式缺省 1.0，显式 0 才关闭
```

任一参数出现即启用闸门；**一个都不传 → 旧行为不变**（`g1b_dn_wo_jc_se.py` 仍只有
`--max-http` 请求计数，`g1b_en_extract.py` 仍无预算）。

示例（决策 2 的补 SE 阶段额度）：

```bash
uv run python g1b_dn_wo_jc_se.py --snapshot out/g1b_en_top_1.json \
  --enrich-se --max-requests 300 --max-mib 32 --max-minutes 15 \
  --budget-file out/budget/se_fill.json
```

## 停止规则

| 情况 | 行为 |
|---|---|
| 请求数 / 字节 / 墙钟任一用满 | 下一次请求**发请求前**拒绝（`reason=requests/bytes/seconds`）；拒绝不产生 HTTP |
| 响应中途超出剩余字节 | 流式读到剩余上限即停，累计字节不越界（`status=oversized`） |
| 单请求超时 | 计入请求数与失败；连续 3 次网络错误/5xx 立即停 |
| 429 | 遵守 `Retry-After`（秒数或 HTTP-date），最多重试 2 次；仍 429 → `retry_exhausted` |
| 401 / 403 | 立即停（`reason=auth`），不重试 |
| 账本与日志不一致 | 启动即拒绝续跑（`BudgetLedgerError`），不静默重置 |

停止后 `manifest.run_status` 为 `partial_http_budget_exhausted`（请求耗尽）或
`partial_http_budget_<reason>`；工具退出码 1。证据里保留 `stop_reason`、`not_requested`。

## 账本与日志

- 账本是 JSON（schema `prod_budget/1`）：累计 `requests / bytes / decoded_bytes / seconds`、
  `by_kind`、`refused`、`stop_reason`、`runs`。每次请求后 `os.replace` 原子写回；
  启动时读取并与日志对账，续跑不重置。
- `prod_budget.log` 每行一个 JSON（schema `prod_budget_log/1`），每**实际 HTTP 尝试**一行：
  `seq / kind / status / bytes / decoded_bytes / cum_requests / cum_bytes /
  cum_decoded / cum_seconds / elapsed_ms / attempt`。
- 对账口径：日志行数 == 账本 `requests`，日志 `bytes` 之和 == 账本 `bytes`。
- 崩溃恢复：日志先写、账本后写；若崩溃发生在两者之间（日志最多领先一行），
  启动时按最后一行累计值补齐账本；其余不一致一律拒绝续跑。

## 离线验证

```bash
uv run python -m unittest discover -p 'test_*.py'   # 176 条全离线
```

全部 HTTP 用 mock（`FakeResponse` / `FakeHTTP`），不访问生产、不读生产凭证。
