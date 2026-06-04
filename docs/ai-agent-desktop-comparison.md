# AI Agent 桌面端对比：给非技术同事选工具

> 最后更新：2026-06-04  
> 面向：公司内部非技术开发人员（运营、供应链、财务等）  
> 目标：选一个能干活、不折腾、能长期用的 AI 桌面工具

---

## 一分钟结论（修正版）

| 你是什么人 | 选什么 | 花多少钱 |
|-----------|--------|---------|
| 非技术同事（日常办公、Excel、文档） | **Codex Desktop + OpenAI 官方** | $20/月 |
| 技术同事（写 Python、管数据、省钱） | **Claude Code CLI + DeepSeek V4** | API 按量 ~¥10-50/月 |
| 技术同事（追求最强能力） | Claude Code + Codex 组合 | $20-40/月 |
| 团队超过 5 人 | **Hermes 服务器部署**（试点） | ¥20-70/人/月 |
| ❌ 别碰 | Codex + Codex++ + DeepSeek | 成本高、体验差 |
| ❌ 别碰 | Claude Desktop 新版直接填 DeepSeek API | 被封了 |

---

## 快速对比

| | Codex Desktop | Claude Desktop | Hermes Desktop |
|------|------|------|------|
| **上手难度** | ⭐ 最低，像微信一样装 | ⭐⭐⭐ 需技术基础 | ⭐⭐ 一般 |
| **中文界面** | ✅ 有 | ⚠️ 部分 | ❌ 全英文 |
| **办公模式** | ✅ Excelmogging 专为办公设计 | ❌ 以编程为主 | ❌ 编程为主 |
| **Excel 操作** | ✅ 直接生成 .xlsx 可预览 | ⚠️ 需要 Python 脚本 | ⚠️ 代码方式 |
| **网页抓取** | ✅ 内置浏览器 + Computer Use | ✅ WebFetch 内置 | ⚠️ 需配置 |
| **接 DeepSeek** | ⚠️ 能接但很折腾 | ❌ 2026年5月起被封杀 | ✅ 原生支持 |
| **接 OpenAI 官方** | ✅ 原生 | ✅ 原生 | ✅ 支持 |
| **价格** | $20/月起 | $20/月起 | 免费 |
| **稳定性** | ✅ 最稳 | ⚠️ API 封杀风险 | ❌ 预览版 |
| **适合场景** | 办公+编程 | 编程为主 | 编程为主 |

---

## 各工具详评

### 1. Codex Desktop — 🥇 非技术同事首选

**为什么推荐：**

2026 年 4 月起 Codex 推出**双模式**：Excelmogging（办公模式）和 Codemaxxing（编程模式）。办公模式下界面极简，不需要任何编程知识。

**实测能做这些事：**
- 📊 "帮我把这个月的销售数据做成 Excel，按品类汇总"
- 📋 "把这份会议纪要转成待办清单表格"
- 🌐 "去这个网页抓取价格数据，填到表格里"
- 📧 "帮我写一封给供应商的邮件，附上 Excel 数据"
- 🧹 "合并这三个 CSV 文件，去掉重复行"

**优点：**
- 界面像聊天软件，不需要学命令行
- 直接生成 `.xlsx` 文件，侧栏可预览
- 内置浏览器，能自动从网页抓数据
- 周活 400 万用户，产品最成熟
- Windows 11 原生支持

**缺点：**
- Plus 版 ($20/月) 重度使用 5 小时可能到额度上限
- Electron 架构，老电脑可能吃力（建议 16GB+ 内存）
- 接 DeepSeek 第三方模型**非常折腾**（身份伪装、工具调用失败、成本反而更高）

**对非技术同事的建议：直接用 OpenAI 官方订阅，不要折腾 Codex++/DeepSeek。**

---

### 2. Claude Desktop — ⚠️ 分情况讨论

**关键区分：你用的是什么版本、什么方式接 DeepSeek。**

#### 情况 A：旧版本 + 本地代理 → ✅ 可用

如果你在 2026 年 4 月底 - 5 月初下载了 Claude Desktop，并使用了本地代理（如 `deepclaude-mixed-setup`、`cc-switch`）+ 模型 ID 伪装，**目前仍可正常使用 DeepSeek V4**。

社区实测：
- 模型 ID 伪装为 `claude-sonnet-4-6` 等 Anthropic 格式 → 绕过白名单
- `deepclaude-mixed-setup`（npm 包）提供一键安装，支持 `claude-mode 3p/1p` 切换
- 本项目用户实测：4 月底下载的版本 + 3P 模式接入 DeepSeek V4，至今能用

