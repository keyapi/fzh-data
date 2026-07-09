---
okf: v0.1
type: Index
title: 技术参考索引
description: 赛狐 API 签名、认证等技术参考文档目录
tags: [sellfox, api-proxy, reference, index]
---

# 技术参考

## 赛狐 API 参考（来自 SELLFOX_API 项目）

| 文档 | 位置 |
|------|------|
| 获取 Access Token | [SELLFOX_API](../../SELLFOX_API/docs/api-reference/开发指南/获取%20Access%20Token.md) |
| 生成 sign（签名） | [SELLFOX_API](../../SELLFOX_API/docs/api-reference/开发指南/生成sign（签名）.md) |
| 公共请求参数 | [SELLFOX_API](../../SELLFOX_API/docs/api-reference/开发指南/公共请求参数.md) |
| 公共报错 | [SELLFOX_API](../../SELLFOX_API/docs/api-reference/开发指南/公共报错.md) |
| 16 条踩坑教训 | [SELLFOX_API](../../SELLFOX_API/docs/lessons/2026-06-25-sellfox-integration-lessons.md) |

## 赛狐 API 签名算法（已验证）

来源: `SELLFOX_API/fetch_ad_reports.py:55-69`

```python
def signed_post(url_path, body=None):
    ts = str(int(time.time() * 1000))
    nonce = str(random.randint(1, 99999))
    sign_params = {
        "access_token": ACCESS_TOKEN,
        "client_id": APP_ID,
        "method": "post",
        "nonce": nonce,
        "timestamp": ts,
        "url": url_path,
    }
    sorted_str = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
    sig = hmac.new(APP_SECRET.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()
    query = f"access_token={ACCESS_TOKEN}&client_id={APP_ID}&nonce={nonce}&timestamp={ts}&sign={sig}"
    full_url = f"{DOMAIN}{url_path}?{query}"
    # ... POST with urllib
```

## 代码参考

| 来源 | 内容 |
|------|------|
| `SELLFOX_API/fetch_ad_reports.py` | 完整 HMAC 签名 + OAuth2 Token 获取（urllib 实现，生产验证） |
| `SELLFOX_API/config.json` | 赛狐 API 配置结构 |
| `new-api-dingtalk-oidc/main.py` | FastAPI lifespan + httpx 参考 |
| `new-api-dingtalk-oidc/Dockerfile` | Docker 部署模板 |
