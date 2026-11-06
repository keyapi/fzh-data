---
okf: v0.1
type: Reference
title: 未合并 PR 资产盘点（45 个 open PR）
description: 只读盘点 keyapi/fzh-data 全部 open PR 的可借鉴规则/结论/资产，判定彼此重复与依赖，并逐条对照通途订单 canon；给出「整并入 / 部分摘取 / 仅留档 / 已被取代」的合并路线
date: 2026-11-06
module: cross-module
tags: [pr-audit, unmerged, tongtool, canon, supply-chain, settlement, infrastructure]
---

# 未合并 PR 资产盘点

> **状态：只读盘点（2026-11-06）。** 未合并/关闭/评论任何 PR，未改业务代码，未写 GS/EN。
> 基线：`origin/main` + 本 worktree 的 canon（PR #335，**尚未并入 main**）。
> 证据等级：PR body / 文件清单 / 关键 markdown 为 A 级；代理转述未回源者标「未证实」。

## 0. 摘要

| 项 | 数 | 说明 |
|---|---:|---|
| 盘点 PR | **45** | 用户清单 44 个 + 本盘点所在分支的 canon PR #335 |
| 可借鉴 | **41** | 整并入 24、部分摘取 16、规范已被吸收 1（#295） |
| 仅留档 / 已被取代 | **4** | #300、#301、#313 仅留档；#314 已被 #318 取代 |
| 与 canon 实质口径冲突 | **4 个 PR** | #280、#294、#312、#318（均集中在件数/FBA 判据） |
| PR 间硬冲突/重复 | **5 组** | 282↔287、283↔296、292↔321、298⊃309、299/305/288 计数互撞 |
| 与 main 确认 DIRTY | **10 个** | 205、290、295、296、300、301、306、326、329、334 |

**最该先并的 5 个 PR**

1. **#335** canon MVP（基线；MERGEABLE/CLEAN，其余盘点都依赖它）。
2. **#322** new-api 定价更正（生产按 flash 价给 pro 计费，约 4.5x 少收；改动 47 行）。
3. **#306** 供应链 A/B/C+D 复盘（rebase 后只合 5 篇 solution，收益高、风险低）。
4. **#280** 旧 Colab 档案（解 #294 的文档断链；TikTok/件数规则按 canon 改写后再摘）。
5. **#321** new-api 注册封堵 + OIDC redirect_uri 白名单（真实安全洞；**合并前必须先脱敏**文档中的旧 `SESSION_SECRET` 与员工姓名）。

> 备选：#327（NAS MCP 假重登，生产已修、仓库未合）、#327 所在的 D 簇修复类可随时插入。

## 1. 口径与方法

### 1.1 45 的构成

用户给定 44 个编号；`gh pr list --state open` 另有 **#335**（本 worktree 分支 `keyapi/tongtool-knowledge-canon` 的 canon PR）。本表把 #335 作为第 45 行，标为「基线」，不计入「可借鉴」分子。

### 1.2 只读边界

- 只调用 `gh pr list/view`、`gh api .../contents`、`git show/cat-file`；不 checkout、不 fetch 工作区、不评论。
- 大 PR（#300 477 文件、#318 108 文件、#329 319 文件）只看 body + 文件列表 + 3–6 个关键 md，未逐行读 diff。
- 所有「与 main 冲突」以 `origin/main` 为基线；所有「与 canon 冲突」以本 worktree 的 `docs/reference/tongtool-order-canon/` 为基线。

### 1.3 合并状态快照（2026-11-06）

- **MERGEABLE/CLEAN**：#286、#335。
- **CONFLICTING/DIRTY**：#205、#290、#295、#296、#300、#301、#306、#326、#329、#334。
- **BLOCKED（待评审）**：#336；**APPROVED**：#309。
- 其余返回 UNKNOWN（GitHub 未计算），合并时仍需 rebase；几乎所有改 `AGENTS.md` / `index.md` / `docs/solutions/index.md` 的 PR 都会与 main 的 114 篇计数冲突。

## 2. 总表（45 行）

> 「核心可借鉴」≤3 条；「冲突」只写实质口径，机械冲突统一见 §8.4；「落点」中的 canon 页均指 `docs/reference/tongtool-order-canon/`。

