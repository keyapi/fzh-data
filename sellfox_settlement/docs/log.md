---
okf: v0.1
type: Log
title: sellfox_settlement 变更日志
tags: [sellfox, amazon, settlement, okf, log]
---

# 变更日志

## 2026-10-10
- **技术验证入库**：2026-08 非 V2 CSV/PDF、渠道账号、EN 成本与银行到账缺口的只读验证脚本和三份调研落入分支；业务明细仍在仓库外。经验库入口 `docs/solutions/tooling-decisions/amazon-non-v2-tax-technical-validation.md`。ZJ 口径、历史成本和 8 月 Amazon 银行流水仍缺。
- **收尾沉淀（ce-okf）**：新增约定 `docs/solutions/conventions/external-questionnaire-via-notion.md`（外部问卷：单份仓库 MD + Notion 访客通道；三条硬边界：MCP 无邀请工具 / 国内需翻墙 / 数据出境只私享）；AGENT_HANDOFF 增 §11，记录技术负责人已答的 **T01—T08** 原话（含 **通途尾程人工导入、导入后次日才显示、一次下载不能跨太久、EN `tongtool_integration` 待完善、报表 FBA 订单不一定在通途**）作为 Codex 接手入口。
- **合并为单份底稿（Notion 可直接导入）**：把填写区重排为 Notion 友好的 4 列表（编号/需确认事项/建议/你的答复+证据）、相对链接改为纯文本仓库路径、`<>` 自动链接改裸 URL，并删除临时派生稿——底稿本身即可导入 Notion，不再有第二份会漂移的副本。
- **新增填写渠道选型调研**：比较让 ZJ 填写问卷的渠道——Notion 公开页+允许编辑（不推荐，公开可编辑且 prompt-injection 风险）、Notion 访客可编辑单页、Notion 原生表单（公开=匿名、不能改自己的回答）、自建局域网表单（最重、仅内网可达）、Google 表单→表格（最贴合现状，已有 SA+gsheets 读取）、钉钉（候选未深入）；结论与来源见 `docs/research/2026-10-10-zj-questionnaire-collection-options.md`。
- **补充 Notion 访客单页实测要点（§2.4）**：核实「完整 MD 导入成页 + 简单表格可转（复杂表格降级、需清理）」「Can edit 即可直接填写（非提交）」「Google/Apple/Microsoft 免费登录」「Free 10 访客够用」「国内访问 Mixed、需翻墙兜底」「Notion MCP 无分享/邀请工具，访客邀请须界面手动」；给出落地流程与'填写区改数据库更好填'的建议。
- **新增分析底稿**：盘点 2026 年 8 月 Amazon 非 V2 月度交易 CSV 与汇总 PDF，记录 65 对文件、13 套本地化表头、零活动及文件名异常，并拆分平台报送收入/退款候选、Amazon 税费、Settlement/银行回款、EN BOM / Tongtool Cost Review 与 FBM/FBA 成本层。
- **重构为 ZJ 可填写底稿**：新增第 2 节填写区——ZJ 决定与证据总表（F01—F20，含 `ZJ 答复/证据链接/适用主体/生效期间/状态` 列）、技术负责人确认表（T01—T08）、税务顾问复核清单；第 1.1 节给出 ZJ 的填写与回传方式、可直接用 AI 工具、不经用户传话；原「待确认问题」清单收并到第 2 节，避免两处口径不一致。
- **修正文件名并给出期间校验结论**：`如森法国2020608.csv`、`如森荷兰2020608.csv` 修正为 `202608`（已核内部交易日期与配对 PDF 均为 2026-08）；明确当前 65 对文件**未发现已证实的下载不完整或期间选错**，「下载不完整/期间选错」仅作为校验结果状态保留。
- **新增渠道账号命名与别名统一（第 4.4 节）**：以 Google 表 `渠道账号（20260521起在此维护）` 为唯一标准源，`{channel_code}{account_code}{region}` 命名、欧洲站点国家后缀、别名只增不改、禁止裸品牌/裸国家码与歧义别名、身份层级与维护方式。
- **扩展成本链表述**：明确 EN Tongtool Cost Review 同时回出产品成本而不只是尾程；FBM 用 `order id + sku`→包裹号接现有尾程流水线；FBA 只补产品成本（+可得头程），履约/仓储费取 Amazon 报表，不叠加 FBM 尾程；保留「Cost Review 完整选路源码不在本仓库、不得杜撰公式」的边界。
- **新增后续实施路线（第 11 节）**：8 阶段交接计划（文件覆盖/账号归一/多语言标准化+PDF 对账/财务口径配置/FBM 成本/FBA 探针与 EN enrichment 接口/Settlement 银行桥/可复跑月度工作簿），供下一个 AI 继续。
- **补充监管与主体边界**：整理 2025—2026 年平台涉税信息报送及申报比对背景，增加北京、深圳和境外法人归属证据矩阵与财税待确认问题；引用深圳市商务局“阳光化”试点公开信息。
- **更新导航**：将分析底稿加入 `docs/research/index.md` 和模块 `docs/index.md`。

## 2026-09-09
- **补齐发现链与 OKF**：调研文加 YAML `type: Research`；新建 `docs/lessons/`（踩坑 Lesson）；`docs/reference/how-we-tested-2026-09.md`（可复跑测试方法+断言）；AGENT_HANDOFF §9 更正钉钉跨月导出已落地事实；AGENTS.md 模块索引 + skill 触发词（迟交/错位/钉钉账期等）；CONCEPTS 钉清两套「账期月」归属；根 `index.md` 经 `scripts/update_index.py` 同步。
- **初始化 OKF bundle**: 建 `docs/`（index.md/log.md）`docs/research/` `docs/reference/`；`AGENT_HANDOFF.md`；`docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md`（从 `docs/research/` 移入）。
- **新增** `docs/reference/settlement-v2-endpoints.md`、`docs/reference/column-mapping.md`、`docs/reference/gsheet-access-and-channel-account.md`——端点/字段、科目映射、谷歌表访问+渠道账号别名规则。
- **文档沉淀**：`docs/solutions/tooling-decisions/amazon-settlement-autofetch-sellfox.md`（ce-compound 知识沉淀+交接）；`docs/solutions/architecture-patterns/account-period-revenue-reconciliation-ecosystem.md`（账期/收款核算生态地图）；`docs/solutions/workflow-issues/amazon-account-period-late-submission-audit.md`（账期迟交审计+规则+最新状态多账期结果）；`CONCEPTS.md` 增「账期/回款核算」术语簇；技能 `sellfox-amazon-settlement` 入 `.agents/skills/`。
- **工具**：`reconcile_amazon.py`（shops/fetch/fetch-custom/candidates/reconcile，`--currency` 取原币）；`audit_late_submission.py`（单文件多账期桶迟交审计，`--platform` 分流）；交叉表 `out/storeName_to_account_candidates.csv`。
- **实测**：赛狐结算中心V2(6月103结算/16.8k明细)、紫鸟插件列式报表(`getPlugPageList type=3`→ZIP→32列CSV) 均取通；赛狐店名↔渠道账号写入共享表；多账期迟交审计跑通(2026-09-09 导出, 全平台1528行/Amazon ~660行)。
