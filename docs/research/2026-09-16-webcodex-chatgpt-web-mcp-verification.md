---
okf: v0.1
type: Research
title: "webcodex" 核实 — ChatGPT 网页版 + MCP 驱动本地 runner，是否绕过 5 小时额度
description: 确认存在多个同名项目；最匹配的是 miuuyy/codex-chatgpt-web（7.6k star）与 yyjeqhc/webcodex（890 star）。5 小时限制不是被"绕过"而是把工作挪到 ChatGPT Web 独立额度桶；浏览器自动化违反 OpenAI ToS 第 30–37 行，社区有封号报告但均为轶事级
---

# "webcodex" 核实：ChatGPT 网页版 + MCP 驱动本地 runner（2026-09-16）

## 一句话结论

**项目真实存在，但名字对不上、机制被误传。** 最匹配描述的是 `miuuyy/codex-chatgpt-web`（7,615 star，MIT）：它把 **ChatGPT 网页版当作 Codex 的一个模型**，用**浏览器自动化**驱动网页版会话，再用 **OpenAI 官方 tunnel-client（MCP）**把 ChatGPT 的工具调用回灌到本地 Codex 任务。所谓"绕过 5 小时限制"**不是真的改限额**，而是把负载从 **Codex/Work 额度桶**挪到 **Chat 额度桶**（三者被 OpenAI 官方拆成独立 allowance）。**主要风险**：浏览器自动化明确撞 OpenAI ToS「circumvent any rate limits or restrictions」条款，社区有封号报告（轶事级）。**不建议在承载公司凭证的环境上跑。**

## 一、是否存在（已核实，gh api 实测 2026-09-16）

