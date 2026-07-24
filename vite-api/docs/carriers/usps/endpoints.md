# USPS V2 端点参考

## 查询运费

```
POST /rate2/usps
```

## 创建标签

```
POST /shipment2/usps
```

创建标签时额外支持字段：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `isNeedToConfirm` | boolean | 否 | 是否需要调用确认 API |
| `clientKey` | string | 否 | 客户端标识 |
| `clientName` | string | 否 | 客户端名称 |

> 通用端点（获取标签、取消标签、余额查询）与 GOFO 共用，见 [GOFO 端点参考](../gofo-express/endpoints.md)
