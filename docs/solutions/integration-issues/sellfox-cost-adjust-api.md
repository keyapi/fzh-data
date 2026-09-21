---
okf: v0.1
type: Reference
title: 赛狐成本补录单——公开 OpenAPI 只读，创建/审核走内部接口（完整契约实测）
date: 2026-09-18
category: integration-issues
module: cost_adjust
problem_type: integration_issue
component: sellfox-openapi
severity: high
applies_when:
  - "要用 API 改赛狐已入库库存的采购成本（成本补录单）"
  - "create.json / audit.json 的 payload 怎么构造"
  - "公开 OpenAPI 调成本补录单一律 40021 访问的接口暂无权限"
  - "要判断某个赛狐功能是否有公开写接口"
  - "审核报「货值不能为负数」—— 变更额超过了该批次剩余货值"
  - "报「存在待审核的补录单」—— 同 SKU 只能有一张在审"
---

# 赛狐成本补录单：公开 OpenAPI 只读，创建/审核走内部接口

## Context

要按「海外仓备货单 + SKU」修正已入库库存的采购成本。既有路径是
`cost_adjust/build_saihu_cost_adjust.py` 生成 xlsx → UI 上传 → 人工点审核，**全程点击**。
目标是把创建与审核改成 API 调用。

先验事实：**赛狐公开 OpenAPI 里，成本补录单只有一个端点**——
`POST /api/fba/cost/adjustment/pageList.json`（查询，Apifox `api-74141034`）。
整个 FBA 模块下没有 create / import / audit。所以「API 写」在公开 OpenAPI 上不存在，
必须走**私有接口**（undocumented internal API，业界亦称 shadow API 影子 API）——
厂商自己前端在用、但未写进公开 OpenAPI 的端点，需借浏览器登录态，无稳定性承诺。
术语与判据见 [`../../research/2026-09-18-sellfox-private-api-terminology.md`](../../research/2026-09-18-sellfox-private-api-terminology.md)。

内部接口名不是从文档来的，是**从打包产物里挖出来的**：
`https://s1.sellfox.com/sellfox-web/<日期>/bundle.index.*.js` 里有完整的
`/api/fba/cost/adjustment/` 端点族。这条方法在赛狐「文档没写但页面在用」时通用。

## Guidance

### 端点族

```
读  GET  /api/fba/cost/adjustment/getItemsByNoAndSearchValue.json?adjustType=&no=
        → 按来源单据号拉可补录商品，逐行带 perPurchase / goods / shippingOrderId
    GET  /api/fba/cost/adjustment/count.json            → {all, to_audit, has_passed, has_rejected}
    GET  /api/fba/cost/adjustment/detailByRelationNo.json?relationNo=&adjustType=
        → 按关联单号查已存在的补录单明细
    POST /api/fba/cost/adjustment/pageList.json
写  POST /api/fba/cost/adjustment/create.json   body = 完整 items 回填后整坨
    POST /api/fba/cost/adjustment/audit.json    body = [adjustId, ...]
    POST /api/fba/cost/adjustment/delete.json   body = [adjustId, ...]
    POST /api/fba/cost/adjustment/reject.json   body = {"adjustId": N, "reason": "..."}
```

**未解析**：`edit.json` / `updateRemark.json` —— 打包产物里有这两个接口，
但成本补录单详情页对「待审核」单**没有任何可编辑输入**，列表页下拉也只有
「审核通过 / 驳回 / 删除」，找不到触发入口。疑似供「库存调整单」页面复用。

### 三步写流程

```
① GET  getItemsByNoAndSearchValue.json?adjustType=6&no=<备货单号>
② 改建   items[].newPurchaseCost / newTotalPurchaseCost（其余整坨照抄）
③ POST create.json → 得到 adjustId + adjustSn，状态 to_audit
   POST audit.json  body=[adjustId] → 生效，改动库存成本
```

### 三个必须照抄、不能自己造的字段

