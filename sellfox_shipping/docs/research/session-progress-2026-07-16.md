---
okf: v0.1
type: Reference
title: 2026-07-16 会话进度与交接记录
description: 独立调研规划落地与 P1A 包裹只读同步纵切的完整过程、提交、验证与下一步，供新对话或其它 Agent 接手
timestamp: 2026-07-16
tags: [sellfox-shipping, handoff, session-progress, p1a]
---

# 2026-07-16 会话进度与交接记录

> **给新对话 / 其它软件 Agent：** 先读本文，再读 [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) 与 [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)。  
> 本文记录**已发生的工作过程与决策**；综合调研文档记录**目标架构与阶段规划**；二者不要混读。

## 1. 会话目标与结果

| 目标 | 结果 |
|------|------|
| 独立形成尾程打单规划（非拼接 Agent A/B/C） | 已写入 `research-synthesis-2026-07-16.md` |
| 澄清命名：Python snake_case vs 外部 camelCase | 已写入综合文档 §2.5，并贯穿实现 |
| Git 提交调研文档 | 提交 `27cd46d` |
| 按规划开始实际构建 | 完成 **P1A 第一条纵切**（包裹只读同步），提交 `0b157e7` |
| 调用赛狐 `submitToPlatform` / 蜴国际 Excel / 钉钉 OIDC | **未做**（有意延后） |

**分支：** `research/claude-strange-jones`  
**规划入口：** [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md)  
**代码入口：** [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)

## 2. 阅读顺序（新 Agent）

1. 本文 — 知道做到哪、下一步是什么、不要踩的坑  
2. [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) — 架构、阶段、安全回写、Karrio/VITE 判断  
3. [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) — 当前代码结构与命令  
4. 需要时再读：`briefing-for-independent-agent.md`（较早背景）、`comprehensive-research-2026-07-15.md`（旧调研对照）

不要把 `AGENT_HANDOFF` 旧版「P1 骨架完成 / P2 FedEx」当作现行阶段；综合文档已重新定义 **P0 / P1A / P1B / P1C / P2+**，旧骨架称 **legacy skeleton**。

## 3. 工作过程时间线

### 3.1 调研与规划（文档）

1. 对照三家 research 分支后，按用户要求**独立判断**，产出综合调研。  
2. 业务澄清要点（详见综合文档附录 A「需求澄清决策记录」）：  
   - P1 试点：**蜴国际 Excel**（无 API）  
   - 闭环：赛狐拉包裹 → 审核 → Excel 导出 → 人工上传 → 追踪号导入 → 对账 → 人工确认 → `submitToPlatform` → 回读  
   - 一单多包 / 一包多单都可能；禁止按行序/页序匹配  
   - P1 读赛狐 `channelName`；本地规则引擎只留扩展点  
   - VITE：通途生产不动；P1 仅测试环境技术验证  
   - Karrio：**不用 Server**；无现成 VITE/GOFO connector；可选 SDK/custom connector 实验  
   - 部署：1–5 人、共享单机、钉钉 OIDC  
3. OKF：新建 `research/index.md`，更新模块 `docs/index.md`、`docs/log.md`，同步根 `index.md`。  
4. 命名修正后提交调研：`27cd46d docs(sellfox-shipping): 固化独立调研与分阶段架构`。

### 3.2 命名边界（实现前已固化）

| 层 | 规则 | 示例 |
|----|------|------|
| Python 类 / 枚举 | PascalCase | `SubmissionIntent`, `PackageStatus` |
| Python 属性 / DB 列 / REST·CLI JSON | snake_case | `package_sn`, `channel_name`, `tracking_number` |
| 外部 wire payload | 保留官方 camelCase | `packageSn`, `channelName`, `trackNo`, `orderId` |
| 映射 | gateway / Pydantic alias | `package_sn = Field(alias="packageSn")` |

核心对应：`package_sn ↔ packageSn`，`channel_name ↔ channelName`，`order_id ↔ orderId`，`tracking_number ↔ trackNo`。  
**不要**把赛狐驼峰字段扩散进 Service Layer 或数据库。

