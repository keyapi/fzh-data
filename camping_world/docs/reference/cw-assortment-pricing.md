---
okf: v0.1
type: Reference
title: Camping World 选品与定价
tags: [campingworld, pricing, assortment, skyroom, margin]
timestamp: 2026-11-20
---

# CW 选品与定价

> 价格侦察日期：2026-11-20。价格会变，交表前需复核。
> 本文件比较的是**不同规格**的邻品，不能当作同款结论；最终以 CW 的零售价带与实测定价为准。

## 1. 结论先行

1. **CW 是价值/中价带**，不是 PB 的高端带。2023 年"PB 定位高于 Amazon"的报价逻辑不能搬过来。
2. Tracy 报价表里的 Suggested Retail（$56.99–$105.99）**落在 CW 可接受区间的上沿或略高**，
   需要用 CW 实际可接受价反推，而不是直接照抄。
3. 首批建议 **8-12 个 SKU**，集中在 **Personal Wedge（小尺寸楔形）与 Gap Filler（床缝填充）**；
   大号 Triangle 全尺寸先不全上，用 1-2 个尺寸试水。
4. Couch Cushion / Corner Pillow 需先确认 RV 尺寸适配，再决定是否进首批。
5. 我方供货净额 = 供货价 × **0.96（3%+1% 折让）** × **0.95（Tracy 5%，按实付）**
   ≈ 供货价 × **0.912**。

## 2. 市场锚点（2026-11-20）

| 渠道 / 产品 | 价格 | 来源 |
|---|---|---|
| CW Comfort Supreme Wedge（23×24×7，泡棉） | **$29.99** | https://www.campingworld.com/comfort-supreme-wedge-support-pillow-74261.html |
| CW TruCool Wedge（23×24×7，Serene Foam） | **$69.99** | https://www.campingworld.com/trucool-wedge-support-pillow-with-serene-foam-140321.html |
| Amazon 床头条 gap filler（Queen 60×10×6） | **$25.99–$39.99** | https://www.amazon.com/bed-wedge-pillow-headboard-adjustable/s?k=bed+wedge+pillow+for+headboard+adjustable+bed |
| Amazon 床头条 gap filler（King 76×10×6） | **$29.99–$58.99** | 同上 |
| Wayfair WOWMAX 三角头枕（高端） | Twin **$78.71** / Queen **$115.68** / King ~**$125–135** | https://www.wayfair.com/keyword.php?keyword=headboard+pillow+triangle+wedge |
| Bed Bath & Beyond 三角枕 | 从 **$38.99** | https://www.bedbathandbeyond.com/bed-wedge-pillow,/k,/results.html |
| PB（我方实测） | 零售 **$149–$199**；供货 **$51.70–$70.36** | `D:\Work\美国\Tracy Miller\KOHLs\KOHLs_初期策略分析_2026-08-17.md` |

**读法**：
- CW 自有 wedge 上限 $69.99，说明消费者对"小尺寸功能枕"的心理价位就在 $30–$70。
- Amazon 长条 gap filler 的成交带 $26–$59；我们的 Triangle 长条款要到 $80+，需要有
  面料/设计溢价支撑。
- Wayfair WOWMAX 证明 $100+ 的三角头枕有市场，但那是**家居装饰**渠道，不是 RV 渠道。

## 3. 现有报价表（Tracy 版，11 行）

| 产品 | 面料/颜色 | 尺寸 | 建议零售 | 供货价 | 净供货(×0.912) | 包装重量 | 包装尺寸 |
|---|---|---|---:|---:|---:|---:|---|
| Triangle Pillow | Velvet / 5 色 | 23 in | 56.99 | 33 | 30.10 | 6.3 lb | 20×16×4.5 |
| Triangle Pillow | Velvet / 5 色 | Twin | 69.99 | 41 | 37.39 | 9 lb | 21×20×5 |
| Triangle Pillow | Velvet / 5 色 | Full | 79.99 | 47 | 42.86 | 10 lb | 23×20×6 |
| Triangle Pillow | Velvet / 5 色 | Queen | 89.99 | 53 | 48.34 | 11.7 lb | 23×20×7 |
| Triangle Pillow | Velvet / 5 色 | King | 105.99 | 63 | 57.46 | 12.5 lb | 23×20×7 |
| Couch Cushion | Velvet / Cationic | 24×5×20 | 56.99 | 33 | 30.10 | 6.3 lb | 20×16×4.5 |
| Couch Cushion | Chenille | 35×17×9 | 65 | 39 | 35.57 | 9.9 lb | 22×20×5 |
| Corner Pillow | Chenille | 35×17×9 | 98 | 58 | 52.90 | 14.08 lb | 25×20×8 |
| Bone Pillow | Velvet | 22×13×12 | 58 | 34 | 31.01 | 2.42 lb | 16×11×6 |
| Arm Support Pillow | Velvet + 菱形网 | 26×26×7 | 52 | 31 | 28.27 | 3.74 lb | 22×17×5 |
| Dual-Use Side-Sleeping Wedge | Spacer + Velvet | 24×22×12 | 59 | 35 | 31.92 | 3.63 lb | 22×15×4 |

来源：`Camping World Product Quotation_English.xlsx`（Tracy 附件）。

## 4. 成本模型

```
净供货额 = 供货价 × (1 - 3% co-op - 1% defective) × (1 - 5% Tracy 佣金)
        = 供货价 × 0.96 × 0.95 ≈ 供货价 × 0.912

我方贡献 = 净供货额 - 到岸成本 - SPS 月费分摊 - 退货成本(按 <5%) - Net 30 资金占用
```

- **尾程运费不进入我方成本**：CW 3rd Party Bill To，运费记在 CW 的 FedEx 账号。
- SPS 月费按 $150/月估算，按预计月单量分摊；CW 增量是否加价待 SPS 确认。
- Net 30 资金占用按实际账期折算，不拍脑袋。
- 到岸成本需从 `D:\Work\美国\Tracy Miller\产品报价\` 的实际成本表取，不用报价表倒推。

## 5. 首批选品建议（8-12 SKU）

| 优先级 | 产品 | 理由 |
|---|---|---|
| P0 | Triangle Pillow 23 in、Twin | 零售 56.99/69.99 落在 CW 带内；轻包装 |
| P0 | Dual-Use Side-Sleeping Wedge | 零售 59，功能明确，RV 场景强 |
| P0 | Arm Support Pillow | 零售 52，轻小 |
| P1 | Bone Pillow | 零售 58，轻小（2.42 lb） |
| P1 | Couch Cushion（24×5×20） | 需确认 RV 沙发尺寸适配 |
| P2 | Triangle Full/Queen/King | 零售 79.99–105.99 高于 CW 现有一档，先各上 1 个试水 |
| P2 | Corner Pillow | 14 lb 重、零售 98，先验证需求 |

排除：一次性全上 5 个尺寸 + 全部颜色（库存与图片成本过高）。

## 6. 试价设计（最小成本验证）

1. 先上 8-12 个 SKU，两类用途为主。
2. 同款分两期测两个净成交价（间隔≥4 周），尽量保持流量与促销位一致。
3. 指标：转化率、每 100 次商品页访问的贡献额、退货率、缺陷率。
4. 覆盖完整退货窗口再下结论；流量不足时**不下价格弹性结论**。
5. 促销位带来的增长单独识别，不归因于价格。

## 7. 待确认

- CW 可接受零售价带与促销资源（问 Tracy/Kara）。
- UPC/GS1：沿用现有还是新注册。
- 到岸成本：从实际成本表取数（当前报价表没有成本）。
- 大号 Triangle 是否值得用低成本面料做 CW 专供版本。
