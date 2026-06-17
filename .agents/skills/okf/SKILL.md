---
name: okf
description: Open Knowledge Format — 任何新子项目或模块的文档必须按 OKF v0.1 规范创建和维护
trigger: 当新建子项目、新建文件夹、新建文档、修改 Markdown 文档、用户提到 OKF、用户要求写文档时触发
---

# OKF — Open Knowledge Format 文档规范

> OKF v0.1: Google 2026.6.12 | Spec: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

## 铁律

1. **每个 .md 文件 YAML frontmatter** — type 唯一必填
2. **每个目录 index.md** — 枚举内容 + 导航
3. **每个 bundle log.md** — 按日期倒序变更历史

## OKF Bundle 骨架

```
<module>/docs/
├── index.md          # type: Index
├── log.md            # type: Log
├── reference/        # type: Reference
├── research/         # type: Research
├── specs/            # type: Spec
└── lessons/          # type: Lesson
```

## Frontmatter

```yaml
---
okf: v0.1
type: Reference    # 唯一必填: Index|Reference|Research|Spec|Lesson|Log
title: 标题
description: 描述
tags: [tag1, tag2]
---
```

## 执行规则

- 新建子项目 → 先建 docs/ → index.md + log.md
- 新增文档 → 加 frontmatter → 更新 log.md → 更新 index.md
- 修改文档 → 追加 log.md 条目

> 参考示例: advertise/docs/
