---
title: Amazon 在线商品配对的分层候选与运营确认流程
type: Reference
date: 2026-08-11
category: conventions
module: amazon_pairing
problem_type: convention
component: sellfox_amazon_pairing
severity: high
applies_when:
  - "盘点或补齐赛狐 Amazon 在线商品配对"
  - "使用通途 SKU 别名生成 Amazon MSKU 配对建议"
  - "评估 Amazon 未配对商品的规则、模糊匹配或机器学习方案"
tags: [amazon, sellfox, pairing, tongtu, erpnext, matching, review]
---

# Amazon 在线商品配对的分层候选与运营确认流程

## Context

赛狐的 Amazon 在线商品配对是将平台 MSKU 与赛狐商品 SKU 关联的独立机制。
它使用 Amazon 在线商品数据、通途主 SKU/别名、EN 产品映射和赛狐商品 SKU 来产生建议，
但不能把“字符串相似”或“通途别名命中”直接视为已配对。

Amazon 配对与赛狐多平台配对不能混用：

| 范围 | 读取 | 写入 | 导入模板 |
| --- | --- | --- | --- |
| Amazon 在线商品 | `POST /api/order/api/product/pageList.json` | `matchByMsku.json` / `matchByAsin.json` | `import_product_msku_match`，列为 `*MSKU、店铺名称、*商品SKU` |
| 多平台配对 | `POST /api/multiplatform/match/getList.json` | `save.json` | `importMatchTemplate`，列为 `*店铺、*MSKU、*SKU` |

虽然多平台接口的平台注册列表包含 Amazon/Amazon_VC，2026-08-11 的实际数据中这两类配对数均为 0；
Amazon 应走第一行的在线商品机制。

## Verified Snapshot

以下数字是 2026-08-11 的只读快照，不是永久完成率。数据来自赛狐 API 缓存、
`通途商品导出_20260811_1200.zip` 与 1411 行通途-EN-赛狐映射表：

| 指标 | 数量 |
| --- | ---: |
| Amazon 在线商品 | 50,169 |
| 已配对 / 未配对 | 26,100 / 24,069 |
| 在售未配对 | 4,407 |
| 严格命中通途主 SKU 或别名 | 442 |
| 可生成 Amazon 导入建议 | 91 |
| 需人工核对 | 133 |
| 三角靠枕低置信候选 | 275 |
| 本地赛狐 SKU 与 EN 映射不一致待核查 | 65 |

“无 EN 映射”表示平台 SKU 已严格命中通途主 SKU 或别名，但这个通途主 SKU 没有出现在
当前 1411 条有库存 SKU 的 EN 产品精确映射中。它可能未精确登记 EN 产品，也可能不在本次
有库存范围；**不表示通途没有该 SKU，也不表示可直接新建赛狐商品。**

## Candidate Pipeline

1. **刷新证据。** 把新的通途商品导出 zip 放入 `D:/Work/赛狐/商品/` 或
   `D:/Work/赛狐/配对/`；`missing_products/tongtu_data.py` 选择最新导出。需要刷新赛狐数据时，
   先确认 API 配额，再运行 `uv run python missing_products/fetch_sellfox_pairing.py --refresh`。
   日常复核默认使用 `out/pairing_cache/`，不要把旧缓存当实时事实。
2. **阶段 0：严格别名。** 平台 SKU/MSKU 必须精确命中通途主 SKU 或别名，再关联
   通途 -> EN 产品 -> 赛狐 SKU。只有单一且可回读的目标才进入可导入建议；一对多、
   无 EN 映射和其他歧义都保留在人工核对页。
3. **阶段 1：可解释规则。** 先以 275 条三角靠枕为试点，从平台 SKU 和英文标题提取尺寸、
   颜色、面料，与 EN `KS0001-*` 变体比较；可用 RapidFuzz 生成 top-N 与置信度。
   此阶段的输出仍是建议，不是配对写入。
4. **阶段 2：学习模型。** 先清洗已配对数据中的错配，再评估 embeddings 或监督学习。
   26,100 条已配对记录可提供训练样本，但 65 条不一致说明它们不能未经清洗直接当标签。
5. **运营确认闭环。** 每条建议必须包含平台标题原文、中文提示、通途主 SKU、EN 编号和名称、
   候选赛狐 SKU 和名称、置信度及匹配依据。运营确认范围后才生成或导入 Amazon 模板，
   并从 `pageList` 回读验证结果。

## 2026-08-14 Pilot Result

现已实现 `amazon_pairing` 只读流水线。历史 26,999 条已配对记录中，只有 14,021 条满足 Gold A；12,918 条 Silver 和 60 条 Quarantine 不作为正例。候选 catalog 含 2,259 个 EN/赛狐普通产品。

四家族试点的 family Top-1 为 94.79%，但原始 Candidate Recall@20 仅 32.25%，排序 Top-1/Top-3 为 41.37%/55.05%，因此 `production_ready=false`。排序 Recall@20 的 100% 来自评估时正样本注入，只衡量排序器，不代表真实候选召回。

最新 3,557 条在售未配对分为 87 条高可信精确证据、550 条实验候选、434 条特殊对象暂缓和 2,486 条无可靠候选，数量完全对账。这个结果确认：当前最合适的自动化不是直接写配对，而是保守缩小人工搜索范围并积累经人工确认、剔除疑问的反馈标签。

## Non-Negotiable Boundaries

- 本子项目当前只读取、分析并生成 Excel 建议，不调用任何赛狐配对写接口。
- 不把 Amazon 的 `import_product_msku_match` 用多平台模板替代，反之亦然。
- 不以英文标题粗略翻译、单个尺寸命中或模型分数自动配对；这些只能缩小人工核对范围。
- 不用配对任务修正 EN 产品、客户物料号或赛狐商品状态。此类缺口回到
  `missing_products` 主线，按完整通途 SKU 精确登记规则处理。
- FBA 别名覆盖较低是已知数据质量问题，不以补全率压力促成猜测性写入。
- 候选检索必须先做可靠属性冲突过滤；若所有候选冲突或家族置信度不足，必须主动弃权。
- cover、foam、combo、主体骨架及其他配套物料不得强配普通 KS 产品；combo 转到 `TJ#` 套件流程。
- 人工反馈必须保存来源工作簿与模型文件哈希，疑问反馈不得回流为 Gold 标签。

## Outputs And Handoff

| 产物 | 用途 |
| --- | --- |
| `Amazon在售未配对分析_*.xlsx` | 在售未配对全量、别名命中与三角靠枕候选 |
| `Amazon配对导入建议_*.xlsx` | 可导入建议、人工核对、三角靠枕候选、65 条不一致分析与说明 |
| `赛狐配对盘点_*.xlsx` | Amazon 已/未配对、多平台配对及通途别名/EN 差异 |
| `amazon_pairing/AGENT_HANDOFF.md` | 新 Agent 的当前快照、脚本入口和写入边界 |

首次接手时先读 `amazon_pairing/AGENT_HANDOFF.md`，再读本流程。需要处理 EN/赛狐商品缺口时，
继续读取 [通途有库存 SKU 三方主线补齐惯例](tongtu-en-sellfox-instock-sku-mainline.md)，
不要在配对脚本中另造产品映射规则。
