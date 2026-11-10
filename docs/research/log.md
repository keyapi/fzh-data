---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

## 2026-11-10

- **新增**: [2026-11-10-douyin-live-commerce-ecosystem.md](2026-11-10-douyin-live-commerce-ecosystem.md)（技术版）与 [2026-11-10-douyin-live-commerce-management-brief.md](2026-11-10-douyin-live-commerce-management-brief.md)（管理层版）— 抖音直播电商生态调研。起点是「工厂开展抖音直播卖货，客服机器人/订单处理/备注传产线/投流/风控该怎么做，EN 能承担多少」。前提确认为**自营品牌 + 自有工厂生产发货**。
  - **结论**: 抖店开放平台对**商家自研（自用型）应用**门槛不高（营业执照 + 软著 + 系统说明书，审核 1–3 工作日，仅授权自有店铺）；ISV 才需 ≥30 人团队。订单（`buyer_words`/`seller_words`/`encrypt_*`）、售后、电子面单（**强制官方**）、**客服机器人权限包**（`/rights/getProductPrivileges` 的权限包明确含「三方客服 + 客服机器人」）、千川 M-API 均有官方接口。
  - **关键澄清**: 「买家备注传不到一线生产」是误读 —— 平台限制的是**收件人明文个人信息**流转，不是业务指令。手动解密 + 复制地址 = 一级隐私违规（单次 2–4 分、累计 12 分清退）。
  - **负面结论**: 直播间弹幕无面向商家的官方接口（官方那套属「直播小玩法」，需抖音云 + 内网专线）；第三方浏览器工具抓中控台归入「非官方工具」风险，不建议。
  - **EN 定位**: 不适合作电商 OMS（无入站 webhook / 无 OAuth2 / 无工单 Doctype / SO 靠手工 Excel），适合生产·工单·BOM·出货；推荐「抖店 → 轻中间层(FastAPI) → EN」。可复用 `sellfox-api-proxy/` 与 `web_automation/dispatch.py` 的既有范式。
  - **风险口径**: 2026 发货三红线 —— 超时 1%–5%、虚假发货 25%、欺诈发货 30% + 首次冻货款 30 天（年度 4 次 → 180 天）；AI 直播须显著标识 + 虚拟人注册 + 真人驱动（2026-02-01《直播电商监督管理办法》）。
  - **5 条待核实**（均写了「若结论相反方案怎么变」）：消息推送是否须上抖店云、客服会话收发 method 与权限包、直播数据是否有官方接口、店铺解密额度数值、EN 是否已有可复用 print format。
  - **纪律**: 第三方文章的数字（68% 违规率、0.018 元/百次）一律标注为第三方说法，未写成定论。
- **同日修订（用户质疑后补证，含四处纠正）**：
  - **纠正 ①：软著是硬门槛，且不可后补。** 官方 FAQ（`question-docs/103/3226`）原文：「调用接口必须先申请资质…软著的要求：必须提供由国家版权局颁发的软件著作权证书…著作权人需与您店铺 & 开发者实名认证一致…在其他软著认证平台均不符合要求」。**ERPNext 是 GPLv3、著作权属 Frappe，不能用于登记**；能登记的是我们自研 app（`key_test`/`tongtool_integration`）。软著常规 30–60 个工作日 ⇒ **从今天算最快 1.5–3 个月才能调接口**，这是 P1 的关键路径，比写代码长。另记 2026-03 版权中心新规的两个摩擦点（手抄"未使用 AI 开发"承诺、AI 代码查重），来源为行业解读，需以公告为准。
  - **纠正 ②：「EN 不适合当电商 OMS」说过头了。** 用户指出 EN 本来就可任意定制、`tongtool_integration` 已是"单向拉取 + 写单"的先例，外挂中间层同样是写代码。已改为：**订单接入优先做成 EN 独立 app（与 `tongtool_integration` 同构）**；该买的是「电商作业台」（波次拣货、面单池、售后审核台、客服会话），理由是投入产出比与生产风险，不是"做不到"。
  - **纠正 ③：`/order/batchDecrypt` 属「基础 API」不是「增值 API」。** 官方《收费接口 & 应用类目》（2026-06-16）明确列出 batchDecrypt 为基础 API，云外可调、单价 ×10。此前根据第三方文写的"解密属增值 API / 必须云内"**已删**；流传的"2023-08-31 起解密须云内"在官方规则里未找到，降级为待工单确认，且**不影响主方案**（我们走密文打单，本就不调解密）。
  - **结案**：抖店云不再是悬念 —— 官方《技术服务费规则》V1.3：基础 API 云内 0.018 / 云外 0.18 元每百次（×10），增值 API 云外默认禁止；**自用型应用 2023-06-01 起同样收费**。按我们的量算云外约 **108 元/月**，不构成"必须上抖店云"的理由。
  - **纠正 ④：自研客服的路径是「飞鸽插件」不是服务端消息 API。** 公开飞鸽 API 只有工具/工单类，没有收发买家消息的 method；官方扩展点是 `抖店应用 → 飞鸽插件`（FAQ 里有"没有开发者模式权限""onShow 首次进入插件时"等条目），字节 `mona` 运行时 README 也提到会话切换监听需 `user_id` 权限包 ⇒ **能力存在但需开通权限后实测**。
