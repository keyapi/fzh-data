---
okf: v0.1
type: Research
title: 赛狐自动拉取 Amazon 账期 — 现状与试点可行性调研
description: 背景/可行性/两报表口径/科目映射/试点实测/SP-API与紫鸟路径/风险与短中长期；供后续 V2 解析与三方比对接手
tags: [sellfox, amazon, settlement, research, custom-transaction, dingtalk]
timestamp: 2026-09-09
resource: sellfox_settlement/reconcile_amazon.py
---

# 赛狐自动拉取 Amazon 账期（收费/税/费用）—— 现状 + 试点可行性调研

日期：2026-09-09
范围：只做 Amazon；账期月按结算周期结束日归属。形态：调研报告 + 可跑原型比对。

---

## 1. 现状（读代码/文件后确认）

**业务链路**
- 运营在钉钉提交「销售收款确认单」：一行=一条账期（一个收款单可含多条账期，按 `审批编号` 归并）。字段含 账期日期、平台、账号、销售额、佣金、广告费、退款、客户退货运费、平台月租、其他费用、收款归属、币种、应收金额。
- 金额来自运营看 Amazon 后台截图（如「结算周期 2026/7/20-8/3，净收入 US$156.32，销售额 2764.11，支出 2607.79，期初 0，账户尾号 470，8/6 转账」）+ 附件 Amazon 导出的 `.txt`。
- 财务同事按**发起时间 4号~下月3号** 归桶到 NAS（`账期YYYYMMDD-YYYYMMDD`）；文件标题 `Amazon&新平台成本 YYYYMMDD-YYYYMMDD 销售收款确认单-<ts>[ _合并汇率&账号_<ts>].xlsx`。
- 两个 Colab 后处理：
  1. `税账期TXT 挂载Gdrive.ipynb`：读每账户 Amazon 结算 `.txt`（tab 分隔、一账户一文件，如 `AMZVerDE-2026-08-04.txt`），做脆弱的「多/少 tab」修正（SKU 含空格会错列），然后按 `transaction-type / amount-type / amount-description / amount / sku / posted-date` 解析；**目前只可靠提取 Tax**。其余多平台各自另写读取（Walmart 等格式各异）。
  2. `钉钉OA收款费用Amazon多平台&附加费&Tax 20250704.ipynb`：读钉钉导出 xlsx → `approval_filter = (审批状态∈['完成','审批中']) & 审批结果!='拒绝'`（并剔除「4月已提交」审批单）→ 合并汇率 → 累加 `收款费用累加外币/人民币` → 合并 `附加费{YYYYMM}` 与 `Tax{YYYYMM}` → FBA 扣减 → 写回 gsheet `钉钉OA收款费用Amazon多平台&附加费&Tax`。

**收入/费用口径**：Amazon 收款在钉钉里拆成 销售额/佣金/广告/退款/费用 等多列；税(Tax)单独从 txt 解析后写 `Tax{YYYYMM}` 再合并；附加费另有 `附加费{YYYYMM}` 表（人工）。

## 2. 问题（与用户描述一致）

- 依赖运营 **3 号前按时提交**、金额靠人填**易错**；
- 审批有 完成/审批中/撤销/拒绝 不确定性（代码只假设"大部分通过"），撤销/拒绝会污染，需反复再导出（7 月桶曾 40 单完成晚于窗口、13 单至 9/8 仍空白）；
- Amazon 结算 txt 欧洲/美国 **小数点和分隔符不同**、SKU 空格错列、同事下错格式；
- 2 年前解析只能猜科目，**实际只用 tax**，科目拆分不可靠；
- 其它多平台无固定格式、无 API（Wayfair/TikTok 等对接赛狐不确定）。

## 3. 关键发现：赛狐已把 Amazon 结算结构化存好

`财务 > 结算中心V2`（= Amazon 结算）两个端点：

