---
okf: v0.1
type: Reference
title: Amazon SP-API 开发者模型 — 2026年6月
description: SP-API 私人 vs 公共开发者、自主授权 vs OAuth、SPN认证、多账号管理权限
tags: [amazon, SP-API, developer, OAuth, authorization, SPN, multi-account]
timestamp: 2026-06-24
---

# Amazon SP-API 开发者授权模型

> 何时读: 需要理解 Amazon API 权限体系、决定自建 vs 用 ERP、评估多账号管理合规性时。

## 1. 开发者类型

### 私人开发者（Private Developer）

| 要求 | 详情 |
|------|------|
| 账户类型 | 必须有 **专业销售账户**（个人账户不符合条件） |
| 授权方式 | **自主授权** — 仅自己的卖家账户可授权该应用 |
| 应用商店列表 | 不列出 |
| 需要 OAuth？ | ❌ 不需要 |
| 需要网站？ | ❌ 不需要 |
| 授权上限 | **10 个自主授权** |
| 费用（2026） | 对自己账户免费（费用已取消） |
| 用例 | 为自己的业务构建工具的卖家 |

来源: [SP-API 注册概述](https://developer-docs.amazon.com/sp-api/docs/sp-api-registration-overview)

### 公共开发者（Public Developer）

| 要求 | 详情 |
|------|------|
| 账户类型 | 任何类型均可申请，但必须注册为公共开发者 |
| 授权方式 | **OAuth 2.0** — 每个卖家必须明确授权 |
| 应用商店列表 | **必须** 在 SP 合作伙伴应用商店中列出 |
| 需要 OAuth？ | ✅ 必须 — 构建完整 OAuth 工作流 |
| 需要网站？ | ✅ 必须 — HTTPS + 隐私政策 + 服务条款 |
| 授权上限 | 25（未上架）/ 无限（上架后） |
| 审核流程 | 更严格（商业验证 + 数据安全评估） |
| 用例 | 为多个卖家构建应用的第三方 SaaS 提供商 |

来源: [注册为公共 SP-API 开发者](https://developer-docs.amazon.com/sp-api/docs/register-as-a-public-developer)

---

## 2. 自主授权 vs OAuth 第三方授权

### 自主授权（私人应用）

- 在卖家中心直接点击"授权" — **无浏览器重定向、无 OAuth**
- 实现工作量为零
- 上限 10 个授权
- 续期仅需添加新角色时

### OAuth 第三方授权（公共应用）

1. 开发者生成 OAuth URL → 卖家在 Amazon 官方页面登录
2. 卖家看到权限范围 → 点击"确认"
3. Amazon 发送授权码 → 开发者换取 refresh_token
4. 年度续期必需（365 天过期）

来源: [授权应用文档](https://developer-docs.amazon.com/sp-api/docs/authorizing-selling-partner-api-applications)、[第六步：设置授权工作流](https://developer-docs.amazon.com/sp-api/docs/onboarding-step-6-set-up-the-authorization-workflow)

---

## 3. 一个开发者应用能否管理多个卖家账号？

**可以。** 这是 SP-API 的设计模式。

```
一个开发者应用（1 个 Client ID + 1 个 Client Secret）
    ├── 卖家账户 A → refresh_token_A
    ├── 卖家账户 B → refresh_token_B
    └── 卖家账户 C → refresh_token_C
```

每个授权产生**唯一的 refresh_token**。运行时使用对应的 token 调用 API，数据完全隔离。

**10 个自主授权限制**: 指通过"自主授权"流程的总次数上限。如果需要超过 10 个，必须升级为公共应用 + OAuth。

来源: [教程：单一应用授权多个供应商账户](https://developer-docs.amazon.com/sp-api/docs/tutorial-use-a-single-sp-api-application-to-authorize-multiple-vendor-central-accounts)、[GitHub Issue #4301](https://github.com/amzn/selling-partner-api-models/issues/4301)

---

## 4. SPN 认证

### 是否需要 SPN？

| 场景 | 需要 SPN？ |
|------|-----------|
| 管理自己组织的多账号 | ❌ 不需要 |
| 在 SPN 市场列出服务 | ✅ 需要 |
| 使用完整广告 API | ✅ 推荐（SPN 认证解锁完整功能） |
| 提供品牌注册服务 | ✅ 必需（2026年起） |
| 通过 API 访问卖家数据 | ❌ 不需要（SP-API 注册即可） |

### SPN 四大审核支柱

1. **合规记录** — 无严重政策违规
2. **专业能力** — 持有 Amazon 官方培训认证的团队成员
3. **服务质量** — 建立的客户支持流程和透明的数据报告
4. **验证案例** — 可验证的店铺增长案例

来源: [Amazon SPN 服务提供商](https://gs.amazon.cn/zhishi/article-260309-5)

---

## 5. ERP 授权流程（赛狐/领星 等）

### 技术流程

```
Step 1: 卖家在 ERP 点击"授权店铺"
Step 2: 浏览器重定向到 sellercentral.amazon.com 官方 OAuth 页面
Step 3: 卖家用自己的凭据登录（从紫鸟/独立 IP）
Step 4: Amazon 显示请求的权限范围 → 卖家点击"确认"
Step 5: Amazon 发送授权码到 ERP 的注册回调 URI
Step 6: ERP 用授权码 + Client ID + Client Secret 换取 refresh_token
Step 7: ERP 安全存储 refresh_token，映射到该卖家
Step 8: ERP 现在可通过 refresh_token 调用 SP-API
```

### 为什么第一次授权必须在紫鸟/独立 IP？

- Amazon 的 OAuth 页面在浏览器中运行 — 受全部 137+ 指纹检测
- 如果两个不同账号从同一 IP/浏览器授权，会产生强关联信号
- 授权完成后，后续 API 调用不再涉及浏览器指纹

### 此流程对任何注册公共开发者都可用

不需要 SPN 认证即可显示 OAuth 页面。但未上架的公共应用上限 25 次授权。

来源: [领星帮助-初始化](https://www.lingxing.com/help/article/systemInitialization)、[SP-API 合规对接](https://post.smzdm.com/p/agg6z3ew/)

---

## 6. 对我们团队的实践指南

### 当前情况
- 多个 Amazon 账号（US/EU/JP...），不同法律实体，同一公司控制
- 已在使用赛狐 ERP（SPN 认证，2023年8月）
- 已开通赛狐 OpenAPI
- 技术团队有能力自行开发

### 推荐路径

**阶段 1: 通过赛狐 API（当前）**
- 安全：赛狐 SPN 认证，零关联风险
- 成本：已在付费使用
- 适合：分析、报表、AI 辅助决策

**阶段 2: 如需完整广告写操作 → 注册私人 SP-API 开发者**
- 用自己的专业卖家账号注册
- 私人应用 + 自主授权（上限 10 个账号）
- 自己处理 OAuth token 管理和 DPP 合规
- 不需要 SPN 认证（内部使用）
- 总费用: **免费**（2026年5月费用取消后）

**阶段 3: 如需服务外部卖家 → 公共开发者 + SPN**
- 注册公共开发者
- 构建 OAuth 工作流 + 公共网站
- 申请 SPN 认证获取完整广告 API
- 长期投入，目前不需要

---

## See also
- [多账号防关联安全](2026-security-multi-account.md)
- [赛狐 API 实践指南](2026-sellfox-api-guide.md)
- [2026 策略框架](2026-strategy-frameworks.md)
