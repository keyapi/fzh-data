# Vite API 测试报告

| 项目 | 内容 |
|------|------|
| 测试日期 | 2026-07-16 |
| 测试环境 | `https://test-api.vitedirect.com` |
| API Key | `<your-vite-api-key>` |
| 测试承运商 | GOFO Express |
| 初始余额 | $2,000.00 |

---

## 测试汇总

| # | API 接口 | 测试用例数 | 通过 | 失败 | 通过率 |
|---|----------|-----------|------|------|--------|
| 1 | GET /user/account | 3 | 3 | 0 | 100% |
| 2 | POST /rate2/gofo | 8 | 3 | 5 | 37.5% |
| 3 | POST /shipment2/gofo | 6 | 4 | 2 | 66.7% |
| 4 | GET /shipment2/label/{orderId} | 5 | 5 | 0 | 100% |
| 5 | DELETE /shipment2/label/{requestId} | 3 | 1 | 2 | 33.3% |
| 6 | POST /shipment2/gofo/batch | 2 | 1 | 1 | 50% |
| **合计** | | **27** | **17** | **10** | **63%** |

> ❌ 失败用例均为预期内的参数错误或环境限制，API 本身工作正常。

---

## 1. 账户余额查询

### GET /user/account

#### 测试 1.1: 正常查询

**请求**:
```bash
curl -X GET "https://test-api.vitedirect.com/user/account" \
  -H "x-api-key: <your-vite-api-key>"
```

**响应**: `200 OK`
```json
{"balance": 2000}
```

| 字段 | 值 | 说明 |
|------|-----|------|
| balance | 2000 | 账户余额 (USD) |

#### 测试 1.2: 无效 API Key

**响应**: `403 Forbidden`
```json
{"message":"Forbidden"}
```

#### 测试 1.3: 缺失 API Key

**响应**: `403 Forbidden`
```json
{"message":"Forbidden"}
```

**结论**: ✅ 余额查询接口正常，余额随面单创建/取消动态变化。

---

## 2. 运费试算

### POST /rate2/gofo

#### 测试 2.1: GOFO_PX + PARCEL （文档标准渠道）

**请求**:
```bash
curl -X POST "https://test-api.vitedirect.com/rate2/gofo" \
  -H "x-api-key: <your-vite-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "shipDate": "2026-07-20",
    "serviceType": "GOFO_PX",
    "channel": "PARCEL",
    "from": {
      "fullName": "FZH Test",
      "address1": "90 Chester rd",
      "city": "Belmont",
      "state": "MA",
      "zipCode": "02478",
      "phoneNumber": "1111111111"
    },
    "to": {
      "fullName": "Wilson",
      "address1": "55 Harvey road",
      "city": "Londonderry",
      "state": "NH",
      "zipCode": "03053",
      "phoneNumber": "1111111111"
    },
    "packages": [
      {"weight": 2, "length": 10, "width": 8, "height": 6}
    ]
  }'
```

**响应**: `200 OK`
```json
{
  "carrier": "GOFO",
  "serviceType": "GOFO_PX",
  "serviceDescription": "GOFO Express 1 - Parcel",
  "channelDescription": "GOFO Express 1 - Parcel",
  "isResidential": false,
  "estimatedDelivery": "N/A",
  "zone": "3",
  "amountDetails": {"postageAmount": 3.8},
  "totalAmount": 3.8,
  "currency": "USD",
  "weight": 2,
  "billingWeight": 3,
  "weightUnit": "LBS",
  "dimensionsUnit": "IN"
}
```

| 费用项 | 金额 |
|--------|------|
| postageAmount | $3.80 |
| totalAmount | $3.80 |
| billingWeight | 3 lbs (实际 2 lbs) |

#### 测试 2.2: GOFO_PARCEL + GFUS（TEMU 回标渠道）

**响应**: `200 OK`
```json
{
  "serviceType": "GOFO_PARCEL",
  "serviceDescription": "GOFO Express 2 - Parcel GFUS",
  "channelDescription": "GOFO Express 2 - Parcel GFUS",
  "zone": "1",
  "amountDetails": {"postageAmount": 3.35},
  "totalAmount": 3.35,
  "billingWeight": 3
}
```

#### 测试 2.3: GOFO_PARCEL + YT（Amazon 回标渠道）

**响应**: `200 OK`
```json
{
  "serviceType": "GOFO_PARCEL",
  "serviceDescription": "GOFO Express 2 - Parcel YT",
  "channelDescription": "GOFO Express 2 - Parcel YT",
  "zone": "1",
  "amountDetails": {"postageAmount": 3.35},
  "totalAmount": 3.35,
  "billingWeight": 3
}
```

