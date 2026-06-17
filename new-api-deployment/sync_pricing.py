"""
DeepSeek 定价同步脚本
用法: python sync_pricing.py
如需定时任务（如每天检查），可用 Windows 任务计划程序调用此脚本
"""
import json, urllib.request, base64, os, sys

# ========== 配置区 ==========
API_BASE = "http://localhost:3000"
USERNAME = "root"
PASSWORD = "admin123456"

# DeepSeek V4 官方定价（单位：人民币元/1M tokens）
# 上游调价时，只需修改这里
PRICING = {
    "deepseek-v4-flash": {
        "input": 1.00,    # 输入（缓存未命中）
        "output": 2.00,   # 输出
        "cache": 0.02,    # 输入（缓存命中）
    },
    "deepseek-v4-pro": {
        "input": 3.00,
        "output": 6.00,
        "cache": 0.025,
    }
}

QUOTA_PER_UNIT = 500000  # $1 = 500,000 额度
USD_RATE = 7.3            # 1 USD = 7.3 RMB
# ============================

def api(method, path, data=None):
    url = f"{API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {e.read().decode()}")
        return None

def login():
    result = api("POST", "/api/user/login",
                 json.dumps({"username": USERNAME, "password": PASSWORD}).encode())
    if result and result.get("success"):
        print("  登录成功")
        return True
    print("  登录失败")
    return False

def get_option(key):
    result = api("GET", f"/api/option/?key={key}")
    if result and result.get("data"):
        for o in result["data"]:
            if o["key"] == key:
                try:
                    return json.loads(o["value"])
                except:
                    return o["value"]
    return None

def update_option(key, value):
    result = api("PUT", "/api/option/",
                 json.dumps({"key": key, "value": json.dumps(value, ensure_ascii=False)}).encode())
    return result and result.get("success")

def main():
    print("=" * 50)
    print("DeepSeek 定价同步")
    print("=" * 50)

    if not login():
        sys.exit(1)

    for model, prices in PRICING.items():
        print(f"\n--- {model} ---")
        # 计算 ModelRatio: input_price = MR * 1e6 / QPU * rate
        # MR = input_price / (1e6 / QPU * rate) = input_price * QPU / (1e6 * rate)
        mr = prices["input"] * QUOTA_PER_UNIT / (1_000_000 * USD_RATE)
        print(f"  ModelRatio = {mr:.6f} (输入 ¥{prices['input']}/1M)")

        # CompletionRatio: output / input
        comp_r = prices["output"] / prices["input"]
        print(f"  CompletionRatio = {comp_r} (输出 ¥{prices['output']}/1M)")

        # CacheRatio: cache / input
        cache_r = prices["cache"] / prices["input"]
        print(f"  CacheRatio = {cache_r} (缓存 ¥{prices['cache']}/1M)")

    print("\n请手动在后台更新，或使用数据库方式写入。")
    print("后台路径: 设置 → 运营设置 → 模型定价")

if __name__ == "__main__":
    main()
