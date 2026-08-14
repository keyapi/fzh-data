---
okf: v0.1
type: Research
title: Amazon 在线配对多系统证据清单与失败模式
description: 汇总赛狐、EN/ERPNext、通途、Google Sheet、NAS 和既有仓库信息，复盘上一版配对流水线的过度弃权原因。
tags: [amazon, pairing, evidence, ontology, failure-modes, knowledge-base]
timestamp: 2026-08-14
---

# Amazon 在线配对多系统证据清单与失败模式

## 结论

上一版只得到 87 条高可信精确证据，不是因为赛狐里没有现成线索，而是因为证据图做得太窄：只允许“当前 MSKU 恰好命中 Gold 标签”或“当前站点+ASIN 在当前已配对缓存中唯一命中”。真实数据里还有大量可由同一 ASIN、父 ASIN、父 SKU、同族 SKU、同图、同标题、EN 客户物料号、通途 goodsQuery 传播的配对线索。

本轮只读核验确认：

- 同一 ASIN 可同时出现在“已配对”和“未配对”的 Listing 中，甚至跨店铺、跨站点；已配对目标可以直接作为强证据。
- `CEN665-Leaves-Grey-66-2` 没有精确客户码，但它的同族 `CEN665-Leaves-Grey-66-1` 和 `NB/CEN665-Leaves-Grey-66` 都映射到 `KS0244-CMGDTH-66x50-GREY`。
- `with Removable Velvet Cover` 描述的是“成品可拆套”，不是单独皮壳，因此上一版路由到 `cover` 是误判。
- `LongHuxing-Foam-...` 中的 Foam 是填充/材质描述，不是单独卖海绵；单独海绵概率较低，且 FBA Listing 多数是绍兴成品。
- 真正多件套、垫子支撑等仍需要单独路由或组合 SKU 流程，不能一刀切。

## 数据源清单

### 赛狐 Amazon 在线商品

- 读取端点：`POST /api/order/api/product/pageList.json`，V2 为 `/api/order/api/product/v2/pageList.json`。
- 分页：`pageNo`、`pageSize`；可筛选 `shopIdList`、`marketplaceIdList`、`onlineStatusList`、`switchFulfillmentTo`、`match`。
- 搜索字段：`sku`、`msku`、`title`、`fnsku`、`commodityName`、`asin`、`parentAsin`。
- 核心响应字段：`shopId`、`marketplaceId`、`asin`、`listingId`、`parentAsin`、`isVariation`、`sku`、`title`、`switchFulfillmentTo`、`mainImage`、`quantity`、`fnsku`、`onlineStatus`、`commodityId`、`commoditySku`、`parentSku`、`currency`、`lastSyncTime`。V2 另有 `commodityName`、`variationChildStr`、`brand`、`amazonBrand`、销量和广告字段。
- 已有缓存：`missing_products/out/pairing_cache/amazon_matched.json`、`amazon_unmatched.json`、`multiplatform.json`。当前快照 26,999 已配对，3,557 在售未配对。
- 配对写入：`/api/order/api/product/matchByMsku.json`、`matchByAsin.json`；批量上限 1000，可传可选 `shopId`。只有用户明确批准范围后才能调用。

### 赛狐商品主数据

- 商品列表：`/api/commodity/pageList.json`。
- 字段：`sku`、`spu`、`name`、`isGroup`、`childSkus`、`commodityAttributeValueRelaList`、图片/分类等。
- 组合 SKU：`isGroup=1`，`TJ#` 套件对象；未合并的 `Codex/sellfox-suite-pairing-audit` 分支有 `sellfox_combo_ops.py` 和完整创建/配对惯例。

### EN / ERPNext

- 生产：`https://erpnext.vilavi.cn`；测试：`https://ensh.vilavi.cn`。
- `Item` 字段：`item_code`、`item_name`、`item_group`、`variant_of`、`has_variants`、`image`、`default_bom`、`attributes`、`customer_items`、`disabled`。
- `Item Group` 字段：`item_group_name`、`parent_item_group`、`is_group`、`is_leaf_group`、`custom_model_id`、`image`、`custom_pim_images`、`custom_nas_path_link`、`daneey_product_details`。
- 批量客户码查询：`POST /api/method/vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping`，输入 `skus`，返回精确 `ref_code -> item_code/item_name/item_group`。适合做强标识索引，但单个 SKU 没命中时仍需模糊传播。
- BOM：`key_test.bom_cost_list` 报表；成本、产品编号、客户物料号、绍兴发货方式、BOM 组件。
- 产品层级：406 个款式/叶子组，约 2,259 个 EN/赛狐普通候选产品。

### 通途 ERP2

- 官方 MCP：`erp2_product_goodsquery`；通过 `tongtool_api/.env` 凭证访问，商户全局 5 次/分钟。
- `goodsQuery` 返回：`sku`、`skuLabel`、`productName`、`categoryName`、`productImgList`、重量/包装尺寸、成本、`goodsDetail`、`updatedDate`。
- 可用于把 Amazon MSKU 作为通途 SKU 查询中文商品名、别名、图片和规格，再匹配 EN 客户码。
- 库存查询：`erp2_stocks_stocksquery`、`erp2_stocks_fbastocksquery`；FBA 库存可用于确认 FBA 先验。
- 历史订单导出和 Google Sheet 可能有旧 SKU 名；`tongtool_order_cost/tongtool_order_cost/sku_map.py` 提供确认的旧名→新名映射。

