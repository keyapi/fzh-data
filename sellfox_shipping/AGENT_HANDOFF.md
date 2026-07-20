---
okf: v0.1
type: Handoff
title: sellfox_shipping — Agent 交接说明
description: 包裹中心架构、当前实现、运行方式与后续阶段边界
updated: 2026-07-17
---

# sellfox_shipping — Agent 交接说明

> **赛狐尾程打单系统** — 包裹批次工作流  
> 人读文档: [README.md](README.md)  
> **新 Agent 必读:** [docs/research/session-progress-2026-07-16.md](docs/research/session-progress-2026-07-16.md)  
> **规划入口:** [docs/research/research-synthesis-2026-07-16.md](docs/research/research-synthesis-2026-07-16.md)

## 新对话 / 换 Agent 接手（30 秒）

1. 读 [session-progress-2026-07-16.md](docs/research/session-progress-2026-07-16.md) — 已完成过程、提交、下一步、勿踩坑（含 §11 P1B 快照）  
2. 读 [research-synthesis-2026-07-16.md](docs/research/research-synthesis-2026-07-16.md) — 目标架构与阶段  
3. 跑验证：`uv run pytest tests/sellfox_shipping -q`  
4. 当前分支：`feature/sellfox-shipping-p1a-rest`

**阶段口径：** 旧「P1 骨架完成 / P2 FedEx」作废；现行阶段为 **P0 → P1A → P1B → P1C → P2+**。旧代码称 **legacy skeleton**。  
**当前：** P1A/P1B 可用；**P1C**：Intent/CAS + 限流回读已落地；**VITE httpx spike + 测试真测 + 选型决策已完成**（不做 Karrio VITE connector）。默认 dry-run CLI。  
**外部：** VITE → `vite-api/` + `carriers/vite/`；蜴国际 → `yiglobal-api/`（**#90 文档 + #91 负余额下单/面单/取消已验**；原 `蜴国际-API/`）。Excel 仍生产默认。**暂不提 PR。**
**限速：** 官方 1 rps；共享代理现约 0.5 rps → `sellfox.submit_min_interval_seconds` 默认 `2.0`。
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

# P1B：蜴国际上传 Excel（仅 local_review=approved 且渠道含「蜴」；重尺走 commodity pageList）
uv run python -m sellfox_shipping.cli lizard-export -o out/lizard-upload.xlsx --actor <operator-id> --json

# P1B：解析蜴国际返回追踪号 Excel（按 package_sn 对账；尚未回写赛狐）
# 可选 --batch-id：回写对应 ShippingBatch
uv run python -m sellfox_shipping.cli lizard-import-tracking \
  -i path/to/return.xlsx --actor <operator-id> --batch-id <N> --json

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
├── config.yaml           # proxy、仓库、承运人配置
├── carriers/lizard/      # 蜴国际 Excel 模板与重尺查找 ★
├── carriers/             # 其它承运人抽象（尚未接闭环）
├── templates/            # Web UI (Jinja2)
├── docs/
│   ├── index.md
│   ├── log.md
│   └── research/
│       ├── research-synthesis-2026-07-16.md   # 规划
│       └── session-progress-2026-07-16.md     # 会话进度交接
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
**VITE：** 测试环境 account/rate/create/getLabel/cancel 已验；决策采用 httpx。  
**蜴国际：** PR#91 已验下单链路；本仓 `LizardApiClient`（httpx 同步，mock）；Excel 仍生产默认。勿从 main HANDOFF 拷明文 Key。

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
