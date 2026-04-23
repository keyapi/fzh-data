# 赛狐 / ERPNext / 通途 数据流水线 — Agent 交接说明

> **用途**：本文件供在新工作区（例如打开 `D:\Work\赛狐\Cursor`）后接手任务的 Agent 阅读，以恢复业务背景、脚本职责与使用方式。  
> **代码位置**：与本文件同目录的 3 个 Python 脚本（历史文件夹名：`导入多属性商品`, 已改为 `multi_attr_saihu`）。

---

## 1. 文件夹与路径说明

| 说明 | 内容 |
|------|------|
| **历史路径** | `D:\Work\赛狐\Cursor\导入多属性商品\` |
| **已改为英文目录名**（便于上层 Agent / CI） | 已改为 `multi_attr_saihu`；重命名后已更新本文档中的路径描述。 |
| **脚本互相依赖** | `erp_tongtu_bridge.py` **import** `erpnext_to_saihu` 中的 `_default_spu_from_sku`、`load_spu_status_maps`。三文件应保持在 **同一目录** 或调整 `PYTHONPATH` / 包结构。 |

**依赖**：`pandas`、`openpyxl`（`pip install pandas openpyxl`）。

**Git**：仓库内 `.gitignore` 忽略 `*.xlsx`（大文件不提交）；通常只跟踪 `.py`、本 `md`、`.gitignore`。

---

## 2. 业务背景（精简）

- **ERPNext**：导出两类 Excel：  
  - **纵向多属性物料表**（`物料` 工作表）：每个 SKU 多行，属性在「属性 / 属性值」列展开。  
  - **通途客户物料子表导出**：`物料编码` + `客户物料号 (客户物料)` 一对多；主表列仅在首行有值，续行为空。  
- **赛狐（Saihu）**：多属性商品导入模板 `*spu_add_new_sku*.xlsx`，工作表 **`商品`**，列为扁平的 `*SPU`、`*款名`、`*SKU`、`*品名`、`*属性1` / `*属性值(中)1`、`属性2`… 等。  
- **通途**：`通途普通商品.xlsx` 含主 `SKU` 与分号分隔的 `SKU别名`；需 **炸开** 成一行一个别名，供与 ERP 客户物料号对齐。  
- **物料属性表**：`EN物料属性*.xlsx` 的 **`Sheet1`**，列 **`款式ID`**（与赛狐 `*SPU` 规则一致：物料编码第一个 `-` 前前缀）、**`在售`**（1/0）、**`还有库存`**（仅 **`有`** 算有库存；无/空/其它为无库存）。用于把结果拆成「在售 / 不在售有库存 / 不在售无库存」。

**款式ID = *SPU**：`_default_spu_from_sku("KS0001-HLR-160-BLUE")` → `"KS0001"`。

---

## 3. 流水线总览（推荐执行顺序）

```
通途普通商品.xlsx  ──►  tongtu_sku_explode.py  ──►  通途SKU别名炸开.xlsx

ERP 纵向导出（无模板/不含通途SKU）──►  erpnext_to_saihu.py  ──►  赛狐导入_在售_*.xlsx
        ▲                                    （+ 物料属性 + 赛狐模板）   赛狐导入_不在售有库存_*.xlsx
        │                                                              赛狐导入_不在售无库存_*.xlsx

ERP 通途SKU 导出 + 通途SKU别名炸开 + 物料属性  ──►  erp_tongtu_bridge.py  ──►  赛狐配对导入_在售.xlsx
                                                                                  赛狐配对导入_不在售有库存.xlsx
                                                                                  赛狐配对导入_不在售无库存.xlsx
                                                     （可选）ERP通途SKU配对.xlsx、冲突检验 xlsx
