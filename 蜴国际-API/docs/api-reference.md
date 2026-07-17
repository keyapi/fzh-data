# 蜴国际 API 对接文档

> **最后更新**: 2026-07-17
> **文档类型**: API 参考

## 基本信息

- **API 文档**: http://47.106.72.196/api_doc2.html
- **API 基地址**: http://47.106.72.196
- **系统入口**: http://47.106.72.196/index.html
- **OpenAPI 规范**: 3.0.0
- **账户标识**: 用户代码 `M6180`（通过 getToken 返回）

## 认证方式

所有业务接口需要在 HTTP Header 中携带：
```
Authorization: {access_token}
```

access_token 通过调用 `getToken` 接口获取，有效期 **24 小时**。

---

## 接口清单

### 一、鉴权相关接口

#### 1. 获取访问授权 (getToken)

```
POST /api/svc/getToken
Content-Type: application/x-www-form-urlencoded
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| app_token | string | 是 | 开发者 Token（个人中心查看） |
| app_key | string | 是 | 开发者 Key（个人中心查看） |

**响应示例** (200):
```json
{
  "code": 200,
  "result": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "user_info": {
      "u_id": 250,
      "u_account": "lihui",
      "u_customer_code": "M6180"
    }
  },
  "msg": "Success"
}
```

**测试结果**: ✅ 可用
- token 为 JWT 格式
- 有效期 24 小时，过期需重新获取
- `u_customer_code` 为客户代码（当前: M6180）

---

### 二、订单相关接口

#### 2. 费用试算 (rates)

```
POST /api/svc/rates
Content-Type: application/json
Authorization: {access_token}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sm_code | string | 是 | 物流产品代码 |
| reference_no | string | 是 | 参考号 |
| weight_unit_type | string | 是 | 计量单位：1=LBS/Inches, 2=KG/CM |
| parcel_declared_value | integer | 是 | 申报价值 |
| parcel_quantity | integer | 是 | 包裹数 |
| box_list | array | 是 | 包裹信息列表 |
| ├ box_actual_weight | number | 是 | 包裹重量 |
| ├ box_length | number | 是 | 长 |
| ├ box_width | number | 是 | 宽 |
| └ box_height | number | 是 | 高 |
| oa_firstname | string | 是 | 收件人 |
| oa_company | string | 是 | 收件人公司 |
| oa_country | string | 是 | 收件人国家（2字母简码，如 US） |
| oa_state | string | 是 | 收件人州/省 |
| oa_city | string | 是 | 收件人城市 |
| oa_postcode | string | 是 | 收件人邮编 |
| oa_street_address1 | string | 是 | 收件人地址1 |
| oa_street_address2 | string | 是 | 收件人地址2 |
| oa_telphone | string | 是 | 收件人电话 |
| oa_doorplate | string | 是 | 收件人门牌号 |
| oa_phone_ext | string | 是 | 电话分机号 |
| signature_service | string | 是 | 签名服务：ASS=成人签名, SSF=普通签名 |
| shipper_address | object | 是 | **发件人信息（须已备案）** |
| ├ shipper_name | string | 是 | 发件人姓名 |
| ├ shipper_company | string | 否 | 发件人公司 |
| ├ shipper_country | string | 是 | 发件人国家（2字母简码） |
| ├ shipper_state_province | string | 是 | 发件人州/省 |
| ├ shipper_city | string | 是 | 发件人城市 |
| ├ shipper_postal_code | string | 是 | 发件人邮编 |
| ├ shipper_address1 | string | 是 | 发件人地址1 |
| ├ shipper_address2 | string | 否 | 发件人地址2 |
| ├ shipper_doorplate | string | 否 | 发件人门牌号 |
| └ shipper_telphone | string | 是 | 发件人电话 |

