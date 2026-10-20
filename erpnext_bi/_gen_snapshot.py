# -*- coding: utf-8 -*-
"""生成离线静态快照 HTML: 把 /api/orders 的数据内联进单文件, 用户双击即可在任意浏览器打开。"""
import json
import urllib.request

from erpnext_bi.app import DASHBOARD_HTML

API = "http://127.0.0.1:8099/api/orders"

# 1) 从运行中的服务取最新聚合数据(服务在本机可达)
req = urllib.request.Request(API, headers={"Accept": "application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    payload = json.loads(r.read().decode("utf-8"))

# 2) 注入数据, 去掉 fetch 逻辑(改为直接用内联 DATA)
data_json = json.dumps(payload, ensure_ascii=False)
html = DASHBOARD_HTML
html = html.replace("let DATA = null;", "const DATA = " + data_json + ";", 1)
html = html.replace("load(false);", "render();", 1)
# 刷新按钮在静态快照里无意义, 改为标注
snap_label = '<span class="muted">（📄 离线快照 · 数据截至 ' + payload.get("updated_at", "—") + "）</span>"
html = html.replace('<button onclick="load(true)">↻ 强制刷新</button>', snap_label, 1)
# 顶部说明补充“离线快照”
html = html.replace(
    "数据实时取自 EN 生产环境",
    "离线快照(数据已内联, 无需联网) · 实时版见服务器 127.0.0.1:8099",
    1,
)

out = "erpnext_bi/dashboard_snapshot.html"
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

print("written ->", out)
print("updated_at:", payload.get("updated_at"), "| orders:", payload.get("order_count"),
      "| bytes:", len(html))
