---
okf: v0.1
type: Handoff
title: Amazon 在售未配对自动匹配建议 — 子项目交接
tags: [amazon, pairing, matching, ml, sellfox, tongtu, handoff]
timestamp: 2026-08-11
---

# Amazon 在售未配对自动匹配建议

> 本子项目用于解决赛狐 Amazon 在线商品“在售但未配对”的自动建议问题。当前只完成只读调研、数据盘点和第一阶段规则建议，未实现 ML 训练，未调用任何赛狐配对写入接口。

> **先读**：[Amazon 在线商品配对的分层候选与运营确认流程](../docs/solutions/conventions/amazon-online-product-pairing-candidate-workflow.md)。
> 它是 Amazon/多平台机制区分、快照时效、人工确认和禁止写入边界的规范来源；本文件保留当前脚本、数据源和交接清单。

## 1. 目标

- 输入：赛狐 Amazon 在线商品（已配对/未配对）、通途最新导出（SKU + SKU别名）、EN 物料/客户物料号、赛狐商品 SKU。
- 输出：给运营人员的配对建议表，尽量可导入赛狐（`import_product_msku_match` 模板），无法唯一确定的进入人工核对。
- 长期目标：用已配对数据训练匹配模型，覆盖通途别名登记不全的 FBA/MSKU。

## 2. 2026-08-11 数据快照

| 指标 | 数量 |
|------|------|
| Amazon 在线产品总数 | 50,169 |
| 已配对 | 26,100 |
| 未配对 | 24,069 |
| 在售未配对 | 4,407 |
| 在售未配对且通途别名命中 | 442 |
| 在售未配对 FBA(AFN) | 53 |
| 在售未配对 MFN | 4,354 |
| 三角靠枕严格候选 | 275 |
| 别名命中中可生成导入 | 91 |
| 别名命中中需人工核对 | 133 |
| 本地SKU与EN映射不一致 | 65 |

数据来源：`missing_products/out/pairing_cache/*.json`（赛狐 API 原始缓存），`D:/Work/赛狐/配对/通途商品导出_20260811_1200.zip`，`missing_products/out/通途EN赛狐映射表_20260811_145635.xlsx`。这是 2026-08-11 快照；后续建议前必须重新确认通途导出和赛狐缓存时效。

## 3. 赛狐配对机制（已核实）

- **Amazon 在线产品配对**是独立机制：
  - 读取：`POST /api/order/api/product/pageList.json`，`match=true/false` 区分配对状态。
  - 写入：`POST /api/order/api/product/matchByMsku.json`、`matchByAsin.json`。
  - 导入模板：`import_product_msku_match`（列 `*MSKU、店铺名称、*商品SKU`）。
- **多平台配对**是另一套机制：
  - 读取：`POST /api/multiplatform/match/getList.json`。
  - 写入：`POST /api/multiplatform/match/save.json`。
  - 导入模板：`importMatchTemplate`（列 `*店铺、*MSKU、*SKU`）。
  - 当前多平台配对 3,285 条，Amazon/Amazon_VC 均为 0，Amazon 不走这套。
- `pageList` 支持精确过滤：`searchType`（sku/msku/asin/parentAsin/title/fnsku/commodityName）、`searchContent`、`onlineStatusList`（active/inActive/delete）、`match`、`shopIdList`、`marketplaceIdList`；`pageSize` 上限 200。

## 4. 现有脚本

| 脚本 | 职责 |
|------|------|
| `missing_products/fetch_sellfox_pairing.py` | 拉取 Amazon + 多平台配对，缓存到 `out/pairing_cache/`，`--refresh` 强制重拉 |
| `missing_products/analyze_amazon_unmatched.py` | 在售未配对分析：别名命中、FBA/MFN、三角靠枕候选 |
| `missing_products/build_amazon_pairing_suggestions.py` | 生成可导入建议、需人工核对、三角靠枕建议、65 条不一致分析 |
| `missing_products/tongtu_data.py` | 通途 zip / 映射底表 / 别名读取 |
| `missing_products/build_mapping_workbook.py` | 生成通途→EN→赛狐映射表 |

