---
name: sellfox-api
description: >
  赛狐 (Sellfox) OpenAPI 访问。支持两种方式：
  (1) 代理 API — 运营/非开发人员首选，钉钉登录自动配 Key，通过 api.vilavi.cn 中转；
  (2) 直接 API — 开发人员在 VPS 白名单 IP 上直连 openapi.sellfox.com。
  提供 419 个 API 端点文档、7 种 SP/SB/SD 广告报告脚本、店铺列表拉取示例。
  当用户提到"赛狐API"、"sellfox api"、"赛狐接口"、"赛狐开放平台"、
  "api.vilavi.cn/sellfox"、"赛狐代理"、"赛狐广告报告"、"赛狐店铺"、
  "sellfox report"、"saihu api"、"赛狐中转"、"赛狐 Key"等时触发。
  不要用于赛狐Excel导入（category/item-cost/item-weight/stock-init/warehouse-restock/multi-attr/other-outbound）。
compatibility: >
  代理 API 不需要本地凭证，只需浏览器访问 https://api.vilavi.cn/sellfox/admin 钉钉登录。
  直接 API 需要 VPS 白名单 IP (82.156.238.248) + SELLFOX_APP_ID/SELLFOX_APP_SECRET 环境变量。
  脚本需要 Python 3.10+ (stdlib only, 无第三方依赖)。
metadata:
  module: sellfox-api-proxy
  proxy_url: https://api.vilavi.cn/sellfox
  proxy_base: https://api.vilavi.cn/sellfox/v1/{account}
  accounts: sellfox-main (赛狐 ERP)
  api_docs: SELLFOX_API/docs/api-reference/
  scripts: SELLFOX_API/fetch_ad_reports.py, SELLFOX_API/fetch_extra_reports.py, SELLFOX_API/fetch_sb_sd_reports.py
  updated: 2026-07-09
---

# 赛狐 API 访问

## §1 快速路由

**先判断用户身份，选对路径：**

| 用户说 | 身份判断 | 走哪条路 |
|--------|---------|---------|
| "帮我调赛狐API" / "拉广告报告" / "查店铺" | 运营/业务人员 | → §2 代理 API |
| "我有 App ID/Secret" / "在 VPS 上跑脚本" | 开发人员 | → §3 直接 API |
| "赛狐某个接口怎么调" | 任意 | → §5 API 文档 |

**规则**：除非用户明确说在 VPS 上运行或有赛狐凭证，否则默认走代理 API。

---

## §2 代理 API（运营/非开发人员）

### 2.1 获取 API Key

用户无需任何凭证，只需钉钉账号：

**Step 1**: 让用户浏览器打开 `https://api.vilavi.cn/sellfox/admin`
**Step 2**: 点击「钉钉登录」→ 钉钉扫码 → 自动创建 API Key（首次登录）
**Step 3**: 在 Key 列表中点击「复制」→ 得到 `sk-xxxx...` 格式的 Key

如果已有 Key 但忘记/丢失：
- 登录后点击「复制」按钮可随时重新获取
- 如果提示"无法复制此 Key"，点「删除」→ 「+ New Key」新建一个

**Agent 注意**：用户是技术小白，不要用 curl 命令教他们获取 Key。让他们打开浏览器链接、扫码、点按钮就行。你只需要让他们把复制到的 `sk-xxx` 发给你。

### 2.2 API 格式

拿到 Key 后，所有赛狐 API 通过代理中转：

```
POST https://api.vilavi.cn/sellfox/v1/{account}/{path}
Header: Authorization: Bearer sk-xxxx...
Header: Content-Type: application/json
Body:   {赛狐 API 原始请求体}
```

- `{account}` 固定为 `sellfox-main`（赛狐 ERP）
- `{path}` 是赛狐原始 API 路径，例如 `api/shop/pageList.json`

**代理自动处理**：OAuth2 Token 获取与刷新、HMAC-SHA256 签名、query 参数注入、Token 过期自动重试。客户端只需 Bearer Key 一个 header。

