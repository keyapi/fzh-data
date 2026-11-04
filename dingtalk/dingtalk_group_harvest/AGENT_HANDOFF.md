---
okf: v0.1
type: Reference
title: dingtalk_group_harvest — Agent 交接
timestamp: 2026-11-03
---

# AGENT_HANDOFF — dingtalk_group_harvest

## 一句话

用 DWS 个人身份把钉钉三个 AI 项目群的增量消息、附件、钉钉文档采集到仓库外，并按周生成记录。

## 关键决策（不要改回去）

1. **不用群机器人采集**：自定义机器人只发不收；企业内部应用 Stream 只能收 @机器人 的实时消息。完整历史走 DWS 用户身份。
2. **原始数据必须在仓库外**：默认 `%USERPROFILE%\dingtalk_harvest`，`DINGTALK_HARVEST_ROOT` 可覆盖。公开仓库只放代码、模板、脱敏文档。
3. **水位只在完整时推进**：`complete=false` / `hasMore=true` / `failures` 非空 / 文件下载失败，都不推进水位，退出码 3。
4. **文档导出失败不阻塞水位**：消息原文已归档，链接可在下次或人工重试；报告里单列。
5. **首期不做实时 Stream**：需要常开进程、断线补拉、去重，收益低于每日批处理。

## 文件职责

| 文件 | 职责 |
|---|---|
| `paths.py` | 归档根、配置路径、DWS 可执行文件定位 |
| `dws_client.py` | subprocess 封装、JSON 解析、登录态检查、ledger 完整性校验 |
| `state.py` | 按群水位、1 秒重叠窗口、原子写 |
| `normalize.py` | 文件/媒体引用识别、钉钉文档链接提取、安全文件名 |
| `harvest.py` | 解析群、拉消息、下载文件、导出文档、归档、推进水位 |
| `reconcile.py` | 对账报告 |
| `digest.py` | 周报：结构化 JSON + Markdown + 可选 Claude Code 润色 |
| `cli.py` | `resolve` / `harvest` / `digest` / `status` |

## 常用命令

```bash
uv run python -m dingtalk.dingtalk_group_harvest.cli resolve --write
uv run python -m dingtalk.dingtalk_group_harvest.cli harvest --dry-run
uv run python -m dingtalk.dingtalk_group_harvest.cli harvest --group "运营2部AI项目沟通群"
uv run python -m dingtalk.dingtalk_group_harvest.cli digest --week 2026-W45 --no-llm
uv run python -m dingtalk.dingtalk_group_harvest.cli status
uv run pytest dingtalk/dingtalk_group_harvest/tests -q
```

## 失败模式

| 现象 | 原因 | 处理 |
|---|---|---|
| `DWS 登录态无效` | refresh token 过期或换设备 | 交互终端 `dws auth login` 扫码 |
| `结果不完整` / 退出码 3 | DWS 分页失败或限流 | 看 `reports/`，降低页大小/重跑；水位未动 |
| 群名无法唯一解析 | 群改名或重名 | 手动在 `groups.local.json` 填 `openConversationId` |
| 文件下载失败 | 文件过期/权限/临时网络 | 水位不推进，下次重试；报告有文件名 |
| 文档导出失败 | 无文档权限/链接失效 | 报告列出 URL；消息原文仍在 |
| 定时任务没跑 | 电脑关机/未登录 | 任务以交互用户运行，需开机登录 |
| 周报末尾出现「已输出结构化版本」 | Claude Code 调用失败 | 长提示词已改走 stdin；看 `claude -p` 的 stderr/退出码 |

## DWS 版本

2026-11-03 实测 `v1.0.66-beta.2`。升级后先跑：

```bash
uv run python -m dingtalk.dingtalk_group_harvest.cli harvest --dry-run
```

确认 `complete / hasMore / failures` 字段语义未变。

## 定时任务的路径陷阱

在 worktree 里运行 `install_harvest_schedule.ps1` 会把任务指向 **worktree 路径**。合并到 main 后，必须在主仓库根目录重跑一次安装脚本，否则删除 worktree 会让任务失效。

## 新对话必读

- `../../docs/solutions/tooling-decisions/dingtalk-group-harvest-dws-user-identity.md` —— 为什么用 DWS 而不是机器人/会话存档
- `../../docs/solutions/developer-experience/claude-headless-long-prompt-stdin.md` —— 周报润色为什么走 stdin
- `../../docs/solutions/developer-experience/windows-schtasks-worktree-path-trap.md` —— 计划任务路径陷阱
