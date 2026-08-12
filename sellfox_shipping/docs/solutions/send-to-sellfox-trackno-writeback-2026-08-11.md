# 赛狐追踪号写回问题反馈（Amazon FBM 订单）

> 发送给：赛狐技术支持
> 日期：2026-08-11
> 我方联系人：FZH（Jack）

## 基本信息

| 项目 | 值 |
|---|---|
| **clientId** | `368618` |
| **url** | `https://openapi.sellfox.com/api/packageShip/quickOutbound.json`（quickOutbound）<br>`https://openapi.sellfox.com/api/packageShip/submitToPlatform.json`（submitToPlatform） |
| **requestId（quickOutbound）** | `feecfeb6-5975-40de-80f1-01376a9d1b09` |
| **requestId（submitToPlatform）** | `79f97e4e-5d45-43d3-9eac-89e5445d1398` |

## 问题描述

包裹 `P2BAA9T735007`（Amazon FBM 订单 `112-9128863-6646603`，店铺 Centrade-WOWMAX-US / shopId `596754`），订单状态 **Unshipped**、包裹状态 **to_process**。

我们通过蜴国际为该包裹创建了尾程面单，获得物流追踪号 `383079265869`，需要把它**写回赛狐**（显示在包裹详情的 `logistics.trackNo`）。

试了两个接口都没写入：

1. **submitToPlatform**：返回 `code=0, data=null`，但 packageDetail 回读 `logistics.trackNo` 仍为 **null**（追踪号未写入）。
2. **quickOutbound**（shipmentType=0 和 1 都试过）：返回 `code=0`，但 per-package 失败 **"该订单不需要提交平台"**（追踪号未写入）。

**异常现象**：测试后赛狐订单从 `Unshipped` 变成了 **`Shipped`（已发货）**，`shipTime` 被设置，但 `trackNo` 仍为空——疑似 quickOutbound shipmentType=1（提交平台且扣库存/确认发货）的副作用，即使平台提交失败/追踪号未写入，仍触发了发货状态变更。

### 需要赛狐确认的问题

1. 对 Amazon FBM 订单（订单 Unshipped、包裹 to_process），要把第三方物流（蜴国际）追踪号写入赛狐，**应该调用哪个接口**？
2. `submitToPlatform` 返回 `code=0, data=null` 但未写入 trackNo，**是什么语义**？是否代表"请求被接受但订单不符合提交条件"？
3. `quickOutbound` 对 Amazon FBM 订单返回"该订单不需要提交平台"，**是否说明 quickOutbound 只适用于多平台（非 Amazon）订单**？
4. 本次 quickOutbound shipmentType=1 **是否把订单从 Unshipped 改成了 Shipped（shipTime 被设置）**？即使"该订单不需要提交平台"失败，也会触发发货确认副作用吗？
5. **如何把这个订单从 `Shipped` 恢复为 `Unshipped`**？当前处于"已发货但无追踪号"的异常状态。

## 输入参数

### 接口1：submitToPlatform 请求体

```json
{
  "shopId": "596754",
  "orderId": "112-9128863-6646603",
  "carrierName": "lizard",
  "trackNo": "383079265869",
  "items": [
    { "orderItemId": "166545481579761", "quantity": "1" }
  ]
}
```

### 接口2：quickOutbound 请求体（shipmentType=0 与 1 均试过）

```json
{
  "packageList": [
    {
      "packageSn": "P2BAA9T735007",
      "carrier": "lizard",
      "trackNo": "383079265869",
      "shipmentType": 0,
      "warehouseId": 274390,
      "isOversea": 2
    }
  ]
}
```

> 注：shipmentType=1 时请求体相同（warehouseId=274390, isOversea=2）。

## 输出参数

### 接口1：submitToPlatform 响应

```json
{ "code": 0, "msg": null, "data": null, "ts": 1786351420871, "requestId": "79f97e4e-5d45-43d3-9eac-89e5445d1398" }
```

### 接口2：quickOutbound 响应（shipmentType=0 实测）

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "successNum": 0,
    "failData": [
      { "packageSn": "P2BAA9T735007", "msg": "该订单不需要提交平台" }
    ]
  },
  "ts": 1786410526776,
  "requestId": "feecfeb6-5975-40de-80f1-01376a9d1b09"
}
```

### 测试后 packageDetail 回读状态

| 字段 | 值 |
|---|---|
| package_status | `has_shipped` |
| orderStatus | `Shipped` |
| shipTime | `2026-08-10 17:01:25` |
| logistics.trackNo | `null`（仍无追踪号）|
| order trackNo | `null` |

## 截图

- **赛狐后台**（我方可截）：订单/包裹详情显示"已发货但追踪号为空"。

  - ![1786410776932](C:\Users\DEV01\AppData\Roaming\Typora\typora-user-images\1786410776932.png)

- **我方系统**：包裹详情页 + 本地审计记录（`submission.quick_outbound P2BAA9T735007 code=0 success=0 fail=1 msg=success`）。

  ​	![1786410812965](C:\Users\DEV01\AppData\Roaming\Typora\typora-user-images\1786410812965.png)

## 附加说明

- 蜴国际面单：carrier=`lizard`，service=`FedEx-Ground-J-TX`，trackNo=`383079265869`。
- 赛狐仓库：`274390`（Centrade-WOWMAX-US-北美仓，type=2/FBA仓）。
- 我方已暂停用 shipmentType=1 测试；纯写追踪号将改用 shipmentType=0。
