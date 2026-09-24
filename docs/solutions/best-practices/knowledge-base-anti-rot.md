---
okf: v0.1
type: Reference
title: 知识库防腐三件套 — 孤儿检测 / 生成式索引 / 链接图
date: 2026-09-24
category: best-practices
module: docs_solutions
problem_type: best_practice
component: documentation
severity: high
applies_when:
  - "docs/solutions 越积越多，不确定某篇还能不能被找到"
  - "收尾时想确认索引/平表/链接是否还和磁盘一致"
  - "犹豫该新写一篇还是更新既有的那篇"
tags: [knowledge-base, orphan-detection, generated-index, link-graph, docs-solutions]
---

# 知识库防腐三件套 — 孤儿检测 / 生成式索引 / 链接图

## Context

`docs/solutions/` 到 2026-09 已积到 106 篇。AGENTS.md 里那句「已解决问题记录，可按 module/tags 搜索」
是**劝告**，而劝告不管用 —— Vercel 用 19 道 Next.js 16 新 API 的题做过对照：

| 方案 | 通过率 |
|---|---|
| 不给任何文档（基线） | 53% |
| 做成 skill 按需拉文档 | **53%（+0）** —— **56% 的评测里 skill 根本没被调用** |
| skill + 明确指令「你必须调用」 | 79% |
| **压缩目录直接放进常驻的 AGENTS.md** | **100%** |

三条归因：没有「要不要查」这个决策点、每轮都在、无先后顺序问题。
结论：**让 Agent 自己决定要不要查 = 一半概率不查**。所以要么把目录放进常驻上下文，要么用机械校验兜住。

## Guidance

三件套对应三种「文档会怎么烂」，缺一不可：

1. **孤儿检测**（防「再也找不到」）
   建反向引用图：一篇 solutions 文档如果没有任何 skill / 模块文档 / AGENTS.md / CONCEPTS.md 指过来，
   它就是孤儿。入链判定要**排除 docs/solutions 自身的互链与自动 log/index** —— 否则「从一篇孤儿链过去」
   会让两篇都算可达，而读者两个都进不去。
2. **生成式索引**（防「索引与磁盘漂移」）
   根平表由 frontmatter（`date` / `title`）生成，**不要手工维护**。实测手工维护的平表已漂 **30 篇**——
   AGENTS.md 里说的「全量平表」当时是假的。category 的 `index.md` 保留人工（它带「什么时候读」的策展描述），
   但校验必须机械。
3. **链接图**（防「指向不存在的文件」）
   文档里的相对链接必须能解析。实测抓到 **13 处断链**，病因高度一致：
   `docs/solutions/<category>/` 下要退 **3 级**才是仓库根，而被写成了 2 级。

外加一条**处置规则**（这是关键，否则检查只是抱怨）：
> 每篇孤儿只有两个合法归宿 —— **route**（挂到相关 skill / 模块文档，**只写路径、不复制内容**）
> 或 **explicit exclude**（写进 `docs/solutions/exclusions.txt` 并给出原因）。**静默忽略不是选项。**

**最后：工具不会自己跑。** 仓库没有 CI，所以要把体检挂进既有流程（本仓库挂在 `ce-okf` 收尾第 5b 步），
否则它和那句劝告一样依赖「有人记得做」。

## Why This Matters

- **不对称的发现成本**：一篇找不到的文档 = 下一个人重新踩一遍坑；而校验是秒级的。
- **漂移是静默的**：索引少了 30 篇、链接断了 13 处，没有任何东西会报错，直到有人真的去点。
- **route 与 fork 的边界**：agent 文件应当**指向**权威文档，绝不复制其内容——
  「agent-only 文件没人审计」会让两份副本静默分叉。挂一行路径是 route，把内容抄进 SKILL.md 是 fork。
  同理，**不要把一手知识只留在未合并分支上**：本次就发现一整套 PB 活动价记录（含补佣金口径）
  因为 PR 被 revert 而停在 `feature/*` 分支，main 上 grep 不到 —— 等于不存在。

## When to Apply

- 任何以「一堆 Markdown 经验文档」为知识库的仓库，尤其多 Agent（Claude / Codex / Cursor）共用时。
- 收尾/提交前，以及新增或移动文档之后。
- 判断「该新写一篇还是更新既有文档」时：先查重复度，同题同解就别再写第二篇。

## Examples

```bash
uv run python scripts/check_solutions_health.py            # 体检：孤儿 / 索引漂移 / 断链 / 篇数
uv run python scripts/check_solutions_health.py --fix      # 重建根平表后再体检
uv run python scripts/check_solutions_health.py --strict   # CI 口径：孤儿也算失败
```

2026-09-24 首次体检的实测产出（全部已修）：

| 发现 | 数量 |
|---|---|
| 根平表漏收文档（手工维护漂了） | 30 |
| category index 漏收 / 缺 index.md | 9 + 1 目录 |
| 相对链接解析不到 | 13 |
| 正文游离在 `docs/solutions/` 根下（旧 schema） | 2 |
| 无任何 skill / 模块文档指向的孤儿 | 35 → triage 后 26 挂靠 + 6 显式豁免 = 0 |

外部参照（同类做法，可借鉴）：`lint-orphan-documents.py`（反向引用图）、docguard 的 `reachability`
与 `generated-index` 规则、docgarden、Grafana `maintain-docs` 里「Orphaned doc needs indexing」的
二选一处置（该索引就加索引，不该就进 Exclusions）。

## Related

- [扫描类脚本防「静默丢数」](scanner-silent-data-loss-guard.md) —— 同一思想在数据管道上的版本：
  宁可报错停机，也不静默少给
- [PB 对账表月度更新](../workflow-issues/pb-reconciliation-monthly-update.md)
- `.agents/skills/ce-okf/SKILL.md` 第 5b 步 —— 本体检的实际挂载点
