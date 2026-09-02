---
module: web_automation
date: 2026-09-02
problem_type: architecture_pattern
component: development_workflow
severity: medium
tags: [web-automation, playwright, capability-pod, monorepo, uv-isolation, dispatcher, sellfox, tongtu]
applies_when:
  - 同事需要"只 clone 一个仓库"即可用数据/API/网页自动化
  - 需要给弱模型/新同事一个"不猜环境"的固定浏览器任务入口
  - 某平台 API 不完整、仍需浏览器自动化，但不想让所有人装 OCR/Chromium
  - 考虑把相邻工具仓库并入主仓库
symptoms:
  - "同事要 clone fzh-data + fzh-web-automation 两个仓库"
  - "网页脚本硬编码 D:\\Work\\赛狐\\网页自动化 与 .venv\\Scripts\\python.exe"
  - "把 ddddocr/onnxruntime 放进根 pyproject 会让所有 uv sync 用户强制下载"
resolution_type: migration
related_components: [sellfox, tongtu, playwright, tooling]
---

# 网页自动化迁入 fzh-data：单仓库独立 uv 能力舱 + 固定 dispatcher

## Context

FZH 维护赛狐 / ERPNext / 通途三方一致性。网页自动化脚本长期散落在相邻仓库
`keyapi/fzh-web-automation`（通途库存/销售导出、赛狐出入库/备货导入、通用 Playwright）。
同事要 clone 两个仓库；根级调度器（`warehouse_restock/`、`missing_products/`）硬编码
`D:\Work\赛狐\网页自动化` 与 `.venv\Scripts\python.exe`，换机器即碎。

与此同时：赛狐/EN 已有正式 API（赛狐仍不完整），通途 API 限流仍靠浏览器；网页自动化
能力对非技术同事有价值，但 **root `uv sync` 不能让所有人装 Playwright/Chromium/ddddocr/
onnxruntime**——同事用 Codex/WorkBuddy/Claude，且可能用弱模型，不能依赖人或模型临场判断
Python 环境、脚本路径、API/网页边界。

方案是"独立能力舱"：一个 Git 仓库内嵌一个**不加入 workspace** 的独立 uv 子项目
`web_automation/`，配统一 dispatcher + 能力矩阵，把能力选择、环境准备、安全边界固化为可执行入口。

