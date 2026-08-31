---
okf: v0.1
type: Solution
title: 赛狐 Amazon FBM 包裹追踪号写回测试记录（submitToPlatform / quickOutbound）— 待赛狐确认
description: P2BAA9T735007 测试两个写追踪号接口均未写入，且 quickOutbound shipmentType=1 疑似触发订单变已发货（无追踪号）；需赛狐确认正确写入口并协助恢复订单状态
timestamp: 2026-08-10
tags: [sellfox-shipping, submitToPlatform, quickOutbound, trackNo, amazon-fbm, 待赛狐确认]
---

# 赛狐 Amazon FBM 包裹追踪号写回测试记录 — 发给赛狐技术 / 同事说明

## 一、背景

我们（FZH）通过蜴国际（lizard）为赛狐的 Amazon FBM 包裹创建了尾程面单，获得了物流追踪号。我们的目标是**把这个物流追踪号写回赛狐**，让它显示在赛狐包裹详情的 `logistics.trackNo`。

测试包裹：`P2BAA9T735007`
- 店铺：Centrade-WOWMAX-US（shopId `596754`）
- 订单：`112-9128863-6646603`（Amazon，marketplace US）
- 订单状态（测试前）：**Unshipped**
- 包裹状态（测试前）：**to_process**
- SKU：`KS0249-QRJL-194` × 1
- 蜴国际面单追踪号：`383079265869`
- 赛狐仓库：274390（Centrade-WOWMAX-US-北美仓，type=2/FBA仓）

## 二、我们测试的两个接口及结果

### 接口 1：submitToPlatform（提交平台）

请求体（`POST /api/packageShip/submitToPlatform.json`）：

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

响应：

```json
{ "code": 0, "msg": null, "data": null }
```

结果：**code=0（返回成功），但 `data=null`，且 packageDetail 回读 `logistics.trackNo` 仍为 null** —— 追踪号**没有写入**。

### 接口 2：quickOutbound（快速出库，shipmentType=1 提交平台且扣库存）

请求体（`POST /api/packageShip/quickOutbound.json`）：

```json
{
  "packageList": [
    {
      "packageSn": "P2BAA9T735007",
      "carrier": "lizard",
      "trackNo": "383079265869",
      "shipmentType": 1,
      "warehouseId": 274390,
      "isOversea": 2
    }
  ]
}
```

响应（顶层）：

```json
{ "code": 0, "msg": "success", "data": { "successNum": 0, "failData": [...] } }
```

per-package 失败原因：

```
P2BAA9T735007: 该订单不需要提交平台
```

结果：**追踪号没有写入**（success=0，fail=1）。

## 三、问题 / 异常现象

**测试后发现赛狐该订单从 `Unshipped` 变成了 `Shipped`（已发货）**：

packageDetail 回读当前状态：

| 字段 | 值 |
|---|---|
| package_status | `has_shipped` |
| orderStatus | `Shipped` |
| shipTime | `2026-08-10 17:01:25` |
| logistics.trackNo | **null（仍无追踪号）** |
| order trackNo | null |

即：**订单变成了"已发货"，但追踪号并没有写入**。

我们不确定这是不是本次 `quickOutbound shipmentType=1` 调用的副作用（确认发货时即使平台提交失败/追踪号未写入，仍改了发货状态），需要赛狐协助确认。

## 四、需要赛狐技术确认的问题

1. **对 Amazon FBM 订单（订单 Unshipped、包裹 to_process），要往赛狐写入第三方物流（蜴国际）追踪号，应该调用哪个接口？**
   - 我们试了 `submitToPlatform` 和 `quickOutbound`，都没写入 `logistics.trackNo`。
   - 是否有专用接口（如按包裹写 trackNo / 物流下单发货 `applyTrackNo`），或需要在赛狐后台配置什么？
2. **`submitToPlatform` 返回 `code=0, data=null` 但未写入 trackNo**，这是什么语义？是否代表"请求被接受但订单不符合提交条件"？
3. **`quickOutbound` 对 Amazon FBM 订单返回"该订单不需要提交平台"**，是否说明 quickOutbound 只适用于多平台（非 Amazon）订单？
4. **本次 quickOutbound shipmentType=1 是否把订单从 Unshipped 改成了 Shipped（shipTime 被设置）？** 即使在"该订单不需要提交平台"失败的情况下，也会触发发货确认副作用吗？
5. **如何把这个订单从 `Shipped` 恢复为 `Unshipped`？** 它现在处于"已发货但无追踪号"的异常状态，需要恢复。赛狐 UI/后台是否有取消发货/恢复未发货的操作？

## 五、给同事的简要说明

- 我们测了两个"回写追踪号到赛狐"的接口，**都写不进去**（submitToPlatform 返回成功但什么都没写；quickOutbound 说"该订单不需要提交平台"）。
- 更严重的是：**订单变成了"已发货"，但追踪号是空的**——这不符合正常流程（应该先有追踪号再发货）。
- 原因待赛狐确认，初步怀疑是 quickOutbound shipmentType=1（确认发货+扣库存）的副作用，即使平台提交失败也改了发货状态。
- **已暂停用 shipmentType=1 测试**；纯写追踪号应用 shipmentType=0（仅提交平台，不扣库存）。
- 需要赛狐：① 确认 Amazon FBM 订单写追踪号的正确接口；② 把这个订单从"已发货"恢复为"未发货"。

## 六、附加信息（如赛狐需要）

- 本地审计记录：`submission.quick_outbound P2BAA9T735007 code=0 success=0 fail=1 msg=success`（两次，09:17 与 09:24）
- submitToPlatform 的 intent/attempt 记录：http 200，响应 `{"code":0,"msg":null,"data":null}`
- 蜴国际面单：carrier=`lizard`，service=`FedEx-Ground-J-TX`，trackNo=`383079265869`
