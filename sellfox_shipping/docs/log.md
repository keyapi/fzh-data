---
okf: v0.1
type: Log
module: sellfox_shipping
created: 2026-07-15
updated: 2026-08-06
---

# sellfox_shipping - 变更日志

## 2026-08-06 - 赛狐 Outbox PR 1 候选事实层

- 新增 migration 0020、订单级 Outbox、来源表与账户 Policy 默认值。
- API label 成功和 Excel tracking 导入统一通过事务 finalizer 生成候选。
- 新增候选去重、来源合并、SUPERSEDED/CONFLICT 规则及显式历史扫描。
- 新增 sellfox-outbox-list/show/scan-candidates，全部无赛狐 HTTP；扫描默认 dry-run。
- 增加成熟方案调研与完整 Outbox 设计；PR 2/3 仍负责真实执行与能力门禁。

## 2026-08-05 - Migration 0019 与生产验收交接

- 合并后全量测试发现：历史 SQLite 库从 0015 连续升级时，0018 使用 `op.add_column(ForeignKey(...))` 会触发 SQLite 不支持的独立约束 ALTER。
- Migration 0018 改为先新增普通列；Migration 0019 使用 Alembic batch copy-and-move 建立外键。
- 0019 同时修复已被旧 0018 半应用并标记为 head、但 `resolution_evidence_id` 外键缺失的数据库。
- 新增历史 0015 连续升级和半应用 0018 修复测试；自动化基线更新为 221 passed、2 个既有 warning。
- 更新路线图：购标恢复核心标记完成，赛狐 outbox 标记为用户延期，下一阶段改为生产验收与三方对账评估。
- 新增 Jack Agent 生产验收接手规范，明确禁止无授权真实购标、取消和赛狐回写。

## 2026-08-05 - PR #143 可靠性复审修复

- Migration 0018 为 resume claim 增加 `claim_token`，并将 lease 改为 SQLite `BEGIN IMMEDIATE` 条件更新。
- lease 释放必须匹配 token，过期 worker 不能清除新 worker 的 claim。
- investigation 增加结构化 `conclusion`；`confirmed_created` 同时保存并核对 `provider_order_id`。
- UNKNOWN_BLOCKED 结案在同一事务内校验证据归属、结论和权威引用，并把 `resolution_evidence_id` 持久化到 operation。
- `label-operation-investigate` 新增必填 `--conclusion`；空白 `other` 证据不能释放购标槽位。
- 新增跨 repository 并发、lease fencing、证据错配和审计关联测试；测试基线更新为 217 passed。

## 2026-08-05 — UNKNOWN_BLOCKED 证据化结案 (PR C：可靠性收口)

- Migration 0017: 新增 `shipping_label_investigations` append-only 表
- 新增 `InvestigationRow` 模型和 `InvestigationRecord` dataclass
- `PackageRepository` 新增 `add_investigation()` / `get_investigations()` / `get_investigation()`
- `LabelService` 新增 `add_investigation()` — 仅记录调查，不解除阻断
- `resolve_unknown_blocked()` 增加必填 `evidence_id`，验证 evidence 归属同一 operation
- 新增 CLI `label-operation-investigate` — 记录调查（evidence_type: ticket/carrier_portal/email/other）
- `label-operation-resolve` CLI 增加必填 `--evidence-id`
- 更新已有测试适配新参数；测试基线: 212 passed, 2 warnings

## 2026-08-05 — resume 并发与幂等收口 (PR B：可靠性收口)

- Migration 0016: `shipping_label_operations` 新增 `claimed_by` (String) 和 `claimed_at` (DateTime, nullable)
- `PackageRepository` 新增 `acquire_resume_lease()` / `release_resume_lease()` — SQLite 原子 lease，同一 operation 仅一个恢复者
- `resume_label_acquisition()` 增加 lease 保护：claim 失败返回 409；lease 在异常/完成时自动释放
- SUCCEEDED 状态 resume 幂等返回已有结果（`idempotent: true`）
- `label-operation-resume` CLI 增加必填 `--actor`（之前硬编码 `cli-resume`）
- `label-operation-resolve` CLI 增加必填 `--actor`（之前硬编码 `cli-resolve`）
- 更新已有测试适配新行为；测试基线: 212 passed, 2 warnings

## 2026-08-05 — 分页计数修复 (PR A：可靠性收口)

- `count_packages()` 改用 `count(distinct package_id)`，修复多订单/多标签场景下 JOIN 行膨胀导致总数放大
- `list_packages()` 与 `count_packages()` 过滤语义一致（复用同一 date_field/isouter/status 逻辑）
- 新增 9 个 repository 测试：多订单日期过滤、多标签（有效/取消/混合）、分页 offset/limit 一致性、order/label 日期边界
- 浏览器验证：分页切换、Dashboard/Transactions 标签页重置、日期类型切换
- 测试基线: 212 passed, 2 warnings

## 2026-08-05 — 赛狐下单时间 + 有效面单时间 + 分页 + 标签页持久化

### 列表新增字段
- **赛狐下单时间**：`shipping_orders.purchase_date`，取包裹内最早订单的下单时间，列表+详情页均显示
- **有效面单时间**：`shipping_labels.created_at`，取 status≠cancelled 的最早面单时间，无则显示"—"

### 日期过滤增强
- Custom Date Range 新增日期类型切换：面单时间 / 下单时间
- 面单时间过滤排除已取消面单（`status != "cancelled"`）
- 下单时间按 `purchase_date` 过滤

### 分页功能
- 共 N 条 / < 1 2 3 ... > 翻页 / 20/50/100/200 条/页
- "..." hover 显示 ◀◀/▶▶，点击快速跳页
- 切换标签页自动重置到第 1 页

### 标签页持久化
- 切换标签页同步更新 URL `tab` 参数，翻页保持标签页状态
- 详情页返回时 `history.back()` 保留完整过滤/分页状态

