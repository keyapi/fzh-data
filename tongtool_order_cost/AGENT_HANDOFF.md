# tongtool_order_cost — Agent 交接

> **CLI**: `scripts/run_audit_170.py` · `scripts/remap_gsheet_sku.py` · `scripts/lookup_tongtool_sku.py` · `scripts/upload_monthly_order_sheet.py`
> **人读**: [README.md](README.md)
> **Skill**: `.agents/skills/tongtool-order-cost/SKILL.md`

## 业务背景

运营对「特殊规则改成本」有异议时，需要证明 Colab **1.7.0** 逻辑：匹配哪些订单、各科目 before→after→Δ。六月 AMZBAINAUS 多为 **ref（参考值）** 模式。

2026-08 追加：通途允许**改主档 SKU 名**。井的规则表用新名；1.4/Google Sheet 订单仍可能是导出当时的旧名。1.7.0 精确匹配会漏行。处理方式是**改订单表旧名→新名**，不改井的新名。

## 管道

```
订单xlsx(未改成本) + 规则xlsx + FX
  → 时间窗过滤 → 6列去重 → attach FX → ￥参考值
  → backup_* → coeff/ref 写入（FBA 正数尾程跳过；负数账期差异写入）
  → 重算产品成本/订单总成本/利润
  → change_events → 多 Sheet 审计 xlsx
```

Google Sheet SKU 改名（与 1.7.0 审计独立）：

```
bootstrap_gsheets_credentials.py
  → secrets/gsheets-service-account.json（gitignore）
remap_gsheet_sku.py --sheet <标题>          # 默认 dry-run
remap_gsheet_sku.py --sheet <标题> --apply  # 用户确认后
lookup_tongtool_sku.py <SKU...>             # 主档是否存在
```

## 关键模块

| 文件 | 作用 |
|------|------|
| `tongtool_order_cost/engine_170.py` | 与 notebook Cell 22 对齐的应用引擎 |
| `tongtool_order_cost/audit_sources.py` | 只读源盘点/快照 + 分块取数二分失败隔离（U1/U3） |
| `tongtool_order_cost/profitability_audit.py` | 盈利审计核心：行身份/grain/口径矩阵/异常分类/利润倒挂（U2/U4/U5/U6） |
| `tongtool_order_cost/profitability_report.py` | 对账闸门 + JSON/Excel(17表)/管理摘要（U7） |
| `tongtool_order_cost/ustx_cost_compare.py` | 美中 USTX 三方案成本对比：列合同 / B1·B2 成本目录 / 全月逐行比较 / 归因 / 闸门 / 产出（纯离线） |
| `tongtool_order_cost/audit.py` | 事件 → 审计簿 |
| `tongtool_order_cost/io_loaders.py` | 订单/规则/汇率加载 |
| `tongtool_order_cost/pp_cotton.py` | 美中 DANEEY 订单 × BOM Cost List → PP 棉 kg 估算 |
| `tongtool_order_cost/gsheets.py` | 本地 SA JSON → gspread Client / gsheet2df |
| `tongtool_order_cost/sku_map.py` | 已确认旧→新映射；gray60 / Foam97 例外 |
| `tongtool_order_cost/tongtool_goods.py` | ERP2 `erp2_product_goodsquery` |
| `scripts/run_audit_170.py` | 1.7.0 特殊规则审计 CLI |
| `scripts/bootstrap_gsheets_credentials.py` | 从 Colab notebook cell 0 抽出 SA 到 `secrets/` |
| `scripts/remap_gsheet_sku.py` | Google Sheet SKU 列 dry-run / apply |
| `scripts/lookup_tongtool_sku.py` | 通途主档 SKU 存在性 |
| `scripts/estimate_pp_cotton.py` | PP 棉用量估算 CLI |
| `scripts/audit_monthly_profitability.py` | 月度盈利审计 CLI：`list`/`snapshot`(只读冻结)/`analyze`(离线)/`ustx-compare`(美中三方案离线对比) |

## Notebook / Google Sheet 约定（2026-08-14 核实）

1.7.0 读 gs **和财务部共享** → ws **Jeck特殊规则-订单改销售额成本**（`use_local_rule_csv_170 = NO`）。
旧 ws **特殊规则-订单改销售额成本** notebook 已不用。

六月订单两份 workbook 都有这 3 张 FBA 相关表（列名不完全一样）：

| 工作表 | 常见 SKU 列 |
|--------|-------------|
| `2026年6月FBA订单` | `SKU`（销量汇总） |
| `写回2026年6月FBA订单` | `SKU`（订单明细） |
| `写回2026年6月FBA订单和非FBA订单` | `通途SKU` |

Workbook 标题：`通途订单202606-特殊规则`（1.7.0 用）、`通途订单202606`（不用来跑特殊规则，SKU 仍应对齐）。

## 已确认旧→新（AMZBAINAUS FBA Velvet）