### 3.3 P1A 实现（代码，TDD）

因缺少蜴国际真实样例，本会话只做**不依赖样例**的 P1A 纵切：

```
赛狐 getPackagePage
  → SellfoxClient（Bearer + /v1/{account}/...）
  → parse_sellfox_package（camelCase → snake_case，保留全部 orders/items）
  → SyncPackagesService（分页、逐行对账、partial_failed）
  → PackageRepository（SQLAlchemy + SQLite WAL）
  → CLI packages-sync --json
```

**新增文件：**

| 文件 | 职责 |
|------|------|
| `sellfox_shipping/package_models.py` | 内部包裹领域模型 |
| `sellfox_shipping/package_repository.py` | SQLAlchemy 多对多持久化 |
| `sellfox_shipping/package_service.py` | 分页同步 + 对账报告 |
| `tests/sellfox_shipping/test_*.py` | 21 个定向测试 |

**关键修改：**

| 文件 | 变更 |
|------|------|
| `sellfox_client.py` | 动态 account 路径、Bearer、`fetch_package_page`、坏行隔离；legacy `fetch_packages` 仍返回 `list[Order]` |
| `cli.py` | `packages-sync`；`partial_failed` 时退出码 1 |
| `pyproject.toml` / `uv.lock` | 增加 `pytest` 开发依赖 |
| `README.md` / `AGENT_HANDOFF.md` / `docs/log.md` | 阶段与命令同步 |

**提交：** `0b157e7 feat(sellfox-shipping): 建立 P1A 包裹只读同步链路`

### 3.4 实现中发现并已修复的问题

这些曾阻塞提交，回归测试已覆盖：

1. **分页漏数**：必须按服务端实际返回行数累计翻页，不能盲用请求 `page_size`。  
2. **并发 upsert**：账户/包裹/订单用 SQLite `ON CONFLICT DO NOTHING` + 再读；避免先查后插竞态。  
3. **坏行隔离**：嵌套对象非法时只记该行失败，不中断整页。  
4. **legacy 契约**：`fetch_packages` 保持返回 `Order`，新路径用 `fetch_package_page`。  
5. **账户一致性**：`request.account_key` 必须与 record `account_key` 一致，否则 `account mismatch`。  
6. **PII**：持久化异常不得把 SQL/原文写入报告，统一 `persistence error`。  
7. **部分失败可对账**：第二页 gateway 失败时返回 `sync_status=partial_failed`、已落库逐行结果、脱敏 `run_errors`；CLI 退出码 1。  
8. **首屏失败**：`total_in_sellfox` / `remaining_count` 为 `null`（未知），不是 0。  
9. **actor**：去空格且禁止空白。

## 4. 当前代码事实（接手后先验证）

```bash
# 测试（本会话末次证据：21 passed）
uv run pytest tests/sellfox_shipping -q

# 命令帮助
uv run python -m sellfox_shipping.cli packages-sync --help

# 真实同步（需要 proxy 与 SELLFOX_PROXY_API_KEY；只读，不回写）
uv run python -m sellfox_shipping.cli packages-sync \
  --date-start YYYY-MM-DD --date-end YYYY-MM-DD \
  --actor <operator-id> --json
```

**持久化表（package repository，与 legacy `store.py` 并存）：**

- `shipping_accounts`
- `shipping_packages` — 唯一 `(account_id, package_sn)`
- `shipping_orders` — 唯一 `(account_id, external_order_id)`
- `shipping_package_orders` — 包裹↔订单多对多
- `shipping_package_items` — 按包裹保存商品行

**SQLite：** WAL、`foreign_keys=ON`、`busy_timeout=5000`。Schema 由 Alembic `0001_package_schema` 管理（`schema.upgrade_schema`）；legacy create_all 库无版本表时 stamp。

**Legacy 仍在、尚未迁移：** `models.py` / `store.py` 订单中心模型、Web `/api/orders/*`、MCP、`fetch` CLI。不要在其上堆蜴国际流程。

