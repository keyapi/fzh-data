#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SPS Commerce 自动化配置文件
管理登录凭据和其他设置

配置使用情况:
- 已使用: email, password, login_wait, page_load_wait, action_wait (5项)
- 未使用: 其他配置项均未在代码中实际使用，保留用于未来扩展 (12项)
"""

import os

# 尝试加载环境变量（如果 dotenv 可用）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # 如果没有安装 python-dotenv，跳过加载 .env 文件
    pass

# SPS Commerce 配置
SPS_CONFIG = {
    # 登录凭据 - 从环境变量读取，如果没有则使用默认值 (已使用)
    'email': os.getenv('SPS_EMAIL', 'us@mxdeals.com'),  # 已使用
    'password': os.getenv('SPS_PASSWORD', 'Fangzhouhui@1023'),  # 已使用
    
    # 浏览器设置 (未使用 - 代码中硬编码)
    'headless': os.getenv('HEADLESS', 'true').lower() == 'true',  # 未使用
    'window_size': os.getenv('WINDOW_SIZE', '1280,720'),  # 未使用
    
    # 等待时间设置（秒）
    'login_wait': int(os.getenv('LOGIN_WAIT', '120')),  # 已使用
    'page_load_wait': int(os.getenv('PAGE_LOAD_WAIT', '60')),  # 已使用
    'element_wait': int(os.getenv('ELEMENT_WAIT', '30')),  # 未使用
    'action_wait': int(os.getenv('ACTION_WAIT', '10')),  # 已使用
    
    # 日期偏移设置 (未使用 - 代码中硬编码为 7)
    'day_offset': int(os.getenv('DAY_OFFSET', '7')),  # 未使用
    
    # 路径设置 (未使用 - 已改为本地路径或自动管理)
    'chromedriver_path': os.getenv('CHROMEDRIVER_PATH', '/usr/local/bin/chromedriver'),  # 未使用 - 改用 webdriver-manager
    'screenshots_dir': os.getenv('SCREENSHOTS_DIR', 'screenshots/'),  # 未使用 - 硬编码为 screenshots/
    'logs_dir': os.getenv('LOGS_DIR', 'logs/'),  # 未使用 - 硬编码为 logs/
    
    # 模板设置 (未使用 - 代码中硬编码)
    'template_cutoff_date': os.getenv('TEMPLATE_CUTOFF_DATE', '2025-10-02'),  # 未使用
    'template_before_cutoff': os.getenv('TEMPLATE_BEFORE_CUTOFF', 'IA Template 20250925 0xBlack138 till1009'),  # 未使用
    'template_after_cutoff': os.getenv('TEMPLATE_AFTER_CUTOFF', 'IA Template 20250605 x100'),  # 未使用
    
    # 重试设置 (未使用 - 代码中硬编码)
    'max_retries': int(os.getenv('MAX_RETRIES', '3')),  # 未使用 - tenacity 装饰器中硬编码为 3
    'retry_delay': int(os.getenv('RETRY_DELAY', '30')),  # 未使用
}

# 验证必要的配置
def validate_config():
    """验证配置是否完整"""
    required_fields = ['email', 'password']
    missing_fields = []
    
    for field in required_fields:
        if not SPS_CONFIG.get(field):
            missing_fields.append(field)
    
    if missing_fields:
        raise ValueError(f"缺少必要的配置项: {', '.join(missing_fields)}")
    
    return True

# 打印配置信息（隐藏敏感信息）
def print_config():
    """打印配置信息（隐藏密码）"""
    config_copy = SPS_CONFIG.copy()
    config_copy['password'] = '*' * len(config_copy['password'])
    
    print("=== SPS 自动化配置 ===")
    for key, value in config_copy.items():
        print(f"{key}: {value}")
    print("=" * 25)

if __name__ == "__main__":
    validate_config()
    print_config()
