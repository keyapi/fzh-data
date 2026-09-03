---
okf: v0.1
type: Solution
title: Playwright + ddddocr 自动登录 — 通途 & 赛狐 全修复验证
date: 2026-07-09
last_updated: 2026-07-09
category: integration-issues
module: fzh-web-automation
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "tongtu_login_ocr.py 页面秒开后悬挂 4.5 分钟无任何操作"
  - "ddddocr 识别 8 次全部失败（非概率问题，系统性错误）"
  - "sellfox_login_ocr.py agree checkbox 每次耗时 60 秒"
  - "赛狐登录实际成功但判定失败（SUCCESS_FRAGMENT 不匹配）"
  - "赛狐 refresh captcha 第 3 次起全部超时"
  - "sellfox_login_ocr.py 重复 except 块导致 SyntaxError"
root_cause: wrong_api
resolution_type: code_fix
tags: [playwright, ddddocr, login, tongtu, sellfox, ocr, captcha, element-ui, checkbox, target-crashed]
related_components: [ddddocr_login, tongtu_auto_export, sellfox_auto_export]
---

# Playwright + ddddocr 自动登录 — 通途 & 赛狐 全修复验证

## Problem

PR #11 合并后，通途和赛狐的 Python Playwright 自动登录脚本均未独立验证通过。通途脚本页面秒开后悬挂 4.5 分钟无操作；赛狐脚本 agree checkbox 操作耗时 60 秒，且登录成功后判定逻辑错误。

## Symptoms

- **通途**: `ensure_checkbox` → `login_loop` → 悬挂 264 秒后浏览器已关闭，所有登录尝试报 `Target closed`
- **通途 OCR**: 8 次全失败，结果如 `74c3`, `c4m7`, `am542` 等 5 位字符串，但不是正确验证码
- **赛狐 agree checkbox**: 每次 `ensure_checkbox` 耗时 60 秒才完成
- **赛狐登录判定**: OCR 正确识别 `74Nk` 后成功跳转到 `dashboard.html`，但 `SUCCESS_FRAGMENT = "/home"` 不匹配，判定为失败
- **赛狐 captcha refresh**: 首次后 JS `querySelector('a[href="javascript:"]')` 找不到刷新链接，所有后续尝试超时
- **赛狐语法错误**: `sellfox_login_ocr.py:62-63` 两个连续的 `except Exception` 块

## What Didn't Work

- **Playwright `locator.screenshot()` + 预处理**: 截图 → PNG 转换 → 灰度 + 自动对比度 + 对比度 1.8 倍增强 → ddddocr。通途 8 次全失败，因为预处理严重破坏了验证码像素特征。
- **`login_loop` 共享抽象**: 用于通途时，`fill_fn` 每次循环重填用户名密码，`ensure_checkbox` 无法检测原生 checkbox 的勾选状态（`is-checked` class 和子元素检测均不适用），导致全部 fallback 链被执行。
- **复杂 JS 查询刷新链接**: `input.closest('.el-input').parentElement.querySelector('a[href="javascript:"]')` 在赛狐页面上找不到刷新元素，因为 DOM 结构不同。

## Solution

### 1. 通途验证码：HTTP 下载原始 JPG（匹配 CDP 方案）

WX 的 CDP 方案 (`cdp-based/get_captcha.py`) 通过 HTTP 下载原始 JPG 并直接传给 ddddocr，不经过任何预处理。Playwright 方案改用截图 + 预处理后破坏了验证码。

**Before (broken):**
```python
# Playwright 截图 + 预处理
png = page.locator('img[alt="验证码"]').screenshot()  # PNG 截图
text = ocr.solve_captcha_from_bytes(png, min_length=4)  # 默认 use_preprocess=True → 灰度+对比度
```

**After (fixed):**
```python
# HTTP 下载原始 JPG + 无预处理（匹配 CDP 方案）
def _download_captcha(page) -> bytes | None:
    captcha_url = page.evaluate('document.querySelector("img[alt=\\"验证码\\"]").src')
    if captcha_url.startswith("/"):
        captcha_url = f"https://passport.tongtool.com{captcha_url}"
    cookies = page.context.cookies()
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c["name"], c["value"])
    resp = session.get(captcha_url, headers={"Referer": "https://passport.tongtool.com/"})
    return resp.content if resp.status_code == 200 else None

raw_jpg = _download_captcha(page)
text = ocr.solve_captcha_from_bytes(raw_jpg, use_preprocess=False, min_length=4)
```

### 2. 通途登录：直连循环替代 login_loop

