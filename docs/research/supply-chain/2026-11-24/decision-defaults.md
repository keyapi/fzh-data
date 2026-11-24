---
okf: v0.1
type: Research
title: 补货与需求协同的可配置默认值建议
timestamp: 2026-11-24
status: proposed-not-activated
tags: [replenishment, defaults, service-level, freshness, fva, governance]
---

# 补货与需求协同的可配置默认值建议

建议沿用已有 `balance` 分档、每周复核和人工异人审核，先做 USNJ 影子试点。本文只给配置决策，不修改业务代码、不部署、不激活参数；“已审核需求”也不自动获得采购资格。所有数值阈值是可回退的**试点建议**，并非行业统一标准或已验证的最优值。

## 事实、推断与未核实项

- **已确认约束（任务输入）**：自有工厂无 MOQ；不自动下单、不写 EN 业务数据；运营与审核分离、禁止自批；未知不填 0；USNJ 试点 296 行；老板要求运营判断和逐周调整，逐周功能由另一任务负责、尚未完成。
- **已核项目文档事实**：[D38–D40][P1] 要求最新快照向前计划、β 主报/α 辅报、周期复核覆盖 L+R、分位数不等于满足率。[评价协议][P2] 要求同政策比较服务与库存。[分型经验][P3] 要求先排费用/组件、全渠道分型、禁止稀疏检查点冒充连续缺货。
- **时点事实的来源边界**：[私有路线复核][P4] 记载 D5 基准 11/11、USNJ 建议 11/13、当时库存 11/23；每日 05:17 和 W1 可能停在 10/27 来自本任务输入，未现场查询 EN/调度器。11/24 对 10/27 的 SO 证据龄为 28 天，不能因今天重新下载而变新。D5 97/157 天都是整期，不能改名为剩余期。
- **历史实验，非本轮实测**：[服务预设分支文档][P5] 报 USNJ 296 键：全 q95 建议量 7,945，balance 4,180，control 3,815，service 5,496；7,945→4,180 约少 47.4%。这是 11/12 包内建议件数对照，**不是**11/13 包复算，不是实际平均库存/资金降低，也没有证明服务不退化。其特殊品/CNY/归属名单可重叠，不可相加推导隔离行数。
- **资产存在但未验收**：本工作树未包含下列业务模块，通过 `git show` 只读核查其他分支：[Supply Copilot 与台账][P6]、[refresh 批量入口][P7]。refresh 复用 D5、不重训；README 的显式等长期间条件不足以证明新期间有效，必须另证起止日与重算方法。真实会话、行级权限及周拆分是否已集成仍未核实，本文不是已实现声明。
- **推断**：沿用现成分档比全量 q95 更适合作为低侵入起点；长交期下 6 周足够检查协作，但不足以证明一个完整补货周期的收益。

## 统一配置与权限约定

表内“范围”是建议允许配置的范围，并非历史观测区间。所有参数均进入版本化配置，优先级为“显式 SKU×分公司例外 > 分公司×商品分型 > 分公司 > 全局”；未匹配回到上层，**未知事实不通过继承变成 0**。SKU 例外还必须带仓/库存池、形态、UOM、期间，避免跨形态串用。

角色简称：**运营 O** 提案；**审核 R** 在授权范围批准；**财务 F** 审核金额/预算口径；**管理员 M** 管身份、配置发布及回退。业务参数由 O 提、异人 R 批，M 可代发布但不代替业务批准；财务参数加 F。下表写“R”均指此流程。权限变更须不同的 M 或指定独立权限审核人复核，无第二人则保留旧配置。

每次变更保存 `config_version/parent_version/key/scope/old/new/unit/reason/evidence/author/approver/effective_at/expires_at`，每次运行固定配置哈希、输入包哈希、各源业务 as_of、模型/期间/名单版本。默认下一个周版本生效；紧急修改也产生新版本并撤销受影响审批。回退发布一个指向旧值的**新版本**，不删日志、不覆盖历史快照，不把旧数据伪装成新数据；配置发布失败保留上个有效版本并标失败。例外默认 7 天到期，允许 1–28 天，R 可改；到期回上层政策，相关未执行判断重新计算审核。

不可突破的硬约束也显式登记为受保护配置：`auto_order=false`、`write_en_business=false`、`allow_self_approval=false`、`unknown_as_zero=false`，允许集合均为 `{false}`。管理员不能通过配置解除任务约束。回退同样受这些约束检查。

