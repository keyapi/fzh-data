---
okf: v0.1
type: Log
title: 解决方案变更日志
tags: [solutions, log]
---

# 变更日志

## 2026-09-22（公开仓与私有知识分层）
- **新增**: `architecture-patterns/public-private-agent-knowledge-split.md` — 调研并裁决公开仓、内部知识与凭证的三层边界：公开仓保留脱敏代码/通用经验；真实拓扑、运维 runbook 和内部 API 进入独立私有 Markdown 仓；密码/token/私钥进入 secret manager 或已忽略的本地环境文件。私有仓用普通 clone + 一键 bootstrap，而非 submodule；SOPS 只补充少量 GitOps 密文，不承担长篇知识库；Vault 等到出现动态凭证/PKI/合规需求再引入。另定义 Agent 自动发现、无权限降级、敏感文档 lint 与已公开内容迁移/历史重写边界。

## 2026-09-22（第二轮：重定向语义 / 出口拓扑 / Tailscale 2026 盘点）
- **新增**: `integration-issues/redirect-307-replays-post-405.md` — 「跳页面」的重定向必须用 **303**。Starlette `RedirectResponse` 默认 307，而 307 **保留请求方法**：退出是 POST → 浏览器 POST 到只接受 GET 的首页 → 405 `{"detail":"Method Not Allowed"}`。由使用者实测发现。**只断言 `Location` 的测试抓不到它**，要断言状态码。
- **新增**: `architecture-patterns/office-egress-fallback-chain.md` — 把散在多份文档里的出口链路串成一张图：主订阅线路 / **应急线路**（OpenClash 节点 `SH-Tailscale-US` → 上海 `socks5-tunnel.service:1080` → 美国 Vultr）/ 公网直反代；含重启存活状态与「用出口 IP 判断当前走哪条线」的定界方法。补的正是那个「各端都有文档、却没人串起来」的缺口。
- **新增**: `tooling-decisions/tailscale-2026-capabilities.md` — 2026 年 Tailscale 新能力里与本仓库相关的三项：**Peer Relays**（自建中继，对症跨境中继慢）、**Services**（服务级 MagicDNS + ACL，可减少手工 NGINX location/白名单，但**不替代应用层登录**）、**Tailcat**（"Tailscale without Tailscale"，无控制面的临时连接工具，不是架构升级）。

## 2026-09-22
- **更新**: `tooling-decisions/tailscale-relay-vs-public-https-china.md` —— 原结论「弃用 Tailscale」**不成立**。根因是**云厂商安全组没放行入站 UDP 41641**，导致直连失败退回香港中继。用户放开该规则后实测：同两台机器从 `relay "hkg"` + 超时 + HTTP 20-30 秒，变成 **直连 31-69ms**。处置顺序改为「先修直连，修不动再考虑绕开」。另记录该服务器上已有的 `socks5-tunnel.service`（SSH 动态转发到美国出口，仅监听 Tailscale 地址）及其实测效果。

- **新增**: `tooling-decisions/tailscale-relay-vs-public-https-china.md` — 境内访问境内服务器时 Tailscale 走**香港中继**（`relay "hkg"`，`tailscale ping` 超时）：实测服务器本机 1-3ms、公网 HTTPS 125ms、**Tailscale 20-30 秒**（TCP 握手单独就要 12-19 秒），12MB 文件根本传不完。结论是**弃用 Tailscale 改走同机公网 HTTPS + 应用层登录**（容器仍只绑 127.0.0.1）。含「把个人笔记本加进 Tailscale 解决不了这个问题」的解释与 UDP 41640 打洞失败的常见原因。
- **新增**: `integration-issues/dingtalk-oidc-bridge-client-onboarding.md` — 自建服务接入公司钉钉 OIDC 桥的**客户端侧**做法（桥本身见 `dingtalk-sso-new-api-oidc-bridge.md`）：不用改钉钉后台、复用签名 cookie、**OIDC state 必须外置到 Redis**、闸门写在应用中间件而不是 nginx `auth_request`（桥没有 `/verify` 端点）、**桥的 corpId 校验时灵时不灵**所以限制用户要靠服务侧白名单。
- **新增**: `integration-issues/reverse-proxy-prefix-return-to.md` — 前缀化反向代理下 `return_to` 踩的坑：`request.url.path` 是**反代剥掉前缀后的应用侧路径**，直接回写给浏览器会把登录后的用户送到**域名根路径**（同域上的另一个服务）。修法是把「应用侧路径」与「浏览器可见路径」分清，回写的 URL 一律补前缀；顺带给 `safe_return_to` 加前缀校验挡同域横向跳转。**使用者实际登录时发现**，自测没覆盖到。
## 2026-09-22
- **修正**: 「新机器怎么让 `ce-okf` 可用」原来教人跑 `setup.ps1`，**对 Claude Code 是多余的**。仓库里 `.claude/skills` 本身就是 git 跟踪的 symlink，只要克隆时让它正确检出，Claude Code 自动看到全部项目 skill。实测对照（同一台机器、开发者模式已开）：默认 `git clone` → `CLAUDE.md` 是 9 字节 stub（0 行）、`.claude/skills` 是**普通文件**、skill 为空；`git clone -c core.symlinks=true` → 两个都是**真 symlink**、`CLAUDE.md` 解析 243 行、`.claude/skills` 列 **47 个 skill**，**全程没跑 setup.ps1**。根因是 Git for Windows 的 `--system core.symlinks=false`；克隆时的 `-c` 只在那一刻生效、**不写进新克隆的 `.git/config`**（已核），所以还要补 `git config core.symlinks true` 才能扛住后续 `pull` 新增的 symlink 条目。`setup.ps1` 缩到**只剩 Claude Desktop 需要**（Desktop 只读 `~/.claude/skills/`，看不到项目级目录）。改动落在 `AGENTS.md` 克隆节 + `CONTRIBUTING.md`「首次初始化」+ `.agents/skills/ce-okf/SKILL.md`「首次安装到新机器」。macOS / Linux 原生支持 symlink，直接 clone 即可。
- **更新**: `ce-okf` 的依赖关系讲清 —— 之前 `AGENTS.md` 的「新机器首次 clone 后必做」清单里**一个字都没提** compound-engineering，而 `ce-okf` 第 1 步要调 `/ce-compound`。同事 clone 完能跑，但会静默走兜底、自己不知道。补：① `AGENTS.md` 加第 **4.5 步**（上游是标准 Claude Code 插件，装法是两条斜杠命令 `/plugin marketplace add EveryInc/compound-engineering-plugin` + `/plugin install compound-engineering`，**脚本代劳不了**，所以只能写进清单让同事的 Agent 读到）；② `.agents/skills/ce-okf/SKILL.md` 的「分工」表加「在本仓库？」列，把 `ce-compound` 标成**第三方 / 可选增强**并列出不装时丢掉什么（重叠检测损失最大、grounding 校验、检索广度），写明**流程照样完整、只降正文质量**。
- **更新**: `developer-experience/git-worktree-branch-upstream-tracks-main.md` — 把"已排除本仓库自身"从三段散句改成**可逐条勾选的排除表**（换机器重新排查时照着跑一遍即可）：脚本调用 `worktree add`（`.md` 里的命中都是文档在教人敲命令）/ `setup.ps1` 实际内容（只做 `CLAUDE.md` symlink + `.agents/skills/*` 链接 + superpowers 链接，**不碰 worktree、不写 `branch.*`**）/ `.claude/settings.json` 不存在 / `.claude/settings.local.json` 只有权限 allowlist、**无 `hooks` 段、无 `WorktreeCreate` hook** / `.git/hooks` 只有 `.sample` / 107 个 `config.worktree` 无 `branch`/`push` 设置。顺带记一句成因量级：`"Bash(git worktree *)"` 在权限 allowlist 里，**Agent 建 worktree 免确认**，所以产出量才这么大。

