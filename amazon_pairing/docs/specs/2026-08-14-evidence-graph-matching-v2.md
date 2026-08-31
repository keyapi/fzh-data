---
okf: v0.1
type: Spec
title: Amazon 在线配对证据图匹配 V2
description: 用多系统证据图、对象/属性本体、结构化候选检索和可选 LLM 裁判替代上一版过窄的四家族试点。
tags: [amazon, pairing, evidence-graph, ontology, llm-judge, spec]
timestamp: 2026-08-14
---

# Amazon 在线配对证据图匹配 V2

## Goal

为赛狐 Amazon 在售未配对 Listing 生成分层、可解释、可追溯的赛狐商品候选。目标不是替代人工，而是显著减少“无可靠候选”盲区，并保证高置信建议仍有严格证据或人工确认。V2 仍不调用赛狐配对写接口。

## Current State And Problem

上一版 V1：

- 87 条高可信精确证据，550 条实验候选，434 条特殊对象，2,486 条主动弃权。
- 证据仅使用“Gold MSKU/别名”和“当前站点+ASIN 唯一目标”。
- 原始 Candidate Recall@20 为 32.25%，模型 `production_ready=false`。
- 对象分类用少量正则，把 `Removable Cover`、`Foam` 和数量词误判为独立皮壳/海绵/套件。

已核验的五条反例应成为 V2 的回归基准。

## Design

### 数据流

```text
Sellfox pageList (matched+unmatched)
  -> raw evidence graph
  -> EN Item/Item Group/customer code/BOM
  -> Tongtool goodsQuery/alias snapshot
  -> object ontology
  -> attribute normalization
  -> candidate blocking
  -> evidence scoring and ranking
  -> optional LLM judge
  -> review workbook
```

### 证据图

统一节点和边：

- `listing`: `(shopId, marketplaceId, msku, asin, listingId)`
- `market_product`: `commoditySku` / `commodityId`
- `toll_product`: Tongtool `sku`, `skuLabel`, `goodsDetail.goodsSku`
- `en_item`: `item_code`, `variant_of`, `customer_items.ref_code`
- `image`: `mainImage` URL、EN `image`、Tongtool `productImgList`

强边来自已配对记录：

| 边 | 传播条件 | 建议用途 |
| --- | --- | --- |
| MSKU -> commoditySku | 同一 MSKU | 精确证据 |
| ASIN -> commoditySku | 同一 ASIN，可跨店铺/站点 | 强证据，需检查目标冲突 |
| parentAsin -> commoditySku | 同一父 ASIN | 候选阻塞 |
| parentSku -> commoditySku | 同一父 SKU | 候选阻塞 |
| FNSKU -> commoditySku | 同一 FNSKU | 强证据 |
| mainImage -> commoditySku | 图片 URL 完全一致 | 强证据 |
| 标题规范化 -> commoditySku | 去掉尺码/单位/标点后一致 | 候选阻塞 |
| EN customer code -> EN item | 精确或同族传播 | 强证据/候选 |
| Tongtool SKU/alias -> EN item | 精确 alias | 强证据/候选 |

同实体传播遵循保守条件：候选集存在时，先检查属性冲突，不因多条证据自动写赛狐。

### 对象本体

对象分类不再是标题正则单点判断，而是组合信号：

| 对象类型 | 强信号 | 否定信号 |
| --- | --- | --- |
| `finished_product` | 标题描述完整枕/沙发/坐垫，`with removable cover`，FBA 或标题含填充描述 | `cover only`、`no filler`、`pillow cover`、`shell only` |
| `cover` | `cover only`、`just cover`、`pillow cover(s)`、`no filler`，EN 候选名称含枕套/皮壳/套子 | `with removable cover`、`removable cover included` |
| `foam_part` | `replacement foam`、`foam only`、明显填充物独立件 | 普通标题中的 `memory foam`、`high-density foam`、`foam-filled` |
| `combo` | `set of`、`2 pcs`、`bundle`、`multipack`、EN `Product Bundle`/`isGroup=1` | 数量词只是规格维度时需人工确认 |
| `unknown` | 多重信号冲突 | 不做强配 |

`CEN665` 案例说明：标题 `Pillow Covers ... No Filler` 确实应路由为 cover，但目标 `KS0244` 本身就是长方形枕套，所以必须允许 `cover -> cover` 匹配，而不是把所有 cover 丢到暂缓。

### 属性本体

新增规范化表：

