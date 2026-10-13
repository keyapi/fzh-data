---
type: Plan
title: 工单驱动渠道接入助手 · 续接实施计划
date: 2026-10-13
status: plan-not-implementation-evidence
---

# 工单驱动渠道接入助手 · 续接实施计划

本文件续接 [竞赛升级设计合同](competition-v2-design.md)（下称「设计」）之后**尚未完成的接线、契约与验收实现**。
**它只是计划，不代表任何阶段已完成或测试通过。**

## 背景与现状

- 设计合同已冻结主线：用户只给工单 → Agent 读工单 + 版本化知识 + 当前状态 → 发现旧模板冲突/重复创建风险/缺失信息 → 跨三页组成整组方案 → 只追问不可推断的问题 → 一次确认 → 后台原子执行 + 独立读回 + 模拟验收 + 失败恢复。模型只有 读/检索/追问/准备 四类工具，**没有执行工具**。
- 上一轮实现留下了 4 个改动文件与 7 个新增文件（`server.py` 未接线即中断）。这些文件已由「阶段 0」存档提交，消除「未提交即可丢」的风险。
- **首要阻塞**：`server.py` 完全没有 `/api/bank/tasks/*` 端点，前端 `bank_task_ui.js`（`index.html:1116` 已引入）因此是坏链；`/competition.html` 也未放行。
- **静默误路由**：`server.py:463` 按 `scenario.startswith('bank_')` 选执行器，`bank_task` 提案会被误交给 `BankOperations`（`:467` 的 cancel 同理走 `STORE.cancel`）。
- **契约缺陷**：`catalog` 不给工单正文；`answer` 后 `questions` 不清理（且 agent 依据从不写入的 `answered` 过滤 → 重复追问）；模型回复缺 `model` 字段。
- **验收缺陷**：`verify`（`bank_tasks.py:518`）只有两项粗检（整库哈希比对 + fixture 布尔标志），设计 §8 要求的逐项模拟验收基本未实现。

## 协作方式：跨工具接力

本工作可能在 **Codex / Claude / 其他工具**之间交替推进，因此：

- **按阶段提交**：每个阶段末尾一次提交 + 更新交接，**任何时刻工作区不留大块未提交改动**。
- **计划以本文件为准**，不靠任何对话历史传递。
- Codex 走自身额度、**不经过公司网关**；Claude 侧经公司网关，存在被 `sensitive_words_detected` 拦截的风险 → 大块实现优先 Codex，接线/验收/浏览器验证可由 Claude 承担。
- 走分支 → 提交 → PR，不直接推 `main`。

## 阶段计划

### 阶段 0 · 存档点
把上一轮的 4 改 7 增提交到 `feature/competition-controlled-agent` 并 push；本计划文档与交接同步落盘。
**闸门**：`git status` 干净，PR 上可见该提交。

### 阶段 ① · 服务端接线：001 主线端到端
- `server.py:353` 静态白名单元组加 `/bank_task_ui.js`；`/competition.html` 仿 `:350` 新增分支（**文件缺失要 404 不要 500**）。
- `do_GET` 新增 `/api/bank/tasks/catalog`、`/state?task_id=`、`/download?id=`；`download` 用 `_send(200, content.encode('utf-8'), 'text/plain; charset=utf-8')`（`_send` 已支持 bytes），如需文件名给 `_send` 加**可选** headers 参数，不改既有调用。
- `do_POST` 新增 `/api/bank/tasks/chat`（复用 `MODEL_SLOTS`、`model_call`、`run_task_agent`，并照 `:446` 补 `result['model']=MODEL`）及 `/start`、`/answer`、`/verify`、`/recover`；一律置于 `_session()` 与 `rate_limit()` 之后。
- **修正误路由**：`:463` 按 `scenario=='bank_task'` 分流到 `BankTasks.execute`，否则 `startswith('bank_')`→`BankOperations`，再否则 `STORE`；`:467` cancel 同理走 `BankTasks.cancel`。
- 复用（勿重写）：`_session`、`rate_limit`、`MODEL_SLOTS`、`model_call`、`_snapshot`、`redact_all`、`_send`、`_error`、`CONFIG`。
- **测试先行**：照 `tests/test_bank_http.py` 范式新增 `tests/test_bank_task_http.py`，用脚本化 stub model 驱动 start→chat(prepare)→execute→verify，不依赖真机。
- **闸门**：`uv run python -m unittest discover -s tests -v` 全绿；脚本化 001 全链终态 `completed`、execute 已提交、catalog 200、chat 含 `model`、cancel 命中 `BankTasks.cancel`。