## 2026-09-16
- **新增**: `workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md` — PB 断货通知与 0 库存订单处理：① 判「哪些订单因无货卡住」用 PB 订单目录 `<YYYYMMDD>/checked0stock order xNN *.csv`（每期一份，比对多期可分新断/持续断）；② **PB PO → EN `Tongtool Order`（`PBUS-<PO>`，拆单为 `-N`）→ `platform_sku` → `erp_item_code`** 映射链，EN 的 `Sales Order.po_no` 与 PB PO 无关；③ `PBUS-<PO>` 是否存在 ⟺ 是否已打单；④ 通知邮件模板（`Vendor 5806`、ASN 已生成标注、一信一 SKU）；⑤ restock date = 补货 SO 下单日 + 3 个月，**一个 SKU 多张未发单会得到不同日期**。
- **新增**: `workflow-issues/cargo-location-tracking-source-reliability.md` — 「货物到哪了」查询方法：把 EN / 通途 / 钉钉 / UPS 四个来源按**事实层 / 登记层 / 不可用**分级，明确「工厂出货看 EN DN」「UPS 收件看 UPS API」「**到国外仓没有可靠来源**」，给出查询顺序与写结论的四档措辞（事实/登记/估算/推不出）。
- **新增（模块）**: `dingtalk/dingtalk_sheet/` —— 只读读钉钉表格（workbook）：`client.py`（accessToken / parse_base_id / list_sheets / read_range / read_sheet_all）、`read_table.py` CLI、22 条离线单测、OKF bundle、README + AGENT_HANDOFF、skill `.agents/skills/dingtalk-sheet/`。原料：两张供应链表（`2026年下单表` / `发货信息总表`）。
- **口径（关键，推翻早先推断）**: **EN 的 `po_no` 不是客户 PO 号** —— 是离职同事自编的内部流转号，SO 自身已有下单日期与仓库，故**待废弃**；脚本列名改为「内部流转号(非客户PO,待废弃)」。**头程的真实入口是「EN销售订单编号 × 钉钉表」**，不是 `po_no`。
- **口径（关键）**: **通途「可用库存 0」≠ 断货** —— 通途为标记发货**必须先报溢**让库存够扣减（系统里出现「出库 N + 报溢 +N」一一抵消），实际是**试探性发货**（PB 订单照常发美中仓，有货发走、没货才回话）。判断货的可靠来源是 **PB 0 库存导出 + 美中仓人工回话**。
- **口径（关键）**: **PB 拿「UPS 站点收到我们包裹」的日期作为付款依据**（账期约 1 个月），故跟踪只分两档 —— `Shipper created a label`（未收到，不计账期）vs 出现 `Drop-Off`(XD) 及之后节点（已收到，那天即起算日）。
- **实测（9 月全量）**: 扫 `202609*/*shipment*.csv` **全部单元格**取 `1Z` 号（120 个，**按号去重** —— 一个 PO 可能多包裹，实测 `137887647`/`137879782` 各 2 个），用 `ups_track` 实查：**110 已收到 / 10 仍停在 Label Created**。建标→揽收 = 0–2 天、中位 0 天。**不要拿 2026-08 那份「1–7 周」当常态**（那是未付发票样本，选择性偏差）。
- **实测（通途 API）**: `erp2_stocks_stocksquery` 按仓库取库存（`warehouseName` 必填，含**在途**；美中仓名 `美中-FZH-DANEEY`）；`erp2_purchase_purchaseorderquery` 可按 `skus` 查**通途采购单号 `PONum` + 到货日**（是通往钉钉「物流信息表」的钥匙）；销量无独立接口，`stockschangedetailquery` 可推但 **`updatedDateFrom` 只能 7 天内**；长区间销量走网页自动化 `tongtu.sales.export`。限流 **5 次/分钟**。
- **实测（反例）**: 通途 `purchaseDate` **≠ 工厂发货日**（`PO021711` 采购 08-26 vs 钉钉登记工厂发货 08-22，晚 4 天）；`WO` 头部状态不可信（以 Job Card 为准）；**我方 ASN / shipment csv ≠ 实际发出**（只证明标记了发出）。
- **加固**: `dingtalk_sheet` 修两个真缺陷 —— ① 接口**用空行把请求区域补满**，「返回行数 < 请求块就停」的翻页条件永不触发（曾误报某表 4 万行，实际 380 行），新增 `read_sheet_all()`；② 对 5xx / 瞬时 `404 uuid not exist` 退避重试（4xx 不重试）。单次 range 上限 **30000 单元格**。
- **更新**: `architecture-patterns/sps-commerce-api-automation.md` 加状态更新 —— 已向 SPS 求证 **API 为收费项、暂缓推进**，重启先谈商务。
- **OKF 合规**: 补 `dingtalk/dingtalk_sheet/README.md`；给 3 个既有文件补 `type`（`erpnext-version-api-compatibility` / `search-first-before-implementing` / `sellfox-cover-combo-create-ops`）。发现 `scripts/update_index.py` 判定 bug：`has_type = "type:" in fm_text` 会误匹配 `problem_type:`，**缺 type 的文件也被计入文档数**。

## 2026-09-09
- **新增**: `architecture-patterns/account-period-revenue-reconciliation-ecosystem.md` — 账期/收款核算「生态地图」：把 销售额(通途) + 各平台账期(Amazon=赛狐结算/列式, OSTKUS, PB, Wayfair, Temu/TikTok/Walmart…) + 汇率 + Tax + 附加费 + 回款归属 + 回款率 + 钉钉提交/审批 + NAS 归桶 + 报税 整条链路画成地图，赛狐只是 Amazon 一块；含公共口径(账期月自然月/4号-3号窗口/结算 vs 日期范围口径/回款率=应收/销售/固定月汇率) 与 现有资产指针 + 缺口待办。
- **新增**: `workflow-issues/amazon-account-period-late-submission-audit.md` — Amazon&新平台账期「提交异常/迟交」审计方法与规则：账期归属=账期日期自然月、提交窗口 4号~下月3号(先 8号~下月7号)、发起时间=提交、`账期月Z` vs `桶B` 判 正常/迟交/遗档/早交；跨文件去重 + `选择平台==亚马逊` 分流；2026-03~08 各桶 正常/迟交/遗档/早交 实测表(8月桶 40 行账期7月、7月桶 40 行完成>08-03+13 未办结、3月桶 6 行 2025 遗档)；产物在 `D:\Work\王忠于\成本核算\`。
- **新增**: `tooling-decisions/amazon-settlement-autofetch-sellfox.md` — 赛狐自动拉取 Amazon 账期：结算中心V2(汇总+明细, `currency` 取原币, 默认 CNY) vs 紫鸟/赛狐插件列式报表(`报告中心 getPlugPageList type=3/4`, 已实测拿到 32 列 Custom Transaction CSV)；两报表口径(payout vs activity/posted)取舍、科目映射、赛狐店名↔渠道账号交叉表(写入共享表「和运营部共享/渠道账号」`赛狐店铺` 列, VERCART=AMZVer, 北京熙锦=AMZBJXJ, Daneey-CA=AMZDANEEYCA, 如泱-CA=AMZBJRYECLTDCA, 北京固祥未启用排除)。产出 `sellfox_settlement/reconcile_amazon.py`(+`fetch-custom`) 与 `sellfox_settlement/docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md`(§10-13) + `sellfox_settlement/AGENT_HANDOFF.md` + `.agents/skills/sellfox-amazon-settlement/`。背景: 财务全靠运营钉钉手动提交 Amazon 账期金额, 依赖人工、金额易错、txt 只能解析 tax。
## 2026-09-14
- **新增**: `workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — 子表字段反查父单的三条 API 铁律（子表直查 403 / 父单直查子字段 417 / 子表过滤结果"一行一子行"必须按父单去重）+ `in` 列表超 4094 字节请求行上限须分块 + `Sales Order Item.name == Production Plan Item.sales_order_item` 连接键 + 出库单必须按 `item_code` 匹配（老出库行 `customer_item_code` 为空）+ `amended_from` 区分改单与死单 + 客户码注册在成品 `KS` 上而订单行卖 `PK#` 皮壳。两条反直觉结论：**ERPNext 的 `Closed` ≠ 已发完**；**`Work Order.status` / `produced_qty` 不可信，进度要看工序卡**（`WO-26-02609` 头 `Not Started`，实际 44 件已过 5 道工序；且完成件数不能各工序求和）。
- **新增**: `EN_API/item_shipment_status.py` + `EN_API/AGENT_HANDOFF_物料发货状态.md` — 客户物料号 / EN 物料号 → 销售订单发货状态 + 生产计划/工单/工序卡报表（单物料颗粒度，3 sheet Excel，`--assert-fixture` 回归自检）。分页相对 `dn_trace_report.py` 加 `order_by="name asc"` 并按实收行数前移；只落新脚本，未回灌旧脚本。
- **实测**: `CENKZ1325-Yellow-138` / `PK#KS0001-DM-140-YELLOW`（美中公司 DANEEY）10 张 SO / 330 件，已发 126 / 未发 184，其中死单 64（SO-26-00099、SO-26-00003、SO-25-00198 尾数 4）、在产待发 120。
## 2026-09-10
- **更新**: `conventions/amazon-period-file-reconcile.md` — 补浏览器补下载路径、env/人名不上 git；公开叙述仍用拼音首字母。
- **新增**: `conventions/amazon-period-file-reconcile.md` — Amazon 账期按账号对 NAS/钉钉/赛狐结算组：负责人≠人名夹、店名经别名、groupPage≠txt 原件、「或」≠「钉钉且附件」；公开叙述用人名首字母。
## 2026-09-21
- **新增**: `integration-issues/sellfox-amazon-settlement-plug-only.md` — Amazon 账期报表（Transaction / Summary PDF）在赛狐侧**只有「插件获取报告」（`report/center/task/getPlugPageList.json`）一条路**，且该接口**纯读、API 不可触发抓取** —— 两条旁证：`创建报告任务` 的 `reportType` 只支持 `PRODUCT_SALE_REPORT`，`亚马逊原报告` 的类型枚举里没有账期。第二条硬约束：**`fileUrls` 是 1 小时有效的腾讯 COS 预签名 URL**，不能存链接，必须「拿新 URL → 立刻下载落盘」。实测：90 家 Amazon 店**仅 39 店有数据、51 店完全没抓过**（呈整店群分布 ⇒ 人工按品牌执行、非周期性任务），**只覆盖 2026-06/07，8-9 月一条没有**。另留档一个**已被否决**的替代方案（`monthProfit/shopSummary` 服务端销售额、覆盖全店但属赛狐自算口径），以免将来重复提议。
- **新增**: `SELLFOX_API/fetch_amazon_settlement.py`（下载归档）+ `SELLFOX_API/probe_amazon_reports.py`（覆盖度矩阵）；调研全记录见 `docs/research/2026-09-21-sellfox-amazon-settlement-reports.md`。
- **更新**: `skills/sellfox-api` 补「报告中心三条路径」对照表（亚马逊原报告 / 自定义报表 / 插件获取报告）。
- **更新**（同日后续）: `intent_router/catalog.yaml` 从 35 补到 **56** 项 —— 补入 11 个此前漏掉的 skill 目录 + 10 个此前漏掉的**业务模块目录**（`advertise` / `amazon_pairing` / `ups_track` / `pb_reconciliation` / `cost_adjust` / `sellfox-api-proxy` / `ai_access_poc` / `google_drive_permissions` / `nas_product_visuals` / `sps_api`），`AGENTS.md` 模块索引表同步（35 → 56 行）。**关键认知：该表原是「策展子集」而非完整清单** —— 18 个顶层模块目录里 16 个不在表内，所以在此之前 `advertise`/`pb_reconciliation`/`ups_track` 这类模块**根本路由不到**。纳入规则（可审计）：有 `AGENT_HANDOFF.md` 或 `docs/`、有代码、且 2026-08-01 后仍有提交（或引用 ≥5 次）；据此排除 `test_upload`（0 py 已废弃）、`EN_shopify`（无文档）、`SPS_Selenium_Local`（仅 README 零引用）、`pdf_to_md`（文档齐但 3 个月未动）。**`dingtalk` 刻意不单列** —— 它就是 `dingtalk-robot` skill 的实现，单列会造出两个都像「发钉钉消息」的选项。**数字更新**：标注样例扩到 31 条（每新模块一条），56 选项下 **33/33 全中**，`confidence` 0.98–1.00、`ambiguity` 0.66–0.98、约 9815 输入 token ≈ $0.00041/次 —— 正面回答了原计划风险 #3「选项变多会互相干扰」。

