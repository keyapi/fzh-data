---
type: Research
title: 深圳办公室海外出口 + ChatGPT Business —— 封号风险、方案矩阵与推荐路线
description: 读取并复核 ChatGPT 分享对话，结合项目实际网络资产调研；结论：深圳"各自翻墙"在封号维度不劣于统一出口，放设备的理由应是管控而非封号
---

# 深圳办公室海外出口 + ChatGPT Business 调研 (2026-09-15)

## 一句话结论

1. **从封号角度，"公司统一出口"比"各自翻墙"更危险** —— "共享代理出口"是 OpenAI 风控的首要扣分项，且**一人违规全段连坐**。北京现在 8 人共用一个出口 IP 正命中这条。
2. **所以"深圳要不要放软路由"不应由封号风险驱动**，只能由**管控**（可见、可限、可收回）驱动。
3. **① 官方网页版 + ② 不发公司凭证给员工 + ③ 不上设备** 三者不可能同时满足 —— 必须放弃一个。
4. **当前选定的落点**：接受现状（深圳各自翻墙）+ 落地 §7 第一步的五条纪律（¥0，当天可做）。

---

## 1. 背景与引用

### 1.1 讨论来源

用户与 ChatGPT 网页版的三轮对话，分享链接（原始 URL，保留备查）：

**https://chatgpt.com/share/6aa8d85e-7e14-83eb-8255-5fd68aa11ecd**

页面标题：`ChatGPT - ChatGPT Business 合规与注册`

> **注意**：ChatGPT 不知道本项目已记录的实际网络资产，其建议部分脱离实际。下文 §4 逐条核实。

### 1.2 三轮问答摘要

| 轮次 | 用户问了什么 | ChatGPT 的核心结论 |
|---|---|---|
| 1 | 用美国分公司注册 ChatGPT Business 是否可行；中国员工翻墙使用是否会被封 | 建议美国分公司做 Customer / Billing / Workspace Owner；但**中国大陆不在支持地区，且 Business 条款限制的是 End User 的访问位置，不是公司注册地**——换主体也不豁免。另建议 Owner 用公司邮箱而非个人 Gmail |
| 2 | 先买 2 个 Standard 验证；中国公司一般怎么设置？北京有 OpenWrt/OpenClash，深圳没人管 | 赞同 2 seat 做北京/深圳 A/B 测试；建议**规则分流**而非全量代理；提醒"固定海外 IP ≠ 合规豁免"；**未提"共享出口会被连坐封禁"** |
| 3 | 北京电脑/OpenWrt/上海阿里云/US Vultr 已装 Tailscale 作 OpenClash 兜底；深圳怎么弄；Tailscale 免费版限制；请调研中国公司案例 | 建议深圳放**一台网关**做 Tailscale subnet router（员工电脑不用装）；区分 subnet router / exit node；免费版 6 users；**未找到**中国公司公开长期用 Business 的证据 |

### 1.3 用户在对话中自述的实际配置（需与项目文档核对）

- 北京办公室：OpenWrt + OpenClash 控制流量出口，**OpenAI 走日本线路**
- OpenClash 的兜底：北京电脑 + OpenWrt + 上海阿里云服务器 + 美国 Vultr 服务器都装了 Tailscale，作为供应商瘫痪时的应急
- 深圳办公室：无专人负责网管，各人还在用自己的翻墙
- 深圳需求：ChatGPT / Codex，**本地软件和网页版都用**

---

## 2. 项目现状（事实，含出处）