- **同日三改（业务方排除 SaaS 后）**：
  - **买 OMS 路线正式排除**。业务方：跨境侧通途与赛狐都是 SaaS、**不能定制且难用**，国内 OMS 大概率同类。§7.4 的 C 选项降为"仅作对照"，推荐回到 A（EN 独立 app）。
  - **新增 §7.5「不等软著的最短路径：Excel 桥」**。软著要 1–3 个月，但「简单订单处理」可以今天开工：抖店后台导出（仅 `订单号/SKU/数量/买家留言/下单时间` 白名单列）→ 导入 EN 生成 SO/工单 → 发货仍在抖店后台用官方面单。**不调解密、不需要 API、不需要软著、不需要抖店云**，与现有「通途导出 → 本地处理 → 建 EN 单据」习惯一致，首版约 2–3 人天。
  - **路线图加 P0.5**：Excel 桥独立成阶段，P1 的 API 自动化只替换"取数"这一段，备注判定与打印格式**不重写**。
  - **新增待核实 #7**：抖店后台导出是否支持自选字段、默认模板是否含明文收件人。
- **同日四改（客服细节 + 发货闭环 + 合规补漏）**：
  - **官方飞鸽机器人是免费的**：抖音电商学习中心原文「智能辅助模式，抖店商家直接使用，**无任何收费项**」⇒ 无坐席费、无 token 费；代价是只做辅助、知识仍需人工录。
  - **飞鸽没有"发送消息"的服务端接口**（开发者实测原话），业界所有"AI 客服接大模型"（含开源 ChatGPT-On-CS、gofly）本质都是**浏览器/Electron 模拟输入**。这解释了为什么自研只能走飞鸽插件。
  - **补一条此前漏掉的合规门槛：AI 客服算法备案**。依据《算法推荐管理规定》第 24 条、《生成式AI服务暂行办法》第 17 条；三档：纯规则仅算法备案 / 调已备案第三方模型需算法备案+大模型登记（约 3–5 个月）/ 自研微调需算法备案+大模型备案（约 6–9 个月）。责任主体按"用自己账号对外提供服务"认定 ⇒ 商家自建同样可能担责。**来源为资质代办行业解读，适用性需法务/网信确认**，已标为待核实 #9。
  - **澄清「挂靠 ISV」= 违规**：《服务商违规处罚及退出机制》把「未经授权将所涉服务转委托第三方」「滥用/售卖平台接口」「账号擅自借给第三方」列为一**级违规**（扣全额保证金、清退）。合法形态只有"订购 ISV 产品"或"委托 ISV 定制开发"。另：**AI 智能客服是「客服工具」下的二级类目，面向服务商**，不是商家自研类目。
  - **补发货闭环**：取号→官方面单→点发货→**单号与轨迹由平台闭环**，无需我们回传；考核看**真实揽收时间**，故"提前点发货后补单号"踩虚假发货。与跨境 TikTok 对比：形态像，但抖店强制官方面单、更锁死。
  - **新增待核实 #8**（官方机器人知识库是否支持批量导入）、**#9**（算法备案适用档位）。
