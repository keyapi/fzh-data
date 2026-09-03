#!/usr/bin/env python3
"""
通途库存导出 — 使用 ddddocr 自动识别验证码 + CDP 浏览器
"""
import subprocess, sys, time, shutil
from pathlib import Path
from datetime import datetime
import ddddocr
import base64
import json

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
DOWNLOADS_DIR = WEB_ROOT / "downloads"
OUTPUT_DIR = WEB_ROOT / "output"
DOWNLOADS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

COMPUTER_TOOL = "/root/.codebuddy/skills/computer-use/scripts/computer_tool.py"
TONGTU_LOGIN = "https://passport.tongtool.com/?u=http%3A%2F%2Ferp102.tongtool.com%2Fj_security_check"
INVENTORY_URL = "https://erp102.tongtool.com/warehouse/goodsbalance/index.htm?warehouse=1&isFirstInto=1"

import os

USERNAME = os.getenv("TONGTU_USER", "")
PASSWORD = os.getenv("TONGTU_PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("错误: 请设置环境变量 TONGTU_USER 和 TONGTU_PASSWORD")
    print("  方式1: 在 .env 文件中设置，然后运行脚本")
    print("  方式2: PowerShell: $env:TONGTU_USER='user'; $env:TONGTU_PASSWORD='pass'")
    sys.exit(1)

WAREHOUSES = [
    "CENTRADE",
    "FZHPoland-covers",
    "FZH-DANEEY-皮壳仓库",
    "FZH-DANEEY-退货产品仓",
    "FZH-DANEEY-成品仓",
    "FZH-DANEEY-半成品仓",
]

def run_tool(action, **kwargs):
    cmd = ["python3", COMPUTER_TOOL, json.dumps({"action": action, **kwargs})]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    # Find JSON in output
    out = result.stdout
    json_start = out.find('{"')
    if json_start < 0:
        return None, result.stderr
    try:
        return json.loads(out[json_start:]), None
    except:
        return None, result.stderr

def get_captcha_image():
    """从当前页面截取验证码图片"""
    # 先截图整个浏览器
    result, err = run_tool("browser_screenshot")
    if not result or "base64_image" not in result:
        return None
    return base64.b64decode(result["base64_image"])

def recognize_captcha(image_bytes):
    """使用 ddddocr 识别验证码"""
    ocr = ddddocr.DdddOcr()
    return ocr.classification(image_bytes)

def get_latest_download():
    downloads = Path("/root/Downloads")
    files = sorted(downloads.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def safe_prefix(name):
    return name.replace("/", "-").replace("\\", "-").replace(":", "-")

def fill_field(selector, value):
    result, err = run_tool("browser_fill", selector=selector, value=value)
    return result is not None

def click_login():
    result, err = run_tool("browser_click", selector="button:has-text(\"立即登录\")")
    return result is not None

def get_url():
    result, err = run_tool("browser_url")
    return result.get("url", "") if result else ""

def goto(url):
    result, err = run_tool("browser_goto", url=url)
    return result is not None

def eval_js(expr):
    result, err = run_tool("browser_eval", expression=expr)
    return result.get("result") if result else None

def click_export():
    result, err = run_tool("browser_click", selector="a:has-text(\"导出Excel\")")
    return result is not None

def click_warehouse(index):
    """用索引点击仓库按钮"""
    js = f"document.querySelectorAll('#warehouseDisableDiv a')[{index}].click()"
    return eval_js(js) is not None

def save_download(warehouse_name):
    latest = get_latest_download()
    if not latest:
        return None
    prefix = safe_prefix(warehouse_name)
    ts = datetime.now().strftime("%Y%m%d")
    new_name = f"{prefix}_库存结存清单{ts}.xlsx"
    target = DOWNLOADS_DIR / new_name
    shutil.copy(str(latest), str(target))
    return target

def login():
    """登录通途，自动识别验证码"""
    print("导航到登录页面...")
    goto(TONGTU_LOGIN)
    time.sleep(3)

    # 填入账号密码
    print("填入账号密码...")
    fill_field('input[name="username"]', USERNAME)
    fill_field('input[name="password"]', PASSWORD)
    time.sleep(1)

    # 最多尝试 5 次验证码
    for attempt in range(5):
        print(f"\n第 {attempt+1} 次尝试登录...")

        # 截图并识别验证码
        img_bytes = get_captcha_image()
        if not img_bytes:
            print("  截图失败")
            continue

        captcha = recognize_captcha(img_bytes)
        print(f"  ddddocr 识别验证码: {captcha}")

        # 填入验证码
        fill_field('input[name="captcha"]', captcha)
        time.sleep(0.5)

        # 点击登录
        click_login()
        time.sleep(3)

        # 检查是否登录成功
        url = get_url()
        print(f"  当前URL: {url}")

        if "erp102" in url and "passport" not in url:
            print("登录成功！")
            return True

        if "check" in url and "captcha" not in url.lower():
            print("  验证码错误，重试...")
            # 重新填密码（可能被清空）
            fill_field('input[name="password"]', PASSWORD)
            time.sleep(1)
        else:
            print("  可能登录成功，检查中...")
            if "erp102" in url:
                print("登录成功！")
                return True

    print("登录失败！")
    return False

def export_all():
    """导出所有仓库"""
    print("导航到库存结存页面...")
    goto(INVENTORY_URL)
    time.sleep(5)

    # 先切到非 CENTRADE 仓库再切回来（通途 Bug 规避）
    print("触发数据表格加载...")
    click_warehouse(1)  # FZHPoland-covers
    time.sleep(3)
    click_warehouse(0)  # CENTRADE
    time.sleep(5)

    # 仓库索引映射
    wh_indices = {0, 1, 3, 4, 5, 6}  # 对应的 6 个仓库

    for idx in sorted(wh_indices):
        wh_name = WAREHOUSES[sorted(wh_indices).index(idx)]
        print(f"\n导出仓库: {wh_name} (索引 {idx})")

        if idx != 0:
            click_warehouse(idx)
            time.sleep(5)

        click_export()
        time.sleep(3)

        saved = save_download(wh_name)
        if saved:
            print(f"  已保存: {saved.name} ({saved.stat().st_size/1024:.0f} KB)")
        else:
            print("  下载失败！")

def merge():
    """调用 merge_inventory.py 合并"""
    print("\n合并所有仓库...")
    subprocess.run([sys.executable, str(SCRIPT_DIR / "merge_inventory.py")], check=False)

def main():
    if not login():
        print("无法登录，退出")
        sys.exit(1)

    export_all()
    merge()

    print(f"\n完成！文件在: {DOWNLOADS_DIR} 和 {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
