---
okf: v0.1
type: Reference
title: 供应链整合调研 — 证据账本
description: 全部来源与证据强度登记；厂商主张(V)与独立证据(I)分离；未找到项单列
date: 2026-10-20
tags: [supply-chain, research, sources]
---

# 证据账本

> 引用格式：正文写 `[S1-012, B]`。新增条目按 ID 顺序追加，不重排已有 ID。
> 时间基准：2026-10（AI 与开源类信息 6 个月即可能过期，必须写日期）。

## 证据等级

| 等级 | 含义 |
|---|---|
| A | 一手数据 / 同行评审 / 官方规范 |
| B | 独立机构评测 / 可复核方法 / 有代码与数据的工程复盘 |
| C | 厂商文档或案例（只能证明「厂商声称」） |
| D | 博客 / 轶事 / 无方法说明的二手转述 |

## 类型

`P` 论文 · `V` 厂商主张 · `I` 独立证据 · `C` 可复现代码或实验

## 已登记来源

| ID | 主张 | 来源 | 类型 | 日期 | 原文摘录 | 强度 | 用于 |
|---|---|---|---|---|---|---|---|
| S1-001 | 端到端履约蓝图已在 main，定义阶段 0–9、数量分层与四组对账等式 | `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` | C | 2026-10-20 核实 | 「每个日期带来源与置信度」 | A | 01 §2/§7 |
| S1-002 | 履约查询实现覆盖阶段 0–3，含证据分层与异常→下一行动 | PR #291 `EN_API/fulfillment/`、`fulfillment_query.py` | C | 2026-10-20 | `FieldValue(kind=fact/derived/estimate/assertion)` | A | 01 §2/§7 |
| S1-003 | 通途订单侧输入事实层可复用，含件数/拆包/补发规则与审计闸门 | PR #294 `order_side_input.py` | C | 2026-10-20 | 快照 + `audit.json` + 17 sheet | A | 01 §2/§7 |
| S1-004 | 成本引擎规格与拆包裹合并「不重不漏」断言 | PR #295 `cost-engine-spec/00–31`、`group_split_rows` | C | 2026-10-20 | 守恒、件数=Σ皮壳行、歧义即阻断 | A | 01 §2/§7 |
| S1-005 | 补货量公式与断货删失口径已成一文 | PR #297 `pb-replenishment-sizing-from-sales.md` | C | 2026-10-20 | `月需求率 × 覆盖期 − 可用 − 在途` | A | 01 §2/§6 |
| S1-006 | 现成低库存扫描：通途分页、526 退避、钉钉推送 | PR #298 `stock_alert/` | C | 2026-10-20 | pageSize≤100、无 total | A | 01 §2/§7 |
| S1-007 | 受控办理 Demo 的治理模式：能力白名单、确认后执行、独立回读 | PR #288 `ops_assistant_demo/` | C | 2026-10-20 | read-then-guard | A | 01 §4.3 |
| S1-008 | demand_forecast 阶段 A 资料与方法选型已归档 | PR #304 `docs/research/2026-08-31-*` | C | 2026-08-31 / 归档 2026-10-20 | 43 张月表 202301–202607 | A | 01 §4.1 |
| S1-009 | PB 多方法预估实现存在且已归档 | PR #304 `pb_reconciliation/sku_forecast.py` | C | 2026-08-31 | M1/M2/M3/M3b + 区间 | A | 01 §4.2、E1 |
| S1-010 | 用户说的「上周网页 Agent demo」更可能是独立仓库版本 | `D:/Work/web-ai-assistant-review-20261012` @ `acb2dd8` | C | 2026-10-15 | 23 项测试 | A | 01 §4.3 |
| S1-011 | 通途订单月表 202301–202607 连续 43 张，可聚合出 SKU 月需求 | PR #304 数据可行性文档 | C | 2026-08-31 | 逐日逐行，含发货日期/通途SKU/数量/仓库 | A | 01 §4.1、E1 |
| S1-012 | PB 10-16 决策包与断货预警可作为 E1/E2 对拍基准 | 本机 PB 订单目录、Notion「PB 断货处理 2026-10-16」 | C | 2026-10-16 | 楔形枕补货 257 件 | A | E1/E2 |
| S1-013 | 钉钉头程表可机器读，但没有结构化 ETA | `dingtalk/dingtalk_sheet/AGENT_HANDOFF.md`、实读表头 | C | 2026-10-20 | 只有工厂确认交期/包装完成日期 | A | 01 §5、06 |
| S1-014 | EN 不扣减通途库存，Bin 不能当可用库存 | `pb-replenishment-sizing-from-sales.md` §4 | C | 2026-10 | 「不要用 EN 的 Bin」 | A | 01 §6 |
| S1-015 | 尾程费率分层模型与 EN 导入契约（历史资产） | PR #232（closed unmerged） | C | 2026-09 关闭 | V0–V4、Holdout、26 列契约 | B | 01 §3 |
| S1-016 | `practical-paths.md` 实际创建于 2026-09-02 17:35（文件名沿用 08-31） | 用户 2026-10-20 更正 | C | 2026-09-02 | 「不是 9/2 没有产出」 | A | 01 §4.1/§10 |
| S1-017 | 目前只有通途库存可用；EN 未同步通途；拆包/合并映射复杂；测试不碰 EN 生产 | 用户 2026-10-20 补充 | C | 2026-10-20 | 「目前我们只有通途库存数据…先别碰EN生产系统」 | A | 05 §4.4、06 B10–B15/C5/D8 |
| S1-018 | Codex 评审 5 项：生产数量口径、E1 修正、E2/E3 收窄、事实契约、计划引擎比较 | 用户转述 Codex 评审 #300 @ 7181415c | C | 2026-10-20 | 「总体接受…但尚不足以作为实施定稿」 | A | 09 |
| S1-019 | E1 修正后：测试期 TSB 0.511 / ens5 0.520 / naive 0.602；验证选 MA3 测试 0.575 | `experiments/e1_forecast/results.md` | C | 2026-10-20 | 见 results.md §4 | A | 09、05 §1 |
| S1-020 | 生产数量四分法：首道 JC / 末道 JC / 已提交 SE / 已提交 DN；produced_qty 仅展示 | `08-fact-contract.md` §1–§2 | C | 2026-10-20 | 「四个量必须分开，禁止互相替代」 | A | 05 §2、09 |
| S1-021 | 计划引擎比较：轻量自组 / ERPNext 原生 / FrePPLe / Odoo；翻转条件 | `05-synthesis.md` §3 候选 D | C | 2026-10-20 | 公开文档主张，未做 PoC | B | 05 §3、09 |
| S1-022 | Codex 第二轮复审 R01–R07：标签重叠、坏数量、DN 行键、收货分摊、需求冲减、互斥余额、引擎对照时点 | Codex #301 `dd2551ef` `claude-review.md` | C | 2026-10-20 | 「框架方向接近一致，实施契约尚未闭合」 | A | 10 |
| S1-023 | Codex 13 个合成契约样例全部 PASS（仅算例自洽） | #301 `contract_examples.py` 实跑 | C | 2026-10-20 | 13/13 PASS | B | 10 §4 |
| S1-024 | 共同框架/决策/样例：D01–D05 必须统一，B01–B07 可保留 | #301 `common-framework.md`/`decisions.md`/`semantic-examples.md` | C | 2026-10-20 | 同 cutoff 互斥余额、预测冲减、DN 行 ID | A | 10 §3–§4 |
| S1-025 | E1 R01/R02 修正后：标签交集空；验证选 Croston 0.448；测试 TSB 0.511 / ens5 0.520 / naive 0.602 | `experiments/e1_forecast/results.md`（R01/R02 修正版） | C | 2026-10-20 | `label_overlap_check.pass=true`；bad_qty=0 | A | 05 §1、10 §2 |
| S1-026 | G0 冻结基线：共同框架/事实契约/验收样例/决策表版本清单 + G1 门槛 | `11-common-baseline.md`、Codex #301 `5708609d` | C | 2026-10-20 | 标签 `supply-chain-g0-baseline-20261020` | A | 11 |
| S1-027 | G1 切片：三角靠枕 family（KS0001 + KS0248）；通途 GSheet 品类可能叫「三角」 | 用户 2026-10-20 确认 | C | 2026-10-20 | 「EN上分类更精确…两者区别很小」 | A | 11 §2.1、05 §5、06 A7 |
| S1-028 | 2026-04..09 月表可用、2026-10 缺失；三角品类主要仓 CENTRADE 1631 vs DANEEY 1586；品类值为「自产-三角靠枕-*」 | Google Sheets 只读核对（2026-09） | C | 2026-10-20 | 2026-09 三角 3963 行 / 4111 件 | A | 11 §2.1、06 B22 |
| S1-029 | G1 两仓 × 2026-04..09；G2/G3 用 43 个月（PR #304：202301–202607），季节性需 2–3 年 | 用户 2026-10-20 确认 + PR #304 | C | 2026-10-20 | 「6 个月数据…不一定必须；季节性是否需一年/多年」 | A | 11 §2.1、05 §5、06 E8–E9 |
| S1-030 | G1 数据来源与映射清单：现有 GSheet/本地成本文件/权威映射/缺口/脱敏 | `13-g1-data-sources.md` | C | 2026-10-20 | 业务导出仅兜底；不入 git | A | 13 |
| S1-031 | PR #303：`EN_API/query_customer_items_suffix.py` + `erpnext_bi/` 客户物料后缀查询工具 | PR #303 `40309079`（已合并） | C | 2026-10-20 | ref_code 子表查询；生产只读需授权 | A | 13 §1.3/§2 |
| S1-032 | 本地 2026-04..09 订单成本文件存在；2026-09 三角 3971 行，CENTRADE 1631/DANEEY 1590，有扣 3280/无扣 511 | `D:/Work/王忠于/成本核算/` 只读核对 | C | 2026-10-20 | 处理结果，不是原始凭证 | A | 13 §1.1/§1.2 |
| S1-033 | 通途SKU↔EN 权威映射：ref_code/importBOMCostList，直连 99.9%；前缀过滤/解析键有坑 | `docs/solutions/integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`（10-17） | C | 2026-10-17 | 「直连优先、旧键兜底」 | A | 13 §2 |
| S1-034 | 通途库存快照：`stock_alert`（PR #298）每日任务 `FZH-StockAlert-daily`；`erp2_stocks_stocksquery` 按仓分页 | `stock_alert/client.py`、`stock_alert/scripts/install_stock_alert_schedule.ps1` | C | 2026-10-20 | pageSize≤100、5 次/分钟 | A | 13 §1/§3 |
| S1-035 | EN 单据只读查询入口：`EN_API/item_shipment_status.py`、#291 `fulfillment_query.py`、`erpnext/scripts/fetch.py` | 代码/文档 | C | 2026-10-20 | SO→PP→WO→JC→DN | A | 13 §1 |
| S1-036 | 库存历史不可得：通途只给当前量；stock_alert 只写低库存行；web_automation stock export 可定时但本机无历史输出；仅有 20260514/20260807 稀疏文件 | 代码/本机核对 | C | 2026-10-20 | 无连续历史归档；G1 不需要历史库存 | A | 05 §2/§4.4、11 §2.1、13 §1.1 |
| S1-037 | 本地 EN BOM 成本表含 `产品编号`+`客户物料号`；EN Tongtool Cost Review 含 `Tongtool SKU`+`ERPNext物料号` | `en_bom_cost_list/EN产品BOM成本列表_20260821_1501.xlsx`、`en_tongtool_cost_review/...` | C | 2026-10-20 | 可直接做 G1 映射，无需 EN API | A | 13 §1.4/§2 |
| S1-038 | PB 只覆盖约 30 个涤麻三角 SKU；仓从 Daneey 到 Centrade 有切换；断货记录只是部分样本 | 用户 2026-10-20 说明 | C | 2026-10-20 | 不能当全 family 真值；仓库切换≠断货 | A | 05 §4.4、13 §3、06 B4 |
| S1-039 | `EN产品BOM成本列表20261016.xlsx`：3,700 行，KS0001/KS0248 1,739 行；列 `产品编号`+`客户物料号` | `D:/Work/王忠于/成本核算/` 只读核对 | C | 2026-10-20 | G1 映射首选 | A | 13 §1.4/§2、11 §2.2 |
| S1-040 | EN 测试环境没有真实 SO/PP/WO/JC/SE/DN；G1 必须用生产 API 只读 | 用户 2026-10-20 说明 | C | 2026-10-20 | 不写生产 | A | 13 §1、11 §2.2 |
| S1-041 | G1a 两仓完成品映射覆盖 99.18% 行/98.84% 件；0 歧义；未匹配 155 行/224 件 | `experiments/g1_contract/results.md` | C | 2026-10-20 | BOM 20261016：3,700 行/1,739 family 行 | A | G1a、05 §5 |
| S1-042 | 763 全仓 vs 155 两仓；155 中 31 行尾缀（30 Cover/1 out）、124 行 P2 非 family；真 family 缺口 0 | `experiments/g1_contract/out/missing_analysis.json` | C | 2026-10-20 | P1/P2 足够，Colab 4.2 未介入 | A | G1a §5 |
| S1-043 | BOM 表 KS0001/KS0248 1,739 行全部 `绍兴发货方式=皮壳`；base 1,200 / Cover 287 / out 2 / 空 142 / 删除 108 | `EN产品BOM成本列表20261016.xlsx` 只读核对 | C | 2026-10-20 | base 不是成品；皮壳口径待确认 | A | mapping_process |
| S1-044 | 公司架构：绍兴生产皮壳/内胆/半成品 → USNJ(CENTRADE)、USTX(DANEEY)、波兰分公司填充/压缩/包装/发货；最终销售多数成品 | `docs/company-context.md:14-29、27-29` | C | 2026-10-20 | 三角靠枕类只发皮壳；成品销售 1:1 消耗皮壳 | A | mapping_process §0、05/11/13 |
| S1-045 | WayfairCG-Cranbury 是下游 3PL，family 销售 1,162 件/6个月；其他 3PL 无 family 销售；海绵 `-Foam` 另列 | 本地订单 family 精确匹配 + 用户说明 | C | 2026-10-20 | 3PL 销售计入需求，转移不重复计 | A | mapping_process §4.1 |
| S1-046 | WayfairCG 库存以 Wayfair 后台手工导出为准；Tongtool 调拨只算发出量；赛狐平台仓 API 无 Wayfair | 用户 2026-10-20 说明 + `SELLFOX_API/docs/api-reference/多平台/平台仓/` 实查 | C | 2026-10-20 | 只有 Temu/Mercado/Walmart WFS，无 Wayfair | A | 13 §1.5、mapping_process §4.2 |
| S1-047 | 产能/交期不确定；美中 2026-06/07/08 新运营入职、第二个月才下单、首批刚回货，历史不可参考；美东稳定 2 人 | WX 2026-10-20 反馈 | C | 2026-10-20 | 美东可回测，美中需 cohort/ramp；交期用区间 | A | 05 §5/§7、08 §5、06 A12 |
| S1-048 | 订单文件 45,129 行/48,346 件无负数；退货仓 family 164/165 正数出库；补发 66/72；未匹配 759/925 pending | 本地 2026-04..09 订单只读核对 | C | 2026-10-20 | 33,719 是出库消耗毛量（含补发），不是净需求 | A | mapping_process §3 |
| S1-049 | 补发/换货是出库消耗，补货必须计入；M 后缀不是唯一判据 | 用户 2026-10-20 口径 + 本地订单 Mxxx 快速核对 | C | 2026-10-20 | family Mxxx 115/124（是64/否51）；全量 286/333（是172/否114） | A | mapping_process §3.1 |
| S1-050 | 三角退货率暂按 5% 作未来需求情景；订单文件无退货行；已回库退货不得二次冲减 | 用户 2026-10-20 口径 + Codex #301 `852d7791` 审核要求 | C | 2026-10-20 | 「比较低 可能先按5%」「退货已计入库存时不得再次冲减」 | B | mapping_process §3.2、06 B29 |
| S1-051 | WayfairCG 供货归属不固定，可能按 SKU 分流；赛狐调拨单可查发货仓/收货仓/SKU/数量/状态/时间 | 用户 2026-10-20 猜测 + `SELLFOX_API/docs/api-reference/仓库/调拨单/调拨单列表.md` | C | 2026-10-20 | `warehouseId`/`targetWarehouseId`/`commoditySku`/`goods`/`status` | A | mapping_process §4.1.1、08 §2.3 |
| S1-052 | Codex #301 `852d7791`：C26–C35 35/35；接受 G1b 带假设启动；要求退货不二次冲减、调拨≠实收、美中 cohort 修正 | Codex #301 `852d7791` | C | 2026-10-20 | 「可以推进G1b，不必再互改综述」 | A | codex-sync §0/§7、g1b_results §5 |
| S1-053 | G1b 库存快照：CENTRADE 478 SKU（可用 9,877 / 在途 4,504）；DANEEY 337 SKU（8,492 / 5,071）；旧皮壳仓当前无独立仓 | 通途 `erp2_stocks_stocksquery` 只读 + 仓库列表 | C | 2026-10-20 | 30 次请求 0 错误；覆盖 5.86 / 5.48 个月 | A | g1b_results §2–§3 |
| S1-054 | EN 单据试点：26 SO / 3,220 订单 / 2,084 已发 / 1,036 未发；死单 421、在产 622；SO 行用 `PK#` 包装码 | `EN_API/item_shipment_status.py` 生产只读 | C | 2026-10-20 | `PK#KS0001-XMMBS-194-HEMPNATURAL`；555 JC | A | g1b_pilot、g1b_results §4 |
| S1-055 | Codex `d9a11557` 判首版未通过 G1 契约验收，列 G1B01–09（缺口零值、坏输入、分页、重复、JC 跨工序、DN 行键、7 件差、歧义、仓池证据） | Codex #301 `review-g1b-first.md` | C | 2026-10-20 | 「首版抽取有进展，但尚未通过 G1 契约验收」 | A | g1b_review_response |
| S1-056 | 试点未发 1,036 = 死单 421 + 在产 622 + 无计划 9 + 超发 -16；421+622 与 1,036 的差 7 = +9-16 | 本地 `g1b_en_fixed3.json` | C | 2026-10-20 | `difference=0` | A | g1b_pilot §1、g1b_results §4 |
| S1-057 | 浏览器 `tongtu.stock.export` 实际产出成本/头程模板（SKU/安全库存/头程费用），不是 available/intransit 库存数量 | `web_automation/output/*_通途导入_头程运费_其他费用.xlsx` + `tongtu_auto_export.py` | C | 2026-10-20 | 5 列；3 个仓手工测试 | A | 14-daily-inventory-backup §1 |
| S1-058 | 每日 API 库存备份脚本 `stock_daily_backup.py` 冒烟通过；任务 `FZH-TongtuStockApiDaily` 每日 05:17 | 本地运行 + `Get-ScheduledTask` | C | 2026-10-20 | 2 页/200 行/complete=false（max-pages 截断） | A | 14-daily-inventory-backup §4 |
| S1-059 | 旧皮壳仓 2026-05/08 有 896/904 SKU、余额 21,226/16,990；2026-10 当前列表不存在；无 ID/改名/迁移凭证 → unverified | 历史结存 xlsx + 通途仓库列表 | C | 2026-10-20 | `g1b_warehouse_evidence.md` | A | G1B09 |

