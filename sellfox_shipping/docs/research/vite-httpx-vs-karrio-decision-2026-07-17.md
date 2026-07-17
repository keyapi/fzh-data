---
okf: v0.1
type: Research
title: VITE spike 决策 — httpx adapter vs Karrio custom connector
description: 基于已落地的 httpx 真测与 Karrio extension 官方成本，给出 P1/近期不实现 Karrio VITE connector 的决策记录
timestamp: 2026-07-17
tags: [sellfox-shipping, vite, karrio, httpx, decision]
---

# VITE spike 决策：httpx vs Karrio custom connector

**范围：** 仅技术决策证据；**不**切换通途生产、**不**承诺 P3 上线。  
**对照规划：** [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) §7.5 / §8.2；早期 [comprehensive-research-2026-07-15.md](comprehensive-research-2026-07-15.md)。

## 0. PR 编号澄清（2026-07-17 重读）

| PR | 实际内容 |
|----|----------|
| **#87 / #89** | `vite-api/`：VITE 文档与测试报告（**无**独立 Karrio 专章） |
| **#88** | `research/claude-strange-jones` → 合入本仓 **research-synthesis** 等；**Karrio 深度评估在此**（§7 不用 Server、无 VITE connector、spike= custom vs httpx） |

同事「昨天调研 Karrio」主要落在 **PR#88 综合调研**，不是 vite-api 目录。本决策与 #88 规划一致，并用 httpx 真测关闭 spike。

## 1. 已完成的 httpx 侧证据

| 交付物 | 说明 |
|--------|------|
| `carriers/vite/client.py` | ~90 LOC：`rate` / `create_shipment` / `get_label` |
| `tests/.../test_vite_client.py` | MockTransport 契约（含 label 数组体） |
| `scripts/vite_test_*_smoke.py` | 测试环境真测：account、三组合 rate、create+异步 getLabel、**create+cancel** |
| 异步口径 | [async-label-and-webhook-2026-07-17.md](async-label-and-webhook-2026-07-17.md) |

**真测结论（test-api）：** rate/create/getLabel/cancel 契约可用；标签异步；cancel 可用 **orderId**；取消后虚拟余额退回；Hook URL 本地阶段空置。

## 2. Karrio custom connector 成本（未实现代码）

依据官方 [Custom Carrier / Extension](https://docs.karrio.io/carriers/sdk/extension)（综合文档 `[K-EXT]`）：

- 脚手架：`Settings` / `Proxy` / `Mapper` + `providers` / `schemas` / contract tests
- 另需：schema 生成工具链、Python **≥3.11** 隔离环境、与 `karrio` core **同版本锁定**
- **无**现成 VITE/GOFO connector 可复用（`[K-SDK]` / `[K-REPO]`）→ 几乎全部映射与错误处理需自写
- 官方步骤还包含 Server OpenAPI/前端 typing 更新——本仓已明确 **不采用 Karrio Server**，这些步骤对本项目无收益

粗估：最小可用 custom connector（rate + shipment + label poll）通常 **数百～上千 LOC** + 独立依赖树，远高于当前 httpx 客户端；且异步轮询 / `requestId` 幂等 / 渠道组合仍要写在公司防腐层之外或之内各一份。

## 3. 维度对比

| 维度 | 直接 httpx（已做） | Karrio custom connector（未做） |
|------|-------------------|--------------------------------|
| 代码量（spike 范围） | ~90 LOC 客户端 + 薄脚本 | 整包 extension + schema + tests，数量级更大 |
| 依赖 | 已有 `httpx` | `karrio` + connector 包；根项目现为 ≥3.10，需隔离 ≥3.11 |
| 错误保真 | 原始 HTTP/JSON 直达；易对账官方报文 | 需映射到 `Message`；易丢 VITE 特有字段 |
| 单位 lbs/in | 调用方显式保证（文档已要求） | Karrio units 可帮换算，但仍要契约测渠道 |
| 异步 label | 公司侧轮询（与蜴国际 30s 建议同构） | Karrio 不等价「替你轮询」；仍要外层编排 |
| Webhook | 本地不接；将来公网再接 | 同样不在 connector 内解决公网 URL |
| 与领域模型 | 易挂在未来 `ApiCarrierAdapter` 后 | 多一层 Address/Parcel ↔ 公司 Package 映射 |
| 复用价值 | 仅 VITE | **无现成 VITE connector**；FedEx 等应优先官方 connector，与 VITE 无关 |
| 维护 | 跟 VITE OpenAPI 变 | 跟 VITE **且** Karrio 大版本/Mapper 接口 |

## 4. 决策（P1 / 近期）

**采用：直接 `httpx` adapter（`ViteGofoClient`）作为 VITE 技术路径。**  
**不采用（近期）：为 VITE 新建 Karrio custom connector。**  
**仍不采用：Karrio Server。**

理由（一句话）：没有可复用的 VITE connector 时，Karrio 带来的统一模型收益盖不过脚手架、版本隔离与双重映射成本；httpx 已用测试账户跑通 rate/create/getLabel。

### 何时重开 Karrio VITE connector？

仅当同时出现：

1. 多个 API 承运人已在生产走 Karrio SDK，公司防腐层已稳定；且  
2. 维护多套 httpx 客户端的成本 > 维护一个 VITE extension；且  
3. 有独立 ≥3.11 环境与版本锁定预算。

### FedEx / GLS

- **FedEx：** 将来优先评估 **官方** Karrio connector（契约测试后），不是 VITE 这条 custom 路线。  
- **GLS：** 仍按综合文档：P2 Excel 优先；API/波兰合同未验证前不绑 Karrio GLS。

## 5. P1C VITE 退出门对照

| 综合文档要求 | 状态 |
|--------------|------|
| httpx adapter | **完成**（mock + 测试环境真测） |
| Karrio 最小 custom connector | **刻意不做**（见 §4 决策） |
| 量化对比 + 决策记录 | **本文** |
| 不切换通途生产 | **遵守** |

## 相关代码 / 文档

- `sellfox_shipping/carriers/vite/`
- `sellfox_shipping/scripts/vite_test_rate_smoke.py`
- `sellfox_shipping/scripts/vite_test_shipment_label_smoke.py`
- [async-label-and-webhook-2026-07-17.md](async-label-and-webhook-2026-07-17.md)
