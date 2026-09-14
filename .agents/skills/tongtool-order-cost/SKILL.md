---
name: tongtool-order-cost
description: >
  通途订单特殊规则 1.7.0 本地审计、Google Sheet 订单 SKU 改名替换、通途 goodsQuery 校验、
  历史尾程费率表（History Last Leg Fee Record）建模与回测。
  用户提到特殊规则、订单改销售额成本、Jeck特殊规则、1.7.0、通途订单202606、
  Google Sheet 通途SKU 替换、gspread、FBA 尾程、账期差异、历史尾程、预估尾程、
  HLF0001、费率表、月初导出时触发。
  不要用于赛狐打单或 ERPNext 工单排查。
metadata:
  module: tongtool_order_cost
  docs: tongtool_order_cost/docs/index.md
  updated: 2026-09-14
---

# 通途订单特殊规则 / Google Sheet SKU 改名

## 必须先做

1. 读 `tongtool_order_cost/AGENT_HANDOFF.md`。
2. Google Sheet 读写前确认本机有 `secrets/gsheets-service-account.json`（gitignored）。没有则运行 bootstrap，**不要**把 notebook 里的私钥提交进 git。
3. 写回 Google Sheet 必须用户确认：工作表名单、只改哪一列、dry-run 计数。默认 `--dry-run`。
4. 井维护**新**通途 SKU。订单表里的旧名才替换；不要把规则表改回旧名。
5. 替换前用通途 `erp2_product_goodsquery`（或本模块 `lookup_tongtool_sku.py`）确认「像旧名」的 SKU 是不是主档里真实存在的另一件货。

## 管道

| 目的 | 命令 |
|------|------|
| 1.7.0 本地审计 | `uv run python tongtool_order_cost/scripts/run_audit_170.py ...` |
| 抽出 gspread 凭证 | `uv run python tongtool_order_cost/scripts/bootstrap_gsheets_credentials.py` |
| SKU 替换预检 | `uv run python tongtool_order_cost/scripts/remap_gsheet_sku.py --sheet 通途订单202606` |
| 确认后写回 | 同上加 `--apply` |
| 通途主档是否存在 | `uv run python tongtool_order_cost/scripts/lookup_tongtool_sku.py SKU1 SKU2` |
| 历史尾程只读剖析 | `uv run python tongtool_order_cost/scripts/analyze_history_last_leg.py`（可加 `--cache`） |
| HLF0001 vs 分层模型回测 | `uv run python tongtool_order_cost/scripts/backtest_history_last_leg.py` |
| 多方案对比 | `uv run python tongtool_order_cost/scripts/compare_history_last_leg_variants.py` |
| 对抗性自检 | `uv run python tongtool_order_cost/scripts/verify_history_last_leg_model.py` |
| 门槛扫掠 | `uv run python tongtool_order_cost/scripts/sweep_history_last_leg_thresholds.py` |
| 生成线上导入文件 | `uv run python tongtool_order_cost/scripts/export_history_last_leg_model.py` |

历史尾程相关脚本全部**只读**：输出落在 gitignore 的 `out/`，不写回 Google Sheet、
不改 `HLF0001`、不做 ERPNext 写入。线上仓库是 `keyapi/tongtool_integration`
（分支 `feature/history-last-leg-v2`），其 `history_last_leg_fee.py` 是唯一解析器。

## 历史尾程（2026-09-14 定稿）

1. **费用列只用 `物流商运费`**（真实回传扣款）。`包裹总运费` 口径不稳（同一包裹有时等于
   物流商运费、有时等于通途运费），只能兜底；`通途运费` 是通途侧阶梯预估。
   旧的「按月份切换费用列」结论**已作废**。
2. **运费是整包价**，禁止 `预估 × 发货数量`；按整包（计费）重量匹配，多行包裹按重量份额分摊。
3. **发布配置单点定义** `model_variants.RECOMMENDED_VARIANT`（当前 `V3c_门槛10`：
   独立分层发布 + 分区优先 + 10 样本 / 2 月门槛）。可信度加权与排平坦实测≈0，**不启用**。
4. **层级名是跨仓库契约**：`history_last_leg_export.LEVEL_NAMES` 与线上
   `history_last_leg_fee.LEVEL_NAMES` 必须逐字一致，两侧各有测试锁定。
5. 报告精度必须**同时报覆盖率**；覆盖率归零会被误读成「没有误差」。
6. 评估要看**月初工件**（月初导出 + 事后补真实的文件对），月均评估会掩盖真实使用场景。
7. 细节与实测见：
   - [docs/research/2026-09-11-history-last-leg-field-profiling.md](../../../tongtool_order_cost/docs/research/2026-09-11-history-last-leg-field-profiling.md)
   - [docs/research/2026-09-14-rate-table-training-methodology.md](../../../tongtool_order_cost/docs/research/2026-09-14-rate-table-training-methodology.md)
   - [docs/solutions/](../../../tongtool_order_cost/docs/solutions/index.md)

## 铁律

- FBA 尾程参考值：`>0`/`=0` 跳过；`<0` 写入 `运费`（账期差异）。详见 AGENT_HANDOFF。
- `BNFBAvelvetgray60` 是 60CM 独立货，不是 gray-100 笔误。
- `FoamFBAKZ159410287-BLACK-97` 是规则笔误，订单侧是 `...-BLACK-100`。`CENKZ159410287-BLACK-97` 是自发货 CEN，不要改。
- 只改 SKU 列（`通途SKU` 优先，否则 `SKU`）。不改 MSKU / 平台 SKU / 成本列。
- Cursor Agent 查主档：用 MCP `user-tongtool_erp2_primary` / `erp2_product_goodsquery`。工具目录没有通途 MCP 时先跑 `uv run python tongtool_api/setup_cursor_mcp.py`，不要静默 HTTP。CLI `lookup_tongtool_sku.py` 仍走 `mcp_http.py`。

## 不要做

- 不要全量导入赛狐。
- 不要把 service account JSON / notebook 私钥写进文档或 commit。
- 不要在未 dry-run 的情况下 `--apply`。
- 不要把个人姓名、同事姓名或个人绝对路径写进文档/提交（用角色称谓与相对路径）。
- 不要把月初占位值（旧预估）当训练标签——那会形成循环训练。