- 美式床品尺码：`Twin=100`、`Twin XL=100`、`Full=140`、`Queen=153`、`King=194`、`California King=200`。仅适用于头部靠枕/床品，不适用于所有商品。
- 长度单位：inch/`in`/`"` 转 cm，`cm` 保持不变；`22IN Tall` 只能作为高度线索，不能当作变体尺寸。
- 颜色：英语 -> 中文标准色，例如 `light blue -> 浅蓝色`，`sage green -> 草绿色`，`deep blue -> 深蓝色`。颜色候选可多值，冲突时降低排名。
- 面料：`velvet -> 荷兰绒/绒布`，`corduroy -> 条绒/纯棉宽条绒`，`linen -> 涤麻`，`cotton jacquard -> 纯棉贡缎提花`。面料不作为硬冲突，除非 EN 属性明确且冲突。
- 数量：`2 pcs`、`set of 2` 提取为 `count=2`，用于组合路由和属性排序。

### 候选阻塞

按优先级合并强边目标：

1. Gold MSKU/alias
2. 同一店铺 ASIN
3. 全局唯一 ASIN
4. FNSKU
5. 图片 URL
6. 同族 EN customer code
7. 父 SKU/父 ASIN
8. 标题相似/字符 TF-IDF

每个候选需要携带证据类型、来源记录数、来源站点/店铺、时间和目标对象类型。可靠属性冲突只降低分数或进入冲突审核，不静默丢弃。

### 排序与裁判

- V1 LightGBM 排名器保留为参考，但不再把 32.25% 的原始召回当作生产就绪。
- V2 默认使用可解释规则分数：硬边、属性一致、对象一致、同图、同标题。
- 仅当候选数在 2-5 条、分数接近或存在跨源冲突时调用 Qwen/DashScope 或公司网关 LLM 裁判。
- LLM 输出必须是固定 schema：`listing_id`、`target_sku`、`confidence`、`evidence`、`abstain`、`missing_info`。不输出其他字段；`confidence` 低或证据不足时必须 `abstain=true`。
- LLM 判断不自动升级为写入权限。

### 审核工作簿

分层输出：

| Sheet | 内容 | 动作 |
| --- | --- | --- |
| `运行汇总` | 输入/输出对账、来源哈希、模型状态 | 审计 |
| `强证据建议` | L0/L1 唯一目标 | 人工批量确认 |
| `Top候选审核` | 普通候选 Top-3 | 人工确认 |
| `冲突候选审核` | 多条强证据目标不同 | 需要专门审核 |
| `对象专项` | cover/foam/combo/unknown | 走对应工作流 |
| `无候选` | 无可靠阻塞 | 继续补充数据 |
| `隔离历史数据` | 有疑问或历史冲突 | 不参与训练 |
| `证据审计` | 每条建议的图边和来源 | 人工穿透 |

反馈继续记录来源工作簿、数据/模型哈希、人工结论和正确 SKU；不做自动导入。

## Verification Contract

必须通过的回归场景：

1. `Danpinse-KS0388-blue-FBA` 使用同 ASIN 目标进入强证据建议。
2. `CEN665-Leaves-Grey-66-2` 通过同族 EN customer code/目标商品本体进入 cover 候选，不进入无候选。
3. `DanCA1534D9-Blue-153` 使用跨站点 ASIN 历史目标进入强证据建议。
4. `LongHuxing-Foam-Lbai-100` 不再被 `Foam` 单独强制路由，应进入普通候选或明确缺货，而不是 foam 暂缓。
5. `BAI31038N0A62927SX-2pcs-us` 保持 combo 对象，但能展示正确的沙发支撑垫候选或组合工作流。
6. 所有输入行进入唯一分流，数量对账成立。
7. 可靠属性冲突不能出现在自动建议 Top-1；只进入冲突审核。
8. 不调用任何写接口。

## Non-Goals

- 不自动调用 `matchByMsku` / `matchByAsin`。
- 不在本模块自动创建 EN/赛狐组合 SKU；需要时回落到已批准的 `sellfox-combo-create` 工作流。
- 不为了覆盖率强制把皮壳/海绵/骨架配给普通 KS 商品。
- 不在无候选时猜测目标。

## Implementation Units

1. `U1` 扩展原始快照字段和 provenance。
2. `U2` 实现证据图和同族传播。
3. `U3` 实现对象本体与尺寸/颜色/面料/数量规范化。
4. `U4` 实现候选阻塞和可解释排序。
5. `U5` 实现可选 LLM 裁判。
6. `U6` 生成分层工作簿和反馈。
7. `U7` 回归测试、评估、文档和 PR 更新。