- **同日五改（自研先例核查，新增 §11）**：
  - **结论：订单侧自研有大量真实先例，是行业常规路径；客服侧也有人做，但只能插件模拟。** 技术上确实不是问题，成本在资质与长期维护。
  - **证据（均可点开验证）**：① 开源全套 OMS `zeasin/qihang-oms`（SpringBoot3，含抖店订单/售后/电子面单/发货/多租户）；② 多语言 SDK —— Java `cnJun/sdk4-jinritemai`、PHP `iMactool/jinritemai`、Python `minibear2021/doudian`（显式支持自用型+沙箱）、Go `zsmhub`、Spring Boot `chrisis58`、PHP 710+ 接口 `whalesky-labs`；③ 生产踩坑文（增量窗口取 `当前时间-60s` 防漏单、`order_id` 幂等、状态映射留未知分支）；④ 资质流程已常规化（51CTO 完整清单；官方 FAQ 有"没有软著怎么办"）；⑤ 旁证：点三把「中大型企业构建自研 OMS/ERP」列为客户群。
  - **客服侧**：开源 `cs-lazy-tools/ChatGPT-On-CS`（AGPL，支持抖店/飞鸽、可接 DeepSeek）与商业 gofly 同构 —— 都是**插件模拟**，因飞鸽无发送消息接口。
  - **两个坑产业**：① 聚合 API（点三/小于科技）可绕开软著门槛，但字段裁剪、稳定性依赖中间商、迁移有改造费 —— 必须封在独立适配层；② ISV 的"自研维护成本极高"说法**风险真实但结论为卖 SaaS**，已有开发团队的账要自己算。
  - **修正整体口径**：前几轮的谨慎主要卡在"资质 + 用户已排除 SaaS"，不是技术。推荐顺序不变但理由更清楚 —— **Excel 桥跑通闭环 → 软著并行办 → 换 API 只替换取数层**。

## 2026-09-21

