# PIM 图片缺失统计 — 交接说明

> **生成时间**: 2026-06-29
> **工具脚本**: `analyze_pim_images.py`
> **相关文档**: [AGENT_HANDOFF.md](AGENT_HANDOFF.md)（通用交接）· [AGENT_HANDOFF_NAS_ANALYSIS.md](AGENT_HANDOFF_NAS_ANALYSIS.md)（NAS 路径统计）
> **输出目录**: `out/`

---

## 1. 业务背景

EN 系统（ERPNext）的物料组（Item Group）有一个自定义子表 `custom_pim_images`，用于存储 PIM（Product Information Management）图片。该子表包含以下字段：

| 字段 | 说明 |
|:---|:---|
| `image_file` / `file_url` | 图片文件路径 |
| `purpose` | 用途分类（如 "Main"） |
| `is_primary` | 是否主图（0/1） |
| `sort_order` | 排序序号 |

**需求**：统计"产品"根节点下所有子孙物料组中，`custom_pim_images` 子表不存在任何图片记录的物料组。

---

## 2. 分析流程

```
ERPNext 全量物料组拉取 (列表接口 → 建立树结构)
  → get_subtree("产品", idx) 递归获取产品子树 (430 个子孙)
  → 逐条调用 GET /api/resource/Item Group/{name} (含子表数据)
  → 提取 custom_pim_images 字段 → 判断是否为空
  → 统计有图/无图物料组数
  → 输出 Excel 报告
```

**注意**：`custom_pim_images` 是子表（Table 类型），列表接口不返回，必须对每个物料组单独调用单文档 API 获取完整数据。

---

## 3. 关键函数

| 函数 | 作用 |
|------|------|
| `ErpnextClient.fetch_all(fields)` | 全量拉取 Item Group 列表（树结构） |
| `ErpnextClient.get_full(docname)` | 获取单个物料组完整数据（含 `custom_pim_images` 子表） |
| `build_index(data)` | 按 `name` 建立字典索引 |
| `get_subtree(name, idx)` | 获取指定节点及其所有子孙节点 |
| `analyze(client, root_name)` | 主分析流程，逐条查询完整数据 |
| `generate_report(results, ...)` | 生成 Excel 报告 |

---

## 4. API 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/resource/Item Group` | GET | 获取物料组列表（树结构） |
| `/api/resource/Item Group/{name}` | GET | 获取单个物料组完整数据（含子表） |

---

## 5. 命令行

```bash
cd D:\Claude Demo\fzh-data\EN_API

# 测试环境（默认）
python analyze_pim_images.py

# 生产环境
python analyze_pim_images.py --env prod

# 指定其他根节点
python analyze_pim_images.py --root "宠物类"

# dry-run 预览（不写文件）
python analyze_pim_images.py --dry-run
```

### 输出文件

`out/PIM图片缺失统计_{timestamp}.xlsx`，包含 Sheet：

| Sheet | 内容 |
|-------|------|
| 汇总 | 整体统计数据（总数 / 有图 / 无图 / 缺失率） |
| 缺失PIM图片 | 无 PIM 图片的物料组明细 |
| 有PIM图片 | 有 PIM 图片的物料组明细（含图片数和图片列表） |
| 查询失败 | 查询失败的物料组（如有） |

---

## 6. 执行结果

### 测试系统 (ensh.vilavi.cn) — 2026-06-29

| 项目 | 数值 |
|:---|---:|
| 物料组总数 | 1,661 |
| "产品"子孙节点 | 430（组53 + 叶子377） |
| **有 PIM 图片** | **189** |
| **缺失 PIM 图片** | **241 (56.0%)** |
| 其中叶子节点有图 | 179 |
| 其中叶子节点无图 | 198 |

### 生产系统 (erpnext.vilavi.cn) — 2026-06-29

| 项目 | 数值 |
|:---|---:|
| 物料组总数 | 3,674 |
| "产品"子孙节点 | 459（组54 + 叶子405） |
| **有 PIM 图片** | **205** |
| **缺失 PIM 图片** | **254 (55.3%)** |
| 其中叶子节点有图 | 192 |
| 其中叶子节点无图 | 213 |

### 测试 vs 生产对比

| 项目 | 测试系统 | 生产系统 |
|:---|---:|---:|
| "产品"子孙节点 | 430 | 459 |
| 有 PIM 图片 | 189 | 205 |
| 缺失 PIM 图片 | 241 (56.0%) | 254 (55.3%) |
| 叶节点无图 | 198 | 213 |

> 两套系统缺失率接近（约 55-56%），生产系统比测试多 29 个物料组，其中较多 13 个缺图物料组。