### 2.3 curl 模板

```bash
# 查店铺列表
curl -X POST https://api.vilavi.cn/sellfox/v1/sellfox-main/api/shop/pageList.json \
  -H "Authorization: Bearer $SAIFU_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pageSize":20,"pageNum":1}'

# 创建广告报告下载任务
curl -X POST https://api.vilavi.cn/sellfox/v1/sellfox-main/api/cpc/download/createTask.json \
  -H "Authorization: Bearer $SAIFU_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "shopIds":["<店铺ID>"],
    "adTypeCode":"sp",
    "reportTypeCode":"adCampaignReport",
    "timeUnit":"daily",
    "reportStartDate":"2026-07-02",
    "reportEndDate":"2026-07-08"
  }'

# 轮询报告任务状态
curl -X POST https://api.vilavi.cn/sellfox/v1/sellfox-main/api/cpc/download/pageList.json \
  -H "Authorization: Bearer $SAIFU_KEY" \
  -H "Content-Type: application/json" \
  -d '{"taskIds":["<任务ID>"],"pageNo":1,"pageSize":50}'

# 其他任意赛狐接口 —— 只需换 path 和 body
curl -X POST https://api.vilavi.cn/sellfox/v1/sellfox-main/<赛狐API路径> \
  -H "Authorization: Bearer $SAIFU_KEY" \
  -H "Content-Type: application/json" \
  -d '<请求体JSON>'
```

### 2.4 可复用的 Python 脚本

**Agent 注意**：下面的脚本已经是完整可用的。用户只需提供 API Key，你在本地帮他们跑。

#### 列出所有店铺（带广告授权状态）

```python
"""List all Sellfox shops with ad authorization status."""
import urllib.request, json, os

KEY = os.getenv("SAIFU_KEY", "sk-xxx")
BASE = "https://api.vilavi.cn/sellfox/v1/sellfox-main"

def api_post(path, body):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# Get all shops in one page
result = api_post("/api/shop/pageList.json", {"pageSize":200,"pageNum":1})
shops = result["data"]["rows"]

print(f"Total: {result['data']['totalSize']} shops")
for s in shops:
    ad = "✓" if s.get("adStatus") == "auth" else "✗"
    print(f"  {s['id']:>8}  {ad}  {s['name']:<40}  {s['region']}  {s['marketplaceId']}")
```

#### 拉取 SP 广告报告（4 种核心报告）

```python
"""Fetch SP ad reports: Campaign, Targeting, SearchTerm, Placement."""
import urllib.request, json, os, time

KEY = os.getenv("SAIFU_KEY", "sk-xxx")
SHOP_ID = "596841"          # 替换为实际店铺 ID
START, END = "2026-07-02", "2026-07-08"
BASE = "https://api.vilavi.cn/sellfox/v1/sellfox-main"

def api_post(path, body):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

REPORTS = [
    ("adCampaignReport",   "Campaign"),
    ("adTargeringReport",  "Targeting"),
    ("adSearchTermReport", "SearchTerm"),
    ("adSpaceReport",      "Placement"),
]

# 1. Create tasks
tasks = {}
for code, label in REPORTS:
    r = api_post("/api/cpc/download/createTask.json", {
        "shopIds":[SHOP_ID],"adTypeCode":"sp","reportTypeCode":code,
        "timeUnit":"daily","reportStartDate":START,"reportEndDate":END})
    tid = r["data"]["id"]
    tasks[tid] = label
    print(f"[OK] {label} task: {tid}")
    time.sleep(2)  # rate limit

# 2. Poll and download
pending = set(tasks.keys())
for _ in range(60):  # max 5 min
    time.sleep(5)
    r = api_post("/api/cpc/download/pageList.json",
        {"taskIds":list(tasks.keys()),"pageNo":1,"pageSize":50})
    for row in r["data"]["rows"]:
        tid = str(row["id"])
        if tid not in pending: continue
        if row["reportState"] == "已生成":
            url = row["downloadUrl"][0]
            urllib.request.urlretrieve(url, f"{tasks[tid]}_{START}_{END}.xlsx")
            print(f"[DONE] {tasks[tid]} → {tasks[tid]}_{START}_{END}.xlsx")
            pending.discard(tid)
        elif row["reportState"] == "失败":
            print(f"[FAIL] {tasks[tid]}")
            pending.discard(tid)
    if not pending: break
    print(f"  Waiting for {len(pending)} tasks...")

if pending:
    print(f"Timeout! Still pending: {[tasks[t] for t in pending]}")
```

