---
okf: v0.1
type: Reference
title: stock_alert 低库存汇总推送 —— 取数、限流、凭证与排障
description: 通途 ERP2 库存接口取数口径、5 次/分钟限流处理、钉钉新群机器人凭证与定时任务
tags: [stock-alert, tongtool, erp2, rate-limit, dingtalk, scheduling]
---

# stock_alert 参考

## 投递方式（正文 + Excel，按数量分档）

正文（两种都会给）：每仓「**N** 个 SKU 可用<5（在途合计 M 件）」。

**计入规则**：`availableStockQuantity < 阈值` **且** 不是「可用=0 且 在途=0」的死库存
（后者既没货也无在途，多为历史/停用 SKU，过滤掉不统计）。即 `可用=0 + 在途>0` 仍计入。

按**低库存 SKU 总数**自动分档（`--small-threshold`，默认 10）：

| 总数 | 投递 |
|---|---|
| ≤ 阈值（或 0） | markdown 正文里**直接列明细**（每仓逐条 `SKU：可用 X　在途 Y`），**不发文件** |
| > 阈值 | 生成 **Excel**（`stock_alert_output/通途低库存_<日期>.xlsx`）→ 上传 ERPNext → 发 **ActionCard 下载卡片**（正文=汇总） |

Excel：**每个仓库一个 sheet**，表头 `SKU | 可用库存 | 在途库存`，每行一个「可用<5」的 SKU（按可用升序）。

复用尾程那套文件推送：`dingtalk/dingtalk_robot/send_file_card.send_file_to_dingtalk()`
（内部先 `upload_to_erpnext` 再 `send_action_card`）。所以**发 Excel 需要 `ERP_API_KEY/SECRET`**
（根 `.env`，指向 `erpnext.vilavi.cn`）——这几项尾程推送也已在用。

## 数据来源（默认读 EN；OpenAPI 回退）

**默认**读 EN 的 `Tongtool Stock Latest`（EN 每天把通途 14 仓库存同步到 MariaDB，字段一致）：

- 认证：`Authorization: token <ERP_API_KEY>:<ERP_API_SECRET>`（根 `.env`；base `ERP_URL` 默认 `https://erpnext.vilavi.cn`）。
- 查询：`GET /api/resource/Tongtool Stock Latest?filters=[["warehouse","=",<仓>]]&fields=[...]&limit_start&limit_page_length`（1000/页）。
- 三主仓约 4,471 行；`in` 精确名可排除 `美中-FZH-DANEEY-退货产品仓`。
- 优点：**不占通途 5 次/分钟、不受 MCP 524 影响、无需维护通途 Key**。

⚠️ **新鲜度门禁（必须）**：

- `GET /api/resource/Tongtool Stock Run?filters=[["job","=","stock_snapshot"]]&order_by=creation desc&limit_page_length=1`
  最近一次必须 `status=Success` 且 `complete=1`；
- 且 `Tongtool Stock Latest` 的 `max(snapshot_at)` 必须是**今天**；
- 不过门禁 → 只发「库存同步未完成」，**不发低库存明细**（避免把同步失败误报为断货）。

### 回退：OpenAPI 直连

> ⚠️ 2026-11-03 起通途 **MCP 网关**对全部 app_key 返回 `524 unknown不在白名单列表里`；
> 同一凭证的 **OpenAPI 正常**。EN 不可达/缺凭证时才回退到 OpenAPI，**不使用 MCP**。

| 项 | 值 |
|---|---|
| 接口 | `POST https://open.tongtool.com/api-service/openapi/tongtool/stocksQuery` |
| 认证 | `GET .../devApp/appToken` → `GET .../partnerOpenInfo/getAppBuyerList`；`sign=md5("app_token{token}timestamp{ts}{secret}")`，`merchantId=partnerOpenId` |
| 必填参数 | query: `app_token/sign/timestamp`；body: `{merchantId, warehouseName, pageNo, pageSize}` |
| 分页 | `pageNo`/`pageSize`（**服务端上限 100**）；`datas.array` 无 total 时靠「本页 < pageSize 即末页」 |
| 返回字段 | `goodsSku` / `availableStockQuantity` / `intransitStockQuantity` / `defectsStockQuantity` / `waitingShipmentStockQuantity` / `goodsAvgCost` |
| 客户端封装 | `tongtool_api/openapi_client.py`（认证/签名/限流/526 重试）+ `stock_alert/client.py`（分页/归一化） |
| 仓库列表 | `POST /openapi/tongtool/warehouseQuery`（过滤 `status=1`） |

### 探测

```bash
uv run python -m stock_alert.cli probe --warehouse "美中-FZH-DANEEY"
```

产出（UTF-8 文件，避免控制台中文乱码）：

- `stock_alert_output/probe_warehouses.json` —— 仓库列表（可核对 `status=1`）；
- `stock_alert_output/probe_sample.json` —— 1 页库存真实响应样本。

## 限流（关键约束）

通途 ERP2 **商户级 5 次/分钟**，多 App 共享，OpenAPI 也一样。见
`tongtool_api/docs/reference/authentication-and-errors.md`、
`tongtool_api/docs/research/2026-08-13-rate-limit-experiment.md`。

