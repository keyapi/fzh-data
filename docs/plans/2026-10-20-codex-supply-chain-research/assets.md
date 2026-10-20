---
okf: v0.1
type: Reference
title: 供应链资产账本与仓库检索边界
date: 2026-10-20
---

# 供应链资产账本

这是 2026-10-20 的只读代码/文档核对，不是生产数据审计。已有设计、已有代码、离线测试、合并、测试站部署、生产运行分别记录。历史报告中的实测数字不当作本轮重测结果。

## 1. 检索范围与计数

- 刷新当前 origin，核对 **22 个开放 PR 的标题及全部变更文件列表**，不是只搜 PR 标题；API 未报错，以下分类覆盖全部 22 个。
- 扫描 **84 个 origin 远端 ref / 84 个不同 head** 的文件名，关注 forecast/demand/predict/预测/销量、履约、成本规范、头程、Agent demo；64 个 ref 有匹配，共 165 个去重相关路径。路径匹配不等于已经逐文件审计。
- 扫描本地 `git log --all` 可达历史的 **2,841 个去重路径**，预测相关文件名仅命中三份赛狐销量接口文档，未找到 demand_forecast 源码或多方法销量预测对比。这是**文件名/提交信息检索范围内未定位**，未覆盖 notebook 内容、已删除且不可达对象、云盘、聊天附件或其他机器。
- 浏览最近 **100 个 closed PR 的标题/合并状态**，找到 #271 履约蓝图/钉钉、#274 库存预检、#263 出货计划/BOM 归档、#262 Colab 工具箱、#220 月度订单导出等；未读取全部 closed PR 的 diff，不声称全历史 PR 都已审计。
- [Gitee](https://gitee.com/keyapi/fzh-data) 网页抓取失败；`git ls-remote --heads` 成功，仅见 main，SHA 与 GitHub main 相同。**只能证明公开可见分支快照相同，不能证明 Gitee PR/私有分支不存在。** 未发现 PJ/Jack 头程新增代码；待其交付接口/PR。
- 原主检出有其他任务的未提交/未跟踪文件，本研究不修改或纳入提交；没有全盘读取私人聊天或未共享资料。

## 2. 关键 ref 快照

| 标签 | ref / PR | 固定 SHA |
|---|---|---|
| MAIN | origin/main | e5d07c9dfb181e102dd4ef990fe3271246527f74 |
| COST | origin/feature/ustx-cost-compare / [#295](https://github.com/keyapi/fzh-data/pull/295) | 7d9c49f89e085960eff6c0c71491290fb76b31be |
| ORDER | origin/feature/en-order-side-input / [#294](https://github.com/keyapi/fzh-data/pull/294) | 2ea63931f5b23d1050a882d8af0ab71605af95a3 |
| COLAB | origin/docs/colab-cost-current-state / [#280](https://github.com/keyapi/fzh-data/pull/280) | b90c79ecfb619921fcc4eb68379aaf16253a8162 |
| FULFILL | origin/claude/frosty-hellman-58de7a / [#291](https://github.com/keyapi/fzh-data/pull/291) | 4e4316c52313f86a40ea5e3ee110263e9a5a8c93 |
| ALERT | origin/feature/en-api-ops / [#298](https://github.com/keyapi/fzh-data/pull/298) | 653782b779eff3af2828cd78c5f306c50de605e1 |
| PB | origin/claude/vigorous-lehmann-889bf7 / [#297](https://github.com/keyapi/fzh-data/pull/297) | e9e92e4fbbe1ebdb1b1be2917fb3d9ab02580750 |
| DEMO | origin/claude/ce-okf-branch-param-desk / [#288](https://github.com/keyapi/fzh-data/pull/288) | 765f36933776963341ef0385dd2a009ebaa577a8 |
| SYNC | origin/claude/affectionate-bell-93d3ec / [#290](https://github.com/keyapi/fzh-data/pull/290) | 57a6c83c29fd34a7350c579a3c02c21842c20e33 |

本表 ref 会继续移动，续接按 SHA 回查，再刷新当前版本；不把本研究快照当永久真值。

## 3. 可复用资产与限制

| ID / 能力 | 已读入口/代码（以上 ref 标签） | 复用判断及实际边界 |
|---|---|---|
| A01 订单/库存/采购连接器 | MAIN: tongtool_api/AGENT_HANDOFF.md、mcp_http.py | 已有官方 MCP/CLI、错误码与商户共享 5 次/分钟实测记录；先复用。不能为三个 Agent 各自放大 API 并发，本轮未调用业务 API |
| A02 月度销售抽取/上传 | MAIN: web_automation/、tongtool_order_cost/scripts/upload_monthly_order_sheet.py；closed #220/#229/#262 | 已合并的月度导出/gsheet/Colab 工具基础；不是干净需求事实层。按发货月与下单月分别保留；生产 notebook 未在本轮读取 |
| A03 SKU/客户物料码映射 | MAIN: missing_products/AGENT_HANDOFF.md、multi_attr_saihu/、channel_account_sync/ | 已有三系统核对、例外与精确完整码登记规则。映射须带客户组/生效时间；不能一律剥 Cover/Foam 后当同一物料，也不为历史缺口重复创建 |
| A04 BOM/成本字段 | MAIN: EN_API/docs/reference/BOM成本报表逻辑.md、bom_cost_list_excel.py、bom_cost_refresh.py | 已有报表解释/取数/刷新资产。成本用于金额与方案对比；不能据“有 BOM 成本”推断生产 BOM、损耗/工时/替代料都完整 |
| A05 Colab 现状与断链 | COLAB: docs/solutions/architecture-patterns/colab-cost-pipeline-current-state.md、colab-cost-pipeline-data-flow.md、colab-gsheet-inventory.md、en-cost-side-current-state.md | 未合并；旧链路与 EN 成本改造的索引。旧月表仅有拆单、EN 裸原单、尾程迟到、仓库缺失等是已记录风险，仍需核当前状态 |
| A06 订单侧归一 | ORDER: tongtool_order_cost/tongtool_order_cost/order_side_input.py、tests/test_order_side_input.py | 已有纯函数、拆单/补发/TikTok 数字主体/部件判据；子单口径不合并订单边界。适合语义规则参考，不等同通用“终端需求件数”已解决；未跑该套测试 |
| A07 拆包裹/BOM 不重不漏 | COST: tongtool_order_cost/tongtool_order_cost/ustx_cost_compare.py 的 order_common_part、group_split_rows、merge_split_orders；docs/reference/cost-engine-spec/30、31 | **已有合并实现**，不是只有候选分组；主比较表保留，合并为附加视图。旧 31 交接“要做合并”已滞后。现有离线测试本轮 56 passed；真实数据量化/规则适用性仍待验证 |
| A08 SO→工序→DN | MAIN: EN_API/item_shipment_status.py、AGENT_HANDOFF_物料发货状态.md、tests/test_item_shipment_status.py | 已合并单物料查询、精确物料匹配、SO 行主键、草稿/取消/改单、工序不跨工序累加。旧进度算法与新“已生产”定义冲突，见下节，不能直接升为全链权威数量 |
| A09 统一履约查询 | FULFILL: EN_API/fulfillment/{model,quantities,stages,rules,kit}.py、fulfillment_query.py | 未合并；具多输入、证据类别、异常、数量阶梯、齐套；**代码只覆盖阶段0–3**，4–8不产出。模型与旧引擎依赖存在口径冲突，本轮相关测试 46 passed 仅证明既有断言 |
| A10 EN 内呈现与全链实体地图 | FULFILL: supply_chain_visibility/AGENT_HANDOFF.md、docs/reference/en-supply-chain-map.md、en-chain-cardinality.md、key_test/ | 找到独立子项目：文档称 SO 内摘要和原生报表已在测试站验证、生产未部署；独立屏仅设计。可复用呈现研究与实体地图，本轮未登录验证部署 |
| A11 工单可信性审计 | MAIN: erpnext/AGENT_HANDOFF.md、scripts/gen_report.py | 已合并正常/虚拟/混合报工分类。历史虚拟一键完工与报工录入重复是不同问题；不可仅看员工或 WO 状态一刀切 |
| A12 末道完工/入库核对 | FULFILL: supply_chain_visibility/docs/reference/en-produced-qty-vs-jobcard.md | 更新文档称 KS 工单无工序卡，入库主口径、末道去重为辅助；需与 A08/A09 协调。历史生产实测未在本轮重做，max(batch,per_tn)本身也是经验规则 |
| A13 出货计划/耗用/销售出库追溯 | MAIN: EN_API/AGENT_HANDOFF_DN追溯报表.md、dn_trace_report.py、AGENT_HANDOFF_delivery_plan_perf.md；closed #263 | 已有 DN→SO→WO→SE 追溯、跨月过滤规范、出货计划扫码性能与占用经验。部分 app 实现在外部仓/服务器，不能把本仓镜像等同部署源；只读参考 |
| A14 出库→通途采购桥 | MAIN: EN_API/tongtool_purchase/AGENT_HANDOFF.md、tongtool_purchase.py、tongtool_purchase_api.py | **关键已有拼图**：已实现预览、按货品累加、DN→采购单、回写单号与作废核验；文档称测试站部署。仅适用指定客户/成品与皮壳，海绵/套件等跳过；不是自动下单授权 |
| A15 头程人工表接入 | MAIN: dingtalk/dingtalk_sheet/{client,read_table}.py、AGENT_HANDOFF.md | 已有普通表格只读、分页空行/单元格上限/503重试/文档操作人权限经验；已有头程入口但未形成运输事件闭环。没有重读真实表 |
| A16 头程事件/数量分配蓝图 | MAIN: docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md；FULFILL 实现边界 | **蓝图已在 main**，设计运输批次/分摊/ETA/到仓，不能标为“全无”或“全已实现”。同事大屏尚待接口；头程费用不是在途事件 |
| A17 库存导入/成本承载 | MAIN: stock_init/AGENT_HANDOFF.md、warehouse_restock/build_saihu_warehouse_restock.py: SAFE_QTY=1000、docs/company-context.md | 复用映射/模板/成本拆分。**1000是成本用途安全冗余**；这些输入不能直接作为实物补货库存。具体赛狐记录是否虚拟须按批次/来源核，不笼统否定所有赛狐库存 |
| A18 低库存登记提醒 | ALERT: stock_alert/{client,scan,notify,excel,cli}.py、docs/reference/low-stock-alert.md | **PR标题漏显资产**；已有整仓分页、节流、汇总通知/任务。规则 available<threshold 且排除 available=0/intransit=0；本轮 scan测试4 passed。排除零零行会漏真实断货，因此不能直接作断货预警；本轮不发消息/安装任务 |
| A19 PB 库存预检/断货闭环 | MAIN: pb_orders/AGENT_HANDOFF.md；PB: notion_stockout.py、docs/reference/notion-stockout.md、tests/test_notion_stockout.py | 已合并 SPS 明细预检；Notion闭环在开放 PR。人工事实/邮件/CSV差分与状态联动可复用；未读 Notion/邮箱原始记录，既有台账不保证覆盖所有商品 |
| A20 PB 下单量样例 | PB: docs/solutions/workflow-issues/pb-replenishment-sizing-from-sales.md | 已有2026-10-16真实业务方法：仓别名、PB/非PB、断货期、覆盖期、通途采购在途、结论先行Excel。是特定样例，6个月覆盖/3个月交期不是全公司参数，剔断货月也不是无偏通用估计 |
| A21 包裹/尾程异常 | MAIN: parcel_track/、ups_track/、fedex_track/、gls_track/、sellfox_shipping/；开放 #159 | 已有多承运商状态历史/异常、打单/回写与失败边界。尾程轨迹不能替代头程在途；打单不等于取件，尾程包裹不可直接当需求件 |
| A22 成本/财务对账 | MAIN: platform_account_reconciliation/、pb_reconciliation/、sellfox_settlement/；开放 #286/#287/#205 | 提供币种、成本、结算证据与商品利润约束；结算月不等需求月，促销供货价变更须带时间。对补货TCO有价值，不把财务金额替代物理数量 |
| A23 受控 Agent demo | DEMO: ops_assistant_demo/AGENT_HANDOFF.md、agent_runtime.py、agent_tools.py、domain.py | 已有CAPABILITIES统一注册、后台身份、不可变确认摘要/状态版本、过期/取消、独立读回模式；文档称132项测试与模拟真机验收，本轮未重跑。**模拟银行/工单，不是SCM生产实现**；可借模式，不整体搬业务 |
| A24 企业 Agent 知识与界面 | MAIN: docs/enterprise-agent-knowledge-system.md、ai_access_poc/open_webui/AGENT_HANDOFF.md、board/AGENT_HANDOFF.md、intent_router/ | 已有只读工具壳/报表摘要、记忆/知识分层研究、路由none兜底。根级ai_access_poc/AGENT_HANDOFF.md不存在，勿据路径误判模块不存在。模型自报confidence不是正确率 |
| A25 同步质量与外部自定义app | SYNC: docs/solutions/integration-issues/en-tongtool-order-package-sync-failures.md；COLAB同步覆盖交接 | 更新文档已给出 warehouse_name更新漏写、商户限流、队列300s、任务重叠等根因/修复记录，较旧“疑似仓库改名”更具体。真正tongtool_integration源码不在本仓，部署修复需另核，不能依据“已同步”状态保证字段完整 |

## 4. 必须裁定的冲突（现有测试不能代替裁定）

| 冲突 | 证据对照 | 对决策的影响 / 当前处理 |
|---|---|---|
| 已生产定义 | FULFILL: EN_API/fulfillment/quantities.py:credible_produced_qty、stages.py 用第一道工序；同ref新 en-produced-qty-vs-jobcard.md §0/§5以已提交Manufacture入库为主 | 首道完成不等最终完工/可用，KS无JC。分别存首道/末道/入库数量，主口径暂挂“待裁定”，不据旧derived数自动补货/承诺 |
| 设计稿与代码状态 | COST: 31-handoff说只完成group_split_rows；同ref已存在merge_split_orders及测试 | 复用现有纯函数与测试再核真实语义，不能重复造同名合并器 |
| 合并的同产品检查是可选参数 | COST: merge_split_orders仅在sku_to_product非None时执行同EN产品守卫；未传时仍可合并 | 56项通过不证明所有调用都启用业务映射，新计划链复用前须强制所需映射/范围检查；缺失或歧义阻断，不能只传订单号相似键 |
| 库存字段≠实物状态 | MAIN SAFE_QTY=1000；ALERT文档注明可用0不等缺货；PB文档不建议EN Bin代通途库存 | 需要仓/系统/业务状态/时间/人工调整的来源契约，不能盲定某系统所有余额绝对权威 |
| 零零行被忽略 | ALERT scan.py:is_low_stock排除available=0且intransit=0 | 登记提醒的合理过滤不适合缺货检测；需结合在售/停售与缺货事实，零零行必须保留到异常/排除报告 |
| 月表/EN时间不同 | COLAB/SYNC: 月表发货月、EN sale_time下单；尾程晚补/父子单表达不同 | 按明确时点/键对账，分别建设需求与出货事实；“按同月找不到”不能当漏单 |

## 5. 全部开放 PR 分流（互斥）

| PR | 分类 | 处理/排除理由 |
|---|---|---|
| #298 | 核心 | stock_alert被标题隐藏；重尺可辅助箱规 |
| #297 | 核心 | PB补货、Notion断货样例 |
| #295 | 核心 | EN BOM成本替换、拆包裹与合并 |
| #294 | 核心 | 订单侧事实、补发/部件口径 |
| #291 | 核心 | 履约模型、EN供应链地图/呈现 |
| #290 | 核心 | 同步质量根因与修复记录 |
| #289 | 核心 | 同步超时/429与数据新鲜度 |
| #288 | 核心 | Agent受控操作可借模式 |
| #280 | 核心 | Colab/gsheet/EN现状和缺口 |
| #299 | 支撑 | Harness/费用经验，非业务架构事实 |
| #287 | 支撑 | 尾程费用迟到、到岸成本/盈利 |
| #286 | 支撑 | 结算/成本/FBA证据桥，非需求事实 |
| #284 | 支撑 | 财务采集/人工口径交接 |
| #282 | 支撑 | 通途历史改单窗口、数据修正边界 |
| #205 | 支撑 | PB促销供货价与毛利约束 |
| #159 | 支撑 | 出库回写安全与未知提交状态 |
| #296 | 本轮排除 | 8/9月结算审批附件收尾，无直接计划能力新增 |
| #293 | 本轮排除 | 网络出口运维，当前无需展开 |
| #292 | 本轮排除 | 网关屏蔽词排错，非供需计划能力 |
| #283 | 本轮排除 | OA/赛狐账期核对，现阶段无新增计划算法/事实 |
| #300 | 研究上下文 | 交接线索；不继承其他软件研究结论 |
| #301 | 本研究 | 自身提交，非被复用业务资产 |

对账：**22 = 9核心 + 7支撑 + 4本轮排除 + 2研究上下文/自身**。分类不是 PR 质量评价；未排除未来复用。

## 6. 本轮离线验证

从上述固定 SHA 导出所需已跟踪 Python 文件至临时目录，未 checkout/cherry-pick 他人分支，未载入生产凭证或访问业务接口。初次无项目 Python 缺 pytest，改用 uv 临时依赖环境（pytest/requests/python-dotenv/openpyxl），不修改仓库依赖/锁文件。

| 来源 | 执行的既有测试 | 结果 |
|---|---|---|
| COST | tongtool_order_cost/tests/test_ustx_cost_compare.py | 56 passed，1.59s |
| FULFILL | EN_API/tests/test_fulfillment.py + test_item_shipment_status.py | 46 passed，11.49s |
| ALERT | stock_alert/tests/test_scan.py | 4 passed，1.97s |

合计 **106 passed / 0 failed**，仅这些文件中的离线断言。不是全仓回归、生产数据对账或算法适用性证明；特别是首道工序口径冲突仍未解决，测试通过不得抹去该风险。
