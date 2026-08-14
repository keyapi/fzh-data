---
okf: v0.1
type: Handoff
title: Amazon 在售未配对自动匹配建议 — 子项目交接
tags: [amazon, pairing, matching, ml, sellfox, tongtu, handoff]
timestamp: 2026-08-14
---

# Amazon 在售未配对自动匹配建议

> 本子项目用于解决赛狐 Amazon 在线商品“在售但未配对”的人工审核辅助问题。现已实现历史标签审计、四家族分类与排序试点、分层弃权工作簿和人工反馈导入；未调用任何赛狐配对写入接口。

> **先读**：[Amazon 在线商品配对的分层候选与运营确认流程](../docs/solutions/conventions/amazon-online-product-pairing-candidate-workflow.md)。
> 它是 Amazon/多平台机制区分、快照时效、人工确认和禁止写入边界的规范来源；本文件保留当前脚本、数据源和交接清单。

## 1. 目标

- 输入：赛狐 Amazon 在线商品（已配对/未配对）、通途最新导出（SKU + SKU别名）、EN 物料/客户物料号、赛狐商品 SKU。
- 输出：给运营人员的配对建议表，尽量可导入赛狐（`import_product_msku_match` 模板），无法唯一确定的进入人工核对。
- 长期目标：用已配对数据训练匹配模型，覆盖通途别名登记不全的 FBA/MSKU。

## 2. 2026-08-13/14 新鲜快照

| 指标 | 数量 |
|------|------|
| 历史已配对审计 | 26,999 |
| Gold A 可训练标签 | 14,021 |
| Silver / Quarantine | 12,918 / 60 |
| Gold A 唯一 MSKU-目标 | 4,070 |
| EN 产品明细 / 明细错误 | 2,317 / 0 |
| 普通赛狐候选产品 | 2,259 |
| 当前在售未配对 | 3,557 |
| 高可信精确证据 | 87 |
| 四家族实验候选 | 550 |
| 特殊对象暂缓 | 434 |
| 无可靠候选 | 2,486 |
| V2 强证据建议 | 237 |
| V2 Top候选审核 | 904 |
| V2 低证据候选 | 2,335 |
| V2 冲突候选审核 | 2 |
| V2 对象专项 | 79 |
| V2 无候选 | 0 |

3,557 条严格对账：`87 + 550 + 434 + 2,486 = 3,557`。特殊对象包含 cover 244、combo 76、unknown 59、foam 55。所有源文件哈希写入标签摘要；后续建议前仍必须重新确认通途导出和赛狐缓存时效。
V2 严格对账：`237 + 904 + 2,335 + 2 + 79 + 0 = 3,557`。V2 已用证据图、对象本体、跨市场 ASIN 传播和 family 检索替代上一版窄匹配，仍不写赛狐。

## 3. 模型结论

试点家族为 `KS0001`、`KS0002`、`KS0248`、`KS0007`，按 MSKU/ASIN 连通分组切分，固定 seed 42。最终诚实评估为：

| 指标 | 结果 |
|------|------|
| family Top-1 / Top-2 | 94.79% / 99.51% |
| 原始 Candidate Recall@20 | 32.25% |
| Ranking Top-1 / Top-3 / Top-5 | 41.37% / 55.05% / 64.33% |
| MRR | 52.58% |
| production_ready | `false` |

排序评估中的 Recall@20 为 100%，是因为训练/评估排序器时注入了正样本，不能冒充原始候选召回率。真正决定能否自动化的是 32.25% 的原始 Candidate Recall@20；因此当前只能辅助人工收集候选，不能自动配对。修复颜色词子串误命中后分数下降，例如 `red` 不再从 `reading` 中被抽出；较低结果更可信。

## 4. 赛狐配对机制（已核实）

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

## 5. 现有入口

| 脚本 | 职责 |
|------|------|
| `missing_products/fetch_sellfox_pairing.py` | 拉取 Amazon + 多平台配对，缓存到 `out/pairing_cache/`，`--refresh` 强制重拉 |
| `missing_products/analyze_amazon_unmatched.py` | 在售未配对分析：别名命中、FBA/MFN、三角靠枕候选 |
| `missing_products/build_amazon_pairing_suggestions.py` | 生成可导入建议、需人工核对、三角靠枕建议、65 条不一致分析 |
| `missing_products/tongtu_data.py` | 通途 zip / 映射底表 / 别名读取 |
| `missing_products/build_mapping_workbook.py` | 生成通途→EN→赛狐映射表 |
| `python -m amazon_pairing.cli build-labels` | 清洗历史已配对数据，生成 Gold/Silver/Quarantine 标签审计 |
| `python -m amazon_pairing.cli snapshot-catalog` | 拉取 EN 与赛狐普通产品候选快照 |
| `python -m amazon_pairing.cli train-pilot` | 训练四家族分类器与 LightGBM LambdaRank，并输出独立指标 |
| `python -m amazon_pairing.cli suggest-active` | 生成八工作表的只读人工审核工作簿 |
| `python -m amazon_pairing.cli suggest-v2` | 生成证据图 V2 工作簿；可选 `--family-model`，使用低证据候选分层 |
| `python -m amazon_pairing.cli import-feedback <xlsx>` | 校验人工结论，追加含模型/来源哈希的 JSONL 反馈 |