- `tongtool_api/openapi_client.py` 用 `min_interval`（默认 13 秒）在两次调用间节流；
- 业务码 **526**（超频）→ 60s 起指数退避，`max_retries` 次后仍失败则抛错；
- `cli.py` 的 `--min-interval` 可覆盖。**不要调小**——整仓翻页本就要按分钟级节奏跑。

其它业务码：`524` 未授权、`525` 参数错、`519` 签名错、`523` token 过期 —— 直接抛错，不重试。

## 容错（瞬时错误）

- **业务码 526（超频）/ HTTP 5xx / 网络错误**：`openapi_client.py` 指数退避重试
  （60s → 120s → 240s，`max_retries=3`）。
- **524（未授权）/ 525（参数错）等确定性错误**：直接抛 `TongToolApiError`，**不重试**；
  524 的失败告警会附带当前出口 IP 与排查提示。
- 最终仍失败时，包装脚本推一条**失败告警**到钉钉（含异常摘要）。

## 凭证

| 用途 | 位置 | 键 |
|---|---|---|
| 通途 ERP2 | `tongtool_api/.env` | `TONGTOOL_ERP2_PRIMARY_KEY` / `TONGTOOL_ERP2_PRIMARY_SECRET` |
| 钉钉群机器人（**默认复用原群**） | 仓库根 `.env` | `DINGTALK_WEBHOOK` / `DINGTALK_SECRET` |
| 钉钉专用群（可选覆盖） | 仓库根 `.env` | `DINGTALK_WEBHOOK_STOCK` / `DINGTALK_SECRET_STOCK` |

- **通途凭证来源**：EN 测试系统（`ssh 8.133.254.66`，站点 `erpnext.vilavi.cn`）的
  `Tongtool Settings` 单例（`tabSingles`）里 `app_key` / `app_secret`（Password 字段需解密读：
  `bench --site erpnext.vilavi.cn execute frappe.utils.password.get_decrypted_password --kwargs
  '{"doctype":"Tongtool Settings","name":"Tongtool Settings","fieldname":"app_secret"}'`）。
  生产 ERP 未装 `tongtool_integration`，没有这个单例。
- **钉钉**默认复用尾程推送那台机器人（原群）。未设 `*_STOCK` 键时自动回退到
  `DINGTALK_WEBHOOK` / `DINGTALK_SECRET`；要另开专用群再设 `*_STOCK` 覆盖。
  `send_dingtalk.send_markdown(text, title, webhook=..., secret=...)` 已支持显式传入。
- ⚠️ **worktree 不带 gitignored 的 `.env`**：从 `.claude/worktrees/...` 运行时要该 worktree 里
  有 `tongtool_api/.env` 与根 `.env`，或从主检出运行。
- 真值**只放 `.env`**（已 gitignore），不进代码、文档、日志或 commit。

## 口径注意

通途「可用库存」**不可信**：通途为标记发货会先「报溢」把库存加上，可用 0 不等于断货
（见 `docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md` §5.1）。
本功能是**登记层提醒**，非断货判定；正文已注明口径。

## 定时任务（Windows）

```powershell
# 每天 09:23（分钟错开整点，避开其它任务）
powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -AtTime "09:23"

# 指定仓库 / 阈值
powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -Warehouses "美中-FZH-DANEEY" -Threshold 5

# 取消
powershell -ExecutionPolicy Bypass -File stock_alert\scripts\install_stock_alert_schedule.ps1 -Remove
```

任务名 `FZH-StockAlert-daily`；包装脚本 `stock_alert/scripts/run_stock_alert_scheduled.cmd`（gitignore）；
日志 `stock_alert_output/logs/stock_alert-daily.log`。

## 排障

- **没收到钉钉**：看日志末尾；跑挂时包装脚本会先推一条失败告警（告警失败只打 stderr，不盖原异常）。
- **业务码 526**：限流。确认只有一个跑批在打，且 `--min-interval` 没被调小。
- **业务码 524**：调用方/应用未授权（如 `unknown不在白名单列表里`）。
  ⚠️ 2026-11-03 起通途 **MCP 网关对全部 app_key 返回 524**，本模块已改用 **OpenAPI**；
  若 OpenAPI 仍 524，核对通途应用状态、AppSecret 是否被重置、ERP2 接口权限与 MCP/接口白名单。
- **HTTP 5xx**：网关/网络抖动。程序已指数退避重试；持续失败则稍后补跑
  （`Start-ScheduledTask -TaskName FZH-StockAlert-daily`）或联系通途。
- **中文乱码**：日志里设了 `PYTHONIOENCODING=utf-8`；手工跑时同样 `export PYTHONIOENCODING=utf-8`。
- **凭证 `KeyError`**：`.env` 不全（根 `.env` 缺钉钉键，或 `tongtool_api/.env` 缺通途键）。
- **电脑睡眠/错过触发**：任务已设 `StartWhenAvailable` + `WakeToRun`，会自动补跑/唤醒；关机则开机后补跑。

## 相关

- 同类骨架：`parcel_track/`（尾程报表 → 钉钉）、`parcel_track/docs/reference/scheduled-dingtalk-push.md`
- 通途基础：`tongtool_api/`（OpenAPI 与限流）
- 钉钉发送器：`dingtalk/dingtalk_robot/send_dingtalk.py`
