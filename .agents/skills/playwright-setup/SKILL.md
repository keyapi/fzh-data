---
name: playwright-setup
description: >
  网页自动化环境就绪检查与修复：先跑 doctor/bootstrap，不要求用户理解 venv 或 Chromium。
  当用户提到"设置自动化环境"、"检查环境"、"装 Playwright"、"浏览器打不开"、
  "首次使用"、"帮我装环境"、"NEED_BROWSER"等时触发。
compatibility: >
  fzh-data 仓库：网页能力舱在 web_automation/（独立 uv 子项目）。root uv sync 不装浏览器。
metadata:
  module: playwright-setup
  updated: 2026-09-02
---

# 网页自动化环境就绪（单仓库）

## 一句话触发（给同事）

| 你想做什么 | 就说 |
|-----------|------|
| 检查网页自动化环境 | "检查自动化环境" |
| 首次准备网页任务 | "准备浏览器环境" |
| 浏览器装不上/打不开 | "浏览器有问题" |

## 标准流程（Agent 按序执行）

```bash
# 1) 环境体检（只读）：uv / web_automation/.venv / playwright / Chromium / OCR / profile
uv run python web_automation/scripts/doctor.py

# 2) 需要时再初始化子环境 + Chromium（幂等）
uv run python web_automation/scripts/bootstrap.py

# 3) 如需 OCR 全自动登录（可选，先问用户），再加 OCR 组
uv run python web_automation/scripts/bootstrap.py --with-ocr
```

**硬规则**：
- 普通同事只需 clone 后 `uv sync`（根环境），网页任务触发时 bootstrap 自动准备 `web_automation/.venv`。
- 不要求用户手动配注册表/环境变量/Visual Studio Build Tools。
- 系统级缺失（如 Windows VC++ 运行库、PowerShell 7）只报告，向用户确认后再装。
- `doctor.py` 全只读；`bootstrap.py` 只在明确运行时才安装。

## 状态对照

| doctor/bootstrap 状态 | 含义 | 处理 |
|------|------|------|
| `READY` | 环境+Chromium 就绪 | 直接执行任务 |
| `NEED_BROWSER` | 子环境或 Chromium 未装 | 跑 `bootstrap.py` |
| `NEED_OCR` | 请求了 OCR 但未装 | `bootstrap.py --with-ocr` |
| `BLOCKED` | uv 缺失等 | 报告用户，别绕过 |
