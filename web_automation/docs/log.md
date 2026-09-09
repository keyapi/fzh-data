---
okf: v0.1
type: Log
title: web_automation 变更日志
description: web_automation 能力舱 OKF 变更日志（迁移 + 能力新增与审查修补）
tags: [web-automation, tongtu, sellfox, playwright, log]
---

# 迁移日志

## 2026-09-02 — Phase A 兼容迁移

**源**：`keyapi/fzh-web-automation` `origin/main` commit `04698a8fb181081221b2997ac511ffc29a474c89`（本机主 checkout 的跟踪基线）。

**入口交付（web_automation/scripts/）**：
- `capabilities.yaml` — 版本化能力矩阵（tongtu/sellfox/generic 7 个动作）
- `runtime.py` — 矩阵解析、错误分类、命令构造（纯标准库 + yaml）
- `bootstrap.py` / `doctor.py` — 按需子环境 + Chromium / 只读体检
- `dispatch.py` — 固定 Agent 入口 + 写操作范围闸门

**迁移脚本**：
- 计划迁移 19 个入口 + 3 个 cdp + `.env.example`/`.mcp.json`
- 实际迁移：`legacy-compatible/` 16 py、`click-based/` 7 py + AGENT_HANDOFF、`cdp-based/` 3 py
- 路径规范化：SCRIPT_DIR → WEB_ROOT 统一指向 `web_automation/` 根；BOM 清除（4 文件）
- 跳过（不迁移）：profiles/cookies/`.env`/downloads/output/截图/Excel；`okf` skill（根已有）；`.codex/`、`.claude/`、未跟踪 `SKILL_*.md`

**根级改造**：
- `.agents/skills/` 新增 4 个自动化 skill（dispatcher-first），改造 stock-init / warehouse-restock
- `warehouse_restock/run_full_restock_flow.py` + `test_e2e_flow.py` 改用 dispatcher，移除自递归
- `missing_products/identify_missing_products.py` + `audit_three_systems.py` 数据目录指向 `web_automation/`
- `AGENTS.md` 加网页任务路由；`scripts/env_doctor.py` 发现能力舱（只读）

**验证对账**：
- `tests/web_automation/` 通过数：**29 passed**（runtime/bootstrap/dispatch/migrated-entrypoints/agent-routes/repo-paths/gitignore/docs）
- 综合回归（web_automation + env_doctor + missing_products）：**62 passed**
- 根环境隔离：root `.venv` 无 playwright/ddddocr/onnxruntime → `ROOT_ISOLATED`
- 子环境默认不含 OCR：`CHILD_BROWSER_ONLY_READY`（ddddocr/onnxruntime 仅在 `--group ocr` 安装）
- Chromium smoke：`playwright install chromium` 成功 + 本地空白页 launch → `CHROMIUM_READY`
- 残留外部路径 `git grep`：**ZERO**（除 `.claude/settings.local.json` 与 docs/superpowers 历史）
- 凭证扫描：改动文件新增行 4 regex 全部 zero；命中仅为 diff 中其它既有文件上下文/占位符
- 索引：`update_index.py --check` → `OK: index.md is up to date`（24 modules / 328 docs）
- dispatcher 路由：读任务 `--check` → READY；写任务无 `--confirm-scope` → NEED_USER_CONFIRMATION

## 2026-09-08 — 新增 tongtu.orderdetail.export（订单详情统计月度导出）

**背景**：财务/运营按月导出通途「订单详情统计」全量自发货订单（全渠道全账号、按发货时间整月）。原纯人工、无脚本。

**交付**：
- `legacy-compatible/tongtu_orderdetail_report.py` — 仿 `tongtu_sales_report.py`：登录（含 ddddocr `--auto-login`）→ 设发货时间范围 → 「统计导出」提交 → 往返 数据查询/统计导出 tab 轮询新「点击下载统计结果」→ 下载 zip
- `capabilities.yaml` + `docs/reference/capability-matrix.md` 注册 `tongtu.orderdetail.export`（BROWSER_ONLY/read）
- `.agents/skills/{web-automation,tongtu-automation}/SKILL.md` 触发词/任务清单
- 新增 `web_automation/AGENT_HANDOFF.md`（模块级 Agent 参考）与 `docs/reference/orderdetail-export.md`（专题：背景/MCP 探路过程/选择器/踩坑/核验）
- `tests/web_automation/test_migrated_entrypoints.py` 登记新脚本入口

**过程要点（MCP 探路确认）**：日期框为 My97，`.fill()` 后勿按 Enter（会整页刷新重置）；「查询」`a[onclick='queryInfo()']` 仅在数据查询 tab 可见，失败须中止；统计结果不自动刷新需往返 tab 轮询；下载基线在历史表稳定后、提交前采集；统计任务提交互斥。

**核验（2026-07 实测）**：`downloads/订单详情统计_202607_*.zip` ≈4.85 MB；xlsx 表头自第 30 行 91 列；9604 行；发货日期 07-01~07-31；数据来源=自发货订单。`uv run pytest tests/web_automation -q` → 48 passed。

## 2026-09-08 — 审查修补（PR #220）

**交付**：查询失败中止（`QUERY_FAILED`）+ 先等历史表稳定再 snapshot 再提交；`--range-start/--range-end` 必须成对；提交打不开弹窗区分 `BUSY`/`SUBMIT_FAILED`；OKF 用法只保留 dispatcher（含 `--check`）。

## 2026-09-09 — 下载识别改为「最上行 = 本次提交」锚定（并入 PR #220）

**为什么**：href 基线差集法在“历史表晚渲染（误认旧任务）”与“小范围快任务（基线含新链接被吞）”两端都有竞态；改成按行身份识别本次任务，两端一并消除。

**改动**（`legacy-compatible/tongtu_orderdetail_report.py`）：
- 去掉 `snapshot_download_hrefs`/`get_existing_download_hrefs`；新增 `capture_prev_top_ts` + `wait_for_my_download`
- 历史表为 fixedHeadFoot 滚动表格：数据表是 header（含「统计条件」th）后 `following::table[1]`（非 sibling），首行空 spacer 须跳过；行文本最后一个 `YYYY-MM-DD HH:MM:SS` = 提交时间
- 提交前记最上行提交时间 → 提交后往返 tab → 最上行提交时间一变锁本次行 → 等该行下载链接

**核验**：单日 2026-07-15 实测 306 行、发货日期全 07-15，RUN_EXIT=0；`uv run pytest tests/web_automation -q` → 48 passed。


