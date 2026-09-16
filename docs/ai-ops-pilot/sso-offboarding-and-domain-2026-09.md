---
okf: v0.1
type: Research
title: ChatGPT Business 的 SSO、域名验证与离职回收
description: Business 是否支持 SAML SSO、IdP 停用能否切断 ChatGPT 访问、verified domain / claimed domain 到底给了什么、SCIM 为何缺失，以及「SSO 能不能像钉钉那样一键断权」的准确答案
tags: [ai-pilot, chatgpt-business, sso, saml, scim, offboarding, domain-verification, identity]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/11489188-setting-up-single-sign-on-sso-for-chatgpt-business
  - https://help.openai.com/en/articles/9534785-single-sign-on-sso-setup-for-openai-products
  - https://help.openai.com/en/articles/8871611-verifying-your-domain-for-openai-identity
  - https://help.openai.com/en/articles/9047883-getting-started-with-openai-identity-and-access-for-managed-workspaces
  - https://help.openai.com/en/articles/10011769-scim-provisioning-and-management
  - https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business
  - https://help.openai.com/en/articles/10479654-onboarding-employees-with-existing-chatgpt-accounts
  - https://help.openai.com/en/articles/8266418-data-retention-when-a-member-is-removed-from-a-workspace
  - https://help.openai.com/en/articles/10489721-troubleshooting-sso-workspace-access-and-domain-verification
  - https://help.openai.com/en/articles/20001257-managing-active-sessions-in-chatgpt
  - https://learn.chatgpt.com/docs/enterprise/user-lifecycle.md
  - https://learn.chatgpt.com/docs/enterprise/groups-and-provisioning.md
  - https://openai.com/business/pricing/
---

# ChatGPT Business 的 SSO、域名验证与离职回收

> 调研日期：2026-09-16。起因：公司准备买 ChatGPT Business（2 席位），核心顾虑是员工离职没法干净断权——「能不能像 new-api 的钉钉 SSO 那样，在 IdP 里停用就完了？」

## 一句话结论

**不能。** Business 支持 SAML/OIDC SSO，但 **SSO 只管「怎么登录」，不管「谁是成员」**。IdP 里停用只能挡住下次登录；要真正断权，仍必须进 ChatGPT 后台手动移除成员（并单独处理席位计费）。Business 没有 SCIM，没有自动离职回收。

## 1. SAML SSO：支持

