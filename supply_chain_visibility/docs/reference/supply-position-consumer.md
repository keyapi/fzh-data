---
okf: v0.1
type: Reference
title: DN与PO状态汇总为单张供应消费表
date: 2026-11-02
status: consumer + full facts v2 unified publication implemented; real A/B/C pending
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

### 2026-11-02：直接组装保存的API导出

无需手工拼整个envelope，可直接输入已保存的API响应（支持外层`message`）：

```powershell
uv run --with pyarrow python -m supply_chain_visibility.supply_position --delivery-json D:/private/delivery.json --mapping-json D:/private/B.json --audit-json D:/private/audit-DN1.json --status-json D:/private/po-batch1.json --out D:/private/supply-position
```

`--audit-json`、`--status-json`均可重复，B文件结构为`{source, version, rows}`。
PO输入同时支持原API的`results/status`与Jack刷新器的`statuses/raw_status`；
组装时规范化字段，同一响应若同时提供互相矛盾的容器/状态则拒收，不盲选优先级。
创建响应使用`{delivery_note, creations}`；缺lines不会自动造清单。
相同创建ID或PO的内容/来源时点冲突会拒收，而不是盲选最后一条。
保留PO批次的partial/终止原因及审计分页覆盖状态；未查询项仍待核实。
组装仅关联本地文件，不会远程拉取或绕过受限权限。

### 统一读取与查看

下游使用`read_position(out, as_of=带时区时点, max_age_seconds=业务允许时效)`。
它校验固定版本路径、manifest/文件哈希、Parquet类型/行数及与报告逐行一致，
返回已解析的reasons/tranches，不要求下游自己解析JSON证据列。

```powershell
uv run --with pyarrow python -m supply_chain_visibility.supply_position --inspect --out D:/private/supply-position --max-age-seconds 86400
```

时效由调用方显式指定；过期、未来时点、来源时点未知或最近刷新失败，默认拒绝读取。
需查看旧资料时加`--allow-stale`，保留所有警告，仍不授权净额/下单。
只读CLI显示汇总，不输出商品明细；程序读取返回完整表。

快照as_of、DN原始observed_at/as_of、PO来源observed_at分别检查。
刚重新生成的文件不能把旧来源变新；日期不带时区/只有日期时标来源时点未知。
缓存读取时间received_at不替代observed_at。旧版本快照缺来源字段时同样保守提示，
不静默视为新鲜。输入文件损坏/JSON解析失败也记录刷新失败，保留旧latest。

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

**上游现状**：delivery_plan `feature/po-creation-audit@2a4d903` 的
`get_creation_audit`/`get_purchase_creation_audit` 已返回 `lines`（含 `dn_item/item_code/
qty/uom/tt_sku/outcome/contribution_qty`）与分页覆盖。仍需同事提供**真实 DN 的私有保存
响应**；本地暂无可读的真实审计/PO 状态样例。缺失时本工具保留
`creation_lines_not_exported` / `po_*_unknown`，不访问受限子表绕过权限。

### po_statuses

接受 `get_purchase_status_many`返回中results字典的原始条目，要求
`found=true`且`identity.purchaseOrderCode`与审计PO号完全一致。
调用方必须记录实际来源的observed_at；缓存生成时间未知时不能仅以抓取时间冒充新鲜。
无查询、限流、权限不足、超时和未知状态均进入待核实，不能当作没有供应。
状态0为待到货；1/2保留具体商品分配未知；3为用户批准的整PO完成假设；4为作废。
不会把状态3观测时间写成实际收货时间。
普通非退货DN的actual_qty也须与审计贡献量一致；不能仅比较原始qty列，
否则原始qty为10但actual_qty变12时会错误关闭12。显式conservation_ok=false/0
禁止关闭；字符串is_return不再按Python真值判定，必须布尔或整数0/1。

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