## 默认值建议表

依据栏 P 为项目证据、S 为外部来源；标“建议”的具体数字均为顾问选择，来源只支撑方法，**不声称来源规定该数字**。

| 参数名 | 默认值 | 允许范围 | 作用域 | 谁能改 | 影响与失效方式 | 依据 |
|---|---|---|---|---|---|---|
| `segmentation_basis` | 优先复用已冻结 ABC×XYZ→A/B/C/D；无有效映射标 unknown | 已审核分型版本；不得用未来留出销量分型 | 全局/分公司/商品分型 | R | 不按名字把“正常”直接等同 A；缺分型不给确定动作 | [P3][P5]；[S1] |
| `abc_breaks` / `xyz_basis` | ABC 按已证全渠道销量累计 80%/95%；XYZ 复用训练期 smooth/intermittent/lumpy 等标签 | 两有序分界 0–100%；XYZ 方法及阈值须成套版本化 | 分公司/商品分型 | R | 无可靠成本不冒称金额 ABC；零销量/短史独立；不新造 CV 阈值；缺全渠道覆盖标条件 | 建议沿用 [P5]；[S1] 支撑价值/波动双轴 |
| `service_beta_target` | A 95%、B 90%、C 85%、D/短史 90%（探索目标） | 80–99%；其外只能单列研究情景 | 分公司/商品分型 | R | β 是即时满足单位/有效需求单位；D 目标不代表 q85 已达标；不达标报缺口，禁止自动调 q 凑目标 | 建议；[P1][P2] |
| `service_alpha_target` | 未设硬门槛；有有效周期时辅报 α | null 或 80–99% | 分公司/商品分型 | R | 周期不可定义则不可评，零需求周期单列；不由 β/q 换算 | [P1][P2]；[S2] |
| `quantile_preset` | balance：A q95、B q90、C q85、D q85 | 先仅 q85/q90/q95；新增分位须校准及新版本 | 分公司/商品分型，SKU 例外 | R | D q85 仅条件候选，非 β 认证；正常/慢销/长尾按已证 ABC×XYZ 再映射，短史进 D；分型 unknown 则 HOLD | [P5]；[S1][S3] |
| `q95_downgrade_gate` | 2 次周评出现“更低 q 在同一有效样本达到该档 β 目标，平均库存或可靠资金低 ≥10%”则提降 1 档；q95 相对 q90 库存 >1.5 倍先告警 | 观察 2–4 次；改善 0–30%；告警比 1.1–3；一次只降 1 档 | 分公司/商品分型 | R | 仅触发提案，不自动降；未达到 β 目标仅能显式提出降低目标的风险方案，不能称等服务节省；样本不足不作已证结论 | 建议；[P2][P5][P8] |
| `hard_service_infeasible` | 不承诺硬 95%；并列 β 90/95/99% × L 60/90/120 天 × R 7/30 天探索前沿 | 冻结网格可扩展；目标调整须显式批准 | 全局/商品分型 | R | 展示同服务少库存/同库存多满足；缺成本用件数/覆盖，不能称资金最优；加急/调拨只报人工选项 | [P1] D40；[P8] 的旧实验不可外推成普遍不可能 |
| `inventory_policy` | 每周周期复核 order-up-to 参照；ROP 仅并列告警 | order-up-to / ROP / 按已证需求 / 人工观察 | 分公司/商品分型 | R | 简单式 Q=max(0,S−IP) 仅在同口径同保护期可用；逐桶账优先，不把晚到供给提前扣掉 | [P1][P2]；[S2][S4] |
| `review_period_R` / `protection_period` | R=7 自然日；保护期=L+R | R 1–30 日；保护期随 L 重算 | 分公司/商品分型 | R | L 从释放生产/采购到可售，含生产、头程、清关、入仓加工上架；预测窗不足即未覆盖/HOLD，不外推尾部 | [P1][P2]；[S2] |
| `safety_stock_method` | 累计保护期需求分位形成 S；SS=max(0,S−同窗期望需求)；不再另叠固定安全天数 | 经验/校准分位；其他方法先并列回测 | 商品分型 | R | 各周 q 不直接相加；交期风险已进联合分布时不得再重复 p90 缓冲；需求/供给共用同一时间账 | [P2]；[S2][S3] |
| `history_fallback` | <12 月标短史 D；有已证类比则借力并列 naive；无类比/需求证据只给已接订单下界+未知增量 | 短史阈值 6–24 月；已审核类比/层级/观察 | 商品分型/SKU | R | 不把“无统计建议”写成补 0；不承诺最低服务；组件跟 BOM；清仓停补需独立已证状态 | 建议继承 [P3]；[P2]、[S5] |
| `hard_budget` | null，无硬预算截断 | null 或带币种/周期的非负金额 | 分公司 | R+F | 缺成本金额为 unknown；不得因 null=无限而取得采购授权 | [P1][P2] |
| `soft_budget_warning` | 相对最近已批同范围周计划金额 >120% 告警；分母无效则对同范围数量变化 >20% 告警 | 金额/数量阈值 10–100%；可另设绝对金额 | 分公司/商品分型 | R+F | 软提示不自动削量；基准为0且新量>0单列“新增”；无可比基准标不可比，跨SKU件数不当资金 | 建议；[P2] |
| `moq` / `order_multiple` | 自有工厂 MOQ=null（明确无约束时可0）；箱倍数 null，不强制凑箱 | MOQ null/非负整数；倍数 null/正整数 | 分公司×SKU×供应商/包装版本 | R（供应商/包装负责人举证） | 外购供应商合同最低量、不可拆外箱才启用；保留原净需求、取整增量与原因；未维护字段不能作硬约束 | [P3]；[S4] |
| `lead_time_quantile` | 同路线/模式/目的可售仓的端到端 L p90 | p50–p95；自然日/营业日历必须注明 | 分公司/路线/商品分型 | R（物流负责人举证） | 不叠加各段 p90 冒充全程 p90；未到货记录保留删失/延误标记；过度保守需前沿对照 | 建议；[P2][S3] 支撑交期风险，不规定 p90 |
| `lead_time_evidence` | 最近12月 ≥20 条已完成可比交期才直接作经验 p90；不足先借已批同路线；再无则仅 L=60/90/120 情景（90为展示中点） | 回看6–24月；最低10–50条；有据人工交期可例外 | 分公司/路线 | R | 20 条只为试点资格，不保证尾分位可靠，仍报样本量/不确定性；情景90不是事实 ETA；无可信 L 不给确定日期/量 | 建议；[P1][P2] |
| `eta_unknown` / `po_on_time` | 分段缺头程/到仓/上架证据则 ETA=unknown；仅 ETA可售 ≤ 需要日 且数量、仓、UOM已证才 true | true/false/unknown 三态；比较口径固定受保护 | 全局/分公司 | R 可改证据策略，不能取消比较 | ETA>需要日为false；日期/数量任一未知则unknown；已证在手不受未关联PO缺ETA牵连；未知供给不能算0或及时到货 | [P1] D39；[P2][P7] |
| `inventory_refresh` | 每日05:17快照，05:45检查完成；冻结/审核前再次只读校验 | 每日1–24次；完成宽限15–120分钟 | 分公司 | R+M | 时区 Asia/Shanghai，可售仓日历另列；库存龄用源快照业务时点，不用下载时间 | 05:17来自任务；其余建议；[P6][P7] |
| `demand_recommend_refresh` | 每周一06:00刷新需求/建议；事件发生或审核前按需重算 | 每日–每14日+按需 | 分公司/商品分型 | R+M | 失败保留旧版并显式陈旧；库存刷新不能更新 forecast_as_of；不重复提交旧建议为新预测 | 建议；[P4][P6][P7]；[S6] |
| `inventory_age` | ≤24h可用；>24h WARN/条件；>48h HOLD | 警告12–24h；HOLD 24–72h且晚于警告 | 分公司 | R+M | WARN 不给确定建议；HOLD 只展示旧版/情景，不可批准；单行/仓局部隔离，不能全表填0 | 建议；[P1] D38 |
| `forecast_age` | ≤7d可用；>7d WARN/条件；>14d HOLD | 警告1–7d；HOLD 7–28d且晚于警告 | 分公司/商品分型 | R+M | 同时检验目标期间；新鲜但期间错仍HOLD；仅改文件日期不能解除 | 建议；[P4][P6][P7] |
| `so_evidence_age` | ≤7d可用；>7d WARN/条件；>14d HOLD（仅依赖它的行/结论） | 警告1–7d；HOLD 7–21d且晚于警告 | 分公司 | R+M | 证据龄按抽取覆盖时点，不能按 SO 创建日；10/27证据在11/24为28d，应HOLD相关净额/催已有，其他证据充分行继续 | 建议；[P4][P6] |
| `critical_unknown` / `readiness` | 必要身份/库存/源期间/供需去重/可售ETA未闭合则HOLD；警告最多“条件” | 研究/条件/已确认；采购资格本试点恒false | 全局/分公司 | R只能补证后改状态 | 刷新完成不自动确认；人工签字不能造事实；D5整期不得平移为剩余期，需重预测或有据逐桶重算 | [P1][P6][P7] |
| `operator_scope` | O仅在显式分公司∩商品分型∩负责人授权交集读写提案；USNJ白名单内 | 显式列表；空范围=拒绝，禁止通配继承 | 分公司/商品分型/负责人 | M+独立权限审核人 | 列表、详情、导出、提交均按行校验；负责人未知隔离，不默认归USNJ | 建议；[P3][P4][P6] |
| `reviewer_scope` | R仅审核授权范围且 actor≠提交者；兼任角色也禁自批 | 显式列表；自批开关仅false | 分公司/商品分型 | M+独立权限审核人 | 越权/自批拒绝并留审计；审核不等于采购授权 | [P4][P6]；任务硬约束 |
| `system_manager_scope` | M管配置/账号/审计；默认无全量业务读权和业务审批权 | 最小权限授权集；空业务范围=拒绝 | 全局/分公司 | 独立权限审核人 | 配置不得绕过行级范围、异人审核及EN只读边界；现场未核实的权限不得说已上线 | 建议；[P4][P6] |
| `pilot_scope` | 冻结 USNJ 296 行源名单；逐行分合格/条件/HOLD/拒收，不能因筛掉变小而漏账 | 仅版本化显式名单；本试点不扩其他分公司 | 分公司/SKU | R（扩大范围另立批准版本） | 输入=接收+拒收+跳过；接收再按readiness拆分，理由可追溯；D5 1513行/USNJ277不与296混母集 | [P4][P5][P7] |
| `pilot_window` | 6周影子协作；第2周流程复核、第4周中评、第6周结项；不足延至8周 | 4–8周；完整交期观察另行延长 | 分公司 | R | 从首份有效冻结版计时；6/8周可能均短于L，不声称完整补货收益；长交期结果待实际到货成熟后另评 | 建议；[P2][P4]；[S6] |
| `special_cny_owner_hold` | 特殊品、CNY受影响、归属待定逐行隔离默认HOLD | 按证据逐行解除；不得一键全放行 | 分公司/商品分型/SKU | R+对应产品/物流负责人 | CNY需已证停复工与首批可售日期及bridge覆盖；不得把97/157天硬作bridge；非受影响行继续 | [P3][P4][P5] |
| `fva_window` | 冻结后未来滚动4个完整周，累计8周复核；按同SKU/仓/UOM/跨度成对比较 | 4–12个完整周；分组至少4个成熟周切点，否则描述性 | 分公司/商品分型/调整原因 | R | 只评分需求已到期且实际已结清的桶；重叠跨度不当独立样本；完整L+R决策效果另等成熟；缺真值不可评 | 建议；[P2]；[S5][S7][S8] |
| `fva_metric` | 主报 FVA_WAPE=WAPE_auto−WAPE_final；另报各阶段FVA、Bias、β/平均库存前沿、工作量、改动率 | 冻结定义，可增加MASE/pinball，不可事后换冠军指标 | 全局/商品分型 | R | 正FVA为改善；WAPE=Σ绝对误差/Σ实际，Bias=Σ(预测−实际)/Σ实际；零分母/缺失不可评，销量删失不当真需求；不称1−WAPE准确率 | [P2]；[S7][S8] |
| `override_degradation` | 连续2次成熟4周窗 FVA<0 提醒复核该原因/分组；β比冻结auto低>2百分点或库存高>20%同样提示 | 观察2–4次；β容忍0–5百分点；库存10–50% | 分公司/商品分型/原因 | R | 不按个人小样本处罚/自动撤权；窗口重叠只作预警，非显著性证据；人工保留须补新证据 | 建议；[P2][S7] |
| `accept_auto` | 默认无改量草稿；运营须显式“接受”提交，仍异人审核 | 接受/改量/改期间/报事件/待核 | 分公司/行 | R定义流程；O选择动作 | 不点击/超时不当同意；保留自动基准供FVA；接受不能解除HOLD | [P4][P6]；[S5] |
| `override_quantity` | 改量须说明总量/增量/比例、原因、证据、有效期间；默认不叠加同范围提案 | 非负最终需求；有符号增量但结果≥0；禁止负补货量 | 行/源期间 | O提、异人R批 | 同范围冲突显式裁决；改动绝对比例>20%或从0改正量优先复核，但不是小改免审；无证据草稿待核 | 建议阈值；[P6][S5] |
| `override_priority_threshold` | 数量改动绝对比例20%；基准为0且新量>0直接优先复核 | 10–100%；零分母分类规则成套版本化 | 分公司/商品分型 | R | 只改变审核排序，任何改量仍须异人审核，不以阈值阻止有证据的大调整 | 建议；[P6][S5] |
| `event_only` / `period_override` | 只报事件不强迫估量，默认不改数字；改期间先重算，不平移总量 | 事件带开始/结束/范围；期间须有源依据 | 行/商品分型 | O提、异人R批 | 总量/增量分开；同事件ID去重；过期不延续，原始提案保留；不可凭97天均分周 | [P4][P6] |
| `weekly_grain` | 最小7自然日，周一至周日；只对有逐周证据/已披露分配方法的需求开放 | 7/14/28日；日粒度须另证数据支持 | 分公司/商品分型 | R | 周桶、源期间、时区固定；守恒Σ周量=对应期间总量，部分周单列；无周依据只看整期，功能未完成前保持禁用 | 建议；[P6]；[S6] |
| `weekly_freeze` | 周三12:00 Asia/Shanghai冻结；周二18:00运营提交、周三11:00审核截止 | 工作日/时间可配，截止顺序必须递增 | 分公司 | R+M | 逾期入下周或显式紧急新版本；未审/冲突不混入冻结量；冻结后禁止原位改写 | 建议；[P4][P6]；[S6]周节奏，不声称周三为标准 |
| `reapproval` | 任一数值/期间/归属/配置/输入源版本改变，或审批后>7天仍未采用，标需重审 | 有效期1–7天；陈旧阈值更严格者优先 | 分公司/行 | R | 来源刷新不能沿用旧哈希审批；与依赖无关的行不全表撤销；重审前沿用旧版仅展示，不得作为新确定建议 | 建议；[P4][P6][P7] |

