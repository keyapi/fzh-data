---
okf: v0.1
type: Reference
title: G1b第四轮修复关闭与family批量PoC交接
date: 2026-10-21
reviewed_ref: f14c97097b054cd2e55353c3baa89a8446c35d46
status: ready-for-family-poc-one-se-edge-remains
---

# 结论

**T01–T04、T06可以关闭对应实现缺口；T05主要失败路径已修，仅余一个混合SE失败边界U01。E01–E04的内容接受，可以进入family只读批量PoC，不再等待泛调研或新一轮架构批准。** U01可与批量抽取准备并行修复，但不能把未修路径的生产量当已验证事实。

固定[Claude #300 f14c9709](https://github.com/keyapi/fzh-data/tree/f14c97097b054cd2e55353c3baa89a8446c35d46/docs/research/supply-chain/2026-10-20/claude)，只核对相对f4797aa0的T01–T06与15增量。未读原始业务文件/凭证、未访问生产/浏览器/任务计划、不改Claude文件。上一轮见[第三轮复审](review-g1b-round3.md)。

## 已关闭与正例

| 项 | 本轮结果 |
|---|---|
| T01 | 已返回且校验为0的SKU保持observed_zero；完整仓中未返回SKU为missing、supply=None，不再进确定零供给。合成正例通过 |
| T02 | hash失配拒绝读取，匹配可读；run目录与最后发布日manifest的改动方向接受，生产调度/实际归档不在本轮验证范围 |
| T03 | A＋不存在B的请求保留2仓，missing_requested单列且complete=false。正例通过 |
| T04 | 一仓完整另一仓失败时，global=false不再使健康仓失去complete。转换→load_stock正例通过 |
| T05已定位缺详情 | list阶段work_order被保留，WO量None；只有无法定位失败记录时也能让没有成功SE的WO量None。这两个正例通过，但混合情形见U01 |
| T06 | 5/6月partial窗口不进headline的no_supply/below_2。执行main原AST过滤片段正例通过 |

共**7个修复正例**。新129 observed_zero / 2 missing / 192低覆盖 / 127 unknown暂按Claude报告登记，未由Codex取真实数据复现，不称G1验收。差7、DN键、BOM歧义与业务改名等此前关闭项不重开。

## U01：唯一剩余P1——SE混合结果仍可绕过unknown

固定版本`g1b_en_extract.py:367–375`先判断“该WO已有SE且没有该WO的bad_se”，之后才判断全局se_error。

最小反例：

1. SE-A详情成功，属于WO-X，成品5；
2. 同批SE-B详情失败，且list阶段也没有work_order；fetch返回`missing_doc_without_work_order`；
3. 因SE-B无法分配到任何WO，WO-X的se_for_wo只有成功SE-A；
4. 汇总优先走:367，仍输出`se_status=ok, se_finished_qty=5`，忽略了同批无法定位失败SE可能也属于WO-X。

[g1b_round4_probes.py](g1b_round4_probes.py)使用真实fetch函数与main原WO汇总代码片段复现，不是重新手写模拟该判断。**5最多是已知小计，不是已确认完整产出。** 对有无法定位失败SE的候选集合应先施加查询完整性闸门，或显式维护每WO完整状态；无法排除影响时该WO量unknown，已知5可另留known_subtotal。加“成功＋未定位失败”回归后重跑已有本地输入即可，不要求重新取生产。

## E01–E04：内容接受，开始实施前整理一个入口

15§2.5–2.8已覆盖版本化family全集、包装/历史映射、modified/业务日期分离、父单重拉与tombstone、提交后推进水位、不可变快照与ETA身份、同cutoff/UOM回归。333/56仍仅为查询样例，PoC尚未实现；这一区分正确。

**P2文档一致性**：15§2.1/2.2仍留旧`snapshot_date`身份、`eta_bucket`主键、三种日期混作水位和`float_sales_order_line`。无需再扩写新章；直接将这两节统一到§2.5–2.8，或明确标为已废弃历史，给实现者一个有效定义。此整理不阻塞family manifest/本地回归准备。

**P2旧hash例外的证据等级**：`--allow-missing-hash`是用户场景中的显式兼容，不等于旧manifest已获历史hash验证。建议产物保留`integrity_mode=legacy_unverified`与例外来源；语义/验收报告分开记录数值完整性与文件历史完整性。不能把本轮计算的actual hash当成过去已承诺的expected hash。新run严格模式继续默认拒绝缺hash。

## 下一步交接

- Claude：先修U01、统一15旧定义；推进family只读批量PoC，按family manifest→分页raw→父单/子行→staging事实→回归/manifest顺序实现。先本地最小回归，再依用户既有授权运行；不扩大到全品类或生产写入。
- PoC交付：固定代码SHA、family manifest版本/hash、每DocType查询/页数/行数与source_id去向、水位提交/失败重跑日志、与已知试点行级差异、unknown/异常和同单位守恒。Wayfair后台与旧仓迁移继续独立pending，不阻塞PoC。
- Codex：下一轮审核U01与**实际PoC差异和输出**，不再对已关闭适配器问题来回写综述。数据库/计划引擎备选仍按此前裁决条件保留。

原35个契约例不变且通过；本轮7正例＋1剩余反例仅为离线合成验证。没有复现129/192真实统计，没有检查自动登录、05:17任务或API补跑。
