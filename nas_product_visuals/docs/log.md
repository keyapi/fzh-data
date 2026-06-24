---
okf: v0.1
type: Log
title: 变更 + 调试日志
description: NAS ACL 权限修复脚本的变更记录和调试过程
tags: [nas, synology, bash, acl, inotify, debug]
---

# 变更 + 调试日志

## 2026-06-24 — fix_design_permissions.sh 调试

### 背景

同事创建了 `/volume1/技术部/fix_design_permissions.sh`，配合 inotify-tools 实时监控"设计稿"文件夹新建事件，
自动用 `synoacltool -add` 添加显式 DENY ACE 阻止"视觉需求（读取）"角色的访问。

目标 ACL 效果：
```
[0] group:视觉需求（读取）:deny:rwxpdDaARWcCo:fd-- (level:0, 显式)
[4] group:视觉需求（读取）:allow:r-x---a-R-c--:fd-- (level:3, 继承但被显式 deny 覆盖)
```

### 环境参数

| 项 | 值 |
|----|-----|
| NAS | `fzh.myds.me:31022` (DSM 7, BTRFS) |
| inotifywait | `/usr/local/bin/inotifywait` v4.23.9.0 (不在 fzh.nas/root PATH) |
| grep | GNU grep 3.1 |
| synoacltool | `/usr/syno/bin/synoacltool` |
| locale | POSIX (LC_ALL=, LC_CTYPE=POSIX) — **关键问题来源** |

### 发现的问题

#### Bug 1 (已修复): `echo` 在 POSIX locale 下破坏 UTF-8 字节

- **现象**: `acl=$(synoacltool -get DIR); echo "$acl" | grep -F "视觉需求"` 在 POSIX locale 下永远返回空
- **根因**: bash `echo` 内置命令在 POSIX locale 下破坏多字节 UTF-8 字符（全角括号）导致管道下游 grep 收到损坏数据
- **修复**: 不用 `echo`，直接 pipe synoacltool 输出：`synoacltool -get DIR | grep -F "视觉需求" | grep -q "deny"`
- **教训**: 在群晖 POSIX locale 环境下，绝不能 `echo "$var" | grep` 含中文的变量

#### Bug 2 (已确认): `synoacltool -del` 无法删除 deny ACE

- **现象**: `synoacltool -del <path> <index>` 返回 `(synoacltool.c, 672) Access deny`，即使 root
- **影响**: 无法事后清理重复 deny，必须在事前 100% 阻止重复
- **绕过**: DSM 网页端 File Station → 右键文件夹 → 属性 → 权限 → 手动删除

#### Bug 3 (已确认): BTRFS 跨删除恢复旧 ACL

- **现象**: `rm -rf 设计稿; mkdir 设计稿` 后，旧的显式 deny ACE 被 BTRFS 扩展属性异步恢复
- **窗口期**: 约 1-3 秒
- **修复**: `fix_one()` 在检查 ACL 前 `sleep 2` 等 BTRFS ACL 沉降完毕

#### Bug 4 (已确认): grep 正则模式无法匹配全角括号

- **现象**: `grep "视觉需求（读取）"` 在 POSIX locale 下正则模式匹配失败（全角括号 `（）` 被当作非法字节）
- **修复**: 改用 `grep -F "视觉需求"`（固定字符串，不解析正则；部分字符串匹配即可，不用带上括号）

### 阻塞: 旧进程残留

DSM 计划任务点"运行"不杀旧实例。旧实例运行的是有 Bug 2 和 Bug 4 的旧脚本，`fix_one` 的 deny 检查永远返回"没 deny"，每次重建文件夹都多加一条。

**尝试过的锁**:
- `/var/run/xxx.pid` — 目录不可写
- `/tmp/xxx.lock` + `mkdir` — 可能有 DSM 进程隔离
- 嵌入式 `flock` + `exec {FD}<>` — sudo 环境下无效

**解决方案**: 重启 NAS 清除残留，新版 DSM 计划任务命令改用：
```
flock -xn /volume1/技术部/.fix_design.lock -c '/bin/bash /volume1/技术部/fix_design_permissions.sh'
```

### 修复后的 fix_design_permissions.sh 关键点

1. 移除 `set -e` — 避免管道错误杀死脚本
2. `fix_one` 直接管道: `synoacltool -get | grep -F "视觉需求" | grep -q "deny"` — 绕过 echo + locale bug
3. `sleep 2` 等 BTRFS ACL 沉降
4. `while true` 外循环 + `sleep 5` 自动重启 inotifywait
5. 重启后补漏扫描 — 覆盖间隔期新建的文件夹
6. `flock -xn` 外挂锁 — 放 DSM 任务计划命令里

### 下一步（新对话）

1. **重启 NAS** 清除所有残留进程
2. DSM 计划任务命令改为 `flock -xn /volume1/技术部/.fix_design.lock -c '/bin/bash /volume1/技术部/fix_design_permissions.sh'`
3. 删除重建测试 — 应只有 1 条 deny
4. 测试通过后改 `BASE_PATH="/volume1/产品信息"` 上线
