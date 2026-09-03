---
okf: v0.1
type: Index
title: ups_track — 参考文档
description: API 事实、输出字段、节点词表、错误分类、模块结构
updated: 2026-09-02
---

# ups_track — 参考文档

## UPS Track API 事实（2026 现行）

| 项 | 值 |
|----|----|
| Token | `POST https://onlinetools.ups.com/security/v1/oauth/token`，Basic auth(client_id:secret)，`grant_type=client_credentials` |
| Track | `GET https://onlinetools.ups.com/api/track/v1/details/{inquiryNumber}`，`Authorization: Bearer`，建议头 `transId` + `transactionSrc`，参数 `locale` |
| 测试 CIE | `https://wwwcie.ups.com`（token 与生产**不通用**，确定性样例数据） |
| Token TTL | `expires_in` 约 14400s；本客户端到期前 ~300s 预刷新 |

## 关键时点提取（models.py）

| 字段 | 判定 | 用途 |
|------|------|------|
| `label_created_dt` | 节点描述含 `Label Created` / `Shipper created a label` | 建标时间 |
| `actual_ship_dt` | 描述含 `We Have Your Package` / `Origin Scan` / `Shipment Received` 等的**最早**节点；否则交付单里首个非建标节点兜底 | 仓库实际交给 UPS（PB 按此付款） |
| `delivered` / `delivery_dt` | 任一节点 `status.type == "D"` 或描述含 `delivered`；取其最晚时间 | 是否已交付、交付时间 |
| `delivery_city/state/signed_by` | 交付节点 location / `deliveryInformation` | 与 shipment CSV 收货地址核对，防查错件 |

> **词表校准**：UPS 事件 status.type/code 与描述文案以真实 CIE/prod 响应为准。首次拿到凭证后，
> 跑几个已知号核对 `*_KEYWORDS`（在 [models.py](models.py)），若有出入调整即可，raw JSON 留档便于排查。

## 错误分类（client.py）

| 场景 | category | retriable |
|------|----------|-----------|
| 401 + code 250002（凭证/权限） | auth | 否 |
| 401（其它） | permission | 否 |
| 429（限流） | rate_limit | 是 |
| 5xx / 网络错误 | transport | 是 |
| 400 + code 200xxx（查无此号） | not_found | 否 |
| 400 其它 / 404 | invalid | 否 |

单号失败**不中断**批量：在 summary 的"错误"列体现，控制台给失败计数。`--resume` 续跑已失败号。

## 结构

```
ups_track/
  __init__.py     导出 UpsTrackClient / UpsTrackError / UpsTrackInfo / UpsEvent
  client.py       OAuth token（缓存+预刷新）、track()、错误分类、env 构建
  models.py       响应 → UpsTrackInfo（三时点提取、事件去重排序）
  batch.py        读清单、并发/节流/重试/局部失败隔离/resume
  cli.py          python -m ups_track.cli query …（三件套输出 + --mock）
  tests/          离线单测（mock HTTP）
```

## 对接其它模块

- 库层直接用：
  ```python
  from ups_track import UpsTrackClient
  client = UpsTrackClient.from_env()          # 或显式 client_id/secret/base_url
  with client:
      info = client.track("1Z999AA10123456784")
      print(info.delivered, info.delivery_dt, info.actual_ship_dt)
  ```
- 需要把 repo root 加入 `sys.path`（模块尚未安装成包时）。
- PB 对账 / sellfox 发货运等业务方各自 import，不共享业务状态。

## 已知边界

- UPS 官方要求生产凭证；查不到的号（无权限/超期）标记错误并保留浏览器 ups.com 兜底。
- 事件文案依赖 UPS 返回语言（默认 `locale=en_US`）。
- 国内网络访问 onlinetools.ups.com 可能需代理（`UPS_HTTP_PROXY`）。