## 5. 明确尚未完成（下一步）

按综合文档阶段，建议顺序：

### 阻塞 P1B 的 P0（业务依赖，代码无法替代）

- [x] 收集蜴国际：上传 Excel、返回追踪号 Excel、PDF 样例（已放到 `数据源/蜥蜴国际-p0-样例/`；① 赛狐导出仅表头无数据）  
- [x] 列结构分析：见 [lizard-p0-column-mapping-2026-07-17.md](lizard-p0-column-mapping-2026-07-17.md)  
  - 匹配键：`参考编号/Reference Code`（形如 `P8140…`）上传/返回原样一致  
  - 追踪号列：`物流单号`；蜴国际侧单号：`订单号`（`M6180…`，非赛狐 orderId）  
  - **重量单位陷阱**：上传 `重量`=克，返回 `重量(kg)`=千克  
  - ① 与 ②–④ 非同批；②⊂③（38/99）；当前本地 sync 库与样例 `P8140…` 零重叠  
- [x] **业务确认**：参考号=赛狐 `packageSn`；重量按蜴国际模板要求换算即可  
- [x] Colab notebook 遗产摘要（背贴为主，不生成上传 Excel）  
- [x] 赛狐→蜴国际试转换 10 单；重尺改走 commodity pageList（8/10 命中）  
- [ ] 未命中 SKU（如 KS0002-DL-194）接 ERPNext 重量模板兜底  
- [ ] 发货编码：暂 `S0143`；仓别映射（USNJ/USTX）待业务确认后再做  
- [ ] 同事 A 重导①（有数据行的赛狐按包裹导出）  
- [ ] 明确 `submitToPlatform` 合约验证范围  
- [ ] 用测试包裹验证赛狐提交契约与回读语义（`submitToPlatform` 幂等性、回读权威性仍为待验证假设）

### P1A 后续（可继续编码，不依赖蜴国际样例）

- [x] 正式 schema migration（Alembic `0001` + `0002_local_review_status`）  
- [ ] 钉钉 OIDC；禁止未认证暴露 PII（legacy Web 仍绑定 `0.0.0.0` 且无 auth）  
- [x] 包裹查询 Web + REST  
- [x] 本地审核写操作（通过/驳回/重置 + AuditEvent）  
- [x] `AuditEvent` 记录 actor（同步 + 审核）  
- [x] Skill 已更新为 P1A 包裹主路径（`.agents/skills/sellfox-shipping`）  
- [ ] 逐步废弃或隔离 legacy 订单入口，避免双模型漂移

### P1B / P1C（依赖样例或明确测试账号）

- [x] 蜴国际 `SpreadsheetCarrierAdapter` 骨架：导出 / 导入对账（CLI `lizard-export` / `lizard-import-tracking`）  
- [x] ERPNext ZLMB# 重尺兜底（Lesson 17；级联 DimsLookup）  
- [ ] 人工确认后的安全 `submitToPlatform`（订单级 `SubmissionIntent` / `SubmissionAttempt`、scope UNKNOWN 阻断、包裹聚合状态）  
- [x] VITE httpx spike（mock）；Karrio custom connector 对比仍可选；不替换通途生产

### 明确暂不做（见综合文档 §11）

- 完整 Karrio Server、Celery、完整 MCP、生产切换 VITE、静默打印、第二套完整规则引擎

## 6. 关键决策摘要（勿推翻除非有新证据）

1. **聚合根是 Package，不是 Order。**  
2. **Excel 与 API 同为正式承运人通道。**  
3. **Karrio Server 不采用；SDK 仅经防腐层可选使用。**  
4. **VITE 无现成 Karrio connector；spike = 新建最小 custom connector vs httpx，不承诺上线。**  
5. **`submitToPlatform` 不可盲重放；一包多单按订单 intent；UNKNOWN 按 `(account, package, order)` scope 阻断。**  
6. **内部 snake_case / 外部 camelCase 必须在 gateway 转换。**  
7. **赛狐导入/回写前必须由用户确认范围；默认测试包裹，不全量。**

