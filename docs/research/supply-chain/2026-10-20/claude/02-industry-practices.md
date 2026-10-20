---
okf: v0.1
type: Research
title: 供应链整合 — 业界实践与可抄边界
description: S&OP、DDMRP、MEIO、APS、控制塔、预测治理与资金约束补货的适用条件、落地成本和对本公司的判断；含证据表与未找到项
date: 2026-10-20
status: checkpoint-2
tags: [supply-chain, research, industry-practices, ddmrp, sop, forecasting, control-tower]
---

# 02 — 业界实践与可抄边界

> 证据协议见 `00-plan.md` §7。正文引用写作 `[S2-001, B]`。
> 厂商文档（Lingxing / Jijia / Eccang / SPS）一律标 `V`，只证明「厂商这样定义」，不当作效果证据。
> 本文的「我们」指：约 5 人技术/运营团队、通途 + ERPNext + 赛狐三系统、中国工厂 → 美/波海外仓约 3 个月头程、长尾 SKU 多、断货频繁、无数据仓库。

## 1. 结论先行

1. **先做「月度轻 S&OP + 周例外会」，不要先上 APS。** S&OP 的产出是跨部门共识和决策记录，不是软件；5 人团队完全可以把五步压成 90 分钟、一页纸。[S2-001, B]
2. **补货用 DDMRP-lite，不做全量 MRP 重排；MEIO 只做两级。** 只在「海外仓成品」和「工厂共享料」设解耦点，用绿/黄/红缓冲和净流量位置触发；安全库存放哪用两级池化回答（快销前置、长尾集中），不做全网多级 DP 优化。[S2-003, C][S2-005, A][S2-006, B]
3. **控制塔从 8–12 条例外规则开始，每条有 owner、时限、升级路径。** 更多可见性不会自动带来更快决策，没有 owner 的红灯只是「更清楚地知道问题还在」。[S2-009, B]
4. **预测考核用「聚合 WAPE + 单序列 MASE + Bias + FVA」，不用 MAPE。** 断货月必须删失或还原，override 必须留原因和到期日。[S2-010, B][S2-012, B][S2-014, B]
5. **资金约束下先定服务水平和预算，再解补货。** 老板拍服务水平和超额预算，供应链拍分配，财务拍现金流；不要让补货算法替老板做现金决策。[S2-015, A]

---

## 2. 八个问题的直接回答

| # | 问题 | 结论 | 适用条件 | 我们是否适用 | 落地成本 / 代价 |
|---|---|---|---|---|---|
| 1 | S&OP/IBP 怎么做 | 月度五步循环，压成 1 页 + 90 分钟 | 有稳定 SKU 家族、销售愿承诺、老板愿拍板 | **是，轻量版** | 约 8 人时/月 + 1 个 owner |
| 2 | DDMRP vs MRP | 用解耦点 + 缓冲 + 净流量，替代逐层展开 | ADU、交期、在途可读；有缓冲纪律 | **是，选 50–100 SKU 试点** | 2–4 周建模 + 每月 2 小时维护 |
| 3 | MEIO 怎么简化 | 只做两级池化，决定安全库存放哪 | 网络是树状、成本/服务参数可估 | **是，简化用** | 约 1 周分析，不建优化器 |
| 4 | APS 要不要 | 先用瓶颈负荷检查；全量 APS 暂时不要 | 多工厂、换型重、瓶颈明显、数据准 | **暂不，只做粗能力校验** | 全量 APS 6–12 个月，不建议 |
| 5 | 控制塔与异常 | 例外队列，不是实时大屏 | 有 owner、SLA、升级路径 | **是，规则版** | 2–4 周 + 每日 15 分钟 |
| 6 | 预测治理 | WAPE/MASE/Bias/FVA + 滚动回测 | 有历史、有断货标记 | **是** | 1–2 周搭回测 + 每月 1 小时 |
| 7 | 资金约束补货 | 先定服务水平与预算，再解分配 | 能拿到采购预算和现金口径 | **是** | 与财务 2 次会 + 月度复盘 |
| 8 | 中型跨境案例 | 国内 ERP 的「目标库存天数」口径可借，厂商主张只作参考 | 能区分 V 与 I | **是** | 0，1 天验证 |

---

## 3. 逐题展开

### 3.1 S&OP / IBP：小公司要的是节奏，不是流程文件

标准 S&OP 是月度五阶段：产品评审、需求计划、供应计划、财务评审、高管批准；需求阶段「refine their forecasts」，供应阶段「create a plan for fulfilling that demand」，财务「make a recommendation」，最后「presented to the CEO for approval」。[S2-001, B]

但不要照搬大公司 IBP。2024 年对巴西 16 家纺织企业的研究把成熟度分五级，样本平均仍处在「按需求预测生产的初始赌博级」，平均约 30%，并明确指出「it is challenging to implement, requiring attention in the initial stage」。[S2-002, A] 这说明：纺织/家居类中小企业的常态是「有预测、没共识、没决策记录」，不是「流程不够复杂」。

**5 人版设计（建议直接照这个开）**

