# tongtool_order_cost — Agent 交接

> **CLI**: `scripts/run_audit_170.py` · `scripts/remap_gsheet_sku.py` · `scripts/lookup_tongtool_sku.py` · `scripts/analyze_history_last_leg.py` · `scripts/backtest_history_last_leg.py` · `scripts/export_history_last_leg_model.py`
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
| `tongtool_order_cost/history_last_leg_analysis.py` | 历史尾程只读剖析：包裹去重、排除、标准化、异常标记、分层统计、分层发布、HLF0001 回测、时间切分 Holdout |
| `tongtool_order_cost/history_last_leg_export.py` | 分层费率 → EN 子表导入行（字段契约、kg 上下界、稳定 `model_key`） |
| `scripts/analyze_history_last_leg.py` | 历史尾程只读分析 CLI（月度 Google Sheet → 多 Sheet 报告 + 本地缓存） |
| `scripts/backtest_history_last_leg.py` | HLF0001 vs 分层模型回测 CLI（全量对照 + 严格时间 Holdout） |
| `scripts/export_history_last_leg_model.py` | 生成 EN 候选导入 CSV + parent 契约 JSON（只读，不写线） |

## 历史尾程升级（只读，2026-09-11）

调研结论见 [docs/research/2026-09-11-history-last-leg-field-profiling.md](docs/research/2026-09-11-history-last-leg-field-profiling.md)。
动手前必须记住的源字段事实：

- 读**原始订单表** `<年>年<月>月订单`；`写回…FBA订单和非FBA订单` 已剔除邮编/物流商/重量，不能用。
- `通途重量` 是**克**且为**包裹级**（组内一致）；`物流商重量` 恒为 0，不可用；`商品重量` 才是逐件。
- 包裹键必须是 `月份|包裹号`；`包裹总运费` 是包裹级且在多件行重复（组内极差 ≤0.05），逐行求和会重复计费。
- 费用来源随月份切换：2025-11 主要看 `物流商运费`，2025-12 起看 `包裹总运费`；分析层按优先级取首个正值并记录来源。
- **渠道必须单独成维**：`VITE` / `M6180` / `US-FEDEX` 是三套价目（USNJ 中位 122.40 / 89.70 / 150.00），按 `FEDEX` 合并即错误。
- **分区敏感度取决于渠道**：VITE 近乎一口价（+2.7%~9.8%），M6180/US-FEDEX 强分区（+42%~53%）。
- 平台承担尾程排除量占 25%~40%，不可省略。

回测结论（`scripts/backtest_history_last_leg.py`）：

- **全量拟合（仅对照，不是闸门）**：分层 US MAE 18.23 vs HLF0001 39.17，偏差 −2.34 vs −17.32。
- **严格时间 Holdout（发布闸门，训练 ≤2026-04 / 验证 2026-05~06，9,052 包裹）**：
  分层 MAE 20.30 vs 33.89、MdAE 14.62 vs 22.42、P90 39.96 vs 85.20、覆盖率 99.6%；
  但偏差由 −1.23 变 **+4.21（略高估）**，因为 2026-06 是样本最低价月份。
- 三种 fallback 顺序（SKU 优先 / 分区优先 / 渠道自适应）在验证窗口**预测完全相同**，
  无法据此判定先后，不能声称渠道自适应已被验证。
- 分渠道：USNJ×VITE 37.84→16.60、US-FEDEX 35.79→20.43、USTX×M6180 22.17→14.71 改善；
  **USNJ×M6180 变差 18.02→21.74**（该渠道 2026-04/05 有整月平坦费率），需单独复核。
- 低量非美国国家在时间切分下失去覆盖（验证期 39 个包裹），需补 `国家+重量层` 降级路径。

已定位线上三处缺陷：千克比克导致重量兜底退化为常量（US 恒返 ¥0.2638）、兜底忽略 SKU、
精确匹配 `LIMIT 1` 无 `ORDER BY`。三处已在 EN 侧共用解析器中修复。

`analyze_history_last_leg.py` 只读，输出到 gitignore 的 `out/`；不写回源表。

## EN 侧落地（2026-09-14，未部署未激活）

仓库 `keyapi/tongtool_integration` 分支 `feature/history-last-leg-v2`（独立 clone 于
`D:/Work/赛狐/Cursor-worktrees/tongtool-integration-history-last-leg`）：

- `tongtool_integration/tongtool_integration/history_last_leg_fee.py`：唯一解析器
  （Active parent 确定性选择、渠道自适应层级、`HLF0001` 兜底、缺列自动降级）
- parent/child DocType JSON 扩展；控制器校验 + 幂等导入 + 激活/停用按钮
- `order_sync`、`tongtool_cost_review`、`excel_tongtool_order` 改为共用解析器，内联历史 SQL 清零
- 测试 `tongtool_integration/tests/test_history_last_leg_fee.py`（30 项）：
  `uv run python -m unittest discover -s tongtool_integration/tests -t .`
- 文档 `docs/history_last_leg_model.md`

**边界**：`HLF0001` 与 3,037 子行全程未读写；无部署、无导入、无激活、未 push/PR。

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