`tongtu_login_ocr.py` 完全重写，匹配 `sellfox_login_ocr.py` 的直连循环模式：
- 填账号密码 **一次**（不在循环中重复）
- 原生 checkbox 用 `cb.check()` 直接操作
- 每次循环：刷新验证码 → HTTP 下载 → ddddocr → 填入 → 点击登录

### 3. 赛狐 agree checkbox：简单 click 替代 ensure_checkbox

**Before (60 秒延迟):**
```python
ocr.ensure_checkbox(SELECTORS["agree_cb"], "阅读并接受协议")
# ensure_checkbox → wait_for(visible, 15s) → _checkbox_looks_checked (永远 False)
# → click → _checkbox_looks_checked (仍然 False) → 内部 fallback → 60s
```

`ensure_checkbox` 选择器指向 `span.el-checkbox__inner` 时，`_checkbox_looks_checked` 的 `is-checked` 检测全部失败（class 在祖父 label 上，不在 inner span 上），导致每次走完所有重试链。

**After (即时完成):**
```python
agree_loc = page.locator(SELECTORS["agree_cb"])
if agree_loc.count() > 0:
    agree_loc.first.click(timeout=5000)  # 直接 click，5s 超时
```

选择器 `label.el-checkbox:has-text("阅读并接受") span.el-checkbox__inner` 确保点击安全区域（`el-checkbox__inner` 是纯 span，不含 `<a>` 子链接，不会触发 Target crashed）。

### 4. 赛狐登录判定：修正 SUCCESS_FRAGMENT + URL 轮询

**Before:**
```python
SUCCESS_FRAGMENT = "/home"  # 错误！实际跳转是 dashboard.html
page.wait_for_timeout(2000)  # 单次 2s 等，重定向可能未完成
```

**After:**
```python
SUCCESS_FRAGMENT = "dashboard"  # 实际跳转目标
for _ in range(10):             # 500ms × 10 轮询
    page.wait_for_timeout(500)
    if SUCCESS_FRAGMENT in (page.url or ""):
        return True
```

### 5. 赛狐 captcha 刷新：text 选择器替代 JS 查询

**Before:**
```python
page.evaluate("""() => {
    const link = input?.closest('.el-input')?.parentElement?.querySelector('a[href="javascript:"]');
    if (link) link.click();
}""")
```

**After:**
```python
page.locator('text=点击刷新').first.click()  # 直接匹配文字
```

### 6. ddddocr_login.py 复选框检测增强

`_checkbox_looks_checked` 新增两种检测路径：
- **原生 checkbox**: `locator.is_checked()` 直接检测 `<input type="checkbox">`
- **祖先 label**: `xpath=ancestor::label[contains(@class,'el-checkbox')]` 查找 Element UI 父级 label 上的 `is-checked` class

### 7. sellfox_login_ocr.py 语法修复

删除第 62-63 行重复的 `except Exception as e:` 块。

## Why This Works

**核心问题**：Playwright `locator.screenshot()` 捕获的是浏览器渲染后的像素（含抗锯齿、CSS 缩放、色彩空间转换），经过灰度+对比度预处理后，与 ddddocr 训练数据（原始 JPG 像素）产生系统性偏差。WX 的 CDP 方案绕过了渲染层，直接下载服务器原始 JPG，所以识别率接近 100%。

**复选框问题**：`ensure_checkbox` 是为 Element UI 设计的复杂抽象，不适合原生 checkbox 和简单场景。直接用 Playwright 原生 `click()` / `check()` 更快更可靠。

## Prevention

- **验证码 OCR 优先原始图片**：能用 HTTP 下载原始图片就不要用 Playwright 截图，除非验证码是 data URI（如赛狐）。
- **`use_preprocess=False` 作为默认**：灰度+对比度预处理仅对特定风格的验证码有效，应作为 opt-in 而非默认。
- **简单场景用简单方法**：原生 checkbox 用 `check()`，Element UI checkbox 且只需要点击的场景用 `click()`。`ensure_checkbox` 仅在需要兼容多种 UI 框架的复杂场景使用。
- **SUCCESS_FRAGMENT 必须 MCP 实测确认**：不能凭记忆写跳转 URL，必须在 MCP 浏览器中手动登录确认实际跳转目标。

## Related

- [docs/lessons/ddddocr-login-pitfalls.md](../lessons/ddddocr-login-pitfalls.md) — 原始 6 个踩坑记录（本文为其验证+修复版）
- [docs/reference/tongtu-captcha-ocr.md](../reference/tongtu-captcha-ocr.md) — WX 的 CDP + ddddocr 方案参考
- PR #11 — `feature/ddddocr-playwright-login`
