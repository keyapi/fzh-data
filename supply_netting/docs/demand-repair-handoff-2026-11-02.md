---
type: Reference
title: D3-D6返修结果与接手入口
date: 2026-11-02
---

# 返修接手入口

实施计划：[demand-repair-2026-11-02.md](demand-repair-2026-11-02.md)。
本轮用户授权直接执行，DeepSeek未充值期间不唤醒工头。代码在`codex/demand-repair-20261102`。

## 原成果先备份

- 私有逐文件SHA快照：`D:/Work/fzh-order-store/backups/before-codex-repair-20261102-160742/backup-manifest.json`。
- 原代码两个本地基线提交：`e3f37dea`、`0dcb766c`；第二个在隔离分支的移植提交为`eba8f923`。
- 原始Excel/Parquet及修复前运行不覆盖。私有数据不提交公开仓库。

## 代码与新产物

| 单元 | 入口 | 新结果 |
|---|---|---|
| D3b v3.4 | `scripts/d3b_history_backtest_v3_2_2026-11-02.py` | `analysis/codex-repair-20261102/D_历史归一与回测_D3b_v3_4_2026-11-02.*` |
| D5 v6.2 | `scripts/d5_time_validated_2026_11_02.py --out <新的唯一目录>` | `analysis/codex-repair-20261102/D5v6_2-full/` |
| D6 v6.2 | `scripts/d6_top50_sandbox_v5_1_2026-11-02.py --as-of 2026-11-02 --out-xlsx ... --out-report ... --manifest ... --decisions ...` | `analysis/codex-repair-20261102/D6v6_2-final/`；`D6v6-final/`已被观察行数量反例否决，v6.1仅修行动量，尚用旧库存 |
| EN库存冻结导出 | `scripts/export_en_inventory_snapshot.py --out <新的唯一目录>` | `analysis/codex-repair-20261102/C-source-20261102/`，GET只读，Parquet与来源运行清单 |
| C库存规则刷新 | `scripts/tongtool_inventory_rollup_a337_v14.py --run-mode refresh --date 2026-11-02 --stock ... --cg-cache ... --b-attribution ...` | `analysis/codex-repair-20261102/C-refresh-20261102-v2/`；新库存沿用A/身份/单位/仓池规则重算；历史固定行号测试不冒充本次验收 |
| 交期证据 | `scripts/leadtime_refresh.py --local-evidence --shipment-csv ... --dn-csv ... --out-dir ...` | 新目录中的逐条证据与计数，不访问网络 |

上述相对结果路径的私有根为`D:/Work/fzh-order-store/`；D5目录中有`forecast.parquet`、`historical_windows.parquet`、工作簿、report和manifest。
D5 v3.1旧入口仅修分层键和分位公式，其旧校准协议仍是探索版；不得再用它承诺服务水平。

## 已落实的关键决定

- 源表month仅作分区标签；训练和实际都用sale_date。414,189行中22,100行源分区与事件月不同，0个未知日期；原字段保留。
- 零误差模型参与比较；模型只比较共同可评估窗口；训练保留删失月份位置，缺观测不填0。
- D5每个origin在当时已知数据内选型；校准窗口结束后才可用于后续origin。每键不足30个样本时使用同仓池/形态/UOM分层池，不把稀疏键当已充分验证。
- 同一分位函数用于评估、预测表、服务表及D6消费。明确区分历史窗口覆盖与未来服务承诺。
- D6催货量、新增量并列；净额使用同一个97/157天总需求分位，不混50天均值与97天安全量。
- 在途不再重加生产；运输从本分公司目的地、主运输和尾程样本取证。生产与头程独立抽样只是情景，不是实测联合分布。
- 未知波兰主运输不借美国空运样本；没有成本时只作紧急程度候选。普船能赶上时不无条件推荐最快空运。
- CG按已授权owner情景抵扣，不补CG，不跨仓直发，自有工厂成品MOQ=n/a。未来库存不消费；CG还必须满足逐行资格，不能只看文件生成日。
- 独立回读发现372个观察行中138行仍被后续舍入逻辑填入新补数量，合计5,156；已改为行动导出的单一来源，观察行行动量为空，保留诊断缺口。旧D6 v6不能作为正确数量结果。

