---
okf: v0.1
type: Index
title: Codex 供应链整合独立调研
date: 2026-10-20
---

# Codex 供应链整合独立调研

2026-10-21最新固定Claudee696fa65：U01已关闭，15定义统一接受；SO批量PoC开始，见[SO首版复审](review-family-so-poc.md)。需修日期漏窗/包装family分类，显式标截断与详情失败；不重开旧T项，不重做综述。

2026-10-21第四轮固定Claudef14c9709：见[关闭项与family PoC交接](review-g1b-round4.md)。T01–T04/T06关闭，T05仅余成功SE＋无法定位失败SE的U01；7正例/1反例。E01–E04接受，可推进family只读批量PoC，下一轮审核实际PoC，不重做综述。

2026-10-21第三轮复审固定Claudef4797aa0：见[修复关闭项与批量ETL实施边界](review-g1b-round3.md)。8个修复正例、6个剩余反例；接受批量方向，仍需修presence/SE未知/批次完整性并补family manifest与增量键。未取业务数据或访问生产。

2026-10-21最新复审：固定Claudeaad55822，见[第二轮修复与重跑审查](review-g1b-round2.md)。DN行键、差7、BOM歧义与业务合仓口径已关闭相应子项；每日备份转换/complete、JC端点、SE未知仍需修复。8个离线反例＋4修复正例，未读取业务数据或访问生产。

最新G1b首版复审：抽取已有首版产物，但适配层和数量守恒尚未验收；见[定向问题与7个离线复现](review-g1b-first.md)。35个契约例通过不能代替真实适配器修复。

当前增量v3：固定Claude629dc7b3，35例通过（C01–C25未变）；见[g1-slice.md](g1-slice.md)及[增量定向复审](review-incremental-v3.md)。解除旧3PL等待条件，同意Claude按显式假设进行G1b；Codex本轮不取数据/访问生产。文内较早暂停/25例描述保留历史，不再作为当前执行指令。

| 文档 | 用途 |
|---|---|
| [G0固定基线与G1扩展](baseline.md) | 冻结5708609d与Claude b23c319a；文件hash及固定读取版本 |
| [G1三角出库与3PL口径v3](g1-slice.md) | 出库含补发、退货情景、3PL实收/供货归属、cohort；G1b可按显式假设继续 |
| [匹配过程§0–§4复核](review-mapping-process.md) | 固定6d0a1324；业务前提接受，毛匹配量/退货/未匹配去向需核，不重复旧v1数字 |
| [08三节定向复核](review-08-g0.md) | 只看§2.1/2.3/2.4；接受/部分接受与执行前提 |
| [当前对齐状态与两PR关系](alignment-status.md) | #300固定cd7a8a06复核、已关闭项、G0余额/需求周期边界、G1推进和交叉审核范围 |
| [共同框架候选与下一阶段](common-framework.md) | 总体链条、实体/键/时间契约与G0–G5门槛；待对方确认 |
| [35个合成例与结果](semantic-examples.md) | C01–C25保留，新增C26–C35；35/35本地参照通过，非真实回放；源码contract_examples.py |
| [对齐状态与备选分支](decisions.md) | 必须统一的契约、可暂留的实现分歧、影响与裁决时点 |
| [Claude修订版定向复审](claude-review.md) | #300固定e0975b97：已关闭项、剩余标签重叠/坏数/键/守恒问题 |
| [调研执行计划](research-plan.md) | 范围、独立性、覆盖标准、子 Agent、阶段提交与验收 |
| [综合判断与三条路线](synthesis.md) | 先看：复用EN、增量计划引擎、窄范围组件的比较及审批视角 |
| [历史预测接续与产品边界](history-handoff.md) | #304已找回；阶段A完成/B未启动；当前不采用TSFM，PB原型复用限制 |
| [资产账本](assets.md) | 27项资产；首次22个开放PR/84远端扫描，加#304定点补核；106项历史离线验证 |
| [能力覆盖与缺口](coverage.md) | 十个能力域的现有/整套/组件证据和待验证条件 |
| [成熟实践研究](industry.md) / [来源](sources-industry.md) | S&OP、MRP、DDMRP、MEIO、APS、服务/现金与适用边界 |
| [预测与Agent研究](forecasting-agents.md) / [来源](sources-ai.md) | 基线、基础模型、删失、LLM+OR、真实案例分级与许可 |
| [开源方案研究](open-source.md) / [来源](sources-oss.md) | 整套计划产品、组件、CE/商业边界、版本与TCO |
| [头程关联模型](freight-model.md) / [来源](sources-freight-model.md) | DN行、票/提单/柜、多运输腿、事件及仓库实收的关联与守恒 |
| [头程数据接入](freight-connectors.md) / [来源](sources-freight-connectors.md) | 供应商/船公司/聚合商API、EDI/文件兜底、开源边界和待核接口 |
| [最小验证合同](experiments.md) | E1已做本地合成参照例；适配器/真实回放、E2计划引擎、E3预测/策略、E4审批Agent尚待验证 |
| [证据与交叉评审](evidence-review.md) | 主Agent抽查、子Agent互审、修改与局限 |
| [起点核对与续接](checkpoint.md) | 已核对分支、交接纠偏、未决项、下次从哪里开始 |
| [出库/3PL增量定向复审](review-incremental-v3.md) | 固定629dc7b3的§3/§4；退货、供货归属与情景边界 |
| [G1b首版实际结果复审](review-g1b-first.md) | 固定2ae0650b，450/501口径、完整性、JC/DN/数量差异；离线探针g1b_review_probes.py |
| [G1b修复第二轮复审](review-g1b-round2.md) | 固定aad55822：关闭子项、daily入口负例与下一步；g1b_round2_probes.py |
| [G1b修复第三轮与批量ETL](review-g1b-round3.md) | 固定f4797aa0：8正例/6反例、15方案的family全集/水位/键；g1b_round3_probes.py |
| [G1b第四轮关闭与PoC交接](review-g1b-round4.md) | 固定f14c9709：7正例/1剩余SE边界、接受E01–E04并推进PoC；g1b_round4_probes.py |
| [U01关闭与SO批量PoC复审](review-family-so-poc.md) | 固定e696fa65：U01正例、4个SO反例与同窗/行级manifest；family_so_review_probes.py |
| [变更日志](log.md) | 阶段成果记录 |

当前状态：Codex完成v3增量、35例和629dc7b3的§3/§4定向复核；旧G1a v1失效，Claude可按显式假设进行G1b，Codex等待真实回放报告再核；已完成首轮独立研究、综合与交叉审阅；真实数据回测和整套产品运行仍待下一阶段。已复核Claude #300固定cd7a8a06：共同框架原则已双向对齐，R01/R02原代码问题可关闭，G0细节及真实验证仍待完成；Cursor成果未读。两PR保持独立，不修改其文件。
