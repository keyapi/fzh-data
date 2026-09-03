---
okf: v0.1
type: Reference
title: 关键技术决策 — uv/Playwright/MCP 架构选型
description: fzh-web-automation 项目的关键技术决策及放弃方案
tags: [uv, playwright, mcp, architecture, cookie, persistent-context]
timestamp: 2026-05-25
---

# 关键技术决策

## 1. uv 环境隔离（非 pip）

uv 比 pip 快 10x，自动管理 venv。同事可能有不同 Python 项目的冲突依赖，uv 隔离开。`pyproject.toml` 声明依赖，`uv sync` 一键安装。

## 2. Playwright persistent_context（非 CDP attach）

**最终方案**：`chromium.launch_persistent_context(user_data_dir="chrome-profile/")`

- Playwright 自己管理 Chromium 实例
- cookies/localStorage 持久化到磁盘
- 首次手动登录，后续免登录
- **放弃的方案**：`chrome.exe --remote-debugging-port=9222` → CDP 端点不可达

## 3. Cookie 注入桥接（MCP ↔ Python）

MCP Playwright 使用独立浏览器实例，无法共享 chrome-profile。解决方案：
- Python 脚本 `--export-cookies` 提取解密 cookie → JSON
- MCP 会话 `browser_run_code` + `addCookies()` 注入
- passport 记住密码 cookie (username/password hash) 触发自动登录

## 4. 两种模式共存

| 模式 | 启动方式 | 适用 |
|------|---------|------|
| Python 脚本 | `uv run python tongtu_auto_export.py` | 日常定时，免登录 |
| MCP 对话 | Claude Desktop 对话 | 探索新页面，一次性操作 |

## 5. 文件结构约定

```
├── tongtu_auto_export.py      # 主脚本：浏览器自动化导出 + 生成导入 + 合并
├── generate_tongtu_import.py  # 数据转换：库存清单 → 5列导入模板
├── merge_inventory.py         # 独立合并脚本：多仓原始清单 → 单文件
├── inspect_warehouse.py       # 诊断工具：dump 通途页面 DOM 元素
├── mcp_to_output.py           # MCP 桥接：整理 MCP 下载文件
├── sellfox_auto_export.py     # 赛狐库存导出（浏览器+API 双模式）
├── sellfox_import_update.py   # 赛狐商品导入更新
├── sellfox_restock_api.py     # 海外仓备货单 API E2E
├── commodity_import_template.py # 商品导入模板下载器
├── chrome-profile/            # 持久化浏览器会话 (gitignore)
├── sellfox-profile/           # 赛狐持久化登录 (gitignore)
├── downloads/                 # 原始库存清单 (gitignore)
└── output/                    # 导入文件 + 合并文件 (gitignore)
```

## 6. 运行方式

```bash
# 日常使用（推荐）
uv run python tongtu_auto_export.py

# 强制重新登录
uv run python tongtu_auto_export.py --fresh

# 导出 cookies 供 MCP 使用
uv run python tongtu_auto_export.py --export-cookies
```
