#!/usr/bin/env python3
"""从通途页面获取验证码图片并识别"""
import requests, ddddocr, json, subprocess, base64, time
from PIL import Image
from io import BytesIO

COMPUTER_TOOL = "/root/.codebuddy/skills/computer-use/scripts/computer_tool.py"

def run_tool(action, **kwargs):
    args = {"action": action, **kwargs}
    cmd = ["python3", COMPUTER_TOOL, json.dumps(args)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    out = result.stdout
    json_start = out.find('{"')
    if json_start < 0:
        return None
    return json.loads(out[json_start:])

# 方法1: 下载验证码图片URL
result = run_tool("browser_eval", expression='document.querySelector("img[alt=验证码]").src')
if result and "result" in result:
    captcha_url = result["result"]
    print(f"验证码URL: {captcha_url}")
    
    # 从浏览器获取 cookies
    cookies_result = run_tool("browser_eval", expression='document.cookie')
    cookies = cookies_result.get("result", "") if cookies_result else ""
    print(f"Cookies: {cookies[:100]}...")
    
    # 用 requests 下载（需要带 cookies）
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Referer": "https://passport.tongtool.com/"
    }
    
    # 从 CDP 获取 cookies 并设置
    if cookies:
        for c in cookies.split(";"):
            if "=" in c:
                k, v = c.strip().split("=", 1)
                session.cookies.set(k, v)
    
    resp = session.get(captcha_url, headers=headers)
    print(f"下载状态: {resp.status_code}, 大小: {len(resp.content)}")
    
    if resp.status_code == 200:
        with open("/workspace/fzh-web-automation/captcha.jpg", "wb") as f:
            f.write(resp.content)
        
        # ddddocr 识别
        ocr = ddddocr.DdddOcr()
        result_text = ocr.classification(resp.content)
        print(f"ddddocr 识别结果: {result_text}")
        
        # 也试试从截图截取验证码区域
        img = Image.open(BytesIO(resp.content))
        print(f"图片尺寸: {img.size}")