## q95、交期与人工判断的解释边界

复用 [P5] 时必须区分 ABC 价值档与最终服务档：ABC的 A(X/Y)→服务A，A(Z)/B(X/Y)→服务B，B(Z)/C(X/Y)→服务C，C(Z)/零销量/新品/淘汰/短史→服务D。XYZ原标签为 X=smooth、Y=intermittent、Z=lumpy/erratic/n/a（生命周期标签另优先处理）。该映射及80/95分界也属于整套可配置政策，不把它当通用行业定律；若只掌握正常/慢销/长尾分型而无法验证对应关系，则保持条件候选，不能强行贴ABC。清仓/淘汰已证的停补规则先于D档分位候选。

[旧服务实验附件][P8] 报告：其名义 τ95 配置在6个历史模型/样本格中仅1格实现 β≥95%，库存相对其基线为1.3–14.2倍。这是特定 lost-sales 模拟、训练乘数与评审切点的结果，既不是本批 USNJ 的预测 q95 校准，也不证明任何未来政策都无法实现95%。它与 [P5] 的建议件数对照共同支持“不能全量硬上 q95，必须报服务—库存前沿”，不能支持“降 q 一定无损”。

优先用已证需求/供给路径对 q85/q90/q95 在相同起始库存、同一需求、同一交期、同一政策下比较。没有一条候选能满足目标时，报告实际达到的 β、未及时满足单位、库存与加急选项，由异人审核接受显式风险；不把 q95 文案改成“95%保证”，也不凭预算软告警自动剪掉尾部。