- **角色压缩**：供应链负责人兼主持人/唯一数字 owner；销售/渠道 1 人；采购/工厂 1 人；财务 0.5 人；老板 0.5 人。合计约 8 人时/月。
- **输入**：通途发货口径的 SKU 月需求（43 张月表）、通途分仓可用与采购在途、EN 工单/工序卡 WIP、DN 实际出库、现金/采购预算。
- **输出**：一页纸——共识需求、供应缺口、前 10 个决策、4 周冻结窗口、决策记录（谁、何时、依据）。
- **节奏**：月度 90 分钟决策会；每周 30 分钟例外会；产品评审按季度或新品触发，不单列。
- **成熟度目标**：6 个月内做到「一个数字 + 有记录的决策」，不要宣称做到 level 4/5。

### 3.2 DDMRP vs MRP：适合长头程，但别把它当万能药

MRP 的逻辑是「预测 → 逐层展开 → 净需求」，在长交期、预测误差大、多仓场景下容易产生批量放大和计划神经质。DDMRP 的做法是「解耦供需」：在特定节点放库存缓冲并监控补货。[S2-003, C] 微软文档列出五个组件：战略库存定位、缓冲画像与水平、动态缓冲调整、需求驱动计划、高度协作与可视执行。[S2-003, C]

**净流量位置（NFP）**：`NFP = 在库 + 在途/在单 − 合格需求`。当 NFP 跌破红区上沿时触发补货；补货量把 NFP 拉回绿区上沿。缓冲分三段：

- **红区**：安全底线，覆盖交期内的波动；按 `ADU × 交期 × 交期因子 × 波动因子` 估算。
- **黄区**：交期内正常消耗；约 `ADU × 交期`。
- **绿区**：补货周期内的用量，取 `ADU × 订货周期` 与 MOQ/整柜量的较大者。

> 上述系数是 DDMRP 的一般结构，不是本公司参数；必须用 E-B1 回测校准，不能直接抄。

**对我们是否适用**：适用，但要缩到两三个解耦点。

1. **海外仓成品**（美中、波兰）：覆盖长头程，按 SKU 分层设缓冲。
2. **工厂共享料/皮壳/面料**：只对多 SKU 共用、交期长的物料设缓冲；否则退回按单采购。
3. **在途虚拟缓冲（可选）**：只对 A 类、断货代价高的 SKU 设，避免「在途 invisibility」。

**前提**：ADU 必须来自发货口径并做断货校正；每条 lane 的交期要有分布而不是一个承诺值；在途/在单必须可读；缓冲参数每月复核、不得随手改。

**失败模式**：解耦点选错（在不需要的地方压库存）；ADU 被断货压低，越缺越不敢补；缓冲被当成「最低库存」而不是「波动覆盖」；SKU 太多导致资金沉淀。2026 年一篇 DDMRP 综述也指出，缓冲规模数学、静态假设和真实世界验证仍然有限，并存在 AI 研究空白。[S2-004, A/B] 这正好支持「小范围试点 + 回测」，而不是全量上线。

### 3.3 MEIO：只做两级，别做全网优化

多级库存优化的经典结果是「保证服务时间 + 周期性补货 + 基库存策略」，用动态规划在树状网络上分配安全库存，目标是在维持高服务的同时最小化库存成本；Graves & Willems 的模型还给了 Eastman Kodak 的应用。[S2-005, A]

MIT 的 Coppel 案例把「池化 + 保证服务模型」用在约 1,500 家门店、30 个配送中心上，安全库存成本从 46.1 万美元降到 39.4 万美元（−17.01%），年物流成本 −13.91%。[S2-006, B] 但这是 2020 年、规模远大于我们的案例，只能借方向，不能借参数。

**我们的网络其实只有两层决策节点**：中国工厂/集货 → 约 3 个月头程 → 美/波海外仓 → 平台/FBA。因此：

- **快销、稳定**（A 类）：安全库存放海外仓，工厂只保留共享料缓冲。
- **中速**（B 类）：海外仓 + 美国中心仓两级，中心仓做池化。
- **长尾**（C 类）：集中到美国中心仓，按单/小批量补，不在每个节点铺货。
- **新品**：小首单 + 2/4/8 周早期信号复核，不进入全量 MEIO。

**不要做**：全 SKU 多级 DP、把每个平台仓都当独立节点、用不可信的成本参数跑优化。我们缺的是干净的服务/成本参数，不是更复杂的算法。

### 3.4 APS vs MRP：先证明产能是瓶颈

MRP 假设无限产能，只算物料；APS 在有限产能下同时考虑工序、换型、顺序和优化目标。APS 的边界不是「先不先进」，而是「约束是否真的卡在产能上」。

**我们什么时候需要 APS**：多工厂/多车间共享瓶颈、换型时间显著、订单优先级频繁冲突、需要按设备排到班次。**什么时候是过度设计**：工序少（枕类的裁剪/缝制/填充/包装）、路由稳定、单厂、主要约束是头程、MOQ、整柜和资金。此时全量 APS 的数据维护成本会超过收益。