| 端点 | 路径 | 关键字段 |
|---|---|---|
| 结算汇总（分页） | `POST /api/financial/v2/settlementSummary/groupPage.json` | `groupStartStr/groupEndStr`(结算周期)、`accountIncome`(销售额)、`accountRefund`(退款)、`accountExpenditure`(支出)、`accountNetIncome`(净收入)、`beginningBalance`(期初)、`endingBalance`(预留金)、`transferAmount`+`accountTail`(转账尾号)、`arrivalStatus`(到账)、`currency`、`storeName/sellerId/marketplaceId/region`、`processingStatus/fundTransferStatus` |
| 结算明细（分页） | `POST /api/financial/v2/settlementSummary/detailPage.json` | `settlementId`、`transactionType`、`amountType`、`amountDescription`、`amount`、`msku`、`fulfillmentId`、`postedDateTimeStr/siteTimeStr`、`currency`、`orderId`、`quantityPurchased` |

**结论**：
- 汇总字段 = 运营所贴截图那一页（净收入/销售额/支出/期初/尾号/到账）→ 可直接对账截图金额。
- 明细字段 = 现在人工解析的 txt 行（同构），且已可按 `startTime/endTime、shopIds、marketplaceIds、amountTypes、transactionTypes、currency` 筛选 —— 免 tab 修正、免欧美小数差异。
- `accountIncome` 等字段名与 `amount` 有符号方向需实跑核对口径。

**筛选/分页参数**：请求体 `startTime/endTime(yyyy-MM-dd)`、`shopIds[]`、`marketplaceIds[]`、`currency`、`amountTypes[]`、`transactionTypes[]`、`updateTimeStart/End`、`pageNo/pageSize`。

## 4. 多平台覆盖情况（从 `财务/多平台` API 文档）

| 平台 | 赛狐账单接口 | 覆盖 |
|---|---|---|
| Amazon | 结算中心V2（汇总+明细） | ✅（本试点） |
| Temu 全托/半托 | 利润报表-查询结算明细（交易收入/结算/广告/EPR/售后等几十个科目） | ✅ |
| TikTok | 利润报表-查询账单明细 | ✅ |
| Walmart | 利润报表-查询结算明细 | ✅ |
| eBay / AliExpress / MercadoLibre / SHEIN(全托/自运营半托/Shopify) | 多平台利润报表-查询结算明细 | ✅ |
| **Wayfair** | — | ❌ 无 |
| Home24 / Mano / Allegro / Cdiscount / EMAGRO / HOUZZ / Worten / ePrice | — | ❌ 无 |

→ **Amazon 理论上可不用人提交钉钉**；TikTok/Walmart/Temu 也可；**Wayfair 必小平台短期还得人工**（或另寻 API）。

## 5. 原型（已落地）

`sellfox_settlement/`：
- `reconcile_amazon.py`：`shops`（建店铺↔渠道账号映射）→ `fetch`（拉汇总+明细到 csv）→ `candidates`（打印未识别科目候选）→ `reconcile`（赛狐各科目 vs 钉钉定稿逐账号比对，输出差异 xlsx）。
- `README.md`：依赖（`uv run python` + SELLFOX_API_KEY）、使用、科目映射 SUBJ 初步规则。
- 复用 `SELLFOX_API/client.py` 的 `SellfoxClient`（代理/直连、限流、重试）。

## 6. 科目映射（初步，需 `candidates` 实跑校准）

| 钉钉科目 | 赛狐匹配线索（初） |
|---|---|
| 销售额 | `amountType`/`amountDescription` = Principal（Order） |
| 佣金 | desc 含 commission；amountType = Commission / Marketplacefacilitatorfee |
| 广告费 | desc 含 advertising / sponsored |
| 退款 | transactionType / amountType = Refund（负） |
| 税 | amountType = Tax；desc 含 withholding / tax |
| 平台月租 | 含 subscription / 月租 |
| 其他/未识别 | 其余（candidates 里人工补） |

**符号口径**：赛狐 `amount` 有符号；钉钉各列多为绝对值。映射后取方向/绝对值对齐，试点阶段先记录差异，逐步统一。

## 7. 风险 / 待量化