| 事项 | 项目实际记录 | 出处 |
|---|---|---|
| 北京拓扑 | 联通光猫 → OpenWrt（OpenClash tproxy + Tailscale）→ 新华三 → WiFi 网段，三层 NAT。**具体网段与设备地址见模块文档，本文不复述** | `us_openai_api_proxy/docs/office-lan-access.md:21-62` |
| 翻墙主线路 | 商业代理订阅；**2026-08 更换过供应商**（具体名称按模块脱敏约定不入库） | `us_openai_api_proxy/docs/log.md:19-24`（v0.14「更新办公室代理订阅与策略组映射」） |
| OpenAI 分流 | OpenClash 里 openai 走**日本**线路 | 用户本次口述（§1.3） |
| 兜底线路 | OpenClash 一个应急策略组指向**公司自建的 SOCKS5 出口**（经上海跳板一跳，最终落在美国服务器） | 历史快照 `operations.md:174-266`（见下方提示） |
| Tailscale 节点 | 北京 OpenWrt / 上海服务器 / 美国服务器 / 用户电脑 —— **同一个微软账号**（这是免费版 6 用户限制的关键事实） | `office-lan-access.md:56,94-96` |
| 公司 AI 网关 | `api.vilavi.cn`（上海阿里云 nginx）：`/` new-api、`/sellfox` 赛狐代理、`/oidc` 钉钉 SSO | `CONCEPTS.md:39-40` |
| 账号生命周期管控 | **入职钉钉登录自动开通；离职自动封号**（`user_leave_org` Stream 事件 + `getbyunionid` 60121 双通道），2026-09-08 生产实测封掉 3 个真实离职者，有 `dingtalk_identity_map` + `offboarding_audit` 审计表 | `docs/solutions/integration-issues/dingtalk-offboarding-hardening.md`；术语定义见 `CONCEPTS.md:42-43` |
| CLIProxyAPI | US Vultr 上把 ChatGPT/Codex 订阅转成 OpenAI 兼容 **API**（**不是网页版**）；北京 3-5 名同事零安装经 LAN 网关共享 | `us_openai_api_proxy/docs/lan-gateway.md:11-46` |
| 深圳现状 | 无 IT 人员、无 OpenWrt、公网 IP 动态；已有 `api.vilavi.cn` 反代方案（~30ms 直连上海） | `office-lan-access.md:264-299` |

> **隐私边界（重要）**：该模块的规则是「订阅与访问凭据、私有地址、网络拓扑均不入库」（`us_openai_api_proxy/docs/log.md:10`、`.agents/skills/us-openai-api-proxy/SKILL.md:32-36`）。**本文因此不复述订阅供应商名、私有网段与隧道拓扑细节**；需要具体值时从受控环境（模块 `.env`，位于父仓库 `D:\Work\赛狐\Cursor`）或模块文档取。
>
> ⚠️ **已知偏差**：`us_openai_api_proxy/docs/office-lan-access.md` 与 `docs/solutions/best-practices/adobe-genuine-prompts-office-openclash.md:55` 中已含私有地址/供应商名，与上述规则不一致——属既有情况，待单独处理。

> **历史快照提示**：`.codex_tmp/sellfox-suite-pairing-audit/` 下的 `operations.md` 是**迁移前的快照**，其中记载的订阅供应商**已经停用**，**不要当现值引用**。判据与来源优先级见 `docs/solutions/documentation-gaps/module-current-config-source-of-truth.md`。

---

## 3. 封号风险调研（要求：有实际记录）

### 3.1 有实际记录的大规模封号事件

| 时间 | 事件 | 关键记录 |
|---|---|---|
| **2023-04** | 数百万账户一夜被封 | "亚洲是重灾区，其中不少都是国内的账号"，开通 Plus 付费的账号也未能幸免。归纳原因：批量注册、**经常切换节点或账号同时挂载多个地区 IP**、频繁通过不支持区域（如香港）访问、API 滥用、**同一台机器先后登录不同账号**。有知乎用户指出"一般不是封号，而是**封 IP**" |
| **2026-06** | V2EX 等中文开发者社区同时大量冒出 ChatGPT 与 Codex 被封帖 | "**部分账号是正常付费、正常使用、毫无脚本痕迹也被一刀切扫到的**" |

### 3.2 2026 现行风控：三层机制

