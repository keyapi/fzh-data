# item_weight_size — Agent 交接说明

> **脚本**: `build_saihu_weight_import.py`（单一主脚本）  
> **人读文档**: [README.md](README.md)

---

## 1. 业务背景

赛狐「商品重尺」导入：为每个 SKU 填入国外发货包装尺寸重量，用于尾程物流（UPS/FedEx）计算运费。

**重量模板概念**：同一品类-面料-尺寸的 SKU（仅颜色不同），重尺一致。因此只需在重量模板（不含颜色，物料编码前缀 `ZLMB#`）中维护一次，然后按前缀匹配到所有颜色变体。

---

## 2. 管道步骤

```
./数据源/*.xlsx
  → _read_saihu_export → SKU + spu 列表（2214 行）
  → _read_weight_data → 重量模板（798 行，含 5 个手填字段）
  → _build_mapped_rows:
      1. 重量模板 → dict[匹配键, row]（去 ZLMB# 前缀）
      2. 逐 SKU 取前 3 段作为匹配键
      3. 匹配成功 → 校验长宽高 → 通过则计算字段
      4. 匹配失败/校验失败 → MappedRow 全空
  → _write_output（openpyxl 模板写盘）
  → _write_issues（4 类问题报告）
```

---

## 3. 关键函数

| 函数 | 作用 |
|------|------|
| `_saihu_match_key(sku)` | 赛狐 SKU 前 3 段为键（≥4 取[:3], =3 全串, <3 返回 None） |
| `_weight_match_key(code)` | 去除 `ZLMB#` 前缀得键 |
| `_build_mapped_rows(saihu_df, weight_df, issues)` | 核心匹配+校验+计算 |
| `_write_output(template, out, rows)` | 用 openpyxl 打开模板，填充 `商品` sheet |
| `_write_issues(out, issues, reports)` | 写多 sheet 问题报告 |

### `MappedRow` 数据类

```python
@dataclass
class MappedRow:
    sku: str
    box_l/w/h: float | None       # 箱规 = 包装长宽高
    box_weight_kg: float | None   # 单箱重量 = 实重(g) × 装箱量 / 1000
    box_qty: int | None          # 装箱量（默认 1）
    pkg_l/w: float | None        # = 包装长宽
    pkg_h: float | None          # = 包装高 / 装箱量（简化算法）
    pkg_weight: float | None     # = 实重(g)（暂按单个重量）
```

---

## 4. 字段映射速查

| 模板列 | 数据来源 | 公式 |
|--------|----------|------|
| `*SKU` | 赛狐导出 SKU | 直填 |
| `商品规格长~商品重量单位` | — | 留空（暂不使用） |
| `箱规长(cm)` | `国外分公司成品包装长(cm)` | 直填 |
| `箱规宽(cm)` | `国外分公司成品包装宽(cm)` | 直填 |
| `箱规高(cm)` | `国外分公司成品包装高(cm)` | 直填 |
| `单箱重量(kg)` | 实重 + 装箱量 | `实重(g) × 装箱量 ÷ 1000` |
| `单箱数量(PCS)` | `装箱量` | 缺省→1 |
| `商品包装规格长(cm)` | `国外分公司成品包装长(cm)` | 同箱规长 |
| `商品包装规格宽(cm)` | `国外分公司成品包装宽(cm)` | 同箱规宽 |
| `商品包装规格高(cm)` | 包装高 + 装箱量 | `包装高 ÷ 装箱量` |
| `商品包装重量` | `实重(g)` | 直填（暂按单个重量） |
| `商品包装重量单位` | — | 固定 `g` |

---

## 5. 校验与问题报告

| Sheet | 内容 |
|-------|------|
| `汇总` | 总行数、已填充数 |
| `重量模板_长宽高不全` | 匹配成功但长宽高任一缺失（不填充） |
| `重量模板_未匹配赛狐SKU` | 重量模板键无法匹配任何赛狐 SKU |
| `赛狐SKU_未匹配重量模板` | 赛狐 SKU 找不到对应重量模板 |
| `装箱量_已默认1` | 长宽高有值但装箱量缺失，已默认 1 |

**校验规则**：
- 长宽高必须三者全部有值，才填充该模板对应的所有 SKU
- 装箱量缺省→1（仅在长宽高都有值时生效）

---

## 6. 命令行

```bash
cd item_weight_size
python build_saihu_weight_import.py
python build_saihu_weight_import.py --weight-data path/to/data.xlsx
python build_saihu_weight_import.py --template path/to/template.xlsx
python build_saihu_weight_import.py --out-dir custom_output
```

---

## 7. 数据路径约定

| 角色 | 默认查找规则 |
|------|-------------|
| 重量数据 | `./数据源/` 下文件名含「重尺数据」的最新 xlsx |
| 赛狐导出 | `./数据源/` 下文件名含「商品导出」+「填重尺」的最新 xlsx |
| 模板 | `./数据源/` 下文件名含「模板」+「商品重尺」的最新 xlsx |
| 输出 | `./out/` |

`_ROOT = _DIR.parent`（工作区根目录）。

---

## 8. 列名常量

彭建数据列：`COL_WT_CODE`（物料编码）、`COL_WT_GROSS_WEIGHT`（实重 g）、`COL_WT_PKG_L/W/H`（包装长宽高 cm）、`COL_WT_BOX_QTY`（装箱量）。

赛狐导出列：`COL_SX_SKU`、`COL_SX_SPU`。

输出列：`COL_OUT_SKU`（`*SKU`）、`COL_OUT_BOX_L/W/H`（箱规）、`COL_OUT_BOX_WEIGHT`（单箱重量 kg）、`COL_OUT_BOX_QTY`（单箱数量 PCS）、`COL_OUT_PKG_L/W/H/WEIGHT/WEIGHT_UNIT`。

---

*若与代码不一致，以 `build_saihu_weight_import.py` 为准。*
