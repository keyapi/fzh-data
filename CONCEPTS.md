# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Agent environment (Windows tooling)

### Windows PowerShell 5.1
系统自带的 Desktop 版 PowerShell（`powershell.exe`）。不支持 `&&`/`||`；在代码页 936（GBK）下默认 `Get-Content` 会把无 BOM 的 UTF-8 中文读乱；`Set-Content -Encoding UTF8` 会写入 UTF-8 **BOM**。

### PowerShell 7 / pwsh
跨平台 PowerShell（`pwsh.exe`），与 5.1 并存。支持 `&&`；默认更适合 UTF-8。本项目推荐 winget 安装稳定版 `Microsoft.PowerShell`（不要 Preview）。Agent 有 `pwsh` 时应优先使用。

### env_doctor
根目录脚本 `scripts/env_doctor.py`：按 OS 检测 Git/uv/node、PS 5.1/pwsh、代码页与 `windows-agent-shell` skill，**默认只打印建议**；`--probe` 跑 `&&`/UTF-8/BOM 对照；`--apply-ps7` 仅在用户明确同意后装 PS7。

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
代表一次逻辑上的承运商购标（create shipment/label）请求。由 claim_label_operation() 原子占用产生，拥有独立状态机，与最终标签（shipping_labels）通过 operation_id 关联。同一包裹同时最多存在一个活跃操作（RESERVED/SENT/ACCEPTED/LABEL_PENDING/UNKNOWN_BLOCKED）。SUCCEEDED 表示购标成功（配合活动 label）；CANCELLED 表示取消确认后的终态，允许新 generation。

### 前置校验 (Preflight)
LabelService.preflight() 在调用任何外部 API 之前执行的统一阻断校验。验证审核状态（approved）、重尺完整性和正值、收件必填字段、以及 VITE 仓库配置的地址电话完备性。任何一条失败即返回 400 并拒绝外部调用。create_label() 必须先跑 preflight 再 claim。

### UNKNOWN_BLOCKED
购标操作的异常状态。表示请求已发出但无法确认承运商是否创建了订单（超时、连接中断、模糊 5xx、进程崩溃）。处于此状态时禁止再次创建；恢复命令仅允许有 provider_order_id 的操作回查承运商状态并下载标签。

### 原子占用 (Atomic Claim)
SQLite BEGIN IMMEDIATE 事务内完成活跃标签/操作冲突检查、generation 分配和 RESERVED 状态插入。并发请求中只有一个获得执行权，其他返回冲突错误。create_label() 在 SENT 之后才调用承运商 HTTP。

## Development Environment

### 3P 模式 (Third-Party Provider Mode)
Claude Desktop 的第三方 API 模式，允许连接非 Anthropic 模型（如 DeepSeek）。此模式有独立的配置文件路径 `Claude-3p\claude_desktop_config.json`（区别于普通模式的 `Claude\` 路径），配置中包含 `"deploymentMode": "3p"` 字段。MCP 服务器的配置格式与普通模式相同。

### 凭证在父仓库不在 worktree
本项目常开 git worktree（`.claude/worktrees/...`）。gitignore 的凭证只存在于**父仓库** `D:\Work\赛狐\Cursor`：`EN_API/.env`（生产 ERPNext API）、`tongtool_api/.env`（通途 MCP）、`secrets/gsheets-service-account.json`（Google Sheet gspread）。worktree 里找不到这些文件；跑脚本要把相关 env 指到父仓库路径（如 `GSPREAD_SERVICE_ACCOUNT_FILE=D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json`），或从父仓库 cwd 运行。

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

### Item Attribute Value All X (底层值表)
Custom doctypes in the `[Stock]` module that hold canonical attribute values for a domain — `Item Attribute Value All Fabric` (`FAB-*`, abbr+attribute_value), `Item Attribute Value All Color` (`CLR-*`, abbr+attribute_value+supplier_color_number), plus 46+ others (Size, Foam Size, Fiber Pad Size, etc.). Product-specific Item Attributes reference these via `custom_select_doctype`.

### Item Attribute (物料属性) custom_select_doctype
Convention: 面料/颜色 Item Attributes (e.g. 三角靠枕面料) set `custom_select_doctype` to an "All X" value table and `custom_select_from_all_attribute_values=1`; 尺寸 attributes leave `custom_select_from_all_attribute_values=0` (sizes lack cross-product generality). `custom_item_group` links the attribute to its owning item group.

### item_group_translation (物料组翻译)
Custom Data field on Item Group storing the English style-level name for customs/export. Source text is the Chinese `item_group_name`. Batch maintenance via `EN_API/translate_item_group_names.py` (Tencent TMT); distinct from material-level English names in `customs_export.py` (DeepSeek on DN line items).

### 模板物料 (Template Item)
An Item with `has_variants=1` that defines the attribute set; concrete SKUs are `variant_of` it (e.g. template `KS0001`, variants `KS0001-CMM-153-PURPLE`).

### 配套物料 (Supporting Items)
The semi-finished/auxiliary items generated from a product template via the「一键创建配套物料及变体」button (Client Script → `key_test.add_item_semi.create_supporting_items_and_variants`). 9 types: 皮壳# (same attrs as product), 内胆# (product size + inner fabric/color), 绍兴包装皮壳#/成品#/半成品# (size only), 波兰PL/美东USNJ/美中USTX包装成品# (size only), 重量模板# (fabric+size, no color). Not every SPU uses all 9.

The button copies **existing product variants** onto supporting templates. It is not a cartesian product of every attribute value. Extra cover SKUs with no matching finished-good variant are leftovers from other generation paths, not the one-click workflow.

皮壳 SKU 必须是 `PK#{SPU}` 模板的变体（`variant_of` 加上与成品相同的 attributes）。`variant_of` is set once at insert; a standalone cover cannot be attached later and must be recreated.