## 7. Git 状态（文档撰写时）

| Commit | 说明 |
|--------|------|
| `27cd46d` | 独立调研 + OKF 导航 + 命名边界 |
| `0b157e7` | P1A 包裹只读同步 |
| `275919e` / `ebed58a` | 交接文档；packages-list + AuditEvent |
| `a03f3e2` | PR #88 合入 main |
| `4605670`～`bda5e0d` | REST + Jinja 包裹页 |
| `7472fbc` | Alembic `0001` |
| `97cdcb1`～`1a2f340` | serve 可选 MCP；线上 proxy + `.env` 加载；真实同步验证 |
| （本切片） | 本地审核写操作 `local_review_status` + migration `0002` |

### 7.1 并行工作边界（2026-07-16）

同事 Agent 正在并行调研 **VITE API** 与 **Karrio**，**尚未提交**。本分支在其成果落地前：

- **不扩展** VITE spike / Karrio custom connector / GOFO 接入实现  
- **不改写**综合文档中 VITE/Karrio 专章为「最终结论」  
- **继续做**与样例无关的 P1A：本地包裹查询、`AuditEvent`、后续 migration/OIDC/审核界面  

对方提交后，再对照合并进 `research/` 或 P1C 决策材料。

### 7.2 本切片续作（提交 `275919e` 之后）

已实现并验证：

1. **`ListPackagesService` + `packages-list` CLI** — 按 `account_key` / `package_status` / `channel_name` 过滤；返回 `order_count` / `item_count` 摘要，不走 legacy `store.py`。  
2. **`shipping_audit_events` + sync 审计** — 每次 `packages.sync` 结束（含 `partial_failed`）写一条 `AuditEvent`；审计写失败只记入 `run_errors`，不丢弃同步报告。  
3. **`GET /api/packages` + `GET /api/packages/{package_sn}`** — REST 只读。  
4. **`/packages` + `/packages/{package_sn}` Jinja 页** — server-rendered 审核只读；Starlette 1.2 需 `TemplateResponse(request, name, context)`。  
5. **Alembic** — `schema.upgrade_schema()`；`0001_package_schema`；legacy create_all 库 stamp。  
6. 测试基线：**34 passed**。  

仍未做：OIDC、Excel、`submitToPlatform`、VITE/Karrio、审核写操作。

工作区可能仍有**无关**未提交文件（advertise、dam、codex config 等）；接手时**只提交 sellfox_shipping 相关改动**，勿把敏感配置或数据文件打进 PR。

**本文档批次（撰写时尚未 commit）涉及文件：**

- `sellfox_shipping/docs/research/session-progress-2026-07-16.md`（新建）
- `sellfox_shipping/docs/research/index.md`、`ONBOARDING.md`
- `sellfox_shipping/docs/research/research-synthesis-2026-07-16.md`（文首交接指针）
- `sellfox_shipping/docs/index.md`、`docs/log.md`
- `sellfox_shipping/AGENT_HANDOFF.md`、`README.md`
- 根目录 `index.md`（仅 sellfox_shipping 段；勿全量跑 `update_index.py` 除非工作区干净）

凭证扫描：禁止硬编码真实 API Key；测试里 mock key 仅用短占位符。

## 8. 验证清单（接手后应再跑一遍）

```bash
uv run pytest tests/sellfox_shipping -q
# 期望：21 passed（或随你新增测试递增）

git log --oneline -3
# 应看到上述两个提交

git status
# 确认自己改动范围，勿混入无关文件
```

真实 proxy 同步前确认：

- `SELLFOX_PROXY_API_KEY` 已设置  
- `config.yaml` 中 `proxy_base_url` / `proxy_account` 正确  
- 用户已确认日期与店铺范围（不全量）  
- 本命令**不会**调用 `submitToPlatform`

## 9. 文档索引联动

本文登记于：

