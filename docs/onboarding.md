# 快速上手（非技术同事）

> 你是运营/销售同事，不需要懂 git 或命令行。用 Codex Agent 帮你跑一切。

## 第一次配置（只做一次，约 10 分钟）

### 1. 安装 Codex

找项目负责人要 Codex 安装包，装好打开。

### 2. 种子指令：让 Codex 帮你把项目搭起来

打开 Codex，粘贴下面这段话：

> 帮我设置 fzh-data 项目：
> 1. 检查 Git 是否安装——没装的话按系统装（Windows: winget, Mac: brew, Linux: apt-get）
> 2. git clone https://github.com/keyapi/fzh-data.git ~/fzh-data
> 3. 进目录读 AGENTS.md，按里面「Agent 新机器首次 clone 后必做」的步骤初始化所有依赖
> 4. 装完后提醒我重启 Codex

Codex 会自动检测系统、安装 Git/uv/Node.js/MCP、拉代码。装完后**重启 Codex**（完全退出再打开），MCP 服务器（网页搜索等）才会生效。

> **Mac 用户**：如果 ~/fzh-data 不习惯，可以换成其他路径，比如 ~/Desktop/fzh-data。
> **Linux 用户**：同上，路径随意。

### 3. 信任项目

重启 Codex 后打开 fzh-data 项目目录，如果弹窗问「是否信任此项目」→ 务必选**「是」**。选「否」会导致搜索等功能不可用。

---

## 日常使用

### 上传图片到 ERPNext 获取链接

对 Agent 说：

> 帮我启动图片上传 Web 工具

Agent 会运行 `uv run python EN_API/image_upload_app.py`，浏览器自动打开上传页面。

在页面里拖图片进去 → 调整顺序 → 点「上传到 ERPNext」→ 下载 Excel 拿到链接。

### 其他功能

告诉 Agent 你要做什么，Agent 会读项目文档，找到对应的脚本运行。比如：

> 帮我做库存初始化
> 帮我导入采购成本
> 帮我搜索 XXX 相关信息

---

## 项目更新了怎么同步

对 Agent 说：

> 帮我把 fzh-data 项目更新到最新版

Agent 执行 `git pull` 即可。如果本地有改动，Agent 会用 `git stash` 临时丢掉再更新（你不会改代码，所以没有需要保留的本地修改）。

---

## 有需求怎么提

对 Agent 说（任选一种说法都可以）：

> 帮我在 EN 创建待办：需要 XXX 功能，因为 XXX
>
> 帮我在 ERPNext 创建需求：XXX
>
> 帮我创建一个 ToDo：XXX

Agent 会自动在 ERPNext 里创建一条待办记录。项目负责人会定期看 EN 里的 ToDo 列表，把需求转成实现。

> A 类同事不需要 GitHub 账号、不需要学 git。Agent + EN ToDo 就是你的需求通道。

---

## 备选：Claude Desktop 用户

如果你用的是 Claude Desktop 而不是 Codex，步骤类似：

1. 官网下载安装：https://claude.ai/download
2. 粘贴同样的种子指令（把「Codex」换成「Claude Desktop」）
3. 装完后还需额外运行一步：`powershell -ExecutionPolicy Bypass -File setup.ps1`（创建 Skill 链接）
4. 重启 Claude Desktop

---

## 你不需要的东西

- ❌ GitHub 账号 — 不需要
- ❌ 学 git / 命令行 — 不需要
- ❌ 读代码 / 改代码 — 不需要
- ✅ 你只需要：告诉 Agent 你要什么，Agent 帮你跑
