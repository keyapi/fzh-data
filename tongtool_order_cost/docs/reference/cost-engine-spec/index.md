---
okf: v0.1
type: Index
title: cost-engine-spec 索引
description: EN/Colab 成本引擎的逐列与逐 cell 逆向规格 —— 成本口径的单一事实源
tags: [reference, index, cost-engine]
---
# cost-engine-spec

> 本 bundle 是**成本口径的单一事实源**：任何成本列怎么来、为什么两套系统不一样、缺哪些数，先查这里。

| 文档 | 说明 |
|------|------|
| [00-review-brief.md](00-review-brief.md) | **评审任务书**：给其它 Agent / 其它对话做独立核验用（待证伪断言清单 + 证据要求 + 输出格式 + 易错点 + 禁止事项） |
| [01-overview-and-glossary.md](01-overview-and-glossary.md) | **入口**：系统上下文、范围/非目标、数据时点、实体与编码速查、用户惯用语对照、「疑问→答案」总表 |
| [02-keys-and-entities.md](02-keys-and-entities.md) | **键与实体**：三套键（`品类尺寸面料编码`/`品类尺寸编码`/`重量模板编号`）、前缀实体、分流字段、6 列去重键、键的坑 |
| [03-data-sources.md](03-data-sources.md) | **数据源清单**：GS 工作簿/ws（谁写谁读多少行）+ EN 报表/Doctype/app；缺口指向覆盖率审计 |
| [04-cost-decision-tables.md](04-cost-decision-tables.md) | **核心**：按 目的地 × 绍兴发货方式 的各分项取值决策表（皮壳/头程/目的地加工/绍兴侧加成）+ A/B1/B2/B3 四方案对照 |
| [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) | 老成本引擎逐 cell 逆向（Colab notebook + Google Sheet）：全流程骨架、每列取值链、与 EN 对照、13 开关 |
| [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md) | 「剔除额」完整定义（`get_sxbzbcp_deduction` 只减不加）· 受影响列清单 · 半成品发货成本是否受影响（非 FBA=不影响）· Jack commit `533ecad`/`cf0bbbd`(2026-10-10) · 09-03 快照证实未扣 |
| [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) | EN 39 个分流点穷举（9 文件，路径:行号）+ `Tongtu Shipping Warehouse` 40 行配置 + 目的地加工成本/头程三列取值链 |
| [07-colab-vs-en.md](07-colab-vs-en.md) | **替换进度表**：逐成本列标「A 现状取数 / EN 取数 / 是否已切 / 7 月差额」（皮壳✅Δ=0、头程✅Δ=0、二次加工❌+225,982、绍兴二次加工❌+38,930） |
| [08-special-cases.md](08-special-cases.md) | **特例**：`-COVER`/`-PPCOTTON`/`-FOAM`（含数字后缀）、自采购、拆单系数、Product Bundle、FBA 清零、是否需尾程、`HEAD-SX→0`、品类白名单清零、灰区 `fillna(0)`、`0.001` 占位、星链替换 |
| [09-known-issues-register.md](09-known-issues-register.md) | **问题登记册**：EN 内部不一致（A）、时序错配（B）、数据缺口/脏数据（C）、命名坑（D）、待证实（E）。所有「未证实」指向此页 |
| [10-glossary.md](10-glossary.md) | **术语表（字段级）**：实体前缀/成本来源编码/头程编码/SKU 后缀/EN 字段/GS 列名/Colab 开关两表速查 |
| [11-plan-new-ustx-processing-table.md](11-plan-new-ustx-processing-table.md) | **可行性方案**：新建「美中USTX二次加工成本」ws —— 键与匹配链、**「行怎么建全」清单**（骨架=绍兴表 177/177）、**缺口 4 类分法与处置**（§3.3，已按 Codex 改写）、风险、分步实施、对拍验证 |
| [12-weight-template-mapping-spec.md](12-weight-template-mapping-spec.md) | **重量模板映射机制**：EN 里权威的只有「品类编码↔KS组」+「面料↔缩写」；**尺寸档规则不在 EN**（反推复现率 31.7%/62.9%）；161 空键仅可补 45 |
| **[13-codex-review-corrections.md](13-codex-review-corrections.md)** | **⚠️ 外部独立复核（Codex, 2026-10-16）的更正登记**：四种时点不可混用 · 新表公式**搜错列**已更正 · 「改来源码无影响」**是错误归因** · 第15条真问题是**幂等**（A6 作废）· 51条正确分类（B组粗分类作废）· colab 逐 cell 文 4 处更正。**与其它页冲突时以本页为准** |
| [14-colab-key-derivation-chain.md](14-colab-key-derivation-chain.md) | **主键推导链**：老引擎 `品类尺寸面料编码` 的三段（品类/尺寸/面料）怎么拼出来 —— `品类使用面料` 表结构 · 尺寸 4.2(cell_066) 与 4.7.2(cell_141) 两条路径 · 面料从 `材料价格明细` 取 `材料编码` · **海绵(HM) 三层特例** · 已被覆盖的旧逻辑 · 带 cell 定位的完整链 |
| [15-exception-rows-monthly-impact.md](15-exception-rows-monthly-impact.md) | **异常行月度影响面**：161 空键 / 51 行在 **7/8/9 月**各自的美中命中行数·键数·占比（41/4379=0.94% · 36/5479=0.66% · 21/2959=0.71%）；Codex 4 类分月拆解；逐月**新增空键**（断链在扩大）；161 空键本季仅 **17 个**被用到 |
| **[16-customer-sku-direct-path.md](16-customer-sku-direct-path.md)** | **⚠️ 重大建议**：改用「**通途SKU → EN 客户物料号**」直连取 USTX 成本 —— 实测美中 **4372/4379=99.8%** 命中、在 0 损失下多覆盖 41 行、且比重量模板更精确；**一次绕开**品类-尺寸-面料/重量模板/尺寸档/161 空键四座山。**可能推翻 [11](11-plan-new-ustx-processing-table.md) 的建表前提** |
| [17-codex-round2-corrections.md](17-codex-round2-corrections.md) | **⚠️ Codex 第二轮复核更正**：公式**歧义仍会取值**（加标记≠阻断）· **「建表不启用」没有隔离**（notebook 按名自动读）· 月度推论更正（「死键」「断链扩大」不成立）· 9 月应 **≥63 行** · 白名单**未证明已归零** · 1:2:4 **源码存在但未触发**。**含安全事件：建议轮换服务账号密钥** |
| [18-sku-direct-impact-on-order-merge.md](18-sku-direct-impact-on-order-merge.md) | **旁支**：通途SKU 直连对订单**合并/拆分/去重**的影响 —— 合并不按 `品类尺寸面料编码`/`通途SKU` 分组（按 `订单号公共部分+平台SKU(统一)`），但**存留行取 `first`** → 换 SKU 后**键身份从「产品级」降为「包裹级」**（核心风险）；3 处拆包逻辑依赖 `品类`/`产品名称`；**7 月只读复跑**：B/C/D=10/14/186 组（与 PR#280 §8.2 逐项吻合）、**歧义阻断桶=0**；含**待拍板 Q1–Q7**。**已按 [20](20-codex-round3-corrections.md) 收窄表述**（不主张"成本更准"） |
| [19-service-account-key-rotation-checklist.md](19-service-account-key-rotation-checklist.md) | **旁支**：Google 服务账号**密钥轮换清单**（影响面/步骤/Colab 内嵌替换/回滚；只写文档，不碰凭证） |
| **[20-codex-round3-corrections.md](20-codex-round3-corrections.md)** | **⛔ Codex 第三轮复核：[16] 结论不予通过** —— 「更准/占优/零损失/四类问题消失」**全部撤回**；覆盖率定义更正（候选≠可唯一取成本，唯一 4369 + 3 歧义）；**我的比较脚本对客户码取 max、掩盖了多候选（自证反例）**；23 处应拆 3+3+17；7 行真实是白名单+五件套；「0」来自估值回退；**7 月历史不可直接回算**（五件套 creation 5/21 vs Version 8/11）；含 6 条可落地修订方案 |
| [21-offline-evidence-table.md](21-offline-evidence-table.md) | **离线证据表 v3（修 Codex 第四轮 4 项）**：4379 行；处置 = auto_ok 3877 / **review_source_unverified 474** / value_diff 11 / bundle 4 / ambiguous 3 / business_exempt 3 / **ambiguous_weight_template 3** / alias_pending 2 / direct_only 2；取值来源**带时点**（`bom_cost_verified` vs `unverified_*`）；含完整 manifest（脚本/输出哈希、两时点、关联依据）。**关键诊断：20261016 导出 vs 当前 BOM 240/240 一致 → 机制对、差异是时点漂移** |
| [22-review-brief-for-cursor-grok.md](22-review-brief-for-cursor-grok.md) | **给 Cursor/Grok 的自足评审说明**（零上下文）：只读本页+4 个文件即可复核 v2 表；含 6 条必证伪断言、已知历史（别重复报）、输出格式、约束 |
| **[23-en-report-rest-fetch-and-timepoints.md](23-en-report-rest-fetch-and-timepoints.md)** | **自己拉 EN 报表的配方 + 三时点对照**：`POST /api/method/frappe.desk.query_report.run`（**必须** `filters.item_group` + `ignore_prepared_report=1`）+ 3 个坑；**机制三重验证**（自拉 ≡ 手导 2101/2101；自拉 ≡ DB BOM 1610/0）；**9/3→10/16 仅漂移 9 个产品(0.4%)**；据此收窄「474 行待业务」 |
| [24-business-checklist.md](24-business-checklist.md) | **业务操作清单**：502 行按 8 桶 → 「要谁确认什么」；**474 行可批量接受**（机制已证、多数是覆盖差异），真正逐条判断的只有 **28 行**；**唯一要你拍板的一句**：7 月核算用 9/3 还是 10/16 的 BOM 状态（影响 3 个产品族） |
| [25-two-lines-and-28-rows.md](25-two-lines-and-28-rows.md) | **两条横向对比线（9/3 / 10/16）+ 大白话版 28 行**：A 242,029 / 线1(9/3) 467,648 / **线2(10/16) 463,893**，两线差 **−3,755￥**；28 行按 7 类列出「要干什么 / 涉及哪些 SKU」；另说明 474 行为何可批量接受 |
| [26-answers-to-28-rows.md](26-answers-to-28-rows.md) | **28 行逐条答复**：27.04/101.07 的**确切出处**（旧 parser 归错款）；**五件套 = Σ(子件×数量) = 0**（现状 208.64 待改）；**海绵闸方案**（键含 FOAM/HM → 二次加工 0，换直连必须加）；**KS0423 gsheet 637 行确认是错的**（应删/改）；针线扣/棉包维持归零；TT0000718/756 无需处理 |
| **[27-gsheet-source-root-cause.md](27-gsheet-source-root-cause.md)** | **⚠️ gsheet 源头根因诊断（2026-10-17）**：**改 `import皮壳成本` 无效**（A/B 是 `IMPORTRANGE` 拉源表的）；三样例**都不是 Colab 解析错** —— ①`TT0312576` 真因是**键撞车**（`品类使用面料` 把「床头靠枕-米白/腰果花/蓝色」误用大靠背的 `KS0423/0424/0425`），EN 证明 `ZLMB#KS0364…` 本就正确 ⇒ **更正 [26] §6 的「删 637」**；②`TT0031054` 是**表里 F 列跨产品**；③`TT0312705` 自洽无误。含**精确到单元格的拟改清单 + 风险 + 已备份** |

