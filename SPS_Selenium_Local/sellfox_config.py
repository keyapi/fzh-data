# -*- coding: utf-8 -*-
"""Sellfox 登录配置（环境变量，勿将密码写入仓库）。"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SELLFOX_CONFIG = {
    "login_url": os.getenv(
        "SELLFOX_LOGIN_URL",
        "https://www.sellfox.com/amzup-web-main/login.html",
    ),
    "username": os.getenv("SELLFOX_USER", ""),
    "password": os.getenv("SELLFOX_PASSWORD", ""),
    # 默认有界面，便于调试验证码；设为 true 可尝试无头（可能不稳定）
    "headless": os.getenv("SELLFOX_HEADLESS", "false").lower() in ("1", "true", "yes"),
    "max_captcha_attempts": int(os.getenv("SELLFOX_MAX_ATTEMPTS", "10")),
    # 若 ddddocr 识别率低，可设为 1：仅填账号密码后暂停，手动输验证码并回车继续
    "manual_captcha": os.getenv("SELLFOX_MANUAL_CAPTCHA", "false").lower()
    in ("1", "true", "yes"),
    # OCR 全部失败时：stdin 手动输入（默认）；设为 fail 则直接报错退出
    "ocr_fallback": os.getenv("SELLFOX_OCR_FALLBACK", "stdin").lower(),
    # 可选：Tesseract 可执行文件路径（若已安装 Tesseract-OCR）
    "tesseract_cmd": os.getenv("TESSERACT_CMD", ""),
    # 高度过小会导致最后一行「请选择属性」下拉无空间展开，搜索框不出现（见 sellfox_multi_attr_setup 说明）
    "window_size": os.getenv("SELLFOX_WINDOW_SIZE", "1280,1200"),
    "login_success_wait": int(os.getenv("SELLFOX_LOGIN_WAIT", "25")),
    # Multi-attribute product flow (sellfox_multi_attr_setup.py)
    "multi_attribute_list_url": os.getenv(
        "SELLFOX_MULTI_LIST_URL",
        "https://www.sellfox.com/amzup-web-main/web/multiAttributeList/index.html",
    ),
    "add_multi_attr_url": os.getenv(
        "SELLFOX_ADD_MULTI_ATTR_URL",
        "https://www.sellfox.com/amzup-web-main/web/wares/addMultiAttr/index.html",
    ),
    "spu": os.getenv("SELLFOX_SPU", "KS0001"),
    "style_name": os.getenv("SELLFOX_STYLE_NAME", "三角靠枕"),
    "attr_1": os.getenv("SELLFOX_ATTR_1", "三角靠枕面料"),
    "attr_2": os.getenv("SELLFOX_ATTR_2", "三角靠枕尺寸"),
    "attr_3": os.getenv("SELLFOX_ATTR_3", "三角靠枕颜色"),
    # 0 = block on input(); >0 = sleep seconds then quit (optional)
    "block_seconds": int(os.getenv("SELLFOX_BLOCK_SECONDS", "0")),
    # 登录成功后直达添加页，跳过「多属性列表 + 点击按钮」（更快）
    "direct_add_page": os.getenv("SELLFOX_DIRECT_ADD_PAGE", "true").lower()
    in ("1", "true", "yes"),
    # 脚本结束是否关闭浏览器：false 时仅阻塞等待，需手动关 Chrome
    "auto_quit_browser": os.getenv("SELLFOX_AUTO_QUIT", "true").lower()
    in ("1", "true", "yes"),
    # 验证码错误后重试前等待（秒）
    "captcha_retry_delay": float(os.getenv("SELLFOX_CAPTCHA_RETRY_DELAY", "0.45")),
}


def validate_sellfox_config():
    missing = []
    if not SELLFOX_CONFIG.get("username"):
        missing.append("SELLFOX_USER")
    if not SELLFOX_CONFIG.get("password"):
        missing.append("SELLFOX_PASSWORD")
    if missing:
        raise ValueError(
            "缺少环境变量: "
            + ", ".join(missing)
            + "（可在本目录创建 .env 或先 export / set）"
        )
