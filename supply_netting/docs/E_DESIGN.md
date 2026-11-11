---
type: Spec
title: E v2 SKU×客户×节点数量与时效视图
date: 2026-11-11
status: implementation-authorized
---

# E v2：按用户修正实现

## 1. 术语与最小交付

产品×仓池就是 SKU×客户，客户为波兰/USNJ/USTX。EN SO.customer 是客户，不是物理工厂仓。原始仓只作位置与来源。保留原 EN 物料、通途 SKU、平台 SKU 和映射，不能假设 EN 产品与通途 SKU 一对一。

最小交付是每 SKU(产品)×客户×节点的数量视图；缺单据不排除观测。节点账保留原始行，另导出 E_product_node_view 和 E_product_totals。UOM/形态是不可合并的附加维度；生命周期不删除任何数量。

- observed_total：所有已知观测量合计，明确 observed_non_additive=true，可能含同批跨阶段/多源重放，不能直接用作供给。
- confirmed_total：已证互斥、可叠加的量；无可证记录时为 null，不伪造 0。同时给 confirmed_complete、unconfirmed_rows 和 known lower-bound 属性，禁止把小计冒充整条 E 的总量。
- linkage_status：snapshot_unique / document_line_proven / export_only / unlinked / mapping_ambiguous。单据是增强，不是最小视图门槛。
- 当前 available 在 stock_key 唯一、同一计数单位、映射无歧义且没有拆包裹风险时可作为该节点已证量；跨 SO/DN/PO/快照仍需额度谱系，不能相加。

## 2. 映射与件套

E_sku_mapping 保留 en_sku、tongtool_sku、customer_raw、mapping_type、mapping_status、source。一个 EN 对多个通途 SKU 全部保留；反向多候选不任取。映射连接不能放大源行数或数量。多码是别名还是拆包裹尚无证据时记 alias_or_parcel_unclassified，并保留同客户观测，不合成已证成品数。

通途数量按用户确认是件数：suffix 1/4/6/9/12PCS 是销售套型，不能再乘 N。E保留 uom、pcs_per_set、set_sku、base_sku、pack_basis；套型解析只增加规格元数据。平台销量为套时，只有已证套型才可换算成件；原生 EN 套单位保持套，不能直接与件相加。Product Bundle 多种组件是组成关系，不能任取首组件当 base SKU。C旧表的套单位/后缀乘数单独保留为 legacy 字段，差异列入对账；不修改 C 源表，也不把旧换算当 E 事实。

## 3. 客户级生命周期

权威表 lifecycle 以 SKU×客户为键。lifecycle_status 允许 unknown_pending/active/seasonal/clearance/discontinued/blocked；unknown_pending 是缺权威状态，blocked 仅明确封禁。EN disabled 独立保存，绝不触发停售，也不删除波兰数量。

销量证据只生成 inferred_status=active_candidate/dormant_candidate/discontinued_candidate，evidence_status=provisional。2026有销量可生成 active_candidate；连续12个月显式完整零观测才生成 dormant_candidate，缺行不补零。用户指定 KS0307 波兰2026=126、US=0，KS0198 波兰2026=93、US从2025起0：作为用户提供的型号/市场级证据保留，不复制成每个变体的销量。

D6接入规则：仅权威 active，或权威 seasonal 且当前位于已登记季节窗时 replenishment_eligible=true。候选与 unknown_pending 只进生命周期待确认表；clearance/discontinued/blocked不自动补。E仍显示全部节点量。本轮不改其他 worktree 的 D6，只输出可消费准入字段。

## 4. 节点与单据增强

available/intransit_observed/waiting_observed/defects/returns、SO未交付均保留。SO明细与汇总只核账一次；逗号拼接SO集合不是新订单。补接本地历史DN明细及开放PO时，按客户/实际仓附单据，SO关联缺失仍显示数量并标 export_only/unlinked。历史DN是累计交付证据，不冒充当前在途余额。PO和库存快照没证明互斥时只入 observed_total。

已证互斥仍沿用 root_order_line×allocation_id×SKU×客户×UOM：订单净量=未DN+DN未发+已发未收+已收。收货事件不能再加 available。同批多包裹必须有分配关系，不按SKU/数量相近自动关联。波兰外部订单已售未扣仍是独立负向承诺节点，缺数量为unknown。

## 5. ETA是必要交付，不以一句缺资料结束

时效分三档：
1. confirmed：已证节点/批次连接到来源明确的ETA、实际发运/收货里程碑；保存来源、观测时间。签收只结束在途，不自动证明可售上架。
2. estimated：已证本行PO预计到货或已关联Shipment ETA；保留source日期、过期/逾期标记，不能称确认。
3. scenario/unknown：无单据连接也提供可复算的规划情景，独立保留，不把同SKU的Shipment表头任意配给当前SO。

SO情景用该客户近六个完整月、去重复SO/DN样本的生产时长，加同客户/路线/模式的头程样本，独立重采样只是一条明确假设，不缩尾、不将两个p90直接相加。输出每模式新订单总交期分位、已有SO条件剩余到仓分位、样本数、退回层级、假设与low置信度；仅已完成运输样本有幸存偏差，不能宣称95%服务。模式缺样本则保持unknown，不从美国替波兰编造路线。

若提供 SKU×客户需要日：latest_order_date=need_date−情景总交期分位；review_due=缺资料的现在，催单建议在预计迟到/承诺逾期时触发，具体催量与催后ETA仍需物流/工厂确认。到货前不可避免缺口与可控补货期分开。只有节点qty可见，不等于已满足服务约束。

最小正式时效数据：SKU×客户×阶段与状态时点；剩余数量和必要映射；SO/DN生产里程碑；PO/Shipment发运/预计到货/收货及线路；需要日。最小视图不因缺这些而缺行，时效可输出unknown和明确补证动作。

## 6. 产物、验收与边界

保留原始 E_nodes 与 C legacy available view；新增 SKU映射、套型映射、SKU×客户×节点双总量、跨节点双总量（observed非加法）、客户 lifecycle/待确认、ETA情景。缺节点覆盖仍明确unknown。源哈希前后相同、源行数/量守恒、映射不放大、库存件数不乘套数、同产品不同客户状态独立、未知生命周期不自动补、单据缺失量仍展示、统计/情景ETA不抬升为confirmed，均须有测试。

运行：uv run python -m supply_netting.e_nodes --as-of 2026-11-11T23:59:59+08:00 --output-dir D:/Work/fzh-order-store/analysis/E_v2_20261111

可选权威lifecycle CSV：sku,customer,lifecycle_status,season_start,season_end,evidence。缺省unknown_pending；用户指明的销量候选写入evidence而非权威状态。可选needs CSV：sku,customer,need_date。原始源与生产系统只读，不使用通途MCP。
