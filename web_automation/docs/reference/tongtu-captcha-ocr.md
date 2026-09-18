---
okf: v0.1
type: Reference
title: 通途验证码自动识别 — ddddocr 方案
description: 使用 ddddocr 深度学习 OCR 自动识别通途登录验证码，实现全自动登录导出
tags: [tongtu, ddddocr, captcha, ocr, login, cdp]
timestamp: 2026-07-08
contributor: wangxian-fzh
---

# 通途验证码自动识别（ddddocr）

## 概述

通途登录页有图形验证码，此前需手动输入。WX（wangxian-fzh）使用 ddddocr 深度学习 OCR 实现了验证码自动识别，结合 CDP 浏览器完成了通途全自动登录 + 导出。

## 两种实现路径

| 路径 | 工具 | 适用环境 | 脚本 |
|------|------|---------|------|
| Playwright | 项目原生 Playwright MCP | Windows/Linux 通用 | `tongtu_auto_export.py`（已有） |
| CDP + ddddocr | CodeBuddy computer-use CDP 浏览器 | WorkBuddy / CodeBuddy | `tongtu_export_ocr.py`（本次新增） |

## CDP 路径（WX 贡献）

### 依赖

```bash
uv add ddddocr Pillow onnxruntime
```

> **onnxruntime 版本踩坑**（参考 fzh-data `SPS_Selenium_Local/requirements.txt:21`）：
> - **问题**：onnxruntime 1.23.x 在 Windows 上加载原生 DLL 失败（`DLL load failed`）
> - **fzh-data 方案**：Python 3.10 锁死 `onnxruntime==1.16.3` + `numpy<2`
> - **本项目现状**：Python 3.12 下 onnxruntime 1.16.3 无 cp312 wheel，只能使用 >= 1.20.1。uv 自动安装 1.27.0。推测新版已修复 DLL 问题，若 Windows 上报 `DLL load failed`，可尝试降 onnxruntime 到 1.18.x（最早支持 cp312 的版本）

### 使用方法

```bash
# 1. 设置环境变量（必须）
export TONGTU_USER="your-email@example.com"
export TONGTU_PASSWORD="your-password"

# 2. 运行
uv run python tongtu_export_ocr.py
```

### 工作原理

1. CDP 浏览器导航到通途登录页
2. 截图获取验证码 → ddddocr 识别（最多 5 次重试）
3. 填入用户名、密码、识别结果 → 点击登录
4. 登录成功后切换 6 个仓库逐一导出 Excel
5. 调用 `merge_inventory.py` 合并

### 脚本清单

| 文件 | 说明 |
|------|------|
| `tongtu_export_ocr.py` | 主脚本：CDP + ddddocr 全自动登录导出 |
| `test_ocr.py` | 独立 OCR 测试：`python test_ocr.py captcha.png` |
| `cdp-based/export_via_cdp.py` | CDP 浏览器仓库导出（不含 OCR 登录） |
| `cdp-based/get_captcha.py` | 验证码获取 + 识别实验脚本 |
| `cdp-based/test_captcha_ocr.py` | 从 CDP 浏览器提取验证码并识别 |
| `一键运行_调试.cmd` | Windows 一键运行脚本（调试版，保留报错信息） |

### 已知限制

- CDP 路径依赖 CodeBuddy/WorkBuddy 的 `computer-use` skill（`/root/.codebuddy/skills/computer-use/scripts/computer_tool.py`）
- 该工具仅在 WorkBuddy 环境中可用，不兼容标准 Playwright 环境
- 验证码识别成功率约 80%（简单数字验证码），重试机制可提升到 95%+

## 参考

- [ddddocr-setup.md](ddddocr-setup.md) — ddddocr + onnxruntime 安装指南（各平台踩坑）
- [ddddocr GitHub](https://github.com/sml2h3/ddddocr)
- [fzh-data SPS_Selenium_Local/sellfox_login.py](https://github.com/keyapi/fzh-data)——赛狐版 ddddocr 登录（Selenium 路径）
