---
okf: v0.1
type: Index
title: 赛狐 API 文档 — 总索引
description: SELLFOX_API 模块 OKF 文档导航
tags: [sellfox, saihu, API, integration]
timestamp: 2026-07-01
---

# 赛狐 API 文档

> SELLFOX_API 模块 — 赛狐开放平台 API 文档本地镜像、连通性测试、接入经验。

## 文档地图

| 你需要... | 读这个 |
|----------|--------|
| Agent 接手总览 | [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) |
| 搜索具体 API 端点 | [api-reference/](api-reference/) — 419 个 API Markdown |
| 了解 API 接入过程 | [lessons/2026-06-25-sellfox-integration-lessons.md](lessons/2026-06-25-sellfox-integration-lessons.md) |
| 查看探索记录 | [research/2026-06-25-sellfox-api-exploration.md](research/2026-06-25-sellfox-api-exploration.md) |
| 查看 API 索引原文 | [api-reference/llms.txt](api-reference/llms.txt) |
| 查看变更历史 | [log.md](log.md) |

## API 参考文档 (api-reference/)

419 个 API 端点文档，分为 16 个模块：

- **开发指南** (14) — 认证、签名、限流、公共参数
- **商品** (16) — SKU/SPU CRUD、分类、辅料、质检
- **销售** (8) — 在线产品、退货报告、配对
- **订单** (9) — 订单列表/详情、FBM 处理
- **广告** (37) — 天/小时维度报告、SP/SB/SD 基础数据
- **FBA** (44) — 发货计划、货件 (STA)、发货单
- **采购** (25) — 采购单、退货、供应商、采购计划
- **仓库** (46) — 库存、入库/出库、加工、调拨、盘点
- **数据** (18) — 销量、产品分析、利润、标签
- **财务** (68) — 批次成本、利润报表、结算、付款
- **多平台** (115) — 销售、订单、平台仓、财务（AliExpress/eBay/Shopify/Temu/TikTok/Walmart）
- **报告中心** (10) — Amazon 原报告、赛狐报告
- **Feed** (3) — 提交 + 查询
- **客服** (1) — Review
- **工具** (1) — 打印标签
- **设置** (4) — 汇率、子账号、店铺、自定义字段

## 目录结构

```
SELLFOX_API/
├── AGENT_HANDOFF.md          ← Agent 入口
├── download_docs.py          ← 文档下载/更新脚本
├── test_api.py               ← 连通性测试
├── config.json
└── docs/                     ← OKF v0.1 bundle
    ├── index.md              ← 本文件
    ├── log.md
    ├── research/
    ├── lessons/
    └── api-reference/        ← 下载的 419 个 API .md
        ├── llms.txt
        ├── 开发指南/ (14)
        ├── 商品/    (16)
        ├── ...
```
