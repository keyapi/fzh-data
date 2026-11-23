---
name: supply-decision-copilot
description: >
  Supply-chain A/B/C/D/E decision replay for FZH branches (USNJ/USTX/Poland).
  Use when asked "某 SKU 给某分公司要不要补、补多少、何时补、为什么",
  or to run doctor/pull/recommend for the private supply-copilot pack.
---

# Supply Decision Copilot

只读回放，不直接下单。公共仓库只有代码；客户数据在 EN 私有包。

## Prerequisites
- EN API key/secret (`ERP_API_KEY`, `ERP_API_SECRET`) —— **自己的账号**，需 System Manager 角色（`pull`/`refresh` 用）；
  不存在也不需要 `ADMIN_ERP_API_KEY` 等变量。
- Private data root `FZH_DATA_ROOT`
- `uv sync`

## Commands
```bash
uv run python -m supply_copilot doctor
uv run python -m supply_copilot pull
uv run python -m supply_copilot recommend --branch USNJ --sku <SKU> [--json]
uv run python -m supply_copilot refresh --branch USNJ --sku <SKU>
```

`recommend` = replay（pack as_of 固定）。`refresh` = EN 实时库存 + 复用 pack 的 D5 预测重算缺口；**不是 D5 重新训练**，输出会明确标注。

## Explainability contract
1. 结论：补/催已有/不补/暂不能判断。
2. 为什么：D6 动作原因 + 需求 q50/q90/q95 + C/EN/PO/SO/CG + 净需求。
3. 时点与来源：包版本/as_of、D5 模型、D3b 回测；未知不补 0。
4. 不下单；采购/运营需复核；数据过期或权限不足时拒绝确定建议。
