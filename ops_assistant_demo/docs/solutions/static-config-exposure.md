---
okf: v0.1
type: Reference
title: 独立演示静态目录不能包含可访问的运行配置
date: 2026-10-12
category: integration-issues
module: ops_assistant_demo
problem_type: integration_issue
component: api-gateway
severity: critical
tags: [static-files, secrets, deployment, handoff]
---

# 独立演示静态目录不能包含可访问的运行配置

## Problem

旧服务将请求路径解析到运行目录，只检查路径是否在目录内与文件是否存在。这阻止不了读取该目录里的 `.env`、源码或后续数据库。Git忽略配置不代表HTTP不可访问。

## Symptoms

本次线上只检查状态和长度，配置路径返回HTTP 200。未打印、保存或提交真实配置内容。本地测试用合成配置文件重现200。

## What Didn't Work

`.gitignore`、密钥只放服务器、目录前缀检查，都不是静态资源授权。源码里没有密钥也不能排除运行配置暴露。

## Solution

`Handler.do_GET`改为明确静态白名单，目前安全补丁只允许首页。配置、源码及未知路径返回404；同时关闭未认证的通用 `/v1/chat/completions` 代理。后续页面若拆分脚本、样式，只添加确切资源名称，不能恢复整个目录可读。

## Why This Works

白名单将可公开文件限制在显式集合。回归测试先复现泄露，再验证配置、源码不可读，主页可用。封堵已经部署；Key按用户明确选择暂不轮换，历史暴露剩余风险并未被封堵撤销。

## Prevention

新后台尚未接入：旧 `/api/chat` 已暂停返回503，旧 `/api/change` 已禁用返回403。后续增加会话、同源检查、输入限制、调用预算与并发限制后才恢复模型入口。新UI及领域模块禁止直接部署，先完成HTTP集成和端到端验收。审计、知识库与权限宣称必须与实际后台行为一致。

## Related

- [交接入口](../../AGENT_HANDOFF.md)
- [继续开发清单](../handoff-2026-10-12.md)
- 回归测试：`tests/test_static_security.py`
