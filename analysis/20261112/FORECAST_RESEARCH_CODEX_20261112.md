---
type: Research
title: Codex｜预测与补货方法调研
date: 2026-11-12
---

# Codex｜预测与补货方法调研

事实据简报；阈值为项目建议，非行业标准。

## 1. 计划窗／粒度

周期复盘保护窗=交期L+复盘期R，逐键/路线计算，无须整周或30天。建议日级净额、周复盘/26周滚动；13周/90天看季度执行，52周看年度季节，S&OP另看约18个月。波兰100.6天超97/98；157勿机械改154，整周展示可向上161，实际终点由供给确定。[Oracle](https://docs.oracle.com/en/industries/retail/retail-inventory-planning-optimization-cloud/24.2.301.0/ipodl/ch-Review-Approve.htm)、[ASCM](https://learningsystem.ascm.org/wp-content/uploads/2019/11/CPIM_LS_2020_Excerpt-2.pdf)

## 2. 春节

录入1/24停工、2/22复工与爬坡日历，预留原料/产能/船期，提前备货；两批各有数量/可售日。T=复工后首批经产能确认的到仓可售日+R，覆盖今日至T需求，不能止于2/7。[产能日历](https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/operations-resources)、[有限排程](https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/operations-scheduling)
联合抽样需求×日历约束交期，求累计需求qα，勿加每日分位或重复叠交期安全量。[累计预测](https://otexts.com/fpp3/practical.html#prediction-intervals-for-aggregates)

## 3. 模型／回测

间歇/块状保留Croston/SBA/TSB，季节需求比较季节朴素、ETS、Theta；LightGBM、简单集成作挑战者，无通用赢家。[模型库](https://github.com/Nixtla/statsforecast)、[LightGBM](https://nixtlaverse.nixtla.io/mlforecast/docs/getting-started/end_to_end_walkthrough.html)、[集成](https://otexts.com/fpp3/practical.html#forecast-combinations)
层级协调保总分一致，conformal校准分位，不保证每键覆盖。[协调](https://otexts.com/fpp3/hierarchical-forecasting.html)、[时序conformal](https://proceedings.mlr.press/v139/xu21h.html)
固定同键、同origin、同保护窗；特征/选模/校准仅用当时已知数据，另留最终测试段。统一采用表，消除D3b/D5分叉；naive多本身无错。看WAPE/MASE、pinball、覆盖、零需求误补；零分母单列，重叠窗口分块重采样。[滚动回测](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation)、[分块法](https://otexts.com/fpp3/advanced.html#bootstrapping-and-bagging)

## 4. 服务水平

ABC价值/缺货重要度×XYZ波动分层；95/90/85可试行，NetSuite九档默认85—98%。[分档](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_85201401162.html)
CSL看不缺货周期，fill rate看满足数量；q95是需求覆盖分位，不自动等于95%服务。单周期成本起点α=Cu/(Cu+Co)，Cu/Co为单位缺货/过量成本。[MIT](https://scx-static-assets.s3.amazonaws.com/SCx%20Key%20Concept%20Documents/MITx_SCx_KeyConcept_SC1x_FV.pdf)
长尾用层级收缩，新品用相似品，季节品计残值；统一q95忽略成本差异。不硬截q95/p50或sigma，p50可为0，截尾须重校准。

## 5. 趋势／情景

先校正缺货、节日错位与渠道变化，再比较STL+ETS/ARIMA、局部趋势或Prophet；近期加权须回测。[STL](https://otexts.com/fpp3/practical.html#weekly-daily-and-sub-daily-data)、[Prophet](https://meta.github.io/prophet/docs/seasonality,_holiday_effects,_and_regressors.html)
Adobe金额预测+6.7%、卖家备货意愿均非本品销量；Amazon30万招聘含兼职/全职，不能当需求增速。[Adobe](https://news.adobe.com/news/2026/09/adobe-us-holiday-shopping-season-to-hit-record)、[Amazon](https://www.aboutamazon.com/news/workplace/amazon-holiday-jobs-2026-seasonal-hiring-healthcare)
基准取校准预测，上/下行按同品多年同比、同类冲击与分块残差生成，注明驱动/权重未知，不统一砍量。周监控校正同比、售罄率、周转、偏差/覆盖。

## 6. 落地／验收


- P0：采用链一致率100%，两例复核，留fallback原因。

- P1：春节两批数量/可售日/保护终点齐全，逐日缺口可追。

- P2：逐日库存影子回测，供给去重且不提前抵扣；暂议WAPE较基线降≥5%、成本/误补不升；覆盖率95%单侧置信下界≥目标−1pp（容差验收，非严格95%已证），稀疏键只报层级。

- P3：业务批准服务档、成本和容差后小范围试运行。