关键产物（`missing_products/out/`）：

- `Amazon在售未配对分析_*.xlsx`：汇总 / 在售未配对全量 / 三角靠枕候选。
- `Amazon配对导入建议_*.xlsx`：可导入建议 / 需人工核对 / 三角靠枕建议 / 65条不一致分析 / 说明。
- `赛狐配对盘点_*.xlsx`：Amazon 已配对/未配对、多平台配对、通途别名_EN差异、待确认。

## 6. 已落地分层方案

1. **阶段 0 别名精确匹配（已做）**：平台SKU/MSKU 精确命中通途主SKU/别名，再经通途→EN→赛狐映射生成导入建议。覆盖 442/4,407，其中 91 条可直接生成导入，133 条因一对多或无 EN 映射需人工核对。
   - “无EN映射”含义：平台SKU命中了通途主SKU/别名，但该通途主SKU未出现在1411有库存EN映射中（未精确登记EN产品成品，或不在本轮有库存范围）；不是通途没有该SKU。
   - 建议表已含：平台标题(原文)、标题中文提示(粗略字典)、通途主SKU、EN产品编号/名称、赛狐SKU；65 条不一致表另含本地/期望双方SKU与中文名称。
2. **严格历史证据**：Gold A 要求通途主 SKU/别名唯一映射到 EN/赛狐目标，并与当前历史配对一致；唯一站点+ASIN 历史目标也可进入高可信页，但仍需人工确认。
3. **对象路由**：ordinary 才进入普通候选；cover、foam、combo 与 unknown 单独暂缓。Combo Listing 路由到 `TJ#` 套件流程，绝不强配普通 KS 产品。
4. **实验模型**：字符 TF-IDF 家族分类、属性冲突过滤、字符 TF-IDF 候选检索和 LightGBM LambdaRank 只在四个家族试点；可靠尺寸/颜色/面料冲突的候选不得出现在审核 Top-3。
5. **主动弃权**：family 置信度不足或候选全部存在可靠冲突时进入“无可靠候选”，不为提高覆盖率降低门槛。
6. **反馈闭环**：工作簿只允许固定结论枚举；手填 SKU 必须存在于候选 catalog。导入反馈时记录工作簿、catalog、family model、ranker 和 evaluation 的 SHA-256。

## 7. 下一步研究重点

- Amazon 标题是英文，EN 名称是中文，需要建立面料/颜色/尺寸双语词典。
- 已配对数据存在错误（例如 65 条不一致中多个 TT SKU 错配到同一个 `KS0437-MSTWBHLR-120x200x45-LIGHT...`），训练前必须清洗。
- 通途别名登记不全，尤其 FBA；别名精确匹配只能覆盖约 10%。
- 一个别名可能对应多个通途 SKU 或多个 EN 产品（一对多），不能自动去重。
- HM1510 海绵：EN REST 校验“客户物料号只能添加到 产品/套件# 物料组”，无法通过 API 给 HM1510 加客户码；且 `TT0031247K0064095-Foam` 没有 218x115x55 的 HM1510 物料。本子项目暂不处理。
- 先让运营审阅 87 条高可信证据和 550 条实验候选，积累剔除疑问后的人工 Gold 标签。
- 优先为四个家族补充专用结构化解析器和同款变体约束，改善原始 Candidate Recall@20；现阶段不应先引入通用 embedding 来掩盖属性冲突。
- 按家族分别评估，尤其 `KS0002` Top-1 只有 28.24%，不能被总体指标掩盖。
- 达到候选召回门槛前不讨论自动写入；即使未来达到门槛，仍需用户批准明确店铺/MSKU/赛狐 SKU 范围。
- 直到用户明确批准具体店铺、MSKU 和赛狐 SKU 的导入范围前，本项目不得调用 `matchByMsku`、`matchByAsin` 或任何多平台写接口。

## 8. 交接清单

1. 读本文档 + `missing_products/AGENT_HANDOFF.md`。
2. 如有新的通途导出，放到 `D:/Work/赛狐/商品/` 或 `D:/Work/赛狐/配对/`，脚本自动取最新。
3. 重跑 `fetch_sellfox_pairing.py --refresh` 前先确认 API 配额；日常分析默认用缓存。
4. 最新验证工作簿为 `amazon_pairing/out/Amazon在售未配对智能审核_20260814_090429.xlsx`，业务产物不提交 Git。
5. 反馈导入后重新训练前，先剔除“暂不确定”“对象类型错误”和其他疑问记录。
6. 所有写入赛狐/EN 的动作必须先经用户确认，禁止直接调写接口。
