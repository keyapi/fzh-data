---
name: okf
description: Open Knowledge Format — 任何新子项目或模块的文档必须按 OKF v0.1 规范创建和维护。每次创建/修改文档后自动更新 index.md 和 log.md。
trigger: 当新建子项目、新建文件夹、新建文档、修改 Markdown 文档、用户提到 OKF、用户要求写文档、用户要求整理文档结构时触发。
---

# OKF — Open Knowledge Format 文档规范

> OKF v0.1 是 Google 2026.6.12 发布的开放知识格式规范。
> 完整 spec: <https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md>

## 铁律

**任何新子项目或模块必须遵守以下 3 条：**

1. **每个 `.md` 文件必须有 YAML frontmatter**，其中 `type` 是唯一必填字段
2. **每个目录必须有 `index.md`** — 枚举目录内容 + 导航
3. **每个 bundle 必须有 `log.md`** — 按日期倒序记录变更历史

## OKF Bundle 骨架

创建新子项目/模块时，必须先生成以下骨架：

```
<module>/
├── AGENT_HANDOFF.md           # Agent 入口 (项目约定, 非 OKF)
├── README.md                  # 人读 (项目约定, 非 OKF)
└── docs/                      # OKF v0.1 bundle
    ├── index.md               # 文档索引 (type: Index)
    ├── log.md                 # 变更历史 (type: Log)
    ├── road map.md            # 路线图 (type: Roadmap, 可选)
    ├── reference/             # type: Reference × N
    │   └── index.md
    ├── research/              # type: Research (可选)
    │   └── index.md
    ├── specs/                 # type: Spec (可选)
    │   └── index.md
    └── lessons/               # type: Lesson (可选)
        └── index.md
```

## Frontmatter 规范

```yaml
---
okf: v0.1               # 合规版本 (将来升级用)
type: Reference          # ★ 唯一必填: Index|Reference|Roadmap|Research|Spec|Lesson|Log
title: 文档标题          # 推荐
description: 一句话描述  # 推荐
tags: [tag1, tag2]       # 推荐
resource: path/to/code   # 可选: 关联的代码文件
timestamp: 2026-06-17    # 可选: ISO 8601 日期
---
```

### type 枚举

| type | 用途 | 示例 |
|------|------|------|
| `Index` | 目录导航文件 | `index.md` |
| `Reference` | 技术参考 (列名/API/配置) | `column-mappings.md` |
| `Roadmap` | 路线图/阶段计划 | `roadmap.md` |
| `Research` | 调研报告 | `2026-06-16-amazon-research.md` |
| `Spec` | 设计文档 | `2026-06-16-design.md` |
| `Lesson` | 经验教训 | `lessons-learned.md` |
| `Log` | 变更历史 | `log.md` |

## log.md 格式

```markdown
---
okf: v0.1
type: Log
title: 变更日志
---
# 变更日志

## 2026-06-17
- **变更描述**: 做了什么、为什么
```

## index.md 格式

```markdown
---
okf: v0.1
type: Index
title: 模块名 — 文档索引
---
# 文档索引

| 你需要... | 读这个 |
|----------|--------|
| ... | [file](path) |
```

## 执行规则

### 新建子项目时

1. 先创建 `docs/` 目录 + `index.md` + `log.md`
2. 根据需要创建 `reference/` / `research/` / `specs/` / `lessons/` 子目录
3. 每个目录加 `index.md`
4. 在 `log.md` 记录 "初始化 OKF bundle"

### 新增文档时

1. 加上 YAML frontmatter (`type` 必填)
2. 在 `log.md` 追加变更条目
3. 如果新增了文件，更新 `index.md` 的导航表

### 修改文档时

1. 在 `log.md` 追加变更条目
2. 如标题/描述变化，更新 frontmatter

> **不必过度设计**: OKF v0.1 只要求 `type` 字段。不要在不必要时加多余的 frontmatter 字段。索引文件保持简洁。

## 参考实现

项目中 `advertise/docs/` 是完整的 OKF v0.1 bundle 示例，可直接参考其结构。
