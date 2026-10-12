---
okf: v0.1
type: Reference
title: 柜面助手回复要排成可读内容，不能把 markdown 原样塞进气泡
date: 2026-10-12
category: developer-experience
module: ops_assistant_demo
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "网点参数台或同类演示页把模型原文放进侧边栏"
  - "用接口返回的字符串核对过内容，但没看气泡里的换行和表格"
  - "模型把表格、星号和编号粘成一行"
tags:
  - ops-assistant
  - markdown
  - chat-ui
  - demo
---

# 柜面助手回复要排成可读内容，不能把 markdown 原样塞进气泡

## Context

联调助手的真实回复是一段粘在一起的 markdown：星号标题、竖线表格、编号说明。页面用转义后的纯文本放进侧边栏。浏览器把换行收成空格，星号和 `|---|` 原样出现。接口 JSON 里能读到「提案已生成」，所以只核对返回字符串会以为已经可演示。

## Guidance

先把原文转义，再排版。粘在一行里的竖线表要拆成表头和数据行；`**...**` 变成强调；`1. ` 变成列表。提示词里要求短句、不要表格，只能减少下一次这样写，不能代替排版。未知标签不要当 HTML 插入。

核对时看侧边栏：表头是「环境 / 字段 / 现值 / 目标值」，正文里不再出现 `**` 和 `|---|`。字段对比仍以页面上的提案卡片为准，气泡只负责把说明读清楚。

## Why This Matters

评委看到的是气泡，不是接口 JSON。一串星号和竖线会被当成没做完。只读 `innerText` 或响应正文，会漏掉「没有换行、没有表格」。

## When to Apply

模型回复进固定版式的业务页，而不是一个本来就渲染 markdown 的聊天产品。限额助手和联调助手共用同一个侧边栏时，两处都走同一套排版。

## Examples

粘成一行的回复：

```text
提案已生成，等待你确认。 **提案内容** | 环境 | 字段 | 现值 | 目标值 | |---|---|---|---| | 测试 | timeout | 30 秒 | 60 秒 | 1. **测试环境尚未写入**：等确认。
```

排版后应是一段说明、一张四列表、一条编号。`<script>` 这类字必须仍是文字。

## Related

- `docs/solutions/architecture-patterns/branch-param-desk-read-then-guard.md`
- `ops_assistant_demo/AGENT_HANDOFF.md`