- **新增**: [workflow-issues/mcp-to-chatgpt-bringup-lessons.md](workflow-issues/mcp-to-chatgpt-bringup-lessons.md) — 把 FAC / 赛狐 / NAS 三个 MCP 接上 ChatGPT 的**方法总结与四个教训**。两个是方法问题不是技术难题：
  ① **单次探针不可信** —— 在办公网内测 `nas.vilavi.cn` 得 200，实为**内网 DNS 覆盖**，换两处外部主机复测才发现 443 公网不通；
  ② **评估第三方方案要先盘功能面再决定自建**（用户直接批评）—— 我把 3 个开源方案只当「对比对象」、**没抄它们的工具清单**，导致功能面远小于现成方案，变成「用户要一个我加一个」；
  ③ **上游封装会吞异常** —— `NAS_API.get_file_list` 失败 `return []`，把「Session timeout」伪装成「文件夹是空的」；`download_file()` 因 `get_file(mode='download')` 写盘不返字节而**永远返回 None**；
  ④ **做对的**：鉴权先验最小闭环（本机 + Tailscale Funnel，零生产影响）拿到 `openai-mcp/1.0.0` 带 `Authorization` 头的决定性日志，结论赛狐与 NAS 共用。
- **更新**: [workflow-issues/search-first-before-implementing.md](workflow-issues/search-first-before-implementing.md) — 补 **Case 2 / Case 3** 与「Why This Matters」补充段。① **内部约定常常只在代码里，不在文档里** —— 给 NAS 路径拼 File Station 深链时我**自己猜了格式**（`?launch=FileStation&path=`）还当成结论写进文档；用户指出 EN 的**产品物料库**早已做过，去测试服务器一搜就找到 `vilavi_pim/api/nas.py` 与 `work_order_task/.../item_group_nas_path.py::encode_filestation_link()`，真格式是**双层 URL 编码**（`quote(quote(path))`），顺带对齐出会话失效错误码是 **105/106/107**（我原只判 106/107）、Thumb 的 `path` **要加双引号**（spec 要求）。② **评估第三方方案要抄「能力清单」** —— 只写对比表就决定自建，事后抄 mrquj 的工具表才发现一次漏了 7 项（搜索/缩略图/文件夹大小/校验和/分享链接/压缩包/读图）。原文档只讲「搜文档」，现补上「搜代码」与「抄清单」两步。另修 `docs/solutions/index.md` 一处 **frontmatter 被顶到第 2 行** 的缺陷（上一次提交把新行插到了 frontmatter 之上，已移回表格）。

