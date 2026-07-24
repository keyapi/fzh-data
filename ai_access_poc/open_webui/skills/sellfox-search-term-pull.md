---
name: 赛狐搜索词拉取
description: 只读 — 向用户确认店铺后调用 sellfox_pull_sp_search_term 拉取 SP 搜索词报告并回报文件路径；禁止自动否词或改广告
---

# 赛狐 SP 搜索词拉取（只读）

## 何时使用

用户说「拉搜索词」「拉广告报告」「帮我下搜索词报表」等时使用本 Skill。

## 硬性禁止

- **禁止**创建/修改广告活动、关键词、竞价、预算、否定词。
- 赛狐当前 **无广告写 API**；即使将来有，本 Skill 也不自动下否词。
- 不要用未经验证的 `advertise/` 脚本输出当作运营结论。

## 步骤

1. 若不知店铺：先调用 Tool `sellfox_list_shops`，让用户选店铺名或 id。
2. 确认 `days`（默认 7，最大 90）。
3. 调用 Tool `sellfox_pull_sp_search_term`（`shop_id` 或 `shop_name` + `days`）。
4. 向用户汇报：`shop_name`、`task_id`、`filepath`、`bytes`、耗时。
5. 说明：文件在服务器 `/data/sellfox_reports/`；分析/否词建议须运营人工审，不要自动执行。

## 失败处理

- 超时 / 「生成中」过久：建议缩小 `days` 或换店重试；报告限流时等待后再拉。
- 缺凭证：提示管理员在 Workspace → Tools → Valves 配置 `SELLFOX_APP_ID` / `SELLFOX_APP_SECRET`，**不要向运营索要 App Secret**。
