# tongtool_order_cost — Agent 交接

> **CLI**: `scripts/run_audit_170.py` · `scripts/remap_gsheet_sku.py` · `scripts/lookup_tongtool_sku.py`
> **历史尾程 CLI**: `scripts/analyze_history_last_leg.py` · `scripts/backtest_history_last_leg.py` · `scripts/compare_history_last_leg_variants.py` · `scripts/verify_history_last_leg_model.py` · `scripts/sweep_history_last_leg_thresholds.py` · `scripts/export_history_last_leg_model.py`
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
| `tongtool_order_cost/model_variants.py` | 多方案费率模型：层级集合、可信度加权、定稿配置 `RECOMMENDED_VARIANT` |
| `scripts/export_history_last_leg_model.py` | 生成 EN 候选导入 CSV + parent 契约 JSON（只读，不写线） |
| `scripts/compare_history_last_leg_variants.py` | 多变体对比（Holdout + 真实月初工件） |
| `scripts/verify_history_last_leg_model.py` | 定稿结论的对抗性自检 |
| `scripts/sweep_history_last_leg_thresholds.py` | 样本/月份门槛扫掠 |

## 历史尾程升级（只读，2026-09-11）

调研结论见 [docs/research/2026-09-11-history-last-leg-field-profiling.md](docs/research/2026-09-11-history-last-leg-field-profiling.md)。
动手前必须记住的源字段事实：

- 读**原始订单表** `<年>年<月>月订单`；`写回…FBA订单和非FBA订单` 已剔除邮编/物流商/重量，不能用。
- `通途重量` 是**克**且为**包裹级**（组内一致）；`物流商重量` 恒为 0，不可用；`商品重量` 才是逐件。
- 包裹键必须是 `月份|包裹号`；多件行上费用列会重复或按重量分摊，必须按列语义取 `max` 或 `sum`。
- **费用列口径（2026-09-14 修正）：建模与真值一律用 `物流商运费`** —— 它是真实回传的承运商扣款
  （月初先写 EN 预估占位，之后被真实费用替换）。`包裹总运费` 口径不稳（同一包裹有时等于物流商运费、
  有时等于通途运费），只能兜底；`通途运费` 是通途自己的阶梯预估。此前「按月份切换」的结论**已作废**。
- **渠道必须单独成维**：`VITE` / `M6180` / `US-FEDEX` 是三套价目（USNJ 中位 122.40 / 89.70 / 150.00），按 `FEDEX` 合并即错误。
- **分区敏感度取决于渠道**：VITE 近乎一口价（+2.7%~9.8%），M6180/US-FEDEX 强分区（+42%~53%）。
- 平台承担尾程排除量占 25%~40%，不可省略。

已定位线上三处缺陷：千克比克导致重量兜底退化为常量（US 恒返 ¥0.2638）、兜底忽略 SKU、
精确匹配 `LIMIT 1` 无 `ORDER BY`。三处已在 EN 侧共用解析器中修复。
另有第四处：旧代码 `预估 × 发货数量`，而运费本质是**整包价**（2 件高估约 37%、3 件约 121%），
**`×件数` 贡献了老方式几乎全部系统性偏差**（月初工件偏差 +11.88 → 去掉后 +1.10）。
分析侧已不再乘件数；EN 调用方（Cost Review / `order_sync`）必须同步去掉乘法，否则月初 Excel 仍会高估。

`analyze_history_last_leg.py` 只读，输出到 gitignore 的 `out/`；不写回源表。

## 历史尾程定稿模型（2026-09-14 定稿，待审）

**发布配置单点定义**：`model_variants.RECOMMENDED_VARIANT`（当前 `V3c_门槛10`）→
导出入口 `build_recommended_tiers` → `scripts/export_history_last_leg_model.py`。

内容：独立分层发布（非排他）+ 分区优先 + **10 样本 / 2 月**门槛 + **11 个层级**
（`L1_SKU_ZIP3_重量` / `L1b_SKU_ZIP1_重量` / `L2_SKU_重量` / `L3_ZIP3_重量` /
`L3b_ZIP1_重量` / `L4_ZIP3` / `L5_重量` / `L5b_国家重量` / `L6_仓库渠道` / `L7_仓库` /
`L8_国家`）。**不用**可信度加权、**不排除**平坦月份（实测增益≈0）。

实测（训练 ≤2026-04；三个验证集 MAE）：

| | HLF0001 | 旧基线 | 定稿 V3c |
|---|---|---|---|
| Holdout 2026-05~06 | 34.52 | 18.07 | **15.03** |
| 月初工件 202605 | 35.76 | 21.37 | **17.64** |
| 月初工件 202606 | 30.29 | 17.08 | **14.18** |
| 独立窗 2026-03~04 | 39.34 | 21.24 | **18.94** |

定稿依据与全部对抗性自检见
[docs/research/2026-09-14-rate-table-training-methodology.md](docs/research/2026-09-14-rate-table-training-methodology.md)
第 8、9 节。**层级名是跨仓库契约**：`history_last_leg_export.LEVEL_NAMES` 与
`tongtool_integration.history_last_leg_fee.LEVEL_NAMES` 必须逐字一致，两侧各有测试锁定；
导出时若出现线上不认识的层级会直接报错。

可复跑脚本：`scripts/compare_history_last_leg_variants.py`（多变体对比工作簿）、
`scripts/verify_history_last_leg_model.py`（对抗性自检）、
`scripts/sweep_history_last_leg_thresholds.py`（门槛扫掠）。


### 线上仓库落地

`keyapi/tongtool_integration` 分支 `feature/history-last-leg-v2`（本地独立 clone，未随本仓库版本管理）：

- `tongtool_integration/tongtool_integration/history_last_leg_fee.py`：唯一解析器
  （Active parent 确定性选择、渠道自适应层级、`HLF0001` 兜底、缺列自动降级）
- parent/child DocType JSON 扩展；控制器校验 + 幂等导入 + 激活/停用按钮
- `order_sync`、`tongtool_cost_review`、`excel_tongtool_order` 改为共用解析器，内联历史 SQL 清零
- 测试 `tongtool_integration/tests/test_history_last_leg_fee.py`（34 项）：
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
- 不要把个人姓名/同事姓名/个人绝对路径写进文档或提交（用角色称谓与相对路径）
- 不要把月初占位值（旧预估）当训练标签——会形成循环训练

## EN 侧落地（2026-09-14，未部署未激活）

见上文「定稿模型」与 EN 仓库 `docs/history_last_leg_model.md`。
