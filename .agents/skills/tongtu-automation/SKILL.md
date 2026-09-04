---
name: tongtu-automation
description: >
  操控通途 ERP (erp102.tongtool.com) 库存结存/销售报表导出与仓库切换，
  以及把导出挂成定时任务（每天/每 N 小时自动跑）。
  当用户提到"通途"、"Tongtu"、"tongtool"、"库存结存"、"导出库存"、"6个仓库"、
  "CENTRADE"、"exportExcelPage"、"togglebutton"、"通途销售报表"、
  "通途导出 cookie"、"定时导出"、"每天导出"、"自动定时"、"每 8 小时"、
  "多久导一次"等时触发。命令走 dispatcher / 调度脚本。
compatibility: >
  需要仓库内网页能力舱（web_automation/ 子环境，Playwright）。通途是 ExtJS，
  持久化登录在 web_automation/chrome-profile/。定时依赖系统调度
  （Windows schtasks 或 Linux/macOS cron，脚本在 web_automation/scripts/）。
metadata:
  module: tongtu-automation
  platform: Tongtu ERP (ExtJS)
  task_stock: tongtu.stock.export
  task_sales: tongtu.sales.export
  profile_dir: web_automation/chrome-profile/
  updated: 2026-09-03
---

# 通途 ERP 库存/销售自动化

## 一句话触发（给同事）

| 你想做什么 | 就说 |
|-----------|------|
| 导出全部 6 仓库存 | "**通途导出库存**" |
| 导出销售报表 | "**通途销售报表**" |
| 以后自动定期导 | "**以后每天导一次通途库存**" / "**每 8 小时自动导销售**" / "**每天凌晨 2 点导库存**" |
| 改频率 / 取消定时 | "**改成每天 3 点**" / "**取消通途定时**" |
| 强制重新登录 | "**通途重新登录**" |

Agent 统一执行（勿改路径/venv）：

```bash
# 0) 状态检查（安全，先做）
uv run python web_automation/scripts/dispatch.py tongtu.stock.export --check
# 1) 正式导出：READY 直接用；NEED_LOGIN 打开浏览器等人手动登录；
#    仅用户明确要 ddddocr 全自动登录才加 --with-ocr
uv run python web_automation/scripts/dispatch.py tongtu.stock.export
```

销售报表同理：task = `tongtu.sales.export`。导出文件落在 `web_automation/downloads/`，合并/导入文件在 `web_automation/output/`。

## 定时 / 重复导出（非技术同事说人话即可）

用户说"以后每天导一次 / 每 N 小时 / 每天几点"时，Agent 按固定流程走，**不要**让用户敲命令或背参数：

1. **判断是一次性还是定时**：句子里有"以后 / 每天 / 每 N 小时 / 定时 / 重复 / 每隔" → 定时；否则一次性走 dispatcher。
2. **定时前置自检**：跑 `uv run python web_automation/scripts/doctor.py`，确认子环境与 Chromium。定时要无人值守（7 天 cookie 过期后自动续登），**OCR 是必需的**——未装时告诉用户"要自动定期跑，得先装个自动识别验证码的小组件（约几十 MB），我帮你装"，然后 `uv sync --project web_automation --group ocr`；装不上（缺 VC++ 运行库等）如实说明并建议仍保持手动登录习惯。
3. **问清参数**：一次问清——导哪个（库存 / 销售 / 都要）+ 频率：每 N 小时（整数小时）或 每天几点（HH:MM）。自然语言转参数（**按 OS 分开，不要混用**）：
   - Windows："每 8 小时" → `-IntervalHours 8`；"每天凌晨 2 点" → `-AtTime "02:00"`。
   - Linux/macOS："每 8 小时" → `--every 8`；"每天凌晨 2 点" → `--at 02:00`。
   - 销售报表有"提交互斥"（提交后到生成前不能再提交），间隔建议 ≥ 1 小时，太短会撞车失败。
4. **注册**（在仓库根执行）：
   - Windows：`powershell -ExecutionPolicy Bypass -File web_automation/scripts/install_tongtu_schedule.ps1 -Task <stock|sales|both> <-IntervalHours N | -AtTime "HH:MM">`
   - Linux/macOS：`bash web_automation/scripts/install_tongtu_schedule.sh --task <stock|sales|both> [--every N | --at HH:MM]`
5. **改频 / 取消**：用户说"改成每天 3 点"→ 用新参数重跑一次脚本（会覆盖）；说"取消通途定时"→ 若曾注册过 stock+sales 两边，用 `-Task both -Remove` / `--task both --remove`，否则只删当前 task。
6. **注册后核对**（必须做，再告诉用户成功）：
   - Windows：`schtasks /Query /TN FZH-TongtuAutoExport-<task> /V /FO LIST`，确认 **Task To Run** 含 `dispatch.py`。
   - Linux/macOS：`crontab -l | grep FZH-Tongtu`，确认有对应 marker 行。
7. **收尾反馈**：任务名（`FZH-TongtuAutoExport-<task>`）、核对到的下次运行时刻、日志在 `web_automation/logs/`、以及"电脑要开机并登录才会跑"。
8. **首次 profile**：若还没有登录 profile（`web_automation/chrome-profile/` 不存在），先让用户跑一次一次性导出并登录，再注册定时，避免定时首跑卡在登录。

> 详细见 `web_automation/docs/reference/scheduling-exports.md`。

## Hard Constraints

- 通途是 **ExtJS**，永远不用 el-select/el-dialog 等 Element UI 选择器。
- 仓库选择器是自定义 togglebutton：未选中 `a.toggle_btn` / 选中 `a.toggle_btn_down`。
- 导出按钮用 `a[onclick="exportExcelPage()"]` 精确匹配（页面有 13 个同名"导出Excel"按钮）。
- 不在 `expect_download` with 块外调用 `download.save_as()`（会超时）。
- 切仓库后**至少等 8 秒**再操作（ExtJS grid 渲染慢）。
- 登录检测：`#warehouseDisableDiv` 可见 = 已登录。

## 核心选择器速查

| 元素 | 选择器 |
|------|--------|
| 仓库按钮(未选) | `#warehouseDisableDiv a.toggle_btn` |
| 仓库按钮(选中) | `#warehouseDisableDiv a.toggle_btn_down` |
| 导出 | `a[onclick="exportExcelPage()"]` |
| 仓库类型筛选 | `#allWarehouseTypeBtn a`（"全部(非FBA)"） |
| 仓库状态筛选 | `#statusBtn a`（"已启用"） |

通途 Bug：切仓库时显示已选中但数据未渲染 → **先切走再切回**。

## Excel 结构

库存清单第 4 行表头（SKU 等 19 列），末尾"数量总计/金额总计"**必须跳过**；
列映射 A=SKU → SKU/SKU别名，Q(17)=头程运费，S(19)=头程其它费。
导入文件 5 列，安全库存/头程报关费**留空 None**。

## 登录

默认人工首次登录（打开的浏览器手动登录一次，cookie 持久化到 `web_automation/chrome-profile/`）。
`ddddocr` 未装时脚本自动降级人工登录，不会崩溃。
