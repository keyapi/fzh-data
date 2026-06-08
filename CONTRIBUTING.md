# 贡献指南（技术开发）

> 你有 GitHub 权限，可以用 Claude Desktop Agent 开发新功能、修复问题、维护 Skill 和文档。

## 开发流程

```
main 分支 → 创建 feature 分支 → 开发 → 推 PR → 审批 → merge 回 main
```

### 1. 开始开发前

```bash
git checkout main
git pull
git checkout -b feature/xxx    # 或 fix/xxx
```

### 2. 在分支上开发

你的 Agent 可以自由提交：

```bash
git add <files>
git commit -m "feat(module): 做了什么"
git push -u origin feature/xxx
```

Commit 格式：中文 `type(scope): description`。类型用 `feat` / `fix` / `docs` / `refactor`。

### 3. 提交 PR

推到 GitHub 后，打开 https://github.com/keyapi/fzh-data/pulls 创建 PR。

- PR 标题简洁（< 70 字）
- PR 描述写清楚：做了什么、为什么这样做、怎么测试
- 如果改动涉及文档，PR 里包含对应的文档更新

### 4. 审批

项目主（keyapi）会审批 PR。审批后 merge 到 main。

## 新增 Skill 或模块

1. 模块目录放到项目根目录下
2. 每个模块需要 3 个文件：脚本 `.py`、`README.md`（人读）、`AGENT_HANDOFF.md`（Agent 读）
3. Skill 文件放到 `.agents/skills/<name>/SKILL.md`
4. 在 AGENTS.md 模块索引表里加一行
5. 详细格式见 `docs/agent-guide.md`

## 代码约定

- 技术栈：Python ≥ 3.10 + uv + pandas + openpyxl
- 用 `uv add <包名>` 加依赖
- 每个脚本 `cd` 到模块目录运行
- Excel 输出放 `out/` 目录（gitignored），带时间戳文件名
- 约定详见 AGENTS.md 和 docs/agent-guide.md

## 不需要的事

本项目没有 CI/CD、没有自动化测试框架、没有 lint CI。以下操作用 Claude Desktop Agent 手动做：

- 代码 review：让 Agent 读 PR diff 做 review
- 测试：Agent 运行脚本，检查 Excel 输出
- 合并：Agent 执行 `git merge`
