---
okf: v0.1
type: Reference
title: 渠道账号 Google 表 → EN Channel Account
description: 把运营共享表里的渠道账号对账并写入生产 ERPNext。
---

# 渠道账号同步

运营在 Google 表维护渠道店铺；生产 EN `Channel Account` 需要跟表。默认只对比、不写。

完整规则：[AGENT_HANDOFF.md](AGENT_HANDOFF.md) 与 [已解决问题](../docs/solutions/workflow-issues/en-channel-account-gsheet-sync.md)。

```powershell
uv run python channel_account_sync/fetch_sources.py
uv run python channel_account_sync/compare.py
uv run python channel_account_sync/apply.py
```

用户确认计划后再：

```powershell
uv run python channel_account_sync/apply.py --apply
```

报告在 `channel_account_sync/out/`（不入库）。单测：

```powershell
uv run pytest channel_account_sync/tests -q
```
