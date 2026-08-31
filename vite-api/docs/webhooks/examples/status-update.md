# Webhook 状态更新通知示例

## 状态更新载荷

与 [标签通知](label-notification.md) 格式一致：

```json
{
  "orderId": "PPGF-1689480000123-1753253592246",
  "status": "OK",
  "url": "http://docs.vitedirect.com/assets/9400110200830513838769.pdf",
  "trackingNumber": "9400111899564088456077"
}
```

## 处理建议

- 在接收到 `status: "OK"` 时，可以自动触发面单打印
- 在接收到 `status: "failed"` 时，记录错误并触发告警
- 同一个 orderId 可能收到多次通知（状态变更时）
