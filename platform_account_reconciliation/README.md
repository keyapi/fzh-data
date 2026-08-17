# platform_account_reconciliation — 平台账期对账

Overstock / OSTK 账期（Payment Summary + Detail）与 EN 生产系统 `Tongtool Order` 的费用级对账。未来可扩展 Wayfair `WFUS` 账期。

## 快速开始

```bash
uv run python platform_account_reconciliation/scripts/reconcile_ostkus.py \
  --account "D:/Work/尹/OSTKUS-2026-07-01.xlsx" \
  --account "D:/Work/尹/OSTKUS-2026-07-16.xlsx" \
  --out "D:/Work/尹/OSTKUS费用级核对.xlsx"
```

默认读取 `EN_API/.env` 中的生产 ERPNext 凭证，只读拉取 `Tongtool Order`。不想调用 EN 时加 `--no-en`。

## 文档

- 新 Agent 先读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)
- 自动触发 Skill：[platform-account-reconciliation](../.agents/skills/platform-account-reconciliation/SKILL.md)
- OKF 索引：[docs/index.md](docs/index.md)
