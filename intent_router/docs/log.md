---
okf: v0.1
type: Log
title: intent_router 变更日志
---
# 变更日志

## 2026-09-21

- **初始化模块**: 建立 `intent_router/` —— 用 TypeSafe Jev / System One 把中文请求路由到本仓库
  本仓库各业务模块。动机：触发词匹配是关键词而非语义，`item-cost`/`stock-init`/`warehouse-restock`
  同吃 EN BOM 成本，触发词天然分不开。
- **契约探针先行**: 实现前先用 2 选项 payload 打了一发真实请求，确认 criteria 的 object 形式被接受
  （HTTP 200，无 422），并确认 `noul` 答案的键名。避开了计划里标为「首要风险」的一项。
- **确定目录真源**: 实测自动派生不可行（`.agents/skills/` 的目录数比 AGENTS.md 模块索引表多十几个、
  触发信息三种形状；目录多对一），改为人工策展 `catalog.yaml` + 集合相等测试卡漂移。
- **修复 YAML 标量强制转换**: `examples` 里裸写的 `401` 被 YAML 解析成 int，导致 string 形式
  criteria 渲染崩溃。数据加引号 + 渲染层显式 `str()`，并加回归测试。
- **修复 .env 的 worktree 陷阱**: 本仓库既有三个加载器都假设仓库根 = `parents[1]`，在 worktree 里
  取不到父仓库 `.env`。改为有界上溯（实测命中 `parents[4]`）。
- **实测发现（写入 README/AGENT_HANDOFF）**:
  - `confidence` 在本目录上**几近饱和（0.97–1.00）**（含 `none` 胜出时也有 0.99），`--min-confidence` 实际不触发；
    真正兜底的是 `none` 选项（模糊请求与域外请求均正确落 `none`）。
  - `ambiguity` 只跨 0.87–0.98，清晰请求 0.95 与域外请求 0.96 几乎重叠，**不具区分度**，
    方向正确但不可用作闸门 → 只在「无法判定」分支显示，避免命中时误导。
  - 因此默认**总是**打印 top-3 候选，并滤掉概率 < 0.005 的填充项。
- **验证**: 离线 176 项通过（12 项 live 默认 skip）；真实调用 10 条标注样例 10/10 命中，
  模糊/域外请求均落 `none`；错误路径 401 不重试、缺凭证退出 1、`--json` 可解析。
- **补 `ce-okf` 目录条目**: PR #249 给 `AGENTS.md` 模块索引表加了 `ce-okf` 行，合并后
  `test_catalog_skill_set_equals_agents_md_table` 立刻报错并打出差集
  `只在 AGENTS.md 里：['ce-okf']` —— **防漂移测试按设计生效**。补上 catalog 条目后
  两边 35 项一致。此后新增模块务必**同时**改 `AGENTS.md` + `catalog.yaml` + skill。
- **修正 `下一步` 提示**: `.agents/skills/` 下的条目没有 `AGENT_HANDOFF.md`，之前会打印
  一个指向不存在文件的提示；现在这类条目改为指向 `SKILL.md`。
- **补 OKF/级联登记**: `CONCEPTS.md` 加「意图路由 (intent_router)」词表；
  `docs/solutions/tooling-decisions/typesafe-jev-intent-router.md` 记录决策与实测坑。
- **补充实测**: catalog 从 34 涨到 35 项后**重跑了 live 标注样例**（输入变了就该重测，
  不能沿用旧结论）—— 仍 10/10，`confidence` 0.97–1.00、`ambiguity` 0.86–0.95，
  两条结论不变。**注**：`confidence` 早先在本模块自己的 33 项目录上确为「恒 1.00」，
  加到 35 项后变成 0.97–1.00 —— 措辞已按最新实测改准，但「阈值 0.5 永不触发」的结论不变。
- **补齐目录（同日后续）**: catalog 35 → 56 项 —— 补入 11 个此前漏掉的 skill 目录
  （dingtalk-robot / item-group-translation / tongtool-api / tongtool-warehouse-sync /
  erpnext-item-create / ecommerce-image-workflow / okf / design-md / design-review /
  frontend-design / workbuddy-config）与 10 个此前漏掉的业务模块目录
  （advertise / ai-access-poc / amazon-pairing / cost-adjust / google-drive-permissions /
  nas-product-visuals / pb-reconciliation / sellfox-api-proxy / sps-api / ups-track）。
  **模块表因此从"策展子集"变成接近全量**（原先 18 个顶层模块目录里有 16 个不在表内）。
  标注样例同步扩到 31 条（每个新模块一条），56 选项下重测 **33/33 全中、无回归** ——
  这是对"选项变多会互相干扰"（原计划风险 #3）的正面回答。
  **数字更新**：`confidence` 0.98–1.00、`ambiguity` 0.66–0.98、约 9815 输入 token ≈ $0.00041/次。
  **未纳入并说明理由**：`test_upload`（0 个 py，已废弃）、`EN_shopify`（无任何文档）、
  `SPS_Selenium_Local`（仅 README、零引用）、`pdf_to_md`（有文档但 3 个月未动）；
  另有 3 个是**假缺口**（`missing_products` / `tongtool_api` / `web_automation` 已被表中同名行代表，
  只是目录名用了 `_` 而表里用 `-`）。**`dingtalk` 也刻意未单独建行** ——
  `dingtalk/dingtalk_robot/` 就是 `dingtalk-robot` skill 的实现，单列会造出两个都像
  「发钉钉消息」的选项，正是最容易让模型选错的形态。
- **计数改为不带数字**: README / SKILL.md / catalog 里原先写死的"33 个模块""30 多个模块"
  随每次补录立刻过期；按 `docs/solutions/log.md` 的教训改成不带数字的表述，只在这一处
  保留带日期的实测记录。