1. **时点**：Amazon 转账在周期结束约 3-5 天后，赛狐经 SP-API 同步可能再滞后 → 测"4 号前能否取全上一月结算"。
2. **口径/符号**：Income/Expenditure、amount 符号 vs 钉钉各列；广告/佣金是否已含在 Amazon 支出内。
3. **周期↔自然月**：Amazon ~14 天结算，`groupEndStr`（如 08-03）贴近"4~3"窗口边界；`账期月=groupEnd月` 规则要验证不重不漏。
4. **收款归属/汇率**：赛狐无收款归属维度，需按现有「渠道账号→收款归属」映射；多渠道多币种用现有汇率表折算。
5. **科目映射不全**：未识别 amountDescription → 归「其他/待确认」，逐步补到映射表。

## 8. 短 / 中 / 长期路径

- **短期（本次）**：跑通 Amazon 自动取回+科目映射，量化 vs 运营提交的误差与覆盖率；钉钉照旧作对照。顺手做「渠道账号大小写/别名统一」与「科目映射表」。
- **中期**：误差可控后，Amazon 金额/科目改赛狐自动取值（运营仍提交/审批，金额自动带出或超阈值才提示）；复用同法到 TikTok/Walmart/Temu；用赛狐 `arrivalStatus/updateTimeStr` 补齐"审批中→完成"与到账状态，弱化审批不确定性。
- **长期**：对接钉钉（Stream API）自动取 发起/完成/撤销/拒绝 状态 + 自动代填；Wayfair 及小平台保持人工或另寻 API；把「账期→科目→收款归属→汇率→回款率」统一为一套数据流（可并入现有 `platform_account_reconciliation` 回款率/对账模式）。

## 9. 参考

- 本地 API 文档：`SELLFOX_API/docs/api-reference/财务/结算中心V2/{结算汇总-分页查询,查询结算明细-分页查询}.md`；索引 `SELLFOX_API/docs/api-reference/llms.txt`。
- apifox 端点：结算汇总 api-399397942、结算明细 api-399397941、发货与结算V2 api-399397943（apifox.cn）。
- 赛狐客户端复用：`SELLFOX_API/client.py` `SellfoxClient`；代理基址 `https://api.vilavi.cn/sellfox/v1/sellfox-main`。
- 收入/费用模型参照：`D:\Work\王忠于\成本核算` 下 `Amazon&新平台成本 *[_合并汇率&账号_].xlsx`（钉钉定稿）。
- 口径来源：`G:\我的云端硬盘\Colab Notebooks\成本核算\透视表订单\钉钉OA收款费用Amazon多平台&附加费&Tax 20250704.ipynb`、`税账期TXT 挂载Gdrive.ipynb`。

---

## 10. 试点实测（2026-06）

**已跑通**：用代理 Key 成功拉取。`fetch --start 2026-06-01 --end 2026-07-10 --month 202606`：
- 结算汇总（groupPage，`timeType=settlementEndTime`）：**134 条**；按 `groupEndStr` 归属 2026-06 的结算 **103 条**。
- 结算明细（detailPage，posted 日期窗口 06-01~07-10）：**38,799 行**；按 June settlementId 命中 **16,801 行**。

**口径实测发现（重要）**
1. `summar.groupEndStr` 格式为 `2026/06/16 06:16:48`（**斜杠**），日期解析要 `replace('/','-')`（我最初用 `-` 解析导致月份过滤=0）。
2. **结算明细 `currency` 全为 CNY**，`amount` 是**人民币**（赛狐按汇率折算）；`summar.currency` 才是站点币（USD/EUR…），`accountNetIncome/Income/Expenditure/Refund` 是**站点币**。→ 十字核对：明细(CNY)/汇率≈汇总(站点币)，实测 EUR≈7.84、USD≈6.73、GBP≈9.13、CAD≈4.88，匹配市场汇率。
3. `accountNetIncome = accountIncome + accountExpenditure + accountRefund`（退款已为负）；如 北京如森-Rucener-DE：2119.72 − 2189.21 − 574.72 = −644.21 ✓。
4. 明细按 posted 日期窗口会**几乎完整**（单结算 合计(CNY) 约 = 汇总净×汇率，差 <1%），但严格完整应加大窗口或按 settlementId（detailPage 强制要求 startTime/endTime，无法纯 settlementId 检索）。
5. **科目齐全**：`transactionType`(Order/Refund/AmazonFees/FBAFees/ServiceFee/…)、`amountType`(ItemPrice/ItemFees/ItemWithheldTax/Promotion/Cost of Advertising/…)、`amountDescription`(Principal/Commission/Tax/MarketplaceFacilitatorTax-Principal/FBAPerUnitFulfillmentFee/Subscription Fee/…)。→ 可映射到钉钉 销售额/佣金/广告/税/退款/平台月租/其他。

