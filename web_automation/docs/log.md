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

## 2026-09-10 — 新增钉钉 aflow 销售收款确认单导出（`dingtalk.aflow.receipt.export`）

**为什么**：财务每期手工从钉钉 aflow「OA审批管理后台」导出销售收款确认单单据 Excel。附件侧 API 路径已跑通，
唯一盲区是离职发起人（`userNotExist`）。本次先把 Excel 这条链沉淀成能力。

**MCP 探路关键结论**（详见 `docs/reference/aflow-receipt-export.md`）：
- 直接开 aflow 会落到**没有任何登录控件**的 `error.vm`；必须先走 `oa.dingtalk.com` 触发统一身份认证 + **选组织**，SSO 才覆盖 aflow。
- 「一键头像登录」依赖钉钉客户端 8441-8443 端口，本机客户端在 **8440** → 不通，最终走扫码。
- 表单名称是 **antd 二级级联**（状态→表单），有多个近似名，必须 `:text-is` 精确匹配。
- 发起时间输入框 **readOnly**，只能走 dtd RangePicker 日历面板；同页有**两对**「开始/结束日期」，用 `nth` 消歧。
- `导出全部` **点按钮本体 = 立即异步导出**；附件选项藏在 **hover** 出来的下拉里（`仅导出审批单附件`）。
- **导出产物是 2 行表头**（行1 审批元数据+合并组标题，行2 明细子字段），数据自第 3 行起；
  **同一单据因明细表重复成多行 → 单据数按唯一 `数据id` 计**。
- **`goto` 同一个 URL（只差 hash）不是重载** —— SPA 不会重新请求，会把旧进度看成"卡住"（本次曾被 96% 误导）。

**附件：证伪**。aflow 无「批量下载附件」；`仅导出审批单附件` 的产物进**钉盘【云盘-团队文件】**，
该行 `下载` 报 `ERR_TOO_MANY_REDIRECTS`；`oa.dingtalk.com` 与 `aflow.dingtalk.com` 是**同一个 SPA**，
不存在可退的"老控制台"。附件维持 API 路径，离职发起人走 Excel 内 `previewAttachments` 深链。

**交付**：`legacy-compatible/dingtalk_aflow_receipt.py`、`capabilities.yaml` 注册、`runtime._PROFILE_DIRS` 加 `dingtalk`、
`.gitignore` 加 profile、`docs/reference/aflow-receipt-export.md`、索引/handoff/capability-matrix 同步、入口测试登记。

**核验（2026-09-10 实测）**：窗口 2026-07-04~09-09 → 405 行 / **265 单据**，发起时间全在窗口内；
产物 232 KB；`数据id` 与 API `instance_ids.json` **265/265 重合**；API manifest 对 6 名离职发起人共 **199 条 `userNotExist`**。