1. **IP 类型识别 + 信誉评分** —— 按 ASN 归属判断住宅 ISP 还是机房
2. **行为模式 + 设备指纹** —— 跨国跳转、一机多号
3. **支付区域校验** —— Stripe 独立一层；有数据显示加州住宅 IP 支付成功率 92%，而"同为纯净住宅 IP 但地区不同"可暴跌至 14%

### 3.3 明确的扣分项清单

| 扣分项 | 描述 |
|---|---|
| **共享代理出口** | 同一 IP 后面几百上千人同时出口，**一个用户违规全段连坐** |
| **频繁跨国跳转** | 同一账号 30 分钟内出现日本、新加坡、美国三个出口 IP |
| **已知机房 IP 段** | AWS / GCP / DigitalOcean 等公有云出口被标记为"非住宅" |
| **被动污染（连坐）** | V2EX 2026-06 有用户报告"**使用美国住宅宽带 + 苹果内购、网络条件良好**"的账号同样被封 —— 说明 IP 段的历史关联也会造成影响 |
| 一机多号 | 同一设备登录多个 OpenAI 账号 |
| 支付 | 虚拟卡 / 一次性卡、同一张卡绑多个账号、卡的发卡地区与账号 IP 严重不匹配 |
| 高危叠加 | **Outlook / Hotmail 注册邮箱 + 共享代理 IP** 两个条件叠加 → 自动风控几乎直接判定违规 |

### 3.4 三个关键发现

**发现一：ChatGPT 与 Codex 共用同一 OpenAI 账号体系。**

账号被停用后，网页登录不了、Codex CLI 同样登录不了、账号下的 API key 也一起失效。

→ **"Codex 走一条路、网页版走另一条路"不能隔离风险**。只要用的是同一个 Business 账号，账号本身被封就一起没了。

**发现二：从封号角度，「统一出口」比「分散」更危险。**

"共享代理出口"是**首要扣分项**，且"一人违规全段连坐"。因此：

- **北京现在 8 人共用一个出口 IP** = 正好命中这条；且机场落地通常是机房 IP（再命中一条）。**这是风险偏高的配置，只是目前没被扫到。**
- V2EX 讨论中「统一走一样的渠道容易团灭」的说法，**在封号维度上是正确的**；而 ChatGPT 建议的"公司统一出口"反而**增加**共享度。
- 但**分散也不安全**：深圳同事若都用同一个热门机场，那个出口同样是"万人骑"。
- **真正的分水岭不是「统一 vs 分散」，而是「这个出口 IP 是干净的住宅 IP，还是被共享的机房 IP」。**

**发现三：企业账号与个人账号的处置不同。**

V2EX 讨论指出"**正常企业即使被 ban 也可以恢复**"（X 上美国某农业科技公司 110 名员工 Claude 集体被封事件，后续"已恢复"）；而个人号申诉"**几乎没有实质作用**，官方通常模板回复'违反政策，无法恢复'，且不退款"。

### 3.5 必须诚实说明的空白

**我没有找到"中国公司的 ChatGPT Business workspace 被封"的公开具体案例。** 公开记录几乎都是个人号 / Plus 号。

可能原因：Business 客户数量少；且有合同与付款关系，OpenAI 处置更谨慎（与发现三一致）。

**因此"Business workspace 会不会被连坐封禁"目前无实证，只能按 Plus / 个人号的风控规律外推。** 这是本调研最大的不确定性，列为开放问题（§8）。

### 3.6 由此对决策的影响

- **"深圳各自翻墙"在封号维度上并不比北京统一出口差，甚至因 IP 分散而略优。**
- 所以「**为了降低封号风险而必须深圳放设备**」这个理由**不成立**。
- 反过来，**深圳放设备做统一出口，在封号维度上是负收益**（把 8 人重新汇聚成一个共享出口）—— 除非那台设备挂的是专门优化的干净住宅节点，且只分流 AI 域名。

---

## 4. 逐条核实 ChatGPT 的说法

