---
okf: v0.1
type: Reference
title: stock_alert 库存接口、统计口径与排障
description: 低库存新增基线、采购入库正增量、名称缓存与独立任务的边界。
---
# 库存提醒参考

## 库存与新增

主源为生产 EN `Tongtool Stock Latest`。最近 `Tongtool Stock Run` 的 `job=stock_snapshot`
必须 `Success` 且 `complete=1`，运行和 Latest 最新 `snapshot_at` 都必须为当日；
失败时仅发“库存同步未完成”，不生成低库存明细。EN 访问异常时才回退通途 `stocksQuery`。

低库存：可用 < 阈值（默认 5），排除可用=0 且在途=0。
低库存始终单卡发送：总览、各仓标题、低库存数/新增数/在途数均用空段落分隔。
底部提供新增Excel与全量Excel两个按钮，列 `SKU | 产品名称 | 可用库存 | 在途库存`。
无新增只保留全量按钮；无低库存不生成文件。完整SKU与名称在Excel中，不再把411行塞入正文。
采购入库按仓标题、产品名称、SKU、数量独立段落；有入库记录时始终另写按仓Excel
（SKU、产品名称、入库数量）并通过同卡按钮下载；正文超过18000 UTF-8字节时退为单卡汇总，不拆条。

新增基线由 `get_stock_history` 精确查询昨日，各仓独立处理；重复 SKU 取最大可用值。
昨日 >= 阈值或不存在此 SKU 则标记新增；昨日 < 阈值不算新增。
整仓基线缺失/读取失败，明确标注“昨日基线缺失”，该仓全量低库存进入 Excel。
未启用基线或无法建立 EN 客户端时不标记新增，stderr 说明原因。

## 接口边界

| 问题 | 来源与限制 |
|---|---|
| 某 SKU 某天库存 | `get_stock_history`：sku、warehouse/warehouse_id、start_date、end_date、limit；无单据号/单据类型过滤 |
| 昨日采购入库 | `get_stock_change`：warehouse、start、end、voucher_type=02；客户端只汇总每条 available_increase > 0 |
| 采购单创建清单 | 零增量只能称为创建/无变化事件；修改也可能为零，不能据此无条件认定创建全集 |
| 给定 PO 是否到仓 | 通途 `purchaseOrderQuery`；用人读的 purchaseOrderCode 查询，结合每行 quantity/in_quantity/status |
| EN 自己的 PO | EN Purchase Order / Purchase Receipt，属于另一套采购单体系 |

库存变动的 `voucher_number` 是通途内部 `purchaseOrderId`，不是 `PO021745` 这种人读 PO 号。
本模块不把两者混用，也不新增 PO 查询 API；采购状态查询不是本轮提醒所需依赖。
同事报告本地库存事件从 2026-10-21 起可用，该时间前的创建覆盖不能保证。
13/13 覆盖仅证明所检查窗口，不能推广为所有历史和未来都完整。

历史/变动 API 最大返回 5000 行且无分页；达到上限时拒绝视为完整结果。
基线查询失败会标为缺失；入库查询异常/格式异常/截断则整次任务失败，避免误报零入库。
入库统计只代表已同步事件，当前不提供独立的库存变动同步完成水位校验。

入库日志报告 input_rows / accepted_rows / skipped（非采购、空 SKU、零增量、负增量）/
output_skus / total_qty；相同 SKU 多事件合并，正向件数相加。
必需列缺失或数量非法直接失败，不把坏数据当零。

## 名称与限流

名称用 `goodsQuery.productName`，映射 `goodsDetail.goodsSku`。
`stock_alert_output/sku_names.json` 周更全量纠正改名，平日批量补缺（每次最多 10 SKU）。
任何名称查询失败只降级为已有缓存或 SKU；查不到的空名称每日重查一次；名称请求最多重试一次，异常信息不输出可能含凭证的 URL。

通途商户所有 App 合计 5 次/分钟；客户端间隔 13 秒，526 退避，524 为未授权。
EN 历史/库存读取不占通途 OpenAPI 配额。名称缓存使用非阻塞 OS 文件锁：已有任务刷新时，其他提醒使用缓存/SKU，不等待、不再发名称请求。
锁由系统在进程退出时释放；`.lock` 文件留存不表示仍被占用。锁只协调本模块，其他应用仍共享通途额度。

凭证只在根 `.env`（EN/钉钉）和 `tongtool_api/.env`（通途）。
worktree 不带这些 gitignored 文件；定时任务跑主检出，主检出必须有完整代码和凭证。

## 消息与定时

- `FZH-StockAlert-daily`：09:23，一张低库存汇总卡片，下载按钮与正文同卡。
- `FZH-StockInbound-daily`：09:47，昨日采购入库，无入库也提醒。
- 两条任务的包装、日志和异常独立；Windows 注册设置 StartWhenAvailable / WakeToRun，仍需电脑开机、用户登录。
- 文件先生成/上传，再发送一次卡片；文件失败仍只发一次汇总并注明失败，返回非零状态。
- 低库存文件：新增与全量分别导出，均按仓分sheet。入库有记录时始终生成完整明细Excel；无入库不生成文件。
- `--dry-run` 不发群、不上传；真实调用用 `--notify`。包装脚本默认带 `--notify`，预览请直接用 CLI。

## 排障

| 表现 | 检查 |
|---|---|
| 库存同步未完成 | 最近快照运行 status/complete、snapshot_at 日期 |
| 无新增 Excel | 是否没有新增、--no-baseline、EN 基线连接是否失败 |
| 基线缺失全量导出 | stderr 单仓异常、历史接口行数是否触顶 |
| 采购入库为零 | 日期/仓库、源是否同步、02 事件是否存在正增量；不等于采购单未到货 |
| 名称是 SKU | 缓存、goodsQuery 权限、526；名称失败不阻断提醒 |
| 钉钉失败 | 对应任务日志、机器人凭证；卡片发送或文件处理失败返回非零 |
| 524 / 526 | 前者应用未授权；后者商户共享限流，停止密集并发 |
