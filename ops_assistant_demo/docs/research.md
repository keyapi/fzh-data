---
type: Research
title: 竞赛设计依据与公开案例
date: 2026-10-12
---

# 竞赛设计依据与公开案例

以下为公开来源，调研日期2026年10月12日。领导评委的偏好是设计推断，不是已取得的评分标准；没有承诺获奖。厂商案例的收益不作为本POC的效果指标。

| 来源 | 能支持什么 | 演示选择 |
|---|---|---|
| [中国银行2026年中期业绩实录](https://www.boc.cn/aboutboc/bi1/202608/t20260829_25688702.html) | 银行讨论AI业务赋能与治理方向 | 尊重知识问答价值，把办理闭环作为进一步能力 |
| [Yonder / Gradient Labs](https://gradient-labs.ai/customers/yonder) | 公开案例介绍Agent整理争议证据和案件，关键决定保留给人 | 减少查资料、整理和重复填写，人保留批准权 |
| [Bradesco / Microsoft](https://www.microsoft.com/en/customers/story/25660-banco-bradesco-sa-azure-ai-foundry/) | 厂商介绍银行AI应用与平台治理 | 能力和控制同时呈现，不单独秀框架 |
| [OWASP Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) | 过大功能、权限和自主性会扩大风险；下游授权与最小权限是控制方向 | 固定业务动作、权限在模型之外检查 |
| [Frappe REST API](https://docs.frappe.io/framework/user/en/api/rest) | API认证关联用户并检查角色权限 | 每次请求继承可信身份，而非模型自报角色 |
| [Frappe Permissions in Code](https://docs.frappe.io/framework-git/server-side/permissions-in-code) | 自定义代码需要明确权限检查 | 不能笼统说“接MCP就自动安全” |

## 推断与取舍

复杂性应来自完整业务链：资料筛选、当前状态、多个相关参数、确认、验证、申请和异常恢复；不用制造大量无意义点击。五分钟主线集中联调异常处理，柜面作答疑展示控制层可以复用。

page-agent可适配页面控件，但关键动作更适合结构化工具以限制范围、审计和核验。发现新字段不是本次主目标，暂不进入默认演示。

有效操作范围＝用户权限∩工具能力∩本次授权范围∩当前业务条件。目标是证明错误动作无法突破演示中实现的边界；不声称完全防止所有攻击或获得监管认证。


## Harness选型补查

2026-10-12核对原始文档：[Pi agent-core](https://github.com/earendil-works/pi/blob/main/packages/agent/README.md)独立提供状态、工具执行与事件流，包含transformContext、prepareRequest、beforeToolCall、finishTurn；不能笼统说Pi对POC必然太重。本轮借鉴按轮更新真实状态、上下文筛选、工具前校验、基于工具结果结束/纠偏的机制，没有引入Pi依赖，也未完整对照评测。

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)基于Cordis插件架构，官方仍标记开发预览与兼容性变化；整套替换需要额外集成验证，模块化思想可借鉴。这是本项目取舍，不是其性能不好或模型能力弱的证明。现有Python执行层继续负责业务权限和事务，框架本身不能取代它。