| ChatGPT 说 | 核实 | 依据 |
|---|---|---|
| 中国大陆不在 OpenAI 支持地区 | ✅ 属实 | OpenAI Help Center 不支持国家列表（中国大陆 / 香港 / 澳门 / 俄罗斯均不在） |
| Business 条款限制 Customer 与 End User 的访问位置，不是公司注册地 | ✅ 属实 | OpenAI Business Terms §16.11/16.12（Export Controls and Geographic Use Restrictions），违约可按 §8 暂停服务 |
| 固定海外 IP ≠ 合规豁免 | ✅ 正确 | 同上 |
| Tailscale 免费版 6 users、设备不限 | ✅ 属实，是 **2026-04-08 Pricing v4** 改版的结果（此前 3 users）；6 是 **tailnet 级用户数**，第 7 人会把整个 tailnet 拖进付费 | <https://tailscale.com/pricing> |
| Tailscale Personal 仅限非商用 | ✅ 属实，原文 "only suitable for non-commercial use" | 同上 |
| Tailscale Standard $8/user/月 | ✅ 属实 | 同上 |
| subnet router ≠ exit node | ✅ 属实；Tailscale 2026 建议两者**分开部署**（SNAT 冲突） | Tailscale Docs；<https://github.com/tailscale/tailscale/issues/18725> |
| **深圳做 subnet router 就够（员工不装客户端）** | ❌ **不准确** | subnet router 让 tailnet 访问某个**私网段**；深圳要的是**互联网出口**，那是 exit node 的活。且 exit node 是 `0.0.0.0/0` **全量**，做不到"只让 ChatGPT 走海外"的域名分流 |
| **公司统一出口更安全** | ❌ **与实证相反** | 见 §3.4 发现二 |
| Codex-only seat 2026-06-24 停售 / Standard $25 月付、$20 年付 | ⚠️ 未能独立验证（OpenAI Help Center 抓取受限），**不影响结论** | — |
| 案例：Phi Browser 招聘页写 ChatGPT Business | ⚠️ 未能独立验证 | — |
| "没有公开证据证明中国公司官方长期使用 Business" | ✅ 与独立调研一致 | V2EX t/1211041 |
| **未提：共享出口连坐风险** | ❌ **重大遗漏** | 见 §3.3、§3.4 |
| 未提：ChatGPT 与 Codex 共用账号体系 | ❌ 遗漏 | 见 §3.4 发现一 |

---

## 5. 四个疑问的正面回答

### Q1. Tailscale 免费版 6 个账户 —— 是否只能用一个账号组网？

**限制的是「用户数 6」，不是「设备数」。一个用户可以有无限台设备。**

项目现状就是 **1 个微软账号挂了 4 台设备**（北京 OpenWrt + 用户电脑 + 上海 + US Vultr）。深圳设备挂同一账号即可，**不新增 user、不触发限制、¥0**。

用户原话中"只能用一个账号组网"——**在 6-8 人规模下反而是对的，而且够用**。

唯一顾虑：Personal 官方定位「非商用」，属 ToS 灰区。但 8 人升 Standard 是 $64/月，与预算约束不匹配。

### Q2. 能否自动转发流量到某节点？

能，但要分清两个被 ChatGPT 混为一谈的机制：

- **exit node**（`--advertise-exit-node`）：路由 `0.0.0.0/0`，**全量流量**走某台机器。**做不到按域名分流。**
- **subnet router**（`--advertise-routes=<cidr>`）：只让 tailnet 访问某个**私网段**，**与互联网出口无关**。

你要的"只让 ChatGPT 走海外、国内直连"= **域名分流**，**Tailscale 本身做不到**。必须在客户端 / 网关上用 Clash 规则实现，Tailscale 只负责提供一条能到海外节点的隧道。

### Q3. 深圳放软路由，没有维护人员？

这是真代价。但按 §3.6，**"为了封号风险"不构成放设备的理由**。

