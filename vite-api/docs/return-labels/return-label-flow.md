# 回标标签创建流程

## 端到端流程

```
                   ┌──────────────┐
                   │ 电商平台     │
                   │ (TEMU/AMAZON)│
                   └──────┬───────┘
                          │ 退货请求
                          ▼
                   ┌──────────────┐
                   │ FZH 系统     │
                   │ (集成 Vite)  │
                   └──────┬───────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
              ▼           ▼           ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ 查询运费  │ │ 创建标签  │ │ 获取标签  │
       │ POST     │→│ POST     │→│ GET      │
       │ /rate2/  │ │ /shipment│ │ /shipment│
       │ gofo     │ │ 2/gofo   │ │ 2/label/ │
       └──────────┘ └──────────┘ └──────────┘
                                      │
                                      ▼
                               ┌──────────────┐
                               │ 打印面单     │
                               │ 贴在退货包裹  │
                               └──────────────┘
```

## 步骤详解

### Step 1: 查询运费

```bash
POST /rate2/gofo
```

> 详见 [运费查询示例](../carriers/gofo-express/examples/rate-request.md)

### Step 2: 创建回标标签

```bash
POST /shipment2/gofo
```

注意：
- `serviceType` 填 `GOFO_PARCEL`
- `channel` 根据平台选择 `GFUS` 或 `YT`
- `requestId` 必须全局唯一
- 重量和尺寸使用 **lbs** 和 **inch**

> 详见 [创建标签示例](../carriers/gofo-express/examples/create-label.md)

### Step 3: 获取标签

```bash
GET /shipment2/label/{orderId}
```

等待 `status` 变为 `OK`，从 `url` 字段获取 PDF 面单。

### Step 4: 打印面单

下载 PDF 并打印，贴在退货包裹上。

## 注意事项

- 测试环境的数据均为模拟数据
- requestId 生成建议: `Date.now() + random(100,999)`
- 面单 URL 在测试环境中可能不可下载
