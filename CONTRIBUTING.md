# 贡献指南（技术开发）

> 你有 GitHub 权限，可以用 Claude Desktop Agent 开发新功能、修复问题、维护 Skill 和文档。
> **main 分支受保护：所有改动必须通过 PR 合并，至少 1 人审批。**

## Git 认证配置

> SSH 在某些网络环境不稳定（GFW），推荐 HTTPS + GitHub CLI。

### 首次配置

1. 生成 [GitHub Personal Access Token](https://github.com/settings/tokens?type=beta)（Fine-grained token），权限：
   - **Contents** — 读写（push/pull）
   - **Issues** — 读写（给其他项目提 issue）
2. 保存 token 到项目根目录：

```bash
echo "github_pat_YOUR_TOKEN" > .gh-token
```

3. 配置 `gh` 认证：

```bash
gh auth login --with-token < .gh-token
gh auth setup-git         # git push/pull 自动走 gh 认证
```

4. 验证：

```bash
gh auth status            # 显示 ✓ Logged in
git push origin main      # 应该能正常 push
```

`.gh-token` 已在 `.gitignore` 中，不会被提交。每个开发者用自己的 PAT。

### 原理

HTTPS 协议不受 GFW 干扰，`gh` CLI 用 token 做认证——比 SSH 更稳定，比把 token 嵌在 remote URL 里更安全。

---

## 首次初始化

Clone 后运行一次：

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

> **为什么需要？** `CLAUDE.md` 是 symlink（→ AGENTS.md），Windows 上 git clone 不会自动创建。
> `~/.claude/skills/` 同样需要链接到项目的 `.agents/skills/`。
> 脚本也处理 superpowers（如果已安装）。

运行一次即可，后续 `git pull` 新增的 skill 需要重新运行脚本。

---

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
