---
okf: v0.1
type: Research
title: 蜴国际 API（PR #90）与现有 Excel 路径对照
description: main 合入的 蜴国际-API 文档要点；相对 P1B Excel 闭环的差异与接入门槛；不含凭证
timestamp: 2026-07-17
tags: [sellfox-shipping, lizard, api, excel]
---

# 蜴国际 API（PR #90）↔ Excel 路径

**来源：** `origin/main` 模块 `蜴国际-API/`（Merge PR **#90**，`90712b0`）。  
**本仓分支暂不合并该目录**；查文档用 main。

## 同事测试结论（文档原述）

| 接口 | 状态 |
|------|------|
| `getToken` | 可用（JWT，约 24h） |
| `ratesv2` | 可用（多产品比价） |
| `rates` | 需已备案发件地址 |
| `createOrder` / `getLabel` / `getBalance` | **账户欠费，未测** |

无独立「测试环境」；生产系统 `http://47.106.72.196/`。扣费接口尚未验证。

## API 主流程

```text
getToken → rates/ratesv2 → createOrder → getLabel（异步，建议约 30s 轮询）
```

- 业务 Header：`Authorization: {access_token}`
- Excel 的发件编码（如 **S0143**）在 API 中须展开为完整 `shipper_address`（须后台已备案）
- `reference_no` ≈ 我方参考编号（应对齐赛狐 `packageSn`）
- 计量：`weight_unit_type` 1=LBS/In、2=KG/CM

## 与本模块 Excel 路径对照

| | P1B Excel（现行） | 蜴国际 API（文档） |
|--|-------------------|-------------------|
| 上传 | 人工 Excel | `createOrder` |
| 追踪号 | 返回 Excel → `lizard-import` | `getLabel` 轮询 |
| 费用 | 返回表运费列 | `rates` / 订单结果 |
| 发件 | `shipper_code` 文本 | 完整备案地址 JSON |
| 面单 | 另途 PDF | `getLabel` / `getPrintLabel` |

## 接入建议（暂不写代码）

1. **先保持 Excel 闭环**直至 `createOrder`+`getLabel` 在有余额账户上冒烟通过。
2. 将来 `ApiCarrierAdapter`：token 缓存、地址备案映射表（S0143→完整地址）、`reference_no=packageSn`、轮询 getLabel → 本地 TrackingAssignment → 再走 P1C `submitToPlatform`。
3. **禁止**把 `蜴国际-API/AGENT_HANDOFF.md` 里的明文 token/key 拷进本模块或提交；凭证仅环境变量。若 main 上 HANDOFF 仍含明文 Key，建议另开 PR 改为占位符并轮换。

## 相关链接（文档内）

- 模块：`蜴国际-API/README.md`、`docs/api-reference.md`、`docs/quickstart.md`
- 官方页：`http://47.106.72.196/api_doc2.html`（内网/同事环境）
