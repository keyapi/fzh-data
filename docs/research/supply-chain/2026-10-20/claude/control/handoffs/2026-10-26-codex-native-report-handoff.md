---
okf: v0.1
type: Handoff
title: Codex 转 Jack：原生报表、PO 入库时间与快照对账
date: 2026-10-26
owner: codex
status: reviewed-test-only
---

# Codex to Jack

用户因额度仅剩 14% 要求停止扩展、总结提交后交接。
本轮由 gpt-6-luna 子 agent 实现，Codex 多轮审核、修复并实际验证；不要将以下有限覆盖说成完整 P0 已完成。

## Entry and State

- fzh-data 分支：`feature/en-native-supply-report-plan`。从本分支读取本交接；不要先切回旧 docs 分支而丢掉本轮信息。
- EN app：`keyapi/key_test`，分支 `feature/so-chain-report-filters`，功能提交 `ef2ed83`，最新提交 `135131d`，draft PR [key_test#2](https://github.com/keyapi/key_test/pull/2)。测试服务器已部署该分支，生产未部署、未修改生产调度。
- 计划：`supply_chain_visibility/docs/research/2026-10-26-en-native-report-plan.md`；PO 参考：`tongtool_api/docs/reference/purchase-receipts.md`。
- #313 的本机数据前提已被生产实测修正；#311 已合并，#312 仍需单独核实当前状态/rebase/回归，不能因本次交接自动合并。

## Verified Facts

生产 EN 库存同步已开启；05:17 定时、14 仓、10-24/25/26 连续完整。最新表、Parquet 历史与只读历史 API 已在生产，不需要再造本地到 EN 的库存推送。
Windows 旧备份任务 Disabled 不能当作生产源停用的依据。
生产另有 05:47 的 stock_change_sync.py/stock_change.parquet，含操作时间、凭证类型/号和四库存桶增量；不要把所有变动认成采购入库。

通途 PO 查询实测有 createdDate/purchaseDate/purchaseArrivalDate；实际入库接口 `erp2_purchase_purchasestockquery` 返回 warehousingDate（秒）、PO、SKU、仓库及 warehousingNum。
头部 purchaseArrivalDate（分钟）不能替代逐条 warehousingDate，EN 的 custom_tongtool_po_created_on 也不是入库时间。
近两日、一周小窗口成功但空；随后按一个已知 PO 的到货附近窗口成功返回 2 行。原始响应只留仓库外临时文件，公开仓库不留行级数量。
响应没有独立 receipt/line ID 和 UOM；暂不具备精确自动库存回放证明。手工 PO 也须保留，不因无 EN 按钮关联而排除。

## Delivered and Tested

1. SO Chain Overview：11 个过滤器、SO 行外键关联、所选 DN 净额与全周期净额分列、权限未知值、SO/DN 单位不一致保护、按单位 KPI、固定阶段行数图；关闭跨单位自动合计行。
2. Supply Timeline：System Manager、9 SKU 的库存证据入口；通途 SKU/仓名不当 EN 键；采集起止、查询时点、来源覆盖、陈旧/未来批和缺失 SKU×仓显式显示。单位或重叠未证时 qty=null，原值仅在 evidence_qty，counted=false。
3. `tongtool_api/purchase_receipts.py`：有界只读分页、相邻请求 13 秒、526 不重试风暴、显式截断；创建/采购/入库三个时间独立保留，时区未证标识，金额不参与数量。
4. `supply_chain_visibility/receipt_reconciliation.py`：纯对账核心；按仓采集窗口区分 before/after/uncertain，强身份重放去重、冲突隔离，入数＝已分类＋重复＋冲突＋未知，按 SKU×仓×单位分开。

验证：本地 75 passed、2 subtests passed；测试服务器 Python 3.10.12 的 39 项报表测试通过，另外验证 Z 时间/上海查询时区、三个日期独立、09:00 入库相对 05:17–05:31 窗口的处理。
真实浏览器确认 SO 筛选、DN 筛选不改变全周期净额、无匹配日期显示空、稳定图表及 Supply Timeline 过滤/窗口/覆盖提示。
真实测试库验证 Administrator 与现有 Sales User：Sales User 无 WO/TN 权限时显示未知，不显示 0。
真实入库样本 2 行通过适配器和对账核心均保留；因缺稳定 ID，2 行为 unknown，没有自动库存修正。

测试入口：

```text
uv run python -m pytest tongtool_api/tests supply_chain_visibility/tests supply_chain_visibility/key_test/key_test__tests__test_supply_query.py supply_chain_visibility/key_test/key_test__tests__test_supply_timeline.py -q
```

测试页面：[SO Chain Overview](https://ensh.vilavi.cn/app/query-report/SO%20Chain%20Overview)、[Supply Timeline](https://ensh.vilavi.cn/app/query-report/Supply%20Timeline)。
生产文件入口：`tongtool_integration/sync/stock_sync.py`、`sync/stock_change_sync.py`；服务器/凭证按 `EN_API/docs/reference/en-server-access.md`，不把凭证复制进交接。

## Next Work

1. 先审核两个仓库 PR，核对 app commit 与本仓库扁平副本；保留测试先行与生产审批，不重写已有报表入口。
2. 入库核对继续小窗口批量采集＋缓存/重叠窗口，不逐 PO 扫全量。核实 warehousingNum 的业务数量语义、来源时区、部分入库与稳定事件/行标识；核实库存桶变动覆盖及 EN 按钮/手工 PO 的关联。未证前只留风险与证据，不自动抵扣在途。
3. 完整供应整合尚未完成：把 W1/SC14 的 PO、WO、DN、实际入库接入共同口径；解决在途/PO 重叠、采集前后漏计、单位与完整批发布，再计算可承诺供给。Supply Timeline 当前仅库存证据，不是完整七阶段/W3。
4. 性能先测过滤下推、批量关联；宽导出才用 Prepared Report，重复昂贵推导才做每日业务预计算。当前没有上线新的 06:30 派生任务。

05:17 是采集开始；采集持续到各仓实际响应或批次完成。09:00 入库可能不在旧库存里，却已从当前 PO 剩余量扣除，必须防漏计；采集前入库又可能同时被库存和完整 PO 计入，必须防重复。
仅加 receipt 不足以恢复 available，因为还有出库、占用/释放、退货及手工调整。
用户提出的“根据 EN 头程自动给通途 PO 入库”仅为后续方向，本次没有授权具体入库对象，禁止自行执行。

## Review Notes

已修复：DN 空日期漏过滤、SO/DN 仓名语义、child DocType 权限、部分可读 DN 伪装完整量、重复 SO 物料串单、单位混加、筛选前 KPI 累计、图表标签切换异常、Python 3.10 Z 兼容、Frappe 无 has_role、TT/EN 编码混淆、源窗口缺失和缺 SKU×仓。
无需重复拉业务数据重证这些已记录事实；先运行离线用例，再针对真正缺证环节做限流内小样本。