### Google Sheet

- PR 174 已提供 `gspread` 本地 service account，可读/写「通途订单202606」等表。
- 与配对直接相关的是 SKU 旧名→新名映射、特殊规则和人工口径；不能当作实时库存/配对主源。

### NAS

- `NAS_API/synology.py` 已封装 FileStation；`/产品信息/KSxxxx_名称/图片` 是款式图片目录。
- `Item Group.custom_nas_path_link` 有图片/设计稿/视频/调研报告路径。
- 可用于款式级图片相似度；NAS 没有稳定的变体图片关系，变体识别仍需 EN 属性和赛狐主图。

### 图片与多模态

- Amazon 在线商品有 `mainImage`；已配对和未配对都可能有相同 URL。
- EN Item 有 `image`；Item Group 有 `image` 和 `custom_pim_images`。
- 通途 goodsQuery 有 `productImgList`。
- 项目已有 DashScope `qwen-vl-ocr` 用法，但图片相似度更适合用 CLIP/SigLIP 或可访问的多模态模型做候选检索，不建议直接让通用 VLM 对 2,259 个候选做全量比对。

## 上一版失败模式复盘

| 用户样例 | 上一版结果 | 根因 | 修复方向 |
| --- | --- | --- | --- |
| `Danpinse-KS0388-blue-FBA` | 一个 CA 行进入无可靠候选 | 当前 ASIN 索引只按站点隔离；另一个站点已有同 ASIN 目标 `KS0388-HLRJLGBL-62x68x38-LIGHTBLUE` | 允许全局 ASIN 唯一目标传播，并把跨店铺/站点重复记录视为同一实体线索 |
| `CEN665-Leaves-Grey-66-2` | 特殊对象暂缓 | 只做完整 SKU 精确命中；没有做同族 `-1`/`-2` 与 `NB/...` 客户码图传播 | 用 EN 客户码前缀、SKU 家庭、标题属性和数量差异做候选，不直接当成 cover 丢弃 |
| `DanCA1534D9-Blue-153` | 特殊对象暂缓 | `Removable ... Cover` 命中 cover 正则 | 用语义规则区分“只卖皮壳”和“成品带可拆套”；优先 ASIN 历史目标 |
| `LongHuxing-Foam-Lbai-100` | 特殊对象暂缓 | `Foam` 命中 foam 正则 | Foam 在普通成品标题中常是材质/填充描述；FBA 与标题结构先验应降低单独海绵概率 |
| `BAI31038N0A62927SX-2pcs-us` | 组合对象暂缓 | 数量词命中 combo | 这是真套装，但仍应按商品对象类型继续匹配 `KS0156...BLACK` 或其他正确目标，而不是只搁置 |

## 量化的证据传播上限

用当前已配对快照对 3,557 条在售未配对做只读、确定性证据扫描：

| 证据 | 有证据行数 | 唯一目标行数 |
| --- | ---: | ---: |
| 精确 MSKU | 73 | 73 |
| ASIN（全局） | 164 | 160 |
| ASIN（店铺内） | 58 | 57 |
| 父 ASIN | 459 | 60 |
| 父 SKU | 382 | 43 |
| 主图 URL | 458 | 209 |
| 标题精确 token | 236 | 155 |
| 标题规范化 | 576 | 196 |
| 朴素确定性级联唯一覆盖 | 495 | 495 |

这说明光靠标识符级联可以补到约 14%，父 ASIN/父 SKU/标题/图片更多是“候选集合”而不是“唯一答案”。下一版必须在候选集合内用 EN 属性、美式尺寸映射、对象类型和可选 LLM 裁判进一步收窄，而不是把这些证据当作冲突直接弃权。

## 证据层级草案

1. `L0 硬标识`：店铺、MSKU、ASIN、FNSKU、EN customer code、通途主 SKU/别名、赛狐 commodity SKU。
2. `L1 跨市场实体传播`：同 ASIN/父 ASIN/父 SKU/同图在已配对记录中的目标集合。
3. `L2 家庭与结构化属性`：EN SPU、Item Group、面料、尺寸、颜色、数量；把 Twin/Full/Queen/King/California King、inch/cm 映射到 EN 尺寸。
4. `L3 文本/图片相似度`：字符或跨语言 embedding、图片 embedding，仅用于排序候选，不用于直接写入。
5. `L4 LLM 裁判`：仅在候选小于约 5 条、证据冲突或属性歧义时调用；输出候选排名、置信度、缺失信息和必须弃权原因。

## 访问与安全边界

- 所有读写必须分层：配对写入、通途写入、EN 写入、Google Sheet 写入都需显式批准范围。
- 通途 ERP2 共享 5 次/分钟配额，批量查询应缓存，避免每行一次调用。
- 赛狐/EN/NAS 凭证和业务文件不进 Git；生成的大数据文件放 ignored `out/`。
- 组合对象、皮壳、海绵、骨架和套件继续单列；不把“无法配对”解释为“可以随便配对”。
