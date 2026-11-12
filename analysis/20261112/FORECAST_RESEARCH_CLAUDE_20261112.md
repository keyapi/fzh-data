# 预测/补货方法调研 — Claude Code（2026-11-12）

> **性质**：只读桌面调研，未改代码、未碰生产。
> **来源分级**：`[文档]` 厂商/标准文档（Oracle、Microsoft、Infor、NRF）；`[学术]` 论文/教材；`[行业]` 咨询/软件商博客（只作实践参考，不当“标准”）。所有 URL 见文末。
> **结论先行**：97/157 不是“错在不是 7 的倍数”，而是错在**没有按每个键的“交期+复盘周期”定窗**；春节问题也不能靠把 157 改大解决，应把停工建成**供给日历**并单开 bridge 窗。统一 q95 的问题比模型选择更严重：**分位窗口 ≠ 风险窗口**时会同时造成 A 类压货和波兰欠货。

---

## 0. 六条结论

1. **计划窗**：业界硬约束是“覆盖累计交期（COLT）+ 复盘周期”，不是 7/30 的整数倍。97 天对波兰（100.6 天）不够；157 天对春节 bridge 也不够。
2. **春节**：成熟做法是 **pre-build/build-ahead + 停工日历 + 两批排产 + 节后爬坡跟踪**；需求窗应覆盖到“首批复工货到达目的地”，不是“复工日”。
3. **模型**：naive 占比高本身不是病，FVA 的逻辑就是打不过 naive 就用 naive；真正的病是 **adopted_model 与回测赢家不一致**，以及缺“带趋势/季节的 ETS + Theta”。
4. **服务水平**：95/90/85 不是业界标准；可说的是 90–98% 是常见区间、85% 对 C/Z 慢销品合理。核心错误是**对所有键统一用 q95(97 天)**。
5. **情景**：不要一刀切 -20/-30%；用“领先指标（sell-through、同比、weeks of cover）+ 分 segment 的三情景 + 概率/触发条件”。
6. **落地**：先修“定义与一致性”（1–2 周），再修“分位窗与服务分档”，春节 bridge 单独做，最后才考虑全局 ML。

---

## 1. 计划窗 / 预测粒度

### 1.1 业界事实

- **硬约束是累计交期，不是 7/30 倍数。** Oracle JD Edwards：计划窗必须覆盖所有低层物料的累计交期，例：累计交期 80 天 → 计划窗不得少于 80 天 [S1]。Infor：物料的计划窗必须至少等于该物料的 total COLT（累计订单交期）[S2]。
- **Microsoft 把“计划窗”直接叫 coverage time fence**：默认 100 天，按日历日计，“must be longer than the total lead time”；并明确“a week is always considered seven days”，即周是 7 天，不因工作日历改变 [S3]。
- **Oracle 的 planning time fence 是同一逻辑的另一面**：fence 内计划引擎不建新计划单；fence 日期 = 开始日 + fence 天数（工作日常用）[S4]。也就是说，“窗口内不可动、窗口外可重排”是 ERP 的通用结构。
- **周期补货的风险窗 = 交期 + 复盘周期**；复盘周期必须计入，否则安全库存算小 [S7]。MIT 的安全库存教材也强调“demand periods equal total lead time, including any review period” [S20]。
- **7/30 倍数的来源是记账/对比口径，不是计划理论。** 零售用 4-4-5，季度 = 13 周 = 91 天，目的是“like days compared to like days” [S5]。S&OP 是月度节奏，常见 18–24 个月视野 [S8]。13 周常用于季度执行/滚动预测（零售季度即 13 周 [S5]），26 周半年，52 周年度预算。
- **没有找到任何权威来源要求“预测窗必须是 7 或 30 的整数倍”。** 真正的三个要求是：① 覆盖 L+R；② origin 对齐复盘周期；③ 评估按 horizon 对齐、末桶完整 [S1–S3, S6]。

### 1.2 对我们的判断

| 项 | 数值 | 判断 |
|---|---|---|
| 97 天 | 13.86 周 | 不是整周；按周汇总时最后一周只有 6 天，周同比会偏 |
| 157 天 | 22.43 周 | 不是整周；最后一周只有 3 天 |
| 波兰累计交期 | 43.6+2+55 = 100.6 天 | **> 97**，按 Oracle/Infor 规则，97 天计划窗不合格 |
| 中国线 p90 交期 | 32+39.5 = 71.5 天 | +7 天复盘 = 78.5，98 天够 |
| 波兰 L+R | 100.6+7 = 107.6 天 | 向上取整周 = **112 天（16 周）** |

