---
okf: v0.1
type: Review-Response
title: 生产只读闸门第三次复审 FAIL 返修说明
date: 2026-10-22
reviewer_target: codex
reviewed_commit: 5300a6b0
verdict_before: fail-2
---

# 生产只读闸门第三次复审 FAIL 返修

针对 `2026-10-22-gate-review3.md` 的两个阻断反例逐项返修。
**未访问生产**；全部验证为离线 mock，封网守卫保证 0 请求。

## 反例 ↔ 修复 ↔ 回归用例

| # | 复审反例（P=`prod_budget.py`） | 根因 | 修复 | 回归用例（`test_prod_budget.py`） |
|---|---|---|---|---|
| ① | P:1026 取消后直接丢弃已读块；实测截止后实读 16 字节、账本仍为 0 | 阻塞读返回后才检查取消；丢弃块时该次读取的字节既没结算也没预占，账本无从体现 | **在途读取预占**：每次阻塞读**之前**在 `_io_lock` 内预占 `min(CHUNK, 剩余字节)` 的 wire 与解压后额度（`_reserve_read`）。正常返回结算为实际字节；EOF 结算为 0；读流异常（未交付块）释放预占；**取消时工作线程不再改账本，预占作为保守上界保留**，主线程快照取 `call.wire + call.reservation.wire`，日志 `bytes` 与账本 `used.bytes/cum_bytes` 同步一致（`_release_reservation` 只在已结算路径调用，绝不清理未结算字节） | `test_blocking_body_read_is_cut_off`（原零字节断言改为预占上界） / `test_cancelled_inflight_read_keeps_reserved_quota`（1000 字节预占跨 close/续跑仍保留且对账通过） / `test_completed_read_settles_reservation_to_actual_bytes`（正常完成不长期占额度） / `test_inflight_read_error_releases_reservation_and_reconciles`（读超时释放预占、仍可重试、对账通过） |
| ② | P:1138 调用方在截止返回路径同步 `close()`，仍可阻塞；80ms 预算实测 437ms 才返回 | 主线程到点后直接调用 `hold.close()`；关连接/排空缓冲可能同步阻塞，超出预算 | **关闭移出截止返回路径**：主线程只置取消标记、在锁内取（含预占的）字节快照后立刻返回，**不再调用任何 `close()`**；响应由被放弃的工作线程在自己的 `finally` 关闭。线程是 daemon，socket 超时已绑定剩余墙钟，是有界收敛。**若要求网络活动也硬停，应使用可终止的进程边界**（本模块不提供） | `test_deadline_return_never_calls_blocking_close`（close 阻塞 1 秒；80ms 预算下主线程 <0.6s 返回、`closed_by == []`，释放后仅工作线程调用 close） |

## 附带修正

- **读流异常与预占的交互**：`raw.read()` 抛 `RequestException/OSError` 时该次读
  未交付任何块，属“已结算”而非“取消后未结算”，释放其预占；否则一次瞬时
  读超时就会把剩余字节额度一次记满，重试策略失效。
- 删除已无用途的 `_Attempt.hold`（主线程不再读取/关闭响应）。
- `prod_budget.md` / `g1_contract/index.md` 同步：新增在途预占、截止路径不
  close、读流异常释放预占三条口径；测试计数 59→63、全离线 235→240。

## 验证

- `uv run python -m unittest test_prod_budget -v`：**63/63 通过**（新增 4 条）。
- `uv run python -m unittest discover -p 'test_*.py'`（g1_contract）：**240/240 通过**。
- 父版本逐字节对照（DN 四个产物 + EN 输出）继续通过；离线默认语义未变。
- 全部 HTTP 走 `FakeHTTP`/`FakeResponse`；离线套件对生产的请求数 **0**。

## 残余风险

1. **被放弃的工作线程仍不能强杀**：主线程到点立即返回（不再 close），响应由
   工作线程 `finally` 关闭；若 read 阻塞且 socket 超时较大，线程可再存活一个
   socket 超时周期。它是 daemon，且取消后不写账本；要硬停网络活动只能用进程边界。
2. **取消时的字节数是保守上界**：在途读取按“本次额度”入账（无字节上限时即
   `CHUNK`），可能高于实际已读字节；闸门已停机，不影响后续请求计数，
   但账本 `bytes` 是该次尝试的上界而非精确值。
3. `HH:MM` 截止按本机当天解析；跨零点运行应改用带日期的 ISO 8601。
4. 无 `Content-Length` 的 chunked 响应恰好用满额度时仍保守判 `oversized`。
5. `Retry-After` / `Content-Encoding` 的头部查找对大小写敏感（沿袭旧实现），
   不影响安全边界（仍受请求数与墙钟约束）。