## 结果解释与后续门禁

D3最新为1,853条需求序列、1,421 eligible、1,093有可比origin、788 adopted，新方法38条；这是探索选型结果。
D5 v6.2全量共3,706条当前预测（每键两个窗口）。名义95%分位历史覆盖约97天95.4%、157天94.8%；非重叠日期子集约95.5%/94.4%。
这些不是未见未来数据的验证；历史身份桥也是当前证据回溯，不是逐历史时点批准记录。没有宣称单SKU95%保证。

本次已只读导出EN完整库存运行：通途`20261102T051800`、5,318行；CG `20261102T072017`、456行，含104汇总行。通途观测时间05:18、CG观测时间07:20（北京时间）。
CG所有104汇总行仍被上游标为stale；原始汇总439、分仓合计439仅证明数量对账，不证明当前可用。C资格为0 eligible /104 pending，保留陈旧检查失败，不把它改成PASS。
C刷新六桶合计5,318行、available数值和10,360,129，行量守恒；这是跨异质原始行的核对总数，不是可下单产品的库存总量。19项10/28固定fixture明确不适用于新快照。
D6是待人工复核的情景候选，auto_order恒false；未抵扣CG的保守场景不代表实际CG库存为0，修复后数量也不能免审核直接下单。
v6.2独立回读：1,853键、374观察行的三类行动量全部为空；90个键保留CG未知标记；有效CG抵扣0。新补35,261、催已有6,561.67仅为该政策/数据情景下候选合计，不是正式下单量。38处输入/输出路径SHA核对一致。报告中的快照fresh只指观测日期，CG业务stale仍单独保留并阻止抵扣。
接生产仍需：复用Jack合格供应事实替代旧聚合PO/在途的启发式；对账目的仓、数量、重叠和可用日期；解决实际CG来源陈旧；独立核实际运行结果。
Jack的远程分支已推进到`68533017`，新增ABC接入/Parquet发布等实现；本轮仅核实其变更存在，尚未并入或完成本轮独立验收，不能继续按早期版本描述为“尚无Parquet”，也不能据此宣称端到端已接通。
现有Orca监工脚本/调度未在本轮恢复或扩大权限，不承诺无人值守闭环。

## 下一步按依赖推进

1. 固定本轮A/B/C/D版本与逐行拼接资格，输入已更新的C及D5；合格与待核分别保留，不要求全部SKU清零未知才继续。
2. 在隔离分支审核Jack `68533017`的ABC读入、来源身份与批次去重、Parquet发布/失败保留旧latest逻辑，使用同一冻结A/B/C最小运行；不整分支盲并进当前返修。
3. 取一组已授权只读的真实SO/DN/Shipment/通途PO事实，验证已入库存不再重复算、FBA占用不分给分公司、签收与通途入库的已批准粗粒度关闭规则、未知目的仓/ETA保留未知。
4. 以新供应时间桶替换D6旧聚合PO与在途情景，输出每键需求/库存/已有供给/缺口/建议时间与数量/前提/来源；另列无法拼接的键及原因，核数量守恒。
5. 对高销量与高金额候选逐条人工审核，随后冻结辅助下单包。真实断货/积压服务效果需持续观测；不将历史分位覆盖率解释为未来不断货保证。

验证命令：`uv run --no-project --with pytest --with numpy --with pandas --with openpyxl --with pyarrow --with scipy --with requests --with python-dotenv python -m pytest tests/demand_repair supply_netting/tests -q`。
续修回归：470 passed /44 subtests passed；工作区凭证扫描739文件通过。CG的业务陈旧检查失败与代码测试通过是两回事。
独立审核原报告及旧反例见私有`analysis/external-review-20261102/`。
