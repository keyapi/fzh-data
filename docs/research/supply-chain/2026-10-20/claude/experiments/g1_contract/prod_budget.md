---
okf: v0.1
type: Reference
title: 生产只读统一预算闸门（prod_budget.py）
description: 两取数工具共用的 requests / 响应字节 / 墙钟预算、跨进程账本、日志对账、持久锁停与崩溃恢复
date: 2026-10-21
module: supply-chain-integration
tags: [supply-chain, production-readonly, budget, gate, safety]
---

# 生产只读统一预算闸门

实现任务书 `control/reviews/2026-10-21-gate-task.md`；原始批准与先决条件见
`control/reviews/2026-10-21-decision3-production-gate.md`；复审 FAIL 与逐项修复见
`control/reviews/2026-10-21-gate-review-fail.md`、`2026-10-21-gate-fix-response.md`、
`2026-10-21-gate-review2-fail.md`、`2026-10-22-gate-fix2-response.md`、
`2026-10-22-gate-review3.md`、`2026-10-22-gate-fix3-response.md`、
`2026-10-22-gate-fix4-response.md`。

**本模块只做闸门，不授权生产访问。** 未获用户对范围/额度的授权前，只能用离线 mock 验证。

## 文件

| 文件 | 作用 |
|---|---|
| `prod_budget.py` | `ProductionBudget` / `BudgetExhausted` / `BudgetLedgerError` / `BudgetContextError` / `iss_budget()`；唯一 HTTP 出口 |
| `test_prod_budget.py` | 64 条离线单测（含三轮复审全部反例、隐式预读复现、在途读取预占、读流异常保留预占与截止返回路径不阻塞、父版本逐字节对照） |
| `g1b_en_extract.py` | 所有分页/逐单 GET 经 `iss_budget` 接入同一账本 |
| `g1b_dn_wo_jc_se.py` | SE 明细补齐、WO 探针、翻页与重试经同一账本 |

## CLI（两工具同名同义）

