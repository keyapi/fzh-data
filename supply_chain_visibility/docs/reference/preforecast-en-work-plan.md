---
okf: v0.1
type: Plan
title: D预测未完成期间的ABC接入与EN供应侧实施计划
date: 2026-11-02
status: implementation-and-handoff
tags: [abc, supply-position, jack, readiness]
---

# 目标和边界

最终目标是分公司自发货的大范围SKU辅助下单，经人工审核后执行。
D预测未完成不阻塞现有供应事实的采集、身份与仓池对齐、库存刷新和追单视图。
没有D时不把需求写0，不生成“无需补货”或最终建议量。
不重建工厂MRP、不引入EN采购单，不新增自动通途入库或自动下单。

## 实际核对的阶段成果

已读Claude提交的PR306（36928abf）与本地冻结工作簿，不以主仓库旧main
或旧聊天代替最新成果。未修改Claude正在使用的脏工作区。

| 板块 | 核实对象 | 结果与限制 |
|---|---|---|
| A | SKU活跃宇宙FINAL | 7087记录，2337活跃EN物料；角色与发货方式不能混同 |
| B | v6r10 | 2931证据行，1914唯一产品×仓池；所有可进净额仍为否，不能把市场已证当下单许可 |
| C | v14 | 2135库存资格键：1918 join_full、217 no_join；源库存时点10/28，文件生成日不是库存日 |
| D | Claude正在迭代 | 不接手改模型，不以未完成为理由停E；本工具标not_integrated |
| E | Jack与PR318/323 | 创建审计已有第一批；完整逐行导出、来源时点、全链消费仍有缺口 |

独立读工作簿并比对输入SHA，A/B/C与原报告冻结指纹一致。
C v14的CG归属输入声明依赖B v6r9，而当前B为v6r10；保留此版本关系，
后续检查归属变更影响，不宣称所有版本天然一致，也不因此废弃已证子集。
本次没有判断线上库存停止刷新，只证明这份供下游消费的C文件已旧。

## 已实施：不依赖D的接入资格表

模块 `supply_chain_visibility/preforecast_readiness.py`，读取三个冻结工作簿，
保留A活跃资格、B同商品同仓池/单位、C身份覆盖与来源、原B门禁/阻断原因，
按目标键形成 `preforecast_readiness.parquet`。不会重新计算A/B/C规则。

```powershell
uv run --with openpyxl --with pyarrow python -m supply_chain_visibility.preforecast_readiness --a D:/private/A.xlsx --b D:/private/B.xlsx --c D:/private/C.xlsx --as-of 2026-11-02 --max-stock-age-days 1 --out D:/private/readiness
```

一天仅是本次显式检查阈值，可由调用方调整，不是已承诺的生产SLA。
文件只读入，不修改原工作簿；输出私有目录，保留版本目录、输入指纹和报告。

真实运行结果：

- 3251个诊断目标键：包含B/C键和A活跃但尚无仓池的占位行，不等于3251个可补货SKU。
- 2135个C输入键全部有去向，没有因未匹配B丢弃。
- 1631个键在A活跃、B同仓池/单位、C join_full上具备接入基础。
- C的1918个join_full中，另287个未匹配当前B同商品/仓池，不跨美东/美中挪库存。
- 1596个键具备独立需求候选形态，供下一步D/E评估；不是最终模型或下单资格。
- 按一天时效检查，当前ABC新鲜可用为0，因为C源是10/28；不能重写生成时间冒充今日库存。
- B原可进净额门禁和共享/历史等阻断原文保留。abc_contract_compatible只是字段/证据可拼，
  不推翻B的下单门禁；所有netting_ready/auto_order仍false。

库存真零保留0；缺库存、partial、缺来源、单位冲突保留null/原因。
不把不同形态/单位/仓池数值全局相加；组件、CG、套件仍走原C资格，不重分配共享池。
下一轮需要刷新C并接E，不能仅因生成本表又声称整体项目完成。

## Jack不依赖D即可推进的工作

| 顺序 | 任务 | 输入与可复用入口 | 可验证交付 |
|---|---|---|---|
| J1 | 完整创建清单只读导出 | delivery_plan审计父/行/事件、现有get_creation_audit | 返回DN/创建ID/status/PO/替代关系与lines；受限用户不能读其他DN；截断/覆盖明确 |
| J2 | PO状态带来源时点 | 现有批量状态查询与缓存 | 每PO的原始状态、原单号身份、目的仓字段（有则给）、source_observed_at/缓存生成时间；不把received_at当来源时间；未查/限流不报不存在 |
| J3 | 按物料/客户SKU取全供应事实 | 既有SO Facts＋DN独立账＋Shipment | 下单余额/已证生产/DN净交付/物流/PO，数量与时间及证明分开；无SO的DN不丢；SO余额不假装已证在产 |
| J4 | 分公司/FBA与物流语义 | 已确认客户/用途映射与Shipment两线 | 报表/API同筛选口径；FBA缺字段不变分公司；签收/POD兼容、上传日不是签收日；拆批不复制整DN量 |
| J5 | 供应时间线与库存来源对接 | 复用现有通途/CG同步与本地C，不重造同步 | SKU×目的仓/池×单位的数量节点、当前库存截至时间、下一已知/预计节点、待核与原单下钻；没D时显示“预测未接”，不显示零需求或建议量 |
| J6 | 批量导出与稳定刷新 | 复用既有API/导出器与PR323 | 先小范围冻结快照，再50/200/500/批准范围规模；页间漂移拒收、失败保留旧版、可见陈旧；按实测定频率，无需先上Redis/事件总线 |

