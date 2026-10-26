---
okf: v0.1
type: Checklist
title: 供应整合数据层发布前检查清单
date: 2026-10-26
module: supply_chain_visibility
tags: [release, supply-chain, performance, d33]
---

# Supply Integration Release Checklist

## Scope

- 本次发布对象：数据层 P1–P4（`supply_row.py`、`receipt_bridge.py`、`overlap_gates.py`、`supply_integration.py`）。
- 不包含：key_test 报表入口改动、生产部署、自动入库、调度改点、主数据修改。
- 当前状态：PR #314 draft；未部署测试站/生产。

## Test Gate

- [ ] `uv run python -m pytest tongtool_api/tests supply_chain_visibility/tests supply_chain_visibility/key_test/key_test__tests__test_supply_query.py supply_chain_visibility/key_test/key_test__tests__test_supply_timeline.py -q`
- 最近结果：**112 passed / 2 subtests passed**（2026-10-26）。
- [ ] 无失败、无 skip；新增用例覆盖跨日入库、窗口外、PO/在途同批、UOM 未证、cover、FBA、未映射。

## D33 Gate

- [ ] 公开仓库无行级数量 CSV/JSON；原始响应只在本机临时目录/`local/`。
- [ ] 未提交 `supply_timeline/` 本地残留、`cache/`、`out/`、`.env`。
- [ ] 文档只放聚合计数与字段规则。

## Data Gates（可承诺供给前必须全过）

- [ ] 覆盖：采集无 `truncated_windows`；无未解释 `not_collected`。
- [ ] 单位：目标 SKU×仓 UOM 已证，或明确按 `(unknown)` 分桶。
- [ ] 身份/时间：receipt 与 PO/库存关联已证，或明确保持 `unknown`；时区已证或标 `unverified`。
- [ ] 重叠：PO/在途、DN/在途、外部 FBA 去重已应用并可见。
- [ ] 基准：库存、PO、入库三类来源 `as_of` 已对齐；不同基准只输出差额，不相加。
- [ ] 部分入库语义（`warehousingNum` 本次量/累计量）已证，或保持 unknown。

## Performance Baseline（2026-10-26，本机合成数据）

命令：

```bash
python supply_chain_visibility/scripts/bench_supply_integration.py --sizes 1000,5000,10000
```

| 每源行数 | 总行数 | build | bridge | report_only | peak |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 4,000 | 0.76s | 0.03s | ~0s | 12.6 MB |
| 5,000 | 20,000 | 3.63s | 0.20s | ~0s | 62.4 MB |
| 10,000 | 40,000 | 7.90s | 0.40s | ~0s | 124.6 MB |

说明：

- 合成数据、单机、无数据库/网络；不代表生产延迟。
- 目标样本 9 SKU / 约 4.3k 行，对应 4k 总行数量级，构建约 **0.8 秒**，可接受。
- 明显超线性时先 profile `apply_overlap_gates` / `to_dict` / `validate_supply_row`；不要先加缓存。
- 宽导出/Top50 再测过滤下推与批量关联；不因本基线承诺生产 SLA。

## Release Steps（需用户/审批后执行）

1. [ ] 在 `keyapi/key_test` 独立 PR 接入数据层；先测试站，后生产。
2. [ ] 不改已有报表入口的筛选语义；只增加字段/说明与只读区块。
3. [ ] 不新增 06:30 派生任务；复用现有库存同步与 Parquet。
4. [ ] 生产发布前记录回滚点；失败回退 app PR，数据层无写副作用。
5. [ ] 生产只读；不自动入库、不改主数据/调度。

## Rollback

- 数据层为纯函数，无写副作用；回滚只需回退 app 报表改动。
- 若报表字段导致异常，先隐藏新区块，不影响原筛选/查询入口。
- 原始响应与缓存可保留供复核；不提交公开仓库。

## Open Decisions（阻塞“可承诺供给”）

- `status=4` PO 语义。
- `warehousingNum` 本次/累计。
- 入库绝对时区。
- `stock_change.parquet` 凭证/桶覆盖。
- 部分入库与换货/替代归属。
- 是否将 Supply Timeline 升级为完整七阶段/W3。

## Links

- [整合设计](2026-10-26-receipt-supply-integration.md)
- [原生报表计划](2026-10-26-en-native-report-plan.md)
- [PO 入库参考](../../../tongtool_api/docs/reference/purchase-receipts.md)
- [PR #314](https://github.com/keyapi/fzh-data/pull/314)