1. **`warehouseId` ≠ `targetWarehouseId`**。前者是**虚拟仓库**（如 272150，FBA 侧来源），
   后者才是真实海外仓（如 279841 = POLAND）。看着像笔误，其实是两个不同仓库。
2. **`newPerFee` 传 `0`，而 `oriPerFee` 是 `null`**。
3. **`oriTotalPerFee` / `newTotalPerFee` / `auxFee` 是空字符串 `""`，不是 `0`**。

`oriTotalPurchaseCost` / `newTotalPurchaseCost` 是整数时要去掉小数点（`1500` 而非 `1500.0`）。

### 建单/审核会被拒的两条硬约束（2026-09-20 实测）

**① 变更额不能超过该批次剩余货值 —— `货值不能为负数`**

补录单改的是**整条备货单行**（`newPurchaseCost` 是单件价，影响面按**备货量**算），
但它扣的是**该批次此刻还剩的货值**（`剩余可用量 × 当前单价`）。两者不等价：

```
单件可下调幅度 ≲ 当前单价 × (批次剩余可用量 / 备货单备货量)
```

实测边界（`KS0001-HLR-153-GINGER`：备货量 1000、当前可用仅 7、单价 179.30）：
理论下限 `179.30 × 7/1000 = 1.2551`，即最多降到 **178.045**。
试 `178.05` 过校验；试 `123.76`（‑55.54/件 × 1000 = ‑55,540，而批次只剩 7×179.30 = 1,255 货值）被拒：

```
失败原因: SKU[KS0001-HLR-153-GINGER], FnSku[], 货值不能为负数。
```

**边界值与公式吻合。** 推论比约束本身更重要：**剩余占比决定可下调幅度**；
备货单被消耗得越多越改不动，**剩余为 0 时完全改不动**。所以「下调成本」有强时效性
—— 要在批次还没被订单/调整单吃掉时做（见
[`../workflow-issues/sellfox-incentive-cost-adjust-2026-09.md`](../workflow-issues/sellfox-incentive-cost-adjust-2026-09.md)）。

**② 同一 SKU 同时只能有一张待审核补录单**

```
SKU：KS0001-HLR-153-GINGER 存在待审核的补录单
```

批量建单必须**按 SKU 串行**：前一张 `audit.json` 通过或 `delete.json` 删除后才能建下一张。
`delete.json` 的 body 与 audit 同形，就是 `[adjustId]`（如 `[20211]`）。

### 调 create 前先用「拦截后挡掉」拿契约，别试错写生产

Playwright 路由可以把请求**截获后 fulfill 假响应**，请求不会到达服务端：

```js
await page.route('**/api/fba/cost/adjustment/create.json', async (route) => {
  capture(route.request().postData());
  await route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify({ code: 40000, msg: '__CAPTURED_BLOCKED__', data: null }) });
});
```

驱动 UI 走到提交，即可拿到**真实 payload 而零写入**。抓完用
`page.unroute()` 撤销再走真实调用。这是本次拿到 create/audit/reject/delete
四个契约而生产数据零改动的方法。

注意：`browser_run_code_unsafe` 每次调用是独立 Node 上下文，`globalThis` 不跨调用，
截获数据要存到**页面上下文**（`window.__cap`）再从页面读。

### 权限差异

公开 OpenAPI 那个 app 对查询的**过滤字段逐个鉴权**：

| 查询方式 | 公开 OpenAPI（代理） |
|---|---|
| 裸分页 / `adjustType` | ✅ |
| `searchField=adjustSn` | ✅ |
| `searchField=sku` | ❌ `40021` |
| `status` / `warehouseIds` / `createTimeStart` | ❌ `40021` |

且该接口会**间歇性 40021**，重试即可恢复 —— 实现必须带重试，别把首次失败当权限问题。
走浏览器会话则不受这些限制。

## Why This Matters

