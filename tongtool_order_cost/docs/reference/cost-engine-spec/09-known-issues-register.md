---
okf: v0.1
type: Reference
title: 成本引擎 · 问题登记册（缺口 / 冲突 / 口径漂移 / 未证实）
description: 汇集本次调查（2026-10 全部对话与子 Agent）发现的全部问题：EN 内部口径漂移、时序错配、数据缺口、命名坑、待证实项；每条给影响与处置建议
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, issues, register, risk, reference]
---

# 成本引擎 · 问题登记册

> **性质**：登记册（register），不是待办清单。**未指派任何人、未排期**（用户 2026-10-15 明确：先记录）。
> 每条含：**现象 → 影响 → 证据 → 建议处置**。

## A. EN 内部不一致（同一概念多处实现、口径互不相同）

| # | 现象 | 影响 | 证据 | 建议 |
|---|---|---|---|---|
| A1 | **「按发货方式组合绍兴成本」有 ≥3 处实现，口径不同**：报表 `sx_cost_all`（半成品→皮壳+成品成本−剔除，**不加半成品**）／订单同步 `sx_shipping_cost`（半成品→皮壳+半成品成本）／`pllc_cover`（另一套） | 同一物料在报表与订单同步下**绍兴成本不等**；下游引用不同源就得到不同成本 | [en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md)、[en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) | 由财务定「哪一处是权威」，其余对齐 |
| A2 | **EN 内 39 个按发货方式/目的地类型的分流点，分散在 9 个文件** | 改一处口径极易漏改其它处 | [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) | 抽成单一口径函数 |
| A3 | **口径漂移 3 处**：`order_sync` 成品 `-FOAM` 头程不 clamp；`delivery_note_filling_cost.sx_cost_all` 缺自采购/剔除规则；`doc_event` 不认后缀且写 `custom_valuation_rate` | 同一 SKU 在不同链路成本不同 | 同上 | 逐条对齐 |
| A4 | **FBA 分支无视发货方式与 `-COVER`/`-FOAM` 特例**（一律取绍兴总成本 + 成品头程） | 带后缀的 FBA 件可能取到不该取的口径 | [en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md) | 确认是否有此类订单 |
| A5 | **BOM 复制缺幂等**：`check_bom_exists`（`utils/bom.py:127–145`）只查 `docstatus=0`（草稿），而 `:290–299` 插入后**立即 `submit()`**（→ docstatus=1）→「已存在」**永不命中**；异常也被吞掉当作不存在 → 重复创建 | 重复执行会堆重复 BOM | [13](13-codex-review-corrections.md) §2（Codex 复核更正）；[work_order_task issue #3](https://github.com/keyapi/work_order_task/issues/3) | **暂不建 todo**（用户 2026-10-15）；修复方向=**幂等 + 源版本更新政策**，**不能机械把 `0` 改 `1`** |
| A6 | ~~表单「复制BOM」按钮路径没有 PP棉 闸门~~ **【2026-10-16 作废】** | **原判错误**：单 BOM 表单**前端有**、自动 `on_submit` **服务端有**、独立批量 **服务端有**。真正的问题是 A5 的幂等 | [13](13-codex-review-corrections.md) §2 | **本条作废**，不建 todo |
| A7 | **`zelin_pp`（已卸载）留下的 Property Setter**给 `default_material_request_type` 加了第 6 个选项 `Phantom` | UI 可能出现无效选项（数据 0 条） | [en-material-request-type-spec.md](../en-material-request-type-spec.md) | 清理残留 |

## B. 时序错配（拿错时点的数据会得出错误结论）

| # | 现象 | 影响 | 建议 |
|---|---|---|---|
| B1 | **GS「EN产品BOM成本列表20260202」是 2026-09-03 导出**，而 EN 线上持续变化（2026-09-15 部分物料换默认 BOM） | 用快照对线上必错（例：`USTXBZCP#KS0455-92x56x75` 快照 206.479 vs 现默认 90.306） | 任何对比**先声明时点**；见 [01](01-overview-and-glossary.md) §4 |
| B2 | **剔除额改动是 2026-10-10（Jack）**，09-03 快照**尚未含** | A/B2 用的 `绍兴包装成品成本` 是**未扣剔除额**的版本；7 月核算当时也没扣 | 若要与新 EN 对齐，需按新口径重算（影响面：成品档的绍兴侧加成） |
| B3 | **覆盖率审计的「0 缺失」是 2026-10-15 线上态** | 不能反推「7 月当时也全」（用户 7 月核算后很可能手工补过） | 覆盖结论一律标注观测时点 |

## C. 数据缺口与脏数据

| # | 现象 | 影响 | 证据 |
|---|---|---|---|
| C1 | **`测算 美中USTX二次加工成本` 缺 115/615 键（美中缺 43.5%）** | 影响 1146 行订单；是「新建美中成本表」的最痛处。**【2026-10-16 按 Codex 复核改写】** 这是**真缺行**（测算表未维护到 177 键，体系不同），**与 C5 的「行在、断链」不是同一缺口**；与「7 月 51 行需专门处理」也无重叠 | [old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)；[15](15-exception-rows-monthly-impact.md) §6 |
| C2 | **头程 USTX 核算表缺 78 键，但 77 个是「行在表内、`品类尺寸面料编码` 列未回填」** | 可通过 `品类尺寸编码`+面料 rematch 修复（行级 2443/2446） | 同上 |
| C3 | **96 个美中 USTX 物料完全没有 BOM**（86 空壳变体 + 10 未建；全部零业务引用；89 个 `valuation_rate=0`） | 其成本走 `Item.valuation_rate` 回退；**不随工资率变**。**【2026-10-16 按 Codex 复核改写】** 这 96 个**零业务引用**，**不进订单行**，与「7 月 51 行 / 161 空键」（订单侧断链）**是两类不同缺口**，不重叠 | [en-ustx-no-bom-items-spec.md](../en-ustx-no-bom-items-spec.md)；[15](15-exception-rows-monthly-impact.md) §6 |
| C4 | **PL 16 个「成品却带非零加工成本」**（15 启用合计 1463.17） | 与「成品→国外加工=0」矛盾；来源是 2025-02-21 建料批次**人工 `valuation_rate` 残值**；皮壳侧另有 18 个同类残值 1707.801 | [en-pl-finished-processing-nonzero-spec.md](../en-pl-finished-processing-nonzero-spec.md) |
| C5 | **`import皮壳成本` 同键指向不同重量模板的冲突键 3 个** | 对比中已按「不猜首/末行」排除对应行。**【2026-10-16 按 Codex 复核改写】** 精确化：是 **3 个键**（`YM-HS-018-153-HLR`／`KS0423-140-XNEOSTH`／`KS0423-153-XNEOSTH`）——**7 月订单命中 3 行**（键 `KS0423-153-XNEOSTH`，源 CSV 物理行 7068/7942/8075），**8 月 1 行、9 月 2 行**（**非 7 月独有**）。Codex §5.1：`KS0423-*` 的 637（指 KS0364）候选须撤下，**重算皮壳/加工/头程**。本条只是「7 月 51 行需专门处理」的 **4 类之一**；其余 3 类是空 key 白名单 3 行 / 源映射空值（161 空键命中 41 行）/ RD 五件套 4 行 | [04](04-cost-decision-tables.md)、[13](13-codex-review-corrections.md) §5.1、[15](15-exception-rows-monthly-impact.md) §3 |
| C6 | **`美中加工成本, USTX` 有 335 行（美中）为字面 0**（非空串） | 按原值 0 计入，不猜测回退。**【2026-10-16 按 Codex 复核改写】** 精确化：7 月美中 **45 个键 / 335 行**为字面 0。**这与「161 空键」是两回事**——字面 0 是**表内有值**（`zero_literal`），空键是**表内无值**（`no_weight_template`），处置不同（前者取 0、后者要分 4 类处理）。月度数见 [15](15-exception-rows-monthly-impact.md) | [monthly-profitability-audit.md](../monthly-profitability-audit.md)；[11](11-plan-new-ustx-processing-table.md) §3.3 |
| C7 | **重量模板命名不一致 1 例**：`ZLMB#KS0383-HLR- 140*50*24`（空格 + `*`）vs `...-140x50x24` | 直连会漏匹配 | [old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md) |
| C8 | **`default_material_request_type` 自 2025 年起不再维护**（2024 M>P，2025 M<P） | 不能拿它当业务标记（多数是没改过的默认 `Purchase`） | [en-material-request-type-spec.md](../en-material-request-type-spec.md) |
| C9 | **绍兴发货方式「成品」是一个单一桶**，混着「绍兴直接采购 / 不用加工 / 仍需加工后发成品」 | 三者**不可区分**；现在靠「恰好没建 BOM」碰巧为 0，**一旦补 BOM 就会冒出错误加工成本** | [en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md) |

## D. 命名/概念坑（易误导）

| # | 坑 | 说明 |
|---|---|---|
| D1 | GS 表 **`import皮壳成本`** 的三列叫「绍兴/美国/波兰**二次加工成本**」，**实际装的是各地的「包装成品成本」** | 表名、列名、内容三者不一致；绍兴列与 `importBOMCostList.绍兴包装成品成本` 在 4328/4331 行相同 |
| D2 | GS「**EN产品BOM成本列表20260202**」的日期是**旧名** | 实为 2026-09-03 导出 |
| D3 | 「**国外加工成品 BOM**」是**口误** | 实际只有「国外**包装**成品」（`USTXBZCP#`/`USNJBZCP#`/`PLBZCP#`）；无「国外加工成品 BOM」的任何证据 |
| D4 | `HEAD-*` 是**头程**编码，**不是**加工成本 | 不存在 `HEAD-USFBA` 加工成本列 |
| D5 | 「**绍兴总成本**」（报表列）≠ 三段相加 | 实为 `皮壳 + 绍兴包装成品成本`；「三段相加」是用户 **Colab 侧**老设计的局限 |
| D6 | 「**绍兴二次加工成本**」在 7 月订单里**美中全 0** | 非空的是 PL 180 行 + USNJ 22 行 |

## E. 待证实（本次未能定论）

| # | 项 | 已排除 |
|---|---|---|
| E1 | 7 个非零 `valuation_rate` 的无 BOM 物料来源 | 已排除库存/采购/工单/BOM/模板传播；形态像人工填报 |
| E2 | **皮壳 1×/半成品 2×/成品 4× 倍数口径** —— **【2026-10-16 部分解决】** 字面**已找到**：`cell049` 的 `fill_shipping_cost`（L72–129）docstring 明写「半成品 = 2×皮壳，成品 = 2×半成品 = 4×皮壳」（[14](14-colab-key-derivation-chain.md) §、[colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) §C/L086） | **仍待判定**：该函数**只更新已存在的发货方式行、不给缺失方式新建行** → 「实际是否触发、触发面多大」未证实（原判「notebook 里无字面」**已过期**） |
| E3 | 半成品剔除项在 09-03 快照是否生效 | 快照未见生效（与 10-10 提交时序吻合） |
| E4 | `绍兴自发货` / `欧洲海外仓` / `加拿大海外仓` 三类 | 配置表**有选项但无配置行** |
| E5 | 剔除额的月度金额 | 未定量 |
| E6 | 「谁在 2024 把 `default_material_request_type` 设成 `Manufacture`」 | 无痕迹 |
| E7 | `KS0101-45`（该物料 3 张 BOM 全 `is_active=0`）成因 | 未查 |
| E8 | 两个 SET 款共用 101.07 / 一个 0.001 占位的来源 | 未查 |
