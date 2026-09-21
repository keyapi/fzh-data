---
okf: v0.1
type: Reference
title: 赛狐调整单写链路实测——createV2 一步到位，batchConfirmAdjust 只适用「待调整」态
date: 2026-09-18
category: integration-issues
module: SELLFOX_API
problem_type: integration_issue
component: sellfox-openapi
severity: high
applies_when:
  - "要用赛狐 OpenAPI 建库存调整单（数量调整 / 换标 / SKU 调整）"
  - "要拿 originId，或想从调整单列表反推库存明细 id"
  - "batchConfirmAdjust 报「非待调整状态无法进行该操作」"
  - "怀疑赛狐接口文档与实装不符"
---

# 赛狐调整单写链路：createV2 一步到位，batchConfirmAdjust 只适用「待调整」态

## Context

《调整单》是赛狐仓库模块下的一组接口，用于调整库存数量 / 换标 / 换 SKU。文档把链路描述成
「建单 → 批量确认」两步，容易让人以为必须两步才落库存。

本次（2026-09-18）在 `sellfox-main` 生产账号上用测试商品真跑了一遍，结论与文档预期**明显不符**，
且推翻了一个基于文档推断的实现假设。记录于此，避免后来者再踩。

关联：`docs/solutions/conventions/sellfox-apifox-api-docs-mirror-refresh.md` 末段已注明
「镜像刷新只回答*文档*是否更新；接口行为与文档不一致时，另做 API 实测」——本次正是那次实测。

## Guidance

### 正确的写链路只有一次调用

```
仓库列表  /api/warehouseManage/warehouseList.json        → warehouseId
库存明细  /api/warehouseManage/warehouseItemList.json    → id  ← 这就是 originId
建调整单  /api/ware/adjust/createV2.json                 → 建单并直接落库存（本账号）
```

`batchConfirmAdjust` **不是必调步骤**，见下。

### 三个反直觉点

**1. `createV2` 的响应 `data` 恒为 `null`，不回传 `adjustNo`。**

文档 schema 里 `data` 就是空对象（`properties: {}`），实测确实返回 `null`。
→ 建完单必须回查 `pageList` 才知道单号：按 `dateType=1` + 当天 + `warehouseId` 拉列表，
再用 `itemList[].commoditySku` 和 `targetAvailable` 双重校验，避免抓错单。

**2. `createV2` 一步到位：单据直接「已完成」并扣减库存。**

无审批流的账号下，建单后立刻回查，`adjustStatus` 已是 `3 已完成`，库存同步落账，
`processInstanceId` / `canReview` 均为 `null`。

**3. `batchConfirmAdjust` 只对停在「待调整(2)」的单生效。**

对已完成单调用必然失败：

```json
{"success": 0, "fail": 1,
 "results": [{"success": false, "message": "非待调整状态无法进行该操作"}]}
```

「待调整」态只在该仓库**配置了审批流**时出现。所以正确做法是：建单后回查状态，
`3` 就跳过确认，`2` 才调 `batchConfirmAdjust`，其他状态报错人工介入。

### originId 的取法

`originId` = 《查询库存明细》返回的 `WarehouseItemOpenVo.id`（库存明细主键）。

**不要试图从调整单列表反推**：统计 37 张历史单共 **524** 条明细，`warehouseItemId`
（文档写「仓库商品id」，疑似就是它）**524/524 全为 `null`**。明细里的 `id` 是调整单明细
自身主键，`commodityId` 才是商品 id，两者都不是 originId。

### 建单入参要点

```json
{
  "type": "0",
  "warehouseId": "279841",
  "remark": "≤1000 字符",
  "items": [{
    "originId": "18194971",
    "targetId": "18194971",
    "available": "-3",
    "defective": "0"
  }]
}
```

- `available` / `defective` 是**字符串**，传有符号增量
- **数量调整时 `targetId` 必须等于 `originId`**；`targetSku` / `targetFnSku` 只在换标 / SKU 调整时用
- 货架未做手工选位时省略 `shelfAvailable` / `shelfDefective` —— 仓库自带「默认货架(良品)」，
  系统会自动分配并回填 `shelfAvailableUsed`

### 读接口的废字段