结论：**97 天不是“统一太短”，而是“对波兰太短、对中国线够”；用一个固定窗覆盖所有键，本身就违反“按 COLT 定窗”的原则。**

### 1.3 建议

1. **主规则**：`H_key = ceil((L_p90 + R + buffer) / 7) × 7`，`R` 为复盘周期（建议 7 天），`buffer` 至少 1 周；下限 8 周。
2. **两个标准桶**：**98 天（14 周）** 与 **154 天（22 周）**；若确需 23 周用 **161 天**。即：**97→98，157→154（或 161）**。理由：整周、可汇总、可评估；157 的 3 天余量没有任何分析含义。
3. **90 天若要保留，改成 91 天（13 周）**，对齐零售季度 [S5]；不要用 90（90 = 12.86 周，也不是整周）。
4. **波兰单独用 112 天（16 周）**，或把波兰的 L 单独参数化；不要用一个 97 覆盖。
5. **桶口径**：日预测按“完整周”汇总；月桶用日历月末，不用固定 30 天。若必须用月桶，3 个月用 13 周（91 天），6 个月用 26 周（182 天）。
6. **不要用拉长 157 来解决春节**（见第 2 节）；常规窗和春节 bridge 窗分开。

---

## 2. 春节停产

### 2.1 业界事实

- **2027 年春节 = 2 月 6 日（周六）** [S9]。官方假期通常 7–9 天，但工厂实际停 7–10 天以上、闲置 2–3 周；应按 **3–4 周产能缺口**规划；整体扰动 **6–8 周**；复工首几周只有 **30–50% 产能**，**3 月中**才接近满产 [S10]。
- **订货节奏**：11 月中前下最终生产单，12 月中前确认出货；备 **4–6 周**额外供应 [S11]。工厂通常在春节前 **2–4 周**开始减产 [S12]。
- **成熟做法**：pre-build / build-ahead（节前把“停工 + 爬坡”期间的需求先生产出来）、shutdown safety stock、产能预留、两批排产、节后爬坡跟踪 [S10, S13, S14]。
- **没有找到“需求窗应覆盖到复工后多久”的统一标准。** 工程上应覆盖到“**首批复工货到达目的地**”，而不是“复工日”。

### 2.2 对我们的判断

按 brief 的 v13：**1/24 停工、2/22 复工**。

| 链路 | 首批复工货到货 | 从 2026-11-02 起算 |
|---|---|---|
| 波兰 | 2/22 + 43.6 + 2 + 55 ≈ **2027-06-02** | **约 212 天** |
| 中国线 | 2/22 + 71.5 ≈ **2027-05-04** | **约 183 天** |

- D5 的 97 天窗到 **2027-02-07**——正停在停工中间。
- D5 的 157 天窗到 **2027-04-08**——仍早于首批复工货到货（波兰 6/2、中国 5/4）。
- 所以：**两个窗都没有覆盖“供给真空”**；把 157 改成 161 也只多 4 天，解决不了 6 周的缺口。

### 2.3 建议（可直接写成规则）

1. **供给日历，不是需求调整**：1/24–2/22 产能 = 0；2/22–3/8 产能 = 30–50%；3/15 后 = 100%。不要用“需求 +30%”模拟停工。**这些百分比先用本厂 2024–2026 实际复工曲线校准**，不要直接当行业常数。
2. **Bridge 窗**：`W_bridge = 停工开始 → 首批复工货到目的地`。2027 年：波兰约 **212 天**，中国线约 **183 天**。这个窗只用于春节 pre-build，不替代常规 98/154。
3. **Pre-build 量** = `q_α(bridge 需求) − 停工开始时在手 − 停工前可到在途 − 停工前已确认 PO`。α 按 Q4 服务水平（A 类建议 97.5–98%）。
4. **下单/出货**：最终生产单 11 月中前；12 月中前确认出货；两批排产——节前 bridge 批、节后补货批；节后批预留产能与原料。
5. **需求窗下限**：至少覆盖到“首批复工货到货 + 1 个复盘周期”；若卖季在复工前结束（Q4 圣诞），覆盖到卖季结束，剩余按清货处理。
6. **S&OP 对齐**：11 月 cycle 增加“CNY 情景”，12 月初冻结；每周跟踪产量 vs 计划、船期 ETA、工厂复工率。
7. **口径提醒**：行业博客的数字互相不一致（4–6 周 vs 6–8 周；30–40% 库存），只能当启发式；以自家工厂日历、实测爬坡和船期为准 [S10, S11]。

