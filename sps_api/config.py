#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPS Commerce API 配置。凭据从 .env 读取（不提交 git）。"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent

TOKEN_URL = os.getenv('SPS_TOKEN_URL', 'https://auth.spscommerce.com/oauth/token')
API_BASE = os.getenv('SPS_API_BASE', 'https://api.spscommerce.com')
AUDIENCE = os.getenv('SPS_AUDIENCE', 'https://spscommerce.com')

APP_ID = os.getenv('SPS_APP_ID', '')
APP_SECRET = os.getenv('SPS_APP_SECRET', '')

TOKEN_FILE = BASE_DIR / 'token.json'


def validate():
    missing = [name for name, val in (('SPS_APP_ID', APP_ID), ('SPS_APP_SECRET', APP_SECRET)) if not val]
    if missing:
        raise ValueError(f"缺少必要配置: {', '.join(missing)}，请编辑 {BASE_DIR / '.env'}")


if __name__ == '__main__':
    validate()
    print(f"API_BASE={API_BASE}")
    print(f"TOKEN_URL={TOKEN_URL}")
    print(f"AUDIENCE={AUDIENCE}")
    print(f"APP_ID={APP_ID[:6]}...")