| 编号 | 主题 | 簇 | 类型 | 核心可借鉴内容 | 与 main/canon 冲突 | 与其它 PR 重复/冲突 | 建议 | 落点 |
|---|---|---|---|---|---|---|---|---|
| 280 | 旧 Colab 成本链现状档案（含 TikTok 拆单记录） | A | 研究 | ①Colab 合并键单键化 +「产品名含包裹」触发缺陷 ②TikTok 旧分支按 `(电话, sku_base)` 合并、正确性无断言 ③40 项自检脚本 | §5「件数≈部件行 max」与 canon 02 §6 / GRP-005 冲突；§1「-1/-2 不合并」需按 02 §4 收窄；canon 无 TikTok 条款 | #294 引用其 conventions 文档，单独合 294 会断链；与 294 件数实现冲突 | **部分摘取**（档案并入；规则按 canon 改写） | 模块 `docs/solutions/architecture-patterns/`；canon 01/02 TikTok 边界、02 §6 |
| 282 | 通途改单窗口≈90 天 | A | 规则（事实约束） | ①超期不可改，实测分界 7/10–7/14 ②云仓直发不需尾程 ③补发 `-M` + OSTK/Wayfair 视为需尾程 | 无计价冲突；90 天是平台约束，canon 05 未建；精确边界未证实 | 与 #287 同改 `monthly-tail-cost-pipeline.md`，287 未含本段 → 先 282 | **整并入** + 摘入 canon 05 | 模块 reference；canon `05-special-flows`（新建） |
| 287 | 待追尾程清单 + FedEx 账单 | A | 工具/研究 | ①缺口=`needs=1 且物流商运费=0` ②账单来源分类（平台付/补发例外/「7条」供应商/疑似官方 FedEx）③FedEx 无账单 API、官网反爬 | 不冲突，是 C13 证据；「疑似官方 FedEx」未证实 | 与 #282 同文件；与 #290/#294 互补 | **部分摘取**（工具并入；分类进 canon 05/07） | `tongtool_order_cost/scripts/`；canon 05 + 07 C13 |
| 290 | 订单历史 DuckDB + 同步失败沉淀 | A | 工具/研究 | ①`_update_order` 不回写 `warehouse_name` → 成本全 0（C1 根因链）②300s/526/任务重叠/SKU 精确匹配 ③GS 2023 起历史真源、EN 2025-07 起完整 | DuckDB 以 GS 为历史真源，与 canon 01 §1「EN 身份权威」需划边界（销售历史≠成本身份） | 与 #287/#294 互补；`branch-shipment-cover-rules` 支持 02 §8 | **部分摘取**（DuckDB 留 demand_forecast；同步失败进 07 C1/06） | `docs/solutions/integration-issues/`、`architecture-patterns/`；canon 07/06、01 §1 |
| 294 | 订单侧输入 + 月度盈利审计（只读） | A | 工具/研究 | ①`order_base` 只剥 1–2 位、`-M` 先剥 ②7 月 9579=9579、利润 diff 0 ③5 仓二次加工借 `2CJG-SX`≈238,278 | `count_pieces` 全填充件 `max+待复核` vs canon 02 §5/§6 阻断禁 max；仅 `-N` 无基行求和 vs `pieces_ambiguous`；docstring 称 TikTok 跨前缀合并，代码只做候选检测（**未证实**） | 已在本 worktree 基线、未入 main；#295 叠加其上；与 #280 断链 | **部分摘取**（先对齐 02 件数边界） | canon 02 §5/§6、07 C2/C6、06 |
| 295 | 美中 USTX 成本三方案 A/B1/B2（+B3） | A | 研究 | ①四列对比，7 月 B2 +264,912、B3 +191,453 ②B1 手填≠B2 重建，「差异即结论」③歧义维表键 fail-closed | canon 03 §4/§3.1 已吸收 B2 口径；无新冲突；头程/工资 167.8→105 未决 | 叠加 #294；内容已在基线 | **规范已被 03 吸收**；代码/方法并入基线 | canon 03/04（未建）/07 C2/C6 |
| 307 | 月度报税成本透视表 | A | 工具 | ①按表头名解析偏移 + 202607 基准硬校验 ②行=渠道账号→仓分类→SKU，值=数量+5 成本/运费 ③创建后逐组回读（2418/2065 组） | 无规则冲突；值列依赖 `*系数*数量`，C1/C2 变更会改透视 | 与 #294/#295 同源、无文件重叠 | **整并入** | 模块 scripts + docs |
| 296 | 钉钉 8/9 月账期收尾 | A | 研究/流程 | ①宽窗导出 `filter_export_by_period` 定稿 ②赛狐一行一笔转账、多结不改数 ③NAS 相邻桶交集=0、`OA_PERIOD_RE` 取起始月 | 无冲突；属账期侧，canon 01 §6 明确退货/结算不在通途订单 | 与 #283 同改 SKILL/HANDOFF/index；296 未含 283 → 先 283 | **整并入** | `docs/solutions/workflow-issues/` + dingtalk handoff/skill |
| 283 | 钉钉 API、Excel、赛狐三线核对 | A | 规则（对账约定） | ①钉钉 API→aflow Excel 按审批编号交叉→赛狐结算组 ②手填销售额/txt 打款/赛狐打款三数不互代 ③别名先对上再判漏交 | 无冲突；与 canon 01 §6 互补 | 与 #296 同文件，先 283 | **整并入** | `docs/solutions/conventions/` + skill |
| 300 | 供应链整合交接 + 独立调研 | B | 研究 | ①轻量决策链 + 薄 Agent ②生产量四口径 P1–P4 ③库存只认通途快照 | `control/` 47/477 已在 main（重复）；`out/*.json` 疑含业务数据（**未证实**） | #301 独立复审；#306 蒸馏；#313 承接 | **仅留档**（control/ 勿重复合入） | `docs/research/supply-chain/2026-10-20/claude/` |
| 301 | Codex 独立调研 + 对 300 复审 | B | 研究 | ①四类数据边界（需求单元/库存位置/已生产/时间可知性）②R-A EN-first 取舍 ③G1/G1b 复审发现 | 无 canon 冲突 | 与 #300 同题异构；review 是证据 | **仅留档** | `docs/plans/2026-10-20-codex-supply-chain-research/` |
| 306 | A/B/C + D 复盘 | B | 研究 | ①A 活跃全集→B 市场归属→C 库存 join + 六互斥桶 ②删失需求/冷启动/自动季节性 ③US owner 重述 84,343 件 / 181 产品 | 无订单口径冲突；AGENTS 旧计数会删 `supply-chain-visibility` 行 | 是 #329 的公开结论版；与 #300/#304 重叠但最凝练 | **整并入**（rebase，只保留 5 篇 solution） | `docs/solutions/architecture-patterns/`、`best-practices/` |
| 308 | 库存每日体检 | B | 工具 | ①双线对账 02:17/05:17，4,575 行四列 diff 0 ②「不要写第三个 fetcher」③freshness/completeness/行数基线 | 无 canon 冲突 | 与 #309/#310 同一快照源；与 #309 取数实现冲突 | **整并入**（rebase + 登记模块） | `scripts/inventory_daily_health.py` + AGENTS 模块表 |
| 309 | 低库存钉钉告警 | B | 工具 | ①EN `Tongtool Stock Latest` + 新鲜度闸门 ②`available<5` 排除 0 库存与仅在途 ③OpenAPI 兜底（MCP 524 起） | 无 canon 冲突；未登记 AGENTS 模块表 | 与 #308/#310 重复取数 | **整并入**（先统一取数链） | `stock_alert/` + 模块表 |
| 310 | 库存历史落库调研 | B | 研究 | ①现势→EN 只读 DocType，日历史→EN 本地盘 ②四桶语义：实物=可用+待发 ③快照时点 05:17/波兰 12:00/美国 17:30 | 无 canon 冲突；「EN 落盘」与 `stock_sync.py` 部分重叠（**未证实**） | 与 #308/#309 重复；Wayfair 篇与 #334 重复 | **部分摘取**（语义/时点/存储三篇） | `docs/solutions/architecture-patterns/` |
| 312 | W1 供应时间线原型（draft） | B | 工具（原型） | ①SC14 七阶段 ②unknown≠0、B_min/B_max ③SC04 DN 对账 4,279 行 diff 0 | **冲突**：`warehouse_map.json` 用仓名 `美国FBA仓`/`dn_customer` 判 `external_fba`，违反 C3/ADR-0001 | #318 是交付实现；与 #313/#314 构成交付链 | **部分摘取**（SC14 契约 + 结果），不整并 | 供 #318 契约；不进 canon |
| 313 | P0 交付形态（draft） | B | 研究 | ①A–E 五方案，C 混合推荐 ②硬约束：EN 读不到本地盘/05:17/5 req/min ③10 个待评审问题 | 无 canon 冲突 | 依赖 #312/#314；#314 被 #318 取代 → 选项需重评 | **仅留档** | `docs/research/.../control/reviews/` |
| 314 | EN 原生报表计划（draft） | B | 研究/计划 | ①EN 实测 Frappe 15.48/ERPNext 15.43.3、5,316 行、5,000 上限、BOM 48.57s ②JACK_QA Q09 六 must-fix、Q10 行级 JSON 违规 | 无 canon 冲突 | body 明写由 #318 接管；`supply_facts_export.py` 351 行被 #318 取代 | **已被取代**（关闭不合并） | 证据抽进 #318 文档 |
| 318 | 供应事实 v1（draft） | B | 工具 | ①`stage_balances` 互斥阶段 + milestones/availability_schedule/links/production_evidence ②无写回、无自动下单 ③196 测试、fixture 1,038 行 | **冲突**：`key_test__supply_facts.py:1736` 用 `custom_fba_sku`、`full_supply_facts.py:179` 用 `purpose` 判 `external_fba`，绕开 C3 | 接管 #314；应消费 #312 契约；20/108 与 main 重叠 | **整并入**（先修 FBA 判据 + rebase + 标「生产未部署」） | `supply_chain_visibility/` + 模块表 |
| 329 | D3b/D5/D6/S1/S2 策略脚本 | B | 研究（脚本集） | ①`not_released`：春节 257 行仅 33 过、新 71 行全 fail ②交期先验 55/30/14，区域修正 n≥30 ③`self_fulfilled_demand/`、`supply_netting/` 两模块 | 无订单口径冲突；AGENTS 旧计数 | 结论已被 #306 蒸馏；与 #300 E1 互修正 | **部分摘取**（结论页 + 两模块单独 PR） | `docs/solutions/` + 两模块 |
| 304 | 销量预估归档 | B | 研究/工具 | ①M1 run rate/M2 YoY/M3 趋势/M3b 季节均值 ②数据源 PB `Invoice to PB` 的 Qty Ordered by PO Date ③缺货低估/滞后/小样本 | 无 canon 冲突 | 与 #306 D 层、#329 D3b 重叠但更轻 | **部分摘取**（脚本留模块，其余留档） | `pb_reconciliation/` + `docs/research/` |
| 334 | Wayfair CG 入库在途 | B | 研究 | ①无 SKU 级 inbound API ②WSA 是 CG→客户出库，入库推断=Δon-hand+WSA ③unknown≠0、`confidence=inferred` | 无 canon 冲突 | 与 #310 Wayfair 篇重复；与 #320 是上下游 | **整并入**（两篇文档） | `docs/solutions/integration-issues/` + research |
| 336 | PB 旧 SKU 转换 | B | 工具 | ①旧→新 SKU 映射（灰/象牙）②深蓝未报价硬失败 ③177 测试、测试站已部署 | 无 canon 冲突 | 与 #304 同 `pb_*` 但不同域 | **整并入** | `pb_orders/arc_sku_migration.py` + docs |
| 284 | Amazon 非 V2 报税底稿 | C | 研究 | ①平台报送/会计/成本利润三层不得混算 ②FBA 只补产品成本+可证头程，不再叠加 FBM 尾程 ③原币按店铺×站点×币种汇总，未定汇率禁跨币种相加 | 无订单 canon 冲突；补充 C13 的 FBA 尾程口径（报税层），不改四列 | #286 的文档版；#286 基于本 PR | **整并入**（先 284 后 286） | `sellfox_settlement/docs/research/`；07 C13 证据 |
| 286 | 非 V2 技术验证十表 | C | 工具/研究 | ①十表 78,256 单元格可复跑 + 哈希校验 ②10 条禁止推断边界（父子单只加拆单/退款 other 不反推/当前 BOM≠历史成本/银行未到账）③账号匹配≠申报主体 | 与 canon 01 退货仓、02 拆单后缀约定一致；为 C1/C7 提供「141 组件仓库名为空」证据 | 基于 #284；与 284 文件重叠 | **整并入**（在 284 后） | `sellfox_settlement/` + `docs/solutions/tooling-decisions/` |
| 159 | quickOutbound 写回门禁 | C | 修复 | ①未设计 Outbox 前禁用 Web/CLI 直接发送 ②仅 approved 包 + `shipmentType=0` 可预览 ③401/429/409 视为 ambiguous，阻断重提 | 无 canon 冲突 | 无 | **整并入** | `sellfox_shipping/` |
| 205 | PB 促销 true-up handoff | C | 研究/文档 | ①item master ≠ open PO cost ②已开票 leave as billed ③四套源待深度研究 | 无 canon 冲突 | 重新合入 #201（main 上被 #204 revert）；与 PB 新模块文档可能重叠 | **部分摘取**（solutions + handoff，rebase 后） | `pb_promo_trueup/` + `docs/solutions/workflow-issues/` |
| 315 | PB 取消邮件闭环 + Notion MCP | C | 规则/工具 | ①CANCEL 四项交叉确认「从未发货」再回信 ②SMTP 后 IMAP APPEND ③Notion 直连 OAuth 兜底 | 无 canon 冲突 | 与 #297 仅机械文件重叠；body 明示「单独开 PR，不并入 #297」 | **整并入**（在 297 后） | `pb_orders/` + `docs/solutions/workflow-issues/` |
| 297 | PB 断货闭环 + JSON API v1 | C | 工具/规则 | ①人+Agent 共用服务层，API 不另起逻辑 ②幂等两层 + 订单号 `-N` 预留 ③断货五步闭环（含网页预检清单） | 无 canon 冲突 | 与 #315 同 PB；`pb_orders/data/*.json` 疑含真实 PO/SKU | **部分摘取/整并**（合并前脱敏 data JSON） | `pb_orders/` |
| 298 | 重量模板重尺导出 | C | 工具 | ①外箱→单个包装联动公式可编辑 ②`--env` 读 `.env` ③生产 1,228 条实测 | 无 canon 冲突 | **整段包含 #309 的 `stock_alert/` 文件**，重复 | **部分摘取**（只取 item_weight；stock_alert 让 309 先合） | `item_weight_size/` |
| 326 | 钉钉 OA 带附件发起 | C | 规则/工具 | ①三步上传 + `Storage.UploadInfo.Read`/`Storage.File.Write` ②OSS PUT 不能用 urllib 默认头 ③PB 月包单行/无合计/日 CSV 升序 | 无 canon 冲突；与 C9 钉钉账期边界一致 | 与 #283/#296 同 OA 模块文档；与 #297/#315 仅机械重叠 | **整并入**（排在 283/296 后） | `dingtalk_oa_approval/` + `docs/solutions/` |
| 330 | DWS 群采集周报 | C | 工具 | ①DWS 个人 OAuth 读历史（vs 机器人/应用/存档）②`complete/hasMore/failures` 硬门槛 ③原始数据仓外 + 水位重试 | 无 canon 冲突 | 与 #326 同钉钉、不同模块 | **整并入**（合并后主仓重跑 install） | `dingtalk/dingtalk_group_harvest/` |
| 288 | ops-assistant 受控渠道接入 POC | D | 工具（POC） | ①read-then-guard ②按动作而非关键词拦截 ③批准绑定摘要/时效/版本 | AGENTS 计数旧；无 canon | 与 #299/#305 抢 dev-exp 计数 | **部分摘取**（只取 1 篇 solution） | `docs/solutions/architecture-patterns/`；不采用 `ops_assistant_demo/` |
| 289 | Daneey 同步 300 秒超时 | D | 修复 | ①RQ default 队列 300s 硬上限 ②429 退避 30+60+90+120 正好耗尽 ③宽泛 except 吞 `JobTimeoutException` | AGENTS 计数旧；无 canon | 与 #292/#293/#305/#321 抢计数 | **整并入**（rebase） | `docs/solutions/integration-issues/` + EN_API handoff |
| 292 | new-api 敏感词 500 | D | 修复/规则 | ①屏蔽词整请求体子串匹配，命中后对话永久报废 ②两开关 AND，都要关 ③排查对话会自我触发 | 与 **#321 硬冲突**（同插「问题 9」）；AGENTS 旧计数 | 同文件同编号 | **整并入**，排 #321 后改「问题 11」 | `docs/solutions/integration-issues/` + handoff |
| 293 | OpenClash 出口事故 | D | 修复/研究 | ①覆写脚本写死旧组名 `Auto`，`find` 返回 nil 静默跳过 ②改脚本不改 live config ③通用线 url-test 自愈、AI 三层手动 select 无自愈 | `office-egress-fallback-chain.md` 在 main 已存在（增量更新）；AGENTS 旧计数 | 无重复 | **整并入** | 该 solutions + `us_openai_api_proxy/AGENT_HANDOFF.md` |
| 299 | DeepSeek 1017 Harness 选型 | D | 研究/工具 | ①DSH ≈0.37x 成本、缓存 95% vs 69%、慢约 2x ②Desktop 3P >30 天 transcript 已清理 ③父仓库 `.env` BOM+`source` 会打印密钥 | AGENTS 计数旧；无 canon | 与 #305 同系统不同问题；计数需合并重算 | **整并入** | `docs/research/` + `docs/solutions/tooling-decisions/` + handoff template |
| 305 | Claude Desktop rewind 修复 | D | 修复 | ①`parentUuid` 分支接错，消息未丢 ②只改 51 字节指针 ③活跃链判据与校验命令 | AGENTS 计数旧；无 canon | 与 #299 计数互撞 | **整并入**（与 #299 同批） | `docs/solutions/developer-experience/` |
| 320 | Wayfair API proxy | D | 工具（新模块） | ①固定 operation 白名单，不做任意透传；Bearer SHA-256 + 账号×operation 双授权 ②token `expires_in` 以响应为准、`supplierId` 是 parent、分页 1–100 ③共享 VPS 用 venv+systemd 不用 Docker | AGENTS 计数旧；新增模块行无冲突；与 #321/#322 改同 handoff | 与 #334 互补，先 320 | **整并入**（先于 334） | `wayfair-api-proxy/` + AGENTS 模块表 |
| 321 | new-api 注册封堵 + redirect_uri 白名单 | D | 修复（安全） | ①容器 `3000:3000` 绕过 nginx、`PasswordRegisterEnabled` 默认 true ②OIDC `redirect_uri` 不校验 → 接管员工账号 ③`SESSION_SECRET` 轮换只失效浏览器态 | 与 **#292 硬冲突**（同插「问题 9」）；公开仓库文档含旧 `SESSION_SECRET` 字面量/员工名，**合并前必须脱敏** | 与 #322 同主题不同问题；与 #320 offboarding 相邻 | **部分摘取/拆分**（安全修复优先；文档脱敏；`reset-user-quota.py` 独立） | `new-api-dingtalk-oidc/` + handoff |
| 322 | new-api 定价更正 | D | 修复（计费） | ①pro 未下线，仅旧名 `deepseek-v4-flash` 路由到 V4.1-Flash-1017 ②错常量让 pro 按 flash 价计费，约 4.5x 差价 ③移除 `PRO_EOL`/`PRO_ROUTES_TO`，恢复自有价目 | main 仍含 `PRO_EOL`（**确认未合入**）；仅 index/log 机械冲突 | 与 #321 同文件不同段 | **整并入**（本簇最高优先） | `new-api-deployment/deepseek_time_pricing.py` + handoff §四 |
| 327 | NAS MCP 假重登 | D | 修复 | ①`BaseApi.shared_session` 使 `relogin=True` 是假重登 ②重建前清空 + `retry_on_session` 覆盖 5 工具 ③30 分钟探活、连续 2 次失败才重启 | main 无 `shared_session` 清理（**确认未合入**）；index 机械冲突 | 与 NAS 可行性 research 可互链 | **整并入**（按 commit 拆读） | `nas_mcp/server.py` + docs/reference |
| 328 | 共享 Drive 文件夹读写 | D | 工具（新模块） | ①SA 读写，文件夹共享给 SA 邮箱即可 ②强制 IPv4 + 退避 + 回退 `content.googleapis.com` ③dry-run 默认、祖先链守卫、覆盖需 `--overwrite` | 无冲突；handoff 公开 Gmail/文件夹 ID（PII） | 与 `google_drive_permissions` 相邻；与 `tongtool_order_cost.gsheets` 边界**未证实** | **整并入**（先确认 PII 可公开） | `drive_folder_ops/` + permissions docs |
| 331 | 离职账号表权限回收 | D | 修复（记录） | ①台账标错「在职」导致清理脚本跳过 ②dry-run 只命中目标账号 34 处 ③清理脚本只重试 429/500/503 | 仅 index 机械冲突 | 与 #320 offboarding 同主题不同系统 | **整并入** | `google_drive_permissions/docs/log.md` |
| 335 | canon MVP（本盘点基线） | — | 规范 | ①01/02/03 canon + 07 冲突 + ADR-0001 ②`rules.yaml` 24 条 ③C1/C3 已有生产库只读证据 | 自身即权威基线 | #294/#295 内容已在其基线；A 簇多数 PR 为其证据 | **整并入**（基线 PR，最先合） | `docs/reference/tongtool-order-canon/` |

