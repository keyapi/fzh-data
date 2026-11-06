---
okf: v0.1
type: Reference
title: 旁路口径（改单窗口 / 尾程 / 补发 / 非商品）
description: 通途订单成本主链之外的运营时效与费用旁路：≈90 天改单窗口、尾程缺口与账单来源、补发/云仓直发例外、非商品与白名单；给出来源 PR 与证据等级
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, tail-cost, split-window, supplementary, non-product, canon]
---

# 旁路口径

> **状态：canon v0.1。** 主计价见 [03](03-price-matrix.md)；订单身份见 [01](01-order-universe.md)。
> 本页只写「不进四列、但会影响运营/利润判断」的规则。

## 1. 通途改单窗口 ≈ 90 天

- **事实约束**：通途侧修改尾程/改单，在发货日期往前约 90 天后**不可改**。
- **实测**：#282 只有两个观测点——发货日期 **7/10 及更早导入失败、7/14 及以后成功**；精确边界未证实。
- **规范写法**：只能写「≈90 天，实测分界 7/10–7/14」，不得写成无条件业务规则。
- **例外**：
  - 云仓直发**不需要尾程**；
  - 补发单 `-M<数字>` 且渠道为 OSTK/Wayfair，视为**需要尾程**（`needs_last_leg=1`）。

**证据**：[#282](https://github.com/keyapi/fzh-data/pull/282)（`monthly-tail-cost-pipeline.md`）；2026-11-06 盘点 §7.3。

## 2. 尾程缺口与账单来源

- **缺口定义**：`needs_tail=1` 且 **物流商运费 = 0** 的订单行 → 进入「待追尾程」清单。
- **账单来源分类**（#287）：
  1. 平台已付（不再追）；
  2. 补发例外（按补发规则处理）；
  3. 「7 条」供应商账单；
  4. 疑似官方 FedEx 账单（未证实，需抬头/账号核对）。
- **FedEx**：无公开账单 API；官网下载存在反爬，自动化被拦 → 只能人工下载或走线下账单。
- **与 C13 的关系**：本页只给缺口定义与账单来源，不裁决「OS/CR/SGP 三套尾程优先级谁为准」（见 [07](07-conflicts.md) C13）。

**证据**：[#287](https://github.com/keyapi/fzh-data/pull/287)（`fedex-billing-online-download.md`、`2026-10-10-fedex-invoice-api-and-official-parcels.md`）。

## 3. 补发与云仓

| 形态 | 判据 | 处理 |
|---|---|---|
| **补发** | 通途 `是否补发货=是`（优先）或订单号 `-M<数字>` | 不合并；需要尾程；成本按原单/补发件单独看 |
| **补发 + OSTK/Wayfair** | `-M<数字>` 且渠道匹配 | 强制 `needs_last_leg=1` |
| **云仓直发** | 仓库为云仓（大件云仓等） | 不需要尾程；成本/补货按云仓口径（第三方仓，不负责补货） |

**证据**：[#282](https://github.com/keyapi/fzh-data/pull/282)；`docs/reference/monthly-tail-cost-pipeline.md`（模块内）。

## 4. 非商品与白名单（边界）

- 非商品/耗材（`BUTTONKIT*`、`PP<n>LB`、`DLZYFX001`、`COTTON-EU`）四列显式 0，不进待审。
- FBA 未登记 SKU 白名单只做**建议**，不自动改成本。
- 哪些品类应清零（旧 Colab 白名单：创意床品/创意方抱枕/异形沙包坐墩/棉包/售后针线扣）属**历史证据**，当前以 [03](03-price-matrix.md) 与本地白名单为准。

**证据**：[08-special-cases.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/08-special-cases.md)（历史）；`non_product_skus.csv`（本地）。
