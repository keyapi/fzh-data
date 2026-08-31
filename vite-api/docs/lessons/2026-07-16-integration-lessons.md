# 集成经验教训

## 本日集成记录

**日期**: 2026-07-16

### 1. API 文档地址说明

文档地址 `http://docs.vitedirect.com/?urls.primaryName=Uniuni%20Ground` 实际加载的是 Swagger UI 的首页，默认选中 "Uniuni Ground" 标签。但实际 API 分组中**没有** Uniuni Ground，而是 9 个独立分组：USPS V2, FedEx V2, FedEx International, UPS V2, UPS International, GOFO Express, Amazon Ground, EEI, Tracking。

### 2. 渠道代码注意事项

- 测试环境使用 `GOFO_PARCEL` 而非文档中的 `GOFO_PX`
- 渠道代码 `GFUS` 和 `YT` 需要联系客户经理确认
- 各渠道支持的回标平台不同

### 3. 单位转换

API 严格要求使用 lbs 和 inch。如果系统使用 kg/cm，需要在发送前转换：
- kg × 2.2046 = lbs
- cm ÷ 2.54 = inch

### 4. requestId 策略 (已实测验证 ✅)

- `requestId` 必须 **≥ 15 位**
- 建议格式: `时间戳(13位) + 随机数(2-3位)`
- 重复 requestId 会被拒绝: `label requestId already exists`
- 推荐生成: `$(date +%s)12345` 或 `Date.now() + random(100,999)`

### 5. 面单状态流转 (已实测验证 ✅)

```
创建 → pending → OK → canceled(取消后)
```

- `pending`: 标签生成中，需要轮询或等待 Webhook
- `OK`: 标签已生成，返回 `url`(PDF) 和 `trackingNumber`
- `canceled`: 已取消，`url` 变为空

### 6. 地址邮编注意事项 (已实测验证 ✅)

- city 必须与 zipCode 严格匹配: **02478 = Belmont** (不是 Boston)
- 测试环境仅部分邮编可用:
  - ✅ 02478 (Belmont, MA) → 03053 (Londonderry, NH)
  - ❌ 91321 (Santa Clarita, CA) — 不在服务范围
  - ❌ 10001 (New York, NY) — 不在服务范围

### 7. 面单取消与退款 (已实测验证 ✅)

- 使用 **orderId** 取消: `DELETE /shipment2/label/{orderId}` ✅ 成功
- 取消后 **全额退款**: $3.80 全额返还
- 重复取消: 返回 `label-canceled` ❌
- 取消状态: `canceled`（获取面单时 status 字段）

### 8. 批量创建注意事项 (已实测验证 ✅)

- 任一 shipment 失败 → 整个请求失败
- 每个 shipment 只能含一个包裹
- 各 shipment 的 requestId 必须唯一

### 9. 有效渠道/服务组合 (已实测验证 ✅)

| 组合 | 运费 | 用途 |
|------|------|------|
| GOFO_PX + PARCEL | ✅ $3.80 | 通用包裹 |
| GOFO_PARCEL + GFUS | ✅ $3.35 | 回标(TEMU/TIKTOK/SHEIN/EBAY) |
| GOFO_PARCEL + YT | ✅ $3.35 | 回标(AMAZON/WALMART) |
| GOFO_PX + GFUS | ❌ 无效 | 不支持 |

### 10. 测试数据局限性

测试环境的 API 返回的是模拟数据，不能作为生产环境计费依据。
