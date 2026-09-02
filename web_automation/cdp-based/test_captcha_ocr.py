#!/usr/bin/env python3
"""从 CDP 浏览器提取验证码图片并识别"""
import subprocess, json, base64, sys
import ddddocr
from pathlib import Path

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

# 获取验证码图片的 src
result = run_tool("browser_eval", expression='document.querySelector("img[alt=验证码]").src')
print("Result:", result)

if result and "result" in result:
    src = result["result"]
    print(f"验证码 src: {src[:100]}...")
    
    # 如果是 data URI，直接解码
    if src.startswith("data:image"):
        base64_data = src.split(",")[1]
        img_bytes = base64.b64decode(base64_data)
        with open("/workspace/fzh-web-automation/captcha_img.png", "wb") as f:
            f.write(img_bytes)
        
        ocr = ddddocr.DdddOcr()
        captcha = ocr.classification(img_bytes)
        print(f"识别结果: {captcha}")
    else:
        # 截图获取
        result2 = run_tool("browser_screenshot")
        if result2 and "base64_image" in result2:
            img_bytes = base64.b64decode(result2["base64_image"])
            ocr = ddddocr.DdddOcr()
            captcha = ocr.classification(img_bytes)
            print(f"整页截图识别结果: {captcha}")
