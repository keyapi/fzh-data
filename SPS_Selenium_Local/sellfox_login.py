#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sellfox 赛狐 ERP 登录（账号密码 + 图形验证码）
凭据仅来自环境变量 SELLFOX_USER / SELLFOX_PASSWORD，勿写入代码库。
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import sys
import time
import traceback
from typing import Optional

from selenium.common.exceptions import TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from sellfox_config import SELLFOX_CONFIG, validate_sellfox_config

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None  # type: ignore

os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/sellfox_login.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# DOM（与 amzup-web-main/login.html 密码登录 Tab 一致）
XP_USER = "//input[@placeholder='请输入手机号/用户名']"
XP_PASS = "//input[@placeholder='请输入密码']"
XP_CAPTCHA_INPUT = "//input[@placeholder='请输入图形验证码']"
XP_CAPTCHA_IMG = XP_CAPTCHA_INPUT + "/following::img[1]"
XP_CAPTCHA_REFRESH = XP_CAPTCHA_IMG + "/parent::a"
XP_LOGIN_BTN = "//button[normalize-space()='登录']"
XP_AUTO_LOGIN_LABEL = "//span[contains(.,'5天内自动登录')]/ancestor::label"
# 协议行：用「隐私协议」缩小范围，避免匹配到页面其它 label
XP_AGREE_LABEL = (
    "//label[contains(@class,'el-checkbox')]"
    "[.//span[contains(.,'阅读并接受')] and .//span[contains(.,'隐私协议')]]"
)
XP_AGREE_LABEL_FALLBACK = "//span[contains(.,'阅读并接受')]/ancestor::label[contains(@class,'el-checkbox')]"


def _normalize_captcha_text(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "")
    # 常见混淆修正（可按实际再调）
    s = re.sub(r"[^0-9A-Za-z]", "", s)
    return s


