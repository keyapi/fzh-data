# TASK 2026-10-27D 补充（工头自查，2026-10-27 17:xx）

用户已明确：**这些数据工头自己查，不要等 Jack**。以下为刚查到的真实结果，请并入 P1。

## A. EN SO backlog（工厂交付管线，不是消费需求）

查询：EN 生产 REST，`Sales Order` `docstatus=1`、`per_delivered<100`、`delivery_date>=2026-08-01`；逐单读 items，`open=qty-delivered_qty`。

| 项 | 值 |
|---|---|
| 开放 SO | **43 单** |
| 开放行 | **740 行** |
| 开放量 | **63,140 件** |
| 逾期量（delivery_date < 2026-10-27） | **52,221 件** |
| 按分公司 | DANEEY 31,644 / CENTRADE 19,550 / 美国FBA 8,732 / 波兰公司 3,214 |
| 按工厂仓 | 半成品仓-FZH 45,737 / 成品仓-FZH 16,764 / 包材仓-FZH 589 / 仓库-FZH 50 |
| 按交付月 | 2026-08 22,240 / 09 28,698 / 10 11,470 / 11 440 / 12 257 |

**口径**：SO 是公司向绍兴工厂下的生产/交付单；`customer` 是分公司（CENTRADE/DANEEY/波兰/FBA），`customer_item_code` 是通途 SKU，`warehouse` 是工厂仓，`delivery_date` 是工厂计划交付日。它是**未来供给管线**，不是终端消费需求；不要与预测需求相加。到分公司还要头程/清关/上架，未到前不能算海外仓可用。

## B. 通途 PO 状态（已查到官方语义）

`EN_API/tongtool_purchase/AGENT_HANDOFF.md` 明确定义：

- `0` 等待到货 → 开放
- `1` 部分到货等待剩余 → 开放剩余
- `2` 部分到货不等待剩余 → 开放剩余
- `3` 全部到货 → 已收
- **`4` 作废 → 排除**

本批 387 行：`0` 244 行 / 16,914 件开放；`3` 101 行 / 6,385 件已收；`4` 42 行 / **2,925 件作废**。  
**开放 PO = 16,914 件，不是 19,839**；`willArriveDate` 全空，`purchaseArrivalDate` 只有已收行有。无 ETA → 条件态；不要问 Jack。

## C. 皮壳/半成品 1:1

不需要等“子仓库存行”。子仓是分公司下的角色/成本标签；实物库存看主仓，1:1 转换作用在：
- EN SO 行（`customer_item_code` 通途 SKU + 工厂仓 + 交付日）；
- 主仓库存按角色（皮壳/半成品/成品）。
把 SO backlog 按 `customer → branch`、`customer_item_code → Tongtong SKU`、`delivery_date` 映射；皮壳/半成品标 `conversion_assumed=true`；不要因“没有子仓库存行”而不做。

## D. 请并入 P1

1. 生成本地 `so_backlog_rows.csv`（行级）+ `so_backlog_summary.json`：分公司、工厂仓、通途 SKU、交付月、开放量、逾期量。
2. 把 SO backlog 作为 **in_production / finished_not_shipped** 供给管线：
   - 计划日 = SO `delivery_date`；
   - 头程/到仓 lead time 用假设值（assumed）或从 YYS DN/头程运单实测分布；未到前不算 branch 可用；
   - `date_confidence=estimated/unknown`；不写 confirmed。
3. 修正 PO：排除 status 4；开放量 16,914；status 3 已收；无 ETA 条件态。
4. 条件决策包分三层显示：
   - 海外仓现货 + 在途（当前可用/条件）；
   - 通途 PO 条件供给（16,914，无 ETA）；
   - 工厂 SO backlog（63,140，逾期 52,221，工厂交付日 + 头程假设）。
   不要把这 63,140 直接加到海外仓可用；它是上游管线。
5. 60 分钟 checkpoint 或完成报告；不 push、不写生产。

## E. 结论

SO backlog、PO 状态、子仓对象都不需要 Jack；Jack 只负责 EN app/生产阶段事实。若他后续提供 W1 的 Shipment ETA/生产阶段，再接入。
