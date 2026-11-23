---
type: Reference
title: stock_alert Agent 交接
---
# stock_alert 交接

## 当前版本（2026-11-18 图片卡片）

默认 `STOCK_ALERT_CARD_MODE=image`：`card_image.py` 用 Pillow 渲染 PNG（蓝底居中标题、
低库存概览在标题下方、低库存各仓今日新增 SKU / 入库各仓明细；无顶部统计框和「分仓明细」标题），
上传后由现有群机器人发图 + 原生下载按钮；
**无需企业内部应用**。单按钮 ActionCard 使用 `btns` 独立跳转，点图片不会触发下载。
低库存卡片按仓列出**今日新增 SKU**（SKU、产品名称、当前库存），不限条数；不显示低库存总数，
不再显示在途合计（Excel 仍保留每个 SKU 的在途库存）；今日无新增（或全无低库存）不推送。采购入库图片同样不限条数，数量单位为「个」。
昨日基线缺失的仓提示「无法判断今日新增」，不把全量低库存当新增。
图片生成/上传失败自动回退文本 ActionCard。
可选 `interactive` / `auto` 走钉钉原生互动卡片（见 `docs/reference/interactive-card.md`）。
采购入库改为 **10:00 / 14:00 / 17:00** 三次直连通途 `/openapi/tongtool/stocksChangeDetailQuery`
（EN `stock_change` 每天约 05:53 才同步一次，白天滞后）；按「上次成功检查 → 本次」增量窗口查询，
窗口状态存 `stock_alert_output/inbound_state.json`，dry-run/发送失败不推进。
每次执行**只为有入库的仓发卡片**（最多 3 张；空仓不推送，三个仓都为 0 时整次不推送），
每张卡只含该仓明细与该仓 Excel。
当前 93 项测试通过；图片卡片已实推，errcode=0。

以下阶段2首版/单卡样式为历史记录，不是当前发送样式。

## 阶段2首版记录

先读 [README](README.md) 和 [接口边界](docs/reference/low-stock-alert.md)。

2026-11-17 接续 Claude 对话 `Continue stock_alert phase 2 enhancements`：
原实现位于 `EN_API/.claude/worktrees/stoic-mirzakhani-a69ef7`，基线 `4216beac`，
中断时主要代码已写、文档未更新。主检出有大量其他 WIP，不切分支、不清理。

阶段2代码已同步至主检出 `stock_alert/`，备份位于 gitignored 的
`stock_alert_output/.backup_codex_20261117_115002/stock_alert/`。
原 PR 为 #309；用户于2026-11-17确认“完整执行”，授权正式发送、启用任务、提交并更新PR。
已正式发送3条低库存+1张新增Excel卡片+1条昨日采购入库提醒，钉钉返回均errcode=0。

本轮离线测试 69 项通过，PowerShell 安装脚本语法检查、凭证扫描通过。
2026-11-17 只读核对：三仓扫描 4476 行，低库存 155/69/187（合计411），
今日新增 6/4/8（合计18），三仓昨日基线均完整。
2026-11-16 采购正向入库：仅美中1 SKU、45件，另两仓0。
首次名称全量刷新目录很大，已确认超过原先2–5分钟预估；
日常复用缓存，但每周全量刷新会延后当日消息，不能承诺09:23整点送达。

低库存与采购入库分别为 `run`、`inbound` 子命令；预览必须用 CLI 的 `--dry-run`。
两个无人值守包装默认 `--notify`，不要用包装做无发送预览。
两任务已注册且回读核对：自2026-11-18起每日09:23 / 09:47运行，均指向主检出。
本轮不合并main，代码交付通过PR #309审批流程。

采购事件仅采用每条正增量，零增量不是入库证明。不要为本功能新增 PO 状态 API；
库存事件不能判断某个 PO 是否全部到仓，也不保证创建清单完整。
真实逐行数据、Excel、名称缓存及日志仅存 `stock_alert_output/`，不提交公开仓库。

最终真实数据 dry-run 已完成：3条低库存消息，UTF-8字节18115/17954/5654，411条明细全部有名称。
新增Excel三仓分别6/4/8行，共18行，4列表头已校验。
首次名称缓存实测30.4分钟（13504个商品）；缓存后再次低库存+入库预览共约10秒。
本地验收文件：`stock_alert_output/phase2_verification.json`、`phase2_low_stock_preview.txt`、
`phase2_inbound_preview.txt`、`通途新增低库存_20261117.xlsx`。
Windows非阻塞缓存锁已测试，避免两任务重叠刷新；库存回退分页大小约束至100，触顶报错。