```

---

## 4. `erpnext_to_saihu.py`

### 4.1 作用

将 ERPNext **纵向** 物料导出转为赛狐 **`商品`** 表结构；属性列固定顺序为 **面料 → 尺寸 → 颜色**；按 **`*SKU` 字符串升序** 排序；可选按物料属性表拆 **三个** 输出文件。

### 4.2 输入

| 来源 | 说明 |
|------|------|
| **ERP 导出** | 工作表默认索引 `0`（通常为 `物料`）。必填列：`物料编码`、`物料组`、`物料名称`、`属性 (规格属性)`、`属性值 (规格属性)`。 |
| **赛狐模板** | `*spu_add_new_sku*.xlsx`，从中复制表头与其它 sheet，只覆盖 `商品` 表数据行。 |
| **物料属性**（可选拆分） | `Sheet1`：`款式ID`、`在售` 必填；`还有库存` 可选。 |

### 4.3 自动选择 ERP 文件规则（未传 `erp_path` 时）

- 必须：文件名含 **`物料导出`**。  
- **排除**：子串 **`产品 通途SKU`**（配对用导出，如 `EN物料导出 产品 通途SKU x2270 …`）。  
  - **不能**用简单排除 `通途SKU`，否则 **`不含通途SKU`** 的正确文件会被误伤。  
- 另排除：`spu_add`、`转换结果`、`物料属性`、`配对`、`炸开`。  
- 多候选时取 **`os.path.getmtime` 最新**。

### 4.4 输出（默认文件名，均在脚本所在目录）

| 文件 | 条件 |
|------|------|
| `赛狐导入_在售_转换结果.xlsx` | `在售==1` |
| `赛狐导入_不在售有库存_转换结果.xlsx` | `在售==0` 且 `还有库存` 规范化后等于 **`有`** |
| `赛狐导入_不在售无库存_转换结果.xlsx` | `在售==0` 且无库存，或 **款式ID 不在物料属性表** |
| `赛狐导入_转换结果.xlsx` | 仅当 `--no-spu-split`（不读物料属性，单文件） |

### 4.5 核心逻辑说明

- **`parse_erp_blocks`**：按「`物料编码` 非空」开新块；块内根据属性名列归类到 `面料/尺寸/颜色`。  
- **`_classify_attr`**：**必须先按后缀** `颜色` / `尺寸` / `面料` 匹配，再回退子串。原因：物料组名可能含 **`大尺寸`**，子串 **`尺寸`** 会误判 **`…颜色`** 行。  
- **`blocks_to_saihu_rows`**：`*SPU` = 物料编码首段；`*款名` = `物料组`；`*SKU` = `物料编码`；`*品名` = `物料名称`。  
- **`load_spu_status_maps`**：返回 `(在售 dict, 还有库存 bool dict)`；重复 `款式ID` **末行覆盖**。无 `还有库存` 列则库存全 `False`。  
- **`load_spu_onsale_map`**：仅返回在售 dict，供 `erp_tongtu_bridge` 若只关心在售时使用（当前 bridge 已改用 `load_spu_status_maps`）。  
- **`write_with_template_simple`**：openpyxl 打开模板、删 `商品` 表第 2 行起、写入字典键与表头匹配列。

### 4.6 命令行摘要

```text
python erpnext_to_saihu.py [ERP.xlsx] [template.xlsx]
  --spu-status PATH
  --out-onsale / --out-offsale-stock / --out-offsale-nostock
  --no-spu-split