- `sum`（明细数目）在 `pageList` 里恒为 `0`，**不可信**，用 `len(itemList)`
- `newAvailable` 就是**当前库存**，不是名字暗示的「调整后的新值」；`available` 同样是当前值，
  只有 `targetAvailable` 是增量。想还原调整前库存得自己减
- `startDate` / `endDate` 只精确到天（`yyyy-MM-dd`），`dateType` 1=创建时间 2=操作时间

### 限流

代理（`api.vilavi.cn/sellfox`）实际约 **1 req/2s**，连打必 429。用
`SELLFOX_API/client.py` 的 `SellfoxClient`（内置 2s pacing + 429 重试），别裸写 urllib。

### 站点内部端点族（与 OpenAPI 路径不同）

OpenAPI 的 `/api/ware/adjust/*` 在 `www.sellfox.com` 上 **404**（返回一段跳 `dashboard.html` 的 HTML）。
站点用的是：

```
/api/gw/sellfox/sellfox-warehouse/sellfox/api/warehouse/adjust/
   pageList | detail | create | submit | confirmAdjust | approval | delete | editRemark
```

列表页 `/web/warehouse/adjustmentSheet/index.html`；详情页 `adjustmentSheetNew/Detail.html?id=<id>`
（**详情页用 URL 传 `id`**，与备货单用 localStorage 不同）。

### 调整单的成本语义（2026-09-18 实测）

- **创建时不录成本** —— item 只有 `originId/targetId/available/defective/shelfAvailable/shelfDefective`，**零成本字段**。
- **新批次的成本 = 该 (仓库,SKU) 当前的加权平均成本快照**（即库存明细的「采购单价 / 单位费用」），
  **不是**来源单的成本。

实测：某 SKU 当前单位费用 4.3763、其来源备货单批次是 4.08，建 `+1` 后新批次
`transportCost = 4.3763` —— 取的是 SKU 均价，不是 4.08。

> 所以调整单批次**天然不会"跟随"**任何来源单：它们是**时点快照**。这解释了为什么改备货单头程改不动它们。

### 不可逆性（重点）

**① `+N` 之后用 `-N` 回不去。** 扣减按 **FIFO 吃最老的批次**，不会冲掉刚建的新批次。

实测 `+1` 再 `-1`：

| | 结果 |
|---|---|
| 备货单批次 | 139 → **138**（被 FIFO 啃掉 1 件）|
| 新建批次 | **1 件留下**（成本 = 当时的 SKU 均价快照）|
| 单位费用 | 4.3763 → **4.3782**（净漂移 +0.0019，且清不掉）|

**② 已完成的调整单不可删除、不可撤销。**

- 删除被明确拒绝：`仅【待调整】、【待提交】状态的单据可删除`
- 详情页只有 `取消`（= 返回列表）和 `打印`，**没有撤销/作废**
- 端点族里**没有** `antiAudit`/`revoke`；`confirmAdjust`/`approval` 都是正向流程
- 唯一能对已完成单做的写操作是 **`editRemark`**（body `{id, remark}`）

### 用它做「数量同步」的代价（不是用错工具）

**先纠正一个容易走偏的结论**：赛狐自己的三方仓模块就有「生成调整单」功能
（i18n `main.warehouse.tripartite.warehouse.generate.adjustment.order`，权限
`MOD_OVERSEA_WAREHOUSE.CREATE_ADJUST`）—— 说明**官方对「外部库存同步」的建模本身就是生成调整单**。
所以用它同步数量**不是选错工具**；问题在下面三点，且都在**成本**侧。

数量同步是**可反复修正**的需求；调整单是**写完即终局、且不可撤销**的单据类型。两者叠加会持续产生：

1. **不可撤销的账本记录**（写错只能再写一笔）
2. **不可修正的成本快照批次**（每轮同步都在库存里沉淀一个「当时均价」，堆积且改不动）
3. **被 FIFO 逐渐啃掉的原始批次**（可修正的那部分在持续消耗）

因此同一 (仓库,SKU) 会积累几十个不同时点的成本快照，**越跑越难把均价改到位**，且没有回退路径。

