---
name: web-automation
description: >
  仓库内网页自动化能力舱统一入口：通途/赛狐/通用浏览器任务都先跑
  web_automation/scripts/dispatch.py 拿确定状态，再按状态执行。
  当用户提到"浏览器自动化"、"Playwright"、"通途导出"、"赛狐导出"、"备货单导入"、
  "库存导出"、"自动登录"、"验证码"、"cookie"、"下载文件"、"浏览器"等时触发。
  本 skill 是路由总纲；平台专项见 tongtu-automation / sellfox-automation。
compatibility: >
  依赖 fzh-data 仓库结构：web_automation/ 是独立 uv 子项目，root uv sync 不会装浏览器。
  首次网页任务由 dispatcher/bootstrap 自动建子环境 + Chromium。
metadata:
  module: web-automation
  updated: 2026-09-02
---

# 网页自动化统一入口

## 硬规则（Agent 必须遵守）

1. **任何网页任务先跑 dispatcher 的 `--check`**，不要自己猜 Python 环境、脚本路径或 venv。
2. dispatcher 输出状态字面执行：
   - `READY` → 继续下一步 / 直接执行；
   - `NEED_BROWSER` → 运行 `uv run python web_automation/scripts/bootstrap.py` 建子环境 + Chromium；
   - `NEED_LOGIN` → 浏览器打开后人手动登录（首次登录优先人工并持久化 profile）；
   - `NEED_OCR` → 说明 OCR 可选，先问用户，需要才 `--with-ocr`；
   - `NEED_USER_CONFIRMATION` → 必须先让用户确认具体文件/SKU/仓库范围，再带 `--confirm-scope "..."`；
   - `BLOCKED` → 停止并把原因告诉用户，不要绕过。
3. **不直接运行 `web_automation/legacy-compatible/*.py`**，除非 dispatcher 明确给出了该命令。
4. OCR（ddddocr）不是默认安装；只有用户明确要"全自动登录/识别验证码"才加 `--with-ocr`。
5. 新页面/新功能先用 Playwright MCP 探路（snapshot + evaluate），确认选择器后再沉淀 Python。

## 常用命令模板

```bash
# 检查某个网页任务的状态（读操作，安全）
uv run python web_automation/scripts/dispatch.py <task> --check

# 正式执行（dispatcher 会先 bootstrap；写操作必须先有 --confirm-scope）
uv run python web_automation/scripts/dispatch.py <task> --confirm-scope "用户确认的范围" -- <透传参数>

# 环境体检（只读，不安装）
uv run python web_automation/scripts/doctor.py
```

任务名（`web_automation/capabilities.yaml`）：
`tongtu.stock.export` / `tongtu.sales.export` / `sellfox.stock.export` /
`sellfox.other-inbound.import` / `sellfox.other-outbound.import` /
`sellfox.restock.import` / `web.generic.explore`。

## 通用浏览器模式

- **选择器优先级**：CSS 属性选择器 > ID+文字 > ref > 纯文字。
- **登录检测**：找仅在登录后出现的特征元素（通途 `#warehouseDisableDiv`、赛狐 URL 离开 login）。
- **下载**：Python 用 `page.expect_download()`；MCP 下载落在 `.playwright-mcp/`。
- **批量操作**：每步切仓库/翻页后等 5–8 秒（ExtJS/Vue 渲染慢）。
- 详细踩坑见 tongtu-automation / sellfox-automation 及其 references。

## 参考

- [playwright-setup](../playwright-setup/SKILL.md)
- [tongtu-automation](../tongtu-automation/SKILL.md)
- [sellfox-automation](../sellfox-automation/SKILL.md)
