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
低库存始终单卡发送：**只显示今日新增数**在标题下方，不显示低库存总数；正文按各仓标题、
今日新增数、今日新增 SKU 明细（SKU/产品名称/当前库存）用空段落分隔；
各仓标题右侧也不显示低库存总数；不显示在途合计（Excel 保留每个 SKU 的在途库存），
今日新增不限条数。
底部提供新增Excel与全量Excel两个按钮，列 `SKU | 产品名称 | 可用库存 | 在途库存`。
今日无新增（或没有低库存）**不推送**，也不生成图片/Excel。图片只列今日新增 SKU，完整 411 行仍在 Excel。
采购入库图片按仓列出全部产品（不限条数），不显示顶部统计框和「分仓明细」标题；
每次执行按仓检查，**只为有入库的仓发卡片**（最多 3 张）；空仓不推送，三个仓都为 0 时整次不推送；
每张卡只含该仓明细，标题/副标题带仓名，Excel 也只含该仓；
文本回退超过18000 UTF-8字节时退为单卡汇总，完整明细仍通过同卡 Excel 下载，不拆条。

白天 10:00 / 14:00 / 17:00 的采购入库**直连通途 OpenAPI**
`/openapi/tongtool/stocksChangeDetailQuery`（`warehouseName`、`updatedDateFrom`、`pageNo`、`pageSize`），
因为 EN 的 `stock_change` 每天约 05:53 才同步一次，无法支撑实时检查。
每次窗口从上次成功检查时间到本次运行时间，当天首次从 00:00 开始；
只保留 `relatedVoucherType=02` 且 `availableStockIncrease>0` 的事件。
窗口状态保存在 `stock_alert_output/inbound_state.json`，dry-run 不推进；发送失败也不推进。
手动历史查询仍可用 `--date YYYY-MM-DD --source tongtool`，或 `--source en` 走 EN 日更数据。

新增基线由 `get_stock_history` 精确查询昨日，各仓独立处理；重复 SKU 取最大可用值。
昨日 >= 阈值或不存在此 SKU 则标记新增；昨日 < 阈值不算新增。
整仓基线缺失/读取失败，明确标注“昨日基线缺失，无法判断今日新增”；
图片不把该仓全量低库存当成新增，全量低库存仍进入 Excel。
未启用基线或无法建立 EN 客户端时不标记新增，stderr 说明原因。

## 接口边界

| 问题 | 来源与限制 |
|---|---|
| 某 SKU 某天库存 | `get_stock_history`：sku、warehouse/warehouse_id、start_date、end_date、limit；无单据号/单据类型过滤 |
| 白天采购入库（实时） | 通途 `stocksChangeDetailQuery`：warehouseName、updatedDateFrom、pageNo、pageSize；客户端只汇总 relatedVoucherType=02 且 availableStockIncrease>0，按 operateTime 窗口过滤 |
| 历史采购入库（EN 日更） | `get_stock_change`：warehouse、start、end、voucher_type=02；作为回退/历史查询，客户端只汇总每条 available_increase > 0 |
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
output_skus / total_qty；相同 SKU 多事件合并，正向数量相加。
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
- `FZH-StockInbound-daily`：10:00 / 14:00 / 17:00，直连通途查当天增量（首次 00:00 起），
  只为有入库的仓推卡片（最多 3 张）；都为 0 时不推送。
- 卡片默认渲染为 PNG 图片（`STOCK_ALERT_CARD_MODE=image`）：蓝底居中标题、统计框、
  低库存各仓今日新增 SKU / 入库分仓明细；
  图片上传失败回退文本 ActionCard。单按钮卡片使用 `btns` 独立跳转，点图片不会触发下载。
  入库数量单位为「个」，低库存在途合计仍为「件」。
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
| 本次无入库 | 不推送；检查窗口（上次检查时间、当天首次 00:00）、日期/仓库、02 事件是否存在正增量；不等于采购单未到货 |
| 名称是 SKU | 缓存、goodsQuery 权限、526；名称失败不阻断提醒 |
| 钉钉失败 | 对应任务日志、机器人凭证；卡片发送或文件处理失败返回非零 |
| 524 / 526 | 前者应用未授权；后者商户共享限流，停止密集并发 |
