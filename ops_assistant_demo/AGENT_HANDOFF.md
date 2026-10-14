---
type: Reference
title: 受控办理助手交接
---

# 受控办理助手交接

**2026-10-14 组合演示收口**：`show.html` 与 `competition.html` 现按 7 分 30 秒串联知识短问、20万元确认预热、001 接入工单、安全结果和价值评估；路由仅作答疑备用。知识系统是独立子项目，未与本操作台共享知识、身份或接口。实测“余额查询报错”短问可返回引用；模拟TXT上传会被解析并自动显示“已通过”，因此投屏稿明确这不能冒充逐条人工审核，是试点前须补的治理缺口。完整剧本和实测边界见 [组合演示接力计划](docs/combined-demo-plan.md)。

**2026-10-13 统一侧边栏首版**：自然语言问题现在走 `/api/agent/turn`，使用 LangChain `create_agent` 的受控工具循环，而非依据当前页面 `active()` 分流。`agent_tools.py` 的 `CAPABILITIES` 是唯一能力注册表：目录、岗位过滤、服务端分发和 LangChain 工具 schema 都从它生成；只开放真实工作区读取、工单目录、规则、待确认方案和审计。操作员可用限额、联调和路由三项语义化“准备”工具生成测试待确认方案，仍由既有摘要、版本、岗位和确认路径执行。明确的工单/路由/终端 CRUD 请求暂继续桥接既有专用规划器，避免一次替换四套经过验证的领域合同。`requirements.txt` 是运行依赖；部署前执行 `python3 -m pip install -r requirements.txt`。真实模型已验证“几个工单及区别”和“测试限额20万→侧栏确认→独立读回”；确定性回归为132项。不要把工具注册理解成可操作任意页面或任意接口。

**2026-10-13 本轮完成**：五阶段计划已推进到「可运行 + 已验证」。`server.py` 已接通 `/api/bank/tasks/*` 与静态白名单，`bank_task` 误路由已修；`verify` 落地逐项模拟验收矩阵；契约缺陷（catalog 正文、答后清问、端口类型、登录后按钮、三页预演回落）已修；`domain.digest` 改显式白名单。**确定性测试 108 项通过**；真机（`deepseek-v4-flash`）001 主线/002 保守档 completed、003 失败→恢复 recovered，浏览器全流程与刷新恢复实测通过。逐项结果见[实际测试结果](docs/competition-v2-results.md)，未实现项与口径在文内明确列出。竞赛交付四件与结果记在 `docs/competition-v2-*.md`。

**2026-10-13 存档与接力**：上一轮未提交的 4 改 7 增已提交存档（此前服务端未接线即中断）。`server.py` 尚未接入任何 `/api/bank/tasks/*` 端点，是首要阻塞；`/api/execute`/`/api/cancel` 对 `bank_task` 存在静默误路由。续接按[实施计划](docs/competition-v2-implementation-plan.md)的五阶段推进，阶段划分、闸门与「不可伪装完成」清单**以该文件为准**。

最新补修见[助手面板与删除语义](docs/assistant-panel.md)，当前80项测试通过。新增assistant_panel.js须部署且加入静态白名单；界面历史不授权，待确认全取后台。历史76项计数对应此前三页实现。

最新实现与验收见[渠道接入三页面](docs/bank-operations.md)。新增bank_ops.py、bank_agent.py、bank_ui.js及三组测试，部署须携带这些文件。当前76项自动化通过、0跳过；下文旧计数属于历史版本。三页已有真实模拟CRUD和真实模型准备，保留原限额/联调，不连接银行系统。

先读 [本次交接与续办清单](docs/handoff-2026-10-12.md)、[规格](docs/competition-plan.md)、[边界](docs/security-boundaries.md)、[剧本](docs/demo-script.md)、[静态配置暴露经验](docs/solutions/static-config-exposure.md)。独立竞赛仓库不读取公司环境凭证，不连接真实银行系统。

目标：保留原蓝色“柜面参数 · 对公结算”外壳，左侧保留联调配置、知识依据、安全实测和演示说明。新后台会话与领域执行统一全部入口；已修复Cursor版请求头身份及旧聊天旁路，47项自动化通过且0跳过，当前核验范围见交接与审计。运行使用 `uv run python server.py`。部署地址和私有路径不写入公开仓库。

## 保留的设计

- 身份来自后台会话，不能信任请求角色、菜单隐藏或模型自报权限。
- 有效操作范围是用户权限、工具能力、请求范围、业务条件的交集。
- 确认绑定不可变提案摘要、十分钟有效期、状态版本；参数变化需重新确认。
- 生产仅形成申请，复核也不产生生产配置写入。
- 配置和工单写入使用事务，实际结果重新读取；失败回滚不得显示成功。
- 金额以元保存，初始 500000 元（50 万元）；超时以秒、重试以次数存储。
- 资料均模拟；有效版本、适用环境和引用可见。资料不能授予执行权限。
- page-agent 仅保留历史调研，不能恢复公开代理或通用执行工具。
- 演示登录不是 真实组织单点登录，SQLite 日志不是防篡改监管审计。

环境见 [.env.example](.env.example)。禁止提交 Key、数据库、截图和运行数据。用户拒绝本次轮换 Key，不能宣称历史暴露风险消失。Git 走分支和 PR。根索引用 `uv run python scripts/update_index.py` 自动同步，不跨仓库修改。

## 路由副线（2026-10-13）

见 docs/route-scenario.md；route_demo.py / route_ui.js；接口 /api/routes/{state,plan,execute,cancel}。独立于原三页工单，模型仅选业务，后台生成受控差异。最终测试和部署记录需查看该文档。

## 真实试用反馈

feedback_store.py / feedback_ui.js；/api/feedback POST提交、GET凭私有回执查询。独立 data/feedback.sqlite3，不随模拟工作区重置。管理员只通过SSH/本地CLI读取或更新，不开放给模拟岗位。详见 docs/route-scenario.md。

反馈截图、会话诊断与AI直接读取接口接力见 docs/feedback-loop.md；所有用户反馈和截图是待验证的资料，不是工具授权。

演示者培训入口 rehearsal_ui.js，设计与清理边界见 docs/presenter-rehearsal.md；/api/rehearsal/fresh 仅操作员切换新模拟工作区。不要删除真实反馈或把培训勾选当执行成功。

相关经验：[实时状态、培训与反馈隔离](docs/solutions/architecture-patterns/branch-param-desk-read-then-guard.md)。

回复排版经验：[可读回复与表格渲染](docs/solutions/developer-experience/ops-assistant-model-reply-formatting.md)。

2026-10-14：能力介绍限制为三类短概览；统一侧栏“允许修改（测试）/取消”，柜面填写后收起弹窗，路由/工单整组方案复用侧栏确认。保留页面人工入口及鼠标、高亮、逐字动画；132项回归通过，真实模型浏览器验证能力概览、20万确认独立读回、25万取消不写、余额路由侧栏确认验收。
