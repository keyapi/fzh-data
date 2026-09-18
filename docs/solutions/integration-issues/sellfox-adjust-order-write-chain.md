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
