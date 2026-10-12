---
type: Handoff
title: 网点参数台演示
module: ops_assistant_demo
date: 2026-10-11
tags: [demo, guardrails, agent]
---

# 网点参数台演示

假的柜面参数页。浏览器里的助手调用 OpenAI 兼容网关，写操作等人点允许。

## 新对话必读

- [先查再决定，护栏看动作](../docs/solutions/architecture-patterns/branch-param-desk-read-then-guard.md)
- [助手回复不要原样显示 markdown](../docs/solutions/developer-experience/ops-assistant-model-reply-formatting.md)
- [给人看的运行说明](README.md)

## 运行

`python server.py`，默认 `127.0.0.1:8765`。密钥从本目录 `.env`，其次才是仓库里已有的 Open WebUI `.env`。不要把 Key 写进页面或文档。

同一页左侧还有联调配置、知识依据、安全实测、演示说明。这些写入走 `/api/ops/*` 和 `domain.py`：确认后才改测试配置，生产只形成申请。

## 不要再做的事

- 不要用整句关键词「生产」「导出」否掉同一句里合法的测试限额修改。
- 不要在用户没给金额时默认改成 20 万。
- 不要把 Pi 或 DeepSeek Harness 整包嵌进来。借的是「读工具结果交回模型」这一轮。网页里自己点控件用 page-agent，并在每步之前等人点允许。
- 允许按钮没被真实点通过之前，不要把页面助手放到对外演示。page-agent 遮罩会盖住侧边栏；刷新后未完成的允许按钮没有点击。
- 不要把模型回复原样塞进气泡。星号和竖线表要先转义再排版，并且要看侧边栏，不要只核对接口字符串。