| 订单旧名 | 井/主档新名 |
|----------|-------------|
| `BNFBAvelvetblack-100` | `BNUSFBA-Velvet-Black-100` |
| `BNFBAvelvetgray-100` | `BNUSFBA-Velvet-Grey-100` |
| `BNUSFBA-vel-grey153` | `BNUSFBA-Velvet-Grey-153` |
| `BNvelvetblack-153fba` | `BNUSFBA-Velvet-Black-153` |

**不要替换：** `BNFBAvelvetgray60`（通途主档存在：三角无扣 60CM）；`CENKZ159410287-BLACK-97`（自发货 CEN）。
**规则笔误：** `FoamFBAKZ159410287-BLACK-97` → 应写 `FoamFBAKZ159410287-BLACK-100`（改规则，不改订单 100→97）。

## 去重键（6 列）

`运营人员` + `发货区域` + `通途SKU` + `渠道账号不含国家` + `渠道账号` + `发货仓按销售汇总分类`（`keep=last|first`）

## 验证要点

1. `ref_usd × fx × 发货数量` = 数量列 after
2. FBA 尾程：参考值 **>0 或 =0** 不改 `运费`；参考值 **<0** 按账期差异写入 `运费`
3. `01_科目瀑布` 各科 Δ 与总览一致
4. SKU 替换：apply 后旧名计数为 0，新名计数 = 原旧名计数，gray60 计数不变

## 相关档案

- [月度盈利审计](docs/reference/monthly-profitability-audit.md)
  —— 老板质疑「平均成本/运费低、回款低反而利润高」时：**先 snapshot 冻结、再 analyze 离线**，
  口径矩阵 + 对账闸门 + JSON/Excel/管理摘要；**只读，不回写 GSheet/EN**。
  含 **美中 USTX 三方案成本对比**（`ustx-compare`：A 现状 / B1 测算表 / B2 EN-import 重建）——
  证明美中改走当地二次加工后四项成本怎么变；**纯离线、不写任何表**。
  要点：B1(人工测算) 与 B2(EN 重建) 非同源，**差异即结论**；头程与现状同源（A 已按绍兴发货方式取 EN 值 → Δ=0），仅「按皮壳重量」勾选项会再差 −16,517；
  另有 **B3 新工资情景**（工资率 167.8→105，只动 `operating_cost`，其余保持 9/3 快照）：7 月美中合计 A 526,225 → B2 791,137 → **B3 717,678**（ΔB3 +191,453）；需 `--wage-boms` 指向 EN 逐 BOM 工序表。见 `docs/reference/en-ustx-bom-wage-rate-spec.md`。
- [Colab 成本引擎逆向规格](docs/reference/colab-cost-engine-spec.md)
  —— 皮壳/头程/二次加工/绍兴二次加工的确切 pandas、仓库→成本来源编码、美中口径不对称的代码证据。
- [EN 直接采购件用「自套 BOM」出成本惯例 + 骨架缺口](../docs/solutions/architecture-patterns/en-direct-purchase-self-bom.md)
  —— 订单成本码为空时，先查物料有没有自套 BOM / 在不在皮壳平均表（`WL-shape-frame` 骨架就是漏项）

## 凭证

| 用途 | 本地文件 | git |
|------|----------|-----|
| Google Sheet | `secrets/gsheets-service-account.json` + `tongtool_order_cost/.env` | 忽略 |
| 通途 ERP2 | `tongtool_api/.env` | 忽略 |

Cursor Agent 用用户级 MCP `user-tongtool_erp2_primary`（`~/.cursor/mcp.json`，由 `tongtool_api/setup_cursor_mcp.py` 写入）。CLI 脚本仍用 `tongtool_api/mcp_http.py`。限流仍是商户合计 5 次/分钟。

## 禁止

- 不要把订单/规则大 xlsx 提交进 git
- 不要提交 service account JSON / notebook 私钥
- 不要直接 push main；走 `feature/...` + PR

## 通途SKU→EN物料 的权威桥（2026-10-17 起）

排查 USTX 成本时确立，**优先用·别猜解析**：

- **两条权威源**（都不需通途 API）：EN `Item Customer Detail.ref_code`（**REST 403，须 SSH 查 DB**）；gsheet `importBOMCostList.客户物料号`（现成列）。
- EN 物料名 → 重量模板：**去末段(颜色) + 前缀 `ZLMB#`**。
- 口径 **直连优先、旧键兜底**：`ustx-compare` 的 `--direct-map` / 默认取 `客户物料号`；`--no-direct` 关。7 月美中直连覆盖 **99.9%**（4367/4372），相对旧键 ΔB2 264,912→268,610。
- **改 gsheet 前**：`import皮壳成本` 是 `IMPORTRANGE` 拉的，**改它无效**；改源工作簿 `财务部绍兴成本核算表单2023`（`皮壳成本平均…`/`品类使用面料`/`材料价格明细`），且**源表+成本表成对改**。
- 详见 `docs/reference/cost-engine-spec/`（27/28 页）与 `docs/solutions/integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`。