## 3. 簇 A 详述：通途订单 / 成本

### 3.1 逐 PR 证据

**#280 旧 Colab 成本链现状档案**
- body/文件：`docs/solutions/architecture-patterns/colab-cost-pipeline-current-state.md`、`colab-gsheet-inventory.md`、`en-cost-side-current-state.md`、`colab-cost-pipeline-data-flow.md`；自检脚本 `tongtool_order_cost/scripts/verify_colab_cost_claims.py`（40 项，FAIL 0）。
- 规则文档 `docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md`：§5 写「件数=配对套数（≈部件行 max）」——与 canon 02 §6 / GRP-005「Σ皮壳行、禁 max」直接冲突；§1 把 `-1/-2` 一律当「一单多件、不合并」，需按 canon 02 §4 的拆单证据收窄。
- TikTok：只在 cell 82–92 记录旧 Colab 分支——渠道 `tiktok/TiktokUS`，`assign_merge_group` 按 `(电话, sku_base)`、leader=`suffix==1`、正则 `([A-Za-z]+-\d{18})`；文档明确「合并产出的发货数量是否正确…范围内无断言」（**未证实**）。
- 判定：档案价值高；规则段必须按 canon 改写后再摘。**先合 280 可解 #294 的文档断链**。

**#282 通途改单窗口≈90 天**
- `tongtool_order_cost/docs/reference/monthly-tail-cost-pipeline.md`：发货日期 7/10 及更早改尾程失败、7/14 及以后成功，分界≈往前 90 天；只有两个观测点，**不能写成「恰好 90 天」**。
- 例外：云仓直发不需尾程；补发 `-M<数字>` + OSTK/Wayfair 视为需尾程（canon 01 §6 已记录，本 PR 补 EN app 侧证据）。
- 判定：平台事实约束，进 canon `05-special-flows`，不要写进 03 计价矩阵。

