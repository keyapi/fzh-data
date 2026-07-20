# 蜴国际 API（yiglobal-api）— AGENT_HANDOFF

> Agent 交接文档 — 2026-07-17；目录于 2026-07-20 由 `蜴国际-API/` 重命名为 `yiglobal-api/`

## 项目概述

蜴国际打单系统 API 对接。系统地址: http://47.106.72.196/index.html  
模块目录：`yiglobal-api/`（业务中文名仍称「蜴国际」）。

## 凭证信息

真实值只放**仓库根** `.env`（gitignore），见 [`.env.example`](.env.example)：

- `YIGLOBAL_APP_TOKEN` / `YIGLOBAL_APP_KEY` / `YIGLOBAL_API_BASE_URL`
- HTTP 请求体字段名仍是对方契约：`app_token` / `app_key`（不要改成 env 名）
- **客户代码**: M6180（通过 getToken 返回）
- **当前 access_token**: 见 `.token_cache` 或重新获取

## 测试状态

| 接口 | 状态 | 日期 | 备注 |
|------|------|------|------|
| getToken | ✅ 通过 | 2026-07-17 | 正常返回 access_token(JWT)，有效期 24h |
| rates | ✅ 通过 | 2026-07-17 | 成功返回费用估算 |
| ratesv2 | ✅ 通过 | 2026-07-17 | 成功返回多物流产品费用试算 |
| createOrder | ✅ 通过 | 2026-07-17 | 成功创建订单，同步返回跟踪号及面单 PDF |
| getLabel | ✅ 通过 | 2026-07-17 | sync_service_status=1, order_status=2(已预报) |
| cancelOrder | ✅ 通过 | 2026-07-17 | 成功取消订单(code=200) |
| getBalance | ⏳ 未测试 | — | — |
| getOrderInfo | ⏳ 未测试 | — | — |

## API 调用流程

1. `POST /api/svc/getToken` (x-www-form-urlencoded: app_token + app_key) → access_token
2. `POST /api/svc/rates` 或 `POST /api/svc/ratesv2` (JSON + Authorization header) → 费用试算
3. `POST /api/svc/createOrder` → 创建订单 → order_code
4. `POST /api/svc/getLabel` → 获取面单(异步, 建议 30s 轮询)

## 关键约束

1. **发件地址必须备案**：`shipper_address` 中的地址必须先在系统后台备案
2. **token 缓存**: access_token 有效期 24h，失效 code=401
3. **面单异步**: 创建订单后面单不一定立即返回，需轮询 getLabel
4. **账户欠费**: 当前不可测试需扣费的接口

## 发件地址

系统中已备案的发件地址列表：

| 地址编码 | 发货人信息 |
|---------|-----------|
| S0886 | Nickole Ayala, 10451, 417 East 162nd Street, NY, Bronx, 9178817328 |
| S0656 | Qiang Ma, 07936, 389 Route 10 Unit R, NJ, East Hanover, 1234567890 |
| **S0143** | **Dan-zhao, 77099, 10812 Fallstone Rd, Suite 402, TX, Houston, 2816770938** |
| S0625 | A_TX_77091, 77099, 10812 Fallstone Rd, Suite 402, TX, Houston, 0000000000 |
| S0941 | FULFILLMENT CENTER, 07094, 915 Secaucus Rd, NJ, Secaucus, 0000000000 |
| S0795 | Qiang Ma, 07936, 389 STATE ROUTE 10 UNIT R, NJ, EAST HANOVER, 1234567890 |
| S1261 | 77489, 77489, 611 S. Cravens Rd Suite 100, TX, Missori City, 6083349880 |

API 调用时 shipper_address 字段需填写的格式（以 S0143 为例）：
```json
{
  "shipper_name": "Dan-zhao",
  "shipper_postal_code": "77099",
  "shipper_address1": "10812 Fallstone Rd",
  "shipper_address2": "Suite 402",
  "shipper_state_province": "TX",
  "shipper_city": "Houston",
  "shipper_country": "US",
  "shipper_telphone": "2816770938"
}
```

## 物流产品代码

| sm_code | 说明 |
|---------|------|
| FedEx-21-AHS-TX | FedEx 21 AHS（德克萨斯） |
| FedEx-21-AHS-USEA | FedEx 21 AHS（美东） |
| FedEx-Eco-21-TX | FedEx Eco 21（德克萨斯） |
| FedEx-Economy-10-HOU | FedEx Economy 10（休斯顿） |
| FedEx-Economy-10-USEA | FedEx Economy 10（美东） |
| FedEx-Ground-20-OS-TX | FedEx Ground 20 OS（德克萨斯） |
| FedEx-Ground-J-TX | FedEx Ground（德克萨斯） |
| FedEx-Ground-J-USWE | FedEx Ground（美西） |

## 代码示例

```python
import requests

BASE_URL = "http://47.106.72.196"

# 1. 获取 token
# app_token / app_key 为 API 字段名；值来自 env YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY
resp = requests.post(f"{BASE_URL}/api/svc/getToken", data={
    "app_token": "<your-yiglobal-app-token>",
    "app_key": "<your-yiglobal-app-key>"
})
token = resp.json()["result"]["access_token"]

# 2. 费用试算
headers = {"Authorization": token, "Content-Type": "application/json"}
payload = {
    "sm_code": "FedEx-Ground-J-TX",
    "reference_no": "test-001",
    "weight_unit_type": "1",
    "parcel_declared_value": 100,
    "parcel_quantity": 1,
    "box_list": [{"box_actual_weight": 10, "box_length": 12, "box_width": 10, "box_height": 8}],
    "oa_firstname": "Test", "oa_company": "Test Co", "oa_country": "US",
    "oa_state": "CA", "oa_city": "Los Angeles", "oa_postcode": "90001",
    "oa_street_address1": "100 Main St", "oa_street_address2": "",
    "oa_telphone": "1234567890", "oa_doorplate": "", "oa_phone_ext": "",
    "signature_service": "",
    "shipper_address": {
        "shipper_name": "Dan-zhao", "shipper_postal_code": "77099",
        "shipper_address1": "10812 Fallstone Rd", "shipper_address2": "Suite 402",
        "shipper_state_province": "TX", "shipper_city": "Houston",
        "shipper_country": "US", "shipper_telphone": "2816770938"
    }
}
resp = requests.post(f"{BASE_URL}/api/svc/ratesv2", json=payload, headers=headers)
print(resp.json())
```