### 阶段 ② · 前后端契约修复
- `catalog` 加工单正文（对齐 `bank_task_ui.js:50` 读的 `text/body/content/request_text`）。
- 答题后从 `task['questions']` 移除该问、归档副本置 `answered=True`，消除重复追问。
- chat 分支补 `result['model']=MODEL`。
- **闸门**：catalog 含 `text`、answer 后无 pending question、chat 含 `model`；浏览器模型行显示、缺项只问一次。

### 阶段 ③ · verify 模拟验收矩阵
001 必需项：三页逐记录读回（含 `record_id`）；终端代码唯一 + 租户一致性显式断言；地址与回调契约（HTTPS/HMAC-SHA256/异步/端口、响应码、原因，全模拟）；**范围未扩大**（apply 路径也取 `before_bank` 比对）；review 报告补 `simulation/source/fixture_version/summary`；执行记录补 `id/version_before/version_after/committed_at`；读回版本被推进改用 `READBACK_STALE`。
**闸门**：001 通过时各检查项均 passed 且含 `record_id`；读回被推进场景返回 `READBACK_STALE`。

### 阶段 ④ · 002 固定值 + 003 失败恢复
002（conservative 档 `8443`）走通 `completed`；003（回调被拒）verify 失败 → 逐项报告 → recover → execute → verify → `recovered`；**recover 幂等**（重复恢复返回既有结果，不产生第二次写）。
**闸门**：三工单全链绿。

### 阶段 ⑤ · 真机评测 + 浏览器 + 演示材料
三工单真机各跑通、无 500、无「假成功」文案；浏览器彩排；产出 6–8 分钟演示脚本、项目说明、答疑材料、可投屏展示页、测试记录、失败备用方案。

## 可延后，但绝不能伪装成「已完成」

- **幂等重复请求账本**、**超时重试时间线**（`bank_tasks.py` 的 profile 有值未用）、**003 逐项失败明细**、**独立敏感占位校验项**：可延后实现，但报告必须显式列「未实现」，**不得用静态字段检查冒充运行验证**。
- `analyzing/executing/execution_failed` 未持久化：设计允许前两者不持久，UI 仅瞬时展示，**不得声称后端状态机已落库**。
- 三页读回若短期仍是整库哈希，必须标注「整库哈希」，不得写「逐记录」。

## 验证

- 单测：`uv run python -m unittest discover -s tests -v`
- 起服务：`uv run python server.py`（默认 `127.0.0.1:8765`），浏览器打开「接入工单」页
- 真机需 `.env` 配 `OPENAI_API_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`

## 风险

- **网关敏感词 500 可能复发**（Claude 侧）：批量读文件走子代理；改代码前先把目标文件读进上下文。
- **`domain.py` 的 digest 改动**：排除集由固定黑名单变为**无界**（任意 `_` 前缀字段），且被 domain/bank_ops/bank_tasks 共用 → 建议改回显式白名单（仅排除执行期私有字段），改则重跑全部 execute 用例。
- **静态白名单**：只放行两个新增文件，保持 `.env`/`server.py`/`.git`/`*.sqlite3` 仍 404。
- 凭证不入库；不重写架构、不引新框架/依赖。