```

---

## 5. `tongtu_sku_explode.py`

### 5.1 作用

读取通途 **`通途普通商品.xlsx`**（默认），将 **`SKU别名`** 按 **`;`** 炸成多行；主 **`SKU`** 参与合并进待拆列表；**输出仅三列**：`SKU`、`SKU别名`、`商品名称`，列顺序为 **`SKU` 在左、`SKU别名` 其次**。

### 5.2 与 Colab 的差异处理

- 空别名：不拼成 `主SKU;` 再拆（避免多出一行空别名），仅保留一行主 SKU。

### 5.3 默认 IO

- 输入：`通途普通商品.xlsx`  
- 输出：`通途SKU别名炸开.xlsx`

### 5.4 命令行

```text
python tongtu_sku_explode.py [input.xlsx] -o output.xlsx --sheet 0
```

---

## 6. `erp_tongtu_bridge.py`

### 6.1 作用

把 **ERP「通途SKU」导出**（含 `客户物料号 (客户物料)` 子表多行）与 **`通途SKU别名炸开.xlsx`** 按客户物料号对齐；再按物料属性 **在售 / 还有库存** 拆成三个配对结果；可选写 **跨物料编码冲突检验** 与全量配对表。

### 6.2 依赖同目录 `erpnext_to_saihu.py`

- `from erpnext_to_saihu import _default_spu_from_sku, load_spu_status_maps`

### 6.3 ERP 源文件自动选择（未传 `erp_path`）

- 含 **`物料导出`** 与 **`通途SKU`**；排除 **`别名`、`炸开`、`配对`**（避免选到炸开结果或本脚本产出）。  
- 多文件取 **修改时间最新**。

### 6.4 数据处理要点

1. **`prepare_erp_customer_rows`**：`ffill` 主表列 → 删空客户物料号 → **`(物料编码, 客户物料号)` 去重**（同一物料下同一通途号多行只留一行，忽略客户组差异）。  
2. **`build_cross_item_conflict_report`**：去重后，若同一 **客户物料号** 对应 **多个不同物料编码**，写入检验报告（**不修改**配对结果）。  
3. **`tongtu_to_long_match_rows`**：通途每行生成匹配键：**主 SKU** 与 **SKU别名**（若与主 SKU 不同则两条），merge 时 **左连接**。  
4. **输出列**：`物料组`、`物料编码`、`客户物料号 (客户物料)`、`通途主SKU`（即通途表 `SKU`）、`SKU别名`、`商品名称`。  
5. **拆分**：与 `erpnext_to_saihu` 相同规则（`在售==1` / `在售==0`+有库存 / 其余含未映射）。

### 6.5 默认输出文件

| 文件 | 说明 |
|------|------|
| `赛狐配对导入_在售.xlsx` | |
| `赛狐配对导入_不在售有库存.xlsx` | |
| `赛狐配对导入_不在售无库存.xlsx` | |
| `ERP通途客户物料号_跨物料编码冲突检验.xlsx` | 默认生成；`--no-conflict-report` 可关 |
| `ERP通途SKU配对.xlsx` | 仅 `--write-combined` |

### 6.6 命令行摘要

```text
python erp_tongtu_bridge.py [ERP通途SKU.xlsx] -t 通途SKU别名炸开.xlsx
  --spu-status PATH
  --out-onsale / --out-offsale-stock / --out-offsale-nostock
  --write-combined [--output-combined PATH]
  --conflict-report PATH | --no-conflict-report
  --sheet-erp / --sheet-tongtu
```

---

## 7. 已解决过的典型问题（供排查）

1. **属性丢失（如「大尺寸…」）**：已改为后缀匹配 `面料/尺寸/颜色`。  
2. **`erpnext_to_saihu` 误选 `赛狐配对*.xlsx`**：自动选源要求 **`物料导出`** 且 **非** `产品 通途SKU`。  
3. **`erp_tongtu_bridge` 误选 `通途SKU别名炸开`**：要求文件名同时含 **`物料导出`** 与 **`通途SKU`**。  
4. **Excel 保存 Permission denied**：关闭正在打开的目标 xlsx 再运行。  
5. **排序**：赛狐导入脚本最终按 **`*SKU` 纯字符串序**（非自然数序）；`200` 可能排在 `60` 前。

---

## 8. 总结表

| 脚本 | 主要输入 | 主要输出 |
|------|----------|----------|
| `erpnext_to_saihu.py` | 纵向物料导出、赛狐模板、物料属性 | `赛狐导入_*_转换结果.xlsx`（最多 3 个） |
| `tongtu_sku_explode.py` | `通途普通商品.xlsx` | `通途SKU别名炸开.xlsx`（3 列） |
| `erp_tongtu_bridge.py` | 通途SKU ERP 导出、炸开表、物料属性 | `赛狐配对导入_*.xlsx`（3 个）+ 可选检验/全量 |

---

## 9. 维护建议

- 若 ERP 或赛狐 **列名变更**，需同步改脚本中的常量字符串。  
- 若将三脚本改为包结构，请保留 **可导入的** `load_spu_status_maps` / `_default_spu_from_sku` 或更新 `erp_tongtu_bridge` 的 import。  
- 在新工作区打开 **`D:\Work\赛狐\Cursor`** 后，用 **绝对路径** 指向本目录即可运行；或将本目录加入 `PYTHONPATH`。

---

*文档生成目的：承接聊天中约定的业务规则与实现细节；若与代码不一致，以仓库内 `.py` 为准。*