### 修复
- `package_repository.py`：`list/count_packages` 加 `date_field` 参数
- `PackageListItem` 加 `purchase_date` / `label_created_at` 字段
- `_build_pagination()` 辅助函数
- `_apply_package_fields`：地址保护改为逐字段非空才写

## 2026-08-05 — #139 补丁：蜴国际 resume 落库 + resolve 动作

- `_resume_lizard_label`：`register_artifact` 后补 `insert_label`；失败保留 `LABEL_PENDING`，不误标 SUCCEEDED
- `allowed_actions`：`UNKNOWN_BLOCKED` → `resolve`（不再只显示 investigate）
- `resolve_unknown_blocked_operation`：补 `append_audit_event`

## 2026-08-05 — 购标 operation 只读 CLI

- 新增 `label-operations-list`：按账户、包裹、状态、承运商过滤，输出稳定 JSON envelope
- 新增 `label-operation-show`：展示 operation 与脱敏后的 label/artifact 摘要
- `allowed_actions` 明确区分 `resume`、`resolve`、`investigate` 与终态无动作；不提供 retry_create
- 查询路径不调用承运商 API，不输出原始 carrier response、label URL 或 error summary

## 2026-08-05 — 恢复 CLI、错误分类与赛狐 Outbox 后续计划

- 确认 PR #132-#136 已进入 main，购标安全核心与 create_label 恢复持久化闭环成为新基线
- 新增实现级 Spec：AI 优先 CLI 契约、carrier error taxonomy、带 provider ID resume、UNKNOWN_BLOCKED 证据化人工结案
- 赛狐回写采用现有 SubmissionIntent/scope guard + 新增 outbox lease/退避，不把购标与回写重试耦合
- 真正的 submitToPlatform 默认关闭；后续由同事在用户确认的单个测试包裹范围内验证

## 2026-08-05 — PR #135 取消原子收口 + 蜴国际 insert→LABEL_PENDING

- `finalize_label_cancellation()`：同一事务内 label inactive + operation CANCELLED
- `cancel_label`：承运商确认后只调原子收口；label 已 cancelled 但 op 仍活跃时可本地 reconcile
- 蜴国际 `insert_label` 失败 → `LABEL_PENDING`（保留 provider ID），不再误标 UNKNOWN_BLOCKED
- 清 blueprint trailing whitespace

## 2026-08-05 — PR #135 恢复闭环：ACCEPTED / LABEL_PENDING

- VITE/蜴国际：拿到 provider order id 后立即 `SENT → ACCEPTED`（在适配层，不等 ship_package 返回）
- poll 超时 / URL 缺失 / PDF 失败 / artifact 失败 → `LABEL_PENDING`，保留 provider_order_id 与 tracking；create 只调用一次
- 取消边：`ACCEPTED/LABEL_PENDING/SUCCEEDED → CANCELLED`；崩溃窗口仅允许 `SENT → CANCELLED` 当已有关联 label
- `cancel_label` 不再静默吞 transition 失败：审计 + 向操作者返回 409
- `app.py` VITE 报价复用严格地址 builder；缺字段时零外部 rate 调用
- Follow-up（未做）：resume CLI；carrier error taxonomy（勿仅靠 HTTP 状态）
- 新增 recovery 测试 8 例

## 2026-08-04 — 购标安全接线 create_label

- `LabelService.create_label()` 接入 preflight → claim → SENT → carrier → SUCCEEDED / FAILED_SAFE / FAILED_FINAL / UNKNOWN_BLOCKED
- `transition_label_operation` 增加合法边表；取消确认后 operation → CANCELLED
- Vite `_build_ship_from` / `_build_ship_to` 删除 Belmont / Customer / XX / 0000000000 虚构兜底
- `ship_package` / lizard insert 传递 `operation_id`
- 蓝图澄清：SUCCEEDED 不占活跃 operation 唯一槽；挡住再购的是活动 label
- 测试：safety 扩至 11 例；全量 160 passed
- 待做：resume CLI、细粒度 ACCEPTED/LABEL_PENDING、app.py 报价路径同类兜底

## 2026-08-04 — 生产可靠性蓝图与路线图

- 独立调研 ShipStation、Sendcloud、Shipium、Metapack、EasyPost、Shippo、Karrio 等成熟方案，确定保留模块化单体和 API/Excel 双通道。
- 新增生产可靠性 Spec：事实边界、preflight、购标 operation 状态机、SQLite 原子 claim、UNKNOWN_BLOCKED 和恢复契约。
- 新增 Must/Should/Later 路线图和 Agent 任务包；首批开发锁定“购标安全核心”。
- 明确短期不迁 PostgreSQL、不部署 Karrio Server、不开发装箱算法。


## 2026-08-04 — 购标安全核心实现 (PR #134)

- 新增 shipping_label_operations 表（migration 0015）与 LabelOperationRow/Record ORM 模型
- claim_label_operation()：SQLite BEGIN IMMEDIATE 原子占用，并发安全；同一包裹同时最多一个活跃操作或标签
- 	ransition_label_operation()：状态机流转，持久化 provider_order_id/tracking_number/error 信息
- LabelService.preflight()：统一前置阻断——审核状态、重尺全正值、收件必填、VITE 仓库地址电话完备性
- shipping_labels 增加 operation_id/is_active：生成默认活跃，取消设 is_active=false 释放约束
- 部分唯一索引：uq_shipping_labels_one_active_per_package + uq_label_operations_one_active_per_package
- LabelPreflightResult dataclass 用于 preflight 输出
- 状态机：RESERVED → SENT → ACCEPTED → LABEL_PENDING → SUCCEEDED / FAILED_SAFE / FAILED_FINAL / UNKNOWN_BLOCKED
- SUCCEEDED 不在活跃 operation 集合中（终端状态，不阻止后续购标）
- 测试：新增 5 个 safety 测试；全量 154 passed
- 版本断言：全部迁移测试更新到 0015_label_acquisition_safety
- 凭证扫描：零输出

