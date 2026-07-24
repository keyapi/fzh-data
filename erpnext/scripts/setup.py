#!/usr/bin/env python3
"""ERPNext 凭证检查 — 自动检测并引导配置 API key/secret"""
import os, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_EXAMPLE = PROJECT_ROOT / "EN_API" / ".env.example"
ENV_FILE = PROJECT_ROOT / "EN_API" / ".env"


def load_env(path: Path) -> dict[str, str]:
    """Parse .env file into dict."""
    env = {}
    if not path.is_file():
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def check_prod() -> tuple[bool, str, str]:
    """Check if production API credentials are available. Returns (ok, key, secret)."""
    # 1. Environment variables (highest priority)
    key = os.environ.get("PROD_ERP_API_KEY", "") or os.environ.get("ERP_API_KEY", "")
    secret = os.environ.get("PROD_ERP_API_SECRET", "") or os.environ.get("ERP_API_SECRET", "")
    if key and secret:
        return True, key, secret

    # 2. .env file
    if ENV_FILE.is_file():
        env = load_env(ENV_FILE)
        key = env.get("PROD_ERP_API_KEY", "") or env.get("ERP_API_KEY", "")
        secret = env.get("PROD_ERP_API_SECRET", "") or env.get("ERP_API_SECRET", "")
        if key and secret and "your_" not in key:
            return True, key, secret

    return False, "", ""


def create_env_from_example():
    """Copy .env.example to .env if not exists."""
    if not ENV_EXAMPLE.is_file():
        print(f"✗ 模板文件不存在: {ENV_EXAMPLE}")
        return False

    print(f"创建 {ENV_FILE} 从模板...")
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    ENV_FILE.write_text(content, encoding="utf-8")
    print(f"✓ 已创建 {ENV_FILE}")
    print()
    print("请编辑此文件，填入真实 API 凭证:")
    print(f"  {ENV_FILE}")
    print()
    print("需要填写的字段:")
    print("  PROD_ERP_API_KEY=你的生产环境API Key")
    print("  PROD_ERP_API_SECRET=你的生产环境API Secret")
    return True


def test_connection(key: str, secret: str) -> bool:
    """Test API connectivity with a lightweight query."""
    import urllib.request, ssl, json

    url = "https://erpnext.vilavi.cn/api/method/frappe.auth.get_logged_user"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {key}:{secret}")

    try:
        ctx = ssl.create_default_context()
        resp = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = json.loads(resp.read())
        if "message" in data:
            print(f"✓ 生产系统连接成功 (用户: {data['message']})")
            return True
        else:
            print(f"✓ 生产系统响应正常")
            return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"✗ 认证失败 (401) — API Key/Secret 不正确")
        elif e.code == 403:
            print(f"✗ 权限不足 (403)")
        else:
            print(f"✗ HTTP {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return False


def main():
    print("=" * 50)
    print("ERPNext API 凭证检查")
    print("=" * 50)
    print()

    ok, key, secret = check_prod()

    if ok:
        print("✓ 凭证已配置")
        # Mask for display
        masked_key = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        print(f"  Key: {masked_key}")
        print()

        print("测试生产系统连接 (erpnext.vilavi.cn)...")
        if test_connection(key, secret):
            print()
            print("凭证配置正确，可以开始使用:")
            print("  uv run python erpnext/scripts/fetch.py --month 2026-07")
        return

    # No valid credentials
    print("✗ API 凭证未配置")
    print()

    if not ENV_FILE.is_file():
        create_env_from_example()
        print()
        print("填好 .env 后重新运行:")
        print("  uv run python erpnext/scripts/setup.py")
    else:
        env = load_env(ENV_FILE)
        has_placeholder = any("your_" in v for v in env.values())
        if has_placeholder:
            print(f"  {ENV_FILE} 存在但凭证仍是占位符 (your_xxx_here)")
            print(f"  请编辑此文件填入真实值:")
            print(f"    {ENV_FILE}")
        else:
            print(f"  {ENV_FILE} 存在但无法读取凭证")
            print(f"  请确认文件包含以下字段 (非空):")
            print(f"    PROD_ERP_API_KEY=...")
            print(f"    PROD_ERP_API_SECRET=...")


if __name__ == "__main__":
    main()
