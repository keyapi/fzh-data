---
okf: v0.1
type: Research
title: 钉钉 DWS CLI 读取群消息的可行性（替代缺失的消息历史 API）
description: 官方 dingtalk-workspace-cli 提供 chat +chat-messages 读取群/单聊历史；需要组织开通 DWS CLI 数据访问、管理员授权应用、应用重定向 URL 含 127.0.0.1 与 login.dingtalk.com；含 NEW-API 应用报错的修复步骤与只读试跑方案
date: 2026-10-26
tags: [dingtalk, dws, cli, group-message, oauth, inventory, stockout]
---

# 钉钉 DWS CLI 读取群消息的可行性

> 结论：**有帮助，而且正好补上之前“没有群消息读取/搜索权限”的缺口。**
> 官方 `dws` CLI 的 `chat +chat-messages` 可以按群读取历史消息（支持时间范围、分页、JSON）。但需要三件事同时成立：组织开通 DWS CLI 数据访问、管理员授权的应用有消息读取 scope、应用重定向 URL 含 `http://127.0.0.1` 与 `https://login.dingtalk.com`。

## 1. 能读到什么

| 需求 | 命令 |
|---|---|
| 读某个群的历史消息 | `dws chat +chat-messages --group <群名或openConversationId> --page-all --format json` |
| 按时间范围读 | `dws chat +chat-messages --group <id> --start "2026-10-01T00:00:00+08:00" --end "2026-10-02T00:00:00+08:00" --order asc --page-all --format json` |
| 关键词/发送者检索 | `dws chat +search-msg --chat-query "盘点群" --query "断货" --page-all --format json` |
| 跨全部可见会话按时间读 | `dws chat message list-all --start <时间> --end <时间> --page-all --no-reactions` |
| 先找群/会话 | `dws chat +recent-conversations --start <时间>`；或 `+unread-chats` |
| @我的消息 | `dws chat +at-me --page-all --no-reactions` |

- 单聊用 `--user` / `--open-dingtalk-id`；群聊用 `--group`。
- 时间范围是 `[start, end)`；只给结束时间只支持 `desc`，升序必须有开始时间。
- 读取后必须检查 `complete`、`hasMore`、`stopReason`、`failures`；**达到页数上限不等于全量**。
- 非首页失败时退出码 **7**（`partial_failure`），不能把部分结果当完整。

## 2. 权限与授权（三个层次）

1. **组织级**：管理员在开发者后台开启「CLI 访问管理 / DWS CLI 数据访问」。未开启时读消息返回 `CLI_ORG_NOT_AUTHORIZED`。
2. **应用级**：`dws auth login` 使用的钉钉应用必须被管理员授权，并具备消息读取 scope（你看到的「搜索会话列表、拉取会话消息内容」就是这一类）。权限最小化，所有调用走钉钉审计链。
3. **用户级**：OAuth 登录后，**只能读当前登录用户本来就能看到的会话**；不是无差别读全公司。

登录：

```bash
dws auth login --client-id <app-key> --client-secret <app-secret>
# 无头服务器
dws auth login --device
dws auth status --format json
```

凭证首次登录后存系统 Keychain，token 自动刷新。**不要把 token / appSecret 写进脚本或日志。**

## 3. 你遇到的报错：重定向 URL

报错原文：

> 请在应用后台设置重定向 URL（回调域名），包含 `http://127.0.0.1` 和 `https://login.dingtalk.com`

这不是 NEW-API 本身的问题，而是**被添加到 DWS CLI 的那个钉钉应用**缺少 DWS 登录所需的回调地址。

**首选：新建一个专用的「企业内部应用」给 DWS CLI，不要复用 NEW-API。**
理由：`new-api-dingtalk-oidc` 用的是**第三方企业应用**（ISV），它的 AppKey/Secret 同时承担 new-api 的生产登录；改它的回调/发版有回归风险。DWS 是内部工具，单独建一个企业内部应用更干净、权限也更好收敛（只给消息读取，不给通讯录写）。

如果你仍想复用 NEW-API：