### 待集成
- ~~preflight+claim 接入 create_label()~~ → 见「购标安全接线」条目
- CLI 命令 label-operations-list / label-operation-resume 尚未实现
- app.py 报价路径 `_build_vite_ship_*` 同类虚构兜底尚未清理

## 2026-08-04 — 背贴 PDF 页内嵌入预览 + 批量打印

### 背贴预览
- 新增 `GET /packages/{sn}/sku-label?inline=1` 参数：`Content-Disposition: inline`，浏览器原生 PDF 渲染
- `package_detail.html`：商品行面板底部嵌入背贴预览（`<embed>`），默认显示，可关闭

### Transactions 标签页
- 包裹列表新增 Dashboard / Transactions 双标签页
- Transactions：日期过滤（Custom Date Range 下拉面板 + 预设按钮）+ 状态/审核/渠道筛选
- 渠道名筛选：新增 `/api/channels` 端点，`<datalist>` 下拉 + 模糊搜索
- 表格新增复选框列 + 全选，选中后表内动态显示批量操作栏（🚚 货车图标）

### 批量打印
- 新增 `POST /api/packages/batch-print`：pymupdf 合并 PDF，支持 sticker / label / both 三种类型
- 严格校验：任一包裹缺少文档 → 422 拒绝整个批次，逐条列出原因
- 合并顺序：按包裹顺序，背贴 → 面单，不可错乱
- 预览弹窗：全屏遮罩 + 文档类型标签页切换 + AbortController 防竞态
- `package_repository.py`：`list_packages()` / `count_packages()` 支持按面单创建时间过滤
- `list_distinct_channels()`：去重渠道名列表

### 批量打印功能

- 包裹列表页新增复选框列 + 全选 + 底部浮动操作栏（显示已选数量）
- 新增日期过滤：预设按钮（今天/近7天/近30天/全部）+ 自定义日期范围，按面单创建时间过滤
- 批量打印弹窗：选择打印类型（仅Label/仅背贴/面单+背贴），背贴在前、面单在后
- 新增 `POST /api/packages/batch-print`：pymupdf 合并 PDF，缺文档的包裹自动跳过
- `package_repository.py`：`list_packages()` / `count_packages()` 支持日期过滤

## 2026-07-28 — SKU 背贴 PDF 生成分析

- 深入分析 Google Colab notebook (148 cells) 中的背贴生成逻辑
- 提取 PDF 生成核心参数：4×2" 页尺寸、reportlab Table + Code128 条形码 + 字体自适应缩放
- 识别数据依赖：中文名称 + 西班牙语名称来自 Google Sheet "US SKU Name"（需 service account 权限）
- 提出 3 种名称获取方案（ERPNext 优先、Google Sheets 兜底、赛狐商品 API 备用）
- 产出：`docs/research/sku-label-back-sticker-analysis-2026-07-28.md`

## 2026-07-30 — SKU 背贴模块实现

### 新增模块：`sku_label/`
- `pdf_generator.py`：reportlab 4×2" 背贴标签 PDF — 包裹号 + Code128 条形码 + 表格（#/SKU/QTY/中文名/西语名），中英混排自适应字号
- `name_lookup.py`：`SkuNameLookup` 通用工具类 — 查 ERPNext `item_languages` 子表获取 `tt_sku`(通途SKU)、`item_name_cn`(中文)、`item_name_es`(西语)
- `__init__.py`：导出 `generate_sku_label_pdf` + `SkuNameLookup`

### CLI + Web 集成
- `cli.py`：新增 `sku-label` 命令（`--package-sn` + `--output`）
- `app.py`：新增 `GET /packages/{sn}/sku-label` 端点，返回 PDF FileResponse
- `package_detail.html`：商品行标题旁新增「下载背贴 PDF」链接
- `pyproject.toml`：新增 `reportlab>=5.0.0` 依赖

### 商品行「商品名称」列
- 新增 migration `0014_carton_override_item_name`：`shipping_carton_overrides` 表添加 `item_name` 列
- `CartonOverrideRow` / `CartonOverrideRecord`：新增 `item_name` 字段
- `package_repository.py`：新增 `upsert_carton_item_name()` 方法（仅保存名称，不要求完整 dims）
- `ErpnextDimsLookupV2`：`_FIELDS` 新增 `item_name`，新增 `_name_cache` + `get_item_name()` 方法
- `CascadingDimsLookup`：新增 `get_item_name()` 代理
- `StaticDimsLookup`：新增 `get_item_name()` stub（返回 ""）
- `_carton_rows_for_package()`：查 EN 获取 item_name → 持久化到 carton_overrides → 渲染到模板
- `package_detail.html`：表格新增 `<th>商品名称</th>` + `<td>` 列

### Bug 修复
- `get_package_dims()`：`session.get()` 按主键 id 查改为 `filter(package_id==)` 按外键查，修复面单创建 "no dimensions available" 错误
- `_compute_package_dims()`：override 存在但 dims 不完整时回退到 EN ZLMB resolved dims
- `_carton_rows_for_package()`：source 判断改为 `override.dims.is_complete` 才标「本地补录」

### 测试
- 5 个测试文件的 migration 版本断言从 `0013` 更新到 `0014`
- `StaticDimsLookup` 补 `get_item_name()` stub
- 149 tests passed

### 2026-08-03 — 模板 input value 回退修复

- 修复 `package_detail.html` 中 4 个 dims input 的 value 表达式：`cr.override.dims.xxx if cr.override and cr.override.dims.is_complete else cr.resolved.xxx`
- 与 07-30 的 `_compute_package_dims` 和 `_carton_rows_for_package` source 修复形成完整闭环（3 处均需检查 `is_complete`）

## 2026-07-28 — 双承运商面单创建 + 取消 + PDF 下载

