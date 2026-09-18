---
okf: v0.1
type: Reference
title: 腾讯云机器翻译 TMT 开通与密钥
description: CAM 专用用户、环境变量、连通性验证
tags: [tencent, tmt, cam, translation]
timestamp: 2026-08-31
---

# 腾讯云 TMT 开通与密钥

## 开通步骤

1. [实名认证](https://console.cloud.tencent.com/)
2. [开通机器翻译](https://console.cloud.tencent.com/tmt)（文本翻译 **每月 500 万字符** 免费）
3. [CAM → API 密钥](https://console.cloud.tencent.com/cam/capi) 创建密钥

## 推荐：专用 CAM 用户

| 项 | 建议 |
|----|------|
| 用户名 | `tmt-api-translation`（仅编程访问，无控制台登录） |
| 策略 | `QcloudTMTFullAccess` |
| 用途 | 本仓库脚本、同事调试、未来 EN App |

**不要**把个人登录子账号（如 `fzh@主账号ID`）的主 SecretKey 分给同事或写入 EN。

## 环境变量

```env
TENCENT_SECRET_ID=AKIDxxxxxxxx
TENCENT_SECRET_KEY=xxxxxxxx
TENCENT_TMT_REGION=ap-guangzhou
```

`APPID` 为账号标识，**脚本不需要**。

## 连通性验证

```bash
cd EN_API
uv run python test_tmt_connectivity.py
```

成功输出 `TMT_OK` 及 3 条样例译文。

## TMT vs 混元翻译

| | TMT | 混元 ChatTranslations |
|--|-----|----------------------|
| 免费额度 | 每月 500 万字符 | 首次 100 万 tokens/年（多模型共享） |
| 本批成本 | ≈0 | ≈0 但不可再生 |
| 报关短品名 | 够用 | 可设 Field/术语库，性价比低 |
| API | `tmt.tencentcloudapi.com` TextTranslate | `hunyuan.ai.tencentcloudapi.com` |

款式级批量维护优先 TMT。

## SDK 注意

项目依赖 `tencentcloud-sdk-python-tmt`。若 `TextTranslateBatchRequest` 不存在，使用：

```python
client.call("TextTranslate", {"SourceText": zh, "Source": "zh", "Target": "en", "ProjectId": 0})
```

见 `translate_item_group_names.py`。
