---
name: supply-chain-agent
description: 分公司补货、历史销量预测、EN通途库存和已有供给的能力路由与独立运行验收。用户要求查询分公司SKU、预测、补货解释、跨机器安装或迁移整套ABCDE时使用。
---

# 供应链能力入口

## 目标

帮助非技术人员用自然语言查询指定分公司/商品的历史、需求、库存、供应与补货候选。另一个Agent应独立取数和重算，不依赖项目主的电脑或代跑。

## 第一件事：确认版本与能力

不要因为目录存在、接口200、demo或一个旧结果可读，就宣布整链可用。

```text
uv run python -m supply_distribution audit --repo . --out <私有目录>/capabilities.json
```

此命令是静态检查，不联网、不读取密钥、不计算补货；即使完整也不证明运行通过。`blocked/partial`要给人解释缺什么，不能显示成“无需补货”。

如当前分支没有该命令，先读AGENTS.md与对应模块README，确认发布分支/提交；不要擅自从旧PR拼接执行。

## 配置

- 用自己的EN API凭证；标准变量`ERP_BASE_URL`、`ERP_API_KEY`、`ERP_API_SECRET`。不要把值写进对话、Git、错误报告或命令参数。
- 凭证文件只放本机私有目录或被忽略的`EN_API/.env`，明确指定的文件不可和其他来源拼钥。
- `FZH_DATA_ROOT`只是发布包应统一采用的目录约定；旧研究脚本未必已经支持，检查参数后使用，不能设置一次就假定所有脚本可移植。
- Claude Desktop需安装用户级skill；clone本身不代表自动发现。主仓库的`setup.ps1`安装后完全退出重开。Codex需信任项目并读取AGENTS.md。

## 能力地图

| 用户想做什么 | 先读/复用 | 关键前提 |
|---|---|---|
| EN历史终端订单采集 | self_fulfilled_demand/AGENT_HANDOFF.md；python -m self_fulfilled_demand.ingest --help | 新增与历史变更分开；完整分页；旧GS历史需覆盖证明 |
| 需求规范化 | self_fulfilled_demand.canonical | SKU/单位/形态/仓映射权威；缺失保留 |
| A商品范围、B归属、C库存资格 | 批准的ABC规则资产与冻结版本；若发布集包含supply_chain_visibility/abc_inputs.py则复用 | 不能用Item.disabled或库存出现代替业务批准 |
| 查EN通途实时库存 | demand_collaboration/live_stock.py | Tongtool Stock Run完整成功，Latest同run；API权限 |
| 查已有供应及DN履约 | supply_chain_visibility的发布集、EN supply_facts/delivery_facts | 版本契约、全部分页、数量阶段去重、ETA未知保留 |
| 预测/回测/需求情景 | 发布清单指定的D入口与模型版本 | 历史与ABC资产齐备，期间明确；旧D5脚本有私有依赖 |
| 库存/供应净额 | supply_netting/AGENT_HANDOFF.md；python -m supply_netting --help | 需求与供给身份/单位/日期一致；不可把所有在途当今日可售 |
| 运营意见协同 | demand_collaboration/README.md | 总量/增量/事件分开；独立审批；不等于预测引擎 |
| 展示现成建议 | demand_collaboration.recommendation | 这是既有CSV的只读解释，不是从历史重算能力 |

缺少对应模块时属于代码尚未发布，缺少规则/历史时属于数据依赖，缺权限时属于访问失败，分别报告。

## 私有能力资产包

EN私有File可分发历史和规则，但文件可下载不代表有权访问全部资产。公共仓库不放业务行、客户资料或凭证。只读取已授权附件；匿名/非授权账户拒绝与合法账户成功应分别验收。

资产包必须覆盖全部批准商品范围及USNJ/USTX/PL；一个SKU仅作测试用例。采用`supply_distribution.bundle`时，按其manifest契约核完整性、范围和执行模式；验证通过只证明文件一致，不证明业务计算通过。

## 给人的回答顺序

1. 商品名称、通途SKU/EN号、分公司、形态、单位与目标期间。
2. 结论：可形成候选／需拍板／暂不能判断，以及数量属于需求还是建议新增采购。
3. 为什么：历史销量与覆盖、预测和区间、可用库存、已有订单/生产/在途、到货日期与不确定量。
4. 每个来源的日期/版本；缺失、陈旧、partial明确；未知不填0。
5. 可展开的单据/来源与未决问题，不默认输出一大堆内部“键”。

严禁将销售目标当预测、将采购SO当终端需求、将制造累计入库当当前可用、将FBA与分公司自发货无条件混合。不得自动下单或生产写回。

## 独立机器验收

固定同一资产版本和日期，应能先复现已知结果；再用新数据自己刷新。必须分别验证三分公司、多个SKU、无销量/断货/未知归属/拆单/部分到货等例外，不能只挑一个通过样本。

验收依次为：代码安装→权限→历史/规则下载→原始事实完整性→预测重算→净额重算→解释输出→刷新恢复。每一步保留输入/成功/跳过/失败及差数去向。未完成的阶段不得通过“旧快照回放成功”替代。