### VITE 面单 (vite/shipment.py)
- `ViteShipmentService.ship_package()`：构建请求体 → `POST /shipment2/gofo`(或 fedex) → 轮询 `GET /shipment2/label/{orderId}`(5s×36次) → 下载 PDF → `register_artifact()` → `insert_label()`
- 服务类型由用户选择(GOFO_PARCEL / FEDEX_GROUND)，不做尺寸自动覆盖；GOFO 超过 22in 时 VITE API 返回 400 错误，用户可自行切换 FedEx
- 单元注入 `fetch_bytes`/`sleep`/`monotonic`，不依赖真实 HTTP

### 蜴国际面单 (label_service.py)
- `_create_lizard_label()`：接入已有的 `LizardApiShipmentService`（createOrder → poll getLabel → PDF → artifact）
- sm_code 优先级：用户选择 > 报价历史最近 lizard channel > 默认 FedEx-Ground-J-TX
- 赛狐原始数据 `weight_grams` 为空时自动从 `shipping_package_dims` 填充

### LabelService (label_service.py)
- 承运商无关编排层：`create_label()` / `cancel_label()` / `download_label_pdf()` / `get_labels_for_package()`
- 重复面单防护：存在 status≠cancelled 的面单时返回 409，提示先取消
- VITE cancel：调用 `DELETE /shipment2/label/{orderId}` → 更新 label status=cancelled

### 数据库 (package_repository.py + 0013 migration)
- 新增 `shipping_labels` 表：tracking_number, carrier_order_id, artifact_id, status, total_amount 等
- `ShippingLabelRow` ORM + `ShippingLabelRecord` dataclass
- Repository 方法：`insert_label()` / `get_label()` / `list_labels_for_package()` / `update_label_status()`
- 创建时间 UTC→UTC+8 转换，与历史报价一致（`%Y-%m-%d %H:%M:%S`）

### Web UI (package_detail.html)
- 「创建面单」面板：承运商选择器 + 动态服务类型(JavaScript 切换) + 操作者 + 创建按钮
- 面单历史表格：创建时间、承运商、追踪号、服务、金额、状态、PDF 下载、取消按钮
- 取消确认弹窗：`confirm('确认取消面单？取消后无法恢复。')`

### API 端点 (app.py)
| Method | Path | 功能 |
|---|---|---|
| POST | `/api/packages/{sn}/create-label` | 创建面单(JSON) |
| POST | `/api/labels/{id}/cancel` | 取消面单(JSON) |
| GET | `/api/labels/{id}/download` | 下载面单 PDF(FileResponse) |
| GET | `/api/packages/{sn}/labels` | 查包裹面单列表 |
| POST | `/packages/{sn}/create-label` | 创建面单(HTML form) |
| POST | `/packages/{sn}/cancel-label/{id}` | 取消面单(HTML form) |

### Bug 修复
- 运费试算：移除 `_get_vite_rate()` 中的路由检查，蜴国际路由的包裹也能显示试算面板
- `_package_detail_context`：`vite_rate` 从 fetch-rates 端点透传，避免硬编码 None
- 时区：label `created_at`/`updated_at` UTC→UTC+8

### 测试
- 全部 149 tests passed
- VITE 生产环境：FedEx Ground 创建成功（追踪号 874966964957），PDF 可下载，取消成功
- 重复创建拦截：409 "已存在有效面单"

### 2026-07-28（续）— VITE 双端点报价 + 历史报价表优化 + 交易流水页

#### VITE 双端点报价 (`_get_vite_rate`)
- 同时查询 GOFO 和 FedEx 两个端点（之前根据尺寸二选一），全部结果存入历史
- 抽取 `_vite_rate_to_dict()` 统一转换
- GOFO 超 22in 时 VITE API 返回 400，静默跳过（仅 FedEx 可用）

#### 历史报价表优化
- 列重组：时间、**承运商**、**产品**、运费、计费重、Zone、类型、最长边、原始数据
- 承运商列：明确显示 VITE / 蜴国际 badge，不再混淆 GOFO/FedEx
- 产品列：VITE 显示 GOFO Parcel / FedEx Ground + 服务描述；蜴国际显示 sm_code

#### 交易流水页 (`/labels`)
- 新页面 `/labels` + 模板 `labels_transaction.html`
- 汇总卡片：按承运商分组统计笔数、金额、生成/取消数
- 交易表格：时间、承运商、追踪号、服务、订单号、金额、状态
- 天数筛选：1/2/7/14/30 天，默认 2 天
- 数据来源：`shipping_labels` 表（每次 API 调用均有完整记录）
- 导航栏所有页面新增「流水」入口
- **VITE 无公开交易流水 API**（/shipment2/list 返回 403，仅 EEVEE 网页端可用）

#### 测试
- 全部 149 tests passed
- 历史报价：单次点击拉取 VITE GOFO + VITE FedEx + 蜴国际全部产品
- 该包裹 (66×56×5cm) 客观上只有 2 个可用产品（GOFO 尺寸限制 + 蜴国际 7/8 产品 total_charge=null）
- 交易流水页：显示 8 笔 VITE 交易，合计 $99.52

## 2026-07-23 — EN 重尺 V2：sibling 借用 + 直连赛狐 + 筛选/分页修复

### 直连赛狐 API
- 新增 `sellfox_shipping/direct_sellfox_client.py`：OAuth2 + HMAC-SHA256 直连 `openapi.sellfox.com`
- CLI `_get_client()` 自动检测 `SELLFOX_APP_ID`/`SELLFOX_APP_SECRET` 切换直连/代理模式
- `.env` 新增 `SELLFOX_APP_ID` / `SELLFOX_APP_SECRET` / `SELLFOX_API_DOMAIN`

### 筛选修复
- `app.py` 两处路由 `or None`：表单空值 `""` → `None`，避免 DB 精确匹配空字符串导致 0 结果
- REST API `GET /api/packages` 补 `review` query param
- 前端 `packages.html`：审核下拉加 `shipped`/`closed` 选项 + badge 按状态变色 + `autocomplete="off"`