`po_on_time` 的需要日是该桶真正需要**可售**数量的日期；ETA 到港/签收不等于可售。必须逐批判断，不能因为一张 PO 的最后日期在总计划期末之前就抵掉全部早期缺口。SO 是需求证据，不与 PO/生产/DN 库存阶段相加；同一订单/行与供给链阶段去重，无法确认是否重叠时局部HOLD。[P1][P7]

FVA 同时保留 naive、自动预测、运营提案、审核最终值。各步骤在同一已成熟需求桶比较；改过的行和未改行分别报样本数/销量覆盖，不能只用自选修改行证明整体收益。需求量调整和补货量调整分开评分：前者看预测损失，后者在同政策/可信供给路径下看 β、缺口、平均库存、稳定性。StatsForecast 滚动切点回测复用既有资产，不为本文另写预测库。[P2][S7][S8]

## 落地前验收（本轮仅文档检查）

1. 每个参数能查当前值、父级回退值、批准人、起效/过期、旧版本；非法值拒绝并保留旧版。用一条SKU例外验证不串仓/形态/UOM。
2. USNJ 296行完整去向；未知数值保持null；费用/组件/归属不明/CNY逐行解释；输入哈希固定，重跑可复算。不把源包数量差异抹平。
3. 对库存25h/49h、预测8d/15d、SO8d/15d、缺ETA、ETA晚于需要日、97天整期冒充剩余期各给状态反例；不允许因重新下载解除陈旧。
4. 两真实账号完成提交/异人审核，逐行越权、自批、旧版本审批、无周依据拆周均拒绝；默认拒绝直到真实鉴权验证。管理员也不能给自己制造审批资格。
5. 冻结自动/人工/最终版本与评分窗；所有跳过、不可评及原因保留；失败回退不会恢复旧采购资格。完整交期尚未成熟时明确只验协作与需求FVA。

