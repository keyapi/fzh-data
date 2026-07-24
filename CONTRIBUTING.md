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

### Git Worktree 创建（Windows 特别说明）

> `CLAUDE.md` 和 `.claude/skills` 在 git 中以 symlink 形式跟踪（mode 120000）。
> Git for Windows 默认 `core.symlinks=false`，clone 和 worktree 均正常。
> 如果机器上 `core.symlinks=true`（如开启了 Windows 开发者模式），worktree 会因权限不足失败。

**Windows 上正确的 worktree 创建方式：**

```bash
# 从主 repo 目录（如 D:\Work\赛狐\Cursor）执行
git -c core.symlinks=false worktree add <path> -b <branch-name>

# worktree 创建后，在新 worktree 中运行
cd <path>
powershell -ExecutionPolicy Bypass -File setup.ps1
```

> `setup.ps1` 的 `New-SafeSymlink` 会尝试创建真实 symlink，失败则自动回退为文件拷贝。

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

## 安全检查（提交前必做）

> ⚠️ 以下规则源于真实泄露事故。违反任一条 → PR 不得合并。

### 硬规则

1. **禁止硬编码凭证** — 密钥、token、密码一律走 `os.getenv()` 或 `.env` 文件
2. **文档/注释只用占位符** — spec、设计文档、注释中的示例密钥必须写成 `<your_key>` 或 `***`，禁止写真实值
3. **禁止 `Bash(KEY=真实值 ...)` 进 allowlist** — 需要传 env var 给命令时，去 `.env` 里设，不要在命令行内联。已经内联过的：去 `settings.local.json` 把值换成 `*`

### 提交前扫描

```bash
# 扫描密钥模式（提交前跑）
grep -rnE "(api_key|api_secret|token|password)\s*=\s*['\"]?[a-zA-Z0-9_-]{10,}" --include="*.py" --include="*.md" --include="*.json" . | grep -v ".git/" | grep -v "settings.local.json" | grep -v ".env"
```

上面命令**不应有输出**。有输出 = 有疑似硬编码密钥，必须清理。

### settings.local.json 陷阱

Claude Desktop 的 "Always allow" 会把整条命令（含内联 env var 值）写进 `settings.local.json`。**永远不要**用以下方式传密钥：

```bash
# ❌ 禁止：内联 env var 会被写进 allowlist
ERP_API_KEY="real_key" uv run python script.py
```

```bash
# ✅ 正确：去 .env 文件设，脚本从 os.getenv 读
uv run python script.py
```

如果已踩坑，清理方法：
```bash
python -c "
p = '.claude/settings.local.json'
c = open(p).read()
for secret in ['real_key_1', 'real_key_2']:
    c = c.replace(secret, '*')
open(p, 'w').write(c)
"
```

### PR review 必查项

Reviewer 必须确认：
- [ ] 无硬编码密钥、token、密码
- [ ] 新增的 spec/设计文档里没有真实凭证
- [ ] 新增的 allow 规则（settings.local.json diff）不含真实值

---

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