出路是让同步**带上成本**（其他入库单 `perPurchase` 必填，或保持调整单但先修好该 SKU 的成本），
完整分析见 [`../workflow-issues/sellfox-inventory-sync-cost-drift.md`](../workflow-issues/sellfox-inventory-sync-cost-drift.md)。

### 替代：其他入库单（带成本）

`其他入库单创建（2.0）` `/api/warehouseInOut/inRecord/v2.json`：

```yaml
WarehouseInItemOpenV2Qo:
  required: [commoditySku, perPurchase]     # 采购单价必填
表头: shipFee 运费 / otherFee 其它费用 / apportionType 费用分配方式(0不分配/1按金额/2按数量)
      type 0其他入库 1采购入库 2维修入库 3退货入库 4还回入库 5次品入库
```

**能一次性带上 数量 + 采购单价 + 头程**。仓库已有实现：
[`web_automation/click-based/sellfox_import_other_inbound.py`](../../../web_automation/click-based/sellfox_import_other_inbound.py)（已支持 `--sku --wh --qty --price`）。

> 未验：其他入库单产生的批次是否同样"独立不跟随"（大概率是）。但它**显式携带成本**，
> 每次入库都能对齐到目标值，比调整单的"黑箱默认"好一个数量级。

## Why This Matters

- 按文档写「建单 → 确认」两步，第二步必然报错，容易被误判成权限或参数问题；
  更糟的是把它当成「确认前不落库存」，从而在批处理里重复建单。
- `originId` 若从调整单列表反推会拿到 `null`，写链路直接断。
- `sum` 被当成明細数用于对账会全盘算错。
- 调整单是**真实库存写入**，误判代价直接落在生产库存上。

## When to Apply

- 要写代码调 `createV2` / `batchConfirmAdjust` / `warehouseItemList` 时。
- 排查「调整单建了但库存没动」或「确认报非待调整状态」时。
- 拿赛狐文档 schema 当实现依据前——本文档即「文档与实装不符」的实例。

## Examples

### 2026-09-18 实测记录（可复查）

| 项 | 值 |
|----|-----|
| 账号 | `sellfox-main`（生产，代理 API） |
| 目标 | POLAND 主仓 `warehouseId=279841`，`test001-white`，扣减 3 |
| originId | `18194971`（`warehouseItemList` 的 `id`） |
| 建单前库存 | 可用 2000 / 次品 0 / 占用 0 |
| `createV2` 返回 | `null` |
| 生成单号 | `AD2609180004`，`adjustStatus=3`，`processInstanceId=null` |
| `batchConfirmAdjust` | `fail=1`，`非待调整状态无法进行该操作` |
| 建单后库存 | 可用 **1997** / 次品 0 / 占用 0 ✓ |
| 修正前统计 | 37 张历史单 / 524 条明细，`warehouseItemId` 全为 null |

可复跑脚本：[`SELLFOX_API/sellfox_adjust_test.py`](../../../SELLFOX_API/sellfox_adjust_test.py)
（默认 dry-run，`--apply` 才写；`--warehouse-id` / `--sku` / `--delta` 可覆盖，
反向 `--delta 3` 即回滚）

### 文档来源

- [查询调整单列表](https://sellfoxapi.apifox.cn/api-360743257.md) → `/api/ware/adjust/pageList.json`
- [创建调整单](https://sellfoxapi.apifox.cn/api-360743256.md) → `/api/ware/adjust/createV2.json`
- [批量确认调整单](https://sellfoxapi.apifox.cn/api-437950677.md) → `/api/ware/adjust/batchConfirmAdjust.json`
- [查询库存明细](https://sellfoxapi.apifox.cn/api-51516622) → `/api/warehouseManage/warehouseItemList.json`

本地镜像：`SELLFOX_API/docs/api-reference/仓库/调整单/`、`.../仓库/库存明细/`

## Related

- [`sellfox-apifox-api-docs-mirror-refresh.md`](../conventions/sellfox-apifox-api-docs-mirror-refresh.md) — 文档镜像刷新的边界：镜像只证明文档更新
- [`unverified-external-api-claims-in-docs.md`](../documentation-gaps/unverified-external-api-claims-in-docs.md) — 外部 API 声明须实测
- [`other-outbound` skill](../../../.agents/skills/other-outbound/) — 其他出库单，另一条零库存路径
