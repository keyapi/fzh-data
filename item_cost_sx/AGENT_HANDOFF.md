# item_cost_sx — Agent 交接说明

> **脚本**: `bom_cost_to_saihu_item_cost.py`（622 行，唯一主脚本）  
> **人读文档**: [README.md](README.md)

---

## 1. 业务背景

ERPNext 定制报表「产品 BOM 成本列表」→ 计算绍兴发货成本 → 与赛狐商品导出 SKU 求交 → 生成赛狐采购成本导入文件（两列/三列）。

核心问题：赛狐导入不接受 `采购成本=0`（与空同等对待）；BOM 未维护完整的行需按「品类-面料-尺寸」键借用兄弟颜色成本。

---

## 2. 管道步骤

```
en_bom_cost_list/*.xlsx（Query Report）
  → _read_bom_excel
  → _process_bom_dataframe（去重保留末行、计算绍兴发货成本）
  → _apply_sku_borrow（同前缀成本借用）
  → _detail_with_sai_col（标记赛狐是否存在）
  → _saihu_import_frame（生成「商品」表：*SKU、采购成本(CNY)、采购备注）
  → _write_result / _write_issues
```

---

## 3. 关键函数与数据类

| 符号 | 作用 |
|------|------|
| `_compute_ship_cost(mode, pk, bcp, tot)` | 按 皮壳/半成品/成品 计算绍兴发货成本 |
| `_apply_sku_borrow(detail)` | 同前缀借用：≥4 节取前 3 节为键，一轮借用 |
| `_saihu_purchase_cost_export(v)` | 赛狐导出规则：NaN/0→None |
| `_latest_xlsx(folder)` | 取目录中最新 xlsx，排除 ~$ 锁文件 |
| `_read_saihu_sku_set(path)` | 读赛狐「商品」工作表 SKU 列作白名单 |
| `_openpyxl_clear_column_nan(...)` | 写盘后清 NaN/0（赛狐不接受 0） |
| `ProcessResult` | `detail: DataFrame` + `issues: list[dict]` |

---

## 4. 业务规则速查

### 4.1 绍兴发货成本

| 发货方式 | 公式 |
|----------|------|
| 皮壳 | `皮壳成本` |
| 半成品 | `皮壳成本` + `绍兴包装半成品成本` |
| 成品 | `绍兴总成本` |
| 其它/空 | 无法计算 |

### 4.2 同前缀成本借用

- SKU 按 `-` 分段：≥4 段取前 3 段为键（品类-面料-尺寸）
- 出借方：同键下第一次出现的非 0、非空初算成本
- 借入方：初算为空/NaN/0 的行
- 仅一轮，借用来源写入 `成本借用自(产品编号)` 列

### 4.3 赛狐导入工作表

- 工作表名必须为 `商品`（常量 `SAI_HU_SHEET`），非 `Sheet1`
- 列：`*SKU`、`采购成本(CNY)`、`采购备注`
- `采购备注`：仅当有有效成本时填写 `EN绍兴发货成本-` + 发货方式

---

## 5. 命令行

```bash
cd item_cost_sx
python bom_cost_to_saihu_item_cost.py
python bom_cost_to_saihu_item_cost.py --bom-dir ../en_bom_cost_list --out-dir out
python bom_cost_to_saihu_item_cost.py --saihu-commodities "path/商品导出.xlsx"
python bom_cost_to_saihu_item_cost.py --skip-saihu-match  # 不过滤赛狐 SKU
python bom_cost_to_saihu_item_cost.py --source path/specific.xlsx
```

---

## 6. 数据路径约定

| 角色 | 默认位置 |
|------|----------|
| EN BOM 源 | `../en_bom_cost_list/`（取最新 xlsx） |
| 赛狐商品清单 | `../edit_item/商品导出 x2215 Commodities2026_04_23(1).xlsx` |
| 输出 | `./out/` |

路径均相对于工作区根目录（脚本内 `_ROOT`），脚本通过 `os.chdir()` 从自身目录运行。

---

## 7. 输出文件

- `赛狐_采购成本导入_YYYYMMDD_HHMMSS.xlsx` — 工作表 `商品`（可导入子集）
- `BOM成本处理_问题报告_YYYYMMDD_HHMMSS.xlsx` — 问题汇总 + 对账（仅EN有 / 仅赛狐有）

---

## 8. 与其它模块的关系

- 与 `category/`、`multi_attr_saihu/` **独立**，无代码依赖
- 仅可能共用「赛狐商品导出」作为数据源

---

## 9. 已知问题

- **Permission denied**: 关闭 Excel 中打开的目标文件后重试
- **工作表名错误**: 赛狐要求为 `商品`，若手工另存勿改为 `Sheet1`
- **借用为 0**: 确认同键下是否存在非 0 初算行

---

*若与代码不一致，以 `bom_cost_to_saihu_item_cost.py` 为准。*
