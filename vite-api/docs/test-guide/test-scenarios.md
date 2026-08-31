# 测试场景（含实测结果）

> 测试日期: 2026-07-16 | 环境: test-api.vitedirect.com

## 场景 1: 运费查询

验证 GOFO Express 运费查询功能。

```
POST /rate2/gofo
```

### 有效的渠道/服务组合

| 组合 | 运费 | 计费重量 | 说明 |
|------|------|----------|------|
| GOFO_PX + PARCEL | $3.80 | 3 lbs | 通用包裹服务 |
| GOFO_PARCEL + GFUS | $3.35 | 3 lbs | TEMU/TIKTOK/SHEIN/EBAY 回标 |
| GOFO_PARCEL + YT | $3.35 | 3 lbs | AMAZON/WALMART 回标 |

> ❌ GOFO_PX + GFUS: `invalid channel/service` (不支持)
> ❌ 邮编 91321/10001: `not within delivery range` (测试环境限制)

**验证点**: 返回 `totalAmount`、`billingWeight`、`zone`

## 场景 2: 创建回标标签 (GFUS)

为 TEMU 平台创建回标标签。

```
POST /shipment2/gofo
serviceType: GOFO_PARCEL
channel: GFUS
```

**实测结果**: ✅ 通过
- orderId 格式: `GF-{requestId}-{timestamp}`
- 初始状态: `pending`
- 数秒后转为 `OK`，获取到 PDF 面单

**验证点**: 返回 `orderId`，初始状态为 `pending`

## 场景 3: 创建回标标签 (YT)

为 Amazon 平台创建回标标签。

```
POST /shipment2/gofo
serviceType: GOFO_PARCEL
channel: YT
```

**实测结果**: ✅ 通过
- orderId 格式: `GF-{requestId}-{timestamp}`
- trackingNumber: `GFUS010188602773264169`

**验证点**: 返回 `orderId`，初始状态为 `pending`

## 场景 4: 查询标签状态

使用 orderId 查询标签处理结果。

```
GET /shipment2/label/{orderId}
```

**实测结果**: ✅ 通过
- 状态流转: `pending` → `OK` → `canceled`(若取消)
- 成功时返回: `trackingNumber`、`url`(PDF 下载)、`amountDetails`
- 失败时返回: `status: "failed"` + `errorMessage`

**验证点**: `status` 从 `pending` 变为 `OK`

## 场景 5: 批量创建标签

一次请求创建多个标签。

```
POST /shipment2/gofo/batch
```

**实测结果**: ✅ 通过（需注意所有 shipment 的邮编必须在服务范围内）
- 任一 shipment 失败 → 整个请求失败
- 每个 shipment 只能含一个包裹

**验证点**: 返回 `labels` 数组包含多个 `orderId`

## 场景 6: 取消标签

取消已创建的标签。

```
DELETE /shipment2/label/{orderId}
```

**实测结果**: ✅ 通过
- 可使用 orderId 或 requestId 取消
- 取消后状态变为 `canceled`
- 重复取消返回 `label-canceled`
- **全额退款验证**: 已通过 ✅（$3.80 全额返还）

**验证点**: 返回 `status: "success"`

## 场景 7: 账户余额查询

查询当前账户余额。

```
GET /user/account
```

**实测结果**: ✅ 通过
- 初始余额: $2,000.00
- 创建面单后: 自动扣减
- 取消面单后: 自动退款
- 最终余额: $1,983.75

**验证点**: 返回 `balance` 数值

## 场景 8: 验证错误处理

| 场景 | 预期 | 实测 |
|------|------|------|
| 重复 requestId | 400 拒绝 | ✅ `label requestId already exists` |
| 无效 API Key | 403 禁止 | ✅ `Forbidden` |
| 缺失 API Key | 403 禁止 | ✅ `Forbidden` |
| fullName > 35字符 | 400 | ✅ `fullName length must less than or equal to 35` |
| requestId < 15位 | 400 | ✅ `requestId length must large than or equal to 15` |

## 测试数据准备

```bash
# ⚠️ 注意: city 必须与 zipCode 匹配！
# 02478 = Belmont (不是 Boston)

# 测试发货地址
FROM_ADDRESS='{
  "zipCode": "02478",
  "fullName": "FZH Test",
  "address1": "90 Chester rd",
  "city": "Belmont",
  "state": "MA",
  "phoneNumber": "1111111111"
}'

# 测试收货地址（测试环境有效邮编）
TO_ADDRESS='{
  "zipCode": "03053",
  "fullName": "Test Customer",
  "address1": "55 Harvey Rd",
  "city": "Londonderry",
  "state": "NH",
  "phoneNumber": "1111111111"
}'

# 生成唯一 requestId（≥15位）
REQUEST_ID="$(date +%s)12345"
```

> 完整测试报告: [test-report-2026-07-16.md](test-report-2026-07-16.md)