### 产品成品登记 (Product-Finished-Good Registration)
三方库存主线中的映射规则：有库存通途完整 SKU（包括 `-Cover`/`-Foam`）必须作为 `customer_items.ref_code` 至少存在于一个 EN `KS` 产品成品变体。`PK#` 皮壳和 `HM1510` 海绵的登记不能替代它，因为 EN 销售订单 Excel 先用通途 SKU 找产品物料，再由交付形态列决定皮壳、成品或半成品的实际处理。

### 精确登记 / 仅基码匹配 (Exact Registration / Base-Code Candidate)
通途 SKU 和 EN 产品客户码的两阶段状态。完整 SKU（大小写不敏感）命中 `customer_items.ref_code` 才是“已精确登记”；剥离 `-Cover`/`-Foam` 后只命中基码是“仅基码匹配”，只能作为补登候选，不能用于完成率或赛狐覆盖率。

### 三方主线 (Tongtu-EN-Sellfox Mainline)
从通途有库存 SKU 到 EN 产品成品变体、再到同编号的赛狐产品 SKU 的闭环。赛狐对象始终是 EN 产品 `item_code`，而非通途半成品原码；套件、非产品项、主体骨架和 PK#/HM1510 维护都必须在报告中单列，不得静默忽略或擅自写入。


### Product Bundle / EN 套件 (TJ#)
ERPNext 用原生 Product Bundle 表示组合销售对象；work_order_task 扩展会在保存时自动生成上层物料 `TJ#<前缀1>x<数量>_<前缀2>x<数量>-001`，物料组 `套件#`，单位 `套`，`is_stock_item=0`，并导出赛狐「导入组合商品」Excel 模板。REST 创建只需传真实存在的 items，服务端负责编号；不要传临时 new_item_code，创建后组成不可改。
完整通途SKU 必须作为客户物料号登记到上层 Item `customer_items.ref_code`（客户组默认美国公司）；同一 SPU 同数量下不同面料/颜色/尺寸变体通过 `-001/-002/...` 序号区分。

### 套件# 分类 / 赛狐组合 SKU
赛狐镜像 EN 的 `套件#` 一级分类（2026-08-11 已建，`fullCid=428697-`）。组合 SKU 在赛狐用 `isGroup=1` + `childSkus` 表示；创建时必须带上底层商品的 `childId`、`sku`、`num`。**TJ# / Product Bundle 镜像**要求赛狐组合 SKU、EN Product Bundle、上层 Item 三者编码和名称必须一致，日常对账用 `sellfox_combo_ops.py sync-combos`，不要手写 REST 或临时编号。三角类 `PK# -> KS x1` 是销售库存代理，不属于 `套件#`，不得进入该同步链；见「皮壳共享库存代理」。
通途客户物料号匹配按大小写不敏感处理；批量场景可先生成“底层物料 × 数量档”全量计划，再按阶段执行并记录进度。
登记表整批为“无捆绑SKU”时，可按 `基码-EN物料码-Npcs` 合成唯一客户物料号并提前登记，基码来源（直接/-Cover去尾/同款借用）写入阶段记录备注。

