---
okf: v0.1
type: Reference
title: 供应链独立调研当前保存点与续接
date: 2026-10-20
---

# 当前保存点（2026-10-20，三角皮壳口径v2与G1b暂停）

2026-10-21最新固定Claudee696fa65：U01已关闭，15定义统一接受；SO批量PoC开始，见[SO首版复审](review-family-so-poc.md)。需修日期漏窗/包装family分类，显式标截断与详情失败；不重开旧T项，不重做综述。

2026-10-21第四轮固定Claudef14c9709：见[关闭项与family PoC交接](review-g1b-round4.md)。T01–T04/T06关闭，T05仅余成功SE＋无法定位失败SE的U01；7正例/1反例。E01–E04接受，可推进family只读批量PoC，下一轮审核实际PoC，不重做综述。

2026-10-21第三轮复审固定Claudef4797aa0：见[修复关闭项与批量ETL实施边界](review-g1b-round3.md)。8个修复正例、6个剩余反例；接受批量方向，仍需修presence/SE未知/批次完整性并补family manifest与增量键。未取业务数据或访问生产。

2026-10-21最新复审：固定Claudeaad55822，见[第二轮修复与重跑审查](review-g1b-round2.md)。DN行键、差7、BOM歧义与业务合仓口径已关闭相应子项；每日备份转换/complete、JC端点、SE未知仍需修复。8个离线反例＋4修复正例，未读取业务数据或访问生产。

最新实跑阶段：已定向复审Claude2ae0650b的G1b首版，见[review-g1b-first.md](review-g1b-first.md)；7个离线缺陷探针复现。请先修未采样当0、输入完整性/去重、首道JC/DN键与SO差7，再扩top10–20；Codex未访问生产。

当前增量v3：固定Claude629dc7b3，35例通过（C01–C25未变）；见[g1-slice.md](g1-slice.md)及[增量定向复审](review-incremental-v3.md)。解除旧3PL等待条件，同意Claude按显式假设进行G1b；Codex本轮不取数据/访问生产。文内较早暂停/25例描述保留历史，不再作为当前执行指令。

## 已完成

- 最新接收6d0a1324的三角1:1皮壳更正：更新g1-slice/baseline、C21–C25（总25/25）、review-mapping-process仅§0–§4。主映射仅20261016 BOM；Cost Review只借逻辑不用数据。不得恢复旧两仓完成品/旧G1a v1成绩。

- 此前按12完成baseline.md、C14–C20（当时20/20 PASS）、review-08-g0.md和g1-slice.md；只读仓库，未读业务文件或取业务API。范围为KS0001/KS0248两leaf×Daneey/Centrade两仓×2026-04..09。P1首选20261016 BOM导出；用户已授权EN单据生产只读，该授权属于此前阶段；当前按业务更正暂停G1b，不据此继续取数。

- 最新补核Claude #300固定cd7a8a065f32c204ef57a423527ecce61243f052，R01/R02原代码问题可关闭，DN/收货/预测冲减结构修订接受。实跑其4个golden和另13个合成检查；未复现真实WAPE。架构原则已由Claude10接受，见alignment-status.md。

- 此前完成Claude #300固定e0975b97定向复审、共同框架候选、分歧表和13/13本地合成例；见common-framework/decisions/semantic-examples/claude-review。未声称双方已批准。
- P0规划已提交dfded88e；本轮完成P1资产复核、P2首轮三路独立研究、P3验证合同设计、P4首轮综合及交叉审阅。
- 首轮25项资产及22个开放PR/84远端树检索已完成；用户补交#304固定74d78faa后资产增至27项，历史预测位置问题已解决。首次检索边界见assets.md，不等于完整生产审计。
- 首轮三个gpt-6-luna子Agent完成成熟实践、预测/Agent、开源研究及互审；本轮另两位定向复审E1/事实契约，并复核合成例，均已结束当前工作。
- 原始来源中重要版本/许可由主Agent另核；原独立首稿未读其他软件；本轮用户授权后开始Claude定向对照，Cursor未读。
- 固定SHA的成本56、履约46、低库存scan4项既有离线测试，共106 passed。它们不能裁定生产事实口径。
- 综合三条路线、老板一页纸三视角、E1–E4验证合同已完成；本轮补独立头程模型/接入研究与来源表。真实回测/整套产品运行尚未执行。
- 当前产品决定：阶段A完成/B未启动，分段全局LightGBM+Croston/TSB长尾/生命周期+Conformal+物料组调和；现阶段不采用TSFM，不加入当前实验。历史PB原型是单SKU一次性脚本，不等公司级模型。

## 关键固定版本与纠偏

所有完整SHA见assets.md。MAIN=e5d07c9dfb181e102dd4ef990fe3271246527f74；COST=#295；FULFILL=#291；ALERT=#298；ORDER=#294；COLAB=#280；PB=#297；DEMO=#288；SYNC=#290。