### 分页修复
- `package_service.py`：锁定首页 `total_size`，防止 API 分页过程中 `totalSize` 波动导致末页丢包
- 终止条件：`page_input_count < page.page_size`（末页）或 `processed >= locked_total`

### 自动审核
- `package_repository.py`：`_auto_set_review_on_terminal_status()` — sync 时 `has_shipped`→`shipped`，`has_canceled`→`closed`；人工审批不覆盖

### EN 重尺 V2（sibling 借用）
- 新增 `carriers/lizard/erpnext_dims_v2.py`：`ErpnextDimsLookupV2`
  - ZLMB 精确匹配 → 数据不全时触发 sibling 借用（同 KS + 同尺寸 + 跨面料）
  - 重量独立决策：FG weight → 借 sibling FG → FTY weight → 借 sibling FTY
  - 长宽高一体决策：FG dims 全>0 → 借 sibling FG dims → FTY dims → 借 sibling FTY dims
  - EN API 按 `ZLMB#{style}-%-{size}` 模糊搜索 sibling 池，带缓存
- `app.py` / `cli.py`：`_get_lizard_dims_lookup()` 移除 CommodityPageListDimsLookup（需代理），接入 V2
- `_carton_rows_for_package()`：`lookup.get()` 包 try/except，EN 故障不阻断页面
- 暂不做多 SKU 合并，每个 SKU 独立展示重尺

## 2026-07-22 — 文档交接体系刷新

- 热入口唯一：`AGENT_HANDOFF.md`（全貌七块）；session-progress / synthesis 降为冷档案/规划底稿
- synthesis：文首裁决框 + 承运人双通道 / P1C 出口 / 样例进度定点修订
- skill / README / 两处 index / ONBOARDING / sample-path 对齐
- Spec：`docs/superpowers/specs/2026-07-21-sellfox-shipping-handoff-docs-design.md`

## 2026-07-22 — tongtool-carrier-analysis：通途承运商分析 + 路由规则设计

### 背景
- 赛狐系统的承运商数据为测试数据（"蜴国际 89%"不实）
- 需要从 EN 生产系统查通途订单获取实际承运商分布

### 已完成
- 从 `erpnext.vilavi.cn` 拉取通途订单 14,416 条（CENTRADE 6,124 + DANEEY 8,292）
- 排除平台物流 (WF/OS/PB) 4,747 条 + Tiktok物流 23 条 → 有效 **9,646 条**
- 实际承运商：VITE-Fedex **69.2%**, M6180蜴国际 **26.2%**, US-FedEx 4.3%
- 包裹尺寸：9,633 SKU，中位数 57.5×48×18cm，体积重 9.7kg
- 多 SKU 合并算法：L=max, W=max, H=sum
- 5 层路由规则设计：定仓→定承运人→选服务→比价→执行

### 产出文档
- `docs/research/tongtool-carrier-analysis-2026-07-22.md` — 分析报告（含查找逻辑、9,646 条数据分布）
- `docs/research/routing-rules-design-2026-07-22.md` — 路由规则设计方案
- `docs/solutions/chatgpt-ups-fedex-analysis-reference-2026-07-22.md` — ChatGPT 参考

### 关键决策
- 承运商仅从 `raw_data.merchantCarrierShortname` 提取
- 排除 platformCode IN (WF, OS, PB) + Tiktok物流
- 初期直接比价（不设复杂评分公式）
- Expected Cost / Carrier Profile 等待 Invoice 数据积累后实现

## 2026-07-20 — ce-compound：trackNo 写路径边界

- `docs/solutions/architecture-patterns/sellfox-trackno-write-path-vs-local-import.md` — 本地 import ≠ 赛狐 UI trackNo；submitToPlatform 为文档化写入口；401/has_shipped 禁重放
- research 交叉引用已更新；`CONCEPTS.md` 增补 sellfox_shipping 词汇

## 2026-07-20 — 同事 20260720 蜴国际样例 + live 401

- 样例 3 文件：上传 xls / 跟踪号 xlsx / 面单 PDF（通途 P#，非赛狐 packageSn）
- 映射 3 票均为 has_shipped；本地 remapped import 3/3；赛狐 trackNo 仍占位/空
- live `submitToPlatform`（to_process `P2AMA9T726848`）→ 代理 HTTP 401；scope UNKNOWN_BLOCKED
- 研究笔记已更新：`docs/research/submit-to-platform-vs-autopush-2026-07-20.md`；session-progress §36

## 2026-07-20 — 本地 Excel 走查

- `scripts/excel_walkthrough_local.py`：导出→合成返回→导入；5/5 persisted（batch#3）

## 2026-07-20 — submitToPlatform vs 自动推送边界

- 研究：`docs/research/submit-to-platform-vs-autopush-2026-07-20.md`（通途写平台；自动推送关；trackNo 探针）
- PR 切片指南：`docs/research/pr-slice-guide-2026-07-20.md`

## 2026-07-20 — LizardApiShipmentService（create→poll→Artifact）

- `api_shipment.py`：可选 API 编排；Excel 仍默认；未挂 Web/CLI
- 测试：`test_lizard_api_shipment.py`

## 2026-07-20 — OIDC 公网就绪（默认仍关闭）

- 启用缺配置启动失败；HTTPS Secure cookie；JSON 401；写操作 actor=钉钉 identity
- 测试：`test_auth_oidc_gate.py`

## 2026-07-20 — S0143 映射 + reference_no=packageSn 适配层

- `order_adapter.py`：备案发件地址表 + `build_create_order_body`（Excel 仍默认）

## 2026-07-20 — 恢复 P1C + 钉死 getLabel/create 字段解析

