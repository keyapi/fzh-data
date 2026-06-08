# 快速上手（非技术同事）

> 你是运营/销售同事，不需要懂 git 或命令行。跟着做一遍，之后告诉你的 Claude Desktop Agent 就行。

## 第一次配置（只做一次）

### 1. 安装 Claude Desktop

官网下载安装：https://claude.ai/download

### 2. 让 Agent 帮你 clone 项目

打开 Claude Desktop，对 Agent 说：

> 帮我克隆项目到本地：
> git clone https://github.com/keyapi/fzh-data.git D:\fzh-data
> 装好依赖：进 D:\fzh-data ，执行 uv sync

Agent 会自动执行。装完即用。

## 日常使用

### 上传图片到 ERPNext 获取链接

对 Agent 说：

> 帮我启动图片上传 Web 工具

Agent 会运行 `uv run python EN_API/image_upload_app.py`，浏览器自动打开上传页面。

在页面里拖图片进去 → 调整顺序 → 点"上传到 ERPNext"→ 下载 Excel 拿到链接。

### 其他功能

告诉 Agent 你要做什么，Agent 会读项目文档，找到对应的脚本运行。

## 项目更新了怎么同步

对 Agent 说：

> 帮我把 fzh-data 项目更新到最新版

Agent 执行 `git pull` 即可。如果本地有改动，Agent 会用 `git stash` 临时丢掉再更新（你不会改代码，所以没有需要保留的本地修改）。

## 有需求怎么提

对 Agent 说（任选一种说法都可以）：

> 帮我在 EN 创建待办：需要 XXX 功能，因为 XXX
>
> 帮我在 ERPNext 创建需求：XXX
>
> 帮我创建一个 ToDo：XXX

Agent 会自动在 ERPNext 里创建一条待办记录。项目负责人会定期看 EN 里的 ToDo 列表，把需求转成实现。

> A 类同事不需要 GitHub 账号、不需要学 git。Agent + EN ToDo 就是你的需求通道。

## 你不需要的东西

- ❌ GitHub 账号 — 不需要
- ❌ 学 git / 命令行 — 不需要
- ❌ 读代码 / 改代码 — 不需要
- ✅ 你只需要：告诉 Agent 你要什么，Agent 帮你跑