2004 年一篇 APS 论文的警告今天仍成立：APS 比 MRP「更依赖数据准确性」，任何输入退化都会「迅速导致明显次优的供应计划」，进而损害「计算机生成计划的信誉和本地决策者的授权」，最终可能导致「整个 Advanced Planning 业务流程失败」。[S2-007, B]（2004 年，方法结论仍适用，工具形态已过时。）

**建议**：先做 8 周粗能力负荷表（按瓶颈工序），只有连续两周负荷 >100% 才进入有限排程；排程先用 Excel/OR-Tools 做单瓶颈，不买 APS。

**春节**：SPS 的厂商文章称工厂停工「至少一个月」，建议提前三个月下单、备「六周最低安全库存」。[S2-016, V] 这是厂商建议，不是独立事实；但方向与我们的长头程一致，应作为计划假设在 S&OP 中显式确认，而不是当真理。

### 3.5 控制塔：例外管理，不是大屏

Gartner 经由 Supply Chain Dive 总结的控制塔包含人、流程、数据、组织等要素，能力包括：实时端到端可视、理解并利用信号、用高级分析做预测与建议、异常管理与情景模拟、协同响应框架、持续学习与感知。[S2-008, B]（2019 年，概念仍适用。）

关键的反直觉证据：更高可见性「在某些组织里反而会拖慢他们」；重要异常应「路由给有明确职责的具名 owner」，要有「定义的升级路径和解决期望」；「没有 owner 的红灯，只是更清楚地知道一个仍在等待解决的问题」；研究结论是「更多信息不会自动产生更快或更好的决策」。[S2-009, B]

所以我们的控制塔不是买一个产品，而是建一个**例外队列**：规则 → 分级 → owner → SLA → 升级 → 关闭 → 月度精度复盘。指标与规则见 §6。

### 3.6 预测治理：指标选错，越努力越糟

**WAPE**：`Σ|y−ŷ| / Σ|y|`。Hyndman 明确指出它「只有在时间序列平稳时才一致」，不应与「趋势、季节性、异方差」数据一起用；间歇性需求还有分母为零的风险，并建议 MASE「a better choice than the WAPE」。[S2-010, B] 因此：

- **聚合层**（品类/渠道/月）用 WAPE，便于向老板解释「总量差多少」。
- **单 SKU** 用 MASE 或分层后的 scaled error；长尾不要用 MAPE。
- **Bias** 单独报：`Σ(y−ŷ)/Σy`，正负号比绝对值更能暴露系统性问题。

**回测**：滚动原点（rolling origin），扩展或滚动窗口，记录每个 horizon 的误差矩阵，而不是只留最后一次切分。[S2-011, B] 建议 12 个月训练、3 个月预测、6 个折。

**FVA**（Forecast Value Added）：评估预测流程中每一步、每个参与者的增量价值，表达「做某事相对于什么都不做的结果」，可正可负；以 naive 为基准，示例中分析师 override 把误差从 25% 降到 24%。[S2-012, B] 这正好回答「销售改预测到底有没有用」。

**Override 治理**：手工 override 很重要，但难点是「知道它何时真正增值、何时悄悄降低精度」；常见病是「没有明确 owner 或理由地累积」以及「应用后很少被结构化评估」。正确做法是把统计预测、override、实际值放在一起比较，判断调整是改善还是恶化。[S2-013, C]

**断货删失**：Tobit 指数平滑在「已知且可能随时间变化的删失水平」下建模，可减少失销与过剩库存，并避免需求估计的「螺旋下行」。[S2-014, B] 对我们的最低要求：标记可用 ≤0 的 SKU-仓-日，报告两套 ADU（原始/校正），并在回测中剔除或还原断货月。

### 3.7 资金约束补货：服务水平是老板的选择，不是算法的输出

经典报童的临界分位数给出最优服务水平；带预算约束时，用尽全部资金下的订货量可能保持不变，而融资成本对市场波动敏感；银行融资与收入分成融资对波动方向相反。[S2-015, A]

落到我们这里，框架是「服务—成本—现金」三角：

- **老板定**：分层的目标服务水平（A/B/C）、年度采购预算、超额审批阈值。
- **供应链定**：在预算内按「每多花一元带来的边际服务提升」分配，优先保 A 类和高毛利。
- **财务定**：现金流安全线、账期、融资成本；库存天数与 CCC 的监控口径。

**公开案例的作用是提醒，不是对标**：赛维时代 2024 年存货周转天数 81 天、同比增加 10 天；[S2-020, A] 经营活动现金流量净额 −4.685 亿元、同比减少 185.25%，经营活动现金流出小计 70.77 亿元、增长 90.20%。[S2-021, A] 华凯易佰 2024 年「整体存货规模较年初增长 115.64%」，销售费用中仓储费用同比增长 153.04%。[S2-022, A/B] 备货能撑增长，也能吃掉现金，这正是老板需要拍板的地方。

### 3.8 中型跨境案例与国内 ERP 口径

国内 ERP 的补货公式值得借鉴，但只能当「本地实践口径」，不能当效果证据：