- 从本地 `c489149` 恢复分支并 rebase main（含 `yiglobal-api` / `YIGLOBAL_*`）
- `parse_create_order_result` / `parse_get_label_result`：主路径 `result.labels.*`

## 2026-07-17 — 凭证迁入根 `.env`，冒烟脚本不再读文档密钥

- 本地：`VITE_*` / `YIGLOBAL_*` 写入仓库根 `.env`（gitignore）
- 模板：`sellfox_shipping/.env.example`；脚本仅 env

## 2026-07-17 — 蜴国际本仓 1 票真调（create/getLabel/cancel）

- 脚本：`scripts/lizard_api_create_cancel_smoke.py`；全程 code=200 / sync=1 / cancel Success
- 详见 session-progress §28

## 2026-07-17 — 蜴国际 httpx 薄客户端（mock）

- `LizardApiClient`：token/ratesv2/create/getLabel/cancel；同步 httpx（非为异步选型）
- Excel 仍生产默认；真调另确认

## 2026-07-17 — 蜴国际 PR#91：负余额 create/getLabel/cancel 已验

- main：`7e1ec1f`；更新 `lizard-api-vs-excel-2026-07-17.md`
- Excel 仍生产默认；可规划 httpx adapter；禁止拷贝明文凭证

## 2026-07-17 — OIDC 脚手架 + SQLite submit 跨进程限流

- `SqliteSubmitRateLimiter` + Alembic `0007`；CLI 真调默认使用
- `auth_oidc.py`：默认关闭；复用 api.vilavi.cn/oidc
- Karrio：重读 PR#88，维持 httpx 决策；蜴国际同事并行测下单（负余额）
- 详见 `docs/research/oidc-and-submit-rate-gate-2026-07-17.md`

## 2026-07-17 — VITE cancel 真测 + Karrio 决策提交

- `cancel_label`：DELETE 可用 orderId；create→OK→cancel 余额退回
- 决策文：`vite-httpx-vs-karrio-decision-2026-07-17.md`（采用 httpx）

## 2026-07-17 — VITE 决策：httpx，不做 Karrio custom connector

- 决策文：`docs/research/vite-httpx-vs-karrio-decision-2026-07-17.md`
- P1C VITE spike 技术退出门关闭；不切换通途

## 2026-07-17 — 异步面单 / Webhook 口径落档

- 用户：VITE API Hook URL 空；蜴国际有 webhook；本地部署
- 蜴国际 IT：getLabel 异步，建议 30s 轮询
- 新增 `docs/research/async-label-and-webhook-2026-07-17.md`

## 2026-07-17 — VITE 测试环境 createShipment + getLabel

- 1 票 GOFO_PX/PARCEL：创建 OK（pending→扣 $3.8）；getLabel 异步约 1–3 分钟后 OK
- 脚本：`scripts/vite_test_shipment_label_smoke.py`；轮询超时建议 ≥180s
- 详见 session-progress §21

## 2026-07-17 — VITE 测试环境 rate 真测

- 仅 test-api：account + rate2/gofo（三组合法 service/channel）；未打单
- 脚本：`scripts/vite_test_rate_smoke.py`；结果记入 session-progress §20

## 2026-07-17 — 限速对齐代理 + VITE httpx spike

- 用户澄清：官方赛狐 API ≤1 rps；共享代理 `api.vilavi.cn/sellfox` 现约 0.5 rps（可调）
- `config.yaml`：`submit_min_interval_seconds: 2.0`（对齐代理）；CLI 读取该值
- VITE：`carriers/vite/client.py` GOFO rate/shipment/label（mock 测试）；不替换通途；凭证仅 env

## 2026-07-17 — P1C：1 rps 限流 + packageDetail 回读 VERIFIED

- `submission_rate_limit.SubmitRateLimiter`（进程内；现默认对齐代理 2.0s）
- submit 成功后 `fetch_package_detail`；trackNo 匹配 → VERIFIED；失败/不匹配留 SUCCESS
- CLI：`packages-verify-intent`；测试 113 passed

## 2026-07-17 — 蜴国际 API PR#90 备忘 + Web 提交确认（dry-run）

- main：`蜴国际-API/`（PR #90）；对照 `docs/research/lizard-api-vs-excel-2026-07-17.md`
- 包裹详情：准备 Intent + dry-run；**不**从 Web 真调 submitToPlatform
- 仍保持 Excel 主路径（API 下单因欠费未验证）

## 2026-07-17 — P1C：SubmissionIntent + CAS（mock）

- Alembic `0006`：scopes / intents / attempts
- `submission_service.py`：prepare、CAS、UNKNOWN scope 阻断、IN_FLIGHT recover
- `sellfox_client.submit_to_platform(wire)` 新路径（`orderId`）
- CLI：`packages-prepare-submit`、`packages-submit-intent`（默认 dry-run）
- 测试 +106；**106 passed**；暂不提 PR

## 2026-07-17 — 进入 P1C：提交状态聚合 + 外部依赖备忘

- 用户确认：VITE 文档/测试已由同事验证，PR #88 / #89 合入 main（`vite-api/`）；暂不提本分支 PR
- 用户确认：蜴国际有 API、无测试环境，同事测试中
- 新增 `submission_state.aggregate_package_submission_state`（综合调研 §3.3 穷尽优先级）；**尚无** `submitToPlatform` 网络调用

## 2026-07-17 — ShippingBatch MVP + Artifact 扁平 private/files

### 代码

- Alembic `0005`：`shipping_batches` / `shipping_batch_packages`
- 导出创建批次；导入可带 `batch_id` 回写（`exported` → `tracking_imported`）
- Artifact 磁盘：`data/artifacts/private/files/{stem}_{hash8}{ext}`（**MD5** 去重，对齐 ERPNext File）
- Web：`/lizard/batches`、详情；导入可选批次 ID；CLI `--batch-id`
- 测试：`test_shipping_batch` + Web 批次页；全套 **72 passed**