**#287 待追尾程清单 + FedEx 账单**
- `tongtool_order_cost/scripts/make_missing_tail_lists.py`：缺口口径 = `是否需要尾程=1 且 物流商运费=0`；202608 实测 541 行/527 包裹，待追 527（蜴国际 250/GLS 228/CENTRADE 36/「7条」5/疑似官方 FedEx 1/平台渠道补发 7）。
- `docs/reference/fedex-billing-online-download.md`：FedEx 无账单/发票下载 API，官网自动化被反爬系统性拦截，只能人工下载。
- 判定：工具与调研进模块；「平台付/补发例外/供应商」分类进 canon 05 并更新 07 C13。

**#290 DuckDB + 同步失败**
- `docs/solutions/integration-issues/en-tongtool-order-package-sync-failures.md` §⑤：`_update_order` 不回写 `warehouse_name` → 订单永久 null → 找不到成本配置 → 子表发货方式/绍兴成本/头程/皮壳成本全 0。这是 **C1 根因链的补充**，但不等于解决 Item 级拆单系数。
- §⑥：SKU 匹配是 `Item Customer Detail.ref_code` 精确等值，约 1/5 是「已登记未重匹配」、4/5 未登记。
- `docs/solutions/architecture-patterns/order-history-duckdb-store.md`：GS 月表 2023-01 起为历史真源、EN 2025-07 起基本完整；`orders_unified` EN 优先、GS 只补 EN 没有的。**销售历史库，不是成本身份权威**。
- 判定：DuckDB 留 demand_forecast；同步失败进 canon 07 C1 证据与 06。

**#294 订单侧输入 + 月度盈利审计**
- `order_side_input.py`：`order_base` 先剥 `-M<数字>` 再剥 `[_-]\d{1,2}$`，与 canon 01 §2 铁律一致；`OS-474530280` 不剥，有测试。
- 件数：有皮壳→Σ皮壳行；无皮壳→Σ成品行；**全是填充件→`max(quantity)` +「只发部件·待复核」**；仅 `-N` 无基行→求和。canon 02 §5/§6 规定载体不唯一/件数不唯一→阻断且禁 max；`split_merge._count_pieces` 对「只有 `-1/-2` 无基行」返回 `pieces_ambiguous`。**本簇唯一需要拍板的实质冲突**。
- 7 月实证：行守恒 9579=9579；`售价×汇率−订单总成本=订单利润` diff 0；成本全缺 27 行；5 仓二次加工借 `2CJG-SX`≈238,278。
- 基线状态：`order_side_input.py` 与 PR head 文件 hash 相同（`e34cf77fbe51`），内容已在 canon 分支基线，但 PR head 不是 HEAD 祖先，**未在 main**。

**#295 USTX 三方案**
- `ustx_cost_compare.py`：A 现状（美中走 `2CJG-SX`）/B1 测算表/B2 EN 式；7 月 B2 +264,912；B1 与 B2 在 57 个共有键上无一相等，所以「差异即结论」，不设「必须相等」闸门。
- canon 03 §4 已写「美中 USTX 目的地二次加工=美中包装成品 BOM `total_cost`」；§3.1 已写绍兴二次三档。B2 正是这套口径，**规范层已被吸收**。
- 未决：头程未纳入（半成品重量权重不在快照内）；B3 工资 167.8→105 只动 `operating_cost`，使 B2 +264,912 收窄到 +191,453。应进 canon 04（未建）或 07 开放项。

**#307 报税成本透视表**
- `gsheets_pivot.py`：行=渠道账号→发货仓按销售汇总分类→通途SKU；值=发货数量、`皮壳成本*系数*数量`、`绍兴二次加工成本*系数*数量`、`二次加工成本*系数*数量`、`头程运费*数量`、`运费`。
- 按表头名解析偏移并与 202607 基准硬校验；默认 dry-run，`--apply` 创建，`--verify-only` 对账；已创建 202608（2418 组）/202609（2065 组），与源表 pandas 分组零差异。
- 判定：报表工具，不定义口径；但 C1/C2 改系数会改透视值。

**#296 / #283 钉钉账期**
- `dingtalk-period-month-closeout-export-sellfox-nas.md`：宽窗导出先 `filter_export_by_period.py --period YYYY-MM`；赛狐同站一月多结会有多行，每行一笔 `transferAmount`，不要用「一行只能配一笔」否定数据；NAS 相邻月 `stem_key` 交集应为 0。
- `amazon-period-file-reconcile.md`：钉钉 OA API → aflow Excel 按 21 位审批编号交叉 → 赛狐 `groupPage` 结算结束日；手填销售额、txt `total-amount`、赛狐 `transferAmount` 是三个数，没读 txt 前不宣布金额正确。
- 判定：与 canon 01 §6「退货只在钉钉账期」互补；283 先于 296（同 skill/同 handoff）。

### 3.2 簇内结论

- 合并顺序：`280 → 282 → 287 → 290 → 294 → 295 → 307 → 283 → 296`。
- 三件需业务/规范拍板：TikTok 旧 Colab `(电话, sku_base)` 是否立规；纯填充单用 `max+待复核` 还是 canon 阻断；尾程来源分类是否替换现有三套优先级。

## 4. 簇 B 详述：供应链 / 库存 / 预测

### 4.1 研究/交付链

- **300 → 301 → 306 → 329**：#300 出方案 + 交接包，#301 独立复审并给另一条路线，二者同题异构、不可互相替代；#306 是公共沉淀（5 篇 solution），也是 #329 的公开结论版；#329 只剩过程脚本 + 两个新模块骨架。
- **312 → 313 → 314 → 318**：#314 body 明写「由 #318 接管，保持 draft，不合并」；#312 是 #318 的原型与 SC14 契约来源；#313 是交付形态决策的旁支。
- **300 的 `control/` 已整体在 main**（47/477 路径重叠），再合会重复。

### 4.2 库存三件套

- #308 体检、#309 告警、#310 历史落库认的是同一事实：EN `Tongtool Stock Latest` 05:17 批次、通途快照、四桶语义、unknown≠0。
- 口径不冲突；冲突在实现——#308 主张「不要写第三个 fetcher」，#309 自带 EN client + OpenAPI fallback，#310 又建议低库存并入同一次拉取。合并前应收敛到一条取数链。

### 4.3 与 canon 的冲突

- #312 `config/warehouse_map.json:84-89` 用仓名 `美国FBA仓`/`dn_customer` 判 `external_fba`。
- #318 `key_test__supply_facts.py:1736` 用 `soi.custom_fba_sku`、`full_supply_facts.py:179` 用 `purpose` 判 `external_fba`。
- 二者都绕开 canon C3 / ADR-0001 的 `warehouse_classification` 唯一判据与「未知映射阻断」。其余 12 个 PR 不碰订单全集/合并/后缀矩阵。

### 4.4 簇内结论

1. #306（rebase，只合 5 篇 solution）。
2. #304 / #334 / #336（互不相关，低风险；334 与 #320 文档层联动）。
3. #308 → #310（节选）→ #309：先体检、再语义/时点、最后告警，并统一取数。
4. #312（节选契约）→ #318（整并，先修 FBA 判据 + 标未部署）；#314 关闭；#313 留档。
5. #300/#301 留档；#329 只摘结论 + 两模块单独 PR。

## 5. 簇 C 详述：结算 / 报税 / 对账

### 5.1 逐 PR 证据

