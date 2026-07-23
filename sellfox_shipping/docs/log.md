---
okf: v0.1
type: Log
module: sellfox_shipping
created: 2026-07-15
updated: 2026-07-22
---

# sellfox_shipping — 变更日志

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
