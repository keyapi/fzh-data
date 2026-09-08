---
okf: v0.1
type: Log
title: parcel_track 变更日志
---

# 变更日志

## 2026-09-08
- **处理时间统一 3 营业日**：UPS / FedEx / GLS `HANDLING_DAYS=3`；假日历仍分美国联邦 vs 波兰法定。
- **workers**：`--workers N` 每家 N 路、UPS→FedEx→GLS 串行（峰值 N）。8 月 live 全量分类合计见 `docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`（无单号/买家）。
- **接入 GLS**：公开 REST（免账号）、波兰历、一格多号拆分、GLS 格内 1Z→UPS。GOFO/TikTok/USPS 仍停放。

## 2026-09-07
- **新增**: 通途混合订单分流 + 共享 classify；UPS 纳入迟发/承运延误/卡件表；当时 GLS/GOFO 停放不计丢。