1. 打开钉钉开发者后台 → 找到你选中的 **NEW-API** 应用（AppKey 应与 `new-api-dingtalk-oidc` 部署里的 `DINGTALK_CLIENT_ID` 一致）。
2. 进入「登录与分享 / 安全设置」→「重定向 URL（回调域名）」。
3. **保留现有** OIDC 回调（`https://<你的域名>/callback`），**追加**：
   - `http://127.0.0.1`
   - `https://login.dingtalk.com`
4. 保存；如提示需要发版，创建并发布新版本；敏感权限版本可能需要 `--confirmed-sensitive` 或管理员审批。
5. 回到 DWS CLI 管理 → Agent 管理，重新「保存并添加应用」。
6. 本机执行 `dws auth login --client-id <app-key> --client-secret <app-secret>` 验证。

注意：这些重定向 URL 是**追加**，不会破坏 NEW-API 现有登录；但改的是生产登录应用，建议先在非高峰改、改完立即用 NEW-API 登录回归一次。

## 4. 两个设置够不够？

你现在的两个设置（DWS CLI 管理 + Agent 管理的消息读取权限）覆盖了**组织级和应用 scope**，但还差：

| 还缺什么 | 在哪做 |
|---|---|
| 应用的 redirect URL 含两个固定值 | 钉钉开发者后台 → 应用 → 登录与分享 |
| 应用发布/审批（含敏感 scope） | 应用版本管理 → 发布 |
| 本机/服务器的 `dws auth login` | CLI |
| `openConversationId`（群 ID） | `dws chat +recent-conversations` 或群名解析 |

「其他渠道」打开状态与 CLI 登录无关，可以不动；「千问办公」也不用管。

## 5. 建议的只读试跑

先不要接自动化，按下面顺序验证：

```bash
# 1. 安装（Windows PowerShell）
irm https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install-devapp.ps1 | iex

# 2. 登录
dws auth login --client-id <app-key> --client-secret <app-secret>
dws auth status --format json

# 3. 找盘点群
dws chat +recent-conversations --start "2026-10-01T00:00:00+08:00" --format json

# 4. 读 1 天（先小范围）
dws chat +chat-messages --group "<openConversationId>" \
  --start "2026-10-20T00:00:00+08:00" --end "2026-10-21T00:00:00+08:00" \
  --order asc --page-all --format json > messages_20261020.json

# 5. 检查完整性
#    看 complete / hasMore / stopReason / failures 是否为空
```

试跑通过后，再考虑每天 07:00 左右拉前一天的消息（只读），落到 `D:/Work/fzh-order-store` 或 EN，用于：
- 美东运营的下架/恢复通知；
- 盘点群的手工调整、报损报溢说明；
- PB/美中的无货通知，作为 `check0stock` 之外的补充证据。

## 6. 限制与风险

- GitHub README **没有**明确写“历史消息读取”命令；能力来自官方 skill 的 `message-query` 参考。**以本机实测为准。**
- 只能读**登录用户可见**的会话；换人/换 profile 结果不同。多账号时只能用唯一 `isOrgCurrent=true` 的 profile。
- 凭证存 Keychain；Windows 的 auth export/import 被拒绝，Linux/无头用 `--device`。
- Alpine/musl 不支持；二进制要 glibc 2.17（生产 CentOS 一般满足）。
- 跨组织没有默认 `--all-orgs`，要配 profile。
- 所有调用走审计链；**只读试用阶段不要发消息**（发送/撤回是另一组命令）。
- 若 DWS CLI 最终不可用，官方替代仍是「会话存档」（合规存档能力，需另行开通），不是普通群 API。

## 7. 本机只读实测（2026-10-26）

> 结论：**端到端跑通。** 安装 → 登录 → 找群 → 按天读消息 → 有界分页，全部成功；只读，未发任何消息，未改生产配置。

### 7.1 环境与安装

