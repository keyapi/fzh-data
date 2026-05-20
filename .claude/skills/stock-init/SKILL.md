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
  inputs: 通途合并库存结存清单 + EN产品BOM成本列表 + 商品导出
  outputs: 赛狐库存初始值导入文件 + 问题报告 + 差异报告 + 新增条目
  updated: 2026-05-20
---

# 赛狐库存初始值导入

## 一句话概括

把通途 6 仓库存 + EN BOM 成本 → 合并映射到赛狐 3 仓 → 生成库存初始值导入 xlsx。

## 快速启动

```bash
cd stock_init
python build_saihu_stock_init.py
```

脚本自动选取 `数据源/` 下最新的数据文件。输出在 `out/{时间戳}/` 下。

## 管道

```
通途库存(6仓, 4771行) ──仓库映射(→3赛狐仓)──┐
EN BOM成本(3566行) ──成本借用+列选取─────────┤
赛狐商品(2214行) ──SKU白名单────────────────┤
  → left merge → 成本列选取 → 赛狐SKU过滤 → 聚合(仓库+SKU) → 输出
```

## 仓库映射

| 通途仓库 | 赛狐仓库 |
|---------|---------|
| CENTRADE | CENTRADE |
| FZHPoland-covers | POLAND |
| FZH-DANEEY-* (5个) | DANEEY |

## 成本选取

| 发货方式 | CENTRADE(美东) | DANEEY(美中) | POLAND(波兰) |
|---------|-------------|------------|-------------|
| 皮壳/半成品 | `发皮壳尾程前成本, 美东USNJ` | `发皮壳尾程前成本, 美中USTX` | `发皮壳尾程前成本, 波兰PL` |
| 成品 | `发成品尾程前成本, 美东USNJ` | `发成品尾程前成本, 美中USTX` | `发成品尾程前成本, 波兰PL` |

## 关键约束

- **共享库存**：店铺、FNSKU 留空（便于后续成本补录单）
- **成本=0 过滤**：赛狐不导入成本=0 的行，导入文件过滤掉
- **成本借用**：同重量模板（前3段SKU）互相借用填充 0 成本，纯列内操作
- **输出拆分**：导入用（成本>0）+ 参考用（全量），两文件分清楚
- **递增导入**：对比 `out/上次导入_基准.xlsx`，只生成新增条目导入文件

## 输出文件

- `赛狐库存初始值_导入_{stamp}.xlsx` — 可直接上传赛狐（成本>0）
- `参考_库存初始值全量_{stamp}.xlsx` — 全量参考（含成本=0）
- `stock_init_问题报告_{stamp}.xlsx` — 7 sheet 问题报告
- `差异报告_{stamp}_vs_{基准}.xlsx` — 与上次导入对比
- `新增条目_导入_{stamp}.xlsx` — 仅新增条目，可直接上传

## 参考

- [给人看的 README](../../stock_init/README.md)
- [给 Agent 的详细参考](../../stock_init/AGENT_HANDOFF.md) — 函数表、字段映射、边界条件全量
