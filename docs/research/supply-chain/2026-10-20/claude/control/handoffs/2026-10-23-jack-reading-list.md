---
okf: v0.1
type: Index
title: Jack W1 阅读清单（按顺序）
date: 2026-10-23
owner: claude-foreman
channel: docs/jack-w1-channel
---

# Jack W1 阅读清单

> 目标：读完后你能独立回答——**这批货现在在哪、下一段什么时候可用、哪些数量算一次、哪些未知不能填 0**。
> 如果只有 30 分钟，先读 §0 的入口 + §1 的 3 篇；其余按需。
> **本分支是 Jack 的唯一事实源**；工头后续与 Jack 有关的技术结论会以新 commit 追加到这里，不依赖聊天转述。

## 0. 先读：履约查询统一入口（#291，已合并 `3405ac10`）

| 文档/代码 | 为什么读 |
|---|---|
| `EN_API/fulfillment_query.py` | 统一入口：多输入（客户码 / EN 物料码）→ SO→生产→销售出库（阶段 0–3）；**JSON 权威** |
| `EN_API/fulfillment/` | 11 模块：数量阶梯对账、齐套、异常 §8 + 下一行动、控制台/Excel 渲染 |
| `supply_chain_visibility/AGENT_HANDOFF.md` | 链路事实地图 + 关键口径 + 边界；**最先读这篇** |
| `supply_chain_visibility/docs/reference/en-supply-chain-map.md` | EN 全链路实体地图（含自定义 app / 建了没用的 doctype） |

**关键口径**：工序进度取**第一道工序**完成量、**不跨工序求和**；`WO.status/produced_qty` **不可信**；
`Closed ≠ 已发完`；出库按 `item_code` 匹配、退货行负数**净额抵扣**；EN 的 `po_no` 不是客户 PO。

**边界**：阶段 0–3；头程/海外仓（4–8）未接入；物料需求/采购/入库 EN 侧基本空白。

**不要重写**：W1 的 timeline 消费它的阶段/数量口径；若与 SC14 冲突，先提 `[W1-Qxx]`。

示例（测试系统优先）：

```bash
uv run python EN_API/fulfillment_query.py --codes CENKZ1325-Yellow-138 --test --json
```

## 1. 必读（30 分钟）

| # | 文档 | 为什么读 |
|---:|---|---|
| 1 | [`2026-10-23-jack-supply-timeline.md`](2026-10-23-jack-supply-timeline.md) | W1–W4 的任务、数据源、输出表、验收、边界 |
| 2 | [`2026-10-23-jack-w1-answers.md`](2026-10-23-jack-w1-answers.md) | 七问答复：PO/在途、WO、海外入库、SKU 映射、仓库、ETA、本地数据 |
| 3 | [`2026-10-23-jack-sample10.md`](../reviews/2026-10-23-jack-sample10.md) | **当前 9 个冻结 SKU** + 1 个缺额；不要再用旧 8+2 |

## 2. 接口契约（写代码前必读）

| # | 文档/代码 | 为什么读 |
|---:|---|---|
| 4 | [`2026-10-23-sc14-spec.md`](../reviews/2026-10-23-sc14-spec.md) | W1/W3 必填字段、阶段枚举、五条边界语义 |
| 5 | [`experiments/sc14/contract.py`](../../../experiments/sc14/contract.py) | 可执行校验：`E_*` / `W_*` 错误码 |
| 6 | [`experiments/sc14/test_contract.py`](../../../experiments/sc14/test_contract.py) | 16 条验收用例；你的输出应能过 |
| 7 | [`experiments/sc14/dry_run_sc04.py`](../../../experiments/sc14/dry_run_sc04.py) | 用真实 SC04 产物预演，抓 2,968 条不合规 |

## 3. 供应侧证据（理解已有什么、缺什么）