**已知局限：**
- 上传图片不报错但 DeepSeek 无法解析（纯文本模型）
- 对话可以继续，不会像 Codex 那样线程卡死
- "猫鼠游戏"风险：Anthropic 可能未来升级检测手段

#### 情况 B：新版本 + 直接 Gateway 配置 → ❌ 已被封

2026 年 5 月 6 日起，Anthropic 推送 1.6259.1 版本，新增**模型 ID 白名单**：
- 只允许 `claude` 或 `anthropic` 前缀的模型
- 直接填 DeepSeek API 地址 → 报错 `configured model is not an anthropic model`

**绕过方法**：必须通过本地代理伪装模型 ID，不能用 Claude Desktop 原生配置面板。

#### 情况 C：Claude Code CLI + DeepSeek → ✅ 最佳性价比

**这是关键发现**——同样用 DeepSeek V4，Claude Code CLI 的成本和体验远优于 Codex Desktop：

| 对比维度 | Claude Code + DeepSeek | Codex Desktop + DeepSeek |
|----------|----------------------|--------------------------|
| 缓存命中率 | 高（上下文策略好） | 低（Token 浪费严重） |
| 同任务成本 | ¥0.5-1 | ¥12（10-20 倍差距） |
| 图片上传 | 不报错，对话继续 | 线程永久卡死 |
| Web Search | WebFetch 内置 | 需装 MCP |
| 配置复杂度 | 环境变量一次配好 | 需桥接代理 + 协议转换 |

Claude Code CLI 的环境变量配置（一次性）：
```bash
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="sk-你的Key"
export ANTHROPIC_MODEL="deepseek-v4-pro"
```

**结论：对技术同事，推荐 Claude Code CLI + DeepSeek，不要用 Codex + DeepSeek。**

---

### 3. Hermes Desktop — 🔮 值得关注，但还不是现在

**6 月 2 日刚发布桌面端（预览版）。** 很有潜力，但还没熟。

**亮点：**
- 免费、开源、本地运行
- "自我进化"——Agent 会观察用户习惯自动优化
- 支持 300+ 模型
- 内置 100 个 Skills

**硬伤（对中国非技术用户）：**
- ❌ **全英文界面**，没有中文切换
- ❌ **中文输入 Bug**：输入法下回车直接发送，不换行
- ❌ 安装可能失败（文件权限问题）
- ❌ Profile 切换不便
- ❌ 稳定性"预览版"级别

**社区第三方版本**有中文支持（`dodo-reach/hermes-desktop`、`hermes-agent-cn`），但太碎片化，不适合推广给非技术同事。

**建议：3 个月后再看桌面端。** 但服务端部署值得现在了解。

---

### 3B. Hermes 服务器部署 — 🏭 企业团队方案

**如果你不想让同事每人装一个桌面端，可以在公司服务器上部署 Hermes，大家通过浏览器或 IM（飞书/企微）使用。**

#### 部署方式

| 方案 | 难度 | 成本 | 适合 |
|------|------|------|------|
| **Docker 双容器**（官方） | ⭐⭐ | 服务器 ¥50/月 | 有 Docker 基础的团队 |
| **阿里云计算巢** 一键部署 | ⭐ | 服务器 + 服务费 | 不想碰命令行的团队 |
| **腾讯云轻量服务器** 应用模板 | ⭐ | ~¥188/年 | 预算敏感的团队 |

#### Docker 部署（最灵活）

```bash
# 核心 Agent 服务
docker run -d --name hermes --restart unless-stopped \
  -v ~/.hermes:/opt/data \
  -p 8642:8642 \
  nousresearch/hermes-agent:latest gateway run

# Web 管理面板
docker run -d --name hermes-dashboard --restart unless-stopped \
  -v ~/.hermes:/opt/data \
  -p 9119:9119 \
  nousresearch/hermes-agent:latest dashboard --host 0.0.0.0
```

#### 多用户支持

| 功能 | 支持情况 |
|------|---------|
| **IM 接入** | ✅ 飞书、企业微信、钉钉、Telegram、微信 |
| **Web 控制台** | ✅ 多人同时操作，权限隔离 |
| **SSO 单点登录** | ✅ JWT / OAuth2.0 / LDAP |
| **审计日志** | ✅ 保留 90 天操作日志 |
| **资源配额** | ✅ 每用户 CPU/内存限额 |
| **Token 消耗** | 取决于使用的模型 API（DeepSeek 极低） |

#### 独特的"自我进化"能力

