---
okf: v0.1
type: Log
title: 调研记录变更日志
description: docs/research 目录变更历史
---

# 变更日志

## 2026-10-29

- **新增**: [2026-10-29-direct-ship-and-dual-warehouse.md](2026-10-29-direct-ship-and-dual-warehouse.md) — 两处业务更正：① 美东/美中不是调拨，改为「跨仓直接发货（需确认可售/退货品质）」；CMPR-194 改为「美中 2 个可直接履约，剩余 2 仍缺」；② 归属表 v6 加双仓销售（2026 双仓 25 个、实质 11 个），实质双仓的归属/建议改为按两仓分别补/核，少量双仓写备注，新增 sheet 11_双仓销售。产物 `46近端缺口_调拨候选_2026-10-28_v3.csv` + `美国与波兰仓库归属_2026-10-28_v6.xlsx`；v5 保留；只读。

- **新增**: [2026-10-29-48-key-decision-draft.md](2026-10-29-48-key-decision-draft.md) — 48 待定量的人工决策草稿（DRAFT）：按设计稿 5 列（商品/仓/角色·现状·系统决定·时间与后果·人只确认）逐行写；47 行近端、1 行非近端；表内可同国调拨 0；8 行近零（97 目标）其中 3 行两窗口近零；SS 仅 8 行应用；最晚下单日 48/48 已过；标注 DRAFT/未验收/非采购量。产物 `analysis/48待定量_人工决策草稿_2026-10-29.xlsx` + 说明；脚本 `scripts/build_decision_draft_48.py`；只读。




## 2026-10-28

- **v2（口径修正）**: 近端调拨候选按复审 F1–F3 修正 —— 去掉对已净额 Q97/旧参考的重复扣库存（CMKTR-140 保留 124.269、CMPR-194 调后仍缺 2；参考合计 407.220、调后 405.220）；拆两列（长窗 Q97 / 旧35天净缺口）并逐行标口径；跨洲排除供给 7 行披露（含 DM-100-YELLOW 美中 PO/在途各 123，不相加不抵扣）。48 行覆盖不变；产物 `*_v2.csv` + 报告 v2；只读。

- **新增**: [2026-10-28-near-gap-transfer-candidates.md](2026-10-28-near-gap-transfer-candidates.md) — 近端缺口调拨候选：53 v3 近端兜底 48 行（46 行 10/26 起 + 2 行 11/02 起），仅 `KS0002-CMPR-194-GINGER` 可从美中调 2；47 行无可调（15 美东同国无货源 + 32 波兰不可跨洲）；潜在改配（开放 PO/在途）0；源库存按 (仓,SKU) 只分配一次、他仓供给不抵扣；产物 `analysis/46近端缺口_调拨候选_2026-10-28.csv` + 报告；只读。

- **v2（口径小修，数量未变）**: 48 键 97/157 原型按复审 F1–F5 修正 —— F1 写明 2.779 天需求盲区未估算；F2 σ 改称「历史销量波动代理」、SS 标政策情景未校准；F3 近零分窗口（97 目标 8 行、157 目标 3 行）；F4 表头/备注 98/161→102/158；F5 汇总改全精度（Q157 662.26、波兰 249.23）并标舍入差。逐行数量与 v1 完全一致；产物 `*_v2.csv` + `报告_v2.md`；脚本 `scripts/h48_prototype_97_157_v2.py`。

- **新增**: [2026-10-28-48-key-97-157-prototype.md](2026-10-28-48-key-97-157-prototype.md) — 48 个「可补单—待定量」键的 97/157 天原型。需求只用真实预测曲线（forecast r4 → run-2026-10-26-r6 的 27 个周桶）积分，**不按旧 35 天比例放大**；因曲线是周桶，**精确第 97/157 天不可算（0 行）**，按项目既定「桶结束 ≥ 目标」取 w14/w22（102/158 天）给出 48 行；SO 管线全 0 无需去重；IP=10-28 同仓已证可发+已证未到货（未证不抵扣）；SS 政策 A1.5×/95%、B1.0×/90%、C1.0×/85% 只在 σ>0 的 8 行应用，其余标未应用；Q 合计 97 目标 441.82 / 157 目标 662.25，需求 356.52/551.83（旧 35 天 116，比值 3.07×/4.76×，逐键中位 2.06）；充分度 可算 40/部分 8（预测近零 Q<1）/不足 0；最晚下单日 48/48 已过。产物 `analysis/48待定量_97_157_原型_2026-10-28.csv` + 报告；脚本 `scripts/h48_prototype_97_157.py`；全程只读。

- **v3（v2 复审 accept-with-findings 小修）**: PO↔DN 匹配只改 5 项、匹配结果不变（27 首选与 v2 全等，9/9 正式链接仍 rank1）。P2#1 非正式推荐改标「候选建议→DN-…（未正式登记）」，「本DN」只留正式（18→v2 报告误写19 已更正）；P2#2 FBA 增加「全部明客码均为 FBA」分支，mixed/unknown 不算 FBA（+3 测试）；P2#3 exception 每条带 uom/qty_by_uom/role/aliases_raw_all，JSON 删跨单位 dn_qty_total 改 dn_qty_by_uom（个38,422/套83,805/件100，recon 个22,565），不做套/件换算；P3#4 边界改 32 FBA(含5取消)+3 非FBA取消+28=63，敏感性改「27首选不变，部分分值与低位排序变化」（DN-00089 第3位变化）；P3#5 新增 aliases_raw_all 保留 `删除` 前缀原始别名。产物 `*_v3.csv/json` + `PO_DN候选匹配报告_2026-10-28_v3.md`；测试 17 passed；全程只读。

