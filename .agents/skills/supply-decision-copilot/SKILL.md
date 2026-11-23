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
- EN API key/secret (`ERP_API_KEY`, `ERP_API_SECRET`) —— **自己的 EN 内部账号**；
  当前任何 EN 内部账号（System User）都可 `pull`（匿名/门户账号 403）；不存在也不需要 `ADMIN_ERP_API_KEY`。
- Private data root `FZH_DATA_ROOT`
- `uv sync`

## Commands
```bash
uv run python -m supply_copilot doctor
uv run python -m supply_copilot pull
uv run python -m supply_copilot recommend --branch USNJ --sku <SKU> [--json]
uv run python -m supply_copilot refresh --branch USNJ --sku <SKU>
uv run python -m supply_copilot supply --branch USNJ     # 实时库存/开放SO/开放PO → <root>/live/
uv run python -m supply_copilot decide --branch USNJ     # 当天候选 + 可执行性
uv run python -m supply_copilot history                  # 历史 parquet 状态
uv run python -m supply_copilot pull-history             # 从 EN 私有目录取历史 parquet
```

`recommend` = replay（pack as_of 固定）。`refresh` = EN 实时库存 + 复用 pack 的 D5 预测重算缺口；**不是 D5 重新训练**。
`decide` = 实时库存 + 开放 SO/PO 重算；报告开头有 **可执行性（是/否）** 与原因。
当前默认口径一般是「否」：需求仍是 D6 q95（as_of 2026-11-13）、PO 未映射到分公司仓、CG 未按实时重算、需要日/下单日沿用 D6 且可能已过期。不得把 `decide` 的候选当作可直接下单的指令。

历史订单/需求是 parquet 快照（截止 2026-10-26），放在 EN 私有目录，不打包、不由每个 Agent 拉 EN 订单；只在重训预测/复核明细时 `pull-history`。

## Explainability contract
1. 结论：补/催已有/不补/暂不能判断。
2. 为什么：D6 动作原因 + 需求 q50/q90/q95 + C/EN/PO/SO/CG + 净需求。
3. 时点与来源：包版本/as_of、D5 模型、D3b 回测；未知不补 0。
4. 不下单；采购/运营需复核；数据过期或权限不足时拒绝确定建议。