- **领星**：建议发货量 =（本地至海外时效 + 安全天数 + 发货频率）× 日销量 −（海外在途 + 可用 + 待检待上架 + 待交付 + 采购计划 + 预计发货量）；支持聚合仓库汇总多仓库存与销量。[S2-017, V]
- **积加**：目标库存量 = 目标库存天数 × 日均消耗；目标库存天数把备货审批、采购交期、质检、物流、入库、调拨、安全库存、补货周期相加再减缺货天数；历史销量可剔除断货；MSKU 日均销量 = 过去 N 天总销量 /（N − 断货天数）。[S2-018, V]
- **易仓**：强调多仓库存整合、备货/补货建议、海运轨迹、订柜与工厂交货、国内外自营仓收货。[S2-019, V]

这三家共同暴露了一个事实：**「减缺货天数」和「聚合多仓」是跨境补货的刚需**，不是高级功能。我们的 PR #297 公式目前只有「月需求率 × 覆盖期 − 可用 − 在途」，缺少断货校正与多仓聚合，这是最该补的两块。

**新品冷启动**：2025 年 WSC 论文指出，新品需求轨迹预测因「稀疏或不存在的历史数据」而困难，早期预测差会导致「overstocks, stockouts, and high product failure rates」；其 CDLF 方法融合产品属性、参考轨迹和上市后早期信号。[S2-023, A/B] 对我们的启示不是上扩散模型，而是：新品用「相似品属性 + 前 2/4/8 周实际」做小步校正。

---

## 4. 可抄的五件事（模板 / 指标 / 节奏）

### 4.1 一页 S&OP 模板

| 区块 | 内容 | 责任人 |
|---|---|---|
| 共识需求 | 未来 6 个月、按品类/渠道的量与额；标注促销/新品 | 销售 |
| 供应视图 | 可用、在途、在单、WIP、头程 ETA、缺口 | 供应链 |
| 财务视图 | 采购金额、库存天数、现金影响 | 财务 |
| 决策清单 | 买/不买、提前/延后、加急/海运、分配规则 | 老板 |
| 冻结窗口 | 未来 4 周不可变订单；8–12 周半冻结 | 供应链 |

**指标**：共识达成率、决策按时关闭率、缺口金额。
**节奏**：月度 90 分钟；会前 2 天数据自动生成，会上不重新对数。

### 4.2 DDMRP-lite 缓冲卡

| 字段 | 说明 |
|---|---|
| SKU / 节点 | 海外仓成品、工厂共享料、在途虚拟缓冲 |
| ADU | 发货口径，剔除断货日后计算 |
| 交期 | 该 lane 的 P50/P90，不用单一承诺值 |
| 红/黄/绿 | 按 §3.2 公式，首版人工校准 |
| NFP | 在库 + 在途 + 在单 − 合格需求 |
| 触发 | NFP < 红区上沿 → 建议补货至绿区上沿 |
| owner / 复核日 | 每月复核，参数变更留痕 |

**指标**：缓冲穿透率、断货率、库存天数、补货建议采纳率。
**节奏**：每周跑一次；每月调一次参数；每季度重选解耦点。

### 4.3 例外队列

| 规则 | 条件 | 级别 | owner | 时限 |
|---|---|---|---|---|
| 断货风险 | 交期 + 复核期内 projected available < 0 | P1 | 补货 owner | 当日 |
| 缓冲穿透 | NFP < 红区上沿 | P1/P2 | 补货 owner | 1 日 |
| 在途延误 | ETA 滑期 > 3 天或无更新 > 7 天 | P2 | 头程 owner | 2 日 |
| 需求突变 | 7 日发货 > 过去 8 周中位数 3 倍且 > 20 件 | P2 | 需求 owner | 2 日 |
| 采购未确认 | PO 发出 > 3 天未确认 | P2 | 采购 owner | 2 日 |
| 生产落后 | 工单完成率落后计划 10% 且 14 天内到期 | P1 | 工厂 owner | 当日 |
| 入库延迟 | DN 实际收货晚于预期 > 5 天 | P3 | 仓库 owner | 1 周 |
| 积压 | DOS > 2 倍目标且 30 天无需求 | P3 | 品类 owner | 1 周 |
| 数据缺失 | SKU/仓映射缺失或 ADU 无法计算 | P2 | 数据 owner | 2 日 |

**指标**：每日告警数、可执行率、平均关闭时长、误报率。
**节奏**：每日 15 分钟站会；每周清理误报规则；每月复盘 owner 负载。

### 4.4 预测评审

- **每月**：看聚合 WAPE、Bias、FVA；抽 top 20 误差 SKU 找原因（断货、促销、新品、映射错误）。
- **每季**：重选方法；比较 naive / 运行率 / 趋势 / 季节 / Croston 的 MASE；不要为了单一指标频繁换模型。
- **Override**：原因码（促销、新品、渠道、供应、其他）+ 到期日；到期自动回到统计值；季度算 override 的 FVA。

### 4.5 补货经济性