(本次实施：PR #208 `feature/web-automation-capability-pod`，源仓库 `origin/main` 04698a8)

## Guidance

### 架构：一仓库多 uv 项目，而非 workspace / dependency group

- `web_automation/` 有自己 `pyproject.toml`、`uv.lock`、`.venv`、`.python-version`（3.12）。
- **不加入 uv workspace**：workspace 共享 lockfile/env，会重新耦合 OCR/浏览器依赖。
- **不用根 dependency group**：uv 的 group 即使不装也统一参与解析，OCR 约束会污染根锁。
- 根项目从不依赖子项目包；跨环境只在 subprocess 层用 `uv run --project web_automation python …`。

依赖分层：基础浏览器层（playwright/pandas/openpyxl/pyyaml…）默认装；OCR
（ddddocr/onnxruntime）放 `[dependency-groups] ocr`，仅 `--with-ocr` 时 `uv sync --group ocr`。
子项目是**虚拟项目**：去掉 `[build-system]`，否则 hatchling 对 `packages=[]` editable 构建报错。

### 入口契约：Agent 只表达业务目标

`web_automation/capabilities.yaml` 是版本化能力矩阵（`platform.action` → mode/risk/通道/回退）。
`scripts/dispatch.py <task> --check` 输出确定状态：

| 状态 | 含义 | 处理 |
|------|------|------|
| `READY` | 路由可用 | 继续执行 |
| `NEED_BROWSER` | 子环境/Chromium 未装 | `scripts/bootstrap.py` |
| `NEED_LOGIN` | 需人工登录 | 打开浏览器让人登录一次（持久化 profile） |
| `NEED_OCR` | 请求 OCR 但未装 | 先问用户，`--with-ocr` |
| `NEED_USER_CONFIRMATION` | 写操作未确认范围 | 带 `--confirm-scope "文件/SKU/仓库范围"` |
| `BLOCKED` | 禁止回退/环境阻断 | 报告，别绕过 |

弱模型读状态字面执行；agent **不得**自拼绝对路径/选 venv/直接装 OCR。

### API/浏览器回退纪律

四类 mode：`API_ONLY` / `API_FIRST_BROWSER_FALLBACK` / `BROWSER_ONLY` / `MANUAL_CONFIRM`。
- 认证/权限/参数/业务校验错误**命中即 BLOCKED**，绝不静默回退浏览器掩盖。
- 仅显式列出的"端点缺失/不支持/服务不可用"允许回退。
- 旧脚本只回普通非零码 → 映射 `UNCLASSIFIED_FAILURE` → BLOCKED，不猜。
- `sellfox_auto_export.py --api` / `sellfox_restock_api.py` 属**私有网页 cookie API**
  （`contract: private-cookie-api`），与正式 `SELLFOX_API` OpenAPI 合同稳定性不同，不可混用。

### 路径与目录约定

迁移脚本统一改 `SCRIPT_DIR = Path(__file__).resolve().parent` + `WEB_ROOT = SCRIPT_DIR.parent`
（`legacy-compatible/`/`click-based/`/`cdp-based/` 内脚本的 profile/downloads/output 一律
指向 `web_automation/` 根），避免各脚本产物散落到子目录。`.env` 从 `web_automation/.env`
或**仓库根 `.env`** 读。凭证仍按项目约定留在父仓库主 checkout，worktree 不复制 `.env`。
profiles/cookies/downloads/output/截图在子目录 `.gitignore` + 根 `.gitignore` 双重防线。

### 迁移纪律（本次实操）

- 源：`git archive origin/main`，**只取 tracked 文件**，不带 `.env`/profiles/未跟踪文件。
  迁移前先确认源工作树 ≠ `origin/main`（本次就在落后分支 + 有未跟踪文件）。
- 平台知识（选择器/踩坑）迁成 `.agents/skills/` + `web_automation/docs/`；执行命令改为 dispatcher。
- 清 UTF-8 BOM（4 个源文件）；路径一次性改写后要查重复行（改写脚本曾重复插 `WEB_ROOT=`）。
- 修历史 bug：`test_e2e_flow.py` step5 曾**调用自身**做"备货单生成"（自递归），改调真脚本。
- Phase B 退役/去重**另开计划**，本轮只写门槛文档，不删旧实现。

## Why This Matters

- 新同事只 clone `fzh-data` + `uv sync` 即得全部能力；浏览器按任务触发初始化，
  OCR 只在明确要求时安装——首次运行时间和 Windows 二进制兼容风险都受控。
- 把"何时用 API、何时浏览器、何时回退"写成矩阵而不是长提示词，弱模型也能正确路由；
  写操作范围由 dispatcher 强闸（`NEED_USER_CONFIRMATION`），守住用户主权。
- `tests/web_automation/` 把根/子环境隔离、回退分类、写闸门、外部路径清零固化成回归测试，
  后续加平台/动作不会悄悄破坏路由。

## When to Apply

- 在 `fzh-data` 里新增网页任务：先在 `capabilities.yaml` 登记动作 + mode + 回退，再写脚本；
  脚本放 `web_automation/` 对应子目录，profile/downloads/output 指向根。
- 新增目标网站：用 Playwright MCP 探路确认选择器闭环后，再沉淀 Python + dispatcher 路由。
- 收到"把 X 仓库并入 fzh-data"类请求：先做 tracked-file 快照 + 外部路径清单，
  评估要不要独立 uv 子项目（依赖重/版本隔离需要），再做迁移而不删实现。

## Examples

### dispatcher 路由（写操作必须确认范围）

```bash
# 读：先 check，再执行
uv run python web_automation/scripts/dispatch.py tongtu.stock.export --check
uv run python web_automation/scripts/dispatch.py tongtu.stock.export

# 写：无 --confirm-scope 时返回 NEED_USER_CONFIRMATION (exit 3)
uv run python web_automation/scripts/dispatch.py sellfox.restock.import \
  --confirm-scope "用户确认的文件/SKU/仓库范围" -- <文件.xlsx>
```

### 能力矩阵片段（capabilities.yaml）

```yaml
sellfox.stock.export:
  mode: API_FIRST_BROWSER_FALLBACK
  risk: read
  allowed_fallback_codes: [ENDPOINT_MISSING, ENDPOINT_UNSUPPORTED, SERVICE_UNAVAILABLE]
  blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED, INVALID_ARGUMENT, BUSINESS_VALIDATION]
  implementation: { api: legacy-compatible/sellfox_auto_export.py, api_args: [--api],
                    browser: legacy-compatible/sellfox_auto_export.py }
sellfox.restock.import:
  mode: MANUAL_CONFIRM          # write ⇒ dispatch 先要 --confirm-scope
  implementation: { browser: click-based/sellfox_import_warehouse_restock.py }
```

### 根级调度器改 dispatcher（消除外部路径）

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
run_web_task("sellfox.stock.export")                       # 导出
run_web_task("sellfox.restock.import", confirm_scope="…")  # 导入（写）
```

## 参考

- 实施计划：`docs/superpowers/plans/2026-08-26-fzh-web-automation-integration.md`
- 能力矩阵与安全边界：`web_automation/docs/reference/capability-matrix.md`、
  `web_automation/docs/reference/security-and-local-state.md`
- Phase B 门槛：`web_automation/docs/reference/phase-b-retirement-gates.md`
- 迁移日志：`web_automation/docs/log.md`
- PR #208 `feature/web-automation-capability-pod`
- 相关约定（auto memory）：凭证在父仓库主 checkout（worktree 不复制 `.env`）；一律
  `uv run python`；提交走 feature 分支 → PR，禁止直推 main。