| # | 文档 | 为什么读 |
|---:|---|---|
| 8 | [`2026-10-23-sc04-supply-stage.md`](../reviews/2026-10-23-sc04-supply-stage.md) | 39 张 DN 的阶段归属；与你的 timeline 对账基准 |
| 9 | [`2026-10-23-dn-split.md`](../reviews/2026-10-23-dn-split.md) | SC03 分路：单据级 vs 数量级；`credited_qty` 不可用 |
| 10 | [`2026-10-23-dn-bridge.md`](../reviews/2026-10-23-dn-bridge.md) | DN 状态接入与未证项 |
| 11 | [`2026-10-22-eta-cover-uom-evidence.md`](../reviews/2026-10-22-eta-cover-uom-evidence.md) | ETA 0/524、Cover 情景、UOM unknown |
| 12 | [`experiments/g1_contract/g1b_results.md`](../../../experiments/g1_contract/g1b_results.md) | WO/JC/SE 窄样本；`produced_qty` 不可当完工账 |
| 13 | [`experiments/g1_contract/prod_budget.md`](../../../experiments/g1_contract/prod_budget.md) | 生产只读闸门：300 请求 / 32 MiB / 900 秒 |

## 4. 映射、目录、下游

| # | 文档 | 为什么读 |
|---:|---|---|
| 14 | [`2026-10-23-map-evidence.md`](../reviews/2026-10-23-map-evidence.md) | 58 直接 / 217 可推导 / 7 未映射；组件不是独立 SKU |
| 15 | [`2026-10-23-sc10-catalog-diff.md`](../reviews/2026-10-23-sc10-catalog-diff.md) | 1,328 母集与完整目录差集（271 有库存无近期销售等） |
| 16 | [`2026-10-23-sc10-entry-prep.md`](../reviews/2026-10-23-sc10-entry-prep.md) | 271 入批检查表；卡在“快照间台账” |
| 17 | [`2026-10-23-sc09-trial-pack-v1-frozen.md`](../reviews/2026-10-23-sc09-trial-pack-v1-frozen.md) | 下游 23 列怎么消费 `supply_*`；不要按它改 W1 |

## 5. 项目规则与当前状态

| # | 文档 | 为什么读 |
|---:|---|---|
| 18 | [`PROJECT_BOARD.md`](../PROJECT_BOARD.md) | 当前卡、Jack 边界、SC13/SC14、已知风险 |
| 19 | [`DECISIONS.md`](../DECISIONS.md) | D16/D17（样本）、D33（公开仓库不放 CSV）、D35（模型） |
| 20 | [`HANDOFF.md`](../HANDOFF.md) | 角色、单一写入者、进程事实 |
| 21 | [`2026-10-23-jack-data-map.md`](2026-10-23-jack-data-map.md) | 本机 DuckDB/备份/EN 证据的读取地图 |
| 22 | [`experiments/sc13/`](../../../experiments/sc13/) | W2 消费端契约；示例参数是 `assumed`，不是业务批准 |

## 6. 旧版识别（不要用）

| 看起来像 | 实际 | 用哪个 |
|---|---|---|
| N2-S0 的 8 填充 + 2 缺额 | 2026-10-22 旧冻结；漏查 EN 工单 | `2026-10-23-jack-sample10.md` 的 9+1 |
| SC14 只有 `contract.py`、没有 spec | spec 曾未提交；本分支已收录 | 本分支的 `2026-10-23-sc14-spec.md` |
| “Stock Entry 0 = 海外 received 0” | 只是 EN 记账 0 | 用签收节点 + 通途库存变动 + SC04 对账 |
| “同量 PO 直接排除” | 会少算 | 两本账 + `overlap_status` + B_min/B_max |
| “WO `produced_qty` 是完工” | 已证有失真 | `estimated remaining` + JC `sum_qty` progress |

## 7. 读完自检（5 问）

1. 一 DN 多运单号时，数量记几行、记多少？
2. 部分签收怎么拆？拆完两行之和必须等于什么？
3. `qty=null` 与 `qty=0` 的区别？`date_confidence=unknown` 时 `available_date` 必须是什么？
4. `CENCord995-DKGrey-97` 和 `PK#KS0001-QDKTR-100-DEEPGREY` 是几行？WO 产出能不能直接当成品？
5. 拿不到 `batch_key` 时，PO/在途怎么出数？为什么不能只给一个数？
