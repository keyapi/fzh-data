---
okf: v0.1
type: Reference
title: 物料组英文翻译管道
description: EN Item Group item_group_translation 批量翻译的数据范围、脚本与报告格式
tags: [en-api, item-group, translation, tmt]
resource: EN_API/translate_item_group_names.py
timestamp: 2026-08-31
---

# 物料组英文翻译管道

## 字段

| 项 | 值 |
|----|-----|
| DocType | Item Group |
| 字段名 | `item_group_translation` |
| 标签 | 物料组翻译 |
| 类型 | Data |
| 加入时间 | 2026-06-29（生产） |

## 目标节点选择

```text
parent 链包含「产品」
AND (
  is_group == 0                    # 普通叶子
  OR is_leaf_group == 1            # LGKS 叶子组
)
```

2026-08 生产统计：424 条（398 KS + 12 其他叶子 + 14 LGKS）。

## 脚本

| 文件 | 作用 |
|------|------|
| `translate_item_group_names.py` | 主流程：拉取 → TMT → Excel → 可选写回 |
| `test_tmt_connectivity.py` | 3 条样例冒烟 |

## CLI

| 参数 | 说明 |
|------|------|
| `--dry-run` | 默认。出 Excel，不写 EN |
| `--fetch-only` | 无 TMT 密钥时仅中文名单 |
| `--apply` | 写回 `item_group_translation` |
| `--env prod\|test` | 默认 prod |

## 报告列（明细 sheet）

`序号`, `name`, `物料组名`, `custom_model_id`, `父级`, `节点类型`, `中文`, `英文`, `现有翻译`, `处理结果`, `状态`, `备注`

## 写回规则

- 仅 `处理结果=成功` 且英文非空
- 若 `现有翻译` 已与译文相同 → 跳过
- `--apply` 时 PUT 单字段，间隔 0.15s

## 与报关脚本分工

- **本管道**：款式级 `item_group_translation`
- **`customs_export.py`**：DN 行聚合物料中文名 → DeepSeek 英文（发票/装箱单/报关单 D 列等）
