---
okf: v0.1
type: Spec
title: 通途库存权威与赛狐库存镜像下的 quickOutbound 单包探针
description: 记录 2026-08-10 会议确认的系统分工、库存镜像目标、未知 API 语义和 quickOutbound shipmentType 探针门禁
timestamp: 2026-08-10
tags: [sellfox-shipping, tongtool, sellfox, inventory-mirror, quickOutbound, probe]
---

# 通途库存权威与赛狐库存镜像下的 quickOutbound 单包探针

## 已确认的业务边界

- **通途是实物操作权威**：入库、异常出库、实际发货，以及后续向 Amazon 等销售平台的物流回传，近期继续由通途和仓库操作人员完成。
- **赛狐是销售侧可见库存镜像**：销售人员习惯在赛狐查看库存；目标是让赛狐库存与通途库存大体一致，而不是把本项目扩展成新的 WMS。
- 建立镜像的候选业务方案是：先在赛狐清零/重建期初库存，再通过海外仓备货单入库建立与通途一致的起始余额；此方案尚未实际验收。
- 两个系统各自扣减库存并不天然错误：它们是两套账。真正需要验证的是扣减的**赛狐仓库、SKU、数量、时点和失败处理**是否能与通途账形成可解释差异。

## 已知事实与未知项

| 项目 | 当前认识 | 证据状态 |
|---|---|---|
| `quickOutbound` | 赛狐 API 文档称快速出库；请求含 `packageSn`、`carrier`、`trackNo`、`shipmentType` 和可选 `warehouseId` | 客户端封装与 mock 已有 |
| `shipmentType=0` | 文档注释为仅提交平台、不扣赛狐库存 | 代码/API 文档层面，未做生产探针 |
| `shipmentType=1` | 可能扣减赛狐库存，且应明确赛狐仓库 | **语义、扣减范围、可重放性均未证实** |
| Friday 实测 | Jack 可能曾对 Amazon 订单/包裹调用成功，但目前没有可复核的请求、回读和三方前后状态证据 | 不能作为生产能力结论 |
| `submitToPlatform` | 过去对 Amazon FBM 包裹曾被拒，出现过 401、"仅支持未发货订单提交平台" 和 "不需要提交平台" 等结果 | 已有局部真实记录，不代表 quickOutbound |
| 通途先发货 | 通途之后可能回传 Amazon；赛狐接口是否因此拒绝或是否会重复推送，仍未知 | 必须单包验证 |

不得把接口名称、单次口头结果或 API 文档推断为已验证生产语义。

## 当前代码裁决

`packages-submit-quick-outbound` 只构建**单包请求预览**，不调用赛狐 HTTP：

- `--shipment-type 0`：预览文档所称的无赛狐库存扣减请求。
- `--shipment-type 1 --warehouse-id <赛狐仓库ID>`：预览可能扣减赛狐库存的请求；缺少仓库 ID 直接拒绝。
- 预览仍要求本地 `approved`、有效未取消面单、真实追踪号、承运商，以及没有 `UNKNOWN_BLOCKED` submission scope。
- Web 页面不发送；普通 CLI 也不发送。任何真实 quickOutbound 必须先实现其独立的 Outbox endpoint，并通过单包 `PROBE_ONLY` 门禁。

这不是永久禁用 `shipmentType=1`。它只是防止在没有用户指定测试包裹、仓库映射和副作用证据时，把库存扣减暴露成普通按钮或普通命令。

## Jack Agent 的验证任务

在仓库/赛狐仓库映射确认后，由用户指定一个可承受副作用的包裹；一次只验证一个端点和一个 `shipmentType`。每一行都要生成脱敏的前后对账记录。

| 场景 | 通途状态 | Amazon 状态 | 赛狐动作候选 | 需判断 |
|---|---|---|---|---|
| A | 尚未发货 | 尚无追踪号 | quickOutbound `shipmentType=0` | 是否更新赛狐 trackNo、是否推送平台、是否不扣赛狐库存 |
| B | 尚未发货 | 尚无追踪号 | quickOutbound `shipmentType=1` + 指定仓库 | 扣减哪个赛狐仓、哪些 SKU/数量、是否更新 trackNo/推送平台 |
| C | 已发货 | 尚未看到通途回传 | 只在 A/B 已确认安全后选其一 | 是否被拒、是否与通途后续回传重复 |
| D | 已发货 | 已有通途追踪号 | 不发送，只读检查 | 赛狐是否已经同步；不得为了测试覆盖现有结果 |

每次探针都必须记录：

1. 脱敏 package/order 标识、平台类型、通途发货状态，以及测试时是否已见 Amazon 追踪号。
2. 赛狐 packageDetail/UI 的 `trackNo`、包裹状态、目标仓库和相关 SKU 库存的发送前、后、30 秒、2 分钟、5 分钟结果。
3. 通途库存与发货状态、Amazon 履约/追踪状态的同一时间点结果。
4. 实际端点、`shipmentType`、`warehouseId`、HTTP 状态、脱敏业务 code/msg、耗时和 Outbox/intent 状态。
5. 是否出现重复平台推送、错误仓库扣减、错误 SKU/数量扣减、状态意外迁移或赛狐/通途差异。

真实请求不成功、超时、5xx、解析失败或副作用不明时，结论是 `UNKNOWN_BLOCKED`，只允许回读和人工调查，不得改参数重放。

## 结论门禁

- `shipmentType=0` 成功且无不可接受副作用，不自动证明 `shipmentType=1` 安全。
- `shipmentType=1` 只有在目标仓库、SKU/数量扣减、赛狐可见状态和平台副作用全部可解释后，才可评估为库存镜像候选。
- 任何一个端点若会产生不可接受的 Amazon/其他平台重复发货、错误仓扣减或不可恢复的库存差异，应记录为 `UNSAFE_PLATFORM_SIDE_EFFECT`，保持禁用。
- 即使确认可用，也只先开放 Outbox 的 `PROBE_ONLY` 单包 CLI；后续是否开放受限批次，取决于持续对账证据，而非一次成功。

## 后续设计方向

若 `shipmentType=1` 通过单包探针，后续实现 `quickOutbound` 专用 Outbox endpoint 类型，复用现有候选去重、确认、Policy、租约、`IN_FLIGHT` 崩溃阻断和回读机制；不得直接复用 `submitToPlatform` 的端点假设。

无论探针结果如何，库存镜像的下一项应是通途与赛狐的**每日只读对账报告**：按仓库/SKU 计数并保留全部差异，先解释差异，再讨论自动调整。
