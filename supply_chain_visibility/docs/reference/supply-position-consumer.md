---
okf: v0.1
type: Reference
title: DN与PO状态汇总为单张供应消费表
date: 2026-10-30
status: offline-consumer-implemented-not-full-chain
tags: [supply-position, parquet, po-creation, handoff]
---

# 一张供应消费表：第一批可执行接入

`supply_chain_visibility/supply_position.py` 是本地只读消费器，连接现有
Delivery Facts v3、Jack的PO创建审计完整文档、PO查询结果与批准的B映射。
不调用网络、不创建PO、不自动入库，不运行历史赛狐备货导入脚本。

当前只实现 **DN/PO阶段**。没有把SO未发、生产、当前库存和预测接入，
这些列保持null；所有行 `netting_ready=false`、`auto_order=false`。
输出不是最终补货建议，历史DN数量也不是当前可用库存。

## 运行

在仓库根目录运行，输入与输出必须放私有目录：

```powershell
uv run --with pyarrow python -m supply_chain_visibility.supply_position --input D:/private/input.json --out D:/private/supply-position
uv run --with pyarrow python -m pytest supply_chain_visibility/tests/test_supply_position.py -q
```

PyArrow通过本次命令的 `--with` 环境提供，不要求修改服务器依赖。
没有PyArrow的普通测试环境仍运行核心规则，明确跳过两项Parquet测试；
发布验收必须按上面命令安装PyArrow执行，不能用跳过结果代替。

## 输入 envelope：supply-position-input/v1

必填字段：

| 字段 | 内容 |
|---|---|
| schema_version | `supply-position-input/v1` |
| as_of | 带时区的计算时点 |
| mapping_version | 调用方批准的B映射版本；缺映射样例须明确写未提供，不能伪称批准 |
| delivery | 完整Delivery Facts v3快照，带scope、pagination、版本、delivery_lines |
| mappings | 逐DN行映射数组；允许空，未映射保留unknown |
| creations | 完整PO创建审计文档数组；允许空，不能从PO号伪造审计 |
| po_statuses | `{observed_at, results: {PO号: 原始状态查询对象}}` |
| max_status_age_seconds | 可选，默认900；本地保守检查阈值，不代表已经承诺生产刷新SLA |

快照完整性复用 `warehouse_restock.delivery_facts_adapter.validate_delivery_snapshot`。
拒绝截断、非法total/版本/范围hash。scope字符串列表、对象列表与字典均遵循既有
规范化规则；hash仅验证完整性，不证明范围来源权威。调用方负责批准业务范围。

### mappings

每条记录必须有 `delivery_note, dn_item, item_code, tt_sku, warehouse, uom,
purpose, evidence`。purpose为 `branch/fba/unknown`；同DN/行只能一条映射。
不能把来源工厂仓当目标仓，不能按FBA字段为空猜分公司。
当前不做UOM转换；映射单位不同则保留待核实。

### creations

每条至少包含 `name, delivery_note, status, purchase_order_code, lines`，
以及有则保留的 `superseded_by`。每条lines使用Jack原始字段：
`dn_item, item_code, qty, uom, tt_sku, outcome, contribution_qty`。
不同原行合并到同一货品时，只统计各原行贡献，不重复使用merged_qty_total。

**上游实际缺口**：截至delivery_plan `f4c95f1`，
`get_purchase_creation_status`背后的`get_creation_audit`返回创建元数据与events，
未返回lines。因此不能直接将该响应当作完整输入。需Jack提供有DN读取权限约束的
完整审计导出（含delivery_note与lines、分页完整性），或由获授权导出器提供完整文档。
缺失时本工具保留 `creation_lines_not_exported`，不访问受限子表绕过权限。

### po_statuses

接受 `get_purchase_status_many`返回中results字典的原始条目，要求
`found=true`且`identity.purchaseOrderCode`与审计PO号完全一致。
调用方必须记录实际来源的observed_at；缓存生成时间未知时不能仅以抓取时间冒充新鲜。
无查询、限流、权限不足、超时和未知状态均进入待核实，不能当作没有供应。
状态0为待到货；1/2保留具体商品分配未知；3为用户批准的整PO完成假设；4为作废。
不会把状态3观测时间写成实际收货时间。

## 输出与数量去向

每行按 `item_code × tt_sku × warehouse × purpose × uom` 分组。
没有观测DN的scope商品也有一行unknown，不写0。

| 字段 | 含义 |
|---|---|
| dn_net_qty | 所选DN范围的历史净交付，不代表现有在途 |
| po_completed_assumed_qty | 仅已确认创建且included行、当前PO状态3的数量 |
| open_po_qty | 仅已确认included且PO状态0的数量，尚无可用日期资格 |
| unresolved_qty | 无审计、映射失败、部分到货等待核实量 |
| known_dn_net_qty | 已知数量小计；有缺数时仅作下界/诊断，不冒称完整总量 |
| reasons_json / tranches_json | 每条来源DN/行、数量、分类、创建/PO号及映射依据 |

已知非退货数量的互斥三类之和等于dn_net_qty。
任何未知数量会使该组完整数量列为null；已知小计和未知行数单列。
退货保留有符号已知净额，涉及的原DN/物料进入人工核实，阶段数量不自动关闭；
不因一条正常退货阻塞无关商品，也不将退货clip成0。首批不自动分摊退货到PO。
FBA行保留事实，action为excluded_fba，不释放其占用给分公司。

## 发布与失败保护

每次写入唯一版本目录，包含一张`supply_position.parquet`、manifest与report。
Parquet按显式schema写入，空结果也有schema；数量nullable，复杂证据为JSON列。
逐表完整读回比较后，才原子替换`latest.json`。Windows不重命名可能被Arrow/
索引器占用的目录；未发布目录不会被latest引用。

`last_attempt.json`记录最近成功或失败，失败不替换最后成功指针。
磁盘完全不可写时无法保证失败sidecar落盘，原异常继续抛出，调用方不得吞错。
读取方须检查latest所指manifest、as_of与last_attempt；文件不会自动刷新。
不创建定时任务，不承诺多个来源为同一事务快照。

## 验证与后续交接

- 覆盖included/遗漏、部分/短收、限流、身份不符、状态陈旧、重复审计、缺lines、
  数量/单位漂移、FBA、未知/无DN、退货、Parquet读回与写入失败保护。
- 独立审查发现的对象scope兼容问题已补反例修复。
- 真实有界样例：用户指定同类商品的一款DANEEY皮壳，42条DN明细、516件历史净交付，
  因未注入批准B映射和历史创建记录而明确进入待核实；不计当前可用供应。
  原始输入与产物仅在本机私有目录，不提交业务行数据。
- Jack补完整创建清单导出和PO状态来源时点；主线补批准B映射、SO/生产/当前库存与D预测。
  入库后是否已含某库存快照仍独立核实，不能重复加入库存。
- 最终`replenishment_decisions`由上述拼接完成后产出；本模块不是该最终交付。