- [research/index.md](index.md) — 「接手继续实现」入口  
- [../index.md](../index.md) / [../log.md](../log.md)  
- [../../AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) — 新对话 30 秒接手  
- [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) 文首指针  
- 根目录 `index.md`（`uv run python scripts/update_index.py`；脏工作区时注意只同步本模块、避免夹带其它模块漂移）

**Cursor 会话 transcript（可选追溯）：**  
`agent-transcripts/6a537da8-7f80-449f-91f3-bb7511de203d`（本机 Cursor 项目目录下；仓库外，不入 Git）。

## 10. 2026-07-17 续：赛狐原生夹具 + PDF 面单替换

| 交付 | 位置 |
|------|------|
| 夹具 00/02/03/04 | `数据源/…/sellfox-native-fixture/`（gitignore） |
| 上传/追踪号重建 | `scripts/rebuild_sellfox_lizard_fixtures.py` |
| PDF 通途→赛狐 | `scripts/replace_tongtu_refs_in_labels.py`（可提交）；详见 `pnumber-to-sellfox-trace` §6 |
| 本地导入 smoke | 38/38 persisted；**未** `submitToPlatform` |

## 11. 2026-07-17 续：P1B Web + 重尺补录（文档快照）

**分支：** `feature/sellfox-shipping-p1a-rest`  
**验证：** `uv run pytest tests/sellfox_shipping -q` → **64 passed**

| 提交 | 内容 |
|------|------|
| `4585c16` | 追踪号本地落库 + 赛狐原生夹具脚本 |
| `63e7319` | Web `/lizard/export`、`/lizard/import` 对账页 |
| `057bd48` | serve 启动打印导出/导入 URL |
| `1af6efc` | 缺 carton 本地人工补录（`0003` + 包裹详情表单） |

### P1B 已具备

- CLI：`lizard-export` / `lizard-import-tracking`
- Web：导出、导入对账、本地审核、重尺补录
- 重尺链：本地 override → pageList → ERPNext ZLMB
- 夹具 02/03/04（本地 gitignore，可对照格式）

### P1B 规划中仍缺（见综合调研 §5.3 / §10）

- ~~**导出批次 Artifact 表**~~ → **已实现**（2026-07-17）：`shipping_artifacts` + `/lizard/artifacts`
- ~~**ShippingBatch / BatchPackage 最小实体**~~ → **已实现**（2026-07-17）：Alembic `0005`；导出建批；导入可选 `batch_id`；Web `/lizard/batches`
- 完整 P1C 提交状态机 / `submitToPlatform`（Batch 目前只有 `exported` → `tracking_imported`）

### Artifact 答疑（实现后）

| 问题 | 答案 |
|------|------|
| 是否含系统生成文件？ | **是**。`lizard-export` / Web 导出生成的上传 Excel 会登记为 `lizard_upload_export` |
| 人工上传？ | **是**。导入追踪号 Excel 登记为 `lizard_tracking_import` |
| 在哪里看？ | Web：`/lizard/artifacts`；磁盘：`data/artifacts/private/files/…` |
| content_hash？ | **MD5**（32 hex），与 ERPNext File 对齐 |
| 与 ERPNext File 关系？ | 扁平 `private/files` + MD5 去重 blob；`virtual_folder` 不改物理路径。详见 [artifact-vs-erpnext-file](artifact-vs-erpnext-file-2026-07-17.md) |
| ShippingBatch？ | Web：`/lizard/batches`；导出自动建批；导入填批次 ID 更新包裹行状态 |

## 13. 2026-07-17 续：ShippingBatch MVP + 扁平 Artifact + 操作记录

**分支：** `feature/sellfox-shipping-p1a-rest`  
**验证：** `uv run pytest tests/sellfox_shipping -q` → **72 passed**  
**Schema head：** `0005_shipping_batches`（依赖 `0004_artifacts`）

### 本切片交付