## 2026-09-20
- **新增**: `workflow-issues/sellfox-incentive-cost-adjust-2026-09.md` — 「特殊规则改赛狐入库成本」的批量执行尝试：目标值来自共享 Google Sheet 特殊规则 844-874 行（汇率 6.8，通途SKU→赛狐SKU 走 EN BOM「客户物料号→产品编号」，28/28 命中），生成 56 明细行 / 6 张备货单。**结论：清单能生成，但大部分行改不动**，因为①**成本补录单下调受「批次剩余货值」封顶**（`单件可下调幅度 ≲ 当前单价 × 剩余占比`，剩余为 0 就完全降不了 → 下调有强时效性，要在被消耗前做），②**同一 SKU 只能有一张待审核补录单**。另记录两条数据可信度教训：**批次表 `goodsAva` 不能当当前库存**（30 行 21 行与库存明细不符，POLAND 整组差约 1000）、**备货单列表接口 `items` 只返回 3 条预览**（据此判断 SKU 成员关系必然误判，本轮连错两次）。
- **更新**: `integration-issues/sellfox-cost-adjust-api.md` — 补「建单/审核会被拒的两条硬约束」（`货值不能为负数` 的公式与实测边界 178.045；`存在待审核的补录单` 与 `delete.json` 用法）与 2026-09-20 实测表；`integration-issues/sellfox-restock-headfee-api.md` — 新增「`searchType` 三个调用面三种约定」表（站点列表 `sku` / 批次表 `commoditySku` / 公开 OpenAPI 不含 SKU）+ 列表 3 行预览陷阱；`research/2026-09-18-sellfox-cost-accounting-fifo.md` — **更正 `goodsAva > 0` = 还在库 的说法**，并在「改成本工具结论」补下调封顶；`cost_adjust/AGENT_HANDOFF.md` — 关键坑新增 8/9/10/11 四条，未解决表补两行。
- **词汇**: `CONCEPTS.md` 新增「剩余货值约束（货值不能为负数）」「激励价」「海外仓批次表 goodsAva」，并加一条 `searchType` 三面约定的 Flagged ambiguity。
- **新增**: `workflow-issues/sellfox-inventory-sync-cost-drift.md` — 「用库存调整单把外部库存数量同步进赛狐」的长期代价。**先纠正一个易走偏的结论**：赛狐自己的三方仓模块就有「生成调整单」功能（i18n `main.warehouse.tripartite.warehouse.generate.adjustment.order`，权限 `MOD_OVERSEA_WAREHOUSE.CREATE_ADJUST`），**官方建模本就是生成调整单** → 用它同步数量**不是选错工具**，问题在成本侧。三点成因：①调整单明细零成本字段，但每建一张必产生新批次，成本 = **创建时该(仓库,SKU)加权均价快照**；②该快照**不可修正**（`+N/-N` 不互抵、已完成单不可删不可撤、调整单无成本字段故无入口）；③结果=可修正的备货单批次被 FIFO 逐渐吃掉、不可修正的快照不断堆积 → **越跑越难改均价且无回退路径**。给出三个选项（维持/A 改用其他入库单`perPurchase`必填/B 保持调整单但先修好成本）。
- **更新**: `integration-issues/sellfox-adjust-order-write-chain.md` 的「结论：调整单不适合承载数量同步」→ 改为「用它做数量同步的代价（不是用错工具）」，与新文档口径一致；`cost_adjust/AGENT_HANDOFF.md` 未解决项同步（三方仓端点已探、本账号未开通功能）。
## 2026-09-21
- **新增**: `tooling-decisions/typesafe-jev-intent-router.md` — 中文意图路由模块 `intent_router/`：用 TypeSafe Jev / System One 把一句中文需求路由到本仓库 30+ 个模块，**只分类不执行**。动机是触发词匹配是关键词不是语义（`item-cost`/`stock-init`/`warehouse-restock` 同吃 EN BOM 成本，触发词分不开）。**两条实测结论决定了它怎么用**：① `confidence` **0.97–1.00、几近饱和**（连模型选 `none` 时也有 0.99）—— 它是**分布集中度不是正确率**，所以 `--min-confidence` 实际**不触发**，真正兜底的是 **`none` 选项**，别把高 confidence 读成"一定对"；② `ambiguity` 只跨 0.87–0.98，清晰请求 0.95 与域外请求 0.96 几乎重叠，**不具区分度**，故只在「无法判定」分支显示。对抗"自信的错"靠**默认总打印 top-3 候选**。**坑**：worktree 里 `.env` 在 `parents[4]` 而非 `parents[1]`，本仓库既有三个加载器全部取不到 key，改用有界上溯；YAML 把裸写的 `401` 强制转成 int 导致 string 形式 criteria 崩溃。另：`criteria` 用 object 形式是**先用 2 选项 payload 打真实请求确认过**（HTTP 200 无 422）才敢铺开的。**防漂移测试已按设计生效一次**：PR #249 给 AGENTS.md 加 `ce-okf` 行后测试立刻报错并打出差集，补 catalog 条目即恢复。
- **新增**: `developer-experience/windows-worktree-claude-md-symlink.md` — Windows 上 worktree 里 `CLAUDE.md` 是 symlink 还是 stub，取决于**开发者模式**（它正是提供"非管理员建文件符号链接"权限的东西）。修正 `CONTRIBUTING.md` 的过期结论：旧文写"开发者模式会让 worktree 创建因权限不足失败"，实测**已反向失效** —— 开启后 `git -c core.symlinks=true worktree add` 成功且 `CLAUDE.md -> AGENTS.md` 是真 symlink、`git status` 干净。**关键坑**：本仓库 `.git/config` 把 `core.symlinks` 显式设成 `false`，worktree 共享该配置，所以不传 `-c` 覆盖即使开了开发者模式仍拿到 stub。stub 状态极隐蔽 —— git 干净、不报错，但该 worktree 里 Claude 系统提示的项目指令**只有 `AGENTS.md` 这 9 个字符**，AGENTS.md 正文完全没进来。另：`setup.ps1` 只在主仓库根目录跑（`~/.claude/skills/*` 是全机一份、必须指向主仓库；在 worktree 跑会指错且 `[SKIP]` 导致修不回来）。
- **更新**: `CONTRIBUTING.md`「Git Worktree 创建（Windows 特别说明）」三处 —— `:61` 的过期结论、`:67` 的推荐命令（`core.symlinks=false` 改成按开发者模式二选一 + 一次性 `git config core.symlinks true`）、`:69-71` 删掉"在 worktree 里跑 setup.ps1"（现在有害）。补「存量 worktree 修复」：`git -C <wt> checkout -- CLAUDE.md .claude/skills`（只碰这两个条目）。**批量扫必须先按工作区内容筛选**，只处理"除 `T CLAUDE.md`/`T .claude/skills` 两行外别无改动"的 —— 本机 134 个 worktree 中 88 个属此类（全扫 0 失败、status 归零），44 个带在制品（有些上千文件）一个未动。
- **新增**: `tooling-decisions/ce-okf-conversation-wrapup-skill.md` — 把用户 40+ 会话里手打的固定收尾提示词（29 个版本同一骨架）固化成仓库内 skill `ce-okf`。决策：**包一层 `ce-compound` 而不是改它** —— 三条理由：① `ce-compound` 写完文档即结束回合，**不提交不开 PR**（用户每次都要"之后 git 提交 并 pr"，这是缺口）；② 它的 `component` 枚举是 Rails 味儿的，而本仓库 `docs/solutions/**` 早已是 OKF + ce-compound 合并 frontmatter，它不写 `okf:`/`type:`；③ 它是用户级外部 skill（`~/.agents/skills/`），改它不随本仓库 PR 走，同事的 Agent 拿不到。另记两条实测：各 category 的 `index.md` 表头不统一（`integration-issues` 三列带日期、`tooling-decisions` 两列）；`AGENT_HANDOFF.md` 用 `type: Handoff` 与 `updated:` 属现役事实，勿"修正"。
- **新增**: `.agents/skills/ce-okf/SKILL.md` — 收尾一条龙：模式判定（新增/增量）→ `ce-compound` 出正文 → frontmatter 归一化 → 11 项 OKF 级联登记 → `update_index.py` 索引联动 → 凭证扫描 → 提交 + PR。参数 `/ce-okf`（默认到 PR）、`refresh`（增量）、`no-pr`（只本地提交）。
- **更新**: `AGENTS.md` 模块索引表 +1 行（`ce-okf`）。
- **修正**: `scripts/update_index.py --check` **不能当硬门禁** —— 逐字节比对但文件头 `generated:` 是分钟级时间戳，只在"刚生成完的同一分钟内"通过，平时误报 `STALE`；索引是否同步要看内容不看退出码。且索引日期列因取 git commit 日期而**注定滞后一个 commit**（先生成后提交时显示上次提交日期），仓库现役习惯即和文档同 commit，无需补 commit。
- **坑**: Windows 上 `setup.ps1` 建**文件**符号链接要开发者模式/管理员，没开时退化成 `Copy-Item`，把 `CLAUDE.md` 从「1 行 stub」写成 AGENTS.md 整份副本（215 行），工作区变脏。**不要提交它**，也不要拿 `git restore` 当标准动作 —— 那会让本机 Claude Code 只读到 `AGENTS.md` 这 9 个字符（目录链接用 junction 不受影响，skills 一直正常）。两个状态只能取一个；开开发者模式才能兼得。已写进 `ce-okf` skill 安装节。
- **新增**: `ce-okf` skill 补「多 Agent 并存（Claude/Codex/Cursor）」一节 —— 三者共用 `AGENTS.md` + `.agents/skills/` 一套事实源（`CLAUDE.md` 只是 Claude 入口，只改 AGENTS.md）；`/ce-compound` 是 Claude 专属、Codex/Cursor 上没有需走内置模板兜底；**提交只逐个 `git add` 本次自己动过的文件，绝不 `git add -A`**（另两个 Agent 的未完成改动会躺在工作区）；看到不认识的改动原样留着。
- **坑**: `setup.ps1` **不能在 worktree 里跑** —— `~/.claude/skills/` 软链是 Claude 独有的，在 worktree 跑会把链接指向临时 worktree；而 `New-SafeJunction` 对已存在路径 `[SKIP]`，**事后在主仓库再跑也修不回来**。本次实施中了一次（`ce-okf` 链接指到 worktree），已用 `(Get-Item $p -Force).Delete()` 移除（只删链接、不动目标）。
- **修正（`ce-compound-refresh` 首跑）**: 上面两条里"仓库 `core.symlinks` 是 `false`"的记载**已被本日后续操作推翻** —— 主仓库已改为 `true`。四份文件同步更正：`docs/solutions/developer-experience/windows-worktree-claude-md-symlink.md`（改判据为"换新机器先确认这一项" + 新增"项目 skill 会在技能列表里出现两遍"的副作用说明）、`docs/solutions/tooling-decisions/ce-okf-conversation-wrapup-skill.md`（改成"本机已开开发者模式 + `core.symlinks=true`，不再是两状态二选一"）、`CONTRIBUTING.md`、`.agents/skills/ce-okf/SKILL.md`。**教训：文档里写"当前状态"会随同一个会话的后续操作立刻过期** —— 能写成"判据/检查方法"就别写死值。
- **修正（`ce-okf` 第 0 步）**: `ce-okf` 首跑发现模式判据不准。旧规则「本次对话已 commit / 已开 PR → 增量」把"对话产物"和"文档是否已存在"混为一谈；已改为「学习点**是否已写进某篇现存文档**」。边做边提交的会话可以同时"已有 PR"和"有全新学习点"，旧规则会把后者误送进 refresh。
- **新增**: `workflow-issues/walmart-account-period-sellfox-api.md` — Walmart 账期可走**赛狐公开 OpenAPI 直拉**（`walmartReport/queryStatementDetail`，权限已开通，含 `periodStartDate`/`periodEndDate`），不再依赖财务手工 xlsx。两个硬结论：①**必须按账期取数**——Walmart 是**双周账期（14 天）**，同一 PO 的销售行与退货/费用行常落相邻账期，按单账期聚合比 EN 必错位（实测 58 单里 12 单如此，会被误判成金额不符）；②**平台费口径结案**——`赛狐佣金=(商品价+Total Walmart Funded Savings)×15%`，`EN platform_fee=商品价×15%`，**差额 = 沃尔玛补贴 × 15%**，逐单 64/64 命中、汇总 28.28 vs 28.32；结论是 **EN 漏算补贴基数、赛狐对**，先前看到的「费率 15%~17% 飘忽」是基数差异造成的假象。另记两类非错误差异（佣金已退货冲平=时点口径）与覆盖边界（**Wayfair 无赛狐财务端点、Overstock 不在赛狐平台枚举**，故本经验不可外推）。3 个账期销售额分毫不差（1317.28/1511.75/4346.60），顺带证明 EN 快照对通途忠实，**无需动用通途 API 复核**（限速 5 次/分钟）。
- **新增**: `SELLFOX_API/probe_walmart_settlement.py`（只读取数探针：`--list-shops` / `--discover-periods` 摸账期 / `--pull-period` 按账期拉；`raw_post()` 绕开 `signed_post()` 的异常包装以保留 40021 等错误码，并兼容两种限流形态）。
- **新增**: `platform_account_reconciliation/scripts/reconcile_walmart.py` — 跨账期合并勾稽 + 平台费口径判定，输出 `账期总览/订单级勾稽/账期费用分类/账期明细`。
- **修复**: `platform_account_reconciliation/scripts/reconcile_ostkus.py` 的 `ENV_FILE` 原写死仓库根，**在 git worktree 里因凭证只在主仓库而跑不起来**；改为向上搜索 `EN_API/.env`（`_resolve_env_file()`）。
- **更新**: `platform_account_reconciliation/AGENT_HANDOFF.md`（增 §10 Walmart，并在 OSTKUS 待办第 1 条补同型差额的复查线索）、模块 `docs/index.md` + `docs/log.md`、`skills/platform-account-reconciliation`（补 Walmart 线路与触发词）。
- **新增**: `developer-experience/git-worktree-branch-upstream-tracks-main.md` — 本机 84 个分支的 upstream 被指成 `refs/heads/main`，直接抵触 AGENTS.md 第 8 条。**根因是 git 默认行为不是本仓库脚本**：`branch.autoSetupMerge`（未设置=默认 `true`）+ worktree 工具拿 `origin/main` 当起点 → git 自动"设为跟随该远端分支"。四条命令实测对照：`worktree add -b X <path> origin/main` ✅设 / 无起点 ❌ / 本地 `main` 作起点 ❌ / 加 `--no-track` ❌；且仓库内无任何脚本或 `.claude/settings.json` 调用 worktree add、`.git/hooks` 只有样本、107 个 `config.worktree` 无 branch/push 设置 → 排除自研。**重要更正**：报告"裸 `git push` 会推 main"是不准的 —— 本仓库 `push.default` 未设置（=`simple`）时裸 push **报错拒绝**、main 不动，只有 `push.default=upstream` 才真推（实测 `feat -> main`）。所以现状是"fail-safe 但护栏是偶然的默认值"，**而那段报错提示恰好写着 `git push origin HEAD:main`，照抄即违规**（二级陷阱；修好后提示会自动变安全）。**修法**：已推的用 `--set-upstream-to=origin/<n>`（4 个）、未推的用 `--unset-upstream`（80 个）—— 实测 `--unset-upstream` 对**被其他 worktree 占用**的分支同样有效，不必先切过去；`git config branch.autoSetupMerge false` 防复发（实测不再自动追踪，且 `git push -u` 仍正常；`=simple` 在 2.35.2 报 `bad boolean config value`）。**两处待办**：该设置是 repo-local**不随 clone 走**（换机/新克隆隐患复活，可考虑进 `setup.ps1`，本次未做）；另有 4 个"别名型"（`merge` 指向别的分支，如 `review-141 → claude/gifted-lamarr-7ffe1d`）疑似有意跟随、未动。旁证：排查途中又新冒出 1 个同类分支，说明并发会话仍在持续产出。
- **更新**: `CONTRIBUTING.md`「Git Worktree 创建（Windows 特别说明）」补本隐患的判据、`branch.autoSetupMerge false` 一行修法与 repo-local 提醒。
- **更新**: `docs/solutions/developer-experience/index.md`、`docs/solutions/index.md`。

