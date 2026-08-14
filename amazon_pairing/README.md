---
okf: v0.1
type: Reference
title: Amazon 在售未配对智能审核
tags: [amazon, pairing, sellfox, review, lightgbm]
timestamp: 2026-08-14
---

# Amazon 在售未配对智能审核

本模块为赛狐 Amazon 在售未配对 Listing 生成只读审核工作簿。高可信优先用**当前已配对**的唯一目标（同 MSKU 跨店、同 ASIN 跨站、parent 家族），不要求 Gold A。cover/foam 走意图分类而不是子串。LTR 只给剩余普通单品打实验候选。

当前模型没有达到生产门槛，禁止自动配对或调用赛狐写接口。最终决策必须由同事在 Excel 中确认，再用 `import-feedback` 校验并沉淀反馈。

## 运行顺序

```powershell
uv run python -m amazon_pairing.cli audit-propagation --cache-workspace D:\Work\赛狐\Cursor
uv run python -m amazon_pairing.cli suggest-active --cache-workspace D:\Work\赛狐\Cursor
# 训练标签 / LTR 试点（证据传播分支默认不要重跑）
uv run python -m amazon_pairing.cli build-labels --cache-workspace D:\Work\赛狐\Cursor
uv run python -m amazon_pairing.cli snapshot-catalog --cache-workspace D:\Work\赛狐\Cursor
uv run python -m amazon_pairing.cli train-pilot
uv run python -m amazon_pairing.cli import-feedback amazon_pairing/out/Amazon在售未配对智能审核_YYYYMMDD_HHMMSS.xlsx
```

模型、缓存、工作簿和反馈保存在 `amazon_pairing/out/`，该目录已忽略，不提交业务数据。完整口径和已验证快照见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
