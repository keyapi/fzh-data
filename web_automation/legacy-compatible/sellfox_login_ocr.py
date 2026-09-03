#!/usr/bin/env python3
"""
赛狐登录 — ddddocr 自动识别验证码 + Playwright

关键：验证码有时效，必须点击刷新后立刻识别+填入+登录。
"""
import base64
import logging
import os
import sys
import time

from ddddocr_login import DdddocrLogin, _normalize_captcha_text

# Windows 中文编码
sys.stdout.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)

# ── 配置 ──
LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
SUCCESS_FRAGMENT = "dashboard"  # 登录成功后跳转到 dashboard.html，不是 /home
MAX_ATTEMPTS = 10

USERNAME = os.getenv("SELLFOX_USER", "")
PASSWORD = os.getenv("SELLFOX_PASSWORD", "")

# ── 选择器（2026-07 MCP 探路实测确认）──
SELECTORS = {
    "username": "#username",
    "password": 'input[placeholder*="请输入密码"]',
    "captcha_img": 'img[src^="data:image/jpg"]',
    "captcha_refresh": 'text=点击刷新',
    "captcha_input": 'input[placeholder*="图形验证码"]',
    "login_btn": 'button:has-text("登录")',
    "auto_login_cb": 'text=5天内自动登录',
    "agree_cb": 'label.el-checkbox:has-text("阅读并接受") span.el-checkbox__inner',
}


def _check_ddddocr() -> bool:
    """Pre-flight: 检测 ddddocr + onnxruntime 是否真的可用"""
    try:
        import ddddocr
        ddddocr.DdddOcr(show_ad=False)
        return True
    except ImportError:
        logger.warning("ddddocr 未安装，将使用 terminal 手动输入验证码")
        logger.warning("修复: uv add ddddocr onnxruntime")
        return False
    except Exception as e:
        logger.warning("ddddocr 加载失败（可能缺少 VC++ 运行库）: %s", e)
        logger.warning("修复: 安装 Microsoft Visual C++ Redistributable")
        return False


def login(page) -> bool:
    if not USERNAME or not PASSWORD:
        logger.error("请设置环境变量 SELLFOX_USER 和 SELLFOX_PASSWORD")
        return False

    ocr_available = _check_ddddocr()

    ocr = DdddocrLogin()
    ocr.set_page(page)

    logger.info("导航到赛狐登录页...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    # 已有有效 cookie → 自动跳转 → 无需登录
    if SUCCESS_FRAGMENT in (page.url or ""):
        logger.info("已有登录态，跳过登录（URL: %s）", page.url)
        return True

    # 等登录表单（可能被 cookie 触发 JS 跳转，这里等不到就再检查 URL）
    try:
        page.wait_for_selector('#username', state='attached', timeout=10000)
    except Exception:
        if SUCCESS_FRAGMENT in (page.url or ""):
            logger.info("已有登录态（延迟跳转），跳过登录")
            return True
        raise

    # 勾选"5天内自动登录"
    try:
        ocr.ensure_checkbox(SELECTORS["auto_login_cb"], "5天内自动登录")
    except Exception as e:
        logger.warning("勾选自动登录失败: %s", e)

    # 勾选协议（存在时直接点击 el-checkbox__inner，避免 Target crashed）
    agree_loc = page.locator(SELECTORS["agree_cb"])
    if agree_loc.count() > 0:
        try:
            agree_loc.first.click(timeout=5000)
            logger.info("已勾选: 阅读并接受协议")
        except Exception as e:
            logger.warning("勾选协议失败: %s", e)
    else:
        logger.info("协议勾选框未显示(已有登录态)，跳过")

    # 填入账号密码（每次尝试前都重新填，因为赛狐失败会清空密码框）
    ocr.fill_field(SELECTORS["username"], USERNAME)
    ocr.fill_field(SELECTORS["password"], PASSWORD)

    last_captcha_src = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info("第 %d/%d 次尝试...", attempt, MAX_ATTEMPTS)

        # 刷新验证码
        if attempt > 1:
            # 赛狐失败后密码框会被清空，每次重试前重新填入
            ocr.fill_field(SELECTORS["username"], USERNAME)
            ocr.fill_field(SELECTORS["password"], PASSWORD)
            try:
                refresh_el = page.locator('text=点击刷新').first
                if refresh_el.count() > 0:
                    refresh_el.click()
                else:
                    page.locator(SELECTORS["captcha_img"]).first.click()
            except Exception:
                pass
            # 等新图（最多 10s）
            for _ in range(20):
                page.wait_for_timeout(500)
                try:
                    cur = page.evaluate(
                        'document.querySelector(\'img[src^="data:image/jpg"]\')?.src || ""'
                    )
                    if cur and cur != last_captcha_src:
                        break
                except Exception:
                    pass

        # 读图 → OCR（至少4位）
        if not ocr_available:
            # Terminal 手动模式：跳过读图+OCR，直接提示用户输入
            print("\n请查看浏览器中的验证码图片，在下方输入验证码后按 Enter:", file=sys.stderr)
            text = _normalize_captcha_text(sys.stdin.readline())
            if not text:
                continue
        else:
            png = None
            captcha_src = None
            try:
                result = page.evaluate(
                    """() => {
                        const img = document.querySelector('img[src^="data:image/jpg"]');
                        if (!img || !img.src) return null;
                        const s = img.src;
                        const i = s.indexOf(',');
                        return { b64: i > 0 ? s.substring(i + 1) : null, src: s };
                    }"""
                )
                if result and result.get("b64"):
                    png = base64.b64decode(result["b64"])
                    captcha_src = result.get("src")
            except Exception:
                pass

            if not png:
                logger.warning("获取验证码失败(URL: %s)，重试...", page.url[:80])
                if SUCCESS_FRAGMENT in (page.url or ""):
                    logger.info("登录成功！URL: %s", page.url)
                    return True
                if "login" not in (page.url or ""):
                    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(1000)
                time.sleep(0.5)
                continue

            last_captcha_src = captcha_src

            text = ocr.solve_captcha_from_bytes(png, use_preprocess=False, min_length=4)
            if not text:
                logger.warning("OCR 失败，重试...")
                time.sleep(0.3)
                continue

        # 填入验证码
        try:
            page.locator(SELECTORS["captcha_input"]).first.fill(text)
        except Exception as e:
            logger.warning("填入验证码失败: %s", e)
            time.sleep(0.3)
            continue

        # 点击登录
        try:
            page.locator(SELECTORS["login_btn"]).first.click()
        except Exception as e:
            logger.warning("点击登录失败: %s", e)
            time.sleep(0.3)
            continue

        # 等结果（轮询 URL，最多 5 秒）
        for _ in range(10):
            page.wait_for_timeout(500)
            url = page.url or ""
            if SUCCESS_FRAGMENT in url:
                logger.info("登录成功！URL: %s", url)
                return True

        if SUCCESS_FRAGMENT not in (page.url or ""):
            logger.info("未跳转（验证码错误或过期），刷新重试...")
        time.sleep(0.3)

    logger.error("全部 %d 次尝试失败", MAX_ATTEMPTS)
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="sellfox-profile",  # 与 sellfox_auto_export.py 共享 cookie
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        pg = context.pages[0] if context.pages else context.new_page()

        success = login(pg)
        print("登录成功！" if success else "登录失败")
        if success:
            pg.wait_for_timeout(3000)

        context.close()
        sys.exit(0 if success else 1)