J1/J2最先打通：无需等新建真实PO，先用冻结样例与既有PO的授权只读验证。
J3/J4可与其并行；J5复用同一事实服务，不维护第二套计算。
J6扩大范围，不把limit=2000或单SO成功说成2000SKU验收。
先用已证子集验证接口，其他A活跃商品继续列出待核/缺失，不能只导出“好看的样本”。

### 本轮收货简化继续生效

PO全部到货按业务批准假设关闭创建清单的included商品；未纳入不一起关闭，
部分/短收不按比例猜商品。历史PO无新审计清单时标legacy/覆盖不足，
不伪造清单，不要求先逐件扫码或全历史逐行对账。
物流签收是到达，不自动写通途入库。PO已完成移出在途后，由相同源时点的
C库存提供余额；两者缓存不同步则刷新/标条件态，不重复加一份DN数量。

## 我们本地继续负责什么

1. 维护本资格表的版本与全范围去向，和Claude的A/B/C/D对齐，不再另定第二套归属。
2. 从现有库存同步产物刷新C并重跑冻结规则；不等D，不把10/28库存当今天。
3. 用J1/J2导出和批准B映射接PR323，验证入库推定、单位、库存时点与去重。
4. D交付后按明确的需求粒度/预测单位/期间接入，不拆套需求去配组件库存，
   不把FBA消费加进分公司；最后才出人工审核补货清单。

## 进展验收方式

按“来源版本/截至时间→输入范围/行数→输出各去向→数量守恒→可复跑命令→限制”交付。
J1覆盖included/排除/映射失败/未知/作废重建；J2覆盖0/1/2/3/4、限流与缓存；
J3覆盖未下生产、已生产未出库、独立DN、多运单、历史parent变化；
J5展示同商品不同仓以及无预测仍可查催单；J6验证源修改/断页/损坏/失败不发布。
新接口与报表代码先测试和冻结评审；合并/生产部署/业务写入仍需原有授权。

## 2026-11-02 full facts v3 的 A/B/C 接入（本轮）

- 复用 `preforecast_readiness.py` 的读取/哈希/去向对账；新增可选的 B 目标键列
  （`目的仓/目标仓/warehouse/仓库`、`branch/分公司`、`purpose/用途`、
  `tt_sku/通途SKU`）。同一维度多个别名值冲突直接失败，不静默取首值。
- 新增 `abc_inputs.py`：A 活跃商品全集、B 身份权威、C 库存观测 → full facts
  的 strict 库存行。缺字段保持 null/unknown + reason；C 无 B 待核；真零保留；
  陈旧保留观察值但不当前可用；同一 CG 物理池被多个 branch 认领时不复制数量，
  另生成唯一池级未归因行。
- B/C 版本关系：`--b-version` 与 `--c-declared-b-version`（或工作簿声明）不一致
  显式 `c_declared_b_version_mismatch`，C 库存不可信。
- A/B/C 输入契约包含 source/version/sha256/row_count/as_of；支持期望哈希/行数校验。
- 发布：`full_supply_facts.parquet` 主入口 + JSON 追溯 + 独立 `supply_position`
  + timeline + 统一 manifest；JSON/Parquet 逐字段回读、重复键拒收、失败不切 latest；
  冻结输入副本 + `--replay-run` 跨平台复跑。
- v3 追加：B/C 单位资格、精确时间证明、观察/归属/下单三层、稳定来源身份去重/冲突、
  非权威来源不得填补缺失身份、物流完整身份分组、输入契约与 partial/truncated 区分。

## 2026-11-02 full facts v4 第三轮收口

- **四层资格**：观察事实 / 归属资格 / 当前可用 / 下单资格；C 必须
  join_full + source_ref + 数量 + UoM，否则 `c_not_qualified`，可信与当前可用均为
  null；原因已报不合格时不得同时保留可信数量。
- **禁止身份覆盖**：ABC 补齐命中已有 DN/PO 键时，不同已证明细来源合并求和、同源重放
  去重、无法证明保留两行并标 `abc_identity_key_conflict`；同键 ABC 库存冲突标
  `abc_inventory_key_conflict`。
- **来源 vs 目标**：来源身份 = source_ref/WO/单据明细 + 商品/UOM；同一物理来源跨
  branch/仓/用途且无 allocation 容量证明 → `source_target_conflict`，不得输出两份
  确定供应；物流同物理组同规则。
- **reader**：每次读取按当前时间重算行级 freshness，文件头新不能掩盖旧行；
  allow_stale 只影响可读许可。
- **冻结输入**：非 not_provided 输入缺失/变更/复制失败终止发布并保留旧 latest。
- **业务 partial**：分页已 exhausted 的 partial 不拒收，该层汇总 unknown、已证片段
  保留，`partial_reason=business_partial`；分页截断仍拒收。
- 版本：`full-supply-facts/v4`、`abc-frozen/v3`、`supply-publication/v3`、
  `supply-pipeline/v4`；真实 A/B/C 工作簿验收仍 pending。
- **真实 A/B/C 冻结工作簿当前不可用，真实链路验收 pending**；不以合成数据冒充。
  D 预测仍未接入；`forecast_connected/netting_ready/auto_order=false`。
