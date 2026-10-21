---
okf: v0.1
type: Handoff
title: 给 Codex 的 G1 同步（合并版 2026-10-20）
description: 业务架构、皮壳 1:1、映射、出库消耗毛量与对账、补发/退货、WayfairCG/3PL 供货归属、美东/美中与产能交期、Codex 待办
date: 2026-10-20
status: consolidated-sync
tags: [supply-chain, codex, g1, sync, consolidated]
---

# 给 Codex 的 G1 同步（合并版，2026-10-20）

> 本文件是当前**唯一同步口径**；前几轮碎片消息以本文件为准。
> Claude #300 实质更新 `1dafa7b2`、G1B01–09 修复 `f6e97f39`、RR01–RR08 修复 `6ebc03c4`、
> T01–T06 修复（本轮）；Codex #301 最新 `93e6bd1f`（接受批量方向，T01–T06 待复核）；
> **已修 presence/SE/完整性入口，下一轮审 T01–T06 与 E01–E04，不重做综述**。

## 0. Codex 当前所处位置（先对齐）

- Codex 最后收到的是 **#300 `6d0a1324`** 时的同步：
  架构 / 1:1 皮壳 / 20261016 映射 / C21–C25 / 暂停 G1b。
- Codex 已在 **#301 `c854800e`** 回应：
  - 接受 1:1 皮壳；C21–C25 完成，25/25 通过；`mapping_process.md` §0–§4 复审完成；
  - 要求 33,719 改称**匹配毛量**；退货仓 165 按交易事件核实；未匹配不得直接判非 family。
- Codex 已在 **#301 `852d7791`** 完成本轮契约同步：
  - 更新基线/G1 范围/§3–§4 定向复审；新增 C26–C35，**35/35 合成样例通过**；
  - **接受 Claude 带显式假设与 unknown 启动 G1b**，不必继续等固定 3PL 归属；
  - 要求真实回放保留：①退货已计入库存时不得再次冲减；②调拨完成≠Wayfair 实收、
    历史供货占比≠当前库存归属；③美中 new cohort run-rate 需考虑上架、有货曝光、断货；
  - 交付物：输入 manifest、逐行去向、数量守恒、假设/unknown 清单。
- **Codex 尚未收到**：
  1. WayfairCG 库存口径（后台手工导出、通途/赛狐调拨≠在手、赛狐无 Wayfair 平台仓 API）；
  2. WX 反馈（美东稳定/美中结构断点、operator/listing/cohort、产能交期区间）；
  3. 本轮报告修正（出库消耗毛量、全量去向对账、退货仓正数出库、C31–C32）；
  4. **最新澄清（本轮新增）**：补发计入出库消耗；三角退货按 5% 情境；WayfairCG 供货归属看调拨单、不固定 USNJ/USTX。
- 所以本次给 Codex 的是 **`c854800e` 之后的增量合并**，不是让它重做。

## 1. 当前状态

- Codex #301 `93e6bd1f`：接受批量 ETL 方向；RR 大部分修复；T01–T06 仍待修
  （未返回 SKU 当零、SE missing_doc 丢 WO、hash/manifest、缺请求仓、逐仓 complete、窗口过滤）。
- Claude 本轮：修 T01–T06；presence 重算 129 observed_zero / 2 missing / 192 <2月 / 127 unknown；
  E01–E04 写入 `15-full-family-etl.md`；Wayfair 仍 `unknown_authority`。
- **当前状态**：适配器修复完成；全 family 批量 PoC 未实现；G1 未验收。
- **G1b 已启动**：补发计入；退货**不在库存净算中二次冲减**（5% 只作未来需求情景）；
  WayfairCG 供货归属缺数据标 `unknown`；已跑 CENTRADE + DANEEY 库存快照与 1 个头部 SKU 的 EN 单据试点。

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

## 4. G1 出库消耗毛量与全量去向对账（2026-04..09）

> 订单文件是出库/销售行，**没有负数退货行**。补货看**库存消耗**，不看会计口径的“销量”：
> 正常销售、补发/换货都是出库消耗，都应计入；退货是反向流，只有退回并重新入库可再售时才冲减。
> 33,719 是 **family 出库消耗毛量（含补发）**，不是净需求，也不是净库存消耗。

