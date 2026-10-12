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


## 最后一轮Harness调研与下一轮实验（2026-10-12，尚未实现）

工作假设：保留deepseek-v4-flash，先评估运行时与工具设计，不把当前失败归咎于模型能力。以下机制有原始文档支持，具体选型是本项目推断。

- [Pi agent-core原始文档](https://github.com/earendil-works/pi/blob/main/packages/agent/README.md)：独立运行层提供prepareRequest、工具前后钩子、finishTurn及执行事件。建议做最小SDK原型对照，不需要搬整个编码助手，也不开放shell/文件系统工具。每次模型请求重新构建可信上下文，业务权限继续在当前Python执行层校验。尚未验证我们的网关与当前Pi版本兼容性。
- [Anthropic上下文工程](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：结构化笔记和压缩用于保存重要进展；提示应给足信息，避免堆砌硬编码分支。映射到本项目：任务对象保存目标、环境、来源轮次、当前阶段、待确认动作和完成证据；聊天历史、用户意图和后台实时状态分别管理。当前仅短历史加近期请求，未具备完整任务记忆。
- [Anthropic工具设计](https://www.anthropic.com/engineering/writing-tools-for-agents)：工具应职责清楚、结果提供相关业务信息，并以独立任务集检验工具选择和参数错误。我们应拆开准备测试变更、创建生产申请、审核申请，避免submit布尔值把申请强制绑定测试修改。成功话术由确定的执行结果生成，不能信模型自行总结。
- [DeepSeek Harness项目](https://github.com/deepseek-ai/deepseek-harness)：插件架构可作模块边界参考；本轮文档站未返回可读内容，Python目录读取失败，未验证嵌入式接入细节，不据此声称它太重或不适合。

代码证据：server.py每场景只保留短历史、六轮工具循环，并配置max_tokens=900和thinking disabled；domain.py资料按查询字符匹配排序，不是语义检索。这些是待评估因素，尚不能证明关闭思考或900token就是失败原因，不能直接把开思考当修复。界面动画目前主要在后台结果返回后播放，缺少实际工具事件实时驱动。

推荐顺序：先用同一Flash模型、相同业务工具与安全策略，比较当前运行时和最小Pi agent-core原型；保留至少12条独立多轮对话，包含生产70秒→提交申请、改口75秒、取消后重来、重置后继续、跨场景、仅申请不改测试、缺值澄清、复核岗提交拒绝、只读问答。测完整任务成功率、错误成功报告、额外追问数、错误工具调用、耗时和调用量，保存实际轨迹。当前46项测试主要证明具体回归和控制层，不代表自然对话能力已经评测通过。

再按失败轨迹调整任务状态与工具合同；最后才单独对照请求参数、知识检索与提示词。不要同时改框架、模型和提示词导致无法定位收益，也不要继续靠某条对话的特判宣称整体变聪明。所有实验、SDK接入、独立生产申请和结构化任务对象均留给下一轮，本轮只完成调研记录。


## Flash真实多轮小样本验证（2026-10-12，探索性，非完整评测）

固定当前模型、代码和工具，云端operator模拟账号通过接口测试两段三轮对话；只评估答复与动作准备，没有批准参数写入。每段前重置当前测试会话工作区。

| 输入 | 实际观察 | 判断 |
|---|---|---|
| 把测试联调超时改成70秒，生产不要动 | 准备测试timeout70，submit=false | 正确准备 |
| 那改成75秒 | 准备timeout75，未把70带回来 | 可承接改口 |
| 只提交生产变更申请，不要修改测试参数 | 仍准备timeout75测试修改，submit=true | 工具合同缺陷，违反本轮限制 |
| 测试联调超时现在是多少？ | 回答当前30秒/重试2次/版本 | 当前状态答复正确 |
| 把它改成80秒 | 准备timeout80 | 可承接指代 |
| 先不改了，请解释重试太多有什么风险 | 解释重试风险，无修改动作 | 能转回问答 |

最后一轮前由测试程序调用后台cancel，不代表已经验证模型理解并执行自然语言取消指令。观察不是统计结论，不能据此声称所有上下文问题已解决；未经独立隐藏集、任务执行后完整结果评估。

发现仅申请缺能力后增加最小拦截：这种请求明确报告CAPABILITY_UNAVAILABLE，不准备测试参数写入、不声称申请已完成。复核岗仍先得到权限拒绝。云端已验证proposal=null，新增回归后47项通过。没有新增独立生产申请工具；下一轮应拆开申请与测试修改，保持相同Flash做运行时/工具合同对照。这比只改模型回复更直接解释本次失败。