| 项 | 说明 |
|----|------|
| Alembic `0005` | 表 `shipping_batches`、`shipping_batch_packages` |
| 导出建批 | `ExportLizardUploadService` → `create_export_batch`；结果含 `batch_id` |
| 导入回填 | `LizardImportRequest.batch_id` 可选；`apply_import_to_batch`；状态 `exported` → `tracking_imported` |
| Artifact 路径 | `data/artifacts/private/files/{stem}_{hash8}{ext}`；同 **MD5** 共用 blob（对齐 EN） |
| Web | `/lizard/batches`、`/lizard/batches/{id}`；导入表单「批次 ID」；导航「批次」 |
| CLI | `lizard-import-tracking --batch-id N` |
| 文档 | `artifact-vs-erpnext-file-2026-07-17.md`（content_hash = MD5） |

### 操作员步骤（本地，不调用 submitToPlatform）

```text
1. 启动（务必 --reload，避免旧进程 404）
   uv run python -m sellfox_shipping.cli serve --host 127.0.0.1 --port 8401 --reload

2. 同步 / 审核包裹（已有流程）
   packages-sync → 包裹详情本地审核 approved → 缺重尺则补录

3. 导出蜴国际上传表
   Web:  http://127.0.0.1:8401/lizard/export
   CLI:  uv run python -m sellfox_shipping.cli lizard-export -o out/lizard-upload.xlsx --actor <谁> --json
   → 下载文件名含 batch{N}；响应头 X-Shipping-Batch-Id
   → 自动登记 Artifact(kind=lizard_upload_export) + ShippingBatch(status=exported)

4. 人工上传 Excel 到蜴国际后台（可能产生费用；测试先问同事）

5. 导入追踪号返回表并对账
   Web:  /lizard/import  （可填步骤 3 的批次 ID，或从 /lizard/batches 点「导入到此批」）
   CLI:  lizard-import-tracking -i return.xlsx --actor <谁> --batch-id N --json
   → 只写本地库追踪号；登记 Artifact(kind=lizard_tracking_import)
   → 若带 batch_id：批次 → tracking_imported；包裹行 tracking_matched / conflict / unmatched

6. 查阅
   制品: http://127.0.0.1:8401/lizard/artifacts
   批次: http://127.0.0.1:8401/lizard/batches
   磁盘: sellfox_shipping/data/artifacts/private/files/
```

### 批次 / 包裹行状态（MVP，非 P1C）

| 实体 | 状态 |
|------|------|
| ShippingBatch | `exported` → `tracking_imported` |
| BatchPackage | `exported` / `skipped` / `tracking_matched` / `tracking_conflict` / `unmatched` |

### 仍不做

- `submitToPlatform` / 赛狐追踪号回写
- 完整提交状态机、钉钉 OIDC
- Artifact 公网 `/files` 分流

### 已知坑

- 旧 `serve` 无 `--reload` 时改路由会 404 → Ctrl+C 后带 `--reload` 重启
- 历史 38 单蜥蜴样例 `trackNo` 多为 packageSn 占位 → **勿**当回写测试数据
- 若本地曾用 SHA-256 登记制品：清空 `data/artifacts/` 后重新导出/导入即可（算法已改 MD5）
- `数据源/**`、`data/`、真实 Key 不入 Git

## 15. 2026-07-17 续：外部依赖进展 + 进入 P1C

### 用户同步（事实）

| 项 | 状态 |
|----|------|
| 蜴国际 API | 文档合入 main：`蜴国际-API/`（PR **#90**）。getToken/ratesv2 可用；createOrder 等欠费未测。**未接本仓代码**；对照见 lizard-api-vs-excel |
| VITE 文档 + 测试环境 | 已到位；同事测完并合入 **main**：PR **#88**、后续小变更 **#89** |
| 本分支 PR | **暂不提 PR**，继续在 `feature/sellfox-shipping-p1a-rest` 开发 |
| 查 VITE 资料 | `origin/main` 的 `vite-api/` 模块（或已合并的 PR 88 内容） |

### 规划下一步（P1C）

综合调研 §10 **P1C**：人工确认 + 安全 `submitToPlatform` + VITE spike。