---

## 3. 模型选择与回测

### 3.1 业界事实

- **间歇需求**：Croston 把“需求大小”和“需求间隔”分开平滑；SBA 用 `(1−α/2)` 纠正 Croston 的正偏差；TSB 适合可能永久归零/淘汰的品 [S15]。综述与实证见 [S16]。
- **M5 的结论是“有条件”的**：冠军是多个 LightGBM 的等权组合（按 store/category/department 训练），**在高聚合层显著优于 Croston，但在最难的产品-店层只是 similar**；主要增益来自 cross-learning 与外生变量 [S17, S18]。含义：全局 ML 不是万能，低量粒度仍要靠简单模型/池化。
- **Theta 在 M3 表现最好之一**，简单、便宜，适合作为强基线 [S21, S22]。
- **回测协议**：rolling origin、expanding window；每个 origin 只用该时点之前的数据、重拟合、按 horizon 评估；不能随机 CV [S6]。
- **常见前视/泄漏**：全序列做平滑/分解/归一化再切分；特征从测试集提取；全局模型跨序列对齐时带入未来信息；用“当天汇总统计”当特征 [S23]。
- **模型选择必须在 validation 上做，test 只做最终评估**；否则报告的是“选择分数”，不是干净样本外 [S23]。
- **区间**：conformal 可给分布无关的覆盖率；多步/在线版本已成熟 [S24, S25]。
- **FVA（Forecast Value Added）**：只有比 naive 更好的模型才值得留；否则 naive 就是正确选择 [S26, S27]。
- **ensemble**：M5 冠军本身就是多个 LightGBM 的**等权组合** [S17]；简单等权/中位数组合常是低成本提升，但必须在 validation 上验证，不能默认 ensemble 一定更好。

### 3.2 对我们的判断

- 模型集 **缺“带趋势/季节的 ETS”和 Theta**。`ETS(A,N,N)` 只有水平，97/157 天跨 Q4，季节性是硬伤。
- **naive 占比高本身不是错**；FVA 的逻辑就是“打不过 naive 就用 naive”。真正的问题是 **DM-60（naive 1.00 vs ets 0.847）和 KJB-90-BEIGE（naive 0.838 vs SBA 0.699）两例 adopted 与回测赢家不一致**——这是选择/写回逻辑 bug，不是模型哲学。
- **Croston/SBA/TSB 只给“速率”点预测**，不能直接给 97 天 p10/p90；若用残差正态假设，间歇序列会严重失真。

### 3.3 建议

1. **选择协议**：rolling origin，`h=98/154`，expanding；至少 12–18 个 origin；selection 在 validation，final 用最后 6 个月 holdout（不参与选择）；按 horizon 分别报告 WAPE + pinball loss + 覆盖率。
2. **候选集**：naive、snaive、MA3、`ETS(A,N,N)`、`ETS(A,Ad,N)`、`ETS(A,A,A)` 或 STL+ETS、Theta；间歇品加 Croston/SBA/TSB；全局 LightGBM 只作为聚合层/高量品候选，不作为低量品默认。
3. **选择门槛**：`FVA ≥ +5%`（相对 naive），且在 ≥60% 的 origin 上胜出；否则 naive。并列时按固定顺序取最简模型，保证确定性。对“看起来更好”的模型做**显著性检验**（Diebold–Mariano 或 block bootstrap），避免把噪声当改进。
4. **间歇品**：sporadic 用 SBA；有淘汰/归零风险用 TSB；不要用 Croston 直接外推 97 天分位。
5. **区间**：按 horizon×分层做经验残差分位，或 split/online conformal；不要假设正态。
6. **修 adopted 不一致**：D4 产出**唯一 selection 表**（key, origin, h, model, params, metric, FVA, reason），D3b 只 join，不再自己算；pipeline 加断言（D3b 的 model 必须等于 D4 同 key 的 model，否则 fail closed）。DM-60 / KJB-90 用同一协议重跑，先解释再改。
7. **防选择过拟合**：selection 与 reporting 分开；跟踪 model churn；每季/每年重选，不要每月翻烧饼。

---

## 4. 服务水平 / 分位

### 4.1 业界事实

