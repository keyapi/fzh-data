"""
赛狐 OpenAPI 连通性测试脚本
用法: python test_sellfox_api.py
自动读取 advertise/.env 中的凭证
"""
import os
import sys
import json
import requests

# 读取 .env 文件
def load_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

# 加载凭证
script_dir = os.path.dirname(os.path.abspath(__file__))
env = load_env(os.path.join(script_dir, '.env'))
env.update({k: v for k, v in os.environ.items() if v})  # 环境变量优先

APP_ID = env.get("SELLFOX_APP_ID", "")
APP_SECRET = env.get("SELLFOX_APP_SECRET", "")
DOMAIN = env.get("SELLFOX_API_DOMAIN", "https://openapi.sellfox.com")

print("=" * 60)
print("赛狐 OpenAPI 连通性测试")
print(f"API 域名: {DOMAIN}")
print(f"App ID: {APP_ID}")
print(f"App Secret: {APP_SECRET[:8]}...")
print("=" * 60)

if not APP_ID or not APP_SECRET:
    print("\n❌ 未找到凭证！请确保 advertise/.env 文件存在且包含:")
    print("  SELLFOX_APP_ID=<SELLFOX_APP_ID>")
    print("  SELLFOX_APP_SECRET=<your-secret>")
    sys.exit(1)

# 检查当前公网 IP
print("\n[0] 检查当前 IP...")
try:
    ip = requests.get("https://ifconfig.me", timeout=5).text.strip()
    print(f"  当前 IP: {ip}")
    if ip == "123.117.236.65":
        print("  ✅ 北京办公室 IP，应在白名单内")
    elif ip == "82.156.238.248":
        print("  ✅ VPS IP，应在白名单内")
    else:
        print(f"  ⚠️  非白名单 IP，以下测试可能失败")
except:
    print("  无法获取公网 IP")

# 测试 1: 基础连通
print("\n[1] 基础连通性...")
try:
    r = requests.get(f"{DOMAIN}/", timeout=10)
    print(f"  {DOMAIN}/: HTTP {r.status_code}")
except Exception as e:
    print(f"  ❌ {e}")

# 测试 2: Swagger 端点（尝试多种认证方式）
print("\n[2] 认证测试（尝试多种方式获取 API 文档）...")

import hmac, hashlib, base64, time as t, uuid

auth_patterns = []

# Pattern A: Basic Auth
auth_patterns.append(("Basic Auth", {
    "Authorization": f"Basic {base64.b64encode(f'{APP_ID}:{APP_SECRET}'.encode()).decode()}"
}))

# Pattern B: Bearer token
auth_patterns.append(("Bearer Token", {
    "Authorization": f"Bearer {APP_SECRET}"
}))

# Pattern C: API Key header
for key_name in ["x-api-key", "X-API-Key", "api-key", "X-App-Secret", "X-Client-Secret"]:
    auth_patterns.append((f"Header: {key_name}", {
        key_name: APP_SECRET,
        "X-App-Id": APP_ID
    }))

# Pattern D: Query params
auth_patterns.append(("Query params", {}))  # Will append to URL

# Pattern E: HMAC (common Chinese API pattern)
ts = str(int(t.time() * 1000))
nonce = str(uuid.uuid4())
sign_str = f"{APP_ID}\n{ts}\n{nonce}"
sig = base64.b64encode(hmac.new(APP_SECRET.encode(), sign_str.encode(), hashlib.sha256).digest()).decode()
auth_patterns.append(("HMAC Header", {
    "X-App-Id": APP_ID,
    "X-Timestamp": ts,
    "X-Nonce": nonce,
    "X-Signature": sig
}))

auth_patterns.append(("HMAC Authorization", {
    "Authorization": f"HMAC-SHA256 AppId={APP_ID},Timestamp={ts},Nonce={nonce},Signature={sig}"
}))

# Try all patterns on /v2/api-docs
for name, headers in auth_patterns:
    url = f"{DOMAIN}/v2/api-docs"
    if name == "Query params":
        url += f"?app_id={APP_ID}&app_secret={APP_SECRET}"
        headers = {}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"  ✅ {name}: HTTP 200! 文档长度={len(r.text)}")
            # 保存文档
            doc_path = os.path.join(script_dir, "sellfox_openapi.json")
            try:
                data = r.json()
                with open(doc_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"  📄 已保存到: {doc_path}")
                # 统计端点
                paths = data.get("paths", {})
                print(f"  📊 API 端点数: {len(paths)}")
                tags = set()
                for p in paths.values():
                    for method in p.values():
                        for tag in method.get("tags", []):
                            tags.add(tag)
                print(f"  📊 模块标签: {sorted(tags)}")
                break
            except:
                print(f"  (非 JSON 响应，无法解析)")
        elif r.status_code == 401:
            pass  # Expected for wrong auth
        else:
            print(f"  {name}: HTTP {r.status_code}")
    except Exception as e:
        pass

# 测试 3: 如果认证成功，试试广告端点
print("\n[3] 尝试访问广告相关数据...")
# 先不预设端点，等认证成功后再说

print("\n" + "=" * 60)
print("测试完成。如果所有认证方式都返回 401，请检查:")
print("  1. 当前 IP 是否在赛狐后台白名单中")
print("  2. App ID / App Secret 是否正确")
print("  3. 赛狐 API 账号的权限是否已开启")
print("=" * 60)
