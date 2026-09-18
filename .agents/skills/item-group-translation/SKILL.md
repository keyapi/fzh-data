---
name: item-group-translation
description: >
  EN 生产物料组 item_group_translation 批量中译英。脚本 translate_item_group_names.py
  使用腾讯云 TMT（或 --fetch-only 仅拉名单）。触发词：物料组翻译、item_group_translation、
  款式英文、报关英文名、TMT、腾讯翻译、物料组英文。
compatibility: >
  需要 requests, pandas, openpyxl, tencentcloud-sdk-python-tmt。
  凭证：EN_API/.env 中 ERP_API_* 与 TENCENT_SECRET_*。
metadata:
  module: EN_API
  scripts: translate_item_group_names.py, test_tmt_connectivity.py
  updated: 2026-08-31
---

# 物料组英文翻译（TMT）

## 何时加载

- 批量翻译 EN Item Group `item_group_translation`
- 报关款式级英文品名维护
- 腾讯云 TMT 密钥配置或连通性排查

## 快速命令

```bash
cd EN_API
uv run python test_tmt_connectivity.py              # 冒烟
uv run python translate_item_group_names.py --dry-run
uv run python translate_item_group_names.py --apply   # 需用户确认
```

## 必读

1. [`EN_API/AGENT_HANDOFF_物料组翻译.md`](../../EN_API/AGENT_HANDOFF_物料组翻译.md)
2. [`docs/solutions/tooling-decisions/en-item-group-tencent-tmt-translation.md`](../../docs/solutions/tooling-decisions/en-item-group-tencent-tmt-translation.md)

## 铁律

- 默认 `--dry-run`，写生产必须用户确认
- 专用 CAM 用户 `tmt-api-translation`，勿泄露个人子账号密钥
- 生产首批可能已由同事 Google 翻译填入；本管道用于增量/修正
- `BetterRest`/`BBL` 非品牌