**2026-06 汇总对比（赛狐明细RNB vs 钉钉 Amazon-only 列RMB；钉钉已去重 & 只留 选择平台=亚马逊）**

| 科目 | 赛狐（汇总） | 钉钉（Amazon-only） | 差异 | 说明 |
|---|---|---|---|---|
| 销售额 | 1,600,913.56（Principal+促销净额） | 2,125,659.02 | −524,745 | 差额=运费/税/口径 |
| 佣金 | −245,304.75 | 380,449.68 | 口径差 | 钉钉为绝对值 |
| 广告费 | −276,279.56 | 322,368.18 | 口径差 | 钉钉含广告成本口径 |
| 退款 | +7,203.04 | 94,794.34 | 大 | 退款方向/口径待确认 |
| 平台月租 | −2,395.55 | 0 | 小 | |
| 税(含VAT) | +1,553.40 | （另 Tax 表） | — | 钉钉税在 Tax{YYYYMM} |
| 其他/未识别 | −142,845.01 | 96,620.71 | 口径差 | 未识别=多条费用需 ladder |

**结论（试点）**
- 可行性：**赛狐已把 Amazon 结算结构化存好**，汇总=截图页、明细=txt 行同构，能自动取回；**金额/科目层面可以替代运营手动读数**。
- 不能一步到位的原因（需业务确认）：① **storeName→渠道账号** 映射（如 `北京如森-Rucener-DE` ↔ `AMZRosoonDE`），来自 EN 渠道账号 gsheet（df_account），不在本 API 里；② **科目口径**：钉钉各列（尤其 销售额/佣金/退款/税）与赛狐 amountType/amountDescription 的对应关系需人工确认后写死映射表；③ 钉钉文件 **Amazon 与 新平台 混排**，比对须按 选择平台 分流。
- 时长/时点未测：结算在周期结束 3-5 天后才有，赛狐同步再滞后，需验证“4 号前能否取全上月”。

**产物**：`sellfox_settlement/reconcile_amazon.py`（shops/fetch/candidates/reconcile）；`sellfox_settlement/out/amazon_june_compare.xlsx`（汇总对比 + 赛狐_by店铺 + 钉钉_by账号 + 科目候选 ladder）；数据 `sellfox_settlement/data/saihu_amazon_202606/`（summary/detail csv）。

**下一步（需你提供）**
1. `storeName ↔ 渠道账号（AMZ…）` 映射：指给我 EN/渠道账号 gsheet（df_account）或直接给我映射表，我就能做逐账号比对。
2. 确认钉钉“销售额 / 佣金 / 退款 / 税”的**取数口径**（分别对应赛狐哪些 amountType/amountDescription），我来固化 `科目映射`。

---

## 11. 关键进展：自定义报表 + 币种 + 科目解析（2026-09）

用户补充了重要线索，实测/调研结论：

