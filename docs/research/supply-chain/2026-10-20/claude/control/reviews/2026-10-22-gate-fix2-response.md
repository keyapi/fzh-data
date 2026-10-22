---
okf: v0.1
type: Review-Response
title: 生产只读闸门第二次复审 FAIL 返修说明
date: 2026-10-22
reviewer_target: codex
reviewed_commit: ed6a7742
verdict_before: fail
---

# 生产只读闸门第二次复审 FAIL 返修

针对 `2026-10-21-gate-review2-fail.md` 的 ①②③（④⑤同源）逐项返修。
**未访问生产**；全部验证为离线 mock。父版本对照只读本地 git 历史。

## 反例 ↔ 修复 ↔ 回归用例

| # | 复审反例（P=`prod_budget.py`） | 根因 | 修复 | 回归用例（`test_prod_budget.py`） |
|---|---|---|---|---|
| ① | P:886/912 真实 Requests 在禁止重定向时仍预读跳转体；离线复现读 16 字节、记账 0 | `Session.send` 在 `allow_redirects=False` 时仍 `next(resolve_redirects(..., yield_requests=True))`，而 `resolve_redirects` 循环开头就是 `resp.content`（无长度上限）；另有 `if not stream: r.content` | 新增 `_GateSession`：`send()` 强制 `stream=True`、`allow_redirects=False`，`resolve_redirects()` 直接返回空迭代器；默认出口 `gated_get()`。**所有状态码**（含 3xx/401/403/429）的响应体统一走 `_read_body` 有界读取并记账；`_content_consumed` 为真时抛 `BudgetAccountingError`（兜底哨兵，拒绝在无法记账时继续） | `test_requests_by_itself_prereads_redirect_body`（复现：原生会话 16 字节）/ `test_gate_session_never_prereads`（0 字节）/ `test_gate_session_forces_safe_stream_flags` / `test_redirect_bytes_are_accounted_by_gate` / `test_forbidden_bytes_are_accounted_by_gate` / `test_rate_limited_body_is_accounted` |
| ② | P:886/952 watchdog 在收到响应头后才启动，等头阻塞不可打断；无 22:30 绝对截止 | 截止逻辑在 `get()` 之后才装配（`threading.Timer` 关响应），连接/等头阶段无人看守；`max_seconds` 只有相对量 | **可中断执行边界** `_run_attempt`：整次 HTTP（建连→等头→读体）进工作线程，主线程只等到 `remaining_seconds`；到点置取消标记、取字节快照、关闭已拿到的响应并返回，`fetch` 记 `deadline` 并持久停机。取消标记在每个阻塞调用前后与每次记账前检查，放弃后不再改账本。新增 `deadline=` / `--deadline`（epoch / datetime / `HH:MM` / ISO 8601），与 `--max-minutes` 取更早者，同时绑定 socket 超时 | `test_absolute_deadline_cuts_off_blocking_wait_for_headers` / `test_relative_wall_budget_also_covers_wait_for_headers` / `test_blocking_body_read_is_cut_off` / `test_abandoned_attempt_never_charges_bytes` / `test_absolute_deadline_in_the_past_refuses_before_http` / `test_socket_timeout_is_bound_by_absolute_deadline` / `test_coerce_deadline_forms` / `test_extract_deadline_flag_enables_gate_and_refuses_after_it` |
| ③④⑤ | P:804/924 403 先写日志并清 pending、再持久化停机；其间崩溃可续跑 | 终止态分两次落盘（`_note` 清 pending 一次、`_stop` 写 stop 一次） | `_note(..., stop=...)`：日志行先 fsync（带 `stop_reason`），随后**一次**账本写同时清 `pending` 并写 `stop_reason`/`exhausted`；删除 `_after_failure` 的两段式调用。恢复时 `_adopt_log_stop` 扫描日志把缺失的停机状态回填账本（在任何请求之前的 `__init__` 内完成） | `test_stop_and_pending_clear_land_in_one_ledger_write` / `test_crash_after_log_before_ledger_rebuilds_terminal_stop` / `test_log_tail_stop_is_adopted_when_ledger_lags` / `test_ledger_stop_survives_when_log_has_no_stop_field` |

## 附带修复（不在复审清单内，但属同一安全边界）

- **测试封网**：默认出口改为会话后，`pb.requests.get` 不再是打桩点。返修期间发现
  `test_extract_gate_counts_all_gets` 因补丁失效**真的打到生产**（GET 只读、
  假凭证 → 401，无数据返回）。已把两个测试模块的打桩点改为 `pb.gated_get`，并新增
  `pb.block_default_transport()`：测试模块导入即封死默认传输，任何漏注入 `http_get`
  的用例立即 `AssertionError`。这一条同时消除了"离线套件误发生产请求"的整类风险。
- 保留旧 `HttpBudget` / `as_log()` 离线字段逐字节不变（父版本对照仍通过）。

## 验证

- `uv run python -m unittest test_prod_budget -v`：**59/59 通过**（新增 19 条）。
- `uv run python -m unittest discover -p 'test_*.py'`（g1_contract）：**235/235 通过**。
- 父版本逐字节对照（DN 四个产物 + EN 输出）继续通过；离线默认语义未变。
- 全部 HTTP 走 `FakeHTTP`/`FakeResponse`；离线套件对生产的请求数 **0**（封网守卫）。

## 残余风险

1. 被放弃的工作线程无法强杀：主线程到点立刻返回，但线程最多再阻塞一个 socket 超时
   （已绑定剩余墙钟/绝对截止）后才退出；等头阶段没有可关闭句柄，socket 超时是唯一上界。
2. `HH:MM` 截止按本机当天解析；跨零点运行应改用带日期的 ISO 8601，否则偏宽松。
3. 无 `Content-Length` 的 chunked 响应恰好用满额度时仍保守判 `oversized`。
4. `Retry-After` / `Content-Encoding` 的头部查找对大小写敏感（沿袭旧实现）；
   requests 原样保留服务器头部大小写，小写返回时 429 会退化为默认 1 秒重试。
   不影响安全边界（仍受请求数与墙钟约束），未在本次返修中改动。
