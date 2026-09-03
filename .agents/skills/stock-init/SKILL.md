---
name: stock-init
description: >
  赛狐库存初始值导入。从通途多仓库存 + EN BOM 成本生成赛狐库存导入文件（数量+成本）。
  当用户提到"库存初始值"、"库存导入"、"stock_init"、"通途库存"、"EN BOM成本"、
  "库存初始化"、"初始库存"、"仓库库存导入"、"共享库存"等时触发。
  不要用于采购成本导入(item-cost)或商品重尺(item-weight)。
compatibility: >
  需要 pandas, openpyxl。从 stock_init/ 目录运行。数据文件需放在 stock_init/数据源/ 下。
metadata:
  module: stock_init
  script: build_saihu_stock_init.py
  updated: 2026-05-20
---

# 赛狐库存初始值导入

把通途 6 仓库存 + EN BOM 成本 → 合并映射到赛狐 3 仓 → 生成库存初始值导入 xlsx。

## 数据准备

**通途库存需先从通途 ERP 自动下载**，用仓库内 dispatcher（首次会自动建浏览器子环境；下载落在 `web_automation/downloads/`，合并文件在 `web_automation/output/`）：

```bash
# 0) 只检查状态（是否需要装浏览器/登录）
uv run python web_automation/scripts/dispatch.py tongtu.stock.export --check

# 1) 正式导出（状态 READY 或 NEED_LOGIN 时执行；NEED_LOGIN 会打开浏览器等人手动登录）
uv run python web_automation/scripts/dispatch.py tongtu.stock.export

# 仅在用户明确要全自动登录（ddddocr）时追加 --with-ocr：
uv run python web_automation/scripts/dispatch.py tongtu.stock.export --with-ocr
```

把 `web_automation/output/` 下最新的 `通途合并库存结存清单*.xlsx` 放入 `stock_init/数据源/` 目录。

## 快速启动

```bash
cd stock_init
uv run python build_saihu_stock_init.py
```

脚本自动选取 `数据源/` 下最新的数据文件。输出在 `out/{时间戳}/` 下。

## 管道概要

通途库存(6仓) → 仓库映射(→3赛狐仓) → left merge EN BOM成本(按发货方式+仓库选取成本列) → 成本借用 → 赛狐SKU白名单过滤 → 聚合(仓库+SKU) → 输出。

## 硬约束

- **共享库存**：店铺、FNSKU 留空
- **成本=0 过滤**：导入文件排除成本=0 的行（赛狐静默跳过）
- **成本借用**：同重量模板键（前3段SKU）列内 0→非零，不跨列
- **输出拆分**：导入用（成本>0）+ 参考用（全量），文件名区分
- **递增导入**：对比 `out/上次导入_基准.xlsx`，只导出新增条目

## 输出文件

- `赛狐库存初始值_导入_{stamp}.xlsx` — 可直接上传赛狐
- `参考_库存初始值全量_{stamp}.xlsx` — 全量参考
- `stock_init_问题报告_{stamp}.xlsx` — 7 sheet
- `差异报告_{stamp}_vs_{基准}.xlsx` — 与上次导入对比
- `新增条目_导入_{stamp}.xlsx` — 仅新增条目

## 参考

- [给人看的 README](../../stock_init/README.md)
- [Agent 详细参考](../../stock_init/AGENT_HANDOFF.md) — 仓库映射、成本选取表、函数索引、字段映射、边界条件、成本借用详则
