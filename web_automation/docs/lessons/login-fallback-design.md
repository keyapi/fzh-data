---
okf: v0.1
type: Lesson
title: 自动登录三级 fallback 架构设计
description: 通途/赛狐 auto-login 的三级降级策略、pre-flight check 模式、密码重试补填 bug、terminal stdin 交互模式
tags: [login, fallback, ddddocr, terminal, stdin, preflight, password-refill, tongtu, sellfox]
timestamp: 2026-07-10
last_updated: 2026-07-10
---

# 自动登录 — 三级 Fallback 架构

## 背景

通途和赛狐的 `--auto-login` 依赖 ddddocr 自动识别验证码。但 ddddocr 有复杂的依赖链（onnxruntime → VC++ Redistributable），在"新机器"、"部分依赖缺失"等场景下容易静默失败。本设计确保在任何依赖状态下用户都有明确、可操作的交互路径。

## 依赖链条与失败点

```
Level 0: Python + uv + Playwright + Chromium
Level 1: ddddocr_login.py (项目模块)
Level 2: ddddocr (pip 包)
Level 3: onnxruntime (ddddocr 的依赖)
Level 4: VC++ Redistributable (Windows 系统库)
```

| 缺失层级 | 失败表现 | 旧行为 | 新行为 |
|---------|---------|-------|-------|
| Level 1 缺失 | `ImportError: No module named 'ddddocr_login'` | 脚本崩溃 | 浏览器手动登录 |
| Level 2 缺失 | `import ddddocr` → ImportError | 8 次 OCR 静默失败 → 最后浏览器 | **terminal 手动输入验证码** |
| Level 3/4 缺失 | `DdddOcr()` → OSError/ImportError | 同上 | **terminal 手动输入验证码** |

## 三级 Fallback 架构

```
auto_login(page)
│
├─ Level 0: Cookie 有效？
│   └─ 已登录 → 跳过登录，直接导出
│
├─ Level 1: ddddocr 可用？
│   ├─ _check_ddddocr() pre-flight
│   ├─ True → 自动 OCR 验证码 → 填入 → 登录
│   └─ False → 进入 Level 2
│
├─ Level 2: Terminal 手动输入
│   ├─ 浏览器显示登录页 + 验证码
│   ├─ Terminal 提示: "请查看浏览器中的验证码图片，在下方输入验证码后按 Enter:"
│   ├─ 用户输入 → 脚本填入浏览器 → 点击登录
│   └─ 失败 → 重试（最多 8 次），每次刷新验证码
│
└─ Level 3: 浏览器手动登录（caller 层）
    ├─ ddddocr_login.py 整个文件缺失 → ImportError
    ├─ login() 返回 False → caller 调用 wait_for_login()
    └─ 浏览器打开 → 用户手动在网页上填表登录 → 保存 cookie
```

## 核心设计决策

### 1. Pre-flight Check (`_check_ddddocr()`)

```python
def _check_ddddocr() -> bool:
    try:
        import ddddocr
        ddddocr.DdddOcr(show_ad=False)  # 实际初始化，检测 DLL 加载
        return True
    except ImportError:
        logger.warning("ddddocr 未安装，将使用 terminal 手动输入验证码")
        logger.warning("修复: uv add ddddocr onnxruntime")
        return False
    except Exception as e:
        logger.warning("ddddocr 加载失败（可能缺少 VC++ 运行库）: %s", e)
        logger.warning("修复: 安装 Microsoft Visual C++ Redistributable")
        return False
```

**为什么要在 login() 入口调用而不是依赖惰性加载？**
- 惰性加载在循环内触发 → 浪费 8 次 OCR 尝试（每次等 OCR 失败）
- Pre-flight 1 秒判断 → 立即进入 terminal 模式
- 错误消息可附带针对性修复建议

### 2. Terminal stdin 交互模式

当 ddddocr 不可用时，跳过所有 OCR 尝试，直接 terminal 交互：

```python
if not ocr_available:
    print("\n请查看浏览器中的验证码图片，在下方输入验证码后按 Enter:", file=sys.stderr)
    text = _normalize_captcha_text(sys.stdin.readline())
```

- 用户名/密码从环境变量读取（已设置则自动填入）
- 只需手输验证码（浏览器中可见）
- 登录成功后 cookie 自动保存（chrome-profile / sellfox-profile）

### 3. 密码重试补填

**Bug**: 通途/赛狐登录失败后，页面会清空密码输入框。原代码只在循环前填入一次密码，后续重试都是空密码 + 验证码。

**Fix**: 在 `if attempt > 1` 分支中，每次重试验证码前补填密码：

```python
if attempt > 1:
    ocr.fill_field(SELECTORS["username"], USERNAME)
    ocr.fill_field(SELECTORS["password"], PASSWORD)
    # 然后刷新验证码...
```

两个平台（通途/赛狐）都有同样的 bug，已统一修复。

### 4. `solve_captcha_from_bytes` 补 stdin fallback

`solve_captcha_from_bytes`（被 tongtu/sellfox login 调用）原来没有 terminal 回退，只有 `solve_captcha` 有。现在对齐：

```python
# OCR 全部失败 → terminal 手动输入
fb = os.environ.get("OCR_FALLBACK", "stdin")
if fb == "fail":
    return None
print("\nOCR 不可用，请在下方输入验证码字符后按 Enter（仅字母数字）:\n", file=sys.stderr)
text = _normalize_captcha_text(sys.stdin.readline())
```

### 5. `import os` 补漏

ddddocr_login.py 中的 `solve_captcha` 方法用了 `os.environ.get()` 但文件头部没有 `import os`。这是因为 stdin fallback 路径从未被触发过（走到这里的场景极少）。已在本次修复中补上。

## 测试覆盖

| 场景 | 模拟方式 | 预期 |
|------|---------|------|
| 全部正常 | 直接运行 | auto OCR → 登录成功 |
| 新机器无 venv | 删除 .venv | `uv sync` 自动安装 24 个包 |
| ddddocr 包缺失 | 重命名 `ddddocr/` | `_check_ddddocr()` → False → terminal 提示 |
| ddddocr_login.py 缺失 | 重命名文件 | ImportError → 浏览器手动登录 |
| onnxruntime 缺失 | 重命名 `onnxruntime/` (子进程) | `_check_ddddocr()` → False → terminal 提示 |
| terminal stdin 输入 | `echo "AB12" \| python` | 读取 stdin → 返回 "AB12" |
| OCR_FALLBACK=fail | 设置环境变量 | ddddocr 损坏时返回 None (不阻塞) |

测试脚本：`test_login_fallback.py`（11 项测试，全通过）— 临时文件，验证完后已删除。

## 用户可见的提示语

### ddddocr 未安装
```
ddddocr 未安装，将使用 terminal 手动输入验证码
修复: uv add ddddocr onnxruntime
```

### onnxruntime / VC++ 缺失
```
ddddocr 加载失败（可能缺少 VC++ 运行库）: DLL load failed
修复: 安装 Microsoft Visual C++ Redistributable
```

### Terminal 手动模式
```
请查看浏览器中的验证码图片，在下方输入验证码后按 Enter:
```

## 关键文件

| 文件 | 改动 |
|------|------|
| `ddddocr_login.py` | +`import os`，`solve_captcha_from_bytes` +stdin fallback |
| `tongtu_login_ocr.py` | +`_check_ddddocr()`，+terminal 手动分支，+密码补填 |
| `sellfox_login_ocr.py` | 同上 |
| `tongtu_auto_export.py` | ImportError → wait_for_login (已有，未改) |
| `sellfox_auto_export.py` | 同上 |
