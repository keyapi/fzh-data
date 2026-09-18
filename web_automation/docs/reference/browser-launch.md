---
okf: v0.1
type: Reference
title: 浏览器启动统一出口（browser_launch）
description: 用环境变量决定 Playwright 走 bundled chromium 还是系统 Chrome、有头还是无头；解决本机有头模式起不来的问题
tags: [web-automation, playwright, chromium, browser, reference]
resource: web_automation/legacy-compatible/browser_launch.py
---

# 浏览器启动统一出口

`web_automation/legacy-compatible/browser_launch.py` 是 Playwright 启动浏览器的**统一出口**。

## 为什么有这层

本机 **bundled chromium 的「有头」模式起不来**：

| 现象 | 证据 |
|---|---|
| `spawn UNKNOWN` | chromium-1234/1200 有头启动直接抛错 |
| 沙箱拒绝访问 | chromium-1228 报 `Sandbox cannot access executable … 拒绝访问。(0x5)` |
| 系统 Chrome 正常 | `channel="chrome"` 有头/无头都起得来（实测 151.0.7922.x） |
| headless 正常 | bundled chromium 无头也起得来 |

怀疑与企业安全软件有关（同一二进制时好时坏、报 SxS 清单错与访问拒绝两种）。各脚本原先**内联**写死
`p.chromium.launch_persistent_context(headless=False)`，既没地方统一改、也留不下开关，于是把这些脚本
在本机判了死刑。

## 两个环境变量

**都不设时，行为与不经过本模块完全一致**（bundled chromium + 脚本自己传的 `headless`）——已用反向验证确认。

| 变量 | 取值 | 效果 |
|---|---|---|
| `WEB_AUTOMATION_BROWSER_CHANNEL` | `chrome` / `msedge` / `chromium` | 走 playwright 的 `channel=`，即本机已装的浏览器 |
| `WEB_AUTOMATION_HEADLESS` | `1/true/yes/on` → 强制无头；`0/false/no/off` → 强制有头 | 覆盖脚本自己传的 `headless` |

无法识别的 `WEB_AUTOMATION_HEADLESS` 取值会被**忽略**（退回脚本自带值），不会静默变成 True。

## 用法

脚本侧：

```python
from browser_launch import launch_persistent

with sync_playwright() as p:
    context = launch_persistent(
        p, PROFILE_DIR, headless=False,
        accept_downloads=True,
        viewport={"width": 1400, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
```

参数与 playwright 原方法一致，只是 `user_data_dir` 改成位置参数（内部会 `str()` 化）。
每次启动会打一行日志，排障时能确认「这次用了哪个浏览器、有头还是无头」：

```
[browser] channel=chrome headless=False profile=D:\...\web_automation\chrome-profile
```

命令行侧（本机跑通途导出）：

```bash
WEB_AUTOMATION_BROWSER_CHANNEL=chrome \
  uv run python web_automation/scripts/dispatch.py tongtu.orderdetail.export \
  -- --range-start 2026-09-11 --range-end 2026-09-17 --auto-login
```

## 迁移状态

**已迁移（通途族，5 处调用）**：`tongtu_orderdetail_report.py`、`tongtu_sales_report.py`、
`tongtu_login_ocr.py`、`tongtu_auto_export.py`（2 处）。

**未迁移（赛狐族与通用，约 15 处）**：仍在各自脚本里内联 `launch_persistent_context`。
这些流程**尚未在本机实测**，盲改有风险，故留作后续；迁移时把内联调用换成
`launch_persistent(p, PROFILE_DIR, headless=..., ...)` 即可，并保持参数逐项一致。

> 迁移前注意：`click-based/` 与 `legacy-compatible/` 下**同名脚本是两份拷贝**，
> 且它们只 import 同目录的兄弟模块（`dispatch.py` 用 `cwd=REPO_ROOT` 起脚本但**不设 `PYTHONPATH`**，
> 所以 `sys.path[0]` 只有脚本所在目录）。因此 `browser_launch.py` 放在 `legacy-compatible/`；
> 若要让 `click-based/` 复用，需要各自放一份或显式加路径。

## 验证

- 单测：`uv run python -m pytest tests/web_automation/test_browser_launch.py -q`
- 正例：带上 `WEB_AUTOMATION_BROWSER_CHANNEL=chrome` 跑 `tongtu.orderdetail.export` → 应见 `[browser] channel=chrome` 并导出成功
- 反例：不带环境变量 → 本机应仍以 `spawn UNKNOWN` 失败（证明默认行为没被改动）
