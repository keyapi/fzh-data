---
okf: v0.1
type: Log
title: 解决方案变更日志
tags: [solutions, log]
---

# 变更日志

## 2026-09-21
- **更新**（同日后续）: `intent_router/catalog.yaml` 从 35 补到 **56** 项 —— 补入 11 个此前漏掉的 skill 目录 + 10 个此前漏掉的**业务模块目录**（`advertise` / `amazon_pairing` / `ups_track` / `pb_reconciliation` / `cost_adjust` / `sellfox-api-proxy` / `ai_access_poc` / `google_drive_permissions` / `nas_product_visuals` / `sps_api`），`AGENTS.md` 模块索引表同步（35 → 56 行）。**关键认知：该表原是「策展子集」而非完整清单** —— 18 个顶层模块目录里 16 个不在表内，所以在此之前 `advertise`/`pb_reconciliation`/`ups_track` 这类模块**根本路由不到**。纳入规则（可审计）：有 `AGENT_HANDOFF.md` 或 `docs/`、有代码、且 2026-08-01 后仍有提交（或引用 ≥5 次）；据此排除 `test_upload`（0 py 已废弃）、`EN_shopify`（无文档）、`SPS_Selenium_Local`（仅 README 零引用）、`pdf_to_md`（文档齐但 3 个月未动）。**`dingtalk` 刻意不单列** —— 它就是 `dingtalk-robot` skill 的实现，单列会造出两个都像「发钉钉消息」的选项。**数字更新**：标注样例扩到 31 条（每新模块一条），56 选项下 **33/33 全中**，`confidence` 0.98–1.00、`ambiguity` 0.66–0.98、约 9815 输入 token ≈ $0.00041/次 —— 正面回答了原计划风险 #3「选项变多会互相干扰」。
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
