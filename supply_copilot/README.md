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
  用你自己的 EN 登录账号生成即可；**当前策略：任何能登录 EN 的用户（含 API Key 调用）都能拉包**，
  匿名 403；后续如需收紧，在服务端下载方法里加角色判断即可，客户端不用改。
- `doctor` / `recommend` / `batch` 只用已下载的包，不需要凭证；`pull` / `refresh` 需要。
- `recommend`：回放 pack（as_of 固定）。
- `refresh`：拉 EN 实时库存、复用 pack 的 D5 预测重算；**不重训 D5**，报告标 `forecast reused`。

口径：D6 q95 − C/EN/PO/SO/CG；催已有与新补分开；未知不补 0；数据包有版本/as_of/哈希。

## 工作台静态页（v2.1，只读）

只消费 A 的冻结 release，不按目录「最新文件」混装。渲染前校验 manifest 与每个 artifact 的
sha256/size，任何一项不符整批拒绝：

```bash
uv run python -m supply_copilot.workbench_page \
  --release-dir D:/Work/fzh-order-store/analysis/workbench-latest-20261124/releases/20261125T095418+0800/ \
  --out D:/private/demand/v21/workbench-v21.html
```

- `--release-dir` 读取并校验 `release_manifest.json` → `snapshot_v2.json` + `baseline_v2.json`；
  也可用 `--snapshot/--baseline` 直接指定松散文件（开发/测试）。
- 页头：display_version / release_id / parent_bundle / 期间 / as_of / computed_at / branch。
- A1 gate：整体 gate 关闭贯穿主表、详情、分析、导出；`row_can_order` 恒 false。
- A2：demand.origin 五类、quantile_status 四类、stock `used_in_decision` + 决策时/浏览时新鲜度、
  SO 决策证据 82 键/142 条/6,414 件（duplicate_form 不重复计）。
- A3：需求基准页签改用 baseline_v2，按完整键（SKU×形态×单位×期间×仓×池）关联，不按 SKU 继承。
- 导出：CSV 带 gate、blocked 原因、origin/quantile、period、bundle/display_version。

## 数据包管理（管理员）

1. zip 分卷放在站点 `private/files/`（文件名固定 `supply-copilot-pack-<version>.partNNN`）；
2. 由 `key_test` 的 `key_test.demand_collaboration.pack_download.get_part` 下发：
   登录即可下载、匿名 403、只允许该前缀的分卷；
3. 客户端 `pull` 通过 `FZH_PACK_METHOD`（默认上述方法）取分卷；换部署时改这个变量即可。