- **分层服务目标**：A/B/C 不同目标，不要全 SKU 一个 95%。
- **预算硬约束**：先算可用采购预算，再按边际服务排序分配。
- **单位统一**：MOQ、整柜、头程按月、海外仓按周；所有建议量向上取整到可执行单位。
- **现金视图**：每次补货建议同时给出金额、预计付款月、库存天数变化。

---

## 5. 明确不抄的（业界这么做，但我们不该）

1. **全量 APS / 全工序有限排程**。我们的瓶颈大概率是头程、MOQ 和资金，不是设备；APS 对数据准确性更敏感，输入一坏就失去计划信誉。[S2-007, B] 先做粗能力负荷，连续两周 >100% 再谈排程。
2. **全 SKU 多级 MEIO 优化**。需要可信的成本、服务时间、需求分布参数；我们连干净的服务口径都还在确认。只做两级池化。[S2-005, A]
3. **实时控制塔大屏 + 全量告警**。更高可见性可能拖慢组织；没有 owner 的告警只是更清楚的问题。[S2-009, B] 先做每日 ≤15 条的例外队列。
4. **每日 SKU 级 S&OP + 单独财务评审**。5 人团队会被会议吞掉；财务并入月度 90 分钟，周会只处理例外。[S2-001, B]
5. **对全部长尾上深度 ML/集成模型**。长尾间歇、样本少、断货多；先用运行率/Croston + 人工判断，MASE 达标再升级。[S2-010, B][S2-014, B]
6. **用 MAPE 考核预测**。零销量会让 MAPE 无定义，且会诱导「避免预测零」的作弊；用 WAPE（聚合）+ MASE（单序列）。[S2-010, B]
7. **把厂商公式当效果证明**。领星/积加/易仓的公式是口径参考，不是「用了就降库存」的证据。[S2-017, V][S2-018, V][S2-019, V]

---

## 6. 控制塔与预测治理操作细则

### 6.1 指标定义（统一口径，避免各说各话）

| 指标 | 定义 | 用途 | 注意 |
|---|---|---|---|
| OTIF | 按承诺日期、完整数量交付的订单行 / 总订单行 | 客户端服务 | 承诺日期要统一为「对客承诺」而非内部计划 |
| Fill rate | 实际发出数量 / 订单需求数量 | 缺货影响 | 与 OTIF 不同，允许分批发 |
| Stockout rate | 可用 ≤0 的 SKU-仓-日 / 总 SKU-仓-日 | 断货监控 | 必须区分「真断货」与「未上架」 |
| DOS | （在库 + 在途）/ ADU | 库存覆盖 | 在途要有可信 ETA，否则虚高 |
| Forecast bias | Σ(y−ŷ)/Σy | 系统性高/低估 | 正负号比绝对值重要 |
| WAPE | Σ\|y−ŷ\|/Σy | 聚合误差 | 仅平稳/近似平稳；分母为零要跳过 |
| MASE | MAE / naive MAE | 单序列比较 | 长尾首选 |
| FVA | (naive 误差 − 方法误差) / naive 误差 | 流程增量价值 | 可负；按步骤/人拆分 |
| Buffer penetration | 红+黄区已消耗 / 总缓冲 | DDMRP 健康度 | 持续穿透说明参数或供应有问题 |
| Exception aging | 例外从打开到关闭的时长 | 组织响应 | 按级别设 SLA |
| In-transit variance | 实际到仓 − ETA | 头程可靠性 | 用 P50/P90，不用平均值掩盖尾部 |
| PO confirm delay | PO 发出到供应商确认的天数 | 供应前置期 | 与交期分开统计 |

### 6.2 告警降噪六条

1. **每条告警必须有 owner 和 SLA**；没有 owner 的规则不许上线。[S2-009, B]
2. **按金额/服务影响排序**，每日只推 top N（建议 15 条），其余进队列不推送。
3. **按 SKU-仓-规则去重**，同一条件 24 小时内只提醒一次；条件消失自动关闭。
4. **已知事件静默**：春节、促销、已知船期延误，设置带到期日的静默窗，过期自动恢复。
5. **分级而非全红**：P1 当日、P2 两日、P3 一周；P3 不进入每日推送。
6. **月度算精度**：抽样核对可执行率；连续两月 <30% 可执行的规则下线或重设阈值。

### 6.3 预测治理节奏

- **周**：只处理例外（新品、促销、断货、映射错误），不改全量参数。
- **月**：WAPE/Bias/FVA 复盘；top 20 误差归因；override 到期清理。[S2-012, B][S2-013, C]
- **季**：滚动回测重跑；方法重选；断货校正参数复核。[S2-011, B]
- **年**：服务水平、预算、解耦点、SKU 分层重定；由老板拍板。

---

## 7. 对本公司的适配判断

### 7.1 五人团队

| 角色 | 兼任 | 每周投入 | 关键产出 |
|---|---|---|---|
| 供应链 owner | 数据/计划 | 4–6 小时 | 唯一数字、缓冲参数、例外队列 |
| 销售/渠道 | 运营 | 1–2 小时 | 促销/新品/渠道变化 |
| 采购/工厂 | 采购 | 2–3 小时 | 交期、MOQ、产能、PO 确认 |
| 财务 | 财务 | 1 小时 | 预算、现金、库存天数 |
| 老板 | 决策 | 1–2 小时/月 | 服务水平、超额审批 |

