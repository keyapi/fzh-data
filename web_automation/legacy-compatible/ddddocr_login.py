#!/usr/bin/env python3
"""
共享模块：Playwright + ddddocr 自动登录引擎
从 fzh-data SPS_Selenium_Local/sellfox_login.py 移植 OCR 逻辑到 Playwright
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import sys
import time
from typing import Optional

from playwright.sync_api import Page, Locator

logger = logging.getLogger(__name__)


def _normalize_captcha_text(text: str) -> str:
    """去空白 + 特殊字符，只保留字母数字"""
    s = text.strip().replace(" ", "").replace("\n", "").replace("\r", "")
    s = re.sub(r"[^0-9A-Za-z]", "", s)
    return s


class DdddocrLogin:
    """Playwright 版 ddddocr 自动登录引擎"""

    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts
        self._page: Optional[Page] = None
        self._dddd_ocr = None        # ddddocr 单例
        self._ddddocr_broken = False # 熔断标志

    # ── page 注入 ──

    def set_page(self, page: Page) -> None:
        self._page = page

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("请先调用 set_page(page)")
        return self._page

    # ── ddddocr 引擎（惰性加载 + 熔断）──

    def _lazy_dddd_ocr(self):
        """惰性加载 ddddocr，单例复用"""
        if self._dddd_ocr is None:
            import ddddocr
            self._dddd_ocr = ddddocr.DdddOcr(show_ad=False)
            logger.info("ddddocr 已加载")
        return self._dddd_ocr

    def _ocr_ddddocr(self, png: bytes) -> Optional[str]:
        """ddddocr 识别，失败一次即熔断"""
        if self._ddddocr_broken:
            return None
        try:
            ocr = self._lazy_dddd_ocr()
            text = ocr.classification(png)
            result = _normalize_captcha_text(text)
            if result:
                return result
            logger.warning("ddddocr 返回空结果")
            return None
        except Exception as e:
            logger.warning("ddddocr 不可用或识别失败: %s", e)
            self._ddddocr_broken = True
            self._dddd_ocr = None
            return None

    def _ocr_pytesseract(self, png: bytes) -> Optional[str]:
        """Tesseract fallback（需要单独安装）"""
        try:
            import pytesseract
            from PIL import Image

            cmd = shutil.which("tesseract")
            if cmd:
                pytesseract.pytesseract.tesseract_cmd = cmd
            else:
                logger.debug("未找到 tesseract，跳过")
                return None
            im = Image.open(io.BytesIO(png))
            raw = pytesseract.image_to_string(
                im,
                config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
            )
            return _normalize_captcha_text(raw) or None
        except ImportError:
            logger.debug("pytesseract 未安装")
            return None
        except Exception as e:
            logger.warning("pytesseract 识别失败: %s", e)
            return None

    def _ocr_best_effort(self, png: bytes) -> Optional[str]:
        """ddddocr → pytesseract 链"""
        t = self._ocr_ddddocr(png)
        if t:
            return t
        return self._ocr_pytesseract(png)

    # ── 验证码预处理 ──

    def _preprocess(self, png: bytes) -> bytes:
        """灰度 + 自动对比度 + 对比度增强，失败回退原图"""
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

    # ── 浏览器操作 ──

    def get_captcha(self, selector: str) -> Optional[bytes]:
        """截取验证码图片"""
        try:
            el = self.page.locator(selector).first
            el.wait_for(state="visible", timeout=10000)
            return el.screenshot()
        except Exception as e:
            logger.warning("截图验证码失败: %s", e)
            return None

    def solve_captcha_from_bytes(self, png: bytes, use_preprocess: bool = True,
                                  min_length: int = 0) -> Optional[str]:
        """直接传入图片字节 → OCR → 返回文本（不走浏览器截图）"""
        body = self._preprocess(png) if use_preprocess else png
        text = self._ocr_best_effort(body)
        if not text and use_preprocess:
            text = self._ocr_best_effort(png)

        if text and min_length > 0 and len(text) < min_length:
            logger.warning("OCR 结果仅 %d 位（需 ≥%d 位）: %s，视为失败", len(text), min_length, text)
            text = None

        if text:
            logger.info("验证码识别结果: %s", text)
            return text

        # OCR 全部失败 → terminal 手动输入
        fb = os.environ.get("OCR_FALLBACK", "stdin")
        if fb == "fail":
            return None
        print(
            "\nOCR 不可用，请在下方输入验证码字符后按 Enter（仅字母数字）:\n",
            file=sys.stderr,
        )
        text = _normalize_captcha_text(sys.stdin.readline())
        return text if text else None

    def solve_captcha(self, captcha_selector: str, use_preprocess: bool = True,
                       min_length: int = 0) -> Optional[str]:
        """截图 → 预处理 → OCR → 返回文本。
        min_length: 最少字符数，低于此值视为识别失败返回 None。
        """
        png = self.get_captcha(captcha_selector)
        if not png:
            return None

        body = self._preprocess(png) if use_preprocess else png
        text = self._ocr_best_effort(body)
        if not text and use_preprocess:
            text = self._ocr_best_effort(png)  # 回退用原图再试

        if text and min_length > 0 and len(text) < min_length:
            logger.warning("OCR 结果仅 %d 位（需 ≥%d 位）: %s，视为失败", len(text), min_length, text)
            text = None

        if not text:
            fb = os.environ.get("OCR_FALLBACK", "stdin")
            if fb == "fail":
                raise RuntimeError(
                    "所有 OCR 后端均失败（常见原因：缺少 VC++ 运行库导致 onnxruntime 无法加载）。"
                    "请安装 Microsoft Visual C++ Redistributable，或安装 Tesseract。"
                )
            print(
                "\nOCR 不可用，请在下方输入验证码字符后按 Enter（仅字母数字）:\n",
                file=sys.stderr,
            )
            text = _normalize_captcha_text(sys.stdin.readline())
            if not text:
                raise RuntimeError("未输入验证码")

        logger.info("验证码识别结果: %s", text)
        return text

    def fill_field(self, selector: str, value: str) -> None:
        el = self.page.locator(selector).first
        el.wait_for(state="visible", timeout=15000)
        el.fill(value)

    def solve_and_fill(self, captcha_selector: str, input_selector: str,
                        min_length: int = 0) -> Optional[str]:
        """识别验证码并填入输入框"""
        text = self.solve_captcha(captcha_selector, min_length=min_length)
        if not text:
            return None
        self.fill_field(input_selector, text)
        return text

    def click_login(self, selector: str) -> None:
        btn = self.page.locator(selector).first
        btn.wait_for(state="visible", timeout=10000)
        btn.click()

    def wait_result(self, url_fragment: str, exclude_fragment: str = "", timeout: int = 25) -> bool:
        """轮询 URL 检测登录是否成功（含 exclude_fragment 表示排除该 URL）"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                url = self.page.url or ""
                if url_fragment in url:
                    if not exclude_fragment or exclude_fragment not in url:
                        logger.info("登录成功，当前 URL: %s", url)
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        logger.warning("登录超时未跳转")
        return False

    # ── Element UI checkbox ──

    def _checkbox_looks_checked(self, locator: Locator) -> bool:
        """检测 checkbox 是否已勾选（Native + Element UI 兼容）"""
        # 1) Native checkbox: locator 本身就是 <input type="checkbox">
        try:
            if locator.is_checked():
                return True
        except Exception:
            pass
        # 2) Element UI: is-checked class 在 locator 自身
        try:
            label = locator.first
            cls = label.get_attribute("class") or ""
            if "is-checked" in cls:
                return True
        except Exception:
            pass
        # 3) locator 包含子 <input type="checkbox">
        try:
            inp = label.locator("input[type='checkbox']")
            if inp.is_checked():
                return True
        except Exception:
            pass
        # 4) Element UI: is-checked 在子节点 el-checkbox__input 上
        try:
            wrap = label.locator("[class*='el-checkbox__input']")
            wcls = wrap.get_attribute("class") or ""
            if "is-checked" in wcls:
                return True
        except Exception:
            pass
        # 5) 当 selector 指向 span.el-checkbox__inner 时，is-checked 在祖父 label 上
        try:
            parent = label.locator("xpath=ancestor::label[contains(@class,'el-checkbox')][1]")
            pcls = parent.get_attribute("class") or ""
            if "is-checked" in pcls:
                return True
        except Exception:
            pass
        return False

    def ensure_checkbox(self, selector: str, desc: str = "") -> None:
        """确保 checkbox 已勾选（Element UI 兼容，Playwright 原生 checkbox 兼容）"""
        locator = self.page.locator(selector).first
        locator.wait_for(state="visible", timeout=15000)
        locator.scroll_into_view_if_needed()
        time.sleep(0.15)

        if self._checkbox_looks_checked(locator):
            logger.info("已勾选(无需操作): %s", desc or selector)
            return

        # 尝试多种点击策略
        try:
            locator.click()
        except Exception:
            try:
                locator.evaluate("el => el.click()")
            except Exception:
                pass
        time.sleep(0.35)

        if self._checkbox_looks_checked(locator):
            logger.info("已勾选: %s", desc or selector)
            return

        # Element UI: 再点内部 __inner
        try:
            inner = locator.locator(".el-checkbox__inner")
            inner.click()
            time.sleep(0.25)
        except Exception:
            pass

        if self._checkbox_looks_checked(locator):
            logger.info("已勾选(二次点击): %s", desc or selector)
            return

        logger.warning("仍无法确认已勾选: %s，将继续尝试登录", desc or selector)

    # ── 主循环 ──

    def login_loop(
        self,
        fill_fn,                          # callable: 填用户名密码
        captcha_selector: str,
        captcha_input_selector: str,
        login_btn_selector: str,
        url_fragment: str,
        exclude_fragment: str = "",
        retry_delay: float = 0.45,
        captcha_min_length: int = 0,
    ) -> bool:
        """
        主循环：填表 → OCR → 登录 → 验证，最多 max_attempts 次。
        返回 True（成功）或 False（全部重试耗尽）。
        captcha_min_length: 验证码最少位数，不足则刷新重试。
        """
        for attempt in range(1, self.max_attempts + 1):
            logger.info("第 %d/%d 次尝试登录...", attempt, self.max_attempts)
            try:
                fill_fn()
            except Exception as e:
                logger.warning("填表失败: %s，重试...", e)
                time.sleep(retry_delay)
                continue

            text = self.solve_and_fill(captcha_selector, captcha_input_selector,
                                       min_length=captcha_min_length)
            if not text:
                logger.warning("验证码识别失败，重试...")
                time.sleep(retry_delay)
                continue

            try:
                self.click_login(login_btn_selector)
            except Exception as e:
                logger.warning("点击登录失败: %s，重试...", e)
                time.sleep(retry_delay)
                continue

            time.sleep(2)
            if self.wait_result(url_fragment, exclude_fragment=exclude_fragment):
                return True

            logger.info("登录未成功，将重试...")
            time.sleep(retry_delay)

        logger.error("全部 %d 次登录尝试失败", self.max_attempts)
        return False


# ── 独立运行（测试 ddddocr 是否可用）──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    import sys
    if len(sys.argv) > 1:
        png_path = sys.argv[1]
        png = open(png_path, "rb").read()
        ocr = DdddocrLogin()
        result = ocr._ocr_best_effort(png)
        print(f"识别结果: {result}")
    else:
        print("用法: python ddddocr_login.py <验证码图片>")