本切片已开：

1. **纯函数** `aggregate_package_submission_state`（无 HTTP）— `submission_state.py` + `test_submission_state.py`
2. 后续（未做）：`SubmissionIntent` / `SubmissionAttempt` 表、CAS、1 rps、mock 下的 `submitToPlatform`；**真实调用前必须用户确认测试包裹范围**
3. VITE spike：对照 `vite-api/` 文档做 httpx adapter vs Karrio 比较；**不替换通途生产**；凭证不入仓

### 仍禁止

- 对历史 `has_shipped` 样例调用 `submitToPlatform`
- 未确认范围的生产回写
- 把 VITE/蜴国际凭证写入 Git

## 16. 2026-07-17 续：SubmissionIntent + CAS（mock）

**分支：** `feature/sellfox-shipping-p1a-rest`  
**验证：** `uv run pytest tests/sellfox_shipping -q` → **106 passed**  
**Schema head：** `0006_submission_intents`

| 项 | 说明 |
|----|------|
| Alembic `0006` | `shipping_submission_scopes` / `_intents` / `_attempts` |
| Service | `submission_service.py`：canonical SHA-256 hash、prepare、CAS、UNKNOWN scope、recover |
| Wire | 新路径用 `orderId`（非 legacy `write_tracking` 的 `amazonOrderId`） |
| CLI | `packages-prepare-submit`；`packages-submit-intent`（默认 `--dry-run`；真调需 `--no-dry-run --i-understand-side-effects`） |
| 测试 | hash / CAS / scope / recover / migration |

### 操作员（仍不默认打赛狐）

```text
# 1. 包裹已 approved + 有真实 tracking_number
uv run python -m sellfox_shipping.cli packages-prepare-submit \
  --package-sn P2A... --actor <谁> --json

# 2. 预览提交（无 HTTP）
uv run python -m sellfox_shipping.cli packages-submit-intent \
  --intent-id <N> --actor <谁> --json

# 3. 真调（须用户确认测试包裹 + 双 flag）
uv run python -m sellfox_shipping.cli packages-submit-intent \
  --intent-id <N> --actor <谁> --no-dry-run --i-understand-side-effects --json
```

### 下一刀

- ~~Web 确认 UI~~（准备 Intent + dry-run；真调仍仅 CLI）
- ~~1 rps 限流；回读 VERIFIED~~
- VITE spike（`vite-api/` on main）
- ~~蜴国际 API 文档~~ → PR **#90** 已合入 main（`蜴国际-API/`）；createOrder/getLabel 因欠费未测 → 暂不替换 Excel

## 17. 2026-07-17 续：蜴国际 API PR#90 + Web 提交确认

**事实：** Merge PR **#90** → `origin/main` 模块 `蜴国际-API/`（getToken/ratesv2 已测；下单类欠费未测）。  
**对照文档：** [lizard-api-vs-excel-2026-07-17.md](lizard-api-vs-excel-2026-07-17.md)  
**安全提醒：** 该模块 HANDOFF 若含明文 token/key，勿拷贝；建议同事改为环境变量占位。

**本切片：**

| 项 | 说明 |
|----|------|
| Web | 包裹详情「赛狐回写确认」：准备 Intent + dry-run（**无** submitToPlatform） |
| 路由 | `POST .../prepare-submit`、`POST .../submit-intent/{id}` |
| 测试 | `test_package_prepare_submit_and_dry_run_web` |

## 18. 2026-07-17 续：1 rps + 回读 VERIFIED

**验证：** `uv run pytest tests/sellfox_shipping -q` → **113 passed**

| 项 | 说明 |
|----|------|
| 限流 | `SubmitRateLimiter`（进程内）；结果字段 `rate_limited_wait_ms` |
| 回读 | submit 成功后调 `packageDetail`；`logistics.trackNo` 与 intent 一致 → `VERIFIED` |
| 不匹配 / 超时 | **保持 SUCCESS**，不标 UNKNOWN、不自动重发 |
| CLI | `packages-verify-intent --intent-id N`（仅回读升格） |
| Client | `SellfoxClient.fetch_package_detail(package_sn)` |