## 2026-09-20

- **修复（链接）**：本 bundle 失效相对链接（少退一级，`../../` → `../../../`）：`architecture-patterns/agent-dingtalk-file-bridge-via-erpnext.md`、`workflow-issues/en-channel-account-gsheet-sync.md`（5 条）、`workflow-issues/search-first-before-implementing.md`。

## 2026-09-18
- **新增**: `integration-issues/sellfox-restock-headfee-api.md` — 备货单改「单个头程费用」：**两条 Excel 路都堵死**（`pickingOrderUpdateTemplate` 表头零费用字段；`overseaPickingListFee` 是物流信息层且无 UI 入口），只能走私有接口 `detail.json` → 改 `items[].headFee`+派生值 → `edit.json` 整坨回发。**收敛口径**：改一张单只影响**本批次**，`Δ单位费用 = ΔheadFee × 本批次可用量/SKU总可用量`。**纠正旧文档**：调整单批次「跟随备货单成本」只对 `type=4（减少）` 成立，`type=3（增加）` 各自**新建独立批次**、不跟随——实测该 SKU 另 11 件来自 3 张 AD 增加单，无自动化入口。**性能**：500 行 / 1.06MB 的 edit 实测 **16~18 秒**（超线性），默认 30s 超时余量薄。另记 `page.json` 的 `searchType` 必须传 `'sku'`（传别的被静默忽略返回全量）、`pickId` 由 localStorage 而非 URL 传递。
- **新增**: `cost_adjust/sellfox_restock_headfee_api.py` — `RestockHeadFeeClient`（`detail` / `list_orders` / `in_stocks()`批次构成 / `project_unit_fee()`预测 / `build_payload` / `edit`），显式超时 + 大单告警，默认 dry-run；打印批次构成与单位费用预测，预测值与实测分毫不差。
- **新增**: `integration-issues/sellfox-cost-adjust-api.md` — 赛狐成本补录单完整 API 契约实测：公开 OpenAPI **只有查询一个端点**且过滤字段逐个鉴权（`searchField=sku`/`status`/`warehouseIds`/`createTime` 全报 `40021`，且该接口间歇 40021 需重试）；创建/审核走**内部接口**（端点名从 `bundle.index.*.js` 打包产物挖出）；`create.json` 是读接口结果的**逐字段回填**（`warehouseId`=虚拟仓库 ≠ `targetWarehouseId`=真实海外仓、`newPerFee`=0 而 `oriPerFee`=null、`oriTotalPerFee` 是空字符串）；`audit`/`delete` body 是裸数组，`reject` 是 `{adjustId, reason}` 对象；`edit`/`updateRemark` 无 UI 触发入口未解析。方法：Playwright 路由**截获后 fulfill 假响应**，零写入拿契约。
- **新增**: `cost_adjust/sellfox_cost_adjust_api.py` — 纯 API 客户端（`CostAdjustClient`：读明细/建单/审核/驳回/删除 + `change_cost` 编排），默认 dry-run；`build_payload` 输出与 UI 实际请求体逐字段一致（单测比对通过）。
- **更新**: `cost_adjust/README.md`（新增「两条写入路径」对比与内部接口契约）、`cost_adjust/build_saihu_cost_adjust.py` 文档串（更正「公开 OpenAPI 没有写入口」的表述，补 API 路径）。
- **实测**: `test001-white`@POLAND 备货单 `OWS294A9T700030` 采购单价 1.50→1.48，建单 `CA26091800004` 并审核生效，库存采购单价 1.3748→1.3648、入库成本 3944.90→3924.96（−19.94）；靶子单 `CA26091800005` 用于抓 reject/delete 契约后已删除。
- **更新**: `integration-issues/sellfox-adjust-order-write-chain.md` — 补「调整单作为数量同步工具」的完整实测：**创建时不录成本**（item 零成本字段）；**新批次成本 = 该(仓库,SKU)当前加权平均成本快照**，不是来源单成本（实测 SKU 均价 4.3763 → 新批次 transportCost 4.3763，而其来源备货单是 4.08）——这解释了它们为何天然"不跟随"；**不可逆**：`+N/-N` 后扣减按 FIFO 吃最老批次、不冲新批次（实测备货单批次 139→138、新批次 1 件留下、单位费用 4.3763→4.3782 且清不掉）；**已完成单不可删除不可撤销**（删除报 `仅【待调整】、【待提交】状态的单据可删除`，详情页只有 `取消`=返回 与 `打印`，端点族无 antiAudit/revoke，唯一可写的是 `editRemark`）。另记站点内部路径 `/api/gw/sellfox/sellfox-warehouse/sellfox/api/warehouse/adjust/{pageList,detail,create,submit,confirmAdjust,approval,delete,editRemark}`（OpenAPI 的 `/api/ware/adjust/*` 在站点上 404）；结论：**调整单不适合承载数量同步**，替代是「其他入库单」（`perPurchase` 必填 + `shipFee/otherFee`）。
- **新增**: `integration-issues/sellfox-adjust-order-write-chain.md` — 赛狐《调整单》写链路生产实测，结论与文档不符：`createV2` 的 `data` 恒为 `null` 不回传单号；无审批流账号下**建单即完成并扣库存**（`adjustStatus=3`、`processInstanceId=null`），`batchConfirmAdjust` 对已完成单报「非待调整状态无法进行该操作」，只适用停在待调整(2) 的单；`originId` 只能取自《查询库存明细》的 `id`（37 张历史单 524/524 条明细 `warehouseItemId` 全为 null，无法反推）；`sum` 恒为 0 是废字段，`newAvailable` 实为当前库存。实测 POLAND(279841) `test001-white` 2000 → 1997。
- **新增**: `SELLFOX_API/sellfox_adjust_test.py` — 调整单链路可复跑脚本（默认 dry-run，`--apply` 才写；建单后按状态决定是否 confirm）。

## 2026-09-10
- **新增**: `tooling-decisions/deepseek-flash-price-cut-2026-09-10-openrouter-evaluation.md` — DeepSeek flash 系列 9/10 12:00 降价（空闲 ¥0.02/¥1/¥4，高峰 2 倍；pro 不变）+ 9/14 12:00 V4 Pro 下线路由到 V4.1 Flash；按账单**行单价反解**峰谷占比（flash 高峰 79.4%）与缓存命中占比（97.2%），实测 24 天 flash 家族 ¥620.82 → ¥358.07（-42.3%）；逐上游对比 OpenRouter（因缓存单价不占优，除 pin StreamLake 外均更贵或打平）→ **结论不迁移**；含 new-api `ChannelTypeOpenRouter=20`、OpenRouter 默认自动路由 vs new-api 多渠道回退、中国用户代理/支付/账单地址/封号/数据留存掣肘。
- **更新**: `new-api-deployment/deepseek_time_pricing.py`（新价 + `PRO_EOL` + `--at` dry-run）、`sync_pricing.py`（同步新价）、`AGENT_HANDOFF.md`（第四节定价配置）— 已部署生产 `/opt/new-api/`。