**判断**：不需要专职计划员；需要的是一个「能自动出数、只做例外」的流程。任何要求每天手工对数、每天开会的方案都不可持续。

### 7.2 三系统

- **通途**：需求（发货口径）、分仓可用、采购在途；共享 5 次/分钟限流，批量任务要排队。
- **ERPNext**：SO/PP/WO/Job Card/DN/BOM；工序卡优先于 WO 头状态；DN 要做净额（部分出库/退货）。
- **赛狐**：结算金额、库存参考；不能反推头程签收；Bin 不能当可用库存。

**判断**：指标权威按 `01-existing-assets.md` §6 初判执行；在老板拍板前，所有报表标注「口径版本 + 来源系统 + 提取时间」。

### 7.3 长头程与多仓

- 预测视野至少 6–9 个月；4 周冻结、8–12 周半冻结。
- 安全库存主要放海外仓；工厂只对共享料设缓冲；在途虚拟缓冲只给 A 类。
- 美/波两仓分别设缓冲，不共用 ADU；仓名用别名族归一。
- 头程 ETA 没有结构化字段（`01` §5），第一版用「订单日期 + 3 个月」并标注低置信，等钉钉/WorkBuddy 数据接入后替换。

### 7.4 断货删失

- 日粒度标记 `available ≤ 0`；月需求同时输出原始值与校正值。
- 校正优先用「剔除断货日」口径（积加做法，[S2-018, V]），复杂场景再上 Tobit。[S2-014, B]
- 回测时断货月不作为正常误差样本；否则会奖励「预测低」的模型。
- 新品前 8 周单独看，不混入成熟 SKU 的 WAPE。

### 7.5 无数据仓库

- 不建 DW；建一张版本化的 `planning_snapshot` 宽表（日期、SKU、节点、在库、在途、在单、ADU、缓冲、建议量），落 Parquet/CSV，脚本可重跑。
- 所有指标带 `as_of` 和 `source`；Google Sheets 只做展示，不做计算源。
- 先复用 PR #298 的分页/退避/钉钉推送，再补计划层。

---

## 8. 1–3 天验证实验

| 实验 | 时间 | 数据 | 方法 | 通过标准 | 失败含义 |
|---|---|---|---|---|---|
| E-B1 缓冲策略回测 | 1 天 | 43 张月表，选 30 个 PB SKU | 对比「当前覆盖天数」vs「DDMRP-lite」；滚动 6 折；断货月删失 | 同库存下 fill rate +3pp，或同 fill rate 下库存 −10% | 缓冲参数不敏感或数据不支持，退回固定天数 |
| E-B2 S&OP  dry run | 0.5 天 | 最近 3 个月数据 | 90 分钟模拟会，1 个品类，产出决策清单 | ≥3 个可执行决策，准备 ≤2 小时 | 会议无法产生决策，先修数据/角色 |
| E-B3 告警精度 | 1 天 | 重建 30 天库存/在途异常 | 按 §4.3 规则跑，抽样 20 条人工判定 | ≤15 条/日，可执行率 ≥60% | 规则太糙，先减规则再加数据 |
| E-B4 产能边界 | 0.5 天 | EN 工单 + 工序卡 8 周 | 粗能力负荷，按瓶颈工序 | 若连续 2 周 >100%，才考虑排程；否则明确不做 APS | 若负荷普遍 <80%，APS 无业务理由 |

> 实验只读业务系统；结果写入 `experiments/`，数字由脚本生成，不手填。

---

## 9. 证据表