- 履约蓝图文档已在main，实现/EN供应链呈现在未合并#291；阶段0–3不等于头程全链实现。
- #298标题为重尺但包含stock_alert，不能只看PR标题找资产。
- #295已有merge_split_orders；旧交接“只完成分组”已滞后。同产品映射守卫是可选参数，复用前要检查调用约束。
- 同一#291里旧代码第一道工序量，与新文档建议的“已提交生产入库主口径”有冲突；此项尚未裁定。
- 赛狐成本导入1000、通途报溢/零库存语义不等于实物可售；stock_alert排除零零行不适合作为全部断货事实。
- frePPLe正式9.19.0 CE需要核库存政策补缺；库存规划屏/策略模型有商业edition边界。TimesFM3下载权重的商业/生产限制不能倒推到2.5。

## 当前未完成与精确下一步

1. 历史预测已定位，不再等用户找位置。先读history-handoff.md的#304固定SHA与代码限制；PJ/Jack敏感资料仍在整理且无PR，等待的是供应商具体接口，不阻塞独立标准/关联模型研究。
2. 本地25个参照合成例已通过；当前先确认3PL责任、退货事件与全输入去向，再安排后续授权回放；不先改生产，不把算例通过写成事实层完成。
3. 选定EN实际版本/启用模块与frePPLe正式CE，再做E2同输入计划对照；edition/许可/适配成本不过门槛就淘汰，不默认自研。
4. 有当时可知历史快照后按已有方向设计E3滚动回测与库存策略仿真；当前不采用/不试验TSFM。PB人为±25%区间不是Conformal，阶段B尚未启动。
5. E4评估Agent语义/权限/幂等/过期审批/独立读回。任何具体生产写入或通知任务另行按范围授权。
6. Claude最新复核已完成，已修问题不重开；G0登记已冻结并复核三节；当前先由Claude修正报告桥表，等待3PL责任确认；之后再安排G1b，Codex审核输入manifest、逐行处置/数量守恒与C01–C25差异。取消/超额和pending互斥按来源规则核，不重开综述。Cursor成果待交付，不阻塞无争议验证。

## 工作区、提交与校验

使用已附着worktree与feature/codex-supply-chain-research；现有Draft PR：[301](https://github.com/keyapi/fzh-data/pull/301)。本研究文档在docs/plans/2026-10-20-codex-supply-chain-research/；当前研究成果提交可由git log该目录确认，P0基线dfded88e；前轮研究3d831924。后续92458fcd补历史接续/头程；dd2551ef补跨方案复审/共同框架/合成例；本轮补cd7a8a06关闭记录与两PR推进规则，当前提交由git log该目录确认。不要在原主检出混入其他人的未提交修改。

凭证扫描、文档BOM/frontmatter/本地链接与四类diff凭证模式检查已通过；移除两文件多余EOF空行后diff格式检查通过。新增仅本地合成例脚本，无业务模块/锁文件/生产数据改动；从固定ref导出的临时测试源码仅留本机临时目录，不提交。

本分支与#300都修改根index.md和docs/plans/index.md；合并需保留双方导航，再运行scripts/update_index.py。#300首轮仅看交接；本轮已定向读取e0975b97819cb967009260795b52c7ed18c04dc2的08/09/05/E1相关文档和代码。Gitee网页失败后用git只见main且与GitHub相同，未证明Gitee PR/私有分支没有新增。

## 额度与可选Astra审查

本轮保存前工具读数：5小时16%、周3%（共享窗口实际使用继续变化）。历史读数不作当前余额。额度共享且可能被别的会话消耗，续接必须刷新。本轮未使用重置额度。

Astra并非必经许可步骤；若用户手动切换，可直接审阅synthesis.md最后的审查提示。审完继续E1/E2；不需重新做泛综述。

可复制续接提示：

> 继续PR #301供应链独立研究，先读index.md、synthesis.md、assets.md和本checkpoint。P1–P4首轮报告已完成，不重做已核资产/泛搜索。优先裁定计划单位、生产数量和库存/供应语义，再按experiments.md做E1，核实际EN版本和正式CE后做E2。历史预测已在#304定位，先读history-handoff.md，不重复找被删会话；现阶段不采用TSFM。PJ头程接口未交付时保留具体接口未知，按freight-model/freight-connectors继续底层契约，UI后置。用便宜模型有界子任务，及时阶段提交；不修改生产、不外发通知。独立报告已固化，Claude定向复审及共同候选见claude-review/common-framework/decisions，Cursor待交付；优先按G0/G1对齐，不重做泛调研。
本轮来源固定Claude d784ef0f，G0 tag实际解析b23c319a；不把较早G1 slice tag自动当成最新范围。首选本地文件的行数与字段来自用户/Claude补充，不声称独立读取验证。PB约30涤麻SKU只是部分信号，G1不依赖历史库存/断货标签。

下次优先读baseline.md、g1-slice.md和review-mapping-process.md。Codex本轮更正与复审已完成，不派生取数任务；当前暂停G1b，待业务裁定及报告修正后再安排回放与审核。25例只是参照验证，不能当真实映射或库存成绩。

当前下一步：先由Claude修正匹配毛量/终端销售/皮壳消耗/补货责任桥表、退货事件类型和全输入去向；WayfairCG/其他3PL归属待业务确认前，本轮不推进G1b/实现，不访问生产。25例是合成参照；33,719不是Codex重算或已批准补货量。