#### 构建任意 API 调用的通用模板

```python
"""Generic Sellfox API call via proxy."""
import urllib.request, json, os

KEY = os.getenv("SAIFU_KEY", "sk-xxx")
BASE = "https://api.vilavi.cn/sellfox/v1/sellfox-main"

def call_sellfox(path, body=None):
    """Call any Sellfox API endpoint through the proxy.
    
    Args:
        path: API path, e.g. "/api/shop/pageList.json"
        body: Request body dict, e.g. {"pageSize": 10}
    Returns:
        Parsed JSON response (the 'data' field unwrapped)
    """
    url = f"{BASE}{path}"
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    if result.get("code") != 0:
        raise RuntimeError(f"API error: code={result.get('code')} msg={result.get('msg')}")
    return result["data"]

# Usage examples:
# shops = call_sellfox("/api/shop/pageList.json", {"pageSize": 10})
# orders = call_sellfox("/api/sc/order/pageOrder.json", {"pageNo":1,"pageSize":10})
```

### 2.5 限流说明

- 赛狐上游限制约 1 rps（每秒 1 请求）
- 代理做 per-key + 全局两级限流
- 超限返回 `429` + `Retry-After` header
- **Agent 注意**：循环调用时务必 `time.sleep(2)`，否则连续请求会被限

### 2.6 常见错误

| HTTP 状态 | 含义 | 处理 |
|----------|------|------|
| 401 `Invalid or inactive API key` | Key 无效或已被禁用 | 让用户重新登录获取新 Key |
| 403 `Key not authorized for account` | Key 绑定的 account 不对 | Key 固定绑 `sellfox-main`，无需改动 |
| 429 `Rate limited` | 触发限流 | `sleep(Retry-After 秒数)` 后重试 |
| 502 `Upstream auth failed` | 代理到赛狐的 OAuth2 Token 过期 | 自动重试，仍失败则联系管理员 |

---

## §3 直接 API（开发人员，在 VPS 白名单 IP 上运行）

**条件**：必须在 VPS (82.156.238.248) 或白名单机器上运行。

### 3.1 凭证

需要环境变量：
- `SELLFOX_APP_ID` — 赛狐开放平台 App ID
- `SELLFOX_APP_SECRET` — 赛狐开放平台 App Secret

VPS 上的 `.secrets.env` 已配置，位置：`/opt/new-api/.secrets.env`

### 3.2 OAuth2 认证

```
GET https://openapi.sellfox.com/api/oauth/v2/token.json
  ?client_id={APP_ID}&client_secret={APP_SECRET}&grant_type=client_credentials

Response: {"code":0, "data":{"access_token":"...", "expires_in":7200000}}
```

Token 有效期 2 小时。唯一不受 IP 白名单限制的端点。

### 3.3 HMAC-SHA256 签名

业务请求必须签名的 query 参数（5 个）：
- `access_token` — OAuth2 Token
- `client_id` — App ID
- `nonce` — 随机数
- `timestamp` — 毫秒时间戳
- `sign` — HMAC-SHA256 签名

**签名算法**（已验证，来源 `SELLFOX_API/fetch_ad_reports.py:55-69`）：