- **新增**: [2026-09-21-sellfox-amazon-settlement-reports.md](2026-09-21-sellfox-amazon-settlement-reports.md) — 赛狐 API 拉 Amazon 账期报表的可行性与覆盖度实测。起点是「财务报税要各账号 Amazon 账期报表，现在只能拿 PDF 自己算」。结论：**能拉，但只有「插件获取报告」一条路，且 API 不可触发抓取**。赛狐侧三条路径实测分工：①`亚马逊原报告`（`report/center/add.json`）是**赛狐服务端生成**，报告类型枚举里**没有账期/结算**；②`自定义报表`（`custom/report/*`）是赛狐自建分析表，非 Amazon 结算文件；③`插件获取报告`（`report/center/task/getPlugPageList.json`）**唯一含账期**，靠浏览器插件在账号登录态下抓回存 COS，接口是**纯读**。旁证：`创建报告任务` 的 `reportType` 只支持 `PRODUCT_SALE_REPORT` 一个值 ⇒ 抓取只能在 UI 侧发生。
- **覆盖度实测**：90 家 Amazon 店，**只有 39 店有数据，完全没抓过 51 店**（9 个店群：Centrade-WOWMAX(2)、TOODDLY-Daneey(2)、VERCART(12)、北京固祥-US(4)、北京如森-Rucener(12)、北京如泱-BJRYECLTD(2)、北京熙锦-Jalnoddsa(2)、方州汇绍兴-Xalviortex(3)、百纳-BNCKTRD(12)），另 25 店缺部分月份。**只有 2026-06 / 2026-07 两个月，8/9 月一条都没有**。只有 reportType 3(Transaction) 与 4(Summary) 存在。覆盖呈**整店群**式 ⇒ 人工按品牌逐个执行，非周期性任务。
- **下载约束（关键）**：`fileUrls` 是 **1 小时有效的腾讯 COS 预签名 URL**（含 `q-sign-time`）⇒ **不能存链接**，必须「拿新 URL → 立刻下载落盘」。
- **新增脚本**: `SELLFOX_API/fetch_amazon_settlement.py`（下载归档，实测 **79 文件 / 0 失败 / 34MB**；产出 `_manifest.csv`、`_gaps.csv`、`_failures.csv`；判扩展名按**魔数** `PK\x03\x04`→zip、`%PDF`→pdf）与 `SELLFOX_API/probe_amazon_reports.py`（覆盖度矩阵快查）。
- **内容抽验**：最小 zip(758B, IE/06) 解出 10 行 CSV（仅表头，当月该站点确无交易，**非错误页**）；最大 zip(44KB, US/06) 722 行交易；PDF 用 pypdf 读出 1 页文字含 `Seller fulfilled selling fees` —— 均为真报表。
- **口径结论**：用户明确**只要 Amazon 官方报表、不要赛狐自算口径**（怕不准）⇒ 插件是唯一路径，51 店需运营补抓。曾评估并被否决的替代方案（`monthProfit/shopSummary` 服务端销售额、覆盖全店但属赛狐口径）已留档，以免将来重复提议。
- **新增**: [2026-09-21-sellfox-walmart-settlement-api.md](2026-09-21-sellfox-walmart-settlement-api.md) — 赛狐 Walmart 账期（结算明细）API 实测可行性。起点是「platform-account-reconciliation 的账期数据源一直是财务手工 xlsx，能否走 API」。结论：**能**。`POST /api/financial/walmartReport/queryStatementDetail.json`（公开 OpenAPI，非私有接口），App 权限已开通 `code=0`，**`periodStartDate`/`periodEndDate` 实测 200/200 行非空**；实测窗口 `2026-08-01→09-21`、店铺 `598030 Centrade US` 共 263 行（200+63），窗口内仅 1 个账期 `2026-08-08→2026-09-05`。EN 侧 `platform_code=walmart_api`、`name=WM-{po}`、`sale_account=WM-CtrdUS`，赛狐 `purchaseOrder` == EN `platform_order_id` **匹配 44/44 = 100%**，`partnerItemId` == EN `Item.platform_sku`。
- **纠偏**: 现有设计文档计划扩展的 **Wayfair WFUS 拿不到赛狐数据源** —— `多平台利润报表` 的 `platformTypes` 枚举无 `WAYFAIR`，赛狐无任何 Wayfair 财务端点；Overstock 在赛狐平台枚举里也不存在。即「Walmart 走得通、Wayfair 走不通」，与既有假设相反。
- **实证坑**: ①`data` 只返回 `rows`，**无 `totalSize`/`totalPage`**，必须翻到短页为止；②代理限流除 `code=40019` 外还有 HTTP 层 `{"detail":"Global rate limited. Retry after Xs"}`（无 `code` 字段），`client.py:114 is_rate_limited_response()` 不认这种；③EN 侧 `requests.Session()` 复用会**静默返回空**（44 个 PO 查 0 条，换裸 `requests.get` 立刻 44/44）；④EN 拆单同 OSTKUS：459 条 WM 单 / 442 个唯一 PO，9 个 PO 有 `{po}`+`{po}_1`+`{po}_2` 多条，2 个只有 `_N` 无裸单；⑤`Tongtool Order Item` 直接查列表 403，item 级只能从父单 detail 读。
- **新增脚本**: `SELLFOX_API/probe_walmart_settlement.py`（只读探针，复用 `client.py` + `repo_root.find_main_root()`；`raw_post()` 绕开 `signed_post()` 的异常包装以保留错误码，并处理两种限流形态）。
- **补测：账期勾稽 + 平台费口径结案**。摸清 **Walmart 是双周账期（14 天）**，2026 年 15 段（`08-08→09-05` 异常为 28 天，疑两期合并，待确认）。拉最近 3 个账期（384 行 / 78 单）：**销售额三个账期全部分毫不差**（1317.28 / 1511.75 / 4346.60，差异均 0.00），订单级 73/77 精确一致（4 单为跨期，销售行在更早账期）。**平台费之谜解开**：`赛狐 Commission on Product = (商品价 + Total Walmart Funded Savings) × 15%`，而 `EN platform_fee = 商品价 × 15%` —— 差额恰为「沃尔玛补贴 × 15%」，逐单 64/64 命中、汇总 28.28 vs 28.32。**结论：赛狐对，EN `platform_fee` 漏算了补贴基数**；之前的「15%~17% 费率飘忽」是基数差异造成的假象。已给 OSTKUS 未结案的 `platform_fee` 差额（-25.73/-36.52）留下复查线索。
- **新增脚本**: `platform_account_reconciliation/scripts/reconcile_walmart.py` — Walmart 账期勾稽（跨账期合并 + 口径判定），输出 `账期总览/订单级勾稽/账期费用分类/账期明细` 四个 sheet。`AGENT_HANDOFF.md` 增补 §10 Walmart 章节。
- **顺带修复**: `reconcile_ostkus.py` 的 `ENV_FILE` 原写死仓库根，**在 git worktree 里因凭证只在主仓库而跑不起来**；改为向上搜索 `EN_API/.env`（`_resolve_env_file()`）。全量测试 629 passed。
- **新增**: [2026-09-21-nas-mcp-chatgpt-feasibility.md](2026-09-21-nas-mcp-chatgpt-feasibility.md) — **群晖 NAS 接入 ChatGPT 的可行性与部署位置**。起因：FAC / 赛狐 MCP 之后，问「公司群晖 NAS 能不能也用 MCP 接 ChatGPT，部署在哪」。
  - **结论：能接，但部署在 VPS（`api.vilavi.cn`），不要部署在 NAS 上。** 硬约束是 ChatGPT 由 OpenAI 服务端来连，必须公网可达；而 **NAS 公网只开非标端口 `11024`、标准 443 不通** —— 既接不了 ChatGPT，也不该为接它把 DSM 直接怼上公网。
  - **定论过程（值得记的教训）**：我在**北京办公室内网**初测 `https://nas.vilavi.cn/` 得 **HTTP 200**，但那是个**假阳性** —— 办公室 OpenWrt dnsmasq 把该域名**劫持到内网 `192.168.100.242`**。改用**两处独立外部主机**（上海 VPS + 美国 VPS）复测：`nas.vilavi.cn:443` **两处都失败**、`:11024` **两处都 200**、对照 `api.vilavi.cn:443` **两处都 200**。与仓库既有记载吻合。**教训：在办公网内测自家公网可达性 = 无效，必须换外部视角。**
  - **顺带验证**：那次外部测试同时证明 **上海 VPS 能访问 NAS 的 `11024`** → 方案 A 的链路（VPS → NAS）本来是通的，不需要额外打通。
  - **落地设计（方案 A）**：ChatGPT → `api.vilavi.cn` nginx `/nas/*` → `nas-mcp` 容器（FastMCP）→ `nas.vilavi.cn:11024` DSM FileStation。
    **只复用现有件，不引第三方**：`NAS_API/synology.py`（认证 + `NAS_ROOT_FOLDER` 范围限制）、`sellfox_shipping/mcp_tools.py` 的 FastMCP 骨架、`sellfox-api-proxy`/`new-api` 那套「Docker + nginx 路径块」模式。**明确不推荐**网上那些第三方群晖 MCP（默认权限面覆盖 Docker/备份/Photos，而我们只要一个共享文件夹）。
  - **工具设计**：只读侧先上（`available`/`get_file_list`/`get_thumbnail`/`download_file`/`folder_exists`）；写侧默认不暴露；**`delete_folder` 建议永不暴露**（破坏性）。
  - **安全约束**：① 专用 DSM 账号 + **只读权限**（DSM API **不支持 2FA** → 必须应用专用密码）；② DSM Auto Block 白名单要放行 VPS 出口 IP；③ **证书校验要打开**（`NAS_API` 现用 `cert_verify=False`，那是为局域网设计的，走公网应校验 LE 证书）；④ 范围锁死在 `NAS_ROOT_FOLDER`；⑤ 容器侧设超时与单文件大小上限。
  - **未决（含一条对赛狐复用的共同问题）**：① **ChatGPT 能否用「自定义标头」鉴权** —— 这个结论**赛狐和 NAS 是同一个**，验一次两处受益；② VPS 出口 IP 到底是 `82.156.238.248` 还是上海这台的 EIP（加 DSM 白名单前须确认）；③ 是否只给局域网 Agent 用（那样方案 C 最省事，不必上任何公网服务）。