## 来源（2026-11-24只读核查）

项目文件链接以本仓库为基准；跨分支文件用固定提交永久链接，防止把“其他分支存在”误说成本工作树已集成。未读取真实私有数据包，未跑业务回测、未实测收益。

| 编号 | 来源及核查边界 |
|---|---|
| P1 | [DECISIONS.md D38–D40](../2026-10-20/claude/control/DECISIONS.md)：本地原文已读。 |
| P2 | [INVENTORY_EVALUATION.md](../2026-10-20/claude/control/INVENTORY_EVALUATION.md)：本地原文已读，β/α、L+R、公平比较与数据不足边界。 |
| P3 | [供应分型与断货证据](../../../solutions/workflow-issues/supply-sku-segmentation-and-stockout-evidence.md)；[先搜再造](../../../solutions/workflow-issues/search-first-before-implementing.md)：本地原文已读。旧经验的软下限不是本次硬MOQ，本文不沿用强制7天需求下限。 |
| P4 | [私有路线复核](D:/private/demand/roadmap-review-20261124.md)：本地原文已读，不复制私有行级数据；依赖权限才能访问。 |
| P5 | [服务分档与USNJ预设](https://github.com/keyapi/fzh-data/blob/191a5cf6fbdbc763625b9ea159945df4095e25f6/supply_netting/docs/service-policy-20261112.md)：以 `git show keyapi/service-preset-usnj-20261112:...` 读取固定提交原文，未重跑其数字。 |
| P6 | [Supply Copilot README](https://github.com/keyapi/fzh-data/blob/666cd700adb2bc187d30c1de13a1e563314bea40/supply_copilot/README.md)、[协同台账README](https://github.com/keyapi/fzh-data/blob/666cd700adb2bc187d30c1de13a1e563314bea40/demand_collaboration/README.md)、[AGENT_HANDOFF](https://github.com/keyapi/fzh-data/blob/666cd700adb2bc187d30c1de13a1e563314bea40/demand_collaboration/AGENT_HANDOFF.md)：以 `git show feature/supply-copilot-release:...` 读取；不是生产权限验收。 |
| P7 | [refresh批量入口README](https://github.com/keyapi/fzh-data/blob/3efd58054ae22bece43e0533015ae90fa33f6f81/supply_copilot/README.md)：以 `git show feature/supply-refresh-batch:...` 读取，期间/去重/报告能力是分支文档记载，未运行验证。 |
| P8 | [服务—库存实验附件](../2026-10-20/claude/control/reviews/2026-10-23-service-inventory-annex.md) §2–4：本地原文已读，特定旧模拟结论，不推广为普适定律。 |
| S1 | [SAP ABC/XYZ Analysis](https://help.sap.com/doc/saphelp_scm700_ehp02/7.0.2/en-US/4d/33d92edb9e00d3e10000000a42189b/content.htm)：官方检索正文说明价值/波动双轴、不同类应用不同预测策略；不规定本文百分比分界。 |
| S2 | [MIT库存课程总结](https://ocw.mit.edu/courses/15-763j-manufacturing-system-and-supply-chain-design-spring-2005/e1800430fdccaf618b22bd551fc00fac_summary.pdf)：本轮读取PDF文本第5页，明确周期order-up-to/连续ROP、安全库存覆盖交期加复核期、周期缺货概率与fill rate分开。 |
| S3 | [SAP Safety Stock and Reorder Level](https://help.sap.com/docs/SAP_ERP/66326f67e0e1416d83c0fdfa4060189d/a06db6531de6b64ce10000000a174cb4.html?locale=en-US&state=PRODUCTION&version=6.18.latest)：官方检索正文，高服务目标、交期和预测误差影响安全库存；支持风险/库存权衡。 |
| S4 | [Microsoft补货方法与数量修正](https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/replenishment-methods-quantity-modification)：网页正文已读，区分周期/按需求/min-max/manual，最低量与倍数独立配置；不证明自有工厂有MOQ。 |
| S5 | [Hyndman & Athanasopoulos, FPP3 第6章](https://otexts.com/fpp3/judgmental.html)：作者原文已读，额外信息、结构化记录与复评支持人工调整；小幅无证据改动容易有害，不构成禁止运营判断。 |
| S6 | [ASCM: Direct Your Supply Chain Plans to Execution](https://www.ascm.org/ascm-insights/direct-your-supply-chain-plans-to-execution/)：官方检索摘要定义S&OE为每周或更频繁执行协同；原页403，未核全文。本文周节奏是S&OE，不能说传统月度S&OP必须每周或周三冻结。 |
| S7 | [SAS: FVA Analysis Step-by-Step](https://www.sas.com/content/dam/SAS/en_us/doc/whitepaper1/forecast-value-added-analysis-106186.pdf)：官方检索正文支持逐过程与naive/自动统计基准比较；本文不采用其“100%−MAPE”呈现。 |
| S8 | [Nixtla StatsForecast模型选择与交叉验证](https://www.nixtla.io/blog/statsforecast-automatic-model-selection)：维护者检索正文说明滚动切点、训练仅用当时历史；不规定本试点4/8周阈值。 |

[P1]: ../2026-10-20/claude/control/DECISIONS.md
[P2]: ../2026-10-20/claude/control/INVENTORY_EVALUATION.md
[P3]: ../../../solutions/workflow-issues/supply-sku-segmentation-and-stockout-evidence.md
[P4]: D:/private/demand/roadmap-review-20261124.md
[P5]: https://github.com/keyapi/fzh-data/blob/191a5cf6fbdbc763625b9ea159945df4095e25f6/supply_netting/docs/service-policy-20261112.md
[P6]: https://github.com/keyapi/fzh-data/blob/666cd700adb2bc187d30c1de13a1e563314bea40/demand_collaboration/README.md
[P7]: https://github.com/keyapi/fzh-data/blob/3efd58054ae22bece43e0533015ae90fa33f6f81/supply_copilot/README.md
[P8]: ../2026-10-20/claude/control/reviews/2026-10-23-service-inventory-annex.md
[S1]: https://help.sap.com/doc/saphelp_scm700_ehp02/7.0.2/en-US/4d/33d92edb9e00d3e10000000a42189b/content.htm
[S2]: https://ocw.mit.edu/courses/15-763j-manufacturing-system-and-supply-chain-design-spring-2005/e1800430fdccaf618b22bd551fc00fac_summary.pdf
[S3]: https://help.sap.com/docs/SAP_ERP/66326f67e0e1416d83c0fdfa4060189d/a06db6531de6b64ce10000000a174cb4.html?locale=en-US&state=PRODUCTION&version=6.18.latest
[S4]: https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/replenishment-methods-quantity-modification
[S5]: https://otexts.com/fpp3/judgmental.html
[S6]: https://www.ascm.org/ascm-insights/direct-your-supply-chain-plans-to-execution/
[S7]: https://www.sas.com/content/dam/SAS/en_us/doc/whitepaper1/forecast-value-added-analysis-106186.pdf
[S8]: https://www.nixtla.io/blog/statsforecast-automatic-model-selection