### 皮壳共享库存代理（赛狐组合商品）
三角类皮壳 Listing 在通途/赛狐并行期、现场只有一个未拆分实物池时的销售层默认关系：赛狐 `KS` 是有库存普通商品，`PK#` 是 `isGroup=1` 的无独立库存组合商品，唯一子项为 `KS x1`。它让成品与皮壳 Listing 扣同一个**用户确认的**分公司仓库存池，但不表达物理组成、生产 BOM 或 EN Product Bundle，不属于 `套件#`，也不得进入 `TJ#` 同步链。运营在赛狐按**组合商品**、SKU `PK#` 查找；它们不会出现在「普通商品」筛选里，也不要用商品名称「皮壳#」当普通商品搜索词。`PK#` 并非永久必须为组合商品；只有仓库分别盘点皮壳/成品并记录转换时，独立普通库存才成立。美中通途另有皮壳仓库，不得默认把 DANEEY 主仓当共享池。赛狐 `POLAND` 对应通途 covers 仓，不对应 `FZHPoland-finished`。

组合代理只共享数量。赛狐「采购成本」至少三层（商品主数据绍兴发货、期初仓+SKU 尾程前、备货单指定采购单价+头程），与 EN Tongtool Cost Review 按通途后缀和交付形态切的局部成本不是同一件事。子件仓 FIFO 被订单吃到，对皮壳 Listing 仍不算利润通过。

### 库存重复承诺（Duplicate ATP）
同一物理池的数量被完整写给多个独立销售 SKU，导致系统可售量总和大于实物。例如通途 `TT123=100` 同时写成赛狐 `KS=100`、`PK#=100`，会暴露 200 件可售量。一对多映射不能直接复制数量；必须只选一个持有池、守恒拆分、记录身份转换，或由外部共享池分配器计算 ATP。

### 赛狐订单成本覆盖层
用 EN 订单成本口径（Cost Review 与特殊规则分开计算，不得混用）在订单层计算皮壳等交付形态的产品成本，再通过赛狐「导入 FBM 采购成本」覆盖原生商品/FIFO 成本。FBM 智能推荐优先采用导入采购成本；订单 API 的 `mergePurchaseCost` 可用于回读导入、手改和退款成本的合并值。公开 OpenAPI 暂未发现写端点；FBA 发货单创建里的「单位采购成本（导入）」是头程发货单字段，不是 FBM 订单成本覆盖。当前稳定入口是 Excel/UI，自动化应先生成模板，再评估 Playwright。

### 赛狐加工 SKU
赛狐商品类型 `isGroup=2`。加工 SKU 有自身库存，支持 `needAssembleProcess`、`processCost` 和 `childSkus`，库存流水里有加工单/拆分单事件。取消“开启加工过程”只缩短状态流，不等于无库存别名。适合未来赛狐接管库存且需要 `PK#` 独立库存时评估；当前通途/赛狐并行阶段不默认启用。

### 库存事实源（Inventory Source of Truth）
多个系统都展示库存时，被选为校准基准的系统。当前通途/赛狐并行期，三角类分公司普通仓以通途为事实源，定期只校准赛狐底层 `KS`。同步必须处理“赛狐订单已扣、通途尚未标记发货”的时间差，避免旧快照把库存加回。FBA、退货仓和不良品仓不因 SKU 相同自动加入共享池。库存事实源不等于利润事实源：皮壳 Listing 的利润仍以 EN Tongtool Cost Review 为准。

### 在线产品配对 vs 订单包裹配对
在线产品配对（`matchByMsku`/`matchByAsin`）决定未来订单 MSKU 映射，可用正确组合 SKU 覆盖；订单包裹配对（`updateMatch`）只改存在包裹的明细，且已发货包裹会被赛狐拒绝（`已发货状态，不能修改商品配对`）。
## 通途订单成本核算

