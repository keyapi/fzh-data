---
okf: v0.1
type: Reference
title: 赛狐 OpenAPI 实践指南 — 2026年6月
description: 赛狐 API 接入信息、认证方式、可用端点、Sellfox MCP 评估、与直接 SP-API 对比
tags: [amazon, advertising, sellfox, saihu, API, MCP, openapi]
timestamp: 2026-06-24
---

# 赛狐 OpenAPI 实践指南

> 何时读: 需要调用赛狐 API、部署 Sellfox MCP、评估 API 能力边界时。

## 1. 接入信息

| 项目 | 值 |
|------|-----|
| API 文档 | `https://sellfoxapi.apifox.cn/`（Apifox 密码保护） |
| 生产环境 | `https://openapi.sellfox.com/` |
| 认证方式 | OAuth 2.0（App ID + App Secret） |
| IP 白名单 | 需联系客户经理配置 |
| 开放对象 | 企业版/旗舰版用户 |

## 2. 已知 API 覆盖范围

基于调研确认（来源: [sellfox-mcp 工具清单](https://github.com/shuolol/sellfox-mcp)、[赛狐 API 公告](https://www.52by.com/article/114738)）：

| 模块 | 接口数 | 说明 |
|------|--------|------|
| 销售与订单 | ~7 | 销量、订单、退货、在线产品 |
| **广告管理** | **35+** | SP/SB/SD 广告活动、广告组、关键词、搜索词、商品定位、小时报告 |
| 财务利润 | ~10 | 结算利润、成本、利润报告 |
| 库存与 FBA | ~6 | FBA 库存、本地库存、库存流水 |
| 客户评论 | ~1 | 评论详情、星级过滤 |
| 系统工具 | ~2 | 店铺列表、健康检查 |
| **总计** | **60-70** | |

### 广告 API 详情（35+ 接口）

- **基础广告数据**（19 个）: SP/SB/SD 的 campaign、ad group、product、keyword、targeting、negative keyword
- **小时级报告**（13 个）: SP/SB/SD 的 campaign/ad group/product/placement 级别小时数据
- **自定义报告**（4 个）: 创建报告任务 → 查询进度 → 下载解析
- **ABA 搜索词**: Amazon Brand Analytics 搜索词报告

## 3. Sellfox MCP Server

### 基本信息

| 项目 | 值 |
|------|-----|
| 仓库 | https://github.com/shuolol/sellfox-mcp |
| Stars | 2 |
| Commits | 7 |
| 作者 | shuolol（独立开发者，与赛狐无关） |
| 许可 | MIT |
| 技术栈 | TypeScript + Node.js 22 + MCP SDK + Zod v4 + SQLite |
| 与赛狐关系 | **第三方/社区项目**，非官方 |

### 评估

| 维度 | 评价 |
|------|------|
| 功能完整度 | ⭐⭐⭐⭐ 70+ 工具，65% 广告相关 |
| 代码质量 | ⭐⭐⭐⭐ 架构清晰，分层合理 |
| 生产就绪度 | ⭐⭐ 2 星、7 提交、无测试、无 CI/CD |
| 社区活跃度 | ⭐ 单人项目，无社区 |
| 风险等级 | 中高 — bus factor=1，无商业支持 |

### 部署方式

```bash
git clone https://github.com/shuolol/sellfox-mcp sellfox-mcp-node
cd sellfox-mcp-node
npm install && npm run build
cp .env.example .env
# 编辑 .env: SELLFOX_CLIENT_ID, SELLFOX_CLIENT_SECRET
npm run dev:http  # localhost:3100
```

Claude Desktop 配置:
```json
{
  "mcpServers": {
    "Sellfox MCP": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:3100/mcp?key=你的API_KEY",
      "name": "Sellfox MCP"
    }
  }
}
```

### 使用建议

- ✅ 可用于 Claude 自然语言查询赛狐数据
- ✅ 广告查询功能完整（35+ 工具）
- ⚠️ 不建议作为生产核心依赖
- ⚠️ 建议先验证 API 原生连通性，再部署 MCP 作为增强层

## 4. 赛狐 API vs 直接 SP-API

| 维度 | 赛狐 API | 直接 SP-API |
|------|---------|------------|
| 安全性 | 最高（SPN 认证） | 中高（需自行合规） |
| 开发者注册 | 不需要 | 需注册 SP-API 开发者 |
| OAuth 管理 | 赛狐处理 | 自己处理 |
| DPP/AUP 合规 | 赛狐承担 | 自己承担 |
| 广告写操作 | 需确认 | 完整（通过 Ads API） |
| 费用 | 含在赛狐订阅中 | 免费（2026年5月后） |
| API 数量 | 60-70 | 完整 SP-API + Ads API |
| 数据刷新 | 取决于赛狐同步频率 | 实时/近实时 |
| 适用于 | 分析优先，快速启动 | 完整广告管理，自动化执行 |

## 5. 待确认事项

- [ ] 广告 API 是否支持**写操作**（创建/修改 campaign、调整出价、添加关键词）
- [ ] 历史数据可回溯天数（SP 约 90 天？SB/SD 约 60 天？）
- [ ] 数据刷新频率（小时级？分钟级？）
- [ ] API 速率限制（QPS 上限？）
- [ ] 赛狐是否会保存超过亚马逊 60 天窗口的历史数据

## See also
- [SP-API 开发者模型](2026-sp-api-developer-model.md)
- [多账号防关联安全](2026-security-multi-account.md)
- [API 与数据基础设施](2026-api-data-ecosystem.md)
- [工具对比](2026-tools-comparison.md)
