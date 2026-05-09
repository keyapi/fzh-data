# category — 赛狐商品分类导入

根据 EN 物料属性中的「赛狐分类」字段和赛狐官方「商品分类导出」树，为赛狐商品导出的每个 SKU 生成完 整的 4 级分类路径，写入赛狐「导入更新商品分类」模板。

## 背景

- 赛狐商品需维护 4 级分类（一级→四级），但「商品导出」中只有单列 `分类`
- EN 物料属性表（`Sheet1`）中 `款式ID` ↔ `赛狐分类`（末级类名）的映射由人工维护
- 「商品分类导出」是赛狐官方分类树，具有层级结构

本脚本将三者交叉验证，生成可直接导入赛狐的分类更新文件，并在控制台和 Excel 报告中标注需人工处理的行。

## 管道

```
赛狐商品导出（SKU 列）  ──┐
                          ├──→ 按 款式ID 查 EN物料属性「赛狐分类」──→ 查 商品分类导出 树
EN物料属性（款式ID-赛狐分类）──┘                                              │
                                                    ┌─────────────────────────┘
商品分类导出（4级树）  ──────────────────────────────┘
                                                    ↓
                          赛狐_导入更新商品分类.xlsx（4 个 sheet）
```

## 使用方法

```bash
cd category
python build_saihu_category_import.py

# 指定文件
python build_saihu_category_import.py \
  --category-export "商品分类导出.xlsx" \
  --template "模板 导入更新商品分类.xlsx" \
  --spu-status "../multi_attr_saihu/EN物料属性.xlsx" \
  --commodities "../edit_item/商品导出.xlsx" \
  --out "输出.xlsx"
```

## 命令行参数

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `--category-export` | `商品分类导出-20260423114344342.xlsx` | 赛狐官方分类导出 |
| `--template` | `模板 导入更新商品分类-20260423114106574.xlsx` | 赛狐导入模板 |
| `--spu-status` | `../multi_attr_saihu/EN物料属性 产品 x1167 修正后 20260415 1102.xlsx` | 物料属性表 |
| `--commodities` | `../edit_item/商品导出 x2215 Commodities2026_04_23(1).xlsx` | 赛狐商品导出 |
| `--out` | 自动生成时间戳文件名 | 输出路径 |

## 输出文件（4 个工作表）

| 工作表 | 内容 |
|--------|------|
| `商品` | 主导入表：`*SKU` + 一级/二级/三级/四级分类 |
| `核对` | 每行 SKU 的校验明细（状态、说明） |
| `错误报告` | 仅需人工处理的异常行（非 ok），含处理建议 |
| `款式_赛狐分类校验` | 每个款式 ID 的「赛狐分类」与官方树对照 |

## 校验规则（CategoryIndex）

`CategoryIndex` 从「商品分类导出」建立末级类名到 4 级路径的索引：

| 状态 | 含义 | 处理 |
|------|------|------|
| `ok` | 末级名在树中唯一匹配 | 直接写入 4 级分类 |
| `not_leaf` | 类名存在但有子级 | 改用最末级名称 |
| `ambiguous_leaf` | 同一末级名对应多条路径 | 需人工指定更细类名 |
| `unknown` | 类名在树中不存在 | 补全物料表或新增分类 |
| `no_style` | 款式 ID 不在物料表中 | 补全物料表 |
| `no_category` | 物料表中赛狐分类为空 | 填写分类 |

## 跨模块依赖

- 动态导入 `multi_attr_saihu/erpnext_to_saihu.py` 中的 `_default_spu_from_sku()`，用于从 SKU 推断款式 ID
- 不修改 `erpnext_to_saihu.py`

## 更多细节

参见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
