# Phase 5: ERPNext Item API 对接 — Design Spec

> 日期: 2026-06-10 | 状态: 待审阅 | 范围: 替换 mock 产品搜索

## 1. 背景

当前 `/api/products/search` 返回 5 个硬编码 mock 数据。ERPNext 测试系统已有 5695 个 Item，需要通过 REST API 做实搜。

## 2. 设计

### 2.1 新增配置 (dam-prototype/.env)

```
ERP_URL=https://ensh.vilavi.cn
ERP_API_KEY=<从 .env 文件获取>
ERP_API_SECRET=<从 .env 文件获取>
```

### 2.2 ErpnextClient（轻量版，放在 main.py 内）

不需要单独文件。在 main.py 开头加一个 ~30 行的类：

```python
class ErpnextClient:
    def __init__(self, base_url, api_key, api_secret):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
    
    def search_items(self, query: str, limit=20):
        import json
        import requests
        url = f"{self.base_url}/api/resource/Item"
        params = {
            "fields": json.dumps(["item_code", "item_name", "item_group", "image"]),
            "filters": json.dumps([
                ["item_code", "like", f"%{query}%"],
                "OR",
                ["item_name", "like", f"%{query}%"],
            ]),
            "limit_page_length": str(limit),
        }
        headers = {"Authorization": f"token {self.api_key}:{self.api_secret}"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return [{"sku": r["item_code"], "name": r["item_name"]} for r in resp.json().get("data", [])]
```

### 2.3 替换 mock endpoint

```python
erp_client = ErpnextClient(ERP_URL, ERP_API_KEY, ERP_API_SECRET)

@app.get("/api/products/search")
def search_products(q: str = Query("", min_length=1)):
    try:
        return erp_client.search_items(q)
    except Exception:
        return []  # graceful degradation
```

## 3. 范围

- [x] 替换 `/api/products/search` mock
- [ ] 以后: Asset → ERPNext Item 4属性自动匹配
- [ ] 以后: `/api/products/{sku}` 详情