若为**管控**而放，降低风险的办法：
1. **带外管理必须先做** —— Tailscale SSH + 一台国产远程桌面（向日葵/ToDesk）双通道。否则翻墙一挂你也进不去
2. 硬件选**带 4G 备份**的（GL.iNet + USB dongle），或额外留一条国产 4G 路由做带外
3. 关键配置**云端下发**，别烧死在设备里
4. **预置 2 台**，坏了直接寄替换机

### Q4. 别的中国公司怎么弄的？

- **大公司**：企业专线（IEPL / IPLC / MPLS）+ 华为 / 深信服 SD-WAN，或 Zscaler / Netskope SASE。走公司统一出口
- **中小跨境公司（本项目规模）**：买合规 SD-WAN CPE（CPE 邮寄到站点插电即用、云后台统一配、有售后 —— 正是"没人维护"的行业正解；10 人内档约 ¥10,000/年）
- **极小团队**：各自机场 + 公司报销。V2EX 上有实务者认为这反而更抗团灭
- **真合规派**：转 Azure OpenAI（中国区）/ 通义 / DeepSeek / 私有部署

公开网络**查不到**中国公司长期使用 Business 的完整案例（与 ChatGPT 的结论一致）。

### Q5.「统一出口容易团灭」是什么情况？

见 §3.4 发现二：8 人共用同一出口 IP → OpenAI 判定为"账号工厂 / 批量操作" → **一人违规全段连坐**。

V2EX 上实务者的说法**在封号维度上是正确的**，而 ChatGPT 的相反建议缺乏实证。

同帖反方观点（AIXAPI）：分散的家宽 / 机房混杂 IP 更容易触发风控，统一走企业专线 IP 反而更稳。两说都有道理 —— 区别在于你怕的是「IP 被标记」还是「单点故障」。

### Q6. 用户的洞察：判断线路的唯一标准是"GPT 能不能用"

**确认成立。** 不需要精确控制出到哪个国家。

香港节点也能用 GPT 很正常 —— **决定因素在国家之外：落地 IP 的质量**。机场的"ChatGPT 解锁"通常靠原生 / 家宽落地 IP，或后台把 `openai.com` 单独分流到特定落地。

**所以"固定出口 IP"意义不大，「IP 干净」才有意义** —— 不必为"必须出美国"之类的目标买单。

---

## 6. 方案矩阵

**约束**：❌ SD-WAN CPE ｜ ❌ 不把线路凭证发给员工 ｜ ❌ 不复用北京订阅 ｜ ✅ 要官方网页版 ｜ ✅ 预算敏感

| 方案 | 员工电脑上有什么 | 新增成本 | 深圳硬件 | 封号风险 | 管控力 |
|---|---|---|---|---|---|
| **A. 收进 `api.vilavi.cn`** | 只有他自己的 `sk-` token | ¥0 | 无 | 低（不碰 OpenAI 账号） | **强**（离职自动封号、用量可见） |
| **B. 深圳旁路网关 + 另开订阅** | 无（订阅只在设备里） | ~¥200/季 | 1 台 | **↑ 汇聚成共享出口，反而升高** | 中 |
| **C. 员工电脑 Clash + 公司代理一人一号** | 公司代理账号密码 | 低 | 无 | 同现状 | 中（可看用量、可单人吊销） |
| **D. 维持现状（各自翻墙）** | 不适用（用他们自己的） | ¥0 | 无 | **中（IP 分散，略优）** | **弱**（不可见、不可限） |

### 由约束推出的结论

1. **① 官方网页版 + ② 不发公司凭证 + ③ 不上设备** —— 三者不可能同时满足，必须放弃一个。
2. **但按 §3.6，选现状（D）在封号维度上并不劣**，代价只是**管控弱**。
3. **决策点收敛为一个问题：你愿意为「管控」付多少钱 / 多少维护成本？**
   - 不愿付 → **D + 落地 §7 第一步的五条纪律**（¥0，当天可做）
   - 愿付 ~¥200/季 + 你的维护 → **B**（须配干净住宅节点 + 只分流 AI 域名）
   - 愿在员工电脑上配 → **C**（一人一号，离职只吊销一个）

