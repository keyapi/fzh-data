---
okf: v0.1
type: Lesson
title: 物料组英文翻译 — 经验教训
description: TMT 管道、Google 翻译并行、SDK 与密钥管理
tags: [en-api, translation, tmt, lesson]
timestamp: 2026-08-31
---

# 物料组英文翻译 — 经验教训

## 1. 生产已填 ≠ 脚本作废

同事用**开源 Google 翻译**先完成了生产 `item_group_translation` 首批填入。TMT 脚本仍保留用于：

- 增量新款 KS/LGKS
- 译文质量修正（先 dry-run Excel 审）
- 迁入 EN App 后的服务端批量

## 2. 424 ≠ 410

用户口头「410 叶子」指 `is_group=0`；脚本还包含 14 个 `is_leaf_group=1` 的 LGKS 叶子组（与 KS 叶子不重叠），合计 **424**。

## 3. TMT SDK 精简包

`TmtClient` 可能只有 `ImageTranslateLLM`，无 `TextTranslateBatchRequest`。用 `client.call("TextTranslate")` 逐条翻译；全量约 5 分钟。

## 4. 密钥分层

| 密钥 | 用途 |
|------|------|
| `fzh` 子账号登录 + MFA | 仅控制台 |
| `tmt-api-translation` CAM API | 脚本 / EN App / 同事调试 |

API 密钥勿在聊天/钉钉明文传播；泄露后在 CAM 新建第二把再禁用旧的。

## 5. 翻译质量

TMT 对家居款式名可用，但：

- 「靠枕」→ pillow / headrest 可能不一致
- `BetterRest`、`BBL` 应作普通词译，非品牌

报关若要求措辞一致，审 Excel 后可固化术语表或后续接 TMT 术语库。

## 6. 与 DeepSeek 分工

| 场景 | 工具 |
|------|------|
| 款式英文名 | TMT / Google / 本脚本 |
| DN 报关聚合物料名 | `customs_export.py` + DeepSeek |

不要指望 DeepSeek 免费额度覆盖 424 条款式名批量任务。
