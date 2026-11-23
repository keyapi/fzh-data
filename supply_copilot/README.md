# Supply Copilot（只读补货决策）

公共仓库放代码，客户数据放 EN 私有包（`FZH_DATA_ROOT`）。给同事 / 老板的 Agent 用：
**问补货问题 → 得到 A/B/C/D/E 证据链 + 建议**，不直接下单。

## 3 分钟起步

```bash
git clone https://github.com/keyapi/fzh-data.git
cd fzh-data && uv sync

# 1) 准备一个空目录放私有数据包（不要在仓库里）
#    Windows PowerShell:
$env:ERP_API_KEY="<你的EN内部账号key>"
$env:ERP_API_SECRET="<你的secret>"
$env:FZH_DATA_ROOT="D:\fzh-pack"; mkdir D:\fzh-pack
#    macOS / Linux:
#    export ERP_API_KEY=... ERP_API_SECRET=... FZH_DATA_ROOT=~/fzh-pack; mkdir -p ~/fzh-pack

uv run python -m supply_copilot doctor     # pull 前显示 missing 属正常
uv run python -m supply_copilot pull       # 下载并校验私有包（约 14MB）
uv run python -m supply_copilot doctor     # 期望 status=ok, missing_files=[]
```

- 凭证只有 `ERP_API_KEY` / `ERP_API_SECRET`，用**自己的 EN 内部账号（System User）**；
  没有也不需要 `ADMIN_ERP_API_KEY`。匿名/门户账号 403。
- 目录要先存在（`doctor` 不会替你创建）；`--env-file` 对含空格路径不可靠，Windows 建议直接设环境变量。
- `doctor` / `recommend` / `batch` 只用已下载的包；`pull` / `refresh` 才需要凭证。

## 能问什么（和补货相关）

| 你可以问 Agent | 对应命令 / 依据 |
|---|---|
| 某 SKU 给某分公司要不要补、补多少、什么时候补、为什么 | `recommend --branch USNJ --sku <SKU>` |
| 这个分公司全部 SKU 的补货建议（不截断） | `batch --branch USNJ` |
| 这个建议的 q50/q90/q95、C/EN/PO/SO/CG、净需求、需要日/下单日 | `recommend` 报告与 `--json` |
| 用的什么预测模型？回测怎么样？趋势如何？ | D5/D3b 证据（模型、holdout、趋势） |
| 现在实时库存多少？按实时库存净需求变多少？ | `refresh --branch USNJ --sku <SKU>`（复用 D5，不重训） |
| 换一套决策口径（v6.24）看看 | `recommend --d6-version v6_24 ...` |
| 精确匹配还是模糊搜 SKU | 默认精确；`--like` 才模糊（防 KS100 误配 KS1000） |
| 这份数据是什么时点、是否完整可信 | `doctor` + 包版本/as_of/sha256 |

注意：结论是**历史回放**（显示 `as_of`，例如 2026-11-13），不是今天的执行建议；未知一律不补 0。

## A/B/C/D/E 是什么

- **A SKU 宇宙**：SKU × 客户 × 仓 × 形态 × UOM（`sku_map.tsv`、`E_lifecycle.parquet`）
- **B 归属**：某 SKU 归哪个客户/池；当前 CLI 未暴露 B 确认流程（数据在本地分析侧）
- **C 库存**：当前可发 C、EN 在途/待发、PO、SO、CG（下游缓冲，不可回拨）
- **D 预估**：D5 v6.8 分位预测（p50/q90/q95…）+ D3b 分类/回测/趋势
- **E 已有供给**：E 节点/生命周期、W1 SO 事实（`E_nodes.parquet`、`W1_SO.jsonl`）
- **D6 决策**：q95 需求 − C/EN/PO/SO/CG = 净需求 → 补 / 催已有 / 不补 / 观察

## 包里有什么（15 个文件，2026-11-13.1）

D3b、D5、D6 v6.22 / v6.24、E 节点与生命周期、C14、CNY v13、traj v13、
W1 SO、SKU 映射、USNJ 建议、老板版 v5.5、需求趋势、服务水平。

其中 CNY（春节备货）、老板版、E 明细、B 归属目前**只有数据、尚无 CLI 命令**；
需要时让 Agent 直接读包内文件，或后续加命令。

## 记录在哪里

- 代码与约定：`supply_copilot/`（本目录）、`.agents/skills/supply-decision-copilot/SKILL.md`
- 测试：`tests/test_supply_copilot.py`
- 数据包清单：`supply_copilot/pack_manifest.json`（版本/as_of/分卷/哈希）
- EN 侧：`key_test` 仓库的 `pack_download`（下发）与 `usnj_static` + Page（只读页）
- 私有数据：EN `private/files/` 与本地 `FZH_DATA_ROOT`，**不进公共仓库**

## 数据包管理（管理员）

1. zip 分卷放在站点 `private/files/`（`supply-copilot-pack-<version>.partNNN`）；
2. 由 `key_test.demand_collaboration.pack_download.get_part` 下发（内部账号可下载、匿名 403）；
3. 客户端通过 `FZH_PACK_METHOD` 覆盖下载方法路径；重新打包时保持 manifest 的 sha256/分卷一致。