**响应示例** (200):
```json
{
  "code": 200,
  "result": {
    "sm_code": "FedEx-Ground-J-TX",
    "address_type": 1,
    "address_type_text": "Residential",
    "currency_code": "USD",
    "total_charge": "14.86",
    "shipping_charge": "9.01",
    "charge_weight": 10,
    "charge_detail": [
      { "charge_desc": "运费", "amount": "9.01" },
      { "charge_desc": "住宅地址附加费", "amount": "3.25" },
      { "charge_desc": "燃油附加费", "amount": "2.60" }
    ]
  },
  "msg": "Success"
}
```

**测试结果**: ⚠️ 需要已备案发件地址
- 发件地址必须在系统后台提前备案
- 未备案会返回 `code: 400, msg: "发货地址不存在"`

---

#### 3. 费用试算 V2 (ratesv2)

```
POST /api/svc/ratesv2
Content-Type: application/json
Authorization: {access_token}
```

与 rates 接口的区别：
- **sm_code 可选**：不传则列出全部可用物流产品
- **新增 ca_zone**：发货地区域（0=全域, 1=美东, 2=美西, 3=美中, 4=美南）
- **返回对象以 sm_code 为 key**：支持一次性对比多个物流产品

**请求参数**（同 rates，新增字段）:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ca_zone | integer | 是 | 发货地区域（0/全域, 1/美东, 2/美西, 3/美中, 4/美南） |

**响应示例** (200):
```json
{
  "code": 200,
  "result": {
    "FedEx-Ground-J-TX": {
      "sm_code": "FedEx-Ground-J-TX",
      "address_type": 1,
      "address_type_text": "Residential",
      "currency_code": "USD",
      "total_charge": "14.86",
      "shipping_charge": "9.01",
      "charge_detail": [
        { "charge_desc": "运费", "amount": "9.01" },
        { "charge_desc": "住宅地址附加费", "amount": "3.25" },
        { "charge_desc": "燃油附加费", "amount": "2.60" }
      ]
    }
  },
  "msg": "Success"
}
```

**测试结果**: ✅ 可用（2026-07-17 验证成功）
- 成功返回多组物流产品费用估算

---

#### 4. 创建订单 (createOrder)

```
POST /api/svc/createOrder
Content-Type: application/json
Authorization: {access_token}
```

**请求参数**: 同 rates 的请求参数 + 以下字段：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| oa_email | string | 是 | 收件人邮箱 |
| box_list[].product_name_cn | string | 是 | 产品中文名 |
| box_list[].product_name_en | string | 是 | 产品英文名 |
| box_list[].product_num | integer | 是 | 产品数量 |
| box_list[].product_price | number | 是 | 产品金额 |
| box_list[].products_hs_code | string | 否 | 海关编码 |
| box_list[].products_origin_country | string | 否 | 原产地国家 |
| box_list[].customer_box_code | string | 否 | 客户自定义箱号 |
| reference_no | string | 是 | 订单参考号（唯一） |

**响应示例** (200):
```json
{
  "code": 200,
  "result": {
    "order_code": "J9808202110106043891",
    "labels": {
      "tracking_number": "1Z0VE597030702040",
      "label_url": "http://...",
      "file_type": "pdf"
    },
    "fee": [
      { "ft_code": "shipping", "ft_name": "运输费", "amount": "12.30", "currency_code": "USD" }
    ]
  },
  "msg": "Success"
}
```

**测试结果**: ⏳ 未测试（账户欠费）

---

#### 5. 取消订单 (cancelOrder)

```
POST /api/svc/cancelOrder
Content-Type: application/json
Authorization: {access_token}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_code | string | 是 | 订单号 |
| reference_no | string | 是 | 参考号 |

**说明**: 仅在订单为草稿、已预报、已提交（未在预报执行中）状态时可取消。

---

#### 6. 获取订单面单 (getLabel)

```
POST /api/svc/getLabel
Content-Type: application/json
Authorization: {access_token}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_code | string | 是 | 订单号 |
| reference_no | string | 是 | 参考号 |

**响应码说明**:
- **200**: 面单已就绪，返回面单 URL 和跟踪号
- **202**: 订单正在预报物流中，建议 30 秒后重试