- **CSL vs fill rate**：CSL 是“每个补货周期不缺货的概率”；fill rate 是“需求中被满足的比例”。同样安全库存下，fill rate 通常高于 CSL；两者不能混用 [S20]。
- **典型目标 90–98%**；z：90% = 1.28、95% = 1.65、99% = 2.33；服务越高，库存非线性上升 [S20]。
- **ABC-XYZ**：按价值/波动分 9 宫格，分档设服务；EazyStock 示例用 **99/95/90**，且 lumpy 品通常给**更低**服务（其矩阵出现 70/90/94/95）；ASCM 也讲 ABC 价值 + XYZ 波动 [S28, S29, S30]。
- **成本最优**：newsvendor 临界比 `CSL* = Cu/(Cu+Co)` [S31]；Lokad 给近似公式 `p = Φ(√(2 ln((1/√(2π))(M/H))))`，M 是缺货边际成本（至少毛利，可含客户流失），H 是交期内的持有成本；条件 `M > 2.5H` [S32]。
- **没有找到“95/90/85 是业界标准”的来源。** 可说的是：95/90 在 90–98 常见区间内；85 低于常见区间，但对 C/Z 慢销品是合理下限 [S20, S28]。

### 4.2 对我们的判断

- **统一 q95 的根本问题**：`q95` 只有在“分位窗口 = 风险窗（L+R）”时才对应 95% CSL。你们用固定 97 天：
  - 对 `L+R≈35 天` 的 key：等于给 **2.8 倍风险窗**备货，实际 CSL 远高于 95%，压库存；
  - 对波兰 `L+R≈108 天`：`q95(97)` 反而**低于** 95% CSL，欠库存。
- **q95/p50 比值上限**：没有标准；`p50=0` 时比值无定义/爆炸。用比值做 cap 会在长尾品上产生任意结果。
- **sigma 上限**：也没有标准；用 cap 掩盖模型误差，不如用稳健尺度（MAD/IQR）+ 分层池化 + 回测覆盖率。

### 4.3 建议

1. **分位窗口改为每个 key 的 L+R**，而不是固定 97；H 只用于计划/汇总。
2. **分档**：A 97.5–98%、B 95%、C 90%、D（慢/块状）85% 或改用 fill rate；先用 95/90/85 作 prior，季度用回测校准。
3. **用临界比定价**：`Cu = 毛利 + 平台惩罚/广告位/CLV`；`Co = L+R 内持有成本 + 过季跌价`。算出来再映射到档位；算不出就显式假设并记录。
4. **长尾/新品/季节**：长尾用 fill rate + 池化，不用高 CSL；新品用类比/分层先验；季节品用季节分位 + 情景，不用全年 sigma。
5. **校准**：rolling-origin 的 PIT/覆盖率，按 class 要求 ±3pp；不达标调 α，不是调 sigma cap。
6. **Cap 的正确形式**：业务风险上限（如 A 类安全库存不超过 8–12 周均值、C 类不超过 16–20 周），或绝对金额上限；**不要 cap q95/p50**。

---

## 5. 需求趋势与情景

### 5.1 业界事实

- **趋势/季节**：STL 分解、ETS、ARIMA、Prophet（节假日/多季节）、局部线性趋势都是成熟方法；多年同比在只有 2–3 年数据时噪声大，需池化/分层。
- **情景**：S&OP 情景是“在需求/供应/库存/产能假设下测试不同组合”，按概率/触发条件管理 [S33, S34]。
- **监控**：sell-through、同比、库存周转/周供应、forecast bias/tracking signal [S35, S36]。
- **2026 假期信号是矛盾的**：卖家备货谨慎（30–40%），但 Adobe 预计线上 +6.7%、Amazon 招 30 万临时工——不能一刀切砍 30–40%。**（这两个数字来自 brief 引用的 AMZ123 / Ecommerce Times，本次未复核原文，只作为“信号矛盾”的例证。）**

### 5.2 建议

1. **趋势**：周粒度 STL / `ETS(A,Ad,A)` 或 Prophet（含节假日）；用 **damped trend** 防止把 Q4 峰值线性外推；2020–2021 排除或降权；<2 年历史的品用类目季节形状做先验。
2. **情景生成**：三情景（base/upside/downside）+ 概率 + 触发条件；按 segment（季节装饰/日常/新品/价格带/渠道）给不同 delta，**不搞统一 -20/-30%**。驱动量：近 4 周 sell-through vs 计划、同比、weeks of cover、广告转化、类目排名。
3. **把“卖家谨慎”转成产品级**：先看该品近 4–8 周 sell-through 和同比是否真的转弱；只有领先指标转弱才下调，且下调的是**补货量/返单**，不是把 A 类也砍 30%。用贝叶斯更新：历史先验 + sell-through 似然 → 情景权重。
4. **监控指标**：weekly sell-through、YoY、weeks of cover、signed bias、tracking signal、PIT coverage；触发复盘：`|bias| > 2σ` 或 sell-through 偏离计划 >15%。

