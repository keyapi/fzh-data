---
okf: v0.1
type: Reference
title: Amazon 在售未配对智能审核
tags: [amazon, pairing, sellfox, review, evidence-graph]
timestamp: 2026-08-14
---

# Amazon 在售未配对智能审核

本模块为赛狐 Amazon 在售未配对 Listing 生成只读证据图审核工作簿。V2 先通过 MSKU/ASIN/FNSKU/图片/标题/父 ASIN/父 SKU 传播历史目标，再结合 EN 对象、颜色和尺寸本体检索；低证据候选单列，仍不写赛狐。

## 运行

```powershell
uv run python -m amazon_pairing.cli train-family
uv run python -m amazon_pairing.cli suggest-v2 --output amazon_pairing/out/Amazon在售未配对证据图审核_YYYYMMDD_HHMMSS.xlsx
```

模型、缓存、工作簿和反馈保存在 `amazon_pairing/out/`，该目录已忽略。完整口径和已验证快照见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
