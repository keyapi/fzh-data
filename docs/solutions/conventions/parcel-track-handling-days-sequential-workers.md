---
okf: v0.1
type: Reference
title: parcel_track 处理天数统一 3 个营业日与 per-carrier 顺序并发
date: 2026-09-08
category: conventions
module: parcel_track
problem_type: convention
component: tooling
severity: medium
applies_when:
  - "跑 UPS/FedEx/GLS 混合异常表，或改迟发处理天数"
  - "把某一承运商的假日表或 HANDLING_DAYS 抄到另一家"
  - "把 --workers N 理解成三家物流商合计并发"
  - "整月通途非FBA订单 live 查询（不要 --mock / --limit）"
tags:
  - "parcel-track"
  - "handling-days"
  - "amazon-business-days"
  - "sequential-workers"
  - "ups"
  - "fedex"
  - "gls"
  - "ops-report"
---

# parcel_track 处理天数统一 3 个营业日与 per-carrier 顺序并发

## Context

运营要把 UPS / FedEx / GLS 三条自发货尾程的**迟发处理时间**拉到同一把尺子：一律 **3 个营业日**，再用通途整月非 FBA 订单做混合全量跑。混合入口 `parcel_track`（PR #215，**截至本文撰写仍未合入 main**）把分类抽到共享模块后，处理天数可以统一，假日日历却不能混用。

摩擦有三层。第一，迟发判定是「建标→收件营业日 − handling」；三家阈值不同则同一张「迟发」表不可比。第二，GLS 起运/交接在波兰，应用波兰法定历（含 Wigilia 12/24），UPS/FedEx 仍用美国联邦假日——统一 handling **不等于**统一日历。第三，整月全量必须搞清并发：同一 `--workers` 传给每家，但三家**串行**查询，峰值约等于 N 而不是 3N。

不要为此引入 Karrio / AfterShip。GLS 公开无鉴权 REST 已另文记录。本文钉：混合编排、handling=3、日历分叉、`--workers` 语义、以及一次已验证的 8 月 live 分类汇总（只给合计，不给单号/买家）。

## Guidance

**1. 处理天数三家都是 3；日历仍按承运商。**

`parcel_track/classify.py`：`HANDLING_DAYS = 3`（L15），`GLS_HANDLING_DAYS = HANDLING_DAYS`（L31）。`policy_for(carrier)`：处理天数均为 3；`gls` 返回波兰假日表，其余返回美国联邦假日表（L34–38）。波兰表含 `2026-12-24`（Wigilia）。

混合报表走 `classified_row` → `policy_for` → `_cat`。迟发：建标→收件营业日减去 handling 后仍大于 0。承运延误：收件→交付营业日大于在途慢阈值，且延误优先于迟发。

GLS 单承运商 `gls_track/ops_report.py` 顶部 `HANDLING_DAYS` 与混合口径对齐为 3；假日历仍用波兰法定假日。Excel「口径说明」写给读表的人：三家统一 3 个营业日，假日历不同（`parcel_track/ops_excel.py`）。

改 handling 只改 `HANDLING_DAYS`（让 GLS 别名跟着走）。禁止把波兰历套到 UPS/FedEx，也禁止把美国联邦历套到 GLS。

**2. `--workers N` = 每个承运商 N 个 worker；三家顺序跑，峰值 ≈ N。**

`run_report`：`w = 1 if mock else max(1, workers)`，`retries = 0 if mock else 1`。随后三个 `if` **依次**执行：先 UPS `run_ups(..., workers=w)`，返回后再 FedEx `run_fedex(..., workers=w)`，再 GLS `_query_gls(..., workers=w)`（`parcel_track/orchestrate.py`）。没有三家同时跑。因此 `--workers 4` 时 UPS 4、FedEx 4、GLS 4，但是**不是 12 路同时打网**。

CLI 默认 `--workers` 为 4；`--mock` 强制 1。FedEx 内部仍按官方 Track 每请求最多约 30 号分块，4 个 worker 是并行 chunk 数。

**3. 凭证与运行环境。**

非 mock 时 CLI `_load_env()`：`load_dotenv(..., override=False)`，先工作树 `.env`，再含 `AGENTS.md` 的仓库根 `.env`，缺 FedEx 时再试 sibling worktree `.env`。文档只写变量名，禁止粘贴 key。本 PR worktree 用父仓库 `.venv` 的 `python -m parcel_track.cli`，不要在 worktree 里 `uv run`（会另建 venv）。

**4. 合入状态。** 上述行为在当前树可核对，产品入口仍挂 **未合入的 PR #215**。对外写 pending，不要写成已在 main。

## Why This Matters

迟发是仓/货代交接 SLA，承运延误是收件后的在途 SLA。handling 不统一时，同一张迟发 sheet 里 GLS 与 FedEx 的逾期天数不可比。日历分叉是正确性：Labor Day 只在美国联邦历；Wigilia 只在波兰历。

若把 `--workers 4` 理解成 12 路并发，会按 3× 估峰值 QPS，既可能打官方限速，也会把整月墙钟误判为可再缩三倍。

## When to Apply

- 改 `parcel_track` / `gls_track` / `fedex_track` 迟发阈值或 Excel 口径说明。
- 运营问「三家是否同一处理天数」或「GLS 为何不是美国假日」。
- 整月 `report`：用 `--workers`（默认 4）理解**每家**并发；live 不要 `--mock`。
- 评估 Karrio / AfterShip：默认否。
- PR #215 合入前引用本行为一律写 pending。

## Examples

**统一天数、分叉日历（单测）。** `parcel_track/tests/test_classify.py` 的 `test_handling_unified_3_calendars_differ`：UPS 与 GLS 的 handling 都等于 3，两套 holiday 列表不相等。

**CLI。** 不传 `--workers` 时为 4。`--mock` 时 CLI 与 orchestrate 都把并发钳成 1。

**8 月 live 全量（本会话已跑；只给合计）。** 输入为运营侧 8 月通途非 FBA 订单 xlsx。父仓库 venv：

```text
python -m parcel_track.cli report --tt <August tongtu xlsx> --out parcel_track_output/ops-202608-live.xlsx --workers 4
```

查询行：`query UPS 715 / FedEx 6761 / GLS 1168 workers=4 retries=1`。完成：UPS 714/715，FedEx 6761/6761，GLS 1147/1168。入 10947 → UPS 715 / FedEx 6761 / GLS 1168 / 停放 2126 → 分类 8660；墙钟约 9 分钟。

分类合计（无跟踪号、无买家）：delivered_ok 7143；late_handover 1247（FedEx 1121 / UPS 125 / GLS 1）；not_handed 89；carrier_slow 74；not_found 43；stuck 31；in_transit 18；reused_no_label 14；cancelled 1。

入行 10947 与「唯一查询号 + 停放」之和不必相等：一格多号会拆行，查询侧再按号去重；停放行不查询、不丢弃。FedEx 分类行可多于唯一号（复用跟踪号多票）。

## Related

- [GLS 公开 REST + 波兰日历坑](../integration-issues/gls-track-public-rest-calendar.md)（REST 免账号、脏单元格、返件；handling 数值以本文为准）
- [FedEx 官方批量 Track](../workflow-issues/fedex-track-batch-query.md)（账号/组织与每请求 ≤30 号）
- 模块交接：`parcel_track/AGENT_HANDOFF.md`
- PR #215（未合入 main，as of 2026-09-08）
