---
type: Reference
title: 受控办理助手交接
---

# 受控办理助手交接

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
- 演示登录不是 BOC SSO，SQLite 日志不是防篡改监管审计。

环境见 [.env.example](.env.example)。禁止提交 Key、数据库、截图和运行数据。用户拒绝本次轮换 Key，不能宣称历史暴露风险消失。Git 走分支和 PR。根索引用 `uv run python scripts/update_index.py` 自动同步，不跨仓库修改。

## 路由副线（2026-10-13）

见 docs/route-scenario.md；route_demo.py / route_ui.js；接口 /api/routes/{state,plan,execute,cancel}。独立于原三页工单，模型仅选业务，后台生成受控差异。最终测试和部署记录需查看该文档。
