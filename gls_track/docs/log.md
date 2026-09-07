---
okf: v0.1
type: Log
title: gls_track 变更日志
tags: [gls, track, module, log]
---

# 变更日志

## 2026-09-07

- **新增**: gls_track 模块 + 调研文档（`docs/research/2026-09-07-gls-poland-track-feasibility.md`）。
- **公开无鉴权 REST 实证**: `rstt029`(摘要免入参) / `rstt028/{号}?postalCode=…`(全量 history) 直连 curl 200 免登录；明细钥匙=目的邮编。
- **口径修正**: `HANDLING_DAYS` 1→2（8 月迟发 147→9）；营业日从美国联邦假日改**波兰 2026 法定假日**（复核补 12/24 Wigilia）；「Amazon是否判迟」仅 Amazon/亚马逊 渠道。
- **全量验证**: loader 自动拆一格多号 → 查询单元 1187；`--workers 4` 整月 3m45s，ok 1148 / err 39(非 GLS 或查无)。
- **CLI**: `query --workers/--resume`、`monthly`(批量查+出 8-Sheet 异常表)。
- **交付物**: `gls_track/ops_report.py` FedEx 风格异常表；`D:\Work\王忠于\成本核算\通途非FBA订单202608 GLS运营异常表 20260907.xlsx`（1187 行：正常1073/查无39/承运延误30/在途24/漏发11/迟发9/卡件1）。
- **统一归属**: 多承运商统一 runner 由 Cursor 在 parcel_track(PR #215) 做；gls_track 作为 GLS adapter 接入（见 AGENT_HANDOFF 末尾）。
