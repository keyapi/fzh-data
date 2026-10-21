---
okf: v0.1
type: Reference
title: U01关闭与family SO批量PoC首版复审
date: 2026-10-21
reviewed_ref: e696fa652ced786be052117fe6b2db0cb8666694
status: u01-closed-so-poc-scope-needs-correction
---

# 判定

**U01关闭，15旧定义统一接受；原适配器这轮修复审查可以收尾。接受SO批量PoC已开始，但其日期范围和family行分类需要修正，96 SO/380行不能据此定为2026-04..09完整family结果。** 下面是新PoC自身问题，不重开T01–T06或重做综述。

固定[Claude #300 e696fa65](https://github.com/keyapi/fzh-data/tree/e696fa652ced786be052117fe6b2db0cb8666694/docs/research/supply-chain/2026-10-20/claude)，审核g1b_round4_response、en_family_poc.py、U01与15的diff及同版本EN_API/item_shipment_status.py客户码查询。没有读取凭证/真实业务文件、没有调用生产API，不改Claude文件或系统任务。

## 1. U01与前轮事项关闭

实跑新`build_four_way`：成功SE5＋同批无法定位的失败SE，有成功量和无成功量的所有候选WO均query_incomplete、产量None、待入库None；已知5保留为known_subtotal。无query error的完整成功例仍给产量5。该闸门在汇总前，原U01反例不再触发。

15§2.1/2.2的快照键/ETA主键/modified水位/子表删除/旧hash例外与新章节已统一，接受；不再要求架构文档补写相同内容。新增DN/WO/JC/SE、modified水位/tombstone未实现是已声明阶段边界，**不作为本轮回归错误**。

## 2. SO PoC的具体问题

路径为固定版本`experiments/g1_contract/en_family_poc.py`，行号一基。

| ID | 级别 | 证据与复现 | 建议 |
|---|---|---|---|
| S01 | P1 | :115试点客户码查询无日期；上游helper仅customer_item_code like，无日期；后续去重/展开未做窗口复核。合成全在2025年的试点SO仍被写入date_from=2026-04-01/date_to=2026-09-30输出 | 所有候选来源共用明确业务日期语义，pilot路径同样过滤；保留来源/日期/窗口外去向。delivery与transaction是并集还是不同分析视图要明示，不能同一个数字掩盖口径。重跑后再更新96/380等报告，不猜实际受影响行数 |
| S02 | P1 | :141–145仅KS前缀/当前group/试点码作为family条件。已知KS0001-A的包装候选PK#KS0001-A，若组不在三角、客户码不是试点，就计入non_family_sibling。BOM候选查询也仅收KS码，可能连父单都漏选 | 将已承诺的版本family manifest真正接入候选发现与行级分类，含经证实KS↔PK#/ND#及历史角色；无法裁定记pending而非nonfamily。不无条件剥码、也不把组件/包装与终端销量重复相加。父单已找到与行分类正确是两件事 |
| S03 | P2 | :122超过max_sos直接切片；so_headers只报切片后数量，退出0，无truncated/候选总量。合成发现2单limit1仍成功形态 | max_sos可用于显式抽样，但manifest标partial、发现/选中/截断数及原因；若要求完整批则非零退出或不发布完整产物。本批96<默认500，未声称本批已截断 |
| S04 | P2 | :135详情缺失有field_issues但continue，:203仍退出0，manifest无complete。非family同行只计总数，无法逐行追溯 | 对found→selected→detail_success/missing→每源行family/pending/out_of_scope逐层对平；缺详情明确partial/failed，不当作成功完成。私有本地JSONL保留行ID/原因，不必公开原单数据 |

S01–S04均以main原函数＋合成iss stub复现；没有重写受测分类器。非family同行4,100只是Claude报告计数，其中可能有S02的待分类行，不直接断言其全部正确或全部有错。

## 3. 如何评价1/10→10/10

保留已知pilot客户码作为补证/候选来源合法，**不建议删除该路径**。但相同名单同时用于发现(:115)、判family(:141–143)和pilot_seen(:148)，10/10只证明经过该补证路径后观察到了名单，不是group/item_code路径独立完整性验证；再加S01日期不一致，不能将1/10与10/10当公平同窗对照或全族recall。

轻量补证即可：每父单/行保存matched_sources与纳入理由，分别报group、manifest物料、已知客户码的去重前后集合和同窗口覆盖；再用独立冻结的预期SO行ID/角色映射作为回归。已知试点可以用来校验，但不要让“测试名单决定纳入”成为覆盖成绩的唯一依据。

## 4. 本轮PoC的manifest还需补什么

以下是阶段交付要求，Claude已声明分页/水位尚未实现，不将未实现的后续模块当现成bug：

- run_id贯穿SO行和父单raw；带脚本SHA、family_manifest版本/hash、每来源条件/时间语义、页数/终止依据、候选/去重/选中/详情失败数量、输入/输出hash、complete/partial理由。
- 同一父单多来源先合并身份再取一次详情，保留来源并集；父单items中每行有独立处置。缺必要行ID/UOM/非法数量需报告，不能用float(None or0)伪造事实。
- SO窗口不是终端订单出库窗口，不能将380 SO行直接对等33,719终端出库件数。交易日期/交付日期/实际出库日期及各阶段cutoff需明确关联；后续四量仍按既定同单位契约核。
- 原始父单raw/逐行审计留私有本地，不公开客户/单据数据；输出文件和manifest按run版本配对，别用固定文件名覆盖后失去group-only与并集两版的可比证据。

## 5. 证据、接受与下一步

[family_so_review_probes.py](family_so_review_probes.py)固定e696fa65，仅离线AST选择器、合成临时文件和stub。U01混合失败与完整成功正例通过；4个PoC反例复现。原35个契约例不变且通过。一位便宜模型独立核对S01–S03和pilot检验独立性，主Agent复跑并核定包装角色不应盲目合并。

下一步Claude先修S01/S02、补S03/S04的可见状态与最小manifest，用同一批本地候选/已授权只读来源重跑同窗SO；DN/WO/JC/SE连接准备可并行，别把未纠正SO集当完整family向下传。然后交付实际PoC差异、分页与行级守恒。U01和旧T项不重开、15不再写同一综述；Wayfair与迁移审计继续独立pending。

本轮没有核验96/380/4,100或129/2/192/127原始结果，未访问生产。原适配器修复关闭与当前SO PoC未验收是不同阶段。
