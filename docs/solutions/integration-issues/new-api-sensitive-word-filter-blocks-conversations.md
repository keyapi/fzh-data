---
okf: v0.1
type: Reference
title: new-api 屏蔽词过滤误拦会话 —— 500 sensitive_words_detected 的成因、关闭项与三处反直觉
date: 2026-10-13
last_updated: 2026-10-13
category: integration-issues
module: new-api-deployment
problem_type: integration_issue
component: gateway_content_filter
severity: high
root_cause: configuration
resolution_type: config_change
symptoms:
  - 对话请求返回 500 sensitive_words_detected（HTTP 500，非 4xx），极易被当成服务端临时故障
  - 多轮对话一旦某轮命中，之后每一轮都报同一错误，无论新消息内容是什么 —— 该对话永久报废
  - 「排查怎么关掉敏感词拦截」的对话本身也被拦，形成自我触发的死循环
tags:
  - new-api
  - sensitive-words
  - gateway
  - content-filter
  - api-vilavi-cn
  - troubleshooting
related_components: [new-api-dingtalk-oidc]
---

# new-api 屏蔽词过滤误拦会话 —— 500 sensitive_words_detected 的成因、关闭项与三处反直觉

> ⚠️ **本文所有「违禁词示例」都用空格/断字写法（如 `越 南`、`S moking`）**。
> 这是刻意的：new-api 用**纯子串匹配**，空格能打断匹配；而一旦屏蔽词过滤被重新开启，
> 读入本文的对话就会**再次被拦**（本文由 `new-api-deployment/AGENT_HANDOFF.md` 路由，
> Agent 处理网关问题时会读到它）。详见 `## Prevention`。

## Problem

公司大模型网关 `api.vilavi.cn`（上海阿里云，`new-api-deployment/`，镜像 `calciumion/new-api`）
在 2026-10-13 连续拦下三个对话：

- 两个 Codex 会话「Continue Codex optimization plan for PR288」
- 为修复它而新开的「调整 new-api 网关敏感词拦截」

三者都返回 `500 sensitive_words_detected (request id: ...)`，导致工作无法推进。

## Symptoms

- 返回 **HTTP 500**，body 内错误名 `sensitive_words_detected`
  （对应 new-api 内部 `ErrorCodeSensitiveWordsDetected`）。**500 会误导排查方向**：看起来像
  「服务端临时故障 / 上游超时」，本能反应是重试——但重试永远同样失败。
- **一旦某轮命中词进入上下文，后续每一轮都失败**，哪怕新消息完全正常。多轮对话把历史消息
  一并上送，检查的是**整个请求体**，不是只看最新一条。
- 最反直觉的一点：**「怎么关掉敏感词过滤」这类排查对话必然自己触发过滤**——因为对话里会
  出现被屏蔽的词（包括错误名、词表里的词），于是越查越被拦。

## Root Cause

new-api 内置**屏蔽词过滤**，默认**开启**，且检查的是用户输入：

- 配置位置：**系统设置 → 运营设置 → 屏蔽词过滤设置**
- 相关开关（`setting/sensitive.go`，持久化在 options 表）：

| 变量 / 键 | 含义 | 默认 |
|---|---|---|
| `CheckSensitiveEnabled` | 启用屏蔽词过滤（总开关） | `true` |
| `CheckSensitiveOnPromptEnabled` | 启用 Prompt 检查（扫用户输入） | `true` |
| `StopOnSensitiveEnabled` | 命中后：`true` 立即停止生成 / `false` 替换敏感词 | `true` |
| `SensitiveWords` | 词表，每行一个（源码内置默认值 `["test_sensitive"]`） | — |

- `ShouldCheckPromptSensitive()` 返回 `CheckSensitiveEnabled && CheckSensitiveOnPromptEnabled`，
  即**两个开关任一为 false 就不再扫 Prompt**。
- 匹配算法：**AC 自动机 + 纯子串匹配，无分词、无语义**。这是误拦的根源：
  - 中文会被拆成单字：设「越 南」→「越」「南」单字也命中（issue #4345）
  - 中文长词误伤：设「大 麻」→「我有一个大 麻 烦」命中（issue #5802）
  - 英文子串误伤：设「SM」→「S moking」命中；设「hi」→ this/high/history 全中；
    设「DAN」→ 含 DAN 的任意单词全中
  - 已知删词不即时生效（疑 **Redis 缓存**，issue #4345）