### Tongtool Cost Review
EN（测试与生产）侧的订单成本核算，用户确认依据通途完整 SKU 后缀（至少 `-Cover`、`-Foam`、`-1`、`-2`）和销售订单「皮壳/成品/半成品」交付形态，从 BOM 选**局部**成本。完整选路源码不在本仓库，Agent 不得用本地文件杜撰公式。赛狐组合商品扣子件批次不能复现这套逻辑。

### 特殊规则 1.7.0 引擎（engine_170.py）
本仓库 `tongtool_order_cost/tongtool_order_cost/engine_170.py` 可验证会重写皮壳/产品、绍兴加工、国外二次加工、头程、海外仓和尾程等分量，再重算产品成本、订单总成本与利润。它**不是** Tongtool Cost Review，而是本地对共享 Google Sheet Jeck 规则的落地；不能拿它当 Cost Review 的实现，也不能用它解释赛狐原生成本。

### 特殊规则（订单改销售额成本）
运营在共享 Google Sheet 里按通途 SKU 改订单销售额或成本科目的规则。当前 notebook 1.7.0 读「和财务部共享」里的 Jeck 工作表。一行里系数模式与参考值模式不能共存；参考值按收款币种乘汇率再乘发货数量写入目标列。本地落地见「特殊规则 1.7.0 引擎（engine_170.py）」，与 EN Tongtool Cost Review 是两套东西。

### 通途主档 SKU 改名
通途允许修改货品主档上的 SKU 字符串。改名后，历史订单导出仍保留导出当时的名字，而规则表通常已是新名。精确匹配管道必须改订单侧旧名去对齐新名，而不是把规则改回旧名。

### FBA 账期尾程差
Amazon FBA 账期费用里已经包含平台履约尾程。特殊规则里对 FBA 填的负数尾程参考值表示「账期尾程减去目标尾程」的冲减，不是再加一笔正的尾程。零或正数对 FBA 仍应跳过，以免重复计入。

### 通途发货仓库（Tongtu Shipping Warehouse）
生产 ERPNext doctype，登记通途自发货仓库。字段：`warehouse_name`（Data）、`warehouse_classification`（**Link → Tongtu Shipping Warehouse Classification**，如 USNJ美东分公司/USTX美中分公司/PL波兰分公司）、`shipping_region`、`warehouse_code`（USNJ/USTX/PL/…）、以及皮壳/绍兴半成品/成品/总成本/加工/头程运费的成本列名。仓库改名后**旧名保留**给历史订单，新前缀名按分公司分类+成本列照抄补登记。

### 发货仓库前缀改名（美东-/美中-/波兰-）
通途自发货仓库最近把主仓名加上分公司前缀：`CENTRADE`→`美东-CENTRADE`、`FZH-DANEEY`→`美中-FZH-DANEEY`、`FZHPoland-covers`→`波兰-FZHPoland-covers`，并新增美东/波兰退货仓。原则是 3 家国外分公司各保留 1 普通仓 + 1 退货仓。生产订单仍大量引用旧名，所以两套名字都要在 ERPNext 登记。

### 订单发货仓库对应成本来源
财务共享表「和财务部共享」里的 ws，8 列把发货仓库映射到成本：`发货仓库 | 对应成本工作簿 | 成本来源编码 | 发货仓分类 | 头程运费来源编码 | 二次加工成本来源编码 | 发货区域 | 发货仓按销售汇总分类`。编码口径：CENTRADE→HEAD-US/2CJG-US；FZH-DANEEY 主仓与皮壳→HEAD-USTX-PK/2CJG-SX；成品/半成品/退货→HEAD-USTX/2CJG-SX；FZHPoland-covers→HEAD-PL/2CJG-PL；FZHPoland-finished→HEAD-EUHWC/2CJG-SX。

## Amazon 在线商品配对

### AFN / MFN
赛狐 Amazon 在线商品字段 `switchFulfillmentTo`：`AFN` = FBA（亚马逊仓发），`MFN` = FBM（卖家自发）。FBA listing 多数是绍兴压缩包装的成品，也有套件；单独卖皮壳/海绵的概率低，但不能用“库存缺 SKU”当不能配对。