2026-11-02补验：27项消费器测试通过，包括2000商品/2000条DN明细/20000件的
离线守恒对照、保存API导出→组装→Parquet→统一读回的端到端用例。
这是本地计算规模验证，不是生产API吞吐或2000真实SKU业务验收。
重放10月30日42条真实DN时，新生成文件仍明确提示旧快照与来源时点不足，
未访问生产采集新数据，未伪装当前在途/库存。

### 2026-11-02 Jack流水线复审补丁

在Jack `4928fc35`上补4项回归：消费器的未闭环原因与来源观测时间传到
`full_supply_facts`，计算时间不冒充源时间；显式冲突SKU不合并；补齐branch后
同步内部查找键，后续其他branch不再误挂；流水线成功重跑更新`last_attempt.json`。
包含PyArrow的模块全量288项、5子测试通过。

`supply_pipeline`当前发布position/facts/timeline三份JSON与manifest/latest，
不是最终补货决策，也尚未将完整facts/timeline发布成Parquet。
原消费器单张`supply_position.parquet`仍是独立交付，两者不能混称。

真实旧DN负向回放：42行、历史净交付516件；未提供批准B、创建清单和PO状态，
所以PO完成供给0，1组待人工核实，来源时效未知。私有证据：
`D:/Work/fzh-order-store/integration-smoke/jack-pipeline-20261102/real-legacy-acceptance-report.json`。
当前连接可读范围的测试创建审计及带PO分公司DN均为0；本地缺测试REST凭证；
单次通途只读查询未返回并已停止等待，没有重试或创建真实PO。
这些结果验证缺证据路径，不能替代真实正向闭环、受限HTTP或生产规模验收。

### 2026-11-02 full_supply_facts v3 统一发布（ABC/单位/时间/复跑）

`supply_pipeline` 现在把 `supply_position`、`full_supply_facts`、`timeline` 放进**同一次
版本发布**：`full_supply_facts.parquet` 是主消费入口，JSON 为追溯副本；`supply_position`
保留自己的 schema/粒度，不并入 full facts。发布前逐文件回读、SHA、schema、唯一键与
JSON/Parquet 逐字段一致校验；失败不切 `latest.json`。reader 返回
`healthy/stale/partial/corrupted/incompatible_version/refresh_failed_using_previous`，
并用 `allow_stale` 显式控制是否可读。

本地冻结 A/B/C 通过 `abc_inputs.load_frozen_abc` 接入：
- **观察/归属/下单三层分开**：`inventory_observed_qty`（C 原始数量+单位）、
  `attribution_status`/`inventory_qty`（B 单位/身份资格）、
  `inventory_current_available_qty`/`order_eligibility`（时间证明+B 门禁）。
- B/C 单位不一致或缺失 → `uom_mismatch`，观察量保留但归属/当前可用为 null；
  同商品同池多个 B 单位分别保留去向，不压成空单位行。
- date-only/naive 不算精确时间；`inventory_time_proven=false`，当前可用量 null；
  同日未来时间按精确 as_of 识别。
- 缺 branch/tt_sku 的非权威来源只进未归属池；B/A 显式身份只有在完整候选唯一时
  才填补 DN/PO 空维度；任意输入排列结果一致。
- 每层按稳定来源身份去重：同身份同载荷只计一次；同身份异载荷显式冲突；
  缺身份保持 unknown；物流按 DN 明细+运单+完整业务身份分组。
- 输入契约：混版页、截断/未 exhausted、缺版本/时间分别显式处理；业务 partial 与
  分页截断用 `partial_reason` 区分；来源状态保守聚合。
- 冻结输入复制到 `run_dir/inputs/`，`--replay-run <run_dir> --out <new_out>` 校验字节后
  复跑；支持空格/中文路径；业务内容 SHA 稳定。

真实 A/B/C 工作簿当前不可用，故**真实链路验收 pending**；无合成数据冒充。
拿到后运行完整命令（见 `supply-facts-contract.md` 的 v3 节）。