**#284 Amazon 非 V2 报税底稿**
- `sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md`：结论先行——先重建平台可能报送的收入/退款候选数，再谈费用和利润；不能把 65 个报表直接合成「中国公司收入」；商品成本与尾程属利润分析层，不等于平台报送收入层。
- 硬边界：EN BOM / Tongtool Cost Review 提供产品成本及仓前/头程；FBM 可接通途真实尾程或 EN 历史预估；**FBA 只补产品成本（+可证头程），Amazon `fba fees` 已含履约/仓储，不再叠加 FBM 尾程**；多币种按 `店铺 × marketplace × currency` 汇总，未定汇率禁跨币种相加。
- 与 canon：不冲突；为 07 C13（尾程优先级）补了「FBA 报税层不叠加内部尾程」的分支口径，但不改 03 的四列。

**#286 非 V2 技术验证十表**
- `docs/solutions/tooling-decisions/amazon-non-v2-tax-technical-validation.md`：10 条禁止推断——行数守恒（65 对 CSV/PDF、11,580 行）；退款 `other` 是合并桶、不能反推每笔；PDF 净额一致≠科目完整；账号匹配≠申报主体；当前 BOM≠8 月历史成本；父子单只加拆单（与 PR 280 的后缀约定相同）；尾程先用实际物流商费用；FBA 缺单先分购买日和 SKU；结算净额含期初/期末；银行实际到账仍缺输入。
- 可复跑：十表 78,256 单元格逐格一致；18 个产物 + 246 个输入哈希一致；`finance_rules.yaml` 在 ZJ 确认前必须 `pending_ZJ`。
- 与 canon：父子单/退货仓/拆单后缀与 01/02 一致；「141 组件仓库名称为空」是 C1/C7 的证据。
- 关系：**#286 基于 #284**，合并顺序 284 → 286。

**#159 quickOutbound 写回门禁**
- `sellfox_shipping/docs/specs/sellfox-inventory-mirror-and-quickoutbound-probe-2026-08-10.md`：未实现独立 Outbox endpoint 前，Web 与普通 CLI 都不发；预览仍要求本地 `approved`、有效未取消面单、真实追踪号、承运商、无 `UNKNOWN_BLOCKED` scope；真实 quickOutbound 只走 `PROBE_ONLY` 单包门禁。
- 405/429/409 提交结果视为 ambiguous，阻断重提；修复 `shipmentType=0`，集中 UNKNOWN 范围释放到审计过的 intent 命令。
- 判定：模块内修复，无 canon 交集，整并入。

**#205 PB 促销 true-up**
- `docs/solutions/workflow-issues/pb-2025-promo-cost-not-restored.md`、`pb_promo_trueup/`：Christine 2026-08-31 改 item master、Diane open PO 待改、扣货至冻结 PO；**item master ≠ open PO cost**；已开票 leave as billed；§9 四套源待深研。
- 关系：延续 #201（main 上被 #204 revert，本 PR 重新合入）。#205 当前 DIRTY。
- 判定：文档仍有价值；rebase 后部分摘取（solution + handoff），不要整模块原样带。

**#315 PB 取消邮件闭环**
- `docs/solutions/workflow-issues/pb-cancel-request-email-closed-loop.md`：按日期范围扫 IMAP 全部文件夹；Buyer SKU→我方 SKU；shipment/invoice/通途订单/Notion 四项交叉确认「从未发货」；回原线程保留 HTML 表格，SMTP 后 IMAP APPEND，汇总提醒邮件也要回，过程追加到 Notion PO 行。
- `docs/lessons/notion-mcp-setup.md`：CLI 直连 Notion MCP，复用 Claude-3p OAuth 缓存；Cloudflare UA、SSE、日期属性键名、真换行与回读验证。
- 关系：与 #297 只有 index/AGENTS/handoff 机械重叠，正文独立；body 明示「单独开 PR，不并入 #297」。

**#297 PB 断货闭环 + JSON API v1**
- `docs/solutions/architecture-patterns/pb-orders-json-api-human-agent.md`：网页与 API 共用 `web/jobs_service.py`；机器 `sk-` Key（库里只存 sha256 + 前缀）+ 人/Agent 公司 OIDC；`/api/` 不认 cookie、未带 token 返回 JSON 401；`Idempotency-Key` + 输入 SHA-256 两层幂等；通途订单号 `-N` 在 `BEGIN IMMEDIATE` 里预留；`/api/openapi.json` 带反代前缀；历史对齐用 `python -m web.backfill_order_numbers`。
- 断货五步闭环 + 网页预检断货清单（`app_settings.default_no_stock`）+ SPS 门户 IA/AKN 操作 + 补货量估算。
- 风险：PR 跟踪 `pb_orders/data/notion_pb_nostock_pos.json` 与 `notion_sku_map.json`，疑含真实 PO/SKU 映射；公开仓库合并前必须脱敏或移出。

**#298 重量模板重尺导出**
- `item_weight_size/export_weight_template_dims.py`：拉全部重量模板导出 xlsx；「重量模板数据」含联动校验列（OK/不符/不适用）；「重尺联动（可编辑）」复刻 Item 表单「长=外长、宽=外宽、高=外高÷内数量」；`--env prod|test` 从 `.env` 读凭证；生产 1,228 条实测。
- 重复：本分支**另含 #309 的全部 `stock_alert/` 文件**（18 个路径完全重合），属同一内容的两个 PR。
- 判定：只取 item_weight 部分；stock_alert 让 #309 先合，298 rebase 后删除重复段。

**#326 钉钉 OA 带附件发起**
- `docs/solutions/integration-issues/dingtalk-oa-create-receipt-with-attachments.md`：发起 `POST /v1.0/workflow/processInstances`；带附件三步（授权空间 → OSS PUT → commit）；除 `Workflow.Instance.Write` 外还要 `Storage.UploadInfo.Read` + `Storage.File.Write`，每开一次发布新版本；unionId 走旧 `topapi/v2/user/get`；OSS PUT 不能用 `urllib` 默认 `Content-Type`；重交前确认上一张已 `TERMINATED`。
- PB 月包惯例：表单只写各结日一行、不要月合计行；日 CSV 升序后挂 `PB invoice 合并 YYYYMM.csv`；日文件夹先收进 `YYYYMM/`。
- 关系：与 #283/#296 同 `dingtalk_oa_approval` 模块文档，建议 283 → 296 → 326。

**#330 DWS 群采集**
- `docs/solutions/tooling-decisions/dingtalk-group-harvest-dws-user-identity.md`：群机器人只能发不能读；企业内部应用 + Stream 读不到接入前历史；会话存档付费且要自行解密。DWS 以个人 OAuth 身份读历史消息/附件/文档。
- 四条硬规则：固定 `openConversationId`；完整性账本 `complete=true`、`hasMore=false`、`failures=[]` 否则不推进水位；按 `fileId` 单独下载、`resourceId` 去重；原始数据必须在公开仓库外。
- 注意：计划任务在 worktree 注册，合并后需在主仓库根目录重跑 `install_harvest_schedule.ps1`；DWS refresh token 约 30 天。

### 5.2 簇内结论

- `284 → 286`（堆叠）。
- `283 → 296 → 326`（同 OA 模块文档）。
- `297 → 315`（PB 主线先大后小）。
- #298 与 #309 二选一：先 309，298 去掉 stock_alert。
- #205 rebase 后部分摘取。
- #159、#330 独立整并入。

## 6. 簇 D 详述：基建 / 工具 / 其它

> 12 个 PR 全部不碰 `docs/reference/tongtool-order-canon/`，无需订单口径对照。共同风险是机械冲突：几乎都重生成 `index.md`，多个还手改 `AGENTS.md` 的「114 篇」计数。

### 6.1 逐 PR 要点

**#288 ops-assistant**：`ops_assistant_demo/README.md` 自述「银行科技子公司内部创新竞赛 POC」，业务/参数/工单/地址全部模拟，`status: poc-simulation`；9,857 行绝大多数是竞赛材料。只可借鉴 `docs/solutions/architecture-patterns/branch-param-desk-read-then-guard.md`（先读最新配置再提案、按动作而非关键词拦截、批准绑定记录摘要/时效/版本）。模块不进主仓；README 含演示口令 `demo2026`，摘取时不要带。

**#289 Daneey 同步 300s 超时**：`vilavi_pim/tasks/daneey_sync.py` 落 RQ default 队列（300s 硬上限）；429 退避 30+60+90+120 正好耗尽；宽泛 `except` 吞 `JobTimeoutException`；`_fetch` 半截数据 + 全量覆盖有清空物料组风险。目标文档在 main 不存在，属新增。

**#292 new-api 敏感词**：屏蔽词对整请求体纯子串匹配，命中后多轮对话永久报废；`CheckSensitiveEnabled` 与 `CheckSensitiveOnPromptEnabled` 取 AND，两个都要关；排查对话会自我触发。与 #321 同插「问题 9」，须串行。

**#293 OpenClash 出口事故**：覆写脚本写死旧订阅组名 `Auto`，`find` 返回 nil 静默跳过、成功日志照打；改脚本不改 live config（否则被订阅更新回滚）；通用线 url-test 自愈、AI 出口三层手动 select 无自愈。`office-egress-fallback-chain.md` 在 main 已存在，本 PR 是增量。

