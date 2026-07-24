---
okf: v0.1
type: Research
title: AI Agent 平台深度对比 — Open WebUI vs Hermes vs Pi vs 其他
description: 针对 FZH 公司需求（浏览器端、代码执行、钉钉 SSO、赛狐/ERPNext API 对接、非技术同事可用），对比主流自部署 AI Agent 平台的稳定性、硬件要求、适用性
date: 2026-07-23
---

# AI Agent 平台深度对比

> 核心需求：浏览器可用、有"手脚"（代码执行 + API 调用）、钉钉登录、非技术同事能上手、5 人团队

---

## 一、Open WebUI — 更新很活跃，但有单点维护风险

**稳定性真相**：你说看到"3周前更新"，实际情况是：
- 主仓库 `open-webui/open-webui`：**昨天还在更新**（Jul 22, 2026），17,201 commits，166 releases
- Helm charts：10 小时前还有新 release
- 最新版本 v0.10.2（Jul 1, 2026）
- 月均发布频率很高（17 releases in Jun, 12 in Jul）

但确实有关键风险：
- **单维护者 + 兼职贡献者**：GitHub issue #7334 里官方自己说的——"a single maintainer and supported by contributors who also have full-time jobs"
- 这意味着如果维护者 burnout 或离开，项目可能停滞
- Helm chart 有 6,700+ 漏洞报告（59 critical, 1,042 high）——但这是 K8s 部署的，Docker 直接部署不涉及

**硬件要求**：
| 场景 | CPU | RAM | 磁盘 |
|------|-----|-----|------|
| 个人使用 | 1 core | 2 GB | 10 GB |
| 小团队 (5人) | 2 core | 4 GB | 20 GB |
| 带代码执行 (Docker沙箱) | 4 core | 8 GB | 40 GB |

**代码执行**：Open Terminal (Docker-in-Docker)，每次执行在独立容器中，支持 Python/Shell/任意语言

**对 FZH 的适用度**：⭐⭐⭐⭐（功能匹配但维护风险需关注）

---

## 二、Hermes Agent — 方向惊艳，但风险高

### 为什么不建议现在用

**1. API 还在剧烈变动**
- 42 天发布了 4 个大版本
- v0.18.0 "The Judgment Release" 是最新的
- API 不兼容更新频繁，生产环境追版本很累

**2. 自我进化是双刃剑**
- 自动生成 Skill 是核心卖点
- **但 V2EX 用户实测**：第 7 天自动把半成品 PR 合进了 main——因为 Skill 漏掉了"只操作 develop 分支"的前提
- 这个 bug 的特质：前几天不暴露，突然某天引爆
- 对非技术团队是定时炸弹

**3. 代码执行能力有限**
- Hermes 本质是**任务编排器**（Orchestrator），不是 Coding Agent
- 它的工具调用是调用预定义的 Skills/Tools，不是动态写代码→执行→看结果
- 对标场景是"帮我每天早上 9 点检查邮件并摘要"而非"分析这个 Excel 并写 Python 脚本处理"
- 虽然可以通过 Docker 隔离执行命令，但没有内置的沙箱代码解释器

**4. 成本不确定性**
- 跨境零售集团实测：从确定性架构迁到 Hermes，单日成本 ¥230 → ¥1.7 万（378 倍）
- 延迟 800ms → 12 秒
- 不过这是大规模商用场景，5 人小团队风险小得多

### 硬件要求
| 场景 | CPU | RAM | 磁盘 |
|------|-----|-----|------|
| CLI 个人使用 | 1 core | 1-2 GB | 10 GB |
| 单 IM 渠道 (如 Telegram) | 1 core | 2 GB | 20 GB |
| 多渠道 + 浏览器自动化 | 2-4 core | 4-8 GB | 60 GB |
| 多用户 5-10 并发 | 2 core | 4 GB | 20 GB |
| 生产 50+ 并发 | 4 core | 8 GB | 80 GB |

实测数据（Reddit r/hermesagent）：
- CLI 模式：~200-350 MB RSS
- Gateway 模式（API server + Telegram）：~400-500 MB RSS
- 两者同时跑：~900-950 MB RSS
- Raspberry Pi 5 (8GB) 实测：940 MB used
- 不需要 GPU（调云端 API）

### Hermes 适合什么
- 24/7 自主运行的"管家型"Agent（监控、提醒、定时任务）
- 接钉钉/飞书/企微做 IM 机器人
- 技术团队愿意折腾、追版本
- 低风险场景（报告生成、文档摘要）

### Hermes 不适合什么
- 需要写代码+执行的交互式编程场景
- 非技术同事直接使用（配置和调试需要技术能力）
- 需要稳定不折腾的生产环境

**对 FZH 的适用度**：⭐⭐（方向对但时机不对，等 v1.0 后再评估）

---

## 三、Pi Agent — 适合开发者，不适合非技术用户

### 为什么不建议

**1. 没有 Web UI**
- Pi 是**纯终端工具**（CLI + TUI）
- 用户必须用命令行操作
- 对非技术同事来说等于没用