Hermes 会自动将成功经验总结为 **Skills**。在服务器部署中，这些 Skills **可以跨用户共享**——A 同事解决问题的经验，B 同事自动受益。

#### 成本测算（10 人团队）

| 项目 | 月成本 |
|------|--------|
| 云服务器（4核8G） | ~¥100-200 |
| DeepSeek API（共享池） | ~¥100-500（按使用量） |
| **每人月均** | **¥20-70** |

> 对比每人买 Codex $20/月 × 10 = $200/月 ≈ ¥1,450/月，Hermes 服务器方案有明显成本优势。

#### 当前局限

- 仍是较新产品，社区生态不如 Codex/Claude
- "自我进化"效果需长期验证
- 中文 IM 集成（企微/飞书）的稳定性待实测
- 桌面端刚发预览版，服务端 + 桌面端的联动尚未成熟

---

### 4. 不值得考虑的

| 工具 | 不推荐原因 |
|------|-----------|
| Cursor | 程序员 IDE，非技术用户用不上 |
| Windsurf | 同上，偏前端开发 |
| OpenCode | 需要自己配 API key，技术门槛高 |
| Gemini CLI | 桌面端体验差 |
| 任何"手动搭代理"方案 | 非技术同事的天书 |

---

## 成本测算

一个非技术同事每月花多少钱？

| 方案 | 月费 | 年费 | 备注 |
|------|------|------|------|
| Codex Plus + OpenAI 官方 | $20 | ~¥1,750 | 最简单，推荐 |
| Codex Pro + OpenAI 官方 | $100 | ~¥8,760 | 重度使用才需要 |
| Codex Plus + DeepSeek (Codex++) | $20 + API 按量 | 不稳定 | 折腾+风险，不推荐 |
| Claude Pro + 官方 | $20 | ~¥1,750 | 封杀风险 |
| Hermes + DeepSeek API | API 按量（极低） | ~¥200-500/年 | 等 3 个月 |

---

## 给公司推广的建议（更新）

### 第 1 步：非技术同事 → Codex Desktop + OpenAI 官方订阅

- $20/月，Excelmogging 办公模式，自然语言操作 Excel
- 不要折腾 Codex++ / DeepSeek ——体验差、成本反而更高

### 第 2 步：技术同事 → Claude Code CLI + DeepSeek

- **成本最优**：同任务 Claude Code + DeepSeek 花费 ¥0.5-1，Codex + DeepSeek 花 ¥12
- 环境变量一次性配置（5 分钟）
- WebFetch 内置，不需要装 MCP
- 图片上传不卡死线程（与 Codex 的关键差异）

### 第 3 步：探索 Hermes 服务器部署

- 如果团队超过 5 人，值得在服务器上部署 Hermes
- Docker 双容器方案，5 分钟上线
- 飞书/企微接入后，非技术同事甚至不需要装任何桌面软件
- 长期成本最低（共享 API + 自我进化积累经验）

### 第 4 步：不要做的事

- ❌ 给非技术同事推 Claude Desktop 3P + 本地代理（技术门槛太高）
- ❌ 给非技术同事推 Codex + Codex++ + DeepSeek（图片卡死 + 搜索靠 MCP）
- ❌ 给任何人推 Hermes 桌面端（中文不支持，等 3 个月）
- ❌ 现在就让全公司用 DeepSeek V4 Pro（`tool_choice` 参数 bug 影响部分功能）

---

## 信息源

| 来源 | 链接 |
|------|------|
| V2EX - 开发用 Claude desktop 还是 Codex？ | `global.v2ex.co/t/1213136` |
| 什么值得买 - 实测三月 Codex：我彻底放弃 Claude Code 了 | `post.smzdm.com/p/anvpk46v/` |
| LINUX DO - CodeX和Claude桌面端的体验讨论 | `linux.do/t/topic/2108676` |
| AIBase - 全线封杀！Claude桌面端收紧限制 | `aibase.com/zh/news/27764` |
| 知乎 - 如何评价Codex桌面版？ | `zhihu.com/question/2001978391264502048` |
| 智东西 - Hermes官方桌面版发布！踩坑记录 | `zhidx.com/p/562879` |
| CSDN - 2026封神级AI神器 Codex 零基础教程 | `blog.csdn.net/2403_88033173/article/details/161348521` |
| 快科技 - DeepSeek V4 不能用了 Claude桌面再次封杀 | `m.mydrivers.com/newsview/1120710` |
| Gate - Codex 双模式（Excelmogging / Codemaxxing） | `gate.tv/zh/news/detail/20672372` |
| 经理人 - Codex 新手入门教学 | `managertoday.com.tw/articles/view/72111` |
