---
type: Reference
title: 旧 ABCDE 能力 → supply_copilot 新入口迁移状态
date: 2026-11-24
status: audited
scope: 只读审计；只列能力与证据，不含客户明细/凭证
reviewed_commit: 453498fa
checked_head: e12a9a13
---

# 旧 ABCDE → supply_copilot 迁移状态

**结论先行**

1. **迁过来的是“入口 + 证据读取”，不是旧 ABCDE 的决策内核。** D 的简化预测（AutoETS/MA3/naive + p50/p90）、C/E 的部分实时读取（库存快照、开放 SO/PO）已接入；A/B 当前范围、分型与每键选型、current-owner 重述、60cm 历史桥、删失接线、周计划**未迁移**。复制了文件 ≠ 能力已迁移。
2. **外部复审 P1 的处理进度**（冻结提交 453498fa → 当前 HEAD e12a9a13 含 3cfb0ada）：P1-1（SO 加进需求）、P1-2（同批相加）、P1-3（有 ETA 即按时）已做**粗修复**；P1-4 只修了“旧文件复用 + EN PO 身份”，**通途 PO 源与 branch/run 原子刷新仍缺**；P1-5/P1-6/P1-7 未修。
3. **现版可作“今日候选 + 解释 + 不可执行原因”**，不可作“可信下单量”。对外不得称“完整迁移”或“90% 服务”。

> 审计基准：`D:/Work/fzh-order-store/analysis/external-review-20261124/review.md`（冻结 453498fa）。
> 本表核对当前 HEAD e12a9a13；旧资产为 `D:/private/demand/sc-data/data/` 下 D3b_v3_11 / D5_v6_8 / D6_v6_22 / D6_v6_24 / service_policy.csv / sku_map.tsv。

## 1. 迁移状态表

状态口径：**已接入**＝在 live/decision 路径实际消费；**仅参考**＝数据或代码在包里但决策不消费；**未迁移**＝能力缺失。

