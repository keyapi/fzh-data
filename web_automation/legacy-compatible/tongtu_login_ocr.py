#!/usr/bin/env python3
"""
通途登录 — ddddocr 自动识别验证码 + Playwright
匹配 WX CDP 方案：HTTP 下载原始 JPG → ddddocr（不做预处理）
"""
import logging
import os
from pathlib import Path
def _load_env():
    """加载 .env 文件中的环境变量（web_automation 根 + 仓库根）"""
    here = Path(__file__).resolve().parent
    for env_path in (here.parent / ".env", here.parent.parent / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if key not in os.environ:
                os.environ[key] = val

_load_env()
import sys
import time

import requests
from ddddocr_login import DdddocrLogin, _normalize_captcha_text

sys.stdout.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)

LOGIN_URL = (
    "https://passport.tongtool.com/"
    "?u=http%3A%2F%2Ferp102.tongtool.com%2Fj_security_check"
)
SUCCESS_FRAGMENT = "erp102"
EXCLUDE_FRAGMENT = "passport"
MAX_ATTEMPTS = 8

USERNAME = os.getenv("TONGTU_USER", "")
PASSWORD = os.getenv("TONGTU_PASSWORD", "")

SELECTORS = {
    "username": 'input[name="username"]',
    "password": 'input[name="password"]',
    "captcha_img": 'img[alt="验证码"]',
    "captcha_input": 'input[name="captcha"]',
    "login_btn": 'button:has-text("立即登录")',
    "auto_login_cb": 'input[type="checkbox"]',
}


def _download_captcha(page) -> bytes | None:
    """下载通途验证码原始 JPG（匹配 CDP 方案：HTTP 下载 + cookies）"""
    try:
        captcha_url = page.evaluate(
            'document.querySelector("img[alt=\\"验证码\\"]").src'
        )
        if not captcha_url:
            return None
        # 处理相对 URL
        if captcha_url.startswith("/"):
            captcha_url = f"https://passport.tongtool.com{captcha_url}"

        cookies = page.context.cookies()
        session = requests.Session()
        for c in cookies:
            session.cookies.set(c["name"], c["value"])
        session.cookies.set("tongtool_front_ys", "1")

        resp = session.get(
            captcha_url,
            headers={
                "User-Agent": page.evaluate("navigator.userAgent"),
                "Referer": "https://passport.tongtool.com/",
            },
            timeout=10,
        )
        if resp.status_code == 200 and len(resp.content) > 100:
            logger.debug("下载验证码成功: %d bytes", len(resp.content))
            return resp.content
        logger.warning("验证码下载失败: HTTP %d, %d bytes", resp.status_code, len(resp.content))
        return None
    except Exception as e:
        logger.warning("下载验证码异常: %s", e)
        return None


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
        logger.error("请设置环境变量 TONGTU_USER 和 TONGTU_PASSWORD，或在 .env 文件中配置")
        return False

    ocr_available = _check_ddddocr()

    ocr = DdddocrLogin()
    ocr.set_page(page)

    logger.info("导航到通途登录页...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('input[name="username"]', state='attached', timeout=15000)
    page.wait_for_timeout(1500)

    # 勾选"7天内自动登录"
    try:
        cb = page.locator(SELECTORS["auto_login_cb"]).first
        cb.wait_for(state="visible", timeout=10000)
        if not cb.is_checked():
            cb.check()
            logger.info("已勾选: 7天内自动登录")
        else:
            logger.info("已勾选(无需操作): 7天内自动登录")
    except Exception as e:
        logger.warning("勾选自动登录失败: %s，继续...", e)

    # 填入账号密码（每次尝试前都重新填，因为通途失败会清空密码框）
    ocr.fill_field(SELECTORS["username"], USERNAME)
    ocr.fill_field(SELECTORS["password"], PASSWORD)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info("第 %d/%d 次尝试...", attempt, MAX_ATTEMPTS)

        # 刷新验证码（点击图片触发 changeCaptcha()）
        if attempt > 1:
            # 通途失败后密码框会被清空，每次重试前重新填入
            ocr.fill_field(SELECTORS["username"], USERNAME)
            ocr.fill_field(SELECTORS["password"], PASSWORD)
            try:
                page.locator(SELECTORS["captcha_img"]).first.click()
                page.wait_for_timeout(600)
            except Exception as e:
                logger.warning("刷新验证码失败: %s", e)

        # 下载原始 JPG → OCR（不做预处理，匹配 CDP 方案）
        if not ocr_available:
            # Terminal 手动模式：跳过下载+OCR，直接提示用户输入
            print("\n请查看浏览器中的验证码图片，在下方输入验证码后按 Enter:", file=sys.stderr)
            text = _normalize_captcha_text(sys.stdin.readline())
            if not text:
                continue
        else:
            raw_jpg = _download_captcha(page)
            if not raw_jpg:
                logger.warning("获取验证码失败，重试...")
                time.sleep(0.5)
                continue

            text = ocr.solve_captcha_from_bytes(raw_jpg, use_preprocess=False, min_length=4)
            if not text:
                logger.warning("OCR 识别失败，重试...")
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

        # 等待结果
        page.wait_for_timeout(2000)
        url = page.url or ""
        if SUCCESS_FRAGMENT in url and EXCLUDE_FRAGMENT not in url:
            logger.info("登录成功！URL: %s", url)
            return True

        logger.info("未跳转，刷新重试...")
        time.sleep(0.3)

    logger.error("全部 %d 次尝试失败", MAX_ATTEMPTS)
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="chrome-profile",  # 与 tongtu_auto_export.py 共享 cookie
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