| 类别 | 行数 | 件数 | 说明 |
|---|---:|---:|---|
| base 码命中 | 32,634 | 33,452 | 分公司出库（多数成品销售，也含补发）→ 1:1 皮壳 |
| `-Cover` 命中 | 254 | 267 | 皮壳例外 |
| **family 出库消耗毛量** | **32,888** | **33,719** | **含补发**；不是净需求 |
| 其中：退货仓 family | 164 | 165 | **正数出库销售**（Amazon/Wayfair/OSTK，`是否补发货=否`），不是退货，照常计入 |
| 其中：family 补发 | 66 | 72 | `是否补发货=是`；**已包含在毛量中，计入补货**；不另加/不净扣 |
| 非 family 退货仓 | 148 | 152 | 其他产品，out of scope |
| 未匹配 text-tri | 763 | 931 | 标 `pending`，不直接判非 family |
| 其余非 family | 11,330 | 13,544 | out of scope |
| **合计** | **45,129** | **48,346** | 对账：32,888+763+11,330+148=45,129；33,719+931+13,544+152=48,346 |

- 之前基于 Cost Review 数据的“124 行非 family”结论**撤回**。
- 退货/贷项不在订单文件；退货单/贷项/平台退货事件另取，不能靠订单文件净扣。

### 4.1 补发（M 后缀）

| 口径 | 行 | 件 | `是否补发货=是` | `是否补发货=否` |
|---|---:|---:|---:|---:|
| 全量 Mxxx | 286 | 333 | 172 | 114 |
| family Mxxx | 115 | 124 | 64 | 51 |

- M 后缀不是唯一判据：family 里 `是否补发货=是` 66 行/72 件，其中 64 行带 M 后缀；
  另有 51 行 Mxxx 但 `是否补发货=否`。需结合 #294 补发口径与渠道/订单规则判断。
- family Mxxx 渠道（行）：Amazon 52、manomano 47、Wayfair 7、Cdiscount 3、PotteryBarn 2、
  HOME24 1、Mirakl 1、allegro 1、Shopify 1。
- 上述 Mxxx 是快速聚合（按订单号后缀），未逐单核；用于量级判断，逐行以 #294 与原始订单为准。
- **补发是出库消耗，已含在 33,719 中；计入补货，不另加、不净扣。**

### 4.2 退货（反向流，5% 情境）

- 订单文件无退货/贷项/负数行；退货必须来自退货单、贷项通知或平台退货事件。
- **库存净算不冲减退货**：已回库的退货已在 `available`，再从需求扣一次就是双扣；
  未回库/报废也不冲减。33,719 直接作为对照当前库存的需求基线。
- 三角退货率暂按 **5% 只作未来需求情景**（`confidence=low`）；本期参考量约 1,682 件。
  它**不用于当前库存净算**，不能与已回库库存重复抵扣；其他品类/新品另定。
  未来可从 Amazon 结算 V2 / 退货报表取实际值并配置化。
- 若退货尚未回库但预计会回库再售，应作为**未来供给**（in-transit/receipt）单列，而不是减需求。
- 退货后又补发：补发已在毛量中，退货回库已在库存中，同样不再重复冲减。

## 5. WayfairCG / 其他 3PL

- **WayfairCG-Cranbury 是下游 3PL**：美国分公司把成品发到 WayfairCG，再卖给顾客。
  - family 销售 **1,162 件/6 个月**（占毛量 3.4%）计入总需求；
  - 分公司→WayfairCG 的**转移不是新增需求**；净算时把 WayfairCG 库存/在途算进去，避免重复。
