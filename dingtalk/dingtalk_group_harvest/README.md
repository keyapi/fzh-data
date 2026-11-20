---
okf: v0.1
type: Guide
title: dingtalk_group_harvest — 使用指南
timestamp: 2026-11-03
---

# dingtalk_group_harvest

钉钉 AI 项目群（运营2/3/4部）的**群消息与文件增量采集 + 周报**工具。

用钉钉官方开源 CLI [DWS](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli) 以**个人 OAuth 身份**读取群历史和消息附件，不依赖群机器人，也不需要企业内部应用或会话存档。

## 为什么不用群机器人

- 自定义群机器人只能发送，不能读取群消息或文件。
- 企业内部应用 + Stream 只能收「@机器人」的实时消息，读不到历史。
- 会话存档需要企业付费/管理员开通，且要自行解密落库。

DWS 直接复用你在钉钉客户端里的身份和权限，能拉历史消息、下载消息附件、导出钉钉文档。

## 前置条件

1. 安装 DWS，并确保 `dws` 在 PATH，或设置 `DWS_EXE`。
2. 管理员已在开发者平台开启 CLI 访问（公司已开通）。
3. 登录一次：`dws auth login`。refresh token 有效期内 `dws auth status` 会自动续期；过期后需要重新扫码。

## 快速开始

```bash
# 1. 解析三个群，写入本地配置（gitignore）
uv run python -m dingtalk.dingtalk_group_harvest.cli resolve --write

# 2. 采集（首次默认回溯 60 天；之后按水位增量）
uv run python -m dingtalk.dingtalk_group_harvest.cli harvest

# 3. 生成上一周周报
uv run python -m dingtalk.dingtalk_group_harvest.cli digest

# 4. 查看登录态与水位
uv run python -m dingtalk.dingtalk_group_harvest.cli status
```

## 配置

- `config/groups.example.json`：入库模板。
- `config/groups.local.json`：本机实际配置（已 gitignore）。首次 `resolve --write` 会自动生成并写入 `openConversationId`。

每个群支持：

```json
{"name": "运营2部AI项目沟通群", "openConversationId": "cid...", "enabled": true, "backfillDays": 60}
```

## 归档目录

默认 `%USERPROFILE%\dingtalk_harvest`，可用 `DINGTALK_HARVEST_ROOT` 覆盖。**所有原始聊天和文件都在仓库外。**

```
<root>/
├── <群名>/messages/YYYY-MM-DD.jsonl
├── <群名>/files/YYYY/MM/<时间>_<发送人>_<文件名>
├── <群名>/media/YYYY/MM/...          # --include-media 时
├── <群名>/docs/YYYY/MM/<标题>.md      # 钉钉文档链接导出的 markdown
├── digests/<群名>/YYYY-Www.md|json
├── reports/<run-id>.md
├── state/watermarks.json
└── logs/
```

## 增量与完整性

- 水位按群保存；每次从上次时间前 1 秒开始，按 `messageId` / `resourceId` 去重。
- DWS 返回 `complete=false`、`hasMore=true` 或有 `failures` 时，**不推进水位**，退出码 3。
- 文件下载失败同样不推进水位，下次运行重试。
- 钉钉文档导出失败只记入报告，不阻塞水位（消息原文已归档，可手动重试）。
- 每次运行写 `reports/<run-id>.md`，含消息/文件/文档的数量对账。

## 定时任务

```powershell
powershell -ExecutionPolicy Bypass -File dingtalk\dingtalk_group_harvest\scripts\install_harvest_schedule.ps1
```

默认每天 08:10 采集、每周一 08:40 汇总。任务以当前登录用户运行，电脑需开机且已登录。日志在 `<root>\logs\`。

> 如果当前是在 git worktree 里注册，任务会指向 worktree 路径。合并后请在主仓库根目录重新运行一次安装脚本，把任务重定向到主仓库；否则删除 worktree 后任务会失效。

## 隐私与合规

- 聊天原文、群文件、人名只落本机私有目录；**绝不提交到公开仓库**。
- 摘要由本地 Claude Code 生成，不经过第三方服务；如未安装 `claude`，会输出结构化版本。
- 本工具只读取你有权限的群；不绕过任何钉钉权限。

## 已知限制

- DWS 仍为 beta，ledger 字段可能变化；升级后先跑 `harvest --dry-run` 回归。
- 标准版钉钉群文件约 180 天保留期，首次采集请尽早。
- 定时任务依赖本机在线；NAS 同步建议单独做，不要让采集直接写网络盘。
- 共享/加密消息若被 DWS 标为解密失败，会在报告里体现，不会静默丢弃。
