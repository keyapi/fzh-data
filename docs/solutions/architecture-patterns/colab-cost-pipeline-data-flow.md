---
okf: v0.1
type: Reference
title: 旧 Colab 成本链 — 数据流关系图（订单 → GS → Colab → EN ↔ 赛狐）
date: 2026-10-08
last_updated: 2026-10-08
category: architecture-patterns
module: tongtool_order_cost
problem_type: architecture_pattern
component: colab-cost-pipeline-data-flow
severity: high
applies_when:
  - "要直观理解旧 Colab 成本链的读数/写回路径与各键"
  - "定位某个数值来自哪张表/哪个 cell，或某个字段在哪几处被重复维护"
tags: [colab, cost-pipeline, data-flow, mermaid, keys, conflict-points]
related_components: [colab_kit, tongtool_order_cost]
---

# 旧 Colab 成本链 — 数据流关系图

> **维护约定：本档案随改动同步更新。** 键、写回目标、冲突点变化时更新。
> 配套：[Colab 逐段现状](colab-cost-pipeline-current-state.md) · [GS 清单](colab-gsheet-inventory.md) · [EN 成本侧现状](en-cost-side-current-state.md)。

```mermaid
flowchart TB
  subgraph SRC["源头系统"]
    TT["通途 ERP2<br/>订单明细导出（自发货 + FBA）"]
    ENAPP["EN（ERPNext）<br/>BOM Cost List 报表<br/>+ Item.customer_items"]
  end

  subgraph GSO["通途订单YYYYMM（每月新建）"]
    O_RAW["ws 2026年M月订单 ★近原始<br/>（订单号带 _1/_2 后缀）"]
    O_RAW_FBA["ws 2026年M月FBA订单"]
    O_MID["ws 写回2026年M月订单<br/>（cell 128 中间写回，全列）"]
    O_FIN["ws 写回2026年M月FBA订单和非FBA订单<br/>（cell 151 最终合并）"]
    O_CHK["ws 检查运营人员-写回…（cell 162）"]
    O_AMZ["写回Amazon…（cell 177）<br/>写回所有订单…（cell 179）"]
  end

  subgraph GSC["财务部绍兴成本核算表单2023"]
    SX_OLD["ws 皮壳成本平均202409-…（用于通途订单202502）<br/>★旧表：品类尺寸面料编码 ↔ EN重量模板物料号（桥接）<br/>+ 当月给分公司发货类型（停更）"]
    EN_BOM["ws EN产品BOM成本列表20260202<br/>产品编号/客户物料号/绍兴发货方式<br/>皮壳·半成品·成品成本/三仓加工成本/头程"]
    SX_MERGE["ws SX合并EN成本（cell 103 写回）"]
    GS_CFG["ws 品类使用面料 / 材料价格明细 / 损耗明细<br/>/ 人工费日常费 / 产品用料工时明细"]
    INBOUND["ws 皮壳入库N月 → 写回皮壳入库N月（cell 34）"]
    SX_AVG["ws 皮壳成本平均…（cell 95 写；⚠ 用了未定义变量 gsheet_name）"]
  end

  subgraph GS2["二次加工成本2022"]
    IMP["ws importBOMCostList<br/>=IMPORTRANGE(EN!A:Y)"]
    IMPPK["ws import皮壳成本<br/>=INDEX(importBOMCostList!$N/$R/$X, MATCH(码,…$Y,0))<br/>→ EN 绍兴包装成品成本 / 美东加工成本USNJ / 波兰加工成本PL"]
    P_SX["ws 绍兴二次加工成本"]
    P_US["ws 美国二次加工成本"]
    P_PL["ws 波兰二次加工成本"]
  end

  subgraph GSH["头程运费成本"]
    H_MERGE["ws 头程运费合并（cell 41 写）"]
    H_EN["ws EN头程运费 / EN头程运费_处理后（cell 47/49 写）"]
    H_REPL["ws 头程运费合并替换EN（cell 51 写）"]
    H_PRICE["ws 头程运费单价记录RMB<br/>+ 各分公司…核算（表内公式=重量×单价/1000<br/>且波兰核算自带一列'发货方式'）"]
  end

  subgraph GSF["和财务部共享"]
    WH["ws 订单发货仓库对应成本来源（47 数据行 + 表头）<br/>→ 成本来源编码 / 头程编码 / 二次加工来源编码"]
    FX["ws 汇率（逐月列 202208…202609）<br/>col_name_select_exchange_rate=YYYYMM"]
  end

  TT --> O_RAW
  TT --> O_RAW_FBA
  ENAPP --> EN_BOM
  ENAPP --> IMPPK

  O_RAW -->|cell 56/66 解析 品类/面料/尺寸| PARSE["cell 66 产品名解析<br/>→ 品类尺寸面料编码"]
  GS_CFG --> PARSE
  PARSE -->|cell 71-92 合并多行| MERGE["4.2.2 / 4.2.3<br/>键=(订单号_公共部分, 平台SKU_统一)"]

  SX_OLD --> C101["cell 101 df_sx_nodups"]
  EN_BOM --> C99["cell 99 df_en_zlmb（不含 绍兴发货方式）"]
  EN_BOM --> C45["cell 45 df_en_zlmb（含 en绍兴发货方式）"]
  C101 --> C103["cell 103 SX合并EN成本<br/>键=EN重量模板物料号"]
  C99 --> C103
  C103 --> SX_MERGE
  MERGE --> C105["cell 105（4.3.1）<br/>合入 当月给分公司发货类型"]
  C103 --> C105

  H_PRICE --> H_MERGE
  C41["cell 41 读头程各 ws"] --> H_MERGE
  C45 --> C47 --> C49 --> H_EN
  H_EN --> C51["cell 51 合并 EN+GS"] --> H_REPL
  H_REPL --> C109["cell 109（4.4）<br/>只带 头程运费金额"]
  C105 --> C109

  P_SX --> C111["cell 111 读多个 ws<br/>月列='二次加工成本多月202511'<br/>来源编码按 ws 名包含关系推断"]
  P_US --> C111
  P_PL --> C111
  WH --> C111
  GS_CFG --> C111
  C109 --> C128["cell 128（4.6）<br/>★0.001 注入点<br/>成品 & 2CJG-PL → 二次加工成本=0.001"]
  C111 --> C128
  FX --> C109

  C128 --> O_MID
  O_MID --> C135["cell 135 白名单 ls_col_order_keep（71 列）<br/>⚠ 丢掉 EN绍兴包装半成品/成品成本"]
  C128 --> C146["cell 146-148 FBA<br/>copy + drop + rename（保留那两列）"]
  C135 --> C151["cell 151（4.8）concat"]
  C146 --> C151
  C151 --> O_FIN
  C151 --> C162["4.9.x 运营人员"] --> O_CHK
  C151 --> C177["4.8.2.1 Amazon"] --> O_AMZ
  C151 --> C179["4.8.2.2 全量"] --> O_AMZ
  O_FIN --> PIVOT["财务透视表 / 运营利润视图"]

  C128 -.-> CONF["⚠ 同一个'发货方式'概念 4 处并存<br/>① 旧表 当月给分公司发货类型（成本选择用它）<br/>② EN 绍兴发货方式（头程用它）<br/>③ 头程核算 ws 自有'发货方式'列<br/>④ Colab 订单上只有 ① 这一个字段"]
  SX_OLD -.->|停更·仅作桥接| CONF
```

