---
name: 赛狐搜索词拉取
description: 只读 — 确认店铺后拉取 SP 搜索词报告，并用返回的 summary/CSV 做分析；禁止自动否词或改广告
---

# 赛狐 SP 搜索词拉取与分析（只读）

## 何时使用

用户说「拉搜索词」「广告情况」「分析某店一周广告」「搜索词报告」等时使用本 Skill。

## 硬性禁止

- **禁止**创建/修改广告活动、关键词、竞价、预算、否定词。
- 赛狐当前 **无广告写 API**；即使将来有，本 Skill 也不自动下否词。
- 不要用未经验证的 `advertise/` 脚本输出当作运营结论。

## 步骤

1. 若不知店铺：先调用 Tool `sellfox_list_shops`，让用户选店铺名或 id。
2. 确认 `days`（默认 7，最大 90）。
3. 调用 Tool `sellfox_pull_sp_search_term`（`shop_id` 或 `shop_name` + `days`）。
4. **分析必须用返回 JSON 里的 `summary`**：
   - `summary.totals`（花费/销售额/订单/曝光/点击/ACoS/ROAS）
   - `summary.top_by_spend_csv`（按花费 Top N 搜索词）
5. **禁止**对用户说「xlsx 是二进制我读不了」——Tool 已解析成文本摘要。
6. 若用户只给了已有路径：调用 `sellfox_summarize_search_term_xlsx(filepath=...)`。
7. 分析结论须标明「只读建议，需运营人工审」；不要自动否词。

## 失败处理

- 超时 / 「生成中」过久：建议缩小 `days` 或换店重试；报告限流时等待后再拉。
- 缺凭证：提示管理员配置 Tool Valves **`SELLFOX_PROXY_API_KEY`**（`https://api.vilavi.cn/sellfox/admin`），或备用 `SELLFOX_APP_ID` / `SELLFOX_APP_SECRET`；**不要向运营索要密钥**。

## 默认启用（管理员）

Workspace → Models → 编辑 `deepseek-v4-flash`（及常用模型）→ Tools 勾选本 Tool → Save。  
勾选后新对话会自动带上 Tool，无需每次手动开 Available Tools。
