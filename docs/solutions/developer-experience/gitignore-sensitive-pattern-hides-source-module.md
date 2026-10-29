---
okf: v0.1
type: Reference
title: .gitignore 的 *token* 会静默漏掉源码与测试——提交后干净 clone 启动失败
date: 2026-10-28
category: developer-experience
module: wayfair-api-proxy
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - "新增源码/测试文件名包含 token、secret、credential 等敏感词"
  - "本地测试通过、部署也正常，但干净 clone 或 CI 导入失败"
tags: [gitignore, git, code-review, imports, ci]
---

# .gitignore 的 `*token*` 会静默漏掉源码与测试

## Context

仓库根 `.gitignore` 有一条 `*token*`，本意是挡凭证文件。新增模块里有一个正常源码
`token_cache.py` 和对应测试 `tests/test_token_cache.py`，名字命中规则，`git status`
根本不显示它们。

## Guidance

- `git add` 只加“看得见的文件”，被 ignore 的源码/测试不会进入暂存区；
- 本地 `pytest` 用工作区文件，当然全绿；tar 部署也把工作区文件带上了，线上也正常；
- 但干净 clone / CI 只有提交内容，`from token_cache import TokenCache` 直接
  `ModuleNotFoundError`，服务启动失败。
- 这类问题不会被测试数量、部署成功或“我本地能跑”发现。

### 检查方法

```bash
git check-ignore -v path/to/file.py          # 命中哪条规则
git ls-files path/to/module | sort           # 真正入库的文件
git status --short --untracked-files=all     # 被 ignore 的不会出现
```

新增模块后至少做一次 **clean-tree import smoke**：

```bash
git archive HEAD | tar -x -C /tmp/verify
cd /tmp/verify/wayfair-api-proxy && python -c "import main"
```

### 处理方式

1. 优先**改名**避开敏感词（例如 `token_cache.py` → `oauth_cache.py`），
   测试同步改名；不要长期依赖 `git add -f`。
2. 确需保留原名时，`git add -f` 后立即用 `git ls-files` 确认；
   后续改动用 `git status` 可能仍看不到，风险持续存在。
3. Code review / 发布清单加一条：新增目录必须 `git ls-files` 对照业务文件清单。

## Why This Matters

被 ignore 的不是垃圾文件，而是运行必需的模块；失败发生在最晚、最贵的环节
（干净部署/CI），而本地与增量部署都不会暴露。一次 Codex 复审靠
`CLEAN_IMPORT: ModuleNotFoundError` 才抓到。

## When to Apply

- 新建 Python 模块、测试、配置文件时；
- 仓库有 `*token*` / `*secret*` / `*credential*` 一类宽泛 ignore 规则时；
- 发布前做干净树验证时。

## Examples

错误命名与修复：

```text
wayfair-api-proxy/token_cache.py        # 被 *token* 忽略
wayfair-api-proxy/oauth_cache.py        # 改名后入库
```

## Related

- `AGENTS.md` 第 9 条（凭证扫描）
- `wayfair-api-proxy/docs/operations.md`（发布验收）
