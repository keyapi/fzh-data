# AGENT_HANDOFF: 独立站 (daneey.com) 产品链接写入 EN 系统

> **最后更新**: 2026-06-30
> **状态**: ✅ 已部署到 EN 系统，定时任务运行中
> **开发目录**: D:\Claude Demo\fzh-data\EN_独立站\（已迁移至 EN_API）
> **正式部署**: D:\Claude Demo\fzh-data\EN_API\独立站同步\

---

## 一、项目概述

### 目标
将 Shopify 独立站 **daneey.com** 的产品详情页 URL 写入 EN 系统（ERPNext）对应的物料组（Item Group）的 `daneey_product_details` 字段。

### 数据流
```
daneey.com 产品数据
  ├─ (初始) CSV文件 products_export_1.csv ← 已完成
  └─ (维护) /products.json API ← 后续增量

TT-SKU → vilavi_pim API → Item Group.daneey_product_details
```

### 环境

| 环境 | URL | 凭证变量 |
|------|-----|---------|
| **生产系统(prod)** | https://erpnext.vilavi.cn | `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET` |
| **测试系统(test)** | https://ensh.vilavi.cn | `TEST_ERP_API_KEY` / `TEST_ERP_API_SECRET` |
| **独立站** | https://daneey.com | (Shopify 公开 API，无需凭证) |

### 项目路径
```
D:\Claude Demo\fzh-data\EN_独立站\
├── shopify_to_en.py              # ✅ 主入口 CLI
├── shopify_source.py              # ✅ 数据源解析
├── en_matcher.py                  # ✅ 匹配器
├── en_writer.py                   # ✅ 写入器
├── common/
│   ├── __init__.py                # ✅ 
│   ├── env.py                     # ✅ 环境配置
│   ├── erpnext_client.py          # ✅ API 客户端
│   └── report.py                  # ✅ 报告生成
├── server_script_get_sku_mapping.py  # ✅ API 参考代码
├── AGENT_HANDOFF_独立站产品链接.md    # ✅ ← 当前文档
├── out/                           # ✅ 输出目录（含报告）
└── 数据源/
    └── products_export_1.csv      # ✅ 580产品, 1401SKU
```

---

## 二、CSV 文件结构

### 概况
Shopify 标准产品导出，**5,225 行、106 列**。

| 指标 | 数值 |
|------|------|
| 独立产品数（Handle去重） | **580** |
| SKU总数（变体） | **1,401** |
| TT前缀SKU（通途系统） | **710** |
| 单变体产品 | 310 |
| 多变体产品（有颜色/尺寸选项） | 229 |

### 关键列

| 列名 | 说明 | 示例 |
|------|------|------|
| **Handle** | URL Slug → 产品链接 | `boho-tufted-fabric-upholstered-corner-headboard` |
| **Variant SKU** | **通途SKU（TT开头）** | `TT0312685K0064373` |
| Title | 产品标题 | BOHO Tufted Fabric Corner Headboard |
| Option1 Name/Value | 变体选项（颜色/尺寸） | Color: Blue |
| Image Src | 图片链接 | https://cdn.shopify.com/... |

### CSV 行结构
- **有 SKU 的行** = 产品变体，含完整信息
- **SKU 空白的行** = 额外图片行
- 处理时按 **Handle 去重**聚合

---

## 三、匹配路径（核心！）

### 数据链路
```
CSV 中的 TT-SKU（如 TT0031038K0062927）
    ↓
调用 vilavi_pim API（POST 批量查询）
    API内部: frappe.db.sql 直查 tabItem Customer Detail
    ↓
返回: {sku, item_code, item_group, item_name}
    ↓
按 item_group 分组 → 合并写入
    ↓
PUT /api/resource/Item Group/{name}
    data: {"daneey_product_details": "<div>产品链接列表HTML</div>"}
```

### 关键 API
| 端点 | 方法 | 说明 |
|------|:----:|------|
| `vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping` | POST | 批量查询 SKU → 物料组 |
| `PUT /api/resource/Item Group/{name}` | PUT | 更新物料组字段 |