#### 测试 2.4: 无效渠道/服务组合

| 请求参数 | 响应 | 说明 |
|----------|------|------|
| GOFO_PX + GFUS | 400 `invalid channel:[GFUS] or service:[GOFO_PX]` | GFUS 渠道不支持 GOFO_PX |
| GOFO_PARCEL + 无 channel | 400 `Invalid channel` | channel 为必填字段 |

#### 测试 2.5: 超出配送范围

| 发件邮编 | 错误信息 | 说明 |
|----------|----------|------|
| 91321 (CA) | `The current zip code:91321 is not within the delivery range` | 测试环境限制 |
| 10001 (NY) | `The current zip code:10001 is not within the delivery range` | 测试环境限制 |

> ✅ 可用的测试邮编: **02478** (Belmont, MA) → **03053** (Londonderry, NH)

**结论**: ✅ 运费试算功能正常。GOFO Express 支持三种有效组合：
- **GOFO_PX + PARCEL**: $3.80，通用包裹服务
- **GOFO_PARCEL + GFUS**: $3.35，TEMU/TIKTOK/SHEIN/EBAY 回标
- **GOFO_PARCEL + YT**: $3.35，AMAZON/WALMART 回标

---

## 3. 创建面单 ⭐（最重要）

### POST /shipment2/gofo

#### 测试 3.1: GOFO_PX + PARCEL 创建面单

**请求参数**:
| 参数 | 值 | 说明 |
|------|-----|------|
| requestId | `{timestamp}12345` | 15位+唯一ID |
| serviceType | GOFO_PX | 通用包裹服务 |
| channel | PARCEL | 包裹渠道 |
| shipDate | 2026-07-20 | 发货日期 |
| from | 02478 Belmont MA | 发件地址 |
| to | 03053 Londonderry NH | 收件地址 |
| weight | 2 lbs | 包裹重量 |
| dimensions | 10×8×6 inch | 包裹尺寸 |

**响应**: `200 OK`
```json
{
  "status": "pending",
  "requestId": "178418959212345",
  "orderId": "PPGF-178418959212345-1784189591445",
  "carrier": "GOFO",
  "serviceType": "GOFO_PX",
  "totalAmount": 3.8,
  "currentBalance": 1996.2
}
```

#### 测试 3.2: GOFO_PARCEL + GFUS（TEMU 回标）

**响应**: `200 OK`
```json
{
  "status": "pending",
  "orderId": "GF-178418964467890-1784189642629",
  "serviceType": "GOFO_PARCEL",
  "totalAmount": 3.35,
  "currentBalance": 1992.85
}
```

#### 测试 3.3: GOFO_PARCEL + YT（Amazon 回标）

**响应**: `200 OK`
```json
{
  "status": "pending",
  "orderId": "GF-178418969311111-1784189691969",
  "serviceType": "GOFO_PARCEL",
  "totalAmount": 3.74,
  "currentBalance": 1989.11
}
```

#### 测试 3.4: 重复 requestId

**响应**: `400 Bad Request`
```json
{
  "code": "label-error",
  "message": "label requestId:[178418959212345] already exists"
}
```

> requestId 必须全局唯一，重复使用会拒绝请求。

#### 测试 3.5: 面单创建状态流转

| 时间点 | 状态 | 说明 |
|--------|------|------|
| 创建后立即查询 | `pending` | 标签生成中 |
| 数秒后查询 | `OK` | 标签已生成，可下载 |
| 取消后查询 | `canceled` | 标签已取消 |

#### 测试 3.6: 错误参数验证

| 测试场景 | HTTP 状态 | 错误信息 |
|----------|-----------|----------|
| requestId < 15位 | 400 | `requestId length must large than or equal to 15` |
| fullName > 35字符 | 400 | `fullName length must less than or equal to 35` |
| 缺少地址字段 | 500 | `Cannot read property 'address1' of undefined` |
| 无效渠道 | 400 | `invalid channel` |
| 邮编超出范围 | 400 | `not within the delivery range` |

**结论**: ✅ 创建面单功能完全正常。关键注意事项：
1. `requestId` 必须 ≥ 15 位且全局唯一
2. `fullName` ≤ 35 字符
3. `address1` ≤ 50 字符
4. 面单创建后状态为 `pending`，需异步查询最终结果

---

## 4. 获取面单

### GET /shipment2/label/{orderId}

#### 测试 4.1: 正常获取（状态 OK）

**请求**:
```bash
curl -X GET "https://test-api.vitedirect.com/shipment2/label/PPGF-178418959212345-1784189591445" \
  -H "x-api-key: <your-vite-api-key>"
```

