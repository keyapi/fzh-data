---
okf: v0.1
type: Log
title: EN_API 文档变更日志
---

# 变更日志

## 2026-08-31

- **文档**: 新增 OKF bundle（物料组翻译 TMT 管道）、`AGENT_HANDOFF_物料组翻译.md`、skill `item-group-translation`
- **背景**: 生产 `item_group_translation` 已由同事用开源 Google 翻译填入；保留 TMT 脚本供后续维护
- **代码**: `translate_item_group_names.py`、`test_tmt_connectivity.py`；依赖 `tencentcloud-sdk-python-tmt`

## 2026-08-28

- **脚本**: 首版 `translate_item_group_names.py` dry-run 424/424 TMT 成功
- **密钥**: 专用 CAM 用户 `tmt-api-translation`（`QcloudTMTFullAccess`）
