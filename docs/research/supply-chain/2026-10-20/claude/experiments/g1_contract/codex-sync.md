---
okf: v0.1
type: Handoff
title: 给 Codex 的 G1 同步（合并版 2026-10-20）
description: 业务架构、皮壳 1:1、映射、匹配毛量与对账、WayfairCG/3PL、美东/美中与产能交期、Codex 待办
date: 2026-10-20
status: consolidated-sync
tags: [supply-chain, codex, g1, sync, consolidated]
---

# 给 Codex 的 G1 同步（合并版，2026-10-20）

> 本文件是当前**唯一同步口径**；前几轮碎片消息以本文件为准。
> Claude #300 最新 `17dce846`；Codex #301 最新 `c854800e`；G1b 暂停。

## 1. 当前状态

- Codex #301 `c854800e`：已接受 1:1 皮壳模型；C21–C25 完成，25/25 合成样例通过；Cost Review 不作数据源。
- Claude #300 `17dce846`：已把 33,719 改为**匹配毛量**；补全全量输入去向对账；G1b 暂停。
- **G1b 暂停**，等两件事：退货/贷项/补发交易事件；WayfairCG 由 USNJ 还是 USTX 供货。

## 2. 公司架构与需求模型

`docs/company-context.md:14-29`：

- 绍兴生产皮壳/内胆/半成品 → **USNJ(CENTRADE)、USTX(DANEEY)、波兰** 三个分公司仓；
- 分公司填充 PP 棉、压缩、包装、仓储、发货；
- 最终卖给顾客的**多数是成品**；个别订单只卖皮壳。
- 三角靠枕类：绍兴只发**皮壳**；成品销售 **1:1 消耗皮壳**；`-Cover` 是只卖皮壳的例外。
- **皮壳仓是分公司仓，不是皮壳产品仓**；其 family 销售行产品名是「三角…靠枕」。

## 3. 映射规则

- **唯一主映射**：`EN产品BOM成本列表20261016.xlsx` 的 `产品编号` + `客户物料号`，按通途SKU 精确匹配。
- EN Tongtool Cost Review：**只借代码逻辑**（直连、后缀、GSheet 源头修正），**不用其数据**。
- Colab/GSheet 4.2：仅兜底；本次未介入。
- 品类/产品名只作未匹配诊断，**不作纳入条件**。
- BOM：KS0001/KS0248 1,739 行，全部 `绍兴发货方式=皮壳`；有效客户码 1,489（base 1,200 / Cover 287 / out 2）；空 142、删除 108。

## 4. G1 匹配毛量与全量去向对账（2026-04..09）

> 订单文件是出库/销售行，**没有负数退货行**；33,719 是**匹配毛量，不是净需求**。

| 类别 | 行数 | 件数 | 说明 |
|---|---:|---:|---|
| base 码命中 | 32,634 | 33,452 | 成品销售 → 1:1 皮壳 |
| `-Cover` 命中 | 254 | 267 | 皮壳例外 |
| **family 匹配毛量** | **32,888** | **33,719** | **不是净需求** |
| 其中：退货仓 family | 164 | 165 | **正数出库销售**（Amazon/Wayfair/OSTK，`是否补发=否`），不是退货，不能按仓名扣 |
| 其中：family 补发 | 66 | 72 | `是否补发=是`；是否算新增需求待交易事件 |
| 非 family 退货仓 | 148 | 152 | 其他产品，out of scope |
| 未匹配 text-tri | 759 | 925 | 标 `pending`，不直接判非 family |
| 其余非 family | 11,334 | 13,550 | out of scope |
| **合计** | **45,129** | **48,346** | 对账：32,888+759+11,334+148=45,129；33,719+925+13,550+152=48,346 |

- 之前基于 Cost Review 数据的“124 行非 family”结论**撤回**。
- 退货/贷项/补发需退货单/贷项/补发交易事件；订单文件里没有负数行。

## 5. WayfairCG / 其他 3PL

- **WayfairCG-Cranbury 是下游 3PL**：美国分公司把成品发到 WayfairCG，再卖给顾客。
  - family 销售 **1,162 件/6 个月**（占毛量 3.4%）计入总需求；
  - 分公司→WayfairCG 的**转移不是新增需求**；净算时把 WayfairCG 库存/在途算进去，避免重复。
- **库存口径**：以 **Wayfair 后台手工导出**为准（YTQ 下载）；Tongtool 调拨≠实际在手，到货可能丢件。
- 赛狐「平台仓」API 只有 **Temu/Mercado/Walmart WFS**，**无 Wayfair**；暂时不能 API 抓取。
- 无后台数据：标 `unknown` + 安全缓冲，不补 0；`transfer vs receipt` 对账，差额进 `discrepancy`。
- 其他 3PL：2026-04..09 没有 family 销售；海绵 `-Foam` 是另一条组件流，不是皮壳需求。
- **待确认**：WayfairCG 由 USNJ 还是 USTX 供货（订单成本来源只写美国公司/COST-US，数据判断不了）。

## 6. 美东/美中与产能交期（WX 反馈）

- **美东 USNJ/CENTRADE**：稳定，2 个运营；历史可回测，用 ens5/TSB + 断货删失。
- **美中 USTX/DANEEY**：2026-06/07/08 新运营入职、第二个月才下单、首批刚回货；
  **历史不可直接参考**；用短窗 run-rate + 运营/Listing cohort + 新品 ramp，不套 ens5/季节性/全历史。
