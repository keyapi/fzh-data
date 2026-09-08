---
okf: v0.1
type: Reference
title: 通途订单详情统计月度导出（tongtu.orderdetail.export）
description: 从浏览器自动化导出通途「订单详情统计」全量自发货订单：背景、MCP 探路过程、选择器/动作序列、踩坑与核验结果
tags: [web-automation, tongtu, orderdetail, export, reference]
resource: web_automation/legacy-compatible/tongtu_orderdetail_report.py
---

# 通途订单详情统计月度导出

## 背景 / 为什么

财务/运营需要按月导出通途 ERP2.0 的「订单详情统计」——**全渠道/全账号、自发货订单、按发货时间整月**
的订单明细（用于月度对账/成本复核）。此前只能人工在网页里设置过滤并点导出，无法复现、无脚本、无留存。

本次沉淀为可复用能力：**`tongtu.orderdetail.export`**（BROWSER_ONLY / read），一条命令导一整月。
目标页：`https://erp102.tongtool.com/statisticsreport/orderdetail/index.htm`

### 过滤语义（用户口径，已固化）

- 渠道 = 全部、账号 = 全部、销售模式 = 全部、是否JIT备货 = 全部；页面其余下拉（订单类型/物流商/邮寄方式/品类/发货仓库/开发/询价/listing责任人/SKU/品牌/包裹号/跟踪号/物流商单号/订单状态 等）也全部保持页面默认「全部」
- 时间用 **发货时间**（默认即发货时间；不用付款时间/商品生成时间）
- 数据来源 = **自发货订单**（页面默认即自发货订单）

## 用法

```bash
# 一键整月（先跑 dispatch 拿状态；--auto-login = ddddocr 全自动登录）
uv run python web_automation/scripts/dispatch.py tongtu.orderdetail.export -- --month 2026-07 --auto-login

# 小范围验证（覆盖 --month）
uv run python .../tongtu_orderdetail_report.py --range-start 2026-07-01 --range-end 2026-07-01

# 直接跑脚本（等价，等价于 dispatcher 的命令）
uv run --project web_automation python web_automation/legacy-compatible/tongtu_orderdetail_report.py --month 2026-07
```

- 首次运行建 `web_automation/chrome-profile/`（cookie 持久化）；cookie 过期后 `--auto-login` 用 OCR 自动续登
- OCR 依赖：`uv sync --project web_automation --group ocr`；凭据只放 gitignored `web_automation/.env`
- 产出：`web_automation/downloads/订单详情统计_YYYYMM_YYYYMMDD_HHMMSS.zip`（gitignored，不入库）

## 过程（MCP 探路 → 沉淀）

1. Playwright MCP 打开目标页（登录后可见）→ 确认日期域、下拉、导出按钮、结果列表。
2. 用探路结果写脚本，骨架完全仿 `tongtu_sales_report.py`（登录分层/下载/失败码契约）。
3. 实测整月导出并核验。

### 页面结构（探路确认）

- 顶部过滤区：`渠道` 勾选组（默认含「全部」）、`账号` 下拉、`销售模式`/`是否JIT备货` 组；`发货时间` 单选默认选中，其后 从/到 两个 My97 日期框
- `数据来源` = 自发货订单（默认）
- 下方 tab：**数据查询**（明细网格）/ **统计导出**（历史统计任务列表 + 「统计」入口）
- 统计导出历史表列：统计条件 / 提交用户 / 提交时间 / 统计结果（含「点击下载统计结果」）/ 操作

## 选择器 / 动作序列

| 动作 | 选择器 / 说明 |
|---|---|
| 日期 从/到 | `input[name='shipTimeFrom']` / `input[name='shipTimeTo']`，直接 `.fill()`，**不按 Enter** |
| 应用过滤 | 切到「数据查询」tab 后点 `a[onclick='queryInfo()']` |
| 提交统计 | 切「统计导出」→ 点 `a[onclick='openConfirmWin()']`（「统计」）→ 弹窗里点 `提交` |
| 轮询新结果 | 记录提交前/后已有 `a:has-text('点击下载统计结果')` 的 href → 往返 数据查询/统计导出 tab 强制刷新 → 出现新 href 即完成 |
| 下载 | 对 href 用 `page.expect_download()`（大 timeout）点链接 `save_as` |

登录检测：`body` 含 `编号：`。跳转离开报表页（如刚登录落在首页）需重开 ORDERDETAIL_URL 再设筛选。

## 踩坑（探路 + 实测）

1. **日期框 My97：`.fill()` 后按 Enter 会整页刷新并重置为默认日期**——只 fill，不要按 Enter。
2. **填日期会弹出 My97 日历 iframe，拦截后续点击**（如「查询」）——填完先让日历收起再点查询。
3. **「查询」按钮只在「数据查询」tab 可见**——先 `switch_tab('数据查询')` 再点 `queryInfo()`；统计导出 tab 下该按钮隐藏。
4. **统计任务状态不自动刷新**——提交后需往返 数据查询/统计导出 两 tab 强制刷新，新结果才会出现。
5. **下载基线要在提交后采集**：提交前历史表可能还没加载完（曾拿到 0 条，把历史里旧任务误当新结果）。改为提交后等 ~3s 再取现有 href 集合。
6. 提交互斥：同页面统计生成中不能再提交（脚本最多重试 3 次）。
7. 网格（数据查询）不要滚动全量加载；只操作「统计导出」列表。
8. 文件名自己带（`订单详情统计_<月>_<时间>.zip`），不信 `suggested_filename`（GBK 乱码坑）。

## 结果核验（2026-07 实测）

- 产出：`web_automation/downloads/订单详情统计_202607_20260908_153332.zip` ≈ **4.85 MB**
- 内部 xlsx 元数据块后表头自 **第 30 行** 起、**91 列**；**9604 行**
- 发货日期 `min=2026-07-01` / `max=2026-07-31`；数据来源 = 自发货订单
- 统计耗时约 51s

## 关联

- 能力注册：`web_automation/capabilities.yaml` `tongtu.orderdetail.export`；路由在 `scripts/dispatch.py` + `runtime.py`
- Skill：`.agents/skills/tongtu-automation/SKILL.md`、`.agents/skills/web-automation/SKILL.md`
- 模板/同族：`legacy-compatible/tongtu_sales_report.py`；登录复用 `legacy-compatible/tongtu_login_ocr.py`