- 只看公开 OpenAPI 会得出「没有写接口，只能点页面」的错误结论。写接口存在，只是在内部。
- payload 是靠**逐字段回填**读接口的结果，任何自造字段都可能被静默改写或拒绝。
- 用真发请求去试 payload = 直接改生产库存成本。拦截后挡掉是零成本拿到契约的唯一安全姿势。
- 生效影响是 **剩余数量 × 价差**，不是原始数量 × 价差（见下）。
- **向下改比向上改难得多**：上调不受限，下调被「批次剩余货值」封顶
  （`单件可下调幅度 ≲ 当前单价 × 剩余占比`）。已消耗完的备货单**改不动**。

## When to Apply

- 要用 API 改赛狐库存采购成本时。
- 判断某赛狐功能有没有公开写接口时 —— 先查公开 OpenAPI，没有再挖打包产物。
- 需要在不改生产数据的前提下拿到写接口契约时。

## Examples

### 2026-09-18 生产实测（test001-white @ POLAND）

用 `sellfox_cost_adjust_api.py` 的构造逻辑（与 UI 实际请求体**逐字段一致**）跑通：

| 项 | 值 |
|---|---|
| 备货单 | `OWS294A9T700030`（adjustType=6 海外仓备货单） |
| 仓库 | 虚拟仓库 272150 → POLAND 279841 |
| 建单 | `CA26091800004`（id=20207），状态 `to_audit` |
| audit body | `[20207]` → `{"fail":0,"success":1}` |
| 采购单价 | 1.3748 → **1.3648** |
| 单位费用 | 0.6006（不变，符合预期） |
| 入库成本 | 3944.90 → **3924.96**（−19.94） |

**−19.94 而非 −20 的原因**：改的是该批次单价 1.50→1.48，但该批次 1000 件里
只剩 997 件（此前被库存调整单扣过 3 个），实际影响 `997 × 0.02 = 19.94`。
加权均价校验：`(997×1.48 + 1000×1.25)/1997 = 1.3648` ✓

`adjustType=6` 不在官方文档列出的 1–5（发货单/采购单/调拨单/其他入库/库存明细）之内，
6 是海外仓备货单。

工具：`cost_adjust/sellfox_cost_adjust_api.py`（默认 dry-run，`--apply` 才写）

### 2026-09-20 批量下调实测（被两条硬约束挡住）

用规则表目标值批量下调激励价时，逐行验证了上面两条约束：

| 测试 | 值 | 结果 |
|---|---|---|
| 边界值 `178.05` | 备货量 1000 / 可用 7 / 现价 179.30 → 理论下限 178.045 | 过校验，但被「存在待审核的补录单」挡下 |
| 目标值 `123.76` | Δ = ‑55.54 ×1000 = ‑55,540；批次剩余货值 7×179.30 = 1,255 | ❌ `货值不能为负数` |
| 清理在审单 | `POST delete.json` body `[20211]` | ✅ 清掉 `CA26092000001` 后可再建 |

结论：这些备货单大多已被订单/调整单消耗大半，**目标价降不到**。
完整执行记录见
[`../workflow-issues/sellfox-incentive-cost-adjust-2026-09.md`](../workflow-issues/sellfox-incentive-cost-adjust-2026-09.md)。

## Related

- [`../workflow-issues/sellfox-incentive-cost-adjust-2026-09.md`](../workflow-issues/sellfox-incentive-cost-adjust-2026-09.md) — 用这套接口批量下调激励价的执行记录（两条硬约束怎么挡住的）
- [`sellfox-adjust-order-write-chain.md`](sellfox-adjust-order-write-chain.md) — 库存**调整单**（数量）的另一条写链路，同为「文档与实装不符 + 内部接口」
- [`../conventions/sellfox-apifox-api-docs-mirror-refresh.md`](../conventions/sellfox-apifox-api-docs-mirror-refresh.md) — 镜像只证明文档更新，行为须实测
- [`../../research/2026-09-18-sellfox-cost-accounting-fifo.md`](../../research/2026-09-18-sellfox-cost-accounting-fifo.md) — 赛狐成本口径与 FIFO 批次
- [`../../../web_automation/docs/reference/sellfox-pitfalls.md`](../../../web_automation/docs/reference/sellfox-pitfalls.md) — 同主题的 UI 侧踩坑