| 项 | 结果 |
|---|---|
| OS | Windows 11 |
| `dws version` | v1.0.66-beta.2（Build 2026-10-26T03:14:10Z，commit `894cdd4`，Edition open） |
| 安装方式 | 官方 `install-devapp.ps1`，SHA-256 校验通过 |
| 二进制 | `C:\Users\zhang\.local\bin\dws.exe`（脚本不改 PATH，不要求管理员） |
| 附带 skill | 安装脚本复制 `dingtalk-misc` skill 失败：`Skill path permissions mismatch: ...\Temp\dws-dev-*\sk\multi\dingtalk-misc != ...\.dws\skills\multi\.dws-dev-copy-*\payload`；**不影响** `dws chat +chat-messages`（shortcut 由二进制内置） |

### 7.2 授权与登录

- 管理员已在钉钉开发者后台开启「DWS CLI 管理」，Agent 管理已授权「搜索会话列表，拉取会话消息内容」。
- NEW-API 应用（AppKey 与 `new-api-dingtalk-oidc` 的 `DINGTALK_CLIENT_ID` 相同）重定向 URL 已含 `http://127.0.0.1`、`https://login.dingtalk.com` 及 OIDC 回调，并已发布新版本；在 DWS Agent 管理重新添加后成功（控制台提示可能需约 5 分钟生效，本次保存后立即登录即成功）。
- 登录命令（凭证从本机 `.env` 读取，未回显、未落仓库）：
  ```bash
  dws auth login --client-id <AppKey> --client-secret <AppSecret>
  ```
- 结果：`success=true`、`token_valid=true`、`refresh_token_valid=true`；组织「方州汇国际」，登录用户实名。token 约 2 小时过期、refresh token 约 30 天（具体时间已核验，此处不记录）。
- 登录为 OAuth Loopback：CLI 起 `127.0.0.1:9125/callback`，浏览器完成扫码授权后自动回写。**无头环境需 `--device`。**

### 7.3 实测命令与结果

**(a) 找会话**
```bash
dws chat +recent-conversations --start "2026-10-01T00:00:00+08:00" --format json
```
- exit 0；`ok=true`，`outcome=success`，`complete=true`，`count=36`，`pagesFetched=7`。
- 返回结构为包装式：`{ok, outcome, data, meta}`；`data.conversations[]` 字段：`conversationId`、`name`、`nameKnown`、`type`（group/direct）、`latestMessageTime`。
- 定位到盘点群「美国物资盘点」（`openConversationId` 以 `cidy+...` 开头），`latestMessageTime=2026-10-02T20:58:01+08:00`。

**(b) 按天读（任务指定日期 2026-10-20）**
```bash
dws chat +chat-messages --group "<openConversationId>" \
  --start "2026-10-20T00:00:00+08:00" --end "2026-10-21T00:00:00+08:00" \
  --order asc --page-all --format json
```
- exit 0；`complete=true`，`hasMore=false`，`partial=false`，`truncated=false`，`count=0`，`pagesFetched=1`，`paginationKnown=true`，`failedCount=0`，`stopReason="source_complete"`，`failures=[]`。
- 0 条是**真的空窗**：该群最后一次发言在 10-02，不是权限或分页问题。

**(c) 有消息的一天（2026-10-02，同群）**
- `count=1`，其余完整性字段同上（`complete=true`、`stopReason=source_complete`）。
- `messages[]` 字段：`conversationId`、`createTime`、`messageId`、`resourceRefs`、`sender`、`senderId`、`text`。

**(d) 通知群（2026-10-26「异常订单&库存预警推送」）**
- `count=2`，`complete=true`，`failures=[]`；字段同上（无资源引用时 `resourceRefs` 省略）。

**(e) 有界分页 / 部分结果**
```bash
dws chat +chat-messages --group "<通知群 openConversationId>" \
  --start "2026-10-01T00:00:00+08:00" --end "2026-10-27T00:00:00+08:00" \
  --order asc --page-all --page-limit 10 --max-items 25 --format json
```
- `pagesFetched=2`，`count=25`，`failedCount=0`，`failures=[]`；
- **`complete=false`、`hasMore=true`、`partial=true`、`truncated=true`、`truncatedByResultLimit=true`、`stopReason="result_limit"`**；
- `nextActions[]` 给出继续读取的游标（复用原会话目标与页大小，`start` 为下一条边界）。
- 结论：**命中 `--max-items` 时必须把结果当“部分”，不能当全量。** 与预期一致。