## 未找到项（N-###）

> 每条必须写：检索词、检索库/系统、日期、检索范围、为什么算「未找到」。
> 结论写「在上述范围内未发现」，不写「不存在」。

| ID | 目标 | 检索词 | 范围 | 日期 | 结论 |
|---|---|---|---|---|---|
| N-001 | `demand_forecast/` 代码子项目 | `demand_forecast`、`forecast` | 全部分支对象表 + `git log --all --name-only` | 2026-10-20 | 在上述范围内未发现目录；只有阶段 A 文档（PR #304） |
| N-002 | 需求预测 / 安全库存 / 净需求 / 排产 / 审批引擎代码 | 上述关键词 | main 全模块 + 全分支 | 2026-10-20 | 未发现实现；只有方法论文档 |
| N-003 | 头程结构化 ETA（离厂/到港/清关/入仓） | ETA、离厂、到港、清关 | 钉钉两张表 + 仓库代码 | 2026-10-20 | 未发现结构化字段；只有人工日期 |
| N-004 | Notion 页面注册表 | notion registry | 仓库文档 + Notion 检索 | 2026-10-20 | 未发现集中注册表；页面分散 |
| N-005 | 第二套业务网页 Agent demo（仓库内） | `ops_assistant`、`web agent` | 全部分支 | 2026-10-20 | 仓库内只有 PR #288；另在 `D:/Work/web-ai-assistant-review-20261012` |

