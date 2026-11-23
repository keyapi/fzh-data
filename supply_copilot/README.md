# Supply Copilot（只读回放）

给外部 Agent/同事用：公共仓库放代码，客户数据放 EN 私有包（`FZH_DATA_ROOT`）。

```bash
uv sync
export ERP_API_KEY=... ERP_API_SECRET=... FZH_DATA_ROOT=D:/data/supply-copilot
uv run python -m supply_copilot doctor
uv run python -m supply_copilot pull
uv run python -m supply_copilot recommend --branch USNJ --sku KS0001-XMMBS-194-HEMPNATURAL
uv run python -m supply_copilot refresh --branch USNJ --sku KS0001-XMMBS-194-HEMPNATURAL
```

- `recommend`：回放 pack（as_of 固定）。
- `refresh`：拉 EN 实时库存、复用 pack 的 D5 预测重算；**不重训 D5**，报告标 `forecast reused`。

口径：D6 q95 − C/EN/PO/SO/CG；催已有与新补分开；未知不补 0；数据包有版本/as_of/哈希。