| ID | 主张 | URL | 类型 | 日期 | 原文摘录 | 强度 |
|---|---|---|---|---|---|---|
| S2-001 | S&OP 是月度五阶段循环，最后到 CEO 批准 | https://rsmus.com/insights/services/business-strategy-operations/what-is-sales-and-operations-planning.html | I | 2026-10-20 访问 | "S&OP is generally broken down into a monthly cycle with five phases"；"presented to the CEO for approval" | B |
| S2-002 | 巴西 16 家纺织企业 S&OP 成熟度平均仍处初始「赌博」级，实施有挑战 | https://doi.org/10.1590/0103-6513.20230084 | P | 2024 | "the initial gamble level ... is, on average, 30%"；"it is challenging to implement, requiring attention in the initial stage" | A |
| S2-003 | DDMRP 通过解耦点与库存缓冲监控补货，含五个组件 | https://raw.githubusercontent.com/MicrosoftDocs/dynamics-365-unified-operations-public/main/articles/supply-chain/master-planning/planning-optimization/ddmrp-overview.md | C | 2026-10-20 访问 | "DDMRP is a planning methodology that's based on the decoupling of supply and demand."；"Decoupling points are specific points ... where you put an inventory buffer" | B/C |
| S2-004 | DDMRP 综述：有可用性/交期/库存改进潜力，但缓冲数学、静态假设与实证有限 | https://doi.org/10.1051/epjconf/202638306008 | P | 2026 | 标题 "Demand-Driven Material Requirements Planning in Downstream Supply Chains: A comprehensive review"；摘要（Crossref）指出上述局限 | A/B |
| S2-005 | 多级库存可用保证服务时间 + 基库存策略在树状网络分配安全库存 | https://doi.org/10.1287/msom.2.1.68.23267 | P | 2000 | 摘要：periodic-review base-stock policies、bounded demand、guaranteed service times、Eastman Kodak 应用 | A |
| S2-006 | 池化 + 保证服务模型在 Coppel 降安全库存 17.01%、物流成本 13.91% | https://dspace.mit.edu/bitstream/handle/1721.1/126496/scm2020-sharma-evaluating-inventory-risk-pooling-strategy-for-multi-echelon-distribution-network-capstone.pdf?sequence=1&isAllowed=y | I | 2020 | 安全库存 461K→394K 美元（−17.01%）；年物流成本 −13.91% | B |
| S2-007 | APS 比 MRP 更依赖数据准确性，输入退化会导致计划失信与流程失败 | http://sajie.journals.ac.za/pub/article/download/234/219 | P | 2004 | "Advanced Planning is even more reliant on data accuracy than Requirements Planning"；"credibility of computer generated supply plans"；"failure of the whole Advanced Planning business process" | B |
| S2-008 | 控制塔含人/流程/数据/组织，能力覆盖可视、信号、预测、异常、协同、学习 | https://www.supplychaindive.com/news/gartner-what-supply-chain-managers-should-know-about-control-towers/574098/ | I | 2019 | "a concept combining five elements — people, process, data and organization"；"Do exception management and scenario modeling" | B |
| S2-009 | 更多可见性可能拖慢组织；异常必须路由给具名 owner 并有升级路径 | https://www.thescxchange.com/why-more-supply-chain-visibility-can-slow-you-down | I | 2026-10-20 访问 | "greater visibility can actually slow them down"；"A red light without an owner is simply better information about a problem that is still waiting to be solved." | B |
| S2-010 | WAPE 仅在平稳时一致，不宜用于趋势/季节/异方差；间歇需求建议 MASE | https://857.robjhyndman.com/hyndsight/wape.html | I | 2025 | "only consistent when the time series is stationary"；"should not be used with data that has trends, or seasonality, or heteroscedasticity"；"a better choice than the WAPE" | B |
| S2-011 | 滚动原点回测可生成多 horizon 误差矩阵 | https://pkg.robjhyndman.com/forecast/reference/tsCV.html | I | 2026-10-20 访问 | "rolling forecast origin"；支持扩展/滚动窗口；输出各预测步长的误差矩阵 | B |
| S2-012 | FVA 评估预测流程每一步/每个参与者的增量价值，以 naive 为基准，可正可负 | https://www.sas.com/content/dam/SAS/en_us/doc/whitepaper1/forecast-value-added-analysis-106186.pdf | I | 2026-10-20 访问 | "FVA is a metric for evaluating the performance of each step and each participant"；"It expresses the results of doing something versus having done nothing."；"FVA can be either positive or negative" | B |
| S2-013 | 手工 override 的价值需要结构化评估，否则会无理由累积并降低精度 | https://optilon.com/resource/sharper-forecast-overrides-for-higher-planning-accuracy/ | I | 2026-10-20 访问 | "The challenge is knowing when overrides truly add value — and when they quietly reduce accuracy."；"Overrides accumulate without clear ownership or rationale" | C |
| S2-014 | Tobit 指数平滑可在已知/可变删失水平下减少失销与过剩，避免需求估计螺旋下行 | https://arxiv.org/abs/2409.05412 | P | 2024-09 | "Tobit Exponential Smoothing with time aggregation constraints"；"known and potentially variable censoring levels over time"；"avoiding spiral-down effects in demand estimation" | B |
| S2-015 | 资金约束报童：预算约束下用尽资金订货量可能不变；融资成本对波动敏感 | https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0329561 | P | 2025 | "This formulation embodies the critical fractile solution"；"Under bank financing, financing costs exhibit a positive sensitivity to market volatility." | A |
| S2-016 | 厂商称春节停工至少一个月，建议提前三个月下单、备六周安全库存 | https://www.spscommerce.com/community/articles/how-to-plan-production-around-chinese-new-year | V | 2026-10-20 访问 | "typically has workers out of the factories for a minimum of one month"；"place their orders a minimum of three months before the holiday"；"six-week minimum safety stock" | C |
| S2-017 | 领星补货公式含时效/安全天数/发货频率与多仓聚合 | https://www.lingxing.com/help/article/allPlatformReplenishmentAdvice | V | 2026-10-20 访问 | "建议发货量=（本地仓至海外仓时效+安全天数+发货频率）*日销量（动态）－（海外仓在途+海外仓可用+...）"；"可设置聚合仓库" | C |
| S2-018 | 积加目标库存天数含审批/交期/质检/物流/入库/调拨/安全库存/补货周期并减缺货天数；支持剔除断货 | https://help.jijiaerp.com/docs/eeE2AHAR | V | 2026-10-20 访问 | "目标库存天数 = 备货计划与审批时间 + 采购交期 + ... + 补货周期 - 缺货天数"；"历史销量是否剔除断货数据"；"日均销量= 过去N天的总销量 /（N-断货天数）" | C |
| S2-019 | 易仓强调多仓库存整合、备货补货、海运轨迹、订柜与工厂交货 | https://www.eccang.com/news/2814 | V | 2026-10-20 访问 | "打通多仓库存数据，海运轨迹实时跟踪货柜运输，订柜计划及工厂交货管理"；"多仓库存整合与一体化看板" | C |
| S2-020 | 赛维时代 2024 年存货周转天数 81 天，同比增加 10 天 | https://stock.stockstar.com/JC2025042900027590.shtml | I | 2025-04-29 | "2024年公司存货周转天数为81天，同比2023年增加10天。" | A |
| S2-021 | 赛维时代 2024 年经营现金流净额 −4.685 亿元，同比 −185.25% | https://finance.sina.cn/2025-04-27/detail-ineurezq9805317.d.html?vt=4 | I | 2025-04-27 | "经营活动产生的现金流量净额为 - 468,535,009.96元，较上年同期减少185.25%"；"经营活动现金流出小计7,077,083,666.64元，增长90.20%." | A |
| S2-022 | 华凯易佰 2024 年存货规模较年初 +115.64%，仓储费用 +153.04% | https://m.21jingji.com/article/20250515/6bf9075e7e4671ede439f9ddd7006bf3.html | I | 2025-05-15 | "整体存货规模较年初增长115.64%"；"销售费用中仓储费用同比增长153.04%" | A/B |
| S2-023 | 新品冷启动因历史稀疏而困难，差预测导致过剩/断货/失败；可融合属性、参考轨迹、早期信号 | https://www.informs-sim.org/wsc25papers/doc107.pdf | P | 2025 | "Accurately forecasting the demand trajectories of newly launched products is a fundamental challenge due to sparse or nonexistent historical data."；"overstocks, stockouts, and high product failure rates" | A/B |
| S2-024 | 告警过载指告警速率超过复核能力 | https://zenodo.org/records/21111461/files/Anomaly_Understanding_Preprint.pdf?download=1 | I | 2025 | "Alert overload is the condition in which the rate of alerts exceeds the capacity to review them."（检索摘要，未逐字复核全文） | C |

