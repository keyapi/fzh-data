---
okf: v0.1
type: Reference
title: 已验证信息源 — Amazon 广告研究 2026
description: 所有引用源的 WebFetch 验证记录，含标题、日期、作者、已验证声明和无差异说明
tags: [amazon, advertising, reference, verified-sources, 2026]
timestamp: 2026-06-24
---

# 已验证信息源

本文档记录研究过程中通过 WebFetch 逐一验证的所有信息源。每个条目包含源 URL、标题、发布日期、作者（如有）、已验证的关键声明，以及与原始研究结论的一致性说明。

---

## Source 1: Amazon Ads MCP Server 官方公告

- **URL**: [https://advertising.amazon.com/en-us/library/news/amazon-ads-mcp-server-open-beta](https://advertising.amazon.com/en-us/library/news/amazon-ads-mcp-server-open-beta)
- **Title**: "Introducing the Amazon Ads MCP Server"
- **Date**: February 2, 2026
- **Author**: Paula Despins, VP Ads Measurement

### 已验证声明

1. **Open Beta 阶段**：MCP Server 已向全球广告主开放 Beta 测试
2. **MCP 协议**：采用 Anthropic Model Context Protocol，非 Amazon 专有协议
3. **跨平台兼容**：支持 Claude、ChatGPT、Gemini 等主流 AI 平台
4. **预构建工具**：提供 campaign 创建、跨国家扩展等预构建工具
5. **全球可用**：不限于特定市场，全球范围内可用

### 差异说明

无差异。官方公告与第三方解读一致。

---

## Source 2: Canopy Management 10 大广告技巧

- **URL**: [https://canopymanagement.com/10-amazon-advertising-tips-for-better-results/](https://canopymanagement.com/10-amazon-advertising-tips-for-better-results/)
- **Date**: March 19, 2026
- **Author**: Chuck Kessler

### 已验证声明

1. **SB 转化率 9.5%**：Sponsored Brands 视频广告格式的平均转化率达到 9.5%
2. **三层 SKU 体系**：Hero SKU（主力）、Supporting SKU（辅助）、Long-tail SKU（长尾），各有不同的广告策略
3. **TACoS 框架**：
   - 新品/启动期：目标 TACoS **15-25%**
   - 成熟期：目标 TACoS **8-12%**
4. **AI 图片效果**：使用 AI 生成的 lifestyle 图片可使 CTR 提升高达 **40%**

### 差异说明

无差异。Canopy Management 的 TACoS 框架与 Mr. Prime 和 Adverio 的基准数据一致。

---

## Source 3: Autron Campaign 架构

- **URL**: [https://autron.ai/blog/amazon-ppc-campaign-structure-in-2026-why-fewer-campaigns-now-beat-more](https://autron.ai/blog/amazon-ppc-campaign-structure-in-2026-why-fewer-campaigns-now-beat-more)
- **Date**: May 4, 2026
- **Author**: Adrian Steele

### 已验证声明

1. **Rufus 媒介作用**：Rufus（现已被 Alexa for Shopping 取代）曾媒介 **15-20% 的移动端查询**
2. **算法信号阈值**：每个 ASIN 至少需要 **30 点击/周** 才能积累足够算法学习信号
3. **意图驱动重组效果**：从关键词精确匹配转向意图驱动架构可实现 **20-35% ACOS 降低**
4. **三桶框架**（Three-Bucket Framework）：Discovery → Harvest/Validation → Performance
5. **"更少 campaign 更好"**：2026 年更少、更大体量的 campaign 优于大量碎片化 SKAG

### 差异说明

无差异。三桶框架与 ClearAds Agency 的架构建议一致。注意 Rufus 已退役，Alexa for Shopping 于 2026 年 5 月接替。

---

## Source 4: Trellis AI for Amazon Ads

- **URL**: [https://gotrellis.com/resources/blog/ai-for-amazon-ads/](https://gotrellis.com/resources/blog/ai-for-amazon-ads/)
- **Date**: May 29, 2026
- **Author**: Mike Lepine, Director of Engineering

### 已验证声明

1. **三级 AI 模型**：
   - Level 1: **AI-Assisted**（AI 辅助）— 人类决策，AI 提供建议
   - Level 2: **AI-Managed**（AI 管理）— AI 自动执行，人类设置护栏
   - Level 3: **Workflow**（工作流）— 完全自动化，端到端
2. **MCP 协议**：确认 Amazon MCP Server 于 2026年2月2日 发布
3. **LLM 局限性**：列出 LLM 在广告优化中的已知限制（数据新鲜度、幻觉、缺乏因果推理）
4. **工作流示例**：展示从搜索词分析到否定关键词的完整工作流

### 备注

Trellis 的产品定位针对 **200+ SKU 的大型运营**，中小卖家可能无法从该工具获得等效价值。

---

## Source 5: PPC Land Consent Deadline

- **URL**: [https://ppc.land/amazon-ads-consent-deadline-is-june-30-your-data-wont-work-after-that/](https://ppc.land/amazon-ads-consent-deadline-is-june-30-your-data-wont-work-after-that/)
- **Date**: May 14, 2026
- **Author**: Luis Rijo

### 已验证声明

1. **强制日期**：**2026年6月30日** 是 Amazon Ads Consent Signal 强制执行日期
2. **影响范围**：受影响的 API 包括 **Amazon Ads Tag (AAT)**、**Conversions API (CAPI)**、**Events API**
3. **技术要求**：必须实现 **TCF v2.2**（欧洲）、**GPP**（美国多州隐私法）、**ACS**（Amazon Consent Signal）之一
4. **国家代码**：必须传入 **2 字符 ISO 国家代码**
5. **数据保留**：用户级数据保留期限制为 **13 个月**

### 差异说明

无差异。**关键截止日期确认**。当前日期为 2026年6月24日，距离截止仅剩 **6 天**。所有使用 AAT/CAPI 的广告主必须立即行动。

---

## Source 6: Amazon Creative Agent 官方公告

- **URL**: [https://www.aboutamazon.ca/news/amazon-ads/amazon-ads-launches-creative-agent-new-agentic-ai-tool-that-creates-professional-quality-ads](https://www.aboutamazon.ca/news/amazon-ads/amazon-ads-launches-creative-agent-new-agentic-ai-tool-that-creates-professional-quality-ads)
- **Date**: February 25, 2026
- **Author**: Amazon Staff

### 已验证声明

1. **代理型 AI**：Creative Agent 是构建在 Creative Studio 内的代理型 AI 工具
2. **全流程覆盖**：从创意构思、脚本、图像、视频、动画、配音、到音乐的一体化 pipeline
3. **免费使用**：对广告主免费开放
4. **技术栈**：基于 **AWS Bedrock + Amazon Nova + Claude** 构建
5. **专业品质**：官方声称可生成专业级广告素材

### 差异说明

无差异。Creative Agent 与代理型广告趋势高度吻合，证实代理型 AI 已在 Amazon 广告生态中落地。

---

## Source 7: Spotify 多代理架构

- **URL**: [https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising](https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising)
- **Date**: February 19, 2026
- **Authors**: Pratik Rasam, Ralph Sylvain

### 已验证声明

1. **6 个专门化代理**：架构包含 6 个协作的专门化 AI 代理
2. **技术栈**：
   - **Google ADK 0.2.0**（Agent Development Kit）
   - **Vertex AI Gemini 2.5 Pro**
   - **gRPC** 作为代理间通信协议
3. **性能提升**：将任务完成时间从 **15-30分钟 压缩至 5-10秒**
4. **提示工程即软件工程**：Spotify 将 prompt engineering 视为软件工程的最佳实践

### 差异说明

无差异。Spotify 的实践验证了多代理架构在广告领域的可行性，Amazon 的 MCP Server 可视为同一趋势的 Amazon 生态变现。

---

## Source 8: IvyeaOps GitHub

- **URL**: [https://github.com/Hector-xue/IvyeaOps](https://github.com/Hector-xue/IvyeaOps)

### 已验证声明

1. **许可证**：**AGPL-3.0**（GNU Affero General Public License v3.0）
2. **技术栈**：**FastAPI + React + Vite + SQLite**
3. **自托管**（Self-hosted）：用户完全控制数据和部署
4. **功能定位**：广告优化引擎，支持 campaign 管理和数据分析
5. **ERP 集成**：支持 **领星 (Lingxing) ERP** 集成
6. **Windows 可用**：提供 Windows EXE 可执行文件

### 差异说明

无差异。IvyeaOps 代表开源/自托管广告管理工具的崛起趋势，与 Amazon Ads MCP Server 形成互补生态。

---

## 信息源状态汇总

| # | 源 | 日期 | 状态 | 一致性 |
|---|---|---|---|---|
| 1 | Amazon Ads MCP Server | 2026-02-02 | 已验证 | 一致 |
| 2 | Canopy Management 10 Tips | 2026-03-19 | 已验证 | 一致 |
| 3 | Autron Campaign Structure | 2026-05-04 | 已验证 | 一致 |
| 4 | Trellis AI for Amazon Ads | 2026-05-29 | 已验证 | 一致 |
| 5 | PPC Land Consent Deadline | 2026-05-14 | 已验证 | **关键截止日** |
| 6 | Amazon Creative Agent | 2026-02-25 | 已验证 | 一致 |
| 7 | Spotify Multi-Agent | 2026-02-19 | 已验证 | 一致 |
| 8 | IvyeaOps GitHub | 持续更新 | 已验证 | 一致 |

---

## See also

- [2026 Strategy Frameworks](./2026-strategy-frameworks.md) — ACoS→TACoS、COSMO、campaign架构、竞价策略
- [2026 Market Intelligence](./2026-market-intelligence.md) — 市场规模、竞争格局、隐私合规