**#299 DeepSeek 1017 Harness**：DSH native ≈0.37x 成本、缓存 95% vs 69%、慢约 2x；Desktop 3P 131 个 >30 天会话 transcript 已清理；父仓库 `.env` BOM + `source` 会打印密钥。新增 research/tooling/dev-exp 文档在 main 均 MISSING。

**#305 Claude Desktop rewind**：`No message found with message.uuid` 是 `parentUuid` 分支接错，消息没丢；只改 51 字节指针。与 #299 同系统不同故障，计数需合并重算。

**#320 Wayfair API proxy**：完整实现（`main.py` 452 行、`wayfair_client.py` 466、`db.py` 723、11 个测试文件 48 项）；已部署美国 Vultr、公网 `https://wayfair-api.vilavi.cn`、EN 生产已拉 1,255 条快照——**能力已在生产运行，合并是补仓库状态**。与 #334 是上下游：334 说明网关能取到什么、取不到什么。

**#321 new-api 安全加固**：容器 `3000:3000` 绕过 nginx、`PasswordRegisterEnabled` 默认 true；OIDC `redirect_uri` 不校验 → 授权码换会话接管员工账号；`SESSION_SECRET` 轮换只失效浏览器登录态、不动 API token。**公开仓库文档含旧 `SESSION_SECRET` 字面量、攻击者 IP、员工姓名**，`check_secrets.py` 抓不到叙述式泄露；合并前必须替换占位符，`reset-user-quota.py` 建议拆出。

**#322 new-api 定价**：`deepseek_time_pricing.py` 仍含 `PRO_ROUTES_TO`/`PRO_EOL`，把 pro 改写成 flash 价；移除后恢复 pro 自有价目（高峰 0.632/3.0/0.033 类比值），body 估算约 4.5x 差价。改动 47+/36-，冲突面最小，**最先合**。

**#327 NAS MCP 假重登**：`nas_client(relogin=True)` 只丢弃模块级 `_nas` 并新建 `FileStation`，没有清 `BaseApi.shared_session`；修复清空 + `retry_on_session` 覆盖 search/folder_size/md5/archive/thumbnail；30 分钟探活、连续 2 次失败才重启，LoginError/ConnectionError 不重启。同 PR 还含 0.1.2 熔断、0.1.3 ping/并发上限/错误码翻译，标题未覆盖，评审需按 commit 拆读。

**#328 Drive 文件夹读写**：文件夹共享给 SA 邮箱即可读写、无需用户 OAuth；强制 IPv4 + 退避 + 回退 `content.googleapis.com` 解决 SSL EOF；dry-run 默认、祖先链守卫、覆盖需 `--overwrite`、备份到仓库外。handoff 公开属主 Gmail 与根文件夹 ID（PII），合并前确认可公开。

**#331 离职权限回收**：台账标错「在职」导致清理脚本跳过，先改台账再执行；dry-run 只命中目标账号 34 处；清理脚本 `api()` 只重试 429/500/503，不重试 SSL/连接异常——正好是 #328 已解决的坑。仅改 log + index，合规性最好。

### 6.2 簇内结论

1. **#322 → #321（先脱敏）→ #292（改问题 11）**：new-api 三件，串行合并。
2. **#331 → #289 → #293 → #305 → #299**：纯文档/低风险，逐篇 rebase；每合一篇重跑 `check_solutions_health.py --fix` + `update_index.py`。
3. **#327 → #328（先确认 PII）→ #320 → #334**：NAS/Drive/Wayfair 链。
4. **#288 只摘 1 篇 solution**，模块不进主仓。
5. 不建议把 #321 + #322 合成一个 PR：一个是访问控制（需安全评审），一个是计费常量（需财务口径），风险面与审批人不同。

## 7. 特别专题（canon 相关）

### 7.1 TikTok 跨前缀拆单与「手动建单」

- **规则已在 #280 的历史文档里**：`docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md` §5b「TikTok 拆单残留：靠『数字主体』跨前缀合并」（分支 `docs/colab-cost-current-state`，commit `72314dee`）。原文要点：
  - TikTok（对接通途）在通途里**不让拆单** ⇒ 拆包裹只能**手动新建销售平台/账号手工建单**补另一半；
  - 同一单号的数字主体散在不同前缀：`TTDaneeyUS-577247129175429589_2`（Foam）↔ `TTDaneeyGo-577247129175429589`（Cover）、`TTDaneeyUS-577250076459897074_2` ↔ `TTBNKC-577250076459897074`；
  - **合并键 = 平台单号数字主体（忽略前缀）**；实测 TiktokUS 渠道 59 个「无皮壳」组全部能按数字主体配到皮壳兄弟，按「同前缀剥 `_N`」配不上。
- **代码已有纯函数**：`tongtool_order_cost/tongtool_order_cost/order_side_input.py::tiktok_platform_body()`（`TT` 前缀 + 数字主体 ≥12 位；先剥 `_N`/`-M####`）。测试 `tests/test_order_side_input.py` 覆盖跨前缀同主体。
- **旧 Colab 实现**（cell 070/082/083/085/089/090/092）：`082` 按 SKU 的 `-N` 拆 `sku_base`；`083` 按 `(电话, sku_base)` 分组、`suffix==1` 当组长；`085` 组内运费求和、只留组长；`089` 从**订单备注**抽订单号再并一次；`090` groupby 求和；`092` concat 回去。依赖电话/备注，且文档自述「合并产出的发货数量是否正确…无断言」，**不完善**。
- **当前本地引擎状态（2026-11-06 实测）**：202608 有 **1 组**跨前缀拆单（`TTDaneeyGo-577511764556747219` Cover + `TTDaneeyUS-577511764556747219_2` Foam），202609 **0 组**。引擎**未合并**：两行各自按后缀计价；GS 模板行 `577511764556747219-1`（Colab 归一化单号）在 raw 中不存在 → `crosswalk_missing`、成本空白。
- **结论**：不是「未找到条款」，而是**规则有文档、有函数、缺实现**。**已于 2026-11-06 落地**：canon 02 §3.1 + `GRP-010` + `_pair_tiktok_cross_prefix` + phase36 body 兜底；202608 该单由空白→整件成本（皮壳 197.13 + 绍兴二次 595.74 + 二次 208.78），202609 无变化。

### 7.2 拆单系数

- canon C1：拆单系数在 OS 恒为 1，因为 `Tongtool Order Item` 没有 `warehouse_name`；字段实际在 `Item Customer Detail`。
- **#290 补了根因链**：`_update_order` 不回写订单头 `warehouse_name` → 订单永久 null → 找不到成本配置 → 子表发货方式/绍兴成本/头程/皮壳成本全 0。这与 C1 的「Item 级系数字段缺失」是**两个不同环节**，不能互相替代；两者都指向「订单同步链路拿不到仓库身份」。
- #307 的透视表值列直接乘 `系数`；C1 一旦修复/启用系数，202608/202609 的透视值会整体变化，需要重跑基线。

### 7.3 90 天改单窗口

- #282：通途侧改尾程/改单在发货日期往前约 90 天后不可改；实测 7/10 失败、7/14 成功，**只有两个观测点**。
- 性质：平台事实约束，不是计价规则。落 canon `05-special-flows` 的「运营时效约束」，并写明「≈90 天，实测分界 7/10–7/14，精确边界未证实」。
- 关联例外：云仓直发不需尾程；补发 `-M<数字>` + OSTK/Wayfair 视为需尾程（canon 01 §6 已有）。

### 7.4 订单历史 DuckDB

- #290：GS 月表 2023-01 起为历史真源，EN 2025-07 起基本完整；通途 API 可见性跟「最近更新时间」走，不能重建 2025-07 以前；`orders_unified` EN 优先、GS 只补 EN 没有的。
- 定位：**demand_forecast 的销售历史库，不是成本身份权威**。canon 01 §1 应补边界：「GS 可提供历史销售骨架，但订单身份/作废/`erp_item_code`/`shipping_method` 仍以 EN 为准」。
- 与 C1 的关系：DuckDB 能补历史销售，但不能补 `warehouse_name`；不要把「有历史订单」误当成「有历史仓库身份」。

### 7.5 供应事实 / 库存口径

- #318 的 `stage_balances` 是**供应阶段**（`on_hand`/`po_open`/`in_production`/`shipped_in_transit`/`received`/`partially_received`/`over_produced`/`unknown`），不是订单全集，不与 canon 01 冲突。
- 但 #312 与 #318 的 **FBA 身份判据**与 canon C3/ADR-0001 冲突：前者用仓名 `美国FBA仓`/`dn_customer`，后者用 `custom_fba_sku`/`purpose`。统一改为 `Tongtu Shipping Warehouse.warehouse_classification`，未知映射阻断。
- 库存三件套（#308/#309/#310）口径一致：EN `Tongtool Stock Latest` 05:17 批次、四桶语义「实物=可用+待发」、unknown≠0；冲突只在取数实现（三套 fetcher），合并前收敛。