> 饱和说明：以上 24 条覆盖 8 个问题的主结论与反证；继续检索主要增加同类厂商文章，边际信息低，故在此停止。

---

## 10. 未找到项（N-2xx）

| ID | 目标 | 检索词 | 范围 | 日期 | 结论 |
|---|---|---|---|---|---|
| N-201 | ASCM/APICS 官方 S&OP 五步页面 | ASCM S&OP five steps、APICS sales and operations planning | ascm.org 站内与公开搜索 | 2026-10-20 | 在上述范围内未发现可公开访问的官方原文页；改用 RSM 的独立整理 [S2-001] |
| N-202 | Microsoft Learn DDMRP 原始页面 | DDMRP overview site:learn.microsoft.com | Microsoft Learn 与 GitHub docs | 2026-10-20 | 直接页面 404；在上述范围内发现 GitHub 原始 Markdown [S2-003] |
| N-203 | EPJ 2026 DDMRP 综述全文 | Demand-Driven Material Requirements Planning review | DOI 与出版社页面 | 2026-10-20 | 全文页 403；在上述范围内仅取得 Crossref 摘要 [S2-004] |
| N-204 | MIT 2025 医疗器械 MEIO 论文 | multi-echelon inventory medical device thesis | MIT DSpace | 2026-10-20 | DSpace 429；在上述范围内仅有检索摘要，未纳入证据表 |
| N-205 | INFORMS/MSOM 删失需求论文全文 | censored demand newsvendor MSOM | INFORMS 与 DOI | 2026-10-20 | 403；在上述范围内仅有检索摘要；改用 Tobit 论文 [S2-014] |
| N-206 | McKinsey 营运资金报告原文 | working capital inventory supply chain McKinsey | McKinsey 站点 | 2026-10-20 | 两次超时；未取得可逐字引用的原文，故正文不引用其数字 |
| N-207 | ASCM/SCOR 官方 OTIF 定义页 | SCOR OTIF definition ASCM | ASCM 与公开搜索 | 2026-10-20 | 在上述范围内未发现官方原文；本文 OTIF 采用通用订单行口径，待业务确认 |

---

## 11. 与后续章节的接口

- **01**：资产与口径初判；本文不重复资产清单。
- **03**：AI/Agent 能做到哪一段；本文只给业务边界，不给模型选型。
- **04**：开源与 TCO；本文的「落地成本」是人力与流程成本，不含软件报价。
- **05**：主 Agent 据此写推荐架构；本文的 §2、§5、§7 是输入。
- **06**：需要老板拍板的事项——分层服务水平、采购预算上限、超额审批阈值、S&OP 固定会议。