---

## 6. 落地计划（不写代码）

| 阶段 | 时间 | 做什么 | 验收指标 |
|---|---|---|---|
| **P0 定义** | 第 1 周 | 写 ADR：`H_key = ceil((L_p90+R+buffer)/7)×7`；标准桶 98/154；服务分档表；selection 协议；D3b/D4 单一事实源 | 每个 key 都有 L、R、H、class；无缺失；ADR 评审通过 |
| **P1 一致性** | 第 1–2 周 | D3b 改为 join D4；加断言；补 `ETS(A,Ad,N)` / `ETS(A,A,A)` / Theta；重跑 rolling-origin | D3b=D4 **100%**；前视注入测试 0 违规；按 horizon 出 WAPE/pinball；adopted 的 FVA>0；naive 占比有解释 |
| **P2 分位窗/分档** | 第 2–4 周 | 分位窗改为 L+R；α 按 class；业务 cap；回测覆盖率 | 各 class 实际覆盖率 ±3pp；库存变化在预算内；无 `q95<q50` 等逻辑错 |
| **P3 春节 bridge** | 第 3–5 周 | 供给日历；bridge 窗；pre-build 量；两批排产 | 1–6 月 A 类无断货（仿真）；pre-build 量与产能对账；下单早于 11 月中 |
| **P4 情景/监控** | 第 5–6 周 | 三情景 + 概率 + 触发；周度监控 | 情景概率/触发有文档；监控上线；假期决策有记录 |
| **P5 全局 ML（可选）** | 2027 Q1 | 聚合层 LightGBM；MinT 层级 reconciliation [S19] | holdout 聚合层 WAPE 改善 ≥5%，key 层不恶化 |

**顺序理由**：P1 不修，后面所有指标都不可信；P2 的收益（库存/缺货）最大；P3 有时效（11 月中前必须下单）；P5 只有在简单模型 plateau 后才值得。

---

## 7. 未能证实 / 需要你确认

1. **“计划窗必须是 7/30 整数倍”**：没有找到权威来源。若你们内部/客户/平台有此约束，请给出规则来源。
2. **“95/90/85 是业界标准”**：没有直接来源；只有 90–98% 典型区间和 99/95/90 的厂商示例。建议把它写成“我们的政策”，不要写成“业界标准”。
3. **春节博客数字不一致**：4–6 周 vs 6–8 周、30–40% 库存；应以自家工厂日历、实测爬坡、船期为准。
4. **波兰 43.6+2+55 天、中国线 p90 71.5 天**：按 brief 给定值推算；若口径变化，bridge 日期要重算。
5. **D5 的 p10/p50/p90 是怎么从 Croston/SBA 得到的**：brief 没说；若是残差正态假设，建议改为经验分位/conformal（见 3.3）。

---

## 8. 来源

**计划窗 / 粒度**

- [S1] Oracle JD Edwards, *Planning Horizons* — https://docs.oracle.com/en/applications/jd-edwards/supply-chain-manufacturing/9.2/eoarp/planning-horizons.html
- [S2] Infor LN, *Cumulative order lead times and horizons* — https://docs.infor.com/ln/10.3/en-us/lnolh/help/cp/onlinemanual/000317.html
- [S3] Microsoft Learn, *Coverage time fences* — https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/coverage-time-fence
- [S4] Oracle Fusion, *How the Planning Time Fence Date Is Calculated* — https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/fausp/how-the-planning-time-fence-date-is-calculated.html
- [S5] NRF, *4-5-4 Calendar* — https://nrf.com/resources/4-5-4-calendar
- [S6] Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* 3e, *Time series cross-validation* — https://otexts.com/fpp3/tscv.html
- [S7] nVentic, *Time horizons in inventory optimization* — https://nventic.com/insights/time-horizons-in-inventory-optimization
- [S8] OmniFold, *What Is S&OP?* — https://omnifold.ai/blog/articles/what-is-sales-and-operations-planning

**春节**