### 11.1 阿里后台「自定义报告」（财务已按月下载，用于税务报税）
`SELLFOX_API/2026Apr1-2026Jun30CustomSummary(1).pdf` + `2026Apr1-2026Jun30CustomTransaction(1).csv`：
- **CustomTransaction CSV（982 行）** = 阿里「报告库→标准订单→交易一览（自定义列）」：**按订单/SKU 一行**，列含 `date/time, settlement id, type(Order/Refund/Service Fee/FBA Inventory Fee/…), order id, sku, quantity, marketplace, fulfillment, product sales, product sales tax, shipping credits, shipping credits tax, gift wrap credits, giftwrap credits tax, Regulatory Fee, Tax On Regulatory Fee, promotional rebates, promotional rebates tax, marketplace withheld tax, selling fees, fba fees, other transaction fees, other, total, Transaction Status, Transaction Release Date`。**全 USD**（"All amounts in USD"），`description` 里 `Cost of Advertising` 即广告行。
- **CustomSummary PDF** = 阿里**结算汇总 statement**，按类目列 `Net sales/credits/refunds / Product...taxes...collected / Selling fees / FBA inventory & inbound fees / Cost of Advertising / Service fees / Shipping label purchases / Liquidations fees / … / Net fees / Net deposits & withdrawals`，也是 USD。

**→ 这基本解决了最大的难点「科目解析」。** 因为是**列式**（每种费一个列），直接对应钉钉列：

| 钉钉科目 | CustomTransaction 列 / 规则 |
|---|---|
| 销售额 | `product sales`（Refund 行取负） |
| 税 | `product sales tax + shipping credits tax + giftwrap credits tax + Tax On Regulatory Fee + marketplace withheld tax` |
| 佣金 | `selling fees` |
| FBA费用/仓库费 | `fba fees`（+ FBA Inventory Fee 行） |
| 广告费 | `description=='Cost of Advertising'` 行 |
| 退款 | `type in (Refund, Refund_Retrocharge)` 行 |
| 运费（客户付） | `shipping credits + shipping label purchases` |
| 其他费用 | `other transaction fees + other` |
| 净额 | `total` |

对照：赛狐 V2 明细是同一底层数据的 **amount-description 行式**（Principal/Commission/Tax/MarketplaceFacilitatorTax-Principal/FBAPerUnitFulfillmentFee/Subscription Fee/…），标准映射（见 11.3）同样可做，只是不如列式直观。

### 11.2 币种：赛狐明细**可以给原币**
实测 `detailPage` 传 `currency` 参数：默认 **CNY**（赛狐折算，变动汇率）；传 `currency=USD` 返回 **USD 原币**（amount=−8.54 等）。→ 不是「只有 RMB」。但要原币需**按币种分别拉**（一个结算一种币；跨月多币种要循环）。建议：**原币 + 财务固定月汇率**折算（与 colab 一致），避免赛狐每日变动汇率。

### 11.3 标准结算报告 amount-description 映射（Web 调研，权威）
- transaction-type: Order / Refund / Adjustment / ServiceFee / other-transaction(MiscEvent)。
- amount-type: ItemPrice / ItemFees / ItemWithheldTax / Promotion / other-amount。
- amount-description 常见值：Principal, Commission, FBAPerUnitFulfillmentFee, StorageFee, StorageRenewalBilling, Shipping, ShippingTax, RefundCommission, ShippingChargeback, Tax, MarketplaceFacilitatorVAT-Principal/Shipping, DigitalServicesFee, DisposalComplete, Current Reserve/Previous Reserve Amount, Shipping label purchase。
- **广告**：on-account 广告出现在结算报告（对应赛狐 `Cost of Advertising`）；off-account 广告**不在**结算报告 → 结算口径的 TACoS 会低估，需另取 SKU Economics 广告报告。
- 一单 5–9 行；**按 posted-date 记**（勿用 order-date）；`amount` 有符号。

### 11.4 落地建议（结合「销售额来自通途、费用来自钉钉/账期」）
- **费用侧**用这套报告/赛狐，**销售额仍走通途**（用户口径）。
- 推荐路径：**优先用 CustomTransaction CSV（列式+原币+财务已在用）**做 Amazon 费用科目解析，逐月出表；**赛狐 V2 明细（currency=原币）** 做自动取回 + 交叉核对。Wayfair/小平台短中期仍人工。
- 待办：① storeName↔渠道账号 映射（渠道账号 gsheet 尚无赛狐店名，需 YB 补或我出候选表核对）；② 用列式报告核对/固化「钉钉科目→列」口径（现基本直给）；③ 加 `currency` 参数取原币、用固定月汇率折算。

