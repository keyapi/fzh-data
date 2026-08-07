---
okf: v0.1
type: Handoff
title: sellfox_shipping — Agent 交接说明
description: 包裹中心架构、当前实现、运行方式与后续阶段边界
updated: 2026-08-06
---

# sellfox_shipping — Agent 交接说明

> **赛狐尾程打单系统** — 包裹批次工作流  
> 人读文档: [README.md](README.md)  
> **新 Agent：只读本文件即可接手。** 细节经 [docs/index.md](docs/index.md) 按需深挖。  
> 生产化开发先读：[生产可靠性蓝图](docs/specs/production-reliability-blueprint-2026-08-04.md) → [路线图](docs/roadmap.md)。
> 过程日记 / 规划底稿（非默认入口）：[session-progress](docs/research/session-progress-2026-07-16.md)、[research-synthesis](docs/research/research-synthesis-2026-07-16.md)

## 新对话 / 换 Agent 接手（30 秒）

1. 读完本文件（全貌七块 + 禁区 + 命令）
2. 跑验证：`uv run pytest tests/sellfox_shipping -q`
3. 需要细节时经 [docs/index.md](docs/index.md) 点进单篇

**不要**默认先读 session-progress / synthesis。

## 全貌七块

### 1. 背景 / 现行目的

Excel 本地闭环（审核 → 导出 → 人工上传物流商 → 导入对账）+ **通途写销售平台**；赛狐**自动推送关**。  
近期产品目标：验证赛狐包裹详情能否显示正确 `trackNo`（非默认推 Amazon）。

### 2. 阶段图

`P0 → P1A → P1B → P1C → P2+`  
代码主路径已合入 main（PR **#96** 集成、**#97** 文档/边界）。  
**产品** trackNo 可见性闭环**未关**（live submit 曾 401）。

### 3. 已完成

- 同步 / 审核 / 蜴国际 Excel 导出·导入 / Artifact·Batch / Intent·CAS·限流
- OIDC 启用路径就绪（**默认关**）
- 蜴国际 API 客户端 + 可选编排（**Excel 仍生产默认**）
- VITE httpx spike + 决策（不做 Karrio VITE connector）
- 边界文档：submit vs 通途/自动推送；trackNo 写路径 solutions

### 4. 波折

- live `submitToPlatform`（`P2AMA9T726848`）→ 代理 **401**；scope `UNKNOWN_BLOCKED`；赛狐 `trackNo` 未变
- **禁盲重放**；本地 `lizard-import` ≠ 赛狐 UI `trackNo`

### 5. 教训（深挖）

- [submit-to-platform-vs-autopush-2026-07-20.md](docs/research/submit-to-platform-vs-autopush-2026-07-20.md)
- [sellfox-trackno-write-path-vs-local-import.md](../docs/solutions/architecture-patterns/sellfox-trackno-write-path-vs-local-import.md)

### 6. 下一步（≤3）