## S2/S3/S4 汇总（从各线证据表机械合并）

> 以下行由脚本从 `02/03/04` 的证据表原样抽取；各文件内表格仍为权威版本。

| ID | 主张 | 来源 | 类型 | 日期 | 原文摘录 | 强度 |
|---|---|---|---|---|---|---|
| S2-001 | S&OP 是月度五阶段循环，最后到 CEO 批准 | https://rsmus.com/insights/services/business-strategy-operations/what-is-sales-and-operations-planning.html | I | 2026-10-20 访问 | "S&OP is generally broken down into a monthly cycle with five phases"；"presented to the CEO for approval" | B |
| S2-002 | 巴西 16 家纺织企业 S&OP 成熟度平均仍处初始「赌博」级，实施有挑战 | https://doi.org/10.1590/0103-6513.20230084 | P | 2024 | "the initial gamble level ... is, on average, 30%"；"it is challenging to implement, requiring attention in the initial stage" | A |
| S2-003 | DDMRP 通过解耦点与库存缓冲监控补货，含五个组件 | https://raw.githubusercontent.com/MicrosoftDocs/dynamics-365-unified-operations-public/main/articles/supply-chain/master-planning/planning-optimization/ddmrp-overview.md | C | 2026-10-20 访问 | "DDMRP is a planning methodology that's based on the decoupling of supply and demand."；"Decoupling points are specific points ... where you put an inventory buffer" | B/C |
| S2-004 | DDMRP 综述：有可用性/交期/库存改进潜力，但缓冲数学、静态假设与实证有限 | https://doi.org/10.1051/epjconf/202638306008 | P | 2026 | 标题 "Demand-Driven Material Requirements Planning in Downstream Supply Chains: A comprehensive review"；摘要（Crossref）指出上述局限 | A/B |
| S2-005 | 多级库存可用保证服务时间 + 基库存策略在树状网络分配安全库存 | https://doi.org/10.1287/msom.2.1.68.23267 | P | 2000 | 摘要：periodic-review base-stock policies、bounded demand、guaranteed service times、Eastman Kodak 应用 | A |
| S2-006 | 池化 + 保证服务模型在 Coppel 降安全库存 17.01%、物流成本 13.91% | https://dspace.mit.edu/bitstream/handle/1721.1/126496/scm2020-sharma-evaluating-inventory-risk-pooling-strategy-for-multi-echelon-distribution-network-capstone.pdf?sequence=1&isAllowed=y | I | 2020 | 安全库存 461K→394K 美元（−17.01%）；年物流成本 −13.91% | B |
| S2-007 | APS 比 MRP 更依赖数据准确性，输入退化会导致计划失信与流程失败 | http://sajie.journals.ac.za/pub/article/download/234/219 | P | 2004 | "Advanced Planning is even more reliant on data accuracy than Requirements Planning"；"credibility of computer generated supply plans"；"failure of the whole Advanced Planning business process" | B |
| S2-008 | 控制塔含人/流程/数据/组织，能力覆盖可视、信号、预测、异常、协同、学习 | https://www.supplychaindive.com/news/gartner-what-supply-chain-managers-should-know-about-control-towers/574098/ | I | 2019 | "a concept combining five elements — people, process, data and organization"；"Do exception management and scenario modeling" | B |
| S2-009 | 更多可见性可能拖慢组织；异常必须路由给具名 owner 并有升级路径 | https://www.thescxchange.com/why-more-supply-chain-visibility-can-slow-you-down | I | 2026-10-20 访问 | "greater visibility can actually slow them down"；"A red light without an owner is simply better information about a problem that is still waiting to be solved." | B |
| S2-010 | WAPE 仅在平稳时一致，不宜用于趋势/季节/异方差；间歇需求建议 MASE | https://857.robjhyndman.com/hyndsight/wape.html | I | 2025 | "only consistent when the time series is stationary"；"should not be used with data that has trends, or seasonality, or heteroscedasticity"；"a better choice than the WAPE" | B |
| S2-011 | 滚动原点回测可生成多 horizon 误差矩阵 | https://pkg.robjhyndman.com/forecast/reference/tsCV.html | I | 2026-10-20 访问 | "rolling forecast origin"；支持扩展/滚动窗口；输出各预测步长的误差矩阵 | B |
| S2-012 | FVA 评估预测流程每一步/每个参与者的增量价值，以 naive 为基准，可正可负 | https://www.sas.com/content/dam/SAS/en_us/doc/whitepaper1/forecast-value-added-analysis-106186.pdf | I | 2026-10-20 访问 | "FVA is a metric for evaluating the performance of each step and each participant"；"It expresses the results of doing something versus having done nothing."；"FVA can be either positive or negative" | B |
| S2-013 | 手工 override 的价值需要结构化评估，否则会无理由累积并降低精度 | https://optilon.com/resource/sharper-forecast-overrides-for-higher-planning-accuracy/ | I | 2026-10-20 访问 | "The challenge is knowing when overrides truly add value — and when they quietly reduce accuracy."；"Overrides accumulate without clear ownership or rationale" | C |
| S2-014 | Tobit 指数平滑可在已知/可变删失水平下减少失销与过剩，避免需求估计螺旋下行 | https://arxiv.org/abs/2409.05412 | P | 2024-09 | "Tobit Exponential Smoothing with time aggregation constraints"；"known and potentially variable censoring levels over time"；"avoiding spiral-down effects in demand estimation" | B |
| S2-015 | 资金约束报童：预算约束下用尽资金订货量可能不变；融资成本对波动敏感 | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0329561 | P | 2025 | "This formulation embodies the critical fractile solution"；"Under bank financing, financing costs exhibit a positive sensitivity to market volatility." | A |
| S2-016 | 厂商称春节停工至少一个月，建议提前三个月下单、备六周安全库存 | https://www.spscommerce.com/community/articles/how-to-plan-production-around-chinese-new-year | V | 2026-10-20 访问 | "typically has workers out of the factories for a minimum of one month"；"place their orders a minimum of three months before the holiday"；"six-week minimum safety stock" | C |
| S2-017 | 领星补货公式含时效/安全天数/发货频率与多仓聚合 | https://www.lingxing.com/help/article/allPlatformReplenishmentAdvice | V | 2026-10-20 访问 | "建议发货量=（本地仓至海外仓时效+安全天数+发货频率）*日销量（动态）－（海外仓在途+海外仓可用+...）"；"可设置聚合仓库" | C |
| S2-018 | 积加目标库存天数含审批/交期/质检/物流/入库/调拨/安全库存/补货周期并减缺货天数；支持剔除断货 | https://help.jijiaerp.com/docs/eeE2AHAR | V | 2026-10-20 访问 | "目标库存天数 = 备货计划与审批时间 + 采购交期 + ... + 补货周期 - 缺货天数"；"历史销量是否剔除断货数据"；"日均销量= 过去N天的总销量 /（N-断货天数）" | C |
| S2-019 | 易仓强调多仓库存整合、备货补货、海运轨迹、订柜与工厂交货 | https://www.eccang.com/news/2814 | V | 2026-10-20 访问 | "打通多仓库存数据，海运轨迹实时跟踪货柜运输，订柜计划及工厂交货管理"；"多仓库存整合与一体化看板" | C |
| S2-020 | 赛维时代 2024 年存货周转天数 81 天，同比增加 10 天 | https://stock.stockstar.com/JC2025042900027590.shtml | I | 2025-04-29 | "2024年公司存货周转天数为81天，同比2023年增加10天。" | A |
| S2-021 | 赛维时代 2024 年经营现金流净额 −4.685 亿元，同比 −185.25% | https://finance.sina.cn/2025-04-27/detail-ineurezq9805317.d.html?vt=4 | I | 2025-04-27 | "经营活动产生的现金流量净额为 - 468,535,009.96元，较上年同期减少185.25%"；"经营活动现金流出小计7,077,083,666.64元，增长90.20%." | A |
| S2-022 | 华凯易佰 2024 年存货规模较年初 +115.64%，仓储费用 +153.04% | https://m.21jingji.com/article/20250515/6bf9075e7e4671ede439f9ddd7006bf3.html | I | 2025-05-15 | "整体存货规模较年初增长115.64%"；"销售费用中仓储费用同比增长153.04%" | A/B |
| S2-023 | 新品冷启动因历史稀疏而困难，差预测导致过剩/断货/失败；可融合属性、参考轨迹、早期信号 | https://www.informs-sim.org/wsc25papers/doc107.pdf | P | 2025 | "Accurately forecasting the demand trajectories of newly launched products is a fundamental challenge due to sparse or nonexistent historical data."；"overstocks, stockouts, and high product failure rates" | A/B |
| S2-024 | 告警过载指告警速率超过复核能力 | https://zenodo.org/records/21111461/files/Anomaly_Understanding_Preprint.pdf?download=1 | I | 2025 | "Alert overload is the condition in which the rate of alerts exceeds the capacity to review them."（检索摘要，未逐字复核全文） | C |
| S3-001 | GIFT-Eval 覆盖 23 数据集、14.4 万序列、1.77 亿点 | https://arxiv.org/abs/2410.10393 | P/I | 2026-10-20 | "23 datasets over 144,000 time series and 177 million data points" | A |
| S3-002 | 移除 LLM 组件不降反升；预训练文本知识无优势 | https://arxiv.org/abs/2406.16964 | P/I | 2026-10-20 | "removing the language model ... does not degrade forecasting performance"; "pretrained LLMs do no better than models trained from scratch" | A |
| S3-003 | TimesFM 汇总第一但优势集中在高周转；间歇段最佳模型随指标变 | https://accesson.kr/jidb/v.17/3/89/59736 | P/I | 2026-10-20 | "TimesFM ranked first on pooled accuracy"; "this performance was concentrated among high-turnover products"; "in the intermittent segment ... the best model changed with the error metric" | A/B |
| S3-004 | 精度排名与服务水平排名负相关；Chronos-2 偏差校正 +14.5pp | https://arxiv.org/abs/2609.13840 | P/I | 2026-10-20 | "Forecast-accuracy rank and order-service rank are negatively correlated ... at -0.555"; "lifts ... from 77.5% to 92.0%" | A |
| S3-005 | M5 预测 42,840 条 Walmart 层级序列 | https://doi.org/10.1016/j.ijforecast.2021.11.013 | P/I | 2026-10-20 | "42,840 time series"；论文第 5 节结论 | A |
| S3-006 | M5 冠军均为纯 ML；仅约 12% 队伍跑赢全部基准，最多约 20% | https://forecasting-strategy.ch/2024/05/16/machine-learning-in-retail-forecasting-results-from-the-m5-competition/ | D | 2026-10-20 | "all of the winning submissions leveraged 'pure' ML models"; "Only c. 12% of the teams managed to outperform all benchmarks"; "up to c. 20%" | D |
| S3-007 | Chronos-Bolt 比原 Chronos 快至多 250×、省内存 20×；Base 205M | https://huggingface.co/amazon/chronos-bolt-base | V | 2026-10-20 | "up to 250 times faster and 20 times more memory-efficient"; "205M" | C |
| S3-008 | Chronos-2 120M、8192 上下文、A10G >300 序列/秒、Apache-2.0 | https://huggingface.co/amazon/chronos-2 | V | 2026-10-20 | "120M-parameter"; "Max. Context Length — 8192"; "over 300 time series forecasts per second on a single A10G GPU" | C |
| S3-009 | TimesFM 2.5 200M/16k，2.5 权重 Apache；3.0 权重非商业 | https://github.com/google-research/timesfm | V | 2026-10-20 | "uses 200M parameters, down from 500M"; "supports up to 16k context length"; 3.0 weights "restricted to non-commercial, non-production use" | C |
| S3-010 | TiRex 论文称 GIFT-Eval/Chronos-ZS SOTA；CC BY-NC-ND | https://arxiv.org/abs/2505.23719 | P/V | 2026-10-20 | "TiRex sets a new state of the art in zero-shot time series forecasting"; "CC BY-NC-ND 4.0" | B |
| S3-011 | Moirai 2.0-R-small（2025-08），仓库 Apache-2.0 | https://github.com/SalesforceAIResearch/uni2ts | V | 2026-10-20 | "Moirai-2.0-R-small (Aug 2025)"; "Apache-2.0 license" | C |
| S3-012 | fev-bench 100 任务、7 域、46 个带协变量任务 | https://arxiv.org/abs/2509.26468 | P/I | 2026-10-20 | "100 forecasting tasks across seven domains, including 46 with covariates" | A |
| S3-013 | Spider 2.0：632 个企业工作流；o1-preview 仅 21.3% | https://arxiv.org/abs/2411.07763 | P/I | 2026-10-20 | "632 real-world text-to-SQL workflow problems"; "only 21.3% of the tasks"; "91.2% on Spider 1.0 and 73.0% on BIRD" | A |
| S3-014 | τ-bench：gpt-4o 级代理 <50%；零售 pass^8 <25% | https://arxiv.org/abs/2406.12045 | P/I | 2026-10-20 | "succeed on <50% of the tasks"; "pass^8 <25% in retail" | A |
| S3-015 | 多 Agent 14 种失败模式，验证缺失/错误独立成类 | https://arxiv.org/abs/2503.13657 | P/I | 2026-10-20 | "14 unique failure modes"; "No or incomplete verification"; "Incorrect verification" | A |
| S3-016 | MCP 定义 Tools/Resources/Prompts；工具调用需用户同意 | https://modelcontextprotocol.io/specification/2025-11-25 | C | 2026-10-20 | "Tools ... actions with side effects"; "hosts must obtain explicit consent before invoking any tool" | A |
| S3-017 | 提示注入含间接注入；建议输出校验、最小权限、高影响人审 | https://genai.owasp.org/llmrisk/llm01-prompt-injection/ | C | 2026-10-20 | "Indirect prompt injections occur when an LLM accepts input from external sources"; "Require human approval for high-risk actions" | A |
| S3-018 | 过度代理=过度功能/权限/自主；高影响动作需人审 | https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ | C | 2026-10-20 | "excessive functionality"; "excessive permissions"; "excessive autonomy"; "require a human to approve high-impact actions" | A |
| S3-019 | AgentDojo：97 任务/629 安全用例；SOTA 模型仍大量失败 | https://arxiv.org/abs/2406.13352 | P/I | 2026-10-20 | "97 realistic tasks and 629 security test cases"; "State-of-the-art LLMs fail at many tasks" | A |
| S3-020 | 语义层把 Text-to-SQL 90.0→98.2、84.1→100；失败形态是报错而非错数 | https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026 | V | 2026-10-20 | "Text-to-SQL will cheerfully give you a wrong number"; "With the Semantic Layer, failure looks like an error message" | C |
| S3-021 | IEEE 配对实验：语义层 +15.0~18.3pp，p<0.05 | https://ieeexplore.ieee.org/document/11627365 | P/I | 2026-10-20 | 会议摘要：60 问题、4 模型、McNemar p<0.05（原文页未抓取） | B |
| S3-022 | OptiMUS 在易/难数据上提升 >20%/>30%；IndustryOR 仍低 | https://arxiv.org/abs/2402.10172 | P/I | 2026-10-20 | "more than 20%" easy; "more than 30%" hard | A |
| S3-023 | LLMOPT 平均求解准确率 +11.08%；自校正提升执行率/准确率 | https://arxiv.org/abs/2410.13213 | P/I | 2026-10-20 | "11.08% average solving accuracy improvement"; "model alignment and self-correction" | A |
| S3-024 | 判断性调整使利润 +4.92%；精度提升不等于利润提升 | https://doi.org/10.1287/mnsc.2024.06321 | P/I | 2026-10-20 | "raised average profitability by 4.92%"; "improved forecast accuracy does not necessarily translate into improved profit" | A |
| S3-025 | 便利店补货系统服务水平 +2.9%，下单时间 −36.5% | https://doi.org/10.1177/10591478251367129 | P/I | 2026-10-20 | 论文摘要（检索）：2.9% service-level improvement；36.5% time reduction | B |
| S3-026 | 独立新闻稿：下单时间 72→45 分钟，人处理例外 | https://www.eurekalert.org/news-releases/1141845 | I | 2026-10-20 | "36.5 percent less time"; "72 minutes a day"; "around 45 minutes after" | B |
| S3-027 | MIT 零售现场实验约 1,900 SKU；计划员存在采纳摩擦 | https://digitalsc.mit.edu/human-ai-collective-intelligence-in-demand-planning/ | I | 2026-10-20 | "approximately 1,900 stock-keeping units"; "reluctance among demand planners to rely on AI-driven algorithms" | B |
| S3-028 | 铁路案例：零样本并非总胜 AutoARIMA，微调后才胜 | https://aws.amazon.com/blogs/machine-learning/how-deutsche-bahn-redefines-forecasting-using-chronos-models-now-available-on-amazon-bedrock-marketplace/ | V | 2026-10-20 | "SMAPE 0.195 versus AutoETS 0.200 and AutoARIMA 0.202"; 第二场景 "0.197 ... versus 0.130"; 微调后 0.127 | C |
| S3-029 | 某全球咖啡连锁 AI 盘点工具约 9 个月后撤下，原因含识别错误 | https://fr.qz.com/starbucks-abandonne-loutil-dinventaire-ai-nomadgo-052226 | I/D | 2026-10-20 | "le comptage automatisé sera retiré"; 误认牛奶种类/漏项；Reuters 报道 | D |
| S3-030 | 自动化偏差综述：XAI 可能反向强化错误信任；人先机后/分歧升级有初步证据 | https://link.springer.com/article/10.1007/s00146-025-02422-7 | P/I | 2026-10-20 | 检索摘要：explainability can backfire；human-first 37.8%→68.0%（二手综述，D 级） | B/D |
| S3-031 | TimeGPT 自称首个时序基础模型；闭源 API，独立复现受限 | https://arxiv.org/abs/2310.03589 | V | 2026-10-20 | "first foundation model for time series"; "zero-shot inference excels" | C |
| S3-032 | MCP 安全：禁止 token passthrough；最小 scope；会话不作为认证 | https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices | C | 2026-10-20 | "Token passthrough ... explicitly forbidden"; "Minimal initial scope set" | A |
| S3-033 | Chronos-Bolt 可 CPU 推理；基准 1024 序列/512 上下文/64 horizon | https://aws.amazon.com/blogs/machine-learning/fast-and-accurate-zero-shot-forecasting-with-chronos-bolt-and-autogluon/ | V | 2026-10-20 | "can also be used on the CPU"; "1024 time series with a context length of 512 ... 64 steps" | C |
| S3-034 | 新品冷启动可用属性+参考轨迹/文本嵌入；原文数值未复核 | https://www.informs-sim.org/wsc25papers/doc107.pdf | P | 2026-10-20 | 检索摘要：CDLF 用静态属性+可比品轨迹+早期销量；PDF 未能解码，按 C 级 | C |
| S3-035 | 评论文本特征在多个单品类研究中提升销量预测；原文多不可复现 | https://onlinelibrary.wiley.com/doi/abs/10.1002/itl2.70158 | P | 2026-10-20 | 检索摘要：评论情感/主题/评分融合提升 RMSE/R²；原文 403，按 C/D 级 | D |
| S4-001 | Airflow 生产只支持 Linux；Windows 需 WSL2 或容器 | https://airflow.apache.org/docs/apache-airflow/stable/installation/prerequisites.html | C | 2026-10-20 访问 | “On Windows you can run it via WSL2 (Windows Subsystem for Linux 2) or via Linux Containers.” | A |
| S4-002 | Airflow 3.3.2，Apache-2.0，声明依赖 251 个 | https://github.com/apache/airflow | C | 2026-10-20 访问 | tag 3.3.2；`requires_dist` 251；`requires_python !=3.15,>=3.10` | A |
| S4-003 | Dagster 生产需 3 个常驻服务；默认 SQLite run storage | https://dagster.io/docs/deployment/oss/oss-deployment-architecture | C | 2026-10-20 访问 | “Dagster requires three long-running services”；“by default Dagster uses SqliteRunStorage” | A |
| S4-004 | Dagster 安装文档含 Windows 步骤，推荐 Python 3.13 | https://dagster.io/docs/getting-started/installation | C | 2026-10-20 访问 | “Python 3.13 is recommended.”；安装分 Mac/Windows/Linux | A |
| S4-005 | Prefect 可在 Windows PowerShell/CMD/conda 安装运行 | https://docs.prefect.io/v3/get-started/install | C | 2026-10-20 访问 | “You can install and run Prefect via Windows PowerShell, the Windows Command Prompt, or conda.” | A |
| S4-006 | Prefect 多机部署需 Postgres 14.9+；SQLite 不支持多机同步 | https://docs.prefect.io/v3/advanced/self-hosted | C | 2026-10-20 访问 | “SQLite does not support multi-server synchronization”；“PostgreSQL version 14.9 or higher is required for multi-server deployments.” | A |
| S4-007 | Prefect Cloud Starter $100/月 | https://www.prefect.io/pricing | V | 2026-10-20 访问 | “Starter: $100/mo” | C |
| S4-008 | Dagster+ Solo $10/月 + $0.040/credit；Starter $100/月 | https://dagster.io/pricing | V | 2026-10-20 访问 | “$10 per month” plus “$0.040/credit”；“$100 per month” plus “$0.035/credit” | C |
| S4-009 | SQLite 公有领域，无需许可证 | https://www.sqlite.org/copyright.html | C | 2026-10-20 访问 | “SQLite is in the public domain and does not require a license.” | A |
| S4-010 | SQLite 单写者；多写应选客户端/服务器数据库 | https://www.sqlite.org/whentouse.html | C | 2026-10-20 访问 | “SQLite supports an unlimited number of simultaneous readers, but it will only allow one writer at any instant in time.” | A |
| S4-011 | DuckDB 进程内、无独立服务、面向 OLAP | https://duckdb.org/why_duckdb | C | 2026-10-20 访问 | “embedded within a host process”；“There is no DBMS server software to install, update and maintain.” | A |
| S4-012 | DuckDB 单写进程；只读可多进程 | https://duckdb.org/docs/current/connect/concurrency.html | C | 2026-10-20 访问 | “one process can both read and write”；“multiple processes can read from the database, but no processes can write” | A |
| S4-013 | DuckDB 1.5.6，MIT，声明依赖 6 个，有 Windows wheel | https://pypi.org/project/duckdb/ | C | 2026-10-20 访问 | `duckdb-1.5.6-cp312-cp312-win_amd64.whl` | A |
| S4-014 | PostgreSQL 宽松许可证 | https://raw.githubusercontent.com/postgres/postgres/master/COPYRIGHT | C | 2026-10-20 访问 | “Permission to use, copy, modify, and distribute this software and its documentation for any purpose, without fee…” | A |
| S4-015 | dbt-core 1.12.6 / dbt-duckdb 1.11.0，均 Apache-2.0 | https://pypi.org/project/dbt-duckdb/ | C | 2026-10-20 访问 | 版本 1.12.6 / 1.11.0；License Apache-2.0 | A |
| S4-016 | dbt Cloud Starter $100/用户/月，含 5 个开发者席位 | https://www.getdbt.com/pricing | V | 2026-10-20 访问 | “$100 per user/month”；“Five developer seats” | C |
| S4-017 | Metabase 核心 AGPL，`enterprise/` 为商业许可 | https://raw.githubusercontent.com/metabase/metabase/master/LICENSE.txt | C | 2026-10-20 访问 | “Outside of the top-level ‘enterprise’ directory… licensed under the AGPL.” | A |
| S4-018 | Metabase 官方数据库列表含 SQLite，不含 DuckDB | https://www.metabase.com/docs/latest/databases/connecting | C | 2026-10-20 访问 | “The databases listed below have official drivers maintained by the Metabase team.”；列表含 SQLite | B |
| S4-019 | Metabase Cloud 不提供 SQLite | https://www.metabase.com/docs/latest/databases/connections/sqlite | C | 2026-10-20 访问 | “SQLite isn’t available for Metabase Cloud.” | A |
| S4-020 | Metabase JAR 需 Java 25（早版本不支持） | https://www.metabase.com/docs/latest/installation-and-operation/running-the-metabase-jar-file | C | 2026-10-20 访问 | “We recommend version 25 of JRE from Eclipse Temurin”；“Earlier Java versions aren’t supported.” | A |
| S4-021 | Metabase Cloud Starter $100/月、$1,080/年；Enterprise 起 $20k/年 | https://www.metabase.com/pricing/ | V | 2026-10-20 访问 | “$100 / month”；“$1,080 / year”；“Price starts at $20,000 / year” | C |
| S4-022 | Superset 6.1.0，Apache-2.0 | https://github.com/apache/superset | C | 2026-10-20 访问 | tag 6.1.0，published 2026-05-13；SPDX Apache-2.0 | A |
| S4-023 | Superset 通过 `duckdb-engine` 支持 DuckDB | https://superset.apache.org/user-docs/6.1.0/databases/supported/duckdb/ | C | 2026-10-20 访问 | “Required packages: duckdb-engine”；`duckdb:////path/to/duck.db` | A |
| S4-024 | Superset Docker 栈含 Postgres、Redis、Celery worker/beat | https://superset.apache.org/user-docs/6.0.0/installation/installation-methods/ | C | 2026-10-20 访问 | “the Superset application, a Postgres metadata DB, Redis cache, Celery worker and beat” | A |
| S4-025 | Grafana AGPL-3.0，定位 metrics/logs/traces | https://grafana.com/docs/grafana/latest/introduction/ | C | 2026-10-20 访问 | “querying, visualizing, and alerting on your metrics, logs, and traces” | A |
| S4-026 | StatsForecast 2.1.1，Apache-2.0，依赖 10 个，有 Windows wheel | https://pypi.org/project/statsforecast/ | C | 2026-10-20 访问 | 版本 2.1.1；`statsforecast-2.1.1-cp312-cp312-win_amd64.whl` | A |
| S4-027 | StatsForecast 提供 Croston/TSB/IMAPA/ADIDA 与滚动交叉验证 | https://nixtlaverse.nixtla.io/statsforecast/docs/models/tsb.html | C | 2026-10-20 访问 | 模型页含 `CrostonClassic`、`TSB`、`IMAPA`、`ADIDA`；核心 API `cross_validation(h, df, n_windows=1, step_size=1, …)` | A |
| S4-028 | HierarchicalForecast 提供 MinTrace/ERM/BottomUp/TopDown 调和 | https://nixtlaverse.nixtla.io/hierarchicalforecast/index.html | C | 2026-10-20 访问 | MinTrace “minimizes the total forecast variance”；ERM “minimizing an L1 regularized objective” | A |
| S4-029 | sktime 1.2.0，BSD-3，依赖 111 个 | https://pypi.org/project/sktime/ | C | 2026-10-20 访问 | `requires_dist` 111；`requires_python <3.15,>=3.10` | A |
| S4-030 | Darts 0.48.1，Apache-2.0，Python >=3.11，依赖 31 个 | https://pypi.org/project/darts/ | C | 2026-10-20 访问 | `requires_python >=3.11`；`requires_dist` 31 | A |
| S4-031 | GluonTS 0.17.0，Apache-2.0，依赖 93 个 | https://pypi.org/project/gluonts/ | C | 2026-10-20 访问 | `requires_dist` 93；`requires_python <3.15,>=3.10` | A |
| S4-032 | Prophet 1.5.0，MIT，依赖 17 个，有 Windows wheel | https://pypi.org/project/prophet/ | C | 2026-10-20 访问 | `prophet-1.5.0-py3-none-win_amd64.whl` | A |
| S4-033 | PyTorch Forecasting 1.8.0，MIT | https://github.com/sktime/pytorch-forecasting | C | 2026-10-20 访问 | tag v1.8.0；SPDX MIT | A |
| S4-034 | OR-Tools 9.15，Apache-2.0，依赖 6 个，有 Windows wheel | https://pypi.org/project/ortools/ | C | 2026-10-20 访问 | `ortools-9.15.6755-cp312-cp312-win_amd64.whl` | A |
| S4-035 | CP-SAT 适合整数规划与作业车间排产，支持 no-overlap | https://developers.google.com/optimization/scheduling/job_shop | C | 2026-10-20 访问 | “The CP-SAT solver is designed for integer programming problems and is generally faster than MPSolver.”；`model.add_no_overlap(...)` | A |
| S4-036 | Pyomo 6.10.1，BSD-3，依赖 36 个 | https://pypi.org/project/pyomo/ | C | 2026-10-20 访问 | `requires_dist` 36；LICENSE.md 为 BSD 文本 | A |
| S4-037 | CVXPY 1.9.3，Apache-2.0，Python >=3.11；凸优化为主，1.9 扩展 DNLP | https://www.cvxpy.org/ | C | 2026-10-20 访问 | “a Python-embedded modeling language for convex optimization problems”；1.9 支持 “quasiconvex programming, and nonlinear programming” | A |
| S4-038 | ERPNext GPL-3.0；Production Plan 做生产/物料计划；Reorder Level 自动建 MR | https://docs.frappe.io/erpnext/auto-creation-of-material-request | C | 2026-10-20 访问 | “When item’s stock reaches reorder level, Material Request is auto-created automatically.”；“comparing the projected quantity… with the reorder level” | A |
| S4-039 | Odoo Community LGPLv3；Enterprise $28.50–36/用户/月；MPS 手工且不能与 reordering rules 混用 | https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment.html | C | 2026-10-20 访问 | MPS “should absolutely not be used alongside reordering rules” | A |
| S4-040 | OpenBoxes EPL-1.0，定位仓库/库存管理，非计划优化 | https://github.com/openboxes/openboxes | C | 2026-10-20 访问 | “An accessible, open-source warehouse and inventory management system.”；v0.9.8-hotfix1 | A |
| S4-041 | Claude Agent SDK 复用 Claude Code agent loop；使用受 Commercial Terms 约束；仓库 MIT | https://code.claude.com/docs/en/agent-sdk/overview | C | 2026-10-20 访问 | “the same tools, agent loop, and context management that power Claude Code, programmable in Python and TypeScript”；“governed by Anthropic’s Commercial Terms of Service” | A |
| S4-042 | MCP 是开放标准，用于连接 AI 应用与外部系统 | https://modelcontextprotocol.io/docs/getting-started/intro | C | 2026-10-20 访问 | “MCP (Model Context Protocol) is an open-source standard for connecting AI applications to external systems.” | A |
| S4-043 | LangGraph 是低层有状态编排；推荐 LangSmith 做可观测 | https://docs.langchain.com/oss/python/langgraph/overview | C | 2026-10-20 访问 | “a low-level orchestration framework and runtime for building, managing, and deploying long-running, stateful agents”；“Use LangSmith to trace requests…” | A |
| S4-044 | PydanticAI 模型无关、OTel 原生、MCP 一等公民 | https://pydantic.dev/docs/ai/overview/ | C | 2026-10-20 访问 | “every model a string swap away”；“OpenTelemetry-native”；“Core ships fundamentals like MCP” | A |
| S4-045 | OpenAI Agents SDK tracing 默认开启，支持多种 MCP 传输 | https://openai.github.io/openai-agents-python/tracing/ | C | 2026-10-20 访问 | Tracing is “enabled by default.”；“understands multiple MCP transports” | A |
| S4-046 | Claude Code 可导出 OTel metrics/logs/traces | https://code.claude.com/docs/en/monitoring-usage | C | 2026-10-20 访问 | “exports metrics as time series data… events via the logs/events protocol, and optionally distributed traces via OpenTelemetry” | A |
| S4-047 | 清华 TUNA 提供 PyPI 镜像 | https://mirrors.tuna.tsinghua.edu.cn/help/pypi/ | C | 2026-10-20 访问 | `pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple some-package` | A |
| S4-048 | 阿里云 ACR 加速已停止同步最新镜像，建议 ACR 订阅或 GA | https://help.aliyun.com/zh/acr/user-guide/accelerate-the-pulls-of-docker-official-images | C | 2026-10-20 访问 | “ACR镜像加速目前已停止同步最新镜像” | A |
| S4-049 | uv 支持 `--offline` 与多读写者共享缓存 | https://docs.astral.sh/uv/concepts/cache/ | C | 2026-10-20 访问 | “With `--offline`, an affected entry is unavailable until it can be refreshed online.”；“uv’s cache supports multiple concurrent readers and writers” | A |
| S4-050 | 近 90 天关闭 issue 的创建→关闭天数中位数（维护信号代理） | https://api.github.com/search/issues?q=repo:PrefectHQ/prefect+is:issue+is:closed+closed:%3E=2026-07-20 | I | 2026-10-20 实测 | Prefect 1.7 / PydanticAI 1.7 / OpenAI Agents 1.0 / ERPNext 0.7 / OR-Tools 4.2 / Metabase 4.5 / Superset 3.9 / Airflow 3.2 / sktime 6.5 / Darts 24.3 / StatsForecast 48.5 / LangGraph 42.7 / Dagster 395 / OpenBoxes 400（天；受清 backlog 影响） | B |
| S4-051 | Claude Sonnet 5.5 公开 API 价 $2 输入 / $10 输出 每百万 token | https://claude.com/pricing | V | 2026-10-20 访问 | “Sonnet 5.5 — input $2; output $10” per million tokens | C |
