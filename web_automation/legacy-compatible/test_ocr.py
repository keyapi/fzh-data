#!/usr/bin/env python3
"""
测试 ddddocr 识别通途登录验证码
"""
import ddddocr
import sys
from PIL import Image

def recognize_captcha(image_path):
    """识别验证码图片"""
    ocr = ddddocr.DdddOcr()
    with open(image_path, 'rb') as f:
        img_bytes = f.read()
    result = ocr.classification(img_bytes)
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 test_ocr.py <验证码图片路径>")
        sys.exit(1)
    
    result = recognize_captcha(sys.argv[1])
    print(f"识别结果: {result}")