> **关于方案 C 的澄清**：它本质上是"公司自建一个带认证的代理"，**性质与自建 VPN 相同**（用户已自行点破）。比直接发订阅好在：一人一号、离职只吊销一个、代理侧可看用量可限额。但仍需在员工电脑上配置，且员工可改配置（改成走自己的线对公司无害；真正的风险是把非 AI 流量指到公司线，代理侧限额可挡）。

> **关于 OpenWrt 上的 IPsec**：那是 strongSwan（IKEv2/IPsec），用途是**把远程设备接入公司内网**，或两台路由器间建隧道。**它解决不了"出墙"** —— 隧道出来之后出口 IP 仍是公司路由器（在国内），要出墙还得再过 OpenClash。

---

## 7. 推荐路线

### 第一步（¥0，立即）：接受现状 + 落地五条纪律

1. **OpenAI 流量收敛到一条固定线路** —— 不要今天日本明天美国（跨国跳转是明确扣分项）
2. **不要让非 AI 流量走 AI 出口** —— YouTube / 下载最容易把 IP 拖进风控库
3. **一人一号，不共用设备登录**
4. **支付走美国分公司的正规实体卡，一卡一号，卡地区与账号地区一致**
5. **注册邮箱避开 Outlook / Hotmail + 共享 IP 这个高危组合**

**这一步不花一分钱，且在封号维度上优于"统一出口"。**

### 第二步（可选，¥0）：深圳编码类 AI 用量收进 `api.vilavi.cn`

Codex++ / Cursor / WorkBuddy → `https://api.vilavi.cn`（项目里已有，~30ms 直连上海）。员工在自己账号下领 `sk-` token，**离职自动封号**，零人工。

**注意两个限制**：
- 这**不覆盖** chatgpt.com 网页版
- 若 Codex 要用 **Business 席位**登录，那仍走 OpenAI 账号体系，**风险与网页版同源**（见 §3.4 发现一）

### 第三步（仅当"管控"成为刚需时）：再讨论 B 或 C

- **B 的正确形态**：深圳 1 台软路由（北京预配好寄过去）+ 专门优化的干净住宅节点 + **只分流 AI 域名**（避免 8 人共享出口放大风险）
- **C 的正确形态**：上海起一个有认证的代理，**一人一号**，代理侧限额 + 审计
- **两者都必须先做带外管理**，否则翻墙挂了远程也进不去

---

## 8. 开放问题（不做断言）

1. **Business workspace 被连坐封禁是否有实证** —— 目前查无公开案例，需持续观察（§3.5）
2. **当前订阅套餐的实际流量额度与北京用量** —— 决定 B 是否必须另开订阅。若深圳只分流 AI 域名，文本流量极小（每人每天几十 MB 量级），增量可能可忽略
3. **深圳 → 上海自建 SOCKS5 出口 经 Tailscale 的实际连通性与延迟** —— 北京侧已知走 `DERP(hkg)` 中转，深圳未实测
4. **US Vultr 1C2G 能否承受新增并发**（若考虑把 CLIProxyAPI 或兜底链路开放给深圳）

---

## 9. 来源

### 封号与风控