| 仓库 | Star | 语言 | License | 创建 | 最后 push | 定位 |
|---|---|---|---|---|---|---|
| [miuuyy/codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web) | **7,615** | TypeScript | MIT | 2026-07-26 | 2026-09-16 | **最匹配**：「Use ChatGPT Web as a native model in Codex — without using Codex quota」 |
| [yyjeqhc/webcodex](https://github.com/yyjeqhc/webcodex) | 890 | Rust | Apache-2.0 | 2026-05-28 | 2026-09-16 | 名字最像，但定位是通用的「云端 agent → 本地开发环境」Runtime，不主打额度 |
| [3169657175/gpt-webcodex](https://github.com/3169657175/gpt-webcodex) | 238 | Python | MIT | 2026-08-07 | 2026-08-29 | 让 ChatGPT 网页版读写桌面文件，Windows 向 |
| [m4j2rpf766-crypto/gpt-web-codex](https://github.com/m4j2rpf766-crypto/gpt-web-codex) | 16 | TypeScript | MIT | 2026-08-13 | 2026-09-04 | ChatGPT Web 规划 + 本地 Luna 执行（`codex exec --json`） |
| [xq3427/WebCodex](https://github.com/xq3427/WebCodex) | 1 | TypeScript | MIT | 2026-09-10 | 2026-09-16 | 小项目，ChatGPT 经 MCP 只读接续 Codex 会话 |

作者均为独立开发者，**与 OpenAI 无任何关联**（各仓库 README 均自行声明）。"webcodex" 是中文社区对这类工具的口头统称，**不存在一个唯一叫 webcodex 的官方项目**。

## 二、机制（读 README + docs/security-model.md 原文）

`miuuyy/codex-chatgpt-web` 三段：

1. **浏览器自动化层**：启动器内置 Electron 浏览器（自带 Chromium，无需另装 Chrome/Node），用户在其中**登录自己的 ChatGPT 账号**，程序代你填 prompt、点发送、读回复，把网页版回复当成 Codex 的模型输出。用的是 **Temporary Chat**（无痕会话）。
2. **MCP 回灌层（Full harness）**：通过 OpenAI 官方 [openai/tunnel-client](https://github.com/openai/tunnel-client)（392 star，Apache-2.0，官方仓库）建立**出站 HTTPS Secure MCP Tunnel**，把 ChatGPT 的工具调用反向路由到当前 Codex 任务的文件/终端/审批。需要：ChatGPT 账号开 **Developer Mode**，建一个 **Tunnel 连接器**（名字必须叫 `Codex Native2`，鉴权选 None、权限 Allow all actions），并创建一个 **Tunnel API Key**（作者称建 key 免费、不消耗模型 API 额度）。
3. **Zero Risk 模式（v5.0.6 新增）**：完全不读/不操作 ChatGPT 页面，由用户**手动**把生成的 prompt 粘进 ChatGPT 发送——专门为规避"浏览器自动化被风控识别"设计。

**凭证要求**：不是 API key，**必须是 ChatGPT 订阅账号（Plus/Pro/Business）** + 一个（免费的）Tunnel API Key。Codex CLI 需已登录。

**安全模型（原文摘录要点，公司管凭证必须看）**：

- `docs/security-model.md` 明列 **Non-goals**：不防"被攻陷的本地用户"、不绕 ChatGPT 额度/工作区限制。
- **浏览器 profile = 敏感登录凭据**：存在 Electron 私有分区，原文警告「Never sync, upload, attach, or commit it」。
- **本机同用户进程可访问**：`127.0.0.1` 上的 Responses 端点**没有独立 bearer 密钥**（因 Codex provider 不能带自定义凭证），同 OS 用户下的任何进程都能打。
- **Prompt injection**：ChatGPT 能看到仓库内容与工具输出，Full 模式可调 write/command 工具；默认关闭自动批准。
- **5 个标签页上限**用于约束同账号并发流量（说明作者清楚这对账号画像有影响）。

## 三、5 小时限制：不是"绕过"，是"换桶"（关键纠偏）

**已核实的事实**：OpenAI 于 **2026-08-25** 为 ChatGPT Plus 恢复 Codex/Work 的 **5 小时滚动窗口**限制（此前 7 月中旬 GPT-5.6 上线时短暂取消）；Pro 档暂免，Enterprise/Edu 走 credit 制。限制按 token/请求累积触发，Codex CLI/IDE/web/iOS 与 Work **共享同一额度池**。

**项目方的说法**（[Discussion #309](https://github.com/miuuyy/codex-chatgpt-web/discussions/309)，作者自述）：
> "**Chat, ChatGPT Work, and Codex will keep separate allowances.**"（引 OpenAI 官方限额表）
> Pro 档 $200：GPT-6 Pro 200 msg/周；GPT-5.6 Sol Pro 170 msg/天；两者合计上限 200 msg/天。
> 作者自测：一周跑了约 **700 次 Pro 发送**后才开始频繁 cooldown。

**准确的机制描述**：
- 它**没有**让 OpenAI 的限额变大或消失。它把 agentic 工作从 **Codex/Work 的 5 小时窗口** 挪到 **Chat 模式自己的额度**（网页版）。
- Chat 模式本身**也有额度**（项目 README 的 Limits 段直接链到讨论 #309 说是"ChatGPT 消息额度"），只是与 Codex 池不共享。
- 作者自称项目"has not become associated with abuse or quota bypassing"——但这**是作者自我评价，不是 OpenAI 的认定**。
- **结论**：官方从没说过"Chat 模式不消耗额度"。把跨桶调度说成"破解 5 小时限制"属于**视频的说法过度**；技术上是**合法的额度重分配**（多买一份桶），不是破解。

## 四、ToS 风险：中高（有明确条款命中）

[OpenAI Terms of Use](https://openai.com/policies/terms-of-use/) "What you cannot do" 原文（2026-09-16 抓取）：

> - "**Automatically or programmatically extract data or Output**"（第 35 行）
> - "**Interfere with or disrupt our Services, including circumvent any rate limits or restrictions or bypass any protective measures or safety mitigations**"（第 37 行）

**浏览器自动化驱动 ChatGPT 网页版 UI** 直接落在第 35/37 行的射程内——即使 Zero Risk 模式（手动粘贴）把"自动提交"这一条摘掉，**Full harness 的自动填 prompt/读回复仍是 programmatic extraction**。

**社区封号报告（轶事级，未独立验证）**：
- Gate 广场帖称"有人已经被封 Codex 账号了"，指的就是这个 7.6k star 项目；**发布者是加密交易所社区账号，非一手证据，未见工单/截图/OpenAI 回执**。
- Linux.do 相关帖（[2525247](https://linux.do/t/topic/2525247)）的社区共识：**没有长期使用者的可靠反馈**，理论上有风险但"现在风险没有那么大"；担心风险者被建议改用 OpenRouter。
- 可验证的官方口径只有 [Why did I receive a warning about my account?](https://help.openai.com/en/articles/10562178-why-did-i-receive-a-warning-about-my-account)：警告 ≠ 立即停号，但重复违规会永久停用。

**风险等级判定**：**中高**。理由：(a) 条款字面命中，不是灰色地带；(b) 账号是共享体系——**一旦停号，ChatGPT web / Codex CLI / 关联 API key 全部失效**；(c) 封号案例无一手证实，但也无任何一方能否认风险；(d) 项目自身把"UI 改版导致选择器失效"列为已知故障模式，**可用性也不稳**。

## 五、如果真实目标是"让非技术同事从聊天 UI 触发内部脚本"

不建议用这条路。合规且被支持的替代：

1. **ChatGPT Developer Mode + MCP 连接器（官方，beta）**：OpenAI [开发者模式文档](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt) 明确 Full MCP（含写操作）**正在向 Business/Enterprise/Edu 计划**推出，管理员可审核并私有发布自建 MCP app。这是**唯一被官方背书**的"聊天 UI 触发内部工具"路径——同一套 tunnel-client，但不做浏览器自动化，因此不撞 ToS。
2. **Open WebUI / 内部 Portal + 函数调用**：自家项目已有裁决（见 `docs/research/2026-07-24-unified-ai-access-research.md`，C′ 门户融合）；用 API key 计费，无封号风险，可做权限、审计、白名单。
3. **Codex / Claude Code 的 Skill + 内部 MCP server**：让同事在受支持的 agent 客户端里触发，二进制由公司分发，凭证走公司侧。
4. **钉钉/企微机器人**：本项目已有 `dingtalk-robot` skill，最低摩擦、零额外账号风险。

**给老板的一句话**：这条路省的是 Plus 订阅的钱，押上的是承载公司凭证的账号；额度是"换桶"不是"免单"，且明确撞 ToS。要走官方 MCP 路线，请用 **Business/Enterprise 的 Developer Mode + 自建 MCP app**，不要碰浏览器自动化。

## 未找到 / 未能核实

- **未找到**任何 OpenAI 官方文档承认「Chat 模式可无限用」「驱动网页版可规避 Codex 限额」——不存在此声明。
- **未能核实**：Gate 广场所称封号案例（无一手证据）；Plus 档在 Chat 模式下的具体 5 小时额度数值（讨论 #309 是作者推测，OpenAI 未公布 Plus 行）。
- **未读**：各仓库源码本体（结论全部基于 README / docs/security-model.md / release notes / GitHub API 元数据 / 官方政策原文）。

## 原始 URL

- https://github.com/miuuyy/codex-chatgpt-web
- https://github.com/miuuyy/codex-chatgpt-web/blob/main/docs/security-model.md
- https://github.com/miuuyy/codex-chatgpt-web/discussions/309
- https://github.com/miuuyy/codex-chatgpt-web/releases
- https://github.com/yyjeqhc/webcodex
- https://github.com/openai/tunnel-client
- https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- https://openai.com/policies/terms-of-use/
- https://help.openai.com/en/articles/10562178-why-did-i-receive-a-warning-about-my-account
- https://linux.do/t/topic/2525247
- https://www.notebookcheck.net/OpenAI-abruptly-restores-harsh-5-hour-Codex-and-Work-limits-for-ChatGPT-Plus.1378377.0.html
- https://www.techrepublic.com/article/news-openai-five-hour-codex-limit-chatgpt-plus/
