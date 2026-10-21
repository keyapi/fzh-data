---
okf: v0.1
type: Research
title: BOM 历史证据升级边界与 producer 反例
description: current_structure_only / historical_verified / historical_unknown 的证据边界、冲突规则、16 个 producer 正反例与阶段总结
tags: [supply-chain, boms, historical-evidence, codex, producer]
created: 2026-10-21
updated: 2026-10-21
sources:
  - https://github.com/frappe/frappe/blob/version-15/frappe/model/document.py
  - https://docs.frappe.io/erpnext/bill-of-materials
  - docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/en_family_poc.py
  - docs/plans/2026-10-20-codex-supply-chain-research/contract_examples.py
---

# BOM historical-evidence boundary

- Message: msg_3a226d426957
- Subject: 历史BOM证据升级规则与producer反例，含阶段总结与踩坑

历史结构证据独立验证报告（供保存到 #301）
任务task_cf5c2c11fb6a，基线d8c473fe / Claude PR #300；只读三份指定设计/domain/replay材料，检查固定提交相关语义并核对官方Frappe文档/源码；0生产查询、0文件写入、未实现/重复实现producer，未重审已接受R1/R2、E1-E4、行键、demand语义。

一、结论与等级边界
当前EN BOM只直接证明“抓取时，该具体BOM文档版本按其数量/UOM声明KS→PK/ND的结构边”，并不直接证明2026-04..09当时存在、当时可用、当时被选用或当时真实消耗；1:1也不证明销售等价/库存互换。建议同时保留current_state与historical_state，避免把三个标签误当成互斥事实：一条边可以当前结构已知、历史仍unknown。

| 输出等级 | 足够材料 | 不可外推 |
| current_structure_only | 抓取成功且内部一致的Item+BOM父单/children、角色/规范KS/方向/UOM/比例可验证，source/site/as_of/raw hash齐全；仅描述该次快照 | 不以今天active/default/disabled、creation/modified推导Apr-Sep；当前BOM残留停用内胆也只是“文档仍挂着”，不证明仍有生产资格 |
| historical_verified，范围=interval | 有可信内容锚点且可重建覆盖请求区间的BOM子行、输出数量、Item身份/UOM/角色及当时资格；完整变更/有效期/候选集证据排除区间内未解释冲突，断点处切段 | 验证区间外不延伸；“历史目录曾存在”不等于实际每单采用；结构不是实际耗料 |
| historical_verified，范围=transaction | 可追溯SO行→对应生产/供货单据→明确绑定的BOM版本；历史原始版本/当期快照或可信可重建内容匹配，且该关系在相关事件时间适用 | 只证明具体事件/批次，不推广整SKU六个月；SO delivery_date不是BOM选用/制造的发生时间，只有SO上的当前BOM名字也不够 |
| historical_unknown | 缺历史锚点、日志链/权限/分页不完整、只见当前BOM、仅有一个Version diff、有效期是猜的、事件绑定不可定位；若有当前快照可另记current_structure_only | 不当0、不当不需要内胆、不自动判非family，也不填满valid_from=2026-04-01/valid_to=2026-09-30 |

升级historical_verified的最小证据链：
1. 内容锚点：可信当期完整BOM/child快照或可校验的归档版本，带site/docname/child IDs/采集来源/时间/hash；Item身份、stock UOM与换算也需能对应到当时，而非只重建BOM数量。
2. 变化覆盖：从锚点到目标事件/区间边界，能够解释所有相关结构变更，包括增删child、父quantity、UOM/conversion、替代品、启用/停用、取消/改版以及相关历史候选BOM；日志/归档来源完整性的依据必须记录。两端相同快照不排除中间A→B→A。
3. 生效与记录时间：有可依赖的业务effective interval或交易绑定时间，和后补记录/采集时间分列；Version.creation是记录时点，不自动是业务生效时点。现在补写的“4月生效”若无当期可核证来源，只能作业务假设或restated解释，不伪装当时已知事实；回测还需available_at，不能把10月才知道的更正用于4月预测输入。
4. 适用范围：timestamp区间需时区与端点语义，整月历史窗口可表达[2026-04-01,2026-10-01)；当前consumer接口valid_to为包含式日期，producer序列化时明确转换为2026-09-30，不丢半天/断点。能证明单日/单事件，就只发该范围，不拼成整六个月。
5. 完整性：历史绑定若需该单实际BOM，不能用最新default代替；泛化族关系若有多个可能BOM，须逐候选裁决而非只取当前active/default。对有删库/迁移/改名/非审计写入风险而无法补证的范围保留unknown，不要求现在建设新审计系统。

