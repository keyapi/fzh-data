# missing_products — 赛狐缺失商品排查

通途库存 → EN → 赛狐 三系统交叉比对，找出赛狐里应创建但可能遗漏的商品。

## 数据源（自动化采集）

| # | 数据 | 来源 | 方式 |
|---|------|------|------|
| 1 | 通途库存 | 通途 ERP | `D:\Work\赛狐\网页自动化\tongtu_auto_export.py` + `merge_inventory.py` |
| 2 | EN BOM 成本 | 本地 xlsx | `warehouse_restock\数据源\EN产品BOM成本列表*.xlsx` |
| 3 | 赛狐商品 | 赛狐 OpenAPI | `SellfoxClient` 拉 SPU + SKU 列表 |
| 4 | EN 物料组 | EN REST API | 产品子树下 `custom_model_id` 非空的 Item Group |

## 用法

```bash
cd missing_products
uv run python identify_missing_products.py
```

输出到 `out/赛狐缺失商品排查_{timestamp}.xlsx`。

## 报告工作表

| Sheet | 内容 |
|-------|------|
| 汇总 | 全量统计 |
| 需创建赛狐商品 | 通途有货+EN有产品+赛狐无SPU（含 EN 产品明细、通途库存）|
| 通途有货但EN未登记 | 通途有库存但匹配不到 EN 客户物料号（按分类：辅料/TT编码/其他）|
| 不在售无库存 | 属性表在售=0 且无库存（无需操作）|
| SPU比对全量 | EN SPU ↔ 赛狐 SPU 全量比对 |
| 仅赛狐有EN无 | 赛狐存在但 EN 产品子树无此 SPU |

## 关键逻辑

- **大小写不敏感匹配**：通途 SKU ↔ EN 客户物料号统一小写比对（历史上有 `KDHY-...-60CM` vs `-60cm` 差异）
- **SKU 后缀清理**：匹配时剥离 `-淘汰`/`-out`/`-Cover`/`-Foam`（`warehouse_restock` 的 `_clean_sku`）
- **SPU 库存按 EN 客户物料号聚合**：不能直接用通途 SKU 前缀当 SPU（通途 `PPL-*` ↔ EN `KS0018-*`）

## 排查出的缺失物料补建

若需补建 EN 缺失物料，参见 `.agents/skills/erpnext-item-create/` 和 `docs/solutions/conventions/erpnext-item-variant-creation-convention.md`。

## 文档

- **新对话请先读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)** — 完整交接（背景/状态/下一步/技术细节）
- [docs/index.md](docs/index.md) — 模块文档索引（OKF）
- [docs/specs/old-product-completion-plan.md](docs/specs/old-product-completion-plan.md) — 三类老产品（星球/石头/张嘴熊）补齐计划 + 库存同步映射设计