- [ChatGPT、Codex 账号被封的常见 6 大原因与解锁方法（2026）](https://x.com/uniswap12/status/2072553437284503930)
- [ChatGPT 账号风控的底层逻辑：从 IP 检测到支付限制的技术分析 — 腾讯云](https://developer.cloud.tencent.com/article/2723465)
- [ChatGPT 与 Codex 封号常见六大原因及自查排查指南（2026版）— 腾讯云](https://cloud.tencent.com/developer/article/2688138)
- [ChatGPT 账号异常与封号常见原因分析及开发者保号技术实践 — 腾讯云](https://cloud.tencent.com/developer/article/2645415)
- [ChatGPT突遭大面积封号，网友应急出解封教程 — 36氪](https://m.36kr.com/p/2199302593300611)
- [ChatGPT大规模封锁亚洲地区帐号 — 卢松松博客](https://lusongsong.com/blog/post/17032.html)
- [ChatGPT 提示"检测到可疑活动/异常登录"怎么办 — IPFoxy](https://www.ipfoxy.net/blog/use-cases/2791)
- [ChatGPT 提示"验证过程中出错"或 account_deactivated？Outlook 邮箱用户必看 — imooc](https://www.imooc.com/article/392115)
- [Why ChatGPT Accounts Get Banned Even with Static Residential IPs — IPDeep](https://www.ipdeep.com/static-residential/chatgpt-static-residential-ip-ban)
- [OpenAI bans Russian ChatGPT accounts in influence campaign — Quartz](https://qz.com/openai-banned-russian-chatgpt-accounts-influence-campaign-082526)

### 企业采购与合规

- [请教 Claude 企业版/团队版的正规开通、付款方式和封号风险 — V2EX](https://v2ex.com/t/1211041)
- [公司用 ChatGPT 怎么合规？6 种企业级替代方案 — Linkmetax](https://www.linkmetax.com/blog/enterprise-chatgpt-compliance-alternatives)
- [ChatGPT Team（现 Business）和 Plus 怎么选？（2026）— PayForChat](https://www.payforchat.com/articles/chatgpt-team-vs-plus-2026)
- [Export Controls and Geographic Use Restrictions (OpenAI Business Terms §16.11)](https://conductatlas.com/platform/openai/openai-business-terms/provision/CA-P-013687/export-controls-and-geographic-use-restrictions/)

### Tailscale

- [Tailscale Pricing](https://tailscale.com/pricing)
- [Tailscale subnet router vs DERP relay vs exit node](https://www.bigiron.cc/guides/tailscale-subnet-router-vs-relay-vs-exit-node)
- [`--snat-subnet-routes=false` 与 Exit Node 的冲突 · Issue #18725](https://github.com/tailscale/tailscale/issues/18725)
- [Tailscale pricing after the free plan — SSD Nodes](https://www.ssdnodes.com/learn/tailscale-pricing-explained)
- [Tailscale Price Increase 2026 – NetBird as Sovereign Alternative](https://birdhost.de/en/blog/tailscale-preiserhoehung-2026-alternative)

### 中国公司跨境网络做法

- [企业如何合规使用 ChatGPT / Claude？SD-WAN国际专线接入全流程 — 掘金](https://juejin.cn/post/7632281566597054505)
- [企业开通国际网络专线有什么要求？需要哪些资质？— SegmentFault](https://segmentfault.com/a/1190000047389682)
- [SD-WAN 跨境组网解决方案 — IPdodo](https://www.ipdodo.com/network-acceleration2)
- [OSDWAN 明点跨境 — 网络方案与价格](https://www.osdwan.com)
- [利用 SD-WAN 和专线混合组网 — AWS 官方博客](https://aws.amazon.com/cn/blogs/china/speed-up-idc-multi-cloud-data-center-domestic-foreign-enterprises-using-sd-wan)
- [数字出海 — 中国联通 U PLUS](https://www.cuguplus.com/zh-hans/globalization)

### 项目内部文档

- `us_openai_api_proxy/docs/office-lan-access.md` — 北京办公室拓扑 + Tailscale 实施 + 深圳方案
- `us_openai_api_proxy/docs/lan-gateway.md` — LAN 网关（CLIProxyAPI 共享）
- `us_openai_api_proxy/docs/log.md` — v0.14 订阅供应商迁移
- `us_openai_api_proxy/docs/operations.md` — 脱敏版运维手册
- `docs/solutions/integration-issues/dingtalk-offboarding-hardening.md` — 离职自动封号双通道
- `docs/solutions/best-practices/adobe-genuine-prompts-office-openclash.md` — OpenClash 规则与三层 NAT 限制
- `CONCEPTS.md` — `api.vilavi.cn` 等术语定义
