---
okf: v0.1
type: Research
title: 蜴国际 API（PR #90/#91）与现有 Excel 路径对照
description: main 合入的 蜴国际-API；PR91 负余额下 createOrder/getLabel/cancelOrder 已验；不含凭证
timestamp: 2026-07-17
tags: [sellfox-shipping, lizard, api, excel]
updated: 2026-07-17
---

# 蜴国际 API（PR #90 / #91）↔ Excel 路径

**来源：** `origin/main` 模块 `蜴国际-API/`  
- PR **#90**（`90712b0`）：模块初建 + 文档  
- PR **#91**（`7e1ec1f` / `8ce1c22`）：负余额下仍完成 **createOrder / getLabel / cancelOrder** 真测并更新文档  

**本仓分支不合并该目录**；查文档用 main。**禁止**把该模块 HANDOFF 里的明文 token/key 拷入本模块。

## 同事测试结论（PR#91 文档）

| 接口 | 状态 | 备注 |
|------|------|------|
| `getToken` | ✅ | JWT，约 24h |
| `rates` / `ratesv2` | ✅ | 需已备案发件地址；例 FedEx-Ground-J-TX |
| `createOrder` | ✅ | 成功创建；本次响应中**同步**带回跟踪号与面单 PDF URL |
| `getLabel` | ✅ | `sync_service_status=1`，`order_status=2`（已预报）；与 create 返回一致 |
| `cancelOrder` | ✅ | `code=200` |
| `getBalance` / `getOrderInfo` / `getPrintLabel` | ⏳ | 未测 |

用户确认：账户余额仍为**负数**时上述下单/取面单/取消仍成功（与 PR#90「欠费未测」结论已过时）。

## API 主流程

```text
getToken → rates/ratesv2 → createOrder → getLabel（建议轮询）→ 可选 cancelOrder
```

关键约束（文档 + IT）：

- 发件地址须后台**备案**；Excel 的 `S0143` 等须展开为完整 `shipper_address` JSON。
- **`reference_no` 必须与 createOrder 完全一致**，否则 getLabel/cancelOrder 报「订单数据不存在」。应对齐赛狐 `packageSn`（或稳定映射）并持久化。
- IT：因跨境网络，面单/追踪号可能**异步**；建议约 **30s** 轮询 `getLabel`。PR#91 样例中 create 响应已含跟踪号与 PDF——实现上应：**先用 create 返回值，若缺则轮询 getLabel**。
- Webhook 后台可配；本地部署阶段不以 webhook 为主路径。

## 与本模块 Excel 路径对照

| | P1B Excel（现行生产主路径） | 蜴国际 API（已冒烟） |
|--|---------------------------|----------------------|
| 上传 | 人工 Excel | `createOrder` |
| 追踪号 | 返回 Excel → `lizard-import` | create 同步字段 和/或 `getLabel` |
| 面单 | 另途 PDF | create / getLabel 的 PDF URL |
| 取消 | 人工后台 | `cancelOrder` |
| 发件 | `shipper_code` | 备案地址 JSON |
| 对账键 | 客户参考号列 | `reference_no`（必须一致） |

## 接入建议（更新）

1. **Excel 闭环暂保留为生产默认**（操作习惯、批量、对账报告已稳）；API 冒烟通过 ≠ 自动切生产。
2. 下一步可开薄 **httpx client**（仿 `carriers/vite/`）：token 缓存、rates、create、getLabel 轮询、cancel；凭证仅 env；**不**把明文写入 Git。
3. `ApiCarrierAdapter`：`reference_no=packageSn`、S0143→shipper 映射表、轮询/同步双路径、Artifact 存 PDF、再进 P1C `submitToPlatform`。
4. 仍建议同事将 main 上 HANDOFF 明文 Key 改为环境变量占位并轮换。

## 相关

- main：`蜴国际-API/README.md`、`docs/api-reference.md`、`AGENT_HANDOFF.md`
- [async-label-and-webhook-2026-07-17.md](async-label-and-webhook-2026-07-17.md)
- 官方页：`http://47.106.72.196/api_doc2.html`
