---
okf: v0.1
type: Reference
title: Amazon 账期 txt Tax 本地管道
description: 运行 run_period_tax.py，替代 Colab 税账期 notebook 的 Tax 产出
---

# Amazon 账期 txt Tax

见 [AGENT_HANDOFF.md](../AGENT_HANDOFF.md)。

```powershell
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket 账期20261004-20261103 --exchange-month 202610 --write-gsheet
```
