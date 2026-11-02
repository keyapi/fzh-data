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
| D6 v6 | `scripts/d6_top50_sandbox_v5_1_2026-11-02.py --as-of 2026-11-02 --out-xlsx ... --out-report ... --manifest ... --decisions ...` | `analysis/codex-repair-20261102/D6v6-final/` |
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
- CG按已授权owner情景抵扣，不补CG，不跨仓直发，自有工厂成品MOQ=n/a。未来库存不消费，陈旧源标记人工复核。

## 结果解释与后续门禁

D3最新为1,853条需求序列、1,421 eligible、1,093有可比origin、788 adopted，新方法38条；这是探索选型结果。
D5 v6.2全量共3,706条当前预测（每键两个窗口）。名义95%分位历史覆盖约97天95.4%、157天94.8%；非重叠日期子集约95.5%/94.4%。
这些不是未见未来数据的验证；历史身份桥也是当前证据回溯，不是逐历史时点批准记录。没有宣称单SKU95%保证。

当前库存/PO仍使用旧冻结文件，不能把新文件生成日说成库存更新时间。D6是待人工复核的情景候选，auto_order恒false；修复后数量也不能免审核直接下单。
接生产仍需：刷新并重算C；复用Jack合格供应事实替代旧聚合PO/在途的启发式；对账目的仓、数量、重叠和可用日期；独立核实际运行结果。
现有Orca监工脚本/调度未在本轮恢复或扩大权限，不承诺无人值守闭环。

验证命令：`uv run --no-project --with pytest --with numpy --with pandas --with openpyxl --with pyarrow --with scipy --with requests --with python-dotenv python -m pytest tests/demand_repair supply_netting/tests -q`。
独立审核原报告及旧反例见私有`analysis/external-review-20261102/`。