- **同日修订（用户反馈后深挖，含两处对本文自身的更正）**：
  - **更正 ①：`sellfox_shipping/mcp_tools.py` 不是「现成的骨架」。** 文件确实在（201 行、2026-07-16 提交），但**从未启用** —— `fastmcp` **不在根 `pyproject.toml`**（只有该模块 Dockerfile 单独装），`main.py:7-17` 用 `try/except ImportError: pass` **静默吞掉**；`AGENT_HANDOFF.md:253` 自述「legacy；根 uv 环境无 fastmcp」。相关测试验证的是**「不装 fastmcp 也能起服务」的 no-op 路径**。→ 只是「可参考形状」，复用它等于从头验证。
  - **更正 ②：「不推荐第三方群晖 MCP」下得太粗。** 深挖后有**明显更贴合**的方案：**`mrquj/mcp-server-synology`** —— `POST /mcp` **Streamable HTTP** + `Authorization: Bearer`，**默认只绑 `127.0.0.1:3020`**（要求前置反代，与本文设计一致），带**路径白名单（含 symlink 逃逸防护）**、只读启发式、**策略下不可能成功的工具直接从清单隐藏**、`/healthz` 可审计。另有 `cmeans`（权限分层 + 2FA，偏本地 stdio）、`lordraw77`（71 工具，面过宽）、`AnythingMCP`（通用网关，自带 OAuth2/RBAC，但对「一个共享文件夹」过重）。
  - **新发现 ③：暴露路径有比公网端口更好的选择。** 上海 VPS 上 tailnet 已存在，**办公室 OpenWrt 路由器在网内**（`100.124.94.69`，VPS 能 ping 通），但**路由器未 advertise 办公网段**，故**到不了 NAS**（`192.168.100.242` ping 失败）。`mrquj` 文档针对「家用路由器后的 NAS」明确建议：**别端口转发 DSM，改用私网 overlay**。→ **把 NAS 拉上 tailnet**（NAS 装 Tailscale）即可让 VPS 走私网调 DSM，**DSM 完全不用公网暴露** —— 比现在的 `:11024` 更干净。
  - **新发现 ④：Tailscale Funnel 已在用**（`https://izuf6cg60rfql8k8qbw87xz.alpines-grouper.ts.net`），当前 `/` → `127.0.0.1:3000`（即 **new-api 已被公网暴露**）。可作为 MCP 的备选前置，但优先用已有 nginx。
  - **IP 查实 ⑤**：上海 VPS（`sh-erpnext-test` / `api.vilavi.cn`）的**真实出口 IP** 就是它自己的 EIP（在该机 `curl ifconfig.me` 实得；网卡只有 `192.168.0.12` + Tailscale `100.119.28.72`）。`82.156.238.248` **不是**这台的出口 —— 它是赛狐白名单里的另一条目（2026-06-25 入仓），**两者关系仍待确认**。→ 给 DSM 加白名单应加**上海这台的出口 IP**（数值不写入仓库）。
  - **鉴权疑问已解答（⑥）**：ChatGPT 连接器 **两条路线都支持** —— A. 静态令牌（选「访问令牌/API 密钥」→ 发 `Authorization: Bearer`）；B. OAuth 2.1（PKCE + protected-resource metadata + DCR/CIMD）。但 **MCP 授权规范已把 OAuth 定为强制**（有资料称 2026-03-15 起），静态令牌属**过渡**方案，且**可发布的应用**必须 OAuth。
    **⭐ 关键：我们的 FAC 已用 OAuth 把 ChatGPT 跑通 —— 路线 B 是被验证过的；路线 A 一次没验过。** → 最低成本动作：拿一个支持 Bearer 的最小服务在 ChatGPT 里试一次「访问令牌」连接器，**10 分钟定路线**。这个结论**赛狐与 NAS 共用**。
  - **推进顺序已据此调整**：① 鉴权最小验证 → ② NAS 拉上 tailnet → ③ 实现路线二选一（先在本地跑 `mrquj` 验连通，再决定是否自建）→ ④ 前置反代 → ⑤ 安全约束。
