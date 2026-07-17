# 蜴国际-API — 面单打印系统对接

> 蜴国际打单系统 API 对接模块。提供面单打印、费用试算、订单管理等接口。

## 接口总览

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/svc/getToken` | POST | 获取访问授权 (access_token) |
| `/api/svc/rates` | POST | 费用试算（单个物流产品） |
| `/api/svc/ratesv2` | POST | 费用试算 V2（支持多物流产品对比） |
| `/api/svc/createOrder` | POST | 创建订单 |
| `/api/svc/cancelOrder` | POST | 取消订单 |
| `/api/svc/getLabel` | POST | 获取订单面单及跟踪号 |
| `/api/svc/getOrderInfo` | POST | 获取订单信息 |
| `/api/svc/getPrintLabel` | POST | 获取面单预览 |
| `/api/svc/createReturn` | POST | 创建回邮订单 |
| `/api/svc/getBalance` | GET | 查询账户余额 |
| `/custom_settings_webhook_url` | POST | 订单推送回调 |

## 前置条件

### 获取 API 凭证

1. 登录面单打印系统：http://47.106.72.196/index.html
2. 进入 **个人中心** → **开发者信息**
3. 获取 `token` 和 `key`

### 发件地址备案

> **重要**：发件地址必须在系统中先备案才能用于 API 调用，否则会返回 `"发货地址不存在"`。

备案方式：
- 登录系统后，在 **地址管理** 中添加发货地址
- 备案后的地址才能在 `shipper_address` 字段中使用
- Excel 中使用的地址编码（如 **S0143**）对应系统中的一条已备案发件地址记录，在 API 中需填写完整的地址信息

**当前发件地址**：

| 地址编码 | 发货人信息 |
|---------|-----------|
| S0886 | Nickole Ayala, 10451, 417 East 162nd Street, NY, Bronx, 9178817328 |
| S0656 | Qiang Ma, 07936, 389 Route 10 Unit R, NJ, East Hanover, 1234567890 |
| **S0143** | **Dan-zhao, 77099, 10812 Fallstone Rd, Suite 402, TX, Houston, 2816770938** |
| S0625 | A_TX_77091, 77099, 10812 Fallstone Rd, Suite 402, TX, Houston, 0000000000 |
| S0941 | FULFILLMENT CENTER, 07094, 915 Secaucus Rd, NJ, Secaucus, 0000000000 |
| S0795 | Qiang Ma, 07936, 389 STATE ROUTE 10 UNIT R, NJ, EAST HANOVER, 1234567890 |
| S1261 | 77489, 77489, 611 S. Cravens Rd Suite 100, TX, Missori City, 6083349880 |

### 物流产品代码

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

## 接口调用流程

```
1. 获取 access_token
   POST /api/svc/getToken  (app_token + app_key)
   ↓
2. 费用试算（下单前预估费用）
   POST /api/svc/rates 或 /api/svc/ratesv2
   ↓
3. 创建订单
   POST /api/svc/createOrder
   ↓
4. 获取面单及跟踪号（异步，建议 30 秒轮询）
   POST /api/svc/getLabel
```

## 当前测试结论

| 接口 | 状态 | 日期 | 备注 |
|------|------|------|------|
| `getToken` | ✅ 通过 | 2026-07-17 | 正常返回 access_token(JWT)，有效期 24h |
| `rates` | ✅ 通过 | 2026-07-17 | 成功返回费用估算（FedEx-Ground-J-TX $14.86） |
| `ratesv2` | ✅ 通过 | 2026-07-17 | 成功返回多物流产品费用对比 |
| `createOrder` | ✅ 通过 | 2026-07-17 | 成功创建订单，同步返回跟踪号和面单 PDF |
| `getLabel` | ✅ 通过 | 2026-07-17 | 成功获取面单信息（sync_service_status=1） |
| `cancelOrder` | ✅ 通过 | 2026-07-17 | 成功取消已创建的订单 |
| `getBalance` | ⏳ 未测试 | — | — |
| `getOrderInfo` | ⏳ 未测试 | — | — |
| `getPrintLabel` | ⏳ 未测试 | — | — |

## 注意事项

1. **access_token 有效期 24 小时**，建议缓存重复使用。失效时会返回 `code: 401, msg: token过期`
2. **发件地址必须已备案**，否则费用试算和创建订单会报错
3. 创建订单后，面单和跟踪号是**异步返回**的，建议 30 秒轮询 `getLabel` 接口
4. **reference_no 必须保持一致**：cancelOrder、getLabel 等接口的 `reference_no` 必须与 createOrder 时使用的值完全一致，否则返回 `"订单数据不存在"`
5. 物流产品代码 (`sm_code`) 可以在批量导入管理页右侧查看物流产品信息列表
6. 计量单位：`weight_unit_type = 1` 表示 LBS/Inches，`2` 表示 KG/CM

## 相关资源

- API 文档：http://47.106.72.196/api_doc2.html
- 系统地址：http://47.106.72.196/index.html
