---
name: warehouse-restock
description: >
  赛狐海外仓备货单导入。从 EN BOM 成本列表拆出绍兴发货成本/头程运费/国外加工成本，
  结合通途仓库分布，生成赛狐海外仓备货单导入 xlsx。
  当用户提到"海外仓备货单"、"warehouse_restock"、"备货单"、"采购入库"、
  "海外仓入库"、"stock_plan"、"成本拆分"、"绍兴发货成本"等时触发。
  不要用于期初库存导入(stock-init)或采购成本导入(item-cost)。
compatibility: >
  需要 pandas, openpyxl。从 warehouse_restock/ 目录运行。
  依赖 数据源/ 下的 EN BOM 成本列表 + 通途库存 + 赛狐商品导出。
  模板文件在 数据源样例/ 下。
metadata:
  module: warehouse_restock
  scripts: build_saihu_warehouse_restock.py, run_full_restock_flow.py
  updated: 2026-05-28
---

# 赛狐海外仓备货单导入

EN BOM Cost List → 三成本拆分（绍兴/头程/加工）→ 赛狐海外仓备货单模板。

## 数据准备

**通途库存数据需先从通途 ERP 自动下载**，用仓库内 dispatcher（首次会自动建浏览器子环境；下载落在 `web_automation/downloads/`，合并文件在 `web_automation/output/`）：

```bash
# 0) 只检查状态
uv run python web_automation/scripts/dispatch.py tongtu.stock.export --check
# 1) 正式导出（NEED_LOGIN 时打开浏览器等人手动登录；OCR 仅用户明确要求时加 --with-ocr）
uv run python web_automation/scripts/dispatch.py tongtu.stock.export
```

把 `web_automation/output/` 下最新的 `通途合并库存结存清单*.xlsx` 放入 `warehouse_restock/数据源/` 目录。

## 两种使用方式

### 方式 1：只生成 Excel（不碰赛狐）

```bash
cd warehouse_restock
uv run python build_saihu_warehouse_restock.py
```

产出 6 个格式 2 文件（默认）+ 6 个格式 1 备份（`_旧格式` 后缀）。

### 方式 2：完整流程调度器（导出库存 → 生成 → 导入）

```bash
cd warehouse_restock
uv run python run_full_restock_flow.py --generate-only --yes   # 仅生成Excel
uv run python run_full_restock_flow.py --skip-zero-out --yes   # 导出+生成+导入(跳过清零)
uv run python run_full_restock_flow.py --yes                   # 全部步骤(含清零)
```

调度器改为调用仓库内 dispatcher（`run_full_restock_flow.py` 已去掉外部路径）。赛狐写操作由 dispatcher 强制范围确认后才执行。

## 管道概要

EN BOM成本列表 → 成本借用(同重量模板) → 三成本拆分 → 通途仓库映射(SKU后缀清理) → 赛狐SKU白名单 → 填模板(双格式输出)。

## 双格式成本映射

### 格式 2（默认，2026-05-28 起）

| 列 | 值 |
|---|-----|
| `指定采购单价` | **绍兴发货成本 + 国外加工成本** |
| `单个头程费用` | **头程运费** |
| `物流费用` | 留空 |
| `其他费用` | 留空 |
| `*备货数量` | 1000 |

> 赛狐显示：采购单价=绍兴+加工，头程费用=纯头程。销售负责人要求单独看头程。

### 格式 1（旧，`_旧格式` 后缀备份）

| 列 | 值 |
|---|-----|
| `指定采购单价` | 绍兴发货成本 |
| `物流费用` | 头程运费 × 1000 |
| `其他费用` | 国外加工成本 × 1000 |
| `单个头程费用` | 留空（赛狐自动算） |

## 硬约束

- 通途仓库判定：SKU **只要出现过**就算（含库存=0）
- 通途 SKU 含人工后缀（如 `-淘汰`）→ 匹配时自动剥离
- 成本缺失时同重量模板内借用
- 模板含 hidden Data Validation sheet，不可删
- 头程/税费分摊方式统一填"自定义"
- 单个备货单 ≤ 500 条，超过自动拆批次

## 完整工作流

```
Step 1: 导出库存明细 → web_automation/scripts/dispatch.py sellfox.stock.export
Step 2: (可选) 其他出库清零 → build_saihu_other_outbound.py → dispatch.py sellfox.other-outbound.import
Step 3: 备货单入库 → build_saihu_warehouse_restock.py → dispatch.py sellfox.restock.import
```

Step 1 是 API 优先（失败仅在明确允许时才回退浏览器）；Step 2/3 是写操作，dispatcher 必须先返回 `NEED_USER_CONFIRMATION`，用用户确认的文件/SKU/仓库范围带 `--confirm-scope` 才执行。导入前会先导出库存备份、导入后再导出对照。写操作只许用用户确认范围内的测试/目标商品，绝不扩大到全量。

## 输出

- `赛狐_海外仓备货单_导入_{仓库}_{stamp}.xlsx` — 格式 2（默认，上传此文件）
- `赛狐_海外仓备货单_导入_{仓库}_{stamp}_旧格式.xlsx` — 格式 1（备份）
- `warehouse_restock_问题报告_{stamp}.xlsx` — 跳过明细 + 成本借用记录

## 参考

- [给人看的 README](../../warehouse_restock/README.md)
- [Agent 详细参考](../../warehouse_restock/AGENT_HANDOFF.md)
- [BOM 成本拆解说明](../../docs/bom_cost_explanation.md)