关键产物（`missing_products/out/`）：

- `Amazon在售未配对分析_*.xlsx`：汇总 / 在售未配对全量 / 三角靠枕候选。
- `Amazon配对导入建议_*.xlsx`：可导入建议 / 需人工核对 / 三角靠枕建议 / 65条不一致分析 / 说明。
- `赛狐配对盘点_*.xlsx`：Amazon 已配对/未配对、多平台配对、通途别名_EN差异、待确认。

## 5. 分阶段方案

1. **阶段 0 别名精确匹配（已做）**：平台SKU/MSKU 精确命中通途主SKU/别名，再经通途→EN→赛狐映射生成导入建议。覆盖 442/4,407，其中 91 条可直接生成导入，133 条因一对多或无 EN 映射需人工核对。
   - “无EN映射”含义：平台SKU命中了通途主SKU/别名，但该通途主SKU未出现在1411有库存EN映射中（未精确登记EN产品成品，或不在本轮有库存范围）；不是通途没有该SKU。
   - 建议表已含：平台标题(原文)、标题中文提示(粗略字典)、通途主SKU、EN产品编号/名称、赛狐SKU；65 条不一致表另含本地/期望双方SKU与中文名称。
2. **阶段 1 规则 + 模糊匹配（建议先做）**：在 275 条三角靠枕候选上试点，从平台 SKU/标题解析尺寸/颜色/面料，与 EN `KS0001-*` 变体比对；工具建议 `RapidFuzz`；输出 top-N + 置信度，人工确认后反馈，形成标注集。
3. **阶段 2 机器学习（后续子项目）**：用 26,100 已配对做训练集（需先清洗错误配对），特征含标题、ASIN、尺寸、颜色、面料、店铺/站点；可用 sentence-transformers embeddings + 分类器，或直接属性抽取 + 向量检索；备选框架：`recordlinkage`、`Splink`、`dedupe`、`pyJedAI`。
4. **阶段 3 运营闭环**：每周/每日差异表 → 运营确认 → 导入赛狐 → 回读验证；把确认结果回流为训练数据。

## 6. 已知问题与开放决策

- Amazon 标题是英文，EN 名称是中文，需要建立面料/颜色/尺寸双语词典。
- 已配对数据存在错误（例如 65 条不一致中多个 TT SKU 错配到同一个 `KS0437-MSTWBHLR-120x200x45-LIGHT...`），训练前必须清洗。
- 通途别名登记不全，尤其 FBA；别名精确匹配只能覆盖约 10%。
- 一个别名可能对应多个通途 SKU 或多个 EN 产品（一对多），不能自动去重。
- HM1510 海绵：EN REST 校验“客户物料号只能添加到 产品/套件# 物料组”，无法通过 API 给 HM1510 加客户码；且 `TT0031247K0064095-Foam` 没有 218x115x55 的 HM1510 物料。本子项目暂不处理。
- 是否允许调用 `matchByMsku` API 批量写入，还是坚持运营上传 Excel 导入，需业务确认。
- 直到用户明确批准具体店铺、MSKU 和赛狐 SKU 的导入范围前，本项目不得调用 `matchByMsku`、`matchByAsin` 或任何多平台写接口。

## 7. 交接清单

1. 读本文档 + `missing_products/AGENT_HANDOFF.md`。
2. 如有新的通途导出，放到 `D:/Work/赛狐/商品/` 或 `D:/Work/赛狐/配对/`，脚本自动取最新。
3. 重跑 `fetch_sellfox_pairing.py --refresh` 前先确认 API 配额；日常分析默认用缓存。
4. 阶段 1 试点从 `Amazon配对导入建议_*.xlsx` 的“三角靠枕建议”页开始。
5. 所有写入赛狐/EN 的动作必须先经用户确认，禁止直接调写接口。
