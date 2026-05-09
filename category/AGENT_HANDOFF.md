# category — Agent 交接说明

> **脚本**: `build_saihu_category_import.py`（477 行，唯一主脚本）  
> **人读文档**: [README.md](README.md)

---

## 1. 业务背景

赛狐商品需要 4 级分类（一级→四级），但：
- 赛狐「商品导出」只有单列 `分类`（不完整）
- EN 物料属性表中人工维护 `款式ID` ↔ `赛狐分类`（末级类名）
- 赛狐「商品分类导出」是唯一的官方分类树

本脚本把三者交叉验证，生成赛狐可直接导入的「导入更新商品分类」xlsx。

---

## 2. 管道步骤

```
赛狐商品导出（SKU/spu列）
  → 读 EN物料属性 Sheet1（款式ID→赛狐分类 map）
  → 读 商品分类导出 → CategoryIndex（末级名→4级路径）
  → 逐 SKU 校验：
      1. SKU 为空 → no_sku
      2. 从 SKU 推断款式ID（_default_spu_from_sku）
      3. 款式ID 不在物料表 → no_style
      4. 赛狐分类为空 → no_category
      5. CategoryIndex.resolve(分类名) → ok/not_leaf/ambiguous_leaf/unknown
  → 写 4 sheet xlsx + 控制台报告
```

---

## 3. 关键类型与函数

### `CategoryIndex(path)` — 分类树索引
- `leaf_to_paths: dict[str, list[tuple]]` — 末级名→4级路径列表
- `all_names: set[str]` — 树中所有类名
- `resolve(name) -> (status, path_or_None, message)`
  - `ok`: 末级名唯一，返回 path
  - `not_leaf`: 有子级，非末级
  - `ambiguous_leaf`: 多条路径
  - `unknown`: 无匹配

### 核心函数

| 函数 | 作用 |
|------|------|
| `load_style_saihu_map(path)` | 读物料属性 Sheet1 → `dict[款式ID, 赛狐分类]` |
| `_import_default_spu_from_sku()` | 动态加载 `multi_attr_saihu/erpnext_to_saihu.py` 的 `_default_spu_from_sku` |
| `_build_sku_error_rows(report)` | 从核对数据提取异常 SKU 行（排除 ok 和注记） |
| `_build_style_audit(style_map, idx)` | 款式级别分类校验 |
| `_write_excel(...)` | 用模板写 4 sheet |
| `_print_console(...)` | 控制台摘要（异常统计、款式校验要点） |

### 常量

```python
CATEGORY_COLS = ("一级分类", "二级分类", "三级分类", "四级分类")
OUT_COLS = ("*SKU", "一级分类", "二级分类", "三级分类", "四级分类")
SHEET_MAIN = "商品"
SHEET_REPORT = "核对"
SHEET_ERRORS = "错误报告"
SHEET_STYLE_AUDIT = "款式_赛狐分类校验"
```

`STATUS_TO_CN` 将技术状态码映射为中文显示。

---

## 4. 跨模块依赖

`_import_default_spu_from_sku()` 使用 `importlib.util` 动态导入：
```python
mod_path = _ROOT / "multi_attr_saihu" / "erpnext_to_saihu.py"
# 加载 _default_spu_from_sku 函数
```

用于：当商品导出中 `spu` 列为空时，从 `SKU`（如 `KS0001-HLR-160-BLUE`）推断款式 ID（`KS0001`）。

---

## 5. 命令行

```bash
cd category
python build_saihu_category_import.py
python build_saihu_category_import.py --out custom.xlsx
python build_saihu_category_import.py --category-export "新分类导出.xlsx"
```

---

## 6. 数据路径约定

| 角色 | 默认值 |
|------|--------|
| 分类导出 | `category/商品分类导出-20260423114344342.xlsx` |
| 模板 | `category/模板 导入更新商品分类-20260423114106574.xlsx` |
| 物料属性 | `multi_attr_saihu/EN物料属性 产品 x1167 修正后 20260415 1102.xlsx` |
| 商品导出 | `edit_item/商品导出 x2215 Commodities2026_04_23(1).xlsx` |
| 输出 | `edit_item/赛狐_导入更新商品分类_YYYYMMDD_HHMMSS.xlsx` |

---

## 7. 输出工作表

| 工作表 | 受众 | 内容 |
|--------|------|------|
| `商品` | 赛狐导入 | `*SKU` + 4 级分类列 |
| `核对` | 运营核对 | 逐行状态、说明 |
| `错误报告` | 运营修正 | 仅需处理的行，含处理建议 |
| `款式_赛狐分类校验` | 运营修正 | 每个款式级别的分类对照 |

---

## 8. 已知问题

- **权限错误**: 关闭 Excel 中打开的目标文件后重试
- **动态导入失败**: 确保 `multi_attr_saihu/erpnext_to_saihu.py` 存在且包含 `_default_spu_from_sku`
- **分类匹配偏差**: 物料表中的「赛狐分类」必须与「商品分类导出」中的末级类名**完全一致**（含空格）

---

*若与代码不一致，以 `build_saihu_category_import.py` 为准。*