**2. 它是 SDK/框架，不是产品**
- 定位：给开发者在自己应用里嵌入 Agent 能力的库
- 需要写 TypeScript 代码来扩展
- 官方文档原话："You need a strong engineering culture that can write TypeScript extensions"

**3. 没有内置多用户管理**
- 每个 Pi 实例是单用户的
- 要多人使用需要自己搭服务器、自己做认证、自己管理 session

### 硬件要求
- 运行在开发者本地机器上
- Agent 核心轻量（~200MB）
- 如果需要本地模型推理（Ollama/vLLM）：8GB+ VRAM
- 只调云端 API：任何现代电脑都够

### Pi 适合什么
- 个人开发者 AI 编程助手
- 需要极强定制能力的团队二次开发
- 合规要求（代码不能离开本地）

### Pi 不适合什么
- 非技术用户直接使用
- 团队开箱即用的方案

**对 FZH 的适用度**：⭐（方向错误，不是你要的产品形态）

---

## 四、替代选项：比 Open WebUI 更稳定的方案

### 4.1 Dify — 🟢 最成熟的替代

**稳定性**：企业级定位，商业化支撑（有 Dify Cloud 付费版），开源版持续维护
- GitHub: langgenius/dify, 65K+ stars
- Apache 2.0 协议
- 有全职团队维护，不像 Open WebUI 靠单维护者

**能力**：
- ✅ Web UI（浏览器端）
- ✅ 可视化工作流编排（拖拽式）
- ✅ 代码执行沙箱（DifySandbox，seccomp + chroot 隔离）
- ✅ 知识库 RAG（比 Open WebUI 更成熟）
- ✅ 多用户 + RBAC
- ✅ OAuth/OIDC 登录
- ✅ 工具/插件系统
- ✅ API 端点暴露

**缺点**：
- 定位偏"AI 应用开发平台"，不只是聊天→开箱比 Open WebUI 复杂
- 工作流抽象层对非技术同事有学习曲线
- 代码执行隔离较弱（seccomp vs Docker）

**硬件要求**：
| 场景 | CPU | RAM | 磁盘 |
|------|-----|-----|------|
| 最小部署 | 2 core | 4 GB | 30 GB |
| 小团队 (5人) | 4 core | 8 GB | 50 GB |
| 含沙箱代码执行 | 4 core | 8 GB | 50 GB |

### 4.2 LibreChat — 🟡 功能全但部署重

**稳定性**：活跃社区维护，发布节奏稳定
- GitHub: danny-avila/LibreChat, 25K+ stars
- MIT 协议

**能力**：
- ✅ Web UI
- ✅ 多模型/多提供商（切换方便）
- ✅ 代码解释器（需接 E2B 或 Daytona 沙箱）
- ✅ 文件上传/下载
- ✅ 多用户 + OAuth/OIDC
- ✅ 插件/工具系统
- ✅ RAG

**缺点**：
- 部署重（需要 MongoDB + Redis）
- 代码执行依赖外部沙箱服务（E2B 要钱，Daytona 要自己搭）
- 镜像 ~800MB+

**硬件要求**：
| 场景 | CPU | RAM | 磁盘 |
|------|-----|-----|------|
| 最小部署 | 2 core | 4 GB | 30 GB |
| 含 MongoDB/Redis | 2 core | 6 GB | 40 GB |
| 含沙箱 | 4 core | 8 GB | 50 GB |

### 4.3 NextChat (ChatGPT-Next-Web) — 🔵 最稳定但最弱

**稳定性**：极简，几乎不会坏
- GitHub: ChatGPTNextWeb/NextChat, 80K+ stars
- MIT 协议
- 功能少 = bug 少 = 维护成本低

**能力**：
- ✅ Web UI 非常干净
- ✅ 文件上传
- ✅ 多模型切换
- ❌ 无代码执行
- ❌ 无 OIDC SSO（需手动填 API Key）
- ❌ 无知识库
- ❌ 无插件

**结论**：纯 chat 方案，和你的需求不匹配。

---

## 五、综合对比

| 维度 | Open WebUI | Hermes | Pi | Dify | LibreChat | NextChat |
|------|:----------:|:------:|:--:|:----:|:---------:|:--------:|
| **Web UI** | ✅ 优秀 | ✅ 有 | ❌ CLI only | ✅ 优秀 | ✅ 良好 | ✅ 极简 |
| **代码执行** | ✅ Docker沙箱 | ⚠️ 有限 | ✅ 终端原生 | ✅ seccomp沙箱 | ⚠️ 需外接 | ❌ 无 |
| **钉钉 OIDC** | ✅ | ⚠️ IM集成 | ❌ | ✅ OAuth | ✅ OIDC | ❌ |
| **多用户** | ✅ | ✅ | ❌ 单用户 | ✅ RBAC | ✅ | ⚠️ 无SSO |
| **非技术可用** | ✅ | ❌ 需技术 | ❌ 需终端 | ⚠️ 有学习曲线 | ✅ | ✅ |
| **RAG 知识库** | ✅ | ⚠️ 记忆系统 | ❌ | ✅ 成熟 | ✅ | ❌ |
| **维护难度** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ |
| **稳定风险** | 🟡 单维护者 | 🔴 API剧变 | 🟢 库=稳定 | 🟢 企业级 | 🟢 社区 | 🟢 极简 |
| **GitHub Stars** | 146K | 150K | ~5K | 65K | 25K | 80K |
| **最小 RAM** | 2 GB | 1 GB | N/A(本地) | 4 GB | 4 GB | 0.5 GB |
| **推荐 RAM (5人)** | 4-8 GB | 2-4 GB | N/A | 8 GB | 6 GB | 1 GB |
| **需要 GPU** | ❌ | ❌ | ❌(API) | ❌ | ❌ | ❌ |

