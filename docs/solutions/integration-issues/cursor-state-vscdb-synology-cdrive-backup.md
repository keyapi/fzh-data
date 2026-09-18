---
okf: v0.1
type: Reference
title: Cursor state.vscdb 膨胀 + Synology Drive 连续备份吃光 C 盘
date: 2026-09-01
last_updated: 2026-09-01
category: integration-issues
module: cursor-agent-environment
problem_type: integration_issue
component: tooling
severity: critical
symptoms:
  - "Cursor 打开后 C 盘空闲以 ~1GB/min 持续下降，多次降到 0，重启/关闭 Cursor 后恢复 ~37GB"
  - "SynologyDrive temp\\N\\.SynologyWorkingDirectory 出现 ~27GB 的孤儿暂存文件（连续备份上传副本）"
  - "state.vscdb 膨胀到 31.8GB，`Developer: GC Agent KV Blobs` 报 SQLITE_FULL 或 0 deleted"
root_cause: config_error
resolution_type: config_change
tags:
  - cursor
  - state.vscdb
  - synology-drive
  - c-drive
  - disk-space
  - agent-environment
  - sqlite
related_components: [cursor, synology-drive, windows]
---

# Cursor state.vscdb 膨胀 + Synology Drive 连续备份吃光 C 盘

## Problem

Cursor 打开后 C 盘剩余空间从 37GB 持续掉到 0，且当日多次复发；关闭 Cursor 后空间恢复。排查发现是两个因素叠加：**state.vscdb 膨胀**（Cursor 已知 bug）+ **Synology Drive 连续备份**把该库当高频变化文件反复上传。

## Symptoms

- Cursor 运行时空闲空间以 ~1GB/min 下降（实测 `cloud-drive-daemon.exe` 以 15-19MB/s 持续写盘）。
- 完全退出 Cursor → C 盘恢复到 ~37GB（备份任务停止、暂存被清理）。
- 首次发生时关联 OpenCode/Git/DSH junction 环文章，但本机**无 `.dsh`、无 junction 环**，已排除。
- `state.vscdb` 从 5 月的 1.6GB 膨胀到 31.8GB；`cursorDiskKV` 表 1,841,851 行，其中 `bubbleId:task-*`（agent 任务气泡）1,401,176 行。

## What Didn't Work

1. **怀疑 Cursor 软件 bug / 网络问题** — 排除：进程抓包/日志均正常，C 盘下降是真实磁盘写入。
2. **怀疑 OpenCode/DSH junction 环**（公众号文章案例）— 排除：本机主目录无 `.dsh`；`.adal`/`.aider-desk` 指向 `.agents\skills` 的单向 junction 无回环。
3. **`Developer: GC Agent KV Blobs` 收缩 state.vscdb** — 失败两次：
   - 在 C 盘跑：`SQLITE_FULL`。GC 压缩需要 **2~3 倍库大小空闲**（旧库 + WAL 膨胀 + 压缩副本三份并存），C 盘 50GB 都不够。
   - 搬 globalStorage 到 D 盘（junction）跑：GC 成功但 **0 deleted** —— 所有 agentKv blob 都被对话/任务"引用"（live），包括 1.4M 个 `bubbleId:task-*` 根本不在 GC 清理范围。**GC 无法缩小这个库。**
4. **`Reload Window` 结算 WAL** — 不生效（只重载渲染层，主进程仍握着连接）；必须**完全退出 Cursor** 才触发 WAL checkpoint。

## Solution

**主修复：停掉并删除 Synology Drive 的连续备份任务。**

1. **Synology Drive Client → 暂停并删除备份任务**（该任务备份 `C:\Users\zhang\AppData\Roaming\Cursor\User\globalStorage` 到 NAS `/volume1/总经办/张克勇/CursorUser/FZHPC13`，模式"连续备份"）。这是 C 盘被吃光的直接触发源。
2. **清理 Synology 孤儿暂存**：删除 `C:\Users\zhang\AppData\Local\SynologyDrive\temp\6\.SynologyWorkingDirectory\`（约 27GB，任务已暂停后安全）。
3. **清理 C 盘可删缓存**（+12.4GB）：
   - Garmin 离线地图 `AppData\Local\Garmin\express\maps`（~8.3GB）
   - 微信更新缓存 `Tencent\xwechat\update`（2.1GB）、企业微信 `Tencent\WXWork\upgrade`（1.8GB）
   - TEMP 残留 `vscode-stable-user-x64-*`、`nsk44E9.tmp`、`Diagnostics`
4. **state.vscdb 保留在 C 盘 SSD（31.8GB）**——GC 清不掉（全 live），用户决定不删旧对话，接受该占用。C 盘稳定在 ~50GB 空闲。

### 诊断定位方法（可复现）

```bash
# 1. 实时抓写盘进程（定位 cloud-drive-daemon 之类的元凶）
powershell "Get-Counter '\Process(*)\IO Write Bytes/sec' | Select -Expand CounterSamples | Where CookedValue -gt 5MB | Sort CookedValue -Desc | Select -First 5 InstanceName, CookedValue"

# 2. 查 Synology 连续备份的暂存目录（C 盘被吃的直接证据）
#    C:\Users\zhang\AppData\Local\SynologyDrive\temp\N\.SynologyWorkingDirectory\

# 3. 查 state.vscdb 及其 WAL（WAL 暴涨说明有进程在重写数据库）
ls -la "%APPDATA%\Cursor\User\globalStorage\" | grep -iE "state.vscdb|wal"

