---
okf: v0.1
type: Reference
title: G1b首版实际结果与适配代码定向复审
date: 2026-10-20
reviewed_ref: 2ae0650b7e701fd0726e6c32748fc5a041ed7d6c
status: partial-extraction-not-contract-acceptance
---

# 判定与范围

**接受“两个仓的库存抽取＋一个SKU的EN试点已有首版产物”；不接受“G1契约/生产四量/逐行守恒已通过”。** 450/501缺口数字必须分清未采样与真实零值后重算。可继续只读调查和修正，不需要重开研究或等待所有未知项；在扩到top10–20前先修影响批量结果的适配器问题。

固定[Claude #300的2ae0650b](https://github.com/keyapi/fzh-data/tree/2ae0650b7e701fd0726e6c32748fc5a041ed7d6c/docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract)审核g1b_coverage/stock_snapshot/en_extract与results/pilot；上游EN_API/item_shipment_status.py同SHA。没有读取xlsx、原始快照、生产单据或凭证，没有访问API或本机定时任务。数字只核文内算术，抽取是否真实完整未独立复跑。

## 必须修正的结果与实现

路径前缀为上面固定版本的`experiments/g1_contract/`；行号按Git源文件一基计数。P1表示影响事实/验收，未声称每个潜在缺陷已在真实数据触发。

| ID/级别 | 问题与证据 | 影响与建议 | 结论 |
|---|---|---|---|
| G1B01 / P1 | coverage.py:247–255缺库存默认0，299–301全branch筛缺口；报告明言PL未拉、Wayfair unknown | 未采样PL/3PL/退货仓会进入“无供给/低覆盖”；把仓请求完成性与SKU查询结果分开，只有完整已查且API语义证明零才记0。450/501按已采样仓重算，其余unknown；它们也是branch×SKU数，不是全局去重SKU数 | 离线P01复现；现数字不可作为实盘缺货计数 |
| G1B02 / P1 | coverage.py:122–141缺月继续，缺列None、坏数量continue；stock_snapshot.py:81–86缺失/非法数转0 | 完整窗口仍除以6，坏输入也产成功形态。必需列/缺月报错或明确partial；数量校验有限、非负、整数件数，坏行保留ID/原因，不能静默跳过 | P03复现库存转换；订单路径静态确认，不断言本批已有坏行 |
| G1B03 / P1 | stock_snapshot.py:164–182满max_pages仍直接返回；code=None和未知datas形状可变成功空数组 | “0错误”不证明全页成功或响应合法。校验业务成功/结构/分页终止，满上限不明末页即incomplete，失败块不能被下游当零 | P05复现；原快照完整性尚未证实 |
| G1B04 / P1 | snapshot.py:248–267对重复行累加，warehouses[wh]又覆盖；coverage.load_stock无跨文件同snapshot/仓去重 | 分块/分页重叠或误传相同快照可双算，且总计与逐SKU视图可能不一致。用源行ID/仓ID/SKU/库存状态粒度去重或拒绝冲突，同cutoff只选一个版本；按请求chunk核返回SKU而非仅全family集合 | P06同快照4变8复现；未声称本批确有重复 |
| G1B05 / P1 | en_extract.py:36–42把WO所有工序total_completed_qty求和，不按首道/提交状态；仅555张JC不是四量 | 两工序各40被标completed_qty80。保留工序卡明细/行键/docstatus/路由，按已定首道规则，无JC=unknown；产出须Manufacture Stock Entry，不能靠该sum或WO头部替代。当前提取未包含SE，故四量未验收 | P04复现；应先修再批量提取 |
| G1B06 / P1 | en_extract.py:101–111只留dn/so_line_id/item/qty；上游EN_API/item_shipment_status.py:503–514的DN投影同样未保留DN Item.name | so_line_id来自so_detail，是SO行FK，不是DN行自身ID；同SO行可多DN行，无法稳定revision/收货分摊/去重。上游及导出均需保留Delivery Note Item.name、版本/cutoff/单位，沿D01契约抽取 | 静态确认；不能以DN张/行计数代替键完备 |
| G1B07 / P1 | pilot.md:41“1036=421+622”；results.md:111重复同构成 | 421+622=1043，差7。3120−2084=1036可以对平，但子分类不平；查逐SO行闭单/超发/负open/其他状态，显式列差异，不擅自把622改615 | P07复现；本SKU守恒未通过 |
| G1B08 / P1 | coverage.py:63–66发现同客户码多EN仅计ambiguous后continue，首个映射仍可用；SKU join全程按原客户码 | 歧义未fail-closed。报告称0歧义，因此未证实污染当前批次，但规则必须修。另保留canonical item/售卖形态/共享池关系，alias库存未对齐时不能把原SKU未命中直接发布实物缺货；不得反向把所有别名库存无条件混池 | P02歧义复现；alias影响待数据证明 |
| G1B09 / P1 | results.md:51–55由“当前列表无独立皮壳仓”推出历史老名已并入及当前单一供给池 | 名称缺失只证明没在该清单见到，不证明合仓/转移余额完成。提供稳定warehouseId、停用仓覆盖、改名/迁移与余额证据；缺证保留unverified，不重问公司基础架构 | 当前仓池合并结论证据不足，不能据此直接等同全部美中供给 |

## 解释与报告完善（P2）

- **覆盖不是有时间约束的可用量。** 14381÷(14720/6)=5.86、13563÷(14860/6)=5.48的文内算术成立；但available＋全部intransit不能证明在缺货前可到。保留on_hand_only覆盖和含在途名义覆盖，未得ETA则unknown，并与EN DN/头程去重。不把跨SKU总量当可互换的服务覆盖。
- **固定三个月和导出字段不一致。** en_extract.py:67仍传lead_months=3并导出lead_date；它不代表区间到货预测，应去掉或明确legacy_display_only。:82读so_delivery_date，而上游SO行实际字段delivery_date，当前导出可能静默None；加必需字段断言。
- **manifest/逐行报告尚为汇总。** results§6给文件名/规模与分项总数，不含输入hash、sheet/源行、请求/页/chunk终止证据及逐行disposition。EN“26 used，另列dead/疑似重复”不是互斥处置，异常可做多标签但主状态必须一行一个，保留原ID在私有本地报告即可，不要求公开原始单据。
- **快照不是瞬时全局事务。** 两仓请求跨数分钟且各块不同时间，需capture_start/end、来源时间、页元信息，不能仅用结束时fetched_at宣称同cutoff严格守恒。
- **每日备份仅收到注册报告。** 注册与NextRunTime不能证明首跑成功、全量分页/仓覆盖和持久留存。应由Claude核wrapper退出码、首个成功日志和带hash全量文件；本轮没有查询、更改或另建任何任务，不重复注册。
- **5%只保留假设。** 未来Amazon结算退款不等于实物退货且不覆盖全部渠道，更不证明可再售回库比例；需退货事件/收货状态与渠道分母。当前不净扣库存的修正接受。

## 已接受与关闭

1. 33,719继续按出库消耗毛量含补发，72已含不另加；库存净算不再次扣退货。
2. WayfairCG库存unknown、调拨不当实收、当前库存归属不由历史比例直接决定；美中run-rate仅指示。
3. 复用已有只读取数入口、当前仅1SKU，仍未声称全family提取完成，这个分阶段方向接受。Job Card是进度证据之一，仍需排除虚拟/撤销/重复卡，不称“唯一可信”而免除验证。

## 可复跑证据与下一步

[g1b_review_probes.py](g1b_review_probes.py)只用固定Git源码的已审纯函数和合成stub，不import生产模块、不读业务文件、不调用API；临时JSON也只有合成库存。运行：

`uv run --no-project python docs/plans/2026-10-20-codex-supply-chain-research/g1b_review_probes.py`

结果7/7缺陷探针复现（**是发现缺陷，不是七项生产验收通过**）。原C01–C35仍是独立契约参照，不用它们PASS替代本轮adapter验证。主Agent实跑，另有便宜模型只读交叉复核；DN自身键与SO外键区别由主Agent按既定D01裁定。

建议Claude先修G1B01–08并给仓库合并证据，再用同一批本地输入重跑：unknown/0分开、完整性闸门、逐行互斥去向、SO差7解释、首道JC与SE/DN四量。随后再扩top10–20；Wayfair后台及平台曝光数据继续并行，不阻塞已知事实修正。Codex下一轮只核修复与重跑差异，不重做泛调研，不改Claude文件。
