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
  用你自己的 EN 内部账号（System User）生成即可；**当前策略：EN 内部账号都能拉包（含 API Key 调用）**，
  匿名 403；后续如需收紧，在服务端下载方法里加角色判断即可，客户端不用改。
- `doctor` / `recommend` / `batch` 只用已下载的包，不需要凭证；`pull` / `refresh` 需要。
- `recommend`：回放 pack（as_of 固定）。
- `refresh`：拉 EN 实时库存、复用 pack 的 D5 预测重算；**不重训 D5**，报告标 `forecast reused`。

口径：D6 q95 − C/EN/PO/SO/CG；催已有与新补分开；未知不补 0；数据包有版本/as_of/哈希。

## 数据包管理（管理员）

1. zip 分卷放在站点 `private/files/`（文件名固定 `supply-copilot-pack-<version>.partNNN`）；
2. 由 `key_test` 的 `key_test.demand_collaboration.pack_download.get_part` 下发：
   登录即可下载、匿名 403、只允许该前缀的分卷；
3. 客户端 `pull` 通过 `FZH_PACK_METHOD`（默认上述方法）取分卷；换部署时改这个变量即可。