### 操作员怎么用（摘要）

1. `serve --reload` → `/lizard/export` 导出（得 `batch_id`）
2. 人工上传蜴国际（费用风险）
3. `/lizard/import` 填同一 `batch_id` 导入返回表 → 本地落库 + 批次状态更新
4. `/lizard/artifacts` 看文件；`/lizard/batches` 看批次

详见 `docs/research/session-progress-2026-07-16.md` §13；EN 对照见 `artifact-vs-erpnext-file-2026-07-17.md`。

## 2026-07-17 — Artifact content_hash 改为 MD5（对齐 ERPNext）

- `register_artifact` / 导出 `file_md5`：`hashlib.md5`（32 hex）
- 旧本地 SHA-256 制品不自动迁移；测试库可清空 `data/artifacts/`
- 文档与制品页文案同步

## 2026-07-17 — Artifact 文件制品表（content_hash 去重）

- 表 `shipping_artifacts`（Alembic `0004`）；blob 现为 `private/files/…`（早期实现曾用 `by-hash/`）
- 同 content_hash 只存一份文件；多条记录可不同 `file_name` / `virtual_folder`（类比 ERPNext File）
- 导出上传表、导入追踪号均登记；Web：`/lizard/artifacts` 列表 + 下载
- **含系统生成文件**（export）与人工上传文件（import）

## 2026-07-17 — 文档：P1B 进度快照与 Artifact 说明

- 更新 `session-progress` §11：Web/补录/夹具提交列表、未做边界
- 澄清「导出批次 Artifact 表」= 登记导出/导入 Excel 的只读制品元数据（hash/模板版本等），非业务必须立即实现
- 同步 `AGENT_HANDOFF` 接手段（分支、64 passed、P1B 状态）

## 2026-07-17 — 缺 dims 人工补录

- 表 `shipping_carton_overrides`（Alembic `0003`）；按 commodity_sku 覆盖
- 查找链：本地补录 → pageList → ERPNext ZLMB
- 包裹详情页「重尺补录」表单；审计 `lizard.carton_override`
- 测试：`test_carton_override` + UI 保存

## 2026-07-17 — Web：蜴国际导出 / 导入对账页

- `/lizard/export`：导出 approved + 渠道含「蜴」→ 下载 xlsx（同 CLI `lizard-export`）
- `/lizard/import`：上传返回 Excel → 本地落库 + 对账报告（matched/persisted/conflicts/unmatched）
- **不**调用 `submitToPlatform`；导航已挂到首页/包裹页
- 测试：`tests/sellfox_shipping/test_lizard_web.py`

## 2026-07-17 — PDF 面单通途→赛狐替换（夹具 04）

- Claude：`pymupdf` 替换 38 页 `CUST REF`/`Ref No`；写入 `sellfox-native-fixture/04-*.pdf`
- 文档：`pnumber-to-sellfox-trace` §6；夹具总览同步含 04
- 可提交脚本：`scripts/replace_tongtu_refs_in_labels.py`（`数据源/` 下入口 gitignore，仅转调）
- 样例 PDF/输出 PDF **不入 git**

## 2026-07-17 — 赛狐原生蜴国际测试夹具 + 本地导入实测

- 子目录 `数据源/…/sellfox-native-fixture/`（gitignore）：02/03 按 packageSn 重建；后补 04 面单
- 脚本：`scripts/rebuild_sellfox_lizard_fixtures.py`；说明见 `docs/research/sellfox-native-lizard-fixture-2026-07-17.md`
- 修正 P81401195 Amazon 尾号 `…0563432`
- 导入落库：`tracking_number == package_sn` 视为占位可覆盖；补同步 7 个 `P2AJA9T…` 后 smoke：**38/38** persisted，conflicts=0；未调用 submitToPlatform

## 2026-07-17 — 状态澄清 + 通途 P 号追溯文档

- 新增 `local-vs-sellfox-status`：本地通过/驳回不改赛狐；导出数据来自 API 汇总
- 收录并脱敏 `pnumber-to-sellfox-trace`（38/38；文档内禁止写密钥）

## 2026-07-17 — ERPNext ZLMB 重尺兜底接入

- `CascadingDimsLookup`：赛狐 pageList → ERPNext `ZLMB#{前3段}` Item
- 字段优先级：国外成品 → 绍兴工厂；实测 KS0002-DL-194 → 4.1kg / 58×19×45
- 凭证读 `EN_API/.env`（`ERP_API_KEY`/`ERP_API_SECRET`）；修正 Lesson 17 字段名为 `*_length/width/height`
- 测试 54 passed

## 2026-07-17 — P1B 蜴国际 Excel 导出/导入骨架

- `carriers/lizard/`：上传表构建、追踪号返回解析、commodity pageList 重尺查找
- Service：`ExportLizardUploadService` / `ImportLizardTrackingService`（对账报告 + AuditEvent）
- CLI：`lizard-export`、`lizard-import-tracking`
- 缺 carton dims 的包裹计入 skipped，不静默导出空重尺；ERPNext 兜底另开
- 测试：`test_lizard_spreadsheet` + `test_lizard_batch`；全量 sellfox_shipping 通过

## 2026-07-17 — 重尺来自商品 pageList（非包裹）

- 包裹 API 确无重尺；`/api/commodity/pageList.json` + `skus` + `isGroup=0` 返回 cartonWeight/LWH
- 试转换重生成：8/10 有值；KS0002-DL-194-* carton 为 0
- 文档：`docs/research/sellfox-carton-dims-source-2026-07-17.md`；发货编码暂固定 S0143

## 2026-07-17 — 赛狐→蜴国际试转换 + Colab 遗产

- 确认：参考编号=赛狐 `packageSn`（`P2A…`）；P0 样例 `P8140…` 为通途号
- 试生成 `trial-sellfox-to-lizard-upload-10.xlsx`（重量空：API 无 packageWeight）
- Colab notebook 摘要：`docs/research/colab-notebook-legacy-summary-2026-07-17.md`（notebook 主做背贴，不生成上传表）

