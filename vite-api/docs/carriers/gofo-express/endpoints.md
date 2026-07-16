# GOFO Express API 端点参考

> 源规范: `/config/gofo.yaml`

---

## 1. 查询运费

```
POST /rate2/gofo
```

获取指定包裹的运费报价。

### 请求体

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `shipDate` | string | 是 | 发货日期，格式 `yyyy-MM-dd` |
| `serviceType` | string | 是 | 服务类型，如 `GOFO_PX` |
| `channel` | string | 否 | 渠道代码，如 `PARCEL`, `GFUS`, `YT` |
| `from` | object | 是 | 发件地址 |
| `to` | object | 是 | 收件地址 |
| `packages` | array | 是 | 包裹数组（只读取 packages[0]） |

### from/to 地址结构

| 字段 | 类型 | 必需 | 最大长度 | 说明 |
|------|------|------|----------|------|
| `fullName` | string | 是 | 35 | 收/发件人姓名 |
| `company` | string | 否 | 35 | 公司名 |
| `address1` | string | 是 | 35-50 | 地址行1 |
| `address2` | string | 否 | 50 | 地址行2 |
| `city` | string | 是 | 28 | 城市 |
| `state` | string | 是 | 2 | 州缩写（如 CA, NY） |
| `zipCode` | string | 是 | 10 | 邮编 |
| `phoneNumber` | string | 否 | 10-15 | 电话 |

### packages 结构

| 字段 | 类型 | 必需 | 最大 | 单位 | 说明 |
|------|------|------|------|------|------|
| `weight` | number | 是 | - | lbs | 重量 |
| `length` | number | 是 | 999 | inch | 长 |
| `width` | number | 是 | 999 | inch | 宽 |
| `height` | number | 是 | 999 | inch | 高 |

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `carrier` | string | 承运商 (`GOFO`) |
| `serviceType` | string | 服务类型 |
| `serviceDescription` | string | 服务描述 |
| `totalAmount` | number | 总金额 (USD) |
| `amountDetails.postageAmount` | number | 邮资金额 |
| `billingWeight` | number | 计费重量 (lbs) |
| `zone` | string | 分区 |
| `estimatedDelivery` | string | 预计送达 |

---

## 2. 创建标签

```
POST /shipment2/gofo
```

创建发货标签。

### 请求体

除运费查询的字段外，额外包含：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `requestId` | string | 是 | **唯一交易ID**，建议 `$timestamp + $random_3_digits` |
| `memo` | string | 否 | 标签备注，≤30字符 |
| `reference` | string | 否 | 商户参考号，会在 Webhook 和查询时原样返回 |

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `orderId` | string | 标签订单ID |
| `status` | string | 状态 (`pending`) |
| `carrier` | string | 承运商 |
| `serviceType` | string | 服务类型 |
| `totalAmount` | number | 总金额 |
| `amountDetails.postageAmount` | number | 邮资金额 |
| `currentBalance` | number | 当前余额（创建后快照） |
| `billingWeight` | number | 计费重量 |

---

## 3. 查询标签

```
GET /shipment2/label/{orderId}
```

获取标签详情和下载链接。

### 路径参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `orderId` | string | 是 | 创建标签时返回的 orderId |

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `orderId` | string | 订单ID |
| `requestId` | string | 请求ID |
| `status` | string | 状态: `OK` / `failed` |
| `carrier` | string | 承运商 |
| `trackingNumber` | string | 追踪号 |
| `trackingNumbers` | array | 多包裹追踪号列表 |
| `url` | string | 标签PDF下载链接 |
| `reference` | string | 商户参考号 |

---

## 4. 批量创建标签

```
POST /shipment2/gofo/batch
```

一次请求创建多个标签。

### 请求体

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `shipments` | array | 是 | 标签数组，每个元素结构和创建标签一致 |

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `labels` | array | 所有标签结果 |
| `currentBalance` | number | 当前余额 |

---

## 5. 取消标签

```
DELETE /shipment2/label/{requestId}
```

取消已创建的标签。

### 路径参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `requestId` | string | 是 | 创建标签时的 orderId/requestId |

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 状态: `success` |
| `message` | string | 取消结果说明 |

---

## 6. 查询账户余额

```
GET /user/account
```

查询当前账户余额。

### 响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `balance` | number | 账户余额 (USD) |
