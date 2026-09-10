# web_automation — 网页自动化能力舱（Agent 参考）

Agent 参考（OKF 文档见 [docs/index.md](docs/index.md)；`click-based/AGENT_HANDOFF.md` 管 click-based 写流程）。
统一入口路由：**任何通途/赛狐/通用浏览器任务，先跑**
`uv run python web_automation/scripts/dispatch.py <task> --check`，按状态字面执行
（`READY`/`NEED_BROWSER`/`NEED_LOGIN`/`NEED_OCR`/`NEED_USER_CONFIRMATION`/`BLOCKED`）。**不要**自己拼路径/venv/OCR。

## 模块职责

把网页自动化（Playwright，持久化登录）从 `fzh-web-automation` 独立能力舱迁入 fzh-data：
通途/赛狐报表导出、通途订单详情统计月度导出、写流程（备货单/出库等导入）的浏览器自动化基座。
能力与路由在 `capabilities.yaml`（`runtime.py` 读、`dispatch.py` 执行）。

## 环境与登录

- 独立 uv 子项目：子环境 `web_automation/.venv`；首次 `uv run python web_automation/scripts/bootstrap.py`（建环境+Chromium），体检 `doctor.py`。
- OCR 全自动登录（ddddocr）：`uv sync --project web_automation --group ocr`；脚本加 `--auto-login`。
- 凭据只放 `web_automation/.env`（gitignored）→ `TONGTU_USER`/`TONGTU_PASSWORD`（通途）、
  `DINGTALK_USER`/`DINGTALK_PASSWORD`（钉钉 aflow，账号密码登录免扫码），绝不入库、不进命令行。
- 持久化登录 cookie：`web_automation/chrome-profile/`（gitignored）。登录识别：body 含 `编号：`。
- OCR 不可用自动降级半自动：自动填账号密码，验证码留人工在窗口输入。

## 常用任务（dispatcher-first）

| 任务 | 脚本 | 说明 |
|---|---|---|
| `tongtu.stock.export` | `legacy-compatible/tongtu_auto_export.py` | 通途库存结存导出 |
| `tongtu.sales.export` | `legacy-compatible/tongtu_sales_report.py` | 销售及库存报表导出 + 按仓分表 |
| **`tongtu.orderdetail.export`** | `legacy-compatible/tongtu_orderdetail_report.py` | 订单详情统计月度导出（详情见下） |
| `sellfox.stock.export` | `legacy-compatible/sellfox_auto_export.py --api` | 赛狐库存（API-first） |
| **`dingtalk.aflow.receipt.export`** | `legacy-compatible/dingtalk_aflow_receipt.py --mode excel` | 钉钉 aflow 销售收款确认单导出 Excel（详情见下） |
| **`dingtalk.aflow.receipt.attachments`** | `legacy-compatible/dingtalk_aflow_receipt.py --mode attachments` | 按导出表补**离职发起人**附件（API `userNotExist` 那批） |
| `web.generic.explore` | Playwright MCP | 新页面探路（snapshot+evaluate 后沉淀 Python） |

## 钉钉 aflow 销售收款确认单导出（背景/过程/结果摘要）

- **背景/为什么**：财务每期要从钉钉 aflow「OA审批管理后台」手工导出销售收款确认单单据为 Excel。
  附件侧已有 API 路径（`dingtalk/dingtalk_oa_approval/fetch_attachments.py`），唯一盲区是离职发起人
  （标准下载接口 `userNotExist`），aflow 以在职管理员身份访问可覆盖。
- **过程**：MCP 探路 → 沉淀脚本 → 注册 `dingtalk.aflow.receipt.export`。选择器/动作/踩坑见
  `docs/reference/aflow-receipt-export.md`。
- **结果（2026-09-10 实测核验）**：窗口 2026-07-04~09-09 → **405 行 / 265 单据**（单据数按唯一 `数据id` 计），
  发起时间全在窗口内；产物 232 KB；`数据id` 与 API `instance_ids.json` **265/265 重合**。
- **用法**：`uv run python web_automation/scripts/dispatch.py dingtalk.aflow.receipt.export -- --from 2026-07-04 --to 2026-09-09`
- **附件**：`--mode attachments` 按导出表补**离职发起人**附件
  （`dispatch.py dingtalk.aflow.receipt.attachments`）。
  走 `pchomepage.htm#/plainapproval?procInstId=<数据id>` 详情页点文件名下载；
  落 `<out>/dingtalk_oa_approval_data/aflow_attachments/<数据id>/` + manifest，可续传。
  **注意**：批量附件（hover「仅导出审批单附件」）产物进钉盘、取不回本地；
  导出表里的 `#/previewAttachments` 深链**需钉钉客户端**，浏览器里打不开 —— 别走错。
  实测对 39 个离职单据 39/39 成功，其中 **38 单是 API `userNotExist`** 的。

## 订单详情统计导出（背景/过程/结果摘要）

- **背景/为什么**：财务/运营按月导出通途「订单详情统计」全量自发货订单。原无脚本，纯手工页面导出。
  需沉淀为可复用能力，供 `--month YYYY-MM` 一键整月。
- **过程**：MCP 探路 orderdetail 页确认选择器与动作序列 → 沉淀脚本（仿 `tongtu_sales_report.py`）
  → 注册 `tongtu.orderdetail.export`。选择器/动作/踩坑见
  `docs/reference/orderdetail-export.md`。
- **结果（2026-07 实测核验）**：`downloads/订单详情统计_202607_*.zip` ≈4.85 MB；
  xlsx 表头自第 30 行起、91 列；**9604 行**；发货日期 **2026-07-01 ~ 07-31**；数据来源=自发货订单。
- **用法**：`uv run python web_automation/scripts/dispatch.py tongtu.orderdetail.export -- --month 2026-07 --auto-login`

## 踩坑速查（通途）

- 日期域 My97：`.fill()` 后**勿按 Enter**（整页刷新重置）；填值弹出日历 iframe 会拦截点击 → 需先关闭。
- 「查询」`a[onclick='queryInfo()']` 只在 **数据查询** tab 可见 → 先切 tab。
- 统计页结果不自动刷新 → 提交后往返 数据查询/统计导出 两 tab 轮询。
- 下载结果识别：按**最上行 = 本次提交**锚定（历史表按提交时间倒序）。数据表是 header（含「统计条件」th）后 `following::table[1]`，非 sibling；首行空 spacer 须跳过；行文本最后一个 datetime = 提交时间。提交前记最上行提交时间 → 提交后往返 tab → 最上行提交时间一变即锁本次行 → 等该行下载链接。
- 文件名自带（不信 suggested_filename 的 GBK）。
- 「查询」失败必须中止（`FAILURE_CODE=QUERY_FAILED`），勿带默认日期继续提交。
- 统计任务提交互斥（生成中不能再提交）；非互斥打不开弹窗用 `SUBMIT_FAILED`。

## 文档指针

- `docs/index.md` — 模块文档导航
- `docs/reference/capability-matrix.md` — 能力矩阵/风险/回退/验证
- `docs/reference/orderdetail-export.md` — 订单详情统计导出专题（选择器/流程/踩坑/核验）
- `docs/reference/tongtu-pitfalls.md` · `sellfox-pitfalls.md` — 平台踩坑
- `scripts/scheduling-exports` 见 `docs/reference/scheduling-exports.md`