## 2026-09-08
- **新增**: `integration-issues/cliproxyapi-auth-unavailable-oauth-recovery.md` — CLIProxyAPI `503 auth_unavailable` 恢复：服务健康不等于目标模型具备上游授权；按升级、浏览器 OAuth、失效认证记录隔离、重启和真实模型请求验收处理。
- **同步**: `us_openai_api_proxy/` 的 runbook、handoff、README、lesson 和受控运维 skill；不记录账号、OAuth URL/代码、认证材料、私有地址或 API key。
- **新增**: `conventions/parcel-track-handling-days-sequential-workers.md` — UPS/FedEx/GLS 迟发处理时间统一 3 个营业日（假日历仍分美国联邦 vs 波兰）；`--workers N` 是每家 N 路、三家串行（峰值 N 不是 3N）；8 月 live 全量分类合计（无单号/买家）。
- **更新**: `integration-issues/dingtalk-offboarding-hardening.md` — 补「生产部署与实测」：上海生产已部署双通道（每日 `offboarding-check.py` cron `0 3 * * *` + 实时 bridge 重建），实测 3 名离职者被每日通道自动封号（`users.status=2`）；bridge 容器需挂 proxy DB volume + `PROXY_DB_PATH` 否则 `STATUS_LATER` 无限重投；proxy key 关 key 链路经容器内函数级测试打通。
- **新增**: `integration-issues/dingtalk-offboarding-hardening.md` — new-api/sellfox-proxy 离职自动封号双通道加固：60121 判离职替代 active、本地 `dingtalk_identity_map`(unionId↔userId)、provider slug 解析、proxy 失败记 `proxy_pending` 保留映射次日补关、`offboarding_audit` 心跳/明细、`--dry-run`/`--force`。背景：真实离职场景(员工移出组织→getbyunionid 60121)原代码当 [SKIP] 永不封；active=false 误伤在职未激活员工。改动：`offboarding-check.py`(classify/熔断/retry)、`stream_listener.py`(本地映射优先+proxy 失败重投)、`main.py`(登录回填映射)；单测见 `tests/new_api_offboarding/`。

## 2026-09-07
- **新增**: `best-practices/adobe-genuine-prompts-office-openclash.md` — 办公室 OpenClash 屏蔽 Adobe 授权校验域名（AGS 弹窗）的处理与教训：hosts 无法通配 `*.adobe.io` 随机子域（lreXXXX）、三层 NAT 下 OpenClash 无法按单设备隔离、最终用 `DOMAIN-SUFFIX,adobe.io/adobegenuine.com,REJECT` 全局屏蔽模拟断网。

## 2026-09-04
- **新增**: `workflow-issues/fedex-track-batch-query.md` — FedEx 官方批量 Track（≤30/请求、配额按请求、不需自有账号）+ 账号/组织恢复路径（879197228 在 2023 组织 Centrade(10548976)，腾讯企业邮箱收重置码）+ `fedex_track` 模块 + 三条教训（反爬假报错需多源核实、按方法关键词统计会漏、配额按请求不计费）。
- **背景**: 打通 FedEx 官方跟踪需先理账号/组织碎片；headless 探针曾误判"FedEx 查无此号"，实则反爬假报错，真实浏览器可查。

## 2026-09-03
- **新增**: `developer-experience/workbuddy-custom-model-newapi-config.md` — WorkBuddy 接公司 new-api 自定义模型，`useCustomProtocol` 必须 `false` 且 `url` 带 `/v1`，否则发消息只回「任务完成」无正文。
- **新增**: `.agents/skills/workbuddy-config/SKILL.md` — WorkBuddy 接公司 new-api 的自动配置 skill（要 key → 备份 → 合并写 `~/.workbuddy/models.json` → 提示重启 → 可选 curl 验证）。

## 2026-08-31
- **更新**: `integration-issues/nas-multi-domain-access-openwrt-quickconnect.md` — QC 与 DSM 外部访问 DDNS 架构澄清；路径 A（OpenWrt 自定义域）vs 路径 B（QC/myds）；勿删 myds、无 DDNS 优先开关。

## 2026-08-28
- **新增**: `integration-issues/nas-multi-domain-access-openwrt-quickconnect.md` — NAS 多域名（nas.daneey.com / nas.vilavi.cn）、OpenWrt ACME 第二张证、DSM 反代铁律、QC 直连/cn4、联通 443 限制；政策保留 `fangzhouhui.quickconnect.cn` 统一入口。
- **新增**: `NAS_API/` OKF bundle、`AGENT_HANDOFF.md`、`.agents/skills/nas-access/`。
## 2026-08-25
- **新增**: `workflow-issues/en-channel-account-gsheet-sync.md` — Google 表渠道账号 → 生产 EN Channel Account；人变才加行；Amazon 禁止 EUR、按 Johna 九国拆；Illiosenergy/`ILLIOSPL`。
- **新增**: `channel_account_sync/` 折叠/命名库、fetch/compare/apply、OKF、Skill。
- **生产结果**: 2026-08-25 新建 18 账号、10 别名、122 个已有账号补负责人，Kaufland 补 AT/IT/FR；未建 `AMZFZHSXEUR`。

## 2026-08-24
- **新增**: `workflow-issues/sellfox-cover-combo-create-ops.md` — 三角皮壳 `PK# -> KS x1` 组合代理批量创建；与 EN `TJ#`/`sync-combos` 分流；`pageList total=0` 翻页、禁止并行 apply、组合商品不在普通商品。
- **新增**: `SELLFOX_API/cover_combo_ops.py` / `cover_combo_plan.py` 与 `docs/reference/cover-combo-ops.md`。
- **生产结果**: 2026-08-21 `status` 计划 955、线上 957 全 `isGroup=1`、`need_create=0`；只读配对候选 604（Active 91），未写 `matchByMsku`。
- **更新**: 共享库存代理 convention 阶段 2 对 KS0001/KS0248 标已完成；Skill / HANDOFF / CONCEPTS 分流。

