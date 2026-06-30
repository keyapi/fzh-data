# AGENT_HANDOFF: 独立站 (daneey.com) 产品链接写入 EN 系统

> **最后更新**: 2026-06-30
> **状态**: ✅ 已部署到 EN 系统，定时任务运行中
> **目录**: D:\Claude Demo\fzh-data\EN_API\

---

## 一、项目概述

### 目标
将 Shopify 独立站 **daneey.com** 的产品详情页 URL 写入 EN 系统（ERPNext）对应的物料组（Item Group）的 `daneey_product_details` 字段。

### 数据流
```
daneey.com 产品数据 (CSV / API)
    → 提取所有 SKU
    → 调用 vilavi_pim API 批量查询 SKU → 物料组
    → 按物料组合并产品链接
    → 全量覆盖写入 Item Group.daneey_product_details
```

### 环境

| 环境 | URL | 凭证变量 |
|------|-----|---------|
| **生产系统(prod)** | https://erpnext.vilavi.cn | `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET` |
| **测试系统(test)** | https://ensh.vilavi.cn | `TEST_ERP_API_KEY` / `TEST_ERP_API_SECRET` |
| **独立站** | https://daneey.com | (Shopify 公开 API，无需凭证) |

---

## 二、核心 API（由 Agent 部署在 EN 系统）

### 查询 SKU → 物料组映射

| 项目 | 内容 |
|:-----|:------|
| **端点** | `POST /api/method/vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping` |
| **位置** | `vilavi_pim/api/pim_api.py`（需 `@frappe.whitelist()` 装饰） |
| **功能** | 批量查询 SKU 对应的 Item 和物料组信息 |
| **数据链路** | `tabItem Customer Detail.ref_code` → `tabItem.name` → `tabItem.item_group` |

**请求体**：
```json
{"skus": ["TT0031038K0062927", "TT0312685K0064373"]}
```

**响应体**：
```json
{
  "total": 2,
  "results": [
    {
      "sku": "TT0031038K0062927",
      "item_code": "KS0156-NYBDSFH-52x52x5-BLACK",
      "item_group": "沙发支撑垫",
      "item_name": "沙发支撑垫-...",
      "item_group_url": "/app/item-group/沙发支撑垫"
    }
  ],
  "not_found": ["TT0312685K0064373"],
  "message": "Found 1 mappings, 1 SKUs not found"
}
```

### 更新物料组字段

| 项目 | 内容 |
|:-----|:------|
| **端点** | `PUT /api/resource/Item Group/{name}` |
| **字段** | `daneey_product_details` |

---

## 三、执行结果

### 测试系统写入结果

| 指标 | 数值 |
|:-----|:----:|
| SKU 查询数 | 1,401 |
| SKU 匹配成功 | 1,006 (71.8%) |
| 产品匹配成功 | 408/580 (70.3%) |
| 覆盖物料组 | 247 个 |
| 成功写入 | 247 ✅ |
| 写入失败 | 2（测试系统缺物料组） |

### API 模式（实时拉取独立站）

| 指标 | 数值 |
|:-----|:----:|
| 拉取产品数 | 284 |
| 匹配率 | 82% |
| 覆盖物料组 | 143 个 |

---

## 四、文件清单

```
D:\Claude Demo\fzh-data\EN_API\
├── shopify_to_en.py              # 单文件脚本（自包含，无其他依赖）
├── AGENT_HANDOFF_独立站产品链接.md  # 当前文档
├── DEPLOY.md                      # 部署说明
└── 数据源/
    └── products_export_1.csv      # 初始 CSV 导入用
```

### shopify_to_en.py 内部模块

| 模块 | 说明 |
|:-----|:------|
| `ErpnextClient` | ERPNext API 客户端（含 417 处理、SKU 查询缓存） |
| `from_csv()` | 从 CSV 读取产品数据 |
| `from_api()` | 从 daneey.com/products.json 拉取实时数据 |
| `EnMatcher` | 匹配器：调用 vilavi_pim API 批量匹配 SKU |
| `EnWriter` | 写入器：全量覆盖（匹配的写入，不匹配的清空） |
| `generate_match_report()` | 生成 Excel 报告 |

### 两种数据源输出格式一致
```python
{
    "handle": "boho-tufted-fabric-upholstered-corner-headboard",
    "title": "BOHO Tufted Fabric Corner Headboard",
    "url": "https://daneey.com/products/...",
    "skus": ["TT0312685K0064373"],
    "match": {"item_group": "沙发支撑垫"},
    "match_status": "ok"  # or "no_match"
}
```

---

## 五、使用方式

```bash
# CSV 模式（初始导入）
python shopify_to_en.py --mode csv --dry-run --env test    # 预览
python shopify_to_en.py --mode csv --env test               # 写测试
python shopify_to_en.py --mode csv --env prod               # 写生产

# API 模式（定时任务用，实时拉取独立站）
python shopify_to_en.py --mode api --dry-run --env prod     # 预览
python shopify_to_en.py --mode api --env prod               # 执行
```

输出：`out/独立站链接匹配结果_{预览|执行}_{时间戳}.xlsx`

---

## 六、已知问题

1. **Shopify 变体后缀导致匹配失败**：CSV 中 SKU 可能带后缀（如 `TT0312640K0064285-1`、`TT0031131K0063816-C-peach`、`TT0312588K0064179-Foam`），但 EN 系统 `customer_items.ref_code` 只存基础 SKU（`TT0312640K0064285`、`TT0031131K0063816`、`TT0312588K0064179`）。已用正则 `TT\d+K\d+` 提取基础码一同查询，并自动建立后缀→基础码的映射关系。
2. **约 28% 产品真正未匹配**：部分 SKU 连基础码也找不到，说明这些产品尚未录入 EN 系统
3. **物料组名含特殊字符**（如 `#`）可能写入失败
4. **全量覆盖**：每次执行会清空本次未匹配到的历史数据（独立站已下架的产品）