- **库存口径**：以 **Wayfair 后台手工导出**为准（YTQ 下载）；通途/赛狐调拨≠实际在手，到货可能丢件。
- 赛狐「平台仓」API 只有 **Temu/Mercado/Walmart WFS**，**无 Wayfair**；暂时不能 API 抓取。
- 无后台数据：标 `unknown` + 安全缓冲，不补 0；`transfer vs receipt` 对账，差额进 `discrepancy`。
- 其他 3PL：2026-04..09 没有 family 销售；海绵 `-Foam` 是另一条组件流，不是皮壳需求。
- **供货归属不固定**：不一定整仓由 USNJ 或 USTX 供，可能按 SKU 分流、也可能随时间变化。
  必须看**通途/赛狐调拨单**，不能从 Wayfair 销售渠道反推。
  - **调拨完成 ≠ Wayfair 实收**；历史供货占比 ≠ 当前库存归属。
    当前库存用 Wayfair 后台实盘；归属用近期调拨，缺数据标 `unknown`。
  - 赛狐 `POST /api/warehouseTransfer/pageList.json`：`warehouseId`=发货仓、
    `targetWarehouseId`=收货仓、`items[].commoditySku`、`items[].goods`、
    `status`（0草稿/1待审核/2待调拨/3待入库/4已完成/5已驳回/6已作废）、`createTime`；
    可按 `targetWarehouseIds` 过滤 WayfairCG、按 `start/end` 取区间。
    见 `SELLFOX_API/docs/api-reference/仓库/调拨单/调拨单列表.md`。
  - 新增 `3pl_supply_allocation(sku, 3pl_warehouse, source_branch, period, transfer_qty,
    in_transit_qty, transfer_no, source, confidence)`；有已完成调拨按量分配，多来源按 SKU 拆；
    只有在途标 `in_transit`；无数据标 `unknown` + 情景（销售占比或 50/50），**不得断言固定来源**。
  - 该分配只影响**分公司级净算**（把 WayfairCG 库存/在途挂到哪个分公司），
    不改变 family 总需求；WayfairCG 总需求只计一次。

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
   - 33,719 = **family 出库消耗毛量（含补发）**，不是净需求/净消耗；
   - 补发计入出库消耗，不另加、不净扣；M 后缀不是唯一判据；
   - 退货按 5% 情境（三角），`restock_share` 未知，输出 0%/50%/100% 敏感性；其他品类不能复用 5%；
   - 美东/美中分仓，不混池；
   - WayfairCG 下游 3PL、库存 manual/unknown、供货归属按调拨单分配；
   - 删除“完成品两仓/皮壳仓排除/品类文本纳入/124 行非 family/补发待核”等旧结论。
2. **C21–C25 + C26–C35 已完成（35/35）**；下一轮审核真实回放，不再改综述：
   - C26：下游 3PL 销售计入毛量，分公司→3PL 转移不重复计；
   - C27：3PL 库存 manual/unknown；通途/赛狐调拨≠在手；丢件进 discrepancy；
   - C28：美中新运营 cohort/ramp，历史不可外推；美东稳定可回测；
   - C29：产能/交期区间/情景，不输出固定 3 个月到货日；
   - C30：operator/listing/cohort 维度，不得混池；
   - C31：出库消耗毛量≠净需求；补发计入；退货是反向流；
   - C32：全量输入去向对账；未匹配 pending，不直接判非 family；
   - C33：3PL 供货归属按调拨单（发货仓→收货仓→SKU→数量）分配，不固定 USNJ/USTX；无数据 unknown+情景；
   - C34：退货 5% 只作未来需求情景；**库存净算不二次冲减**（已回库在 available）；
   - C35：补发 M 后缀不是唯一判据；需 `是否补发货` + 渠道/订单规则，引用 #294 口径；
   - C36：退货已计入库存不得再次冲减；未回库/报废也不冲减；5% 只用于需求情景；
   - C37：调拨完成≠Wayfair 实收；历史供货占比≠当前库存归属；当前库存用后台实盘，供货归属用近期调拨/unknown；
   - C38：美中 new cohort run-rate 必须考虑 Listing 上架、有货曝光、断货；不能裸用 6 个月平均。
3. **定向复核**修正后的 `mapping_process.md` §3/§4（出库消耗毛量与去向对账、补发/退货、3PL 供货归属），记录接受/部分接受/不接受。
4. **G1b 已启动**：补发已计入，退货不在库存净算中二次冲减，WayfairCG 供货归属缺数据标 unknown；
   交付输入 manifest、逐行去向、数量守恒、假设/unknown 清单，下一轮审核实际结果。
5. 不合并 #301 到 #300；不访问生产；不写生产适配器；不改 Claude 文件。

## 8. 待业务提供/确认

1. 退货单/贷项/平台退货事件；未来可从 Amazon 结算 V2 / 退货报表取实际退货率并配置化。
   当前 5% 只作未来需求情景；已回库的退货不得再次冲减库存净算。
2. WayfairCG 调拨单与仓库映射（赛狐 `warehouseTransfer/pageList.json`；通途如可得），用于供货归属。
3. 补发 M 后缀规则与 `是否补发货` 字段覆盖范围（family 有 51 行 Mxxx 但 `是否补发货=否`）。
4. 运营/Listing 起始日期、首单日期、Listing 上线日期。
5. 历史下单→到货分布、工厂产能/节假日。

