# Superpowers 手动安装指南（Claude Desktop 3P 模式）

> 最后更新：2026-06-09  
> 面向：B 类技术开发同事  
> 适用：Claude Desktop 3P 模式，组织未开通 Plugin 市场  
> 仓库：https://github.com/obra/superpowers

---

## 背景

Superpowers 是 obra 开发的 14 个 Agent Skill 集合（brainstorming、TDD、writing-plans 等），提供结构化的软件开发方法论。

**Claude Code CLI** 可以通过 `/plugin install superpowers@claude-plugins-official` 一键安装。但 **Claude Desktop 3P 模式**存在两个障碍：

1. 组织 Plugin 市场未开通（Customize → Plugins → Browse 显示 "Your organization hasn't provided plugins"）
2. Superpowers 不是 MCP server，无法通过 `claude_desktop_config.json` 安装

**解决方案：手动安装 skill 文件到 `~/.claude/skills/`。**

---

## 关键认知

### Claude Desktop 的三套扩展机制

| 机制 | 入口 | 3P 模式下可用？ |
|------|------|:---:|
| **MCP 服务器** | `claude_desktop_config.json` / Connectors 面板 | ✅ |
| **Plugin 市场** | Customize → Plugins → Browse | ❌ 需要组织开通 |
| **Skill 文件** | `~/.claude/skills/` 目录 | ✅ 自动加载 |

MCP（Playwright、FAC）和 Skill（frontend-design、superpowers）走的是**不同通道**。Plugin 市场本质上是 Skill 文件的自动分发渠道——关了市场只是不能一键安装，手动放文件一样用。

### Superpowers 的组件拆解

| 组件 | 作用 | 手动装能否工作 |
|------|------|:---:|
| `skills/*/SKILL.md` | 14 个核心技能 | ✅ |
| `hooks/session-start` | 每个新会话注入使用说明 | ❌ 需要插件系统 |
| `.claude-plugin/` | 市场元数据 | 不需要 |

**Hook 只做自动注入使用说明书，不影响 skills 执行。**

---

## 安装步骤

### 1. 检查是否已有冲突的 skill

```bash
ls ~/.claude/skills/brainstorming/
ls .agents/skills/brainstorming/
```

如果存在——特别是来自 `npx skills add` 的 Open Design 空壳版（43 行，只有目录条目，无实质方法论）——先删除：

```bash
rm -rf .agents/skills/brainstorming/
```

### 2. 克隆仓库

```bash
git clone https://github.com/obra/superpowers.git ~/.claude/superpowers
```

### 3. 创建 Skill 链接

**关键踩坑：不支持父级 symlink。**

❌ 错误做法（Claude Desktop 不递归扫描嵌套子目录）：
```bash
ln -s ~/.claude/superpowers/skills ~/.claude/skills/superpowers
```

✅ 正确做法——每个 skill 单独建链接：

```bash
python -c "
import os, subprocess
skills_dir = os.path.expanduser(r'~\.claude\superpowers\skills')
target_dir = os.path.expanduser(r'~\.claude\skills')
for name in os.listdir(skills_dir):
    src = os.path.join(skills_dir, name)
    dst = os.path.join(target_dir, name)
    if os.path.isdir(src) and not os.path.exists(dst):
        print(f'Creating junction: {name}')
        subprocess.run(['cmd', '/c', 'mklink', '/J', dst, src], check=True)
print('Done')
"
```

**为什么用 Python 而不是 shell 循环：** Git Bash 在 Windows 上的 `for` 循环中 bash 变量无法正确传入 `cmd /c mklink`（变量被原样输出而非展开），且路径含中文时编码问题更严重。

### 4. 重启 Claude Desktop

### 5. 验证

重启后在对话中测试：

```
/using-superpowers
/brainstorming
```

均返回完整 skill 内容即为成功。

---

## 经验教训

### Lesson 67：Skill 扫描只走一层

`~/.claude/skills/` 下的 symlink 如果指向一个包含多个子目录的**父目录**，Claude Desktop 不会递归扫描子目录中的 `SKILL.md`。每个 skill 必须作为独立目录（或独立 symlink）直接出现在 `~/.claude/skills/` 下。

推断依据：`frontend-design -> ~/.agents/skills/frontend-design`（单级 symlink）能工作，但 `superpowers -> ~/.claude/superpowers/skills`（父级 symlink，内含 14 个子目录）不工作。

### Lesson 68：Windows 上 bash/cmd 混用陷阱

在 Git Bash 中通过 `cmd /c` 执行 Windows 原生命令时，bash 变量（`$name`、`${name}`）在 `cmd` 的上下文中不会被展开。这导致 `mklink` 收到字面字符串 `$name` 而非实际目录名。

**Workaround：用 Python 的 `subprocess.run` 作为中间层**，在 Python 中拼接好路径再传给 `cmd /c mklink`。

### Lesson 69：Open Design 的 skill 是目录条目，不是实现

通过 `npx skills add` 安装的某些 skill（如 Open Design 的 brainstorming）可能是"瘦客户端"——只有 43 行，包含 `upstream: "https://github.com/obra/superpowers"` 引用，但没有实质方法论。它的作用是告诉你"去装上游完整版"。安装前先读 SKILL.md 确认不是空壳。

### Lesson 70：Plugin 市场和 Skill 文件是同一套底层

Claude Desktop 的 Plugin 就是打包好的 Skill 文件集合。组织关了市场不等于不能用 skills——手动放到 `~/.claude/skills/` 同样生效。这跟 VS Code 扩展的 `.vsix` 文件和手动放到 `~/.vscode/extensions/` 的关系类似。

---

## 卸载

```bash
# 删除所有 superpowers skill 链接
rm ~/.claude/skills/brainstorming
rm ~/.claude/skills/dispatching-parallel-agents
rm ~/.claude/skills/executing-plans
rm ~/.claude/skills/finishing-a-development-branch
rm ~/.claude/skills/receiving-code-review
rm ~/.claude/skills/requesting-code-review
rm ~/.claude/skills/subagent-driven-development
rm ~/.claude/skills/systematic-debugging
rm ~/.claude/skills/test-driven-development
rm ~/.claude/skills/using-git-worktrees
rm ~/.claude/skills/using-superpowers
rm ~/.claude/skills/verification-before-completion
rm ~/.claude/skills/writing-plans
rm ~/.claude/skills/writing-skills

# 删除克隆的仓库（可选）
rm -rf ~/.claude/superpowers
```

---

## 相关文档

- [FAC MCP 部署指南](./fac-mcp-setup.md) — MCP 安装方式
- [AI Agent 桌面版对比](./ai-agent-desktop-comparison.md) — Claude Desktop vs Codex 差异
- [Superpowers 上游仓库](https://github.com/obra/superpowers)
- [Claude Code 插件市场](https://claude.com/plugins/superpowers)