- **同日修订二（用户补充办公室架构后，再改一次 —— 其中一条推翻了上一轮的建议）**：
  - **查实 ①：公网 443 不通的原因是「联通限制」（ISP 层封入向 443），不是配置问题。** 仓库早已记载（`NAS_API/docs/reference/nas-multi-domain-access.md` §网络拓扑：「端口转发 443 → 192.168.1.5:443（LAN 通，**公网不通 — 联通限制**）」）。→ **NAS 永远给不了公网标准 443**，除非走隧道（Cloudflare Tunnel / Tailscale Funnel，不依赖入向端口）。**这条强化了「部署在 VPS」的结论。**
  - **查实 ②：本开发机在 `192.168.10.9`（新华三网段），DNS 指向 `192.168.10.1`，该 DNS 把 `nas.vilavi.cn` 解析成 `192.168.100.242`** → curl 实连 `192.168.100.242:443` 得 200。**证实「假阳性」的机制是内网 DNS 覆盖**（且仓库记着该网段 DNS 也劫持 myds）。另注：本机 ping 不通任何 NAS 地址但 TCP 通（ICMP 被挡）。
  - **⚠️ 推翻上一轮建议 ③：不要用「NAS 装 Tailscale」。** NAS 双网口（`eth0` OpenWrt LAN / `eth1` 光猫 LAN），**默认线路是光猫侧**（用户为「可访问率」选的），但**断电重启有一定概率翻到 LAN1**（近期断电 2 次后仍保持 LAN2）。后果：
    | 路径 | 依赖 NAS 出向默认路由？ | 断电翻转后 |
    |---|---|---|
    | 公网 `:11024`（现状） | ❌ 不依赖（入向转发） | ✅ 不受影响 |
    | NAS 装 Tailscale | ✅ 依赖 | ⚠️ 可能断 |
    | OpenWrt 定向转发 | ❌ 不依赖 | ✅ 不受影响 |
    → **T1（NAS 装 Tailscale）引入的正是当初选 LAN2 想规避的风险**，已从推荐里移除。
  - **新推荐：T3 —— 在 OpenWrt 上做定向转发**（只把 tailnet 侧一个端口 DNAT 到 `192.168.100.242:5001`）：只暴露 DSM 端口、不暴露整个网段、且不依赖 NAS 出向路由。**比 `mrquj` 文档给的泛化建议更贴合你们的双网卡现实。** 若嫌麻烦，**维持 T4（现状公网 `:11024`）其实够用且稳**，用「只读账号 + 只放行 VPS 出口 IP」收敛即可。
  - 另记用户提到的已知副作用：LAN1/LAN2 **翻墙能力不一致**，群晖自动备份 Google Sheet 到 NAS 的功能受默认口影响（用户表示可后议）。
## 2026-09-20

