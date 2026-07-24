# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Unified AI access (ai_access_poc)

### 壳 PoC (Shell PoC)
C′ 双轨中的浏览器壳：Open WebUI + Docker-only Open Terminal + 赛狐只读 Workspace Tool。验证「Chat 能拉搜索词报告并分析」，不做 Portal、不做广告写。

### 板 PoC (Board PoC)
C′ 双轨中的业务板：IvyeaOps fork 后把领星 OpenAPI 换成赛狐只读适配（sellers + 搜索词规范化 + optimizer 候选）。与壳并行规划，壳绿后再全力推进。

### Tool summary（赛狐报告）
Workspace Tool 拉取 xlsx 后返回的 JSON 文本摘要（`totals` + `top_by_spend_csv` 等）。聊天模型不能读二进制 xlsx，分析必须靠 summary 或沙箱代码。

### Open Terminal vs Code Interpreter
Open WebUI 里两套代码执行能力：Open Terminal = Docker Linux 沙箱（推荐）；Code Interpreter 默认引擎 Pyodide（legacy，浏览器 WASM）。同一会话互斥。

## Cross-border shipping (sellfox_shipping)

### Sellfox packageSn
赛狐订单处理里的包裹业务键（对外字段 `packageSn`）。与通途历史「P 号」不是同一体系；蜴国际 Excel 客户参考号应对齐 `packageSn`，不能直接拿通途 `P814…` 当赛狐主键。

### Local tracking import
本模块把物流商返回的运单号写入**本地** SQLite（`lizard-import`）。这只更新本地库，**不会**自动改变赛狐包裹详情里的 `trackNo`。

### submitToPlatform
赛狐 OpenAPI「提交平台」写接口：请求可带 `trackNo` 等字段。公开文档下目前未见单独的「只改物流、不提交平台」接口。业务上销售平台运单仍可由通途写回；赛狐自动推送可关闭。能否用该接口在关自动推送时「只填赛狐可见号」须 live 验证，且只读代理权限不等于可写。

### ShippingBatch
本模块对一次蜥蜴 Excel 导出/导入往返的批次登记（制品、对账计数）。与赛狐侧「提交平台」不是同一对象。

## Development Environment

### 3P 模式 (Third-Party Provider Mode)
Claude Desktop 的第三方 API 模式，允许连接非 Anthropic 模型（如 DeepSeek）。此模式有独立的配置文件路径 `Claude-3p\claude_desktop_config.json`（区别于普通模式的 `Claude\` 路径），配置中包含 `"deploymentMode": "3p"` 字段。MCP 服务器的配置格式与普通模式相同。

## Manufacturing

### 一键完工 (One-Click Complete)
A custom ERPNext feature that completes a Work Order by programmatically creating virtual Job Cards for every operation using employee `HR-EMP-00001`, filling each with the planned quantity. Completes in under two seconds. Designed for scenarios where scan-based reporting is unavailable, but creates fabricated production data when used on Work Orders that have real worker scans.

### 扫码报工 (Scan-Based Job Reporting)
The normal production reporting workflow: workers scan a barcode at each operation station, creating a Job Card with their employee ID and the actual quantity completed. This is the source of truth for production data. Contrasts with 一键完工.

### 成品fg (Finished Goods)
Final assembly products combining 皮壳 (leather shell) + 内胆 (inner liner) + 充棉 (stuffing). Identified by item codes starting with `KS` (no `#`). Have zero operations on the Work Order routing because components are produced as separate semi-finished Work Orders. `open_material_qty = 0` is normal. Currently completed via 一键完工; scan-based workflow is planned.

### 半成品 (Semi-Finished Goods)
Intermediate production items with multi-operation routings. Two subtypes: 皮壳 (leather shell, `PK#` prefix) and 内胆 (inner liner, `ND#` prefix). Require step-by-step scan reporting through each operation. `open_material_qty` must be > 0 if cutting was actually performed.

### 开料 (Material Issuing / Cutting)
The first production operation that issues raw fabric and cuts it to size. The quantity reported here (`open_material_qty`) is the production ceiling — no subsequent operation can produce more than what was cut. A zero value on a semi-finished Work Order means cutting was never reported in the system.

### 虚拟员工 (Virtual Employee)
Employee ID `HR-EMP-00001`, used exclusively by the 一键完工 feature. All Job Cards assigned to this employee are synthetic and reflect planned quantities, not actual production. Detected by checking `time_logs[].employee` on individual Job Card records.

## ERPNext Platform

### Custom App
A Frappe framework application that extends ERPNext with project-specific functionality. Deployed alongside core ERPNext (`erpnext`, `frappe`) in the same bench. Each custom app has its own git repository under `frappe-bench/apps/`. This project has multiple custom apps including `delivery_plan`, `key_oms`, `key_test`, `light_mes`, and `vilavi_pim`.

### Inventory Dimension (库存辅助核算)
ERPNext's stock auxiliary accounting system that adds extra tracking fields (e.g., tracking number, label combination) to stock transactions and Stock Ledger Entries. Configured via the Inventory Dimension doctype. Each dimension maps a reference document to a custom field in transaction line items and a corresponding column in Stock Ledger Entry.

### Version Drift (版本差异)
The gap between the test ERPNext version and the production ERPNext version. Currently the test system runs ERPNext v15.59.0 while production runs v15.43.3. This drift means ERPNext internal APIs (such as `get_inventory_dimensions()`) may return different field sets between the two environments, causing custom app code to work on test but silently fail on production.

## Integrations

### DingTalk Custom Robot (钉钉自定义机器人)
A webhook-based DingTalk group messaging channel used by AI agents (WorkBuddy, Claude Code) in this project to send notifications and file download links. Uses HMAC-SHA256 signing. Distinct from DingTalk enterprise internal bots — custom robots do not require AppKey/AppSecret and are scoped to a single group, making them safe to share with non-developer agent users. Cannot send file attachments directly; file delivery uses ActionCard messages with download links hosted on ERPNext.
