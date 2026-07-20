# 快速入门

> 从获取 API 凭证到完成费用试算的完整流程。

## 前置准备

1. **系统访问**：确认可访问 http://47.106.72.196/index.html
2. **API 凭证**：在系统「个人中心 → 开发者信息」中获取 token 和 key，写入仓库根 `.env`：
   - `YIGLOBAL_APP_TOKEN` / `YIGLOBAL_APP_KEY` / `YIGLOBAL_API_BASE_URL`
   - 见 [`../.env.example`](../.env.example)
3. **发件地址备案**（重要）：在系统中添加并备案发件地址，否则费用试算会报错。Excel 中的地址编码（如 **S0143**）对应系统中的一条发件地址，但 API 中必须填写完整的地址信息，不能直接使用编码。

## 步骤 1：获取 access_token

```bash
# 值从环境变量读取；下面 YOUR_* 仅为占位
curl -s -X POST http://47.106.72.196/api/svc/getToken \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "app_token=YOUR_TOKEN&app_key=YOUR_KEY"
```

成功响应：
```json
{
  "code": 200,
  "result": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "user_info": { "u_account": "lihui", "u_customer_code": "M6180" }
  }
}
```

## 步骤 2：调用费用试算

### 方式 A：查询指定物流产品 (rates)

```bash
curl -s -X POST http://47.106.72.196/api/svc/rates \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "sm_code": "FedEx-Ground-J-TX",
    "reference_no": "test-001",
    "weight_unit_type": "1",
    "parcel_declared_value": 100,
    "parcel_quantity": 1,
    "box_list": [{
      "box_actual_weight": 10,
      "box_length": 12,
      "box_width": 10,
      "box_height": 8
    }],
    "oa_firstname": "Receiver Name",
    "oa_company": "Company",
    "oa_country": "US",
    "oa_state": "CA",
    "oa_city": "Los Angeles",
    "oa_postcode": "90001",
    "oa_street_address1": "100 Main Street",
    "oa_street_address2": "",
    "oa_telphone": "1234567890",
    "oa_doorplate": "",
    "oa_phone_ext": "",
    "signature_service": "",
    "shipper_address": {
      "shipper_name": "发件人",
      "shipper_postal_code": "77099",
      "shipper_address1": "10812 Fallstone Rd",
      "shipper_address2": "Suite 402",
      "shipper_state_province": "TX",
      "shipper_city": "Houston",
      "shipper_country": "US",
      "shipper_telphone": "2816770938"
    }
  }'
```

### 方式 B：对比全部物流产品 (ratesv2)

```bash
curl -s -X POST http://47.106.72.196/api/svc/ratesv2 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "reference_no": "test-002",
    "weight_unit_type": "1",
    "ca_zone": 0,
    "parcel_declared_value": 100,
    "parcel_quantity": 1,
    "box_list": [{
      "box_actual_weight": 10,
      "box_length": 12,
      "box_width": 10,
      "box_height": 8
    }],
    "oa_firstname": "Receiver Name",
    "oa_company": "Company",
    "oa_country": "US",
    "oa_state": "CA",
    "oa_city": "Los Angeles",
    "oa_postcode": "90001",
    "oa_street_address1": "100 Main Street",
    "oa_street_address2": "",
    "oa_telphone": "1234567890",
    "oa_doorplate": "",
    "oa_phone_ext": "",
    "signature_service": "",
    "shipper_address": {
      "shipper_name": "Dan-zhao",
      "shipper_postal_code": "77099",
      "shipper_address1": "10812 Fallstone Rd",
      "shipper_address2": "Suite 402",
      "shipper_state_province": "TX",
      "shipper_city": "Houston",
      "shipper_country": "US",
      "shipper_telphone": "2816770938"
    }
  }'
```

## 常见问题

### Q: 返回 "发货地址不存在"
**原因**: `shipper_address` 未在系统中备案。
**解决**: 登录系统 → 地址管理 → 添加发件地址 → 备案后再试。

### Q: 返回 "token过期"
**原因**: access_token 超过 24 小时有效期。
**解决**: 重新调用 getToken 获取新 token。

### Q: 账户欠费能测试哪些接口？
- ✅ getToken（获取授权）
- ✅ rates / ratesv2（费用试算）
- ⏳ createOrder（需要账户余额）
- ⏳ getLabel（需要已创建的订单）
