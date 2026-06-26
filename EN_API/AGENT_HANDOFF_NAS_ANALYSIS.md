# NAS 路径缺失统计 — 交接说明

> **生成时间**: 2026-06-25
> **工具脚本**: `analyze_nas_paths.py`
> **相关文档**: [AGENT_HANDOFF.md](AGENT_HANDOFF.md)（通用交接）
> **输出目录**: `out/`

---

## 1. 业务背景

EN 系统（ERPNext）的物料组（Item Group）有一个自定义字段 `custom_nas_path_link`，用于存储 NAS 上对应产品文件夹的路径链接。该字段为富文本（HTML）格式，包含四类 NAS 路径：

| 类别 | 用途 |
|:---|:---|
| **图片** | 产品图片目录 |
| **设计稿** | 产品设计稿件目录 |
| **视频** | 产品视频目录 |
| **调研报告** | 产品调研报告目录 |

每类路径在物料组中的格式如下（ERPNext 富文本编辑器存储为 HTML）：

```html
<p><strong>图片:</strong> <a href="..." target="_blank">/产品信息/KS0403_半躺式升级人类狗床/图片</a></p>
<p><strong>设计稿:</strong> <a href="..." target="_blank">/产品信息/KS0403_半躺式升级人类狗床/设计稿</a></p>
```

**需求**：统计"产品"根节点下所有子孙物料组中，图片 / 设计稿 / 视频 / 调研报告四类路径分别缺失哪些物料组，以便补充 NAS 目录结构。

---

## 2. 分析流程

```
ERPNext 全量物料组拉取 (fields 含 custom_nas_path_link)
  → build_index 建立 name→记录 字典
  → get_subtree("产品", idx) 递归获取产品子树 (不含根自身)
  → 对每个物料组:
      1. 提取 custom_nas_path_link 字段 (HTML)
      2. 正则解析 <strong>标签:</strong> <a>路径</a>  → {类别: 路径} 字典
      3. 标记四类路径的存在状态
  → 按类别统计缺失物料组
  → 输出 Excel 报告 (汇总 + 各类缺失明细 + 完全无配置清单)
```

### 关键细节

- 字段 `custom_nas_path_link` 以 **HTML 格式** 存储在 ERPNext 中（富文本编辑器），需要使用正则提取标签和路径
- 必须显式指定 fields 列表包含 `custom_nas_path_link`，使用 `fields=None` 会导致只返回 `name` 字段
- 递归遍历"产品"下所有层级的子孙节点，包括组节点（`is_group=1`）和叶子节点（`is_group=0`）

---

## 3. 关键函数

| 函数 | 作用 |
|------|------|
| `ErpnextClient(base_url, api_key, api_secret)` | API 客户端，管理 session + 认证 |
| `ErpnextClient.fetch_all(fields)` | 全量拉取 Item Group，支持指定字段列表 |
| `build_index(data)` | 按 `name` 建立字典索引 |
| `get_subtree(name, idx)` | 获取指定节点及其所有子孙节点 |
| `get_descendants(name, idx)` | 递归获取所有子孙节点（不含自身） |
| `parse_nas_paths(nas_html)` | 解析 custom_nas_path_link HTML → {类别: 路径} |
| `analyze(client, root_name)` | 主分析流程，返回每条记录的路径状态明细 |
| `generate_report(results, ...)` | 生成 Excel 报告（汇总 + 各类缺失 Sheet） |

---

## 4. API 端点与关键参数

| 端点 | 方法 | 关键参数 |
|------|------|---------|
| `/api/resource/Item Group` | GET | `fields`=`json.dumps(["name","item_group_name","parent_item_group","is_group","custom_model_id","custom_nas_path_link"])`, `limit_page_length=0` |

注意：要用 `limit_page_length=0`（返回全部），而不是 `limit=0`。`limit=0` 会导致只返回 `name` 字段。

---

## 5. 命令行

```bash
cd D:\Claude Demo\fzh-data\EN_API

# 测试环境（默认）
python analyze_nas_paths.py

# 生产环境
python analyze_nas_paths.py --env prod

# 指定其他根节点
python analyze_nas_paths.py --root "宠物类"

# dry-run 预览（不写文件）
python analyze_nas_paths.py --dry-run
```

### 输出文件

`out/NAS路径缺失统计_{timestamp}.xlsx`，包含 Sheet：

| Sheet | 内容 |
|-------|------|
| 汇总 | 整体统计数据，各类别缺失数及比例 |
| 缺失_图片 | 缺少图片路径的物料组明细 |
| 缺失_设计稿 | 缺少设计稿路径的物料组明细 |
| 缺失_视频 | 缺少视频路径的物料组明细 |
| 缺失_调研报告 | 缺少调研报告路径的物料组明细 |
| 完全无NAS路径 | 完全没有配置任何 NAS 路径的物料组 |

---

## 6. 执行结果

### 测试系统 (ensh.vilavi.cn) — 2026-06-25

| 项目 | 数值 |
|:---|---:|
| 物料组总数 | 1,661 |
| "产品"子孙节点 | 430（组53 + 叶子377） |
| 有 NAS 路径配置 | 315 |
| 缺失**图片** | **207 (48.1%)** |
| 缺失**设计稿** | **192 (44.7%)** |
| 缺失**视频** | **397 (92.3%)** |
| 缺失**调研报告** | **182 (42.3%)** |

### 生产系统 (erpnext.vilavi.cn) — 2026-06-25

| 项目 | 数值 |
|:---|---:|
| 物料组总数 | 3,674 |
| "产品"子孙节点 | 459（组54 + 叶子405） |
| 有 NAS 路径配置 | 320 |
| 缺失**图片** | **239 (52.1%)** |
| 缺失**设计稿** | **206 (44.9%)** |
| 缺失**视频** | **424 (92.4%)** |
| 缺失**调研报告** | **196 (42.7%)** |

> **关键发现**：视频路径在测试和生产两个环境中的缺失率均超过 **92%**，远高于其他三类，表明视频 NAS 目录普遍未建立或未配置。