## 9. 可直接复制给 Codex（合并版）

```text
c854800e 之后的增量合并（你已完成的部分保留，不用重做）：

一、你 c854800e 已完成、保留
- C21–C25（25/25）与 mapping_process §0–§4 复审保留。
- 你要求把 33,719 改称“匹配毛量”、退货 165 按交易事件、未匹配不得直接判非 family ——
  已照办，并进一步修正为“出库消耗毛量（含补发）”。

二、报告修正（你还没看到）
- 33,719 是 family 出库消耗毛量（含补发），32,888 行；不是净需求/净消耗。
- 订单文件 45,129 行/48,346 件，无负数退货行。
- 全量去向：family 32,888 + 未匹配 pending 763 + 非 family 退货仓 148 + out_of_scope 11,330 = 45,129 行；
  件数 33,719+931+152+13,544=48,346。
- 退货仓 family 164/165 是正数出库销售（Amazon/Wayfair/OSTK，是否补发货=否），不是退货，照常计入；
  family 补发 66/72 已含在毛量中，计入补货，不另加/不净扣；未匹配 763/931 标 pending；
  之前“124 行非 family”撤回。

三、最新澄清：补发/退货（本轮新增）
- 补发是出库消耗，补货必须计入；M 后缀不是唯一判据：
  全量 Mxxx 286/333（是否补发货=是 172/否 114）；family Mxxx 115/124（是 64/否 51）；
  family 渠道 Amazon 52、manomano 47、Wayfair 7 等。
- 退货不在订单文件；三角退货率暂按 5% **只作未来需求情景**（假设，不是事实），其他品类/新品另定。
  **库存净算不二次冲减**：已回库的退货已在 available；未回库/报废也不冲减。
  5% 参考量约 1,682 件，不得与当前库存重复抵扣。
- 退货后又补发时，补发已在毛量中，退货回库已在库存中，同样不再重复冲减。

四、新增输入 1：WayfairCG/3PL
- 下游 3PL；family 销售 1,162 件计入毛量；分公司→3PL 转移不重复计。
- 库存以 Wayfair 后台手工导出为准（YTQ）；Tongtool/赛狐调拨≠在手；到货可能丢件。
- 赛狐平台仓 API 只有 Temu/Mercado/Walmart WFS，无 Wayfair；无数据标 unknown+安全缓冲；
  transfer vs receipt 对账，差额进 discrepancy。
- 供货归属不固定 USNJ/USTX，可能按 SKU 分流：用调拨单分配；
  赛狐 POST /api/warehouseTransfer/pageList.json（发货仓/收货仓/SKU/数量/状态/时间）；
  新增 3pl_supply_allocation；无数据 unknown+情景，不得断言。
- 其他 3PL 无 family 销售；海绵 -Foam 另列。

五、新增输入 2：WX 计划
- 美东稳定（2 运营），历史可回测；美中 2026-06/07/08 新运营、第二个月才下单、
  首批刚回货，历史不可参考；必须分仓，不能混池。
- demand_line/forecast_bucket 增加 operator_id/listing_id/operator_start_date/
  listing_launch_date/demand_cohort；美中用短窗 run-rate + cohort/ramp，不套 ens5/季节性。
- 产能/交期用区间/情景（如 60–120 天），输出覆盖期/缺货风险，不输出固定 3 个月到货日。

六、请 Codex 做
- 更新 g1-slice/baseline：出库消耗毛量（含补发）；退货 5% 情境；美东/美中分仓；
  WayfairCG 库存 manual/unknown + 供货归属调拨单；删除旧结论。
- 保留 C21–C25，新增 C26–C35（3PL 销售/库存/供货分配、美中 cohort/ramp、交期区间、
  operator/listing/cohort、出库消耗毛量、全量去向、退货 5%/restock、M 后缀判据）。
- 定向复核 mapping_process.md §3/§4（修正后的出库消耗毛量与去向对账）。
- G1b 可在假设下启动：补发已计入、退货 5% 情境、3PL 供货归属 unknown 不阻塞；
  需业务补退货回库比例/调拨单数据来收紧。
- 不写生产、不合并 #301、不改 Claude 文件。
```
