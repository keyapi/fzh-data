# missing_products — 赛狐缺失商品排查

通途库存 → EN → 赛狐 三系统交叉比对，找出赛狐里应创建但可能遗漏的商品。

## 数据源（自动化采集）

| # | 数据 | 来源 | 方式 |
|---|------|------|------|
| 1 | 通途库存 | 通途 ERP | `web_automation/scripts/dispatch.py tongtu.stock.export`（合并文件在 `web_automation/output/`） |
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
| 通途有货但EN未登记 | 通途有库存但完整 SKU 未登记到 EN 产品物料 |
| 不在售无库存 | 属性表在售=0 且无库存（无需操作）|
| SPU比对全量 | EN SPU ↔ 赛狐 SPU 全量比对 |
| 仅赛狐有EN无 | 赛狐存在但 EN 产品子树无此 SPU |

## 关键逻辑

- **大小写不敏感匹配**：通途 SKU ↔ EN 客户物料号统一小写比对（历史上有 `KDHY-...-60CM` vs `-60cm` 差异）
- **完整 SKU 精确匹配**：`-Cover`/`-Foam` 必须以完整编号登记到 EN 产品变体；去后缀基码只用于推荐候选，不代表已登记
- **产品物料是必需索引**：EN 销售订单 Excel 使用通途 SKU 找产品物料，再结合“皮壳/成品/半成品”列处理交付形态；`PK#`/`HM1510` 登记不能替代产品登记
- **SPU 库存按 EN 客户物料号聚合**：不能直接用通途 SKU 前缀当 SPU（通途 `PPL-*` ↔ EN `KS0018-*`）

## 排查出的缺失物料补建

若需补建 EN 缺失物料，参见 `.agents/skills/erpnext-item-create/` 和 `docs/solutions/conventions/erpnext-item-variant-creation-convention.md`。


## 只读交付脚本（2026-08-11）

| 脚本 | 输出 | 说明 |
|------|------|------|
| `build_mapping_workbook.py` | `out/通途EN赛狐映射表_*.xlsx` | 1411 行有库存 SKU 的 通途→EN→赛狐 映射，含一对多/多对一/暂缓 |
| `build_foam_status_workbook.py` | `out/海绵通途SKU现状_*.xlsx` | 25 条海绵 SKU 现状 + HM1510 历史登记参考，不写 HM1510 |
| `fetch_sellfox_pairing.py` | `out/赛狐配对盘点_*.xlsx` | Amazon 在线产品配对 + 多平台配对只读盘点；原始数据缓存于 `out/pairing_cache/`，`--refresh` 强制重拉 |

赛狐配对分 **Amazon 在线产品配对** 与 **多平台配对** 两套机制，接口、模板和现状详见 AGENT_HANDOFF §3.5。
## 文档

- **新对话请先读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)** — 完整交接（背景/状态/下一步/技术细节）
- **主线规则与完整复盘**：[通途有库存 SKU 三方主线补齐惯例](../docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md) — 完整码精确登记、半成品边界、赛狐创建与验证
- **自动触发 Skill**：[missing-products](../.agents/skills/missing-products/SKILL.md) — 新对话提到三方一致性/通途有库存/Cover/Foam/赛狐缺SKU 时自动加载
- [docs/index.md](docs/index.md) — 模块文档索引（OKF）
- [docs/specs/old-product-completion-plan.md](docs/specs/old-product-completion-plan.md) — 三类老产品（星球/石头/张嘴熊）补齐计划 + 库存同步映射设计