- `demand_line` / `forecast_bucket` 增加 `operator_id`、`listing_id`、`operator_start_date`、
  `listing_launch_date`、`demand_cohort`；不允许把新老运营混池。
- **产能/交期不确定**：lead time 用区间/情景（如 60–120 天）+ 产能约束；
  输出覆盖期与缺货风险区间，**不输出固定 3 个月到货日**，不要把 3 个月写成事实。
- 需要数据：运营名单/入职日期/首单日期、Listing 上线日期、历史下单→到货分布、工厂产能/节假日。

## 7. Codex 现在应做

1. **更新 `g1-slice.md` / `baseline.md`**：
   - 33,719 = 匹配毛量，不是净需求；
   - 美东/美中分仓，不混池；
   - WayfairCG 下游 3PL、库存 manual/unknown；
   - 删除“完成品两仓/皮壳仓排除/品类文本纳入/124 行非 family”等旧结论。
2. **保留 C21–C25，新增 C26–C32**：
   - C26：下游 3PL 销售计入毛量，分公司→3PL 转移不重复计；
   - C27：3PL 库存 manual/unknown；Tongtool 调拨≠在手；丢件进 discrepancy；
   - C28：美中新运营 cohort/ramp，历史不可外推；美东稳定可回测；
   - C29：产能/交期区间/情景，不输出固定 3 个月到货日；
   - C30：operator/listing/cohort 维度，不得混池；
   - C31：匹配毛量≠净需求；订单文件无负数退货行，退货/贷项/补发必须用交易事件；
   - C32：全量输入去向对账；未匹配 pending，不直接判非 family。
3. **定向复核**修正后的 `mapping_process.md` §3/§4（匹配毛量与去向对账），记录接受/部分接受/不接受。
4. **暂不进入 G1b/实现**：等退货/补发交易事件 + WayfairCG 供货归属确认。
5. 不合并 #301 到 #300；不访问生产；不写生产适配器；不改 Claude 文件。

## 8. 待业务提供/确认

1. 退货/贷项/补发交易事件（退货单、贷项通知、补发记录）：订单文件里没有负数行。
2. WayfairCG 由 USNJ 还是 USTX 供货。
3. 运营/Listing 起始日期、首单日期、Listing 上线日期。
4. 历史下单→到货分布、工厂产能/节假日。

## 9. 可直接复制给 Codex（合并版）

```text
G1 合并版同步（以本段为准，前几轮碎片消息作废）：

一、架构与需求
- 绍兴生产皮壳/内胆/半成品 → USNJ(CENTRADE)、USTX(DANEEY)、波兰分公司
  填充 PP 棉/压缩/包装/发货；最终销售多数成品，个别只卖皮壳。
- 三角靠枕类绍兴只发皮壳；成品销售 1:1 消耗皮壳；-Cover 是皮壳例外。
- 皮壳仓是分公司仓，不是皮壳产品仓。

二、映射
- 唯一主映射：EN产品BOM成本列表20261016.xlsx 的产品编号+客户物料号，按通途SKU 精确匹配。
- EN Tongtool Cost Review 只借代码逻辑，不用其数据；Colab 4.2 仅兜底；品类文本只作诊断。

三、匹配毛量与对账（2026-04..09）
- 33,719 是 family 匹配毛量，不是净需求；32,888 行。
- 订单文件 45,129 行/48,346 件，无负数退货行。
- family 32,888 + 未匹配 pending 759 + 非 family 退货仓 148 + out_of_scope 11,334 = 45,129 行；
  件数 33,719+925+152+13,550=48,346。
- 退货仓 family 164/165 是正数出库销售，不是退货；family 补发 66/72 待交易事件；
  未匹配 759/925 标 pending，不直接判非 family；之前“124 行非 family”撤回。

四、WayfairCG/3PL
- 下游 3PL；family 销售 1,162 件计入毛量；分公司→3PL 转移不重复计。
- 库存以 Wayfair 后台手工导出为准（YTQ）；Tongtool 调拨≠在手；到货可能丢件。
- 赛狐平台仓 API 只有 Temu/Mercado/Walmart WFS，无 Wayfair；无数据标 unknown+安全缓冲；
  transfer vs receipt 对账，差额进 discrepancy。
- 其他 3PL 无 family 销售；海绵 -Foam 另列。
- 待确认：WayfairCG 由 USNJ 还是 USTX 供货。

五、美东/美中与交期（WX）
- 美东稳定（2 运营），历史可回测；美中 2026-06/07/08 新运营、第二个月才下单、
  首批刚回货，历史不可参考；必须分仓，不能混池。
- demand_line/forecast_bucket 增加 operator_id/listing_id/operator_start_date/
  listing_launch_date/demand_cohort；美中用短窗 run-rate + cohort/ramp，不套 ens5/季节性。
- 产能/交期用区间/情景（如 60–120 天），输出覆盖期/缺货风险，不输出固定 3 个月到货日。

六、请 Codex 做
- 更新 g1-slice/baseline；保留 C21–C25，新增 C26–C32（3PL 销售/库存、
  美中 cohort/ramp、交期区间、operator/listing/cohort、匹配毛量≠净需求、全量去向对账）。
- 定向复核 mapping_process.md §3/§4。
- G1b 暂停，等退货/补发交易事件 + WayfairCG 供货归属确认。
- 不写生产、不合并 #301、不改 Claude 文件。
```