- [S9] Smithsonian, *2027: Year of the Goat* — https://www.si.edu/spotlight/lunar-year-goat
- [S10] Olimp Warehousing, *Chinese New Year 2026: Logistics Guide for U.S. Importers* — https://olimpwarehousing.com/planning-chinese-new-year-2026-logistics/
- [S11] ReplenishRadar, *Chinese New Year Supply Chain Planning Guide* — https://replenishradar.com/blog/chinese-new-year-supply-chain
- [S12] EasyImex, *China Factory Shutdown Chinese New Year 2027* — https://easyimex.com/blog/china-factory-shutdown-chinese-new-year-2027/
- [S13] Slimstock, *Chinese New Year 2026: how to prepare your Supply Chain* — https://www.slimstock.com/blog/prepare-your-supply-chain-for-chinese-new-year/
- [S14] Royalcase, *Chinese New Year 2027: What OEM Buyers Need to Know* — https://www.royalcase.com/blog-posts/chinese-new-year-2027-what-oem-buyers-need-to-know-about-lead-times

**模型 / 回测**

- [S15] Nixtla StatsForecast, *CrostonSBA Model* — https://nixtlaverse.nixtla.io/statsforecast/docs/models/crostonsba.html
- [S16] Syntetos et al., *Intermittent demand forecasting: An empirical study* — https://www.sciencedirect.com/science/article/abs/pii/S0925527314002771
- [S17] Makridakis et al., *The M5 Accuracy competition: Results, findings and conclusions* (PDF) — https://statmodeling.stat.columbia.edu/wp-content/uploads/2021/10/M5_accuracy_competition.pdf
- [S18] *Introduction to the M5 forecasting competition Special Issue*, PMC — https://pmc.ncbi.nlm.nih.gov/articles/PMC9232271
- [S19] FPP3, *Forecasting hierarchical and grouped time series* — https://otexts.com/fpp3/hierarchical-forecasting.html
- [S20] King, *Understanding safety stock and mastering its equations*, MIT 2.810 (PDF) — https://web.mit.edu/2.810/www/files/readings/King_SafetyStock.pdf
- [S21] Spiliotis et al., *Generalizing the Theta method for automatic forecasting* — https://www.sciencedirect.com/science/article/abs/pii/S0377221720300242
- [S22] Hyndman & Billah, *Unmasking the Theta method* — https://bridges.monash.edu/articles/journal_contribution/Unmasking_the_Theta_method/5084719
- [S23] *Forecast Evaluation for Data Scientists: Common Pitfalls and Best Practices* — https://arxiv.org/html/2203.10716v2
- [S24] *Online conformal inference for multi-step time series forecasting* — https://arxiv.org/abs/2410.13115
- [S25] *Ensemble Conformalized Quantile Regression for Probabilistic Time Series Forecasting* — https://arxiv.org/pdf/2202.08756
- [S26] E2open, *Forecasting and Inventory Benchmark Study* (FVA definition) — https://www.e2open.com/wp-content/uploads/2019/02/2018_Forecasting_and_Inventory_Benchmark_Study_white_paper_digital.pdf
- [S27] Demand Planning, *How To Use Forecast Value Added Analysis* — https://demand-planning.com/2018/02/12/what-is-forecast-value-added-analysis

**服务水平 / 分位**

- [S28] EazyStock, *ABC-XYZ Inventory Classification Guide* (PDF) — https://www.eazystock.com/wp-content/uploads/2022/10/us-wp-abc-xyz-inventory-classification-guide.pdf
- [S29] ASCM, *The XYZs of Inventory Management* — https://www.ascm.org/ascm-insights/the-xyzs-of-inventory-management/
- [S30] Cyberstockroom, *How to Use ABC-XYZ Analysis* — https://blog.cyberstockroom.com/2026/09/01/how-to-use-abc-xyz-analysis-for-advanced-inventory-classification/
- [S31] MetricGate, *Newsvendor Critical Fractile* — https://metricgate.com/docs/newsvendor-critical-fractile/
- [S32] Lokad, *Service level definition and formula* — https://www.lokad.com/service-level-definition-and-formula/

**情景 / 监控**

- [S33] ToolsGroup, *S&OP Scenario Planning* — https://www.toolsgroup.com/blog/sop-scenario-planning/
- [S34] Demand Planning, *Scenario Analysis for S&OP: Case Study* — https://demand-planning.com/2017/06/08/scenario-analysis-for-sop/
- [S35] Inflow, *Sell-Through Rate* — https://www.inflowinventory.com/blog/what-is-sell-through-rate-heres-why-it-matters-for-your-business/
- [S36] Netstock, *What Is a Good Inventory Turnover Ratio?* — https://www.netstock.com/blog/what-is-a-good-inventory-turnover-ratio/