```python
import hmac, hashlib, time, random

def compute_sign(access_token, app_id, app_secret, url_path):
    ts = str(int(time.time() * 1000))
    nonce = str(random.randint(1, 99999))
    params = {
        "access_token": access_token,
        "client_id": app_id,
        "method": "post",
        "nonce": nonce,
        "timestamp": ts,
        "url": url_path,
    }
    # 按 key 排序 → k=v&k=v 格式
    sorted_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sig = hmac.new(app_secret.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()
    
    # 发送时只传 5 个参数（method 和 url 仅参与签名，不发送）
    return {
        "access_token": access_token,
        "client_id": app_id,
        "nonce": nonce,
        "timestamp": ts,
        "sign": sig,
    }
```

**注意**：`method` 和 `url` 参与签名计算但**不发送**到 query string。这是已验证的踩坑教训（#6）。

---

## §4 已有脚本

这些脚本在 `SELLFOX_API/` 目录下，是直接 API 方式（需在 VPS 白名单 IP 运行）：

| 脚本 | 报告类型 | 数量 |
|------|---------|------|
| `fetch_ad_reports.py` | SP: Campaign, Targeting, SearchTerm, Placement | 4 种 |
| `fetch_extra_reports.py` | SP: AdGroup, AdProduct, PurchasedItem | 3 种 |
| `fetch_sb_sd_reports.py` | SB 7种 + SD 5种 | 12 种 |

**Agent 注意**：如果用代理 API 方式运行（推荐给运营用户），参考 §2.4 的脚本模板——去掉签名逻辑，只需 Bearer Key。

---

## §5 API 文档

赛狐 419 个 API 端点文档在 `SELLFOX_API/docs/api-reference/`，按模块组织：

| 模块 | 端点数 | 目录 |
|------|--------|------|
| 商品 | 16 | `SELLFOX_API/docs/api-reference/商品/` |
| 销售 | 8 | `SELLFOX_API/docs/api-reference/销售/` |
| 订单 | 9 | `SELLFOX_API/docs/api-reference/订单/` |
| 广告 | 37 | `SELLFOX_API/docs/api-reference/广告/` |
| FBA | 44 | `SELLFOX_API/docs/api-reference/FBA/` |
| 采购 | 25 | `SELLFOX_API/docs/api-reference/采购/` |
| 仓库 | 46 | `SELLFOX_API/docs/api-reference/仓库/` |
| 数据 | 18 | `SELLFOX_API/docs/api-reference/数据/` |
| 财务 | 68 | `SELLFOX_API/docs/api-reference/财务/` |
| 多平台 | 115 | `SELLFOX_API/docs/api-reference/多平台/` |
| 报告中心 | 10 | `SELLFOX_API/docs/api-reference/报告中心/` |
| Feed | 3 | `SELLFOX_API/docs/api-reference/Feed/` |
| 客服 | 1 | `SELLFOX_API/docs/api-reference/客服/` |
| 工具 | 1 | `SELLFOX_API/docs/api-reference/工具/` |
| 设置 | 4 | `SELLFOX_API/docs/api-reference/设置/` |
| 开发指南 | 14 | `SELLFOX_API/docs/api-reference/开发指南/` |

每个 `.md` 文件含 OpenAPI YAML spec（请求参数、返回格式、字段说明）。

**Agent 读取方式**：
1. 确定端点在哪个模块
2. 进入对应目录，找到 `.md` 文件
3. 文件内包含完整请求/响应 schema

**机器可读索引**：`SELLFOX_API/docs/api-reference/llms.txt`（858 行，可 grep）

---

## §6 相关文档

- `sellfox-api-proxy/docs/lessons/2026-07-09-full-architecture-evolution.md` — 17 条经验教训
- `sellfox-api-proxy/AGENT_HANDOFF.md` — 代理网关 Agent 接手文档
- `SELLFOX_API/docs/lessons/2026-06-25-sellfox-integration-lessons.md` — 16 条 API 集成教训
- `SELLFOX_API/docs/api-reference/开发指南/` — 认证、签名、限流、公共参数
