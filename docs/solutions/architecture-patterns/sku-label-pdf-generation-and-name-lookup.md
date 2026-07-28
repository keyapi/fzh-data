---
title: SKU 背贴 PDF 生成与通用名称查询模式
date: 2026-07-28
category: architecture-patterns
module: sellfox_shipping
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - 需要为包裹生成 SKU 背贴 PDF（仓库识别标签）
  - 需要根据 commodity_sku 查询中文/西班牙语品名
  - 需要在 PDF 中正确渲染中英混排文本
tags: [sku-label, back-sticker, pdf, reportlab, sku-name-lookup, erpnext, gspread]
---

# SKU 背贴 PDF 生成与通用名称查询模式

## Context

跨境电商仓库发货时需要在包裹上贴背贴——一张 4×2 英寸的小标签，标注包裹号、内含 SKU 及其中文/西班牙语名称。此前由 Google Colab notebook 生成，需要在 sellfox_shipping 子项目中实现。

Colab notebook 已经跑了 2 年，逻辑稳定但有技术债：Google service account 私钥硬编码在 notebook 里。

详见：`sellfox_shipping/docs/research/sku-label-back-sticker-analysis-2026-07-28.md`

## Guidance

### 1. PDF 生成：直接移植 notebook 逻辑

用 `reportlab` 生成 4×2"（288×144 points）PDF，不要重写核心算法。

**关键参数：**
- 页面：`(288, 144)` points
- 表格列宽：`[0.4cm, 2.55cm, 0.5cm, 3.25cm, 3.35cm]`
- 表头：`['#', 'SKU', 'QTY', 'Name Chinese', 'Nombres en español']`
- 中文字体：`STSong-Light`（reportlab 内置 UnicodeCIDFont）
- 自适应缩放：起始 10pt，最小 5pt，步进 0.9

**不要做的：**
- 不要换字体方案（已稳定运行 2 年）
- 不要重写中英混排逻辑（`split_text_by_language` + `build_mixed_xml`）
- 不要改表格列宽（仓库已习惯当前布局）

### 2. SKU 名称查询：通用 lookup 类

新建 `SkuNameLookup` 类，按优先级链查询：

```
commodity_sku → ERPNext Item.item_name → Google Sheets → SKU 编码兜底
```

复用已有 `erpnext_dims_v2.py` 的 EN API 认证模式（`token {api_key}:{api_secret}`），批量预热 `prefetch()` 方法。

**接口：**
```python
lookup = SkuNameLookup(erpnext_base=..., erpnext_api_key=..., erpnext_api_secret=...)
name = lookup.get("KS0002-DL-194")
# → {"cn": "靠枕内胆 194cm", "es": "Relleno cojín 194cm"}
```

### 3. 回退策略（来自 Colab notebook 遗产）

| 名称 | 第一来源 | 回退 |
|------|---------|------|
| 中文名称 | ERPNext Item `item_name` | Google Sheets `中文名称` → SKU 编码 |
| 西班牙语名称 | ERPNext Item `custom_spanish_name`（如有） | Google Sheets `西班牙语名称` → 留空 |

### 4. 凭证安全

Google service account 私钥**不入 git**。通过环境变量 `GOOGLE_SERVICE_ACCOUNT_FILE` 指向本地文件，单独渠道传递。

## Why This Matters

- **避免重复踩坑**：中文字体、中英混排、自适应缩放这些坑 notebook 已经踩过并解决
- **通用工具复用**：`SkuNameLookup` 不只服务背贴，包裹详情页、面单品名填充都可以用
- **安全基线**：硬编码私钥是 notebook 的反面教材，新实现必须走环境变量

## When to Apply

- 实现背贴 PDF 生成时：直接用本文和 research doc 里的代码
- 任何需要根据 commodity_sku 查品名的地方：用 `SkuNameLookup`
- 生成任何含中文的 PDF 时：参考中英混排方案

## Examples

生成一个包裹的背贴：

```python
from sellfox_shipping.sku_label.pdf_generator import generate_sku_label_pdf
from sellfox_shipping.sku_label.name_lookup import SkuNameLookup

lookup = SkuNameLookup(
    erpnext_base="https://erpnext.vilavi.cn",
    erpnext_api_key=os.getenv("ERP_API_KEY"),
    erpnext_api_secret=os.getenv("ERP_API_SECRET"),
)

items = []
for item in package.items:
    sku = item.commodity_sku or item.seller_sku
    names = lookup.get(sku)
    items.append({
        "sku": sku, "qty": item.quantity,
        "cn_name": names["cn"], "es_name": names["es"],
    })

generate_sku_label_pdf(
    [{"package_sn": package.package_sn, "items": items}],
    "sku_label.pdf",
    timestamp="07.28",
)
```

## Related

- `sellfox_shipping/docs/research/sku-label-back-sticker-analysis-2026-07-28.md` — 完整代码级实现指南
- `sellfox_shipping/docs/research/colab-notebook-legacy-summary-2026-07-17.md` — Colab notebook 遗产摘要
- `sellfox_shipping/carriers/lizard/erpnext_dims_v2.py` — 可复用的 EN API 认证模式
