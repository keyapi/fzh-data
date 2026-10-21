---
okf: v0.1
type: Reference
title: G1b第三轮修复复审与批量ETL实施边界
date: 2026-10-21
reviewed_ref: f4797aa06bf5bb9168c02bc3841a31b0549ea0ed
status: bulk-direction-accepted-adapter-gaps-remain
---

# 本轮结论

**接受批量ETL方向，也接受大部分上轮修复；还不能整体关闭RR01–RR08或宣布G1验收。** 当前最关键的两处事实错误仍是：完整仓中未返回SKU被当零、SE详情失败丢WO关联后汇成零。这两处应先修；批量family manifest/增量规则可同时补，不重做综述、不等待Wayfair调拨数据。

固定[Claude #300 f4797aa0](https://github.com/keyapi/fzh-data/tree/f4797aa06bf5bb9168c02bc3841a31b0549ea0ed/docs/research/supply-chain/2026-10-20/claude)，审g1b_round2_response、四个库存/转换脚本、en_extract及15-full-family-etl。只读Git材料；没有读取原始xlsx/JSONL/凭证，没有登录、访问API或修改任务；自动登录与补跑成功依Claude报告登记，不称独立验证。前轮见[第二轮复审](review-g1b-round2.md)。

## 1. 已验证修复，不重复返工

| 前轮项 | 本轮处理 |
|---|---|
| RR01旧complete并集、冲突不降状态 | 两个合成正例通过：新incomplete不继承旧complete；冲突使该仓incomplete。仍需下节T04逐仓信息贯通 |
| RR02空数变0、冲突first-wins | 实际daily转换正例通过：缺数量bad且incomplete；异值整键丢弃并conflict，不再保留首值当确定库存 |
| RR03未知响应假空仓 | daily.rows_of未知结构抛错、合法空数组可用；业务码严格200与截断标记静态确认。该响应形状子项关闭 |
| RR04缺首末工序用后道替代 | 合成route cut→sew但只存在sew卡，first=cut且qty=None，修复成立；optional返工工序不能擅自忽略。JC有效状态/同工序重叠卡仍需源明细验证，不把辅助last_card当契约末道 |
| RR05 SE未知处理 | 增加SE行ID/单位/状态，已知WO的bad SE可保留unknown，这部分接受；missing_doc边界T05仍未关闭 |
| RR06 Wayfair来源 | Tongtool快照即使complete也为unknown_authority，合成正例通过，不进入已确认缺口。`authority`字段当前固定写期望后台名，建议另记actual_source与required_authority，别让参考API行看似来自后台 |
| RR07缺文件 | 合成缺文件返回complete=false，修复成立；请求仓不在manifest中的T03仍需修 |
| RR08坏数量/缺窗口 | 非有限/负/分数不纳入毛量的实现接受；但headline过滤未用window_complete，T06仍未关闭 |

旧DN自身键、差7分解、BOM歧义隔离、用户确认改名继续关闭相应子项，不再重问。131/194/127仍仅为Claude该批报告，未由Codex重跑业务数据；新增presence规则落地后需更新该统计。

## 2. 六个剩余反例（固定f4797aa0已离线复现）

脚本前缀为`experiments/g1_contract/`；P1影响事实结论，P2影响完整性/报告资格。反例不意味着本批真实数据已触发。

| ID | 级别 | 证据、影响与最小修复 |
|---|---|---|
| T01 | P1 | coverage.py:432仍对不存在的(branch,sku)补全零，:441只凭仓完整标sampled_complete。与用户及15§2.3“API未返回=unknown”直接矛盾。保留presence和quantity_status；只有实际返回且校验通过的0才observed_zero，完整分页不证明不存在的业务SKU库存为0。未返回SKU不得进无供给/低覆盖计数，含在途与on_hand字段应为None或明确非权威值。随后重算131/194/127，不假设会变化多少 |
| T02 | P1 | converter:101只算当前hash，未对manifest的file_sha256校验；daily:163仍写固定仓文件，:187逐个os.replace，:284再替换manifest。单文件原子不等于整批原子，同日重跑中可读到“旧manifest＋新仓文件”。合成expected hash全0但实际不同仍complete=true。使用不可变run_id仓文件，manifest最后发布；读取时核期望hash/行数/仓ID/批次，失配拒绝，不用重算新hash替旧manifest背书 |
| T03 | P2 | converter:83–84先按wanted过滤entries，:170再从结果生成requested；请求A＋不存在的B时，B消失且complete=true。requested应保留用户原请求，missing_requested单列并失败/incomplete；这与每日producer端已补的请求完整性保持一致 |
| T04 | P2 | load_stock:317只用global complete，忽略转换产物complete_warehouses/by_warehouse.complete。A仓已完整、B仓失败时，A也被降成不完整。逐仓绑定选中文件的该仓complete，global只作整批摘要；T01的SKU presence又是另一层，不能互代。反例只证明误降级，不称会虚增确定供给 |
| T05 | P1 | en_extract:188的missing_doc记录未带list阶段已知work_order；:353–356只把有work_order的SE归组，:373把该WO无记录当0。已用真实函数＋main中的原AST汇总片段复现missing_doc→se_finished_qty=0。失败记录保留列表已知WO，或维护WO级查询完整性；若不能定位则相关候选WO一律unknown，不可降为“已知没有SE” |
| T06 | P2 | coverage.main:518起no_supply/no_demand/below_2只查supply_status，不查需求window_complete；coverage_eligible只加在branch_cov，未参与headline过滤。合成5/6月窗口仍进无供给和低覆盖计数。给SKU行与过滤共用统一eligibility；partial输出可保留，但不能混入完整窗口统计 |

不要求为这些问题重拉生产：先用负例验证，再用已有本地输入重跑。对真实库存是否缺货、哪些SE有读取失败，不在本轮缺乏原始数据时猜测。

## 3. 15-full-family-etl：方向接受，实施前补齐五个小契约

### E01 family全集与批量完整性

333行/56SO只证明一次按两个组查询可用，不证明全族、全页或历史完整。现有试点已知SO行可能卖PK#而非KS，物料历史组也会变化。定义带版本的family manifest：KS leaf/规范物料/客户码、PK#/ND#等角色映射、历史停用/改组、纳入/排除/pending原因。通过父单批量重拉后按**行**筛选，保留非family同行的去向，不因父单被选中就纳入全部行。

把两个组筛选、manifest item_code并集和旧9个成功客户码作交叉覆盖核验；不能因为不在两个当前组就漏掉已知试点。批量后按原单/行ID复用，不需逐客户码1,486次。333/56、原始页数、筛选后行数都要写manifest。实际EN父单明细字段按本仓库接口核对（既有代码遍历items），不把文中的order_items假定成真实API字段。

### E02 增量与失败重跑

每个DocType明确变更发现字段和cursor：以modified发现旧单迟改，transaction/posting_date用于业务日期而不能互换当增量；稳定排序使用(modified,name)，设置重叠回读及run_started_at上界。命中父单后整单重拉子表，删除的子行用失效/tombstone处理；保留取消、amended_from、移出family与状态修改。仅幂等upsert新行无法清理消失的旧行。

完整落raw/staging、校验并事务提交事实后才推进对应水位，partial/失败不推进；跨来源不装作一个事务快照。周期对账可发现硬删除，无需搭完整CDC服务。若源不保证子行修改带动父modified，需明确验证或以子表变更/周期全量补偿。

### E03 不可变事实键

`fact_inventory_snapshot`不能以(snapshot_date,warehouse_id,sku)作唯一历史身份：同日多次采集会覆盖，API与浏览器也会冲突。建议保留(source,snapshot_id/run_id,warehouse_id,sku[,必要库存维度])及as_of，另设“选定合格快照”视图。日期只作分区/筛选，不作多批次身份。

`fact_in_transit`的eta_bucket是可变属性，不应入稳定主键；一次ETA改桶不能留下两笔供应。用source/doc/line/运输腿或lot的稳定身份，ETA及revision/observed_at另外版本化；没有单据行的通途汇总intransit应独立存为snapshot视图，不能编造doc_id，也不能和DN/物流事实重复累计。`float_sales_order_line`笔误可顺手更名fact，不影响核心讨论。

### E04 守恒与增量回归

“SO→DN→SE”不是三层数量直接相等。按相同cutoff、规范单位和链接粒度检查：有效订单/取消/正向发出/原未交/超发，退货单列；工序报工、SE入库、DN发运分开，原库存与在途是互斥余额。首末道和SE unknown不因另层已知就补0；组件与成品经已确认配方/UOM换算后才对账。

实施前最小回放包：旧日期SO后来修改、取消/改单、删子行、移组、相同modified跨页、失败重跑不推进水位、ETA修订不增供应、同日双快照、缺SKU与explicit0、SE详情失败。可直接作为本地PoC验收，不要求先获取新的业务参数。

### E05 分阶段推进

接受raw→staging→fact/dim→metrics结构，不锁定数据库或引入复杂平台。先将本次已知事实错误修完，同时补15的manifest/键/cursor/重跑规则，然后实现**family只读批量PoC**，校验已知试点及全族去向后再扩大到全品类。Wayfair实盘/调拨归属、旧迁移凭证继续独立pending；无需再次等待Codex批准才能修复或准备PoC，也不构成新的生产权限。

## 4. 证据与交接

[g1b_round3_probes.py](g1b_round3_probes.py)复用既有离线AST选择器，固定f4797aa0，仅合成临时文件/stub，无业务模块导入或API。实跑**8个修复正例通过＋6个剩余反例复现**；SE反例包含main的原WO汇总代码片段，避免只测局部函数。旧35契约例源码不变，仍35/35。

一位gpt-6-luna子Agent独立复核15与既定08/EN代码，主Agent核定family完整性、增量和键的建议。自动登录凭证位置已知，不读取/搬动/打印，不让用户再次提供。此处评审不验证cookie失效后登录、09:46补跑、下一次05:17调度或原数据131/194/127。

给Claude：先修T01/T02/T05和T03/T04/T06，补15的E01–E04；附负例与已有输入重跑差异，不重做泛调研。已关闭子项不再来回改；批量方向继续，G1真实契约尚未验收。
