---
okf: v0.1
type: Reference
title: Amazon 在售未配对智能审核
tags: [amazon, pairing, sellfox, review, lightgbm]
timestamp: 2026-08-14
---

# Amazon 在售未配对智能审核

本模块为赛狐 Amazon 在售未配对 Listing 生成只读审核工作簿。它把历史已配对信息分层清洗，先使用严格别名或唯一站点 ASIN 历史证据，再对普通单品生成实验级 Top-3 候选；皮壳、海绵、套件和无法可靠判断的记录单独暂缓。

当前模型没有达到生产门槛，禁止自动配对或调用赛狐写接口。最终决策必须由同事在 Excel 中确认，再用 `import-feedback` 校验并沉淀反馈。

## 运行顺序

```powershell
uv run python -m amazon_pairing.cli build-labels
uv run python -m amazon_pairing.cli snapshot-catalog
uv run python -m amazon_pairing.cli train-pilot
uv run python -m amazon_pairing.cli suggest-active
uv run python -m amazon_pairing.cli import-feedback amazon_pairing/out/Amazon在售未配对智能审核_YYYYMMDD_HHMMSS.xlsx
```

模型、缓存、工作簿和反馈保存在 `amazon_pairing/out/`，该目录已忽略，不提交业务数据。完整口径和已验证快照见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
