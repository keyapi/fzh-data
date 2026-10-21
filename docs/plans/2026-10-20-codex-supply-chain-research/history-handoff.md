---
okf: v0.1
type: Reference
title: 已找回预测资产与用户确认的产品边界
date: 2026-10-20
---

# 已找回预测资产与产品边界

## 来源与证据范围

用户补充并确认 [PR #304](https://github.com/keyapi/fzh-data/pull/304)，分支 `claude/gifted-ptolemy-bc923f`，本轮读取时 OPEN，固定提交 `74d78faa899596c1d16b07ea00b38be373a928a2`。通过git show读取未合并文件，未将其分支合入本研究；不要仅在main搜目录而再次报告“未找到”。

已读：

- [会话重建纪要](https://github.com/keyapi/fzh-data/blob/74d78faa899596c1d16b07ea00b38be373a928a2/docs/research/2026-10-20-demand-forecast-session-reconstruction.md)。
- [数据可行性](https://github.com/keyapi/fzh-data/blob/74d78faa899596c1d16b07ea00b38be373a928a2/docs/research/2026-08-31-demand-forecast-data-feasibility.md)、[实用路线](https://github.com/keyapi/fzh-data/blob/74d78faa899596c1d16b07ea00b38be373a928a2/docs/research/2026-08-31-demand-forecast-practical-paths.md)。
- [PB脚本](https://github.com/keyapi/fzh-data/blob/74d78faa899596c1d16b07ea00b38be373a928a2/pb_reconciliation/sku_forecast.py)、[口径与方法说明](https://github.com/keyapi/fzh-data/blob/74d78faa899596c1d16b07ea00b38be373a928a2/pb_reconciliation/docs/reference/sku-forecast.md)。

这是对归档文件和代码的阅读；没有恢复已删除的原始会话，没有重查43张表/生产物料数量，也没有运行仓外PB真实文件。重建文档中的历史事实按其证据范围引用，不等于本轮独立重测。

## 用户确认后必须继承的约束

| 项 | 当前状态/执行含义 |
|---|---|
| 阶段A | 数据可行性已完成；当时记录通途202301–202607连续43个月表及EN产品映射。当前访问权限、覆盖完整性和字段质量需启动时刷新 |
| 阶段B | 未启动、未拍板，未建demand_forecast目录；不能把技术方向写成已上线、已排期或已验证公司级模型 |
| 预测技术方向 | 分段 + 全局LightGBM + Croston/TSB等长尾/生命周期兜底 + Conformal区间 + 物料组调和；作为已有方向继续验证，不重启无边界模型选秀 |
| TSFM | **现阶段不采用，也不加入当前实验候选。** #301保留Chronos/TimesFM/Moirai等SOTA和许可资料作研究储备；研究进展不撤销产品决定。以后变更需用户明确调整范围 |
| 断货与人工例外 | 断货期必须打标，不当普通0；保留补货同事可录入、带理由的例外层。低库存登记值不直接等同断货事实 |
| PB样例 | M1运行率、M2同比、M3线性趋势、M3b季节平均是特定PB样例，不是公司级模型。原结果只适用当时数据截止和窗口，重跑会变 |
| 凭证与输出 | 凭证只在父检出已忽略文件；业务输出在仓外sales_forecast目录，不提交、不复制进公开研究。旧脚本硬编码本机数据路径，不当公共读取层 |
| 头程 | PJ/Jack正在清理敏感内容，未交PR；不能推断无数据或访问其未交付资料。继续独立研究底层获取和EN关联，不等大屏交付 |

## 时间线与不可恢复边界

归档纪要说明8月31日产出PB基线、方法现状和数据可行性；**practical-paths实际创建于9月2日17:35**，接在当天最后一条160字消息之后。frontmatter日期仍为8月31日，不能据此把路线文档的创建时间写错。原消息内容与完整讨论过程已不可恢复；只保留“PB基线→方法→数据→路线”的四段顺序，不补写被删对话。

## 复用前的代码与历史假设检查

| 资产/说法 | 实际限制 | 当前处理 |
|---|---|---|
| sku_forecast.py读取层 | 固定本机glob/工作表/列位置，按发票H/D行读取并以PO日期汇总，近期未开票会漏入样本；不是统一终端订单面板 | 复用方法原型和列语义，阶段B先建列名合同、显式as_of/成熟度和来源血缘，不复制硬编码路径 |
| M1最近12月 | dense_months只从首个销售月补到最后销售月，不自动延伸到观察截止；尾部无销售可能消失 | 截止时点与在售日历独立构造；区分无需求、缺货、停更、未开票，不静默补零 |
| M2同比与M3趋势 | 同比的YTD固定1–6月；趋势按历史长度继续外推而非显式起始日期间隔 | 只作为旧样例基线；冻结预测原点、训练窗口和未来跨度后才能重用，不能当通用回测器 |
| M3b季节平均 | 会纳入预测年份数据且只保留正销量；历史零被排除可抬高均值，错误时间切分有泄漏风险 | 截止时点前的有效历史才可参与；缺货与真实零分别编码，保留偏差说明 |
| 区间与建议备货 | 各方法mid±25%、推荐加约20%是人为启发式；未扣现有库存/在途/MOQ或资金 | 不称概率/Conformal区间，也不直接升为净补货命令；模型区间、业务缓冲和净需求分开 |
| “剥后缀即可映射” | customer_items.ref_code是已知入口，但Cover/Foam角色、客户组、历史SKU改名、单卖部件与套件均影响物理单位 | 完整精确映射优先；剥后缀仅产生候选，角色/单位/同产品核对后才能归一，保留未匹配 |
| “可用库存≤0就是断货月” | 与后续通途报溢/登记语义及赛狐成本库存证据冲突 | 必须交叉在售/可售日、断货记录及收发证据；历史可行性结论不证明当前标签已可靠 |
| “LightGBM Tweedie天然解决零膨胀/新品” | 目标函数与跨序列学习不自动解决停售/删失/新品样本缺口 | 分段、生命周期/缺货语义及滚动回测分别验证；不以旧综述中“现代默认”当性能证明 |

这些限制不要求修改#304归档；本研究记录从历史原型转为公司级方案时的验证门槛，避免改写历史或重复造轮子。

## 当前方向的官方实现依据（补核，不是运行结果）

| ID | 原始来源/访问日2026-10-20 | 能证明与不能证明 |
|---|---|---|
| H1 | [MLForecast预测区间官方教程](https://nixtlaverse.nixtla.io/mlforecast/docs/how-to-guides/prediction_intervals.html)，Introduction、Train models/PredictionIntervals | 现成sklearn兼容点预测与Conformal校准窗口/逐预测跨度区间，可复用实现；不保证本公司非平稳/删失数据的实际覆盖率，也不等同安全库存已最优 |
| H2 | [LightGBM参数文档](https://lightgbm.readthedocs.io/en/stable/Parameters.html)，objective/tweedie/quantile | 核对官方参数入口，版本访问时显示4.7.0；具体目标函数和标签/特征约束仍须锁版本验证，不能用tweedie名字证明适合所有SKU |

尝试打开HierarchicalForecast方法页失败，不能据此说没有调和库；阶段B按正式版本核BottomUp/MinT、聚合矩阵、非负与区间一致性。这里没有安装或跑模型。
