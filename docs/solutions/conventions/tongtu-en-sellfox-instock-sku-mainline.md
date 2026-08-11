---
title: 通途有库存 SKU 三方主线补齐惯例
date: 2026-08-11
category: conventions
module: missing_products
problem_type: convention
component: development_workflow
severity: high
applies_when:
  - "核对通途有库存 SKU 是否已在 EN 和赛狐就绪"
  - "处理带 -Cover 或 -Foam 后缀的通途 SKU"
  - "补登 EN 客户物料号或创建赛狐多属性 SKU"
  - "重新生成三系统一致性报告或库存同步映射"
tags: [tongtu, erpnext, sellfox, customer-items, semifinished, sku-audit]
---

# 通途有库存 SKU 三方主线补齐惯例

## Context

本项目的主线不是把通途 SKU 机械地变成赛狐 SKU，而是维护一条可用于销售订单导入和库存同步的关系：

```text
通途有库存的完整 SKU
  -> 至少一个 EN 产品成品变体的 customer_items.ref_code
  -> 该 EN 产品 item_code 在赛狐存在同编号、同名称、同属性的 SKU
```

销售订单 Excel 先以通途 SKU 找到 EN 的产品成品变体，再由 Excel 的“皮壳/成品/半成品”列确定实际交付形态。因此 `PK#` 皮壳和 `HM1510` 海绵可保留其自身维护信息，但其 `customer_items` 不能替代产品成品的登记。赛狐本阶段也以 EN 产品 `item_code` 为商品 SKU，不为 `PK#` 或 `HM1510` 创建商品。

这条规则是对早期审计误判的修正：旧逻辑剥离 `-Cover`/`-Foam` 后缀后发现基码已登记，便把完整半成品 SKU 算作已登记，遗漏了销售订单实际需要的完整码。

## Non-Negotiable Invariants

1. 只把**完整**通途 SKU（含 `-Cover`、`-Foam`）作为 EN 登记是否完成的判据；匹配时大小写不敏感。
2. 去尾缀后的基码只用来找候选产品，绝不能把“仅基码匹配”报告为“已登记”。
3. 主线登记目标必须是 `KS` 产品成品变体；`PK#`、`HM1510`、辅料和包装物不能替代它。
4. 一个完整通途 SKU 在多个成品变体中已有正确登记时，保留全部关系，本轮不迁移、不去重。
5. 赛狐 SKU 的编号、名称、属性名和属性值以 EN 产品变体为准；新建后必须从赛狐列表 API 回读验证。不得为了本次核验更改已有 SKU 的在售状态。
6. 套件、其他非产品项和主体骨架要明确列出并暂缓，不能被静默过滤。

## Data Contract

| 系统 | 这轮使用的字段 | 作用 |
| --- | --- | --- |
| 通途 | `SKU`、`可用库存`、`货品名称/规格`、`仓库` | 只纳入可用库存大于 0 的完整 SKU；按 SKU 汇总库存与仓库 |
| EN 产品 Item | `item_code`、`item_name`、`variant_of`、`attributes`、完整 `customer_items[].ref_code` | 成品映射和赛狐 SKU 的唯一事实来源 |
| EN BOM Cost List | `产品编号`、`产品名称`、发货方式 | 定位产品范围、成本与报告展示；不能单独作为客户码全集 |
| 赛狐 SKU 列表 | `spu`、`sku`、`name`、`commodityAttributeValueRelaList` | 验证目标 EN 产品 SKU 是否存在、名称和属性是否一致 |

**为什么必须回读 EN Item：** BOM Cost List 的“客户物料号”列只可能显示一个客户码；直接拿该列做索引会漏掉同一产品变体 `customer_items` 子表里的其他完整码。审计必须拉取范围内每一个产品 Item，并由完整子表重建 `客户码 -> 产品 item_code[]` 索引。

## Workflow

### 1. 先刷新证据，不按旧报告写入

1. 从生产 EN 生成最新 BOM Cost List。报告 `key_test.bom_cost_list` 需要全部六个 filters：`item_group=产品`、`show_disabled=1`、`show_ref_code=1`、`sum_columns_at_end=1`、`pllc_sfg_missing_use_cover=0`、`simplified_column_view=0`。
2. 拉取最新通途合并库存、EN 产品 Item/Item Group、赛狐全量 SKU。
3. 运行 `missing_products/audit_three_systems.py`，先读汇总和 `通途映射全量`，再讨论任何写入。
4. 核对数量守恒：有库存唯一通途 SKU = 已精确登记 + 未精确登记；每一条未登记 SKU 必须进入一个明确分类。