### 7.6 尾程与报税边界

- canon C13 仍登记「尾程优先级三套」（OS / CR / SGP），未裁决。
- #287 提供账单来源分类（平台付/补发例外/供应商/疑似官方 FedEx），可作为 C13 的证据，但不是裁决。
- #284/#286 的「FBA 只补产品成本，Amazon `fba fees` 已含履约/仓储，不再叠加 FBM 尾程」是**报税/利润分析层**的边界，不改 canon 03 的四列，也不替代 C13 对订单尾程的裁决。

## 8. 冲突矩阵

### 8.1 与 canon 的实质口径冲突（4 处）

| PR | canon 位置 | 冲突内容 | 处理 |
|---|---|---|---|
| 280 | `02-grouping-and-merge.md` §6、`rules.yaml` GRP-005 | 规则文档写「件数≈部件行 max」 | 改写为「Σ皮壳行；成品载体=无尾号基行之和；不唯一→阻断」，不要原样带入 |
| 294 | `02` §5/§6、GRP-005 | `count_pieces` 全填充件取 `max + 待复核`；仅 `-N` 无基行求和 | 二选一：canon 增「纯填充单」专条，或 294 改为阻断；业务拍板 |
| 312 | `01` §5、ADR-0001 C3、`rules.yaml` FBA-001 | `warehouse_map.json` 用仓名判 `external_fba` | 改用 `warehouse_classification`；未知映射阻断 |
| 318 | 同上 | `custom_fba_sku` / `purpose` 判 `external_fba` | 改用 `warehouse_classification`；补「生产未部署」标注 |

### 8.2 与 canon 的边界/补充（不构成冲突，但需登记）

| PR | canon 位置 | 补充 | 动作 |
|---|---|---|---|
| 282 | `05-special-flows`（未建） | 90 天改单窗口、云仓直发不需尾程 | 新建 05，写「≈90 天」 |
| 287 | `07` C13、`05` | 尾程账单来源分类、FedEx 无账单 API | 进 05；C13 加证据链接 |
| 290 | `07` C1、`06`（未建） | `_update_order` 不回写 `warehouse_name` 的根因链 | 进 07 C1 证据；06 写实现映射 |
| 290 | `01` §1 | DuckDB/GS 历史销售边界 | 01 §1 加一句「GS 不定义订单身份」 |
| 286 | `01` §3/§6 | 父子单只加拆单、退货仓只是发货仓 | 作为 01 的证据，不改条文 |
| 284/286 | `07` C13 | FBA 报税层不叠加 FBM 尾程 | 07 C13 加分支持口径，不改 03 |
| 280 | `01`/`02` TikTok | 旧 Colab `(电话, sku_base)` 合并 | 不立规；若采纳，先补正确性断言 |
| 294 | `01`/`02` TikTok | docstring 称跨前缀合并，代码只做候选检测 | 修正 docstring，避免把候选当规则 |

### 8.3 PR 间依赖 / 重复 / 硬冲突

| 组 | 关系 | 说明 | 顺序 |
|---|---|---|---|
| 280 → 294 | 文档依赖 | 294 docstring 指向只在 280 分支的 conventions 文档 | 280 先 |
| 294 → 295 | 堆叠 | 295 body 明说叠加在 294 上 | 294 先 |
| 282 ↔ 287 | 同文件 | 都改 `monthly-tail-cost-pipeline.md`；287 未含 282 的 90 天段 | 282 先 |
| 283 → 296 | 同 skill/handoff | 296 未含 283 的三线文字 | 283 先 |
| 284 → 286 | 堆叠 | 286 body 明说基于 284 | 284 先 |
| 312 → 318 | 契约依赖 | 318 应消费 312 的 SC14 契约 | 312 先（节选） |
| 314 → 318 | 取代 | 314 body 明写由 318 接管 | 关闭 314 |
| 300/301 → 306 → 329 | 同题 | 300/301 过程，306 蒸馏结论，329 原始脚本 | 306 先；300/301 留档；329 节选 |
| 308 / 309 / 310 | 同数据源 | 三套 fetcher，口径一致 | 308 → 310（节选）→ 309 |
| 298 ⊃ 309 | 完全重复 | 298 含 309 的全部 `stock_alert/` 文件 | 309 先；298 删重复段 |
| 297 → 315 | 同模块 | 315 明示单独 PR，不并入 297 | 297 先 |
| 283/296 → 326 | 同 OA 模块 | 都改 `dingtalk_oa_approval` 文档 | 283 → 296 → 326 |
| 292 ↔ 321 | 同插入点 | 都在 handoff「问题 8」后插「问题 9」 | 321 先；292 改问题 11 |
| 321 ↔ 322 | 同文件不同段 | 一个访问控制、一个计费常量 | 322 先；321 后 |
| 299 / 305 / 288 | 计数互撞 | 都以 dev-exp 10 为基线各加 1–2 篇 | 合并后统一重算 |
| 320 → 334 | 上下游 | 334 依赖 320 的网关能力 | 320 先 |
| 328 ↔ 331 | 互补 | 328 解决 SSL EOF 重试；331 记录该缺口 | 互链，不合并 |

### 8.4 与 main 的机械冲突

- **确认 DIRTY**：#205、#290、#295、#296、#300、#301、#306、#326、#329、#334。
- **计数过期**：几乎所有改 `AGENTS.md` 的 PR 都以 109–112 篇为基线；main 已是 **114 篇**（integration 23 / arch 18 / tooling 13 / dev-exp 10）。逐篇合入会把手写计数改回旧值。
- **文件重叠**：`index.md`、`docs/solutions/index.md`、`docs/solutions/log.md`、各分类 `index.md`、各模块 `AGENT_HANDOFF.md`。
- **处理原则**：不要手工解冲突；逐篇 rebase 到最新 main，只保留自己新增的内容，合并后统一跑：
  ```bash
  uv run python scripts/update_index.py
  uv run python scripts/check_solutions_health.py --fix
  ```
- **不要逐字相信 PR 里的篇数**：以脚本重算结果为准。

## 9. 合并路线

### 9.1 第一批：低风险 / 高价值（建议本周）

| 顺序 | PR | 为什么先 | 前置动作 |
|---:|---|---|---|
| 1 | 335 | canon 基线，其余盘点依赖 | 无（CLEAN） |
| 2 | 322 | 生产按 flash 价给 pro 计费，约 4.5x 少收 | 无（仅 index/log 冲突） |
| 3 | 306 | 供应链结论已蒸馏，只合 5 篇 solution | rebase；只保留新增 solution |
| 4 | 280 | 解 294 断链；Colab 档案长期价值 | 规则段按 canon 改写后再摘 |
| 5 | 321 | 真实安全洞（注册暴露 + redirect_uri 接管） | **先脱敏** `SESSION_SECRET`/员工名；拆 `reset-user-quota.py` |
| 6 | 327 | NAS 假重登，生产已修、仓库未合 | 按 commit 拆读 |
| 7 | 331、289、293 | 纯文档/低风险 | 逐篇 rebase，重跑索引 |

### 9.2 第二批：需口径修正或串行

| 顺序 | PR | 前置动作 |
|---:|---|---|
| 1 | 294 → 295 | 先对齐 02 件数边界；295 规范已被 03 吸收 |
| 2 | 282 → 287 | 同文件；90 天段进 canon 05 |
| 3 | 283 → 296 → 326 | 同 OA 模块文档 |
| 4 | 284 → 286 | 堆叠；报税边界进 07 C13 |
| 5 | 297 → 315 | PB 主线；297 先脱敏 `data/*.json` |
| 6 | 309 → 298 | 298 只取 item_weight；stock_alert 由 309 提供 |
| 7 | 308 → 310（节选）→ 309 | 统一库存取数链 |
| 8 | 312（节选）→ 318 | 先改 FBA 判据为 `warehouse_classification`，标「生产未部署」 |
| 9 | 159、330、304、334、336 | 独立模块/文档，低风险 |
| 10 | 320 → 334 | 网关先于其下游口径 |

### 9.3 只摘文档，不整并

- **#288**：只取 `docs/solutions/architecture-patterns/branch-param-desk-read-then-guard.md`；`ops_assistant_demo/` 不进主仓。
- **#310**：只取语义/时点/存储三篇，其余留档。
- **#312**：只取 SC14 契约与结果表，等 #318 定型。
- **#329**：只取结论页 + `self_fulfilled_demand/`、`supply_netting/` 两模块（各自单独 PR）。
- **#205**：只取 solution + handoff，rebase 后重开。
- **#290**：DuckDB 部分留 demand_forecast；只把同步失败沉淀进 solutions。

### 9.4 放弃 / 关闭 / 仅留档

