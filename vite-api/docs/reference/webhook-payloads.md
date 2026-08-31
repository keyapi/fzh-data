# Webhook 通知载荷参考

## 推送时机

当标签订单处理完成时，Vite 系统会向配置的 Webhook URL 推送通知。

## 载荷格式

```json
{
  "orderId": "string",
  "status": "string",
  "url": "string",
  "trackingNumber": "string"
}
```

## 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `orderId` | string | 标签订单 ID |
| `status` | string | `OK` 成功 / `failed` 失败 |
| `url` | string | 标签 PDF 下载地址 |
| `trackingNumber` | string | 物流追踪号 |

## 比对

此格式与 `GET /shipment2/label/{orderId}` 的响应格式一致。

> Webhook 配置详见 [Webhook 配置指南](../webhooks/setup-guide.md)