> **已完成 1a) 购标安全原语 (PR [#134](https://github.com/keyapi/fzh-data/pull/134))** — claim / preflight / migration 0015 / UNKNOWN_BLOCKED
> **已完成 1b) 购标安全接线 + 恢复持久化 (PR [#135](https://github.com/keyapi/fzh-data/pull/135))**
> - `create_label()`：preflight → claim → SENT → carrier
> - 承运商适配层拿到 `order_id`/`order_code` 后立即 `SENT → ACCEPTED`（落 `provider_order_id`）
> - poll/PDF/artifact 失败 → `LABEL_PENDING`（保留 provider ID + tracking）；create 只调一次
> - 取消：`ACCEPTED/LABEL_PENDING/SUCCEEDED → CANCELLED`；崩溃窗口 `SENT + 已关联 label` 可释放；transition 失败不得静默成功
> - Vite 购标与报价路径删除虚构地址兜底
> **已完成 1c) Operation CLI + carrier error taxonomy + resume + resolve (PR [#137](https://github.com/keyapi/fzh-data/pull/137), [#142](https://github.com/keyapi/fzh-data/pull/142))**
> - `label-operations-list/show` 只读控制面
> - carrier error taxonomy（Vite/Lizard 错误分类）
> - `label-operation-resume`：带 provider ID 的恢复（仅 getLabel/PDF/artifact，禁止 create）
> - `label-operation-resolve`：UNKNOWN_BLOCKED 人工结案（fail_safe / fail_final / provide_known_id）
> **已完成 1d) 赛狐下单时间 + 有效面单时间 + 分页 (PR [#141](https://github.com/keyapi/fzh-data/pull/141))**
> - 包裹列表新增"赛狐下单时间"和"有效面单时间"列
> - Dashboard / Transactions 双标签页分页
> **已完成 1e) 分页 count 修复 (PR A)**
> - `count_packages()` 改用 `count(distinct package_id)`，修复多订单、多标签场景下总数放大
> - 新增 9 个 repository 测试覆盖多订单/多标签/日期边界/分页语义一致性
> - 浏览器验证通过：分页切换、标签页重置、日期类型切换
> **已完成 1f) resume 并发与幂等收口 (PR B)**
> - Migration 0016: `shipping_label_operations` 新增 `claimed_by`/`claimed_at`
> - `acquire_resume_lease()` / `release_resume_lease()` — SQLite 原子 lease
> - SUCCEEDED 操作 idempotent 返回既有结果
> - `label-operation-resume` 和 `label-operation-resolve` 增加必填 `--actor`
> **已完成 1g) UNKNOWN_BLOCKED 证据化结案 (PR C)**
> - Migration 0017: 新增 `shipping_label_investigations` append-only 表
> - `add_investigation()` — 仅记录调查，不解除阻断
> - `resolve_unknown_blocked()` 增加必填 `evidence_id`，验证归属
> - 新增 CLI `label-operation-investigate`（evidence_type: ticket/carrier_portal/email/other）
> - `label-operation-resolve` 增加必填 `--evidence-id`
> **PR #143 复审修复：lease fencing + 权威证据约束**
> - Migration 0018 增加 `claim_token`、investigation `conclusion` 和 operation `resolution_evidence_id`
> - resume claim 使用 SQLite `BEGIN IMMEDIATE`；只有持有同一 token 的 worker 可以释放 lease
> - `label-operation-investigate` 必填 `--conclusion`：`confirmed_not_created` / `confirmed_created` / `confirmed_rejected`
> - `confirmed_created` 必须同时传 `--provider-order-id`，结案时与 CLI 输入严格匹配
> - `fail_safe`、`provide_known_id`、`fail_final` 分别只接受对应 conclusion
> - 结案证据必须有外部引用或私有 artifact；`other` 类型不能直接作为权威结案证据
> - 结案事务持久化 `resolution_evidence_id`，审计事件同时记录 evidence ID
>
> **当前接手裁决（2026-08-05）：**
> 1. 先合入并验证 Migration 0019：修复历史 SQLite 库连续升级失败及半应用 0018 缺失外键。
> 2. Jack Agent 第一阶段只做生产验收与缺口复核，按 [生产验收与交接规范](docs/specs/production-acceptance-and-jack-handoff-2026-08-05.md) 输出 readiness matrix。
> 3. 赛狐 outbox 已完成 PR 1 候选层与 PR 2 执行器/回读；真实发送前必须读 [Outbox 设计](docs/specs/sellfox-writeback-outbox-2026-08-06.md) 与 [单包能力探针运行手册](docs/specs/sellfox-writeback-probe-runbook-2026-08-06.md)，默认保持 DISABLED + UNVERIFIED。
> 4. 赛狐 outbox PR 2 已实现：confirm/run-once/verify/policy/capability CLI、`BEGIN IMMEDIATE` 租约、`IN_FLIGHT` 崩溃阻断与 packageDetail 回读均完成；全部测试 mock，未真实调用赛狐。
> 5. 公网部署前仍需 OIDC/CSRF/RBAC、secure cookie 与 PII/log 脱敏审计。
> 6. 当前自动化基线为 **260 passed, 2 warnings**；仍不等于承运商沙箱或生产业务验收完成。

> **2026-08-07 新对话接手补充：**
> - **当前分支/PR**：`fix/sellfox-submit-quantity-errorbody` → **PR #158**（本次全部改动已提交：quickOutbound 写回、蜴国际发货地址按仓库推导、4xx=FAILED、scope unblock、quantity string、ca_zone CENTRADE=0）。PR #153/#154/#155 未合并（内容已被 #158 覆盖部分）。
> - **本次完整问题记录**：先读 [docs/solutions/sellfox-writeback-label-address-2026-08-07.md](docs/solutions/sellfox-writeback-label-address-2026-08-07.md)。
> - **优先任务（新对话第一步）**：
>   1. 同步 8 月包裹（`packages-sync --date-start 2026-08-01 --date-end <今天> --actor cli`）。
>   2. **修复蜴国际面单打印发货地址错误**：实测蜴国际可能忽略 createOrder 的 `shipper_address`，改用其账户/产品（FedEx-Ground-J-TX）配置地址（Missouri City TX）。美东正确地址已写入 config `warehouses.CENTRADE`（Overstock.com, Centrade Inc / 389 Route 10 Unit R, East Hanover NJ 07936 / 7327622442）。需与蜴国际确认 `shipper_address` 是否生效、是否有 NJ 产品/账户配置。
>   3. 与赛狐确认正确写回 API（submitToPlatform/quickOutbound 均被拒"不需要提交平台"；候选 `applyTrackNo` 物流下单发货）。
> - 测试基线：**293 passed**。
> - 凭证/服务器/同步步骤沿用文首「快速启动」。

### 7. 重规划裁决

- **不**整本作废 synthesis；修订 P1C 出口与承运人双通道（见 synthesis 文首裁决框）
- **承运人双通道：** `SpreadsheetCarrierAdapter` 与 `ApiCarrierAdapter` 同等级；同一承运人可两者皆有；**生产默认 Excel**；有 API 另挂可选路径（蜴国际 API 已有，不替表）
- 平台推送非本阶段默认；Intent/CLI 真调路径保留备用
- 当前规模先强化 SQLite；出现持续写竞争或多实例恢复需求时再迁 PostgreSQL
- 暂不采用 Karrio Server；约 5 个 API 承运商或至少两个标准 connector 可复用时再做独立服务 POC
- 装箱算法延期，本阶段不改变现有尺寸公式

## 禁区

- 不盲重放 `submitToPlatform`；真调须用户确认测试包裹
- 不把 legacy `store.py` 订单模型当生产闭环
- 不从文档/HANDOFF 拷明文 API Key
- 赛狐导入/回写前必须确认范围（默认测试商品）

## 架构

```
Sellfox gateway (wire camelCase → internal snake_case)
    → SyncPackagesService（分页、逐行报告、部分失败报告）
    → PackageRepository（SQLAlchemy + SQLite WAL）
    → Typer JSON CLI
```

Legacy Web/MCP/订单接口仍保留，但尚未迁移到新 Service Layer。不要把 legacy skeleton 当作生产闭环，也不要在 `store.py` 订单模型上堆蜴国际流程。

## 快速启动

```bash
# 测试
uv run pytest tests/sellfox_shipping -q

# P1A：包裹只读同步（需要 SELLFOX_PROXY_API_KEY；不调用 submitToPlatform）
uv run python -m sellfox_shipping.cli packages-sync \
  --date-start 2026-07-15 --date-end 2026-07-16 \
  --actor <operator-id> --json

# 本地包裹列表（只读本地库）
uv run python -m sellfox_shipping.cli packages-list --status to_audit --json

# 购标 operation 只读控制面（无承运商 HTTP）
uv run python -m sellfox_shipping.cli label-operations-list \
  --status UNKNOWN_BLOCKED --carrier vite --json
uv run python -m sellfox_shipping.cli label-operation-show \
  --operation-id <N> --json

# P1B：蜴国际上传 Excel（仅 local_review=approved 且渠道含「蜴」；重尺走 commodity pageList）
uv run python -m sellfox_shipping.cli lizard-export -o out/lizard-upload.xlsx --actor <operator-id> --json

# P1B：解析蜴国际返回追踪号 Excel（按 package_sn 对账；生成本地 Outbox 候选，尚未回写赛狐）
# 可选 --batch-id：回写对应 ShippingBatch
uv run python -m sellfox_shipping.cli lizard-import-tracking \
  -i path/to/return.xlsx --actor <operator-id> --batch-id <N> --json

# Outbox 候选控制面（全部无赛狐 HTTP）
uv run python -m sellfox_shipping.cli sellfox-outbox-list --json
uv run python -m sellfox_shipping.cli sellfox-outbox-show --outbox-id <N> --json
uv run python -m sellfox_shipping.cli sellfox-outbox-scan-candidates \
  --account-key sellfox-main --package-sn <SN> --json

# Outbox PR 2：确认单个候选（构建/复用 SubmissionIntent，无 HTTP）
uv run python -m sellfox_shipping.cli sellfox-outbox-confirm \
  --outbox-id <N> --actor <operator-id> --json

# Outbox PR 2：dry-run 预览（无 HTTP、不领取 lease）
uv run python -m sellfox_shipping.cli sellfox-outbox-run-once \
  --outbox-id <N> --actor <operator-id> --json

# Outbox PR 2：真实单包探针（需 PROBE_ONLY + 用户授权测试包裹）
uv run python -m sellfox_shipping.cli sellfox-outbox-run-once \
  --outbox-id <N> --actor <operator-id> --no-dry-run \
  --i-understand-side-effects --limit 1 --json

# Outbox PR 2：仅回读核验 VERIFY_PENDING（不重新 submit）
uv run python -m sellfox_shipping.cli sellfox-outbox-verify \
  --outbox-id <N> --actor <operator-id> --json

# Outbox PR 2：Policy 与能力证据
uv run python -m sellfox_shipping.cli sellfox-outbox-policy-show --account-key sellfox-main --json
uv run python -m sellfox_shipping.cli sellfox-outbox-capability-record \
  --account-key sellfox-main --capability-status SAFE_TRACKNO_ONLY \
  --evidence-ref <ref> --actor <approver> --json

# P1C：准备 submitToPlatform intents（无 HTTP）
uv run python -m sellfox_shipping.cli packages-prepare-submit \
  --package-sn <packageSn> --actor <operator-id> --json

# P1C：提交单个 intent（默认 dry-run）
uv run python -m sellfox_shipping.cli packages-submit-intent \
  --intent-id <N> --actor <operator-id> --json

# P1C：SUCCESS → VERIFIED（仅 packageDetail 回读，不重新 submit）
uv run python -m sellfox_shipping.cli packages-verify-intent \
  --intent-id <N> --actor <operator-id> --json

# Web Server（FastAPI；本地开发请加 --reload）
uv run python -m sellfox_shipping.cli serve --host 127.0.0.1 --port 8401 --reload
# 打开 http://127.0.0.1:8401/packages
# 导出：http://127.0.0.1:8401/lizard/export
# 导入对账：http://127.0.0.1:8401/lizard/import
# 文件制品：http://127.0.0.1:8401/lizard/artifacts
# 打单批次：http://127.0.0.1:8401/lizard/batches

# Legacy 订单 CLI（勿作为主流程扩展）
uv run python -m sellfox_shipping.cli fetch --date-start 2026-07-01 --date-end 2026-07-15
uv run python -m sellfox_shipping.cli orders --status to_print --json
```

## 项目结构

```
sellfox_shipping/
├── main.py               # 入口：FastAPI + FastMCP 组装（legacy）
├── app.py                # FastAPI app（legacy REST + Web UI）
├── mcp_tools.py          # FastMCP（legacy；根 uv 环境无 fastmcp，Docker 另装）
├── cli.py                # Typer CLI；packages-sync / lizard-export / lizard-import-tracking
├── lizard_batch.py       # P1B 导出/导入 Service ★
├── models.py             # Legacy 订单中心 Pydantic 模型
├── store.py              # Legacy sqlite3 订单库
├── sellfox_client.py     # 赛狐 gateway：Bearer、动态 account、包裹解析
├── package_models.py     # 包裹领域模型（内部 snake_case）★
├── package_repository.py # SQLAlchemy 多对多持久化 ★
├── package_service.py    # 包裹分页同步与数量对账 ★
├── outbox_service.py     # 赛狐回写 Outbox 确认/租约/执行/回读 ★
├── config.yaml           # proxy、仓库、承运人配置
├── carriers/lizard/      # 蜴国际 Excel 模板与重尺查找 ★
├── carriers/             # 其它承运人抽象（尚未接闭环）
├── templates/            # Web UI (Jinja2)
├── docs/
│   ├── index.md
│   ├── log.md
│   └── research/
│       ├── research-synthesis-2026-07-16.md   # 规划
│       └── session-progress-2026-07-16.md     # 冷档案
└── Dockerfile
```

`★` = 2026-07-16 P1A 纵切新增/主路径。

## 命名边界（强制）

| 层 | 规则 |
|----|------|
| Python / DB / 内部 JSON | `snake_case`（`package_sn`, `channel_name`, `tracking_number`） |
| 类名 | `PascalCase` |
| 赛狐 / VITE wire | 官方 camelCase，仅在 gateway 出现（`packageSn`, `trackNo`） |
| 转换 | adapter / Pydantic alias；request hash 用内部 snake_case canonical DTO |

详见综合文档 §2.5。

## 当前阶段：P1A 第一条纵切（已提交）

**已实现**

- 代理 `Authorization: Bearer` + `/v1/{proxy_account}/...`
- 包裹列表解析，保留全部 `orders[]` / `items[]`（一包多单）
- 唯一键 `(account_id, package_sn)`；订单/包裹多对多
- SQLite WAL + foreign_keys + busy_timeout；并发 upsert 用 ON CONFLICT
- `SyncPackagesService`：按实际行数分页；`input = success+skipped+failed+unmatched`
- `partial_failed`：中途失败保留已落库结果 + 报告；CLI 退出码 1
- `packages-sync` JSON CLI（强制非空 `actor`）
- `packages-list`：本地包裹摘要查询（状态/渠道过滤）
- `shipping_audit_events`：同步结束写 `packages.sync` 审计（含部分失败）
- REST：`GET /api/packages`、`GET /api/packages/{package_sn}`、`POST /api/packages/{package_sn}/review`
- Web：`/packages` 审核；`/lizard/export` 下载上传表；`/lizard/import` 追踪号导入 + 对账报告（**仅本地**）
- P1B：`lizard-export` / `lizard-import-tracking` CLI；重尺 pageList → ERPNext ZLMB；导入可覆盖 `trackNo==packageSn` 占位
- Schema：Alembic `0001` … `0006_submission_intents`

**已验证：** `uv run pytest tests/sellfox_shipping -q`

**未默认调用：** `submitToPlatform`（CLI 默认 dry-run）  

**live 探针（2026-07-20）：** `P2AMA9T726848` intent#1 真调 → 代理 **401**；scope `UNKNOWN_BLOCKED`；赛狐 `trackNo` 未变。填号结论待修写权限后再测。

**未实现：** 公网实际打开 OIDC、成功的 live 填号、VITE 同构编排挂界面；Excel 仍生产默认；**默认不推销售平台**（通途写平台 + 自动推送关）

**已落地（本切片）：** SQLite submit gate；OIDC 启用路径就绪（默认关）；`order_adapter` + `LizardApiShipmentService`；submit vs 自动推送边界文档；20260720 通途样例映射 + 本地 import。
**VITE：** 生产环境 GOFO + FedEx rate/create/shipment/label；决策采用 httpx。FedEx channel=ODFC，22" 阈值自动切换 GOFO/FedEx。  
**蜴国际：** PR#91 已验下单链路；本仓 `LizardApiClient`（httpx 同步，mock）；ratesv2 报价已集成，Excel 仍生产默认。勿从 main HANDOFF 拷明文 Key。

## 报价引擎 (新增)

| 功能 | 说明 |
|------|------|
| VITE 询价 | 最长边 ≤22" GOFO(GFUS), >22" FedEx(ODFC)；生产环境已验 |
| 蜴国际询价 | ratesv2 全部产品，S0143 发件，ca_zone=1(美东) |
| 历史报价 | `shipping_package_rates` 表，VITE + 蜴国际共用，按需获取 |
| 手动触发 | 点击按钮 → POST `/fetch-rates`，避免每次页面加载拉取 API |
| 原始响应 | `raw_data` 列存储完整 API 返回 JSON（indent=2 格式化，暗色代码块可展开） |
| 地址类型 | `address_type` 列存储 `address_type_text`（Residential/Commercial），与 Zone 分离 |
| CLI | `packages-rate-history --package-sn X --json` |
| 数据库 | `0010_package_rates` → `0011_package_rates_raw` → `0012_package_rates_address_type` |

### 数据流

```
包裹详情页（初始加载：仅路由建议 + 历史，不调 API）
  → 用户点击「获取 VITE + 蜴国际 报价」
  → POST /packages/{sn}/fetch-rates
  → _get_vite_rate()               # VITE GOFO/FedEx
  → _get_lizard_rate()             # 蜴国际 ratesv2（静默持久化）
  → _persist_rate(raw_response=…)  # 写入 shipping_package_rates（含 raw_data）
  → 刷新页面
  → 运费试算面板（路由建议承运商）
  → 历史报价面板（VITE + 蜴国际 混合，点击展开 JSON）
```

## 问题记录

| 问题 | 修复 |
|------|------|
| EN_API/.env 缺失 → EN ZLMB 重尺全返回"缺失" | 从 `D:\Claude Demo\fzh-data\EN_API\.env` 复制到 worktree |
| FedEx ODFC 测试环境 403 | 切换生产环境 + prod API key |
| 上海时间显示为 UTC | `_rate_row_to_record` 引用 `row.fetched_at` 而非转换后的局部变量 |
| address2 字段名不匹配 | Pydantic 模型用 `address_line_2`，不是 `address2` |
| 国际地址 state 为空 → API 400 | `_build_vite_ship_to` city 前 2 字符兜底 |

## 待实现

| 阶段 | 内容 | 依赖 |
|------|------|------|
| P1A 后续 | OIDC；legacy 入口隔离 | 钉钉 OIDC 配置 |
| P1B 收尾 | ~~Artifact~~ / ~~ShippingBatch MVP~~（`0004`+`0005`；`/lizard/artifacts`、`/lizard/batches`） | — |
| P1C | Intent/CAS + Web dry-run + 可配置限流 + 回读 VERIFIED + **VITE httpx（决策关闭）** | 真调须确认测试包裹；通途生产不动 |
| P2+ | PDF/packlist、GLS Excel、经验证的 API connector | 各承运人资料 |

详细决策与暂不做边界见综合调研文档。过程细节见 [session-progress](docs/research/session-progress-2026-07-16.md)。

## 数据流（现行主路径）

```
赛狐订单处理 API getPackagePage
    → sellfox-api-proxy（Bearer + account）
    → SellfoxClient.fetch_package_page()
    → SyncPackagesService.sync()
    → PackageRepository.upsert()
    → JSON reconciliation report
```

## 凭证

| 项目 | 来源 |
|------|------|
| 赛狐 API | 环境变量 `SELLFOX_PROXY_API_KEY`，经 sellfox-api-proxy |
| 蜴国际 API | 根目录 `.env`：`YIGLOBAL_APP_TOKEN` / `YIGLOBAL_APP_KEY`（见 [`.env.example`](.env.example)；模块文档在 `yiglobal-api/`） |
| VITE 测试 | 根目录 `.env`：`VITE_API_KEY` / `VITE_API_BASE_URL`（变量名跨环境一致，只换值） |
| GLS/FedEx | 后续验证，不在当前纵切 |

真调前：复制 [`.env.example`](.env.example) 键到仓库根 `.env`（gitignore）。冒烟脚本**只**读 env，不再从 Markdown 取密钥。禁止把真实 Key 写入仓库或文档。赛狐导入/回写前必须用户确认范围。
