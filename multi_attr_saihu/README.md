# multi_attr_saihu — ERPNext/通途 → 赛狐多属性商品导入

将 ERPNext 纵向物料导出和通途 SKU 别名转换为赛狐多属性商品导入模板。

## 三个脚本

| 脚本 | 职责 |
|------|------|
| `erpnext_to_saihu.py` | ERPNext 纵向物料导出 → 赛狐 `商品` 表（属性 面料→尺寸→颜色），可选按在售/库存拆 3 个文件 |
| `tongtu_sku_explode.py` | 通途 `SKU别名` 按 `;` 炸成每行一个别名 |
| `erp_tongtu_bridge.py` | ERP 通途SKU 导出 + 炸开表 → 赛狐配对导入，按客户物料号对齐 |

## 快速开始

```bash
cd multi_attr_saihu
uv sync    # 在仓库根目录执行一次

# 1. 炸开通途 SKU 别名
python tongtu_sku_explode.py [通途普通商品.xlsx]

# 2. ERP 纵向物料 → 赛狐多属性导入
python erpnext_to_saihu.py [物料导出.xlsx] [模板.xlsx] --spu-status "EN物料属性.xlsx"

# 3. 通途配对
python erp_tongtu_bridge.py [通途SKU导出.xlsx] -t 通途SKU别名炸开.xlsx --spu-status "EN物料属性.xlsx"
```

## 文件依赖

- `erp_tongtu_bridge.py` 依赖同目录 `erpnext_to_saihu.py`（import `_default_spu_from_sku`, `load_spu_status_maps`）
- 输入 Excel 文件不纳入 Git（`.gitignore` 忽略 `*.xlsx`）

## 更多细节

参见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。