| PR | 处理 | 理由 |
|---|---|---|
| 314 | **关闭，不合并** | body 明写由 #318 接管；`supply_facts_export.py` 351 行被 318 的 1,341 行版取代 |
| 300 | 仅留档 | `control/` 47/477 已在 main；`out/*.json` 疑含业务数据 |
| 301 | 仅留档 | 与 300 同题异构，结论已由 306 蒸馏 |
| 313 | 仅留档 | 交付形态决策需按 #318 新基线重评 |
| 288 模块 | 不采用 | 外部银行竞赛 POC，与 FZH 数据管道不同域 |
| 321 文档 | 合并前必须改写 | 旧 `SESSION_SECRET`、攻击者 IP、员工姓名在公开仓库 |

### 9.5 每批收尾

```bash
uv run python scripts/update_index.py
uv run python scripts/check_solutions_health.py --fix
uv run python scripts/check_secrets.py
git diff origin/main...HEAD | grep -iE "(api_key|api_secret|password|token|ghp_|github_pat_)\s*=\s*['\"]?\w{8,}"
```

## 10. 未证实清单

| # | 项 | 现状 | 需要什么 |
|---|---|---|---|
| U1 | TikTok 跨前缀按数字主体合并 | **已落地**（2026-11-06）：canon 02 §3.1 + GRP-010 + 引擎配对 + phase36 兜底 | 已验收：202608 1 单、202609 0 单 |
| U2 | TikTok「手动建单」条款 | **已找到并落地**：TikTok API 不允许拆单 → 手动新建渠道账号建单；匹配键=数字主体（忽略前缀） | canon 02 §3.1 / GRP-010 |
| U3 | 90 天精确边界 | 只有 7/10、7/14 两个观测点 | 更多样本；canon 只能写「≈90 天」 |
| U4 | 「疑似官方 FedEx」账单 | #287 只有 1 单 | 账单抬头/账号核对 |
| U5 | #310「EN 落盘」与 `stock_sync.py` 重叠 | 未直接读 EN 代码 | 只读源码核对 |
| U6 | #328 与 `tongtool_order_cost.gsheets` 边界 | 未证实 | 读两边接口后补一句边界 |
| U7 | #300 `out/*.json` 是否真实业务数据 | 未证实 | 抽样 + 与 AGENTS.md 第 9 条对照 |
| U8 | #297 `data/*.json` 是否含真实 PO/SKU | 未证实 | 合并前脱敏审查 |
| U9 | #286「141 组件仓库名称为空」的月度影响 | 只有 8 月计数 | 多月复跑 |
| U10 | #318 生产未部署 | body 自述 | 部署前补状态说明 |

## 11. 附：45 编号索引

- **簇 A（9）**：280、282、287、290、294、295、307、296、283
- **簇 B（14）**：300、301、306、308、309、310、312、313、314、318、329、304、334、336
- **簇 C（9）**：284、286、159、205、315、297、298、326、330
- **簇 D（12）**：288、289、292、293、299、305、320、321、322、327、328、331
- **基线（1）**：335

## 12. Codex 独立复核对照（2026-11-06）

Codex 独立跑了同一批 PR（只读 body/文件/关键 md），与工头盘点的对照如下。

### 12.1 一致项

- 都认为 **#280、#282、#287、#290、#294、#295、#286、#309、#310、#334** 是主要可借鉴资产。
- 都认为 **#314 已被 #318 接管**、**#313 只是选项稿**、**#300/#301 留档**、**基建类 PR 不并入通途 canon**。
- 都认为 **#295 的 B1/B2 测算不能直接当正式价格矩阵**（canon 03 已吸收 B2 口径）。
- 都认为 **#282 的 90 天是观测阈值**，不能写成无条件业务规则。

### 12.2 差异与处理

| 项 | 工头 | Codex | 处理 |
|---|---|---|---|
| 先并顺序 | #335 → #322（定价 bug）→ #306 → #280 → #321（安全） | #280/#282 → #294 → #295 → #335 | 两条线并行：**canon 线**按 Codex（280/282→294→295→335），**仓库健康线**按工头（322/321/306 随时插入） |
| TikTok | 旧判「不立规 / 未找到手动建单」 | 未单独展开 | **已修正**（§7.1）：规则在 #280 §5b，缺的是实现 |
| 冲突范围 | 4 处 canon 实质冲突 + 5 组 PR 间硬冲突 | 8 条（含 #295/#282/#287/#290 vs canon） | 合并为 §8 矩阵；两边的条目全部保留 |
| #312/#318 FBA 判据 | 指出与 C3/ADR-0001 冲突 | 未提 | 采纳工头：合并 #318 前必须先改 `warehouse_classification` |
| #321 安全 | 指出文档含旧 `SESSION_SECRET`/员工名，合并前必须脱敏 | 列为「不建议并」 | 采纳工头：**先脱敏再合**，不是简单放弃 |

### 12.3 最终建议（两线并行）

1. **canon 线**（P0）：#280（摘 TikTok/件数规则）→ #282（90 天进 canon 05）→ #294（对齐件数边界）→ #295（已被 03 吸收，只留方法）→ 更新 #335。
2. **仓库健康线**（P0）：#322（定价 4.5x 少收）→ #321（注册暴露，先脱敏）→ #327（NAS 假重登）→ #306（供应链复盘 5 篇）。
3. **TikTok 落地**（P0，canon 线内）：canon 02 加条款 + 引擎配对 + phase36 body 兜底；202608 影响 1 单。
4. **其余**按 §9 的第二/三/四批执行；每批收尾跑 `update_index.py` / `check_solutions_health.py --fix` / `check_secrets.py`。

## 13. 最近活动与合并风险（2026-11-06）

> 用户关心：有些 PR 最近还在改，是否还有未完成事项、合并会有什么影响。本节把「活动状态」与「合并动作」分开说清楚。

### 13.1 最近 7 天有更新的 PR（按更新时间倒序）

| 更新日 | PR | 草稿 | 主题 | 建议 |
|---|---|---:|---|---|
| 11-06 | 295 | 否 | 通途 USTX 三方案（本次基线所在分支） | 本会话仍在推进；先不动 |
| 11-06 | 297 | 否 | PB 断货闭环 | 进行中；等 owner |
| 11-06 | 329 | 否 | 供应链 D3b/D5/D6/S1/S2 | 进行中；等 owner |
| 11-06 | 334 | 否 | Wayfair CG 调研 | 进行中；等 owner |
| 11-06 | 335 | 否 | 通途 canon（本次交付） | **本 PR**；可按需合 |
| 11-06 | 336 | 否 | PB 旧 SKU 转换 | 进行中；等 owner |
| 11-05 | 306 | 否 | 供应链 A/B/C+D 复盘 | 结论已定；可作为第一批候选 |
| 11-04 | 309 | 否 | 低库存钉钉告警 | 进行中；等 owner |
| 11-04 | 310 | 否 | 库存历史落库调研 | 调研稿；等 owner |
| 11-04 | 330 | 否 | DWS 群消息采集 | 进行中；等 owner |
| 11-04 | 331 | 否 | 离职账号权限回收 | 文档类；可随时合 |
| 11-03 | 318 | **是** | 供应事实 v1 | 草稿，勿合并 |
| 11-03 | 327 | 否 | NAS MCP 假重登 | 修复类；可随时合 |
| 11-03 | 328 | 否 | Drive 文件夹读写 | 可随时合 |
| 11-02 | 287 | 否 | 待追尾程 + FedEx 账单 | 工具/文档；可随时合 |
| 11-02 | 326 | 否 | 钉钉收款确认单 | 文档类；可随时合 |

> 另外 312、314、313 是 10-29 的**草稿**，仍在进行；320/321/322 是 10-29 的修复/基建类，未再更新。

### 13.2 合并 = 什么，影响是什么（大白话）

- **合并 = 把这条分支的改动正式放进 main**。不合并，代码/文档就只在分支上；合并后，所有人（和后续 Agent）默认看到的是新版本。
- **对知识库没有影响**：本次 canon 已经把这些 PR 的**规则**吸收进来了；合不合并 PR，都不影响你查规则。
- **合并的真实影响**：
  1. **行为变化**：比如 #322 会改计费、#321 会封注册入口、#297/#336 会改 PB 出件；这些不是纯文档。
  2. **冲突风险**：分支越久没合，和 main 的差异越大，合并要 rebase，可能要手工解冲突。
  3. **未完成风险**：最近还在改、或还是草稿的 PR，合了等于把「半成品」放进 main。
- **不合并的代价**：这些成果只留在分支，main 上的 Agent 看不到；但本次 canon 已经把**结论**接住，所以知识不会丢。

### 13.3 建议的默认动作

1. **本次不合并任何 PR**。知识库交付已经完成；合并是单独的工程动作。
2. 只对「**已定稿 + 最近 7 天没再改 + 非草稿**」的 PR 考虑合并；当前符合的只有文档类：#331、#327、#328、#287、#326。
3. 最近 7 天还在更新或草稿的（#295/#297/#329/#334/#336/#309/#310/#330/#318/#312/#314/#313），**等 owner 确认完成**再动。
4. #335（canon）本身可按需合；它目前 stacked 在 #295 上，若要单独落 main，需要 rebase 到 main 另开 PR。