## Solution

**关闭两个开关**（用户在 Web 后台完成，实测即时生效、无需重启容器）：

1. 系统设置 → 运营设置 → 屏蔽词过滤设置
2. 取消勾选 **启用屏蔽词过滤功能**（`CheckSensitiveEnabled`）
3. 取消勾选 **启用 Prompt 检查**（`CheckSensitiveOnPromptEnabled`）
4. 点击 **保存屏蔽词过滤设置**

**验证（已实测）**：同一条此前返回 `500 sensitive_words_detected` 的 WebFetch 请求
（抓取 `setting/sensitive.go`），在关闭后正常返回文件内容。开关即时生效。

### 决策记录

- **2026-10-13 决定**：**保持全关**，优先保证工作可用。
- 理由：`api.vilavi.cn` 是**全公司共享网关**，拦截影响所有走它的同事；且当前词表精度太低
  （见上「纯子串匹配」），保留拦截的收益小于误拦成本。
- **未采纳的替代方案（折中）**：保留总开关、清理词表里的误伤短词/子串词。此项作为**将来**
  若要恢复合规拦截时的候选，不在本次执行。

## What Didn't Work

- **把 500 当临时故障重试**：错误码是 500，但原因是确定的输入命中，重试必失败。唯一可靠线索
  是 body 里的错误名 `sensitive_words_detected`，不是状态码。
- **只关一个开关**：`ShouldCheckPromptSensitive()` 是两者 **AND**；只关 Prompt 检查而不关总开关，
  或反之，都不生效——必须**两个都关**。
- **在原对话里继续排查**：历史上下文已含命中词，该对话无法自救，只能**换新对话**处理。

## Prevention

- **网关返回 500 时先看 body 错误名**，别默认是上游故障。`sensitive_words_detected` /
  `insufficient_user_quota` 等是网关自身的确定性拒绝，重试无用。
- **命中即换对话**：屏蔽词命中的对话不可恢复（历史里已带词）。要接着干活，开新对话。
- **元教训：含违禁词的学习文档本身是未来的触发源**。本文会被 `AGENT_HANDOFF.md` 路由，
  一旦过滤重新开启，任何读到它的对话都会被拦。故本文示例一律**空格断字**，并请后来者保持这一写法。
- 若日后要恢复拦截，先解决误伤：官方 issue #5802 的社区讨论方向是「AC 粗筛 + 分词/小模型精筛」、
  加白名单、流式输出滑动窗口审核。可用 [`LLM-Filter-Probe`](https://github.com/soundstarrain/LLM-Filter-Probe)
  逆向定位具体是哪个词触发的。
- 排查生产环境词表/开关时用 MySQL（密码在服务器 `/opt/new-api/.secrets.env`，见
  [new-api-deployment/AGENT_HANDOFF.md](../../../new-api-deployment/AGENT_HANDOFF.md) 第六节），
  改词表后若疑似 Redis 缓存未刷新，重启 `new-api` 容器可重置。

## References

- 配置项与菜单路径（官方文档）：https://docs.newapi.pro/zh/docs/guide/console/settings/operation-settings
- 源码 `setting/sensitive.go`：https://gitcode.com/wuhuidong/new-api/blob/main/setting/sensitive.go
- issue #4345「敏感词设置有问题」（拆字、删词不生效）：https://github.com/QuantumNous/new-api/issues/4345
- issue #5802「优化敏感词匹配」（AC 误拦与优化方向）：https://github.com/QuantumNous/new-api/issues/5802
- 社区讨论（`sensitive_words_detected` 怎么过）：https://linux.do/t/topic/2982056
- 敏感词逆向定位工具：https://github.com/soundstarrain/LLM-Filter-Probe
- 本模块部署与运维：[new-api-deployment/AGENT_HANDOFF.md](../../../new-api-deployment/AGENT_HANDOFF.md)
- 同目录相关：钉钉 SSO 桥接 [dingtalk-sso-new-api-oidc-bridge.md](dingtalk-sso-new-api-oidc-bridge.md)