---

## 六、务实结论

### 如果你要的是"浏览器里的 Codex/Claude Code 替代品"——坦诚说，目前没有

Codex Desktop / Claude Code 的核心优势（本地文件系统、浏览器自动化、完整 OS 权限）是 Web 方案的硬天花板。这不是某个产品的问题，是架构层面的差异。

### 但如果你要的是"80% 常见工作能在浏览器里完成"——Open WebUI 或 Dify 都可以

| 工作场景 | Open WebUI | Dify | 本地 Agent |
|---------|:----------:|:----:|:----------:|
| 上传 Excel → AI 分析 | ✅ | ✅ | ✅ |
| 调赛狐 API 拉报告 | ✅ (沙箱内requests) | ✅ (工作流) | ✅ |
| 调 ERPNext API | ✅ | ✅ | ✅ |
| 写 Python 脚本跑数据 | ✅ | ✅ | ✅ |
| 钉钉机器人发消息 | ✅ | ✅ | ✅ |
| 读写本地文件 | ⚠️ 上传/下载 | ⚠️ 上传/下载 | ✅ |
| 浏览器自动化 | ❌ | ❌ | ✅ |

### 二者的关键差异

| 差异 | Open WebUI | Dify |
|------|-----------|------|
| **维护者** | 1 人+兼职贡献者（风险） | 全职团队+商业化公司（稳） |
| **学习曲线** | 低（像 ChatGPT） | 中（工作流画布） |
| **代码执行** | Docker 沙箱（强隔离） | seccomp 沙箱（弱隔离） |
| **定位** | "自己部署的 ChatGPT" | "AI 应用开发平台" |
| **扩展性** | Python Pipelines | 工作流+插件市场 |

### 我的建议

**短期（现在）**：Open WebUI——尽管有单维护者风险，但对 5 人团队来说功能最匹配、上手最简单。如果它停更了，迁移到 Dify 的成本不高（都是 OpenAI 兼容 API，数据导出不难）。

**中期（3-6个月后）**：关注 Hermes v1.0——如果 API 稳定了、自进化 Skill 有了安全护栏，它会是更强的方案（原生钉钉集成、持久记忆、24/7 运行）。

**长期底线**：Dify——有商业化支撑，不会死。如果 Open WebUI 和 Hermes 都不行，这是最稳的退路。

### 硬件最终建议

**不要用 ERPNext 测试服务器！** 4C8G 已经跑着 ERPNext + MariaDB + Redis + Nginx，再叠 AI 沙箱会崩。

推荐方案（选一个）：
- **公司闲置 PC**（16GB+ RAM）装 Ubuntu Server + Docker → ¥0
- **阿里云轻量服务器 2C4G** → ¥68/月（够 3-5 人轻度用）
- **阿里云 ECS 4C8G** → ¥200-300/月（够 5-10 人舒适用）

---

## 数据源

- Open WebUI GitHub: https://github.com/open-webui/open-webui (146K stars, updated Jul 22 2026)
- Open WebUI 代码执行文档: https://docs.openwebui.com/features/chat-conversations/chat-features/code-execution
- Open WebUI Issue #7334 (单维护者确认): https://github.com/open-webui/open-webui/issues/7334
- Hermes Agent 硬件需求: https://xcloud.host/best-hermes-agent-hosting-providers
- Hermes Agent 实测 RAM: https://www.reddit.com/r/hermesagent/comments/1t246e3/actual_memory_ram_not_vram_requirements
- Hermes Agent 系统需求: https://openclawlaunch.com/guides/hermes-agent-system-requirements
- Hermes 自部署指南: https://www.virtua.cloud/learn/en/tutorials/self-host-hermes-agent-vps
- Hermes vs OpenClaw 安全对比: https://hackernoon.com/hermes-agent-vs-openclaw-which-ai-agent-framework-wins-in-2026
- Pi Agent 评测: https://petronellatech.com/blog/pi-dev-platform-review
- Pi Agent Hacker News 讨论: https://news.ycombinator.com/item?id=47143754
- Dify GitHub: https://github.com/langgenius/dify
- LibreChat GitHub: https://github.com/danny-avila/LibreChat