---

## 12. 赛狐能否获取 CustomTransaction + storeName↔渠道账号 落地（2026-09）

### 12.1 赛狐 API 能否拿列式 CustomTransaction —— 已核实
**结论：赛狐 OpenAPI 不能原生生成列式（Custom Transaction）报表；但能把「紫鸟/赛狐插件已抓取到的 Amazon 报表文件」接口暴露出来。**
- 原生结构化无：`财务/结算中心V2/查询结算明细` 返回的是 amount-description 行式(`transactionType/amountType/amountDescription/amount/…`)，非 order/SKU 列式。`数据/自定义报表`、`利润报表V2-订单` 都是维度/订单聚合，不是交易行。
- 可取抓取文件：`报告中心/插件获取报告/插件获取报告.md` → `POST /api/report/center/task/getPlugPageList.json`，返回已抓任务的 `fileUrls`(1h 有效) 的 CSV/ZIP；`reportTypeList`：**3=Transaction、4=Summary、5=Deferred transaction、6=FBAInboundConvenience**。**type=3 Transaction** 与卖家后台「日期范围/自定义交易一览」最接近。
- 但只能**列已抓文件**，不能主动生成新的日期范围；要想有文件，需先让**紫鸟+赛狐插件**抓取。
- 另有 `报告中心/亚马逊原报告 add.json`(报告类型枚举 无 settlement/Transaction)、`报告中心/赛狐报告 createTask.json`(仅 PRODUCT_SALE_REPORT)。
- 权威(SP-API)：列式报告官方 API 无对应 reportType（MWS `GET_DATE_RANGE_FINANCIAL_TRANSACTION_DATA` 也被拒），**只能 UI 浏览器**；`GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`=赛狐 V2 明细同源。

**→ 两条路可并存（用户要"2者兼顾"）**：
1. 列式 CustomTransaction（活动/activity/pasted、原币、财务/税报用）：**紫鸟+赛狐插件抓** → 赛狐 `getPlugPageList(type=3)` 拿文件 → 解析。需先启用紫鸟赛狐插件并让运营/财务抓当月。
2. 赛狐结算V2（payout 口径，自动）：`currency` 参数可取原币；已能自动拉。**注意两种报表口径不同(activity vs payout)，总额天然不同，别直接对等**。

### 12.2 storeName ↔ 渠道账号 —— 落地
- 读共享表「和运营部共享/渠道账号（20260521起在此维护）」+ 旧表(来自和财务共享)，用**收款主体(实体)→账号族** + **站点** 自动匹配（忽略赛狐随意填的品牌后缀如 Jalnoddsa/LELEFIDO/WOWMAX/Xalviortex）。
- 关键确认：北京熙锦(XJ)→AMZBJXJ、Daneey-LELEFIDO-CA→AMZDANEEYCA、CA=加拿大、TR=土耳其、IE=爱尔兰、**北京固祥 未启用(无销售/账期) 排除**。
- **已写入 gsheet**：在 `渠道账号`+`渠道账号别名` 列右侧新增一列 **`赛狐店铺`**（当前落在最右列 AU，可在表头拖到别名旁）；按 `渠道账号` 命中 **填了 61 行**；并在表末尾**追加 2 行账号**（`AMZDANEEYCA`(Daneey-LELEFIDO-CA)、`AMZBJRYECLTDCA`(北京如泱-BJRYECLTD-CA)，别名/运营分组待补）。无当月数据、或未启用的店留空(如 VERCART-*、君缘-TR/IE、北京熙锦-CA、方州汇绍兴-CA/MX、北京固祥-*)。
- 产物：`sellfox_settlement/out/storeName_to_account_candidates.csv`(含 店铺/收款主体/品牌/站点/归属族/渠道账号/状态)。
- 待 YB 确认：新增 2 行账号的 别名/运营分组/运营人员；以及是否补「通途有订单但无赛狐店名」的账号（通途未在手，未做）。