| # | 能力 | 旧实现/版本 | 新入口状态 | 证据（文件:行 / 命令 / 产物） | 对决策的影响 | 下一步 |
|---|---|---|---|---|---|---|
| M01 | A/B 当前范围（active/owner/归属） | D3b v3.11 `3_分类` 1,749 键＝波兰 735／美中 533／美东 296／CG 178／其他 7；US 需求按 current-owner 重述（owner-known 281,490 件 + unassigned 31,033）；USNJ 试点包 299 个归属产品→296 行建议 | **仅参考**：decide 只遍历 D6 v6.22/24 的 1,571 行，按池过滤（USNJ 296）；无 B 归属确认、无 lifecycle 过滤 | `supply_copilot/decide.py:727-734`；`supply_copilot/recommend.py:33-40,49-53`；D6_v6_22.xlsx#1_全量动作 1,571 行；`README.md`「当前 CLI 未暴露 B 确认流程」 | 新 SKU、新 owner、新归属不自动进入输出；“当前全部 active 范围”无法回答；旧 D6 名单就是天花板（复审正文“仍遍历旧名单”） | 把 D3b/B 归属 + E_lifecycle 做成 build_demand 的范围过滤，并输出“旧 1,749 → 当前”差数报告 |
| M02 | 60cm 历史桥（KS0001→KS0248） | D3b `1_映射桥` 2,649 行（唯一 2,363／未匹配 253／多候选 33）；60cm 专项 26 个 KS0001-*-60 键：6 键合并 2,615 件、20 键 kept_no_target 4,001 件，总 6,616 守恒；D5 v6.5/6.6 60cm 版 | **未迁移**：rebuild/forecast 按通途 SKU 独立建模，无 successor 拼接 | `D3b_v3_11.xlsx#1_映射桥`；`60cm_287_reconciliation_v8_20261107.json`；`supply_copilot/rebuild.py:262-293`；`self_fulfilled_demand/forecast.py:392-397` | 60cm 新品历史被低估、老品尾巴不断；分型与分位建立在断裂序列上；多原 SKU 预测相加 ≠ 先拼产品历史再建模（复审 P1-5） | 在 build_demand 前做 SKU 血缘拼接，保留旧键→新键对账与数量守恒 |
| M03 | 需求分型 | D3b `3_分类` demand_pattern：lumpy 491／intermittent 410／smooth 357／no_demand 222／new 147／obsolescent 67／short 55；含 ADI/CV²/SBC 与 train 版本 | **未迁移**：只按历史长度套 T20 规则，无分型 | `self_fulfilled_demand/forecast.py:16-22,243-290`；D3b#3_分类 | 间歇/块状/退市/新品用同一规则；无法解释“为什么这个键用这个模型” | 先把 demand_pattern 作为证据列接入，再按分型给候选模型集 |
| M04 | 每 SKU 选型（SBA/TSB/Croston/AutoETS/snaive/MA3/naive） | D3b adopted_model：none 901／snaive 242／naive 160／ma3 123／theta 104／ets_aadn 57／ets_ann 54／ets_aaa 42／croston 34／sba 32；D5 model 另含 tsb 78；每键 holdout_wape + `4_回测_asof` + `15_趋势诊断` | **未迁移**（仅规则基线已接入）：n<3→naive、3–7→MA3、≥7→AutoETS（≥24 月才 season_length=12）；回测只作透明、不换型 | `forecast.py:16-22,243-290,183-191,494-545`；`supply_copilot/rebuild.py:414-423`；D3b#4_回测_asof | 间歇/块状需求用 AutoETS/MA3 可能系统性偏；旧“每键选型 + 留出回测”证据链丢失；不可称“沿用旧模型” | R2 同口径对比旧 D5／新 AutoETS／SBA/TSB/Croston/Theta，按累计误差、偏差、覆盖、缺货/积压决定 |
| M05 | 分位档 q85/q90/q95 | D5 `1_预测` 三档 q85/q90/q95（3,498 行＝1,749 键×97/157 天）；`3_服务水平` 10,494 行（键×horizon×level）；`service_policy.csv` 1,749 行（ABC/XYZ、preset、service_level_prior、quantile、override） | **仅参考**：新只出 p50/p90；decide 直接取 p90 当需求；service_policy 只读取 canonical_uom，分位档被忽略 | `supply_copilot/decide.py:459-480,628`；`D5_v6_8.xlsx#1_预测,#3_服务水平`；`service_policy.csv` | 把 q95 换成 p90 同时改了用量政策，不能当界面改名；后台 q85/q90/q95 与 A/B/C 分档没有进入决策 | 保留后台档位，界面显示“基准/更多缓冲”并可展开依据 |
| M06 | 分位校准与服务口径 | D5 `4_时间验证` 有回溯覆盖（97 天：q85 0.857、q90 0.904，basis=retrospective only）；`3_服务水平` calibrated＝“否：回溯历史覆盖，非服务承诺” | **未迁移**：p90 来自 ≤4 个一步回测原点的同月残差上界，未验证 60/90/120/180 天累计需求覆盖 | `forecast.py:586-611,689-706,183-185`；D5#4_时间验证；复审 P1-6 | p90 是未校准上侧情景，**不等于 90% 销量满足率或 90% 不缺货概率**；对外“约 90% 服务”超证据 | 在 L90 累计需求上回测覆盖率；对外只写“保守档（名义 90% 分位，覆盖率未验证）”；档位由缺货/积压代价与保护期决定 |
| M07 | 删失/断货 | D2b v2：1,617 键中 363 键修正，观测 37,209→43,076（+15.8%），为上界情景；D5 v6.7 主链不做删失补偿，只作验证剔除 | **仅参考**：`censoring.py` 适配层存在，但 `ForecastConfig.censoring=False`，rebuild 未传 flags | `self_fulfilled_demand/censoring.py:1-11`；`forecast.py:194`；`rebuild.py:414-422`；`stockout_censoring_audit_20261109.md`；复审 P1-7 | 断货月按观测低值训练→预测偏低；少数键偏差可达 1.4–2.7 倍；复制了删失研究不等于生效 | R1 把删失 flags 接入 rebuild（默认保守档），保留“观测=下界”的可审计统计 |
| M08 | 缺月/零销/未知 | 旧链区分不足月、删失月、no_demand；不足月不进拟合 | **未迁移**（缺月→0）：首末完整月之间缺失月补 0.0；完整月边界按全表最早/最晚成交日判定；零销=0；只有无完整月才 null | `forecast.py:337-360,392-397`；复审 P1-7 | 中间缺资料月被当真实 0；某 SKU 自身月底无成交不会被标不足月；“没算/没卖/断货”仍混在一起 | 把“未知月／缺资料月”与“真实 0”分开；不足月按 SKU 自身边界判定 |
| M09 | 当前 owner 重述 | D3b v3.5+：唯一 owner 承接，多 owner→US_unassigned；US 281,490 件按 owner 重述，迁移 84,343 件/181 产品；预测用 current-owner、回测用 as-of，两套序列分开 | **未迁移**：build_demand 用订单行历史发货仓→canonical_warehouse（as-of 池），无 owner 重述 | `D3B_V35_OWNER_RESTATEMENT_TASK.md`；D3b#10_责任重述审计 1,152 行、#9b_责任重述对账；`rebuild.py:226-242,337`；复审 P1-5 | 新品/迁移产品按历史仓预测，与当前责任方不一致；新预测实为 as-of 口径，与旧 D6 current-owner 不可直接比 | R1 在 rebuild 前端接 owner_map，输出 current-owner 与 as-of 两套序列并分别标注 |
| M10 | 仓份额 | 旧 B 政策：唯一 owner／有证据才拆双仓；D3b `13_双仓责任与份额`（dual_rule=180d）；退货跟原订单 | **未迁移**：SKU 级预测 × 最近 3 个完整月各仓销量占比分配（`last_3_complete_months`）；无近 3 月销量则 null | `forecast.py:1070-1104`；D3b#13_双仓责任与份额；复审 P1-5 | 份额法会把预测摊到已不负责的仓；与 owner 政策冲突；跨仓调拨/双责无证据 | 份额改为 owner 政策下的证据化分配；无证据不摊派 |
| M11 | SO 方向（分公司 SO） | D6 净需求＝q95 − C/EN/PO/SO/CG（SO 当供给）；E v2 曾把 3 张波兰 SO 并入 stock_wait | **已接入（部分）**：SO 不再加进需求，改为上游条件供给；`incoming=max(intransit, po_on_time, so_qty)` | `decide.py:578-585,594-595`；3cfb0ada；`tests/test_decide_supply_semantics.py` | 修掉复审 P1-1；但 SO 只作条件供给，`max()` 无批次键时是同批粗保护；SO 客户归池靠 customer 名映射，未归上的行只计数 | 用 SO↔DN↔package 单据键做批次互斥，替代 max |
| M12 | 生产/在制（WO） | E 设计含 WO/在制节点；E 复核结论“在制（WIP）：没有” | **未迁移**：`fetch_chain` 能拉 WO，但 decide 不消费、无 CLI | `supply_copilot/en_live.py:611-700`（WO 节点，仅 tests 调用）；`E_REVIEW_RESULT_20261111.md` P1-1 | 在制/待产不计入供给，缺口偏大；无法回答“何时到” | 把 WO/在制作为独立节点接入 E，带 planned_end/expected_delivery |
| M13 | DN/发货数量 | E 里 DN 无数量，只参与 ETA；新旧均承认 SO↔DN 关联不完美 | **仅参考**：`fetch_chain` DN 节点有 qty，但 decide 不读、无 CLI | `en_live.py:705-740`；`E_REVIEW_RESULT_20261111.md` P1-1 | 不知道“已发未到”；与 SO 余额可能重复或遗漏 | DN 作为 in-transit 事实接入，按单号与 SO/PO 互斥 |
| M14 | Shipment/在途 ETA | ZMT/EN shipment 快照分段；E nodes 有 eta/eta_status/eta_basis | **未迁移**：库存快照只有 intransit 总量，无批次/ETA；Package 节点仅按订单号/tracking 精确查 | `en_live.py:316-395`（intransit 总量）；`E_ARCHITECTURE_PRINCIPLES_20261111.md §5` | 在途只能当条件供给，无法判断按时；不能分“今天下/下周下/空运/催” | 接 shipment segments + ETA 分布，输出 eta_basis 与置信度；无依据标 unknown |
| M15 | 通途 PO / EN PO 身份 | D6 `PO追加(去重)` 来自通途未收队列；PO/DN 审计 20 键仅 3 个有 PO（140 件） | **仅参考**：默认 `fetch_open_po` 是 EN Purchase Order（EN 物料码，非通途成品采购单）；`supply` 写 `po_open.tsv` 不含 eta；可另传 `--po-tongtool` JSONL（status 0/1/2、willArriveDate） | `en_live.py:505-563`；`decide.py:265-342`；`cli.py:192-199`；复审 P1-4 | 默认 live PO 多为物料仓/非成品，过滤后常为 0；无 ETA→po_on_time=0→PO 不计入 expected；不能称“PO 已接入” | 以通途 `purchaseOrderQuery` 为默认 PO 源，透传 ETA，按单号去重 |
| M16 | CG 抵扣 | D6 按 SKU owner 抵扣 USNJ/USTX，CG 池只观察；仅 eligible 且非 stale 可抵；max(cg_buffer, 可调拨) 不求和 | **仅参考**：实时 `WayfairCG-*` available 作上界，再 `min(live_cg, d6_cg)` 封顶；无 D6 值则 0（live_no_policy） | `decide.py:535-545`；`live_rules.py:250+`；复审 P1-4/限制 | 规则未确认时只保守封顶；不虚增抵扣，但可能低估可用缓冲；可执行性常因“CG 未确认”为否 | 把 eligible/stale/owner 规则落成显式策略，单列节点，不与 SO/在途求和 |
| M17 | 批次去重/净额 | `supply_netting.net_all`：批次键、跨阶段同批只计一次、FBA 分配排除、退货仓角色排除；D6 PO 已去重 | **未迁移**：只按仓库前缀汇总；`incoming=max(...)` 是粗保护；`demand_netting` 只登记哈希 | `decide.py:25-33,580-583,885,902`；复审 P1-2 | 同批在途+PO+SO 仍可能重复或漏计；数量级不可当净额；只能说“上界保护” | 接批次键（PO/DN/SO/package），输出 observed_total 与 confirmed_total 两个总量 |
| M18 | ETA 与需要日分桶 | D6 按需要日/下单日排程；E 的 ETA 带 basis | **仅参考（日期仍是 D6）**：需要日/下单日沿用 D6；有交期时按 D6 计划交期倒排（date_source=d6_need_minus_d6_lead）；PO 仅 ETA≤需要日计按时 | `decide.py:507-519,553-558,611-614`；复审 P1-3 | 过期下单日只能标 past_due，不能重排；live PO 无 ETA 时 P1-3 修复不生效；“用今天重跑”≠重新规划可靠可售日 | 按实际路线交期 + 需要日重算；ETA 缺失标 unknown |
| M19 | 刷新一致性（branch/run/as_of/manifest/旧文件复用） | D6 包有 manifest/as_of/sha；旧流程要求刷新前后保留两套 SHA 与差异表 | **已接入（部分）**：`supply` 按分公司目录写 + manifest（generated_at/errors/files sha），SO/PO 抓取失败删除旧文件；decide 只看文件存在，不读 manifest；rebuild 写 forecast run + CURRENT | `cli.py:170-212,283-284`；`decide.py:397-438,784-789`；`cli.py:15-22`（doctor 只查存在）；复审 P1-4 | 修掉“失败后旧文件冒充当前”；但仍可把不同时点/不同分支的 stock 与 forecast 组合；decide 无法证明 SO/PO 是本次刷新；doctor 不验包哈希/覆盖 | 引入 run_id+as_of+branch+complete 的原子 manifest，decide 强制匹配并写入输出；不一致拒绝或标不可执行 |
| M20 | 周度计划（90 天≠13 整周） | 规划要求周倍数窗口（13/26/52 周）与周分位；D5 v6.9 计划 | **未迁移**：只有 60/90/120/180 天窗口，按月权重合计；无周计划、无周分位 | `forecast.py:121-136,815-830`；`supply_copilot/RUNBOOK.md §5`「按周数量：正在加」；`FORECAST_METHOD_PLAN_20261112.md`；复审「13 周为 91 天」 | 90 天无法落成 13 个整周；首尾部分周与周分位相加问题未处理；不能按周下单/排产 | R3 从同一需求轨迹输出周计划，精确 90 天边界守恒；周分位不简单相加；先 13 周并显式标首尾部分周 |
| M21 | 数据新鲜度 | DATA_FRESHNESS：11-02 是审计日，各源截止不同（订单 10-31、PO 陈旧 4 天） | **已接入（部分）**：orders 到 2026-11-22（421,291 行）；stock 取 EN 最新成功 run（snapshot_at），>12h 警告；D6 包 as_of 2026-11-13；history 2026-10-26；rebuild 决策日默认=数据最大日 | `orders_manifest.json`；`history_manifest.json`；`pack_manifest.json`；`decide.py:845-861`；`README.md` | 需求可能刷新到 11-22、库存是当天 run、D6 回退是 11-13，三者不同时点；跨时点组合未标不可执行 | 统一 run manifest（orders_as_of/stock_as_of/forecast_as_of/cutoff），输出时点表；跨时点标不可执行 |
| M22 | 独立数据获取 | 旧链靠作者在本地刷新 D5/D6/C/E 文件 | **仅参考**：`pull-orders` 取仓库内冻结 manifest 指向的 11-22 包，不是持续向 EN 采集；本地能重算 ≠ 无需作者刷新数据 | `supply_copilot/history.py:111-118`；`orders_manifest.json` source；复审“pull-orders 默认下载仓库内冻结 manifest” | 收件方拿到的是某个冻结时点；新订单要等作者重发；不能宣称“自己就能持续更新” | 明确区分“历史回放／本地试算／已验证人工审核候选”三个层级；补运维增量采集说明 |
| M23 | 生命周期（按客户） | E 设计：lifecycle 按 SKU×客户（active/seasonal/clearance/discontinued/blocked）；EN disabled 只作技术开关 | **仅参考**：`E_lifecycle.parquet` 4,049 行，`lifecycle_status` **全部 unknown_pending**；CLI 未消费 | `E_ARCHITECTURE_PRINCIPLES_20261111.md §3`；`E_lifecycle.parquet`；`pack_manifest.json` | 无法按“客户是否 active”过滤补货；停售/清仓/季节品仍可能进候选 | 先补 lifecycle 证据与 authority，再接 D6 动作过滤 |
| M24 | 可执行性门（保护） | 旧 D6 有 auto_order=false 与人工复核 | **已接入**：默认 `executable=否` 并列原因（需求未刷新、SO/PO 未接入、PO 未映射、CG 未确认、下单日已过、库存>12h） | `decide.py:859-878,880-904`；复审“发布版有实质保护” | 降低误用风险，但不使主表数量自动正确；仍须人工复核 | 保持；把 R0 的批次/PO/run 校验加进同一门 |

