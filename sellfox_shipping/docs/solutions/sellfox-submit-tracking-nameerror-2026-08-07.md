---
okf: v0.1
type: Solution
title: 回写赛狐 NameError — Web 端点误用 cli.py 私有函数
description: 包裹详情"回写面单追踪号到赛狐"端点调用只存在于 cli.py 的 _get_client 导致 NameError；提取共享 get_sellfox_client 工厂修复
timestamp: 2026-08-07
tags: [sellfox-shipping, sellfox-client, submitToPlatform, nameerror]
---

# 回写赛狐 NameError — Web 端点误用 cli.py 私有函数

## 现象

包裹 P2B9A9T734516 点击「回写面单追踪号到赛狐」提示 `回写赛狐失败: name '_get_client' is not defined`。

## 根因

Web 端点 `POST /packages/{sn}/submit-label-tracking`（app.py）构造
`SubmissionService(repo, _get_client())`，但 `_get_client()` 只定义在 `cli.py`，
`app.py` 模块作用域不存在 → 调用时抛 `NameError`，被端点 except 捕获成失败消息。

**潜伏原因**：测试 `test_submit_label_tracking.py` 只覆盖 service 层（用 mock client），
从未通过 FastAPI TestClient 触发该 Web 端点 → NameError 一直未被发现。CLI 路径正常
（cli.py 有 `_get_client`），所以此前从未暴露。

## 修复

把 cli.py 里"智能客户端工厂"逻辑（`SELLFOX_APP_ID`/`SELLFOX_APP_SECRET` 有则直连
官方 OpenAPI，否则走共享代理）提取为共享函数 `get_sellfox_client()`，放回
`sellfox_client.py`（客户端类同模块）：

- `app.py` 端点改用 `get_sellfox_client()`（从 `sellfox_client` import）
- `cli.py._get_client()` 改为 `return get_sellfox_client()`（去重，行为不变）

`direct_sellfox_client` 在函数内**延迟 import**，避免循环依赖（direct 模块内部也
延迟 import sellfox_client 的 parse 函数）。

## 教训

1. **跨模块复用函数要提取共享位置**：CLI 私有的 `_get_client` 被 Web 端点引用，属于
   "未定义引用"隐患。客户端工厂这类被多个入口复用的逻辑，应放在客户端模块本身。
2. **Web 端点要有端到端测试**：service 层测试通过不代表端点可用。端点测试至少要用
   TestClient + mock 客户端打一遍，能捕获这类 `NameError` 级别的接线错误。

## 验证

- 新增 `test_sellfox_client_factory.py`（直连/代理两种 env 分支）；全量 283 passed。
- TestClient mock 客户端 POST `/packages/P2B9A9T734516/submit-label-tracking`：
  HTTP 200，成功消息渲染，无 NameError。（真实 submitToPlatform 属副作用调用，需用户确认后点击。）
