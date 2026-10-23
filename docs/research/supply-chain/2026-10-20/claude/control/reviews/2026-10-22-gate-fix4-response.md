---
okf: v0.1
type: Review-Response
title: 生产只读闸门第四次复审阻断返修说明（读流异常保留预占）
date: 2026-10-22
reviewer_target: codex
reviewed_commit: 1fd196c8
verdict_before: fail-1
---

# 生产只读闸门第四次复审阻断返修

针对 Codex 复审 `1fd196c8` 的唯一阻断：`prod_budget.py:1157-1164` 在读流异常时
整笔释放预占。**未访问生产**；全部验证为离线 mock，封网守卫保证 0 请求。

## 复审反例 ↔ 根因 ↔ 修复

| 项 | 复审反例（P=`prod_budget.py`） | 根因 | 修复 |
|---|---|---|---|
| 读流异常释放预占 | P:1157-1164：真实 http.client/urllib3 场景下 `read()` 已从 socket 读走 16 字节后抛超时 → 账本/日志 0、`pending` 清空、续跑仍 0 | 代码假设“异常 = 未交付任何块 = 未消耗任何字节”。但 http.client/urllib3 会先把数据读进缓冲区、再在等剩余数据时抛超时；这些字节已从 socket 消耗，调用方却拿不到任何块，异常本身也无法证明未消耗 | 异常路径与取消路径同口径：**保留预占**，把它并入 `_Body` 的 `wire/decoded` 计数并同步 `_Attempt`，日志 `bytes`、账本 `used.bytes/cum_bytes`、重试与续跑口径一致。只有 EOF（能证明本次读未消耗）才释放预占。 |

## 回归用例（`test_prod_budget.py`）

| 用例 | 覆盖 |
|---|---|
| `test_partial_read_then_timeout_keeps_reserved_bytes_across_retry_and_resume` | `PartialThenTimeoutRaw` 复现“已从 socket 读走 16 字节后抛超时、交付 0 字节”：第 1 次尝试记 `read_error` 且 `bytes=CHUNK`（不是 0）→ 第 2 次尝试成功；账本 = 预占 + 实际字节，日志与账本对账通过、`pending=None`；新进程续跑从非零字节继续，再取一页仍对账（原反例：续跑仍 0）。 |
| `test_partial_read_timeout_never_undercounts_capped_byte_budget` | 有 `max_bytes` 上限时同样不得清零：预占 = `min(CHUNK, 剩余)` = 1000，保留后用尽预算 → 下一次请求前拒绝（`reason=bytes`），账本/日志均为 1000，续跑维持持久停。宁可保守停，不可少记。 |

删除原 `test_inflight_read_error_releases_reservation_and_reconciles`（它固化的是被
复审否决的“释放”口径）。

## 验证

- `uv run python -m unittest test_prod_budget -v`：**64/64 通过**（净增 1 条）。
- `uv run python -m unittest discover -p 'test_*.py'`（g1_contract）：**241/241 通过**。
- 父版本逐字节对照（DN 四个产物 + EN 输出）继续通过；离线默认语义未变。
- 全部 HTTP 走 `FakeHTTP`/`FakeResponse`；离线套件对生产的请求数 **0**。

## 残余风险

1. **异常时字节数是保守上界**：无法知道 urllib3/http.client 实际读走多少字节，
   按本次预占（≤`CHUNK`，且不越过剩余字节预算）记账，可能多记。正常 MiB 级预算
   下影响可忽略；字节预算小于一个 `CHUNK` 时，一次瞬时读超时即用尽预算并持久停
   （`reason=bytes`）。这是刻意取舍：少记已消耗字节会导致预算泄漏与续跑失真。
2. 被放弃的工作线程仍不能强杀（沿用上轮结论）：主线程到点立即返回，不调用
   `close()`；线程以 socket 超时为有界收敛，取消后不写账本。
3. `HH:MM` 截止按本机当天解析；跨零点运行应改用带日期的 ISO 8601。
