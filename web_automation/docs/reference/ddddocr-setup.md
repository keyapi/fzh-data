---
okf: v0.1
type: Reference
title: ddddocr + onnxruntime 安装指南
description: ddddocr 验证码识别库的安装、onnxruntime 版本兼容性、各平台踩坑与解决方案
tags: [ddddocr, onnxruntime, setup, windows, macos, linux, captcha, ocr]
timestamp: 2026-07-09
last_updated: 2026-07-09
---

# ddddocr + onnxruntime 安装指南

## 基本安装

```bash
uv add ddddocr onnxruntime Pillow
```

ddddocr 依赖 onnxruntime 加载深度学习模型（~70MB），首次识别时加载模型需 3-5 秒，后续调用秒出。

## onnxruntime 版本兼容性

| Python | onnxruntime | 说明 |
|--------|------------|------|
| 3.10 | `1.16.3` + `numpy<2` | fzh-data Selenium 路径锁死版本 |
| 3.12 | `1.20.1` ~ `1.27.0` | 1.16.3 无 cp312 wheel，uv 自动拉 1.27.0 |
| 3.13 | `>=1.21.0` | 1.20.x 无 cp313 wheel |

> **本项目的 Python 版本**：pyproject.toml 要求 `>=3.9`，uv 自动选择已安装的最高版本。CI/Build 环境可能出现与本地不同的 Python 版本。

## 平台踩坑

### Windows

**问题 1: `DLL load failed` (onnxruntime 1.23.x)**

```
ImportError: DLL load failed while importing onnxruntime_pybind11_state
```

- **原因**：onnxruntime 1.23.x 在 Windows 上原生 DLL 加载失败（缺少 VC++ 运行时依赖）
- **fzh-data 方案**（Python 3.10）：`uv add "onnxruntime==1.16.3" "numpy<2"`
- **本项目方案**（Python 3.12+）：onnxruntime 1.27.0（推测新版已修复），若仍报错降到 1.18.x

```bash
# 降级方案（如果 1.27.0 报 DLL 错误）
uv add "onnxruntime==1.18.0"
```

**问题 2: 缺少 VC++ 运行库**

ddddocr 的 ONNX 模型加载依赖 Microsoft Visual C++ Redistributable。若未安装，OCR 调用会静默失败。

- 下载：[Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- 安装后重启命令行

**问题 3: Windows 中文编码**

脚本输出中文可能乱码。本项目已在 `tongtu_login_ocr.py` 和 `sellfox_login_ocr.py` 中添加：

```python
sys.stdout.reconfigure(encoding='utf-8')
```

### macOS

ddddocr 支持 macOS（Apple Silicon / Intel），但 onnxruntime 的 wheel 可用性取决于 Python 版本：

```bash
# Apple Silicon (arm64)
uv add ddddocr onnxruntime Pillow

# 如果报错，尝试指定 onnxruntime 版本
uv add "onnxruntime>=1.20.1"
```

> macOS 上 onnxruntime 通过 Rosetta 2 或原生 arm64 wheel 运行。Apple Silicon 优先使用原生 wheel。

### Linux

```bash
uv add ddddocr onnxruntime Pillow
```

Linux 环境通常无版本兼容问题。若 Docker/CI 环境缺少系统库：

```bash
apt-get install -y libgl1-mesa-glx libglib2.0-0
```

## 验证安装

```bash
# 测试 ddddocr 能否正常加载
python -c "import ddddocr; ocr = ddddocr.DdddOcr(); print('OK')"

# 测试验证码识别（需先准备验证码图片）
uv run python test_ocr.py captcha.png
```

如果 `import ddddocr` 成功但 `DdddOcr()` 挂起或崩溃 → onnxruntime DLL 问题，检查 VC++ 运行库。

## 降级策略

自动登录采用**三级 fallback** 架构，确保任何依赖状态都有可操作的路径：

| 层级 | 条件 | 行为 |
|------|------|------|
| Level 1 | ddddocr 可用 | 自动 OCR 识别验证码 |
| Level 2 | ddddocr 不可用（未安装/VC++ 缺失） | terminal 提示用户手动输入验证码（浏览器中可见验证码图片） |
| Level 3 | ddddocr_login.py 整个模块缺失 | 打开浏览器，用户手动填表登录 |

如果自动登录一直失败（OCR 识别率低或持续报错），可临时关闭自动登录：

```bash
# 不加 --auto-login，使用人工登录
uv run python tongtu_auto_export.py
```

主脚本在 ddddocr 不可用时自动降级，不会崩溃。降级时会打印明确的修复提示：

```
# ddddocr 未安装
ddddocr 未安装，将使用 terminal 手动输入验证码
修复: uv add ddddocr onnxruntime

# onnxruntime / VC++ 缺失
ddddocr 加载失败（可能缺少 VC++ 运行库）: DLL load failed
修复: 安装 Microsoft Visual C++ Redistributable
```

> 详见 [login-fallback-design.md](../lessons/login-fallback-design.md) — 完整架构设计文档。

## 相关文档

- [tongtu-captcha-ocr.md](tongtu-captcha-ocr.md) — WX 的 CDP + ddddocr 方案
- [ddddocr-login-pitfalls.md](../lessons/ddddocr-login-pitfalls.md) — 自动登录踩坑汇总
- [ddddocr-playwright-login-fixes.md](../solutions/integration-issues/ddddocr-playwright-login-fixes.md) — 全修复验证记录
- [ddddocr GitHub](https://github.com/sml2h3/ddddocr)
- [onnxruntime 版本列表](https://pypi.org/project/onnxruntime/#history)