## 2. 三个最容易误读的口径

1. **“296 行”不是全量。** 296 是 D6 v6.22 里美东 USNJ 的键数；D6 全量 1,571 行；D3b 的 A/B 范围是 1,749 键（含 CG 178 + 其他 7）。三者不能互相替代。
2. **“p90 / 约 90% 情形”不是“90% 服务水平”。** 它只是历史残差的经验上分位，未做 L90 累计覆盖回测；q90 与 q95 的差别也不是固定采购增幅（复审 P1-6 已否“97.5% 约翻倍”说法）。
3. **新旧预测不是同一口径。** 旧 D5/D6 是 current-owner 需求；新 rebuild 是订单行历史发货仓（as-of）需求 + 最近 3 月仓份额。没有对齐商品池/形态/单位/cutoff/保护期之前，两者数量不可直接比较。

## 3. 建议推进顺序

- **R0 供给语义闭环（阻断项）**：一次做完 P1-2/P1-3/P1-4 的剩余部分——通途 PO 为默认源并透传 ETA、按单据键做批次互斥、branch/run/as_of/complete 原子 manifest、SO 归池证据。把复审 `counterexamples.json` 的 4 个反例固化为阻断性验收。现有 `max()` 只是过渡保护，不能当净额。
- **R1 旧能力迁移签证**：本表逐项签字——A/B 当前范围差数、60cm 血缘拼接、删失接线、缺月/未知区分、current-owner 与 as-of 两套序列、按客户 lifecycle。未证来源一律保持 unknown，不让旧 D6 回退伪称“本期最新预测”。
- **R2 同口径滚动对比**：对齐商品池、形态、单位、cutoff、保护期后，旧 D5、新 AutoETS 基线、SBA/TSB/Croston/Theta 分类候选一起滚动回测；看累计误差、偏差、区间覆盖、缺货/积压，不凭模型个数或耗时决定。同时验证 q85/q90/q95 的实际覆盖率。
- **R3 周计划与 90 天边界**：从同一需求轨迹和明确分摊假设输出周计划；90 天精确边界守恒，13 周（91 天）显式标首尾部分周；周分位不简单相加。候选通过后再评估时间层级等增强。

