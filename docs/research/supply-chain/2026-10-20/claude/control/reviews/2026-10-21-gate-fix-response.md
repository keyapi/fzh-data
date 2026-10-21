---
okf: v0.1
type: Review-Response
title: 生产只读闸门复审 FAIL 返修说明
date: 2026-10-21
reviewer_target: codex
reviewed_commit: be37645b
verdict_before: fail
---

# 生产只读闸门复审 FAIL 返修

针对 `2026-10-21-gate-review-fail.md` 的 7 类问题逐项返修。**未访问生产**，
全部验证为离线 mock；父版本对照只读本地 git 历史。

## 逐项关闭

| # | 复审问题 | 修复 |
|---|---|---|
| 1 | P:534 自动重定向绕过计数 | `requests.get(..., allow_redirects=False)`；3xx 不读体、不跟随，`reason=redirect` 立即停并持久化 |
| 2 | P:149/486 先读后裁；T:196 实读 16 记 10；P:135 无界解压 | 每次 read 前用 `min(CHUNK, max_bytes-used_bytes)` 作为 `amt`；解压 `max_length=remaining+1`；解压额度满时下一次请求前拒绝（见 `test_read_amount_never_exceeds_remaining` / `test_decoded_budget_reached_refuses_next_request`） |
| 3 | P:534 超时未绑定剩余墙钟；阻塞读不可中断；空响应越时成功 | 每请求 `timeout=min(config, remaining_seconds)`；读前/读后检查截止；`threading.Timer(remaining)` 到点关闭响应中断阻塞读；空响应读完后再判截止（见 `test_timeout_is_bounded_by_remaining_wall_clock` / `test_empty_response_past_deadline_does_not_succeed`） |
| 4 | P:413 不查停止；403 后再 fetch 仍发请求；P:242 续跑清停止 | `_preflight` 先判 `exhausted`；`_load` 保留 `exhausted/stop_reason`，续跑不清除；要重置必须人工轮换账本（见 `test_403_then_fetch_never_sends` / `test_stop_is_persistent_across_processes`） |
| 5 | P:424 仅内存预占；P:264 无互斥；尾恢复不补耗时 | 发请求前持久写 `pending`（请求/最后请求时刻/timeout）；读流每块 checkpoint；`<ledger>.lock` OS 独占锁；崩溃按“最后分块 + 一个 in-flight 块上界 + timeout 上界”保守恢复；尾恢复补 `cum_seconds`（见 `test_crash_mid_request_is_counted_and_recovered_conservatively` / `test_exclusive_run_lock_rejects_second_live_budget` / `test_tail_recovery_restores_elapsed_seconds`） |
| 6 | P:206 续跑重置间隔；P:711 交错上下文串预算 | `last_request_epoch` 落盘，续跑不足一个间隔则重新等满；`iss_budget` 进程内禁止同一 module / 同一 budget 的重叠上下文，退出时校验补丁归属（见 `test_min_interval_survives_resume` / `test_overlapping_iss_contexts_are_forbidden`） |
| 7 | T:485 只验字段集合 | 新增 `ParentVersionParityTests`：用 `git show be37645b^:` 取父版本，固定 `datetime` 后分别运行，对 DN 四个产物与 EN 输出做逐字节比较 |

## 验证

- `uv run python -m unittest test_prod_budget -v`：**40/40 通过**。
- `uv run python -m unittest discover -p 'test_*.py'`（g1_contract）：**190/190 通过**。
- 父版本对照：DN `association_manifest.json` / `line_dispositions.jsonl` /
  `snapshots_manifest.json` / `run.log` 与 EN 输出均 `bytes` 相等。
- 全部 HTTP 走 `FakeHTTP`/`FakeResponse`；0 生产请求。

## 残余风险

- 单次阻塞读在 watchdog 关闭后仍可能多阻塞一个请求超时；不会把超时记成成功。
- 无 `Content-Length` 的 chunked 响应恰好用满字节额度时保守判 `oversized`。
- br/zstd 无内置解码器；`Accept-Encoding` 只请求 gzip/deflate。
- 停止状态持久化意味着换更大额度续跑前必须人工轮换账本（刻意设计，非缺陷）。