### 2. 用两阶段匹配表达事实与候选

```python
complete = tongtu_sku.casefold()
base = strip_suffix(tongtu_sku).casefold()
exact_products = customer_code_to_products[complete]
candidate_products = customer_code_to_products[base] if base != complete else []

status = (
    "已精确登记" if exact_products else
    "仅基码匹配" if candidate_products else
    "真正未登记"
)
```

赛狐核验使用 `exact_products`。如果仍是“仅基码匹配”，赛狐结果必须显示“待 EN 产品映射”，而不是把基码候选误当作赛狐已覆盖。

### 3. 对真正缺口建立可审计的写入候选

仅当完整码未精确登记时，才用基码、面料、尺寸、颜色、产品族和 BOM/历史映射找候选。把候选及证据写进报告：

- `-Cover`：优先验证相同面料、尺寸、颜色的 EN 产品成品变体。
- `-Foam`：按实际适用产品族和尺寸确认产品成品变体；海绵硬度或 `HM1510` 型号是候选证据，不是登记目标。
- 拉链款弧形靠枕：PP 棉和海绵成品可共享一张皮壳。历史上一条 Cover 码可能挂在 `KS0340` 和 `KS0342`；只要求至少一个已证实适用的产品登记，本轮不强制清理一对多。
- 无法从现有资料证明唯一适用关系时：保留为“候选不唯一/待确认”，不写入生产。

写入前检查该完整客户码是否已被其他 EN 产品占用；写入后逐项重新 GET 目标 Item，确认完整 `ref_code` 已存在。`missing_products/register_product_customer_codes.py` 采用默认 dry-run，只有 `--apply` 才允许写生产。

### 4. 再处理赛狐，不拿通途半成品码建商品

对已精确映射的 EN 产品 `item_code`：

1. 从赛狐全量 SKU 列表确认对应 SPU 和 SKU 是否存在。
2. 比对 EN/赛狐的产品名称与属性对，定位缺失的属性簇或属性值。
3. 赛狐 API 没有创建属性簇/属性值端点时，先按已有模板生成属性管理 Excel，交由用户导入并确认成功。
4. 只在属性已就绪、用户确认范围后，通过 API 创建产品 SKU。请求值必须等同 EN 的 `item_code`、`item_name`、属性名和属性值。
5. 从赛狐列表 API 回读，不修改存量商品销售状态。

当赛狐缺的是产品属性，不能把 EN 模板的历史不完整属性集照搬。产品实际有颜色时，EN 和赛狐都应有颜色属性；参见 [EN 物料/变体创建惯例](erpnext-item-variant-creation-convention.md)。

### 5. 按业务问题交付报告

`missing_products/build_mainline_report.mjs` 基于最新审计生成 `通途SKU未在EN产品登记及赛狐状态_*.xlsx`。它不是只列“缺口”，而要让业务能判断每一行的处理边界：

| Sheet | 作用 |
| --- | --- |
| 汇总 | 对账数字、范围和本轮结论 |
| 套件暂缓 | 单独保留套件，不混入杂项 |
| 其他非产品项暂缓 | 辅料、ASIN、杂项等已知非产品项 |
| 皮壳通途SKU | 全部皮壳完整码、精确登记次数、赛狐产品状态 |
| 海绵通途SKU | 全部海绵完整码、精确登记次数、赛狐产品状态 |
| 主体骨架后续 | 有业务价值但不进入本轮产品主线的主体骨架 |
| 一对多历史关系 | 已存在的一个通途码到多个产品变体关系 |
| 通途映射全量 | 1411 等全部库存 SKU 的可追溯事实表 |

每条记录至少展示：完整通途 SKU、库存、EN 精确登记次数、所有 EN 产品编号、基码候选及证据、赛狐产品 SKU 状态和建议动作。

## Verified 2026-08-11 Result

本轮最新证据为：