### 在线商品配对 vs 多平台配对
赛狐两套独立机制。Amazon MSKU↔赛狐 SKU 走在线商品（`pageList` / `matchByMsku` / `matchByAsin` / 模板 `import_product_msku_match`）。多平台配对（`getList` / `save` / `importMatchTemplate`）即使注册了 Amazon 也不走这条。不要混用接口或模板。

### listing 意图 vs 库存主线
配对问的是「这条在售 listing 对应哪个可销售赛狐 SKU」。通途有库存 SKU 必须登记 EN 客户码，是另一条主线。标题含 Cover/Foam 不等于 listing 在卖皮壳或海绵；KS0244 等枕套成品本来就叫 cover。有库存半成品不必都有 Amazon listing。

### Gold A vs 活证据
Gold A：历史已配对 ∩ 通途别名唯一 ∩ EN/赛狐一致，只用于训练清洗。活证据：当前已配对的 `commoditySku`（含无别名的 Silver），按同 MSKU/ASIN/parent 传播。高可信看活证据是否唯一，不看是不是 Gold A。

## Integrations

### Cursor MCP vs Codex MCP
通途官方 MCP 在两个宿主上要**分别注册**。Codex 写 `~/.codex/config.toml`（`setup_codex_mcp.ps1`）；Cursor 写 `~/.cursor/mcp.json`（`setup_cursor_mcp.py`）。仓库 `.cursor/` 整目录 gitignore，clone 不会带上项目级 `mcp.json`。通途不在 Cursor Marketplace，Agent 也没有可调用的「安装 MCP」对话框。Cursor 用户级服务器在工具目录里叫 `user-<mcp.json 键名>`。

### Tongtool ERP2 Shared Rate Bucket

通途 ERP2.0 的同一商户上游调用预算。2026-08-13 实测：两个独立 App 经 MCP 调用仍共用每分钟 5 次额度；主 App 连续 5 次成功后，第二 App 的首个同端点调用返回业务码 526。这不是每 App 独立额度。524 表示细粒度接口未授权，不能当作限流；所有 ERP2 自动化应合并计数、缓存和退避。

### DingTalk Custom Robot (钉钉自定义机器人)
A webhook-based DingTalk group messaging channel used by AI agents (WorkBuddy, Claude Code) in this project to send notifications and file download links. Uses HMAC-SHA256 signing. Distinct from DingTalk enterprise internal bots — custom robots do not require AppKey/AppSecret and are scoped to a single group, making them safe to share with non-developer agent users. Cannot send file attachments directly; file delivery uses ActionCard messages with download links hosted on ERPNext.

## Flagged ambiguities

- "'五桶' had been used as if it meant IvyeaOps 五杠杆 — they are distinct (search-term labels vs optimizer action candidates)."
- "Amazon Auto/product/category reports often put ASINs in the customer search-term column — that is real report data, not a mapping bug; keyword 收割 must not treat those strings as exact keywords (filter deferred as of 2026-07-28)."
- "通途主档 SKU 改名后的旧名，与规则笔误（例如 Foam FBA BLACK-97），不是同一类问题；像旧名的字符串要先查主档。"
- "赛狐「采购成本」曾被用来同时指商品主数据绍兴发货、期初仓+SKU 尾程前、备货单指定采购单价+头程；三者不可互换，也都不等于 EN Tongtool Cost Review 的皮壳切片。"

## 平台账期对账

- **账期文件**: Overstock `OSTKUS-*.xlsx` 含 `Payment Summary` + `Detail` + `Mozart Reports`，是结算文件，不是平台订单导出。
- **Tongtool Order**: EN 生产系统里的通途订单快照；Overstock 单据名通常为 `OS-{platform_order_id}`，另一账号 `OSTK02US` 使用 `OSFD-` 前缀。
- **拆单后缀**: 多 SKU/多件订单在通途/EN 会拆成 `_1/_2/_3` 子单，`platform_order_id` 保留后缀；汇总时需排除金额相同的“无后缀重复主单”。
- **对账金额口径**: 用 `order_amount` / `products_total_price` 对账；`order_items.transaction_price` 是组件行，不能加总；`actual_total_price` 在退货订单上可能为 0。