> "SSO and domain verification are included with ChatGPT Business. Business supports Security Assertion Markup Language (SAML) and OpenID Connect (OIDC)."
> — [help/11489188](https://help.openai.com/en/articles/11489188-setting-up-single-sign-on-sso-for-chatgpt-business)

官方定价对比表 Security & Administration 分组：`SAML SSO` Business = Yes，Enterprise = Yes。Business 卡片文案："Secure workspace with SAML, SSO, and MFA"
— [openai.com/business/pricing/](https://openai.com/business/pricing/)

**支持哪些 IdP：官方没有固定清单。** 设置流程里是「按 UI 里出现的选项选」：

> "Choose one of the providers shown, such as **Okta**, **Entra**, or **Custom SAML** when available. If your provider is not listed, select **Custom SAML** when offered; an existing configuration may also offer **Custom OIDC**."
> — [help/9534785](https://help.openai.com/en/articles/9534785-single-sign-on-sso-setup-for-openai-products)

即：Okta / Entra 有原生磁贴，其余走 Custom SAML 或 Custom OIDC。SCIM 文档另有一份更长的集成商名单（Okta、Microsoft Entra ID、Google Workspace、PingFederate、OneLogin、Rippling），但**那是 SCIM 的名单，不是 Business SSO 的名单**——Business 用不到 SCIM，不要据此推断 Google Workspace 在 Business SSO 里是原生选项。Google Workspace 在 Business SSO 下是否原生可选：**未核实**（大概率能通过 Custom SAML/OIDC 接）。

## 2. IdP 停用之后会发生什么

### 挡得住「下次登录」

若工作区把 SSO 策略设为 **Required**，该策略只覆盖**已验证域名下的成员**：

> "**Required** SSO applies to members whose email address uses a verified domain covered by the workspace policy. Invited members from other domains may still use another permitted sign-in method."

对应的报错也印证了这点（被要求用 SSO 的账号再用密码/社交登录会被拒）：

> "**require_sso_login** — The selected workspace requires SSO, but the sign-in attempt used another method."
> "**Oops! Please use your organization's SSO to access your account** — The workspace requires SSO, but the user attempted to sign in with a password or social sign-in provider."
> — [help/10489721](https://help.openai.com/en/articles/10489721-troubleshooting-sso-workspace-access-and-domain-verification)

### 挡不住「已有会话」，也挡不住「成员身份」

SSO 与成员管理是两条独立轨道：

> "SSO controls how someone signs in; it does not invite them to your workspace or grant access to another ChatGPT workspace, an API organization, or an Ads account. **Workspace owners or admins must manage invitations, members, and available seats separately in ChatGPT.**"
> — [help/11489188](https://help.openai.com/en/articles/11489188-setting-up-single-sign-on-sso-for-chatgpt-business)

最直白的一句在入职文档里：

> "**A user added to the workspace can consume a seat even if their identity-provider access prevents sign-in.**"
> — [help/10479654](https://help.openai.com/en/articles/10479654-onboarding-employees-with-existing-chatgpt-accounts)

也就是说：IdP 停用 = 挡住登录；**成员仍在工作区、席位仍被占用**。

### 会话本身

- 文档只提到「改策略会踢人下线」：`"Changing a ChatGPT policy to Required or Off can sign out affected users."`——**这句话说的是改 SSO 策略，不是 IdP 停用**。
- 自助踢会话的功能对 SSO 账号**明确不可用**：
  > "**Active sessions** ... is not available for accounts linked to an organization's SSO sign-in, including SAML or OIDC. This can apply even if your organization does not require SSO for every sign-in, or if you used another sign-in method for your current session."
  > — [help/20001257](https://help.openai.com/en/articles/20001257-managing-active-sessions-in-chatgpt)
- **IdP 停用后，浏览器里已存在的 ChatGPT 会话多久失效：官方无任何说明。未核实。** 不要把「停用 IdP」当成即时断权手段。

### 真正的即时断权动作（文档保证）

> "Removing a member ends their workspace access immediately, but will not remove their ChatGPT seat from the workspace's billable seat count. To stop being billed for the seat starting with your next billing cycle, a workspace owner must remove it."
> — [help/8542216](https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business)

> "When a member is removed from a ChatGPT workspace, their access to that workspace is revoked immediately."
> — [help/8266418](https://help.openai.com/en/articles/8266418-data-retention-when-a-member-is-removed-from-a-workspace)

## 3. 域名验证 ≠ 认领域名

**Business 可以做域名验证**（定价表 `Domain verification` Business = Yes），但它的作用被写得很克制：

> "Domain verification confirms that your company or institution controls an email domain. A verified domain can support your tenant's identity settings and single sign-on (SSO)."
> "**Verifying a domain does not automatically enable SSO, invite users, configure SCIM, or give someone access to a ChatGPT workspace, API Platform organization, or Ads account.**"
> "Verifying a work domain does not delete an existing personal ChatGPT workspace or merge its chats."
> — [help/8871611](https://help.openai.com/en/articles/8871611-verifying-your-domain-for-openai-identity)

**关键：文档明确区分「验证」和「认领」，且认领是审批制功能，不是 Business 的常规能力：**

> "**Domain verification and domain claiming are different. Verifying a domain does not claim it. Domain claiming is available only for approved use cases and requires a separate request through OpenAI Support or your account team.**"

所以「公司验证了域名后，员工就不能用公司邮箱开个人号了」——**这个效果在 Business 上不成立**。域名验证反而会限制自助改邮箱：

> "Verifying a company or school domain can restrict self-service account-email changes."

Business 唯一与「把员工引到工作区」相关的机制是 **Workspace discovery**（Business 默认开启，Enterprise 默认关闭）：

> "Workspace discovery helps people at your company find and join your ChatGPT workspace using a verified email address on your domain."
> — [help/8542216](https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business)

但它是**邀请加入**方向（可从「需审批」调成「自动接受」），不是「禁止在别处用公司邮箱」。此外 Business admin **无权强制**员工合并/删除个人工作区：`"ChatGPT Business admins cannot require someone to merge or delete a personal workspace."`

## 4. Business 不含什么

> "**A standalone ChatGPT Business plan does not include SCIM, synchronized groups, or automatic directory provisioning.**"
> — [help/11489188](https://help.openai.com/en/articles/11489188-setting-up-single-sign-on-sso-for-chatgpt-business)

SCIM 文档的适用范围表把 Business 直接归为不可用：

| SCIM scope | Eligible products or plans |
| --- | --- |
| **Not available** | **Standalone ChatGPT Business** and ChatGPT for Teachers plans; use another supported onboarding method. |

> "A standalone ChatGPT Business plan and ChatGPT for Teachers do not include SCIM."
> — [help/10011769](https://help.openai.com/en/articles/10011769-scim-provisioning-and-management)

生命周期文档的能力表同样：

| Capability | Supported workspace plans |
| --- | --- |
| Directory synchronization through SCIM | ChatGPT Enterprise, Edu, and Healthcare |
| Custom roles and role-based access control | ChatGPT Enterprise, Edu, Healthcare, and Teachers |
| Codex access tokens | ChatGPT Business and Enterprise |
| — [learn.chatgpt.com/docs/enterprise/user-lifecycle.md](https://learn.chatgpt.com/docs/enterprise/user-lifecycle.md)

定价对比表另确认：`SCIM` Brain No / Enterprise Yes；`Global admin console` Business No；`Role-based access controls` Business No。

**实际含义**：Business 的成员增删**只能在 ChatGPT 后台手动做**（`Workspace settings > Members`）。没有「IdP 组 → 工作区」的自动同步，也没有离职自动回收。

> 注：搜索引擎缓存的旧版 11489188 曾有一句 "No SCIM / AD group sync on the Business plan, so all user provisioning and de-provisioning is manual."。**现行版本已改成上引措辞**，该旧引文不再出现在官方页面，勿引用。

## 5. 实操答案：离职流程

「IdP 停用 → 完事」**不成立**。Business + SSO + 域名验证下，最小完整离职清单是：

| # | 动作 | 在哪做 | 依据 |
|---|------|--------|------|
| 1 | 停用/移出 IdP 应用（挡住后续登录） | 钉钉 / Entra | help/9534785 |
| 2 | **手动移除成员**「Remove member」（真正即时断权） | ChatGPT `Workspace settings > Members` | help/8542216 / 8266418 |
| 3 | **手动释放付费席位**（否则继续计费） | `Workspace settings > Members > Manage seats` | help/8542216 |
| 4 | 吊销该人的 **Codex access token** | `chatgpt.com/admin/access-tokens` | learn.chatgpt.com user-lifecycle |
| 5 | 逐个断开外部系统（Slack / GitHub / Google Drive / 插件） | 各自系统 | learn.chatgpt.com user-lifecycle |
| 6 | 交接 Projects / GPTs 所有权 | 自动归 workspace owner | help/8266418 |

### 关于「要不要改密码」

- **纯 SSO 账号本来就没有 OpenAI 密码可改**：`"If the account was created through an identity provider or social sign-in method such as Google, Microsoft, or Apple, there may be no OpenAI password to reset."`（help/10489721）
- 但**员工用公司邮箱注册过的个人账号是员工的个人资产**，Business admin 无权要求合并或删除；那部分访问不随公司工作区回收。要不要协作处理由公司政策决定，OpenAI 侧不提供强制手段。
- 因此「改密码」这个担忧**基本可以放下**——真正的缺口不在密码，而在**必须手点的第 2、3 步**。

### Codex token 是容易漏的一块

> "Removing local Codex permission **suspends** existing tokens but **doesn't revoke** them. Those tokens can work again if a workspace owner restores the permission, so explicitly revoke credentials that must lose access permanently."
> — [learn.chatgpt.com/docs/enterprise/user-lifecycle.md](https://learn.chatgpt.com/docs/enterprise/user-lifecycle.md)

## 6. 与钉钉 SSO 的差距（正面回答老板）

| 能力 | new-api + 钉钉 SSO | ChatGPT Business |
|------|-------------------|------------------|
| IdP 停用 = 断权 | ✅ | ❌ 只挡登录，成员与席位还在 |
| 自动回收（SCIM） | ✅ | ❌ 无，需 Enterprise |
| 管理员踢会话 | ✅ | ❌ 无对应功能；SSO 账号连 Active sessions 都不可见 |
| 改密码 | ✅ | ✅ **但不需要**（SSO 账号无密码） |
| 离职要手点几步 | 0 | **2 步（移除成员 + 释放席位）+ token/外部系统若干** |

**权衡**：如果「IdP 一键断权」是硬需求，唯一官方路径是 **Enterprise（含 SCIM + 全局管理台）**，代价是联系销售、至少要谈合同与席位量。Business 的 2 席位场景下，离职回收靠的是「一份 SOP + 一个记得去做的人」，量小（1–2 人）时完全可接受，量一大就会漏。

## 待核实清单

1. **IdP 停用后已存在会话的存活时长**——官方无说明。
2. **Google Workspace 是否能作为 Business SSO 的原生选项**（非 Custom SAML）。
3. 个人账号（曾用密码注册）在加入 SSO 工作区后，是否仍保留独立密码登录路径。
