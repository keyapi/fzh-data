# 独立站 (daneey.com) 产品链接同步 — 部署说明

> **将此文档 + 代码目录 交给运维Agent，在 EN 系统/服务器上部署定时任务**

---

## 一、功能说明

每天定时从 **daneey.com** 拉取最新产品数据，通过 TT-SKU 匹配 EN 系统物料组（Item Group），将独立站详情页链接写入 `daneey_product_details` 字段。

**全量覆盖逻辑**：
- 匹配到的物料组 → 写入最新链接
- 之前有但已不匹配的 → 自动清空（产品已下架）

---

## 二、文件清单

将以下整个目录部署到服务器：

```
D:\Claude Demo\fzh-data\EN_独立站\
├── shopify_to_en.py              # 主入口（CLI）
├── shopify_source.py              # 数据源（Shopify API）
├── en_matcher.py                  # SKU → 物料组 匹配器
├── en_writer.py                   # 写入物料组字段
├── common/
│   ├── __init__.py
│   ├── env.py                     # 环境配置
│   ├── erpnext_client.py          # ERPNext API 客户端
│   └── report.py                  # 报告生成
├── sync_daneey.bat                # 定时任务批处理脚本
├── .env                           # API 凭证（需创建）
├── AGENT_HANDOFF_独立站产品链接.md  # 交接文档
└── 数据源/
    └── products_export_1.csv      # （可选，初始导入用）
```

---

## 三、依赖安装

```bash
pip install requests pandas openpyxl
```

---

## 四、环境变量 / .env 文件

在 `EN_独立站/.env` 中配置：

```ini
# EN系统 API 凭证（测试环境）
TEST_ERP_API_KEY=xxxx
TEST_ERP_API_SECRET=xxxx

# EN系统 API 凭证（生产环境）
PROD_ERP_API_KEY=xxxx
PROD_ERP_API_SECRET=xxxx
```

---

## 五、API 依赖

EN 系统需要提供以下 API 端点（已在测试系统验证可运行）：

**接口**：`POST /api/method/vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping`

**功能**：根据 SKU 列表批量查询对应的 Item 和物料组信息

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
      "customer_name": "",
      "item_code": "KS0156-NYBDSFH-52x52x5-BLACK",
      "item_name": "...",
      "item_group": "沙发支撑垫",
      "item_group_url": "/app/item-group/沙发支撑垫"
    }
  ],
  "not_found": ["TT0312685K0064373"],
  "message": "Found 1 mappings, 1 SKUs not found"
}
```

**数据链路**：
```
tabItem Customer Detail.ref_code (SKU)
    → tabItem.name (parent)
    → tabItem.item_group (物料组)
```

**Python 实现（Server Script 参考）**：
```python
import frappe

def get_sku_item_itemgroup_mapping():
    data = frappe.local.form_dict
    skus = data.get("skus") or []
    if not skus or not isinstance(skus, list):
        return {"total": 0, "results": [], "not_found": [], "message": "请提供 skus 参数"}

    placeholders = ", ".join(["%s"] * len(skus))
    rows = frappe.db.sql(f"""
        SELECT DISTINCT icd.ref_code AS sku, icd.customer_name,
               icd.parent AS item_name, i.item_code, i.item_name, i.item_group
        FROM `tabItem Customer Detail` icd
        LEFT JOIN `tabItem` i ON i.name = icd.parent
        WHERE icd.ref_code IN ({placeholders})
    """, skus, as_dict=True)

    found = set()
    results = []
    for row in rows:
        found.add(row["sku"])
        results.append({
            "sku": row["sku"],
            "customer_name": row.get("customer_name", ""),
            "item_code": row.get("item_code", ""),
            "item_name": row.get("item_name", ""),
            "item_group": row.get("item_group", ""),
            "item_group_url": f"/app/item-group/{row.get('item_group', '')}",
        })

    return {
        "total": len(results),
        "results": results,
        "not_found": [s for s in skus if s not in found],
        "message": f"Found {len(results)} mappings, {len(skus)-len(results)} SKUs not found"
    }
```

---

## 六、定时任务配置

### 方式一：Windows 任务计划程序（推荐）

| 设置项 | 值 |
|--------|-----|
| 程序 | `D:\Claude Demo\fzh-data\EN_独立站\sync_daneey.bat` |
| 起始位置 | `D:\Claude Demo\fzh-data\EN_独立站` |
| 触发时间 | **每天 5:40 / 13:40 / 21:40** |
| 运行用户 | 当前登录用户（需有网络权限） |

### 方式二：Linux cron（如果部署在 Linux 服务器）

```bash
crontab -e

# 添加以下三行：
40 5 * * * cd /path/to/EN_独立站 && python shopify_to_en.py --mode api --env prod >> out/cron.log 2>&1
40 13 * * * cd /path/to/EN_独立站 && python shopify_to_en.py --mode api --env prod >> out/cron.log 2>&1
40 21 * * * cd /path/to/EN_独立站 && python shopify_to_en.py --mode api --env prod >> out/cron.log 2>&1
```

### 方式三：ERPNext Scheduled Job Type

在 ERPNext 中创建 **Scheduled Job Type** 文档：

| 字段 | 值 |
|------|-----|
| DocType | Scheduled Job Type |
| Method | `shopify_to_en.run_scheduled` |
| Frequency | 自定义（Cron Expression） |
| Cron Expression | `40 5,13,21 * * *` |

需同时创建 Server Script `shopify_to_en.py` 来调用外部脚本：

```python
import frappe
import subprocess
import os

def run_scheduled():
    """定时同步独立站产品链接"""
    script_dir = "/path/to/EN_独立站"
    log_file = os.path.join(script_dir, "out", "cron_sync.log")
    
    result = subprocess.run(
        ["python", "shopify_to_en.py", "--mode", "api", "--env", "prod"],
        cwd=script_dir,
        capture_output=True, text=True, timeout=600
    )
    
    with open(log_file, "a") as f:
        f.write(f"\n=== {frappe.utils.now()} ===\n")
        f.write(result.stdout)
        if result.stderr:
            f.write(f"STDERR:\n{result.stderr}")
    
    frappe.log_error(f"独立站同步完成", "shopify_sync")
```

---

## 七、首次部署验证步骤

```bash
# 1. 测试 API 调用
cd D:\Claude Demo\fzh-data\EN_独立站
python shopify_to_en.py --mode api --dry-run --env test

# 2. 确认无误后，测试生产 dry-run
python shopify_to_en.py --mode api --dry-run --env prod

# 3. 首次写入生产
python shopify_to_en.py --mode api --env prod

# 4. 验证定时任务
# 手动执行 sync_daneey.bat 确认日志输出正常
```

---

## 八、输出文件

| 文件 | 说明 |
|------|------|
| `out/独立站链接匹配结果_执行_{ts}.xlsx` | 每次执行报告（含匹配详情） |
| `out/logs/sync_yyyymmdd_hhmm.log` | 定时任务日志（自动保留30天） |

---

## 九、更新交接文档

部署完成后，更新 `AGENT_HANDOFF_独立站产品链接.md` 中的部署状态，然后将整个 `EN_独立站` 目录迁移到 `EN_API/` 下统一管理。
