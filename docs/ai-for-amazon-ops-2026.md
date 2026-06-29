---
okf: v0.1
type: Presentation
title: AI 赋能 Amazon 运营 — 2026 实战指南
description: 面向运营团队 + 管理层的 15-20 分钟 AI 应用分享，涵盖业界趋势、广告优化、Listing 优化、AI 工具实测对比与项目实战。
audience: Amazon 运营同事 + 管理层
date: 2026-06-29
updated: 2026-06-29 (Claude 深度优化版 — 补充 COSMO/Alexa for Shopping/工具实测/案例/成本)
---

# AI 赋能 Amazon 运营 — 2026 实战指南

> 面向：Amazon 运营团队 + 管理层 | 约 15-20 分钟
> 分享人：张克勇 | 2026-06-29
> 优化：Claude Desktop Agent（补充 COSMO 算法、Alexa for Shopping、工具实测对比、行业案例、成本估算）

---

## 目录

1. [2026，AI 不再是聊天机器人](#part1)
2. [AI + 广告优化：从人工调表到智能决策](#part2)
3. [AI + Listing 优化：COSMO 时代的文案、图片、视频全链路](#part3)
4. [我们已经在做什么 + 下一步](#part4)
5. [行动建议：今天就能开始的 3 件事](#part5)

---

## <a id="part1"></a>Part 1：2026，AI 不再是聊天机器人（约 3 分钟）

### 2025 → 2026：最大的变化是什么？

| 维度 | 2025 年 | 2026 年 |
|------|---------|---------|
| **AI 角色** | 对话助手：你问 → 它答 | **自主执行者**：你说目标 → 它干活 |
| **典型用法** | ChatGPT 聊天、帮忙写文案 | AI Agent 自动跑报表、调广告、对账 |
| **谁在用** | 主要是个人实验 | **团队落地**：运营、供应链、财务都在用 |
| **工具形态** | 网页聊天框 | **终端 Agent + 桌面 App + 浏览器自动化** |
| **门槛** | 需要会写 Prompt | **自然语言即可**，像吩咐实习生一样 |
| **成本** | $20/月 ChatGPT 订阅 | **¥10-50/月/人**（API 按量付费，5 人团队总成本 ¥50-150/月） |

> 一句话总结：**2025 年是「AI 陪你聊天」，2026 年是「AI 帮你干活」。**

---

### 核心概念：什么是 AI Agent？

```
传统 AI：你问「这个广告活动 ACOS 多少？」→ AI 回答「35%」

AI Agent：你说「帮我把高 ACOS 的广告活动找出来，关键词加否定，
         再生成一份优化报告」→ AI 自己打开报表、分析、
         生成否定词列表、输出报告 ✅
```

**AI Agent = 大模型 + 工具调用 + 自主决策**

它能：读文件、跑代码、调 API、操作浏览器、写 Excel……像一个人一样完成多步工作流。

亚马逊 2026 年白皮书数据：**超过 98%** 的中国卖家已经在使用 AI 工具，其中 **16%** 已进阶到 AI 工作流/智能代理阶段。

---

### 2026 年三大技术底座

**① MCP 协议（Model Context Protocol）**

> 就像 USB 接口统一了外设连接，**MCP 统一了 AI 连接外部工具的方式**。

- Anthropic 发明，OpenAI、微软等已跟进，成为**行业标准**
- AI 通过 MCP 直接操作：数据库、API、文件系统、浏览器……
- **我们已经在用**：卖家精灵 MCP（查竞品关键词）、ERPNext API、赛狐 API

**② Coding Agent（编程智能体）**

| 工具 | 一句话 | 适合谁 |
|------|--------|--------|
| **Claude Code** | 终端里的 AI 程序员，能读代码库、改文件、跑测试、提交 PR | 技术同事 |
| **Codex CLI** | OpenAI 开源的 Claude Code 替代品 | 技术同事 |
| **Cursor / Windsurf** | AI 原生的代码编辑器 | 技术同事 |
| **Claude Desktop** | 电脑上的 AI 助手，能操作文件、运行终端、打开浏览器 | **运营同事** |
| **Codex Desktop** | OpenAI 版桌面 Agent，开源 | 运营同事 |

> 关键变化：**非程序员也能用 Coding Agent 做自动化**。
> 运营同事对 Claude Desktop 说「帮我把这 4 份 Amazon 广告报告分析一下」→ 它自己写脚本跑。

**③ 桌面 Agent（Desktop Agent）**

- 能操作文件、运行终端、打开浏览器 — **不只是聊天**
- 运营同事用法：上传 Excel → 告诉 Agent 目标 → 等结果

---

### ⚠️ 避坑：API 中转站的陷阱

很多人为了"方便"用 API 中转站。但实测数据触目惊心：

| 风险 | 实测数据 |
|------|---------|
| 注入恶意代码 | 428 个中转站中 **9 个**（2.1%） |
| 窃取 AWS 凭证 | 428 个中 **17 个**（4.0%） |
| 模型身份造假 | **45.83%** 的端点以次充好 |
| 医疗问答准确性 | 从 83.82% 暴跌至 **37%**（花钱买 Opus，实际调了小模型） |

> **结论：永远不要用 API 中转站。直接用官方 API 或 DeepSeek 官方渠道。**

---

### 行业数据：AI 已不是可选项

- **81%** 的企业报告电商持续增长（MIT 2026 报告）
- **60%** 已实施全渠道分销策略，同比 +10%
- **35%** 使用 AI 虚拟试穿/尺码预测的企业，退货率已下降
- Amazon 美国站平均 CPC 已达 **$1.15**（较 2020 年涨 62%）— 精细化运营不是可选项，是生存必需
- **98%** 中国卖家已使用 AI 工具，**16%** 已进阶到智能代理阶段（亚马逊 2026 白皮书）

> 来源：MIT CTL 2026 State of Supply Chain Omnichannel Report；Amazon 2026 China Cross-Border E-Commerce White Paper；CETA International

---

## <a id="part2"></a>Part 2：AI + 广告优化 — 从人工调表到智能决策（约 4 分钟）

### 我们已经做了什么：Amazon 广告分析工具

**输入**：Amazon 后台导出 4 份 Sponsored Products 报告
↓
**AI Agent 自动分析**：
- 广告活动：37 个活动 ACOS/ROAS 排行 + 散点图
- 搜索词：自动识别收割词 / 否定词 / 观察词（5 桶分类）
- 投放 + 广告位效率对比
↓
**输出**：6 页 Excel 报告 + **按优先级排列的操作清单**

**实际效果（如森 US 近 30 天）**：

| 指标 | 数值 | 说明 |
|------|------|------|
| 总花费 | $3,483 | — |
| 广告销售额 | $11,513 | — |
| 整体 ACOS | 30.25% | **优于家纺品类均值 32.5%** |
| ROAS | 3.31x | — |
| 收割关键词 | 10 个（$168 → $2,238） | 加到精准匹配 |
| 否定关键词 | 32 个（省 $498） | 花过钱但零转化 |
| Top of Search ACOS | 17.34% | 最优广告位 |

> 操作同事拿到报告后只需 **15 分钟**就能完成一轮优化，之前纯人工需要 2-3 小时。

**关键发现**：广告位效率差异巨大 —
- **Product Pages** CVR 常常是 Top of Search 的 **2 倍**，且 CPC 更低 — 很多卖家低估了这个位置
- **Rest of Search** 通常表现最差
- 我们目前只用了 4/13 份 SP 报告，还有 **9 份报告**（如 Purchased Product 光环效应分析、Search Term Impression Share）可用

---

### 业界 AI 广告工具对比

#### PPC 优化工具 — 不同广告花费级别的实际月费

| 工具 | 月费（$5K 花费） | 月费（$30K 花费） | 特点 |
|------|-----------------|-------------------|------|
| **Scale Insights** | $78 | $78 | 最便宜，150 个活动上限，每小时调价 |
| **Sellozo** | $149 | $149 | 固定价不跟花费走，高花费首选 |
| **Teikametrics** | ~$79 | ~$1,099 | 增量感知出价（区分自然/广告增量） |
| **Perpetua** | $250-695 | ~$1,200-2,000 | 全自动"黑盒"AI，功能最强但最贵 |
| **我们自己做的** | **$0** | **$0** | 完全定制，按我们的逻辑来 |

> 2026 行业排名（HyperFX）：Hyper 9.3 > Pacvue 9.2 > Perpetua 9.0 > Quartile 8.6 > Skai 8.4

#### 竞品情报工具（2026 AI 功能对比）

| 工具 | 月费起步 | AI 核心功能 | 适合 |
|------|---------|------------|------|
| **Helium 10** | $129 | AI Listing Builder (ChatGPT-5.1)、AI PPC (Adtomic)、AI 评论情感分析、AI 需求预测 | 成熟卖家全栈 |
| **Jungle Scout** | $49 | AI 机会评分、AI 评论摘要、AI 销售分析仪表盘 | 新手友好 |
| **DataHawk** | 企业定制 | AI 组合预测、AI 异常检测、多市场 BI 集成 | 品牌/企业级 |
| **卖家精灵** | ¥200+ | MCP 已接入（我们已在用）、关键词缺口识别 | 中文卖家关键词 |

---

### 2026 年广告优化的新玩法

**① Sponsored Brands Video**：视频广告 ACOS 平均 16%，远优于静态图 24%
→ 亚马逊已推出**免费 AI 视频生成器**：上传产品图片 → 自动生成 6 个 6-15 秒视频变体
→ 去年 Q3 使用量环比增长 **4 倍**，**>60%** 是首次投视频广告的品牌

**② 分时竞价自动化**：AI 根据历史转化率自动调整不同时段的出价
→ 优麦云已支持，也可自己用 MCP + 定时任务实现

**③ 跨市场广告预算分配**：AI 根据各站点 ROAS 自动分配预算
→ 我们 3 个海外仓（美东/美中/波兰）+ 多国 Amazon 站点的天然优势

**④ TACoS 全局视角**：不只盯 ACoS，引入自然销售数据计算 TACoS
→ 这是我们工具的 **Phase 4 方向**

**⑤ AMC（Amazon Marketing Cloud）**：
- 广告归因事件：免费
- 零售购买 5 年数据：$500/月 → 客户生命周期价值、队列分析、流失建模
- 适合年广告费 $50K+ 的卖家

---

### 可复用的 MCP / Skills 生态

我们不需要从零造轮子。2026 年已有成熟生态：

| 资源 | 能力 | 状态 |
|------|------|------|
| **Two Minute Reports MCP** | 连接 22+ 营销数据源含 Amazon Ads + Seller Central | 可直接用 |
| **Amazon Official Ads MCP** | 自然语言 → Ads API 调用（2026.2 公测） | 可直接用 |
| **Agent Central MCP** | 144 个工具：Ads + Seller Central + 库存 | 可直接用 |
| **ads-amazon Skill** | 250+ 广告检查项 | 可直接用 |
| **claudesdk-amazon-skills-chat** | 54 个中文亚马逊卖家技能 | 可直接用 |

> 策略：API 层/MCP 层用现成的，**定制化 Excel 报告 + 中文卖家业务逻辑自己写**。

---

## <a id="part3"></a>Part 3：AI + Listing 优化 — COSMO 时代的文案、图片、视频全链路（约 5 分钟）

### 2026 最大变化：Amazon 搜索已进入 AI 时代

两件事同时发生了：

---

**① Rufus → Alexa for Shopping（2026 年 5 月）**

Amazon 的 AI 购物助手经历了自 Alexa 推出以来最大的升级：

```
旧：Rufus 是侧边栏的聊天机器人（需要用户主动打开）
新：Alexa for Shopping 直接嵌入主搜索栏（用户无需任何操作）
```

| 关键数据 | 数值 |
|---------|------|
| 已使用 AI 助手的购物者 | **3 亿+** |
| 互动同比增长 | **210%** |
| 增量年化销售额 | **$120 亿** |
| AI 购物者转化率 vs 传统搜索 | **高 60%** |
| 2025 黑五由 Rufus 处理的会话 | **38%** |
| 移动端查询中 AI 占比 | **13-20%** |

> 亚马逊此举是对 Perplexity Comet、OpenAI Instant Checkout 等外部 AI 购物代理的防御 — 保护其 **$560 亿**广告业务。AI 搜索已不是未来，是正在发生的事。

Alexa for Shopping 从这些数据源提取信息来回答购物者：
1. **Listing 内容**（标题、要点、描述、A+）
2. **客户评论**（情感、用例语言）
3. **问答**（对 AI 生成式搜索**极重要**）
4. **浏览和购买历史**（个性化推荐）
5. **图片**（AI 解释视觉内容）

---

**② COSMO 算法：从关键词匹配到意图理解**

COSMO（Common Sense Knowledge Graph，常识知识图谱）是 Amazon 搜索的底层革命：

| 维度 | A9/A10 时代（旧） | COSMO 时代（2026） |
|------|------------------|-------------------|
| **核心逻辑** | 文本字符串匹配关键词 | 理解购物者**为什么**搜索、需要解决什么问题 |
| **评估问题** | "这个 Listing 包含搜索词吗？" | "这个产品能解决购物者描述的问题吗？" |
| **内容风格** | 关键词密集、同义词堆砌 | 自然语言、传达意图、覆盖场景 |
| **更新周期** | 近实时 | 7-14 天 |

COSMO 通过 **15 种语义关系** 评估 Listing，分为 5 层：

| 层级 | 关系类型 | 靠枕套示例 |
|------|---------|-----------|
| **功能** | Used_For_Func, Capable_Of, Used_To | "可机洗、隐藏式拉链、45x45cm" |
| **受众** | Used_For_Audience, Used_By, xIs_A | "适合有小孩和宠物的家庭" |
| **场景** | Used_In_Location, Used_For_Event, Used_On | "客厅、卧室、阳台飘窗；四季通用" |
| **分类** | Is_A, Used_As | "家居装饰靠枕套，亦可作腰靠" |
| **关联** | Used_With, xInterested_In, xWant | "搭配同系列窗帘和毯子；追求简约北欧风格" |

> 实际操作目标：在 Listing 中覆盖 **5-8 个关键关系**，可显著提升 COSMO 下的搜索可见度。

---

### 实操：COSMO 时代的 Listing 优化框架

**第 1 步：填满结构化属性 — ROI 最高的动作**

Amazon 目录有 **750+ 数据字段**。大多数卖家只填了 10-20 个。AI 代理依赖结构化属性做推荐 — **填空是排名提升最被低估的手段**。90% 以上的完整率是及格线，而非目标。

**第 2 步：标题适配 75 字符新规（⚠️ 2026.7.27 生效！）**

这是 2026 年最大的结构性变化：

| 字段 | 限制 | 放什么 |
|------|------|--------|
| **标题** | **75 字符** | 品牌 + 核心产品 + 主要差异化 |
| **Item Highlights**（新） | 125 字符 | 材料、使用场景、次要关键词、认证 |

```
旧标题（关键词堆砌）："靠枕套装饰枕套棉质沙发靠垫套卧室客厅靠垫套45x45cm..."
新标题（COSMO 优化）："[品牌] 棉麻靠枕套 — 隐藏拉链 可机洗 45x45cm || 适合有宠物的家庭"
Item Highlights："高密度棉麻混纺、透气亲肤。客厅/卧室/飘窗均适用。OEKO-TEX 认证。"
```

> 7 月 27 日起，亚马逊 AI 会**自动重写**超长标题。品牌注册卖家有 14 天审核窗口。Prime Day（6.23-26）仅剩约 5 周！

**第 3 步：要点写成"回答"，而非功能列表**

```
旧方法：全大写标题 + 功能堆砌
  "PREMIUM QUALITY — Made of 100% cotton, soft, breathable, durable, machine washable..."

新方法：想象购物者在 Alexa for Shopping 里会问什么，提前回答
  "高密度棉麻混纺面料 — 透气亲肤，即使夏天也不闷汗。​可机洗不变形，
   经 50 次机洗测试不起球。隐藏式拉链设计，两面同色，翻转即换风格。"
```

**第 4 步：战略性建设问答区 — ROI 最高的 Listing 优化**

问答是 COSMO 可见度**回报最快**的优化：
- 添加 10-15 条精心设计的 QA → 30-60 天内可观看到 **20-30% 转化率提升**
- 每条 QA 嵌入场景 + 受众 + 能力信号
- 示例 Q："这个靠枕套适合有猫的家庭吗？" A："适合。高密度棉麻混纺面料防抓挠，隐藏式拉链不会被猫爪勾开，可机洗方便清洁宠物毛发。"

**第 5 步：A+ 内容 + 图片**

A+ 内容不被 A9 索引，但 COSMO/Alexa for Shopping **会完整读取**。必须包含：场景图、"适合谁"板块、对比图表。Premium A+ 转化率提升最高可达 **20%**。

---

### AI Listing 工具实测对比

| 工具 | 价格 | 核心能力 | 适合 |
|------|------|---------|------|
| **Helium 10 Listing Builder** | $99+/月 | ChatGPT-5.1 驱动、Listing 质量评分(1-10)、多语言、直接同步 Seller Central | 成熟卖家 |
| **卖家精灵 AI** | 免费起步 | 中文友好、用美国头部 Listing 训练、关键词缺口识别 | 中文卖家入门 |
| **Perci.ai** | $15/次 或 $299+/月 | 纯 AI 文案、受限关键词防护、语气调节 | 合规要求高的品牌 |
| **CopyMonkey** | $49+/月 | 批量生成最快、结构化输出 | 多 SKU 批量操作 |
| **亚马逊原生工具** | **免费** | AI Listing Generator + Enhance My Listing（持续优化在线 Listing） | 所有卖家起步 |

**推荐工作流**：卖家精灵拉关键词 → Helium 10/Claude 生成草稿 → 人工审核品牌调性 → 亚马逊原生工具检查 → 发布

**2026 年文案趋势**：
- 语义内容优于关键词堆砌 — Alexa for Shopping 像读文档一样读取 Listing
- 对话式 AI 优化 — Listing 必须回答自然语言问题
- AI 文案必须"人性化" — 通用 AI 文转化差，需加入品牌独特语言
- 护理说明用专用字段 — 放要点里会导致亚马逊自动覆盖你的第一条要点

---

### AI 图片 / 视频生成

#### 图片

| 场景 | 工具 | 用途 |
|------|------|------|
| 白底主图优化 | AI 抠图 + 背景处理 | 符合 Amazon 规范（纯白底、产品 ≥85% 画面、无文字/Logo/水印） |
| 生活场景图 | Midjourney / Adobe Firefly | A+ 模块、品牌故事 |
| AI 自动标注 | DeepSeek Vision API（**我们已落地**） | 自动标注颜色/角度/品类/背景 + Amazon 合规检查 |

#### 视频

| 工具 | 价格 | 核心能力 |
|------|------|---------|
| **Amazon AI Video Generator** | **免费** | 产品图 → 6 个 6-15 秒视频变体，Sponsored Brands 直接用 |
| **Runway Gen-4** | $12-15/月 | 电影级品牌视频 |
| **HeyGen** | $24-29/月 | 700+ AI 主播、175+ 语言唇形同步、UGC 风格广告 |
| **Synthesia** | $18-22/月 | 企业合规 (SOC 2)、140+ 语言 |

> 成本对比：之前做 200 个产品视频/月需 €40,000-80,000/年，现在用 AI 工具只需 €500-2,000/月（降幅 **90%+**，来源：Epinium 2026.4）
>
> UGC 风格 AI 视频**持续优于**高制作电影级视频 — 购买完成率高 **27%**

---

### 多语言批量 Listing

- 我们有北美（英/西）+ 欧洲（德/法/意/西/波兰语）多个站点
- AI 可以：英文主 Listing → 自动翻译 + 本地化 SEO → **一次性覆盖 7 个站点**
- 不仅是翻译，是**针对当地搜索习惯做关键词适配**

---

## <a id="part4"></a>Part 4：我们已经在做什么 + 下一步（约 3 分钟）

### 当前 AI 应用全景

```
┌──────────────────────────────────────────────────────────────┐
│                    FZH AI 应用现状                              │
├──────────────┬──────────────────┬────────────────────────────┤
│   广告优化    │   数据管道        │   内容 & 图片               │
├──────────────┼──────────────────┼────────────────────────────┤
│ ✅ 广告分析   │ ✅ 库存初始化     │ ✅ 图片上传 Web             │
│   工具 v0.3  │   赛狐导入        │   工具 (拖拽排序)            │
│              │                  │                            │
│ ✅ 搜索词     │ ✅ 采购成本       │ ✅ AI 图片自动标注           │
│   5 桶分类   │   自动计算        │   DeepSeek Vision +        │
│              │                  │   Amazon 合规检查           │
│ ✅ 卖家精灵   │ ✅ 商品重尺       │ 🔜 AI 商品图自动生成         │
│   MCP 接入   │   重量匹配       │                            │
│              │                  │ 🔜 多语言 Listing           │
│ 🔜 竞价自动化 │ ✅ 商品分类       │   批量生成                  │
│              │   4 级分类树     │                            │
│ 🔜 TACoS     │ ✅ 海外仓备货     │                            │
│    全局视角  │   三成本拆分      │                            │
├──────────────┼──────────────────┼────────────────────────────┤
│   基础设施    │ ✅ ChatGPT API 共享 (US 代理)                   │
│              │ ✅ 钉钉 OAuth 登录 (new-api)                   │
│              │ 🔜 赛狐 API 接入 (16 个模块含 Ads)              │
└──────────────┴───────────────────────────────────────────────┘
```

### 供应链示例：三系统数据对账

这是**非运营但老板感兴趣**的展示：

```
赛狐 (Amazon 对接)  ←→  ERPNext (主数据源)  ←→  通途 (发货系统)
         ↑                    ↑                    ↑
         └────────── AI Agent 自动对账 ──────────────┘

背景：三方系统 SKU 定义不同——
  赛狐按 Amazon SKU、ERPNext 按物料编码、通途按发货 SKU
  之前由一个人全职做，每次对账 2-3 天

已落地的 AI 自动化：
  - 库存初始化：通途多仓库存 → 赛狐导入文件
  - 采购成本：EN BOM 成本 → 赛狐采购价（绍兴工厂 → 头程运费）
  - 商品分类：EN 物料属性 ↔ 赛狐 4 级分类树
  - 备货单：三成本（工厂/头程/海外加工）自动拆分
  - 多属性商品：EN 纵向物料 → 赛狐扁平多属性格式
```

---

### 下一步路线图

| 优先级 | 方向 | 对运营的价值 | 依赖 |
|--------|------|-------------|------|
| 🔴 高 | **广告 TACoS 计算** | 看清广告的真实 ROI（含自然销售） | 需要产品利润率数据 |
| 🔴 高 | **竞品关键词情报整合** | 卖家精灵 MCP → 自动建议新关键词 | 卖家精灵 MCP（已就绪） |
| 🔴 高 | **广告决策日志** | 记录每次调了什么、效果如何 → AI 学习优化 | 无 |
| 🔴 高 | **补充 9 份 SP 报告** | Purchased Product（光环效应）、Impression Share 等 | 从 Amazon 后台导出 |
| 🟡 中 | **AI Listing 文案** | 批量生成多语言产品文案 | Helium 10 / SellerSprite |
| 🟡 中 | **AI 商品图片** | 用 AI 生成 lifestyle 场景图 | Midjourney / Firefly |
| 🟡 中 | **赛狐 API 广告自动化** | 通过赛狐 API 调广告（赛狐 16 个模块中已含 Ads） | IP 白名单 + OAuth |
| 🟢 远期 | **企业知识沉淀系统** | AI 自动提取经验→沉淀为团队知识→新人上手快 | LiteLLM 网关 + Git |
| 🟢 远期 | **AMC 数据分析** | 客户生命周期价值、队列分析、流失建模 | $500/月 + Brand Registry |

> 企业知识系统愿景：LiteLLM 网关自动记录所有 AI 交互 → 每周 Python 脚本提取模式/踩坑/成功经验 → 人工审核后写入 Git → 所有 Agent 自动加载。"错误自动升级为团队规则"。

---

## <a id="part5"></a>Part 5：行动建议 — 今天就能开始的 3 件事（约 3 分钟）

### 1️⃣ 装上 AI 助手，让 AI 帮你干活

> 不需要学代码，**像吩咐实习生一样跟 AI 说话**。

```
第一天：装 Claude Desktop / Codex Desktop → 告诉它「帮我分析这份广告报表」
第一周：学会用「上传文件 + 给指令」模式
第一个月：发现 80% 的重复性工作都能交给 AI
```

**成本参考**（5 人运营团队）：

| 角色 | 推荐方案 | 月费/人 |
|------|---------|---------|
| 运营同事（非技术） | Codex Desktop + OpenAI 订阅 | ~$20（¥145） |
| 运营同事（愿意学） | Claude Desktop + DeepSeek V4 Flash | ¥10-30 |
| 技术同事 | Claude Code CLI + DeepSeek V4 Pro | ¥20-50 |
| **5 人团队总计** | **1 个 DeepSeek API Key 共享** | **¥50-150/月** |

> 参考：`docs/onboarding.md`（已有非技术同事快速上手指南）

---

### 2️⃣ 广告优化先跑起来 — 用我们的工具

现有广告分析工具已可用，只需要：

1. 从 Amazon 后台导出 4 份 SP 报告（5 分钟）
2. 放到 `advertise/数据源/` 目录
3. 对 AI 说「帮我分析广告」
4. 拿到 Excel 报告 → 按操作清单执行（15 分钟）

> **20 分钟完成一轮优化** vs 之前 2-3 小时。

---

### 3️⃣ 建立 AI 使用习惯

| 场景 | 以前 | 以后 |
|------|------|------|
| 写 Listing 文案 | 自己憋半天 | AI 出 3 版 → 你挑 + 改 |
| 查竞品关键词 | 手动翻卖家精灵 | 对 AI 说「查这 5 个竞品的核心关键词」 |
| 做周报 | 手动拉数据做表 | AI 自动汇总 + 格式化 |
| 图片处理 | Photoshop | AI 抠图 + 调色 + 生成场景图 |
| 多语言翻译 | 谷歌翻译 | AI 做本地化 SEO 翻译 |
| Listing 合规检查 | 人工逐条核对 | AI 对标 COSMO 15 种关系 + 750 属性字段 |

---

### 其他跨境电商公司已经在做了

| 公司 | 成果 |
|------|------|
| **MelodySusie**（美甲品牌） | 全链路广告自动化、**ACOS 仅行业 1/3**、转化率 **+40%** |
| **ubras**（内衣品牌） | Amazon 店铺**仅 2 人运营**，做到传统 10 人团队规模 |
| **TOPDON**（汽车诊断仪） | 新品上线决策从数天 → **几分钟**、3 个月销量破万 |
| **Jihong**（吉宏股份） | AI 多智能体平台：运营效率 **+60%**、内容产量 **+770%**、客服自动化 **85%** |
| **Emitever**（LED 装饰灯） | Listing 转化率 <10%→**14%**、销售额 **+120%**、内容成本 $20K→$5K/月 |

> 他们不是大厂。他们只是比同行**早半年**开始用 AI。

---

### ⚠️ 不要做的事

| 不要 | 原因 |
|------|------|
| 用 API 中转站 | 45% 以次充好，4% 窃取凭证，2% 注入恶意代码 |
| Codex Desktop + DeepSeek 组合 | 每任务 ¥12 vs Claude Code 的 ¥0.5-1（**10-20 倍差价**）；上传图片会卡死线程 |
| 用 Hermes 自动 Skill | 已知案例：自动合并了半成品 PR 到 main，成本从 ¥230 飙到 ¥17,000/天 |
| 一次性改完所有 Listing | 每次改一个变量，观察 7-14 天再改下一个 |
| 忽视移动端 | 50%+ 购买在手机上完成，标题前 60-80 字符最关键 |

---

## 总结

```
        2025                    2026
   ┌─────────────┐       ┌─────────────────┐
   │  AI = 聊天   │  →→→  │  AI = 干活的同事  │
   │  你问 → 它答  │       │  你说目标 → 它执行  │
   └─────────────┘       └─────────────────┘

  ✅ 已落地：广告分析工具，供应链对账，图片上传，AI 图片标注
  🔜 推进中：TACoS 计算，竞品情报，AI Listing 文案，赛狐 API 接入
  🎯 目标：每个运营同事都有一个 AI 助手，每天省 1-2 小时
  💰 成本：5 人团队 ¥50-150/月（不到一顿饭钱）
```

---

## 讨论 & QA

> 你想先试哪个？
>
> - 装 Claude Desktop 开始用？
> - 跑一次广告分析工具？
> - 试试 AI 给某个 ASIN 写 Listing？
> - 用卖家精灵 MCP 拉竞品关键词？

---

## 参考 & 延伸阅读

### 项目文档
- **新手上手**：`docs/onboarding.md`（非技术同事快速上手）
- **广告工具**：`advertise/README.md`（如何使用广告分析）
- **公司背景**：`docs/company-context.md`（三系统 + 供应链）
- **Agent 对比**：`docs/ai-agent-desktop-comparison.md`（选型参考）
- **非技术落地**：`docs/non-tech-team-agent-guide.md`（可行性报告）

### 业界趋势与数据
- MIT CTL 2026 Omnichannel Report: https://ctl.mit.edu/news/ai-not-optional-anymore-omnichannel-supply-chains-new-mit-ctl-research-finds
- Amazon 2026 China Cross-Border E-Commerce White Paper: https://m.sohu.com/a/1035709349_121372103/
- CETA International PPC Guide 2026: https://www.cetainternational.com/insights/amazon-ppc-advertising-optimization-2026
- Anthropic Claude Blog: https://claude.com/blog
- Claude Opus 4.8: https://www.anthropic.com/news/claude-opus-4-8

### Listing & COSMO 优化
- COSMO Algorithm Complete Guide (2026): https://www.zonguru.com/blog/amazon-cosmo-guide
- Amazon Alexa for Shopping Listing Optimization: https://www.sellersprite.com/en/blog/amazon-alexa-for-shopping-listing-optimization-2026
- Amazon 75-Character Title Rule: https://canopymanagement.com/amazon-75-character-title-limit-item-highlights/
- A10 Algorithm Explained 2026: https://amzscout.net/blog/amazon-a10-algorithm-explained/
- Amazon Agent-Ready Attributes Audit: https://www.sellersprite.com/en/blog/amazon-agent-ready-attributes-audit-2026

### AI 工具 & 案例
- AI Video Tools for Ecommerce (2026): https://videowise.com/blog/ai-video-tools-ecommerce
- Helium 10 vs Jungle Scout (2026): https://www.smartscout.com/blog/helium-10-vs-jungle-scout
- Best Amazon PPC Tools 2026: https://ecommerceparadise.com/best-amazon-ppc-tools-2026/
- 吉宏股份 AI+ 成果: https://www.cs.com.cn/ssgs/01/2026/06/17/detail_2026061710018963.html
- StoreClaw AI 跨境工具: https://eu.36kr.com/en/p/3846793046133257
- 义乌 AI Agent 案例: http://www.china.org.cn/china/Off_the_Wire/2026-06/10/content_118542081.shtml
