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

### api.vilavi.cn（公司 new-api 网关）
上海阿里云 nginx 反代的公司 AI 网关：`/v1` 模型 API、`/sellfox` 赛狐代理、`/oidc` 钉钉 SSO。个人 Token 在后台「令牌管理」领取（`sk-…`）。生产渠道模型名以 `deepseek-v4-flash` / `deepseek-v4-pro` 为准；历史名 `deepseek-chat` 在默认组无渠道，会表现为 chat/completions **503**。

### IvyeaOps vs IvyeaAgent
- **IvyeaOps**：运营工作台 SPA（本仓库板 PoC 的主体验，fork 于 Hector-xue/IvyeaOps）。  
- **IvyeaAgent**：独立本地 Agent 服务（常见 `:8765`，Hector-xue/ivyea-agent），服务知识库语义检索与部分 text chain。未启动时 `/assistant` 仍可直连 new-api；`/brain` 会降级为关键词检索。

### 五杠杆（IvyeaOps optimizer）
`lingxing_optimizer` 对**广告实体**可采取的五类动作候选（只读 PoC 只出候选、不写）：**否词**、**收割（加词）**、**降 bid**、**加 bid**、**加预算**。目标 ACOS（毛利推导）是共用阈值基准，不是第六个动作。依赖「表现报表 + 实体配置」两类数据。

### 收割（关键词杠杆）
五杠杆之一：把搜索词报表里达标的 **客户搜索词** 建议加成 **精准关键词**（只读 PoC 为 advisory）。不自动等于商品定向收割；报表里 ASIN 形「搜索词」仍可能进入该路径，直至过滤器落地。

### 五桶分析法（advertise 搜索词分类）
`advertise/analyze_search_term.py` 对**搜索词行**打的五个分析桶：**Harvest / Negate / Monitor / Protect / Ignore**（见 `advertise/AGENT_HANDOFF.md`「5 桶分类」）。这是报表分析标签，**不是** IvyeaOps 的五杠杆。对应关系：Harvest≈收割候选、Negate≈否词候选；Monitor/Protect/Ignore 在五杠杆里没有同名动作。

## Cross-border shipping (sellfox_shipping)

### Sellfox packageSn
赛狐订单处理里的包裹业务键（对外字段 `packageSn`）。与通途历史「P 号」不是同一体系；蜴国际 Excel 客户参考号应对齐 `packageSn`，不能直接拿通途 `P814…` 当赛狐主键。

### Local tracking import
本模块把物流商返回的运单号写入**本地** SQLite（`lizard-import`）。这只更新本地库，**不会**自动改变赛狐包裹详情里的 `trackNo`。

### submitToPlatform
赛狐 OpenAPI「提交平台」写接口：请求可带 `trackNo` 等字段。公开文档下目前未见单独的「只改物流、不提交平台」接口。业务上销售平台运单仍可由通途写回；赛狐自动推送可关闭。能否用该接口在关自动推送时「只填赛狐可见号」须 live 验证，且只读代理权限不等于可写。

### ShippingBatch
本模块对一次蜥蜴 Excel 导出/导入往返的批次登记（制品、对账计数）。与赛狐侧「提交平台」不是同一对象。

### 购标操作 (Label Operation)
代表一次逻辑上的承运商购标（create shipment/label）请求。由 claim_label_operation() 原子占用产生，拥有独立状态机，与最终标签（shipping_labels）通过 operation_id 关联。同一包裹同时最多存在一个活跃操作。

### 前置校验 (Preflight)
LabelService.preflight() 在调用任何外部 API 之前执行的统一阻断校验。验证审核状态（approved）、重尺完整性和正值、收件必填字段、以及 VITE 仓库配置的地址电话完备性。任何一条失败即返回 400 并拒绝外部调用。

### UNKNOWN_BLOCKED
购标操作的异常状态。表示请求已发出但无法确认承运商是否创建了订单（超时、连接中断、模糊 5xx、进程崩溃）。处于此状态时禁止再次创建；恢复命令仅允许有 provider_order_id 的操作回查承运商状态并下载标签。

### 原子占用 (Atomic Claim)
SQLite BEGIN IMMEDIATE 事务内完成活跃标签/操作冲突检查、generation 分配和 RESERVED 状态插入。并发请求中只有一个获得执行权，其他返回冲突错误。

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

## Flagged ambiguities

- "'五桶' had been used as if it meant IvyeaOps 五杠杆 — they are distinct (search-term labels vs optimizer action candidates)."
- "Amazon Auto/product/category reports often put ASINs in the customer search-term column — that is real report data, not a mapping bug; keyword 收割 must not treat those strings as exact keywords (filter deferred as of 2026-07-28)."
