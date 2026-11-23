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

- **凭证：只有 `ERP_API_KEY` / `ERP_API_SECRET`，没有也不需要 `ADMIN_ERP_API_KEY`。**
  用你自己的 EN 账号（System Manager 角色）生成；不要用别人的 key。
  `pull` 下载私有 File 时，Frappe 只认上传者本人或挂靠单据的可读角色——
  数据包已挂靠到 System Manager 专属的 `usnj-supply-copilot` Page，所以你的 System Manager 账号可直接拉取。
- `doctor` / `recommend` / `batch` 只用已下载的包，不需要凭证；`pull` / `refresh` 需要。
- `recommend`：回放 pack（as_of 固定）。
- `refresh`：拉 EN 实时库存、复用 pack 的 D5 预测重算；**不重训 D5**，报告标 `forecast reused`。

口径：D6 q95 − C/EN/PO/SO/CG；催已有与新补分开；未知不补 0；数据包有版本/as_of/哈希。

## 数据包管理（管理员）

1. zip 分卷上传到 EN `File`（`is_private=1`），得到 `/private/files/...` 地址；
2. 把每个分卷 File 的 `attached_to_doctype` / `attached_to_name` 设为
   `Page` / `usnj-supply-copilot`（该 Page 只授予 System Manager 读取）；
3. 之后任何 System Manager 用自己的 API Key 都能 `pull`；未挂靠时只有上传者本人能拉。
   （Page fixture 见 key_test 仓库；部署前先确认页面存在。）