## 4. 不能对外宣称的能力

1. **不能称“ABCDE 能力已完整迁移/已接入”。** 只迁了 D 的简化预测与部分 C/E live 读取。
2. **不能称“今天可直接下单/这是可执行采购建议”。** 默认 `executable=否`，数量是候选。
3. **不能称“p90/q90 是 90% 服务水平 / 90% 不缺货概率”。** 未校准、未做累计覆盖回测。
4. **不能称“沿用/复现了旧 D5/D6 的模型与选型”。** 分型、每键选型、TSB/SBA/Croston/Theta 未迁移；回测不换型。
5. **不能称“PO/SO/在途已按批次去重、净额可信”。** 只有 `max()` 粗保护，`net_all` 未接入。
6. **不能称“PO 已接通途采购单”。** 默认是 EN Purchase Order，且 `supply` 不写 ETA。
7. **不能称“60cm 历史桥 / current-owner 重述已迁移”。** 均未迁移。
8. **不能称“断货删失已修正需求”。** 删失默认关闭；缺月仍补 0。
9. **不能称“数据是同一时点/最新”。** 订单 11-22、库存运行时、D6 包 11-13 三者不同。
10. **不能称“支持按周计划 / 13 周”。** 周计划未迁移。
11. **不能称“E 已有供给线是 SKU×客户×节点的事实源”。** E 复核已否；lifecycle 全 unknown_pending。
12. **不能称“独立重算 = 不需要作者刷新数据”。** `pull-orders` 取的是冻结包。

## 5. 复核方法

```bash
# 旧资产口径（只输出聚合计数，不导出客户明细）
uv run python - <<'PY'
import pandas as pd
b="D:/private/demand/sc-data/data/"
print(len(pd.read_excel(b+"D3b_v3_11.xlsx", sheet_name="3_分类")))
print(pd.read_excel(b+"D6_v6_22.xlsx", sheet_name="1_全量动作")["池"].value_counts())
print(pd.read_excel(b+"D5_v6_8.xlsx", sheet_name="1_预测")["model"].value_counts())
PY

# 新入口行为
uv run python -m supply_copilot recommend --branch USNJ --limit 1
uv run python -m supply_copilot decide --branch USNJ
uv run pytest tests/test_decide_supply_semantics.py -q
```

> 本文件只新增 `supply_copilot/MIGRATION_STATUS.md`；未改业务代码、未跑 `scripts/update_index.py`（按任务约束只交付本文件）。