- 通途有库存唯一 SKU：1411。
- 已精确登记在 EN 产品的 SKU：1397。
- 剩余 14 条：2 个套件和 12 个已知非产品项，均明确暂缓。
- 皮壳完整 SKU：108，全部已精确登记 EN 产品，映射产品 SKU 在赛狐均存在。
- 海绵完整 SKU：25，全部已精确登记 EN 产品，映射产品 SKU 在赛狐均存在。
- 本轮补登并回读验证的完整 Cover 码：
  - `C/Linen-Coffee-194-661-WOW-Cover` -> `KS0001-CMM-194-COFFEE`
  - `C/Linen-Natural-183-688-wow-Cover` -> `KS0001-XMMBS-183-HEMPNATURAL`
  - `TT0000750K0063009-Cover` -> `KS0002-DL-100-BLACK`

因此该轮主线不需要新建赛狐属性或 SKU。这个结论只针对当时刷新过的四个数据源；有库存、EN 或赛狐数据发生变化后，必须重新审计。

## Failed Approaches And Their Replacement

| 旧做法 | 为什么错误 | 替代做法 |
| --- | --- | --- |
| 去 `-Cover/-Foam` 后只要基码存在就认定已登记 | 销售订单导入找不到完整通途 SKU，皮壳/海绵缺口被静默掩盖 | 完整码精确匹配；基码只显示候选 |
| 只读 BOM Cost List 的一个客户物料号列 | 一个产品多个 `customer_items` 时漏掉客户码 | 回读每个 EN 产品 Item 的完整子表 |
| 用通途 `-Cover/-Foam` 编号创建赛狐商品 | 赛狐 SKU 与 EN 产品 SKU、销售订单映射和库存同步断裂 | 创建/验证 EN 产品 `item_code` 对应的赛狐 SKU |
| 把登记写到 PK#/HM1510 视为完成 | 没满足 EN 销售订单的产品物料查找路径 | 产品成品变体至少登记一次；配套物料单独调查 |
| 以“客户码全局唯一”清理所有历史一对多 | 拉链款弧形靠枕等共用皮壳确实存在可解释的一对多历史 | 先保留并报告，后续另立数据治理任务 |
| 为“修复”赛狐缺口而改现有 SKU 为停售 | EN 禁用与赛狐销售状态语义不同，越过用户授权 | 只验证/新建；不改现有赛狐销售状态 |

## Supporting-Material Investigation Boundary

主线归零后才做只读调查，不能在调查中迁移或删除配套物料客户码。`missing_products/investigate_supporting_customer_codes.py` 的 2026-08-11 结果为：

- `PK#`：没有客户物料号。
- `HM1510`：75 条原始子表行、53 个唯一“物料+客户码”组合、52 个唯一客户码；许多值带“删除”前缀。
- 唯一跨物料重复客户码是 `删除Curve-Pillow-Foam-50`，挂在 `HM1510-YD2-50x22x55-WHITE` 和 `HM1510-YD2-LLK50x22x55-WHITE`。

后续研究要同时看销售订单导入、生产、库存和 BOM，确定配套物料客户码是否值得继续维护；在结论前不得迁移、删除或将它们重新定义为主线映射。

## Verification Checklist

1. 运行 `uv run pytest tests/missing_products -q`。
2. 对审计报告验证 `有库存总数 = 已精确登记 + 未精确登记`，并检查未登记表不存在被静默丢掉的 Cover/Foam。
3. 用十条拉链款弧形靠枕 Cover 回归，确认每条至少精确登记一次，已有多挂完整保留。
4. 确认 `Curve-Pillow-50-Foam` 显示为已精确登记到既有 `KS0342` 产品。
5. 对每个生产写入回读目标 EN Item，确认完整 `customer_items.ref_code`；对每个赛狐新建回读 SKU、名称、属性和值。
6. 运行最新审计后，主线皮壳/海绵应当只有“已精确登记”和“赛狐全部存在”；套件、其他非产品项、骨架只能出现在明确的暂缓/后续表中。

## Related

- [missing_products Agent 交接](../../../missing_products/AGENT_HANDOFF.md)
- [missing_products 使用说明](../../../missing_products/README.md)
- [通途有库存 SKU 三方主线补齐复盘](../../../missing_products/docs/lessons/2026-08-11-tongtu-en-sellfox-mainline-completion.md)
- [missing-products Skill](../../../.agents/skills/missing-products/SKILL.md)
- [EN 物料/变体创建惯例](erpnext-item-variant-creation-convention.md)
- [三方审计脚本](../../../missing_products/audit_three_systems.py)
- [产品客户码写入脚本](../../../missing_products/register_product_customer_codes.py)
- [配套物料只读调查脚本](../../../missing_products/investigate_supporting_customer_codes.py)