class SellfoxLogin:
    def __init__(self):
        self.driver: Optional[Chrome] = None
        self._dddd_ocr = None
        self._ddddocr_broken = False

    def _lazy_dddd_ocr(self):
        if self._dddd_ocr is None:
            import ddddocr

            self._dddd_ocr = ddddocr.DdddOcr(show_ad=False)
        return self._dddd_ocr

    def setup_driver(self) -> bool:
        try:
            options = Options()
            if SELLFOX_CONFIG["headless"]:
                options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            w, h = SELLFOX_CONFIG["window_size"].split(",", 1)
            options.add_argument(f"--window-size={w},{h}")
            options.add_argument("--disable-blink-features=AutomationControlled")

            if ChromeDriverManager is not None:
                chrome_service = Service(ChromeDriverManager().install())
            else:
                chrome_service = Service()

            self.driver = Chrome(service=chrome_service, options=options)
            self.driver.implicitly_wait(5)
            logger.info("Chrome WebDriver 初始化成功 (headless=%s)", SELLFOX_CONFIG["headless"])
            return True
        except Exception as e:
            logger.error("Chrome WebDriver 初始化失败: %s", e)
            return False

    def save_screenshot(self, name: str) -> Optional[str]:
        if not self.driver:
            return None
        path = os.path.join("screenshots", name)
        try:
            self.driver.save_screenshot(path)
            logger.info("截图: %s", path)
            return path
        except Exception as e:
            logger.warning("截图失败: %s", e)
            return None

    def _ocr_ddddocr(self, png: bytes) -> Optional[str]:
        if self._ddddocr_broken:
            return None
        try:
            ocr = self._lazy_dddd_ocr()
            text = ocr.classification(png)
            return _normalize_captcha_text(text) or None
        except Exception as e:
            logger.warning("ddddocr 不可用或识别失败: %s", e)
            self._ddddocr_broken = True
            self._dddd_ocr = None
            return None

    def _ocr_pytesseract(self, png: bytes) -> Optional[str]:
        try:
            import pytesseract
            from PIL import Image

            cmd = SELLFOX_CONFIG.get("tesseract_cmd") or shutil.which("tesseract")
            if cmd:
                pytesseract.pytesseract.tesseract_cmd = cmd
            else:
                return None
            im = Image.open(io.BytesIO(png))
            raw = pytesseract.image_to_string(im, config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
            return _normalize_captcha_text(raw) or None
        except Exception as e:
            logger.warning("pytesseract 不可用或识别失败: %s", e)
            return None

    def _ocr_best_effort(self, png: bytes) -> Optional[str]:
        t = self._ocr_ddddocr(png)
        if t:
            return t
        return self._ocr_pytesseract(png)

    def _optional_preprocess(self, png: bytes) -> bytes:
        """简单预处理：灰度 + 对比度，失败则回退原图。"""
        try:
            from PIL import Image, ImageEnhance, ImageOps

            im = Image.open(io.BytesIO(png)).convert("L")
            im = ImageOps.autocontrast(im)
            im = ImageEnhance.Contrast(im).enhance(1.8)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return png

    def _el_checkbox_looks_checked(self, label) -> bool:
        """Element UI：以 label / el-checkbox__input 上的 is-checked 为准，不能只看原生 input。"""
        try:
            cls = label.get_attribute("class") or ""
            if "is-checked" in cls:
                return True
        except Exception:
            pass
        try:
            inp = label.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
            if inp.is_selected():
                return True
        except Exception:
            pass
        try:
            wrap = label.find_element(
                By.CSS_SELECTOR, "[class*='el-checkbox__input'], span.el-checkbox__input"
            )
            wcls = wrap.get_attribute("class") or ""
            if "is-checked" in wcls:
                return True
        except Exception:
            pass
        return False

    def _ensure_el_checkbox_label(self, label, desc: str) -> None:
        assert self.driver
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', inline:'nearest'});", label
        )
        time.sleep(0.15)
        if self._el_checkbox_looks_checked(label):
            logger.info("已勾选(无需操作): %s", desc)
            return
        try:
            label.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", label)
        time.sleep(0.35)
        if self._el_checkbox_looks_checked(label):
            logger.info("已勾选: %s", desc)
            return
        # 再点一次内部可视区域（Element UI 偶发要点到 __inner）
        try:
            inner = label.find_element(By.CSS_SELECTOR, ".el-checkbox__inner")
            inner.click()
            time.sleep(0.25)
        except Exception:
            self.driver.execute_script("arguments[0].click();", label)
            time.sleep(0.25)
        if self._el_checkbox_looks_checked(label):
            logger.info("已勾选(二次点击): %s", desc)
            return
        logger.warning("仍无法确认已勾选: %s，将继续尝试登录", desc)

    def _find_agreement_label(self):
        assert self.driver
        for xp in (XP_AGREE_LABEL, XP_AGREE_LABEL_FALLBACK):
            els = self.driver.find_elements(By.XPATH, xp)
            for el in els:
                try:
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        return WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, XP_AGREE_LABEL))
        )

    def ensure_login_checkboxes(self) -> None:
        """登录前勾选「5天内自动登录」与「阅读并接受协议」。"""
        assert self.driver
        auto = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, XP_AUTO_LOGIN_LABEL))
        )
        self._ensure_el_checkbox_label(auto, "5天内自动登录")
        agree = self._find_agreement_label()
        self._ensure_el_checkbox_label(agree, "赛狐用户协议及隐私协议")

    def fill_user_pass(self) -> None:
        assert self.driver
        u = WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.XPATH, XP_USER))
        )
        u.clear()
        u.send_keys(SELLFOX_CONFIG["username"])
        p = self.driver.find_element(By.XPATH, XP_PASS)
        p.clear()
        p.send_keys(SELLFOX_CONFIG["password"])
        logger.info("已填写用户名与密码")

    def refresh_captcha(self) -> None:
        assert self.driver
        el = self.driver.find_element(By.XPATH, XP_CAPTCHA_REFRESH)
        el.click()
        time.sleep(0.4)

    def solve_and_fill_captcha(self, use_preprocess: bool = True) -> str:
        assert self.driver
        img = WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.XPATH, XP_CAPTCHA_IMG))
        )
        png = img.screenshot_as_png
        ts = int(time.time())
        raw_path = f"sellfox_captcha_raw_{ts}.png"
        with open(os.path.join("screenshots", raw_path), "wb") as f:
            f.write(png)

        body = self._optional_preprocess(png) if use_preprocess else png
        if use_preprocess:
            pre_path = f"sellfox_captcha_pre_{ts}.png"
            with open(os.path.join("screenshots", pre_path), "wb") as f:
                f.write(body)

        text = self._ocr_best_effort(body)
        if not text and use_preprocess:
            text = self._ocr_best_effort(png)
        if not text:
            fb = SELLFOX_CONFIG.get("ocr_fallback", "stdin")
            if fb == "fail":
                raise RuntimeError(
                    "所有 OCR 后端均失败（常见原因：缺少 VC++ 运行库导致 onnxruntime 无法加载）。"
                    "请安装 Microsoft Visual C++ Redistributable，或安装 Tesseract 并设置 TESSERACT_CMD，"
                    "或使用环境变量 SELLFOX_MANUAL_CAPTCHA=1。"
                )
            path = os.path.join("screenshots", raw_path)
            print(
                f"\nOCR 不可用，请查看验证码图片文件:\n  {os.path.abspath(path)}\n"
                "在下方输入验证码字符后按 Enter（仅字母数字）:\n",
                file=sys.stderr,
            )
            text = _normalize_captcha_text(sys.stdin.readline())
            if not text:
                raise RuntimeError("未输入验证码")
        logger.info("使用验证码: %s", text)

        cap_in = self.driver.find_element(By.XPATH, XP_CAPTCHA_INPUT)
        cap_in.clear()
        cap_in.send_keys(text)
        return text

    def click_login(self) -> None:
        assert self.driver
        btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, XP_LOGIN_BTN))
        )
        btn.click()
        logger.info("已点击登录")

    def wait_login_result(self) -> bool:
        """若离开 login.html 则视为成功。"""
        assert self.driver
        wait_sec = SELLFOX_CONFIG["login_success_wait"]
        end = time.time() + wait_sec
        while time.time() < end:
            try:
                url = self.driver.current_url or ""
                if "login.html" not in url.lower():
                    logger.info("登录成功，当前 URL: %s", url)
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        logger.warning("仍在登录页或超时未跳转")
        return False

    def manual_captcha_pause(self) -> None:
        assert self.driver
        self.ensure_login_checkboxes()
        self.fill_user_pass()
        logger.info(
            "SELLFOX_MANUAL_CAPTCHA=1：请在浏览器中手动输入图形验证码，"
            "然后回到此终端按 Enter 继续（脚本将只负责点击登录）。"
        )
        input()
        self.ensure_login_checkboxes()
        self.click_login()

    def _quit_driver_unless_kept(self, keep_browser_open: bool, login_succeeded: bool) -> None:
        if not self.driver:
            return
        if keep_browser_open and login_succeeded:
            logger.info("保持浏览器会话（keep_browser_open=True），未关闭 WebDriver")
            return
        try:
            self.driver.quit()
        except Exception as e:
            logger.warning("关闭 WebDriver 时: %s", e)
        finally:
            self.driver = None

    def login(self, keep_browser_open: bool = False) -> bool:
        validate_sellfox_config()
        login_succeeded = False

        if SELLFOX_CONFIG["manual_captcha"]:
            if not self.setup_driver():
                return False
            try:
                self.driver.get(SELLFOX_CONFIG["login_url"])
                time.sleep(2)
                self.manual_captcha_pause()
                login_succeeded = self.wait_login_result()
                if login_succeeded:
                    self.save_screenshot("sellfox_login_success.png")
                else:
                    self.save_screenshot("sellfox_login_fail.png")
                return login_succeeded
            except Exception as e:
                logger.error("登录异常: %s", e)
                logger.error(traceback.format_exc())
                self.save_screenshot("sellfox_login_error.png")
                return False
            finally:
                self._quit_driver_unless_kept(keep_browser_open, login_succeeded)

        if not self.setup_driver():
            return False

        try:
            self.driver.get(SELLFOX_CONFIG["login_url"])
            time.sleep(2)
            self.ensure_login_checkboxes()
            self.fill_user_pass()

            attempts = SELLFOX_CONFIG["max_captcha_attempts"]
            for i in range(1, attempts + 1):
                logger.info("验证码尝试 %s/%s", i, attempts)
                if i > 1:
                    self.refresh_captcha()
                    time.sleep(0.5)

                self.solve_and_fill_captcha()
                # 填验证码后协议可能被重置或未命中，点击登录前再确保两项均已勾选
                self.ensure_login_checkboxes()
                self.click_login()

                if self.wait_login_result():
                    self.save_screenshot("sellfox_login_success.png")
                    login_succeeded = True
                    return True

                self.save_screenshot(f"sellfox_login_retry_{i}.png")
                # 若出现腾讯滑块等业务拦截，多试几次通常无意义，但仍按次数重试
                time.sleep(float(SELLFOX_CONFIG.get("captcha_retry_delay", 0.45)))

            logger.error("超过最大尝试次数仍未登录成功")
            self.save_screenshot("sellfox_login_fail.png")
            return False

        except Exception as e:
            logger.error("登录异常: %s", e)
            logger.error(traceback.format_exc())
            self.save_screenshot("sellfox_login_error.png")
            return False
        finally:
            self._quit_driver_unless_kept(keep_browser_open, login_succeeded)


def main():
    ok = SellfoxLogin().login(keep_browser_open=False)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