```bash
--max-requests N        # 请求数上限（含重试/429/翻页；dn 工具缺省沿用 --max-http）
--max-mib M             # 响应传输字节上限（MiB；同一上限也约束解压后字节）
--max-minutes T         # 跨进程累计墙钟上限（分钟）
--deadline HH:MM        # 绝对截止时刻（本机时区当天；也收 ISO 8601），与 --max-minutes 取更早者
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
| 请求数 / 字节 / 解压后字节 / 墙钟 / 绝对截止任一用满 | 下一次请求**发请求前**拒绝（`reason=requests/bytes/seconds`）；拒绝不产生 HTTP |
| 响应中途超出剩余字节 | **按剩余额度读**（`read(min(CHUNK, remaining))`），累计字节不越界（`status=oversized`） |
| 解压后字节到达上限 | 解压 `max_length=remaining+1` 硬限；下一次请求前拒绝（不会先解压再裁） |
| 3xx 重定向 | `allow_redirects=False`，不跟随；`reason=redirect` 立即停（跳转不能绕过计数/间隔） |
| 隐式预读 | 会话强制 `stream=True` 且 **`resolve_redirects` 直接返回空**：库既不整包读 `r.content`，也不在禁止跳转时预读跳转体；**每个**响应体（含 3xx/401/403/429）都经 `_read_body` 有界读取并记账 |
| 单请求超时 | 计入请求数与失败；socket 超时绑定**剩余墙钟**（含绝对截止） |
| 等响应头/读体阻塞 | **可中断执行边界**：整次 HTTP 在工作线程里，主线程只等到截止；到点放弃本次尝试、**立刻返回**（主线程绝不调用可能阻塞的 `close()`），记 `deadline` 并持久停机；响应由被放弃的工作线程在 `finally` 关闭 |
| 取消时已有在途读 | 阻塞读**之前**已预占读取额度（≤CHUNK 且不越字节预算）；取消后工作线程不再结算，预占作为**保守上界留在账本/日志**，绝不清成 0（复审反例：实读 16 字节、账本 0） |
| 读流超时/断连 | 已结算字节保留；**异常无法证明本次阻塞读未消耗**（http.client/urllib3 可能先读走部分字节再抛超时）→ 与取消同口径：预占作为**保守上界**并入 `body` 计数，日志 `bytes`、账本 `cum_bytes` 与续跑一致，绝不归 0。只有 EOF 能证明未消耗，才释放预占 |
| 空响应但已越过墙钟 | 读完后再查截止；`status=deadline`，不返回成功 |
| 429 | 遵守 `Retry-After`（秒数或 HTTP-date），最多重试 2 次；仍 429 → `retry_exhausted` |
| 401 / 403 | 立即停（`reason=auth`），不重试；**终止态与清 pending 一次原子落盘** |
| 账本与日志不一致 | 启动即拒绝续跑（`BudgetLedgerError`），不静默重置 |

**停止是持久的。** 401/403、预算耗尽、重定向等一旦写入账本 `exhausted=true` /
`stop_reason`，续跑（新进程）不会清除；要重新放行必须人工轮换/删除账本文件。
这是复审要求的“持久锁停”，避免 403 后换进程继续打生产。
**终止态先落日志再落账本**：崩溃在两次写之间时，续跑按日志里的 `stop_reason`
重建停机（`_adopt_log_stop`），同样不会放行。

停止后 `manifest.run_status` 为 `partial_http_budget_exhausted`（请求耗尽）或
`partial_http_budget_<reason>`；工具退出码 1。证据里保留 `stop_reason`、`not_requested`。

## 账本、日志与并发

- 账本是 JSON（schema `prod_budget/1`）：累计 `requests / bytes / decoded_bytes / seconds`、
  `by_kind`、`refused`、`stop_reason`、`last_request_epoch`、`pending`、`runs`。
  每次请求（及读流每个分块）后 `os.replace` 原子写回；启动时读取并与日志对账，续跑不重置。
- **发请求前持久预占**：先写 `used.requests+1`、`last_request_epoch` 和
  `pending{seq,kind,path,timeout_seconds,wire_bytes,decoded_bytes,content_encoding}`，
  再发 HTTP。HTTP 途中崩溃时请求不会丢。
- **在途读取预占**：每次阻塞读之前按本次额度（`min(CHUNK, 剩余字节)`）预占 wire
  与解压后字节；正常返回结算为实际字节并释放多余额度，EOF 结算为 0。**取消与
  读流异常都不得清除**：已从 socket 读走但来不及结算/交付的字节按预占上界保留，
  日志 `bytes`、账本 `used.bytes` 与 `cum_bytes` 同步采用该上界，三方仍然对账一致。
  读流异常时预占并入 `body` 计数（因此重试不会把它当 0，续跑也从该上界继续）。
- **独占运行锁**：`<ledger>.lock` 用 OS 文件锁（Windows `msvcrt` / POSIX `flock`），
  进程死亡自动释放；同一账本第二个活进程启动即 `BudgetLedgerError`。
- `prod_budget.log` 每行一个 JSON（schema `prod_budget_log/1`），每**实际 HTTP 尝试**一行：
  `seq / kind / status / bytes / decoded_bytes / cum_requests / cum_bytes /
  cum_decoded / cum_seconds / elapsed_ms / attempt`，终止尝试（404 除外）另带
  `stop_reason`——它是崩溃后重建停止状态的唯一依据。
- 对账口径：日志行数 == 账本 `requests`，日志 `bytes` 之和 == 账本 `bytes`。
- **崩溃恢复**：
  - 日志已写、账本未写（最多领先一行）：按最后一行累计值补齐，**同时恢复 `cum_seconds`
    与 `stop_reason`**。
  - 账本已写、日志未写（HTTP 途中崩溃）：请求已计；字节按“最后分块 + 一个 in-flight
    块上界（压缩响应直接记满解压额度）”补记；耗时按本次请求的 `timeout_seconds`
    上界补记；补一条 `status=recovered_crash` 日志行使对账成立。
  - 若日志里已有该 `seq` 的行（崩溃在日志写后、账本写前），直接采用日志精确值，
    不再加保守上界。
  - 任何一行日志带 `stop_reason` 而账本没有 → 启动即回填停机状态（原子写一次）。
- **最小间隔跨进程**：`last_request_epoch` 落盘；续跑时若距上次请求不足一个间隔
  （含时钟回拨），从当前进程重新等满一个间隔——只会更慢，不会更短。
- **上下文禁止重叠**：进程内同一 `api_get_status` 或同一 budget 只允许一个
  `iss_budget` 上下文；嵌套/交错直接 `BudgetContextError`，避免预算串用与错误还原。

## 离线验证

```bash
uv run python -m unittest test_prod_budget -v        # 64 条（本模块）
uv run python -m unittest discover -p 'test_*.py'    # 241 条全离线
```

全部 HTTP 用 mock（`FakeResponse` / `FakeHTTP`），不访问生产、不读生产凭证。
两个测试模块导入时都调用 `pb.block_default_transport()`：**任何一条测试漏注入
`http_get`，默认传输会立即 `AssertionError`**，不会静默打出真实请求。
`ParentVersionParityTests` 用 `git show be37645b^:` 取父版本源码，固定时钟后分别运行，
对 `association_manifest.json` / `line_dispositions.jsonl` / `snapshots_manifest.json` /
`run.log` 以及 `g1b_en_extract` 输出做**逐字节**比较（不只是字段集合）。

## 已知边界 / 残余风险

1. **被放弃的工作线程不能强杀**：截止到点后主线程立刻返回（不再等任何阻塞读，
   **也不调用可能阻塞的 `close()`**），但 Python 无法终止线程；响应由工作线程
   在自己的 `finally` 关闭，线程最多再阻塞一个 socket 超时
   （已在请求开始时绑定剩余墙钟/绝对截止），随后检查取消标记退出，不写账本。
   等响应头阶段没有可关闭的句柄，socket 超时是它唯一的收敛上界。
   **若要求网络活动也立即硬停，只能用可终止的进程边界**（本模块不提供）。
2. **无 `Content-Length` 的 chunked 响应恰好用满字节额度**：无法无损证明流已结束，
   保守判为 `oversized`（停而不是继续）。这只会在额度刚好用满时发生。
3. **未内置解码器（br/zstd）**：按传输字节计，`Accept-Encoding` 只请求 gzip/deflate，
   EN 实际不会返回 br/zstd；若返回，解压后字节上限无法约束。
4. **坏行/手工改日志**：一律拒绝续跑；不会自动修复。
5. **父版本对照依赖 git 历史**：浅克隆缺 `be37645b^` 时测试直接失败（不静默跳过）。
6. **`HH:MM` 形式的截止按“本机当天”解析**：跨零点运行时应改用 ISO 8601 带日期，
   否则 00:05 会把 23:30 解析成当晚（约 23 小时后），比预期宽松。
   跨天场景一律用 `--deadline 2026-10-22T22:30:00+08:00`。
7. **退出码/清单未新增绝对截止字段**：`as_log()["seconds"]["absolute_deadline"]`
   只在闸门模式出现，离线默认输出（与父版本逐字节对照的部分）不变。
8. **读流异常的预占是保守上界，可能多记**：异常时无法知道 urllib3/http.client
   究竟从 socket 读走多少字节，只能按本次预占（≤`CHUNK`，且不越过剩余字节预算）
   记账。正常 MiB 级预算下影响可忽略；但若字节预算本身小于一个 `CHUNK`，一次瞬时
   读超时就会用尽预算并触发持久停（`reason=bytes`）。这是刻意取舍：**宁可保守停，
   不可少记已消耗字节**（复审反例：实读 16 字节、账本/日志 0、续跑仍 0）。