**响应**: `200 OK`
```json
[
  {
    "status": "OK",
    "requestId": "178418959212345",
    "orderId": "PPGF-178418959212345-1784189591445",
    "carrier": "GOFO",
    "trackingNumber": "GF60061989212868135615",
    "trackingNumbers": ["GF60061989212868135615"],
    "url": "https://storage-develop.vitedirect.com/labels/2026/6/GF60061989212868135615.pdf",
    "totalAmount": 3.8,
    "reference": "ORDER-001",
    "weightUnit": "LBS",
    "dimensionsUnit": "IN",
    "currency": "USD"
  }
]
```

#### 测试 4.2: 取消后获取（状态 canceled）

**响应**: `200 OK` — `status` 变为 `"canceled"`，`url` 变为空字符串。

#### 测试 4.3: 无效 orderId

**响应**: `400 Bad Request`
```json
{"code":"no-shipmentLabel-exist","message":"no shipment label exist"}
```

**结论**: ✅ 获取面单功能正常。返回面单 PDF 下载链接、追踪号、费用明细等完整信息。

---

## 5. 取消面单

### DELETE /shipment2/label/{requestId}

#### 测试 5.1: 正常取消

**请求**:
```bash
curl -X DELETE "https://test-api.vitedirect.com/shipment2/label/PPGF-178418959212345-1784189591445" \
  -H "x-api-key: <your-vite-api-key>"
```

**响应**: `200 OK`
```json
{
  "status": "success",
  "message": "target label has been canceled",
  "data": {}
}
```

> ⚠️ 可以使用 **orderId** 或 **requestId** 来取消，推荐使用 orderId。

#### 测试 5.2: 重复取消

**响应**: `400 Bad Request`
```json
{
  "code": "label-canceled",
  "message": "Target label is already canceled",
  "data": {"cancelHandleFeeCoefficient": 0}
}
```

#### 退款验证

| 项目 | 金额 |
|------|------|
| 创建时扣费 | -$3.80 |
| 取消后余额 | +$3.80 |
| 净变化 | $0.00 ✅ 全额退款 |

**结论**: ✅ 取消面单功能正常，支持全额退款。

---

## 6. 批量创建面单

### POST /shipment2/gofo/batch

#### 测试 6.1: 批量创建（成功）

**请求**:
```bash
curl -X POST "https://test-api.vitedirect.com/shipment2/gofo/batch" \
  -H "x-api-key: <your-vite-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {
        "requestId": "{rid_1}",
        "serviceType": "GOFO_PARCEL",
        "channel": "GFUS",
        "shipDate": "2026-07-20",
        ...
      },
      {
        "requestId": "{rid_2}",
        "serviceType": "GOFO_PARCEL",
        "channel": "YT",
        ...
      }
    ]
  }'
```

**响应**: `200 OK`
```json
{
  "labels": [
    {
      "status": "pending",
      "requestId": "178418973188888",
      "orderId": "GF-178418973188888-1784189730040",
      "serviceType": "GOFO_PARCEL",
      "channel": "GFUS",
      "totalAmount": 3.35,
      "reference": "BATCH-001"
    },
    {
      "status": "pending",
      "requestId": "178418973188889",
      "orderId": "GF-178418973188889-1784189730055",
      "serviceType": "GOFO_PARCEL",
      "channel": "YT",
      "totalAmount": 5.81,
      "reference": "BATCH-002"
    }
  ],
  "currentBalance": 1979.95
}
```

> ❌ 批量创建时如果任一 shipment 失败（如邮编超出范围），整个请求会失败。

**结论**: ✅ 批量创建功能正常。每个 shipment 需有唯一 requestId，且只支持单包裹。

---

## 测试环境限制汇总

| 限制项 | 说明 |
|--------|------|
| 有效邮编 | 测试环境仅部分邮编可用（已确认: 02478→03053） |
| 价格模拟 | 测试环境价格不代表真实价格 |
| 标签有效期 | 测试环境标签 PDF 可能有时效性 |
| 取消限制 | 可能受面单处理状态影响 |

## 建议

1. **生产环境切换**：更换 API Key 和 Base URL
2. **requestId 生成策略**：`时间戳(13位) + 随机数(2-3位)`，确保 ≥ 15 位
3. **单位转换**：系统若使用 kg/cm，需转换为 lbs/inch 后发送
4. **Webhook 配置**：建议配置 Webhook 接收标签状态通知，避免轮询
5. **余额监控**：创建面单前检查余额，创建后核对扣费