## 读图要点

1. **两条"EN→Colab"入口，同名不同物**：`cell 45` 的 `df_en_zlmb` **含** `en绍兴发货方式`（只服务头程）；`cell 99` 的 `df_en_zlmb` **不含**（服务成本）。
2. **桥接单点**：旧表 `皮壳成本平均202409-…` 提供 `品类尺寸面料编码 ↔ EN重量模板物料号`，是 `cell 103` 的合并键；也是 202606 那 139 行"无 EN 匹配"的成因。
3. **`二次加工成本` 的真实来源**：GS `二次加工成本2022` 的活跃列 —— 它本身是 `IMPORTRANGE` + `INDEX/MATCH` 指向 EN 的公式，**EN 无值时回落到手填旧列**（绍兴 188 / 美国 40 / 波兰 112 行）。
4. **`0.001` 注入点**：`cell 128`，条件依赖**旧字段** `成品`（应由 EN `绍兴发货方式` 判定）。
5. **列丢失点**：`cell 135` 白名单未收录 `EN绍兴包装半成品成本`/`EN绍兴包装成品成本` ⇒ 非 FBA 行在最终表为 NaN（仅因 FBA 帧是整份拷贝而重新出现）。
6. **写回目标共 7 处**：`写回2026年M月订单`(128)、`写回…FBA订单和非FBA订单`(151)、`检查运营人员-…`(162)、`写回Amazon…`(177)、`写回所有订单…`(179)、`合并多月非FBA通途订单`(186)、`FBA合并多月通途订单`(190 读)。
7. **"发货方式"4 处并存**（① 旧表字段 ② EN `绍兴发货方式` ③ 头程核算 ws 自有列 ④ Colab 订单字段=①）—— 是本链最根本的不一致源。
8. **每月跑两遍（顺序不可颠倒）**：第一遍 `4.3.1–4.6 → 4.6.1`（非 FBA，写 `写回{月}订单`）；第二遍 `4.7.1/4.7.2 → 再跑 4.3.1–4.6（⚠不跑 4.6.1） → 4.7.3/4.8`（FBA，写 `写回{月}FBA订单` 后合并）。图上的 `C128 → O_MID` 因此**发生两次**，且 `C99–C128` 复用同一个全局 `df_order_cost`。详见 [Colab 档案 §1.1](colab-cost-pipeline-current-state.md)。
