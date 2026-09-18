---
name: sellfox-automation
description: >
  操控赛狐 ERP (sellfox.com) 库存明细导出、其他出入库、备货单导入等网页流程。
  当用户提到"赛狐"、"Sellfox"、"库存明细"、"仓库导出"、"其他入库"、"其他出库"、
  "备货单"、"导出库存"、"隐藏0数据"等时触发。所有命令走 dispatcher。
  Sellfox 有正式 OpenAPI 的模块优先 API；网页能力保留给 API 不覆盖的场景。
compatibility: >
  需要仓库内网页能力舱（web_automation/ 子环境，Playwright + 可选 OCR）。
  Sellfox 是 Element UI (Vue)。持久化登录在 web_automation/sellfox-profile/。
metadata:
  module: sellfox-automation
  platform: Sellfox ERP (Element UI / Vue.js)
  account: fzh (克勇)
  stock_export_task: sellfox.stock.export
  updated: 2026-09-02
---

# 赛狐 ERP 网页自动化

## 一句话触发（给同事）

| 你想做什么 | 就说 |
|-----------|------|
| 导出库存明细备份 | "**赛狐导出库存**" |
| 其他入库 | "**赛狐其他入库**" |
| 其他出库清零 | "**赛狐其他出库**" |
| 海外仓备货单导入 | "**赛狐导入备货单**" |

Agent 统一执行（勿改路径/venv）：

```bash
# 读操作（API 优先）：先 --check
uv run python web_automation/scripts/dispatch.py sellfox.stock.export --check
uv run python web_automation/scripts/dispatch.py sellfox.stock.export

# 写操作：必须先确认范围，再带 --confirm-scope（值必须是用户确认的文件/SKU/仓库）
uv run python web_automation/scripts/dispatch.py sellfox.other-outbound.import \
  --confirm-scope "用户确认的具体范围" -- <文件>
uv run python web_automation/scripts/dispatch.py sellfox.restock.import \
  --confirm-scope "用户确认的具体范围" -- <文件>
```

**范围规则**：写操作默认只许用用户明确确认的测试/目标商品；绝不扩大到全量。赛狐导入是
Vue/Element UI 页面，dispatcher 在导入前会确认范围、修改后会导出对照。

## Hard Constraints

- Sellfox 是 **Element UI (Vue)**，永远不用 ExtJS togglebutton 模式。
- 导出按钮是纯图标 `.icon_sf_download`，不用 `text=导出` 搜索。
- SPA 导航后等 5–8 秒再操作。
- 定位 dialog 必须过滤可见：页面有 20+ 隐藏 `.el-dialog__wrapper`，用
  `filter(w => w.getBoundingClientRect().width > 0)`。
- **库存修改铁律**：涉及库存数量/成本修改（其他入库/出库/备货）**必须**先导出库存明细备份，
  修改后再导出一次对照验证；零库存 SKU 也有成本，备份导出要取消"隐藏0数据记录"。
- **MCP 先探路**：新页面/新功能先 MCP 截图+snapshot+evaluate 探路，禁止凭猜 URL。

## 常用选择器

- 搜索类型切换：`input.el-input__inner` 值 ∈ {SKU,识别码,品名,型号,FNSKU,SPU,款名,MSKU}；
- 精/模：`.icon_sf_fuzzy` 存在 = fuzzy；
- 导出触发：`.icon_sf_download.f_18` → 弹窗点"确定" → 出现"立即下载"后 `expect_download`；
- 隐藏 0 数据：`span:text-is("隐藏0数据记录")`（取消勾选导出全量）。

## API vs 浏览器

`sellfox.stock.export` 是 API 优先（`--api`，用持久化 cookie 调 HTTP），
认证/参数/业务错误**禁止**静默回退浏览器；仅"端点缺失/不支持/服务不可用"才回退，
且回退由 dispatcher 判定。`sellfox_restock_api.py` 属私有网页 cookie API，
与正式 Sellfox OpenAPI（SELLFOX_API/）不是一回事，不可混用。

## 登录

默认人工首次登录并持久化 cookie 到 `web_automation/sellfox-profile/`；
`--auto-login` 需要 ddddocr（OCR 可选，用户明确要求才 `--with-ocr`），未装则降级人工。