### Server Script 参考代码
见同目录 `server_script_get_sku_mapping.py`。该 API 在 `vilavi_pim` app 中部署，**不是** Server Script。

---

## 四、执行结果

### 测试系统写入结果（2026-06-30）

| 指标 | 数值 |
|:-----|:----:|
| SKU 查询数 | 1,401 |
| SKU 匹配成功 | **1,006** (71.8%) |
| 产品匹配成功 | **408/580** (70.3%) |
| 覆盖物料组 | **247 个** |
| 成功写入 | **247** ✅ |
| 写入失败 | 2（测试系统缺该物料组） |

### 失败原因
2 个失败是因为物料组在测试系统不存在（生产系统有）：
- `侧睡U形身体枕`
- `重量模板#假日休闲躺椅`（名称含 #）

---

## 五、使用方式

### CLI 参数

```bash
# 预览匹配结果
python shopify_to_en.py --mode csv --dry-run --env test

# 写入测试系统
python shopify_to_en.py --mode csv --env test

# 写入生产系统（务必先 dry-run 预览）
python shopify_to_en.py --mode csv --dry-run --env prod
python shopify_to_en.py --mode csv --env prod

# API 增量模式（后续）
python shopify_to_en.py --mode api --dry-run --env prod
```

### 输出文件
- `out/独立站链接匹配结果_预览_{ts}.xlsx` — dry-run 报告
- `out/独立站链接匹配结果_执行_{ts}.xlsx` — 执行报告

---

## 六、已知问题

1. **172 个产品未匹配**（占 29.7%）：SKU 在生产系统 customer_items 中找不到对应记录
   - 可能原因：部分产品 SKU 尚未录入 EN 系统，或使用了不同的编码体系
2. **API 仅部署在测试系统**：目前匹配阶段使用生产系统 API（已部署），匹配数据齐全
3. **特殊字符物料组名**：如含 `#` 的物料组名可能导致写入失败

---

## 七、后续计划

| 优先级 | 事项 |
|:------:|------|
| 🔴 | 写入生产系统 |
| 🟡 | 分析 172 个未匹配产品的原因 |
| 🟢 | 搭建 API 增量模式（替代 CSV） |
| 🟢 | 完善后迁移到 `EN_API/` |

---

## 八、代码架构（为部署到 EN 系统准备）

```
shopify_to_en.py (主入口 CLI)
  │
  ├── shopify_source.py     数据源层
  │   ├── from_csv()        从 CSV 读取
  │   └── from_api()        从 API 拉取
  │
  ├── en_matcher.py         匹配层
  │   └── match_batch()     批量匹配(调用 API)
  │
  ├── en_writer.py          写入层
  │   └── write_all()       更新物料组字段
  │
  └── common/               公共模块
      ├── erpnext_client.py  API 客户端
      ├── env.py             环境配置
      └── report.py          报告生成
```

两种数据源输出相同格式，匹配/写入完全复用：

```python
{
    "handle": "boho-tufted-fabric-upholstered-corner-headboard",
    "title": "BOHO Tufted Fabric Corner Headboard",
    "url": "https://daneey.com/products/boho-tufted-fabric-...",
    "skus": ["TT0312685K0064373"],
    "variants": [{"sku": "...", "price": "305.99", "option": "Default Title"}],
    "images": ["https://cdn.shopify.com/..."],
}
```

---

## 九、下个会话接手指南

### 5 分钟上手
1. **读此文档** — 了解完整上下文
2. **看数据源**: `数据源/products_export_1.csv`
3. **看参考代码**: `shopify_to_en.py`（主入口）
4. **看输出**: `out/` 目录下的 Excel 报告
5. **检查凭证**: `.env` 文件（在 EN_API/ 下）

### 常用操作
```bash
# 写入生产
cd D:\Claude Demo\fzh-data\EN_独立站
python shopify_to_en.py --mode csv --env prod

# API 增量同步
python shopify_to_en.py --mode api --dry-run --env prod
```
