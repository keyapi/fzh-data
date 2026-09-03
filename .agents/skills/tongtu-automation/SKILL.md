---
name: tongtu-automation
description: >
  操控通途 ERP (erp102.tongtool.com) 库存结存/销售报表导出与仓库切换。
  当用户提到"通途"、"Tongtu"、"tongtool"、"库存结存"、"导出库存"、"6个仓库"、
  "CENTRADE"、"exportExcelPage"、"togglebutton"、"通途销售报表"、
  "通途导出 cookie"等时触发。所有命令走 dispatcher。
compatibility: >
  需要仓库内网页能力舱（web_automation/ 子环境，Playwright）。通途是 ExtJS，
  持久化登录在 web_automation/chrome-profile/。
metadata:
  module: tongtu-automation
  platform: Tongtu ERP (ExtJS)
  task_stock: tongtu.stock.export
  task_sales: tongtu.sales.export
  profile_dir: web_automation/chrome-profile/
  updated: 2026-09-02
---

# 通途 ERP 库存/销售自动化

## 一句话触发（给同事）

| 你想做什么 | 就说 |
|-----------|------|
| 导出全部 6 仓库存 | "**通途导出库存**" |
| 导出销售报表 | "**通途销售报表**" |
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
