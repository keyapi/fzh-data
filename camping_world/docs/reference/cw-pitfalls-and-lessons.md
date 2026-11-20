---
okf: v0.1
type: Reference
title: 美国商超入驻经验与坑（PB/CW 适用）
tags: [retail, vendor-onboarding, edi, chargeback, gs1, insurance, lessons]
timestamp: 2026-11-20
---

# 美国商超入驻经验与坑

> 本文分两层：**我们自己验证过的**（PB）与**行业公开资料**（带来源）。
> 用途：CW 入驻时提前避坑，不重复交学费。

## 1. 我们自己的 PB 经验（已验证）

| 经验 | 说明 |
|---|---|
| SPS 一条链路跑通 | EDI + 标签都在 SPS 完成，每周手动 2-3 次 |
| 5% 中间人佣金按实付 | 促销折后自动生效（`tm_commission.py`） |
| 退货率 <5% | 已计入报价；PB 未收退货费 |
| 缺货按明细行处理 | 不按整单取消，避免误伤有货行 |
| 对账按 UPS 实发日期 | 不按建单日期 |
| 标签裁切 + 背贴 | 从 SPS 导出的合并 PDF 再加工 |

## 2. 行业通用规律

### 2.1 EDI 是合规系统，不是"能传文件"

- **856 ASN 是最常见的罚款来源**；ASN 必须来自**实际发货数据**，不能从 PO 数据生成。
- **SSCC-18 必须与 ASN 和箱标一致**；不一致会直接产生扣款。
- **855 不能省**：迟交或缺失会被视为不确认，导致订单取消或合规扣分。
- **997 功能确认**也有时限（部分零售商 24 小时）。
- **只测一种 PO 类型**是典型错误：补货 PO 通过，促销/直发 PO 上线才爆。
- **通用 EDI map 会失败**：每家零售商字段、代码、承运商映射都不同，必须单独认证。
- 上线后要**持续监控** failed 856、997 reject、迟交 810，而不是等罚款通知。

来源：
- https://www.spscommerce.com/community/articles/edi-chargebacks-explained
- https://www.shipnetwork.com/post/edi-chargebacks-what-causes-them-and-how-to-avoid-them
- https://getproductiv.com/edi-setup-retail-fulfillment
- https://vantree.com/costco-edi-integration

### 2.2 罚款/扣款（chargebacks）

- 六类高频：错过窗口、短发/超发、ASN 迟或错、标签不可扫、托盘/装箱违规、未授权承运商。
- 管理不善可吃掉 **5%–15% 的销售额**。
- 争议窗口从 **30 天到 18 个月**不等；证据要在**发货时**就留存。
- 单次罚款从 $5 到 $250+；CW 自己的表是 $50–$600（见入驻清单）。

来源：
- https://dpwagner.com/fulfillment/blog/vendor-compliance
- https://www.aims360.com/fashion-business-resources/edi-dropshipping-apparel-erp-software-dropship-management
- https://www.spscommerce.com/community/articles/edi-chargebacks-explained

### 2.3 UPC / GS1

- 大型零售商要求 **GS1 Company Prefix 归属供应商品牌**；转售/共享前缀会被拒。
- 案例级需要 **GTIN-14 / ITF-14 / GS1-128**，不能只贴消费者 UPC。
- UPC 复用有规则；CW 写明**最后一次发货后 30 个月**才能复用，且下单后改 UPC 罚 $50/SKU。
- 申请 GS1 前缀需要时间，**应在 Item Setup 前启动**。

来源：
- https://www.spscommerce.com/community/articles/gs1-standards-for-new-suppliers-gtins-upcs-and-case-codes
- https://corporate.walmart.com/suppliers/requirements
- https://www.barcode.graphics/frequently-asked-questions-upc-barcodes-and-gs1-company-prefixes

### 2.4 HTS / 原产地 / Prop 65

- HTS 至少 **8 位**；原产地要 **2 位国家代码**。
- Prop 65 的首要责任在**制造商/供应商**；要么产品标注警告，要么书面通知零售商并取得确认。

来源：
- https://www.p65warnings.ca.gov/business-resources/frequently-asked-questions-businesses

### 2.5 保险：措辞比金额更容易出事

- 常见要求：additional insured 具体措辞、primary & non-contributory、waiver of subrogation、
  A.M. Best 评级、30 天取消通知。
- 措辞不匹配合同，出险时会被拒赔。**不要只让经纪"按惯例出"**，要按合同原文逐条对。

来源：
- https://vendor.tractorsupply.com/assets/docs/VRM.pdf（vendor 手册示例）
- https://totalcsr.com/insurance-glossary/additional-insured-vendors

### 2.6 报价与商务

- Allowances/deductions 是收入的固定折让，不是"偶尔发生"：CW 是 4%。
- Net 30/60 是资金占用，要按实际账期算成本。
- MAP 与渠道冲突要提前处理（同一 SKU 在 PB/CW/Amazon 的价格关系）。
- 价格变更通常要求提前书面通知（CW 90 天）。
- 促销/co-op 要确认计算基数是 **invoice 金额**还是**实付金额**。

来源：
- CW 合规指南 §2.4（90 天价格变更）
- 用户确认的佣金/返点口径

### 2.7 入驻节奏

- EDI 认证通常 **2-6 周**；SPS 官方对 CW 说 3 天到 6 周。
- **Item setup 延迟比仓库错误更常见**：GTIN、箱规、实测尺寸未批，导致首单发不出。
- 先小批量试点，别一次上全量 SKU。

来源：
- https://dpwagner.com/fulfillment/blog/vendor-compliance
- https://getproductiv.com/edi-setup-retail-fulfillment

## 3. CW 特有的坑（文档已明确）

| 坑 | 后果 |
|---|---|
| 用 UPS | 明确不支持；RS-04 $600 + 运费 |
| 用 Collect / Payor Recipient | RS-04 / RS-16 罚款 |
| Ground / Home Delivery 选错 | RS-16 $200 + 差额 |
| 855 迟于 1 个工作日 | 订单不确定/取消风险 |
| 846 超过 72 小时 | 库存不可见，影响补货 |
| ASN 晚于 810 或晚于到货 | 合规问题 |
| 下单后改 UPC/属性 | PI-02 $50/SKU |
| 忽略 New Store 条款 | 应跳过，别误签 |

## 4. 原则：调研结论 ≠ 对方确认

即使我们通过公开资料、SPS 文档或行业惯例确认了某件事，只要**CW 没有书面说清**，
就必须通过 Tracy 向 CW 确认，并留下书面回复。原因：

- 罚款条款以合同/合规指南为准，不以行业惯例为准。
- 承运账号、标签来源、模板审批都在 CW 手里。
- 出了争议，只有对方的书面确认能作为证据。

具体待确认清单见 [cw-open-questions.md](cw-open-questions.md)。

## 5. 对本项目的行动

1. **标签优先走 SPS**；FedEx 后台/API 只作兜底。
2. **每日 EDI 检查**，不再沿用 PB 每周 2-3 次。
3. **数据主档先行**：UPC/GS1 前缀、HTS、实测箱规尺寸、原产地、Prop 65。
4. **发货留证**：标签照片、ASN 发送时间、承运商取件记录。
5. **记录争议窗口**：CW 的扣款争议期要问清并写进 SOP。