```text
# 真调后若仍 SUCCESS，可单独回读核验
uv run python -m sellfox_shipping.cli packages-verify-intent \
  --intent-id <N> --actor <谁> --json
```

## 19. 2026-07-17 续：代理限速口径 + VITE httpx spike

**用户澄清（限速两层）：**

| 路径 | 限速 | 本仓库应对 |
|------|------|------------|
| 直连赛狐官方 OpenAPI | 最多 **1 rps** | `submit_min_interval_seconds: 1.0` |
| 共享代理 `https://api.vilavi.cn/sellfox`（admin：[/sellfox/admin](https://api.vilavi.cn/sellfox/admin)） | 现约 **0.5 rps**（用户可在代理侧改） | 默认 **`2.0`**（≈0.5 rps）；与 `config.yaml` 中 `proxy_base_url` 一致 |

进程内 `SubmitRateLimiter` **不能**替代多实例/多操作员协调；多客户端并发时仍依赖代理侧限速。

**VITE spike（仅 httpx，mock）：**

| 项 | 说明 |
|----|------|
| 模块 | `sellfox_shipping/carriers/vite/client.py` → `ViteGofoClient` |
| 端点 | `POST /rate2/gofo`、`POST /shipment2/gofo`、`GET /shipment2/label/{orderId}` |
| 凭证 | `VITE_API_KEY` / 可选 `VITE_API_BASE_URL`；**不入仓** |
| 测试 | `tests/sellfox_shipping/test_vite_client.py`（`httpx.MockTransport` only） |
| 不做 | 不替换通途生产；本切片不做 Karrio custom connector；无 live 打单除非用户给 key + 确认范围 |

### 下一刀

- （可选）真测 VITE test env：用户提供范围后再跑 rate（避免误下单）
- Karrio custom connector 对比笔记（仍可选）
- 多实例 submit 协调 / OIDC / 蜴国际 createOrder 验证后 adapter

## 20. 2026-07-17 续：VITE 测试环境 rate 真测

**范围：** 仅 `test-api.vitedirect.com` 的 `GET /user/account` + `POST /rate2/gofo`；**未** createShipment / getLabel。  
**脚本：** `sellfox_shipping/scripts/vite_test_rate_smoke.py`（key 来自 `VITE_API_KEY` 或 `vite-api` 测试文档；不打印 key）。

| 项 | 结果 |
|----|------|
| 账户 | `200`，`balance≈2969.48`（虚拟余额；rate 不计费） |
| GOFO_PX + PARCEL | OK，`totalAmount=3.8`，zone=3 |
| GOFO_PARCEL + GFUS | OK，`totalAmount=3.35`，zone=1 |
| GOFO_PARCEL + YT | OK，`totalAmount=3.35`，zone=1 |
| GOFO_PX + GFUS | 仍无效（与 PR#88 报告一致） |
| 文档示例 CA `91321` 发件 | 400「邮编不在配送范围」→ 改用报告内 MA `02478`→NH `03053` |

**口径：** 测试价 ≠ 生产价；同事正用生产测 rate。本仓继续以测试环境验证契约，不切换通途生产。

### 下一刀

- （可选）测试环境 createShipment + getLabel（会动虚拟余额；须用户确认）
- Karrio custom connector 对比笔记（仍可选）
- 多实例 submit 协调 / OIDC / 蜴国际 createOrder 验证后 adapter

## 14. 本文档维护约定

后续 Agent 完成一个可交付切片后，应：

1. 在本文追加新章节（日期 + 做了什么 + 提交哈希 + 验证命令 + 未完成项），或新建 `session-progress-YYYY-MM-DD.md` 并改本索引入口  
2. 同步 `docs/log.md` 与 `AGENT_HANDOFF.md`「当前阶段」  
3. 勿把聊天里的临时假设写成已确认事实；用户确认项写进综合文档附录 A
