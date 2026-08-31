#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SPS Commerce access token 获取。

优先用 Machine-to-Machine（client_credentials）流：只需 App ID + App Secret，
不需要 Redirect URI，适合公司代表自己连接 SPS（官方文档明确推荐此场景用 M2M）。

token 会被缓存到 token.json 并按 expires_in 复用（官方要求缓存复用，避免被限流）。
如果当前 App 是 Web Service 类型导致 client_credentials 失败，请到 Dev Center
创建一个 Machine-to-Machine 类型的 App，复制新的 Sandbox App ID/Secret 到 .env。
"""
import json
import time
import urllib.error
import urllib.request

from config import APP_ID, APP_SECRET, AUDIENCE, TOKEN_FILE, TOKEN_URL, validate


def _request_token():
    body = json.dumps({
        'grant_type': 'client_credentials',
        'client_id': APP_ID,
        'client_secret': APP_SECRET,
        'audience': AUDIENCE,
    }).encode('utf-8')
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def get_token(force=False):
    """返回 access_token。force=True 时强制重新获取。"""
    validate()
    if not force and TOKEN_FILE.exists():
        try:
            cached = json.loads(TOKEN_FILE.read_text('utf-8'))
            if cached.get('expires_at', 0) > time.time() + 60:
                return cached['access_token']
        except (ValueError, KeyError):
            pass

    try:
        data = _request_token()
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')
        print(f"[错误] HTTP {e.code} 获取 token 失败: {detail}")
        if 'unsupported_grant_type' in detail or 'grant_type' in detail:
            print(
                "[提示] 当前 App 可能不是 Machine-to-Machine 类型。"
                "请到 Dev Center Applications 新建一个类型为 "
                "Machine-to-Machine Application 的 App，用它的 Sandbox App ID/Secret。"
            )
        raise

    access_token = data['access_token']
    expires_in = int(data.get('expires_in', 3600))
    cache = {
        'access_token': access_token,
        'expires_at': time.time() + expires_in,
    }
    TOKEN_FILE.write_text(json.dumps(cache, indent=2), 'utf-8')
    print(f"[OK] 获取到 access token（有效 {expires_in}s，已缓存到 {TOKEN_FILE.name}）")
    return access_token


if __name__ == '__main__':
    token = get_token(force=True)
    print(token[:40] + '...')
