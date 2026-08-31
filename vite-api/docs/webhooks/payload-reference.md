# Webhook 事件类型和载荷

## 事件类型

### 标签就绪通知

当标签处理完成（无论成功或失败）时触发。

### 状态更新通知

当标签状态发生变化时触发。

## 通用载荷格式

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
| `status` | string | 状态: `OK` / `failed` / `pending` |
| `url` | string | 标签 PDF 下载地址（状态为 OK 时） |
| `trackingNumber` | string | 物流追踪号（状态为 OK 时） |

## 状态枚举

| 状态 | 说明 |
|------|------|
| `pending` | 标签处理中 |
| `OK` | 标签已生成 |
| `failed` | 标签创建失败 |