---

## 13. 实测验证 + 两表对比 + gsheet 落地（2026-09）

### 13.1 紫鸟/赛狐插件「列式报表」—— 亲自实测成功
- `POST /api/report/center/task/getPlugPageList.json`，`reportTypeList` **一次传一个**（传多个报"报告类型参数错误"）。
- `reportType=3`(Transaction, 月度)=列式表；real 拉到 `totalSize=53`；`reportType=4`(Summary)=26。
- **下载实测**：`fileUrls` 是 **ZIP**（内含 `2026-06MonthlyTransaction.csv`），解压后表头 = 财务那份 Custom Transaction，**32 列**（比财务的 31 列多了 `account type`）：
  `date/time, settlement id, type, order id, sku, description, quantity, marketplace, account type, fulfillment, order city/state/postal, tax collection model, product sales, product sales tax, shipping credits, shipping credits tax, gift wrap credits, giftwrap credits tax, Regulatory Fee, Tax On Regulatory Fee, promotional rebates, promotional rebates tax, marketplace withheld tax, selling fees, fba fees, other transaction fees, other, total, Transaction Status, Transaction Release Date`（云途汇德-Novelledo-US 样例行匹配 ✓）。
- `reportDayType` = 月度 `yyyy-MM`；按店、按市场、原币。

### 13.2 两表深度对比（Novelledo-US, 2026-06）
| 科目 | A=Custom Transaction(USD) | B=赛狐结算明细(CNY) |
|---|---|---|
| 销售额 | product sales 4922.86; 促销 −219.22; 净售价 **4703.64** | Principal **18919.85** |
| 税 | **0.00**(collection≈withheld 净0) | **0.00** |
| 佣金 | selling fees −834.68 | Commission −2599.60 |
| FBA | fba fees −2474.84 | (并入未识别) |
| 广告 | Cost of Advertising −652.13 | −4387.34 |
| 其他费用 | other tx + other −1550.34 | 其他/未识别 −19531.32 |
| 退款(tx=Refund) | product sales −501.99 | 0 |
| 合计 | **−119.89** | **−7867.45** |
- **结论：二者不直接相等。** ① **口径**：A=活动/activity-posted(含 deferred)、B=payout(结算周期结束日)；② 币种 CNY vs USD；③ 赛狐明细侧的 `其他/未识别` 很大(大量 amountDescription 未映射)。→ **做费用/科目用 A(列式)更干净**；**做回款率/打款用 B**。别把两者总额当同一口径。
- 科目方向一致：`product_sales↔Principal`、`selling_fees↔Commission`、`tax↔税`、`fba↔FBA`、`Cost of Advertising↔广告`。

### 13.3 gsheet「渠道账号」已按你要求修正
- `赛狐店铺` 列已用 Sheets API `moveDimension` **移到 `渠道账号别名` 右侧**（现列序：编号/渠道/渠道账号/渠道账号别名/**赛狐店铺**/运营分组/…）。
- 2 行新账号 `AMZDANEEYCA`(别名清空；事业三部 / 荆春雨)、`AMZBJRYECLTDCA`(别名清空；事业二部 / 刘小菁)——别名不再含裸 `CA`/品牌 `LELEFIDO`（colab cell 1.2/1.2.1 爆炸+去重，别名必须是独立账号标识）。
- **VERCART→AMZVer** 已补（按你确认）：`AMZVerUS/CA/ES/UK/FR/IT/NL/SE/PL/BE` = `VERCART-{region}`；`VERCART-TR/IE`、`AMZVerMX` 无对应店/账号，留空。
- 北京固祥-* 未启用 → 排除；其余无当月数据店(君缘-TR/IE、北京熙锦-CA、云途汇德-CA、FZH深圳-CA/IE、方州汇绍兴-CA/MX、百纳-TR/IE、Daneey-IE) 留空。
- 产物：`sellfox_settlement/reconcile_amazon.py`(新增 `fetch-custom`)；`out/storeName_to_account_candidates.csv`。