# 4. 确认 Synology 备份任务指向（data\db\sys.sqlite 的 connection_table + server_view_table）
```

### 大库跑 GC 的可靠方式（避免 SQLITE_FULL）

GC 压缩需要 2~3 倍库空间。C 盘物理放不下时：

```bash
# ① 完全退出 Cursor
# ② 把 globalStorage 复制到 D 盘
robocopy "C:\Users\zhang\AppData\Roaming\Cursor\User\globalStorage" "D:\CursorData\globalStorage" /E /R:1 /W:1 /MT:16
# ③ 建 junction
powershell "New-Item -ItemType Junction -Path 'C:\Users\zhang\AppData\Roaming\Cursor\User\globalStorage' -Target 'D:\CursorData\globalStorage'"
# ④ 开 Cursor 跑 GC（现在临时文件在 D 盘，有空间）
# ⑤ 完全退出 Cursor（触发 WAL checkpoint）→ 移除 junction → 搬回/留 D
```

## Why This Works

- **根因**：`state.vscdb` 是 Cursor 的全局 SQLite 库（聊天 + Agent KV），已知 bug 会无限膨胀（社区见 41GB 案例；官方"正在跟踪"）。5 月时 1.6GB，近 3 个月涨到 31.8GB。库变大后，Synology **连续备份**检测到它高频变化 → 在 C 盘暂存 ~30GB 上传副本（`temp\N\.SynologyWorkingDirectory`）→ C 盘被吃光。
- 停掉备份任务 → 触发源消失 → C 盘不再被吃。
- GC 清不掉的原因：所有 blob 都被对话/任务引用（live），无孤儿可删；1.4M 个 `bubbleId:task-*` 是 agent 任务状态快照，绑定在对话上，不在 GC 清理范围。

## Prevention

1. **绝不连续备份 Cursor 的 `globalStorage` / `state.vscdb`**。备份聊天记录的正确方式：Cursor 关闭状态下定时拷贝 `state.vscdb` + `~\.cursor\projects\` 到 D 盘/NAS（如 `D:\CursorBackup\state.vscdb.YYYYMMDD`）。
2. **GC 只清"孤儿"agent 数据**，对全 live 的库无效；大库上还要求 2~3 倍空间。想真正缩库要用 `Developer: Delete Old Chats…`（会删聊天）或手动清理（有 UI 风险）。
3. **WAL 结算必须完全退出 Cursor**，`Reload Window` 不触发。
4. **监控**：C 盘空间骤降先查 `SynologyDrive\temp\N\.SynologyWorkingDirectory`，再看 `%APPDATA%\Cursor\User\globalStorage\state.vscdb` 及其 WAL 是否暴涨。可用 `scripts/check_cursor_cdrive_health.py`。

## Investigation Timeline（2026-08-28 ~ 09-01）

1. **08-28 发现**：C 盘从 37GB 掉到 0，多次复发；关闭 Cursor 恢复。Web 调研命中 state.vscdb 膨胀已知 bug + Synology 连续备份嫌疑。
2. **08-28 实锤**：`cloud-drive-daemon.exe`（Synology）以 15-19MB/s 写盘；`SynologyDrive\temp\6\.SynologyWorkingDirectory\HceEKc-P` = 27.39GB 暂存。暂停备份 → 增长停止；删暂存 → C 盘回到 ~30GB。
3. **08-28 备份**：`state.vscdb` 用 sqlite3 `.backup` 一致性快照到 `D:\CursorBackup\state.vscdb`（31.7GB）。
4. **08-31 比对**：从 NAS 下载周五 11.91GB 快照（SFTP，`nas.daneey.com`），与 17:19 备份比对。结论：周五 10:14→17:19 涨 ~20GB，**几乎全是 `bubbleId:task-*`（+97万行，agent 任务气泡）+ checkpoint + agentKv，不是聊天**（ItemTable 只 +6 行）。抽样到最大任务之一是 PB 促销模板任务（Tracy Miller / Vendor Promo Template_Centrade）。
5. **08-31 GC 失败 ×2**（C 盘 SQLITE_FULL）→ 搬 globalStorage 到 D 盘 junction → GC 成功但 0 deleted。
6. **09-01 收尾**：WAL（31.9GB）在完全退出后 checkpoint；移除 junction；`.old` 重命名回 C 盘原位置（数据与 D 副本一致，零拷贝）；C 盘稳定 ~50GB。

## Lessons

- **磁盘骤降先找"高频写盘进程"再找"被反复上传的大文件"**，用 `Get-Counter` 抓进程级写入速率最直接。
- **连续备份 + 频繁变化的大 SQLite 库 = 灾难**；数据库备份必须"关闭时快照"，不能"实时连续"。
- **Cursor GC 的认知纠偏**：它只清孤儿数据，全 live 的库删不动；大库压缩需要 2~3 倍空间。别指望 GC 收缩一个活跃使用的库。
- **junction 移除要非递归**：`[System.IO.Directory]::Delete(path, $false)` 只删链接不碰目标，`rm -rf` 会跟进目标。
- **Git Bash 里调 robocopy/cmd 有 MSYS 路径转换坑**（`/E` 变 `E:\`），要用 PowerShell 包装或用 `//`。

## Related

- Cursor 论坛：[State.vscdb grows to 30GB due to bubbleId/agentKv entries](https://forum.cursor.com/t/state-vscdb-grows-to-30gb-due-to-bubbleid-agentkv-entries/167641)
- 排查脚本：[scripts/check_cursor_cdrive_health.py](../../../scripts/check_cursor_cdrive_health.py)