## 疑问 → 答案位置

（完整 18 项见 [01](01-overview-and-glossary.md) §8；此处为高频入口）

| 疑问 | 去哪 |
|---|---|
| A/B1/B2/B3 各用了哪些成本？ | [04](04-cost-decision-tables.md) §5 + [07](07-colab-vs-en.md) |
| 某成本列到底怎么算？ | [04](04-cost-decision-tables.md)（决策表）+ [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md)（老引擎逐 cell） |
| 头程 `HEAD-USTX` / `HEAD-USTX-PK` 有何区别？ | [04](04-cost-decision-tables.md) §2.2；[08](08-special-cases.md) §7 |
| 「二次加工」用绍兴包装成品还是美中包装成品？ | [04](04-cost-decision-tables.md) §6；[07](07-colab-vs-en.md) |
| 某个键/前缀代表什么物料？ | [02](02-keys-and-entities.md) §2；[10](10-glossary.md) |
| 某张表谁写谁读、多少行？ | [03](03-data-sources.md) |
| 老系统哪些表会缺行？缺多少？ | [03](03-data-sources.md) §3；[../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md) |
| `-COVER` / `-PPCOTTON` / `-FOAM` 是什么？ | [08](08-special-cases.md) §1 |
| 剔除额是什么？影响半成品发货成本吗？ | [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md)；[04](04-cost-decision-tables.md) §4 |
| EN 内部自己一致吗？ | [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md)；[09](09-known-issues-register.md) |

## 相邻文档（不在本 bundle）

- 专项调查：[../en-ustx-no-bom-items-spec.md](../en-ustx-no-bom-items-spec.md)、[../en-pl-finished-processing-nonzero-spec.md](../en-pl-finished-processing-nonzero-spec.md)、[../en-material-request-type-spec.md](../en-material-request-type-spec.md)、[../en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md)、[../en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)
- 美中 USTX 方案对比：[../monthly-profitability-audit.md](../monthly-profitability-audit.md)、[../ustx-cost-caliber-note.md](../ustx-cost-caliber-note.md)、[../en-ustx-bom-wage-rate-spec.md](../en-ustx-bom-wage-rate-spec.md)
- 覆盖率审计：[../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)
- Colab 引擎总规格：[../colab-cost-engine-spec.md](../colab-cost-engine-spec.md)