Version/modified证据的充分与不足：
- Version diff + 可信完整锚点 + 子表/身份/UOM/状态的可还原链 + 完整性依据，才可以重建指定时段；单独Version清单/条数、空清单、一个before/after字段、只有最新版本都不足。查到日志≠日志覆盖所有写入；track_changes当下打开≠过去一直打开。
- creation早于4月只证明记录声称更早创建；modified早于4月也不能证明内容此后未改；modified在10月可能仅是成本变动，同样不能反向断言结构从10月才存在。可用结构字段指纹区分cost-only变化与结构变化，但full raw hash必须保留，结构投影规则也须版本化。
- 项目固定d8c473fe的EN_API/bom_fabric_qty_fix.py:90-94直接改BOM Item.qty/stock_qty并row.db_update，97-102与118-119还使用update_modified=False，足以否定“所有数量变更都会推进父modified”的默认前提；这不证明该脚本实际改过本批KS，也不能把它当作发生过的历史事件。
- 官方[Frappe version-15 document.py](https://github.com/frappe/frappe/blob/version-15/frappe/model/document.py#L1217) 的save_version受track_changes/ignore_version等条件控制；db_set可跳过modified更新。因此日志无记录不能证明无变更；实际生产版本/配置尚未查询，不能据官方分支断言本机审计设置。
- 官方[ERPNext BOM](https://docs.frappe.io/erpnext/bill-of-materials)的is_active/is_default用于启用与默认选用；它们不是整段历史的有效期证明。

二、冲突与领域规则
1. 冲突按canonical KS/组件role/时间段/应用事件分组。不同BOM只改成本、而所验证PK边/UOM/比例一致，不必制造该边的冲突；若同一时段对canonical、组件身份、角色或归一比例不一致，置conflict/pending，default/最新/first/last-wins均不能裁决。明确交易绑定可解该交易选用，但不能抹掉泛化层歧义。
2. 同一component复用多个KS是多对多事实，不必声称数据错；但当前“variant→唯一canonical KS”消费接口无法裁决时仍pending，保留候选边。别强剥后缀、按组+尺寸造内胆，或强制-Cover单码映射PK。domain-notes已确认-Cover可跨拆包/填充情境，前缀与结构不能证明终端别名。
3. 停用Item或inactive BOM：历史当时有资格且版本内容明确，可以historical_verified/current_planning_eligible=false；当前BOM残留已停用ND按领域是清理候选，不重新启用，不据此补内胆。今天BOM无ND只证明今天该BOM不含ND；“历史也无ND”须当时证据，不能由当前缺项倒推。
4. 同组件重复child行先聚合stock量；ratio=组件stock总量/KS输出stock量，两侧换算可验证、finite正数量与字段相容才可用。不同UOM缺转换/历史转换变过不明、输出数量缺失/冲突、替代料/损耗/多级路径未解释均pending。实际比例非1可以保留结构事实ratio≠1，但当前S02只接纳1:1，不能改数强凑1或直接判非family。
5. domain-notes明确KS成品BOM只有PK皮壳+ND内胆；SXBZCP#/PLBZCP#/USTXBZCP#为另一套填充/包装BOM，不含KS，不能代替KS→PK/ND关系证据。完整成品/FBA用料以后需叠加包装BOM；本次结构证明不声称已完成全部物料计划。

三、producer验收反例矩阵（可直接变成可重复离线fixtures；本任务仅给断言，不复制实现或宣称已跑producer）
H01 当前10月BOM KS-A→PK-A为10:10、active/default、但无历史：assert current_structure_only && historical_unknown && 不输出覆盖Apr-Sep的verified有效期。
H02 creation/modified均2026-03、Version查询空，但有可能update_modified=False直改：assert 不升级；Version空/403/截断分别留原因，不能当“未变”。
H03 可信3月31完整锚点 + 覆盖至10月1的完整可还原记录/资格范围，PK边/UOM始终一致、ratio1：assert historical_verified(interval Apr-Sep)；重复运行/候选顺序打乱应同结果。
H04 4月1与9月30快照相同，6月存在A→B→A或中间链缺失：assert 不能据两端相同认六个月verified；仅保留已证实点/段。
H05 7月1由PK-A切PK-B，转换前后均有完整证据：assert 两段，不输出唯一整窗映射；当前consumer整窗仍pending，不first-wins/last-wins。
H06 10月仅成本变动，完整历史重建证明结构投影不变：assert 可保留结构historical_verified；不能因modified新就否认所有历史，raw hash不同但结构指纹一致。
H07 6月12明确WO/SO行绑定BOM-v1，且有当期完整v1哈希和UOM：assert transaction范围verified，不自动给Apr-Sep；若只有BOM名字+当前同名payload则historical_unknown。
H08 当前default=新BOM、旧订单只给delivery_date无绑定：assert 不把default反填旧单；delivery_date也不充当BOMeffective_from。
H09 ND在5月确证使用、7月移除、10月disabled：assert 5月历史边可证且current_planning=false；7月后按证据无内胆，不能整窗加ND，也不能重新启用。
H10 两个同时可用BOM一个PK-A一个PK-B或ratio1/2，default=A：assert conflict/pending；增加明确事件绑定只解该事件，泛化冲突仍在。
H11 输出10、相同component分两行6+4→stock总10：assert ratio1；输出10/组件5→ratio0.5留结构事实但不入1:1已裁定集合；UOM换算缺失→pending。
H12 当前有效BOM/Item完整，但历史Item UOM从Box改Nos且转换链缺失：assert historical_unknown；不能用当前factor重算历史数量。
H13 只读到SXBZCP#/USTXBZCP#填充包装BOM，无KS→PK子边：assert 不证明S02关系；只留packaging领域证据。
H14 producer只覆盖20候选，当前BOM/Version权限或页数上限导致漏候选：assert manifest sample/partial，未读候选unknown；不把已读几份一致当全部历史BOM一致。
H15 可信锚点有child，后续Version仅保存价格diff且无法确认child变更覆盖：assert 历史仍unknown；若child前后完整和所有写入可追溯才升级。
H16 同一原始输入更换fetch时间/run_id、排序、分页切块不改变判决；仅改变current.active/disabled不能擦掉已证实历史，且仅改变历史effective断点应只影响对应区间。

四、最小输出与manifest建议（兼容d8消费者，少返工）
保留现有variant_evidence/1与variant-evidence/1、source/site、producer版本、payload/raw哈希等字段；不要替换已通过consumer。当前只抓Item/BOM时，evidence=structural + evidence_scope=current_structure_only；history unresolved另记historical_state=unknown及history_missing_reasons，不填写假历史valid_from/to或eligible_at_evidence=true，未裁定如实保留。
每条增加或作为诊断sidecar：
- observed_at/captured_at、current_bom_state；historical_state、verification_extent=point|interval|transaction、verified_intervals[]/covered_event_refs[]、history_gaps[]，业务effective_at与recorded_at/available_at分开；
- canonical_ks、variant_code、role、方向、normalized组件/output/UOM/ratio、candidate_boms完整列表与当前及当时资格分别记录；
- historical_basis_type（archived_snapshot / anchored_version_chain / pinned_transaction_revision），historical_basis_refs[]（Item/BOM/child/Version/关联单据的name/version/hash），anchor_hash、reconstruction/structure_rule_version；
- history_completeness（complete|partial|not_assessed）及依据/缺口，不用Version空列表自动设complete；resolution=consistent|conflict|unknown，reason_codes与candidate_count/read/failure去向。
manifest：明确sample candidates≤20的请求/已读/未匹配/冲突/权限/截断计数与具体私有清单，逐源页数和complete；current_structure_only/historical_verified/historical_unknown按code及边计数分开，历史覆盖范围与current范围分别统计；record/data/script/schema/rule哈希固定，run重复结果可规范化比较。
当前consumer d8c473fe P:333-348要求historical_verified且valid_from/to覆盖整轮。单事件/分段历史证据先放sidecar，不挤进单code唯一整窗记录；只有足够证明整窗同映射才输出该条可消费记录。这样producer今天可以完成current-only采样，历史升级以后补材料即可，不要求立刻写Version重建引擎或改consumer。

五、阶段总结与踩坑（请随报告保存/提交#301）
已定决定：d8无证据R1/R2提取审计已通过，后续不再重开；当前BOM与历史证据分开；KS→PK/ND为组件边，PK=皮壳/ND=内胆；1:1是结构用量而非销售/库存等价；producer先限额快照、缺历史就current_structure_only+pending；不自动重启停用内胆，不用包装BOM替代KS证据，不强制-Cover一对一；不改已验收consumer以迎合暂时拿不到的历史数据。
踩坑1 current/historical边界：抓取时刻、BOM业务生效、交易选用、回测当时可知是四个不同时间；单笔证据不证明六个月，两端相同不证明中间没变。
踩坑2 Version/modified不可靠：父modified可不变、Version可未开/忽略/缺链，项目已有直接更新路径；但modified较新也可能仅成本变化，别走另一极端把全部旧关系判失效；需锚点+覆盖+结构字段重建。
踩坑3 producer反例：H01/H02当前快照冒充历史、H04中间变化、H05跨期last-wins、H07同名BOM当不可变版本、H09缺ND/停用误补、H12用今天UOM回填旧单，必须进入可重跑负例；H03/H06/H07限定范围是正例，不能只写永远pending的测试。
未决项：真实site的Version可用性/保留范围/track_changes历史设置、可信历史快照位置与时间锚、BOM选择/生效规则、事件级SO→WO→BOM版本绑定、历史Item UOM变动、候选历史删除/迁移覆盖，目前均未查生产而不可裁决。后续在已有只读额度内按发现逐项补证；若不可恢复就保留unknown，另行记录业务假设，不把历史假设写成fact。
结尾交接：本任务交付的是证据判定规则与反例规格，不是producer实现或真实历史验收；当前可证明范围不因已通过SO审计门而扩大。源码依据/三份输入路径及官方链接已列，报告artifact为本Orca消息；无文件写入、无生产访问、无U01/旧T重审。