- **v2（复审 reject 后重做）**: PO↔DN 候选匹配修复 F1–F5 —— F1 正式归属改用 EN `custom_tongtool_purchase_order` 只读导出（`scripts/en_dn_po_field_export.py`，带 manifest/sha256，不再硬编码），评分前排除他人正式占用的 PO，`official_owner`/`proposed_owner` 分列，非正式推荐不再写「本DN」，采纳对做逐 SKU `alloc_qty` 分配；F2 `qty_fit` 改逐 SKU 绝对差（测试覆盖 DN(10,90) vs PO(90,10) 反例 = 0）；F3 多别名 63 行/518 件/9 DN，渠道规则解析 28 行/271 件、隔离 35 行/247 件，不挑别名抬分；F4 反查与 PO 别名统一清 `删除`（DN-00086 恢复 10/10、141=141）；F5 通途 PO 补拉改 `scripts/tongtool_po_pull.py` 带分页 manifest（7/25–8/26 = 2 页 113 行，修正 v1 只取 100 行漏 PO021712），「7/26–8/25」改述为「查询窗口返回 0 行」。**业务规则并入**：纯内胆 ND# DN 与 FBA DN → 「不建PO/无需匹配」，属预期正常；DN-26-00068 由「无候选」改判纯内胆。结果：28 DN = 正式链接 9（多出 DN-26-00114→PO021742）/ 有候选 18 / 纯内胆 1 / FBA 0 / 无候选 0，9 张正式链接全部 rank 1（8 张已知样例仍全中）。产物 `*_v2.csv/json` + `PO_DN候选匹配报告_2026-10-28_v2.md` + exception companion（322 行）；测试 `tests/po_dn_match/test_po_dn_v2.py` 8 passed。全程只读。

- **新增**: [2026-10-28-po-dn-candidate-matching.md](2026-10-28-po-dn-candidate-matching.md) — PO↔DN 候选匹配（只读）。8/1 起 28 张 DN / 2,589 行里 8 张有 EN 正式链接 `custom_tongtool_purchase_order`；其余 20 张做候选：**19 张给出候选、1 张（DN-26-00068）无候选**；8 张已确认样例 **8/8 复现为 rank 1**。口径：PO 日期用 `createdDate`、窗口双向 ±90 天（实测同日 12 / PO 晚于 DN 15 / 早于 0）、SKU 去 `-Foam/-Cover` 后缀归一、DN 无客户码行按 item_code 反查 `sku_item`（2,310/2,589 可解析，279 行为材料/组件）；数量按 SKU 逐行对账（337 行：302 全等、35 不等且全部 PO>DN）。关键发现：8/26 集中建的 PO021704–021712 是 8/4–8/21 六张 DN 的**回溯建单**；7/26–8/25 通途无任何 PO（只读 API 确认）；PO021743 本地快照缺失，已只读补拉。产出 `D:/Work/fzh-order-store/analysis/po_dn_candidate_links_2026-10-28.csv`、`po_dn_sku_recon_2026-10-28.csv`、`PO_DN候选匹配报告_2026-10-28.md`（本地，不入库）；脚本 `scripts/po_dn_candidate_match.py`。未改 EN / 通途、未 push。

- **新增**: [2026-10-28-wayfair-cg-source-map.md](2026-10-28-wayfair-cg-source-map.md) — Wayfair CG（Castlegate）仓来源归类，worker E 交付给 YTQ 核对。口径：8/1–10/28 自发货订单里 `warehouse=WayfairCG-*`（account `WFCastleGateUS`），GS（8/1–9/30，CG 单到 9/18）+ EN（8/26–10/26）合并 593 单 / 677 件 / 49 SKU；来源仓判定用「窗口内该 SKU 在美东池/美中池的出库路径」，旁证为 8-07 与 10-23 两池库存。结果 26 SKU 美东 / 23 SKU 美中 / 0 无法判断（强 45、中 4）；Wayfair dropship NJ(美东)/TX(美中) 位置信息 39/39 与判定一致、0 冲突。**关键限制**：通途库存变动 API 仅 7 天，回查不到 8–9 月调拨单 → 来源是推断不是凭证；订单侧 CG 仓只有 Cranbury，McDonough/Perris/PortWentworth/Romeoville 只在 Wayfair 库存表出现。产物 `D:/Work/fzh-order-store/analysis/wf-cg-source-map-2026-10-28.xlsx`（本地，不入库）；脚本 `scripts/wf_cg_source_map.py`。退货例外按 SKU 标候选（22 个 SKU 有窗口退货仓出库），未扣减件数。

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