- **新增**: [2026-09-20-sellfox-official-mcp-feasibility.md](2026-09-20-sellfox-official-mcp-feasibility.md) — **赛狐官方 MCP 可行性**。FAC（ERPNext）接通后，接着问「赛狐能不能也接 MCP」。
  - **最终结论：可用，且已用只读链路跑通。** 端点 `https://api-mcp.sellfox.com/mcp`，`streamable-http`，协议 `2025-06-18`（与 FAC 同版本），`serverInfo` = `sellfox-api v1.30.0`。
  - **两条独立鉴权路径（关键，别混）**：
    | 路径 | 头 | 来源 | 实测 |
    |---|---|---|---|
    | A. API 账号 | `X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret` | API 账号 App ID/Secret | ✅ **可用** |
    | B. MCP 管理 | 单头 `X-MCP-Key` | 后台「业务设置 → 全局 → MCP管理」 | ❌ `40027 未启用MCP功能` |
    - 客服答复针对的是 **B**；**A 现在就能用**。CSDN 教程给的正是 A（就实测而言它是对的），官方后台页面给的是 B —— **不矛盾，是两条通道**。
  - **只读链路实测通过**：① 直连 `openapi.sellfox.com` 取 token 得 `{"code":0,"msg":"success"}`（凭证有效 + **北京办公室 IP 白名单已放行**）；② MCP `initialize`/`tools/list` 200；③ 只读工具 `get_shop_page_list` 返回**真实店铺数据**。**数据未写入任何文件；生产 App Secret 未落盘、未写进文档。**
  - **工具清单：23 个 = 13 读 + 1 报表任务 + 9 个 SP 广告写**。13 个读工具已确认可用；`create_ad_download_task` 对应公开文档 `/api/cpc/download/createTask.json`（建**报表下载任务**，不改广告数据）。
  - **⚠️ 9 个 SP 广告写工具：未调用。** `edit_sp_campaign`（自述单次最多 100 条）、`edit_sp_ad_product/group/targeting`、`close_sp_negative_targeting`、`create_sp_{keyword,negative_keyword,product,negative_product}_targeting`。只读了 schema（`required=["shop_id","items"]`，`items` 是 `array<object>` 且 **schema 极薄、无字段级约束**），**未发任何写请求** —— 这些是生产广告写操作，在明确授权与隔离方案前不碰。
  - **与「赛狐广告无写 API」约束的关系（仍未定论）**：该约束在**公开 OpenAPI 层面仍成立**（本地镜像 443 篇、09-17 刷新：广告模块 `manageData/*` 全是分页查询、`hourData/*` 是报表、唯一 `create` 是报表任务）；而这 9 个工具**已能通过 MCP 触达**。**→ 既不能据此断定约束失效，也不能断定工具可用。** 要落地须显式验证。
  - **结论演变（如实保留，避免误信中间版本）**：首版「能接」→ 二版因 `40027` 改「不可用」并撤回一条过度断言 → **三版（本版）换 API 账号凭证实测只读成功，回到「可用」**。二版测出 `40027` 是因为**用错了头**（用了 B 路径），不是功能不可用。
  - **凭证归属的关键取舍**：官方 MCP 要**把生产 App ID/Secret 直接交给客户端**；自有 `sellfox-api-proxy` 则**签发自己的 key**、客户端拿不到赛狐凭证。→ 多人/多 Agent 场景优先走 proxy；官方 MCP 更适合单人自用。
  - **未决**：① 9 个写工具真伪（问客服，或在**明确指定的测试店铺**上用无副作用载荷验证 —— 需用户显式授权）；② B 路径何时开通；③ 限流是否同样适用。
  - **安全建议**（按项目既有偏好）：默认只读，建**权限收窄到只读的独立 API 账号**，把限制放在**服务端**而非 prompt。

## 2026-09-18

- **新增**: [2026-09-18-sellfox-private-api-terminology.md](2026-09-18-sellfox-private-api-terminology.md) — 区分赛狐「公开 OpenAPI」与「私有接口」。调研结论：业界**没有唯一权威说法**，最接近的是 **Shadow API（影子 API）**（Wiz/Invicti/Akto，OWASP API9:2023 Improper Inventory Management），但定义强调「归属方失去管控」——赛狐是**自己在用自己维护**，只是在公开 OpenAPI 之外，**不严格成立**；Tyk 的「UI 就是一个 ergonomics 更差的 API」最贴切本场景。**用词约定**：正文用「私有接口 / 非公开内部接口」，首次出现补「（undocumented internal API，业界亦称 shadow API）」，**避免用「浏览器 API」**（歧义大，易被读成 Playwright 自动化本身）。含 4 条判据、私有接口价值定位（**在「修」不在「批量」**，海外仓备货单改头程是典型唯一路径）、取证纪律（route 截获后 fulfill 假响应 = 零写入）。
- **新增**: [2026-09-18-sellfox-cost-accounting-fifo.md](2026-09-18-sellfox-cost-accounting-fifo.md) — 赛狐成本口径与 FIFO 批次（成本挂在批次上、调整单/出库按先进先出吃批次）。