## 2026-08-21
- **新增**: `workflow-issues/soft-wall-combo-batch-staging.md` — 软包墙围 6 底层物料 × 4 数量 = 24 个 EN 套件/赛狐组合商品批量分阶段创建；登记表去重、`plan --full`、`apply` 三步写入、阶段记录 Excel 续跑。
- **新增**: `SELLFOX_API/soft_wall_stage.py` / `soft_wall_lookup.py` — 软包墙围计划/预览/状态/结果追踪与 EN/赛狐只读快照。
- **更新**: `SELLFOX_API/sellfox_combo_ops.py` 新增 `register-customer-code`；`combo_en.py` 增加客户物料号读写；`repo_root.py` 支持根 `.env` 含 EN 凭证；`combo-ops.md` 命令表/代码地图同步。
- **结果**: 24 个组合全部创建并回读，`sync-combos` `input_en=24 / output_rows=24 / ok=24`；新补齐通途SKU 统一小写 `pcs` 登记客户物料号。
- **新增**: `workflow-issues/zipper-combo-batch-staging.md` — 拉链款 41 行全部“无捆绑SKU”，按 `基码-EN物料码-Npcs` 合成唯一客户物料号，40 个组合全部创建并回读（`sync-combos` `ok=40`）。
- **新增**: `SELLFOX_API/zipper_stage.py` — 拉链款登记表名称自动匹配 EN 底层物料、合成通途SKU、批量 apply 与阶段记录。
- **更新**: `soft_wall_lookup.py` 支持 `--product` 通用快照；`soft_wall_stage.py` 支持 `configure(product)` 复用框架。
- **新增**: `workflow-issues/flex-headboard-combo-batch-staging.md` + `SELLFOX_API/flex_headboard_stage.py` — 灵活拼接床头板单变体 4 个数量档全部创建并回读（`sync-combos` `ok=4`）。
- **新增**: `workflow-issues/support-pad-combo-reconcile.md` + `SELLFOX_API/support_pad_stage.py` — 沙发支撑垫存量 EN 套件补齐客户物料号与缺失赛狐组合（`sync-combos` `ok=3`）。
- **新增**: `workflow-issues/combinable-sofa-combo-batch-staging.md` + `SELLFOX_API/combinable_sofa_stage.py` — 可组合扶手沙发双子件组合按 `基码x数量_基码x数量` 合成通途SKU，4 个组合全部创建并回读（`sync-combos` `ok=4`）。
- **新增**: `workflow-issues/deep-sofa-combo-batch-staging.md` + `SELLFOX_API/deep_sofa_stage.py` — 深卧单人沙发椅双色组合 3 个全部创建并回读（`sync-combos` `ok=3`）；`client.py` 增加代理嵌套 detail 限流识别与单测。
- **新增**: `workflow-issues/retro-sofa-combo-batch-staging.md` + `SELLFOX_API/retro_sofa_stage.py` — 复古造型大体量沙发四模块组合 1 个创建并回读（`sync-combos` `ok=1`）。
- **新增**: `workflow-issues/outdoor-pad-combo-batch-staging.md` + `SELLFOX_API/outdoor_pad_stage.py` — 户外托盘垫 6 个套装按确认组成创建并回读（`sync-combos` `ok=6`）。
- **新增**: `workflow-issues/fringe-sofa-combo-batch-staging.md` + `SELLFOX_API/fringe_sofa_stage.py` — 弧形流苏沙发单件整沙发组合创建并回读（`sync-combos` `ok=1`）。
- **新增**: `workflow-issues/comma-sofa-combo-batch-staging.md` + `SELLFOX_API/comma_sofa_stage.py` — 逗号组合沙发 2 个组合创建并回读（`TJ#KS0369x1_KS0378x1_KS0379x1-001/002`，赛狐 3924081/3924082）。
- **新增**: `workflow-issues/triangle-set-combo-batch-staging.md` + `SELLFOX_API/triangle_set_stage.py` / `triangle_set_apply.py` — 三角有扣套装 13 个组合创建并回读（`TJ#KS0001x1_KS0260x1-001~003`、`x2-001~010`，赛狐 3924083~3924095）。
- **更新**: `workflow-issues/index.md`、`docs/solutions/index.md`、`CONCEPTS.md`
- **评审修正**: Cursor 审查后拆分 EN Tongtool Cost Review 与特殊规则 1.7.0 引擎（`engine_170.py`），禁止把本地特殊规则当 Cost Review 实现；修正库存模型/核心验收标题和阶段编号；不可破坏规则限定为组合代理模型；审计脚本 next_actions 指向 4B 成本覆盖；missing-products 补充已有独立普通 `PK#` 的评估路由；CONCEPTS 引擎路径修正为完整 `tongtool_order_cost/tongtool_order_cost/engine_170.py`，扣减规则明确仅组合代理适用。
- **更新**: `conventions/sellfox-cover-shared-inventory-transition.md` — `PK#` 组合从永久/冻结模型降为并行期单一实物池下的推荐默认；补充独立普通商品、外部共享池分配器、重复 ATP 风险及一对多/多对一库存守恒。成本路线改为验证 FBM 订单采购成本导入覆盖，记录 `mergePurchaseCost`、调整单 API 与加工单写链缺口，沙盒拆为库存和成本两条。
- **更新（早期阶段，已由上一条继续收敛）**: `conventions/sellfox-cover-shared-inventory-transition.md` — [#191](https://github.com/keyapi/fzh-data/pull/191) 在波兰 covers 确认之后：组合采购成本复选框只改商品主数据；子件 `KS` 仓 FIFO 仍不是皮壳部分成本；EN Tongtool Cost Review 按 `-Cover`/`-Foam`/`-1`/`-2` 与交付形态切片，赛狐无对等定制；当时先暂停新测试单，后续改为可用已有皮壳 FBM 订单验证成本覆盖。

## 2026-08-20
- **新增**: `conventions/sellfox-cover-shared-inventory-transition.md` — 固化三角类在通途/赛狐并行期以 `KS` 普通商品承接库存、`PK# -> KS x1` 组合商品承接皮壳 Listing 的共享库存代理；明确不是 EN Product Bundle/BOM，加工商品留待通途退役后评估，并定义单 SKU 沙盒三项验收。
- **新增**: `sellfox_cover_inventory/` 与 `.agents/skills/sellfox-cover-inventory/` — OKF bundle、Handoff、只读审计脚本及触发路由。
- **更新**: `conventions/sellfox-cover-shared-inventory-transition.md` — 美中皮壳仓 vs DANEEY 主仓；FBA/退货审计 blocked；missing-products 禁止的是有库存 `PK#` 普通商品。
- **更新**: 用户确认赛狐 `POLAND` 对应通途 covers 仓、不对应 `FZHPoland-finished`；只读审计仅对波兰成品仓名 `cautions`。
- **新增**: `conventions/erpnext-product-cover-variant-pairing.md` — 三角靠枕/无扣成品↔皮壳 suffix 审计、一键配套复制而非笛卡尔、独立 PK# 须重建（CannotChangeConstantError）、cover-only 176/27 暂缓。
- **更新**: `conventions/erpnext-item-variant-creation-convention.md` — 独立皮壳禁止 PUT `variant_of`，改为无库存重建。

## 2026-08-19
- **新增**: `workflow-issues/tongtu-warehouse-rename-reconciliation.md` — 通途自发货仓库改名（美东-/美中-/波兰- 前缀）后的三处对账登记：通途清单 → 生产 ERPNext `Tongtu Shipping Warehouse`（新建照抄分公司成本列）→ 财务共享表「订单发货仓库对应成本来源」（参考旧名行、美东/波兰退货仓按主仓口径推断并确认）。含凭证在父仓库/worktree、uv、控制台编码、dry-run 等经验教训。
- **新增**: `.agents/skills/tongtool-warehouse-sync/SKILL.md` — 仓库改名/登记触发词 skill，handoff 指向上述文档。
- **更新**: `workflow-issues/index.md`、`docs/solutions/index.md`、`CONCEPTS.md`

## 2026-08-17
- **新增**: `workflow-issues/ostkus-account-reconciliation.md` — OSTKUS 账期与 EN Tongtool Order 对账；覆盖拆单后缀、OSFD- 前缀、重复主单、金额字段口径、跨期退单。
- **新增**: `workflow-issues/index.md` 更新

## 2026-08-14
- **新增**: `workflow-issues/pb-reconciliation-monthly-update.md` — PB 对账表月度更新脚本化（追加付款/补录发票/截止判定/双开票映射/不重不漏校验/颜色标记）+ UPS 交付核查判断迟发 vs PB 漏结算；openpyxl 全量重算、显式填色、CSV 数值转换陷阱。
- **更新**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 活证据≠Gold A、跨站同 MSKU/ASIN 传播、意图≠子串、配对≠库存主线；对应 sibling 分支 `feature/amazon-pairing-evidence`。
- **新增**: `developer-experience/cursor-tongtool-mcp-registration.md` — Cursor 通途 MCP 不会从 clone/Marketplace/安装提示出现；`setup_cursor_mcp.py` 写用户级 mcp.json；同会话 goodsQuery 200。
- **新增**: `workflow-issues/tongtool-sku-rename-gsheet-remap.md` — 通途主档 SKU 改名导致 1.7.0 漏匹配；本地 gspread 凭证 + 订单 Google Sheet 旧名替换 + goodsQuery 校验。
- **新增**: `workflow-issues/index.md`
- **更新**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 记录四家族试点的真实召回/排序指标、3,557 条分层对账、主动弃权和反馈溯源要求；明确模型未达生产门槛。
- **更新**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 记录四家族试点的真实召回/排序指标、3,557 条分层对账、主动弃权和反馈溯源要求；明确模型未达生产门槛。
- **新增**: `developer-experience/cursor-tongtool-mcp-registration.md` — Cursor 通途 MCP 不会从 clone/Marketplace/安装提示出现；`setup_cursor_mcp.py` 写用户级 mcp.json；同会话 goodsQuery 200。
- **新增**: `workflow-issues/tongtool-sku-rename-gsheet-remap.md` — 通途主档 SKU 改名导致 1.7.0 漏匹配；本地 gspread 凭证 + 订单 Google Sheet 旧名替换 + goodsQuery 校验。
- **新增**: `workflow-issues/index.md`

## 2026-08-13
- **新增**: `developer-experience/windows-codex-powershell-utf8.md` — Windows Agent 的 `&&` ParserError、GBK/UTF-8 乱码与 PS 5.1 BOM 对照；`scripts/env_doctor.py` + `windows-agent-shell` skill；本机 PS 5.1 基线 vs pwsh 7.6.4 验证。
- **新增**: `developer-experience/index.md` — developer-experience 分类索引。
- **新增**: `integration-issues/tongtool-erp2-mcp-shared-rate-limit.md` — 记录通途 ERP2 MCP 的本机凭证分层、运行时权限探测、524/525/526 判别，以及双 App 共享五次每分钟限流的实时证据；对应基础文档、Skill、Handoff 与可复跑只读测试脚本已在 `tongtool_api/`。

## 2026-08-11
- **新增**: `conventions/amazon-online-product-pairing-candidate-workflow.md` — 区分 Amazon 在线商品和多平台配对机制，固化别名严格匹配、人工确认、规则/ML 分阶段演进及禁止自动写入的边界。
- **更新**: 三方主线惯例补充 PR #162 后的 1411 行映射快照、HM1510 REST 417 阻断与冻结结论；映射表是库存同步设计输入，不是写入授权。
- **新增**: `conventions/tongtu-en-sellfox-instock-sku-mainline.md` — 通途有库存 SKU 的完整码登记、EN 产品映射、赛狐产品 SKU 验证及半成品边界。
- **背景**: 旧审计把 `-Cover/-Foam` 的基码匹配误作完整登记；本次以 EN 产品 `customer_items` 完整回读修正，固化三系统主线与只读调查边界。

## 2026-08-07
- **新增**: `conventions/erpnext-item-variant-creation-convention.md` — EN 物料/变体创建惯例（四层属性体系、9 类配套物料、API 创建链条、已知坑）
- **新增**: `conventions/index.md` — conventions 分类索引
- **背景**: 通途→EN→赛狐缺口分析中补建缺失物料 `KS0001-CMM-153-PURPLE`，逆向还原物料体系惯例；此前无文档记录此惯例

## 2026-09-22
- **新增**: `integration-issues/carrier-label-batch-field-length-limits.md` — Overstock/Wayfair 组合件（皮壳 `-Cover` + 海绵 `-Foam`）在仓库侧炸成多 SKU，而一个包裹只能贴一个面单 ⇒ 给承运商的批量导入 csv 必须**每包裹一行**、把多个 SKU 拼进同一个字段。这段拼接随 SKU 数变长，撞上承运商字段硬上限：**UPS Reference 1~5 各 35 字符、超了整批被拒**（`Invalid Package Reference Value`，第三方支持文章明写这是 carrier limitation）；**FedEx 批量模板 `Available headers` 里 `poNumber=String(30)`、`reference=String(30)`、`itemDescription=String(450)`、`harmonizedCode=String(35)`** —— 同一个拼接串在不同字段要用不同上限，不能一刀切。两者失败模式不同：UPS fail-loud（整批拒）、FedEx fail-silent（承运商侧按上限切，位置不受控）。方法上固化两条：**上限从官方模板自带的字段定义表读**（FedEx 那张表就在本地模板 xlsx，不用翻文档站）、**用"承运商已接受历史文件的最长值"交叉验证**（实测 UPS Reference 2 最长 30 / FedEx poNumber 最长 29，都贴着上限 ⇒ "一直没出问题"只是还没撞上多 SKU 订单）。关键认知：**这个风险是模板从「每包裹一行」改「每货品一行」新引入的** —— 旧模板下每包裹只有一个 SKU、合并是空操作（最长 32 字符），历史里找不到先例。
- **新增**: `integration-issues/sku-name-backfill-via-en-customer-code.md` — 背贴 4×2" 标签的品名查名键 = 通途导出 `Reference 2` 的**原样字符串**（两侧 `strip().upper()` 后匹配），表是 `US SKU Name` sheet。某组合件的海绵 SKU 缺失 ⇒ 标签那一行品名空白。**通途SKU 在 EN 存于 `Item.customer_code`（逗号串）与 `customer_items[].ref_code`（子表），不在 `item_languages.tt_sku`** —— 后者只存 `-Cover` 形式的成品码，海绵件的 `item_languages` 干脆是空的。三个访问性坑（均实测）：`Item Language` **子表不能 list**（`403 PermissionError`，但可逐 Item 读带出）、`commodity_sku` **不能当过滤字段**（`Field not permitted in query`）、`Item.name` 是**物料编码**不是通途SKU（`name like %TT...%` 一律空）。PIM API `vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping` 能一把映射，**但必须先做假阳性测试**（丢 `TT9999999K9999999-Foam` / 随便一个串进去应返回 `not_found`）并横验同族自洽（100→100、153→153、160→160、183→183 全对）才敢用。**尺寸↔序号不成顺序**（153 是 `...4183`、160 却是 `...4182`）必须逐条读不能推。另记一条判断法：同一个件在**通途=直角 / EN PIM=方格 / 同包裹皮壳=菱形**时三者互斥、且 EN 里三种款式各有独立物料 ⇒ 该件是**跨款式中性件**，写中性名比咬着某个款式名安全。实战：8 个尺寸对账出「7 缺 1 有」，从 EN 借数补齐后复测缺名数 0。
- **新增**: `developer-experience/colab-notebook-drive-api-editing.md` — 改同事 Colab notebook 代码的可复现做法：`.ipynb` 在 Drive 里就是 JSON 文件（无专门 API）。**读要 `alt=media`**（`/export?mimeType=` 对 Colab 文件 403 `Export only supports Docs editors files`）；**写用 multipart 并显式带 `mimeType: application/vnd.google.colaboratory`** 防类型被改；cell 定位用 `strip()` 匹配并**断言唯一命中**（commented-out 老代码与生效代码只差一个 `#`）；写完**必须重新下载逐段断言**「除目标格外其余 cell JSON 逐字相等」（本次 29→31 cells）；写前比 `modifiedTime` 做并发守卫（实测用户跑一次 cell、Colab 把**执行输出**存回文件就会动）；语法自检要把 `!cmd` 中和成 `pass  # !cmd` **且保留缩进**（丢缩进会得到假 `IndentationError`，实测白折腾一轮）；"先备份再改"落点是 notebook 自带的 `## 下面老代码，不用运行` 区块。**⚠️ 私钥风险**：业务 notebook 常把服务账号私钥塞在顶部依赖安装 cell 里 ⇒ 本地兜底备份必须放**仓库外**。
- **新增**: `developer-experience/colab-shell-out-filename-spaces.md` — `!zip -q {zip} {" ".join(files)}` 在文件名**含空格**时必然失败：`!cmd` 把整行原样交给 shell，`Overstock-...-351 每货品一行_UPS_....csv` 被空格切成两个不存在的路径 ⇒ `zip error: Nothing to do!`（非零退出但**不抛异常**）⇒ 压缩包根本没生成 ⇒ 紧接着 `files.download()` 抛 `FileNotFoundError`。**报错点离根因很远**（崩在 download，因在 zip），容易误判成"下载坏了"。修法：换 Python `zipfile`（收字符串列表，没有 shell 这一层）。预防：notebook 里凡"把变量拼进 shell 命令"先问值可能含空格/引号/中文吗；业务同事保存导出时会顺手加中文后缀（`... 每包裹一行.xls`）正是本次来源。通用思路：**报错点离根因远时，先怀疑"上一步静默失败了"**。
- **更新**: `CONCEPTS.md` 补「背贴」与「通途SKU 的后缀形态（`-Cover`/`-Foam`/裸基础码）」两条词条（此前文档里高频使用但从未定义）；`sellfox_shipping/AGENT_HANDOFF.md` 补字段上限与查名链两条坑；`google_drive_permissions/AGENT_HANDOFF.md` 把 `.ipynb→Drive files.get/update` 那一行展开成可操作要点并指向新文档。
- **新增模块**: `colab_kit/`（+ skill `colab-kit`）—— 把「改同事 Colab notebook」这套动作从**每次现写 Drive 调用**固化成 CLI：网络命令 `meta`/`fetch`/`backup`/`guard`/`write`/`verify`，本地命令 `cells`/`dump`/`find`/`insert`/`backup-cell`/`sed`/`syntax`/`diff`。**触发动机**：本次会话的读/写/改/回读校验每一步都是临时手写的，而这类需求会反复出现（另一条线「PB 订单处理」已从 Colab 迁入仓库，Overstock 这条将来也可能迁）。实测：本地命令对真实 31 格 notebook 跑通（`find` 对同一锚点命中 **2 格** —— 生效代码 + 注释掉的老代码，正是 `sed` 默认拒绝多命中的理由）；网络命令只读手测 `meta`→`fetch`→`guard`（过期 `modifiedTime` 正确 exit 2）→`verify --expect-changed ""`；`uv run pytest colab_kit/tests -q` → 14 passed。
- **新增模块**: `tongtool_order_shipping/`（+ skill `tongtool-order-shipping`）—— **module 归属修正**：上一批把「承运商字段上限」与「背贴品名补齐」两篇挂成 `module: sellfox_shipping`，那是错的（`sellfox_shipping` 是**赛狐侧**尾程打单）；这两篇讲的是**通途订单导出**的发货侧后处理，只是"都用 UPS/FedEx 面单"这点关系。两篇的 `module:` 已改为 `tongtool_order_shipping`。该模块**目前无代码** —— 流水线本体仍是同事的 Colab notebook，本目录承载硬约束与将来迁入的落点（先例 `pb_orders/`）。
- **修复（既有漂移）**: `intent_router/tests/test_catalog.py::test_catalog_skill_set_equals_agents_md_table` 在本批之前**已经是红的**（已用 HEAD 版文件核实）：AGENTS.md 有 `sellfox-amazon-settlement` / `dingtalk-oa-approval` / `gsheet-monthly-order` 三行，而 `intent_router/catalog.yaml` 一个都没有 —— 即「加了 AGENTS.md 行却没补 catalog 条目」，正是该文件头部注释与 `ce-okf` 记录里警告过的同一类脱节（这次方向相反）。已补 3 条选项（含各自的 `coverage`/`exclusions`/`examples`，`dir` 均验证存在），本批后 `pytest intent_router/tests colab_kit/tests` → **274 passed, 33 skipped**（原先 1 failed）。同时给 `sellfox-shipping` / `tongtool-order-cost` / `google-drive-permissions` 三条的 `exclusions` 补上新兄弟模块，让路由真正分得开。
- **新增**: `tooling-decisions/colab-kit-notebook-edit-toolbox.md` —— 为什么把「改同事的 Colab notebook」做成**独立模块 + skill**（`colab_kit/`）而不是塞进 `google_drive_permissions/`。三条取舍：网络/本地命令分开（改 cell 是纯 JSON，可离线单测）；`verify` 与 `guard` 是**一等公民**（手写时最容易省掉的正是这两步）；`sed` 默认拒绝多命中（实测同一锚点命中 2 格）。与 `google_drive_permissions` 的分界写成对照表：**权限 vs 内容**，失败模式从"权限判断错"变成"**写坏别人的活文档**"。另一条动因是会重复 —— `pb_orders/` 已迁过一条，Overstock 这条将来也可能迁。
- **新增**: `developer-experience/gh-pr-edit-projects-classic-workaround.md` —— `gh pr edit <n> --title/--body-file` 在本机（gh 2.71.2）**exit 1 且改动不生效**，报 `GraphQL: Projects (classic) is being deprecated … (repository.pullRequest.projectCards)`：`gh pr edit` 走 GraphQL 且前置查询会取 `projectCards`，弃用后整条命令在发出修改前就中止。绕法 = **`gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -f title=… -F body=@file`**（REST，不碰 `projectCards`），改完 `gh pr view` 回读。**真正的坑是信号不可信**：命令串里接了 `| tail` 时 `$?` 是 `tail` 的、永远 0，报错行也被淹没 —— 本次就是靠回读 PR 才发现标题没变。