### 7.4 返回结构差异（实现注意）

- `+recent-conversations`：包装式 `{ok, outcome, data{complete, conversations, count, pagesFetched, rangeSemantics, ...}, meta}`。
- `+chat-messages`：**扁平 ledger**，完整性字段直接在顶层：`complete / hasMore / partial / truncated / truncatedByPageLimit / truncatedByResultLimit / count / pagesFetched / paginationKnown / failedCount / stopReason / failures / nextActions / queryRange / identityResult`。
- `queryRange.semantics = "[start,end)"`，与传入参数一致。

### 7.5 观测到的退出码与错误

- 成功均 `exit 0`。
- 本次未触发失败路径；文档所述“非首页失败退出码 7（`partial_failure`）”未实测。失败时仍以 `complete=false` + `failures[]` 兜底判断。

### 7.6 仍未做

- 未发送任何消息、未改群/机器人配置、未改生产系统。
- 未接自动化；建议下一步按天只读拉取，落库前断言 `complete && !hasMore && failures.isEmpty()`。

### 7.7 目标群实测：美国客服沟通（2026-10）

> 用户确认：**美国物资盘点不是** WX/Paula 沟通群；真正有下架/库存记录的是「美国客服沟通」（用户在其中）。

- 10/01–10/26 共 **233 条**，`complete=true`、3 页、`stopReason=source_complete`。
- **156 条可读，77 条（33%）是 SafeChat/安恒密盾加密**：`decryptCandidateCount=77`、`decryptFailedCount=77`、`decryptAllowedCount=0`、reason=`policy_disabled`。当前安装的 `dws` 为 open 版，`safechat` 子命令不存在；要解密需要 SafeChat 后端 + 企业密盾策略允许。
- 可读消息里库存相关关键词：**下架 9、库存 20、缺货 5、恢复 2、盘点 1、报溢 1**。典型内容（去标识）：
  - “亚马逊已经下架，请把通途库存调为零”；
  - “没有库存，请下架”；
  - “缺货的 SKU 用 Blue Geometry 替代，注意更新库存”；
  - “退货后再报溢出 label”；
  - “这类盘点/调整库存的信息发盘点群集中处理”（10/20 WX）。
- **关键缺口**：WX 要求把盘点/调整库存信息集中到「盘点群」，但**用户不在该群**；DWS 只能读登录用户可见的会话，所以该群目前读不到。要完整覆盖，需要把用户或专用账号拉进盘点群，或让 WX 转发/导出。
- 33% 加密 + 盘点群不可见 ⇒ **不能用“没搜到”证明“没有下架/缺货”**；只能把已读到的当正证据。

**建议顺序**：

1. 先让用户/专用账号加入「盘点群」；这是比解密更关键的覆盖面问题。
2. 如企业使用安恒密盾，找密盾管理员确认是否允许该应用解密；否则接受 67% 明文覆盖。
3. 现阶段只解析明文消息，按 `下架/库存/缺货/恢复/报溢` 做关键词 + 人工复核，**不自动当作断货标签**。
4. 原始消息只落在 `D:/Work/fzh-order-store/dingtalk/`（不入公开仓库）；仓库只记录方法、聚合数和限制。

## 8. 来源

- [DingTalk-Real-AI/dingtalk-workspace-cli（官方仓库）](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli)
- [message-query：消息读取、搜索与查询](https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/refs/heads/main/skills/multi/dingtalk-chat/references/chat/message-query.md)
- [dingtalk-chat SKILL.md](https://github.com/dingtalk-real-ai/dingtalk-workspace-cli/blob/92c4f8c355c749ec470c68f998d862a00d7d1709/skills/multi/dingtalk-chat/SKILL.md)
- [devapp-agent-install-guide.md](https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/docs/devapp-agent-install-guide.md)
- [capability-limits.md](https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/skills/multi/dingtalk-shared/references/capability-limits.md)