## 2026-09-07

- **新增**: [2026-09-07-gls-poland-track-feasibility.md](2026-09-07-gls-poland-track-feasibility.md) — GLS（波兰分公司自发货）跟踪可行性。结论：读轨迹**不需开发者账号**——公开无鉴权 REST `gls-group.com/app/service/open/rest/PL/en/rstt029`(摘要) / `rstt028/{no}?postalCode=…`(全量明细) 免登录实测 200(样本 `29626585597`/邮编 21706，history 10 条覆盖建标/收件/交付)；官方 ShipIT/MyGLS 走 GLS 波兰客户(ADE plus/Uni-Portal) + office@gls-poland.com 开通 WebAPI，纯 dev portal 注册替代不了。分支 `feature/gls-track-research`。
- **实证**: 8 月通途样本 GLS-Poland 1265 行 → 去重 1176 单号（11 位 `2…`）；明细唯一钥匙=目的邮编（订单 `邮编` 列已有）。
- **全量验证 + ops 表**: loader 自动拆分一格多号 → 查询单元 1187；`--workers 4` 共享连接池跑整月 3m45s（无限流），ok 1148/err 39(非 GLS 或接口查无)。`gls_track/ops_report.py` 出 FedEx 风格 8-Sheet 异常表。口径：`HANDLING_DAYS=2`、营业日用波兰 2026 假日(非美国联邦)、周末不计、「Amazon是否判迟」仅 Amazon/亚马逊 渠道。输出 `通途非FBA订单202608 GLS运营异常表 20260907.xlsx`（1187 行：正常1073/查无39/承运延误30/在途24/漏发11/迟发9/卡件1）。


- **新增**: [2026-08-18-sps-commerce-api-feasibility.md](2026-08-18-sps-commerce-api-feasibility.md) — SPS Commerce API 自动化可行性（Pottery Barn）。结论：走 Transaction API + M2M client_credentials（无需 Redirect URI），沙盒实测读/写/删全部成功；生产需与 SPS 签约 + 实施团队开通。新增 `sps_api/` POC 模块。
- **关键发现**: Web Service App 不支持 client_credentials（403 unauthorized_client），必须配 Redirect URI；新建 Machine-to-Machine App 即可免交互拿 token。
- **跟进**: 从 `us@mxdeals.com` 读取了 2025-06/07 与 SPS 联系人 Alison Kudrle 的完整邮件线程，并向她发出回复（确认是否仍负责 + 自己对接 API 是否额外收费）。新增 `sps_api/read_sps_mail.py`、`sps_api/docs/reference/tencent-imap.md`（腾讯 IMAP 检索特性）、`sps_api/docs/research/2026-08-18-sps-alison-email-thread.md`。

## 2026-07-24

- **壳 PoC 骨架落地**: 分支 `feature/ai-access-shell-poc` — `ai_access_poc/open_webui/` compose + Tool + Skill；`SELLFOX_API/client.py`。
- **新增**: [2026-07-24-unified-ai-access-poc-plan.md](2026-07-24-unified-ai-access-poc-plan.md) — C′ 双 PoC 实施计划：壳 OWUI + 板 IvyeaOps 赛狐只读映射与验收标准。
- **纠偏补篇**: 独立复审文档 §8 — 撤销「advertise/ 已验证」论据；赛狐广告无写 API；IvyeaOps→赛狐分层成本 15–34 人天（只读）；推荐 Portal 融合 C′（OWUI 壳 + IvyeaOps 板）。
- **新增**: [2026-07-24-unified-ai-access-independent-review.md](2026-07-24-unified-ai-access-independent-review.md) — 对 PR #109 统一 AI 接入调研的独立复审；回答开放问题 8.1–8.5；裁决推荐 Open WebUI 主路径（A′）并强制反证 IvyeaOps 全量改造。
- **新增**: 本 log.md（OKF bundle 补齐）。
- **新增**: [2026-10-08-key-test-branch-unification-review.md](2026-10-08-key-test-branch-unification-review.md) — key_test 生产线/测试线分叉的逐文件评审清单：22 个双边冲突文件分 4 档（纯格式 3 / 测试侧变薄 6 / 测试侧领先 12 / 需人工看 1）+ 41 个测试独有文件分 5 类 + 三个待决策 + 4 条已核对事实。
