---
okf: v0.1
type: Reference
title: 浅克隆 worktree 下 update_index.py 会把所有文档日期刷成同一值
date: 2026-11-17
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: low
applies_when:
  - "在 worktree / CI 的浅克隆里跑 scripts/update_index.py"
  - "根 index.md 出现几百行与本次改动无关的日期变更"
tags: [git, shallow-clone, worktree, update-index, tooling]
related_components: [tooling]
---

# 浅克隆 worktree 下 update_index.py 会把所有文档日期刷成同一值

## Context

`scripts/update_index.py` 的「Updated」列优先取 **git 最后提交日期**，未跟踪文件才回落 mtime
（脚本注释里写明了：mtime 在新 clone 上是检出时间，不可靠）。

但**浅克隆**（`git clone --depth 1` 或某些工具生成的 worktree）里，`git log` 对任何文件都只能看到
**同一个最新提交**。于是：

```
$ git rev-list --count HEAD
1
$ git log -1 --format=%ad --date=short -- EN_API/docs/index.md
2026-11-06          # 全仓库文件都是这一天
```

此时重生成 `index.md`，会给**几百个文件**的 Updated 列统一改成那一个日期 —— 与本次改动毫无关系。

> 实测：本仓库的某个 worktree 创建时就是 `rev-list --count` = 1，重生成产生了 1183 行 diff；
> 之后历史被补齐（`rev-list` 变回 1350）、再跑就只差 25 行。所以**每次跑之前都要现测**，不要凭印象。

## Guidance

1. 跑之前先判断是否浅克隆：

```bash
git rev-list --count HEAD     # 1 = 浅克隆
```

2. 若是浅克隆，**不要把整份重生成结果提交**：
   - 撤回自动生成：`git checkout -- index.md`
   - 只手工补本次该变的行（模块计数、新文档那一行、`generated`/`Last updated` 时间戳）
   - 或者改到**完整克隆**的主仓库里重跑脚本，再把结果带过来。
3. 提交时在 PR 描述里注明"根索引为最小手改，完整重生成请在全量克隆执行"。

## Why This Matters

一次无关的 1000+ 行 diff 会淹没真实改动、增加评审成本，还让 `git blame` 失真。
这类噪音一旦进 main，后续每次 review 都要重新辨别。

## When to Apply

- 在 worktree / 临时检出里改 OKF 文档并跑索引脚本时。
- 看到 `git diff index.md` 行数远大于实际改动时。

## Related

- [scripts/update_index.py](../../../scripts/update_index.py)
- [AGENTS.md](../../../AGENTS.md) —— 第 11 条（索引联动更新）