## 2026-07-17 — 蜴国际 P0 样例列映射

- 样例已入 `数据源/蜥蜴国际-p0-样例/`（gitignore）；① 仅表头无数据，②③④ 为同事 B 同批往返
- 分析结论：`docs/research/lizard-p0-column-mapping-2026-07-17.md`
- 匹配键 `参考编号/Reference Code`；追踪号 `物流单号`；上传重量为克、返回为 kg

## 2026-07-17 — 本地包裹审核写操作

- 新增 `local_review_status`（pending/approved/rejected）与 Alembic `0002`
- `POST /api/packages/{sn}/review` + 详情页表单；同步不覆盖本地审核状态
- 审核写入 `packages.review` AuditEvent；列表可按本地审核筛选
- 测试 44 passed

## 2026-07-17 — serve 不依赖 fastmcp

- `main.py` 将 FastMCP 改为可选挂载；未安装时仍可启动 Web/REST
- `serve` 关闭 reload、使用 `log_level=info`；无 fastmcp 时提示 MCP disabled
- 实测：`uv run python -m sellfox_shipping.cli serve` 后 `GET /packages` → 200
- 测试：`test_serve_without_fastmcp.py`；全量 36 passed

## 2026-07-16 — P1A Alembic schema migration

- 新增 `schema.upgrade_schema()` + Alembic `0001_package_schema`
- `PackageRepository` 启动改为跑 migration，不再裸 `create_all`
- 已有 create_all 库无 `alembic_version` 时 stamp head，避免重复建表失败
- 依赖增加 `alembic`；测试 34 passed

## 2026-07-16 — P1A 包裹审核 Jinja 页

- 新增 server-rendered `/packages` 与 `/packages/{package_sn}`，共用 ListPackagesService / PackageRepository
- 修正 Starlette 1.2 `TemplateResponse(request, name, context)` 签名（旧写法触发 Jinja LRUCache TypeError）
- 导航加入「包裹」入口；legacy 订单页标注
- 测试：`uv run pytest tests/sellfox_shipping -q` → 32 passed

## 2026-07-16 — P1A 包裹 REST 只读接口

- 新增 `GET /api/packages` 与 `GET /api/packages/{package_sn}`，共用 `ListPackagesService` / `PackageRepository`
- 新增 3 个 FastAPI 定向测试；`uv run pytest tests/sellfox_shipping -q` → 29 passed

## 2026-07-16 — P1A 包裹查询与同步审计

- 新增 `packages-list` CLI：按账户 / 状态 / 渠道过滤本地包裹摘要（`order_count` / `item_count`）
- 新增 `shipping_audit_events` 表；`packages.sync` 结束（含 `partial_failed`）写入 `AuditEvent`（actor + 计数摘要）
- 明确并行边界：同事 Agent 调研 VITE/Karrio 未提交前，本分支不扩展 VITE spike / Karrio connector
- 测试：`uv run pytest tests/sellfox_shipping -q` → 26 passed

## 2026-07-16 — 会话进度交接文档

- 新增 `docs/research/session-progress-2026-07-16.md`：完整记录独立调研落地、命名边界、P1A TDD 实现、审查修复、提交哈希、未完成项与勿踩坑
- 更新 `research/index.md`、`docs/index.md`、`AGENT_HANDOFF.md`：区分「接手继续实现」与「从零独立再调研」阅读顺序
- 目的：新开对话或其它软件 Agent 可从会话进度文档无缝续作，无需依赖聊天上下文

## 2026-07-16 — P1A 包裹只读同步纵切

- 新增内部 snake_case 包裹模型；赛狐 camelCase 仅在 gateway 边界解析
- 修复 Sellfox proxy 动态 account 路径和 Bearer 认证头
- 新增 SQLAlchemy package repository，启用 SQLite WAL、foreign keys、busy timeout，并按账户保存包裹—订单多对多关系
- 新增 `SyncPackagesService`：按实际返回行分页，输出逐行对账；中途 gateway 失败保留已处理结果并返回 `partial_failed`
- 新增 `packages-sync` JSON CLI；要求 actor，部分失败输出报告后返回非零退出码
- 新增 21 个定向测试；当前纵切不调用 `submitToPlatform`，不表示 P1A/P1B 全部完成

## 2026-07-16 — 独立综合调研与导航

- 新增独立综合调研，形成以内部 `(sellfox_account_id, package_sn)` 为包裹业务键、以包裹批次为主线的架构判断
- 将 P1 规划为双轨验证：蜴国际 Excel 完整闭环，以及 VITE 测试环境下 Karrio custom connector 与直接 API 适配器的技术对比
- 补齐 `research/index.md`，将独立综合文档设为当前推荐规划入口，并保留旧调研作来源对照
- 为既有 research 文档补齐或规范化 OKF frontmatter，统一使用 `Reference` / `Research` 类型
- 明确 Python 内部统一 snake_case，第三方 camelCase 仅保留在 adapter/gateway wire payload 边界
- 明确一包多单提交意图、逐订单尝试与包裹级聚合状态（仅规划，尚未实现）
- 本条仅记录调研结论与规划更新，不表示相关代码已经实现

## 2026-07-15 — P1 骨架搭建

- 创建项目结构: models, store, sellfox_client, carriers/base
- FastAPI REST API + 基础 Web UI (index + orders 页)
- FastMCP tools: list_orders, get_order, get_order_shipping_info, fetch_orders_from_sellfox, get_carrier_info, list_available_carriers
- Typer CLI: fetch, orders, status, carriers, rules, serve
- Dockerfile + docker-compose.yml
- config.yaml 含仓库、承运人、规则模板
- OKF 文档框架
- ce-compound: 完整调研文档写入 docs/solutions/architecture-patterns/ 和 docs/research/
