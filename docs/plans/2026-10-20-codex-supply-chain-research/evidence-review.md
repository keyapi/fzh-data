---
okf: v0.1
type: Reference
title: 证据抽查与交叉评审记录
date: 2026-10-20
---

# 证据抽查与交叉评审

这是研究文档的质量核对，不是业务系统上线评审。三个研究子 Agent 独立首稿后交换审阅；主 Agent 保留判断权，没有以三家模型共识代替原始证据，也尚未阅读 Claude/Cursor 的独立深度调研成果。

## 交叉评审与处理

| 审阅 | 发现 | 处理 |
|---|---|---|
| 预测/Agent → 成熟实践 | 资金/服务权重未定，不能预设统一排序 | 作者改为Pareto/多情景，由业务确认目标后再排序 |
| 预测/Agent → 成熟实践 | Oracle软约束可能超载被误读为所有APS通则 | 作者限定为特定产品机制，其他候选逐项核硬/软约束 |
| 预测/Agent → 成熟实践 | 月度S&OP/周滚动被写得太确定，且2–4周估期无输入支持 | 作者明确周期候选，移除具体估期，改为数据门槛 |
| 成熟实践 → 预测/Agent | 先将需求折“基础件”容易混淆独立需求与BOM派生需求 | 作者分开终端售卖需求、包裹/部件、BOM派生；单卖皮壳仍可有独立需求 |
| 成熟实践 → 预测/Agent | 已生产字段需要区别工序与已提交入库 | 作者补仓库新旧口径冲突及待裁定状态；主 Agent在资产账本保持双证据 |
| 成熟实践 → 预测/Agent | 许可补充URL未进计数，某Oracle蓝图无定位 | 作者纳入许可来源/去重，删无来源例子，区分章节与摘要阅读 |
| 开源 → 资产/覆盖 | 没发现测试、测试站、生产状态被直接混同 | 仍保留“本轮未访问生产”的边界；不是给原业务实现全面背书 |

主 Agent另行修正来源状态/计数、相对链接、文档预览版冒充正式版等问题。统计数字仅按各表实际条目计算；同一页面承载多项claim不重复当多个来源，不将只读摘要宣称为全文验证。

## 主 Agent直接抽查的承载结论

| 编号 | 原始来源及定位（访问日2026-10-20） | 能支持的判断/限制 |
|---|---|---|
| M01 | [TimesFM官方README](https://github.com/google-research/timesfm)，Update September 2026 / License notice | 代码/2.5及以前权重与3.0权重许可不同；自托管与授权云路径不同。不能据代码Apache推断3.0商业自托管可用 |
| M02 | [TimesFM-3对统计法模拟比较](https://arxiv.org/abs/2610.00589)，论文摘要/版本页 | 确认原始研究存在、主题与范围；子Agent阅读正文的详细百分比未由主Agent重跑，不作为公司成效数引用 |
| M03 | [frePPLe正式release](https://github.com/frePPLe/frepple/releases/tag/9.19.0)，release标签/资产 | 可固定9.19.0 CE，不把current预览文档当稳定安装包 |
| M04 | [frePPLe Editions](https://frepple.com/editions/)，Community及Cloud/Enterprise段 | 社区物料/产能/统计预测与商业库存规划的产品边界；营销页只证明厂商功能描述，不证明真实适配效果 |
| M05 | [9.19.0库存屏源文档](https://raw.githubusercontent.com/frePPLe/frepple/9.19.0/doc/user-interface/plan-analysis/inventory-planning.rst)，Important；[库存模型app](https://raw.githubusercontent.com/frePPLe/frepple/9.19.0/doc/modeling-wizard/inventory-planning/index.rst)，Important | 固定tag核查edition限制；不能把商业库存政策界面算成免费CE功能 |
| M06 | [Oracle Forecast Consumption](https://docs.oracle.com/en/applications/jd-edwards/supply-chain-manufacturing/9.2/eoarp/understanding-forecast-consumption.html)，开头及period/customer规则 | 实际订单冲减预测可避免同一需求重复计算；这是方法/产品行为，项目的窗口和订单类型仍待定义 |
| M07 | [Odoo18官方MPS文档源](https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/inventory_and_mrp/manufacturing/workflows/use_mps.rst)，开头/Important及补货设置；[18.0核心LICENSE](https://raw.githubusercontent.com/odoo/odoo/18.0/LICENSE)，前9行 | 官网页面失败后取官方源码补证，核实手调预测/建议补货及核心LGPLv3，不能据此证明MPS属于CE或EE功能免费；保留原失败URL与恢复路径 |

主 Agent打开current库存屏时标题为10.0.0；子Agent初稿一度把页面写成9.19.0，已要求改用固定tag。主 Agent尝试版本号文档路径与根LICENSE裸URL分别失败/404，没有据此认定项目无该文档或无许可证。Gitee网页抓取失败后改用只读git分支列举，结果和限制已记入assets。

## 仍未验证的主张

- 厂商/客户报告的成本节约、Agent运营改善、模型榜单胜率，不是本公司证据。
- 正式tag安装、完整许可证文件/权重卡、依赖兼容与中文/国内网络可用性尚未全面实测。
- 生产工序/入库、库存余额、头程及历史真实销售未重查；旧经验中的经验去重规则未被提升为通用事实。
- 106项离线通过只是既有代码断言；发现口径冲突时不以绿测试结束调查。新链路还需E1–E4实验，见experiments。