**注意事项**:
- 同一个单号一秒钟限制查询一次
- 关注 `sync_service_status` 和 `logistics_err` 字段判断是否预报失败
- `sync_service_status = 2` 且 `logistics_err` 有值时表示预报失败

---

#### 7. 获取订单信息 (getOrderInfo)

```
POST /api/svc/getOrderInfo
Content-Type: application/json
Authorization: {access_token}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_code | string | 否 | 订单号 |
| reference_no | string | 否 | 客户参考单号 |
| date_from | string | 否 | 开始时间 (Y-m-d H:i:s) |
| date_to | string | 否 | 结束时间 (Y-m-d H:i:s) |

---

#### 8. 获取面单预览 (getPrintLabel)

```
POST /api/svc/getPrintLabel
Content-Type: application/x-www-form-urlencoded
Authorization: {access_token}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_code | string | 是 | 订单号 |

**响应**: 返回 PDF 面单 URL 列表

---

### 三、账户相关接口

#### 9. 查询账户余额 (getBalance)

```
GET /api/svc/getBalance
Authorization: {access_token}
```

**响应示例** (200):
```json
{
  "code": 200,
  "result": { "balance": 100.12 },
  "msg": "Success"
}
```

---

### 四、推送相关接口

#### 10. 订单推送 (custom_settings_webhook_url)

```
POST /custom_settings_webhook_url
```

用于接收系统推送的订单状态变更通知。需要先在系统后台配置回调 URL。

---

## 发件地址说明

发件地址（`shipper_address`）需要在系统中**提前备案**后才能使用。

- Excel 中使用的地址编码是系统中已备案地址的内部标识
- API 调用时**不能直接使用地址编码**，必须填写完整的地址对象
- 地址对象字段：`shipper_name`, `shipper_postal_code`, `shipper_address1`, `shipper_address2`, `shipper_state_province`, `shipper_city`, `shipper_country`, `shipper_telphone`

### 已备案地址列表

| 地址编码 | 发货人信息 |
|---------|-----------|
| S0886 | Nickole Ayala, 10451, 417 East 162nd Street, NY, Bronx, 9178817328 |
| S0656 | Qiang Ma, 07936, 389 Route 10 Unit R, NJ, East Hanover, 1234567890 |
| **S0143** | **Dan-zhao, 77099, 10812 Fallstone Rd, Suite 402, TX, Houston, 2816770938** |
| S0625 | A_TX_77091, 77099, 10812 Fallstone Rd, Suite 402, TX, Houston, 0000000000 |
| S0941 | FULFILLMENT CENTER, 07094, 915 Secaucus Rd, NJ, Secaucus, 0000000000 |
| S0795 | Qiang Ma, 07936, 389 STATE ROUTE 10 UNIT R, NJ, EAST HANOVER, 1234567890 |
| S1261 | 77489, 77489, 611 S. Cravens Rd Suite 100, TX, Missori City, 6083349880 |

### 地址编码 → API 字段映射（以 S0143 为例）

```
S0143: Dan-zhao, 77099, 10812 Fallstone Rd, Suite 402, TX, Houston, 2816770938
  ↓
shipper_name:        Dan-zhao
shipper_postal_code: 77099
shipper_address1:    10812 Fallstone Rd
shipper_address2:    Suite 402
shipper_state_province: TX
shipper_city:        Houston
shipper_country:     US
shipper_telphone:    2816770938
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

## 错误码说明

| code | 说明 |
|------|------|
| 200 | 成功 |
| 202 | 处理中（getLabel 接口面单尚未就绪） |
| 400 | 请求参数错误 |
| 401 | token 过期或无效 |

## Token 缓存策略

access_token 有效期 24 小时，建议：

1. 首次调用 getToken 获取 token
2. 将 token 缓存到本地（文件/数据库/Redis）
3. 每次调用前检查 token 是否过期
4. 过期则重新调用 getToken 获取新 token
5. token 失效时 API 返回 `code: 401, msg: token过期`
